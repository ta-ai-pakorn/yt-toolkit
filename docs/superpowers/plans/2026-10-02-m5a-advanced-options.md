# M5 round A ตัวเลือกขั้นสูง (time range, chapter split, SponsorBlock) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Tasks inside one wave run as parallel subagents, each in its own git worktree (see "Waves" and "Lane rules"). Every task is reviewed by a reviewer subagent before its wave closes.

**Goal:** In W2 the user can download only a time range (frame-exact), split a clip into one file per chapter (video and audio), and cut SponsorBlock ad segments, from a shared "ตัวเลือกขั้นสูง" section in the วิดีโอ, เสียง and ซับ tabs, with "ตั้งจุดเริ่ม / ตั้งจุดจบ" buttons under the player and in the frame menu; the backend downloads the full clip and cuts it with ffmpeg (approach B).

**Spec:** `docs/superpowers/specs/2026-10-02-m5a-advanced-download-options-design.md` (owner decisions D1-D9, final Thai copy). Acceptance: AC-ADV-01..04, AC-VID-10 part 1, AC-SUB-10, plus the folded M4 follow-ups (lifecycle sweep of new names; W2 download before settings load, items 1-3).

**Out of scope (round A):** sharp frames (round B), YouTube cookies and `useCookies` (round C), advanced options in W3, subtitle split by chapter, subtitle re-timing after SponsorBlock, several ranges per download, decimal-second input.

**Architecture:**
- **Download full, cut ourselves (D9).** Handlers keep the M4 download step unchanged, then build *keep intervals* on the original timeline with pure functions in a new `core/advanced.py` (range ∩ clip, minus merged SponsorBlock segments, pieces < 1 s dropped; or one interval per chapter). One cutter in `core/media.py` (`cut_args` + `MediaTools.cut`) turns `(input, intervals, mode, target)` into an intermediate file in `work/<jobId>/`; the existing M4 finalize steps (cover, metadata, mov_text subtitles, mp3/wav conversion) then run on the cut file unchanged.
- **SponsorBlock through yt-dlp.** `core/extractor.py` (still the only `yt_dlp` importer) wraps `yt_dlp.postprocessor.sponsorblock.SponsorBlockPP.run` as `sponsor_segments()`; failures become `SponsorBlockError`, which handlers turn into a grey note, never a retry or a queue brake.
- **Subtitles by range.** Tokens are filtered by midpoint, clamped and shifted to 0 **before** cue building, and cue ends are clamped to the range length, identically in `core/srt_builder.py` and `web/src/lib/srt-builder.ts` (parity fixtures), so the file, the preview and "คัดลอกข้อความ" agree byte for byte.
- **One per-clip store on the web.** `web/src/pages/video/advanced/advanced-store.ts` (external store keyed by `videoId`, memory only) holds the raw field text and switches; the three tabs, the player buttons and the frame menu all write to it. Pure validation/labels live in `web/src/lib/advanced-options.ts`; SponsorBlock categories live in the server setting `sponsorblockDefault` (D3 cross-clip memory, `PATCH /settings`).

**Tech Stack:** unchanged (Python 3.13 + uv, FastAPI, pydantic v2, yt-dlp 2026.08.19 as a library, ffmpeg 8.1 from `bin/` or PATH, React + Vite + Tailwind + shadcn/Base UI + react-query 5, Vitest, Playwright). No new Python or npm dependency.

---

## Owner decisions (from the spec, 2026-10-02)

| # | Decision | Where in this plan |
|---|---|---|
| D1 | Time-range cuts are frame-exact (video re-encoded) | C3 `mode="exact"`, T3, T8 |
| D2 | Chapter split for video **and** audio | C1, T13 |
| D3 | Advanced values are per clip (reset on another clip / reload); only the SponsorBlock categories are remembered (setting `sponsorblockDefault`); the SponsorBlock switch starts off | C9 store, T10 `useSponsorCategoryToggle` |
| D4 | Chapter files go to `<clip folder>/แยกตาม chapter (mp4|m4a|mp3|wav)/` | C2 `plan_chapter_output`, T13 |
| D5 | SponsorBlock included, off by default | C1, C4, T8 |
| D6 | Video chapter split = fast stream-copy cuts (boundaries may be off 1-3 s); audio chapters exact | C3 `mode="fast"`, T13 |
| D7 | "ตั้งจุดเริ่ม / ตั้งจุดจบ" under the player, next to the time fields, and in the frame menu | T10 (field buttons), T11 (player + frame menu) |
| D8 | W3 gets no advanced options | W3 keeps `paramsFromSettings` (T6 keeps `splitChapters: false`) |
| D9 | Approach B: download full clip, cut with ffmpeg | whole plan |

### Planner decisions (not owner questions; Pete can still object)
- **Exact video cut:** one ffmpeg run, one input per interval with input-side `-ss <s> -t <len>` (accurate seek), `setpts/asetpts` + `concat` filter, `libx264 -preset veryfast -crf 20 -pix_fmt yuv420p` + `aac 192k`, `-f mp4`. Verified locally (see Verified facts).
- **Exact audio cut (±50 ms):** m4a with exactly one interval = stream copy (`-ss -t -i … -c copy`, measured start error ≤ 3 ms, duration +12..18 ms); m4a with several intervals (SponsorBlock) = AAC 192k re-encode through the same concat filter; mp3 and wav = cut to a PCM wav intermediate (sample exact), then the existing `to_mp3` / `to_wav` run on it (one lossy encode only).
- **Fast video chapter cut:** `-ss <s> -t <len> -i … -map 0:v:0 -map 0:a? -c copy -avoid_negative_ts make_zero -f mp4` (starts at the keyframe before the chapter, D6).
- **How chapter info reaches the handler:** from the clip's cached `VideoInfo.chapters` (`{startS, endS, title}`, read by `_start` through `VideoService.get(peek=True)`), with the end of the last chapter clipped to the duration reported by the download's own info. Fewer than 2 usable chapters at run time → full file + note `NO_CHAPTERS`.
- **SponsorBlock categories (`sponsorblockDefault`):** the web reads them from `GET /settings` and saves every tick change with `PATCH /settings {sponsorblockDefault: [...]}` (optimistic update, revert + toast `th.general.saveFailed` on error). The backend validator is tightened to the 8 known categories, non-empty.
- **SponsorBlock with a range:** segments are clipped to the range. If nothing is cut (no segments, or none inside the range, or everything left would be shorter than 1 s), the job gets note `SPONSORBLOCK_EMPTY` ("ไม่มีข้อมูลจากชุมชน ได้คลิปเต็ม"), no `(ตัดโฆษณา)` suffix, and no ad re-encode (a range still cuts the range).
- **Unknown duration at the API:** when the probe is cached, a `range` on a live clip or a clip with `durationS <= 0` is 422 (the UI disables the fields for such clips). Uncached: the handler clips the range end to the real duration; a range that ends up shorter than 1 s fails the job with `E_UNKNOWN`.
- **`subtitle` + `range` + `format: "md"`:** 422 (the web never sends `md` since BRD #112; a ranged note has no defined chapter layout).
- **Disk check:** jobs that cut use factor 3 (download + cut + finished file) instead of 2; the downloaded file is deleted as soon as the cut is written.
- **Queue/history text (spec 3.5):** the suffix (` · ช่วง 1:30-5:00`, ` · แยก chapter`, ` · ตัดโฆษณา`) is appended by `jobTitle()`, so it shows in the queue bar, the queue sheet rows and the finished/failed toasts. W5 history rows are one row per clip (no job title), so they are unchanged.
- **Fake media tools:** without ffmpeg (e2e has none) `FakeMediaTools.cut` copies a real tiny fixture file and records every call (`CutCall`: intervals, mode, target, has_audio). The "right durations" of the spec are asserted on the recorded intervals; file playback length is only real with real ffmpeg (integration tests, network tests).
- **Player readiness:** "ใช้เวลาที่ตัวเล่นอยู่ตอนนี้" is enabled when the player store has this clip, `started`, and status `playing | paused | ended`.
- **Exclusivity across tabs:** the chapter switch is blocked (in the วิดีโอ and เสียง tabs) by a set range, by SponsorBlock, or by a chosen embed-subtitle track (shared `choices.embedSubs`); while chapters are on, the range fields (all three tabs), the SponsorBlock switch and the embed-subtitle select are disabled with "ปิด 'แยกไฟล์ตาม chapter' ก่อน", and the builders never send `embedSubs`, `range` or `sponsorblock` together with `splitChapters: true`. A player/frame "ตั้งจุด…" press while chapters are on shows a toast with "ปิด 'แยกไฟล์ตาม chapter' ก่อน" and changes nothing.
- **"ช่วงต้องยาวอย่างน้อย 1 วินาที":** the fields take whole seconds, so once start < end the range is at least 1 s and the UI cannot produce this message; the string is kept in `th.ts` (final copy) and the rule is enforced by the API (`endMs − startMs ≥ 1000`) and by the handler after clipping the end to the real duration.
- **Validation display:** errors show after the field loses focus, after a "ตั้งจุด…" press, or after a download press (store flag `checked`); a download press with an invalid range opens the section and focuses the first invalid field, creating no job.
- **M4 follow-up "หน้า W2 กับค่าตั้ง":** (1) download buttons of the วิดีโอ/เสียง tabs stay disabled until `GET /settings` has settled (success or error); (2) a remembered quality height above the compat cap (e.g. 1080 after switching to 720) resolves to the cap height option instead of a silent "อัตโนมัติ"; (3) e2e asserts `maxHeight` in the enqueued body for compat-1080, compat-720 and max.

## Questions for the owner

None blocking. The spec has no conflict this plan could not resolve; every interpretation is listed under "Planner decisions" above.

**Owner inputs needed before the network run (T15 writes the tests, nobody runs them without approval):**
1. A short public clip that has SponsorBlock `sponsor` data for AC-ADV-04 (`tests/network_videos.toml [advanced] sponsor_clip`). The test skips with a clear reason while it is empty. Approving the run also means approving roughly 60-120 MB of downloads (sizes listed in T15).

---

## Waves

Integration branch: `m5a-advanced-options` (already checked out; the spec is commit `2c5ffa3`).

| Wave | Lanes (one worktree each, file sets disjoint) | Depends on |
|---|---|---|
| 1 | T1 job params + notes + stages + settings · T2 keep-interval maths + file names · T3 ffmpeg cutter · T4 SponsorBlock source + fake fixtures · T5 subtitle range (Python + TS parity) · T6 web types, builders, all M5-A strings, download-state follow-ups · T7 web advanced logic + per-clip store | spec |
| 2 | T8 handlers: range, SponsorBlock, subtitle/embedded range · T9 lifecycle sweep of new names · T10 W2 "ตัวเลือกขั้นสูง" section in the three tabs · T11 player buttons + frame menu items · T12 queue/history job text and stages | gate 1 (T8←T1,T2,T3,T4,T5 · T9←T2 · T10←T5,T6,T7 · T11←T6,T7 · T12←T6,T7) |
| 3 | T13 handlers: chapter split + SponsorBlock wiring · T14 queue e2e (real fake backend) · T15 docs + network tests (written, not run) | gate 2 (T13←T8 · T14←T4,T8 (+T13 at the final gate) · T15←all) |
| final | controller: merge, full checks, `npm run build`, `npm run e2e`, commit `web/dist`, reviews, live preview for Pete | gate 3 |

**Critical path:** T2 / T3 / T4 → T8 → T13 → final gate (`queue` e2e project).
**Counts:** 3 waves + final gate · 15 tasks (= 15 lanes).

### Lane rules (every task)
1. **Worktree and branch.** Each task runs in its own git worktree (`isolation: "worktree"`) on branch `m5a/t<N>-<slug>`, branched from the head of `m5a-advanced-options` at the start of its wave. Do not switch the main checkout's branch.
2. **Files.** A task creates or modifies **only** the files in its **Files** list. Needing another file is a plan bug: stop and report it to the controller; do not edit the file.
3. **Shared files have exactly one owner per wave:**

   | File | W1 owner | W2 owner | W3 owner |
   |---|---|---|---|
   | `src/yttoolkit/core/handlers.py`, `tests/unit/test_handlers.py` | — | T8 | T13 |
   | `src/yttoolkit/lifecycle.py`, `tests/unit/test_lifecycle.py` | — | T9 | T13 |
   | `src/yttoolkit/core/jobs.py`, `core/queue.py`, `core/settings.py`, `core/videos.py`, `api/jobs.py` | T1 | — | — |
   | `src/yttoolkit/core/files.py`, `core/advanced.py` | T2 | — | — |
   | `src/yttoolkit/core/media.py` | T3 | — | — |
   | `src/yttoolkit/core/download.py`, `core/extractor.py`, `tests/fixtures/downloads/behaviors.json`, `tests/fixtures/README.md` | T4 | — | — |
   | `src/yttoolkit/core/srt_builder.py`, `core/subtitles.py`, `web/src/lib/srt-builder.ts` | T5 | — | — |
   | `web/src/i18n/th.ts` | T6 | — | — |
   | `web/src/lib/types.ts` | T6 | T12 | — |
   | `web/src/lib/download-options.ts`, `web/src/pages/video/download/use-download-state.ts` | T6 | — | — |
   | `web/src/pages/video/download/video-panel.tsx`, `audio-panel.tsx`, `web/src/pages/video/subs-panel.tsx`, `web/src/pages/video/subs/*` | — | T10 | — |
   | `web/src/pages/video/player/player-slot.tsx`, `web/src/pages/video/frames.tsx` | — | T11 | — |
   | `PRD.md`, `BRD.md`, `docs/**` (except this plan) | — | — | T15 |
   | `web/dist/**` | final gate only; **no lane builds into or commits `web/dist`** | | |

   A lane that needs a Thai string that is not in C8 stops and asks the controller; the controller adds it at the gate (T6 is the only writer of `th.ts`).
4. **Tests.**
   - Python lanes run their own tests, then the full `uv run pytest -q -W error -p no:cacheprovider`.
   - Web lanes run `npm run typecheck && npm run lint && npm test` in `web/`.
   - Lanes **do not run Playwright.** Specs are written, typechecked and linted in the lane and run at the final gate (the controller may also run them at gate 2, see the gate procedure).
   - **No spec in the default `chromium` project may create a real job or change real settings.** A chromium spec that clicks an enqueue button first calls `mockEnqueue(page)`; one that ticks a SponsorBlock category first mocks `PATCH /api/settings`. Real jobs only in `queue-*.spec.ts` (the `queue` project).
   - Network tests (`@pytest.mark.network`) are written in T15 and **never run** without Pete's approval.
5. **Processes.** No lane starts a server. Never touch the owner's app on port 8787. Kill processes by PID only.
6. **Commits.** Every commit message ends with exactly `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`. Use `git commit -F- <<'EOF' … EOF`.

### Wave gate procedure (controller, serial)
1. Merge every lane branch of the wave into `m5a-advanced-options` with `git merge --no-ff m5a/t<N>-<slug>`. A merge conflict means the plan is wrong: stop and report.
2. `uv sync --frozen && uv run pytest -q -W error -p no:cacheprovider` (must pass; real-ffmpeg tests run on the dev machine).
3. `cd web && npm ci && npm run typecheck && npm run lint && npm test`.
4. Gate 2 (recommended, not committed): `cd web && npm run build && npm run e2e` to catch W2 UI failures before wave 3; failures go back to T10/T11 as a fix round. Do **not** commit `web/dist` at gate 1 or 2.
5. Run the two-stage review (spec compliance, then code quality) from superpowers:subagent-driven-development on each task of the wave, and fix findings in the owning lane before the next wave.

### Final gate (controller, after wave 3)
1. Merge T13-T15 (`--no-ff`), then steps 2-3 above.
2. `cd web && npm run build` then `npm run e2e` (runs project `chromium` on `E2E_PORT` (8799) and project `queue` on `E2E_PORT + 1`, both fake mode, built `dist`). A failing `queue-advanced.spec.ts` goes back to T13/T14; chromium failures to T10/T11.
3. Check total JS gzip ≤ 400 KB excluding fonts (PRD 6.5).
4. Commit the rebuilt `web/dist` as `build(web): web/dist after M5 round A` (with the trailer).
5. Reviews as in step 5 above, then a live preview for Pete on port 8791 (memory rule "preview after QA"): fake mode is enough for the UI; real downloads only with his approval.

---

## Verified facts (read or measured on 2026-10-02 in this repo)
- **yt-dlp 2026.08.19** (`uv run python -c "import yt_dlp.version as v; print(v.__version__)"`). `yt_dlp/postprocessor/sponsorblock.py`: `SponsorBlockPP(downloader, categories=None, api='https://sponsor.ajay.app')`; `run(info)` reads `info['extractor_key']` (`'Youtube'`), `info['id']`, `info.get('duration')` and returns `([], info)` with `info['sponsorblock_chapters'] = [{start_time, end_time, category, title, type, _categories}]`. The request URL carries only the first 4 hex chars of `sha256(video_id)`. `_download_json` (in `postprocessor/common.py`) retries `extractor_retries` times (default 3) and raises `PostProcessingError` (a `YoutubeDLError`); HTTP 404 = no data → `[]`. `FFmpegPostProcessor.__init__` only resolves paths (no subprocess), so constructing the PP needs no ffmpeg. With `duration=None` the duration filter raises `TypeError` when a segment has `videoDuration`, so the wrapper refuses an unknown duration.
- **ffmpeg 8.1** on PATH (`Gyan.FFmpeg … ffmpeg-8.1-full_build`). Experiments in the scratchpad on a 40 s lavfi `testsrc2` + sine clip encoded with a 4 s GOP:
  - exact cut `-ss 10.000 -t 5.000 -i src.mp4` + `setpts/asetpts` + `concat=n=1:v=1:a=1` + libx264 veryfast crf 20 + aac 192k: video 5.000 s, audio 5.000 s; first frame vs source frame at 10.000 s mean abs diff 0.31 (vs 2.89 for the next frame) → frame-exact (AC-ADV-01 method).
  - two intervals (2-7 s, 13-20 s) in one run: 12.000 s; frame at 5.0 s of the output = source frame at 13 s (diff 0.21).
  - no-audio variant (`concat … a=0`, `-an`): video only, 5.000 s.
  - fast copy `-ss 10 -t 5 -i … -c copy -avoid_negative_ts make_zero`: starts at the keyframe at 8 s (7.07 s long) → D6 behaviour.
  - m4a stream copy single interval: click at 10.000 s cut from 9.5 s lands at 0.5027 s; from 9.987 s at 0.0157 s (target 0.013); duration 2.012-2.018 s for 2 s → within ±50 ms.
  - m4a AAC re-encode and wav PCM through the concat filter with two intervals: clicks exactly at 0.5000 s and 3.0000 s; durations 5.0155 s / 5.0000 s.
  - `-metadata track=3/12` is kept by mp4/m4a, mp3 (id3v2.3) and wav (RIFF INFO).
  - The exact argument lists of C3 were run against these files: all 8 cases exit 0 with the expected streams and durations.
- **Fixtures:** `tests/fixtures/media/video.mp4` 2.0 s 160×90 10 fps one keyframe + AAC; `audio.m4a` 2.0 s; `audio.wav` 0.5 s. Probe fixtures: `jNQXAC9IVRw` 19 s, 3 chapters (`Intro` 0-5, `The cool thing` 5-17, `End` 17-19), owner subs; `aqz-KE-bpKQ` 635 s, no chapters, no subs; `88o5Sk8_m1Y` 372 s, `a.th-orig`. `tests/fixtures/subs/tokens/th-asr.json` has 87 tokens starting in 90-210 s, `en-asr.json` 368.
- **Line endings:** `.gitattributes` is `* text=auto eol=lf` with `tests/fixtures/subs/golden/** -text`; `git ls-files --eol` shows every `.py`, `.ts`, `.json` and `.md` file as `i/lf w/lf`; only the 28 subtitle goldens are CRLF. The standing rule below is therefore applied as "never change a file's existing line endings": use the Edit tool (or `open(..., newline="")`), and keep new CRLF data inside JSON strings (`\r\n`) so no new `-text` path is needed.
- **Strict params today:** `api/jobs.py` uses `extra="forbid"`; `splitChapters` is `Literal[False]`; `tests/api/test_jobs_api.py::test_post_rejects_bad_items` lists `splitChapters: True` (video and audio) and `sponsorblock: ["sponsor"]` as 422 cases; those rows become valid in M5-A and T1 removes them.
- **`Downloader` is `runtime_checkable`** and `tests/unit/test_handlers.py:1005` asserts `isinstance(env.downloader, Downloader)` for a stub; adding a method to that protocol would break wave 1, so SponsorBlock is a separate protocol `SponsorSource` and a new `HandlerDeps.sponsors` field (T8), wired in `lifecycle.open_services` in T13.
- **`files.plan_output` asserts `len(suffix + "." + ext) <= TAIL_RESERVE (30)`.** Range + ads + no-audio tails reach 50 characters (` (ไม่มีเสียง) (100.00.00-100.05.00) (ตัดโฆษณา).mp4`). T2 raises the assert to `TAIL_MAX = 60` and shortens only the *file* stem by the excess, so every M4 name and every clip folder name stay byte-identical (proof in T2).
- **Web test environment:** Vitest runs in node (no jsdom, no Testing Library); components are covered by Playwright only, so all logic that needs unit tests is written as pure functions.
- **Stage validation:** `core/jobs.py:259` (`_encode`) and `core/queue.py:98` (`JobContext.stage`) reject stages outside `STAGES`; both must accept the new stages.
- **Queue rows:** `DoneRow` already lists every output with its own "ดาวน์โหลด" link and reveals `outputs[0]`, so many chapter outputs need no new UI.
- `web/e2e/queue-helpers.ts` exports `mockEnqueue`, `enqueue`, `waitForJob`, `openQueueSheet`; `web/e2e/fake-yt.ts` exports `installFakeYT(page, {durationS, rate})`. The e2e data root is reset before each run.

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

**M5-A specific:**
- SponsorBlock never sends user data (yt-dlp sends a 4-character hash prefix) and never uses the visitor session cookie file (`with_session=False`).
- SponsorBlock failures never raise `YtError` out of the handler, never trigger `E_NETWORK` retries and never call the bot-check brake.
- No range/chapter/SponsorBlock UI or params in W3 (D8).
- Accessibility: every field, switch, checkbox and icon button has an accessible name; field errors are linked with `aria-describedby`; axe has no serious/critical findings in both themes.

**Tests:**
- Backend: `uv run pytest -q -W error -p no:cacheprovider` (no warnings).
- Web: `cd web && npm run typecheck && npm run lint && npm test` (ESLint 0 errors / 0 warnings).
- Final: `cd web && npm run build` then `npm run e2e`.
- Real-ffmpeg tests use `requires_ffmpeg` from `tests/helpers_ffmpeg.py`.

---

## Shared contracts (every lane codes against these)

### C1. Job params, notes and stages (`core/jobs.py`, `api/jobs.py`, T1)
`core/jobs.py` gains (exact):
```python
STAGES = (
    "probing", "downloading_video", "downloading_audio", "merging", "converting", "writing",
    "cutting", "cutting_ads",
)
SPLIT_STAGE = re.compile(r"splitting:(\d{1,4})/(\d{1,4})")   # "splitting:3/12" = กำลังแยก chapter 3 จาก 12
SPONSORBLOCK_CATEGORIES = (
    "sponsor", "selfpromo", "interaction", "intro", "outro", "preview", "filler", "music_offtopic",
)
MIN_RANGE_MS = 1000        # ช่วงต้องยาวอย่างน้อย 1 วินาที
RANGE_TOLERANCE_MS = 500   # ปลายช่วงเกินความยาวคลิปได้ไม่เกินนี้ (ความยาวคลิปเป็นวินาทีปัดเศษ)

def split_stage(index: int, total: int) -> str      # ValueError unless 1 <= index <= total <= 9999
def is_stage(value: str) -> bool                    # value in STAGES or SPLIT_STAGE.fullmatch(value)
```
New `NOTES` entries (verbatim):

| code | message |
|---|---|
| `SPONSORBLOCK_EMPTY` | ไม่มีข้อมูลจากชุมชน ได้คลิปเต็ม |
| `SPONSORBLOCK_UNREACHABLE` | ติดต่อ SponsorBlock ไม่ได้ ได้คลิปเต็ม |
| `NO_CHAPTERS` | คลิปนี้ไม่มี chapter ได้ไฟล์เต็ม |

Params (additions; everything else unchanged and still `extra="forbid"`):
```ts
type TimeRange = { startMs: number; endMs: number }          // ints, multiples of 1000, 0 <= startMs, endMs - startMs >= 1000
video:    { ...M4, splitChapters: boolean = false, range?: TimeRange, sponsorblock?: SponsorCategory[] }
audio:    { ...M4, splitChapters: boolean = false, range?: TimeRange, sponsorblock?: SponsorCategory[] }
subtitle: { ...M4, range?: TimeRange }                        // range + format "md" -> 422
```
Validation → 422 `E_BAD_REQUEST` (nothing enqueued): non-int / bool / float `startMs`/`endMs`; not multiples of 1000; `startMs < 0`; `endMs - startMs < 1000`; `sponsorblock` empty, duplicated, or with a category outside `SPONSORBLOCK_CATEGORIES`; `splitChapters: true` with `range`, `sponsorblock` or `embedSubs`; subtitle `range` with `format: "md"`. Then, for items with `range` or `splitChapters: true` and a stored probe (`VideoService.peek_cached`): live clip or `durationS <= 0` with a range; `endMs > durationS*1000 + RANGE_TOLERANCE_MS`; `splitChapters` on a clip with fewer than 2 chapters. Uncached = accepted (the handler re-checks). Stored params = `model_dump(exclude_none=True)`.

`VideoService.peek_cached(video_id: str) -> dict | None` — stored VideoInfo regardless of age, no probe, does not touch `opened_at`; bad id or no row = None.

### C2. Keep intervals and file names (`core/advanced.py` new, `core/files.py`, T2)
```python
Interval = tuple[int, int]            # ms on the original timeline, start < end
MIN_PIECE_MS = 1000
ADS_SUFFIX = " (ตัดโฆษณา)"
def range_suffix(start_ms: int, end_ms: int) -> str       # " (01.30-05.00)"; end >= 1 h -> " (1.02.30-1.05.00)" both sides
def merge_intervals(items: Iterable[Interval]) -> list[Interval]
def keep_intervals(span: Interval, ads: Iterable[Interval]) -> list[Interval]   # span minus ads (clipped, merged), pieces < 1 s dropped
def kept_ms(intervals: Iterable[Interval]) -> int
@dataclass(frozen=True)
class ChapterPart:
    index: int          # 1-based
    total: int
    start_ms: int
    end_ms: int
    title: str          # stripped, may be ""
def chapter_parts(chapters: Sequence[Mapping[str, Any]], duration_ms: int) -> list[ChapterPart]   # [] when < 2 usable
```
`core/files.py`:
```python
TAIL_MAX = 60                            # suffix + "." + ext may be this long (was asserted <= TAIL_RESERVE)
CHAPTER_DIR = "แยกตาม chapter ({ext})"
def chapter_dir_name(ext: str) -> str     # "แยกตาม chapter (mp4)"
def plan_chapter_output(root: Path, title: str, video_id: str, ext: str, group: str | None, *,
                        index: int, total: int, chapter_title: str) -> Path
    # <clip folder of plan_output>/แยกตาม chapter (<ext>)/<NN> - <safe chapter title>.<ext>
    # NN = 2 digits, 3 when total >= 100; empty/unsafe title -> "chapter <index>"; title truncated to fit 240;
    # no room for any title -> "<NN>.<ext>"; still too long -> YtError("E_OUTPUT_NOT_WRITABLE", "path too long")
```
Output names (handlers, T8/T13): order no-audio → range → ads:
`<t>.mp4`, `<t> (ไม่มีเสียง) (01.30-05.00) (ตัดโฆษณา).mp4`, `<t> (01.30-05.00).m4a|mp3|wav`, `<t> (ตัดโฆษณา).m4a`, `<t> (01.30-05.00).<lang>.srt|txt`, chapter files per `plan_chapter_output`. A second identical download gets ` (2)` (`files._candidates`).

### C3. Cutter (`core/media.py`, T3)
```python
CutMode = Literal["exact", "fast"]
CutTarget = Literal["mp4", "m4a", "wav"]
X264_PRESET = "veryfast"
X264_CRF = 20
CUT_AAC_KBPS = 192

@dataclass(frozen=True)
class MediaMeta:            # + one new field with a default (existing call sites unchanged)
    ...
    track: str | None = None     # "3/12" -> -metadata track=3/12 (mp4, m4a, mp3, wav)

def cut_args(ffmpeg: str, src: Path, dst: Path, intervals: Sequence[tuple[int, int]], *,
             mode: CutMode, target: CutTarget, has_audio: bool) -> list[str]
class MediaTools(Protocol):
    def cut(self, src: Path, dst: Path, intervals: Sequence[tuple[int, int]], *, mode: CutMode,
            target: CutTarget, has_audio: bool, cancel: Callable[[], bool],
            on_progress: Callable[[float | None], None]) -> None: ...
@dataclass(frozen=True)
class CutCall:
    src_name: str
    dst_name: str
    intervals: tuple[tuple[int, int], ...]
    mode: str
    target: str
    has_audio: bool
FakeMediaTools.cuts: list[CutCall]       # appended by FakeMediaTools.cut
```
Rules: `fast` = mp4 only, exactly one interval, stream copy. `exact` + `m4a` + one interval = stream copy. Every other `exact` = filter_complex concat re-encode (mp4: libx264 + aac or `-an`; m4a: aac 192k; wav: pcm_s16le). Progress uses the kept duration. Bad intervals (empty, `start < 0`, `end <= start`) → `ValueError`. Fake: `wav` target copies `<media_root>/audio.wav`, other targets copy `src`.

### C4. SponsorBlock source (`core/download.py`, `core/extractor.py`, T4)
```python
SponsorSegment = tuple[int, int, str]          # (startMs, endMs, category)
class SponsorBlockError(Exception): ...        # unreachable / bad answer / unknown duration (never a YtError)
@runtime_checkable
class SponsorSource(Protocol):
    def sponsor_segments(self, video_id: str, categories: Sequence[str],
                         duration_s: float | None) -> list[SponsorSegment]: ...
```
`YtDlpExtractor.sponsor_segments`: `_check_video_id`; `duration_s` falsy → `SponsorBlockError("duration unknown")`; `self._ydl({**_PROBE_OPTS, "extractor_retries": 1})` (no session); `SponsorBlockPP(ydl, list(categories)).run({"id", "extractor_key": "Youtube", "duration"})`; any exception → `SponsorBlockError(type(exc).__name__)`; keep `type == "skip"` and requested categories; ms = `round(seconds * 1000)`; keep `end > start`; sorted.
`FakeExtractor.sponsor_segments`: reads `tests/fixtures/sponsorblock/<videoId>.json`: missing file = `[]`; `{"error": "..."}` = `SponsorBlockError`; `{"segments": [[startMs, endMs, "category"], ...]}` filtered by categories. Records `("sponsor_segments", video_id)` in `calls`.
Fake clips added to `behaviors.json` (all `probeAs` existing fixtures, default steps):

| id | probeAs | title | SponsorBlock fixture |
|---|---|---|---|
| `RANGECLIP01` | `aqz-KE-bpKQ` | คลิปช่วงเวลา | — |
| `ADSCUTCLIP1` | `aqz-KE-bpKQ` | คลิปมีช่วงโฆษณา | `{"segments": [[0, 12000, "intro"], [60000, 90000, "sponsor"], [600000, 635000, "outro"]]}` |
| `ADSNODATA01` | `aqz-KE-bpKQ` | คลิปไม่มีข้อมูลโฆษณา | (no file) |
| `ADSOFFLINE1` | `aqz-KE-bpKQ` | คลิปที่ติดต่อ SponsorBlock ไม่ได้ | `{"error": "unreachable"}` |
| `CHAPTERS001` | `jNQXAC9IVRw` | คลิปมี 3 chapter | — |

### C5. Subtitle range (`core/srt_builder.py`, `core/subtitles.py`, `web/src/lib/srt-builder.ts`, T5)
```python
def range_tokens(tokens: Sequence[Token], start_ms: int, end_ms: int) -> list[Token]
    # keep tokens whose midpoint is in [start, end): 2*start <= s + e < 2*end (integer maths)
    # s' = max(s, start) - start, e' = min(e, end) - start
def clamp_cues(cues: Sequence[Cue], limit_ms: int) -> list[Cue]    # end = min(end, limit)
SubtitleService.export(video_id, track_id, fmt, opts, range_ms: tuple[int, int] | None = None) -> SubtitleExport
    # srt/txt: to_srt(clamp_cues(build_cues(range_tokens(...)), end - start)); md + range -> ValueError
```
```ts
export function rangeTokens(tokens: readonly SubToken[], startMs: number, endMs: number): SubToken[]
export function clampCues(cues: readonly Cue[], limitMs: number): Cue[]
```
Parity fixtures (JSON, CRLF kept inside strings): `tests/fixtures/subs/range-cases.json` (hand cases, C5 table in T5) and `tests/fixtures/subs/range-golden.json` (`th-asr` and `en-asr` medium preset, 90000-210000, generated from the Python builder once).

### C6. Handler behaviour (`core/handlers.py`, T8 + T13)
- `HandlerDeps.sponsors: SponsorSource | None = None` (T8); `lifecycle.open_services` passes `sponsors=extractor` (T13). `None` = treated as unreachable.
- `CUT_DISK_FACTOR = 3` for any job with a range, SponsorBlock data or chapter split; otherwise `DISK_FACTOR = 2`.
- Stages: `cutting` (range only), `cutting_ads` (ads cut), `splitting:<i>/<n>` per chapter, then the M4 stages (`converting`, `writing`).
- Notes: `SPONSORBLOCK_UNREACHABLE` (fetch failed or no source), `SPONSORBLOCK_EMPTY` (fetched, nothing cut), `NO_CHAPTERS` (split asked, < 2 usable chapters).
- `JobResult.outputs` = one file, or every chapter file in chapter order (kind `video` / `audio`); `แหล่งที่มา.txt` goes to the clip folder.
- Chapter files: metadata `title` = chapter title (empty → `chapter <n>`), `track` = `n/total`.

### C7. Web types and builders (`web/src/lib/types.ts`, `web/src/lib/download-options.ts`, T6)
```ts
export type TimeRange = { startMs: number; endMs: number }
export type SponsorCategory = "sponsor" | "selfpromo" | "interaction" | "intro" | "outro" | "preview" | "filler" | "music_offtopic"
// VideoJobParams / AudioJobParams: splitChapters: boolean; range?: TimeRange; sponsorblock?: SponsorCategory[]
// SubtitleJobParams: range?: TimeRange
export const SPONSOR_CATEGORIES: readonly SponsorCategory[]           // C1 order
export const DEFAULT_SPONSOR_CATEGORIES: readonly SponsorCategory[]   // sponsor, selfpromo, interaction
export function sponsorCategories(s: Pick<Settings, "sponsorblockDefault"> | undefined): SponsorCategory[]
export type AdvancedParams = { range?: TimeRange; splitChapters: boolean; sponsorblock?: SponsorCategory[] }
export const NO_ADVANCED: AdvancedParams                                // { splitChapters: false }
buildVideoParams(input & { advanced?: AdvancedParams }): VideoJobParams // splitChapters -> never embedSubs
buildAudioParams(input & { advanced?: AdvancedParams }): AudioJobParams
export function buildSubtitleParams(input: { trackId: string; format: SubExportFormat; options: SubOptions; range?: TimeRange | null }): SubtitleJobParams
```
`useDownloadState` (T6) returns `{ state, languages, remember, cap, ready }` (`ready = !settings.isPending`). `JobStage` is widened in wave 2 by T12 (`"cutting" | "cutting_ads" | \`splitting:${number}/${number}\``).

### C8. Thai strings (`web/src/i18n/th.ts`, T6 writes them verbatim; nobody else edits `th.ts`)
```ts
advanced: {
  title: "ตัวเลือกขั้นสูง",
  active: "ใช้ตัวเลือกขั้นสูงอยู่",
  range: "ช่วงเวลา",
  start: "เริ่ม",
  end: "จบ",
  usePlayerTime: "ใช้เวลาที่ตัวเล่นอยู่ตอนนี้",
  playFirst: "กดเล่นคลิปก่อน",
  errors: {
    format: "พิมพ์เวลาแบบ 1:30 หรือ 1:02:30",
    order: "จุดเริ่มต้องมาก่อนจุดจบ",
    beyond: "เกินความยาวคลิป ({duration})",
    tooShort: "ช่วงต้องยาวอย่างน้อย 1 วินาที",
  },
  rangeUnavailable: "คลิปสดหรือคลิปที่ไม่รู้ความยาว ตั้งช่วงเวลาไม่ได้",
  exactHint: "ตัดตรงจุดที่ตั้งเป๊ะ ใช้เวลาแปลงไฟล์เพิ่ม",
  setStart: "ตั้งจุดเริ่ม",
  setEnd: "ตั้งจุดจบ",
  startSet: "ตั้งจุดเริ่มที่ {time} แล้ว",
  endSet: "ตั้งจุดจบที่ {time} แล้ว",
  frameStart: "ตั้งเป็นจุดเริ่ม",
  frameEnd: "ตั้งเป็นจุดจบ",
  chapters: "แยกไฟล์ตาม chapter",
  chaptersHint: "ได้ไฟล์ละ 1 chapter ในโฟลเดอร์ย่อย",
  chaptersVideoHint: " · ขอบแต่ละ chapter อาจคลาด 1-3 วินาที",
  blocked: {
    range: "ใช้คู่กับช่วงเวลาไม่ได้ ล้างช่วงเวลาก่อน",
    sponsorblock: "ใช้คู่กับตัดโฆษณาไม่ได้",
    embedSubs: "ใช้คู่กับฝังซับไม่ได้",
    chapters: "ปิด 'แยกไฟล์ตาม chapter' ก่อน",
  },
  sponsorblock: "ตัดโฆษณา (SponsorBlock)",
  sponsorblockHint: "ใช้ข้อมูลที่ผู้ชมช่วยกันมาร์ก คลิปที่ไม่มีข้อมูลจะได้คลิปเต็ม",
  categories: {
    sponsor: "ช่วงสปอนเซอร์",
    selfpromo: "ช่วงโปรโมตตัวเอง",
    interaction: "ช่วงขอให้กดติดตามหรือไลก์",
    intro: "ช่วงเปิดรายการ",
    outro: "ช่วงปิดท้าย",
    preview: "ช่วงตัวอย่างหรือสรุปซ้ำ",
    filler: "ช่วงนอกเรื่อง",
    music_offtopic: "ช่วงที่ไม่ใช่เพลง (คลิปเพลง)",
  },
  subsWarning: "เวลาซับจะไม่ตรงกับวิดีโอที่ตัดโฆษณาแล้ว",
  choiceChapters: "แยก chapter",
  choiceAds: "ตัดโฆษณา",
  withChoice: "{label} ({choice})",
  previewTitle: "{title} ({range})",
},
// queue (additions inside the existing `queue` object)
stages: { ...existing six..., cutting: "กำลังตัดช่วง", cutting_ads: "กำลังตัดโฆษณา" },
splitting: "กำลังแยก chapter {i}/{n}",
choice: { range: " · ช่วง {range}", chapters: " · แยก chapter", ads: " · ตัดโฆษณา" },
```
Labels produced from these: `โหลด mp4 (1:30-5:00)`, `โหลด m4a (1:30-5:00)`, `โหลด .srt (1:30-5:00)`, `โหลด .txt (1:30-5:00)`, `โหลด mp4 (แยก chapter)`, `โหลด mp4 (ตัดโฆษณา)`, `โหลด mp4 (1:30-5:00, ตัดโฆษณา)`; preview title `ตัวอย่าง 5 ซับแรก (1:30-5:00)`; toast `ตั้งจุดเริ่มที่ 1:30 แล้ว`. Times use `formatDuration` (`M:SS` / `H:MM:SS`). Category-save failure reuses `th.general.saveFailed`.

### C9. Advanced logic and per-clip store (`web/src/lib/advanced-options.ts`, `web/src/pages/video/advanced/advanced-store.ts`, T7)
```ts
export type ClipRange = { startMs: number; endMs: number }
// whole-second input: start < end already means >= 1 s, so the spec's "ช่วงต้องยาวอย่างน้อย 1 วินาที"
// (th.advanced.errors.tooShort) can never be produced by the UI; it stays in th.ts and the API enforces the rule
export type RangeError = "format" | "order" | "beyond"
export type RangeCheck = { range: ClipRange | null; startError: RangeError | null; endError: RangeError | null }
export function parseClock(text: string): number | null                  // seconds; ss | m:ss | mm:ss | h:mm:ss
export function validateRange(startText: string, endText: string, durationS: number): RangeCheck
export function rangeAvailable(video: Pick<VideoInfo, "isLive" | "durationS">): boolean
export function chaptersAvailable(video: Pick<VideoInfo, "chapters">): boolean   // >= 2
export function rangeText(range: ClipRange): string                     // "1:30-5:00"
export function keptSeconds(range: ClipRange): number
export function scaleBytes(bytes: number | undefined, durationS: number, keptS: number | undefined): number | undefined
export type ChoicePart = { kind: "range"; range: ClipRange } | { kind: "chapters" } | { kind: "ads" }
export function choiceParts(o: { range: ClipRange | null; splitChapters: boolean; ads: boolean }): ChoicePart[]
export type ChapterBlock = "range" | "sponsorblock" | "embedSubs"
export function chapterBlock(v: { startText: string; endText: string; sponsorblock: boolean }, embedSubsOn: boolean): ChapterBlock | null
```
```ts
export type AdvancedValues = { startText: string; endText: string; splitChapters: boolean; sponsorblock: boolean; open: boolean; checked: boolean }
export const EMPTY_ADVANCED: AdvancedValues
export function getAdvanced(videoId: string): AdvancedValues        // other clip = EMPTY_ADVANCED (stable reference)
export function advancedActive(v: AdvancedValues): boolean          // any text, chapters or SponsorBlock
export const advancedActions: {
  patch(videoId: string, patch: Partial<AdvancedValues>): void
  mark(videoId: string, which: "start" | "end", ms: number): "set" | "blocked"   // blocked while splitChapters
}
export function useAdvanced(videoId: string): AdvancedValues
export function __resetAdvancedForTests(): void
```

### C10. Queue text (`web/src/components/queue/job-text.ts`, T12)
```ts
export function stageText(stage: JobStage): string            // "splitting:3/12" -> "กำลังแยก chapter 3/12"
export function jobChoice(params: JobParams): string           // " · ช่วง 1:30-5:00 · ตัดโฆษณา" ("" when none)
export const jobTitle: (job: Pick<Job, "title" | "videoId"> & { params?: JobParams }) => string   // title + jobChoice
```

### C11. E2E ids and files
Chromium specs (mocked enqueue): `web/e2e/advanced-options.spec.ts` (T10), `web/e2e/range-marks.spec.ts` (T11), extra assertions in `web/e2e/download-tabs.spec.ts` (T10). Queue spec (real fake backend): `web/e2e/queue-advanced.spec.ts` (T14) using only the C4 fake ids.

---

## File structure

**Backend (new):** `src/yttoolkit/core/advanced.py` (T2) keep intervals, chapter parts, range suffix.
**Backend (modified):** `core/jobs.py`, `core/queue.py`, `core/settings.py`, `core/videos.py`, `api/jobs.py` (T1) · `core/files.py` (T2) · `core/media.py` (T3) · `core/download.py`, `core/extractor.py` (T4) · `core/srt_builder.py`, `core/subtitles.py` (T5) · `core/handlers.py` (T8, T13) · `lifecycle.py` (T9, T13).
**Fixtures (new):** `tests/fixtures/sponsorblock/ADSCUTCLIP1.json`, `ADSOFFLINE1.json` (T4) · `tests/fixtures/subs/range-cases.json`, `range-golden.json` (T5).
**Tests (new):** `tests/unit/test_advanced.py` (T2), `tests/integration/test_cut_ffmpeg.py` (T3), `tests/unit/test_sponsorblock.py` (T4), `tests/unit/test_srt_range.py` (T5), `tests/network/test_advanced_network.py` (T15).
**Web (new):** `web/src/lib/advanced-options.ts` + test, `web/src/pages/video/advanced/advanced-store.ts` + test (T7) · `web/src/pages/video/advanced/{switch-row.tsx, use-advanced-choice.ts, range-fields.tsx, sponsor-controls.tsx, advanced-section.tsx}` (T10) · `web/src/pages/video/player/range-mark-buttons.tsx` (T11) · `web/src/lib/srt-range.test.ts` (T5) · e2e specs (C11).
**Web (modified):** `types.ts`, `download-options.ts` (+test), `th.ts`, `use-download-state.ts` (+test) (T6) · `srt-builder.ts` (T5) · `video-panel.tsx`, `audio-panel.tsx`, `subs-panel.tsx`, `subs/export-buttons.tsx`, `subs/preview.tsx` (T10) · `player-slot.tsx`, `frames.tsx` (T11) · `types.ts` (`JobStage`), `job-text.ts` (+test) (T12).
**Docs (modified, T15):** `PRD.md`, `BRD.md`, `docs/acceptance.md`, `docs/m4-followups.md`, `tests/network_videos.toml`.

---

## Wave 1

### Task 1: Job params, notes, stages, settings categories, cached-probe check

**Files:**
- Modify: `src/yttoolkit/core/jobs.py` (imports, `STAGES`, new constants and functions, `NOTES`, `_encode`)
- Modify: `src/yttoolkit/core/queue.py:29` (import) and `:97-98` (`_JobContext.stage`)
- Modify: `src/yttoolkit/core/settings.py:30` (drop `SPONSOR_CATEGORY`), `:122-125` (`_validate_sponsorblock`)
- Modify: `src/yttoolkit/core/videos.py` (add `VideoService.peek_cached` after `get`)
- Modify: `src/yttoolkit/api/jobs.py` (models, `clip_problem`, `create_jobs`)
- Modify: `tests/api/test_jobs_api.py`, `tests/unit/test_jobs_store.py`, `tests/unit/test_queue.py`, `tests/unit/test_settings.py`, `tests/unit/test_videos.py`

**Interfaces:**
- Consumes: M4 `JobStore`, `QueueRunner`, `SettingsStore`, `VideoService._stored_hit`, `api.errors.error_response`, `api.errors.BAD_REQUEST_MESSAGE`.
- Produces: C1 exactly (`STAGES`, `SPLIT_STAGE`, `split_stage`, `is_stage`, `SPONSORBLOCK_CATEGORIES`, `MIN_RANGE_MS`, `RANGE_TOLERANCE_MS`, three `NOTES`), `VideoService.peek_cached(video_id) -> dict | None`, `api.jobs.clip_problem(params, info) -> str | None`.

- [ ] **Step 1: Write the failing store, queue, settings and videos tests**

Append to `tests/unit/test_jobs_store.py` (extend the existing `from yttoolkit.core.jobs import …` line with `NOTES, is_stage, split_stage`):
```python
def test_m5a_stages_are_stored(store):
    (job,) = add(store)
    store.transition(job.id, "running")
    for stage in ("cutting", "cutting_ads", split_stage(3, 12)):
        assert store.update(job.id, stage=stage).stage == stage
    with pytest.raises(ValueError):
        store.update(job.id, stage="splitting:x/12")


def test_is_stage_and_split_stage_bounds():
    assert is_stage("writing") and is_stage("cutting_ads") and is_stage("splitting:1/2")
    assert not is_stage("splitting:1/2/3") and not is_stage("splitting:") and not is_stage("nope")
    assert split_stage(1, 1) == "splitting:1/1"
    for bad in ((0, 3), (4, 3), (1, 10_000)):
        with pytest.raises(ValueError):
            split_stage(*bad)


def test_m5a_notes_are_verbatim():
    assert NOTES["SPONSORBLOCK_EMPTY"] == "ไม่มีข้อมูลจากชุมชน ได้คลิปเต็ม"
    assert NOTES["SPONSORBLOCK_UNREACHABLE"] == "ติดต่อ SponsorBlock ไม่ได้ ได้คลิปเต็ม"
    assert NOTES["NO_CHAPTERS"] == "คลิปนี้ไม่มี chapter ได้ไฟล์เต็ม"
```
Append to `tests/unit/test_queue.py`:
```python
def test_context_accepts_m5a_stages(runner_factory):
    seen: list[str | None] = []

    def handler(job, ctx):
        for stage in ("cutting", "cutting_ads", "splitting:2/3"):
            ctx.stage(stage)
            seen.append(r.store.get(job.id).stage)
        return JobResult()

    r, spawn, _ = runner_factory(handler=handler)
    (job,) = r.enqueue(jobs_of("frames_zip", 1))
    r.tick()
    spawn.run_all()
    assert seen == ["cutting", "cutting_ads", "splitting:2/3"]
    assert r.store.get(job.id).status == "done"


def test_context_rejects_an_unknown_stage(runner_factory):
    def handler(job, ctx):
        ctx.stage("splitting:x")
        return JobResult()

    r, spawn, _ = runner_factory(handler=handler)
    (job,) = r.enqueue(jobs_of("frames_zip", 1))
    r.tick()
    spawn.run_all()
    assert (r.store.get(job.id).status, r.store.get(job.id).error_code) == ("failed", "E_UNKNOWN")
```
In `tests/unit/test_settings.py`, add these rows to the `bad` parametrize list of `test_invalid_patch_is_rejected_and_changes_nothing` (keep the existing two `sponsorblockDefault` rows):
```python
        {"sponsorblockDefault": []},
        {"sponsorblockDefault": ["sponsor", "poi_highlight"]},
        {"sponsorblockDefault": ["chapter"]},
```
and append:
```python
def test_sponsorblock_default_keeps_order_and_drops_duplicates(store):
    saved = store.patch({"sponsorblockDefault": ["filler", "sponsor", "filler", "music_offtopic"]})
    assert saved["sponsorblockDefault"] == ["filler", "sponsor", "music_offtopic"]
```
Append to `tests/unit/test_videos.py`:
```python
def test_peek_cached_reads_the_stored_row_without_probing_or_opening(
    svc: VideoService, ext: CountingExtractor, db: Database, clock: Clock
) -> None:
    assert svc.peek_cached("aqz-KE-bpKQ") is None
    assert svc.peek_cached("not an id") is None
    svc.get("aqz-KE-bpKQ", peek=True)
    opened = db.execute("SELECT opened_at FROM videos WHERE video_id = 'aqz-KE-bpKQ'")[0]["opened_at"]
    clock.advance(days=3)  # older than the 24 h cache: still returned
    info = svc.peek_cached("aqz-KE-bpKQ")
    assert info is not None and info["durationS"] == 635 and info["chapters"] == []
    assert ext.count["probe"] == 1
    assert db.execute("SELECT opened_at FROM videos WHERE video_id = 'aqz-KE-bpKQ'")[0]["opened_at"] == opened
```

- [ ] **Step 2: Run them, expect FAIL**

Run: `uv run pytest tests/unit/test_jobs_store.py tests/unit/test_queue.py tests/unit/test_settings.py tests/unit/test_videos.py -q -W error -p no:cacheprovider`
Expected: FAIL (`ImportError: cannot import name 'is_stage'`, `AttributeError: … 'peek_cached'`, the new settings rows are accepted).

- [ ] **Step 3: Implement `core/jobs.py`, `core/queue.py`, `core/settings.py`, `core/videos.py`**

`core/jobs.py` — add `import re` to the imports and replace the `STAGES` line:
```python
STAGES = (
    "probing", "downloading_video", "downloading_audio", "merging", "converting", "writing",
    "cutting", "cutting_ads",
)  # fmt: skip
# "splitting:<i>/<n>" = กำลังแยก chapter ที่ i จาก n (M5 รอบ A) หน้าเว็บแสดง "กำลังแยก chapter i/n"
SPLIT_STAGE = re.compile(r"splitting:(\d{1,4})/(\d{1,4})")
```
`NOTES` gains (keep the four M4 entries):
```python
    "SPONSORBLOCK_EMPTY": "ไม่มีข้อมูลจากชุมชน ได้คลิปเต็ม",
    "SPONSORBLOCK_UNREACHABLE": "ติดต่อ SponsorBlock ไม่ได้ ได้คลิปเต็ม",
    "NO_CHAPTERS": "คลิปนี้ไม่มี chapter ได้ไฟล์เต็ม",
```
After `NOTES`:
```python
# ตัวเลือกขั้นสูงของงานโหลด (M5 รอบ A) ที่ API ตรวจและตัวทำงานใช้ร่วมกัน
SPONSORBLOCK_CATEGORIES = (
    "sponsor", "selfpromo", "interaction", "intro", "outro", "preview", "filler", "music_offtopic",
)  # fmt: skip
MIN_RANGE_MS = 1000  # ช่วงเวลาต้องยาวอย่างน้อย 1 วินาที
RANGE_TOLERANCE_MS = 500  # ความยาวคลิปเก็บเป็นวินาทีปัดเศษ ปลายช่วงจึงเกินได้ไม่เกินครึ่งวินาที


def split_stage(index: int, total: int) -> str:
    """ขั้นของการแยกไฟล์ตาม chapter: "splitting:<i>/<n>" (1 <= i <= n <= 9999)"""
    if not 1 <= index <= total <= 9999:
        raise ValueError(f"split stage out of range: {index}/{total}")
    return f"splitting:{index}/{total}"


def is_stage(value: str) -> bool:
    return value in STAGES or SPLIT_STAGE.fullmatch(value) is not None
```
In `_encode` replace `value not in STAGES` with `not is_stage(value)`.
`core/queue.py`: in the `from .jobs import …` line replace `STAGES` with `is_stage`; in `_JobContext.stage` replace `if stage not in STAGES:` with `if not is_stage(stage):`.
`core/settings.py`: delete the `SPONSOR_CATEGORY = re.compile(...)` line (keep `import re`, `LANGUAGE_TAG` still uses it), add `from .jobs import SPONSORBLOCK_CATEGORIES`, and replace `_validate_sponsorblock`:
```python
def _validate_sponsorblock(value: Any) -> list[str]:
    """หมวด SponsorBlock ที่ติ๊กไว้ (D3 จำข้ามคลิป): ต้องมีอย่างน้อย 1 หมวด และเป็นหมวดที่ตัดได้เท่านั้น"""
    if (
        not isinstance(value, list)
        or not value
        or not all(isinstance(v, str) and v in SPONSORBLOCK_CATEGORIES for v in value)
    ):
        raise _bad("sponsorblockDefault", "must be a non-empty list of SponsorBlock categories")
    return list(dict.fromkeys(value))
```
`core/videos.py`, in `VideoService` right after `get`:
```python
    def peek_cached(self, video_id: str) -> dict | None:
        """VideoInfo ที่เก็บไว้ (ไม่ดูอายุ ไม่ probe ไม่นับว่าเปิดคลิป) ใช้ตรวจค่าของงานตอนส่งเข้าคิว
        id ผิดรูปแบบ ไม่มีแถว หรือแถวเสีย = None"""
        if not VIDEO_ID.fullmatch(video_id):
            return None
        return self._stored_hit(video_id, peek=True)
```

- [ ] **Step 4: Run the Step 1 tests, expect PASS** (same command as Step 2).

- [ ] **Step 5: Write the failing API tests**

In `tests/api/test_jobs_api.py`, remove these three rows from the `item` parametrize list of `test_post_rejects_bad_items` (valid in M5-A; the `range` row with `startS`, the `useCookies`, `contact_sheet` `source: "sharp"` and `frames_sharp` rows stay):
```python
        {"videoId": "aqz-KE-bpKQ", "kind": "video", "params": {"splitChapters": True}},
        {"videoId": "aqz-KE-bpKQ", "kind": "audio", "params": {"format": "m4a", "splitChapters": True}},
        {"videoId": "aqz-KE-bpKQ", "kind": "video", "params": {"sponsorblock": ["sponsor"]}},
```
Then add imports and tests:
```python
from yttoolkit.core.extractor import FakeExtractor
from yttoolkit.core.videos import VideoService

VIDEO = {"maxQuality": False, "splitChapters": False, "noAudio": False, "audioLanguage": "original"}
RANGE = {"startMs": 90_000, "endMs": 300_000}


def video_item(video_id: str = "aqz-KE-bpKQ", **params) -> dict:
    return {"videoId": video_id, "kind": "video", "params": {**VIDEO, **params}}


def test_post_accepts_m5a_advanced_params(env):
    items = [
        video_item(range=RANGE),
        video_item(sponsorblock=["sponsor", "filler"]),
        video_item("jNQXAC9IVRw", splitChapters=True),
        {"videoId": "aqz-KE-bpKQ", "kind": "audio",
         "params": {"format": "mp3", "range": RANGE, "sponsorblock": ["intro"]}},
        {"videoId": "jNQXAC9IVRw", "kind": "audio", "params": {"format": "m4a", "splitChapters": True}},
        {"videoId": "88o5Sk8_m1Y", "kind": "subtitle",
         "params": {"trackId": "a.th-orig", "format": "txt", "options": SUB_OPTIONS, "range": RANGE}},
    ]
    resp = env.client().post("/api/jobs", json={"items": items}, headers=AUTH)
    assert resp.status_code == 200, resp.text
    stored = [job["params"] for job in resp.json()["jobs"]]
    assert stored[0] == {**VIDEO, "range": RANGE}
    assert stored[1] == {**VIDEO, "sponsorblock": ["sponsor", "filler"]}
    assert stored[2] == {**VIDEO, "splitChapters": True}
    assert stored[3] == {"format": "mp3", "mp3Kbps": 192, "splitChapters": False, "audioLanguage": "original",
                         "range": RANGE, "sponsorblock": ["intro"]}
    assert stored[4] == {"format": "m4a", "splitChapters": True, "audioLanguage": "original"}
    assert stored[5]["range"] == RANGE


@pytest.mark.parametrize(
    "params",
    [
        {"range": {"startMs": 90_000}},
        {"range": {**RANGE, "x": 1}},
        {"range": {"startMs": 90_500, "endMs": 300_000}},
        {"range": {"startMs": -1000, "endMs": 3000}},
        {"range": {"startMs": 5000, "endMs": 5000}},
        {"range": {"startMs": 6000, "endMs": 5000}},
        {"range": {"startMs": 1000.0, "endMs": 5000}},
        {"range": {"startMs": True, "endMs": 5000}},
        {"range": {"startMs": "1000", "endMs": 5000}},
        {"sponsorblock": []},
        {"sponsorblock": ["sponsor", "sponsor"]},
        {"sponsorblock": ["poi_highlight"]},
        {"sponsorblock": "sponsor"},
        {"splitChapters": "yes"},
        {"splitChapters": True, "range": RANGE},
        {"splitChapters": True, "sponsorblock": ["sponsor"]},
        {"splitChapters": True, "embedSubs": "o.th", "subOptions": SUB_OPTIONS},
    ],
)
def test_post_rejects_bad_advanced_video_params(env, params):
    resp = env.client().post("/api/jobs", json={"items": [video_item(**params)]}, headers=AUTH)
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "E_BAD_REQUEST"
    assert env.store.pending_count() == 0


@pytest.mark.parametrize(
    "item",
    [
        {"videoId": "aqz-KE-bpKQ", "kind": "audio", "params": {"format": "m4a", "splitChapters": True, "range": RANGE}},
        {"videoId": "aqz-KE-bpKQ", "kind": "subtitle", "params": {"format": "md", "options": SUB_OPTIONS, "range": RANGE}},
        {"videoId": "aqz-KE-bpKQ", "kind": "subtitle",
         "params": {"format": "srt", "options": SUB_OPTIONS, "sponsorblock": ["sponsor"]}},
        {"videoId": "aqz-KE-bpKQ", "kind": "subtitle",
         "params": {"format": "srt", "options": SUB_OPTIONS, "splitChapters": True}},
    ],
)
def test_post_rejects_bad_advanced_audio_and_subtitle_params(env, item):
    resp = env.client().post("/api/jobs", json={"items": [item]}, headers=AUTH)
    assert resp.status_code == 422


@pytest.fixture
def cached(env):
    """AppContext overrides with a VideoService whose probe cache holds two clips
    (the videos router also needs extractor and cache_root, see api/videos.build_videos_router)"""
    fake = FakeExtractor(FIXTURES)
    videos = VideoService(env.db, fake)
    videos.get("aqz-KE-bpKQ")  # 635 s, no chapters
    videos.get("jNQXAC9IVRw")  # 19 s, 3 chapters
    return {"videos": videos, "extractor": fake, "cache_root": env.tmp / "cache"}


@pytest.mark.parametrize(
    ("item", "status"),
    [
        (video_item(range={"startMs": 0, "endMs": 635_000}), 200),
        (video_item(range={"startMs": 600_000, "endMs": 636_000}), 422),
        (video_item("jNQXAC9IVRw", range={"startMs": 0, "endMs": 19_000}), 200),
        (video_item("jNQXAC9IVRw", range={"startMs": 0, "endMs": 20_000}), 422),
        (video_item(splitChapters=True), 422),
        (video_item("jNQXAC9IVRw", splitChapters=True), 200),
        ({"videoId": "aqz-KE-bpKQ", "kind": "audio", "params": {"format": "wav", "splitChapters": True}}, 422),
        (video_item("88o5Sk8_m1Y", range={"startMs": 0, "endMs": 999_000}), 200),  # not cached: the handler checks
        (video_item("88o5Sk8_m1Y", splitChapters=True), 200),
    ],
)
def test_post_checks_range_and_chapters_against_a_cached_probe(env, cached, item, status):
    resp = env.client(**cached).post("/api/jobs", json={"items": [item]}, headers=AUTH)
    assert resp.status_code == status, resp.text
    if status == 422:
        assert resp.json()["error"]["code"] == "E_BAD_REQUEST"
        assert item["videoId"] in resp.json()["error"]["detail"]
        assert env.store.pending_count() == 0


def test_post_rejects_a_range_on_a_clip_without_a_known_duration(env, cached, monkeypatch):
    videos = cached["videos"]
    monkeypatch.setattr(videos, "peek_cached", lambda video_id: {"durationS": 0, "isLive": False, "chapters": []})
    resp = env.client(**cached).post("/api/jobs", json={"items": [video_item(range=RANGE)]}, headers=AUTH)
    assert resp.status_code == 422
    monkeypatch.setattr(videos, "peek_cached", lambda video_id: {"durationS": 900, "isLive": True, "chapters": []})
    resp = env.client(**cached).post("/api/jobs", json={"items": [video_item(range=RANGE)]}, headers=AUTH)
    assert resp.status_code == 422
```

- [ ] **Step 6: Run them, expect FAIL** — `uv run pytest tests/api/test_jobs_api.py -q -W error -p no:cacheprovider` (M5-A params still 422; no cached checks).

- [ ] **Step 7: Implement `api/jobs.py`**

Imports: add `from collections.abc import Mapping`; add `StrictBool, StrictInt` to the pydantic import; extend the `..core.jobs` import with `MIN_RANGE_MS, RANGE_TOLERANCE_MS, SPONSORBLOCK_CATEGORIES`; add `BAD_REQUEST_MESSAGE` to the `.errors` import. Change docstring line 4 to `ค่าของงานแต่ละชนิด (C3 + M5 รอบ A) ตรวจด้วย pydantic: key ที่ไม่รู้จัก คุกกี้ และภาพคม = 422`.

Add after `_audio_language`:
```python
class RangeModel(_Strict):
    """ช่วงเวลาของงาน (M5 รอบ A): มิลลิวินาทีเต็มวินาที เริ่มก่อนจบอย่างน้อย 1 วินาที"""

    startMs: StrictInt = Field(ge=0)
    endMs: StrictInt

    @model_validator(mode="after")
    def _whole_seconds(self) -> RangeModel:
        if self.startMs % 1000 or self.endMs % 1000:
            raise ValueError("range must be whole seconds (multiples of 1000 ms)")
        if self.endMs - self.startMs < MIN_RANGE_MS:
            raise ValueError("range must start before it ends and last at least 1 second")
        return self


def _sponsor_categories(value: list[str] | None) -> list[str] | None:
    if value is None:
        return None
    if not value:
        raise ValueError("sponsorblock must list at least one category")
    if len(set(value)) != len(value):
        raise ValueError("sponsorblock categories must be unique")
    unknown = [v for v in value if v not in SPONSORBLOCK_CATEGORIES]
    if unknown:
        raise ValueError(f"unknown sponsorblock categories: {unknown}")
    return value


class _CutOptions(_Grouped):
    """ตัวเลือกขั้นสูงของงานวิดีโอและเสียง: แยกตาม chapter ใช้คู่กับช่วงเวลาหรือตัดโฆษณาไม่ได้"""

    range: RangeModel | None = None
    sponsorblock: list[str] | None = None
    splitChapters: StrictBool = False

    _sponsorblock = field_validator("sponsorblock")(_sponsor_categories)

    @model_validator(mode="after")
    def _chapters_alone(self) -> _CutOptions:
        if self.splitChapters and (self.range is not None or self.sponsorblock is not None):
            raise ValueError("splitChapters cannot be combined with range or sponsorblock")
        return self
```
`VideoParams` becomes `class VideoParams(_CutOptions):` (delete its `splitChapters` line) and its validator becomes:
```python
    @model_validator(mode="after")
    def _embed_rules(self) -> VideoParams:
        if self.embedSubs is not None and self.subOptions is None:
            raise ValueError("embedSubs requires subOptions")
        if self.embedSubs is not None and self.splitChapters:
            raise ValueError("embedSubs cannot be combined with splitChapters")  # AC-VID-10 part 2
        return self
```
`AudioParams` becomes `class AudioParams(_CutOptions):` (delete its `splitChapters` line). `SubtitleParams` gains:
```python
    range: RangeModel | None = None

    @model_validator(mode="after")
    def _range_formats(self) -> SubtitleParams:
        if self.range is not None and self.format == "md":
            raise ValueError("range works with srt and txt only")
        return self
```
Add after `OrderBody`:
```python
def clip_problem(params: Mapping[str, Any], info: Mapping[str, Any] | None) -> str | None:
    """ตรวจช่วงเวลาและการแยก chapter กับข้อมูลคลิปที่เก็บไว้ (C1) ไม่มีข้อมูล = None (ตัวทำงานตรวจอีกรอบ)"""
    rng = params.get("range")
    split = bool(params.get("splitChapters"))
    if info is None or (rng is None and not split):
        return None
    if rng is not None:
        duration_ms = int(info.get("durationS") or 0) * 1000
        if info.get("isLive") or duration_ms <= 0:
            return "range needs a clip with a known duration"
        if rng["endMs"] > duration_ms + RANGE_TOLERANCE_MS:
            return f"range ends after the clip ({duration_ms} ms)"
    if split and len(info.get("chapters") or []) < 2:
        return "splitChapters needs a clip with at least 2 chapters"
    return None
```
In `create_jobs`, after the ffmpeg check and before `queue.enqueue(...)`:
```python
        videos = ctx.videos
        if videos is not None:
            for item in body.items:
                if "range" not in item.params and not item.params.get("splitChapters"):
                    continue
                problem = clip_problem(item.params, videos.peek_cached(item.videoId))
                if problem is not None:
                    return error_response(422, "E_BAD_REQUEST", BAD_REQUEST_MESSAGE, f"{item.videoId}: {problem}")
```

- [ ] **Step 8: Run the API tests, then the full suite, expect PASS** — `uv run pytest tests/api/test_jobs_api.py -q -W error -p no:cacheprovider` then `uv run pytest -q -W error -p no:cacheprovider`.

- [ ] **Step 9: Commit**
```bash
git add src/yttoolkit/core/jobs.py src/yttoolkit/core/queue.py src/yttoolkit/core/settings.py src/yttoolkit/core/videos.py src/yttoolkit/api/jobs.py tests/api/test_jobs_api.py tests/unit/test_jobs_store.py tests/unit/test_queue.py tests/unit/test_settings.py tests/unit/test_videos.py
git commit -F- <<'EOF'
feat(jobs): M5-A params (range, sponsorblock, splitChapters), notes, cut/split stages

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
EOF
```

### Task 2: Keep-interval maths, chapter parts and output names

**Files:**
- Create: `src/yttoolkit/core/advanced.py`, `tests/unit/test_advanced.py`
- Modify: `src/yttoolkit/core/files.py` (constants, `plan_output`, new `chapter_dir_name`, `plan_chapter_output`)
- Modify: `tests/unit/test_files.py`

**Interfaces:**
- Consumes: `files.safe_component`, `files.truncate_title`, `files._u16`, `YtError`.
- Produces: C2 exactly.

- [ ] **Step 1: Write the failing tests** — `tests/unit/test_advanced.py`:
```python
"""คณิตของตัวเลือกขั้นสูง (M5 รอบ A): ช่วงที่เก็บไว้ ช่วงของ chapter และส่วนต่อท้ายชื่อไฟล์"""

from __future__ import annotations

import pytest

from yttoolkit.core.advanced import (
    ADS_SUFFIX,
    MIN_PIECE_MS,
    ChapterPart,
    chapter_parts,
    keep_intervals,
    kept_ms,
    merge_intervals,
    range_suffix,
)


@pytest.mark.parametrize(
    ("start", "end", "suffix"),
    [
        (90_000, 300_000, " (01.30-05.00)"),
        (0, 59_000, " (00.00-00.59)"),
        (3_750_000, 3_900_000, " (1.02.30-1.05.00)"),
        (0, 3_600_000, " (0.00.00-1.00.00)"),
        (59 * 60_000, 3_661_000, " (0.59.00-1.01.01)"),
        (36_000_000, 36_300_000, " (10.00.00-10.05.00)"),
    ],
)
def test_range_suffix(start, end, suffix):
    assert range_suffix(start, end) == suffix
    assert not set('\\/:*?"<>|') & set(suffix)


def test_ads_suffix_is_the_spec_text():
    assert ADS_SUFFIX == " (ตัดโฆษณา)" and MIN_PIECE_MS == 1000


def test_merge_intervals_sorts_joins_and_drops_empty():
    assert merge_intervals([(50, 60), (0, 10), (5, 20), (20, 30), (40, 40)]) == [(0, 30), (50, 60)]


def test_keep_without_ads_is_the_span():
    assert keep_intervals((0, 635_000), []) == [(0, 635_000)]


def test_keep_removes_ads_and_clips_them_to_the_span():
    ads = [(60_000, 90_000), (0, 12_000), (600_000, 700_000)]
    assert keep_intervals((0, 635_000), ads) == [(12_000, 60_000), (90_000, 600_000)]


def test_keep_inside_a_range():
    assert keep_intervals((30_000, 120_000), [(60_000, 90_000), (200_000, 210_000)]) == [
        (30_000, 60_000), (90_000, 120_000)]


def test_keep_drops_pieces_shorter_than_one_second():
    # left pieces (0, 500) and (50_000, 50_900) are both shorter than 1 s
    assert keep_intervals((0, 100_000), [(500, 50_000), (50_900, 100_000)]) == []
    assert keep_intervals((0, 100_000), [(1_000, 50_000)]) == [(0, 1_000), (50_000, 100_000)]


def test_keep_everything_cut_is_empty():
    assert keep_intervals((0, 10_000), [(0, 10_000)]) == []


def test_kept_ms():
    assert kept_ms([(0, 1_000), (5_000, 7_500)]) == 3_500


ZOO = [
    {"startS": 0, "endS": 5, "title": "Intro"},
    {"startS": 5, "endS": 17, "title": "The cool thing"},
    {"startS": 17, "endS": 19, "title": "End"},
]


def test_chapter_parts_of_the_zoo_clip():
    assert chapter_parts(ZOO, 19_000) == [
        ChapterPart(1, 3, 0, 5_000, "Intro"),
        ChapterPart(2, 3, 5_000, 17_000, "The cool thing"),
        ChapterPart(3, 3, 17_000, 19_000, "End"),
    ]


def test_chapter_parts_clip_the_last_end_and_strip_titles():
    parts = chapter_parts([{"startS": 0, "endS": 10.5, "title": "  a  "}, {"startS": 10.5, "endS": 99, "title": ""}], 20_000)
    assert parts == [ChapterPart(1, 2, 0, 10_500, "a"), ChapterPart(2, 2, 10_500, 20_000, "")]


def test_chapter_parts_need_two_usable_chapters():
    assert chapter_parts([], 10_000) == []
    assert chapter_parts(ZOO[:1], 19_000) == []
    assert chapter_parts([{"startS": 0, "endS": 5, "title": "a"}, {"startS": 25, "endS": 30, "title": "b"}], 19_000) == []
    assert chapter_parts([{"startS": None, "endS": 5}, {"startS": "x", "endS": 9}], 19_000) == []
```
Append to `tests/unit/test_files.py`:
```python
def test_m4_names_and_folders_are_unchanged_by_the_longer_tail_budget(tmp_path):
    root = tmp_path / ("r" * 40)
    for title in ("สั้น", "ก" * 300, "Big Buck Bunny 60fps 4K - Official Blender Foundation Short Film"):
        for suffix, ext in (("", "mp4"), (" (ไม่มีเสียง)", "mp4"), (".th", "srt"), (" - contact sheet", "jpg")):
            planned = files.plan_output(root, title, ID, suffix, ext)
            short = planned.parent.name[: -len(f" [{ID}]")]
            assert planned.name == f"{short}{suffix}.{ext}"


def test_long_m5_tail_shortens_only_the_file_name(tmp_path):
    title = "ก" * 300
    tail = " (ไม่มีเสียง) (100.00.00-100.05.00) (ตัดโฆษณา)"
    plain = files.plan_output(tmp_path, title, ID, "", "mp4")
    long = files.plan_output(tmp_path, title, ID, tail, "mp4")
    assert long.parent == plain.parent  # same clip folder as every other job of the clip
    assert long.name.endswith(f"{tail}.mp4") and len(long.name) < len(plain.name) + len(tail)
    assert len(str(long)) + files.UNIQUE_RESERVE <= files.PATH_LIMIT


def test_tail_longer_than_tail_max_is_a_programming_error(tmp_path):
    with pytest.raises(AssertionError):
        files.plan_output(tmp_path, "t", ID, " " + "x" * 60, "mp4")


def test_chapter_output_names(tmp_path):
    path = files.plan_chapter_output(tmp_path, "คลิป", ID, "mp4", None, index=1, total=3, chapter_title="Intro: part 1")
    assert path.parent.name == "แยกตาม chapter (mp4)"
    assert path.parent.parent == files.plan_output(tmp_path, "คลิป", ID, "", "mp4").parent
    assert path.name == "01 - Intro part 1.mp4"
    assert files.plan_chapter_output(tmp_path, "คลิป", ID, "mp3", "ชุด A", index=7, total=120,
                                     chapter_title="x").name == "007 - x.mp3"
    assert files.plan_chapter_output(tmp_path, "คลิป", ID, "m4a", None, index=2, total=3,
                                     chapter_title=" ?? ").name == "02 - chapter 2.m4a"
    assert files.chapter_dir_name("wav") == "แยกตาม chapter (wav)"


def test_chapter_output_fits_the_path_limit(tmp_path):
    path = files.plan_chapter_output(tmp_path, "ก" * 300, ID, "mp4", None, index=12, total=30, chapter_title="ข" * 300)
    assert len(str(path)) + files.UNIQUE_RESERVE <= files.PATH_LIMIT
    assert path.name.startswith("12 - ข") and path.name.endswith(".mp4")
```

- [ ] **Step 2: Run, expect FAIL** — `uv run pytest tests/unit/test_advanced.py tests/unit/test_files.py -q -W error -p no:cacheprovider` → `ModuleNotFoundError: yttoolkit.core.advanced`, `AttributeError: plan_chapter_output`.

- [ ] **Step 3: Implement `core/advanced.py`**
```python
"""ตัวเลือกขั้นสูงของงานโหลด (M5 รอบ A): ช่วงที่เก็บไว้หลังตัดช่วงเวลา/โฆษณา ช่วงของ chapter และส่วนต่อท้ายชื่อไฟล์

ฟังก์ชันล้วน เวลาเป็นมิลลิวินาทีบนเส้นเวลาของคลิปต้นฉบับ core/handlers.py เรียกใช้ ไม่แตะไฟล์ ไม่เรียก ffmpeg
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

Interval = tuple[int, int]
MIN_PIECE_MS = 1000  # ชิ้นที่เหลือหลังตัดโฆษณาสั้นกว่านี้ทิ้งไป (spec 3.2)
ADS_SUFFIX = " (ตัดโฆษณา)"
_HOUR_MS = 3_600_000


def _clock(ms: int, hours: bool) -> str:
    total = ms // 1000
    h, rest = divmod(total, 3600)
    m, s = divmod(rest, 60)
    return f"{h}.{m:02d}.{s:02d}" if hours else f"{m:02d}.{s:02d}"


def range_suffix(start_ms: int, end_ms: int) -> str:
    """ส่วนต่อท้ายชื่อไฟล์ของช่วงเวลา " (01.30-05.00)" ปลายช่วงถึงชั่วโมงแรก = มีชั่วโมงทั้งสองข้าง " (1.02.30-1.05.00)"
    ใช้ "." แทน ":" เพราะ Windows ห้ามใช้ ":" ในชื่อไฟล์"""
    hours = end_ms >= _HOUR_MS
    return f" ({_clock(start_ms, hours)}-{_clock(end_ms, hours)})"


def merge_intervals(items: Iterable[Interval]) -> list[Interval]:
    """เรียงและรวมช่วงที่ทับหรือชนกัน ช่วงว่าง (end <= start) ถูกทิ้ง"""
    merged: list[list[int]] = []
    for start, end in sorted((s, e) for s, e in items if e > s):
        if merged and start <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], end)
        else:
            merged.append([start, end])
    return [(s, e) for s, e in merged]


def keep_intervals(span: Interval, ads: Iterable[Interval]) -> list[Interval]:
    """span ลบช่วงโฆษณา (ตัดให้อยู่ใน span แล้วรวมกันก่อน) ชิ้นที่เหลือสั้นกว่า 1 วินาทีถูกทิ้ง เรียงตามเวลา"""
    start, end = span
    clipped = [(max(s, start), min(e, end)) for s, e in ads]
    pieces: list[Interval] = []
    cursor = start
    for s, e in merge_intervals(clipped):
        if s > cursor:
            pieces.append((cursor, s))
        cursor = max(cursor, e)
    if end > cursor:
        pieces.append((cursor, end))
    return [(s, e) for s, e in pieces if e - s >= MIN_PIECE_MS]


def kept_ms(intervals: Iterable[Interval]) -> int:
    return sum(e - s for s, e in intervals)


@dataclass(frozen=True)
class ChapterPart:
    index: int  # เริ่มที่ 1
    total: int
    start_ms: int
    end_ms: int
    title: str  # ตัดช่องว่างหัวท้ายแล้ว อาจว่าง (ชื่อไฟล์ใช้ "chapter <n>" แทน)


def _ms(value: Any) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int | float) or not math.isfinite(value) or value < 0:
        return None
    return round(value * 1000)


def chapter_parts(chapters: Sequence[Mapping[str, Any]], duration_ms: int) -> list[ChapterPart]:
    """chapter ของ VideoInfo ({startS, endS, title}) -> ช่วงของแต่ละไฟล์ ปลายไม่เกินความยาวจริงของไฟล์ที่โหลดมา
    chapter ที่อ่านเวลาไม่ได้หรือเหลือยาว 0 ถูกข้าม เหลือไม่ถึง 2 chapter = [] (ตัวทำงานใส่โน้ต NO_CHAPTERS)"""
    spans: list[tuple[int, int, str]] = []
    for chapter in chapters:
        start, end = _ms(chapter.get("startS")), _ms(chapter.get("endS"))
        if start is None or end is None:
            continue
        end = min(end, duration_ms)
        if end > start:
            spans.append((start, end, str(chapter.get("title") or "").strip()))
    if len(spans) < 2:
        return []
    total = len(spans)
    return [ChapterPart(i, total, s, e, t) for i, (s, e, t) in enumerate(spans, start=1)]
```

- [ ] **Step 4: Implement the `core/files.py` changes**

Add next to the constants:
```python
TAIL_MAX = 60  # M5: ส่วนต่อท้าย (ไม่มีเสียง) + ช่วงเวลา + (ตัดโฆษณา) + นามสกุล ยาวได้ถึงนี้ (ส่วนเกิน TAIL_RESERVE ตัดจากชื่อไฟล์)
CHAPTER_DIR = "แยกตาม chapter ({ext})"  # D4: โฟลเดอร์ย่อยของไฟล์แยกตาม chapter ในโฟลเดอร์ของคลิป
```
Replace the body of `plan_output` from `tail = …` to `return planned` with:
```python
    tail = f"{suffix}.{ext}"
    assert _u16(tail) <= TAIL_MAX, "suffix + extension longer than TAIL_MAX"
    base = root / group_folder_name(group) if group else root
    t = safe_component(title, video_id)
    budget = PATH_LIMIT - (_u16(str(base)) + 1) - _u16(f" [{video_id}]") - 1 - TAIL_RESERVE - UNIQUE_RESERVE
    cap = budget // 2
    short = ""
    if cap >= _MIN_TITLE:
        short = truncate_title(t, min(TITLE_MAX, cap))
    if short:
        # ชื่อโฟลเดอร์คิดจากงบเดิมเสมอ (ทุกงานของคลิปลงโฟลเดอร์เดียวกัน) ส่วนท้ายที่ยาวกว่า TAIL_RESERVE
        # ตัดเฉพาะชื่อไฟล์ลงเท่าส่วนที่เกิน: ชื่อแบบ M4 (ส่วนท้าย <= 30) จึงเหมือนเดิมทุกตัวอักษร
        file_cap = budget - _u16(short) + TAIL_RESERVE - _u16(tail)
        stem = short if _u16(short) <= file_cap else truncate_title(short, file_cap)
        planned = base / f"{short} [{video_id}]" / f"{stem or video_id}{tail}"
    else:
        planned = base / video_id / f"{video_id}{tail}"
    if _u16(str(planned)) > PATH_LIMIT - UNIQUE_RESERVE:
        raise YtError("E_OUTPUT_NOT_WRITABLE", "path too long")
    return planned
```
Add after `plan_output`:
```python
def chapter_dir_name(ext: str) -> str:
    return CHAPTER_DIR.format(ext=ext)


def plan_chapter_output(
    root: Path, title: str, video_id: str, ext: str, group: str | None, *, index: int, total: int, chapter_title: str
) -> Path:
    """ไฟล์ของ chapter ที่ index: <โฟลเดอร์ของคลิป>/แยกตาม chapter (<ext>)/<NN> - <ชื่อ chapter>.<ext>

    NN 2 หลัก (3 หลักเมื่อมี 100 chapter ขึ้นไป) ชื่อ chapter ทำความสะอาดแบบชื่อคลิป ว่าง = "chapter <n>"
    ตัดชื่อ chapter ให้ path ไม่เกิน 240 ไม่เหลือที่เลย = "<NN>.<ext>" ยังยาวเกิน = E_OUTPUT_NOT_WRITABLE
    """
    folder = plan_output(root, title, video_id, "", ext, group).parent / chapter_dir_name(ext)
    number = f"{index:0{3 if total >= 100 else 2}d}"
    name = safe_component(chapter_title, f"chapter {index}")
    budget = PATH_LIMIT - UNIQUE_RESERVE - (_u16(str(folder)) + 1) - _u16(f"{number} - ") - _u16(f".{ext}")
    short = truncate_title(name, budget) if budget > 0 else ""
    planned = folder / (f"{number} - {short}.{ext}" if short else f"{number}.{ext}")
    if _u16(str(planned)) > PATH_LIMIT - UNIQUE_RESERVE:
        raise YtError("E_OUTPUT_NOT_WRITABLE", "path too long")
    return planned
```
Why M4 names cannot change: for tails ≤ 30, `file_cap = budget − len(short) + 30 − len(tail) ≥ budget − cap ≥ cap ≥ len(short)`, so `stem == short`.

- [ ] **Step 5: Run, expect PASS; run the full suite** — `uv run pytest tests/unit/test_advanced.py tests/unit/test_files.py -q -W error -p no:cacheprovider` then `uv run pytest -q -W error -p no:cacheprovider`.

- [ ] **Step 6: Commit**
```bash
git add src/yttoolkit/core/advanced.py src/yttoolkit/core/files.py tests/unit/test_advanced.py tests/unit/test_files.py
git commit -F- <<'EOF'
feat(core): keep-interval maths, chapter parts and M5-A output names

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
EOF
```

### Task 3: ffmpeg cutter (exact / fast) and the fake cutter

**Files:**
- Modify: `src/yttoolkit/core/media.py` (imports, constants, `MediaMeta.track`, `_meta_args`, `wav_args`, `cut_args`, `MediaTools.cut`, `FfmpegTools.cut`, `CutCall`, `FakeMediaTools.cut`)
- Modify: `tests/unit/test_media_args.py`
- Create: `tests/integration/test_cut_ffmpeg.py`

**Interfaces:**
- Consumes: `run_ffmpeg`, `JobCancelled`, `YtError`.
- Produces: C3 exactly.

- [ ] **Step 1: Write the failing argument tests** — in `tests/unit/test_media_args.py` add `CutCall, cut_args` to the `yttoolkit.core.media` import, add `from dataclasses import replace` to the imports and `MEDIA_ROOT = Path(__file__).resolve().parents[1] / "fixtures" / "media"` after `SUB`, then append:
```python
CUT_HEAD = [FF, "-hide_banner", "-nostdin", "-y", "-progress", "pipe:1", "-nostats"]
X264 = ["-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p"]


def test_cut_exact_mp4_one_interval() -> None:
    args = cut_args(FF, SRC, DST, [(90_000, 300_000)], mode="exact", target="mp4", has_audio=True)
    assert args == CUT_HEAD + [
        "-ss", "90.000", "-t", "210.000", "-i", str(SRC),
        "-filter_complex",
        "[0:v:0]setpts=PTS-STARTPTS[v0];[0:a:0]asetpts=PTS-STARTPTS[a0];[v0][a0]concat=n=1:v=1:a=1[v][a]",
        "-map", "[v]", "-map", "[a]", *X264, "-c:a", "aac", "-b:a", "192k", "-f", "mp4", str(DST),
    ]  # fmt: skip


def test_cut_exact_mp4_two_intervals_without_audio() -> None:
    args = cut_args(FF, SRC, DST, [(0, 60_000), (90_000, 635_000)], mode="exact", target="mp4", has_audio=False)
    assert args == CUT_HEAD + [
        "-ss", "0.000", "-t", "60.000", "-i", str(SRC),
        "-ss", "90.000", "-t", "545.000", "-i", str(SRC),
        "-filter_complex", "[0:v:0]setpts=PTS-STARTPTS[v0];[1:v:0]setpts=PTS-STARTPTS[v1];[v0][v1]concat=n=2:v=1:a=0[v]",
        "-map", "[v]", *X264, "-an", "-f", "mp4", str(DST),
    ]  # fmt: skip


def test_cut_fast_mp4_is_a_stream_copy() -> None:
    args = cut_args(FF, SRC, DST, [(5_000, 17_000)], mode="fast", target="mp4", has_audio=True)
    assert args == CUT_HEAD + [
        "-ss", "5.000", "-t", "12.000", "-i", str(SRC), "-map", "0:v:0", "-map", "0:a?",
        "-c", "copy", "-avoid_negative_ts", "make_zero", "-f", "mp4", str(DST),
    ]  # fmt: skip
    silent = cut_args(FF, SRC, DST, [(5_000, 17_000)], mode="fast", target="mp4", has_audio=False)
    assert "0:a?" not in silent


def test_cut_m4a_one_interval_copies_two_intervals_reencode() -> None:
    m4a = Path("in.m4a")
    one = cut_args(FF, m4a, DST, [(9_500, 11_500)], mode="exact", target="m4a", has_audio=True)
    assert one == CUT_HEAD + ["-ss", "9.500", "-t", "2.000", "-i", str(m4a), "-map", "0:a:0", "-c", "copy",
                              "-f", "mp4", str(DST)]
    two = cut_args(FF, m4a, DST, [(9_500, 11_500), (19_000, 22_000)], mode="exact", target="m4a", has_audio=True)
    assert two[-9:] == ["-map", "[a]", "-c:a", "aac", "-b:a", "192k", "-f", "mp4", str(DST)]
    assert "[a0][a1]concat=n=2:v=0:a=1[a]" in two[two.index("-filter_complex") + 1]


def test_cut_wav_is_pcm() -> None:
    args = cut_args(FF, SRC, Path("cut.wav"), [(1_000, 3_000)], mode="exact", target="wav", has_audio=True)
    assert args[-7:] == ["-map", "[a]", "-c:a", "pcm_s16le", "-f", "wav", "cut.wav"]
    assert args[args.index("-filter_complex") + 1] == "[0:a:0]asetpts=PTS-STARTPTS[a0];[a0]concat=n=1:v=0:a=1[a]"


@pytest.mark.parametrize(
    ("intervals", "mode", "target"),
    [([], "exact", "mp4"), ([(5, 5)], "exact", "mp4"), ([(-1000, 0)], "exact", "wav"),
     ([(0, 1000), (2000, 3000)], "fast", "mp4"), ([(0, 1000)], "fast", "m4a")],
)
def test_cut_rejects_bad_requests(intervals, mode, target) -> None:
    with pytest.raises(ValueError):
        cut_args(FF, SRC, DST, intervals, mode=mode, target=target, has_audio=True)


def test_track_metadata_only_when_set() -> None:
    assert "track=3/12" not in mp4_args(FF, SRC, DST, META, cover=None, subtitle=None, audio_language=None)
    with_track = replace(META, track="3/12")
    for args in (
        mp4_args(FF, SRC, DST, with_track, cover=None, subtitle=None, audio_language=None),
        m4a_args(FF, SRC, DST, with_track, cover=None, audio_language=None),
        mp3_args(FF, SRC, DST, with_track, kbps=192, cover=None, audio_language=None),
        wav_args(FF, SRC, DST, with_track, audio_language=None),
    ):
        assert _contains(args, ["-metadata", "track=3/12"])


def test_fake_cut_records_and_copies(tmp_path: Path) -> None:
    fake = FakeMediaTools(MEDIA_ROOT)
    src = tmp_path / "media.mp4"
    src.write_bytes(b"video")
    seen: list[float | None] = []
    fake.cut(src, tmp_path / "cut.mp4", [(0, 1000), (2000, 3000)], mode="exact", target="mp4", has_audio=False,
             cancel=lambda: False, on_progress=seen.append)
    fake.cut(src, tmp_path / "cut.wav", [(0, 1000)], mode="exact", target="wav", has_audio=True,
             cancel=lambda: False, on_progress=seen.append)
    assert (tmp_path / "cut.mp4").read_bytes() == b"video"
    assert (tmp_path / "cut.wav").read_bytes() == (MEDIA_ROOT / "audio.wav").read_bytes()
    assert fake.cuts == [
        CutCall("media.mp4", "cut.mp4", ((0, 1000), (2000, 3000)), "exact", "mp4", False),
        CutCall("media.mp4", "cut.wav", ((0, 1000),), "exact", "wav", True),
    ]
    assert seen == [1.0, 1.0]
    with pytest.raises(JobCancelled):
        fake.cut(src, tmp_path / "x.mp4", [(0, 1000)], mode="fast", target="mp4", has_audio=True,
                 cancel=lambda: True, on_progress=seen.append)
```

- [ ] **Step 2: Write the failing real-ffmpeg tests** — `tests/integration/test_cut_ffmpeg.py`:
```python
"""ตัวตัดของ M5 รอบ A กับ ffmpeg จริง (ข้ามเมื่อเครื่องไม่มี ffmpeg): ความยาว ภาพแรกตรงเฟรม การยกเลิก"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
from helpers_ffmpeg import ffprobe_json, find_test_ffmpeg, requires_ffmpeg

from yttoolkit.core.cancel import JobCancelled
from yttoolkit.core.media import FfmpegTools

pytestmark = requires_ffmpeg
MEDIA = Path(__file__).resolve().parents[1] / "fixtures" / "media"


def _ffmpeg() -> str:
    found = find_test_ffmpeg()
    assert found is not None
    return found


def _tools() -> FfmpegTools:
    return FfmpegTools(lambda: Path(_ffmpeg()))


def _durations(path: Path) -> dict[str, float]:
    return {s["codec_type"]: float(s["duration"]) for s in ffprobe_json(path)["streams"]}


@pytest.fixture(scope="module")
def gop_clip(tmp_path_factory) -> Path:
    """คลิป 20 วิ 30 fps keyframe ทุก 4 วิ (เหมือนคลิปยูทูปที่ keyframe ห่าง) ภาพเปลี่ยนทุกเฟรม"""
    out = tmp_path_factory.mktemp("cut") / "src.mp4"
    subprocess.run(
        [_ffmpeg(), "-hide_banner", "-loglevel", "error", "-y", "-f", "lavfi", "-i", "testsrc2=size=320x180:rate=30",
         "-f", "lavfi", "-i", "sine=frequency=440:sample_rate=44100", "-t", "20", "-c:v", "libx264", "-g", "120",
         "-keyint_min", "120", "-sc_threshold", "0", "-pix_fmt", "yuv420p", "-c:a", "aac", str(out)],
        check=True,
    )  # fmt: skip
    return out


def _gray_frame(path: Path, at_s: float | None) -> bytes:
    seek = ["-ss", f"{at_s:.3f}"] if at_s is not None else []
    return subprocess.run(
        [_ffmpeg(), "-hide_banner", "-loglevel", "error", *seek, "-i", str(path), "-frames:v", "1",
         "-f", "rawvideo", "-pix_fmt", "gray", "-"],
        check=True, capture_output=True,
    ).stdout  # fmt: skip


def _diff(a: bytes, b: bytes) -> float:
    return sum(abs(x - y) for x, y in zip(a, b, strict=True)) / len(a)


def _never() -> bool:
    return False


def test_exact_cut_starts_on_the_requested_frame(gop_clip: Path, tmp_path: Path) -> None:
    out = tmp_path / "cut.mp4"
    seen: list[float | None] = []
    _tools().cut(gop_clip, out, [(10_000, 15_000)], mode="exact", target="mp4", has_audio=True,
                 cancel=_never, on_progress=seen.append)
    durations = _durations(out)
    assert abs(durations["video"] - 5.0) <= 0.05 and abs(durations["audio"] - 5.0) <= 0.05
    first = _gray_frame(out, None)
    assert _diff(first, _gray_frame(gop_clip, 10.0)) < _diff(first, _gray_frame(gop_clip, 10.0 + 1 / 30)) / 3
    assert seen and max(v for v in seen if v is not None) <= 1.0


def test_exact_cut_joins_several_intervals(gop_clip: Path, tmp_path: Path) -> None:
    out = tmp_path / "ads.mp4"
    _tools().cut(gop_clip, out, [(2_000, 7_000), (13_000, 20_000)], mode="exact", target="mp4", has_audio=True,
                 cancel=_never, on_progress=lambda _: None)
    assert abs(_durations(out)["video"] - 12.0) <= 0.05


def test_fast_cut_starts_at_the_keyframe_before(gop_clip: Path, tmp_path: Path) -> None:
    out = tmp_path / "fast.mp4"
    _tools().cut(gop_clip, out, [(10_000, 15_000)], mode="fast", target="mp4", has_audio=True,
                 cancel=_never, on_progress=lambda _: None)
    assert 5.0 <= _durations(out)["video"] <= 7.2  # keyframe at 8 s: up to one GOP earlier (D6)


def test_audio_cuts_are_within_50_ms(tmp_path: Path) -> None:
    tools = _tools()
    one = tmp_path / "one.m4a"
    tools.cut(MEDIA / "audio.m4a", one, [(500, 1_500)], mode="exact", target="m4a", has_audio=True,
              cancel=_never, on_progress=lambda _: None)
    assert abs(_durations(one)["audio"] - 1.0) <= 0.05
    wav = tmp_path / "two.wav"
    tools.cut(MEDIA / "audio.m4a", wav, [(0, 500), (1_000, 1_800)], mode="exact", target="wav", has_audio=True,
              cancel=_never, on_progress=lambda _: None)
    assert abs(_durations(wav)["audio"] - 1.3) <= 0.05


def test_cancel_kills_the_cut(gop_clip: Path, tmp_path: Path) -> None:
    with pytest.raises(JobCancelled):
        _tools().cut(gop_clip, tmp_path / "x.mp4", [(0, 20_000)], mode="exact", target="mp4", has_audio=True,
                     cancel=lambda: True, on_progress=lambda _: None)
```

- [ ] **Step 3: Run both, expect FAIL** — `uv run pytest tests/unit/test_media_args.py tests/integration/test_cut_ffmpeg.py -q -W error -p no:cacheprovider` → `ImportError: cannot import name 'cut_args'`.

- [ ] **Step 4: Implement in `core/media.py`**

Imports: `from collections.abc import Callable, Sequence`, `from typing import Literal, Protocol`. Constants after `_POLL_SECONDS`:
```python
CutMode = Literal["exact", "fast"]
CutTarget = Literal["mp4", "m4a", "wav"]
# ตัดแบบแม่นยำ (D1) เข้ารหัสภาพใหม่ด้วย H.264 ที่เปิดได้ทุกที่ ความเร็วพอดีกับโน้ตบุ๊กทั่วไป
X264_PRESET = "veryfast"
X264_CRF = 20
CUT_AAC_KBPS = 192
```
`MediaMeta` gets a last field `track: str | None = None  # "3/12" ของไฟล์แยกตาม chapter`. `_meta_args` appends `["-metadata", f"track={meta.track}"]` when `meta.track`. `wav_args` becomes:
```python
    # ไม่ใส่ -ar: อัตราสุ่มตัวอย่างคงเดิม  audio_language รับไว้ให้ลายเซ็นเหมือนตัวอื่น (wav ไม่มีแท็กภาษา)
    tags = ["-metadata", f"title={meta.title}", "-metadata", f"artist={meta.artist}"]
    if meta.track:
        tags += ["-metadata", f"track={meta.track}"]
    return _head(ffmpeg, src) + ["-map", "0:a:0", "-c:a", "pcm_s16le"] + tags + [str(dst)]
```
`MediaTools` protocol gains:
```python
    def cut(
        self,
        src: Path,
        dst: Path,
        intervals: Sequence[tuple[int, int]],
        *,
        mode: CutMode,
        target: CutTarget,
        has_audio: bool,
        cancel: Callable[[], bool],
        on_progress: Callable[[float | None], None],
    ) -> None: ...
```
Builder (after `wav_args`):
```python
def _seconds(ms: int) -> str:
    return f"{ms / 1000:.3f}"


def _check_intervals(intervals: Sequence[tuple[int, int]]) -> list[tuple[int, int]]:
    clean = [(int(s), int(e)) for s, e in intervals]
    if not clean or any(s < 0 or e <= s for s, e in clean):
        raise ValueError(f"bad cut intervals: {intervals!r}")
    return clean


def cut_args(
    ffmpeg: str,
    src: Path,
    dst: Path,
    intervals: Sequence[tuple[int, int]],
    *,
    mode: CutMode,
    target: CutTarget,
    has_audio: bool,
) -> list[str]:
    """ตัดช่วง (มิลลิวินาทีบนเส้นเวลาต้นฉบับ) ลงไฟล์ระหว่างทาง (C3)

    - fast: mp4 ช่วงเดียว คัดลอกสตรีม เริ่มที่ keyframe ก่อนจุดตัด (แยก chapter ของวิดีโอ D6)
    - exact + m4a ช่วงเดียว: คัดลอกสตรีม (คลาดไม่เกินหนึ่งเฟรม AAC ~23 ms)
    - exact อื่น ๆ: แต่ละช่วงเป็น input ของตัวเอง (-ss ก่อน -i = seek แม่นยำเมื่อเข้ารหัสใหม่) แล้วต่อด้วย concat
      mp4 = H.264 + AAC (หรือไม่มีเสียง) · m4a = AAC · wav = PCM (ให้ to_mp3/to_wav แปลงต่อ)
    """
    clean = _check_intervals(intervals)
    head = [ffmpeg, "-hide_banner", "-nostdin", "-y", "-progress", "pipe:1", "-nostats"]
    if mode == "fast":
        if target != "mp4" or len(clean) != 1:
            raise ValueError("fast cut takes exactly one interval of an mp4")
        ((s, e),) = clean
        maps = ["-map", "0:v:0"] + (["-map", "0:a?"] if has_audio else [])
        return head + ["-ss", _seconds(s), "-t", _seconds(e - s), "-i", str(src)] + maps + [
            "-c", "copy", "-avoid_negative_ts", "make_zero", "-f", "mp4", str(dst)]  # fmt: skip
    if target == "m4a" and len(clean) == 1:
        ((s, e),) = clean
        return head + ["-ss", _seconds(s), "-t", _seconds(e - s), "-i", str(src),
                       "-map", "0:a:0", "-c", "copy", "-f", "mp4", str(dst)]  # fmt: skip
    video = target == "mp4"
    audio = has_audio or target != "mp4"
    args = list(head)
    chains: list[str] = []
    pads: list[str] = []
    for i, (s, e) in enumerate(clean):
        args += ["-ss", _seconds(s), "-t", _seconds(e - s), "-i", str(src)]
        if video:
            chains.append(f"[{i}:v:0]setpts=PTS-STARTPTS[v{i}]")
            pads.append(f"[v{i}]")
        if audio:
            chains.append(f"[{i}:a:0]asetpts=PTS-STARTPTS[a{i}]")
            pads.append(f"[a{i}]")
    outs = ("[v]" if video else "") + ("[a]" if audio else "")
    chains.append("".join(pads) + f"concat=n={len(clean)}:v={int(video)}:a={int(audio)}{outs}")
    args += ["-filter_complex", ";".join(chains)]
    if video:
        args += ["-map", "[v]"]
    if audio:
        args += ["-map", "[a]"]
    if video:
        args += ["-c:v", "libx264", "-preset", X264_PRESET, "-crf", str(X264_CRF), "-pix_fmt", "yuv420p"]
    if audio:
        args += ["-c:a", "pcm_s16le"] if target == "wav" else ["-c:a", "aac", "-b:a", f"{CUT_AAC_KBPS}k"]
    else:
        args += ["-an"]
    return args + ["-f", "wav" if target == "wav" else "mp4", str(dst)]
```
`FfmpegTools.cut` (same signature as the protocol):
```python
    def cut(
        self,
        src: Path,
        dst: Path,
        intervals: Sequence[tuple[int, int]],
        *,
        mode: CutMode,
        target: CutTarget,
        has_audio: bool,
        cancel: Callable[[], bool],
        on_progress: Callable[[float | None], None],
    ) -> None:
        args = cut_args(self._require(), src.resolve(), dst.resolve(), intervals,
                        mode=mode, target=target, has_audio=has_audio)  # fmt: skip
        kept_s = sum(e - s for s, e in intervals) / 1000
        run_ffmpeg(args, duration_s=kept_s, cancel=cancel, on_progress=on_progress, popen_flags=self._popen_flags)
```
Fake (place `CutCall` before `FakeMediaTools`; `dataclass` is already imported):
```python
@dataclass(frozen=True)
class CutCall:
    """การตัดหนึ่งครั้งของ FakeMediaTools (เทสตรวจช่วงที่ตัด ความยาวของไฟล์ปลอมไม่ตรงกับช่วงที่ตัด)"""

    src_name: str
    dst_name: str
    intervals: tuple[tuple[int, int], ...]
    mode: str
    target: str
    has_audio: bool
```
In `FakeMediaTools.__init__` add `self.cuts: list[CutCall] = []`; add the method (same signature as `FfmpegTools.cut`):
```python
    def cut(self, src, dst, intervals, *, mode, target, has_audio, cancel, on_progress) -> None:
        clean = _check_intervals(intervals)
        if cancel():
            raise JobCancelled()
        self.cuts.append(CutCall(src.name, dst.name, tuple(clean), mode, target, has_audio))
        self._copy(self._root / "audio.wav" if target == "wav" else src, dst, cancel, on_progress)
```
(Write the parameter annotations in full, as in `FfmpegTools.cut`.) Extend the `FakeMediaTools` docstring with: `ตัดช่วง = คัดลอกไฟล์ (เป้าหมาย wav = audio.wav) และจดการเรียกไว้ใน cuts`.

- [ ] **Step 5: Run, expect PASS; run the full suite** — `uv run pytest tests/unit/test_media_args.py tests/integration/test_cut_ffmpeg.py tests/unit/test_no_shell.py -q -W error -p no:cacheprovider` then `uv run pytest -q -W error -p no:cacheprovider`.

- [ ] **Step 6: Commit**
```bash
git add src/yttoolkit/core/media.py tests/unit/test_media_args.py tests/integration/test_cut_ffmpeg.py
git commit -F- <<'EOF'
feat(media): exact and fast ffmpeg cutter, track metadata, fake cutter

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
EOF
```

### Task 4: SponsorBlock segment source (real + fake) and fake clips

**Files:**
- Modify: `src/yttoolkit/core/download.py` (types, `SponsorBlockError`, `SponsorSource`)
- Modify: `src/yttoolkit/core/extractor.py` (`_sponsor_from_chapters`, `YtDlpExtractor.sponsor_segments`, `FakeExtractor.sponsor_segments`, docstrings)
- Create: `tests/fixtures/sponsorblock/ADSCUTCLIP1.json`, `tests/fixtures/sponsorblock/ADSOFFLINE1.json`
- Modify: `tests/fixtures/downloads/behaviors.json`, `tests/fixtures/README.md`
- Modify: `tests/unit/test_extractor_download.py` (`C14` constant)
- Create: `tests/unit/test_sponsorblock.py`

**Interfaces:**
- Consumes: `YtDlpExtractor._ydl`, `_PROBE_OPTS`, `_check_video_id`.
- Produces: C4 exactly.

- [ ] **Step 1: Write the fixtures**

`tests/fixtures/sponsorblock/ADSCUTCLIP1.json`:
```json
{"segments": [[0, 12000, "intro"], [60000, 90000, "sponsor"], [600000, 635000, "outro"]]}
```
`tests/fixtures/sponsorblock/ADSOFFLINE1.json`:
```json
{"error": "unreachable"}
```
`tests/fixtures/downloads/behaviors.json`: add inside `"videos"` after `REFUSEDDL01` (add a comma after the `REFUSEDDL01` entry; keep every existing entry):
```json
    "RANGECLIP01": {"probeAs": "aqz-KE-bpKQ", "title": "คลิปช่วงเวลา"},
    "ADSCUTCLIP1": {"probeAs": "aqz-KE-bpKQ", "title": "คลิปมีช่วงโฆษณา"},
    "ADSNODATA01": {"probeAs": "aqz-KE-bpKQ", "title": "คลิปไม่มีข้อมูลโฆษณา"},
    "ADSOFFLINE1": {"probeAs": "aqz-KE-bpKQ", "title": "คลิปที่ติดต่อ SponsorBlock ไม่ได้"},
    "CHAPTERS001": {"probeAs": "jNQXAC9IVRw", "title": "คลิปมี 3 chapter"}
```
In `tests/unit/test_extractor_download.py` add the same five entries to `C14["videos"]`:
```python
        "RANGECLIP01": {"probeAs": BBB, "title": "คลิปช่วงเวลา"},
        "ADSCUTCLIP1": {"probeAs": BBB, "title": "คลิปมีช่วงโฆษณา"},
        "ADSNODATA01": {"probeAs": BBB, "title": "คลิปไม่มีข้อมูลโฆษณา"},
        "ADSOFFLINE1": {"probeAs": BBB, "title": "คลิปที่ติดต่อ SponsorBlock ไม่ได้"},
        "CHAPTERS001": {"probeAs": "jNQXAC9IVRw", "title": "คลิปมี 3 chapter"},
```
Append to `tests/fixtures/README.md`:
```markdown
## sponsorblock/ (M5 รอบ A)
ช่วงโฆษณาปลอมของ `FakeExtractor.sponsor_segments` ต่อคลิป: `{"segments": [[startMs, endMs, "หมวด"], ...]}` หรือ `{"error": "..."}` (= ติดต่อ SponsorBlock ไม่ได้) · ไม่มีไฟล์ = ไม่มีข้อมูลจากชุมชน
- `ADSCUTCLIP1.json` intro 0-12 วิ, sponsor 60-90 วิ, outro 600-635 วิ (คลิปปลอมที่ probe เป็น aqz-KE-bpKQ 635 วิ)
- `ADSOFFLINE1.json` ติดต่อไม่ได้ · `ADSNODATA01` ไม่มีไฟล์ = ไม่มีข้อมูล

คลิปปลอมของ M5 รอบ A ใน `downloads/behaviors.json`: RANGECLIP01, ADSCUTCLIP1, ADSNODATA01, ADSOFFLINE1 (probe เป็น aqz-KE-bpKQ) และ CHAPTERS001 (probe เป็น jNQXAC9IVRw 3 chapter) ใช้ใน web/e2e/queue-advanced.spec.ts เท่านั้น
```

- [ ] **Step 2: Write the failing tests** — `tests/unit/test_sponsorblock.py`:
```python
"""ช่วงโฆษณาจาก SponsorBlock (C4): ตัวจริงห่อ SponsorBlockPP ของ yt-dlp (ไม่ต่อเน็ต: แทน _download_json) และตัวปลอม"""

from __future__ import annotations

from pathlib import Path

import pytest
from yt_dlp.postprocessor.sponsorblock import SponsorBlockPP

from yttoolkit.core.download import SponsorBlockError, SponsorSource
from yttoolkit.core.extractor import FakeExtractor, YtDlpExtractor
from yttoolkit.core.yterrors import YtError

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
BBB = "aqz-KE-bpKQ"


def _answer(segments: list[dict]) -> list[dict]:
    return [{"videoID": "other", "segments": []}, {"videoID": BBB, "segments": segments}]


def _segment(start: float, end: float, category: str, action: str = "skip") -> dict:
    return {"segment": [start, end], "category": category, "actionType": action,
            "videoDuration": 635.0, "description": ""}


def test_both_extractors_are_sponsor_sources() -> None:
    assert isinstance(YtDlpExtractor(), SponsorSource)
    assert isinstance(FakeExtractor(FIXTURES), SponsorSource)


def test_real_maps_skip_segments_to_milliseconds(monkeypatch) -> None:
    urls: list[str] = []

    def fake_json(self, url, **kwargs):
        urls.append(url)
        return _answer([_segment(60.0, 90.25, "sponsor"), _segment(100.0, 101.0, "selfpromo", action="mute"),
                        _segment(0.4, 12.0, "intro")])

    monkeypatch.setattr(SponsorBlockPP, "_download_json", fake_json)
    got = YtDlpExtractor().sponsor_segments(BBB, ["sponsor", "selfpromo", "intro"], 635.0)
    assert got == [(0, 12_000, "intro"), (60_000, 90_250, "sponsor")]  # mute dropped; start <= 1 s snapped to 0
    assert BBB not in urls[0] and "/api/skipSegments/" in urls[0]  # only a hash prefix leaves the machine


def test_real_no_data_is_empty(monkeypatch) -> None:
    monkeypatch.setattr(SponsorBlockPP, "_download_json", lambda self, url, **kw: None)  # HTTP 404
    assert YtDlpExtractor().sponsor_segments(BBB, ["sponsor"], 635.0) == []


def test_real_failure_is_a_sponsorblock_error_not_a_yt_error(monkeypatch) -> None:
    def boom(self, url, **kwargs):
        raise OSError("connection refused")

    monkeypatch.setattr(SponsorBlockPP, "_download_json", boom)
    with pytest.raises(SponsorBlockError) as info:
        YtDlpExtractor().sponsor_segments(BBB, ["sponsor"], 635.0)
    assert not isinstance(info.value, YtError)


def test_real_needs_a_duration_and_a_valid_id() -> None:
    with pytest.raises(SponsorBlockError):
        YtDlpExtractor().sponsor_segments(BBB, ["sponsor"], None)
    with pytest.raises(YtError):
        YtDlpExtractor().sponsor_segments("bad id", ["sponsor"], 635.0)


def test_fake_reads_fixtures_and_filters_categories() -> None:
    fake = FakeExtractor(FIXTURES)
    assert fake.sponsor_segments("ADSCUTCLIP1", ["sponsor"], 635.0) == [(60_000, 90_000, "sponsor")]
    assert fake.sponsor_segments("ADSCUTCLIP1", ["intro", "outro"], 635.0) == [
        (0, 12_000, "intro"), (600_000, 635_000, "outro")]
    assert fake.sponsor_segments("ADSNODATA01", ["sponsor"], 635.0) == []
    with pytest.raises(SponsorBlockError):
        fake.sponsor_segments("ADSOFFLINE1", ["sponsor"], 635.0)
    assert ("sponsor_segments", "ADSNODATA01") in fake.calls


def test_fake_m5a_clips_probe_as_their_sources() -> None:
    fake = FakeExtractor(FIXTURES)
    chapters = fake.probe("CHAPTERS001")
    assert chapters["title"] == "คลิปมี 3 chapter" and len(chapters["chapters"]) == 3
    assert fake.probe("RANGECLIP01")["duration"] == 635
```

- [ ] **Step 3: Run, expect FAIL** — `uv run pytest tests/unit/test_sponsorblock.py tests/unit/test_extractor_download.py -q -W error -p no:cacheprovider` → `ImportError: cannot import name 'SponsorBlockError'`.

- [ ] **Step 4: Implement**

`core/download.py` (add `Sequence` to the `collections.abc` import; place after `DownloadResult`):
```python
SponsorSegment = tuple[int, int, str]  # (startMs, endMs, หมวด) บนเส้นเวลาของคลิป


class SponsorBlockError(Exception):
    """ติดต่อ SponsorBlock ไม่ได้หรือคำตอบใช้ไม่ได้ ไม่ใช่ YtError โดยตั้งใจ:
    ห้ามทำให้คิวลองใหม่ (E_NETWORK) หรือพักคิว (E_BOT_CHECK) งานยังได้คลิปเต็มพร้อมโน้ต"""


@runtime_checkable
class SponsorSource(Protocol):
    def sponsor_segments(
        self, video_id: str, categories: Sequence[str], duration_s: float | None
    ) -> list[SponsorSegment]:
        """ช่วงที่ผู้ชมมาร์กไว้ตามหมวดที่เลือก (ไม่มีข้อมูล = []) ติดต่อไม่ได้ = SponsorBlockError"""
        ...
```
`core/extractor.py`: import `SponsorBlockError, SponsorSegment` from `.download`; add `Sequence` to the `collections.abc` import; add after `_REFUSED_ATTEMPTS`:
```python
_SPONSORBLOCK_RETRIES = 1  # ลองซ้ำครั้งเดียวพอ: ติดต่อไม่ได้ก็ยังได้คลิปเต็มพร้อมโน้ต


def _sponsor_from_chapters(chapters: object, categories: Sequence[str]) -> list[SponsorSegment]:
    """sponsorblock_chapters ของ SponsorBlockPP -> [(startMs, endMs, หมวด)] เฉพาะแบบ "skip" ของหมวดที่ขอ"""
    wanted = set(categories)
    found: list[SponsorSegment] = []
    for chapter in chapters if isinstance(chapters, list) else []:
        if not isinstance(chapter, dict) or chapter.get("type") != "skip" or chapter.get("category") not in wanted:
            continue
        start, end = chapter.get("start_time"), chapter.get("end_time")
        if isinstance(start, int | float) and isinstance(end, int | float) and end > start:
            found.append((round(start * 1000), round(end * 1000), str(chapter["category"])))
    return sorted(found)
```
In `YtDlpExtractor` (after `pinned_comment`):
```python
    def sponsor_segments(
        self, video_id: str, categories: Sequence[str], duration_s: float | None
    ) -> list[SponsorSegment]:
        """ช่วงโฆษณาจาก SponsorBlock ผ่าน SponsorBlockPP ของ yt-dlp (ส่งแค่ hash 4 ตัวแรกของ video id)

        ไม่ใช้เซสชันผู้ชม (ไม่ใช่ยูทูป) · ไม่รู้ความยาวคลิป = SponsorBlockError (ตัวกรองของ yt-dlp ต้องใช้)
        พังแบบไหนก็ได้ SponsorBlockError ที่บอกแค่ชื่อชนิด error (ไม่มีข้อมูลผู้ใช้ใน log)
        """
        _check_video_id(video_id)
        if not duration_s:
            raise SponsorBlockError("duration unknown")
        from yt_dlp.postprocessor.sponsorblock import SponsorBlockPP

        try:
            with self._ydl({**_PROBE_OPTS, "extractor_retries": _SPONSORBLOCK_RETRIES}) as ydl:
                pp = SponsorBlockPP(ydl, list(categories))
                _, info = pp.run({"id": video_id, "extractor_key": "Youtube", "duration": duration_s})
        except Exception as exc:
            raise SponsorBlockError(type(exc).__name__) from exc
        return _sponsor_from_chapters(info.get("sponsorblock_chapters"), categories)
```
In `FakeExtractor` (after `pinned_comment`; mention `sponsorblock/<id>.json` in the class docstring):
```python
    def sponsor_segments(
        self, video_id: str, categories: Sequence[str], duration_s: float | None
    ) -> list[SponsorSegment]:
        """sponsorblock/<id>.json: {"segments": [[startMs, endMs, หมวด], ...]} | {"error": ...} ไม่มีไฟล์ = []"""
        self.calls.append(("sponsor_segments", video_id))
        _check_video_id(video_id)
        path = self.root / "sponsorblock" / f"{video_id}.json"
        if not path.is_file():
            return []
        doc = json.loads(path.read_text(encoding="utf-8"))
        if doc.get("error"):
            raise SponsorBlockError(f"fake: {doc['error']}")
        wanted = set(categories)
        return sorted((int(s), int(e), str(c)) for s, e, c in doc.get("segments") or [] if c in wanted)
```

- [ ] **Step 5: Run, expect PASS; run the full suite** — `uv run pytest tests/unit/test_sponsorblock.py tests/unit/test_extractor_download.py -q -W error -p no:cacheprovider` then `uv run pytest -q -W error -p no:cacheprovider`; `git grep -n "import yt_dlp\|from yt_dlp" -- src/` must list only `src/yttoolkit/core/extractor.py`.

- [ ] **Step 6: Commit**
```bash
git add src/yttoolkit/core/download.py src/yttoolkit/core/extractor.py tests/fixtures/sponsorblock tests/fixtures/downloads/behaviors.json tests/fixtures/README.md tests/unit/test_extractor_download.py tests/unit/test_sponsorblock.py
git commit -F- <<'EOF'
feat(extractor): SponsorBlock segments via yt-dlp (real + fake) and M5-A fake clips

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
EOF
```

### Task 5: Subtitles by range in Python and TypeScript (byte parity)

**Files:**
- Modify: `src/yttoolkit/core/srt_builder.py` (add `range_tokens`, `clamp_cues` after `build_cues`)
- Modify: `src/yttoolkit/core/subtitles.py` (`SubtitleService.export` gains `range_ms`)
- Modify: `web/src/lib/srt-builder.ts` (add `rangeTokens`, `clampCues` after `buildCues`)
- Create: `tests/fixtures/subs/range-cases.json`, `tests/fixtures/subs/range-golden.json`
- Create: `tests/unit/test_srt_range.py`, `web/src/lib/srt-range.test.ts`

**Interfaces:**
- Consumes: `Token`, `Cue`, `build_cues`, `to_srt`, `PRESETS`, `options_from_dict` (Python); `buildCues`, `toSrt`, `PRESETS` (TS).
- Produces: C5 exactly. T8 calls `deps.subtitles.export(video_id, track_id, fmt, opts, span)` **positionally** (handler test stubs use `*args`); T10 calls `rangeTokens` / `clampCues`.

- [ ] **Step 1: Write the hand-made parity cases** — `tests/fixtures/subs/range-cases.json` (exact content; the `srt` strings keep CRLF as `\r\n` escapes, so the file itself stays LF):
```json
{
  "version": 1,
  "cases": [
    {
      "name": "boundary-midpoint",
      "options": {"maxChars": 25, "lines": 1, "minMs": 1200, "maxMs": 5000, "mode": "chars"},
      "startMs": 1000, "endMs": 3000,
      "tokens": [{"t": "Before", "s": 0, "e": 800}, {"t": " cross", "s": 900, "e": 1300}, {"t": " inside", "s": 1300, "e": 2000}, {"t": " edge", "s": 2600, "e": 3400}, {"t": " after", "s": 3500, "e": 3900}],
      "ranged": [{"t": " cross", "s": 0, "e": 300}, {"t": " inside", "s": 300, "e": 1000}],
      "srt": "1\r\n00:00:00,000 --> 00:00:01,200\r\ncross inside\r\n"
    },
    {
      "name": "last-cue-clamped",
      "options": {"maxChars": 25, "lines": 1, "minMs": 1200, "maxMs": 5000, "mode": "chars"},
      "startMs": 4000, "endMs": 5500,
      "tokens": [{"t": "Hello", "s": 5000, "e": 5200}, {"t": " world", "s": 5200, "e": 5300}],
      "ranged": [{"t": "Hello", "s": 1000, "e": 1200}, {"t": " world", "s": 1200, "e": 1300}],
      "srt": "1\r\n00:00:01,000 --> 00:00:01,500\r\nHello world\r\n"
    },
    {
      "name": "thai-shift",
      "options": {"maxChars": 15, "lines": 1, "minMs": 800, "maxMs": 3000, "mode": "chars"},
      "startMs": 60000, "endMs": 63200,
      "tokens": [{"t": "สวัสดี", "s": 60000, "e": 60600}, {"t": "ครับ", "s": 60600, "e": 61000}, {"t": "วันนี้", "s": 62500, "e": 63000}, {"t": "เรา", "s": 63000, "e": 63300}],
      "ranged": [{"t": "สวัสดี", "s": 0, "e": 600}, {"t": "ครับ", "s": 600, "e": 1000}, {"t": "วันนี้", "s": 2500, "e": 3000}, {"t": "เรา", "s": 3000, "e": 3200}],
      "srt": "1\r\n00:00:00,000 --> 00:00:01,000\r\nสวัสดีครับ\r\n\r\n2\r\n00:00:02,500 --> 00:00:03,200\r\nวันนี้เรา\r\n"
    },
    {
      "name": "empty-range",
      "options": {"maxChars": 25, "lines": 1, "minMs": 1200, "maxMs": 5000, "mode": "chars"},
      "startMs": 10000, "endMs": 20000,
      "tokens": [{"t": "Only", "s": 0, "e": 500}],
      "ranged": [],
      "srt": ""
    }
  ]
}
```
(These expected values were produced on 2026-10-02 by running the C5 algorithm over the M3 `build_cues`; `" edge"` has its midpoint exactly at `endMs` and is excluded — the range is half-open; the last cue of `last-cue-clamped` would end at 2,500 ms after the 1.2 s minimum and is clamped to 1,500 ms; `thai-shift` cue 2 would end at 3,300 ms and is clamped to 3,200 ms.)

- [ ] **Step 2: Write the failing Python tests** — `tests/unit/test_srt_range.py`:
```python
"""ซับตามช่วงเวลา (C5, AC-SUB-10): กรองคำตามจุดกึ่งกลาง เลื่อนให้เริ่มที่ 0 ตัดปลายซับไม่ให้เกินความยาวช่วง

ไฟล์ range-cases.json / range-golden.json ใช้ร่วมกับ web/src/lib/srt-range.test.ts (ต้องตรงกันทุกไบต์ AC-SUB-06)
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from yttoolkit.core.db import Database
from yttoolkit.core.extractor import FakeExtractor
from yttoolkit.core.srt_builder import PRESETS, Cue, Token, build_cues, clamp_cues, options_from_dict, range_tokens, to_srt
from yttoolkit.core.subtitles import SubtitleService
from yttoolkit.core.videos import VideoService

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
SUBS = FIXTURES / "subs"
CASES = json.loads((SUBS / "range-cases.json").read_text(encoding="utf-8"))["cases"]
GOLDEN_RANGE = (90_000, 210_000)


def _tokens(raw: list[dict]) -> list[Token]:
    return [Token(t["t"], t["s"], t["e"]) for t in raw]


def _srt(tokens: list[Token], start: int, end: int, opts) -> str:
    return to_srt(clamp_cues(build_cues(range_tokens(tokens, start, end), opts), end - start))


@pytest.mark.parametrize("case", CASES, ids=lambda c: c["name"])
def test_range_cases(case):
    ranged = range_tokens(_tokens(case["tokens"]), case["startMs"], case["endMs"])
    assert [{"t": t.t, "s": t.s, "e": t.e} for t in ranged] == case["ranged"]
    assert _srt(_tokens(case["tokens"]), case["startMs"], case["endMs"], options_from_dict(case["options"])) == case["srt"]


@pytest.mark.parametrize("name", ["th-asr", "en-asr"])
def test_real_tokens_match_the_range_golden(name):
    golden = json.loads((SUBS / "range-golden.json").read_text(encoding="utf-8"))
    doc = json.loads((SUBS / "tokens" / f"{name}.json").read_text(encoding="utf-8"))
    assert _srt(_tokens(doc["tokens"]), *GOLDEN_RANGE, PRESETS["medium"]) == golden[f"{name}.medium.90000-210000"]


def test_ac_sub_10_cues_stay_inside_the_range():
    doc = json.loads((SUBS / "tokens" / "th-asr.json").read_text(encoding="utf-8"))
    cues = clamp_cues(build_cues(range_tokens(_tokens(doc["tokens"]), 90_000, 300_000), PRESETS["medium"]), 210_000)
    assert cues and cues[0].start_ms >= 0 and cues[-1].end_ms <= 210_000


def test_clamp_cues_only_shortens_ends():
    cues = [Cue(0, 1000, ("a",)), Cue(1000, 5000, ("b",))]
    assert clamp_cues(cues, 3000) == [Cue(0, 1000, ("a",)), Cue(1000, 3000, ("b",))]


def test_export_with_a_range(tmp_path):
    db = Database(tmp_path / "app.db")
    db.migrate()
    fake = FakeExtractor(FIXTURES)
    subs = SubtitleService(VideoService(db, fake), fake.fetch_subtitle, tmp_path / "cache")
    try:
        full = subs.export("88o5Sk8_m1Y", "a.th-orig", "srt", PRESETS["medium"])
        ranged = subs.export("88o5Sk8_m1Y", "a.th-orig", "srt", PRESETS["medium"], (10_000, 40_000))
        txt = subs.export("88o5Sk8_m1Y", "a.th-orig", "txt", PRESETS["medium"], (10_000, 40_000))
        assert ranged.data == txt.data and ranged.data != full.data
        ends = [int(h) * 3_600_000 + int(m) * 60_000 + int(s) * 1000 + int(ms)
                for h, m, s, ms in re.findall(r"--> (\d\d):(\d\d):(\d\d),(\d\d\d)", ranged.data.decode("utf-8"))]
        assert ends and max(ends) <= 30_000
        with pytest.raises(ValueError):
            subs.export("88o5Sk8_m1Y", "a.th-orig", "md", PRESETS["medium"], (10_000, 40_000))
    finally:
        db.close()
```

- [ ] **Step 3: Run, expect FAIL** — `uv run pytest tests/unit/test_srt_range.py -q -W error -p no:cacheprovider` → `ImportError: cannot import name 'clamp_cues'`.

- [ ] **Step 4: Implement the Python side**

`core/srt_builder.py`, after `build_cues`:
```python
# ---------- ช่วงเวลา (M5 รอบ A, AC-SUB-10) ฝั่ง TS มี rangeTokens / clampCues ที่ต้องได้ผลตรงกันทุกตัว ----------


def range_tokens(tokens: Sequence[Token], start_ms: int, end_ms: int) -> list[Token]:
    """คำที่จุดกึ่งกลางอยู่ในช่วง [start, end) (เทียบแบบจำนวนเต็ม 2*start <= s+e < 2*end)
    เวลาที่คร่อมขอบถูกตัดให้อยู่ในช่วง แล้วเลื่อนให้ช่วงเริ่มที่ 0 (ทำก่อนสร้างซับ)"""
    return [
        Token(tok.t, max(tok.s, start_ms) - start_ms, min(tok.e, end_ms) - start_ms)
        for tok in tokens
        if 2 * start_ms <= tok.s + tok.e < 2 * end_ms
    ]


def clamp_cues(cues: Sequence[Cue], limit_ms: int) -> list[Cue]:
    """ซับสุดท้ายที่ถูกยืดตามเวลาขั้นต่ำต้องไม่เลยปลายช่วง (AC-SUB-10: จบ <= ความยาวช่วง)"""
    return [Cue(c.start_ms, min(c.end_ms, limit_ms), c.lines) for c in cues]
```
`core/subtitles.py`: import `clamp_cues, range_tokens` with the other `srt_builder` names; change `export`:
```python
    def export(
        self, video_id: str, track_id: str, fmt: str, opts: SubOptions, range_ms: tuple[int, int] | None = None
    ) -> SubtitleExport:
        """ไฟล์ซับแบบ srt/txt/md (CRLF, UTF-8 ไม่มี BOM) ชื่อไฟล์ router ตั้งเองจาก title + lang

        txt = เนื้อเดียวกับ srt ทุกไบต์ (เจ้าของตัดสิน owner preview round 2: ต่างกันแค่นามสกุล)
        range_ms = (start, end) เฉพาะ srt/txt: ซับของช่วงนั้นนับเวลาใหม่จาก 0 (AC-SUB-10) md + ช่วง = ValueError
        opts ต้องผ่านการตรวจมาแล้ว (options_from_dict) โหมด tokens ที่ไม่มี tokens_per_cue = ValueError
        """
        if fmt not in FORMATS:
            raise ValueError(f"format must be one of {FORMATS}")
        if range_ms is not None and fmt == "md":
            raise ValueError("range works with srt and txt only")
        info = self._videos.get(video_id, peek=True)
        track = self._track(video_id, track_id)
        tokens: list[Token] = list(self._parsed(video_id, track).tokens)
        title = str(info.get("title") or "")
        if fmt in ("srt", "txt"):
            if range_ms is None:
                text = to_srt(build_cues(tokens, opts))
            else:
                start, end = range_ms
                text = to_srt(clamp_cues(build_cues(range_tokens(tokens, start, end), opts), end - start))
        else:
            text = to_md(tokens, title=title, video_id=video_id, chapters=_chapter_ms(info))
        return SubtitleExport(title, track.lang, text.encode("utf-8"))
```

- [ ] **Step 5: Generate the real-data golden from the Python builder (once) and commit it with the tests**
```bash
uv run python -c "
import json; from pathlib import Path
from yttoolkit.core.srt_builder import PRESETS, Token, build_cues, clamp_cues, range_tokens, to_srt
subs = Path('tests/fixtures/subs'); out = {}
for name in ('th-asr', 'en-asr'):
    doc = json.loads((subs / 'tokens' / f'{name}.json').read_text(encoding='utf-8'))
    tokens = [Token(t['t'], t['s'], t['e']) for t in doc['tokens']]
    out[f'{name}.medium.90000-210000'] = to_srt(clamp_cues(build_cues(range_tokens(tokens, 90000, 210000), PRESETS['medium']), 120000))
(subs / 'range-golden.json').write_text(json.dumps(out, ensure_ascii=False, indent=1) + '\n', encoding='utf-8', newline='\n')
"
```
Check: both values are non-empty and start with `1\r\n00:00:0`. Never regenerate this file to make a test pass; a mismatch means one builder is wrong.

- [ ] **Step 6: Run the Python tests, expect PASS** — `uv run pytest tests/unit/test_srt_range.py tests/unit/test_srt_golden.py tests/unit/test_subtitles.py -q -W error -p no:cacheprovider`.

- [ ] **Step 7: Write the failing TS parity test** — `web/src/lib/srt-range.test.ts`:
```ts
/**
 * ซับตามช่วงเวลา (M5 รอบ A, AC-SUB-10): ฝั่งเว็บต้องได้ผลตรงกับ core/srt_builder.range_tokens/clamp_cues ทุกไบต์
 * อ่านชุดเดียวกับ tests/unit/test_srt_range.py ห้ามแก้ไฟล์ fixture เพื่อให้เทสนี้ผ่าน
 */
import { describe, expect, it } from "vitest"

import casesRaw from "../../../tests/fixtures/subs/range-cases.json?raw"
import goldenRaw from "../../../tests/fixtures/subs/range-golden.json?raw"
import enAsrRaw from "../../../tests/fixtures/subs/tokens/en-asr.json?raw"
import thAsrRaw from "../../../tests/fixtures/subs/tokens/th-asr.json?raw"

import { buildCues, clampCues, rangeTokens, toSrt } from "./srt-builder"
import { PRESETS } from "./sub-options"
import type { SubOptions, SubToken } from "./types"

type RangeCase = {
  name: string
  options: SubOptions
  startMs: number
  endMs: number
  tokens: SubToken[]
  ranged: SubToken[]
  srt: string
}

const cases = (JSON.parse(casesRaw) as { cases: RangeCase[] }).cases
const golden = JSON.parse(goldenRaw) as Record<string, string>
const tokenDocs: Record<string, SubToken[]> = {
  "th-asr": (JSON.parse(thAsrRaw) as { tokens: SubToken[] }).tokens,
  "en-asr": (JSON.parse(enAsrRaw) as { tokens: SubToken[] }).tokens,
}

const srtOf = (tokens: readonly SubToken[], startMs: number, endMs: number, options: SubOptions) =>
  toSrt(clampCues(buildCues(rangeTokens(tokens, startMs, endMs), options), endMs - startMs))

describe("range parity with the Python builder", () => {
  it.each(cases.map((c) => [c.name, c] as const))("%s", (_name, c) => {
    expect(rangeTokens(c.tokens, c.startMs, c.endMs)).toEqual(c.ranged)
    expect(srtOf(c.tokens, c.startMs, c.endMs, c.options)).toBe(c.srt)
  })

  it.each(["th-asr", "en-asr"])("%s medium 90000-210000 matches range-golden.json", (name) => {
    const expected = golden[`${name}.medium.90000-210000`]
    expect(expected.length).toBeGreaterThan(0)
    expect(srtOf(tokenDocs[name], 90_000, 210_000, PRESETS.medium)).toBe(expected)
  })

  it("clampCues shortens only the ends", () => {
    const cues = [
      { startMs: 0, endMs: 1000, lines: ["a"] },
      { startMs: 1000, endMs: 5000, lines: ["b"] },
    ]
    expect(clampCues(cues, 3000)).toEqual([cues[0], { startMs: 1000, endMs: 3000, lines: ["b"] }])
  })
})
```

- [ ] **Step 8: Run, expect FAIL** — `cd web && npx vitest run src/lib/srt-range.test.ts` → `rangeTokens is not exported`.

- [ ] **Step 9: Implement the TS side** — in `web/src/lib/srt-builder.ts` after `buildCues`:
```ts
/**
 * ช่วงเวลา (M5 รอบ A, AC-SUB-10): คำที่จุดกึ่งกลางอยู่ใน [startMs, endMs) (เทียบแบบจำนวนเต็ม 2*start <= s+e < 2*end)
 * เวลาที่คร่อมขอบถูกตัดให้อยู่ในช่วง แล้วเลื่อนให้ช่วงเริ่มที่ 0 · ตรงกับ range_tokens ฝั่ง Python ทุกตัว
 */
export function rangeTokens(tokens: readonly SubToken[], startMs: number, endMs: number): SubToken[] {
  const out: SubToken[] = []
  for (const tok of tokens) {
    const twiceMid = tok.s + tok.e
    if (twiceMid < 2 * startMs || twiceMid >= 2 * endMs) continue
    out.push({ t: tok.t, s: Math.max(tok.s, startMs) - startMs, e: Math.min(tok.e, endMs) - startMs })
  }
  return out
}

/** ซับที่ถูกยืดตามเวลาขั้นต่ำต้องไม่เลยปลายช่วง (ตรงกับ clamp_cues ฝั่ง Python) */
export function clampCues(cues: readonly Cue[], limitMs: number): Cue[] {
  return cues.map((cue) => ({ startMs: cue.startMs, endMs: Math.min(cue.endMs, limitMs), lines: cue.lines }))
}
```

- [ ] **Step 10: Run, expect PASS** — `cd web && npm run typecheck && npm run lint && npm test`, then `uv run pytest -q -W error -p no:cacheprovider`.

- [ ] **Step 11: Commit**
```bash
git add src/yttoolkit/core/srt_builder.py src/yttoolkit/core/subtitles.py web/src/lib/srt-builder.ts tests/fixtures/subs/range-cases.json tests/fixtures/subs/range-golden.json tests/unit/test_srt_range.py web/src/lib/srt-range.test.ts
git commit -F- <<'EOF'
feat(subs): subtitles by time range with Python/TS byte parity (AC-SUB-10)

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
EOF
```

### Task 6: Web types, builders, all M5-A strings, W2 download-state follow-ups

**Files:**
- Modify: `web/src/lib/types.ts` (params types only; `JobStage` is T12's)
- Modify: `web/src/lib/download-options.ts`, `web/src/lib/download-options.test.ts`
- Modify: `web/src/i18n/th.ts`
- Modify: `web/src/pages/video/download/use-download-state.ts`, `web/src/pages/video/download/use-download-state.test.ts`

**Interfaces:**
- Consumes: M4 builders and `useDownloadPrefs`, `settingsQuery`.
- Produces: C7 and C8 exactly; `useDownloadState(...)` adds `ready: boolean`; `qualityForHeight(options, height, cap?)`.

- [ ] **Step 1: Write the failing builder tests** — append to `web/src/lib/download-options.test.ts` (add `buildSubtitleParams, DEFAULT_SPONSOR_CATEGORIES, NO_ADVANCED, SPONSOR_CATEGORIES, sponsorCategories` to the import from `./download-options`):
```ts
describe("M5-A: ตัวเลือกขั้นสูงใน params", () => {
  const base = {
    quality: AUTO_QUALITY,
    maxQuality: false,
    noAudio: false,
    audioLanguage: "original",
    embedSubs: null,
    subOptions: PRESETS.medium,
  }
  const range = { startMs: 90_000, endMs: 300_000 }

  it("ไม่มีตัวเลือกขั้นสูง = params เหมือน M4 ทุกคีย์", () => {
    expect(buildVideoParams({ ...base, advanced: NO_ADVANCED })).toEqual(buildVideoParams(base))
  })

  it("ช่วงเวลาและตัดโฆษณาไปกับงานวิดีโอ", () => {
    expect(buildVideoParams({ ...base, advanced: { splitChapters: false, range, sponsorblock: ["sponsor", "filler"] } })).toEqual({
      maxQuality: false,
      noAudio: false,
      audioLanguage: "original",
      splitChapters: false,
      range,
      sponsorblock: ["sponsor", "filler"],
    })
  })

  it("แยก chapter = ไม่ส่งฝังซับ (ใช้คู่กันไม่ได้ AC-VID-10 ส่วนที่ 2)", () => {
    expect(buildVideoParams({ ...base, embedSubs: "o.th", advanced: { splitChapters: true } })).toEqual({
      maxQuality: false,
      noAudio: false,
      audioLanguage: "original",
      splitChapters: true,
    })
  })

  it("งานเสียงรับตัวเลือกเดียวกัน · ตัดโฆษณาที่ไม่มีหมวด = ไม่ส่ง", () => {
    expect(buildAudioParams({ format: "mp3", mp3Kbps: 192, audioLanguage: "original", advanced: { splitChapters: true } })).toEqual({
      format: "mp3",
      mp3Kbps: 192,
      splitChapters: true,
      audioLanguage: "original",
    })
    expect(buildAudioParams({ format: "m4a", mp3Kbps: 192, audioLanguage: "th", advanced: { splitChapters: false, range, sponsorblock: [] } })).toEqual({
      format: "m4a",
      splitChapters: false,
      audioLanguage: "th",
      range,
    })
  })

  it("งานซับส่งเฉพาะช่วงเวลา", () => {
    expect(buildSubtitleParams({ trackId: "a.th-orig", format: "srt", options: PRESETS.medium, range })).toEqual({
      trackId: "a.th-orig",
      format: "srt",
      options: PRESETS.medium,
      range,
    })
    expect(buildSubtitleParams({ trackId: "a.th-orig", format: "txt", options: PRESETS.medium, range: null })).not.toHaveProperty("range")
  })

  it("หมวด SponsorBlock จากการตั้งค่า: เฉพาะหมวดที่รู้จักตามลำดับหน้าเว็บ · ว่างหรือยังไม่โหลด = 3 หมวดเริ่มต้น", () => {
    expect(SPONSOR_CATEGORIES).toEqual(["sponsor", "selfpromo", "interaction", "intro", "outro", "preview", "filler", "music_offtopic"])
    expect(sponsorCategories(undefined)).toEqual([...DEFAULT_SPONSOR_CATEGORIES])
    expect(sponsorCategories({ sponsorblockDefault: ["filler", "sponsor", "bogus"] })).toEqual(["sponsor", "filler"])
    expect(sponsorCategories({ sponsorblockDefault: [] })).toEqual(["sponsor", "selfpromo", "interaction"])
  })
})
```

- [ ] **Step 2: Update and extend the download-state tests** — in `web/src/pages/video/download/use-download-state.test.ts`:
  - rename the test `"จำความสูงของภาพ VP9 ไว้แต่ปิดความละเอียดสูงสุด = ใช้ H.264 ที่สูงเท่ากัน · 2160 ไม่มีในโหมดเปิดได้ทุกที่ = อัตโนมัติ"` to `"… · 2160 เกินเพดาน = ตัวเลือกที่เพดาน (1080p) ไม่ใช่อัตโนมัติ"` and change its second expectation to `expect(resolveDownloadState(prefs({ quality: 2160 }), clip(), null, {}).quality).toBe("299")`;
  - rename `"ความสูงที่จำไว้เกินเพดาน (1080) = อัตโนมัติ · 720 เริ่มที่ 720p"` to `"ความสูงที่จำไว้เกินเพดาน (1080) = ตัวเลือกที่เพดาน 720p (M4 follow-up) · 720 เริ่มที่ 720p"` and change its first expectation to `.toBe("298")`;
  - append:
```ts
describe("qualityForHeight กับเพดาน (M4 follow-up 'หน้า W2 กับค่าตั้ง' ข้อ 2)", () => {
  const compat = [
    { value: "299", height: 1080, fps: 60, codec: "H.264", compat: true },
    { value: "298", height: 720, fps: 60, codec: "H.264", compat: true },
  ]
  it("ความสูงเกินเพดาน = ตัวเลือกที่เพดาน · ไม่ส่งเพดาน = กติกาเดิม", () => {
    expect(qualityForHeight(compat, 1080, 720)).toBe("298")
    expect(qualityForHeight(compat, 2160, 1080)).toBe("299")
    expect(qualityForHeight(compat, 720, 1080)).toBe("298")
    expect(qualityForHeight(compat, 480, 1080)).toBe("auto")
    expect(qualityForHeight(compat, 2160)).toBe("auto")
  })
  it("ความละเอียดสูงสุดเปิด = ไม่ใช้เพดาน", () => {
    expect(resolveDownloadState(prefs({ quality: 2160, maxQuality: true }), clip(), null, {}, 720).quality).toBe("315")
  })
})
```

- [ ] **Step 3: Run, expect FAIL** — `cd web && npx vitest run src/lib/download-options.test.ts src/pages/video/download/use-download-state.test.ts`.

- [ ] **Step 4: Implement the types** — in `web/src/lib/types.ts`, before `VideoJobParams`:
```ts
/** ช่วงเวลาของงาน (M5 รอบ A): มิลลิวินาที เต็มวินาที เริ่มก่อนจบอย่างน้อย 1 วินาที */
export type TimeRange = { startMs: number; endMs: number }

/** หมวด SponsorBlock ที่ตัดได้ (ตรงกับ core/jobs.SPONSORBLOCK_CATEGORIES) */
export type SponsorCategory =
  | "sponsor"
  | "selfpromo"
  | "interaction"
  | "intro"
  | "outro"
  | "preview"
  | "filler"
  | "music_offtopic"
```
In `VideoJobParams` replace `splitChapters: false` with:
```ts
  /** แยกไฟล์ตาม chapter (M5 รอบ A) ใช้คู่กับ range, sponsorblock และ embedSubs ไม่ได้ */
  splitChapters: boolean
  /** โหลดเฉพาะช่วง (M5 รอบ A) */
  range?: TimeRange
  /** หมวดโฆษณาที่ตัด (M5 รอบ A) ไม่มีคีย์ = ไม่ตัด */
  sponsorblock?: SponsorCategory[]
```
`AudioJobParams` gets the same three fields (replacing `splitChapters: false`). `SubtitleJobParams` becomes `GroupFolder & { trackId?: string; format: SubExportFormat; options: SubOptions; range?: TimeRange }`.

- [ ] **Step 5: Implement the builders** — in `web/src/lib/download-options.ts` add `SponsorCategory, SubExportFormat, SubtitleJobParams, TimeRange` to the type import, then add after `batchMinutes`:
```ts
/** หมวด SponsorBlock ทั้ง 8 แบบตามลำดับที่หน้าเว็บแสดง (ตรงกับ core/jobs.SPONSORBLOCK_CATEGORIES) */
export const SPONSOR_CATEGORIES: readonly SponsorCategory[] = [
  "sponsor",
  "selfpromo",
  "interaction",
  "intro",
  "outro",
  "preview",
  "filler",
  "music_offtopic",
]

/** หมวดที่ติ๊กไว้เมื่อยังไม่เคยเลือกเอง (ค่าเริ่มต้นของการตั้งค่า sponsorblockDefault) */
export const DEFAULT_SPONSOR_CATEGORIES: readonly SponsorCategory[] = ["sponsor", "selfpromo", "interaction"]

/** หมวดที่ติ๊กไว้จากการตั้งค่า (D3 จำข้ามคลิป): เฉพาะหมวดที่รู้จัก เรียงตาม SPONSOR_CATEGORIES · ว่างหรือยังไม่โหลด = ค่าเริ่มต้น */
export function sponsorCategories(s: Pick<Settings, "sponsorblockDefault"> | undefined): SponsorCategory[] {
  const saved = new Set(s?.sponsorblockDefault ?? [])
  const known = SPONSOR_CATEGORIES.filter((category) => saved.has(category))
  return known.length > 0 ? known : [...DEFAULT_SPONSOR_CATEGORIES]
}

/** ตัวเลือกขั้นสูงที่ไปกับงานวิดีโอ/เสียง (M5 รอบ A) · ไม่มีหมวดโฆษณา = ไม่ตัดโฆษณา */
export type AdvancedParams = { range?: TimeRange; splitChapters: boolean; sponsorblock?: SponsorCategory[] }

/** ไม่ใช้ตัวเลือกขั้นสูง (W3 และค่าเริ่มต้นของตัวสร้าง params) */
export const NO_ADVANCED: AdvancedParams = { splitChapters: false }

/** ใส่ช่วงเวลาและหมวดโฆษณาลง params (เฉพาะที่มีค่า) */
function addAdvanced(params: { range?: TimeRange; sponsorblock?: SponsorCategory[] }, advanced: AdvancedParams): void {
  if (advanced.range) params.range = advanced.range
  if (advanced.sponsorblock && advanced.sponsorblock.length > 0) params.sponsorblock = [...advanced.sponsorblock]
}
```
`buildVideoParams` — add `advanced?: AdvancedParams` to its input type and replace the body:
```ts
  const advanced = input.advanced ?? NO_ADVANCED
  const params: VideoJobParams = {
    maxQuality: input.maxQuality,
    splitChapters: advanced.splitChapters,
    noAudio: input.noAudio,
    audioLanguage: input.audioLanguage,
  }
  if (input.compatCap === 720 && !input.maxQuality) params.maxHeight = 720
  if (input.quality !== AUTO_QUALITY) params.formatId = input.quality
  // แยกตาม chapter ใช้คู่กับฝังซับไม่ได้ (backend ตอบ 422): ไม่ส่งฝังซับเลย
  if (input.embedSubs !== null && !advanced.splitChapters) {
    params.embedSubs = input.embedSubs
    params.subOptions = input.subOptions
  }
  addAdvanced(params, advanced)
  return params
```
`buildAudioParams` — add `advanced?: AdvancedParams` to its input and replace the body:
```ts
  const advanced = input.advanced ?? NO_ADVANCED
  const params: AudioJobParams = {
    format: input.format,
    splitChapters: advanced.splitChapters,
    audioLanguage: input.audioLanguage,
  }
  if (input.format === "mp3") params.mp3Kbps = input.mp3Kbps
  addAdvanced(params, advanced)
  return params
```
Add after `buildAudioParams`:
```ts
/** ค่าของงานซับ (แท็บซับ) · มีช่วงเวลา = ซับเฉพาะช่วงนั้นนับเวลาใหม่จาก 0 (AC-SUB-10) */
export function buildSubtitleParams(input: {
  trackId: string
  format: SubExportFormat
  options: SubOptions
  range?: TimeRange | null
}): SubtitleJobParams {
  const params: SubtitleJobParams = { trackId: input.trackId, format: input.format, options: input.options }
  if (input.range) params.range = input.range
  return params
}
```
`paramsFromSettings` keeps `splitChapters: false` (W3, D8) — no change.

- [ ] **Step 6: Implement the download-state follow-ups** — in `web/src/pages/video/download/use-download-state.ts`:
```ts
/**
 * คุณภาพเริ่มต้นจากค่าที่จำไว้ (จำเป็นความสูงของภาพ ไม่ใช่ formatId): ตัวเลือกที่สูงเท่ากัน โดยเลือกแบบเปิดได้ทุกที่ (H.264)
 * ก่อน แล้วค่อยตามลำดับของ qualityOptions (fps มากสุดก่อน) · ไม่มีความสูงนั้น หรือจำว่า "auto" = "auto"
 * cap (โหมดเปิดได้ทุกที่): ความสูงที่จำไว้เกินเพดาน = ใช้ความสูงที่เพดานแทน ไม่กลายเป็น "อัตโนมัติ" เงียบ ๆ (M4 follow-up)
 */
export function qualityForHeight(options: readonly QualityOption[], height: DownloadPrefs["quality"], cap?: number): string {
  if (height === AUTO_QUALITY) return AUTO_QUALITY
  const wanted = cap === undefined ? height : Math.min(height, cap)
  const same = options.filter((option) => option.height === wanted)
  return (same.find((option) => option.compat) ?? same[0])?.value ?? AUTO_QUALITY
}
```
In `resolveDownloadState` change the fallback to `qualityForHeight(options, prefs.quality, maxQuality ? undefined : cap)`. In `useDownloadState`:
```ts
  // M4 follow-up: กดโหลดก่อนค่าตั้งมาถึงเคยใช้เพดาน 1080 · ปุ่มโหลดรอจนค่าตั้งโหลดเสร็จ (หรือโหลดไม่สำเร็จ = ใช้ค่าเริ่มต้น)
  const ready = !settings.isPending
  return { state, languages, remember, cap, ready }
```

- [ ] **Step 7: Add the strings (C8)** — in `web/src/i18n/th.ts`:
  - inside `queue`, replace the `stages` line with
```ts
    stages: { probing: "ดึงข้อมูล", downloading_video: "โหลดภาพ", downloading_audio: "โหลดเสียง", merging: "รวมไฟล์", converting: "แปลงไฟล์", writing: "บันทึกไฟล์", cutting: "กำลังตัดช่วง", cutting_ads: "กำลังตัดโฆษณา" },
    // M5 รอบ A: ขั้นแยกไฟล์ตาม chapter (stage "splitting:<i>/<n>") และตัวเลือกที่ต่อท้ายชื่องานในแถวคิว
    splitting: "กำลังแยก chapter {i}/{n}",
    choice: { range: " · ช่วง {range}", chapters: " · แยก chapter", ads: " · ตัดโฆษณา" },
```
  - add a new top-level key `advanced` right after the closing `},` of `download` with exactly the C8 `advanced` object (all keys and texts verbatim).

- [ ] **Step 8: Run, expect PASS** — `cd web && npm run typecheck && npm run lint && npm test`.

- [ ] **Step 9: Commit**
```bash
git add web/src/lib/types.ts web/src/lib/download-options.ts web/src/lib/download-options.test.ts web/src/i18n/th.ts web/src/pages/video/download/use-download-state.ts web/src/pages/video/download/use-download-state.test.ts
git commit -F- <<'EOF'
feat(web): M5-A job params, builders, strings; W2 waits for settings, keeps the cap height

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
EOF
```

### Task 7: Web advanced-options logic and the per-clip store

**Files:**
- Create: `web/src/lib/advanced-options.ts`, `web/src/lib/advanced-options.test.ts`
- Create: `web/src/pages/video/advanced/advanced-store.ts`, `web/src/pages/video/advanced/advanced-store.test.ts`

**Interfaces:**
- Consumes: `formatDuration` (`web/src/lib/format.ts`), `VideoInfo` (types).
- Produces: C9 exactly, with `RangeError = "format" | "order" | "beyond"` (whole-second input can never give a range shorter than 1 s once start < end, so the spec's "ช่วงต้องยาวอย่างน้อย 1 วินาที" stays in `th.ts` for completeness and is enforced by the API).

- [ ] **Step 1: Write the failing tests** — `web/src/lib/advanced-options.test.ts`:
```ts
import { describe, expect, it } from "vitest"

import {
  chapterBlock,
  chaptersAvailable,
  choiceParts,
  keptSeconds,
  parseClock,
  rangeAvailable,
  rangeText,
  scaleBytes,
  validateRange,
} from "./advanced-options"

describe("parseClock", () => {
  it.each([
    ["90", 90],
    ["0", 0],
    ["1:30", 90],
    ["01:30", 90],
    ["100:00", 6000],
    ["1:02:30", 3750],
    [" 5:00 ", 300],
  ])("%s = %d วินาที", (text, seconds) => {
    expect(parseClock(text)).toBe(seconds)
  })

  it.each(["", "1:3", "1:60", "1.30", "-5", "1:02:3", "123456", "1:30:00:00", "๑:๓๐", "1:30.5", "abc"])("%s อ่านไม่ได้", (text) => {
    expect(parseClock(text)).toBeNull()
  })
})

describe("validateRange (คลิป 6:12 = 372 วินาที)", () => {
  const D = 372
  it("ว่างทั้งสองช่อง = ไม่มีช่วง ไม่มี error", () => {
    expect(validateRange("", " ", D)).toEqual({ range: null, startError: null, endError: null })
  })
  it("ช่องว่างหนึ่งช่อง = ปลายอีกด้านของคลิป", () => {
    expect(validateRange("1:30", "5:00", D).range).toEqual({ startMs: 90_000, endMs: 300_000 })
    expect(validateRange("", "5:00", D).range).toEqual({ startMs: 0, endMs: 300_000 })
    expect(validateRange("1:30", "", D).range).toEqual({ startMs: 90_000, endMs: 372_000 })
    expect(validateRange("0:00", "6:12", D).range).toEqual({ startMs: 0, endMs: 372_000 })
  })
  it("พิมพ์ผิดรูปแบบ = error ใต้ช่องนั้น", () => {
    expect(validateRange("1:3x", "", D)).toEqual({ range: null, startError: "format", endError: null })
    expect(validateRange("", "abc", D)).toEqual({ range: null, startError: null, endError: "format" })
  })
  it("เริ่มไม่ก่อนจบ = error ที่ช่องเริ่ม", () => {
    expect(validateRange("5:00", "1:30", D)).toEqual({ range: null, startError: "order", endError: null })
    expect(validateRange("6:12", "", D)).toEqual({ range: null, startError: "order", endError: null })
  })
  it("เกินความยาวคลิป", () => {
    expect(validateRange("", "9:00", D)).toEqual({ range: null, startError: null, endError: "beyond" })
    expect(validateRange("7:00", "", D)).toEqual({ range: null, startError: "beyond", endError: null })
  })
})

describe("ความพร้อมของคลิป", () => {
  it("ช่วงเวลา: ต้องไม่ใช่คลิปสดและรู้ความยาว · chapter: อย่างน้อย 2", () => {
    expect(rangeAvailable({ isLive: false, durationS: 372 })).toBe(true)
    expect(rangeAvailable({ isLive: true, durationS: 372 })).toBe(false)
    expect(rangeAvailable({ isLive: false, durationS: 0 })).toBe(false)
    expect(chaptersAvailable({ chapters: [] })).toBe(false)
    expect(chaptersAvailable({ chapters: [{ startS: 0, endS: 5, title: "a" }] })).toBe(false)
    expect(chaptersAvailable({ chapters: [{ startS: 0, endS: 5, title: "a" }, { startS: 5, endS: 9, title: "b" }] })).toBe(true)
  })
})

describe("ป้ายและขนาด", () => {
  it("ข้อความช่วงแบบเวลาในแอพ", () => {
    expect(rangeText({ startMs: 90_000, endMs: 300_000 })).toBe("1:30-5:00")
    expect(rangeText({ startMs: 3_750_000, endMs: 3_900_000 })).toBe("1:02:30-1:05:00")
  })
  it("ส่วนของป้ายปุ่มตามลำดับ ช่วง → chapter → โฆษณา", () => {
    const range = { startMs: 0, endMs: 60_000 }
    expect(choiceParts({ range, splitChapters: false, ads: true })).toEqual([{ kind: "range", range }, { kind: "ads" }])
    expect(choiceParts({ range: null, splitChapters: true, ads: false })).toEqual([{ kind: "chapters" }])
    expect(choiceParts({ range: null, splitChapters: false, ads: false })).toEqual([])
  })
  it("ขนาดประมาณตามความยาวที่เหลือ", () => {
    expect(keptSeconds({ startMs: 90_000, endMs: 300_000 })).toBe(210)
    expect(scaleBytes(372_000_000, 372, 210)).toBe(210_000_000)
    expect(scaleBytes(372_000_000, 372, undefined)).toBe(372_000_000)
    expect(scaleBytes(undefined, 372, 210)).toBeUndefined()
    expect(scaleBytes(1000, 0, 10)).toBe(1000)
  })
})

describe("chapterBlock: ใครเปิดก่อนชนะ", () => {
  const empty = { startText: "", endText: "", sponsorblock: false }
  it("ช่วงเวลา → ตัดโฆษณา → ฝังซับ", () => {
    expect(chapterBlock(empty, false)).toBeNull()
    expect(chapterBlock({ ...empty, endText: "5:00" }, true)).toBe("range")
    expect(chapterBlock({ ...empty, sponsorblock: true }, true)).toBe("sponsorblock")
    expect(chapterBlock(empty, true)).toBe("embedSubs")
  })
})
```
`web/src/pages/video/advanced/advanced-store.test.ts`:
```ts
import { beforeEach, describe, expect, it } from "vitest"

import { __resetAdvancedForTests, advancedActions, advancedActive, EMPTY_ADVANCED, getAdvanced } from "./advanced-store"

beforeEach(() => __resetAdvancedForTests())

describe("ค่าตัวเลือกขั้นสูงต่อคลิป (D3)", () => {
  it("เริ่มว่าง และคืนก้อนเดิมทุกครั้ง (useSyncExternalStore ต้องได้อ้างอิงเดิม)", () => {
    expect(getAdvanced("aqz-KE-bpKQ")).toBe(EMPTY_ADVANCED)
    expect(EMPTY_ADVANCED).toEqual({ startText: "", endText: "", splitChapters: false, sponsorblock: false, open: false, checked: false })
  })

  it("ทุกแท็บของคลิปเดียวกันเห็นค่าเดียวกัน · เปิดคลิปอื่น = เริ่มใหม่", () => {
    advancedActions.patch("aqz-KE-bpKQ", { startText: "1:30" })
    expect(getAdvanced("aqz-KE-bpKQ").startText).toBe("1:30")
    expect(getAdvanced("88o5Sk8_m1Y")).toBe(EMPTY_ADVANCED)
    advancedActions.patch("88o5Sk8_m1Y", { endText: "2:00" })
    expect(getAdvanced("aqz-KE-bpKQ")).toBe(EMPTY_ADVANCED)
    expect(getAdvanced("88o5Sk8_m1Y")).toMatchObject({ startText: "", endText: "2:00" })
  })

  it("ตั้งจุดจากตัวเล่น/ภาพเฟรม: ปัดลงเป็นวินาที เปิดส่วนตัวเลือก และแสดง error ทันที", () => {
    expect(advancedActions.mark("aqz-KE-bpKQ", "start", 90_999)).toBe("set")
    expect(advancedActions.mark("aqz-KE-bpKQ", "end", 3_750_400)).toBe("set")
    expect(getAdvanced("aqz-KE-bpKQ")).toMatchObject({ startText: "1:30", endText: "1:02:30", open: true, checked: true })
  })

  it("แยก chapter เปิดอยู่ = ตั้งจุดไม่ได้ ค่าไม่เปลี่ยน", () => {
    advancedActions.patch("jNQXAC9IVRw", { splitChapters: true })
    expect(advancedActions.mark("jNQXAC9IVRw", "start", 5_000)).toBe("blocked")
    expect(getAdvanced("jNQXAC9IVRw").startText).toBe("")
  })

  it("ใช้ตัวเลือกขั้นสูงอยู่ = มีข้อความในช่องเวลา หรือเปิดแยก chapter / ตัดโฆษณา", () => {
    expect(advancedActive(EMPTY_ADVANCED)).toBe(false)
    expect(advancedActive({ ...EMPTY_ADVANCED, open: true, checked: true })).toBe(false)
    expect(advancedActive({ ...EMPTY_ADVANCED, endText: "5:00" })).toBe(true)
    expect(advancedActive({ ...EMPTY_ADVANCED, splitChapters: true })).toBe(true)
    expect(advancedActive({ ...EMPTY_ADVANCED, sponsorblock: true })).toBe(true)
  })
})
```

- [ ] **Step 2: Run, expect FAIL** — `cd web && npx vitest run src/lib/advanced-options.test.ts src/pages/video/advanced/advanced-store.test.ts` (modules missing).

- [ ] **Step 3: Implement `web/src/lib/advanced-options.ts`**
```ts
import { formatDuration } from "./format"
import type { VideoInfo } from "./types"

/** ช่วงเวลาที่ผู้ใช้ตั้ง (มิลลิวินาที เต็มวินาที) รูปร่างเดียวกับ TimeRange ของงาน */
export type ClipRange = { startMs: number; endMs: number }

/** เหตุผลที่ช่องเวลาใช้ไม่ได้ (ข้อความอยู่ที่ th.advanced.errors) */
export type RangeError = "format" | "order" | "beyond"

export type RangeCheck = { range: ClipRange | null; startError: RangeError | null; endError: RangeError | null }

const NONE: RangeCheck = { range: null, startError: null, endError: null }

// ss | m:ss | mm:ss | h:mm:ss (วินาทีเต็ม ไม่มีทศนิยม ตัวเลขอารบิกเท่านั้น)
const CLOCK = /^(?:(\d{1,5})|(\d{1,3}):([0-5]\d)|(\d{1,2}):([0-5]\d):([0-5]\d))$/

/** เวลาที่พิมพ์ในช่อง "เริ่ม"/"จบ" เป็นวินาที · รูปแบบผิด = null */
export function parseClock(text: string): number | null {
  const match = CLOCK.exec(text.trim())
  if (!match) return null
  if (match[1] !== undefined) return Number(match[1])
  if (match[2] !== undefined) return Number(match[2]) * 60 + Number(match[3])
  return Number(match[4]) * 3600 + Number(match[5]) * 60 + Number(match[6])
}

/**
 * ตรวจช่องเวลา (spec 1.1): ว่างทั้งคู่ = ไม่มีช่วง · ว่างช่องเดียว = ปลายอีกด้านของคลิป
 * ลำดับ: รูปแบบผิด / เกินความยาวคลิป (ต่อช่อง) แล้วจึงเริ่มต้องก่อนจบ (แสดงที่ช่องเริ่ม)
 */
export function validateRange(startText: string, endText: string, durationS: number): RangeCheck {
  const startBlank = startText.trim() === ""
  const endBlank = endText.trim() === ""
  if (startBlank && endBlank) return NONE
  const start = startBlank ? 0 : parseClock(startText)
  const end = endBlank ? durationS : parseClock(endText)
  const startError: RangeError | null = start === null ? "format" : start > durationS ? "beyond" : null
  const endError: RangeError | null = end === null ? "format" : end > durationS ? "beyond" : null
  if (start === null || end === null || startError !== null || endError !== null) return { range: null, startError, endError }
  if (start >= end) return { range: null, startError: "order", endError: null }
  return { range: { startMs: start * 1000, endMs: end * 1000 }, startError: null, endError: null }
}

/** ตั้งช่วงเวลาได้: ไม่ใช่คลิปสด และรู้ความยาวคลิป */
export function rangeAvailable(video: Pick<VideoInfo, "isLive" | "durationS">): boolean {
  return !video.isLive && video.durationS > 0
}

/** แยกไฟล์ตาม chapter ได้: คลิปมีอย่างน้อย 2 chapter */
export function chaptersAvailable(video: Pick<VideoInfo, "chapters">): boolean {
  return video.chapters.length >= 2
}

/** "1:30-5:00" (เวลาแบบเดียวกับความยาวคลิปในแอพ) ใช้ทั้งป้ายปุ่ม หัวตัวอย่างซับ และแถวคิว */
export function rangeText(range: ClipRange): string {
  return `${formatDuration(range.startMs / 1000)}-${formatDuration(range.endMs / 1000)}`
}

export function keptSeconds(range: ClipRange): number {
  return (range.endMs - range.startMs) / 1000
}

/** ขนาดประมาณตามความยาวที่เหลือหลังตัดช่วง (ไม่รู้ขนาด หรือไม่มีช่วง = ค่าเดิม) */
export function scaleBytes(bytes: number | undefined, durationS: number, keptS: number | undefined): number | undefined {
  if (bytes === undefined || keptS === undefined || durationS <= 0) return bytes
  return Math.round((bytes * Math.min(keptS, durationS)) / durationS)
}

export type ChoicePart = { kind: "range"; range: ClipRange } | { kind: "chapters" } | { kind: "ads" }

/** ส่วนที่ต่อท้ายป้ายปุ่มโหลด เช่น "โหลด mp4 (1:30-5:00, ตัดโฆษณา)" เรียง ช่วง → chapter → โฆษณา */
export function choiceParts(o: { range: ClipRange | null; splitChapters: boolean; ads: boolean }): ChoicePart[] {
  const parts: ChoicePart[] = []
  if (o.range) parts.push({ kind: "range", range: o.range })
  if (o.splitChapters) parts.push({ kind: "chapters" })
  if (o.ads) parts.push({ kind: "ads" })
  return parts
}

export type ChapterBlock = "range" | "sponsorblock" | "embedSubs"

/** เหตุผลที่สวิตช์ "แยกไฟล์ตาม chapter" กดไม่ได้ (ตัวที่เปิดก่อนชนะ spec 1.2) · null = กดได้ */
export function chapterBlock(
  v: { startText: string; endText: string; sponsorblock: boolean },
  embedSubsOn: boolean,
): ChapterBlock | null {
  if (v.startText.trim() !== "" || v.endText.trim() !== "") return "range"
  if (v.sponsorblock) return "sponsorblock"
  if (embedSubsOn) return "embedSubs"
  return null
}
```

- [ ] **Step 4: Implement `web/src/pages/video/advanced/advanced-store.ts`**
```ts
import { useSyncExternalStore } from "react"

import { formatDuration } from "@/lib/format"

/**
 * ค่าตัวเลือกขั้นสูงของคลิปที่เปิดอยู่ (M5 รอบ A, D3): ก้อนเดียวในหน่วยความจำ ใช้ร่วมกันทุกแท็บ ตัวเล่น และเมนูภาพเฟรม
 * เปิดคลิปอื่นหรือโหลดหน้าใหม่ = เริ่มใหม่ · ส่งงานเข้าคิวแล้วค่ายังอยู่ (โหลดอีกแบบของช่วงเดิมได้)
 * หมวด SponsorBlock ไม่อยู่ที่นี่ (จำข้ามคลิปในการตั้งค่า sponsorblockDefault)
 */
export type AdvancedValues = {
  /** ข้อความในช่อง "เริ่ม" / "จบ" ตามที่พิมพ์ (ตรวจด้วย validateRange) */
  startText: string
  endText: string
  splitChapters: boolean
  /** สวิตช์ "ตัดโฆษณา (SponsorBlock)" เริ่มปิดทุกคลิป */
  sponsorblock: boolean
  /** ส่วน "ตัวเลือกขั้นสูง" กางอยู่ (กดตั้งจุดจากตัวเล่นแล้วกางให้เอง) */
  open: boolean
  /** แสดง error ของช่องเวลาแล้ว (ออกจากช่อง กดตั้งจุด หรือกดโหลด) */
  checked: boolean
}

export const EMPTY_ADVANCED: AdvancedValues = Object.freeze({
  startText: "",
  endText: "",
  splitChapters: false,
  sponsorblock: false,
  open: false,
  checked: false,
})

let held: { videoId: string | null; values: AdvancedValues } = { videoId: null, values: EMPTY_ADVANCED }
const listeners = new Set<() => void>()

function subscribe(listener: () => void): () => void {
  listeners.add(listener)
  return () => {
    listeners.delete(listener)
  }
}

/** ค่าของคลิปนี้ (คลิปอื่น = ค่าว่างก้อนเดิมเสมอ) */
export function getAdvanced(videoId: string): AdvancedValues {
  return held.videoId === videoId ? held.values : EMPTY_ADVANCED
}

/** มีตัวเลือกขั้นสูงที่ใช้อยู่ (ป้าย "ใช้ตัวเลือกขั้นสูงอยู่" ทุกแท็บ) */
export function advancedActive(v: AdvancedValues): boolean {
  return v.startText.trim() !== "" || v.endText.trim() !== "" || v.splitChapters || v.sponsorblock
}

export const advancedActions = {
  /** แก้ค่าของคลิปนี้ (คลิปอื่นที่ค้างอยู่ถูกล้าง) */
  patch(videoId: string, patch: Partial<AdvancedValues>): void {
    held = { videoId, values: { ...getAdvanced(videoId), ...patch } }
    for (const listener of listeners) listener()
  },
  /** "ตั้งจุดเริ่ม/จบ" จากตัวเล่นหรือภาพเฟรม: เวลาปัดลงเป็นวินาที · แยก chapter เปิดอยู่ = "blocked" ไม่เปลี่ยนค่า */
  mark(videoId: string, which: "start" | "end", ms: number): "set" | "blocked" {
    if (getAdvanced(videoId).splitChapters) return "blocked"
    const text = formatDuration(Math.floor(Math.max(0, ms) / 1000))
    advancedActions.patch(videoId, {
      ...(which === "start" ? { startText: text } : { endText: text }),
      open: true,
      checked: true,
    })
    return "set"
  },
}

/** ค่าของคลิปนี้แบบ reactive (เรนเดอร์ใหม่เมื่อค่าของคลิปนี้เปลี่ยน) */
export function useAdvanced(videoId: string): AdvancedValues {
  return useSyncExternalStore(
    subscribe,
    () => getAdvanced(videoId),
    () => getAdvanced(videoId),
  )
}

/** ทดสอบเท่านั้น */
export function __resetAdvancedForTests(): void {
  held = { videoId: null, values: EMPTY_ADVANCED }
  for (const listener of listeners) listener()
}
```

- [ ] **Step 5: Run, expect PASS** — `cd web && npm run typecheck && npm run lint && npm test`.

- [ ] **Step 6: Commit**
```bash
git add web/src/lib/advanced-options.ts web/src/lib/advanced-options.test.ts web/src/pages/video/advanced/advanced-store.ts web/src/pages/video/advanced/advanced-store.test.ts
git commit -F- <<'EOF'
feat(web): time-field parsing/validation, labels and the per-clip advanced store

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
EOF
```

---

## Wave 2

### Task 8: Handlers — time range, SponsorBlock, subtitle and embedded-subtitle range

**Files:**
- Modify: `src/yttoolkit/core/handlers.py`
- Modify: `tests/unit/test_handlers.py`

**Interfaces:**
- Consumes: C1 (`MIN_RANGE_MS`, stages, notes), C2 (`ADS_SUFFIX`, `Interval`, `keep_intervals`, `kept_ms`, `range_suffix`), C3 (`MediaTools.cut`, `MediaMeta`, `FakeMediaTools.cuts`, `CutCall`), C4 (`SponsorSource`, `SponsorBlockError`), C5 (`SubtitleService.export(…, range_ms)` called positionally).
- Produces: C6 for range/ads/subtitles: `HandlerDeps.sponsors: SponsorSource | None = None`, `CUT_DISK_FACTOR = 3`, private helpers `_requested_range`, `_sponsor_segments`, `_duration_ms`, `_Cut`, `_cut` (T13 reuses `_requested_range`, `_duration_ms`, `CUT_DISK_FACTOR`).

- [ ] **Step 1: Write the failing tests** — append to `tests/unit/test_handlers.py` (add to the imports: `from yttoolkit.core.advanced import ADS_SUFFIX`, `SponsorBlockError, video_choice` to the `yttoolkit.core.download` import, `CutCall` to the `yttoolkit.core.media` import):
```python
# ---------- M5 รอบ A: ช่วงเวลา ตัดโฆษณา ซับตามช่วง ----------

RANGE = {"startMs": 90_000, "endMs": 300_000}
ADS = [(60_000, 90_000, "sponsor"), (100_000, 101_000, "intro")]


class StubSponsors:
    """SponsorSource ตามสัญญา C4: ช่วงตายตัว หรือ error=True = ติดต่อ SponsorBlock ไม่ได้"""

    def __init__(self, segments=(), error: bool = False) -> None:
        self.segments = list(segments)
        self.error = error
        self.calls: list[tuple[str, tuple[str, ...], float | None]] = []

    def sponsor_segments(self, video_id, categories, duration_s):
        self.calls.append((video_id, tuple(categories), duration_s))
        if self.error:
            raise SponsorBlockError("fake: unreachable")
        return [s for s in self.segments if s[2] in categories]


def run_with(env, sponsors, kind: str, video_id: str, params: dict, **kwargs):
    return env.run(kind, video_id, params, deps=replace(env.deps, sponsors=sponsors), **kwargs)


def test_video_range_is_cut_exactly_and_named(env):
    result, ctx = env.run("video", BBB, video_params(range=RANGE))
    assert env.media.cuts == [CutCall("media.mp4", "cut.mp4", ((90_000, 300_000),), "exact", "mp4", True)]
    assert ctx.stages.index("cutting") < ctx.stages.index("writing")
    name, kwargs = env.media.calls[-1]
    assert name == "finalize_mp4" and kwargs["meta"].duration_s == 210.0
    assert output_path(result) == env.planned(BBB, BBB_TITLE, " (01.30-05.00)", "mp4")
    assert result.notes == ()


def test_range_end_after_the_clip_is_clipped_to_the_real_duration(env):
    result, _ = env.run("video", BBB, video_params(range={"startMs": 600_000, "endMs": 700_000}))
    assert env.media.cuts[-1].intervals == ((600_000, 635_000),)
    assert output_path(result).name.endswith(" (10.00-10.35).mp4")


def test_range_outside_the_clip_fails_the_job(env):
    with pytest.raises(YtError) as info:
        env.run("video", BBB, video_params(range={"startMs": 700_000, "endMs": 710_000}))
    assert info.value.code == "E_UNKNOWN"
    assert folders(env.out) == []


def test_no_audio_range_name_order(env):
    result, _ = env.run("video", BBB, video_params(noAudio=True, range=RANGE))
    assert env.media.cuts[-1].has_audio is False
    assert output_path(result).name.endswith(" (ไม่มีเสียง) (01.30-05.00).mp4")


def test_sponsorblock_cuts_the_ads(env):
    sponsors = StubSponsors(ADS)
    result, ctx = run_with(env, sponsors, "video", BBB, video_params(sponsorblock=["sponsor"]))
    assert sponsors.calls == [(BBB, ("sponsor",), 635.0)]
    assert env.media.cuts[-1].intervals == ((0, 60_000), (90_000, 635_000))
    assert "cutting_ads" in ctx.stages and "cutting" not in ctx.stages
    assert env.media.calls[-1][1]["meta"].duration_s == 605.0
    assert output_path(result) == env.planned(BBB, BBB_TITLE, ADS_SUFFIX, "mp4")
    assert result.notes == ()


def test_sponsorblock_without_data_keeps_the_full_clip_and_name(env):
    result, ctx = run_with(env, StubSponsors(), "video", BBB, video_params(sponsorblock=["sponsor"]))
    assert env.media.cuts == [] and "cutting_ads" not in ctx.stages
    assert output_path(result) == env.planned(BBB, BBB_TITLE, "", "mp4")
    assert result.notes == ("SPONSORBLOCK_EMPTY",)


@pytest.mark.parametrize("sponsors", [StubSponsors(error=True), None], ids=["error", "no-source"])
def test_sponsorblock_unreachable_keeps_the_full_clip(env, sponsors):
    result, _ = run_with(env, sponsors, "video", BBB, video_params(sponsorblock=["sponsor"]))
    assert env.media.cuts == []
    assert output_path(result) == env.planned(BBB, BBB_TITLE, "", "mp4")
    assert result.notes == ("SPONSORBLOCK_UNREACHABLE",)


def test_range_and_ads_together(env):
    params = video_params(range={"startMs": 30_000, "endMs": 120_000}, sponsorblock=["sponsor"])
    result, _ = run_with(env, StubSponsors(ADS), "video", BBB, params)
    assert env.media.cuts[-1].intervals == ((30_000, 60_000), (90_000, 120_000))
    assert output_path(result).name.endswith(" (00.30-02.00) (ตัดโฆษณา).mp4")


def test_ads_outside_the_range_cut_the_range_only(env):
    params = video_params(range={"startMs": 200_000, "endMs": 260_000}, sponsorblock=["sponsor"])
    result, ctx = run_with(env, StubSponsors(ADS), "video", BBB, params)
    assert env.media.cuts[-1].intervals == ((200_000, 260_000),)
    assert "cutting" in ctx.stages and "cutting_ads" not in ctx.stages
    assert output_path(result).name.endswith(" (03.20-04.20).mp4")
    assert result.notes == ("SPONSORBLOCK_EMPTY",)


def test_sponsors_are_not_asked_without_sponsorblock(env):
    sponsors = StubSponsors(ADS)
    run_with(env, sponsors, "video", BBB, video_params(range=RANGE))
    assert sponsors.calls == []


@pytest.mark.parametrize(
    ("fmt", "target", "method"),
    [("m4a", "m4a", "finalize_m4a"), ("mp3", "wav", "to_mp3"), ("wav", "wav", "to_wav")],
)
def test_audio_range(env, fmt, target, method):
    result, ctx = env.run("audio", BBB, audio_params(fmt, range=RANGE))
    assert env.media.cuts == [CutCall("media.m4a", f"cut.{target}", ((90_000, 300_000),), "exact", target, True)]
    name, kwargs = env.media.calls[-1]
    assert name == method and kwargs["meta"].duration_s == 210.0
    assert "cutting" in ctx.stages
    assert output_path(result) == env.planned(BBB, BBB_TITLE, " (01.30-05.00)", fmt)


def test_audio_sponsorblock(env):
    result, _ = run_with(env, StubSponsors(ADS), "audio", BBB, audio_params("m4a", sponsorblock=["sponsor"]))
    assert env.media.cuts[-1] == CutCall("media.m4a", "cut.m4a", ((0, 60_000), (90_000, 635_000)), "exact", "m4a", True)
    assert output_path(result) == env.planned(BBB, BBB_TITLE, ADS_SUFFIX, "m4a")


def test_subtitle_range_file(env):
    params = {"trackId": "a.th-orig", "format": "srt", "options": MEDIUM, "range": {"startMs": 10_000, "endMs": 40_000}}
    result, _ = env.run("subtitle", THAI, params)
    expected = env.subtitles.export(THAI, "a.th-orig", "srt", PRESETS["medium"], (10_000, 40_000))
    assert output_path(result).read_bytes() == expected.data
    assert output_path(result) == env.planned(THAI, THAI_TITLE, f" (00.10-00.40).{expected.lang}", "srt")


def test_embedded_subtitles_follow_the_range(env):
    params = video_params(embedSubs="a.th-orig", subOptions=MEDIUM, range={"startMs": 10_000, "endMs": 40_000})
    env.run("video", THAI, params)
    name, kwargs = env.media.calls[-1]
    expected = env.subtitles.export(THAI, "a.th-orig", "srt", PRESETS["medium"], (10_000, 40_000)).data
    assert name == "finalize_mp4" and kwargs["sub_text"] == expected


def test_cutting_needs_three_times_the_download_size(env):
    expected = video_choice(env.fake.probe(BBB), video_params()).expected_bytes
    assert expected == 267_891_149
    env.free = 600_000_000  # >= 2 x expected, < 3 x expected
    env.run("video", BBB, video_params())
    with pytest.raises(YtError) as info:
        env.run("video", BBB, video_params(range=RANGE))
    assert info.value.code == "E_DISK_FULL" and info.value.params == {"size": "804 MB"}


def test_cancel_while_cutting_leaves_nothing(env):
    with pytest.raises(JobCancelled):
        env.run("video", BBB, video_params(range=RANGE), cancel_on="cutting")
    assert folders(env.out) == []
```

- [ ] **Step 2: Run, expect FAIL** — `uv run pytest tests/unit/test_handlers.py -q -W error -p no:cacheprovider` (`TypeError: HandlerDeps.__init__() got an unexpected keyword argument 'sponsors'`, no cuts).

- [ ] **Step 3: Implement in `core/handlers.py`**

Imports: `from dataclasses import dataclass, replace`; `from .advanced import ADS_SUFFIX, Interval, keep_intervals, kept_ms, range_suffix`; extend the `.download` import with `DownloadResult, SponsorBlockError, SponsorSource`; extend the `.jobs` import with `MIN_RANGE_MS`; extend the `.media` import with `CutTarget`. Add to the module docstring: `M5 รอบ A: โหลดทั้งคลิปแล้วตัดช่วงเวลา/โฆษณาด้วย ffmpeg (core/media.cut) ก่อนขั้นจัดไฟล์เดิม`.

Constants:
```python
CUT_DISK_FACTOR = 3  # งานที่ตัด: ไฟล์ที่โหลด + ไฟล์ที่ตัด + ไฟล์ที่จัดเสร็จ อยู่พร้อมกันได้
```
`HandlerDeps` gains, as the last field:
```python
    # ที่มาของช่วงโฆษณา (C4 ตัว extractor) lifecycle ต่อให้ None = ติดต่อ SponsorBlock ไม่ได้ (ได้คลิปเต็มพร้อมโน้ต)
    sponsors: SponsorSource | None = None
```
`_disk_checked` gains a keyword `factor: int = DISK_FACTOR` and uses `need = factor * choice.expected_bytes`.

Add after `_disk_checked`:
```python
def _requested_range(params: Mapping[str, Any]) -> Interval | None:
    """ช่วงเวลาของงาน (API ตรวจมาแล้ว) ไม่มี = None · ข้อมูลงานเสีย = E_UNKNOWN"""
    raw = params.get("range")
    if raw is None:
        return None
    start = raw.get("startMs") if isinstance(raw, Mapping) else None
    end = raw.get("endMs") if isinstance(raw, Mapping) else None
    if type(start) is not int or type(end) is not int or start < 0 or end - start < MIN_RANGE_MS:
        raise YtError("E_UNKNOWN", f"range: {raw!r}")
    return start, end


def _sponsor_segments(
    deps: HandlerDeps, ctx: JobContext, clip: _Clip, params: Mapping[str, Any]
) -> tuple[list[Interval] | None, tuple[str, ...]]:
    """ช่วงโฆษณาตามหมวดที่ขอ: None = ไม่ได้ขอตัดโฆษณา หรือติดต่อ SponsorBlock ไม่ได้ (คู่กับโน้ต)

    error ของ SponsorBlock ไม่ทำให้งานล้ม ไม่ลองใหม่ ไม่พักคิว (ไม่ใช่ยูทูป) log บอกแค่ชนิด error
    """
    categories = params.get("sponsorblock")
    if not categories:
        return None, ()
    source = deps.sponsors
    if source is None:
        log.info("งาน %s ไม่มีตัวดึงข้อมูล SponsorBlock ได้คลิปเต็ม", ctx.job_id)
        return None, ("SPONSORBLOCK_UNREACHABLE",)
    try:
        found = source.sponsor_segments(clip.video_id, [str(c) for c in categories], clip.meta.duration_s)
    except SponsorBlockError as exc:
        log.info("งาน %s ติดต่อ SponsorBlock ไม่ได้ (%s) ได้คลิปเต็ม", ctx.job_id, exc)
        return None, ("SPONSORBLOCK_UNREACHABLE",)
    return [(start, end) for start, end, _ in found], ()


def _duration_ms(raw: Mapping[str, Any], clip: _Clip) -> int | None:
    """ความยาวจริงของไฟล์ที่โหลด (duration ของ yt-dlp รอบนี้ ไม่มีใช้ของ probe) ไม่รู้ = None"""
    for value in (raw.get("duration"), clip.info.get("durationS")):
        if isinstance(value, int | float) and not isinstance(value, bool) and value > 0:
            return round(value * 1000)
    return None


@dataclass(frozen=True)
class _Cut:
    path: Path  # ไฟล์ที่จะเข้าขั้นจัดไฟล์ (ไม่ได้ตัด = ไฟล์ที่โหลดมาเอง)
    suffix: str  # ส่วนต่อท้ายชื่อไฟล์ ช่วงเวลา + (ตัดโฆษณา)
    duration_s: float | None  # ความยาวหลังตัด (ความคืบหน้าของขั้นถัดไป)
    notes: tuple[str, ...]


def _cut(
    deps: HandlerDeps,
    ctx: JobContext,
    clip: _Clip,
    result: DownloadResult,
    report: _Reporter,
    *,
    span: Interval | None,
    ads: list[Interval] | None,
    target: CutTarget,
    has_audio: bool,
) -> _Cut:
    """ตัดช่วงเวลาและ/หรือโฆษณาแบบแม่นยำ (D1) ไม่มีอะไรต้องตัด = ใช้ไฟล์ที่โหลดมา ไม่แปลงซ้ำ ไม่ต่อชื่อ

    ปลายช่วงเกินความยาวจริง (API ตรวจไม่ได้เพราะยังไม่มีข้อมูลคลิป) = ตัดปลายให้เท่าความยาวจริง เหลือไม่ถึง 1 วิ = E_UNKNOWN
    ขอตัดโฆษณาแต่ไม่มีอะไรถูกตัดเลย = โน้ต SPONSORBLOCK_EMPTY (ชื่อไฟล์ไม่มี (ตัดโฆษณา))
    """
    full = _Cut(result.path, "", clip.meta.duration_s, ())
    if span is None and ads is None:
        return full
    total = _duration_ms(result.info, clip)
    if span is not None:
        start, end = span
        if total is not None:
            end = min(end, total)
        if end - start < MIN_RANGE_MS:
            raise YtError("E_UNKNOWN", f"range {span} is outside the clip ({total} ms)")
        span = (start, end)
    whole = span if span is not None else ((0, total) if total is not None else None)
    if whole is None:
        raise YtError("E_UNKNOWN", "clip duration unknown, cannot cut")
    keep = keep_intervals(whole, ads or ())
    ads_cut = bool(keep) and keep != [whole]
    notes = ("SPONSORBLOCK_EMPTY",) if ads is not None and not ads_cut else ()
    if span is None and not ads_cut:
        return replace(full, notes=notes)
    if not ads_cut:
        keep = [whole]
    report.stage("cutting_ads" if ads_cut else "cutting")
    out = Path(ctx.workdir) / f"cut.{target}"
    deps.media.cut(result.path, out, keep, mode="exact", target=target, has_audio=has_audio,
                   cancel=ctx.cancelled, on_progress=report.fraction)  # fmt: skip
    ctx.check_cancelled()
    result.path.unlink(missing_ok=True)  # ไฟล์ที่โหลดมาไม่ใช้แล้ว คืนที่ว่างก่อนขั้นจัดไฟล์
    suffix = (range_suffix(*span) if span is not None else "") + (ADS_SUFFIX if ads_cut else "")
    return _Cut(out, suffix, kept_ms(keep) / 1000, notes)
```
`_export_subtitle` gains a last parameter `span: Interval | None = None` and calls `deps.subtitles.export(video_id, track_id, fmt, opts, span)` (both calls, positional). `_embedded_subtitle` gains `span: Interval | None` (last positional) and passes it to `_export_subtitle(deps, ctx, clip.video_id, str(track_id), "srt", opts, span)`.

`_video` becomes:
```python
def _video(deps: HandlerDeps, job: Job, ctx: JobContext) -> JobResult:
    report = _Reporter(ctx)
    clip = _start(deps, job, ctx, report)
    params = job.params
    workdir = Path(ctx.workdir)
    span = _requested_range(params)
    subtitle, sub_notes = _embedded_subtitle(deps, ctx, clip, params, span)
    ads, ad_notes = _sponsor_segments(deps, ctx, clip, params)
    ctx.check_cancelled()
    factor = CUT_DISK_FACTOR if span is not None or ads is not None else DISK_FACTOR

    def choose(raw: dict) -> DownloadChoice:
        return _disk_checked(video_choice(raw, params), (clip.root, workdir), deps.disk_free, factor=factor)

    result = deps.downloader.download(clip.video_id, choose, workdir, _hooks(deps, ctx, report))
    ctx.check_cancelled()
    no_audio = bool(params.get("noAudio"))
    cut = _cut(deps, ctx, clip, result, report, span=span, ads=ads, target="mp4", has_audio=not no_audio)
    cover = _cover(deps, clip, ctx)
    ctx.check_cancelled()
    report.stage("writing")
    out = workdir / "out.mp4"
    deps.media.finalize_mp4(
        cut.path,
        out,
        replace(clip.meta, duration_s=cut.duration_s),
        cover=cover,
        subtitle=subtitle,
        audio_language=result.choice.audio_language,
        cancel=ctx.cancelled,
        on_progress=report.fraction,
        no_audio=no_audio,
    )
    suffix = (NO_AUDIO_SUFFIX if no_audio else "") + cut.suffix
    notes = (*result.choice.notes, *sub_notes, *ad_notes, *cut.notes)
    return _finish(deps, ctx, clip, out, suffix=suffix, ext="mp4", kind="video", notes=notes)
```
`_audio` becomes:
```python
def _audio(deps: HandlerDeps, job: Job, ctx: JobContext) -> JobResult:
    report = _Reporter(ctx)
    clip = _start(deps, job, ctx, report)
    params = job.params
    fmt = str(params.get("format") or "m4a")
    if fmt not in ("m4a", "mp3", "wav"):
        raise YtError("E_UNKNOWN", f"audio format {fmt!r}")
    workdir = Path(ctx.workdir)
    span = _requested_range(params)
    ads, ad_notes = _sponsor_segments(deps, ctx, clip, params)
    ctx.check_cancelled()
    factor = CUT_DISK_FACTOR if span is not None or ads is not None else DISK_FACTOR

    def choose(raw: dict) -> DownloadChoice:
        return _disk_checked(audio_choice(raw, params), (clip.root, workdir), deps.disk_free, factor=factor)

    result = deps.downloader.download(clip.video_id, choose, workdir, _hooks(deps, ctx, report))
    ctx.check_cancelled()
    # m4a ตัดเป็น m4a · mp3/wav ตัดเป็น wav (PCM ตัดได้ตรงตัวอย่างเสียง) แล้วแปลงต่อครั้งเดียว
    cut = _cut(deps, ctx, clip, result, report, span=span, ads=ads, target="m4a" if fmt == "m4a" else "wav", has_audio=True)
    language = result.choice.audio_language
    meta = replace(clip.meta, duration_s=cut.duration_s)
    out = workdir / f"out.{fmt}"
    common: dict[str, Any] = {"audio_language": language, "cancel": ctx.cancelled, "on_progress": report.fraction}
    if fmt == "wav":
        report.stage("converting")
        deps.media.to_wav(cut.path, out, meta, **common)
    else:
        cover = _cover(deps, clip, ctx)
        ctx.check_cancelled()
        if fmt == "mp3":
            report.stage("converting")
            kbps = int(params.get("mp3Kbps") or DEFAULT_MP3_KBPS)
            deps.media.to_mp3(cut.path, out, meta, kbps=kbps, cover=cover, **common)
        else:
            report.stage("writing")
            deps.media.finalize_m4a(cut.path, out, meta, cover=cover, **common)
    report.stage("writing")
    notes = (*result.choice.notes, *ad_notes, *cut.notes)
    return _finish(deps, ctx, clip, out, suffix=cut.suffix, ext=fmt, kind="audio", notes=notes)
```
`_subtitle`: compute `span = _requested_range(params)` after `opts`, call `_export_subtitle(deps, ctx, clip.video_id, str(track_id), fmt, opts, span)`, and finish with `suffix=(range_suffix(*span) if span is not None else "") + f".{lang}"`.

- [ ] **Step 4: Run, expect PASS** — `uv run pytest tests/unit/test_handlers.py -q -W error -p no:cacheprovider`, then `uv run pytest -q -W error -p no:cacheprovider`. Every M4 test in `test_handlers.py` must still pass unchanged (no range/ads = same calls, same names, same stages).

- [ ] **Step 5: Commit**
```bash
git add src/yttoolkit/core/handlers.py tests/unit/test_handlers.py
git commit -F- <<'EOF'
feat(handlers): cut time ranges and SponsorBlock ads after download; subtitles by range

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
EOF
```

### Task 9: Lifecycle sweep learns the M5-A names

**Files:**
- Modify: `src/yttoolkit/lifecycle.py` (constants after `_SWEEP_SUB_EXTS`, `toolkit_name_pattern`, `_sweep_folder`, `sweep_interrupted_outputs`)
- Modify: `tests/unit/test_lifecycle.py`

**Interfaces:**
- Consumes: C2 (`ADS_SUFFIX` from `core/advanced.py`, `chapter_dir_name` from `core/files.py`), `handlers.NO_AUDIO_SUFFIX`.
- Produces: `toolkit_name_pattern(prefix)` that also matches range/ads names (including the shortened stems of C2) and ranged subtitle names; the sweep also cleans the four `แยกตาม chapter (…)` sub-folders and removes them when empty.

- [ ] **Step 1: Write the failing tests** — append to `tests/unit/test_lifecycle.py`:
```python
@pytest.mark.parametrize(
    ("name", "ours"),
    [
        (f"{TITLE} (01.30-05.00).mp4", True),
        (f"{TITLE} (1.02.30-1.05.00) (2).m4a", True),
        (f"{TITLE} (ตัดโฆษณา).mp3", True),
        (f"{TITLE} (ไม่มีเสียง) (01.30-05.00) (ตัดโฆษณา).mp4.part", True),
        (f"{TITLE} (01.30-05.00).th.srt", True),
        (f"{TITLE} (01.30-05.00) (3).en-US.txt", True),
        ("Big (10.00.00-10.05.00) (ตัดโฆษณา).mp4", True),  # stem shortened by files.plan_output (C2)
        ("Big.mp4", False),  # a shortened stem only with a range or ads suffix
        (f"{TITLE} (1.30-5.00).mp4", False),  # minutes need 2 digits when there are no hours
        (f"{TITLE} (ตัดโฆษณา) (01.30-05.00).mp4", False),  # wrong order
        (f"x{TITLE} (01.30-05.00).mp4", False),
        (f"{TITLE} (01.30-05.00).docx", False),
    ],
)
def test_toolkit_name_pattern_covers_m5a_names(name, ours):
    assert bool(lifecycle.toolkit_name_pattern(TITLE).fullmatch(name)) is ours


def test_sweep_cleans_chapter_subfolders(paths):
    db, store, root, folder, job_id = _sweep_env(paths)
    try:
        chapters = folder / files.chapter_dir_name("mp4")
        chapters.mkdir()
        (chapters / "01 - Intro.mp4").write_bytes(b"real chapter")  # ไฟล์ที่ย้ายเสร็จแล้วก่อนโปรแกรมดับ: เก็บไว้
        (chapters / "02 - The cool thing.mp4").write_bytes(b"")  # จองชื่อไว้แล้วดับ
        (chapters / "03.mp4.part").write_bytes(b"half")
        (chapters / "notes.txt").write_bytes(b"")  # ไฟล์ของผู้ใช้
        empty = folder / files.chapter_dir_name("mp3")
        empty.mkdir()
        (empty / "01 - a.mp3").write_bytes(b"")
        stranded = [job.id for job in store.running()]
        store.interrupt_running("หยุดกลางคัน")
        assert lifecycle.sweep_interrupted_outputs(store, root, stranded) == 3
        assert sorted(p.name for p in chapters.iterdir()) == ["01 - Intro.mp4", "notes.txt"]
        assert not empty.exists()
    finally:
        db.close()
```

- [ ] **Step 2: Run, expect FAIL** — `uv run pytest tests/unit/test_lifecycle.py -k "m5a or chapter_subfolders" -q -W error -p no:cacheprovider`.

- [ ] **Step 3: Implement in `lifecycle.py`** — imports: `from .core.advanced import ADS_SUFFIX`, and `chapter_dir_name` via the existing `files` module (`files.chapter_dir_name`). After `_SWEEP_SUB_EXTS`:
```python
# M5 รอบ A: ส่วนต่อท้ายช่วงเวลา " (01.30-05.00)" / " (1.02.30-1.05.00)" (core/advanced.range_suffix)
_RANGE_SUFFIX = r" \((?:\d{2}\.\d{2}-\d{2}\.\d{2}|\d{1,3}\.\d{2}\.\d{2}-\d{1,3}\.\d{2}\.\d{2})\)"
_UNIQUE = r"(?: \((?:[2-9]|[1-9][0-9])\))?"  # " (2)" ... " (99)" จาก files._candidates
# ไฟล์ในโฟลเดอร์ย่อย "แยกตาม chapter (<ext>)": "<NN> - <ชื่อ>.<ext>" หรือ "<NN>.<ext>" (files.plan_chapter_output)
_CHAPTER_EXTS = ("mp4", "m4a", "mp3", "wav")
_CHAPTER_FILE = re.compile(rf"\d{{2,3}}(?: - .+)?{_UNIQUE}\.(?:{'|'.join(_CHAPTER_EXTS)})(?:\.part)?")
```
Replace `toolkit_name_pattern`:
```python
def _prefixes(name: str) -> str:
    """regex ของทุกคำขึ้นต้นที่ไม่ว่างของ name (files.plan_output ตัดชื่อไฟล์ให้สั้นลงเมื่อส่วนท้ายยาวเกิน 30 ตัว)"""
    pattern = ""
    for ch in reversed(name[1:]):
        pattern = f"(?:{re.escape(ch)}{pattern})?"
    return re.escape(name[:1]) + pattern


def toolkit_name_pattern(prefix: str) -> re.Pattern[str]:
    """ชื่อไฟล์ที่ตัวทำงานในคิวสร้างได้จริงในโฟลเดอร์ของคลิป (ใช้ fullmatch) ต่อท้าย .part ได้

    สื่อ/ภาพ/zip: <ชื่อ>[ส่วนต่อท้ายของชนิดงาน][ (N)].<นามสกุล>  เช่น "ชื่อ (ไม่มีเสียง) (2).mp4"
    M5 รอบ A: <ชื่อ>[ (ไม่มีเสียง)][ (ช่วงเวลา)][ (ตัดโฆษณา)][ (N)].<นามสกุล> (ต้องมีช่วงเวลาหรือตัดโฆษณา ชื่ออาจถูกตัดสั้น)
    ซับ: <ชื่อ>[ (ช่วงเวลา)][ (N)].<ภาษา>.<รูปแบบ>  (files วางเลขกันซ้ำไว้หน้ารหัสภาษา)
    ชื่ออื่น (เช่นไฟล์ของผู้ใช้ "<ชื่อ> notes.docx") ไม่ตรง จึงไม่ถูกลบ"""
    name = re.escape(prefix)
    shrunk = _prefixes(prefix)
    suffixes = "|".join(re.escape(s) for s in _SWEEP_SUFFIXES)
    exts = "|".join(_SWEEP_MEDIA_EXTS)
    subs = "|".join(_SWEEP_SUB_EXTS)
    no_audio, ads = re.escape(NO_AUDIO_SUFFIX), re.escape(ADS_SUFFIX)
    media = rf"{name}(?:{suffixes})?{_UNIQUE}\.(?:{exts})"
    cut = rf"{shrunk}(?:{no_audio})?(?:{_RANGE_SUFFIX}(?:{ads})?|{ads}){_UNIQUE}\.(?:{exts})"
    subtitle = rf"{name}{_UNIQUE}\.[A-Za-z0-9-]+\.(?:{subs})"
    subtitle_range = rf"{shrunk}{_RANGE_SUFFIX}{_UNIQUE}\.[A-Za-z0-9-]+\.(?:{subs})"
    return re.compile(rf"(?:{media}|{cut}|{subtitle}|{subtitle_range})(?:\.part)?")
```
`_sweep_folder(folder: Path, ours: re.Pattern[str], keep: set[str]) -> int` — same body, but take the compiled pattern instead of building it from `prefix` (delete the `ours = toolkit_name_pattern(prefix)` line). Add:
```python
def _remove_if_empty(folder: Path) -> None:
    """โฟลเดอร์ย่อยของ chapter ที่ว่างหลังล้างไฟล์ค้าง = ลบทิ้ง (มีไฟล์อื่นอยู่ = rmdir ไม่สำเร็จ ปล่อยไว้)"""
    try:
        folder.rmdir()
    except OSError:
        return
```
In `sweep_interrupted_outputs` replace the inner `removed += _sweep_folder(folder, prefix, keep)` with:
```python
                removed += _sweep_folder(folder, toolkit_name_pattern(prefix), keep)
                for ext in _CHAPTER_EXTS:
                    chapters = folder / files.chapter_dir_name(ext)
                    removed += _sweep_folder(chapters, _CHAPTER_FILE, keep)
                    _remove_if_empty(chapters)
```

- [ ] **Step 4: Run, expect PASS** — `uv run pytest tests/unit/test_lifecycle.py -q -W error -p no:cacheprovider` (all M4 sweep tests unchanged), then the full suite.

- [ ] **Step 5: Commit**
```bash
git add src/yttoolkit/lifecycle.py tests/unit/test_lifecycle.py
git commit -F- <<'EOF'
feat(lifecycle): sweep range/ads names and chapter sub-folders of interrupted jobs

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
EOF
```

### Task 10: W2 "ตัวเลือกขั้นสูง" in the วิดีโอ, เสียง and ซับ tabs

**Files:**
- Create: `web/src/pages/video/advanced/switch-row.tsx`, `web/src/pages/video/advanced/use-advanced-choice.ts`, `web/src/pages/video/advanced/range-fields.tsx`, `web/src/pages/video/advanced/sponsor-controls.tsx`, `web/src/pages/video/advanced/advanced-section.tsx`
- Modify: `web/src/pages/video/download/video-panel.tsx`, `web/src/pages/video/download/audio-panel.tsx`
- Modify: `web/src/pages/video/subs-panel.tsx`, `web/src/pages/video/subs/export-buttons.tsx`, `web/src/pages/video/subs/preview.tsx`
- Create: `web/e2e/advanced-options.spec.ts`
- Modify: `web/e2e/download-tabs.spec.ts` (M4 follow-up items 1 and 3)

**Interfaces:**
- Consumes: C7 (`AdvancedParams`, `buildVideoParams`/`buildAudioParams`/`buildSubtitleParams` with `advanced`, `SPONSOR_CATEGORIES`, `sponsorCategories`), `useDownloadState(...).ready` (T6), C8 strings, C9 (`advanced-store`, `advanced-options`), C5 (`rangeTokens`, `clampCues`), `usePlayerValue`/`getPlayerState` (player store), `patchSettings`, `SETTINGS_KEY`.
- Produces: `AdvancedSection`, `SwitchRow` (moved out of `video-panel.tsx`), `useAdvancedChoice(video, tab, embedSubsOn): AdvancedChoice`, `revealRangeErrors(choice, videoId, tab)`, `fieldId(which, tab)`; field ids `advanced-start-<tab>` / `advanced-end-<tab>`.

- [ ] **Step 1: Create `web/src/pages/video/advanced/switch-row.tsx`** (moved from `video-panel.tsx`, plus a reason)
```tsx
import { useId } from "react"

import { Field, FieldContent, FieldDescription, FieldLabel } from "@/components/ui/field"
import { Switch } from "@/components/ui/switch"

type Props = {
  label: string
  hint: string
  checked: boolean
  onChange: (checked: boolean) => void
  disabled?: boolean
  /** เหตุผลที่กดไม่ได้ (แสดงแทนคำอธิบาย ผูกกับสวิตช์เหมือนคำอธิบาย) null = ไม่มี */
  reason?: string | null
}

/** สวิตช์พร้อมคำอธิบายใต้ชื่อ (คำอธิบายหรือเหตุผลผูกกับสวิตช์ผ่าน aria-describedby) */
export function SwitchRow({ label, hint, checked, onChange, disabled = false, reason = null }: Props) {
  const id = useId()
  const hintId = useId()
  return (
    <Field orientation="horizontal" className="items-start" data-disabled={disabled || undefined}>
      <Switch
        id={id}
        checked={checked}
        onCheckedChange={onChange}
        disabled={disabled}
        aria-describedby={hintId}
        className="mt-0.5"
      />
      <FieldContent>
        <FieldLabel htmlFor={id}>{label}</FieldLabel>
        <FieldDescription id={hintId}>{reason ?? hint}</FieldDescription>
      </FieldContent>
    </Field>
  )
}
```

- [ ] **Step 2: Create `web/src/pages/video/advanced/use-advanced-choice.ts`**
```ts
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { toast } from "sonner"

import { fill, th } from "@/i18n/th"
import {
  chapterBlock,
  chaptersAvailable,
  choiceParts,
  keptSeconds,
  rangeAvailable,
  rangeText,
  validateRange,
  type ChapterBlock,
  type RangeCheck,
} from "@/lib/advanced-options"
import { NO_ADVANCED, SPONSOR_CATEGORIES, sponsorCategories, type AdvancedParams } from "@/lib/download-options"
import { patchSettings, SETTINGS_KEY, settingsQuery } from "@/lib/settings-api"
import type { Settings, SponsorCategory, VideoInfo } from "@/lib/types"

import { advancedActions, advancedActive, useAdvanced, type AdvancedValues } from "./advanced-store"

export type AdvancedTab = "video" | "audio" | "subs"

export type AdvancedChoice = {
  values: AdvancedValues
  patch: (patch: Partial<AdvancedValues>) => void
  /** ป้าย "ใช้ตัวเลือกขั้นสูงอยู่" */
  active: boolean
  /** ตั้งช่วงเวลาได้ (ไม่ใช่คลิปสด รู้ความยาว) */
  rangeOk: boolean
  /** แสดงสวิตช์แยก chapter ในแท็บนี้ (วิดีโอ/เสียง และคลิปมี >= 2 chapter) */
  chaptersOk: boolean
  /** แยก chapter เปิดอยู่ (ทุกแท็บ: ช่องเวลา ตัดโฆษณา และฝังซับกดไม่ได้) */
  split: boolean
  check: RangeCheck
  /** ช่องเวลามี error = กดโหลดแล้วไม่สร้างงาน (AC-ADV-02) */
  invalid: boolean
  /** เหตุผลที่สวิตช์แยก chapter กดไม่ได้ */
  block: ChapterBlock | null
  categories: SponsorCategory[]
  /** ตัวเลือกที่ส่งไปกับงานของแท็บนี้ */
  params: AdvancedParams
  /** ความยาวหลังตัดช่วง (วินาที) ใช้ย่อขนาดประมาณ */
  keptS: number | undefined
  /** ป้ายปุ่มโหลด เช่น "โหลด mp4 (1:30-5:00, ตัดโฆษณา)" */
  label: (base: string) => string
}

/** id ของช่องเวลา (มีแท็บเดียวที่เรนเดอร์อยู่ จึงไม่ซ้ำกัน) */
export const fieldId = (which: "start" | "end", tab: AdvancedTab): string => `advanced-${which}-${tab}`

/**
 * ตัวเลือกขั้นสูงของแท็บหนึ่ง (M5 รอบ A): ค่าจากที่เก็บต่อคลิป + ตรวจช่องเวลา + หมวดโฆษณาจากการตั้งค่า
 * ซับ: ส่งเฉพาะช่วงเวลา · วิดีโอ/เสียง: ช่วงเวลา แยก chapter ตัดโฆษณา (แยก chapter ชนะทุกอย่างที่เปิดทีหลัง)
 */
export function useAdvancedChoice(video: VideoInfo | undefined, tab: AdvancedTab, embedSubsOn: boolean): AdvancedChoice {
  const videoId = video?.videoId ?? ""
  const values = useAdvanced(videoId)
  const settings = useQuery(settingsQuery())
  const rangeOk = video !== undefined && rangeAvailable(video)
  const hasChapters = video !== undefined && chaptersAvailable(video)
  const split = hasChapters && values.splitChapters
  const check: RangeCheck =
    video !== undefined && rangeOk && !split
      ? validateRange(values.startText, values.endText, video.durationS)
      : { range: null, startError: null, endError: null }
  const categories = sponsorCategories(settings.data)
  const media = tab !== "subs"
  const ads = media && values.sponsorblock && !split
  const params: AdvancedParams = { ...NO_ADVANCED, splitChapters: media && split }
  if (check.range) params.range = check.range
  if (ads) params.sponsorblock = categories
  const texts = choiceParts({ range: check.range, splitChapters: params.splitChapters, ads }).map((part) =>
    part.kind === "range" ? rangeText(part.range) : part.kind === "chapters" ? th.advanced.choiceChapters : th.advanced.choiceAds,
  )
  return {
    values,
    patch: (patch) => advancedActions.patch(videoId, patch),
    active: advancedActive(values),
    rangeOk,
    chaptersOk: media && hasChapters,
    split,
    check,
    invalid: check.startError !== null || check.endError !== null,
    block: chapterBlock(values, embedSubsOn),
    categories,
    params,
    keptS: check.range ? keptSeconds(check.range) : undefined,
    label: (base) => (texts.length === 0 ? base : fill(th.advanced.withChoice, { label: base, choice: texts.join(", ") })),
  }
}

/** กดโหลดตอนช่องเวลามี error: กางส่วนตัวเลือก แสดง error แล้วโฟกัสช่องแรกที่ผิด (ไม่สร้างงาน AC-ADV-02) */
export function revealRangeErrors(choice: AdvancedChoice, videoId: string, tab: AdvancedTab): void {
  advancedActions.patch(videoId, { checked: true, open: true })
  const which = choice.check.startError !== null ? "start" : "end"
  requestAnimationFrame(() => document.getElementById(fieldId(which, tab))?.focus())
}

/**
 * ติ๊ก/เอาติ๊กหมวด SponsorBlock: บันทึกลงการตั้งค่า sponsorblockDefault (D3 จำข้ามคลิป) แบบเห็นผลทันที
 * บันทึกไม่สำเร็จ = คืนค่าเดิม + toast · หมวดสุดท้ายเอาติ๊กออกไม่ได้ (ผู้เรียกปิดช่องนั้นไว้ด้วย)
 */
export function useSponsorCategoryToggle(): (category: SponsorCategory, on: boolean, current: readonly SponsorCategory[]) => void {
  const client = useQueryClient()
  const mutation = useMutation({
    mutationFn: (next: SponsorCategory[]) => patchSettings({ sponsorblockDefault: next }),
    onMutate: async (next: SponsorCategory[]) => {
      await client.cancelQueries({ queryKey: SETTINGS_KEY })
      const previous = client.getQueryData<Settings>(SETTINGS_KEY)
      if (previous) client.setQueryData<Settings>(SETTINGS_KEY, { ...previous, sponsorblockDefault: next })
      return { previous }
    },
    onError: (_error, _next, context) => {
      if (context?.previous) client.setQueryData(SETTINGS_KEY, context.previous)
      toast.error(th.general.saveFailed)
    },
    onSuccess: (saved) => client.setQueryData(SETTINGS_KEY, saved),
  })
  return (category, on, current) => {
    const next = SPONSOR_CATEGORIES.filter((c) => (c === category ? on : current.includes(c)))
    if (next.length > 0) mutation.mutate(next)
  }
}
```

- [ ] **Step 3: Create `web/src/pages/video/advanced/range-fields.tsx`**
```tsx
import { Clock } from "lucide-react"
import { useId } from "react"

import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip"
import { fill, th } from "@/i18n/th"
import type { RangeError } from "@/lib/advanced-options"
import { formatDuration } from "@/lib/format"
import type { VideoInfo } from "@/lib/types"

import { getPlayerState, usePlayerValue, type PlayerStatus } from "../player/player-store"
import { fieldId, type AdvancedChoice, type AdvancedTab } from "./use-advanced-choice"

const t = th.advanced

/** ตัวเล่นเริ่มเล่นคลิปนี้แล้ว (มีเวลาให้ใช้) */
const PLAYING: ReadonlySet<PlayerStatus> = new Set(["playing", "paused", "ended"])

function errorText(error: RangeError, durationS: number): string {
  return error === "beyond" ? fill(t.errors.beyond, { duration: formatDuration(durationS) }) : t.errors[error]
}

type FieldProps = {
  id: string
  label: string
  value: string
  error: RangeError | null
  durationS: number
  disabled: boolean
  playerReady: boolean
  onChange: (text: string) => void
  onBlur: () => void
}

/** ช่องเวลา + ปุ่มไอคอน "ใช้เวลาที่ตัวเล่นอยู่ตอนนี้" (D7) · error สีแดงใต้ช่อง ผูกด้วย aria-describedby */
function TimeField({ id, label, value, error, durationS, disabled, playerReady, onChange, onBlur }: FieldProps) {
  const errorId = `${id}-error`
  const message = error === null ? null : errorText(error, durationS)
  const fromPlayer = () => onChange(formatDuration(Math.floor(getPlayerState().currentMs / 1000)))
  return (
    <div role="group" aria-label={label} className="flex flex-col gap-1">
      <Label htmlFor={id}>{label}</Label>
      <div className="flex items-center gap-1">
        <Input
          id={id}
          value={value}
          inputMode="text"
          autoComplete="off"
          spellCheck={false}
          disabled={disabled}
          aria-invalid={message !== null || undefined}
          aria-describedby={message !== null ? errorId : undefined}
          className="w-28"
          onChange={(event) => onChange(event.target.value)}
          onBlur={onBlur}
        />
        <Tooltip>
          <TooltipTrigger render={<span className="inline-flex [&_button:disabled]:pointer-events-none" />}>
            <Button
              variant="ghost"
              size="icon-sm"
              aria-label={t.usePlayerTime}
              disabled={disabled || !playerReady}
              focusableWhenDisabled
              onClick={fromPlayer}
            >
              <Clock aria-hidden />
            </Button>
          </TooltipTrigger>
          <TooltipContent>{playerReady ? t.usePlayerTime : t.playFirst}</TooltipContent>
        </Tooltip>
      </div>
      {message !== null && (
        <p id={errorId} className="text-sm text-destructive">
          {message}
        </p>
      )}
    </div>
  )
}

/**
 * "ช่วงเวลา": ช่อง "เริ่ม" / "จบ" (ss, m:ss, mm:ss, h:mm:ss) · คลิปสด/ไม่รู้ความยาว หรือแยก chapter เปิดอยู่ = กดไม่ได้พร้อมเหตุผล
 * error แสดงหลังออกจากช่อง กดตั้งจุด หรือกดโหลด (values.checked) · แท็บวิดีโอที่มีช่วงแล้ว = บอกว่าตัดเป๊ะแต่ใช้เวลาเพิ่ม
 */
export function RangeFields({ video, tab, choice }: { video: VideoInfo; tab: AdvancedTab; choice: AdvancedChoice }) {
  const noteId = useId()
  const { values, patch, check } = choice
  const playerReady = usePlayerValue((s) => s.videoId === video.videoId && s.started && PLAYING.has(s.status))
  const disabled = !choice.rangeOk || choice.split
  const note = !choice.rangeOk ? t.rangeUnavailable : choice.split ? t.blocked.chapters : null
  const shown = (error: RangeError | null) => (values.checked ? error : null)
  return (
    <fieldset aria-describedby={note !== null ? noteId : undefined} className="flex min-w-0 flex-col gap-2">
      <legend className="mb-2 text-sm font-medium">{t.range}</legend>
      <div className="flex flex-wrap gap-x-6 gap-y-3">
        <TimeField
          id={fieldId("start", tab)}
          label={t.start}
          value={values.startText}
          error={shown(check.startError)}
          durationS={video.durationS}
          disabled={disabled}
          playerReady={playerReady}
          onChange={(startText) => patch({ startText })}
          onBlur={() => patch({ checked: true })}
        />
        <TimeField
          id={fieldId("end", tab)}
          label={t.end}
          value={values.endText}
          error={shown(check.endError)}
          durationS={video.durationS}
          disabled={disabled}
          playerReady={playerReady}
          onChange={(endText) => patch({ endText })}
          onBlur={() => patch({ checked: true })}
        />
      </div>
      {note !== null && (
        <p id={noteId} className="text-sm text-muted-foreground">
          {note}
        </p>
      )}
      {tab === "video" && check.range !== null && <p className="text-sm text-muted-foreground">{t.exactHint}</p>}
    </fieldset>
  )
}
```

- [ ] **Step 4: Create `web/src/pages/video/advanced/sponsor-controls.tsx`**
```tsx
import { Checkbox } from "@/components/ui/checkbox"
import { th } from "@/i18n/th"
import { SPONSOR_CATEGORIES } from "@/lib/download-options"

import { SwitchRow } from "./switch-row"
import { useSponsorCategoryToggle, type AdvancedChoice } from "./use-advanced-choice"

const t = th.advanced

/**
 * สวิตช์ "ตัดโฆษณา (SponsorBlock)" (เริ่มปิดทุกคลิป D3/D5) + รายการหมวด (ติ๊กแล้วจำข้ามคลิปในการตั้งค่า)
 * หมวดสุดท้ายเอาติ๊กออกไม่ได้ · แท็บวิดีโอที่ฝังซับอยู่ = เตือนว่าเวลาซับจะไม่ตรง (FR-ADV-4)
 */
export function SponsorControls({ tab, choice, embedSubsOn }: { tab: "video" | "audio"; choice: AdvancedChoice; embedSubsOn: boolean }) {
  const toggle = useSponsorCategoryToggle()
  const { values, patch, categories, split } = choice
  const on = values.sponsorblock && !split
  return (
    <div className="flex flex-col gap-3">
      <SwitchRow
        label={t.sponsorblock}
        hint={t.sponsorblockHint}
        checked={on}
        disabled={split}
        reason={split ? t.blocked.chapters : null}
        onChange={(sponsorblock) => patch({ sponsorblock })}
      />
      {on && (
        <div role="group" aria-label={t.sponsorblock} className="grid gap-x-4 gap-y-1 pl-10 sm:grid-cols-2">
          {SPONSOR_CATEGORIES.map((category) => {
            const ticked = categories.includes(category)
            return (
              // ชื่อของช่องมาจาก label ที่ครอบ (Base UI ผูกให้เอง) กดข้อความก็ติ๊กได้
              <label key={category} className="flex min-h-8 cursor-pointer items-center gap-2 text-sm">
                <Checkbox
                  checked={ticked}
                  disabled={ticked && categories.length === 1}
                  onCheckedChange={(checked) => toggle(category, checked === true, categories)}
                />
                {t.categories[category]}
              </label>
            )
          })}
        </div>
      )}
      {tab === "video" && on && embedSubsOn && <p className="text-sm text-warning">{t.subsWarning}</p>}
    </div>
  )
}
```

- [ ] **Step 5: Create `web/src/pages/video/advanced/advanced-section.tsx`**
```tsx
import { ChevronDown } from "lucide-react"

import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible"
import { th } from "@/i18n/th"
import type { VideoInfo } from "@/lib/types"

import { RangeFields } from "./range-fields"
import { SponsorControls } from "./sponsor-controls"
import { SwitchRow } from "./switch-row"
import type { AdvancedChoice, AdvancedTab } from "./use-advanced-choice"

const t = th.advanced

type Props = {
  video: VideoInfo
  tab: AdvancedTab
  choice: AdvancedChoice
  /** แท็บวิดีโอฝังซับอยู่ (คำเตือน SponsorBlock) */
  embedSubsOn: boolean
}

/**
 * "ตัวเลือกขั้นสูง" (M5 รอบ A): พับไว้ตอนแรก ค่าชุดเดียวกันทุกแท็บ (ที่เก็บต่อคลิป) · ป้าย "ใช้ตัวเลือกขั้นสูงอยู่" ข้างหัวข้อ
 * วิดีโอ/เสียง: ช่วงเวลา · แยกไฟล์ตาม chapter (คลิปมี >= 2 chapter) · ตัดโฆษณา · ซับ: ช่วงเวลาเท่านั้น
 */
export function AdvancedSection({ video, tab, choice, embedSubsOn }: Props) {
  const { values, patch } = choice
  const chapterReason = !values.splitChapters && choice.block !== null ? t.blocked[choice.block] : null
  return (
    <Collapsible open={values.open} onOpenChange={(open) => patch({ open })} className="flex flex-col gap-3">
      <div className="flex flex-wrap items-center gap-2">
        <CollapsibleTrigger render={<Button variant="ghost" size="sm" className="group/advanced -ml-2.5" />}>
          {t.title}
          <ChevronDown aria-hidden className="transition-transform group-data-[panel-open]/advanced:rotate-180" />
        </CollapsibleTrigger>
        {choice.active && (
          <Badge variant="secondary" data-slot="advanced-active">
            {t.active}
          </Badge>
        )}
      </div>
      <CollapsibleContent className="flex min-w-0 flex-col gap-5 rounded-lg border p-4">
        <RangeFields video={video} tab={tab} choice={choice} />
        {choice.chaptersOk && (
          <SwitchRow
            label={t.chapters}
            hint={tab === "video" ? t.chaptersHint + t.chaptersVideoHint : t.chaptersHint}
            checked={values.splitChapters}
            disabled={chapterReason !== null}
            reason={chapterReason}
            onChange={(splitChapters) => patch({ splitChapters })}
          />
        )}
        {tab !== "subs" && <SponsorControls tab={tab} choice={choice} embedSubsOn={embedSubsOn} />}
      </CollapsibleContent>
    </Collapsible>
  )
}
```

- [ ] **Step 6: Wire the วิดีโอ tab** — in `web/src/pages/video/download/video-panel.tsx`:
  - delete the local `SwitchRowProps`/`SwitchRow` (moved) and the now unused imports (`Field…`, `Switch`); import `SwitchRow` from `../advanced/switch-row`, `AdvancedSection` from `../advanced/advanced-section`, `revealRangeErrors, useAdvancedChoice` from `../advanced/use-advanced-choice`, `scaleBytes` from `@/lib/advanced-options`.
  - in `VideoForm` replace the lines from `const { state, languages, remember, cap } = …` through `const embedDisabled = …` and `submit` with:
```tsx
  const { state, languages, remember, cap, ready } = useDownloadState(video, choices)
  const subSettings = useSubSettings()
  const subtitles = useQuery(subtitlesQuery(video.videoId, enabled))
  const { enqueue, pending } = useEnqueue(ENQUEUE_MESSAGES)

  const options = qualityOptions(video, state.maxQuality, cap)
  // ความละเอียดสูงสุดเปิดอยู่: "อัตโนมัติ" = ภาพดีที่สุดของคลิป (อาจเป็น VP9/AV1) ไม่ใช่ "เปิดได้ทุกที่ 1080p"
  const autoLabel = state.maxQuality ? t.autoMax : fill(t.auto, { h: cap })
  const autoNotCompat = state.maxQuality && options.length > 0 && !options[0].compat
  const labels = new Map<string, string>([[AUTO_QUALITY, autoLabel]])
  for (const option of options) {
    labels.set(option.value, optionLabel(option, videoSizeEstimate(video, option.value, state.noAudio, state.maxQuality, cap)))
  }

  const tracks = subtitles.data ? embeddableTracks(subtitles.data.tracks, originalLanguage(subtitles.data.tracks, video.audio)) : []
  const chosenEmbed = resolveEmbed(choices.embedSubs, tracks)
  const advanced = useAdvancedChoice(video, "video", chosenEmbed !== null)
  // แยกตาม chapter เปิดอยู่ = ไม่ฝังซับ (ใช้คู่กันไม่ได้ AC-VID-10 ส่วนที่ 2) ช่องฝังซับกดไม่ได้พร้อมเหตุผล
  const embedSubs = advanced.split ? null : chosenEmbed
  // รายการแทร็กยังไม่มา = ยังกดไม่ได้ (ไม่มีเหตุผลให้บอก) · มาแล้วไม่มีซับ หรือโหลดไม่สำเร็จ = กดไม่ได้พร้อมเหตุผล
  const embedReason = advanced.split
    ? th.advanced.blocked.chapters
    : subtitles.isPending
      ? null
      : tracks.length === 0
        ? t.embedNoSubs
        : null
  const embedDisabled = advanced.split || tracks.length === 0
  // ขนาดประมาณย่อตามความยาวของช่วงที่ตั้ง (ตัดโฆษณา/แยก chapter = ไม่รู้ล่วงหน้า ใช้ขนาดเต็ม)
  const size = scaleBytes(videoSizeEstimate(video, state.quality, state.noAudio, state.maxQuality, cap), video.durationS, advanced.keptS)

  async function submit() {
    if (pending || !ready) return
    if (advanced.invalid) {
      revealRangeErrors(advanced, video.videoId, "video")
      return
    }
    const params = buildVideoParams({
      quality: state.quality,
      maxQuality: state.maxQuality,
      compatCap: cap,
      noAudio: state.noAudio,
      audioLanguage: state.audioLanguage,
      embedSubs,
      subOptions: subSettings.options,
      advanced: advanced.params,
    })
    const ok = await enqueue([{ videoId: video.videoId, kind: "video", params, title: video.title }])
    if (ok) remember(videoPrefsPatch(state, video, languages, cap))
  }
```
  - keep the quality select, the max-quality `SwitchRow`, `AudioLanguageSelect`, the no-audio `SwitchRow` and the embed block as they are; insert `<AdvancedSection video={video} tab="video" choice={advanced} embedSubsOn={embedSubs !== null} />` right before the button row, and change the button to:
```tsx
        <Button disabled={pending || !ready} focusableWhenDisabled onClick={() => void submit()}>
          {pending ? <Spinner aria-hidden /> : <Download aria-hidden />}
          {advanced.label(t.download)}
        </Button>
```
  - add `th` usage (`th.advanced.blocked.chapters`) — `th` is already imported.

- [ ] **Step 7: Wire the เสียง tab** — in `web/src/pages/video/download/audio-panel.tsx`: import `AdvancedSection`, `revealRangeErrors, useAdvancedChoice`, `scaleBytes`; then in `AudioForm`:
```tsx
  const { state, languages, remember, ready } = useDownloadState(video, choices)
  const { enqueue, pending } = useEnqueue(ENQUEUE_MESSAGES)
  // แยก chapter ถูกกันด้วยการฝังซับที่เลือกไว้ในแท็บวิดีโอ (ค่าชุดเดียวกันทุกแท็บ)
  const advanced = useAdvancedChoice(video, "audio", choices.embedSubs != null)

  const source = wavSourceTrack(video.audio)
  const hint = state.audioFormat === "m4a" ? t.m4aHint : state.audioFormat === "mp3" ? t.mp3Hint : t.wavHint
  const fullSize =
    state.audioFormat === "wav"
      ? wavBytes(video.durationS, source?.sampleRate, source?.channels)
      : audioSizeEstimate(video, state.audioFormat, state.mp3Kbps, state.audioLanguage)
  const size = scaleBytes(fullSize, video.durationS, advanced.keptS)

  async function submit() {
    if (pending || !ready) return
    if (advanced.invalid) {
      revealRangeErrors(advanced, video.videoId, "audio")
      return
    }
    const params = buildAudioParams({
      format: state.audioFormat,
      mp3Kbps: state.mp3Kbps,
      audioLanguage: state.audioLanguage,
      advanced: advanced.params,
    })
    const ok = await enqueue([{ videoId: video.videoId, kind: "audio", params, title: video.title }])
    if (ok) remember(audioPrefsPatch(state, languages))
  }
```
  insert `<AdvancedSection video={video} tab="audio" choice={advanced} embedSubsOn={false} />` right before the button row, and make the button `disabled={pending || !ready}` with label `{advanced.label(fill(t.download, { format: state.audioFormat }))}`.

- [ ] **Step 8: Wire the ซับ tab** — `web/src/pages/video/subs/preview.tsx`: import `useMemo`, `fill`, `rangeText, type ClipRange` from `@/lib/advanced-options`, `clampCues, cueStats, rangeTokens` from `@/lib/srt-builder`; `PreviewBody` and `SubsPreview` gain a prop `range: ClipRange | null` (document it: "ช่วงเวลาที่ตั้งไว้ (null = ทั้งคลิป) ตัวอย่างและหัวข้อเป็นของช่วงนั้น"); pass it from `SubsPreview` to `PreviewBody`; at the top of `PreviewBody`:
```tsx
  const start = range?.startMs
  const end = range?.endMs
  // ช่วงเวลา (AC-SUB-10): คำในช่วงนับเวลาใหม่จาก 0 แบบเดียวกับไฟล์ที่ backend สร้าง (srt-range.test.ts)
  const tokens = useMemo(
    () => (start === undefined || end === undefined ? data.tokens : rangeTokens(data.tokens, start, end)),
    [data.tokens, start, end],
  )
  const built = useCues(tokens, options)
  const cues = useMemo(
    () => (start === undefined || end === undefined ? built : clampCues(built, end - start)),
    [built, start, end],
  )
  const title = range ? fill(th.advanced.previewTitle, { title: t.previewTitle, range: rangeText(range) }) : t.previewTitle
```
  and render `{title}` in the `h3` instead of `{t.previewTitle}` (delete the old `const cues = useCues(data.tokens, options)`).

  `web/src/pages/video/subs/export-buttons.tsx`: import `rangeTokens` (with `toTxt`), `buildSubtitleParams` from `@/lib/download-options`, `type ClipRange` from `@/lib/advanced-options`; add props:
```ts
  /** ช่วงเวลาที่ตั้งไว้ (null = ทั้งคลิป) ไฟล์และข้อความที่คัดลอกเป็นของช่วงนั้น */
  range: ClipRange | null
  /** ช่องเวลามี error: กดโหลดแล้วแสดง error แทนการส่งงาน (AC-ADV-02) */
  invalid: boolean
  onInvalid: () => void
  /** ป้ายปุ่ม เช่น "โหลด .srt (1:30-5:00)" */
  label: (base: string) => string
```
  change `copyTranscript` call to `void copyTranscript(range ? rangeTokens(tokens, range.startMs, range.endMs) : tokens)`, the button text to `{label(text)}` (rename the loop variable `label` of `FORMATS` to `text`), and `download`:
```ts
  async function download(format: SubExportFormat) {
    if (!track || failed || busy !== null) return
    if (invalid) {
      onInvalid()
      return
    }
    setBusy(format)
    try {
      const params = buildSubtitleParams({ trackId: track.id, format, options, range })
      await enqueue([{ videoId, kind: "subtitle", params }])
    } finally {
      setBusy(null)
    }
  }
```
  `web/src/pages/video/subs-panel.tsx`: replace the `useQueryClient().getQueryData(...)` line with a cache-only subscription and add the section, warning and new props:
```tsx
  // ข้อมูลคลิปจาก cache เท่านั้น (หน้า W2 โหลดไว้แล้ว) ไม่ยิงคำขอใหม่ ซึ่งจะนับว่าเปิดคลิปซ้ำ
  const video = useQuery({ ...videoQuery(videoId), enabled: false }).data
  const advanced = useAdvancedChoice(video, "subs", false)
  const range = advanced.params.range ?? null
```
```tsx
          <PresetControls options={settings.options} onPreset={settings.choosePreset} onCustom={settings.setCustom} />
          {video && <AdvancedSection video={video} tab="subs" choice={advanced} embedSubsOn={false} />}
          {track && (
            <>
              <Separator />
              <SubsPreview query={tokens} options={settings.options} onUseOriginal={backToOriginal} range={range} />
            </>
          )}
          {advanced.values.sponsorblock && !advanced.split && (
            <p className="text-sm text-warning">{th.advanced.subsWarning}</p>
          )}
          <ExportButtons
            videoId={videoId}
            track={track}
            options={settings.options}
            tokens={tokens.data?.tokens}
            failed={tokens.isError}
            range={range}
            invalid={advanced.invalid}
            onInvalid={() => revealRangeErrors(advanced, videoId, "subs")}
            label={advanced.label}
          />
```
  (import `useQuery` instead of `useQueryClient` if the latter is no longer used; import `AdvancedSection`, `revealRangeErrors`, `useAdvancedChoice`.)

- [ ] **Step 9: Write the chromium e2e spec** — `web/e2e/advanced-options.spec.ts`:
```ts
/// <reference lib="dom" />
import AxeBuilder from "@axe-core/playwright"
import { expect, test, type Page } from "@playwright/test"

import type { AudioJobParams, Settings, SubtitleJobParams, VideoJobParams } from "../src/lib/types"

import { mockEnqueue } from "./queue-helpers"

/**
 * M5 รอบ A: "ตัวเลือกขั้นสูง" ในแท็บวิดีโอ เสียง ซับ (โปรเจกต์ chromium: ทุกเทสที่กดโหลดดัก POST /api/jobs ด้วย mockEnqueue
 * และทุกเทสที่ติ๊กหมวด SponsorBlock ดัก PATCH /api/settings ไม่มีงานจริงและไม่แก้การตั้งค่าจริง)
 */

const THAI = "88o5Sk8_m1Y" // 372 วิ มีซับ a.th-orig ไม่มี chapter
const BBB = "aqz-KE-bpKQ" // 635 วิ ไม่มีซับ ไม่มี chapter
const ZOO = "jNQXAC9IVRw" // 19 วิ 3 chapter มีซับเจ้าของคลิป

const ADVANCED = "ตัวเลือกขั้นสูง"
const ACTIVE = "ใช้ตัวเลือกขั้นสูงอยู่"
const CHAPTERS = "แยกไฟล์ตาม chapter"
const ADS = "ตัดโฆษณา (SponsorBlock)"

const tab = (page: Page, name: string) => page.getByRole("tab", { name, exact: true })
const panel = (page: Page) => page.getByRole("tabpanel")
const button = (page: Page, name: string) => page.getByRole("button", { name, exact: true })
// ช่องเวลา (role textbox) · ใช้ getByRole ไม่ใช่ getByLabel เพราะกลุ่มของช่องก็มีชื่อ "เริ่ม"/"จบ" (role group)
const field = (page: Page, name: "เริ่ม" | "จบ") => panel(page).getByRole("textbox", { name, exact: true })

async function openAdvanced(page: Page) {
  const trigger = button(page, ADVANCED)
  if ((await trigger.getAttribute("aria-expanded")) !== "true") await trigger.click()
  await expect(trigger).toHaveAttribute("aria-expanded", "true")
}

async function setRange(page: Page, start: string, end: string) {
  await openAdvanced(page)
  await field(page, "เริ่ม").fill(start)
  await field(page, "จบ").fill(end)
  await field(page, "จบ").blur()
}

/**
 * ดัก GET/PATCH /api/settings: อ่านค่าจริงครั้งแรกครั้งเดียว แล้วตอบจากสำเนาในเทส (PATCH รวมค่าที่ส่งมา ไม่แตะ backend)
 * GET ที่ตามมา (เช่น react-query โหลดใหม่) จึงเห็นค่าที่ติ๊กไว้ ไม่เด้งกลับเป็นค่าของ backend
 */
async function mockSettings(page: Page): Promise<{ bodies: Partial<Settings>[] }> {
  const bodies: Partial<Settings>[] = []
  let current: Settings | null = null
  await page.route("**/api/settings", async (route) => {
    const method = route.request().method()
    if (method !== "GET" && method !== "PATCH") return route.fallback()
    if (current === null) current = (await (await route.fetch({ method: "GET" })).json()) as Settings
    if (method === "PATCH") {
      const body = route.request().postDataJSON() as Partial<Settings>
      bodies.push(body)
      current = { ...current, ...body }
    }
    await route.fulfill({ json: current })
  })
  return { bodies }
}

async function seriousViolations(page: Page) {
  const results = await new AxeBuilder({ page }).analyze()
  return results.violations
    .filter((v) => v.impact === "serious" || v.impact === "critical")
    .map((v) => ({ id: v.id, nodes: v.nodes.map((n) => n.target.join(" ")).slice(0, 5) }))
}

test.describe("ตัวเลือกขั้นสูง: ช่วงเวลา", () => {
  test("พับไว้ตอนแรก · ตั้ง 1:30-5:00 แล้วทุกแท็บเห็นค่าเดียวกัน ป้ายปุ่มและป้าย 'ใช้ตัวเลือกขั้นสูงอยู่' · ส่งช่วงไปกับงาน", async ({ page }) => {
    const { bodies } = await mockEnqueue(page)
    await page.goto(`/v/${THAI}?tab=video`)
    await expect(button(page, "โหลด mp4")).toBeEnabled()
    await expect(button(page, ADVANCED)).toHaveAttribute("aria-expanded", "false")
    await expect(page.getByText(ACTIVE)).toHaveCount(0)
    await setRange(page, "1:30", "5:00")
    await expect(panel(page).getByText(ACTIVE)).toBeVisible()
    await expect(panel(page).getByText("ตัดตรงจุดที่ตั้งเป๊ะ ใช้เวลาแปลงไฟล์เพิ่ม")).toBeVisible()
    await button(page, "โหลด mp4 (1:30-5:00)").click()
    await expect.poll(() => bodies.length).toBe(1)
    expect((bodies[0][0].params as VideoJobParams).range).toEqual({ startMs: 90_000, endMs: 300_000 })

    await tab(page, "เสียง").click()
    await expect(panel(page).getByText(ACTIVE)).toBeVisible()
    await button(page, "โหลด m4a (1:30-5:00)").click()
    await expect.poll(() => bodies.length).toBe(2)
    expect((bodies[1][0].params as AudioJobParams).range).toEqual({ startMs: 90_000, endMs: 300_000 })

    await tab(page, "ซับ").click()
    await expect(page.getByRole("heading", { name: "ตัวอย่าง 5 ซับแรก (1:30-5:00)" })).toBeVisible()
    await button(page, "โหลด .srt (1:30-5:00)").click()
    await expect.poll(() => bodies.length).toBe(3)
    expect((bodies[2][0].params as SubtitleJobParams).range).toEqual({ startMs: 90_000, endMs: 300_000 })
    await expect(button(page, "โหลด .txt (1:30-5:00)")).toBeVisible()
  })

  test("ช่องผิดรูปแบบ / เริ่มไม่ก่อนจบ / เกินความยาวคลิป: ปุ่มยังกดได้ error ใต้ช่อง ไม่สร้างงาน (AC-ADV-02)", async ({ page }) => {
    const { bodies } = await mockEnqueue(page)
    await page.goto(`/v/${THAI}?tab=video`)
    await setRange(page, "5:00", "1:30")
    const start = field(page, "เริ่ม")
    await expect(panel(page).getByText("จุดเริ่มต้องมาก่อนจุดจบ")).toBeVisible()
    await expect(start).toHaveAttribute("aria-invalid", "true")
    await expect(start).toHaveAccessibleDescription("จุดเริ่มต้องมาก่อนจุดจบ")
    await button(page, "โหลด mp4").click()
    await setRange(page, "1:3x", "")
    await expect(panel(page).getByText("พิมพ์เวลาแบบ 1:30 หรือ 1:02:30")).toBeVisible()
    await setRange(page, "", "9:00")
    await expect(panel(page).getByText("เกินความยาวคลิป (6:12)")).toBeVisible()
    await button(page, "โหลด mp4").click()
    await expect(field(page, "จบ")).toBeFocused()
    await page.waitForTimeout(300)
    expect(bodies).toHaveLength(0)
  })

  test("เปิดคลิปอื่น = ค่าเริ่มใหม่ (D3)", async ({ page }) => {
    await page.goto(`/v/${THAI}?tab=video`)
    await setRange(page, "1:30", "5:00")
    await page.goto(`/v/${BBB}?tab=video`)
    await expect(button(page, "โหลด mp4")).toBeVisible()
    await expect(page.getByText(ACTIVE)).toHaveCount(0)
    await openAdvanced(page)
    await expect(field(page, "เริ่ม")).toHaveValue("")
  })

  test("คลิปที่ไม่รู้ความยาว: ช่องเวลากดไม่ได้พร้อมเหตุผล", async ({ page }) => {
    await page.route(
      (url) => url.pathname === `/api/videos/${BBB}`,
      async (route) => {
        const response = await route.fetch()
        await route.fulfill({ response, json: { ...((await response.json()) as object), durationS: 0 } })
      },
    )
    await page.goto(`/v/${BBB}?tab=video`)
    await openAdvanced(page)
    await expect(field(page, "เริ่ม")).toBeDisabled()
    await expect(panel(page).getByText("คลิปสดหรือคลิปที่ไม่รู้ความยาว ตั้งช่วงเวลาไม่ได้")).toBeVisible()
  })

  test("ขนาดประมาณย่อตามช่วง", async ({ page }) => {
    await page.goto(`/v/${BBB}?tab=video`)
    const estimate = panel(page).getByText(/^ขนาดประมาณ /)
    const before = await estimate.textContent()
    await setRange(page, "0:00", "1:00")
    await expect(estimate).not.toHaveText(before ?? "")
  })
})

test.describe("ตัวเลือกขั้นสูง: แยกไฟล์ตาม chapter", () => {
  test("มีเฉพาะคลิปที่มี >= 2 chapter และไม่อยู่ในแท็บซับ", async ({ page }) => {
    await page.goto(`/v/${BBB}?tab=video`)
    await openAdvanced(page)
    await expect(page.getByRole("switch", { name: CHAPTERS })).toHaveCount(0)
    await page.goto(`/v/${ZOO}?tab=audio`)
    await openAdvanced(page)
    await expect(page.getByRole("switch", { name: CHAPTERS })).toBeVisible()
    await tab(page, "ซับ").click()
    await expect(button(page, ADVANCED)).toBeVisible()
    await expect(page.getByRole("switch", { name: CHAPTERS })).toHaveCount(0)
  })

  test("เปิดแล้ว: ป้ายปุ่ม ช่องเวลา/ตัดโฆษณา/ฝังซับกดไม่ได้ · ส่ง splitChapters อย่างเดียว", async ({ page }) => {
    const { bodies } = await mockEnqueue(page)
    await page.goto(`/v/${ZOO}?tab=video`)
    await openAdvanced(page)
    await page.getByRole("switch", { name: CHAPTERS }).click()
    await expect(panel(page).getByText("ได้ไฟล์ละ 1 chapter ในโฟลเดอร์ย่อย · ขอบแต่ละ chapter อาจคลาด 1-3 วินาที")).toBeVisible()
    await expect(field(page, "เริ่ม")).toBeDisabled()
    await expect(page.getByRole("switch", { name: ADS })).toBeDisabled()
    await expect(page.getByRole("combobox", { name: "ฝังซับ (เปิด/ปิดได้)", exact: true })).toBeDisabled()
    await expect(panel(page).getByText("ปิด 'แยกไฟล์ตาม chapter' ก่อน").first()).toBeVisible()
    await button(page, "โหลด mp4 (แยก chapter)").click()
    await expect.poll(() => bodies.length).toBe(1)
    const params = bodies[0][0].params as VideoJobParams
    expect(params.splitChapters).toBe(true)
    expect(params).not.toHaveProperty("range")
    expect(params).not.toHaveProperty("sponsorblock")
    expect(params).not.toHaveProperty("embedSubs")
  })

  test("ตั้งช่วงไว้ก่อน = สวิตช์แยก chapter กดไม่ได้พร้อมเหตุผล", async ({ page }) => {
    await page.goto(`/v/${ZOO}?tab=video`)
    await setRange(page, "0:05", "")
    await expect(page.getByRole("switch", { name: CHAPTERS })).toBeDisabled()
    await expect(page.getByRole("switch", { name: CHAPTERS })).toHaveAccessibleDescription("ใช้คู่กับช่วงเวลาไม่ได้ ล้างช่วงเวลาก่อน")
  })
})

test.describe("ตัวเลือกขั้นสูง: ตัดโฆษณา", () => {
  test("เริ่มปิด · เปิดแล้วเห็น 3 หมวดเริ่มต้น · ติ๊กแล้วบันทึกลงการตั้งค่า · หมวดสุดท้ายเอาออกไม่ได้ · ส่งหมวดไปกับงาน", async ({ page }) => {
    const { bodies } = await mockEnqueue(page)
    const settings = await mockSettings(page)
    await page.goto(`/v/${BBB}?tab=video`)
    await openAdvanced(page)
    const sponsor = page.getByRole("switch", { name: ADS })
    await expect(sponsor).not.toBeChecked()
    await sponsor.click()
    await expect(button(page, "โหลด mp4 (ตัดโฆษณา)")).toBeVisible()
    for (const name of ["ช่วงสปอนเซอร์", "ช่วงโปรโมตตัวเอง", "ช่วงขอให้กดติดตามหรือไลก์"]) {
      await expect(page.getByRole("checkbox", { name })).toBeChecked()
    }
    await expect(page.getByRole("checkbox", { name: "ช่วงนอกเรื่อง" })).not.toBeChecked()
    await page.getByRole("checkbox", { name: "ช่วงสปอนเซอร์" }).click()
    await expect.poll(() => settings.bodies.at(-1)).toEqual({ sponsorblockDefault: ["selfpromo", "interaction"] })
    await page.getByRole("checkbox", { name: "ช่วงโปรโมตตัวเอง" }).click()
    await expect(page.getByRole("checkbox", { name: "ช่วงขอให้กดติดตามหรือไลก์" })).toBeDisabled()
    await setRange(page, "1:30", "5:00")
    await button(page, "โหลด mp4 (1:30-5:00, ตัดโฆษณา)").click()
    await expect.poll(() => bodies.length).toBe(1)
    expect((bodies[0][0].params as VideoJobParams).sponsorblock).toEqual(["interaction"])
  })

  test("ฝังซับอยู่ = เตือนใต้สวิตช์ในแท็บวิดีโอ · แท็บซับเตือนเหนือปุ่ม", async ({ page }) => {
    await page.goto(`/v/${THAI}?tab=video`)
    const embed = page.getByRole("combobox", { name: "ฝังซับ (เปิด/ปิดได้)", exact: true })
    await expect(embed).toBeEnabled()
    await embed.click()
    await page.getByRole("option").nth(1).click()
    await openAdvanced(page)
    await page.getByRole("switch", { name: ADS }).click()
    await expect(panel(page).getByText("เวลาซับจะไม่ตรงกับวิดีโอที่ตัดโฆษณาแล้ว")).toBeVisible()
    await tab(page, "ซับ").click()
    await expect(panel(page).getByText("เวลาซับจะไม่ตรงกับวิดีโอที่ตัดโฆษณาแล้ว")).toBeVisible()
  })
})

test.describe("ตัวเลือกขั้นสูง: การเข้าถึงและจอแคบ", () => {
  for (const scheme of ["dark", "light"] as const) {
    test(`ส่วนตัวเลือกที่กางพร้อม error ไม่มีปัญหาระดับ serious/critical (${scheme})`, async ({ page }) => {
      await page.emulateMedia({ colorScheme: scheme })
      await page.goto(`/v/${ZOO}?tab=video`)
      await setRange(page, "0:10", "0:05")
      await expect(panel(page).getByText("จุดเริ่มต้องมาก่อนจุดจบ")).toBeVisible()
      expect(await seriousViolations(page)).toEqual([])
      await page.goto(`/v/${BBB}?tab=audio`)
      await openAdvanced(page)
      await page.getByRole("switch", { name: ADS }).click()
      expect(await seriousViolations(page)).toEqual([])
    })
  }

  test("จอ 640 × 800: ทั้งสามแท็บไม่ล้นแนวนอนตอนกางส่วนตัวเลือก", async ({ page }) => {
    await page.setViewportSize({ width: 640, height: 800 })
    for (const which of ["video", "audio", "subs"] as const) {
      await page.goto(`/v/${ZOO}?tab=${which}`)
      await openAdvanced(page)
      if (which !== "subs") await page.getByRole("switch", { name: ADS }).click()
      expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(640)
    }
  })
})
```

- [ ] **Step 10: Extend `web/e2e/download-tabs.spec.ts`** (M4 follow-up items 1 and 3) — append:
```ts
test.describe("W2 กับค่าตั้ง (M4 follow-up)", () => {
  /** ตอบ GET /api/settings ด้วยค่าตั้งของ backend ที่แก้บางช่อง (ไม่แก้การตั้งค่าจริง) delayMs = ตอบช้า */
  async function withSettings(page: Page, patch: Record<string, unknown>, delayMs = 0) {
    await page.route("**/api/settings", async (route) => {
      if (route.request().method() !== "GET") return route.fallback()
      const response = await route.fetch()
      if (delayMs) await new Promise((resolve) => setTimeout(resolve, delayMs))
      await route.fulfill({ response, json: { ...((await response.json()) as object), ...patch } })
    })
  }

  for (const [videoDefault, maxHeight] of [["compat-1080", undefined], ["compat-720", 720], ["max", undefined]] as const) {
    test(`ค่าตั้ง ${videoDefault}: ส่ง maxHeight ${maxHeight ?? "(ไม่ส่ง)"}`, async ({ page }) => {
      const { bodies } = await mockEnqueue(page)
      await withSettings(page, { videoDefault })
      await openTab(page, BBB, "video")
      await downloadMp4(page).click()
      await expect.poll(() => bodies.length).toBe(1)
      const params = bodies[0][0].params as VideoJobParams
      if (maxHeight === undefined) expect(params).not.toHaveProperty("maxHeight")
      else expect(params.maxHeight).toBe(maxHeight)
    })
  }

  test("ปุ่มโหลดรอจนค่าตั้งมาถึง แล้วจึงใช้เพดานของค่าตั้ง", async ({ page }) => {
    const { bodies } = await mockEnqueue(page)
    await withSettings(page, { videoDefault: "compat-720" }, 1500)
    await page.goto(`/v/${BBB}?tab=video`)
    await expect(downloadMp4(page)).toBeDisabled()
    await expect(downloadMp4(page)).toBeEnabled({ timeout: 5000 })
    await downloadMp4(page).click()
    await expect.poll(() => bodies.length).toBe(1)
    expect((bodies[0][0].params as VideoJobParams).maxHeight).toBe(720)
  })
})
```
(Note: the "รอจน" test uses `page.goto` directly because `openTab` waits for the button to be visible only; `toBeDisabled` works on the focusable-when-disabled button because Base UI sets `aria-disabled`/`disabled`.)

- [ ] **Step 11: Run the web checks, expect PASS** — `cd web && npm run typecheck && npm run lint && npm test`. (Playwright runs at the gates.)

- [ ] **Step 12: Commit**
```bash
git add web/src/pages/video/advanced web/src/pages/video/download/video-panel.tsx web/src/pages/video/download/audio-panel.tsx web/src/pages/video/subs-panel.tsx web/src/pages/video/subs/export-buttons.tsx web/src/pages/video/subs/preview.tsx web/e2e/advanced-options.spec.ts web/e2e/download-tabs.spec.ts
git commit -F- <<'EOF'
feat(w2): advanced options section (range, chapter split, SponsorBlock) in video/audio/subs tabs

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
EOF
```

### Task 11: "ตั้งจุดเริ่ม / ตั้งจุดจบ" under the player, in the docked player and in the frame menu

**Files:**
- Create: `web/src/pages/video/player/range-mark-buttons.tsx`
- Modify: `web/src/pages/video/player/player-slot.tsx` (`PlayerFrame` passes `videoId` to `DockToolbar`; `DockToolbar` and `ControlsRow` render the buttons)
- Modify: `web/src/pages/video/frames.tsx` (two context-menu items)
- Create: `web/e2e/range-marks.spec.ts`

**Interfaces:**
- Consumes: C9 `advancedActions.mark`, `getPlayerState`, C8 strings (`setStart`, `setEnd`, `startSet`, `endSet`, `frameStart`, `frameEnd`, `blocked.chapters`), `formatDuration`.
- Produces: `markRange(videoId, which, ms): void` (toast + store), `RangeMarkButtons({ videoId, size?, className? })`.

- [ ] **Step 1: Create `web/src/pages/video/player/range-mark-buttons.tsx`**
```tsx
import { cn } from "cn"
import { ChevronFirst, ChevronLast } from "lucide-react"
import { toast } from "sonner"

import { Button } from "@/components/ui/button"
import { fill, th } from "@/i18n/th"
import { formatDuration } from "@/lib/format"

import { advancedActions } from "../advanced/advanced-store"
import { getPlayerState } from "./player-store"

const t = th.advanced

/**
 * ตั้งจุดเริ่ม/จบของช่วงเวลา (ค่าเดียวกับช่องในแท็บวิดีโอ เสียง ซับ D7) แล้วแจ้งด้วย toast
 * แยกไฟล์ตาม chapter เปิดอยู่ = แจ้งเหตุผล ไม่เปลี่ยนค่า · เวลาปัดลงเป็นวินาที
 */
export function markRange(videoId: string, which: "start" | "end", ms: number): void {
  if (advancedActions.mark(videoId, which, ms) === "blocked") {
    toast.error(t.blocked.chapters)
    return
  }
  const time = formatDuration(Math.floor(Math.max(0, ms) / 1000))
  toast.success(fill(which === "start" ? t.startSet : t.endSet, { time }))
}

type Props = { videoId: string; size?: "sm" | "xs"; className?: string }

/** ปุ่ม "ตั้งจุดเริ่ม" / "ตั้งจุดจบ" ใต้ตัวเล่นและบนตัวเล่นลอย: ใช้เวลาที่ตัวเล่นอยู่ตอนนี้ */
export function RangeMarkButtons({ videoId, size = "sm", className }: Props) {
  const mark = (which: "start" | "end") => markRange(videoId, which, getPlayerState().currentMs)
  return (
    <div data-slot="range-marks" className={cn("flex flex-wrap items-center gap-1", className)}>
      <Button variant="outline" size={size} onClick={() => mark("start")}>
        <ChevronFirst aria-hidden />
        {t.setStart}
      </Button>
      <Button variant="outline" size={size} onClick={() => mark("end")}>
        <ChevronLast aria-hidden />
        {t.setEnd}
      </Button>
    </div>
  )
}
```

- [ ] **Step 2: Wire the player** — in `player-slot.tsx`: import `RangeMarkButtons` from `./range-mark-buttons`; in `PlayerFrame` change `{docked && <DockToolbar boxRef={boxRef} onClose={onClose} />}` to `{docked && <DockToolbar videoId={videoId} boxRef={boxRef} onClose={onClose} />}`; `DockToolbar` takes `videoId: string` and renders `<RangeMarkButtons videoId={videoId} size="xs" />` right after `<ReelStatus … />`; `ControlsRow` renders `<RangeMarkButtons videoId={video.videoId} />` right after its `<ReelStatus … />`. Update the `ControlsRow`/`PlayerControls` doc comment: "แถวใต้ตัวเล่นในหัวคลิป: แถบไทม์ไลน์ + "ช่วง i จาก n" + ปุ่มตั้งจุดเริ่ม/จบ (M5 รอบ A)", and the `DockToolbar` comment likewise.

- [ ] **Step 3: Add the frame-menu items** — in `frames.tsx` import `ChevronFirst, ChevronLast` (add to the lucide import) and `markRange` from `./player/range-mark-buttons`; in the `ContextMenuContent` of the frame, right after the "เล่นจากตรงนี้" item:
```tsx
        <ContextMenuItem onClick={() => markRange(videoId, "start", frame.tMs)}>
          <ChevronFirst aria-hidden />
          {th.advanced.frameStart}
        </ContextMenuItem>
        <ContextMenuItem onClick={() => markRange(videoId, "end", frame.tMs)}>
          <ChevronLast aria-hidden />
          {th.advanced.frameEnd}
        </ContextMenuItem>
```

- [ ] **Step 4: Write the chromium e2e spec** — `web/e2e/range-marks.spec.ts`:
```ts
import { expect, test, type Page } from "@playwright/test"

import { installFakeYT } from "./fake-yt"

/**
 * M5 รอบ A (D7): "ตั้งจุดเริ่ม/ตั้งจุดจบ" ใต้ตัวเล่น บนตัวเล่นลอย ในเมนูคลิกขวาของภาพเฟรม และปุ่ม "ใช้เวลาที่ตัวเล่นอยู่ตอนนี้"
 * ตัวเล่นปลอม (installFakeYT) เวลาเดินช้ามาก (rate 0.001) เวลาที่ตั้งจึงคงที่ ไม่ต่อยูทูปจริง ไม่สร้างงาน
 */

const THAI = "88o5Sk8_m1Y" // 372 วิ มีภาพเฟรม

const button = (page: Page, name: string) => page.getByRole("button", { name, exact: true })
const toast = (page: Page, text: string) => page.locator("[data-sonner-toast]").filter({ hasText: text })
const timeField = (page: Page, name: "เริ่ม" | "จบ") => page.getByRole("tabpanel").getByRole("textbox", { name, exact: true })

/** "00:00:20" (timecode ของภาพเฟรม) -> "0:20" (เวลาแบบที่ช่องและ toast ใช้) */
function clock(timecode: string): string {
  const [h, m, s] = timecode.split(":").map(Number)
  return h > 0 ? `${h}:${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}` : `${m}:${String(s).padStart(2, "0")}`
}

async function thirdFrame(page: Page) {
  const image = page.getByRole("img", { name: /^ภาพเฟรมที่ / }).nth(2)
  await expect(image).toBeVisible()
  const alt = (await image.getAttribute("alt")) ?? ""
  return { image, time: clock(alt.replace("ภาพเฟรมที่ ", "")) }
}

test("เมนูภาพเฟรม 'ตั้งเป็นจุดเริ่ม' ตั้งค่าในช่อง เปิดส่วนตัวเลือก และแจ้ง toast", async ({ page }) => {
  await page.goto(`/v/${THAI}`)
  const { image, time } = await thirdFrame(page)
  await image.click({ button: "right" })
  await page.getByRole("menuitem", { name: "ตั้งเป็นจุดเริ่ม" }).click()
  await expect(toast(page, `ตั้งจุดเริ่มที่ ${time} แล้ว`)).toBeVisible()
  await page.getByRole("tab", { name: "วิดีโอ", exact: true }).click()
  await expect(button(page, "ตัวเลือกขั้นสูง")).toHaveAttribute("aria-expanded", "true")
  await expect(timeField(page, "เริ่ม")).toHaveValue(time)
  await expect(page.getByRole("tabpanel").getByText("ใช้ตัวเลือกขั้นสูงอยู่")).toBeVisible()
})

test("ปุ่มใต้ตัวเล่นมีหลังเริ่มเล่นเท่านั้น · ตั้งจุดเริ่ม/จบจากเวลาตัวเล่น · ปุ่มข้างช่องใช้เวลาเดียวกัน", async ({ page }) => {
  await installFakeYT(page, { durationS: 372, rate: 0.001 })
  await page.goto(`/v/${THAI}?tab=video`)
  await expect(button(page, "ตั้งจุดเริ่ม")).toHaveCount(0)
  await button(page, "ตัวเลือกขั้นสูง").click()
  const startGroup = page.getByRole("group", { name: "เริ่ม" })
  await expect(startGroup.getByRole("button", { name: "ใช้เวลาที่ตัวเล่นอยู่ตอนนี้" })).toBeDisabled()

  await button(page, "เล่นคลิป").click()
  await expect(button(page, "ตั้งจุดเริ่ม")).toBeVisible()
  await button(page, "ตั้งจุดเริ่ม").click()
  await expect(toast(page, "ตั้งจุดเริ่มที่ 0:00 แล้ว")).toBeVisible()
  await expect(timeField(page, "เริ่ม")).toHaveValue("0:00")

  await page.getByRole("tab", { name: "ภาพเฟรม", exact: true }).click()
  const { image, time } = await thirdFrame(page)
  await image.click({ button: "right" })
  await page.getByRole("menuitem", { name: "เล่นจากตรงนี้" }).click()
  await button(page, "ตั้งจุดจบ").click()
  await expect(toast(page, `ตั้งจุดจบที่ ${time} แล้ว`)).toBeVisible()
  await page.getByRole("tab", { name: "วิดีโอ", exact: true }).click()
  await expect(timeField(page, "จบ")).toHaveValue(time)
  await expect(button(page, `โหลด mp4 (0:00-${time})`)).toBeVisible()
  await timeField(page, "เริ่ม").fill("")
  await page.getByRole("group", { name: "เริ่ม" }).getByRole("button", { name: "ใช้เวลาที่ตัวเล่นอยู่ตอนนี้" }).click()
  await expect(timeField(page, "เริ่ม")).toHaveValue(time)
  // เริ่ม = จบ ใช้ไม่ได้: ป้ายปุ่มไม่มีช่วง และมี error ใต้ช่องเริ่ม
  await expect(button(page, "โหลด mp4")).toBeVisible()
  await expect(page.getByRole("tabpanel").getByText("จุดเริ่มต้องมาก่อนจุดจบ")).toBeVisible()
})

test("ตัวเล่นลอยมีปุ่มตั้งจุดด้วย", async ({ page }) => {
  await installFakeYT(page, { durationS: 372, rate: 0.001 })
  await page.goto(`/v/${THAI}`)
  await button(page, "เล่นคลิป").click()
  await expect(button(page, "ตั้งจุดเริ่ม")).toBeVisible()
  await page.mouse.wheel(0, 4000)
  const dock = page.getByRole("region", { name: "ตัวเล่นคลิป (ลอย)" })
  await expect(dock).toBeVisible()
  await expect(dock.getByRole("button", { name: "ตั้งจุดเริ่ม", exact: true })).toBeVisible()
  await expect(dock.getByRole("button", { name: "ตั้งจุดจบ", exact: true })).toBeVisible()
})
```

- [ ] **Step 5: Run the web checks, expect PASS** — `cd web && npm run typecheck && npm run lint && npm test`.

- [ ] **Step 6: Commit**
```bash
git add web/src/pages/video/player/range-mark-buttons.tsx web/src/pages/video/player/player-slot.tsx web/src/pages/video/frames.tsx web/e2e/range-marks.spec.ts
git commit -F- <<'EOF'
feat(w2): set start/end from the player, the docked player and the frame menu

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
EOF
```

### Task 12: Queue rows: job choice text and the new stages

**Files:**
- Modify: `web/src/lib/types.ts` (`JobStage` only)
- Modify: `web/src/components/queue/job-text.ts`, `web/src/components/queue/job-text.test.ts`

**Interfaces:**
- Consumes: C8 (`th.queue.splitting`, `th.queue.choice`, new `stages` keys), C9 `rangeText`.
- Produces: C10 exactly.

- [ ] **Step 1: Write the failing tests** — append to `web/src/components/queue/job-text.test.ts` (add `jobChoice, stageText` to the `./job-text` import and `import { PRESETS } from "@/lib/sub-options"`):
```ts
describe("M5-A: ชื่องานต่อท้ายตัวเลือก (spec 3.5) และขั้นตอนใหม่", () => {
  it("ช่วงเวลา · แยก chapter · ตัดโฆษณา", () => {
    const range = { startMs: 90_000, endMs: 300_000 }
    expect(
      jobTitle(job({ params: { maxQuality: false, splitChapters: false, noAudio: false, audioLanguage: "original", range, sponsorblock: ["sponsor"] } })),
    ).toBe("คลิปทดสอบ · ช่วง 1:30-5:00 · ตัดโฆษณา")
    expect(jobTitle(job({ kind: "audio", params: { format: "m4a", splitChapters: true, audioLanguage: "original" } }))).toBe(
      "คลิปทดสอบ · แยก chapter",
    )
    expect(
      jobTitle(job({ kind: "subtitle", params: { trackId: "a.th-orig", format: "srt", options: PRESETS.medium, range: { startMs: 3_750_000, endMs: 3_900_000 } } })),
    ).toBe("คลิปทดสอบ · ช่วง 1:02:30-1:05:00")
    expect(jobChoice({ source: "fast" })).toBe("")
    expect(jobTitle({ title: "", videoId: "aqz-KE-bpKQ" })).toBe("aqz-KE-bpKQ")
  })

  it("ขั้นตอนตัดช่วง ตัดโฆษณา แยก chapter", () => {
    expect(stageText("cutting")).toBe("กำลังตัดช่วง")
    expect(stageText("cutting_ads")).toBe("กำลังตัดโฆษณา")
    expect(stageText("splitting:3/12")).toBe("กำลังแยก chapter 3/12")
    expect(stageText("writing")).toBe("บันทึกไฟล์")
    expect(progressLine(job({ stage: "splitting:2/5", progress: 0.5 }))).toBe("กำลังแยก chapter 2/5 · 50%")
  })
})
```

- [ ] **Step 2: Run, expect FAIL** — `cd web && npx vitest run src/components/queue/job-text.test.ts`.

- [ ] **Step 3: Implement** — `web/src/lib/types.ts`:
```ts
export type JobStage =
  | "probing"
  | "downloading_video"
  | "downloading_audio"
  | "merging"
  | "converting"
  | "writing"
  | "cutting"
  | "cutting_ads"
  | `splitting:${number}/${number}`
```
`web/src/components/queue/job-text.ts` — imports become `import { rangeText } from "@/lib/advanced-options"` and `import type { Job, JobParams, JobStage } from "@/lib/types"`; replace `jobTitle` and add:
```ts
const SPLIT = /^splitting:(\d+)\/(\d+)$/
type FixedStage = keyof typeof th.queue.stages

/** ข้อความของขั้นตอน: "splitting:3/12" = "กำลังแยก chapter 3/12" (M5 รอบ A) ที่เหลือตามตาราง th.queue.stages */
export function stageText(stage: JobStage): string {
  const split = SPLIT.exec(stage)
  if (split) return fill(th.queue.splitting, { i: split[1], n: split[2] })
  return th.queue.stages[stage as FixedStage]
}

/** ตัวเลือกขั้นสูงของงาน ต่อท้ายชื่องาน (spec 3.5): " · ช่วง 1:30-5:00", " · แยก chapter", " · ตัดโฆษณา" */
export function jobChoice(params: JobParams): string {
  let text = ""
  if ("range" in params && params.range) text += fill(th.queue.choice.range, { range: rangeText(params.range) })
  if ("splitChapters" in params && params.splitChapters) text += th.queue.choice.chapters
  if ("sponsorblock" in params && params.sponsorblock && params.sponsorblock.length > 0) text += th.queue.choice.ads
  return text
}

/** ชื่อที่แสดงของงาน: ชื่อคลิป (ยังไม่รู้ชื่อ = รหัสคลิป) + ตัวเลือกขั้นสูงของงาน */
export const jobTitle = (job: Pick<Job, "title" | "videoId"> & { params?: JobParams }): string =>
  (job.title || job.videoId) + (job.params ? jobChoice(job.params) : "")
```
In `progressLine` replace `th.queue.stages[job.stage]` with `stageText(job.stage)`.

- [ ] **Step 4: Run, expect PASS** — `cd web && npm run typecheck && npm run lint && npm test` (the queue components keep calling `jobTitle(job)` with full jobs; no other change).

- [ ] **Step 5: Commit**
```bash
git add web/src/lib/types.ts web/src/components/queue/job-text.ts web/src/components/queue/job-text.test.ts
git commit -F- <<'EOF'
feat(queue): job titles show range/chapter/ads choices; cut and split stages

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
EOF
```

---

## Wave 3

### Task 13: Chapter split (video fast, audio exact) and the SponsorBlock wiring

**Files:**
- Modify: `src/yttoolkit/core/handlers.py`
- Modify: `tests/unit/test_handlers.py`
- Modify: `src/yttoolkit/lifecycle.py` (`open_services`: `HandlerDeps(..., sponsors=extractor)`)
- Modify: `tests/unit/test_lifecycle.py`

**Interfaces:**
- Consumes: T8 (`_requested_range`, `_sponsor_segments`, `_duration_ms`, `_cut`, `CUT_DISK_FACTOR`, `HandlerDeps.sponsors`), C1 `split_stage`, C2 (`chapter_parts`, `ChapterPart`, `files.plan_chapter_output`), C3 (`mode="fast"`, `MediaMeta.track`).
- Produces: the rest of C6 (chapter outputs, `NO_CHAPTERS`, `splitting:i/n`), and the real/fake SponsorBlock source wired into the running app.

- [ ] **Step 1: Write the failing tests** — append to `tests/unit/test_handlers.py`:
```python
# ---------- M5 รอบ A: แยกไฟล์ตาม chapter ----------

ZOO_TITLE = "Me at the zoo"
ZOO_NAMES = ["01 - Intro", "02 - The cool thing", "03 - End"]


def test_video_chapter_split(env):
    result, ctx = env.run("video", ZOO, video_params(splitChapters=True))
    assert [c.intervals for c in env.media.cuts] == [((0, 5_000),), ((5_000, 17_000),), ((17_000, 19_000),)]
    assert {(c.mode, c.target, c.has_audio) for c in env.media.cuts} == {("fast", "mp4", True)}
    assert [s for s in ctx.stages if s.startswith("splitting")] == ["splitting:1/3", "splitting:2/3", "splitting:3/3"]
    clip_folder = env.planned(ZOO, ZOO_TITLE, "", "mp4").parent
    paths = [Path(o.root) / o.rel for o in result.outputs]
    assert [p.name for p in paths] == [f"{n}.mp4" for n in ZOO_NAMES]
    assert {p.parent for p in paths} == {clip_folder / "แยกตาม chapter (mp4)"}
    assert all(p.is_file() for p in paths) and {o.kind for o in result.outputs} == {"video"}
    assert (clip_folder / files.SOURCE_NOTE_NAME).is_file()
    metas = [kwargs["meta"] for name, kwargs in env.media.calls if name == "finalize_mp4"]
    assert [(m.title, m.track, m.duration_s) for m in metas] == [
        ("Intro", "1/3", 5.0), ("The cool thing", "2/3", 12.0), ("End", "3/3", 2.0)]
    assert result.notes == ()


@pytest.mark.parametrize(
    ("fmt", "target", "method"),
    [("m4a", "m4a", "finalize_m4a"), ("mp3", "wav", "to_mp3"), ("wav", "wav", "to_wav")],
)
def test_audio_chapter_split_is_exact(env, fmt, target, method):
    result, _ = env.run("audio", ZOO, audio_params(fmt, splitChapters=True))
    assert [(c.mode, c.target) for c in env.media.cuts] == [("exact", target)] * 3
    assert [Path(o.rel).name for o in result.outputs] == [f"{n}.{fmt}" for n in ZOO_NAMES]
    assert {Path(o.rel).parent.name for o in result.outputs} == {f"แยกตาม chapter ({fmt})"}
    assert [name for name, _ in env.media.calls] == [method] * 3


def test_chapter_split_on_a_clip_without_chapters_gives_the_full_file(env):
    result, ctx = env.run("video", BBB, video_params(splitChapters=True))
    assert env.media.cuts == [] and not any(s.startswith("splitting") for s in ctx.stages)
    assert output_path(result) == env.planned(BBB, BBB_TITLE, "", "mp4")
    assert result.notes == ("NO_CHAPTERS",)


def test_second_chapter_split_gets_numbered_copies(env):
    env.run("video", ZOO, video_params(splitChapters=True))
    again, _ = env.run("video", ZOO, video_params(splitChapters=True))
    assert Path(again.outputs[0].rel).name == "01 - Intro (2).mp4"


def test_cancel_during_the_chapter_split_leaves_nothing(env):
    with pytest.raises(JobCancelled):
        env.run("video", ZOO, video_params(splitChapters=True), cancel_on="splitting:2/3")
    assert folders(env.out) == []
```
Append to `tests/unit/test_lifecycle.py`:
```python
def test_open_services_gives_the_handlers_the_sponsorblock_source(paths, fake_platform, monkeypatch):
    captured = {}
    real = lifecycle.build_handlers

    def spy(deps):
        captured["deps"] = deps
        return real(deps)

    monkeypatch.setattr(lifecycle, "build_handlers", spy)
    services = lifecycle.open_services(paths, fake_platform, fake=True)
    try:
        assert captured["deps"].sponsors is services.extractor
    finally:
        services.db.close()
```

- [ ] **Step 2: Run, expect FAIL** — `uv run pytest tests/unit/test_handlers.py tests/unit/test_lifecycle.py -q -W error -p no:cacheprovider` (`splitChapters` is ignored: one full file; `sponsors` is `None`).

- [ ] **Step 3: Implement in `core/handlers.py`** — extend imports: `ChapterPart, chapter_parts` from `.advanced`, `split_stage` from `.jobs`. Add after `_cut`:
```python
def _ignore_progress(_fraction: float | None) -> None:
    """ขั้นจัดไฟล์ของแต่ละ chapter สั้นมาก แถบคิวแสดงเฉพาะความคืบหน้าของการตัด"""


def _chapters(clip: _Clip, result: DownloadResult) -> list[ChapterPart]:
    """chapter ของคลิป (VideoInfo จาก cache) ปลายสุดท้ายไม่เกินความยาวจริงของไฟล์ที่โหลด ไม่ถึง 2 = []"""
    total = _duration_ms(result.info, clip)
    return chapter_parts(clip.info.get("chapters") or [], total) if total else []


def _split(
    deps: HandlerDeps,
    ctx: JobContext,
    clip: _Clip,
    result: DownloadResult,
    report: _Reporter,
    parts: list[ChapterPart],
    *,
    ext: str,
    target: CutTarget,
    mode: CutMode,
    has_audio: bool,
    finalize: Callable[[Path, Path, MediaMeta], None],
) -> list[tuple[Path, ChapterPart]]:
    """ไฟล์ละ chapter ใน workdir ตามลำดับ (D2/D6): ตัดช่วงของ chapter แล้วจัดไฟล์ (ปก ชื่อ chapter ลำดับ n/total)
    ไฟล์ทั้งหมดย้ายเข้าที่พร้อมกันตอนจบ (ยกเลิกกลางทาง = ไม่มีไฟล์ไหนเข้าโฟลเดอร์ผลลัพธ์)"""
    workdir = Path(ctx.workdir)
    made: list[tuple[Path, ChapterPart]] = []
    for part in parts:
        ctx.check_cancelled()
        report.stage(split_stage(part.index, part.total))
        cut = workdir / f"part-{part.index:03d}.cut.{target}"
        deps.media.cut(result.path, cut, [(part.start_ms, part.end_ms)], mode=mode, target=target,
                       has_audio=has_audio, cancel=ctx.cancelled, on_progress=report.fraction)  # fmt: skip
        out = workdir / f"part-{part.index:03d}.{ext}"
        meta = replace(
            clip.meta,
            title=part.title or f"chapter {part.index}",
            duration_s=(part.end_ms - part.start_ms) / 1000,
            track=f"{part.index}/{part.total}",
        )
        finalize(cut, out, meta)
        cut.unlink(missing_ok=True)
        made.append((out, part))
    result.path.unlink(missing_ok=True)
    return made


def _finish_chapters(
    deps: HandlerDeps,
    ctx: JobContext,
    clip: _Clip,
    made: list[tuple[Path, ChapterPart]],
    *,
    ext: str,
    kind: str,
    notes: Iterable[str],
) -> JobResult:
    """ย้ายไฟล์ของทุก chapter เข้า "<โฟลเดอร์ของคลิป>/แยกตาม chapter (<ext>)/" ตามลำดับ (D4) แล้วเขียน
    แหล่งที่มา.txt ที่โฟลเดอร์ของคลิป ผลของงาน = ทุกไฟล์ตามลำดับ chapter"""
    ctx.check_cancelled()
    outputs: list[OutputFile] = []
    for path, part in made:
        planned = files.plan_chapter_output(
            clip.root, clip.title, clip.video_id, ext, clip.group,
            index=part.index, total=part.total, chapter_title=part.title,
        )  # fmt: skip
        final = files.move_into_place(path, planned)
        rel = final.relative_to(clip.root).as_posix()
        log.info("งาน %s บันทึกไฟล์ %s", ctx.job_id, rel)
        outputs.append(OutputFile(root=str(clip.root), rel=rel, size_bytes=final.stat().st_size, kind=kind))
    clip_folder = files.plan_output(clip.root, clip.title, clip.video_id, "", ext, clip.group).parent
    _write_note(deps, ctx, clip, clip_folder)
    return JobResult(outputs=tuple(outputs), notes=_unique(notes), title=clip.title or None)
```
(add `CutMode` to the `.media` import.)

In `_video`: compute `split = bool(params.get("splitChapters"))` next to `span`; the disk factor becomes `CUT_DISK_FACTOR if split or span is not None or ads is not None else DISK_FACTOR`; right after `no_audio = …` insert:
```python
    split_notes: tuple[str, ...] = ()
    if split:
        parts = _chapters(clip, result)
        if parts:
            cover = _cover(deps, clip, ctx)

            def finalize(src: Path, dst: Path, meta: MediaMeta) -> None:
                deps.media.finalize_mp4(
                    src, dst, meta, cover=cover, subtitle=None, audio_language=result.choice.audio_language,
                    cancel=ctx.cancelled, on_progress=_ignore_progress, no_audio=no_audio,
                )  # fmt: skip

            made = _split(deps, ctx, clip, result, report, parts, ext="mp4", target="mp4", mode="fast",
                          has_audio=not no_audio, finalize=finalize)  # fmt: skip
            report.stage("writing")
            return _finish_chapters(deps, ctx, clip, made, ext="mp4", kind="video", notes=(*result.choice.notes, *sub_notes))
        split_notes = ("NO_CHAPTERS",)
```
and the final notes become `(*result.choice.notes, *sub_notes, *ad_notes, *cut.notes, *split_notes)`.

In `_audio`: same `split` and disk factor; right after the download and `ctx.check_cancelled()` insert:
```python
    split_notes: tuple[str, ...] = ()
    if split:
        parts = _chapters(clip, result)
        if parts:
            cover = None if fmt == "wav" else _cover(deps, clip, ctx)
            kbps = int(params.get("mp3Kbps") or DEFAULT_MP3_KBPS)
            language = result.choice.audio_language

            def finalize(src: Path, dst: Path, meta: MediaMeta) -> None:
                common: dict[str, Any] = {"audio_language": language, "cancel": ctx.cancelled, "on_progress": _ignore_progress}
                if fmt == "wav":
                    deps.media.to_wav(src, dst, meta, **common)
                elif fmt == "mp3":
                    deps.media.to_mp3(src, dst, meta, kbps=kbps, cover=cover, **common)
                else:
                    deps.media.finalize_m4a(src, dst, meta, cover=cover, **common)

            made = _split(deps, ctx, clip, result, report, parts, ext=fmt, target="m4a" if fmt == "m4a" else "wav",
                          mode="exact", has_audio=True, finalize=finalize)  # fmt: skip
            report.stage("writing")
            return _finish_chapters(deps, ctx, clip, made, ext=fmt, kind="audio", notes=result.choice.notes)
        split_notes = ("NO_CHAPTERS",)
```
and its final notes become `(*result.choice.notes, *ad_notes, *cut.notes, *split_notes)`. Update `build_handlers`' docstring: `ตัวทำงานของทุกชนิดงานใน M4 + ตัวเลือกขั้นสูงของ M5 รอบ A (frames_sharp เป็นงานรอบ B ยังไม่มี)`.

`lifecycle.py`, in `open_services`, add to the `HandlerDeps(...)` call:
```python
            sponsors=extractor,  # type: ignore[arg-type]  # ทั้งตัวจริงและตัวปลอมมี sponsor_segments (C4)
```

- [ ] **Step 4: Run, expect PASS; run the full suite** — `uv run pytest tests/unit/test_handlers.py tests/unit/test_lifecycle.py -q -W error -p no:cacheprovider`, then `uv run pytest -q -W error -p no:cacheprovider`.

- [ ] **Step 5: Commit**
```bash
git add src/yttoolkit/core/handlers.py tests/unit/test_handlers.py src/yttoolkit/lifecycle.py tests/unit/test_lifecycle.py
git commit -F- <<'EOF'
feat(handlers): split by chapter into a sub-folder (video fast, audio exact); wire SponsorBlock

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
EOF
```

### Task 14: Queue e2e with the real fake backend

**Files:**
- Create: `web/e2e/queue-advanced.spec.ts`

**Interfaces:**
- Consumes: C4 fake clips (`RANGECLIP01`, `ADSCUTCLIP1`, `ADSNODATA01`, `ADSOFFLINE1`, `CHAPTERS001`), `enqueue`, `waitForJob`, `openQueueSheet` (`web/e2e/queue-helpers.ts`), C8 queue strings, C1 notes.
- Produces: the `queue`-project proof of C6 in fake mode (runs at the final gate, after T13 is merged).

- [ ] **Step 1: Write the spec** — `web/e2e/queue-advanced.spec.ts`:
```ts
import { expect, test, type APIRequestContext } from "@playwright/test"

import type { Job, NewJob } from "../src/lib/types"

import { enqueue, openQueueSheet, waitForJob } from "./queue-helpers"

/**
 * M5 รอบ A กับ backend โหมด fake ตัวจริง (โปรเจกต์ queue): งานจริงของคลิปปลอมใน tests/fixtures/downloads/behaviors.json
 * ตรวจเฉพาะงานของคลิปตัวเอง (ไม่นับยอดรวมของแถบคิว) · โหมด fake ตัดด้วยการคัดลอก: ตรวจชื่อไฟล์ จำนวนไฟล์ และโน้ต
 */

const VIDEO = { maxQuality: false, splitChapters: false, noAudio: false, audioLanguage: "original" }

async function done(request: APIRequestContext, item: NewJob): Promise<Job> {
  const [job] = await enqueue(request, [item])
  return waitForJob(request, (j) => j.id === job.id && j.status === "done", { timeout: 30_000 })
}

const names = (job: Job) => (job.outputs ?? []).map((output) => output.name)

test("ช่วงเวลา: ชื่อไฟล์มี (01.30-05.00) · แถวคิวต่อท้าย ' · ช่วง 1:30-5:00'", async ({ page, request }) => {
  const job = await done(request, {
    videoId: "RANGECLIP01",
    kind: "video",
    params: { ...VIDEO, range: { startMs: 90_000, endMs: 300_000 } },
  })
  expect(names(job)).toEqual(["คลิปช่วงเวลา (01.30-05.00).mp4"])
  await page.goto("/")
  const sheet = await openQueueSheet(page)
  await expect(sheet.locator(`[data-job-id="${job.id}"]`)).toContainText("คลิปช่วงเวลา · ช่วง 1:30-5:00")
})

test("แยก chapter (เสียง m4a): 3 ไฟล์ตามลำดับ และปุ่มดาวน์โหลดครบทุกไฟล์", async ({ page, request }) => {
  const job = await done(request, {
    videoId: "CHAPTERS001",
    kind: "audio",
    params: { format: "m4a", splitChapters: true, audioLanguage: "original" },
  })
  expect(names(job)).toEqual(["01 - Intro.m4a", "02 - The cool thing.m4a", "03 - End.m4a"])
  await page.goto("/")
  const row = (await openQueueSheet(page)).locator(`[data-job-id="${job.id}"]`)
  await expect(row).toContainText("คลิปมี 3 chapter · แยก chapter")
  await expect(row.getByRole("link", { name: /^ดาวน์โหลด / })).toHaveCount(3)
})

test("แยก chapter (วิดีโอ): ชื่อไฟล์ 01-03", async ({ request }) => {
  const job = await done(request, { videoId: "CHAPTERS001", kind: "video", params: { ...VIDEO, splitChapters: true } })
  expect(names(job)).toEqual(["01 - Intro.mp4", "02 - The cool thing.mp4", "03 - End.mp4"])
})

test("ตัดโฆษณาที่มีข้อมูล: ชื่อมี (ตัดโฆษณา) ไม่มีโน้ต", async ({ request }) => {
  const job = await done(request, { videoId: "ADSCUTCLIP1", kind: "video", params: { ...VIDEO, sponsorblock: ["sponsor"] } })
  expect(names(job)).toEqual(["คลิปมีช่วงโฆษณา (ตัดโฆษณา).mp4"])
  expect(job.notes ?? []).toEqual([])
})

test("ไม่มีข้อมูลจากชุมชน: ได้คลิปเต็ม ชื่อปกติ และโน้ตสีเทาในแถวคิว", async ({ page, request }) => {
  const job = await done(request, { videoId: "ADSNODATA01", kind: "video", params: { ...VIDEO, sponsorblock: ["sponsor"] } })
  expect(names(job)).toEqual(["คลิปไม่มีข้อมูลโฆษณา.mp4"])
  expect(job.notes).toEqual([{ code: "SPONSORBLOCK_EMPTY", message: "ไม่มีข้อมูลจากชุมชน ได้คลิปเต็ม" }])
  await page.goto("/")
  const row = (await openQueueSheet(page)).locator(`[data-job-id="${job.id}"]`)
  await expect(row).toContainText("ไม่มีข้อมูลจากชุมชน ได้คลิปเต็ม")
  await expect(row).toContainText("คลิปไม่มีข้อมูลโฆษณา · ตัดโฆษณา")
})

test("ติดต่อ SponsorBlock ไม่ได้: งานสำเร็จ ได้คลิปเต็ม พร้อมโน้ต", async ({ request }) => {
  const job = await done(request, { videoId: "ADSOFFLINE1", kind: "audio", params: { format: "m4a", splitChapters: false, audioLanguage: "original", sponsorblock: ["sponsor"] } })
  expect(names(job)).toEqual(["คลิปที่ติดต่อ SponsorBlock ไม่ได้.m4a"])
  expect(job.notes).toEqual([{ code: "SPONSORBLOCK_UNREACHABLE", message: "ติดต่อ SponsorBlock ไม่ได้ ได้คลิปเต็ม" }])
})
```

- [ ] **Step 2: Typecheck and lint** — `cd web && npm run typecheck && npm run lint` (the spec runs at the final gate with `npm run e2e`).

- [ ] **Step 3: Commit**
```bash
git add web/e2e/queue-advanced.spec.ts
git commit -F- <<'EOF'
test(e2e): queue jobs with range, chapter split and SponsorBlock in fake mode

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
EOF
```

### Task 15: Docs (PRD, BRD, acceptance, follow-ups) and network tests (written, not run)

**Files:**
- Modify: `PRD.md`, `BRD.md`, `docs/acceptance.md`, `docs/m4-followups.md`
- Modify: `tests/network_videos.toml`
- Create: `tests/network/test_advanced_network.py`

**Interfaces:**
- Consumes: everything above (final names, strings, notes, behaviour).
- Produces: docs that match the code; a network test that Pete can approve and run.

- [ ] **Step 1: PRD.md** — make these exact edits (find each anchor with `rg -n` first):
  1. Line starting `- **"ตัวเลือกขั้นสูง"** เป็น Collapsible` — replace the sentence `· **M4 ยังไม่แสดงส่วนนี้เลย** เพราะของข้างในทุกอย่างเป็นงาน M5 (กฎ BRD #53: แสดงเมื่อมีตัวเลือกที่ใช้ได้จริง · BRD #94)` with: `· **M5 รอบ A เปิดใช้แล้ว:** ช่วงเวลา (ช่อง "เริ่ม"/"จบ" รับ ss, m:ss, mm:ss, h:mm:ss และปุ่ม "ใช้เวลาที่ตัวเล่นอยู่ตอนนี้"), "แยกไฟล์ตาม chapter" (แท็บวิดีโอ/เสียง เฉพาะคลิปที่มี ≥ 2 chapter), "ตัดโฆษณา (SponsorBlock)" (แท็บวิดีโอ/เสียง) · ค่าเป็นของคลิปที่เปิดอยู่ (เปิดคลิปอื่นหรือโหลดหน้าใหม่ = เริ่มใหม่) จำข้ามคลิปเฉพาะหมวด SponsorBlock (`sponsorblockDefault`) · แยก chapter ใช้คู่กับช่วงเวลา ตัดโฆษณา และฝังซับไม่ได้ (ตัวที่เปิดก่อนชนะ อีกตัวกดไม่ได้พร้อมเหตุผล) · ปุ่มโหลดบอกตัวเลือก เช่น "โหลด mp4 (1:30-5:00, ตัดโฆษณา)" · ช่องเวลาผิด = ข้อความสีแดงใต้ช่อง ไม่สร้างงาน (AC-ADV-02) · สเปก `docs/superpowers/specs/2026-10-02-m5a-advanced-download-options-design.md`` (keep the backticks around the path only).
  2. Replace the whole line starting `- **"ตัวเลือกขั้นสูง" ในแท็บซับ (BRD #53):**` with: `- **"ตัวเลือกขั้นสูง" ในแท็บซับ (BRD #53, M5 รอบ A):** มีช่วงเวลาอย่างเดียว · ตัวอย่างซับ ("ตัวอย่าง 5 ซับแรก (1:30-5:00)") "คัดลอกข้อความ" และไฟล์ .srt/.txt เป็นของช่วงนั้น นับเวลาใหม่จาก 00:00 (AC-SUB-10) · เปิดตัดโฆษณาไว้ = ข้อความเตือน "เวลาซับจะไม่ตรงกับวิดีโอที่ตัดโฆษณาแล้ว" เหนือปุ่มโหลด`
  3. After the line starting `- **ไม่อยู่ใน M3.5:**` add: `- **M5 รอบ A:** หลังเริ่มเล่น ใต้ตัวเล่น (และบนตัวเล่นลอย) มีปุ่ม "ตั้งจุดเริ่ม" / "ตั้งจุดจบ" ใช้เวลาที่ตัวเล่นอยู่ (ปัดลงเป็นวินาที) แจ้ง "ตั้งจุดเริ่มที่ {เวลา} แล้ว" และกาง "ตัวเลือกขั้นสูง" ให้ (BRD #81, D7)`
  4. Replace the line starting `- "ตั้งจุดเริ่ม/จบ" มาใน M5 · "ดูซับช่วงนี้"` with: `- เมนูคลิกขวาของภาพเฟรมมี "ตั้งเป็นจุดเริ่ม" / "ตั้งเป็นจุดจบ" ตั้งแต่ M5 รอบ A (ใช้เวลาของภาพ ค่าเดียวกับช่องในตัวเลือกขั้นสูง พร้อม toast) · "ดูซับช่วงนี้" มาแล้วใน M3 เป็นรายการที่ 5 (ดู "สิ่งที่ M3 ทำจริง" ด้านบน)`
  5. In the W2 component table, replace the row starting `| **ตัวเลือกขั้นสูง** (พับไว้ · **M4 ยังซ่อน**)` with: `| **ตัวเลือกขั้นสูง** (พับไว้ · M5 รอบ A) | Collapsible · ช่อง "เริ่ม"/"จบ" + ปุ่มไอคอน "ใช้เวลาที่ตัวเล่นอยู่ตอนนี้" · Switch "แยกไฟล์ตาม chapter" (ซ่อนถ้าไม่ถึง 2 chapter ไม่มีในแท็บซับ) · Switch "ตัดโฆษณา (SponsorBlock)" + Checkbox 8 หมวด (แท็บวิดีโอ/เสียง) · (M5 รอบ C) Checkbox "ใช้คุกกี้กับคลิปนี้" (แสดงเฉพาะเมื่อเปิดคุกกี้ไว้ FR-CK-7) | ค่าในส่วนนี้มีผลกับปุ่มโหลดวิดีโอ เสียง และซับทั้งหมด · เมื่อใช้อยู่ ให้แสดง Badge "ใช้ตัวเลือกขั้นสูงอยู่" ข้างหัวข้อในทุกแท็บ (เห็นได้แม้พับอยู่) |`
  6. Replace the row starting `| เปิด SponsorBlock พร้อมโหลดซับ |` with: `| เปิดตัดโฆษณาพร้อมฝังซับ (แท็บวิดีโอ) หรือโหลดซับ (แท็บซับ) | ข้อความเตือนใต้สวิตช์ (วิดีโอ) / เหนือปุ่มโหลด (ซับ) | "เวลาซับจะไม่ตรงกับวิดีโอที่ตัดโฆษณาแล้ว" | — |`
  7. Replace the `AC-ADV-03` row with: `| AC-ADV-03 | แยก chapter ในคลิปที่มี 5 chapter → ได้ 5 ไฟล์ ชื่อ `01 - <ชื่อ>.mp4` ถึง `05 - <ชื่อ>.mp4` ในโฟลเดอร์ย่อย `แยกตาม chapter (mp4)` ของโฟลเดอร์คลิป · เสียงแยกได้เช่นกัน (`แยกตาม chapter (m4a|mp3|wav)` ตัดตรงเวลา) · วิดีโอตัดตาม keyframe ขอบคลาดได้ 1-3 วิ (D6) | N |`
  8. In the job-params table: `video` row — replace `splitChapters: false` with `splitChapters: bool` and `(M5 เพิ่ม `range?`, `sponsorblock?`, `splitChapters: true`)` with `range?: {startMs, endMs}` (มิลลิวินาที เต็มวินาที ยาว ≥ 1 วิ) · `sponsorblock?: string[]` (หมวดของ SponsorBlock ไม่ซ้ำ ไม่ว่าง) (M5 รอบ A) · `splitChapters: true` ใช้คู่กับ `range` / `sponsorblock` / `embedSubs` ไม่ได้ (422)`; `audio` row likewise (`splitChapters: bool`, `range?`, `sponsorblock?` M5 รอบ A, and append to its notes cell: `· ช่วงเวลา/ตัดโฆษณา: m4a ช่วงเดียวตัดแบบคัดลอกสตรีม หลายช่วงเข้ารหัส AAC ใหม่ · mp3/wav ตัดเป็น PCM ก่อนแปลง`); `subtitle` row — replace `(M5 เพิ่ม `range?`` with `(M5 รอบ A: `range?` ใช้กับ srt/txt เท่านั้น md + range = 422`.
  9. Replace the strictness bullet starting `- **M4 ตรวจ params เข้ม**` with: `- **ตรวจ params เข้ม** (`POST /jobs` ปฏิเสธ key ที่ไม่รู้จักทุกตัว → 422 `E_BAD_REQUEST`): `useCookies` (M5 รอบ C) และ `kind: "frames_sharp"` / `source: "sharp"` (M5 รอบ B) ยังถูกปฏิเสธ · `range` ต้องเป็นจำนวนเต็มคูณ 1000, `0 ≤ startMs`, ยาว ≥ 1000 · `sponsorblock` ไม่ว่าง ไม่ซ้ำ อยู่ใน 8 หมวด · `splitChapters: true` คู่กับ `range`/`sponsorblock`/`embedSubs` → 422 (AC-VID-10 ส่วนที่ 2) · ถ้ามีข้อมูลคลิปใน cache: ช่วงเกินความยาวคลิป (+0.5 วิ) คลิปสด/ไม่รู้ความยาว หรือแยก chapter ในคลิปที่มีไม่ถึง 2 chapter → 422 (ไม่มี cache = ตัวทำงานตรวจอีกรอบ) · `embedSubs` ไม่มี `subOptions` → 422 · `subOptions` / `options` ต้องผ่านกติกาของ `srt_builder` · `formatId` ต้องเป็น `[A-Za-z0-9_-]{1,32}` · `embedSubs` ต้องเป็น track id รูปแบบ `o.`/`a.`/`t.` + ชื่อ · mp3 ไม่ส่ง `mp3Kbps` = 192 · params ที่เก็บคือค่าที่ตรวจแล้ว`
  10. Replace the three bullets `- **โหลดเฉพาะช่วง:** …`, `- **แยก chapter:** …`, `- **SponsorBlock:** …` with:
```markdown
- **ตัวเลือกขั้นสูง (M5 รอบ A, แนวทาง B D9):** โหลดทั้งคลิปแบบ M4 แล้วโปรแกรมตัดเองด้วย ffmpeg (`core/media.cut`) ไม่ใช้ `download_ranges` / `FFmpegSplitChapters` / `sponsorblock_remove` ของ yt-dlp · ช่วงที่เก็บไว้ (keep intervals) คิดบนเส้นเวลาต้นฉบับ: ช่วงเวลา = `[[start, end]]` · ตัดโฆษณา = คลิป (หรือช่วง) ลบช่วงโฆษณาที่รวมกันแล้ว ชิ้นที่เหลือสั้นกว่า 1 วิทิ้ง · แยก chapter = ช่วงละ chapter ไฟล์ละช่วง
- **ตัดแบบแม่นยำ (ช่วงเวลา/ตัดโฆษณา D1):** แต่ละช่วงเป็น input ของตัวเอง (`-ss` ก่อน `-i`) ต่อด้วย `concat` เข้ารหัสใหม่ H.264 (`libx264 -preset veryfast -crf 20`) + AAC 192k ภาพแรกตรงเฟรมที่ตั้ง (AC-ADV-01) · เสียง m4a ช่วงเดียวคัดลอกสตรีม (คลาดไม่เกิน ~23 ms) หลายช่วงเข้ารหัส AAC ใหม่ · mp3/wav ตัดเป็น PCM แล้วแปลงครั้งเดียว · แล้วจึงทำขั้นเดิมของ M4 (ปก ข้อมูลไฟล์ ฝังซับ) กับไฟล์ที่ตัด ฝังซับพร้อมช่วงเวลาใช้ซับของช่วงนั้น (AC-VID-10 ส่วนที่ 1)
- **แยก chapter (D2/D4/D6):** วิดีโอตัดแบบคัดลอกสตรีมตาม keyframe (ขอบคลาด 1-3 วิ ไม่ต้องเข้ารหัสทั้งคลิปใหม่) เสียงตัดตรงเวลา · ไฟล์ `<NN> - <ชื่อ chapter>.<นามสกุล>` ในโฟลเดอร์ย่อย `แยกตาม chapter (<นามสกุล>)` (NN 2 หลัก 3 หลักเมื่อมี ≥ 100 chapter ชื่อว่าง = `chapter <n>`) ข้อมูลไฟล์ `title` = ชื่อ chapter `track` = n/ทั้งหมด · ผลของงานคือทุกไฟล์ตามลำดับ · คลิปที่พบว่ามีไม่ถึง 2 chapter = ได้ไฟล์เต็มพร้อมหมายเหตุ `NO_CHAPTERS`
- **SponsorBlock:** ดึงผ่าน `SponsorBlockPP` ของ yt-dlp ใน `core/extractor.py` (ส่งแค่ hash 4 ตัวแรกของ video id ไม่ส่งข้อมูลผู้ใช้ ไม่ใช้เซสชันผู้ชม) · ไม่มีข้อมูลของหมวดที่เลือก (หรือไม่มีช่วงไหนอยู่ในช่วงเวลาที่ตั้ง) = ได้คลิปเต็ม ชื่อไฟล์ปกติ ไม่เข้ารหัสใหม่ หมายเหตุ `SPONSORBLOCK_EMPTY` · ติดต่อไม่ได้ = งานยังสำเร็จ หมายเหตุ `SPONSORBLOCK_UNREACHABLE` ไม่ลองใหม่ ไม่พักคิว
- **ชื่อไฟล์ (M5 รอบ A):** ลำดับส่วนต่อท้าย ไม่มีเสียง → ช่วงเวลา → ตัดโฆษณา เช่น `<ชื่อ> (ไม่มีเสียง) (01.30-05.00) (ตัดโฆษณา).mp4` (ใช้ `.` แทน `:` · ถึงชั่วโมง = `(1.02.30-1.05.00)`) · ซับ `<ชื่อ> (01.30-05.00).<lang>.srt|txt` · ส่วนต่อท้ายที่ยาวเกิน 30 ตัวตัดจากชื่อไฟล์ ไม่แตะชื่อโฟลเดอร์ของคลิป · ขั้นตอนในแถวคิว "กำลังตัดช่วง" / "กำลังตัดโฆษณา" / "กำลังแยก chapter i/n" · ชื่องานในคิวต่อท้าย " · ช่วง 1:30-5:00" / " · แยก chapter" / " · ตัดโฆษณา"
```
  11. In the bullet starting `- **หมายเหตุของงาน:**`, after the `QUALITY_FALLBACK` entry add: `, `SPONSORBLOCK_EMPTY` ("ไม่มีข้อมูลจากชุมชน ได้คลิปเต็ม"), `SPONSORBLOCK_UNREACHABLE` ("ติดต่อ SponsorBlock ไม่ได้ ได้คลิปเต็ม"), `NO_CHAPTERS` ("คลิปนี้ไม่มี chapter ได้ไฟล์เต็ม") (M5 รอบ A)`.
  12. In the bullet starting `- **ตรวจพื้นที่ก่อนโหลด:**` append: ` · งานที่ตัดช่วง ตัดโฆษณา หรือแยก chapter ใช้ 3 เท่า (ไฟล์ที่โหลด + ไฟล์ที่ตัด + ไฟล์ที่จัดเสร็จ) และลบไฟล์ที่โหลดทันทีที่ตัดเสร็จ (M5 รอบ A)`.
  13. Traceability row `| FR-ADV-1..4 |` — change its screens cell to `W2 (ตัวเลือกขั้นสูง ตัวเล่น เมนูภาพเฟรม), W4 (แถวคิว), W7 (toast)`.

- [ ] **Step 2: BRD.md** — replace the four FR-ADV rows with:
```markdown
| FR-ADV-1 | **โหลดเฉพาะช่วง** กรอกเวลาเริ่มและจบได้ทั้ง `ss`, `m:ss`, `mm:ss` และ `h:mm:ss` หรือตั้งจากตัวเล่น (ปุ่ม "ตั้งจุดเริ่ม/ตั้งจุดจบ" ใต้ตัวเล่นและข้างช่อง) และจากเมนูคลิกขวาของภาพเฟรม ใช้ได้ทั้งวิดีโอ เสียง และซับ · ตัดตรงเฟรม (วิดีโอเข้ารหัสใหม่) |
| FR-ADV-2 | **แยกไฟล์ตาม chapter** แสดงเฉพาะคลิปที่มี ≥ 2 chapter ใช้ได้ทั้งวิดีโอและเสียง ได้ไฟล์ละ chapter ตั้งชื่อว่า `01 - <ชื่อ chapter>.mp4` ในโฟลเดอร์ย่อย `แยกตาม chapter (mp4)` (เสียง `(m4a|mp3|wav)`) · วิดีโอตัดเร็วตาม keyframe ขอบคลาดได้ 1-3 วินาที เสียงตัดตรงเวลา |
| FR-ADV-3 | **SponsorBlock** ปิดไว้ทุกคลิป เปิดแล้วตัดช่วงตามหมวดที่ติ๊ก ค่าเริ่มต้น `sponsor`, `selfpromo`, `interaction` เลือกหมวดเพิ่มได้ 8 หมวด หมวดที่ติ๊กจำข้ามคลิป ถ้าคลิปไม่มีข้อมูลให้แจ้งว่า "ไม่มีข้อมูลจากชุมชน ได้คลิปเต็ม" ติดต่อไม่ได้แจ้งว่า "ติดต่อ SponsorBlock ไม่ได้ ได้คลิปเต็ม" |
| FR-ADV-4 | ถ้าเปิด SponsorBlock คู่กับการฝังซับหรือการโหลดซับ ให้เตือนว่า "เวลาซับจะไม่ตรงกับวิดีโอที่ตัดโฆษณาแล้ว" (จะแก้ใน v2) |
```
Then add these rows after decision `| 116 |` (same 4-column format):
```markdown
| 117 | **ช่วงเวลาตัดตรงเฟรมเสมอ** (วิดีโอเข้ารหัสใหม่ H.264) รอนานขึ้นได้ · M5 รอบ A (D1) | ✅ | ตัดช่วงไปโพสต์หรือนำเสนอ ถ้าจุดเริ่มคลาดไป 2-5 วินาทีใช้งานไม่ได้ · พิธอนุมัติ 2026-10-02 |
| 118 | **แยกไฟล์ตาม chapter ได้ทั้งวิดีโอและเสียง** · M5 รอบ A (D2) | ✅ | สัมมนา 2 ชั่วโมงแยกเป็น mp3 หัวข้อละไฟล์ฟังในรถได้ · พิธอนุมัติ 2026-10-02 |
| 119 | **ตัวเลือกขั้นสูงเป็นของคลิปที่เปิดอยู่** (เปิดคลิปอื่นหรือโหลดหน้าใหม่ = เริ่มใหม่) จำข้ามคลิปเฉพาะหมวด SponsorBlock สวิตช์ตัดโฆษณาเริ่มปิดทุกคลิป · M5 รอบ A (D3) | ✅ | ช่วงของคลิปหนึ่งต้องไม่ติดไปคลิปอื่นโดยไม่ตั้งใจ ตัดโฆษณาทำให้ไฟล์สั้นลงจึงต้องเลือกเองทุกครั้ง · พิธอนุมัติ 2026-10-02 |
| 120 | **ไฟล์แยก chapter อยู่ในโฟลเดอร์ย่อย** `แยกตาม chapter (mp4)` / `(mp3)` ของโฟลเดอร์คลิป · M5 รอบ A (D4) | ✅ | สัมมนามีได้ 20-30 chapter ต้องไม่ปนกับไฟล์เต็ม ซับ และโน้ต ชื่อโฟลเดอร์มีนามสกุลกันชื่อ `01 - …` ชนกันเมื่อแยกทั้งวิดีโอและเสียง · พิธอนุมัติ 2026-10-02 |
| 121 | **SponsorBlock อยู่ในรอบนี้ ปิดไว้ตอนเริ่ม** · M5 รอบ A (D5) | ✅ | มีใน yt-dlp อยู่แล้ว ต้นทุนต่ำ คลิปไทยส่วนใหญ่ไม่มีข้อมูล ผลจึงบอกชัดว่าได้คลิปเต็ม · พิธอนุมัติ 2026-10-02 |
| 122 | **แยก chapter ของวิดีโอตัดเร็ว** (ไม่เข้ารหัสใหม่ ขอบคลาด 1-3 วิ) เสียงตัดตรงเวลา · M5 รอบ A (D6) | ✅ | ตัดตรงเฟรมทั้งคลิป 2 ชั่วโมงใช้เวลา 30-60 นาทีขึ้นไปบนโน้ตบุ๊กทั่วไป ขอบ chapter ไม่ต้องตรงเฟรม · พิธอนุมัติ 2026-10-02 |
| 123 | **ปุ่ม "ตั้งจุดเริ่ม/ตั้งจุดจบ" มีทั้งใต้ตัวเล่นและข้างช่องเวลา** เมนูคลิกขวาของภาพเฟรมก็มี · M5 รอบ A (D7) | ✅ | ใต้ตัวเล่นกดได้ระหว่างดู ข้างช่องเห็นว่าค่าไหนเปลี่ยน · พิธอนุมัติ 2026-10-02 |
| 124 | **W3 ยังไม่มีตัวเลือกขั้นสูง** ในรอบ A · M5 รอบ A (D8) | ✅ | ช่วงเวลาและ chapter เป็นของคลิปเดียว ตัดโฆษณาใน W3 เพิ่มทีหลังได้ถ้ามีคนขอ · พิธอนุมัติ 2026-10-02 |
| 125 | **โหลดทั้งคลิปแล้วโปรแกรมตัดเองด้วย ffmpeg** (ไม่ใช้การโหลดเฉพาะช่วงของ yt-dlp) · M5 รอบ A (D9) | ✅ | เชื่อถือได้ ควบคุมและทดสอบเองได้ทั้งหมด แลกกับคลิปยาวต้องโหลดเต็มเสมอ · พิธอนุมัติ 2026-10-02 |
```

- [ ] **Step 3: docs/acceptance.md** — append after the M4 section:
```markdown
## M5 รอบ A (ทำบน Windows 10/11 กับยูทูปจริง)
| AC | ขั้นตอน | ผ่าน |
|---|---|---|
| M5A-RANGE | เปิดคลิปยาวกว่า 6 นาที แท็บ "วิดีโอ" กาง "ตัวเลือกขั้นสูง" พิมพ์ "เริ่ม" `1:30` "จบ" `5:00` ปุ่มต้องเป็น "โหลด mp4 (1:30-5:00)" และเห็น "ใช้ตัวเลือกขั้นสูงอยู่" · โหลดจนเสร็จ ไฟล์ชื่อ `<ชื่อคลิป> (01.30-05.00).mp4` ยาว 3:30 เปิดดูภาพแรกตรงกับวินาทีที่ 1:30 บนยูทูป (AC-ADV-01) · แท็บ "เสียง" ปุ่มเป็น "โหลด m4a (1:30-5:00)" ได้ไฟล์ยาว 3:30 | ☐ |
| M5A-ERRORS | พิมพ์ "เริ่ม" `5:00` "จบ" `1:30` แล้วกดโหลด: ไม่มีงานใหม่ในคิว ใต้ช่องขึ้น "จุดเริ่มต้องมาก่อนจุดจบ" สีแดง · พิมพ์ `1:3x` ขึ้น "พิมพ์เวลาแบบ 1:30 หรือ 1:02:30" · พิมพ์เวลาเกินความยาวคลิป ขึ้น "เกินความยาวคลิป (…)" (AC-ADV-02) | ☐ |
| M5A-MARKS | กดเล่นคลิป เลื่อนไปราว 1:30 กด "ตั้งจุดเริ่ม" ใต้ตัวเล่น ขึ้น "ตั้งจุดเริ่มที่ 1:30 แล้ว" · ไปแท็บภาพเฟรม คลิกขวาภาพหนึ่ง → "ตั้งเป็นจุดจบ" · ไปแท็บวิดีโอ ส่วนตัวเลือกกางอยู่และช่องมีค่าทั้งสอง · เลื่อนจอลงให้ตัวเล่นลอย ปุ่มทั้งสองอยู่บนตัวเล่นลอยด้วย | ☐ |
| M5A-RESET | ตั้งช่วงไว้แล้วเปิดคลิปอื่น ช่องต้องว่างและไม่มีป้าย "ใช้ตัวเลือกขั้นสูงอยู่" · กลับคลิปเดิม (ไม่โหลดหน้าใหม่) ค่าก็เริ่มใหม่เช่นกัน · หมวด SponsorBlock ที่ติ๊กไว้ยังเหมือนเดิมทุกคลิป | ☐ |
| M5A-CHAPTERS | เปิดคลิปที่มีหลาย chapter (เช่นสัมมนา) เปิด "แยกไฟล์ตาม chapter" ปุ่มเป็น "โหลด mp4 (แยก chapter)" ช่องเวลา ตัดโฆษณา และฝังซับกดไม่ได้พร้อม "ปิด 'แยกไฟล์ตาม chapter' ก่อน" · โหลดเสร็จ โฟลเดอร์คลิปมีโฟลเดอร์ย่อย `แยกตาม chapter (mp4)` ไฟล์ `01 - …` ครบเท่าจำนวน chapter ขอบแต่ละไฟล์คลาดไม่เกิน 3 วินาที (AC-ADV-03) · ทำซ้ำในแท็บเสียงแบบ mp3 ได้ `แยกตาม chapter (mp3)` เปิดในโปรแกรมเล่นเพลงเห็นชื่อ chapter และลำดับ | ☐ |
| M5A-ADS | คลิปที่มีข้อมูล SponsorBlock: เปิด "ตัดโฆษณา (SponsorBlock)" เห็นหมวดที่ติ๊กไว้ 3 หมวด ปุ่มเป็น "โหลด mp4 (ตัดโฆษณา)" · โหลดเสร็จ ไฟล์ `<ชื่อ> (ตัดโฆษณา).mp4` สั้นลงเท่าช่วงที่ตัด ± 1 วินาที (AC-ADV-04) · คลิปไทยที่ไม่มีข้อมูล: ได้คลิปเต็ม ชื่อปกติ แถวคิวมีหมายเหตุ "ไม่มีข้อมูลจากชุมชน ได้คลิปเต็ม" · ติ๊กหมวดเปลี่ยนแล้วเปิดคลิปอื่น หมวดที่ติ๊กยังอยู่ | ☐ |
| M5A-SUBS | แท็บซับ ตั้งช่วง `1:30`-`5:00` หัวตัวอย่างเป็น "ตัวอย่าง 5 ซับแรก (1:30-5:00)" ซับแรกเริ่มที่ 00:00 · กด "โหลด .srt (1:30-5:00)" ได้ไฟล์ `<ชื่อ> (01.30-05.00).th.srt` เปิดใน Notepad ซับสุดท้ายจบไม่เกิน 00:03:30 (AC-SUB-10) · "คัดลอกข้อความ" ได้เฉพาะข้อความในช่วง | ☐ |
| M5A-EMBED | แท็บวิดีโอ ตั้งช่วง 1:30-5:00 พร้อม "ฝังซับ" ไทย โหลดแล้วเปิดใน VLC ซับขึ้นตรงเสียงพูดตั้งแต่ต้นไฟล์ (AC-VID-10 ส่วนที่ 1) · เปิดตัดโฆษณาพร้อมฝังซับ ต้องเห็นข้อความ "เวลาซับจะไม่ตรงกับวิดีโอที่ตัดโฆษณาแล้ว" | ☐ |
| M5A-QUEUE | ระหว่างงานตัดทำงาน แถวคิวขึ้น "กำลังตัดช่วง" / "กำลังตัดโฆษณา" / "กำลังแยก chapter 2/12" พร้อม % · ชื่องานต่อท้าย " · ช่วง 1:30-5:00" / " · แยก chapter" / " · ตัดโฆษณา" · กดยกเลิกระหว่างตัด งานหยุดภายใน 3 วินาทีและไม่มีไฟล์ค้างในโฟลเดอร์ | ☐ |
| M5A-SWEEP | เริ่มงานแยก chapter ของคลิปยาว แล้วปิดโปรแกรมด้วย stop.bat ระหว่างที่ขึ้น "บันทึกไฟล์" · เปิดโปรแกรมใหม่ งานเป็น "หยุดกลางคัน" และไม่มีไฟล์ 0 ไบต์หรือ `.part` ค้างในโฟลเดอร์คลิปและ `แยกตาม chapter (…)` | ☐ |
| M5A-NARROW | ซูม 200% (หรือหน้าต่างกว้าง 640 px) กางตัวเลือกขั้นสูงทั้งสามแท็บ เปิดตัดโฆษณา ไม่มีแถบเลื่อนแนวนอน ช่องเริ่ม/จบเรียงลงได้ (BRD #83) | ☐ |
```

- [ ] **Step 4: docs/m4-followups.md** — append ` **(ทำแล้วใน M5 รอบ A: ปุ่มโหลดรอค่าตั้ง · ความสูงที่จำไว้เกินเพดานใช้ความสูงที่เพดาน · e2e ตรวจ maxHeight ทุกแบบ)**` to the end of the bullet starting `- **หน้า W2 กับค่าตั้ง:**`; append ` **(M5 รอบ A เพิ่มชื่อช่วงเวลา/ตัดโฆษณาและโฟลเดอร์ย่อย "แยกตาม chapter" แล้ว)**` to the bullet starting `- **กู้งานตอนเปิด:**`; and in "เลื่อนไป M5" append to the "ตัวเลือกขั้นสูงของ W2" bullet: ` · **รอบ A ทำแล้ว** (ช่วงเวลา แยก chapter ตัดโฆษณา) คุกกี้อยู่รอบ C`.

- [ ] **Step 5: tests/network_videos.toml** — append:
```toml
[advanced]
# M5 รอบ A (T15): คลิปของ tests/network/test_advanced_network.py · ตรวจ probe ซ้ำก่อนรันถ้าห่างหลายเดือน
range_clip = "88o5Sk8_m1Y"       # 372 วิ มี a.th-orig: ช่วง 01:30-05:00 (AC-ADV-01) และฝังซับตามช่วง (AC-VID-10 ส่วนที่ 1)
chapters_clip = "jNQXAC9IVRw"    # 19 วิ 3 chapter (AC-ADV-03 ใช้ 3 chapter: คลิปสั้นสุดที่มี chapter โหลดน้อย)
no_sponsor_clip = "kwmHaXUAa0M"  # 10 วิ ไม่มีข้อมูล SponsorBlock (กรณี "ไม่มีข้อมูลจากชุมชน")
sponsor_clip = ""                # พิธเลือกคลิปสั้นที่มีข้อมูล sponsor ก่อนรัน (ว่าง = ข้ามกรณีที่มีข้อมูลของ AC-ADV-04)
```

- [ ] **Step 6: Write the network test** — `tests/network/test_advanced_network.py`:
```python
"""M5 รอบ A กับยูทูปจริง: ช่วงเวลาตรงเฟรม (AC-ADV-01), แยก chapter (AC-ADV-03), SponsorBlock (AC-ADV-04),
ฝังซับตามช่วงเวลา (AC-VID-10 ส่วนที่ 1) ผ่าน handler ของคิว + yt-dlp จริง + ffmpeg จริง

ต้องได้รับอนุญาตจากพิธก่อนรัน: โหลดไฟล์จริงจากยูทูปประมาณ 60-120 MB (240p) ลง temp ลบทิ้งเมื่อทุกเทสผ่าน
รันเองด้วย: uv run pytest -m network -q tests/network/test_advanced_network.py -s
id ของคลิปอยู่ใน tests/network_videos.toml ([advanced]) · sponsor_clip ว่าง = ข้ามกรณีที่มีข้อมูลของ SponsorBlock
ยูทูปตอบ 429 หรือขอยืนยันว่าไม่ใช่บอท = เทสตก ให้รายงานผล ห้ามแก้เทสให้หลวมลง
"""

from __future__ import annotations

import re
import shutil
import subprocess
import time
import tomllib
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest
from helpers_ffmpeg import ffprobe_json, requires_ffmpeg

from yttoolkit.core.advanced import merge_intervals
from yttoolkit.core.db import Database
from yttoolkit.core.extractor import YtDlpExtractor, visitor_session, ytdlp_version
from yttoolkit.core.handlers import HandlerDeps, build_handlers
from yttoolkit.core.jobs import Job, JobResult
from yttoolkit.core.media import FfmpegTools
from yttoolkit.core.subtitles import SubtitleService
from yttoolkit.core.videos import VideoService

pytestmark = [pytest.mark.network, requires_ffmpeg]

_TOML = Path(__file__).resolve().parents[1] / "network_videos.toml"
CLIPS: dict[str, str] = tomllib.loads(_TOML.read_text(encoding="utf-8"))["advanced"]
SMALL = 240  # ไฟล์เล็ก โหลดเร็ว (เส้นทางเลือก format ยังเป็นของจริง)
QUEUE_GAP_S = 2
MEDIUM = {"maxChars": 25, "lines": 1, "minMs": 1200, "maxMs": 5000}
VIDEO = {"maxQuality": False, "maxHeight": SMALL, "splitChapters": False, "noAudio": False, "audioLanguage": "original"}
SRT_TIME = re.compile(r"(\d\d):(\d\d):(\d\d),(\d\d\d) --> (\d\d):(\d\d):(\d\d),(\d\d\d)")


class Ctx:
    """JobContext ขั้นต่ำสำหรับเรียก handler ตรง ๆ (ไม่ผ่านคิว)"""

    def __init__(self, workdir: Path, output_root: Path) -> None:
        self.job_id = "01900000-0000-7000-8000-0000000000ab"
        self.workdir = workdir
        self.output_root = output_root

    def stage(self, stage: str) -> None:
        return None

    def progress(self, fraction: float | None, speed_bps: int | None = None, eta_s: int | None = None) -> None:
        return None

    def set_title(self, title: str) -> None:
        return None

    def cancelled(self) -> bool:
        return False

    def check_cancelled(self) -> None:
        return None

    def wait(self, seconds: float) -> None:
        time.sleep(seconds)


def _job(kind: str, video_id: str, params: dict[str, Any]) -> Job:
    return Job(
        id="01900000-0000-7000-8000-0000000000ab", video_id=video_id, title="", kind=kind, params=params,
        status="running", stage=None, progress=None, speed_bps=None, eta_s=None, attempt=0, bot_checks=0,
        position=0, error_code=None, error_message=None, error_detail=None, notes=(), outputs=(),
        created_at="2026-10-02T00:00:00Z", started_at=None, finished_at=None,
    )  # fmt: skip


@dataclass
class Env:
    root: Path
    extractor: YtDlpExtractor
    videos: VideoService
    ffmpeg: str
    handlers: dict
    counter: int = 0
    last: float = 0.0

    def run(self, kind: str, video_id: str, params: dict[str, Any]) -> JobResult:
        wait = QUEUE_GAP_S - (time.monotonic() - self.last)
        if wait > 0:
            time.sleep(wait)
        self.last = time.monotonic()
        self.counter += 1
        workdir = self.root / "work" / str(self.counter)
        workdir.mkdir(parents=True)
        return self.handlers[kind](_job(kind, video_id, params), Ctx(workdir, self.root / "output"))


@pytest.fixture(scope="module")
def env(tmp_path_factory: pytest.TempPathFactory, request: pytest.FixtureRequest) -> Iterator[Env]:
    root = tmp_path_factory.mktemp("advanced-network")
    ffmpeg = shutil.which("ffmpeg")
    assert ffmpeg is not None
    ytdlp_version()
    db = Database(root / "app.db")
    db.migrate()
    session = visitor_session(root / "data")
    extractor = YtDlpExtractor(session=session)
    videos = VideoService(db, extractor)
    subs = SubtitleService(videos, extractor.fetch_subtitle, root / "cache", session=session)
    deps = HandlerDeps(
        videos=videos,
        downloader=extractor,  # type: ignore[arg-type]
        media=FfmpegTools(lambda: Path(ffmpeg)),
        subtitles=subs,
        cache_root=root / "cache",
        sponsors=extractor,
    )
    state = Env(root, extractor, videos, ffmpeg, build_handlers(deps))
    try:
        yield state
    finally:
        extractor.close()
        db.close()
        if request.session.testsfailed:
            print(f"[kept for inspection] {root}")
        else:
            shutil.rmtree(root, ignore_errors=True)


def _path(result: JobResult, index: int = 0) -> Path:
    out = result.outputs[index]
    return Path(out.root) / out.rel


def _duration(path: Path, kind: str) -> float:
    return float(next(s for s in ffprobe_json(path)["streams"] if s["codec_type"] == kind)["duration"])


def _gray(ffmpeg: str, path: Path, at_s: float | None) -> bytes:
    seek = ["-ss", f"{at_s:.3f}"] if at_s is not None else []
    return subprocess.run(
        [ffmpeg, "-hide_banner", "-loglevel", "error", *seek, "-i", str(path), "-frames:v", "1",
         "-vf", "scale=160:90", "-f", "rawvideo", "-pix_fmt", "gray", "-"],
        check=True, capture_output=True,
    ).stdout  # fmt: skip


def _diff(a: bytes, b: bytes) -> float:
    return sum(abs(x - y) for x, y in zip(a, b, strict=True)) / len(a)


def test_ac_adv_01_range_is_frame_exact(env: Env) -> None:
    clip = CLIPS["range_clip"]
    full = env.run("video", clip, dict(VIDEO))
    cut = env.run("video", clip, {**VIDEO, "range": {"startMs": 90_000, "endMs": 300_000}})
    path = _path(cut)
    assert path.name.endswith(" (01.30-05.00).mp4")
    assert abs(_duration(path, "video") - 210.0) <= 0.5
    first = _gray(env.ffmpeg, path, None)
    reference = _path(full)
    at = _diff(first, _gray(env.ffmpeg, reference, 90.0))
    around = min(_diff(first, _gray(env.ffmpeg, reference, 89.0)), _diff(first, _gray(env.ffmpeg, reference, 91.0)))
    assert at < 4.0 and at <= around + 1.0


def test_ac_adv_03_chapter_split_video_and_mp3(env: Env) -> None:
    clip = CLIPS["chapters_clip"]
    chapters = env.videos.get(clip)["chapters"]
    assert len(chapters) >= 3
    video = env.run("video", clip, {**VIDEO, "splitChapters": True})
    names = [Path(o.rel).name for o in video.outputs]
    assert len(names) == len(chapters)
    assert all(name.startswith(f"{i:02d} - ") and name.endswith(".mp4") for i, name in enumerate(names, start=1))
    assert {Path(o.rel).parent.name for o in video.outputs} == {"แยกตาม chapter (mp4)"}
    for i, chapter in enumerate(chapters):
        length = chapter["endS"] - chapter["startS"]
        assert length - 0.2 <= _duration(_path(video, i), "video") <= length + 3.2  # D6: up to one GOP more
    audio = env.run("audio", clip, {"format": "mp3", "mp3Kbps": 128, "splitChapters": True, "audioLanguage": "original"})
    assert {Path(o.rel).parent.name for o in audio.outputs} == {"แยกตาม chapter (mp3)"}
    for i, chapter in enumerate(chapters):
        assert abs(_duration(_path(audio, i), "audio") - (chapter["endS"] - chapter["startS"])) <= 0.15
    tags = {k.lower(): v for k, v in (ffprobe_json(_path(audio, 0))["format"].get("tags") or {}).items()}
    assert tags.get("track") == f"1/{len(chapters)}"


def test_ac_adv_04_sponsorblock_cuts_the_segments(env: Env) -> None:
    clip = CLIPS.get("sponsor_clip") or ""
    if not clip:
        pytest.skip("ใส่ id คลิปที่มีข้อมูล SponsorBlock ใน tests/network_videos.toml [advanced] sponsor_clip ก่อนรัน")
    info = env.videos.get(clip)
    segments = env.extractor.sponsor_segments(clip, ["sponsor"], float(info["durationS"]))
    assert segments, "คลิปนี้ไม่มีข้อมูล sponsor แล้ว เลือกคลิปใหม่"
    result = env.run("video", clip, {**VIDEO, "sponsorblock": ["sponsor"]})
    path = _path(result)
    assert path.name.endswith(" (ตัดโฆษณา).mp4") and result.notes == ()
    cut_s = sum(e - s for s, e in merge_intervals([(s, e) for s, e, _ in segments])) / 1000
    assert abs(_duration(path, "video") - (info["durationS"] - cut_s)) <= 1.0


def test_ac_adv_04_no_sponsor_data_keeps_the_full_clip(env: Env) -> None:
    result = env.run("video", CLIPS["no_sponsor_clip"], {**VIDEO, "sponsorblock": ["sponsor"]})
    assert result.notes == ("SPONSORBLOCK_EMPTY",)
    assert not _path(result).name.endswith(" (ตัดโฆษณา).mp4")


def test_ac_vid_10_part_1_embedded_subtitles_follow_the_range(env: Env) -> None:
    clip = CLIPS["range_clip"]
    params = {**VIDEO, "embedSubs": "a.th-orig", "subOptions": MEDIUM, "range": {"startMs": 90_000, "endMs": 120_000}}
    path = _path(env.run("video", clip, params))
    srt = subprocess.run(
        [env.ffmpeg, "-hide_banner", "-loglevel", "error", "-i", str(path), "-map", "0:s:0", "-f", "srt", "-"],
        check=True, capture_output=True,
    ).stdout.decode("utf-8")  # fmt: skip
    times = [
        (int(a) * 3_600_000 + int(b) * 60_000 + int(c) * 1000 + int(d), int(e) * 3_600_000 + int(f) * 60_000 + int(g) * 1000 + int(h))
        for a, b, c, d, e, f, g, h in SRT_TIME.findall(srt)
    ]
    assert times, "ไม่มีซับในไฟล์"
    assert min(s for s, _ in times) >= 0 and max(e for _, e in times) <= 30_000
```
- [ ] **Step 7: Check without running the network** — `uv run pytest -q -W error -p no:cacheprovider` (the new file is collected but deselected by `-m 'not network'`), and `uv run python -m py_compile tests/network/test_advanced_network.py`. Do **not** run `-m network`.

- [ ] **Step 8: Commit**
```bash
git add PRD.md BRD.md docs/acceptance.md docs/m4-followups.md tests/network_videos.toml tests/network/test_advanced_network.py
git commit -F- <<'EOF'
docs: M5 round A in PRD/BRD/acceptance; network tests for AC-ADV-01/03/04 and AC-VID-10 part 1

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
EOF
```

---

## Spec coverage (self-review)

| Spec item | Task(s) |
|---|---|
| §1 collapsible in วิดีโอ/เสียง/ซับ, one per-clip store, values survive tabs, reset on another clip/reload, stay after queueing | T7 (store), T10 |
| §1 badge in every tab, button labels, size estimate scaled | T7 (`choiceParts`, `scaleBytes`, `advancedActive`), T10 |
| §1 control matrix (range all tabs; chapters video/audio ≥ 2; SponsorBlock video/audio) | T10 (`chaptersOk`, `tab !== "subs"`) |
| §1.1 field formats, empty-end rules, player-time icon button + tooltip "กดเล่นคลิปก่อน", under-player buttons + toasts + open section, frame menu items, validation texts, live/unknown duration text, exact hint | T7, T10, T11 |
| §1.2 chapter switch + hints, hidden < 2 chapters, exclusivity texts both ways | T7 (`chapterBlock`), T10 |
| §1.3 SponsorBlock switch off per clip, hint, 8 categories with Thai labels, default ticks from `sponsorblockDefault`, PATCH on change, last one locked, subtitle warning (video under switch, subs above buttons) | T1 (settings validator), T6, T10 |
| §1.4 640 px, accessible names, aria-describedby, axe both themes | T10 e2e, T11 |
| §2 output names (range, ads, order, hours, subtitles), chapter sub-folder, numbering, sanitised titles, `chapter <n>`, ` (2)`, outputs in order, title/track metadata | T2, T3 (`track`), T8, T13 |
| §3.1 params + validation matrix + cached-probe checks, W3 unchanged | T1, T6 (W3 builder untouched) |
| §3.2 approach B: keep intervals, exact/fast cutter, audio ±50 ms, then M4 steps, embedded subs with range, disk check, cancel, progress stages | T2, T3, T8, T13, T1 (stages), T12 (stage text) |
| §3.3 SponsorBlock via yt-dlp in extractor, hashed prefix, notes (empty, unreachable, no chapters), never brakes | T4, T8, T13 |
| §3.4 subtitle range in Python and TS before cue building, midpoint rule, preview + copy follow, .txt == .srt | T5, T10 |
| §3.5 queue/history job text | T12 (history rows are per clip: unchanged, see Planner decisions) |
| §3.6 lifecycle sweep of new names; W2 download before settings load (items 1-3) | T9, T6, T10 (e2e item 3) |
| §4 tests: unit (params, intervals, names, parity, parsing, labels), fake cutter + fake SponsorBlock fixtures, chromium e2e, queue e2e, network tests (approval) | T1-T15 |
| §5 docs: PRD, BRD (FR-ADV, D1-D9 rows, follow-ups), acceptance M5-A section | T15 |

Self-review checks run on this plan: no "TBD"/"TODO"/"similar to Task N"; every function used by a later task is defined in a contract and in exactly one task (`split_stage`/`is_stage` T1, `keep_intervals`/`chapter_parts`/`range_suffix`/`ADS_SUFFIX` T2, `cut_args`/`MediaTools.cut`/`CutCall` T3, `SponsorSource`/`SponsorBlockError`/`sponsor_segments` T4, `range_tokens`/`clamp_cues`/`rangeTokens`/`clampCues` T5, `AdvancedParams`/`buildSubtitleParams`/`sponsorCategories`/`ready` T6, `validateRange`/`rangeText`/`advancedActions.mark` T7, `HandlerDeps.sponsors`/`_cut` T8, `toolkit_name_pattern` T9, `useAdvancedChoice`/`revealRangeErrors` T10, `markRange` T11, `jobTitle`/`stageText` T12); names match across tasks (`RangeError` has no `tooShort`, `AdvancedChoice.split` is defined in T10 and used only there; `export(…, range_ms)` is called positionally in T8).

---

## Execution handoff

Plan saved to `docs/superpowers/plans/2026-10-02-m5a-advanced-options.md`. Execute with superpowers:subagent-driven-development: one fresh subagent per task in its own worktree (lanes of a wave in parallel), the wave gate procedure between waves, and the two-stage review per task.
