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
- **Prototype results (all tasks applied):** `pytest -q -W error` 3,694 passed (46 network deselected); web `tsc -b` clean, `eslint .` clean, vitest 1,150 passed (68 files); after `npm run build`: Playwright chromium 563 passed of 566 on the first full 4-worker run — the 3 failures were `list.spec.ts:380`/`:465` (fixed by P30, then `list.spec.ts` + `home.spec.ts` 86/86) and one `download-tabs.spec.ts` timing flake (P31, 29/29 on rerun); the three new/changed specs 34/34; queue project (`--workers=1`) 38/38.
- **Replace blocks.** Every "Replace (n) … with …" block below was generated from the prototype diff. Each old text occurs exactly once in its file at the task's wave base, and applying the blocks of a file in order rebuilds the prototype file byte for byte. 135 replace blocks in total; 135 of them also occur exactly once at `344567b` (including the blocks of files a previous wave already changed: they only touch lines that the earlier wave left alone).
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

## Wave 1

### Task 1: One naming rule — `files.plan_names` and the golden fixtures (spec 2.2, 2.5; AC-OUT-09)

**Files:**
- Modify: `src/yttoolkit/core/files.py`
- Create: `tests/unit/test_names_golden.py`
- Create (generated, never hand-edited): `tests/fixtures/names/cases.json`, `tests/fixtures/names/golden.json`

**Interfaces:**
- Consumes: `files.safe_component`, `files.truncate_title`, `files._u16`, `files.group_folder_name`, the constants `PATH_LIMIT`, `TITLE_MAX`, `TAIL_RESERVE`, `TAIL_MAX`, `UNIQUE_RESERVE`, `_MIN_TITLE` (same module); `settings.FILENAME_STYLES` (only in the test).
- Produces: K1 Python side exactly — `NAME_STYLES`, `CHANNEL_SEP`, `QUALITY_LABEL`, `plan_names(...) -> (folder, file)`, `plan_output(..., *, style="title", uploader="", quality=None)`. The fixtures `cases.json` (60 cases) and `golden.json` that T8 reads.

- [ ] **Step 1: Generate the parity input `cases.json`**

The cases contain invisible characters (U+001C, U+FEFF, U+200B, U+3000, …). Write this one-off generator to the scratchpad (not into the repo) and run it from the worktree root. It uses `chr()` only (P17):
```python
"""Writes tests/fixtures/names/cases.json (M6 round A parity input). Run from the repo root:
    uv run python <this file>
Uses chr() for every invisible character, so the script itself contains no escape sequences."""

import json
import unicodedata
from pathlib import Path

ID = "dQw4w9WgXcQ"
STYLES = ("title", "title-channel", "title-quality")
AC_OUT_01 = 'ทดสอบ: "A/B" <ภาค 1>?'
LONG = "ก" * 300
SAMPLE = "สอนทำกับข้าวง่าย ๆ ใน 10 นาที"
LONGEST_SUFFIX = " (ไม่มีเสียง) (1.02.30-1.05.00) (ตัดโฆษณา)"
cases: list[dict] = []


def add(name, title, *, base=60, suffix="", ext="mp4", style="title", uploader="", quality=None, clip=ID):
    cases.append({"name": name, "baseLen": base, "title": title, "clipId": clip, "suffix": suffix, "ext": ext,
                  "style": style, "uploader": uploader, "quality": quality})


for s in STYLES:
    add(f"ac-out-01-mp4-{s}", AC_OUT_01, style=s, uploader="ช่อง: ทดสอบ/1", quality="1080p")
    add(f"ac-out-01-mp3-{s}", AC_OUT_01, ext="mp3", style=s, uploader="ช่อง: ทดสอบ/1", quality="mp3 192k")
    add(f"ac-out-02-mp4-{s}", LONG, suffix=" (ไม่มีเสียง)", style=s, uploader="ครัวบ้านเรา", quality="1080p")
    add(f"ac-out-02-mp3-{s}", LONG, ext="mp3", style=s, uploader="ครัวบ้านเรา", quality="mp3 192k")
    add(f"longest-suffix-{s}", LONG, suffix=LONGEST_SUFFIX, style=s, uploader="ครัวบ้านเรา", quality="1080p")
    add(f"subtitle-range-{s}", "ซับทดสอบ", suffix=" (01.30-05.00).th", ext="srt", style=s, uploader="ช่อง")
for b in (150, 151, 152):
    add(f"thai-marks-cut-b{b}", "กี่" * 100, base=b, style="title-channel", uploader="น้ำใจ")
    add(f"emoji-cut-b{b}", chr(0x1F600) * 100, base=b, style="title-channel", uploader=chr(0x1F600) + "ช่อง")
WS_TITLE = "".join([
    "a", chr(0x1C), "b", chr(0xFEFF), "c", chr(0x200B), "d", chr(0x09), "e  f", chr(0x3000), "g", chr(0xA0), "h",
    chr(0x85), "i", chr(0x180E), "j", chr(0x1F), "k", chr(0x2028), "l",
])
WS_UPLOADER = chr(0x09) + "ช่อง" + chr(0x3000) + " ทดสอบ" + chr(0x1C)
add("whitespace-classes", WS_TITLE, style="title-channel", uploader=WS_UPLOADER)
add("reserved-con", "CON", style="title-channel", uploader="NUL")
add("reserved-com1-txt", "com1.txt")
add("reserved-lpt-superscript", "LPT¹", style="title-quality", quality="1080p")
add("reserved-uploader", "Hi", style="title-channel", uploader="aux")
add("trailing-dots-spaces", "Hello world... . ", style="title-channel", uploader="ช่อง. . ")
add("empty-title", "", style="title-channel", uploader="ช่อง")
add("forbidden-only-title", '?:*"<>|', style="title-quality", quality="1080p")
add("empty-uploader", "คลิปทดสอบ", style="title-channel", uploader="")
add("forbidden-only-uploader", "คลิปทดสอบ", style="title-channel", uploader='?:*"<>|')
add("uploader-120-b60", "สอนทำกับข้าวง่าย ๆ ใน 10 นาที แบบละเอียดทุกขั้นตอน", style="title-channel", uploader="ช" * 120)
add("uploader-120-b150", "สอนทำกับข้าวง่าย ๆ ใน 10 นาที แบบละเอียดทุกขั้นตอน", base=150, style="title-channel",
    uploader="ช" * 120)
add("dots-title-long-uploader", "........abcdefgh", base=150, style="title-channel", uploader="ช" * 120)
add("note-title-channel", "โน้ตของคลิป", suffix=".note", ext="md", style="title-channel", uploader="ช่อง")
add("contact-sheet-title-channel", "ภาพรวม", suffix=" - contact sheet", ext="jpg", style="title-channel",
    uploader="ช่อง")
add("frames-zip-title-quality", "ภาพรวม", suffix=" - frames", ext="zip", style="title-quality")
add("quality-missing", "คลิปทดสอบ", style="title-quality")
add("quality-m4a", "คลิปทดสอบ", ext="m4a", style="title-quality", quality="m4a 128k")
add("quality-m4a-unknown", "คลิปทดสอบ", ext="m4a", style="title-quality", quality="m4a")
add("quality-wav", "คลิปทดสอบ", ext="wav", style="title-quality", quality="wav")
add("quality-ignored-for-title-channel", "คลิปทดสอบ", style="title-channel", uploader="ช่อง", quality="1080p")
add("channel-ignored-for-title-quality", "คลิปทดสอบ", style="title-quality", uploader="ช่อง", quality="1080p")
for b in (3, 60, 150, 200, 230):
    for s in ("title", "title-channel"):
        add(f"base-{b}-{s}", SAMPLE, base=b, style=s, uploader="ครัวบ้านเรา")
add("base-200-title-quality", SAMPLE, base=200, style="title-quality", quality="1080p")
add("opaque-clip-id", "", clip="ไอดี_ทดสอบ-01", style="title-quality", quality="1080p")
add("opaque-clip-id-titled", "คลิป", clip="ไอดี_ทดสอบ-01", style="title-channel", uploader="ช่อง")
add("sample-clip", SAMPLE, base=40, style="title-channel", uploader="ครัวบ้านเรา", clip="abcdefghijk")

names = [c["name"] for c in cases]
assert len(names) == len(set(names)) == 60


def visible(text: str) -> str:
    """JSON with every invisible character written as an escape (the file stays readable and diff-friendly)."""
    return "".join(f"{chr(92)}u{ord(c):04x}" if unicodedata.category(c)[0] in "CZ" and c != " " else c for c in text)


lines = [" " + visible(json.dumps(c, ensure_ascii=False)) for c in cases]
out = Path("tests/fixtures/names/cases.json")
out.parent.mkdir(parents=True, exist_ok=True)
out.write_bytes(("[\n" + ",\n".join(lines) + "\n]\n").encode("utf-8"))
print(f"wrote {out} ({len(cases)} cases)")
```
Run: `cd "$WORKTREE" && uv run python <scratchpad>/make_name_cases.py && sha256sum tests/fixtures/names/cases.json`
Expected: `wrote tests/fixtures/names/cases.json (60 cases)` and sha256 `7713db622570e32137d16a72880dfcff31687d98a90719df5da467cfcf4eaff3`. A different hash means the generator was mis-copied: compare it again with the block above.

- [ ] **Step 2: Write the failing tests**

Create `tests/unit/test_names_golden.py`:
```python
"""ชื่อโฟลเดอร์/ไฟล์ตามรูปแบบชื่อไฟล์ (M6 รอบ A spec 2.2 / 2.5, C10): files.plan_names ต้องตรงกับ golden ทุกตัวอักษร

tests/fixtures/names/cases.json = ข้อมูลเข้า (camelCase แบบเดียวกับ NameInput ของเว็บ) เขียนด้วยมือ
tests/fixtures/names/golden.json = ผลที่ถูกต้อง สร้างได้ทางเดียวคือรัน
`YT_UPDATE_GOLDEN=1 uv run pytest tests/unit/test_names_golden.py` (รอบนั้นจบแดงเสมอ ดู test_zz_...)
ฝั่งเว็บ (web/src/lib/filename-parity.test.ts) อ่านสองไฟล์นี้ไปเทียบกับ planNames จึงห้ามแก้ golden เพื่อให้เทสผ่าน
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from yttoolkit.core import files, settings
from yttoolkit.core.yterrors import YtError

NAMES = Path(__file__).resolve().parents[1] / "fixtures" / "names"
CASES_FILE = NAMES / "cases.json"
GOLDEN_FILE = NAMES / "golden.json"
UPDATE = os.environ.get("YT_UPDATE_GOLDEN") == "1"
_REGENERATED = False  # True เมื่อรอบนี้เขียน golden ใหม่ ทำให้เทสสุดท้ายของไฟล์ล้มเหลวโดยตั้งใจ

ID = "dQw4w9WgXcQ"
AC_OUT_01 = 'ทดสอบ: "A/B" <ภาค 1>?'
FORBIDDEN = set('\\/:*?"<>|')


def _cases() -> list[dict]:
    return json.loads(CASES_FILE.read_text(encoding="utf-8"))


def _expected(case: dict) -> dict:
    try:
        folder, file = files.plan_names(
            case["baseLen"], case["title"], case["clipId"], suffix=case["suffix"], ext=case["ext"],
            style=case["style"], uploader=case["uploader"], quality=case["quality"],
        )  # fmt: skip
    except YtError as exc:
        assert exc.code == "E_OUTPUT_NOT_WRITABLE"
        return {"error": exc.detail}
    return {"folder": folder, "file": file}


@pytest.fixture(scope="module", autouse=True)
def _update_golden():
    """YT_UPDATE_GOLDEN=1: เขียน golden ใหม่ก่อนเทสรัน ห้ามใช้เมื่อมี CI และรอบนั้นจบแดงเสมอ (ดู test_zz_...)"""
    global _REGENERATED
    if UPDATE:
        if os.environ.get("CI"):
            pytest.fail("YT_UPDATE_GOLDEN=1 is refused when CI is set: goldens are never regenerated in CI", pytrace=False)
        doc = {case["name"]: _expected(case) for case in _cases()}
        text = json.dumps(doc, ensure_ascii=False, indent=1) + "\n"
        GOLDEN_FILE.write_bytes(text.encode("utf-8"))
        _REGENERATED = True
    yield


def test_case_names_are_unique_and_every_case_has_a_golden():
    names = [case["name"] for case in _cases()]
    assert len(names) == len(set(names))
    assert GOLDEN_FILE.is_file(), "golden.json is missing: run with YT_UPDATE_GOLDEN=1"
    golden = json.loads(GOLDEN_FILE.read_text(encoding="utf-8"))
    assert sorted(golden) == sorted(names)


@pytest.mark.parametrize("case", _cases(), ids=lambda case: case["name"])
def test_plan_names_matches_golden(case):
    golden = json.loads(GOLDEN_FILE.read_text(encoding="utf-8"))
    assert _expected(case) == golden[case["name"]]


def test_name_styles_match_the_settings_choices():
    assert files.NAME_STYLES == settings.FILENAME_STYLES


# ---------- กฎที่เทสฝั่ง Python อย่างเดียว ----------


def _legacy_plan_output(root: Path, title: str, video_id: str, suffix: str, ext: str, group: str | None = None) -> Path:
    """สำเนาของ files.plan_output ก่อน M6 (ที่ 344567b) ทุกบรรทัด: ใช้ยืนยันว่าแบบ "title" ไม่เปลี่ยนชื่อของใคร"""
    tail = f"{suffix}.{ext}"
    base = root / files.group_folder_name(group) if group else root
    t = files.safe_component(title, video_id)
    budget = files.PATH_LIMIT - (files._u16(str(base)) + 1) - files._u16(f" [{video_id}]") - 1
    budget -= files.TAIL_RESERVE + files.UNIQUE_RESERVE
    cap = budget // 2
    short = ""
    if cap >= 8:
        short = files.truncate_title(t, min(files.TITLE_MAX, cap))
    if short:
        file_cap = budget - files._u16(short) + files.TAIL_RESERVE - files._u16(tail)
        stem = short if files._u16(short) <= file_cap else files.truncate_title(short, file_cap)
        planned = base / f"{short} [{video_id}]" / f"{stem or video_id}{tail}"
    else:
        planned = base / video_id / f"{video_id}{tail}"
    if files._u16(str(planned)) > files.PATH_LIMIT - files.UNIQUE_RESERVE:
        raise YtError("E_OUTPUT_NOT_WRITABLE", "path too long")
    return planned


def _root_of_length(tmp_path: Path, n: int) -> Path:
    anchor = Path(tmp_path.anchor)
    root = anchor / ("x" * (n - len(str(anchor))))
    assert len(str(root)) == n
    return root


_LEGACY_TITLES = (
    "สั้น", "Hi", "ก" * 300, "😀" * 300, chr(0x0E31) * 300, AC_OUT_01, "CON", "com1.txt", "", "...",
    "Big Buck Bunny 60fps 4K - Official Blender Foundation Short Film", "ชื่อคลิปยาวพอสมควร",
)  # fmt: skip
_LEGACY_TAILS = (
    ("", "mp4"), (" (ไม่มีเสียง)", "mp4"), (".th", "srt"), (" (01.30-05.00).th", "srt"), (".note", "md"),
    (" - contact sheet", "jpg"), (" - frames", "zip"), ("", "wav"), (" - ภาพคม", "jpg"),
    (" (ไม่มีเสียง) (1.02.30-1.05.00) (ตัดโฆษณา)", "mp4"),
)  # fmt: skip


@pytest.mark.parametrize("root_len", [4, 40, 60, 110, 150, 190])
@pytest.mark.parametrize("group", [None, "รวมคลิป ก/ข", "g" * 80])
def test_title_style_gives_exactly_the_names_from_before_m6(tmp_path, root_len, group):
    root = _root_of_length(tmp_path, root_len)
    for title in _LEGACY_TITLES:
        for suffix, ext in _LEGACY_TAILS:
            try:
                before = _legacy_plan_output(root, title, ID, suffix, ext, group)
            except YtError:
                with pytest.raises(YtError):
                    files.plan_output(root, title, ID, suffix, ext, group)
                continue
            assert files.plan_output(root, title, ID, suffix, ext, group) == before
            assert files.plan_output(root, title, ID, suffix, ext, group, style="title", uploader="ช่อง",
                                     quality="1080p") == before  # fmt: skip


@pytest.mark.parametrize("title", [AC_OUT_01, "ก" * 300])
@pytest.mark.parametrize(("ext", "quality"), [("mp4", "1080p"), ("mp3", "mp3 192k")])
def test_ac_out_09_every_style_is_safe_and_keeps_quality_and_extension(tmp_path, title, ext, quality):
    root = _root_of_length(tmp_path, 60)
    folders = set()
    for style in files.NAME_STYLES:
        path = files.plan_output(root, title, ID, "", ext, style=style, uploader="ครัว: บ้าน/เรา", quality=quality)
        assert not FORBIDDEN & set(path.parent.name + path.name)
        assert files._u16(str(path)) + files.UNIQUE_RESERVE <= files.PATH_LIMIT
        assert path.name.endswith(f".{ext}")
        if style == "title-quality":
            assert path.name.endswith(f" ({quality}).{ext}")
        if style == "title-channel":
            assert path.name.endswith(f" - ครัว บ้านเรา.{ext}")
        folders.add(path.parent)
    assert len(folders) == 1  # โฟลเดอร์ของคลิปไม่ขึ้นกับรูปแบบ


def test_long_channel_cuts_the_title_to_eight_before_the_channel():
    folder, file = files.plan_names(150, "ก" * 300, ID, suffix="", ext="mp4", style="title-channel", uploader="ช" * 120)
    stem = file.removesuffix(".mp4")
    title_part, channel_part = stem.split(files.CHANNEL_SEP, 1)
    assert title_part == "ก" * 8 and channel_part and set(channel_part) == {"ช"}
    assert 150 + 1 + files._u16(folder) + 1 + files._u16(file) <= files.PATH_LIMIT - files.UNIQUE_RESERVE


def test_unknown_style_and_bad_quality_are_programming_errors():
    with pytest.raises(ValueError):
        files.plan_names(10, "t", ID, suffix="", ext="mp4", style="channel")
    for bad in ("1080P", "", "x" * 17, "mp3/192k"):
        with pytest.raises(ValueError):
            files.plan_names(10, "t", ID, suffix="", ext="mp4", style="title-quality", quality=bad)


def test_zz_golden_was_not_regenerated():
    """ต้องอยู่ท้ายไฟล์: รอบที่เขียน golden เองเทสอื่นผ่านเพราะเทียบกับไฟล์ที่เพิ่งเขียน จึงต้องจบแดงเสมอ"""
    assert not _REGENERATED, "golden regenerated, review git diff and re-run without YT_UPDATE_GOLDEN"
```

- [ ] **Step 3: Run them, expect FAIL**

Run: `cd "$WORKTREE" && uv run pytest tests/unit/test_names_golden.py tests/unit/test_files.py -q -W error -p no:cacheprovider`
Expected: `83 failed, 92 passed` — `unit/test_names_golden.py::test_plan_names_matches_golden` (×60). (`AttributeError: module 'yttoolkit.core.files' has no attribute 'plan_names'` / `NAME_STYLES`; `golden.json is missing`); `tests/unit/test_files.py` still passes.

- [ ] **Step 4: Implement `plan_names` in `src/yttoolkit/core/files.py`**

In `src/yttoolkit/core/files.py`:

Replace (1):
```python
- path เต็มต้องไม่เกิน 240 ตัวอักษร (เผื่อ " (99)" ไว้ต่อท้ายตอนชื่อซ้ำ)
```
with:
```python
- path เต็มต้องไม่เกิน 240 ตัวอักษร (เผื่อ " (99)" ไว้ต่อท้ายตอนชื่อซ้ำ)
- M6 รอบ A: ชื่อไฟล์ตามรูปแบบ (title / title-channel / title-quality) คิดใน plan_names ที่เดียว
  หน้าเว็บมีตัวเดียวกันที่ web/src/lib/filename.ts (เทียบกันด้วย tests/fixtures/names/*.json)
```

Replace (2):
```python
_LONGEST_FRAME_NAME = "frame_000-00-00_200.jpg"  # ชื่อภาพคมยาวสุด: ชั่วโมง 3 หลัก ภาพที่ 200 ในวินาทีเดียวกัน
```
with:
```python
_LONGEST_FRAME_NAME = "frame_000-00-00_200.jpg"  # ชื่อภาพคมยาวสุด: ชั่วโมง 3 หลัก ภาพที่ 200 ในวินาทีเดียวกัน

# M6 รอบ A: รูปแบบชื่อไฟล์ (ค่าเดียวกับ settings.FILENAME_STYLES ซึ่งเป็นที่ตรวจค่าตั้ง files ไม่ import settings)
NAME_STYLES = ("title", "title-channel", "title-quality")
CHANNEL_SEP = " - "  # "<ชื่อคลิป> - <ช่อง>"
QUALITY_LABEL = re.compile(r"[a-z0-9 ]{1,16}")  # ส่วนคุณภาพ เช่น "1080p" "mp3 192k" "m4a" "wav"
```

Replace (3):
```python
def plan_output(root: Path, title: str, video_id: str, suffix: str, ext: str, group: str | None = None) -> Path:
```
with:
```python
def _stem(short: str, channel: str, avail: int) -> str:
    """ชื่อไฟล์ก่อนส่วนท้าย (ยาวไม่เกิน avail) ไม่มีช่อง = กฎเดิมของ M4 ทุกตัวอักษร · มีช่อง = ตัดชื่อคลิปก่อน
    (เหลืออย่างน้อย 8 ตัว) แล้วค่อยตัดชื่อช่อง ยังไม่พอ = ทิ้งชื่อช่อง · คืน "" = ให้ผู้เรียกใช้รหัสคลิปแทน"""
    if not channel:
        return short if _u16(short) <= avail else truncate_title(short, avail)
    joined = f"{short}{CHANNEL_SEP}{channel}"
    if _u16(joined) <= avail:
        return joined
    sep = _u16(CHANNEL_SEP)
    cut = truncate_title(short, max(avail - sep - _u16(channel), _MIN_TITLE))
    if cut and _u16(f"{cut}{CHANNEL_SEP}{channel}") <= avail:
        return f"{cut}{CHANNEL_SEP}{channel}"
    room = avail - _u16(cut) - sep
    short_channel = truncate_title(channel, room) if cut and room >= 1 else ""
    if short_channel:
        return f"{cut}{CHANNEL_SEP}{short_channel}"
    return truncate_title(short, avail)


def plan_names(
    base_len: int,
    title: str,
    clip_id: str,
    *,
    suffix: str,
    ext: str,
    style: str = "title",
    uploader: str = "",
    quality: str | None = None,
) -> tuple[str, str]:
    """(ชื่อโฟลเดอร์ของคลิป, ชื่อไฟล์) ตามรูปแบบชื่อไฟล์ (M6 รอบ A spec 2.2) กฎเดียวกับ web/src/lib/filename.ts

    base_len = ความยาว UTF-16 ของโฟลเดอร์ที่โฟลเดอร์ของคลิปจะอยู่ (โฟลเดอร์ผลลัพธ์ + "\\<กลุ่ม>" ถ้ามี)
    clip_id = รหัสคลิปแบบข้อความทึบ (ใช้เป็นชื่อสำรองและใน " [<id>]" เท่านั้น ไม่ตรวจรูปแบบ C12)
    uploader = ชื่อช่อง (ใช้เฉพาะแบบ title-channel) · quality = ส่วนคุณภาพ เช่น "1080p" / "mp3 192k" (เฉพาะ title-quality)
    ชื่อโฟลเดอร์ไม่ขึ้นกับรูปแบบ (ทุกงานของคลิปลงโฟลเดอร์เดียวกัน) · ยาวเกิน = ตัดชื่อคลิปก่อน แล้วชื่อช่อง
    ไม่ตัดส่วนคุณภาพและนามสกุล · path ยาวเกินแม้ใช้รหัสคลิป = E_OUTPUT_NOT_WRITABLE
    """
    if style not in NAME_STYLES:
        raise ValueError(f"unknown filename style: {style!r}")
    if quality is not None and not QUALITY_LABEL.fullmatch(quality):
        raise ValueError(f"bad quality label: {quality!r}")
    quality_part = f" ({quality})" if style == "title-quality" and quality else ""
    tail = f"{quality_part}{suffix}.{ext}"
    assert _u16(tail) <= TAIL_MAX, "suffix + extension longer than TAIL_MAX"
    t = safe_component(title, clip_id)
    budget = PATH_LIMIT - (base_len + 1) - _u16(f" [{clip_id}]") - 1 - TAIL_RESERVE - UNIQUE_RESERVE
    cap = budget // 2
    short = truncate_title(t, min(TITLE_MAX, cap)) if cap >= _MIN_TITLE else ""
    if short:
        # ชื่อโฟลเดอร์คิดจากงบเดิมเสมอ (ทุกงานของคลิปลงโฟลเดอร์เดียวกัน) ส่วนท้ายที่ยาวกว่า TAIL_RESERVE
        # ตัดเฉพาะชื่อไฟล์ลงเท่าส่วนที่เกิน: ชื่อแบบ M4 (ส่วนท้าย <= 30) จึงเหมือนเดิมทุกตัวอักษร
        folder = f"{short} [{clip_id}]"
        avail = budget - _u16(short) + TAIL_RESERVE - _u16(tail)
        channel = safe_component(uploader, "") if style == "title-channel" else ""
        file = f"{_stem(short, channel, avail) or clip_id}{tail}"
    else:
        folder, file = clip_id, f"{clip_id}{tail}"
    if base_len + 1 + _u16(folder) + 1 + _u16(file) > PATH_LIMIT - UNIQUE_RESERVE:
        raise YtError("E_OUTPUT_NOT_WRITABLE", "path too long")
    return folder, file


def plan_output(
    root: Path,
    title: str,
    video_id: str,
    suffix: str,
    ext: str,
    group: str | None = None,
    *,
    style: str = "title",
    uploader: str = "",
    quality: str | None = None,
) -> Path:
```

