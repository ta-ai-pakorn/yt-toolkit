# PRD: YT Toolkit v1

> เอกสารความต้องการของผลิตภัณฑ์ (Product Requirements Document)
> เวอร์ชัน 1.0 · 2026-09-28 · เจ้าของ: ธรรมชาติ เฉลิมวงศ์ (พิธ) · สถานะ: รออนุมัติ
> เอกสารคู่กัน: [BRD.md](BRD.md) (เหตุผลทางธุรกิจ, ความต้องการ FR-*, ระบบดีไซน์, บันทึกการตัดสินใจ)

---

## 0. วิธีอ่านเอกสารนี้

- **BRD บอกว่า "ทำอะไร และทำไม"** · **PRD บอกว่า "ทำออกมาหน้าตาแบบไหน ทำงานอย่างไร และรู้ได้อย่างไรว่าเสร็จ"**
- ถ้า PRD กับ BRD ขัดกัน ให้ยึด PRD แล้วแก้ BRD ตาม
- รหัสที่ใช้:

| รหัส | ความหมาย | ตัวอย่าง |
|---|---|---|
| `FR-*` | ความต้องการเชิงฟังก์ชัน (มาจาก BRD ข้อ 5) | FR-SUB-3 |
| `US-*` | User story | US-04 |
| `W*` | หน้าจอ (wireframe) | W2 |
| `AC-*` | เกณฑ์ยอมรับ ต้องเทสได้ทุกข้อ | AC-SUB-03 |
| `E_*` | รหัส error | E_BOT_CHECK |

- คำว่า **ต้อง** = บังคับ · **ควร** = ทำถ้าไม่กระทบกำหนดส่ง · **อาจ** = ทางเลือก

---

## 1. ขอบเขตของ PRD นี้

| รุ่น | ส่งมอบ | ครอบคลุม |
|---|---|---|
| **v1.0** | Windows 10/11 | ทุกข้อในเอกสารนี้ |
| **v1.1** | macOS 13+ (Apple Silicon + Intel) | ทุกข้อในเอกสารนี้ + ข้อ 12 |

v2 (ชุดเครื่องมือสื่อครบวงจร + ชั้น AI) อยู่นอกขอบเขต ดู BRD ข้อ 17

### สมมติฐานที่ใช้เขียนเอกสารนี้
| # | สมมติฐาน | กระทบ | สถานะ |
|---|---|---|---|
| A1 | ทรานสคริปต์อยู่ส่วนล่างสุดของ W2 | W2 | ✅ ยืนยันแล้ว 2026-09-28 |
| A2 | คิวแบบขยายเปิดเป็น Sheet จากด้านล่าง | W4 | ✅ ยืนยันแล้ว 2026-09-28 |
| A3 | จำนวนผู้ใช้ไม่เกิน 20 คน (ทุกคนมีบัญชี GitHub) | การแจกจ่าย | รอยืนยัน |
| A4 | หน้าจอภาษาไทยอย่างเดียว | i18n | รอยืนยัน |

---

## 2. ผู้ใช้และ User story

**ผู้ใช้หลัก:** พนักงานออฟฟิศที่ไม่ใช่สายเทคนิค ใช้คลิปยูทูปทำสไลด์ สื่ออบรม และโพสต์ ใช้แอพเป็นครั้งคราว ไม่ได้เปิดทั้งวัน

| รหัส | ในฐานะพนักงาน ฉันต้องการ... | เพื่อ... | FR |
|---|---|---|---|
| US-01 | วางลิงก์แล้วเห็นภาพรวมของคลิปทันที | รู้ว่าคลิปมีเนื้อหาอะไรโดยไม่ต้องนั่งดู | FR-IN, FR-PROBE, FR-FRAME-1 |
| US-02 | โหลดคลิปเป็น mp4 ที่เปิดได้ทุกโปรแกรม | เอาไปใส่สไลด์หรือโปรแกรมตัดต่อได้เลย | FR-VID |
| US-03 | โหลดแค่เสียง | ฟังเลกเชอร์หรือใช้เสียงประกอบ | FR-AUD |
| US-04 | ได้ซับภาษาไทยที่อ่านง่าย | ใส่ซับในคลิป หรือเอาข้อความไปใช้ต่อ | FR-SUB |
| US-05 | เก็บภาพจากคลิปเป็นภาพเดียวหรือหลายภาพ | ใช้ในสไลด์และเอกสาร | FR-FRAME |
| US-06 | โหลดเฉพาะช่วงที่ต้องการ | ไม่ต้องโหลดทั้งคลิปยาว ๆ | FR-ADV-1 |
| US-07 | โหลดหลายคลิปหรือทั้งเพลย์ลิสต์ในครั้งเดียว | ประหยัดเวลา | FR-IN-2, FR-IN-3, FR-Q |
| US-08 | ปิดแท็บไปทำงานอื่นแล้วงานยังเดินต่อ | ไม่ต้องนั่งเฝ้า | FR-Q-1 |
| US-09 | รู้ทันทีว่าไฟล์อยู่ที่ไหน | เอาไฟล์ไปใช้ต่อได้เลย | FR-OUT-3 |
| US-10 | เข้าใจว่าเกิดอะไรขึ้นเวลามีปัญหา | แก้เองได้ หรือส่งข้อมูลให้ผู้ดูแล | FR-SET-4, BRD ข้อ 13 |
| US-11 | เปิดและปิดโปรแกรมได้ง่ายเหมือนโปรแกรมทั่วไป | ไม่ต้องใช้คำสั่ง | FR-LIFE |

---

## 3. แผนผังหน้าจอและ flow

```
W1 หน้าแรก ──วางลิงก์──► /api/resolve
   │                     ├─ คลิปเดียว ──────────► W2 หน้าผลลัพธ์ (/v/:videoId)
   │                     ├─ เพลย์ลิสต์ / หลายลิงก์ ► W3 เลือกคลิป (/batch)
   │                     └─ มีทั้ง v= และ list= ──► กล่องถาม "คลิปเดียว / ทั้งเพลย์ลิสต์"
   ├─ ประวัติ ──► W5 (/history) ──คลิกแถว──► W2
   └─ ตั้งค่า ──► W6 (/settings)

W4 แถบคิว: ติดล่างทุกหน้า · คลิกเพื่อขยายเป็น Sheet
W7 กล่องยืนยัน / toast / error: ซ้อนบนทุกหน้า
```

| Route | หน้า |
|---|---|
| `/` | W1 |
| `/v/:videoId` | W2 |
| `/batch?src=<resolveId>` | W3 |
| `/history` | W5 |
| `/settings` และ `/settings/health` | W6 |

---

## 4. รายละเอียดหน้าจอ

ทุกหน้าใช้ระบบดีไซน์ Studio Dark (BRD ข้อ 10) และมีสถานะครบ 4 แบบ: **กำลังโหลด / ว่าง / ผิดพลาด / ปกติ**

### W1 หน้าแรก
| ส่วน | คอมโพเนนต์ | พฤติกรรม |
|---|---|---|
| แถบบน | Button (ghost) | ลิงก์ไป W5, W6 |
| ช่องวางลิงก์ | Input Group + Textarea (สูงขึ้นเองได้ถึง 8 บรรทัด) | placeholder `https://youtube.com/watch?v=...` · ปุ่ม **วิเคราะห์** เป็นปุ่มหลักปุ่มเดียวของหน้า |
| คำแนะนำ | Kbd | "กด Ctrl+V ที่ไหนก็ได้" (macOS แสดง ⌘V) |
| ผลการวิเคราะห์ | รายการใต้ช่องวางลิงก์ | ดูหัวข้อ "ผลการวิเคราะห์" ด้านล่าง · ยังไม่ได้กดวิเคราะห์ → ซ่อนส่วนนี้ |
| ล่าสุด | Item × 5 | ปก, ชื่อ, ความยาว · คลิกไป W2 · ไม่มีประวัติ → ซ่อนส่วนนี้ |
| ข้อความเตือนการใช้งาน | ข้อความเล็ก | BRD ข้อ 20 |

**คีย์ลัด:** `Ctrl/⌘+V` นอกช่องกรอก = วางแล้ววิเคราะห์ทันที · `Ctrl/⌘+Enter` ในช่อง = วิเคราะห์ · `Enter` = ขึ้นบรรทัดใหม่

