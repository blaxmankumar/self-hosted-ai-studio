# Complete project preservation manifest

Prepared 15 October 2026 (Asia/Calcutta) for a local, append-only commit.

- Branch: `feat/self-hosted-local-foundation`.
- Parent before preservation: `b578108936e83a3b2a5e86644057a56f8aea73a1`.
- Remote left unchanged: `origin` -> `https://github.com/Autom8AI/Open-Higgsfield-AI.git` (fetch and push).
- No push, fetch, history rewrite, reset, revert, deletion, squash or source restoration was performed.
- Initial state: 33 modified tracked files, 43 untracked source/documentation files, no staged files.
- Planned commit: **77 changed files** (33 modified and 44 added, including this manifest).
- Complete retained project tree: **124 files**, including 47 unchanged original tracked files.
- Existing source edits are preserved as currently implemented, including the completed replacement of old provider catalogs. Earlier versions remain in the existing Git history.

## Safety checks

- Inspected current branch, HEAD, remotes, index and unstaged/untracked files.
- Scanned the complete candidate project tree for recognized credential/token/private-key signatures, credential URLs and literal secret assignments. The eight initial findings were reviewed as deliberate test fixtures or invalid-URL rejection cases; no genuine credentials were detected.
- Checked candidate paths for actual environment files, private keys, model binaries, dependencies, environments, caches and builds: none are part of the candidate tree.
- Checked sizes: no candidate file is 50 MiB or larger. Largest retained original file is `docs/assets/demo.mp4`, approximately 5.752 MiB. No large binary staging is needed.
- Verified both `.env.example` templates remain includable and contain no actual credentials.
- Independent inventory review found no legitimate source, tests, setup scripts or project documentation accidentally hidden by ignore rules.
- Only `.gitignore` was extended for additional exclusions, and this manifest was added during preservation. Application code and tests were not edited.
- No models, drivers, cloud resources or paid APIs were installed or used. Runtime/build tests are not part of this preservation operation; their previous results remain documented in the included reports.

## Changed files included in the preservation commit

```text
A  .env.example
M  .gitignore
M  README.md
A  app/api/local/[...path]/route.js
M  app/layout.js
A  backend/.env.example
A  backend/.gitignore
A  backend/README.md
A  backend/__init__.py
A  backend/app/__init__.py
A  backend/app/config.py
A  backend/app/errors.py
A  backend/app/jobs.py
A  backend/app/main.py
A  backend/app/remote_worker.py
A  backend/app/schemas.py
A  backend/app/storage.py
A  backend/app/workers.py
A  backend/requirements-dev.txt
A  backend/requirements-lock.txt
A  backend/requirements.txt
A  backend/setup.cmd
A  backend/start.cmd
A  backend/test.cmd
A  backend/tests/test_backend.py
A  backend/tests/test_remote_worker.py
M  components/ApiKeyModal.js
M  components/StandaloneShell.js
A  docs/GPU_WORKER_IMPLEMENTATION_REPORT.md
A  docs/GPU_WORKER_INTEGRATION.md
A  docs/IMPLEMENTATION_REPORT.md
A  docs/LOCAL_DEVELOPMENT.md
A  docs/LOCAL_SD15_PREFLIGHT_2026-10-14.md
A  docs/PHASE4_TRIAL_REPORT.md
A  docs/PROJECT_PRESERVATION_MANIFEST.md
A  docs/REPOSITORY_ANALYSIS.md
A  docs/audits/npm-after.json
A  docs/audits/npm-before.json
A  docs/audits/npm-production.json
M  electron/main.js
M  index.html
A  lib/local-backend.mjs
M  next.config.mjs
M  package-lock.json
M  package.json
M  packages/studio/package.json
A  packages/studio/src/api.js
M  packages/studio/src/components/CinemaStudio.jsx
M  packages/studio/src/components/ImageStudio.jsx
M  packages/studio/src/components/LipSyncStudio.jsx
M  packages/studio/src/components/VideoStudio.jsx
M  packages/studio/src/models.js
M  packages/studio/src/muapi.js
A  scripts/check-studio-render.cjs
A  scripts/smoke-local.mjs
M  src/components/AuthModal.js
M  src/components/CinemaStudio.js
M  src/components/Header.js
M  src/components/ImageStudio.js
M  src/components/LipSyncStudio.js
M  src/components/SettingsModal.js
M  src/components/UploadPicker.js
M  src/components/VideoStudio.js
A  src/lib/localApi.js
A  src/lib/localStorage.js
M  src/lib/models.js
M  src/lib/muapi.js
M  src/lib/pendingJobs.js
M  src/lib/uploadHistory.js
M  src/main.js
M  src/style.css
M  src/styles/global.css
A  tests/legacy-local.test.mjs
A  tests/local-backend.test.mjs
A  tests/local-client.test.mjs
A  tests/model-registry.test.mjs
M  vite.config.js
```

