# tests/fixtures

ข้อมูลที่ `FakeExtractor` (`src/yttoolkit/core/extractor.py`) และเทสใช้แทนการต่อยูทูปจริง
ดึงเมื่อ 2026-09-29 ด้วย yt-dlp 2026.08.19 (`yt-dlp[default]` + deno จาก PyPI) บน Windows 11
สคริปต์ที่ใช้ดึงเป็นสคริปต์ทิ้ง ไม่ได้ commit ไว้

## probe/
ผล `extract_info(download=False)` ที่ตัดให้เหลือเฉพาะฟิลด์ที่แอพอ่าน

- `aqz-KE-bpKQ.json`: ข้อมูลจริงของ Big Buck Bunny (635 วินาที, storyboard sb0..sb3)
- `jNQXAC9IVRw.json`: ข้อมูลจริงของ "Me at the zoo" (19 วินาที, ไม่มี storyboard, มี chapters)
- `live_upcoming.json`: ข้อมูลสังเคราะห์ `live_status: is_upcoming` ใช้ได้ทั้งชื่อ `live_upcoming` และ id `UPCOMINGLV1`

ฟิลด์ที่เก็บ:
- ระดับบน: `id, title, channel, uploader, duration, upload_date, timestamp, live_status, availability, thumbnail, chapters` (และ `playlist_count` ถ้ามี)
- ต่อ format: `format_id, format_note, ext, vcodec, acodec, height, width, fps, abr, tbr, filesize, filesize_approx, language, language_preference, rows, columns` และ `fragments` เฉพาะ storyboard

ลิงก์ทั้งหมดของ format (googlevideo ที่มีลายเซ็น) ถูกลบออก ลิงก์ fragment ของ storyboard ถูกเขียนใหม่เป็น:
- sb0: `https://fake.invalid/storyboard/<id>/M<n>.jpg` (มีไฟล์จริงใน `storyboard/`)
- sb1..sb3: `https://fake.invalid/storyboard/<id>/<sbN>/M<n>.jpg` (ไม่มีไฟล์ `fetch` จะได้ `E_NETWORK`)

## storyboard/aqz-KE-bpKQ/
แผ่น storyboard sb0 จริง 15 แผ่น (`M0.jpg`..`M14.jpg`) โหลดจากลิงก์ใน probe ด้านบน

- ยูทูปส่งไฟล์เป็น **WebP** แม้ลิงก์จะลงท้าย `.jpg` จึงเก็บตามที่ได้มาจริง Pillow เปิดได้ตามปกติ
- แผ่น `M0`..`M13` ขนาด 960×540 (ตาราง 3×3 ช่องละ 320×180)
- แผ่นสุดท้าย `M14` ขนาด 640×180 (มีแค่ 2 ช่อง แถวเดียว) ขนาดช่องจึงต้องคิดจาก `width`/`height` ของ format ไม่ใช่จากขนาดรูปหารจำนวนช่อง

## playlist/
- `PLfake250.json`: ข้อมูลสังเคราะห์ รูปแบบเดียวกับผล `extract_flat="in_playlist"` มี 250 คลิป (`fake0000001`..`fake0000250`) ใช้เทสการตัดที่ 200 คลิป (AC-IN-07)

## errors/
ข้อความ error ของ yt-dlp หนึ่งไฟล์ต่อหนึ่งข้อความ ชื่อไฟล์ `<รหัส>-<n>.txt` เทส `tests/unit/test_yterrors.py` ตรวจว่า `classify` ได้รหัสตามชื่อไฟล์