**ผลการวิเคราะห์ (M2):** กด "วิเคราะห์" แล้วหน้าเว็บเรียก `POST /resolve`
- ได้คลิปเดียว → ไป W2 ทันที · ได้ลิงก์เดียวที่เป็นทั้งคลิปและเพลย์ลิสต์ → กล่องถาม (W7) "คลิปนี้" หรือ "ทั้งเพลย์ลิสต์"
- หลายลิงก์หรือเพลย์ลิสต์ → แสดงรายการผลใต้ช่องวางลิงก์ เรียงตามลำดับที่วาง แต่ละแถวมีสถานะกำลังโหลด/ผิดพลาดของตัวเอง
  - คลิป: รหัสคลิป + ลิงก์ "เปิดดู" ไป W2
  - ลิงก์ที่อ่านไม่ออก: ข้อความที่วาง + ข้อความ `E_INVALID_INPUT` สีแดง
  - เพลย์ลิสต์: ชื่อเพลย์ลิสต์, จำนวนคลิป และหมายเหตุ "เลือกคลิปจากเพลย์ลิสต์ได้ในเวอร์ชันถัดไป" (เกิน 200 คลิปบอกว่าแสดงแค่ 200 คลิปแรก)
- ตารางเลือกคลิปแบบเต็ม (W3) มาใน M4

### W2 หน้าผลลัพธ์
เรียงจากบนลงล่าง ส่วนไหนข้อมูลมาก่อน แสดงก่อน ไม่ต้องรอกันทั้งหน้า

| ส่วน | คอมโพเนนต์ | สถานะพิเศษ |
|---|---|---|
| หัวคลิป: ปก, ชื่อ, ช่อง, ความยาว, จำนวน chapter, แทร็กซับที่เลือก | Badge | กำลังโหลด: Skeleton รูปร่างเดียวกัน |
| **ภาพเฟรม** | Card, Aspect Ratio (16:9), Hover Card (ขยาย 1.5 เท่า + timecode), Context Menu, Button Group | กำลังโหลด: Skeleton 6 ช่อง · ไม่มี storyboard: Empty + ปุ่ม "ขอภาพคม" |
| แถวภาพเฟรม | grid 6 คอลัมน์ (จอแคบ 3 คอลัมน์) แสดง 2 แถวแรก ที่เหลือกด "ดูทั้งหมด" | |
| **วิดีโอ** | Select (คุณภาพ), Switch ("ความละเอียดสูงสุด"), Button หลัก "โหลด mp4" | Switch เปิด → Select แสดงตัวเลือก VP9/AV1 พร้อมป้ายเตือน |
| **เสียง** | Toggle Group (m4a แนะนำ / mp3), Select bitrate (แสดงเฉพาะ mp3), Button รอง "โหลดเสียง" | |
| **ซับ** | Select แทร็ก (3 กลุ่มตาม FR-SUB-2), Toggle Group (สั้น/กลาง/ยาว), Collapsible "ปรับเอง" (Slider + Field), กล่อง preview 5 ซับแรก + ตัวนับ, Button Group (.srt .txt .md คัดลอก) | ไม่มีซับ: ซ่อนทั้งส่วน แสดงข้อความ "คลิปนี้ไม่มีซับ" |
| **ตัวเลือกขั้นสูง** (พับไว้) | Collapsible · ช่องเวลาเริ่ม/จบ · Switch "แยกไฟล์ตาม chapter" (ซ่อนถ้าไม่มี chapter) · Switch "ตัดโฆษณา" + รายการหมวด | ค่าในส่วนนี้มีผลกับปุ่มโหลดวิดีโอ เสียง และซับทั้งหมด · เมื่อเปิดใช้ ให้แสดง Badge "ใช้ตัวเลือกขั้นสูงอยู่" ที่หัวส่วนวิดีโอ |
| **ทรานสคริปต์** | Input Group (ค้นหา), Scroll Area (สูงสูงสุด 360px) | คลิกบรรทัด → ไฮไลต์เฟรมที่ใกล้ที่สุดและเลื่อนแถวภาพเฟรมไปหา |

**เมนูคลิกขวาที่ภาพเฟรม (M2):** มี 2 รายการ
- **โหลดภาพนี้** → โหลดไฟล์ภาพเฟรมนั้นชื่อ `frame_HH-MM-SS.jpg` (`/cache/...?download=1`)
- **คัดลอกเวลา** → คัดลอก timecode รูปแบบ `HH:MM:SS` แล้วขึ้น toast "คัดลอกแล้ว"
- "ตั้งจุดเริ่ม/จบ" มาใน M5 และ "ดูซับช่วงนี้" มาใน M3
- เปิดเมนูด้วยคีย์บอร์ดได้ (Shift+F10 หรือปุ่ม Menu) ทุกภาพเฟรมกด Tab ไปถึงได้

**ปุ่มโหลดภาพเฟรมทั้งชุด (M2):** "Contact sheet" และ "โหลดทั้งหมด (.zip)" เป็นปุ่มรอง โหลดผ่านเบราว์เซอร์ตรง ๆ (ไม่เข้าคิว) · M4 ย้ายเข้าคิวงานและบันทึกลงโฟลเดอร์ผลลัพธ์

**กฎปุ่มหลัก:** "โหลด mp4" เป็นปุ่มหลักปุ่มเดียวของ W2 ปุ่มอื่นทั้งหมดเป็นปุ่มรองหรือปุ่มโปร่ง

**เมื่อกดปุ่มโหลดใด ๆ:** สร้างงานเข้าคิวทันที → toast "เพิ่มเข้าคิวแล้ว" → แถบคิวแสดงงานนั้น (ไม่ย้ายหน้า) (ยกเว้น contact sheet และ zip ใน M2 ซึ่งโหลดผ่านเบราว์เซอร์ทันที)

### W3 เลือกคลิป (เพลย์ลิสต์ / หลายลิงก์)
| ส่วน | คอมโพเนนต์ | พฤติกรรม |
|---|---|---|
| หัว | ข้อความ | ชื่อเพลย์ลิสต์หรือ "หลายลิงก์" · จำนวนทั้งหมด · จำนวนที่เลือก |
| ตาราง | @reui/data-grid (row selection + virtualization) | คอลัมน์: ช่องติ๊ก, ปก, ชื่อ, ความยาว · ค่าเริ่มต้นติ๊กทั้งหมด · ลิงก์ที่อ่านไม่ออกแสดงเป็นแถวสีแดงติ๊กไม่ได้ |
| การตั้งค่ารวม | Select (วิดีโอ/เสียง/ไม่เอา), Toggle Group (ซับ: ไม่เอา/.srt/.txt/.md) | ใช้กับทุกคลิปที่เลือก |
| ปุ่มหลัก | Button "ส่งเข้าคิว N คลิป" | N > 20 → Alert Dialog (FR-Q-5) |

### W4 คิวงาน
**แถบล่าง (ย่อ):** แสดงงานที่กำลังทำงานล่าสุด 1 งาน + ตัวนับ "กำลังทำ / รอ / เสร็จ" · ไม่มีงานเลย → ซ่อนแถบ
**Sheet (ขยาย):** รายการงานเรียง: กำลังทำ → รอ → ผิดพลาด → เสร็จ (เสร็จแสดง 20 งานล่าสุด)

| ประเภทแถว | คอมโพเนนต์ | ปุ่ม |
|---|---|---|
| กำลังทำ | Item + Progress + ข้อความ ขั้นตอน · % · ความเร็ว · เวลาที่เหลือ | ยกเลิก |
| รอ | Item + ที่จับลาก (@reui/sortable) | ยกเลิก |
| เสร็จ | Item + ไอคอนติ๊ก | เปิดโฟลเดอร์ · ดาวน์โหลด |
| ผิดพลาด / หยุดกลางคัน | Item + ไอคอน + ข้อความภาษาคน | รายละเอียด · ลองใหม่ |
| พักคิว (เบรกฉุกเฉิน) | Alert ด้านบนของ Sheet และบนแถบล่าง + นาฬิกานับถอยหลัง | ลองต่อเลย |

### W5 ประวัติ
@reui/data-grid · คอลัมน์: ปก, ชื่อคลิป, ไฟล์ที่ได้ (Badge ต่อชนิด), เวลา (แบบ "5 นาทีก่อน") · เรียงล่าสุดก่อน · ค้นหาจากชื่อ · คลิกแถวเปิด W2 จาก cache · ว่าง → Empty "ยังไม่มีประวัติ" + ปุ่มกลับหน้าแรก

### W6 ตั้งค่า + ตรวจสุขภาพระบบ
Tabs 3 แท็บ
- **ทั่วไป** (Field): ค่าทั้งหมดในข้อ 6.4 · บันทึกทันทีเมื่อเปลี่ยน (ไม่มีปุ่มบันทึก) แล้วแสดง toast "บันทึกแล้ว"
- **ตรวจสุขภาพระบบ** (Item + Badge): ffmpeg, yt-dlp (เวอร์ชัน + อายุ), JS runtime, เน็ต, สิทธิ์เขียนโฟลเดอร์, พื้นที่ดิสก์ · แต่ละแถวมีสถานะ พร้อม / เตือน / ใช้ไม่ได้ และปุ่ม "วิธีแก้" · ปุ่ม "ตรวจหาอัปเดต", "ปิดโปรแกรม"
- **เกี่ยวกับ**: เวอร์ชันแอพ, git commit, ลิงก์ README, ข้อความการใช้งานอย่างถูกต้อง

