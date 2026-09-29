@echo off
setlocal
chcp 65001 >nul
cd /d "%~dp0"

set "GIT_TERMINAL_PROMPT=0"
set "GCM_INTERACTIVE=never"
set "GIT_HTTP_LOW_SPEED_LIMIT=1000"
set "GIT_HTTP_LOW_SPEED_TIME=15"

echo [1/4] กำลังตรวจหาอัปเดต...
git pull --ff-only --quiet
if errorlevel 1 echo       ข้ามการอัปเดต ใช้เวอร์ชันเดิม

where uv >nul 2>nul
if errorlevel 1 set "PATH=%USERPROFILE%\.local\bin;%PATH%"
where uv >nul 2>nul
if errorlevel 1 (
  echo [2/4] กำลังติดตั้ง uv...
  powershell -NoProfile -ExecutionPolicy ByPass -Command "irm https://astral.sh/uv/install.ps1 | iex"
  if errorlevel 1 goto fail
) else (
  echo [2/4] มี uv แล้ว
)

echo [3/4] กำลังเตรียม Python และไลบรารี (ครั้งแรกใช้เวลา 1-2 นาที)...
uv sync --frozen --no-dev --quiet
if errorlevel 1 goto fail

echo [4/4] กำลังเปิด YT Toolkit...
start "" ".venv\Scripts\pythonw.exe" -m yttoolkit start
exit /b 0

:fail
echo.
echo เปิดโปรแกรมไม่สำเร็จ ถ่ายภาพหน้าจอนี้ส่งให้ผู้ดูแล แล้วกดปุ่มใดก็ได้เพื่อปิดหน้าต่าง
pause >nul
exit /b 1
