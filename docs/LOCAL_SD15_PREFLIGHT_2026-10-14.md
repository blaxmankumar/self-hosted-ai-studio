# Local SD 1.5 preflight: stopped at memory gate

Checked **14 October 2026, 16:26–16:27 IST (Asia/Calcutta)** for the user's
local-only Option A. No genuine image was generated. No GPU runtime was loaded.

The current request authorizes isolated setup only if resource checks pass.
It explicitly requires stopping under excessive memory pressure and separate
approval before checkpoint downloads or driver changes. Those current
instructions take precedence over historical trial permissions.

## Resource measurements

GiB means 1024^3 bytes. VRAM values below use MiB.

| Measurement | 16:26:52 IST | 16:27:04 IST |
| --- | --- | --- |
| Total usable physical RAM | 7.845 GiB | 7.845 GiB |
| Available physical RAM | **0.558 GiB** | **0.843 GiB** |
| Physical memory load | 92% | 89% |
| Committed memory | 17.574 GiB | 17.357 GiB |
| Commit limit | 19.005 GiB | 19.005 GiB |
| Remaining commit headroom | **1.431 GiB** | **1.648 GiB** |
| Commit utilization | **92.47%** | **91.33%** |

Commit headroom is system commit limit minus committed bytes. It does not
represent free physical RAM or substitute for RAM during CPU offloading.

| Additional measurement | Result |
| --- | --- |
| GPU | GeForce GTX 1650 Ti with Max-Q Design |
| NVIDIA driver | 462.21 |
| VRAM total / used / free | 4096 / 134 / 3962 MiB |
| GPU utilization | 0% at sampling |
| C: free / total | 50.173 / 355.548 GiB |
| D: free / total | 75.067 / 102.477 GiB |
| Python | CPython 3.13.12, 64-bit |
| Python executable | `C:\Users\MSI\AppData\Local\Programs\Python\Python313\python.exe` |

**Decision: stop before isolated environment creation, installation or model
loading.** Both samples have less than 1 GiB available RAM and less than 2 GiB
commit headroom. The existing project assessment targets approximately 2–3 GiB
available RAM and several GiB commit headroom even for a small CUDA test, with
roughly 4 GiB available preferred before model loading. These are conservative
trial gates, not vendor minimums or a guarantee that full inference fits.

Mostly free VRAM and sufficient disk space do not fix the system RAM shortage.
Low-VRAM CPU offloading would also consume system RAM; it is not a reason to
bypass this gate. No pagefile or other system setting was changed.

## Existing worker contract and configuration

- The frontend already submits through `/api/local` to FastAPI, whose HTTP
  worker adapter accepts a loopback worker origin such as
  `http://127.0.0.1:<port>`. This supports entirely local inference; external
  GPU hosting is unnecessary.
- `backend/.env` is currently absent. `Settings.from_environment()` reports the
  worker URL unconfigured; all registry entries are configured/available false.
  This was checked without printing any credential or starting a worker.
- A native ComfyUI endpoint cannot be substituted directly for the existing
  contract. A future local bridge must implement `GET /v1/health`,
  `POST /v1/jobs`, `GET /v1/jobs/{UUID}`,
  `GET /v1/jobs/{UUID}/outputs/{filename}`, and `DELETE /v1/jobs/{UUID}`.
  It must preserve UUID idempotency, actual progress/cancellation, and return
  genuine decoded 512 x 512 image results. See
  [the complete contract](GPU_WORKER_INTEGRATION.md).
- Video, Lip Sync and Cinema remain disabled with the current unavailable
  catalog. **Before enabling the image worker**, Cinema needs a separate
  capability guard: it currently shares text-to-image models and would become
  enabled when `remote-image` becomes available. Its current ratio/resolution
  defaults do not match the first adapter's square 512 contract. That future
  change was identified, not implemented after the resource stop.

## Execution and test status

| Stage | Result |
| --- | --- |
| RAM and commit check | Failed resource gate in both samples |
| GPU/driver inventory | Passed discovery; no CUDA computation implied |
| Disk inventory | Completed; space is not the current blocker |
| Python inventory | 3.13.12 x64 confirmed |
| Existing backend settings/registry inspection | Completed; no ready models |
| New isolated inference environment | Not created |
| PyTorch installation/CUDA tensor, cuBLAS or cuDNN tests | Not attempted |
| ComfyUI installation/startup/low-VRAM validation | Not attempted |
| SD 1.5 checkpoint download | Not attempted; approval still required |
| Local ComfyUI bridge implementation | Deferred at explicit resource stop |
| Genuine 512 x 512 Studio generation | Not attempted; no output exists |
| Generation time / throughput / peak inference RAM or VRAM | Unmeasured |
| Existing unit suites/builds | Preserved; not rerun during this resource stop |

Driver compatibility is **untested**, not declared failed. No inference speed,
model memory footprint or successful Studio generation is claimed. No
applications or existing servers were terminated. No application code, runtime
configuration, driver, pagefile or dependency was changed. Only this report was
added. No Kaggle, Muapi, AWS, paid API or external GPU host was used.

