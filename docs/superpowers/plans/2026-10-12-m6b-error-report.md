# M6 round B: two-layer errors, the problem report and logging Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (chosen execution method: subagent-driven development with parallel lanes). Steps use checkbox (`- [ ]`) syntax for tracking. Tasks inside one wave run as parallel subagents, each in its own controller-created git worktree (see "Waves" and "Lane rules"). Every task is reviewed by a reviewer subagent before its wave closes.

**Goal:** Every error the staff see gets a folded "ดูรายละเอียด" section (code + raw detail) and a "คัดลอกข้อมูลแจ้งปัญหา" button; the server builds one ready-to-paste Markdown report (machine state + the error + the last 50 log lines) behind one redaction point; every job failure and every non-job API error lands in `run/logs/app.log` with its code.

**Spec:** `docs/superpowers/specs/2026-10-12-m6b-error-report-design.md` (binding: owner decisions D1-D7, constraints C1-C11, Thai copy §7 used verbatim, spec questions Q1-Q5 answered in §9). Also read PRD.md §7 / §7.1 and `docs/acceptance.md`.

**Out of scope (round B):** `E_SETTINGS_INVALID` and settings import/export (round A), a corrupt on-disk `settings.json`, the output-folder field message and the cookies-dialog import message, removing absolute paths from API error `detail` in general, any upload or network use by the report, phone layouts, macOS launchers (M7).

**Architecture:**
- **Redaction (`yttoolkit/redact.py`, T1).** `redact_home` also matches percent-encoded home forms; new `mask_user_paths`, `mask_media_urls`, `scrub_titles`; `redact_log_detail` (the `job_failed` line) and `redact_report` (the report: plus token and sign-in cookie names). Stdlib only.
- **OS version (`Platform.os_version`, T2)** for the report's "ระบบ:" line, plus a guard test that only `yttoolkit.platform` checks the OS.
- **Copy + log file (T3).** `E_UNKNOWN` text (D3), the health-page JS-runtime warning text (D2), `app.log` rotation 5 MB × 3 files and quiet `httpx` INFO lines (D7).
- **Report builder (`core/diagnostics.py`, T6).** Pure function `build_report(ReportInputs) -> str`: PRD §7.1 template, log tail across `app.log`/`.1`/`.2` under the `app.log` handler lock, redaction in one place, then caps 2,000 / 300 / 8,000.
- **Queue failure log (`core/queue.py`, T7).** One `job_failed id= kind= code= detail=` line (+ redacted traceback) per failure, written in `_fail` and the spawn-failure path.
- **API (`api/diagnostics.py`, `api/errors.py`, `app.py`, T11).** Token-protected `POST /api/diagnostics` with hand validation (422 never echoes a value); `ErrorLogMiddleware` writes `api_error method= path= status= code=` for every `/api` error response; the privacy canary covers the report (AC-SET-06).
- **Web foundation (T4).** `th.errors.*` keys, `lib/report.ts` (`reportRequest`, `cleanRequest`, `fetchReport`, `copyReport`), `components/error-report/` (`model.ts`, `CopyReportButton`, `ErrorDetails`, `showErrorToast`).
- **Web call sites (T8, T9, T10)** split by disjoint files: clip page + history/batch (all `LoadError` callers), queue + crash panel + account, home/settings/enqueue. **E2E (T12)** `web/e2e/error-report.spec.ts` (chromium, mocked failures, real fake-mode `/api/diagnostics`).
- **Docs (T5).** PRD §6.2 row and §11, `docs/acceptance.md` "M6 รอบ B" rows for AC-SET-03..06, follow-up files.

**Tech Stack:** unchanged (Python 3.13 + uv, FastAPI, yt-dlp as a library, React ^19.2 + Vite + Tailwind v4 + shadcn/Base UI + react-query 5 + sonner 2, Vitest (node), Playwright + axe). No new Python or npm dependency (C11).

---

## Owner answers (Pete, 2026-10-12; spec §9, all binding)

- **Spec Q1:** non-job error line in the report = `- รหัส: E_NETWORK · หน้าจอ: video-header (videoId dQw4w9WgXcQ)` (Thai label `หน้าจอ:` + ASCII context tag). T6 `_code_line`, T12 e2e literal.
- **Spec Q2:** no manual-copy box when the clipboard is blocked; only the toast "คัดลอกไม่สำเร็จ ลองอีกครั้ง" (`th.errors.copyFailed`). T4 `copyReport`.
- **Spec Q3:** `start.bat:88`, `:95` keep their "ถ่ายภาพหน้าจอนี้ส่งให้ผู้ดูแล…" text. No task touches `start.bat`.
- **Spec Q4:** 3 log files total: `RotatingFileHandler(maxBytes=5_000_000, backupCount=2)`. T3.
- **Spec Q5:** the small action toasts (cancel/retry, reorder, resume, account delete, reveal, SponsorBlock save) get the copy button, keep their text, pass the dropped error, `duration: Infinity` + a stable id. T8/T9.
- **Decision-file Q1-Q3 (D1-D3):** copy button at every error point; `E_JS_RUNTIME_MISSING` is only the health-page warning text; new `E_UNKNOWN` text.

## Planner rulings (resolutions of spec gaps; Pete can still object)