### W7 กล่องยืนยันและการแจ้งเตือน
| กรณี | คอมโพเนนต์ | ข้อความ (ใจความ) | ปุ่ม |
|---|---|---|---|
| ปิดโปรแกรมตอนมีงานค้าง | Alert Dialog | "ปิดโปรแกรมตอนนี้? มีงานค้าง N งาน ถ้าปิดตอนนี้จะหยุดกลางคัน และลองใหม่ได้ทีหลัง" | กลับไปก่อน / ปิดเลย |
| ส่งงานเกิน 20 คลิป | Alert Dialog | "ส่ง N คลิปเข้าคิว? ใช้เวลาประมาณ X นาที ถ้าโหลดเยอะติดกัน ยูทูปอาจขอยืนยันว่าไม่ใช่บอท" | ยกเลิก / ส่งเข้าคิว |
| ลิงก์มีทั้งคลิปและเพลย์ลิสต์ | Dialog | "ลิงก์นี้อยู่ในเพลย์ลิสต์ จะเอาแค่คลิปนี้ หรือทั้งเพลย์ลิสต์?" | คลิปนี้ / ทั้งเพลย์ลิสต์ |
| งานเสร็จ | Toast | "โหลดเสร็จแล้ว · <ชื่อ>" | เปิดโฟลเดอร์ |
| งานผิดพลาด | Toast (ไม่หายเอง) + รายละเอียดในแถวคิว | ข้อความจากข้อ 7 | รายละเอียด |
| เปิด SponsorBlock พร้อมโหลดซับ | ข้อความเตือนใต้ Switch | "เวลาซับจะไม่ตรงกับวิดีโอที่ตัดโฆษณาแล้ว" | — |

---

## 5. เกณฑ์ยอมรับ (Acceptance Criteria)

ทุก AC ต้องมีเทสอย่างน้อยหนึ่งตัว (ระดับเทสอยู่ในวงเล็บ: U=unit, A=API, E=E2E, N=network, M=ตรวจมือ)

### 5.1 รับลิงก์
| AC | เงื่อนไข → ผลที่ต้องได้ | เทส |
|---|---|---|
| AC-IN-01 | ใส่ `https://youtu.be/dQw4w9WgXcQ?t=42` → ได้ videoId `dQw4w9WgXcQ` ชนิด video | U |
| AC-IN-02 | รองรับรูปแบบ watch, youtu.be, shorts, live, m.youtube.com, ID ล้วน 11 ตัว และลิงก์ที่มีพารามิเตอร์อื่นปน | U |
| AC-IN-03 | ใส่ 5 บรรทัด มีซ้ำ 1 บรรทัด ว่าง 1 บรรทัด → ได้ 3 รายการ | U |
| AC-IN-04 | บรรทัดที่ไม่ใช่ยูทูป → รายการนั้นได้ `E_INVALID_INPUT` รายการอื่นทำต่อตามปกติ | U, E |
| AC-IN-05 | ลิงก์ที่มีทั้ง `v=` และ `list=` → ได้ชนิด `ambiguous` และหน้าเว็บแสดง Dialog ตาม W7 | U, E |
| AC-IN-06 | กด Ctrl+V ขณะไม่ได้โฟกัสช่องกรอกใด ๆ และคลิปบอร์ดเป็นลิงก์ยูทูป → เริ่มวิเคราะห์ · ถ้าไม่ใช่ลิงก์ยูทูป → ไม่ทำอะไร | E |
| AC-IN-07 | เพลย์ลิสต์ 250 คลิป → แสดง 200 คลิปแรกพร้อมข้อความว่าจำกัดที่ 200 | A |

### 5.2 ข้อมูลคลิปและภาพเฟรม
| AC | เงื่อนไข → ผลที่ต้องได้ | เทส |
|---|---|---|
| AC-PROBE-01 | วิเคราะห์คลิปเดิมซ้ำภายใน 24 ชม. → ใช้ cache ไม่เรียกยูทูป | A |
| AC-PROBE-02 | คลิปไลฟ์ที่ยังออกอากาศ → `E_LIVE_NOT_READY` | A |
| AC-FRAME-01 | คลิปยาว ≤ 1 ชม. บนเน็ต ≥ 50 Mbps → เฟรมโหมดเร็วแสดงครบภายใน 5 วินาทีนับจากกดวิเคราะห์ | N, M |
| AC-FRAME-02 | ตัด grid ของ storyboard ได้เฟรมตามจำนวนจริง ไม่รวมช่องว่างท้าย grid ที่เกินความยาวคลิป · timecode ของเฟรมที่ i = i × ช่วงห่าง | U |
| AC-FRAME-03 | โหมดคมให้ timecode ชุดเดียวกับโหมดเร็ว ภาพ ≥ 1280 px กว้าง และลบไฟล์วิดีโอชั่วคราวหลังเสร็จ | A |
| AC-FRAME-04 | โหมดคมตั้งช่วงห่างได้ ถ้าช่วงห่างทำให้เกิน 200 เฟรม ระบบปรับช่วงห่างขึ้นให้พอดี 200 และแจ้งผู้ใช้ | U |
| AC-FRAME-05 | contact sheet มี 5 คอลัมน์, timecode ทุกช่อง, หัวภาพมีชื่อคลิปภาษาไทยแสดงถูกต้อง (ไม่เป็นกล่องสี่เหลี่ยม) | U, M |
| AC-FRAME-06 | zip มีไฟล์ชื่อ `frame_HH-MM-SS.jpg` ครบตามจำนวนเฟรม | U |

### 5.3 วิดีโอและเสียง
| AC | เงื่อนไข → ผลที่ต้องได้ | เทส |
|---|---|---|
| AC-VID-01 | ค่าเริ่มต้น → ไฟล์ mp4 ที่ codec ภาพเป็น H.264 (`avc1`) เสียงเป็น AAC ความสูง ≤ 1080 | N (ตรวจด้วย ffprobe) |
| AC-VID-02 | เปิด "ความละเอียดสูงสุด" + เลือก 2160p ในคลิปที่มี 4K → ไฟล์ mp4 ความสูง 2160 | N |
| AC-VID-03 | คลิปที่มีเสียงหลายภาษา → แทร็กเสียงในไฟล์คือแทร็ก original (เทียบ language กับข้อมูลจาก probe) | N |
| AC-VID-04 | ไฟล์ mp4 มีปกและ metadata ชื่อคลิป ช่อง และลิงก์ต้นทาง | N |
| AC-AUD-01 | m4a → ไม่มีการเข้ารหัสใหม่ (codec เป็น AAC ตรงกับต้นฉบับ) | N |
| AC-AUD-02 | mp3 192 → bitrate 192 kbps ± 5% | N |

### 5.4 ซับ
| AC | เงื่อนไข → ผลที่ต้องได้ | เทส |
|---|---|---|
| AC-SUB-01 | คลิปไทยที่มี `th-orig` และ `th` → เลือก `th-orig` อัตโนมัติ | U |
| AC-SUB-02 | ไม่มีทั้งซับเจ้าของและ `*-orig` → ไม่เลือกอะไร และแสดงรายการให้เลือกเอง ซับแปลอัตโนมัติอยู่ในเมนูย่อยพร้อมคำเตือน | U, E |
| AC-SUB-03 | fixture json3 ไทย → ไม่มีบล็อก `aAppend` หลุดเข้ามา ไม่มีซับสองอันที่มีข้อความเหมือนกันติดกัน | U |
| AC-SUB-04 | ทุกซับที่สร้างจาก fixture ไทย เริ่มและจบที่รอยต่อ token เท่านั้น (ต่อ token กลับแล้วได้ข้อความเดิมทุกตัวอักษร) | U |
| AC-SUB-05 | preset "กลาง" → ทุกซับยาว ≤ 25 ตัวอักษร ยกเว้นซับที่มี token เดียวยาวเกิน · ซับที่แสดงสั้นกว่า 1.2 วิ มีได้เฉพาะกรณีที่ถัดไปติดซับอื่นทันที | U |
| AC-SUB-06 | ตัวสร้างซับฝั่ง TS กับฝั่ง Python ให้ผล `.srt` ตรงกันทุกไบต์ ทุก fixture ทุก preset | U (ทั้งสองฝั่ง) |
| AC-SUB-07 | ปรับค่าใน "ปรับเอง" → preview อัปเดตภายใน 200 ms สำหรับคลิปยาว 1 ชม. | E |
| AC-SUB-08 | `.srt` เป็น UTF-8 ไม่มี BOM, ขึ้นบรรทัดแบบ CRLF, เลขลำดับเริ่มที่ 1 ต่อเนื่อง, เวลาไม่ทับกัน | U |
| AC-SUB-09 | ซับที่ไม่มีเวลาระดับคำ ยาว 60 ตัวอักษรไทย ที่ preset กลาง → แตกเป็นซับหลายอันโดยไม่ตัดกลางคำตามผลของ PyThaiNLP | U |
| AC-SUB-10 | เลือกช่วง 01:30-05:00 → ซับแรกเริ่มที่ ≥ 00:00:00 ซับสุดท้ายจบ ≤ 00:03:30 และไม่มีข้อความนอกช่วง | U |
| AC-SUB-11 | json3 ใช้ไม่ได้ → ใช้ vtt แทนโดยอัตโนมัติ ผลลัพธ์ยังผ่าน AC-SUB-03 และ AC-SUB-04 | U |

