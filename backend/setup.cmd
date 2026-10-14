@echo off
setlocal
cd /d "%~dp0"
python -m venv .venv
if errorlevel 1 exit /b 1
".venv\Scripts\python.exe" -m pip install -r requirements-dev.txt -c requirements-lock.txt
if errorlevel 1 exit /b 1
if not exist .env copy .env.example .env >nul
echo Backend environment ready. Run backend\start.cmd from the project root.
