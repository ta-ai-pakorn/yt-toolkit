# M5 round B2 ภาพคมตรงจุดและโหมดโรงภาพยนตร์ (sharp capture at the playhead + theater mode) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Tasks inside one wave run as parallel subagents, each in its own controller-created git worktree (see "Waves" and "Lane rules"). Every task is reviewed by a reviewer subagent before its wave closes.

**Goal:** In W2 the user pauses a how-to clip, presses "ถ่ายภาพคมตรงนี้" (under the player, on the docked mini player, or in a frame's context menu) and gets, in about 2-3 s and without downloading the clip, a sharp JPG of exactly that moment at the resolution chosen in Settings (default "สูงสุดที่มี"); the image appears in a strip "ภาพที่ถ่ายไว้" under the player and is also copied to `<clip folder>/ภาพที่ถ่าย/`. Pressing ▶ expands the player to the full content width (theater mode, animated with View Transitions, toggled with the button or **T**, remembered per computer); portrait clips get a tall player on the left with the info on the right.

**Spec:** `docs/superpowers/specs/2026-10-05-m5b2-capture-and-theater-design.md` (owner decisions E1-E7, final Thai copy, used verbatim). Spike: memory note `youtube-partial-frame-fetch.md` (sidx byte-range method, 2.0 MB / 2.4 s at 1080p, 7.5 MB / 3.2 s at 4K).

**Out of scope (round B2):** OCR of a capture ("คัดลอกข้อความในภาพ"), captures in W3 or in bulk, annotating/cropping captures, theater mode on other pages, YouTube cookies (round C).

**Architecture:**
- **Pure partial-fetch core (`core/frame_piece.py`, new, no `yt_dlp`).** Walks the top-level mp4 boxes to the `sidx` box (fetching more than the first 64 KB when needed), parses `sidx` v0/v1 into byte ranges with times, picks the segment that holds `t_ms`, and builds `init + segment` bytes. Both extractors call it with a `read_range(first, last)` callback; it also holds the capture format chooser (video-only mp4 over https, short side ≤ cap, largest, SDR, avc1 > av01, smallest).
- **Network in `core/extractor.py` only.** `YtDlpExtractor.fetch_frame_piece` probes fresh (stored probes drop format URLs), chooses the format and does ranged GETs through `ydl.urlopen(Request(url, headers={**http_headers, "Range": ...}))`; errors map through `classify`; logs carry id, format id and byte counts only. `FakeExtractor.fetch_frame_piece` cuts the same way from the committed fixture `tests/fixtures/capture/piece.mp4` (4 s, 1 s segments) and honours `captureError` in `behaviors.json`.
- **Capture service (`core/capture.py`, new).** Validates (live / unknown duration / out of range → 422), returns an existing `c_<tMs>` without fetching (idempotent), refuses while the queue is paused by a bot check (409 `E_QUEUE_PAUSED`) or while another capture runs (409 `E_CAPTURE_BUSY`, one global non-blocking lock), fetches into `work/capture-<uuid>/`, extracts with `media.extract_frame(..., long_side=None)` (no scaling; retry once 100 ms earlier), writes the cache copy, then the folder copy (`frame_HH-MM-SS[_n].jpg`), then the index entry last; a folder failure rolls the cache copy back. Delete removes the folder copy only when it is still the recorded file under the recorded root (no links followed), then the cache copy and the entry. A bot check brakes the queue.
- **API (`api/captures.py`, new):** `GET/POST /videos/{id}/captures`, `DELETE /videos/{id}/captures/{captureId}`, `POST /videos/{id}/captures/reveal`; the cache route serves `captures/c_<tMs>.jpg` immutable with a `frame_HH-MM-SS.jpg` download name. Setting `captureQuality` (`"max" | "1080" | "720"`, default `"max"`).
- **Web:** a pure theater model (`theater.ts`: reducer, storage, portrait detection, T-key guard, View Transition runner) and hook (`use-theater.ts`); `VideoHeader` renders three layouts (compact / theater-wide / theater-tall) with the same element tree up to `PlayerSlot`, so the iframe is resized, never remounted. Capture UI in `pages/video/capture/` (API + pure model + a tiny shared store for the one-at-a-time busy flag and "open/flash this capture" signals + button, menu item and strip with lightbox actions and delete confirm), mounted in the header, the controls row, the docked toolbar and the frame context menu. Settings › ทั่วไป gains a select.

**Tech Stack:** unchanged (Python 3.13 + uv, FastAPI, pydantic v2, yt-dlp 2026.08.19 as a library, ffmpeg 8.1 from `bin/` or PATH, Pillow, React ^19.2 + Vite + Tailwind v4 + shadcn/Base UI + react-query 5 + sonner, Vitest (node, no jsdom), Playwright). No new Python or npm dependency.

---

## Owner decisions (from the spec, 2026-10-05)

| # | Decision | Where in this plan |
|---|---|---|
| E1 | Capture is instant, outside the queue; the file is also saved to the clip folder | C7 `CaptureService` (lock, no queue), C11 API, T7, T11 |
| E2 | Resolution is a setting: "สูงสุดที่มี" (default) / 1080p / 720p, cap on the short side, no scaling | C1 `captureQuality`, C2 `CAPTURE_SHORT_SIDES`/`pick_capture_format`, C3 `long_side=None`, T1, T2, T3, T10 |
| E3 | Captures show as a strip under the player (layout ก.) | C8 `CaptureStrip`, C13 placement, T8, T13 |
| E4 | Theater mode on ▶ (if remembered), T / button toggles, remembered per computer | C5 theater model, C9 header, T5, T9 |
| E5 | Portrait theater: player ~80% viewport height on the left, info on the right | C5 `isPortraitVideo`/`headerLayout`, C9 `theater-tall`, T5, T9 |
| E6 | Partial fetch via `sidx`, through yt-dlp's networking | C2, C6, T2, T6 |
| E7 | A capture can be deleted (strip, app cache, clip folder) after a confirm | C7 `delete`, C11 `DELETE`, C8 lightbox, T7, T8, T11 |

### Planner decisions (not owner questions; Pete can still object)
- **Pure sidx/format code lives in a new `core/frame_piece.py`** (no `yt_dlp` import): it is unit-testable byte maths shared by the real and the fake extractor; `core/extractor.py` stays the only `yt_dlp` importer and only adds the ranged GETs.
- **A capture always probes fresh** inside `fetch_frame_piece`: the stored probe drops format URLs (`videos._MEDIA_FIELDS`) and signed links expire after hours; W2's cached `VideoInfo` is used only for duration, live status and title.
- **No mp4 candidate under the cap → the smallest short side above it** (a resolution setting never makes a capture fail); no mp4/https video-only format at all → `E_CAPTURE_UNSUPPORTED`.
- **Segment lookup:** a time before the first segment uses the first one, a time exactly on a boundary uses the later segment, a time past the index end is `E_UNKNOWN` (the service already rejects times ≥ duration).
- **Write order is cache copy → folder copy → index entry** (spec 3.2 + §4 "no index entry is written before the files exist"); a folder failure deletes the cache copy, so the strip never shows a capture without a folder copy.
- **Idempotency is checked before the pause/busy checks** (it needs no network): an existing `c_<tMs>` answers 200 with the same body, a new one 201; the web flashes the tile either way.
- **422 rejections** (live, unknown duration, `tMs` outside `[0, duration)`) answer `E_BAD_REQUEST` with the standard bad-request text through a `CaptureRejected` exception (that code is not in `MESSAGES`, so it cannot be a `YtError`).
- **HTTP status of the new/used codes on capture routes** (added to `STATUS_BY_CODE`): `E_CAPTURE_UNSUPPORTED` 422, `E_CAPTURE_BUSY` 409, `E_QUEUE_PAUSED` 409, `E_FFMPEG_MISSING` 409, `E_DISK_FULL` 507, `E_OUTPUT_NOT_WRITABLE` 409. The service brakes the queue on `E_BOT_CHECK`; the router does not call `on_bot_check` again.
- **`{time}` in "…ลองใหม่หลัง {time}"** is the clock time `HH:MM` (backend: Asia/Bangkok; web: the computer's clock). `YtError.message` only fills templates listed in `MESSAGES_NO_PARAMS`, so `E_QUEUE_PAUSED` gets the existing `E_BOT_CHECK` text as its no-params fallback (no new copy).
- **ffmpeg missing → `E_FFMPEG_MISSING` before any network request.**
- **Width/height of a capture are read from the written JPEG** (Pillow), not from the format (fake mode copies `cover.jpg`).
- **Delete order:** folder copy first (a file locked by an image viewer → `E_OUTPUT_NOT_WRITABLE`, nothing changed), then the cache copy and the entry. A missing folder copy is fine.
- **"เปิดโฟลเดอร์"** opens the folder of the newest capture whose folder copy still exists, else the folder planned from the current output setting if it exists, else 404.
- **Error copy of `E_CAPTURE_*` / `E_QUEUE_PAUSED` lives only in `core/yterrors.MESSAGES`**; the web shows the server's message (single source, like every other API error). `th.ts` gets the UI copy only.
- **Lightbox actions reuse the existing frame action strings** (spec 2.3 "existing frame actions"): `th.frames.copyImage` "คัดลอกภาพ", `th.frames.downloadFrame` "โหลดภาพนี้", `th.frames.openYoutubeAt`, `th.frames.playFrom`. Thumbnail alt and lightbox label reuse `th.frames.frameAlt` ("ภาพเฟรมที่ {time}"). No invented Thai.
- **Capture times show tenths when not whole** ("2:05.4"; whole seconds "2:05") in the toast and the tile badge: captures are 100 ms precise and two captures in one second must be told apart.
- **Strip keyboard model = spec 2.3 literally:** one Tab stop (roving `tabIndex`), ←/→/↑/↓/Home/End move, Enter/Space open. The frame grid keeps its current one-stop-per-tile model (unchanged).
- **Theater is triggered only by ▶ in the player slot** (spec 1.1); "เล่นจากตรงนี้" from frames/transcript does not switch (the layout would jump above the user's scroll position). Closing the player keeps the current layout.
- **View-transition names exist only during a switch** (`html[data-theater-switching]`), and there is no animation while the slot is docked (off-screen) or under reduced motion; the layout still switches.
- **Shift is not a blocking modifier for T** (Shift+T yields "T", which the spec allows); Ctrl/Alt/Meta and key repeat block it; any open `dialog`/`alertdialog`/`menu`/`listbox` blocks it.
- **Chromium e2e default storage `yt-toolkit:theater = "0"`** (playwright.config `storageState`): existing specs press ▶ and assert compact geometry; `theater.spec.ts` and capture specs opt in explicitly. The `queue` project keeps the real default (theater).
- **The strip renders whenever captures exist** (before play too); compact = under the controls in the left column, theater-wide = one scrollable row under the controls, theater-tall = bottom of the info column, narrow = right after the narrow controls row.
- **Context-menu item** lives inside `ContextMenuContent` (mounted only while the menu is open, so no per-tile subscription) and is disabled while busy or blocked (menus show no tooltip).
- **`useCapture` reads `isLive` from the `["video", id]` cache** (no prop threading through the frame grid and the docked toolbar).
- **Portrait detection:** the `VideoInfo.video[]` entry with the largest `height` (tie: largest `width`) has a known `width` and `width < height`.
- **The capture fixture is committed** (`tests/fixtures/capture/piece.mp4`, ~50 KB, exact ffmpeg command in `tests/fixtures/README.md`); tests never regenerate it. Synthetic boxes in Python cover sidx v0, a box crossing 64 KB, nested references and bad boxes.
- **Fake clips** (`behaviors.json`, all `probeAs` BBB): `CAPTURE0001` (works), `CAPTURENO01` (`captureError: E_CAPTURE_UNSUPPORTED`), `CAPTUREBOT1` (`E_BOT_CHECK`), `CAPTURENET1` (`E_NETWORK`). The fake maps any `t_ms` onto the 4 s fixture with `t_ms % 4000` and shifts the segment start back to clip time.
- **Error details never carry the media URL:** an `HTTPError` detail is `HTTP Error <status>`, a `RequestError` detail is its class name.

## Questions for the owner

None blocking. Every ambiguity is ruled above.

**Owner inputs needed before the network run (T15 writes the test, nobody runs it without approval):**
1. Approval to run `tests/network/test_capture_network.py`: two captures of `aqz-KE-bpKQ` (one at the 1080 cap, one at "max"), about 2-8 MB in total, deleted after the run.

---

## Waves

Integration branch: `m5b2-capture-theater` (already checked out in the main checkout; the spec is commit `e044969`).

| Wave | Lanes (one worktree each, file sets disjoint) | Depends on |
|---|---|---|
| 1 | T1 `captureQuality` + capture error copy · T2 pure sidx/format module + fixture · T3 `extract_frame(long_side=None)` · T4 web strings + types · T5 web theater model (pure) | spec |
| 2 | T6 extractor `fetch_frame_piece` (real + fake) + fake clips · T7 capture service + real-ffmpeg integration · T8 web capture data, store, hook, button, menu item, strip · T9 theater layout in the header (+ toggle, CSS, e2e) · T10 settings select | gate 1 (T6←T2 · T7←T1,T2,T3 · T8←T4 · T9←T4,T5 · T10←T4) |
| 3 | T11 capture API + cache route + app wiring · T12 lifecycle wiring · T13 mount capture in W2 + capture e2e (mocked) · T14 queue e2e (real fake backend) · T15 docs + network test (written, not run) | gate 2 (T11←T6,T7 · T12←T6,T7 · T13←T8,T9 · T14←T11,T12,T13 (runs at the final gate) · T15←all) |
| final | controller: merge, full checks, `npm run build`, `npm run e2e`, commit `web/dist`, reviews, live preview for Pete | gate 3 |

**Critical path:** T2 → T7 → T11 → final gate (`queue` e2e project).
**Counts:** 3 waves + final gate · 15 tasks (= 15 lanes: 5 + 5 + 5).

### Lane rules (every task)
1. **Worktree and branch.** The controller creates one worktree per lane **before** dispatching it: `git worktree add .claude/worktrees/m5b2-<lane> -b m5b2/t<N>-<slug> m5b2-capture-theater` (branched from the head of `m5b2-capture-theater` at the start of the wave), and gives the lane its absolute path as `WORKTREE`. The harness option `isolation: "worktree"` is unreliable and is **not** used. The lane starts **every** shell command with `cd "$WORKTREE" &&` (the shell does not keep the directory between calls) and edits files only by their absolute path under `WORKTREE`. Never switch the main checkout's branch; never edit files outside `WORKTREE`.
2. **Files.** A task creates or modifies **only** the files in its **Files** list. Needing another file is a plan bug: stop and report it to the controller; do not edit the file.
3. **Shared files have exactly one owner per wave:**

   | File | W1 owner | W2 owner | W3 owner |
   |---|---|---|---|
   | `src/yttoolkit/core/settings.py`, `core/yterrors.py`, `tests/unit/test_settings.py`, `tests/api/test_settings_api.py` | T1 | — | — |
   | `tests/unit/test_yterrors.py` | T1 | — | T15 |
   | `src/yttoolkit/core/frame_piece.py`, `tests/unit/test_frame_piece.py`, `tests/fixtures/capture/**` | T2 | — | — |
   | `tests/fixtures/README.md` | T2 | T6 | — |
   | `src/yttoolkit/core/media.py`, `tests/unit/test_media_args.py`, `tests/integration/test_sharp_ffmpeg.py` | T3 | — | — |
   | `web/src/i18n/th.ts`, `web/src/lib/types.ts`, `web/src/lib/download-options.test.ts`, `web/src/lib/download-prefs.test.ts`, `web/src/pages/video/advanced/use-advanced-choice.test.ts` | T4 | — | — |
   | `web/src/pages/settings/general-form.test.ts` | T4 (fixture line) | T10 | — |
   | `web/src/pages/video/theater.ts`, `theater.test.ts` | T5 | — | — |
   | `src/yttoolkit/core/extractor.py`, `tests/fixtures/downloads/behaviors.json`, `tests/unit/test_extractor_download.py`, `tests/unit/test_extractor_capture.py` | — | T6 | — |
   | `src/yttoolkit/core/capture.py`, `tests/helpers_capture.py`, `tests/unit/test_capture.py`, `tests/integration/test_capture_ffmpeg.py` | — | T7 | — |
   | `web/src/pages/video/capture/**` | — | T8 | — |
   | `web/src/pages/video/header.tsx`, `web/src/pages/video/player/player-slot.tsx` | — | T9 | T13 |
   | `web/src/pages/video/use-theater.ts`, `theater-toggle.tsx`, `web/src/index.css`, `web/playwright.config.ts`, `web/e2e/theater.spec.ts` | — | T9 | — |
   | `web/src/pages/settings/general-panel.tsx`, `general-form.ts`, `web/e2e/settings-general.spec.ts` | — | T10 | — |
   | `src/yttoolkit/api/captures.py`, `api/videos.py`, `src/yttoolkit/app.py`, `tests/api/test_captures_api.py`, `tests/api/test_videos_api.py` | — | — | T11 |
   | `src/yttoolkit/lifecycle.py`, `tests/unit/test_lifecycle.py` | — | — | T12 |
   | `web/src/pages/video/frames.tsx`, `web/e2e/capture.spec.ts`, `web/e2e/video.spec.ts`, `web/e2e/sharp-grid.spec.ts`, `web/e2e/transcript.spec.ts` | — | — | T13 |
   | `web/e2e/queue-capture.spec.ts` | — | — | T14 |
   | `PRD.md`, `BRD.md`, `docs/**` (except this plan), `tests/network/test_capture_network.py`, `tests/network_videos.toml` | — | — | T15 |
   | `web/dist/**` | final gate only; **no lane builds into or commits `web/dist`** | | |

   A lane that needs a Thai string that is not in C4 stops and asks the controller; the controller adds it at the gate (T4 is the only writer of `th.ts`).
4. **Tests.**
   - Python lanes run their own tests, then the full `uv run pytest -q -W error -p no:cacheprovider`.
   - Web lanes run `cd "$WORKTREE/web" && npm run typecheck && npm run lint && npm test`.
   - Lanes **do not run Playwright.** Specs are written, typechecked and linted in the lane and run at the gates by the controller.
   - The `queue` Playwright project is **always** run with `--workers=1` (the npm `e2e` script does this: `playwright test --project=chromium && playwright test --project=queue --workers=1 --pass-with-no-tests`); never run it in parallel and never run two Playwright invocations at once.
   - **No spec in the default `chromium` project may create a real job, a real capture or change real settings.** A chromium spec that triggers a capture mocks `/api/videos/<id>/captures*` with `page.route` first; one that clicks an enqueue button calls `mockEnqueue(page)`; one that flips a setting uses `stubSettings`. Real captures only in `queue-capture.spec.ts` (fake backend, never YouTube).
   - Network tests (`@pytest.mark.network`) are written in T15 and **never run** without Pete's approval. No lane makes any request to YouTube.
5. **Processes.** No lane starts a server. Never touch the owner's app on port 8787. Kill processes by PID only. Never `shell=True`.
6. **Commits.** Every commit message ends with exactly `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>` (this overrides any harness default trailer). Use `git commit -F- <<'EOF' … EOF`.
7. **Line endings.** Never change a file's existing line endings: edit with the Edit tool (or `open(..., newline="")`); new text files are LF. The mp4 fixture is binary (git's `text=auto` detects it, like `tests/fixtures/media/video.mp4`).

### Wave gate procedure (controller, serial)
1. Merge every lane branch of the wave into `m5b2-capture-theater` with `git merge --no-ff m5b2/t<N>-<slug>`. A merge conflict means the plan is wrong: stop and report. Then `git worktree remove .claude/worktrees/m5b2-<lane>` for each merged lane.
2. `uv sync --frozen && uv run pytest -q -W error -p no:cacheprovider` (must pass; real-ffmpeg tests run on the dev machine).
3. `cd web && npm ci && npm run typecheck && npm run lint && npm test`.
4. Gate 2 (recommended, not committed): `cd web && npm run build && npx playwright test --project=chromium e2e/theater.spec.ts e2e/settings-general.spec.ts` to catch header/settings failures before wave 3; failures go back to T9/T10 as a fix round. Do **not** commit `web/dist` at gate 1 or 2.
5. Run the two-stage review (spec compliance, then code quality) from superpowers:subagent-driven-development on each task of the wave, and fix findings in the owning lane before the next wave.

### Final gate (controller, after wave 3)
1. Merge T11-T15 (`--no-ff`), then steps 2-3 above.
2. `cd web && npm run build` then `npm run e2e` (project `chromium` on `E2E_PORT` (8799), then project `queue` on `E2E_PORT + 1` with `--workers=1`, both fake mode, built `dist`). A failing `queue-capture.spec.ts` goes back to T11/T12/T13/T14; chromium failures to T9/T13 (header, strip) or T10 (settings).
3. Check total JS gzip ≤ 400 KB excluding fonts (PRD 6.5).
4. Commit the rebuilt `web/dist` as `build(web): web/dist after M5 round B2` (with the trailer).
5. Reviews as in step 5 above, then a live preview for Pete on port 8791 in fake mode (memory rule "preview after QA"): theater on ▶, T, the narrow window, capture on `CAPTURE0001`, the strip, the lightbox, delete, the setting. A portrait clip and real captures against YouTube only with his approval.

---

## Verified facts (read or measured on 2026-10-05 in this repo)
- **Branch** `m5b2-capture-theater`, head `e044969` (spec commit). `.gitattributes` is `* text=auto eol=lf`; `git ls-files --eol` shows `i/-text` for `tests/fixtures/media/video.mp4` (binary auto-detected) and `i/lf` for `.py`/`.ts`.
- **Extractor.** `core/extractor.py:49-55` `_PROBE_OPTS`; `:48` `_ANSI`; `:101-106` `check_live` (raises `E_LIVE_NOT_READY` for `is_live`/`is_upcoming`); `:109-112` `_check_video_id`; `:490-503` `YtDlpExtractor._ydl(opts, with_session=)`; `:554-581` `fetch_subtitle` maps `HTTPError` 429 → `E_BOT_CHECK`, other `HTTPError`/`RequestError` → `E_NETWORK`, `YoutubeDLError` → `classify`; `:684-701` `_extract_for_download` uses `ydl.sanitize_info(raw)`; `:741-1003` `FakeExtractor` (`calls` `:762`, `probe` with `probeAs`/`title` `:771-791`, `_behavior` `:865-867`). `tests/unit/test_extractor_download.py:34-63` holds the literal `C14` and `:120` asserts it equals `behaviors.json` (T6 must update both). `tests/unit/test_extractor.py:299-336` `FakeYDL` pattern (monkeypatch `yt_dlp.YoutubeDL`).
- **yt-dlp networking** (`uv run python`): `Request(url, data=None, headers=None, …)`, `Response(fp, url, headers, status=200, …)`, `Response.read(amt=None)`, `HTTPError(response)`; `str(HTTPError)` is `HTTP Error <status>: <reason>` → `classify` gives `E_BOT_CHECK` (429), `E_YT_REFUSED` (4xx), `E_NETWORK` (5xx).
- **Media.** `core/media.py:36` `SHARP_LONG_SIDE = 1280`; `:137-146` `MediaTools.extract_frame(src, dst, t_ms, *, long_side: int, dynamic_range, cancel) -> bool`; `:344-346` `scale_filter`; `:349-357` `tonemap_filter`; `:360-367` `_check_frame` (`long_side < 1` raises; `None` would `TypeError`); `:370-384` `frame_args` always adds `-vf <scale>`; `:599-624` `FfmpegTools.extract_frame` returns `False` when ffmpeg ends `E_UNKNOWN` (no image); `:627-635` `FrameCall.long_side: int`; `:754-771` `FakeMediaTools.extract_frame` copies `cover.jpg`, `frame_limit_ms` makes it return `False`. Tests: `tests/unit/test_media_args.py:406-515`, `tests/integration/test_sharp_ffmpeg.py:16-35` helpers (`_ffmpeg`, `_tools`, `_clip`).
- **Files.** `core/files.py:27` `PATH_LIMIT = 240`; `:60-62` `_u16` (private); `:65-75` `safe_component`; `:103-128` `plan_output(root, title, video_id, suffix, ext, group)` (the clip folder is `.parent`); `:299-308` `ensure_output_root` (`E_OUTPUT_NOT_WRITABLE`). `core/frames.py:67` `file_timecode(ms)` → `HH-MM-SS`.
- **Queue.** `core/queue.py:50-53` `PauseState(until: datetime, reason: str)`; `:494-501` `brake(reason="E_BOT_CHECK")`; `:512-521` `pause_state()`; `:550-556` `recover()` → `:580-594` `_empty_work_root()` removes **every** child of `work/` (covers `work/capture-*` left by a crash); `shutdown()` `:578` does the same.
- **Settings.** `core/settings.py:32` `VIDEO_DEFAULTS`; `:80-84` `_one_of` (exact type, so `1080` int is rejected for `"1080"`); `:150-164` `_VALIDATORS`; `:170-186` defaults (`autoSharpFrames` `:181`). Key lists that must gain `captureQuality`: `tests/api/test_settings_api.py:10-26` `SETTING_KEYS`, `tests/unit/test_settings.py:25-50` defaults dict; web Settings literals `web/src/lib/download-options.test.ts:591`, `web/src/lib/download-prefs.test.ts:23`, `web/src/pages/settings/general-form.test.ts:20`, `web/src/pages/video/advanced/use-advanced-choice.test.ts:23`. `web/e2e/settings-general.spec.ts:72-84` test "พร้อมหกช่อง" lists the fields; `:49-61` `stubSettings` reads the real settings (no literal).
- **Errors.** `core/yterrors.py:15-43` `MESSAGES`; `:47-49` `MESSAGES_NO_PARAMS`; `:156-169` `YtError.message` fills `{…}` only for codes in `MESSAGES_NO_PARAMS`. `tests/unit/test_yterrors.py:25` `PRD_PENDING`; `:130-146` PRD check replaces only `{size}`; `:174-177` every templated message needs a no-params entry.
- **Videos.** `core/videos.py:68-83` `_MEDIA_FIELDS` (no `url`, no `http_headers`, no `protocol`): stored probes cannot be used to fetch; `:434-446` `VideoInfo` `title`, `durationS`, `isLive = live_status == "is_live"`; `:576` `VideoService.get(video_id, refresh=False, peek=False)`; `:625-630` `peek_cached(video_id)` (no probe).
- **API.** `api/videos.py:53-72` `STATUS_BY_CODE`; `:118-148` `yt_error_response(exc, subject, *, on_bot_check=None)` (unknown codes are sent as `E_UNKNOWN`, status default 500); `:77` `_CACHE_PART` already accepts `captures/c_125400.jpg`; `:304-317` `cache_file` marks only `storyboard`/`sharp` `f_NNNN.jpg` immutable; `:376-385` `_frame_download_name`. `api/errors.py:18` `BAD_REQUEST_MESSAGE`; `:62-65` `error_response`; `:72-73` 404 → `E_NOT_FOUND`; `:77-81` body validation → 422 `E_BAD_REQUEST`. `api/jobs.py:85-86` `_Strict` (`extra="forbid"`); `:450-458` reveal uses `(ctx.open_folder or ctx.plat.open_folder)`. `app.py:38-70` `AppContext`; `:73-90` `create_app` includes routers only when their service is set. `tests/api/conftest.py:14-35` `make_client(**overrides)`; `tests/api/test_videos_api.py:45-70` `services`/`api` fixtures, `:382`/`:1035` immutable assertions. No test enumerates routes.
- **Lifecycle.** `lifecycle.py:258-269` `Services`; `:272-345` `open_services` (fake → `FakeExtractor` `:281`, `FakeMediaTools` `:301-302`; `QueueRunner(..., work_root=paths.work)` `:320-328`; `deps.on_bot_check = queue.brake` `:331`); `:708-731` `_run_server` builds `AppContext(...)`; fake mode sets `ctx.open_folder = _fake_open_folder` `:733-736`. `tests/unit/test_lifecycle.py:733` `_run_capturing_ctx(paths, fake_platform, monkeypatch, ready=True, **extra)`; `:1319-1326` ctx field test pattern.
- **Fixtures.** No portrait probe fixture exists; `aqz-KE-bpKQ` (BBB) is 635 s, max 3840×2160; behaviors clips today: `SLOWDOWNLD1-4, BOTCHECKDL1, NETRETRYDL1, REFUSEDDL01, RANGECLIP01, ADSCUTCLIP1, ADSNODATA01, ADSOFFLINE1, CHAPTERS001, SHARPCLIP01, AUTOSHARP01`.
- **ffmpeg 8.1 experiments (scratchpad, Gyan full build):**
  - `ffmpeg -f lavfi -i "testsrc=size=1920x1080:rate=10:duration=4" -c:v libx264 -preset veryslow -crf 40 -bf 0 -g 10 -keyint_min 10 -sc_threshold 0 -pix_fmt yuv420p -an -movflags +frag_keyframe+empty_moov+default_base_moof+global_sidx -fflags +bitexact -flags:v +bitexact out.mp4` → 50,545 bytes; boxes `ftyp` (28) · `moov` (752) · `sidx` v1 at offset 780, timescale 10240, earliest 0, first_offset 0, 4 references of 10240 units (1 s) · `moof`+`mdat` × 4 · `mfra`; `ffprobe` start 0.000, duration 4.0. With B-frames (default `-bf`) `earliest_presentation_time` is 2048 (0.2 s) and the file starts at 0.2 s.
  - A piece = bytes `[0, sidx end)` + one segment: `ffprobe` start_time of the piece = the segment start (tfdt); `ffmpeg -ss (t - segStart) -i piece.mp4 -frames:v 1 -q:v 2` gives exactly the frame of `ffmpeg -ss t -i full.mp4 …` (mean abs diff 0.0 at t = 0, 1.0 (boundary), 2.55); with no `-vf` the output is 1920×1080 (no scaling). `-ss 0.95` on the last segment (t = 3.95, last frame at 3.9) writes no image (the `E_UNKNOWN` → `False` path).
- **Web.** `web/src/pages/video/header.tsx:42-49` `LAYOUT`/`COVER`/`PLAYER_COLUMN`/`FULL_ROW`/`TOUCH`; `:246-315` `VideoHeader` (early returns for loading/error; `PlayerSlot` is the first child of the `PLAYER_COLUMN` div `:286-289`; narrow controls after `h1` `:301`). `player/player-slot.tsx:25` private `reducedMotion`; `:142-181` `DockToolbar` (`RangeMarkButtons size="xs"` `:163`); `:222-307` `PlayerSlot` (▶ `onClick={() => playerActions.playFrom()}` `:282`, slot class `aspect-video` `:270`); `:314-345` `PlayerControls`/`ControlsRow` (`RangeMarkButtons` `:342`). `player/player-store.ts:79-81` `markTimeMs()`; `:190-196` `usePlayerValue`. `frames.tsx:61-85` module-private `copyFrameImage`, `downloadWithToast`, `openInYoutube`, `frameDownloadUrl`; `:255-294` `ContextMenuContent` (`playFrom` item `:276-279`); each frame tile is its own Tab stop (`:207-216`, no roving tabindex). `lightbox.tsx:32-80` `Lightbox` renders `children` inside the popup after the image; `:105-113` arrow keys in `FrameLightbox`. `components/layout.tsx:91` `main` is `mx-auto max-w-[960px] px-4`. `lib/api.ts:25-50` `api<T>()` throws `ApiError(status, code, message, detail)` with the server message; a 204 body parses to `null`. `lib/jobs.ts:18` `QUEUE_KEY`, `:33-41` `queueQuery()`. `lib/types.ts:22-31` `VideoFormat`, `:53-77` `VideoInfo`, `:306` `QueueState`, `:308-324` `Settings`. `i18n/th.ts:162-200` `frames` (`frameAlt`, `copyImage`, `imageCopied`, `copyImageFailed`, `downloadFrame`, `preparing`, `openYoutubeAt`, `playFrom`), `:512-529` `general`, `:540` `fill`. `lib/use-narrow-screen.ts` narrow = `(width < 40rem)`. `components/theme-provider.tsx:34-40` wraps `window.localStorage` in try/catch. `components/queue/pause-alert.tsx:17-24` `useNow` interval pattern. `pages/video/errors.ts:24-31` `hasCode`, `errorMessage`. `components/ui/alert-dialog.tsx:174-187` exports (`AlertDialogContent` forwards Popup props incl. `finalFocus`). `components/ui/button.tsx:21-33` sizes `xs`, `sm`, `icon-xs`, `icon-sm`. lucide-react has `Camera`, `Expand`, `Shrink`, `FolderOpen`, `Trash2`. TypeScript `~6` declares `document.startViewTransition`; React `^19.2.8`; `eslint-plugin-react-hooks ^7.1.1` recommended (purity / set-state-in-effect rules: no `Date.now()` in render, no synchronous `setState` in effects).
- **E2E menu lists.** The frame context menu's items are asserted as full lists in `web/e2e/video.spec.ts:19-28` (`MENU_ITEMS`), `web/e2e/transcript.spec.ts:21-31` (`M2_MENU`, `MENU_WITH_SUBS`) and `web/e2e/sharp-grid.spec.ts:72-75`; `player-sync.spec.ts:148-151` reads items 4-5 by index.
- **E2E.** `web/playwright.config.ts:29-44` projects `chromium` (ignores `queue-*`) and `queue`; `package.json:13` `e2e` = chromium then `--project=queue --workers=1`. `e2e/fake-yt.ts:145-172` `installFakeYT(page, {durationS, rate, …})`, `:174-181` `fakeYTLog(page)` (`players` count). `e2e/sharp-grid.spec.ts:17-38` mocks JSON + images with `page.route` and `COVER = path.join(import.meta.dirname, "../../tests/fixtures/media/cover.jpg")`. Existing chromium specs press ▶ and assert compact geometry (`player.spec.ts:88-135, 196-211, 386-420`, `range-marks.spec.ts`, `player-sync.spec.ts`, `replayed-filter.spec.ts`, `video-tabs.spec.ts`, `clip-info.spec.ts`, `video.spec.ts`).
- **Docs anchors.** `PRD.md:186-206` player bullets end with `- **ไม่อยู่ใน M3.5:**`; `:569-593` API table (row `| GET | \`/videos/{id}/pinned-comment\``); `:714-731` settings (`autoSharpFrames` `:726`); `:763-805` errors (`E_NO_SHARP_FRAMES` `:782`). `BRD.md:983` last decision row `| 136 |`. `docs/acceptance.md:109` section `## M5 รอบ B (ทำบน Windows 10/11 กับยูทูปจริง)` (last). `tests/network/test_sharp_network.py` header/skip pattern; `tests/network_videos.toml` sections.

---

## Global Constraints
**Carried over:** every Global Constraint of `docs/superpowers/plans/2026-10-01-m4-downloads.md` (and through it M3, M2, M1): Python 3.13 + uv; bind `127.0.0.1` only; error envelope `{"error":{"code","message","detail"}}`; `pathlib` everywhere; `core/` never imports `api/` or `platform/`; every screen has loading / empty / error / normal; no TODO comments; unit and API tests never touch the network; network tests carry `@pytest.mark.network`; all web strings live in `web/src/i18n/th.ts`; backend user-facing messages live in `core/yterrors.MESSAGES` and `core/jobs.NOTES`; never log an absolute output path; at most one amber primary button per page (W2: "โหลด mp4").

**Project rules (owner, verbatim):**
- Commit messages end exactly with "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>".
- Never `shell=True` (no `os.system` / `os.popen`; external programs get an argument list).
- Only `yttoolkit.platform` checks the OS.
- `yt_dlp` is imported only in `core/extractor.py`.
- No personal data, tokens or cookie values in logs.
- Kill processes by PID only.
- Never touch the owner's app on port 8787.
- Thai UI copy only from the spec (buttons start with a verb, no "กรุณา", no "!").
- Narrow-window rule BRD #83: check at 640 px (a narrow desktop window / 200% zoom), not phones; nothing overflows horizontally (`document.documentElement.scrollWidth <= clientWidth`); no new phone-only polish.
- Chromium-project e2e specs never create real jobs (`mockEnqueue`); real jobs only in `queue-*.spec.ts`.
- Python edits on Windows must preserve CRLF line endings (blobs are CRLF, core.autocrlf=true) — use the Edit tool or `newline=''`. (Verified fact: tracked `.py` files are currently LF; the rule is applied as "never change a file's existing line endings".)
- Do not build/commit `web/dist` in lanes (the controller builds at the end).

**M5-B2 specific:**
- No request to YouTube from any lane, test or e2e spec (network tests are written only). Chromium specs mock every capture route; the `queue` project captures only against `FakeExtractor` and the committed fixture.
- One capture at a time in the whole app (backend lock + web busy flag); captures never go through the queue and never count toward its concurrency; a capture honours the bot-check pause and triggers the brake on `E_BOT_CHECK`.
- Logs of the capture path carry the video id, the format id, byte counts and error codes only: never the media URL, request headers, cookies, file paths or the output root (`outputRoot` is stored in the index, never logged).
- Delete never follows a symlink or junction, never deletes outside the recorded output root, never deletes a file whose name differs from the recorded one.
- The theater switch never remounts `PlayerSlot` (the iframe is resized, not reloaded); DOM order equals visual order in every layout (no CSS `order`); `localStorage` access is wrapped in try/catch.
- Accessibility: the toggle has `aria-pressed` and a tooltip; disabled capture buttons stay focusable with a tooltip reason; the strip is a labelled list with one Tab stop; the delete confirm is an `alertdialog`; axe has no serious/critical findings in both themes.

**Tests:**
- Backend: `uv run pytest -q -W error -p no:cacheprovider` (no warnings).
- Web: `cd web && npm run typecheck && npm run lint && npm test` (ESLint 0 errors / 0 warnings).
- Final: `cd web && npm run build` then `npm run e2e` (queue project serial).
- Real-ffmpeg tests use `requires_ffmpeg` from `tests/helpers_ffmpeg.py`.

---

## Review Focus (inputs the spec implies that would most likely bite a real user)
1. **Paused on a segment boundary, in the last fraction of a second, or before the first frame of a clip whose index starts late** → the right segment is fetched, the frame equals what ffmpeg gives on the whole file at that time, the last fraction retries 100 ms earlier, past the index is `E_UNKNOWN`. Pinned by T2 `test_segment_for_boundaries_before_and_past`, T7 `test_no_frame_retries_100_ms_earlier_then_fails`, T7 integration `test_piece_frame_equals_the_full_file_frame` (t = 0, 1000, 2550, 3500) and `test_last_fraction_retries_and_still_gets_a_frame` (t = 3950).
2. **Output folder not writable / disk full / index write fails mid-capture** → no strip item, no cache copy, no index entry, the temp dir is gone. Pinned by T7 `test_output_failure_rolls_back_the_cache_copy` and `test_temp_dir_is_removed_on_every_path`.
3. **Deleting after the user renamed or moved the file, edited paths, a linked folder, or a changed output setting** → only the recorded file under the recorded root is removed, nothing else. Pinned by T7 `test_delete_skips_a_path_outside_the_recorded_root`, `test_delete_skips_a_renamed_file`, `test_delete_never_follows_a_linked_folder`, `test_delete_uses_the_recorded_root_after_the_setting_changes`, `test_delete_with_a_locked_folder_copy_changes_nothing`.
4. **Double click / two entry points at once / a second tab** → exactly one fetch; the second gets `E_CAPTURE_BUSY`; the web never sends the second request. Pinned by T7 `test_second_capture_while_one_runs_is_busy`, T11 `test_post_while_busy_is_409`, T8 `capture-store.test.ts` "tryBegin is single-flight".
5. **Theater switch with a playing clip, reduced motion, no View Transition API, T while typing or with a dialog open** → the iframe element survives, the end layout is the same, T is ignored where it must be. Pinned by T5 `theater.test.ts` (`runLayoutTransition`, `theaterKeyAllowed`), T9 e2e "▶ switches to theater without reloading the player" and "reduced motion: same layout, no transition".

---

## Shared contracts (every lane codes against these)

### C1. Setting and error copy (`core/settings.py`, `core/yterrors.py`, T1)
```python
# core/settings.py
CAPTURE_QUALITIES = ("max", "1080", "720")
# _VALIDATORS["captureQuality"] = lambda v: _one_of("captureQuality", v, CAPTURE_QUALITIES)
# default "captureQuality": "max" (right after "autoSharpFrames")

# core/yterrors.py MESSAGES (verbatim spec 2.2)
"E_CAPTURE_UNSUPPORTED": 'คลิปนี้ถ่ายภาพคมเฉพาะจุดไม่ได้ ใช้ "ขอภาพคม" ทั้งคลิปแทนได้'
"E_CAPTURE_BUSY": "กำลังถ่ายภาพอื่นอยู่ รอสักครู่"
"E_QUEUE_PAUSED": "พักการโหลดอยู่เพราะยูทูปขอตรวจสอบ ลองใหม่หลัง {time}"
# MESSAGES_NO_PARAMS["E_QUEUE_PAUSED"] = the E_BOT_CHECK text "ยูทูปขอให้ยืนยันว่าไม่ใช่บอท พักคิวไว้ 10 นาทีก่อนนะ"
```
`YtError("E_QUEUE_PAUSED", "…", params={"time": "17:10"}).message` = `พักการโหลดอยู่เพราะยูทูปขอตรวจสอบ ลองใหม่หลัง 17:10`. `PRD_PENDING` holds the three new codes until T15 adds their PRD rows.

### C2. Partial fetch maths (`core/frame_piece.py`, new, no `yt_dlp`, T2)
```python
HEAD_BYTES = 65_536
MAX_INDEX_BYTES = 1_048_576
MAX_TOP_BOXES = 64
CAPTURE_SHORT_SIDES: dict[str, int | None] = {"max": None, "1080": 1080, "720": 720}
ReadRange = Callable[[int, int], bytes]   # (first byte, last byte inclusive) -> bytes (may be shorter at EOF)

@dataclass(frozen=True)
class SidxRef:
    offset: int      # first byte of the segment in the file
    size: int
    start: int       # start time in timescale units
    duration: int

@dataclass(frozen=True)
class SidxIndex:
    timescale: int
    refs: tuple[SidxRef, ...]
    def to_ms(self, units: int) -> int          # units * 1000 // timescale
    @property
    def end_ms(self) -> int                     # end of the last segment

@dataclass(frozen=True)
class MediaIndex:
    init: bytes      # bytes [0, end of the sidx box): ftyp + moov + sidx
    sidx: SidxIndex

@dataclass(frozen=True)
class PieceInfo:
    path: Path
    segment_start_ms: int
    width: int | None
    height: int | None
    format_id: str
    dynamic_range: str | None   # None = SDR (the convention of MediaTools.extract_frame)

def parse_sidx(box: bytes, box_offset: int) -> SidxIndex            # v0/v1; E_CAPTURE_UNSUPPORTED on anything else
def read_index(read_range: ReadRange) -> MediaIndex                 # walks top-level boxes, fetches past 64 KB if needed
def segment_for(index: SidxIndex, t_ms: int) -> SidxRef | None      # before first -> first · boundary -> later · past end -> None
def fetch_piece(read_range: ReadRange, index: MediaIndex, t_ms: int) -> tuple[bytes, SidxRef]   # init + segment
def write_piece(dest: Path, data: bytes) -> None                    # OSError -> E_DISK_FULL (ENOSPC) / E_UNKNOWN
def max_short_side(quality: str) -> int | None                      # ValueError for unknown
def short_side(fmt: Mapping[str, Any]) -> int                       # min(w, h) · h when w unknown · 0 unknown
def pick_capture_format(info: Mapping[str, Any], max_short_side: int | None) -> dict | None
def piece_info(fmt: Mapping[str, Any], path: Path, index: SidxIndex, ref: SidxRef) -> PieceInfo
```
Errors: no `sidx` before `moof`/`mdat`, nested reference, version ≥ 2, bad box size, index past `MAX_INDEX_BYTES` → `YtError("E_CAPTURE_UNSUPPORTED")`; a short read → `YtError("E_NETWORK", "short read")`; time past the index → `YtError("E_UNKNOWN", "time past the end of the index")`.
Format candidates: `ext == "mp4"`, `protocol == "https"`, `vcodec` not `none`, `acodec` `none`/missing, non-empty `url`, `short_side > 0`. Best = min key `(-short_side, not SDR, codec rank avc1 0 / av01 1 / other 2, size unknown last, size, format_id)` among `short_side ≤ cap` (no cap for `None`); none under the cap → the candidates with the smallest short side.

### C3. Frame extraction without scaling (`core/media.py`, T3)
```python
def frame_args(ffmpeg: str, src: Path, dst: Path, t_ms: int, *, long_side: int | None = SHARP_LONG_SIDE,
               dynamic_range: str | None = None) -> list[str]
    # long_side None = no scale filter; no filter at all = no "-vf"; HDR + None = "-vf <tonemap>"
class MediaTools(Protocol):
    def extract_frame(self, src: Path, dst: Path, t_ms: int, *, long_side: int | None, dynamic_range: str | None,
                      cancel: Callable[[], bool]) -> bool: ...
@dataclass(frozen=True)
class FrameCall: ...; long_side: int | None
```
`_check_frame`: `long_side` is `None` or an int ≥ 1 (bool rejected).

### C4. Thai strings and web types (`web/src/i18n/th.ts`, `web/src/lib/types.ts`, T4 only)
```ts
// th.ts (new sections after `sharp`, verbatim spec)
theater: {
  expand: "ขยายตัวเล่น (T)",
  collapse: "ย่อตัวเล่น (T)",
  tooltip: "โหมดโรงภาพยนตร์",
},
capture: {
  button: "ถ่ายภาพคมตรงนี้",
  busy: "กำลังถ่าย…",
  done: "ถ่ายภาพคมแล้ว · {time}",
  view: "ดูภาพ",
  liveDisabled: "คลิปสดถ่ายภาพคมไม่ได้",
  pausedDisabled: "พักการโหลดอยู่เพราะยูทูปขอตรวจสอบ ลองใหม่หลัง {time}",
  stripTitle: "ภาพที่ถ่ายไว้ ({n})",
  openFolder: "เปิดโฟลเดอร์",
  delete: "ลบภาพนี้",
  deleteConfirm: "ลบภาพนี้ทั้งในแอพและในโฟลเดอร์ไหม",
  deleteAction: "ลบภาพ",
  cancel: "ยกเลิก",
  deleted: "ลบภาพแล้ว",
},
// general (additions)
captureQuality: "ความละเอียดภาพที่ถ่าย",
captureQualities: { max: "สูงสุดที่มี", "1080": "1080p", "720": "720p" },
captureQualityHint: "ภาพยิ่งละเอียด ตัวหนังสือเล็กในคลิปยิ่งอ่านง่าย ใช้เน็ตต่อภาพมากขึ้น (4K ราว 8 MB)",

// types.ts
export type CaptureQuality = "max" | "1080" | "720"
export type Capture = { id: string; tMs: number; width: number; height: number; url: string }
export type CaptureList = { captures: Capture[] }
// Settings gains: captureQuality: CaptureQuality
```
Reused existing strings: `th.frames.frameAlt`, `copyImage`, `imageCopied`, `copyImageFailed`, `downloadFrame`, `preparing`, `openYoutubeAt`, `playFrom`; `th.errors.unknown`, `th.errors.downloadFailed`.

### C5. Theater model (`web/src/pages/video/theater.ts`, pure, T5)
```ts
export const THEATER_KEY = "yt-toolkit:theater"
export const SWITCHING_ATTR = "data-theater-switching"
export type TheaterState = { videoId: string | null; on: boolean }
export type TheaterAction =
  | { type: "play"; videoId: string; preference: boolean }   // ▶ pressed in the slot
  | { type: "toggle"; videoId: string }
export function theaterReducer(state: TheaterState, action: TheaterAction): TheaterState
export function isTheaterOn(state: TheaterState, videoId: string): boolean        // another clip = false (compact)
export type PreferenceStorage = Pick<Storage, "getItem" | "setItem">
export function safeStorage(): PreferenceStorage | null                          // window.localStorage in try/catch
export function readTheaterPreference(storage: PreferenceStorage | null): boolean   // "0" = false; anything else / throws / null = true
export function writeTheaterPreference(storage: PreferenceStorage | null, on: boolean): void   // "1" | "0", swallows errors
export function isPortraitVideo(video: Pick<VideoInfo, "video">): boolean
export type HeaderLayout = "compact" | "theater-wide" | "theater-tall"
export function headerLayout(o: { on: boolean; narrow: boolean; portrait: boolean }): HeaderLayout
export type KeyLike = { key: string; ctrlKey: boolean; altKey: boolean; metaKey: boolean; repeat: boolean; defaultPrevented: boolean; target: unknown }
export function isEditableTarget(target: unknown): boolean
export function theaterKeyAllowed(event: KeyLike, ctx: { canToggle: boolean; overlayOpen: boolean }): boolean
export function prefersReducedMotion(): boolean
export type TransitionDoc = {
  documentElement: { setAttribute(name: string, value: string): void; removeAttribute(name: string): void }
  startViewTransition?: (update: () => void) => { finished: Promise<unknown> }
}
export function runLayoutTransition(apply: () => void, env: { doc: TransitionDoc; animate: boolean }): void
```

### C6. Extractor (`core/extractor.py`, T6)
```python
# both YtDlpExtractor and FakeExtractor
def fetch_frame_piece(self, video_id: str, t_ms: int, max_short_side: int | None, dest: Path) -> PieceInfo
```
Real: fresh `extract_info` (probe options, visitor session) → `check_live` → `pick_capture_format` (none → `E_CAPTURE_UNSUPPORTED`, no ranged request) → `read_index`/`fetch_piece` through `ydl.urlopen(Request(url, headers={**http_headers, "Range": "bytes=a-b"}))` reading at most `b-a+1` bytes → `write_piece(dest)` → `PieceInfo`. Errors: `HTTPError` → `classify("HTTP Error <status>")` (`E_UNKNOWN` → `E_NETWORK`) with detail `HTTP Error <status>`; `RequestError` → `E_NETWORK` with the class name; `YoutubeDLError` → `classify`; anything else → `E_UNKNOWN`. One `log.info` line: video id, format id, bytes fetched.
Fake: `calls.append(("fetch_frame_piece", video_id))`, `probe(video_id)` (same private/unavailable/live errors), `captureError` → `YtError(<code>)`, else cut from `<fixtures>/capture/piece.mp4` with `local = t_ms % index.sidx.end_ms` and `segment_start_ms = t_ms - (local - <segment start of local>)`; facts `format_id "fake-capture"`, 1920×1080, SDR.
New `behaviors.json` clips: `CAPTURE0001` `{"probeAs": BBB, "title": "คลิปถ่ายภาพคม"}`, `CAPTURENO01` `{… "title": "คลิปถ่ายภาพคมไม่ได้", "captureError": "E_CAPTURE_UNSUPPORTED"}`, `CAPTUREBOT1` `{… "title": "คลิปถ่ายภาพคมติดบอท", "captureError": "E_BOT_CHECK"}`, `CAPTURENET1` `{… "title": "คลิปถ่ายภาพคมเน็ตหลุด", "captureError": "E_NETWORK"}`.

### C7. Capture service (`core/capture.py`, new, T7)
```python
CAPTURE_FOLDER = "captures"           # <cache>/<id>/captures/
CAPTURE_INDEX = "index.json"          # {"captures": [entry, ...]}
OUTPUT_DIR = "ภาพที่ถ่าย"            # <output>/<clip folder>/ภาพที่ถ่าย/
CAPTURE_ID = re.compile(r"c_(\d{1,9})")
NO_FRAME_RETRY_MS = 100

class CaptureRejected(Exception):     # -> 422 E_BAD_REQUEST
    detail: str

@dataclass(frozen=True)
class Capture:
    id: str          # "c_<tMs>"
    t_ms: int
    width: int
    height: int
    file: str        # "c_<tMs>.jpg" in <cache>/<id>/captures/

class CaptureService:
    def __init__(self, videos, extractor, media, cache_root: Path, settings, queue, *, work_root: Path,
                 now: Callable[[], datetime] = ...) -> None
    def capture(self, video_id: str, t_ms: int) -> tuple[Capture, bool]    # (capture, created)
    def list(self, video_id: str) -> list[Capture]                          # sorted by t_ms; drops entries without a cache file
    def delete(self, video_id: str, capture_id: str) -> None                # KeyError = unknown
    def reveal_dir(self, video_id: str) -> Path | None
    def cache_path(self, video_id: str, capture: Capture) -> Path
```
Index entry: `{"id", "tMs", "width", "height", "file", "outputRoot", "outputRel", "createdAt"}` (`outputRel` uses `/`, `createdAt` UTC ISO seconds). Order inside `capture`: id check (`E_INVALID_INPUT`) → `t_ms` int check / live / duration ≤ 0 / out of `[0, duration*1000)` (`CaptureRejected`) → existing `c_<tMs>` (return, `created=False`) → `queue.pause_state()` (`E_QUEUE_PAUSED`, `params={"time": HH:MM Bangkok}`) → `media.available()` (`E_FFMPEG_MISSING`) → non-blocking global lock (`E_CAPTURE_BUSY`) → re-check existing → temp dir `work_root/capture-<uuid hex>` → fetch → extract at `t_ms - segment_start_ms` (then 100 ms earlier) → size from the JPEG → cache copy → folder copy (`frame_HH-MM-SS.jpg`, `_2` … `_99`) → index entry → `finally` remove the temp dir. `YtError("E_BOT_CHECK")` anywhere → `queue.brake("E_BOT_CHECK")` then re-raise.

### C8. Web capture module (`web/src/pages/video/capture/`, T8)
```ts
// capture-api.ts
export const capturesKey: (videoId: string) => readonly ["captures", string]
export function capturesQuery(videoId: string, enabled: boolean)            // GET /videos/{id}/captures -> Capture[]
export function postCapture(videoId: string, tMs: number): Promise<Capture>
export function deleteCapture(videoId: string, id: string): Promise<void>
export function revealCaptures(videoId: string): Promise<void>
export function withCapture(list: readonly Capture[] | undefined, item: Capture): Capture[]   // replace same id, sort by tMs
export function withoutCapture(list: readonly Capture[] | undefined, id: string): Capture[]
// capture-model.ts
export const CAPTURE_STEP_MS = 100
export function captureTimeMs(ms: number): number                 // round to 100 ms, >= 0
export function captureClock(ms: number): string                  // "2:05" / "2:05.4" / "1:02:05.4"
export function clockTime(iso: string): string                    // local "HH:MM", invalid = ""
export type CaptureBlock = { kind: "live" } | { kind: "paused"; until: string } | null
export function captureBlock(o: { isLive: boolean; pausedUntil: string | null; now: number }): CaptureBlock
export function blockTooltip(block: CaptureBlock): string | null
export function stripKeyTarget(key: string, index: number, count: number): number | null
export function focusAfterDelete(ids: readonly string[], removed: string): string | null
export function captureDownloadUrl(url: string): string           // + "&download=1" / "?download=1"
export function captureFileName(ms: number): string               // "frame_HH-MM-SS.jpg"
// capture-store.ts
export type CaptureTarget = { videoId: string; id: string }
export type CaptureUiState = { busy: boolean; viewing: CaptureTarget | null; flash: (CaptureTarget & { n: number }) | null }
export const captureStore: { get(); subscribe(l); tryBegin(): boolean; end(); view(t); closeView(); flash(t) }
export function useCaptureUi<T>(select: (s: CaptureUiState) => T): T
export function __resetCaptureStoreForTests(): void
// use-capture.ts
export function runCapture(client: QueryClient, videoId: string, ms: number): Promise<void>
export function useCapture(videoId: string): { busy: boolean; block: CaptureBlock; capture: (ms: number) => void }
// capture-button.tsx
export function CaptureButton(props: { videoId: string; variant?: "row" | "dock" }): JSX.Element
export function CaptureMenuItem(props: { videoId: string; tMs: number }): JSX.Element
// capture-strip.tsx
export type StripLayout = "wrap" | "row"
export function CaptureStrip(props: { videoId: string; layout: StripLayout; className?: string }): JSX.Element | null
```
DOM hooks for e2e: the button has `data-slot="capture-button"`, the strip `section[data-slot="capture-strip"]` with a `ul` named by its heading "ภาพที่ถ่ายไว้ (n)", the lightbox actions `[data-slot="capture-actions"]`.

### C9. Header layouts and player props (`header.tsx`, `player/player-slot.tsx`, `use-theater.ts`, `theater-toggle.tsx`, T9)
```ts
// use-theater.ts
export function useTheater(o: { videoId: string | null; portrait: boolean; narrow: boolean; inView: boolean }): {
  layout: HeaderLayout; on: boolean; canToggle: boolean; toggle: () => void; onPlayPressed: () => void
}
// theater-toggle.tsx
export function TheaterToggle(props: { on: boolean; onToggle: () => void }): JSX.Element
// player-slot.tsx (additions)
PlayerSlot({ video, inView, onBox, className, portrait?: boolean, onPlay?: () => void })
PlayerControls({ video, inView, className, actions?: ReactNode })   // actions follow the range-mark buttons in one wrapping row
```
`VideoHeader` root: `div[data-slot="video-header"][data-layout=<HeaderLayout>]` → first child the player column (first child `PlayerSlot` in every layout) → second child `div[data-slot="video-info"]`. CSS (`index.css`): `html[data-theater-switching] [data-slot="video-header"] [data-slot="player-slot"] { view-transition-name: yt-player }`, `html[data-theater-switching] [data-slot="video-info"] { view-transition-name: yt-info }`, groups 300 ms `cubic-bezier(0, 0, 0.2, 1)`.

### C10. Settings select (`general-panel.tsx`, `general-form.ts`, T10)
`GeneralKey` gains `"captureQuality"`; `export const CAPTURE_QUALITIES = ["max", "1080", "720"] as const`; a `ChoiceSelect` labelled "ความละเอียดภาพที่ถ่าย" with the hint as `aria-describedby`, placed after "คุณภาพวิดีโอเริ่มต้น".

### C11. API (`api/captures.py` new, `api/videos.py`, `app.py`, T11)
- `GET /api/videos/{id}/captures` → 200 `{"captures": [{"id", "tMs", "width", "height", "url"}]}`; `url = /api/cache/{id}/captures/c_<tMs>.jpg?v=<mtime_ns>`; bad id → 422 `E_INVALID_INPUT`.
- `POST /api/videos/{id}/captures` body `{"tMs": StrictInt}` (`extra="forbid"`, `0 ≤ tMs ≤ 172_800_000`) → 201 new / 200 existing, same item shape; `CaptureRejected` → 422 `E_BAD_REQUEST`; `YtError` → `yt_error_response(exc, video_id)` (no `on_bot_check`).
- `DELETE /api/videos/{id}/captures/{captureId}` → 204; unknown → 404 `E_NOT_FOUND`; `YtError` → its status.
- `POST /api/videos/{id}/captures/reveal` → 200 `{"ok": true}` after `(ctx.open_folder or ctx.plat.open_folder)(folder)`; no folder → 404.
- `STATUS_BY_CODE` gains `E_CAPTURE_UNSUPPORTED` 422, `E_CAPTURE_BUSY` 409, `E_QUEUE_PAUSED` 409, `E_FFMPEG_MISSING` 409, `E_DISK_FULL` 507, `E_OUTPUT_NOT_WRITABLE` 409.
- `GET /api/cache/{id}/captures/c_<tMs>.jpg` → `Cache-Control: public, max-age=86400, immutable`; `?download=1` → `frame_HH-MM-SS.jpg`.
- `AppContext.captures: CaptureService | None = None`; `create_app` includes the router when it is set.

### C12. Lifecycle (`lifecycle.py`, T12)
`Services.captures: CaptureService | None = None`; `open_services` builds `CaptureService(videos, extractor, media, paths.cache, settings, queue, work_root=paths.work)` right after the queue; `_run_server` sets `ctx.captures = services.captures` right after building the `AppContext` (attribute assignment keeps T12 independent of T11, which adds the field).

### C13. Placement in W2 (T13)
- `ControlsRow`: `<RangeMarkButtons/>` · `<CaptureButton videoId/>` · `actions` (theater toggle) in one wrapping row.
- `DockToolbar`: `<CaptureButton videoId variant="dock"/>` right after the docked range-mark buttons.
- Header: `<CaptureStrip>` right after the controls in each layout (compact/narrow `wrap`, theater-wide `row`, theater-tall `wrap` at the bottom of the info column); rendered even before play.
- Frame context menu: `<CaptureMenuItem videoId tMs={frame.tMs}/>` right after "เล่นจากตรงนี้".

### C14. E2E files
Chromium (mocked capture API, fake YouTube player): `web/e2e/theater.spec.ts` (T9), `web/e2e/capture.spec.ts` (T13), extra test in `web/e2e/settings-general.spec.ts` (T10). Queue (real fake backend, serial): `web/e2e/queue-capture.spec.ts` (T14) using only `CAPTURE0001`. `web/playwright.config.ts` (T9) sets the chromium project's default storage `yt-toolkit:theater = "0"`.

---

## File structure

**Backend (new):** `src/yttoolkit/core/frame_piece.py` (T2) · `src/yttoolkit/core/capture.py` (T7) · `src/yttoolkit/api/captures.py` (T11).
**Backend (modified):** `core/settings.py`, `core/yterrors.py` (T1) · `core/media.py` (T3) · `core/extractor.py` (T6) · `api/videos.py`, `app.py` (T11) · `lifecycle.py` (T12).
**Fixtures:** `tests/fixtures/capture/piece.mp4` (T2, new, binary ~50 KB) · `tests/fixtures/README.md` (T2 capture section, T6 behaviors rows) · `tests/fixtures/downloads/behaviors.json` (T6).
**Tests (new):** `tests/unit/test_frame_piece.py` (T2) · `tests/unit/test_extractor_capture.py` (T6) · `tests/helpers_capture.py`, `tests/unit/test_capture.py`, `tests/integration/test_capture_ffmpeg.py` (T7) · `tests/api/test_captures_api.py` (T11) · `tests/network/test_capture_network.py` (T15).
**Tests (modified):** `test_settings.py`, `test_yterrors.py`, `tests/api/test_settings_api.py` (T1; `test_yterrors.py` again T15) · `test_media_args.py`, `tests/integration/test_sharp_ffmpeg.py` (T3) · `test_extractor_download.py` (T6) · `tests/api/test_videos_api.py` (T11) · `test_lifecycle.py` (T12).
**Web (new):** `web/src/pages/video/theater.ts` + test (T5) · `web/src/pages/video/capture/{capture-api.ts, capture-api.test.ts, capture-model.ts, capture-model.test.ts, capture-store.ts, capture-store.test.ts, use-capture.ts, capture-button.tsx, capture-strip.tsx}` (T8) · `web/src/pages/video/use-theater.ts`, `theater-toggle.tsx` (T9) · e2e specs (C14).
**Web (modified):** `th.ts`, `types.ts`, four Settings test literals (T4) · `header.tsx`, `player/player-slot.tsx`, `index.css`, `playwright.config.ts` (T9) · `general-panel.tsx`, `general-form.ts` (+test), `settings-general.spec.ts` (T10) · `header.tsx`, `player/player-slot.tsx`, `frames.tsx`, `e2e/video.spec.ts`, `e2e/sharp-grid.spec.ts`, `e2e/transcript.spec.ts` (T13).
**Docs (modified, T15):** `PRD.md`, `BRD.md`, `docs/acceptance.md`, `tests/network_videos.toml`.

---

## Wave 1

### Task 1: `captureQuality` setting and the capture error copy

**Files:**
- Modify: `src/yttoolkit/core/settings.py` (`CAPTURE_QUALITIES`, validator, default)
- Modify: `src/yttoolkit/core/yterrors.py` (`E_CAPTURE_UNSUPPORTED`, `E_CAPTURE_BUSY`, `E_QUEUE_PAUSED`, no-params fallback)
- Modify: `tests/unit/test_settings.py`, `tests/unit/test_yterrors.py`, `tests/api/test_settings_api.py`

**Interfaces:**
- Consumes: `_one_of` (`core/settings.py:80-84`), `MESSAGES`/`MESSAGES_NO_PARAMS`/`YtError` (`core/yterrors.py`).
- Produces: C1 exactly.

- [ ] **Step 1: Write the failing tests**

In `tests/unit/test_settings.py`, inside the dict of `test_defaults_match_the_c5_table`, add right after the `"autoSharpFrames": True,` line:
```python
        "captureQuality": "max",
```
add these rows to the `bad` list of `test_invalid_patch_is_rejected_and_changes_nothing` (after the `autoSharpFrames` rows):
```python
        {"captureQuality": "4k"},
        {"captureQuality": 1080},
        {"captureQuality": None},
```
and append:
```python
def test_capture_quality_accepts_the_three_choices(store):  # M5 รอบ B2 spec 2.4
    for value in ("1080", "720", "max"):
        assert store.patch({"captureQuality": value})["captureQuality"] == value
```
In `tests/api/test_settings_api.py` add `"captureQuality",` to `SETTING_KEYS` right after `"autoSharpFrames",`, and append:
```python
def test_capture_quality_round_trips(client):
    resp = client.patch("/api/settings", json={"captureQuality": "720"}, headers=AUTH)
    assert resp.status_code == 200 and resp.json()["captureQuality"] == "720"
    bad = client.patch("/api/settings", json={"captureQuality": "480"}, headers=AUTH)
    assert bad.status_code == 422 and bad.json()["error"]["code"] == "E_BAD_REQUEST"
    assert client.get("/api/settings").json()["captureQuality"] == "720"
```
In `tests/unit/test_yterrors.py` set
```python
PRD_PENDING: set[str] = {"E_CAPTURE_UNSUPPORTED", "E_CAPTURE_BUSY", "E_QUEUE_PAUSED"}
```
(T15 adds the PRD rows and empties the set again), change the placeholder line inside `test_messages_match_prd_table` from
```python
        text = message.replace("{size}", "<ขนาด>")
```
to
```python
        text = message.replace("{size}", "<ขนาด>").replace("{time}", "<เวลา>")
```
and append:
```python
def test_m5b2_capture_messages_are_verbatim_spec_copy() -> None:
    assert MESSAGES["E_CAPTURE_UNSUPPORTED"] == 'คลิปนี้ถ่ายภาพคมเฉพาะจุดไม่ได้ ใช้ "ขอภาพคม" ทั้งคลิปแทนได้'
    assert MESSAGES["E_CAPTURE_BUSY"] == "กำลังถ่ายภาพอื่นอยู่ รอสักครู่"
    assert MESSAGES["E_QUEUE_PAUSED"] == "พักการโหลดอยู่เพราะยูทูปขอตรวจสอบ ลองใหม่หลัง {time}"


def test_queue_paused_fills_the_time_and_never_shows_the_placeholder() -> None:
    assert YtError("E_QUEUE_PAUSED", "paused", params={"time": "17:10"}).message == (
        "พักการโหลดอยู่เพราะยูทูปขอตรวจสอบ ลองใหม่หลัง 17:10"
    )
    assert YtError("E_QUEUE_PAUSED").message == MESSAGES["E_BOT_CHECK"]
    assert "{time}" not in str(YtError("E_QUEUE_PAUSED"))
```

- [ ] **Step 2: Run them, expect FAIL**

Run: `cd "$WORKTREE" && uv run pytest tests/unit/test_settings.py tests/unit/test_yterrors.py tests/api/test_settings_api.py -q -W error -p no:cacheprovider`
Expected: FAIL (`captureQuality` missing from the defaults and `SETTING_KEYS`, `KeyError: 'E_CAPTURE_UNSUPPORTED'`, `test_prd_pending_codes_are_known_messages` fails).

- [ ] **Step 3: Implement `core/settings.py`**

After the `VIDEO_DEFAULTS = …` line add:
```python
# M5 รอบ B2 (E2): ความละเอียดภาพคมตรงจุด เพดานนับที่ด้านสั้น "max" = สูงสุดที่มี (ถึง 4K)
CAPTURE_QUALITIES = ("max", "1080", "720")
```
Add to `_VALIDATORS`, right after the `"autoSharpFrames"` entry:
```python
    "captureQuality": lambda v: _one_of("captureQuality", v, CAPTURE_QUALITIES),
```
Add to the defaults dict, right after the `"autoSharpFrames": True,` line:
```python
            "captureQuality": "max",  # M5 รอบ B2 spec 2.4: ภาพคมตรงจุดใช้ format ที่ละเอียดที่สุด
```

- [ ] **Step 4: Implement `core/yterrors.py`**

In `MESSAGES`, right after the `E_NO_SHARP_FRAMES` entry add:
```python
    # M5 รอบ B2 ถ่ายภาพคมตรงจุด (spec 2.2): ไม่มี mp4 ที่มี sidx · มีการถ่ายอื่นค้างอยู่ · คิวพักเพราะยูทูปขอตรวจสอบ
    "E_CAPTURE_UNSUPPORTED": 'คลิปนี้ถ่ายภาพคมเฉพาะจุดไม่ได้ ใช้ "ขอภาพคม" ทั้งคลิปแทนได้',
    "E_CAPTURE_BUSY": "กำลังถ่ายภาพอื่นอยู่ รอสักครู่",
    "E_QUEUE_PAUSED": "พักการโหลดอยู่เพราะยูทูปขอตรวจสอบ ลองใหม่หลัง {time}",
```
In `MESSAGES_NO_PARAMS` add:
```python
    # ไม่รู้เวลาที่คิวจะกลับมา (ไม่ควรเกิด capture ส่งเวลาเสมอ): ใช้ข้อความของ E_BOT_CHECK ที่มีอยู่แล้ว
    "E_QUEUE_PAUSED": "ยูทูปขอให้ยืนยันว่าไม่ใช่บอท พักคิวไว้ 10 นาทีก่อนนะ",
```

- [ ] **Step 5: Run the tests, expect PASS** — same command as Step 2, then `cd "$WORKTREE" && uv run pytest -q -W error -p no:cacheprovider`.

- [ ] **Step 6: Commit**
```bash
cd "$WORKTREE" && git add src/yttoolkit/core/settings.py src/yttoolkit/core/yterrors.py tests/unit/test_settings.py tests/unit/test_yterrors.py tests/api/test_settings_api.py && git commit -F- <<'EOF'
feat(settings): M5-B2 captureQuality setting and capture error copy

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
EOF
```

### Task 2: Pure partial-fetch module (`core/frame_piece.py`) and the capture fixture

**Files:**
- Create: `src/yttoolkit/core/frame_piece.py`, `tests/unit/test_frame_piece.py`
- Create: `tests/fixtures/capture/piece.mp4` (binary, generated once with ffmpeg, committed)
- Modify: `tests/fixtures/README.md` (new section `## capture/`)

**Interfaces:**
- Consumes: `YtError` (`core/yterrors.py`).
- Produces: C2 exactly.

- [ ] **Step 1: Generate the fixture (once) and check it**

Run (ffmpeg 8.x on PATH; the exact bytes may differ between ffmpeg builds, the tests check only the structure):
```bash
cd "$WORKTREE" && mkdir -p tests/fixtures/capture && ffmpeg -hide_banner -loglevel error -y -f lavfi -i "testsrc=size=1920x1080:rate=10:duration=4" -c:v libx264 -preset veryslow -crf 40 -bf 0 -g 10 -keyint_min 10 -sc_threshold 0 -pix_fmt yuv420p -an -movflags +frag_keyframe+empty_moov+default_base_moof+global_sidx -fflags +bitexact -flags:v +bitexact tests/fixtures/capture/piece.mp4 && ls -l tests/fixtures/capture/piece.mp4
```
Expected: a file of roughly 50 KB (measured 50,545 bytes with ffmpeg 8.1 Gyan full build). `git check-attr -a tests/fixtures/capture/piece.mp4` shows `text: auto`; after `git add` it must show as binary in `git ls-files --eol` (`i/-text`).

- [ ] **Step 2: Write the failing tests**

Create `tests/unit/test_frame_piece.py`:
```python
"""ภาพคมตรงจุด (M5 รอบ B2 spec 3.1): อ่าน sidx (v0/v1, กล่องเลย 64 KB, รอยต่อ, เลยท้าย) เลือก format และประกอบชิ้น"""

from __future__ import annotations

import ast
import struct
from pathlib import Path

import pytest

from yttoolkit.core import frame_piece
from yttoolkit.core.frame_piece import (
    HEAD_BYTES,
    MAX_INDEX_BYTES,
    PieceInfo,
    SidxIndex,
    SidxRef,
    fetch_piece,
    max_short_side,
    parse_sidx,
    pick_capture_format,
    piece_info,
    read_index,
    segment_for,
    short_side,
    write_piece,
)
from yttoolkit.core.yterrors import YtError

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "capture" / "piece.mp4"


def _box(kind: bytes, payload: bytes) -> bytes:
    return struct.pack(">I4s", 8 + len(payload), kind) + payload


def _sidx(version: int, timescale: int, earliest: int, first: int, refs: list[tuple[int, int]]) -> bytes:
    body = struct.pack(">B3xII", version, 1, timescale)
    body += struct.pack(">II", earliest, first) if version == 0 else struct.pack(">QQ", earliest, first)
    body += struct.pack(">HH", 0, len(refs))
    for size, duration in refs:
        body += struct.pack(">III", size, duration, 0x9000_0000)
    return _box(b"sidx", body)


def _file(moov_payload: int = 100, version: int = 1, refs: list[tuple[int, int]] | None = None, earliest: int = 0) -> bytes:
    refs = refs or [(1000, 5000), (1200, 5000), (800, 4000)]
    head = _box(b"ftyp", b"isom\x00\x00\x02\x00") + _box(b"moov", b"\x00" * moov_payload)
    head += _sidx(version, 1000, earliest, 0, refs)
    segments = b"".join(bytes([i + 1]) * size for i, (size, _d) in enumerate(refs))
    return head + segments


class Reader:
    def __init__(self, data: bytes) -> None:
        self.data = data
        self.calls: list[tuple[int, int]] = []

    def __call__(self, first: int, last: int) -> bytes:
        self.calls.append((first, last))
        return self.data[first : last + 1]


@pytest.mark.parametrize("version", [0, 1])
def test_parse_sidx_gives_offsets_and_times(version: int) -> None:
    box = _sidx(version, 90_000, 9000, 16, [(500, 450_000), (700, 450_000)])
    index = parse_sidx(box, 1000)
    first = 1000 + len(box) + 16
    assert index == SidxIndex(90_000, (SidxRef(first, 500, 9000, 450_000), SidxRef(first + 500, 700, 459_000, 450_000)))
    assert index.to_ms(9000) == 100 and index.end_ms == 10_100


@pytest.mark.parametrize(
    "box",
    [
        _box(b"sidx", b"\x00" * 10),  # too short
        _box(b"free", b"\x00" * 40),  # not sidx
        _sidx(2, 1000, 0, 0, [(10, 10)]),  # unknown version
        _sidx(0, 0, 0, 0, [(10, 10)]),  # timescale 0
        _sidx(0, 1000, 0, 0, [(0x8000_0010, 10)]),  # reference to another sidx
    ],
)
def test_bad_sidx_is_unsupported(box: bytes) -> None:
    with pytest.raises(YtError) as info:
        parse_sidx(box, 0)
    assert info.value.code == "E_CAPTURE_UNSUPPORTED"


def test_read_index_walks_ftyp_and_moov_in_one_request() -> None:
    data = _file()
    reader = Reader(data)
    index = read_index(reader)
    assert reader.calls == [(0, HEAD_BYTES - 1)]
    sidx_end = len(data) - 3000
    assert index.init == data[:sidx_end]
    assert [r.offset for r in index.sidx.refs] == [sidx_end, sidx_end + 1000, sidx_end + 2200]
    assert [index.sidx.to_ms(r.start) for r in index.sidx.refs] == [0, 5000, 10_000]


def test_a_sidx_crossing_64_kb_fetches_the_rest_of_the_box() -> None:
    data = _file(moov_payload=HEAD_BYTES - 60)  # sidx เริ่มก่อน 64 KB นิดเดียว ท้ายกล่องอยู่เลย 64 KB
    reader = Reader(data)
    index = read_index(reader)
    sidx_end = len(data) - 3000
    assert reader.calls == [(0, HEAD_BYTES - 1), (HEAD_BYTES, sidx_end - 1)]
    assert len(index.sidx.refs) == 3


def test_a_box_header_past_64_kb_is_fetched_too() -> None:
    data = _file(moov_payload=HEAD_BYTES + 100)
    index = read_index(Reader(data))
    assert index.sidx.end_ms == 14_000


def test_media_before_any_sidx_is_unsupported() -> None:
    data = _box(b"ftyp", b"isom") + _box(b"moov", b"\x00" * 8) + _box(b"moof", b"\x00" * 8) + _box(b"mdat", b"x")
    with pytest.raises(YtError) as info:
        read_index(Reader(data))
    assert info.value.code == "E_CAPTURE_UNSUPPORTED"


def test_a_sidx_too_far_into_the_file_is_unsupported() -> None:
    data = _file(moov_payload=MAX_INDEX_BYTES)
    with pytest.raises(YtError) as info:
        read_index(Reader(data))
    assert info.value.code == "E_CAPTURE_UNSUPPORTED"


def test_a_bad_box_size_is_unsupported() -> None:
    data = struct.pack(">I4s", 4, b"ftyp") + b"\x00" * 100
    with pytest.raises(YtError) as info:
        read_index(Reader(data))
    assert info.value.code == "E_CAPTURE_UNSUPPORTED"


def test_a_short_read_is_a_network_error() -> None:
    data = _file(moov_payload=HEAD_BYTES - 60)
    with pytest.raises(YtError) as info:
        read_index(lambda first, last: data[first : min(last + 1, HEAD_BYTES + 4)])
    assert info.value.code == "E_NETWORK"


def test_segment_for_boundaries_before_and_past() -> None:
    index = SidxIndex(1000, (SidxRef(0, 10, 200, 1000), SidxRef(10, 10, 1200, 1000)))
    assert segment_for(index, 0) == index.refs[0]  # ก่อนท่อนแรก (earliest 0.2 s) = ท่อนแรก
    assert segment_for(index, 1199) == index.refs[0]
    assert segment_for(index, 1200) == index.refs[1]  # ตรงรอยต่อ = ท่อนหลัง
    assert segment_for(index, 2199) == index.refs[1]
    assert segment_for(index, 2200) is None


def test_segment_for_uses_exact_timescale_maths() -> None:
    index = SidxIndex(90_000, (SidxRef(0, 1, 0, 450_001), SidxRef(1, 1, 450_001, 450_000)))
    assert segment_for(index, 5000) == index.refs[0]  # 5000 ms = 450_000 หน่วย ยังอยู่ท่อนแรก (ยาว 450_001)
    assert segment_for(index, 5001) == index.refs[1]


def test_fetch_piece_is_init_plus_one_segment() -> None:
    data = _file()
    reader = Reader(data)
    index = read_index(reader)
    piece, ref = fetch_piece(reader, index, 7_500)
    assert ref == index.sidx.refs[1]
    assert piece == index.init + b"\x02" * 1200
    assert reader.calls[-1] == (ref.offset, ref.offset + 1199)
    with pytest.raises(YtError) as past:
        fetch_piece(reader, index, 14_000)
    assert past.value.code == "E_UNKNOWN"
    with pytest.raises(YtError) as short:
        fetch_piece(lambda first, last: data[first:last], index, 0)
    assert short.value.code == "E_NETWORK"


def test_the_committed_fixture_is_a_four_second_dash_file() -> None:
    data = FIXTURE.read_bytes()
    reader = Reader(data)
    index = read_index(reader)
    assert reader.calls == [(0, HEAD_BYTES - 1)]
    assert index.sidx.timescale == 10_240 and len(index.sidx.refs) == 4 and index.sidx.end_ms == 4000
    assert [index.sidx.to_ms(r.start) for r in index.sidx.refs] == [0, 1000, 2000, 3000]
    assert index.sidx.refs[-1].offset + index.sidx.refs[-1].size <= len(data)
    piece, ref = fetch_piece(reader, index, 2550)
    assert index.sidx.to_ms(ref.start) == 2000 and len(piece) == len(index.init) + ref.size


def test_write_piece_creates_the_folder(tmp_path: Path) -> None:
    dest = tmp_path / "work" / "piece.mp4"
    write_piece(dest, b"abc")
    assert dest.read_bytes() == b"abc"


def _fmt(fid: str, w: int | None, h: int, **extra: object) -> dict:
    base = {"format_id": fid, "ext": "mp4", "protocol": "https", "vcodec": "avc1.640028", "acodec": "none",
            "url": f"https://media.invalid/{fid}", "width": w, "height": h}  # fmt: skip
    return {**base, **extra}


def test_max_short_side_maps_the_setting() -> None:
    assert [max_short_side(q) for q in ("max", "1080", "720")] == [None, 1080, 720]
    with pytest.raises(ValueError):
        max_short_side("4k")


def test_short_side_counts_portrait_by_width() -> None:
    assert short_side({"width": 1080, "height": 1920}) == 1080
    assert short_side({"height": 720}) == 720
    assert short_side({"width": 640}) == 0


def test_pick_prefers_the_largest_short_side_under_the_cap() -> None:
    formats = [_fmt("137", 1920, 1080), _fmt("136", 1280, 720), _fmt("401", 3840, 2160, vcodec="av01.0.12M.08")]
    assert pick_capture_format({"formats": formats}, None)["format_id"] == "401"
    assert pick_capture_format({"formats": formats}, 1080)["format_id"] == "137"
    assert pick_capture_format({"formats": formats}, 720)["format_id"] == "136"
    portrait = [_fmt("p1080", 1080, 1920), _fmt("p720", 720, 1280)]
    assert pick_capture_format({"formats": portrait}, 1080)["format_id"] == "p1080"  # ด้านสั้น 1080 ไม่เกินเพดาน


def test_pick_order_sdr_then_avc1_then_smallest() -> None:
    same = [
        _fmt("hdr", 1920, 1080, dynamic_range="HDR10"),
        _fmt("av1", 1920, 1080, vcodec="av01.0.08M.08", dynamic_range="SDR", filesize=10),
        _fmt("big", 1920, 1080, filesize=900),
        _fmt("small", 1920, 1080, filesize=500),
    ]
    assert pick_capture_format({"formats": same}, None)["format_id"] == "small"
    assert pick_capture_format({"formats": same[:2]}, None)["format_id"] == "av1"
    assert pick_capture_format({"formats": same[:1]}, None)["format_id"] == "hdr"


def test_pick_skips_everything_that_has_no_sidx_mp4() -> None:
    formats = [
        _fmt("webm", 1920, 1080, ext="webm", vcodec="vp9"),
        _fmt("hls", 1920, 1080, protocol="m3u8_native"),
        _fmt("muxed", 1280, 720, acodec="mp4a.40.2"),
        _fmt("audio", None, 0, vcodec="none", acodec="mp4a.40.2"),
        _fmt("nourl", 1920, 1080, url=""),
        {"format_id": "sb0", "ext": "mhtml", "protocol": "mhtml", "vcodec": "none"},
    ]
    assert pick_capture_format({"formats": formats}, None) is None
    assert pick_capture_format({}, None) is None


def test_nothing_under_the_cap_takes_the_smallest_above() -> None:
    formats = [_fmt("2160", 3840, 2160), _fmt("1440", 2560, 1440)]
    assert pick_capture_format({"formats": formats}, 720)["format_id"] == "1440"


def test_piece_info_reads_the_format_facts(tmp_path: Path) -> None:
    index = SidxIndex(1000, (SidxRef(0, 1, 0, 5000), SidxRef(1, 1, 5000, 5000)))
    sdr = piece_info(_fmt("137", 1920, 1080), tmp_path / "p.mp4", index, index.refs[1])
    assert sdr == PieceInfo(tmp_path / "p.mp4", 5000, 1920, 1080, "137", None)
    hdr = piece_info(_fmt("701", 3840, 2160, dynamic_range="HDR10"), tmp_path / "p.mp4", index, index.refs[0])
    assert hdr.dynamic_range == "HDR10" and hdr.segment_start_ms == 0


def test_the_module_never_imports_yt_dlp() -> None:
    tree = ast.parse(Path(frame_piece.__file__).read_text(encoding="utf-8"))
    names = {alias.name for node in ast.walk(tree) if isinstance(node, ast.Import) for alias in node.names}
    names |= {node.module for node in ast.walk(tree) if isinstance(node, ast.ImportFrom) and node.module}
    assert not any(name.split(".")[0] == "yt_dlp" for name in names)
```

- [ ] **Step 3: Run them, expect FAIL**

Run: `cd "$WORKTREE" && uv run pytest tests/unit/test_frame_piece.py -q -W error -p no:cacheprovider`
Expected: FAIL (`ModuleNotFoundError: No module named 'yttoolkit.core.frame_piece'`).

- [ ] **Step 4: Implement `src/yttoolkit/core/frame_piece.py`**
```python
"""ภาพคมตรงจุด (M5 รอบ B2 spec 3.1) ส่วนที่ไม่ต่อเน็ต: อ่าน sidx ของ mp4 แบบแบ่งท่อน เลือก format และประกอบไฟล์ชิ้นเล็ก

ไฟล์ DASH ของยูทูปเรียงกล่องเป็น ftyp, moov, sidx แล้วตามด้วย moof+mdat ทีละท่อน (ราว 5 วินาทีต่อท่อน)
sidx บอกว่าแต่ละท่อนเริ่มที่ไบต์ไหน ยาวกี่ไบต์ และกินเวลาเท่าไร จึงโหลดแค่ส่วนหัว (init) กับท่อนเดียวที่มีเวลาที่ต้องการ
โมดูลนี้ไม่ใช้ yt-dlp และไม่ต่อเน็ต: ตัวจริง (extractor.py) ส่ง read_range ที่ยิงคำขอแบบ Range
ตัวปลอมส่ง read_range ที่ตัดจากไฟล์ใน tests/fixtures/capture/
"""

from __future__ import annotations

import errno
import struct
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .yterrors import YtError

HEAD_BYTES = 65_536  # คำขอแรก: ftyp + moov + sidx ของยูทูปอยู่ในช่วงนี้แทบทุกคลิป
MAX_INDEX_BYTES = 1_048_576  # เลยจากนี้ยังไม่เจอ sidx = ไม่ใช่ไฟล์แบบที่รองรับ
MAX_TOP_BOXES = 64
# ค่าตั้ง captureQuality -> ด้านสั้นสูงสุด (None = ไม่จำกัด "สูงสุดที่มี")
CAPTURE_SHORT_SIDES: dict[str, int | None] = {"max": None, "1080": 1080, "720": 720}

ReadRange = Callable[[int, int], bytes]  # (ไบต์แรก, ไบต์สุดท้ายแบบนับรวม) -> ข้อมูล (สั้นกว่าที่ขอได้ถ้าถึงท้ายไฟล์)


@dataclass(frozen=True)
class SidxRef:
    """ท่อนหนึ่งของไฟล์: ไบต์แรก ขนาด และเวลาเริ่ม/ความยาวในหน่วย timescale"""

    offset: int
    size: int
    start: int
    duration: int


@dataclass(frozen=True)
class SidxIndex:
    timescale: int
    refs: tuple[SidxRef, ...]

    def to_ms(self, units: int) -> int:
        return units * 1000 // self.timescale

    @property
    def end_ms(self) -> int:
        last = self.refs[-1]
        return self.to_ms(last.start + last.duration)


@dataclass(frozen=True)
class MediaIndex:
    init: bytes  # ไบต์ 0 ถึงท้ายกล่อง sidx (ftyp + moov + sidx) ffmpeg ต้องใช้ส่วนนี้ถอดรหัสท่อนใดก็ได้
    sidx: SidxIndex


@dataclass(frozen=True)
class PieceInfo:
    """ไฟล์ชิ้นเล็ก (init + หนึ่งท่อน) ที่เขียนแล้ว · segment_start_ms = เวลาของคลิปที่ท่อนนี้เริ่ม"""

    path: Path
    segment_start_ms: int
    width: int | None
    height: int | None
    format_id: str
    dynamic_range: str | None  # None = SDR (แบบเดียวกับ MediaTools.extract_frame)


def _unsupported(why: str) -> YtError:
    return YtError("E_CAPTURE_UNSUPPORTED", why)


def parse_sidx(box: bytes, box_offset: int) -> SidxIndex:
    """กล่อง sidx ทั้งกล่อง (version 0 หรือ 1) -> ตำแหน่งไบต์และเวลาของทุกท่อน (ISO 14496-12 8.16.3)

    box_offset = ตำแหน่งของกล่องในไฟล์: ท่อนแรกเริ่มที่ท้ายกล่อง + first_offset
    """
    if len(box) < 32 or box[4:8] != b"sidx":
        raise _unsupported("not a sidx box")
    version = box[8]
    if version not in (0, 1):
        raise _unsupported(f"sidx version {version}")
    if version == 1 and len(box) < 40:
        raise _unsupported("sidx box too short")
    pos = 16  # หัวกล่อง 8 + version/flags 4 + reference_ID 4
    (timescale,) = struct.unpack_from(">I", box, pos)
    pos += 4
    if version == 0:
        earliest, first = struct.unpack_from(">II", box, pos)
        pos += 8
    else:
        earliest, first = struct.unpack_from(">QQ", box, pos)
        pos += 16
    pos += 2  # reserved
    (count,) = struct.unpack_from(">H", box, pos)
    pos += 2
    if timescale == 0 or count == 0 or pos + count * 12 > len(box):
        raise _unsupported("bad sidx")
    offset = box_offset + len(box) + first
    start = earliest
    refs: list[SidxRef] = []
    for _ in range(count):
        word, duration, _sap = struct.unpack_from(">III", box, pos)
        pos += 12
        if word >> 31:
            raise _unsupported("sidx points to another sidx")
        size = word & 0x7FFF_FFFF
        refs.append(SidxRef(offset, size, start, duration))
        offset += size
        start += duration
    return SidxIndex(timescale, tuple(refs))


class _Head:
    """ไบต์ต้นไฟล์ที่โหลดมาแล้ว ขอเพิ่มต่อท้ายได้จนถึง MAX_INDEX_BYTES"""

    def __init__(self, read_range: ReadRange) -> None:
        self._read = read_range
        self.data = read_range(0, HEAD_BYTES - 1)

    def need(self, end: int) -> None:
        if end <= len(self.data):
            return
        if end > MAX_INDEX_BYTES:
            raise _unsupported("no sidx near the start of the file")
        more = self._read(len(self.data), end - 1)
        if len(more) != end - len(self.data):
            raise YtError("E_NETWORK", "short read")
        self.data += more


def _find_sidx(head: _Head) -> tuple[int, int]:
    """เดินกล่องระดับบนจากต้นไฟล์จนเจอ sidx -> (ตำแหน่ง, ขนาด) · เจอ moof/mdat ก่อน = ไม่มี sidx"""
    pos = 0
    for _ in range(MAX_TOP_BOXES):
        head.need(pos + 8)
        size, kind = struct.unpack_from(">I4s", head.data, pos)
        header = 8
        if size == 1:
            head.need(pos + 16)
            (size,) = struct.unpack_from(">Q", head.data, pos + 8)
            header = 16
        if size < header:  # 0 = กล่องยาวถึงท้ายไฟล์ (ไม่มีอะไรตามหลัง) หรือขนาดเสีย
            raise _unsupported(f"bad box size at {pos}")
        if kind == b"sidx":
            return pos, size
        if kind in (b"moof", b"mdat"):
            raise _unsupported("no sidx before the media")
        pos += size
    raise _unsupported("no sidx")


def read_index(read_range: ReadRange) -> MediaIndex:
    head = _Head(read_range)
    pos, size = _find_sidx(head)
    head.need(pos + size)
    sidx = parse_sidx(head.data[pos : pos + size], pos)
    return MediaIndex(head.data[: pos + size], sidx)


def segment_for(index: SidxIndex, t_ms: int) -> SidxRef | None:
    """ท่อนที่มีเวลา t_ms: ก่อนท่อนแรก = ท่อนแรก · ตรงรอยต่อ = ท่อนหลัง · เลยท่อนสุดท้าย = None
    เทียบในหน่วย timescale × 1000 จึงไม่มีเศษปัด"""
    target = t_ms * index.timescale
    for ref in index.refs:
        if target < (ref.start + ref.duration) * 1000:
            return ref
    return None


def fetch_piece(read_range: ReadRange, index: MediaIndex, t_ms: int) -> tuple[bytes, SidxRef]:
    """init + ท่อนเดียวที่มี t_ms (ไฟล์ mp4 ที่ ffmpeg เปิดได้ เวลาของไฟล์เริ่มที่เวลาของท่อน)"""
    ref = segment_for(index.sidx, t_ms)
    if ref is None:
        raise YtError("E_UNKNOWN", "time past the end of the index")
    body = read_range(ref.offset, ref.offset + ref.size - 1)
    if len(body) != ref.size:
        raise YtError("E_NETWORK", "short read")
    return index.init + body, ref


def write_piece(dest: Path, data: bytes) -> None:
    try:
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(data)
    except OSError as err:
        raise YtError("E_DISK_FULL" if err.errno == errno.ENOSPC else "E_UNKNOWN", type(err).__name__) from err


def max_short_side(quality: str) -> int | None:
    if quality not in CAPTURE_SHORT_SIDES:
        raise ValueError(f"unknown capture quality: {quality!r}")
    return CAPTURE_SHORT_SIDES[quality]


def _positive(value: Any) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    return int(value) if value > 0 else None


def short_side(fmt: Mapping[str, Any]) -> int:
    width, height = _positive(fmt.get("width")), _positive(fmt.get("height"))
    if width and height:
        return min(width, height)
    return height or 0


def _is_sdr(fmt: Mapping[str, Any]) -> bool:
    value = fmt.get("dynamic_range")
    return value is None or str(value).strip().upper() in ("", "SDR")


def _codec_rank(fmt: Mapping[str, Any]) -> int:
    vcodec = str(fmt.get("vcodec") or "").lower()
    if vcodec.startswith("avc1"):
        return 0
    if vcodec.startswith("av01"):
        return 1
    return 2


def _is_candidate(fmt: object) -> bool:
    """mp4 ภาพอย่างเดียวที่โหลดผ่าน https ตรง ๆ (ไฟล์แบบนี้ของยูทูปมี sidx) และรู้ขนาดภาพ"""
    if not isinstance(fmt, Mapping):
        return False
    vcodec = fmt.get("vcodec")
    url = fmt.get("url")
    return (
        fmt.get("ext") == "mp4"
        and fmt.get("protocol") == "https"
        and isinstance(vcodec, str)
        and vcodec not in ("", "none")
        and fmt.get("acodec") in (None, "none")
        and isinstance(url, str)
        and url != ""
        and short_side(fmt) > 0
    )


def _rank(fmt: Mapping[str, Any]) -> tuple:
    size = _positive(fmt.get("filesize")) or _positive(fmt.get("filesize_approx"))
    return (-short_side(fmt), not _is_sdr(fmt), _codec_rank(fmt), size is None, size or 0, str(fmt.get("format_id")))


def pick_capture_format(info: Mapping[str, Any], max_short_side: int | None) -> dict | None:
    """format ที่ใช้ถ่ายภาพ (spec 3.1 ข้อ 2): ด้านสั้นมากสุดที่ไม่เกินเพดาน > SDR > avc1 > av01 > ไฟล์เล็กสุด
    ไม่มีตัวที่ไม่เกินเพดาน = ตัวที่ด้านสั้นเล็กที่สุดเหนือเพดาน · ไม่มี mp4 ภาพอย่างเดียวผ่าน https เลย = None"""
    candidates = [dict(f) for f in (info.get("formats") or []) if _is_candidate(f)]
    if not candidates:
        return None
    pool = [f for f in candidates if max_short_side is None or short_side(f) <= max_short_side]
    if not pool:
        smallest = min(short_side(f) for f in candidates)
        pool = [f for f in candidates if short_side(f) == smallest]
    return min(pool, key=_rank)


def piece_info(fmt: Mapping[str, Any], path: Path, index: SidxIndex, ref: SidxRef) -> PieceInfo:
    return PieceInfo(
        path=path,
        segment_start_ms=index.to_ms(ref.start),
        width=_positive(fmt.get("width")),
        height=_positive(fmt.get("height")),
        format_id=str(fmt.get("format_id") or ""),
        dynamic_range=None if _is_sdr(fmt) else str(fmt.get("dynamic_range")),
    )
```

- [ ] **Step 5: Document the fixture** — append to `tests/fixtures/README.md`:
```markdown

## capture/ (M5 รอบ B2 ถ่ายภาพคมตรงจุด)
- `piece.mp4`: วิดีโอสังเคราะห์ 4 วินาที 1920×1080 10 fps (`testsrc` ของ ffmpeg) แบบ fragmented mp4 ที่เรียงกล่องแบบไฟล์ DASH ของยูทูป: `ftyp`, `moov`, `sidx` (version 1, timescale 10240, 4 ท่อน ท่อนละ 1 วินาที) แล้ว `moof`+`mdat` ทีละท่อน · ไม่มี B-frame ไฟล์จึงเริ่มที่เวลา 0 · ราว 50 KB
- สร้างครั้งเดียวด้วย ffmpeg 8.1 (Gyan full build) แล้ว commit ไว้ เทสไม่สร้างใหม่ (ffmpeg รุ่นอื่นได้ไบต์ต่างกันเล็กน้อย เทสตรวจแค่โครงสร้าง):
  `ffmpeg -f lavfi -i "testsrc=size=1920x1080:rate=10:duration=4" -c:v libx264 -preset veryslow -crf 40 -bf 0 -g 10 -keyint_min 10 -sc_threshold 0 -pix_fmt yuv420p -an -movflags +frag_keyframe+empty_moov+default_base_moof+global_sidx -fflags +bitexact -flags:v +bitexact piece.mp4`
- ใช้กับ `core/frame_piece.py` (เทสตัวอ่าน sidx), `FakeExtractor.fetch_frame_piece` (ตัดชิ้นด้วยตัวอ่านตัวจริง เวลาเกิน 4 วินาทีวนกลับด้วย `t % 4000`) และเทส ffmpeg จริงของการถ่ายภาพ (ภาพจากชิ้นต้องตรงกับภาพจากไฟล์เต็มที่เวลาเดียวกัน)
```

- [ ] **Step 6: Run the tests, expect PASS** — same command as Step 3 (27 passed), then `cd "$WORKTREE" && uv run pytest -q -W error -p no:cacheprovider`.

- [ ] **Step 7: Commit**
```bash
cd "$WORKTREE" && git add src/yttoolkit/core/frame_piece.py tests/unit/test_frame_piece.py tests/fixtures/capture/piece.mp4 tests/fixtures/README.md && git ls-files --eol tests/fixtures/capture/piece.mp4 && git commit -F- <<'EOF'
feat(capture): M5-B2 pure sidx reader, capture format choice and the DASH fixture

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
EOF
```
Expected `git ls-files --eol` line: `i/-text w/-text attr/text=auto eol=lf …piece.mp4`.

### Task 3: Frame extraction without scaling (`long_side=None`)

**Files:**
- Modify: `src/yttoolkit/core/media.py` (`_check_frame`, `frame_args`, `MediaTools.extract_frame`, `FfmpegTools.extract_frame`, `FrameCall`, `FakeMediaTools.extract_frame` signatures)
- Modify: `tests/unit/test_media_args.py`, `tests/integration/test_sharp_ffmpeg.py`

**Interfaces:**
- Consumes: round B `frame_args`, `scale_filter`, `tonemap_filter`.
- Produces: C3 exactly (every round B call with an int keeps its exact arguments).

- [ ] **Step 1: Write the failing tests**

In `tests/unit/test_media_args.py`, add after `test_frame_args_hdr_puts_the_tone_map_before_the_scale`:
```python
def test_frame_args_without_long_side_keeps_the_source_size() -> None:  # M5 รอบ B2 ภาพคมตรงจุด
    assert frame_args(FF, SRC, JPG, 125_400, long_side=None) == FRAME_HEAD + [
        "-ss", "125.400", "-i", str(SRC), "-frames:v", "1", "-q:v", "2", str(JPG)]  # fmt: skip
    hdr = frame_args(FF, SRC, JPG, 0, long_side=None, dynamic_range="HDR10")
    assert hdr[hdr.index("-vf") + 1] == tonemap_filter("HDR10")


@pytest.mark.parametrize("long_side", [0, -5, True, 1.5])
def test_long_side_must_be_none_or_a_positive_int(long_side) -> None:
    with pytest.raises(ValueError):
        frame_args(FF, SRC, JPG, 0, long_side=long_side)


def test_fake_extract_frame_records_no_long_side(tmp_path: Path) -> None:
    fake = FakeMediaTools(MEDIA_ROOT)
    dst = tmp_path / "frame.jpg"
    assert fake.extract_frame(MEDIA_ROOT / "video.mp4", dst, 400, long_side=None, dynamic_range=None,
                              cancel=_no_cancel) is True  # fmt: skip
    assert fake.frames == [FrameCall("video.mp4", "frame.jpg", 400, None, None)]
```
In `tests/integration/test_sharp_ffmpeg.py`, append:
```python
def test_no_long_side_keeps_the_source_resolution(clips, tmp_path: Path) -> None:  # M5 รอบ B2 spec 2.4
    wide, tall = tmp_path / "wide.jpg", tmp_path / "tall.jpg"
    assert _tools().extract_frame(clips["wide"], wide, 2000, long_side=None, dynamic_range=None, cancel=_never)
    assert _tools().extract_frame(clips["portrait"], tall, 2000, long_side=None, dynamic_range=None, cancel=_never)
    assert _size(wide) == (1920, 1080) and _size(tall) == (1080, 1920)


def test_no_long_side_with_hdr_tone_maps_at_the_source_size(clips, tmp_path: Path) -> None:
    dst = tmp_path / "h.jpg"
    assert _tools().extract_frame(clips["hdr"], dst, 1000, long_side=None, dynamic_range="HDR10", cancel=_never)
    assert _size(dst) == (1280, 720)
```

- [ ] **Step 2: Run them, expect FAIL**

Run: `cd "$WORKTREE" && uv run pytest tests/unit/test_media_args.py tests/integration/test_sharp_ffmpeg.py -q -W error -p no:cacheprovider`
Expected: FAIL (`TypeError: '<' not supported between instances of 'NoneType' and 'int'` in `_check_frame`).

- [ ] **Step 3: Implement**

Replace `_check_frame` and `frame_args` in `core/media.py` with:
```python
def _check_frame(t_ms: int, long_side: int | None, dynamic_range: str | None) -> None:
    """กฎเดียวกันทั้งตัวจริงและตัวปลอม · long_side None = ไม่ย่อ (ภาพคมตรงจุด M5 รอบ B2)"""
    if isinstance(t_ms, bool) or not isinstance(t_ms, int) or t_ms < 0:
        raise ValueError(f"bad frame time: {t_ms!r}")
    if long_side is not None and (isinstance(long_side, bool) or not isinstance(long_side, int) or long_side < 1):
        raise ValueError(f"bad long side: {long_side!r}")
    if dynamic_range is not None and dynamic_range.strip().upper() in ("", "SDR"):
        raise ValueError("pass dynamic_range=None for SDR")


def frame_args(
    ffmpeg: str,
    src: Path,
    dst: Path,
    t_ms: int,
    *,
    long_side: int | None = SHARP_LONG_SIDE,
    dynamic_range: str | None = None,
) -> list[str]:
    """ภาพคมหนึ่งภาพ (spec 3.4): -ss ก่อน -i บนไฟล์ในเครื่อง = ตรงเวลา · dynamic_range = HDR ที่ต้อง tone-map
    long_side None = เก็บความละเอียดเท่าต้นฉบับ (M5 รอบ B2) · ไม่มีตัวกรองเลย = ไม่ใส่ -vf"""
    _check_frame(t_ms, long_side, dynamic_range)
    filters: list[str] = []
    if dynamic_range is not None:
        filters.append(tonemap_filter(dynamic_range))
    if long_side is not None:
        filters.append(scale_filter(long_side))
    vf = ["-vf", ",".join(filters)] if filters else []
    return [ffmpeg, "-hide_banner", "-nostdin", "-y", "-loglevel", "error", "-ss", _seconds(t_ms), "-i", str(src),
            "-frames:v", "1", *vf, "-q:v", str(SHARP_JPEG_Q), str(dst)]  # fmt: skip
```
Change the annotation `long_side: int,` to `long_side: int | None,` in the three `extract_frame` signatures (`MediaTools`, `FfmpegTools`, `FakeMediaTools`), and in `FrameCall` change `long_side: int` to `long_side: int | None` (docstring unchanged).

- [ ] **Step 4: Run the tests, expect PASS** — same command as Step 2, then `cd "$WORKTREE" && uv run pytest -q -W error -p no:cacheprovider` (round B handler tests still pass `long_side=1280`).

- [ ] **Step 5: Commit**
```bash
cd "$WORKTREE" && git add src/yttoolkit/core/media.py tests/unit/test_media_args.py tests/integration/test_sharp_ffmpeg.py && git commit -F- <<'EOF'
feat(media): M5-B2 extract_frame keeps the source size when long_side is None

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
EOF
```

### Task 4: Web strings and types

**Files:**
- Modify: `web/src/i18n/th.ts` (new sections `theater`, `capture`; `general` additions)
- Modify: `web/src/lib/types.ts` (`CaptureQuality`, `Capture`, `CaptureList`, `Settings.captureQuality`)
- Modify (fixture line only): `web/src/lib/download-options.test.ts`, `web/src/lib/download-prefs.test.ts`, `web/src/pages/settings/general-form.test.ts`, `web/src/pages/video/advanced/use-advanced-choice.test.ts`

**Interfaces:**
- Consumes: spec copy (sections 1.1, 2.1-2.4).
- Produces: C4 exactly. T4 is the only writer of `th.ts` in this round.

- [ ] **Step 1: Add the strings to `web/src/i18n/th.ts`**

Right after the closing `},` of the `sharp: { … }` section add:
```ts
  // M5 รอบ B2: โหมดโรงภาพยนตร์ (ปุ่มในแถวใต้ตัวเล่น ข้อความเปลี่ยนตามสถานะ + tooltip)
  theater: {
    expand: "ขยายตัวเล่น (T)",
    collapse: "ย่อตัวเล่น (T)",
    tooltip: "โหมดโรงภาพยนตร์",
  },
  // M5 รอบ B2: ถ่ายภาพคมตรงจุดที่ตัวเล่นอยู่ และแถบ "ภาพที่ถ่ายไว้" (ข้อความ error มาจาก backend)
  capture: {
    button: "ถ่ายภาพคมตรงนี้",
    busy: "กำลังถ่าย…",
    done: "ถ่ายภาพคมแล้ว · {time}",
    view: "ดูภาพ",
    liveDisabled: "คลิปสดถ่ายภาพคมไม่ได้",
    pausedDisabled: "พักการโหลดอยู่เพราะยูทูปขอตรวจสอบ ลองใหม่หลัง {time}",
    stripTitle: "ภาพที่ถ่ายไว้ ({n})",
    openFolder: "เปิดโฟลเดอร์",
    delete: "ลบภาพนี้",
    deleteConfirm: "ลบภาพนี้ทั้งในแอพและในโฟลเดอร์ไหม",
    deleteAction: "ลบภาพ",
    cancel: "ยกเลิก",
    deleted: "ลบภาพแล้ว",
  },
```
In the `general` section, right after `autoSharpFramesHint: …,` add:
```ts
    // M5 รอบ B2 spec 2.4
    captureQuality: "ความละเอียดภาพที่ถ่าย",
    captureQualities: { max: "สูงสุดที่มี", "1080": "1080p", "720": "720p" },
    captureQualityHint: "ภาพยิ่งละเอียด ตัวหนังสือเล็กในคลิปยิ่งอ่านง่าย ใช้เน็ตต่อภาพมากขึ้น (4K ราว 8 MB)",
```

- [ ] **Step 2: Add the types to `web/src/lib/types.ts`**

Right after the `SharpSet` type add:
```ts
/** ภาพคมที่ถ่ายตรงจุด (M5 รอบ B2) · id = "c_<tMs>" · url มี ?v= อยู่แล้ว (ภาพ immutable) */
export type Capture = { id: string; tMs: number; width: number; height: number; url: string }

export type CaptureList = { captures: Capture[] }

/** ความละเอียดภาพที่ถ่าย (เพดานนับที่ด้านสั้น) "max" = สูงสุดที่มี */
export type CaptureQuality = "max" | "1080" | "720"
```
In `Settings`, right after `autoSharpFrames: boolean` add:
```ts
  captureQuality: CaptureQuality
```

- [ ] **Step 3: Keep the four Settings test literals typed** — in each of `web/src/lib/download-options.test.ts`, `web/src/lib/download-prefs.test.ts`, `web/src/pages/settings/general-form.test.ts` and `web/src/pages/video/advanced/use-advanced-choice.test.ts`, add right after the line `autoSharpFrames: true,` (same indentation):
```ts
  captureQuality: "max",
```

- [ ] **Step 4: Verify**

Run: `cd "$WORKTREE/web" && npm run typecheck && npm run lint && npm test`
Expected: all pass (no consumer of the new strings yet; the four literals satisfy the new required `captureQuality`).

- [ ] **Step 5: Commit**
```bash
cd "$WORKTREE" && git add web/src/i18n/th.ts web/src/lib/types.ts web/src/lib/download-options.test.ts web/src/lib/download-prefs.test.ts web/src/pages/settings/general-form.test.ts web/src/pages/video/advanced/use-advanced-choice.test.ts && git commit -F- <<'EOF'
feat(web): M5-B2 theater and capture strings, Capture types, captureQuality setting type

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
EOF
```

### Task 5: Theater model (pure)

**Files:**
- Create: `web/src/pages/video/theater.ts`, `web/src/pages/video/theater.test.ts`

**Interfaces:**
- Consumes: `VideoInfo` (`web/src/lib/types.ts:53-77`).
- Produces: C5 exactly.

- [ ] **Step 1: Write the failing test** — create `web/src/pages/video/theater.test.ts`:
```ts
import { describe, expect, it, vi } from "vitest"

import {
  headerLayout,
  isEditableTarget,
  isPortraitVideo,
  isTheaterOn,
  readTheaterPreference,
  runLayoutTransition,
  SWITCHING_ATTR,
  THEATER_KEY,
  theaterKeyAllowed,
  theaterReducer,
  writeTheaterPreference,
  type KeyLike,
  type PreferenceStorage,
  type TheaterState,
  type TransitionDoc,
} from "./theater"

const BBB = "aqz-KE-bpKQ"
const THAI = "88o5Sk8_m1Y"
const START: TheaterState = { videoId: null, on: false }

describe("theaterReducer", () => {
  it("▶ กับค่าที่จำไว้เป็นโรงภาพยนตร์ = ขยาย · ค่าที่จำไว้เป็นแบบปกติ = คงเดิม", () => {
    expect(theaterReducer(START, { type: "play", videoId: BBB, preference: true })).toEqual({ videoId: BBB, on: true })
    expect(theaterReducer(START, { type: "play", videoId: BBB, preference: false })).toEqual({ videoId: BBB, on: false })
  })

  it("ปุ่ม/T สลับ · ▶ ซ้ำตอนขยายอยู่ไม่ย่อแม้ค่าที่จำไว้เป็นแบบปกติ", () => {
    const on = theaterReducer(START, { type: "toggle", videoId: BBB })
    expect(on).toEqual({ videoId: BBB, on: true })
    expect(theaterReducer(on, { type: "play", videoId: BBB, preference: false })).toBe(on)
    expect(theaterReducer(on, { type: "toggle", videoId: BBB })).toEqual({ videoId: BBB, on: false })
  })

  it("เปิดคลิปอื่น = แบบปกติจนกว่าจะกด ▶", () => {
    const on: TheaterState = { videoId: BBB, on: true }
    expect(isTheaterOn(on, BBB)).toBe(true)
    expect(isTheaterOn(on, THAI)).toBe(false)
    expect(theaterReducer(on, { type: "toggle", videoId: THAI })).toEqual({ videoId: THAI, on: true })
    expect(theaterReducer(on, { type: "play", videoId: THAI, preference: false })).toEqual({ videoId: THAI, on: false })
  })
})

function memory(initial?: string): PreferenceStorage & { items: Map<string, string> } {
  const items = new Map<string, string>()
  if (initial !== undefined) items.set(THEATER_KEY, initial)
  return {
    items,
    getItem: (key: string) => items.get(key) ?? null,
    setItem: (key: string, value: string) => void items.set(key, value),
  }
}

const throwing: PreferenceStorage = {
  getItem: () => {
    throw new Error("blocked")
  },
  setItem: () => {
    throw new Error("blocked")
  },
}

describe("ค่าที่จำไว้", () => {
  it("ไม่มีค่า = โรงภาพยนตร์ · '0' = แบบปกติ · '1' = โรงภาพยนตร์", () => {
    expect(readTheaterPreference(memory())).toBe(true)
    expect(readTheaterPreference(memory("0"))).toBe(false)
    expect(readTheaterPreference(memory("1"))).toBe(true)
  })

  it("เขียน '1' / '0' ใต้ key yt-toolkit:theater", () => {
    const storage = memory()
    writeTheaterPreference(storage, false)
    expect(storage.items.get("yt-toolkit:theater")).toBe("0")
    writeTheaterPreference(storage, true)
    expect(storage.items.get("yt-toolkit:theater")).toBe("1")
  })

  it("ที่เก็บใช้ไม่ได้ (null หรือโยน error) = โรงภาพยนตร์ และเขียนไม่พัง", () => {
    expect(readTheaterPreference(null)).toBe(true)
    expect(readTheaterPreference(throwing)).toBe(true)
    expect(() => writeTheaterPreference(throwing, false)).not.toThrow()
    expect(() => writeTheaterPreference(null, false)).not.toThrow()
  })
})

const fmt = (height: number, width?: number) => ({ formatId: `f${height}x${width ?? 0}`, height, width, fps: 30, vcodec: "avc1", compat: true })

describe("isPortraitVideo", () => {
  it("ดูรายการที่สูงที่สุด ต้องรู้ความกว้างและกว้างน้อยกว่าสูง", () => {
    expect(isPortraitVideo({ video: [] })).toBe(false)
    expect(isPortraitVideo({ video: [fmt(1080, 1920), fmt(720, 1280)] })).toBe(false)
    expect(isPortraitVideo({ video: [fmt(1920, 1080), fmt(1280, 720)] })).toBe(true)
    expect(isPortraitVideo({ video: [fmt(1920)] })).toBe(false)
    expect(isPortraitVideo({ video: [fmt(1080, 1920), fmt(1280, 720)] })).toBe(true)
    expect(isPortraitVideo({ video: [fmt(1080, 1080)] })).toBe(false)
  })
})

describe("headerLayout", () => {
  it("ปิด หรือจอแคบ = แบบปกติ · แนวนอน = กว้าง · แนวตั้ง = สูง", () => {
    expect(headerLayout({ on: false, narrow: false, portrait: false })).toBe("compact")
    expect(headerLayout({ on: true, narrow: true, portrait: false })).toBe("compact")
    expect(headerLayout({ on: true, narrow: false, portrait: false })).toBe("theater-wide")
    expect(headerLayout({ on: true, narrow: false, portrait: true })).toBe("theater-tall")
  })
})

describe("ปุ่ม T", () => {
  const key = (patch: Partial<KeyLike> = {}): KeyLike => ({
    key: "t",
    ctrlKey: false,
    altKey: false,
    metaKey: false,
    repeat: false,
    defaultPrevented: false,
    target: { tagName: "BODY" },
    ...patch,
  })
  const ready = { canToggle: true, overlayOpen: false }

  it("t และ T สลับได้ (Shift ไม่นับเป็นปุ่มเสริม)", () => {
    expect(theaterKeyAllowed(key(), ready)).toBe(true)
    expect(theaterKeyAllowed(key({ key: "T" }), ready)).toBe(true)
    expect(theaterKeyAllowed(key({ key: "y" }), ready)).toBe(false)
  })

  it("ยังไม่เล่น/จอแคบ หรือมีกล่อง/เมนูเปิดอยู่ = ไม่สลับ", () => {
    expect(theaterKeyAllowed(key(), { canToggle: false, overlayOpen: false })).toBe(false)
    expect(theaterKeyAllowed(key(), { canToggle: true, overlayOpen: true })).toBe(false)
  })

  it("Ctrl/Alt/Meta กดค้าง หรือมีคนจัดการไปแล้ว = ไม่สลับ", () => {
    for (const patch of [{ ctrlKey: true }, { altKey: true }, { metaKey: true }, { repeat: true }, { defaultPrevented: true }]) {
      expect(theaterKeyAllowed(key(patch), ready)).toBe(false)
    }
  })

  it("พิมพ์อยู่ในช่องกรอก = ไม่สลับ", () => {
    for (const target of [{ tagName: "INPUT" }, { tagName: "textarea" }, { tagName: "SELECT" }, { tagName: "DIV", isContentEditable: true }]) {
      expect(isEditableTarget(target)).toBe(true)
      expect(theaterKeyAllowed(key({ target }), ready)).toBe(false)
    }
    expect(isEditableTarget(null)).toBe(false)
    expect(isEditableTarget({ tagName: "BUTTON" })).toBe(false)
  })
})

describe("runLayoutTransition", () => {
  function fakeDoc(withApi: boolean, fail = false) {
    const attrs = new Map<string, string>()
    let settle: () => void = () => undefined
    const finished = new Promise<void>((resolve, reject) => {
      settle = fail ? () => reject(new Error("skipped")) : resolve
    })
    const start = vi.fn((update: () => void) => {
      update()
      return { finished }
    })
    const doc: TransitionDoc = {
      documentElement: { setAttribute: (name, value) => void attrs.set(name, value), removeAttribute: (name) => void attrs.delete(name) },
      ...(withApi ? { startViewTransition: start } : {}),
    }
    return { doc, attrs, start, settle: () => settle() }
  }

  it("ไม่มี API = สลับทันที ไม่ใส่ชื่อ", () => {
    const { doc, attrs } = fakeDoc(false)
    const apply = vi.fn()
    runLayoutTransition(apply, { doc, animate: true })
    expect(apply).toHaveBeenCalledOnce()
    expect(attrs.size).toBe(0)
  })

  it("ลดการเคลื่อนไหวหรือตัวเล่นลอย (animate false) = สลับทันทีแม้มี API", () => {
    const { doc, start } = fakeDoc(true)
    const apply = vi.fn()
    runLayoutTransition(apply, { doc, animate: false })
    expect(apply).toHaveBeenCalledOnce()
    expect(start).not.toHaveBeenCalled()
  })

  it("มี API: ใส่ชื่อระหว่างสลับ แล้วเอาออกเมื่อจบ", async () => {
    const { doc, attrs, start, settle } = fakeDoc(true)
    const apply = vi.fn()
    runLayoutTransition(apply, { doc, animate: true })
    expect(start).toHaveBeenCalledOnce()
    expect(apply).toHaveBeenCalledOnce()
    expect(attrs.has(SWITCHING_ATTR)).toBe(true)
    settle()
    await vi.waitFor(() => expect(attrs.has(SWITCHING_ATTR)).toBe(false))
  })

  it("transition ถูกข้าม (reject) ก็เอาชื่อออก", async () => {
    const { doc, attrs, settle } = fakeDoc(true, true)
    runLayoutTransition(() => undefined, { doc, animate: true })
    settle()
    await vi.waitFor(() => expect(attrs.has(SWITCHING_ATTR)).toBe(false))
  })
})
```

- [ ] **Step 2: Run it, expect FAIL**

Run: `cd "$WORKTREE/web" && npx vitest run src/pages/video/theater.test.ts`
Expected: FAIL (`Failed to resolve import "./theater"`).

- [ ] **Step 3: Implement** — create `web/src/pages/video/theater.ts`:
```ts
import type { VideoInfo } from "@/lib/types"

/**
 * โหมดโรงภาพยนตร์ของหัวคลิป W2 (M5 รอบ B2 spec 1): ส่วนที่ไม่แตะ React (เทสได้ใน node)
 * ค่าที่จำไว้ (localStorage) · ตัวลดสถานะ · คลิปแนวตั้ง · เลย์เอาต์ · ปุ่ม T · การสลับด้วย View Transition
 */

export const THEATER_KEY = "yt-toolkit:theater"
/** ใส่ที่ <html> เฉพาะระหว่างสลับ: CSS ตั้งชื่อ view transition ให้ช่องตัวเล่นและคอลัมน์ข้อมูลเฉพาะช่วงนี้ */
export const SWITCHING_ATTR = "data-theater-switching"

export type TheaterState = { videoId: string | null; on: boolean }

export type TheaterAction =
  /** กด ▶ ในช่องตัวเล่น: ค่าที่จำไว้เป็นโรงภาพยนตร์ = ขยาย */
  | { type: "play"; videoId: string; preference: boolean }
  /** ปุ่มหรือปุ่ม T */
  | { type: "toggle"; videoId: string }

/** สถานะของคลิปที่เปิดอยู่: เปิดคลิปอื่น = แบบปกติจนกว่าจะกด ▶ (ค่าของคลิปเดิมไม่ติดมา) */
export function isTheaterOn(state: TheaterState, videoId: string): boolean {
  return state.videoId === videoId && state.on
}

export function theaterReducer(state: TheaterState, action: TheaterAction): TheaterState {
  const current = isTheaterOn(state, action.videoId)
  if (action.type === "toggle") return { videoId: action.videoId, on: !current }
  const on = current || action.preference
  return state.videoId === action.videoId && state.on === on ? state : { videoId: action.videoId, on }
}

export type PreferenceStorage = Pick<Storage, "getItem" | "setItem">

/** localStorage ของเบราว์เซอร์ · เบราว์เซอร์ที่ปิดการเก็บข้อมูลโยน error ตั้งแต่แตะชื่อ = null (ใช้ค่าเริ่มต้น) */
export function safeStorage(): PreferenceStorage | null {
  try {
    return typeof window === "undefined" ? null : window.localStorage
  } catch {
    return null
  }
}

/** "0" = แบบปกติ · ไม่มีค่า ค่าอื่น หรืออ่านไม่ได้ = โรงภาพยนตร์ (ค่าเริ่มต้น spec 1.1) */
export function readTheaterPreference(storage: PreferenceStorage | null): boolean {
  if (!storage) return true
  try {
    return storage.getItem(THEATER_KEY) !== "0"
  } catch {
    return true
  }
}

export function writeTheaterPreference(storage: PreferenceStorage | null, on: boolean): void {
  if (!storage) return
  try {
    storage.setItem(THEATER_KEY, on ? "1" : "0")
  } catch {
    // ที่เก็บเต็มหรือถูกปิด: ไม่จำ ครั้งหน้าใช้ค่าเริ่มต้น
  }
}

/** คลิปแนวตั้ง (Shorts/Reel): รายการภาพที่สูงที่สุด (สูงเท่ากันดูความกว้าง) รู้ความกว้างและกว้างน้อยกว่าสูง */
export function isPortraitVideo(video: Pick<VideoInfo, "video">): boolean {
  let best: VideoInfo["video"][number] | null = null
  for (const format of video.video) {
    if (best === null || format.height > best.height || (format.height === best.height && (format.width ?? 0) > (best.width ?? 0))) {
      best = format
    }
  }
  return best !== null && best.width !== undefined && best.width > 0 && best.width < best.height
}

export type HeaderLayout = "compact" | "theater-wide" | "theater-tall"

/** จอแคบ (< 640 px) เต็มความกว้างอยู่แล้ว: โหมดโรงภาพยนตร์ไม่เปลี่ยนอะไร */
export function headerLayout(o: { on: boolean; narrow: boolean; portrait: boolean }): HeaderLayout {
  if (!o.on || o.narrow) return "compact"
  return o.portrait ? "theater-tall" : "theater-wide"
}

export type KeyLike = {
  key: string
  ctrlKey: boolean
  altKey: boolean
  metaKey: boolean
  repeat: boolean
  defaultPrevented: boolean
  target: unknown
}

const EDITABLE_TAGS = new Set(["INPUT", "TEXTAREA", "SELECT"])

/** โฟกัสอยู่ในช่องกรอก (input, textarea, select, contenteditable) */
export function isEditableTarget(target: unknown): boolean {
  if (typeof target !== "object" || target === null) return false
  const node = target as { tagName?: unknown; isContentEditable?: unknown }
  return (typeof node.tagName === "string" && EDITABLE_TAGS.has(node.tagName.toUpperCase())) || node.isContentEditable === true
}

/**
 * ปุ่ม T / t สลับโหมดเมื่อ: เริ่มเล่นแล้วและจอไม่แคบ (canToggle) · ไม่มีกล่องหรือเมนูเปิดอยู่ · ไม่ได้พิมพ์อยู่ในช่องกรอก
 * · ไม่กด Ctrl/Alt/Meta · ไม่ใช่การกดค้าง · Shift ไม่นับ (Shift+T ได้ "T" ซึ่ง spec ให้ใช้ได้)
 */
export function theaterKeyAllowed(event: KeyLike, ctx: { canToggle: boolean; overlayOpen: boolean }): boolean {
  if (event.key !== "t" && event.key !== "T") return false
  if (!ctx.canToggle || ctx.overlayOpen) return false
  if (event.ctrlKey || event.altKey || event.metaKey || event.repeat || event.defaultPrevented) return false
  return !isEditableTarget(event.target)
}

export function prefersReducedMotion(): boolean {
  return typeof window !== "undefined" && typeof window.matchMedia === "function" && window.matchMedia("(prefers-reduced-motion: reduce)").matches
}

export type TransitionDoc = {
  documentElement: { setAttribute(name: string, value: string): void; removeAttribute(name: string): void }
  startViewTransition?: (update: () => void) => { finished: Promise<unknown> }
}

/**
 * สลับเลย์เอาต์ (spec 1.3): มี document.startViewTransition และ animate = ทำผ่าน View Transition (ชื่อของช่องตัวเล่นกับคอลัมน์ข้อมูล
 * ใส่ด้วย SWITCHING_ATTR เฉพาะระหว่างนั้น) · ไม่มี API, ผู้ใช้ขอลดการเคลื่อนไหว หรือตัวเล่นลอยอยู่ (animate false) = สลับทันที
 * apply ต้องอัปเดต DOM ให้เสร็จในตัว (React: flushSync) ภาพหลังสลับจึงถูกจับหลัง DOM เปลี่ยนแล้ว
 */
export function runLayoutTransition(apply: () => void, env: { doc: TransitionDoc; animate: boolean }): void {
  const start = env.doc.startViewTransition
  if (!env.animate || typeof start !== "function") {
    apply()
    return
  }
  const root = env.doc.documentElement
  const clear = () => root.removeAttribute(SWITCHING_ATTR)
  root.setAttribute(SWITCHING_ATTR, "")
  try {
    start.call(env.doc, apply).finished.then(clear, clear)
  } catch {
    clear()
    apply()
  }
}
```

- [ ] **Step 4: Run it, expect PASS** (16 tests), then `cd "$WORKTREE/web" && npm run typecheck && npm run lint && npm test`.

- [ ] **Step 5: Commit**
```bash
cd "$WORKTREE" && git add web/src/pages/video/theater.ts web/src/pages/video/theater.test.ts && git commit -F- <<'EOF'
feat(web): M5-B2 theater model (preference, layouts, T key guard, view transition runner)

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
EOF
```

## Wave 2

### Task 6: Extractor `fetch_frame_piece` (real + fake) and the fake capture clips

**Files:**
- Modify: `src/yttoolkit/core/extractor.py` (imports, `_FAKE_CAPTURE_FORMAT`, `YtDlpExtractor.fetch_frame_piece`, `FakeExtractor.CAPTURE_FIXTURE` + `fetch_frame_piece`)
- Modify: `tests/fixtures/downloads/behaviors.json` (4 clips), `tests/unit/test_extractor_download.py` (the literal `C14`), `tests/fixtures/README.md` (behaviors rows)
- Create: `tests/unit/test_extractor_capture.py`

**Interfaces:**
- Consumes: C2 (`read_index`, `fetch_piece`, `pick_capture_format`, `piece_info`, `write_piece`, `PieceInfo`) from T2; existing `_ydl`, `_PROBE_OPTS`, `check_live`, `classify`, `_ANSI`, `FakeExtractor.probe/_behavior`.
- Produces: C6 exactly.

- [ ] **Step 1: Add the fake clips (test data first)**

In `tests/fixtures/downloads/behaviors.json` replace the last entry line and the closing of `"videos"`:
```json
    "AUTOSHARP01": {"probeAs": "aqz-KE-bpKQ", "title": "คลิปภาพคมอัตโนมัติ", "media": {"width": 1280, "height": 720, "dynamic_range": "SDR"}},
    "CAPTURE0001": {"probeAs": "aqz-KE-bpKQ", "title": "คลิปถ่ายภาพคม"},
    "CAPTURENO01": {"probeAs": "aqz-KE-bpKQ", "title": "คลิปถ่ายภาพคมไม่ได้", "captureError": "E_CAPTURE_UNSUPPORTED"},
    "CAPTUREBOT1": {"probeAs": "aqz-KE-bpKQ", "title": "คลิปถ่ายภาพคมติดบอท", "captureError": "E_BOT_CHECK"},
    "CAPTURENET1": {"probeAs": "aqz-KE-bpKQ", "title": "คลิปถ่ายภาพคมเน็ตหลุด", "captureError": "E_NETWORK"}
  }
```
In `tests/unit/test_extractor_download.py`, inside `C14["videos"]`, right after the `"AUTOSHARP01": {…},` entry add:
```python
        "CAPTURE0001": {"probeAs": BBB, "title": "คลิปถ่ายภาพคม"},
        "CAPTURENO01": {"probeAs": BBB, "title": "คลิปถ่ายภาพคมไม่ได้", "captureError": "E_CAPTURE_UNSUPPORTED"},
        "CAPTUREBOT1": {"probeAs": BBB, "title": "คลิปถ่ายภาพคมติดบอท", "captureError": "E_BOT_CHECK"},
        "CAPTURENET1": {"probeAs": BBB, "title": "คลิปถ่ายภาพคมเน็ตหลุด", "captureError": "E_NETWORK"},
```
In `tests/fixtures/README.md`, append to the `## capture/` section (T2 created it):
```markdown
- คลิปปลอมใน `downloads/behaviors.json` (ทุกตัว `probeAs` BBB): `CAPTURE0001` ถ่ายได้ปกติ · `CAPTURENO01` (`captureError: E_CAPTURE_UNSUPPORTED`) · `CAPTUREBOT1` (`E_BOT_CHECK`) · `CAPTURENET1` (`E_NETWORK`) · คลิปอื่นทุกตัวถ่ายได้จาก fixture เดียวกัน
```

- [ ] **Step 2: Write the failing tests** — create `tests/unit/test_extractor_capture.py`:
```python
"""ถ่ายภาพคมตรงจุดของ extractor (M5 รอบ B2 C6): ตัวปลอมตัดชิ้นจาก fixture · ตัวจริงยิงคำขอแบบ Range ผ่าน yt-dlp (ถูกแทน ไม่ต่อเน็ต)"""

from __future__ import annotations

import io
import logging
from pathlib import Path
from typing import Any, ClassVar, Self

import pytest
import yt_dlp
from yt_dlp.networking import Response
from yt_dlp.networking.exceptions import HTTPError, TransportError
from yt_dlp.utils import DownloadError

from yttoolkit.core.extractor import FakeExtractor, YtDlpExtractor
from yttoolkit.core.frame_piece import MediaIndex, read_index
from yttoolkit.core.yterrors import YtError

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
PIECE = FIXTURES / "capture" / "piece.mp4"
BBB = "aqz-KE-bpKQ"
MEDIA_URL = "https://media.invalid/videoplayback?sig=SECRET"


def _index() -> tuple[bytes, MediaIndex]:
    data = PIECE.read_bytes()
    return data, read_index(lambda first, last: data[first : last + 1])


# ---------- ตัวปลอม ----------


def test_fake_cuts_the_fixture_and_maps_the_time_back(tmp_path: Path) -> None:
    fake = FakeExtractor(FIXTURES)
    dest = tmp_path / "work" / "piece.mp4"
    info = fake.fetch_frame_piece(BBB, 125_400, None, dest)
    data, index = _index()
    segment = index.sidx.refs[1]  # 125_400 % 4000 = 1400 อยู่ท่อนที่เริ่ม 1000
    assert dest.read_bytes() == index.init + data[segment.offset : segment.offset + segment.size]
    assert info.path == dest and info.segment_start_ms == 125_000
    assert (info.width, info.height, info.format_id, info.dynamic_range) == (1920, 1080, "fake-capture", None)
    assert ("fetch_frame_piece", BBB) in fake.calls


def test_fake_capture_clip_ignores_the_cap(tmp_path: Path) -> None:
    info = FakeExtractor(FIXTURES).fetch_frame_piece("CAPTURE0001", 3_999, 720, tmp_path / "p.mp4")
    assert info.segment_start_ms == 3_000 and info.height == 1080


@pytest.mark.parametrize(
    ("video_id", "code"),
    [
        ("CAPTURENO01", "E_CAPTURE_UNSUPPORTED"),
        ("CAPTUREBOT1", "E_BOT_CHECK"),
        ("CAPTURENET1", "E_NETWORK"),
        ("PRIVATEVID1", "E_VIDEO_PRIVATE"),
        ("UPCOMINGLV1", "E_LIVE_NOT_READY"),
        ("zzzzzzzzzzz", "E_VIDEO_UNAVAILABLE"),
    ],
)
def test_fake_failures_write_nothing(tmp_path: Path, video_id: str, code: str) -> None:
    dest = tmp_path / "piece.mp4"
    with pytest.raises(YtError) as info:
        FakeExtractor(FIXTURES).fetch_frame_piece(video_id, 1000, None, dest)
    assert info.value.code == code
    assert not dest.exists()


# ---------- ตัวจริง (yt_dlp.YoutubeDL ถูกแทน) ----------


def _format(**extra: Any) -> dict:
    return {
        "format_id": "137", "ext": "mp4", "protocol": "https", "vcodec": "avc1.640028", "acodec": "none",
        "width": 1920, "height": 1080, "url": MEDIA_URL, "http_headers": {"User-Agent": "ua", "Accept": "*/*"},
        **extra,
    }  # fmt: skip


class CaptureYDL:
    """แทน yt_dlp.YoutubeDL: extract_info คืน info ที่ตั้งไว้ · urlopen ตอบตามช่วงไบต์ของหัว Range จาก body"""

    instances: ClassVar[list[CaptureYDL]] = []
    info: ClassVar[object] = None
    body: ClassVar[bytes] = b""
    fail: ClassVar[BaseException | None] = None

    def __init__(self, params: dict) -> None:
        self.params = params
        self.url = ""
        self.requests: list[Any] = []
        CaptureYDL.instances.append(self)

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *exc: object) -> None:
        return None

    def extract_info(self, url: str, download: bool = True) -> object:
        assert download is False
        self.url = url
        if isinstance(CaptureYDL.info, BaseException):
            raise CaptureYDL.info
        return CaptureYDL.info

    def sanitize_info(self, info: dict, remove_private_keys: bool = False) -> dict:
        return info

    def urlopen(self, request: Any) -> Response:
        self.requests.append(request)
        if CaptureYDL.fail is not None:
            raise CaptureYDL.fail
        first, last = (int(n) for n in request.headers["Range"].removeprefix("bytes=").split("-"))
        return Response(io.BytesIO(CaptureYDL.body[first : last + 1]), request.url, {}, status=206)


@pytest.fixture
def ydl(monkeypatch: pytest.MonkeyPatch) -> type[CaptureYDL]:
    CaptureYDL.instances = []
    CaptureYDL.info = {"id": BBB, "live_status": "not_live", "formats": [_format()]}
    CaptureYDL.body = PIECE.read_bytes()
    CaptureYDL.fail = None
    monkeypatch.setattr(yt_dlp, "YoutubeDL", CaptureYDL)
    return CaptureYDL


def test_real_fetches_the_head_then_one_segment(ydl: type[CaptureYDL], tmp_path: Path, caplog) -> None:
    caplog.set_level(logging.INFO, logger="yttoolkit")
    dest = tmp_path / "piece.mp4"
    info = YtDlpExtractor().fetch_frame_piece(BBB, 2_550, 1080, dest)
    (inst,) = ydl.instances
    assert inst.url == f"https://www.youtube.com/watch?v={BBB}"
    assert inst.params["skip_download"] is True and inst.params["noplaylist"] is True
    data, index = _index()
    segment = index.sidx.refs[2]
    assert [r.headers["Range"] for r in inst.requests] == [
        "bytes=0-65535",
        f"bytes={segment.offset}-{segment.offset + segment.size - 1}",
    ]
    assert all(r.url == MEDIA_URL and r.headers["User-Agent"] == "ua" for r in inst.requests)
    assert dest.read_bytes() == index.init + data[segment.offset : segment.offset + segment.size]
    assert (info.segment_start_ms, info.format_id, info.width, info.height, info.dynamic_range) == (
        2_000, "137", 1920, 1080, None)  # fmt: skip
    assert "137" in caplog.text
    for secret in ("SECRET", "media.invalid", "User-Agent", str(tmp_path)):
        assert secret not in caplog.text


def test_real_respects_the_short_side_cap(ydl: type[CaptureYDL], tmp_path: Path) -> None:
    ydl.info = {"id": BBB, "live_status": "not_live",
                "formats": [_format(), _format(format_id="401", width=3840, height=2160, vcodec="av01.0.12M.08")]}  # fmt: skip
    assert YtDlpExtractor().fetch_frame_piece(BBB, 0, None, tmp_path / "a.mp4").format_id == "401"
    assert YtDlpExtractor().fetch_frame_piece(BBB, 0, 1080, tmp_path / "b.mp4").format_id == "137"


def test_real_without_an_mp4_format_is_unsupported_and_requests_nothing(ydl: type[CaptureYDL], tmp_path: Path) -> None:
    ydl.info = {"id": BBB, "live_status": "not_live", "formats": [_format(ext="webm", vcodec="vp9")]}
    with pytest.raises(YtError) as info:
        YtDlpExtractor().fetch_frame_piece(BBB, 0, None, tmp_path / "p.mp4")
    assert info.value.code == "E_CAPTURE_UNSUPPORTED"
    assert ydl.instances[0].requests == []


def test_real_live_clip_is_refused(ydl: type[CaptureYDL], tmp_path: Path) -> None:
    ydl.info = {"id": BBB, "live_status": "is_live", "formats": [_format()]}
    with pytest.raises(YtError) as info:
        YtDlpExtractor().fetch_frame_piece(BBB, 0, None, tmp_path / "p.mp4")
    assert info.value.code == "E_LIVE_NOT_READY"


@pytest.mark.parametrize(("status", "code"), [(429, "E_BOT_CHECK"), (403, "E_YT_REFUSED"), (503, "E_NETWORK")])
def test_real_http_errors_map_without_the_url(ydl: type[CaptureYDL], tmp_path: Path, status: int, code: str) -> None:
    ydl.fail = HTTPError(Response(io.BytesIO(b""), MEDIA_URL, {}, status=status))
    dest = tmp_path / "p.mp4"
    with pytest.raises(YtError) as info:
        YtDlpExtractor().fetch_frame_piece(BBB, 0, None, dest)
    assert info.value.code == code and info.value.detail == f"HTTP Error {status}"
    assert not dest.exists()


def test_real_connection_errors_are_network_errors(ydl: type[CaptureYDL], tmp_path: Path) -> None:
    ydl.fail = TransportError("connection reset by media.invalid")
    with pytest.raises(YtError) as info:
        YtDlpExtractor().fetch_frame_piece(BBB, 0, None, tmp_path / "p.mp4")
    assert info.value.code == "E_NETWORK" and info.value.detail == "TransportError"


def test_real_probe_errors_are_classified(ydl: type[CaptureYDL], tmp_path: Path) -> None:
    ydl.info = DownloadError("ERROR: [youtube] aqz-KE-bpKQ: Sign in to confirm you're not a bot")
    with pytest.raises(YtError) as info:
        YtDlpExtractor().fetch_frame_piece(BBB, 0, None, tmp_path / "p.mp4")
    assert info.value.code == "E_BOT_CHECK"


def test_real_rejects_a_bad_video_id(ydl: type[CaptureYDL], tmp_path: Path) -> None:
    with pytest.raises(YtError) as info:
        YtDlpExtractor().fetch_frame_piece("../etc", 0, None, tmp_path / "p.mp4")
    assert info.value.code == "E_INVALID_INPUT" and ydl.instances == []
```

- [ ] **Step 3: Run them, expect FAIL**

Run: `cd "$WORKTREE" && uv run pytest tests/unit/test_extractor_capture.py tests/unit/test_extractor_download.py -q -W error -p no:cacheprovider`
Expected: FAIL (`AttributeError: 'FakeExtractor' object has no attribute 'fetch_frame_piece'`); `test_extractor_download.py` already passes with the new `C14`.

- [ ] **Step 4: Implement `core/extractor.py`**

1. Imports: after `from contextlib import contextmanager` add `from dataclasses import replace`; before `from .inputs import …` add
```python
from .frame_piece import PieceInfo, fetch_piece, pick_capture_format, piece_info, read_index, write_piece
```
2. Right before `_PLAYLIST_OPTS = {` add:
```python
# ข้อเท็จจริงของชิ้นภาพจาก fixture ของตัวปลอม (testsrc 1920x1080 SDR) M5 รอบ B2
_FAKE_CAPTURE_FORMAT = {"format_id": "fake-capture", "width": 1920, "height": 1080, "dynamic_range": "SDR"}
```
3. In `YtDlpExtractor`, insert right before `def _extract(self, url: str, opts: dict, *, with_session: bool = False) -> dict:`:
```python
    def fetch_frame_piece(self, video_id: str, t_ms: int, max_short_side: int | None, dest: Path) -> PieceInfo:
        """ภาพคมตรงจุด (M5 รอบ B2 spec 3.1) โดยไม่โหลดทั้งคลิป

        1. probe ใหม่ (ค่าตั้ง probe + เซสชันผู้ชม): ข้อมูลที่เก็บไว้ไม่มีลิงก์สื่อ และลิงก์ที่ยูทูปเซ็นไว้หมดอายุได้
        2. เลือก mp4 ภาพอย่างเดียวผ่าน https (frame_piece.pick_capture_format) ไม่มี = E_CAPTURE_UNSUPPORTED
        3. โหลดหัวไฟล์ (64 KB) อ่าน sidx แล้วโหลดเฉพาะท่อนที่มี t_ms ด้วยคำขอแบบ Range ผ่านตัวส่งคำขอของ yt-dlp
           (spike 2026-10-05: --download-sections และ ffmpeg ที่ต่อลิงก์ยูทูปตรง ๆ ค้าง)
        4. เขียน init + ท่อนนั้นลง dest
        error: HTTP 429 = E_BOT_CHECK · 4xx อื่น = E_YT_REFUSED · 5xx และเน็ตหลุด = E_NETWORK
        รายละเอียดของ error และ log ไม่มีลิงก์สื่อ (มีลายเซ็น) หัวคำขอ หรือ path: log บอกแค่ id, format และจำนวนไบต์
        """
        _check_video_id(video_id)
        from yt_dlp.networking import Request
        from yt_dlp.networking.exceptions import HTTPError, RequestError
        from yt_dlp.utils import YoutubeDLError

        fetched = 0
        try:
            with self._ydl(_PROBE_OPTS, with_session=True) as ydl:
                raw = ydl.extract_info(f"https://www.youtube.com/watch?v={video_id}", download=False)
                if raw is None:
                    raise YtError("E_UNKNOWN", f"yt-dlp ไม่คืนข้อมูลสำหรับ {video_id}")
                fmt = pick_capture_format(check_live(ydl.sanitize_info(raw)), max_short_side)
                if fmt is None:
                    raise YtError("E_CAPTURE_UNSUPPORTED", f"{video_id}: no video-only mp4 over https")
                media_url = str(fmt["url"])
                headers = {str(k): str(v) for k, v in (fmt.get("http_headers") or {}).items()}

                def read_range(first: int, last: int) -> bytes:
                    nonlocal fetched
                    request = Request(media_url, headers={**headers, "Range": f"bytes={first}-{last}"})
                    with ydl.urlopen(request) as response:
                        # เซิร์ฟเวอร์ที่ไม่สน Range (ตอบ 200 ทั้งไฟล์) ก็ไม่โหลดเกินที่ขอ
                        data = response.read(last - first + 1)
                    fetched += len(data)
                    return data

                index = read_index(read_range)
                piece, ref = fetch_piece(read_range, index, t_ms)
        except YtError:
            raise
        except HTTPError as exc:
            detail = f"HTTP Error {exc.status}"
            code = classify(detail)
            raise YtError("E_NETWORK" if code == "E_UNKNOWN" else code, detail) from exc
        except RequestError as exc:
            raise YtError("E_NETWORK", type(exc).__name__) from exc
        except YoutubeDLError as exc:
            message = _ANSI.sub("", str(exc)) or type(exc).__name__
            raise YtError(classify(message), message) from exc
        except Exception as exc:
            raise YtError("E_UNKNOWN", f"{type(exc).__name__}: {exc}") from exc
        write_piece(dest, piece)
        log.info("ถ่ายภาพคม %s: format %s โหลด %d ไบต์", video_id, fmt.get("format_id"), fetched)
        return piece_info(fmt, dest, index.sidx, ref)
```
4. In `FakeExtractor`, right after the line `_FAKE_SPEED_BPS = 2_000_000  # …` add:
```python
    CAPTURE_FIXTURE = Path("capture") / "piece.mp4"  # M5 รอบ B2: ชิ้นภาพของ fetch_frame_piece
```
and insert right before `    @staticmethod\n    def _media_of(conf: dict) -> MediaFacts | None:`:
```python
    def fetch_frame_piece(self, video_id: str, t_ms: int, max_short_side: int | None, dest: Path) -> PieceInfo:
        """C6 ตัวปลอม (M5 รอบ B2): probe เหมือนตัวจริง (คลิปส่วนตัว/ไม่มี/ไลฟ์ได้ error เดียวกัน) แล้วตัดชิ้นจาก
        <fixtures_root>/capture/piece.mp4 ด้วยตัวอ่าน sidx ตัวจริง ไม่ต่อเน็ต ไม่สนเพดานความละเอียด (1920x1080 เสมอ)
        fixture ยาว 4 วินาที: เวลาของคลิปวนด้วย t_ms % ความยาว แล้วเลื่อนเวลาเริ่มท่อนกลับเป็นเวลาของคลิป
        "captureError" ของคลิปใน behaviors.json = โยน YtError รหัสนั้น (ไม่เขียนไฟล์)
        """
        self.calls.append(("fetch_frame_piece", video_id))
        self.probe(video_id)
        error = self._behavior(video_id).get("captureError")
        if error:
            raise YtError(str(error), f"fake: capture of {video_id} set to fail")
        data = (self.root / self.CAPTURE_FIXTURE).read_bytes()

        def read_range(first: int, last: int) -> bytes:
            return data[first : last + 1]

        index = read_index(read_range)
        local = t_ms % index.sidx.end_ms
        piece, ref = fetch_piece(read_range, index, local)
        write_piece(dest, piece)
        info = piece_info(_FAKE_CAPTURE_FORMAT, dest, index.sidx, ref)
        return replace(info, segment_start_ms=t_ms - (local - info.segment_start_ms))

```
5. Add to the `FakeExtractor` class docstring, after the `งานโหลด (download) …` paragraph: `ภาพคมตรงจุด (fetch_frame_piece) ตัดชิ้นจาก capture/piece.mp4 ตาม "captureError" ใน behaviors (M5 รอบ B2)`.

- [ ] **Step 5: Run the tests, expect PASS** — same command as Step 3 (17 new tests), then `cd "$WORKTREE" && uv run pytest -q -W error -p no:cacheprovider`.

- [ ] **Step 6: Commit**
```bash
cd "$WORKTREE" && git add src/yttoolkit/core/extractor.py tests/fixtures/downloads/behaviors.json tests/unit/test_extractor_download.py tests/unit/test_extractor_capture.py tests/fixtures/README.md && git commit -F- <<'EOF'
feat(extractor): M5-B2 fetch_frame_piece via sidx ranged GETs (real) and the fixture (fake)

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
EOF
```

### Task 7: Capture service (`core/capture.py`) and its real-ffmpeg integration test

**Files:**
- Create: `src/yttoolkit/core/capture.py`
- Create: `tests/helpers_capture.py`, `tests/unit/test_capture.py`, `tests/integration/test_capture_ffmpeg.py`

**Interfaces:**
- Consumes: C1 (`captureQuality`, `E_QUEUE_PAUSED`/`E_CAPTURE_BUSY` copy), C2 (`PieceInfo`, `max_short_side`, `read_index`, `fetch_piece`, `write_piece` in the test helper), C3 (`extract_frame(long_side=None)`), `files.plan_output`, `files.ensure_output_root`, `files.PATH_LIMIT`, `frames.file_timecode`, `inputs.VIDEO_ID`, Pillow.
- Produces: C7 exactly (`recorded_output` is public for the tests and `reveal_dir`).

- [ ] **Step 1: Write the test helper** — create `tests/helpers_capture.py` (imported like `helpers_ffmpeg.py`):
```python
"""ตัวช่วยเทสของการถ่ายภาพคมตรงจุด (M5 รอบ B2): ตัวดึงชิ้นภาพจาก fixture และบริการปลอมที่ CaptureService ใช้"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

from yttoolkit.core.frame_piece import PieceInfo, fetch_piece, read_index, write_piece
from yttoolkit.core.yterrors import YtError

FIXTURES = Path(__file__).resolve().parent / "fixtures"
PIECE = FIXTURES / "capture" / "piece.mp4"
MEDIA = FIXTURES / "media"
BBB = "aqz-KE-bpKQ"
TITLE = "Big Buck Bunny"


class FixtureFetcher:
    """fetch_frame_piece จาก piece.mp4 ด้วยตัวอ่าน sidx ตัวจริง (เวลาวนทุก 4 วินาทีแบบ FakeExtractor)
    error = โยนแทน · gate = รอจนถูก set (เทสการถ่ายซ้อน) · calls = (video_id, t_ms, max_short_side)"""

    def __init__(self) -> None:
        self.calls: list[tuple[str, int, int | None]] = []
        self.error: YtError | None = None
        self.gate: threading.Event | None = None
        self.started = threading.Event()

    def fetch_frame_piece(self, video_id: str, t_ms: int, max_short_side: int | None, dest: Path) -> PieceInfo:
        self.calls.append((video_id, t_ms, max_short_side))
        self.started.set()
        if self.gate is not None:
            assert self.gate.wait(10)
        if self.error is not None:
            raise self.error
        data = PIECE.read_bytes()

        def read_range(first: int, last: int) -> bytes:
            return data[first : last + 1]

        index = read_index(read_range)
        local = t_ms % index.sidx.end_ms
        piece, ref = fetch_piece(read_range, index, local)
        write_piece(dest, piece)
        return PieceInfo(dest, t_ms - (local - index.sidx.to_ms(ref.start)), 1920, 1080, "fixture", None)


def clip_info(duration_s: int = 635, title: str = TITLE, live: bool = False) -> dict:
    return {"videoId": BBB, "title": title, "durationS": duration_s, "isLive": live}


class FakeVideos:
    """VideoService.get / peek_cached จาก dict (ไม่มีคลิป = E_VIDEO_UNAVAILABLE)"""

    def __init__(self, infos: dict[str, dict]) -> None:
        self.infos = infos

    def get(self, video_id: str, refresh: bool = False, peek: bool = False) -> dict:
        if video_id not in self.infos:
            raise YtError("E_VIDEO_UNAVAILABLE", video_id)
        return dict(self.infos[video_id])

    def peek_cached(self, video_id: str) -> dict | None:
        info = self.infos.get(video_id)
        return dict(info) if info is not None else None


@dataclass
class StubSettings:
    output: Path
    quality: str = "max"

    def get(self) -> dict:
        return {"captureQuality": self.quality}

    def output_dir(self) -> Path:
        return self.output


@dataclass
class StubQueue:
    paused_until: datetime | None = None
    brakes: list[str] = field(default_factory=list)

    def pause_state(self) -> SimpleNamespace | None:
        return None if self.paused_until is None else SimpleNamespace(until=self.paused_until, reason="E_BOT_CHECK")

    def brake(self, reason: str = "E_BOT_CHECK") -> None:
        self.brakes.append(reason)
```

- [ ] **Step 2: Write the failing tests** — create `tests/unit/test_capture.py`:
```python
"""บริการถ่ายภาพคมตรงจุด (M5 รอบ B2 C7): ไม่ใช้เน็ต ไม่ใช้ ffmpeg (ชิ้นภาพจาก fixture + FakeMediaTools)"""

from __future__ import annotations

import errno
import json
import shutil
import threading
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import pytest
from helpers_capture import BBB, MEDIA, TITLE, FakeVideos, FixtureFetcher, StubQueue, StubSettings, clip_info
from PIL import Image

from yttoolkit.core.capture import OUTPUT_DIR, Capture, CaptureRejected, CaptureService, recorded_output
from yttoolkit.core.media import FakeMediaTools, FrameCall
from yttoolkit.core.yterrors import YtError

COVER = MEDIA / "cover.jpg"
with Image.open(COVER) as _img:
    COVER_SIZE = _img.size


@dataclass
class Env:
    service: CaptureService
    fetcher: FixtureFetcher
    media: FakeMediaTools
    settings: StubSettings
    queue: StubQueue
    videos: FakeVideos
    cache: Path
    work: Path
    out: Path

    @property
    def captures(self) -> Path:
        return self.cache / BBB / "captures"

    @property
    def folder(self) -> Path:
        return self.out / f"{TITLE} [{BBB}]" / OUTPUT_DIR

    def index(self) -> list[dict]:
        return json.loads((self.captures / "index.json").read_text(encoding="utf-8"))["captures"]


@pytest.fixture
def env(tmp_path: Path) -> Env:
    fetcher, media, queue = FixtureFetcher(), FakeMediaTools(MEDIA), StubQueue()
    settings, videos = StubSettings(tmp_path / "out"), FakeVideos({BBB: clip_info()})
    service = CaptureService(videos, fetcher, media, tmp_path / "cache", settings, queue, work_root=tmp_path / "work",
                             now=lambda: datetime(2026, 10, 5, 8, 0, tzinfo=UTC))  # fmt: skip
    return Env(service, fetcher, media, settings, queue, videos, tmp_path / "cache", tmp_path / "work", tmp_path / "out")


def _work_is_clean(env: Env) -> bool:
    return not env.work.exists() or list(env.work.iterdir()) == []


def test_capture_writes_the_cache_copy_the_folder_copy_then_the_index(env: Env) -> None:
    capture, created = env.service.capture(BBB, 125_400)
    assert created is True
    assert capture == Capture("c_125400", 125_400, COVER_SIZE[0], COVER_SIZE[1], "c_125400.jpg")
    cached = env.captures / "c_125400.jpg"
    assert cached.read_bytes() == COVER.read_bytes() == (env.folder / "frame_00-02-05.jpg").read_bytes()
    assert env.service.cache_path(BBB, capture) == cached
    assert env.index() == [{
        "id": "c_125400", "tMs": 125_400, "width": COVER_SIZE[0], "height": COVER_SIZE[1], "file": "c_125400.jpg",
        "outputRoot": str(env.out), "outputRel": f"{TITLE} [{BBB}]/ภาพที่ถ่าย/frame_00-02-05.jpg",
        "createdAt": "2026-10-05T08:00:00+00:00",
    }]  # fmt: skip
    assert env.fetcher.calls == [(BBB, 125_400, None)]
    # ชิ้นที่ได้เริ่มที่ 125.0 วินาที: ดึงภาพที่ 0.4 วินาทีของชิ้น ไม่ย่อ (long_side None) SDR
    assert env.media.frames == [FrameCall("piece.mp4", "frame.jpg", 400, None, None)]
    assert _work_is_clean(env)


def test_the_same_moment_is_returned_without_fetching(env: Env) -> None:
    first, _ = env.service.capture(BBB, 2_000)
    env.queue.paused_until = datetime(2099, 1, 1, tzinfo=UTC)  # ภาพเดิมไม่ต้องใช้เน็ต: คิวพักก็ได้ภาพเดิม
    again, created = env.service.capture(BBB, 2_000)
    assert again == first and created is False
    assert len(env.fetcher.calls) == 1 and len(env.index()) == 1


def test_second_capture_while_one_runs_is_busy(env: Env) -> None:
    env.fetcher.gate = threading.Event()
    results: dict[str, tuple[Capture, bool]] = {}
    worker = threading.Thread(target=lambda: results.setdefault("first", env.service.capture(BBB, 1_000)))
    worker.start()
    assert env.fetcher.started.wait(5)
    with pytest.raises(YtError) as busy:
        env.service.capture(BBB, 2_000)
    assert busy.value.code == "E_CAPTURE_BUSY"
    env.fetcher.gate.set()
    worker.join(10)
    assert results["first"][1] is True
    assert [call[1] for call in env.fetcher.calls] == [1_000]
    assert env.service.capture(BBB, 2_000)[1] is True  # ปลดล็อกแล้วถ่ายต่อได้


def test_paused_queue_refuses_with_the_bangkok_time(env: Env) -> None:
    env.queue.paused_until = datetime(2026, 10, 5, 10, 10, tzinfo=UTC)
    with pytest.raises(YtError) as info:
        env.service.capture(BBB, 1_000)
    assert info.value.code == "E_QUEUE_PAUSED"
    assert info.value.message == "พักการโหลดอยู่เพราะยูทูปขอตรวจสอบ ลองใหม่หลัง 17:10"
    assert env.fetcher.calls == []


@pytest.mark.parametrize(
    ("info", "t_ms"),
    [
        (clip_info(live=True), 1_000),
        (clip_info(duration_s=0), 1_000),
        (clip_info(duration_s=10), -1),
        (clip_info(duration_s=10), 10_000),
        (clip_info(duration_s=10), True),
        (clip_info(duration_s=10), "1000"),
    ],
)
def test_requests_the_clip_cannot_serve_are_rejected(env: Env, info: dict, t_ms: object) -> None:
    env.videos.infos[BBB] = info
    with pytest.raises(CaptureRejected):
        env.service.capture(BBB, t_ms)  # type: ignore[arg-type]
    assert env.fetcher.calls == []


def test_a_bad_video_id_is_invalid_input(env: Env) -> None:
    with pytest.raises(YtError) as info:
        env.service.capture("../x", 0)
    assert info.value.code == "E_INVALID_INPUT"


def test_two_captures_in_one_second_get_numbered_names(env: Env) -> None:
    env.service.capture(BBB, 125_400)
    env.service.capture(BBB, 125_800)
    assert sorted(p.name for p in env.folder.iterdir()) == ["frame_00-02-05.jpg", "frame_00-02-05_2.jpg"]
    assert [e["outputRel"].rsplit("/", 1)[1] for e in env.index()] == ["frame_00-02-05.jpg", "frame_00-02-05_2.jpg"]


def test_output_failure_rolls_back_the_cache_copy(env: Env, tmp_path: Path) -> None:
    blocked = tmp_path / "blocked"
    blocked.write_bytes(b"not a folder")
    env.settings.output = blocked
    with pytest.raises(YtError) as info:
        env.service.capture(BBB, 1_000)
    assert info.value.code == "E_OUTPUT_NOT_WRITABLE"
    assert not (env.captures / "c_1000.jpg").exists()
    assert not (env.captures / "index.json").exists()
    assert env.service.list(BBB) == [] and _work_is_clean(env)


def test_index_failure_rolls_back_both_copies(env: Env, monkeypatch: pytest.MonkeyPatch) -> None:
    def full(*_args: object) -> None:
        raise OSError(errno.ENOSPC, "No space left on device")

    monkeypatch.setattr(env.service, "_write_entries", full)
    with pytest.raises(YtError) as info:
        env.service.capture(BBB, 1_000)
    assert info.value.code == "E_DISK_FULL"
    assert not (env.captures / "c_1000.jpg").exists()
    assert not env.folder.exists() or list(env.folder.iterdir()) == []


def test_temp_dir_is_removed_on_every_path(env: Env) -> None:
    env.fetcher.error = YtError("E_NETWORK", "reset")
    with pytest.raises(YtError):
        env.service.capture(BBB, 1_000)
    assert _work_is_clean(env)
    env.fetcher.error = None
    env.service.capture(BBB, 1_000)
    assert _work_is_clean(env)


def test_bot_check_brakes_the_queue(env: Env) -> None:
    env.fetcher.error = YtError("E_BOT_CHECK", "429")
    with pytest.raises(YtError) as info:
        env.service.capture(BBB, 1_000)
    assert info.value.code == "E_BOT_CHECK" and env.queue.brakes == ["E_BOT_CHECK"]
    env.fetcher.error = YtError("E_NETWORK", "reset")
    with pytest.raises(YtError):
        env.service.capture(BBB, 1_000)
    assert env.queue.brakes == ["E_BOT_CHECK"]


def test_no_frame_retries_100_ms_earlier_then_fails(env: Env) -> None:
    env.media.frame_limit_ms = 350  # ที่ 0.4 วินาทีของชิ้นไม่มีภาพ ถอยไป 0.3 ได้ภาพ
    assert env.service.capture(BBB, 125_400)[1] is True
    assert [call.t_ms for call in env.media.frames] == [400, 300]
    env.media.frames.clear()
    env.media.frame_limit_ms = 0
    with pytest.raises(YtError) as info:
        env.service.capture(BBB, 125_500)
    assert info.value.code == "E_UNKNOWN"
    assert [call.t_ms for call in env.media.frames] == [500, 400]
    env.media.frames.clear()
    with pytest.raises(YtError):
        env.service.capture(BBB, 125_000)  # ต้นชิ้นพอดี: ไม่มีที่ให้ถอย
    assert [call.t_ms for call in env.media.frames] == [0]
    assert env.service.list(BBB) == [Capture("c_125400", 125_400, *COVER_SIZE, "c_125400.jpg")]


@pytest.mark.parametrize(("quality", "cap"), [("max", None), ("1080", 1080), ("720", 720)])
def test_the_setting_sets_the_short_side_cap(env: Env, quality: str, cap: int | None) -> None:
    env.settings.quality = quality
    env.service.capture(BBB, 1_000)
    assert env.fetcher.calls == [(BBB, 1_000, cap)]


def test_missing_ffmpeg_fails_before_any_fetch(env: Env, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(env.media, "available", lambda: False)
    with pytest.raises(YtError) as info:
        env.service.capture(BBB, 1_000)
    assert info.value.code == "E_FFMPEG_MISSING" and env.fetcher.calls == []


def test_list_is_sorted_and_drops_entries_without_a_cache_file(env: Env) -> None:
    for t_ms in (3_000, 1_000, 2_000):
        env.service.capture(BBB, t_ms)
    assert [c.t_ms for c in env.service.list(BBB)] == [1_000, 2_000, 3_000]
    (env.captures / "c_2000.jpg").unlink()
    assert [c.t_ms for c in env.service.list(BBB)] == [1_000, 3_000]
    assert [e["tMs"] for e in env.index()] == [1_000, 3_000]
    assert env.service.list("bad id") == []


def test_delete_removes_the_folder_copy_the_cache_copy_and_the_entry(env: Env) -> None:
    capture, _ = env.service.capture(BBB, 125_400)
    env.service.delete(BBB, capture.id)
    assert not (env.folder / "frame_00-02-05.jpg").exists()
    assert not (env.captures / "c_125400.jpg").exists()
    assert env.service.list(BBB) == []
    for video_id, capture_id in ((BBB, capture.id), (BBB, "c_x"), (BBB, "../c_1"), ("bad", "c_1")):
        with pytest.raises(KeyError):
            env.service.delete(video_id, capture_id)


def test_delete_with_the_folder_copy_already_gone(env: Env) -> None:
    capture, _ = env.service.capture(BBB, 1_000)
    (env.folder / "frame_00-00-01.jpg").unlink()
    env.service.delete(BBB, capture.id)
    assert env.service.list(BBB) == []


def _edit_entry(env: Env, **patch: str) -> None:
    entries = env.index()
    entries[0].update(patch)
    (env.captures / "index.json").write_text(json.dumps({"captures": entries}, ensure_ascii=False), encoding="utf-8")


def test_delete_skips_a_path_outside_the_recorded_root(env: Env, tmp_path: Path) -> None:
    capture, _ = env.service.capture(BBB, 1_000)
    decoy = tmp_path / "decoy" / OUTPUT_DIR / "frame_00-00-01.jpg"
    decoy.parent.mkdir(parents=True)
    decoy.write_bytes(b"keep me")
    _edit_entry(env, outputRel=f"../decoy/{OUTPUT_DIR}/frame_00-00-01.jpg")
    env.service.delete(BBB, capture.id)
    assert decoy.read_bytes() == b"keep me"
    assert (env.folder / "frame_00-00-01.jpg").exists()  # ไม่ใช่ไฟล์ที่บันทึกไว้ (index ถูกแก้) จึงไม่แตะ
    assert env.service.list(BBB) == []


def test_delete_skips_a_renamed_file(env: Env) -> None:
    capture, _ = env.service.capture(BBB, 1_000)
    renamed = env.folder / "frame_00-00-01 ของฉัน.jpg"
    (env.folder / "frame_00-00-01.jpg").rename(renamed)
    env.service.delete(BBB, capture.id)
    assert renamed.exists() and env.service.list(BBB) == []


def _link_dir(link: Path, target: Path) -> None:
    try:
        link.symlink_to(target, target_is_directory=True)
    except OSError:
        try:
            import _winapi  # Windows: junction ไม่ต้องใช้สิทธิ์ผู้ดูแล

            _winapi.CreateJunction(str(target), str(link))
        except (ImportError, OSError, AttributeError):
            pytest.skip("this machine cannot create a directory link")


def test_delete_never_follows_a_linked_folder(env: Env, tmp_path: Path) -> None:
    capture, _ = env.service.capture(BBB, 1_000)
    elsewhere = tmp_path / "elsewhere"
    shutil.move(str(env.folder), str(elsewhere))
    _link_dir(env.folder, elsewhere)
    env.service.delete(BBB, capture.id)
    assert (elsewhere / "frame_00-00-01.jpg").exists()
    assert env.service.list(BBB) == []


def test_delete_uses_the_recorded_root_after_the_setting_changes(env: Env, tmp_path: Path) -> None:
    capture, _ = env.service.capture(BBB, 1_000)
    env.settings.output = tmp_path / "another-output"
    env.service.delete(BBB, capture.id)
    assert not (env.folder / "frame_00-00-01.jpg").exists()


def test_delete_with_a_locked_folder_copy_changes_nothing(env: Env, monkeypatch: pytest.MonkeyPatch) -> None:
    capture, _ = env.service.capture(BBB, 1_000)
    real_unlink = Path.unlink

    def locked(self: Path, missing_ok: bool = False) -> None:
        if self.name == "frame_00-00-01.jpg":
            raise PermissionError(13, "used by another process")
        real_unlink(self, missing_ok=missing_ok)

    monkeypatch.setattr(Path, "unlink", locked)
    with pytest.raises(YtError) as info:
        env.service.delete(BBB, capture.id)
    assert info.value.code == "E_OUTPUT_NOT_WRITABLE"
    monkeypatch.undo()
    assert env.service.list(BBB) == [capture]
    assert (env.captures / "c_1000.jpg").exists()


def test_reveal_dir_prefers_the_recorded_folder_then_the_planned_one(env: Env) -> None:
    assert env.service.reveal_dir(BBB) is None
    env.service.capture(BBB, 1_000)
    assert env.service.reveal_dir(BBB) == env.folder
    (env.folder / "frame_00-00-01.jpg").unlink()
    assert env.service.reveal_dir(BBB) == env.folder  # โฟลเดอร์ตามค่าตั้งปัจจุบันยังอยู่
    env.folder.rmdir()
    assert env.service.reveal_dir(BBB) is None
    assert env.service.reveal_dir("bad id") is None


@pytest.mark.parametrize(
    ("root", "rel"),
    [
        ("\\\\server\\share", f"a/{OUTPUT_DIR}/frame_00-00-01.jpg"),
        ("relative/root", f"a/{OUTPUT_DIR}/frame_00-00-01.jpg"),
        (None, f"a\\{OUTPUT_DIR}\\frame_00-00-01.jpg"),
        (None, f"C:/a/{OUTPUT_DIR}/frame_00-00-01.jpg"),
        (None, f"a/อื่น/frame_00-00-01.jpg"),
        (None, f"a/{OUTPUT_DIR}/notes.txt"),
        (None, f"{OUTPUT_DIR}/frame_00-00-01.jpg"),
    ],
)
def test_recorded_output_refuses_odd_paths(tmp_path: Path, root: str | None, rel: str) -> None:
    assert recorded_output(str(tmp_path) if root is None else root, rel) is None
```
and `tests/integration/test_capture_ffmpeg.py`:
```python
"""ถ่ายภาพคมตรงจุดกับ ffmpeg จริง (M5 รอบ B2 spec 6): ชิ้นจาก sidx ตัวจริง ภาพต้องตรงกับภาพจากไฟล์เต็มที่เวลาเดียวกัน
และได้ความละเอียดต้นฉบับ (1920×1080 ไม่ย่อ) · ไม่ต่อเน็ต"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
from helpers_capture import BBB, PIECE, FakeVideos, FixtureFetcher, StubQueue, StubSettings, clip_info
from helpers_ffmpeg import find_test_ffmpeg, requires_ffmpeg
from PIL import Image

from yttoolkit.core.capture import CaptureService
from yttoolkit.core.media import FfmpegTools

pytestmark = requires_ffmpeg


def _ffmpeg() -> str:
    found = find_test_ffmpeg()
    assert found is not None
    return found


def _service(tmp_path: Path) -> CaptureService:
    return CaptureService(FakeVideos({BBB: clip_info(duration_s=4)}), FixtureFetcher(), FfmpegTools(lambda: Path(_ffmpeg())),
                          tmp_path / "cache", StubSettings(tmp_path / "out"), StubQueue(), work_root=tmp_path / "work")  # fmt: skip


def _reference(at_s: float, folder: Path) -> Path:
    """ภาพจากไฟล์เต็ม (ไม่ผ่านการตัดชิ้น) ที่เวลาเดียวกัน คำสั่งแบบเดียวกับตัวทำงาน"""
    out = folder / f"ref-{at_s:.3f}.jpg"
    subprocess.run([_ffmpeg(), "-hide_banner", "-loglevel", "error", "-y", "-ss", f"{at_s:.3f}", "-i", str(PIECE),
                    "-frames:v", "1", "-q:v", "2", str(out)], check=True)  # fmt: skip
    return out


def _gray(path: Path) -> bytes:
    with Image.open(path) as img:
        return img.convert("L").resize((480, 270)).tobytes()


def _diff(a: bytes, b: bytes) -> float:
    return sum(abs(x - y) for x, y in zip(a, b, strict=True)) / len(a)


@pytest.mark.parametrize("t_ms", [0, 1_000, 2_550, 3_500])
def test_piece_frame_equals_the_full_file_frame(tmp_path: Path, t_ms: int) -> None:
    service = _service(tmp_path)
    capture, created = service.capture(BBB, t_ms)
    assert created and (capture.width, capture.height) == (1920, 1080)
    here = _gray(service.cache_path(BBB, capture))
    same = _gray(_reference(t_ms / 1000, tmp_path))
    other = _gray(_reference(((t_ms + 1_500) % 4_000) / 1000, tmp_path))
    assert _diff(here, same) < 0.5 < _diff(here, other)


def test_last_fraction_retries_and_still_gets_a_frame(tmp_path: Path) -> None:
    service = _service(tmp_path)
    capture, _ = service.capture(BBB, 3_950)  # ภาพสุดท้ายอยู่ที่ 3.9 วินาที: 3.95 ไม่มีภาพ ถอยไป 3.85 แล้วได้ภาพ 3.9
    assert _diff(_gray(service.cache_path(BBB, capture)), _gray(_reference(3.85, tmp_path))) < 0.5
```

- [ ] **Step 3: Run them, expect FAIL**

Run: `cd "$WORKTREE" && uv run pytest tests/unit/test_capture.py tests/integration/test_capture_ffmpeg.py -q -W error -p no:cacheprovider`
Expected: FAIL (`ModuleNotFoundError: No module named 'yttoolkit.core.capture'`).

- [ ] **Step 4: Implement** — create `src/yttoolkit/core/capture.py`:
```python
"""ถ่ายภาพคมตรงจุดที่ตัวเล่นอยู่ (M5 รอบ B2 spec 3.2): ไม่ผ่านคิว ถ่ายได้ครั้งละภาพทั้งแอพ

ไฟล์ของคลิปหนึ่ง:
- cache ของแอพ: <cache>/<id>/captures/c_<tMs>.jpg และ captures/index.json = {"captures": [entry, ...]}
  entry = {"id", "tMs", "width", "height", "file", "outputRoot", "outputRel", "createdAt"}
- โฟลเดอร์ผลลัพธ์: <output>/<โฟลเดอร์ของคลิป>/ภาพที่ถ่าย/frame_HH-MM-SS.jpg (วินาทีเดียวกัน _2, _3 ...)
ลำดับการเขียน: ไฟล์ใน cache → ไฟล์ในโฟลเดอร์ → แถวใน index (แถวมาหลังสุด: ไม่มีแถวไหนชี้ไฟล์ที่ยังไม่มี)
ไฟล์ชั่วคราวอยู่ใน work/capture-<uuid>/ ลบทุกครั้งที่จบ (ดับกลางทาง = ตัวกวาด work/ ตอนเปิดโปรแกรมลบให้)
log บอกแค่ id คลิป รหัส error และชนิด error (ไม่มี path ลิงก์ หรือ outputRoot) · core ไม่ import api/platform
"""

from __future__ import annotations

import errno
import json
import logging
import os
import re
import shutil
import threading
import uuid
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path, PurePosixPath
from typing import Any, Protocol

from PIL import Image, UnidentifiedImageError

from .files import PATH_LIMIT, ensure_output_root, plan_output
from .frame_piece import PieceInfo, max_short_side
from .frames import file_timecode
from .inputs import VIDEO_ID
from .yterrors import YtError

log = logging.getLogger("yttoolkit")

CAPTURE_FOLDER = "captures"
CAPTURE_INDEX = "index.json"
OUTPUT_DIR = "ภาพที่ถ่าย"
CAPTURE_ID = re.compile(r"c_(\d{1,9})")
NO_FRAME_RETRY_MS = 100  # spec 4: เวลาเศษท้ายคลิปที่ไม่มีภาพ ลองถอยหลัง 100 ms อีกครั้งเดียว
MAX_SAME_SECOND = 99
_OUTPUT_NAME = re.compile(r"frame_\d{2,}-\d{2}-\d{2}(?:_\d{1,2})?\.jpg")
_LONGEST_NAME = "frame_000-00-00_99.jpg"
_BANGKOK = timezone(timedelta(hours=7))


class PieceFetcher(Protocol):
    def fetch_frame_piece(self, video_id: str, t_ms: int, max_short_side: int | None, dest: Path) -> PieceInfo: ...


class VideoLookup(Protocol):
    def get(self, video_id: str, refresh: bool = False, peek: bool = False) -> dict: ...
    def peek_cached(self, video_id: str) -> dict | None: ...


class FrameExtractor(Protocol):
    def available(self) -> bool: ...
    def extract_frame(self, src: Path, dst: Path, t_ms: int, *, long_side: int | None, dynamic_range: str | None,
                      cancel: Callable[[], bool]) -> bool: ...  # fmt: skip


class CaptureSettings(Protocol):
    def get(self) -> dict: ...
    def output_dir(self) -> Path: ...


class QueueBrake(Protocol):
    def pause_state(self) -> Any: ...  # PauseState(until, reason) | None
    def brake(self, reason: str = "E_BOT_CHECK") -> None: ...


class CaptureRejected(Exception):
    """คำขอที่ถ่ายไม่ได้เพราะตัวคำขอเอง (คลิปสด ไม่รู้ความยาว เวลานอกคลิป) API ตอบ 422 E_BAD_REQUEST"""

    def __init__(self, detail: str) -> None:
        super().__init__(detail)
        self.detail = detail


@dataclass(frozen=True)
class Capture:
    id: str
    t_ms: int
    width: int
    height: int
    file: str


def _never() -> bool:
    return False


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _u16(text: str) -> int:
    return len(text.encode("utf-16-le", errors="surrogatepass")) // 2


def _clock(moment: datetime) -> str:
    """เวลาแบบนาฬิกา HH:MM ของประเทศไทย (ข้อความ "ลองใหม่หลัง {time}")"""
    return moment.astimezone(_BANGKOK).strftime("%H:%M")


def _write_error(err: OSError) -> YtError:
    return YtError("E_DISK_FULL" if err.errno == errno.ENOSPC else "E_OUTPUT_NOT_WRITABLE", type(err).__name__)


def _entry_ok(entry: object) -> bool:
    if not isinstance(entry, dict):
        return False
    match = CAPTURE_ID.fullmatch(str(entry.get("id")))
    t_ms = entry.get("tMs")
    return (
        match is not None
        and type(t_ms) is int
        and int(match.group(1)) == t_ms
        and entry.get("file") == f"c_{t_ms}.jpg"
        and all(type(entry.get(k)) is int and entry[k] > 0 for k in ("width", "height"))
        and all(isinstance(entry.get(k), str) for k in ("outputRoot", "outputRel", "createdAt"))
    )


def _to_capture(entry: Mapping[str, Any]) -> Capture:
    return Capture(str(entry["id"]), int(entry["tMs"]), int(entry["width"]), int(entry["height"]), str(entry["file"]))


def _is_link(path: Path) -> bool:
    try:
        return path.is_symlink() or path.is_junction()
    except OSError:
        return True


def _exact_name(folder: Path, name: str) -> bool:
    try:
        with os.scandir(folder) as entries:
            return any(entry.name == name for entry in entries)
    except OSError:
        return False


def recorded_output(root_text: str, rel: str) -> Path | None:
    """ไฟล์ในโฟลเดอร์ผลลัพธ์ตามที่บันทึกไว้ ถ้ายังเป็นไฟล์เดิมจริง: อยู่ใต้ root ที่บันทึก ชื่อตรงเป๊ะ ไม่ผ่านลิงก์ใด ๆ
    ไม่ผ่านเกณฑ์หรือไม่มีไฟล์แล้ว = None (ห้ามลบ/เปิดอย่างอื่น)"""
    if not root_text or root_text.startswith(("\\\\", "//")) or "\x00" in rel or "\\" in rel or ":" in rel:
        return None
    root = Path(root_text)
    parts = PurePosixPath(rel).parts
    if not root.is_absolute() or PurePosixPath(rel).is_absolute() or any(p in ("", ".", "..") for p in parts):
        return None
    if len(parts) < 3 or parts[-2] != OUTPUT_DIR or not _OUTPUT_NAME.fullmatch(parts[-1]):
        return None
    current = root
    for part in parts:
        current = current / part
        if _is_link(current):
            return None
    try:
        real_root = root.resolve(strict=True)
        real = current.resolve(strict=True)
    except (OSError, RuntimeError):
        return None
    if not real.is_relative_to(real_root) or not current.is_file() or not _exact_name(current.parent, parts[-1]):
        return None
    return current


class CaptureService:
    """C7: ถ่าย (capture) ดูรายการ (list) ลบ (delete) และหาโฟลเดอร์ที่ต้องเปิด (reveal_dir)"""

    def __init__(
        self,
        videos: VideoLookup,
        extractor: PieceFetcher,
        media: FrameExtractor,
        cache_root: Path,
        settings: CaptureSettings,
        queue: QueueBrake,
        *,
        work_root: Path,
        now: Callable[[], datetime] = _utcnow,
    ) -> None:
        self._videos = videos
        self._extractor = extractor
        self._media = media
        self._cache_root = Path(cache_root)
        self._settings = settings
        self._queue = queue
        self._work_root = Path(work_root)
        self._now = now
        self._busy = threading.Lock()  # ถ่ายได้ครั้งละภาพทั้งแอพ (ไม่รอ: ถือไว้อยู่ = E_CAPTURE_BUSY)
        self._guard = threading.Lock()
        self._clip_locks: dict[str, threading.Lock] = {}

    # ---------- ที่เก็บ ----------

    def _clip_lock(self, video_id: str) -> threading.Lock:
        with self._guard:
            return self._clip_locks.setdefault(video_id, threading.Lock())

    def _folder(self, video_id: str) -> Path:
        return self._cache_root / video_id / CAPTURE_FOLDER

    def cache_path(self, video_id: str, capture: Capture) -> Path:
        return self._folder(video_id) / capture.file

    def _read_entries(self, video_id: str) -> list[dict]:
        try:
            data = json.loads((self._folder(video_id) / CAPTURE_INDEX).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return []
        items = data.get("captures") if isinstance(data, dict) else None
        return [entry for entry in items if _entry_ok(entry)] if isinstance(items, list) else []

    def _write_entries(self, video_id: str, entries: list[dict]) -> None:
        folder = self._folder(video_id)
        folder.mkdir(parents=True, exist_ok=True)
        tmp = folder / f".{CAPTURE_INDEX}.{uuid.uuid4().hex}.tmp"
        try:
            tmp.write_text(json.dumps({"captures": sorted(entries, key=lambda e: e["tMs"])}, ensure_ascii=False),
                           encoding="utf-8")  # fmt: skip
            os.replace(tmp, folder / CAPTURE_INDEX)
        finally:
            tmp.unlink(missing_ok=True)

    def _existing(self, video_id: str, t_ms: int) -> Capture | None:
        with self._clip_lock(video_id):
            for entry in self._read_entries(video_id):
                if entry["tMs"] == t_ms and (self._folder(video_id) / entry["file"]).is_file():
                    return _to_capture(entry)
        return None

    # ---------- ถ่ายภาพ ----------

    def capture(self, video_id: str, t_ms: int) -> tuple[Capture, bool]:
        """ถ่ายภาพที่เวลา t_ms คืน (ภาพ, ถ่ายใหม่ไหม) · เวลาเดิมที่ถ่ายไว้แล้ว = คืนภาพเดิมโดยไม่โหลดอะไร"""
        if not VIDEO_ID.fullmatch(video_id):
            raise YtError("E_INVALID_INPUT", f"video id ไม่ถูกรูปแบบ: {video_id!r}")
        if isinstance(t_ms, bool) or not isinstance(t_ms, int):
            raise CaptureRejected("tMs must be an integer")
        info = self._videos.get(video_id, peek=True)
        duration_ms = int(info.get("durationS") or 0) * 1000
        if info.get("isLive"):
            raise CaptureRejected("live clip")
        if duration_ms <= 0:
            raise CaptureRejected("duration unknown")
        if not 0 <= t_ms < duration_ms:
            raise CaptureRejected(f"tMs {t_ms} outside 0..{duration_ms}")
        existing = self._existing(video_id, t_ms)
        if existing is not None:
            return existing, False
        pause = self._queue.pause_state()
        if pause is not None:
            raise YtError("E_QUEUE_PAUSED", "queue paused by a bot check", params={"time": _clock(pause.until)})
        if not self._media.available():
            raise YtError("E_FFMPEG_MISSING")
        if not self._busy.acquire(blocking=False):
            raise YtError("E_CAPTURE_BUSY", "another capture is running")
        try:
            existing = self._existing(video_id, t_ms)
            if existing is not None:
                return existing, False
            return self._capture_locked(video_id, str(info.get("title") or ""), t_ms), True
        except YtError as exc:
            if exc.code == "E_BOT_CHECK":
                self._queue.brake("E_BOT_CHECK")
            log.warning("ถ่ายภาพคม %s ไม่สำเร็จ (%s)", video_id, exc.code)
            raise
        finally:
            self._busy.release()

    def _capture_locked(self, video_id: str, title: str, t_ms: int) -> Capture:
        tmp = self._work_root / f"capture-{uuid.uuid4().hex}"
        try:
            tmp.mkdir(parents=True)
            try:
                cap = max_short_side(str(self._settings.get().get("captureQuality", "max")))
            except ValueError:
                cap = None  # ค่าตั้งเสีย (ไม่ควรเกิด SettingsStore ตรวจแล้ว) = สูงสุดที่มี
            piece = self._extractor.fetch_frame_piece(video_id, t_ms, cap, tmp / "piece.mp4")
            frame = tmp / "frame.jpg"
            offset = max(0, t_ms - piece.segment_start_ms)
            if not self._extract(piece, frame, offset):
                if offset == 0 or not self._extract(piece, frame, max(0, offset - NO_FRAME_RETRY_MS)):
                    raise YtError("E_UNKNOWN", "no frame at this time")
            width, height = _jpeg_size(frame)
            return self._store(video_id, title, t_ms, frame, width, height)
        finally:
            shutil.rmtree(tmp, ignore_errors=True)

    def _extract(self, piece: PieceInfo, frame: Path, offset_ms: int) -> bool:
        return self._media.extract_frame(piece.path, frame, offset_ms, long_side=None,
                                         dynamic_range=piece.dynamic_range, cancel=_never)  # fmt: skip

    def _store(self, video_id: str, title: str, t_ms: int, frame: Path, width: int, height: int) -> Capture:
        capture = Capture(f"c_{t_ms}", t_ms, width, height, f"c_{t_ms}.jpg")
        folder = self._folder(video_id)
        cached = folder / capture.file
        try:
            folder.mkdir(parents=True, exist_ok=True)
            part = folder / f".{capture.file}.{uuid.uuid4().hex}.part"
            try:
                shutil.copyfile(frame, part)
                os.replace(part, cached)
            finally:
                part.unlink(missing_ok=True)
        except OSError as err:
            raise YtError("E_DISK_FULL" if err.errno == errno.ENOSPC else "E_UNKNOWN", type(err).__name__) from err
        output: Path | None = None
        try:
            root = self._settings.output_dir()
            output = self._write_output(root, title, video_id, t_ms, frame)
            entry = {
                "id": capture.id, "tMs": t_ms, "width": width, "height": height, "file": capture.file,
                "outputRoot": str(root), "outputRel": output.relative_to(root).as_posix(),
                "createdAt": self._now().astimezone(UTC).isoformat(timespec="seconds"),
            }  # fmt: skip
            with self._clip_lock(video_id):
                entries = [e for e in self._read_entries(video_id) if e["id"] != capture.id]
                try:
                    self._write_entries(video_id, [*entries, entry])
                except OSError as err:
                    raise YtError("E_DISK_FULL" if err.errno == errno.ENOSPC else "E_UNKNOWN", type(err).__name__) from err
        except BaseException:
            cached.unlink(missing_ok=True)
            if output is not None:
                output.unlink(missing_ok=True)
            raise
        return capture

    def _write_output(self, root: Path, title: str, video_id: str, t_ms: int, frame: Path) -> Path:
        """สำเนาในโฟลเดอร์ของคลิป: <clip folder>/ภาพที่ถ่าย/frame_HH-MM-SS.jpg (ชื่อซ้ำ _2 ... _99) จองชื่อแบบ exclusive"""
        ensure_output_root(root)
        folder = plan_output(root, title, video_id, "", "jpg").parent / OUTPUT_DIR
        if _u16(str(folder / _LONGEST_NAME)) > PATH_LIMIT:
            raise YtError("E_OUTPUT_NOT_WRITABLE", "path too long")
        stem = f"frame_{file_timecode(t_ms)}"
        try:
            folder.mkdir(parents=True, exist_ok=True)
            for n in range(1, MAX_SAME_SECOND + 1):
                target = folder / (f"{stem}.jpg" if n == 1 else f"{stem}_{n}.jpg")
                try:
                    handle = target.open("xb")
                except FileExistsError:
                    continue
                try:
                    with handle, frame.open("rb") as source:
                        shutil.copyfileobj(source, handle)
                except BaseException:
                    target.unlink(missing_ok=True)
                    raise
                return target
        except OSError as err:
            raise _write_error(err) from err
        raise YtError("E_OUTPUT_NOT_WRITABLE", "no free name in the capture folder")

    # ---------- รายการ ลบ เปิดโฟลเดอร์ ----------

    def list(self, video_id: str) -> list[Capture]:
        """ภาพของคลิปเรียงตามเวลา · แถวที่ไฟล์ใน cache หายไปแล้วถูกลบออกจาก index"""
        if not VIDEO_ID.fullmatch(video_id):
            return []
        with self._clip_lock(video_id):
            entries = self._read_entries(video_id)
            kept = [e for e in entries if (self._folder(video_id) / e["file"]).is_file()]
            if len(kept) != len(entries):
                try:
                    self._write_entries(video_id, kept)
                except OSError as err:
                    log.warning("เขียนรายการภาพที่ถ่ายของ %s ใหม่ไม่ได้ (%s)", video_id, type(err).__name__)
        return [_to_capture(e) for e in sorted(kept, key=lambda e: e["tMs"])]

    def delete(self, video_id: str, capture_id: str) -> None:
        """ลบภาพจากโฟลเดอร์ (เฉพาะไฟล์เดิมที่บันทึกไว้) แล้วจาก cache และ index · ไม่รู้จัก = KeyError
        ไฟล์ในโฟลเดอร์ลบไม่ได้ (เช่นเปิดค้างในโปรแกรมดูภาพ) = E_OUTPUT_NOT_WRITABLE และไม่เปลี่ยนอะไร"""
        if not VIDEO_ID.fullmatch(video_id) or not CAPTURE_ID.fullmatch(capture_id):
            raise KeyError(capture_id)
        with self._clip_lock(video_id):
            entries = self._read_entries(video_id)
            entry = next((e for e in entries if e["id"] == capture_id), None)
            if entry is None:
                raise KeyError(capture_id)
            target = recorded_output(entry["outputRoot"], entry["outputRel"])
            if target is not None:
                try:
                    target.unlink(missing_ok=True)
                except OSError as err:
                    raise YtError("E_OUTPUT_NOT_WRITABLE", type(err).__name__) from err
            (self._folder(video_id) / entry["file"]).unlink(missing_ok=True)
            try:
                self._write_entries(video_id, [e for e in entries if e["id"] != capture_id])
            except OSError as err:
                raise YtError("E_UNKNOWN", type(err).__name__) from err

    def reveal_dir(self, video_id: str) -> Path | None:
        """โฟลเดอร์ ภาพที่ถ่าย ที่จะเปิด: ของภาพล่าสุดที่ไฟล์ยังอยู่ · ไม่มี = โฟลเดอร์ตามค่าตั้งปัจจุบันถ้ามีอยู่ · ไม่มีเลย = None"""
        if not VIDEO_ID.fullmatch(video_id):
            return None
        with self._clip_lock(video_id):
            entries = sorted(self._read_entries(video_id), key=lambda e: e["createdAt"], reverse=True)
        for entry in entries:
            target = recorded_output(entry["outputRoot"], entry["outputRel"])
            if target is not None:
                return target.parent
        info = self._videos.peek_cached(video_id)
        if info is None:
            return None
        try:
            folder = plan_output(self._settings.output_dir(), str(info.get("title") or ""), video_id, "", "jpg").parent
        except YtError:
            return None
        folder = folder / OUTPUT_DIR
        return folder if folder.is_dir() and not _is_link(folder) else None


def _jpeg_size(path: Path) -> tuple[int, int]:
    try:
        with Image.open(path) as img:
            return int(img.width), int(img.height)
    except (OSError, UnidentifiedImageError) as err:
        raise YtError("E_UNKNOWN", f"unreadable frame: {type(err).__name__}") from err
```

- [ ] **Step 5: Run the tests, expect PASS** — same command as Step 3 (42 passed with ffmpeg; `test_delete_never_follows_a_linked_folder` creates a symlink or, on Windows without the privilege, a junction, and skips only when neither works), then `cd "$WORKTREE" && uv run pytest -q -W error -p no:cacheprovider`.

Measured margins (scratch, ffmpeg 8.1): frames 1.5 s apart differ by 8.6-12.5 grey levels, adjacent frames (0.1 s) by 0.97, the same frame by 0.0, so the `< 0.5 <` assertion also catches an off-by-one-frame seek.

- [ ] **Step 6: Commit**
```bash
cd "$WORKTREE" && git add src/yttoolkit/core/capture.py tests/helpers_capture.py tests/unit/test_capture.py tests/integration/test_capture_ffmpeg.py && git commit -F- <<'EOF'
feat(capture): M5-B2 capture service (single flight, pause brake, cache + folder copy, safe delete)

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
EOF
```

### Task 8: Web capture module (API, model, store, hook, button, menu item, strip)

**Files:**
- Create: `web/src/pages/video/capture/capture-api.ts`, `capture-api.test.ts`, `capture-model.ts`, `capture-model.test.ts`, `capture-store.ts`, `capture-store.test.ts`, `use-capture.ts`, `capture-button.tsx`, `capture-strip.tsx`

**Interfaces:**
- Consumes: C4 (`th.capture.*`, `th.frames.*`, `Capture`, `CaptureList`), `api`/`ApiError` (`lib/api.ts`), `QUEUE_KEY`/`queueQuery` (`lib/jobs.ts`), `errorMessage`/`hasCode` (`pages/video/errors.ts`), `markTimeMs`/`playerActions` (`player/player-store.ts`), `Lightbox` (`lightbox.tsx`, actions passed as `children`), `copyImage`, `downloadFile`, `formatDuration`, `formatTimecode`, `youtubeWatchUrl`, shadcn `Button`, `Tooltip`, `ContextMenuItem`, `AlertDialog*`, `AspectRatio`, `Spinner`.
- Produces: C8 exactly. Nothing mounts these components yet (T13 does).

- [ ] **Step 1: Write the failing tests**

`web/src/pages/video/capture/capture-model.test.ts`:
```ts
import { describe, expect, it } from "vitest"

import {
  blockTooltip,
  captureBlock,
  captureClock,
  captureDownloadUrl,
  captureFileName,
  captureTimeMs,
  clockTime,
  focusAfterDelete,
  stripKeyTarget,
} from "./capture-model"

describe("captureTimeMs", () => {
  it("ปัดทีละ 100 ms ไม่ติดลบ", () => {
    expect(captureTimeMs(125_449)).toBe(125_400)
    expect(captureTimeMs(125_450)).toBe(125_500)
    expect(captureTimeMs(-30)).toBe(0)
    expect(captureTimeMs(Number.NaN)).toBe(0)
  })
})

describe("captureClock", () => {
  it("วินาทีเต็มไม่มีทศนิยม · มีเศษแสดงหนึ่งตำแหน่ง · ครบชั่วโมงแสดงชั่วโมง", () => {
    expect(captureClock(125_000)).toBe("2:05")
    expect(captureClock(125_400)).toBe("2:05.4")
    expect(captureClock(3_725_900)).toBe("1:02:05.9")
    expect(captureClock(0)).toBe("0:00")
  })
})

describe("clockTime", () => {
  it("HH:MM ตามนาฬิกาเครื่อง · อ่านไม่ได้ = ว่าง", () => {
    const at = new Date(2026, 9, 5, 7, 4)
    expect(clockTime(at.toISOString())).toBe("07:04")
    expect(clockTime("ไม่ใช่เวลา")).toBe("")
  })
})

describe("captureBlock / blockTooltip", () => {
  const now = Date.parse("2026-10-05T10:00:00Z")
  it("คลิปสดมาก่อน", () => {
    const block = captureBlock({ isLive: true, pausedUntil: "2026-10-05T10:10:00Z", now })
    expect(block).toEqual({ kind: "live" })
    expect(blockTooltip(block)).toBe("คลิปสดถ่ายภาพคมไม่ได้")
  })

  it("คิวพักอยู่ = บอกเวลาที่ลองใหม่ได้ · ครบเวลาแล้วหรืออ่านไม่ได้ = ถ่ายได้", () => {
    const until = "2026-10-05T10:10:00Z"
    const block = captureBlock({ isLive: false, pausedUntil: until, now })
    expect(block).toEqual({ kind: "paused", until })
    expect(blockTooltip(block)).toBe(`พักการโหลดอยู่เพราะยูทูปขอตรวจสอบ ลองใหม่หลัง ${clockTime(until)}`)
    expect(captureBlock({ isLive: false, pausedUntil: "2026-10-05T09:59:00Z", now })).toBeNull()
    expect(captureBlock({ isLive: false, pausedUntil: "x", now })).toBeNull()
    expect(captureBlock({ isLive: false, pausedUntil: null, now })).toBeNull()
    expect(blockTooltip(null)).toBeNull()
  })
})

describe("stripKeyTarget", () => {
  it("ลูกศรเลื่อนทีละภาพไม่เลยขอบ · Home/End · ปุ่มอื่น = null", () => {
    expect(stripKeyTarget("ArrowRight", 0, 3)).toBe(1)
    expect(stripKeyTarget("ArrowDown", 2, 3)).toBe(2)
    expect(stripKeyTarget("ArrowLeft", 0, 3)).toBe(0)
    expect(stripKeyTarget("ArrowUp", 2, 3)).toBe(1)
    expect(stripKeyTarget("Home", 2, 3)).toBe(0)
    expect(stripKeyTarget("End", 0, 3)).toBe(2)
    expect(stripKeyTarget("Enter", 1, 3)).toBeNull()
    expect(stripKeyTarget("ArrowRight", 0, 0)).toBeNull()
  })
})

describe("focusAfterDelete", () => {
  it("ภาพถัดไป · ภาพสุดท้ายถูกลบ = ภาพก่อนหน้า · ไม่เหลือ = null", () => {
    expect(focusAfterDelete(["a", "b", "c"], "b")).toBe("c")
    expect(focusAfterDelete(["a", "b", "c"], "c")).toBe("b")
    expect(focusAfterDelete(["a"], "a")).toBeNull()
    expect(focusAfterDelete(["a", "b"], "x")).toBe("a")
  })
})

describe("ชื่อและลิงก์โหลดภาพ", () => {
  it("ต่อ download=1 ถูกตัว · ชื่อ frame_HH-MM-SS.jpg", () => {
    expect(captureDownloadUrl("/api/cache/x/captures/c_1.jpg?v=9")).toBe("/api/cache/x/captures/c_1.jpg?v=9&download=1")
    expect(captureDownloadUrl("/a.jpg")).toBe("/a.jpg?download=1")
    expect(captureFileName(125_400)).toBe("frame_00-02-05.jpg")
  })
})
```
`web/src/pages/video/capture/capture-api.test.ts`:
```ts
import { QueryClient } from "@tanstack/react-query"
import { describe, expect, it, vi } from "vitest"

import type { Capture } from "@/lib/types"

import { capturesKey, capturesQuery, deleteCapture, postCapture, revealCaptures, withCapture, withoutCapture } from "./capture-api"

const BBB = "aqz-KE-bpKQ"
const item = (tMs: number): Capture => ({ id: `c_${tMs}`, tMs, width: 1920, height: 1080, url: `/api/cache/${BBB}/captures/c_${tMs}.jpg?v=1` })

function stubFetch(status: number, body: unknown) {
  return vi.fn<typeof fetch>(async () =>
    status === 204 ? new Response(null, { status }) : new Response(JSON.stringify(body), { status }),
  )
}

describe("withCapture / withoutCapture", () => {
  it("เติมแล้วเรียงตามเวลา · id เดิมแทนที่ · ลบตาม id", () => {
    const list = withCapture(withCapture(undefined, item(3000)), item(1000))
    expect(list.map((c) => c.tMs)).toEqual([1000, 3000])
    expect(withCapture(list, { ...item(1000), width: 1280 }).map((c) => c.width)).toEqual([1280, 1920])
    expect(withoutCapture(list, "c_1000").map((c) => c.id)).toEqual(["c_3000"])
    expect(withoutCapture(undefined, "c_1")).toEqual([])
  })
})

describe("คำขอ", () => {
  it("GET รายการ คืน captures", async () => {
    const fetch = stubFetch(200, { captures: [item(1000)] })
    const client = new QueryClient()
    const data = await client.fetchQuery(capturesQuery(BBB, true, { fetch }))
    expect(data).toEqual([item(1000)])
    expect(fetch).toHaveBeenCalledWith(`/api/videos/${BBB}/captures`, expect.objectContaining({ method: "GET" }))
    expect(capturesKey(BBB)).toEqual(["captures", BBB])
  })

  it("POST ส่ง tMs พร้อม token · DELETE และ reveal ใช้ path ของภาพ", async () => {
    const post = stubFetch(201, item(125_400))
    expect(await postCapture(BBB, 125_400, { fetch: post, token: "t" })).toEqual(item(125_400))
    const [url, init] = post.mock.calls[0]
    expect(url).toBe(`/api/videos/${BBB}/captures`)
    expect(init?.method).toBe("POST")
    expect(init?.body).toBe(JSON.stringify({ tMs: 125_400 }))
    expect(new Headers(init?.headers).get("X-Toolkit-Token")).toBe("t")

    const del = stubFetch(204, null)
    await deleteCapture(BBB, "c_125400", { fetch: del, token: "t" })
    expect(del.mock.calls[0][0]).toBe(`/api/videos/${BBB}/captures/c_125400`)
    expect(del.mock.calls[0][1]?.method).toBe("DELETE")

    const reveal = stubFetch(200, { ok: true })
    await revealCaptures(BBB, { fetch: reveal, token: "t" })
    expect(reveal.mock.calls[0][0]).toBe(`/api/videos/${BBB}/captures/reveal`)
  })

  it("error ของ backend ส่งต่อเป็น ApiError พร้อมข้อความไทย", async () => {
    const fetch = stubFetch(422, { error: { code: "E_CAPTURE_UNSUPPORTED", message: "ข้อความ", detail: null } })
    await expect(postCapture(BBB, 0, { fetch, token: "t" })).rejects.toMatchObject({ code: "E_CAPTURE_UNSUPPORTED", message: "ข้อความ" })
  })
})
```
`web/src/pages/video/capture/capture-store.test.ts` (also covers `runCapture`; `sonner` and `postCapture` are mocked):
```ts
import { QueryClient } from "@tanstack/react-query"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

import { ApiError } from "@/lib/api"
import { QUEUE_KEY } from "@/lib/jobs"
import type { Capture } from "@/lib/types"

import { capturesKey } from "./capture-api"
import { __resetCaptureStoreForTests, captureStore } from "./capture-store"
import { runCapture } from "./use-capture"

const toast = vi.hoisted(() => ({ success: vi.fn(), error: vi.fn() }))
vi.mock("sonner", () => ({ toast }))
const api = vi.hoisted(() => ({ postCapture: vi.fn() }))
vi.mock("./capture-api", async (importOriginal) => ({ ...(await importOriginal<object>()), postCapture: api.postCapture }))

const BBB = "aqz-KE-bpKQ"
const item = (tMs: number): Capture => ({ id: `c_${tMs}`, tMs, width: 1920, height: 1080, url: `/api/cache/${BBB}/captures/c_${tMs}.jpg?v=1` })

beforeEach(() => {
  __resetCaptureStoreForTests()
  toast.success.mockReset()
  toast.error.mockReset()
  api.postCapture.mockReset()
})
afterEach(() => __resetCaptureStoreForTests())

describe("captureStore", () => {
  it("tryBegin is single-flight: ครั้งที่สองระหว่างถ่าย = false จน end", () => {
    expect(captureStore.tryBegin()).toBe(true)
    expect(captureStore.tryBegin()).toBe(false)
    captureStore.end()
    expect(captureStore.tryBegin()).toBe(true)
  })

  it("view / closeView / flash (n เพิ่มทุกครั้ง)", () => {
    captureStore.view({ videoId: BBB, id: "c_1" })
    expect(captureStore.get().viewing).toEqual({ videoId: BBB, id: "c_1" })
    captureStore.closeView()
    expect(captureStore.get().viewing).toBeNull()
    captureStore.flash({ videoId: BBB, id: "c_1" })
    captureStore.flash({ videoId: BBB, id: "c_1" })
    expect(captureStore.get().flash).toEqual({ videoId: BBB, id: "c_1", n: 2 })
  })
})

describe("runCapture", () => {
  it("ปัดเวลา ส่งครั้งเดียว เติมลงแถบตามเวลา กระพริบ และ toast มีปุ่ม ดูภาพ", async () => {
    const client = new QueryClient()
    client.setQueryData<Capture[]>(capturesKey(BBB), [item(200_000)])
    api.postCapture.mockResolvedValue(item(125_400))
    const first = runCapture(client, BBB, 125_449)
    await runCapture(client, BBB, 9_000) // ระหว่างถ่ายอยู่: ไม่ส่งซ้ำ
    await first
    expect(api.postCapture).toHaveBeenCalledTimes(1)
    expect(api.postCapture).toHaveBeenCalledWith(BBB, 125_400)
    expect(client.getQueryData<Capture[]>(capturesKey(BBB))?.map((c) => c.tMs)).toEqual([125_400, 200_000])
    expect(captureStore.get().flash).toMatchObject({ videoId: BBB, id: "c_125400" })
    expect(captureStore.get().busy).toBe(false)
    const [message, options] = toast.success.mock.calls[0]
    expect(message).toBe("ถ่ายภาพคมแล้ว · 2:05.4")
    expect(options.action.label).toBe("ดูภาพ")
    options.action.onClick()
    expect(captureStore.get().viewing).toEqual({ videoId: BBB, id: "c_125400" })
  })

  it("พลาด = toast ข้อความจาก backend ไม่เติมแถบ · ยูทูปขอตรวจสอบ = โหลดสถานะคิวใหม่", async () => {
    const client = new QueryClient()
    const invalidate = vi.spyOn(client, "invalidateQueries")
    api.postCapture.mockRejectedValueOnce(new ApiError(422, "E_CAPTURE_UNSUPPORTED", "ถ่ายไม่ได้", null, null))
    await runCapture(client, BBB, 0)
    expect(toast.error).toHaveBeenCalledWith("ถ่ายไม่ได้")
    expect(client.getQueryData(capturesKey(BBB))).toBeUndefined()
    expect(invalidate).not.toHaveBeenCalled()
    api.postCapture.mockRejectedValueOnce(new ApiError(429, "E_BOT_CHECK", "ยูทูปขอให้ยืนยัน", null, null))
    await runCapture(client, BBB, 0)
    expect(invalidate).toHaveBeenCalledWith({ queryKey: QUEUE_KEY })
    expect(captureStore.get().busy).toBe(false)
  })
})
```

- [ ] **Step 2: Run them, expect FAIL**

Run: `cd "$WORKTREE/web" && npx vitest run src/pages/video/capture`
Expected: FAIL (`Failed to resolve import "./capture-model"` and the others).

- [ ] **Step 3: Implement the pure parts and the store**

`web/src/pages/video/capture/capture-api.ts`:
```ts
import { queryOptions } from "@tanstack/react-query"

import { api } from "@/lib/api"
import type { Capture, CaptureList } from "@/lib/types"

/** ภาพคมที่ถ่ายตรงจุด (M5 รอบ B2 สัญญา C11): รายการ ถ่าย ลบ และเปิดโฟลเดอร์ */

type ApiDeps = Parameters<typeof api>[2]

export const capturesKey = (videoId: string) => ["captures", videoId] as const

/** รายการภาพของคลิป เรียงตามเวลา · URL ภาพมี ?v= อยู่แล้ว เก็บผลไว้สั้น ๆ แบบ storyboard */
export function capturesQuery(videoId: string, enabled: boolean, deps?: ApiDeps) {
  return queryOptions({
    queryKey: capturesKey(videoId),
    queryFn: ({ signal }) => api<CaptureList>(`/videos/${videoId}/captures`, { signal }, deps).then((body) => body.captures),
    enabled,
    retry: false,
    staleTime: 60_000,
  })
}

export function postCapture(videoId: string, tMs: number, deps?: ApiDeps): Promise<Capture> {
  return api<Capture>(`/videos/${videoId}/captures`, { method: "POST", body: JSON.stringify({ tMs }) }, deps)
}

export async function deleteCapture(videoId: string, id: string, deps?: ApiDeps): Promise<void> {
  await api<null>(`/videos/${videoId}/captures/${encodeURIComponent(id)}`, { method: "DELETE" }, deps)
}

export async function revealCaptures(videoId: string, deps?: ApiDeps): Promise<void> {
  await api<{ ok: boolean }>(`/videos/${videoId}/captures/reveal`, { method: "POST" }, deps)
}

/** ใส่ภาพใหม่ (id เดิม = แทนที่) แล้วเรียงตามเวลา */
export function withCapture(list: readonly Capture[] | undefined, item: Capture): Capture[] {
  return [...(list ?? []).filter((c) => c.id !== item.id), item].sort((a, b) => a.tMs - b.tMs)
}

export function withoutCapture(list: readonly Capture[] | undefined, id: string): Capture[] {
  return (list ?? []).filter((c) => c.id !== id)
}
```
`web/src/pages/video/capture/capture-model.ts`:
```ts
import { fill, th } from "@/i18n/th"
import { formatDuration, formatTimecode } from "@/lib/format"

/** ส่วนที่คิดล้วน ๆ ของการถ่ายภาพคมตรงจุด (M5 รอบ B2) เทสได้ใน node */

/** ปุ่มถ่ายภาพปัดเวลาของตัวเล่นทีละ 100 ms (spec 2.1) */
export const CAPTURE_STEP_MS = 100

export function captureTimeMs(ms: number): number {
  const safe = Number.isFinite(ms) ? Math.max(0, ms) : 0
  return Math.round(safe / CAPTURE_STEP_MS) * CAPTURE_STEP_MS
}

/** เวลาของภาพที่ถ่าย "2:05" หรือ "2:05.4": ละเอียดถึง 0.1 วินาที สองภาพในวินาทีเดียวกันจึงอ่านต่างกัน */
export function captureClock(ms: number): string {
  const safe = Math.max(0, Math.round(Number.isFinite(ms) ? ms : 0))
  const whole = formatDuration(Math.floor(safe / 1000))
  const tenth = Math.floor((safe % 1000) / 100)
  return tenth === 0 ? whole : `${whole}.${tenth}`
}

/** เวลาแบบนาฬิกา HH:MM ของเครื่อง (คิวพักถึงกี่โมง) อ่านไม่ได้ = "" */
export function clockTime(iso: string): string {
  const at = new Date(iso)
  if (Number.isNaN(at.getTime())) return ""
  return `${String(at.getHours()).padStart(2, "0")}:${String(at.getMinutes()).padStart(2, "0")}`
}

/** เหตุที่ถ่ายไม่ได้ตอนนี้: คลิปสด · คิวพักเพราะยูทูปขอตรวจสอบ (pausedUntil ยังไม่ถึง) · null = ถ่ายได้ */
export type CaptureBlock = { kind: "live" } | { kind: "paused"; until: string } | null

export function captureBlock(o: { isLive: boolean; pausedUntil: string | null; now: number }): CaptureBlock {
  if (o.isLive) return { kind: "live" }
  if (o.pausedUntil) {
    const until = Date.parse(o.pausedUntil)
    if (!Number.isNaN(until) && until > o.now) return { kind: "paused", until: o.pausedUntil }
  }
  return null
}

export function blockTooltip(block: CaptureBlock): string | null {
  if (block === null) return null
  if (block.kind === "live") return th.capture.liveDisabled
  return fill(th.capture.pausedDisabled, { time: clockTime(block.until) })
}

/** ปุ่มในแถบภาพที่ถ่ายไว้ (จุดหยุด Tab เดียว เลื่อนด้วยลูกศร): ตำแหน่งใหม่ · null = ไม่ใช่ปุ่มของแถบ */
export function stripKeyTarget(key: string, index: number, count: number): number | null {
  if (count <= 0) return null
  switch (key) {
    case "ArrowRight":
    case "ArrowDown":
      return Math.min(count - 1, index + 1)
    case "ArrowLeft":
    case "ArrowUp":
      return Math.max(0, index - 1)
    case "Home":
      return 0
    case "End":
      return count - 1
    default:
      return null
  }
}

/** ลบภาพแล้วโฟกัสภาพไหนต่อ: ภาพถัดไป ไม่มีก็ภาพก่อนหน้า · ไม่เหลือภาพ = null */
export function focusAfterDelete(ids: readonly string[], removed: string): string | null {
  const at = ids.indexOf(removed)
  if (at < 0) return ids[0] ?? null
  return ids[at + 1] ?? ids[at - 1] ?? null
}

/** url สำหรับโหลดภาพ (?v= มีอยู่แล้ว ต่อ &download=1) */
export function captureDownloadUrl(url: string): string {
  return `${url}${url.includes("?") ? "&" : "?"}download=1`
}

/** ชื่อไฟล์สำรองตอนโหลด frame_HH-MM-SS.jpg (แบบเดียวกับไฟล์ในโฟลเดอร์) */
export function captureFileName(ms: number): string {
  return `frame_${formatTimecode(ms).replaceAll(":", "-")}.jpg`
}
```
`web/src/pages/video/capture/capture-store.ts`:
```ts
import { useSyncExternalStore } from "react"

/**
 * สถานะร่วมของการถ่ายภาพคมทั้งแอพ (M5 รอบ B2): ถ่ายได้ครั้งละภาพ (ทุกปุ่มใช้ busy ตัวเดียวกัน)
 * viewing = ภาพที่ต้องเปิดใหญ่ (toast "ดูภาพ" สั่งได้แม้แถบยังไม่ถูกวาด) · flash = ภาพที่เพิ่งถ่าย ให้แถบกระพริบ (n เพิ่มทุกครั้ง)
 */

export type CaptureTarget = { videoId: string; id: string }

export type CaptureUiState = {
  busy: boolean
  viewing: CaptureTarget | null
  flash: (CaptureTarget & { n: number }) | null
}

const INITIAL: CaptureUiState = { busy: false, viewing: null, flash: null }

let state: CaptureUiState = INITIAL
const listeners = new Set<() => void>()

function set(patch: Partial<CaptureUiState>): void {
  state = { ...state, ...patch }
  for (const listener of listeners) listener()
}

export const captureStore = {
  get: (): CaptureUiState => state,
  subscribe(listener: () => void): () => void {
    listeners.add(listener)
    return () => listeners.delete(listener)
  },
  /** จองการถ่าย · มีการถ่ายค้างอยู่ = false (ไม่ส่งคำขอซ้ำ) */
  tryBegin(): boolean {
    if (state.busy) return false
    set({ busy: true })
    return true
  },
  end(): void {
    if (state.busy) set({ busy: false })
  },
  view(target: CaptureTarget): void {
    set({ viewing: target })
  },
  closeView(): void {
    if (state.viewing) set({ viewing: null })
  },
  flash(target: CaptureTarget): void {
    set({ flash: { ...target, n: (state.flash?.n ?? 0) + 1 } })
  },
}

/** อ่านเฉพาะค่าที่เลือก (ต้องคืน primitive หรืออ้างอิงเดิม) */
export function useCaptureUi<T>(select: (s: CaptureUiState) => T): T {
  return useSyncExternalStore(
    captureStore.subscribe,
    () => select(state),
    () => select(state),
  )
}

/** ทดสอบเท่านั้น */
export function __resetCaptureStoreForTests(): void {
  state = INITIAL
  for (const listener of listeners) listener()
}
```
`web/src/pages/video/capture/use-capture.ts`:
```ts
import { useQuery, useQueryClient, type QueryClient } from "@tanstack/react-query"
import { useEffect, useState } from "react"
import { toast } from "sonner"

import { fill, th } from "@/i18n/th"
import { QUEUE_KEY, queueQuery } from "@/lib/jobs"
import type { Capture, VideoInfo } from "@/lib/types"

import { errorMessage, hasCode } from "../errors"
import { capturesKey, postCapture, withCapture } from "./capture-api"
import { captureBlock, captureClock, captureTimeMs, type CaptureBlock } from "./capture-model"
import { captureStore, useCaptureUi } from "./capture-store"

/** คลิปสดไหม: อ่านจากข้อมูลคลิปที่หน้า W2 โหลดไว้แล้ว (["video", id]) ไม่ยิงคำขอเพิ่ม */
function cachedIsLive(client: QueryClient, videoId: string): boolean {
  return client.getQueryData<VideoInfo>(["video", videoId])?.isLive === true
}

/**
 * ถ่ายภาพคมหนึ่งภาพ (ทุกทางเข้าใช้ตัวนี้ spec 2.2): ถ่ายได้ครั้งละภาพทั้งแอพ (มีค้างอยู่ = ไม่ทำอะไร)
 * สำเร็จ = เติมลงแถบ (เวลาเดิม = แทนที่) + กระพริบ + toast "ถ่ายภาพคมแล้ว · {time}" มีปุ่ม "ดูภาพ"
 * พลาด = toast ข้อความจาก backend · ยูทูปขอตรวจสอบ/คิวพัก = โหลดสถานะคิวใหม่ ทุกปุ่มจะปิดพร้อมเหตุผล
 */
export async function runCapture(client: QueryClient, videoId: string, ms: number): Promise<void> {
  if (!captureStore.tryBegin()) return
  try {
    const capture = await postCapture(videoId, captureTimeMs(ms))
    client.setQueryData<Capture[]>(capturesKey(videoId), (list) => withCapture(list, capture))
    captureStore.flash({ videoId, id: capture.id })
    toast.success(fill(th.capture.done, { time: captureClock(capture.tMs) }), {
      action: { label: th.capture.view, onClick: () => captureStore.view({ videoId, id: capture.id }) },
    })
  } catch (error) {
    toast.error(errorMessage(error, th.errors.unknown))
    if (hasCode(error, "E_BOT_CHECK") || hasCode(error, "E_QUEUE_PAUSED")) {
      void client.invalidateQueries({ queryKey: QUEUE_KEY })
    }
  } finally {
    captureStore.end()
  }
}

/** เวลาปัจจุบันที่เดินทุกวินาทีเฉพาะตอน active (ปุ่มกลับมากดได้เองเมื่อคิวครบเวลาพัก) */
function useNowWhile(active: boolean): number {
  const [now, setNow] = useState(() => Date.now())
  useEffect(() => {
    if (!active) return
    const timer = window.setInterval(() => setNow(Date.now()), 1000)
    return () => window.clearInterval(timer)
  }, [active])
  return now
}

/** สถานะของปุ่มถ่ายภาพ: กำลังถ่าย (ทั้งแอพ) · เหตุที่ถ่ายไม่ได้ · capture(ms) = ถ่ายที่เวลานั้น (กดไม่ได้อยู่ = ไม่ทำอะไร) */
export function useCapture(videoId: string): { busy: boolean; block: CaptureBlock; capture: (ms: number) => void } {
  const client = useQueryClient()
  const busy = useCaptureUi((s) => s.busy)
  const queue = useQuery(queueQuery())
  const pausedUntil = queue.data?.pausedUntil ?? null
  const now = useNowWhile(pausedUntil !== null)
  const block = captureBlock({ isLive: cachedIsLive(client, videoId), pausedUntil, now })
  const capture = (ms: number) => {
    if (busy || block !== null) return
    void runCapture(client, videoId, ms)
  }
  return { busy, block, capture }
}
```

- [ ] **Step 4: Run the tests, expect PASS** — same command as Step 2 (16 tests).

- [ ] **Step 5: Implement the components**

`web/src/pages/video/capture/capture-button.tsx`:
```tsx
import { Camera } from "lucide-react"
import type { ComponentProps } from "react"

import { Button } from "@/components/ui/button"
import { ContextMenuItem } from "@/components/ui/context-menu"
import { Spinner } from "@/components/ui/spinner"
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip"
import { th } from "@/i18n/th"

import { markTimeMs } from "../player/player-store"
import { blockTooltip } from "./capture-model"
import { useCapture } from "./use-capture"

type Props = { videoId: string; variant?: "row" | "dock" }

/**
 * "ถ่ายภาพคมตรงนี้" (M5 รอบ B2 spec 2.1-2.2): ใช้เวลาที่ตัวเล่นอยู่ (markTimeMs กำลังโหลด = เวลาที่ขอไว้) ปัดทีละ 100 ms
 * row = ปุ่มมีข้อความในแถวใต้ตัวเล่น · dock = ปุ่มไอคอนบนตัวเล่นลอย (ชื่อปุ่มเดียวกัน + tooltip)
 * กำลังถ่าย (ทั้งแอพ) = วงหมุน + "กำลังถ่าย…" · คลิปสด / คิวพัก = กดไม่ได้แต่โฟกัสได้ พร้อม tooltip บอกเหตุผล
 */
export function CaptureButton({ videoId, variant = "row" }: Props) {
  const { busy, block, capture } = useCapture(videoId)
  const reason = blockTooltip(block)
  const label = busy ? th.capture.busy : th.capture.button
  const dock = variant === "dock"
  const props: ComponentProps<typeof Button> = {
    variant: dock ? "ghost" : "outline",
    size: dock ? "icon-xs" : "sm",
    "aria-label": dock ? label : undefined,
    className: dock ? "max-sm:size-11" : "max-sm:h-11",
    disabled: busy || reason !== null,
    focusableWhenDisabled: true,
    onClick: () => capture(markTimeMs()),
  }
  const content = (
    <>
      {busy ? <Spinner aria-hidden /> : <Camera aria-hidden />}
      {dock ? null : label}
    </>
  )
  const tip = reason ?? (dock ? label : null)
  if (tip === null) {
    return (
      <Button {...props} data-slot="capture-button">
        {content}
      </Button>
    )
  }
  return (
    <Tooltip>
      <TooltipTrigger render={<Button {...props} data-slot="capture-button" />}>{content}</TooltipTrigger>
      <TooltipContent>{tip}</TooltipContent>
    </Tooltip>
  )
}

/** รายการ "ถ่ายภาพคมตรงนี้" ในเมนูคลิกขวาของภาพเฟรม: ใช้เวลาของภาพ · กดไม่ได้ระหว่างถ่ายหรือเมื่อถ่ายไม่ได้ (เมนูไม่มี tooltip) */
export function CaptureMenuItem({ videoId, tMs }: { videoId: string; tMs: number }) {
  const { busy, block, capture } = useCapture(videoId)
  return (
    <ContextMenuItem disabled={busy || block !== null} onClick={() => capture(tMs)}>
      <Camera aria-hidden />
      {th.capture.button}
    </ContextMenuItem>
  )
}
```
`web/src/pages/video/capture/capture-strip.tsx`:
```tsx
import { useQuery, useQueryClient } from "@tanstack/react-query"
import { Download, ExternalLink, FolderOpen, ImageIcon, Play, Trash2 } from "lucide-react"
import { useEffect, useId, useRef, useState, type KeyboardEvent } from "react"
import { toast } from "sonner"

import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog"
import { AspectRatio } from "@/components/ui/aspect-ratio"
import { Button } from "@/components/ui/button"
import { fill, th } from "@/i18n/th"
import { copyImage } from "@/lib/clipboard"
import { downloadFile } from "@/lib/download"
import { youtubeWatchUrl } from "@/lib/format"
import type { Capture } from "@/lib/types"
import { cn } from "cn"

import { errorMessage } from "../errors"
import { Lightbox } from "../lightbox"
import { playerActions } from "../player/player-store"
import { capturesKey, capturesQuery, deleteCapture, revealCaptures, withoutCapture } from "./capture-api"
import { captureClock, captureDownloadUrl, captureFileName, focusAfterDelete, stripKeyTarget } from "./capture-model"
import { captureStore, useCaptureUi } from "./capture-store"

/** wrap = ภาพตัดขึ้นบรรทัด (แบบปกติ จอแคบ แนวตั้ง) · row = แถวเดียวเลื่อนได้ (โรงภาพยนตร์แนวนอน) */
export type StripLayout = "wrap" | "row"

const TILE_BUTTON =
  "relative block w-full cursor-zoom-in overflow-hidden rounded-md bg-black outline-none hover:ring-2 hover:ring-ring/40 focus-visible:ring-3 focus-visible:ring-ring"

const reducedMotion = () =>
  typeof window.matchMedia === "function" && window.matchMedia("(prefers-reduced-motion: reduce)").matches

/** ตำแหน่งที่โฟกัสได้เมื่อแถบหายไป (ลบภาพสุดท้ายแล้ว): ปุ่มถ่ายภาพ ไม่มีก็ชื่อคลิป */
function fallbackFocus(): HTMLElement | null {
  return document.querySelector<HTMLElement>('[data-slot="capture-button"]') ?? document.querySelector<HTMLElement>("h1")
}

async function copyCapture(url: string): Promise<void> {
  try {
    await copyImage(url)
    toast.success(th.frames.imageCopied)
  } catch {
    toast.error(th.frames.copyImageFailed)
  }
}

async function downloadCapture(capture: Capture): Promise<void> {
  const id = toast.loading(th.frames.preparing)
  try {
    await downloadFile(captureDownloadUrl(capture.url), captureFileName(capture.tMs))
    toast.dismiss(id)
  } catch (error) {
    toast.error(errorMessage(error, th.errors.downloadFailed), { id })
  }
}

/**
 * แถบ "ภาพที่ถ่ายไว้ ({n})" ใต้ตัวเล่น (M5 รอบ B2 spec 2.3): ภาพ 16:9 กว้างราว 96 px พร้อมป้ายเวลา เรียงตามเวลา
 * จุดหยุด Tab เดียว (ภาพที่โฟกัสล่าสุด) ลูกศร/Home/End เลื่อน Enter/Space เปิดภาพใหญ่ · ภาพแนวตั้งเว้นขอบในช่อง 16:9
 * ไม่มีภาพ / กำลังโหลด / โหลดไม่ได้ = ไม่แสดงอะไร (แถบเป็นของเสริม) · ภาพใหญ่มีปุ่ม คัดลอก โหลด เปิดในยูทูป เล่นจากตรงนี้ ลบ
 */
export function CaptureStrip({ videoId, layout, className }: { videoId: string; layout: StripLayout; className?: string }) {
  const client = useQueryClient()
  const captures = useQuery(capturesQuery(videoId, true))
  const list = captures.data ?? []
  const viewing = useCaptureUi((s) => (s.viewing?.videoId === videoId ? s.viewing.id : null))
  const flash = useCaptureUi((s) => (s.flash?.videoId === videoId ? s.flash : null))
  const [active, setActive] = useState(0)
  const [confirming, setConfirming] = useState<Capture | null>(null)
  const [deleting, setDeleting] = useState(false)
  const [lastViewed, setLastViewed] = useState<Capture | null>(null)
  const buttons = useRef(new Map<string, HTMLButtonElement>())
  const afterDelete = useRef<string | null>(null)
  const headingId = useId()

  const viewIndex = viewing === null ? -1 : list.findIndex((c) => c.id === viewing)
  const current = viewIndex >= 0 ? list[viewIndex] : null
  // จำภาพล่าสุดไว้ ให้ภาพยังอยู่ระหว่างแอนิเมชันปิด
  if (current !== null && current !== lastViewed) setLastViewed(current)
  const shown = current ?? lastViewed
  const tabStop = Math.min(active, Math.max(0, list.length - 1))

  // ภาพที่เพิ่งถ่าย (หรือถ่ายซ้ำเวลาเดิม): เลื่อนให้เห็นแล้วกระพริบกรอบสั้น ๆ (ลดการเคลื่อนไหว = ไม่กระพริบ)
  useEffect(() => {
    if (flash === null) return
    const node = buttons.current.get(flash.id)
    if (!node) return
    node.scrollIntoView({ block: "nearest", inline: "nearest" })
    if (reducedMotion() || typeof node.animate !== "function") return
    node.animate(
      [{ boxShadow: "0 0 0 3px var(--primary)" }, { boxShadow: "0 0 0 0 transparent" }],
      { duration: 1200, easing: "ease-out" },
    )
  }, [flash])

  if (list.length === 0) return null

  function focusAt(index: number) {
    setActive(index)
    buttons.current.get(list[index].id)?.focus()
  }

  function onKeyDown(event: KeyboardEvent<HTMLUListElement>) {
    const index = list.findIndex((c) => buttons.current.get(c.id) === document.activeElement)
    if (index < 0) return
    const next = stripKeyTarget(event.key, index, list.length)
    if (next === null) return
    event.preventDefault()
    focusAt(next)
  }

  function onLightboxKey(event: KeyboardEvent<HTMLDivElement>) {
    if (viewIndex < 0) return
    const next = event.key === "ArrowRight" ? viewIndex + 1 : event.key === "ArrowLeft" ? viewIndex - 1 : -1
    if (next < 0 || next >= list.length) return
    event.preventDefault()
    setActive(next)
    captureStore.view({ videoId, id: list[next].id })
  }

  function returnFocus(): HTMLElement | null {
    const target = afterDelete.current ?? shown?.id ?? null
    afterDelete.current = null
    return (target !== null ? buttons.current.get(target) : undefined) ?? fallbackFocus()
  }

  async function confirmDelete() {
    if (confirming === null || deleting) return
    const removed = confirming
    setDeleting(true)
    try {
      await deleteCapture(videoId, removed.id)
      const next = focusAfterDelete(list.map((c) => c.id), removed.id)
      afterDelete.current = next
      client.setQueryData<Capture[]>(capturesKey(videoId), (old) => withoutCapture(old, removed.id))
      setConfirming(null)
      captureStore.closeView()
      toast.success(th.capture.deleted)
      // กล่องยืนยันกับภาพใหญ่ปิดพร้อมกัน: หลังแอนิเมชันปิดจบ โฟกัสภาพถัดไป (ไม่เหลือภาพ = ปุ่มถ่ายภาพ / ชื่อคลิป)
      window.setTimeout(() => ((next !== null ? buttons.current.get(next) : undefined) ?? fallbackFocus())?.focus(), 200)
    } catch (error) {
      toast.error(errorMessage(error, th.errors.unknown))
    } finally {
      setDeleting(false)
    }
  }

  async function reveal() {
    try {
      await revealCaptures(videoId)
    } catch (error) {
      toast.error(errorMessage(error, th.errors.unknown))
    }
  }

  const time = shown ? captureClock(shown.tMs) : ""
  return (
    <section aria-labelledby={headingId} data-slot="capture-strip" className={cn("flex min-w-0 flex-col gap-1.5", className)}>
      <div className="flex items-center justify-between gap-2">
        <h2 id={headingId} className="text-sm font-medium">
          {fill(th.capture.stripTitle, { n: list.length })}
        </h2>
        <Button variant="link" size="sm" className="h-auto px-0 max-sm:h-11" onClick={() => void reveal()}>
          <FolderOpen aria-hidden />
          {th.capture.openFolder}
        </Button>
      </div>
      <ul
        aria-labelledby={headingId}
        onKeyDown={onKeyDown}
        className={cn("flex gap-2 p-[3px]", layout === "row" ? "overflow-x-auto" : "flex-wrap")}
      >
        {list.map((capture, index) => {
          const clock = captureClock(capture.tMs)
          return (
            <li key={capture.id} className="w-24 shrink-0">
              <button
                ref={(node) => {
                  if (node) buttons.current.set(capture.id, node)
                  else buttons.current.delete(capture.id)
                }}
                type="button"
                tabIndex={index === tabStop ? 0 : -1}
                aria-haspopup="dialog"
                onFocus={() => setActive(index)}
                onClick={() => {
                  setActive(index)
                  captureStore.view({ videoId, id: capture.id })
                }}
                className={TILE_BUTTON}
              >
                <AspectRatio ratio={16 / 9}>
                  <img
                    src={capture.url}
                    alt={fill(th.frames.frameAlt, { time: clock })}
                    loading="lazy"
                    decoding="async"
                    className="size-full object-contain"
                  />
                  <span
                    aria-hidden
                    className="pointer-events-none absolute bottom-0.5 left-0.5 rounded-sm bg-background/85 px-1 font-mono text-[11px] text-foreground"
                  >
                    {clock}
                  </span>
                </AspectRatio>
              </button>
            </li>
          )
        })}
      </ul>
      {shown && (
        <Lightbox
          open={current !== null}
          src={shown.url}
          label={fill(th.frames.frameAlt, { time })}
          onClose={() => captureStore.closeView()}
          finalFocus={returnFocus}
          sizeKey={shown.url}
          onKeyDown={onLightboxKey}
        >
          <span className="sr-only" aria-live="polite">
            {time}
          </span>
          <div data-slot="capture-actions" className="mt-2 flex flex-wrap items-center justify-center gap-2">
            <Button variant="secondary" size="sm" onClick={() => void copyCapture(shown.url)}>
              <ImageIcon aria-hidden />
              {th.frames.copyImage}
            </Button>
            <Button variant="secondary" size="sm" onClick={() => void downloadCapture(shown)}>
              <Download aria-hidden />
              {th.frames.downloadFrame}
            </Button>
            <Button
              variant="secondary"
              size="sm"
              onClick={() => window.open(youtubeWatchUrl(videoId, shown.tMs), "_blank", "noopener,noreferrer")}
            >
              <ExternalLink aria-hidden />
              {th.frames.openYoutubeAt}
            </Button>
            <Button
              variant="secondary"
              size="sm"
              onClick={() => {
                captureStore.closeView()
                playerActions.playFrom(shown.tMs)
              }}
            >
              <Play aria-hidden />
              {th.frames.playFrom}
            </Button>
            <Button variant="destructive" size="sm" onClick={() => setConfirming(shown)}>
              <Trash2 aria-hidden />
              {th.capture.delete}
            </Button>
          </div>
        </Lightbox>
      )}
      <AlertDialog open={confirming !== null} onOpenChange={(open) => !open && !deleting && setConfirming(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>{th.capture.deleteConfirm}</AlertDialogTitle>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel disabled={deleting}>{th.capture.cancel}</AlertDialogCancel>
            <AlertDialogAction variant="destructive" disabled={deleting} onClick={() => void confirmDelete()}>
              <Trash2 aria-hidden />
              {th.capture.deleteAction}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </section>
  )
}
```

- [ ] **Step 6: Verify** — `cd "$WORKTREE/web" && npm run typecheck && npm run lint && npm test` (all pass; react-hooks v7 rules: no `Date.now()` in render (the clock lives in `useNowWhile`), refs read only in callbacks/effects).

- [ ] **Step 7: Commit**
```bash
cd "$WORKTREE" && git add web/src/pages/video/capture && git commit -F- <<'EOF'
feat(web): M5-B2 capture module (api, model, single-flight store, button, menu item, strip with lightbox actions and delete)

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
EOF
```

### Task 9: Theater layout in the W2 header (hook, toggle, CSS, e2e)

**Files:**
- Create: `web/src/pages/video/use-theater.ts`, `web/src/pages/video/theater-toggle.tsx`, `web/e2e/theater.spec.ts`
- Modify: `web/src/pages/video/header.tsx`, `web/src/pages/video/player/player-slot.tsx`, `web/src/index.css`, `web/playwright.config.ts`

**Interfaces:**
- Consumes: C5 (T5), C4 `th.theater.*` (T4), `usePlayerValue` (`player/player-store.ts:190-196`), `useNarrowScreen`, `useSlotInView`, `flushSync` from `react-dom`.
- Produces: C9 exactly (`PlayerSlot` `portrait`/`onPlay`, `PlayerControls` `actions`, `data-slot="video-header"`/`data-layout`/`data-slot="video-info"`, `data-slot="theater-toggle"`, `data-slot="player-actions"`).

- [ ] **Step 1: Write the e2e spec (runs at gate 2 / final gate, not in the lane)** — create `web/e2e/theater.spec.ts`:
```ts
/// <reference lib="dom" />
import AxeBuilder from "@axe-core/playwright"
import { expect, test, type Page } from "@playwright/test"

import { fakeYTLog, installFakeYT } from "./fake-yt"

/**
 * M5 รอบ B2 โหมดโรงภาพยนตร์ (spec 1): กด ▶ แล้วขยาย · ปุ่ม/T สลับ · จำค่าข้ามคลิป · คลิปแนวตั้ง · จอแคบ · ลดการเคลื่อนไหว
 * ตัวเล่นปลอม (installFakeYT) ไม่ต่อยูทูปจริง ไม่สร้างงาน · ไฟล์นี้ล้างค่า "0" ที่ project chromium ตั้งไว้ (playwright.config)
 * เพื่อทดสอบค่าเริ่มต้นจริง (ไม่มีค่า = โรงภาพยนตร์)
 */
test.use({ storageState: { cookies: [], origins: [] } })

const BBB = "aqz-KE-bpKQ" // 635 วิ แนวนอน สูงสุด 3840x2160
const THAI = "88o5Sk8_m1Y"

const header = (page: Page) => page.locator('[data-slot="video-header"]')
const slot = (page: Page) => page.locator('[data-slot="player-slot"]')
const iframe = (page: Page) => page.locator('[data-slot="player-host"] iframe')
const toggle = (page: Page) => page.locator('[data-slot="theater-toggle"]')
const heading = (page: Page) => page.getByRole("heading", { level: 1 })
const dock = (page: Page) => page.getByRole("region", { name: "ตัวเล่นคลิป (ลอย)" })
const stored = (page: Page) => page.evaluate(() => window.localStorage.getItem("yt-toolkit:theater"))

/** นับครั้งที่เรียก document.startViewTransition (ต้องติดตั้งก่อน goto) */
async function countTransitions(page: Page) {
  await page.addInitScript(() => {
    const w = window as unknown as { __vt: number }
    w.__vt = 0
    if (typeof document.startViewTransition !== "function") return
    const original = document.startViewTransition.bind(document)
    document.startViewTransition = ((update?: ViewTransitionUpdateCallback) => {
      w.__vt += 1
      return original(update)
    }) as typeof document.startViewTransition
  })
}
const transitions = (page: Page) => page.evaluate(() => (window as unknown as { __vt: number }).__vt)

async function open(page: Page, videoId: string) {
  await installFakeYT(page, { durationS: 635, rate: 0.001 })
  await page.goto(`/v/${videoId}`)
  await expect(heading(page)).not.toBeEmpty()
}

/** กด ▶ ในช่องตัวเล่น แล้วรอจนตัวเล่นปลอมเล่นอยู่ */
async function play(page: Page) {
  await page.getByRole("button", { name: "เล่นคลิป", exact: true }).click()
  await expect(iframe(page)).toHaveCount(1)
  await expect.poll(async () => (await fakeYTLog(page)).calls).toContain("play")
}

/** ข้อมูลคลิปจาก backend โหมด fake แต่สลับกว้าง/สูง: คลิปกลายเป็นแนวตั้ง */
async function asPortrait(page: Page, videoId: string) {
  await page.route(
    (url) => url.pathname === `/api/videos/${videoId}`,
    async (route) => {
      const response = await route.fetch()
      const body = (await response.json()) as { video: { width?: number; height: number }[] }
      const video = body.video.map((f) => (f.width ? { ...f, width: f.height, height: f.width } : f))
      await route.fulfill({ response, json: { ...body, video } })
    },
  )
}

async function seriousViolations(page: Page) {
  const results = await new AxeBuilder({ page }).analyze()
  return results.violations.filter((v) => v.impact === "serious" || v.impact === "critical").map((v) => v.id)
}

test("▶ ขยายเต็มความกว้างโดยไม่โหลดตัวเล่นใหม่ · ปุ่มและปุ่ม T สลับ · จำค่าไว้", async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 900 })
  await countTransitions(page)
  await open(page, BBB)
  await expect(header(page)).toHaveAttribute("data-layout", "compact")
  await expect(toggle(page)).toHaveCount(0)
  expect((await slot(page).boundingBox())?.width ?? 0).toBeLessThan(300)

  await play(page)
  await expect(header(page)).toHaveAttribute("data-layout", "theater-wide")
  await expect.poll(async () => (await slot(page).boundingBox())?.width ?? 0).toBeGreaterThan(900)
  const slotBox = (await slot(page).boundingBox())!
  expect((await heading(page).boundingBox())!.y).toBeGreaterThan(slotBox.y + slotBox.height)
  await expect(toggle(page)).toHaveText("ย่อตัวเล่น (T)")
  await expect(toggle(page)).toHaveAttribute("aria-pressed", "true")
  expect(await transitions(page)).toBeGreaterThan(0)
  await toggle(page).hover()
  await expect(page.getByText("โหมดโรงภาพยนตร์", { exact: true })).toBeVisible()

  await iframe(page).evaluate((node) => node.setAttribute("data-marker", "same"))
  await heading(page).click()
  await page.keyboard.press("t")
  await expect(header(page)).toHaveAttribute("data-layout", "compact")
  await expect(toggle(page)).toHaveText("ขยายตัวเล่น (T)")
  await expect(toggle(page)).toHaveAttribute("aria-pressed", "false")
  expect(await stored(page)).toBe("0")
  await toggle(page).click()
  await expect(header(page)).toHaveAttribute("data-layout", "theater-wide")
  expect(await stored(page)).toBe("1")
  // สลับไปมาแล้วยังเป็น iframe ตัวเดิม (ไม่ถูกสร้างใหม่ ไม่โหลดใหม่)
  await expect(iframe(page)).toHaveAttribute("data-marker", "same")
  expect((await fakeYTLog(page)).players).toBe(1)
})

test("ค่าที่จำไว้ใช้กับทุกคลิป · เปิดคลิปอื่นเริ่มแบบปกติจนกว่าจะกด ▶", async ({ page }) => {
  await open(page, BBB)
  await play(page)
  await toggle(page).click()
  await expect(header(page)).toHaveAttribute("data-layout", "compact")

  await open(page, THAI)
  await expect(header(page)).toHaveAttribute("data-layout", "compact")
  await play(page)
  await expect(header(page)).toHaveAttribute("data-layout", "compact")
  await toggle(page).click()
  await expect(header(page)).toHaveAttribute("data-layout", "theater-wide")

  await open(page, BBB)
  await expect(header(page)).toHaveAttribute("data-layout", "compact")
  await play(page)
  await expect(header(page)).toHaveAttribute("data-layout", "theater-wide")
})

test("ปุ่ม T ไม่ทำงานตอนพิมพ์ในช่อง มีกล่องเปิดอยู่ หรือกด Alt · Shift+T ใช้ได้", async ({ page }) => {
  await installFakeYT(page, { durationS: 635, rate: 0.001 })
  await page.goto(`/v/${BBB}?tab=video`)
  await play(page)
  await expect(header(page)).toHaveAttribute("data-layout", "theater-wide")

  await page.getByRole("button", { name: "ตัวเลือกขั้นสูง", exact: true }).click()
  await page.getByRole("tabpanel").getByRole("textbox", { name: "เริ่ม", exact: true }).click()
  await page.keyboard.press("t")
  await expect(header(page)).toHaveAttribute("data-layout", "theater-wide")

  await heading(page).click()
  await page.keyboard.press("Alt+t")
  await expect(header(page)).toHaveAttribute("data-layout", "theater-wide")

  await page.getByRole("button", { name: "ดูภาพปก", exact: true }).click()
  await expect(page.getByRole("dialog")).toBeVisible()
  await page.keyboard.press("t")
  await expect(header(page)).toHaveAttribute("data-layout", "theater-wide")
  await page.keyboard.press("Escape")
  await expect(page.getByRole("dialog")).toHaveCount(0)

  await page.keyboard.press("Shift+KeyT")
  await expect(header(page)).toHaveAttribute("data-layout", "compact")
})

test("คลิปแนวตั้ง: ตัวเล่นสูง 80% ของจอทางซ้าย ข้อมูลและแถวใต้ตัวเล่นอยู่ทางขวา", async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 900 })
  await asPortrait(page, BBB)
  await open(page, BBB)
  await play(page)
  await expect(header(page)).toHaveAttribute("data-layout", "theater-tall")
  await expect.poll(async () => Math.round((await slot(page).boundingBox())?.height ?? 0)).toBe(720)
  const box = (await slot(page).boundingBox())!
  expect(box.width / box.height).toBeCloseTo(9 / 16, 2)
  const title = (await heading(page).boundingBox())!
  expect(title.x).toBeGreaterThan(box.x + box.width - 1)
  expect(title.y).toBeLessThan(box.y + box.height)
  const bar = (await page.getByRole("slider", { name: "ตำแหน่งในคลิป" }).boundingBox())!
  expect(bar.x).toBeGreaterThan(box.x + box.width - 1)
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth)).toBe(true)
})

test("จอแคบ 600 px: แบบปกติเสมอ ไม่มีปุ่ม และปุ่ม T ไม่ทำงาน", async ({ page }) => {
  await page.setViewportSize({ width: 600, height: 800 })
  await open(page, BBB)
  await play(page)
  await expect(header(page)).toHaveAttribute("data-layout", "compact")
  await expect(toggle(page)).toHaveCount(0)
  await heading(page).click()
  await page.keyboard.press("t")
  await expect(header(page)).toHaveAttribute("data-layout", "compact")
  expect(await stored(page)).toBeNull()
})

test("ลดการเคลื่อนไหว: เลย์เอาต์เหมือนกันแต่ไม่มี view transition", async ({ page }) => {
  await page.emulateMedia({ reducedMotion: "reduce" })
  await countTransitions(page)
  await open(page, BBB)
  await play(page)
  await expect(header(page)).toHaveAttribute("data-layout", "theater-wide")
  await toggle(page).click()
  await expect(header(page)).toHaveAttribute("data-layout", "compact")
  expect(await transitions(page)).toBe(0)
})

test("ตัวเล่นลอยในโหมดโรงภาพยนตร์ · T สลับได้ระหว่างลอยโดยไม่มีแอนิเมชัน", async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 800 })
  await countTransitions(page)
  await open(page, BBB)
  await play(page)
  await expect(header(page)).toHaveAttribute("data-layout", "theater-wide")
  const before = await transitions(page)
  await expect.poll(() => page.evaluate(() => document.documentElement.scrollHeight - window.innerHeight)).toBeGreaterThan(1500)
  await page.evaluate(() => window.scrollTo(0, 2000))
  await expect(dock(page)).toBeVisible()
  await page.keyboard.press("t")
  await expect(header(page)).toHaveAttribute("data-layout", "compact")
  expect(await transitions(page)).toBe(before)
  expect((await fakeYTLog(page)).players).toBe(1)
})

for (const scheme of ["light", "dark"] as const) {
  test(`axe ไม่มีปัญหาร้ายแรงในโหมดโรงภาพยนตร์ (${scheme}) · 640 px ไม่ล้นแนวนอน`, async ({ page }) => {
    await page.emulateMedia({ colorScheme: scheme })
    await page.setViewportSize({ width: 640, height: 800 })
    await open(page, BBB)
    await play(page)
    await expect(header(page)).toHaveAttribute("data-layout", "theater-wide")
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth)).toBe(true)
    expect(await seriousViolations(page)).toEqual([])
  })
}
```

- [ ] **Step 2: Keep the existing chromium specs on the compact header** — in `web/playwright.config.ts`, replace the `use` of the `chromium` project with:
```ts
      use: {
        ...devices["Desktop Chrome"],
        baseURL: `http://127.0.0.1:${PORT}`,
        // M5 รอบ B2: spec เดิมกด ▶ แล้วตรวจหัวคลิปแบบปกติ จึงจำค่า "แบบปกติ" ไว้ก่อน
        // theater.spec.ts และ capture.spec.ts ตั้งค่าที่เก็บเอง (test.use storageState)
        storageState: {
          cookies: [],
          origins: [{ origin: `http://127.0.0.1:${PORT}`, localStorage: [{ name: "yt-toolkit:theater", value: "0" }] }],
        },
      },
```
(the `queue` project keeps the real default: theater).

- [ ] **Step 3: Implement the hook and the toggle**

`web/src/pages/video/use-theater.ts`:
```ts
import { useCallback, useEffect, useReducer } from "react"
import { flushSync } from "react-dom"

import { usePlayerValue } from "./player/player-store"
import {
  headerLayout,
  isTheaterOn,
  prefersReducedMotion,
  readTheaterPreference,
  runLayoutTransition,
  safeStorage,
  theaterKeyAllowed,
  theaterReducer,
  writeTheaterPreference,
  type HeaderLayout,
  type TheaterAction,
} from "./theater"

/** กล่องหรือเมนูที่เปิดอยู่ (Base UI ถอดออกจาก DOM เมื่อปิด) ปุ่ม T ต้องไม่ทำงานระหว่างนั้น */
const OVERLAYS = '[role="dialog"], [role="alertdialog"], [role="menu"], [role="listbox"]'

/**
 * โหมดโรงภาพยนตร์ของหัวคลิป (M5 รอบ B2 spec 1): เลย์เอาต์ที่ใช้ ปุ่มสลับ และปุ่ม T
 * - กด ▶ ในช่องตัวเล่น (onPlayPressed): ค่าที่จำไว้เป็นโรงภาพยนตร์ (ค่าเริ่มต้น) = ขยาย
 * - toggle (ปุ่มหรือ T): สลับแล้วจำค่าไว้ใน localStorage ใช้ครั้งถัดไปที่กด ▶ ทุกคลิป
 * - เปิดคลิปอื่น = แบบปกติจนกว่าจะกด ▶ · จอแคบ = แบบปกติเสมอ ไม่มีปุ่ม T ไม่ทำงาน
 * - สลับผ่าน View Transition (flushSync ให้ DOM ใหม่พร้อมก่อนจับภาพ) ยกเว้นลดการเคลื่อนไหวหรือตัวเล่นลอยอยู่
 */
export function useTheater(o: { videoId: string | null; portrait: boolean; narrow: boolean; inView: boolean }): {
  layout: HeaderLayout
  on: boolean
  canToggle: boolean
  toggle: () => void
  onPlayPressed: () => void
} {
  const { videoId, portrait, narrow, inView } = o
  const [state, dispatch] = useReducer(theaterReducer, { videoId: null, on: false })
  const on = videoId !== null && isTheaterOn(state, videoId)
  const started = usePlayerValue((s) => videoId !== null && s.videoId === videoId && s.started)
  const canToggle = started && !narrow
  const layout = headerLayout({ on, narrow, portrait })

  const change = useCallback(
    (action: TheaterAction) => {
      runLayoutTransition(() => flushSync(() => dispatch(action)), {
        doc: document,
        animate: !narrow && inView && !prefersReducedMotion(),
      })
    },
    [narrow, inView],
  )

  const toggle = useCallback(() => {
    if (videoId === null) return
    writeTheaterPreference(safeStorage(), !on)
    change({ type: "toggle", videoId })
  }, [videoId, on, change])

  const onPlayPressed = useCallback(() => {
    if (videoId === null) return
    const preference = readTheaterPreference(safeStorage())
    const action: TheaterAction = { type: "play", videoId, preference }
    if (preference && !on && !narrow) change(action)
    else dispatch(action)
  }, [videoId, on, narrow, change])

  useEffect(() => {
    if (!canToggle) return
    const onKey = (event: KeyboardEvent) => {
      if (!theaterKeyAllowed(event, { canToggle, overlayOpen: document.querySelector(OVERLAYS) !== null })) return
      event.preventDefault()
      toggle()
    }
    window.addEventListener("keydown", onKey)
    return () => window.removeEventListener("keydown", onKey)
  }, [canToggle, toggle])

  return { layout, on, canToggle, toggle, onPlayPressed }
}
```
`web/src/pages/video/theater-toggle.tsx`:
```tsx
import { Expand, Shrink } from "lucide-react"

import { Button } from "@/components/ui/button"
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip"
import { th } from "@/i18n/th"

/**
 * ปุ่ม "ขยายตัวเล่น (T)" / "ย่อตัวเล่น (T)" ในแถวใต้ตัวเล่น (M5 รอบ B2 spec 1.1) aria-pressed = อยู่ในโหมดโรงภาพยนตร์
 * tooltip "โหมดโรงภาพยนตร์" · มีเฉพาะหลังเริ่มเล่นและจอไม่แคบ (หัวคลิปตัดสิน)
 */
export function TheaterToggle({ on, onToggle }: { on: boolean; onToggle: () => void }) {
  return (
    <Tooltip>
      <TooltipTrigger
        render={
          <Button
            variant="outline"
            size="sm"
            aria-pressed={on}
            aria-keyshortcuts="T"
            data-slot="theater-toggle"
            onClick={onToggle}
          />
        }
      >
        {on ? <Shrink aria-hidden /> : <Expand aria-hidden />}
        {on ? th.theater.collapse : th.theater.expand}
      </TooltipTrigger>
      <TooltipContent>{th.theater.tooltip}</TooltipContent>
    </Tooltip>
  )
}
```

- [ ] **Step 4: Player slot props** (`web/src/pages/video/player/player-slot.tsx`)

1. Import: `import { useCallback, useEffect, useId, useLayoutEffect, useRef, type ReactNode, type RefObject } from "react"`.
2. Replace the `PlayerSlot` signature (from `export function PlayerSlot({` to the line before `const { videoId, thumbnailUrl } = video`) and extend its doc comment:
```tsx
export function PlayerSlot({
  video,
  inView,
  onBox,
  className,
  portrait = false,
  onPlay,
}: {
  video: VideoInfo
  inView: boolean
  onBox?: (node: HTMLDivElement | null) => void
  className?: string
  portrait?: boolean
  onPlay?: () => void
}) {
```
3. Replace the slot `className={cn("relative w-full rounded-md outline-none", failed ? "sm:aspect-video" : "aspect-video", className)}` with:
```tsx
      className={cn(
        "relative rounded-md outline-none",
        portrait ? "aspect-[9/16] h-[min(80vh,760px)]" : cn("w-full", failed ? "sm:aspect-video" : "aspect-video"),
        className,
      )}
```
4. Replace the ▶ button's `onClick={() => playerActions.playFrom()}` with:
```tsx
          onClick={() => {
            onPlay?.()
            playerActions.playFrom()
          }}
```
5. Replace `PlayerControls` and `ControlsRow` (to the end of the file) with:
```tsx
export function PlayerControls({
  video,
  inView,
  className,
  actions,
}: {
  video: VideoInfo
  inView: boolean
  className?: string
  /** ปุ่มเพิ่มต่อท้ายแถวปุ่มใต้ตัวเล่น (M5 รอบ B2: ปุ่มโหมดโรงภาพยนตร์) */
  actions?: ReactNode
}) {
  const storeVideoId = usePlayerValue((s) => s.videoId)
  const status = usePlayerValue((s) => s.status)
  const started = usePlayerValue((s) => s.started)
  const reel = usePlayerValue((s) => s.reel !== null)
  const active = storeVideoId === video.videoId && ACTIVE.has(status)
  const durationMs = Math.max(0, video.durationS) * 1000
  const timeline = durationMs > 0
  // ลอยอยู่ (เริ่มเล่นแล้วแต่ช่องพ้นจอ) = ไม่มีแถวนี้ · เงื่อนไขเดียวกับ docked ของ PlayerSlot
  if (!active || !started || !inView || !(timeline || reel)) return null
  return <ControlsRow video={video} durationMs={timeline ? durationMs : 0} className={className} actions={actions} />
}

function ControlsRow({
  video,
  durationMs,
  className,
  actions,
}: {
  video: VideoInfo
  durationMs: number
  className?: string
  actions?: ReactNode
}) {
  const row = useRef<HTMLDivElement>(null)
  // แถวนี้หายเพราะตัวเล่นลอย (เลื่อนจอลงทั้งที่โฟกัสอยู่ที่แถบ): โฟกัสไป "กลับไปที่หัวคลิป" บนตัวเล่นลอย
  useFocusRescue(row, () => firstSlot(FOCUS_SLOTS.dockBack, FOCUS_SLOTS.cover))
  return (
    <div ref={row} data-slot="player-controls" className={cn("flex flex-col gap-2", className)}>
      {durationMs > 0 && <Timeline durationMs={durationMs} chapters={video.chapters} replayed={video.mostReplayed} visible />}
      <ReelStatus
        buttonClassName="max-sm:h-11"
        // กดหยุด: แถบไทม์ไลน์ในแถวเดียวกัน (ไม่มีแถบ = ปุ่มช่วงไฮไลต์ในแถวปุ่ม) · หายเพราะตัวเล่นลอย: ปุ่มบนตัวเล่นลอย
        fallbackFocus={() =>
          row.current?.querySelector<HTMLElement>('[role="slider"]') ??
          firstSlot(FOCUS_SLOTS.dockBack, FOCUS_SLOTS.reel, FOCUS_SLOTS.cover)
        }
      />
      {/* แถวปุ่มใต้ตัวเล่น (spec C2): ตั้งจุดเริ่ม · ตั้งจุดจบ · ปุ่มเพิ่มจากหัวคลิป ตัดขึ้นบรรทัดได้ */}
      <div data-slot="player-actions" className="flex flex-wrap items-center gap-1">
        <RangeMarkButtons videoId={video.videoId} />
        {actions}
      </div>
    </div>
  )
}
```

- [ ] **Step 5: Header layouts** (`web/src/pages/video/header.tsx`)

1. Imports: after `import { subtitlesQuery } from "./subs-queries"` add
```tsx
import { isPortraitVideo, type HeaderLayout } from "./theater"
import { TheaterToggle } from "./theater-toggle"
```
and before `import { useVideoParams } from "./url-state"` add `import { useTheater } from "./use-theater"`.
2. After the `TOUCH` constant add:
```tsx
/**
 * สามเลย์เอาต์ของหัวคลิป (M5 รอบ B2 spec 1.2) ต้นไม้ของ element เหมือนกันทุกแบบ (รากเดิม → คอลัมน์ตัวเล่น → PlayerSlot ลูกคนแรก)
 * เปลี่ยนแค่ class ช่องตัวเล่นจึงไม่ถูกสร้างใหม่และ iframe ไม่โหลดใหม่ · ไม่ใช้ CSS order (ลำดับ DOM = ลำดับที่ตาเห็น)
 * compact = แบบเดิม (ตัวเล่น 288 px ซ้าย) · theater-wide = ตัวเล่นเต็มความกว้าง ข้อมูลอยู่ใต้ · theater-tall = ตัวเล่นแนวตั้งซ้าย ข้อมูลขวา
 */
const LAYOUTS: Record<HeaderLayout, { root: string; player: string; info: string }> = {
  compact: { root: LAYOUT, player: PLAYER_COLUMN, info: "flex min-w-0 flex-1 flex-col gap-2 max-sm:contents" },
  "theater-wide": { root: "flex flex-col gap-4", player: "flex w-full flex-col gap-2", info: "flex min-w-0 flex-col gap-2" },
  "theater-tall": { root: "flex flex-row items-start gap-4", player: "flex shrink-0 flex-col gap-2", info: "flex min-w-0 flex-1 flex-col gap-2" },
}
```
3. In `VideoHeader`, right after `const narrow = useNarrowScreen()` add (hooks stay above the early returns):
```tsx
  // โหมดโรงภาพยนตร์ (M5 รอบ B2): กด ▶ แล้วขยาย · ปุ่ม/T สลับ · คลิปแนวตั้งได้ตัวเล่นสูงทางซ้าย
  const theater = useTheater({ videoId: videoId ?? null, portrait: data ? isPortraitVideo(data) : false, narrow, inView: slotInView })
```
4. Replace the final `return ( <div className={LAYOUT}> … </div> )` of `VideoHeader` with:
```tsx
  const { layout } = theater
  const tall = layout === "theater-tall"
  const classes = LAYOUTS[layout]
  // แถวใต้ตัวเล่น (ไทม์ไลน์ + ปุ่ม) อยู่ใต้ตัวเล่น ยกเว้นจอแคบ (ใต้ชื่อคลิป) และแนวตั้งในโหมดโรงภาพยนตร์ (ท้ายคอลัมน์ข้อมูล)
  const controls = (className?: string) => (
    <PlayerControls
      key={data.videoId}
      video={data}
      inView={slotInView}
      className={className}
      actions={theater.canToggle ? <TheaterToggle on={theater.on} onToggle={theater.toggle} /> : undefined}
    />
  )
  return (
    <div data-slot="video-header" data-layout={layout} className={classes.root}>
      {/* ช่องตัวเล่น (ปก + ▶ ก่อนเล่น) · key: เปิดคลิปถัดไปแล้วเริ่มใหม่ · ลูกคนแรกของคอลัมน์ตัวเล่นเสมอ (สลับเลย์เอาต์ไม่สร้างใหม่)
          แถวไทม์ไลน์ (หลังกดเล่น): จอกว้างอยู่ใต้ตัวเล่นในคอลัมน์ซ้าย · จอแคบอยู่ใต้ชื่อคลิปเต็มความกว้าง · แนวตั้งท้ายคอลัมน์ข้อมูล
          วางคนละที่ใน DOM (ไม่ใช้ CSS order) ลำดับ Tab และโปรแกรมอ่านหน้าจอจึงตรงกับที่ตาเห็นทุกแบบ */}
      <div className={classes.player}>
        <PlayerSlot
          key={data.videoId}
          video={data}
          inView={slotInView}
          onBox={setSlotBox}
          portrait={tall}
          onPlay={theater.onPlayPressed}
        />
        {!narrow && !tall && controls()}
      </div>
      <div data-slot="video-info" className={classes.info}>
        {/* จอแคบ (< 640 px) ตัดชื่อที่ 3 บรรทัด ไม่ให้ชื่อยาวดันแถบแท็บพ้นจอแรก (review I-3: ชื่อไทย 100 ตัวดันไป 805 px)
            ชื่อเต็มยังอยู่ใน title (ชี้เมาส์) และโปรแกรมอ่านหน้าจออ่านครบ (ตัดแค่ที่ตาเห็น) */}
        <h1
          ref={headingRef}
          tabIndex={-1}
          title={data.title}
          className="text-xl leading-relaxed font-semibold break-words outline-none max-sm:line-clamp-3 max-sm:self-center max-sm:text-lg"
        >
          {data.title}
        </h1>
        {narrow && controls(FULL_ROW)}
        <Meta video={data} trackName={track ? trackLabel(track) : null} />
        <StatTiles video={data} className={FULL_ROW} />
        <div className={`flex flex-wrap items-center gap-2 ${FULL_ROW}`}>
          <NoteButton videoId={data.videoId} trackId={track?.id ?? null} />
          <YoutubeLink videoId={data.videoId} />
          {/* key: เปิดคลิปถัดไปแล้วกล่องภาพปกปิดเสมอ */}
          <CoverButton key={data.videoId} src={data.thumbnailUrl} />
          {/* เฉพาะคลิปที่มีช่วงดูซ้ำบ่อย: อยู่ในแถวปุ่ม (ไม่ใช่ใต้ตัวเล่น) หัวคลิปก่อนเล่นจึงสูงไม่ขึ้นกับ mostReplayed */}
          <ReelButton ranges={data.mostReplayed} />
        </div>
        {tall && controls()}
      </div>
    </div>
  )
```
5. Update the `VideoHeader` doc comment: add the line ` * M5 รอบ B2: สามเลย์เอาต์ (ปกติ / โรงภาพยนตร์แนวนอน / แนวตั้ง) ด้วยต้นไม้ element เดียวกัน (ดู LAYOUTS)`.

- [ ] **Step 6: View-transition CSS** — append to `web/src/index.css`:
```css
/*
 * M5 รอบ B2 โหมดโรงภาพยนตร์: ชื่อ view transition ของช่องตัวเล่นและคอลัมน์ข้อมูลมีเฉพาะระหว่างสลับ
 * (theater.ts ใส่ html[data-theater-switching] แล้วเอาออกเมื่อจบ) ตัวเล่นลอยจึงไม่ถูกกระทบตอนปกติ
 * ราว 300 ms ease-out · ลดการเคลื่อนไหว = ไม่เรียก startViewTransition เลย
 */
html[data-theater-switching] [data-slot="video-header"] [data-slot="player-slot"] {
  view-transition-name: yt-player;
}
html[data-theater-switching] [data-slot="video-info"] {
  view-transition-name: yt-info;
}
::view-transition-group(yt-player),
::view-transition-group(yt-info) {
  animation-duration: 300ms;
  animation-timing-function: cubic-bezier(0, 0, 0.2, 1);
}
```

- [ ] **Step 7: Verify** — `cd "$WORKTREE/web" && npm run typecheck && npm run lint && npm test` (the e2e spec typechecks through `tsconfig.node.json`). Do not run Playwright in the lane; the controller runs `npx playwright test --project=chromium e2e/theater.spec.ts` at gate 2 together with the existing `player.spec.ts`, `range-marks.spec.ts` and `player-sync.spec.ts` (compact geometry must be unchanged thanks to Step 2).

- [ ] **Step 8: Commit**
```bash
cd "$WORKTREE" && git add web/src/pages/video/use-theater.ts web/src/pages/video/theater-toggle.tsx web/src/pages/video/header.tsx web/src/pages/video/player/player-slot.tsx web/src/index.css web/playwright.config.ts web/e2e/theater.spec.ts && git commit -F- <<'EOF'
feat(web): M5-B2 theater mode in the W2 header (layouts, T key, remembered choice, view transition)

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
EOF
```

### Task 10: Settings › ทั่วไป "ความละเอียดภาพที่ถ่าย"

**Files:**
- Modify: `web/src/pages/settings/general-form.ts`, `web/src/pages/settings/general-form.test.ts`, `web/src/pages/settings/general-panel.tsx`, `web/e2e/settings-general.spec.ts`

**Interfaces:**
- Consumes: C4 (`th.general.captureQuality*`, `Settings.captureQuality`), C1 (backend key).
- Produces: C10.

- [ ] **Step 1: Write the failing test** — in `general-form.test.ts` change the import to
```ts
import { CAPTURE_QUALITIES, choicePatch, displayed, languageOptions, outputDirPatch, serverMessage } from "./general-form"
```
and append:
```ts
describe("captureQuality (M5 รอบ B2)", () => {
  it("เลือกค่าอื่นส่งเฉพาะ key นั้น ค่าเดิมไม่ส่ง · ตัวเลือกสามค่าตามลำดับพร้อมชื่อไทย", () => {
    expect(CAPTURE_QUALITIES).toEqual(["max", "1080", "720"])
    expect(choicePatch("captureQuality", "720", SAVED)).toEqual({ captureQuality: "720" })
    expect(choicePatch("captureQuality", "max", SAVED)).toBeNull()
    expect(CAPTURE_QUALITIES.map((q) => th.general.captureQualities[q])).toEqual(["สูงสุดที่มี", "1080p", "720p"])
  })
})
```

- [ ] **Step 2: Run it, expect FAIL** — `cd "$WORKTREE/web" && npx vitest run src/pages/settings/general-form.test.ts` → `CAPTURE_QUALITIES` is not exported / `"captureQuality"` is not a `GeneralKey`.

- [ ] **Step 3: Implement**

`general-form.ts`: replace the `GeneralKey` line (and its comment) with
```ts
/** ค่าที่หน้า "ทั่วไป" แก้ได้ (ทั้งเจ็ดช่อง) */
export type GeneralKey =
  | "outputDir"
  | "concurrency"
  | "audioLanguage"
  | "videoDefault"
  | "audioDefault"
  | "autoSharpFrames"
  | "captureQuality"
```
and after `VIDEO_DEFAULTS` add
```ts
/** M5 รอบ B2 spec 2.4: ความละเอียดภาพที่ถ่าย (เพดานด้านสั้น) เรียงตามที่แสดง */
export const CAPTURE_QUALITIES = ["max", "1080", "720"] as const
```
`general-panel.tsx`: add `CAPTURE_QUALITIES,` to the `./general-form` import; change the skeleton count `{ length: 6 }` to `{ length: 7 }`; insert right before the `<Field>` whose title id is `general-audio`:
```tsx
      {/* M5 รอบ B2 spec 2.4: ความละเอียดของ "ถ่ายภาพคมตรงนี้" (เพดานนับที่ด้านสั้น) */}
      <Field>
        <FieldTitle id="general-capture">{t.captureQuality}</FieldTitle>
        <ChoiceSelect
          labelId="general-capture"
          hintId="general-capture-hint"
          value={shown.captureQuality}
          options={CAPTURE_QUALITIES.map((value) => ({ value, label: t.captureQualities[value] }))}
          onChange={(value) => {
            const next = CAPTURE_QUALITIES.find((q) => q === value)
            if (next) choose(choicePatch("captureQuality", next, shown))
          }}
        />
        <FieldDescription id="general-capture-hint">{t.captureQualityHint}</FieldDescription>
      </Field>

```

- [ ] **Step 4: e2e** — in `web/e2e/settings-general.spec.ts` rename the test `"/settings เปิดที่แท็บทั่วไป พร้อมหกช่อง"` to `"/settings เปิดที่แท็บทั่วไป พร้อมเจ็ดช่อง"`, add after its `คุณภาพวิดีโอเริ่มต้น` assertion
```ts
  await expect(page.getByRole("combobox", { name: "ความละเอียดภาพที่ถ่าย" })).toBeVisible()
```
and append:
```ts
test("ความละเอียดภาพที่ถ่าย: ค่าเริ่มต้นสูงสุดที่มี · เลือก 720p แล้วบันทึกและคงอยู่ (ใช้ค่าจำลอง ไม่เขียน backend)", async ({ page, request }) => {
  const stub = await stubSettings(page, request)
  await page.goto("/settings/general")
  const select = page.getByRole("combobox", { name: "ความละเอียดภาพที่ถ่าย" })
  await expect(select).toContainText("สูงสุดที่มี")
  await expect(page.getByText("ภาพยิ่งละเอียด ตัวหนังสือเล็กในคลิปยิ่งอ่านง่าย ใช้เน็ตต่อภาพมากขึ้น (4K ราว 8 MB)")).toBeVisible()
  await select.click()
  await page.getByRole("option", { name: "720p", exact: true }).click()
  await expect(saved(page)).toBeVisible()
  expect(stub.patches).toEqual([{ captureQuality: "720" }])
  await page.reload()
  await expect(page.getByRole("combobox", { name: "ความละเอียดภาพที่ถ่าย" })).toContainText("720p")
})
```

- [ ] **Step 5: Verify** — `cd "$WORKTREE/web" && npm run typecheck && npm run lint && npm test`.

- [ ] **Step 6: Commit**
```bash
cd "$WORKTREE" && git add web/src/pages/settings/general-form.ts web/src/pages/settings/general-form.test.ts web/src/pages/settings/general-panel.tsx web/e2e/settings-general.spec.ts && git commit -F- <<'EOF'
feat(web): M5-B2 settings select for the capture resolution

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
EOF
```

## Wave 3

### Task 11: Capture API, cache route and app wiring

**Files:**
- Create: `src/yttoolkit/api/captures.py`, `tests/api/test_captures_api.py`
- Modify: `src/yttoolkit/api/videos.py` (`STATUS_BY_CODE`, `_CAPTURE_FILE`, `cache_file`), `src/yttoolkit/app.py` (`AppContext.captures`, router), `tests/api/test_videos_api.py`

**Interfaces:**
- Consumes: C7 (`CaptureService`, `CaptureRejected`, `Capture`, `CAPTURE_FOLDER`), C6 fake clips (`CAPTURE0001`, `CAPTURENO01`, `CAPTUREBOT1`, `CAPTURENET1`), `yt_error_response`, `error_response`, `BAD_REQUEST_MESSAGE`, `VIDEO_ID`, `file_timecode`.
- Produces: C11 exactly.

- [ ] **Step 1: Write the failing tests** — create `tests/api/test_captures_api.py`:
```python
"""API ถ่ายภาพคมตรงจุด (M5 รอบ B2 C11): FakeExtractor (ชิ้นจาก fixture) + FakeMediaTools ไม่ต่อเน็ต ไม่ใช้ ffmpeg"""

from __future__ import annotations

import re
import threading
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

import pytest

from yttoolkit.core.capture import OUTPUT_DIR, CaptureService
from yttoolkit.core.db import Database
from yttoolkit.core.extractor import FakeExtractor
from yttoolkit.core.media import FakeMediaTools
from yttoolkit.core.settings import SettingsStore
from yttoolkit.core.videos import VideoService

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
BBB = "aqz-KE-bpKQ"
CLIP = "CAPTURE0001"
BASE = "http://127.0.0.1:8787"
AUTH = {"X-Toolkit-Token": "test-token", "Origin": BASE}
URL = re.compile(r"/api/cache/(?P<id>[\w-]{11})/captures/(?P<file>c_\d+\.jpg)\?v=\d+")


@dataclass
class Queue:
    paused_until: datetime | None = None
    brakes: list[str] = field(default_factory=list)

    def pause_state(self) -> SimpleNamespace | None:
        return None if self.paused_until is None else SimpleNamespace(until=self.paused_until, reason="E_BOT_CHECK")

    def brake(self, reason: str = "E_BOT_CHECK") -> None:
        self.brakes.append(reason)


class GatedExtractor(FakeExtractor):
    """ตัวปลอมที่รอ gate ก่อนตัดชิ้น (เทสการถ่ายซ้อน)"""

    def __init__(self, root: Path) -> None:
        super().__init__(root)
        self.gate = threading.Event()
        self.started = threading.Event()

    def fetch_frame_piece(self, video_id, t_ms, max_short_side, dest):  # type: ignore[no-untyped-def]
        self.started.set()
        assert self.gate.wait(10)
        return super().fetch_frame_piece(video_id, t_ms, max_short_side, dest)


@pytest.fixture
def api(make_client, tmp_path):
    made: list[Database] = []

    def _api(extractor: FakeExtractor | None = None):
        db = Database(tmp_path / f"app{len(made)}.db")
        db.migrate()
        made.append(db)
        fake = extractor or FakeExtractor(FIXTURES)
        videos = VideoService(db, fake, now=lambda: datetime(2026, 10, 5, 8, tzinfo=UTC))
        settings = SettingsStore(db, tmp_path / "out")
        queue = Queue()
        cache = tmp_path / "cache"
        service = CaptureService(videos, fake, FakeMediaTools(FIXTURES / "media"), cache, settings, queue,
                                 work_root=tmp_path / "work")  # fmt: skip
        client = make_client(videos=videos, extractor=fake, cache_root=cache, captures=service, settings=settings)
        client.queue = queue  # type: ignore[attr-defined]
        client.out = tmp_path / "out"  # type: ignore[attr-defined]
        return client

    yield _api
    for db in made:
        db.close()


def _error(resp) -> dict:
    return resp.json()["error"]


def test_post_creates_then_returns_the_same_capture(api) -> None:
    client = api()
    resp = client.post(f"/api/videos/{BBB}/captures", json={"tMs": 125_400}, headers=AUTH)
    assert resp.status_code == 201
    body = resp.json()
    assert {k: body[k] for k in ("id", "tMs", "width", "height")} == {"id": "c_125400", "tMs": 125_400, "width": 160, "height": 90}
    assert URL.fullmatch(body["url"]) and URL.fullmatch(body["url"])["file"] == "c_125400.jpg"
    again = client.post(f"/api/videos/{BBB}/captures", json={"tMs": 125_400}, headers=AUTH)
    assert again.status_code == 200 and again.json() == body
    assert client.get(f"/api/videos/{BBB}/captures").json() == {"captures": [body]}
    folder = next(client.out.glob(f"*[[]{BBB}[]]")) / OUTPUT_DIR
    assert [p.name for p in folder.iterdir()] == ["frame_00-02-05.jpg"]


def test_capture_images_are_immutable_and_download_by_timecode(api) -> None:
    client = api()
    url = client.post(f"/api/videos/{BBB}/captures", json={"tMs": 125_400}, headers=AUTH).json()["url"]
    image = client.get(url)
    assert image.status_code == 200 and image.headers["content-type"] == "image/jpeg"
    assert image.headers["cache-control"] == "public, max-age=86400, immutable"
    download = client.get(url.split("?")[0] + "?download=1")
    assert download.headers["content-disposition"] == 'attachment; filename="frame_00-02-05.jpg"'
    assert client.get(f"/api/cache/{BBB}/captures/index.json").status_code == 404


@pytest.mark.parametrize(
    "body",
    [{}, {"tMs": "1000"}, {"tMs": 1.5}, {"tMs": True}, {"tMs": -1}, {"tMs": 1000, "extra": 1}, {"tMs": 172_800_001}],
)
def test_post_body_is_strict(api, body) -> None:
    resp = api().post(f"/api/videos/{BBB}/captures", json=body, headers=AUTH)
    assert resp.status_code == 422 and _error(resp)["code"] == "E_BAD_REQUEST"


def test_out_of_range_and_bad_ids(api) -> None:
    client = api()
    late = client.post(f"/api/videos/{BBB}/captures", json={"tMs": 635_000}, headers=AUTH)
    assert late.status_code == 422 and _error(late)["code"] == "E_BAD_REQUEST"
    assert _error(late)["detail"].startswith(BBB)
    for path in ("/api/videos/bad/captures",):
        assert client.get(path).status_code == 422
        assert client.post(path, json={"tMs": 0}, headers=AUTH).json()["error"]["code"] == "E_INVALID_INPUT"


def test_post_requires_the_token(api) -> None:
    assert api().post(f"/api/videos/{BBB}/captures", json={"tMs": 0}).status_code == 403


@pytest.mark.parametrize(
    ("video_id", "status", "code", "message"),
    [
        ("CAPTURENO01", 422, "E_CAPTURE_UNSUPPORTED", 'คลิปนี้ถ่ายภาพคมเฉพาะจุดไม่ได้ ใช้ "ขอภาพคม" ทั้งคลิปแทนได้'),
        ("CAPTURENET1", 502, "E_NETWORK", "เน็ตหลุด ลองใหม่อีกครั้ง"),
        ("CAPTUREBOT1", 429, "E_BOT_CHECK", "ยูทูปขอให้ยืนยันว่าไม่ใช่บอท พักคิวไว้ 10 นาทีก่อนนะ"),
    ],
)
def test_extractor_failures_map_to_their_status(api, video_id, status, code, message) -> None:
    client = api()
    resp = client.post(f"/api/videos/{video_id}/captures", json={"tMs": 1_000}, headers=AUTH)
    assert resp.status_code == status
    assert (_error(resp)["code"], _error(resp)["message"]) == (code, message)
    assert client.queue.brakes == (["E_BOT_CHECK"] if code == "E_BOT_CHECK" else [])  # พักคิวครั้งเดียว (จาก service)
    assert client.get(f"/api/videos/{video_id}/captures").json() == {"captures": []}


def test_paused_queue_is_409_with_the_time(api) -> None:
    client = api()
    client.queue.paused_until = datetime(2026, 10, 5, 10, 10, tzinfo=UTC)
    resp = client.post(f"/api/videos/{BBB}/captures", json={"tMs": 1_000}, headers=AUTH)
    assert resp.status_code == 409
    assert _error(resp) == {"code": "E_QUEUE_PAUSED", "message": "พักการโหลดอยู่เพราะยูทูปขอตรวจสอบ ลองใหม่หลัง 17:10",
                            "detail": "queue paused by a bot check"}  # fmt: skip


def test_post_while_busy_is_409(api) -> None:
    fake = GatedExtractor(FIXTURES)
    client = api(fake)
    client.get(f"/api/videos/{BBB}")  # probe ก่อน (ให้ VideoService มีข้อมูลคลิป)
    results: dict[str, int] = {}
    worker = threading.Thread(
        target=lambda: results.setdefault(
            "first", client.post(f"/api/videos/{BBB}/captures", json={"tMs": 1_000}, headers=AUTH).status_code))
    worker.start()
    assert fake.started.wait(5)
    busy = client.post(f"/api/videos/{BBB}/captures", json={"tMs": 2_000}, headers=AUTH)
    assert busy.status_code == 409 and _error(busy) == {
        "code": "E_CAPTURE_BUSY", "message": "กำลังถ่ายภาพอื่นอยู่ รอสักครู่", "detail": "another capture is running"}
    fake.gate.set()
    worker.join(10)
    assert results["first"] == 201


def test_delete_then_404(api) -> None:
    client = api()
    capture = client.post(f"/api/videos/{BBB}/captures", json={"tMs": 1_000}, headers=AUTH).json()
    resp = client.delete(f"/api/videos/{BBB}/captures/{capture['id']}", headers=AUTH)
    assert resp.status_code == 204 and resp.content == b""
    assert client.get(f"/api/videos/{BBB}/captures").json() == {"captures": []}
    assert client.delete(f"/api/videos/{BBB}/captures/{capture['id']}", headers=AUTH).status_code == 404
    assert client.delete(f"/api/videos/{BBB}/captures/x", headers=AUTH).status_code == 404
    assert client.delete(f"/api/videos/{BBB}/captures/c_1000").status_code == 403


def test_reveal_opens_the_capture_folder(api, fake_platform) -> None:
    client = api()
    assert client.post(f"/api/videos/{CLIP}/captures/reveal", headers=AUTH).status_code == 404
    client.post(f"/api/videos/{CLIP}/captures", json={"tMs": 1_000}, headers=AUTH)
    resp = client.post(f"/api/videos/{CLIP}/captures/reveal", headers=AUTH)
    assert resp.status_code == 200 and resp.json() == {"ok": True}
    assert fake_platform.opened == [client.out / f"คลิปถ่ายภาพคม [{CLIP}]" / OUTPUT_DIR]
    assert client.post("/api/videos/bad/captures/reveal", headers=AUTH).status_code == 404


def test_no_captures_router_without_the_service(make_client) -> None:
    assert make_client().get(f"/api/videos/{BBB}/captures").status_code == 404
```
and append to `tests/api/test_videos_api.py`:
```python
def test_cache_serves_capture_files_immutable_with_a_timecode_name(api):  # M5 รอบ B2
    client = api()
    folder = client.cache_root / BBB / "captures"
    folder.mkdir(parents=True)
    Image.new("RGB", (32, 18)).save(folder / "c_3725900.jpg", "JPEG")
    resp = client.get(f"/api/cache/{BBB}/captures/c_3725900.jpg?download=1")
    assert resp.status_code == 200 and resp.headers["cache-control"] == "public, max-age=86400, immutable"
    assert resp.headers["content-disposition"] == 'attachment; filename="frame_01-02-05.jpg"'
    (folder / "other.jpg").write_bytes((folder / "c_3725900.jpg").read_bytes())
    assert "cache-control" not in client.get(f"/api/cache/{BBB}/captures/other.jpg").headers


def test_capture_codes_have_their_http_status():  # M5 รอบ B2 C11
    from yttoolkit.api.videos import STATUS_BY_CODE

    assert {code: STATUS_BY_CODE[code] for code in (
        "E_CAPTURE_UNSUPPORTED", "E_CAPTURE_BUSY", "E_QUEUE_PAUSED", "E_FFMPEG_MISSING", "E_DISK_FULL",
        "E_OUTPUT_NOT_WRITABLE")} == {
        "E_CAPTURE_UNSUPPORTED": 422, "E_CAPTURE_BUSY": 409, "E_QUEUE_PAUSED": 409, "E_FFMPEG_MISSING": 409,
        "E_DISK_FULL": 507, "E_OUTPUT_NOT_WRITABLE": 409}  # fmt: skip
```

- [ ] **Step 2: Run them, expect FAIL**

Run: `cd "$WORKTREE" && uv run pytest tests/api/test_captures_api.py tests/api/test_videos_api.py -q -W error -p no:cacheprovider`
Expected: FAIL (`AppContext` has no field `captures` → `make_client(captures=…)` sets an unused attribute and every route is 404; `STATUS_BY_CODE` misses the new codes).

- [ ] **Step 3: Implement** — create `src/yttoolkit/api/captures.py`:
```python
"""API ถ่ายภาพคมตรงจุด (M5 รอบ B2 สัญญา C11): รายการ ถ่าย ลบ และเปิดโฟลเดอร์ ภาพที่ถ่าย

route เป็น `def` ธรรมดา (โหลดชิ้นวิดีโอ เรียก ffmpeg เขียนไฟล์) FastAPI จึงส่งไปรันใน threadpool
ไม่ผ่านคิว (E1) · ยูทูปขอยืนยันว่าไม่ใช่บอท = CaptureService พักคิวเองแล้ว route นี้จึงไม่เรียก on_bot_check ซ้ำ
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from fastapi import APIRouter, HTTPException, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, StrictInt

from ..core.capture import CAPTURE_FOLDER, Capture, CaptureRejected
from ..core.inputs import VIDEO_ID
from ..core.yterrors import YtError
from .errors import BAD_REQUEST_MESSAGE, error_response
from .videos import yt_error_response

if TYPE_CHECKING:
    from ..app import AppContext

MAX_CAPTURE_MS = 172_800_000  # 48 ชั่วโมง (ยาวกว่านี้ CaptureService ปฏิเสธด้วยความยาวคลิปอยู่แล้ว)


class CaptureBody(BaseModel):
    """{tMs} อย่างเดียว (spec 3.3) key อื่น / ไม่ใช่จำนวนเต็ม / ติดลบ = 422"""

    model_config = ConfigDict(extra="forbid")
    tMs: StrictInt = Field(ge=0, le=MAX_CAPTURE_MS)


def build_captures_router(ctx: AppContext) -> APIRouter:
    service = ctx.captures
    cache_root = ctx.cache_root
    if service is None or cache_root is None:
        raise ValueError("ต้องมี captures และ cache_root ถึงจะเปิด API ถ่ายภาพคมได้")
    router = APIRouter()

    def item(video_id: str, capture: Capture) -> dict:
        """ภาพหนึ่งภาพในรูปของ API · url ต่อ ?v=<เวลาแก้ไขไฟล์> (ภาพ immutable ถ่ายใหม่ที่เวลาเดิมได้ URL ใหม่)"""
        try:
            version = f"?v={service.cache_path(video_id, capture).stat().st_mtime_ns}"
        except OSError:
            version = ""
        return {
            "id": capture.id,
            "tMs": capture.t_ms,
            "width": capture.width,
            "height": capture.height,
            "url": f"/api/cache/{video_id}/{CAPTURE_FOLDER}/{capture.file}{version}",
        }

    def invalid_id(video_id: str) -> JSONResponse:
        return yt_error_response(YtError("E_INVALID_INPUT", f"video id ไม่ถูกรูปแบบ: {video_id!r}"), "-")

    @router.get("/videos/{video_id}/captures", response_model=None)
    def list_captures(video_id: str) -> dict | JSONResponse:
        if not VIDEO_ID.fullmatch(video_id):
            return invalid_id(video_id)
        return {"captures": [item(video_id, capture) for capture in service.list(video_id)]}

    @router.post("/videos/{video_id}/captures", status_code=201, response_model=None)
    def create_capture(video_id: str, body: CaptureBody, response: Response) -> dict | JSONResponse:
        try:
            capture, created = service.capture(video_id, body.tMs)
        except CaptureRejected as exc:
            return error_response(422, "E_BAD_REQUEST", BAD_REQUEST_MESSAGE, f"{video_id}: {exc.detail}")
        except YtError as exc:
            return yt_error_response(exc, video_id)
        if not created:
            response.status_code = 200  # เวลาเดิมที่ถ่ายไว้แล้ว: คืนภาพเดิม (idempotent)
        return item(video_id, capture)

    @router.delete("/videos/{video_id}/captures/{capture_id}", status_code=204, response_model=None)
    def delete_capture(video_id: str, capture_id: str) -> Response | JSONResponse:
        try:
            service.delete(video_id, capture_id)
        except KeyError:
            raise HTTPException(status_code=404) from None
        except YtError as exc:
            return yt_error_response(exc, video_id)
        return Response(status_code=204)

    @router.post("/videos/{video_id}/captures/reveal")
    def reveal_captures(video_id: str) -> dict:
        folder: Path | None = service.reveal_dir(video_id) if VIDEO_ID.fullmatch(video_id) else None
        if folder is None:
            raise HTTPException(status_code=404)
        (ctx.open_folder or ctx.plat.open_folder)(folder)
        return {"ok": True}

    return router
```
In `src/yttoolkit/api/videos.py`:
1. Import: before `from ..core.comments import PinnedCommentService` add `from ..core.capture import CAPTURE_FOLDER`.
2. `STATUS_BY_CODE`: after `"E_YT_REFUSED": 502,` add
```python
    # M5 รอบ B2 ถ่ายภาพคมตรงจุด (api/captures.py)
    "E_CAPTURE_UNSUPPORTED": 422,
    "E_CAPTURE_BUSY": 409,
    "E_QUEUE_PAUSED": 409,
    "E_FFMPEG_MISSING": 409,
    "E_DISK_FULL": 507,
    "E_OUTPUT_NOT_WRITABLE": 409,
```
3. After `_FRAME_FOLDERS = (STORYBOARD_FOLDER, SHARP_FOLDER)` add
```python
_CAPTURE_FILE = re.compile(r"c_(\d{1,9})\.jpg")  # ภาพคมตรงจุด captures/c_<tMs>.jpg (M5 รอบ B2)
```
4. In `cache_file`, replace the block from `is_frame = …` to the `name = …` line with:
```python
        is_frame = len(parts) == 2 and parts[0] in _FRAME_FOLDERS and _FRAME_FILE.fullmatch(parts[1])
        capture = _CAPTURE_FILE.fullmatch(parts[1]) if len(parts) == 2 and parts[0] == CAPTURE_FOLDER else None
        headers: dict[str, str] = {}
        if is_frame or capture:
            headers["Cache-Control"] = FRAME_CACHE_CONTROL
        if download:
            if capture:
                name = f"frame_{file_timecode(int(capture.group(1)))}.jpg"
            else:
                name = _frame_download_name(target.parent, parts[-1]) if is_frame else parts[-1]
```
In `src/yttoolkit/app.py`:
1. Import `from .api.captures import build_captures_router` (before `from .api.errors import …`) and, inside `if TYPE_CHECKING:`, `from .core.capture import CaptureService`.
2. Add to `AppContext` after `open_folder`:
```python
    # M5 รอบ B2 ถ่ายภาพคมตรงจุด (run_app สร้างให้) ไม่มี = ไม่เปิด API /videos/{id}/captures
    captures: CaptureService | None = None
```
3. In `create_app`, before `if ctx.subtitles is not None:` add
```python
    if ctx.captures is not None:
        app.include_router(build_captures_router(ctx), prefix="/api")
```

- [ ] **Step 4: Run the tests, expect PASS** — same command as Step 2 (21 new tests; the 124 existing video API tests still pass), then `cd "$WORKTREE" && uv run pytest -q -W error -p no:cacheprovider`.

- [ ] **Step 5: Commit**
```bash
cd "$WORKTREE" && git add src/yttoolkit/api/captures.py src/yttoolkit/api/videos.py src/yttoolkit/app.py tests/api/test_captures_api.py tests/api/test_videos_api.py && git commit -F- <<'EOF'
feat(api): M5-B2 capture routes (list, capture, delete, reveal) and immutable capture images

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
EOF
```

### Task 12: Lifecycle wiring

**Files:**
- Modify: `src/yttoolkit/lifecycle.py`, `tests/unit/test_lifecycle.py`

**Interfaces:**
- Consumes: C7 `CaptureService`, C6 `fetch_frame_piece` on both extractors. The `AppContext.captures` field is added by T11 in the same wave, so this lane sets it by attribute assignment (a plain dataclass accepts it before T11 merges; `create_app` reads it after T11 merges), which keeps the two lanes independent.
- Produces: C12.

- [ ] **Step 1: Write the failing tests** — append to `tests/unit/test_lifecycle.py`:
```python
def test_open_services_builds_the_capture_service(paths, fake_platform):  # M5 รอบ B2 C12
    from yttoolkit.core.capture import CaptureService

    services = lifecycle.open_services(paths, fake_platform, fake=True)
    try:
        assert isinstance(services.captures, CaptureService)
        capture, created = services.captures.capture("CAPTURE0001", 1_000)
        assert created and services.captures.list("CAPTURE0001") == [capture]
        assert list((paths.data_root / "output").rglob("frame_00-00-01.jpg"))
        with pytest.raises(YtError) as info:
            services.captures.capture("CAPTUREBOT1", 1_000)
        assert info.value.code == "E_BOT_CHECK"
        assert services.queue.pause_state() is not None  # ยูทูปขอตรวจสอบ = พักคิวจริง
        assert not list(paths.work.glob("capture-*"))
    finally:
        services.db.close()


def test_run_app_puts_the_capture_service_on_the_context(paths, fake_platform, monkeypatch):
    from yttoolkit.core.capture import CaptureService

    code, ctx = _run_capturing_ctx(paths, fake_platform, monkeypatch, fake=True)
    assert code == 0 and isinstance(ctx.captures, CaptureService)


def test_startup_removes_a_capture_left_by_a_crash(paths, fake_platform):
    leftover = paths.work / "capture-0123456789abcdef"
    leftover.mkdir(parents=True)
    (leftover / "piece.mp4").write_bytes(b"half")
    services = lifecycle.open_services(paths, fake_platform, fake=True)
    try:
        lifecycle.recover_jobs(services)
        assert not leftover.exists()
    finally:
        services.db.close()
```

- [ ] **Step 2: Run them, expect FAIL** — `cd "$WORKTREE" && uv run pytest tests/unit/test_lifecycle.py -q -W error -p no:cacheprovider -k capture` → `AttributeError: 'Services' object has no attribute 'captures'`.

- [ ] **Step 3: Implement `lifecycle.py`**
1. Import (keep alphabetical order of the `.core` imports): `from .core.capture import CaptureService`.
2. `Services`: after the `pinned` field add `    captures: CaptureService | None = None  # M5 รอบ B2 ถ่ายภาพคมตรงจุด ส่งต่อเป็น ctx.captures`.
3. In `open_services`, right after `deps.on_bot_check = queue.brake` add:
```python
        # M5 รอบ B2: ถ่ายภาพคมตรงจุดไม่ผ่านคิว แต่เคารพการพักคิว (ยูทูปขอตรวจสอบ) และสั่งพักคิวเองเมื่อเจอ
        captures = CaptureService(
            videos,
            extractor,  # type: ignore[arg-type]  # ทั้งตัวจริงและตัวปลอมมี fetch_frame_piece (C6)
            media,
            paths.cache,
            settings,
            queue,
            work_root=paths.work,
        )
```
and add `captures=captures,` to the `Services(...)` call after `pinned=pinned,`.
4. In `_run_server`, right after the `AppContext(...)` call (before `if fake:`), add:
```python
    # M5 รอบ B2: API ถ่ายภาพคม (create_app เปิด router เมื่อมีค่านี้) ตั้งแบบนี้ lane ของ app.py จึงไม่ชนกัน
    ctx.captures = services.captures
```

- [ ] **Step 4: Run the tests, expect PASS** — same command without `-k` (whole file, 178 tests), then the full suite.

- [ ] **Step 5: Commit**
```bash
cd "$WORKTREE" && git add src/yttoolkit/lifecycle.py tests/unit/test_lifecycle.py && git commit -F- <<'EOF'
feat(app): M5-B2 wire the capture service into open_services and the app context

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
EOF
```

### Task 13: Mount capture in W2 and the mocked capture e2e

**Files:**
- Modify: `web/src/pages/video/header.tsx` (strip placement), `web/src/pages/video/player/player-slot.tsx` (`ControlsRow`, `DockToolbar`), `web/src/pages/video/frames.tsx` (menu item)
- Modify (hard-coded frame-menu lists that gain the new item): `web/e2e/video.spec.ts` (`MENU_ITEMS`), `web/e2e/sharp-grid.spec.ts` (the list in "เมนูคลิกขวาของภาพคมครบทุกรายการ…"), `web/e2e/transcript.spec.ts` (`M2_MENU`, which `MENU_WITH_SUBS` extends)
- Create: `web/e2e/capture.spec.ts`

**Interfaces:**
- Consumes: C8 (`CaptureButton`, `CaptureMenuItem`, `CaptureStrip`, `StripLayout`), C9 (layouts, `controls()` placement from T9).
- Produces: C13.

- [ ] **Step 1: Write the e2e spec (runs at the final gate)** — create `web/e2e/capture.spec.ts`:
```ts
/// <reference lib="dom" />
import path from "node:path"

import AxeBuilder from "@axe-core/playwright"
import { expect, test, type Page } from "@playwright/test"

import type { Capture } from "../src/lib/types"

import { fakeYTLog, installFakeYT } from "./fake-yt"

/**
 * M5 รอบ B2 ถ่ายภาพคมตรงจุด (spec 2): ปุ่มใต้ตัวเล่น ปุ่มบนตัวเล่นลอย เมนูภาพเฟรม แถบ "ภาพที่ถ่ายไว้" ภาพใหญ่ และการลบ
 * โปรเจกต์ chromium: API ถ่ายภาพจำลองด้วย page.route ทั้งหมด (ไม่ถ่ายจริง ไม่ต่อยูทูป) ภาพทุกภาพคือ tests/fixtures/media/cover.jpg
 * หัวคลิปแบบปกติ (ค่าเริ่มต้นของ project) ยกเว้นกลุ่มโรงภาพยนตร์ที่ตั้ง yt-toolkit:theater = "1" เอง
 */

const BBB = "aqz-KE-bpKQ"
const COVER = path.join(import.meta.dirname, "../../tests/fixtures/media/cover.jpg")
const BUTTON = "ถ่ายภาพคมตรงนี้"

const item = (tMs: number): Capture => ({ id: `c_${tMs}`, tMs, width: 1920, height: 1080, url: `/api/cache/${BBB}/captures/c_${tMs}.jpg?v=1` })

type MockOptions = { delayMs?: number; error?: { status: number; code: string; message: string } }
type MockState = { list: Capture[]; posts: number[]; deletes: string[]; reveals: number }

/** จำลอง API ถ่ายภาพของคลิป BBB: รายการ ถ่าย (หน่วงได้ / ตอบ error ได้) ลบ เปิดโฟลเดอร์ และไฟล์ภาพ */
async function mockCaptures(page: Page, initial: Capture[] = [], options: MockOptions = {}): Promise<MockState> {
  const state: MockState = { list: [...initial], posts: [], deletes: [], reveals: 0 }
  await page.route(`**/api/videos/${BBB}/captures`, async (route) => {
    if (route.request().method() === "GET") return route.fulfill({ json: { captures: state.list } })
    const { tMs } = route.request().postDataJSON() as { tMs: number }
    state.posts.push(tMs)
    if (options.delayMs) await new Promise((resolve) => setTimeout(resolve, options.delayMs))
    if (options.error) {
      const { status, code, message } = options.error
      return route.fulfill({ status, json: { error: { code, message, detail: null } } })
    }
    const capture = item(tMs)
    state.list = [...state.list.filter((c) => c.id !== capture.id), capture].sort((a, b) => a.tMs - b.tMs)
    return route.fulfill({ status: 201, json: capture })
  })
  await page.route(`**/api/videos/${BBB}/captures/reveal`, (route) => {
    state.reveals += 1
    return route.fulfill({ json: { ok: true } })
  })
  await page.route(`**/api/videos/${BBB}/captures/c_*`, (route) => {
    const id = new URL(route.request().url()).pathname.split("/").pop() ?? ""
    state.deletes.push(id)
    state.list = state.list.filter((c) => c.id !== id)
    return route.fulfill({ status: 204, body: "" })
  })
  await page.route(`**/api/cache/${BBB}/captures/**`, (route) => route.fulfill({ path: COVER, contentType: "image/jpeg" }))
  return state
}

const captureButton = (page: Page) => page.locator('[data-slot="player-controls"]').getByRole("button", { name: BUTTON })
const stripList = (page: Page) => page.locator('[data-slot="capture-strip"]').getByRole("list")
const tile = (page: Page, clock: string) => stripList(page).getByRole("button", { name: `ภาพเฟรมที่ ${clock}`, exact: true })
const toast = (page: Page, text: string | RegExp) => page.locator("[data-sonner-toast]").filter({ hasText: text })
const dock = (page: Page) => page.getByRole("region", { name: "ตัวเล่นคลิป (ลอย)" })

async function open(page: Page) {
  await installFakeYT(page, { durationS: 635, rate: 0.001 })
  await page.goto(`/v/${BBB}`)
  await expect(page.getByRole("heading", { level: 1 })).not.toBeEmpty()
}

async function play(page: Page) {
  await page.getByRole("button", { name: "เล่นคลิป", exact: true }).click()
  await expect(page.locator('[data-slot="player-host"] iframe')).toHaveCount(1)
  await expect.poll(async () => (await fakeYTLog(page)).calls).toContain("play")
}

async function seriousViolations(page: Page) {
  const results = await new AxeBuilder({ page }).analyze()
  return results.violations.filter((v) => v.impact === "serious" || v.impact === "critical").map((v) => v.id)
}

test("ปุ่มมีหลังเริ่มเล่น · กำลังถ่าย… · toast ดูภาพ · ภาพเข้าแถบ · เวลาปัดทีละ 100 ms", async ({ page }) => {
  const state = await mockCaptures(page, [], { delayMs: 800 })
  await open(page)
  await expect(captureButton(page)).toHaveCount(0)
  await expect(page.locator('[data-slot="capture-strip"]')).toHaveCount(0)
  await play(page)
  const frame = page.getByRole("img", { name: /^ภาพเฟรมที่ / }).nth(2)
  await frame.click({ button: "right" })
  await page.getByRole("menuitem", { name: "เล่นจากตรงนี้" }).click()

  await captureButton(page).click()
  await expect(page.locator('[data-slot="player-controls"]').getByRole("button", { name: "กำลังถ่าย…" })).toBeDisabled()
  await expect(toast(page, /^ถ่ายภาพคมแล้ว · /)).toBeVisible()
  expect(state.posts).toHaveLength(1)
  expect(state.posts[0] % 100).toBe(0)
  await expect(captureButton(page)).toBeEnabled()
  await expect(page.getByRole("heading", { name: "ภาพที่ถ่ายไว้ (1)" })).toBeVisible()
  await expect(stripList(page).getByRole("listitem")).toHaveCount(1)

  await toast(page, /^ถ่ายภาพคมแล้ว · /).getByRole("button", { name: "ดูภาพ" }).click()
  await expect(page.getByRole("dialog")).toBeVisible()
  await expect(page.locator('[data-slot="capture-actions"]').getByRole("button")).toHaveText([
    "คัดลอกภาพ",
    "โหลดภาพนี้",
    "เปิดในยูทูปตรงเวลานี้",
    "เล่นจากตรงนี้",
    "ลบภาพนี้",
  ])
})

test("ภาพใหญ่ ←/→ · ยกเลิกไม่ลบ · ลบหลังยืนยันแล้ว toast และโฟกัสภาพข้างเคียง", async ({ page }) => {
  const state = await mockCaptures(page, [item(1000), item(2000), item(3000)])
  await open(page)
  await expect(page.getByRole("heading", { name: "ภาพที่ถ่ายไว้ (3)" })).toBeVisible()
  await tile(page, "0:02").click()
  await expect(page.getByRole("dialog", { name: "ภาพเฟรมที่ 0:02" })).toBeVisible()
  await page.keyboard.press("ArrowRight")
  const last = page.getByRole("dialog", { name: "ภาพเฟรมที่ 0:03" })
  await expect(last).toBeVisible()

  await last.getByRole("button", { name: "ลบภาพนี้" }).click()
  const confirm = page.getByRole("alertdialog", { name: "ลบภาพนี้ทั้งในแอพและในโฟลเดอร์ไหม" })
  await confirm.getByRole("button", { name: "ยกเลิก" }).click()
  await expect(confirm).toHaveCount(0)
  expect(state.deletes).toEqual([])

  await last.getByRole("button", { name: "ลบภาพนี้" }).click()
  await confirm.getByRole("button", { name: "ลบภาพ", exact: true }).click()
  await expect(toast(page, "ลบภาพแล้ว")).toBeVisible()
  expect(state.deletes).toEqual(["c_3000"])
  await expect(page.getByRole("dialog")).toHaveCount(0)
  await expect(page.getByRole("heading", { name: "ภาพที่ถ่ายไว้ (2)" })).toBeVisible()
  await expect(tile(page, "0:02")).toBeFocused()
})

test("แถบมีจุดหยุด Tab เดียว · ลูกศร/Home/End เลื่อน · Enter เปิดภาพใหญ่ · Esc กลับมาที่ภาพเดิม", async ({ page }) => {
  await mockCaptures(page, [item(1000), item(2500), item(3000)])
  await open(page)
  await expect(stripList(page).locator('button[tabindex="0"]')).toHaveCount(1)
  await tile(page, "0:01").focus()
  await page.keyboard.press("ArrowRight")
  await expect(tile(page, "0:02.5")).toBeFocused()
  await page.keyboard.press("End")
  await expect(tile(page, "0:03")).toBeFocused()
  await page.keyboard.press("Home")
  await expect(tile(page, "0:01")).toBeFocused()
  await expect(stripList(page).locator('button[tabindex="0"]')).toHaveCount(1)
  await page.keyboard.press("Enter")
  await expect(page.getByRole("dialog", { name: "ภาพเฟรมที่ 0:01" })).toBeVisible()
  await page.keyboard.press("Escape")
  await expect(tile(page, "0:01")).toBeFocused()
})

test("เมนูคลิกขวาของภาพเฟรม 'ถ่ายภาพคมตรงนี้' ใช้เวลาของภาพ", async ({ page }) => {
  const state = await mockCaptures(page)
  await open(page)
  const storyboard = (await (await page.request.get(`/api/videos/${BBB}/storyboard`)).json()) as { frames: { tMs: number }[] }
  await page.getByRole("img", { name: /^ภาพเฟรมที่ / }).nth(2).click({ button: "right" })
  await page.getByRole("menuitem", { name: BUTTON }).click()
  await expect.poll(() => state.posts).toEqual([Math.round(storyboard.frames[2].tMs / 100) * 100])
  await expect(page.getByRole("heading", { name: "ภาพที่ถ่ายไว้ (1)" })).toBeVisible()
})

test("ตัวเล่นลอยมีปุ่มไอคอน 'ถ่ายภาพคมตรงนี้'", async ({ page }) => {
  const state = await mockCaptures(page)
  await open(page)
  await play(page)
  await expect.poll(() => page.evaluate(() => document.documentElement.scrollHeight - window.innerHeight)).toBeGreaterThan(1200)
  await page.evaluate(() => window.scrollTo(0, 1200))
  await expect(dock(page)).toBeVisible()
  await dock(page).getByRole("button", { name: BUTTON }).click()
  await expect.poll(() => state.posts.length).toBe(1)
})

test("error จาก backend: toast ข้อความไทย ไม่มีภาพในแถบ ปุ่มกลับมากดได้", async ({ page }) => {
  const message = 'คลิปนี้ถ่ายภาพคมเฉพาะจุดไม่ได้ ใช้ "ขอภาพคม" ทั้งคลิปแทนได้'
  await mockCaptures(page, [], { error: { status: 422, code: "E_CAPTURE_UNSUPPORTED", message } })
  await open(page)
  await play(page)
  await captureButton(page).click()
  await expect(toast(page, message)).toBeVisible()
  await expect(page.locator('[data-slot="capture-strip"]')).toHaveCount(0)
  await expect(captureButton(page)).toBeEnabled()
})

test("คิวพักเพราะยูทูปขอตรวจสอบ: ปุ่มกดไม่ได้แต่โฟกัสได้ พร้อมเวลาที่ลองใหม่", async ({ page }) => {
  const state = await mockCaptures(page)
  const until = new Date(Date.now() + 10 * 60_000).toISOString()
  await page.route("**/api/queue", (route) => route.fulfill({ json: { pausedUntil: until, reason: "E_BOT_CHECK", concurrency: 2 } }))
  await open(page)
  await play(page)
  await expect(captureButton(page)).toBeDisabled()
  await captureButton(page).focus()
  await expect(captureButton(page)).toBeFocused()
  await captureButton(page).hover()
  await expect(page.getByText(/^พักการโหลดอยู่เพราะยูทูปขอตรวจสอบ ลองใหม่หลัง \d{2}:\d{2}$/)).toBeVisible()
  await captureButton(page).click({ force: true })
  expect(state.posts).toEqual([])
})

test("คลิปสด: ปุ่มกดไม่ได้พร้อมเหตุผล", async ({ page }) => {
  await mockCaptures(page)
  await page.route(
    (url) => url.pathname === `/api/videos/${BBB}`,
    async (route) => {
      const response = await route.fetch()
      await route.fulfill({ response, json: { ...(await response.json()), isLive: true } })
    },
  )
  await open(page)
  await play(page)
  await expect(captureButton(page)).toBeDisabled()
  await captureButton(page).hover()
  await expect(page.getByText("คลิปสดถ่ายภาพคมไม่ได้", { exact: true })).toBeVisible()
})

test("'เปิดโฟลเดอร์' ขอให้ backend เปิดโฟลเดอร์ ภาพที่ถ่าย", async ({ page }) => {
  const state = await mockCaptures(page, [item(1000)])
  await open(page)
  await page.locator('[data-slot="capture-strip"]').getByRole("button", { name: "เปิดโฟลเดอร์" }).click()
  await expect.poll(() => state.reveals).toBe(1)
})

test.describe("โหมดโรงภาพยนตร์แนวนอน", () => {
  test.beforeEach(async ({ page }) => {
    await page.addInitScript(() => window.localStorage.setItem("yt-toolkit:theater", "1"))
  })

  test("แถบเป็นแถวเดียวเลื่อนได้ หน้าไม่ล้นแนวนอน", async ({ page }) => {
    await page.setViewportSize({ width: 1280, height: 900 })
    await mockCaptures(page, Array.from({ length: 14 }, (_, i) => item((i + 1) * 1000)))
    await open(page)
    await play(page)
    await expect(page.locator('[data-slot="video-header"]')).toHaveAttribute("data-layout", "theater-wide")
    const list = stripList(page)
    const tops = await list.getByRole("listitem").evaluateAll((items) => items.map((li) => Math.round(li.getBoundingClientRect().top)))
    expect(new Set(tops).size).toBe(1)
    expect(await list.evaluate((ul) => ul.scrollWidth > ul.clientWidth)).toBe(true)
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth)).toBe(true)
  })
})

for (const scheme of ["light", "dark"] as const) {
  test(`axe ไม่มีปัญหาร้ายแรง (${scheme}) แถบ + ภาพใหญ่ · 640 px ไม่ล้นแนวนอน`, async ({ page }) => {
    await page.emulateMedia({ colorScheme: scheme })
    await page.setViewportSize({ width: 640, height: 800 })
    await mockCaptures(page, [item(1000), item(125_400)])
    await open(page)
    await play(page)
    await expect(captureButton(page)).toBeVisible()
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth)).toBe(true)
    expect(await seriousViolations(page)).toEqual([])
    await tile(page, "2:05.4").click()
    await expect(page.getByRole("dialog")).toBeVisible()
    expect(await seriousViolations(page)).toEqual([])
  })
}
```

- [ ] **Step 2: Header** (`web/src/pages/video/header.tsx`, after T9)
1. Import before `import { Lightbox } from "./lightbox"`: `import { CaptureStrip, type StripLayout } from "./capture/capture-strip"`.
2. Right before `return (` of `VideoHeader`'s main render (after the `controls` helper) add:
```tsx
  // แถบ "ภาพที่ถ่ายไว้" (M5 รอบ B2 spec 2.3) ต่อจากแถวใต้ตัวเล่นทุกเลย์เอาต์ มีภาพเมื่อไรก็แสดง (ไม่ต้องรอกดเล่น)
  const strip = (stripLayout: StripLayout, className?: string) => (
    <CaptureStrip key={`captures-${data.videoId}`} videoId={data.videoId} layout={stripLayout} className={className} />
  )
```
3. Place it after each `controls(...)`:
```tsx
        {!narrow && !tall && controls()}
        {!narrow && !tall && strip(layout === "theater-wide" ? "row" : "wrap")}
```
```tsx
        {narrow && controls(FULL_ROW)}
        {narrow && strip("wrap", FULL_ROW)}
```
```tsx
        {tall && controls()}
        {tall && strip("wrap")}
```

- [ ] **Step 3: Player slot** (`web/src/pages/video/player/player-slot.tsx`)
1. Import before `import { FOCUS_SLOTS, … } from "./focus-rescue"`: `import { CaptureButton } from "../capture/capture-button"`.
2. In `DockToolbar`, right after `<RangeMarkButtons videoId={videoId} size="xs" />` add:
```tsx
      {/* M5 รอบ B2: ถ่ายภาพคมตรงนี้ (ปุ่มไอคอน ชื่อและ tooltip เดียวกับปุ่มใต้ตัวเล่น) */}
      <CaptureButton videoId={videoId} variant="dock" />
```
3. In `ControlsRow`, between `<RangeMarkButtons videoId={video.videoId} />` and `{actions}` add `<CaptureButton videoId={video.videoId} />`.

- [ ] **Step 4: Frame context menu** (`web/src/pages/video/frames.tsx`)
1. Import before `import { errorMessage } from "./errors"`: `import { CaptureMenuItem } from "./capture/capture-button"`.
2. Right after the `ContextMenuItem` that renders `{t.playFrom}` add:
```tsx
        {/* M5 รอบ B2: ถ่ายภาพคมที่เวลาของภาพนี้ (อยู่ในเมนูที่เปิดเท่านั้น จึงไม่มีตัวนับต่อภาพ) */}
        <CaptureMenuItem videoId={videoId} tMs={frame.tMs} />
```

- [ ] **Step 5: Existing menu lists** — the frame context menu now has "ถ่ายภาพคมตรงนี้" right after "เล่นจากตรงนี้". Insert `"ถ่ายภาพคมตรงนี้",` right after `"เล่นจากตรงนี้",` in: `web/e2e/video.spec.ts` `MENU_ITEMS` (lines 19-28), `web/e2e/transcript.spec.ts` `M2_MENU` (lines 21-30; `MENU_WITH_SUBS` follows automatically) and the `toHaveText([...])` list of `web/e2e/sharp-grid.spec.ts` (line 72-75). `web/e2e/player-sync.spec.ts:148-151` reads items 4 and 5 by index and stays valid (the new item is index 6).

- [ ] **Step 6: Verify** — `cd "$WORKTREE/web" && npm run typecheck && npm run lint && npm test` (Playwright runs at the final gate: `capture.spec.ts` plus the existing `player.spec.ts`, `player-sync.spec.ts`, `range-marks.spec.ts`, `video.spec.ts`, `sharp-grid.spec.ts`, `transcript.spec.ts`).

- [ ] **Step 7: Commit**
```bash
cd "$WORKTREE" && git add web/src/pages/video/header.tsx web/src/pages/video/player/player-slot.tsx web/src/pages/video/frames.tsx web/e2e/capture.spec.ts web/e2e/video.spec.ts web/e2e/sharp-grid.spec.ts web/e2e/transcript.spec.ts && git commit -F- <<'EOF'
feat(web): M5-B2 mount sharp capture (controls row, docked player, frame menu, strip)

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
EOF
```

### Task 14: Queue e2e with the real fake backend

**Files:**
- Create: `web/e2e/queue-capture.spec.ts`

**Interfaces:**
- Consumes: C11 API, C12 wiring, C13 UI, C6 fake clips `CAPTURE0001`/`CAPTUREBOT1`, `installFakeYT`/`fakeYTLog`, `resumeQueue` (`e2e/queue-helpers.ts:127`).
- Produces: the end-to-end proof of spec §6 "one real capture against the fake extractor fixture, through the API, including the folder copy".

- [ ] **Step 1: Write the spec** — create `web/e2e/queue-capture.spec.ts`:
```ts
/// <reference lib="dom" />
import fs from "node:fs"
import path from "node:path"

import { expect, test, type Page } from "@playwright/test"

import { fakeYTLog, installFakeYT } from "./fake-yt"
import { resumeQueue } from "./queue-helpers"

/**
 * M5 รอบ B2 ถ่ายภาพคมตรงจุดกับ backend โหมดปลอมจริง (project queue รันทีละ spec --workers=1):
 * FakeExtractor ตัดชิ้นจาก tests/fixtures/capture/piece.mp4 · FakeMediaTools คัดลอก cover.jpg · ไม่ต่อยูทูป
 * ใช้คลิปปลอม CAPTURE0001 (ถ่ายได้) และ CAPTUREBOT1 (ยูทูปขอตรวจสอบ) เท่านั้น
 * project นี้ไม่มีค่า yt-toolkit:theater ตั้งไว้: กด ▶ แล้วได้โหมดโรงภาพยนตร์ (ค่าเริ่มต้นจริง)
 */

const CLIP = "CAPTURE0001"
const BOT = "CAPTUREBOT1"
const TITLE = "คลิปถ่ายภาพคม"

const captureButton = (page: Page) => page.locator('[data-slot="player-controls"]').getByRole("button", { name: "ถ่ายภาพคมตรงนี้" })
const toast = (page: Page, text: string | RegExp) => page.locator("[data-sonner-toast]").filter({ hasText: text })

async function openAndPlay(page: Page, videoId: string) {
  await installFakeYT(page, { durationS: 635, rate: 0.001 })
  await page.goto(`/v/${videoId}`)
  await page.getByRole("button", { name: "เล่นคลิป", exact: true }).click()
  await expect.poll(async () => (await fakeYTLog(page)).calls).toContain("play")
  await expect(page.locator('[data-slot="video-header"]')).toHaveAttribute("data-layout", "theater-wide")
}

test("ถ่ายจริงกับ backend ปลอม: แถบ ไฟล์ในโฟลเดอร์ของคลิป เวลาเดิมได้ภาพเดิม และลบทั้งสองที่", async ({ page, request }) => {
  await openAndPlay(page, CLIP)
  await captureButton(page).click()
  await expect(toast(page, "ถ่ายภาพคมแล้ว · 0:00")).toBeVisible()
  await expect(page.getByRole("heading", { name: "ภาพที่ถ่ายไว้ (1)" })).toBeVisible()

  const listed = (await (await request.get(`/api/videos/${CLIP}/captures`)).json()) as { captures: { id: string; url: string }[] }
  expect(listed.captures.map((c) => c.id)).toEqual(["c_0"])
  const image = await request.get(listed.captures[0].url)
  expect(image.ok()).toBe(true)
  expect(image.headers()["content-type"]).toBe("image/jpeg")
  const { outputDir } = (await (await request.get("/api/settings")).json()) as { outputDir: string }
  const folder = path.join(outputDir, `${TITLE} [${CLIP}]`, "ภาพที่ถ่าย")
  expect(fs.readdirSync(folder)).toEqual(["frame_00-00-00.jpg"])

  // เวลาเดิม: backend ตอบ 200 พร้อมภาพเดิม ไม่สร้างไฟล์ใหม่
  const again = page.waitForResponse((r) => r.url().endsWith(`/api/videos/${CLIP}/captures`) && r.request().method() === "POST")
  await captureButton(page).click()
  expect((await again).status()).toBe(200)
  await expect(page.getByRole("heading", { name: "ภาพที่ถ่ายไว้ (1)" })).toBeVisible()
  expect(fs.readdirSync(folder)).toEqual(["frame_00-00-00.jpg"])

  await page.locator('[data-slot="capture-strip"]').getByRole("list").getByRole("button").first().click()
  await page.getByRole("dialog").getByRole("button", { name: "ลบภาพนี้" }).click()
  await page.getByRole("alertdialog").getByRole("button", { name: "ลบภาพ", exact: true }).click()
  await expect(toast(page, "ลบภาพแล้ว")).toBeVisible()
  await expect(page.locator('[data-slot="capture-strip"]')).toHaveCount(0)
  expect(fs.readdirSync(folder)).toEqual([])
  expect(((await (await request.get(`/api/videos/${CLIP}/captures`)).json()) as { captures: unknown[] }).captures).toEqual([])
})

test("ยูทูปขอตรวจสอบระหว่างถ่าย: toast และคิวพัก ปุ่มถ่ายภาพปิดพร้อมเหตุผล", async ({ page, request }) => {
  try {
    await openAndPlay(page, BOT)
    await captureButton(page).click()
    await expect(toast(page, "ยูทูปขอให้ยืนยันว่าไม่ใช่บอท พักคิวไว้ 10 นาทีก่อนนะ")).toBeVisible()
    await expect
      .poll(async () => ((await (await request.get("/api/queue")).json()) as { pausedUntil: string | null }).pausedUntil)
      .not.toBeNull()
    await expect(captureButton(page)).toBeDisabled()
    await expect(page.locator('[data-slot="capture-strip"]')).toHaveCount(0)
  } finally {
    await resumeQueue(request) // spec ถัดไปของ project queue ต้องได้คิวที่ไม่พัก
  }
})
```

- [ ] **Step 2: Verify** — `cd "$WORKTREE/web" && npm run typecheck && npm run lint` (the spec runs only at the final gate: `npx playwright test --project=queue --workers=1 e2e/queue-capture.spec.ts`, after T11-T13 are merged and `npm run build` ran).

- [ ] **Step 3: Commit**
```bash
cd "$WORKTREE" && git add web/e2e/queue-capture.spec.ts && git commit -F- <<'EOF'
test(e2e): M5-B2 real capture against the fake backend (strip, folder copy, idempotent, delete, bot check)

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
EOF
```

### Task 15: Docs (PRD, BRD, acceptance) and the network test (written, not run)

**Files:**
- Modify: `PRD.md`, `BRD.md`, `docs/acceptance.md`, `tests/network_videos.toml`, `tests/unit/test_yterrors.py` (`PRD_PENDING` back to empty)
- Create: `tests/network/test_capture_network.py`

**Interfaces:**
- Consumes: everything above (final names, strings, codes, behaviour).
- Produces: docs matching the code (spec §5); a network test Pete can approve and run.

- [ ] **Step 1: PRD.md** — find each anchor with `rg -n` first; edit with the Edit tool (LF kept).
  1. Right after the bullet starting `- **ไม่อยู่ใน M3.5:**` (end of the player section of W2) insert:
```markdown

**โหมดโรงภาพยนตร์และถ่ายภาพคมตรงจุด (M5 รอบ B2 · พิธอนุมัติ 2026-10-05 · BRD #137-#143 · สเปก `docs/superpowers/specs/2026-10-05-m5b2-capture-and-theater-design.md`):**
- **โหมดโรงภาพยนตร์ (E4):** กด ▶ ในช่องตัวเล่น = ตัวเล่นขยายเต็มความกว้างของเนื้อหา (ราว 928 px สัดส่วน 16:9) ตามด้วยแถวใต้ตัวเล่นและแถบ "ภาพที่ถ่ายไว้" แล้วชื่อคลิป ข้อมูล ช่องตัวเลข และแถวปุ่มเดิม · ปุ่ม "ขยายตัวเล่น (T)" / "ย่อตัวเล่น (T)" (aria-pressed, tooltip "โหมดโรงภาพยนตร์") อยู่ในแถวใต้ตัวเล่น มีหลังเริ่มเล่นเท่านั้น · ปุ่ม T/t สลับได้เมื่อไม่ได้พิมพ์ในช่องกรอก ไม่มีกล่อง/เมนูเปิด และไม่กด Ctrl/Alt/Meta · จำค่าใน `localStorage` คีย์ `yt-toolkit:theater` (`"1"`/`"0"` ไม่มีค่า = โรงภาพยนตร์) ใช้ครั้งถัดไปที่กด ▶ ทุกคลิป · เปิดคลิปอื่นเริ่มแบบปกติจนกว่าจะกด ▶ · จอแคบ (< 640 px) ไม่เปลี่ยนอะไร ไม่มีปุ่ม · สลับด้วย View Transition ราว 300 ms (ลดการเคลื่อนไหว ตัวเล่นลอยอยู่ หรือเบราว์เซอร์ไม่มี API = สลับทันที) ตัวเล่นไม่ถูกโหลดใหม่ · ตัวเล่นลอยทำงานเหมือนเดิมทั้งสองแบบ · ลำดับ DOM ตรงกับที่ตาเห็นทุกแบบ
- **คลิปแนวตั้ง (E5):** ตัวเล่นสูง min(80vh, 760 px) สัดส่วน 9:16 ทางซ้าย ชื่อคลิป ข้อมูล แถวใต้ตัวเล่น และแถบภาพที่ถ่ายอยู่ทางขวา · แนวตั้ง = รายการภาพที่สูงที่สุดใน `VideoInfo.video[]` รู้ความกว้างและกว้างน้อยกว่าสูง
- **"ถ่ายภาพคมตรงนี้" (E1, E6):** ปุ่มในแถวใต้ตัวเล่น (ต่อจาก "ตั้งจุดเริ่ม"/"ตั้งจุดจบ") ปุ่มไอคอนบนตัวเล่นลอย และรายการในเมนูคลิกขวาของภาพเฟรม (ใช้เวลาของภาพ) · ใช้เวลาของตัวเล่นปัดทีละ 100 ms · ไม่ผ่านคิว ได้ภาพราว 2-3 วินาทีโดยโหลดแค่ส่วนหัวของไฟล์กับท่อนเดียวที่มีเวลานั้น (ดัชนี `sidx` ของ mp4 ผ่านตัวส่งคำขอของ yt-dlp) · ถ่ายได้ครั้งละภาพทั้งแอพ ระหว่างถ่ายปุ่มขึ้น "กำลังถ่าย…" · เสร็จ = toast "ถ่ายภาพคมแล้ว · {เวลา}" (เวลาละเอียด 0.1 วินาที) ปุ่ม "ดูภาพ" และภาพเข้าแถบ · คลิปสด หรือคิวพักเพราะยูทูปขอตรวจสอบ = ปุ่มกดไม่ได้แต่โฟกัสได้ พร้อม tooltip บอกเหตุผล · เวลาเดิมซ้ำ = ได้ภาพเดิม
- **แถบ "ภาพที่ถ่ายไว้ ({n})" (E3, E7):** ต่อจากแถวใต้ตัวเล่น (โรงภาพยนตร์แนวนอน = แถวเดียวเลื่อนได้ · แบบอื่นตัดขึ้นบรรทัด) ภาพ 16:9 กว้างราว 96 px มีป้ายเวลา เรียงตามเวลา จุดหยุด Tab เดียว ลูกศร/Home/End เลื่อน Enter เปิดภาพใหญ่ · ภาพใหญ่มีปุ่ม "คัดลอกภาพ" "โหลดภาพนี้" "เปิดในยูทูปตรงเวลานี้" "เล่นจากตรงนี้" "ลบภาพนี้" (ยืนยัน "ลบภาพนี้ทั้งในแอพและในโฟลเดอร์ไหม" → "ลบภาพแล้ว") · "เปิดโฟลเดอร์" เปิด `<โฟลเดอร์ของคลิป>/ภาพที่ถ่าย/` · ไม่มีภาพ = ไม่มีแถบ · ภาพอยู่ใน cache ของแอพ (`<cache>/<id>/captures/`) และสำเนาในโฟลเดอร์ (`frame_HH-MM-SS.jpg` วินาทีเดียวกัน `_2`) · ล้าง cache 30 วันลบจากแอพ ไฟล์ในโฟลเดอร์อยู่ต่อ
- **ความละเอียด (E2):** ค่าตั้ง `captureQuality` (ข้อ 6.4) เพดานนับที่ด้านสั้น ภาพได้ความละเอียดเท่าต้นฉบับ ไม่ย่อ
```
  2. In the API table, right after the row starting `| GET | \`/videos/{id}/pinned-comment\`` insert:
```markdown
| GET | `/videos/{id}/captures` | — | (M5 รอบ B2) `{captures:[{id, tMs, width, height, url}]}` เรียงตามเวลา · `id` = `c_<tMs>` · `url` = `/api/cache/{id}/captures/c_<tMs>.jpg?v=<เวลาแก้ไขไฟล์>` (immutable แบบภาพเฟรม · `?download=1` ได้ชื่อ `frame_HH-MM-SS.jpg`) |
| POST | `/videos/{id}/captures` | `{tMs: int}` (เข้มงวด key อื่น = 422) | (M5 รอบ B2) ถ่ายภาพคมที่เวลานั้นทันที ไม่ผ่านคิว: 201 ภาพใหม่ · 200 เวลาเดิมที่ถ่ายไว้แล้ว (คืนภาพเดิม ไม่โหลดอะไร) · 422 `E_BAD_REQUEST` (คลิปสด ไม่รู้ความยาว เวลานอกคลิป) · 422 `E_CAPTURE_UNSUPPORTED` · 409 `E_CAPTURE_BUSY` / `E_QUEUE_PAUSED` / `E_FFMPEG_MISSING` / `E_OUTPUT_NOT_WRITABLE` · 429 `E_BOT_CHECK` (พักคิว) · 502 `E_NETWORK` / `E_YT_REFUSED` · 507 `E_DISK_FULL` |
| DELETE | `/videos/{id}/captures/{captureId}` | — | (M5 รอบ B2) 204 ลบสำเนาในโฟลเดอร์ (เฉพาะไฟล์เดิมใต้โฟลเดอร์ผลลัพธ์ที่บันทึกไว้ ไม่ตามลิงก์ ไฟล์หายไปแล้วก็ได้) แล้วลบจาก cache · ไฟล์ในโฟลเดอร์ลบไม่ได้ = 409 `E_OUTPUT_NOT_WRITABLE` ไม่เปลี่ยนอะไร · ไม่รู้จัก = 404 |
| POST | `/videos/{id}/captures/reveal` | — | (M5 รอบ B2) เปิดโฟลเดอร์ `ภาพที่ถ่าย` ของคลิป (ของภาพล่าสุดที่ไฟล์ยังอยู่ ไม่มีก็ตามค่าตั้งปัจจุบัน) · ยังไม่มีโฟลเดอร์ = 404 |
```
  3. Error table: right after the `E_NO_SHARP_FRAMES` row insert:
```markdown
| `E_CAPTURE_UNSUPPORTED` | คลิปนี้ถ่ายภาพคมเฉพาะจุดไม่ได้ ใช้ "ขอภาพคม" ทั้งคลิปแทนได้ | (M5 รอบ B2) คลิปไม่มี mp4 ภาพอย่างเดียวที่มีดัชนี `sidx` (มีแต่ webm หรือแบบรวมเสียง) · HTTP 422 · ไม่เขียนอะไร |
| `E_CAPTURE_BUSY` | กำลังถ่ายภาพอื่นอยู่ รอสักครู่ | (M5 รอบ B2) มีการถ่ายภาพคมอื่นค้างอยู่ (ถ่ายได้ครั้งละภาพทั้งแอพ) · HTTP 409 |
| `E_QUEUE_PAUSED` | พักการโหลดอยู่เพราะยูทูปขอตรวจสอบ ลองใหม่หลัง <เวลา> | (M5 รอบ B2) คิวพักเพราะ `E_BOT_CHECK` ถ่ายภาพคมไม่ได้จนครบเวลา · `<เวลา>` = นาฬิกา HH:MM (เวลาไทย) · HTTP 409 · ไม่มีเวลาให้เติม = ข้อความของ `E_BOT_CHECK` |
```
  4. Settings table: right after the `autoSharpFrames` row insert:
```markdown
| `captureQuality` | `max` \| `1080` \| `720` | `max` · ความละเอียดของ "ถ่ายภาพคมตรงนี้" (M5 รอบ B2 E2) เพดานนับที่ด้านสั้น (`1080` = คลิปแนวตั้งกว้างไม่เกิน 1080) · ไม่มี format ที่ไม่เกินเพดาน = ใช้ตัวที่ด้านสั้นเล็กที่สุดเหนือเพดาน · ภาพไม่ถูกย่อ (4K ราว 8 MB ต่อภาพ) · หน้าตั้งค่า "ความละเอียดภาพที่ถ่าย": สูงสุดที่มี / 1080p / 720p |
```
- [ ] **Step 2: BRD.md** — append after row `| 136 |` (same 4 columns):
```markdown
| 137 | **ถ่ายภาพคมตรงจุดทันที ไม่ผ่านคิว** ภาพมาราว 2-3 วินาที และลงโฟลเดอร์ของคลิปด้วย (`ภาพที่ถ่าย/`) · M5 รอบ B2 (E1) | ✅ | ผู้ใช้กำลังดูคลิปที่หยุดไว้ทำตาม รอคิวทำให้เสียจังหวะ · ถ่ายได้ครั้งละภาพทั้งแอพและหยุดเมื่อคิวพักเพราะยูทูปขอตรวจสอบ · พิธเลือก "ทันที + ลงโฟลเดอร์ด้วย" 2026-10-05 |
| 138 | **ความละเอียดภาพที่ถ่ายเป็นค่าตั้ง** "สูงสุดที่มี" (ค่าเริ่มต้น ถึง 4K) / 1080p / 720p เพดานนับที่ด้านสั้น ไม่ย่อภาพ · M5 รอบ B2 (E2) | ✅ | ตัวหนังสือเล็กในคลิปสอนใช้งานต้องการความละเอียดสูงสุด (4K ราว 7.5 MB และ 3 วินาทีต่อภาพ ตาม spike) · พิธเลือก 2026-10-05 |
| 139 | **ภาพที่ถ่ายแสดงเป็นแถบใต้ตัวเล่น (ทางเลือก ก.)** · M5 รอบ B2 (E3) | ✅ | เห็นได้ระหว่างดูโดยไม่ต้องสลับแท็บ · พิธเลือก ข. ก่อนแล้วเปลี่ยนเป็น ก. หลังเห็นคู่กับโหมดโรงภาพยนตร์ 2026-10-05 |
| 140 | **โหมดโรงภาพยนตร์** กด ▶ แล้วตัวเล่นขยายเต็มความกว้างแบบมีแอนิเมชัน ข้อมูลคลิปย้ายลงล่าง ปุ่มหรือ T สลับ จำค่าต่อเครื่อง · M5 รอบ B2 (E4) | ✅ | ช่องตัวเล่น 288 px อ่านตัวหนังสือเล็กไม่ออก · แบบเดียวกับโหมดโรงภาพยนตร์ของยูทูป (ปุ่ม T) · ไอเดียของพิธ 2026-10-05 |
| 141 | **คลิปแนวตั้งในโหมดโรงภาพยนตร์** ตัวเล่นสูงราว 80% ของจอทางซ้าย ข้อมูลทางขวา · M5 รอบ B2 (E5) | ✅ | ตัวเล่นแนวตั้งเต็มความกว้างสูงราว 1,650 px และวางกลางจะเสียที่สองข้าง · พิธเลือก 2026-10-05 |
| 142 | **ถ่ายภาพด้วยดัชนี `sidx` ของ mp4 ผ่านตัวส่งคำขอของ yt-dlp** โหลดแค่ส่วนหัวกับท่อนเดียวที่มีเวลานั้น · M5 รอบ B2 (E6) | ✅ | spike 2026-10-05: `--download-sections` ค้าง 5 นาที ffmpeg ต่อสตรีมยูทูปตรง ๆ ค้าง · วิธี sidx ได้ 2.0 MB จาก 258 MB ใน 2.4 วินาที (1080p) และ 7.5 MB จาก 712 MB ใน 3.2 วินาที (4K) ภาพถูกต้อง · คลิปที่ไม่มี mp4 แบบนี้ = `E_CAPTURE_UNSUPPORTED` ชวนไปใช้ "ขอภาพคม" |
| 143 | **ลบภาพที่ถ่ายได้** ลบจากแถบ cache ของแอพ และโฟลเดอร์ของคลิป หลังยืนยัน · ลบเฉพาะไฟล์เดิมที่บันทึกไว้ ไม่ตามลิงก์ · M5 รอบ B2 (E7) | ✅ | หยุดผิดจังหวะบ่อย · ครีมเสนอในดีไซน์ พิธเห็นและอนุมัติ 2026-10-05 |
```
- [ ] **Step 3: docs/acceptance.md** — append after the M5 รอบ B section:
```markdown

## M5 รอบ B2 (ทำบน Windows 10/11 กับยูทูปจริง)
| AC | ขั้นตอน | ผ่าน |
|---|---|---|
| M5B2-THEATER | เปิดคลิปแนวนอน กด ▶: ตัวเล่นขยายเต็มความกว้างแบบมีแอนิเมชัน คลิปเล่นต่อไม่สะดุด ข้อมูลคลิปอยู่ใต้ลงมา · คลิกที่ชื่อคลิปแล้วกด T: ย่อกลับ · ปุ่ม "ย่อตัวเล่น (T)" / "ขยายตัวเล่น (T)" ตรงกับสถานะ · เลื่อนจอลงตัวเล่นลอยมุมจอได้ตามเดิม | ☐ |
| M5B2-REMEMBER | ย่อตัวเล่นแล้วเปิดคลิปอื่น กด ▶: ยังเป็นแบบปกติ · ขยายแล้วปิดเบราว์เซอร์ เปิดใหม่ กด ▶: ขยายเอง | ☐ |
| M5B2-PORTRAIT | เปิดคลิป Shorts กด ▶: ตัวเล่นแนวตั้งสูงราว 80% ของจอทางซ้าย ข้อมูลทางขวา ไม่มีแถบเลื่อนแนวนอน | ☐ |
| M5B2-CAPTURE | คลิปสอนใช้งานที่ตัวหนังสือเล็ก หยุดตรงช่วงระหว่างภาพเฟรมสองภาพ กด "ถ่ายภาพคมตรงนี้": ภาพมาภายในราว 3 วินาที ตรงกับที่หยุด ตัวหนังสืออ่านออก · toast "ถ่ายภาพคมแล้ว · {เวลา}" กด "ดูภาพ" เปิดภาพใหญ่ · มีไฟล์ `frame_HH-MM-SS.jpg` ใน `<โฟลเดอร์ของคลิป>/ภาพที่ถ่าย/` · ถ่ายจากตัวเล่นลอยและจากเมนูคลิกขวาของภาพเฟรมได้ | ☐ |
| M5B2-STRIP | แถบ "ภาพที่ถ่ายไว้ (n)" เรียงตามเวลา · Tab เข้าแถบครั้งเดียว ลูกศรเลื่อน Enter เปิด · ภาพใหญ่: "คัดลอกภาพ" ไปวางใน LINE ได้ · "โหลดภาพนี้" · "เปิดในยูทูปตรงเวลานี้" · "เล่นจากตรงนี้" · "เปิดโฟลเดอร์" เปิดโฟลเดอร์ ภาพที่ถ่าย | ☐ |
| M5B2-DELETE | "ลบภาพนี้" → ยืนยัน: ภาพหายจากแถบและจากโฟลเดอร์ · "ยกเลิก" = ไม่หาย | ☐ |
| M5B2-SETTING | ตั้งค่า ทั่วไป "ความละเอียดภาพที่ถ่าย" = 720p แล้วถ่ายคลิป 4K: ภาพด้านสั้น 720 · กลับเป็น "สูงสุดที่มี": ภาพ 4K (ราว 8 MB) | ☐ |
| M5B2-NARROW | ซูม 200% (หรือหน้าต่างกว้าง 640 px): ไม่มีแถบเลื่อนแนวนอน · ต่ำกว่า 640 px ไม่มีปุ่มขยาย และกด T ไม่เปลี่ยน | ☐ |
```
- [ ] **Step 4: tests/network_videos.toml** — append:
```toml

[capture]
# M5 รอบ B2 (T15): คลิปของ tests/network/test_capture_network.py · ตรวจข้อมูลคลิปซ้ำก่อนรันถ้าห่างหลายเดือน
landscape = "aqz-KE-bpKQ"  # Big Buck Bunny 635 วิ, CC BY, mp4 avc1 ถึง 1080 และ av01 ถึง 2160 (spike 2026-10-05: 1080p 2.0 MB / 4K 7.5 MB ต่อภาพ)
```
- [ ] **Step 5: Network test** — create `tests/network/test_capture_network.py` (do **not** run it):
```python
"""M5 รอบ B2 กับยูทูปจริง: ถ่ายภาพคมตรงจุดด้วย YtDlpExtractor.fetch_frame_piece + ffmpeg จริง (spec 5, E6)

ต้องได้รับอนุญาตจากพิธก่อนรัน: โหลดชิ้นวิดีโอสองชิ้น (ชิ้นละหนึ่งท่อน ไม่ใช่ทั้งคลิป) รวมราว 2-8 MB ลง temp ลบทิ้งเมื่อจบ
รันเองด้วย: uv run pytest -m network -q tests/network/test_capture_network.py -s
id ของคลิปอยู่ใน tests/network_videos.toml ([capture]) · ยูทูปตอบ 429 หรือขอยืนยันว่าไม่ใช่บอท = เทสตก ให้รายงานผล ห้ามแก้เทสให้หลวมลง
"""

from __future__ import annotations

import time
import tomllib
from pathlib import Path

import pytest
from helpers_ffmpeg import find_test_ffmpeg, requires_ffmpeg
from PIL import Image

from yttoolkit.core.extractor import YtDlpExtractor
from yttoolkit.core.frame_piece import PieceInfo
from yttoolkit.core.media import FfmpegTools

pytestmark = [pytest.mark.network, requires_ffmpeg]

_TOML = Path(__file__).resolve().parents[1] / "network_videos.toml"
CLIPS: dict[str, str] = tomllib.loads(_TOML.read_text(encoding="utf-8"))["capture"]
AT_MS = 120_500
GAP_S = 2  # เว้นช่วงระหว่างคำขอไปยูทูป (แบบเดียวกับ network test อื่น)
MAX_PIECE_BYTES = 15_000_000  # หนึ่งท่อน (ราว 5 วินาที) ไม่ใช่ทั้งคลิป: BBB 4K ทั้งคลิปราว 700 MB


def _frame_size(piece: PieceInfo, out: Path) -> tuple[int, int]:
    ffmpeg = find_test_ffmpeg()
    assert ffmpeg is not None
    tools = FfmpegTools(lambda: Path(ffmpeg))
    assert tools.extract_frame(piece.path, out, AT_MS - piece.segment_start_ms, long_side=None,
                               dynamic_range=piece.dynamic_range, cancel=lambda: False)  # fmt: skip
    with Image.open(out) as img:
        return img.size


@pytest.mark.parametrize(("cap", "short_side"), [(1080, 1080), (None, 2160)])
def test_one_segment_gives_a_source_size_frame(tmp_path: Path, cap: int | None, short_side: int) -> None:
    started = time.monotonic()
    piece = YtDlpExtractor().fetch_frame_piece(CLIPS["landscape"], AT_MS, cap, tmp_path / "piece.mp4")
    elapsed = time.monotonic() - started
    size = piece.path.stat().st_size
    assert size < MAX_PIECE_BYTES
    assert 0 <= AT_MS - piece.segment_start_ms < 15_000
    width, height = _frame_size(piece, tmp_path / "frame.jpg")
    assert min(width, height) == short_side
    assert (width, height) == (piece.width, piece.height)
    print(f"cap={cap} format={piece.format_id} {width}x{height} piece={size / 1e6:.1f} MB in {elapsed:.1f} s")
    time.sleep(GAP_S)
```
- [ ] **Step 6: Empty `PRD_PENDING`** — in `tests/unit/test_yterrors.py` set `PRD_PENDING: set[str] = set()` (the three PRD rows now exist; `test_prd_pending_codes_have_no_prd_row` would fail otherwise).
- [ ] **Step 7: Verify** — `cd "$WORKTREE" && uv run pytest tests/unit/test_yterrors.py -q -W error -p no:cacheprovider` (PRD rows match `MESSAGES`, with `{time}` written as `<เวลา>`), then `cd "$WORKTREE" && uv run pytest -q -W error -p no:cacheprovider` (network tests are deselected by marker in normal runs: confirm the new file shows as skipped/deselected, never executed).
- [ ] **Step 8: Commit**
```bash
cd "$WORKTREE" && git add PRD.md BRD.md docs/acceptance.md tests/network_videos.toml tests/network/test_capture_network.py tests/unit/test_yterrors.py && git commit -F- <<'EOF'
docs: M5 round B2 in PRD/BRD/acceptance; network test for sharp capture (written, not run)

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
EOF
```

---

## Spec coverage (self-review)

| Spec item | Task(s) |
|---|---|
| Owner decisions E1-E7 | table at the top; E1 T7/T11 · E2 T1/T2/T3/T10 · E3 T8/T13 · E4 T5/T9 · E5 T5/T9 · E6 T2/T6 · E7 T7/T8/T11 |
| §1.1 states compact/theater, ▶ applies the remembered preference, nothing before the first play | T5 (`theaterReducer`, `readTheaterPreference`), T9 (`onPlay` → `onPlayPressed`), e2e "▶ ขยาย…" |
| §1.1 toggle button: labels, `aria-pressed`, tooltip, only after start | T4 copy, T9 `TheaterToggle` via `PlayerControls actions` (renders only after start), e2e |
| §1.1 T/t guard (started, not in inputs, no dialog/menu, no modifier) | T5 `theaterKeyAllowed`/`isEditableTarget` (+ Vitest), T9 `useTheater` listener + overlay query, e2e "ปุ่ม T ไม่ทำงาน…" |
| §1.1 remembered preference `yt-toolkit:theater` "1"/"0", try/catch, default theater, applies on next ▶ any clip | T5 storage functions (+ throwing storage test), T9 `toggle`, e2e "ค่าที่จำไว้…" |
| §1.1 narrow < 640: no change, no button, T does nothing | T5 `headerLayout`, T9 `canToggle`, e2e "จอแคบ 600 px" |
| §1.1 docked mini player unchanged in both layouts; another clip resets to compact | T9 (slot never remounted, docking untouched), T5 `isTheaterOn`, e2e "ตัวเล่นลอย…", "ค่าที่จำไว้…" |
| §1.2 landscape theater (full width, C2 + C3 under it, then info, tabs) | T9 `LAYOUTS["theater-wide"]`, T13 strip `row` placement, e2e geometry |
| §1.2 portrait theater (min(80vh,760px) 9:16 left, info right with C2 + C3 at the bottom) | T9 `PlayerSlot portrait`, `theater-tall`, T13 strip at the bottom, e2e "คลิปแนวตั้ง" |
| §1.2 compact (C2 + C3 under the small player, wrap) | T9 (unchanged compact), T13 `wrap` strip |
| §1.2 portrait detection | T5 `isPortraitVideo` (+ Vitest) |
| §1.2 DOM order = visual order, no CSS `order` | T9 (three placements of `controls()`), T13 (strip next to each) |
| §1.3 `startViewTransition` with names on slot and info, ~300 ms ease-out | T5 `runLayoutTransition`, T9 `index.css`, e2e counts transitions |
| §1.3 reduced motion / no API → instant; `flushSync`; iframe resized not remounted | T5 (+ Vitest), T9 `useTheater` (`flushSync`, `prefersReducedMotion`), e2e "ลดการเคลื่อนไหว…", iframe marker + `players === 1` |
| §2.1 entry points: C2 button (markTimeMs, 100 ms), docked icon button, frame context menu (frame `tMs`) | T8 `CaptureButton`/`CaptureMenuItem`/`captureTimeMs`, T13 mounting, e2e |
| §2.2 busy spinner "กำลังถ่าย…", one capture app-wide, done toast + "ดูภาพ", strip append in order with highlight | T8 (`captureStore`, `runCapture`, strip flash), T7 lock, e2e |
| §2.2 disabled reasons (live, paused) focusable with tooltip | T8 `captureBlock`/`blockTooltip`/`CaptureButton`, e2e "คิวพัก…", "คลิปสด…" |
| §2.2 error codes and copy; bot check brakes the queue | T1 copy, T6 mapping, T7 brake, T11 statuses, T8 toast from server message, T14 bot-check spec |
| §2.3 strip header + "เปิดโฟลเดอร์", tiles ~96 px with time badge in time order, wrap/row, keyboard model, portrait padded, empty/loading = nothing | T8 `CaptureStrip` (+ `stripKeyTarget` Vitest), T11 reveal, T13 placement, e2e |
| §2.3 lightbox actions (copy, download, open in YouTube at time, play from here, delete + confirm + toast) | T8, e2e "ภาพใหญ่ ←/→…", T14 |
| §2.3 persistence per clip, 30-day purge keeps folder files | T7 (cache under `<cache>/<id>/captures/`, existing `purge_stale_cache` removes the clip folder only) |
| §2.4 `captureQuality` setting + Settings › ทั่วไป select + hint; cap on the short side; no scaling | T1, T10, T2 `pick_capture_format`/`max_short_side`, T3 `long_side=None`, T7 passes the cap |
| §3.1 probe, format choice, 64 KB head, sidx v0/v1, fetch past 64 KB, segment fetch, write init + segment | T2 (pure), T6 (`YtDlpExtractor.fetch_frame_piece`) |
| §3.1 errors via `classify`; logs id/format/bytes only; fake from `piece.mp4` with unsupported/network/bot behaviours | T6 (+ log assertions), T2 fixture, T6 `captureError` clips |
| §3.2 service: 422 rejections, 409 paused, non-blocking lock, temp dir under `work/`, extract `long_side=None` (HDR tone-map), cache copy + atomic index under a per-clip lock, folder copy `frame_HH-MM-SS` `_2`, `finally` cleanup, idempotent | T7 |
| §3.2 list drops missing cache files; delete safety (root, name, no links, missing ok); index entry fields; `outputRoot` never logged | T7 (`recorded_output`, delete tests) |
| §3.3 API: GET list + url `?v=`, POST strict 201/errors, DELETE 204/404, reveal 200/404, cache route immutable for `captures` | T11 |
| §3.4 settings key exposed in GET, web `Settings` type | T1, T4 |
| §4 edge rows: no mp4 sidx · last fraction retry 100 ms · double click busy · bot check · app closed mid-capture (startup sweep) · disk full / not writable rollback · deleted folder file · same moment idempotent | T2/T6 · T7 · T7/T8/T11 · T7/T11/T14 · T12 `test_startup_removes_a_capture_left_by_a_crash` · T7 · T7 `test_delete_with_the_folder_copy_already_gone` · T7/T11/T14 |
| §5 docs: PRD W2 rows, API list, error table, settings table; BRD E1-E7; acceptance M5-B2; network test | T15 |
| §6 Python units (sidx, format, service, API, settings) | T2, T7, T11, T1 |
| §6 integration with real ffmpeg (fragmented mp4 with sidx, real parser + extract, frame matches time, source resolution) | T7 `tests/integration/test_capture_ffmpeg.py`, T3 `test_no_long_side_keeps_the_source_resolution` |
| §6 Vitest (reducer, storage incl. throwing, portrait, T guard, strip ordering + keyboard) | T5, T8 |
| §6 Playwright chromium (switch on play, T + button, preference across clips, portrait, narrow no-op, reduced motion, capture busy/toast/strip/lightbox/delete, disabled live/paused, frame menu, axe light/dark, 640 px) | T9 `theater.spec.ts`, T13 `capture.spec.ts`, T10 settings spec |
| §6 Playwright queue/fake backend: one real capture end to end incl. the folder copy | T14 `queue-capture.spec.ts` |
| Review Focus 1-5 | T2+T7, T7, T7, T7+T11+T8, T5+T9 (test names listed in the section) |

Self-review checks run on this plan:
- No "TBD"/"TODO"/"similar to Task N"; every code step carries the full code.
- The Python code of T1, T2, T3, T6, T7, T11 and T12 (and their tests) was run in a scratch copy of the repo before writing this plan: `test_frame_piece.py` 27 passed, `test_extractor_capture.py` + `test_extractor_download.py` + `test_media_args.py` 148 passed, `test_capture.py` + `test_capture_ffmpeg.py` 42 passed, `test_captures_api.py` 19 passed, `test_videos_api.py` 126 passed, `test_lifecycle.py` 178 passed, T1 files passed except the two PRD-row checks that need `PRD.md` (present in the repo). The web code of T5, T8, T9, T10, T13 and the three e2e specs typechecked (`tsc` app + node configs) and linted clean in a scratch copy; Vitest: `theater.test.ts` 16, capture module 16, settings 15 passed. Playwright was not run (gates do).
- Every symbol a later task uses is defined in a contract and in exactly one earlier task: `CAPTURE_QUALITIES`/`E_CAPTURE_*`/`E_QUEUE_PAUSED` T1 · `read_index`/`fetch_piece`/`segment_for`/`pick_capture_format`/`piece_info`/`write_piece`/`PieceInfo`/`max_short_side` T2 · `long_side=None` T3 · `th.theater`/`th.capture`/`th.general.captureQuality*`/`Capture`/`CaptureQuality` T4 · `theaterReducer`/`isPortraitVideo`/`headerLayout`/`theaterKeyAllowed`/`runLayoutTransition` T5 · `fetch_frame_piece`/`CAPTURE0001…` T6 · `CaptureService`/`CaptureRejected`/`recorded_output`/`CAPTURE_FOLDER`/`OUTPUT_DIR` T7 · `CaptureButton`/`CaptureMenuItem`/`CaptureStrip`/`useCapture`/`runCapture` T8 · `useTheater`/`TheaterToggle`/`PlayerSlot portrait,onPlay`/`PlayerControls actions` T9 · `CAPTURE_QUALITIES` (web) T10 · `build_captures_router`/`AppContext.captures` T11 · `Services.captures` T12.
- Names match across tasks (`yt-toolkit:theater`, `data-theater-switching`, `data-slot` values `video-header`/`video-info`/`player-actions`/`theater-toggle`/`capture-button`/`capture-strip`/`capture-actions`, `c_<tMs>`, `ภาพที่ถ่าย`, `captureError`).
- Every file appears in exactly one lane per wave (Lane rules table); `th.ts` and `types.ts` are written only by T4; existing tests that hard-code the extended lists are in the owning task's Files (`SETTING_KEYS`, defaults dict, `PRD_PENDING`, `C14`, the four web Settings literals, the "หกช่อง" settings e2e test, the three frame-menu lists in `video.spec.ts`/`transcript.spec.ts`/`sharp-grid.spec.ts`, compact-geometry player specs protected by the config default).

---

## Execution handoff

Plan saved to `docs/superpowers/plans/2026-10-05-m5b2-capture-and-theater.md`. Execute with superpowers:subagent-driven-development: the controller creates one worktree per lane under `.claude/worktrees/m5b2-<lane>` on `m5b2/t<N>-<slug>` and dispatches one fresh subagent per task with its absolute `WORKTREE` (wave 1 = T1-T5, wave 2 = T6-T10, wave 3 = T11-T15, lanes of a wave in parallel), runs the wave gate procedure between waves (gate 2 adds the chromium `theater.spec.ts` and settings spec run), the two-stage review per task, then the final gate (build, `npm run e2e` with the queue project serial, `web/dist` commit, live preview for Pete in fake mode with `CAPTURE0001`). The network test runs only after Pete approves the ~2-8 MB download.