### 5.5 ตัวเลือกขั้นสูง
| AC | เงื่อนไข → ผลที่ต้องได้ | เทส |
|---|---|---|
| AC-ADV-01 | ช่วง 01:30-05:00 → ความยาววิดีโอ 3:30 ± 0.5 วิ และภาพแรกตรงกับเฟรมที่ 01:30 ของต้นฉบับ (ตัดแบบแม่นยำ ไม่ใช่ตัดตาม keyframe) | N |
| AC-ADV-02 | เวลาเริ่ม ≥ เวลาจบ หรือเกินความยาวคลิป → ปุ่มโหลดยังกดได้ แต่แสดง error ใต้ช่องและไม่สร้างงาน | E |
| AC-ADV-03 | แยก chapter ในคลิปที่มี 5 chapter → ได้ 5 ไฟล์ ชื่อ `01 - <ชื่อ>.mp4` ถึง `05 - <ชื่อ>.mp4` | N |
| AC-ADV-04 | SponsorBlock ในคลิปที่มีข้อมูล sponsor → ความยาวไฟล์ลดลงเท่ากับผลรวมช่วงที่ตัด ± 1 วิ · คลิปที่ไม่มีข้อมูล → ได้คลิปเต็ม และแถวคิวแสดงข้อความตาม FR-ADV-3 | N |

### 5.6 คิวงาน
| AC | เงื่อนไข → ผลที่ต้องได้ | เทส |
|---|---|---|
| AC-Q-01 | ส่ง 5 งาน ที่ค่าพร้อมกัน = 2 → ไม่เคยมีงานสถานะ `running` เกิน 2 งาน | U |
| AC-Q-02 | ระหว่างเริ่มงานที่ต้องต่อยูทูปสองงานติดกัน มีช่วงห่าง 2-5 วิ | U (นาฬิกาปลอม) |
| AC-Q-03 | งานได้ `E_BOT_CHECK` → คิวพัก 10 นาที งานที่รออยู่ไม่เริ่ม มี event `queue.paused` · กด "ลองต่อเลย" → เริ่มต่อทันที | U, A |
| AC-Q-04 | ปิดแท็บ แล้วเปิดใหม่ → เห็นงานทั้งหมดพร้อมสถานะปัจจุบัน | E |
| AC-Q-05 | ปิดโปรแกรมขณะมีงาน `running` → เปิดใหม่ งานนั้นเป็น `interrupted` และลองใหม่ได้ · `work/` ว่าง | A |
| AC-Q-06 | ลากสลับงานที่รออยู่ → ลำดับเริ่มงานเป็นไปตามที่ลาก และคงอยู่หลังรีเฟรช | E |
| AC-Q-07 | ยกเลิกงานที่กำลังโหลด → หยุดภายใน 3 วิ ลบไฟล์ชั่วคราวของงานนั้น | A |
| AC-Q-08 | ความคืบหน้าส่งผ่าน SSE ไม่ถี่กว่า 4 ครั้งต่อวินาทีต่องาน | A |

### 5.7 ไฟล์และประวัติ
| AC | เงื่อนไข → ผลที่ต้องได้ | เทส |
|---|---|---|
| AC-OUT-01 | ชื่อคลิป `ทดสอบ: "A/B" <ภาค 1>?` → ชื่อโฟลเดอร์ไม่มีอักขระต้องห้าม และมี `[<videoId>]` ต่อท้าย | U |
| AC-OUT-02 | ชื่อคลิปยาว 300 ตัวอักษร → path เต็มของไฟล์ยาวไม่เกิน 240 ตัวอักษร | U |
| AC-OUT-03 | โหลดไฟล์ชื่อซ้ำ → ต่อท้าย ` (2)`, ` (3)` ไม่เขียนทับ | U |
| AC-OUT-04 | กด "เปิดโฟลเดอร์" → Explorer/Finder เปิดพร้อมเลือกไฟล์นั้น | M |
| AC-OUT-05 | เปิด W2 ของคลิปจากประวัติขณะไม่มีเน็ต → ข้อมูลคลิปและภาพเฟรมโหมดเร็วยังแสดงจาก cache | E |

### 5.8 เปิด ปิด ตั้งค่า
| AC | เงื่อนไข → ผลที่ต้องได้ | เทส |
|---|---|---|
| AC-LIFE-01 | บัญชีผู้ใช้ใหม่ที่ติดตั้งแค่ Git → clone → ดับเบิลคลิกไฟล์เปิด → เบราว์เซอร์เปิดหน้าแรกภายใน 10 นาที | M |
| AC-LIFE-02 | เปิดครั้งที่สอง (มีของครบแล้ว) → หน้าแรกขึ้นภายใน 5 วิ | M |
| AC-LIFE-03 | กดไฟล์เปิดซ้ำขณะแอพเปิดอยู่ → ไม่มี process ที่สอง เบราว์เซอร์เปิดไปที่ตัวเดิม | A, M |
| AC-LIFE-04 | ปิดได้ทั้ง 3 ทาง ทุกทางผ่าน FR-LIFE-4 เมื่อมีงานค้าง | M |
| AC-LIFE-05 | ไม่มีเน็ตตอนเปิด → `git pull` ล้มเหลวแบบเงียบภายใน 15 วิ แล้วแอพเปิดได้ตามปกติ | M |
| AC-LIFE-06 | port 8787 ถูกใช้ → แอพเปิดที่ 8788 และไฟล์ปิดโปรแกรมยังปิดได้ | A |
| AC-SET-01 | เปลี่ยนค่าตั้งค่า → มีผลทันทีโดยไม่ต้องรีสตาร์ท และคงอยู่หลังรีสตาร์ท | A, E |
| AC-SET-02 | ลบ `bin/ffmpeg*` และปิดการหา ffmpeg ใน PATH (`YT_TOOLKIT_FFMPEG_PATH_LOOKUP=0`) แล้วเปิดแอพ → หน้าตรวจสุขภาพแสดงว่า ffmpeg ใช้ไม่ได้ พร้อมปุ่มโหลดใหม่ ปุ่มที่ต้องใช้ ffmpeg กดแล้วบอกเหตุผล | E |

### 5.9 ความปลอดภัย
| AC | เงื่อนไข → ผลที่ต้องได้ | เทส |
|---|---|---|
| AC-SEC-01 | เซิร์ฟเวอร์ฟังที่ `127.0.0.1` เท่านั้น เครื่องอื่นในวงเดียวกันเชื่อมต่อไม่ได้ | A, M |
| AC-SEC-02 | คำขอที่ `Host` ไม่ใช่ `127.0.0.1:<port>` หรือ `localhost:<port>` → 421 | A |
| AC-SEC-03 | POST/PUT/PATCH/DELETE ที่ไม่มี token หรือ `Origin` ไม่ตรง → 403 | A |
| AC-SEC-04 | ขอไฟล์ด้วย path ที่มี `..` หรือ path นอกโฟลเดอร์ที่อนุญาต → 404 | A |
| AC-SEC-05 | ลิงก์หรือชื่อคลิปที่มี `; & | $()` ไม่ทำให้เกิดการรันคำสั่งใด ๆ | U |

---

## 6. ข้อกำหนดทางเทคนิค

### 6.1 โครงสร้างข้อมูล (SQLite: `data/app.db`)

