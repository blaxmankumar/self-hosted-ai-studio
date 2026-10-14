# Existing Studio GPU worker implementation

Completed 14 October 2026 (Asia/Calcutta). This work extends the existing
Next.js/FastAPI project. Existing uncommitted work was preserved. No separate
Kaggle demo, notebook, inference service, tunnel or GPU resource was created.

## Repository inspection and compatibility

The active application is `app/studio/page.js` -> `StandaloneShell` -> the
React `packages/studio` workspace. Browser requests use `/api/local`; the
Next.js proxy connects only to the local FastAPI backend. Model choices come
from the backend registry. SQLite stores job history and `/outputs` serves
registered assets belonging to completed jobs. The separate Vite/Electron
frontend remains present and uses the existing local API.

The existing `Worker.generate` interface remains compatible. A new optional
`ManagedWorker` interface describes live readiness, request validation and
progress. `HttpGPUWorker` implements this lifecycle against a documented v1
HTTP contract. Provider names, CUDA, PyTorch and weights do not enter the
frontend or the local API runtime. The GPU serving process needs its own
compatible runtime on an authorized host.

The user's successful SD 1.5 test on two Kaggle Tesla T4 GPUs is user-supplied
evidence of notebook inference. It is not evidence that this Studio can access
a permitted, ready inference API. Earlier local hardware measurements remain
historical; this work does not install model runtimes or change drivers.

## What now works

- An opt-in worker adapter configured through `backend/.env`, with server-side
  bearer authentication, HTTPS outside loopback, and no browser-selected URLs.
- Live model readiness, shared catalog/health probes, a fresh readiness check
  before submission, and rejection of unsupported parameters before creating
  jobs. URL configuration alone never enables Generate.
- Asynchronous submission, polling, reported progress, bounded job deadlines,
  idempotency identifiers and best-effort remote cancellation. Failures are
  saved with safe messages and no successful result.
- Download of worker outputs onto local storage, with fixed job-specific paths,
  byte limits, decoded image validation, MIME/extension/dimension checks and
  rejection of declared mock or test results. Production supplies no fallback
  image. Provenance still relies on a trusted genuine inference service.
- Image Studio generation/status controls, restored history before generation,
  preview and checked downloads that preserve the image filename extension.
  The initial remote model advertises square 512 x 512 text-to-image only.
- The existing Video Studio, Lip Sync and Cinema Studio remain present for
  future model integrations. Validated uploads and their inference workers
  remain unavailable.

HTTPX 0.28.1 is now a runtime transport dependency; Pillow 12.3.0 is pinned for
image validation. Pillow was installed in the existing backend virtual
environment. Neither dependency installs an inference model or GPU runtime.

## Validation

| Check | Result |
| --- | --- |
| `python -m unittest discover -s backend/tests -v` using the backend venv | 41 passed, including 18 new remote-worker tests |
| `npm.cmd test` | 22 passed |
| `npm.cmd run build` | Next.js production build passed |
| `npm.cmd run build:studio` | React workspace build passed |
| `node scripts/check-studio-render.cjs` | All four studios and restored safe image history rendered |
| `node scripts/smoke-local.mjs` | 16 checks passed against the local frontend and backend |
| Backend `pip check` | No broken requirements |
| `git diff --check` | Passed |

The worker tests inject `httpx.MockTransport` only inside tests. Their decoded
PNG fixtures and emulated inference declarations test the contract and byte
transport; they are not AI images or evidence of successful inference. No
fixture service or production test mode was enabled. Live smoke checks used
the unconfigured production app and never submitted to a configured model.

Existing Node module-type warnings and a Starlette TestClient deprecation
warning do not fail the checks. No dependency migration was added for these
preexisting warnings.

## What remains blocked

There is no configured GPU endpoint, deployed serving process or installed
model. Production health reports `inference_ready: false`; the remote model
reports `configured: false` and `available: false`. Generate is correctly
disabled, and direct generation attempts return `MODEL_NOT_AVAILABLE` without
creating jobs. Genuine image generation inside Studio has not been performed.

Kaggle's official notebook/editor/API documentation does not establish a
supported arbitrary inference-hosting endpoint. Its session lifecycle is also
unsuitable for reliable serving. The published rules prohibit circumvention
and resource abuse but do not justify claiming that every personal inference
endpoint is categorically banned. The project therefore does not use Kaggle as
an API host. The official sources and policy distinction are recorded in
[GPU worker integration](GPU_WORKER_INTEGRATION.md).

No free always-on GPU service has been verified or selected. No Muapi, paid API,
AWS integration or paid GPU provisioning was used. Remote cancellation cannot
guarantee termination when the worker/network fails, and a disconnected POST
may have started remote work before a job UUID was received. The service must
enforce idempotency and its own inference deadline.

## Exact next step for a real image

1. Use a GPU host already owned or explicitly authorized for inference serving.
   Run a genuine SD 1.5 service there implementing the v1 routes/schemas in
   [GPU_WORKER_INTEGRATION.md](GPU_WORKER_INTEGRATION.md). An arbitrary notebook
   or model URL does not implement this contract.
2. Set `LOCAL_STUDIO_REMOTE_WORKER_URL`, `LOCAL_STUDIO_REMOTE_WORKER_TOKEN` and
   `LOCAL_STUDIO_REMOTE_WORKER_MODEL` in `backend/.env`, using that worker's
   origin, credential and model alias. Restart FastAPI.
3. Check `http://127.0.0.1:3000/api/local/models` for `remote-image` with both
   `configured` and `available` true. In Studio, click Retry connection if the
   catalog predates the backend restart.
4. Select the remote image worker at 1:1 and click Generate. Verify two distinct
   prompts produce genuine images, persist in history, preview correctly and
   download from the local output route. Record the actual runtime/model and
   output files before reporting real inference as working.

Paid resource provisioning remains subject to the user's explicit approval.
