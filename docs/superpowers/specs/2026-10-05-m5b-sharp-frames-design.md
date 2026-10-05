# M5 round B — sharp frames — design

Pete approved the design sections in conversation on 2026-10-05. This written spec is waiting for his review.

M5 runs in three rounds, each going spec → plan → build → owner preview:
- A: advanced download options (merged to main as aa57629)
- **B: sharp frames (this spec)**
- C: opt-in YouTube cookies

Round B touches:
- the W2 frames section;
- the `video` job (automatic sharp frames);
- the job API, the handlers and the in-app cache;
- the settings "ทั่วไป" tab;
- the docs.

Thai UI strings below are final copy. Use them verbatim.

Requirements covered: FR-FRAME-2, FR-FRAME-3, FR-FRAME-5 (sharp source), AC-FRAME-03, AC-FRAME-04, BRD #33 (the `E_NO_STORYBOARD` text changes at M5). Also the `contact_sheet` / `frames_zip` `source: "sharp"` item in docs/m4-followups.md.

## Owner decisions (2026-10-05)

| # | Decision | Why |
|---|---|---|
| D1 | **Approach ก**: download the whole clip as video-only ≤ 720p into the job's work folder, extract the frames with ffmpeg, then delete the video. The rejected options were seeking ffmpeg directly into the YouTube stream (ข) and downloading short sections (ค). | ข and ค make 100-200 separate requests to YouTube in a row. That risks a bot check, which brakes the whole queue, and they break when stream URLs expire or YouTube changes. ก reuses the existing download path (pacing, brake, progress, cancel). Cost: long clips download in full (1 h ≈ 300-800 MB, deleted at once). |
| D2 | Sharp frames go to **both places**: (1) the in-app cache, where the frames grid shows them; (2) a folder of JPGs in the output folder. | Pete's choice: staff see sharp frames in the app and also get files they can use right away. |
| D3 | "ขอภาพคม" opens a **small dialog first**. It offers "same times as fast frames" (the default) or "every N seconds". It shows the frame count and the download size before anything is queued. | Pete's choice. FR-FRAME-3 requires a user-set interval. The size warning matters because the temporary download can be large. |
| D4 | "720p" means a **short side ≤ 720**. Frames are scaled so the **long side is 1280 px**. Portrait clips (Shorts) therefore give 720×1280. AC-FRAME-03's "≥ 1280 px wide" reads as "long side ≥ 1280". | A literal 1280-wide portrait frame would need a 1080p download, which is much heavier for no real gain. Ruled by Cream; Pete may override. |
| D5 | **One sharp set per clip** in the app. A new request replaces it there. Output-folder copies are never overwritten: a repeat request gets ` (2)`. | Keeps the grid simple: one fast set and at most one sharp set. Files the user already has are never touched. |
| D6 | **Automatic sharp frames** after a `video` job. Conditions: full clip, height ≥ 720 (short side), not HDR. Frames go to the **in-app cache only**. The setting is **on by default** and can be switched off. | Pete's idea and choice. The video is already on disk, so this costs no network and carries no bot risk (10-40 s of local ffmpeg work per clip). It skips the output folder because 100 JPGs next to every video would clutter it; users can still zip or right-click. |
| D7 | No sharp frames in **W3** (multi-clip page) in round B. | Each clip can download hundreds of MB. Ticking a whole playlist would be very heavy. Add later if asked. Automatic sharp frames still apply to W3 video jobs, because that path needs no extra download. |
| D8 | Manual sharp jobs prefer an **SDR** format, so HDR clips are not washed out. Automatic sharp frames **skip HDR files** instead of tone-mapping. | YouTube offers SDR formats alongside HDR ones, so the manual job can avoid the problem entirely. For a file the user chose to download, tone-mapping is a colour risk Cream does not want to take silently. |

## 1. W2 frames section: the "ขอภาพคม" button and dialog