```sql
CREATE TABLE schema_version (version INTEGER NOT NULL);

CREATE TABLE videos (
  video_id      TEXT PRIMARY KEY,          -- 11 ตัวอักษร
  title         TEXT NOT NULL,
  channel       TEXT,
  duration_s    INTEGER,
  thumbnail_url TEXT,
  chapters_json TEXT,                      -- [{start_s, end_s, title}]
  probe_json    TEXT NOT NULL,             -- ข้อมูลจาก yt-dlp ที่ตัดส่วนไม่ใช้ออกแล้ว
  probed_at     TEXT NOT NULL,             -- ISO 8601
  opened_at     TEXT NOT NULL              -- ใช้ล้าง cache ที่ไม่ได้เปิด 30 วัน
);

CREATE TABLE jobs (
  id            TEXT PRIMARY KEY,          -- UUIDv7
  video_id      TEXT NOT NULL REFERENCES videos(video_id),
  kind          TEXT NOT NULL,             -- video | audio | subtitle | frames_sharp | contact_sheet | frames_zip
  params_json   TEXT NOT NULL,             -- ดูข้อ 6.3
  status        TEXT NOT NULL,             -- queued | running | done | failed | cancelled | interrupted
  stage         TEXT,                      -- probing | downloading_video | downloading_audio | merging | converting | writing
  progress      REAL,                      -- 0..1
  speed_bps     INTEGER,
  eta_s         INTEGER,
  position      INTEGER NOT NULL,          -- ลำดับในคิว (สลับได้เฉพาะ queued)
  error_code    TEXT,                      -- E_*
  error_detail  TEXT,                      -- ข้อความเทคนิคดิบ ใช้ในส่วน "รายละเอียด"
  outputs_json  TEXT,                      -- [{path, size_bytes, kind}]
  created_at    TEXT NOT NULL,
  started_at    TEXT,
  finished_at   TEXT
);
CREATE INDEX jobs_status_position ON jobs(status, position);

CREATE TABLE settings (key TEXT PRIMARY KEY, value_json TEXT NOT NULL);
```

**Cache ของแต่ละคลิป:** `data/cache/<videoId>/` เก็บ `storyboard/*.jpg`, `subs/<track>.json3|.vtt`, `thumb.jpg` · ลบเมื่อไม่ได้เปิดเกิน 30 วัน (ตรวจตอนเปิดโปรแกรม)

**การเปลี่ยนสถานะงาน** (อย่างอื่นนอกจากนี้ถือเป็นบั๊ก)
```
queued ──► running ──► done
   │          ├──────► failed ──(ลองใหม่)──► queued
   │          ├──────► cancelled
   │          └─(แอพปิด)► interrupted ──(ลองใหม่)──► queued
   └──(ยกเลิก)──► cancelled
```

### 6.2 API

- Base: `http://127.0.0.1:<port>/api` · รับส่ง JSON (UTF-8)
- **Token:** เซิร์ฟเวอร์ใส่ token ลงใน `<meta name="yt-token">` ของ `index.html` ตอนเสิร์ฟ หน้าเว็บส่งกลับใน header `X-Toolkit-Token` ทุกคำขอที่ไม่ใช่ GET
- **Sec-Fetch-Site:** คำขอ /api ที่ Sec-Fetch-Site เป็น cross-site หรือ same-site ถูกปฏิเสธ 403 (`E_FORBIDDEN`) ทุก method เพราะ GET บางตัวมีผลข้างเคียง (probe ยูทูป เขียนประวัติ ทำภาพ) · ไม่มี header นี้ หรือเป็น same-origin / none ผ่านได้
- **รูปแบบ error:** `{"error": {"code": "E_...", "message": "<ข้อความภาษาไทย>", "detail": "<ข้อความเทคนิค>"}}`

| Method | Path | Body / Query | ตอบกลับ |
|---|---|---|---|
| GET | `/ping` | — | `{ok:true, pid}` ตอบทันที ใช้เช็คว่าแอพยังทำงานอยู่ (ไฟล์เปิด/ปิดโปรแกรมและ dev server ใช้ตัวนี้) |
| GET | `/health` | — | `{version, commit, tools:{ffmpeg, ytdlp, jsRuntime}, disk, output, network}` ทุกตัวเป็น `ToolStatus = {status: ok\|warn\|error, name, version, message, path}` (ใช้เวลาได้ถึง 5 วิเพราะเช็คเน็ต) |
| POST | `/resolve` | `{text}` (ไม่เกิน 20,000 ตัวอักษร) | `{resolveId, items:[{input, kind: video\|playlist\|ambiguous\|invalid, videoId?, playlistId?, error?}]}` เรียงตามลำดับที่วาง · `error` มีเฉพาะแถว invalid = `{code:"E_INVALID_INPUT", message}` · `resolveId` ยังไม่เก็บลงฐานข้อมูล (W3 ใช้ใน M4) |
| GET | `/videos/{id}` | `?refresh=1` | `VideoInfo` (ข้อ 6.2.1) · probe ใหม่ถ้าไม่มี cache หรือขอ refresh · id ผิดรูปแบบ → 422 `E_INVALID_INPUT` |
| GET | `/videos/{id}/storyboard` | — | `{intervalMs, frames:[{index, tMs, url}]}` · `url` = `/api/cache/{id}/storyboard/f_NNNN.jpg?v=<เวลาที่สร้างชุดภาพ>` (ภาพชุดใหม่ได้ URL ใหม่) |
| GET | `/videos/{id}/storyboard/contact-sheet.jpg` | — | ไฟล์ JPEG (Content-Disposition: attachment) ชื่อ `<ชื่อคลิป> - contact sheet.jpg` (ชื่อภาษาไทยส่งใน `filename*` ตาม RFC 5987 ชื่อสำรอง `contact-sheet.jpg`) |
| GET | `/videos/{id}/storyboard/frames.zip` | — | ไฟล์ zip (Content-Disposition: attachment) ชื่อ `<ชื่อคลิป> - frames.zip` ข้างในเป็น `frame_HH-MM-SS.jpg` |
| GET | `/videos/{id}/subtitles` | — | `{tracks:[{id, lang, name, group: owner\|original\|translated}], defaultTrackId?}` |
| GET | `/videos/{id}/subtitles/{trackId}/tokens` | — | `{hasWordTiming, tokens:[{t, s, e}]}` (t=ข้อความ, s/e=ms) |
| GET | `/playlists/{id}` | — | `{title, total, truncated, entries:[{videoId, title, durationS?, thumbnailUrl}]}` สูงสุด 200 คลิป |
| POST | `/jobs` | `{items:[{videoId, kind, params}]}` | `{jobs:[Job]}` |
| GET | `/jobs` | `?status=&limit=` | `{jobs:[Job]}` |
| POST | `/jobs/{id}/cancel` | — | `Job` |
| POST | `/jobs/{id}/retry` | — | `Job` |
| PUT | `/jobs/order` | `{ids:[...]}` (เฉพาะ queued) | `{ok:true}` |
| POST | `/queue/resume` | — | `{ok:true}` |
| POST | `/tools/ffmpeg/install` | — | `ToolStatus` ของ ffmpeg หลังติดตั้ง · ล้มเหลว → `E_TOOL_INSTALL_FAILED` |
| GET | `/jobs/{id}/outputs/{n}` | — | ไฟล์ (Content-Disposition: attachment) |
| POST | `/jobs/{id}/outputs/{n}/reveal` | — | `{ok:true}` เปิด Explorer/Finder |
| GET | `/cache/{videoId}/{path}` | `?download=1` (ไม่บังคับ) | ไฟล์ภาพใน cache (ภาพเฟรม, ปก) เฉพาะที่อยู่ใต้ `data/cache/<videoId>/` · path ที่มี `..`, `\`, `:` หรือขึ้นต้นด้วย `/` หรือตัวพิมพ์เล็ก/ใหญ่ไม่ตรงชื่อจริง → 404 (AC-SEC-04) · ภาพเฟรมมี `Cache-Control: public, max-age=86400, immutable` · `?download=1` → attachment ชื่อ `frame_HH-MM-SS.jpg` |
| GET | `/history` | `?q=&limit=&offset=` (`limit` ค่าเริ่มต้น 20 สูงสุด 100) | `{items:[{videoId, title, thumbnailUrl, durationS, outputs:[kind], lastAt}], total}` |
| GET | `/diagnostics` | `?jobId=` (ไม่บังคับ) | `{text}` รายงานแจ้งปัญหาแบบ Markdown ตามข้อ 7.1 |
| GET | `/settings` | — | `Settings` |
| PATCH | `/settings` | บางส่วนของ `Settings` | `Settings` |
| POST | `/update` | — | `{updated, restarting}` |
| POST | `/shutdown` | `{force?: bool}` | 200 `{ok}` หรือ 409 `{pendingJobs}` ถ้ามีงานค้างและไม่ force |
| GET | `/events` | — | SSE (ข้อ 6.2.2) |

- **contact sheet และ zip ใน M2** ทำตอนขอแล้วส่งให้เบราว์เซอร์โหลดทันที · M4 ย้ายเข้าคิวเป็นงานชนิด `contact_sheet` / `frames_zip` และบันทึกลงโฟลเดอร์ผลลัพธ์
- **HTTP status ของ error จากยูทูป:** `E_INVALID_INPUT` 422 · `E_VIDEO_UNAVAILABLE`, `E_VIDEO_PRIVATE`, `E_NO_STORYBOARD` 404 · `E_LIVE_NOT_READY`, `E_AGE_RESTRICTED`, `E_GEO_BLOCKED` 409 · `E_BOT_CHECK` 429 · `E_NETWORK` 502 · รหัสอื่น (`E_UNKNOWN`) 500

#### 6.2.1 ชนิดข้อมูลหลัก
```ts
type VideoInfo = {
  videoId: string; title: string; channel: string; durationS: number;
  publishedAt?: string; thumbnailUrl: string;
  chapters: { startS: number; endS: number; title: string }[];
  video: { formatId: string; height: number; fps: number; vcodec: string;
           compat: boolean; sizeBytes?: number }[];      // compat = H.264 เปิดได้ทุกที่
  audio: { formatId: string; language?: string; isOriginal: boolean;
           acodec: string; abrKbps?: number }[];
  hasStoryboard: boolean; isLive: boolean;
};

