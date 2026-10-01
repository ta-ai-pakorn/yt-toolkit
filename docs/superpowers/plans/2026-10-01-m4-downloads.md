# M4 โหลดและคิว (Downloads and the job queue) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Tasks inside one wave run as parallel subagents, each in its own git worktree (see "Waves"). Every task is reviewed by a reviewer subagent before its wave closes.

**Goal:** The user downloads clips as files that land in the output folder: mp4 (with audio language, no-audio and soft subtitles), m4a / mp3 / wav, subtitle files, contact sheets and frame zips. Everything goes through one persistent job queue with live progress (SSE), cancel, retry, reorder, an emergency brake for YouTube bot checks, a playlist / multi-link picker (W3), a queue bar and sheet on every page (W4), a history page (W5), the W7 dialogs and toasts, `แหล่งที่มา.txt` in every output folder and a "คัดลอกเครดิต" button.

**Scope (PRD section 10, row M4):** W2 video and audio tabs · `video`, `audio` (incl. wav) jobs · audio language / dubbed audio · no-audio · soft subtitles (`mov_text`) · `แหล่งที่มา.txt` + "คัดลอกเครดิต" · queue, SSE, W3, W4, W5, W7 · moving subtitle files, contact sheet and zip into the queue (PRD 6.2 notes, BRD #28, #49) · the M4 items of `docs/m2-followups.md` and `docs/m3-followups.md`.

**Acceptance criteria:** AC-VID-01..09 and AC-VID-10 part 2 (the 422; part 1 needs time ranges = M5) · AC-AUD-01..04 · AC-Q-01..08 · AC-OUT-01..08 · AC-SEC-05 · AC-SET-01 (settings API + W6 "ทั่วไป", if Q4 = A).

**Out of scope (M5 and later):** time ranges, split by chapter, SponsorBlock, sharp frames (`frames_sharp`), YouTube cookies, "ตั้งจุดเริ่ม/จบ" from the player, filename styles (M6), clear-cache / backup settings / stats (M6), the W2 "ตัวเลือกขั้นสูง" panel (nothing usable inside until M5, BRD #53 rule: hidden).

**Architecture:**
- **One queue, many handlers.** `core/queue.py` (`QueueRunner`) owns scheduling: concurrency 1-3 from settings, a random 2-5 s gap between consecutive YouTube-bound job starts, the 10-minute emergency brake keyed on the error **code** `E_BOT_CHECK` (never on HTTP status), automatic network retries (2, 5, 10 s), cancel within 3 s, restart recovery (`running` → `interrupted`, `work/` emptied). Each job kind has a handler in `core/handlers.py` that only orchestrates: probe (cached) → extractor download → media post-processing → move into the output folder → `แหล่งที่มา.txt`.
- **yt-dlp only downloads; we finish the file.** `core/extractor.py` (the only `yt_dlp` importer) does one extraction, asks a pure chooser (`core/download.py`) for the exact format spec (original audio, dub language, no-audio, compat 1080p), then downloads into `work/<jobId>/media.<ext>` with yt-dlp merging video+audio. `core/media.py` then runs our own ffmpeg pass (cover, metadata, `mov_text` subtitles, audio language tag, mp3/wav conversion) through a killable `subprocess.Popen` argument list. `core/files.py` computes the Windows-safe Thai folder/file names (≤ 240 chars, ` (2)` suffixes) and writes `แหล่งที่มา.txt`.
- **Live updates.** `core/events.py` (`EventBus`) coalesces job updates to at most 4 per second per job; `api/events.py` streams them as SSE. The web app keeps the job list in the react-query cache and patches it from SSE; on reconnect it refetches.
- **Fake mode end to end.** `YT_TOOLKIT_FAKE=1` swaps in `FakeExtractor.download` (copies tiny real media files from `tests/fixtures/media/`, timed by `tests/fixtures/downloads/behaviors.json`) and `FakeMediaTools` (no ffmpeg needed), writes outputs under `<data_root>/output`, and makes "เปิดโฟลเดอร์" a logged no-op. Playwright gets a second fake backend (`queue` project, port `E2E_PORT + 1`) so job-creating specs never disturb the existing specs.

**Tech Stack:** unchanged (Python 3.13 + uv, FastAPI, yt-dlp 2026.08.19 as a library, ffmpeg from `bin/` or PATH, React + Vite + Tailwind + shadcn/Base UI + react-query). New web packages: `@dnd-kit/core`, `@dnd-kit/sortable`, `@dnd-kit/utilities`. New shadcn components: `sheet`, `progress`, `alert-dialog`, `checkbox`, `table`. No new Python dependency.

---

## Owner decisions (ANSWERED 2026-10-01: all eight recommended)

The controller asks Pete the questions in `m4-questions.md` (scratchpad) before Wave 1 and records the answers here. **This plan is written for the recommended answer of every question.** Where another answer changes a task, the task says so in a "Q<n> ≠ recommended" note.

| # | Topic | Recommended answer the plan assumes |
|---|---|---|
| Q1 | A job that hits `E_BOT_CHECK` | Goes back to the front of the queue once (new transition `running → queued`) and restarts by itself when the brake ends; a second bot check on the same job fails it |
| Q2 | HTTP 403 / other 4xx (not 429) while downloading | Re-extract once, then fail with new code `E_YT_REFUSED`; never auto-retried, never brakes the queue |
| Q3 | Subtitle files, contact sheet, zip | Move into the queue (files land in the output folder); remove the old browser-download endpoints. "บันทึกเป็นโน้ต (.md)" stays a browser download |
| Q4 | Settings in M4 | Settings API + W6 "ทั่วไป" tab with output folder, jobs at once, default audio language, default video quality, default audio format |
| Q5 | W5 history | One list: every clip opened **or** downloaded, with file-type badges; W1 "ล่าสุด" keeps "opened only" via `?scope=opened` |
| Q6 | "คัดลอกเครดิต" placement | A "เครดิต" section at the top of the ข้อมูลคลิป tab (PRD wins over BRD 9.2); the header stays as it is |
| Q7 | Way into W3 | W1 results header button (all clip rows of the list) + a button on each playlist/mix row (that playlist only) |
| Q8 | W2 default tab | Stays ภาพเฟรม; new order ภาพเฟรม · วิดีโอ · เสียง · ซับ · ทรานสคริปต์ · ข้อมูลคลิป |

### Planner defaults (not questions; Pete can still object)
- **Remember last choices (BRD 10.8 #6):** like M3's `yt-toolkit.subs`, W2 remembers its last download choices in `localStorage` key `yt-toolkit.download` (`v: 1`). The server-side `lastUsed` setting stays unused until M6.
- **W3 / W5 tables:** a plain shadcn `Table` (semantic `<table>`), not `@reui/data-grid`: at most 200 rows, so no virtualization is needed, and no registry/network dependency. **Reorder (AC-Q-06):** `@dnd-kit` directly (what `@reui/sortable` wraps) with the keyboard sensor and Thai announcements.
- **Advanced options panel:** stays hidden in W2 in M4 (all its options are M5).
- **Video quality list:** "เปิดได้ทุกที่ สูงสุด 1080p (แนะนำ)" first, then every H.264 height ≤ 1080; the "ความละเอียดสูงสุด" switch adds VP9/AV1 and heights > 1080 with a "บางโปรแกรมเปิดไม่ได้" badge.
- **wav/mp3 source:** the AAC (m4a) track of the chosen language, so the W2 wav size estimate uses a known sample rate (default 44,100 Hz, 2 channels when the probe does not say).
- **Embed subtitles:** the list offers the clip's owner and original-language tracks (not machine translations) and uses the length preset currently set in the ซับ tab.
- **Narrow screens (BRD #83):** new M4 UI is checked at 640 × 800 CSS px (a 1280 px window at 200% zoom). Below 640 px the header menu shows icons only (with `aria-label` and tooltip) so "ประวัติ" fits; this keeps the existing 360 px tests green, it is not phone polish.
- **Disk check:** a job does not start its download when free space < 2 × the expected size (`E_DISK_FULL` "พื้นที่ไม่พอ ต้องมีว่างอย่างน้อย <ขนาด>").
- **Notes on jobs:** a job can carry notes (`AUDIO_LANG_FALLBACK`, `NO_SUBTITLES`, `EMBED_SUBS_SKIPPED`, `QUALITY_FALLBACK`), shown in grey in its queue row.
- **Downloads use the anonymous visitor session** (`with_session=True`) like probe and subtitles, so one extraction serves the whole job.
- **Batch subtitles:** a W3 subtitle job without a track uses the clip's default track; a clip with no default track ends `done` with no file and the note "คลิปนี้ไม่มีซับ" (not red, PRD 7 `E_NO_SUBTITLES`).
- **AC-VID-10 part 1** (embedded subtitles with a time range) moves to M5 with time ranges.

---


> **Owner answers (2026-10-01):** Pete chose the recommended option for all eight questions Q1-Q8 (see the questions list). The plan stands as written.

## Waves

| Wave | Lanes (one worktree each, file sets disjoint) | Depends on |
|---|---|---|
| 1 | T1 job store + schema v2 · T2 settings store + API + AppContext + settings wiring · T3 output files · T4 probe v5 + format chooser + error codes · T5 media tools + media fixtures · T6 event bus + SSE · T7 web kit, all M4 strings, deps, Playwright projects · T8 web data layer + e2e helpers | Owner answers Q1-Q8 |
| 2 | T9 extractor download (real + fake) · T10 job handlers · T11 queue runner + jobs API · T12 history API + bot-check brake hook + endpoint removal · T13 W5 history page + routes · T14 W4 queue bar/sheet + W7 shutdown dialog · T15 W2 วิดีโอ/เสียง tabs · T16 W2 subtitles/frames into the queue + credit · T17 W6 ทั่วไป tab | Wave 1 gate (T9←T1,T4 · T10←T1,T3,T4,T5 · T11←T1,T2,T4,T6 · T12←T2,T4 · T13..T17←T7,T8) |
| 3 | T18 lifecycle integration (wiring, fake mode, recovery, shutdown, tray count) · T19 W3 batch page | Wave 2 gate (T18←T9,T10,T11,T12 · T19←T7,T8,T13) |
| 4 | T20 network tests, docs (PRD/BRD/acceptance/followups/README), final verification, live preview for Pete | Wave 3 gate |

**Critical path:** T1 / T4 / T6 → T11 → T18 → gate 3 (first run of the `queue` e2e project) → T20.

**Counts:** 4 waves · 20 lanes (= 20 tasks).

### Lane rules (every task)
1. **Worktree and branch.** Each task runs in its own git worktree (`isolation: "worktree"`) on branch `m4/t<N>-<slug>`, branched from the integration branch `m4-downloads` at the start of its wave.
2. **Files.** A task creates or modifies **only** the files in its **Files** list. Needing another file is a plan bug: stop and report it to the controller; do not edit the file.
3. **Shared files have exactly one owner per wave:**

   | File | W1 owner | W2 owner | W3 owner | W4 owner |
   |---|---|---|---|---|
   | `src/yttoolkit/app.py` | T2 | T11 | — | — |
   | `src/yttoolkit/api/routes.py` | T2 | — | — | — |
   | `src/yttoolkit/lifecycle.py` | T2 | — | T18 | — |
   | `src/yttoolkit/tray.py` | — | — | T18 | — |
   | `src/yttoolkit/core/yterrors.py` | T4 | — | — | — |
   | `src/yttoolkit/core/videos.py` | T4 | T12 | — | — |
   | `src/yttoolkit/core/extractor.py` | — | T9 | — | — |
   | `src/yttoolkit/api/videos.py`, `src/yttoolkit/api/subtitles.py` | — | T12 | — | — |
   | `src/yttoolkit/api/errors.py` | — | T11 | — | — |
   | `tests/fixtures/README.md` | T5 | T9 | — | — |
   | `tests/fixtures/probe/**`, `tests/fixtures/errors/**` | T4 | — | — | — |
   | `web/src/i18n/th.ts` | T7 | — | — | — |
   | `web/package.json`, `web/package-lock.json`, `web/playwright.config.ts` | T7 | — | — | — |
   | `web/src/lib/types.ts` | T8 | — | — | — |
   | `web/src/router.tsx`, `web/src/pages/lazy.tsx` | — | T13 | T19 | — |
   | `web/src/components/layout.tsx` | — | T14 | — | — |
   | `web/src/pages/video/tabs.tsx`, `web/src/pages/video/url-state.ts` | — | T15 | — | — |
   | `PRD.md`, `BRD.md`, `README.md`, `docs/**` | — | — | — | T20 |
   | `web/dist/**` | wave gates and T20 only; no lane builds into or commits `web/dist` | | | |

   A lane that needs a Thai string that is not in C13 stops and asks the controller; the controller adds it at the gate.
4. **Tests.**
   - Python lanes run their own tests, then the full `uv run pytest -q -W error`.
   - Web lanes run `npm run typecheck && npm run lint && npm test` in `web/`.
   - Lanes **do not run Playwright.** Specs are written, typechecked and linted in the lane and run at the gate.
   - **No spec in the default `chromium` project may create a job.** A chromium spec that clicks an enqueue button must first `page.route("**/api/jobs", …)` and fulfil it (C14). Real jobs only run in `queue-*.spec.ts` files (the `queue` project).
5. **Processes.** No lane starts a server except T18 (integration tests start `serve` on 8850-8869 like `tests/integration/test_serve.py`) and T20 (preview on 8791). Never touch the owner's app on 8787. Kill processes by PID only.
6. **Commits.** Every commit message ends with exactly `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`. Use `git commit -F- <<'EOF' … EOF`.

### Wave gate procedure (controller, serial)
1. Merge every lane branch of the wave into `m4-downloads` with `--no-ff`. A merge conflict means the plan is wrong: stop and report.
2. `uv sync --frozen && uv run pytest -q -W error`
3. `cd web && npm ci && npm run typecheck && npm run lint && npm test && npm run build`, then check total JS gzip ≤ 400 KB excluding fonts (PRD 6.5; it was ~267 KB after M3.5).
4. `cd web && npm run e2e` (runs project `chromium` on `E2E_PORT` (default 8799) and then project `queue` on `E2E_PORT + 1` with one worker; both fake mode).
   - Gate 1 and gate 2: the `queue` project has no runnable backend features yet (jobs API is wired in T18); run `npx playwright test --project=chromium` only. Gate 3 runs both. A failing `queue-*` spec at gate 3 goes back to its owning task (T13-T17, T19) as a fix round.
5. Commit the rebuilt `web/dist` as `build(web): rebuild dist after M4 wave <n>` (with the trailer).
6. Run the two-stage review (spec, then quality) from superpowers:subagent-driven-development on each task of the wave, and fix findings in the owning lane before starting the next wave.

---

## Verified facts (read on 2026-10-01, yt-dlp 2026.08.19 in `.venv/Lib/site-packages/yt_dlp/`)
- `YoutubeDL.__init__` builds `self.format_selector` from `params['format']` (`YoutubeDL.py:817-820`). Changing `params['format']` later has no effect, so the download step uses a **second** `YoutubeDL` built with the chosen format and calls `process_ie_result(info, download=True)` on the info from the first extraction (`YoutubeDL.py:1909`). No second extraction request.
- Hooks: `progress_hooks`, `postprocessor_hooks`, `post_hooks` are constructor params (`YoutubeDL.py:823-825`). `yt_dlp.utils.DownloadCancelled` exists (`utils/_utils.py:1103`); raising it from a progress hook aborts the download.
- The merger postprocessor is `FFmpegMergerPP` (`postprocessor/ffmpeg.py:822`); its hook reports `postprocessor == "Merger"`.
- The trimmed probe (`core/videos.trim_probe`) keeps no media URLs (`_MEDIA_FIELDS`), no `license`, no `asr`, no `audio_channels`. The fixtures have no `license`/`asr`/`audio_channels` either.
- Fixture `8lpOfyoxcvU` has audio `th` "Thai original (default)" (`139-1`, `140-1`, …) and an `en-US` dub (`139-0`, `140-0`, …): the dub fixture for AC-VID-05/06/07. `aqz-KE-bpKQ` and `jNQXAC9IVRw` audio has no language. `jNQXAC9IVRw` has 3 chapters and owner subs; `88o5Sk8_m1Y` has `a.th-orig`; `aqz-KE-bpKQ` has no subs.
- `core/db.py` already creates `jobs` with `video_id … REFERENCES videos(video_id)` and `PRAGMA foreign_keys=ON`. No code writes `jobs` yet. W3 needs jobs for clips never probed, so the FK must go (schema v2, T1).
- `GET /api/history` already exists (W1 "ล่าสุด", `?limit=5`): opened clips only, `outputs: []`.
- `platform.windows.kill` already runs `taskkill /PID <pid> /T /F` (tree kill by PID).
- E2E runs with `YT_TOOLKIT_FFMPEG_PATH_LOOKUP=0` and an empty `bin/`: **no ffmpeg in e2e**, so fake mode must not need ffmpeg. The dev machine has ffmpeg 8.1 on PATH (`where ffmpeg`). CI python runs on `windows-latest` and `macos-latest`; tests that need real ffmpeg must `skipif` when it is missing.
- `ctx.output_dir` is today always the real `<Downloads>/YT-Toolkit`, even in fake mode: e2e would write into Pete's Downloads. Fake mode must use `<data_root>/output` (T18).
- uvicorn waits for open streaming responses on shutdown unless `timeout_graceful_shutdown` is set, so an open SSE stream would hang "ปิดโปรแกรม" (T18 sets it and closes the bus first).
- Playwright runs spec files in parallel against one backend; a paused or busy queue would leak into unrelated specs. Hence the separate `queue` project and backend (C14).

### Not yet verified (the named task verifies it and records the result in its commit message)
- ffmpeg 8.1 accepts a JPEG `attached_pic` with `-c copy` in mp4 and in `.m4a` written with `-f mp4`, and the wav muxer writes `title`/`artist` as INFO tags (T5, real-ffmpeg integration tests).
- `process_ie_result(info, download=True)` returns the info with `requested_downloads[-1]["filepath"]` after a merge (T9 network smoke in T20; T9 falls back to globbing `media.*`).
- A short public clip with a Thai dub and a short public 4K clip for the network tests (T20 looks for them; fallbacks are written in T20).

---

## Global Constraints
**Carried over:** everything under "Global Constraints" of `docs/superpowers/plans/2026-09-30-m3-subtitles.md` (and through it M2 and M1): Python 3.13 + uv; bind `127.0.0.1` only; wrong Host → 421; missing token or wrong Origin → 403; error envelope `{"error":{"code","message","detail"}}`; `pathlib` everywhere; Studio Dark, no Magic UI / Aceternity / Animate UI; `core/` never imports `api/` or `platform/`; every screen has loading / empty / error / normal; no TODO comments; unit and API tests never touch the network; network tests carry `@pytest.mark.network`.

**Project rules (owner):**
- Commit trailer, exactly: `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
- Never `shell=True`; no `os.system` / `os.popen`. External programs get an argument **list**. Only `yttoolkit.platform` checks the OS. Kill processes by PID only (`Popen.kill()` on a process we started, or `platform.kill(pid)`).
- No personal data, tokens or cookie values in logs or diagnostics. Never log an absolute output path (it contains the Windows user name): log the job id and the path relative to the output folder. API responses pass `error.detail` through `redact_home` (T11 makes it public in `api/errors.py`).
- `yt_dlp` is imported only in `src/yttoolkit/core/extractor.py`.
- Thai UI copy: buttons start with a verb, no "กรุณา", no "!". All web strings live in `web/src/i18n/th.ts` (C13); backend user-facing messages live in `core/yterrors.MESSAGES` and `core/jobs.NOTES` (C11).
- Narrow-screen rule (BRD #83): target a narrow desktop window or 200% zoom (checked at 640 × 800 CSS px), not phones. Nothing overflows horizontally (`document.documentElement.scrollWidth <= clientWidth`). No new phone-only polish (no new 44 px touch sizing, no swipe gestures). Existing 360 px tests must keep passing.
- At most one amber primary button per page. W2's only primary button is "โหลด mp4" (inside the วิดีโอ tab). W3's is "ส่งเข้าคิว N คลิป".

**Tests:**
- Backend: `uv run pytest -q -W error` (no warnings).
- Web: Vitest (`npm test`), ESLint 0 errors / 0 warnings, `tsc -b`.
- Playwright e2e against the fake backend only; e2e never touches real YouTube; jobs only in the `queue` project (C14). axe: no serious/critical issues in both themes on every new screen state.
- Real-ffmpeg tests are marked with the `requires_ffmpeg` skip helper (C9) and must pass on the dev machine at the gate.

**Formats:**
- Generated `.srt/.txt/.md` subtitle files and `แหล่งที่มา.txt`: UTF-8, no BOM, CRLF.
- Folder `<outputDir>/<ชื่อคลิป> [<videoId>]/`; file names per C10; full path ≤ 240 characters.
- Times shown in the UI: `H:MM:SS` / `M:SS` for ETA, sizes in decimal units (`MB` = 1,000,000 bytes) via the existing `lib/format.ts` helpers where they exist.

---

## Shared contracts (every lane codes against these)

### C1. Database schema v2 and the job model (`core/db.py`, `core/jobs.py`, T1)
`SCHEMA_VERSION = 2`. The `jobs` table (replaces v1; no foreign key to `videos`):
```sql
CREATE TABLE jobs (
  id            TEXT PRIMARY KEY,          -- UUIDv7 text (C1 uuid7)
  video_id      TEXT NOT NULL,
  title         TEXT NOT NULL DEFAULT '',  -- clip title known at enqueue, updated after probe
  kind          TEXT NOT NULL,             -- video | audio | subtitle | frames_sharp | contact_sheet | frames_zip
  params_json   TEXT NOT NULL,
  status        TEXT NOT NULL,             -- queued | running | done | failed | cancelled | interrupted
  stage         TEXT,                      -- probing | downloading_video | downloading_audio | merging | converting | writing
  progress      REAL,                      -- 0..1
  speed_bps     INTEGER,
  eta_s         INTEGER,
  attempt       INTEGER NOT NULL DEFAULT 0, -- automatic network retry in progress (1..3), 0 = none
  bot_checks    INTEGER NOT NULL DEFAULT 0, -- times this job hit E_BOT_CHECK (Q1)
  position      INTEGER NOT NULL,
  error_code    TEXT,
  error_message TEXT,                      -- Thai message at failure time
  error_detail  TEXT,                      -- raw technical text
  notes_json    TEXT,                      -- ["AUDIO_LANG_FALLBACK", ...]
  outputs_json  TEXT,                      -- [{"root","rel","sizeBytes","kind"}]
  created_at    TEXT NOT NULL,
  started_at    TEXT,
  finished_at   TEXT
);
CREATE INDEX jobs_status_position ON jobs(status, position);
```
Migration v1 → v2 runs in one transaction: `DROP INDEX IF EXISTS jobs_status_position`, `ALTER TABLE jobs RENAME TO jobs_v1`, create v2, copy the v1 columns that exist (`id, video_id, kind, params_json, status, stage, progress, speed_bps, eta_s, position, error_code, error_detail, outputs_json, created_at, started_at, finished_at`), `DROP TABLE jobs_v1`, `UPDATE schema_version SET version = 2`. A fresh database is created directly at v2.

`core/jobs.py` public names:
```python
JOB_KINDS = ("video", "audio", "subtitle", "frames_sharp", "contact_sheet", "frames_zip")
STATUSES = ("queued", "running", "done", "failed", "cancelled", "interrupted")
STAGES = ("probing", "downloading_video", "downloading_audio", "merging", "converting", "writing")
TERMINAL = frozenset({"done", "failed", "cancelled", "interrupted"})
# PRD 6.1 plus running -> queued (Q1, bot check only)
TRANSITIONS = frozenset({
    ("queued", "running"), ("queued", "cancelled"),
    ("running", "done"), ("running", "failed"), ("running", "cancelled"),
    ("running", "interrupted"), ("running", "queued"),
    ("failed", "queued"), ("interrupted", "queued"),
})
NOTES = {
    "AUDIO_LANG_FALLBACK": "คลิปนี้ไม่มีเสียงภาษาที่เลือก ใช้เสียงต้นฉบับแทน",
    "NO_SUBTITLES": "คลิปนี้ไม่มีซับ",
    "EMBED_SUBS_SKIPPED": "ฝังซับไม่สำเร็จ ได้ไฟล์วิดีโอที่ไม่มีซับ",
    "QUALITY_FALLBACK": "คุณภาพที่เลือกไม่มีแล้ว ใช้คุณภาพที่ใกล้ที่สุดแทน",
}

def uuid7() -> str: ...           # 36-char RFC 9562 v7 text, lexically increasing per millisecond

# JobCancelled lives in core/cancel.py (owned by T5) so wave-1 lanes do not depend on each other:
#   class JobCancelled(Exception): ...   # raised by handlers / extractor / media when cancel is requested
# core/jobs.py re-exports nothing; every user imports `from .cancel import JobCancelled`.
class InvalidTransition(Exception): ...    # API maps to 409 E_JOB_STATE

@dataclass(frozen=True)
class OutputFile:
    root: str        # absolute output root at job time (never sent to the browser)
    rel: str         # "<folder>/<file>" with "/" separators
    size_bytes: int
    kind: str        # "video" | "audio" | "subtitle" | "image" | "archive"

@dataclass(frozen=True)
class NewJob:
    video_id: str
    kind: str
    params: dict
    title: str = ""

@dataclass(frozen=True)
class JobResult:
    outputs: tuple[OutputFile, ...] = ()
    notes: tuple[str, ...] = ()
    title: str | None = None

class JobContext(Protocol):
    job_id: str
    workdir: Path        # work/<jobId>/, created by the runner, removed after the job
    output_root: Path    # settings outputDir snapshot taken when the job starts
    def stage(self, stage: str) -> None: ...
    def progress(self, fraction: float | None, speed_bps: int | None = None, eta_s: int | None = None) -> None: ...
    def set_title(self, title: str) -> None: ...
    def cancelled(self) -> bool: ...
    def check_cancelled(self) -> None: ...      # raises JobCancelled
    def wait(self, seconds: float) -> None: ... # cancellable sleep, raises JobCancelled

Handler = Callable[["Job", JobContext], JobResult]

@dataclass
class Job:
    id: str; video_id: str; title: str; kind: str; params: dict; status: str
    stage: str | None; progress: float | None; speed_bps: int | None; eta_s: int | None
    attempt: int; bot_checks: int; position: int
    error_code: str | None; error_message: str | None; error_detail: str | None
    notes: tuple[str, ...]; outputs: tuple[OutputFile, ...]
    created_at: str; started_at: str | None; finished_at: str | None
    def to_api(self) -> dict: ...   # C2 shape, without "cancelling" (the API adds it)

class JobStore:
    def __init__(self, db: Database, *, now: Callable[[], datetime] = ..., new_id: Callable[[], str] = uuid7) -> None
    def add(self, items: Sequence[NewJob]) -> list[Job]                 # queued, positions max+1, max+2, ...
    def get(self, job_id: str) -> Job | None
    def list_default(self) -> list[Job]                                  # C4 "default list"
    def list_status(self, status: str, limit: int) -> list[Job]
    def queued(self) -> list[Job]                                        # by position asc
    def running(self) -> list[Job]
    def transition(self, job_id: str, to: str, **fields: Any) -> Job     # validates TRANSITIONS; sets started_at (→running), finished_at (→terminal)
    def update(self, job_id: str, **fields: Any) -> Job                  # running jobs only: stage, progress, speed_bps, eta_s, attempt, title
    def requeue(self, job_id: str, *, front: bool = False, bot_checks: int | None = None, reset_bot_checks: bool = False) -> Job
        # failed|interrupted|running → queued in ONE transaction; clears error/progress/outputs/notes/attempt/stage
        # (gate 1) transition(id, "queued") always raises InvalidTransition: requeue() is the only way back into the queue
    def reorder(self, ids: Sequence[str]) -> None                        # see C4 PUT /jobs/order
    def interrupt_running(self, message: str) -> int                     # every running → interrupted, error_code E_INTERRUPTED
    def pending_count(self) -> int                                       # queued + running
```
Field names passed to `transition`/`update` are the Python attribute names (`error_code`, `error_message`, `error_detail`, `notes`, `outputs`, `bot_checks`, …). Timestamps are ISO 8601 UTC with `+00:00`.

### C2. Job JSON (API and SSE) and TS types
```ts
export type JobKind = "video" | "audio" | "subtitle" | "frames_sharp" | "contact_sheet" | "frames_zip"
export type JobStatus = "queued" | "running" | "done" | "failed" | "cancelled" | "interrupted"
export type JobStage = "probing" | "downloading_video" | "downloading_audio" | "merging" | "converting" | "writing"
export type JobError = { code: string; message: string; detail?: string | null }
export type JobNote = { code: string; message: string }
export type JobOutput = { index: number; name: string; sizeBytes: number }   // name = file name only, never a path
export type Job = {
  id: string; videoId: string; title: string; kind: JobKind; params: JobParams
  status: JobStatus; stage?: JobStage; progress?: number; speedBps?: number; etaS?: number
  attempt?: number          // present when > 0: "เน็ตหลุด กำลังลองใหม่ (ครั้งที่ n/3)"
  cancelling?: boolean      // present (true) while a running job is being cancelled
  position: number
  error?: JobError; notes?: JobNote[]; outputs?: JobOutput[]
  createdAt: string; startedAt?: string; finishedAt?: string
}
export type JobPatch = { id: string } & { [K in keyof Omit<Job, "id">]?: Job[K] | null }  // null = field cleared
```
`Job.to_api()` omits keys whose value is `None` (and `attempt` when 0, `notes`/`outputs` when empty). `error` is `{code, message, detail}` with `detail` redacted by the API layer.

### C3. Params per kind (validated by `api/jobs.py`, consumed by `core/handlers.py`)
```ts
export type VideoJobParams = {
  formatId?: string            // ^[A-Za-z0-9_-]{1,32}$ ; absent = automatic
  maxQuality: boolean          // default false
  maxHeight?: 720 | 1080       // compat mode cap, default 1080 (W3 / settings "compat-720")
  splitChapters: false         // true -> 422 in M4 (M5)
  noAudio: boolean             // default false
  audioLanguage: string        // "original" | BCP-47-ish tag ^[A-Za-z]{2,3}(-[A-Za-z0-9]{2,8})*$ ; default "original"
  embedSubs?: string           // track id ^[oat]\.[A-Za-z0-9_-]{1,64}$ ; requires subOptions
  subOptions?: SubOptions
}
export type AudioJobParams = { format: "m4a" | "mp3" | "wav"; mp3Kbps?: 128 | 192 | 320; splitChapters: false; audioLanguage: string }
export type SubtitleJobParams = { trackId?: string; format: "srt" | "txt" | "md"; options: SubOptions }
export type ContactSheetJobParams = { source: "fast"; columns: 5 }
export type FramesZipJobParams = { source: "fast" }
export type JobParams = VideoJobParams | AudioJobParams | SubtitleJobParams | ContactSheetJobParams | FramesZipJobParams
export type NewJob = { videoId: string; kind: Exclude<JobKind, "frames_sharp">; params: JobParams; title?: string }
```
Validation (422 `E_BAD_REQUEST` via the existing validation handler): unknown keys rejected (`extra="forbid"`, so `range`, `sponsorblock`, `useCookies` → 422 in M4); `kind == "frames_sharp"` → 422; `splitChapters: true` → 422 (and AC-VID-10: `embedSubs` together with `splitChapters: true` → 422); `embedSubs` without `subOptions` → 422; `subOptions`/`options` pass `srt_builder.options_from_dict`; mp3 without `mp3Kbps` → normalised to 192; the stored params are the normalised dict (`model_dump(exclude_none=True)`).

### C4. Jobs API (`api/jobs.py`, T11) — all under `/api`, sync `def` routes
| Method | Path | Body / query | Response |
|---|---|---|---|
| POST | `/jobs` | `{items: NewJob[]}` (1..500) | 200 `{jobs: Job[]}` · 422 `E_BAD_REQUEST` · 409 `E_FFMPEG_MISSING` when any item kind is in `FFMPEG_KINDS` and `ctx.media.available()` is false (nothing enqueued) |
| GET | `/jobs` | `?status=<JobStatus>&limit=1..200` (default 50) | `{jobs: Job[]}`. **No `status` = default list:** all `running` (by `started_at` asc) and `queued` (by `position` asc), the 20 newest `failed`/`interrupted` finished in the last 7 days, and the 20 newest `done` finished in the last 24 h. `cancelled` is never in the default list. With `status`: queued by position asc, running by started_at asc, others by `finished_at` desc |
| GET | `/queue` | — | `{pausedUntil: string \| null, reason: string \| null, concurrency: 1 \| 2 \| 3}` |
| POST | `/jobs/{id}/cancel` | — | `Job` (queued → `cancelled` at once; running → still `running` with `cancelling: true`, the final `cancelled` arrives by SSE within 3 s) · 404 `E_NOT_FOUND` · 409 `E_JOB_STATE` for terminal jobs |
| POST | `/jobs/{id}/retry` | — | `Job` (`failed`/`interrupted` → `queued` at the end) · 404 · 409 `E_JOB_STATE` |
| PUT | `/jobs/order` | `{ids: string[]}` (1..1000) | `{ok: true}`. Ids that are not currently `queued` are ignored. The remaining ids take the **existing position values of those same jobs**, sorted ascending, in the order given; other queued jobs keep their positions |
| POST | `/queue/resume` | — | `{ok: true}` (also when not paused) |
| GET | `/jobs/{id}/outputs/{n}` | — | the file, `Content-Disposition: attachment` via `attachment_header(fallback, name)` (fallback `download.<ext>`) · 404 `E_NOT_FOUND` when the job, the index or the file is missing, or when the resolved path is not inside the job's recorded root |
| POST | `/jobs/{id}/outputs/{n}/reveal` | — | `{ok: true}` after `ctx.reveal(path)` (None → `ctx.plat.reveal`) · 404 as above |
| GET | `/events` | — | SSE (C6) |

Job ids in paths must match `^[0-9a-f-]{36}$`, else 404. Every route returns `Job.to_api()` plus `cancelling: true` when `queue.is_cancelling(id)`, with `error.detail` passed through `redact_home`.

### C5. Settings (`core/settings.py`, `api/settings.py`, T2)
Keys and defaults (PRD 6.4, plus `"word"` in `subPreset`, BRD #61):

| key | type | default |
|---|---|---|
| `outputDir` | absolute path string | real mode `<Downloads>/YT-Toolkit`; fake mode `<data_root>/output` (passed in by lifecycle) |
| `videoDefault` | `"compat-1080" \| "compat-720" \| "max"` | `"compat-1080"` |
| `audioDefault` | `"m4a" \| "mp3" \| "wav"` | `"m4a"` |
| `audioLanguage` | `"original"` or a tag (regex in C3) | `"original"` |
| `mp3Kbps` | `128 \| 192 \| 320` | `192` |
| `subPreset` | `"short" \| "medium" \| "long" \| "word" \| "custom"` | `"medium"` |
| `subCustom` | SubOptions (camelCase) | medium preset values |
| `concurrency` | `1 \| 2 \| 3` | `2` |
| `sponsorblockDefault` | string[] | `["sponsor","selfpromo","interaction"]` |
| `theme` | `"system" \| "dark" \| "light"` | `"system"` |
| `filenameStyle` | `"title" \| "title-channel" \| "title-quality"` | `"title"` |
| `cookies` | `{enabled, source, warningAccepted, importedAt?}` | `{enabled:false, source:null, warningAccepted:false}` (read-only via PATCH) |
| `statsResetAt` | string \| null | `null` (read-only via PATCH) |
| `lastUsed` | object | `{}` |

```python
class SettingsError(Exception):
    def __init__(self, code: str, detail: str) -> None   # code: E_BAD_REQUEST | E_OUTPUT_NOT_WRITABLE
class SettingsStore:
    def __init__(self, db: Database, default_output_dir: Path) -> None
    def get(self) -> dict            # full Settings, defaults merged with stored values
    def patch(self, partial: Mapping[str, Any]) -> dict   # all-or-nothing; persists; returns full Settings
    def output_dir(self) -> Path
    def concurrency(self) -> int
```
PATCH rules: unknown key, wrong type, out-of-range value, or `cookies`/`statsResetAt` → `SettingsError("E_BAD_REQUEST")`; `outputDir` must be absolute; it is created (`mkdir(parents=True, exist_ok=True)`) and probed by writing and deleting `.yt-toolkit-write-test`; failure → `SettingsError("E_OUTPUT_NOT_WRITABLE")`. Nothing is stored if any key fails.

API: `GET /settings` → Settings · `PATCH /settings` → Settings | 422 `{code: E_BAD_REQUEST | E_OUTPUT_NOT_WRITABLE}` · `POST /settings/open-output` → `{ok:true}` after creating the folder and calling `ctx.open_folder(path)` (None → `ctx.plat.open_folder`); not writable → 422 `E_OUTPUT_NOT_WRITABLE`.

### C6. Events (`core/events.py`, `api/events.py`, T6)
```python
@dataclass(frozen=True)
class Event:
    name: str      # "job.created" | "job.updated" | "queue.paused" | "queue.resumed" | "app.shutdown"
    data: dict

CLOSED: Final = object()   # sentinel returned by Subscription.get after close()

class Subscription:
    def get(self, timeout: float) -> Event | None | object   # Event, None on timeout, CLOSED after bus/sub close
    def close(self) -> None

class EventBus:
    MIN_INTERVAL_S = 0.25
    def __init__(self, *, monotonic: Callable[[], float] = time.monotonic,
                 schedule: Callable[[float, Callable[[], None]], None] | None = None) -> None
        # schedule(delay_s, fn) runs fn later; default uses threading.Timer (daemon)
    def subscribe(self) -> Subscription
    def publish(self, name: str, data: dict) -> None          # immediate
    def job_updated(self, job_id: str, fields: dict) -> None  # merge into a pending patch for job_id;
        # emit {"id": job_id, **merged} now if >= 0.25 s since this job's last emit, else schedule one flush
        # at last_emit + 0.25 s. Result: at most 4 job.updated per second per job (AC-Q-08); nothing is lost.
    def close(self) -> None                                    # every subscription's get() returns CLOSED
```
Wire format (`api/events.py`): `format_event(e) = f"event: {e.name}\ndata: {json.dumps(e.data, ensure_ascii=False, separators=(',', ':'))}\n\n"`. The stream starts with `retry: 3000\n\n`; sends `: ping\n\n` after 15 s without events; ends when the bus closes. Response headers: `Content-Type: text/event-stream; charset=utf-8`, `Cache-Control: no-cache`, `X-Accel-Buffering: no`.
```python
async def sse_stream(bus: EventBus, *, ping_s: float = 15.0, poll_s: float = 1.0,
                     monotonic: Callable[[], float] = time.monotonic) -> AsyncIterator[str]
def build_events_router(ctx: AppContext) -> APIRouter    # GET /events (needs ctx.events)
```
`sse_stream` waits with `await anyio.to_thread.run_sync(sub.get, poll_s, abandon_on_cancel=True)` and closes its subscription in `finally`.

Payloads: `job.created` = full `Job`; `job.updated` = `JobPatch`; `queue.paused` = `{until: ISO, reason: "E_BOT_CHECK"}`; `queue.resumed` = `{}`; `app.shutdown` = `{}`.

### C7. Queue runner (`core/queue.py`, T11)
```python
@dataclass(frozen=True)
class PauseState:
    until: datetime
    reason: str

class SettingsView(Protocol):
    def concurrency(self) -> int: ...
    def output_dir(self) -> Path: ...

class QueueRunner:
    def __init__(self, store: JobStore, bus: EventBus, handlers: Mapping[str, Handler], *,
                 settings: SettingsView, work_root: Path,
                 delay_range: tuple[float, float] = (2.0, 5.0), brake_s: float = 600.0,
                 retry_waits: tuple[float, ...] = (2.0, 5.0, 10.0),
                 monotonic: Callable[[], float] = time.monotonic,
                 wall: Callable[[], datetime] = lambda: datetime.now(UTC),
                 rng: random.Random | None = None,
                 spawn: Callable[[Callable[[], None]], None] | None = None) -> None
        # spawn(fn) runs a worker; default starts a daemon thread. Tests pass a recorder.
    def start(self) -> None                    # dispatcher thread: tick() on wake-up or every 0.2 s
    def tick(self) -> list[str]                # one scheduling pass, returns the ids it started
    def enqueue(self, items: Sequence[NewJob]) -> list[Job]   # publishes job.created per job, wakes dispatcher
    def cancel(self, job_id: str) -> Job       # KeyError -> 404, InvalidTransition -> 409
    def retry(self, job_id: str) -> Job
    def reorder(self, ids: Sequence[str]) -> None   # publishes job.updated {id, position} for moved jobs
    def brake(self, reason: str = "E_BOT_CHECK") -> None   # pause until wall()+brake_s (extends), publishes queue.paused
    def resume(self) -> None                   # clears pause, publishes queue.resumed, wakes dispatcher
    def pause_state(self) -> PauseState | None # expired pause is cleared here (publishes queue.resumed)
    def is_cancelling(self, job_id: str) -> bool
    @property
    def next_youtube_at(self) -> float          # monotonic time before which no YouTube job starts (tests read it)
    def pending_count(self) -> int
    def recover(self) -> int                   # startup: store.interrupt_running(MESSAGES["E_INTERRUPTED"]) + empty work_root
    def shutdown(self, timeout: float = 5.0) -> None   # stop dispatcher; cancel running with reason "shutdown"
        # -> they end "interrupted" (E_INTERRUPTED); join up to timeout; leftovers interrupted by the store; empty work_root
```
Scheduling (`tick`): (1) paused and not expired → start nothing; expired → clear + `queue.resumed`. (2) `slots = settings.concurrency() - len(store.running())`. (3) Walk `store.queued()` by position while `slots > 0`: a job whose kind is in `YOUTUBE_KINDS` waits while `monotonic() < next_youtube_at` (skip it, later non-YouTube jobs may still start); starting a YouTube job sets `next_youtube_at = monotonic() + rng.uniform(*delay_range)`. The first YouTube job after idle starts at once (`next_youtube_at` starts at `-inf`). (4) Start = `store.transition(id, "running")`, publish, create `work_root/<id>/`, `spawn(worker)`.

Worker outcome rules:
- `JobResult` → `done` with `outputs`, `notes`, `title`, `progress=1`.
- `JobCancelled` → `cancelled` (user) or `interrupted` with `E_INTERRUPTED` (shutdown).
- `YtError("E_NETWORK")` while `attempt < 3` → `attempt += 1`, publish, `ctx.wait(retry_waits[attempt-1])`, run the handler again (same workdir). After the third retry fails → `failed` `E_NETWORK` with `MESSAGES["E_NETWORK"]`.
- `YtError("E_BOT_CHECK")` → `brake()`; if `bot_checks == 0` → `store.requeue(id, front=True, bot_checks=1)` (Q1, one transaction); else `transition(id, "failed", error_code="E_BOT_CHECK")`. A manual retry calls `store.requeue(id, reset_bot_checks=True)` and returns 409 E_JOB_STATE unless the job is failed or interrupted. **Only the code decides; HTTP status is never consulted.** `E_TRANSLATION_BLOCKED`, `E_SESSION_WARMING` and every other code never brake.
- Other `YtError` → `failed` with `code`, `exc.message`, `exc.detail`. Any other exception → `failed` `E_UNKNOWN` (`log.exception` with the job id).
- Always: `shutil.rmtree(workdir, ignore_errors=True)`, wake the dispatcher, log `"งาน %s (%s) จบด้วย %s"` with id, kind, status/code (no absolute paths).

`JobContext` (concrete, private to `core/queue.py`): `progress()` and `stage()` write the store and call `bus.job_updated`; `cancelled()` is a `threading.Event`; `wait()` waits on that event.

### C8. Format chooser and download contract (`core/download.py` T4, `core/extractor.py` T9)
```python
YOUTUBE_KINDS = frozenset({"video", "audio", "subtitle", "frames_sharp"})
FFMPEG_KINDS = frozenset({"video", "audio"})

@dataclass(frozen=True)
class DownloadChoice:
    format_spec: str              # yt-dlp format string
    merge_mp4: bool               # True -> merge_output_format "mp4"
    audio_language: str | None    # language of the chosen audio track (for metadata), None = unknown / no audio
    notes: tuple[str, ...]        # C1 NOTES codes
    expected_bytes: int | None    # for the disk check

@dataclass
class DownloadHooks:
    on_stage: Callable[[str], None]
    on_progress: Callable[[float | None, int | None, int | None], None]   # fraction, speed B/s, eta s
    is_cancelled: Callable[[], bool]
    ffmpeg_location: Path | None

@dataclass(frozen=True)
class DownloadResult:
    path: Path        # the media file inside workdir
    info: dict        # sanitized yt-dlp info of this extraction
    choice: DownloadChoice

class Downloader(Protocol):
    def download(self, video_id: str, choose: Callable[[dict], DownloadChoice],
                 workdir: Path, hooks: DownloadHooks) -> DownloadResult: ...
    def fetch(self, url: str) -> bytes: ...

def pick_audio(formats: list[dict], want: str, *, codec_prefix: str | None) -> tuple[dict | None, tuple[str, ...]]
def video_choice(info: dict, params: Mapping[str, Any]) -> DownloadChoice
def audio_choice(info: dict, params: Mapping[str, Any]) -> DownloadChoice
```

`pick_audio` (exact):
1. Candidates = the raw format dicts for the entries of `core.videos._audio_formats(formats)` (same filtering and `isOriginal` rule as VideoInfo). If `codec_prefix` is set, keep those whose `acodec` starts with it; if none remain, keep all.
2. `want` empty or `"original"`: pool = candidates flagged original, or all candidates if none is flagged; return the max by `(abr or 0, format_id)`; notes `()`.
3. Otherwise `L = want.lower()`: matches = candidates whose `language` lower-cased equals `L` or starts with `L + "-"`; return the max by `(abr or 0, format_id)`, notes `()`. No match → the result of rule 2 with notes `("AUDIO_LANG_FALLBACK",)`.
4. No candidates at all → `(None, ())`.

`video_choice` (exact): `H = params.get("maxHeight", 1080)`; compat = not `maxQuality` and no `formatId`.
- Video part: `formatId` present and in `info["formats"]` → `formatId`; present but missing → treat as automatic and add note `QUALITY_FALLBACK`; `maxQuality` → `bv*`; compat → `bv*[vcodec^=avc1][height<={H}]`.
- `noAudio` → `format_spec = <video part>` (no `+`, no `ba`, no fallback; AC-VID-08).
- With audio: `aud = pick_audio(formats, audioLanguage, codec_prefix=None if maxQuality else "mp4a")`; `aid = aud["format_id"]` or `"ba"` (maxQuality) / `"ba[acodec^=mp4a]"` (otherwise); `format_spec = f"{video}+{aid}"` + (`"/b[ext=mp4]"` if compat, `"/b"` if maxQuality, `""` if formatId).
- `merge_mp4 = True`; `audio_language = aud.get("language")` (None for noAudio); `expected_bytes` = size of the best format matching the video part (max height, then max `filesize`/`filesize_approx`) + size of `aud` (`filesize`, `filesize_approx`, or `abr * 1000 / 8 * duration`), None when unknown.

`audio_choice`: `aud = pick_audio(formats, audioLanguage, codec_prefix="mp4a")`; `format_spec = aud["format_id"]` or `"ba[acodec^=mp4a]/ba"`; `merge_mp4 = False`; for `wav`, `expected_bytes += duration * 44100 * 2 * 2`.

**Real `download` (T9):** check id → extract with `self._ydl(_PROBE_OPTS, with_session=True)` → `check_live` → `choice = choose(ydl.sanitize_info(info))` (a `YtError` from `choose` propagates unchanged) → a second `YoutubeDL` with `_download_opts(choice, workdir, hooks)` → `process_ie_result(info, download=True)` → path = `requested_downloads[-1]["filepath"]` or the single `media.*` file in workdir (ignoring `*.part`, `*.ytdl`). Errors: `DownloadCancelled` → `JobCancelled`; `YoutubeDLError` → `YtError(classify(msg), msg)`; `E_YT_REFUSED` from the download step → extract + choose + download once more, then raise (Q2); other exceptions → `E_UNKNOWN`.
```python
def _download_opts(choice: DownloadChoice, workdir: Path, hooks: DownloadHooks) -> dict:
    # quiet, no_warnings, noprogress=True, noplaylist=True, overwrites=True, socket_timeout=20,
    # retries=3, fragment_retries=3, format=choice.format_spec,
    # outtmpl={"default": "media.%(ext)s"}, paths={"home": str(workdir), "temp": str(workdir)},
    # merge_output_format="mp4" only when choice.merge_mp4, ffmpeg_location=str(...) only when set,
    # progress_hooks=[_progress_hook(hooks)], postprocessor_hooks=[_pp_hook(hooks)], logger=_YtDlpLogger()
```
`_progress_hook`: on `status == "downloading"`: if `hooks.is_cancelled()` raise `DownloadCancelled`; stage = `"downloading_audio"` when `info_dict.vcodec == "none"` else `"downloading_video"` (call `on_stage` only when it changes); fraction = `downloaded_bytes / (total_bytes or total_bytes_estimate)` or None; speed/eta as ints or None. `_pp_hook`: on `status == "started"`: cancelled → raise `DownloadCancelled`; `postprocessor == "Merger"` → `on_stage("merging")`.

**Fake `download` (T9):** reads `tests/fixtures/downloads/behaviors.json` (C14). `info = self.probe(video_id)`; `choice = choose(info)`; runs `steps` progress steps of `stepMs` (`downloading_video` for the first half and `downloading_audio` for the second when `merge_mp4` and `"+"` in the spec, else one stage), checking `is_cancelled()` before each step (→ `JobCancelled`); `failAtStep`/`error`/`failTimes` raise `YtError(error, "fake: …")` (failures counted per video id for the lifetime of the extractor); then `on_stage("merging")` when `merge_mp4`, and copies `media/video.mp4` (merge with `+`), `media/video-noaudio.mp4` (merge without `+`) or `media/audio.m4a` (no merge) to `workdir/media.mp4` / `media.m4a`.

### C9. Media tools (`core/media.py`, T5)
```python
@dataclass(frozen=True)
class MediaMeta:
    title: str
    artist: str               # channel
    comment: str              # https://www.youtube.com/watch?v=<id>
    date: str | None          # YYYY-MM-DD
    duration_s: float | None  # for progress only

@dataclass(frozen=True)
class SubtitleInput:
    path: Path                # UTF-8 .srt in workdir
    language: str             # ISO 639-2 ("tha")

class MediaTools(Protocol):
    def available(self) -> bool: ...
    def ffmpeg_path(self) -> Path | None: ...
    def finalize_mp4(self, src: Path, dst: Path, meta: MediaMeta, *, cover: Path | None,
                     subtitle: SubtitleInput | None, audio_language: str | None,
                     cancel: Callable[[], bool], on_progress: Callable[[float | None], None]) -> None: ...
    def finalize_m4a(self, src, dst, meta, *, cover, audio_language, cancel, on_progress) -> None: ...
    def to_mp3(self, src, dst, meta, *, kbps: int, cover, audio_language, cancel, on_progress) -> None: ...
    def to_wav(self, src, dst, meta, *, audio_language, cancel, on_progress) -> None: ...

class FfmpegTools:   # MediaTools
    def __init__(self, find_ffmpeg: Callable[[], Path | None], *, popen_flags: int = 0) -> None
class FakeMediaTools:   # MediaTools, available() is True, copies files, no ffmpeg
    def __init__(self, media_root: Path) -> None

def mp4_args(ffmpeg: str, src: Path, dst: Path, meta: MediaMeta, *, cover: Path | None,
             subtitle: SubtitleInput | None, audio_language: str | None) -> list[str]
def m4a_args(ffmpeg, src, dst, meta, *, cover, audio_language) -> list[str]
def mp3_args(ffmpeg, src, dst, meta, *, kbps, cover, audio_language) -> list[str]
def wav_args(ffmpeg, src, dst, meta, *, audio_language) -> list[str]
def run_ffmpeg(args: list[str], *, duration_s: float | None, cancel: Callable[[], bool],
               on_progress: Callable[[float | None], None], popen_flags: int = 0) -> None
def iso639_2(lang: str | None) -> str   # "th"->"tha", "en"/"en-US"->"eng", 3 letters pass through lower-cased, else "und"
```
`iso639_2` table: th tha, en eng, ja jpn, ko kor, zh chi, fr fre, de ger, es spa, pt por, ru rus, vi vie, id ind, ms may, hi hin, ar ara, it ita, lo lao, my bur, km khm. The skip helper for real-ffmpeg tests lives in `tests/helpers_ffmpeg.py` (T5), not in `core/media.py`.
Argument lists (exact order; `M` = `["-metadata", f"title={t}", "-metadata", f"artist={a}", "-metadata", f"comment={c}"]` plus `["-metadata", f"date={d}"]` when `date`; `L(s)` = `[f"-metadata:s:{s}:0", f"language={iso639_2(audio_language)}"]` when `audio_language`):
- common head: `[ffmpeg, "-hide_banner", "-nostdin", "-y", "-progress", "pipe:1", "-nostats", "-i", src]`
- mp4: head + (`["-i", cover]`) + (`["-i", sub.path]`) + `["-map", "0:v:0", "-map", "0:a?"]` + (`["-map", f"{sub_idx}:0"]`) + (`["-map", f"{cover_idx}:0"]`) + `["-c", "copy"]` + (`["-c:s", "mov_text", "-metadata:s:s:0", f"language={sub.language}", "-disposition:s:0", "default"]`) + (`["-disposition:v:1", "attached_pic"]`) + M + L("a") + `["-movflags", "+faststart", dst]`. Input indexes: cover = 1 when present; subtitle = 1 + (cover present).
- m4a: head + (`["-i", cover]`) + `["-map", "0:a:0"]` + (`["-map", "1:0", "-disposition:v:0", "attached_pic"]`) + `["-c", "copy"]` + M + L("a") + `["-f", "mp4", "-movflags", "+faststart", dst]`
- mp3: head + (`["-i", cover]`) + `["-map", "0:a:0"]` + (`["-map", "1:0"]`) + `["-c:a", "libmp3lame", "-b:a", f"{kbps}k"]` + (`["-c:v", "copy", "-disposition:v:0", "attached_pic"]`) + `["-id3v2_version", "3"]` + M + L("a") + `[dst]`
- wav: head + `["-map", "0:a:0", "-c:a", "pcm_s16le"]` + `["-metadata", f"title={t}", "-metadata", f"artist={a}"]` + `[dst]` (sample rate unchanged: no `-ar`)

`run_ffmpeg`: `subprocess.Popen(args, stdin=DEVNULL, stdout=PIPE, stderr=PIPE, creationflags=popen_flags)`; reader threads parse `out_time_us=` (fraction = µs / (duration_s × 10⁶), clamped 0..1, None when duration unknown) and keep the last 4,000 characters of stderr; poll every 0.1 s; `cancel()` → `proc.kill()`, `wait()`, raise `JobCancelled`; non-zero exit → `YtError("E_DISK_FULL", tail)` when the tail contains "No space left on device", else `YtError("E_UNKNOWN", f"ffmpeg exit {code}: {tail}")`. `FfmpegTools` methods raise `YtError("E_FFMPEG_MISSING")` when `find_ffmpeg()` is None.

### C10. Output files (`core/files.py`, T3)
```python
PATH_LIMIT = 240
TITLE_MAX = 100
TAIL_RESERVE = 30          # suffix + "." + ext is at most this long (asserted)
UNIQUE_RESERVE = 5         # " (99)"
SOURCE_NOTE_NAME = "แหล่งที่มา.txt"

def safe_component(text: str, fallback: str) -> str
    # drop \ / : * ? " < > | and Unicode Cc/Cf; whitespace runs -> one space; strip;
    # strip trailing dots and spaces; Windows reserved names (CON, PRN, AUX, NUL, COM1-9, LPT1-9,
    # case-insensitive, with or without extension) get a "_" prefix; empty -> fallback
def truncate_title(text: str, limit: int) -> str
    # cut to <= limit code points without leaving a combining mark (category M*) as the first
    # character after the cut; rstrip spaces and dots
def plan_output(root: Path, title: str, video_id: str, suffix: str, ext: str) -> Path
    # t = safe_component(title, video_id)
    # n = min(TITLE_MAX, len(t), (PATH_LIMIT - (len(str(root)) + 1) - len(f" [{video_id}]") - 1 - TAIL_RESERVE - UNIQUE_RESERVE) // 2)
    # (amended at gate 1) cap = the path-budget term above (lengths in UTF-16 code units);
    # cap >= 8: folder = f"{truncate_title(t, min(TITLE_MAX, cap))} [{video_id}]", file likewise.
    #           A short title such as "Hi" keeps its name; it does NOT fall back to the videoId.
    # cap < 8, or truncation leaves "": folder = video_id, file = f"{video_id}{suffix}.{ext}"
    # still longer than PATH_LIMIT - UNIQUE_RESERVE -> YtError("E_OUTPUT_NOT_WRITABLE", "path too long")
    # The folder name depends only on (root, title, video_id), so every job of a clip shares one folder.
def unique_path(path: Path) -> Path      # path, then "<stem> (2)<ext>" ... "(99)"; all taken -> YtError("E_OUTPUT_NOT_WRITABLE")
def move_into_place(src: Path, planned: Path) -> Path   # mkdir parents; unique_path; os.replace, or shutil.move across volumes; returns final path
def ensure_output_root(root: Path) -> None   # mkdir + write probe; failure -> YtError("E_OUTPUT_NOT_WRITABLE", str(err))

@dataclass(frozen=True)
class SourceInfo:
    title: str; channel: str; video_id: str; published: str | None; license: str | None
def credit_line(title: str, channel: str, video_id: str) -> str
    # "ที่มา: {title} — {channel} (YouTube) https://youtu.be/{video_id}"
def source_note_text(info: SourceInfo, downloaded_at: datetime) -> str
def write_source_note(folder: Path, info: SourceInfo, downloaded_at: datetime) -> Path
    # atomic (temp file + os.replace) under a per-folder lock; one file per folder, overwritten
```
`source_note_text` (lines joined with `\r\n`, file ends with `\r\n`; date-time in +07:00):
```
แหล่งที่มา
ชื่อคลิป: {title}
ช่อง: {channel}
ลิงก์: https://www.youtube.com/watch?v={video_id}
วันที่เผยแพร่: {published YYYY-MM-DD or ไม่ระบุ}
วันที่โหลด: {YYYY-MM-DD HH:MM} (+07:00)
สัญญาอนุญาต: {license or ไม่ระบุ}

เครดิตพร้อมใช้:
{credit_line(...)}

ข้อความนี้เป็นข้อมูลอ้างอิงแหล่งที่มาเท่านั้น ไม่ได้แปลว่าได้รับอนุญาตให้ใช้เนื้อหา
```
File names per kind (handlers, T10): video `"<t>.mp4"`, no audio `"<t> (ไม่มีเสียง).mp4"`; audio `"<t>.m4a" | ".mp3" | ".wav"`; subtitle `"<t>.<lang>.<fmt>"` (BRD #50); contact sheet `"<t> - contact sheet.jpg"`; zip `"<t> - frames.zip"`.

### C11. Error codes, messages and HTTP statuses (`core/yterrors.py` T4, `api/videos.STATUS_BY_CODE` T12)
New or changed `MESSAGES` entries (verbatim):

| code | message | HTTP when it reaches the API directly |
|---|---|---|
| `E_BOT_CHECK` (changed, PRD 7 "ตั้งแต่ M4") | ยูทูปขอให้ยืนยันว่าไม่ใช่บอท พักคิวไว้ 10 นาทีก่อนนะ | 429 (unchanged) |
| `E_FFMPEG_MISSING` | ยังไม่มีโปรแกรมแปลงไฟล์ (ffmpeg) กด "โหลดใหม่" ในหน้าตรวจสุขภาพ | 409 (`POST /jobs`) |
| `E_DISK_FULL` | พื้นที่ไม่พอ ต้องมีว่างอย่างน้อย {size} (without a size: `MESSAGES_NO_PARAMS` "พื้นที่ไม่พอ ลบไฟล์หรือเลือกโฟลเดอร์อื่นในหน้าตั้งค่า", gate 1) | job only |
| `E_OUTPUT_NOT_WRITABLE` | บันทึกลงโฟลเดอร์นี้ไม่ได้ ลองเปลี่ยนโฟลเดอร์ในหน้าตั้งค่า | 422 (settings) |
| `E_INTERRUPTED` | งานหยุดกลางคันเพราะปิดโปรแกรม | job only |
| `E_JOB_STATE` (new) | งานนี้เปลี่ยนสถานะไปแล้ว ลองรีเฟรชหน้าเว็บ | 409 |
| `E_YT_REFUSED` (new, Q2) | ยูทูปไม่ยอมส่งไฟล์ของคลิปนี้ตอนนี้ ลองใหม่ภายหลัง | 502 |

`E_NETWORK` keeps "เน็ตหลุด ลองใหม่อีกครั้ง"; the counter text "เน็ตหลุด กำลังลองใหม่ (ครั้งที่ n/3)" is a web string built from `Job.attempt`.

`YtError` gains a keyword `params: Mapping[str, str] | None = None`; `message` = `MESSAGES[code].format_map(params)` when params are given (`E_DISK_FULL` uses `{"size": "<n> GB|MB"}`).

`classify` gains, after `E_VIDEO_UNAVAILABLE` and before `E_NETWORK`, a regex rule: `http error 4(?!29)\d\d` → `E_YT_REFUSED` (429 is already `E_BOT_CHECK` earlier). This fixes the M2 follow-up (4xx other than 429 must not be retried). `extractor.fetch_subtitle` keeps its own status mapping (403/404/410 → `E_NETWORK` → re-probe), unchanged.

### C12. Web contracts (T8 writes them; T13-T17 and T19 consume them)
`web/src/lib/types.ts` adds C2, C3, and:
```ts
export type QueueState = { pausedUntil: string | null; reason: string | null; concurrency: 1 | 2 | 3 }
export type Settings = {
  outputDir: string; videoDefault: "compat-1080" | "compat-720" | "max"; audioDefault: "m4a" | "mp3" | "wav"
  audioLanguage: string; mp3Kbps: 128 | 192 | 320; subPreset: SubPreset | "custom"; subCustom: SubOptions
  concurrency: 1 | 2 | 3; sponsorblockDefault: string[]; theme: "system" | "dark" | "light"
  filenameStyle: "title" | "title-channel" | "title-quality"
  cookies: { enabled: boolean; source: "file" | "firefox" | null; warningAccepted: boolean; importedAt?: string }
  statsResetAt: string | null; lastUsed: Record<string, unknown>
}
// VideoInfo gains: license?: string ; AudioFormat gains: sampleRate?: number; channels?: number
// HistoryItem.outputs becomes JobKind[]
```
`web/src/lib/jobs.ts`:
```ts
export const JOBS_KEY = ["jobs"] as const
export const QUEUE_KEY = ["queue"] as const
export function jobsQuery(): { queryKey: typeof JOBS_KEY; queryFn: () => Promise<Job[]> }
export function queueQuery(): { queryKey: typeof QUEUE_KEY; queryFn: () => Promise<QueueState> }
export function enqueueJobs(items: NewJob[]): Promise<Job[]>
export function cancelJob(id: string): Promise<Job>
export function retryJob(id: string): Promise<Job>
export function reorderJobs(ids: string[]): Promise<void>
export function resumeQueue(): Promise<void>
export function revealOutput(id: string, index: number): Promise<void>
export const outputUrl = (id: string, index: number) => `/api/jobs/${id}/outputs/${index}`
export function upsertJob(jobs: readonly Job[], job: Job): Job[]
export function mergeJobPatch(jobs: readonly Job[], patch: JobPatch): Job[]   // unknown id -> same array; null -> key removed
export type SheetGroups = { running: Job[]; queued: Job[]; failed: Job[]; done: Job[] }
export function groupForSheet(jobs: readonly Job[]): SheetGroups
  // running by startedAt asc · queued by position asc · failed = failed + interrupted by finishedAt desc
  // done by finishedAt desc, first 20 · cancelled dropped
export type BarSummary = { visible: boolean; current: Job | null; running: number; queued: number; done: number; failed: number }
export function barSummary(jobs: readonly Job[]): BarSummary   // visible = any non-cancelled job; current = latest-started running job
export type EnqueueMessages = { added: string; addedMany: string; failed: string; goHealth: string }
export function useEnqueue(messages: EnqueueMessages): { enqueue: (items: NewJob[]) => Promise<boolean>; pending: boolean }
  // UI tasks pass th.queue.{added, addedMany, addFailed, goHealth}. toast added (1 job) / addedMany ({n});
  // 409 E_FFMPEG_MISSING -> toast.error(error.message, action goHealth -> /settings/health);
  // other errors -> toast.error(error.message || failed); seeds the JOBS_KEY cache with the returned jobs
```
`web/src/lib/events.ts`:
```ts
export type ServerEvent =
  | { type: "job.created"; job: Job } | { type: "job.updated"; patch: JobPatch }
  | { type: "queue.paused"; until: string; reason: string } | { type: "queue.resumed" } | { type: "app.shutdown" }
export function parseServerEvent(name: string, data: string): ServerEvent | null
export function applyServerEvent(client: QueryClient, event: ServerEvent): { before?: Job; after?: Job }
export function connectEvents(client: QueryClient, opts: {
  onShutdown: () => void
  onJobChange?: (before: Job | undefined, after: Job) => void
  createSource?: (url: string) => EventSource
}): () => void    // EventSource("/api/events"); after a reconnect ("open" following "error") invalidates JOBS_KEY and QUEUE_KEY
export const appShutdown: { get(): boolean; set(): void; subscribe(fn: () => void): () => void }
export function useAppShutdown(): boolean
```
`web/src/lib/settings-api.ts`: `SETTINGS_KEY = ["settings"]`, `settingsQuery()`, `patchSettings(partial): Promise<Settings>`, `openOutputFolder(): Promise<void>`.

`web/src/lib/download-options.ts`:
```ts
export const AUTO_QUALITY = "auto"
export type QualityOption = { value: string; height: number; fps: number; codec: string; compat: boolean; sizeBytes?: number }
export function codecLabel(vcodec: string): string     // avc1* -> "H.264", vp09*/vp9 -> "VP9", av01* -> "AV1", else family upper-cased
export function qualityOptions(video: VideoInfo, maxQuality: boolean): QualityOption[]
  // !maxQuality: compat formats with height <= 1080; maxQuality: all; sorted height desc, fps desc; value = formatId
export type LanguageOption = { value: string; label: string }
export function audioLanguageOptions(video: VideoInfo, languageName: (tag: string) => string,
  labels: { original: string; originalUnknown: string }): LanguageOption[] | null
  // distinct languages (case-insensitive) of video.audio; < 2 -> null
  // first { value: "original", label: fill(labels.original, {lang: name of the original track's language})
  //   (labels.originalUnknown when unknown) }, then the other languages in first-seen order, value = tag
  // UI tasks pass th.download.{original, originalUnknown}
export function resolveAudioLanguage(options: LanguageOption[] | null, preferred: string): string
  // options null -> preferred (the backend falls back and notes it); preferred matches an option value by
  // equality or "<preferred>-" prefix -> that value; else "original"
export function wavBytes(durationS: number, sampleRate = 44100, channels = 2): number   // durationS * sampleRate * channels * 2
export function wavMegabytes(durationS: number, sampleRate?: number, channels?: number): number   // Math.round(wavBytes / 1e6)
export function videoSizeEstimate(video: VideoInfo, quality: string, noAudio: boolean): number | undefined
export function batchMinutes(count: number, concurrency: number): number   // Math.max(1, Math.ceil(count * 35 / concurrency / 60))
export function buildVideoParams(input: { quality: string; maxQuality: boolean; noAudio: boolean; audioLanguage: string;
  embedSubs: string | null; subOptions: SubOptions }): VideoJobParams
export function buildAudioParams(input: { format: "m4a" | "mp3" | "wav"; mp3Kbps: 128 | 192 | 320; audioLanguage: string }): AudioJobParams
export function paramsFromSettings(kind: "video" | "audio", s: Settings): VideoJobParams | AudioJobParams   // W3 defaults
```
`web/src/lib/download-prefs.ts` (localStorage `yt-toolkit.download`, `v: 1`; storage failures fall back to memory like `subs-settings.ts`):
```ts
export type DownloadPrefs = { v: 1; quality: "auto" | number; maxQuality: boolean; noAudio: boolean
  audioFormat: "m4a" | "mp3" | "wav"; mp3Kbps: 128 | 192 | 320; audioLanguage: string }
export const DOWNLOAD_PREFS_KEY = "yt-toolkit.download"
export function prefsFromSettings(s: Settings | undefined): DownloadPrefs
export function parsePrefs(raw: string | null, fallback: DownloadPrefs): DownloadPrefs
export function createPrefsStore(getStorage: () => Storage | null): { get(fallback): DownloadPrefs; set(patch: Partial<DownloadPrefs>): void; subscribe(fn): () => void }
export const downloadPrefs: ReturnType<typeof createPrefsStore>
export function useDownloadPrefs(fallback: DownloadPrefs): [DownloadPrefs, (patch: Partial<DownloadPrefs>) => void]
```
`quality` remembers a height, not a format id: on another clip the W2 tab uses the option with that height when it exists, else "auto".

URL state (T15): `VideoTab = "frames" | "video" | "audio" | "subs" | "transcript" | "info"`; `VIDEO_TABS` in that order; default still `frames`.

### C13. Thai strings (T7 writes them into `web/src/i18n/th.ts` verbatim; nobody else edits `th.ts`)
Additions to existing objects:
```ts
nav: { history: "ประวัติ" }
video: {
  tabs: { video: "วิดีโอ", audio: "เสียง" },
  info: { creditTitle: "เครดิต", copyCredit: "คัดลอกเครดิต", creditLine: "ที่มา: {title} — {channel} (YouTube) https://youtu.be/{id}" },
}
settings: { tabs: { general: "ทั่วไป" } }
shutdown: {
  confirmTitle: "ปิดโปรแกรมตอนนี้?",
  confirmBody: "มีงานค้าง {n} งาน ถ้าปิดตอนนี้จะหยุดกลางคัน และลองใหม่ได้ทีหลัง",
  back: "กลับไปก่อน",
  force: "ปิดเลย",
}
```
New top-level objects:
```ts
download: {
  video: {
    title: "วิดีโอ",
    quality: "คุณภาพ",
    auto: "เปิดได้ทุกที่ สูงสุด 1080p (แนะนำ)",
    option: "{height}p · {fps} fps · {codec}",
    optionSize: "{height}p · {fps} fps · {codec} · ประมาณ {size}",
    maxQuality: "ความละเอียดสูงสุด",
    maxQualityHint: "ได้ถึง 4K หรือ 8K แต่เป็นไฟล์ VP9 หรือ AV1 ที่โปรแกรมตัดต่อบางตัวเปิดไม่ได้",
    notCompat: "บางโปรแกรมเปิดไม่ได้",
    noAudio: "ไม่เอาเสียง",
    noAudioHint: "ได้ไฟล์ภาพอย่างเดียว ชื่อไฟล์ลงท้ายด้วย (ไม่มีเสียง)",
    embedSubs: "ฝังซับ (เปิด/ปิดได้)",
    embedNone: "ไม่ฝัง",
    embedNoSubs: "คลิปนี้ไม่มีซับให้ฝัง",
    embedHint: "ผู้ชมเปิดหรือปิดซับได้จากโปรแกรมเล่น ความยาวซับตามที่ตั้งไว้ในแท็บซับ",
    estimate: "ขนาดประมาณ {size}",
    download: "โหลด mp4",
  },
  audio: {
    title: "เสียง",
    format: "รูปแบบไฟล์",
    formats: { m4a: "m4a (แนะนำ)", mp3: "mp3", wav: "wav" },
    m4aHint: "เร็วกว่าและเสียงดีกว่า",
    mp3Hint: "เปิดได้ทุกเครื่อง แต่ต้องแปลงไฟล์จึงช้ากว่า m4a",
    mp3Bitrate: "คุณภาพ mp3",
    kbps: "{n} kbps",
    wavSize: "ไฟล์ไม่บีบอัด ขนาดประมาณ {mb} MB",
    download: "โหลดเสียง",
  },
  audioLanguage: "ภาษาเสียง",
  original: "ต้นฉบับ ({lang})",
  originalUnknown: "ต้นฉบับ",
  languageDisabled: "ปิด 'ไม่เอาเสียง' ก่อนถึงจะเลือกภาษาเสียงได้",
  loading: "กำลังโหลดตัวเลือกการโหลด",
  noFormats: "คลิปนี้ไม่มีไฟล์ให้โหลด",
},
queue: {
  region: "คิวงาน",
  open: "เปิดคิวงาน",
  close: "ปิดคิวงาน",
  counts: "กำลังทำ {running} · รอ {queued} · เสร็จ {done}",
  sheetTitle: "คิวงาน",
  sheetHint: "ปิดแท็บนี้ได้ งานยังทำต่อ",
  groups: { running: "กำลังทำ", queued: "รอ", failed: "ผิดพลาด", done: "เสร็จแล้ว" },
  stages: { probing: "ดึงข้อมูล", downloading_video: "โหลดภาพ", downloading_audio: "โหลดเสียง", merging: "รวมไฟล์", converting: "แปลงไฟล์", writing: "บันทึกไฟล์" },
  starting: "กำลังเริ่ม",
  waiting: "รอคิว",
  percent: "{n}%",
  speed: "{size}/วินาที",
  eta: "เหลือ {time}",
  retrying: "เน็ตหลุด กำลังลองใหม่ (ครั้งที่ {n}/3)",
  cancelling: "กำลังยกเลิก",
  interrupted: "หยุดกลางคัน",
  cancel: "ยกเลิก",
  cancelJob: "ยกเลิกงาน {title}",
  retry: "ลองใหม่",
  retryJob: "ลองใหม่ {title}",
  openFolder: "เปิดโฟลเดอร์",
  openFolderOf: "เปิดโฟลเดอร์ของ {title}",
  download: "ดาวน์โหลด",
  downloadOf: "ดาวน์โหลด {file}",
  details: "ดูรายละเอียด",
  errorCode: "รหัส {code}",
  copyDetails: "คัดลอกรายละเอียด",
  dragHandle: "ลากเพื่อเปลี่ยนลำดับ {title}",
  dnd: {
    picked: "ยก {title} ขึ้นแล้ว กดลูกศรขึ้นหรือลงเพื่อย้าย แล้วกด Space เพื่อวาง",
    moved: "{title} อยู่ลำดับที่ {n}",
    dropped: "วาง {title} ไว้ลำดับที่ {n}",
    cancelled: "ยกเลิกการย้าย {title}",
  },
  paused: {
    title: "พักคิวไว้ชั่วคราว",
    body: "ยูทูปขอให้ยืนยันว่าไม่ใช่บอท คิวจะเริ่มต่อเองในอีก {time}",
    resume: "ลองต่อเลย",
  },
  kinds: { video: "วิดีโอ", audio: "เสียง", subtitle: "ซับ", frames_sharp: "ภาพคม", contact_sheet: "ภาพรวมเฟรม", frames_zip: "ภาพเฟรม (.zip)" },
  added: "เพิ่มเข้าคิวแล้ว",
  addedMany: "เพิ่มเข้าคิวแล้ว {n} งาน",
  addFailed: "เพิ่มเข้าคิวไม่สำเร็จ ลองอีกครั้ง",
  finished: "โหลดเสร็จแล้ว · {title}",
  failed: "โหลดไม่สำเร็จ · {title}",
  goHealth: "ไปหน้าตรวจสุขภาพ",
  fileMissing: "ไม่พบไฟล์ อาจถูกย้ายหรือลบไปแล้ว",
  revealFailed: "เปิดโฟลเดอร์ไม่สำเร็จ",
  actionFailed: "ทำรายการนี้ไม่สำเร็จ ลองรีเฟรชหน้าเว็บ",
},
batch: {
  pageTitle: "เลือกคลิป · {app}",
  crumb: "เลือกคลิป",
  multiTitle: "หลายลิงก์",
  counts: "ทั้งหมด {total} คลิป · เลือกแล้ว {selected} คลิป",
  selectAll: "เลือกทั้งหมด",
  selectRow: "เลือก {title}",
  columns: { select: "เลือก", thumb: "ปก", title: "ชื่อคลิป", duration: "ความยาว" },
  invalidRow: "ลิงก์นี้อ่านไม่ออก",
  playlistsNote: "เพลย์ลิสต์ในรายการนี้เลือกคลิปได้จากปุ่มในแถวของเพลย์ลิสต์ที่หน้าแรก",
  what: "โหลดอะไร",
  whats: { video: "วิดีโอ (mp4)", audio: "เสียง", none: "ไม่เอา" },
  subs: "ซับ",
  subsNone: "ไม่เอา",
  submit: "ส่งเข้าคิว {n} คลิป",
  nothing: "เลือกคลิป และเลือกวิดีโอ เสียง หรือซับอย่างน้อยหนึ่งอย่าง",
  confirmTitle: "ส่ง {n} คลิปเข้าคิว?",
  confirmBody: "ใช้เวลาประมาณ {minutes} นาที ถ้าโหลดเยอะติดกัน ยูทูปอาจขอยืนยันว่าไม่ใช่บอท",
  confirmCancel: "ยกเลิก",
  confirmOk: "ส่งเข้าคิว",
  expired: "รายการนี้ไม่อยู่แล้ว วางลิงก์ใหม่ที่หน้าแรก",
  open: "เลือกคลิปที่จะโหลด",
  loading: "กำลังโหลดรายการคลิป",
  loadError: "โหลดรายการคลิปไม่สำเร็จ",
},
history: {
  title: "ประวัติ",
  pageTitle: "ประวัติ · {app}",
  search: "ค้นหาจากชื่อคลิป",
  clearSearch: "ล้างคำค้น",
  columns: { thumb: "ปก", title: "ชื่อคลิป", outputs: "ไฟล์ที่ได้", time: "เวลา" },
  kinds: { video: "วิดีโอ", audio: "เสียง", subtitle: "ซับ", contact_sheet: "ภาพ", frames_zip: "ภาพ", frames_sharp: "ภาพ" },
  empty: "ยังไม่มีประวัติ",
  emptyHint: "คลิปที่เปิดดูหรือโหลดจะขึ้นที่นี่",
  noMatch: "ไม่พบคลิปที่ตรงกับ “{q}”",
  more: "แสดงเพิ่ม",
  shown: "แสดง {n} จาก {total} คลิป",
  loadError: "โหลดประวัติไม่สำเร็จ",
},
general: {
  outputDir: "โฟลเดอร์ผลลัพธ์",
  outputDirHint: "ไฟล์ที่โหลดจะอยู่ในโฟลเดอร์ย่อยตามชื่อคลิป วางที่อยู่โฟลเดอร์แล้วกด Enter",
  openOutput: "เปิดโฟลเดอร์",
  concurrency: "จำนวนงานพร้อมกัน",
  concurrencyHint: "ตั้งมากกว่า 2 งาน ยูทูปอาจขอยืนยันว่าไม่ใช่บอทบ่อยขึ้น",
  audioLanguage: "ภาษาเสียงเริ่มต้น",
  audioLanguageHint: "ใช้เมื่อคลิปมีเสียงพากย์ภาษานั้น ถ้าไม่มีจะใช้เสียงต้นฉบับ",
  languages: { original: "ต้นฉบับ", th: "ไทย", en: "อังกฤษ", ja: "ญี่ปุ่น", ko: "เกาหลี", zh: "จีน", es: "สเปน", fr: "ฝรั่งเศส", de: "เยอรมัน", pt: "โปรตุเกส", hi: "ฮินดี", id: "อินโดนีเซีย" },
  videoDefault: "คุณภาพวิดีโอเริ่มต้น",
  videoDefaults: { "compat-1080": "เปิดได้ทุกที่ 1080p", "compat-720": "เปิดได้ทุกที่ 720p", max: "ความละเอียดสูงสุด" },
  audioDefault: "รูปแบบเสียงเริ่มต้น",
  saved: "บันทึกแล้ว",
  saveFailed: "บันทึกไม่สำเร็จ ลองอีกครั้ง",
  loadError: "โหลดค่าตั้งไม่สำเร็จ",
},
```

### C14. E2E projects and fake behaviours
- `web/playwright.config.ts` (T7): `PORT = Number(process.env.E2E_PORT ?? 8799)`, `QUEUE_PORT = PORT + 1`. Two `webServer` entries (same command and env as today, the second with `--port ${QUEUE_PORT}` and data root `…e2e-queue[-<PORT>]`). Projects: `chromium` (`baseURL` PORT, `testIgnore: /queue-.*\.spec\.ts/`) and `queue` (`baseURL` QUEUE_PORT, `testMatch: /queue-.*\.spec\.ts/`). `web/package.json`: `"e2e": "playwright test --project=chromium && playwright test --project=queue --workers=1 --pass-with-no-tests"`. Parallel runs with `E2E_PORT` must be at least 2 apart.
- `web/e2e/queue-helpers.ts` (T8):
  ```ts
  export async function listJobs(request: APIRequestContext, status?: JobStatus): Promise<Job[]>
  export async function waitForJob(request: APIRequestContext, match: (job: Job) => boolean, opts?: { timeout?: number }): Promise<Job>
  export async function cancelJobsFor(request: APIRequestContext, videoIds: string[]): Promise<void>  // POST cancel for queued/running jobs of those clips
  export async function resumeQueue(request: APIRequestContext): Promise<void>
  export async function openQueueSheet(page: Page): Promise<Locator>      // clicks the bar, returns the sheet dialog
  export function mockEnqueue(page: Page): Promise<{ bodies: NewJob[][] }> // chromium-project helper: fulfils POST /api/jobs with fake queued jobs and records bodies
  ```
  Mutating requests from `request` need `X-Toolkit-Token` (read from the page's `<meta name="yt-token">`) and `Origin`; the helpers take the token from `page` via a `token(page)` helper in the same file.
- `tests/fixtures/downloads/behaviors.json` (T9):
  ```json
  {
    "default": {"steps": 6, "stepMs": 120},
    "videos": {
      "SLOWDOWNLD1": {"probeAs": "aqz-KE-bpKQ", "title": "คลิปโหลดช้า 1", "steps": 40, "stepMs": 250},
      "SLOWDOWNLD2": {"probeAs": "aqz-KE-bpKQ", "title": "คลิปโหลดช้า 2", "steps": 40, "stepMs": 250},
      "SLOWDOWNLD3": {"probeAs": "aqz-KE-bpKQ", "title": "คลิปโหลดช้า 3", "steps": 40, "stepMs": 250},
      "SLOWDOWNLD4": {"probeAs": "aqz-KE-bpKQ", "title": "คลิปโหลดช้า 4", "steps": 40, "stepMs": 250},
      "BOTCHECKDL1": {"probeAs": "aqz-KE-bpKQ", "title": "คลิปติดบอท", "steps": 6, "stepMs": 120, "failAtStep": 2, "error": "E_BOT_CHECK", "failTimes": 1},
      "NETRETRYDL1": {"probeAs": "aqz-KE-bpKQ", "title": "คลิปเน็ตหลุด", "steps": 6, "stepMs": 120, "failAtStep": 1, "error": "E_NETWORK", "failTimes": 1},
      "REFUSEDDL01": {"probeAs": "aqz-KE-bpKQ", "title": "คลิปที่ยูทูปไม่ส่งไฟล์", "steps": 6, "stepMs": 120, "failAtStep": 0, "error": "E_YT_REFUSED", "failTimes": 99}
    }
  }
  ```
  `FakeExtractor.probe(id)` for an id listed under `videos` with `probeAs` loads that fixture, sets `id` and (when given) `title`.
- **Which spec uses which clip** (avoid cross-file interference in the `queue` project): T14 `queue-flow.spec.ts` → `SLOWDOWNLD1..4`, `BOTCHECKDL1`, `NETRETRYDL1`, `REFUSEDDL01`; T15 `queue-download.spec.ts` → `aqz-KE-bpKQ`, `8lpOfyoxcvU`; T16 `queue-files.spec.ts` → `88o5Sk8_m1Y`, `OWNERTHSUB1`; T13 `queue-history.spec.ts` → `jNQXAC9IVRw`; T19 `queue-batch.spec.ts` → `VTTFALLBAK1`, `NOORIGSUB01`, `LONGTHAI1hr` (multi-link list) and `PLfakeplaylist250` (dialog only, never submitted).

### C15. History API (`core/videos.recent`, `api/videos.py`, T12)
`GET /history?q=&limit=&offset=&scope=all|opened` (default `all`): `{items: [{videoId, title, thumbnailUrl, durationS, outputs: JobKind[], lastAt}], total}`.
- `scope=opened`: clips opened in W2 (`opened_at != PEEK_SENTINEL`), `lastAt = opened_at` (W1 "ล่าสุด", unchanged behaviour).
- `scope=all`: clips opened in W2 **or** with at least one `done` job that has an output; `lastAt = max(opened_at if opened, max finished_at of done jobs)`; sorted `lastAt` desc, then `video_id`.
- `outputs` (both scopes): distinct kinds of `done` jobs with ≥ 1 output, in the order `video, audio, subtitle, contact_sheet, frames_zip`.
- `q` matches `videos.title` (`LIKE` with the existing escaping). Unknown `scope` → 422.

---

## File structure

**Backend (new):**
- `src/yttoolkit/core/jobs.py` (T1) job model, store, transitions, notes, uuid7
- `src/yttoolkit/core/settings.py` (T2) settings store
- `src/yttoolkit/api/settings.py` (T2) `/settings`, `/settings/open-output`
- `src/yttoolkit/core/files.py` (T3) output names, folders, `แหล่งที่มา.txt`
- `src/yttoolkit/core/download.py` (T4) format chooser, download contract types, kind sets
- `src/yttoolkit/core/media.py` (T5) ffmpeg argument builders, runner, fake media tools, `iso639_2`
- `src/yttoolkit/core/cancel.py` (T5) `JobCancelled`
- `src/yttoolkit/core/events.py` (T6), `src/yttoolkit/api/events.py` (T6)
- `src/yttoolkit/core/handlers.py` (T10) job handlers
- `src/yttoolkit/core/queue.py` (T11), `src/yttoolkit/api/jobs.py` (T11)

**Backend (modified):** `core/db.py` (T1), `app.py` (T2, T11), `api/routes.py` (T2), `core/videos.py` (T4, T12), `core/yterrors.py` (T4), `core/extractor.py` (T9), `api/videos.py` + `api/subtitles.py` (T12), `api/errors.py` (T11), `lifecycle.py` (T2, T18), `tray.py` (T18).

**Web (new):** `lib/jobs.ts`, `lib/events.ts`, `lib/settings-api.ts`, `lib/download-options.ts`, `lib/download-prefs.ts` (T8) · `components/ui/{sheet,progress,alert-dialog,checkbox,table}.tsx` (T7) · `components/queue/*` (T14) · `pages/video/download/*` (T15) · `pages/history.tsx`, `pages/history/*` (T13) · `pages/settings/general-panel.tsx` (T17) · `pages/batch.tsx`, `pages/batch/*` (T19).

**Fixtures:** `tests/fixtures/media/{video.mp4,video-noaudio.mp4,audio.m4a,audio.mp3,audio.wav,cover.jpg}` (T5) · `tests/fixtures/downloads/behaviors.json` (T9) · `tests/fixtures/errors/E_YT_REFUSED-1.txt` (T4).

---

## Wave 1

### Task 1: Job store and schema v2

**Files:**
- Modify: `src/yttoolkit/core/db.py`
- Create: `src/yttoolkit/core/jobs.py`
- Modify: `tests/unit/test_db.py`
- Create: `tests/unit/test_jobs_store.py`

**Interfaces:**
- Consumes: `Database` (existing).
- Produces: everything in C1 except `JobCancelled` (`JobStore`, `Job`, `NewJob`, `JobResult`, `OutputFile`, `JobContext`, `Handler`, `InvalidTransition`, `NOTES`, `TRANSITIONS`, `uuid7`, `SCHEMA_VERSION = 2`).

- [ ] **Step 1: Write the failing schema tests** (append to `tests/unit/test_db.py`)

```python
V1_JOBS = """CREATE TABLE schema_version (version INTEGER NOT NULL);
CREATE TABLE videos (video_id TEXT PRIMARY KEY, title TEXT NOT NULL, channel TEXT, duration_s INTEGER,
  thumbnail_url TEXT, chapters_json TEXT, probe_json TEXT NOT NULL, probed_at TEXT NOT NULL, opened_at TEXT NOT NULL);
CREATE TABLE jobs (id TEXT PRIMARY KEY, video_id TEXT NOT NULL REFERENCES videos(video_id), kind TEXT NOT NULL,
  params_json TEXT NOT NULL, status TEXT NOT NULL, stage TEXT, progress REAL, speed_bps INTEGER, eta_s INTEGER,
  position INTEGER NOT NULL, error_code TEXT, error_detail TEXT, outputs_json TEXT, created_at TEXT NOT NULL,
  started_at TEXT, finished_at TEXT);
CREATE INDEX jobs_status_position ON jobs(status, position);
CREATE TABLE settings (key TEXT PRIMARY KEY, value_json TEXT NOT NULL);
INSERT INTO schema_version (version) VALUES (1);"""


def test_fresh_database_is_v2_without_job_foreign_key(tmp_path):
    db = Database(tmp_path / "app.db")
    db.migrate()
    assert db.execute("SELECT max(version) AS v FROM schema_version")[0]["v"] == 2
    db.execute(
        "INSERT INTO jobs (id, video_id, kind, params_json, status, position, created_at) "
        "VALUES ('j1', 'notprobed01', 'video', '{}', 'queued', 1, '2026-10-01T00:00:00+00:00')"
    )
    cols = {r["name"] for r in db.execute("PRAGMA table_info(jobs)")}
    assert {"title", "attempt", "bot_checks", "error_message", "notes_json"} <= cols


def test_v1_database_migrates_and_keeps_rows(tmp_path):
    import sqlite3
    raw = sqlite3.connect(tmp_path / "app.db")
    raw.executescript(V1_JOBS)
    raw.execute("INSERT INTO videos VALUES ('aqz-KE-bpKQ','t',NULL,NULL,NULL,NULL,'{}','x','x')")
    raw.execute("INSERT INTO jobs (id, video_id, kind, params_json, status, position, created_at) "
                "VALUES ('old', 'aqz-KE-bpKQ', 'video', '{}', 'done', 3, 'x')")
    raw.commit(); raw.close()
    db = Database(tmp_path / "app.db")
    db.migrate()
    row = db.execute("SELECT * FROM jobs WHERE id = 'old'")[0]
    assert (row["status"], row["position"], row["title"], row["attempt"]) == ("done", 3, "", 0)
    assert db.execute("SELECT max(version) AS v FROM schema_version")[0]["v"] == 2
    assert not db.execute("SELECT 1 FROM sqlite_master WHERE name = 'jobs_v1'")
```

- [ ] **Step 2: Run them, expect FAIL** — `uv run pytest tests/unit/test_db.py -q -W error` (version is still 1).
- [ ] **Step 3: Implement schema v2 and the v1 → v2 migration in `core/db.py`** exactly as C1 (one `executescript("BEGIN; … COMMIT;")`; keep the "newer than this program" error). Existing `purge_stale_cache` stays unchanged (it already skips clips that have jobs).
- [ ] **Step 4: Write the failing store tests** in `tests/unit/test_jobs_store.py`:

```python
from datetime import UTC, datetime, timedelta
import pytest
from yttoolkit.core.db import Database
from yttoolkit.core.jobs import InvalidTransition, JobStore, NewJob, OutputFile, uuid7

NOW = datetime(2026, 10, 1, 12, 0, tzinfo=UTC)

@pytest.fixture
def store(tmp_path):
    db = Database(tmp_path / "app.db"); db.migrate()
    clock = {"now": NOW}
    s = JobStore(db, now=lambda: clock["now"])
    s.clock = clock
    return s

def add(store, n=1, kind="video"):
    return store.add([NewJob(f"vid{i:08d}", kind, {"maxQuality": False}, f"คลิป {i}") for i in range(n)])

def test_add_appends_positions_in_order(store):
    jobs = add(store, 3)
    assert [j.position for j in jobs] == [1, 2, 3]
    assert all(j.status == "queued" for j in jobs)
    assert [j.id for j in store.queued()] == [j.id for j in jobs]

def test_transition_rules(store):
    (job,) = add(store)
    running = store.transition(job.id, "running")
    assert running.started_at is not None
    with pytest.raises(InvalidTransition):
        store.transition(job.id, "running")          # running -> running is not a transition
    done = store.transition(job.id, "done", outputs=(OutputFile("C:/out", "a [x]/a.mp4", 10, "video"),), notes=("NO_SUBTITLES",))
    assert done.finished_at is not None and done.outputs[0].rel == "a [x]/a.mp4"
    with pytest.raises(InvalidTransition):
        store.transition(job.id, "queued")

def test_requeue_front_and_end(store):
    a, b, c = add(store, 3)
    store.transition(c.id, "running")
    front = store.requeue(c.id, front=True)
    assert front.status == "queued" and front.position < a.position
    store.transition(front.id, "running"); store.transition(front.id, "failed", error_code="E_NETWORK")
    end = store.requeue(front.id)
    assert end.position > b.position and end.error_code is None

def test_reorder_reuses_existing_slots(store):
    a, b, c, d = add(store, 4)
    store.reorder([d.id, b.id, "unknown"])
    order = [j.id for j in store.queued()]
    assert order == [a.id, d.id, c.id, b.id]

def test_interrupt_running_and_pending(store):
    a, b = add(store, 2)
    store.transition(a.id, "running")
    assert store.pending_count() == 2
    assert store.interrupt_running("งานหยุดกลางคันเพราะปิดโปรแกรม") == 1
    got = store.get(a.id)
    assert (got.status, got.error_code) == ("interrupted", "E_INTERRUPTED")
    assert store.pending_count() == 1

def test_default_list_windows(store):
    a, b, c = add(store, 3)
    for j in (a, b):
        store.transition(j.id, "running")
    store.transition(a.id, "done")
    store.clock["now"] = NOW + timedelta(hours=25)
    store.transition(b.id, "cancelled")
    ids = {j.id for j in store.list_default()}
    assert ids == {c.id}          # done older than 24 h and cancelled are hidden

def test_to_api_shape(store):
    (job,) = add(store)
    api = store.get(job.id).to_api()
    assert api == {"id": job.id, "videoId": "vid00000000", "title": "คลิป 0", "kind": "video",
                   "params": {"maxQuality": False}, "status": "queued", "position": 1, "createdAt": api["createdAt"]}

def test_uuid7_sorts_by_time():
    ids = [uuid7() for _ in range(50)]
    assert all(len(i) == 36 and i[14] == "7" for i in ids)
    assert ids == sorted(ids)
```

- [ ] **Step 5: Run, expect FAIL** (`ModuleNotFoundError: yttoolkit.core.jobs`).
- [ ] **Step 6: Implement `core/jobs.py`** per C1. All writes go through `db.transaction()`. `to_api()` builds the C2 dict; `outputs` become `[{"index": i, "name": PurePosixPath(rel).name, "sizeBytes": n}]`; `notes` become `[{"code", "message": NOTES[code]}]` (unknown codes are skipped); `error` = `{"code", "message", "detail"}`. `list_default` uses `now()` for the 24 h / 7 day windows.
- [ ] **Step 7: Run `uv run pytest tests/unit/test_db.py tests/unit/test_jobs_store.py -q -W error`, then the full suite. Expect PASS.**
- [ ] **Step 8: Commit** `feat(core): job store and schema v2 (jobs without FK, notes, retries)`.

### Task 2: Settings store, settings API, AppContext fields for M4

**Files:**
- Create: `src/yttoolkit/core/settings.py`, `src/yttoolkit/api/settings.py`
- Modify: `src/yttoolkit/app.py`, `src/yttoolkit/api/routes.py`
- Modify: `src/yttoolkit/lifecycle.py` (build `SettingsStore` in `open_services`; default output `plat.downloads_dir() / "YT-Toolkit"`, or `paths.data_root / "output"` in fake mode; set `ctx.settings`; in fake mode set `ctx.open_folder` and `ctx.reveal` to functions that only `log.info("โหมดข้อมูลปลอม: ไม่เปิดโฟลเดอร์")`), `tests/unit/test_lifecycle.py`
- Create: `tests/unit/test_settings.py`, `tests/api/test_settings_api.py`

**Interfaces:**
- Consumes: `Database`, `srt_builder.PRESETS` (for `subCustom`).
- Produces: C5 (`SettingsStore`, `SettingsError`, `build_settings_router(ctx)`), and these **AppContext fields** (all default `None`; annotated with `TYPE_CHECKING`-only imports so the modules may not exist yet):
  ```python
  settings: SettingsStore | None = None
  queue: QueueRunner | None = None        # core.queue (T11)
  events: EventBus | None = None          # core.events (T6)
  media: MediaTools | None = None         # core.media (T5)
  on_bot_check: Callable[[], None] | None = None
  reveal: Callable[[Path], None] | None = None
  open_folder: Callable[[Path], None] | None = None
  ```
  `create_app` includes the settings router when `ctx.settings` is set. `api/routes.py` `_health()` passes `ctx.settings.output_dir()` (when set) instead of `ctx.output_dir`.

- [ ] **Step 1: Failing unit tests** (`tests/unit/test_settings.py`): defaults equal the C5 table (with `outputDir == str(tmp/"out")`); `patch({"concurrency": 3})` persists across a new `SettingsStore` on the same DB; `patch({"concurrency": 4})`, `patch({"nope": 1})`, `patch({"cookies": {...}})`, `patch({"statsResetAt": "x"})`, `patch({"outputDir": "relative"})` raise `SettingsError` with code `E_BAD_REQUEST` and change nothing (check with a second key in the same patch, e.g. `{"concurrency": 1, "nope": 1}` leaves concurrency at 2); `patch({"outputDir": str(a_file)})` → `E_OUTPUT_NOT_WRITABLE`; `patch({"subPreset": "word"})` accepted; `get()` contains no cookie values beyond the C5 status fields.
- [ ] **Step 2: Run, expect FAIL.**
- [ ] **Step 3: Implement `core/settings.py`** (values stored as JSON in the `settings` table; a lock around read-modify-write).
- [ ] **Step 4: Failing API tests** (`tests/api/test_settings_api.py`, using `make_client(settings=SettingsStore(db, tmp/"out"))`): `GET /api/settings` 200 full shape; `PATCH` with `AUTH` 200 and persisted; `PATCH` without token → 403; invalid → 422 envelope with the right code; `POST /api/settings/open-output` calls the `open_folder` override with the output path (and `fake_platform.opened` when the override is None); `GET /api/health` → `output.path` equals the settings folder.
- [ ] **Step 5: Implement `api/settings.py`, the AppContext fields and the `create_app`/`routes.py` changes.**
- [ ] **Step 6: Failing lifecycle tests, then the wiring:** `open_services(paths, plat, fake=True)` returns a settings store whose `outputDir` default is `<data_root>/output`; real mode uses the platform's Downloads; the fake-mode `open_folder` override never calls the platform. (`open_services` gains a `plat` parameter; update its callers and the existing tests.) Run all tests. Expect PASS.
- [ ] **Step 7: Commit** `feat: settings store and API, M4 AppContext fields, settings wired into the app`.

### Task 3: Output files (`core/files.py`)

**Files:**
- Create: `src/yttoolkit/core/files.py`, `tests/unit/test_files.py`

**Interfaces:** Produces C10. Consumes `YtError` (existing; `E_OUTPUT_NOT_WRITABLE` gets its message from T4, the code works before that because `YtError.message` falls back to `E_UNKNOWN`).

- [ ] **Step 1: Failing tests** (`tests/unit/test_files.py`):

```python
from datetime import UTC, datetime
from pathlib import Path
from yttoolkit.core import files

ID = "dQw4w9WgXcQ"

def test_ac_out_01_forbidden_characters(tmp_path):
    p = files.plan_output(tmp_path, 'ทดสอบ: "A/B" <ภาค 1>?', ID, "", "mp4")
    assert p.parent.name == f"ทดสอบ AB ภาค 1 [{ID}]"
    assert p.name == "ทดสอบ AB ภาค 1.mp4"
    assert not set('\\/:*?"<>|') & set(p.parent.name + p.name)

def test_ac_out_02_long_title_fits_240(tmp_path):
    p = files.plan_output(tmp_path, "ก" * 300, ID, " (ไม่มีเสียง)", "mp4")
    assert len(str(p)) + files.UNIQUE_RESERVE <= files.PATH_LIMIT
    assert p.name.endswith(" (ไม่มีเสียง).mp4") and p.parent.name.endswith(f" [{ID}]")

def test_folder_is_shared_by_every_kind(tmp_path):
    title = "ก" * 300
    names = {files.plan_output(tmp_path, title, ID, s, e).parent.name
             for s, e in [("", "mp4"), (".th", "srt"), (" - contact sheet", "jpg"), ("", "wav")]}
    assert len(names) == 1

def test_truncation_never_splits_thai_marks():
    assert files.truncate_title("กี่", 1) == ""          # "ก" + mark: cut before the base, not between
    assert files.truncate_title("ทดสอบที่", 6) == "ทดสอบ"

def test_reserved_and_trailing(tmp_path):
    assert files.safe_component("CON", ID) == "_CON"
    assert files.safe_component("  ชื่อ...  ", ID) == "ชื่อ"
    assert files.safe_component("\u202e\x00", ID) == ID

def test_ac_out_03_unique_suffix(tmp_path):
    first = tmp_path / "a.mp4"; first.write_bytes(b"1")
    (tmp_path / "a (2).mp4").write_bytes(b"2")
    assert files.unique_path(first).name == "a (3).mp4"

def test_root_too_long_falls_back_to_id(tmp_path):
    deep = tmp_path / ("x" * max(1, 190 - len(str(tmp_path))))   # root of about 190 characters
    p = files.plan_output(deep, "ชื่อคลิปยาวพอสมควร", ID, "", "mp4")
    assert p.parent.name == ID and p.name == f"{ID}.mp4"

def test_ac_out_06_source_note_bytes(tmp_path):
    info = files.SourceInfo("คลิป", "ช่อง", ID, "2026-09-01", None)
    path = files.write_source_note(tmp_path, info, datetime(2026, 10, 5, 7, 32, tzinfo=UTC))
    data = path.read_bytes()
    assert not data.startswith(b"\xef\xbb\xbf") and b"\r\n" in data and b"\n" not in data.replace(b"\r\n", b"")
    text = data.decode("utf-8")
    assert "ลิงก์: https://www.youtube.com/watch?v=dQw4w9WgXcQ\r\n" in text
    assert "วันที่โหลด: 2026-10-05 14:32 (+07:00)\r\n" in text
    assert "สัญญาอนุญาต: ไม่ระบุ\r\n" in text                    # AC-OUT-07 (no license)
    assert "ที่มา: คลิป — ช่อง (YouTube) https://youtu.be/dQw4w9WgXcQ\r\n" in text

def test_ac_out_06_second_job_updates_one_file(tmp_path):
    lic = "Creative Commons Attribution license (reuse allowed)"
    files.write_source_note(tmp_path, files.SourceInfo("ค", "ช", ID, None, lic), datetime(2026, 10, 1, tzinfo=UTC))
    files.write_source_note(tmp_path, files.SourceInfo("ค", "ช", ID, None, lic), datetime(2026, 10, 2, tzinfo=UTC))
    notes = list(tmp_path.glob("แหล่งที่มา*.txt"))
    assert len(notes) == 1 and "2026-10-02" in notes[0].read_text("utf-8") and lic in notes[0].read_text("utf-8")

def test_move_into_place_creates_folder_and_uniquifies(tmp_path):
    src = tmp_path / "w" / "final.mp4"; src.parent.mkdir(); src.write_bytes(b"x")
    planned = tmp_path / "out" / "a [id]" / "a.mp4"
    planned.parent.mkdir(parents=True); planned.write_bytes(b"old")
    assert files.move_into_place(src, planned).name == "a (2).mp4"
```
- [ ] **Step 2: Run, expect FAIL.**
- [ ] **Step 3: Implement C10.** (`truncate_title("กี่", 1)`: the cut point after "ก" is followed by a mark, so back off to 0.)
- [ ] **Step 4: Run, expect PASS; run the full suite.**
- [ ] **Step 5: Commit** `feat(core): output file naming, folders and แหล่งที่มา.txt`.

### Task 4: Probe v5, format chooser, error codes

**Files:**
- Modify: `src/yttoolkit/core/videos.py` (PROBE_VERSION 5, `license`, `asr`, `audio_channels`)
- Create: `src/yttoolkit/core/download.py`
- Modify: `src/yttoolkit/core/yterrors.py`
- Modify: `tests/unit/test_videos.py`, `tests/unit/test_video_meta.py`, `tests/unit/test_yterrors.py`
- Create: `tests/unit/test_download_choice.py`
- Create: `tests/fixtures/errors/E_YT_REFUSED-1.txt` with `ERROR: unable to download video data: HTTP Error 403: Forbidden`
- Modify: `tests/fixtures/probe/88o5Sk8_m1Y.json` (add top-level `"license": "Creative Commons Attribution license (reuse allowed)"`; the README note is written by T5)

**Interfaces:**
- Produces: C8 types and functions (`DownloadChoice`, `DownloadHooks`, `DownloadResult`, `Downloader`, `pick_audio`, `video_choice`, `audio_choice`, `YOUTUBE_KINDS`, `FFMPEG_KINDS`); C11 messages and `classify` rule; `YtError(params=…)`; VideoInfo `license`; audio entries `sampleRate`/`channels`.
- Consumes: `core.videos._audio_formats`.

- [ ] **Step 1: Failing probe tests:** `trim_probe` keeps `license` (top level) and `asr`, `audio_channels` per audio format (add both to `_MEDIA_FIELDS`); `to_video_info` returns `license` when present and `sampleRate`/`channels` on audio entries when present; `PROBE_VERSION == 5` (rows of version 4 are re-probed, same mechanism as before).
- [ ] **Step 2: Failing chooser tests** (`tests/unit/test_download_choice.py`), loading fixtures through `FakeExtractor(FIXTURES).probe(id)`:

```python
from yttoolkit.core.download import audio_choice, pick_audio, video_choice
DUB = "8lpOfyoxcvU"; BBB = "aqz-KE-bpKQ"

def test_original_audio_is_default(fake):           # AC-VID-03/06 (original)
    info = fake.probe(DUB)
    aud, notes = pick_audio(info["formats"], "original", codec_prefix="mp4a")
    assert aud["format_id"] == "140-1" and aud["language"] == "th" and notes == ()

def test_dub_language_is_chosen(fake):              # AC-VID-05
    aud, notes = pick_audio(fake.probe(DUB)["formats"], "en", codec_prefix="mp4a")
    assert aud["language"] == "en-US" and notes == ()

def test_missing_language_falls_back_with_note(fake):   # AC-VID-06
    aud, notes = pick_audio(fake.probe(DUB)["formats"], "ja", codec_prefix="mp4a")
    assert aud["language"] == "th" and notes == ("AUDIO_LANG_FALLBACK",)

def test_compat_default_spec(fake):                 # AC-VID-01 selector
    c = video_choice(fake.probe(DUB), {"maxQuality": False, "noAudio": False, "audioLanguage": "original"})
    assert c.format_spec == "bv*[vcodec^=avc1][height<=1080]+140-1/b[ext=mp4]"
    assert c.merge_mp4 and c.audio_language == "th"

def test_no_audio_has_no_audio_part(fake):          # AC-VID-08 (U)
    c = video_choice(fake.probe(BBB), {"maxQuality": False, "noAudio": True, "audioLanguage": "original"})
    assert c.format_spec == "bv*[vcodec^=avc1][height<=1080]" and "+" not in c.format_spec and "ba" not in c.format_spec
    assert c.audio_language is None

def test_max_quality_and_format_id(fake):
    info = fake.probe(BBB)
    assert video_choice(info, {"maxQuality": True, "noAudio": False, "audioLanguage": "original"}).format_spec.startswith("bv*+")
    fid = next(f["format_id"] for f in info["formats"] if f.get("vcodec", "").startswith("avc1"))
    c = video_choice(info, {"formatId": fid, "maxQuality": False, "noAudio": False, "audioLanguage": "original"})
    assert c.format_spec.startswith(f"{fid}+") and "/" not in c.format_spec
    gone = video_choice(info, {"formatId": "999999", "maxQuality": False, "noAudio": False, "audioLanguage": "original"})
    assert "QUALITY_FALLBACK" in gone.notes and gone.format_spec.startswith("bv*[vcodec^=avc1]")

def test_audio_m4a_spec(fake):
    c = audio_choice(fake.probe(DUB), {"format": "m4a", "audioLanguage": "original"})
    assert c.format_spec == "140-1" and not c.merge_mp4
```
(`fake` is a fixture returning `FakeExtractor(FIXTURES)`; check the exact format ids against `8lpOfyoxcvU.json` while writing the test and use the real ones: the original mp4a medium track is the `140-1` entry.)
- [ ] **Step 3: Failing error tests** (`tests/unit/test_yterrors.py`): every file in `tests/fixtures/errors/` still classifies to its prefix (the existing loop now includes `E_YT_REFUSED-1.txt`); `classify("HTTP Error 404: Not Found") == "E_YT_REFUSED"`; `classify("... HTTP Error 429: Too Many Requests") == "E_BOT_CHECK"`; `MESSAGES` has the C11 strings verbatim (update the existing `E_BOT_CHECK` assertion to the M4 text); `YtError("E_DISK_FULL", "x", params={"size": "3.2 GB"}).message == "พื้นที่ไม่พอ ต้องมีว่างอย่างน้อย 3.2 GB"`.
- [ ] **Step 4: Run all three test files, expect FAIL.**
- [ ] **Step 5: Implement** `core/download.py` (C8; the types `DownloadHooks`, `DownloadResult`, `Downloader` live here so T9 and T10 share them), the `videos.py` changes and the `yterrors.py` changes.
- [ ] **Step 6: Run the full suite. Expect PASS** (fix any existing test that pinned `PROBE_VERSION == 4` or the old bot-check text).
- [ ] **Step 7: Commit** `feat(core): probe v5 (license, sample rate), format chooser, M4 error codes`.

### Task 5: Media tools, media fixtures, no-shell test

**Files:**
- Create: `src/yttoolkit/core/media.py`, `src/yttoolkit/core/cancel.py`
- Create: `tests/helpers_ffmpeg.py` (`find_test_ffmpeg() -> str | None` = `shutil.which("ffmpeg")`; `requires_ffmpeg = pytest.mark.skipif(find_test_ffmpeg() is None, reason="ต้องมี ffmpeg ในเครื่อง")`; `ffprobe_json(path) -> dict`)
- Create: `tests/unit/test_media_args.py`, `tests/integration/test_media_ffmpeg.py`, `tests/unit/test_no_shell.py`
- Create: `tests/fixtures/media/video.mp4`, `video-noaudio.mp4`, `audio.m4a`, `audio.mp3`, `audio.wav`, `cover.jpg`
- Modify: `tests/fixtures/README.md` (new sections "media/" with the exact generation commands, and the `license` note for `88o5Sk8_m1Y`)

**Interfaces:** Produces C9 (`MediaMeta`, `SubtitleInput`, `MediaTools`, `FfmpegTools`, `FakeMediaTools`, the four `*_args` builders, `run_ffmpeg`, `iso639_2`). Consumes `YtError`. Also creates `src/yttoolkit/core/cancel.py` with the single class `JobCancelled(Exception)` (docstring: raised when the user or shutdown cancels a job); T9, T10 and T11 import it from there.

- [ ] **Step 1: Generate the fixtures once** (commit the files; record these commands in `tests/fixtures/README.md`):
```bash
cd tests/fixtures/media
ffmpeg -hide_banner -y -f lavfi -i testsrc=size=160x90:rate=10 -f lavfi -i sine=frequency=440:sample_rate=44100 -t 2 -c:v libx264 -pix_fmt yuv420p -c:a aac -b:a 64k -shortest video.mp4
ffmpeg -hide_banner -y -f lavfi -i testsrc=size=160x90:rate=10 -t 2 -c:v libx264 -pix_fmt yuv420p video-noaudio.mp4
ffmpeg -hide_banner -y -f lavfi -i sine=frequency=440:sample_rate=44100 -t 2 -c:a aac -b:a 64k audio.m4a
ffmpeg -hide_banner -y -f lavfi -i sine=frequency=440:sample_rate=44100 -t 2 -c:a libmp3lame -b:a 128k audio.mp3
ffmpeg -hide_banner -y -f lavfi -i sine=frequency=440:sample_rate=22050 -t 0.5 -ac 1 -c:a pcm_s16le audio.wav
ffmpeg -hide_banner -y -f lavfi -i testsrc=size=160x90 -frames:v 1 cover.jpg
```
Each file must stay under 60 KB.
- [ ] **Step 2: Failing argv tests** (`tests/unit/test_media_args.py`): `[iso639_2(x) for x in ("th", "en-US", "tha", "xx", None)] == ["tha", "eng", "tha", "und", "und"]`; exact lists for mp4 (cover + subtitle + `audio_language="th"` → contains `"-map", "0:v:0", "-map", "0:a?", "-map", "2:0", "-map", "1:0"`, `"-c:s", "mov_text"`, `"-metadata:s:s:0", "language=tha"`, `"-disposition:s:0", "default"`, `"-disposition:v:1", "attached_pic"`, `"-metadata:s:a:0", "language=tha"` and ends with `"-movflags", "+faststart", str(dst)`), m4a (`"-f", "mp4"`), mp3 (`"-b:a", "192k"`, `"-id3v2_version", "3"`), wav (`"-c:a", "pcm_s16le"`, no `"-ar"`). **AC-SEC-05:** a title `ทดสอบ; & | $(rm -rf ~) \`x\`` appears exactly once, as the single element `"title=ทดสอบ; & | $(rm -rf ~) \`x\`"`.
- [ ] **Step 3: Failing no-shell test** (`tests/unit/test_no_shell.py`): parse every `src/yttoolkit/**/*.py` with `ast`; fail on any call with keyword `shell` whose value is not the constant `False`, and on any call to `os.system` / `os.popen`.
- [ ] **Step 4: Failing fake tests:** `FakeMediaTools(media_root)`: `available()` is True; `finalize_mp4` copies `src` to `dst`; `to_mp3` / `to_wav` write a copy of `audio.mp3` / `audio.wav`; `on_progress(1.0)` called; `cancel()` returning True → `JobCancelled` and no `dst`. `FfmpegTools(lambda: None).available()` is False and every method raises `YtError` code `E_FFMPEG_MISSING`.
- [ ] **Step 5: Failing real-ffmpeg tests** (`tests/integration/test_media_ffmpeg.py`, every test `@requires_ffmpeg`): `finalize_mp4(video.mp4 → out.mp4, cover.jpg, subs.srt (tha), audio_language="th")` → ffprobe shows one `mov_text` stream with `language=tha` and disposition default, an `attached_pic` video stream, audio `language=tha`, format tag `title`, and the main video stream codec/bit rate equal to the source (AC-VID-09 "ไม่เข้ารหัสภาพใหม่"); `finalize_m4a(audio.m4a)` with cover keeps codec `aac` (AC-AUD-01) and has the title tag; `to_mp3(kbps=192)` → `bit_rate` within 192 kbps ± 5% (AC-AUD-02); `to_wav(audio.m4a)` → `pcm_s16le`, sample rate 44100, duration within 0.1 s, tags `title`/`artist` (AC-AUD-03); cancel: `run_ffmpeg([ffmpeg, "-hide_banner", "-nostdin", "-y", "-re", "-f", "lavfi", "-i", "sine=duration=30", "-f", "null", "-"], duration_s=30, cancel=<True after 0.3 s>, …)` raises `JobCancelled` in under 1.5 s and the process is gone.
- [ ] **Step 6: Run, expect FAIL. Implement C9. Run again; on the dev machine all real-ffmpeg tests must PASS** (record "attached_pic in m4a via -f mp4: OK" or the deviation in the commit message; if `-c copy` rejects the JPEG in mp4, switch the cover stream to `-c:v:1 mjpeg` and say so).
- [ ] **Step 7: Commit** `feat(core): media tools (ffmpeg argument lists, runner, fake), media fixtures`.

### Task 6: Event bus and SSE

**Files:**
- Create: `src/yttoolkit/core/events.py`, `src/yttoolkit/api/events.py`
- Create: `tests/unit/test_events.py`, `tests/api/test_events_stream.py`

**Interfaces:** Produces C6 (`Event`, `EventBus`, `Subscription`, `CLOSED`, `format_event`, `sse_stream`, `build_events_router`). The router is included by T11 (`app.py` owner in W2).

- [ ] **Step 1: Failing bus tests:**

```python
from yttoolkit.core.events import CLOSED, EventBus

class Clock:
    def __init__(self): self.t = 0.0; self.jobs = []
    def __call__(self): return self.t
    def schedule(self, delay, fn): self.jobs.append((self.t + delay, fn))
    def advance(self, dt):
        self.t += dt
        due = [j for j in self.jobs if j[0] <= self.t]; self.jobs = [j for j in self.jobs if j[0] > self.t]
        for _, fn in due: fn()

def drain(sub):
    out = []
    while (e := sub.get(0)) is not None and e is not CLOSED: out.append(e)
    return out

def test_ac_q_08_at_most_four_updates_per_second():
    clock = Clock(); bus = EventBus(monotonic=clock, schedule=clock.schedule); sub = bus.subscribe()
    for i in range(100):
        bus.job_updated("j1", {"progress": i / 100}); clock.advance(0.01)
    events = drain(sub)
    assert 1 <= len(events) <= 5            # 1 s window: first emit + at most 4 flushes
    clock.advance(1.0)
    last = drain(sub)[-1]
    assert last.data == {"id": "j1", "progress": 0.99}   # nothing lost: the final value arrives

def test_other_jobs_are_independent():
    clock = Clock(); bus = EventBus(monotonic=clock, schedule=clock.schedule); sub = bus.subscribe()
    bus.job_updated("a", {"progress": 0.1}); bus.job_updated("b", {"progress": 0.2})
    assert [e.data["id"] for e in drain(sub)] == ["a", "b"]

def test_publish_is_immediate_and_close_wakes():
    bus = EventBus(); sub = bus.subscribe()
    bus.publish("queue.paused", {"until": "x", "reason": "E_BOT_CHECK"})
    assert sub.get(0).name == "queue.paused"
    bus.close()
    assert sub.get(1) is CLOSED
```
- [ ] **Step 2: Failing stream tests** (`tests/api/test_events_stream.py`): `format_event(Event("job.updated", {"id": "j", "title": "ไทย"}))` equals `'event: job.updated\ndata: {"id":"j","title":"ไทย"}\n\n'`; `sse_stream` (driven with `anyio.run` and a fake monotonic) yields `"retry: 3000\n\n"`, then a published event, then `": ping\n\n"` after the fake clock passes 15 s, then stops after `bus.close()`; through `TestClient`, `GET /api/events` with a bus closed by a `threading.Timer(0.2, bus.close)` after one `publish` returns status 200, `text/event-stream` and the body contains that event.
- [ ] **Step 3: Run, expect FAIL. Implement. Run, expect PASS. Full suite.**
- [ ] **Step 4: Commit** `feat: event bus with per-job throttle and SSE stream`.

### Task 7: Web UI kit, all M4 strings, packages, Playwright projects

**Files:**
- Modify: `web/src/i18n/th.ts` (C13 verbatim)
- Modify: `web/package.json`, `web/package-lock.json` (deps `@dnd-kit/core`, `@dnd-kit/sortable`, `@dnd-kit/utilities`; script `e2e` per C14)
- Modify: `web/playwright.config.ts` (C14)
- Create: `web/src/components/ui/sheet.tsx`, `progress.tsx`, `alert-dialog.tsx`, `checkbox.tsx`, `table.tsx` (via `npx shadcn@latest add sheet progress alert-dialog checkbox table`, Base UI variants matching `components.json` style `base-nova`)

- [ ] **Step 1:** Add the components with the shadcn CLI; check each new file uses the theme tokens (no hard-coded colours) and the `data-slot` attributes like the existing UI files.
- [ ] **Step 2:** Add C13 to `th.ts` exactly (keys and text). Keep `as const`.
- [ ] **Step 3:** Install the dnd-kit packages; update the `e2e` script; implement the two-server/two-project config.
- [ ] **Step 4:** `npm run typecheck && npm run lint && npm test && npm run build`; report the new gzip total in the commit message.
- [ ] **Step 5: Commit** `feat(web): M4 UI kit, strings, dnd-kit, queue e2e project`.

### Task 8: Web data layer and e2e helpers

**Files:**
- Modify: `web/src/lib/types.ts` (C2, C3, C12 types)
- Create: `web/src/lib/jobs.ts`, `web/src/lib/jobs.test.ts`
- Create: `web/src/lib/events.ts`, `web/src/lib/events.test.ts`
- Create: `web/src/lib/settings-api.ts`, `web/src/lib/settings-api.test.ts`
- Create: `web/src/lib/download-options.ts`, `web/src/lib/download-options.test.ts`
- Create: `web/src/lib/download-prefs.ts`, `web/src/lib/download-prefs.test.ts`
- Create: `web/e2e/queue-helpers.ts`

**Interfaces:** Produces C12 and the C14 helpers. Consumes `api()` from `lib/api.ts`, `fill()` and the existing `th` keys, `toast` (sonner). T8 never references the **new** C13 keys (T7 adds them in the same wave): every user-facing text in T8 code arrives through parameters (`EnqueueMessages`, the `labels` of `audioLanguageOptions`).

- [ ] **Step 1: Failing Vitest cases:**
  - `jobs.test.ts`: `mergeJobPatch` merges, removes keys set to `null`, ignores unknown ids (returns the same array instance); `upsertJob` replaces by id or appends; `groupForSheet` ordering and the 20-done cap, drops `cancelled`, puts `interrupted` with `failed`; `barSummary` counts and `current` = latest `startedAt` running; `enqueueJobs` posts `{items}` with the token header (inject `fetch` via `api` deps the same way `api.test.ts` does).
  - `events.test.ts`: `parseServerEvent` for all five names and garbage (`null`); `applyServerEvent` on a real `QueryClient` updates `["jobs"]` and `["queue"]` and returns `before/after`; `connectEvents` with a fake `EventSource` calls `onShutdown` on `app.shutdown`, calls `onJobChange` when a status changes, and invalidates both keys on `open` after `error`.
  - `download-options.test.ts`: `qualityOptions` for the BBB probe shape (compat-only ≤ 1080 vs all), `codecLabel`, `audioLanguageOptions` for a dub clip (`th` original + `en-US`) with labels `{original: "ต้นฉบับ ({lang})", originalUnknown: "ต้นฉบับ"}` → `[{value:"original", label:"ต้นฉบับ (ไทย)"}, {value:"en-US", label:"อังกฤษ (สหรัฐอเมริกา)"}]` with a `languageName` built on `Intl.DisplayNames("th", {type:"language"})`, and `null` for single-language clips; `resolveAudioLanguage` (`"en"` → `"en-US"`, `"ja"` → `"original"`, options null → preferred); **AC-AUD-04:** `wavBytes(60) === 10_584_000` and `wavMegabytes(635) === 112`; `batchMinutes(21, 2) === 7`, `batchMinutes(1, 3) === 1`; `buildVideoParams` (auto → no `formatId`; noAudio → `noAudio:true`; embed → `embedSubs` + `subOptions`); `paramsFromSettings("video", {...videoDefault:"compat-720"})` → `maxHeight: 720`.
  - `download-prefs.test.ts`: defaults from settings, version mismatch or junk → fallback, storage throwing on get/set → memory only, `set` notifies subscribers.
  - `settings-api.test.ts`: `patchSettings` sends PATCH with JSON body and token.
- [ ] **Step 2: Run, expect FAIL. Implement. Run `npm run typecheck && npm run lint && npm test`. Expect PASS.**
- [ ] **Step 3:** Write `web/e2e/queue-helpers.ts` (C14); it must typecheck and lint.
- [ ] **Step 4: Commit** `feat(web): jobs, events, settings and download-option data layer`.

---

## Wave 2

### Task 9: Extractor download (real and fake) and fake behaviours

**Files:**
- Modify: `src/yttoolkit/core/extractor.py`
- Create: `tests/unit/test_extractor_download.py`
- Create: `tests/fixtures/downloads/behaviors.json` (C14 verbatim)
- Modify: `tests/fixtures/README.md` (section "downloads/": what each id does)

**Interfaces:** Consumes C8 types from `core/download.py`, `JobCancelled` from `core/cancel.py`. Produces `YtDlpExtractor.download`, `FakeExtractor.download`, `FakeExtractor.probe` behaviour ids, and the private helpers `_download_opts`, `_progress_hook`, `_pp_hook` (tested directly).

- [ ] **Step 1: Failing fake tests:** BBB video choice → `workdir/media.mp4` equals `media/video.mp4` bytes; noAudio → `video-noaudio.mp4`; audio choice → `media.m4a`; stages reported in order (`downloading_video`, `downloading_audio`, `merging`); progress fractions increase to 1.0; `is_cancelled` returning True at step 3 → `JobCancelled` and no media file; `NETRETRYDL1` fails once with `E_NETWORK` then succeeds on the second call; `REFUSEDDL01` always `E_YT_REFUSED`; `FakeExtractor.probe("SLOWDOWNLD1")["title"] == "คลิปโหลดช้า 1"` and `["id"] == "SLOWDOWNLD1"`; unknown id without a probe fixture → `E_VIDEO_UNAVAILABLE` (unchanged). Fake tests set `stepMs` to 0 by passing a behaviours file path (constructor keyword `behaviors: Path | None = None`, default `<fixtures_root>/downloads/behaviors.json`) pointing at a temp copy with `stepMs: 0`.
- [ ] **Step 2: Failing real-wiring tests** (no network): `_download_opts` returns the exact dict of C8 (merge key only when `merge_mp4`; `ffmpeg_location` only when set); `_progress_hook` maps sample `d` dicts to `on_stage`/`on_progress` calls and raises `DownloadCancelled` when cancelled; `_pp_hook` reports `merging` for `Merger`; and a monkeypatched `yt_dlp.YoutubeDL` stub (records params, `extract_info` returns the BBB fixture, `process_ie_result` writes `media.mp4` and returns `{"requested_downloads": [{"filepath": …}]}`) proves: one extraction, the second instance gets `choice.format_spec`, the result path is returned, and when the stub's `process_ie_result` raises `DownloadError("ERROR: unable to download video data: HTTP Error 403: Forbidden")` the whole extract+download runs exactly twice before `YtError("E_YT_REFUSED")` is raised (Q2).
- [ ] **Step 3: Run, expect FAIL. Implement C8 "Real" and "Fake". Run, expect PASS. Full suite.**
- [ ] **Step 4: Commit** `feat(core): yt-dlp download with chooser, hooks and fake behaviours`.

### Task 10: Job handlers

**Files:**
- Create: `src/yttoolkit/core/handlers.py`, `tests/unit/test_handlers.py`

**Interfaces:**
```python
@dataclass
class HandlerDeps:
    videos: VideoService
    downloader: Downloader            # C8 (extractor)
    media: MediaTools                 # C9
    subtitles: SubtitleService
    cache_root: Path
    now: Callable[[], datetime] = lambda: datetime.now(UTC)
    disk_free: Callable[[Path], int] = lambda p: shutil.disk_usage(p).free
def build_handlers(deps: HandlerDeps) -> dict[str, Handler]   # keys: video, audio, subtitle, contact_sheet, frames_zip
```
Consumes C1, C3, C8, C9, C10, `SubtitleService.export/tracks`, `storyboard.get_storyboard`, `frames.contact_sheet/frames_zip`, `srt_builder.options_from_dict`.

Handler flow (all kinds): `ctx.stage("probing")`; `info = videos.get(video_id, peek=True)`; `ctx.set_title(info["title"])`; `files.ensure_output_root(ctx.output_root)`; … ; `ctx.stage("writing")`; move into place via `files.plan_output` + `files.move_into_place`; `files.write_source_note(folder, SourceInfo(title, channel, id, publishedAt[:10] or None, license), deps.now())`; return `JobResult(outputs=(OutputFile(str(root), rel, size, kind),), notes, title)`.
- **video:** `choose = lambda raw: _disk_checked(video_choice(raw, params), root)` (`E_DISK_FULL` with `params={"size": <2 × expected, human>}` when `disk_free(root) < 2 × expected`); `downloader.download(...)` with hooks bound to `ctx` and `ffmpeg_location=media.ffmpeg_path()`; cover = `downloader.fetch(info["thumbnailUrl"])` → Pillow → `workdir/cover.jpg` (any exception → no cover, `log.info`); embed subs when `embedSubs`: `subtitles.export(id, track, "srt", options_from_dict(subOptions))` → `workdir/subs.srt`, language `iso639_2(result.lang)`; a `YtError` other than `E_NETWORK`/`E_BOT_CHECK` → note `EMBED_SUBS_SKIPPED`; `media.finalize_mp4(…, audio_language=choice.audio_language)` (subtitle language via `iso639_2` from `core/media.py`); name suffix `" (ไม่มีเสียง)"` when `noAudio`; kind `"video"`.
- **audio:** `audio_choice`; m4a → `finalize_m4a` (stage `writing`), mp3 → `to_mp3(kbps)` and wav → `to_wav` (stage `converting`); kind `"audio"`.
- **subtitle:** track = `params.trackId` or `subtitles.tracks(id).get("defaultTrackId")`; none → `JobResult(notes=("NO_SUBTITLES",), title=…)` (no folder, no note file); export; `E_SESSION_WARMING` → `ctx.wait(exc.retry_after or 5)` then one more export; write bytes to `workdir/out.<fmt>` then move to `"<t>.<lang>.<fmt>"`; kind `"subtitle"`.
- **contact_sheet / frames_zip:** `get_storyboard(id, videos, cache_root, downloader.fetch)` → frame files → `contact_sheet(frames, title, durationS)` / `frames_zip(frames)` → `"<t> - contact sheet.jpg"` (kind `"image"`) / `"<t> - frames.zip"` (kind `"archive"`).

- [ ] **Step 1: Failing tests** with real services on a temp DB (`VideoService` + `SubtitleService` over the existing `FakeExtractor(FIXTURES)` for probe and subtitles), a test-local `StubDownloader` implementing the C8 `Downloader` protocol (calls `choose(FakeExtractor.probe(id))`, reports `downloading_video`/`downloading_audio`/`merging`, honours `hooks.is_cancelled()` by raising `JobCancelled`, copies `tests/fixtures/media/video.mp4`, `video-noaudio.mp4` or `audio.m4a` like C8 "Fake"; `FakeExtractor.download` itself is T9's, same wave), `FakeMediaTools(FIXTURES/"media")` and a `RecordingContext` (implements `JobContext`, records stages/progress, `wait` records seconds): video BBB → `out/<title> [aqz-KE-bpKQ]/<title>.mp4` exists, `แหล่งที่มา.txt` exists, result kind `video`, stages `probing → downloading_video → downloading_audio → merging → writing`; noAudio → name ends with ` (ไม่มีเสียง).mp4`; audio m4a/mp3/wav names and stage `converting` for mp3/wav; `jNQXAC9IVRw` audio with `audioLanguage: "th"` → note `AUDIO_LANG_FALLBACK`; subtitle `88o5Sk8_m1Y` srt → file content equals `SubtitleService.export(...).data` and name ends `.th-orig.srt`… (check: `export` returns `lang` — use whatever it returns, e.g. `th`; the test asserts `name.endswith(f".{result.lang}.srt")`); subtitle on BBB (no subs) → note `NO_SUBTITLES`, no output, no folder; contact sheet on BBB → a JPEG; frames_zip → a zip with `frame_00-00-00.jpg`; `disk_free=lambda p: 10` → `YtError` `E_DISK_FULL` whose message contains "พื้นที่ไม่พอ"; output root is a file → `E_OUTPUT_NOT_WRITABLE`; context cancelled during download → `JobCancelled`; embed subs with a track the clip lacks → note `EMBED_SUBS_SKIPPED` and the mp4 still written; two jobs of the same clip → one folder, one `แหล่งที่มา.txt`.
- [ ] **Step 2: Run, expect FAIL. Implement. Run, expect PASS. Full suite.**
- [ ] **Step 3: Commit** `feat(core): job handlers for video, audio, subtitle, contact sheet and zip`.

### Task 11: Queue runner and jobs API

**Files:**
- Create: `src/yttoolkit/core/queue.py`, `src/yttoolkit/api/jobs.py`
- Modify: `src/yttoolkit/app.py` (include `build_jobs_router` and `build_events_router` when `ctx.queue` and `ctx.events` are set)
- Modify: `src/yttoolkit/api/errors.py` (public `redact_home = _redact_home`; keep the private name as an alias for existing imports)
- Create: `tests/unit/test_queue.py`, `tests/api/test_jobs_api.py`

**Interfaces:** Produces C4 and C7. Consumes C1, C3 (pydantic models here), C6, `SettingsView`, `FFMPEG_KINDS`/`YOUTUBE_KINDS`, `MESSAGES`, `attachment_header` (from `api/videos.py`).

- [ ] **Step 1: Failing runner tests** (`tests/unit/test_queue.py`) with a `ManualSpawn` (collects worker callables; the test runs them when it wants), a `BlockingHandler` (waits on a `threading.Event` per job, honours `ctx.cancelled()`), fake `monotonic`/`wall`, `random.Random(1)`, and a stub settings view:

```python
def test_ac_q_01_never_more_than_concurrency(runner_factory):
    r, spawn, h = runner_factory(concurrency=2, kind="contact_sheet")   # non-YouTube: no delay
    r.enqueue([NewJob(f"vid{i:08d}", "contact_sheet", {"source": "fast", "columns": 5}) for i in range(5)])
    assert len(r.tick()) == 2 and len(r.tick()) == 0
    spawn.run_one(); h.finish_one(); r.tick()
    assert len(r.store.running()) <= 2

def test_ac_q_02_gap_between_youtube_starts(runner_factory):
    r, spawn, h = runner_factory(concurrency=2, kind="video")
    r.enqueue([NewJob("vid00000001", "video", {}), NewJob("vid00000002", "video", {})])
    assert len(r.tick()) == 1
    gap = r.next_youtube_at - r.clock.t
    assert 2.0 <= gap <= 5.0
    r.clock.t += gap - 0.01; assert r.tick() == []
    r.clock.t += 0.02; assert len(r.tick()) == 1

def test_ac_q_03_bot_check_pauses_and_resume(runner_factory):
    r, spawn, h = runner_factory(concurrency=1, kind="video", fail={"vid00000001": "E_BOT_CHECK"})
    r.enqueue([NewJob("vid00000001", "video", {}), NewJob("vid00000002", "video", {})])
    r.tick(); spawn.run_all()
    events = r.bus_events()
    assert ("queue.paused", "E_BOT_CHECK") in [(e.name, e.data.get("reason")) for e in events]
    first = r.store.get_by_video("vid00000001")
    assert first.status == "queued" and first.bot_checks == 1 and first.position < r.store.get_by_video("vid00000002").position
    r.clock.t += 100; assert r.tick() == []            # still paused, nothing starts
    r.resume(); assert len(r.tick()) == 1             # "ลองต่อเลย" starts at once

def test_brake_keys_on_code_not_status(runner_factory):
    r, spawn, h = runner_factory(concurrency=1, kind="subtitle", fail={"vid00000001": "E_TRANSLATION_BLOCKED"})
    r.enqueue([NewJob("vid00000001", "subtitle", {})]); r.tick(); spawn.run_all()
    assert r.pause_state() is None and r.store.get_by_video("vid00000001").status == "failed"

def test_second_bot_check_fails_the_job(...): ...
def test_network_retries_wait_2_5_10_then_fail(...): ...   # attempt 1..3 published, waits recorded, final message "เน็ตหลุด ลองใหม่อีกครั้ง"
def test_ac_q_07_cancel_running_within_3s_removes_workdir(...): ...   # real thread spawn; handler polls ctx.cancelled every 0.05 s; cancel -> status cancelled in < 3 s; workdir gone
def test_cancel_queued_is_immediate(...): ...
def test_retry_failed_goes_to_end(...): ...
def test_ac_q_05_recover_interrupts_running_and_empties_work(...): ...
def test_shutdown_interrupts_running(...): ...           # status interrupted, error_code E_INTERRUPTED
def test_concurrency_change_applies_next_tick(...): ...  # AC-SET-01 (queue part)
def test_unexpected_exception_fails_with_unknown(...): ...
```
(`runner_factory`, `ManualSpawn`, `store.get_by_video` are test helpers defined in the test file; `get_by_video` is a small helper over `store.list_status`, not a `JobStore` method.)
- [ ] **Step 2: Failing API tests** (`tests/api/test_jobs_api.py`, `make_client(queue=runner, events=bus, settings=…, media=FakeMediaTools(...))` with fake handlers): POST valid video/audio/subtitle/contact_sheet/frames_zip → 200 and `job.created` events; POST `frames_sharp`, `range`, `splitChapters: true`, `embedSubs` without `subOptions` → 422 `E_BAD_REQUEST`; **AC-VID-10:** `embedSubs` + `splitChapters: true` → 422; POST video with `media` whose `available()` is False → 409 `E_FFMPEG_MISSING` and no job stored; POST without token → 403; GET `/jobs` default list rules; GET `/jobs?status=done&limit=1`; GET `/queue` paused shape after `runner.brake()`; cancel/retry 200/404/409 (`E_JOB_STATE`); PUT `/jobs/order` reorders; POST `/queue/resume`; GET output: 200 attachment with RFC 5987 Thai name, 404 for a bad index, a deleted file, and a forged `outputs_json` whose `rel` is `../../secret.txt`; reveal calls the `reveal` override with the absolute path; the `detail` of a failed job with a home-folder path comes back with `~`.
- [ ] **Step 3: Run, expect FAIL. Implement C7 and C4. Run, expect PASS. Full suite.**
- [ ] **Step 4: Commit** `feat: queue runner (concurrency, gap, brake, retries, cancel, recovery) and jobs API`.

### Task 12: History API, bot-check brake hook, old endpoints removed

**Files:**
- Modify: `src/yttoolkit/core/videos.py` (`recent(limit, offset, q, scope)`)
- Modify: `src/yttoolkit/api/videos.py` (history `scope`; `STATUS_BY_CODE["E_YT_REFUSED"] = 502`; a per-router error mapper that calls `ctx.on_bot_check()` when the code is `E_BOT_CHECK`; remove `GET /videos/{id}/storyboard/contact-sheet.jpg` and `/frames.zip` (Q3))
- Modify: `src/yttoolkit/api/subtitles.py` (use the same mapper; remove `GET /videos/{id}/subtitles/{trackId}/export` and `export_filenames` (Q3); `/note` stays)
- Modify: `tests/api/test_videos_api.py`, `tests/api/test_subtitles_api.py` (drop the removed endpoints' tests; their file-content assertions move to T10's handler tests)
- Create: `tests/api/test_history_api.py`

**Interfaces:**
```python
def yt_error_response(exc: YtError, subject: str, *, on_bot_check: Callable[[], None] | None = None) -> JSONResponse
def yt_error_mapper(on_bot_check: Callable[[], None] | None) -> Callable[[F], F]   # decorator factory replacing _maps_yt_errors
```
`on_bot_check` exceptions are caught and logged; the response is unchanged. Consumes C15, `ctx.on_bot_check` (T2).

- [ ] **Step 1: Failing tests:** C15 cases (`scope=opened` = old behaviour incl. peek exclusion; `scope=all` includes a never-opened clip with a done job (insert rows directly), `outputs` order, `lastAt` = later of open and finish, search, unknown scope → 422); `GET /api/videos/<id>` with an extractor that raises `E_BOT_CHECK` calls `on_bot_check` once and still answers 429 with the M4 message; `E_TRANSLATION_BLOCKED` (503) from `/tokens` and `E_NETWORK` do **not** call it; the removed paths answer 404 `E_NOT_FOUND`.
- [ ] **Step 2: Run, expect FAIL. Implement. Run, expect PASS. Full suite.**
- [ ] **Step 3: Commit** `feat(api): history with outputs, bot-check brake hook, queue-only file exports`.

> **Q3 ≠ recommended:** keep the three GET endpoints and their tests; T16 then adds queue buttons next to the browser ones instead of replacing them.

### Task 13: W5 history page and routes

**Files:**
- Create: `web/src/pages/history.tsx`, `web/src/pages/history/history-table.tsx`, `web/src/pages/history/queries.ts`, `web/src/pages/history/queries.test.ts`
- Modify: `web/src/router.tsx` (`/history`; `/settings` now redirects to `/settings/general`), `web/src/pages/lazy.tsx` (`LazyHistoryPage`)
- Modify: `web/src/pages/home/recent.tsx` (`/history?limit=5&scope=opened`, query key `["history", {limit: 5, scope: "opened"}]`)
- Create: `web/e2e/history.spec.ts` (chromium: empty state, search no-match, row link opens W2, axe both themes, 640 px no overflow), `web/e2e/queue-history.spec.ts` (queue: download audio of `jNQXAC9IVRw` through the API helper, wait done, history row shows badge "เสียง" and opens W2 from cache — AC-OUT-05 E)

**Requirements (PRD W5 + C15):** semantic table: ปก (thumbnail 16:9, 96 px), ชื่อคลิป (link to `/v/:id`, single tab stop per row; whole row clickable like W1), ไฟล์ที่ได้ (Badge per kind using `th.history.kinds`, de-duplicated labels), เวลา (`relativeTime`); newest first; search input (debounced 300 ms, kept in `?q=` with replace); pages of 50 via `useInfiniteQuery` with "แสดงเพิ่ม" and "แสดง N จาก M คลิป"; states: loading (Skeleton rows), error (existing error panel + retry), empty (Empty "ยังไม่มีประวัติ" + hint + button "กลับหน้าแรก"), no match (text with the query). `document.title` = `th.history.pageTitle`. Header nav link is added by T14.

- [ ] **Step 1:** Vitest for `queries.ts` (URL building with `q`, `scope=all`, offsets; next-page param).
- [ ] **Step 2:** Implement; typecheck, lint, Vitest.
- [ ] **Step 3:** Write both specs (they run at gate 3).
- [ ] **Step 4: Commit** `feat(web): W5 history page`.

### Task 14: W4 queue bar and sheet, toasts, W7 shutdown dialog

**Files:**
- Create: `web/src/components/queue/queue-bar.tsx`, `queue-sheet.tsx`, `job-row.tsx`, `sortable-queued.tsx`, `pause-alert.tsx`, `use-queue.ts`, `use-queue.test.ts`, `job-text.ts`, `job-text.test.ts`, `shutdown-dialog.tsx`
- Modify: `web/src/components/layout.tsx` (nav item "ประวัติ" between หน้าแรก and ตั้งค่า with `History` icon, icon-only below 640 px with `aria-label` + tooltip; mount `<QueueBar/>`; mount `useServerEvents` (connect once); render `ShutdownScreen` when `useAppShutdown()`; open the shutdown dialog when `?confirmShutdown=1`)
- Modify: `web/src/pages/settings/health-panel.tsx` ("ปิดโปรแกรม": on 409 open `ShutdownDialog` with `pendingJobs` instead of the toast; "ปิดเลย" posts `{force: true}`)
- Create: `web/e2e/queue-flow.spec.ts`, `web/e2e/nav.spec.ts` (chromium: "ประวัติ" link present with `aria-current` on `/history`, icon-only at 360 px with an accessible name, no overflow at 360 and 640)

**Requirements (PRD W4, W7, BRD 10.7):**
- **Bar** (`role="region"` `aria-label` "คิวงาน"): fixed to the bottom of every page, hidden when `barSummary().visible` is false; one line: current job title (truncated) + `stage · %` + speed + ETA (or "รอคิว" / "เน็ตหลุด กำลังลองใหม่ (ครั้งที่ n/3)") + counters `th.queue.counts`; a 4 px amber progress line; the whole bar is one button "เปิดคิวงาน" (`aria-expanded`) that opens the Sheet. While paused it shows the pause alert (C13 `paused.*`) with a live countdown (`m:ss`) and "ลองต่อเลย". Sets `--dock-bottom-offset` on `:root` to its height (ResizeObserver) and back to `0px` when hidden/unmounted, so the M3.5 floating player and toasts stack above it. Wraps to two lines on narrow windows, never overflows.
- **Sheet** (bottom, `max-height: 80vh`, scroll inside, title "คิวงาน", hint): pause alert on top, then groups from `groupForSheet` with headings: running rows (title, kind label, stage · % · speed · ETA, Progress, "ยกเลิก" with `aria-label` "ยกเลิกงาน {title}"; "กำลังยกเลิก" when `cancelling`); queued rows (drag handle "ลากเพื่อเปลี่ยนลำดับ {title}", dnd-kit keyboard sensor with C13 announcements, "ยกเลิก"); failed/interrupted rows (icon + `error.message`, "ดูรายละเอียด" collapsible with "รหัส {code}" + detail + "คัดลอกรายละเอียด", "ลองใหม่"); done rows (check icon (one scale-in, none with `prefers-reduced-motion`), output name, notes in grey, "เปิดโฟลเดอร์" → `revealOutput`, "ดาวน์โหลด" = link `outputUrl(id, 0)` with `download`). Rows show `title || videoId`.
- **Reorder:** on drop call `reorderJobs(newQueuedIds)` (optimistic, rollback + `th.queue.actionFailed` toast on error).
- **Toasts** via `connectEvents(onJobChange)`: status becomes `done` → `toast.success(th.queue.finished)` with action "เปิดโฟลเดอร์"; `failed` → `toast.error(th.queue.failed + message)` with `duration: Infinity` and action "รายละเอียด" (opens the Sheet scrolled to the row). Only for transitions seen in this tab (no toasts for history loaded on refresh).
- **Shutdown dialog** (Alert Dialog, C13 `shutdown.*`): count = `running + queued` from the jobs cache (or `pendingJobs` from the 409); "กลับไปก่อน" closes and removes `confirmShutdown` from the URL (replace); "ปิดเลย" → `POST /shutdown {force: true}` → shutdown screen.
- **App shutdown:** `app.shutdown` event → the layout shows the existing `ShutdownScreen`.
- Queue data: `useQuery(jobsQuery())` + `useQuery(queueQuery())`, patched by SSE; refetch on reconnect.

- [ ] **Step 1: Vitest:** `job-text.ts` (pure: `progressLine(job)`, `formatEta`, `formatSpeed`, retry text, paused countdown text `m:ss` from `pausedUntil` and now) and `use-queue.ts` (pure reducers around reorder optimistic update/rollback).
- [ ] **Step 2: Implement; typecheck, lint, Vitest.**
- [ ] **Step 3: `queue-flow.spec.ts`** (serial; queue project): enqueue `SLOWDOWNLD1..4` via the API helper → bar shows "กำลังทำ 2 · รอ 2"; **AC-Q-04** reload → same rows; **AC-Q-06** drag `SLOWDOWNLD4` above `SLOWDOWNLD3` (mouse) and with the keyboard (Space, ArrowUp, Space) → `GET /api/jobs` order and reload keep it, and when a slot frees `SLOWDOWNLD4` starts first; cancel a running job → row leaves within 3 s; `NETRETRYDL1` shows the retry text then finishes; `BOTCHECKDL1` → pause alert on the bar and in the sheet with a countdown near 10:00, the job back in "รอ", then "ลองต่อเลย" → it finishes; `REFUSEDDL01` → failed row with the E_YT_REFUSED message, "รายละเอียด" shows the code, "ลองใหม่" re-queues it; done row "ดาวน์โหลด" returns 200 with an attachment; "เปิดโฟลเดอร์" returns ok (fake no-op); `--dock-bottom-offset` equals the bar height while visible; axe (both themes) with the sheet open; 640 × 800 no horizontal overflow; shutdown dialog: tray URL `/?confirmShutdown=1` shows the count, "กลับไปก่อน" removes the param, "ปิดเลย" (with `POST /api/shutdown` mocked by `page.route`) shows "ปิดโปรแกรมแล้ว". Clean up with `cancelJobsFor` in `afterAll`.
- [ ] **Step 4: Commit** `feat(web): W4 queue bar and sheet, job toasts, W7 shutdown dialog`.

### Task 15: W2 วิดีโอ and เสียง tabs

**Files:**
- Modify: `web/src/pages/video/tabs.tsx` (C12 order; render the two panels; `panelHasButtons(video)` returns `video !== undefined` because the info tab now always has the credit button, T16)
- Modify: `web/src/pages/video/url-state.ts`, `web/src/pages/video/url-state.test.ts`
- Create: `web/src/pages/video/download/video-panel.tsx`, `audio-panel.tsx`, `audio-language-select.tsx`, `use-download-state.ts`, `use-download-state.test.ts`
- Modify: `web/e2e/video-tabs.spec.ts` (`TAB_NAMES` → `["ภาพเฟรม", "วิดีโอ", "เสียง", "ซับ", "ทรานสคริปต์", "ข้อมูลคลิป"]`)
- Create: `web/e2e/download-tabs.spec.ts` (chromium, mocked enqueue), `web/e2e/queue-download.spec.ts` (queue)

**Requirements (PRD W2 rows วิดีโอ/เสียง, FR-VID-1..9, FR-AUD-1..5, C12):**
- **วิดีโอ tab:** heading; Select "คุณภาพ" (`AUTO_QUALITY` option first = `th.download.video.auto`, then `qualityOptions` labelled with `option`/`optionSize`); Switch "ความละเอียดสูงสุด" with hint; when on, non-compat options carry the badge "บางโปรแกรมเปิดไม่ได้"; Select "ภาษาเสียง" (`audioLanguageOptions`; hidden when null; disabled with tooltip `languageDisabled` when "ไม่เอาเสียง" is on); Switch "ไม่เอาเสียง" with hint; Select "ฝังซับ (เปิด/ปิดได้)" (default "ไม่ฝัง"; options = owner/original tracks from the existing subtitle tracks query; disabled with tooltip "คลิปนี้ไม่มีซับให้ฝัง" when none) using the current ซับ-tab options (`useSubSettings`); size line `estimate` when `videoSizeEstimate` is known; the page's only primary button "โหลด mp4" → `useEnqueue([{videoId, kind: "video", params: buildVideoParams(...), title}])`.
- **เสียง tab:** ToggleGroup m4a (แนะนำ) / mp3 / wav with `m4aHint` / `mp3Hint`; Select "คุณภาพ mp3" (128/192/320, default 192) only for mp3; for wav the line `wavSize` with `wavMegabytes(durationS, sampleRate, channels)` of the original audio track; the same "ภาษาเสียง" Select (shared state: changing it in one tab changes the other); secondary button "โหลดเสียง".
- **Defaults and memory:** `useDownloadPrefs(prefsFromSettings(settings))`; each successful enqueue saves the choices (quality as height or "auto").
- **States:** loading (Skeleton while `video` is undefined), empty (`noFormats` when `video.video` and `video.audio` are both empty), error (the page already handles video load errors).
- No "ตัวเลือกขั้นสูง" panel in M4.

- [ ] **Step 1: Vitest:** `url-state.test.ts` (new tabs parse/patch; unknown → frames), `use-download-state.test.ts` (pure state helpers: shared language, noAudio disables language, prefs → initial state per clip, quality height fallback).
- [ ] **Step 2: Implement; typecheck, lint, Vitest.**
- [ ] **Step 3: `download-tabs.spec.ts`** (mocked `POST /api/jobs` via `mockEnqueue`): 6 tabs in order and `?tab=video` deep link; exactly one amber primary button on the page ("โหลด mp4"); default payload for BBB `{kind:"video", params:{maxQuality:false, noAudio:false, audioLanguage:"original", splitChapters:false}}` and toast "เพิ่มเข้าคิวแล้ว"; noAudio → `noAudio:true` and the language Select disabled; **AC-VID-07** `8lpOfyoxcvU` shows the Select with first option "ต้นฉบับ (ไทย)" and only "อังกฤษ (สหรัฐอเมริกา)" besides; choosing it sends `audioLanguage:"en-US"` and the เสียง tab shows the same choice; BBB has no language Select; **AC-AUD-04 (E)** BBB wav shows "ไฟล์ไม่บีบอัด ขนาดประมาณ 112 MB"; mp3 shows the bitrate Select and sends `mp3Kbps:192`; ฝังซับ disabled with tooltip on BBB, enabled on `88o5Sk8_m1Y`; `E_FFMPEG_MISSING` (mock 409) → error toast with "ไปหน้าตรวจสุขภาพ"; axe both themes on both tabs; 640 × 800 no overflow.
- [ ] **Step 4: `queue-download.spec.ts`:** real video job for BBB → done row named `<BBB title>.mp4`; audio m4a for `8lpOfyoxcvU` with English → done; "ดาวน์โหลด" returns `video/mp4` bytes (size of the fixture `video.mp4`).
- [ ] **Step 5: Commit** `feat(web): W2 video and audio download tabs`.

### Task 16: W2 subtitle files, contact sheet and zip through the queue; credit

**Files:**
- Modify: `web/src/pages/video/subs/export-buttons.tsx` (".srt/.txt/.md" enqueue `{kind:"subtitle", params:{trackId: track.id, format, options}}`; spinner while posting; same disabled rules)
- Modify: `web/src/lib/sub-options.ts`, `web/src/lib/sub-options.test.ts` (remove `exportPath` and its tests; `notePath` stays)
- Modify: `web/src/pages/video/frames.tsx` (only the bulk buttons: "โหลดภาพรวมเฟรม" → `contact_sheet {source:"fast", columns:5}`, "โหลดทั้งหมด (.zip)" → `frames_zip {source:"fast"}`; single-frame download and everything else unchanged)
- Modify: `web/src/pages/video/clip-details.tsx` (credit section), `web/src/pages/video/info-sections.ts`, `web/src/pages/video/info-sections.test.ts`
- Modify: `web/e2e/subs.spec.ts` (download tests → mocked enqueue payload tests), `web/e2e/replayed-filter.spec.ts` (zip test → mocked enqueue: payload `frames_zip` with no filter params), `web/e2e/clip-info.spec.ts` (credit + empty-state wording)
- Create: `web/e2e/queue-files.spec.ts`

**Requirements:** **Credit (FR-OUT-7, AC-OUT-08, Q6):** the ข้อมูลคลิป tab starts with section "เครดิต" (h2) showing the credit line text (`th.video.info.creditLine`) and a ghost button "คัดลอกเครดิต" → clipboard `ที่มา: <ชื่อคลิป> — <ช่อง> (YouTube) https://youtu.be/<videoId>` (one line) + toast "คัดลอกแล้ว"; on `lg` it is the top of the left column (above คำอธิบาย). `infoSections(video)` gains `credit: true` when the clip has a title; "คลิปนี้ไม่มีข้อมูลเพิ่มเติม" now shows under the credit section when every other section is absent.

- [ ] **Step 1: Vitest:** `info-sections.test.ts` (credit flag; empty rule), `sub-options.test.ts` (exportPath gone, notePath unchanged).
- [ ] **Step 2: Implement; typecheck, lint, Vitest.**
- [ ] **Step 3: Specs:** rewritten chromium tests use `mockEnqueue` and assert payloads (`subtitle` with `trackId`, `format`, full `options`; `contact_sheet`; `frames_zip`) and the toast; **AC-OUT-08** credit copy (record clipboard writes like the existing helper) in `clip-info.spec.ts`; `queue-files.spec.ts`: `88o5Sk8_m1Y` .srt job → done, output name ends `.srt`, `GET` output bytes start with `1\r\n00:00:00,120`; `OWNERTHSUB1` .md job → done; BBB contact sheet → `image/jpeg`; BBB zip → `application/zip`.
- [ ] **Step 4: Commit** `feat(web): subtitle files, contact sheet and zip go through the queue; copy credit`.

### Task 17: W6 ทั่วไป tab

**Files:**
- Modify: `web/src/pages/settings.tsx` (tabs ทั่วไป · ตรวจสุขภาพระบบ · เกี่ยวกับ; default `general`)
- Create: `web/src/pages/settings/general-panel.tsx`, `web/src/pages/settings/general-form.ts`, `web/src/pages/settings/general-form.test.ts`
- Create: `web/e2e/settings-general.spec.ts`

**Requirements (PRD W6 ทั่วไป, C5, Q4):** fields save on change (no save button) and toast "บันทึกแล้ว": โฟลเดอร์ผลลัพธ์ (Input; saves on Enter or blur when changed; 422 shows the server message under the field and keeps the old value; secondary button "เปิดโฟลเดอร์" → `openOutputFolder`); จำนวนงานพร้อมกัน (ToggleGroup 1/2/3 + hint); ภาษาเสียงเริ่มต้น (Select from `th.general.languages`); คุณภาพวิดีโอเริ่มต้น (Select `videoDefaults`); รูปแบบเสียงเริ่มต้น (ToggleGroup m4a/mp3/wav); states loading / error (retry) / normal. `general-form.ts` holds the pure helpers (dirty check, PATCH body builder).

- [ ] **Step 1: Vitest for `general-form.ts`. Implement. Typecheck, lint, Vitest.**
- [ ] **Step 2: Spec** (chromium; PATCHes only settings, restores them in `afterAll`): `/settings` lands on ทั่วไป; change concurrency to 1 → toast, reload keeps 1 (**AC-SET-01 E**); relative path `abc` → inline error, value unchanged after reload; "เปิดโฟลเดอร์" → no error toast (fake no-op); axe both themes; 640 × 800 no overflow.
- [ ] **Step 3: Commit** `feat(web): W6 general settings tab`.

> **Q4 ≠ recommended (backend only):** skip T17; T13 keeps `/settings` → `/settings/health`.

---

## Wave 3

### Task 18: Lifecycle integration

**Files:**
- Modify: `src/yttoolkit/lifecycle.py`, `src/yttoolkit/tray.py`
- Modify: `tests/unit/test_lifecycle.py`, `tests/unit/test_tray.py`
- Create: `tests/integration/test_queue_serve.py`

**Interfaces:** Consumes everything above. Produces:
```python
@dataclass
class Services:
    db: Database; videos: VideoService; extractor: Extractor; subtitles: SubtitleService
    settings: SettingsStore; events: EventBus; media: MediaTools; queue: QueueRunner
def open_services(paths: Paths, plat: Platform, fake: bool = False) -> Services   # replaces T2's tuple return
```
- Fake mode: `FakeExtractor`, `FakeMediaTools(CODE_ROOT/"tests/fixtures/media")`, queue `delay_range=(0.05, 0.2)`; settings, the `<data_root>/output` default and the no-op `reveal`/`open_folder` are already wired by T2.
- Real mode: `YtDlpExtractor(session=…)`, `FfmpegTools(lambda: tools.find_ffmpeg(paths, plat), popen_flags=plat.popen_flags)`, default output `plat.downloads_dir() / "YT-Toolkit"`, default delays.
- Startup: `queue.recover()` before the server starts (AC-Q-05); `queue.start()` after `wait_until_ready`. `ctx`: `settings`, `queue`, `events`, `media`, `on_bot_check=queue.brake`, `pending_jobs=queue.pending_count`; tray "เปิดโฟลเดอร์ผลลัพธ์" uses `settings.output_dir()`.
- Shutdown (`finally`): `queue.shutdown(timeout=5)` → `events.publish("app.shutdown", {})` → `events.close()` → `server.stop()`; `uvicorn.Config(..., timeout_graceful_shutdown=3)`.
- Tray (FR-LIFE-6): `build_tray(open_app, open_output, quit_app, running_count)` adds a first, disabled menu item whose text is a callable `"กำลังทำ {n} งาน"`; lifecycle subscribes to the bus in a daemon thread and calls `icon.update_menu()` on `job.updated`/`job.created` at most once per second.

- [ ] **Step 1: Failing unit tests:** `open_services(fake=True)` wires fakes and the `<data_root>/output` default; real mode wires `FfmpegTools`; `_run_server` sets the ctx fields (use the existing test seams); the tray menu text callable reflects `running_count`.
- [ ] **Step 2: Failing integration tests** (`tests/integration/test_queue_serve.py`, pattern of `test_serve.py`, ports 8850-8869, `YT_TOOLKIT_FAKE=1`, `YT_TOOLKIT_FFMPEG_PATH_LOOKUP=0`): (a) POST `/api/jobs` (token from `run/app.json`, Origin header) a BBB video job → poll `/api/jobs` until `done` → `<data_root>/output/<title> [aqz-KE-bpKQ]/` has the mp4 and `แหล่งที่มา.txt`, `<data_root>/work/` is empty; (b) **AC-Q-05:** enqueue `SLOWDOWNLD1`, wait for `running`, kill the server by PID (`plat.kill(info.pid)`), start `serve` again → the job is `interrupted` with `E_INTERRUPTED`, `work/` is empty, POST retry → it runs again; (c) `GET /api/events` receives `job.created` for a new job (read the stream with `httpx.stream` and a short timeout); (d) `stop` with a running job: `lifecycle.stop(..., ask=lambda _: "y")` exits 0 within 15 s and the job is `interrupted` after a restart.
- [ ] **Step 3: Implement. Run unit + integration tests, then the full suite. Expect PASS.**
- [ ] **Step 4: Commit** `feat: wire queue, settings, events and media into the app lifecycle`.

### Task 19: W3 batch page

**Files:**
- Create: `web/src/pages/batch.tsx`, `web/src/pages/batch/batch-table.tsx`, `web/src/pages/batch/batch-options.tsx`, `web/src/pages/batch/rows.ts`, `web/src/pages/batch/rows.test.ts`
- Modify: `web/src/router.tsx` (`/batch`), `web/src/pages/lazy.tsx` (`LazyBatchPage`)
- Modify: `web/src/pages/home/result-list.tsx` (Q7: results header button "เลือกคลิปที่จะโหลด" when the list has ≥ 2 clip rows; each playlist/mix row gets the same button → `/batch?src=<listId>&playlist=<id>[&v=<mixVideoId>]`)
- Modify: `web/e2e/list.spec.ts` (entry buttons present/absent; clicking navigates)
- Create: `web/e2e/queue-batch.spec.ts`

**Requirements (PRD W3, FR-IN-3, FR-Q-5, W7, C3, C12):**
- `rows.ts` (pure): from the W1 home state (`results`, `listId`) and the URL → rows `{videoId, title?, durationS?, invalid?: {input}}`: without `playlist`, clip rows = `video` + `ambiguous` items de-duplicated by `videoId` (same rule as the clip sequence), `invalid` items as red unselectable rows, playlist rows excluded (show `playlistsNote` when any exist); with `playlist`, the entries of `playlistQuery(id, undefined, v)` (≤ 200). Titles come from the query cache (`videoTitleQuery` data / playlist entries) without new requests; unknown titles show the id in mono. `src` not equal to the stored `listId` → expired state.
- Page: breadcrumb `หน้าแรก › รายการที่วาง (N ลิงก์) › เลือกคลิป`; header (playlist title or "หลายลิงก์", `counts`); table with a header checkbox "เลือกทั้งหมด" (indeterminate when partial) and per-row checkboxes ("เลือก {title}"), default all selected; options: Select "โหลดอะไร" (วิดีโอ (mp4) / เสียง / ไม่เอา; default วิดีโอ) and ToggleGroup "ซับ" (ไม่เอา / .srt / .txt / .md; default ไม่เอา); the only primary button "ส่งเข้าคิว {n} คลิป" (n = selected clips), disabled-but-focusable with `nothing` hint when n = 0 or both are "ไม่เอา"; n > 20 → Alert Dialog `confirmTitle`/`confirmBody` with `batchMinutes(n, settings.concurrency)`, buttons ยกเลิก / ส่งเข้าคิว; submit → one `video` or `audio` job per clip with `paramsFromSettings(kind, settings)` plus one `subtitle` job per clip (`{format, options: current ซับ-tab options}`, no `trackId`), titles included; toast `addedMany`; stay on the page.
- States: loading (playlist query), error (retry), expired (Empty + "กลับหน้าแรก"), normal. 640 × 800 no overflow.

- [ ] **Step 1: Vitest for `rows.ts`.** Implement; typecheck, lint, Vitest.
- [ ] **Step 2: Specs:** `list.spec.ts` (chromium) entry buttons; `queue-batch.spec.ts`: paste `VTTFALLBAK1`, `NOORIGSUB01`, `LONGTHAI1hr` and `https://example.com/x` on W1 → "เลือกคลิปที่จะโหลด" → W3 shows 3 selectable rows + 1 red row; choose เสียง + .srt → submit → 6 jobs appear in the queue and finish (subtitle jobs of clips without a default track end with "คลิปนี้ไม่มีซับ"); playlist `PLfakeplaylist250` → W3 shows 200 rows → submit shows the dialog with "ส่ง 200 คลิปเข้าคิว?" → "ยกเลิก" (nothing enqueued); axe both themes; expired link → empty state.
- [ ] **Step 3: Commit** `feat(web): W3 batch picker`.

---

## Wave 4

### Task 20: Network tests, documents, final verification, live preview

**Files:**
- Create: `tests/network/test_download_network.py`
- Modify: `tests/network_videos.toml` (section `[downloads]`)
- Modify: `PRD.md`, `BRD.md`, `docs/acceptance.md`, `docs/m2-followups.md`, `docs/m3-followups.md`, `README.md`
- Modify: `tests/unit/test_yterrors.py` (gate 1): once the PRD rows for `E_JOB_STATE` and `E_YT_REFUSED` exist, empty `PRD_PENDING` so the tripwire test passes
- Create: `docs/m4-followups.md`
- Rebuild: `web/dist/**`

- [ ] **Step 1: Pick network clips** (record id, title, licence and the date checked in `tests/network_videos.toml [downloads]`): a short CC clip with multiple heights; `8lpOfyoxcvU` (Thai original + en-US dub) for AC-VID-03/05/06 — if no English clip with a Thai dub is found, AC-VID-05 is checked in reverse on `8lpOfyoxcvU` (choose `en` → track language `en`, not the original) and the gap goes into `docs/m4-followups.md`; a short 4K clip for AC-VID-02 — if none ≤ 2 minutes is found, AC-VID-02 becomes a manual row in `docs/acceptance.md`.
- [ ] **Step 2: Write `test_download_network.py`** (`@pytest.mark.network`, real `YtDlpExtractor` + `FfmpegTools` + handlers into `tmp_path`, ffprobe checks): AC-VID-01 (h264/aac, height ≤ 1080), AC-VID-03, AC-VID-04 (cover attached_pic, title/artist/comment tags), AC-VID-05, AC-VID-08 (no audio stream, name suffix), AC-VID-09 (`mov_text`, `tha`, video codec and bit rate equal to the plain download, text equal to the `.srt` built with the same preset), AC-AUD-01..03, AC-AUD-04 (wav size within 5% of the estimate). Run it once: `uv run pytest -m network -q tests/network/test_download_network.py -s`; record the result.
- [ ] **Step 3: Update `PRD.md`:** W2 (6 tabs, M4 states, advanced panel hidden), W3/W4/W5/W6 as built, W7 rows, 6.1 schema v2 + `running → queued`, 6.2 (new/changed endpoints: `/jobs` details, `GET /queue`, `/history?scope`, `/settings/open-output`, removed GET exports per Q3), 6.2.1 `Job` (title, attempt, cancelling, notes) and VideoInfo (`license`, `sampleRate`, `channels`), 6.3 params (`maxHeight`, M4 rejections), 6.3.1 (explicit audio format id instead of `ba[acodec^=mp4a]`), 6.4 (`subPreset` incl. `word`; `lastUsed` unused; fake output folder), 6.5 (dnd-kit + shadcn Table instead of @reui), section 7 (C11 rows), AC-VID-10 part 1 → M5, the `queue` e2e project. Add every owner answer and planner default to `BRD.md` section 19 as new decisions (#84 onwards) and fix BRD 9.2 / 13 ("HTTP 403" row) and FR-OUT-7 placement per Q6.
- [ ] **Step 4: `docs/acceptance.md` "M4" rows:** AC-OUT-04 (Explorer opens with the file selected), real downloads of a Thai clip (mp4 opens in PowerPoint and VLC; VLC shows the embedded subtitle track and can turn it off), m4a/mp3/wav open in the default player, `แหล่งที่มา.txt` opens correctly in Notepad, the queue keeps working after closing the tab, 10 clips from a real playlist via W3 (BRD 16 M4 gate), stop.bat with a running job, tray shows the running count.
- [ ] **Step 5:** Mark the M4 items of `docs/m2-followups.md` (4xx retry → `E_YT_REFUSED`; "ประวัติ" menu fit) and `docs/m3-followups.md` (`E_TRANSLATION_BLOCKED` does not pause; expired-link retry rule now under the queue's 3 retries) as done; create `docs/m4-followups.md` for anything deferred. `README.md`: the `queue` e2e project and that parallel `E2E_PORT` runs must be ≥ 2 apart; where downloaded files go.
- [ ] **Step 6: Final verification:** full pytest `-W error`; web typecheck/lint/test/build; gzip ≤ 400 KB; `npm run e2e` (both projects); `uv run pytest -m network …` result recorded.
- [ ] **Step 7: Live preview for Pete** (memory rule "Preview after QA"): start `YT_TOOLKIT_DATA_ROOT=<temp> uv run python -m yttoolkit serve --port 8791` (real YouTube, real ffmpeg), open it in the preview browser, and walk the "M4" acceptance rows as a user; leave it running for Pete and give him the URL. Stop it later by PID.
- [ ] **Step 8: Commit** `docs: M4 PRD/BRD/acceptance updates, network download tests` and `build(web): web/dist for M4`.

---

## AC coverage

| AC | Test (level) | Task |
|---|---|---|
| AC-VID-01, 02, 03, 04, 05, 09 | `tests/network/test_download_network.py` (N) · AC-VID-09 also `test_media_ffmpeg.py` | T20, T5 |
| AC-VID-06 | `test_download_choice.py` (U) · `test_handlers.py` | T4, T10 |
| AC-VID-07 | `download-tabs.spec.ts` (E) | T15 |
| AC-VID-08 | `test_download_choice.py` (U) · network (N) · handler name suffix | T4, T10, T20 |
| AC-VID-10 | part 2: `test_jobs_api.py` (A) · part 1: M5 | T11 |
| AC-AUD-01..03 | `test_media_ffmpeg.py` (real ffmpeg) + network (N) | T5, T20 |
| AC-AUD-04 | `download-options.test.ts` (U) · `download-tabs.spec.ts` (E) | T8, T15 |
| AC-Q-01, 02, 03 | `test_queue.py` (U) · AC-Q-03 also `test_jobs_api.py` (A) and `queue-flow.spec.ts` | T11, T14 |
| AC-Q-04 | `queue-flow.spec.ts` (E) | T14 |
| AC-Q-05 | `test_queue_serve.py` (A) · `test_jobs_store.py` · `test_queue.py` | T18, T1, T11 |
| AC-Q-06 | `queue-flow.spec.ts` (E) · `test_jobs_store.py` | T14, T1 |
| AC-Q-07 | `test_queue.py` (real threads) · `test_media_ffmpeg.py` cancel | T11, T5 |
| AC-Q-08 | `test_events.py` (U) | T6 |
| AC-OUT-01, 02, 03, 06, 07 | `test_files.py` (U) · AC-OUT-07 also `test_video_meta.py` | T3, T4 |
| AC-OUT-04 | `docs/acceptance.md` (M) | T20 |
| AC-OUT-05 | `queue-history.spec.ts` (E) + existing M2 offline-fallback tests (A) | T13 |
| AC-OUT-08 | `clip-info.spec.ts` (E) | T16 |
| AC-SEC-05 | `test_media_args.py`, `test_no_shell.py` (U) | T5 |
| AC-SET-01 | `test_settings_api.py` (A) · `settings-general.spec.ts` (E) · `test_queue.py` | T2, T17, T11 |
