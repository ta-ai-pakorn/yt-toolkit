# M6 round A: paste button, filename style, clearing temporary data, settings backup Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (chosen execution method: subagent-driven development with parallel lanes). Steps use checkbox (`- [ ]`) syntax for tracking. Tasks inside one wave run as parallel subagents, each in its own controller-created git worktree (see "Waves" and "Lane rules"). Every task is reviewed by a reviewer subagent before its wave closes.

**Goal:** A "วาง" button in W1 that reads the clipboard only on click; a filename style (`title` / `title-channel` / `title-quality`) with a live example computed in the browser and snapshotted on each job; a "ข้อมูลในเครื่อง" section that clears temporary data safely while jobs and captures run; and settings backup / import with all-or-nothing validation.

**Spec:** `docs/superpowers/specs/2026-10-14-m6a-daily-conveniences-design.md` (binding: owner decisions D1-D9, constraints C1-C12, Thai copy §9 used verbatim, spec questions Q1-Q4 answered in §11). Also read `PRD.md` §6.1 / §6.2 / §6.4 / §7 and `docs/acceptance.md` "M6 รอบ A". The PRD and acceptance updates were made in the spec commits (`1151343`, `344567b`); no task edits `PRD.md` or `docs/acceptance.md`.

**Out of scope (round A):** multi-site support (C12, spec §10), renaming existing files when the style changes, a style per job in W2 / W3, clearing the ffmpeg install leftovers in `work/`, `run/logs` or `videos` rows, the statistics tab and the rest of M6, phone layouts (C8), any change to BRD.

**Architecture:**
- **One naming rule, two languages (T1, T8).** `core/files.plan_names(base_len, title, clip_id, *, suffix, ext, style, uploader, quality) -> (folder, file)`; `plan_output` becomes a thin wrapper (positional signature kept, new keywords). `web/src/lib/filename.ts` `planNames` mirrors it character for character; `tests/fixtures/names/cases.json` (input) + `golden.json` (generated from Python) pin both (C10).
- **Style snapshot (T2).** DB schema v3 adds `jobs.filename_style` (frozen `_JOBS_V2` keeps v1 → v2 → v3 working); `QueueRunner._start` writes `job.filename_style or settings.filename_style()` on the first start, every retry keeps it; `JobContext.filename_style`. `job_titles(..., channel)` + `JobStore.channel_of` so log lines and reports also hide the channel name.
- **History channel (T3).** `GET /history` items carry `channel` (the example uses the latest opened clip).
- **Web foundation (T4).** Every new Thai string in `th.ts`, `HistoryItem.channel`, `lib/settings-api.ts` (export / import / storage calls), `isSupportedLink` (C12), shared `recentQuery()`.
- **Names on disk (T5).** `_Clip.style` / `_Clip.uploader`, `_finish(..., quality)`; quality labels `(1080p)` from the downloaded file's short side, `(mp3 192k)` / `(m4a 128k)` through `standard_kbps` (Pete Q4 = B), `(wav)`; `MediaFacts.abr_kbps` read in `core/extractor.py` only (C3).
- **Settings backup / import (T6).** `GET /api/settings/export` (dated attachment), async `POST /api/settings/import` (1 MB cap → 413, UTF-8 with BOM, NaN rejected), `SettingsStore.import_settings` (all-or-nothing, unknown keys skipped, unusable `outputDir` → warning), `E_SETTINGS_INVALID` in `MESSAGES`.
- **Clearing temporary data (T7).** `core/storage.py` `StorageService.usage()` / `clear()` with the two-phase rename-then-delete under `QueueRunner.hold_active()` + `CaptureService.hold_active()`; `db.cache_folder` (the one id + containment check, C12); `api/storage.py`; startup sweep of `.clear-*`.
- **Web features (T8-T10, T12).** `filename.ts`; the paste button (`pages/home/paste-button.ts` + `home.tsx`); the "ข้อมูลในเครื่อง" section (`local-data.ts` + `local-data-section.tsx`); the filename-style field with its example (`filename-example.ts` + `filename-style-field.tsx`).
- **Sweep, canary, e2e (T11, T13, T14).** Style-aware `toolkit_name_pattern`; the privacy canary covers export and storage; chromium e2e for paste and the General tab, all writes mocked.

**Tech Stack:** unchanged (Python 3.13 + uv, FastAPI, yt-dlp as a library, SQLite, React ^19.2 + Vite + Tailwind v4 + shadcn/Base UI + react-query 5 + sonner 2, Vitest (node), Playwright + axe). No new Python or npm dependency (C11).

---

## Owner answers and decisions (Pete, 2026-10-14; spec D1-D9 and §11, all binding)

- **D1 / Q1 (paste replaces the box):** link → fill + analyze at once; other text → fill only; `readText()` only on click; denied / unsupported → the PRD hint under the box + focus, no red error, no toast. T4 (`isSupportedLink`, copy), T9 (button), T14 (e2e).
- **D2 / Q2 (what "clear" clears):** `data/cache/<id>/` and stale `work/` dirs; never an active job's or capture's cache / work dir, outputs, `app.db`, `data/visitor-session.*`, `run/logs`. T7.
- **D3 / Q3 (which files get the style):** `title-channel` = every title-based file; `title-quality` = video and audio only; chapter split, captures, sharp dir and clip folder unchanged; cut the title first, then the channel. T1, T5.
- **D4 (snapshot on the job):** first start fixes the style; retries keep it; the sweep reads it. T2, T11.
- **D5 (example without an API call):** TS mirror + golden parity; latest opened clip else the Thai sample. T1, T8, T12.
- **D6 (backup / import):** shape, 1 MB / 413, all-or-nothing, unknown keys skipped, unusable `outputDir` = warning, hook fired, `E_SETTINGS_INVALID`. T6, T10.
- **D7 (storage API):** `GET /storage`, `POST /storage/clear`, `_remove_cache_folder` safety reused, ±1 %, running job safe. T7.
- **D8 (UI):** "ข้อมูลในเครื่อง" section and the style Select + example in the General tab, M6-B error toasts, 640 px. T10, T12, T14.
- **D9 (future sites, C12):** no multi-site work; nothing new paints the app into a YouTube-only corner. T1 (opaque `clip_id`, neutral `uploader`), T4 (`isSupportedLink`), T6 (`app` + `schema` only), T7 (`cache_folder`).
- **Spec Q1 = B:** sample `สอนทำกับข้าวง่าย ๆ ใน 10 นาที`, channel `ครัวบ้านเรา`. T4 copy, T12.
- **Spec Q2 = B:** import success toast `นำเข้าค่าตั้งแล้ว`. T4 copy, T10.
- **Spec Q3:** kept-folder warning `นำเข้าค่าตั้งแล้ว แต่ใช้โฟลเดอร์ผลลัพธ์ในไฟล์บนเครื่องนี้ไม่ได้ จึงใช้โฟลเดอร์เดิมต่อ`, a warning toast that stays until dismissed. T4 copy, T10.
- **Spec Q4 = B:** nearest of 32/48/64/96/128/160/192/256/320, tie → higher, same function for mp3. T5.

