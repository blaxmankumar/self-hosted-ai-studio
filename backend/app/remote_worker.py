"""Opt-in HTTP adapter for an operator-authorized GPU inference service.

This is a client, not a notebook server, GPU runtime, provisioning tool, or
provider API. The v1 contract is documented in docs/GPU_WORKER_INTEGRATION.md.
No destination or credential can be supplied by a browser generation request.
"""

import asyncio
from collections.abc import Callable
import json
import logging
from pathlib import Path
from typing import Literal
from uuid import UUID

import httpx
from PIL import Image
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from .config import Settings
from .errors import ApiError
from .schemas import GenerationRequest, MediaKind, safe_output_filename
from .workers import WorkerAvailability, WorkerError, WorkerOutput, WorkerResult

logger = logging.getLogger("local_studio.worker")
IMAGE_FORMATS = {"image/png": "PNG", "image/jpeg": "JPEG", "image/webp": "WEBP"}
EXTENSIONS = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".webp": "image/webp"}


class WireModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class RemoteModel(WireModel):
    id: str = Field(min_length=1, max_length=128)
    type: MediaKind
    ready: bool
    capabilities: list[str] = Field(max_length=16)


class RemoteHealth(WireModel):
    protocol_version: int = Field(ge=1, le=1)
    models: list[RemoteModel] = Field(max_length=100)


class RemoteOutput(WireModel):
    filename: str
    media_type: Literal["image/png", "image/jpeg", "image/webp"]

    @field_validator("filename")
    @classmethod
    def validate_filename(cls, value):
        if not safe_output_filename(value) or Path(value).suffix not in EXTENSIONS:
            raise ValueError("Unsafe image output name")
        return value


class RemoteResult(WireModel):
    model: str
    inference_performed: bool
    mock: bool = False
    test_only: bool = False
    outputs: list[RemoteOutput] = Field(min_length=1, max_length=8)


class RemoteJob(WireModel):
    id: UUID
    status: Literal["pending", "running", "completed", "failed"]
    progress: float | None = Field(default=None, ge=0, le=100, allow_inf_nan=False)
    result: RemoteResult | None = None
    error: "RemoteFailure | None" = None


class RemoteFailure(WireModel):
    code: str = Field(max_length=128)
    message: str = Field(max_length=8000)