Replace (4):
```python
    """
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
with:
```python
    style / uploader / quality = รูปแบบชื่อไฟล์ (M6 รอบ A ดู plan_names) ผู้เรียกที่ใช้แค่ .parent ไม่ต้องส่ง
    """
    base = root / group_folder_name(group) if group else root
    folder, file = plan_names(
        _u16(str(base)), title, video_id, suffix=suffix, ext=ext, style=style, uploader=uploader, quality=quality
    )
    return base / folder / file
```

Notes for the implementer:
- `plan_output` must give **exactly** today's names for `style="title"` (`test_title_style_gives_exactly_the_names_from_before_m6` compares it with a verbatim copy of the old function over 6 root lengths × 3 groups × 12 titles × 10 tails).
- `_stem` only cuts the title down to 8 characters before it cuts the channel (D3); when the title cut is empty the channel is dropped (P5).
- `clip_id` is opaque: no id regex in `plan_names` (C12).

- [ ] **Step 5: Generate `golden.json`, then run the tests, expect PASS**

Run: `cd "$WORKTREE" && YT_UPDATE_GOLDEN=1 uv run pytest tests/unit/test_names_golden.py -q -W error -p no:cacheprovider`
Expected: exactly one failure, `test_zz_golden_was_not_regenerated` (on purpose). Then:
Run: `cd "$WORKTREE" && sha256sum tests/fixtures/names/golden.json` — expected `56cfcce46d9684971e00c9bd24bebec3742f23b9a3198a41b9d3c42c7417eb4e` (the prototype's file; a different hash means `plan_names` differs from this plan — fix the code, never the golden).
Spot-check three entries of `golden.json`:
```json
{
 "ac-out-01-mp4-title-channel": {
  "folder": "ทดสอบ AB ภาค 1 [dQw4w9WgXcQ]",
  "file": "ทดสอบ AB ภาค 1 - ช่อง ทดสอบ1.mp4"
 },
 "longest-suffix-title-quality": {
  "folder": "กกกกกกกกกกกกกกกกกกกกกกกกกกกกกกกกกกกกกกกกกกกกกกกกกกกกกกกกกกกกกกกก [dQw4w9WgXcQ]",
  "file": "กกกกกกกกกกกกกกกกกกกกกกกกกกกกกกกกกกกกกกกกก (1080p) (ไม่มีเสียง) (1.02.30-1.05.00) (ตัดโฆษณา).mp4"
 },
 "uploader-120-b150": {
  "folder": "สอนทำกับข้าวง่าย ๆ [dQw4w9WgXcQ]",
  "file": "สอนทำกับ - ชชชชชชชชชชชชชชชชชชชชชชชชชชชชชชชชชชชช.mp4"
 },
 "whitespace-classes": {
  "folder": "a bcd e f g h ij k l [dQw4w9WgXcQ]",
  "file": "a bcd e f g h ij k l - ช่อง ทดสอบ.mp4"
 },
 "base-230-title": {
  "error": "path too long"
 }
}
```
Run: `cd "$WORKTREE" && uv run pytest tests/unit/test_names_golden.py tests/unit/test_files.py -q -W error -p no:cacheprovider`
Expected: `175 passed`. Then the full suite: `cd "$WORKTREE" && uv run pytest -q -W error -p no:cacheprovider` (all pass).

- [ ] **Step 6: Commit**
```bash
cd "$WORKTREE" && git add src/yttoolkit/core/files.py tests/unit/test_names_golden.py tests/fixtures/names/cases.json tests/fixtures/names/golden.json && git commit -F- <<'EOF'
feat(files): plan_names with the filename styles; parity cases and Python golden

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
EOF
```


### Task 2: Schema v3 and the style snapshot on the job; the channel in log and report scrubbing (spec 2.4, 2.7 privacy)

**Files:**
- Modify: `src/yttoolkit/core/db.py`, `src/yttoolkit/core/jobs.py`, `src/yttoolkit/core/queue.py`, `src/yttoolkit/core/settings.py`, `src/yttoolkit/api/diagnostics.py`
- Modify: `tests/unit/test_db.py`, `tests/unit/test_jobs_store.py`, `tests/unit/test_queue.py`, `tests/unit/test_settings.py`, `tests/api/test_diagnostics_api.py`

**Interfaces:**
- Consumes: `Database.migrate` / `_MIGRATIONS`, `JobStore.transition` / `_FIELD_COLUMNS`, `QueueRunner._start`, `job_titles`, `log_job_failed`, `SettingsStore.get`.
- Produces: K2 exactly — `SCHEMA_VERSION = 3`, `_JOBS_V2`, `_MIGRATIONS[3]`, `Job.filename_style`, `transition(..., filename_style=)`, `JobStore.channel_of`, `JobContext.filename_style` (the real `_JobContext` sets it from the started job), `SettingsView.filename_style()`, `SettingsStore.filename_style()`, `job_titles(job, chapters_json, channel="")`, `log_job_failed(..., channel="")`. T5 reads `ctx.filename_style`; T7 edits `queue.py` again in wave 2; T11 reads `job.filename_style` and `channel_of`.

- [ ] **Step 1: Write the failing tests**

In `tests/api/test_diagnostics_api.py`:

Replace (1):
```python

def test_a_videos_only_report_hides_that_clips_chapter_titles(env) -> None:
```
with:
```python

def test_the_report_hides_the_channel_name(env) -> None:
    # M6 รอบ A: ชื่อไฟล์แบบ title-channel มีชื่อช่อง รายงานต้องปิดชื่อช่องด้วย (ทั้งงานในคิวและคลิปที่ไม่มีงาน)
    channel = "Somchai Kitchen Channel"
    env.db.execute(
        "INSERT INTO videos (video_id, title, channel, probe_json, probed_at, opened_at)"
        " VALUES (?, ?, ?, '{}', 'x', 'x')",
        (BBB, TITLE, channel),
    )
    (job,) = env.store.add([NewJob(BBB, "video", {}, TITLE)])
    env.store.transition(job.id, "running")
    detail = f"no free name for {TITLE} - {channel}.mp4"
    env.store.transition(job.id, "failed", error_code="E_OUTPUT_NOT_WRITABLE", error_message="m", error_detail=detail)
    assert channel not in env.report({"jobId": job.id})
    assert channel not in env.report({"code": "E_NETWORK", "detail": f"x {channel} y", "videoId": BBB})


def test_a_videos_only_report_hides_that_clips_chapter_titles(env) -> None:
```

In `tests/unit/test_db.py`:

Replace (1):
```python
def test_fresh_database_is_v2_without_job_foreign_key(tmp_path):
    db = Database(tmp_path / "app.db")
    db.migrate()
    assert db.execute("SELECT max(version) AS v FROM schema_version")[0]["v"] == 2
```
with:
```python
def test_fresh_database_is_v3_without_job_foreign_key(tmp_path):
    db = Database(tmp_path / "app.db")
    db.migrate()
    assert db.execute("SELECT max(version) AS v FROM schema_version")[0]["v"] == 3
```

Replace (2):
```python
    assert {"title", "attempt", "bot_checks", "error_message", "notes_json"} <= cols
```
with:
```python
    assert {"title", "attempt", "bot_checks", "error_message", "notes_json", "filename_style"} <= cols
```

Replace (3):
```python
    assert (row["status"], row["position"], row["title"], row["attempt"]) == ("done", 3, "", 0)
    assert db.execute("SELECT max(version) AS v FROM schema_version")[0]["v"] == 2
```
with:
```python
    assert (row["status"], row["position"], row["title"], row["attempt"]) == ("done", 3, "", 0)
    assert row["filename_style"] is None  # งานก่อน M6 = แบบ "title"
    assert db.execute("SELECT max(version) AS v FROM schema_version")[0]["v"] == 3
```

Replace (4):
```python
        assert db.execute("SELECT max(version) AS v FROM schema_version")[0]["v"] == 2
    finally:
        db.close()
```
with:
```python
        assert db.execute("SELECT max(version) AS v FROM schema_version")[0]["v"] == 3
    finally:
        db.close()


# ---------- M6 รอบ A: schema v3 (jobs.filename_style) ----------


def _v2_database(path: Path) -> None:
    """ฐานข้อมูล v2 ตามที่ M4-M6 รอบ B สร้างจริง (ตาราง jobs แบบ _JOBS_V2) พร้อมงานหนึ่งงานและค่าตั้งหนึ่งค่า"""
    raw = sqlite3.connect(path)
    raw.executescript(
        "CREATE TABLE schema_version (version INTEGER NOT NULL);"
        "CREATE TABLE videos (video_id TEXT PRIMARY KEY, title TEXT NOT NULL, channel TEXT, duration_s INTEGER,"
        " thumbnail_url TEXT, chapters_json TEXT, probe_json TEXT NOT NULL, probed_at TEXT NOT NULL,"
        " opened_at TEXT NOT NULL);"
        f"{db_module._JOBS_V2}"
        "CREATE TABLE settings (key TEXT PRIMARY KEY, value_json TEXT NOT NULL);"
        "INSERT INTO schema_version (version) VALUES (2);"
    )
    raw.execute("INSERT INTO videos VALUES ('aqz-KE-bpKQ','t','ช่อง',60,NULL,NULL,'{}','x','x')")
    raw.execute(
        "INSERT INTO jobs (id, video_id, title, kind, params_json, status, attempt, bot_checks, position, "
        "error_code, notes_json, outputs_json, created_at, started_at, finished_at) VALUES "
        "('v2job', 'aqz-KE-bpKQ', 'ชื่อ', 'audio', '{\"format\": \"mp3\"}', 'failed', 0, 1, 7, 'E_NETWORK', "
        "'[\"NO_CHAPTERS\"]', NULL, 'c', 's', 'f')"
    )
    raw.execute("INSERT INTO settings VALUES ('concurrency', '3')")
    raw.commit()
    raw.close()


def test_v2_database_migrates_to_v3_and_keeps_every_row(tmp_path):
    _v2_database(tmp_path / "app.db")
    db = Database(tmp_path / "app.db")
    db.migrate()
    assert db.execute("SELECT max(version) AS v FROM schema_version")[0]["v"] == 3
    assert len(db.execute("SELECT version FROM schema_version")) == 1
    row = db.execute("SELECT * FROM jobs WHERE id = 'v2job'")[0]
    assert (row["title"], row["kind"], row["params_json"], row["status"], row["bot_checks"], row["position"]) == (
        "ชื่อ", "audio", '{"format": "mp3"}', "failed", 1, 7,
    )  # fmt: skip
    assert (row["error_code"], row["notes_json"], row["created_at"], row["finished_at"]) == (
        "E_NETWORK", '["NO_CHAPTERS"]', "c", "f",
    )  # fmt: skip
    assert row["filename_style"] is None
    assert db.execute("SELECT channel FROM videos")[0]["channel"] == "ช่อง"
    assert db.execute("SELECT value_json FROM settings WHERE key = 'concurrency'")[0]["value_json"] == "3"
    assert _jobs_video_index_columns(db) == ["video_id", "status"]
    db.migrate()  # ครั้งที่สอง = ไม่ทำอะไร
    assert db.execute("SELECT max(version) AS v FROM schema_version")[0]["v"] == 3
    db.close()


def test_v1_database_migrates_through_v2_to_v3(tmp_path):
    raw = sqlite3.connect(tmp_path / "app.db")
    raw.executescript(V1_JOBS)
    raw.execute("INSERT INTO videos VALUES ('aqz-KE-bpKQ','t',NULL,NULL,NULL,NULL,'{}','x','x')")
    raw.execute("INSERT INTO jobs (id, video_id, kind, params_json, status, position, created_at) "
                "VALUES ('old', 'aqz-KE-bpKQ', 'video', '{}', 'done', 3, 'x')")  # fmt: skip
    raw.commit()
    raw.close()
    db = Database(tmp_path / "app.db")
    db.migrate()
    cols = [r["name"] for r in db.execute("PRAGMA table_info(jobs)")]
    assert cols.count("filename_style") == 1 and cols[-1] == "filename_style"
    row = db.execute("SELECT * FROM jobs WHERE id = 'old'")[0]
    assert (row["status"], row["position"], row["filename_style"]) == ("done", 3, None)
    assert db.execute("SELECT max(version) AS v FROM schema_version")[0]["v"] == 3
    db.close()


def test_migration_2_still_builds_the_frozen_v2_table():
    assert "filename_style" not in db_module._JOBS_V2
    assert "filename_style" not in db_module._MIGRATIONS[2]
    assert db_module._JOBS_V2.strip() in db_module._MIGRATIONS[2]
    assert "filename_style" in db_module._JOBS and SCHEMA_VERSION == 3


def test_v3_migration_failure_rolls_back_to_v2(tmp_path, monkeypatch):
    _v2_database(tmp_path / "app.db")
    db = Database(tmp_path / "app.db")
    try:
        with monkeypatch.context() as m:
            m.setitem(db_module._MIGRATIONS, 3, "ALTER TABLE jobs ADD COLUMN filename_style TEXT; CREATE TABLE broken (;")
            with pytest.raises(sqlite3.Error):
                db.migrate()
        assert db.execute("SELECT max(version) AS v FROM schema_version")[0]["v"] == 2
        assert "filename_style" not in {r["name"] for r in db.execute("PRAGMA table_info(jobs)")}
        db.migrate()
        assert db.execute("SELECT max(version) AS v FROM schema_version")[0]["v"] == 3
    finally:
        db.close()
```

In `tests/unit/test_jobs_store.py`:

Append at the end of the file:
```python

# ---------- M6 รอบ A: jobs.filename_style และชื่อช่อง ----------

def test_filename_style_is_written_on_start_and_survives_requeue(store):
    (job,) = add(store)
    assert job.filename_style is None
    running = store.transition(job.id, "running", filename_style="title-channel")
    assert running.filename_style == "title-channel"
    failed = store.transition(job.id, "failed", error_code="E_NETWORK", error_message="m")
    assert failed.filename_style == "title-channel"
    again = store.requeue(job.id, reset_bot_checks=True)
    assert again.filename_style == "title-channel" and again.error_code is None
    assert "filenameStyle" not in again.to_api() and "filename_style" not in again.to_api()

def test_update_cannot_change_the_filename_style(store):
    (job,) = add(store)
    store.transition(job.id, "running", filename_style="title")
    with pytest.raises(ValueError):
        store.update(job.id, filename_style="title-quality")

def test_channel_of_reads_the_videos_row(store):
    sql = "INSERT INTO videos (video_id, title, channel, probe_json, probed_at, opened_at) VALUES (?, 't', ?, '{}', 'x', 'x')"
    store._db.execute(sql, ("vid00000000", "ครัวบ้านเรา"))
    store._db.execute(sql, ("vid00000001", None))
    assert store.channel_of("vid00000000") == "ครัวบ้านเรา"
    assert store.channel_of("vid00000001") == ""
    assert store.channel_of("missing0000") == ""
```

In `tests/unit/test_queue.py`:

Replace (1):
```python
        self.output = output
```
with:
```python
        self.output = output
        self.style = "title"  # M6 รอบ A: รูปแบบชื่อไฟล์ปัจจุบัน (เทสเปลี่ยนได้)
```

Replace (2):
```python
        return self.output
```
with:
```python
        return self.output

    def filename_style(self) -> str:
        return self.style
```

Append at the end of the file:
```python


# ---------- M6 รอบ A: รูปแบบชื่อไฟล์ตั้งตอนงานเริ่มครั้งแรก (D4) ----------


class StyleRecorder(ScriptedHandler):
    """ScriptedHandler ที่จดรูปแบบชื่อไฟล์ที่งานได้รับในแต่ละรอบ (ctx.filename_style)"""

    def __init__(self, fail: dict | None = None) -> None:
        super().__init__(fail)
        self.styles: list[str] = []

    def __call__(self, job, ctx) -> JobResult:
        self.styles.append(ctx.filename_style)
        return super().__call__(job, ctx)


def test_the_first_start_stores_the_current_style(runner_factory):
    h = StyleRecorder()
    r, spawn, _ = runner_factory(concurrency=1, handler=h)
    (job,) = r.enqueue(jobs_of("video", 1))
    assert r.store.get(job.id).filename_style is None  # ยังไม่เริ่ม
    r.settings_view.style = "title-channel"
    r.tick()
    assert r.store.get(job.id).filename_style == "title-channel"
    spawn.run_all()
    assert h.styles == ["title-channel"]
    assert r.store.get(job.id).filename_style == "title-channel"
    api = r.job_api(r.store.get(job.id))
    assert "filenameStyle" not in api and "filename_style" not in api  # ข้อมูลภายใน ไม่อยู่ใน API


def test_a_job_queued_before_a_style_change_uses_the_style_at_its_start(runner_factory):
    h = StyleRecorder()
    r, spawn, _ = runner_factory(concurrency=1, handler=h)
    first, second = r.enqueue(jobs_of("frames_zip", 2, {"source": "fast"}))
    r.tick()  # งานแรกเริ่มด้วย "title"
    r.settings_view.style = "title-quality"  # เปลี่ยนระหว่างงานแรกรันอยู่ (AC-OUT-10)
    spawn.run_all()
    r.tick()
    spawn.run_all()
    assert h.styles == ["title", "title-quality"]
    assert (r.store.get(first.id).filename_style, r.store.get(second.id).filename_style) == ("title", "title-quality")


def test_a_retry_after_a_style_change_keeps_the_first_style(runner_factory):
    h = StyleRecorder(fail={"vid00000001": ["E_YT_REFUSED", None]})
    r, spawn, _ = runner_factory(concurrency=1, handler=h)
    r.settings_view.style = "title-channel"
    (job,) = r.enqueue(jobs_of("video", 1))
    r.tick()
    spawn.run_all()
    assert r.store.get(job.id).status == "failed"
    r.settings_view.style = "title-quality"
    requeued = r.retry(job.id)
    assert requeued.filename_style == "title-channel"  # requeue ไม่ล้างรูปแบบ
    r.clock.t += 10  # พ้นช่วงเว้นระหว่างงานยูทูป
    r.tick()
    spawn.run_all()
    assert r.store.get(job.id).status == "done"
    assert h.styles == ["title-channel", "title-channel"]


def test_the_bot_check_requeue_keeps_the_first_style(runner_factory):
    h = StyleRecorder(fail={"vid00000001": ["E_BOT_CHECK", None]})
    r, spawn, _ = runner_factory(concurrency=1, handler=h)
    r.settings_view.style = "title-quality"
    (job,) = r.enqueue(jobs_of("video", 1))
    r.tick()
    spawn.run_all()
    assert r.store.get(job.id).status == "queued"  # ครั้งแรกกลับหัวคิว
    r.settings_view.style = "title"
    r.resume()
    r.clock.t += 10  # พ้นช่วงเว้นระหว่างงานยูทูป
    r.tick()
    spawn.run_all()
    assert h.styles == ["title-quality", "title-quality"]
    assert r.store.get(job.id).filename_style == "title-quality"


def test_network_retries_inside_one_run_keep_the_style(runner_factory, monkeypatch):
    monkeypatch.setattr(queue_module._JobContext, "wait", lambda self, s: None)
    h = StyleRecorder(fail={"vid00000001": ["E_NETWORK", "E_NETWORK", None]})
    r, spawn, _ = runner_factory(concurrency=1, handler=h)
    r.settings_view.style = "title-channel"
    r.enqueue(jobs_of("video", 1))
    r.tick()
    r.settings_view.style = "title"
    spawn.run_all()
    assert h.styles == ["title-channel"] * 3


def test_job_titles_include_the_channel():
    fake = type("J", (), {"title": "T1", "params": {}})()
    assert queue_module.job_titles(fake, None, "ครัวบ้านเรา") == ("T1", "ครัวบ้านเรา")
    assert queue_module.job_titles(fake, None) == ("T1",)


def test_job_failed_hides_the_channel_name(runner_factory, caplog):
    channel = "Somchai Kitchen Channel"
    detail = f"[Errno 13] Permission denied: '~\\\\Downloads\\\\Main Clip Title - {channel} [vid00000001]\\\\x.mp4'"
    r, spawn, h = runner_factory(concurrency=1, fail={"vid00000001": YtError("E_OUTPUT_NOT_WRITABLE", detail)})
    r.store._db.execute(
        "INSERT INTO videos (video_id, title, channel, probe_json, probed_at, opened_at)"
        " VALUES ('vid00000001', 'row title', ?, '{}', 'x', 'x')",
        (channel,),
    )
    r.enqueue([NewJob("vid00000001", "video", {}, "Main Clip Title")])
    with caplog.at_level(logging.INFO, logger="yttoolkit"):
        r.tick()
        spawn.run_all()
    (record,) = failed_records(caplog)
    assert channel not in record.getMessage() and "Somchai Kitchen" not in caplog.text
```

In `tests/unit/test_settings.py`:

Append at the end of the file:
```python


# ---------- M6 รอบ A: คิวอ่านรูปแบบชื่อไฟล์ ----------


def test_filename_style_reads_the_current_setting(store):
    assert store.filename_style() == "title"
    store.patch({"filenameStyle": "title-quality"})
    assert store.filename_style() == "title-quality"
```

- [ ] **Step 2: Run them, expect FAIL**

Run: `cd "$WORKTREE" && uv run pytest tests/unit/test_db.py tests/unit/test_jobs_store.py tests/unit/test_queue.py tests/unit/test_settings.py tests/api/test_diagnostics_api.py -q -W error -p no:cacheprovider`
Expected: `19 failed, 268 passed` — `unit/test_db.py::test_fresh_database_is_v3_without_job_foreign_key`, `unit/test_db.py::test_v1_database_migrates_and_keeps_rows`, `unit/test_db.py::test_v1_migration_failure_rolls_back`, `unit/test_db.py::test_v2_database_migrates_to_v3_and_keeps_every_row`, `unit/test_db.py::test_v1_database_migrates_through_v2_to_v3`, `unit/test_db.py::test_migration_2_still_builds_the_frozen_v2_table`, `unit/test_db.py::test_v3_migration_failure_rolls_back_to_v2`, `unit/test_jobs_store.py::test_filename_style_is_written_on_start_and_survives_requeue`, `unit/test_jobs_store.py::test_update_cannot_change_the_filename_style`, `unit/test_jobs_store.py::test_channel_of_reads_the_videos_row`, `unit/test_queue.py::test_the_first_start_stores_the_current_style`, `unit/test_queue.py::test_a_job_queued_before_a_style_change_uses_the_style_at_its_start`, `unit/test_queue.py::test_a_retry_after_a_style_change_keeps_the_first_style`, `unit/test_queue.py::test_the_bot_check_requeue_keeps_the_first_style`, `unit/test_queue.py::test_network_retries_inside_one_run_keep_the_style`, `unit/test_queue.py::test_job_titles_include_the_channel`, `unit/test_queue.py::test_job_failed_hides_the_channel_name`, `unit/test_settings.py::test_filename_style_reads_the_current_setting`, `api/test_diagnostics_api.py::test_the_report_hides_the_channel_name`.

- [ ] **Step 3: Implement**

In `src/yttoolkit/api/diagnostics.py`:

Replace (1):
```python
def _video_row(ctx: AppContext, video_id: str | None) -> tuple[str, str | None]:
    """(ชื่อคลิป, chapters_json) จากตาราง videos · ไม่มีแถวหรืออ่านไม่ได้ = ("", None)"""
    if not video_id or ctx.db is None:
        return "", None
    try:
        rows = ctx.db.execute("SELECT title, chapters_json FROM videos WHERE video_id = ?", (video_id,))
    except sqlite3.Error:
        return "", None
    return (str(rows[0]["title"] or ""), rows[0]["chapters_json"]) if rows else ("", None)
```
with:
```python
def _video_row(ctx: AppContext, video_id: str | None) -> tuple[str, str | None, str]:
    """(ชื่อคลิป, chapters_json, ชื่อช่อง) จากตาราง videos · ไม่มีแถวหรืออ่านไม่ได้ = ("", None, "")"""
    if not video_id or ctx.db is None:
        return "", None, ""
    try:
        rows = ctx.db.execute("SELECT title, chapters_json, channel FROM videos WHERE video_id = ?", (video_id,))
    except sqlite3.Error:
        return "", None, ""
    if not rows:
        return "", None, ""
    return str(rows[0]["title"] or ""), rows[0]["chapters_json"], str(rows[0]["channel"] or "")
```

Replace (2):
```python
    row_title, chapters_json = _video_row(ctx, video_id)
    # ชุดชื่อเดียวกับบรรทัด job_failed (job_titles): ชื่องาน โฟลเดอร์ playlist/ชุดงาน ชื่อ chapter + ชื่อในตาราง videos
    names = job_titles(job if job is not None else _NoJob(), chapters_json)
```
with:
```python
    row_title, chapters_json, channel = _video_row(ctx, video_id)
    # ชุดชื่อเดียวกับบรรทัด job_failed (job_titles): ชื่องาน โฟลเดอร์ playlist/ชุดงาน ชื่อช่อง ชื่อ chapter + ชื่อในตาราง videos
    names = job_titles(job if job is not None else _NoJob(), chapters_json, channel)
```

In `src/yttoolkit/core/db.py`:

Replace (1):
```python
SCHEMA_VERSION = 2

# v2: ไม่มี foreign key ไป videos (W3 เข้าคิวคลิปที่ยังไม่เคย probe ได้) และมีช่องของงาน M4 เพิ่ม
```
with:
```python
SCHEMA_VERSION = 3

# v2: ไม่มี foreign key ไป videos (W3 เข้าคิวคลิปที่ยังไม่เคย probe ได้) และมีช่องของงาน M4 เพิ่ม
# แช่แข็งไว้ตามที่เป็นตอน v2: _MIGRATIONS[2] ต้องสร้างตารางแบบ v2 เสมอ ไม่งั้นอัปเกรด v1 -> v2 -> v3
# จะได้คอลัมน์ของ v3 ตั้งแต่ขั้น 2 แล้ว ALTER ของขั้น 3 ล้ม (duplicate column)
_JOBS_V2 = """
CREATE TABLE jobs (
  id            TEXT PRIMARY KEY,
  video_id      TEXT NOT NULL,
  title         TEXT NOT NULL DEFAULT '',
  kind          TEXT NOT NULL,
  params_json   TEXT NOT NULL,
  status        TEXT NOT NULL,
  stage         TEXT,
  progress      REAL,
  speed_bps     INTEGER,
  eta_s         INTEGER,
  attempt       INTEGER NOT NULL DEFAULT 0,
  bot_checks    INTEGER NOT NULL DEFAULT 0,
  position      INTEGER NOT NULL,
  error_code    TEXT,
  error_message TEXT,
  error_detail  TEXT,
  notes_json    TEXT,
  outputs_json  TEXT,
  created_at    TEXT NOT NULL,
  started_at    TEXT,
  finished_at   TEXT
);
CREATE INDEX jobs_status_position ON jobs(status, position);
CREATE INDEX IF NOT EXISTS jobs_video ON jobs(video_id, status);
"""

# v3 (M6 รอบ A): filename_style = รูปแบบชื่อไฟล์ ณ ตอนเริ่มงานครั้งแรก (NULL = ยังไม่เริ่ม หรืองานก่อน M6 = "title")
```

Replace (2):
```python
  error_message TEXT,
  error_detail  TEXT,
  notes_json    TEXT,
  outputs_json  TEXT,
  created_at    TEXT NOT NULL,
  started_at    TEXT,
  finished_at   TEXT
);
CREATE INDEX jobs_status_position ON jobs(status, position);
CREATE INDEX IF NOT EXISTS jobs_video ON jobs(video_id, status);
"""

_SCHEMA = f"""
```
with:
```python
  error_message TEXT,
  error_detail  TEXT,
  notes_json    TEXT,
  outputs_json  TEXT,
  created_at    TEXT NOT NULL,
  started_at    TEXT,
  finished_at   TEXT,
  filename_style TEXT
);
CREATE INDEX jobs_status_position ON jobs(status, position);
CREATE INDEX IF NOT EXISTS jobs_video ON jobs(video_id, status);
"""

_SCHEMA = f"""
```

Replace (3):
```python
{_JOBS}
INSERT INTO jobs ({_V1_JOB_COLUMNS}) SELECT {_V1_JOB_COLUMNS} FROM jobs_v1;
DROP TABLE jobs_v1;
UPDATE schema_version SET version = 2;
```
with:
```python
{_JOBS_V2}
INSERT INTO jobs ({_V1_JOB_COLUMNS}) SELECT {_V1_JOB_COLUMNS} FROM jobs_v1;
DROP TABLE jobs_v1;
UPDATE schema_version SET version = 2;
""",
    3: """
ALTER TABLE jobs ADD COLUMN filename_style TEXT;
UPDATE schema_version SET version = 3;
```

In `src/yttoolkit/core/jobs.py`:

Replace (1):
```python
    "outputs": "outputs_json",
```
with:
```python
    "outputs": "outputs_json",
    "filename_style": "filename_style",  # M6 รอบ A: ตั้งครั้งเดียวตอน queued -> running ครั้งแรก (QueueRunner._start)
```

Replace (2):
```python
    output_root: Path    # outputDir ณ ตอนเริ่มงาน
```
with:
```python
    output_root: Path    # outputDir ณ ตอนเริ่มงาน
    filename_style: str  # M6 รอบ A: รูปแบบชื่อไฟล์ของงานนี้ (Job.filename_style ที่ตั้งตอนเริ่มครั้งแรก)
```

Replace (3):
```python
    finished_at: str | None
```
with:
```python
    finished_at: str | None
    # M6 รอบ A: รูปแบบชื่อไฟล์ ณ ตอนเริ่มครั้งแรก ลองใหม่ใช้ค่าเดิม (ชื่อไม่เปลี่ยน ตัวกวาดไฟล์ค้างหาเจอ)
    # None = ยังไม่เคยเริ่ม หรืองานก่อน M6 (= "title") · ไม่อยู่ใน API (ข้อมูลภายใน)
    filename_style: str | None = None
```

Replace (4):
```python
        finished_at=row["finished_at"],
```
with:
```python
        finished_at=row["finished_at"],
        filename_style=row["filename_style"],
```

Append at the end of the file:
```python

    def channel_of(self, video_id: str) -> str:
        """ชื่อช่องของคลิปจากตาราง videos (M6 รอบ A: ชื่อไฟล์แบบ title-channel ตัวกวาดไฟล์ค้าง และตัวปิดชื่อใน log)
        ไม่มีแถว ค่าว่าง หรืออ่านไม่ได้ = "" ไม่ยกต่อ"""
        try:
            rows = self._db.execute("SELECT channel FROM videos WHERE video_id = ?", (video_id,))
        except sqlite3.Error:
            return ""
        return str(rows[0]["channel"] or "") if rows else ""
```

In `src/yttoolkit/core/queue.py`:

Replace (1):
```python
def job_titles(job: Any, chapters_json: str | None) -> tuple[str, ...]:
    """ชื่อที่ต้องปิดในข้อความเกี่ยวกับงานหนึ่งงาน (รีวิวท้ายรอบ I1): ชื่องาน ชื่อโฟลเดอร์ playlist/ชุดงาน (params.folder)
    และชื่อ chapter ทุกตอนของคลิป (คอลัมน์ chapters_json ของตาราง videos) · ค่าที่อ่านไม่ได้ข้ามไป ไม่ยกต่อ
```
with:
```python
def job_titles(job: Any, chapters_json: str | None, channel: str = "") -> tuple[str, ...]:
    """ชื่อที่ต้องปิดในข้อความเกี่ยวกับงานหนึ่งงาน (รีวิวท้ายรอบ I1): ชื่องาน ชื่อโฟลเดอร์ playlist/ชุดงาน (params.folder)
    ชื่อช่อง (M6 รอบ A: ชื่อไฟล์แบบ title-channel มีชื่อช่อง) และชื่อ chapter ทุกตอนของคลิป
    (คอลัมน์ chapters_json ของตาราง videos) · ค่าที่อ่านไม่ได้ข้ามไป ไม่ยกต่อ
```

Replace (2):
```python
    names = [job.title, folder if isinstance(folder, str) else ""]
```
with:
```python
    names = [job.title, folder if isinstance(folder, str) else "", channel if isinstance(channel, str) else ""]
```

Replace (3):
```python
    job: Job, code: str, detail: str | None, exc: BaseException | None, chapters_json: str | None = None
```
with:
```python
    job: Job,
    code: str,
    detail: str | None,
    exc: BaseException | None,
    chapters_json: str | None = None,
    channel: str = "",
```

Replace (4):
```python
    """
    level = logging.WARNING if exc is None or isinstance(exc, YtError) else logging.ERROR
    try:
        message = job_failed_message(job, code, detail, exc, job_titles(job, chapters_json))