## Planner rulings (resolutions of spec gaps; Pete can still object)

- **P1 — `standard_kbps` returns `int | None`.** Spec §2.3 types it `-> int` but also says a non-finite or non-positive value "is treated as unknown (label `m4a`)". `None` = unknown; `_audio_quality` then writes `m4a`.
- **P2 — a cut m4a is labelled by the re-encoded bitrate.** `media.cut` re-encodes AAC at `CUT_AAC_KBPS` (192) when a range or ads cut is applied (`media.py:338`), so the source `abr` would be wrong. `_audio_quality(..., recoded=cut.path != result.path)` gives `(m4a 192k)` for a cut file and the source bitrate otherwise.
- **P3 — `files.NAME_STYLES`.** Spec §2.2 says `files` imports nothing from `settings`, so `files.py` keeps its own tuple; T1 pins `files.NAME_STYLES == settings.FILENAME_STYLES`.
- **P4 — web `FILENAME_STYLES` lives in `lib/filename.ts`.** Spec §2.6 names `general-form.ts`; `general-form.ts` re-exports it (`export { FILENAME_STYLES } from "@/lib/filename"`) so the Select and the mirror share one list.
- **P5 — an empty title cut skips the channel steps.** Spec §2.2 step 9.2 can cut a title that starts with dots (`........abc`) to `""`; then steps 9.2-9.3 are skipped and step 9.4 (drop the channel) runs. Both languages, pinned by the golden case `dots-title-long-uploader`.
- **P6 — every fake `JobContext` gets `filename_style`.** Handlers read `ctx.filename_style` (a `JobContext` Protocol attribute, no `getattr` fallback); T5 adds `self.filename_style = "title"` to the seven fake contexts (`tests/helpers_sharp.py`, `test_handlers.py`, `test_handlers_account.py`, `test_lifecycle.py`, three `tests/network/` files).
- **P7 — the sweep dedupes on (folder, style, channel).** Two interrupted jobs of one clip with different styles are both swept (spec §6 "two jobs of one clip, different styles"); the sharp and chapter sweeps stay once per folder. `channel_of` is read only for `title-channel`.
- **P8 — `toolkit_name_pattern` rejects an unknown style** with `ValueError` (programming error, like `plan_names`).
- **P9 — the report reads the channel from the row it already reads.** `api/diagnostics._video_row` returns `(title, chapters_json, channel)` instead of a second `store.channel_of` call (`ctx.queue` may be `None` there). The queue's three call sites use `store.channel_of` as the spec says.
- **P10 — the capture work-dir name is chosen before `_capture_locked`.** `_current = (video_id, tmp.name)` must be set before the folder exists (spec §3.2), so `tmp` moves to `_capture_once` and `_capture_locked(video_id, title, t_ms, tmp)` takes it.
- **P11 — `ChoiceSelect` moves to `pages/settings/choice-select.tsx`** so `filename-style-field.tsx` can use it without a circular import with `general-panel.tsx`.
- **P12 — the import success toast is `นำเข้าค่าตั้งแล้ว`.** Spec §7.4's e2e line still says "บันทึกแล้ว"; Pete Q2 = B wins.
- **P13 — the kept-folder warning is dismissed with "ปิด".** "Stays until dismissed" (spec §4.3): `toast.warning` + `PLAIN_TOAST` + `duration: Infinity` + `action: { label: th.common.close }`, the same control as the account-removed toast (`use-account.ts:14-20`). No new copy.
- **P14 — a failed clear closes the dialog and refetches the size** (spec silent on failure), then shows the M6-B error toast.
- **P15 — the paste e2e stubs `navigator.clipboard.readText`.** The OS clipboard is shared by the four parallel Playwright workers (other specs write it), so `home-paste.spec.ts` replaces `readText` with `addInitScript` and counts calls; the real browser permission prompt is the manual check in `docs/acceptance.md` AC-IN-08/09.
- **P16 — chromium e2e mock every write and every storage call.** A real `POST /api/storage/clear` would wipe the fake backend's cache that parallel specs read; a real import would rewrite global settings. `settings-local-data.spec.ts` mocks `/api/settings`, `/api/settings/import`, `/api/settings/export`, `/api/storage*` and `/api/history`.
- **P17 — no backslash-u escapes in this plan's code.** Some tool layers turn a backslash-u-XXXX sequence in a tool argument into the character itself, which would put raw control characters into JSON (invalid) or source files. TS builds such strings with `String.fromCodePoint`, Python with `chr()`; `cases.json` is written by a one-off generator (Task 1, Step 1) and checked by sha256; `golden.json` is generated by the golden test.
- **P18 — `SettingsStore._save(clean)`** is the shared transaction of `patch` and `import_settings` (spec §4.2 step 4 "the same SQL as patch"); `patch` behaves as before.
- **P19 — `SettingsStore.exportable()`, `export_document(settings, now)`, `export_file_name(now)`** make the export testable; `exportedAt` is UTC, the file name uses the local date (spec §4.1).
- **P20 — fixed import details.** `"not UTF-8"`, `"not JSON"`, `"file must be a JSON object"`, `"app invalid"`, `"schema invalid"`, `"settings invalid"`, `"<key>: invalid value"`, `"file larger than 1048576 bytes"` (413). A file of exactly 1 MB is read.
- **P21 — links in the storage roots.** A top-level symlink or junction is "other" (counted 0, never cleared); `tree_bytes` never follows a symlink or a junction (`Path.is_junction()` / `DirEntry.is_junction()`, Python ≥ 3.12, C2-safe).
- **P22 — `work/.clear-*` is counted reclaimable and cleared** (spec §3.1 table); only `data/cache/.clear-*` needs the startup sweep (`QueueRunner.recover` already empties `work/`). `lifecycle.sweep_clear_once` mirrors `sweep_sharp_cache_once` (log-only on failure).
- **P23 — the stale cache-image row of spec §3.3** is tested in `tests/api/test_storage_api.py` (needs `make_client`); the other §3.3 rows are in `tests/unit/test_storage_readers.py`.
- **P24 — the General tab has eight fields now.** Skeleton count 7 → 8, the `GeneralKey` comment, and the "เจ็ดช่อง" test in `settings-general.spec.ts` (T14) is extended.
- **P25 — `HistoryItem.channel` is required**, so `web/e2e/history.spec.ts`'s factory gets `channel: ""` in T4 (typecheck).
- **P26 — the example ignores group folders.** `exampleFileName` uses `baseLen = outputDir.length`; a `PathTooLongError` retries with `baseLen: 0` (spec §2.6).
- **P27 — `recentQuery()` uses `queryOptions`** and `RECENT_LIMIT = 5` is exported; the key is unchanged (`["history", { limit: 5, scope: "opened" }]`).
- **P28 — the paste hint also hides after an `empty` click** (spec §1.3: "hides on the next non-denied click").
- **P29 — `readClipboard(deps)`:** `deps` with the key `clipboard` set to `undefined` = no clipboard (testable); no `deps` = `navigator.clipboard`.
- **P30 — `list.spec.ts` focus walk.** Two existing W1 tests focus "วิเคราะห์" and press Shift+Tab to reach the box; the new "วาง" button sits between them (spec §1.3 "before วิเคราะห์"), so T9 starts the walk from "วาง". Found by the prototype's full e2e run.
- **P31 — pre-existing timing flake.** `download-tabs.spec.ts` (W2, untouched here) failed one different test in each of two 4-worker runs and passed 29/29 with `--workers=2`; a gate that sees it reruns that file once with `--workers=2` before blaming a lane.

