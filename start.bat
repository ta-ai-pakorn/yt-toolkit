@echo off
setlocal
rem การอัปเดตในขั้น [1/4] (git merge หรือ reset) อาจเขียนทับไฟล์นี้ แต่ cmd อ่านไฟล์ .bat ต่อจากตำแหน่ง byte เดิม ไฟล์ใหม่จึงพังกลางทาง
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
rem ถ้าปิดหน้าต่างตอน git กำลังเขียนไฟล์ จะเหลือ .git\index.lock กับไฟล์เก่าปนใหม่ แล้วการอัปเดตครั้งต่อไปพังตลอด
rem จึงอัปเดตใน :update ซึ่งเขียนไฟล์ run\update-in-progress ไว้ก่อน และลบทิ้งเมื่อจบ ถ้ารอบหน้าเจอไฟล์นี้แปลว่ารอบก่อนถูกตัดกลางทาง
rem run\update.lock เปิดค้างไว้ตลอดที่อยู่ใน :update และ git ที่รันจากในนั้นถือต่อด้วย ถ้ายังเปิดไม่ได้แปลว่ามี start.bat หรือ git ของมันทำงานอยู่ จึงข้ามการอัปเดต
if not exist "run\" mkdir "run" >nul 2>nul
set "_YT_FREE="
set "_YT_UPDATED="
2>nul (call :lockprobe 9>>"run\update.lock")
if defined _YT_FREE call :update 9>>"run\update.lock"
if not defined _YT_UPDATED echo       ข้ามการอัปเดต ใช้เวอร์ชันเดิม
rem ใช้ตอนทดสอบเท่านั้น (tests/integration/test_start_bat_update.py) ให้หยุดหลังขั้นอัปเดต
if defined YT_START_TEST_UPDATE_ONLY goto done

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

:lockprobe
set "_YT_FREE=1"
exit /b 0

:update
set "_YT_PHASE="
if exist "run\update-in-progress" set /p _YT_PHASE=<"run\update-in-progress"
rem ถ้าซ่อมไม่สำเร็จ ข้ามการอัปเดตรอบนี้และเก็บ run\update-in-progress ไว้ให้รอบหน้าซ่อมใหม่
if exist "run\update-in-progress" (
  call :repair
  if errorlevel 1 exit /b 0
)
rem ขั้น fetch โหลดผ่านเน็ตอย่างเดียว ไม่แตะไฟล์ของโปรแกรม ถ้าถูกตัดตรงนี้ไฟล์ยังครบชุดเดิม
>"run\update-in-progress" echo fetch
git fetch --quiet
if errorlevel 1 goto updateend
rem ถ้ามีไฟล์ของ git ที่แก้ค้างไว้ (เครื่องนักพัฒนา) จดว่า merge-dirty แล้วถ้าถูกตัดกลางทาง รอบหน้าจะไม่ reset ทับงานที่แก้
rem ไม่นับไฟล์นอก git เพราะ reset ไม่ลบไฟล์เหล่านั้น และ merge ตรวจก่อนเขียนแล้วว่าไม่มีไฟล์นอก git ขวางทาง
rem ตรวจไม่ได้ก็ถือว่ามีงานที่แก้ไว้ก่อน
set "_YT_MERGEPHASE=merge"
git diff --quiet HEAD >nul 2>nul
if errorlevel 1 set "_YT_MERGEPHASE=merge-dirty"
>"run\update-in-progress" echo %_YT_MERGEPHASE%
git merge --ff-only --quiet @{u}
if errorlevel 1 goto updateend
set "_YT_UPDATED=1"
:updateend
del "run\update-in-progress" >nul 2>nul
exit /b 0

:repair
rem ไฟล์ run\update-in-progress ยืนยันว่า start.bat รอบก่อนถูกตัดกลางทาง และเราถือ run\update.lock อยู่ จึงไม่มี git ของรอบนั้นเหลืออยู่ ลบไฟล์ lock ที่ค้างได้
echo       อัปเดตครั้งก่อนค้างกลางทาง กำลังซ่อม...
rem หาโฟลเดอร์ของ git จาก git เอง เพราะใน worktree ที่แยกออกมา .git เป็นไฟล์ ไม่ใช่โฟลเดอร์
set "_YT_GITDIR="
set "_YT_COMMONDIR="
for /f "delims=" %%g in ('git rev-parse --git-dir 2^>nul') do set "_YT_GITDIR=%%g"
for /f "delims=" %%g in ('git rev-parse --git-common-dir 2^>nul') do set "_YT_COMMONDIR=%%g"
if not defined _YT_GITDIR exit /b 1
if not defined _YT_COMMONDIR exit /b 1
set "_YT_GITDIR=%_YT_GITDIR:/=\%"
set "_YT_COMMONDIR=%_YT_COMMONDIR:/=\%"
del /f /q "%_YT_GITDIR%\*.lock" >nul 2>nul
del /f /q "%_YT_COMMONDIR%\packed-refs.lock" >nul 2>nul
if exist "%_YT_COMMONDIR%\refs\" for /r "%_YT_COMMONDIR%\refs" %%f in (*.lock) do del /f /q "%%f" >nul 2>nul
rem ล้างไฟล์ที่แก้ค้างไว้เฉพาะเมื่อรอบก่อนถูกตัดตอนเขียนไฟล์ (merge) บนเครื่องที่ไม่มีงานแก้ค้าง
rem ถ้าถูกตัดตอนโหลด (fetch) ไฟล์ยังไม่ถูกแตะ และถ้าเป็น merge-dirty ห้าม reset เพราะจะทิ้งงานที่แก้ไว้ จึงลบแค่ lock
if not "%_YT_PHASE%"=="merge" exit /b 0
rem ขั้น merge เริ่มหลัง fetch จบแล้ว @{u} จึงเป็นเวอร์ชันที่รอบก่อนเขียนค้างไว้ ทำต่อให้จบได้โดยไม่ต้องใช้เน็ต
rem ใช้ reset แทน merge เพราะไฟล์ใหม่ที่เขียนค้างไว้เป็นไฟล์นอก git ซึ่ง merge ไม่ยอมเขียนทับ
rem ทำเฉพาะเมื่อเดินหน้าต่อจาก HEAD ได้ตรง ๆ เหมือน merge --ff-only ไม่อย่างนั้นกลับไปเวอร์ชันเดิมครบชุด
git merge-base --is-ancestor HEAD @{u} >nul 2>nul
if errorlevel 1 goto repairold
git reset --hard --quiet @{u}
if errorlevel 1 exit /b 1
set "_YT_UPDATED=1"
exit /b 0
:repairold
git reset --hard --quiet HEAD
if errorlevel 1 exit /b 1
exit /b 0
