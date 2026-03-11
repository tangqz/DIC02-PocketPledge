@echo off
setlocal

set "ROOT_DIR=%~dp0"
set "BACKEND_DIR=%ROOT_DIR%backend"
set "FRONTEND_DIR=%ROOT_DIR%frontend"

echo Starting backend and frontend from %ROOT_DIR%

start "DIC2026 Backend" powershell -NoExit -ExecutionPolicy Bypass -Command "Set-Location '%BACKEND_DIR%'; python -m uvicorn app.main:app --host 0.0.0.0 --port 12393 --reload"
start "DIC2026 Frontend" powershell -NoExit -ExecutionPolicy Bypass -Command "Set-Location '%FRONTEND_DIR%'; npm run dev"

echo Backend: http://localhost:12393
echo Frontend: Vite dev server window started

endlocal