### 1.1 Entry points
- **Frames section toolbar:** a button **"ขอภาพคม"** in the bulk download group, next to "โหลดภาพรวมเฟรม" and "โหลดทั้งหมด (.zip)" (as in the BRD wireframe, line 443).
- **No-storyboard empty state:** the existing disabled "ขอภาพคม" stub becomes an active button. The "เปิดใช้ในเวอร์ชันถัดไป" tooltip is removed.
- `E_NO_STORYBOARD` changes in both `core/yterrors.py` and `web/src/i18n/th.ts` to:
  - **คลิปนี้ไม่มีภาพตัวอย่างแบบเร็ว กด "ขอภาพคม" แทนได้**

### 1.2 Disabled states
The button stays focusable when disabled (`focusableWhenDisabled`), and its tooltip gives the reason.

| When | Button text / tooltip |
|---|---|
| Live, upcoming or unknown-duration clip | tooltip **"คลิปสดยังขอภาพคมไม่ได้"** |
| A `frames_sharp` job for this clip is queued or running | text **"กำลังดึงภาพคม…"**, with a spinner |

### 1.3 Dialog
Title **"ขอภาพคม"**. The dialog is a radio group plus one number field:

- ◉ **"เวลาเดียวกับภาพเร็ว"**
  - Second line: **"ทุก ~{interval} วินาที · {count} ภาพ"**.
  - `{interval}` is the storyboard interval in seconds with one decimal, e.g. `4.9`.
  - `{count}` is the number of fast frames.
- ○ **"ตั้งเอง ทุก [N] วินาที · {count} ภาพ"**
  - N is an integer from 1 to 3600.
  - `{count}` updates as the user types.
  - Validation: a non-integer or out-of-range value shows inline **"ใส่เลขวินาทีเต็ม 1-3600"**, and the start button is disabled.

Below the choice:
- Size line:
  - With a known size: **"ต้องโหลดวิดีโอชั่วคราวราว {size} (ลบทิ้งเมื่อเสร็จ)"**.
  - Without one: **"ต้องโหลดวิดีโอชั่วคราว ไม่ทราบขนาดล่วงหน้า (ลบทิ้งเมื่อเสร็จ)"**.
  - `{size}` comes from `VideoInfo.video[]`: take the format with the largest short side ≤ 720 and read its `sizeBytes`. Format it with the existing size formatter.
- Resolution line: **"ภาพกว้าง 1280 px"**.
  - For a portrait clip: **"ภาพสูง 1280 px"**.
  - If the best short side is < 720: **"คลิปนี้มีภาพสูงสุด {h}p ภาพจะเล็กกว่าปกติ"**.
- **Over 200 frames** (AC-FRAME-04): the count line is replaced, live, by:
  - **"ทุก {N} วินาทีจะได้ {count} ภาพ เกินที่ดึงได้ 200 ภาพ จะใช้ทุก {N2} วินาทีแทน"**
  - The job is sent with `intervalS = N2`.
- **A sharp set already exists** for this clip: an extra line **"ภาพคมชุดเดิมในแอพจะถูกแทนด้วยชุดใหม่ (ไฟล์ในโฟลเดอร์ไม่หาย)"**.
- **No storyboard:** the first radio is absent. The custom interval defaults to `max(1, ceil(durationS / 100))`.

Buttons:
- **"ยกเลิก"** closes the dialog.
- **"เริ่มดึงภาพคม"** enqueues `{kind: "frames_sharp", params: {}}` when "same times" is chosen, or `{intervalS: N}` / `{intervalS: N2}` for a custom interval. It then closes the dialog and shows the usual enqueue toast ("เพิ่มเข้าคิวแล้ว").

Interval maths is shared between the web and the backend (section 3.2). The web copy lives in `web/src/lib/sharp-frames.ts` and has unit tests with the same cases as Python.

## 2. W2 frames grid: fast and sharp

