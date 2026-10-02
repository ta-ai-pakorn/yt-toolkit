# M5 round A — advanced download options (time range, chapter split, SponsorBlock) — design

The owner (Pete) approved the design sections in conversation on 2026-10-02; this written spec awaits his review. M5 is split into three rounds, each with its own spec → plan → build → owner preview: **A (this spec)** advanced download options · B sharp frames · C opt-in YouTube cookies. Round A touches W2 (video, audio and subtitle tabs, the player and the frame menu), the job API, the handlers and the docs. Thai UI strings below are final copy; use them verbatim.

## Owner decisions (2026-10-02)

| # | Decision | Why |
|---|---|---|
| D1 | Time-range cuts are always **frame-exact** (video re-encoded) | Users cut a section to post or present it; a start that drifts 2-5 s earlier is not usable. Waiting longer is acceptable. |
| D2 | Chapter split is available for **video and audio** | A 2-hour seminar split into one mp3 per topic is a real use (listening in the car). |
| D3 | Advanced values are **per clip** (reset when another clip is opened). Only the SponsorBlock categories ticked are remembered across clips; the SponsorBlock switch starts off for every clip | A range from one clip must never leak into another clip by accident; cutting ads shortens the file, so it must be a deliberate choice each time. |
| D4 | Chapter files go to a **sub-folder** of the clip folder: `แยกตาม chapter (mp4)` / `แยกตาม chapter (mp3)` | A seminar can have 20-30 chapters; they must not mix with the full file, subtitles and note. The format in the folder name stops `01 - …` names from colliding when both video and audio are split. |
| D5 | SponsorBlock is included, **off by default** | Built into yt-dlp, small cost; most Thai clips will have no community data, so the result clearly says so. |
| D6 | Chapter split of **video** uses fast cuts (no re-encode; each boundary may be off by 1-3 s). Audio chapter files are exact | Exact video splitting would re-encode the whole clip (30-60+ min for 2 h on a typical laptop); chapter boundaries do not need frame accuracy. |
| D7 | "Set start / set end" buttons exist **both** under the player and next to the time fields; the frame right-click menu also gets them | Under the player you can press while watching; next to the field you see which value changes. |
| D8 | W3 (multi-clip page) gets **no** advanced options in round A | Range and chapters are per clip; SponsorBlock in W3 can be added later if asked. |
| D9 | Approach **B: download the full clip, then the app cuts with ffmpeg** (no yt-dlp section download, no spike) | Reliable and fully under our control and testable; cost: long clips are always downloaded in full. |

## 1. W2 "ตัวเลือกขั้นสูง" section

- A Collapsible "ตัวเลือกขั้นสูง" (collapsed by default) at the bottom of the options in the **วิดีโอ**, **เสียง** and **ซับ** tabs. The three tabs share **one** set of values (one store keyed by `videoId`, in memory). Values survive tab switches on the same clip; opening another clip (or reloading the page) resets them. After a download is queued the values stay (the user may queue another format of the same range).
- When any advanced value is active:
  - Badge **"ใช้ตัวเลือกขั้นสูงอยู่"** next to the "ตัวเลือกขั้นสูง" trigger **in every tab** (visible while collapsed).
  - The download buttons carry the range: `โหลด mp4 (1:30-5:00)`, `โหลด m4a (1:30-5:00)`, `โหลด .srt (1:30-5:00)`, `โหลด .txt (1:30-5:00)`. With chapter split: `โหลด mp4 (แยก chapter)`. With SponsorBlock: `โหลด mp4 (ตัดโฆษณา)`. (Range and SponsorBlock together: `โหลด mp4 (1:30-5:00, ตัดโฆษณา)`.)
  - The size estimate ("ขนาดประมาณ …") scales to the kept duration.
- Which controls appear in which tab:

| Control | วิดีโอ | เสียง | ซับ |
|---|---|---|---|
| ช่วงเวลา (start / end) | ✓ | ✓ | ✓ |
| แยกไฟล์ตาม chapter | ✓ (only if the clip has ≥ 2 chapters) | ✓ (same) | — |
| ตัดโฆษณา (SponsorBlock) | ✓ | ✓ | — (no effect on subtitle files) |

