"""Transport/persistence tests only. These fixtures never perform AI inference.

The test worker is injected only into create_app in this test module. It is not
discoverable by the production entry point, registry, settings, or routes.
"""

import asyncio
import base64
from pathlib import Path
import tempfile
import time
import unittest
from uuid import uuid4

from fastapi.testclient import TestClient

from backend.app.config import Settings
from backend.app.main import create_app
from backend.app.schemas import Job, ModelInfo
from backend.app.storage import JobStore, utc_now
from backend.app.workers import ModelRegistry, Registration, WorkerOutput, WorkerResult

# A one-pixel PNG is strictly an API/file transport fixture, not a generated image.
TRANSPORT_FIXTURE = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII=")


class IsolatedTransportWorker:
    def __init__(self, delay=0.02, failure=False, unsafe=False, filename="transport-fixture.png"):
        self.delay = delay
        self.failure = failure
        self.unsafe = unsafe
        self.filename = filename
        self.cancelled = False

    async def generate(self, kind, request, output_dir):
        try:
            await asyncio.sleep(self.delay)
        except asyncio.CancelledError:
            self.cancelled = True
            raise
        if self.failure:
            raise RuntimeError("isolated transport fixture failure")
        if self.unsafe:
            return WorkerResult(outputs=(WorkerOutput("../unsafe.png", "image/png"),))
        (output_dir / self.filename).write_bytes(TRANSPORT_FIXTURE)
        (output_dir / "unregistered.png").write_bytes(TRANSPORT_FIXTURE)
        return WorkerResult(outputs=(WorkerOutput(self.filename, "image/png"),), metadata={"test_only": True, "inference_performed": False})


class BackendTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(prefix="local-studio-test-")
        self.data_dir = Path(self.directory.name)

    def tearDown(self):
        self.directory.cleanup()

    def application(self, worker=None, **options):
        registry = None
        if worker is not None:
            registry = ModelRegistry((Registration(ModelInfo(id="isolated-transport-fixture", name="Test-only transport fixture", type="image",
                configured=True, available=True, reason="Injected only by tests; not AI inference", capabilities=["text-to-image"]), worker),))
        return create_app(Settings(data_dir=self.data_dir, **options), registry)

    def client(self, application):
        return TestClient(application, base_url="http://127.0.0.1:8000")

    def submit(self, client):
        response = client.post("/generate/image", json={"model": "isolated-transport-fixture", "prompt": "API transport test only"})
        self.assertEqual(response.status_code, 202, response.text)
        self.assertEqual(response.json()["status"], "pending")
        return response.json()["id"]

    def wait_for(self, client, job_id, states=("completed", "failed")):
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline:
            job = client.get(f"/jobs/{job_id}").json()
            if job["status"] in states:
                return job
            time.sleep(0.005)
        self.fail(f"Job {job_id} did not reach {states}")

    def test_health_and_truthful_model_catalog(self):
        with self.client(self.application()) as client:
            health = client.get("/health").json()
            self.assertEqual(health["status"], "ok")
            self.assertFalse(health["inference_ready"])
            self.assertEqual(health["available_models"], 0)
            models = client.get("/models").json()["models"]
            self.assertEqual({model["type"] for model in models}, {"image", "video", "lipsync"})
            self.assertTrue(all(not model["available"] and not model["configured"] and model["reason"] for model in models))
            self.assertEqual(client.get("/jobs").json(), {"jobs": []})

    def test_unavailable_models_never_create_jobs(self):
        with self.client(self.application()) as client:
            for kind in ("image", "video", "lipsync"):
                for model in (f"local-{kind}", "unknown-model"):
                    with self.subTest(kind=kind, model=model):
                        response = client.post(f"/generate/{kind}", json={"model": model, "prompt": "test"})
                        self.assertEqual(response.status_code, 409)
                        self.assertEqual(response.json()["error"]["code"], "MODEL_NOT_AVAILABLE")
            self.assertEqual(client.get("/jobs").json(), {"jobs": []})

    def test_validation_errors_are_structured(self):
        invalid_values = [
            {}, {"model": "local-image", "prompt": " "},
            {"model": "local-image", "prompt": "x", "width": 513},
            {"model": "local-image", "prompt": "x", "width": 8192},
            {"model": "local-image", "prompt": "x", "seed": -1},
            {"model": "local-image", "prompt": "x", "seed": True},
            {"model": "local-image", "prompt": "x", "duration": 31},
            {"model": "local-image", "prompt": "x", "duration": True},
            {"model": "local-image", "prompt": "x", "aspect_ratio": "wide"},
            {"model": "local-image", "prompt": "x", "api_key": "should-not-be-used"},
        ]
        with self.client(self.application()) as client:
            for payload in invalid_values:
                with self.subTest(payload=payload):
                    response = client.post("/generate/image", json=payload)
                    self.assertEqual(response.status_code, 422)
                    self.assertEqual(response.json()["error"]["code"], "VALIDATION_ERROR")
                    self.assertTrue(response.json()["error"]["details"])

    def test_remote_and_traversing_media_references_rejected(self):
        bad_urls = ["https://example.com/image.png", "file:///C:/secret.png", "blob:http://localhost/x", f"/outputs/{uuid4()}/../secret.png", f"/outputs/{uuid4()}/bad..png"]
        with self.client(self.application()) as client:
            for reference in bad_urls:
                with self.subTest(reference=reference):
                    response = client.post("/generate/image", json={"model": "local-image", "prompt": "x", "image_url": reference})
                    self.assertEqual(response.status_code, 422)
            response = client.post("/generate/image", json={"model": "local-image", "prompt": "x", "image_url": f"/outputs/{uuid4()}/reference.png"})
            self.assertEqual(response.status_code, 409)

    def test_restricted_cors_and_blocked_foreign_writes(self):
        with self.client(self.application()) as client:
            for origin in ("http://localhost:3000", "http://127.0.0.1:3000", "http://localhost:5173", "http://127.0.0.1:5173"):
                response = client.options("/generate/image", headers={"Origin": origin, "Access-Control-Request-Method": "POST", "Access-Control-Request-Headers": "content-type"})
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.headers["access-control-allow-origin"], origin)
            foreign = "https://malicious.example"
            self.assertNotIn("access-control-allow-origin", client.get("/health", headers={"Origin": foreign}).headers)
            response = client.post("/generate/image", headers={"Origin": foreign}, json={"model": "local-image", "prompt": "x"})
            self.assertEqual(response.status_code, 403)
            self.assertEqual(response.json()["error"]["code"], "ORIGIN_NOT_ALLOWED")
            response = client.post("/uploads", headers={"Sec-Fetch-Site": "cross-site"})
            self.assertEqual(response.status_code, 403)

    def test_dns_rebinding_host_rejected(self):
        with self.client(self.application()) as client:
            response = client.get("/health", headers={"Host": "malicious.example:8000"})
            self.assertEqual(response.status_code, 403)
            self.assertEqual(response.json()["error"]["code"], "HOST_NOT_ALLOWED")

    def test_non_loopback_cors_configuration_rejected(self):
        for origin in ("*", "http://example.com:3000", "http://localhost:3000/path", "http://user@localhost:3000"):
            with self.subTest(origin=origin), self.assertRaises(ValueError):
                Settings(data_dir=self.data_dir, allowed_origins=(origin,))

    def test_request_body_is_bounded(self):
        with self.client(self.application(max_request_bytes=1024)) as client:
            response = client.post("/generate/image", json={"model": "local-image", "prompt": "x" * 2000})
            self.assertEqual(response.status_code, 413)
            self.assertEqual(response.json()["error"]["code"], "REQUEST_TOO_LARGE")

    def test_job_lifecycle_and_output_retrieval_with_isolated_worker(self):
        with self.client(self.application(IsolatedTransportWorker(delay=0.1))) as client:
            job_id = self.submit(client)
            running = self.wait_for(client, job_id, ("running",))
            self.assertIsNone(running["result"])
            job = self.wait_for(client, job_id)
            self.assertEqual(job["status"], "completed")
            self.assertTrue(job["result"]["metadata"]["test_only"])
            self.assertFalse(job["result"]["metadata"]["inference_performed"])
            output = client.get(job["result"]["outputs"][0]["url"])
            self.assertEqual(output.status_code, 200)
            self.assertEqual(output.content, TRANSPORT_FIXTURE)
            self.assertEqual(output.headers["content-type"], "image/png")
            self.assertEqual(output.headers["x-content-type-options"], "nosniff")
            self.assertEqual(client.get("/jobs").json()["jobs"][0]["id"], job_id)

    def test_completed_history_and_assets_survive_restart(self):
        with self.client(self.application(IsolatedTransportWorker())) as client:
            job_id = self.submit(client)
            output_url = self.wait_for(client, job_id)["result"]["outputs"][0]["url"]
        with self.client(self.application()) as restarted:
            self.assertFalse(restarted.get("/health").json()["inference_ready"])
            self.assertEqual(restarted.get(f"/jobs/{job_id}").json()["status"], "completed")
            self.assertEqual(restarted.get(output_url).content, TRANSPORT_FIXTURE)

    def test_interrupted_persisted_jobs_are_failed_on_startup(self):
        store = JobStore(self.data_dir)
        store.initialize()
        ids = []
        for state in ("pending", "running"):
            job_id = str(uuid4())
            ids.append(job_id)
            now = utc_now()
            store.insert(Job(id=job_id, status=state, type="image", model="test", prompt="persistence test", parameters={}, created_at=now, updated_at=now))
        with self.client(self.application()) as client:
            for job_id in ids:
                job = client.get(f"/jobs/{job_id}").json()
                self.assertEqual(job["status"], "failed")
                self.assertEqual(job["error"]["code"], "JOB_INTERRUPTED")

    def test_worker_failure_is_persisted_without_leaking_exception(self):
        with self.assertLogs("local_studio.jobs", level="ERROR"), self.client(self.application(IsolatedTransportWorker(failure=True))) as client:
            job = self.wait_for(client, self.submit(client))
            self.assertEqual(job["status"], "failed")
            self.assertEqual(job["error"]["code"], "WORKER_FAILED")
            self.assertNotIn("isolated transport fixture failure", job["error"]["message"])
            self.assertIsNone(job["result"])

    def test_timeout_cancels_cooperative_worker_and_persists_failure(self):
        worker = IsolatedTransportWorker(delay=2)
        with self.client(self.application(worker, job_timeout_seconds=0.02)) as client:
            job = self.wait_for(client, self.submit(client))
            self.assertEqual(job["status"], "failed")
            self.assertEqual(job["error"]["code"], "JOB_TIMEOUT")
            self.assertTrue(worker.cancelled)
            self.assertFalse((self.data_dir / "outputs" / job["id"] / "transport-fixture.png").exists())

    def test_queue_has_a_hard_bound(self):
        with self.client(self.application(IsolatedTransportWorker(delay=0.3), max_pending_jobs=1)) as client:
            self.submit(client)
            response = client.post("/generate/image", json={"model": "isolated-transport-fixture", "prompt": "second test"})
            self.assertEqual(response.status_code, 429)
            self.assertEqual(response.json()["error"]["code"], "JOB_QUEUE_FULL")
            self.assertEqual(len(client.get("/jobs").json()["jobs"]), 1)

    def test_shutdown_cancels_worker_and_marks_job_interrupted(self):
        worker = IsolatedTransportWorker(delay=2)
        with self.client(self.application(worker)) as client:
            job_id = self.submit(client)
            self.wait_for(client, job_id, ("running",))
        self.assertTrue(worker.cancelled)
        with self.client(self.application()) as restarted:
            job = restarted.get(f"/jobs/{job_id}").json()
            self.assertEqual(job["status"], "failed")
            self.assertEqual(job["error"]["code"], "JOB_INTERRUPTED")

    def test_unregistered_assets_and_traversal_cannot_be_served(self):
        with self.client(self.application(IsolatedTransportWorker())) as client:
            job_id = self.submit(client)
            self.wait_for(client, job_id)
            for filename in ("unregistered.png", "missing.png", "bad..png", "C:secret.png", "%2e%2e%2fsecret.png"):
                with self.subTest(filename=filename):
                    response = client.get(f"/outputs/{job_id}/{filename}")
                    self.assertEqual(response.status_code, 404)
            self.assertEqual(client.get(f"/outputs/{uuid4()}/transport-fixture.png").status_code, 404)

    def test_unsafe_worker_output_cannot_complete_a_job(self):
        with self.assertLogs("local_studio.jobs", level="ERROR"), self.client(self.application(IsolatedTransportWorker(unsafe=True))) as client:
            job = self.wait_for(client, self.submit(client))
            self.assertEqual(job["status"], "failed")
            self.assertEqual(job["error"]["code"], "WORKER_FAILED")
            self.assertIsNone(job["result"])

    def test_output_file_size_limit_is_enforced_before_completion(self):
        with self.assertLogs("local_studio.jobs", level="ERROR"), self.client(self.application(IsolatedTransportWorker(), max_output_bytes=1)) as client:
            job = self.wait_for(client, self.submit(client))
            self.assertEqual(job["status"], "failed")
            self.assertIsNone(job["result"])
            self.assertEqual(client.get(f"/outputs/{job['id']}/transport-fixture.png").status_code, 404)

    def test_output_names_match_frontend_proxy_allowlist(self):
        with self.assertLogs("local_studio.jobs", level="ERROR"), self.client(self.application(IsolatedTransportWorker(filename="multiple.dots.png"))) as client:
            job = self.wait_for(client, self.submit(client))
            self.assertEqual(job["status"], "failed")
            self.assertIsNone(job["result"])
            self.assertEqual(client.get(f"/outputs/{job['id']}/multiple.dots.png").status_code, 404)

    def test_output_directory_link_cannot_expose_another_directory(self):
        with self.client(self.application(IsolatedTransportWorker())) as client:
            job_id = self.submit(client)
            job = self.wait_for(client, job_id)
            output_url = job["result"]["outputs"][0]["url"]
            directory = self.data_dir / "outputs" / job_id
            moved = self.data_dir / "transport-original"
            directory.rename(moved)
            try:
                directory.symlink_to(moved, target_is_directory=True)
            except OSError:
                # Windows often requires Developer Mode/admin rights for symlinks.
                # Restore test storage and test the same escape guard via resolution.
                moved.rename(directory)
                from unittest.mock import patch
                original_resolve = Path.resolve

                def escaped_resolve(path, *args, **kwargs):
                    if path == directory / "transport-fixture.png":
                        return self.data_dir / "outside-storage.png"
                    return original_resolve(path, *args, **kwargs)

                with patch.object(Path, "resolve", escaped_resolve):
                    self.assertEqual(client.get(output_url).status_code, 404)
            else:
                self.assertEqual(client.get(output_url).status_code, 404)

    def test_missing_jobs_invalid_ids_and_pagination(self):
        with self.client(self.application()) as client:
            self.assertEqual(client.get(f"/jobs/{uuid4()}").json()["error"]["code"], "JOB_NOT_FOUND")
            self.assertEqual(client.get("/jobs/not-a-uuid").json()["error"]["code"], "VALIDATION_ERROR")
            self.assertEqual(client.get("/jobs?limit=999").status_code, 422)
            self.assertEqual(client.get("/jobs?offset=-1").status_code, 422)

    def test_uploads_explicitly_unavailable_and_not_saved(self):
        with self.client(self.application()) as client:
            response = client.post("/uploads", content=b"test-only media", headers={"Content-Type": "application/octet-stream"})
            self.assertEqual(response.status_code, 501)
            self.assertEqual(response.json()["error"]["code"], "UPLOAD_NOT_AVAILABLE")
            self.assertFalse((self.data_dir / "uploads").exists())

    def test_available_registry_entry_requires_an_actual_worker(self):
        with self.assertRaises(ValueError):
            ModelRegistry((Registration(ModelInfo(id="no-worker", name="Invalid entry", type="image", configured=True, available=True, reason="test")),))


if __name__ == "__main__":
    unittest.main()