- **P1 — API test module name.** The spec names both `tests/unit/test_diagnostics.py` and `tests/api/test_diagnostics.py`. pytest here runs without `__init__.py` packages, so two test files with the same basename fail collection ("import file mismatch"). The API tests live in **`tests/api/test_diagnostics_api.py`** (same pattern as `test_account_api.py`).
- **P2 — PRD §6.2 row.** PRD §6.2 already has a stale row `| GET | /diagnostics | ?jobId= ...`. T5 **replaces** that row with the spec §2.1 POST row (there is no GET any more), and changes the §11 FR-SET-5 cell to `POST /diagnostics`.
- **P3 — "nothing else in the report mentions the account" (spec §6.3).** The log tail contains the app's own account log lines (for example "นำเข้าบัญชียูทูปชั่วคราวแล้ว ลบเองภายใน <UTC time>"), which carry no cookie data and already pass the M5-C canary rule. The canary checks the "only the status line" rule on the header + error section (everything before `### log ล่าสุด`); the whole report, log block included, must still pass `_assert_clean` and contain no cookie names.
- **P4 — the web never sends a body the server rejects.** `lib/report.ts` `cleanRequest` drops a `jobId` / `context` / `videoId` that breaks the server pattern (for example `/v/abc`), turns a malformed `code` into `E_UNKNOWN` and cuts `detail` to 4,000. `fetchReport` always sends `cleanRequest(req)`, so a real error never gets 422 instead of a report (spec §2.1 "the server never returns 422 for a real error").
- **P5 — toasts that reuse an error toast's id.** sonner merges a new toast into the existing one with the same id (`{...old, ...new}`), so a later success/loading toast with the same id would keep the copy button and `duration: Infinity`. Every non-error toast that shares an id with an error toast spreads `PLAIN_TOAST` (`{description, duration, action, cancel}` all `undefined`) first: the finished-job toast `job-<id>`, settings "บันทึกแล้ว" (`settings-general`), ffmpeg install loading/success/info (`ffmpeg`).
- **P6 — `ErrorDetails` takes either an error or a ready request.** Props are `{ error, context, videoId?, jobId? }` or `{ request }`; the queue `FailedRow` passes `{ request: { jobId, code, detail, context: "queue" } }` because `job.error` is not an `ApiError`. It also takes `className` (`"col-start-2"` inside icon Alerts) and `open` / `onOpenChange` (spec §1.4).
- **P7 — `SubsPreview` gets a `videoId` prop** (spec §1.3 wants `videoId` for `video-subs-preview`, the component had none); `subs-panel.tsx` passes it (T8).
- **P8 — UNC paths start at a boundary.** `mask_user_paths` treats `\\server\share\` as a path only at the start of text or after whitespace, a quote, `(`, `=`, `,`, `;` or `:`; otherwise the doubled-backslash repr `'~\\Downloads\\a.mp4'` would be masked as a UNC path (found by the prototype).
- **P9 — unhandled exceptions in the middleware.** Starlette's `ServerErrorMiddleware` (outside every user middleware) sends the 500 for an unhandled exception, so `ErrorLogMiddleware` never sees that response. It catches the exception before any response started, logs `api_error ... status=500 code=E_UNKNOWN` at WARNING and re-raises; `_unhandled_error` still writes the traceback line (now with `code=E_UNKNOWN`). Spec §6.2 "a 500 → a WARNING line plus the traceback line".
- **P10 — pre-existing failure at HEAD.** `tests/unit/test_yterrors.py::test_messages_match_prd_table` fails at `ffbd03e` because the spec commit already changed PRD §7 `E_UNKNOWN`; T3 fixes it. Every other test passed at `ffbd03e` (3,276 passed, 46 network deselected; vitest 1,009 passed).

---

## Waves

Integration branch: `m6b-error-report` (already checked out in the main checkout; HEAD `ffbd03e` = the spec commits; this plan is the next commit).

| Wave | Lanes (one worktree each, file sets disjoint, run in parallel) | Depends on |
|---|---|---|
| 1 | T1 redaction helpers · T2 `Platform.os_version` + OS-check guard · T3 copy fixes + log rotation · T4 web foundation (strings, `lib/report.ts`, `components/error-report/`) · T5 docs | plan |
| 2 | T6 report builder · T7 queue `job_failed` logging · T8 web clip page + history/batch · T9 web queue + crash + account · T10 web home/settings/enqueue | gate 1 (T6←T1 · T7←T1 · T8/T9/T10←T4) |
| 3 | T11 `POST /api/diagnostics` + `ErrorLogMiddleware` + privacy canary · T12 chromium e2e `error-report.spec.ts` | gate 2 (T11←T2,T6 · T12←T8,T9,T10 at runtime; the spec file itself only needs T4 names) |
| final | controller: merge, full checks, `npm run build`, `npm run e2e`, commit `web/dist`, reviews, live preview for Pete | gate 3 |

**Merge order inside each wave** (no two lanes share a file, so the order only keeps history readable): wave 1 T1 → T2 → T3 → T4 → T5; wave 2 T6 → T7 → T8 → T9 → T10; wave 3 T11 → T12. A conflict means the plan is wrong: stop and report.
**Critical path:** T1 → T6 → T11 (then the final gate runs T12's e2e against everything).
**Counts:** 3 waves + final gate · 12 tasks (5 + 5 + 2 lanes).

### Lane rules (every task)
1. **Worktree and branch.** The controller creates one worktree per lane **before** dispatching it: `git worktree add .claude/worktrees/m6b-t<N> -b m6b/t<N>-<slug> m6b-error-report` (branched from the head of `m6b-error-report` at the start of the wave) and gives the lane its absolute path as `WORKTREE`. The harness option `isolation: "worktree"` is not used. The lane starts **every** shell command with `cd "$WORKTREE" &&` and edits files only by absolute path under `WORKTREE`. Never switch the main checkout's branch. For web lanes the controller runs `cd "$WORKTREE/web" && npm ci` once before dispatch.
2. **Files.** A task creates or modifies **only** the files in its **Files** list. Needing another file is a plan bug: stop and report it.
3. **Shared files have exactly one owner per wave:**

   | File | W1 | W2 | W3 |
   |---|---|---|---|
   | `src/yttoolkit/redact.py`, `tests/unit/test_redact.py` | T1 | — | — |
   | `src/yttoolkit/platform/{base,windows,macos}.py`, `tests/conftest.py`, `tests/unit/test_platform.py` | T2 | — | — |
   | `core/tools.py`, `core/yterrors.py`, `probe.py`, `tests/unit/test_tools_status.py`, `test_yterrors.py`, `test_probe.py` | T3 | — | — |
   | `tests/api/test_errors.py` | T3 (E_UNKNOWN text) | — | — (T11 does not edit it) |
   | `web/src/i18n/th.ts` | T4 (add keys, change `unknown`) | T9 (remove `queue.copyDetails` only) | — |
   | `web/src/lib/report.ts` (+test), `web/src/components/error-report/**`, `web/e2e/settings-general.spec.ts` | T4 | — | — |
   | `PRD.md`, `docs/acceptance.md`, `docs/m1-followups.md`, `docs/m4-followups.md` | T5 | — | — |
   | `core/diagnostics.py`, `tests/unit/test_diagnostics.py` | — | T6 | — |
   | `core/queue.py`, `tests/unit/test_queue.py` | — | T7 | — |
   | `web/src/pages/video/**` (listed files), `pages/video.tsx`, `pages/history.tsx`, `pages/batch.tsx`, `capture-store.test.ts` | — | T8 | — |
   | `components/queue/**` (listed), `components/account/use-account.ts`, `components/error-panel.tsx`, `components/route-error.tsx`, `web/e2e/nav.spec.ts`, `web/e2e/queue-flow.spec.ts` | — | T9 | — |
   | `pages/home.tsx`, `pages/home/{result-list.tsx,use-analyze.tsx}`, `pages/settings/{advanced,general,health}-panel.tsx`, `lib/jobs.ts`, `lib/jobs.test.ts` | — | T10 | — |
   | `api/diagnostics.py`, `api/errors.py`, `app.py`, `tests/api/test_diagnostics_api.py`, `tests/integration/test_account_privacy.py` | — | — | T11 |
   | `web/e2e/error-report.spec.ts` | — | — | T12 |
   | `web/dist/**` | final gate only; **no lane builds into or commits `web/dist`** | | |

   A lane that needs a Thai string that is not in spec §7 stops and asks the controller (never invent copy).
4. **Tests.**
   - Python lanes run their own tests first, then `cd "$WORKTREE" && uv run pytest -q -W error -p no:cacheprovider`.
   - Web lanes run `cd "$WORKTREE/web" && npm run typecheck && npm run lint && npm test`.
   - Lanes **do not run Playwright.** Specs are written, typechecked and linted in the lane; the controller runs them at gates.
   - The `queue` Playwright project is **always** run with `--workers=1` (the npm `e2e` script does this); never two Playwright invocations at once.
   - **No spec in the `chromium` project creates a real job.** Chromium specs mock the failing calls with `page.route` (POST `/api/jobs` included); only `/api/diagnostics` goes to the real fake-mode backend.
5. **Processes.** No lane starts a server. Never touch the owner's app on port 8787. Kill processes by PID only. Never `shell=True`.
6. **Commits.** Every commit message ends with exactly `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`. Use `git commit -F- <<'EOF' … EOF`.
7. **Line endings.** LF everywhere (`.gitattributes` `* text=auto eol=lf`); edit with the Edit tool; new files LF.
8. **Backslashes.** Python and TS literals below contain backslashes on purpose. Copy them with the Edit/Write tool, never through a shell heredoc (the shell layer can collapse `\\`).

### Wave gate procedure (controller, serial)
1. Merge every lane branch of the wave into `m6b-error-report` in the merge order above with `git merge --no-ff m6b/t<N>-<slug>`; then `git worktree remove .claude/worktrees/m6b-t<N>`.
2. `uv sync --frozen && uv run pytest -q -W error -p no:cacheprovider` (must pass).
3. `cd web && npm ci && npm run typecheck && npm run lint && npm test`.
4. Gate 2 only: `cd web && npm run build` then `npx playwright test --project=chromium e2e/nav.spec.ts e2e/video.spec.ts e2e/home.spec.ts e2e/settings-general.spec.ts e2e/health.spec.ts e2e/account.spec.ts e2e/capture.spec.ts` and `npx playwright test --project=queue --workers=1 e2e/queue-flow.spec.ts` (existing specs still pass with the new boxes/toasts). Then `git checkout -- web/dist` (never commit `web/dist` at a gate).
5. Two-stage review (spec compliance, then code quality) per task of the wave; fix findings in the owning lane before the next wave.

### Final gate (controller, after wave 3)
1. Merge T11, T12 (`--no-ff`), then steps 2-3 above.
2. `cd web && npm run build` then `npm run e2e` (chromium on `E2E_PORT` 8799, then queue on 8800 with `--workers=1`). A failing `error-report.spec.ts` goes back to T12 (or the lane that owns the failing component: T4 components, T8 clip page, T9 crash/queue, T10 health/enqueue).
3. Check total JS gzip ≤ 400 KB excluding fonts (PRD 6.5).
4. Commit the rebuilt `web/dist` as `build(web): web/dist after M6 round B` (with the trailer).
5. Reviews, then a live preview for Pete on port 8791 in fake mode (memory rule "preview after QA"): a clip-page error (mock not possible live, so use `/v/PRIVATEVID1`) → "ดูรายละเอียด" → "คัดลอกข้อมูลแจ้งปัญหา" → paste into Notepad; a failed queue job (`REFUSEDDL01`) → toast + row; Settings › ตรวจสุขภาพระบบ button; a 640 px window. Then Pete runs `docs/acceptance.md` "M6 รอบ B" on Windows.

---

## Verified facts (read on 2026-10-12 at `ffbd03e`; a scratch prototype of T1-T3, T6, T7, T11 and T4 was run against this tree)
- **Redaction.** `src/yttoolkit/redact.py` (stdlib only): `MASK = "<hidden>"`, `SIGN_IN_COOKIE_NAMES` (15 names), `_NAMES` alternation, `redact_secrets`, `_home_aliases` (functools.cache, lazy `from .platform import current`), `redact_home` (`variants` set at `:82-86`), `HomePathFilter`, `SecretFilter`, `add_redaction`. `api/errors.py` re-exports `redact_home`/`_home_aliases` and keeps `from pathlib import Path` because tests patch `errors.Path.home`. `tests/unit/test_redact.py:242` checks the module does not load the web stack.
- **Platform.** `platform/base.py:25` `Platform` protocol ends with `path_aliases`; `windows.py` imports `ctypes, functools, msvcrt, os, subprocess, uuid` (no `sys`); `macos.py` imports `fcntl, os, signal, subprocess`; `platform/__init__.py` is the only `sys.platform` user in `src/`. `tests/conftest.py:12` `FakePlatform` dataclass. `tests/unit/test_platform.py` has `windows_module` / `macos_module` fixtures that load isolated copies (fake `msvcrt`/`fcntl` off-platform).
- **Copy.** `core/yterrors.py:50` `E_UNKNOWN`; `core/tools.py:124` "ไม่พบตัวช่วยของ yt-dlp (deno)"; `tests/unit/test_tools_status.py:118`, `tests/unit/test_yterrors.py:131`, `tests/api/test_errors.py:63`, `web/e2e/settings-general.spec.ts:233` pin the old texts; `web/src/i18n/th.ts:590` `errors.unknown`.
- **Log file.** `probe.py:64` `setup_file_log` → `RotatingFileHandler(filename, maxBytes=1_000_000, backupCount=3, encoding="utf-8")`; `tests/unit/test_probe.py:109-110` pin it; `test_probe.py:30` asserts `probe` does not import `httpx`.
- **Queue.** `core/queue.py:316` spawn-failure `log.exception`; `:351` summary line; `:362` `JobCancelled` without reason; `:371` `YtError` fail; `:375-376` unexpected exception; `:406` `_fail`; `:430` `_bot_check` final fail. `QueueRunner.store` is the `JobStore`; `JobStore.get(id)` (`core/jobs.py:406`) returns `Job` with `video_id`, `title`, `kind`, `error_code`, `error_detail`. `tests/unit/test_queue.py` `runner_factory(concurrency, fail, handler, spawn)`, `ScriptedHandler` (`fail[video_id]` = code string → `YtError(code, f"fake {code}")`, exception, or list), `jobs_of(kind, n)`.
- **API/app.** `app.py:83-102` `create_app` (routers, then `LocalOnlyMiddleware`); `api/security.py` returns its own 403/421 JSON (`E_FORBIDDEN`); `api/account.py:36` validates by hand; `tests/api/conftest.py` `make_client(**overrides)` (token `test-token`, port 8787, `commit="abc1234"`, `version="0.1.0"`). The SPA mount answers `GET /api/<anything>` with 404 `E_NOT_FOUND`.
- **Privacy canary.** `tests/integration/test_account_privacy.py:91` `test_canaries_never_leave_memory` (`failed` = the failed signed-in job, `CANARIES[3]` = canary cookie name).
- **Web.** `lib/api.ts` `ApiError(status, code, message, detail, body)`, `api()` adds the token for non-GET and throws `E_OFFLINE` with `th.errors.offline`; `lib/clipboard.ts:60-74` `copyImage` (ClipboardItem promise pattern); `components/queue/job-row.tsx:93-151` (`copyDetails`, `FailedRow`); `use-queue.ts:157-196` (`revealWithToast`, `notifyJobChange`), `:244-252` `runJobAction`, `:261-281` `useReorder`; `components/error-panel.tsx`; `components/route-error.tsx` (no `Toaster`; `layout.tsx:102` has it); `pages/settings/health-panel.tsx:75-103` toasts, `:115-128` load error, `:166-175` action row. Vitest is node-only; files mocking `sonner`: `use-queue-events.test.ts`, `use-queue.test.ts`, `lib/jobs.test.ts`, `use-advanced-choice.test.ts`, `capture-store.test.ts`. sonner 2 merges a same-id toast into the old one (`node_modules/sonner/dist/index.mjs:198-213`).
- **E2E.** `e2e/nav.spec.ts:222` expects the old "คัดลอกรายละเอียด" button (T9 changes it); `e2e/queue-flow.spec.ts:195-206`; `e2e/axe-settled.ts` `analyzeSettled(page)`; `e2e/home.spec.ts:639-659` aborts `**/assets/<chunk>-*.js`; `clip-info.spec.ts:195` `context.grantPermissions(["clipboard-read", "clipboard-write"])`.

---

## Global Constraints

**Carried over:** every Global Constraint of `docs/superpowers/plans/2026-10-06-m5c-temporary-youtube-account.md` (and through it M5-B2 … M1): Python 3.13 + uv; bind `127.0.0.1` only; error envelope `{"error":{"code","message","detail"}}`; `pathlib` everywhere; `core/` never imports `api/` or `platform/`; every screen has loading / empty / error / normal; no TODO comments; unit and API tests never touch the network; all web strings live in `web/src/i18n/th.ts`; backend user-facing messages live in `core/yterrors.MESSAGES`; at most one amber primary button per page area.

**Project rules (owner, verbatim — hard rules):**
- Never use `shell=True` (no `os.system` / `os.popen`; external programs get an argument list). No new subprocess in this round (C1).
- Only `yttoolkit.platform` checks the OS (no `sys.platform`, `os.name`, `platform.system()`, `sys.getwindowsversion()`, `platform.mac_ver()` outside `src/yttoolkit/platform/`; C2).
- `yt_dlp` may be imported only in `src/yttoolkit/core/extractor.py` (application code). `core/diagnostics.py` and `api/diagnostics.py` import neither `yt_dlp` nor `extractor` (C3).
- No personal data, tokens, cookie names or values, absolute paths or clip titles in logs, SSE, API errors or the report (C4). Paths under home appear only as `~\...`; traceback frame lines `File "...", line N` keep their app-code path after home redaction.
- One redaction function per output: the report through `redact.redact_report` in `build_report` only; the `job_failed` line through `redact.redact_log_detail` in `core/queue.py` only; `HomePathFilter` / `SecretFilter` stay (C5).
- LF line endings in every file except `*.bat` (C7).
- Thai UI copy only from the spec, the PRD or the existing `th.ts`, never invented; buttons start with a verb, no "กรุณา", no "!" (C8). New log lines use ASCII `key=value` fields.
- Every commit trailer is exactly `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
- Never touch port 8787; kill processes by PID only.
- Target a 640 px narrow window (or 200 % zoom): `document.documentElement.scrollWidth <= 640`; no new phone polish (C9).
- `web/dist` is committed only at the final gate, after `npm run build`.
- Chromium e2e specs never create real jobs and mock the API; the `queue` Playwright project runs with `--workers=1`.
- The report endpoint is a token-protected `POST`; nothing adds a GET that returns log content (C10).
- No new dependencies, Python or npm; Vitest stays node-only (C11).

**Tests:**
- Backend: `uv run pytest -q -W error -p no:cacheprovider` (no warnings).
- Web: `cd web && npm run typecheck && npm run lint && npm test` (ESLint 0 errors / 0 warnings).
- Final: `cd web && npm run build` then `npm run e2e`.

---

## Review Focus (inputs the spec implies that would most likely bite a real user)
1. **A clip id or code that breaks the server's body rules** (`/v/abc` typed by hand, `ApiError` code from an odd envelope, a 6,000-character job detail) → the button still copies a report, never a 422 toast. Pinned by T4 `cleanRequest` tests ("videoId / jobId / context ที่ผิดรูปถูกทิ้ง…", "detail ยาวเกิน = ตัดที่ 4,000 ตัว") and T4 `fetchReport` test (body is cleaned).
2. **A paths repr with doubled backslashes or spaces** (`OSError` `'D:\\งาน ตัดต่อ\\คลิป ยาว.mp4'`, `'~\\Downloads\\a b.mp4'`, `file:///C:/Users/...`, `C%3A%5CUsers%5C...`) → `<path>` / `~` without eating the home-relative part. Pinned by T1 `test_mask_user_paths_quoted_oserror_repr_with_spaces`, `test_mask_user_paths_keeps_tilde_urls_and_traceback_frames` (doubled-backslash `~` case), `test_percent_encoded_and_file_url_home_forms_are_tilde`, T11 `test_job_report_has_every_prd_heading_and_no_personal_data`.
3. **A success toast after an error toast with the same id** (a failed job retried and finished, settings saved after a failed save, ffmpeg reinstall after a failure) → the success toast has no copy button and closes by itself. Pinned by T4 `PLAIN_TOAST` model test and T9 `use-queue-events.test.ts` "งานที่เคยพลาดแล้วเสร็จ…" test, T10 health/settings code using `PLAIN_TOAST`.
4. **A cut that lands inside a home path** (a 300-character log line or a 2,000-character detail whose end is `C:\Users\<name>\...`) → no half username. Pinned by T6 `test_caps_apply_after_redaction_so_a_cut_never_leaks_half_a_username`.
5. **The report endpoint's own log line or a request without the token** → the report never contains its own `diagnostics` line, and a request without the token gets 403 with no report. Pinned by T11 `test_the_report_never_contains_its_own_log_line`, `test_no_token_or_a_foreign_origin_is_403`.

---

## Shared contracts (every lane codes against these)

### K1. Redaction (`src/yttoolkit/redact.py`, T1)
```python
PATH_MASK = "<path>"; TITLE_MASK = "<title>"; URL_MASK = "<url>"; TITLE_MIN = 4; TITLE_PREFIX = 16
def mask_user_paths(text: str) -> str
def mask_media_urls(text: str) -> str
def scrub_titles(text: str, titles: Iterable[str]) -> str
def redact_log_detail(text: str, titles: Iterable[str] = ()) -> str      # home → secrets → paths → media URLs → titles
def redact_report(text: str, *, token: str, titles: Iterable[str] = ()) -> str   # + token → <hidden>, cookie names → <hidden>
```
`redact_home` additionally matches `quote(form, safe="")` and `quote(form.replace("\\", "/"), safe="/")` of every home form.

### K2. OS version (T2)
`Platform.os_version(self) -> str` — Windows `"Windows 11 (10.0.26200)"` / `"Windows 10 (10.0.19045)"` / `"Windows"`; macOS `"macOS 15.6"` / `"macOS"`. `FakePlatform.os_version_text: str = "Windows 11 (10.0.26200)"`, `FakePlatform.os_version()`.

### K3. Report builder (`src/yttoolkit/core/diagnostics.py`, T6)
```python
@dataclass(frozen=True)
class ErrorSection: code: str | None; detail: str | None; kind: str | None = None; video_id: str | None = None; context: str | None = None
@dataclass(frozen=True)
class ReportInputs: now: datetime; version: str; commit: str | None; os_version: str; ytdlp: ToolStatus; ffmpeg: ToolStatus
                    js_runtime: ToolStatus; account_active: bool; error: ErrorSection | None; log_dir: Path; token: str; titles: tuple[str, ...]
def build_report(inputs: ReportInputs) -> str
DETAIL_MAX = 2000; LOG_LINE_MAX = 300; REPORT_MAX = 8000; LOG_FILES = ("app.log", "app.log.1", "app.log.2")
```

### K4. Queue log (T7)
`core/queue.py`: `JOB_FAILED_DETAIL_MAX = 2000`; `job_failed_message(job, code, detail, exc) -> str`; `log_job_failed(job, code, detail, exc) -> None`; `QueueRunner._fail(job, ctx, code, message, detail, exc=None)`.
Line: `job_failed id=<id> kind=<kind> code=<code> detail=<redacted, ≤2000, \n escaped>` + `\n<redacted traceback>` when `exc` is set. WARNING for `YtError` / no exception, ERROR otherwise.

### K5. API (T11)
`POST /api/diagnostics` body keys `jobId` `^[A-Za-z0-9_-]{1,64}$`, `code` `^E_[A-Z0-9_]{1,40}$`, `detail` ≤ 4,000, `context` `^[a-z][a-z0-9-]{0,31}$`, `videoId` `^[A-Za-z0-9_-]{11}$` → `200 {"report": str}` + `Cache-Control: no-store`; 422 `E_BAD_REQUEST` details: `body must be a JSON object` · `body has an unknown field` · `<key> must be a string` · `<key> must match ^<rule>$` · `detail longer than 4000 characters`. Log `INFO diagnostics code=<c|-> context=<c|-> job=<id|->`. `api/errors.py` `ErrorLogMiddleware` → `api_error method=<M> path=<path> status=<n> code=<code|?>` (404 DEBUG, ≥ 500 WARNING, else INFO).

### K6. Web (T4)
```ts
// web/src/i18n/th.ts  errors.*
copyReport: "คัดลอกข้อมูลแจ้งปัญหา", details: "ดูรายละเอียด", code: "รหัส {code}", copied: "คัดลอกแล้ว", copyFailed: "คัดลอกไม่สำเร็จ ลองอีกครั้ง"
unknown: 'มีบางอย่างผิดพลาด กด "คัดลอกข้อมูลแจ้งปัญหา" แล้วส่งให้ผู้ดูแล'
// web/src/lib/report.ts
export const MAX_DETAIL = 4000; export const STACK_LINES = 10
export type ReportRequest = { jobId?: string; code?: string; detail?: string; context?: string; videoId?: string }
export type ReportWhere = { context: string; videoId?: string; jobId?: string }
export type CopyOutcome = { ok: true } | { ok: false; message: string }
export function cleanRequest(req: ReportRequest): ReportRequest
export function reportRequest(error: unknown, where: ReportWhere): ReportRequest
export function fetchReport(req: ReportRequest, deps?): Promise<string>
export function copyReport(req: ReportRequest, deps?): Promise<CopyOutcome>     // never throws
// web/src/components/error-report/model.ts
export const REPORT_TOAST_ID = "report-copy"
export type ToastButton = { label: string; onClick: () => void }
export type ErrorToastOptions = { request: ReportRequest; id?: string | number; description?: ReactNode; action?: ToastButton; cancel?: ToastButton }
export type DetailsSource = ({ error: unknown } & ReportWhere) | { request: ReportRequest }
export function detailsRequest(source: DetailsSource): ReportRequest
export function detailsOpenByDefault(code: string | undefined, defaultOpen?: boolean): boolean
export function errorToastSettings(opts): { id; duration: Infinity; action; cancel }
export const PLAIN_TOAST = { description: undefined, duration: undefined, action: undefined, cancel: undefined }
// components
export function CopyReportButton(props: { request: ReportRequest; variant?: "outline" | "default"; size?: "sm" | "default"; className?: string })
export function ErrorDetails(props: DetailsSource & { defaultOpen?; open?; onOpenChange?; className? })   // data-testid="error-details", trigger data-details-trigger=""
export function showErrorToast(message: string, opts: ErrorToastOptions): string | number
```

### K7. Call-site contexts and toast ids (spec §1.3, used by T8-T10 and T12)
Inline: `video-header`, `video-subtitles`, `video-subs-preview`, `video-transcript`, `video-frames`, `video-pinned` (all + `videoId`), `history`, `batch`, `home`, `home-playlist`, `settings-advanced`, `settings-general`, `health-load`, `queue` (+ `jobId`), `chunk` / `crash` (ErrorPanel), `health` (health button, no error).
Toasts (`context` → `id`): failed job (request `{jobId, code, detail, context: "queue"}`) → `job-<id>`; `capture` → `capture-error`; `enqueue` → `enqueue-error`; `settings-general` → `settings-general` (save) / `settings-open` (open folder); `frames-download` → the loading-toast id; `capture-download` → the loading-toast id, `capture-delete`, `capture-reveal`; `analyze` → `analyze-error`; `ffmpeg-install` → `ffmpeg`; `shutdown` → `shutdown-error`; `video-refresh` → `video-refresh`; `queue-action` → `queue-action-<id>`; `queue-reorder`; `queue-resume`; `account-delete`; `queue-reveal` → `queue-reveal-<id>`; `advanced-save`.

---

## File structure

**Backend (new):** `core/diagnostics.py` (T6) · `api/diagnostics.py` (T11).
**Backend (modified):** `redact.py` (T1) · `platform/base.py`, `windows.py`, `macos.py` (T2) · `core/tools.py`, `core/yterrors.py`, `probe.py` (T3) · `core/queue.py` (T7) · `api/errors.py`, `app.py` (T11).
**Tests (new):** `tests/unit/test_diagnostics.py` (T6) · `tests/api/test_diagnostics_api.py` (T11).
**Tests (modified):** `test_redact.py` (T1) · `tests/conftest.py`, `test_platform.py` (T2) · `test_tools_status.py`, `test_yterrors.py`, `test_probe.py`, `tests/api/test_errors.py` (T3) · `test_queue.py` (T7) · `tests/integration/test_account_privacy.py` (T11).
**Web (new):** `lib/report.ts` + test, `components/error-report/{model.ts, model.test.ts, copy-report-button.tsx, error-details.tsx, error-toast.tsx, error-toast.test.ts}` (T4) · `e2e/error-report.spec.ts` (T12).
**Web (modified):** `th.ts`, `e2e/settings-general.spec.ts` (T4) · clip page + history + batch files (T8) · queue/crash/account files, `th.ts` (remove one key), `e2e/nav.spec.ts`, `e2e/queue-flow.spec.ts` (T9) · home/settings/`lib/jobs.ts` files (T10).
**Docs (modified):** `PRD.md`, `docs/acceptance.md`, `docs/m1-followups.md`, `docs/m4-followups.md` (T5).

---

## Wave 1

### Task 1: Redaction helpers for the job-failure log line and the report (`redact.py`)

**Files:**
- Modify: `src/yttoolkit/redact.py`
- Modify: `tests/unit/test_redact.py`

**Interfaces:**
- Consumes: `redact_home`, `redact_secrets`, `_home_aliases`, `_NAMES`, `MASK`, `SIGN_IN_COOKIE_NAMES` (same module); `yttoolkit.core.files.safe_component(text, fallback)` (stdlib only, imported lazily).
- Produces: K1 exactly — `PATH_MASK`, `TITLE_MASK`, `URL_MASK`, `TITLE_MIN`, `TITLE_PREFIX`, `mask_user_paths`, `mask_media_urls`, `scrub_titles`, `redact_log_detail(text, titles=())`, `redact_report(text, *, token, titles=())`; `redact_home` also hides percent-encoded home forms.

- [ ] **Step 1: Write the failing tests**

In `tests/unit/test_redact.py` replace
```python
from pathlib import Path
```
with
```python
from pathlib import Path, PureWindowsPath
```

Then append at the end of the file (after `test_redact_module_does_not_load_the_web_stack`):
```python
# ---------- M6 รอบ B: path นอกโฟลเดอร์ผู้ใช้ ลิงก์ไฟล์ของยูทูป ชื่อคลิป token และชื่อคุกกี้ ----------

HOME = PureWindowsPath("C:/Users/somchai")
TITLE = "คลิปสอนทำขนม: วิธีทำบัวลอย | ตอนที่ 1"


@pytest.fixture
def somchai_home(monkeypatch):
    """โฟลเดอร์ผู้ใช้ปลอมแบบ Windows (แบบเดียวกับ tests/api/test_errors.py) ไม่มีชื่อสั้นแบบ 8.3"""
    monkeypatch.setattr(errors.Path, "home", lambda: HOME)
    monkeypatch.setattr(redact, "_home_aliases", lambda home: ())


@pytest.mark.parametrize(
    "text",
    [
        "open file:///C:/Users/somchai/Downloads/a.mp4 failed",
        "url=file:///c:/users/SOMCHAI/x",
        "path=C%3A%5CUsers%5Csomchai%5CDownloads",
        "path=C%3a%5cusers%5cSomchai%5cDownloads",
        "path=C%3A/Users/somchai/Downloads",
    ],
)
def test_percent_encoded_and_file_url_home_forms_are_tilde(somchai_home, text: str) -> None:
    out = redact.redact_home(text)
    assert "somchai" not in out.lower()
    assert "~" in out


def test_percent_encoded_home_keeps_the_sibling_guard(somchai_home) -> None:
    assert redact.redact_home("C%3A%5CUsers%5Csomchaiyo") == "C%3A%5CUsers%5Csomchaiyo"


def test_mask_user_paths_quoted_oserror_repr_with_spaces() -> None:
    text = r"[Errno 28] No space left on device: 'D:\\งาน ตัดต่อ\\คลิป ยาว.mp4' (เขียนไม่ได้)"
    assert redact.mask_user_paths(text) == "[Errno 28] No space left on device: '<path>' (เขียนไม่ได้)"


def test_mask_user_paths_double_quoted_unc_and_bare_paths() -> None:
    assert redact.mask_user_paths(r'open "\\nas\share\my clips\a.mp4"') == 'open "<path>"'
    assert redact.mask_user_paths(r"dest \\nas\share\a.mp4, retry") == "dest <path>, retry"
    assert redact.mask_user_paths("saved to E:/out/a.mp4") == "saved to <path>"
    assert redact.mask_user_paths(r"x (D:\out\a.mp4)") == "x (<path>)"


def test_mask_user_paths_keeps_tilde_urls_and_traceback_frames() -> None:
    kept = (
        r"~\Downloads\a.mp4 and ~/Videos",
        r"'~\\Downloads\\a b.mp4' (repr ของ OSError: backslash สองตัว ไม่ใช่ UNC)",
        "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
        r'  File "C:\yt-dl\src\yttoolkit\core\queue.py", line 360, in _run_job',
        "ratio 16:9 at 1:30",
    )
    for text in kept:
        assert redact.mask_user_paths(text) == text
    frames = 'Traceback:\n  File "D:\\app\\x.py", line 5, in f\nOSError: D:\\out\\a.mp4\n'
    assert redact.mask_user_paths(frames) == 'Traceback:\n  File "D:\\app\\x.py", line 5, in f\nOSError: <path>\n'


def test_mask_media_urls_masks_only_googlevideo() -> None:
    text = (
        "GET https://rr3---sn-abc.googlevideo.com/videoplayback?ip=203.0.113.9&sig=AB 403 · "
        "https://i.ytimg.com/vi/dQw4w9WgXcQ/hq.jpg ok"
    )
    assert redact.mask_media_urls(text) == "GET <url> 403 · https://i.ytimg.com/vi/dQw4w9WgXcQ/hq.jpg ok"


def test_scrub_titles_exact_safe_name_and_truncated_file_name() -> None:
    from yttoolkit.core.files import safe_component

    safe = safe_component(TITLE, "")
    assert safe != TITLE  # ":" และ "|" ใช้ในชื่อไฟล์ไม่ได้
    text = f"title={TITLE}\nfile ~\\Downloads\\{safe} [x].mp4\ncut '~\\Downloads\\{safe[:20]}.mp4'"
    out = redact.scrub_titles(text, (TITLE,))
    assert "บัวลอย" not in out and "สอนทำขนม" not in out
    assert out.count("<title>") == 3
    assert "~\\Downloads\\<title>" in out


def test_scrub_titles_skips_short_titles_and_empty_input() -> None:
    assert redact.scrub_titles("the job failed", ("job",)) == "the job failed"
    assert redact.scrub_titles("anything", ()) == "anything"


def test_redact_log_detail_runs_every_step_in_order(somchai_home) -> None:
    detail = (
        f"C:\\Users\\somchai\\Downloads\\{TITLE}.mp4 · D:\\out\\a.mp4 · SAPISID={CANARY} · "
        "https://r1---sn-x.googlevideo.com/videoplayback?ip=198.51.100.7"
    )
    out = redact.redact_log_detail(detail, (TITLE,))
    assert out.startswith("~\\Downloads\\<title>")
    assert "somchai" not in out and CANARY not in out and "D:\\" not in out and "198.51.100.7" not in out
    assert TITLE not in out and "<path>" in out and "<url>" in out


def test_redact_report_hides_the_token_and_every_sign_in_cookie_name() -> None:
    token = "tok-9f8e7d6c5b4a"
    names = " ".join(f"{name}=v{i}" for i, name in enumerate(redact.SIGN_IN_COOKIE_NAMES))
    out = redact.redact_report(f"token {token} cookies {names}", token=token, titles=())
    assert token not in out
    for name in redact.SIGN_IN_COOKIE_NAMES:
        assert name not in out
    assert out.startswith("token <hidden> cookies <hidden>=<hidden>")


def test_redact_report_keeps_ids_codes_and_ordinary_words() -> None:
    text = r"E_YT_REFUSED job=a1b2 videoId dQw4w9WgXcQ SIDEBAR XSAPISID ~\Downloads"
    assert redact.redact_report(text, token="", titles=()) == text


def test_redact_report_does_not_load_the_web_stack_or_yt_dlp() -> None:
    code = (
        "import sys, yttoolkit.redact as r\n"
        "r.redact_report('C:/x a', token='t', titles=('คลิปทดสอบยาวพอ',))\n"
        "print(','.join(sorted({'httpx', 'fastapi', 'uvicorn', 'starlette', 'yt_dlp'} & set(sys.modules))))\n"
    )
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=60, check=True)
    assert out.stdout.strip() == ""
```

- [ ] **Step 2: Run them, expect FAIL**

Run: `cd "$WORKTREE" && uv run pytest tests/unit/test_redact.py -q -W error -p no:cacheprovider`
Expected: the new tests fail with `AttributeError: module 'yttoolkit.redact' has no attribute 'mask_user_paths'` (and similar), and the percent-encoded home cases fail on `assert "somchai" not in out.lower()`. The 35 old tests still pass.

- [ ] **Step 3: Implement in `src/yttoolkit/redact.py`**

Replace (1) the end of the module docstring and the imports:
```python
  probe.setup_file_log ใส่ให้ app.log ตั้งแต่สร้าง handler (ก่อนโหลด lifecycle) จึงครอบความล้มเหลวตอนเปิดโปรแกรมด้วย
"""

from __future__ import annotations

import functools
import logging
import re
from pathlib import Path
```
with:
```python
  probe.setup_file_log ใส่ให้ app.log ตั้งแต่สร้าง handler (ก่อนโหลด lifecycle) จึงครอบความล้มเหลวตอนเปิดโปรแกรมด้วย
- (M6 รอบ B) mask_user_paths / mask_media_urls / scrub_titles: ปิด path นอกโฟลเดอร์ผู้ใช้ ลิงก์ไฟล์ของยูทูป และชื่อคลิป
  redact_log_detail = ชุดของบรรทัด job_failed ใน app.log · redact_report = ชุดของรายงานแจ้งปัญหา (เพิ่ม token และชื่อคุกกี้)
"""

from __future__ import annotations

import functools
import logging
import re
from collections.abc import Iterable
from pathlib import Path
from urllib.parse import quote
```

Replace (2) the home variants in `redact_home`:
```python
    variants = {
        form
        for name in (home, *_home_aliases(home))
        for form in (name, name.replace("\\", "/"), name.replace("\\", "\\\\"))
    }
```
with:
```python
    forms = {
        form
        for name in (home, *_home_aliases(home))
        for form in (name, name.replace("\\", "/"), name.replace("\\", "\\\\"))
    }
    # M6 รอบ B: แบบ percent-encoded ด้วย (file:///C:/Users/... และ path ใน URL ที่ yt-dlp ยกมา) ตัวพิมพ์ของ %xx ไม่สำคัญ
    variants = forms | {quote(f, safe="") for f in forms} | {quote(f.replace("\\", "/"), safe="/") for f in forms}
```

Replace (3) the end of the file:
```python
    for kind in (HomePathFilter, SecretFilter):
        if not any(isinstance(f, kind) for f in handler.filters):
            handler.addFilter(kind())
```
with:
```python
    for kind in (HomePathFilter, SecretFilter):
        if not any(isinstance(f, kind) for f in handler.filters):
            handler.addFilter(kind())


# ---------- M6 รอบ B: บรรทัด job_failed ใน app.log และรายงานแจ้งปัญหา ----------

PATH_MASK = "<path>"
TITLE_MASK = "<title>"
URL_MASK = "<url>"
TITLE_MIN = 4  # ชื่อคลิปที่สั้นกว่านี้ไม่ปิด (จะไปโดนคำธรรมดา)
TITLE_PREFIX = 16  # ชื่อไฟล์ที่ถูกตัดสั้น: ขึ้นต้นด้วย 16 ตัวแรกของชื่อไฟล์ของคลิป = ถือว่าเป็นชื่อคลิป
# ไดรฟ์ (C:\ หรือ C:/) หรือ UNC (\\server\share\) · ตัวอักษรที่ติดคำก่อนหน้าไม่ใช่ไดรฟ์ (https:// ไม่ใช่ไดรฟ์ s:)
# UNC เริ่มได้แค่ต้นข้อความหรือหลังช่องว่าง/อัญประกาศ/วงเล็บ/=,;: ไม่งั้น ~\\Downloads\\ (repr ที่ backslash สองตัว) จะถูกมองเป็น UNC
_ROOT = r"""(?:(?<![A-Za-z0-9])[A-Za-z]:[\\/]|(?<![^\s'"(=,;:])\\\\[^\\/\s'"<>|]+[\\/])"""
_QUOTED_PATH = re.compile(r"""(['"])(""" + _ROOT + r""")[^\r\n]*?\1""")
_BARE_PATH = re.compile(_ROOT + r"""[^\s'"<>|,;)]*""")
_FRAME_LINE = re.compile(r'^\s*File ".*", line \d+')
_MEDIA_URL = re.compile(r"""(?i)https?://(?:[a-z0-9-]+\.)*googlevideo\.com(?::\d+)?(?:[/?#][^\s'"<>]*)?""")
_COOKIE_NAME = re.compile(rf"(?<![A-Za-z0-9_-])(?:{_NAMES})(?![A-Za-z0-9_-])")


def _mask_paths_in_line(line: str) -> str:
    if _FRAME_LINE.match(line):
        return line  # บรรทัด File "...", line N ของ traceback ชี้โค้ดของแอพ (C4): คง path ไว้ (โฟลเดอร์ผู้ใช้เป็น ~ แล้ว)
    line = _QUOTED_PATH.sub(lambda m: f"{m.group(1)}{PATH_MASK}{m.group(1)}", line)
    return _BARE_PATH.sub(PATH_MASK, line)


def mask_user_paths(text: str) -> str:
    """แทน path เต็มที่ไม่อยู่ใต้โฟลเดอร์ผู้ใช้ (ไดรฟ์อื่น โฟลเดอร์แชร์) ด้วย <path> · path ที่เป็น ~ แล้วคงไว้

    path ที่ขึ้นต้นหลังอัญประกาศยาวถึงอัญประกาศปิดตัวเดียวกัน (repr ของ OSError ที่ชื่อมีช่องว่าง)
    ไม่อย่างนั้นยาวถึงช่องว่าง หรือ ' " < > | , ; ) ตัวแรก
    """
    return "".join(_mask_paths_in_line(line) for line in text.splitlines(keepends=True))


def mask_media_urls(text: str) -> str:
    """ลิงก์ไฟล์สื่อของยูทูป (*.googlevideo.com) มีเลข IP ของผู้ใช้และลายเซ็น: แทนด้วย <url>"""
    return _MEDIA_URL.sub(URL_MASK, text)


def scrub_titles(text: str, titles: Iterable[str]) -> str:
    """แทนชื่อคลิปด้วย <title>: ชื่อตรงตัว ชื่อแบบที่ใช้เป็นชื่อไฟล์ (safe_component) และชื่อไฟล์ที่ถูกตัดสั้น"""
    from .core.files import safe_component  # stdlib ล้วน import ตอนใช้ probe จะได้ไม่โหลด core

    for title in titles:
        if len(title) < TITLE_MIN:
            continue
        text = text.replace(title, TITLE_MASK)
        safe = safe_component(title, "")
        if len(safe) >= TITLE_MIN and safe != title:
            text = text.replace(safe, TITLE_MASK)
        if len(safe) >= TITLE_PREFIX:
            text = re.sub(re.escape(safe[:TITLE_PREFIX]) + r"""[^\\/'"\r\n]*""", TITLE_MASK, text)
    return text


def redact_log_detail(text: str, titles: Iterable[str] = ()) -> str:
    """ชุดซ่อนข้อมูลของบรรทัด job_failed ใน app.log (เรียกที่เดียว: core/queue.py)

    โฟลเดอร์ผู้ใช้ → ค่าคุกกี้ → path อื่น → ลิงก์ไฟล์ของยูทูป → ชื่อคลิป
    """
    text = mask_media_urls(mask_user_paths(redact_secrets(redact_home(text))))
    return scrub_titles(text, tuple(titles))


def redact_report(text: str, *, token: str, titles: Iterable[str] = ()) -> str:
    """ชุดซ่อนข้อมูลของรายงานแจ้งปัญหา (เรียกที่เดียว: core/diagnostics.build_report)

    = redact_log_detail + token ของแอพเป็น <hidden> + ชื่อคุกกี้เข้าสู่ระบบทั้งคำเป็น <hidden> (รายงานไม่มีชื่อคุกกี้เลย FR-CK-5)
    """
    text = redact_log_detail(text, titles)
    if token:
        text = text.replace(token, MASK)
    return _COOKIE_NAME.sub(MASK, text)
```

Notes for the implementer:
- `_ROOT`'s UNC branch only starts at a boundary (planner ruling P8): without the `(?<![^\s'"(=,;:])` look-behind, `'~\\Downloads\\a b.mp4'` (an `OSError` repr after home redaction) is masked as a UNC path, which the test `test_mask_user_paths_keeps_tilde_urls_and_traceback_frames` pins.
- `scrub_titles` imports `safe_component` inside the function so `import yttoolkit.redact` still loads nothing from `core` (probe runs it before the web stack).

- [ ] **Step 4: Run the tests, expect PASS**

Run: `cd "$WORKTREE" && uv run pytest tests/unit/test_redact.py -q -W error -p no:cacheprovider`
Expected: 51 passed. Then the full suite: `cd "$WORKTREE" && uv run pytest -q -W error -p no:cacheprovider` (only `tests/unit/test_yterrors.py::test_messages_match_prd_table` may fail, pre-existing, fixed by T3 — planner ruling P10).

- [ ] **Step 5: Commit**
```bash
cd "$WORKTREE" && git add src/yttoolkit/redact.py tests/unit/test_redact.py && git commit -F- <<'EOF'
feat(redact): mask other-drive paths, media URLs, clip titles; report and job-log redaction

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
EOF
```


### Task 2: `Platform.os_version()` and the "only `yttoolkit.platform` checks the OS" guard

**Files:**
- Modify: `src/yttoolkit/platform/base.py`, `src/yttoolkit/platform/windows.py`, `src/yttoolkit/platform/macos.py`
- Modify: `tests/conftest.py` (`FakePlatform`)
- Modify: `tests/unit/test_platform.py`

**Interfaces:**
- Consumes: the `windows_module` / `macos_module` fixtures in `tests/unit/test_platform.py`.
- Produces: K2 — `Platform.os_version() -> str`, `WindowsPlatform.os_version`, `MacPlatform.os_version`, `FakePlatform.os_version_text` + `os_version()` (T11 reads `ctx.plat.os_version()`).

- [ ] **Step 1: Write the failing tests**

In `tests/unit/test_platform.py` replace
```python
import os
import subprocess
import sys
import types
```
with
```python
import os
import re
import subprocess
import sys
import types
```

Append at the end of the file:
```python
# ---- M6 รอบ B: ชื่อและเลขรุ่นของระบบปฏิบัติการ (บรรทัด "ระบบ:" ของรายงานแจ้งปัญหา) ------------------------------


def _winver(major: int, minor: int, build: int):
    return lambda: types.SimpleNamespace(major=major, minor=minor, build=build)


@pytest.mark.parametrize(
    ("version", "expected"),
    [
        ((10, 0, 26200), "Windows 11 (10.0.26200)"),
        ((10, 0, 22000), "Windows 11 (10.0.22000)"),
        ((10, 0, 19045), "Windows 10 (10.0.19045)"),
        ((6, 3, 9600), "Windows 6 (6.3.9600)"),
    ],
)
def test_windows_os_version_names_11_by_build(windows_module, monkeypatch, version, expected):
    monkeypatch.setattr(windows_module.sys, "getwindowsversion", _winver(*version), raising=False)
    assert windows_module.WindowsPlatform().os_version() == expected


def test_windows_os_version_falls_back_when_unreadable(windows_module, monkeypatch):
    def broken():
        raise OSError("no version")

    monkeypatch.setattr(windows_module.sys, "getwindowsversion", broken, raising=False)
    assert windows_module.WindowsPlatform().os_version() == "Windows"


@pytest.mark.parametrize(("release", "expected"), [("15.6", "macOS 15.6"), ("", "macOS")])
def test_macos_os_version(macos_module, monkeypatch, release, expected):
    monkeypatch.setattr(macos_module.platform, "mac_ver", lambda: (release, ("", "", ""), ""))
    assert macos_module.MacPlatform().os_version() == expected


@pytest.mark.skipif(sys.platform != "win32", reason="อ่านเลขรุ่นของ Windows จริง")
def test_windows_os_version_live():
    text = current().os_version()
    assert text.startswith("Windows ")
    assert text.endswith(")") and "(10." in text


# ---- กฎของโปรเจกต์: เช็กระบบปฏิบัติการได้ที่ yttoolkit.platform ที่เดียว (M6 รอบ B C2) ------------------------------

SRC = Path(__file__).resolve().parents[2] / "src" / "yttoolkit"
_OS_CHECK = re.compile(r"\bsys\.platform\b|\bos\.name\b|\bplatform\.(?:system|release|version|mac_ver|win32_ver)\(|getwindowsversion")


def test_only_the_platform_package_checks_the_os():
    offenders = [
        f"{path.relative_to(SRC).as_posix()}:{n}"
        for path in sorted(SRC.rglob("*.py"))
        if path.relative_to(SRC).parts[0] != "platform"
        for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1)
        if _OS_CHECK.search(line)
    ]
    assert offenders == []


def test_os_check_detector():
    for line in ("if sys.platform == 'win32':", "os.name == 'nt'", "platform.system()", "sys.getwindowsversion()"):
        assert _OS_CHECK.search(line), line
    for line in ("platform.os_version()", "ctx.plat.name", "from ..platform import Platform"):
        assert not _OS_CHECK.search(line), line
```

- [ ] **Step 2: Run them, expect FAIL**

Run: `cd "$WORKTREE" && uv run pytest tests/unit/test_platform.py -q -W error -p no:cacheprovider`
Expected: the `os_version` tests fail with `AttributeError: 'WindowsPlatform' object has no attribute 'os_version'` (and `module ... has no attribute 'sys'` / `'platform'` on the module patches); `test_only_the_platform_package_checks_the_os` and `test_os_check_detector` already pass (the tree is clean today — they guard the future).

- [ ] **Step 3: Implement**

`src/yttoolkit/platform/base.py` — replace
```python
    def path_aliases(self, path: Path) -> list[str]:
        """ชื่ออื่นที่ชี้ไปที่เดียวกับ path (Windows: ชื่อสั้นแบบ 8.3) ใช้ตัดชื่อผู้ใช้ออกจากข้อความ error"""
        ...
```
with
```python
    def path_aliases(self, path: Path) -> list[str]:
        """ชื่ออื่นที่ชี้ไปที่เดียวกับ path (Windows: ชื่อสั้นแบบ 8.3) ใช้ตัดชื่อผู้ใช้ออกจากข้อความ error"""
        ...

    def os_version(self) -> str:
        """ชื่อและเลขรุ่นของระบบปฏิบัติการสำหรับรายงานแจ้งปัญหา"""
        ...
```

`src/yttoolkit/platform/windows.py` — replace (1)
```python
import os
import subprocess
import uuid
```
with
```python
import os
import subprocess
import sys
import uuid
```
and replace (2) the end of the file
```python
        short = buffer.value
        return [short] if short.casefold() != full.casefold() else []
```
with
```python
        short = buffer.value
        return [short] if short.casefold() != full.casefold() else []

    def os_version(self) -> str:
        """ชื่อและเลขรุ่นของระบบปฏิบัติการสำหรับรายงานแจ้งปัญหา เช่น Windows 11 (10.0.26200) (M6 รอบ B)

        Windows 11 ยังรายงาน major 10 จึงดูเลข build ≥ 22000 · ไม่ใช้ platform.release() เพราะ Python รุ่นเก่าบอก 10
        บน Windows 11 · อ่านไม่ได้ = คืนแค่ Windows
        """
        try:
            v = sys.getwindowsversion()
            if v.major == 10 and v.build >= 22000:
                name = "Windows 11"
            elif v.major == 10:
                name = "Windows 10"
            else:
                name = f"Windows {v.major}"
            return f"{name} ({v.major}.{v.minor}.{v.build})"
        except Exception:
            return "Windows"
```

`src/yttoolkit/platform/macos.py` — replace (1)
```python
import fcntl
import os
import signal
```
with
```python
import fcntl
import os
import platform
import signal
```
and replace (2) the end of the file
```python
    def path_aliases(self, path: Path) -> list[str]:
        return []
```
with
```python
    def path_aliases(self, path: Path) -> list[str]:
        return []

    def os_version(self) -> str:
        """ชื่อและเลขรุ่นสำหรับรายงานแจ้งปัญหา เช่น macOS 15.6 (M6 รอบ B: ให้ protocol ครบ · macOS จริงมาใน M7)"""
        # platform ตัวนี้คือโมดูลของ stdlib (import แบบ absolute) ไม่ใช่แพ็กเกจ yttoolkit.platform
        release = platform.mac_ver()[0]
        return f"macOS {release}" if release else "macOS"
```

`tests/conftest.py` — replace (1)
```python
    aliases: list[str] = field(default_factory=list)  # ชื่ออื่นของ path (Windows: ชื่อสั้นแบบ 8.3)
```
with
```python
    aliases: list[str] = field(default_factory=list)  # ชื่ออื่นของ path (Windows: ชื่อสั้นแบบ 8.3)
    os_version_text: str = "Windows 11 (10.0.26200)"  # M6 รอบ B: บรรทัด "ระบบ:" ของรายงานแจ้งปัญหา
```
and replace (2)
```python
    def path_aliases(self, path: Path) -> list[str]:
        return list(self.aliases)
```
with
```python
    def path_aliases(self, path: Path) -> list[str]:
        return list(self.aliases)

    def os_version(self) -> str:
        return self.os_version_text
```

- [ ] **Step 4: Run, expect PASS**

Run: `cd "$WORKTREE" && uv run pytest tests/unit/test_platform.py -q -W error -p no:cacheprovider` (36 passed on Windows; the live test is skipped elsewhere), then the full suite.

- [ ] **Step 5: Commit**
```bash
cd "$WORKTREE" && git add src/yttoolkit/platform/base.py src/yttoolkit/platform/windows.py src/yttoolkit/platform/macos.py tests/conftest.py tests/unit/test_platform.py && git commit -F- <<'EOF'
feat(platform): os_version for the problem report; guard that only platform checks the OS

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
EOF
```


### Task 3: Copy fixes (`E_UNKNOWN`, JS-runtime warning) and the 5 MB × 3 log rotation

**Files:**
- Modify: `src/yttoolkit/core/yterrors.py` (`E_UNKNOWN`)
- Modify: `src/yttoolkit/core/tools.py` (`JS_RUNTIME_MISSING_MESSAGE`)
- Modify: `src/yttoolkit/probe.py` (rotation, `httpx` level)
- Modify: `tests/unit/test_yterrors.py`, `tests/unit/test_tools_status.py`, `tests/unit/test_probe.py`, `tests/unit/test_lifecycle.py` (rotation pin at `:463-464`), `tests/api/test_errors.py` (`:63`)

**Interfaces:**
- Consumes: PRD §7 rows (already updated in the spec commit; `test_messages_match_prd_table` compares them).
- Produces: `MESSAGES["E_UNKNOWN"] == 'มีบางอย่างผิดพลาด กด "คัดลอกข้อมูลแจ้งปัญหา" แล้วส่งให้ผู้ดูแล'` (and so `api/errors.UNKNOWN_MESSAGE`); `tools.JS_RUNTIME_MISSING_MESSAGE`; `probe.LOG_MAX_BYTES = 5_000_000`, `probe.LOG_BACKUPS = 2`.

- [ ] **Step 1: Update the tests first**

`tests/unit/test_yterrors.py` — replace
```python
    assert MESSAGES["E_UNKNOWN"] == "มีบางอย่างผิดพลาด ถ่ายภาพหน้าจอนี้ส่งให้ผู้ดูแล"
```
with
```python
    assert MESSAGES["E_UNKNOWN"] == 'มีบางอย่างผิดพลาด กด "คัดลอกข้อมูลแจ้งปัญหา" แล้วส่งให้ผู้ดูแล'  # M6 รอบ B D3
```

`tests/api/test_errors.py` — replace
```python
        "message": "มีบางอย่างผิดพลาด ถ่ายภาพหน้าจอนี้ส่งให้ผู้ดูแล",
```
with
```python
        "message": 'มีบางอย่างผิดพลาด กด "คัดลอกข้อมูลแจ้งปัญหา" แล้วส่งให้ผู้ดูแล',
```

`tests/unit/test_tools_status.py` — replace
```python
    assert status.message == "ไม่พบตัวช่วยของ yt-dlp (deno)"
```
with
```python
    assert status.message == "บางคุณภาพอาจไม่แสดง เพราะเครื่องยังไม่มีตัวช่วยที่ yt-dlp ต้องใช้"  # PRD ข้อ 7 E_JS_RUNTIME_MISSING
```

`tests/unit/test_probe.py` — replace (1)
```python
    assert handler.maxBytes == 1_000_000
    assert handler.backupCount == 3
```
with
```python
    assert handler.maxBytes == 5_000_000  # M6 รอบ B: PRD 7.1 หมุนไฟล์ที่ 5 MB เก็บ 3 ไฟล์ (app.log + .1 + .2)
    assert handler.backupCount == 2
```
and replace (2)
```python
def test_cli_start_logs_crash_and_exits_1(tmp_path, monkeypatch, restore_root_logging):
```
with
```python
def test_setup_file_log_quiets_httpx_info_lines(paths, restore_root_logging):
    httpx_logger = logging.getLogger("httpx")
    before = httpx_logger.level
    try:
        httpx_logger.setLevel(logging.NOTSET)
        probe.setup_file_log(paths)
        assert httpx_logger.level == logging.WARNING  # M6 รอบ B: ไม่มีบรรทัด INFO ของทุกคำขอ (มี URL ภาพเต็ม)
        assert not httpx_logger.isEnabledFor(logging.INFO)
    finally:


def test_cli_start_logs_crash_and_exits_1(tmp_path, monkeypatch, restore_root_logging):
```

`tests/unit/test_lifecycle.py` (inside `test_setup_file_logging_uses_rotating_handler`) — replace
```python
        assert handler.maxBytes == 1_000_000
        assert handler.backupCount == 3
```
with
```python
        assert handler.maxBytes == 5_000_000  # M6 รอบ B: PRD 7.1 หมุนไฟล์ที่ 5 MB เก็บ 3 ไฟล์
        assert handler.backupCount == 2
```

- [ ] **Step 2: Run them, expect FAIL**

Run: `cd "$WORKTREE" && uv run pytest tests/unit/test_yterrors.py tests/unit/test_tools_status.py tests/unit/test_probe.py tests/unit/test_lifecycle.py tests/api/test_errors.py -q -W error -p no:cacheprovider`
Expected: failures on the old `E_UNKNOWN` text (`test_messages_match_prd_table` too), the JS message, `maxBytes == 5_000_000` (got `1000000`) in both probe and lifecycle tests, and `httpx_logger.level == logging.WARNING`.

- [ ] **Step 3: Implement**

`src/yttoolkit/core/yterrors.py` — replace
```python
    "E_UNKNOWN": "มีบางอย่างผิดพลาด ถ่ายภาพหน้าจอนี้ส่งให้ผู้ดูแล",
```
with
```python
    # M6 รอบ B (Pete Q3 = A): หน้าเว็บมีปุ่ม "คัดลอกข้อมูลแจ้งปัญหา" ทุกจุดแล้ว ไม่ต้องถ่ายภาพหน้าจอ
    "E_UNKNOWN": 'มีบางอย่างผิดพลาด กด "คัดลอกข้อมูลแจ้งปัญหา" แล้วส่งให้ผู้ดูแล',
```
(`api/errors.UNKNOWN_MESSAGE = MESSAGES["E_UNKNOWN"]` follows by itself; `start.bat` is **not** touched — Pete spec Q3.)

`src/yttoolkit/core/tools.py` — replace (1)
```python
FFMPEG_INSTALLING_MESSAGE = "กำลังโหลด ffmpeg อาจใช้เวลา 1-3 นาที"
```
with
```python
FFMPEG_INSTALLING_MESSAGE = "กำลังโหลด ffmpeg อาจใช้เวลา 1-3 นาที"
JS_RUNTIME_MISSING_MESSAGE = "บางคุณภาพอาจไม่แสดง เพราะเครื่องยังไม่มีตัวช่วยที่ yt-dlp ต้องใช้"
```
and replace (2)
```python
    return ToolStatus("warn", name=None, message="ไม่พบตัวช่วยของ yt-dlp (deno)")
```
with
```python
    # M6 รอบ B (D2): ข้อความของ E_JS_RUNTIME_MISSING ใน PRD ข้อ 7 เป็นคำเตือนของหน้าตรวจสุขภาพ ไม่ใช่ error ของการโหลด
    return ToolStatus("warn", name=None, message=JS_RUNTIME_MISSING_MESSAGE)
```
(`E_JS_RUNTIME_MISSING` stays out of `yterrors.MESSAGES`; the node fallback "ใช้ node แทน deno" is unchanged; the web shows `tool.message` already.)

`src/yttoolkit/probe.py` — replace (1)
```python
PING_TIMEOUT = 2
```
with
```python
PING_TIMEOUT = 2
# PRD ข้อ 7.1 "หมุนไฟล์ที่ 5 MB เก็บ 3 ไฟล์" (Pete spec Q4): app.log + app.log.1 + app.log.2 รวมไม่เกิน 15 MB
LOG_MAX_BYTES = 5_000_000
LOG_BACKUPS = 2
```
replace (2)
```python
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    target = os.path.abspath(filename)
```
with
```python
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    # M6 รอบ B: httpx เขียน INFO ทุกคำขอพร้อม URL เต็มของภาพ/ปก ให้เหลือแค่ WARNING (ตั้งตามชื่อ ไม่ต้อง import httpx)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    target = os.path.abspath(filename)
```
replace (3)
```python
    handler = logging.handlers.RotatingFileHandler(filename, maxBytes=1_000_000, backupCount=3, encoding="utf-8")
```
with
```python
    handler = logging.handlers.RotatingFileHandler(
        filename, maxBytes=LOG_MAX_BYTES, backupCount=LOG_BACKUPS, encoding="utf-8"
    )
```

- [ ] **Step 4: Run, expect PASS**

Same command as Step 2 (all pass; `test_probe_and_its_imports_do_not_load_the_web_stack` still passes because `httpx` is set by name), then the full suite — it is now fully green (P10 fixed).

- [ ] **Step 5: Commit**
```bash
cd "$WORKTREE" && git add src/yttoolkit/core/yterrors.py src/yttoolkit/core/tools.py src/yttoolkit/probe.py tests/unit/test_yterrors.py tests/unit/test_tools_status.py tests/unit/test_probe.py tests/unit/test_lifecycle.py tests/api/test_errors.py && git commit -F- <<'EOF'
feat: new E_UNKNOWN and JS-runtime texts; app.log rotates at 5 MB keeping 3 files

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
EOF
```


---

> **WIP:** tasks T4-T12, the spec-coverage table and the execution handoff follow in the next commit of this plan. Do not execute before the plan is complete.
