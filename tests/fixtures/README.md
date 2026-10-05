# tests/fixtures

ข้อมูลที่ `FakeExtractor` (`src/yttoolkit/core/extractor.py`) และเทสใช้แทนการต่อยูทูปจริง
ดึงเมื่อ 2026-09-29 ด้วย yt-dlp 2026.08.19 (`yt-dlp[default]` + deno จาก PyPI) บน Windows 11
สคริปต์ที่ใช้ดึงเป็นสคริปต์ทิ้ง ไม่ได้ commit ไว้

## probe/
ผล `extract_info(download=False)` ที่ตัดให้เหลือเฉพาะฟิลด์ที่แอพอ่าน

- `aqz-KE-bpKQ.json`: ข้อมูลจริงของ Big Buck Bunny (635 วินาที, storyboard sb0..sb3)
- `jNQXAC9IVRw.json`: ข้อมูลจริงของ "Me at the zoo" (19 วินาที, ไม่มี storyboard) ยกเว้น `chapters` 3 รายการ (Intro / The cool thing / End) ที่**เขียนเองเป็นข้อมูลทดสอบ** คลิปจริงไม่มี chapter
- `live_upcoming.json`: ข้อมูลสังเคราะห์ `live_status: is_upcoming` `FakeExtractor` หาไฟล์นี้จาก id `UPCOMINGLV1` ในไฟล์ (id ต้องผ่านกฎ 11 ตัวเดียวกับของจริง)

ฟิลด์ที่เก็บ:
- ระดับบน: `id, title, channel, uploader, duration, upload_date, timestamp, live_status, availability, thumbnail, chapters` (และ `playlist_count` ถ้ามี)
- `thumbnail` ตัด query string (พารามิเตอร์ลายเซ็นของภาพย่อ) ออก เหลือแค่ path
- ต่อ format: `format_id, format_note, ext, vcodec, acodec, height, width, fps, abr, tbr, filesize, filesize_approx, language, language_preference, rows, columns` และ `fragments` เฉพาะ storyboard

ลิงก์ทั้งหมดของ format (googlevideo ที่มีลายเซ็น) ถูกลบออก ลิงก์ fragment ของ storyboard ถูกเขียนใหม่เป็น:
- sb0: `https://fake.invalid/storyboard/<id>/M<n>.jpg` (มีไฟล์จริงใน `storyboard/`)
- sb1..sb3: `https://fake.invalid/storyboard/<id>/<sbN>/M<n>.jpg` (ไม่มีไฟล์ `fetch` จะได้ `E_NETWORK`)

## storyboard/aqz-KE-bpKQ/
แผ่น storyboard sb0 จริง 15 แผ่น (`M0.jpg`..`M14.jpg`) โหลดจากลิงก์ใน probe ด้านบน

- ยูทูปส่งไฟล์เป็น **WebP** แม้ลิงก์จะลงท้าย `.jpg` จึงเก็บตามที่ได้มาจริง Pillow เปิดได้ตามปกติ
- แผ่น `M0`..`M13` ขนาด 960×540 (ตาราง 3×3 ช่องละ 320×180)
- แผ่นสุดท้าย `M14` ขนาด 640×180 (มีแค่ 2 ช่อง แถวเดียว) ขนาดช่องจึงต้องคิดจาก `width`/`height` ของ format ไม่ใช่จากขนาดรูปหารจำนวนช่อง

## probe/ ของ M3 (ซับ)
ดึงเมื่อ 2026-09-30 ด้วย yt-dlp 2026.08.19 (`YtDlpExtractor().probe`) บน Windows 11 ฟิลด์ที่เก็บเหมือน M2 ข้างบน เพิ่ม `description`, `subtitles`, `automatic_captions`