- **The switch:** when the clip has a sharp set (`GET /api/videos/{id}/sharp` returns 200), the section header shows a two-option toggle group **[ภาพเร็ว | ภาพคม]** (`aria-label` **"ชุดภาพเฟรม"**).
  - The default is **ภาพคม**.
  - The choice lives in memory for that clip only and is not persisted.
  - When there is no sharp set, the toggle is absent.
- **A job finishes while the page is open:** when a `frames_sharp` job for this clip finishes (`done`), the queue event stream invalidates the sharp query. The same happens when a `video` job finishes with the automatic sharp step done. The grid then switches to **ภาพคม** unless the user already chose ภาพเร็ว on this clip during this visit.
- **Everything that works on fast frames works on the sharp set:**
  - click to open the large image;
  - ▶ play from here;
  - the "▶ กำลังเล่น" frame;
  - the "ดูซ้ำบ่อย" frames and filter;
  - the `?at=` highlight;
  - every context-menu item: copy image, download image, copy time, copy link at time, open on YouTube at time, play from here, view subs, ตั้งเป็นจุดเริ่ม / ตั้งเป็นจุดจบ.

  Copy and download use the sharp file. All of these key off each frame's own `tMs`, so a custom-interval set, whose times differ from the fast set, works unchanged.
- **The no-storyboard state with a sharp set:** the grid shows the sharp set. There is no toggle, because there is no fast set to switch to.
- **Bulk buttons follow the toggle.** "โหลดภาพรวมเฟรม" sends `contact_sheet {source, columns: 5}` and "โหลดทั้งหมด (.zip)" sends `frames_zip {source}`, where `source` is `"sharp"` when the toggle shows ภาพคม and `"fast"` otherwise.
  - The contact-sheet cell stays 320×180.
  - Sharp frames are downscaled into the cell, so the sheet is crisp. Fast frames are upscaled, as before.

## 3. The `frames_sharp` job

### 3.1 Params and API validation
- `kind: "frames_sharp"` with params `{intervalS?: int, folder?: str}`.
  - `intervalS` is an integer from 1 to 3600.
  - `folder` follows the existing M4 rule (1-80 characters, `safe_component`).
  - Unknown keys → 422 `E_BAD_REQUEST`, as for every kind.
- `contact_sheet.source` and `frames_zip.source` accept `"fast" | "sharp"`.
- When cached clip info exists, the API rejects a live or unknown-duration clip with 422. Without cached info, the handler checks the same rule and fails with `E_LIVE_NOT_READY` (live/upcoming) or `E_UNKNOWN` (duration unknown), the same pattern round A uses for ranges.
- `frames_sharp` joins `FFMPEG_KINDS`, so a missing ffmpeg gives 422 `E_FFMPEG_MISSING` at enqueue time. It is already in `YOUTUBE_KINDS`, so pacing and the bot-check brake apply.
- The web `NewJob.kind` type stops excluding `frames_sharp`. The web `ContactSheetJobParams` / `FramesZipJobParams` widen `source`.

### 3.2 Timecode plan (`core/sharp.py`, pure, mirrored in `web/src/lib/sharp-frames.ts`)
- `MAX_SHARP_FRAMES = 200`
- **Same times as fast frames** (`intervalS` absent and a storyboard exists):
  - Use the storyboard index `tMs` list exactly.
  - If it has more than 200 entries, fall back to custom mode with `N2 = ceil(durationS / 200)` and add the raised-interval note.
- **Custom N:**
  - Frames sit at `t_i = i × N × 1000` ms for `i = 0, 1, …` while `t_i < durationMs`.
  - If the count exceeds 200, use `N2 = ceil(durationS / 200)`. This guarantees ≤ 200 frames.
- **`intervalS` absent and no storyboard:** custom mode with `N = max(1, ceil(durationS / 100))`.
- **Note** when the interval was raised (manual job only), code `SHARP_INTERVAL_RAISED`:
  - **"ปรับเป็นทุก {N2} วินาทีเพื่อไม่ให้เกิน 200 ภาพ"**

