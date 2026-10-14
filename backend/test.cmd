@echo off
setlocal
cd /d "%~dp0.."
"backend\.venv\Scripts\python.exe" -m unittest discover -s backend/tests -v