- `88o5Sk8_m1Y.json`: ข้อมูลจริงของ "Thai Listening Practice EP.1" (372 วินาที ช่อง KOD THAI) ไม่มีซับเจ้าของ ซับอัตโนมัติ `th-orig` + `th` (ไม่มี `tlang` ทั้งคู่) และ `en, ja, fr, ko, zh-Hans` ที่เป็นซับแปล storyboard sb0..sb3 เขียนลิงก์ใหม่เหมือน M2
- `8lpOfyoxcvU.json`: ข้อมูลจริงของ Thairath "3 นาทีคดีดัง" (403 วินาที ช่อง Thairath Variety) เสียงต้นฉบับ `th` (`language_preference` 10) กับเสียงพากย์ `en-US` ซับอัตโนมัติมี `en-US-orig` และ `th-orig` และบางคีย์ (`th`, `en`, ...) มีทั้งรายการที่มี `tlang` และไม่มี
- `aqz-KE-bpKQ.json`, `jNQXAC9IVRw.json`: ของเดิมจาก M2 เพิ่มแค่ `description`, `subtitles`, `automatic_captions` ฟิลด์เดิมไม่ถูกแตะ (aqz ไม่มีซับเลย ใช้เป็นคลิป "ไม่มีซับ") ซับอัตโนมัติของ jNQ เป็น HLS (`protocol: m3u8_native`) อย่างเดียว เก็บไว้เพื่อให้เทสพิสูจน์ว่าถูกข้าม
- ข้อมูลสังเคราะห์ (`channel: "ชุดทดสอบ"`, `live_status: not_live`, ไม่มี storyboard) `FakeExtractor` หาไฟล์ตามชื่อไฟล์:
  - `LONGTHAI1hr.json`: คลิปไทย 3720 วินาที (1 ชั่วโมง) ใช้เทสความเร็ว json3 ชี้ไปที่ไฟล์ของ 88o5 พร้อม `?repeat=10` (ให้ตัวปลอมเอาไฟล์มาต่อซ้ำ 10 รอบ)
  - `VTTFALLBAK1.json`: json3 ชี้ไป `subs/VTTFALLBAK1/broken.json3` (JSON ที่ถูกตัดกลางทาง) ส่วน vtt ชี้ไปไฟล์ vtt จริงของ 88o5 ใช้เทสการถอยไปอ่าน vtt
  - `NOORIGSUB01.json`: ไม่มีซับเจ้าของ ซับอัตโนมัติ `yue` (ไม่มี `tlang`) กับ `en`, `th` ที่เป็นซับแปล (ลงท้าย `?tlang=`) ทุกอันชี้ไปฐานเดียวกับไฟล์ของ 88o5
  - `OWNERTHSUB1.json`: คลิปภาษาอังกฤษ (ชื่อ "Owner Thai subtitle test" 240 วินาที เสียงต้นฉบับ `en`) มีซับเจ้าของ `th` กับ `en` (json3 + vtt) และซับอัตโนมัติ `en-orig` (json3 ชี้ไป `subs/OWNERTHSUB1/en.json3`) ลิงก์ vtt ของซับเจ้าของไม่มีไฟล์รองรับ (มีแค่ json3)

ฟิลด์ที่เก็บของซับ:
- `description` เป็นข้อความดิบจาก yt-dlp
- `subtitles` / `automatic_captions`: ต่อคีย์เก็บเฉพาะรายการที่ `ext` เป็น `json3` หรือ `vtt` และรายการ `protocol: m3u8_native` (ของ HLS) ฟิลด์ของรายการเก็บแค่ `ext, url, name, protocol` (ถ้ามี) `live_chat` ไม่ได้เก็บ
- ซับอัตโนมัติที่เป็นซับแปลเก็บเฉพาะคีย์ `en, ja, fr, ko, zh-Hans` (ยูทูปเสนอกว่า 150 ภาษา) คีย์ที่ไม่ใช่ซับแปลเก็บครบ

ลิงก์ (ลายเซ็นของยูทูปหมดอายุใน 6-7 ชั่วโมง จึงเขียนใหม่ทุกอัน) รูปแบบ `https://fake.invalid/subs/<videoId>/<key>.<ext>[?tlang=<code>][&repeat=<n>]`:
- `<key>` คือคีย์ของ yt-dlp (`th-orig`, `en`, ...) `<ext>` คือ `json3` หรือ `vtt`
- `?tlang=<code>` คงไว้ตามลิงก์จริงที่มี `tlang` (เป็นซับแปลที่ยูทูปแปลให้) `FakeExtractor` จะหาไฟล์ `subs/<videoId>/tlang-<code>.<ext>`
- `&repeat=<n>` ใช้กับ json3 เท่านั้น: ตัวปลอมเอาไฟล์มาต่อซ้ำ n รอบ (เฉพาะ `LONGTHAI1hr`)
- ลิงก์ HLS เขียนเป็น `https://fake.invalid/hls/<videoId>/<key>.m3u8` (ไม่มีไฟล์ เพราะต้องถูกข้าม)

