# M5 round B2: sharp capture at the playhead and theater mode (design)

Pete approved the design sections in conversation on 2026-10-05. This written spec is awaiting his review.

Round B2 sits between round B (sharp frames, merged as 1cd6566) and round C (opt-in YouTube cookies). It touches:
- the W2 header (player area);
- a new capture service and API;
- the extractor (partial fetch);
- settings;
- the frame context menu;
- the docs.

The Thai UI strings below are final copy. Use them verbatim.

**Why this round exists (Pete, 2026-10-05):** in how-to / step-by-step clips (UX/UI demos, prompt writing) the on-screen text is small. Viewers pause and copy what they see. The moment they need is often between two fast frames, which are about 10 s apart. They need a sharp image of exactly where the player is paused, without downloading the whole clip. The 288 px player column also makes small text hard to read, which is why theater mode is part of this round.

## Owner decisions (2026-10-05)

| # | Decision | Why |
|---|---|---|
| E1 | **Capture is instant and does not go through the queue.** The image appears in about 2-3 s, and the file is also saved to the clip folder automatically. | Pete's choice ("ทันที + ลงโฟลเดอร์ด้วย"). The user is following along with a paused clip, so waiting in a queue breaks the flow. |
| E2 | **Resolution is a setting.** The default is "สูงสุดที่มี" (highest available, up to 4K); the other choices are 1080p and 720p. | Pete's choice. Small text needs the highest resolution. A 4K capture costs about 7.5 MB and 3 s (spike). |
| E3 | **Captured images show as a strip under the player (layout ก.).** | Pete chose ข. at first, then switched to ก. after seeing it next to theater mode. The strip is visible while watching, with no tab switch. |
| E4 | **Theater mode.** Pressing play expands the player to the full content width with an animation, and the clip info moves below. **T** or a button toggles it. The app remembers the choice per computer. | Pete's idea, modelled on YouTube's theater mode (T shortcut). |
| E5 | **Portrait clips (Shorts/Reel)** in theater mode: the player is about 80% of the viewport height, on the left, with the info column on the right. | Pete's choice. A full-width portrait player would be about 1,650 px tall; centering it would waste the sides. |
| E6 | **Partial fetch via the mp4 `sidx` index** through yt-dlp's own networking: fetch the index, then only the one segment that contains the time. | Spike, 2026-10-05: `--download-sections` hung for 5 min and plain ffmpeg on the stream URL hung. The sidx method fetched 2.0 MB of 258 MB in 2.4 s at 1080p, and 7.5 MB of 712 MB in 3.2 s at 4K. The frame was correct. |
| E7 | **A user can delete a capture.** Deleting removes it from the strip, the app cache and the clip folder, after a confirmation. | Pausing at the wrong moment is common. Planner decision; Pete saw it in the design and approved. |

## 1. Theater mode (W2 header)

### 1.1 Behaviour
- **States.** The header has two layouts for the clip being viewed:
  - **compact:** today's layout, a 288 px player column on the left and info on the right;
  - **theater.**
- **Pressing ▶ in the player slot.** The layout switches to theater **if the remembered preference is theater (the default)**. Nothing changes before the first play.
- **Toggle button.** A button sits in the button row under the player.
  - Its label is **"ขยายตัวเล่น (T)"** in compact and **"ย่อตัวเล่น (T)"** in theater.
  - It has `aria-pressed` and the tooltip **"โหมดโรงภาพยนตร์"**.
  - It is visible only after the player has started.
- **Keyboard: T or t** toggles the layout when all of these hold:
  - the player has started;
  - focus is not in an input, textarea, select or contenteditable element;
  - no dialog or menu is open;
  - no modifier key is held.

  Focus inside the YouTube iframe never reaches the page, which is expected. The button covers that case.
- **Remembered preference.** Toggling stores the choice in `localStorage` under `yt-toolkit:theater` (`"1"` or `"0"`).
  - Reads and writes are wrapped in try/catch.
  - If storage is unavailable, the default is theater.
  - The preference applies the next time play is pressed, on any clip.