class HttpGPUWorker:
    def __init__(self, settings: Settings, transport: httpx.AsyncBaseTransport | None = None):
        if not settings.remote_worker_url:
            raise ValueError("A worker endpoint must be explicitly configured")
        self.settings = settings
        # Transport injection is a test boundary, never an environment toggle.
        self.transport = transport

    def client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            base_url=self.settings.remote_worker_url,
            headers={"Accept-Encoding": "identity", **({"Authorization": f"Bearer {self.settings.remote_worker_token}"} if self.settings.remote_worker_token else {})},
            timeout=self.settings.worker_request_timeout_seconds,
            follow_redirects=False, trust_env=False, transport=self.transport,
        )

    @staticmethod
    def check_response(response: httpx.Response):
        if response.status_code in {401, 403}:
            raise WorkerError("WORKER_AUTH_FAILED", "The GPU worker rejected its server-side credential. Check backend configuration.")
        if response.status_code >= 500 or response.status_code in {408, 429}:
            raise WorkerError("WORKER_UNAVAILABLE", "The GPU worker is unavailable or busy. Retry after checking the worker.")
        if not 200 <= response.status_code < 300:
            raise WorkerError("WORKER_PROTOCOL_ERROR", "The GPU worker returned an unsupported response. Check its v1 contract.")
        if response.headers.get("content-encoding", "identity").lower() != "identity":
            raise WorkerError("WORKER_PROTOCOL_ERROR", "The GPU worker must return uncompressed HTTP bodies for bounded transfers.")

    async def request_json(self, client, method, path, schema, **kwargs):
        try:
            return await asyncio.wait_for(self._request_json(client, method, path, schema, **kwargs),
                timeout=self.settings.worker_request_timeout_seconds)
        except TimeoutError:
            raise WorkerError("WORKER_UNAVAILABLE", "The GPU worker did not respond before the connection deadline.") from None

    async def _request_json(self, client, method, path, schema, **kwargs):
        try:
            async with client.stream(method, path, **kwargs) as response:
                self.check_response(response)
                if response.headers.get("content-type", "").split(";", 1)[0].strip() != "application/json":
                    raise WorkerError("WORKER_PROTOCOL_ERROR", "The GPU worker did not return the expected JSON contract.")
                data = bytearray()
                async for chunk in response.aiter_bytes():
                    data.extend(chunk)
                    if len(data) > 65536:
                        raise WorkerError("WORKER_PROTOCOL_ERROR", "The GPU worker response exceeded the JSON limit.")
                # JSON-mode validation permits a UUID string, with strict scalar checks.
                return schema.model_validate_json(bytes(data))
        except httpx.HTTPError:
            raise WorkerError("WORKER_UNAVAILABLE", "The configured GPU worker could not be reached. Check the worker connection.") from None
        except (ValidationError, ValueError, json.JSONDecodeError):
            raise WorkerError("WORKER_PROTOCOL_ERROR", "The GPU worker returned an invalid v1 response.") from None

    async def check_availability(self, kind: MediaKind) -> WorkerAvailability:
        if kind != "image":
            return WorkerAvailability(False, "This adapter currently supports text-to-image only.")
        try:
            async with self.client() as client:
                health = await self.request_json(client, "GET", "/v1/health", RemoteHealth)
            matches = [model for model in health.models if model.id == self.settings.remote_worker_model and model.type == kind]
            if len(matches) != 1 or not matches[0].ready or "text-to-image" not in matches[0].capabilities:
                return WorkerAvailability(False, "The configured image model is not ready on the GPU worker.")
            return WorkerAvailability(True, "The GPU worker reports the configured text-to-image model ready.")
        except WorkerError as error:
            return WorkerAvailability(False, error.message)

    def validate_request(self, kind: MediaKind, request: GenerationRequest):
        if (
            kind != "image" or request.aspect_ratio != "1:1" or request.width != 512 or request.height != 512
            or any(value is not None for value in (request.image_url, request.audio_url, request.video_url,
                request.duration, request.resolution, request.quality))
        ):
            raise ApiError(422, "UNSUPPORTED_WORKER_PARAMETERS", "This worker integration currently accepts 512 x 512 text-to-image requests only, without media inputs or quality labels.")

    async def generate(self, kind, request, output_dir) -> WorkerResult:
        return await self.generate_with_progress(kind, request, output_dir, lambda progress: None)

    async def generate_with_progress(self, kind: MediaKind, request: GenerationRequest, output_dir: Path,
            on_progress: Callable[[float | None], None]) -> WorkerResult:
        self.validate_request(kind, request)
        remote_id = None
        finished = False
        async with self.client() as client:
            try:
                job = await self.request_json(client, "POST", "/v1/jobs", RemoteJob,
                    headers={"Idempotency-Key": output_dir.name},
                    json={"model": self.settings.remote_worker_model, "kind": kind,
                        "parameters": request.model_dump(include={"prompt", "negative_prompt", "width", "height", "seed"})})
                remote_id = job.id
                while True:
                    if job.id != remote_id:
                        raise WorkerError("WORKER_PROTOCOL_ERROR", "The GPU worker returned a different job identifier.")
                    # Completion is announced only after the image has been verified locally.
                    on_progress(job.progress if job.status != "completed" else None)
                    if job.status == "failed":
                        raise WorkerError("WORKER_FAILED", "The GPU worker reported that image generation failed. Check its logs.")
                    if job.status == "completed":
                        result = job.result
                        if not result or result.model != self.settings.remote_worker_model or not result.inference_performed or result.mock or result.test_only:
                            raise WorkerError("WORKER_INVALID_OUTPUT", "The GPU worker did not confirm genuine inference for the configured model. No image result was accepted.")
                        names = [output.filename for output in result.outputs]
                        if len(names) != len(set(names)):
                            raise WorkerError("WORKER_INVALID_OUTPUT", "The GPU worker returned duplicate image outputs.")
                        for output in result.outputs:
                            await self.download(client, remote_id, output, output_dir, request)
                        finished = True
                        return WorkerResult(tuple(WorkerOutput(output.filename, output.media_type) for output in result.outputs),
                            metadata={"worker": "http-v1", "remote_model": self.settings.remote_worker_model,
                                "remote_job_id": str(remote_id), "inference_performed": True})
                    await asyncio.sleep(self.settings.worker_poll_interval_seconds)
                    job = await self.request_json(client, "GET", f"/v1/jobs/{remote_id}", RemoteJob)
            finally:
                if remote_id is not None and not finished:
                    # The service must cooperate. Network failures cannot guarantee
                    # remote cancellation; no automatic resubmission is performed.
                    try:
                        await asyncio.wait_for(self.cancel(client, remote_id), timeout=2)
                    except (Exception, asyncio.CancelledError):
                        logger.warning("GPU worker cancellation was not acknowledged; check the worker directly")

    async def cancel(self, client, remote_id):
        async with client.stream("DELETE", f"/v1/jobs/{remote_id}", timeout=2) as response:
            if response.status_code not in {200, 204}:
                raise WorkerError("WORKER_PROTOCOL_ERROR", "Worker cancellation was not acknowledged")

    async def download(self, client, remote_id, output, directory, request):
        destination = directory / output.filename
        partial = directory / (output.filename + ".part")
        try:
            if EXTENSIONS.get(destination.suffix) != output.media_type:
                raise ValueError("Output MIME does not match its extension")
            async with client.stream("GET", f"/v1/jobs/{remote_id}/outputs/{output.filename}") as response:
                self.check_response(response)
                media_type = response.headers.get("content-type", "").split(";", 1)[0].strip()
                if media_type != output.media_type:
                    raise ValueError("Output response is not the declared image type")
                total = 0
                with partial.open("xb") as target:
                    async for chunk in response.aiter_bytes():
                        total += len(chunk)
                        if total > self.settings.max_output_bytes:
                            raise ValueError("Image exceeds the output limit")
                        target.write(chunk)
                if total == 0:
                    raise ValueError("Empty image output")
            # Size is bounded before decoding, and dimensions before pixel loading.
            with Image.open(partial, formats=list(IMAGE_FORMATS.values())) as image:
                if image.format != IMAGE_FORMATS[output.media_type] or image.size != (request.width, request.height) or getattr(image, "is_animated", False):
                    raise ValueError("Image format, dimensions or frame count is unsupported")
                image.verify()
            with Image.open(partial, formats=list(IMAGE_FORMATS.values())) as image:
                image.load()
            partial.replace(destination)
        except WorkerError:
            raise
        except httpx.HTTPError:
            raise WorkerError("WORKER_UNAVAILABLE", "The GPU worker image transfer was interrupted. Check the worker connection.") from None
        except (OSError, ValueError, Image.DecompressionBombError):
            raise WorkerError("WORKER_INVALID_OUTPUT", "The GPU worker returned an invalid, oversized, or incompatible image. No image result was accepted.") from None
        finally:
            partial.unlink(missing_ok=True)