---

## Waves

Integration branch: `m6a-daily` (already checked out in the main checkout; the spec commits end at `344567b`; this plan is the next commit).

| Wave | Lanes (one worktree each, file sets disjoint, run in parallel) | Depends on |
|---|---|---|
| 1 | T1 `plan_names` + golden fixtures · T2 schema v3 + style snapshot + channel scrub · T3 history `channel` · T4 web foundation (copy, types, API client, `isSupportedLink`, `recentQuery`) | plan |
| 2 | T5 names on disk (handlers, quality labels) · T6 settings backup / import · T7 clearing temporary data (storage) · T8 `lib/filename.ts` mirror · T9 paste button · T10 "ข้อมูลในเครื่อง" section | gate 1 (T5←T1,T2 · T6←T2 · T7←T2 · T8←T1 fixtures · T9←T4 · T10←T4) |
| 3 | T11 style-aware leftover sweep · T12 filename-style field + example · T13 privacy canary · T14 chromium e2e | gate 2 (T11←T2 · T12←T4,T8,T10 · T13←T6,T7 · T14←T9,T10,T12 at runtime; the spec files only need T4 names) |
| final | controller: merge, full checks, `npm run build`, `npm run e2e`, commit `web/dist`, reviews, live preview for Pete | gate 3 |

**Merge order inside each wave** (no two lanes share a file, so the order only keeps history readable): wave 1 T1 → T2 → T3 → T4; wave 2 T5 → T6 → T7 → T8 → T9 → T10; wave 3 T11 → T12 → T13 → T14. A conflict means the plan is wrong: stop and report.
**Critical path:** T2 → T7 → T13 (backend) and T1 → T8 → T12 → T14 (web).
**Counts:** 3 waves + final gate · 14 tasks (4 + 6 + 4 lanes).