## probe/ ของ owner round 2 (ข้อมูลคลิป C-A1)
เพิ่มฟิลด์ `view_count, like_count, comment_count, channel_follower_count, tags, categories, heatmap` (ต่อจาก `chapters`)

- `88o5Sk8_m1Y`, `jNQXAC9IVRw`: ค่าจริงจาก `YtDlpExtractor().probe` คลิปละครั้งเดียว เมื่อ 2026-10-01 (yt-dlp 2026.08.19) · `heatmap` ของ 88o5 เป็น `null` จริง (คลิปนี้ยูทูปไม่มีกราฟ) · ของ jNQ เป็นของจริง 100 รายการ
- ที่เหลือเป็นค่าสังเคราะห์: `aqz-KE-bpKQ`, `8lpOfyoxcvU`, `OWNERTHSUB1`, `LONGTHAI1hr` มี heatmap 100 รายการที่สร้างจากเนินรูประฆัง (ยอดสูงสุดปรับเป็น 1.0 แบบยูทูป) · `OWNERTHSUB1` มีแท็กที่ทดสอบ YAML (`"`, `:`, `#`, `\`, ช่องว่างหัวท้าย, แท็กว่าง) · `LONGTHAI1hr` มี 55 แท็ก (แอพเก็บ 50) · `NOORIGSUB01` มี `comment_count: 0` (แถวคอมเมนต์ปักหมุดถูกซ่อน)
- `VTTFALLBAK1` และ `live_upcoming.json` ไม่มีฟิลด์เหล่านี้ (กรณี "ไม่รู้ค่า")

## comments/ (คอมเมนต์ปักหมุด C-A2)
`FakeExtractor.pinned_comment` อ่าน `comments/<videoId>.json` รูปแบบ `{"comment": {text, likes?, publishedText?, byUploader} | null}` ไม่มีไฟล์ = `null` · ไฟล์ `{"error": "<รหัส>"}` = โยน error รหัสนั้น

- `88o5Sk8_m1Y.json`: `byUploader: true` · **เขียนเอง** ข้อความไทยหลายบรรทัดที่โปรเจกต์แต่ง (ไม่ใช่คอมเมนต์จริงของช่อง) มีลิงก์ `example.com` ไว้ทดสอบว่าหน้าเว็บไม่ทำลิงก์
- `VIEWERPIN01.json`: **เขียนเอง** ปักหมุดของผู้ชม `byUploader: false` (คลิปสังเคราะห์ `probe/VIEWERPIN01.json` ชื่อ "คลิปที่คอมเมนต์ปักหมุดเป็นของผู้ชม" ไม่มีซับ)
- `aqz-KE-bpKQ.json`: `null` (ไม่มีคอมเมนต์ปักหมุด)
- `OWNERTHSUB1.json`: `E_NETWORK`
- ไม่มีชื่อ id หรือรูปของผู้เขียนในทุกไฟล์ (PDPA)

## subs/
ไฟล์ซับที่โหลดจากลิงก์จริง (ก่อนเขียนลิงก์ใหม่) ตามไบต์ที่ได้มา ไม่แปลงปลายบรรทัด ไม่แก้เนื้อหา ยกเว้น `OWNERTHSUB1` ที่เขียนเอง

- `88o5Sk8_m1Y/th-orig.json3`: ซับไทยอัตโนมัติ 192 events มี `aAppend` 95 อัน มีเวลาต่อคำ (`tOffsetMs`) events ซ้อนกัน
- `88o5Sk8_m1Y/th-orig.vtt`: ตัวเดียวกันแบบ vtt ที่ขึ้นทีละบรรทัด (rolling) ขึ้นต้นด้วย `WEBVTT`
- `88o5Sk8_m1Y/tlang-en.json3`: **สร้างเอง (synthetic)** แทนซับแปลอังกฤษจริง เพราะตอนดึงเมื่อ 2026-09-30 ยูทูปตอบ 429 ("automated queries") เฉพาะคำขอซับแปล (`tlang=en`) ใช้เวลาของ event ใน `th-orig.json3` (ข้าม `aAppend`) event ละ 1 seg ข้อความ "Synthetic translated line N." ตามรูปแบบซับแปลอัตโนมัติ (ไม่มีเวลาต่อคำ) ถ้าวันหลังดึงของจริงได้ ให้แทนที่ไฟล์นี้
- `8lpOfyoxcvU/en-US-orig.json3`, `th-orig.json3`: ซับอัตโนมัติอังกฤษ (เสียงพากย์) และไทย
- `jNQXAC9IVRw/en.json3`, `en.vtt`, `de.json3`: ซับเจ้าของช่อง ไม่มีเวลาต่อคำ ข้อความมี `\n` ในประโยค
- `OWNERTHSUB1/th.json3`, `en.json3`: **เขียนเอง** ไม่ได้ดึงจากยูทูป ใช้โครงเดียวกับ json3 ซับเจ้าของจริง (ดูจาก `jNQXAC9IVRw/en.json3`) ประโยคไทย 20 ประโยคที่ทีมเขียน: event แรกเป็นเครดิตผู้แปล ("แปลโดย ทีมทดสอบ") มี 1 event ที่มี `\n` กลางประโยค มี 1 ประโยคยาวเกิน 110 ตัวอักษร และมีช่องว่างระหว่าง event 3.5 วินาที `en.json3` คือ 20 ประโยคอังกฤษที่ตรงกัน (เวลาเดียวกัน)
- `VTTFALLBAK1/broken.json3`: ข้อความ `{"events": [` (JSON ที่ถูกตัดกลางทาง)

## storyboard/88o5Sk8_m1Y/
แผ่น storyboard sb0 จริง 9 แผ่น (`M0.jpg`..`M8.jpg`) ของ "Thai Listening Practice EP.1" ไว้ให้เทส "ทรานสคริปต์ -> เฟรม" มีภาพจริง เป็น WebP ที่ลงท้าย `.jpg` เหมือนของ aqz ข้างบน

## playlist/
- `PLfakeplaylist250.json` (id `PLfakeplaylist250` ยาวผ่านกฎ 10-64 ตัวของ `core/inputs.py`): ข้อมูลสังเคราะห์ รูปแบบเดียวกับผล `extract_flat="in_playlist"` มี 250 คลิป (`fake0000001`..`fake0000250`) ใช้เทสการตัดที่ 200 คลิป (AC-IN-07)
- `RDaqz-KE-bpKQ.json`: มิกซ์อัตโนมัติสังเคราะห์ ชื่อ "มิกซ์ - Big Buck Bunny" มี 30 คลิป (คลิปแรกคือคลิปตั้งต้น `aqz-KE-bpKQ` ตามด้วย `jNQXAC9IVRw` และ `mixfake0003`..`mixfake0030`) ไม่มี `playlist_count` เหมือนมิกซ์จริง ใช้เทสการตัดที่ 25 คลิป · `FakeExtractor` อ่านไฟล์นี้เมื่อส่งคลิปตั้งต้น (`video_id`) มาด้วยเท่านั้น

## errors/
ข้อความ error ของ yt-dlp หนึ่งไฟล์ต่อหนึ่งข้อความ ชื่อไฟล์ `<รหัส>-<n>.txt` เทส `tests/unit/test_yterrors.py` ตรวจว่า `classify` ได้รหัสตามชื่อไฟล์

| ไฟล์ | ที่มาของข้อความ |
|---|---|
| `E_BOT_CHECK-1`, `-2` | เหตุผลจากยูทูปผ่าน `extractor/youtube/_video.py` (กิ่ง `'sign in' in reason`) ต่อด้วย `_youtube_login_hint` ใน `extractor/youtube/_base.py` และ `_login_hint` ใน `extractor/common.py` (`-2` ใช้ `'` ธรรมดาแทน `’`) |
| `E_BOT_CHECK-3` | ข้อความ rate limit ใน `extractor/youtube/_video.py` ("This content isn't available, try again later") |
| `E_BOT_CHECK-4` | errnote `Unable to download API page` ใน `extractor/youtube/_base.py` + `HTTP Error 429` จาก `networking/exceptions.py` |
| `E_BOT_CHECK-5` | `reason += '. YouTube is requiring a captcha challenge before playback'` ใน `extractor/youtube/_video.py` |
| `E_VIDEO_PRIVATE-1` | ข้อความจริงจากการ probe `yZIXLfi8CZQ` (คลิปที่ `extractor/youtube/_video.py` ระบุ `'skip': 'Private video'`) |
| `E_VIDEO_PRIVATE-2` | เหตุผลแบบยาวของยูทูป ผ่านกิ่ง `'sign in'` ใน `extractor/youtube/_video.py` |
| `E_VIDEO_PRIVATE-3` | `'skip': 'This playlist is private'` ใน `extractor/youtube/_tab.py` ในรูป `YouTube said: ...` ของ `extractor/youtube/_base.py` |
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
| `E_LIVE_NOT_READY-1`, `-2` | เหตุผลของยูทูปที่ส่งผ่าน `raise_no_formats` ใน `extractor/youtube/_video.py` (รูปแบบ "This live event will begin" เดียวกับ `extractor/eplus.py`) |
| `E_NETWORK-1` | errnote ใน `extractor/youtube/_base.py` + `getaddrinfo failed` ของ Windows (`networking/_helper.py`) |
| `E_NETWORK-2` | `Connection to ... timed out` ใน `networking/_requests.py` |
| `E_NETWORK-3` | connection reset ของ Windows (10054) ห่อด้วย errnote `Unable to download API page` ใน `extractor/youtube/_base.py` (ตัวข้อความ reset มาจากระบบปฏิบัติการ ไม่ได้อยู่ใน yt-dlp) |
| `E_NETWORK-5` | `Connection reset by peer` (Errno 104) มาจากระบบปฏิบัติการ ไม่ได้อยู่ใน yt-dlp |
| `E_NETWORK-4` | `unable to download video data` + `HTTP Error 503` จาก `networking/exceptions.py` |
| `E_NETWORK-6` | `A network error has occurred.` ใน `extractor/common.py` (ห่อ `IncompleteRead`) |
| `E_UNKNOWN-1` | `Requested format is not available` ใน `YoutubeDL.py` |
| `E_UNKNOWN-2` | `This video is DRM protected` ใน `extractor/common.py` (`report_drm`) |

path ในตารางอยู่ใต้ `.venv/Lib/site-packages/yt_dlp/`

## media/ (ไฟล์สื่อจิ๋วของ M4)
ไฟล์สื่อสร้างเองในเครื่องด้วย ffmpeg 8.1 (ไม่ได้โหลดจากที่ไหน) ใช้เทส `core/media.py` กับ ffmpeg จริง (`tests/integration/test_media_ffmpeg.py`) และเป็นไฟล์ที่ `FakeMediaTools` คัดลอกให้ (`video.mp4`, `audio.m4a`, `audio.mp3`, `audio.wav`) ทุกไฟล์เล็กกว่า 60 KB ภาพคือ test pattern ของ ffmpeg เสียงคือโทน 440 Hz ไม่มีเนื้อหาของบุคคลที่สาม

สร้างด้วยคำสั่งนี้ (รันในโฟลเดอร์ `tests/fixtures/media`):

```bash
ffmpeg -hide_banner -y -f lavfi -i testsrc=size=160x90:rate=10 -f lavfi -i sine=frequency=440:sample_rate=44100 -t 2 -c:v libx264 -pix_fmt yuv420p -c:a aac -b:a 64k -shortest video.mp4
ffmpeg -hide_banner -y -f lavfi -i testsrc=size=160x90:rate=10 -t 2 -c:v libx264 -pix_fmt yuv420p video-noaudio.mp4
ffmpeg -hide_banner -y -f lavfi -i sine=frequency=440:sample_rate=44100 -t 2 -c:a aac -b:a 64k audio.m4a
ffmpeg -hide_banner -y -f lavfi -i sine=frequency=440:sample_rate=44100 -t 2 -c:a libmp3lame -b:a 128k audio.mp3
ffmpeg -hide_banner -y -f lavfi -i sine=frequency=440:sample_rate=22050 -t 0.5 -ac 1 -c:a pcm_s16le audio.wav
ffmpeg -hide_banner -y -f lavfi -i testsrc=size=160x90 -frames:v 1 cover.jpg
```

| ไฟล์ | ขนาดประมาณ | ใช้ทำอะไร |
|---|---|---|
| `video.mp4` | 24 KB | h264 160×90 10 fps 2 วินาที + เสียง aac 64k |
| `video-noaudio.mp4` | 6 KB | ภาพอย่างเดียว (เทสคลิปไม่มีเสียง) |
| `audio.m4a` | 18 KB | aac 44.1 kHz 2 วินาที (ต้นทางของ mp3 / wav / ใส่ปก) |
| `audio.mp3` | 33 KB | mp3 128k (สิ่งที่ `FakeMediaTools.to_mp3` เขียนออกมา) |
| `audio.wav` | 22 KB | pcm_s16le mono 22.05 kHz 0.5 วินาที (สิ่งที่ `FakeMediaTools.to_wav` เขียนออกมา) |
| `cover.jpg` | 5 KB | ภาพปก 160×90 |

เทส real-ffmpeg ใช้ `requires_ffmpeg` (`tests/helpers_ffmpeg.py`) จะถูกข้ามเมื่อเครื่องไม่มี ffmpeg

หมายเหตุ `license`: `probe/88o5Sk8_m1Y.json` มีฟิลด์ระดับบน `"license": "Creative Commons Attribution license (reuse allowed)"` ซึ่งใส่เข้าไปด้วยมือ (ตัวตัด probe `core/videos.trim_probe` ไม่เก็บฟิลด์นี้ และไฟล์ probe อื่นไม่มี) เพื่อให้เทสเครดิตของคลิป CC BY อ่านค่าจากไฟล์ได้ (`tests/unit/test_video_meta.py`) คลิปนี้เผยแพร่แบบ CC BY ตามหัวข้อ "ลิขสิทธิ์" ด้านล่าง

## downloads/ (งานโหลดของตัวปลอม M4)
`behaviors.json` (ตามสัญญา C14 ของแผน M4 ทุกตัวอักษร) บอก `FakeExtractor.download` ว่าแต่ละคลิปโหลดกี่ขั้น ขั้นละกี่มิลลิวินาที และพลาดตรงไหน ตัวปลอมไม่ต่อเน็ตและไม่ใช้ ffmpeg: เดินครบทุกขั้นแล้วคัดลอกไฟล์จาก `media/` (`video.mp4` เมื่อรวมภาพกับเสียง, `video-noaudio.mp4` เมื่อไม่มีเสียง, `audio.m4a` เมื่อโหลดเสียง) ไปเป็น `media.mp4` / `media.m4a` ใน workdir ของงาน

- `default`: คลิปที่ไม่อยู่ใน `videos` โหลด 6 ขั้น ขั้นละ 120 ms (คลิปต้องมีไฟล์ใน `probe/` ไม่มี = `E_VIDEO_UNAVAILABLE` เหมือนเดิม)
- `videos`: คลิปสังเคราะห์ ไม่มีไฟล์ใน `probe/` ของตัวเอง `probeAs` บอกว่าให้ใช้ข้อมูลของคลิปไหน (ทุกตัวใช้ Big Buck Bunny `aqz-KE-bpKQ`) แล้วตัวปลอมเปลี่ยน `id` เป็นของคลิปนั้นและเปลี่ยน `title` ตามที่ตั้งไว้
- `failAtStep` / `error` / `failTimes`: พอถึงขั้นที่ `failAtStep` (นับจาก 0) ให้พลาดด้วยรหัส `error` ไม่เกิน `failTimes` ครั้งต่อคลิป นับตลอดอายุของตัวปลอมหนึ่งตัว (เปิดโปรแกรมใหม่ = เริ่มนับใหม่)

| id | ชื่อคลิป | ทำอะไร | สเปก e2e ที่ใช้ |
|---|---|---|---|
| `SLOWDOWNLD1`..`SLOWDOWNLD4` | คลิปโหลดช้า 1..4 | 40 ขั้น ขั้นละ 250 ms (ราว 10 วินาที) ไว้เห็นงานที่กำลังโหลด งานรอคิว และการยกเลิก | `queue-flow.spec.ts` (T14) |
| `BOTCHECKDL1` | คลิปติดบอท | พลาด `E_BOT_CHECK` ที่ขั้น 2 ครั้งเดียว แล้วรอบถัดไปผ่าน (Q1: คิวพัก งานกลับไปหัวคิวหนึ่งครั้ง แล้วโหลดได้) | `queue-flow.spec.ts` |
| `NETRETRYDL1` | คลิปเน็ตหลุด | พลาด `E_NETWORK` ที่ขั้น 1 ครั้งเดียว แล้วรอบถัดไปผ่าน (ตัวนับ "ลองใหม่ครั้งที่ n/3") | `queue-flow.spec.ts` |
| `REFUSEDDL01` | คลิปที่ยูทูปไม่ส่งไฟล์ | พลาด `E_YT_REFUSED` ตั้งแต่ขั้น 0 ทุกครั้ง (99 ครั้ง) งานจบเป็นสีแดง ไม่ลองซ้ำเอง (Q2) | `queue-flow.spec.ts` |

เทสหน่วย (`tests/unit/test_extractor_download.py`) ส่งพารามิเตอร์ `behaviors` ชี้ไปที่สำเนาของไฟล์นี้ที่ตั้ง `stepMs` เป็น 0 จะได้ไม่ต้องรอ และเช็คว่าไฟล์นี้ตรงกับ C14 ทุกค่า แก้ไฟล์นี้ต้องแก้สัญญา C14 ในแผนก่อน

## ลิขสิทธิ์
Big Buck Bunny © Blender Foundation | www.bigbuckbunny.org
เผยแพร่ภายใต้ [Creative Commons Attribution 3.0](https://creativecommons.org/licenses/by/3.0/)
ข้อมูลใน `probe/aqz-KE-bpKQ.json` และภาพใน `storyboard/aqz-KE-bpKQ/` มาจากคลิปนี้บนยูทูป (ช่อง Blender) ภาพถูกย่อเป็นภาพตัวอย่างโดยยูทูป ไม่ได้แก้ไขเพิ่ม

### คลิปของ M3
- `88o5Sk8_m1Y` "Thai Listening Practice | EP.1 | Beginner" ช่อง KOD THAI (https://www.youtube.com/channel/UC-N21-wHc1xazese2t3EjaQ) และ `8lpOfyoxcvU` "3 นาทีคดีดัง : 2499 บันทึกชีวิต แดง ไบเล่ | Thairath Online" ช่อง Thairath Variety (https://www.youtube.com/channel/UCtc9-CS_FIZ7GGrm8--wsrQ) เผยแพร่บนยูทูปภายใต้ Creative Commons Attribution (CC BY) ข้อมูลใน `probe/`, ไฟล์ใน `subs/<videoId>/` และภาพใน `storyboard/88o5Sk8_m1Y/` ของสองคลิปนี้มาจากคลิปดังกล่าว ไม่ได้แก้ไขเนื้อหา
- "Me at the zoo" (`jNQXAC9IVRw`, ช่อง jawed): เหมือนเดิม
- `OWNERTHSUB1` เป็นข้อมูลสังเคราะห์ที่โปรเจกต์เขียนเอง (ไม่มีข้อความของบุคคลที่สาม)
- ไม่ได้เก็บซับของคลิป TED ไว้ในรีโป (ซับ TED เป็น CC BY-NC-ND) เทสเครือข่ายเปิดคลิปจริงได้โดยไม่เก็บอะไรลงรีโป
- ข้อมูลทั้งหมดใช้ในเทสเท่านั้น รีโปเป็นแบบส่วนตัว

## sponsorblock/ (M5 รอบ A)
ช่วงโฆษณาปลอมของ `FakeExtractor.sponsor_segments` ต่อคลิป: `{"segments": [[startMs, endMs, "หมวด"], ...]}` หรือ `{"error": "..."}` (= ติดต่อ SponsorBlock ไม่ได้) · ไม่มีไฟล์ = ไม่มีข้อมูลจากชุมชน
- `ADSCUTCLIP1.json` intro 0-12 วิ, sponsor 60-90 วิ, outro 600-635 วิ (คลิปปลอมที่ probe เป็น aqz-KE-bpKQ 635 วิ)
- `ADSOFFLINE1.json` ติดต่อไม่ได้ · `ADSNODATA01` ไม่มีไฟล์ = ไม่มีข้อมูล

คลิปปลอมของ M5 รอบ A ใน `downloads/behaviors.json`: RANGECLIP01, ADSCUTCLIP1, ADSNODATA01, ADSOFFLINE1 (probe เป็น aqz-KE-bpKQ) และ CHAPTERS001 (probe เป็น jNQXAC9IVRw 3 chapter) ใช้ใน web/e2e/queue-advanced.spec.ts เท่านั้น

## ภาพคม (M5 รอบ B)
คลิปปลอมใน `downloads/behaviors.json` (probe เป็น aqz-KE-bpKQ 635 วิ ภาพเร็ว 128 ภาพ) ใช้ใน `web/e2e/queue-sharp.spec.ts` เท่านั้น:
- `SHARPCLIP01` "คลิปภาพคม": งาน `frames_sharp` (เลือก format 298 avc1 1280×720 ตาม `download.sharp_choice`)
- `AUTOSHARP01` "คลิปภาพคมอัตโนมัติ": มี `"media": {"width": 1280, "height": 720, "dynamic_range": "SDR"}` = ตัวปลอมบอกว่าไฟล์ที่โหลดเป็น 720p SDR งาน `video` จึงทำภาพคมอัตโนมัติ (คลิปอื่นไม่มี `media` = ไม่รู้ขนาดไฟล์ ภาพคมอัตโนมัติข้าม)

`FakeMediaTools.extract_frame` เขียนสำเนาของ `media/cover.jpg` เป็นภาพคมทุกภาพ (โหมดปลอมไม่มี ffmpeg)
`sharp/plan-cases.json`: เคสแผนเวลาภาพคมที่ `tests/unit/test_sharp_plan.py` และ `web/src/lib/sharp-frames.test.ts` อ่านร่วมกัน (เขียนเอง คำนวณมือตาม spec 3.2)

## capture/ (M5 รอบ B2 ถ่ายภาพคมตรงจุด)
- `piece.mp4`: วิดีโอสังเคราะห์ 4 วินาที 1920×1080 10 fps (`testsrc` ของ ffmpeg) แบบ fragmented mp4 ที่เรียงกล่องแบบไฟล์ DASH ของยูทูป: `ftyp`, `moov`, `sidx` (version 1, timescale 10240, 4 ท่อน ท่อนละ 1 วินาที) แล้ว `moof`+`mdat` ทีละท่อน · ไม่มี B-frame ไฟล์จึงเริ่มที่เวลา 0 · ราว 50 KB
- สร้างครั้งเดียวด้วย ffmpeg 8.1 (Gyan full build) แล้ว commit ไว้ เทสไม่สร้างใหม่ (ffmpeg รุ่นอื่นได้ไบต์ต่างกันเล็กน้อย เทสตรวจแค่โครงสร้าง):
  `ffmpeg -f lavfi -i "testsrc=size=1920x1080:rate=10:duration=4" -c:v libx264 -preset veryslow -crf 40 -bf 0 -g 10 -keyint_min 10 -sc_threshold 0 -pix_fmt yuv420p -an -movflags +frag_keyframe+empty_moov+default_base_moof+global_sidx -fflags +bitexact -flags:v +bitexact piece.mp4`
- ใช้กับ `core/frame_piece.py` (เทสตัวอ่าน sidx), `FakeExtractor.fetch_frame_piece` (ตัดชิ้นด้วยตัวอ่านตัวจริง เวลาเกิน 4 วินาทีวนกลับด้วย `t % 4000`) และเทส ffmpeg จริงของการถ่ายภาพ (ภาพจากชิ้นต้องตรงกับภาพจากไฟล์เต็มที่เวลาเดียวกัน)
