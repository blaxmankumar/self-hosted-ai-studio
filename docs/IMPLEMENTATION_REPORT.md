# Local foundation implementation report

Completed on 13 October 2026 on branch
`feat/self-hosted-local-foundation`. Implemented Phases 1–3 and the minimum
frontend connection. Changes are local and uncommitted; nothing was pushed or
deployed. No source file was deleted, cloud resource created, GPU driver changed,
model weight downloaded or inference result fabricated.

## Result

Next.js calls an allowlisted local API route, which connects to FastAPI on
127.0.0.1:8000. The existing Image, Video, Lip Sync and Cinema React interfaces
are retained. API keys are unnecessary, known old keys are removed when the
updated browser origin opens, and only configured/available models enter
selectors. The API is healthy with **zero ready models**.

The legacy Vite frontend also has a local proxy, status and unavailable panels.
Both old provider clients are local compatibility exports. Legacy stored
histories remain intact but are not fetched or polled. Local histories and
outputs use separate storage keys and validated same-origin URLs. Electron
security restrictions are restored; packaged desktop connectivity is deferred.

FastAPI validates request schemas and exposes health, model availability,
image/video/lip-sync submission, job status/history and safe local outputs.
An injected worker interface, bounded queue, timeout/cancellation and SQLite
job persistence are implemented. The default app registers no working adapter.
Uploads return 501 `UPLOAD_NOT_AVAILABLE`; unavailable models return 409
`MODEL_NOT_AVAILABLE` without creating jobs.

## Verification

| Check | Final result |
| --- | --- |
| Node client/proxy/model/storage tests | 17 passed, 0 failed |
| FastAPI/backend tests | 23 passed, 0 failed |
| Live local integration against dev server | 16 checks passed |
| Live local integration against production server | 16 checks passed |
| Four existing studios rendered with empty models | 4 passed |
| Next.js production build | Passed |
| Workspace CSS/Babel build | Passed |
| Legacy Vite production build | Passed |
| Python dependency consistency (`pip check`) | Passed |
| Git whitespace check (`git diff --check`) | Passed |
| Interactive browser/visual check | Not run: browser inventory was empty and the in-app browser was unavailable |
| Genuine AI image/video/lip-sync inference | Not attempted: outside Phases 1–3, no model installed |

Backend fixtures are explicitly test-only and exercise storage/transport; they
are not AI inference evidence. Persistence/retrieval is verified using isolated
fixture jobs and files, not fabricated production history.

An initial Vite build failed because the filesystem sandbox denied esbuild's
parent-directory metadata lookup. The approved local build passed outside that
sandbox. Existing mixed Tailwind 3/4 configuration was aligned with Tailwind 3.
Warnings remain about Node module detection, Vite's CommonJS API and duplicate
module imports, Browserslist data, and Starlette's test-only HTTPX deprecation.
These warnings did not fail the final checks.

## Dependencies

Initial audit: **52** findings (2 critical, 39 high, 9 moderate, 2 low).
Final audit: **32** findings (1 critical, 23 high, 8 moderate).
Production-only audit: **2** findings (1 high, 1 moderate).

Next.js and matching ESLint config were updated to 15.5.27; direct PostCSS to
8.5.30; compatible Babel and transitive patches were applied. Unused Axios and
the unused Tailwind 4 Vite plugin were removed. `npm audit fix` was run with
install scripts disabled and without `--force`.

Remaining findings cover Vite/Electron/build tooling, Tailwind/Babel transitive
pattern parsing and Next.js's nested PostCSS dependency. npm recommends major
toolchain migrations for these. The remaining critical `tar` finding is in
desktop build tooling. This report does **not** claim a clean audit or readiness
for public deployment. Full reports are in `audits/npm-before.json`,
`audits/npm-after.json` and `audits/npm-production.json`.

A scoped nested PostCSS override was evaluated but removed after npm retained
the old nested resolution; no unresolved override or invalid dependency tree
is left in the final manifest. Existing user lockfile changes were backed up in
ignored `.cache/preexisting-package-lock.json` and
`.cache/preexisting-package-lock.diff` before dependency reconciliation.

## Commands executed

Repository/machine inspection used `rg --files`, `rg -n`, `Get-Content`,
`git status --short`, `git diff`, `git remote -v`, `git branch --show-current`,
`python --version`, `py --list`, `python -m pip --version`, `node --version`,
`npm.cmd --version`, `npm.cmd ls` and `nvidia-smi`.

The branch was created with:

```powershell
git switch -c feat/self-hosted-local-foundation
```

Main setup, dependency and validation commands (some were repeated after fixes):

