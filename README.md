# YT Toolkit

เครื่องมือจัดการสื่อจากยูทูปที่รันบนเครื่องของคุณ เปิดผ่านเบราว์เซอร์ที่ `http://127.0.0.1:8787`
เอกสาร: [BRD.md](BRD.md) · [PRD.md](PRD.md)

## ติดตั้งบน Windows (ทำครั้งเดียว)
1. ลง Git: เปิด PowerShell แล้ววาง `winget install Git.Git`
2. รับคำเชิญเข้า repo นี้ที่ GitHub
3. วางคำสั่งนี้ใน PowerShell (ครั้งแรกจะเด้งให้ล็อกอิน GitHub ผ่านเบราว์เซอร์)
   ```powershell
   git clone https://github.com/ta-ai-pakorn/yt-toolkit.git "$env:USERPROFILE\YT-Toolkit"
   ```
4. เปิดโฟลเดอร์ `YT-Toolkit` แล้วดับเบิลคลิก `start.bat`

## เปิดและปิดโปรแกรม
- เปิด: ดับเบิลคลิก `start.bat` (อัปเดตเวอร์ชันใหม่ให้เองทุกครั้ง)
- ปิด: ดับเบิลคลิก `stop.bat` หรือคลิกขวาไอคอนสีอำพันที่มุมขวาล่าง → "ปิดโปรแกรม" หรือกดปุ่ม "ปิดโปรแกรม" ในหน้าตั้งค่า
  (บน Windows 11 ถ้าไม่เห็นไอคอน ให้กดลูกศร `^` ที่มุมขวาล่างของแถบงาน ไอคอนอาจซ่อนอยู่ในนั้น)

## สำหรับผู้พัฒนา
```bash
uv sync                                   # ลง dependency รวมชุดเทส
uv run pytest                             # เทส Python
uv run python -m yttoolkit serve --dev    # backend (port 8787)
cd web && npm install && npm run dev      # หน้าเว็บ (port 5173) ต่อกับ backend ข้างบน
cd web && npm test && npm run e2e         # เทสหน้าเว็บ
cd web && npm run build                   # build แล้ว commit web/dist ด้วยทุกครั้ง
```

- เปิด backend (`serve --dev`) ให้เรียบร้อยก่อนสั่ง `npm run dev` ทุกครั้ง เพราะ vite ต่อเข้า backend ตามพอร์ตที่เห็นตอนเริ่มรัน
- ถ้าพอร์ตของ backend เปลี่ยน (เช่น 8787 ถูกใช้อยู่) ให้ปิดแล้วเปิด vite ใหม่
- log ของโปรแกรมอยู่ที่ `run/logs/app.log` ถ้าเปิดไม่ขึ้นให้เปิดไฟล์นี้ดูก่อน
