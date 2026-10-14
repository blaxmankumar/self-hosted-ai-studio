# GPU worker integration for the existing Studio

Assessment date: **14 October 2026 (Asia/Calcutta)**. This continues the existing
Next.js/FastAPI project. It does not create a separate image generator or a
Kaggle notebook.

## Compatibility and the existing application

The active frontend is Next.js: `app/studio/page.js` renders
`components/StandaloneShell.js` and the React components in
`packages/studio/src/components/`. The Image Studio already has prompt controls,
generation state, history, preview and downloads. Its local client submits jobs
through the same-origin `/api/local` proxy; FastAPI owns `/models`, `/generate/*`,
`/jobs` and `/outputs`. The worker belongs behind this API boundary, so the
browser never needs a GPU provider URL or worker credential.

The local backend already has a `Worker` protocol, `WorkerResult`, a model
registry, a bounded asynchronous job manager, SQLite job history and safe output
serving. These are the integration points. Video, Lip Sync and Cinema remain in
the same application. Their unavailable models and disabled uploads reflect
missing integrations, rather than being removed features.

The user's successful Stable Diffusion 1.5 test on Kaggle's two Tesla T4 GPUs is
evidence, supplied by the user, that their tested notebook runtime can perform
image inference. It does not establish an accessible or permitted API endpoint,
an always-on worker, or successful inference inside this Studio. No notebook
execution or new model inference was performed for this assessment.

The earlier [local compatibility report](PHASE4_TRIAL_REPORT.md) records 4 GiB
VRAM, driver 462.21, Python 3.13 and insufficient available system RAM at the
time of its checks. Those are historical measurements, not a fresh hardware
test. A remote worker keeps PyTorch, CUDA and model weights out of this small
FastAPI environment and out of the user's memory-constrained computer. The GPU
host must independently use a compatible model runtime; the HTTP adapter does
not make an incompatible host compatible. No driver, pagefile, model weights or
GPU package installation is included here.

## Kaggle: official support, rules and the decision

### What the official sources establish

