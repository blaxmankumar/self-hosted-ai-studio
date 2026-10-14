"""Small, explicit local configuration; never downloads or registers models."""

from dataclasses import dataclass, field
from ipaddress import ip_address
import os
from pathlib import Path
import re
from urllib.parse import urlsplit

BACKEND_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ORIGINS = (
    "http://localhost:3000", "http://127.0.0.1:3000",
    "http://localhost:5173", "http://127.0.0.1:5173",
)


def read_env_file(path: Path) -> dict[str, str]:
    """Read simple KEY=value lines, with process environment taking precedence."""
    if not path.is_file():
        return {}
    values = {}
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        key, separator, value = line.partition("=")
        if not separator or not key.strip().startswith("LOCAL_STUDIO_"):
            continue
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        values[key.strip()] = value
    return values


def validate_origin(origin: str) -> str:
    parsed = urlsplit(origin)
    if (
        parsed.scheme not in {"http", "https"}
        or parsed.hostname not in {"localhost", "127.0.0.1", "::1"}
        or parsed.username is not None or parsed.password is not None
        or parsed.path or parsed.query or parsed.fragment
    ):
        raise ValueError("CORS origins must be exact loopback HTTP origins, without paths or wildcards")
    # Accessing port also rejects invalid port strings.
    _ = parsed.port
    return origin


def validate_worker_url(url: str, token: str) -> str:
    """Worker destinations are operator configuration, never user request URLs."""
    parsed = urlsplit(url)
    try:
        loopback = parsed.hostname == "localhost" or ip_address(parsed.hostname or "").is_loopback
    except ValueError:
        loopback = False
    if (
        parsed.scheme not in {"http", "https"} or not parsed.hostname
        or parsed.username is not None or parsed.password is not None
        or parsed.path not in {"", "/"} or parsed.query or parsed.fragment
        or (parsed.scheme != "https" and not loopback)
        or any(character.isspace() for character in url) or "\\" in url
    ):
        raise ValueError("Worker URL must be an HTTPS origin (HTTP allowed only on loopback), without credentials or paths")
    _ = parsed.port
    if not loopback and not token:
        raise ValueError("A remote worker requires a server-side bearer token")
    return url.rstrip("/")


@dataclass(frozen=True)
class Settings:
    data_dir: Path = BACKEND_ROOT / "data"
    allowed_origins: tuple[str, ...] = DEFAULT_ORIGINS
    job_timeout_seconds: float = 300
    max_pending_jobs: int = 8
    max_concurrent_jobs: int = 1
    max_request_bytes: int = 65536
    max_output_bytes: int = 100 * 1024 * 1024
    remote_worker_url: str = ""
    remote_worker_token: str = field(default="", repr=False)
    remote_worker_model: str = "stable-diffusion-v1-5"
    worker_request_timeout_seconds: float = 5
    worker_poll_interval_seconds: float = 1

    def __post_init__(self):
        object.__setattr__(self, "data_dir", Path(self.data_dir).resolve())
        if not self.allowed_origins:
            raise ValueError("At least one exact loopback frontend origin is required")
        for origin in self.allowed_origins:
            validate_origin(origin)
        if not 0 < self.job_timeout_seconds <= 3600:
            raise ValueError("Job timeout must be between 0 and 3600 seconds")
        if not 1 <= self.max_concurrent_jobs <= self.max_pending_jobs <= 32:
            raise ValueError("Job concurrency and queue must be between 1 and 32")
        if not 1024 <= self.max_request_bytes <= 1024 * 1024:
            raise ValueError("Request limit must be between 1 KiB and 1 MiB")
        if not 1 <= self.max_output_bytes <= 1024 * 1024 * 1024:
            raise ValueError("Output limit must be between 1 byte and 1 GiB")
        if any(ord(character) < 33 or ord(character) > 126 for character in self.remote_worker_token):
            raise ValueError("Worker token must contain printable ASCII without spaces")
        if self.remote_worker_url:
            object.__setattr__(self, "remote_worker_url", validate_worker_url(self.remote_worker_url, self.remote_worker_token))
        elif self.remote_worker_token:
            raise ValueError("Worker token requires a configured worker URL")
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._/-]{0,127}", self.remote_worker_model):
            raise ValueError("Worker model must be a bounded model identifier")
        if not 0 < self.worker_request_timeout_seconds <= 5:
            raise ValueError("Worker request timeout must be between 0 and 5 seconds (below the local proxy deadline)")
        if not 0 < self.worker_poll_interval_seconds <= 30:
            raise ValueError("Worker poll interval must be between 0 and 30 seconds")

    @classmethod
    def from_environment(cls):
        values = read_env_file(BACKEND_ROOT / ".env")
        values.update(os.environ)
        configured_dir = values.get("LOCAL_STUDIO_DATA_DIR", "data")
        data_dir = Path(configured_dir)
        if not data_dir.is_absolute():
            data_dir = BACKEND_ROOT / data_dir
        origins = tuple(
            item.strip() for item in values.get("LOCAL_STUDIO_FRONTEND_ORIGINS", ",".join(DEFAULT_ORIGINS)).split(",")
            if item.strip()
        )
        return cls(
            data_dir=data_dir,
            allowed_origins=origins,
            job_timeout_seconds=float(values.get("LOCAL_STUDIO_JOB_TIMEOUT_SECONDS", "300")),
            max_pending_jobs=int(values.get("LOCAL_STUDIO_MAX_PENDING_JOBS", "8")),
            max_concurrent_jobs=int(values.get("LOCAL_STUDIO_MAX_CONCURRENT_JOBS", "1")),
            max_request_bytes=int(values.get("LOCAL_STUDIO_MAX_REQUEST_BYTES", "65536")),
            max_output_bytes=int(values.get("LOCAL_STUDIO_MAX_OUTPUT_BYTES", str(100 * 1024 * 1024))),
            remote_worker_url=values.get("LOCAL_STUDIO_REMOTE_WORKER_URL", "").strip(),
            remote_worker_token=values.get("LOCAL_STUDIO_REMOTE_WORKER_TOKEN", ""),
            remote_worker_model=values.get("LOCAL_STUDIO_REMOTE_WORKER_MODEL", "stable-diffusion-v1-5"),
            worker_request_timeout_seconds=float(values.get("LOCAL_STUDIO_WORKER_REQUEST_TIMEOUT_SECONDS", "5")),
            worker_poll_interval_seconds=float(values.get("LOCAL_STUDIO_WORKER_POLL_INTERVAL_SECONDS", "1")),
        )