### Lane rules (every task)
1. **Worktree and branch.** The controller creates one worktree per lane **before** dispatching it: `git worktree add .claude/worktrees/m6a-t<N> -b m6a/t<N>-<slug> m6a-daily` (branched from the head of `m6a-daily` at the start of the wave) and gives the lane its absolute path as `WORKTREE`. The harness option `isolation: "worktree"` is not used. The lane starts **every** shell command with `cd "$WORKTREE" &&` and edits files only by absolute path under `WORKTREE`. Never switch the main checkout's branch. For web lanes the controller runs `cd "$WORKTREE/web" && npm ci` once before dispatch; for Python lanes `cd "$WORKTREE" && uv sync --frozen`.
2. **Files.** A task creates or modifies **only** the files in its **Files** list. Needing another file is a plan bug: stop and report it.
3. **Shared files have exactly one owner per wave:**

   | File | W1 | W2 | W3 |
   |---|---|---|---|
   | `web/src/i18n/th.ts` (every new key of spec §9) | T4 | — | — |
   | `tests/conftest.py`, `tests/api/conftest.py` | — (no task edits them) | — | — |
   | `PRD.md`, `docs/acceptance.md`, `BRD.md` | — (done in the spec commits) | — | — |
   | `src/yttoolkit/core/db.py`, `tests/unit/test_db.py` | T2 (schema v3) | T7 (`cache_folder`) | — |
   | `src/yttoolkit/core/queue.py`, `tests/unit/test_queue.py` | T2 (snapshot, `job_titles` channel) | T7 (`hold_active`, `_JobContext.video_id`) | — |
   | `src/yttoolkit/core/settings.py`, `tests/unit/test_settings.py` | T2 (`filename_style()`) | T6 (`import_settings`) | — |
   | `src/yttoolkit/core/jobs.py`, `tests/unit/test_jobs_store.py`, `src/yttoolkit/api/diagnostics.py`, `tests/api/test_diagnostics_api.py` | T2 | — | — |
   | `src/yttoolkit/core/files.py`, `tests/fixtures/names/*`, `tests/unit/test_names_golden.py` | T1 | — | — |
   | `src/yttoolkit/core/videos.py`, `tests/unit/test_videos.py`, `tests/api/test_history_api.py`, `tests/api/test_videos_api.py` | T3 | — | — |
   | `web/src/lib/{types,settings-api,paste}.ts` (+ tests), `web/src/pages/history/queries.ts` (+ test), `web/src/pages/home/recent.tsx`, `web/e2e/history.spec.ts` | T4 | — | — |
   | `core/{handlers,download,extractor}.py`, `tests/helpers_sharp.py`, `tests/network/*.py`, `tests/unit/test_{handlers,handlers_account,handlers_sharp,extractor_download,download_choice}.py` | — | T5 | — |
   | `src/yttoolkit/lifecycle.py` | — | T7 (startup sweep) | T11 (sweep patterns) |
   | `tests/unit/test_lifecycle.py` | — | T5 (fake context only) | T11 |
   | `api/settings.py`, `core/yterrors.py`, `tests/api/test_settings_api.py` | — | T6 | — |
   | `core/{storage,capture}.py`, `api/storage.py`, `app.py`, `tests/unit/test_{storage,storage_readers,capture}.py`, `tests/api/test_storage_api.py` | — | T7 | — |
   | `web/src/lib/filename.ts` (+ 2 tests) | — | T8 | — |
   | `web/src/pages/home.tsx`, `pages/home/{paste-button.ts,paste-button.test.ts,use-analyze.tsx}`, `web/e2e/list.spec.ts` | — | T9 | — |
   | `web/src/pages/settings/general-panel.tsx` | — | T10 (section) | T12 (style field, `ChoiceSelect` move) |
   | `web/src/pages/settings/local-data{.ts,.test.ts,-section.tsx}` | — | T10 | — |
   | `web/src/pages/settings/{general-form.ts,general-form.test.ts,choice-select.tsx,filename-example.ts,filename-example.test.ts,filename-style-field.tsx}` | — | — | T12 |
   | `tests/integration/test_account_privacy.py` | — | — | T13 |
   | `web/e2e/{home-paste,settings-local-data,settings-general}.spec.ts` | — | — | T14 |
   | `web/dist/**` | final gate only; **no lane builds into or commits `web/dist`** | | |

   A lane that needs a Thai string that is not in spec §9 stops and asks the controller (never invent copy).
4. **Tests.**
   - Python lanes run their own tests first, then `cd "$WORKTREE" && uv run pytest -q -W error -p no:cacheprovider`.
   - Web lanes run `cd "$WORKTREE/web" && npm run typecheck && npm run lint && npm test`.
   - Lanes **do not run Playwright.** Specs are written, typechecked and linted in the lane; the controller runs them at gates.
   - The `queue` Playwright project is **always** run with `--workers=1` (the npm `e2e` script does this); never two Playwright invocations at once. `playwright.config.ts` caps workers at 4 (unchanged).
   - **No spec in the `chromium` project creates a real job or writes shared backend state.** Chromium specs mock every write with `page.route` (P16).
5. **Processes.** No lane starts a server. Never touch the owner's app on port 8787 (the `8787` in `tests/api/conftest.py` is only a TestClient base URL, nothing listens). Kill processes by PID only. Never `shell=True`.
6. **Commits.** Every commit message ends with exactly `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`. Use `git commit -F- <<'EOF' … EOF`.
7. **Line endings.** LF everywhere (`.gitattributes` `* text=auto eol=lf`); edit with the Edit tool; new files LF. Check with `git diff --check` before committing.
8. **Backslashes.** Python and TS literals below contain backslashes on purpose (`"\\"`, `r"\d{3,4}p"`, `"D:\\a"`). Copy them with the Edit/Write tool exactly as printed, never through a shell heredoc.
9. **No backslash-u escapes (P17).** Never type a backslash followed by `u` and four hex digits in a tool argument: a tool layer may turn it into the raw character. The code in this plan has none; keep it that way. After writing, `cd "$WORKTREE" && git diff | grep -nP '\\u[0-9a-fA-F]{4}'` must print nothing (the only escapes allowed are the ones inside `tests/fixtures/names/cases.json`, which the generator writes).
10. **Goldens.** `tests/fixtures/names/golden.json` is only ever written by `YT_UPDATE_GOLDEN=1 uv run pytest tests/unit/test_names_golden.py` in T1; that run ends red on purpose (`test_zz_golden_was_not_regenerated`). No other lane regenerates or edits it.