| ไฟล์ | ที่มาของข้อความ |
|---|---|
| `E_BOT_CHECK-1`, `-2` | เหตุผลจากยูทูปผ่าน `extractor/youtube/_video.py` (กิ่ง `'sign in' in reason`) ต่อด้วย `_youtube_login_hint` ใน `extractor/youtube/_base.py` และ `_login_hint` ใน `extractor/common.py` (`-2` ใช้ `'` ธรรมดาแทน `’`) |
| `E_BOT_CHECK-3` | ข้อความ rate limit ใน `extractor/youtube/_video.py` ("This content isn't available, try again later") |
| `E_BOT_CHECK-4` | errnote `Unable to download API page` ใน `extractor/youtube/_base.py` + `HTTP Error 429` จาก `networking/exceptions.py` |
| `E_VIDEO_PRIVATE-1` | ข้อความจริงจากการ probe `yZIXLfi8CZQ` (คลิปที่ `extractor/youtube/_video.py` ระบุ `'skip': 'Private video'`) |
| `E_VIDEO_PRIVATE-2` | เหตุผลแบบยาวของยูทูป ผ่านกิ่ง `'sign in'` ใน `extractor/youtube/_video.py` |
| `E_VIDEO_UNAVAILABLE-1` | ข้อความจริงจากการ probe id ที่ไม่มีอยู่ (`aaaaaaaaaaa`) |
| `E_VIDEO_UNAVAILABLE-2` | `'skip': 'Video unavailable'` ใน `extractor/youtube/_video.py` |
| `E_VIDEO_UNAVAILABLE-3`, `-4` | เหตุผล + subreason ที่ `extractor/youtube/_video.py` ต่อกันเป็น `reason. subreason` ("This video has been removed", "This video is no longer available") |
| `E_VIDEO_UNAVAILABLE-5` | `is not a valid URL` ใน `extractor/generic.py` |
| `E_VIDEO_UNAVAILABLE-6` | `Incomplete YouTube ID` ใน `extractor/youtube/_mistakes.py` |
| `E_VIDEO_UNAVAILABLE-7` | ข้อความจริงจากการดึงเพลย์ลิสต์ที่ไม่มีอยู่ (`YouTube said:` ใน `extractor/youtube/_base.py`) |
| `E_GEO_BLOCKED-1` | `The uploader has not made this video available in your country` ใน `extractor/youtube/_video.py` + ข้อความต่อท้ายของ `GeoRestrictedError` ใน `YoutubeDL.py` |
| `E_GEO_BLOCKED-2` | subreason "blocked it in your country" ผ่าน `extractor/youtube/_video.py` |
| `E_GEO_BLOCKED-3` | ข้อความตั้งต้นของ `raise_geo_restricted` ใน `extractor/common.py` |
| `E_AGE_RESTRICTED-1` | เหตุผลจากยูทูปที่ `_is_agegated` ใน `extractor/youtube/_video.py` ตรวจ ("confirm your age", "inappropriate") |
| `E_AGE_RESTRICTED-2` | ข้อความ `age-restricted` ใน `extractor/youtube/_video.py` |
| `E_LIVE_NOT_READY-1`, `-2` | เหตุผลของยูทูปที่ส่งผ่าน `raise_no_formats` ใน `extractor/youtube/_video.py` (รูปแบบ "This live event will begin" เดียวกับ `extractor/eplus.py`) |
| `E_NETWORK-1` | errnote ใน `extractor/youtube/_base.py` + `getaddrinfo failed` ของ Windows (`networking/_helper.py`) |
| `E_NETWORK-2` | `Connection to ... timed out` ใน `networking/_requests.py` |
| `E_NETWORK-3` | connection reset ของ Windows (10054) ห่อด้วย errnote `Unable to download API page` ใน `extractor/youtube/_base.py` (ตัวข้อความ reset มาจากระบบปฏิบัติการ ไม่ได้อยู่ใน yt-dlp) |
| `E_NETWORK-5` | `Connection reset by peer` (Errno 104) มาจากระบบปฏิบัติการ ไม่ได้อยู่ใน yt-dlp |
| `E_NETWORK-4` | `unable to download video data` + `HTTP Error 503` จาก `networking/exceptions.py` |
| `E_UNKNOWN-1` | `Requested format is not available` ใน `YoutubeDL.py` |
| `E_UNKNOWN-2` | `This video is DRM protected` ใน `extractor/common.py` (`report_drm`) |

path ในตารางอยู่ใต้ `.venv/Lib/site-packages/yt_dlp/`

## ลิขสิทธิ์
Big Buck Bunny © Blender Foundation | www.bigbuckbunny.org
เผยแพร่ภายใต้ [Creative Commons Attribution 3.0](https://creativecommons.org/licenses/by/3.0/)
ข้อมูลใน `probe/aqz-KE-bpKQ.json` และภาพใน `storyboard/aqz-KE-bpKQ/` มาจากคลิปนี้บนยูทูป (ช่อง Blender) ภาพถูกย่อเป็นภาพตัวอย่างโดยยูทูป ไม่ได้แก้ไขเพิ่ม
