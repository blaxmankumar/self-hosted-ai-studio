"""Provider-independent workers; adapters are unavailable until checked.

Adapters must be cooperatively asynchronous and propagate cancellation. A GPU
process/subprocess adapter must stop its underlying inference when cancelled;
wrapping blocking inference in asyncio.to_thread does NOT satisfy this contract.
"""

from dataclasses import dataclass, field
import asyncio
import time
from pathlib import Path
from typing import Callable, Protocol

from .schemas import GenerationRequest, MediaKind, ModelInfo


@dataclass(frozen=True)
class WorkerAvailability:
    available: bool
    reason: str


class WorkerError(Exception):
    """An adapter failure with a fixed, safe public code and message."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True)
class WorkerOutput:
    filename: str
    media_type: str


@dataclass(frozen=True)
class WorkerResult:
    outputs: tuple[WorkerOutput, ...]
    metadata: dict = field(default_factory=dict)


class Worker(Protocol):
    async def generate(self, kind: MediaKind, request: GenerationRequest, output_dir: Path) -> WorkerResult:
        """Produce genuine assets inside output_dir, or raise; honor cancellation."""
        ...


class ManagedWorker(Worker, Protocol):
    """Optional lifecycle interface for local or remote GPU adapters.

    Worker-only adapters remain compatible. Managed adapters add live readiness,
    parameter validation before job creation, and genuine progress reporting.
    """

    async def check_availability(self, kind: MediaKind) -> WorkerAvailability:
        ...

    def validate_request(self, kind: MediaKind, request: GenerationRequest) -> None:
        ...

    async def generate_with_progress(self, kind: MediaKind, request: GenerationRequest,
            output_dir: Path, on_progress: Callable[[float | None], None]) -> WorkerResult:
        ...


@dataclass(frozen=True)
class Registration:
    info: ModelInfo
    worker: Worker | None = None


class ModelRegistry:
    def __init__(self, registrations: tuple[Registration, ...] = ()):
        self._entries = {}
        self._refresh_lock = asyncio.Lock()
        self._checked_at: dict[str, float] = {}
        for registration in registrations:
            self.register(registration)

    def register(self, registration: Registration):
        if registration.info.id in self._entries:
            raise ValueError("Model ids must be unique")
        if registration.info.available and (not registration.info.configured or registration.worker is None):
            raise ValueError("An available model must have a configured real worker")
        self._entries[registration.info.id] = registration

    def models(self) -> list[ModelInfo]:
        return [entry.info for entry in self._entries.values()]

    def worker_for(self, model: str, kind: MediaKind) -> Worker | None:
        entry = self._entries.get(model)
        if not entry or entry.info.type != kind or not entry.info.configured or not entry.info.available:
            return None
        return entry.worker

    async def refresh(self, model: str | None = None):
        """Recheck managed adapters; injected legacy workers keep their contract."""
        async with self._refresh_lock:
            for model_id, entry in tuple(self._entries.items()):
                check = getattr(entry.worker, "check_availability", None)
                if (model is None or model == model_id) and entry.info.configured and check:
                    # /health and /models are requested together by the UI. Share
                    # their probe for one second, but always recheck submissions.
                    if model is None and time.monotonic() - self._checked_at.get(model_id, float("-inf")) < 1:
                        continue
                    try:
                        state = await check(entry.info.type)
                    except Exception:
                        state = WorkerAvailability(False, "The configured worker could not be checked.")
                    self._entries[model_id] = Registration(entry.info.model_copy(update={
                        "available": state.available, "reason": state.reason,
                    }), entry.worker)
                    self._checked_at[model_id] = time.monotonic()


def default_registry(settings=None) -> ModelRegistry:
    from .config import Settings
    from .remote_worker import HttpGPUWorker

    settings = settings or Settings()
    remote = HttpGPUWorker(settings) if settings.remote_worker_url else None
    return ModelRegistry((
        Registration(ModelInfo(id="local-image", name="Local image worker", type="image",
            reason="No local image adapter or model is installed. Hardware compatibility must be checked before setup.",
            capabilities=["text-to-image", "image-to-image"])),
        Registration(ModelInfo(id="local-video", name="Local video worker", type="video",
            reason="No local video adapter is installed. Heavy video models have not been approved or tested on the 4 GB GPU.",
            capabilities=["text-to-video", "image-to-video"])),
        Registration(ModelInfo(id="local-lipsync", name="Local lip-sync worker", type="lipsync",
            reason="No local lip-sync adapter, model, or validated upload pipeline is installed.",
            capabilities=["image-audio-to-video", "video-audio-to-video"])),
        Registration(ModelInfo(id="remote-image", name="Remote GPU image worker", type="image",
            configured=remote is not None, available=False,
            reason="Worker readiness has not been checked." if remote else "No permitted GPU worker endpoint is configured. Set LOCAL_STUDIO_REMOTE_WORKER_URL after choosing a service that permits inference hosting.",
            capabilities=["text-to-image"],
            inputs={"aspect_ratio": {"enum": ["1:1"], "default": "1:1"}}), remote),
    ))
