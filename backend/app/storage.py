"""SQLite stores local job history atomically; file access is never path-based."""

from contextlib import contextmanager
from datetime import datetime, timezone
import sqlite3
from pathlib import Path

from .schemas import Job, JobError


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class JobStore:
    def __init__(self, data_dir: Path):
        self.data_dir = data_dir
        self.path = data_dir / "jobs.sqlite3"

    @contextmanager
    def connection(self):
        connection = sqlite3.connect(self.path, timeout=10)
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    def initialize(self):
        self.data_dir.mkdir(parents=True, exist_ok=True)
        with self.connection() as connection:
            connection.execute("PRAGMA journal_mode=WAL")
            connection.execute("CREATE TABLE IF NOT EXISTS jobs (id TEXT PRIMARY KEY, status TEXT NOT NULL, created_at TEXT NOT NULL, data TEXT NOT NULL)")
            connection.execute("CREATE INDEX IF NOT EXISTS jobs_created_at ON jobs(created_at)")

    def insert(self, job: Job):
        with self.connection() as connection:
            connection.execute("INSERT INTO jobs(id,status,created_at,data) VALUES(?,?,?,?)", (job.id, job.status, job.created_at, job.model_dump_json()))

    def save(self, job: Job):
        job.updated_at = utc_now()
        with self.connection() as connection:
            connection.execute("UPDATE jobs SET status=?,data=? WHERE id=?", (job.status, job.model_dump_json(), job.id))

    def get(self, job_id: str) -> Job | None:
        with self.connection() as connection:
            row = connection.execute("SELECT data FROM jobs WHERE id=?", (job_id,)).fetchone()
        return Job.model_validate_json(row[0]) if row else None

    def list(self, limit: int = 50, offset: int = 0) -> list[Job]:
        with self.connection() as connection:
            rows = connection.execute("SELECT data FROM jobs ORDER BY created_at DESC LIMIT ? OFFSET ?", (limit, offset)).fetchall()
        return [Job.model_validate_json(row[0]) for row in rows]

    def recover_interrupted(self):
        with self.connection() as connection:
            rows = connection.execute("SELECT data FROM jobs WHERE status IN ('pending','running')").fetchall()
            for row in rows:
                job = Job.model_validate_json(row[0])
                job.status = "failed"
                job.updated_at = utc_now()
                job.result = None
                job.error = JobError(code="JOB_INTERRUPTED", message="The backend stopped before this job completed. Submit a new request to retry.")
                connection.execute("UPDATE jobs SET status=?,data=? WHERE id=?", (job.status, job.model_dump_json(), job.id))