### 1.1 Time range
- Two text fields **"เริ่ม"** and **"จบ"**. Accepted input: `ss`, `m:ss`, `mm:ss`, `h:mm:ss` (seconds precision; no decimals). Empty both = no range. One empty = the other end of the clip (empty start = 0:00, empty end = clip end).
- Next to each field a small button **"ใช้เวลาที่ตัวเล่นอยู่ตอนนี้"** (icon button with that accessible name + tooltip). It takes the player's current time rounded down to the second. Disabled until the player has started (tooltip **"กดเล่นคลิปก่อน"**).
- Under the player (W2 header, below the player box, visible only once the player has started, also in the docked mini player): two buttons **"ตั้งจุดเริ่ม"** and **"ตั้งจุดจบ"**. Pressing one sets the value, shows a toast **"ตั้งจุดเริ่มที่ {time} แล้ว"** / **"ตั้งจุดจบที่ {time} แล้ว"**, and marks the advanced section as open so it is expanded when the user goes to a download tab.
- Frame right-click menu (frames tab): two new items **"ตั้งเป็นจุดเริ่ม"** and **"ตั้งเป็นจุดจบ"** using the frame's timestamp, with the same toasts.
- Validation (inline, red text under the field, **no job is created**, button stays clickable — AC-ADV-02):
  - bad format → **"พิมพ์เวลาแบบ 1:30 หรือ 1:02:30"**
  - start ≥ end → **"จุดเริ่มต้องมาก่อนจุดจบ"**
  - beyond the clip → **"เกินความยาวคลิป ({duration})"**
  - kept length < 1 s → **"ช่วงต้องยาวอย่างน้อย 1 วินาที"**
- Live, upcoming or unknown-duration clips: fields disabled with the text **"คลิปสดหรือคลิปที่ไม่รู้ความยาว ตั้งช่วงเวลาไม่ได้"**.
- Under the fields when a range is set (video tab): hint **"ตัดตรงจุดที่ตั้งเป๊ะ ใช้เวลาแปลงไฟล์เพิ่ม"**.

### 1.2 Chapter split
- Switch **"แยกไฟล์ตาม chapter"** with hint **"ได้ไฟล์ละ 1 chapter ในโฟลเดอร์ย่อย"** (video tab adds **" · ขอบแต่ละ chapter อาจคลาด 1-3 วินาที"**).
- Hidden when the clip has fewer than 2 chapters.
- Mutually exclusive with range, SponsorBlock and embedded subtitles. Whichever is on first wins; the other control is disabled with a reason:
  - chapter switch while a range is set → **"ใช้คู่กับช่วงเวลาไม่ได้ ล้างช่วงเวลาก่อน"**
  - chapter switch while SponsorBlock is on → **"ใช้คู่กับตัดโฆษณาไม่ได้"**
  - chapter switch while embed subtitles is on → **"ใช้คู่กับฝังซับไม่ได้"**
  - range fields / SponsorBlock switch / embed-subtitles switch while chapters are on → **"ปิด 'แยกไฟล์ตาม chapter' ก่อน"**
  - Why exclusive: a range that cuts through a chapter makes the first/last chapter file ambiguous; ad cuts shift chapter boundaries; embedded subtitles per chapter is v2 (BRD).

### 1.3 SponsorBlock
- Switch **"ตัดโฆษณา (SponsorBlock)"**, off for every clip. Hint: **"ใช้ข้อมูลที่ผู้ชมช่วยกันมาร์ก คลิปที่ไม่มีข้อมูลจะได้คลิปเต็ม"**.
- When on: a checkbox list of categories (Thai label → yt-dlp category):
  - `sponsor` **"ช่วงสปอนเซอร์"** · `selfpromo` **"ช่วงโปรโมตตัวเอง"** · `interaction` **"ช่วงขอให้กดติดตามหรือไลก์"** · `intro` **"ช่วงเปิดรายการ"** · `outro` **"ช่วงปิดท้าย"** · `preview` **"ช่วงตัวอย่างหรือสรุปซ้ำ"** · `filler` **"ช่วงนอกเรื่อง"** · `music_offtopic` **"ช่วงที่ไม่ใช่เพลง (คลิปเพลง)"**
  - Default ticked = setting `sponsorblockDefault` (`["sponsor","selfpromo","interaction"]`). Changing the ticks saves them to that setting (`PATCH /settings`) — this is the cross-clip memory (D3). At least one category must stay ticked (the last one cannot be unticked).