```powershell
npm.cmd audit --json --cache .cache/npm
npm.cmd outdated --json --cache .cache/npm
npm.cmd update next eslint-config-next postcss @babel/cli @babel/preset-env @babel/preset-react --ignore-scripts --cache .cache/npm --no-fund
npm.cmd audit fix --ignore-scripts --cache .cache/npm --no-fund
npm.cmd update postcss --ignore-scripts --cache .cache/npm --no-fund
npm.cmd dedupe --ignore-scripts --cache .cache/npm --no-fund
npm.cmd install --ignore-scripts --cache .cache/npm --no-fund
npm.cmd audit --omit=dev --json --cache .cache/npm
python -m venv backend/.venv
& .\backend\.venv\Scripts\python.exe -m pip install --cache-dir .cache/pip -r backend/requirements-dev.txt
npm.cmd test
& .\backend\.venv\Scripts\python.exe -m unittest discover -s backend/tests -v
& .\backend\.venv\Scripts\python.exe -m pip check
& .\backend\.venv\Scripts\python.exe -m pip freeze
npm.cmd run build
npm.cmd run build:studio
node scripts/check-studio-render.cjs
npm.cmd run vite:build
npm.cmd run dev
& .\backend\.venv\Scripts\python.exe -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000
Invoke-RestMethod 'http://127.0.0.1:3000/api/local/health'
Invoke-RestMethod 'http://127.0.0.1:3000/api/local/models'
node scripts/smoke-local.mjs
npm.cmd start
git diff --check
```

Legacy source also received `node --check` and relative-import checks; all 20
JavaScript files passed. The studio components and shell received a read-only
in-memory Babel/React render check in addition to the reproducible render script.

PowerShell blocked `npm.ps1`; all successful npm commands used `npm.cmd`.
Initial sandboxed audit/network commands failed and were rerun with reviewed
network access. No execution policy or other OS security control was changed.

## Known limits and next task

This is a single-user, loopback-only foundation with a single-process queue.
No model adapter, validated upload pipeline, character studio, real image
generation, video generation or lip-sync inference is implemented yet. Cinema
camera/lens controls remain usable and compose prompts, but cannot generate
without a ready image worker. Future adapters must validate their own supported
options and local input files and stop inference on cancellation.

Model identity conditioning, GPU offload, distributed workers, remote inference
hosts, authentication, cloud queues/storage and deployment are later work.
No AWS resource changes or assumptions about GPU quota/credit eligibility were
made. Browser visual behavior remains to be checked manually.

Recommended next task: evaluate SD 1.5 with a suitable ComfyUI configuration for
the GTX 1650/4 GB/driver 462.21. Check Python/PyTorch compatibility and VRAM first,
then request approval for any weights or driver changes. Only after setup,
connect one real worker and verify two different custom prompts and saved files.

Exact first-time setup, two-terminal startup and reproducible checks are in
[LOCAL_DEVELOPMENT.md](LOCAL_DEVELOPMENT.md). Windows `.cmd` helpers are in
`backend/` and do not require changing PowerShell execution policy.

## Files created

```text
.env.example
app/api/local/[...path]/route.js
backend/.env.example
backend/.gitignore
backend/README.md
backend/__init__.py
backend/app/__init__.py
backend/app/config.py
backend/app/errors.py
backend/app/jobs.py
backend/app/main.py
backend/app/schemas.py
backend/app/storage.py
backend/app/workers.py
backend/requirements.txt
backend/requirements-dev.txt
backend/requirements-lock.txt
backend/setup.cmd
backend/start.cmd
backend/test.cmd
backend/tests/test_backend.py
docs/IMPLEMENTATION_REPORT.md
docs/LOCAL_DEVELOPMENT.md
docs/REPOSITORY_ANALYSIS.md
docs/audits/npm-before.json
docs/audits/npm-after.json
docs/audits/npm-production.json
lib/local-backend.mjs
packages/studio/src/api.js
scripts/check-studio-render.cjs
scripts/smoke-local.mjs
src/lib/localApi.js
src/lib/localStorage.js
tests/legacy-local.test.mjs
tests/local-backend.test.mjs
tests/local-client.test.mjs
tests/model-registry.test.mjs
```

## Files modified

```text
.gitignore
README.md
app/layout.js
components/ApiKeyModal.js
components/StandaloneShell.js
electron/main.js
index.html
next.config.mjs
package.json
package-lock.json
packages/studio/package.json
packages/studio/src/components/CinemaStudio.jsx
packages/studio/src/components/ImageStudio.jsx
packages/studio/src/components/LipSyncStudio.jsx
packages/studio/src/components/VideoStudio.jsx
packages/studio/src/models.js
packages/studio/src/muapi.js
src/components/AuthModal.js
src/components/CinemaStudio.js
src/components/Header.js
src/components/ImageStudio.js
src/components/LipSyncStudio.js
src/components/SettingsModal.js
src/components/UploadPicker.js
src/components/VideoStudio.js
src/lib/models.js
src/lib/muapi.js
src/lib/pendingJobs.js
src/lib/uploadHistory.js
src/main.js
src/style.css
src/styles/global.css
vite.config.js
```

Generated/ignored local artifacts include `backend/.venv`, `backend/data`,
`.next`, workspace/root `dist`, and `.cache`.

Temporary test servers were stopped after validation. Because Ctrl+C did not
stop the PTY-hosted processes, their exact command lines were checked with
`Get-CimInstance Win32_Process` and only the verified test server PIDs were
stopped using `Stop-Process`. No unrelated process was stopped.