### Wave gate procedure (controller, serial)
1. Merge every lane branch of the wave into `m6a-daily` in the merge order above with `git merge --no-ff m6a/t<N>-<slug>`; then `git worktree remove .claude/worktrees/m6a-t<N>`.
2. `uv sync --frozen && uv run pytest -q -W error -p no:cacheprovider` (must pass).
3. `cd web && npm ci && npm run typecheck && npm run lint && npm test`.
4. Gate 2 only: `cd web && npm run build` then `npx playwright test --project=chromium e2e/home.spec.ts e2e/list.spec.ts e2e/history.spec.ts e2e/settings-general.spec.ts e2e/nav.spec.ts` (existing specs still pass with the new button and section) and `npx playwright test --project=queue --workers=1` (real jobs now get the snapshot and the styled names). Then `git checkout -- web/dist && git clean -fdq web/dist` (never commit `web/dist` at a gate).
5. Two-stage review (spec compliance, then code quality) per task of the wave; fix findings in the owning lane before the next wave.

### Final gate (controller, after wave 3)
1. Merge T11 → T12 → T13 → T14 (`--no-ff`), then steps 2-3 above.
2. `cd web && npm run build` then `npm run e2e` (chromium on `E2E_PORT` 8799, then queue on 8800 with `--workers=1`). A failing `home-paste.spec.ts` goes back to T9 (or T4 for copy), `settings-local-data.spec.ts` to T10 (section) or T12 (style field), `settings-general.spec.ts` / `list.spec.ts` to the lane named in the failing assertion. `download-tabs.spec.ts` flakes: P31.
3. Check total JS gzip ≤ 400 KB excluding fonts (PRD 6.5).
4. Commit the rebuilt `web/dist` as `build(web): web/dist after M6 round A` (with the trailer).
5. Reviews, then a live preview for Pete on port 8791 in fake mode (memory rule "preview after QA"): W1 "วาง" with a link and with plain text (allow and block the permission in the browser); Settings › ทั่วไป: change the style and watch the example; "ล้างข้อมูลชั่วคราว" with a real clip cache, confirm; "สำรองค่าตั้ง" then "นำเข้าค่าตั้ง" the same file, then a file with `outputDir` = `Q:\YT`; a 640 px window. Then Pete runs `docs/acceptance.md` "M6 รอบ A" on Windows.
6. Ask Pete how to finish the milestone branch (memory: he usually picks merge + push, still ask) and give him the milestone progress report.

---