```
with:
```python
    channel = ชื่อช่องของคลิป (JobStore.channel_of) ถูกปิดด้วย (M6 รอบ A)
    """
    level = logging.WARNING if exc is None or isinstance(exc, YtError) else logging.ERROR
    try:
        message = job_failed_message(job, code, detail, exc, job_titles(job, chapters_json, channel))
```

Replace (5):
```python
    def output_dir(self) -> Path: ...
```
with:
```python
    def output_dir(self) -> Path: ...
    def filename_style(self) -> str: ...  # M6 รอบ A: อ่านตอนงานเริ่มครั้งแรก (D4)
```

Replace (6):
```python
        self.output_root = output_root
```
with:
```python
        self.output_root = output_root
        self.filename_style = job.filename_style or "title"  # M6 รอบ A: ค่าที่ _start ตั้งไว้ในงาน
```

Replace (7):
```python
            job = self.store.transition(job.id, "running")
```
with:
```python
            # M6 รอบ A (D4): รูปแบบชื่อไฟล์ตั้งครั้งเดียวตอนเริ่มครั้งแรก ลองใหม่ (ทุกทาง) ใช้ค่าเดิมในงาน
            style = job.filename_style or self._settings.filename_style()
            job = self.store.transition(job.id, "running", filename_style=style)
```

Replace (8):
```python
            log_job_failed(job, "E_UNKNOWN", detail, exc, self.store.chapters_json(job.video_id))
```
with:
```python
            log_job_failed(job, "E_UNKNOWN", detail, exc, self.store.chapters_json(job.video_id),
                           self.store.channel_of(job.video_id))  # fmt: skip
```

Replace (9):
```python
            titles = job_titles(job, self.store.chapters_json(job.video_id))
```
with:
```python
            titles = job_titles(job, self.store.chapters_json(job.video_id), self.store.channel_of(job.video_id))
```

Replace (10):
```python
        log_job_failed(job, code, detail, exc, self.store.chapters_json(job.video_id))
```
with:
```python
        log_job_failed(job, code, detail, exc, self.store.chapters_json(job.video_id), self.store.channel_of(job.video_id))
```

In `src/yttoolkit/core/settings.py`:

Append at the end of the file:
```python

    def filename_style(self) -> str:
        """รูปแบบชื่อไฟล์ปัจจุบัน (คิวอ่านตอนงานเริ่มครั้งแรก M6 รอบ A D4)"""
        return str(self.get()["filenameStyle"])
```

Notes for the implementer:
- `_JOBS_V2` is today's `_JOBS` text unchanged; `_MIGRATIONS[2]` must use it, or a v1 database would get the v3 column in step 2 and fail on step 3's `ALTER` (`test_v1_database_migrates_through_v2_to_v3`).
- `filename_style` is **not** in `_REQUEUE_CLEARS` and **not** in `to_api()`: retries keep it (D4), the API shape is unchanged.
- `QueueRunner._start` reads the setting only when `job.filename_style` is `None` (the first start).

- [ ] **Step 4: Run the tests, expect PASS**

Run: the Step 2 command. Expected: `287 passed`. Then the full suite: `cd "$WORKTREE" && uv run pytest -q -W error -p no:cacheprovider` (all pass; the handlers do not read `ctx.filename_style` yet, T5 does).

- [ ] **Step 5: Commit**
```bash
cd "$WORKTREE" && git add src/yttoolkit/core/db.py src/yttoolkit/core/jobs.py src/yttoolkit/core/queue.py src/yttoolkit/core/settings.py src/yttoolkit/api/diagnostics.py tests/unit/test_db.py tests/unit/test_jobs_store.py tests/unit/test_queue.py tests/unit/test_settings.py tests/api/test_diagnostics_api.py && git commit -F- <<'EOF'
feat(queue): schema v3 jobs.filename_style snapshot at first start; scrub the channel in job logs and reports

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
EOF
```


### Task 3: `GET /history` items carry the channel (spec 2.6)

**Files:**
- Modify: `src/yttoolkit/core/videos.py`
- Modify: `tests/unit/test_videos.py`, `tests/api/test_history_api.py`, `tests/api/test_videos_api.py`

**Interfaces:**
- Consumes: `VideoService.recent` (`videos.channel` column, already stored by the probe).
- Produces: K3 — every history item has `channel: str` (`""` when unknown). T4 types it (`HistoryItem.channel`), T12 uses it for the example.

- [ ] **Step 1: Write the failing tests**

In `tests/api/test_history_api.py`:

Replace (1):
```python
    assert set(zoo) == {"videoId", "title", "thumbnailUrl", "durationS", "outputs", "lastAt"}
```
with:
```python
    assert set(zoo) == {"videoId", "title", "channel", "thumbnailUrl", "durationS", "outputs", "lastAt"}


# ---------- M6 รอบ A: ชื่อช่อง (ตัวอย่างชื่อไฟล์แบบ title-channel ในหน้าตั้งค่า) ----------


@pytest.mark.parametrize("scope", ["opened", "all"])
def test_items_carry_the_channel(env, scope):
    client, clock, _ = env
    client.get(f"/api/videos/{BBB}")
    clock.advance(minutes=1)
    client.get(f"/api/videos/{THAI}")
    items = client.get("/api/history", params={"scope": scope}).json()["items"]
    assert [(i["videoId"], i["channel"]) for i in items] == [(THAI, "KOD THAI"), (BBB, "Blender")]


def test_an_unknown_channel_is_an_empty_string(env):
    client, _, _ = env
    client.get(f"/api/videos/{BBB}")
    env_db = client.app.state.ctx.db
    env_db.execute("UPDATE videos SET channel = NULL WHERE video_id = ?", (BBB,))
    (item,) = client.get("/api/history", params={"scope": "opened"}).json()["items"]
    assert item["channel"] == ""
```

In `tests/api/test_videos_api.py`:

Replace (1):
```python
    assert set(item) == {"videoId", "title", "thumbnailUrl", "durationS", "outputs", "lastAt"}
```
with:
```python
    assert set(item) == {"videoId", "title", "channel", "thumbnailUrl", "durationS", "outputs", "lastAt"}
    assert item["channel"] == "Blender"
```

In `tests/unit/test_videos.py`:

Replace (1):
```python
        "title": "Me at the zoo",
```
with:
```python
        "title": "Me at the zoo",
        "channel": "jawed",
```

- [ ] **Step 2: Run them, expect FAIL**

Run: `cd "$WORKTREE" && uv run pytest tests/unit/test_videos.py tests/api/test_history_api.py tests/api/test_videos_api.py -q -W error -p no:cacheprovider`
Expected: `6 failed, 266 passed` — `unit/test_videos.py::test_recent_orders_by_opened_at_desc_with_expected_fields`, `api/test_history_api.py::test_scope_all_includes_never_opened_clip_with_done_job`, `api/test_history_api.py::test_items_carry_the_channel` (×2), `api/test_history_api.py::test_an_unknown_channel_is_an_empty_string`, `api/test_videos_api.py::test_history_after_two_probes`.

- [ ] **Step 3: Implement in `src/yttoolkit/core/videos.py`**

In `src/yttoolkit/core/videos.py`:

Replace (1):
```python
        outputs = ชนิดงานที่เสร็จและมีไฟล์ (ไม่ซ้ำ) เรียงตาม HISTORY_KIND_ORDER ทั้งสอง scope
```
with:
```python
        outputs = ชนิดงานที่เสร็จและมีไฟล์ (ไม่ซ้ำ) เรียงตาม HISTORY_KIND_ORDER ทั้งสอง scope
        channel = ชื่อช่อง ("" = ไม่รู้) ตัวอย่างชื่อไฟล์ในหน้าตั้งค่าใช้ (M6 รอบ A spec 2.6)
```

Replace (2):
```python
            f"SELECT v.video_id, v.title, v.thumbnail_url, v.duration_s, {last_at} AS last_at "
```
with:
```python
            f"SELECT v.video_id, v.title, v.channel, v.thumbnail_url, v.duration_s, {last_at} AS last_at "
```

Replace (3):
```python
            f"SELECT video_id, title, thumbnail_url, duration_s, last_at {base} "
```
with:
```python
            f"SELECT video_id, title, channel, thumbnail_url, duration_s, last_at {base} "
```

Replace (4):
```python
                "title": row["title"],
```
with:
```python
                "title": row["title"],
                "channel": row["channel"] or "",
```

- [ ] **Step 4: Run the tests, expect PASS**

Run: the Step 2 command. Expected: `272 passed`. Then the full suite (all pass).

- [ ] **Step 5: Commit**
```bash
cd "$WORKTREE" && git add src/yttoolkit/core/videos.py tests/unit/test_videos.py tests/api/test_history_api.py tests/api/test_videos_api.py && git commit -F- <<'EOF'
feat(history): history items carry the channel name

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
EOF
```


### Task 4: Web foundation — every new string, types, the settings/storage API client, `isSupportedLink`, `recentQuery`

**Files:**
- Modify: `web/src/i18n/th.ts`, `web/src/lib/types.ts`, `web/src/lib/settings-api.ts`, `web/src/lib/paste.ts`, `web/src/pages/history/queries.ts`, `web/src/pages/home/recent.tsx`
- Modify: `web/src/lib/settings-api.test.ts`, `web/src/lib/paste.test.ts`, `web/src/pages/history/queries.test.ts`, `web/e2e/history.spec.ts` (P25, one line)

**Interfaces:**
- Consumes: `api()` (`lib/api.ts`), `downloadFile(url, fallbackName, deps)` (`lib/download.ts`), `historyPath` (`pages/history/queries.ts`), `looksLikeYoutube` (`lib/paste.ts`).
- Produces: K4 exactly. T9 uses `th.home.paste*` and `isSupportedLink`; T10 uses `th.general.*` (local data), `exportSettings`, `importSettings`, `storageQuery`, `clearStorage`, `STORAGE_KEY`, `MAX_SETTINGS_FILE_BYTES`, `ImportResult`, `StorageUsage`; T12 uses `th.general.filename*` and `recentQuery`.

- [ ] **Step 1: Write the failing tests**

In `web/e2e/history.spec.ts`:

Replace (1):
```ts
    title,
    thumbnailUrl: `https://i.ytimg.com/vi/${videoId}/hqdefault.jpg`,
```
with:
```ts
    title,
    channel: "",
    thumbnailUrl: `https://i.ytimg.com/vi/${videoId}/hqdefault.jpg`,
```

In `web/src/lib/paste.test.ts`:

Replace (1):
```ts
import { ID_LOOKS_RANDOM, looksLikeYoutube } from "./paste"
```
with:
```ts
import { ID_LOOKS_RANDOM, isSupportedLink, looksLikeYoutube } from "./paste"
```

Append at the end of the file:
```ts

// M6 รอบ A (C12): จุดเดียวที่ทุกทางวางเรียก วันนี้ = looksLikeYoutube ทุกข้อความ
describe("isSupportedLink", () => {
  it.each([
    "https://www.youtube.com/watch?v=aqz-KE-bpKQ",
    "youtu.be/aqz-KE-bpKQ",
    "aqz-KE-bpKQ",
    "ดูคลิปนี้ youtu.be/aqz-KE-bpKQ นะ",
    "สวัสดีครับ\n2. https://www.youtube.com/watch?v=jNQXAC9IVRw ขอบคุณครับ",
    "(https://www.youtube.com/playlist?list=PLfakeplaylist250)",
    "",
    "   ",
    "hello world",
    "Goodmorning",
    "development",
    "https://example.com/youtu.be/aqz-KE-bpKQ",
    "me@youtube.com/watch?v=dQw4w9WgXcQ",
    "a.youtu.be/dQw4w9WgXcQ",
    "https://vimeo.com/76979871",
  ])("ตรงกับ looksLikeYoutube: %j", (text) => {
    expect(isSupportedLink(text)).toBe(looksLikeYoutube(text))
  })
})
```

In `web/src/lib/settings-api.test.ts`:

Replace (1):
```ts
import {
  openOutputFolder,
```
with:
```ts
import {
  clearStorage,
  exportSettings,
  importSettings,
  MAX_SETTINGS_FILE_BYTES,
  openOutputFolder,
```

Replace (2):
```ts
  settingsQuery,
```
with:
```ts
  settingsQuery,
  STORAGE_KEY,
  storageQuery,
```

Append at the end of the file:
```ts

// M6 รอบ A: สำรอง/นำเข้าค่าตั้ง (spec 4.3) และข้อมูลชั่วคราว (spec 3.4)
describe("settings-api M6 รอบ A", () => {
  it("exportSettings โหลด GET /api/settings/export แล้วบันทึกด้วยชื่อจาก Content-Disposition", async () => {
    const fetch = vi.fn().mockResolvedValue(
      new Response("{}\n", {
        status: 200,
        headers: { "Content-Disposition": "attachment; filename=\"yt-toolkit-settings-2026-10-14.json\"" },
      })
    )
    const save = vi.fn()
    await expect(exportSettings({ fetch, save })).resolves.toBe("yt-toolkit-settings-2026-10-14.json")
    expect(fetch).toHaveBeenCalledWith("/api/settings/export")
    expect(save).toHaveBeenCalledWith(expect.any(Blob), "yt-toolkit-settings-2026-10-14.json")
  })

  it("exportSettings ไม่มี Content-Disposition ใช้ชื่อสำรอง", async () => {
    const fetch = vi.fn().mockResolvedValue(new Response("{}", { status: 200 }))
    const save = vi.fn()
    await expect(exportSettings({ fetch, save })).resolves.toBe("yt-toolkit-settings.json")
  })

  it("importSettings ส่ง POST เนื้อไฟล์ดิบพร้อม token และ Content-Type JSON คืน {settings, warnings}", async () => {
    const body = { settings: { theme: "dark" }, warnings: ["outputDir"] }
    const fetch = vi.fn().mockResolvedValue(jsonResponse(200, body))
    const text = '{"app": "yt-toolkit", "schema": 1, "settings": {"theme": "dark"}}'
    await expect(importSettings(text, { fetch, token: "tok" })).resolves.toEqual(body)
    const [url, init] = fetch.mock.calls[0]
    expect(`${init.method} ${url}`).toBe("POST /api/settings/import")
    expect(init.body).toBe(text) // ไม่ parse ไม่แก้ backend ตรวจเอง
    const headers = new Headers(init.headers)
    expect(headers.get("X-Toolkit-Token")).toBe("tok")
    expect(headers.get("Content-Type")).toBe("application/json")
  })

  it("importSettings ไฟล์ผิดรูปแบบได้ ApiError E_SETTINGS_INVALID พร้อม status", async () => {
    const fetch = vi.fn().mockResolvedValue(
      jsonResponse(413, { error: { code: "E_SETTINGS_INVALID", message: "ไฟล์นี้ใช้ไม่ได้", detail: "file larger than 1048576 bytes" } })
    )
    await expect(importSettings("x", { fetch, token: "tok" })).rejects.toMatchObject({
      status: 413,
      code: "E_SETTINGS_INVALID",
      detail: "file larger than 1048576 bytes",
    })
  })

  it("storageQuery อ่าน GET /storage ด้วยคีย์ ['storage'] · clearStorage POST พร้อม token", async () => {
    const usage = { cacheBytes: 1_200_000_000, workBytes: 5, reclaimableBytes: 1_200_000_005 }
    const fetch = vi.fn().mockResolvedValueOnce(jsonResponse(200, usage)).mockResolvedValueOnce(jsonResponse(200, { freedBytes: 42 }))
    const query = storageQuery({ fetch })
    expect(query.queryKey).toEqual(["storage"])
    expect(STORAGE_KEY).toEqual(["storage"])
    await expect(query.queryFn()).resolves.toEqual(usage)
    expect(fetch.mock.calls[0][0]).toBe("/api/storage")
    await expect(clearStorage({ fetch, token: "tok" })).resolves.toEqual({ freedBytes: 42 })
    const [url, init] = fetch.mock.calls[1]
    expect(`${init.method} ${url}`).toBe("POST /api/storage/clear")
    expect(new Headers(init.headers).get("X-Toolkit-Token")).toBe("tok")
  })

  it("เพดานไฟล์ค่าตั้ง 1 MB ตรงกับ backend", () => {
    expect(MAX_SETTINGS_FILE_BYTES).toBe(1_048_576)
  })
})
```

In `web/src/pages/history/queries.test.ts`:

Replace (1):
```ts
import { HISTORY_PAGE_SIZE, historyPath, historyQuery, nextHistoryOffset, outputLabels } from "./queries"
```
with:
```ts
import { HISTORY_PAGE_SIZE, historyPath, historyQuery, nextHistoryOffset, outputLabels, RECENT_LIMIT, recentQuery } from "./queries"
```

Replace (2):
```ts
  title: `คลิป ${n}`,
```
with:
```ts
  title: `คลิป ${n}`,
  channel: "",
```

Replace (3):
```ts

describe("outputLabels", () => {
```
with:
```ts

describe("recentQuery", () => {
  it("คีย์เดิมของ W1 'ล่าสุด' (5 คลิป scope=opened) หน้าตั้งค่าใช้ตัวเดียวกันจึงได้ cache เดียวกัน", () => {
    expect(RECENT_LIMIT).toBe(5)
    expect(recentQuery().queryKey).toEqual(["history", { limit: 5, scope: "opened" }])
    expect(recentQuery(1).queryKey).toEqual(["history", { limit: 1, scope: "opened" }])
  })
})

describe("outputLabels", () => {
```

- [ ] **Step 2: Run them, expect FAIL**

Run: `cd "$WORKTREE/web" && npm run typecheck`
Expected: `tsc` fails (first errors: `src/lib/paste.test.ts(3,27): error TS2305: Module '"./paste"' has no exported member 'isSupportedLink'.`; `src/lib/settings-api.test.ts(4,3): error TS2305: Module '"./settings-api"' has no exported member 'clearStorage'.`; `src/lib/settings-api.test.ts(5,3): error TS2305: Module '"./settings-api"' has no exported member 'exportSettings'.`; `src/lib/settings-api.test.ts(6,3): error TS2305: Module '"./settings-api"' has no exported member 'importSettings'.`; `src/lib/settings-api.test.ts(7,3): error TS2305: Module '"./settings-api"' has no exported member 'MAX_SETTINGS_FILE_BYTES'.`).

- [ ] **Step 3: Implement**

All Thai strings below are copied from spec §9 (sources: PRD :101, :306, :307, W7 :325, §7 :814, BRD FR-IN-7 / FR-OUT-8 / FR-SET-6..7, Pete Q1-Q3). Do not change a character.

In `web/src/i18n/th.ts`:

Replace (1):
```ts
    analyze: "วิเคราะห์",
```
with:
```ts
    analyze: "วิเคราะห์",
    // M6 รอบ A (PRD W1, BRD FR-IN-7): ปุ่มวางจากคลิปบอร์ด · เบราว์เซอร์ไม่ให้อ่าน = คำแนะนำใต้ช่อง ({key} = Ctrl+V / ⌘V)
    paste: "วาง",
    pasteDenied: "เบราว์เซอร์ไม่อนุญาตให้อ่านคลิปบอร์ด คลิกในช่องแล้วกด {key} แทน",
```

Replace (2):
```ts
    loadError: "โหลดค่าตั้งไม่สำเร็จ",
```
with:
```ts
    loadError: "โหลดค่าตั้งไม่สำเร็จ",
    // M6 รอบ A (spec 9): รูปแบบชื่อไฟล์ (PRD :306, BRD FR-OUT-8) · ชื่อตัวอย่างเมื่อยังไม่เคยเปิดคลิป (Pete Q1 = B)
    filenameStyle: "รูปแบบชื่อไฟล์",
    filenameStyles: { title: "ชื่อคลิป", "title-channel": "ชื่อคลิป - ช่อง", "title-quality": "ชื่อคลิป (คุณภาพ)" },
    filenameExample: "ตัวอย่าง: {name}",
    filenameSample: "สอนทำกับข้าวง่าย ๆ ใน 10 นาที",
    filenameSampleChannel: "ครัวบ้านเรา",
    // ข้อมูลในเครื่อง (PRD :307, W7 :325, BRD FR-SET-6..7, PRD §7 :814) · Pete Q2 = B, Q3
    localData: "ข้อมูลในเครื่อง",
    clearTemp: "ล้างข้อมูลชั่วคราว ({size})",
    clearTempPlain: "ล้างข้อมูลชั่วคราว",
    clearConfirmTitle: "ล้างข้อมูลชั่วคราว {size}?",
    clearConfirmBody: "ไฟล์ที่โหลดไว้ ประวัติ และค่าตั้งยังอยู่ครบ แต่เปิดคลิปเก่าต้องดึงภาพใหม่",
    clearCancel: "ยกเลิก",
    clearConfirm: "ล้างเลย",
    cleared: "ล้างแล้ว ได้พื้นที่คืน {size}",
    backup: "สำรองค่าตั้ง",
    import: "นำเข้าค่าตั้ง",
    settingsInvalid: 'ไฟล์นี้ไม่ใช่ไฟล์ค่าตั้งของ YT Toolkit หรือไฟล์เสียหาย ลองเลือกไฟล์ที่ได้จากปุ่ม "สำรองค่าตั้ง"',
    imported: "นำเข้าค่าตั้งแล้ว",
    importedKeptFolder: "นำเข้าค่าตั้งแล้ว แต่ใช้โฟลเดอร์ผลลัพธ์ในไฟล์บนเครื่องนี้ไม่ได้ จึงใช้โฟลเดอร์เดิมต่อ",
```

In `web/src/lib/paste.ts`:

Append at the end of the file:
```ts

/**
 * ข้อความนี้เป็นลิงก์ที่แอพวิเคราะห์ได้ไหม (วางแล้ววิเคราะห์ทันที) — จุดเดียวที่ทุกทางวางเรียก
 * (ปุ่ม "วาง", วางในช่อง, Ctrl/⌘+V นอกช่อง) วันนี้รับแค่ยูทูป เว็บอื่นในอนาคตเพิ่มที่ฟังก์ชันนี้ที่เดียว (M6 รอบ A C12)
 */
export function isSupportedLink(text: string): boolean {
  return looksLikeYoutube(text)
}
```

In `web/src/lib/settings-api.ts`:

Replace (1):
```ts
import { api } from "./api"
```
with:
```ts
import { api } from "./api"
import { downloadFile } from "./download"
```

Append at the end of the file:
```ts

// ---------- M6 รอบ A: สำรอง/นำเข้าค่าตั้ง และข้อมูลชั่วคราว ----------

/** ไฟล์ค่าตั้งใหญ่สุดที่นำเข้าได้ (ตรงกับ MAX_SETTINGS_IMPORT_BYTES ของ backend · เกิน = ไม่ส่ง) */
export const MAX_SETTINGS_FILE_BYTES = 1_048_576

/** ชื่อสำรองเมื่อ backend ไม่ส่ง Content-Disposition (ปกติได้ yt-toolkit-settings-YYYY-MM-DD.json) */
export const SETTINGS_FILE_FALLBACK = "yt-toolkit-settings.json"

type DownloadDeps = Parameters<typeof downloadFile>[2]

/** สำรองค่าตั้ง: โหลด GET /api/settings/export ลงเครื่อง คืนชื่อไฟล์ที่บันทึก · ล้มเหลว = ApiError */
export function exportSettings(deps?: DownloadDeps): Promise<string> {
  return downloadFile("/api/settings/export", SETTINGS_FILE_FALLBACK, deps)
}

export type ImportResult = { settings: Settings; warnings: string[] }

/** นำเข้าค่าตั้งจากเนื้อไฟล์ (ส่งข้อความดิบ backend ตรวจเอง) · ไฟล์ผิดรูปแบบ = ApiError 422/413 E_SETTINGS_INVALID */
export function importSettings(text: string, deps?: ApiDeps): Promise<ImportResult> {
  return api<ImportResult>("/settings/import", { method: "POST", body: text }, deps)
}

export const STORAGE_KEY = ["storage"] as const

/** ขนาดของ data/cache และ work/ (ไบต์) · reclaimableBytes = ส่วนที่ปุ่ม "ล้างข้อมูลชั่วคราว" ลบได้ตอนนี้ */
export type StorageUsage = { cacheBytes: number; workBytes: number; reclaimableBytes: number }

export function storageQuery(deps?: ApiDeps): {
  queryKey: typeof STORAGE_KEY
  queryFn: () => Promise<StorageUsage>
} {
  return {
    queryKey: STORAGE_KEY,
    queryFn: () => api<StorageUsage>("/storage", {}, deps),
  }
}

/** ล้างข้อมูลชั่วคราวที่ไม่มีงานใช้ คืนจำนวนไบต์ที่ได้คืนจริง */
export function clearStorage(deps?: ApiDeps): Promise<{ freedBytes: number }> {
  return api<{ freedBytes: number }>("/storage/clear", { method: "POST" }, deps)
}
```

In `web/src/lib/types.ts`:

Replace (1):
```ts
  title: string
  thumbnailUrl: string
```
with:
```ts
  title: string
  /** ชื่อช่อง ("" = ไม่รู้) ใช้ทำตัวอย่างชื่อไฟล์แบบ title-channel ในหน้าตั้งค่า (M6 รอบ A) */
  channel: string
  thumbnailUrl: string
```

In `web/src/pages/history/queries.ts`:

Replace (1):
```ts
import { infiniteQueryOptions, keepPreviousData } from "@tanstack/react-query"
```
with:
```ts
import { infiniteQueryOptions, keepPreviousData, queryOptions } from "@tanstack/react-query"
```

Replace (2):
```ts

/** ป้ายชนิดไฟล์ของแถว: ชนิดที่ใช้ป้ายเดียวกัน (เช่น contact sheet กับ zip ภาพ = "ภาพ") แสดงครั้งเดียว ลำดับตามที่ backend ส่งมา */
```
with:
```ts

/** W1 "ล่าสุด" จำนวนคลิป */
export const RECENT_LIMIT = 5

/**
 * คลิปที่เปิดดูล่าสุด (W1 "ล่าสุด" และตัวอย่างชื่อไฟล์ในหน้าตั้งค่า M6 รอบ A) ใช้คีย์เดียวกันจึงใช้ cache ร่วมกัน
 * "opened" = เฉพาะคลิปที่เคยเปิดดูในหน้า W2 (หน้า /history แสดงคลิปที่โหลดไฟล์ด้วย)
 */
export function recentQuery(limit = RECENT_LIMIT) {
  return queryOptions({
    queryKey: ["history", { limit, scope: "opened" }] as const,
    queryFn: () => api<HistoryPage>(historyPath({ limit, scope: "opened" })),
  })
}

/** ป้ายชนิดไฟล์ของแถว: ชนิดที่ใช้ป้ายเดียวกัน (เช่น contact sheet กับ zip ภาพ = "ภาพ") แสดงครั้งเดียว ลำดับตามที่ backend ส่งมา */
```

In `web/src/pages/home/recent.tsx`:

Replace (1):
```tsx
import { api } from "@/lib/api"
import { formatDuration, relativeTime } from "@/lib/format"
import type { HistoryPage } from "@/lib/types"

import { historyPath } from "../history/queries"
import { Thumbnail } from "./thumbnail"

const LIMIT = 5
```
with:
```tsx
import { formatDuration, relativeTime } from "@/lib/format"

import { recentQuery } from "../history/queries"
import { Thumbnail } from "./thumbnail"

```

Replace (2):
```tsx
  const history = useQuery({
    // "ล่าสุด" = เฉพาะคลิปที่เคยเปิดดูในหน้า W2 (หน้า /history แสดงคลิปที่โหลดไฟล์ด้วย)
    queryKey: ["history", { limit: LIMIT, scope: "opened" }],
    queryFn: () => api<HistoryPage>(historyPath({ limit: LIMIT, scope: "opened" })),
  })
```
with:
```tsx
  // "ล่าสุด" = เฉพาะคลิปที่เคยเปิดดูในหน้า W2 · คีย์เดียวกับตัวอย่างชื่อไฟล์ในหน้าตั้งค่า (M6 รอบ A)
  const history = useQuery(recentQuery())
```

- [ ] **Step 4: Run the tests, expect PASS**

Run: `cd "$WORKTREE/web" && npm run typecheck && npm run lint && npm test`
Expected: typecheck clean, lint clean, vitest `1059 passed (1059)`.

- [ ] **Step 5: Commit**
```bash
cd "$WORKTREE" && git add web/src/i18n/th.ts web/src/lib/types.ts web/src/lib/settings-api.ts web/src/lib/settings-api.test.ts web/src/lib/paste.ts web/src/lib/paste.test.ts web/src/pages/history/queries.ts web/src/pages/history/queries.test.ts web/src/pages/home/recent.tsx web/e2e/history.spec.ts && git commit -F- <<'EOF'
feat(web): M6 round A strings, history channel type, settings and storage API client, isSupportedLink, shared recent query

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
EOF
```

---

## Wave 2

### Task 5: Names on disk — style, channel and quality labels in the handlers (spec 2.1, 2.3; AC-OUT-09)

**Files:**
- Modify: `src/yttoolkit/core/handlers.py`, `src/yttoolkit/core/download.py`, `src/yttoolkit/core/extractor.py`
- Modify: `tests/unit/test_handlers.py`, `tests/unit/test_handlers_sharp.py`, `tests/helpers_sharp.py`, `tests/unit/test_handlers_account.py`, `tests/unit/test_lifecycle.py` (one line: the fake context, P6), `tests/unit/test_extractor_download.py`, `tests/unit/test_download_choice.py`, `tests/network/test_advanced_network.py`, `tests/network/test_download_network.py`, `tests/network/test_sharp_network.py`

**Interfaces:**
- Consumes: T1 `files.plan_output(..., style=, uploader=, quality=)`; T2 `JobContext.filename_style`; `download.media_facts`, `download._number`; `media.CUT_AAC_KBPS`; `DownloadResult.media`.
- Produces: K5 — `MediaFacts.abr_kbps`, `handlers.STANDARD_KBPS`, `handlers.standard_kbps`, `_Clip.style` / `_Clip.uploader`, `_finish(..., quality=)`. `_downloaded_facts` returns facts when the height **or** the audio bitrate is known.

- [ ] **Step 1: Write the failing tests**

In `tests/helpers_sharp.py`:

Replace (1):
```python
        self.output_root = output_root
```
with:
```python
        self.output_root = output_root
        self.filename_style = "title"  # M6 รอบ A: JobContext.filename_style
```

Replace (2):
```python
        self, kind: str, video_id: str, params: dict, *, cancel_on: str | None = None, deps: HandlerDeps | None = None
```
with:
```python
        self,
        kind: str,
        video_id: str,
        params: dict,
        *,
        cancel_on: str | None = None,
        deps: HandlerDeps | None = None,
        style: str = "title",
```

Replace (3):
```python
        ctx = Ctx(workdir, self.out, cancel_on=cancel_on)
```
with:
```python
        ctx = Ctx(workdir, self.out, cancel_on=cancel_on)
        ctx.filename_style = style
```

In `tests/network/test_advanced_network.py`:

Replace (1):
```python
        self.output_root = output_root
```
with:
```python
        self.output_root = output_root
        self.filename_style = "title"  # M6 รอบ A: JobContext.filename_style
```

In `tests/network/test_download_network.py`:

Replace (1):
```python
        self.output_root = output_root
```
with:
```python
        self.output_root = output_root
        self.filename_style = "title"  # M6 รอบ A: JobContext.filename_style
```

In `tests/network/test_sharp_network.py`:

Replace (1):
```python
        self.output_root = output_root
```
with:
```python
        self.output_root = output_root
        self.filename_style = "title"  # M6 รอบ A: JobContext.filename_style
```

In `tests/unit/test_download_choice.py`:

Append at the end of the file:
```python
    # M6 รอบ A: bitrate เสียงตามที่ yt-dlp บอก (ยังไม่ปัด) ค่าที่ไม่ใช่ตัวเลขบวก = ไม่รู้
    assert media_facts({"abr": 129.478}).abr_kbps == 129.478
    assert media_facts({"abr": 0}).abr_kbps is None and media_facts({"abr": "x"}).abr_kbps is None
    assert MediaFacts(1280, 720, "SDR").abr_kbps is None
```

In `tests/unit/test_extractor_download.py`:

Replace (1):
```python

def test_real_download_without_facts_reports_none(dl: type[DownloadYDL], workdir: Path) -> None:
```
with:
```python

def test_real_audio_download_reports_its_bitrate(dl: type[DownloadYDL], workdir: Path) -> None:
    # M6 รอบ A: ไฟล์เสียงอย่างเดียวไม่มีความสูง แต่มี abr (ส่วน "(m4a 128k)" ของชื่อไฟล์)
    dl.result = {"id": BBB, "requested_downloads": [{"filepath": str(workdir / "media.m4a"), "abr": 129.478}]}
    result = YtDlpExtractor().download(BBB, _video(), workdir, Recorder().hooks)
    assert result.media == MediaFacts(None, None, None, 129.478)


def test_real_download_without_facts_reports_none(dl: type[DownloadYDL], workdir: Path) -> None:
```

In `tests/unit/test_handlers.py`:

Replace (1):
```python
from yttoolkit.core import files
```
with:
```python
from yttoolkit.core import files, handlers
```

Replace (2):
```python
    DownloadResult,
```
with:
```python
    DownloadResult,
    MediaFacts,
```

Replace (3):
```python
    def __init__(self, workdir: Path, output_root: Path, cancel_on: str | None = None) -> None:
        self.job_id = "01900000-0000-7000-8000-000000000001"
        self.workdir = workdir
        self.output_root = output_root
```
with:
```python
    def __init__(
        self, workdir: Path, output_root: Path, cancel_on: str | None = None, filename_style: str = "title"
    ) -> None:
        self.job_id = "01900000-0000-7000-8000-000000000001"
        self.workdir = workdir
        self.output_root = output_root
        self.filename_style = filename_style  # M6 รอบ A: รูปแบบชื่อไฟล์ที่คิวตั้งให้งาน
```

Replace (4):
```python
        self.fetched: list[str] = []
```
with:
```python
        self.fetched: list[str] = []
        self.media: MediaFacts | None = None  # M6 รอบ A: ข้อมูลไฟล์ที่โหลดจริง (ส่วนคุณภาพของชื่อไฟล์)
```

Replace (5):
```python
        shutil.copyfile(source, target)
        return DownloadResult(target, info, choice)
```
with:
```python
        shutil.copyfile(source, target)
        return DownloadResult(target, info, choice, self.media)
```

Replace (6):
```python
        self, kind: str, video_id: str, params: dict, *, cancel_on: str | None = None, deps: HandlerDeps | None = None
```
with:
```python
        self,
        kind: str,
        video_id: str,
        params: dict,
        *,
        cancel_on: str | None = None,
        deps: HandlerDeps | None = None,
        style: str = "title",
```

Replace (7):
```python
        ctx = RecordingContext(workdir, self.out, cancel_on=cancel_on)
```
with:
```python
        ctx = RecordingContext(workdir, self.out, cancel_on=cancel_on, filename_style=style)
```

Append at the end of the file:
```python



# ---------- M6 รอบ A: รูปแบบชื่อไฟล์ (spec 2.1 / 2.3, D3) ----------

THAI_CHANNEL = "KOD THAI"
THAI_SAFE = "Thai Listening Practice EP.1 Beginner"  # "|" ใช้ในชื่อไฟล์ไม่ได้
FULL_HD = MediaFacts(1920, 1080, "SDR")


def styled(env: Env, video_id: str, title: str, suffix: str, ext: str, style: str, quality: str | None) -> Path:
    channel = THAI_CHANNEL if video_id == THAI else ""
    return files.plan_output(env.out.resolve(), title, video_id, suffix, ext, style=style, uploader=channel,
                             quality=quality)  # fmt: skip


@pytest.mark.parametrize(
    ("style", "name"),
    [
        ("title", f"{THAI_SAFE}.mp4"),
        ("title-channel", f"{THAI_SAFE} - {THAI_CHANNEL}.mp4"),
        ("title-quality", f"{THAI_SAFE} (1080p).mp4"),
    ],
)
def test_video_name_follows_the_job_style(env, style, name):
    env.downloader.media = FULL_HD
    result, _ = env.run("video", THAI, video_params(), style=style)
    path = output_path(result)
    assert path.name == name
    assert path == styled(env, THAI, THAI_TITLE, "", "mp4", style, "1080p")
    assert path.parent == env.planned(THAI, THAI_TITLE, "", "mp4").parent  # โฟลเดอร์ของคลิปเดิมทุกแบบ


def test_a_vertical_video_uses_the_short_side(env):
    env.downloader.media = MediaFacts(1080, 1920, "SDR")
    result, _ = env.run("video", THAI, video_params(), style="title-quality")
    assert output_path(result).name == f"{THAI_SAFE} (1080p).mp4"


def test_unknown_video_facts_give_no_quality_part(env):
    result, _ = env.run("video", THAI, video_params(), style="title-quality")
    assert output_path(result).name == f"{THAI_SAFE}.mp4"


def test_the_quality_part_comes_before_the_existing_suffixes(env):
    env.downloader.media = MediaFacts(1280, 720, "SDR")
    result, _ = env.run("video", THAI, video_params(noAudio=True, range={"startMs": 90_000, "endMs": 300_000}),
                        style="title-quality")  # fmt: skip
    assert output_path(result).name == f"{THAI_SAFE} (720p) (ไม่มีเสียง) (01.30-05.00).mp4"


@pytest.mark.parametrize(
    ("fmt", "params", "media", "quality"),
    [
        ("mp3", {}, None, "mp3 192k"),
        ("mp3", {"mp3Kbps": 320}, None, "mp3 320k"),
        ("m4a", {}, MediaFacts(None, None, None, 129.5), "m4a 128k"),
        ("m4a", {}, MediaFacts(None, None, None, 49.2), "m4a 48k"),
        ("m4a", {}, None, "m4a"),
        ("wav", {}, MediaFacts(None, None, None, 129.5), "wav"),
    ],
)
def test_audio_quality_part(env, fmt, params, media, quality):
    env.downloader.media = media
    result, _ = env.run("audio", THAI, audio_params(fmt, **params), style="title-quality")
    assert output_path(result).name == f"{THAI_SAFE} ({quality}).{fmt}"


def test_a_cut_m4a_is_named_by_the_re_encoded_bitrate(env):
    env.downloader.media = MediaFacts(None, None, None, 129.5)
    result, _ = env.run("audio", THAI, audio_params("m4a", range={"startMs": 90_000, "endMs": 300_000}),
                        style="title-quality")  # fmt: skip
    assert output_path(result).name == f"{THAI_SAFE} (m4a 192k) (01.30-05.00).m4a"


def test_audio_title_channel(env):
    result, _ = env.run("audio", THAI, audio_params("mp3"), style="title-channel")
    assert output_path(result).name == f"{THAI_SAFE} - {THAI_CHANNEL}.mp3"


@pytest.mark.parametrize(
    ("kind", "params", "plain", "channel"),
    [
        ("subtitle", {"trackId": "a.th-orig", "format": "srt", "options": MEDIUM}, ".th.srt",
         f" - {THAI_CHANNEL}.th.srt"),
        ("note", {}, ".note.md", f" - {THAI_CHANNEL}.note.md"),
        ("contact_sheet", {"source": "fast", "columns": 5}, " - contact sheet.jpg",
         f" - {THAI_CHANNEL} - contact sheet.jpg"),
        ("frames_zip", {"source": "fast"}, " - frames.zip", f" - {THAI_CHANNEL} - frames.zip"),
    ],
)
def test_other_kinds_get_the_channel_but_never_a_quality_part(env, kind, params, plain, channel):
    env.downloader.media = FULL_HD
    plain_result, _ = env.run(kind, THAI, params, style="title-quality")
    channel_result, _ = env.run(kind, THAI, params, style="title-channel")
    assert output_path(plain_result).name == f"{THAI_SAFE}{plain}"
    assert output_path(channel_result).name == f"{THAI_SAFE}{channel}"
    assert output_path(plain_result).parent == output_path(channel_result).parent


@pytest.mark.parametrize("style", ["title-channel", "title-quality"])
def test_chapter_split_names_ignore_the_style(env, style):
    env.downloader.media = FULL_HD
    result, _ = env.run("video", ZOO, video_params(splitChapters=True), style=style)
    clip_folder = env.planned(ZOO, ZOO_TITLE, "", "mp4").parent
    assert [Path(o.rel).name for o in result.outputs] == [f"{n}.mp4" for n in ZOO_NAMES]
    assert {(Path(o.root) / o.rel).parent for o in result.outputs} == {clip_folder / "แยกตาม chapter (mp4)"}


def test_an_unknown_channel_gives_the_plain_title(env, monkeypatch):
    real = env.videos.get
    monkeypatch.setattr(env.videos, "get", lambda video_id, **kw: {**real(video_id, **kw), "channel": None})
    result, _ = env.run("video", THAI, video_params(), style="title-channel")
    assert output_path(result).name == f"{THAI_SAFE}.mp4"


def test_the_style_names_never_reach_the_log(env, caplog):
    caplog.set_level(logging.DEBUG, logger="yttoolkit")
    env.downloader.media = FULL_HD
    env.run("video", THAI, video_params(), style="title-channel")
    env.run("audio", THAI, audio_params("mp3"), style="title-quality")
    assert THAI_CHANNEL not in caplog.text and "Thai Listening" not in caplog.text
    assert "1080p" not in caplog.text and "mp3 192k" not in caplog.text


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (129.5, 128), (112, 128), (144, 160), (150, 160), (140, 128), (20, 32), (500, 320),
        *((kbps, kbps) for kbps in handlers.STANDARD_KBPS),
        (float("nan"), None), (float("inf"), None), (0, None), (-5, None), (None, None), (True, None),
    ],
)
def test_standard_kbps(value, expected):
    assert handlers.standard_kbps(value) == expected
```

In `tests/unit/test_handlers_account.py`:

Replace (1):
```python
        self.output_root = output_root
```
with:
```python
        self.output_root = output_root
        self.filename_style = "title"  # M6 รอบ A: JobContext.filename_style
```

In `tests/unit/test_handlers_sharp.py`:

Append at the end of the file:
```python


# ---------- M6 รอบ A: รูปแบบชื่อไฟล์ไม่เปลี่ยนชื่อโฟลเดอร์ภาพคม (D3) ----------


@pytest.mark.parametrize("style", ["title-channel", "title-quality"])
def test_the_sharp_folder_ignores_the_filename_style(env, style):
    result, _ = env.run("frames_sharp", BBB, {"intervalS": 60}, style=style)
    assert _folder(result) == files.plan_sharp_dir(env.out.resolve(), BBB_TITLE, BBB)
    assert _folder(result).parent == _clip_folder(env)
```

In `tests/unit/test_lifecycle.py`:

Replace (1):
```python
        self.output_root = output_root
```
with:
```python
        self.output_root = output_root
        self.filename_style = "title"  # M6 รอบ A: JobContext.filename_style
```

- [ ] **Step 2: Run them, expect FAIL**

Run: `cd "$WORKTREE" && uv run pytest tests/unit/test_handlers.py tests/unit/test_handlers_account.py tests/unit/test_handlers_sharp.py tests/unit/test_handlers_auto_sharp.py tests/unit/test_extractor_download.py tests/unit/test_download_choice.py tests/unit/test_lifecycle.py -q -W error -p no:cacheprovider`
Expected: `1 error` (collection error in `unit/test_handlers.py`) (`tests/unit/test_handlers.py` does not even collect: `module 'yttoolkit.core.handlers' has no attribute 'STANDARD_KBPS'`).

- [ ] **Step 3: Implement**

In `src/yttoolkit/core/download.py`:

Replace (1):
```python
    dynamic_range: str | None  # "SDR" | "HDR10" | "HLG" | ... (yt-dlp ใส่ "SDR" ให้ format วิดีโอที่ไม่บอก)
```
with:
```python
    dynamic_range: str | None  # "SDR" | "HDR10" | "HLG" | ... (yt-dlp ใส่ "SDR" ให้ format วิดีโอที่ไม่บอก)
    # M6 รอบ A: bitrate เสียงของไฟล์ที่โหลดจริง (kbps ตามที่ yt-dlp บอก ยังไม่ปัด) ใช้ทำส่วน "(m4a 128k)" ของชื่อไฟล์
    abr_kbps: float | None = None
```

Replace (2):
```python
        dynamic if isinstance(dynamic, str) and dynamic else None,
```
with:
```python
        dynamic if isinstance(dynamic, str) and dynamic else None,
        _number(fmt.get("abr")),
```

In `src/yttoolkit/core/extractor.py`:

Replace (1):
```python
    """ขนาดภาพและช่วงสีของไฟล์ที่โหลดจริง: requested_downloads ตัวสุดท้าย (yt-dlp รวมค่าของภาพไว้ให้ตอนรวมไฟล์)
    หรือผลระดับบน · ไม่รู้ความสูง = None"""
```
with:
```python
    """ขนาดภาพ ช่วงสี และ bitrate เสียงของไฟล์ที่โหลดจริง: requested_downloads ตัวสุดท้าย (yt-dlp รวมค่าของภาพไว้ให้
    ตอนรวมไฟล์) หรือผลระดับบน · ไม่รู้ทั้งความสูงและ bitrate เสียง = None (M6 รอบ A: ไฟล์เสียงอย่างเดียวมีแค่ bitrate)"""
```

Replace (2):
```python
    return facts if facts.height is not None else None
```
with:
```python
    return facts if facts.height is not None or facts.abr_kbps is not None else None
```

In `src/yttoolkit/core/handlers.py`:

Replace (1):
```python
from .media import SHARP_LONG_SIDE, CutMode, CutTarget, MediaMeta, MediaTools, SubtitleInput, iso639_2
```
with:
```python
from .media import CUT_AAC_KBPS, SHARP_LONG_SIDE, CutMode, CutTarget, MediaMeta, MediaTools, SubtitleInput, iso639_2
```

Replace (2):
```python
_EMBED_RETRY_CODES = frozenset({"E_NETWORK", "E_BOT_CHECK"})
```
with:
```python
_EMBED_RETRY_CODES = frozenset({"E_NETWORK", "E_BOT_CHECK"})
# M6 รอบ A (Pete Q4 = B): ส่วนคุณภาพของชื่อไฟล์เสียงใช้ bitrate มาตรฐานที่ใกล้ที่สุด (กึ่งกลาง = ค่าที่สูงกว่า)
STANDARD_KBPS = (32, 48, 64, 96, 128, 160, 192, 256, 320)
```

Replace (3):
```python
    group: str | None = None  # params.folder ดิบ (files.plan_output ทำความสะอาดเอง) None = ไม่มีโฟลเดอร์กลุ่ม
```
with:
```python
    group: str | None = None  # params.folder ดิบ (files.plan_output ทำความสะอาดเอง) None = ไม่มีโฟลเดอร์กลุ่ม
    style: str = "title"  # M6 รอบ A: รูปแบบชื่อไฟล์ของงาน (ctx.filename_style ที่คิวตั้งตอนเริ่มครั้งแรก)
    uploader: str = ""  # ชื่อช่องดิบจากข้อมูลคลิป (files.plan_names ทำความสะอาดเอง) ใช้เฉพาะแบบ title-channel
```

Replace (4):
```python
    return _Clip(job.video_id, info, title, root, job_group(job.params))
```
with:
```python
    uploader = str(info.get("channel") or "")
    return _Clip(job.video_id, info, title, root, job_group(job.params), style=ctx.filename_style, uploader=uploader)
```

Replace (5):
```python
) -> JobResult:
    """ย้ายไฟล์ที่เสร็จแล้วเข้าโฟลเดอร์ของคลิป เขียนแหล่งที่มา.txt แล้วคืนผลของงาน"""
    ctx.check_cancelled()
    planned = files.plan_output(clip.root, clip.title, clip.video_id, suffix, ext, clip.group)
```
with:
```python
    quality: str | None = None,
) -> JobResult:
    """ย้ายไฟล์ที่เสร็จแล้วเข้าโฟลเดอร์ของคลิป เขียนแหล่งที่มา.txt แล้วคืนผลของงาน
    ชื่อไฟล์ตามรูปแบบของงาน (clip.style) · quality = ส่วนคุณภาพของแบบ title-quality (วิดีโอ/เสียงเท่านั้น)"""
    ctx.check_cancelled()
    planned = files.plan_output(clip.root, clip.title, clip.video_id, suffix, ext, clip.group,
                                style=clip.style, uploader=clip.uploader, quality=quality)  # fmt: skip
```

Replace (6):
```python
    return tuple(dict.fromkeys(notes))
```
with:
```python
    return tuple(dict.fromkeys(notes))


def standard_kbps(value: float | None) -> int | None:
    """bitrate มาตรฐานที่ใกล้ value ที่สุดจาก STANDARD_KBPS (ห่างเท่ากัน = ค่าที่สูงกว่า ชื่อไฟล์จะไม่บอกต่ำกว่าจริง)
    ต่ำกว่า 32 = 32 · เกิน 320 = 320 · ไม่ใช่ตัวเลข ไม่จำกัด หรือไม่เกิน 0 = None (ไม่รู้)"""
    if isinstance(value, bool) or not isinstance(value, int | float) or not math.isfinite(value) or value <= 0:
        return None
    return min(STANDARD_KBPS, key=lambda kbps: (abs(kbps - value), -kbps))


def _video_quality(media: MediaFacts | None) -> str | None:
    """ส่วนคุณภาพของวิดีโอ: ด้านสั้นของไฟล์ที่โหลดจริง เช่น "1080p" (คลิปแนวตั้ง 1080x1920 ก็ "1080p") ไม่รู้ = None"""
    if media is None or not media.short_side:
        return None
    return f"{media.short_side}p"


def _audio_quality(fmt: str, params: Mapping[str, Any], media: MediaFacts | None, *, recoded: bool) -> str:
    """ส่วนคุณภาพของเสียง: "mp3 192k" (ค่าที่ผู้ใช้เลือก) · "m4a 128k" (bitrate ของไฟล์ที่โหลด ปัดเป็นค่ามาตรฐาน
    ถ้าตัดช่วงเวลา/โฆษณา = ไฟล์ถูกเข้ารหัสใหม่ที่ CUT_AAC_KBPS) ไม่รู้ bitrate = "m4a" · wav = "wav"
    """
    if fmt == "mp3":
        return f"mp3 {standard_kbps(int(params.get('mp3Kbps') or DEFAULT_MP3_KBPS))}k"
    if fmt == "wav":
        return "wav"
    kbps = standard_kbps(CUT_AAC_KBPS if recoded else (media.abr_kbps if media is not None else None))
    return f"m4a {kbps}k" if kbps else "m4a"
```

Replace (7):
```python
    finished = _finish(deps, ctx, clip, out, suffix=suffix, ext="mp4", kind="video", notes=notes)
```
with:
```python
    finished = _finish(deps, ctx, clip, out, suffix=suffix, ext="mp4", kind="video", notes=notes,
                       quality=_video_quality(result.media))  # fmt: skip
```

Replace (8):
```python
    return _finish(deps, ctx, clip, out, suffix=cut.suffix, ext=fmt, kind="audio", notes=notes)
```
with:
```python
    quality = _audio_quality(fmt, params, result.media, recoded=cut.path != result.path)
    return _finish(deps, ctx, clip, out, suffix=cut.suffix, ext=fmt, kind="audio", notes=notes, quality=quality)
```

Notes for the implementer:
- The label is derived at finish time from the file that was really downloaded (`result.media`), never from the requested quality: a 1080p request that fell back to 720p is named `(720p)`.
- `extractor.py` stays the only `yt_dlp` importer (C3); `media_facts` only reads the dict yt-dlp returned.
- Chapter split, sharp frames, captures and the clip folder do not take the style (D3): `_finish_chapters`, `_publish_sharp`, `plan_chapter_output`, `plan_sharp_dir` and `capture.py` are unchanged.

- [ ] **Step 4: Run the tests, expect PASS**

Run: the Step 2 command. Expected: `535 passed`. Then the full suite: `cd "$WORKTREE" && uv run pytest -q -W error -p no:cacheprovider` (all pass, including `test_logs_have_no_absolute_paths` / `test_logs_have_no_clip_title`, C5).

- [ ] **Step 5: Commit**
```bash
cd "$WORKTREE" && git add src/yttoolkit/core/handlers.py src/yttoolkit/core/download.py src/yttoolkit/core/extractor.py tests/unit/test_handlers.py tests/unit/test_handlers_sharp.py tests/helpers_sharp.py tests/unit/test_handlers_account.py tests/unit/test_lifecycle.py tests/unit/test_extractor_download.py tests/unit/test_download_choice.py tests/network/test_advanced_network.py tests/network/test_download_network.py tests/network/test_sharp_network.py && git commit -F- <<'EOF'
feat(handlers): file names follow the job's filename style with channel and standard quality labels

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
EOF
```


### Task 6: Settings backup and import (spec 4.1, 4.2; AC-SET-09, AC-SET-10)

**Files:**
- Modify: `src/yttoolkit/core/settings.py`, `src/yttoolkit/core/yterrors.py`
- Replace whole: `src/yttoolkit/api/settings.py`
- Modify: `tests/unit/test_settings.py`, `tests/api/test_settings_api.py`

**Interfaces:**
- Consumes: `SettingsStore` (`_VALIDATORS`, `_validate_output_dir`, `ensure_writable`, `READ_ONLY`, `RETIRED_KEYS`, `on_output_dir`), `api/errors.error_response`, `api/videos.attachment_header`, T2's `SettingsStore.filename_style()` (kept).
- Produces: K6 exactly. T10 calls the two routes through T4's client; T13 calls the export while the canary account is held.

- [ ] **Step 1: Write the failing tests**

In `tests/api/test_settings_api.py`:

Append at the end of the file:
```python



# ---------- M6 รอบ A: สำรอง / นำเข้าค่าตั้ง (spec 4, AC-SET-09 / AC-SET-10) ----------

import json  # noqa: E402
import re  # noqa: E402
from datetime import datetime  # noqa: E402

from yttoolkit.api import settings as settings_api  # noqa: E402
from yttoolkit.core.yterrors import MESSAGES  # noqa: E402

INVALID = MESSAGES["E_SETTINGS_INVALID"]


def _rows(db) -> list[tuple[str, str]]:
    return [(r["key"], r["value_json"]) for r in db.execute("SELECT key, value_json FROM settings ORDER BY key")]


def _import(client, content: bytes | str, headers: dict | None = None):
    data = content.encode("utf-8") if isinstance(content, str) else content
    return client.post("/api/settings/import", content=data,
                       headers={**AUTH, "Content-Type": "application/json", **(headers or {})})  # fmt: skip


def test_export_is_a_dated_attachment_without_read_only_keys(client):
    client.patch("/api/settings", json={"theme": "dark"}, headers=AUTH)
    resp = client.get("/api/settings/export")
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/json"
    assert resp.headers["cache-control"] == "no-store"
    name = f"yt-toolkit-settings-{datetime.now().astimezone():%Y-%m-%d}.json"
    assert resp.headers["content-disposition"] == f"attachment; filename=\"{name}\"; filename*=UTF-8''{name}"
    assert resp.content.endswith(b"}\n") and not resp.content.startswith(b"\xef\xbb\xbf") and b"\r" not in resp.content
    doc = resp.json()
    assert list(doc) == ["app", "schema", "exportedAt", "settings"]
    assert (doc["app"], doc["schema"]) == ("yt-toolkit", 1)
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\+00:00", doc["exportedAt"])
    assert set(doc["settings"]) == SETTING_KEYS - {"statsResetAt"}
    assert doc["settings"]["theme"] == "dark"


def test_export_needs_no_token(client):
    assert client.get("/api/settings/export", headers={"Origin": "http://127.0.0.1:8787"}).status_code == 200


def test_import_round_trip_on_a_fresh_data_folder(client, make_client, tmp_path):
    client.patch("/api/settings", json={"concurrency": 3, "filenameStyle": "title-quality"}, headers=AUTH)
    exported = client.get("/api/settings/export")
    fresh_db = Database(tmp_path / "fresh.db")
    fresh_db.migrate()
    try:
        fresh = make_client(settings=SettingsStore(fresh_db, tmp_path / "elsewhere"))
        resp = _import(fresh, exported.content)
        assert resp.status_code == 200
        body = resp.json()
        assert body["warnings"] == []
        after = fresh.get("/api/settings").json()
        for key, value in exported.json()["settings"].items():
            assert after[key] == value, key
        assert body["settings"] == after
    finally:
        fresh_db.close()


def test_import_with_a_bom_is_accepted(client):
    doc = {"app": "yt-toolkit", "schema": 1, "settings": {"theme": "light"}}
    resp = _import(client, b"\xef\xbb\xbf" + json.dumps(doc).encode("utf-8"))
    assert resp.status_code == 200 and resp.json()["settings"]["theme"] == "light"


def test_import_keeps_an_unusable_output_dir_and_warns(client, tmp_path):
    old = client.get("/api/settings").json()["outputDir"]
    doc = {"app": "yt-toolkit", "schema": 1, "settings": {"outputDir": "relative\\folder", "theme": "dark"}}
    resp = _import(client, json.dumps(doc))
    assert resp.status_code == 200
    assert resp.json()["warnings"] == ["outputDir"]
    assert resp.json()["settings"]["outputDir"] == old and resp.json()["settings"]["theme"] == "dark"


@pytest.mark.parametrize(
    ("content", "detail"),
    [
        (b"not json at all", "not JSON"),
        (b"\xff\xfe\x00garbage", "not UTF-8"),
        (b'{"app": "yt-toolkit", "schema": 1, "settings": {"concurrency": NaN}}', "not JSON"),
        (b'{"app": "other", "schema": 1, "settings": {}}', "app invalid"),
        (b'{"app": "yt-toolkit", "schema": 2, "settings": {}}', "schema invalid"),
        (b"[" * 100_000, "not JSON"),
        (b'{"app": "yt-toolkit", "schema": 1, "settings": {"theme": "SECRET-VALUE-123"}}', "theme: invalid value"),
        (b'{"app": "yt-toolkit", "schema": 1, "settings": {"outputDir": 7}}', "outputDir: invalid value"),
    ],
    ids=["not-json", "not-utf8", "nan", "other-app", "newer-schema", "deep-nesting", "bad-value", "output-dir-type"],
)
def test_import_of_a_bad_file_is_422_and_changes_nothing(client, db, content, detail):
    client.patch("/api/settings", json={"concurrency": 3}, headers=AUTH)
    before = _rows(db)
    resp = _import(client, content)
    assert resp.status_code == 422
    assert resp.json()["error"] == {"code": "E_SETTINGS_INVALID", "message": INVALID, "detail": detail}
    assert b"SECRET-VALUE-123" not in resp.content  # 422 ไม่ยกค่าในไฟล์กลับ
    assert _rows(db) == before


def test_import_above_one_megabyte_is_413_with_or_without_content_length(client, db):
    big = b'{"app": "yt-toolkit", "schema": 1, "settings": {}, "pad": "' + b"x" * 1_048_576 + b'"}'
    before = _rows(db)
    resp = _import(client, big)
    assert resp.status_code == 413
    assert resp.json()["error"] == {"code": "E_SETTINGS_INVALID", "message": INVALID,
                                    "detail": "file larger than 1048576 bytes"}  # fmt: skip

    def chunks():
        yield big[:600_000]
        yield big[600_000:]

    streamed = client.post("/api/settings/import", content=chunks(),
                           headers={**AUTH, "Content-Type": "application/json"})  # fmt: skip
    assert streamed.status_code == 413
    assert _rows(db) == before


def test_exactly_one_megabyte_is_still_read(client):
    doc = b'{"app": "yt-toolkit", "schema": 1, "settings": {}, "pad": "'
    body = doc + b"x" * (settings_api.MAX_SETTINGS_IMPORT_BYTES - len(doc) - 2) + b'"}'
    assert len(body) == settings_api.MAX_SETTINGS_IMPORT_BYTES
    assert _import(client, body).status_code == 200


def test_import_requires_the_token_and_our_origin(client):
    doc = json.dumps({"app": "yt-toolkit", "schema": 1, "settings": {}})
    no_token = client.post("/api/settings/import", content=doc, headers={"Origin": "http://127.0.0.1:8787"})
    foreign = client.post("/api/settings/import", content=doc, headers={**AUTH, "Origin": "https://evil.example"})
    assert no_token.status_code == 403 and foreign.status_code == 403
    assert no_token.json()["error"]["code"] == "E_FORBIDDEN"


def test_import_body_never_reaches_the_log(client, caplog):
    import logging

    with caplog.at_level(logging.DEBUG, logger="yttoolkit"):
        _import(client, b'{"app": "yt-toolkit", "schema": 1, "settings": {"theme": "SECRET-VALUE-123"}}')
    assert "SECRET-VALUE-123" not in caplog.text
```

In `tests/unit/test_settings.py`:

Append at the end of the file:
```python


# ---------- M6 รอบ A: นำเข้าไฟล์สำรองค่าตั้ง (spec 4.2, AC-SET-09 / AC-SET-10) ----------


def _doc(settings: dict, **top) -> dict:
    return {"app": "yt-toolkit", "schema": 1, "exportedAt": "2026-10-14T05:00:00+00:00", "settings": settings, **top}


def _rows(db) -> list[tuple[str, str]]:
    return [(r["key"], r["value_json"]) for r in db.execute("SELECT key, value_json FROM settings ORDER BY key")]


def test_import_round_trips_an_export_on_a_fresh_store(db, store, tmp_path):
    store.patch({"concurrency": 3, "theme": "dark", "filenameStyle": "title-channel", "outputDir": str(tmp_path / "v")})
    exported = store.exportable()
    assert "statsResetAt" not in exported and "cookies" not in exported
    fresh_db = Database(tmp_path / "fresh.db")
    fresh_db.migrate()
    try:
        fresh = SettingsStore(fresh_db, tmp_path / "other")
        saved, warnings = fresh.import_settings(_doc(exported))
        assert warnings == []
        assert {k: v for k, v in saved.items() if k != "statsResetAt"} == exported
        assert fresh.get() == {**exported, "statsResetAt": None}
    finally:
        fresh_db.close()


def test_import_skips_unknown_read_only_and_retired_keys(db, store):
    saved, warnings = store.import_settings(_doc({
        "concurrency": 1, "futureKey": {"x": 1}, "statsResetAt": "2026-01-01T00:00:00+00:00", "cookies": {"a": 1},
    }))  # fmt: skip
    assert warnings == [] and saved["concurrency"] == 1 and saved["statsResetAt"] is None
    assert {key for key, _ in _rows(db)} == {"concurrency"}


@pytest.mark.parametrize(
    "settings",
    [
        {"theme": "dark", "concurrency": 5},
        {"concurrency": 2, "theme": 1},
        {"outputDir": 3, "theme": "dark"},
        {"mp3Kbps": 192.0},
        {"autoSharpFrames": "true"},
        {"sponsorblockDefault": []},
        {"subCustom": {"maxChars": -1}},
    ],
)
def test_import_with_one_bad_value_changes_nothing(db, store, settings):
    store.patch({"concurrency": 3})
    before = _rows(db)
    with pytest.raises(SettingsError) as err:
        store.import_settings(_doc(settings))
    assert err.value.code == "E_SETTINGS_INVALID"
    assert err.value.detail.endswith(": invalid value") and err.value.key in settings
    assert _rows(db) == before


@pytest.mark.parametrize(
    ("doc", "detail"),
    [
        ([1, 2], "file must be a JSON object"),
        ("text", "file must be a JSON object"),
        ({"app": "other", "schema": 1, "settings": {}}, "app invalid"),
        ({"schema": 1, "settings": {}}, "app invalid"),
        ({"app": "yt-toolkit", "schema": 2, "settings": {}}, "schema invalid"),
        ({"app": "yt-toolkit", "schema": "1", "settings": {}}, "schema invalid"),
        ({"app": "yt-toolkit", "schema": True, "settings": {}}, "schema invalid"),
        ({"app": "yt-toolkit", "schema": 1.0, "settings": {}}, "schema invalid"),
        ({"app": "yt-toolkit", "schema": 1, "settings": [1]}, "settings invalid"),
        ({"app": "yt-toolkit", "schema": 1}, "settings invalid"),
    ],
)
def test_import_of_a_file_that_is_not_ours_is_invalid(db, store, doc, detail):
    before = _rows(db)
    with pytest.raises(SettingsError) as err:
        store.import_settings(doc)
    assert (err.value.code, err.value.detail) == ("E_SETTINGS_INVALID", detail)
    assert _rows(db) == before


def test_empty_settings_is_valid_and_changes_nothing(db, store):
    store.patch({"theme": "light"})
    before = _rows(db)
    saved, warnings = store.import_settings(_doc({}))
    assert warnings == [] and saved["theme"] == "light" and _rows(db) == before


# path ของเครื่องอื่น: บน Windows "/Users/..." ไม่ใช่ path เต็ม · บน macOS สร้างโฟลเดอร์ใต้ /Users ไม่ได้ (คำเตือนทั้งคู่)
@pytest.mark.parametrize("folder", ["relative/folder", "", "   ", "/Users/somchai-not-here/Movies", "D:\\a\x00b"])
def test_an_output_dir_that_cannot_be_used_here_keeps_the_old_one(store, tmp_path, folder):
    old = store.get()["outputDir"]
    saved, warnings = store.import_settings(_doc({"outputDir": folder, "theme": "dark"}))
    assert warnings == ["outputDir"]
    assert saved["outputDir"] == old and saved["theme"] == "dark"


def test_an_unwritable_output_dir_keeps_the_old_one(store, tmp_path):
    a_file = tmp_path / "file.txt"
    a_file.write_text("x")
    old = store.get()["outputDir"]
    saved, warnings = store.import_settings(_doc({"outputDir": str(a_file), "concurrency": 1}))
    assert (warnings, saved["outputDir"], saved["concurrency"]) == (["outputDir"], old, 1)


def test_the_output_dir_hook_fires_once_with_the_new_folder(store, tmp_path):
    calls: list[Path] = []
    store.on_output_dir = calls.append
    store.import_settings(_doc({"outputDir": str(tmp_path / "new"), "theme": "dark"}))
    assert calls == [tmp_path / "new"]
    store.import_settings(_doc({"outputDir": "relative", "theme": "light"}))  # คำเตือน = ไม่เปลี่ยนโฟลเดอร์
    store.import_settings(_doc({"theme": "dark"}))
    assert calls == [tmp_path / "new"]


def test_all_imported_keys_are_written_in_one_transaction(db, store, monkeypatch):
    from yttoolkit.core import db as db_module

    before = _rows(db)
    real = db_module.Transaction.execute
    seen = {"upserts": 0}

    def failing(self, sql, params=()):
        if sql.startswith("INSERT INTO settings"):
            seen["upserts"] += 1
            if seen["upserts"] == 2:
                raise RuntimeError("disk gone")
        return real(self, sql, params)

    monkeypatch.setattr(db_module.Transaction, "execute", failing)
    with pytest.raises(RuntimeError):
        store.import_settings(_doc({"theme": "dark", "concurrency": 1}))
    monkeypatch.undo()
    assert _rows(db) == before


def test_import_deletes_retired_rows_like_patch(db, store):
    db.execute("INSERT INTO settings (key, value_json) VALUES ('cookies', '{\"state\": \"none\"}')")
    store.import_settings(_doc({"theme": "dark"}))
    assert {key for key, _ in _rows(db)} == {"theme"}
```

- [ ] **Step 2: Run them, expect FAIL**

Run: `cd "$WORKTREE" && uv run pytest tests/unit/test_settings.py tests/api/test_settings_api.py tests/unit/test_yterrors.py -q -W error -p no:cacheprovider`
Expected: `1 error` (collection error in `api/test_settings_api.py`) — the run stops at collection because `tests/api/test_settings_api.py` reads `MESSAGES["E_SETTINGS_INVALID"]`, which does not exist yet; the new `test_settings.py` tests fail on `import_settings` / `exportable`.

- [ ] **Step 3: Implement**

Replace the whole of `src/yttoolkit/api/settings.py` with:
```python
"""API ตั้งค่า (สัญญา C5): ดู แก้ และเปิดโฟลเดอร์ปลายทาง · M6 รอบ A: สำรอง (export) และนำเข้า (import) ค่าตั้ง

