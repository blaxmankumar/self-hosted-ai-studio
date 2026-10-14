# Repository inspection and implementation scope

Inspected locally on 13 October 2026, before source edits. Work branch:
`feat/self-hosted-local-foundation`. A modified `package-lock.json` and an
untracked `.next/` directory existed before this work; no source files were
deleted. The original lockfile and its diff were copied into ignored `.cache/`
before dependency reconciliation.

## Existing application

- Next.js App Router: `app/page.js` redirects to `/studio`;
  `app/studio/page.js` mounts `components/StandaloneShell.js`.
- The active React studios are exported by the local npm workspace `studio`
  from `packages/studio/src/index.js`. Its Image, Video, Lip Sync and Cinema
  components use Tailwind and React state. Cinema includes camera, lens,
  focal-length and aperture controls with local preview assets.
- A second, independent vanilla-JavaScript frontend lives in `src/`, starts
  with Vite, and is packaged by `electron/main.js`. It must also be addressed
  to prevent an alternate entry point from calling the old provider.
- Muapi inference and uploads were implemented separately in
  `packages/studio/src/muapi.js` and `src/lib/muapi.js`. The Vite `/api` proxy
  targeted `api.muapi.ai`. Fetch and XMLHttpRequest sent `x-api-key` headers.
- `components/StandaloneShell.js` required `localStorage.muapi_key` before
  mounting any studio. Legacy auth/settings also persisted this key, and the
  legacy client could read `window.__MUAPI_KEY__`.
- Both frontend trees used generated, static hosted-model catalogs in
  `models.js`, with model-specific aspect ratios, resolutions, durations,
  quality and reference-image fields. Image and Video assumed a nonempty
  model list; empty lists require guarded initialization and mode switching.
- Uploads used remote URLs. The React image picker kept upload state in
  memory. Legacy upload references were persisted as `muapi_uploads`;
  pending jobs as `muapi_pending_jobs`; histories as `muapi_history`,
  `video_history`, `lipsync_history` and `cinema_history`. React generation
  history was primarily component state. Loading old remote media or polling
  old job IDs would make requests even after replacing generation methods.
- Downloads fetched output URLs; several helpers fell back to opening those
  URLs. The local client must validate all result/history URLs.
- Electron explicitly disabled `webSecurity`; this setting has been restored
  and sandboxing enabled. Desktop packaging is outside the validated MVP.

## Dependency and machine checks

Initial `npm audit` reported **52 findings**: 2 critical, 39 high, 9 moderate,
2 low. The complete initial report is `audits/npm-before.json`.
Installed versions included Next 15.5.14, React 19.2.4, Vite 5.4.21,
Electron 33.4.11, Electron Builder 25.1.8, PostCSS 8.5.6 and Axios 1.13.6.
Axios had no source imports and was unnecessary for the local fetch client.
Safe dependency updates stay within existing major versions; remaining
Vite/Electron/Tailwind toolchain migrations are separate work.

`nvidia-smi` confirmed an NVIDIA GeForce GTX 1650, 4096 MiB VRAM,
driver 462.21 and reported CUDA driver compatibility 11.2. This is not proof
that a particular PyTorch build or model is compatible. Python 3.13.12 and
Node 25.3.0 are installed; `py --list` did not find registered interpreters.
Use `python` rather than assuming the `py` launcher works. PowerShell blocks
`npm.ps1`; `npm.cmd` works without changing execution policy.

## Implementation plan: Phases 1–3 only

1. Create the feature branch and record this inspection.
2. Replace hosted inference with a provider-independent, same-origin client
   and an allowlisted Next.js route to the loopback FastAPI service. Remove
   key gates, clear only known old secret keys, preserve old stored histories
   without loading remote media, and use truthful local model availability.
3. Add typed FastAPI endpoints, persistent jobs, a worker interface, safe
   local outputs, restricted CORS/origins, bounded timeouts, environment
   examples, Windows startup commands and focused tests.
4. Verify backend startup, Next.js startup, connection, unavailable-model
   errors and local job/output behavior. Test worker fixtures validate
   plumbing only; they are never described as genuine AI inference.

No model weights, PyTorch/CUDA packages, GPU driver changes, cloud resources
or real image/video/lip-sync inference are part of this run. Uploads are
explicitly unavailable until a validated model integration is implemented.
