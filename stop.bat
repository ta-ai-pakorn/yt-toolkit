@echo off
setlocal
rem เก็บ code page เดิมไว้ก่อน แล้วคืนค่าทุกทางออก (ดู :done)
set "_OLDCP="
for /f "tokens=* delims=" %%a in ('chcp') do for %%b in (%%a) do set "_OLDCP=%%b"
set "_OLDCP=%_OLDCP:.=%"
echo %_OLDCP%| findstr /r "^[0-9][0-9]*$" >nul
if errorlevel 1 set "_OLDCP=65001"
chcp 65001 >nul
set "PYTHONUTF8=1"
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo YT Toolkit ยังไม่ได้ติดตั้ง
  timeout /t 3 >nul
  goto done
)
".venv\Scripts\python.exe" -m yttoolkit stop
timeout /t 3 >nul

:done
chcp %_OLDCP% >nul
exit /b 0