- Kaggle's notebook documentation describes a reproducible notebook environment,
  limited GPU availability with possible queues, a 12-hour CPU/GPU session limit,
  idle termination, and session-local scratch storage. The documented technical
  specifications include a T4 x2 configuration. GPU quotas and actual
  availability must be checked in the user's account; this integration does not
  assume a fixed weekly allowance. [Kaggle notebook documentation](https://www.kaggle.com/docs/notebooks).
- The same documentation includes an **experimental Kaggle Jupyter Server**
  connection for VS Code/Colab notebook editors and the Jupyter `/tree` interface.
  This is an officially documented external notebook connection, so a blanket
  assertion that every remote connection is forbidden would be inaccurate. The
  feature is not documented as hosting an arbitrary FastAPI inference service.
  [Kaggle notebook documentation](https://www.kaggle.com/docs/notebooks).
- Kaggle's official CLI supports running/updating notebooks and downloading
  their code/output. This provides a batch notebook workflow. It does not
  document an arbitrary notebook-hosted inference endpoint for this Studio.
  [Official Kaggle CLI](https://github.com/Kaggle/kaggle-cli).
- The Terms limit ordinary use to the user's personal/internal/noncommercial
  purposes, restrict use for third parties, and require compliance with the AUP.
  This does not by itself prove that this user's personal ML notebook experiment
  violates the rules. [Kaggle Terms of Use](https://www.kaggle.com/terms).
- The AUP, with an active version dated 22 June 2025 when checked, prohibits
  interfering with or circumventing services and resource abuse, with examples
  including server farming, malicious circumvention/obfuscation tools, and
  activity unrelated to ML/data science. It does not explicitly classify every
  personal inference endpoint as server farming. [Kaggle Acceptable Use Policy](https://www.kaggle.com/aup).

### Technical feasibility and policy interpretation

**Technical inference:** running SD 1.5 in a notebook and connecting a notebook
editor can work, as the user and official documentation demonstrate. Neither
establishes a supported network route to an arbitrary inference server. The
notebook API's run/status/output pattern could support batch experimentation;
it has different startup, session, output and latency semantics from a ready GPU
worker. A session cap, idle termination and allocation queues also make a free
notebook unsuitable for a reliable continuously available inference endpoint.

**Policy interpretation:** circumventing quotas, idle limits or networking
restrictions conflicts with the AUP. Whether a particular nonpublic personal ML
workflow is permitted needs to be evaluated against Kaggle's actual support and
rules. The sources reviewed do not supply affirmative authorization for turning
the free notebook into this Studio's hosted inference API. Do not equate example
notebooks or unofficial tutorials with permission. Kaggle support is the right
place for a written clarification if a future supported workflow is desired.

**Decision for this project:** no Kaggle inference-hosting adapter is enabled.
Kaggle remains a useful model experiment, not the selected API host. No public
tunnels, notebook service exposure, keepalive tricks, quota bypasses, polling
agents that repurpose notebooks into servers, or alternate notebook APIs are
implemented. The project instead prepares an explicit worker contract for a
permitted GPU host. This is a compatibility/support decision with policy risk;
it is not a claim that Kaggle bans all inference or all remote Jupyter use.

## Permitted GPU host and first real-image gate

Use a GPU machine the user already owns or is explicitly authorized to use, or
a service whose terms and supplied entitlement explicitly permit inference
serving. The GPU worker must be reachable through the host's supported networking
and protected authentication. No provider account, paid API, GPU rental or cloud
resource has been selected or provisioned. Muapi and AWS are outside this work.
There is no verified free always-on GPU endpoint supplied with the repository.

## Adapter configuration

The default worker URL is empty and the `remote-image` entry stays unavailable.
Configuration belongs in `backend/.env` or the FastAPI process environment,
never a `NEXT_PUBLIC_*` variable or browser storage:

```dotenv
# Fill these only after choosing an authorized GPU host and a genuine worker.
LOCAL_STUDIO_REMOTE_WORKER_URL=
LOCAL_STUDIO_REMOTE_WORKER_TOKEN=
LOCAL_STUDIO_REMOTE_WORKER_MODEL=stable-diffusion-v1-5
LOCAL_STUDIO_WORKER_REQUEST_TIMEOUT_SECONDS=5
LOCAL_STUDIO_WORKER_POLL_INTERVAL_SECONDS=1
```

The URL must be the worker's origin without a path, query, fragment or embedded
credentials. Off-loopback connections require HTTPS and a bearer token. HTTP is
accepted only on loopback for an operator-owned local worker. Model names are
worker aliases, not a trigger to download weights or provision a service. The
local selectable model id is `remote-image`; the default remote alias is
`stable-diffusion-v1-5` and can be changed to the alias actually served by the
worker. Readiness/JSON requests have a total deadline, configured from greater
than zero through five seconds; HTTP transport also uses that value for each
network operation during image transfers. The local job deadline in
`LOCAL_STUDIO_JOB_TIMEOUT_SECONDS` also includes queue waiting and bounds the
overall transfer/generation workflow. Catalog and health reads share readiness
for one second; each generation submission rechecks its selected worker.

The first integration supports **text-to-image at square 512 x 512 only**. It
does not advertise image editing, uploads, video or lip sync as available.
Existing worker/model interfaces allow later adapters and capabilities to be
added when their real runtimes and media workflows are implemented and tested.

## Provider-independent worker HTTP contract (version 1)

This is the contract for a separate GPU service; the repository supplies the
Studio-side adapter, **not a deployed GPU serving process**. A service with
different routes or schemas needs an adapter or a worker-side bridge on its
permitted host. Configuring an arbitrary model URL or a notebook editor URL is
insufficient.

All calls include `Authorization: Bearer <token>` when a token is configured.
The worker must authenticate them and enforce its own access and job ownership.
No browser CORS change or public notebook tunnel is needed for this contract.
Readiness and job responses must have `Content-Type: application/json` and be
at most 64 KiB. Version 1 uses strict scalar types and rejects unknown fields at
every JSON object level; for example, `protocol_version` must be the integer
`1`, not `true` or a string. Do not add arbitrary metadata or output URL fields.
The adapter requests `Accept-Encoding: identity`; readiness, job and image
responses must omit `Content-Encoding` or set it to `identity`. Compressed
JSON/image HTTP bodies are rejected so transfer byte limits remain meaningful.

| Method and route | Required behavior |
| --- | --- |
| `GET /v1/health` | Return protocol version 1 and ready models; readiness must mean weights and runtime are actually ready to infer. |
| `POST /v1/jobs` | Accept the configured model alias, image kind and supported parameters; return a remote job UUID and state. Enforce the `Idempotency-Key` contract. |
| `GET /v1/jobs/{UUID}` | Return pending/running/completed/failed, optional progress and a genuine result or failure. |
| `GET /v1/jobs/{UUID}/outputs/{filename}` | Return image bytes for that completed job; never redirect to an arbitrary result URL. |
| `DELETE /v1/jobs/{UUID}` | Stop the underlying GPU work and acknowledge with HTTP 200 or 204. |

The adapter treats any other cancellation status as an unacknowledged cancel
and does not read an acknowledgement response body.

Readiness example:

```json
{
  "protocol_version": 1,
  "models": [{
    "id": "stable-diffusion-v1-5",
    "type": "image",
    "ready": true,
    "capabilities": ["text-to-image"]
  }]
}
```

Job submission body:

```json
{
  "model": "stable-diffusion-v1-5",
  "kind": "image",
  "parameters": {
    "prompt": "A lighthouse above a calm sea at dawn",
    "negative_prompt": null,
    "width": 512,
    "height": 512,
    "seed": 123
  }
}
```

`Idempotency-Key` is the local job's UUID. Repeating this key at the worker must
identify the same submission rather than start duplicate inference. The adapter
does not retry job submission, since a disconnected POST may already have
started work. An accepted job response has `id` as a UUID, a supported `status`
and optional `progress`:

```json
{
  "id": "11111111-1111-4111-8111-111111111111",
  "status": "pending",
  "progress": null
}
```

Progress, when supplied, is a finite number from 0 through 100; strings and
booleans are invalid. Omitted progress is unknown (`null`). A completed job's
result must name the configured remote model and assert real inference:

```json
{
  "id": "11111111-1111-4111-8111-111111111111",
  "status": "completed",
  "progress": 100,
  "result": {
    "model": "stable-diffusion-v1-5",
    "inference_performed": true,
    "outputs": [{"filename": "image.png", "media_type": "image/png"}]
  }
}
```

Optional `mock` and `test_only` flags belong **inside `result`**, are booleans,
and default to false; a true flag rejects the result. `inference_performed`
must be the boolean true. A provenance assertion is a contract requirement,
not cryptographic proof of model provenance: only connect a worker whose actual
inference implementation is trusted and verified.
Malformed, unavailable or explicitly synthetic/test-only results fail the job.
Results contain one through eight outputs with unique filenames. Filenames are
at most 128 characters, use only ASCII letters, digits, underscores and hyphens
in the stem, and have one lowercase `.png`, `.jpg`, `.jpeg` or `.webp` extension.
The declared MIME type, HTTP `Content-Type`, extension and actual decoded format
must agree. Images are downloaded only from the configured worker and checked
as nonanimated PNG/JPEG/WebP with the expected 512 x 512 size. The per-file
download bound is `LOCAL_STUDIO_MAX_OUTPUT_BYTES` (100 MiB by default).
The backend saves validated bytes in its assigned local output directory and
returns local `/outputs/{local UUID}/{filename}` references to the Studio.
Worker-provided arbitrary URLs and metadata are not forwarded to the browser.
The remote job's completed state does not complete the local job: local progress
becomes unknown while downloading/validating, then reaches 100 only after the
validated result is saved. Worker credentials remain in the backend.

A failed job may include an `error` with a string `code` (at most 128 characters)
and string `message` (at most 8000 characters):

```json
{
  "id": "11111111-1111-4111-8111-111111111111",
  "status": "failed",
  "error": {"code": "INFERENCE_FAILED", "message": "Worker inference failed."}
}
```

Its remote error text is not displayed verbatim or saved as the local failure.
The local job uses a fixed, safe `WORKER_FAILED` code/message, directing the
operator to the GPU worker's own logs. Authentication, availability, protocol
and invalid output failures also use fixed local messages.

On local timeout or shutdown the adapter makes a bounded, best-effort cancel
request (at most two seconds). The GPU service must actually stop inference;
HTTP transport cannot guarantee remote cancellation if the network or worker
fails. In particular, an ambiguous disconnected submission might not yield a
remote UUID to cancel. The service should also bound its own inference lifetime
and retain its idempotency records. A transport timeout is never reported as a
successful image.

## Exact next step to enable Generate

1. Obtain access to an **already permitted GPU host** and run a genuine SD 1.5
   service there that implements the contract above, using a compatible runtime
   and appropriately licensed weights. Any later paid GPU provisioning requires
   explicit approval; no paid API integration or provisioning is included here.
2. Set its supported origin, bearer token and model alias in `backend/.env`.
   Restart the local FastAPI backend. Keep the Next.js frontend on
   `http://127.0.0.1:3000/studio`.
3. Verify `http://127.0.0.1:3000/api/local/models` reports `remote-image` as
   `configured: true` and `available: true`, and the local health endpoint reports
   `inference_ready: true`. A connected backend by itself is insufficient.
4. Select the remote image model in the existing Image Studio and submit a
   custom prompt at 1:1. Verify that the job completes and its genuine image
   appears in preview and history and can be downloaded. Repeat with a distinct
   second prompt, and verify the saved output files.

Before describing Generate as working for AI inference, the chosen worker must
load the actual SD 1.5 model, report it ready, accept a Studio request and return
genuine model-generated image bytes. Run two distinct custom prompts through
the existing Image Studio, observe each local job's progress/status, then verify
preview, history and download from the local output route. Record the model,
runtime, seed and generated files. Transport fixtures and readiness assertions
alone are not proof of inference; no fixture is a production fallback.