route ส่วนใหญ่เป็น `def` ธรรมดา (แตะดิสก์และฐานข้อมูล) FastAPI จึงส่งไปรันใน threadpool
POST /settings/import เป็น async เพื่ออ่าน body ดิบเองทีละชิ้น (หยุดที่ 1 MB) แล้วส่งงานเขียนไปรันใน threadpool
body ของการนำเข้าไม่ถูก log และไม่ถูกยกกลับใน error (detail บอกชื่อ key อย่างมาก C4)
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, NoReturn

from fastapi import APIRouter, Body, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import JSONResponse, Response

from ..core.settings import EXPORT_APP, EXPORT_SCHEMA, SettingsError, ensure_writable
from ..core.yterrors import MESSAGES
from .errors import BAD_REQUEST_MESSAGE, error_response
from .videos import attachment_header

if TYPE_CHECKING:
    from ..app import AppContext

OUTPUT_NOT_WRITABLE_MESSAGE = "บันทึกลงโฟลเดอร์นี้ไม่ได้ ลองเปลี่ยนโฟลเดอร์ในหน้าตั้งค่า"
OUTPUT_DIR_BAD_MESSAGE = "ใส่ที่อยู่โฟลเดอร์แบบเต็ม เช่น C:\\Users\\ชื่อ\\Videos"
_MESSAGES = {
    "E_BAD_REQUEST": BAD_REQUEST_MESSAGE,
    "E_OUTPUT_NOT_WRITABLE": MESSAGES.get("E_OUTPUT_NOT_WRITABLE", OUTPUT_NOT_WRITABLE_MESSAGE),
}
# M6 รอบ A: ไฟล์ค่าตั้งใหญ่สุดที่รับ (เท่ากับ MAX_SETTINGS_FILE_BYTES ของเว็บ)
MAX_SETTINGS_IMPORT_BYTES = 1_048_576
EXPORT_FILE_PREFIX = "yt-toolkit-settings-"


def _settings_error(error: SettingsError) -> JSONResponse:
    if error.code == "E_SETTINGS_INVALID":
        return _invalid(error.detail)
    if error.code == "E_BAD_REQUEST" and error.key == "outputDir":
        return error_response(422, error.code, OUTPUT_DIR_BAD_MESSAGE, error.detail)
    return error_response(422, error.code, _MESSAGES.get(error.code, BAD_REQUEST_MESSAGE), error.detail)


def _invalid(detail: str, status: int = 422) -> JSONResponse:
    return error_response(status, "E_SETTINGS_INVALID", MESSAGES["E_SETTINGS_INVALID"], detail)


def _too_large() -> JSONResponse:
    return _invalid(f"file larger than {MAX_SETTINGS_IMPORT_BYTES} bytes", 413)


def _reject_constant(name: str) -> NoReturn:
    """NaN / Infinity / -Infinity ไม่ใช่ JSON จริง (json.loads ของ Python รับเอง ต้องปฏิเสธเอง)"""
    raise ValueError(f"{name} is not JSON")


def export_document(settings: dict[str, Any], now: datetime) -> dict[str, Any]:
    """เนื้อไฟล์สำรองค่าตั้ง: app + schema พอสำหรับตรวจตอนนำเข้า (ไม่มีอะไรเฉพาะยูทูป C12)"""
    return {
        "app": EXPORT_APP,
        "schema": EXPORT_SCHEMA,
        "exportedAt": now.astimezone(UTC).isoformat(timespec="seconds"),
        "settings": settings,
    }


def export_file_name(now: datetime) -> str:
    """yt-toolkit-settings-YYYY-MM-DD.json ตามวันที่ของเครื่อง"""
    return f"{EXPORT_FILE_PREFIX}{now.astimezone():%Y-%m-%d}.json"


def build_settings_router(ctx: AppContext) -> APIRouter:
    router = APIRouter()
    store = ctx.settings
    assert store is not None  # create_app เรียกต่อเมื่อมี ctx.settings เท่านั้น

    @router.get("/settings")
    def get_settings() -> dict:
        return store.get()

    @router.patch("/settings", response_model=None)
    def patch_settings(body: Any = Body(...)) -> dict | JSONResponse:
        try:
            return store.patch(body)
        except SettingsError as error:
            return _settings_error(error)

    @router.post("/settings/open-output", response_model=None)
    def open_output() -> dict | JSONResponse:
        folder: Path = store.output_dir()
        try:
            ensure_writable(folder)
        except SettingsError as error:
            return _settings_error(error)
        opener = ctx.open_folder or ctx.plat.open_folder
        opener(folder)
        return {"ok": True}

    @router.get("/settings/export")
    def export_settings() -> Response:
        """ไฟล์สำรองค่าตั้ง (FR-SET-7): GET ไม่ต้องใช้ token เหมือน GET /settings ที่ให้ค่าเดียวกันอยู่แล้ว"""
        now = datetime.now(UTC)
        text = json.dumps(export_document(store.exportable(), now), ensure_ascii=False, indent=2, allow_nan=False)
        name = export_file_name(now)
        return Response(
            (text + "\n").encode("utf-8"),
            media_type="application/json",
            headers={"Content-Disposition": attachment_header(name, name), "Cache-Control": "no-store"},
        )

    @router.post("/settings/import", response_model=None)
    async def import_settings(request: Request) -> dict | JSONResponse:
        """นำเข้าไฟล์สำรอง: ไม่เกิน 1 MB (413) · UTF-8 มี BOM ได้ · JSON จริง (ไม่มี NaN) · ตรวจทั้งไฟล์ก่อนเขียน"""
        length = request.headers.get("content-length", "")
        if length.isdigit() and int(length) > MAX_SETTINGS_IMPORT_BYTES:
            return _too_large()
        data = bytearray()
        async for chunk in request.stream():
            data += chunk
            if len(data) > MAX_SETTINGS_IMPORT_BYTES:
                return _too_large()
        try:
            text = bytes(data).decode("utf-8-sig")  # Notepad อาจใส่ BOM
        except UnicodeDecodeError:
            return _invalid("not UTF-8")
        try:
            doc = json.loads(text, parse_constant=_reject_constant)
        except (ValueError, RecursionError):
            return _invalid("not JSON")
        try:
            settings, warnings = await run_in_threadpool(store.import_settings, doc)
        except SettingsError as error:
            return _settings_error(error)
        return {"settings": settings, "warnings": warnings}

    return router
```

In `src/yttoolkit/core/settings.py`:

Replace (1):
```python
core ไม่รู้จัก HTTP: ผิดเงื่อนไขโยน SettingsError พร้อมรหัสให้ชั้น api แปลงเป็น 422
```
with:
```python
core ไม่รู้จัก HTTP: ผิดเงื่อนไขโยน SettingsError พร้อมรหัสให้ชั้น api แปลงเป็น 422
M6 รอบ A: นำเข้าไฟล์ค่าตั้ง (import_settings) ทั้งหมดหรือไม่เลยเหมือนกัน แต่ใจกว้างกว่า PATCH:
key ที่ไม่รู้จัก/อ่านอย่างเดียว/เลิกใช้ถูกข้าม และ outputDir ที่ใช้บนเครื่องนี้ไม่ได้ = คงค่าเดิม + คำเตือน
```

Replace (2):
```python


class SettingsError(Exception):
    """code: E_BAD_REQUEST | E_OUTPUT_NOT_WRITABLE"""
```
with:
```python
# M6 รอบ A: ไฟล์สำรองค่าตั้ง {app, schema, exportedAt, settings} (ไม่มีอะไรเฉพาะยูทูป C12)
EXPORT_APP = "yt-toolkit"
EXPORT_SCHEMA = 1


class SettingsError(Exception):
    """code: E_BAD_REQUEST | E_OUTPUT_NOT_WRITABLE | E_SETTINGS_INVALID (นำเข้าไฟล์ค่าตั้ง M6 รอบ A)

    detail เป็นภาษาอังกฤษคงที่ บอกชื่อ key ได้ ไม่ยกค่าจากผู้ใช้/ไฟล์ (C4)"""
```

Replace (3):
```python
            ensure_writable(Path(clean["outputDir"]))
```
with:
```python
            ensure_writable(Path(clean["outputDir"]))
        return self._save(clean)

    def _save(self, clean: Mapping[str, Any]) -> dict:
        """เขียนทุก key ที่ตรวจแล้วในธุรกรรมเดียว (ลบ key ที่เลิกใช้ไปด้วย) แล้วคืนค่าตั้งทั้งหมด
        outputDir เปลี่ยน = เรียก on_output_dir นอกล็อก (ต่อสายตัวปิด path ใน log)"""
```

Replace (4):
```python

    def output_dir(self) -> Path:
```
with:
```python

    def exportable(self) -> dict:
        """ค่าตั้งที่ใส่ในไฟล์สำรอง: ทุก key ยกเว้นค่าอ่านอย่างเดียว (statsResetAt) · cookies ไม่ใช่ key อยู่แล้ว"""
        return {key: value for key, value in self.get().items() if key not in READ_ONLY}

    def import_settings(self, doc: object) -> tuple[dict, list[str]]:
        """นำเข้าไฟล์สำรองค่าตั้ง (M6 รอบ A spec 4.2) คืน (ค่าตั้งทั้งหมดหลังนำเข้า, คำเตือน)

        ไฟล์ผิดรูป (ไม่ใช่ object, app/schema/settings ผิด) หรือค่าของ key ที่รู้จักผิดชนิด/นอกช่วง
        = SettingsError E_SETTINGS_INVALID และไม่เปลี่ยนอะไรเลย · key ที่ไม่รู้จัก statsResetAt และ cookies ถูกข้าม
        outputDir ที่ใช้บนเครื่องนี้ไม่ได้ (รูปแบบผิดหรือเขียนไม่ได้) = คงค่าเดิม และคำเตือน "outputDir"
        key ที่ไม่มีในไฟล์คงค่าเดิม · ทุก key เขียนในธุรกรรมเดียว
        """
        if not isinstance(doc, Mapping):
            raise SettingsError("E_SETTINGS_INVALID", "file must be a JSON object")
        if doc.get("app") != EXPORT_APP:
            raise SettingsError("E_SETTINGS_INVALID", "app invalid")
        schema = doc.get("schema")
        if type(schema) is not int or schema != EXPORT_SCHEMA:
            raise SettingsError("E_SETTINGS_INVALID", "schema invalid")
        values = doc.get("settings")
        if not isinstance(values, Mapping):
            raise SettingsError("E_SETTINGS_INVALID", "settings invalid")
        clean: dict[str, Any] = {}
        output_dir: str | None = None
        for key, value in values.items():
            if key in READ_ONLY or key in RETIRED_KEYS or key not in _VALIDATORS:
                continue  # key ที่ไม่รู้จัก (ไฟล์จากรุ่นใหม่กว่า) / อ่านอย่างเดียว / เลิกใช้ = ข้าม
            if key == "outputDir":
                if not isinstance(value, str):
                    raise SettingsError("E_SETTINGS_INVALID", "outputDir: invalid value", key=key)
                output_dir = value  # ตรวจหลังทุก key ผ่าน (ด้านล่าง)
                continue
            try:
                clean[key] = _VALIDATORS[key](value)
            except SettingsError as error:
                raise SettingsError("E_SETTINGS_INVALID", f"{key}: invalid value", key=key) from error
        warnings: list[str] = []
        if output_dir is not None:
            # นอก lock เหมือน patch · ใช้บนเครื่องนี้ไม่ได้ (path ของเครื่องอื่น ไดรฟ์ที่ไม่มี เขียนไม่ได้) = คงโฟลเดอร์เดิม
            try:
                folder = _validate_output_dir(output_dir)
                ensure_writable(Path(folder))
            except SettingsError:
                warnings.append("outputDir")
            else:
                clean["outputDir"] = folder
        return self._save(clean), warnings

    def output_dir(self) -> Path:
```

In `src/yttoolkit/core/yterrors.py`:

Replace (1):
```python
    "E_COOKIES_INVALID": "ไฟล์นี้ใช้ไม่ได้ ตรวจว่าเข้าสู่ระบบยูทูปแล้วก่อนส่งออก แล้วส่งออก cookies.txt ใหม่",
```
with:
```python
    "E_COOKIES_INVALID": "ไฟล์นี้ใช้ไม่ได้ ตรวจว่าเข้าสู่ระบบยูทูปแล้วก่อนส่งออก แล้วส่งออก cookies.txt ใหม่",
    # M6 รอบ A: ไฟล์ที่นำเข้าในหน้าตั้งค่า > ข้อมูลในเครื่อง ไม่ใช่ไฟล์จากปุ่ม "สำรองค่าตั้ง" (ไม่เปลี่ยนค่าตั้งเลย)
    "E_SETTINGS_INVALID": 'ไฟล์นี้ไม่ใช่ไฟล์ค่าตั้งของ YT Toolkit หรือไฟล์เสียหาย ลองเลือกไฟล์ที่ได้จากปุ่ม "สำรองค่าตั้ง"',
```

Notes for the implementer:
- `PATCH /settings` stays strict (unknown key, `statsResetAt` → 422 `E_BAD_REQUEST`); only the import is tolerant. Both write through `_save` (P18).
- The import body is never logged; every `detail` is a fixed English string that names a key at most (C4, P20). `tests/unit/test_yterrors.py::test_messages_match_prd_table` checks the new message against the PRD §7 row added in the spec commit.

- [ ] **Step 4: Run the tests, expect PASS**

Run: the Step 2 command. Expected: `230 passed`. Then the full suite (all pass).

- [ ] **Step 5: Commit**
```bash
cd "$WORKTREE" && git add src/yttoolkit/core/settings.py src/yttoolkit/core/yterrors.py src/yttoolkit/api/settings.py tests/unit/test_settings.py tests/api/test_settings_api.py && git commit -F- <<'EOF'
feat(settings): export a dated settings file and import it all-or-nothing (E_SETTINGS_INVALID, 1 MB cap)

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
EOF
```


### Task 7: Clearing temporary data — `StorageService`, the active holds, `/api/storage` (spec 3; AC-SET-07, AC-SET-08)

**Files:**
- Create: `src/yttoolkit/core/storage.py`, `src/yttoolkit/api/storage.py`
- Modify: `src/yttoolkit/core/db.py`, `src/yttoolkit/core/queue.py`, `src/yttoolkit/core/capture.py`, `src/yttoolkit/app.py`, `src/yttoolkit/lifecycle.py`
- Create: `tests/unit/test_storage.py`, `tests/unit/test_storage_readers.py`, `tests/api/test_storage_api.py`
- Modify: `tests/unit/test_queue.py`, `tests/unit/test_capture.py`, `tests/unit/test_db.py`

**Interfaces:**
- Consumes: T2's `queue.py` (the `_JobContext` with `filename_style`), `db._remove_cache_folder`, `CaptureService._busy` / `_guard` / `_capture_locked`, `Paths.cache` / `Paths.work`, `AppContext.cache_root` / `queue` / `captures`.
- Produces: K7 exactly. T13 calls `GET /api/storage` and `POST /api/storage/clear`; T10 calls them through T4's client.

- [ ] **Step 1: Write the failing tests**

Create `tests/api/test_storage_api.py`:
```python
"""API ข้อมูลชั่วคราว (M6 รอบ A spec 3.4, AC-SET-07 / AC-SET-08): GET /api/storage · POST /api/storage/clear"""

from __future__ import annotations

import random
import threading
from pathlib import Path

import pytest

from yttoolkit.core.db import Database
from yttoolkit.core.events import EventBus
from yttoolkit.core.extractor import FakeExtractor
from yttoolkit.core.jobs import JobResult, JobStore, NewJob, OutputFile
from yttoolkit.core.queue import QueueRunner
from yttoolkit.core.settings import SettingsStore
from yttoolkit.core.videos import VideoService

# ค่าเดียวกับ tests/api/conftest.py (import conftest ตรง ๆ ไม่ได้)
BASE = "http://127.0.0.1:8787"
AUTH = {"X-Toolkit-Token": "test-token", "Origin": BASE}
FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
BBB = "aqz-KE-bpKQ"
ZOO = "jNQXAC9IVRw"
MB = 1_000_000


def sized(path: Path, size: int) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as f:
        f.truncate(size)
    return path


@pytest.fixture
def client(make_client, paths):
    return make_client(cache_root=paths.cache)


def test_no_storage_router_without_a_cache_root(make_client):
    assert make_client().get("/api/storage").status_code == 404


def test_get_storage_shape_and_no_store(client, paths):
    sized(paths.cache / BBB / "storyboard" / "f.jpg", 2 * MB)
    sized(paths.work / "ffmpeg-download.zip", MB)
    resp = client.get("/api/storage")
    assert resp.status_code == 200
    assert resp.headers["cache-control"] == "no-store"
    assert resp.json() == {"cacheBytes": 2 * MB, "workBytes": MB, "reclaimableBytes": 2 * MB}


def test_get_storage_needs_no_token(client):
    assert client.get("/api/storage", headers={"Origin": BASE}).status_code == 200


def test_clear_frees_and_reports_the_real_bytes(client, paths):
    sized(paths.cache / BBB / "storyboard" / "f.jpg", 2 * MB)
    sized(paths.cache / ZOO / "pinned.json", 100)
    resp = client.post("/api/storage/clear", headers=AUTH)
    assert resp.status_code == 200 and resp.headers["cache-control"] == "no-store"
    assert resp.json() == {"freedBytes": 2 * MB + 100}
    assert list(paths.cache.iterdir()) == []
    assert client.get("/api/storage").json()["reclaimableBytes"] == 0


def test_clear_ignores_a_body(client, paths):
    assert client.post("/api/storage/clear", json={"everything": True}, headers=AUTH).json() == {"freedBytes": 0}


def test_clear_needs_the_token_and_our_origin(client, paths):
    sized(paths.cache / BBB / "storyboard" / "f.jpg", MB)
    no_token = client.post("/api/storage/clear", headers={"Origin": BASE})
    foreign = client.post("/api/storage/clear", headers={**AUTH, "Origin": "https://evil.example"})
    assert no_token.status_code == 403 and foreign.status_code == 403
    assert no_token.json()["error"]["code"] == "E_FORBIDDEN"
    assert (paths.cache / BBB / "storyboard" / "f.jpg").is_file()


def test_ac_set_08_a_running_job_survives_a_clear_and_finishes(make_client, paths, tmp_path):
    db = Database(paths.db)
    db.migrate()
    started, release = threading.Event(), threading.Event()

    def handler(job, ctx):
        (ctx.workdir / "media.mp4.part").write_bytes(b"x" * 1000)
        sized(paths.cache / job.video_id / "storyboard" / "f.jpg", MB)
        started.set()
        assert release.wait(10)
        assert (ctx.workdir / "media.mp4.part").is_file()  # ยังอยู่หลังล้าง
        assert (paths.cache / job.video_id / "storyboard" / "f.jpg").is_file()
        return JobResult(outputs=(OutputFile(str(ctx.output_root), f"x [{job.video_id}]/x.mp4", 1, "video"),))

    settings = SettingsStore(db, tmp_path / "out")
    runner = QueueRunner(JobStore(db), EventBus(), {"video": handler}, settings=settings, work_root=paths.work,
                         rng=random.Random(1), redact=lambda text: text)  # fmt: skip
    try:
        client = make_client(cache_root=paths.cache, queue=runner, settings=settings, db=db)
        sized(paths.cache / ZOO / "storyboard" / "f.jpg", 3 * MB)
        (job,) = runner.enqueue([NewJob(BBB, "video", {})])
        runner.tick()
        assert started.wait(5)
        usage = client.get("/api/storage").json()
        assert usage["reclaimableBytes"] == 3 * MB  # ของงานที่กำลังทำไม่นับ
        assert client.post("/api/storage/clear", headers=AUTH).json() == {"freedBytes": 3 * MB}
        release.set()
        for _ in range(200):
            if runner.store.get(job.id).status == "done":
                break
            threading.Event().wait(0.02)
        assert runner.store.get(job.id).status == "done"
    finally:
        release.set()
        runner.shutdown(timeout=1)
        db.close()



def test_a_stale_cache_image_url_is_404_after_a_clear(make_client, paths):
    # spec 3.3 แถว api/videos._cache_target: ลิงก์ภาพเก่าที่หน้าเว็บยังถืออยู่ = 404 ไม่ใช่ 500
    db = Database(paths.db)
    db.migrate()
    try:
        fake = FakeExtractor(FIXTURES)
        client = make_client(db=db, videos=VideoService(db, fake), extractor=fake, cache_root=paths.cache)
        assert client.get(f"/api/videos/{BBB}/storyboard").status_code == 200
        assert client.get(f"/api/cache/{BBB}/storyboard/f_0000.jpg").status_code == 200
        assert client.post("/api/storage/clear", headers=AUTH).json()["freedBytes"] > 0
        resp = client.get(f"/api/cache/{BBB}/storyboard/f_0000.jpg")
        assert resp.status_code == 404 and resp.json()["error"]["code"] == "E_NOT_FOUND"
        assert client.get(f"/api/videos/{BBB}/storyboard").status_code == 200  # เปิดคลิปเก่าอีกครั้ง = ดึงภาพใหม่
    finally:
        db.close()
```

In `tests/unit/test_capture.py`:

Append at the end of the file:
```python



# ---------- M6 รอบ A: hold_active (ปุ่มล้างข้อมูลชั่วคราว spec 3.2) ----------


def test_hold_active_reports_the_running_capture_and_its_work_dir(env: Env) -> None:
    with env.service.hold_active() as idle:
        assert idle is None
    env.fetcher.gate = threading.Event()
    worker = threading.Thread(target=lambda: env.service.capture(BBB, 1_000))
    worker.start()
    try:
        assert env.fetcher.started.wait(5)
        with env.service.hold_active() as current:
            assert current is not None and current[0] == BBB
            assert current[1].startswith("capture-") and (env.work / current[1]).is_dir()
    finally:
        env.fetcher.gate.set()
        worker.join(10)
    with env.service.hold_active() as after:
        assert after is None
    assert list(env.work.iterdir()) == []


def test_a_capture_waits_while_the_active_set_is_held(env: Env) -> None:
    done = threading.Event()
    with env.service.hold_active():
        worker = threading.Thread(target=lambda: (env.service.capture(BBB, 1_000), done.set()))
        worker.start()
        assert not done.wait(0.2)  # รอ _guard
        assert not env.work.exists() or list(env.work.iterdir()) == []
    worker.join(10)
    assert done.is_set()
```

In `tests/unit/test_db.py`:

Append at the end of the file:
```python



# ---------- M6 รอบ A: cache_folder (ตัวตรวจเดียวกับการล้าง cache เก่า) ----------


def test_cache_folder_accepts_only_video_id_folders_inside_the_root(tmp_path: Path):
    root = (tmp_path / "cache").resolve()
    root.mkdir()
    assert db_module.cache_folder(root, "aqz-KE-bpKQ") == root / "aqz-KE-bpKQ"
    for bad in ("..", "../x", "a/b", "a\\b", "short", "toolongvideoid1", "", ".clear-" + "a" * 32, "storyboard"):
        assert db_module.cache_folder(root, bad) is None, bad
```

In `tests/unit/test_queue.py`:

Append at the end of the file:
```python



# ---------- M6 รอบ A: hold_active (ปุ่มล้างข้อมูลชั่วคราว spec 3.2) ----------


def test_hold_active_lists_running_jobs_and_their_clips(runner_factory):
    r, spawn, h = runner_factory(concurrency=2)
    first, second, third = r.enqueue([NewJob("vid00000001", "frames_zip", {"source": "fast"}),
                                      NewJob("vid00000002", "frames_zip", {"source": "fast"}),
                                      NewJob("vid00000003", "frames_zip", {"source": "fast"})])  # fmt: skip
    with r.hold_active() as idle:
        assert idle.job_ids == frozenset() and idle.video_ids == frozenset()
    r.tick()
    with r.hold_active() as active:
        assert active.job_ids == {first.id, second.id}
        assert active.video_ids == {"vid00000001", "vid00000002"}
    spawn.run_all()
    with r.hold_active() as after:
        assert after.job_ids == frozenset()
    assert r.store.get(third.id).status == "queued"


def test_no_job_starts_while_the_active_set_is_held(runner_factory):
    r, spawn, h = runner_factory(concurrency=2)
    r.enqueue(jobs_of("frames_zip", 1, {"source": "fast"}))
    started: list[list[str]] = []
    with r.hold_active():
        ticker = threading.Thread(target=lambda: started.append(r.tick()))
        ticker.start()
        ticker.join(0.2)
        assert ticker.is_alive()  # tick รอล็อกของคิว
        assert r.store.running() == []
    ticker.join(5)
    assert len(started[0]) == 1
```

Create `tests/unit/test_storage.py`:
```python
"""ข้อมูลชั่วคราว (M6 รอบ A spec 3, AC-SET-07 / AC-SET-08): core/storage.StorageService และ sweep_clear_leftovers

ไฟล์ใหญ่สร้างด้วย truncate (sparse: st_size ตามที่ตั้ง ไม่เขียนข้อมูลจริง) เทสจึงเร็ว · ไม่แตะเครือข่าย
"""

from __future__ import annotations

import logging
import os
import shutil
import threading
from contextlib import contextmanager
from pathlib import Path

import pytest

from yttoolkit import lifecycle
from yttoolkit.config import Paths
from yttoolkit.core import storage as storage_module
from yttoolkit.core.queue import ActiveJobs
from yttoolkit.core.storage import STAGING_GRACE_S, StorageService, StorageUsage, sweep_clear_leftovers, tree_bytes

BBB = "aqz-KE-bpKQ"
ZOO = "jNQXAC9IVRw"
THAI = "88o5Sk8_m1Y"
JOB = "0190a1b2-c3d4-7e5f-8a6b-7c8d9e0f1a2b"
OTHER_JOB = "0190a1b2-c3d4-7e5f-8a6b-000000000002"
CAPTURE = "capture-" + "a" * 32
NOW = 2_000_000_000.0
MB = 1_000_000


def sized(path: Path, size: int) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as f:
        f.truncate(size)
    return path


class FakeQueue:
    def __init__(self) -> None:
        self.jobs: dict[str, str] = {}  # job id -> video id
        self.held = 0

    @contextmanager
    def hold_active(self):
        self.held += 1
        yield ActiveJobs(frozenset(self.jobs), frozenset(self.jobs.values()))


class FakeCaptures:
    def __init__(self) -> None:
        self.current: tuple[str, str] | None = None

    @contextmanager
    def hold_active(self):
        yield self.current


@pytest.fixture
def env(tmp_path: Path):
    paths = Paths(data_root=tmp_path)
    paths.ensure()
    queue, captures = FakeQueue(), FakeCaptures()
    service = StorageService(paths.cache, paths.work, queue=queue, captures=captures, now=lambda: NOW)
    return paths, queue, captures, service


def _keep_outside(paths: Paths) -> list[Path]:
    """ของที่ต้องไม่ถูกแตะเลย: ไฟล์ผลลัพธ์ app.db เซสชันผู้ชม และ log"""
    return [
        sized(paths.data_root / "output" / f"คลิป [{BBB}]" / "คลิป.mp4", 3 * MB),
        sized(paths.db, 10_000),
        sized(paths.data / "visitor-session.txt", 100),
        sized(paths.data / "visitor-session.json", 100),
        sized(paths.logs / "app.log", 1_000),
    ]


# ---------- AC-SET-07 ----------


