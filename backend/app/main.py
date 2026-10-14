"""Local FastAPI foundation. No generation is available without real workers."""

from contextlib import asynccontextmanager
import logging
from urllib.parse import urlsplit
from uuid import UUID

from fastapi import FastAPI, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.cors import CORSMiddleware

from .config import Settings
from .errors import ApiError
from .jobs import JobManager
from .schemas import ImageRequest, Job, LipSyncRequest, VideoRequest
from .storage import JobStore
from .workers import ModelRegistry, default_registry

VERSION = "0.1.0"
logger = logging.getLogger("local_studio.api")


class LocalBoundaryMiddleware:
    """Block DNS rebinding, foreign browser writes, and oversized JSON bodies."""

    def __init__(self, app, settings: Settings):
        self.app = app
        self.settings = settings

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        headers = {key.decode("latin-1").lower(): value.decode("latin-1") for key, value in scope.get("headers", [])}
        try:
            parsed = urlsplit("//" + headers.get("host", ""))
            valid_host = (
                parsed.hostname in {"localhost", "127.0.0.1", "::1"}
                and not parsed.username and not parsed.password
                and not parsed.path and not parsed.query and not parsed.fragment
            )
            _ = parsed.port
        except ValueError:
            valid_host = False
        if not valid_host:
            await JSONResponse({"error": {"code": "HOST_NOT_ALLOWED", "message": "This API accepts only loopback host names."}}, status_code=403)(scope, receive, send)
            return
        if scope["method"] in {"POST", "PUT", "PATCH", "DELETE"}:
            origin = headers.get("origin")
            if (origin is not None and origin not in self.settings.allowed_origins) or (
                origin is None and headers.get("sec-fetch-site") == "cross-site"
            ):
                await JSONResponse({"error": {"code": "ORIGIN_NOT_ALLOWED", "message": "Requests must come from a configured local frontend origin."}}, status_code=403)(scope, receive, send)
                return
        if scope["method"] == "POST" and scope["path"].startswith("/generate/"):
            chunks = []
            size = 0
            while True:
                message = await receive()
                if message["type"] == "http.disconnect":
                    return
                size += len(message.get("body", b""))
                if size > self.settings.max_request_bytes:
                    await JSONResponse({"error": {"code": "REQUEST_TOO_LARGE", "message": "The generation request exceeds the configured size limit."}}, status_code=413)(scope, receive, send)
                    return
                chunks.append(message.get("body", b""))
                if not message.get("more_body", False):
                    break
            delivered = False

            async def buffered_receive():
                nonlocal delivered
                if not delivered:
                    delivered = True
                    return {"type": "http.request", "body": b"".join(chunks), "more_body": False}
                return await receive()

            await self.app(scope, buffered_receive, send)
        else:
            await self.app(scope, receive, send)


def create_app(settings: Settings | None = None, registry: ModelRegistry | None = None) -> FastAPI:
    settings = settings or Settings.from_environment()
    registry = registry if registry is not None else default_registry(settings)
    manager = JobManager(settings, registry, JobStore(settings.data_dir))

    @asynccontextmanager
    async def lifespan(application):
        manager.initialize()
        logger.info("Local API started; %d available model adapters", sum(model.available for model in registry.models()))
        try:
            yield
        finally:
            await manager.close()

    # Disable CDN-backed interactive docs; /openapi.json remains entirely local.
    application = FastAPI(title="Self-Hosted AI Studio", version=VERSION, lifespan=lifespan, docs_url=None, redoc_url=None)
    application.state.settings = settings
    application.state.registry = registry
    application.state.job_manager = manager
    application.add_middleware(LocalBoundaryMiddleware, settings=settings)
    application.add_middleware(CORSMiddleware, allow_origins=list(settings.allowed_origins), allow_credentials=False,
        allow_methods=["GET", "POST"], allow_headers=["Content-Type"], expose_headers=["Content-Disposition"])

    @application.exception_handler(ApiError)
    async def api_error_handler(request: Request, error: ApiError):
        return JSONResponse(error.payload(), status_code=error.status_code)

    @application.exception_handler(RequestValidationError)
    async def validation_error_handler(request: Request, error: RequestValidationError):
        details = [{"loc": list(item["loc"]), "message": item["msg"], "type": item["type"]} for item in error.errors()]
        return JSONResponse({"error": {"code": "VALIDATION_ERROR", "message": "The request contains invalid or unsupported parameters.", "details": details}}, status_code=422)

    @application.exception_handler(StarletteHTTPException)
    async def http_error_handler(request: Request, error: StarletteHTTPException):
        return JSONResponse({"error": {"code": "NOT_FOUND" if error.status_code == 404 else "HTTP_ERROR", "message": str(error.detail)}}, status_code=error.status_code, headers=error.headers)

    @application.exception_handler(Exception)
    async def unexpected_error_handler(request: Request, error: Exception):
        logger.error("Unhandled local API error", exc_info=error)
        return JSONResponse({"error": {"code": "INTERNAL_ERROR", "message": "The local backend encountered an error. Review its log for details."}}, status_code=500)

    @application.get("/health")
    async def health():
        await registry.refresh()
        count = sum(model.available and model.configured for model in registry.models())
        return {"status": "ok", "service": "self-hosted-ai-studio", "version": VERSION,
            "inference_ready": count > 0, "available_models": count}

    @application.get("/models")
    async def models():
        await registry.refresh()
        return {"models": registry.models()}

    @application.post("/generate/image", status_code=202, response_model=Job)
    async def generate_image(request: ImageRequest):
        await registry.refresh(request.model)
        return manager.submit("image", request)

    @application.post("/generate/video", status_code=202, response_model=Job)
    async def generate_video(request: VideoRequest):
        await registry.refresh(request.model)
        return manager.submit("video", request)

    @application.post("/generate/lipsync", status_code=202, response_model=Job)
    async def generate_lipsync(request: LipSyncRequest):
        await registry.refresh(request.model)
        return manager.submit("lipsync", request)

    @application.get("/jobs")
    async def list_jobs(limit: int = Query(default=50, ge=1, le=200), offset: int = Query(default=0, ge=0, le=1000000)):
        return {"jobs": manager.store.list(limit=limit, offset=offset)}

    @application.get("/jobs/{job_id}", response_model=Job)
    async def get_job(job_id: UUID):
        job = manager.store.get(str(job_id))
        if job is None:
            raise ApiError(404, "JOB_NOT_FOUND", "This local job does not exist.")
        return job

    @application.get("/outputs/{job_id}/{filename}")
    async def get_output(job_id: UUID, filename: str):
        path, media_type = manager.output_path(str(job_id), filename)
        return FileResponse(path, media_type=media_type, filename=filename, content_disposition_type="inline",
            headers={"X-Content-Type-Options": "nosniff", "Cache-Control": "private, no-cache"})

    @application.post("/uploads")
    async def upload_unavailable():
        raise ApiError(501, "UPLOAD_NOT_AVAILABLE", "Validated local media uploads are planned for the next integration phase. No file was saved.")

    return application


app = create_app()