### 3.3 Format selection (inside `core/extractor.py`, the only place that imports yt_dlp)
- Video-only formats with `min(width, height) ≤ 720`, preferring:
  1. SDR (`dynamic_range` absent or `"SDR"`);
  2. the largest short side;
  3. avc1 over vp9 over av01 (decode speed on Pete's iGPU-class machines);
  4. the smallest size.
- No video-only format → the best muxed format under the same rules.
- Short side < 720 → use the best available and add the note `SHARP_LOW_RES`:
  - **"คลิปนี้มีภาพสูงสุด {h}p ภาพจึงเล็กกว่าปกติ"**
- No SDR format at all → use HDR and tone-map in ffmpeg, the same zscale chain as section 3.4. This case is rare and is covered by a unit test of the argument builder.

### 3.4 Extraction (`core/media.py`)
- One ffmpeg call per frame on the local file:
  ```
  -ss <t> -i <file> -frames:v 1 -vf scale=<long side 1280, keep aspect, never upscale> -q:v 2 <out>.jpg
  ```
  - `-ss` before `-i` is accurate on a local file.
  - Never shell=True.
  - Check cancel between frames.
  - Progress is `i/n`.
- A timecode that yields no image is dropped. This can only happen within the last second, because of the duration rounding. If zero frames come out, the job fails with `E_UNKNOWN` (as the round A cutter does for an ffmpeg failure).
- `FakeMediaTools` mirrors the real argument validation, as in round A.

### 3.5 Stages, title, outputs
- **Stages:**
  - `downloading_video`, with %, speed and ETA, like a video download;
  - `extracting_frames:i/n`, shown as **"กำลังดึงภาพ {i}/{n}"**;
  - `writing`.
- **Queue title:** **"{title} · ภาพคม {n} ภาพ"**. `n` is the planned count; until it is known, the title is just "{title} · ภาพคม".
- **Output folder:** `<output>/<folder?>/<ชื่อคลิป> - ภาพคม/frame_HH-MM-SS.jpg`.
  - Names are made by the existing `file_timecode`. A second frame in the same second gets `_2`, `_3`, exactly like `frames_zip`.
  - If the folder name exists, it gets ` (2)` and so on.
  - The job's single output is the **folder**, so "เปิดโฟลเดอร์" opens it.
  - `<ชื่อคลิป>` goes through the existing safe-name and length rules.
- **In-app cache:** written as described in section 5.
- The work folder (with the temporary video) is deleted by the queue runner as today. AC-FRAME-03's "temporary video deleted" is asserted by a test.
- **Disk check before starting:** chosen format size × 1.1 + `n × 400 KB`. When the size is unknown, use the existing unknown-size policy.

## 4. Automatic sharp frames after a `video` job

- **Setting:** `autoSharpFrames: bool`, default `true`, in `core/settings.py`.
  - The settings "ทั่วไป" tab shows a switch **"ทำภาพคมอัตโนมัติตอนโหลดวิดีโอ"**.
  - Hint: **"ใช้ไฟล์ที่โหลดมาแล้ว ไม่ต้องโหลดเพิ่ม ใช้เวลาเพิ่มราว 10-40 วินาทีต่อคลิป"**.
- **Runs only when all of these hold:**
  - the setting is on;
  - the job is a `video` job with no `range`, no `sponsorblock` and `splitChapters` false (the file timeline must equal the clip timeline);
  - the downloaded video's short side is ≥ 720;
  - the file is not HDR;
  - the clip has no existing sharp set **from a manual job**. An existing automatic set is replaced.
  - ffmpeg is present.
- **Timing:** after the video file has been finalized and moved to the output folder, so the video job's result is already secure.
  - New stage `sharp_frames:i/n`, shown as **"กำลังทำภาพคม {i}/{n}"**.
  - It reads the final output file. No copy is made.
- **What it produces:**
  - Times follow the "same times as fast frames" plan of section 3.2. Without a storyboard, the custom default is used.
  - Frames use the same scale and quality as section 3.4.
  - Output goes to the cache only (section 5), with `origin: "auto"`.
  - Nothing is written to the output folder, and the job's outputs do not change.
- **Failure is never fatal.** Any error, a missing storyboard fetch, a missing ffmpeg, or a cancel during this stage are all logged (no personal data). The partial temporary set is removed and the video job still ends `done` with its file.
  - A cancel during `sharp_frames` ends the job `done`, not `cancelled`, because the video is complete.
  - No note is added for a skipped or failed automatic step.

## 5. In-app cache and API

- **Layout:** `<cache>/<videoId>/sharp/`
  - `index.json`: `{origin: "manual"|"auto", intervalMs: int|null, frames: [{index, tMs, file}], createdAt}`. `intervalMs` is null for the "same times" plan.
  - frame files `f_0000.jpg …`, using the storyboard naming helper.
- **Atomic replacement:**
  1. Build into `<cache>/<videoId>/sharp.tmp-<jobId>/`.
  2. Rename the old `sharp/` to `sharp.old-<jobId>/`.
  3. Rename the new folder into place.
  4. Delete the old one.

  A cancel or crash before step 3 leaves the previous set untouched.
- **Startup sweep:** `lifecycle.py` deletes leftover `sharp.tmp-*` / `sharp.old-*` folders and output folders named `* - ภาพคม` / `* - ภาพคม (n)` that belong to interrupted jobs, using the existing interrupted-job sweep rules.
- **`GET /api/videos/{id}/sharp`:**
  - With a set: `{origin, intervalMs, frames: [{index, tMs, url}]}`, where the `url` is under `/api/cache/{id}/sharp/…?v=<index mtime>`, the same immutable-cache trick as the storyboard.
  - Without a set: 404 with code `E_NO_SHARP_FRAMES`. The web treats 404 as "no sharp set", not as an error.
- **Purge:** the existing 30-day stale-cache purge removes the whole `<videoId>` folder, sharp set included. Nothing new is needed.
- **`contact_sheet` / `frames_zip` with `source: "sharp"`:**
  - They read the sharp index.
  - If the set is missing (purged meanwhile), they fail with `E_NO_SHARP_FRAMES`:
    - **"ภาพคมของคลิปนี้ถูกล้างไปแล้ว กด "ขอภาพคม" ใหม่ได้"**

## 6. Errors and edge cases

| Case | Behaviour |
|---|---|
| Clip has no 720p | Best available, note `SHARP_LOW_RES` (manual); automatic step skipped |
| HDR clip | Manual: SDR format preferred (tone-map only if no SDR exists). Automatic: skipped |
| Bot check | Existing brake (`on_bot_check`), job fails with the existing bot-check error |
| Disk too small / ffmpeg missing | Existing preflight errors (`E_DISK_FULL` at start, 422 `E_FFMPEG_MISSING` at enqueue) |
| Cancel during a manual job | Work folder deleted. The partial output folder is deleted. The cache keeps the previous set (atomic swap). |
| App closed mid-job | The startup sweep removes the partial output folder and the temporary cache folders |
| Live / unknown duration | Button disabled; API 422; handler re-check |
| Sharp set purged before a sharp contact sheet / zip runs | `E_NO_SHARP_FRAMES` with the message above |
| Two sharp jobs for one clip | UI prevents it. If it happens via the API, the later one simply replaces the cache set; output folders get ` (2)` |
| User deletes the output folder | No effect on the app; history "เปิดโฟลเดอร์" shows the existing "ไม่พบไฟล์ อาจถูกย้ายหรือลบไปแล้ว" |

## 7. Docs to update
- **PRD:**
  - the frames-section row (line 219);
  - the `frames_sharp` / `contact_sheet` / `frames_zip` job table (lines 669-671);
  - the strict-params paragraph (line 676: `frames_sharp` and `source: "sharp"` are now accepted);
  - the error table (`E_NO_STORYBOARD`, `E_NO_SHARP_FRAMES`);
  - the settings section (`autoSharpFrames`).
- **BRD:**
  - new decision rows for D1-D8;
  - a note on AC-FRAME-03's portrait reading (D4).
- **docs/acceptance.md:** an M5-B section with hands-on rows (dialog, over-200 message, grid switch, contact sheet / zip sharp, automatic sharp after a 720p download, Shorts clip).
- **docs/m4-followups.md:** mark the sharp-frames item done.
- **docs/m5a-followups.md:** note that the HDR point is handled for sharp frames only (D8). The cut path is unchanged.
- **tests/network_videos.toml / tests/network:** a `[sharp] clip` entry (short clip, ≈ 20-50 MB) and a network test. It runs only with Pete's approval.

## 8. Testing
- **Python unit tests:**
  - the timecode plan (same times, custom, raise to 200, no storyboard, frames near the end);
  - format selection (SDR preference, short side ≤ 720, portrait, < 720 note, muxed fallback, HDR-only tone-map args);
  - extraction argument builder;
  - handler flow with fake downloader and `FakeMediaTools`: stages, outputs, notes, cancel cleanup, atomic swap;
  - automatic step: each skip condition, failure is non-fatal, cancel ends `done`, manual set not replaced;
  - API validation;
  - `GET /sharp` 200/404;
  - contact sheet / zip `source: "sharp"`, including `E_NO_SHARP_FRAMES`;
  - lifecycle sweep of the new names;
  - the settings key.
- **Integration (real ffmpeg):** a small fixture video (generated by ffmpeg in the test, as in round A's cut tests). It asserts:
  - timecodes match the plan;
  - long side is 1280 for a 16:9 source;
  - 720×1280 for a portrait source;
  - the temporary video is gone afterwards (AC-FRAME-03).
- **Vitest:** `sharp-frames.ts` with the same cases as Python; dialog state; source selection for the bulk buttons.
- **Playwright chromium (mocked, never real jobs):**
  - the dialog: default choice, custom interval, the over-200 message (AC-FRAME-04), the replace warning;
  - live-clip and in-queue disabled states;
  - the no-storyboard flow;
  - the grid toggle and the auto-switch on job done;
  - the context menu on sharp frames;
  - bulk buttons sending `source: "sharp"`;
  - the settings switch;
  - axe checks in light and dark, and the 640 px narrow window.
- **Playwright queue spec (real jobs on local fixtures, `queue-*.spec.ts`):** one manual `frames_sharp` job end-to-end with the fake extractor.
- **Network test:** written; it runs only with Pete's approval.

## Out of scope (round B)
- Sharp frames in W3 (D7).
- More than one sharp set per clip, or keeping history of sets.
- Tone-mapping in the automatic step or in the round A cut path.
- Choosing JPG quality or resolution in the UI.

## Changes after approval (2026-10-05, during build)
- ffmpeg missing at enqueue is HTTP 409 `E_FFMPEG_MISSING` (the existing API and toast), not 422 (§3.1, §6).
- The sharp output folder sits inside the clip folder: `<clip folder>/<ชื่อคลิป> - ภาพคม/`, like every other per-clip output (§3.5).
- Format selection lives in `core/download.py` (`sharp_choice`, a pure chooser); `core/extractor.py` remains the only `yt_dlp` importer (§3.3 wording).
- The done queue title shows the frames actually kept (the folder's file count), which can be fewer than planned when end frames drop (§3.5).
- The dialog shows the storyboard interval rounded to one decimal.
- The "ขอภาพคม" number field no longer switches to "ตั้งเอง" on keyboard focus, only on click/tap or typing, so the default stays reachable by keyboard (§1.3).
- The automatic step never replaces a manual set; the check is atomic with the swap (§4).
