@echo off
setlocal

set "ROOT_DIR=%~dp0"
set "BACKEND_DIR=%ROOT_DIR%backend"
set "FRONTEND_DIR=%ROOT_DIR%frontend"

echo Starting backend and frontend from %ROOT_DIR%

start "DIC2026 Backend" powershell -NoExit -ExecutionPolicy Bypass -Command "Set-Location '%BACKEND_DIR%'; & '%BACKEND_DIR%\.venv\Scripts\python.exe' -m uvicorn app.main:app --host 0.0.0.0 --port 12393 --reload"
start "DIC2026 Frontend" powershell -NoExit -ExecutionPolicy Bypass -Command "Set-Location '%FRONTEND_DIR%'; npm run dev"
start "Vision Debugger" powershell -NoExit -ExecutionPolicy Bypass -Command "Set-Location '%BACKEND_DIR%\scripts'; & '%BACKEND_DIR%\.venv\Scripts\python.exe' vision_debugger.py"

echo Backend: http://localhost:12393
echo Frontend: Vite dev server window started

endlocal