## Verified facts (read on 2026-10-14 at `344567b`; every task below was built as a scratch prototype on this tree)
- **Prototype method.** A detached worktree at `344567b` received the 14 tasks as 14 commits (one per task, in the merge order above). Each task was then re-applied **alone** on its wave base (wave 1 = `344567b`, wave 2 = wave 1 merged, wave 3 = waves 1-2 merged) and its own tests were run twice: with only its test files (the failures listed in each task's Step 2) and with the whole task (the passes in Step 4). The worktree was removed afterwards.
- **Prototype results (all tasks applied):** @@FACT_RESULTS@@
- **Replace blocks.** Every "Replace (n) … with …" block below was generated from the prototype diff. Each old text occurs exactly once in its file at the task's wave base, and applying the blocks of a file in order rebuilds the prototype file byte for byte. @@FACT_BLOCKS@@
- **Naming.** `core/files.py:103-128` `plan_output` (budget `PATH_LIMIT - (base_len + 1) - len(" [<id>]") - 1 - TAIL_RESERVE - UNIQUE_RESERVE`, `cap = budget // 2`, `file_cap`); callers that only use `.parent`: `plan_chapter_output :154`, `plan_sharp_dir :169`, `handlers._finish_chapters`, `capture.py:405`, `:480`, `lifecycle._clip_folders`. `safe_component` collapses `\s` (Python: 29 code points incl. U+001C-U+001F, U+0085; not U+FEFF) and drops `Cc`/`Cf`/`Cs`.
- **Queue.** `core/queue.py:359-366` `_start` (settings read, `transition(job.id, "running")`, `_JobContext(self, job, workdir, output_root)`, `self._active[job.id] = ctx` under `self._lock`, an `RLock` that `tick` also holds); `JobStore.requeue` clears `_REQUEUE_CLEARS` only (no `filename_style`); `transition` writes `_FIELD_COLUMNS`. `tests/unit/test_queue.py` `StubSettings`, `runner_factory`, `ScriptedHandler`; YouTube kinds wait 2-5 s (`r.clock.t += 10` to pass the gap).
- **DB.** `SCHEMA_VERSION = 2`, `_JOBS` used by both `_SCHEMA` and `_MIGRATIONS[2]` (so it must be frozen as `_JOBS_V2` before v3 adds a column); three tests in `test_db.py` pin version 2.
- **Handlers.** `_Clip` (`handlers.py:153`), `_start` (`:180`), `_finish` (`:539`), `_video` passes `result.media`; seven fake `JobContext` classes in tests (P6); `StubDownloader` in `test_handlers.py` returns no `media`. `media.cut` re-encodes AAC at `CUT_AAC_KBPS = 192` (P2).
- **Settings.** `SettingsStore.patch` (`settings.py:214-243`) validates all keys, then `ensure_writable` outside the lock, then one transaction; `_validate_output_dir` rejects non-absolute paths (`/Users/...` on Windows). `api/settings.py` is 62 lines (replaced whole in T6). `api/videos.attachment_header(fallback, filename)`.
- **Storage.** `_remove_cache_folder` (`db.py:206-222`) owns the `VIDEO_ID` + `resolve()` containment check; `CaptureService._busy` / `_guard` (`capture.py:199-207`), `_capture_locked` creates `work/capture-<hex>` (`:294`); `sharp_store.TMP_PREFIX = "sharp.tmp-"`, storyboard staging `storyboard.tmp-<hex>`; `QueueRunner.recover` empties `work/`.
- **Web.** `home.tsx:130-141` addon row; `use-analyze.tsx:152` global paste; `recent.tsx:21-25` inline query; `general-panel.tsx` `ChoiceSelect` (private), skeleton of 7; `general-form.ts` `GeneralKey`; `lib/download.ts` `downloadFile(url, fallbackName, deps)`; `components/error-report/{error-toast.tsx,model.ts}` `showErrorToast`, `PLAIN_TOAST`; `use-account.ts:14-20` the persistent toast with a "ปิด" action; `lib/format.ts` `formatBytes` (1.2 GB).
- **E2E.** `playwright.config.ts` `workers: 4`, chromium (`E2E_PORT` 8799) and queue (8800); `e2e/axe-settled.ts` `analyzeSettled`; `settings-general.spec.ts` `stubSettings` pattern; `list.spec.ts:384-385`, `:469-470` focus "วิเคราะห์" then Shift+Tab (P30).

---

## Global Constraints

**Carried over:** every Global Constraint of `docs/superpowers/plans/2026-10-12-m6b-error-report.md` (and through it M5-C … M1): Python 3.13 + uv; bind `127.0.0.1` only; error envelope `{"error":{"code","message","detail"}}`; `pathlib` everywhere; `core/` never imports `api/` or `platform/`; every screen has loading / empty / error / normal; no TODO comments; unit and API tests never touch the network; all web strings live in `web/src/i18n/th.ts`; backend user-facing messages live in `core/yterrors.MESSAGES`; at most one amber primary button per page area; every error the staff see uses the M6-B `showErrorToast` / `ErrorDetails` with a stable toast id.

**Project rules (owner, verbatim — hard rules):**
- Never use `shell=True` (no `os.system` / `os.popen`; external programs get an argument list). No new subprocess in this round (C1).
- Only `yttoolkit.platform` checks the OS (no `sys.platform`, `os.name`, `platform.system()` outside `src/yttoolkit/platform/`). The size walk uses `DirEntry.is_junction()` / `Path.is_junction()`, a cross-platform API, not an OS check (C2).
- `yt_dlp` may be imported only in `src/yttoolkit/core/extractor.py`. The audio bitrate fact is read there and passed out through `download.MediaFacts.abr_kbps` (C3).
- No clip titles, channel names, absolute paths, the token, or cookie names / values in logs, SSE, API errors or reports (C4). New log lines use ASCII `key=value` fields with counts and error class names only (`storage_clear freed= entries= skipped=`, `storage_skip reason=`, `storage_sweep removed=`). The import never echoes a value from the file in `detail`. The exported settings file is a user download and carries `outputDir` on purpose (FR-SET-7), nothing else personal.
- The privacy tests keep passing unchanged: `tests/unit/test_handlers.py` (`test_logs_have_no_absolute_paths`, `test_logs_have_no_clip_title`), `tests/unit/test_redact.py`, `tests/api/test_errors.py`, `tests/integration/test_account_privacy.py` (T13 only adds to it) (C5).
- LF line endings in every file except `*.bat`; the exported JSON is written with `\n` (C6).
- Thai UI copy only from the spec (§9), the PRD or the existing `th.ts`, never invented; buttons start with a verb, no "กรุณา", no "!" (C7).
- Every commit trailer is exactly `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
- Never touch port 8787; kill processes by PID only.
- Target a 640 px narrow window (or 200 % zoom): `document.documentElement.scrollWidth <= 640`; no new phone polish; the app is served on 127.0.0.1 only (C8).
- New POSTs live under `/api` (token + Origin by `LocalOnlyMiddleware`); the web calls them through `api()`; the export download uses `downloadFile` (C9).
- One naming rule, two languages: Python `files.plan_names` and TS `planNames` give the same output for every case in `tests/fixtures/names/cases.json`; `golden.json` is generated from Python and the TS test never edits it (C10).
- No new dependencies, Python or npm; Vitest stays node-only, component logic goes into `.ts` modules (C11).
- **Future sites (C12):** link detection goes through `isSupportedLink` only; `plan_names` / `planNames` take a neutral `uploader` and an opaque `clip_id` (no YouTube-id regex inside); the clear reuses `db.cache_folder` and adds no new place that hard-codes the 11-character id; the settings file has `app` + `schema` only; Thai label stays "ช่อง". Remaining YouTube-only assumptions: spec §10 (awareness only, no work).
- `web/dist` is committed only at the final gate, after `npm run build`.
- Chromium e2e specs never create real jobs and mock the API; the `queue` Playwright project runs with `--workers=1`; `playwright.config.ts` caps workers at 4.

**Tests:**
- Backend: `uv run pytest -q -W error -p no:cacheprovider` (no warnings).
- Web: `cd web && npm run typecheck && npm run lint && npm test` (ESLint 0 errors / 0 warnings).
- Final: `cd web && npm run build` then `npm run e2e`.

---

## Review Focus (inputs the spec implies that would most likely bite a real user)
1. **A job retried by another path after the style changed** (manual retry, the bot-check requeue, in-run `E_NETWORK` retries, a job queued before the change) → the retry keeps the first name and the sweep looks for that name. Pinned by T2 `test_a_retry_after_a_style_change_keeps_the_first_style`, `test_the_bot_check_requeue_keeps_the_first_style`, `test_network_retries_inside_one_run_keep_the_style`, `test_a_job_queued_before_a_style_change_uses_the_style_at_its_start`, `test_filename_style_is_written_on_start_and_survives_requeue`, and T11 `test_two_jobs_of_one_clip_with_different_styles_are_both_swept`.
2. **Clearing while another tab builds a clip's frames, or while a job or a capture runs** → no 500, the running work finishes, the next open rebuilds. Pinned by T7 `test_a_young_staging_folder_keeps_the_clip_and_an_old_one_does_not`, `test_ac_set_08_a_running_job_survives_a_clear_and_finishes`, `test_the_running_capture_keeps_its_clip_cache_and_work_dir`, `test_no_job_starts_while_the_active_set_is_held`, `test_a_capture_waits_while_the_active_set_is_held`, `test_a_stale_cache_image_url_is_404_after_a_clear`, and the §3.3 reader tests.
3. **A file held open on Windows during the clear** (Explorer thumbnail, a player) → `freedBytes` reports only what was really removed, the leftover is cleared next time or at startup. Pinned by T7 `test_a_folder_that_cannot_be_renamed_stays_and_is_not_counted`, `test_a_file_that_cannot_be_deleted_is_left_in_trash_and_not_counted`, `test_trash_left_in_the_cache_is_cleared_again`, `test_sweep_clear_leftovers_removes_only_our_trash`.
4. **A user's own file that looks like a styled toolkit name** (`<title> - notes.mp4`, `<title> (1080p) notes.docx`) and a done output → never deleted by the startup sweep. Pinned by T11 `test_title_channel_pattern` (`- notes.mp4` false), `test_title_quality_pattern`, `test_sweep_removes_leftovers_of_a_title_channel_job` (keeps a user file with content and the done output).
5. **A settings file from another machine or another app** (a macOS path, a missing drive, a newer `schema`, a JSON from another tool, a 2 MB file, a BOM, NaN) → old folder kept with the warning, or 422/413 with nothing changed and no value echoed. Pinned by T6 `test_an_output_dir_that_cannot_be_used_here_keeps_the_old_one`, `test_import_of_a_file_that_is_not_ours_is_invalid`, `test_import_of_a_bad_file_is_422_and_changes_nothing`, `test_import_above_one_megabyte_is_413_with_or_without_content_length`, `test_import_with_a_bom_is_accepted`, and T10 `importTooLarge` / T14 "ไฟล์ใหญ่กว่า 1 MB".

---

## Shared contracts (every lane codes against these)

### K1. Naming (`src/yttoolkit/core/files.py`, T1 · `web/src/lib/filename.ts`, T8)
```python
NAME_STYLES = ("title", "title-channel", "title-quality"); CHANNEL_SEP = " - "; QUALITY_LABEL = re.compile(r"[a-z0-9 ]{1,16}")
def plan_names(base_len: int, title: str, clip_id: str, *, suffix: str, ext: str, style: str = "title",
               uploader: str = "", quality: str | None = None) -> tuple[str, str]      # YtError E_OUTPUT_NOT_WRITABLE "path too long"
def plan_output(root, title, video_id, suffix, ext, group=None, *, style="title", uploader="", quality=None) -> Path
```
```ts
export type FilenameStyle = Settings["filenameStyle"]; export const FILENAME_STYLES: readonly ["title", "title-channel", "title-quality"]
export type NameInput = { baseLen: number; title: string; clipId: string; suffix: string; ext: string; style?: FilenameStyle; uploader?: string; quality?: string | null }
export class PathTooLongError extends Error {}   // message "path too long"
export function planNames(input: NameInput): { folder: string; file: string }
export function safeComponent(text: string, fallback: string): string
export function truncateTitle(text: string, limit: number): string
```
Fixtures: `tests/fixtures/names/cases.json` (60 `NameInput` + `name`), `golden.json` (`{name: {folder, file} | {error: "path too long"}}`).

### K2. Style snapshot (T2)
`db.SCHEMA_VERSION = 3`, `db._JOBS_V2` (frozen), `jobs.filename_style TEXT`; `Job.filename_style: str | None = None` (last field); `JobStore.transition(..., filename_style=...)`; `JobStore.channel_of(video_id) -> str`; `JobContext.filename_style: str`; `SettingsView.filename_style() -> str`; `SettingsStore.filename_style() -> str`; `queue.job_titles(job, chapters_json, channel="")`; `queue.log_job_failed(job, code, detail, exc, chapters_json=None, channel="")`.

### K3. History (T3)
`GET /api/history` items: `{videoId, title, channel, thumbnailUrl, durationS, outputs, lastAt}` (`channel` = `""` when unknown).

### K4. Web foundation (T4)
```ts
// th.home: paste, pasteDenied ("{key}") · th.general: filenameStyle, filenameStyles{title,"title-channel","title-quality"}, filenameExample ("{name}"),
//   filenameSample, filenameSampleChannel, localData, clearTemp ("{size}"), clearTempPlain, clearConfirmTitle ("{size}"), clearConfirmBody,
//   clearCancel, clearConfirm, cleared ("{size}"), backup, import, settingsInvalid, imported, importedKeptFolder
// lib/types.ts: HistoryItem.channel: string
// lib/paste.ts
export function isSupportedLink(text: string): boolean
// lib/settings-api.ts
export const MAX_SETTINGS_FILE_BYTES = 1_048_576; export const SETTINGS_FILE_FALLBACK = "yt-toolkit-settings.json"
export function exportSettings(deps?): Promise<string>
export type ImportResult = { settings: Settings; warnings: string[] }
export function importSettings(text: string, deps?): Promise<ImportResult>
export const STORAGE_KEY = ["storage"] as const
export type StorageUsage = { cacheBytes: number; workBytes: number; reclaimableBytes: number }
export function storageQuery(deps?): { queryKey: typeof STORAGE_KEY; queryFn: () => Promise<StorageUsage> }
export function clearStorage(deps?): Promise<{ freedBytes: number }>
// pages/history/queries.ts
export const RECENT_LIMIT = 5; export function recentQuery(limit = RECENT_LIMIT)   // key ["history", { limit, scope: "opened" }]
```

### K5. Names on disk (T5)
`download.MediaFacts.abr_kbps: float | None = None` (4th field); `handlers.STANDARD_KBPS`, `handlers.standard_kbps(value) -> int | None`; `_Clip.style`, `_Clip.uploader`; `_finish(..., quality: str | None = None)`; labels `"1080p"`, `"mp3 192k"`, `"m4a 128k"`, `"m4a"`, `"wav"`.

### K6. Settings backup / import (T6)
`settings.EXPORT_APP = "yt-toolkit"`, `EXPORT_SCHEMA = 1`; `SettingsStore.exportable() -> dict`, `SettingsStore.import_settings(doc) -> tuple[dict, list[str]]`, `SettingsError("E_SETTINGS_INVALID", detail, key=...)`; `api/settings.MAX_SETTINGS_IMPORT_BYTES = 1_048_576`, `export_document(settings, now)`, `export_file_name(now)`; routes `GET /api/settings/export`, `POST /api/settings/import` → `{settings, warnings}`; `MESSAGES["E_SETTINGS_INVALID"]`.

### K7. Storage (T7)
```python
# core/db.py
def cache_folder(root: Path, name: str) -> Path | None
# core/queue.py
@dataclass(frozen=True) class ActiveJobs: job_ids: frozenset[str]; video_ids: frozenset[str]
QueueRunner.hold_active() -> ContextManager[ActiveJobs]          # holds the queue RLock
# core/capture.py
CaptureService.hold_active() -> ContextManager[tuple[str, str] | None]   # (video_id, work dir name), holds _guard
# core/storage.py
STAGING_GRACE_S = 600; TRASH_PREFIX = ".clear-"
@dataclass(frozen=True) class StorageUsage: cache_bytes: int; work_bytes: int; reclaimable_bytes: int  # .to_api()
class StorageService(cache_root, work_root, *, queue, captures, now=time.time): usage() -> StorageUsage; clear() -> int
def tree_bytes(path: Path) -> int; def sweep_clear_leftovers(cache_root: Path) -> int
# lifecycle.py
def sweep_clear_once(cache_root: Path) -> None
```
Routes: `GET /api/storage` → `{cacheBytes, workBytes, reclaimableBytes}`; `POST /api/storage/clear` → `{freedBytes}`; both `Cache-Control: no-store`.

### K8. Web features (T8-T10, T12)
```ts
// pages/home/paste-button.ts
export type PasteOutcome = { kind: "analyze"; text: string } | { kind: "fill"; text: string } | { kind: "empty" } | { kind: "denied" }
export function readClipboard(deps?: { clipboard?: Pick<Clipboard, "readText"> | undefined }): Promise<PasteOutcome>
// pages/settings/local-data.ts
export const CLEAR_TOAST_ID = "storage-clear", IMPORT_TOAST_ID = "settings-import", EXPORT_TOAST_ID = "settings-export"
export const CLIP_CACHE_KEYS; export function forgetClipCaches(client): void
export function clearButton(usage?: StorageUsage): { label: string; size: string | null; disabled: boolean }
export function importTooLarge(file: Pick<Blob, "size">): boolean; export const TOO_LARGE_REQUEST: ReportRequest
export function importNotice(result: Pick<ImportResult, "warnings">): { kind: "success" | "warning"; message: string }
export function LocalDataSection(): JSX.Element                  // local-data-section.tsx, data-testid="local-data-actions"
// pages/settings/filename-example.ts
export const SAMPLE_CLIP_ID = "abcdefghijk"; export type ExampleClip = { title: string; channel: string; videoId: string }
export function exampleFileName(style: FilenameStyle, clip: ExampleClip | undefined, outputDir: string): string
// pages/settings/filename-style-field.tsx · choice-select.tsx
export function FilenameStyleField(props: { value: FilenameStyle; outputDir: string; onChange: (v: FilenameStyle) => void })
export function ChoiceSelect(props: { labelId; hintId?; value; options; onChange })
```
DOM ids: `paste-hint` (W1 hint, `role="status"`), `general-filename` (title), `general-filename-example` (example line). Report contexts: `settings-import`, `settings-export`, `storage-clear`.

---

## File structure

**Backend (new):** `core/storage.py`, `api/storage.py` (T7).
**Backend (modified):** `core/files.py` (T1) · `core/db.py`, `core/jobs.py`, `core/queue.py`, `core/settings.py`, `api/diagnostics.py` (T2) · `core/videos.py` (T3) · `core/handlers.py`, `core/download.py`, `core/extractor.py` (T5) · `core/settings.py`, `api/settings.py`, `core/yterrors.py` (T6) · `core/db.py`, `core/queue.py`, `core/capture.py`, `app.py`, `lifecycle.py` (T7) · `lifecycle.py` (T11).
**Tests (new):** `tests/unit/test_names_golden.py`, `tests/fixtures/names/{cases,golden}.json` (T1) · `tests/unit/test_storage.py`, `tests/unit/test_storage_readers.py`, `tests/api/test_storage_api.py` (T7).
**Tests (modified):** T2 `test_db`, `test_jobs_store`, `test_queue`, `test_settings`, `tests/api/test_diagnostics_api` · T3 `test_videos`, `tests/api/test_history_api`, `tests/api/test_videos_api` · T5 `test_handlers`, `test_handlers_account`, `test_handlers_sharp`, `helpers_sharp`, `test_lifecycle` (fake context), `test_extractor_download`, `test_download_choice`, three `tests/network/` files · T6 `test_settings`, `tests/api/test_settings_api` · T7 `test_queue`, `test_capture`, `test_db` · T11 `test_lifecycle` · T13 `tests/integration/test_account_privacy`.
**Web (new):** `lib/filename.ts` + 2 tests (T8) · `pages/home/paste-button.ts` + test (T9) · `pages/settings/local-data.ts` + test, `local-data-section.tsx` (T10) · `pages/settings/filename-example.ts` + test, `filename-style-field.tsx`, `choice-select.tsx` (T12) · `e2e/home-paste.spec.ts`, `e2e/settings-local-data.spec.ts` (T14).
**Web (modified):** `i18n/th.ts`, `lib/{types,settings-api,paste}.ts` (+ tests), `pages/history/queries.ts` (+ test), `pages/home/recent.tsx`, `e2e/history.spec.ts` (T4) · `pages/home.tsx`, `pages/home/use-analyze.tsx`, `e2e/list.spec.ts` (T9) · `pages/settings/general-panel.tsx` (T10, T12) · `pages/settings/general-form.ts` (+ test) (T12) · `e2e/settings-general.spec.ts` (T14).

---

**WIP:** the task sections (Task 1 … Task 14) are being generated from the prototype.
