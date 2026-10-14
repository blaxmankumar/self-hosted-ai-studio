"""Remote-worker contract, persistence, and byte-transport tests only.

All HTTP requests use an explicitly injected httpx.MockTransport. The PNG below
is a programmatically constructed transport fixture and contains no AI output.
Successful response fixtures emulate a worker's required inference declaration
solely to test the contract; they do not constitute evidence of real inference.
No fixture is discoverable by the production registry or application settings.
"""

import asyncio
import io
import json
from pathlib import Path
import tempfile
import time
import unittest
from uuid import uuid4

import httpx
from fastapi.testclient import TestClient
from PIL import Image

from backend.app.config import Settings
from backend.app.errors import ApiError
from backend.app.main import create_app
from backend.app.remote_worker import HttpGPUWorker
from backend.app.schemas import ImageRequest, ModelInfo
from backend.app.workers import ModelRegistry, Registration, WorkerError, default_registry


def transport_png(size=(512, 512)):
    """Construct bytes for decoding/transport checks, never an AI image."""
    buffer = io.BytesIO()
    Image.new("RGB", size, color=(40, 70, 90)).save(buffer, format="PNG")
    return buffer.getvalue()


TRANSPORT_PNG = transport_png()
REMOTE_JOB_ID = str(uuid4())
MODEL_ID = "stable-diffusion-v1-5"
SECRET = "transport-test-token-never-real"


def healthy_models(**overrides):
    model = {"id": MODEL_ID, "type": "image", "ready": True, "capabilities": ["text-to-image"]}
    model.update(overrides)
    return {"protocol_version": 1, "models": [model]}


def pending_job():
    return {"id": REMOTE_JOB_ID, "status": "pending", "progress": None}


def completed_job(**result_overrides):
    result = {
        "model": MODEL_ID,
        "inference_performed": True,
        "outputs": [{"filename": "transport-fixture.png", "media_type": "image/png"}],
    }
    result.update(result_overrides)
    return {"id": REMOTE_JOB_ID, "status": "completed", "progress": 100, "result": result}


class RemoteWorkerSettingsTests(unittest.TestCase):
    def test_default_registry_keeps_all_features_unavailable_without_configuration(self):
        settings = Settings()
        self.assertEqual(settings.remote_worker_url, "")
        self.assertEqual(settings.remote_worker_token, "")
        self.assertEqual(settings.remote_worker_model, MODEL_ID)
        models = default_registry(settings).models()
        self.assertEqual({model.type for model in models}, {"image", "video", "lipsync"})
        self.assertIn("remote-image", {model.id for model in models})
        self.assertTrue(all(not model.available for model in models))

    def test_external_worker_requires_https_authentication_and_exact_origin(self):
        invalid_settings = [
            {"remote_worker_url": "http://gpu.example", "remote_worker_token": SECRET},
            {"remote_worker_url": "https://gpu.example"},
            {"remote_worker_url": "https://user:password@gpu.example", "remote_worker_token": SECRET},
            {"remote_worker_url": "https://gpu.example/api", "remote_worker_token": SECRET},
            {"remote_worker_url": "https://gpu.example?token=secret", "remote_worker_token": SECRET},
            {"remote_worker_url": "https://gpu.example#fragment", "remote_worker_token": SECRET},
            {"remote_worker_url": "ftp://gpu.example", "remote_worker_token": SECRET},
            {"remote_worker_url": "https://gpu.example:bad", "remote_worker_token": SECRET},
        ]
        for options in invalid_settings:
            with self.subTest(options=options), self.assertRaises(ValueError):
                Settings(**options)
        self.assertEqual(Settings(remote_worker_url="http://127.0.0.1:8080").remote_worker_url, "http://127.0.0.1:8080")
        self.assertEqual(Settings(remote_worker_url="https://gpu.example", remote_worker_token=SECRET).remote_worker_url, "https://gpu.example")


class RemoteWorkerTransportTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(prefix="remote-worker-transport-test-")
        self.data_dir = Path(self.directory.name)
        self.output_dir = self.data_dir / str(uuid4())
        self.output_dir.mkdir()
        self.settings = Settings(
            data_dir=self.data_dir,
            remote_worker_url="https://gpu.example",
            remote_worker_token=SECRET,
            worker_request_timeout_seconds=5,
            worker_poll_interval_seconds=0.01,
        )
        self.request = ImageRequest(model="remote-image", prompt="Transport contract test only", negative_prompt="fixture", seed=123)

    def tearDown(self):
        self.directory.cleanup()

    def worker(self, handler, **options):
        settings = Settings(**{**self.settings.__dict__, **options}) if options else self.settings
        return HttpGPUWorker(settings, transport=httpx.MockTransport(handler))

    def generation_handler(self, *, state=None, content=TRANSPORT_PNG, content_type="image/png", output_status=200):
        state = completed_job() if state is None else state
        requests = []

        def handler(request):
            requests.append(request)
            if request.url.path == "/v1/health":
                return httpx.Response(200, json=healthy_models())
            if request.method == "POST" and request.url.path == "/v1/jobs":
                return httpx.Response(202, json=pending_job())
            if request.method == "DELETE" and request.url.path == f"/v1/jobs/{REMOTE_JOB_ID}":
                return httpx.Response(204)
            if request.url.path == f"/v1/jobs/{REMOTE_JOB_ID}":
                return httpx.Response(200, json=state)
            if request.url.path == f"/v1/jobs/{REMOTE_JOB_ID}/outputs/transport-fixture.png":
                headers = {"Content-Type": content_type}
                if output_status == 302:
                    headers["Location"] = "https://untrusted.example/secret.png"
                return httpx.Response(output_status, content=content, headers=headers)
            raise AssertionError(f"Unexpected transport-only request: {request.method} {request.url.path}")

        return handler, requests

    async def test_availability_requires_matching_ready_text_to_image_model(self):
        documents = [
            (healthy_models(), True),
            ({"protocol_version": 1, "models": []}, False),
            (healthy_models(id="another-model"), False),
            (healthy_models(type="video"), False),
            (healthy_models(ready=False), False),
            (healthy_models(capabilities=["image-to-image"]), False),
            ({"protocol_version": 2, "models": healthy_models()["models"]}, False),
            ({"protocol_version": True, "models": healthy_models()["models"]}, False),
        ]
        for payload, available in documents:
            with self.subTest(payload=payload):
                worker = self.worker(lambda request: httpx.Response(200, json=payload))
                readiness = await worker.check_availability("image")
                self.assertEqual(readiness.available, available)
                self.assertTrue(readiness.reason)
        readiness = await self.worker(lambda request: httpx.Response(200, json=healthy_models())).check_availability("video")
        self.assertFalse(readiness.available)

    async def test_stalled_health_probe_has_total_deadline_and_cancels_transport_request(self):
        cancelled = asyncio.Event()

        async def stalled(request):
            try:
                await asyncio.Event().wait()
            finally:
                cancelled.set()

        worker = self.worker(stalled, worker_request_timeout_seconds=0.02)
        readiness = await asyncio.wait_for(worker.check_availability("image"), 1)
        self.assertFalse(readiness.available)
        self.assertTrue(cancelled.is_set())
        self.assertIn("deadline", readiness.reason)

    async def test_down_authentication_failure_and_bad_protocol_are_unavailable_without_secret_leaks(self):
        def disconnected(request):
            raise httpx.ConnectError(f"Transport test exception {SECRET}", request=request)

        handlers = [
            disconnected,
            lambda request: httpx.Response(401, text=SECRET),
            lambda request: httpx.Response(500, text=SECRET),
            lambda request: httpx.Response(200, text="not JSON " + SECRET),
            lambda request: httpx.Response(200, json={"protocol_version": True, "models": []}),
            lambda request: httpx.Response(302, headers={"Location": "https://untrusted.example/v1/health"}),
        ]
        for handler in handlers:
            with self.subTest(handler=handler):
                readiness = await self.worker(handler).check_availability("image")
                self.assertFalse(readiness.available)
                self.assertNotIn(SECRET, readiness.reason)

    async def test_registry_refresh_tracks_live_availability_instead_of_configured_url(self):
        ready = True

        def handler(request):
            return httpx.Response(200, json=healthy_models(ready=ready))

        worker = self.worker(handler)
        registry = ModelRegistry((Registration(ModelInfo(
            id="remote-image", name="Transport contract test worker", type="image", configured=True,
            available=False, reason="Not checked yet", capabilities=["text-to-image"],
        ), worker),))
        self.assertIsNone(registry.worker_for("remote-image", "image"))
        await registry.refresh()
        self.assertIs(registry.worker_for("remote-image", "image"), worker)
        ready = False
        await registry.refresh("remote-image")
        self.assertIsNone(registry.worker_for("remote-image", "image"))
        self.assertFalse(registry.models()[0].available)

    async def test_concurrent_catalog_probes_share_health_check_and_submission_rechecks_readiness(self):
        checks = 0
        first_probe_started = asyncio.Event()
        release_first_probe = asyncio.Event()

        async def handler(request):
            nonlocal checks
            self.assertEqual(request.url.path, "/v1/health")
            checks += 1
            if checks == 1:
                first_probe_started.set()
                await release_first_probe.wait()
            return httpx.Response(200, json=healthy_models(ready=checks == 1))

        worker = self.worker(handler)
        registry = ModelRegistry((Registration(ModelInfo(
            id="remote-image", name="Transport contract test worker", type="image", configured=True,
            available=False, reason="Not checked yet", capabilities=["text-to-image"],
        ), worker),))
        concurrent_probes = [asyncio.create_task(registry.refresh()) for _ in range(2)]
        await asyncio.wait_for(first_probe_started.wait(), 1)
        release_first_probe.set()
        await asyncio.gather(*concurrent_probes)
        self.assertEqual(checks, 1)
        self.assertIs(registry.worker_for("remote-image", "image"), worker)
        await registry.refresh("remote-image")
        self.assertEqual(checks, 2)
        self.assertIsNone(registry.worker_for("remote-image", "image"))

    async def test_generation_sends_bounded_model_parameters_reports_actual_progress_and_retrieves_bytes(self):
        states = iter([
            {"id": REMOTE_JOB_ID, "status": "running", "progress": 22},
            {"id": REMOTE_JOB_ID, "status": "running", "progress": 76},
            completed_job(),
        ])
        handler, requests = self.generation_handler()

        def progressing_handler(request):
            if request.method == "GET" and request.url.path == f"/v1/jobs/{REMOTE_JOB_ID}":
                requests.append(request)
                return httpx.Response(200, json=next(states))
            return handler(request)

        progress = []

        def record_progress(value):
            progress.append(value)

        result = await self.worker(progressing_handler).generate_with_progress("image", self.request, self.output_dir, record_progress)
        self.assertEqual((self.output_dir / "transport-fixture.png").read_bytes(), TRANSPORT_PNG)
        self.assertEqual(result.outputs[0].filename, "transport-fixture.png")
        self.assertEqual(result.outputs[0].media_type, "image/png")
        self.assertIn(22, progress)
        self.assertIn(76, progress)
        submitted = next(request for request in requests if request.method == "POST")
        self.assertEqual(submitted.headers["Idempotency-Key"], self.output_dir.name)
        self.assertEqual(json.loads(submitted.content), {
            "model": MODEL_ID, "kind": "image", "parameters": {
                "prompt": self.request.prompt, "negative_prompt": "fixture", "width": 512, "height": 512, "seed": 123,
            },
        })
        self.assertTrue(all(request.url.host == "gpu.example" for request in requests))
        self.assertTrue(all(request.headers["Authorization"] == f"Bearer {SECRET}" for request in requests))

    async def test_unsupported_input_is_rejected_before_remote_job_submission(self):
        requests = []
        worker = self.worker(lambda request: requests.append(request) or httpx.Response(200, json=healthy_models()))
        unsupported = [
            {"aspect_ratio": "16:9"}, {"width": 768}, {"height": 768},
            {"quality": "high"}, {"resolution": "1024"}, {"duration": 2.0},
            {"image_url": f"/outputs/{uuid4()}/input.png"},
            {"audio_url": f"/outputs/{uuid4()}/input.mp4"},
            {"video_url": f"/outputs/{uuid4()}/input.mp4"},
        ]
        for overrides in unsupported:
            with self.subTest(overrides=overrides), self.assertRaises(ApiError) as raised:
                worker.validate_request("image", self.request.model_copy(update=overrides))
            self.assertEqual(raised.exception.status_code, 422)
        self.assertEqual(requests, [])

    async def test_failure_malformed_state_and_unverified_provenance_never_save_an_output(self):
        states = [
            {"id": REMOTE_JOB_ID, "status": "failed", "progress": None, "error": {"code": "GPU_OOM", "message": SECRET}},
            {"id": str(uuid4()), "status": "completed", "result": completed_job()["result"]},
            {"id": REMOTE_JOB_ID, "status": "running", "progress": 101},
            {"id": REMOTE_JOB_ID, "status": "unknown", "progress": 0},
            completed_job(inference_performed=False),
            completed_job(inference_performed="true"),
            completed_job(test_only=True),
            completed_job(mock=True),
            completed_job(model="another-model"),
            completed_job(outputs=[{"filename": "../transport-fixture.png", "media_type": "image/png"}]),
            completed_job(outputs=[{"url": "https://untrusted.example/image.png", "media_type": "image/png"}]),
        ]
        for state in states:
            with self.subTest(state=state):
                handler, requests = self.generation_handler(state=state)
                with self.assertRaises(WorkerError) as raised:
                    await self.worker(handler).generate("image", self.request, self.output_dir)
                self.assertNotIn(SECRET, str(raised.exception))
                self.assertEqual(list(self.output_dir.iterdir()), [])
                self.assertFalse(any("/outputs/" in request.url.path for request in requests))

    async def test_invalid_image_wrong_dimensions_content_type_redirect_and_size_are_rejected(self):
        cases = [
            {"content": b"This is not an image"},
            {"content": TRANSPORT_PNG[:-20]},
            {"content": transport_png((256, 256))},
            {"content_type": "image/jpeg"},
            {"output_status": 302},
            {"max_output_bytes": 1},
        ]
        for options in cases:
            with self.subTest(options={key: value for key, value in options.items() if key != "content"}):
                options = dict(options)
                limit = options.pop("max_output_bytes", self.settings.max_output_bytes)
                handler, requests = self.generation_handler(**options)
                with self.assertRaises(WorkerError):
                    await self.worker(handler, max_output_bytes=limit).generate("image", self.request, self.output_dir)
                self.assertEqual(list(self.output_dir.iterdir()), [])
                self.assertTrue(all(request.url.host == "gpu.example" for request in requests))

    async def test_request_timeout_is_sanitized(self):
        def timeout(request):
            raise httpx.ReadTimeout(f"Timeout exception contains {SECRET}", request=request)

        with self.assertRaises(WorkerError) as raised:
            await self.worker(timeout).generate("image", self.request, self.output_dir)
        self.assertEqual(raised.exception.code, "WORKER_UNAVAILABLE")
        self.assertNotIn(SECRET, str(raised.exception))
        self.assertEqual(list(self.output_dir.iterdir()), [])

    async def test_cancelling_inference_sends_remote_delete_and_propagates_cancellation(self):
        started = asyncio.Event()
        cancelled = asyncio.Event()

        async def handler(request):
            if request.method == "POST":
                return httpx.Response(202, json=pending_job())
            if request.method == "DELETE":
                self.assertEqual(request.url.path, f"/v1/jobs/{REMOTE_JOB_ID}")
                cancelled.set()
                return httpx.Response(204)
            if request.url.path == "/v1/health":
                return httpx.Response(200, json=healthy_models())
            started.set()
            await asyncio.Event().wait()

        task = asyncio.create_task(self.worker(handler).generate("image", self.request, self.output_dir))
        await asyncio.wait_for(started.wait(), 2)
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await asyncio.wait_for(task, 2)
        self.assertTrue(cancelled.is_set())
        self.assertEqual(list(self.output_dir.iterdir()), [])


class RemoteWorkerLocalApiTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(prefix="remote-worker-local-api-test-")
        self.data_dir = Path(self.directory.name)
        self.settings = Settings(
            data_dir=self.data_dir, remote_worker_url="https://gpu.example", remote_worker_token=SECRET,
            worker_request_timeout_seconds=5, worker_poll_interval_seconds=0.01,
        )

    def tearDown(self):
        self.directory.cleanup()

    def application(self, handler):
        worker = HttpGPUWorker(self.settings, transport=httpx.MockTransport(handler))
        registry = ModelRegistry((Registration(ModelInfo(
            id="remote-image", name="Transport contract test worker", type="image", configured=True,
            available=False, reason="Not checked yet", capabilities=["text-to-image"],
        ), worker),))
        return create_app(self.settings, registry)

    def wait_for(self, client, job_id):
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            job = client.get(f"/jobs/{job_id}").json()
            if job["status"] in {"completed", "failed"}:
                return job
            time.sleep(0.01)
        self.fail("Transport-only job did not finish")

    def test_remote_contract_result_is_persisted_retrieved_and_listed_in_existing_job_api(self):
        def handler(request):
            if request.url.path == "/v1/health":
                return httpx.Response(200, json=healthy_models())
            if request.method == "POST":
                return httpx.Response(202, json=pending_job())
            if request.url.path == f"/v1/jobs/{REMOTE_JOB_ID}":
                return httpx.Response(200, json=completed_job())
            return httpx.Response(200, content=TRANSPORT_PNG, headers={"Content-Type": "image/png"})

        with TestClient(self.application(handler), base_url="http://127.0.0.1:8000") as client:
            models = client.get("/models").json()["models"]
            self.assertTrue(models[0]["available"])
            response = client.post("/generate/image", json={"model": "remote-image", "prompt": "Transport test only"})
            self.assertEqual(response.status_code, 202, response.text)
            self.assertIsNone(response.json()["result"])
            job_id = response.json()["id"]
            job = self.wait_for(client, job_id)
            self.assertEqual(job["status"], "completed", job)
            self.assertEqual(job["progress"], 100)
            output_url = job["result"]["outputs"][0]["url"]
            self.assertTrue(output_url.startswith(f"/outputs/{job_id}/"))
            output = client.get(output_url)
            self.assertEqual(output.status_code, 200)
            self.assertEqual(output.content, TRANSPORT_PNG)
            self.assertEqual(output.headers["content-type"], "image/png")
            self.assertEqual(client.get("/jobs").json()["jobs"][0]["id"], job_id)
            self.assertEqual(client.get(f"/outputs/{job_id}/unregistered.png").status_code, 404)

    def test_unavailable_remote_worker_blocks_job_creation(self):
        with TestClient(self.application(lambda request: httpx.Response(503)), base_url="http://127.0.0.1:8000") as client:
            self.assertFalse(client.get("/models").json()["models"][0]["available"])
            response = client.post("/generate/image", json={"model": "remote-image", "prompt": "Transport test only"})
            self.assertEqual(response.status_code, 409)
            self.assertEqual(response.json()["error"]["code"], "MODEL_NOT_AVAILABLE")
            self.assertEqual(client.get("/jobs").json(), {"jobs": []})

    def test_unsupported_request_is_rejected_without_persisting_or_submitting_remote_job(self):
        requests = []

        def handler(request):
            requests.append(request)
            self.assertEqual(request.url.path, "/v1/health")
            return httpx.Response(200, json=healthy_models())

        with TestClient(self.application(handler), base_url="http://127.0.0.1:8000") as client:
            response = client.post("/generate/image", json={"model": "remote-image", "prompt": "Transport test only", "width": 768})
            self.assertEqual(response.status_code, 422)
            self.assertEqual(response.json()["error"]["code"], "UNSUPPORTED_WORKER_PARAMETERS")
            self.assertEqual(client.get("/jobs").json(), {"jobs": []})
            self.assertTrue(all(request.method == "GET" for request in requests))

    def test_local_job_deadline_cancels_remote_inference_and_persists_timeout(self):
        self.settings = Settings(**{**self.settings.__dict__, "job_timeout_seconds": 0.1})
        cancellations = []

        def handler(request):
            if request.url.path == "/v1/health":
                return httpx.Response(200, json=healthy_models())
            if request.method == "POST":
                return httpx.Response(202, json=pending_job())
            if request.method == "DELETE":
                cancellations.append(request.url.path)
                return httpx.Response(204)
            return httpx.Response(200, json={"id": REMOTE_JOB_ID, "status": "running", "progress": 44})

        with TestClient(self.application(handler), base_url="http://127.0.0.1:8000") as client:
            response = client.post("/generate/image", json={"model": "remote-image", "prompt": "Transport test only"})
            self.assertEqual(response.status_code, 202, response.text)
            job_id = response.json()["id"]
            job = self.wait_for(client, job_id)
            self.assertEqual(job["status"], "failed", job)
            self.assertEqual(job["error"]["code"], "JOB_TIMEOUT")
            self.assertEqual(cancellations, [f"/v1/jobs/{REMOTE_JOB_ID}"])
            self.assertIsNone(job["result"])
            self.assertEqual(client.get(f"/outputs/{job_id}/transport-fixture.png").status_code, 404)

    def test_upstream_failure_is_persisted_as_safe_error_and_outputs_remain_inaccessible(self):
        def handler(request):
            if request.url.path == "/v1/health":
                return httpx.Response(200, json=healthy_models())
            if request.method == "POST":
                return httpx.Response(202, json=pending_job())
            if request.method == "DELETE":
                return httpx.Response(204)
            return httpx.Response(200, json={
                "id": REMOTE_JOB_ID, "status": "failed", "progress": None,
                "error": {"code": "GPU_OOM", "message": f"Do not expose {SECRET}"},
            })

        with TestClient(self.application(handler), base_url="http://127.0.0.1:8000") as client:
            response = client.post("/generate/image", json={"model": "remote-image", "prompt": "Transport test only"})
            self.assertEqual(response.status_code, 202, response.text)
            job_id = response.json()["id"]
            job = self.wait_for(client, job_id)
            self.assertEqual(job["status"], "failed")
            self.assertEqual(job["error"]["code"], "WORKER_FAILED")
            self.assertIsNone(job["result"])
            self.assertNotIn(SECRET, json.dumps(job["error"]))
            self.assertEqual(client.get(f"/outputs/{job_id}/transport-fixture.png").status_code, 404)


if __name__ == "__main__":
    unittest.main()
