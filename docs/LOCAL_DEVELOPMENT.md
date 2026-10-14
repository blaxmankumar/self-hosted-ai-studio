# Local foundation

The existing studios connect to a local backend without browser API keys.
The backend includes an opt-in HTTP GPU worker adapter. With the worker URL
blank, no AI model is installed or enabled. Empty model selectors and disabled
generation are intentional; `/generate/*` returns `MODEL_NOT_AVAILABLE`.
See [GPU worker integration](GPU_WORKER_INTEGRATION.md) for the remote protocol,
Kaggle assessment and exact real-image activation steps. No generated example
is used as inference evidence.

## Run on Windows PowerShell

Run these commands from the project folder. Neither virtual-environment
activation nor a PowerShell execution-policy change is required.

First-time setup:

```powershell
Set-Location 'C:\Users\MSI\Open-Higgsfield-AI'
npm.cmd ci --ignore-scripts --cache .cache/npm
python -m venv backend/.venv
& .\backend\.venv\Scripts\python.exe -m pip install -r backend/requirements-dev.txt -c backend/requirements-lock.txt
```

Backend, in terminal 1:

```powershell
Set-Location 'C:\Users\MSI\Open-Higgsfield-AI'
& .\backend\.venv\Scripts\python.exe -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000 --workers 1 --no-proxy-headers
```

Frontend, in terminal 2:

```powershell
Set-Location 'C:\Users\MSI\Open-Higgsfield-AI'
npm.cmd run dev
```

Open `http://127.0.0.1:3000/studio`. The connection indicator should say
the backend is connected, with zero available models. Settings lists model
availability and reasons. Use Ctrl+C in each terminal to stop the servers.

Optional root `.env.local` configuration is shown in `.env.example`:
`LOCAL_BACKEND_URL` defaults to `http://127.0.0.1:8000` and accepts only HTTP
loopback origins. `LOCAL_BACKEND_TIMEOUT_MS` defaults to 10000. These values
stay on the Next.js server; the browser calls only `/api/local`.
See `backend/.env.example` for backend settings. Restart servers after
configuration changes.

## Reproducible checks

```powershell
Set-Location 'C:\Users\MSI\Open-Higgsfield-AI'
npm.cmd test
& .\backend\.venv\Scripts\python.exe -m unittest discover -s backend/tests -v
npm.cmd run build
npm.cmd run build:studio
node scripts/check-studio-render.cjs
npm.cmd run vite:build
Invoke-RestMethod 'http://127.0.0.1:8000/health'
Invoke-RestMethod 'http://127.0.0.1:3000/api/local/health'
Invoke-RestMethod 'http://127.0.0.1:3000/api/local/models'
Invoke-RestMethod 'http://127.0.0.1:3000/api/local/jobs'
curl.exe -i -X POST 'http://127.0.0.1:3000/api/local/generate/image' -H 'Content-Type: application/json' --data-binary '{"model":"sd15-local","prompt":"A lighthouse at dawn"}'
npm.cmd audit --json --cache .cache/npm
node scripts/smoke-local.mjs
```

The generation check should return HTTP 409 and `MODEL_NOT_AVAILABLE`.
Use a JSON file with `curl.exe --data-binary '@request.json'` if your Windows
curl/PowerShell combination alters argument quotes. Backend API docs are
available as JSON at `http://127.0.0.1:8000/openapi.json`. CDN-backed interactive
docs are disabled so the backend does not fetch third-party scripts.

## Data and safeguards

- Browser requests remain on the frontend origin. The Next.js proxy allows
  only documented endpoints, validates request sizes and origins, strips
  credential headers, rejects redirects and times out unavailable backends.
- Model lists come from backend configuration **and** worker availability;
  catalog candidates are not selectable models.
- Known old Muapi secret keys are removed from the current browser origin.
  Old histories/uploads are preserved in storage but not rendered or polled.
  Other browser profiles, ports and origins have separate storage; they are
  cleaned when the updated application is opened there.
- Outputs and jobs persist under ignored `backend/data/`. Safe output routes
  serve only completed job artifacts. The worker must return actual local
  files; completion without a file is an error.
- Uploads return `UPLOAD_NOT_AVAILABLE` and are disabled in the UI. Prompt
  payloads cannot contain arbitrary remote media URLs.
- Development bindings default to 127.0.0.1. CORS is restricted to explicitly
  configured loopback frontend origins. There is no multi-user authentication
  in this local foundation.
- Vite development uses `http://127.0.0.1:5173` and a fixed local proxy.
  Packaged Electron has no backend proxy and clearly reports unavailability.

## Next task

Obtain an existing, authorized GPU host whose terms permit inference serving.
Run a genuine SD 1.5 worker implementing the documented HTTP v1 contract, set
its URL/model/server-side token in `backend/.env`, and restart the backend.
When `/models` reports `remote-image` configured and available, use the existing
Image Studio to test two distinct prompts and verify preview, history, download
and failure behavior. The first adapter supports square 512 x 512 text-to-image.
No GPU service is provisioned here; paid resources require the user's approval.
Video, lip sync, character conditioning and validated uploads remain future
integrations. The local API still binds only to loopback. No notebook service,
public tunnel, paid API, Muapi or AWS integration is added.