def test_ac_set_07_sizes_within_one_percent_and_clear_empties_the_cache(env):
    paths, _, _, service = env
    keep = _keep_outside(paths)
    written = 0
    for video_id, sizes in ((BBB, (20 * MB, 1 * MB)), (ZOO, (15 * MB,)), (THAI, (10 * MB, 4 * MB))):
        for i, size in enumerate(sizes):
            written += sized(paths.cache / video_id / "storyboard" / f"f_{i:04d}.jpg", size).stat().st_size
    usage = service.usage()
    assert abs(usage.cache_bytes - written) <= written * 0.01
    assert usage.reclaimable_bytes == usage.cache_bytes == 50 * MB and usage.work_bytes == 0
    freed = service.clear()
    assert freed == usage.reclaimable_bytes
    assert list(paths.cache.iterdir()) == []
    assert all(p.is_file() for p in keep)
    assert service.usage() == StorageUsage(0, 0, 0)


def test_usage_api_shape():
    assert StorageUsage(1, 2, 3).to_api() == {"cacheBytes": 1, "workBytes": 2, "reclaimableBytes": 3}


# ---------- AC-SET-08: งานที่กำลังทำ และการถ่ายภาพที่กำลังทำ ----------


def test_ac_set_08_an_active_job_keeps_its_work_dir_and_clip_cache(env):
    paths, queue, _, service = env
    queue.jobs = {JOB: BBB}
    sized(paths.work / JOB / "media.mp4.part", 7 * MB)
    sized(paths.work / OTHER_JOB / "media.mp4", 2 * MB)  # งานที่จบไปแล้ว (เหลือค้าง)
    sized(paths.cache / BBB / "storyboard" / "f_0000.jpg", 5 * MB)
    sized(paths.cache / ZOO / "storyboard" / "f_0000.jpg", 3 * MB)
    usage = service.usage()
    assert (usage.cache_bytes, usage.work_bytes, usage.reclaimable_bytes) == (8 * MB, 9 * MB, 5 * MB)
    assert service.clear() == 5 * MB
    assert (paths.work / JOB / "media.mp4.part").is_file()
    assert (paths.cache / BBB / "storyboard" / "f_0000.jpg").is_file()
    assert not (paths.work / OTHER_JOB).exists() and not (paths.cache / ZOO).exists()
    assert queue.held == 2


def test_the_running_capture_keeps_its_clip_cache_and_work_dir(env):
    paths, _, captures, service = env
    captures.current = (ZOO, CAPTURE)
    sized(paths.work / CAPTURE / "piece.mp4", MB)
    sized(paths.work / ("capture-" + "b" * 32) / "piece.mp4", MB)
    sized(paths.cache / ZOO / "captures" / "c1.jpg", MB)
    service.clear()
    assert (paths.work / CAPTURE / "piece.mp4").is_file() and (paths.cache / ZOO / "captures" / "c1.jpg").is_file()
    assert not (paths.work / ("capture-" + "b" * 32)).exists()


def test_without_queue_or_captures_everything_known_is_clearable(tmp_path):
    paths = Paths(data_root=tmp_path)
    paths.ensure()
    sized(paths.cache / BBB / "pinned.json", 10)
    sized(paths.work / JOB / "x", 10)
    service = StorageService(paths.cache, paths.work, queue=None, captures=None)
    assert service.usage().reclaimable_bytes == 20 and service.clear() == 20


# ---------- ของกำลังเตรียม ของที่ไม่รู้จัก ลิงก์ ----------


def test_a_young_staging_folder_keeps_the_clip_and_an_old_one_does_not(env):
    paths, _, _, service = env
    young = paths.cache / BBB / "storyboard.tmp-0123"
    sized(young / "f_0000.jpg", MB)
    os.utime(young, (NOW - 10, NOW - 10))
    old = paths.cache / ZOO / ("sharp.tmp-" + JOB)
    sized(old / "f_0000.jpg", MB)
    os.utime(old, (NOW - STAGING_GRACE_S - 1, NOW - STAGING_GRACE_S - 1))
    assert service.usage().reclaimable_bytes == MB
    service.clear()
    assert young.is_dir() and not (paths.cache / ZOO).exists()


def test_unknown_entries_are_counted_but_never_cleared(env):
    paths, _, _, service = env
    keep = [
        sized(paths.cache / "notes.txt", 100),
        sized(paths.cache / "storyboard" / "x.jpg", 200),  # ไม่ใช่รหัสคลิป
        sized(paths.cache / "toolongvideoid1" / "x.jpg", 300),
        sized(paths.work / "ffmpeg-download.zip", 400),  # tools.py โหลด ffmpeg ลง work/
        sized(paths.work / "random-dir" / "x", 500),
        sized(paths.work / ".clear-short" / "x", 600),  # ชื่อไม่ตรงรูปแบบของเรา
    ]
    usage = service.usage()
    assert (usage.cache_bytes, usage.work_bytes, usage.reclaimable_bytes) == (600, 1500, 0)
    assert service.clear() == 0
    assert all(p.is_file() for p in keep)


def _link_dir(link: Path, target: Path) -> None:
    try:
        link.symlink_to(target, target_is_directory=True)
    except OSError:
        try:
            import _winapi  # Windows: junction ไม่ต้องใช้สิทธิ์ผู้ดูแล

            _winapi.CreateJunction(str(target), str(link))
        except (ImportError, OSError, AttributeError):
            pytest.skip("this machine cannot create a directory link")


def test_a_linked_folder_is_never_followed_or_cleared(env, tmp_path):
    paths, _, _, service = env
    elsewhere = tmp_path / "elsewhere"
    secret = sized(elsewhere / "big.bin", 9 * MB)
    _link_dir(paths.cache / BBB, elsewhere)
    nested = sized(paths.cache / ZOO / "storyboard" / "f.jpg", MB)
    _link_dir(paths.cache / ZOO / "linked", elsewhere)
    usage = service.usage()
    assert usage.cache_bytes == MB and usage.reclaimable_bytes == MB
    service.clear()
    assert secret.is_file() and not nested.exists()
    assert tree_bytes(elsewhere) == 9 * MB


def test_missing_roots_count_as_zero(tmp_path):
    service = StorageService(tmp_path / "no-cache", tmp_path / "no-work", queue=FakeQueue(), captures=FakeCaptures())
    assert service.usage() == StorageUsage(0, 0, 0) and service.clear() == 0


# ---------- Windows: ไฟล์เปิดค้าง ----------


def test_a_folder_that_cannot_be_renamed_stays_and_is_not_counted(env, monkeypatch):
    paths, _, _, service = env
    sized(paths.cache / BBB / "storyboard" / "f.jpg", 2 * MB)
    sized(paths.cache / ZOO / "storyboard" / "f.jpg", 3 * MB)
    real = os.rename

    def locked(src, dst):
        if Path(src).name == BBB:
            raise PermissionError(13, "The process cannot access the file")
        return real(src, dst)

    monkeypatch.setattr(storage_module.os, "rename", locked)
    assert service.clear() == 3 * MB
    assert (paths.cache / BBB / "storyboard" / "f.jpg").is_file()
    assert [p.name for p in paths.cache.iterdir()] == [BBB]  # ไม่มี .clear-* เหลือ


def test_a_file_that_cannot_be_deleted_is_left_in_trash_and_not_counted(env, monkeypatch):
    paths, _, _, service = env
    sized(paths.cache / BBB / "storyboard" / "a.jpg", 2 * MB)
    sized(paths.cache / BBB / "storyboard" / "b.jpg", 3 * MB)
    real = shutil.rmtree

    def partial(path, ignore_errors=False, **kwargs):
        for file in Path(path).rglob("a.jpg"):
            file.unlink()
        return None  # b.jpg "เปิดค้าง" ลบไม่ได้

    monkeypatch.setattr(storage_module.shutil, "rmtree", partial)
    assert service.clear() == 2 * MB
    monkeypatch.setattr(storage_module.shutil, "rmtree", real)
    (trash,) = [p for p in paths.cache.iterdir()]
    assert trash.name.startswith(".clear-")
    assert service.usage().reclaimable_bytes == 3 * MB  # รอบหน้าล้างต่อได้
    assert service.clear() == 3 * MB and list(paths.cache.iterdir()) == []


def test_a_second_clear_waits_for_the_first(env, monkeypatch):
    paths, _, _, service = env
    sized(paths.cache / BBB / "storyboard" / "f.jpg", MB)
    started, release = threading.Event(), threading.Event()
    real = shutil.rmtree

    def slow(path, *args, **kwargs):
        started.set()
        release.wait(5)
        return real(path, *args, **kwargs)

    monkeypatch.setattr(storage_module.shutil, "rmtree", slow)
    results: list[int] = []
    first = threading.Thread(target=lambda: results.append(service.clear()))
    first.start()
    assert started.wait(5)
    second = threading.Thread(target=lambda: results.append(service.clear()))
    second.start()
    second.join(0.2)
    assert second.is_alive()  # รอครั้งแรก
    release.set()
    first.join(5)
    second.join(5)
    assert sorted(results) == [0, MB]


# ---------- ของค้างจากการล้างที่ถูกตัดกลางทาง ----------


def test_sweep_clear_leftovers_removes_only_our_trash(tmp_path):
    cache = tmp_path / "cache"
    sized(cache / (".clear-" + "c" * 32) / BBB / "f.jpg", 10)
    keep = [sized(cache / BBB / "f.jpg", 10), sized(cache / ".clear-x" / "f", 10)]
    assert sweep_clear_leftovers(cache) == 1
    assert all(p.is_file() for p in keep) and not (cache / (".clear-" + "c" * 32)).exists()
    assert sweep_clear_leftovers(tmp_path / "missing") == 0


def test_open_services_sweeps_clear_leftovers(tmp_path, monkeypatch):
    called: list[Path] = []
    monkeypatch.setattr(lifecycle, "sweep_clear_leftovers", lambda root: called.append(root) or 1)
    lifecycle.sweep_clear_once(tmp_path / "cache")
    assert called == [tmp_path / "cache"]

    def broken(root):
        raise OSError("boom")

    monkeypatch.setattr(lifecycle, "sweep_clear_leftovers", broken)
    lifecycle.sweep_clear_once(tmp_path / "cache")  # พลาดแค่ log ไม่ยกต่อ


def test_trash_left_in_the_cache_is_cleared_again(env):
    paths, _, _, service = env
    sized(paths.cache / (".clear-" + "d" * 32) / BBB / "f.jpg", MB)
    sized(paths.work / (".clear-" + "e" * 32) / JOB / "f", MB)
    assert service.usage().reclaimable_bytes == 2 * MB
    assert service.clear() == 2 * MB
    assert list(paths.cache.iterdir()) == [] and list(paths.work.iterdir()) == []


# ---------- C4: log ไม่มี path ไม่มีชื่อคลิป ----------


def test_logs_have_no_paths_or_titles(env, caplog, monkeypatch):
    paths, _, _, service = env
    sized(paths.cache / BBB / "storyboard" / "คลิปลับ.jpg", MB)
    sized(paths.cache / ZOO / "storyboard" / "f.jpg", MB)
    real = os.rename

    def locked(src, dst):
        if Path(src).name == ZOO:
            raise PermissionError(13, f"denied {src}")
        return real(src, dst)

    monkeypatch.setattr(storage_module.os, "rename", locked)
    with caplog.at_level(logging.DEBUG, logger="yttoolkit"):
        service.usage()
        service.clear()
    assert "storage_clear freed=1000000 entries=1 skipped=1" in caplog.text
    assert "storage_skip reason=PermissionError" in caplog.text
    assert str(paths.data_root) not in caplog.text and "คลิปลับ" not in caplog.text
    assert BBB not in caplog.text and ZOO not in caplog.text
```

Create `tests/unit/test_storage_readers.py`:
```python
"""ทุกตัวอ่าน cache ต้องทนโฟลเดอร์ data/cache/<id>/ ที่หายไป (M6 รอบ A spec 3.3: หลังกด "ล้างข้อมูลชั่วคราว")

หนึ่งเทสต่อหนึ่งแถวของตาราง spec 3.3 (แถว api/videos._cache_target อยู่ที่ tests/api/test_storage_api.py)
FakeExtractor ไม่แตะเครือข่าย
"""

from __future__ import annotations

import shutil
from datetime import UTC, datetime
from pathlib import Path

import pytest
from helpers_capture import BBB as CAPTURE_CLIP
from helpers_capture import MEDIA, FakeVideos, FixtureFetcher, StubQueue, StubSettings, clip_info

from yttoolkit.core.capture import CaptureService
from yttoolkit.core.comments import PinnedCommentService
from yttoolkit.core.db import Database, purge_stale_cache
from yttoolkit.core.extractor import FakeExtractor
from yttoolkit.core.media import FakeMediaTools
from yttoolkit.core.sharp_store import read_sharp, sweep_sharp_leftovers
from yttoolkit.core.storyboard import get_storyboard
from yttoolkit.core.subtitles import SubtitleService
from yttoolkit.core.videos import VideoService

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
BBB = "aqz-KE-bpKQ"
THAI = "88o5Sk8_m1Y"
NOW = datetime(2026, 10, 14, 5, 0, tzinfo=UTC)
TRASH = ".clear-" + "f" * 32


@pytest.fixture
def env(tmp_path: Path):
    db = Database(tmp_path / "app.db")
    db.migrate()
    fake = FakeExtractor(FIXTURES)
    videos = VideoService(db, fake, now=lambda: NOW)
    yield db, fake, videos, tmp_path / "cache"
    db.close()


def _cleared(cache: Path, video_id: str) -> None:
    shutil.rmtree(cache / video_id, ignore_errors=True)
    assert not (cache / video_id).exists()


def test_storyboard_rebuilds_after_the_clip_cache_is_gone(env):
    _, fake, videos, cache = env
    first = get_storyboard(BBB, videos, cache, fake.fetch)
    _cleared(cache, BBB)
    again = get_storyboard(BBB, videos, cache, fake.fetch)
    assert len(again["frames"]) == len(first["frames"]) == 128
    assert (cache / BBB / "storyboard" / "index.json").is_file()


def test_read_sharp_is_none_after_the_clip_cache_is_gone(env):
    _, _, _, cache = env
    (cache / BBB / "sharp").mkdir(parents=True)
    _cleared(cache, BBB)
    assert read_sharp(cache, BBB) is None


def test_the_capture_strip_is_empty_after_the_clip_cache_is_gone(tmp_path):
    service = CaptureService(FakeVideos({CAPTURE_CLIP: clip_info()}), FixtureFetcher(), FakeMediaTools(MEDIA),
                             tmp_path / "cache", StubSettings(tmp_path / "out"), StubQueue(),
                             work_root=tmp_path / "work", now=lambda: NOW)  # fmt: skip
    capture, _ = service.capture(CAPTURE_CLIP, 1_000)
    copies = list((tmp_path / "out").rglob("*.jpg"))
    assert service.list(CAPTURE_CLIP) and copies
    _cleared(tmp_path / "cache", CAPTURE_CLIP)
    assert service.list(CAPTURE_CLIP) == []
    assert all(p.is_file() for p in copies)  # สำเนาใน "ภาพที่ถ่าย/" ยังอยู่


def test_subtitle_tokens_download_again_after_the_clip_cache_is_gone(env):
    _, fake, videos, cache = env
    subtitles = SubtitleService(videos, fake.fetch_subtitle, cache)
    first = subtitles.tokens(THAI, "a.th-orig")
    _cleared(cache, THAI)
    again = subtitles.tokens(THAI, "a.th-orig")
    assert [t.t for t in again.tokens] == [t.t for t in first.tokens]
    assert (cache / THAI / "subs").is_dir()


def test_the_pinned_comment_is_fetched_again_after_the_clip_cache_is_gone(env):
    _, fake, videos, cache = env
    calls: list[str] = []

    def pinned(video_id: str) -> dict | None:
        calls.append(video_id)
        return {"text": "ปักหมุด", "likes": 1, "byUploader": True}

    service = PinnedCommentService(videos, pinned, cache, now=lambda: NOW)
    assert service.get(THAI) == {"text": "ปักหมุด", "likes": 1, "byUploader": True}
    _cleared(cache, THAI)
    assert service.get(THAI) == {"text": "ปักหมุด", "likes": 1, "byUploader": True}
    assert calls == [THAI, THAI]


def test_startup_sweeps_ignore_a_clear_trash_folder(env):
    db, _, _, cache = env
    trash = cache / TRASH / BBB / "storyboard"
    trash.mkdir(parents=True)
    (trash / "f.jpg").write_bytes(b"x")
    assert sweep_sharp_leftovers(cache) == 0
    assert purge_stale_cache(db, cache, NOW) == 0
    assert (trash / "f.jpg").is_file()  # ของ .clear-* ลบโดย sweep_clear_leftovers เท่านั้น
```

- [ ] **Step 2: Run them, expect FAIL**

Run: `cd "$WORKTREE" && uv run pytest tests/unit/test_storage.py tests/unit/test_storage_readers.py tests/api/test_storage_api.py tests/unit/test_queue.py tests/unit/test_capture.py tests/unit/test_db.py -q -W error -p no:cacheprovider`
Expected: `1 error` (collection error in `unit/test_storage.py`) — the run stops at collection: `yttoolkit.core.storage` does not exist yet. Run `tests/unit/test_queue.py tests/unit/test_capture.py tests/unit/test_db.py` alone to see the `hold_active` / `cache_folder` failures.

- [ ] **Step 3: Implement**

Create `src/yttoolkit/api/storage.py`:
```python
"""API ข้อมูลชั่วคราว (M6 รอบ A, FR-SET-6): GET /storage (ขนาด) · POST /storage/clear (ล้าง)

POST ผ่าน token + Origin ของ LocalOnlyMiddleware เหมือนคำขออื่นที่ไม่ใช่ GET · body ไม่ถูกอ่าน
route เป็น `def` ธรรมดา (เดินดิสก์) FastAPI จึงส่งไปรันใน threadpool · OSError ที่ไม่คาดคิด = 500 E_UNKNOWN (M6 รอบ B)
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from ..core.storage import StorageService

if TYPE_CHECKING:
    from ..app import AppContext

NO_STORE = {"Cache-Control": "no-store"}


def build_storage_router(ctx: AppContext) -> APIRouter:
    router = APIRouter()
    assert ctx.cache_root is not None  # create_app เรียกต่อเมื่อมี ctx.cache_root เท่านั้น
    service = StorageService(ctx.cache_root, ctx.paths.work, queue=ctx.queue, captures=ctx.captures)

    @router.get("/storage")
    def storage_usage() -> JSONResponse:
        return JSONResponse(service.usage().to_api(), headers=NO_STORE)

    @router.post("/storage/clear")
    def storage_clear() -> JSONResponse:
        return JSONResponse({"freedBytes": service.clear()}, headers=NO_STORE)

    return router
```

In `src/yttoolkit/app.py`:

Replace (1):
```python
from .api.static import mount_web
```
with:
```python
from .api.static import mount_web
from .api.storage import build_storage_router
```

Replace (2):
```python
        app.include_router(build_videos_router(ctx), prefix="/api")
```
with:
```python
        app.include_router(build_videos_router(ctx), prefix="/api")
    if ctx.cache_root is not None:
        # M6 รอบ A: ขนาดและการล้างข้อมูลชั่วคราว (ใช้คิวและการถ่ายภาพถ้ามี เพื่อข้ามของที่กำลังใช้)
        app.include_router(build_storage_router(ctx), prefix="/api")
```

In `src/yttoolkit/core/capture.py`:

Replace (1):
```python
from collections.abc import Callable, Mapping
```
with:
```python
from collections.abc import Callable, Iterator, Mapping
from contextlib import contextmanager
```

Replace (2):
```python
        self._guard = threading.Lock()
        self._clip_locks: dict[str, threading.Lock] = {}
```
with:
```python
        self._guard = threading.Lock()  # ห้ามถือแล้วเรียกออกไปนอกบริการ (ลำดับล็อก: คิว -> _guard)
        self._clip_locks: dict[str, threading.Lock] = {}
        # M6 รอบ A: การถ่ายที่กำลังทำ (รหัสคลิป, ชื่อโฟลเดอร์ทำงานใน work/) ปุ่มล้างข้อมูลชั่วคราวข้ามสองที่นี้
        self._current: tuple[str, str] | None = None
```

Replace (3):
```python
            return self._clip_locks.setdefault(video_id, threading.Lock())
```
with:
```python
            return self._clip_locks.setdefault(video_id, threading.Lock())

    @contextmanager
    def hold_active(self) -> Iterator[tuple[str, str] | None]:
        """ถือ _guard ตลอดบล็อกแล้วให้ (รหัสคลิป, ชื่อโฟลเดอร์ทำงาน) ของการถ่ายที่กำลังทำ ไม่มี = None
        การถ่ายที่จะเริ่มระหว่างบล็อกรอจนปล่อย (ไม่กี่มิลลิวินาที) จึงไม่สร้างโฟลเดอร์ทำงานแทรกกลาง"""
        with self._guard:
            yield self._current
```

Replace (4):
```python
            raise YtError("E_CAPTURE_BUSY", "another capture is running")
```
with:
```python
            raise YtError("E_CAPTURE_BUSY", "another capture is running")
        tmp = self._work_root / f"capture-{uuid.uuid4().hex}"
        with self._guard:
            self._current = (video_id, tmp.name)  # ก่อนสร้างโฟลเดอร์ทำงาน: ปุ่มล้างข้อมูลชั่วคราวเห็นเสมอ
```

Replace (5):
```python
            return self._capture_locked(video_id, str(info.get("title") or ""), t_ms), True
```
with:
```python
            return self._capture_locked(video_id, str(info.get("title") or ""), t_ms, tmp), True
```

Replace (6):
```python
            self._busy.release()

    def _capture_locked(self, video_id: str, title: str, t_ms: int) -> Capture:
        tmp = self._work_root / f"capture-{uuid.uuid4().hex}"
```
with:
```python
            with self._guard:
                self._current = None
            self._busy.release()

    def _capture_locked(self, video_id: str, title: str, t_ms: int, tmp: Path) -> Capture:
```

In `src/yttoolkit/core/db.py`:

Replace (1):
```python

def _remove_cache_folder(root: Path, video_id: str) -> bool:
```
with:
```python

def cache_folder(root: Path, name: str) -> Path | None:
    """โฟลเดอร์ cache ของคลิป `<root>/<name>` (resolve แล้ว) เมื่อ name เป็นรหัสคลิปที่ถูกรูป และยังอยู่ใต้ root
    (ไม่ใช่ root เอง) · ไม่ผ่าน = None ผู้เรียกต้องไม่แตะดิสก์ · root ต้อง resolve มาแล้ว
    ที่เดียวที่ตัดสินว่าชื่อไหนเป็นโฟลเดอร์ cache ที่แอพสร้าง (ล้าง cache เก่า และปุ่มล้างข้อมูลชั่วคราว M6 รอบ A)
    งานในอนาคต (เว็บอื่น C12): เปลี่ยนการตรวจ VIDEO_ID ตรงนี้เป็นตัวตรวจ cache key ที่เดียว"""
    if not VIDEO_ID.fullmatch(name):
        return None
    folder = (root / name).resolve()
    if folder == root or not folder.is_relative_to(root):
        return None
    return folder


def _remove_cache_folder(root: Path, video_id: str) -> bool:
```

Replace (2):
```python
    folder = (root / video_id).resolve()
    if folder == root or not folder.is_relative_to(root):
        log.warning("ข้ามการลบโฟลเดอร์ cache: %s อยู่นอก %s", folder, root)
```
with:
```python
    folder = cache_folder(root, video_id)
    if folder is None:
        log.warning("ข้ามการลบโฟลเดอร์ cache: %s อยู่นอก %s", root / video_id, root)
```

In `src/yttoolkit/core/queue.py`:

Replace (1):
```python
from collections.abc import Callable, Mapping, Sequence
```
with:
```python
from collections.abc import Callable, Iterator, Mapping, Sequence
from contextlib import contextmanager
```

Replace (2):
```python

class SettingsView(Protocol):
```
with:
```python

@dataclass(frozen=True)
class ActiveJobs:
    """งานที่กำลังทำ ณ ตอนถือล็อกของคิว (M6 รอบ A ปุ่มล้างข้อมูลชั่วคราวข้าม work/<jobId> และ cache ของคลิปนั้น)"""

    job_ids: frozenset[str]
    video_ids: frozenset[str]


class SettingsView(Protocol):
```

Replace (3):
```python
        self.job_id = job.id
```
with:
```python
        self.job_id = job.id
        self.video_id = job.video_id  # M6 รอบ A: hold_active บอกคลิปที่ cache ห้ามถูกล้าง
```

Replace (4):
```python

    def is_cancelling(self, job_id: str) -> bool:
```
with:
```python

    @contextmanager
    def hold_active(self) -> Iterator[ActiveJobs]:
        """ถือล็อกของคิวตลอดบล็อก (ล็อกเดียวกับที่ tick ใช้เริ่มงาน) แล้วให้ชุดงานที่กำลังทำ
        งานที่เริ่มก่อนอยู่ในชุดเสมอ และไม่มีงานใหม่เริ่มระหว่างบล็อก · ผู้ถือต้องปล่อยเร็ว (ไม่ลบไฟล์ใต้ล็อก)
        ลำดับล็อก: ล็อกคิว -> ล็อกของ CaptureService (M6 รอบ A spec 3.2)"""
        with self._lock:
            active = list(self._active.values())
            yield ActiveJobs(frozenset(ctx.job_id for ctx in active), frozenset(ctx.video_id for ctx in active))

    def is_cancelling(self, job_id: str) -> bool:
```

Create `src/yttoolkit/core/storage.py`:
```python
"""ข้อมูลชั่วคราวของแอพ (M6 รอบ A, FR-SET-6): ขนาดของ data/cache/ และ work/ และปุ่ม "ล้างข้อมูลชั่วคราว"

ล้างได้เฉพาะสิ่งที่แอพสร้างเอง (spec 3.1):
- data/cache/<รหัสคลิป>/ ที่ db.cache_folder ยอมรับ ยกเว้นคลิปของงานที่กำลังทำ ของการถ่ายภาพที่กำลังทำ
  และโฟลเดอร์ที่มีของกำลังเตรียม (ลูกชื่อมี ".tmp-" ที่แก้ไขไม่เกิน STAGING_GRACE_S วินาที)
- work/<jobId>/ (uuid7 36 ตัว) ยกเว้นงานที่กำลังทำ · work/capture-<hex>/ ยกเว้นการถ่ายที่กำลังทำ
- .clear-<hex>/ ที่ค้างจากการล้างครั้งก่อน (ทั้งสองที่)
อย่างอื่นนับขนาดแต่ไม่ลบ ไม่ตาม symlink / junction · app.db, visitor-session, run/ และโฟลเดอร์ผลลัพธ์อยู่นอกทั้งสองที่

