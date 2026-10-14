"""Provider-independent, deliberately bounded generation requests."""

import re
from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

MediaKind = Literal["image", "video", "lipsync"]
SAFE_FILENAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}\Z")
SAFE_OUTPUT_FILENAME = re.compile(r"[A-Za-z0-9_-]+\.(?:png|jpg|jpeg|webp|mp4)\Z")
LOCAL_ASSET = re.compile(r"/(?:outputs|uploads)/([0-9a-fA-F-]{36})/([A-Za-z0-9][A-Za-z0-9._-]{0,127})\Z")


def safe_filename(name: str) -> bool:
    return bool(SAFE_FILENAME.fullmatch(name)) and ".." not in name


def safe_output_filename(name: str) -> bool:
    return len(name) <= 128 and bool(SAFE_OUTPUT_FILENAME.fullmatch(name))


class GenerationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    model: str = Field(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9][A-Za-z0-9._/-]*$")
    prompt: str = Field(default="", max_length=8000)
    negative_prompt: str | None = Field(default=None, max_length=8000)
    aspect_ratio: str = Field(default="1:1", pattern=r"^[1-9][0-9]?:[1-9][0-9]?$", max_length=5)
    resolution: str | None = Field(default=None, min_length=1, max_length=32)
    width: Annotated[int, Field(strict=True, ge=64, le=2048, multiple_of=8)] = 512
    height: Annotated[int, Field(strict=True, ge=64, le=2048, multiple_of=8)] = 512
    seed: Annotated[int, Field(strict=True, ge=0, le=4294967295)] | None = None
    duration: Annotated[float, Field(strict=True, gt=0, le=30, allow_inf_nan=False)] | None = None
    quality: str | None = Field(default=None, min_length=1, max_length=32)
    image_url: str | None = Field(default=None, max_length=200)
    audio_url: str | None = Field(default=None, max_length=200)
    video_url: str | None = Field(default=None, max_length=200)

    @field_validator("image_url", "audio_url", "video_url")
    @classmethod
    def local_media_only(cls, value):
        if value is None:
            return value
        matched = LOCAL_ASSET.fullmatch(value)
        if not matched or not safe_filename(matched.group(2)):
            raise ValueError("Media must refer to a local /outputs/{UUID}/{filename} or /uploads/{UUID}/{filename} asset")
        UUID(matched.group(1))
        return value


class ImageRequest(GenerationRequest):
    prompt: str = Field(min_length=1, max_length=8000)


class VideoRequest(GenerationRequest):
    prompt: str = Field(min_length=1, max_length=8000)


class LipSyncRequest(GenerationRequest):
    """Input requirements are enforced by a future real adapter, after readiness."""


class ModelInfo(BaseModel):
    model_config = ConfigDict(frozen=True)
    id: str
    name: str
    type: MediaKind
    configured: bool = False
    available: bool = False
    reason: str
    capabilities: list[str] = Field(default_factory=list)
    inputs: dict = Field(default_factory=dict)


class JobError(BaseModel):
    code: str
    message: str


class OutputInfo(BaseModel):
    url: str
    media_type: str


class JobResult(BaseModel):
    outputs: list[OutputInfo]
    metadata: dict = Field(default_factory=dict)


class Job(BaseModel):
    id: str
    status: Literal["pending", "running", "completed", "failed"]
    type: MediaKind
    model: str
    prompt: str
    parameters: dict
    created_at: str
    updated_at: str
    progress: float | None = Field(default=None, ge=0, le=100, allow_inf_nan=False)
    result: JobResult | None = None
    error: JobError | None = None