- **Narrow window (< 640 px, BRD #83).** The layout is already full width, so theater changes nothing. The toggle button is hidden and T does nothing.
- **Docked mini player.** It is unchanged. When the slot scrolls out of view, the docked player floats as today in both layouts.
- **Opening another clip** resets the layout to compact until play is pressed.

### 1.2 Layouts (width ≥ 640 px)
- **Landscape clip, theater:**
  - The player spans the full main column (`main` is `max-w-[960px]` with `px-4`, so about 928 px wide) at 16:9.
  - Below it come the button row (C2) and the capture strip (C3).
  - Then the title, meta, stat tiles and the button row (note / YouTube / cover / reel), in today's DOM order.
  - The tool tabs follow.
- **Portrait clip, theater:**
  - Two columns.
  - **Left:** the player, height `min(80vh, 760px)` at 9:16.
  - **Right:** `flex-1`, with the title, meta, stat tiles, the note/YouTube row, then the button row (C2) and the capture strip (C3) at the bottom.
  - The tabs follow below both columns.
- **Compact:** today's layout. The button row (C2) and the strip (C3) sit under the small player in the left column. Thumbnails wrap.
- **Portrait detection:** the clip is portrait when the highest-resolution entry in `VideoInfo.video[]` has `width` known and `width < height`. Otherwise it is landscape.
- **DOM order equals visual order** in every layout, so Tab order and screen readers match what is seen. CSS `order` is not used, following the existing header rule.

### 1.3 Animation
- The switch is wrapped in `document.startViewTransition` when it exists. The page sets `view-transition-name` on the player slot and on the info block. Duration is about 300 ms, and the easing is the app's standard ease-out.
- **No animation when** `prefers-reduced-motion: reduce` is set, or when `startViewTransition` is missing. The layout still switches instantly.
- The React state change inside the transition uses `flushSync`, so the snapshot is taken after the DOM updates. React here is ^19.2, so the stable `<ViewTransition>` component is not assumed.
- The YouTube iframe keeps playing through the switch. The player element is resized, never remounted (the existing `PlayerSlot` stays mounted).

## 2. Capturing a sharp frame at the playhead

### 2.1 Entry points
- **Button row under the player (C2):**
  - "ตั้งจุดเริ่ม" and "ตั้งจุดจบ" are already there.
  - The new button is **"ถ่ายภาพคมตรงนี้"**, with a camera icon. It uses `markTimeMs()` (the playhead, or the pending seek while loading), rounded to 100 ms.
  - It is visible only after the player has started, the same rule as the mark buttons.
- **Docked mini player:** an icon button with the same name, next to the docked mark buttons.
- **Frame context menu (fast or sharp grid):** a new item **"ถ่ายภาพคมตรงนี้"** that uses the frame's `tMs`.

### 2.2 States and copy
- **While working:** the button shows a spinner and the text **"กำลังถ่าย…"**, and it is disabled. Only one capture runs in the app at a time. All entry points share one busy flag.
- **Done:**
  - a toast **"ถ่ายภาพคมแล้ว · {time}"** with the action **"ดูภาพ"**, which opens the large image;
  - the new thumbnail is appended to the strip, in time order, with a short highlight.
- **Disabled reasons** (the button stays focusable and shows a tooltip):

  | When | Tooltip |
  |---|---|
  | live / upcoming clip | **"คลิปสดถ่ายภาพคมไม่ได้"** |
  | the queue is paused by a bot check (`QueueState.pausedUntil` set) | **"พักการโหลดอยู่เพราะยูทูปขอตรวจสอบ ลองใหม่หลัง {time}"** |

- **Errors** (toast, no partial strip item):

  | Code | Message |
  |---|---|
  | `E_CAPTURE_UNSUPPORTED` (no mp4 format with a `sidx` index) | **"คลิปนี้ถ่ายภาพคมเฉพาะจุดไม่ได้ ใช้ "ขอภาพคม" ทั้งคลิปแทนได้"** |
  | `E_CAPTURE_BUSY` | **"กำลังถ่ายภาพอื่นอยู่ รอสักครู่"** |
  | the existing `E_NETWORK`, `E_BOT_CHECK`, `E_DISK_FULL`, `E_OUTPUT_NOT_WRITABLE` | existing text |

  A capture that hits `E_BOT_CHECK` calls the queue brake, as jobs do.

### 2.3 The strip "ภาพที่ถ่ายไว้" (C3, layout ก.)
- **Header line:** **"ภาพที่ถ่ายไว้ ({n})"** and a link-style button **"เปิดโฟลเดอร์"**, which opens `<clip folder>/ภาพที่ถ่าย/`.
- **Thumbnails:** 16:9 tiles about 96 px wide, with a time badge, in time order.
  - The row wraps in the compact and portrait layouts, and is one scrollable row in landscape theater.
  - It has the same focus and keyboard rules as the frame grid: one tab stop, arrow keys, Enter opens.
  - Portrait captures are padded into the 16:9 tile.
- **No captures:** the strip is not rendered.
- **Loading:** the strip shows nothing until the list arrives. There is no skeleton, because the strip is optional.
- **Clicking a thumbnail** opens the existing lightbox with the full image, plus these actions:
  - **"คัดลอกภาพ"** and **"โหลดภาพ"** (existing frame actions);
  - **"เปิดในยูทูปตรงเวลานี้"**;
  - **"เล่นจากตรงนี้"**;
  - **"ลบภาพนี้"**. It opens a confirm dialog **"ลบภาพนี้ทั้งในแอพและในโฟลเดอร์ไหม"** with **"ลบภาพ"** / **"ยกเลิก"**. Then the toast **"ลบภาพแล้ว"**.
- **Captures persist per clip** in the app cache. The 30-day stale-cache purge removes them from the app, but the files in the clip folder stay. They also survive closing the app.

### 2.4 Resolution setting
- `captureQuality: "max" | "1080" | "720"`, default `"max"`.
- In Settings › ทั่วไป: **"ความละเอียดภาพที่ถ่าย"** with the options **"สูงสุดที่มี"** / **"1080p"** / **"720p"**, and the hint **"ภาพยิ่งละเอียด ตัวหนังสือเล็กในคลิปยิ่งอ่านง่าย ใช้เน็ตต่อภาพมากขึ้น (4K ราว 8 MB)"**.
- The cap applies to the **short side**: 1080 caps a portrait clip at 1080 wide. The image is saved at the source resolution, with no scaling.

## 3. Backend

### 3.1 Partial frame fetch (`core/extractor.py`, the only yt_dlp importer)
`fetch_frame_piece(video_id, t_ms, max_short_side, dest) -> PieceInfo{path, segment_start_ms, width, height, format_id, dynamic_range}`.

1. **Probe the clip** with the existing probe options and visitor session.
2. **Choose a format:**
   - video-only, `ext == "mp4"`, `protocol == "https"`, short side ≤ cap (no cap for `"max"`);
   - prefer the largest short side, then SDR, then avc1 > av01, then the smallest size.
   - No candidate → `E_CAPTURE_UNSUPPORTED`.
3. **Fetch bytes 0-65535** with `ydl.urlopen(Request(url, headers={**http_headers, "Range": ...}))`.
4. **Parse `sidx`** (version 0 and 1). Missing → `E_CAPTURE_UNSUPPORTED`. If the box extends past 64 KB, fetch the rest of the box.
5. **Find the reference** containing `t_ms`, then fetch `[offset, offset + size - 1]` the same way.
6. **Write `init + segment`** to `dest`.

Other rules:
- Network errors map through the existing `yterrors.classify`.
- Logs carry the video id, format id and byte counts only, never the URL, headers or paths.
- `FakeExtractor` implements the same method from a fixture mp4 piece, `tests/fixtures/capture/piece.mp4` (a few seconds of generated 1920×1080 video with a `sidx`), plus behaviours for the unsupported, network-failure and bot-check cases.

### 3.2 Capture service (`core/capture.py`, new)
`CaptureService(videos, extractor, media, cache_root, settings, queue)`:
- **`capture(video_id, t_ms) -> Capture`:**
  - Reject live clips, clips of unknown duration, and `t_ms` outside `[0, duration)`, each with a 422.
  - Reject with 409 `E_QUEUE_PAUSED` when `queue.pause_state()` is set. The message is the bot-check text above.
  - Acquire the one global capture lock **without waiting**. If it is held, return 409 `E_CAPTURE_BUSY`.
  - Fetch the piece into a temp dir under `work/`.
  - Extract with `media.extract_frame(piece, t_ms - segment_start_ms, out, long_side=None)`. `None` means no scaling; this is a small extension of T4's `extract_frame`. For HDR, the tone-map follows round B.
  - Write the cache copy `<cache>/<id>/captures/c_<tMs>.jpg` and update `captures/index.json` atomically (temp + replace, under a per-clip lock).
  - Copy into `<output>/<clip folder>/ภาพที่ถ่าย/frame_HH-MM-SS.jpg`. A second capture in the same second gets `_2`, `_3`, and so on.
  - Delete the temp dir in `finally`.
  - **If the same `tMs` already exists**, return the existing capture without fetching. This makes it idempotent.
- **`list(video_id)`** returns the captures sorted by `tMs`. Entries whose cache file is missing are dropped from the index.
- **`delete(video_id, capture_id)`:**
  - Remove the cache file and the index entry.
  - Delete the output copy **only if** the recorded path resolves under the recorded output root and still has the recorded name. This never follows symlinks and never deletes anything else.
  - A missing output file is fine.
- **Index entry:** `{id: "c_<tMs>", tMs, width, height, file, outputRoot, outputRel, createdAt}`. `outputRoot` is stored so deletion still works after the output folder setting changes. It is never logged.
- **Concurrency and pacing:** captures run outside the queue and do not count toward its concurrency setting. A capture costs one probe (usually cached) plus two ranged GETs. The protection against YouTube blocking is the global single-flight lock plus honouring the bot-check brake.

### 3.3 API
- **`GET /api/videos/{id}/captures`** returns `{captures: [{id, tMs, width, height, url}]}`. The `url` is `/api/cache/{id}/captures/c_<tMs>.jpg?v=<mtime>`, served with the same immutable rules as frames. The cache route allows the `captures` folder.
- **`POST /api/videos/{id}/captures`** takes `{tMs: int}` (strict, unknown keys → 422). It returns 201 with the capture, or the errors in §2.2. It is a sync route (threadpool), with no request body beyond `tMs`.
- **`DELETE /api/videos/{id}/captures/{captureId}`** returns 204, or 404 for an unknown id.
- **`POST /api/videos/{id}/captures/reveal`** opens the clip's `ภาพที่ถ่าย` folder. It returns 404 when the folder does not exist yet.

### 3.4 Settings
`captureQuality` uses the validator `_one_of(("max","1080","720"))`, with default `"max"`. It is exposed in `GET /api/settings`, and the web `Settings` type gains it.

## 4. Errors and edge cases

| Case | Behaviour |
|---|---|
| Clip has only webm or progressive formats (no mp4 `sidx`) | `E_CAPTURE_UNSUPPORTED` toast pointing at "ขอภาพคม" |
| Time in the last fraction of a second (no decodable frame) | Retry once at `t_ms - 100`. If there is still no frame, `E_UNKNOWN` |
| Double click / two entry points at once | The second gets `E_CAPTURE_BUSY`; the button is already disabled |
| Bot check during a capture | Error toast; the queue brake starts; all capture buttons disable with the pause tooltip |
| App closed mid-capture | The temp dir under `work/` is removed by the existing startup sweep. No index entry is written before the files exist |
| Output folder not writable / disk full | Existing error codes. The cache copy and the index entry are rolled back, so the strip never shows a capture without a folder copy |
| User deleted the folder file | The strip still shows the capture; delete works (missing file is fine) |
| Same moment captured twice | Idempotent: the existing capture is returned and flashed in the strip |

## 5. Docs to update
- **PRD:**
  - the W2 header row (theater mode, capture button, strip);
  - the API list (`/captures`);
  - the error table (`E_CAPTURE_UNSUPPORTED`, `E_CAPTURE_BUSY`, `E_QUEUE_PAUSED`);
  - the settings table (`captureQuality`).
- **BRD:** decision rows for E1-E7.
- **docs/acceptance.md:** an M5-B2 section with hands-on rows:
  - theater on play, T toggle, remembered preference;
  - the portrait layout;
  - capture at a paused moment between two fast frames;
  - the strip, the lightbox actions and delete;
  - the setting;
  - the narrow window.
- **tests/network:** a capture network test (written, run only with Pete's approval; about 2-8 MB).

## 6. Testing
- **Python units:**
  - sidx parsing: v0 and v1, a box crossing 64 KB, the time on a segment boundary, time past the end;
  - format choice (cap by short side, mp4 only, unsupported);
  - the capture service: idempotency, busy, paused, live, out of range, `_2` naming, rollback on output failure, delete safety (outside root, renamed file, symlink);
  - the API (strict body, codes, cache route for `captures`);
  - the settings key.
- **Integration (real ffmpeg):** a generated fragmented mp4 with a `sidx` (ffmpeg `-movflags +dash` or `frag_keyframe+sidx`). Pass it through the real parser and the extract path, and assert the frame matches the requested time and the source resolution.
- **Vitest:** the theater layout reducer and preference storage (including storage throwing), portrait detection, the T-key guard (inputs, modifiers, dialogs), strip ordering and keyboard model.
- **Playwright chromium (mocked):**
  - the theater switch on play;
  - T and the button;
  - the remembered preference across clips;
  - the portrait layout;
  - the narrow-window no-op;
  - reduced motion (no animation, same end layout);
  - capture: busy state, toast, strip append, lightbox actions, delete confirm;
  - the disabled states (live, paused);
  - the frame menu item;
  - axe in light and dark;
  - 640 px.
- **Playwright queue/fake backend:** one real capture against the fake extractor fixture, end to end through the API, including the folder copy.

## Out of scope (round B2)
- Reading the text out of a capture ("คัดลอกข้อความในภาพ" / OCR): noted for later.
- Captures in W3 or in bulk.
- Annotating or cropping captures.
- Theater mode on the other pages.