ล้างเป็นสองช่วง (spec 3.2): ใต้ล็อกของคิวและของการถ่ายภาพ (ไม่กี่มิลลิวินาที) ย้ายของที่ล้างได้เข้า .clear-<hex>/
ในโฟลเดอร์เดียวกัน (ไม่ข้ามไดรฟ์) · นอกล็อกจึงค่อยลบจริง ลบไม่หมด (ไฟล์เปิดค้าง) = เหลือไว้ล้างรอบหน้าหรือตอนเปิดโปรแกรม
log มีแต่ตัวเลขและชื่อชนิด error ไม่มี path ไม่มีรหัสคลิป (C4) · core/ ไม่ import api/ platform/ หรือ yt_dlp
"""

from __future__ import annotations

import logging
import os
import re
import shutil
import threading
import time
import uuid
from collections.abc import Callable, Iterator
from contextlib import AbstractContextManager, ExitStack, contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from .db import cache_folder
from .queue import ActiveJobs

log = logging.getLogger("yttoolkit")

STAGING_GRACE_S = 600  # ของที่กำลังเตรียม (storyboard.tmp-*, sharp.tmp-*) ใหม่กว่านี้ = โฟลเดอร์ของคลิปนั้นยังไม่ล้าง
STAGING_MARK = ".tmp-"
TRASH_PREFIX = ".clear-"
_TRASH = re.compile(r"\.clear-[0-9a-f]{32}")
_JOB_DIR = re.compile(r"[0-9a-f-]{36}")
_CAPTURE_DIR = re.compile(r"capture-[0-9a-f]{32}")


@dataclass(frozen=True)
class StorageUsage:
    cache_bytes: int
    work_bytes: int
    reclaimable_bytes: int

    def to_api(self) -> dict[str, int]:
        return {"cacheBytes": self.cache_bytes, "workBytes": self.work_bytes, "reclaimableBytes": self.reclaimable_bytes}


class JobHold(Protocol):
    def hold_active(self) -> AbstractContextManager[ActiveJobs]: ...


class CaptureHold(Protocol):
    def hold_active(self) -> AbstractContextManager[tuple[str, str] | None]: ...


@dataclass(frozen=True)
class _Active:
    job_ids: frozenset[str]
    video_ids: frozenset[str]
    capture_dir: str | None


@dataclass(frozen=True)
class _Entry:
    path: Path
    clearable: bool


def _skip_link(entry: os.DirEntry[str]) -> bool:
    return entry.is_symlink() or entry.is_junction()


def tree_bytes(path: Path) -> int:
    """ขนาดรวม (st_size) ของไฟล์ปกติทุกไฟล์ใต้ path (path เป็นไฟล์ก็ได้) ไม่ตาม symlink / junction
    อ่านไม่ได้ = นับ 0 แล้วข้าม · ไม่มี path = 0"""
    try:
        if path.is_symlink() or path.is_junction():
            return 0
        if path.is_file():
            return path.stat().st_size
    except OSError:
        return 0
    total = 0
    stack = [path]
    while stack:
        current = stack.pop()
        try:
            with os.scandir(current) as entries:
                for entry in entries:
                    try:
                        if _skip_link(entry):
                            continue
                        if entry.is_dir(follow_symlinks=False):
                            stack.append(Path(entry.path))
                        elif entry.is_file(follow_symlinks=False):
                            total += entry.stat(follow_symlinks=False).st_size
                    except OSError:
                        continue
        except OSError:
            continue
    return total


class StorageService:
    """ขนาดและการล้างข้อมูลชั่วคราว queue / captures = ตัวที่บอกงานที่กำลังทำ (None = ไม่มีบริการนั้น)"""

    def __init__(
        self,
        cache_root: Path,
        work_root: Path,
        *,
        queue: JobHold | None,
        captures: CaptureHold | None,
        now: Callable[[], float] = time.time,
    ) -> None:
        self._cache_root = Path(cache_root)
        self._work_root = Path(work_root)
        self._queue = queue
        self._captures = captures
        self._now = now
        self._clearing = threading.Lock()  # ล้างครั้งละครั้ง (ครั้งที่สองรอแล้วล้างสิ่งที่เหลือ)

    @contextmanager
    def _hold(self) -> Iterator[_Active]:
        """ถือล็อกของคิวแล้วของการถ่ายภาพ (ลำดับนี้เสมอ) ตลอดบล็อก ระหว่างนี้ไม่มีงาน/การถ่ายเริ่มใหม่"""
        with ExitStack() as stack:
            jobs = stack.enter_context(self._queue.hold_active()) if self._queue is not None else None
            capture = stack.enter_context(self._captures.hold_active()) if self._captures is not None else None
            yield _Active(
                job_ids=jobs.job_ids if jobs is not None else frozenset(),
                video_ids=(jobs.video_ids if jobs is not None else frozenset())
                | (frozenset({capture[0]}) if capture is not None else frozenset()),
                capture_dir=capture[1] if capture is not None else None,
            )

    def _staging(self, folder: Path) -> bool:
        """มีของกำลังเตรียมที่ยังใหม่อยู่ในโฟลเดอร์ของคลิป (เช่นอีกแท็บกำลังสร้าง storyboard)"""
        try:
            with os.scandir(folder) as entries:
                for entry in entries:
                    if STAGING_MARK not in entry.name:
                        continue
                    try:
                        modified = entry.stat(follow_symlinks=False).st_mtime
                    except OSError:
                        return True  # อ่านเวลาไม่ได้ = ถือว่ายังเตรียมอยู่ (ไม่เสี่ยงลบ)
                    if self._now() - modified < STAGING_GRACE_S:
                        return True
        except OSError:
            return True
        return False

    def _list(self, root: Path, active: _Active, *, cache: bool) -> list[_Entry]:
        """ของทุกชิ้นใน root คู่กับว่าล้างได้ไหม (ตามตาราง spec 3.1) · ไม่มี root = [] · อ่าน root ไม่ได้ = OSError ต่อ"""
        try:
            with os.scandir(root) as found:
                entries = list(found)
        except FileNotFoundError:
            return []
        resolved = root.resolve()
        listed: list[_Entry] = []
        for entry in entries:
            path = Path(entry.path)
            try:
                plain_dir = not _skip_link(entry) and entry.is_dir(follow_symlinks=False)
            except OSError:
                plain_dir = False
            clearable = False
            if plain_dir and _TRASH.fullmatch(entry.name):
                clearable = True
            elif plain_dir and cache:
                folder = cache_folder(resolved, entry.name)
                clearable = folder is not None and entry.name not in active.video_ids and not self._staging(path)
            elif plain_dir and _JOB_DIR.fullmatch(entry.name):
                clearable = entry.name not in active.job_ids
            elif plain_dir and _CAPTURE_DIR.fullmatch(entry.name):
                clearable = entry.name != active.capture_dir
            listed.append(_Entry(path, clearable))
        return listed

    def usage(self) -> StorageUsage:
        """ขนาดตอนนี้: ถือล็อกแค่ตอนดูว่าอะไรล้างได้ วัดขนาดนอกล็อก"""
        with self._hold() as active:
            cache = self._list(self._cache_root, active, cache=True)
            work = self._list(self._work_root, active, cache=False)
        sizes = {entry.path: tree_bytes(entry.path) for entry in (*cache, *work)}
        return StorageUsage(
            cache_bytes=sum(sizes[e.path] for e in cache),
            work_bytes=sum(sizes[e.path] for e in work),
            reclaimable_bytes=sum(sizes[e.path] for e in (*cache, *work) if e.clearable),
        )

    def clear(self) -> int:
        """ล้างทุกอย่างที่ล้างได้ คืนจำนวนไบต์ที่ลบได้จริง (ไม่ใช่ที่วางแผนไว้)"""
        with self._clearing:
            trashes: list[Path] = []
            moved = skipped = 0
            with self._hold() as active:
                for root, cache in ((self._cache_root, True), (self._work_root, False)):
                    targets = [e.path for e in self._list(root, active, cache=cache) if e.clearable]
                    if not targets:
                        continue
                    trash = root / f"{TRASH_PREFIX}{uuid.uuid4().hex}"
                    try:
                        trash.mkdir()
                    except OSError as exc:
                        skipped += len(targets)
                        log.debug("storage_skip reason=%s", type(exc).__name__)
                        continue
                    trashes.append(trash)
                    for path in targets:
                        try:
                            os.rename(path, trash / path.name)  # โฟลเดอร์แม่เดียวกัน ไม่ข้ามไดรฟ์
                            moved += 1
                        except OSError as exc:  # Windows: มีไฟล์เปิดค้างในโปรแกรมอื่น
                            skipped += 1
                            log.debug("storage_skip reason=%s", type(exc).__name__)
            freed = 0
            for trash in trashes:
                planned = tree_bytes(trash)
                shutil.rmtree(trash, ignore_errors=True)
                left = tree_bytes(trash) if trash.exists() else 0
                try:
                    trash.rmdir()
                except OSError:
                    pass  # ยังมีไฟล์ลบไม่ได้: เหลือ .clear-* ไว้ล้างรอบหน้า
                freed += planned - left
            log.info("storage_clear freed=%s entries=%s skipped=%s", freed, moved, skipped)
            return freed


def sweep_clear_leftovers(cache_root: Path) -> int:
    """ตอนเปิดโปรแกรม: ลบ data/cache/.clear-*/ ที่ค้างจากการล้างที่ถูกตัดกลางทาง คืนจำนวนโฟลเดอร์ที่ลบหมด
    (work/.clear-* ถูกลบอยู่แล้วตอน QueueRunner.recover ล้าง work/ ทั้งโฟลเดอร์)"""
    try:
        with os.scandir(cache_root) as found:
            entries = list(found)
    except FileNotFoundError:
        return 0
    removed = 0
    for entry in entries:
        if not _TRASH.fullmatch(entry.name) or _skip_link(entry) or not entry.is_dir(follow_symlinks=False):
            continue
        shutil.rmtree(entry.path, ignore_errors=True)
        if not os.path.exists(entry.path):
            removed += 1
    return removed
```

In `src/yttoolkit/lifecycle.py`:

Replace (1):
```python
from .core.sharp_store import sweep_sharp_leftovers
```
with:
```python
from .core.sharp_store import sweep_sharp_leftovers
from .core.storage import sweep_clear_leftovers
```

Replace (2):
```python
        sweep_sharp_cache_once(paths.cache)
```
with:
```python
        sweep_sharp_cache_once(paths.cache)
        sweep_clear_once(paths.cache)
```

Replace (3):
```python

def start_periodic_purge(
```
with:
```python

def sweep_clear_once(cache_root: Path) -> None:
    """ตอนเปิดโปรแกรม (ยังไม่มีงานรัน): ลบ data/cache/.clear-* ที่ค้างจากการล้างข้อมูลชั่วคราวที่ถูกตัดกลางทาง
    (M6 รอบ A) พลาดแค่บันทึก log"""
    try:
        count = sweep_clear_leftovers(cache_root)
        if count:
            log.info("storage_sweep removed=%s", count)
    except Exception:
        log.exception("ล้างข้อมูลชั่วคราวที่ค้างไม่สำเร็จ (ข้ามไปก่อน)")


def start_periodic_purge(
```

Notes for the implementer:
- Lock order is always queue `_lock` → captures `_guard` (`StorageService._hold`); `_guard` is never held while calling out of `CaptureService` (spec 3.2). Nothing is deleted while a hold is taken: phase 1 only renames into `.clear-<hex>/` in the same root, phase 2 measures and deletes outside the holds.
- `freedBytes` is measured (trash size before minus what is left), never the planned size (Review Focus 3).
- `cache_folder` is the one place that decides whether a name is a clip cache folder (C12); `storage.py` adds no id regex.
- `storage.py` imports nothing from `api/`, `platform/` or `yt_dlp`; log lines carry counts and error class names only (C4).

- [ ] **Step 4: Run the tests, expect PASS**

Run: the Step 2 command. Expected: `218 passed`. Then the full suite (all pass).

- [ ] **Step 5: Commit**
```bash
cd "$WORKTREE" && git add src/yttoolkit/core/storage.py src/yttoolkit/api/storage.py src/yttoolkit/core/db.py src/yttoolkit/core/queue.py src/yttoolkit/core/capture.py src/yttoolkit/app.py src/yttoolkit/lifecycle.py tests/unit/test_storage.py tests/unit/test_storage_readers.py tests/api/test_storage_api.py tests/unit/test_queue.py tests/unit/test_capture.py tests/unit/test_db.py && git commit -F- <<'EOF'
feat(storage): measure and clear temporary data without touching running jobs or captures

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
EOF
```


### Task 8: The TS mirror `lib/filename.ts` and the golden parity test (spec 2.2, 2.5; C10)

**Files:**
- Create: `web/src/lib/filename.ts`, `web/src/lib/filename.test.ts`, `web/src/lib/filename-parity.test.ts`

**Interfaces:**
- Consumes: T1's `tests/fixtures/names/cases.json` and `golden.json` (read with `import.meta.glob(..., { query: "?raw" })`, as `srt-parity.test.ts`); `Settings["filenameStyle"]` (`lib/types.ts`).
- Produces: K1 TS side exactly. T12 calls `planNames`, `PathTooLongError`, `FILENAME_STYLES`, `FilenameStyle`, `NameInput`.

- [ ] **Step 1: Write the failing tests**

Create `web/src/lib/filename-parity.test.ts`:
```ts
/**
 * ตัวอย่างชื่อไฟล์ในหน้าเว็บต้องตรงกับชื่อจริงที่ backend ตั้งทุกตัวอักษร (M6 รอบ A spec 2.5, C10)
 *
 * อ่าน tests/fixtures/names/cases.json (ข้อมูลเข้า) และ golden.json (ผลจาก files.plan_names ที่
 * tests/unit/test_names_golden.py สร้าง) แล้วเทียบกับ planNames ตรง ๆ ถ้าไม่ตรงคือฝั่งใดฝั่งหนึ่งผิด ห้ามแก้ golden
 */
import { describe, expect, it } from "vitest"

import { PathTooLongError, planNames, type NameInput } from "./filename"

const files = import.meta.glob("../../../tests/fixtures/names/*.json", {
  query: "?raw",
  import: "default",
  eager: true,
}) as Record<string, string>

type Case = NameInput & { name: string }
type Golden = Record<string, { folder: string; file: string } | { error: string }>

function load<T>(name: string): T {
  const entry = Object.entries(files).find(([path]) => path.endsWith(`/${name}`))
  if (!entry) throw new Error(`missing fixture ${name}`)
  return JSON.parse(entry[1]) as T
}

const cases = load<Case[]>("cases.json")
const golden = load<Golden>("golden.json")

function actual(input: NameInput): { folder: string; file: string } | { error: string } {
  try {
    return planNames(input)
  } catch (error) {
    if (error instanceof PathTooLongError) return { error: error.message }
    throw error
  }
}

describe("planNames ตรงกับ files.plan_names (golden)", () => {
  it("มี golden ครบทุกกรณี และไม่มี golden เกิน", () => {
    expect(Object.keys(golden).sort()).toEqual(cases.map((c) => c.name).sort())
    expect(cases.length).toBeGreaterThanOrEqual(50)
  })

  it.each(cases.map((c) => [c.name, c] as const))("%s", (name, input) => {
    expect(actual(input)).toEqual(golden[name])
  })
})
```

Create `web/src/lib/filename.test.ts`:
```ts
import { describe, expect, it } from "vitest"

import { FILENAME_STYLES, PATH_LIMIT, PathTooLongError, planNames, safeComponent, truncateTitle } from "./filename"

/** ตัวอักษรจาก code point (เทสไม่ใช้ escape แบบ backslash-u ในซอร์ส) */
const cp = (...codes: number[]) => String.fromCodePoint(...codes)

describe("safeComponent (กฎเดียวกับ files.safe_component)", () => {
  it("ช่องว่างแบบ Python: U+001C-U+001F และ U+0085 เป็นช่องว่าง U+FEFF กับ U+200B ถูกทิ้ง (Cf)", () => {
    expect(safeComponent(`a${cp(0x1c)}b${cp(0x1f)}c${cp(0x85)}d`, "x")).toBe("a b c d")
    expect(safeComponent(`a${cp(0xfeff)}b${cp(0x200b)}c`, "x")).toBe("abc")
    expect(safeComponent(`${cp(0x3000)}ก${cp(0xa0)}ข${cp(0x09, 0x0a)}`, "x")).toBe("ก ข")
  })

  it("ตัดอักขระต้องห้ามแล้วรวมช่องว่างซ้ำ ตัดจุด/ช่องว่างท้ายชื่อ", () => {
    expect(safeComponent('ทดสอบ: "A/B" <ภาค 1>?', "x")).toBe("ทดสอบ AB ภาค 1")
    expect(safeComponent("Why | How", "x")).toBe("Why How")
    expect(safeComponent("Hello... . ", "x")).toBe("Hello")
  })

  it("ว่าง = ค่าสำรอง · ชื่อสงวนของ Windows ได้ _ นำหน้า", () => {
    expect(safeComponent('?:*"<>|', "dQw4w9WgXcQ")).toBe("dQw4w9WgXcQ")
    expect(safeComponent("CON", "x")).toBe("_CON")
    expect(safeComponent("com1.txt", "x")).toBe("_com1.txt")
    expect(safeComponent("LPT¹", "x")).toBe("_LPT¹")
    expect(safeComponent("CONSOLE", "x")).toBe("CONSOLE")
  })
})

describe("truncateTitle (กฎเดียวกับ files.truncate_title)", () => {
  it("ไม่ตัดกลางคู่ surrogate (อีโมจินับ 2)", () => {
    expect(truncateTitle("😀😀😀", 5)).toBe("😀😀")
    expect(truncateTitle("😀😀😀", 1)).toBe("")
  })

  it("ไม่ทิ้งสระ/วรรณยุกต์ไว้หลังรอยตัด (ถอยไปก่อนพยัญชนะ)", () => {
    expect(truncateTitle("กี่", 1)).toBe("")
    expect(truncateTitle("กี่กี่", 4)).toBe("กี่")
    expect(truncateTitle("ที่นี่", 2)).toBe("")
    expect(truncateTitle("ที่นี่", 4)).toBe("ที่")
  })

  it("พอดีแล้วไม่ตัด แต่ยังตัดจุด/ช่องว่างท้าย", () => {
    expect(truncateTitle("abc. ", 10)).toBe("abc")
    expect(truncateTitle("abcdef", 3)).toBe("abc")
  })
})

describe("planNames", () => {
  const base = { baseLen: 40, title: "สอนทำกับข้าวง่าย ๆ ใน 10 นาที", clipId: "abcdefghijk", suffix: "", ext: "mp4" }

  it("สามรูปแบบ: โฟลเดอร์เดิม ชื่อไฟล์ต่างกันตามรูปแบบ", () => {
    const names = FILENAME_STYLES.map((style) => planNames({ ...base, style, uploader: "ครัวบ้านเรา", quality: "1080p" }))
    expect(new Set(names.map((n) => n.folder))).toEqual(new Set(["สอนทำกับข้าวง่าย ๆ ใน 10 นาที [abcdefghijk]"]))
    expect(names.map((n) => n.file)).toEqual([
      "สอนทำกับข้าวง่าย ๆ ใน 10 นาที.mp4",
      "สอนทำกับข้าวง่าย ๆ ใน 10 นาที - ครัวบ้านเรา.mp4",
      "สอนทำกับข้าวง่าย ๆ ใน 10 นาที (1080p).mp4",
    ])
  })

  it("path ยาวเกินแม้ใช้รหัสคลิป = PathTooLongError", () => {
    expect(() => planNames({ ...base, baseLen: PATH_LIMIT })).toThrow(PathTooLongError)
  })

  it("รูปแบบที่ไม่รู้จักหรือส่วนคุณภาพผิดรูป = Error (ข้อผิดพลาดของโปรแกรม)", () => {
    expect(() => planNames({ ...base, style: "channel" as never })).toThrow("unknown filename style")
    expect(() => planNames({ ...base, style: "title-quality", quality: "1080P" })).toThrow("bad quality label")
  })
})
```

- [ ] **Step 2: Run them, expect FAIL**

Run: `cd "$WORKTREE/web" && npm run typecheck`
Expected: `tsc` fails (first errors: `src/lib/filename-parity.test.ts(9,61): error TS2307: Cannot find module './filename' or its corresponding type declarations.`; `src/lib/filename-parity.test.ts(33,60): error TS18046: 'error' is of type 'unknown'.`; `src/lib/filename.test.ts(3,104): error TS2307: Cannot find module './filename' or its corresponding type declarations.`; `src/lib/filename.test.ts(53,40): error TS7006: Parameter 'style' implicitly has an 'any' type.`; `src/lib/filename.test.ts(54,31): error TS7006: Parameter 'n' implicitly has an 'any' type.`).

- [ ] **Step 3: Implement `web/src/lib/filename.ts`**

Create `web/src/lib/filename.ts`:
```ts
/**
 * ชื่อโฟลเดอร์/ไฟล์ตามรูปแบบชื่อไฟล์ (M6 รอบ A spec 2.2) — ตัวเดียวกับ files.plan_names ของ backend ทุกตัวอักษร
 *
 * หน้าเว็บใช้ทำบรรทัด "ตัวอย่าง: …" ในหน้าตั้งค่าโดยไม่เรียก API (AC-OUT-10) ชื่อไฟล์จริงตั้งที่ backend เสมอ
 * ทั้งสองฝั่งเทียบกันด้วย tests/fixtures/names/{cases,golden}.json (filename-parity.test.ts) ห้ามแก้ golden ให้เทสผ่าน
 *
 * จุดที่ต้องเลียน Python ให้ตรง:
 * - ความยาวนับเป็น UTF-16 code unit (`string.length`) เหมือน files._u16
 * - `\s` ของ Python ไม่เท่ากับของ JS: PY_WS = ช่องว่างตาม str.isspace() (มี \x1c-\x1f \x85 ไม่มี U+FEFF)
 * - ตัวที่ทิ้ง: \ / : * ? " < > | และหมวด Cc Cf Cs ตรวจทีละ code point
 * - ตัดชื่อทีละ code point ไม่ทิ้งสระ/วรรณยุกต์ (หมวด M) ไว้ตัวแรกหลังรอยตัด แล้วตัด "." และช่องว่างท้ายชื่อ
 */
import type { Settings } from "./types"

export type FilenameStyle = Settings["filenameStyle"]

/** ลำดับเดียวกับ files.NAME_STYLES / settings.FILENAME_STYLES ของ backend (ลำดับที่แสดงในหน้าตั้งค่า) */
export const FILENAME_STYLES = ["title", "title-channel", "title-quality"] as const satisfies readonly FilenameStyle[]

export type NameInput = {
  baseLen: number
  title: string
  clipId: string
  suffix: string
  ext: string
  style?: FilenameStyle
  uploader?: string
  quality?: string | null
}

export const PATH_LIMIT = 240
export const TITLE_MAX = 100
export const TAIL_RESERVE = 30
export const TAIL_MAX = 60
export const UNIQUE_RESERVE = 5
export const CHANNEL_SEP = " - "
const MIN_TITLE = 8
const QUALITY_LABEL = /^[a-z0-9 ]{1,16}$/

// ช่องว่างตาม str.isspace() ของ Python (ตรงกับ \s ของ re ใน Python) ไม่ใช่ \s ของ JS: ครบ 29 ตัว
const PY_WS_CODES = [
  0x09, 0x0a, 0x0b, 0x0c, 0x0d, 0x1c, 0x1d, 0x1e, 0x1f, 0x20, 0x85, 0xa0, 0x1680,
  0x2000, 0x2001, 0x2002, 0x2003, 0x2004, 0x2005, 0x2006, 0x2007, 0x2008, 0x2009, 0x200a,
  0x2028, 0x2029, 0x202f, 0x205f, 0x3000,
]
// ตัวอักษรจริงในวงเล็บ [] (ไม่ใช้ escape แบบ backslash-u ในซอร์ส) · ไม่มีตัวไหนมีความหมายพิเศษในวงเล็บ
const PY_WS_CLASS = String.fromCodePoint(...PY_WS_CODES)
const PY_WS = new RegExp(`[${PY_WS_CLASS}]+`, "gu")
const PY_WS_EDGES = new RegExp(`^[${PY_WS_CLASS}]+|[${PY_WS_CLASS}]+$`, "gu")
const FORBIDDEN = new Set(["\\", "/", ":", "*", "?", '"', "<", ">", "|"])
const DROPPED_CATEGORY = /^[\p{Cc}\p{Cf}\p{Cs}]$/u
const MARK = /^\p{M}$/u
const TRAILING_DOTS = /[. ]+$/

const RESERVED = new Set<string>([
  "CON", "PRN", "AUX", "NUL", "CONIN$", "CONOUT$",
  ...Array.from({ length: 9 }, (_, i) => `COM${i + 1}`),
  ...Array.from({ length: 9 }, (_, i) => `LPT${i + 1}`),
  // Windows ถือเลขยกกำลัง ¹ ² ³ เป็นเลขพอร์ตด้วย
  ...["COM", "LPT"].flatMap((dev) => ["¹", "²", "³"].map((sup) => `${dev}${sup}`)),
])

export class PathTooLongError extends Error {
  constructor() {
    super("path too long")
    this.name = "PathTooLongError"
  }
}

function pyStrip(text: string): string {
  return text.replace(PY_WS_EDGES, "")
}

/** files.safe_component: ชื่อที่เป็นส่วนหนึ่งของ path บน Windows ได้ · เหลือว่าง = fallback */
export function safeComponent(text: string, fallback: string): string {
  const spaced = text.replace(PY_WS, " ")
  let kept = ""
  for (const ch of spaced) {
    if (!FORBIDDEN.has(ch) && !DROPPED_CATEGORY.test(ch)) kept += ch
  }
  const name = pyStrip(kept.replace(PY_WS, " ")).replace(TRAILING_DOTS, "")
  if (!name) return fallback
  const head = pyStrip(name.split(".")[0] ?? "").toUpperCase()
  return RESERVED.has(head) ? `_${name}` : name
}

/** files.truncate_title: ยาวไม่เกิน limit (UTF-16) ไม่ตัดกลางคู่ surrogate และไม่ทิ้งสระ/วรรณยุกต์ไว้หลังรอยตัด */
export function truncateTitle(text: string, limit: number): string {
  if (text.length <= limit) return text.replace(TRAILING_DOTS, "")
  const points = Array.from(text)
  let cut = 0
  let used = 0
  for (const ch of points) {
    used += ch.length
    if (used > limit) break
    cut += 1
  }
  while (cut > 0 && MARK.test(points[cut] ?? "")) cut -= 1
  return points.slice(0, cut).join("").replace(TRAILING_DOTS, "")
}

function stem(short: string, channel: string, avail: number): string {
  if (!channel) return short.length <= avail ? short : truncateTitle(short, avail)
  const joined = `${short}${CHANNEL_SEP}${channel}`
  if (joined.length <= avail) return joined
  const sep = CHANNEL_SEP.length
  const cut = truncateTitle(short, Math.max(avail - sep - channel.length, MIN_TITLE))
  if (cut && `${cut}${CHANNEL_SEP}${channel}`.length <= avail) return `${cut}${CHANNEL_SEP}${channel}`
  const room = avail - cut.length - sep
  const shortChannel = cut && room >= 1 ? truncateTitle(channel, room) : ""
  if (shortChannel) return `${cut}${CHANNEL_SEP}${shortChannel}`
  return truncateTitle(short, avail)
}

/** files.plan_names: (ชื่อโฟลเดอร์ของคลิป, ชื่อไฟล์) · path ยาวเกินแม้ใช้รหัสคลิป = PathTooLongError */
export function planNames(input: NameInput): { folder: string; file: string } {
  const { baseLen, title, clipId, suffix, ext, style = "title", uploader = "", quality = null } = input
  if (!(FILENAME_STYLES as readonly string[]).includes(style)) throw new Error(`unknown filename style: ${style}`)
  if (quality !== null && !QUALITY_LABEL.test(quality)) throw new Error(`bad quality label: ${quality}`)
  const qualityPart = style === "title-quality" && quality ? ` (${quality})` : ""
  const tail = `${qualityPart}${suffix}.${ext}`
  if (tail.length > TAIL_MAX) throw new Error("suffix + extension longer than TAIL_MAX")
  const t = safeComponent(title, clipId)
  const budget = PATH_LIMIT - (baseLen + 1) - ` [${clipId}]`.length - 1 - TAIL_RESERVE - UNIQUE_RESERVE
  const cap = Math.floor(budget / 2)
  const short = cap >= MIN_TITLE ? truncateTitle(t, Math.min(TITLE_MAX, cap)) : ""
  let folder: string
  let file: string
  if (short) {
    folder = `${short} [${clipId}]`
    const avail = budget - short.length + TAIL_RESERVE - tail.length
    const channel = style === "title-channel" ? safeComponent(uploader, "") : ""
    file = `${stem(short, channel, avail) || clipId}${tail}`
  } else {
    folder = clipId
    file = `${clipId}${tail}`
  }
  if (baseLen + 1 + folder.length + 1 + file.length > PATH_LIMIT - UNIQUE_RESERVE) throw new PathTooLongError()
  return { folder, file }
}
```

Notes for the implementer:
- `PY_WS_CODES` is Python's `str.isspace()` set (29 code points): it includes U+001C-U+001F and U+0085 (not whitespace in JS) and excludes U+FEFF (whitespace in JS, `Cf` in Python, so it is dropped instead).
- Iterate code points (`for (const ch of text)`, `Array.from(text)`), count `ch.length` (1 or 2): a surrogate pair is never split.
- Never edit `golden.json` to make the parity test pass; a mismatch is a bug in `filename.ts` (or, if Python changed, T1 regenerates).

- [ ] **Step 4: Run the tests, expect PASS**

Run: `cd "$WORKTREE/web" && npm run typecheck && npm run lint && npm test`
Expected: typecheck clean, lint clean, vitest `1129 passed (1129)`.

- [ ] **Step 5: Commit**
```bash
cd "$WORKTREE" && git add web/src/lib/filename.ts web/src/lib/filename.test.ts web/src/lib/filename-parity.test.ts && git commit -F- <<'EOF'
feat(web): planNames mirror of files.plan_names with golden parity

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
EOF
```


### Task 9: The "วาง" button in W1 (spec 1; AC-IN-08, AC-IN-09)

**Files:**
- Create: `web/src/pages/home/paste-button.ts`, `web/src/pages/home/paste-button.test.ts`
- Modify: `web/src/pages/home.tsx`, `web/src/pages/home/use-analyze.tsx`, `web/e2e/list.spec.ts` (P30)

**Interfaces:**
- Consumes: T4 `isSupportedLink`, `th.home.paste`, `th.home.pasteDenied`; `pasteShortcut()` (`lib/platform.ts`); `homeStore`, `useAnalyze`, `useGlobalPaste`.
- Produces: K8 `readClipboard`, `PasteOutcome`; the DOM id `paste-hint` that T14 checks. No other file calls `readText`.

- [ ] **Step 1: Write the failing tests**

In `web/e2e/list.spec.ts`:

Replace (1):
```ts
    await page.reload()
    await expectThreeIntact(page)
    await page.getByRole("button", { name: "วิเคราะห์" }).focus()
    await page.keyboard.press("Shift+Tab")
    await expect(page.getByRole("textbox")).toBeFocused()
```
with:
```ts
    await page.reload()
    await expectThreeIntact(page)
    // M6 รอบ A: ปุ่ม "วาง" อยู่ระหว่างช่องกับปุ่มวิเคราะห์ จึงเริ่มถอยจากปุ่มวาง
    await page.getByRole("button", { name: "วาง", exact: true }).focus()
    await page.keyboard.press("Shift+Tab")
    await expect(page.getByRole("textbox")).toBeFocused()
```

Replace (2):
```ts
    await page.reload()
    await expectThreeIntact(page)
    await page.getByRole("button", { name: "วิเคราะห์" }).focus()
    await page.keyboard.press("Shift+Tab")
    const box = page.getByRole("textbox")
```
with:
```ts
    await page.reload()
    await expectThreeIntact(page)
    // M6 รอบ A: ปุ่ม "วาง" อยู่ระหว่างช่องกับปุ่มวิเคราะห์ จึงเริ่มถอยจากปุ่มวาง
    await page.getByRole("button", { name: "วาง", exact: true }).focus()
    await page.keyboard.press("Shift+Tab")
    const box = page.getByRole("textbox")
```

Create `web/src/pages/home/paste-button.test.ts`:
```ts
import { describe, expect, it, vi } from "vitest"

import { readClipboard } from "./paste-button"

const reader = (readText: () => Promise<string>) => ({ clipboard: { readText: vi.fn(readText) } })

describe("readClipboard (ปุ่ม วาง)", () => {
  it("ลิงก์ยูทูป = analyze พร้อมข้อความเดิมไม่ตัดช่องว่าง", async () => {
    await expect(readClipboard(reader(async () => "  https://youtu.be/aqz-KE-bpKQ\n"))).resolves.toEqual({
      kind: "analyze",
      text: "  https://youtu.be/aqz-KE-bpKQ\n",
    })
    await expect(readClipboard(reader(async () => "ดูคลิปนี้ youtu.be/aqz-KE-bpKQ นะ"))).resolves.toMatchObject({
      kind: "analyze",
    })
  })

  it("ข้อความอื่น = fill", async () => {
    await expect(readClipboard(reader(async () => "สูตรแกงเขียวหวาน"))).resolves.toEqual({
      kind: "fill",
      text: "สูตรแกงเขียวหวาน",
    })
  })

  it("ว่างหรือมีแต่ช่องว่าง (เช่นคัดลอกรูปภาพ) = empty", async () => {
    await expect(readClipboard(reader(async () => ""))).resolves.toEqual({ kind: "empty" })
    await expect(readClipboard(reader(async () => " \n\t"))).resolves.toEqual({ kind: "empty" })
  })

  it("ผู้ใช้ไม่อนุญาต (NotAllowedError) หรือ NotFoundError = denied ไม่โยนต่อ", async () => {
    const refuse = async () => {
      throw new DOMException("Read permission denied.", "NotAllowedError")
    }
    await expect(readClipboard(reader(refuse))).resolves.toEqual({ kind: "denied" })
    const missing = async () => {
      throw new DOMException("No valid data on clipboard.", "NotFoundError")
    }
    await expect(readClipboard(reader(missing))).resolves.toEqual({ kind: "denied" })
  })

  it("readText โยนแบบ sync = denied", async () => {
    const clipboard = {
      readText: () => {
        throw new TypeError("Illegal invocation")
      },
    }
    await expect(readClipboard({ clipboard })).resolves.toEqual({ kind: "denied" })
  })

  it("ไม่มีคลิปบอร์ด หรือไม่มี readText = denied", async () => {
    await expect(readClipboard({ clipboard: undefined })).resolves.toEqual({ kind: "denied" })
    await expect(readClipboard({ clipboard: {} as Pick<Clipboard, "readText"> })).resolves.toEqual({ kind: "denied" })
  })

  it("ไม่ส่ง deps = ใช้ navigator.clipboard (ใน node ไม่มี = denied)", async () => {
    vi.stubGlobal("navigator", { clipboard: { readText: async () => "youtu.be/aqz-KE-bpKQ" } })
    try {
      await expect(readClipboard()).resolves.toEqual({ kind: "analyze", text: "youtu.be/aqz-KE-bpKQ" })
      vi.stubGlobal("navigator", {})
      await expect(readClipboard()).resolves.toEqual({ kind: "denied" })
    } finally {
      vi.unstubAllGlobals()
    }
  })

  it("อ่านคลิปบอร์ดครั้งเดียวต่อการกด", async () => {
    const deps = reader(async () => "x")
    await readClipboard(deps)
    expect(deps.clipboard.readText).toHaveBeenCalledTimes(1)
  })
})
```

- [ ] **Step 2: Run them, expect FAIL**

Run: `cd "$WORKTREE/web" && npm run typecheck`
Expected: `tsc` fails (first errors: `src/pages/home/paste-button.test.ts(3,31): error TS2307: Cannot find module './paste-button' or its corresponding type declarations.`).

- [ ] **Step 3: Implement**

In `web/src/pages/home.tsx`:

Replace (1):
```tsx
import { CircleX } from "lucide-react"
```
with:
```tsx
import { CircleX, Clipboard } from "lucide-react"
```

Replace (2):
```tsx
import { looksLikeYoutube } from "@/lib/paste"
import { pasteShortcut } from "@/lib/platform"

```
with:
```tsx
import { isSupportedLink } from "@/lib/paste"
import { pasteShortcut } from "@/lib/platform"

import { readClipboard } from "./home/paste-button"
```

Replace (3):
```tsx
  const [announce, setAnnounce] = useState("")
```
with:
```tsx
  const [announce, setAnnounce] = useState("")
  // M6 รอบ A (AC-IN-09): เบราว์เซอร์ไม่ให้อ่านคลิปบอร์ดตอนกด "วาง" = คำแนะนำใต้ช่อง (ไม่ใช่ error)
  const [pasteDenied, setPasteDenied] = useState(false)
```

Replace (4):
```tsx
  useGlobalPaste(analyze, pending)
```
with:
```tsx
  useGlobalPaste(analyze, pending)

  /** ปุ่ม "วาง" (D1): อ่านคลิปบอร์ดเมื่อกดเท่านั้น ลิงก์ = แทนข้อความในช่องแล้ววิเคราะห์ · ข้อความอื่น = เติมลงช่อง */
  async function pasteFromClipboard() {
    if (pending) return
    const outcome = await readClipboard()
    if (outcome.kind === "denied") {
      setPasteDenied(true)
      inputRef.current?.focus()
      return
    }
    setPasteDenied(false)
    if (outcome.kind === "empty") {
      inputRef.current?.focus()
      return
    }
    // ข้อความในช่องถูกแทนทั้งหมด: การแตะช่องครั้งแรกไม่ต้องเลือกข้อความเดิมแล้ว
    selectOnFirstFocus.current = false
    restoredSelected.current = false
    if (outcome.kind === "analyze") {
      analyze(outcome.text)
      return
    }
    homeStore.set({ text: outcome.text })
    inputRef.current?.focus()
  }
```

Replace (5):
```tsx
            onChange={(event) => {
              restoredSelected.current = false
```
with:
```tsx
            aria-describedby={pasteDenied ? "paste-hint" : undefined}
            onChange={(event) => {
              restoredSelected.current = false
              setPasteDenied(false)
```

Replace (6):
```tsx
              if (!replacesAll || !looksLikeYoutube(pasted)) return
```
with:
```tsx
              if (!replacesAll || !isSupportedLink(pasted)) return
```

Replace (7):
```tsx
          <InputGroupAddon align="block-end" className="justify-end">
            {/* aria-disabled แทน disabled เพื่อให้โฟกัสยังอยู่ที่ปุ่ม (analyze() กันการกดซ้ำอยู่แล้ว) */}
```
with:
```tsx
          <InputGroupAddon align="block-end" className="justify-end gap-2">
            {/* aria-disabled แทน disabled เพื่อให้โฟกัสยังอยู่ที่ปุ่ม (analyze() กันการกดซ้ำอยู่แล้ว) */}
            <Button
              type="button"
              variant="secondary"
              aria-disabled={pending}
              className="aria-disabled:pointer-events-none aria-disabled:opacity-50"
              onClick={() => void pasteFromClipboard()}
            >
              <Clipboard data-icon="inline-start" aria-hidden />
              {th.home.paste}
            </Button>
```

Replace (8):
```tsx
        </InputGroup>
```
with:
```tsx
        </InputGroup>
        {pasteDenied && (
          <p id="paste-hint" role="status" className="text-sm text-muted-foreground">
            {fill(th.home.pasteDenied, { key: pasteShortcut() })}
          </p>
        )}
```

Create `web/src/pages/home/paste-button.ts`:
```ts
import { isSupportedLink } from "@/lib/paste"

/**
 * ผลของปุ่ม "วาง" (M6 รอบ A spec 1.2, AC-IN-08 / AC-IN-09)
 * - analyze: ลิงก์ที่แอพวิเคราะห์ได้ → แทนข้อความในช่องแล้ววิเคราะห์ทันที (ส่งข้อความเดิมไม่ตัดช่องว่าง)
 * - fill: ข้อความอื่น → เติมลงช่องอย่างเดียว
 * - empty: คลิปบอร์ดว่างหรือมีแต่ช่องว่าง (เช่นคัดลอกรูปภาพ) → ไม่เปลี่ยนอะไร
 * - denied: เบราว์เซอร์ไม่มี readText หรือไม่อนุญาต → คำแนะนำใต้ช่อง (ไม่ใช่ error สีแดง)
 */
export type PasteOutcome =
  | { kind: "analyze"; text: string }
  | { kind: "fill"; text: string }
  | { kind: "empty" }
  | { kind: "denied" }

type ClipboardReader = Pick<Clipboard, "readText">

/**
 * อ่านคลิปบอร์ดเมื่อผู้ใช้กดปุ่มเท่านั้น (ไม่มีที่อื่นในแอพเรียก readText) · ไม่โยน error ทุกกรณี
 * deps.clipboard = ตัวแทนในเทส (ไม่ส่ง = navigator.clipboard ส่ง undefined = ไม่มีคลิปบอร์ด)
 */
export async function readClipboard(deps?: { clipboard?: ClipboardReader | undefined }): Promise<PasteOutcome> {
  const clipboard = deps && "clipboard" in deps ? deps.clipboard : globalThis.navigator?.clipboard
  if (!clipboard || typeof clipboard.readText !== "function") return { kind: "denied" }
  let text: string
  try {
    text = await clipboard.readText()
  } catch {
    // NotAllowedError (ผู้ใช้กดไม่อนุญาต) NotFoundError หรือ readText โยนเองแบบ sync
    return { kind: "denied" }
  }
  if (typeof text !== "string" || text.trim() === "") return { kind: "empty" }
  return isSupportedLink(text) ? { kind: "analyze", text } : { kind: "fill", text }
}
```

In `web/src/pages/home/use-analyze.tsx`:

Replace (1):
```tsx
import { looksLikeYoutube } from "@/lib/paste"
```
with:
```tsx
import { isSupportedLink } from "@/lib/paste"
```

Replace (2):
```tsx
    if (!looksLikeYoutube(pasted)) return
```
with:
```tsx
    if (!isSupportedLink(pasted)) return
```

Notes for the implementer:
- The button is `aria-disabled` (not `disabled`) while analyzing, like "วิเคราะห์": focus stays and the handler returns early.
- The hint is muted text with `role="status"`, not an `Alert` and not a toast (AC-IN-09); the textarea is `aria-describedby="paste-hint"` only while it shows.
- The two existing call sites (`home.tsx` in-box paste, `use-analyze.tsx` global paste) switch to `isSupportedLink` with no behaviour change (C12).

- [ ] **Step 4: Run the tests, expect PASS**

Run: `cd "$WORKTREE/web" && npm run typecheck && npm run lint && npm test`
Expected: typecheck clean, lint clean, vitest `1067 passed (1067)`. (`list.spec.ts` runs at gate 2.)

- [ ] **Step 5: Commit**
```bash
cd "$WORKTREE" && git add web/src/pages/home/paste-button.ts web/src/pages/home/paste-button.test.ts web/src/pages/home.tsx web/src/pages/home/use-analyze.tsx web/e2e/list.spec.ts && git commit -F- <<'EOF'
feat(web): paste button in W1 reads the clipboard only on click, hint when the browser refuses

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
EOF
```


### Task 10: The "ข้อมูลในเครื่อง" section — clear, back up, import (spec 3.3 web, 4.3, 5)

**Files:**
- Create: `web/src/pages/settings/local-data.ts`, `web/src/pages/settings/local-data.test.ts`, `web/src/pages/settings/local-data-section.tsx`
- Modify: `web/src/pages/settings/general-panel.tsx`

**Interfaces:**
- Consumes: T4 `storageQuery`, `clearStorage`, `exportSettings`, `importSettings`, `STORAGE_KEY`, `SETTINGS_KEY`, `MAX_SETTINGS_FILE_BYTES`, `ImportResult`, `StorageUsage`, `th.general.*`; M6-B `showErrorToast`, `PLAIN_TOAST`, `reportRequest`; `serverMessage` (`general-form.ts`); `formatBytes`; shadcn `AlertDialog`, `FieldSet`, `FieldLegend`, `Button`, `Spinner`.
- Produces: K8 `local-data.ts` names and `LocalDataSection` (rendered as the last item of `GeneralPanel`'s `FieldGroup`). T12 edits `general-panel.tsx` again in wave 3; T14 tests the section.

- [ ] **Step 1: Write the failing tests**

Create `web/src/pages/settings/local-data.test.ts`:
```ts
import { QueryClient } from "@tanstack/react-query"
import { describe, expect, it } from "vitest"

import { th } from "@/i18n/th"

import { clearButton, CLIP_CACHE_KEYS, forgetClipCaches, importNotice, importTooLarge, TOO_LARGE_REQUEST } from "./local-data"

describe("clearButton", () => {
  it("มีขนาด: ป้ายตาม BRD (1.2 GB) และกดได้", () => {
    expect(clearButton({ cacheBytes: 1_200_000_000, workBytes: 0, reclaimableBytes: 1_200_000_000 })).toEqual({
      label: "ล้างข้อมูลชั่วคราว (1.2 GB)",
      size: "1.2 GB",
      disabled: false,
    })
  })

  it("ไม่มีอะไรให้ล้าง = กดไม่ได้ · ยังไม่รู้ขนาด = ป้ายไม่มีขนาดและกดไม่ได้", () => {
    expect(clearButton({ cacheBytes: 5, workBytes: 0, reclaimableBytes: 0 })).toMatchObject({ disabled: true })
    expect(clearButton(undefined)).toEqual({ label: th.general.clearTempPlain, size: null, disabled: true })
  })
})

describe("forgetClipCaches", () => {
  it("ลบข้อมูลของคลิปที่หายไปกับ cache ส่วนข้อมูลคลิป ประวัติ รายชื่อซับ และค่าตั้งคงไว้", () => {
    const client = new QueryClient()
    for (const key of [...CLIP_CACHE_KEYS.map((k) => [...k, "aqz-KE-bpKQ"]), ["video", "aqz-KE-bpKQ"], ["history", {}],
      ["subtitles", "aqz-KE-bpKQ"], ["settings"], ["storage"]]) {
      client.setQueryData(key, { cached: true })
    }
    forgetClipCaches(client)
    const left = client.getQueryCache().getAll().map((q) => q.queryKey[0])
    expect(left.sort()).toEqual(["history", "settings", "storage", "subtitles", "video"])
    expect(client.getQueryState(["storage"])?.isInvalidated).toBe(true)
  })
})

describe("import helpers", () => {
  it("ไฟล์เกิน 1 MB ไม่ส่ง · รายงานใช้ detail เดียวกับ 413 ของ backend", () => {
    expect(importTooLarge({ size: 1_048_576 })).toBe(false)
    expect(importTooLarge({ size: 1_048_577 })).toBe(true)
    expect(TOO_LARGE_REQUEST).toEqual({
      code: "E_SETTINGS_INVALID",
      detail: "file larger than 1048576 bytes",
      context: "settings-import",
    })
  })

  it("ข้อความหลังนำเข้า: สำเร็จ / ใช้โฟลเดอร์ในไฟล์ไม่ได้", () => {
    expect(importNotice({ warnings: [] })).toEqual({ kind: "success", message: "นำเข้าค่าตั้งแล้ว" })
    expect(importNotice({ warnings: ["outputDir"] })).toEqual({ kind: "warning", message: th.general.importedKeptFolder })
  })
})
```

- [ ] **Step 2: Run them, expect FAIL**

Run: `cd "$WORKTREE/web" && npm run typecheck`
Expected: `tsc` fails (first errors: `src/pages/settings/local-data.test.ts(6,113): error TS2307: Cannot find module './local-data' or its corresponding type declarations.`; `src/pages/settings/local-data.test.ts(26,48): error TS7006: Parameter 'k' implicitly has an 'any' type.`).

- [ ] **Step 3: Implement**

In `web/src/pages/settings/general-panel.tsx`:

Replace (1):
```tsx
} from "./general-form"
```
with:
```tsx
} from "./general-form"
import { LocalDataSection } from "./local-data-section"
```

Replace (2):
```tsx
      />
    </FieldGroup>
```
with:
```tsx
      />

      {/* M6 รอบ A (PRD :307): ล้างข้อมูลชั่วคราว · สำรองค่าตั้ง · นำเข้าค่าตั้ง */}
      <LocalDataSection />
    </FieldGroup>
```

Create `web/src/pages/settings/local-data-section.tsx`:
```tsx
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { Download, Eraser, Upload } from "lucide-react"
import { useRef, useState, type ChangeEvent } from "react"
import { toast } from "sonner"

import { showErrorToast } from "@/components/error-report/error-toast"
import { PLAIN_TOAST } from "@/components/error-report/model"
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog"
import { Button } from "@/components/ui/button"
import { FieldLegend, FieldSet } from "@/components/ui/field"
import { Spinner } from "@/components/ui/spinner"
import { fill, th } from "@/i18n/th"
import { formatBytes } from "@/lib/format"
import { reportRequest } from "@/lib/report"
import { clearStorage, exportSettings, importSettings, SETTINGS_KEY, storageQuery } from "@/lib/settings-api"
import type { Settings } from "@/lib/types"

import { serverMessage } from "./general-form"
import {
  CLEAR_TOAST_ID,
  clearButton,
  EXPORT_TOAST_ID,
  forgetClipCaches,
  IMPORT_TOAST_ID,
  importNotice,
  importTooLarge,
  TOO_LARGE_REQUEST,
} from "./local-data"

const t = th.general

/**
 * "ข้อมูลในเครื่อง" ในแท็บทั่วไป (M6 รอบ A spec 5, PRD :307): ล้างข้อมูลชั่วคราว · สำรองค่าตั้ง · นำเข้าค่าตั้ง
 * ขนาดเป็นข้อมูลรอง: โหลดไม่ได้ = ปุ่มไม่มีขนาดและกดไม่ได้ ไม่แจ้ง error (แบบเดียวกับ "ล่าสุด" ใน W1)
 */
export function LocalDataSection() {
  const queryClient = useQueryClient()
  const usage = useQuery(storageQuery())
  const button = clearButton(usage.isSuccess ? usage.data : undefined)
  const [confirmOpen, setConfirmOpen] = useState(false)
  // ขนาดบนหัวกล่องยืนยัน = ขนาดบนปุ่มตอนกด (ไม่เปลี่ยนกลางทางเมื่อขนาดโหลดใหม่)
  const [confirmSize, setConfirmSize] = useState("")
  const fileInput = useRef<HTMLInputElement>(null)

  const clear = useMutation({
    mutationFn: () => clearStorage(),
    onSuccess: ({ freedBytes }) => {
      setConfirmOpen(false)
      // ...PLAIN_TOAST: id เดียวกับ toast error ของการล้าง ไม่ให้ปุ่มคัดลอก/เวลาค้างติดมา (M6 รอบ B P5)
      toast.success(fill(t.cleared, { size: formatBytes(freedBytes) }), { ...PLAIN_TOAST, id: CLEAR_TOAST_ID })
      forgetClipCaches(queryClient)
    },
    onError: (error) => {
      setConfirmOpen(false)
      void queryClient.invalidateQueries({ queryKey: storageQuery().queryKey })
      showErrorToast(serverMessage(error), {
        id: CLEAR_TOAST_ID,
        request: reportRequest(error, { context: "storage-clear" }),
      })
    },
  })

  const exporting = useMutation({
    mutationFn: () => exportSettings(),
    // สำเร็จไม่มี toast: เบราว์เซอร์แสดงการดาวน์โหลดเอง
    onError: (error) =>
      showErrorToast(error.message, { id: EXPORT_TOAST_ID, request: reportRequest(error, { context: "settings-export" }) }),
  })

  const importing = useMutation({
    mutationFn: (text: string) => importSettings(text),
    onSuccess: (result) => {
      // ธีมและค่าเริ่มต้นของการโหลดเปลี่ยนตามทันที
      queryClient.setQueryData<Settings>(SETTINGS_KEY, result.settings)
      const notice = importNotice(result)
      if (notice.kind === "warning") {
        // ต้องอ่าน: ค้างจนกดปิด (แบบ toast หลังลบบัญชี) ไม่มีปุ่มคัดลอก เพราะไม่มีอะไรพลาด
        toast.warning(notice.message, {
          ...PLAIN_TOAST,
          id: IMPORT_TOAST_ID,
          duration: Infinity,
          action: { label: th.common.close, onClick: () => undefined },
        })
      } else {
        toast.success(notice.message, { ...PLAIN_TOAST, id: IMPORT_TOAST_ID })
      }
    },
    onError: (error) =>
      showErrorToast(serverMessage(error), {
        id: IMPORT_TOAST_ID,
        request: reportRequest(error, { context: "settings-import" }),
      }),
  })

  async function onFile(event: ChangeEvent<HTMLInputElement>) {
    const input = event.currentTarget
    const file = input.files?.[0]
    input.value = "" // เลือกไฟล์เดิมซ้ำได้
    if (!file) return
    if (importTooLarge(file)) {
      showErrorToast(t.settingsInvalid, { id: IMPORT_TOAST_ID, request: TOO_LARGE_REQUEST })
      return
    }
    importing.mutate(await file.text())
  }

  return (
    <FieldSet>
      <FieldLegend>{t.localData}</FieldLegend>
      <div className="flex flex-wrap gap-2" data-testid="local-data-actions">
        <Button
          type="button"
          variant="secondary"
          disabled={button.disabled || clear.isPending}
          onClick={() => {
            setConfirmSize(button.size ?? "")
            setConfirmOpen(true)
          }}
        >
          <Eraser data-icon="inline-start" aria-hidden />
          {button.label}
        </Button>
        <Button type="button" variant="secondary" disabled={exporting.isPending} onClick={() => exporting.mutate()}>
          {exporting.isPending ? <Spinner data-icon="inline-start" /> : <Download data-icon="inline-start" aria-hidden />}
          {t.backup}
        </Button>
        <Button
          type="button"
          variant="secondary"
          disabled={importing.isPending}
          onClick={() => fileInput.current?.click()}
        >
          {importing.isPending ? <Spinner data-icon="inline-start" /> : <Upload data-icon="inline-start" aria-hidden />}
          {t.import}
        </Button>
        <input
          ref={fileInput}
          type="file"
          accept=".json,application/json"
          className="hidden"
          tabIndex={-1}
          aria-hidden
          onChange={(event) => void onFile(event)}
        />
      </div>
      <AlertDialog
        open={confirmOpen}
        onOpenChange={(next) => {
          if (!next && !clear.isPending) setConfirmOpen(false)
        }}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>{fill(t.clearConfirmTitle, { size: confirmSize })}</AlertDialogTitle>
            <AlertDialogDescription>{t.clearConfirmBody}</AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel disabled={clear.isPending}>{t.clearCancel}</AlertDialogCancel>
            <AlertDialogAction disabled={clear.isPending} onClick={() => clear.mutate()}>
              {clear.isPending && <Spinner />}
              {t.clearConfirm}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </FieldSet>
  )
}
```

Create `web/src/pages/settings/local-data.ts`:
```ts
import type { QueryClient } from "@tanstack/react-query"

import { fill, th } from "@/i18n/th"
import { formatBytes } from "@/lib/format"
import type { ReportRequest } from "@/lib/report"
import { MAX_SETTINGS_FILE_BYTES, STORAGE_KEY, type ImportResult, type StorageUsage } from "@/lib/settings-api"

/**
 * ตรรกะของส่วน "ข้อมูลในเครื่อง" (M6 รอบ A spec 3.3, 4.3, 5) แยกจาก JSX เพื่อเทสใน node ได้
 */

/** id คงที่ของ toast แต่ละแหล่ง (error ครั้งใหม่แทนที่ toast เดิม) */
export const CLEAR_TOAST_ID = "storage-clear"
export const IMPORT_TOAST_ID = "settings-import"
export const EXPORT_TOAST_ID = "settings-export"

/**
 * ข้อมูลของคลิปที่หายไปพร้อม data/cache หลังล้าง: ลบออกจากแคชของหน้าเว็บ เปิดคลิปเก่าแล้วโหลดใหม่ (spec 3.3)
 * ["video"], ["history"], ["subtitles"] (รายชื่อแทร็กจาก probe) และ ["settings"] ยังใช้ได้ จึงไม่แตะ
 */
export const CLIP_CACHE_KEYS = [["storyboard"], ["sharp"], ["captures"], ["subtokens"], ["pinned-comment"]] as const

export function forgetClipCaches(client: Pick<QueryClient, "removeQueries" | "invalidateQueries">): void {
  for (const queryKey of CLIP_CACHE_KEYS) client.removeQueries({ queryKey })
  void client.invalidateQueries({ queryKey: STORAGE_KEY })
}

export type ClearButton = { label: string; size: string | null; disabled: boolean }

/** ปุ่ม "ล้างข้อมูลชั่วคราว (<ขนาด>)" · ยังโหลดไม่เสร็จหรือโหลดไม่ได้ = ไม่มีขนาดและกดไม่ได้ (ข้อมูลรอง ไม่แจ้ง error) */
export function clearButton(usage: StorageUsage | undefined): ClearButton {
  if (!usage) return { label: th.general.clearTempPlain, size: null, disabled: true }
  const size = formatBytes(usage.reclaimableBytes)
  return { label: fill(th.general.clearTemp, { size }), size, disabled: usage.reclaimableBytes <= 0 }
}

/** ไฟล์ที่ใหญ่เกิน 1 MB ไม่ส่งไป backend เลย (backend ตอบ 413 แบบเดียวกัน) */
export function importTooLarge(file: Pick<Blob, "size">): boolean {
  return file.size > MAX_SETTINGS_FILE_BYTES
}

/** body ของรายงานแจ้งปัญหาเมื่อไฟล์ใหญ่เกิน (detail เดียวกับ 413 ของ backend) */
export const TOO_LARGE_REQUEST: ReportRequest = {
  code: "E_SETTINGS_INVALID",
  detail: `file larger than ${MAX_SETTINGS_FILE_BYTES} bytes`,
  context: IMPORT_TOAST_ID,
}

export type ImportNotice = { kind: "success" | "warning"; message: string }

/** นำเข้าสำเร็จ: ไม่มีคำเตือน = "นำเข้าค่าตั้งแล้ว" · ใช้โฟลเดอร์ในไฟล์ไม่ได้ = คำเตือนที่ค้างจนกดปิด (Pete Q2 = B, Q3) */
export function importNotice(result: Pick<ImportResult, "warnings">): ImportNotice {
  return result.warnings.includes("outputDir")
    ? { kind: "warning", message: th.general.importedKeptFolder }
    : { kind: "success", message: th.general.imported }
}
```

Notes for the implementer:
- Every toast in this section has a fixed id (`storage-clear`, `settings-import`, `settings-export`); non-error toasts spread `PLAIN_TOAST` first (M6-B P5). The kept-folder warning stays until "ปิด" (P13).
- The size in the dialog title is the size on the button when it was pressed (`confirmSize`), so a refetch does not change the question mid-dialog.
- The file input is reset after each pick so the same file can be imported again; a file over 1 MB is never sent.

- [ ] **Step 4: Run the tests, expect PASS**

Run: `cd "$WORKTREE/web" && npm run typecheck && npm run lint && npm test`
Expected: typecheck clean, lint clean, vitest `1064 passed (1064)`.

- [ ] **Step 5: Commit**
```bash
cd "$WORKTREE" && git add web/src/pages/settings/local-data.ts web/src/pages/settings/local-data.test.ts web/src/pages/settings/local-data-section.tsx web/src/pages/settings/general-panel.tsx && git commit -F- <<'EOF'
feat(web): local data section in Settings - clear temporary data, back up and import settings

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
EOF
```

---

## Wave 3

### Task 11: The leftover sweep finds styled names (spec 2.7)

**Files:**
- Modify: `src/yttoolkit/lifecycle.py`, `tests/unit/test_lifecycle.py`

**Interfaces:**
- Consumes: T2 `Job.filename_style`, `JobStore.channel_of`; T1 `files.CHANNEL_SEP`, `files.safe_component`; T7's `lifecycle.py` (startup sweep, kept); `_prefixes`, `_sweep_folder`, `_clip_folders`.
- Produces: `toolkit_name_pattern(prefix, *, style="title", uploader="")` (`title` = today's pattern unchanged); `sweep_interrupted_outputs` passes each job's style and channel (P7).

- [ ] **Step 1: Write the failing tests**

In `tests/unit/test_lifecycle.py`:

Append at the end of the file:
```python



# ---------- M6 รอบ A: ไฟล์ค้างของงานที่ตั้งชื่อแบบ title-channel / title-quality (spec 2.7) ----------

CHANNEL = "Blender Studio"


@pytest.mark.parametrize(
    ("name", "ours"),
    [
        (f"{TITLE} - {CHANNEL}.mp4", True),
        (f"{TITLE} - {CHANNEL} (2).mp4", True),
        (f"{TITLE} - {CHANNEL} (ไม่มีเสียง).mp4", True),
        (f"{TITLE} - {CHANNEL} - contact sheet.jpg", True),
        (f"{TITLE} - {CHANNEL}.th.srt", True),
        (f"{TITLE} - {CHANNEL}.note.md", True),
        ("Big Bu - Blen (01.30-05.00).mp4.part", True),  # ตัดทั้งชื่อคลิปและชื่อช่อง
        (f"{TITLE}.mp4", True),  # ชื่อช่องถูกทิ้งเมื่อยาวเกิน
        (f"{TITLE} - notes.mp4", False),
        (f"{TITLE} - {CHANNEL} notes.docx", False),
        (f"{TITLE} (1080p).mp4", False),
    ],
)
def test_title_channel_pattern(name, ours):
    assert bool(lifecycle.toolkit_name_pattern(TITLE, style="title-channel", uploader=CHANNEL).fullmatch(name)) is ours


@pytest.mark.parametrize(
    ("name", "ours"),
    [
        (f"{TITLE} (1080p).mp4", True),
        (f"{TITLE} (2160p) (2).mp4", True),
        (f"{TITLE} (720p) (ไม่มีเสียง).mp4", True),
        (f"{TITLE} (mp3 192k).mp3", True),
        (f"{TITLE} (m4a 128k).m4a.part", True),
        (f"{TITLE} (m4a).m4a", True),
        (f"{TITLE} (wav).wav", True),
        ("Big (1080p) (01.30-05.00).mp4", True),  # ชื่อถูกตัดเพราะส่วนท้ายยาว
        (f"{TITLE}.mp4", True),  # ไม่รู้คุณภาพ = ไม่มีส่วนคุณภาพ
        (f"{TITLE}.th.srt", True),
        (f"{TITLE} - contact sheet.jpg", True),
        (f"{TITLE} (1080).mp4", False),
        (f"{TITLE} (flac 900k).mp3", False),
        (f"{TITLE} - {CHANNEL}.mp4", False),
    ],
)
def test_title_quality_pattern(name, ours):
    assert bool(lifecycle.toolkit_name_pattern(TITLE, style="title-quality").fullmatch(name)) is ours


def test_title_pattern_ignores_the_uploader():
    plain = lifecycle.toolkit_name_pattern(TITLE)
    assert lifecycle.toolkit_name_pattern(TITLE, style="title", uploader=CHANNEL).pattern == plain.pattern
    assert lifecycle.toolkit_name_pattern(TITLE, style="title-channel", uploader="").fullmatch(f"{TITLE}.mp4")
    with pytest.raises(ValueError):
        lifecycle.toolkit_name_pattern(TITLE, style="channel")


def _styled_sweep_env(paths, style: str):
    db = Database(paths.db)
    db.migrate()
    db.execute(
        "INSERT INTO videos (video_id, title, channel, probe_json, probed_at, opened_at) VALUES (?, ?, ?, '{}', 'x', 'x')",
        ("aqz-KE-bpKQ", TITLE, CHANNEL),
    )
    store = JobStore(db)
    root = (paths.data_root / "output").resolve()
    folder = files.plan_output(root, TITLE, "aqz-KE-bpKQ", "", "mp4").parent
    folder.mkdir(parents=True)
    done, stopped = store.add([NewJob("aqz-KE-bpKQ", "video", {}, TITLE), NewJob("aqz-KE-bpKQ", "video", {}, TITLE)])
    store.transition(done.id, "running", filename_style=style)
    done_name = f"{TITLE} - {CHANNEL} (2).mp4" if style == "title-channel" else f"{TITLE} (1080p) (2).mp4"
    (folder / done_name).write_bytes(b"")  # ไฟล์ผลลัพธ์ของงานที่เสร็จ (ว่างจริง) ห้ามลบ
    store.transition(done.id, "done", outputs=(OutputFile(str(root), f"{folder.name}/{done_name}", 0, "video"),))
    store.transition(stopped.id, "running", filename_style=style)
    return db, store, root, folder, done_name


def test_sweep_removes_leftovers_of_a_title_channel_job(paths):
    db, store, root, folder, done_name = _styled_sweep_env(paths, "title-channel")
    try:
        leftovers = [f"{TITLE} - {CHANNEL}.mp4", "Big Bu - Blen (01.30-05.00).mp4.part", f"{TITLE} - {CHANNEL}.th.srt"]
        for name in leftovers:
            (folder / name).write_bytes(b"" if not name.endswith(".part") else b"half")
        kept = {done_name: b"", f"{TITLE} - notes.mp4": b"user file", f"{TITLE} - {CHANNEL} (3).mp4": b"real video"}
        for name, data in kept.items():
            if not (folder / name).exists():
                (folder / name).write_bytes(data)
        stranded = [job.id for job in store.running()]
        store.interrupt_running("หยุดกลางคัน")
        assert lifecycle.sweep_interrupted_outputs(store, paths.data_root / "output", stranded) == 3
        assert sorted(p.name for p in folder.iterdir()) == sorted(kept)
    finally:
        db.close()


def test_sweep_removes_leftovers_of_a_title_quality_job(paths):
    db, store, root, folder, done_name = _styled_sweep_env(paths, "title-quality")
    try:
        for name in (f"{TITLE} (1080p).mp4", f"{TITLE} (mp3 192k).mp3", f"{TITLE} (m4a 128k).m4a.part"):
            (folder / name).write_bytes(b"")
        kept = {done_name: b"", f"{TITLE} (1080p) notes.docx": b""}
        for name, data in kept.items():
            if not (folder / name).exists():
                (folder / name).write_bytes(data)
        stranded = [job.id for job in store.running()]
        store.interrupt_running("หยุดกลางคัน")
        assert lifecycle.sweep_interrupted_outputs(store, paths.data_root / "output", stranded) == 3
        assert sorted(p.name for p in folder.iterdir()) == sorted(kept)
    finally:
        db.close()


def test_two_jobs_of_one_clip_with_different_styles_are_both_swept(paths):
    db, store, root, folder, done_name = _styled_sweep_env(paths, "title-channel")
    try:
        (other,) = store.add([NewJob("aqz-KE-bpKQ", "audio", {"format": "mp3"}, TITLE)])
        store.transition(other.id, "running", filename_style="title-quality")
        (folder / f"{TITLE} - {CHANNEL}.mp4").write_bytes(b"")
        (folder / f"{TITLE} (mp3 192k).mp3").write_bytes(b"")
        stranded = [job.id for job in store.running()]
        store.interrupt_running("หยุดกลางคัน")
        assert lifecycle.sweep_interrupted_outputs(store, paths.data_root / "output", stranded) == 2
        assert sorted(p.name for p in folder.iterdir()) == [done_name]
    finally:
        db.close()


def test_a_job_from_before_m6_is_swept_with_the_title_pattern(paths):
    db, store, root, folder, done_name = _styled_sweep_env(paths, "title")
    try:
        db.execute("UPDATE jobs SET filename_style = NULL")
        (folder / f"{TITLE}.mp4").write_bytes(b"")
        (folder / f"{TITLE} - {CHANNEL}.mp4").write_bytes(b"")  # ไม่ใช่ชื่อแบบ title: ไม่แตะ
        stranded = [job.id for job in store.running()]
        store.interrupt_running("หยุดกลางคัน")
        assert lifecycle.sweep_interrupted_outputs(store, paths.data_root / "output", stranded) == 1
        assert (folder / f"{TITLE} - {CHANNEL}.mp4").exists()
    finally:
        db.close()
```

- [ ] **Step 2: Run them, expect FAIL**

Run: `cd "$WORKTREE" && uv run pytest tests/unit/test_lifecycle.py -q -W error -p no:cacheprovider`
Expected: `29 failed, 192 passed` — `unit/test_lifecycle.py::test_title_channel_pattern` (×11), `unit/test_lifecycle.py::test_title_quality_pattern` (×14), `unit/test_lifecycle.py::test_title_pattern_ignores_the_uploader`, `unit/test_lifecycle.py::test_sweep_removes_leftovers_of_a_title_channel_job`, `unit/test_lifecycle.py::test_sweep_removes_leftovers_of_a_title_quality_job`, `unit/test_lifecycle.py::test_two_jobs_of_one_clip_with_different_styles_are_both_swept`.

- [ ] **Step 3: Implement in `src/yttoolkit/lifecycle.py`**

In `src/yttoolkit/lifecycle.py`:

Replace (1):
```python
_UNIQUE = r"(?: \((?:[2-9]|[1-9][0-9])\))?"  # " (2)" ... " (99)" จาก files._candidates
```
with:
```python
_UNIQUE = r"(?: \((?:[2-9]|[1-9][0-9])\))?"  # " (2)" ... " (99)" จาก files._candidates
# M6 รอบ A: ส่วนคุณภาพของแบบ title-quality (handlers._video_quality / _audio_quality) "(1080p)" "(mp3 192k)" "(m4a)" "(wav)"
_QUALITY_PART = r"(?: \((?:\d{3,4}p|(?:mp3|m4a) \d{2,3}k|m4a|wav)\))?"
```

Replace (2):
```python
    seen: set[Path] = set()
    removed = 0
    for job in jobs.values():
        for folder, prefix in _clip_folders(root, job.video_id, job.title, job_group(job.params)):
            if folder not in seen:
                seen.add(folder)
                removed += _sweep_folder(folder, toolkit_name_pattern(prefix), keep)
```
with:
```python
    seen: set[tuple[Path, str, str]] = set()
    seen_dirs: set[Path] = set()
    removed = 0
    for job in jobs.values():
        # M6 รอบ A: ชื่อไฟล์ตามรูปแบบที่งานตั้งไว้ตอนเริ่ม (NULL = งานก่อน M6 = title) · ชื่อช่องจากตาราง videos
        style = job.filename_style or "title"
        uploader = store.channel_of(job.video_id) if style == "title-channel" else ""
        for folder, prefix in _clip_folders(root, job.video_id, job.title, job_group(job.params)):
            # สองงานของคลิปเดียวกันคนละรูปแบบ = ดูโฟลเดอร์เดียวกันด้วยทั้งสองรูปแบบ
            if (folder, style, uploader) not in seen:
                seen.add((folder, style, uploader))
                removed += _sweep_folder(folder, toolkit_name_pattern(prefix, style=style, uploader=uploader), keep)
            if folder not in seen_dirs:
                seen_dirs.add(folder)
```

Replace (3):
```python
def toolkit_name_pattern(prefix: str) -> re.Pattern[str]:
```
with:
```python
def toolkit_name_pattern(prefix: str, *, style: str = "title", uploader: str = "") -> re.Pattern[str]:
```

Replace (4):
```python
    ชื่ออื่น (เช่นไฟล์ของผู้ใช้ "<ชื่อ> notes.docx") ไม่ตรง จึงไม่ถูกลบ"""
    name = re.escape(prefix)
    shrunk = _prefixes(prefix)
