"""Bounded asynchronous jobs. Production cannot submit without a real adapter."""

import asyncio
import logging
from pathlib import Path
from uuid import uuid4

from .config import Settings
from .errors import ApiError
from .schemas import GenerationRequest, Job, JobError, JobResult, MediaKind, OutputInfo, safe_output_filename
from .storage import JobStore, utc_now
from .workers import ModelRegistry, Worker, WorkerError, WorkerResult

logger = logging.getLogger("local_studio.jobs")
MEDIA_TYPES = {
    ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
    ".webp": "image/webp", ".mp4": "video/mp4",
}


class JobManager:
    def __init__(self, settings: Settings, registry: ModelRegistry, store: JobStore):
        self.settings = settings
        self.registry = registry
        self.store = store
        self.outputs_dir = settings.data_dir / "outputs"
        self.tasks: dict[str, asyncio.Task] = {}
        self.slots = asyncio.Semaphore(settings.max_concurrent_jobs)
        self.closing = False

    def initialize(self):
        self.store.initialize()
        self.store.recover_interrupted()
        self.outputs_dir.mkdir(parents=True, exist_ok=True)

    def submit(self, kind: MediaKind, request: GenerationRequest) -> Job:
        worker = self.registry.worker_for(request.model, kind)
        if worker is None:
            raise ApiError(409, "MODEL_NOT_AVAILABLE", f"Model '{request.model}' is not configured and available for {kind} generation. No inference was run.")
        if self.closing:
            raise ApiError(503, "SERVICE_STOPPING", "The backend is stopping. Retry after restarting it.")
        if len(self.tasks) >= self.settings.max_pending_jobs:
            raise ApiError(429, "JOB_QUEUE_FULL", "The local generation queue is full. Wait for an active job to finish.")
        validate = getattr(worker, "validate_request", None)
        if validate:
            validate(kind, request)
        now = utc_now()
        job = Job(id=str(uuid4()), status="pending", type=kind, model=request.model,
            prompt=request.prompt, parameters=request.model_dump(exclude={"model", "prompt"}), created_at=now, updated_at=now)
        self.store.insert(job)
        task = asyncio.create_task(self.run(job.id, kind, request, worker), name=f"generation-{job.id}")
        self.tasks[job.id] = task
        task.add_done_callback(lambda completed, job_id=job.id: self.tasks.pop(job_id, None))
        logger.info("Job %s accepted (%s)", job.id, kind)
        return job

    async def run(self, job_id: str, kind: MediaKind, request: GenerationRequest, worker: Worker):
        try:
            # The deadline includes queue waiting; only cooperative async adapters are valid.
            await asyncio.wait_for(self.execute(job_id, kind, request, worker), timeout=self.settings.job_timeout_seconds)
        except TimeoutError:
            self.fail(job_id, "JOB_TIMEOUT", "The generation worker exceeded the configured job timeout.")
        except asyncio.CancelledError:
            self.fail(job_id, "JOB_INTERRUPTED", "The backend stopped before this job completed. Submit a new request to retry.")
            raise
        except WorkerError as error:
            self.fail(job_id, error.code, error.message)
        except Exception:
            # Avoid returning exception text (prompts, paths, adapter secrets) to callers.
            logger.exception("Job %s failed", job_id)
            self.fail(job_id, "WORKER_FAILED", "The generation worker failed. Review the backend log for details.")

    async def execute(self, job_id: str, kind: MediaKind, request: GenerationRequest, worker: Worker):
        async with self.slots:
            job = self.store.get(job_id)
            job.status = "running"
            self.store.save(job)
            output_dir = self.outputs_dir / job_id
            output_dir.mkdir(exist_ok=False)
            def on_progress(progress: float | None):
                current = self.store.get(job_id)
                if current and current.status == "running" and current.progress != progress:
                    current.progress = progress
                    self.store.save(current)

            generate_with_progress = getattr(worker, "generate_with_progress", None)
            result = await generate_with_progress(kind, request, output_dir, on_progress) if generate_with_progress else await worker.generate(kind, request, output_dir)
            outputs = self.validate_outputs(job_id, output_dir, kind, result)
            job = self.store.get(job_id)
            job.status = "completed"
            job.progress = 100
            job.result = JobResult(outputs=outputs, metadata=result.metadata)
            self.store.save(job)
            logger.info("Job %s completed", job_id)

    def validate_outputs(self, job_id: str, directory: Path, kind: MediaKind, result: WorkerResult) -> list[OutputInfo]:
        if not isinstance(result, WorkerResult) or not result.outputs or len(result.outputs) > 8:
            raise ValueError("Worker must return between one and eight validated output assets")
        if directory.is_symlink() or directory.is_junction():
            raise ValueError("Output directory must not be a link or junction")
        directory = directory.resolve()
        if directory != (self.outputs_dir / job_id).absolute() or not directory.is_relative_to(self.outputs_dir.resolve()):
            raise ValueError("Output directory escaped storage")
        outputs = []
        seen = set()
        for output in result.outputs:
            if not safe_output_filename(output.filename) or output.filename in seen:
                raise ValueError("Invalid or duplicated output name")
            seen.add(output.filename)
            path = directory / output.filename
            expected_media = MEDIA_TYPES.get(path.suffix.lower())
            expected_prefix = "image/" if kind == "image" else "video/"
            if expected_media != output.media_type or not output.media_type.startswith(expected_prefix):
                raise ValueError("Output extension and media type do not match the requested feature")
            if path.is_symlink() or not path.resolve().is_relative_to(directory) or not path.is_file():
                raise ValueError("Worker output is missing or escaped its directory")
            if not 0 < path.stat().st_size <= self.settings.max_output_bytes:
                raise ValueError("Worker output is empty or exceeds the configured file limit")
            outputs.append(OutputInfo(url=f"/outputs/{job_id}/{output.filename}", media_type=output.media_type))
        return outputs

    def fail(self, job_id: str, code: str, message: str):
        job = self.store.get(job_id)
        if job and job.status in {"pending", "running"}:
            job.status = "failed"
            job.result = None
            job.error = JobError(code=code, message=message)
            self.store.save(job)
            logger.warning("Job %s failed (%s)", job_id, code)

    def output_path(self, job_id: str, filename: str) -> tuple[Path, str]:
        if not safe_output_filename(filename):
            raise ApiError(404, "OUTPUT_NOT_FOUND", "The requested output does not exist.")
        job = self.store.get(job_id)
        url = f"/outputs/{job_id}/{filename}"
        asset = next((item for item in job.result.outputs if item.url == url), None) if job and job.status == "completed" and job.result else None
        if asset is None:
            raise ApiError(404, "OUTPUT_NOT_FOUND", "The requested output does not exist.")
        directory = self.outputs_dir / job_id
        path = directory / filename
        if directory.is_symlink() or directory.is_junction() or path.is_symlink() or not path.resolve().is_relative_to(directory.resolve()) or not path.is_file():
            raise ApiError(404, "OUTPUT_NOT_FOUND", "The requested output does not exist.")
        if not 0 < path.stat().st_size <= self.settings.max_output_bytes:
            raise ApiError(404, "OUTPUT_NOT_FOUND", "The requested output does not exist.")
        return path, asset.media_type

    async def close(self):
        self.closing = True
        active = list(self.tasks.values())
        for task in active:
            task.cancel()
        if active:
            await asyncio.gather(*active, return_exceptions=True)
        # Also handles pending tasks cancelled before their coroutine first ran.
        self.store.recover_interrupted()
