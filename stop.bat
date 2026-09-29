@echo off
chcp 65001 >nul
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo YT Toolkit ยังไม่ได้ติดตั้ง
  timeout /t 3 >nul
  exit /b 0
)
".venv\Scripts\python.exe" -m yttoolkit stop
timeout /t 3 >nul
