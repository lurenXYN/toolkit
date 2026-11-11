@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  python -m venv .venv
  ".venv\Scripts\python.exe" -m pip install -r requirements.txt
)
echo Starting toolkit at http://127.0.0.1:8780
".venv\Scripts\python.exe" -m toolkit serve --host 127.0.0.1 --port 8780
pause