Sandboxed CIM/WMI queries returned Access denied. Read-only Windows
`GlobalMemoryStatusEx` and `GetPerformanceInfo` calls succeeded without elevated
access and supplied the memory measurements. Disk usage came from the standard
Python filesystem API. No resource check was skipped.

## Exact PowerShell commands

Run from the existing workspace. The following memory command was executed;
it only reads counters, samples twice 12 seconds apart, and prints JSON:

```powershell
Set-Location 'C:\Users\MSI\Open-Higgsfield-AI'
@'
import ctypes
from ctypes import wintypes
import datetime
import json
import shutil
import time

class MemoryStatus(ctypes.Structure):
    _fields_ = [("dwLength", wintypes.DWORD), ("dwMemoryLoad", wintypes.DWORD)] + [(name, ctypes.c_ulonglong) for name in ("ullTotalPhys", "ullAvailPhys", "ullTotalPageFile", "ullAvailPageFile", "ullTotalVirtual", "ullAvailVirtual", "ullAvailExtendedVirtual")]

class PerformanceInfo(ctypes.Structure):
    _fields_ = [("cb", wintypes.DWORD)] + [(name, ctypes.c_size_t) for name in ("CommitTotal", "CommitLimit", "CommitPeak", "PhysicalTotal", "PhysicalAvailable", "SystemCache", "KernelTotal", "KernelPaged", "KernelNonpaged", "PageSize")] + [(name, wintypes.DWORD) for name in ("HandleCount", "ProcessCount", "ThreadCount")]

kernel = ctypes.WinDLL("kernel32", use_last_error=True)
psapi = ctypes.WinDLL("psapi", use_last_error=True)
kernel.GlobalMemoryStatusEx.argtypes = [ctypes.POINTER(MemoryStatus)]
kernel.GlobalMemoryStatusEx.restype = wintypes.BOOL
psapi.GetPerformanceInfo.argtypes = [ctypes.POINTER(PerformanceInfo), wintypes.DWORD]
psapi.GetPerformanceInfo.restype = wintypes.BOOL

def sample():
    memory = MemoryStatus(dwLength=ctypes.sizeof(MemoryStatus))
    performance = PerformanceInfo(cb=ctypes.sizeof(PerformanceInfo))
    if not kernel.GlobalMemoryStatusEx(ctypes.byref(memory)) or not psapi.GetPerformanceInfo(ctypes.byref(performance), ctypes.sizeof(performance)):
        raise ctypes.WinError(ctypes.get_last_error())
    unit = 1024 ** 3
    commit = performance.CommitTotal * performance.PageSize
    limit = performance.CommitLimit * performance.PageSize
    return {"time_ist": datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=5, minutes=30))).isoformat(timespec="seconds"), "total_physical_gib": round(memory.ullTotalPhys / unit, 3), "available_physical_gib": round(memory.ullAvailPhys / unit, 3), "physical_load_percent": memory.dwMemoryLoad, "committed_gib": round(commit / unit, 3), "commit_limit_gib": round(limit / unit, 3), "commit_headroom_gib": round((limit - commit) / unit, 3), "commit_used_percent": round(100 * commit / limit, 2)}

print(json.dumps({"sample": sample()}), flush=True)
for drive in ("C:\\", "D:\\"):
    usage = shutil.disk_usage(drive)
    print(json.dumps({"drive": drive, "total_gib": round(usage.total / 1024**3, 3), "free_gib": round(usage.free / 1024**3, 3)}), flush=True)
time.sleep(12)
print(json.dumps({"sample": sample()}), flush=True)
'@ | python -
```

GPU and interpreter checks executed:

```powershell
nvidia-smi --query-gpu=name,driver_version,memory.total,memory.used,memory.free,utilization.gpu --format=csv
python --version
python -c "import struct,sys; print('executable:',sys.executable); print('bits:',struct.calcsize('P')*8)"
```

Existing backend configuration check executed (prints no URL or secret):

```powershell
& .\backend\.venv\Scripts\python.exe -c "from backend.app.config import Settings; from backend.app.workers import default_registry; s=Settings.from_environment(); print('worker_url_configured:',bool(s.remote_worker_url)); print('models:',[(m.id,m.type,m.configured,m.available) for m in default_registry(s).models()])"
```

## Safe next step

Save work and close unused browser/editor windows normally, then rerun the
read-only memory command above. Keep the working Studio and backend available.
Do not terminate Memory Compression, Windows Update or security services, and
do not increase the pagefile as a substitute for physical RAM.

When headroom is sufficient and stable, resume in order: isolated runtime;
verify actual CUDA tensor/cuBLAS/cuDNN operations; validate compatible ComfyUI
startup and low-VRAM settings without a checkpoint; obtain checkpoint approval;
verify/download only the approved model; add the local bridge and Cinema guard;
then generate through Image Studio and verify preview, history and download.
Driver changes also require separate approval. There is no current checkpoint
approval request because the earlier resource and CUDA prerequisites are unmet.
