@echo off
rem ============================================================
rem start.bat —— 双击一键启动「文物断代与鉴定系统」
rem 等价于在终端运行 .\start.ps1
rem ============================================================
cd /d "%~dp0"

where pwsh >nul 2>nul && (
    pwsh -NoProfile -ExecutionPolicy Bypass -File "%~dp0start.ps1"
) || (
    powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0start.ps1"
)

echo.
echo 已退出，按任意键关闭窗口...
pause >nul