type Job = {
  id: string; videoId: string; title: string; kind: JobKind; params: JobParams;
  status: JobStatus; stage?: string; progress?: number; speedBps?: number; etaS?: number;
  position: number; error?: { code: string; message: string; detail?: string };
  outputs?: { index: number; name: string; sizeBytes: number }[];
  createdAt: string; finishedAt?: string;
};
```

#### 6.2.2 SSE (`/events`)
| event | data | เมื่อไร |
|---|---|---|
| `job.created` | `Job` | สร้างงาน |
| `job.updated` | `Job` (เฉพาะฟิลด์ที่เปลี่ยน + `id`) | เปลี่ยนสถานะหรือความคืบหน้า (ไม่เกิน 4 ครั้ง/วิ/งาน) |
| `queue.paused` | `{until, reason}` | เบรกฉุกเฉิน |
| `queue.resumed` | `{}` | กลับมาทำงาน |
| `app.shutdown` | `{}` | กำลังปิดโปรแกรม (หน้าเว็บแสดง "ปิดโปรแกรมแล้ว") |

ส่ง comment `: ping` ทุก 15 วิ · หน้าเว็บต่อใหม่อัตโนมัติ แล้วดึง `/jobs` ใหม่ทั้งชุดหลังต่อสำเร็จ

### 6.3 พารามิเตอร์ของงาน และวิธีทำงาน

| kind | params | วิธีทำงาน |
|---|---|---|
| `video` | `{formatId?, maxQuality: bool, range?: {startS, endS}, splitChapters: bool, sponsorblock?: string[]}` | ดูข้อ 6.3.1 |
| `audio` | `{format: m4a\|mp3, mp3Kbps?: 128\|192\|320, range?, splitChapters, sponsorblock?}` | m4a: ดึงแทร็ก AAC ต้นฉบับไม่เข้ารหัสใหม่ · mp3: เข้ารหัสด้วย ffmpeg ตาม bitrate |
| `subtitle` | `{trackId, format: srt\|txt\|md, options: SubOptions, range?}` | ใช้ `srt_builder` (BRD ข้อ 12) แล้วเขียนไฟล์ลงโฟลเดอร์ผลลัพธ์ |
| `frames_sharp` | `{intervalS?}` | โหลดภาพอย่างเดียว ≤ 720p ลง `work/` → ffmpeg ดึงเฟรม JPG → ลบวิดีโอ |
| `contact_sheet` | `{source: fast\|sharp, columns: 5}` | Pillow ประกอบภาพ + ฟอนต์ IBM Plex Sans Thai (ฝังในแอพ) |
| `frames_zip` | `{source: fast\|sharp}` | zip ภาพเฟรม |

```ts
type SubOptions = { maxChars: number; lines: 1 | 2; minMs: number; maxMs: number;
                    mode: "chars" | "tokens"; tokensPerCue?: number };
