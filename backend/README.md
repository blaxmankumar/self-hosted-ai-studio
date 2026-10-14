# Local backend foundation

The default API has **no configured model and no inference**. Its image, video
and lip-sync slots are unavailable. A healthy API connection does not mean a
model is ready. The opt-in HTTP GPU adapter contacts only an explicitly
configured worker; no endpoint downloads weights or provisions resources.

See [GPU worker integration](../docs/GPU_WORKER_INTEGRATION.md) for the Kaggle
assessment, exact remote contract and steps to enable a real worker inside the
existing Image Studio. A configured URL alone never marks a model available.

From the project root in Windows PowerShell:

```powershell
.\backend\setup.cmd
.\backend\start.cmd
```

These command scripts do not require changing PowerShell execution policy. Setup
creates `backend/.venv`, installs the small pinned API/test dependencies, and
copies `.env.example` to `.env` only if `.env` does not already exist. Start binds
to `127.0.0.1:8000`, disables proxy-header trust and uses one process. Direct
equivalents after setup:

```powershell
.\backend\.venv\Scripts\python.exe -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000 --workers 1 --no-proxy-headers
.\backend\.venv\Scripts\python.exe -m unittest discover -s backend/tests -v
Invoke-RestMethod http://127.0.0.1:8000/health
Invoke-RestMethod http://127.0.0.1:8000/models
```

Python 3.13 is tested for this API layer. Future model runtimes may need a
separate compatible Python/PyTorch environment after hardware review. Setup
installs no GPU, model, cloud, multipart, or paid API package. HTTPX is the
worker transport and Pillow validates returned image bytes; both are pinned.

Configuration is read from `backend/.env`; process environment values override
the file. Relative `LOCAL_STUDIO_DATA_DIR` paths resolve beneath `backend/`.
Only exact loopback frontend origins are accepted (Next.js port 3000 and Vite
port 5173 by default). Foreign browser writes and non-loopback Host headers are
rejected, including cross-site writes without an Origin. CLI and the local
Next.js proxy can call without an Origin header. Local services and other users
on this computer are trusted; this foundation is not a shared-user deployment.

## HTTP contract

`GET /health` returns status, service, version, `inference_ready`, and
`available_models`. The production defaults are `false` and `0` respectively.
`GET /models` returns `{models:[...]}`. Each entry has `id`, `name`, `type`,
`configured`, `available`, `reason`, `capabilities` and input choices.
Only configured, available entries can be submitted. Managed worker readiness
is checked live; concurrent catalog/health reads share a one-second probe.
Submission rechecks the selected worker and validates its supported parameters.

`POST /generate/image`, `/generate/video` and `/generate/lipsync` accept JSON:

| Field | Validation |
| --- | --- |
| `model` | Required identifier, at most 128 characters |
| `prompt` | Required nonblank for image/video; optional for lip sync; at most 8000 characters |
| `negative_prompt` | Optional, at most 8000 characters |
| `aspect_ratio` | Numeric ratio such as `1:1`, `16:9`; defaults to `1:1` |
| `resolution`, `quality` | Optional labels, at most 32 characters |
| `width`, `height` | Integers 64–2048, multiples of 8; default 512 |
| `seed` | Optional integer 0–4294967295 |
| `duration` | Optional seconds, greater than 0 and at most 30 |
| `image_url`, `audio_url`, `video_url` | Optional local `/outputs/{UUID}/{safe_filename}` or `/uploads/{UUID}/{safe_filename}` reference |

Unsupported extra fields are rejected. These bounds validate API requests; they
are not GPU feasibility guarantees. Remote media URLs, blobs, file URLs and
traversing paths are rejected. A future adapter must additionally validate its
supported resolutions/options and that referenced input assets exist.

With no ready worker, generation returns HTTP 409:

```json
{"error":{"code":"MODEL_NOT_AVAILABLE","message":"... No inference was run."}}
```

A configured ready worker receives a 202 job: `id`, `status`, `type`, `model`,
`prompt`, `parameters`, `created_at`, `updated_at`, `progress`, `result`, `error`.
`GET /jobs/{UUID}` retrieves it; `GET /jobs?limit=50&offset=0` returns
`{jobs:[...]}` newest first (limit maximum 200). Job states are pending, running,
completed and failed. Progress is null when unknown or a worker-reported
percentage; completion reaches 100 after local validation. Results have `outputs:[{url,media_type}]` and
`metadata`. Failed jobs have `error:{code,message}` and no result. HTTP errors
use `{error:{code,message,details?}}`; request validation returns HTTP 422.

`GET /outputs/{UUID}/{filename}` serves only listed assets belonging to a
completed job. Names, extension/MIME consistency, file size, resolved paths,
symlinks and Windows junctions are checked. Supported outputs are PNG, JPEG,
WebP and MP4. Output stems contain only ASCII letters, digits, underscores and
hyphens, with a single lowercase extension and at most 128 total characters,
matching the frontend proxy. Arbitrary filesystem paths are never accepted.
`POST /uploads` returns HTTP 501 `UPLOAD_NOT_AVAILABLE` and saves no file.
Validated uploads are intentionally deferred to the later model/media phase.

Local job records live in `backend/data/jobs.sqlite3`; output assets live in
`backend/data/outputs/{job UUID}/`. SQLite writes are atomic. Jobs left pending
or running after restart become failed with `JOB_INTERRUPTED`. History is not
automatically deleted. The local queue defaults to 8 active/waiting jobs and
one running worker; the 300-second deadline includes queue waiting. JSON requests
are capped at 64 KiB and individual outputs at 100 MiB by default.

## Future worker boundary and test limits

`workers.py` defines the `Worker` protocol, `WorkerResult`, and `ModelRegistry`.
The app factory accepts an explicitly injected registry. `remote_worker.py`
implements an optional HTTP v1 adapter. Set its URL/model/server-side token in
`backend/.env` only after choosing a permitted GPU host and implementing its
worker contract. The first adapter accepts square 512 x 512 text-to-image only.
There is no flag, route or import discovery that enables a dummy adapter.
Adapters must report availability truthfully and write genuine artifacts only
inside their assigned output directory. Declared mocks or no inference,
arbitrary output URLs, redirects, invalid image bytes and mismatched dimensions
fail. Model provenance still depends on a trusted real worker.

Workers must be cooperatively asynchronous and propagate cancellation. A future
GPU/subprocess service must stop its underlying inference process on timeout or
shutdown; cancelling an `asyncio.to_thread` wrapper alone is insufficient.
The HTTP adapter attempts bounded cancellation after errors or local
cancellation. It cannot guarantee remote termination when the network or worker
fails; check the worker directly if cancellation is not acknowledged. It never
automatically resubmits a disconnected POST.
The current queue is single-process; run one Uvicorn worker against each data
directory. A shared multiprocess/distributed queue requires a later worker
service. Completed outputs and job history survive restarts, but no resumable
GPU computation is claimed.

Tests inject a transport-only worker defined **only in the test module**, with a
one-pixel PNG fixture and explicit `inference_performed:false` metadata. They
verify lifecycle, persistence, error handling, queue bounds, cancellation and
safe retrieval. They are not evidence of successful AI generation. Remote tests
also inject transport fixtures only inside tests; successful declarations
emulate the required contract and do not prove AI inference. The default app
remains unable to generate or upload media until a genuine worker is ready.

Pinned versions were checked against the project releases on
[PyPI FastAPI](https://pypi.org/project/fastapi/),
[PyPI Uvicorn](https://pypi.org/project/uvicorn/) and
[PyPI Pydantic](https://pypi.org/project/pydantic/).
