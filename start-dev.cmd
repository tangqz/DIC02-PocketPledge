@echo off
setlocal

set "ROOT_DIR=%~dp0"
set "BACKEND_DIR=%ROOT_DIR%backend"
set "FRONTEND_DIR=%ROOT_DIR%frontend"

echo Starting backend and frontend from %ROOT_DIR%

start "DIC2025 Backend" powershell -NoExit -ExecutionPolicy Bypass -Command "Set-Location '%BACKEND_DIR%'; uv run uvicorn app.main:app --host 0.0.0.0 --port 12393 --reload --reload-dir app --reload-dir scripts"
start "DIC2025 Frontend" powershell -NoExit -ExecutionPolicy Bypass -Command "Set-Location '%FRONTEND_DIR%'; npm run dev --host"
start "Vision Debugger" powershell -NoExit -ExecutionPolicy Bypass -Command "Set-Location '%BACKEND_DIR%'; uv run python scripts/vision_debugger.py"

echo Backend: http://0.0.0.0:12393 (局域网可访问)
echo Frontend: http://0.0.0.0:5173 (局域网可访问)
echo.
echo 提示: 使用你的本机 IP 地址从其他设备访问，例如:
echo   http://^<你的IP^>:5173
echo 查看 IP 地址: 运行 ipconfig 命令

endlocal