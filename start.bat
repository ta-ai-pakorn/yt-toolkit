@echo off
setlocal
rem git pull ในขั้น [1/4] อาจเขียนทับไฟล์นี้ แต่ cmd อ่านไฟล์ .bat ต่อจากตำแหน่ง byte เดิม ไฟล์ใหม่จึงพังกลางทาง
rem รอบแรกจึงคัดลอกตัวเองไปไว้ในโฟลเดอร์ TEMP แล้วรันสำเนานั้น โดยส่งโฟลเดอร์ของโปรแกรมไปเป็นพารามิเตอร์ตัวแรก
if defined YT_START_RELAUNCHED goto relaunched
set "YT_START_RELAUNCHED=1"
rem ตัวแปร RANDOM ตั้งต้นจากนาฬิกา ดับเบิลคลิกซ้ำในวินาทีเดียวกันจึงได้เลขซ้ำ ใส่เศษวินาทีและวนหาชื่อที่ยังไม่มี
:ytname
set "_YT_COPY=%TEMP%\yt-toolkit-start-%RANDOM%-%TIME:~-2%%RANDOM%.bat"
if exist "%_YT_COPY%" goto ytname
rem ถ้าคัดลอกไม่ได้ (เช่นโฟลเดอร์ TEMP เขียนไม่ได้) ก็รันจากไฟล์เดิมแบบก่อนหน้านี้
copy /y "%~f0" "%_YT_COPY%" >nul 2>nul
if errorlevel 1 (
  call "%~f0" "%~dp0"
  exit /b
)
rem คำสั่งหลัง call ต้องอยู่ในวงเล็บชุดเดียว cmd อ่านทั้งชุดไว้ก่อน จึงไม่ต้องกลับไปอ่านไฟล์นี้ที่อาจถูกเขียนทับแล้ว
(
  call "%_YT_COPY%" "%~dp0"
  call set "_YT_RC=%%ERRORLEVEL%%"
  del "%_YT_COPY%" >nul 2>nul
  call exit /b %%_YT_RC%%
)

:relaunched
rem เก็บ code page เดิมไว้ก่อน แล้วคืนค่าทุกทางออก (ดู :done และ :fail)
set "_OLDCP="
for /f "tokens=* delims=" %%a in ('chcp') do for %%b in (%%a) do set "_OLDCP=%%b"
set "_OLDCP=%_OLDCP:.=%"
echo %_OLDCP%| findstr /r "^[0-9][0-9]*$" >nul
if errorlevel 1 set "_OLDCP=65001"
chcp 65001 >nul
set "PYTHONUTF8=1"
cd /d "%~1"

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
rem ถ้าโปรแกรมเปิดอยู่แล้ว ค้างหน้าต่างไว้นานขึ้นให้อ่านข้อความด้านบนทัน
if defined _RUNNING (
  timeout /t 6 >nul
) else (
  timeout /t 2 >nul
)
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