## Original files retained unchanged in the commit tree

```text
afterPack.js
app/globals.css
app/page.js
app/studio/page.js
docs/assets/demo.mp4
docs/assets/generated_example.webp
docs/assets/studio_demo.webp
jsconfig.json
models_dump.json
packages/studio/babel.config.json
packages/studio/package-lock.json
packages/studio/postcss.config.js
packages/studio/src/index.js
packages/studio/src/tailwind.css
packages/studio/tailwind.config.js
postcss.config.js
project_knowledge.md
public/assets/cinema/70s_cinema_prime.webp
public/assets/cinema/classic_16mm_film.webp
public/assets/cinema/classic_anamorphic.webp
public/assets/cinema/clinical_sharp_prime.webp
public/assets/cinema/compact_anamorphic.webp
public/assets/cinema/creative_tilt_lens.webp
public/assets/cinema/extreme_macro.webp
public/assets/cinema/f_11.webp
public/assets/cinema/f_1_4.webp
public/assets/cinema/f_4.webp
public/assets/cinema/full_frame_cine_digital.webp
public/assets/cinema/grand_format_70mm_film.webp
public/assets/cinema/halation_diffusion.webp
public/assets/cinema/modular_8k_digital.webp
public/assets/cinema/premium_large_format_digital.webp
public/assets/cinema/premium_modern_prime.webp
public/assets/cinema/studio_digital_s35.webp
public/assets/cinema/swirl_bokeh_portrait.webp
public/assets/cinema/vintage_prime.webp
public/assets/cinema/warm_cinema_prime.webp
public/banner.png
public/vite.svg
src/components/CameraControls.js
src/components/Sidebar.js
src/counter.js
src/javascript.svg
src/lib/promptUtils.js
src/styles/studio.css
src/styles/variables.css
tailwind.config.js
```

## Excluded local files and reasons

Ignore rules prevent these from being newly staged. Excluded files stay on disk; nothing was removed.

| Path/pattern | Reason |
| --- | --- |
| `.env`, `.env.*`, `*.env`, `.envrc` | Actual local environment configuration and potential secrets; `.env.example` is explicitly retained. |
| `.aws/`, `.ssh/`, `.git-credentials`, `.netrc`, `*.pem`, `*.key`, `*.p12`, `*.pfx` | Local credentials and private key material. |
| `node_modules/` | Reinstallable dependencies; source manifests and both npm lockfiles are retained. |
| `.venv*/`, `venv/`, `env/`, `site-packages/` | Machine-specific Python environments; requirements and pinned constraints are retained. |
| `.cache/`, `__pycache__/`, `*.pyc`, tool caches, coverage, logs | Rebuildable local/cache/runtime state. |
| `.next/`, `dist/`, `dist-ssr/`, root `out/` and `release/` | Rebuildable frontend and packaged application output. |
| `backend/data/`, root `outputs/`, `uploads/`, `generated/` | SQLite runtime jobs, uploads and generated inference outputs, not source code. |
| `*.ckpt`, `*.safetensors`, `*.pt`, `*.pth`, `*.onnx`, `*.gguf`, `*.h5`, `*.hdf5`, `*.tflite`, `*.torchscript`, `*.bin` | Model/checkpoint binaries; model registry/configuration source remains included. |
| Editor state and `.ipynb_checkpoints/` | Local editor/notebook state. |

The initial ignored-file inventory contained 31,379 files: `.cache` 1,891; `.next` 90; backend environments/data/bytecode 2,093; root `dist` 31; `node_modules` 27,265; Studio build output 9. Counts may change while local development services run.

Original already-tracked documentation/demo and UI assets are retained, including `docs/assets/generated_example.webp` and `models_dump.json`. Their names do not make them runtime output for this snapshot. This preservation does not claim that a genuine Studio inference has succeeded.

## Verification after committing

The final commit hash, clean Git status and unchanged remotes are reported in the chat after the commit exists. The commit must have the parent above and retain every initially tracked path. No remote operation is authorized yet.

```powershell
git branch --show-current
git show --stat --oneline HEAD
git diff-tree --no-commit-id --name-status -r HEAD
git status --short
git remote -v
```