```

#### 6.3.1 การเลือก format (จุดเริ่มต้น ต้องยืนยันด้วย network test ใน M4)
- **เปิดได้ทุกที่ (ค่าเริ่มต้น):** `bv*[vcodec^=avc1][height<=1080]+ba[acodec^=mp4a]/b[ext=mp4]` ใส่ใน mp4
- **ความละเอียดสูงสุด:** `bv*+ba/b` ใส่ใน mp4 (`merge_output_format=mp4`)
- **เลือกคุณภาพเอง:** ใช้ `formatId` ที่ผู้ใช้เลือก + เสียงตามกฎด้านล่าง
- **เสียงต้นฉบับ:** เลือกแทร็กที่ `isOriginal` ก่อนเสมอ (คำนวณจาก probe: format_note มีคำว่า original หรือ default, หรือ language_preference สูงสุด) · ถ้า probe ระบุไม่ได้ ใช้ลำดับค่าเริ่มต้นของ yt-dlp
- **โหลดเฉพาะช่วง:** `download_ranges` + `force_keyframes_at_cuts=True` เพื่อให้ตัดแม่นยำ (ช้ากว่าเพราะต้องเข้ารหัสใหม่ แต่ช่วงสั้นจึงรับได้)
- **แยก chapter:** postprocessor `FFmpegSplitChapters` + `force_keyframes`
- **SponsorBlock:** `sponsorblock_remove=<หมวด>` ผ่าน postprocessor ModifyChapters

### 6.4 ค่าตั้งค่า (Settings) และค่าเริ่มต้น
| key | ชนิด | ค่าเริ่มต้น |
|---|---|---|
| `outputDir` | string | `<Downloads>/YT-Toolkit` |
| `videoDefault` | `compat-1080` \| `compat-720` \| `max` | `compat-1080` |
| `audioDefault` | `m4a` \| `mp3` | `m4a` |
| `mp3Kbps` | 128 \| 192 \| 320 | 192 |
| `subPreset` | `short` \| `medium` \| `long` \| `custom` | `medium` |
| `subCustom` | SubOptions | ค่าของ medium |
| `concurrency` | 1 \| 2 \| 3 | 2 |
| `sponsorblockDefault` | string[] | `["sponsor","selfpromo","interaction"]` |
| `theme` | `system` \| `dark` \| `light` | `system` |
| `lastUsed` | object | ค่าที่เลือกล่าสุดใน W2 (แพทเทิร์น UX ข้อ 6 ของ BRD ข้อ 10.8) |

### 6.5 Frontend
| หัวข้อ | เลือก |
|---|---|
| สร้างโปรเจกต์ | `npx shadcn@latest init` เทมเพลต Vite · **Base UI** (ค่าเริ่มต้น) · TypeScript |
| Preset | บันทึก Studio Dark เป็น shadcn preset ใน repo (สี, ฟอนต์, มุมโค้ง, ไอคอน Lucide) |
| คอมโพเนนต์ @shadcn | Button, Button Group, Input Group, Textarea, Kbd, Toggle Group, Select, Switch, Slider, Field, Collapsible, Card, Aspect Ratio, Hover Card, Context Menu, Scroll Area, Skeleton, Spinner, Progress, Sheet, Item, Badge, Alert, Alert Dialog, Dialog, Toast (sonner), Tabs, Empty, Tooltip |
| คอมโพเนนต์เสริม | `@reui/data-grid` (W3, W5), `@reui/sortable` (W4) |
| ห้ามใช้ | Magic UI, Aceternity, Animate UI (ขัดกับ calm design) |
| Routing | React Router (library mode) |
| ข้อมูลจากเซิร์ฟเวอร์ | TanStack Query · SSE อัปเดต cache ของ Query โดยตรง |
| ฟอนต์ | `@fontsource/ibm-plex-sans-thai`, `@fontsource/ibm-plex-mono` (self-host) |
| ข้อความ | รวมไว้ที่ `web/src/i18n/th.ts` ไฟล์เดียว ห้ามเขียนข้อความในคอมโพเนนต์ตรง ๆ |
| ตัวสร้างซับ | `web/src/lib/srt-builder.ts` พอร์ตจาก Python ผ่าน fixture ชุดเดียวกัน (AC-SUB-06) |
| ขนาด bundle | JS หลังบีบอัด ≤ 400 KB (ไม่นับฟอนต์) |

### 6.6 โครงสร้างฝั่ง backend
ตาม BRD ข้อ 8 · เพิ่มกฎ:
- `core/` ห้าม import `api/` หรือ `platform/` โดยตรง ให้รับของที่ต้องใช้ผ่านพารามิเตอร์
- โหมด `YT_TOOLKIT_FAKE=1`: แทน yt-dlp และ ffmpeg ด้วยตัวปลอมที่อ่านจาก `tests/fixtures/` ใช้กับ E2E และการพัฒนาหน้าเว็บโดยไม่ต้องต่อเน็ต

---

## 7. รหัส error และข้อความ

| รหัส | ข้อความถึงผู้ใช้ | ระบบทำอะไร |
|---|---|---|
| `E_INVALID_INPUT` | ลิงก์นี้ไม่ใช่ลิงก์ยูทูป ลองคัดลอกจากแถบที่อยู่ของเบราว์เซอร์อีกครั้ง | ทำรายการอื่นต่อ |
| `E_BOT_CHECK` | ยูทูปขอให้ยืนยันว่าไม่ใช่บอท พักคิวไว้ 10 นาทีก่อนนะ | เบรกฉุกเฉิน |
| `E_VIDEO_PRIVATE` | คลิปนี้เป็นส่วนตัว เจ้าของต้องเปิดเป็นสาธารณะก่อน | งานล้มเหลว |
| `E_VIDEO_UNAVAILABLE` | คลิปนี้ถูกลบหรือไม่มีแล้ว | งานล้มเหลว |
| `E_GEO_BLOCKED` | คลิปนี้ดูในประเทศไทยไม่ได้ | งานล้มเหลว |
| `E_AGE_RESTRICTED` | คลิปนี้จำกัดอายุ ต้องล็อกอินถึงจะโหลดได้ ซึ่งเวอร์ชันนี้ยังไม่รองรับ | งานล้มเหลว |
| `E_LIVE_NOT_READY` | คลิปนี้ยังถ่ายทอดสดอยู่หรือยังไม่เผยแพร่ ลองใหม่หลังจบไลฟ์ | งานล้มเหลว |
| `E_NO_SUBTITLES` | คลิปนี้ไม่มีซับ | ไม่นับเป็น error ในหน้าจอ |
| `E_NO_STORYBOARD` | คลิปนี้ไม่มีภาพตัวอย่างแบบเร็ว กด "ขอภาพคม" แทนได้ | แสดงปุ่มโหมดคม |
| `E_FFMPEG_MISSING` | ยังไม่มีโปรแกรมแปลงไฟล์ (ffmpeg) กด "โหลดใหม่" ในหน้าตรวจสุขภาพ | ปิดฟีเจอร์ที่ต้องใช้ |
| `E_JS_RUNTIME_MISSING` | บางคุณภาพอาจไม่แสดง เพราะเครื่องยังไม่มีตัวช่วยที่ yt-dlp ต้องใช้ | เตือนในหน้าตรวจสุขภาพ |
| `E_DISK_FULL` | พื้นที่ไม่พอ ต้องมีว่างอย่างน้อย <ขนาด> | ไม่เริ่มงาน |
| `E_NETWORK` | เน็ตหลุด กำลังลองใหม่ (ครั้งที่ n/3) | ลองใหม่อัตโนมัติ 3 ครั้ง (รอ 2, 5, 10 วิ) |
| `E_OUTPUT_NOT_WRITABLE` | บันทึกลงโฟลเดอร์นี้ไม่ได้ ลองเปลี่ยนโฟลเดอร์ในหน้าตั้งค่า | งานล้มเหลว |
| `E_INTERRUPTED` | งานหยุดกลางคันเพราะปิดโปรแกรม | รอผู้ใช้กดลองใหม่ |
| `E_TOOL_INSTALL_FAILED` | โหลดโปรแกรมที่ต้องใช้ไม่สำเร็จ ตรวจเน็ตแล้วกด "โหลด ffmpeg ใหม่" อีกครั้ง | คงสถานะเดิม |
| `E_FORBIDDEN` | คำขอนี้ไม่ได้รับอนุญาต ลองรีเฟรชหน้าเว็บ | ตอบ 403 (NFR-SEC-3) |
| `E_OFFLINE` | เชื่อมต่อโปรแกรมไม่ได้ ถ้าปิดโปรแกรมไปแล้ว เปิดใหม่ด้วย start.bat | ฝั่งหน้าเว็บ: เชื่อมต่อ backend ไม่ได้ |
| `E_UNKNOWN` | มีบางอย่างผิดพลาด ถ่ายภาพหน้าจอนี้ส่งให้ผู้ดูแล | งานล้มเหลว · M6 เปลี่ยนเป็นปุ่ม "คัดลอกข้อมูลแจ้งปัญหา" |
| `E_NOT_FOUND` | ไม่พบสิ่งที่ขอ | ตอบ 404 (path ที่ไม่มีใน API) |
| `E_BAD_REQUEST` | ข้อมูลที่ส่งมาไม่ถูกต้อง ลองรีเฟรชหน้าเว็บ | ตอบ 422 (ข้อมูลไม่ผ่านการตรวจ) · HTTP error อื่นใช้ข้อความเดียวกันกับรหัส `E_HTTP_<status>` |

หมายเหตุ `E_NETWORK`: จุดที่ไม่ได้ลองใหม่อัตโนมัติ (เช่นหน้าผลลัพธ์ใน M2) ใช้ข้อความ "เน็ตหลุด ลองใหม่อีกครั้ง" แทน ข้อความที่มีตัวนับ (ครั้งที่ n/3) ใช้เมื่อคิวงานใน M4 เป็นผู้ลองใหม่

`errors.py` ต้องแปลงข้อความของ yt-dlp เป็นรหัสเหล่านี้ด้วยชุดทดสอบจากข้อความ error จริงที่เก็บไว้ใน `tests/fixtures/errors/`

### 7.1 error สองชั้นและรายงานแจ้งปัญหา (FR-SET-5)

| ชั้น | ใครอ่าน | มีอะไร |
|---|---|---|
| **หน้าเว็บ** | พนักงาน | `message` ภาษาไทยจากตารางข้างบน + ส่วน "รายละเอียด" ที่พับไว้ (รหัส error + `detail` ข้อความเทคนิคดิบ) |
| **log** | ผู้ดูแล / AI | `run/logs/app.log` ทุก error มีเวลา, รหัส error, job id และ traceback · หมุนไฟล์ที่ 5 MB เก็บ 3 ไฟล์ |

**ปุ่ม "คัดลอกข้อมูลแจ้งปัญหา"** อยู่ในส่วน "รายละเอียด" ของ error ทุกจุด และในหน้าตรวจสุขภาพระบบ เรียก `GET /api/diagnostics` แล้วคัดลอกข้อความนี้ลงคลิปบอร์ด:

```markdown
## รายงานปัญหา YT Toolkit
- เวลา: 2026-10-05 14:32 (+07:00)
- แอพ: 0.1.0 (commit abc1234) · ระบบ: Windows 11 (10.0.26200)
- yt-dlp: 2026.09.20 · ffmpeg: 8.1 · JS runtime: deno 2.9.7
### error
- รหัส: E_BOT_CHECK · งาน: video (videoId dQw4w9WgXcQ)
- รายละเอียด: <detail>
### log ล่าสุด (50 บรรทัด)
```text
<บรรทัด log>
```
```

- path ที่มีชื่อผู้ใช้ในรายงานต้องแทนด้วย `~` (เช่น `C:\Users\somchai\Downloads` → `~\Downloads`) เพื่อไม่ให้ข้อมูลส่วนตัวหลุด
- ไม่ใส่ token ของแอพในรายงาน

| AC | เงื่อนไข → ผลที่ต้องได้ | เทส |
|---|---|---|
| AC-SET-03 | error ที่เกิดจากงานใด ๆ → มีบรรทัดใน `app.log` ที่มีรหัส error และ job id | A |
| AC-SET-04 | `/api/diagnostics?jobId=` → มีครบทุกหัวข้อตามตัวอย่าง ไม่มีชื่อผู้ใช้ใน path และไม่มี token | A |
| AC-SET-05 | กด "คัดลอกข้อมูลแจ้งปัญหา" → คลิปบอร์ดได้ข้อความรายงาน และมี toast "คัดลอกแล้ว" | E |

---

## 8. ข้อกำหนดที่ไม่ใช่ฟังก์ชัน (สรุปเป็นตัวเลข)

| หัวข้อ | ค่าที่ต้องได้ | วัดอย่างไร |
|---|---|---|
| เปิดครั้งแรก | ≤ 10 นาที | AC-LIFE-01 |
| เปิดครั้งถัดไป | ≤ 5 วิ | AC-LIFE-02 |
| ภาพเฟรมโหมดเร็ว | ≤ 5 วิ | AC-FRAME-01 |
| preview ซับ | ≤ 200 ms | AC-SUB-07 |
| RAM ตอนไม่มีงาน | ≤ 300 MB (backend + หน้าเว็บ 1 แท็บ) | วัดด้วย Task Manager / Activity Monitor |
| Contrast | WCAG AA ทั้งสองธีม | axe ใน E2E |
| คีย์บอร์ด | ใช้ W1-W7 ได้ครบโดยไม่ใช้เมาส์ | E2E |

---

## 9. แผนการทดสอบ

| ระดับ | เครื่องมือ | รันเมื่อไร | ครอบคลุม |
|---|---|---|---|
| Unit (Python) | pytest | ทุก push · Windows + macOS | AC ที่ติด U |
| Unit (หน้าเว็บ) | Vitest | ทุก push | srt-builder, การแปลงเวลา, ตัวแยกลิงก์ฝั่งหน้าเว็บ |
| API | pytest + TestClient + โหมด FAKE | ทุก push | AC ที่ติด A, ความปลอดภัยทั้งหมด |
| E2E | Playwright + โหมด FAKE + axe | ทุก push | AC ที่ติด E, ทั้งธีมมืดและสว่าง |
| Network | pytest `-m network` | รันเองก่อนปิดแต่ละ milestone | AC ที่ติด N |
| ตรวจมือ | checklist ใน `docs/acceptance.md` | ก่อนส่งมอบ v1.0 / v1.1 | AC ที่ติด M |

**ชุดคลิปสำหรับ network test** (เก็บเป็นรายการ ID ใน `tests/network_videos.toml`): คลิปไทยสั้นมี `th-orig`, คลิปมีเสียงพากย์หลายภาษา, คลิปมี chapter ≥ 3, คลิปมีข้อมูล SponsorBlock, คลิปไม่มีซับ, คลิปมี 4K, เพลย์ลิสต์ ≤ 10 คลิป

**Fixture ที่ต้องเก็บก่อนเริ่ม M3:** json3 ไทย (มี `aAppend`), json3 อังกฤษ, vtt อัตโนมัติ, ซับของเจ้าของคลิป (ไม่มีเวลาระดับคำ), storyboard 1 ชุด, ข้อความ error จริงของ yt-dlp อย่างน้อยรหัสละ 1 ตัว

---

## 10. Milestone และนิยามคำว่า "เสร็จ"

| Milestone | ส่งมอบ | AC ที่ต้องผ่าน |
|---|---|---|
| **M1 โครงพื้นฐาน** | repo private, `pyproject`, ไฟล์เปิด/ปิด Windows, `platform/` (มีโครง macOS), เปิดได้ตัวเดียว, tray, middleware ความปลอดภัย, ffmpeg + JS runtime, `/health`, W6 แท็บตรวจสุขภาพ, shadcn init + preset Studio Dark, W1 เปล่า, CI Windows + macOS | AC-LIFE-01..06, AC-SEC-01..04, AC-SET-02 |
| **M2 ดูก่อนโหลด** | `/resolve`, `/videos`, `/storyboard`, W1 เต็ม, W2 ส่วนหัวและภาพเฟรม, contact sheet, zip | AC-IN-*, AC-PROBE-*, AC-FRAME-01, 02, 05, 06 |
| **M3 ซับ** | fixture, subtitles, srt_builder (Python + TS), W2 ส่วนซับและทรานสคริปต์ | AC-SUB-* (ยกเว้น 10) |
| **M4 โหลดและคิว** | video, audio, คิว, SSE, W3, W4, W5, W7 | AC-VID-*, AC-AUD-*, AC-Q-*, AC-OUT-*, AC-SEC-05 |
| **M5 ขั้นสูง** | ช่วงเวลา, chapter, SponsorBlock, โหมดคม | AC-ADV-*, AC-SUB-10, AC-FRAME-03, 04 |
| **M6 → v1.0** | error ครบตามข้อ 7 รวม error สองชั้นและรายงานแจ้งปัญหา (ข้อ 7.1), a11y, README Windows, GitHub Actions | ทุก AC บน Windows + ตัวเลขในข้อ 8 |
| **M7 → v1.1** | `platform/macos.py`, `.command`, ffmpeg สำหรับ Mac, README macOS | ทุก AC บน macOS + ข้อ 12 |

**นิยามคำว่า "เสร็จ" ของทุกงาน**
1. AC ที่เกี่ยวข้องมีเทสและผ่าน
2. CI ผ่านทั้ง Windows และ macOS
3. ข้อความในหน้าจออยู่ใน `th.ts` และผ่านแนวการเขียนข้อความใน BRD ข้อ 10.9
4. มีครบทั้ง 4 สถานะ (กำลังโหลด / ว่าง / ผิดพลาด / ปกติ)
5. ไม่มี TODO ค้างในโค้ดที่ merge

---

## 11. ตารางโยงความต้องการ

| FR (BRD) | หน้าจอ | API | AC |
|---|---|---|---|
| FR-IN-1..6 | W1, W3, W7 | `/resolve`, `/playlists/{id}` | AC-IN-01..07 |
| FR-PROBE-1..3 | W2 | `/videos/{id}` | AC-PROBE-01..02 |
| FR-FRAME-1..6 | W2 | `/storyboard`, `/jobs` (frames_*, contact_sheet) | AC-FRAME-01..06 |
| FR-VID-1..6 | W2, W3 | `/jobs` (video) | AC-VID-01..04 |
| FR-AUD-1..4 | W2, W3 | `/jobs` (audio) | AC-AUD-01..02 |
| FR-SUB-1..10 | W2 | `/subtitles`, `/tokens`, `/jobs` (subtitle) | AC-SUB-01..11 |
| FR-ADV-1..4 | W2, W7 | `/jobs` (params) | AC-ADV-01..04, AC-SUB-10 |
| FR-Q-1..8 | W4, W7 | `/jobs*`, `/queue/resume`, `/events` | AC-Q-01..08 |
| FR-OUT-1..5 | W2, W4, W5 | `/outputs`, `/reveal`, `/history` | AC-OUT-01..05 |
| FR-SET-1..4 | W6 | `/settings`, `/health`, `/update` | AC-SET-01..02 |
| FR-LIFE-1..7 | W6, W7 | `/shutdown` | AC-LIFE-01..06 |
| NFR-SEC-1..6 | — | middleware | AC-SEC-01..05 |

---

## 12. ส่วนเพิ่มของ v1.1 (macOS)

| หัวข้อ | ข้อกำหนด | AC |
|---|---|---|
| ไฟล์เปิด/ปิด | `start.command`, `stop.command` มีสิทธิ์ execute ใน git · เปิดแอพแบบแยก process แล้วปิดหน้าต่าง Terminal เอง | AC-MAC-01: ดับเบิลคลิกแล้วแอพเปิด หน้าต่าง Terminal ปิดภายใน 10 วิ |
| menu bar | pystray ที่ main thread, uvicorn ใน thread แยก | AC-MAC-02: ไอคอนแสดงที่ menu bar และเมนูครบตาม FR-LIFE-6 |
| เปิดโฟลเดอร์ | `open -R <file>` | AC-OUT-04 บน macOS |
| ffmpeg | แหล่งที่มี Apple Silicon + Intel พร้อม checksum (ตัดสินใจเมื่อเริ่ม M7) | AC-MAC-03: เครื่อง Apple Silicon และ Intel ได้ ffmpeg ที่ตรงสถาปัตยกรรม |
| คีย์ลัด | แสดง ⌘ แทน Ctrl ทุกที่ | AC-MAC-04: ตรวจด้วย E2E ที่จำลอง platform เป็น macOS |
| Git | README สอนลง Command Line Tools | AC-LIFE-01 บน macOS |

---

## 13. คำถามที่ยังเปิดอยู่

| # | คำถาม | ต้องตอบก่อน | ค่าที่ใช้ถ้ายังไม่ตอบ |
|---|---|---|---|
| Q1 | ผู้ใช้จริงประมาณกี่คน | M6 | ≤ 20 คน (A3) |
| ~~Q2~~ | ~~ย้ายทรานสคริปต์ขึ้นไปข้างภาพเฟรมไหม~~ | — | ปิดแล้ว: อยู่ล่างสุด (A1) |
| ~~Q3~~ | ~~คิวแบบขยายเป็น Sheet หรือแผงข้าง~~ | — | ปิดแล้ว: Sheet (A2) |
| ~~Q4~~ | ~~ได้ deno ผ่าน uv บนทั้งสองระบบไหม~~ | — | ปิดแล้ว: ได้ ทดสอบบน Windows 2026-09-28 (PyPI `deno` 2.9.7, yt-dlp รายงาน `JS runtimes: deno-2.9.7`) · macOS ยืนยันใน CI ของ M1 |
| Q5 | แหล่ง ffmpeg สำหรับ macOS | M7 | ffmpeg ที่ผู้ใช้มีใน PATH |
