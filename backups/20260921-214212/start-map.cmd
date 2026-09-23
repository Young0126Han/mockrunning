@echo off
setlocal
cd /d "%~dp0"
set "PYTHONPATH=%~dp0src"
set "PYTHON=%~dp0.venv\Scripts\python.exe"
if not exist "%PYTHON%" set "PYTHON=python.exe"
start "" /b "%PYTHON%" -m ios_location_controller.web
timeout /t 3 /nobreak >nul
start "" http://127.0.0.1:8765
echo Map server started at http://127.0.0.1:8765