- If SponsorBlock is on and the user also downloads subtitles or has embed subtitles on: warning text **"เวลาซับจะไม่ตรงกับวิดีโอที่ตัดโฆษณาแล้ว"** (FR-ADV-4) under the switch in the video tab (embed) and above the buttons in the subtitle tab.

### 1.4 Layout
- Narrow-window rule (BRD #83): at 640 px nothing overflows horizontally; the two time fields may stack.
- Accessibility: every field, switch, checkbox and icon button has an accessible name; errors are linked with `aria-describedby`; axe has no serious/critical findings in both themes.

## 2. Output files

All in the clip folder as today (`<output>/<clip [id]>/`), with `แหล่งที่มา.txt`. Windows forbids `:` so times use `.`.

| Choice | File name |
|---|---|
| Range (video/audio) | `<title> (01.30-05.00).mp4` / `.m4a` / `.mp3` / `.wav`; with hours `(1.02.30-1.05.00)` |
| Range (subtitle) | `<title> (01.30-05.00).<lang>.srt` / `.txt`, cues re-timed from 00:00 (AC-SUB-10) |
| SponsorBlock | `<title> (ตัดโฆษณา).mp4`; with a range `<title> (01.30-05.00) (ตัดโฆษณา).mp4` |
| No audio + range | `<title> (ไม่มีเสียง) (01.30-05.00).mp4` (order: no-audio, range, ads) |
| Chapter split | `<clip folder>/แยกตาม chapter (mp4)/01 - <chapter title>.mp4` … (`mp3`, `m4a`, `wav` likewise). Two-digit numbers; three digits when there are ≥ 100 chapters. Chapter titles are sanitised like clip titles (`files.safe_component`); empty title → `chapter <n>`; duplicates are fine because of the number prefix |

- Each output file gets the same cover/metadata treatment as today; chapter files also get `title` = chapter title and `track` = n/total.
- A second download of the same choice gets ` (2)` like today.
- The job result lists every output file (chapter split = many outputs in `JobResult.outputs`, in order).

## 3. Backend

### 3.1 Job params (additions; everything else unchanged and still strict)
- `video`: `range?: {startMs:int, endMs:int}`, `sponsorblock?: string[]`, `splitChapters: bool` (was `Literal[False]`).
- `audio`: same three.
- `subtitle`: `range?` only.
- Validation (422 `E_BAD_REQUEST`):
  - `0 ≤ startMs < endMs`, `endMs − startMs ≥ 1000`, both multiples of 1000;
  - `sponsorblock` non-empty, unique, each in the 8 categories above;
  - `splitChapters: true` with `range`, `sponsorblock` or `embedSubs` → 422;
  - when the probe is cached: `endMs` beyond the duration (+500 ms tolerance), or `splitChapters` on a clip with < 2 chapters → 422; uncached → checked again in the handler.
- W3 and every M4 caller keep sending `splitChapters: false` and no range/sponsorblock.

### 3.2 Processing (approach B)
1. Download the full media exactly as M4 does (same format choice, retries, cancel, progress).
2. Build the list of **keep intervals** on the original timeline:
   - range only → `[[start, end]]`;
   - SponsorBlock → the clip (or the range) minus the ad segments (segments merged, clipped to the range, pieces shorter than 1 s dropped);
   - chapter split → one interval per chapter, each producing its own file.
3. One cutter in `core/media.py` turns `(input, intervals, mode)` into the output:
   - **exact mode** (range and SponsorBlock, video): re-encode video H.264 + AAC in mp4 so the first frame is the frame at `start` (AC-ADV-01); several intervals are cut and joined in one ffmpeg run.
   - **exact mode, audio**: cut at sample accuracy (m4a may stay AAC copy when the cut lands within one AAC frame of the target — the planner picks the simplest command that meets ±50 ms; mp3/wav are re-encoded anyway).
   - **fast mode** (video chapter split only): stream copy, cut at keyframes (D6).
   - Then the existing M4 steps (cover, metadata, embed subtitles) run on the cut file. Embedded subtitles with a range use the range-cut subtitle (AC-VID-10 part 1).
4. Disk check covers the full download plus the cut output.
5. Cancel works during cutting like other ffmpeg steps.
6. Progress stages (queue row text): **"กำลังตัดช่วง"**, **"กำลังตัดโฆษณา"**, **"กำลังแยก chapter {i}/{n}"**, with progress from ffmpeg time.

### 3.3 SponsorBlock data
- Fetched through yt-dlp's SponsorBlock support, wrapped in `core/extractor.py` (only place that imports yt_dlp) as a `Downloader` method returning `[(startMs, endMs, category)]`. yt-dlp sends a hashed, truncated video-id prefix to the SponsorBlock API; no user data is sent.
- Notes on the finished job (new note codes):
  - no segments for the chosen categories → **"ไม่มีข้อมูลจากชุมชน ได้คลิปเต็ม"** (AC-ADV-04). Nothing was cut, so the file is named like a normal download (no `(ตัดโฆษณา)` suffix) and no re-encode happens — the name never claims a cut that did not happen;
  - SponsorBlock unreachable / error → **"ติดต่อ SponsorBlock ไม่ได้ ได้คลิปเต็ม"**, normal name, job still succeeds;
  - chapter split requested but the clip turned out to have < 2 chapters → **"คลิปนี้ไม่มี chapter ได้ไฟล์เต็ม"**, full file.
- SponsorBlock errors never trigger the bot-check brake (it is not YouTube).

### 3.4 Subtitles by range
- Tokens are filtered to the range and shifted to start at 0 **before** cue building, in both `core/srt_builder.py` and `web/src/lib/srt-builder.ts`, so file and preview stay byte-identical (AC-SUB-06). Tokens crossing a boundary are clipped (kept if their midpoint is inside, times clamped).
- The subtitle tab preview and "คัดลอกข้อความ" follow the range when one is set (preview title gets ` (1:30-5:00)`).
- `.txt` stays byte-identical to `.srt` (BRD #113).

### 3.5 Queue and history text
- Job titles in the queue/history rows append the choice: ` · ช่วง 1:30-5:00`, ` · แยก chapter`, ` · ตัดโฆษณา`.

### 3.6 Folded-in M4 follow-ups
- Lifecycle recover/sweep learns the new names (range/ads suffixes, chapter sub-folders) so interrupted jobs leave nothing behind.
- W2 download before settings are loaded (M4 follow-up "หน้า W2 กับค่าตั้ง" items 1-3), because the same download-state module is rebuilt here.

## 4. Testing
- Unit (Python + vitest): param validation matrix; keep-interval maths (range ∩ minus ads, merging, < 1 s drop); file naming incl. path budget and sanitised chapter names; subtitle range parity fixtures (Py ↔ TS byte-identical); time-field parsing/validation; button labels.
- Fake mode (`YT_TOOLKIT_FAKE=1`): FakeMediaTools implements the cutter (records intervals, writes plausible files with the right durations); a fake SponsorBlock source with fixtures for "has segments", "no segments", "unreachable".
- E2E (chromium, mocked enqueue): advanced section in each tab, shared state, badge, labels, validation, player and frame-menu buttons, exclusivity rules, warning, axe both themes, 640 px. Queue project (real fake backend): range, chapter split (many outputs), SponsorBlock notes.
- Network tests (real YouTube, **owner approval before running**, sizes stated): range on a long clip (AC-ADV-01 first-frame check), chapter split (AC-ADV-03), SponsorBlock clip with data (AC-ADV-04), embed subs with range (AC-VID-10 part 1).

## 5. Docs
- PRD: W2 component table, advanced section, job params, processing notes (replace the yt-dlp `download_ranges` / `FFmpegSplitChapters` / `sponsorblock_remove` notes with approach B), notes table, AC-ADV rows (AC-ADV-03 now also audio and sub-folder), traceability.
- BRD: FR-ADV-1..4 wording (sub-folder, audio chapters, fast video chapter cut), decisions D1-D9 as new rows after #116, followups.
- docs/acceptance.md: new M5-A section with manual checks for every decision above.

## Out of scope (round A)
Sharp frames (round B), cookies (round C), advanced options in W3, subtitle split by chapter, subtitle re-timing after SponsorBlock (v2), several ranges per download, decimal-second input.
