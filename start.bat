@echo off
setlocal
rem เก็บ code page เดิมไว้ก่อน แล้วคืนค่าทุกทางออก (ดู :done และ :fail)
set "_OLDCP="
for /f "tokens=* delims=" %%a in ('chcp') do for %%b in (%%a) do set "_OLDCP=%%b"
set "_OLDCP=%_OLDCP:.=%"
echo %_OLDCP%| findstr /r "^[0-9][0-9]*$" >nul
if errorlevel 1 set "_OLDCP=65001"
chcp 65001 >nul
set "PYTHONUTF8=1"
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

rem ถ้าโปรแกรมเปิดอยู่แล้ว uv sync จะไปแก้ไฟล์ที่กำลังใช้งาน จึงข้ามขั้นนี้
set "_RUNNING="
if not exist ".venv\Scripts\python.exe" goto checkdone
".venv\Scripts\python.exe" -m yttoolkit wait --timeout 0 >nul 2>nul
if not errorlevel 1 set "_RUNNING=1"
:checkdone

if defined _RUNNING goto alreadyrunning
echo [3/4] กำลังเตรียม Python และไลบรารี ^(ครั้งแรกใช้เวลา 1-2 นาที^)...
uv sync --frozen --no-dev --quiet
if errorlevel 1 goto fail
goto launch

:alreadyrunning
echo       โปรแกรมเปิดอยู่แล้ว ถ้าเพิ่งมีอัปเดต ให้ปิดโปรแกรมแล้วเปิดใหม่เพื่อใช้เวอร์ชันล่าสุด

:launch
echo [4/4] กำลังเปิด YT Toolkit...
start "" ".venv\Scripts\pythonw.exe" -m yttoolkit start
echo       รอให้โปรแกรมพร้อม อาจใช้เวลาสูงสุด 25 วินาที
".venv\Scripts\python.exe" -m yttoolkit wait --timeout 25
if errorlevel 1 goto startfail
timeout /t 2 >nul
goto done

:startfail
echo.
echo ถ่ายภาพหน้าจอนี้ส่งให้ผู้ดูแล แล้วกดปุ่มใดก็ได้เพื่อปิดหน้าต่าง
pause >nul
chcp %_OLDCP% >nul
exit /b 1

:fail
echo.
echo เปิดโปรแกรมไม่สำเร็จ ถ่ายภาพหน้าจอนี้ส่งให้ผู้ดูแล แล้วกดปุ่มใดก็ได้เพื่อปิดหน้าต่าง
pause >nul
chcp %_OLDCP% >nul
exit /b 1

:done
chcp %_OLDCP% >nul
exit /b 0