```
with:
```python
    ชื่ออื่น (เช่นไฟล์ของผู้ใช้ "<ชื่อ> notes.docx") ไม่ตรง จึงไม่ถูกลบ
    M6 รอบ A (spec 2.7): style = รูปแบบของงาน · title = แบบเดิมทุกตัวอักษร
    title-channel: ส่วนชื่อ = <ชื่อ (ตัดสั้นได้)>[ - <ช่อง (ตัดสั้นได้)>] ทุกแบบ (ชื่อไฟล์ยาวเกินตัดได้ทั้งสองส่วน)
    title-quality: สื่อ/ที่ตัดช่วง มี "(1080p)" "(mp3 192k)" "(m4a 128k)" "(m4a)" "(wav)" ต่อชื่อ (ตัดสั้นได้) ได้ · ซับเหมือน title
    """
    if style == "title":
        name = re.escape(prefix)
        shrunk = _prefixes(prefix)
        quality = ""
    elif style == "title-channel":
        channel = files.safe_component(uploader, "")
        name = _prefixes(prefix) + (rf"(?:{re.escape(files.CHANNEL_SEP)}{_prefixes(channel)})?" if channel else "")
        shrunk = name
        quality = ""
    elif style == "title-quality":
        name = re.escape(prefix)
        shrunk = _prefixes(prefix)
        quality = _QUALITY_PART
    else:
        raise ValueError(f"unknown filename style: {style!r}")
```

Replace (5):
```python
    media = rf"{name}(?:{suffixes})?{_UNIQUE}\.(?:{exts})"
    cut = rf"{shrunk}(?:{no_audio})?(?:{_RANGE_SUFFIX}(?:{ads})?|{ads}){_UNIQUE}\.(?:{exts})"
```
with:
```python
    media_name = rf"{shrunk}{quality}" if quality else name
    media = rf"{media_name}(?:{suffixes})?{_UNIQUE}\.(?:{exts})"
    cut = rf"{shrunk}{quality}(?:{no_audio})?(?:{_RANGE_SUFFIX}(?:{ads})?|{ads}){_UNIQUE}\.(?:{exts})"
```

Notes for the implementer:
- The safety rules are unchanged: only 0-byte reservations and `.part` files, never a `done` output (`keep`), only inside the clip folder, symlinks skipped.
- The existing parametrised pattern tests (`test_toolkit_name_pattern_matches_only_names_the_handlers_write`, `..._covers_note_outputs`, `..._covers_m5a_names`) must keep passing unchanged: `style="title"` builds exactly today's regex.

- [ ] **Step 4: Run the tests, expect PASS**

Run: the Step 2 command. Expected: `221 passed`. Then the full suite (all pass).

- [ ] **Step 5: Commit**
```bash
cd "$WORKTREE" && git add src/yttoolkit/lifecycle.py tests/unit/test_lifecycle.py && git commit -F- <<'EOF'
feat(lifecycle): sweep interrupted outputs named with the job's filename style

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
EOF
```


### Task 12: The filename-style field and its live example in the General tab (spec 2.6; AC-OUT-10)

**Files:**
- Create: `web/src/pages/settings/filename-example.ts`, `web/src/pages/settings/filename-example.test.ts`, `web/src/pages/settings/filename-style-field.tsx`, `web/src/pages/settings/choice-select.tsx`
- Modify: `web/src/pages/settings/general-form.ts`, `web/src/pages/settings/general-form.test.ts`, `web/src/pages/settings/general-panel.tsx`

**Interfaces:**
- Consumes: T8 `planNames`, `PathTooLongError`, `FILENAME_STYLES`, `FilenameStyle`, `NameInput`; T4 `recentQuery`, `th.general.filename*`; T10's `general-panel.tsx` (the section stays last); `choicePatch`, `displayed`.
- Produces: K8 `exampleFileName`, `SAMPLE_CLIP_ID`, `ExampleClip`, `FilenameStyleField`, `ChoiceSelect` (moved, P11); `GeneralKey` gains `"filenameStyle"`; `general-form.ts` re-exports `FILENAME_STYLES` (P4); DOM ids `general-filename`, `general-filename-example` that T14 checks.

- [ ] **Step 1: Write the failing tests**

Create `web/src/pages/settings/filename-example.test.ts`:
```ts
import { describe, expect, it } from "vitest"

import { exampleFileName, SAMPLE_CLIP_ID } from "./filename-example"

const DIR = "C:\\Users\\somchai\\Downloads\\YT-Toolkit"
const CLIP = { title: 'ทดสอบ: "A/B" <ภาค 1>?', channel: "ช่อง/ทดสอบ", videoId: "aqz-KE-bpKQ" }

describe("exampleFileName", () => {
  it("ยังไม่เคยเปิดคลิป: ใช้ชื่อตัวอย่างภาษาไทย ทั้งสามรูปแบบ", () => {
    expect(exampleFileName("title", undefined, DIR)).toBe("สอนทำกับข้าวง่าย ๆ ใน 10 นาที.mp4")
    expect(exampleFileName("title-channel", undefined, DIR)).toBe("สอนทำกับข้าวง่าย ๆ ใน 10 นาที - ครัวบ้านเรา.mp4")
    expect(exampleFileName("title-quality", undefined, DIR)).toBe("สอนทำกับข้าวง่าย ๆ ใน 10 นาที (1080p).mp4")
    expect(SAMPLE_CLIP_ID).toHaveLength(11)
  })

  it("มีคลิปที่เปิดล่าสุด: ใช้ชื่อและช่องของคลิปนั้นตามกฎชื่อไฟล์ของ backend", () => {
    expect(exampleFileName("title", CLIP, DIR)).toBe("ทดสอบ AB ภาค 1.mp4")
    expect(exampleFileName("title-channel", CLIP, DIR)).toBe("ทดสอบ AB ภาค 1 - ช่องทดสอบ.mp4")
    expect(exampleFileName("title-quality", CLIP, DIR)).toBe("ทดสอบ AB ภาค 1 (1080p).mp4")
  })

  it("คลิปไม่รู้ชื่อช่อง: แบบ title-channel ได้ชื่อคลิปอย่างเดียว (เหมือนไฟล์จริง)", () => {
    expect(exampleFileName("title-channel", { ...CLIP, channel: "" }, DIR)).toBe("ทดสอบ AB ภาค 1.mp4")
  })

  it("ชื่อยาว 300 ตัว: ตัดตามงบ path ส่วนคุณภาพและนามสกุลอยู่ครบ", () => {
    const long = { title: "ก".repeat(300), channel: "ครัวบ้านเรา", videoId: "aqz-KE-bpKQ" }
    const name = exampleFileName("title-quality", long, DIR)
    expect(name.endsWith(" (1080p).mp4")).toBe(true)
    expect(name.length).toBeLessThan(120)
  })

  it("โฟลเดอร์ผลลัพธ์ยาวจน path เกิน: ยังแสดงรูปแบบได้ (คิดเหมือนโฟลเดอร์สั้น)", () => {
    expect(exampleFileName("title-channel", undefined, "D:\\" + "x".repeat(250))).toBe(
      "สอนทำกับข้าวง่าย ๆ ใน 10 นาที - ครัวบ้านเรา.mp4"
    )
  })
})
```

In `web/src/pages/settings/general-form.test.ts`:

Replace (1):
```ts
import { CAPTURE_QUALITIES, choicePatch, displayed, languageOptions, outputDirPatch, serverMessage } from "./general-form"
```
with:
```ts
import {
  CAPTURE_QUALITIES,
  choicePatch,
  displayed,
  FILENAME_STYLES,
  languageOptions,
  outputDirPatch,
  serverMessage,
} from "./general-form"
```

Replace (2):
```ts
    expect(outputDirPatch("abc", SAVED.outputDir)).toEqual({ outputDir: "abc" })
```
with:
```ts
    expect(outputDirPatch("abc", SAVED.outputDir)).toEqual({ outputDir: "abc" })
  })
})

describe("M6 รอบ A: รูปแบบชื่อไฟล์", () => {
  it("สามแบบตามลำดับ BRD FR-OUT-8 มีป้ายไทยครบ", () => {
    expect(FILENAME_STYLES).toEqual(["title", "title-channel", "title-quality"])
    expect(FILENAME_STYLES.map((s) => th.general.filenameStyles[s])).toEqual([
      "ชื่อคลิป",
      "ชื่อคลิป - ช่อง",
      "ชื่อคลิป (คุณภาพ)",
    ])
  })

  it("choicePatch ส่งเฉพาะ filenameStyle เมื่อเปลี่ยน · เท่าเดิม = null", () => {
    expect(choicePatch("filenameStyle", "title-channel", SAVED)).toEqual({ filenameStyle: "title-channel" })
    expect(choicePatch("filenameStyle", "title", SAVED)).toBeNull()
  })

  it("ระหว่างรอบันทึก ค่าที่แสดง (และบรรทัดตัวอย่าง) เป็นค่าที่เพิ่งเลือก", () => {
    expect(displayed(SAVED, { filenameStyle: "title-quality" }).filenameStyle).toBe("title-quality")
```

- [ ] **Step 2: Run them, expect FAIL**

Run: `cd "$WORKTREE/web" && npm run typecheck`
Expected: `tsc` fails (first errors: `src/pages/settings/filename-example.test.ts(3,49): error TS2307: Cannot find module './filename-example' or its corresponding type declarations.`; `src/pages/settings/general-form.test.ts(12,3): error TS2305: Module '"./general-form"' has no exported member 'FILENAME_STYLES'.`; `src/pages/settings/general-form.test.ts(56,33): error TS7006: Parameter 's' implicitly has an 'any' type.`; `src/pages/settings/general-form.test.ts(56,39): error TS7053: Element implicitly has an 'any' type because expression of type 'any' can't be used to index type '{ readonly title: "ชื่อคลิป"; readonly "title-channel": "ชื่อคลิป - ช่อง"; readonly "title-quality": "ชื่อคลิป (คุณภาพ)"; }'.`; `src/pages/settings/general-form.test.ts(64,24): error TS2345: Argument of type '"filenameStyle"' is not assignable to parameter of type '"videoDefault" | "audioDefault" | "audioLanguage" | "concurrency" | "autoSharpFrames" | "captureQuality"'.`).

- [ ] **Step 3: Implement**

Create `web/src/pages/settings/choice-select.tsx`:
```tsx
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"

type ChoiceSelectProps = {
  labelId: string
  hintId?: string
  value: string
  options: { value: string; label: string }[]
  onChange: (value: string) => void
}

/** ช่องเลือกจากรายการของแท็บทั่วไป (ย้ายออกจาก general-panel.tsx ใน M6 รอบ A ให้ช่องรูปแบบชื่อไฟล์ใช้ร่วม) */
export function ChoiceSelect({ labelId, hintId, value, options, onChange }: ChoiceSelectProps) {
  const labels = new Map(options.map((o) => [o.value, o.label]))
  return (
    <Select<string> value={value} onValueChange={(next) => next && onChange(next)}>
      <SelectTrigger aria-labelledby={labelId} aria-describedby={hintId} className="w-full min-w-0 sm:w-72">
        <SelectValue>{(current: string | null) => (current ? (labels.get(current) ?? current) : "")}</SelectValue>
      </SelectTrigger>
      <SelectContent alignItemWithTrigger={false} align="start">
        {options.map((o) => (
          <SelectItem key={o.value} value={o.value}>
            {o.label}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  )
}
```

Create `web/src/pages/settings/filename-example.ts`:
```ts
import { th } from "@/i18n/th"
import { PathTooLongError, planNames, type FilenameStyle, type NameInput } from "@/lib/filename"

/** รหัสคลิปของชื่อตัวอย่าง (เครื่องที่ยังไม่เคยเปิดคลิป) 11 ตัวเท่ารหัสยูทูป จึงกินความยาวเท่าคลิปจริง */
export const SAMPLE_CLIP_ID = "abcdefghijk"

export type ExampleClip = { title: string; channel: string; videoId: string }

/**
 * ชื่อไฟล์ตัวอย่างของบรรทัด "ตัวอย่าง: …" (M6 รอบ A spec 2.6, AC-OUT-10) คำนวณในหน้าเว็บ ไม่เรียก API
 * ใช้คลิปที่เปิดล่าสุด ไม่มี = ชื่อตัวอย่างภาษาไทย (Pete Q1 = B) · เป็นไฟล์วิดีโอ 1080p เสมอ (PRD: "<ชื่อไฟล์>.mp4")
 * โฟลเดอร์ผลลัพธ์ยาวจนชื่อไม่พอ = คิดเหมือนโฟลเดอร์สั้น (ตัวอย่างต้องอ่านรูปแบบออก ไม่ใช่ชื่อรหัสคลิป)
 */
export function exampleFileName(style: FilenameStyle, clip: ExampleClip | undefined, outputDir: string): string {
  const source = clip ?? { title: th.general.filenameSample, channel: th.general.filenameSampleChannel, videoId: SAMPLE_CLIP_ID }
  const input: Omit<NameInput, "baseLen"> = {
    title: source.title,
    clipId: source.videoId,
    uploader: source.channel,
    style,
    quality: "1080p",
    suffix: "",
    ext: "mp4",
  }
  try {
    return planNames({ ...input, baseLen: outputDir.length }).file
  } catch (error) {
    if (!(error instanceof PathTooLongError)) throw error
    return planNames({ ...input, baseLen: 0 }).file
  }
}
```

Create `web/src/pages/settings/filename-style-field.tsx`:
```tsx
import { useQuery } from "@tanstack/react-query"

import { Field, FieldDescription, FieldTitle } from "@/components/ui/field"
import { fill, th } from "@/i18n/th"
import { FILENAME_STYLES, type FilenameStyle } from "@/lib/filename"
import { recentQuery } from "@/pages/history/queries"

import { ChoiceSelect } from "./choice-select"
import { exampleFileName } from "./filename-example"

const t = th.general

type Props = {
  /** ค่าที่แสดงอยู่ (ระหว่างรอบันทึก = ค่าที่เพิ่งเลือก บรรทัดตัวอย่างจึงเปลี่ยนทันที) */
  value: FilenameStyle
  outputDir: string
  onChange: (value: FilenameStyle) => void
}

/**
 * รูปแบบชื่อไฟล์ + บรรทัด "ตัวอย่าง: …" (M6 รอบ A spec 2.6, PRD :306, AC-OUT-10)
 * ตัวอย่างคำนวณในหน้าเว็บจากคลิปที่เปิดล่าสุด (คีย์เดียวกับ "ล่าสุด" ใน W1 ใช้ cache ร่วม) เปลี่ยนรูปแบบแล้วไม่เรียก API
 * โหลดคลิปล่าสุดไม่ได้หรือยังไม่เคยเปิดคลิป = ชื่อตัวอย่างภาษาไทย
 */
export function FilenameStyleField({ value, outputDir, onChange }: Props) {
  const recent = useQuery(recentQuery())
  const latest = recent.data?.items[0]
  const name = exampleFileName(value, latest, outputDir)
  return (
    <Field>
      <FieldTitle id="general-filename">{t.filenameStyle}</FieldTitle>
      <ChoiceSelect
        labelId="general-filename"
        hintId="general-filename-example"
        value={value}
        options={FILENAME_STYLES.map((style) => ({ value: style, label: t.filenameStyles[style] }))}
        onChange={(next) => {
          const style = FILENAME_STYLES.find((s) => s === next)
          if (style) onChange(style)
        }}
      />
      <FieldDescription id="general-filename-example" className="font-mono break-all">
        {fill(t.filenameExample, { name })}
      </FieldDescription>
    </Field>
  )
}
```

In `web/src/pages/settings/general-form.ts`:

Replace (1):
```ts
/** ค่าที่หน้า "ทั่วไป" แก้ได้ (ทั้งเจ็ดช่อง) */
```
with:
```ts
/** ค่าที่หน้า "ทั่วไป" แก้ได้ (ทั้งแปดช่อง) */
```

Replace (2):
```ts
export type GeneralPatch = Partial<Pick<Settings, GeneralKey>>
```
with:
```ts
  | "filenameStyle"
export type GeneralPatch = Partial<Pick<Settings, GeneralKey>>

/** M6 รอบ A: รูปแบบชื่อไฟล์ เรียงตามที่แสดง (ตัวเดียวกับ lib/filename.ts = files.NAME_STYLES ของ backend) */
export { FILENAME_STYLES } from "@/lib/filename"
```

In `web/src/pages/settings/general-panel.tsx`:

Replace (1):
```tsx
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
```
with:
```tsx

```

Replace (2):
```tsx
import { SwitchRow } from "@/pages/video/advanced/switch-row"

import {
```
with:
```tsx
import { SwitchRow } from "@/pages/video/advanced/switch-row"

import { ChoiceSelect } from "./choice-select"
import { FilenameStyleField } from "./filename-style-field"
import {
```

Replace (3):
```tsx
        {Array.from({ length: 7 }, (_, i) => (
```
with:
```tsx
        {Array.from({ length: 8 }, (_, i) => (
```

Replace (4):
```tsx
        opening={open.isPending}
```
with:
```tsx
        opening={open.isPending}
      />

      {/* M6 รอบ A (PRD :306, FR-OUT-8): รูปแบบชื่อไฟล์ + ตัวอย่างที่เปลี่ยนทันทีเมื่อเลือก */}
      <FilenameStyleField
        value={shown.filenameStyle}
        outputDir={settings.data.outputDir}
        onChange={(value) => choose(choicePatch("filenameStyle", value, shown))}
```

Replace (5):
```tsx
type ChoiceSelectProps = {
  labelId: string
  hintId?: string
  value: string
  options: { value: string; label: string }[]
  onChange: (value: string) => void
}

function ChoiceSelect({ labelId, hintId, value, options, onChange }: ChoiceSelectProps) {
  const labels = new Map(options.map((o) => [o.value, o.label]))
  return (
    <Select<string> value={value} onValueChange={(next) => next && onChange(next)}>
      <SelectTrigger aria-labelledby={labelId} aria-describedby={hintId} className="w-full min-w-0 sm:w-72">
        <SelectValue>{(current: string | null) => (current ? (labels.get(current) ?? current) : "")}</SelectValue>
      </SelectTrigger>
      <SelectContent alignItemWithTrigger={false} align="start">
        {options.map((o) => (
          <SelectItem key={o.value} value={o.value}>
            {o.label}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  )
}

```
with:
```tsx

```

Notes for the implementer:
- The example is computed from `shown.filenameStyle` (the value being saved), so it changes on select before the PATCH returns, and it makes **no** request: `recentQuery()` shares W1's cache key (AC-OUT-10).
- The example is always the video form with `1080p` (PRD: "ตัวอย่าง: <ชื่อไฟล์>.mp4"); `font-mono break-all` keeps a 300-character name inside 640 px.

- [ ] **Step 4: Run the tests, expect PASS**

Run: `cd "$WORKTREE/web" && npm run typecheck && npm run lint && npm test`
Expected: typecheck clean, lint clean, vitest `1150 passed (1150)`.

- [ ] **Step 5: Commit**
```bash
cd "$WORKTREE" && git add web/src/pages/settings/filename-example.ts web/src/pages/settings/filename-example.test.ts web/src/pages/settings/filename-style-field.tsx web/src/pages/settings/choice-select.tsx web/src/pages/settings/general-form.ts web/src/pages/settings/general-form.test.ts web/src/pages/settings/general-panel.tsx && git commit -F- <<'EOF'
feat(web): filename style field with a live example computed in the browser

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
EOF
```


### Task 13: The privacy canary covers the settings file and the storage routes (spec 7.3; C4, C5)

**Files:**
- Modify: `tests/integration/test_account_privacy.py`

**Interfaces:**
- Consumes: T6 `GET /api/settings/export`; T7 `GET /api/storage`, `POST /api/storage/clear` (the real app from `lifecycle.open_services` + `create_app`, with `cache_root` set).
- Produces: nothing new; the existing file walk at the end now runs after a clear.

- [ ] **Step 1: Extend the canary test**

In `tests/integration/test_account_privacy.py`:

Replace (1):
```python
ผ่านเงื่อนไขเดียวกัน ไม่มีชื่อคุกกี้เลย และพูดถึงบัญชีแค่บรรทัดสถานะ
```
with:
```python
ผ่านเงื่อนไขเดียวกัน ไม่มีชื่อคุกกี้เลย และพูดถึงบัญชีแค่บรรทัดสถานะ
(M6 รอบ A spec 7.3) ไฟล์สำรองค่าตั้ง GET /api/settings/export และ GET /api/storage · POST /api/storage/clear
ตอนถือบัญชีอยู่ ผ่านเงื่อนไขเดียวกัน (การล้างต้องไม่เขียนข้อมูลคุกกี้ลงที่ใด ตรวจด้วยการเดินไฟล์ท้ายเทส)
```

Replace (2):
```python
    assert "- รหัส: E_VIDEO_PRIVATE · งาน: video (videoId PRIVATEVID1)" in reports[0]
```
with:
```python
    assert "- รหัส: E_VIDEO_PRIVATE · งาน: video (videoId PRIVATEVID1)" in reports[0]
    # M6 รอบ A (spec 7.3): ไฟล์สำรองค่าตั้ง และขนาด/ล้างข้อมูลชั่วคราว ตอนถือบัญชีอยู่ ไม่มีคุกกี้ ชื่อคุกกี้ หรือ token
    exported = client.get("/api/settings/export")
    bodies.append(exported.text)
    assert exported.status_code == 200 and exported.json()["app"] == "yt-toolkit"
    for name in ("SAPISID", "__Secure-3PSID", "LOGIN_INFO", CANARIES[3], TOKEN, "cookies"):
        assert name not in exported.text, f"{name} อยู่ในไฟล์สำรองค่าตั้ง"
    assert set(call("GET", "/api/storage")) == {"cacheBytes", "workBytes", "reclaimableBytes"}
    assert set(call("POST", "/api/storage/clear", headers=AUTH)) == {"freedBytes"}
```

- [ ] **Step 2: Run it, expect PASS** (the guarded code exists after gate 2; this task only adds the checks)

Run: `cd "$WORKTREE" && uv run pytest tests/integration/test_account_privacy.py -q -W error -p no:cacheprovider`
Expected: `1 passed`. Then the full suite (all pass).

- [ ] **Step 3: Commit**
```bash
cd "$WORKTREE" && git add tests/integration/test_account_privacy.py && git commit -F- <<'EOF'
test(privacy): the canary covers the settings export and the storage routes

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
EOF
```


### Task 14: Chromium e2e — paste, the filename example, the local data section (spec 7.4)

**Files:**
- Create: `web/e2e/home-paste.spec.ts`, `web/e2e/settings-local-data.spec.ts`
- Modify: `web/e2e/settings-general.spec.ts` (P24)

**Interfaces:**
- Consumes: labels and ids from T4 (copy), T9 (`paste-hint`, button "วาง"), T10 (group "ข้อมูลในเครื่อง", buttons, `alertdialog`, file input), T12 (combobox "รูปแบบชื่อไฟล์", `#general-filename-example`); `e2e/axe-settled.ts` `analyzeSettled`.
- Produces: nothing; chromium project only, every write mocked (P15, P16).

- [ ] **Step 1: Write the specs**

Create `web/e2e/home-paste.spec.ts`:
```ts
import { analyzeSettled } from "./axe-settled"
import { expect, test, type Page } from "@playwright/test"

// M6 รอบ A ปุ่ม "วาง" ใน W1 (spec 1, AC-IN-08 / AC-IN-09) · project chromium: ไม่สร้างงาน /api/resolve ถูก mock
// navigator.clipboard.readText ถูกแทนด้วย addInitScript (คลิปบอร์ดของเครื่องใช้ร่วมกันทุก worker ที่รันขนานกัน
// จึงไม่ใช้คลิปบอร์ดจริงเป็นข้อมูลของเทส) · การขอสิทธิ์ของเบราว์เซอร์จริงตรวจด้วยมือใน docs/acceptance.md AC-IN-08/09

const BBB_URL = "https://www.youtube.com/watch?v=aqz-KE-bpKQ"
const HINT = "เบราว์เซอร์ไม่อนุญาตให้อ่านคลิปบอร์ด คลิกในช่องแล้วกด Ctrl+V แทน"

type ClipboardMode = { mode: "text"; text: string } | { mode: "denied" } | { mode: "missing" }

/** แทน readText ก่อนหน้าโหลด และนับจำนวนครั้งที่ถูกเรียกไว้ที่ window.__readTextCalls */
async function stubClipboard(page: Page, setup: ClipboardMode) {
  await page.addInitScript((conf: ClipboardMode) => {
    const counter = { calls: 0 }
    Object.defineProperty(window, "__readTextCalls", { get: () => counter.calls })
    if (conf.mode === "missing") {
      Object.defineProperty(Navigator.prototype, "clipboard", { get: () => undefined, configurable: true })
      return
    }
    const readText = () => {
      counter.calls += 1
      return conf.mode === "denied"
        ? Promise.reject(new DOMException("Read permission denied.", "NotAllowedError"))
        : Promise.resolve(conf.text)
    }
    Object.defineProperty(navigator.clipboard, "readText", { value: readText, configurable: true })
  }, setup)
}

const readTextCalls = (page: Page) => page.evaluate(() => (window as unknown as { __readTextCalls: number }).__readTextCalls)

async function countResolves(page: Page): Promise<{ calls: number }> {
  const seen = { calls: 0 }
  await page.route("**/api/resolve", (route) => {
    seen.calls += 1
    return route.fulfill({ json: { resolveId: "r1", items: [], skippedText: true } })
  })
  return seen
}

const pasteButton = (page: Page) => page.getByRole("button", { name: "วาง", exact: true })

test("AC-IN-08: ลิงก์ในคลิปบอร์ด → กดวาง แทนข้อความในช่องแล้ววิเคราะห์ทันที · ไม่อ่านคลิปบอร์ดก่อนกด", async ({ page }) => {
  await stubClipboard(page, { mode: "text", text: BBB_URL })
  const resolves = await countResolves(page)
  await page.goto("/")
  await page.getByRole("textbox").fill("ข้อความเก่าในช่อง")
  expect(await readTextCalls(page)).toBe(0)
  await pasteButton(page).click()
  await expect(page.getByRole("textbox")).toHaveValue(BBB_URL)
  await expect.poll(() => resolves.calls).toBe(1)
  expect(await readTextCalls(page)).toBe(1)
})

test("AC-IN-08: ข้อความอื่น → เติมลงช่องอย่างเดียว ไม่วิเคราะห์", async ({ page }) => {
  await stubClipboard(page, { mode: "text", text: "สูตรแกงเขียวหวาน" })
  const resolves = await countResolves(page)
  await page.goto("/")
  await pasteButton(page).click()
  await expect(page.getByRole("textbox")).toHaveValue("สูตรแกงเขียวหวาน")
  await expect(page.getByRole("textbox")).toBeFocused()
  expect(resolves.calls).toBe(0)
})

test("คลิปบอร์ดว่าง → ช่องเดิมไม่เปลี่ยน โฟกัสช่อง ไม่มีคำแนะนำ", async ({ page }) => {
  await stubClipboard(page, { mode: "text", text: "  " })
  await page.goto("/")
  await page.getByRole("textbox").fill("เดิม")
  await pasteButton(page).click()
  await expect(page.getByRole("textbox")).toBeFocused()
  await expect(page.getByRole("textbox")).toHaveValue("เดิม")
  await expect(page.getByText(HINT)).toHaveCount(0)
})

for (const mode of ["denied", "missing"] as const) {
  test(`AC-IN-09: เบราว์เซอร์ไม่ให้อ่านคลิปบอร์ด (${mode}) → คำแนะนำใต้ช่อง โฟกัสช่อง ไม่มี error สีแดง ไม่มี toast`, async ({
    page,
  }) => {
    await stubClipboard(page, { mode })
    await page.goto("/")
    await pasteButton(page).click()
    const hint = page.getByText(HINT)
    await expect(hint).toBeVisible()
    await expect(hint).toHaveAttribute("role", "status")
    await expect(page.getByRole("textbox")).toBeFocused()
    await expect(page.getByRole("textbox")).toHaveAttribute("aria-describedby", "paste-hint")
    await expect(page.getByRole("alert")).toHaveCount(0)
    await expect(page.locator("[data-sonner-toast]")).toHaveCount(0)
    // พิมพ์ในช่อง = คำแนะนำหายไป
    await page.getByRole("textbox").fill("x")
    await expect(hint).toHaveCount(0)
  })
}

test("ระหว่างวิเคราะห์ ปุ่มวางกดไม่ได้ (โฟกัสยังอยู่) และไม่อ่านคลิปบอร์ด", async ({ page }) => {
  await stubClipboard(page, { mode: "text", text: BBB_URL })
  let release: () => void = () => undefined
  await page.route("**/api/resolve", async (route) => {
    await new Promise<void>((resolve) => (release = resolve))
    await route.fulfill({ json: { resolveId: "r1", items: [], skippedText: true } })
  })
  await page.goto("/")
  await page.getByRole("textbox").fill(BBB_URL)
  await page.getByRole("button", { name: "วิเคราะห์" }).click()
  await expect(pasteButton(page)).toHaveAttribute("aria-disabled", "true")
  await pasteButton(page).click({ force: true })
  expect(await readTextCalls(page)).toBe(0)
  release()
})

test("หน้าต่างแคบ 640 px: ปุ่มวางกับปุ่มวิเคราะห์อยู่แถวเดียวกัน คำแนะนำไม่ทำให้เลื่อนซ้ายขวา · axe ผ่าน", async ({ page }) => {
  await page.setViewportSize({ width: 640, height: 800 })
  await stubClipboard(page, { mode: "denied" })
  await page.goto("/")
  await pasteButton(page).click()
  await expect(page.getByText(HINT)).toBeVisible()
  const paste = await pasteButton(page).boundingBox()
  const analyze = await page.getByRole("button", { name: "วิเคราะห์" }).boundingBox()
  expect(paste && analyze && Math.abs(paste.y - analyze.y) < 2).toBe(true)
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(640)
  const results = await analyzeSettled(page)
  expect(results.violations.filter((v) => v.impact === "serious" || v.impact === "critical")).toEqual([])
})
```

In `web/e2e/settings-general.spec.ts`:

Replace (1):
```ts
test("/settings เปิดที่แท็บทั่วไป พร้อมเจ็ดช่อง", async ({ page }) => {
```
with:
```ts
test("/settings เปิดที่แท็บทั่วไป พร้อมแปดช่อง และส่วนข้อมูลในเครื่อง", async ({ page }) => {
```

Replace (2):
```ts
  await expect(page.getByRole("button", { name: "เปิดโฟลเดอร์" })).toBeVisible()
```
with:
```ts
  await expect(page.getByRole("button", { name: "เปิดโฟลเดอร์" })).toBeVisible()
  await expect(page.getByRole("combobox", { name: "รูปแบบชื่อไฟล์" })).toBeVisible()
  await expect(page.getByText(/^ตัวอย่าง: .+\.mp4$/)).toBeVisible()
```

Replace (3):
```ts
  await expect(page.getByRole("switch", { name: "ทำภาพคมอัตโนมัติตอนโหลดวิดีโอ" })).toBeVisible()
```
with:
```ts
  await expect(page.getByRole("switch", { name: "ทำภาพคมอัตโนมัติตอนโหลดวิดีโอ" })).toBeVisible()
  // M6 รอบ A: ส่วน "ข้อมูลในเครื่อง" (ปุ่มล้างมีขนาดหรือไม่มีก็ได้ ขึ้นกับ cache ของ spec อื่นที่รันพร้อมกัน)
  const local = page.getByRole("group", { name: "ข้อมูลในเครื่อง" })
  await expect(local.getByRole("button", { name: /^ล้างข้อมูลชั่วคราว/ })).toBeVisible()
  await expect(local.getByRole("button", { name: "สำรองค่าตั้ง" })).toBeVisible()
  await expect(local.getByRole("button", { name: "นำเข้าค่าตั้ง" })).toBeVisible()
```

Create `web/e2e/settings-local-data.spec.ts`:
```ts
import { analyzeSettled } from "./axe-settled"
import { expect, test, type APIRequestContext, type Page } from "@playwright/test"

// M6 รอบ A: รูปแบบชื่อไฟล์ + ตัวอย่าง (AC-OUT-10) และ "ข้อมูลในเครื่อง" (AC-SET-07..10) ในแท็บทั่วไป
// project chromium ห้ามเขียน backend ที่ spec อื่นใช้ร่วม: /api/settings (GET/PATCH), /api/storage*, /api/settings/import,
// /api/settings/export และ /api/history ถูก mock ด้วย page.route ทั้งหมด

type Stored = Record<string, unknown>
type Stub = { patches: Stored[]; state: () => Stored }

async function readSettings(request: APIRequestContext): Promise<Stored> {
  const response = await request.get("/api/settings")
  expect(response.ok()).toBe(true)
  return (await response.json()) as Stored
}

/** แทน GET/PATCH /api/settings ด้วยค่าในหน้า (เริ่มจากค่าจริง) ไม่เขียน backend · เก็บเนื้อ PATCH ไว้นับ */
async function stubSettings(page: Page, request: APIRequestContext, start: Stored = {}): Promise<Stub> {
  let state = { ...(await readSettings(request)), ...start }
  const patches: Stored[] = []
  await page.route("**/api/settings", (route) => {
    if (route.request().method() === "PATCH") {
      const body = route.request().postDataJSON() as Stored
      patches.push(body)
      state = { ...state, ...body }
    }
    return route.fulfill({ json: state })
  })
  return { patches, state: () => state }
}

type Clip = { videoId: string; title: string; channel: string }

async function stubHistory(page: Page, items: Clip[]) {
  await page.route("**/api/history?*", (route) =>
    route.fulfill({
      json: {
        items: items.map((c) => ({ ...c, thumbnailUrl: "", durationS: 60, outputs: [], lastAt: new Date().toISOString() })),
        total: items.length,
      },
    })
  )
}

async function stubStorage(page: Page, reclaimableBytes: number, freedBytes = reclaimableBytes) {
  const calls = { clear: 0 }
  await page.route("**/api/storage", (route) =>
    route.fulfill({ json: { cacheBytes: reclaimableBytes, workBytes: 0, reclaimableBytes } })
  )
  await page.route("**/api/storage/clear", (route) => {
    calls.clear += 1
    return route.fulfill({ json: { freedBytes } })
  })
  return calls
}

const example = (page: Page) => page.locator("#general-filename-example")
const toast = (page: Page, text: string) => page.locator("[data-sonner-toast]", { hasText: text })

async function seriousViolations(page: Page) {
  const results = await analyzeSettled(page)
  return results.violations
    .filter((v) => v.impact === "serious" || v.impact === "critical")
    .map((v) => ({ id: v.id, nodes: v.nodes.map((n) => n.target.join(" ")).slice(0, 5) }))
}

// ---------- รูปแบบชื่อไฟล์ ----------

test("AC-OUT-10: เปลี่ยนรูปแบบ → ตัวอย่างเปลี่ยนทันที ใช้คลิปที่เปิดล่าสุด และไม่เรียก API อื่นนอกจากบันทึก", async ({
  page,
  request,
}) => {
  const stub = await stubSettings(page, request, { filenameStyle: "title" })
  await stubHistory(page, [{ videoId: "aqz-KE-bpKQ", title: 'ทดสอบ: "A/B" <ภาค 1>?', channel: "ช่อง/ทดสอบ" }])
  await stubStorage(page, 0)
  await page.goto("/settings/general")
  await expect(example(page)).toHaveText("ตัวอย่าง: ทดสอบ AB ภาค 1.mp4")
  const requests: string[] = []
  page.on("request", (r) => {
    if (new URL(r.url()).pathname.startsWith("/api/")) requests.push(`${r.method()} ${new URL(r.url()).pathname}`)
  })
  await page.getByRole("combobox", { name: "รูปแบบชื่อไฟล์" }).click()
  await page.getByRole("option", { name: "ชื่อคลิป - ช่อง" }).click()
  await expect(example(page)).toHaveText("ตัวอย่าง: ทดสอบ AB ภาค 1 - ช่องทดสอบ.mp4")
  await expect(toast(page, "บันทึกแล้ว")).toBeVisible()
  await page.getByRole("combobox", { name: "รูปแบบชื่อไฟล์" }).click()
  await page.getByRole("option", { name: "ชื่อคลิป (คุณภาพ)" }).click()
  await expect(example(page)).toHaveText("ตัวอย่าง: ทดสอบ AB ภาค 1 (1080p).mp4")
  await expect.poll(() => stub.patches.length).toBe(2)
  expect(stub.patches).toEqual([{ filenameStyle: "title-channel" }, { filenameStyle: "title-quality" }])
  expect(requests).toEqual(["PATCH /api/settings", "PATCH /api/settings"])
})

test("ยังไม่เคยเปิดคลิป: ตัวอย่างใช้ชื่อคลิปภาษาไทยตัวอย่าง", async ({ page, request }) => {
  await stubSettings(page, request, { filenameStyle: "title-channel" })
  await stubHistory(page, [])
  await stubStorage(page, 0)
  await page.goto("/settings/general")
  await expect(example(page)).toHaveText("ตัวอย่าง: สอนทำกับข้าวง่าย ๆ ใน 10 นาที - ครัวบ้านเรา.mp4")
})

// ---------- ล้างข้อมูลชั่วคราว ----------

test("AC-SET-07: ปุ่มบอกขนาด → กล่องยืนยัน → ยกเลิกไม่ส่งอะไร → ล้างเลย → toast ได้พื้นที่คืน", async ({ page, request }) => {
  await stubSettings(page, request)
  await stubHistory(page, [])
  const calls = await stubStorage(page, 1_200_000_000)
  await page.goto("/settings/general")
  await expect(page.getByRole("group", { name: "ข้อมูลในเครื่อง" })).toBeVisible()
  const clear = page.getByRole("button", { name: "ล้างข้อมูลชั่วคราว (1.2 GB)" })
  await clear.click()
  const dialog = page.getByRole("alertdialog")
  await expect(dialog.getByRole("heading", { name: "ล้างข้อมูลชั่วคราว 1.2 GB?" })).toBeVisible()
  await expect(dialog).toContainText("ไฟล์ที่โหลดไว้ ประวัติ และค่าตั้งยังอยู่ครบ แต่เปิดคลิปเก่าต้องดึงภาพใหม่")
  await dialog.getByRole("button", { name: "ยกเลิก" }).click()
  await expect(dialog).toHaveCount(0)
  expect(calls.clear).toBe(0)
  await clear.click()
  await page.getByRole("alertdialog").getByRole("button", { name: "ล้างเลย" }).click()
  await expect(toast(page, "ล้างแล้ว ได้พื้นที่คืน 1.2 GB")).toBeVisible()
  await expect(page.getByRole("alertdialog")).toHaveCount(0)
  expect(calls.clear).toBe(1)
})

test("ไม่มีอะไรให้ล้าง หรือโหลดขนาดไม่ได้ = ปุ่มกดไม่ได้ ไม่มี error", async ({ page, request }) => {
  await stubSettings(page, request)
  await stubHistory(page, [])
  await page.route("**/api/storage", (route) => route.fulfill({ status: 500, json: { error: { code: "E_UNKNOWN", message: "x" } } }))
  await page.goto("/settings/general")
  await expect(page.getByRole("button", { name: "ล้างข้อมูลชั่วคราว", exact: true })).toBeDisabled()
  await expect(page.locator("[data-sonner-toast]")).toHaveCount(0)
})

test("ล้างไม่สำเร็จ → toast error พร้อมปุ่มคัดลอกข้อมูลแจ้งปัญหา", async ({ page, request }) => {
  await stubSettings(page, request)
  await stubHistory(page, [])
  await page.route("**/api/storage", (route) => route.fulfill({ json: { cacheBytes: 5e6, workBytes: 0, reclaimableBytes: 5e6 } }))
  await page.route("**/api/storage/clear", (route) =>
    route.fulfill({ status: 500, json: { error: { code: "E_UNKNOWN", message: "มีบางอย่างผิดพลาด", detail: "OSError" } } })
  )
  await page.goto("/settings/general")
  await page.getByRole("button", { name: "ล้างข้อมูลชั่วคราว (5.0 MB)" }).click()
  await page.getByRole("alertdialog").getByRole("button", { name: "ล้างเลย" }).click()
  await expect(toast(page, "มีบางอย่างผิดพลาด").getByRole("button", { name: "คัดลอกข้อมูลแจ้งปัญหา" })).toBeVisible()
})

// ---------- สำรอง / นำเข้าค่าตั้ง ----------

test("AC-SET-09: สำรองค่าตั้ง → ดาวน์โหลดไฟล์ชื่อตามวันที่", async ({ page, request }) => {
  await stubSettings(page, request)
  await stubHistory(page, [])
  await stubStorage(page, 0)
  await page.route("**/api/settings/export", (route) =>
    route.fulfill({
      body: '{"app": "yt-toolkit", "schema": 1, "settings": {}}\n',
      headers: {
        "Content-Type": "application/json",
        "Content-Disposition": "attachment; filename=\"yt-toolkit-settings-2026-10-14.json\"; filename*=UTF-8''yt-toolkit-settings-2026-10-14.json",
      },
    })
  )
  await page.goto("/settings/general")
  const download = page.waitForEvent("download")
  await page.getByRole("button", { name: "สำรองค่าตั้ง" }).click()
  expect((await download).suggestedFilename()).toBe("yt-toolkit-settings-2026-10-14.json")
  await expect(page.locator("[data-sonner-toast]")).toHaveCount(0)
})

const IMPORT_FILE = (settings: Stored) => ({
  name: "yt-toolkit-settings-2026-10-14.json",
  mimeType: "application/json",
  buffer: Buffer.from(JSON.stringify({ app: "yt-toolkit", schema: 1, settings })),
})

test("AC-SET-09: นำเข้าไฟล์ถูกต้อง → นำเข้าค่าตั้งแล้ว และค่าใหม่ขึ้นบนจอทันที", async ({ page, request }) => {
  const stub = await stubSettings(page, request, { concurrency: 2 })
  await stubHistory(page, [])
  await stubStorage(page, 0)
  const bodies: string[] = []
  await page.route("**/api/settings/import", (route) => {
    bodies.push(route.request().postData() ?? "")
    return route.fulfill({ json: { settings: { ...stub.state(), concurrency: 3 }, warnings: [] } })
  })
  await page.goto("/settings/general")
  await page.locator('input[type="file"]').setInputFiles(IMPORT_FILE({ concurrency: 3 }))
  await expect(toast(page, "นำเข้าค่าตั้งแล้ว")).toBeVisible()
  await expect(
    page.getByRole("group", { name: "จำนวนงานพร้อมกัน" }).getByRole("button", { name: "3", exact: true })
  ).toHaveAttribute("aria-pressed", "true")
  expect(JSON.parse(bodies[0])).toEqual({ app: "yt-toolkit", schema: 1, settings: { concurrency: 3 } })
})

test("AC-SET-09: โฟลเดอร์ในไฟล์ใช้บนเครื่องนี้ไม่ได้ → คำเตือนค้างจนกดปิด", async ({ page, request }) => {
  const stub = await stubSettings(page, request)
  await stubHistory(page, [])
  await stubStorage(page, 0)
  await page.route("**/api/settings/import", (route) =>
    route.fulfill({ json: { settings: stub.state(), warnings: ["outputDir"] } })
  )
  await page.goto("/settings/general")
  await page.locator('input[type="file"]').setInputFiles(IMPORT_FILE({ outputDir: "Q:\\YT" }))
  const warning = toast(page, "นำเข้าค่าตั้งแล้ว แต่ใช้โฟลเดอร์ผลลัพธ์ในไฟล์บนเครื่องนี้ไม่ได้ จึงใช้โฟลเดอร์เดิมต่อ")
  await expect(warning).toBeVisible()
  await page.waitForTimeout(4500) // toast ปกติหายใน 4 วินาที
  await expect(warning).toBeVisible()
  await warning.getByRole("button", { name: "ปิด" }).click()
  await expect(warning).toHaveCount(0)
})

test("AC-SET-10: ไฟล์ที่ไม่ใช่ไฟล์ค่าตั้ง → ข้อความจาก backend พร้อมปุ่มคัดลอกข้อมูลแจ้งปัญหา", async ({ page, request }) => {
  await stubSettings(page, request)
  await stubHistory(page, [])
  await stubStorage(page, 0)
  const message = 'ไฟล์นี้ไม่ใช่ไฟล์ค่าตั้งของ YT Toolkit หรือไฟล์เสียหาย ลองเลือกไฟล์ที่ได้จากปุ่ม "สำรองค่าตั้ง"'
  await page.route("**/api/settings/import", (route) =>
    route.fulfill({ status: 422, json: { error: { code: "E_SETTINGS_INVALID", message, detail: "app invalid" } } })
  )
  await page.goto("/settings/general")
  await page.locator('input[type="file"]').setInputFiles({ name: "other.json", mimeType: "application/json", buffer: Buffer.from("{}") })
  await expect(toast(page, message).getByRole("button", { name: "คัดลอกข้อมูลแจ้งปัญหา" })).toBeVisible()
})

test("ไฟล์ใหญ่กว่า 1 MB → ไม่ส่งไป backend และแจ้งข้อความเดียวกัน", async ({ page, request }) => {
  await stubSettings(page, request)
  await stubHistory(page, [])
  await stubStorage(page, 0)
  let imports = 0
  await page.route("**/api/settings/import", (route) => {
    imports += 1
    return route.abort()
  })
  await page.goto("/settings/general")
  await page.locator('input[type="file"]').setInputFiles({
    name: "big.json",
    mimeType: "application/json",
    buffer: Buffer.alloc(2 * 1024 * 1024, 0x20),
  })
  const message = 'ไฟล์นี้ไม่ใช่ไฟล์ค่าตั้งของ YT Toolkit หรือไฟล์เสียหาย ลองเลือกไฟล์ที่ได้จากปุ่ม "สำรองค่าตั้ง"'
  await expect(toast(page, message).getByRole("button", { name: "คัดลอกข้อมูลแจ้งปัญหา" })).toBeVisible()
  expect(imports).toBe(0)
})

// ---------- หน้าต่างแคบ และ axe ----------

test("หน้าต่างแคบ 640 px: ตัวอย่างชื่อยาว 300 ตัวและแถวปุ่มไม่ทำให้เลื่อนซ้ายขวา · กล่องยืนยันอ่านได้ครบ", async ({
  page,
  request,
}) => {
  await page.setViewportSize({ width: 640, height: 800 })
  await stubSettings(page, request, { filenameStyle: "title-channel" })
  await stubHistory(page, [{ videoId: "aqz-KE-bpKQ", title: "ก".repeat(300), channel: "ช".repeat(120) }])
  await stubStorage(page, 1_200_000_000)
  await page.goto("/settings/general")
  await expect(example(page)).toContainText("ตัวอย่าง: กกกก")
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(640)
  await page.getByRole("button", { name: "ล้างข้อมูลชั่วคราว (1.2 GB)" }).click()
  const dialog = page.getByRole("alertdialog")
  await expect(dialog.getByRole("button", { name: "ล้างเลย" })).toBeInViewport()
  const box = await dialog.boundingBox()
  expect(box && box.x >= 0 && box.x + box.width <= 640).toBe(true)
})

for (const scheme of ["dark", "light"] as const) {
  test(`axe: ส่วนข้อมูลในเครื่อง ช่องรูปแบบชื่อไฟล์ และกล่องยืนยัน (${scheme})`, async ({ page, request }) => {
    await page.emulateMedia({ colorScheme: scheme })
    await stubSettings(page, request)
    await stubHistory(page, [])
    await stubStorage(page, 1_200_000_000)
    await page.goto("/settings/general")
    await expect(page.getByRole("button", { name: "ล้างข้อมูลชั่วคราว (1.2 GB)" })).toBeEnabled()
    await expect(page.locator("html")).toHaveClass(scheme === "dark" ? /dark/ : /light/)
    expect(await seriousViolations(page)).toEqual([])
    await page.getByRole("button", { name: "ล้างข้อมูลชั่วคราว (1.2 GB)" }).click()
    await expect(page.getByRole("alertdialog")).toBeVisible()
    expect(await seriousViolations(page)).toEqual([])
  })
}
```

- [ ] **Step 2: Typecheck and lint them in the lane**

Run: `cd "$WORKTREE/web" && npm run typecheck && npm run lint && npm test`
Expected: typecheck clean, lint clean, vitest `1142 passed (1142)`. Lanes do not run Playwright.

- [ ] **Step 3: Commit**
```bash
cd "$WORKTREE" && git add web/e2e/home-paste.spec.ts web/e2e/settings-local-data.spec.ts web/e2e/settings-general.spec.ts && git commit -F- <<'EOF'
test(e2e): paste button, filename example, clear / back up / import settings, 640 px and axe

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
EOF
```

- [ ] **Step 4 (controller, final gate):** `cd web && npm run build && npx playwright test --project=chromium e2e/home-paste.spec.ts e2e/settings-local-data.spec.ts e2e/settings-general.spec.ts` — 34 passed on the prototype (7 + 13 + 14). A failure goes back to the owning lane (T9 paste, T10 section, T12 style field, T4 copy).

---

## Spec coverage (self-review)

| Spec item | Task(s) |
|---|---|
| D1 / §1.1 `isSupportedLink`, the two existing call sites switched | T4 (predicate + test), T9 (`home.tsx`, `use-analyze.tsx`) |
| §1.2 `readClipboard` model (four outcomes, missing clipboard / readText, rejection, sync throw, read only on click) | T9 `paste-button.ts` + test; T14 0 calls before the click |
| §1.3 secondary "วาง" button before "วิเคราะห์", `aria-disabled` while pending, replace vs fill, hint with `role="status"` + `aria-describedby`, hides on change / non-denied click | T9 (P28); T14 |
| §1.3 640 px addon row | T14 (`home-paste.spec.ts` same row, `scrollWidth`) |
| D3 / §2.1 which kinds take each style; chapter split, sharp dir, captures, clip folder unchanged; suffix order | T5 tests per kind × style, chapter + sharp unchanged; T1 folder identical across styles |
| §2.2 `plan_names` algorithm (budget, cap, fallback, channel cut order, path check), `plan_output` wrapper, port details | T1 (+ P3, P5), T8 |
| §2.3 quality labels, short side, unknown facts, `standard_kbps` (tie → higher, clamps, unknown), `MediaFacts.abr_kbps` from the extractor | T5 (+ P1, P2) |
| D4 / §2.4 schema v3 (frozen `_JOBS_V2`), `Job.filename_style`, `SettingsView.filename_style`, `_start` snapshot, `JobContext.filename_style`, `_Clip.style` / `uploader` | T2, T5 |
| §2.5 parity fixtures (cases, golden via `YT_UPDATE_GOLDEN=1`, TS reads both; minimum cases list) | T1 (60 cases incl. every listed one), T8 |
| §2.6 history `channel`, shared `recentQuery`, `exampleFileName` (latest clip / sample, `PathTooLongError` retry), the field after `OutputDirField`, `GeneralKey` | T3, T4, T12 (+ P26, P27) |
| §2.7 `channel_of`, styled sweep patterns, `job_titles(..., channel)` + callers | T2 (privacy), T11 (+ P7, P8, P9) |
| D2 / §3.1 what is counted / clearable, staging grace, links not followed, unreadable = 0 | T7 (+ P21, P22) |
| §3.2 `hold_active` (queue lock, capture `_guard`, lock order), two phases with rename into `.clear-*`, honest `freedBytes`, serialised clears, startup sweep | T7 (+ P10, P22) |
| §3.3 readers that tolerate a missing cache (one test per row), web cache cleanup after a clear | T7 `test_storage_readers.py` + API 404 test (P23); T10 `forgetClipCaches` |
| §3.4 `db.cache_folder`, `core/storage.py`, `api/storage.py`, router in `create_app`, log lines | T7 |
| D6 / §4.1 export body, serialisation, headers, dated name, no token needed | T6 (+ P19) |
| §4.2 import: 413 (header and stream), UTF-8 + BOM, NaN, shape, all-or-nothing, skipped keys, `outputDir` warning, one transaction, hook, `E_SETTINGS_INVALID` | T6 (+ P18, P20) |
| §4.3 web: client calls, file picker, 1 MB pre-check, success / warning / failure toasts, export failure | T4 (client), T10 (+ P12, P13) |
| D8 / §5 the section (legend, three secondary buttons, sizes, disabled states), confirm dialog, after-clear toast + cleanup, report contexts, 640 px | T10, T14 (+ P14) |
| §6 edge cases | paste while analyzing (T9, T14) · style change mid-run (T2) · two jobs different styles (T11, T5 folder) · long channel (T1) · clear while a job / capture runs (T7) · file open on Windows (T7) · app closed mid-clear (T7 startup sweep) · import without the folder (T6, T14) · newer `schema` (T6) · import while a job runs (T6 hook; queue reads `output_dir` at each start, unchanged) |
| §7.1-§7.4 tests | T1, T2, T3, T5, T6, T7, T11 (Python unit/API) · T13 (canary) · T4, T8, T9, T10, T12 (vitest) · T14 (chromium, axe light/dark, 640 px) |
| §8 docs | done in the spec commits; no task edits `PRD.md` / `docs/acceptance.md` |
| §9 Thai copy | T4 (every key, verbatim); no other task adds Thai (lane rule 3) |
| §10 YouTube-only assumptions | awareness only (C12) |
| §12 review focus | Review Focus 1-5 above, each pinned by named tests |

Self-review checks run on this plan:
- **Placeholders:** none — new files are given whole; changed files are exact "Replace … with …" blocks generated from the prototype diff (each old block occurs once at the task's wave base; the per-block check against `344567b` is in "Verified facts").
- **Type/name consistency:** `plan_names` / `plan_output` / `NAME_STYLES` / `CHANNEL_SEP` (T1 → T5, T11), `planNames` / `PathTooLongError` / `FILENAME_STYLES` / `FilenameStyle` (T8 → T12), `filename_style` (T2 column, `Job`, `JobContext`, `SettingsView`; T5 `_Clip.style`; T11), `channel_of` (T2 → T11), `ActiveJobs` / `hold_active` (T7 queue + capture → `StorageService`), `StorageUsage` (Python `to_api()` keys = TS type keys), `ImportResult` / `exportSettings` / `importSettings` / `storageQuery` / `clearStorage` / `STORAGE_KEY` (T4 → T10), `recentQuery` (T4 → T12), `readClipboard` / `PasteOutcome` (T9), DOM ids `paste-hint`, `general-filename-example`, `local-data-actions`: one spelling each.
- **Lane isolation:** no file appears in two lanes of the same wave (Lane rules table); files owned in two waves (`db.py`, `queue.py`, `settings.py`, their tests, `lifecycle.py`, `test_lifecycle.py`, `general-panel.tsx`) change in different waves only, and each later block was checked at its wave base.
- **Review Focus:** five input classes, each pinned by named tests in the owning task.
- **Hard rules:** no `shell=True`, no new OS check (junction API only), `yt_dlp` stays in `extractor.py`, no titles / paths / tokens / cookies in new log lines or details, LF, no invented Thai, trailer, port 8787 untouched, 640 px checks, C12 corners listed.

---

## Execution handoff

Plan saved to `docs/superpowers/plans/2026-10-14-m6a-daily-conveniences.md`. Execution method (already chosen): **superpowers:subagent-driven-development with parallel lanes** — the controller creates one worktree per lane under `.claude/worktrees/m6a-t<N>` on `m6a/t<N>-<slug>` and dispatches one fresh subagent per task with its absolute `WORKTREE` (wave 1 = T1-T4, wave 2 = T5-T10, wave 3 = T11-T14, lanes of a wave in parallel), merges in the stated order, runs the wave gate procedure between waves (gate 2 adds the existing-e2e check), the two-stage review per task, then the final gate (build, `npm run e2e` with the queue project serial, `web/dist` commit, live preview for Pete, Windows checks from `docs/acceptance.md` "M6 รอบ A", Pete's merge choice and the milestone progress report). Pete reviews the plan before execution starts.
