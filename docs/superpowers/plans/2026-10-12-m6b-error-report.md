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
- **P11 — the logged API path is percent-encoded.** `scope["path"]` is already URL-decoded, so `/api/videos/bad%0Aid/captures` would put a line break into `app.log` (the prototype broke `tests/api/test_captures_api.py::test_post_with_a_malformed_id_never_reaches_the_service`). `api_error` logs `urllib.parse.quote(path, safe="/-_.~")`.
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


### Task 4: Web foundation — strings, `lib/report.ts`, `components/error-report/`

**Files:**
- Modify: `web/src/i18n/th.ts` (`errors` section only)
- Create: `web/src/lib/report.ts`, `web/src/lib/report.test.ts`
- Create: `web/src/components/error-report/model.ts`, `model.test.ts`, `copy-report-button.tsx`, `error-details.tsx`, `error-toast.tsx`, `error-toast.test.ts`
- Modify: `web/e2e/settings-general.spec.ts` (`:233` mocked `E_UNKNOWN` envelope text)

**Interfaces:**
- Consumes: `api`, `ApiError` (`lib/api.ts`); `th`, `fill` (`i18n/th.ts`); `Button`, `Spinner`, `Collapsible*` (`components/ui`); sonner `toast`.
- Produces: K6 exactly (strings, `MAX_DETAIL`, `STACK_LINES`, `ReportRequest`, `ReportWhere`, `CopyOutcome`, `cleanRequest`, `reportRequest`, `fetchReport`, `copyReport`, `REPORT_TOAST_ID`, `ToastButton`, `ErrorToastOptions`, `DetailsSource`, `detailsRequest`, `detailsOpenByDefault`, `errorToastSettings`, `PLAIN_TOAST`, `CopyReportButton`, `ErrorDetails`, `showErrorToast`). T8-T10 and T12 use these names only.

No call site uses the new components yet (T8-T10). `th.queue.copyDetails` stays until T9 removes it together with its last user.

- [ ] **Step 1: Write the failing tests**

Create `web/src/lib/report.test.ts`:
```ts
import { describe, expect, it, vi } from "vitest"

import { th } from "@/i18n/th"

import { ApiError } from "./api"
import { cleanRequest, copyReport, fetchReport, MAX_DETAIL, reportRequest, STACK_LINES } from "./report"

const REPORT = "## รายงานปัญหา YT Toolkit\n- เวลา: 2026-10-12 10:00 (+07:00)\n"
const VIDEO = "dQw4w9WgXcQ"

class FakeItem {
  readonly items: Record<string, Promise<Blob> | Blob>
  constructor(items: Record<string, Promise<Blob> | Blob>) {
    this.items = items
  }
}
const Item = FakeItem as unknown as typeof ClipboardItem

function jsonResponse(status: number, body: unknown): Response {
  return new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } })
}

describe("reportRequest", () => {
  it("ApiError = รหัสและ detail จากเซิร์ฟเวอร์ พร้อมหน้าจอและคลิป", () => {
    const error = new ApiError(502, "E_YT_REFUSED", "ยูทูปไม่ยอมส่งไฟล์", "HTTP Error 403: Forbidden", null)
    expect(reportRequest(error, { context: "video-header", videoId: VIDEO })).toEqual({
      code: "E_YT_REFUSED",
      detail: "HTTP Error 403: Forbidden",
      context: "video-header",
      videoId: VIDEO,
    })
  })

  it("ApiError ที่ไม่มี detail = ไม่มีช่อง detail", () => {
    expect(reportRequest(new ApiError(0, "E_OFFLINE", "x", null, null), { context: "crash" })).toEqual({
      code: "E_OFFLINE",
      context: "crash",
    })
  })

  it("Error อื่น = E_UNKNOWN + ชื่อ: ข้อความ + stack ไม่เกิน 10 บรรทัด", () => {
    const error = new TypeError("x is undefined")
    error.stack = Array.from({ length: 30 }, (_, i) => `    at f${i} (app.js:${i})`).join("\n")
    const req = reportRequest(error, { context: "crash" })
    expect(req.code).toBe("E_UNKNOWN")
    const lines = req.detail!.split("\n")
    expect(lines[0]).toBe("TypeError: x is undefined")
    expect(lines).toHaveLength(1 + STACK_LINES)
    expect(lines.at(-1)).toBe("    at f9 (app.js:9)")
  })

  it("ค่าที่ไม่ใช่ error = E_UNKNOWN ไม่มี detail", () => {
    expect(reportRequest("boom", { context: "chunk" })).toEqual({ code: "E_UNKNOWN", context: "chunk" })
    expect(reportRequest(undefined, { context: "chunk" })).toEqual({ code: "E_UNKNOWN", context: "chunk" })
  })

  it("detail ยาวเกิน = ตัดที่ 4,000 ตัว (เซิร์ฟเวอร์ไม่ตอบ 422 กับ error จริง)", () => {
    const error = new ApiError(500, "E_UNKNOWN", "x", "d".repeat(9000), null)
    expect(reportRequest(error, { context: "crash" }).detail).toHaveLength(MAX_DETAIL)
  })
})

describe("cleanRequest: body ผ่านกฎของเซิร์ฟเวอร์เสมอ", () => {
  it("videoId / jobId / context ที่ผิดรูปถูกทิ้ง รหัสที่ผิดรูปเป็น E_UNKNOWN", () => {
    expect(
      cleanRequest({ code: "boom", videoId: "abc", jobId: "../x", context: "Video Header", detail: "d" }),
    ).toEqual({ code: "E_UNKNOWN", detail: "d" })
  })

  it("ค่าที่ถูกต้องผ่านครบ · detail ว่างไม่ส่ง", () => {
    const ok = { jobId: "01a1-b_2", code: "E_HTTP_502", context: "queue", videoId: VIDEO }
    expect(cleanRequest({ ...ok, detail: "" })).toEqual(ok)
  })
})

describe("fetchReport", () => {
  it("POST /api/diagnostics พร้อม token และ body ที่ทำความสะอาดแล้ว คืนข้อความรายงาน", async () => {
    const fetch = vi.fn().mockResolvedValue(jsonResponse(200, { report: REPORT }))
    await expect(fetchReport({ code: "E_NETWORK", videoId: "bad" }, { fetch, token: "tok" })).resolves.toBe(REPORT)
    const [url, init] = fetch.mock.calls[0]
    expect(url).toBe("/api/diagnostics")
    expect(init.method).toBe("POST")
    expect(new Headers(init.headers).get("X-Toolkit-Token")).toBe("tok")
    expect(JSON.parse(init.body)).toEqual({ code: "E_NETWORK" })
  })
})

// unhandled rejection ใด ๆ ทำให้ vitest ล้มทั้งชุดเอง จึงไม่ต้องดักเพิ่ม (ทุกกรณีข้างล่างต้องไม่มี)
describe("copyReport", () => {
  it("มี ClipboardItem = เขียนทันทีด้วย text/plain ที่เป็น Promise (ยังอยู่ในจังหวะที่ผู้ใช้กด)", async () => {
    let resolve: (text: string) => void = () => {}
    const fetchReport = vi.fn(() => new Promise<string>((r) => (resolve = r)))
    const write = vi.fn(async (items: ClipboardItems) => {
      const blob = await (items[0] as unknown as FakeItem).items["text/plain"]
      expect(await blob.text()).toBe(REPORT)
    })
    const done = copyReport({ code: "E_X" }, { clipboard: { write }, ClipboardItem: Item, fetchReport })
    expect(write).toHaveBeenCalledTimes(1) // ก่อนรายงานมาถึง
    expect(fetchReport).toHaveBeenCalledWith({ code: "E_X" })
    resolve(REPORT)
    await expect(done).resolves.toEqual({ ok: true })
  })

  it("ไม่มี ClipboardItem = รอรายงานแล้ว writeText", async () => {
    const writeText = vi.fn(async () => {})
    const outcome = await copyReport({}, { clipboard: { writeText }, ClipboardItem: undefined, fetchReport: async () => REPORT })
    expect(outcome).toEqual({ ok: true })
    expect(writeText).toHaveBeenCalledWith(REPORT)
  })

  it("เซิร์ฟเวอร์ตอบ error = ข้อความของเซิร์ฟเวอร์", async () => {
    const write = vi.fn(async (items: ClipboardItems) => {
      await (items[0] as unknown as FakeItem).items["text/plain"]
    })
    const fetchReport = () => Promise.reject(new ApiError(422, "E_BAD_REQUEST", "ข้อมูลที่ส่งมาไม่ถูกต้อง ลองรีเฟรชหน้าเว็บ", null, null))
    await expect(copyReport({}, { clipboard: { write }, ClipboardItem: Item, fetchReport })).resolves.toEqual({
      ok: false,
      message: "ข้อมูลที่ส่งมาไม่ถูกต้อง ลองรีเฟรชหน้าเว็บ",
    })
  })

  it("ปิดโปรแกรมไปแล้ว (E_OFFLINE) = th.errors.offline", async () => {
    const fetch = vi.fn().mockRejectedValue(new TypeError("Failed to fetch"))
    const writeText = vi.fn(async () => {})
    const outcome = await copyReport(
      {},
      { clipboard: { writeText }, ClipboardItem: undefined, fetchReport: (req) => fetchReport(req, { fetch, token: "t" }) },
    )
    expect(outcome).toEqual({ ok: false, message: th.errors.offline })
    expect(writeText).not.toHaveBeenCalled()
  })

  it("error ที่ไม่ใช่ ApiError ตอนขอรายงาน = th.errors.unknown", async () => {
    const outcome = await copyReport({}, { clipboard: { writeText: vi.fn() }, ClipboardItem: undefined, fetchReport: () => Promise.reject(new Error("x")) })
    expect(outcome).toEqual({ ok: false, message: th.errors.unknown })
  })

  it("คลิปบอร์ดไม่ยอม = th.errors.copyFailed (คัดลอกไม่สำเร็จ ลองอีกครั้ง)", async () => {
    const write = vi.fn(() => Promise.reject(new DOMException("Document is not focused", "NotAllowedError")))
    const outcome = await copyReport({}, { clipboard: { write }, ClipboardItem: Item, fetchReport: async () => REPORT })
    expect(outcome).toEqual({ ok: false, message: "คัดลอกไม่สำเร็จ ลองอีกครั้ง" })
  })

  it("ไม่มีคลิปบอร์ดเลย = copyFailed", async () => {
    await expect(copyReport({}, { clipboard: undefined, ClipboardItem: undefined, fetchReport: async () => REPORT })).resolves.toEqual({
      ok: false,
      message: th.errors.copyFailed,
    })
  })
})
```

Create `web/src/components/error-report/model.test.ts`:
```ts
import { describe, expect, it } from "vitest"

import { ApiError } from "@/lib/api"

import { detailsOpenByDefault, detailsRequest, errorToastSettings, PLAIN_TOAST } from "./model"

describe("detailsRequest", () => {
  it("จาก error ที่จับได้ + ที่ที่เกิด", () => {
    const error = new ApiError(502, "E_YT_REFUSED", "x", "HTTP Error 403", null)
    expect(detailsRequest({ error, context: "video-frames", videoId: "dQw4w9WgXcQ" })).toEqual({
      code: "E_YT_REFUSED",
      detail: "HTTP Error 403",
      context: "video-frames",
      videoId: "dQw4w9WgXcQ",
    })
  })

  it("จาก body ที่ประกอบไว้ (แถวงานในคิว) ผ่าน cleanRequest", () => {
    expect(detailsRequest({ request: { jobId: "j1", code: "E_NETWORK", detail: "d".repeat(5000), context: "queue" } })).toEqual({
      jobId: "j1",
      code: "E_NETWORK",
      detail: "d".repeat(4000),
      context: "queue",
    })
  })
})

describe("detailsOpenByDefault (planner ruling R1)", () => {
  it("E_UNKNOWN กางเอง รหัสอื่นพับไว้", () => {
    expect(detailsOpenByDefault("E_UNKNOWN")).toBe(true)
    expect(detailsOpenByDefault("E_NETWORK")).toBe(false)
    expect(detailsOpenByDefault(undefined)).toBe(false)
  })

  it("ผู้เรียกกำหนดเองได้", () => {
    expect(detailsOpenByDefault("E_UNKNOWN", false)).toBe(false)
    expect(detailsOpenByDefault("E_NETWORK", true)).toBe(true)
  })
})

describe("errorToastSettings", () => {
  it("ค้างจนกดปิด (D1) ส่ง id action cancel ต่อไปตรง ๆ", () => {
    const action = { label: "a", onClick: () => {} }
    const cancel = { label: "c", onClick: () => {} }
    expect(errorToastSettings({ id: "job-1", action, cancel })).toEqual({ id: "job-1", duration: Infinity, action, cancel })
    expect(errorToastSettings({})).toEqual({ id: undefined, duration: Infinity, action: undefined, cancel: undefined })
  })
})

describe("PLAIN_TOAST (planner ruling P5)", () => {
  it("ล้างทุกช่องที่ toast error ตั้งไว้ เมื่อ toast อื่นใช้ id เดียวกัน", () => {
    // แบบเดียวกับที่ sonner รวม toast ใหม่ทับ toast เดิมที่ id เดียวกัน: { ...เดิม, ...ใหม่ }
    const errorToast: Record<string, unknown> = { ...errorToastSettings({ id: "x", action: { label: "a", onClick: () => {} } }), description: "btn" }
    const merged = { ...errorToast, ...PLAIN_TOAST }
    expect(merged).toEqual({ id: "x", duration: undefined, action: undefined, cancel: undefined, description: undefined })
  })
})
```

Create `web/src/components/error-report/error-toast.test.ts`:
```ts
import type { ReactElement, ReactNode } from "react"
import { beforeEach, describe, expect, it, vi } from "vitest"

const toast = vi.hoisted(() => ({ error: vi.fn(() => "t1"), success: vi.fn() }))
vi.mock("sonner", () => ({ toast }))

import { CopyReportButton } from "./copy-report-button"
import { showErrorToast } from "./error-toast"

type Options = { id?: string; duration?: number; action?: unknown; cancel?: unknown; description: ReactElement<{ children: ReactNode[] }> }

beforeEach(() => toast.error.mockClear())

describe("showErrorToast", () => {
  it("ข้อความเดิม ค้างจนกดปิด id คงที่ ปุ่มคัดลอกอยู่ในแถว description (ไม่ใช่ action)", () => {
    const action = { label: "ไปหน้าตรวจสุขภาพ", onClick: () => {} }
    const request = { code: "E_FFMPEG_MISSING", context: "enqueue" }
    expect(showErrorToast("ยังไม่มีโปรแกรมแปลงไฟล์", { request, id: "enqueue-error", action })).toBe("t1")
    const [message, options] = toast.error.mock.lastCall as unknown as [string, Options]
    expect(message).toBe("ยังไม่มีโปรแกรมแปลงไฟล์")
    expect(options.id).toBe("enqueue-error")
    expect(options.duration).toBe(Infinity)
    expect(options.action).toBe(action)
    expect(options.cancel).toBeUndefined()
    const [extra, button] = options.description.props.children as [ReactNode, ReactElement<{ request: unknown }>]
    expect(extra).toBeUndefined()
    expect(button.type).toBe(CopyReportButton)
    expect(button.props.request).toBe(request)
  })

  it("description เดิม (ข้อความ error ของงาน) อยู่ก่อนปุ่ม", () => {
    showErrorToast("โหลดไม่สำเร็จ · คลิป", { request: { jobId: "j1" }, id: "job-j1", description: "เน็ตหลุด ลองใหม่อีกครั้ง" })
    const [, options] = toast.error.mock.lastCall as unknown as [string, Options]
    expect(options.description.props.children[0]).toBe("เน็ตหลุด ลองใหม่อีกครั้ง")
  })
})
```

- [ ] **Step 2: Run them, expect FAIL**

Run: `cd "$WORKTREE/web" && npx vitest run src/lib/report.test.ts src/components/error-report`
Expected: `Failed to resolve import "./report"` / `"./model"` / `"./error-toast"` for the three files.

- [ ] **Step 3: Strings (`web/src/i18n/th.ts`)**

Replace
```ts
    downloadFailed: "โหลดไฟล์ไม่สำเร็จ ลองอีกครั้ง",
    unknown: "มีบางอย่างผิดพลาด ถ่ายภาพหน้าจอนี้ส่งให้ผู้ดูแล",
    offline: "เชื่อมต่อโปรแกรมไม่ได้ ถ้าปิดโปรแกรมไปแล้ว เปิดใหม่ด้วย start.bat",
    pageTitle: "เปิดหน้านี้ไม่สำเร็จ",
    chunk: "โปรแกรมเพิ่งอัปเดต โหลดหน้านี้ใหม่อีกครั้ง",
    crash: "หน้านี้ทำงานผิดพลาด โหลดหน้าใหม่แล้วลองอีกครั้ง",
  },
```
with
```ts
    downloadFailed: "โหลดไฟล์ไม่สำเร็จ ลองอีกครั้ง",
    // M6 รอบ B (Pete Q3 = A): ทุก error มีปุ่ม "คัดลอกข้อมูลแจ้งปัญหา" แล้ว ไม่ต้องถ่ายภาพหน้าจอ
    unknown: 'มีบางอย่างผิดพลาด กด "คัดลอกข้อมูลแจ้งปัญหา" แล้วส่งให้ผู้ดูแล',
    offline: "เชื่อมต่อโปรแกรมไม่ได้ ถ้าปิดโปรแกรมไปแล้ว เปิดใหม่ด้วย start.bat",
    pageTitle: "เปิดหน้านี้ไม่สำเร็จ",
    chunk: "โปรแกรมเพิ่งอัปเดต โหลดหน้านี้ใหม่อีกครั้ง",
    crash: "หน้านี้ทำงานผิดพลาด โหลดหน้าใหม่แล้วลองอีกครั้ง",
    // M6 รอบ B: error สองชั้น (PRD 7.1) ทุกคำยกมาจาก PRD / ข้อความเดิมใน th.ts (spec 7) ไม่มีคำใหม่
    copyReport: "คัดลอกข้อมูลแจ้งปัญหา",
    details: "ดูรายละเอียด",
    code: "รหัส {code}",
    copied: "คัดลอกแล้ว",
    copyFailed: "คัดลอกไม่สำเร็จ ลองอีกครั้ง",
  },
```

`web/e2e/settings-general.spec.ts` — replace
```ts
        json: { error: { code: "E_UNKNOWN", message: "มีบางอย่างผิดพลาด ถ่ายภาพหน้าจอนี้ส่งให้ผู้ดูแล", detail: null } },
```
with
```ts
        json: { error: { code: "E_UNKNOWN", message: 'มีบางอย่างผิดพลาด กด "คัดลอกข้อมูลแจ้งปัญหา" แล้วส่งให้ผู้ดูแล', detail: null } },
```

- [ ] **Step 4: Create `web/src/lib/report.ts`**
```ts
import { th } from "@/i18n/th"

import { api, ApiError } from "./api"

/**
 * รายงานแจ้งปัญหา (M6 รอบ B · PRD 7.1): หน้าเว็บส่งแค่ข้อมูลของ error ไป POST /api/diagnostics
 * เซิร์ฟเวอร์สร้างรายงานทั้งหมดและซ่อนข้อมูลส่วนตัวที่จุดเดียว · โมดูลนี้ไม่มี React (เทสใน node ได้)
 */

/** ความยาวสูงสุดของ detail ที่ส่ง (เท่ากับ MAX_DETAIL ของ api/diagnostics.py): error จริงต้องไม่โดน 422 */
export const MAX_DETAIL = 4000
/** จำนวนบรรทัดของ stack ที่ใส่ต่อท้าย "<name>: <message>" ของ error ที่ไม่ใช่ ApiError */
export const STACK_LINES = 10

/** body ของ POST /api/diagnostics (ทุกช่องไม่บังคับ) */
export type ReportRequest = { jobId?: string; code?: string; detail?: string; context?: string; videoId?: string }

/** ที่ที่ error เกิด: context = แท็ก ASCII ของหน้าจอ (spec 1.3) เช่น "video-header" */
export type ReportWhere = { context: string; videoId?: string; jobId?: string }

export type CopyOutcome = { ok: true } | { ok: false; message: string }

// กฎเดียวกับ api/diagnostics.py PATTERNS: ค่าที่ไม่ผ่านกฎไม่ส่ง (ไม่ให้ปุ่มได้ 422 แทนรายงาน)
const PATTERNS = {
  jobId: /^[A-Za-z0-9_-]{1,64}$/,
  code: /^E_[A-Z0-9_]{1,40}$/,
  context: /^[a-z][a-z0-9-]{0,31}$/,
  videoId: /^[A-Za-z0-9_-]{11}$/,
} as const

/**
 * ทำ body ให้ผ่านกฎของเซิร์ฟเวอร์เสมอ: ช่องที่ผิดรูปถูกทิ้ง (code ที่ผิดรูปกลายเป็น E_UNKNOWN) · detail ตัดที่ MAX_DETAIL
 * เช่น /v/abc (videoId พิมพ์เองผิด) ยังได้รายงาน ไม่ใช่ 422
 */
export function cleanRequest(req: ReportRequest): ReportRequest {
  const out: ReportRequest = {}
  for (const key of ["jobId", "context", "videoId"] as const) {
    const value = req[key]
    if (value !== undefined && PATTERNS[key].test(value)) out[key] = value
  }
  if (req.code !== undefined) out.code = PATTERNS.code.test(req.code) ? req.code : "E_UNKNOWN"
  if (req.detail) out.detail = req.detail.slice(0, MAX_DETAIL)
  return out
}

/**
 * body ของรายงานจาก error ที่จับได้: ApiError = รหัสและ detail จากเซิร์ฟเวอร์ · Error อื่น = E_UNKNOWN + "<name>: <message>"
 * ตามด้วย stack ไม่เกิน 10 บรรทัด · ค่าอื่น = E_UNKNOWN ไม่มี detail
 */
export function reportRequest(error: unknown, where: ReportWhere): ReportRequest {
  const req: ReportRequest = { context: where.context, videoId: where.videoId, jobId: where.jobId }
  if (error instanceof ApiError) {
    req.code = error.code
    req.detail = error.detail ?? undefined
  } else if (error instanceof Error) {
    req.code = "E_UNKNOWN"
    const head = `${error.name}: ${error.message}`
    const stack = error.stack ? error.stack.split("\n").slice(0, STACK_LINES).join("\n") : ""
    req.detail = stack ? `${head}\n${stack}` : head
  } else {
    req.code = "E_UNKNOWN"
  }
  return cleanRequest(req)
}

/** ขอรายงาน (Markdown) จากเซิร์ฟเวอร์ · api() ใส่ token ให้เอง · ต่อไม่ได้ = ApiError E_OFFLINE */
export async function fetchReport(req: ReportRequest, deps?: Parameters<typeof api>[2]): Promise<string> {
  const { report } = await api<{ report: string }>(
    "/diagnostics",
    { method: "POST", body: JSON.stringify(cleanRequest(req)) },
    deps,
  )
  return report
}

type CopyDeps = {
  clipboard?: Partial<Pick<Clipboard, "write" | "writeText">>
  ClipboardItem?: typeof ClipboardItem
  fetchReport?: (req: ReportRequest) => Promise<string>
}

/**
 * ขอรายงานแล้วคัดลอกลงคลิปบอร์ด · ไม่โยน error เลย
 * เริ่มขอรายงานทันทีในจังหวะที่กด แล้วส่ง Promise<Blob> ให้ ClipboardItem (แบบเดียวกับ copyImage ใน clipboard.ts)
 * การเขียนจึงยังอยู่ในจังหวะที่ผู้ใช้กด แม้รายงานมาถึงทีหลัง · ไม่มี ClipboardItem = รอรายงานแล้ว writeText
 * พลาด: ขอรายงานไม่ได้ = ข้อความของเซิร์ฟเวอร์ (ปิดโปรแกรมไปแล้ว = th.errors.offline) · คลิปบอร์ดไม่ยอม = th.errors.copyFailed
 */
export async function copyReport(req: ReportRequest, deps: CopyDeps = {}): Promise<CopyOutcome> {
  const clipboard = "clipboard" in deps ? deps.clipboard : globalThis.navigator?.clipboard
  const Item = "ClipboardItem" in deps ? deps.ClipboardItem : globalThis.ClipboardItem
  const text = (deps.fetchReport ?? fetchReport)(req)
  // ถ้าขอรายงานไม่สำเร็จ write จะล้มเองอยู่แล้ว: กันไม่ให้ Promise ตัวนี้กลายเป็น unhandled rejection อีกทาง
  text.catch(() => {})
  try {
    if (clipboard?.write && Item) {
      await clipboard.write([new Item({ "text/plain": text.then((t) => new Blob([t], { type: "text/plain" })) })])
    } else if (clipboard?.writeText) {
      await clipboard.writeText(await text)
    } else {
      throw new Error("clipboard unsupported")
    }
    return { ok: true }
  } catch {
    const failed = await text.then(
      () => null,
      (error: unknown) => error ?? new Error("report failed"),
    )
    if (failed !== null) return { ok: false, message: failed instanceof ApiError ? failed.message : th.errors.unknown }
    return { ok: false, message: th.errors.copyFailed }
  }
}
```

- [ ] **Step 5: Create `web/src/components/error-report/model.ts`**
```ts
import type { ReactNode } from "react"

import { cleanRequest, reportRequest, type ReportRequest, type ReportWhere } from "@/lib/report"

/**
 * ตรรกะของส่วน "ดูรายละเอียด" และ toast ของ error (M6 รอบ B spec 1.1) แยกจาก JSX เพื่อเทสใน node ได้
 * (vitest ไม่มี DOM แบบเดียวกับ components/account/dialog-model.ts)
 */

/** id ของ toast "คัดลอกแล้ว" / คัดลอกไม่สำเร็จ: กดซ้ำหลายครั้งได้ toast เดียว */
export const REPORT_TOAST_ID = "report-copy"

export type ToastButton = { label: string; onClick: () => void }

/** ตัวเลือกของ showErrorToast: request = body ของรายงาน · id คงที่ต่อแหล่ง error (error ครั้งใหม่แทนที่ toast เดิม) */
export type ErrorToastOptions = {
  request: ReportRequest
  id?: string | number
  description?: ReactNode
  action?: ToastButton
  cancel?: ToastButton
}

/** ที่มาของส่วนพับ: error ที่จับได้ + ที่ที่เกิด หรือ body ที่ประกอบไว้แล้ว (แถวงานที่พลาดในคิว) */
export type DetailsSource = ({ error: unknown } & ReportWhere) | { request: ReportRequest }

/** body ของรายงานของส่วนพับ · รหัสและ detail ที่แสดงมาจาก body นี้ จึงตรงกับที่ส่งไปเสมอ */
export function detailsRequest(source: DetailsSource): ReportRequest {
  if ("request" in source) return cleanRequest(source.request)
  return reportRequest(source.error, { context: source.context, videoId: source.videoId, jobId: source.jobId })
}

/**
 * กางไว้ตั้งแต่แรกเมื่อรหัสเป็น E_UNKNOWN (planner ruling R1): ข้อความของรหัสนี้บอกให้กดปุ่ม
 * ปุ่มจึงต้องเห็นโดยไม่ต้องกดอะไรก่อน · ผู้เรียกกำหนดเองได้ด้วย defaultOpen
 */
export function detailsOpenByDefault(code: string | undefined, defaultOpen?: boolean): boolean {
  return defaultOpen ?? code === "E_UNKNOWN"
}

/** ตัวเลือก sonner ของ toast error (ยกเว้น description ที่ error-toast.tsx ใส่ปุ่มคัดลอก): ค้างจนกดปิด (D1) */
export function errorToastSettings(opts: Pick<ErrorToastOptions, "id" | "action" | "cancel">) {
  return { id: opts.id, duration: Infinity, action: opts.action, cancel: opts.cancel }
}

/**
 * กระจายใส่ toast ที่ใช้ id เดียวกับ toast error (เช่น "โหลดเสร็จแล้ว" ของงานที่เคยพลาด "บันทึกแล้ว" กำลังโหลด ffmpeg)
 * sonner รวมค่าใหม่ทับ toast เดิมที่มี id เดียวกัน ช่องที่ไม่ส่งจะค้างจาก toast error (ปุ่มคัดลอก + ไม่หายเอง)
 */
export const PLAIN_TOAST = { description: undefined, duration: undefined, action: undefined, cancel: undefined }
```

- [ ] **Step 6: Create `web/src/components/error-report/copy-report-button.tsx`**
```tsx
import { Copy } from "lucide-react"
import { useRef, useState } from "react"
import { toast } from "sonner"

import { Button } from "@/components/ui/button"
import { Spinner } from "@/components/ui/spinner"
import { th } from "@/i18n/th"
import { copyReport, type ReportRequest } from "@/lib/report"

import { REPORT_TOAST_ID } from "./model"

type Props = {
  request: ReportRequest
  variant?: "outline" | "default"
  size?: "sm" | "default"
  className?: string
}

/**
 * ปุ่ม "คัดลอกข้อมูลแจ้งปัญหา" (PRD 7.1): ขอรายงานจากเซิร์ฟเวอร์แล้วคัดลอก → toast "คัดลอกแล้ว"
 * ระหว่างรอ = ปิดปุ่ม + วงหมุน (กดสองครั้งส่งคำขอเดียว) · ใช้แค่ useState/useRef กับ api() ไม่มี React Query
 * ไม่มี store ไม่มี router จึงยังใช้ได้ใน ErrorPanel หลังหน้าพัง · ความล้มเหลวของปุ่มนี้ไม่มีปุ่มรายงานซ้อน
 */
export function CopyReportButton({ request, variant = "outline", size = "sm", className }: Props) {
  const [pending, setPending] = useState(false)
  const busy = useRef(false)

  function onClick() {
    if (busy.current) return
    busy.current = true
    setPending(true)
    // เรียกทันทีในจังหวะที่กด (ไม่มี await ก่อนหน้า): ClipboardItem ยังนับเป็นการกระทำของผู้ใช้
    void copyReport(request).then((outcome) => {
      busy.current = false
      setPending(false)
      if (outcome.ok) toast.success(th.errors.copied, { id: REPORT_TOAST_ID })
      else toast.error(outcome.message, { id: REPORT_TOAST_ID })
    })
  }

  return (
    <Button type="button" variant={variant} size={size} className={className} disabled={pending} onClick={onClick}>
      {pending ? <Spinner /> : <Copy aria-hidden />}
      {th.errors.copyReport}
    </Button>
  )
}
```

- [ ] **Step 7: Create `web/src/components/error-report/error-details.tsx`**
```tsx
import { ChevronDown } from "lucide-react"
import { useState } from "react"

import { Button } from "@/components/ui/button"
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible"
import { fill, th } from "@/i18n/th"
import { cn } from "cn"

import { CopyReportButton } from "./copy-report-button"
import { detailsOpenByDefault, detailsRequest, type DetailsSource } from "./model"

type Props = DetailsSource & {
  /** กางตั้งแต่แรกไหม (ไม่ส่ง = กางเมื่อรหัสเป็น E_UNKNOWN) */
  defaultOpen?: boolean
  /** คุมจากข้างนอก (แถวงานในคิว: ปุ่ม "ดูรายละเอียด" ใน toast สั่งกาง) */
  open?: boolean
  onOpenChange?: (open: boolean) => void
  /** ใน Alert ที่มีไอคอน ส่ง "col-start-2" ให้ตรงกับข้อความ */
  className?: string
}

/**
 * ส่วนพับ "ดูรายละเอียด" ของ error ทุกจุด (PRD 7.1 ชั้นหน้าเว็บ · spec 1.1): รหัส · ข้อความเทคนิคดิบ · "คัดลอกข้อมูลแจ้งปัญหา"
 * หน้าตาเดียวกับแถวงานที่พลาดในคิวเดิม · <pre> ตัดคำได้ทุกตัว หน้าต่าง 640 px ไม่เลื่อนซ้ายขวา
 */
export function ErrorDetails(props: Props) {
  const { defaultOpen, open, onOpenChange, className } = props
  const request = detailsRequest(props)
  const code = request.code ?? "E_UNKNOWN"
  const [ownOpen, setOwnOpen] = useState(() => detailsOpenByDefault(code, defaultOpen))
  return (
    <Collapsible
      data-testid="error-details"
      className={cn("min-w-0", className)}
      open={open ?? ownOpen}
      onOpenChange={(next) => {
        setOwnOpen(next)
        onOpenChange?.(next)
      }}
    >
      <CollapsibleTrigger
        data-details-trigger=""
        render={<Button variant="link" size="sm" className="group/details h-7 px-0 text-muted-foreground" />}
      >
        {th.errors.details}
        <ChevronDown aria-hidden className="transition-transform group-data-[panel-open]/details:rotate-180" />
      </CollapsibleTrigger>
      <CollapsibleContent className="flex flex-col items-start gap-2 pt-1 text-foreground">
        <p className="font-mono text-xs">{fill(th.errors.code, { code })}</p>
        {request.detail && (
          <pre className="max-h-40 w-full overflow-auto rounded-md bg-muted p-2 font-mono text-xs break-all whitespace-pre-wrap">
            {request.detail}
          </pre>
        )}
        <CopyReportButton request={request} />
      </CollapsibleContent>
    </Collapsible>
  )
}
```

- [ ] **Step 8: Create `web/src/components/error-report/error-toast.tsx`**
```tsx
import { toast } from "sonner"

import { CopyReportButton } from "./copy-report-button"
import { errorToastSettings, type ErrorToastOptions } from "./model"

/**
 * toast ของ error ทุกตัว (D1): ค้างจนกดปิด · ปุ่ม "คัดลอกข้อมูลแจ้งปัญหา" อยู่ในแถว description ไม่ใช่ช่อง action ของ sonner
 * (sonner ปิด toast เมื่อกด action แต่ toast ต้องอยู่ต่อให้กด "ดูรายละเอียด" / ปุ่มบัญชีได้ และ action/cancel มีเจ้าของแล้ว)
 * ส่ง id คงที่ของแหล่ง error เสมอ: error ครั้งใหม่จากที่เดิมแทนที่ toast เดิม ไม่ซ้อนเป็นกอง
 */
export function showErrorToast(message: string, opts: ErrorToastOptions): string | number {
  return toast.error(message, {
    ...errorToastSettings(opts),
    description: (
      <div className="mt-1 flex flex-col items-start gap-2">
        {opts.description}
        <CopyReportButton request={opts.request} />
      </div>
    ),
  })
}
```

- [ ] **Step 9: Run, expect PASS**

Run: `cd "$WORKTREE/web" && npx vitest run src/lib/report.test.ts src/components/error-report` (23 passed), then `npm run typecheck && npm run lint && npm test` (prototype: 63 files / 1,032 tests passed, ESLint clean — `error-toast.tsx` exports only a function, which `react-refresh/only-export-components` accepts).

- [ ] **Step 10: Commit**
```bash
cd "$WORKTREE" && git add web/src/i18n/th.ts web/src/lib/report.ts web/src/lib/report.test.ts web/src/components/error-report web/e2e/settings-general.spec.ts && git commit -F- <<'EOF'
feat(web): problem-report request, copy button, details section and error toast

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
EOF
```


### Task 5: Docs — PRD §6.2 / §11, acceptance rows AC-SET-03..06, follow-up files

**Files:**
- Modify: `PRD.md` (the §6.2 `/diagnostics` row and the §11 FR-SET-5 row only; §7 / §7.1 were already updated in the spec commit)
- Modify: `docs/acceptance.md` (new "M6 รอบ B" section at the end)
- Modify: `docs/m1-followups.md` (`:58`), `docs/m4-followups.md` (`:40`)

**Interfaces:**
- Consumes: the final names of K5 (endpoint, body rules) and the Thai strings of spec §7 (quoted, never new).
- Produces: docs matching the code. `tests/integration/test_account_privacy.py`'s docstring is T11's (it owns that file).

Every `old` text occurs exactly once in its file (use the Edit tool, LF kept). Docs are Pete-style Thai prose; quoted UI strings are the spec §7 strings.

- [ ] **Step 1: PRD.md §6.2 — replace the stale GET row (planner ruling P2)**

Replace
```markdown
| GET | `/diagnostics` | `?jobId=` (ไม่บังคับ) | `{text}` รายงานแจ้งปัญหาแบบ Markdown ตามข้อ 7.1 |
```
with
```markdown
| POST | `/diagnostics` | `{jobId?, code?, detail?, context?, videoId?}` (detail ≤ 4,000) | `{report}` Markdown ตามแม่แบบใน §7.1 · token เหมือนคำขออื่นที่ไม่ใช่ GET · ช่องผิดรูป = 422 `E_BAD_REQUEST` |
```

- [ ] **Step 2: PRD.md §11 — FR-SET-5 traceability**

Replace
```markdown
| FR-SET-5 | W6, W7 | `/diagnostics` | AC-SET-03..06 |
```
with
```markdown
| FR-SET-5 | W2, W3, W4, W5, W6, W7 (ส่วน "ดูรายละเอียด" และปุ่ม "คัดลอกข้อมูลแจ้งปัญหา" ทุกจุดที่มี error) | `POST /diagnostics` · `run/logs/app.log` (บรรทัด `job_failed` และ `api_error`) | AC-SET-03..06 |
```

- [ ] **Step 3: docs/acceptance.md — manual Windows checks**

Append at the end of the file (after the `M5C-NARROW` row):
```markdown

## M6 รอบ B (ทำบน Windows 10/11 · error สองชั้น รายงานแจ้งปัญหา และ log)
| AC | ขั้นตอน | ผ่าน |
|---|---|---|
| AC-SET-03 | ส่งงานโหลดคลิปที่ยูทูปไม่ส่งไฟล์ หรือถอดสายเน็ตระหว่างโหลดจนงานพลาด แล้วเปิด `run\logs\app.log` ด้วย Notepad: มีบรรทัด `job_failed id=<รหัสงาน> kind=video code=<รหัส error> detail=...` พร้อมเวลาข้างหน้า ตามด้วย traceback · ไม่มีชื่อผู้ใช้ Windows ไม่มีชื่อคลิป (เห็น `<title>` แทน) และ path นอกโฟลเดอร์ผู้ใช้เป็น `<path>` | ☐ |
| AC-SET-04 | กดปุ่ม "คัดลอกข้อมูลแจ้งปัญหา" ที่แถวงานที่พลาดในคิว แล้ววางใน Notepad: มีครบทุกหัวข้อตามตัวอย่างใน PRD ข้อ 7.1 (เวลา แอพ ระบบ yt-dlp ffmpeg JS runtime บัญชียูทูป error log ล่าสุด) · บรรทัดรหัสเป็น `- รหัส: <รหัส> · งาน: video (videoId <id>)` · ค้นชื่อผู้ใช้ Windows ของเครื่อง (`Ctrl+F`) ไม่เจอ path ในโฟลเดอร์ผู้ใช้ขึ้นต้นด้วย `~\` · ไม่มีชื่อคลิป | ☐ |
| AC-SET-05 | หน้าคลิป (W2) ที่เปิดไม่ได้ (เช่นคลิปส่วนตัว): กด "ดูรายละเอียด" เห็น "รหัส …" ข้อความเทคนิค และปุ่ม "คัดลอกข้อมูลแจ้งปัญหา" · กดแล้วมี toast "คัดลอกแล้ว" · วางใน LINE (หรือ Teams) และ Notepad: ข้อความครบ อ่านเป็นรายการได้ บล็อก log ไม่ขาดกลาง · บรรทัดรหัสเป็น `- รหัส: <รหัส> · หน้าจอ: video-header (videoId <id>)` · toast ของ error (เช่นงานที่พลาด) มีปุ่มนี้ในตัว และค้างจนกดปิด | ☐ |
| AC-SET-05b | ตั้งค่า > ตรวจสุขภาพระบบ: ปุ่ม "คัดลอกข้อมูลแจ้งปัญหา" อยู่ถัดจาก "ตรวจอีกครั้ง" · วางแล้วไม่มีหัวข้อ `### error` · ไม่มีตัวช่วยของ yt-dlp: แถวนั้นขึ้น "บางคุณภาพอาจไม่แสดง เพราะเครื่องยังไม่มีตัวช่วยที่ yt-dlp ต้องใช้" | ☐ |
| AC-SET-05c | error ที่รหัสเป็น `E_UNKNOWN`: ข้อความ "มีบางอย่างผิดพลาด กด "คัดลอกข้อมูลแจ้งปัญหา" แล้วส่งให้ผู้ดูแล" และส่วน "ดูรายละเอียด" กางไว้แล้ว เห็นปุ่มทันที · ปิดโปรแกรมด้วย stop.bat แล้วกดปุ่มในแท็บที่ค้างอยู่: toast "เชื่อมต่อโปรแกรมไม่ได้ ถ้าปิดโปรแกรมไปแล้ว เปิดใหม่ด้วย start.bat" ไม่มีอะไรถูกคัดลอก | ☐ |
| AC-SET-06 | (M6) ทำตาม M5C-IMPORT ให้ถือบัญชีชั่วคราวอยู่ แล้วกด "คัดลอกข้อมูลแจ้งปัญหา" ทั้งที่แถวงานที่พลาดและที่หน้าตรวจสุขภาพ: บรรทัดบัญชีเป็น "บัญชียูทูป: ใช้บัญชีชั่วคราวอยู่" เท่านั้น · ค้น `SAPISID`, `LOGIN_INFO` และค่าคุกกี้สักตัวจากไฟล์ในข้อความที่วาง: ไม่เจอ (ชื่อคุกกี้เป็น `<hidden>`) · ไม่มี token ของแอพ (ค่าใน `<meta name="yt-token">` ของหน้าเว็บ) | ☐ |
| M6B-ROTATE | ดูโฟลเดอร์ `run\logs\` หลังใช้งานนาน: มีไม่เกิน 3 ไฟล์ (`app.log`, `app.log.1`, `app.log.2`) ไฟล์ละไม่เกินราว 5 MB · ใน `app.log` ไม่มีบรรทัด `HTTP Request:` ของ httpx | ☐ |
| M6B-NARROW | หน้าต่างกว้าง 640 px (หรือซูม 200%): กล่อง error ที่กาง "ดูรายละเอียด" แล้ว (ข้อความเทคนิคยาว) toast ที่มีปุ่มคัดลอก และหน้าตรวจสุขภาพ ไม่มีแถบเลื่อนแนวนอน · toast ที่ค้างหลายอันไม่บังแถบคิว | ☐ |
```

- [ ] **Step 4: docs/m1-followups.md — close the M6 diagnostics item**

Replace
```markdown
- **FR-SET-5 และ AC-SET-03 ถึง AC-SET-05 (รายงานวินิจฉัย และปุ่ม "คัดลอกข้อมูลแจ้งปัญหา"):** ตามแผนอยู่ใน M6 ครับ
```
with
```markdown
- **FR-SET-5 และ AC-SET-03 ถึง AC-SET-05 (รายงานวินิจฉัย และปุ่ม "คัดลอกข้อมูลแจ้งปัญหา"):** ทำแล้วใน M6 รอบ B ครับ (`POST /api/diagnostics`, บรรทัด `job_failed` / `api_error` ใน `app.log` ตรวจมือตาม `docs/acceptance.md` ส่วน "M6 รอบ B")
```

- [ ] **Step 5: docs/m4-followups.md — the canary now covers the report**

Replace
```markdown
- **รายงานแจ้งปัญหา (`/api/diagnostics`) ยังไม่มีในแอพ:** เทส canary ของ M5 รอบ C (`tests/integration/test_account_privacy.py`) ตรวจ log, `app.log`, ข่าว SSE, คำตอบของ API, `/health`, `GET /cookies` และไฟล์บนดิสก์ · ตอนทำรายงานใน M6 ต้องเพิ่มรายงานเข้าเทสเดียวกัน (AC-SET-06)
```
with
```markdown
- **รายงานแจ้งปัญหา (`/api/diagnostics`) (ปิดแล้วใน M6 รอบ B):** เทส canary `tests/integration/test_account_privacy.py` เรียก `POST /api/diagnostics` ทั้งสามแบบ (งานที่พลาด error จากหน้าเว็บ หน้าตรวจสุขภาพ) ตอนถือบัญชีอยู่ แล้วตรวจว่าไม่มีค่า canary ไม่มีชื่อคุกกี้ และส่วนหัวพูดถึงบัญชีแค่บรรทัดสถานะ (AC-SET-06)
```

- [ ] **Step 6: Verify**

Run: `cd "$WORKTREE" && git grep -n "GET | \`/diagnostics\`\|ถ่ายภาพหน้าจอนี้ส่งให้ผู้ดูแล" -- PRD.md docs/acceptance.md` — prints only the PRD §7 `E_UNKNOWN` note ("ข้อความเดิม …ถ่ายภาพหน้าจอนี้ส่งให้ผู้ดูแล") and nothing for the old GET row. Then `cd "$WORKTREE" && uv run pytest tests/unit/test_yterrors.py -q -W error -p no:cacheprovider` (PRD §7 rows untouched; the one pre-existing failure P10 is expected until T3 merges).

- [ ] **Step 7: Commit**
```bash
cd "$WORKTREE" && git add PRD.md docs/acceptance.md docs/m1-followups.md docs/m4-followups.md && git commit -F- <<'EOF'
docs: M6 round B API row, FR-SET-5 traceability, acceptance checks AC-SET-03..06

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
EOF
```


---

## Wave 2

### Task 6: Report builder (`core/diagnostics.py`)

**Files:**
- Create: `src/yttoolkit/core/diagnostics.py`
- Create: `tests/unit/test_diagnostics.py`

**Interfaces:**
- Consumes: `redact.redact_report(text, *, token, titles)` (T1); `core.tools.ToolStatus`; the `app.log` handler that `probe.setup_file_log` installs (`RotatingFileHandler` with `baseFilename == os.path.abspath(log_dir / "app.log")`).
- Produces: K3 — `ErrorSection`, `ReportInputs`, `build_report`, constants `NONE`, `LOG_FILES`, `TAIL_LINES`, `TAIL_BYTES`, `DETAIL_MAX`, `LOG_LINE_MAX`, `REPORT_MAX`; private `_tail_lines(log_dir, want=50, *, read=_read_tail)` and `_read_tail(path)` (tests inject `read`).

The builder is pure apart from reading the log files: no FastAPI, no `yt_dlp`, no `extractor`, no network, no `collect_health` (C3; the last test pins it).

- [ ] **Step 1: Write the failing tests** — create `tests/unit/test_diagnostics.py`:
```python
"""รายงานแจ้งปัญหา (M6 รอบ B · core/diagnostics.py · PRD ข้อ 7.1): แม่แบบ ค่าที่ไม่มี log ล่าสุด และเพดานความยาว"""

from __future__ import annotations

import logging
import logging.handlers
from dataclasses import replace
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path, PureWindowsPath

import pytest

from yttoolkit import redact
from yttoolkit.core import diagnostics
from yttoolkit.core.diagnostics import (
    DETAIL_MAX,
    LOG_LINE_MAX,
    REPORT_MAX,
    ErrorSection,
    ReportInputs,
    build_report,
)
from yttoolkit.core.tools import ToolStatus

BANGKOK = timezone(timedelta(hours=7))
NOW = datetime(2026, 10, 5, 14, 32, 9, tzinfo=BANGKOK)
TOKEN = "tok-5d4c3b2a1f0e"


def inputs(log_dir: Path, **over) -> ReportInputs:
    base = ReportInputs(
        now=NOW,
        version="0.1.0",
        commit="abc1234",
        os_version="Windows 11 (10.0.26200)",
        ytdlp=ToolStatus("ok", name="yt-dlp", version="2026.09.20"),
        ffmpeg=ToolStatus("ok", name="ffmpeg", version="8.1", path="C:/tools/ffmpeg.exe"),
        js_runtime=ToolStatus("ok", name="deno", version="2.9.7", path="C:/tools/deno.exe"),
        account_active=False,
        error=ErrorSection(code="E_BOT_CHECK", detail="ERROR: [youtube] dQw4w9WgXcQ: Sign in to confirm", kind="video",
                           video_id="dQw4w9WgXcQ"),  # fmt: skip
        log_dir=log_dir,
        token=TOKEN,
        titles=(),
    )
    return replace(base, **over)


def write_log(log_dir: Path, name: str, lines: list[str]) -> None:
    log_dir.mkdir(parents=True, exist_ok=True)
    (log_dir / name).write_text("".join(f"{line}\n" for line in lines), encoding="utf-8", newline="\n")


def log_block(report: str) -> list[str]:
    body = report.split("### log ล่าสุด (50 บรรทัด)\n", 1)[1]
    lines = body.rstrip("\n").split("\n")
    return lines[1:-1]  # ไม่เอาบรรทัดเปิดและปิดรั้ว


# ---------- แม่แบบ ----------


def test_job_report_matches_the_prd_template_exactly(tmp_path: Path) -> None:
    write_log(tmp_path, "app.log", ["2026-10-05 14:31:58,120 INFO yttoolkit: งาน j1 (video) จบด้วย E_BOT_CHECK"])
    assert build_report(inputs(tmp_path)) == (
        "## รายงานปัญหา YT Toolkit\n"
        "- เวลา: 2026-10-05 14:32 (+07:00)\n"
        "- แอพ: 0.1.0 (commit abc1234) · ระบบ: Windows 11 (10.0.26200)\n"
        "- yt-dlp: 2026.09.20 · ffmpeg: 8.1 · JS runtime: deno 2.9.7\n"
        "- บัญชียูทูป: ไม่ได้ใช้บัญชี\n"
        "### error\n"
        "- รหัส: E_BOT_CHECK · งาน: video (videoId dQw4w9WgXcQ)\n"
        "- รายละเอียด: ERROR: [youtube] dQw4w9WgXcQ: Sign in to confirm\n"
        "### log ล่าสุด (50 บรรทัด)\n"
        "```text\n"
        "2026-10-05 14:31:58,120 INFO yttoolkit: งาน j1 (video) จบด้วย E_BOT_CHECK\n"
        "```\n"
    )


def test_time_uses_the_local_offset_with_a_colon(tmp_path: Path) -> None:
    utc = build_report(inputs(tmp_path, now=datetime(2026, 1, 2, 3, 4, tzinfo=UTC)))
    assert "- เวลา: 2026-01-02 03:04 (+00:00)\n" in utc
    minus = build_report(inputs(tmp_path, now=datetime(2026, 1, 2, 3, 4, tzinfo=timezone(timedelta(hours=-3, minutes=-30)))))
    assert "(-03:30)" in minus


def test_a_naive_time_is_a_programming_error(tmp_path: Path) -> None:
    with pytest.raises(AssertionError):
        build_report(inputs(tmp_path, now=datetime(2026, 10, 5, 14, 32)))


def test_missing_values_say_none(tmp_path: Path) -> None:
    report = build_report(inputs(
        tmp_path,
        commit=None,
        ytdlp=ToolStatus("ok", name="yt-dlp", version=None),
        ffmpeg=ToolStatus("error", name="ffmpeg", message="ยังไม่มีโปรแกรมแปลงไฟล์ (ffmpeg)"),
        js_runtime=ToolStatus("warn", name=None, message="x"),
    ))  # fmt: skip
    assert "- แอพ: 0.1.0 (commit ไม่มี) · ระบบ: Windows 11 (10.0.26200)\n" in report
    assert "- yt-dlp: ไม่มี · ffmpeg: ไม่มี · JS runtime: ไม่มี\n" in report


@pytest.mark.parametrize("status", ["warn", "error"])
def test_ffmpeg_version_only_when_ready(tmp_path: Path, status: str) -> None:
    report = build_report(inputs(tmp_path, ffmpeg=ToolStatus(status, name="ffmpeg", version="8.1")))
    assert "· ffmpeg: ไม่มี ·" in report


def test_node_fallback_shows_node_and_its_version(tmp_path: Path) -> None:
    report = build_report(inputs(tmp_path, js_runtime=ToolStatus("warn", name="node", version="22.11.0")))
    assert "JS runtime: node 22.11.0\n" in report


def test_tool_paths_never_appear(tmp_path: Path) -> None:
    report = build_report(inputs(tmp_path))
    assert "C:/tools" not in report and "ffmpeg.exe" not in report


@pytest.mark.parametrize(("active", "line"), [(False, "ไม่ได้ใช้บัญชี"), (True, "ใช้บัญชีชั่วคราวอยู่")])
def test_account_line_has_only_the_two_prd_phrases(tmp_path: Path, active: bool, line: str) -> None:
    report = build_report(inputs(tmp_path, account_active=active))
    assert f"- บัญชียูทูป: {line}\n" in report
    assert [x for x in report.splitlines() if "บัญชี" in x] == [f"- บัญชียูทูป: {line}"]  # ไม่มีเวลา ชื่อ หรือค่าคุกกี้


# ---------- หัวข้อ error ----------


def test_non_job_error_line_with_context_and_video_id(tmp_path: Path) -> None:
    error = ErrorSection(code="E_NETWORK", detail=None, context="video-header", video_id="dQw4w9WgXcQ")
    report = build_report(inputs(tmp_path, error=error))
    assert "- รหัส: E_NETWORK · หน้าจอ: video-header (videoId dQw4w9WgXcQ)\n- รายละเอียด: ไม่มี\n" in report


def test_non_job_error_line_without_context_or_video_id(tmp_path: Path) -> None:
    report = build_report(inputs(tmp_path, error=ErrorSection(code=None, detail="")))
    assert "### error\n- รหัส: ไม่มี\n- รายละเอียด: ไม่มี\n" in report


def test_non_job_error_with_context_only(tmp_path: Path) -> None:
    report = build_report(inputs(tmp_path, error=ErrorSection(code="E_UNKNOWN", detail="x", context="crash")))
    assert "- รหัส: E_UNKNOWN · หน้าจอ: crash\n" in report


def test_no_error_section_for_the_health_report(tmp_path: Path) -> None:
    report = build_report(inputs(tmp_path, error=None))
    assert "### error" not in report and "- รหัส:" not in report
    assert "- บัญชียูทูป: ไม่ได้ใช้บัญชี\n### log ล่าสุด (50 บรรทัด)\n" in report


def test_multi_line_detail_is_a_list_continuation_and_crlf_collapses(tmp_path: Path) -> None:
    error = ErrorSection(code="E_UNKNOWN", detail="TypeError: x\r\n    at a (app.js:1)\n    at b (app.js:2)", context="crash")
    report = build_report(inputs(tmp_path, error=error))
    assert "- รายละเอียด: TypeError: x\n      at a (app.js:1)\n      at b (app.js:2)\n### log" in report
    assert "\r" not in report


# ---------- log ล่าสุด ----------


def test_tail_spans_rotation_in_order(tmp_path: Path) -> None:
    write_log(tmp_path, "app.log.1", [f"old {i}" for i in range(40)])
    write_log(tmp_path, "app.log", [f"new {i}" for i in range(20)])
    lines = log_block(build_report(inputs(tmp_path)))
    assert lines == [f"old {i}" for i in range(10, 40)] + [f"new {i}" for i in range(20)]


def test_tail_reads_at_most_three_files_and_ignores_an_old_fourth(tmp_path: Path) -> None:
    write_log(tmp_path, "app.log.3", ["ancient"])
    write_log(tmp_path, "app.log.2", ["two"])
    write_log(tmp_path, "app.log.1", ["one"])
    write_log(tmp_path, "app.log", ["zero"])
    assert log_block(build_report(inputs(tmp_path))) == ["two", "one", "zero"]


def test_no_log_files_say_none_inside_the_fence(tmp_path: Path) -> None:
    report = build_report(inputs(tmp_path / "missing"))
    assert report.endswith("### log ล่าสุด (50 บรรทัด)\n```text\nไม่มี\n```\n")


def test_invalid_utf8_bytes_become_replacement_characters(tmp_path: Path) -> None:
    tmp_path.mkdir(exist_ok=True)
    (tmp_path / "app.log").write_bytes(b"ok \xff\xfe bytes\n")
    assert log_block(build_report(inputs(tmp_path))) == ["ok \ufffd\ufffd bytes"]


def test_a_big_app_log_drops_the_partial_first_line_and_never_pulls_from_older_files(tmp_path: Path) -> None:
    write_log(tmp_path, "app.log.1", ["older file"])
    filler = "x" * 2000
    write_log(tmp_path, "app.log", [f"{i:03d} {filler}" for i in range(40)] + [f"tail {i}" for i in range(3)])
    lines = log_block(build_report(inputs(tmp_path, error=None)))
    assert "older file" not in lines
    assert lines[-3:] == ["tail 0", "tail 1", "tail 2"]
    assert all(line.startswith(("tail", "0")) for line in lines)  # ไม่มีเศษบรรทัดที่ถูกตัดหัว


def test_a_small_app_log_with_few_lines_pulls_the_rest_from_older_files(tmp_path: Path) -> None:
    write_log(tmp_path, "app.log.1", [f"a {i}" for i in range(60)])
    write_log(tmp_path, "app.log", ["b 0"])
    lines = log_block(build_report(inputs(tmp_path, error=None)))
    assert len(lines) == 50 and lines[0] == "a 11" and lines[-1] == "b 0"


def test_an_unreadable_file_is_skipped(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    def read(path: Path):
        if path.name == "app.log":
            raise PermissionError("locked")
        return (["from one"], True) if path.name == "app.log.1" else None

    with caplog.at_level(logging.DEBUG, logger="yttoolkit"):
        assert diagnostics._tail_lines(tmp_path, read=read) == ["from one"]
    assert any("app.log" in r.getMessage() for r in caplog.records)


def test_backticks_in_a_log_line_get_a_longer_fence(tmp_path: Path) -> None:
    write_log(tmp_path, "app.log", ["a ``` b", "c ````` d"])
    report = build_report(inputs(tmp_path, error=None))
    assert "\n``````text\na ``` b\nc ````` d\n``````\n" in report


def test_tail_holds_the_app_log_handler_lock(tmp_path: Path) -> None:
    write_log(tmp_path, "app.log", ["x"])
    handler = logging.handlers.RotatingFileHandler(tmp_path / "app.log", encoding="utf-8")
    root = logging.getLogger()
    root.addHandler(handler)
    held: list[bool] = []

    def read(path: Path):
        held.append(handler.lock._is_owned())  # type: ignore[attr-defined]  # RLock ของ Handler.createLock
        return diagnostics._read_tail(path)

    try:
        assert diagnostics._tail_lines(tmp_path, read=read) == ["x"]
    finally:
        root.removeHandler(handler)
        handler.close()
    assert held and all(held)
    assert not handler.lock._is_owned()  # type: ignore[attr-defined]


# ---------- เพดานความยาว (หลังซ่อนข้อมูล) ----------


def test_a_long_log_line_is_cut_with_an_ellipsis(tmp_path: Path) -> None:
    write_log(tmp_path, "app.log", ["y" * 1000])
    (line,) = log_block(build_report(inputs(tmp_path, error=None)))
    assert len(line) == LOG_LINE_MAX and line.endswith("…")


def test_a_long_detail_is_cut_to_the_detail_cap(tmp_path: Path) -> None:
    error = ErrorSection(code="E_UNKNOWN", detail="d" * 5000, context="crash")
    report = build_report(inputs(tmp_path, error=error))
    detail = report.split("- รายละเอียด: ", 1)[1].split("\n", 1)[0]
    assert len(detail) == DETAIL_MAX and detail.endswith("…")


def test_report_stays_under_the_cap_by_dropping_the_oldest_log_lines(tmp_path: Path) -> None:
    write_log(tmp_path, "app.log", [f"{i:02d} " + "z" * 290 for i in range(50)])
    error = ErrorSection(code="E_UNKNOWN", detail="d" * 1990, context="crash")
    report = build_report(inputs(tmp_path, error=error))
    assert len(report) <= REPORT_MAX
    lines = log_block(report)
    assert 0 < len(lines) < 50
    assert lines[-1].startswith("49 ")  # บรรทัดใหม่สุดยังอยู่ ที่ทิ้งคือบรรทัดเก่า
    assert "### log ล่าสุด (50 บรรทัด)" in report


def test_caps_apply_after_redaction_so_a_cut_never_leaks_half_a_username(tmp_path: Path, monkeypatch) -> None:
    from yttoolkit.api import errors

    monkeypatch.setattr(errors.Path, "home", lambda: PureWindowsPath("C:/Users/somchaijaidee"))
    monkeypatch.setattr(redact, "_home_aliases", lambda home: ())
    # path ยาวคร่อมจุดตัด 300: ถ้าตัดก่อนซ่อน "somchai" จะหลุดครึ่งเดียวและไม่ถูกแทน
    write_log(tmp_path, "app.log", ["p" * 290 + " C:\\Users\\somchaijaidee\\Downloads\\a.mp4"])
    error = ErrorSection(code="E_UNKNOWN", detail="q" * 1995 + " C:\\Users\\somchaijaidee\\x", context="crash")
    report = build_report(inputs(tmp_path, error=error))
    assert "somchai" not in report
    assert " ~\\Downlo" in report and " ~\\x" in report  # ซ่อนก่อนแล้วค่อยตัด: รอยตัดอยู่หลัง ~


def test_token_titles_cookie_names_and_other_drives_are_hidden(tmp_path: Path) -> None:
    title = "สูตรขนมไทยโบราณ ตอนพิเศษ"
    write_log(tmp_path, "app.log", [f"token={TOKEN} SAPISID=abc {title} D:\\out\\a.mp4"])
    error = ErrorSection(code="E_DISK_FULL", detail=f"'D:\\\\out\\\\{title}.mp4'", kind="video", video_id="dQw4w9WgXcQ")
    report = build_report(inputs(tmp_path, error=error, titles=(title,)))
    for leaked in (TOKEN, "SAPISID", title, "D:\\out"):
        assert leaked not in report
    assert "videoId dQw4w9WgXcQ" in report and "E_DISK_FULL" in report


def test_the_builder_never_touches_the_network_or_yt_dlp() -> None:
    import ast

    source = Path(diagnostics.__file__).read_text(encoding="utf-8")
    imported = {
        alias.name for node in ast.walk(ast.parse(source)) if isinstance(node, ast.Import) for alias in node.names
    } | {node.module or "" for node in ast.walk(ast.parse(source)) if isinstance(node, ast.ImportFrom)}
    assert not {"yt_dlp", "extractor", "fastapi", "httpx"} & {name.split(".")[0] for name in imported}
    assert "collect_health" not in source
```

- [ ] **Step 2: Run them, expect FAIL**

Run: `cd "$WORKTREE" && uv run pytest tests/unit/test_diagnostics.py -q -W error -p no:cacheprovider`
Expected: collection error `ModuleNotFoundError: No module named 'yttoolkit.core.diagnostics'`.

- [ ] **Step 3: Implement** — create `src/yttoolkit/core/diagnostics.py`:
```python
"""รายงานแจ้งปัญหา (M6 รอบ B · PRD ข้อ 7.1 · FR-SET-5): ข้อความ Markdown ที่พนักงานคัดลอกไปส่งผู้ดูแล

เซิร์ฟเวอร์สร้างทั้งรายงานที่นี่ที่เดียว: สถานะเครื่อง + error + log ล่าสุด 50 บรรทัด
ทุกส่วนผ่าน redact.redact_report ที่จุดเดียว (build_report ขั้นที่ 2) แล้วค่อยตัดความยาว จึงไม่มีรอยตัดกลาง path
ไม่ต่อเน็ต ไม่ import FastAPI, yt_dlp หรือ extractor (ผู้เรียกส่งสถานะเครื่องมือเข้ามา) อ่านแค่ไฟล์ log
"""

from __future__ import annotations

import logging
import logging.handlers
import os
import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from ..redact import redact_report
from .tools import ToolStatus

log = logging.getLogger("yttoolkit")

NONE = "ไม่มี"
TITLE = "## รายงานปัญหา YT Toolkit"
LOG_HEADING = "### log ล่าสุด (50 บรรทัด)"  # หัวข้อคงที่ตามแม่แบบ แม้ log มีไม่ถึง 50 บรรทัด
ACCOUNT_OFF = "ไม่ได้ใช้บัญชี"
ACCOUNT_ON = "ใช้บัญชีชั่วคราวอยู่"
LOG_FILES = ("app.log", "app.log.1", "app.log.2")  # ใหม่ไปเก่า (หมุนไฟล์เก็บ 3 ไฟล์ probe.LOG_BACKUPS)
TAIL_LINES = 50
TAIL_BYTES = 64 * 1024  # อ่านท้ายไฟล์ละไม่เกินเท่านี้ ไฟล์ใหญ่ 5 MB ก็ไม่ต้องอ่านทั้งไฟล์
DETAIL_MAX = 2000
LOG_LINE_MAX = 300
REPORT_MAX = 8000  # พอดีกับช่องแชตทั่วไป (LINE / Teams / AI) ดู spec Review Focus 1
ELLIPSIS = "…"
_BACKTICKS = re.compile(r"`{3,}")


@dataclass(frozen=True)
class ErrorSection:
    code: str | None  # None = "ไม่มี"
    detail: str | None
    kind: str | None = None  # ชนิดงาน ("video", "audio", ...) มี = error ของงานในคิว
    video_id: str | None = None
    context: str | None = None  # หน้าจอที่เกิด error (error ที่ไม่ใช่งานในคิวเท่านั้น)


@dataclass(frozen=True)
class ReportInputs:
    now: datetime  # เวลาท้องถิ่นที่มี timezone (api ส่ง datetime.now().astimezone() เทสส่งเอง)
    version: str
    commit: str | None
    os_version: str
    ytdlp: ToolStatus
    ffmpeg: ToolStatus
    js_runtime: ToolStatus
    account_active: bool
    error: ErrorSection | None
    log_dir: Path
    token: str  # ใช้ซ่อนเท่านั้น ไม่มีวันอยู่ในรายงาน
    titles: tuple[str, ...]  # ชื่อคลิปที่ต้องปิด (ชื่องาน + ชื่อในตาราง videos)


def build_report(inputs: ReportInputs) -> str:
    """รายงานตามแม่แบบ PRD ข้อ 7.1 ทุกบรรทัดจบด้วย LF

    ลำดับที่อนุญาตลำดับเดียว: 1) รวบรวมส่วนดิบ 2) redact_report ทุกส่วน 3) ตัดความยาว 4) ต่อด้วย \\n
    """
    offset = inputs.now.utcoffset()
    assert offset is not None, "now ต้องมี timezone (datetime.now().astimezone())"
    # 1) ส่วนดิบ
    header = _header_lines(inputs)
    code_line = _code_line(inputs.error) if inputs.error is not None else None
    detail = (inputs.error.detail or "").replace("\r\n", "\n") if inputs.error is not None else ""
    logs = _tail_lines(inputs.log_dir)
    # 2) ซ่อนข้อมูลส่วนตัว (จุดเดียวของรายงาน · C5)

    def redact(text: str) -> str:
        return redact_report(text, token=inputs.token, titles=inputs.titles)

    header = [redact(line) for line in header]
    code_line = redact(code_line) if code_line is not None else None
    detail = redact(detail)
    logs = [redact(line) for line in logs]
    # 3) ตัดความยาว (หลังซ่อนแล้ว รอยตัดจึงไม่ทำให้ชื่อผู้ใช้หลุดครึ่งหนึ่ง)
    detail = _cut(detail, DETAIL_MAX)
    logs = [_cut(line, LOG_LINE_MAX) for line in logs]
    # 4) ต่อ แล้วทิ้ง log บรรทัดเก่าสุดทีละบรรทัดจนไม่เกิน REPORT_MAX
    text = _assemble(header, code_line, detail, logs)
    while len(text) > REPORT_MAX and logs:
        logs.pop(0)
        text = _assemble(header, code_line, detail, logs)
    if len(text) > REPORT_MAX and code_line is not None:
        detail = _cut(detail, max(1, len(detail) - (len(text) - REPORT_MAX)))
        text = _assemble(header, code_line, detail, logs)
    return text


def _header_lines(inputs: ReportInputs) -> list[str]:
    z = inputs.now.strftime("%z")  # +0700
    when = f"{inputs.now.strftime('%Y-%m-%d %H:%M')} ({z[:3]}:{z[3:5]})"
    ffmpeg = inputs.ffmpeg.version if inputs.ffmpeg.status == "ok" and inputs.ffmpeg.version else NONE
    runtime = inputs.js_runtime
    js = " ".join(part for part in (runtime.name, runtime.version) if part) if runtime.name else NONE
    return [
        TITLE,
        f"- เวลา: {when}",
        f"- แอพ: {inputs.version} (commit {inputs.commit or NONE}) · ระบบ: {inputs.os_version}",
        f"- yt-dlp: {inputs.ytdlp.version or NONE} · ffmpeg: {ffmpeg} · JS runtime: {js}",
        f"- บัญชียูทูป: {ACCOUNT_ON if inputs.account_active else ACCOUNT_OFF}",
    ]


def _code_line(error: ErrorSection) -> str:
    code = error.code or NONE
    if error.kind is not None:  # งานในคิว: บรรทัดตามแม่แบบตรงตัว
        return f"- รหัส: {code} · งาน: {error.kind} (videoId {error.video_id or NONE})"
    line = f"- รหัส: {code}"
    if error.context:
        line += f" · หน้าจอ: {error.context}"  # ป้ายไทยตาม Pete spec Q1 ตามด้วยแท็ก ASCII ของหน้าจอ
    if error.video_id:
        line += f" (videoId {error.video_id})"
    return line


def _detail_lines(detail: str) -> list[str]:
    if not detail.strip():
        return [f"- รายละเอียด: {NONE}"]
    first, *rest = detail.split("\n")
    return [f"- รายละเอียด: {first}", *(f"  {line}" for line in rest)]  # บรรทัดต่อของรายการ Markdown


def _fence(lines: list[str]) -> str:
    longest = max((len(run) for line in lines for run in _BACKTICKS.findall(line)), default=0)
    return "`" * max(3, longest + 1)


def _assemble(header: list[str], code_line: str | None, detail: str, logs: list[str]) -> str:
    out = list(header)
    if code_line is not None:
        out += ["### error", code_line, *_detail_lines(detail)]
    fence = _fence(logs)
    out += [LOG_HEADING, f"{fence}text", *(logs or [NONE]), fence]
    return "\n".join(out) + "\n"


def _cut(text: str, limit: int) -> str:
    return text if len(text) <= limit else text[: limit - 1] + ELLIPSIS


# ---------- log ล่าสุด ----------


def _file_handler(log_dir: Path) -> logging.Handler | None:
    """handler ของ app.log ตัวที่ probe.setup_file_log สร้าง (lock เดียวกับที่ emit → doRollover ใช้) ไม่มี = None"""
    target = os.path.abspath(log_dir / "app.log")
    for handler in logging.getLogger().handlers:
        if isinstance(handler, logging.handlers.RotatingFileHandler) and handler.baseFilename == target:
            return handler
    return None


def _read_tail(path: Path) -> tuple[list[str], bool] | None:
    """บรรทัดท้ายไฟล์ (ไม่เกิน TAIL_BYTES) และว่าได้อ่านทั้งไฟล์ไหม · ไม่มีไฟล์ = None · อ่านไม่ได้ = OSError"""
    try:
        f = open(path, "rb")  # noqa: SIM115 (ปิดใน finally ด้านล่าง)
    except FileNotFoundError:
        return None
    try:
        size = f.seek(0, os.SEEK_END)
        start = max(0, size - TAIL_BYTES)
        f.seek(start)
        data = f.read()
    finally:
        f.close()
    lines = data.decode("utf-8", errors="replace").splitlines()
    if start > 0 and lines:
        lines = lines[1:]  # บรรทัดแรกหลังจุดที่ seek ถูกตัดกลางบรรทัด
    return lines, start == 0


TailReader = Callable[[Path], "tuple[list[str], bool] | None"]


def _tail_lines(log_dir: Path, want: int = TAIL_LINES, *, read: TailReader = _read_tail) -> list[str]:
    """log ล่าสุดไม่เกิน want บรรทัด เก่าไปใหม่ · อ่านไฟล์เก่ากว่าต่อเมื่อไฟล์ใหม่กว่าอ่านได้ทั้งไฟล์แล้วยังไม่พอ (ไม่มีช่องโหว่)

    ถือ lock ของ handler ของ app.log ระหว่างอ่าน: บน Windows ถ้าหมุนไฟล์ตอนเรากำลังเปิดไฟล์อยู่ การเปลี่ยนชื่อจะล้มและ
    บรรทัดนั้นหาย · ไม่ log อะไรระหว่างถือ lock (บันทึกไฟล์ที่อ่านไม่ได้ไว้ log ทีหลัง)
    """
    handler = _file_handler(log_dir)
    unreadable: list[str] = []
    result: list[str] = []
    if handler is not None:
        handler.acquire()
    try:
        for name in LOG_FILES:
            try:
                got = read(log_dir / name)
            except OSError:
                unreadable.append(name)
                continue
            if got is None:
                continue
            lines, whole = got
            need = want - len(result)
            result = (lines[-need:] if need > 0 else []) + result
            if len(result) >= want or not whole:
                break
    finally:
        if handler is not None:
            handler.release()
    for name in unreadable:
        log.debug("อ่าน %s ไม่ได้ ข้ามไปในรายงานแจ้งปัญหา", name)
    return result
```

Design notes (spec §2.2):
- Assembly order is fixed: raw parts → `redact_report` on every part → caps → join. The caps run after redaction so a cut never splits a home path (Review Focus 4).
- The tail moves to an older file only when the newer one was read whole (≤ 64 KiB) and still gave fewer than 50 lines, so the tail never has a gap; `app.log.3` from older versions is ignored.
- The `app.log` handler lock (`handler.acquire()` / `release()`, the same RLock `emit` → `doRollover` takes) is held while reading: on Windows a rename while our handle is open would fail and lose that record. Nothing is logged while the lock is held (unreadable files are logged at DEBUG afterwards).
- A log line with a run of ≥ 3 backticks gets a fence one backtick longer than the longest run.

- [ ] **Step 4: Run, expect PASS**

Run the Step 2 command (30 passed), then the full suite.

- [ ] **Step 5: Commit**
```bash
cd "$WORKTREE" && git add src/yttoolkit/core/diagnostics.py tests/unit/test_diagnostics.py && git commit -F- <<'EOF'
feat(core): problem-report builder (PRD 7.1 template, log tail, one redaction point, caps)

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
EOF
```

### Task 7: One `job_failed` log line per failed job (`core/queue.py`, AC-SET-03)

**Files:**
- Modify: `src/yttoolkit/core/queue.py`
- Modify: `tests/unit/test_queue.py`

**Interfaces:**
- Consumes: `redact.redact_log_detail(text, titles)` (T1); `Job.id/kind/title`.
- Produces: K4 — `JOB_FAILED_DETAIL_MAX`, `job_failed_message(job, code, detail, exc)`, `log_job_failed(job, code, detail, exc)`, `QueueRunner._fail(..., exc=None)`. The old `log.exception` calls at `:316` (spawn) and `:375` (unexpected) are gone; the summary line `งาน … จบด้วย …` (`:351`) stays.

- [ ] **Step 1: Write the failing tests**

In `tests/unit/test_queue.py` replace
```python
import random
import threading
import time
from datetime import UTC, datetime, timedelta
```
with
```python
import logging
import random
import threading
import time
from datetime import UTC, datetime, timedelta
```
and append at the end of the file:
```python
# ---------- M6 รอบ B: บรรทัด job_failed ใน app.log (AC-SET-03 · spec 3.2) ----------


def failed_records(caplog) -> list[logging.LogRecord]:
    return [r for r in caplog.records if r.getMessage().startswith("job_failed ")]


def run_one_job(runner_factory, caplog, outcome, *, title: str = "", kind: str = "video"):
    r, spawn, h = runner_factory(concurrency=1, fail={"vid00000001": outcome})
    (job,) = r.enqueue([NewJob("vid00000001", kind, {}, title)])
    with caplog.at_level(logging.INFO, logger="yttoolkit"):
        r.tick()
        spawn.run_all()
    return r, job


def test_yt_error_failure_logs_one_detailed_warning_with_a_traceback(runner_factory, caplog):
    r, job = run_one_job(runner_factory, caplog, "E_YT_REFUSED")
    (record,) = failed_records(caplog)
    assert record.levelno == logging.WARNING
    first, trace = record.getMessage().split("\n", 1)
    assert first == f"job_failed id={job.id} kind=video code=E_YT_REFUSED detail=fake E_YT_REFUSED"
    assert trace.startswith("Traceback (most recent call last):") and "YtError" in trace
    assert record.exc_info is None  # traceback อยู่ในข้อความ จึงผ่านตัวปิดชื่อคลิปด้วย
    assert r.store.get(job.id).error_code == "E_YT_REFUSED"


def test_unexpected_exception_logs_once_at_error_with_e_unknown(runner_factory, caplog):
    run_one_job(runner_factory, caplog, RuntimeError("boom"))
    (record,) = failed_records(caplog)
    assert record.levelno == logging.ERROR
    assert "code=E_UNKNOWN detail=RuntimeError: boom" in record.getMessage()
    assert "RuntimeError: boom" in record.getMessage().split("\n", 1)[1]
    assert [r for r in caplog.records if r.exc_info] == []  # log.exception เดิมของงานที่พังถูกเอาออก (ไม่ซ้ำสองที่)


def test_cancelled_without_a_reason_logs_a_warning_without_traceback(runner_factory, caplog):
    run_one_job(runner_factory, caplog, JobCancelled())
    (record,) = failed_records(caplog)
    assert record.levelno == logging.WARNING
    assert "\n" not in record.getMessage()
    assert "code=E_UNKNOWN detail=JobCancelled" in record.getMessage()


def test_spawn_failure_logs_a_job_failed_line(runner_factory, caplog):
    def broken_spawn(fn):
        raise RuntimeError("can't start new thread")

    r, spawn, h = runner_factory(spawn=broken_spawn)
    (job,) = r.enqueue(jobs_of("frames_zip", 1))
    with caplog.at_level(logging.INFO, logger="yttoolkit"):
        assert r.tick() == []
    (record,) = failed_records(caplog)
    assert record.levelno == logging.ERROR
    assert record.getMessage().startswith(
        f"job_failed id={job.id} kind=frames_zip code=E_UNKNOWN detail=RuntimeError: can't start new thread\nTraceback"
    )
    assert [r for r in caplog.records if r.exc_info] == []


def test_second_bot_check_logs_a_job_failed_line_and_the_first_does_not(runner_factory, caplog):
    r, spawn, h = runner_factory(concurrency=1, fail={"vid00000001": ["E_BOT_CHECK", "E_BOT_CHECK"]})
    (job,) = r.enqueue(jobs_of("video", 1))
    with caplog.at_level(logging.INFO, logger="yttoolkit"):
        r.tick()
        spawn.run_all()
        assert failed_records(caplog) == []  # ครั้งแรกกลับหัวคิว ไม่ใช่ความล้มเหลว
        r.resume()
        r.clock.t += 10
        r.tick()
        spawn.run_all()
    (record,) = failed_records(caplog)
    assert record.levelno == logging.WARNING
    assert f"job_failed id={job.id} kind=video code=E_BOT_CHECK detail=fake E_BOT_CHECK\nTraceback" in record.getMessage()


def test_job_failed_hides_the_title_home_and_other_drive_paths(runner_factory, caplog, tmp_path):
    title = "สูตรลับขนมไทยของยาย ตอนที่ 3"
    detail = f"[Errno 13] Permission denied: '{tmp_path}\\out\\{title}.mp4' · copy to 'D:\\backup\\{title}.mp4'"
    run_one_job(runner_factory, caplog, YtError("E_OUTPUT_NOT_WRITABLE", detail), title=title)
    text = caplog.text
    assert title not in text and str(tmp_path) not in text and "D:\\backup" not in text
    assert "<title>" in text and "<path>" in text and "~" in text


def test_job_failed_detail_is_one_line_and_capped(runner_factory, caplog):
    run_one_job(runner_factory, caplog, YtError("E_YT_REFUSED", "line one\r\nline two\n" + "x" * 5000))
    first = failed_records(caplog)[0].getMessage().split("\n", 1)[0]
    detail = first.split(" detail=", 1)[1]
    assert detail.startswith("line one\\r\\nline two\\n")
    assert len(detail) <= queue_module.JOB_FAILED_DETAIL_MAX + 6  # \r \n ที่ escape แล้วยาวขึ้นตัวละ 1
    assert detail.endswith("…")


def test_job_failed_line_reaches_app_log(runner_factory, caplog, paths):
    from yttoolkit import probe

    root = logging.getLogger()
    before, level = list(root.handlers), root.level
    try:
        probe.setup_file_log(paths)
        r, job = run_one_job(runner_factory, caplog, "E_YT_REFUSED")
        for handler in root.handlers:
            handler.flush()
        text = (paths.logs / "app.log").read_text(encoding="utf-8")
    finally:
        for handler in list(root.handlers):
            if handler not in before:
                root.removeHandler(handler)
                handler.close()
        root.setLevel(level)
    assert f"WARNING yttoolkit: job_failed id={job.id} kind=video code=E_YT_REFUSED" in text
```

- [ ] **Step 2: Run them, expect FAIL**

Run: `cd "$WORKTREE" && uv run pytest tests/unit/test_queue.py -q -W error -p no:cacheprovider -k "job_failed or logs_"`
Expected: the new tests fail on `(record,) = failed_records(caplog)` (`ValueError: not enough values to unpack (expected 1, got 0)`) and `test_job_failed_detail_is_one_line_and_capped` with `IndexError`; `AttributeError: ... 'JOB_FAILED_DETAIL_MAX'`.

- [ ] **Step 3: Implement in `src/yttoolkit/core/queue.py`**

Replace (1) the imports and the logger line:
```python
import logging
import math
import random
import shutil
import threading
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Protocol

from .cancel import JobCancelled
from .download import YOUTUBE_KINDS
from .events import EventBus
from .jobs import Handler, InvalidTransition, Job, JobResult, JobStore, NewJob, is_stage
from .yterrors import MESSAGES, YtError

log = logging.getLogger("yttoolkit")
```
with:
```python
import logging
import math
import random
import shutil
import threading
import time
import traceback
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Protocol

from ..redact import redact_log_detail
from .cancel import JobCancelled
from .download import YOUTUBE_KINDS
from .events import EventBus
from .jobs import Handler, InvalidTransition, Job, JobResult, JobStore, NewJob, is_stage
from .yterrors import MESSAGES, YtError

log = logging.getLogger("yttoolkit")

# M6 รอบ B (spec 3.2): ความยาวสูงสุดของ detail ในบรรทัด job_failed (หลังซ่อนข้อมูลแล้ว)
JOB_FAILED_DETAIL_MAX = 2000


def job_failed_message(job: Job, code: str, detail: str | None, exc: BaseException | None) -> str:
    """บรรทัด job_failed ของ app.log: ฟิลด์ ASCII key=value (ไม่ต้องมีข้อความไทยใหม่) ตามด้วย traceback (ถ้ามี)

    detail และ traceback ผ่าน redact_log_detail ที่นี่ที่เดียว (C5) พร้อมชื่องาน: ข้อความของ OSError ที่มีชื่อไฟล์
    ของคลิปก็ถูกปิดด้วย · traceback อยู่ในข้อความเอง ไม่ใช้ exc_info จึงผ่านตัวปิดชื่อคลิปด้วย
    """
    titles = (job.title,)
    text = redact_log_detail(detail or "-", titles)
    if len(text) > JOB_FAILED_DETAIL_MAX:
        text = text[: JOB_FAILED_DETAIL_MAX - 1] + "…"
    text = text.replace("\r", "\\r").replace("\n", "\\n")
    line = f"job_failed id={job.id} kind={job.kind} code={code} detail={text}"
    if exc is None:
        return line
    trace = redact_log_detail("".join(traceback.format_exception(exc)), titles)
    return f"{line}\n{trace.rstrip()}"


def log_job_failed(job: Job, code: str, detail: str | None, exc: BaseException | None) -> None:
    """WARNING สำหรับ YtError หรือไม่มี exception · ERROR สำหรับ exception ที่ไม่ได้คาดไว้ (E_UNKNOWN)"""
    level = logging.WARNING if exc is None or isinstance(exc, YtError) else logging.ERROR
    log.log(level, "%s", job_failed_message(job, code, detail, exc))
```
(`core` may import `yttoolkit.redact`: it is neither `api` nor `platform`, and it is stdlib only; `test_core_does_not_import_api_or_platform_at_runtime` stays green.)

Replace (2) the spawn-failure block in `_start`:
```python
            # เปิดเธรดไม่ได้ (เช่นเครื่องทรัพยากรหมด): งานต้องไม่ค้าง running โดยไม่มีใครทำ
            log.exception("เริ่มงาน %s ไม่ได้", job.id)
            ctx.close()
            self._forget(job.id, ctx)
            shutil.rmtree(workdir, ignore_errors=True)
            ctx.done.set()
            try:
                failed = self.store.transition(job.id, "failed", error_code="E_UNKNOWN",
                                               error_message=MESSAGES["E_UNKNOWN"],
                                               error_detail=f"{type(exc).__name__}: {exc}")
```
with:
```python
            # เปิดเธรดไม่ได้ (เช่นเครื่องทรัพยากรหมด): งานต้องไม่ค้าง running โดยไม่มีใครทำ
            detail = f"{type(exc).__name__}: {exc}"
            log_job_failed(job, "E_UNKNOWN", detail, exc)
            ctx.close()
            self._forget(job.id, ctx)
            shutil.rmtree(workdir, ignore_errors=True)
            ctx.done.set()
            try:
                failed = self.store.transition(job.id, "failed", error_code="E_UNKNOWN",
                                               error_message=MESSAGES["E_UNKNOWN"], error_detail=detail)
```

Replace (3) in `_run_job`:
```python
            if exc.code == "E_QUEUE_PAUSED" and self.pause_state() is not None:
                return self._paused(job, ctx)
            return self._fail(job, ctx, exc.code, exc.message, exc.detail)
        except Exception as exc:
            if ctx.reason is not None:
                return self._stopped(job, ctx)
            log.exception("งาน %s (%s) พังแบบไม่คาดคิด", job.id, job.kind)
            return self._fail(job, ctx, "E_UNKNOWN", MESSAGES["E_UNKNOWN"], f"{type(exc).__name__}: {exc}")
```
with:
```python
            if exc.code == "E_QUEUE_PAUSED" and self.pause_state() is not None:
                return self._paused(job, ctx)
            return self._fail(job, ctx, exc.code, exc.message, exc.detail, exc)
        except Exception as exc:
            if ctx.reason is not None:
                return self._stopped(job, ctx)
            # พังแบบไม่คาดคิด: traceback ลง log ครั้งเดียวในบรรทัด job_failed พร้อมรหัส (M6 รอบ B)
            return self._fail(job, ctx, "E_UNKNOWN", MESSAGES["E_UNKNOWN"], f"{type(exc).__name__}: {exc}", exc)
```
(The `JobCancelled` without a reason at `:362` keeps calling `_fail` with no exception → WARNING without traceback.)

Replace (4) the `_fail` signature:
```python
    def _fail(self, job: Job, ctx: _JobContext, code: str, message: str, detail: str | None) -> str:
        self._clear_workdir(ctx)
```
with:
```python
    def _fail(
        self, job: Job, ctx: _JobContext, code: str, message: str, detail: str | None, exc: BaseException | None = None
    ) -> str:
        """ทุกความล้มเหลวของงานผ่านที่นี่ (ยกเว้นเปิดเธรดไม่ได้ใน _start): บรรทัด job_failed หนึ่งบรรทัดต่อครั้ง (AC-SET-03)"""
        log_job_failed(job, code, detail, exc)
        self._clear_workdir(ctx)
```

Replace (5) the end of `_bot_check`:
```python
        if ctx.reason is not None:
            return self._stopped(job, ctx)
        return self._fail(job, ctx, "E_BOT_CHECK", exc.message, exc.detail)
```
with:
```python
        if ctx.reason is not None:
            return self._stopped(job, ctx)
        return self._fail(job, ctx, "E_BOT_CHECK", exc.message, exc.detail, exc)
```

- [ ] **Step 4: Run, expect PASS**

Run: `cd "$WORKTREE" && uv run pytest tests/unit/test_queue.py -q -W error -p no:cacheprovider` (65 passed), then the full suite (the privacy tests `test_handlers.py::test_logs_have_no_absolute_paths` / `test_logs_have_no_clip_title` and `test_account_privacy.py` must stay green — C6).

- [ ] **Step 5: Commit**
```bash
cd "$WORKTREE" && git add src/yttoolkit/core/queue.py tests/unit/test_queue.py && git commit -F- <<'EOF'
feat(queue): one redacted job_failed line with code, detail and traceback per failure

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
EOF
```


### Task 8: Web — clip page (W2), history and batch: every `LoadError` and every W2 error toast

**Files:**
- Modify: `web/src/pages/video/load-error.tsx` (required `context`, optional `videoId`, renders `ErrorDetails`)
- Modify (all `LoadError` callers, spec §1.3 table): `web/src/pages/video/header.tsx`, `subtitle-gate.tsx`, `subs/preview.tsx` (+ `videoId` prop, P7), `subs-panel.tsx` (passes it), `transcript-panel.tsx`, `frames.tsx` (also the file-download toast), `clip-details.tsx`, `web/src/pages/history.tsx`, `web/src/pages/batch.tsx`
- Modify (W2 toasts): `web/src/pages/video.tsx` (background refresh), `web/src/pages/video/capture/use-capture.ts`, `web/src/pages/video/capture/capture-strip.tsx` (download / delete / reveal), `web/src/pages/video/advanced/use-advanced-choice.ts` (SponsorBlock default save, spec Q5)
- Modify: `web/src/pages/video/capture/capture-store.test.ts`

**Interfaces:**
- Consumes (T4): `ErrorDetails`, `showErrorToast`, `reportRequest`.
- Produces: `LoadError` props `context: string` (required) and `videoId?: string`; `SubsPreview` prop `videoId: string`. Contexts / ids from K7: `video-header`, `video-subtitles`, `video-subs-preview`, `video-transcript`, `video-frames`, `video-pinned`, `history`, `batch`; toasts `frames-download` (loading-toast id), `capture` → `capture-error`, `capture-download` (loading-toast id), `capture-delete`, `capture-reveal`, `video-refresh`, `advanced-save`.

Why these files are one lane: `context` becomes a required prop of `LoadError`, so every caller must change in the same commit (typecheck). The W2 toasts live in the same folder.

- [ ] **Step 1: Update the failing unit tests (capture toast)**

`web/src/pages/video/capture/capture-store.test.ts`:

Replace (1):
```ts
vi.mock("./capture-api", async (importOriginal) => ({ ...(await importOriginal<object>()), postCapture: api.postCapture }))

const BBB = "aqz-KE-bpKQ"
const item = (tMs: number): Capture => ({ id: `c_${tMs}`, tMs, width: 1920, height: 1080, url: `/api/cache/${BBB}/captures/c_${tMs}.jpg?v=1` })

beforeEach(() => {
```
with:
```ts
vi.mock("./capture-api", async (importOriginal) => ({ ...(await importOriginal<object>()), postCapture: api.postCapture }))

const BBB = "aqz-KE-bpKQ"
type ErrorOptions = { id?: string; duration?: number; action?: { label: string; onClick: () => void } }
/** ข้อความและตัวเลือกของ toast error ล่าสุด (M6 รอบ B: ทุกตัวผ่าน showErrorToast) */
const lastError = () => toast.error.mock.lastCall as unknown as [string, ErrorOptions]
const item = (tMs: number): Capture => ({ id: `c_${tMs}`, tMs, width: 1920, height: 1080, url: `/api/cache/${BBB}/captures/c_${tMs}.jpg?v=1` })

beforeEach(() => {
```

Replace (2):
```ts
    const invalidate = vi.spyOn(client, "invalidateQueries")
    api.postCapture.mockRejectedValueOnce(new ApiError(422, "E_CAPTURE_UNSUPPORTED", "ถ่ายไม่ได้", null, null))
    await runCapture(client, BBB, 0)
    expect(toast.error).toHaveBeenCalledWith("ถ่ายไม่ได้")
    expect(client.getQueryData(capturesKey(BBB))).toBeUndefined()
    expect(invalidate).not.toHaveBeenCalled()
    api.postCapture.mockRejectedValueOnce(new ApiError(429, "E_BOT_CHECK", "ยูทูปขอให้ยืนยัน", null, null))
```
with:
```ts
    const invalidate = vi.spyOn(client, "invalidateQueries")
    api.postCapture.mockRejectedValueOnce(new ApiError(422, "E_CAPTURE_UNSUPPORTED", "ถ่ายไม่ได้", null, null))
    await runCapture(client, BBB, 0)
    const [message, options] = lastError()
    expect(message).toBe("ถ่ายไม่ได้")
    expect(options.id).toBe("capture-error") // M6 รอบ B: id คงที่ ค้างจนกดปิด ไม่มีปุ่มบัญชี
    expect(options.duration).toBe(Infinity)
    expect(options.action).toBeUndefined()
    expect(client.getQueryData(capturesKey(BBB))).toBeUndefined()
    expect(invalidate).not.toHaveBeenCalled()
    api.postCapture.mockRejectedValueOnce(new ApiError(429, "E_BOT_CHECK", "ยูทูปขอให้ยืนยัน", null, null))
```

Replace (3):
```ts
    accountDialog.close()
  })

  it("M5 รอบ C: ยูทูปขอตรวจสอบ (E_BOT_CHECK) = ไม่มีปุ่มบัญชี ข้อความเดิม ไม่ค้างถาวร", async () => {
    const client = new QueryClient()
    api.postCapture.mockRejectedValueOnce(new ApiError(429, "E_BOT_CHECK", "ยูทูปขอให้ยืนยัน", null, null))
    await runCapture(client, BBB, 0)
    expect(toast.error).toHaveBeenLastCalledWith("ยูทูปขอให้ยืนยัน")
  })

  it("M5 รอบ C: ถือบัญชีอยู่แล้ว = ไม่มีปุ่ม (ข้อความ ลองด้วยบัญชีแล้ว… มาจาก backend)", async () => {
```
with:
```ts
    accountDialog.close()
  })

  it("M5 รอบ C: ยูทูปขอตรวจสอบ (E_BOT_CHECK) = ไม่มีปุ่มบัญชี ข้อความเดิม (M6 รอบ B: ค้างจนกดปิดเหมือน error อื่น)", async () => {
    const client = new QueryClient()
    api.postCapture.mockRejectedValueOnce(new ApiError(429, "E_BOT_CHECK", "ยูทูปขอให้ยืนยัน", null, null))
    await runCapture(client, BBB, 0)
    const [message, options] = lastError()
    expect(message).toBe("ยูทูปขอให้ยืนยัน")
    expect(options.action).toBeUndefined()
    expect(options.duration).toBe(Infinity)
  })

  it("M5 รอบ C: ถือบัญชีอยู่แล้ว = ไม่มีปุ่ม (ข้อความ ลองด้วยบัญชีแล้ว… มาจาก backend)", async () => {
```

Replace (4):
```ts
    client.setQueryData(ACCOUNT_KEY, { active: true, used: true })
    api.postCapture.mockRejectedValueOnce(new ApiError(404, "E_VIDEO_PRIVATE", "ลองด้วยบัญชีแล้วยังเปิดไม่ได้", null, null))
    await runCapture(client, BBB, 0)
    expect(toast.error).toHaveBeenLastCalledWith("ลองด้วยบัญชีแล้วยังเปิดไม่ได้")
  })
})
```
with:
```ts
    client.setQueryData(ACCOUNT_KEY, { active: true, used: true })
    api.postCapture.mockRejectedValueOnce(new ApiError(404, "E_VIDEO_PRIVATE", "ลองด้วยบัญชีแล้วยังเปิดไม่ได้", null, null))
    await runCapture(client, BBB, 0)
    const [message, options] = lastError()
    expect(message).toBe("ลองด้วยบัญชีแล้วยังเปิดไม่ได้")
    expect(options.action).toBeUndefined()
  })
})
```

(The old test name said "ไม่ค้างถาวร": D1 makes every error toast stay until dismissed — a deliberate change, spec §1.3.)

- [ ] **Step 2: Run, expect FAIL**

Run: `cd "$WORKTREE/web" && npx vitest run src/pages/video/capture/capture-store.test.ts`
Expected: 3 failures (`options.id` is `undefined`, `duration` is `undefined`).

- [ ] **Step 3: `LoadError` gets the details section** — `web/src/pages/video/load-error.tsx`:

Replace (1):
```tsx

import { UseAccountButton } from "@/components/account/account-button"
import { useAccountStatus } from "@/components/account/use-account"
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
import { Button, buttonVariants } from "@/components/ui/button"
import { th } from "@/i18n/th"
```
with:
```tsx

import { UseAccountButton } from "@/components/account/account-button"
import { useAccountStatus } from "@/components/account/use-account"
import { ErrorDetails } from "@/components/error-report/error-details"
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
import { Button, buttonVariants } from "@/components/ui/button"
import { th } from "@/i18n/th"
```

Replace (2):
```tsx
  ref?: Ref<HTMLDivElement>
  /** M5 รอบ C: error จำกัดอายุ/ส่วนตัว + ยังไม่ได้ใช้บัญชี = ปุ่มหลัก "ใช้บัญชียูทูปชั่วคราว" แล้วทำ onImported หลังนำเข้า */
  account?: { onImported: () => void }
}

/** กล่อง error ของหน้า W2: ข้อความไทยจาก envelope + ปุ่มลองใหม่ (ซ่อนเมื่อลองใหม่ไม่ช่วย) */
export function LoadError({ title, error, onRetry, showHome = false, ref, account }: Props) {
  const { active } = useAccountStatus()
  const retry = showRetry(error, account !== undefined, active)
  const offerAccount = account !== undefined && showAccountButton(error instanceof ApiError ? error.code : null, active)
```
with:
```tsx
  ref?: Ref<HTMLDivElement>
  /** M5 รอบ C: error จำกัดอายุ/ส่วนตัว + ยังไม่ได้ใช้บัญชี = ปุ่มหลัก "ใช้บัญชียูทูปชั่วคราว" แล้วทำ onImported หลังนำเข้า */
  account?: { onImported: () => void }
  /** M6 รอบ B: แท็กหน้าจอของรายงานแจ้งปัญหา (spec 1.3 เช่น "video-header") */
  context: string
  /** คลิปที่ error นี้เป็นของ (ไม่มี = หน้าที่ไม่ใช่ของคลิปเดียว เช่นประวัติ) */
  videoId?: string
}

/**
 * กล่อง error ของหน้า W2 / ประวัติ / หลายคลิป: ข้อความไทยจาก envelope + ปุ่มลองใหม่ (ซ่อนเมื่อลองใหม่ไม่ช่วย)
 * M6 รอบ B: ใต้แถวปุ่มมีส่วนพับ "ดูรายละเอียด" (รหัส + ข้อความเทคนิค + "คัดลอกข้อมูลแจ้งปัญหา")
 */
export function LoadError({ title, error, onRetry, showHome = false, ref, account, context, videoId }: Props) {
  const { active } = useAccountStatus()
  const retry = showRetry(error, account !== undefined, active)
  const offerAccount = account !== undefined && showAccountButton(error instanceof ApiError ? error.code : null, active)
```

Replace (3):
```tsx
          )}
        </div>
      )}
    </Alert>
  )
}
```
with:
```tsx
          )}
        </div>
      )}
      <ErrorDetails error={error} context={context} videoId={videoId} className="col-start-2" />
    </Alert>
  )
}
```

- [ ] **Step 4: Every `LoadError` caller passes its context**

`web/src/pages/video/header.tsx` (the clip info failed, so `data` is empty: the report's `videoId` comes from the route):

Replace (1):
```tsx
import { ExternalLink, ImageIcon, NotebookPen } from "lucide-react"
import { useCallback, useEffect, useRef, useState, type ReactNode } from "react"
import { createPortal } from "react-dom"

import { Badge } from "@/components/ui/badge"
import { Button, buttonVariants } from "@/components/ui/button"
```
with:
```tsx
import { ExternalLink, ImageIcon, NotebookPen } from "lucide-react"
import { useCallback, useEffect, useRef, useState, type ReactNode } from "react"
import { createPortal } from "react-dom"
import { useParams } from "react-router"

import { Badge } from "@/components/ui/badge"
import { Button, buttonVariants } from "@/components/ui/button"
```

Replace (2):
```tsx
  }, [videoId])
  // เปิดคลิปที่เปิดไม่ได้ (เช่นกด "ถัดไป" แล้วคลิปนั้นถูกลบ) ไม่มีชื่อคลิป: โฟกัสกล่อง error แทน ไม่ปล่อยไว้ที่ body
  const errorRef = useRef<HTMLDivElement>(null)
  const failed = !data && video.isError
  useEffect(() => {
    if (failed && focusLost()) errorRef.current?.focus({ preventScroll: true })
```
with:
```tsx
  }, [videoId])
  // เปิดคลิปที่เปิดไม่ได้ (เช่นกด "ถัดไป" แล้วคลิปนั้นถูกลบ) ไม่มีชื่อคลิป: โฟกัสกล่อง error แทน ไม่ปล่อยไว้ที่ body
  const errorRef = useRef<HTMLDivElement>(null)
  // เปิดคลิปไม่ได้ = ยังไม่มีข้อมูลคลิป: videoId ของรายงานมาจาก URL (/v/:videoId)
  const { videoId: pageId } = useParams()
  const failed = !data && video.isError
  useEffect(() => {
    if (failed && focusLost()) errorRef.current?.focus({ preventScroll: true })
```

Replace (3):
```tsx
          error={video.error}
          onRetry={() => void video.refetch()}
          account={{ onImported: () => void video.refetch() }}
        />
      )
    }
```
with:
```tsx
          error={video.error}
          onRetry={() => void video.refetch()}
          account={{ onImported: () => void video.refetch() }}
          context="video-header"
          videoId={pageId}
        />
      )
    }
```

`web/src/pages/video/subtitle-gate.tsx`:

Replace (1):
```tsx
export function SubtitleGate({ videoId, enabled, children }: Props) {
  const subtitles = useQuery(subtitlesQuery(videoId, enabled))
  if (subtitles.isError) {
    return <LoadError title={t.loadError} error={subtitles.error} onRetry={() => void subtitles.refetch()} />
  }
  if (!subtitles.isSuccess) return <SubsSkeleton />
  if (subtitles.data.tracks.length === 0) return <NoSubtitles />
```
with:
```tsx
export function SubtitleGate({ videoId, enabled, children }: Props) {
  const subtitles = useQuery(subtitlesQuery(videoId, enabled))
  if (subtitles.isError) {
    return (
      <LoadError
        title={t.loadError}
        error={subtitles.error}
        onRetry={() => void subtitles.refetch()}
        context="video-subtitles"
        videoId={videoId}
      />
    )
  }
  if (!subtitles.isSuccess) return <SubsSkeleton />
  if (subtitles.data.tracks.length === 0) return <NoSubtitles />
```

`web/src/pages/video/subs/preview.tsx`:

Replace (1):
```tsx
}

type Props = {
  /** ผลของ tokensQuery สำหรับแทร็กที่ใช้อยู่ */
  query: UseQueryResult<SubTokens>
  options: SubOptions
```
with:
```tsx
}

type Props = {
  /** คลิปของซับนี้ (M6 รอบ B: videoId ของรายงานแจ้งปัญหา) */
  videoId: string
  /** ผลของ tokensQuery สำหรับแทร็กที่ใช้อยู่ */
  query: UseQueryResult<SubTokens>
  options: SubOptions
```

Replace (2):
```tsx
 * ยูทูปไม่ให้โหลดซับแปล = คำแนะนำ + ปุ่มใช้ซับภาษาต้นฉบับ · ซับแปลรอเซสชัน = กล่องนับถอยหลัง (โหลดให้เองเมื่อครบ)
 * ผิดพลาดอื่น = Alert + ลองใหม่ (ถ้าลองแล้วช่วย)
 */
export function SubsPreview({ query, options, onUseOriginal, range }: Props) {
  if (query.isError) {
    if (hasCode(query.error, "E_NO_SUBTITLES")) return <NoTokens />
    if (hasCode(query.error, "E_TRANSLATION_BLOCKED")) return <TranslationBlocked onUseOriginal={onUseOriginal} />
    if (isWarming(query.error)) return <SessionWarming key={query.errorUpdatedAt} query={query} onUseOriginal={onUseOriginal} />
    return <LoadError title={t.loadError} error={query.error} onRetry={() => void query.refetch()} />
  }
  if (!query.isSuccess) return <PreviewSkeleton />
  return <PreviewBody data={query.data} options={options} range={range} />
```
with:
```tsx
 * ยูทูปไม่ให้โหลดซับแปล = คำแนะนำ + ปุ่มใช้ซับภาษาต้นฉบับ · ซับแปลรอเซสชัน = กล่องนับถอยหลัง (โหลดให้เองเมื่อครบ)
 * ผิดพลาดอื่น = Alert + ลองใหม่ (ถ้าลองแล้วช่วย)
 */
export function SubsPreview({ videoId, query, options, onUseOriginal, range }: Props) {
  if (query.isError) {
    if (hasCode(query.error, "E_NO_SUBTITLES")) return <NoTokens />
    if (hasCode(query.error, "E_TRANSLATION_BLOCKED")) return <TranslationBlocked onUseOriginal={onUseOriginal} />
    if (isWarming(query.error)) return <SessionWarming key={query.errorUpdatedAt} query={query} onUseOriginal={onUseOriginal} />
    return (
      <LoadError
        title={t.loadError}
        error={query.error}
        onRetry={() => void query.refetch()}
        context="video-subs-preview"
        videoId={videoId}
      />
    )
  }
  if (!query.isSuccess) return <PreviewSkeleton />
  return <PreviewBody data={query.data} options={options} range={range} />
```

`web/src/pages/video/subs-panel.tsx`:

Replace (1):
```tsx
          {track && (
            <>
              <Separator />
              <SubsPreview query={tokens} options={settings.options} onUseOriginal={backToOriginal} range={range} />
            </>
          )}
          {advanced.values.sponsorblock && !advanced.split && (
```
with:
```tsx
          {track && (
            <>
              <Separator />
              <SubsPreview
                videoId={videoId}
                query={tokens}
                options={settings.options}
                onUseOriginal={backToOriginal}
                range={range}
              />
            </>
          )}
          {advanced.values.sponsorblock && !advanced.split && (
```

`web/src/pages/video/transcript-panel.tsx`:

Replace (1):
```tsx
  else if (hasCode(tokens.error, "E_TRANSLATION_BLOCKED")) body = <TranslationBlocked onUseOriginal={onUseOriginal} />
  else if (isWarming(tokens.error)) body = <SessionWarming key={tokens.errorUpdatedAt} query={tokens} onUseOriginal={onUseOriginal} />
  else if (tokens.isError) {
    body = <LoadError title={th.subs.loadError} error={tokens.error} onRetry={() => void tokens.refetch()} />
  } else if (!tokens.isSuccess) body = <LinesSkeleton />
  else if (cues.length === 0) body = <NoLines />
  else body = <TranscriptLines cues={cues} at={at} segments={segments} onPick={onPick} />
```
with:
```tsx
  else if (hasCode(tokens.error, "E_TRANSLATION_BLOCKED")) body = <TranslationBlocked onUseOriginal={onUseOriginal} />
  else if (isWarming(tokens.error)) body = <SessionWarming key={tokens.errorUpdatedAt} query={tokens} onUseOriginal={onUseOriginal} />
  else if (tokens.isError) {
    body = (
      <LoadError
        title={th.subs.loadError}
        error={tokens.error}
        onRetry={() => void tokens.refetch()}
        context="video-transcript"
        videoId={videoId}
      />
    )
  } else if (!tokens.isSuccess) body = <LinesSkeleton />
  else if (cues.length === 0) body = <NoLines />
  else body = <TranscriptLines cues={cues} at={at} segments={segments} onPick={onPick} />
```

`web/src/pages/video/clip-details.tsx`:

Replace (1):
```tsx

  let body: ReactNode
  if (pinned.isError) {
    body = <LoadError title={t.pinned.loadError} error={pinned.error} onRetry={() => void pinned.refetch()} />
  } else if (!pinned.isSuccess) body = <PinnedSkeleton />
  else if (comment) body = <PinnedText comment={comment} />
  else body = <p className="text-sm text-muted-foreground">{t.pinned.none}</p>
```
with:
```tsx

  let body: ReactNode
  if (pinned.isError) {
    body = (
      <LoadError
        title={t.pinned.loadError}
        error={pinned.error}
        onRetry={() => void pinned.refetch()}
        context="video-pinned"
        videoId={videoId}
      />
    )
  } else if (!pinned.isSuccess) body = <PinnedSkeleton />
  else if (comment) body = <PinnedText comment={comment} />
  else body = <p className="text-sm text-muted-foreground">{t.pinned.none}</p>
```

`web/src/pages/history.tsx` (both boxes):

Replace (1):
```tsx
      {history.isPending ? (
        <HistoryTableSkeleton />
      ) : history.isError && !history.data ? (
        <LoadError title={th.history.loadError} error={history.error} onRetry={() => void history.refetch()} />
      ) : items.length === 0 ? (
        urlQ ? (
          <p role="status" className="py-8 text-center text-muted-foreground [overflow-wrap:anywhere]">
```
with:
```tsx
      {history.isPending ? (
        <HistoryTableSkeleton />
      ) : history.isError && !history.data ? (
        <LoadError
          title={th.history.loadError}
          error={history.error}
          onRetry={() => void history.refetch()}
          context="history"
        />
      ) : items.length === 0 ? (
        urlQ ? (
          <p role="status" className="py-8 text-center text-muted-foreground [overflow-wrap:anywhere]">
```

Replace (2):
```tsx
              title={th.history.loadError}
              error={history.error}
              onRetry={() => void (history.isFetchNextPageError ? history.fetchNextPage() : history.refetch())}
            />
          )}
          <div className="flex flex-col items-center gap-3 pt-2">
```
with:
```tsx
              title={th.history.loadError}
              error={history.error}
              onRetry={() => void (history.isFetchNextPageError ? history.fetchNextPage() : history.refetch())}
              context="history"
            />
          )}
          <div className="flex flex-col items-center gap-3 pt-2">
```

`web/src/pages/batch.tsx`:

Replace (1):
```tsx
          title={failure === settings ? th.general.loadError : t.loadError}
          error={failure.error}
          onRetry={() => void failure.refetch()}
        />
      ) : loadingPlaylist ? (
        <div aria-busy="true">
```
with:
```tsx
          title={failure === settings ? th.general.loadError : t.loadError}
          error={failure.error}
          onRetry={() => void failure.refetch()}
          context="batch"
        />
      ) : loadingPlaylist ? (
        <div aria-busy="true">
```

- [ ] **Step 5: W2 toasts become `showErrorToast`**

`web/src/pages/video/frames.tsx` (the storyboard `LoadError` and the file-download toast, which keeps the loading toast's id so the error replaces it):

Replace (1):
```tsx
import { useCallback, useEffect, useMemo, useRef, useState, type KeyboardEvent, type ReactNode, type RefObject } from "react"
import { toast } from "sonner"

import { AspectRatio } from "@/components/ui/aspect-ratio"
import { Button } from "@/components/ui/button"
import { ButtonGroup } from "@/components/ui/button-group"
```
with:
```tsx
import { useCallback, useEffect, useMemo, useRef, useState, type KeyboardEvent, type ReactNode, type RefObject } from "react"
import { toast } from "sonner"

import { showErrorToast } from "@/components/error-report/error-toast"
import { AspectRatio } from "@/components/ui/aspect-ratio"
import { Button } from "@/components/ui/button"
import { ButtonGroup } from "@/components/ui/button-group"
```

Replace (2):
```tsx
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip"
import { fill, th } from "@/i18n/th"
import { ApiError } from "@/lib/api"
import { copyImage } from "@/lib/clipboard"
import { downloadFile } from "@/lib/download"
import { formatTimecode, youtubeLinkAt, youtubeWatchUrl } from "@/lib/format"
```
with:
```tsx
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip"
import { fill, th } from "@/i18n/th"
import { ApiError } from "@/lib/api"
import { reportRequest } from "@/lib/report"
import { copyImage } from "@/lib/clipboard"
import { downloadFile } from "@/lib/download"
import { formatTimecode, youtubeLinkAt, youtubeWatchUrl } from "@/lib/format"
```

Replace (3):
```tsx
    await downloadFile(url, fallbackName)
    toast.dismiss(id)
  } catch (error) {
    toast.error(errorMessage(error, th.errors.downloadFailed), { id })
  }
}
```
with:
```tsx
    await downloadFile(url, fallbackName)
    toast.dismiss(id)
  } catch (error) {
    // M6 รอบ B: id เดิมของ toast "กำลังเตรียม" = แทนที่ toast นั้นด้วย error ที่มีปุ่มคัดลอก
    showErrorToast(errorMessage(error, th.errors.downloadFailed), {
      id,
      request: reportRequest(error, { context: "frames-download" }),
    })
  }
}
```

Replace (4):
```tsx
    )
  }
  else if (storyboard.isError) {
    body = <LoadError title={t.loadError} error={storyboard.error} onRetry={() => void storyboard.refetch()} />
  } else body = <FrameSkeleton />

  return (
```
with:
```tsx
    )
  }
  else if (storyboard.isError) {
    body = (
      <LoadError
        title={t.loadError}
        error={storyboard.error}
        onRetry={() => void storyboard.refetch()}
        context="video-frames"
        videoId={videoId}
      />
    )
  } else body = <FrameSkeleton />

  return (
```

`web/src/pages/video.tsx` (background refresh; `toast` is no longer used in this file):

Replace (1):
```tsx
import { useQuery } from "@tanstack/react-query"
import { useEffect } from "react"
import { useLocation, useParams } from "react-router"
import { toast } from "sonner"

import { fill, th } from "@/i18n/th"

import { homeStore, useHomeState } from "./home/state"
import { readFromList, useAnalyze, useGlobalPaste } from "./home/use-analyze"
```
with:
```tsx
import { useQuery } from "@tanstack/react-query"
import { useEffect } from "react"
import { useLocation, useParams } from "react-router"
import { showErrorToast } from "@/components/error-report/error-toast"
import { fill, th } from "@/i18n/th"
import { reportRequest } from "@/lib/report"

import { homeStore, useHomeState } from "./home/state"
import { readFromList, useAnalyze, useGlobalPaste } from "./home/use-analyze"
```

Replace (2):
```tsx

  // รีเฟรชเบื้องหลังล้มเหลวทั้งที่มีข้อมูลเดิมอยู่: ไม่ล้มทั้งหน้า แจ้งด้วย toast
  useEffect(() => {
    if (video.isError && hasData) toast.error(errorMessage(video.error, th.errors.unknown))
  }, [video.isError, video.error, hasData])

  return (
    <div className="flex flex-col gap-6 pt-2">
```
with:
```tsx

  // รีเฟรชเบื้องหลังล้มเหลวทั้งที่มีข้อมูลเดิมอยู่: ไม่ล้มทั้งหน้า แจ้งด้วย toast
  useEffect(() => {
    if (!video.isError || !hasData) return
    showErrorToast(errorMessage(video.error, th.errors.unknown), {
      id: "video-refresh",
      request: reportRequest(video.error, { context: "video-refresh", videoId }),
    })
  }, [video.isError, video.error, hasData, videoId])

  return (
    <div className="flex flex-col gap-6 pt-2">
```

`web/src/pages/video/capture/use-capture.ts` (one stable id; the account action is kept, D1 makes it persistent in every branch):

Replace (1):
```ts
import { toast } from "sonner"

import { openAccountDialog } from "@/components/account/account-store"
import { fill, th } from "@/i18n/th"
import { ACCOUNT_KEY, showAccountButton } from "@/lib/account"
import { ApiError } from "@/lib/api"
import { QUEUE_KEY, queueQuery } from "@/lib/jobs"
import type { AccountStatus, Capture, VideoInfo } from "@/lib/types"

import { errorMessage, hasCode } from "../errors"
```
with:
```ts
import { toast } from "sonner"

import { openAccountDialog } from "@/components/account/account-store"
import { showErrorToast } from "@/components/error-report/error-toast"
import { fill, th } from "@/i18n/th"
import { ACCOUNT_KEY, showAccountButton } from "@/lib/account"
import { ApiError } from "@/lib/api"
import { QUEUE_KEY, queueQuery } from "@/lib/jobs"
import { reportRequest } from "@/lib/report"
import type { AccountStatus, Capture, VideoInfo } from "@/lib/types"

import { errorMessage, hasCode } from "../errors"
```

Replace (2):
```ts
    const active = client.getQueryData<AccountStatus>(ACCOUNT_KEY)?.active === true
    const account = showAccountButton(error instanceof ApiError ? error.code : null, active)
    const message = errorMessage(error, th.errors.unknown)
    if (account) {
      const retry = () => void runCapture(client, videoId, ms)
      toast.error(message, {
        duration: Infinity, // มีปุ่มให้กด: ไม่หายเองก่อนผู้ใช้เห็น (เหมือน toast งานที่พลาด)
        action: { label: th.account.use, onClick: () => openAccountDialog({ origin: "error", onImported: retry }) },
      })
    } else {
      toast.error(message)
    }
    if (hasCode(error, "E_BOT_CHECK") || hasCode(error, "E_QUEUE_PAUSED")) {
      void client.invalidateQueries({ queryKey: QUEUE_KEY })
    }
```
with:
```ts
    const active = client.getQueryData<AccountStatus>(ACCOUNT_KEY)?.active === true
    const account = showAccountButton(error instanceof ApiError ? error.code : null, active)
    const message = errorMessage(error, th.errors.unknown)
    const retry = () => void runCapture(client, videoId, ms)
    // M6 รอบ B: toast เดียว (id คงที่) ค้างจนกดปิด มีปุ่มคัดลอก · มีปุ่มบัญชีเมื่อจำกัดอายุ/ส่วนตัวและยังไม่ได้ใช้บัญชี
    showErrorToast(message, {
      id: "capture-error",
      request: reportRequest(error, { context: "capture", videoId }),
      action: account
        ? { label: th.account.use, onClick: () => openAccountDialog({ origin: "error", onImported: retry }) }
        : undefined,
    })
    if (hasCode(error, "E_BOT_CHECK") || hasCode(error, "E_QUEUE_PAUSED")) {
      void client.invalidateQueries({ queryKey: QUEUE_KEY })
    }
```

`web/src/pages/video/capture/capture-strip.tsx` (download keeps the loading-toast id; delete and reveal get their own ids):

Replace (1):
```tsx
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
```
with:
```tsx
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog"
import { showErrorToast } from "@/components/error-report/error-toast"
import { AspectRatio } from "@/components/ui/aspect-ratio"
import { Button } from "@/components/ui/button"
import { fill, th } from "@/i18n/th"
import { copyImage } from "@/lib/clipboard"
import { downloadFile } from "@/lib/download"
import { youtubeWatchUrl } from "@/lib/format"
import { reportRequest } from "@/lib/report"
import type { Capture } from "@/lib/types"
import { cn } from "cn"
```

Replace (2):
```tsx
    await downloadFile(captureDownloadUrl(capture.url), captureFileName(capture.tMs))
    toast.dismiss(id)
  } catch (error) {
    toast.error(errorMessage(error, th.errors.downloadFailed), { id })
  }
}
```
with:
```tsx
    await downloadFile(captureDownloadUrl(capture.url), captureFileName(capture.tMs))
    toast.dismiss(id)
  } catch (error) {
    showErrorToast(errorMessage(error, th.errors.downloadFailed), {
      id,
      request: reportRequest(error, { context: "capture-download" }),
    })
  }
}
```

Replace (3):
```tsx
      } catch (error) {
        // ภาพหายไปแล้ว (ถูกลบจากที่อื่น) = ถือว่าลบสำเร็จ · พลาดแบบอื่น = แจ้งแล้วโหลดรายการใหม่ให้ตรงกับของจริง
        if (!hasCode(error, "E_NOT_FOUND")) {
          toast.error(errorMessage(error, th.errors.unknown))
          void client.invalidateQueries({ queryKey: capturesKey(videoId) })
          return
        }
```
with:
```tsx
      } catch (error) {
        // ภาพหายไปแล้ว (ถูกลบจากที่อื่น) = ถือว่าลบสำเร็จ · พลาดแบบอื่น = แจ้งแล้วโหลดรายการใหม่ให้ตรงกับของจริง
        if (!hasCode(error, "E_NOT_FOUND")) {
          showErrorToast(errorMessage(error, th.errors.unknown), {
            id: "capture-delete",
            request: reportRequest(error, { context: "capture-delete", videoId }),
          })
          void client.invalidateQueries({ queryKey: capturesKey(videoId) })
          return
        }
```

Replace (4):
```tsx
    try {
      await revealCaptures(videoId)
    } catch (error) {
      toast.error(errorMessage(error, th.errors.unknown))
    }
  }
```
with:
```tsx
    try {
      await revealCaptures(videoId)
    } catch (error) {
      showErrorToast(errorMessage(error, th.errors.unknown), {
        id: "capture-reveal",
        request: reportRequest(error, { context: "capture-reveal", videoId }),
      })
    }
  }
```

`web/src/pages/video/advanced/use-advanced-choice.ts` (spec Q5: keep the text `th.general.saveFailed`, pass the dropped error; `toast` is no longer used in this file):

Replace (1):
```ts
import { useMutation, useQuery, useQueryClient, type QueryClient } from "@tanstack/react-query"
import { toast } from "sonner"

import { fill, th } from "@/i18n/th"
import {
  chapterBlock,
```
with:
```ts
import { useMutation, useQuery, useQueryClient, type QueryClient } from "@tanstack/react-query"
import { showErrorToast } from "@/components/error-report/error-toast"
import { fill, th } from "@/i18n/th"
import {
  chapterBlock,
```

Replace (2):
```ts
  type RangeCheck,
} from "@/lib/advanced-options"
import { NO_ADVANCED, SPONSOR_CATEGORIES, sponsorCategories, type AdvancedParams } from "@/lib/download-options"
import { patchSettings, SETTINGS_KEY, settingsQuery } from "@/lib/settings-api"
import type { Settings, SponsorCategory, VideoInfo } from "@/lib/types"
```
with:
```ts
  type RangeCheck,
} from "@/lib/advanced-options"
import { NO_ADVANCED, SPONSOR_CATEGORIES, sponsorCategories, type AdvancedParams } from "@/lib/download-options"
import { reportRequest } from "@/lib/report"
import { patchSettings, SETTINGS_KEY, settingsQuery } from "@/lib/settings-api"
import type { Settings, SponsorCategory, VideoInfo } from "@/lib/types"
```

Replace (3):
```ts
      if (previous) client.setQueryData<Settings>(SETTINGS_KEY, { ...previous, sponsorblockDefault: next })
      return { previous }
    },
    onError: (_error: unknown, _next: SponsorCategory[], context: { previous: Settings | undefined } | undefined) => {
      if (context?.previous) client.setQueryData(SETTINGS_KEY, context.previous)
      toast.error(th.general.saveFailed)
    },
    onSuccess: (saved: Settings) => {
      if (client.isMutating({ mutationKey: SPONSOR_MUTATION_KEY }) <= 1) client.setQueryData(SETTINGS_KEY, saved)
```
with:
```ts
      if (previous) client.setQueryData<Settings>(SETTINGS_KEY, { ...previous, sponsorblockDefault: next })
      return { previous }
    },
    onError: (error: unknown, _next: SponsorCategory[], context: { previous: Settings | undefined } | undefined) => {
      if (context?.previous) client.setQueryData(SETTINGS_KEY, context.previous)
      showErrorToast(th.general.saveFailed, { id: "advanced-save", request: reportRequest(error, { context: "advanced-save" }) })
    },
    onSuccess: (saved: Settings) => {
      if (client.isMutating({ mutationKey: SPONSOR_MUTATION_KEY }) <= 1) client.setQueryData(SETTINGS_KEY, saved)
```

Not changed on purpose (spec §1.3 "still excluded"): the copy-failure toasts in `capture-strip.tsx` (`copyCapture`), `clip-details.tsx`, `frames.tsx` (`copyFrameImage`, `copyText`), `subs/export-buttons.tsx`, and the local validation toast in `player/range-mark-buttons.tsx`.

- [ ] **Step 6: Run, expect PASS**

Run: `cd "$WORKTREE/web" && npm run typecheck && npm run lint && npm test` (prototype: 1,032 tests passed, ESLint clean). Then `cd "$WORKTREE/web" && git grep -n "<LoadError" -- src | grep -v "context=" ` must print only the multi-line JSX openings (every `LoadError` element has a `context=` line; check by eye that each of the 9 sites has one).

- [ ] **Step 7: Commit**
```bash
cd "$WORKTREE" && git add web/src/pages/video.tsx web/src/pages/history.tsx web/src/pages/batch.tsx web/src/pages/video && git commit -F- <<'EOF'
feat(web): details section and copy button on every clip-page, history and batch error

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
EOF
```


### Task 9: Web — queue (failed row, failed-job toast, small action toasts), crash panel, account delete

**Files:**
- Modify: `web/src/components/queue/job-row.tsx` (FailedRow uses `ErrorDetails`; `copyDetails` deleted)
- Modify: `web/src/components/queue/use-queue.ts` (failed-job toast, finished toast `PLAIN_TOAST`, `revealWithToast`, `runJobAction`, `useReorder`)
- Modify: `web/src/components/queue/use-queue-events.test.ts`
- Modify: `web/src/components/queue/pause-alert.tsx`, `web/src/components/queue/shutdown-dialog.tsx`, `web/src/components/account/use-account.ts`
- Modify: `web/src/components/error-panel.tsx`, `web/src/components/route-error.tsx`
- Modify: `web/src/i18n/th.ts` (remove `queue.copyDetails` only)
- Modify: `web/e2e/nav.spec.ts` (`:222`), `web/e2e/queue-flow.spec.ts` (`:205`)

**Interfaces:**
- Consumes (T4): `ErrorDetails` (`request` + `open` / `onOpenChange`), `CopyReportButton`, `showErrorToast`, `PLAIN_TOAST`, `reportRequest`.
- Produces: K7 ids `job-<id>` (failed-job request `{ jobId, code, detail, context: "queue" }`), `queue-action-<id>`, `queue-reorder`, `queue-resume`, `queue-reveal-<id>`, `account-delete`, `shutdown-error`; contexts `chunk` / `crash` in `ErrorPanel`; `RouteError` renders its own `<Toaster position="bottom-right" />`.

Planner ruling P12 (layout, C9): `ErrorPanel` keeps the `AlertAction` slot but makes it a static row under the message (`static col-start-2 mt-2 flex flex-wrap gap-2`). Two buttons in the default absolute top-right slot would cover the title at 640 px.

- [ ] **Step 1: Write the failing tests** — `web/src/components/queue/use-queue-events.test.ts`:

Replace (1):
```ts
import { QueryClient } from "@tanstack/react-query"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

import { accountDialog } from "@/components/account/account-store"
import { ACCOUNT_KEY } from "@/lib/account"
import { ApiError } from "@/lib/api"
import { JOBS_KEY } from "@/lib/jobs"
```
with:
```ts
import { QueryClient } from "@tanstack/react-query"
import type { ReactElement, ReactNode } from "react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

import { accountDialog } from "@/components/account/account-store"
import { CopyReportButton } from "@/components/error-report/copy-report-button"
import { ACCOUNT_KEY } from "@/lib/account"
import { ApiError } from "@/lib/api"
import { JOBS_KEY } from "@/lib/jobs"
```

Replace (2):
```ts
    const invalidate = vi.spyOn(client, "invalidateQueries")
    api.retryJob.mockRejectedValueOnce(new ApiError(500, "E_UNKNOWN", "พัง", null, null))
    await runJobAction(client, "retry", "j1")
    expect(toast.error).toHaveBeenCalledWith("ทำรายการนี้ไม่สำเร็จ ลองรีเฟรชหน้าเว็บ")
    expect(invalidate).toHaveBeenCalledWith({ queryKey: JOBS_KEY })
  })
})

describe("serverEventHandlers: ปิดโปรแกรม", () => {
  it("บัญชีถูกลบเพราะปิดโปรแกรม: ล้าง toast อื่นทีละตัว แต่ toast ลบบัญชีที่ขึ้นอยู่แล้วยังอยู่ (ไม่สร้างใหม่)", () => {
    const handlers = serverEventHandlers(new QueryClient())
```
with:
```ts
    const invalidate = vi.spyOn(client, "invalidateQueries")
    api.retryJob.mockRejectedValueOnce(new ApiError(500, "E_UNKNOWN", "พัง", null, null))
    await runJobAction(client, "retry", "j1")
    const [message, options] = toast.error.mock.lastCall as unknown as [string, ToastOptions]
    expect(message).toBe("ทำรายการนี้ไม่สำเร็จ ลองรีเฟรชหน้าเว็บ")
    expect(options.id).toBe("queue-action-j1") // M6 รอบ B (spec Q5): ค้างจนกดปิด มีปุ่มคัดลอก ส่ง error จริงไปกับรายงาน
    expect(options.duration).toBe(Infinity)
    expect(copyButton(options).props.request).toEqual({ code: "E_UNKNOWN", context: "queue-action", jobId: "j1" })
    expect(invalidate).toHaveBeenCalledWith({ queryKey: JOBS_KEY })
  })
})

type ToastOptions = {
  id?: string
  duration?: number
  description?: ReactElement<{ children: ReactNode[] }>
  action?: { label: string }
  cancel?: { label: string }
}
const copyButton = (options: ToastOptions) =>
  options.description!.props.children[1] as ReactElement<{ request: Record<string, string | undefined> }>

describe("serverEventHandlers: toast ของงาน (M6 รอบ B)", () => {
  it("งานพลาด = ค้างจนกดปิด id job-<id> ข้อความ error อยู่ก่อนปุ่มคัดลอก รายงานหางานจาก jobId", () => {
    serverEventHandlers(new QueryClient()).onJobChange?.(job(), failed("E_YT_REFUSED"))
    const [message, options] = toast.error.mock.lastCall as unknown as [string, ToastOptions]
    expect(message).toBe("โหลดไม่สำเร็จ · คลิปจำกัดอายุ")
    expect(options.id).toBe("job-j1")
    expect(options.duration).toBe(Infinity)
    expect(options.description!.props.children[0]).toBe("คลิปนี้จำกัดอายุ")
    const button = copyButton(options)
    expect(button.type).toBe(CopyReportButton)
    expect(button.props.request).toEqual({ jobId: "j1", code: "E_YT_REFUSED", detail: "x", context: "queue" })
  })

  it("งานที่เคยพลาดแล้วเสร็จ = toast เสร็จล้างปุ่มคัดลอกและเวลาค้างของ toast พลาดตัวเดิม (P5)", () => {
    serverEventHandlers(new QueryClient()).onJobChange?.(failed("E_NETWORK"), job({ status: "done" }))
    const [message, options] = toast.success.mock.lastCall as unknown as [string, ToastOptions & Record<string, unknown>]
    expect(message).toBe("โหลดเสร็จแล้ว · คลิปจำกัดอายุ")
    expect(options.id).toBe("job-j1")
    for (const key of ["description", "duration", "cancel"]) {
      expect(key in options).toBe(true)
      expect(options[key]).toBeUndefined()
    }
  })
})

describe("serverEventHandlers: ปิดโปรแกรม", () => {
  it("บัญชีถูกลบเพราะปิดโปรแกรม: ล้าง toast อื่นทีละตัว แต่ toast ลบบัญชีที่ขึ้นอยู่แล้วยังอยู่ (ไม่สร้างใหม่)", () => {
    const handlers = serverEventHandlers(new QueryClient())
```

- [ ] **Step 2: Run, expect FAIL**

Run: `cd "$WORKTREE/web" && npx vitest run src/components/queue/use-queue-events.test.ts`
Expected: the `runJobAction` test fails (`options` is `undefined`), the new failed-toast test fails on `options.description!.props` (description is a string today), the finished-toast test fails on `"description" in options`.

- [ ] **Step 3: Queue toasts** — `web/src/components/queue/use-queue.ts`:

Replace (1):
```ts

import { openAccountDialog } from "@/components/account/account-store"
import { REMOVED_TOAST_ID, showRemovedToast } from "@/components/account/use-account"
import { fill, th } from "@/i18n/th"
import { ACCOUNT_KEY, showAccountButton, type AccountEvent } from "@/lib/account"
import { ApiError } from "@/lib/api"
import { connectEvents, type ConnectOptions } from "@/lib/events"
import { cancelJob, JOBS_KEY, jobsQuery, queueQuery, reorderJobs, retryJob, revealOutput } from "@/lib/jobs"
import type { AccountStatus, Job } from "@/lib/types"

import { jobTitle } from "./job-text"
```
with:
```ts

import { openAccountDialog } from "@/components/account/account-store"
import { REMOVED_TOAST_ID, showRemovedToast } from "@/components/account/use-account"
import { showErrorToast } from "@/components/error-report/error-toast"
import { PLAIN_TOAST } from "@/components/error-report/model"
import { fill, th } from "@/i18n/th"
import { ACCOUNT_KEY, showAccountButton, type AccountEvent } from "@/lib/account"
import { ApiError } from "@/lib/api"
import { connectEvents, type ConnectOptions } from "@/lib/events"
import { cancelJob, JOBS_KEY, jobsQuery, queueQuery, reorderJobs, retryJob, revealOutput } from "@/lib/jobs"
import { reportRequest } from "@/lib/report"
import type { AccountStatus, Job } from "@/lib/types"

import { jobTitle } from "./job-text"
```

Replace (2):
```ts
  try {
    await revealOutput(id, index)
  } catch (error) {
    toast.error(error instanceof ApiError && error.status === 404 ? th.queue.fileMissing : th.queue.revealFailed)
  }
}
```
with:
```ts
  try {
    await revealOutput(id, index)
  } catch (error) {
    // M6 รอบ B (spec Q5): ข้อความเดิม + ปุ่มคัดลอก (ส่ง error จริงไปกับรายงาน)
    showErrorToast(error instanceof ApiError && error.status === 404 ? th.queue.fileMissing : th.queue.revealFailed, {
      id: `queue-reveal-${id}`,
      request: reportRequest(error, { context: "queue-reveal", jobId: id }),
    })
  }
}
```

Replace (3):
```ts
  const title = jobTitle(after)
  if (kind === "finished") {
    const first = after.outputs?.[0]
    toast.success(fill(th.queue.finished, { title }), {
      id: `job-${after.id}`,
      action: first
        ? { label: th.queue.openFolder, onClick: () => void revealWithToast(after.id, first.index) }
```
with:
```ts
  const title = jobTitle(after)
  if (kind === "finished") {
    const first = after.outputs?.[0]
    // ...PLAIN_TOAST: งานที่เคยพลาดแล้วลองใหม่จนเสร็จใช้ id เดิม sonner รวมค่าทับ toast พลาดตัวเดิม (P5)
    toast.success(fill(th.queue.finished, { title }), {
      ...PLAIN_TOAST,
      id: `job-${after.id}`,
      action: first
        ? { label: th.queue.openFolder, onClick: () => void revealWithToast(after.id, first.index) }
```

Replace (4):
```ts
          onClick: () => openAccountDialog({ origin: "error", onImported: () => void runJobAction(client, "retry", after.id) }),
        }
      : null
    toast.error(fill(th.queue.failed, { title }), {
      id: `job-${after.id}`,
      description: after.error?.message,
      duration: Infinity,
      action: account ?? details,
      cancel: account ? details : undefined,
    })
  }
}
```
with:
```ts
          onClick: () => openAccountDialog({ origin: "error", onImported: () => void runJobAction(client, "retry", after.id) }),
        }
      : null
    // M6 รอบ B: ปุ่มคัดลอกอยู่ในแถว description (action / cancel เป็นของปุ่มบัญชีกับ "ดูรายละเอียด" เหมือนเดิม)
    showErrorToast(fill(th.queue.failed, { title }), {
      id: `job-${after.id}`,
      description: after.error?.message,
      action: account ?? details,
      cancel: account ? details : undefined,
      request: { jobId: after.id, code: after.error?.code, detail: after.error?.detail ?? undefined, context: "queue" },
    })
  }
}
```

Replace (5):
```ts
  try {
    const job = await (action === "cancel" ? cancelJob(id) : retryJob(id))
    client.setQueryData<Job[]>(JOBS_KEY, (old) => applyActionResult(old, job))
  } catch {
    toast.error(th.queue.actionFailed)
    void client.invalidateQueries({ queryKey: JOBS_KEY })
  }
}
```
with:
```ts
  try {
    const job = await (action === "cancel" ? cancelJob(id) : retryJob(id))
    client.setQueryData<Job[]>(JOBS_KEY, (old) => applyActionResult(old, job))
  } catch (error) {
    showErrorToast(th.queue.actionFailed, {
      id: `queue-action-${id}`,
      request: reportRequest(error, { context: "queue-action", jobId: id }),
    })
    void client.invalidateQueries({ queryKey: JOBS_KEY })
  }
}
```

Replace (6):
```ts
      client.setQueryData<Job[]>(JOBS_KEY, next)
      try {
        await reorderJobs(ids)
      } catch {
        client.setQueryData<Job[]>(JOBS_KEY, (old) => (old === undefined ? old : rollbackReorder(old, snapshot)))
        toast.error(th.queue.actionFailed)
      }
    },
    [client],
```
with:
```ts
      client.setQueryData<Job[]>(JOBS_KEY, next)
      try {
        await reorderJobs(ids)
      } catch (error) {
        client.setQueryData<Job[]>(JOBS_KEY, (old) => (old === undefined ? old : rollbackReorder(old, snapshot)))
        showErrorToast(th.queue.actionFailed, { id: "queue-reorder", request: reportRequest(error, { context: "queue-reorder" }) })
      }
    },
    [client],
```

- [ ] **Step 4: The failed row** — `web/src/components/queue/job-row.tsx` (the controlled `open` and `data-details-trigger=""` the toast's "ดูรายละเอียด" relies on stay — `ErrorDetails` sets the attribute on its trigger):

Replace (1):
```tsx
import { ChevronDown, CircleCheck, CirclePause, CircleX, Copy, Download, FolderOpen, RotateCcw } from "lucide-react"
import { useState, type ComponentProps, type ReactNode } from "react"
import { toast } from "sonner"

import { UseAccountButton } from "@/components/account/account-button"
import { useAccountStatus } from "@/components/account/use-account"
import { Badge } from "@/components/ui/badge"
import { Button, buttonVariants } from "@/components/ui/button"
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible"
import { Progress } from "@/components/ui/progress"
import { Spinner } from "@/components/ui/spinner"
import { fill, th } from "@/i18n/th"
```
with:
```tsx
import { CircleCheck, CirclePause, CircleX, Download, FolderOpen, RotateCcw } from "lucide-react"
import { useState, type ComponentProps, type ReactNode } from "react"

import { UseAccountButton } from "@/components/account/account-button"
import { useAccountStatus } from "@/components/account/use-account"
import { ErrorDetails } from "@/components/error-report/error-details"
import { Badge } from "@/components/ui/badge"
import { Button, buttonVariants } from "@/components/ui/button"
import { Progress } from "@/components/ui/progress"
import { Spinner } from "@/components/ui/spinner"
import { fill, th } from "@/i18n/th"
```

Replace (2):
```tsx
  )
}

async function copyDetails(text: string): Promise<void> {
  try {
    await navigator.clipboard.writeText(text)
    toast.success(th.video.copied)
  } catch {
    toast.error(th.video.copyFailed)
  }
}

/** แถวงานที่พลาดหรือหยุดกลางคัน: ข้อความผิดพลาด · "ดูรายละเอียด" (รหัส + ข้อความเทคนิค + คัดลอก) · "ลองใหม่" */
export function FailedRow({ job, expanded }: { job: Job; expanded: boolean }) {
  const retry = useJobAction("retry", job.id)
  // เปิดจาก toast "ดูรายละเอียด" = กางรายละเอียด แม้แถวนี้จะแสดงอยู่แล้วก่อนหน้า
```
with:
```tsx
  )
}

/**
 * แถวงานที่พลาดหรือหยุดกลางคัน: ข้อความผิดพลาด · "ดูรายละเอียด" (รหัส + ข้อความเทคนิค + "คัดลอกข้อมูลแจ้งปัญหา") · "ลองใหม่"
 * M6 รอบ B: ปุ่มคัดลอกรายงานแทนปุ่ม "คัดลอกรายละเอียด" เดิม · เซิร์ฟเวอร์หางานจาก jobId ก่อน code/detail เป็นตัวสำรอง
 */
export function FailedRow({ job, expanded }: { job: Job; expanded: boolean }) {
  const retry = useJobAction("retry", job.id)
  // เปิดจาก toast "ดูรายละเอียด" = กางรายละเอียด แม้แถวนี้จะแสดงอยู่แล้วก่อนหน้า
```

Replace (3):
```tsx
          </div>
        )}
        {code && (
          <Collapsible open={open} onOpenChange={setOpen}>
            <CollapsibleTrigger
              data-details-trigger=""
              render={<Button variant="link" size="sm" className="group/details h-7 px-0 text-muted-foreground" />}
            >
              {th.queue.details}
              <ChevronDown aria-hidden className="transition-transform group-data-[panel-open]/details:rotate-180" />
            </CollapsibleTrigger>
            <CollapsibleContent className="flex flex-col items-start gap-2 pt-1">
              <p className="font-mono text-xs">{fill(th.queue.errorCode, { code })}</p>
              {detail && (
                <pre className="max-h-40 w-full overflow-auto rounded-md bg-muted p-2 font-mono text-xs break-all whitespace-pre-wrap">
                  {detail}
                </pre>
              )}
              <Button variant="outline" size="sm" onClick={() => void copyDetails(detail ? `${code}\n${detail}` : code)}>
                <Copy aria-hidden />
                {th.queue.copyDetails}
              </Button>
            </CollapsibleContent>
          </Collapsible>
        )}
      </div>
      <Button
```
with:
```tsx
          </div>
        )}
        {code && (
          <ErrorDetails
            request={{ jobId: job.id, code, detail: detail ?? undefined, context: "queue" }}
            open={open}
            onOpenChange={setOpen}
          />
        )}
      </div>
      <Button
```

`web/src/i18n/th.ts` — the last user of `queue.copyDetails` is gone (`queue.details` / `queue.errorCode` stay: the toast action still uses `queue.details`):

Replace (1):
```ts
    downloadOf: "ดาวน์โหลด {file}",
    details: "ดูรายละเอียด",
    errorCode: "รหัส {code}",
    copyDetails: "คัดลอกรายละเอียด",
    dragHandle: "ลากเพื่อเปลี่ยนลำดับ {title}",
    dnd: {
      picked: "ยก {title} ขึ้นแล้ว กดลูกศรขึ้นหรือลงเพื่อย้าย แล้วกด Space เพื่อวาง",
```
with:
```ts
    downloadOf: "ดาวน์โหลด {file}",
    details: "ดูรายละเอียด",
    errorCode: "รหัส {code}",
    dragHandle: "ลากเพื่อเปลี่ยนลำดับ {title}",
    dnd: {
      picked: "ยก {title} ขึ้นแล้ว กดลูกศรขึ้นหรือลงเพื่อย้าย แล้วกด Space เพื่อวาง",
```

- [ ] **Step 5: The small action toasts (spec Q5) and shutdown**

`web/src/components/queue/pause-alert.tsx`:

Replace (1):
```tsx
import { useMutation, useQueryClient } from "@tanstack/react-query"
import { Hourglass } from "lucide-react"
import { useEffect, useState } from "react"
import { toast } from "sonner"

import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
import { Button } from "@/components/ui/button"
import { Spinner } from "@/components/ui/spinner"
import { th } from "@/i18n/th"
import { QUEUE_KEY, resumeQueue } from "@/lib/jobs"
import type { QueueState } from "@/lib/types"
import { cn } from "cn"
```
with:
```tsx
import { useMutation, useQueryClient } from "@tanstack/react-query"
import { Hourglass } from "lucide-react"
import { useEffect, useState } from "react"

import { showErrorToast } from "@/components/error-report/error-toast"
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
import { Button } from "@/components/ui/button"
import { Spinner } from "@/components/ui/spinner"
import { th } from "@/i18n/th"
import { QUEUE_KEY, resumeQueue } from "@/lib/jobs"
import { reportRequest } from "@/lib/report"
import type { QueueState } from "@/lib/types"
import { cn } from "cn"
```

Replace (2):
```tsx
    mutationFn: () => resumeQueue(),
    onSuccess: () =>
      client.setQueryData<QueueState>(QUEUE_KEY, (old) => (old === undefined ? old : { ...old, pausedUntil: null, reason: null })),
    onError: () => toast.error(th.queue.actionFailed),
  })

  if (pausedRemainingMs(pausedUntil, now) <= 0) return null
```
with:
```tsx
    mutationFn: () => resumeQueue(),
    onSuccess: () =>
      client.setQueryData<QueueState>(QUEUE_KEY, (old) => (old === undefined ? old : { ...old, pausedUntil: null, reason: null })),
    onError: (error) =>
      showErrorToast(th.queue.actionFailed, { id: "queue-resume", request: reportRequest(error, { context: "queue-resume" }) }),
  })

  if (pausedRemainingMs(pausedUntil, now) <= 0) return null
```

`web/src/components/queue/shutdown-dialog.tsx` (`toast` stays for `toast.dismiss()`):

Replace (1):
```tsx
import { useState } from "react"
import { toast } from "sonner"

import {
  AlertDialog,
  AlertDialogAction,
```
with:
```tsx
import { useState } from "react"
import { toast } from "sonner"

import { showErrorToast } from "@/components/error-report/error-toast"
import {
  AlertDialog,
  AlertDialogAction,
```

Replace (2):
```tsx
import { fill, th } from "@/i18n/th"
import { api } from "@/lib/api"
import { appShutdown } from "@/lib/events"

import { useQueueData } from "./use-queue"
```
with:
```tsx
import { fill, th } from "@/i18n/th"
import { api } from "@/lib/api"
import { appShutdown } from "@/lib/events"
import { reportRequest } from "@/lib/report"

import { useQueueData } from "./use-queue"
```

Replace (3):
```tsx
      onShutdown?.()
      appShutdown.set()
    },
    onError: (error) => toast.error(error.message),
  })

  return (
```
with:
```tsx
      onShutdown?.()
      appShutdown.set()
    },
    onError: (error) =>
      showErrorToast(error.message, { id: "shutdown-error", request: reportRequest(error, { context: "shutdown" }) }),
  })

  return (
```

`web/src/components/account/use-account.ts` (`toast` stays for `showRemovedToast`):

Replace (1):
```ts
import { useEffect, useState } from "react"
import { toast } from "sonner"

import { th } from "@/i18n/th"
import { ACCOUNT_KEY, accountQuery, deleteAccount, INACTIVE } from "@/lib/account"
import type { AccountStatus } from "@/lib/types"

/** toast หลังลบบัญชี (ทุกเหตุผล ทุกแท็บ): ไม่หายเอง มีปุ่ม "ปิด" · id เดียว = ลบในแท็บนี้แล้วข่าว SSE ตามมาไม่เด้งซ้ำ */
```
with:
```ts
import { useEffect, useState } from "react"
import { toast } from "sonner"

import { showErrorToast } from "@/components/error-report/error-toast"
import { th } from "@/i18n/th"
import { ACCOUNT_KEY, accountQuery, deleteAccount, INACTIVE } from "@/lib/account"
import { reportRequest } from "@/lib/report"
import type { AccountStatus } from "@/lib/types"

/** toast หลังลบบัญชี (ทุกเหตุผล ทุกแท็บ): ไม่หายเอง มีปุ่ม "ปิด" · id เดียว = ลบในแท็บนี้แล้วข่าว SSE ตามมาไม่เด้งซ้ำ */
```

Replace (2):
```ts
      client.setQueryData<AccountStatus>(ACCOUNT_KEY, status)
      showRemovedToast()
    },
    onError: () => toast.error(th.queue.actionFailed),
  })
  return { remove: () => mutation.mutate(), pending: mutation.isPending }
}
```
with:
```ts
      client.setQueryData<AccountStatus>(ACCOUNT_KEY, status)
      showRemovedToast()
    },
    // M6 รอบ B (spec Q5): รายงานมีแค่บรรทัดสถานะบัญชีเหมือนทุกรายงาน (C4)
    onError: (error) =>
      showErrorToast(th.queue.actionFailed, { id: "account-delete", request: reportRequest(error, { context: "account-delete" }) }),
  })
  return { remove: () => mutation.mutate(), pending: mutation.isPending }
}
```

- [ ] **Step 6: The crash panel and its Toaster**

`web/src/components/error-panel.tsx`:

Replace (1):
```tsx
import { CircleX } from "lucide-react"

import {
  Alert,
  AlertAction,
```
with:
```tsx
import { CircleX } from "lucide-react"

import { CopyReportButton } from "@/components/error-report/copy-report-button"
import {
  Alert,
  AlertAction,
```

Replace (2):
```tsx
import { Button } from "@/components/ui/button"
import { th } from "@/i18n/th"
import { isChunkLoadError } from "@/lib/lazy-import"

// หน้าแทนเมื่อเปิดหน้าไม่สำเร็จ: ไฟล์โค้ดของหน้าหายหลังอัปเดตโปรแกรม (แท็บเก่า) หรือโค้ดหน้านั้นพัง
export function ErrorPanel({ error }: { error: unknown }) {
  return (
    <div className="pt-8">
      <Alert variant="destructive">
        <CircleX aria-hidden />
        <AlertTitle>{th.errors.pageTitle}</AlertTitle>
        <AlertDescription>
          {isChunkLoadError(error) ? th.errors.chunk : th.errors.crash}
        </AlertDescription>
        <AlertAction>
          <Button variant="outline" size="sm" onClick={() => location.reload()}>
            {th.common.reload}
          </Button>
```
with:
```tsx
import { Button } from "@/components/ui/button"
import { th } from "@/i18n/th"
import { isChunkLoadError } from "@/lib/lazy-import"
import { reportRequest } from "@/lib/report"

// หน้าแทนเมื่อเปิดหน้าไม่สำเร็จ: ไฟล์โค้ดของหน้าหายหลังอัปเดตโปรแกรม (แท็บเก่า) หรือโค้ดหน้านั้นพัง
// M6 รอบ B: ปุ่ม "คัดลอกข้อมูลแจ้งปัญหา" ก่อนปุ่มโหลดหน้าใหม่ (E_UNKNOWN + ชื่อ: ข้อความ + stack) ยังใช้ได้หลังหน้าพัง
// เพราะใช้แค่ api() กับ <meta> ของ token · ปุ่มสองปุ่มเรียงเป็นแถวใต้ข้อความ (หน้าต่าง 640 px ไม่ทับหัวข้อ)
export function ErrorPanel({ error }: { error: unknown }) {
  const chunk = isChunkLoadError(error)
  return (
    <div className="pt-8">
      <Alert variant="destructive">
        <CircleX aria-hidden />
        <AlertTitle>{th.errors.pageTitle}</AlertTitle>
        <AlertDescription>
          {chunk ? th.errors.chunk : th.errors.crash}
        </AlertDescription>
        <AlertAction className="static col-start-2 mt-2 flex flex-wrap gap-2">
          <CopyReportButton request={reportRequest(error, { context: chunk ? "chunk" : "crash" })} />
          <Button variant="outline" size="sm" onClick={() => location.reload()}>
            {th.common.reload}
          </Button>
```

`web/src/components/route-error.tsx`:

Replace (1):
```tsx
import { useRouteError } from "react-router"

import { ErrorPanel } from "@/components/error-panel"

// ตาข่ายชั้นสุดท้ายของ router: ข้อผิดพลาดที่หลุดจากทุกหน้า ไม่ให้เห็นหน้า error ภาษาอังกฤษของ React Router
export function RouteError() {
  return (
    <main className="mx-auto max-w-[960px] px-4">
      <ErrorPanel error={useRouteError()} />
    </main>
  )
}
```
with:
```tsx
import { useRouteError } from "react-router"

import { ErrorPanel } from "@/components/error-panel"
import { Toaster } from "@/components/ui/sonner"

// ตาข่ายชั้นสุดท้ายของ router: ข้อผิดพลาดที่หลุดจากทุกหน้า ไม่ให้เห็นหน้า error ภาษาอังกฤษของ React Router
// หน้านี้แทน Layout ทั้งหน้า (Toaster อยู่ใน Layout) จึงมี Toaster ของตัวเอง ไม่งั้น toast "คัดลอกแล้ว" ไม่ขึ้น (M6 รอบ B)
export function RouteError() {
  return (
    <main className="mx-auto max-w-[960px] px-4">
      <ErrorPanel error={useRouteError()} />
      <Toaster position="bottom-right" />
    </main>
  )
}
```

(`PageErrorBoundary` renders inside `Layout`, which already has the Toaster: no change.)

- [ ] **Step 7: E2E literals that pinned the old button**

`web/e2e/nav.spec.ts`:

Replace (1):
```ts
    await failed.getByRole("button", { name: "ดูรายละเอียด" }).click()
    await expect(failed.getByText("รหัส E_YT_REFUSED")).toBeVisible()
    await expect(failed.getByText("HTTP Error 403: Forbidden")).toBeVisible()
    await expect(failed.getByRole("button", { name: "คัดลอกรายละเอียด" })).toBeVisible()
    await expect(failed.getByRole("button", { name: "ลองใหม่ คลิปที่ยูทูปไม่ส่งไฟล์" })).toBeVisible()

    const done = sheet.locator(`[data-job-id="${DONE}"]`)
```
with:
```ts
    await failed.getByRole("button", { name: "ดูรายละเอียด" }).click()
    await expect(failed.getByText("รหัส E_YT_REFUSED")).toBeVisible()
    await expect(failed.getByText("HTTP Error 403: Forbidden")).toBeVisible()
    // M6 รอบ B: ปุ่มคัดลอกรายงานแทนปุ่มคัดลอกรายละเอียดเดิม
    await expect(failed.getByRole("button", { name: "คัดลอกข้อมูลแจ้งปัญหา" })).toBeVisible()
    await expect(failed.getByRole("button", { name: "คัดลอกรายละเอียด" })).toHaveCount(0)
    await expect(failed.getByRole("button", { name: "ลองใหม่ คลิปที่ยูทูปไม่ส่งไฟล์" })).toBeVisible()

    const done = sheet.locator(`[data-job-id="${DONE}"]`)
```

`web/e2e/queue-flow.spec.ts` (queue project, real fake jobs; run only at the gate with `--workers=1`):

Replace (1):
```ts
    await expect(failed).toContainText("ยูทูปไม่ยอมส่งไฟล์ของคลิปนี้ตอนนี้ ลองใหม่ภายหลัง")
    await failed.getByRole("button", { name: "ดูรายละเอียด" }).click()
    await expect(failed.getByText("รหัส E_YT_REFUSED")).toBeVisible()

    const retried = page.waitForResponse((r) => r.url().endsWith(`/api/jobs/${job.id}/retry`) && r.request().method() === "POST")
    await failed.getByRole("button", { name: `ลองใหม่ ${TITLE.REFUSEDDL01}` }).click()
```
with:
```ts
    await expect(failed).toContainText("ยูทูปไม่ยอมส่งไฟล์ของคลิปนี้ตอนนี้ ลองใหม่ภายหลัง")
    await failed.getByRole("button", { name: "ดูรายละเอียด" }).click()
    await expect(failed.getByText("รหัส E_YT_REFUSED")).toBeVisible()
    // M6 รอบ B: แถวที่พลาดมีปุ่มคัดลอกรายงานแทนปุ่มคัดลอกรายละเอียดเดิม
    await expect(failed.getByRole("button", { name: "คัดลอกข้อมูลแจ้งปัญหา" })).toBeVisible()
    await expect(failed.getByRole("button", { name: "คัดลอกรายละเอียด" })).toHaveCount(0)

    const retried = page.waitForResponse((r) => r.url().endsWith(`/api/jobs/${job.id}/retry`) && r.request().method() === "POST")
    await failed.getByRole("button", { name: `ลองใหม่ ${TITLE.REFUSEDDL01}` }).click()
```

- [ ] **Step 8: Run, expect PASS**

Run: `cd "$WORKTREE/web" && npm run typecheck && npm run lint && npm test` (prototype: 1,034 passed). `git grep -n "copyDetails\|คัดลอกรายละเอียด" -- web/src` prints nothing.

- [ ] **Step 9: Commit**
```bash
cd "$WORKTREE" && git add web/src/components web/src/i18n/th.ts web/e2e/nav.spec.ts web/e2e/queue-flow.spec.ts && git commit -F- <<'EOF'
feat(web): report button on failed jobs, queue action toasts and the crash panel

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
EOF
```


### Task 10: Web — home (W1), settings tabs, health page, enqueue toast

**Files:**
- Modify: `web/src/pages/home.tsx`, `web/src/pages/home/result-list.tsx`, `web/src/pages/home/use-analyze.tsx`
- Modify: `web/src/pages/settings/advanced-panel.tsx`, `web/src/pages/settings/general-panel.tsx`, `web/src/pages/settings/health-panel.tsx`
- Modify: `web/src/lib/jobs.ts`, `web/src/lib/jobs.test.ts`

**Interfaces:**
- Consumes (T4): `ErrorDetails`, `CopyReportButton`, `showErrorToast`, `PLAIN_TOAST`, `reportRequest`.
- Produces: `lib/jobs.ENQUEUE_TOAST_ID = "enqueue-error"`; K7 contexts `home`, `home-playlist`, `settings-advanced`, `settings-general`, `health-load`, `health`; toast ids `analyze-error`, `settings-general` (existing `TOAST_ID`), `settings-open`, `ffmpeg`, `shutdown-error`, `enqueue-error`. The health page's copy button sits right after "ตรวจอีกครั้ง" and before "ปิดโปรแกรม" (spec §1.6), `variant="outline"`, default size; its request is `{ context: "health" }` (no error section, D4).

Spec §1.3 notes honoured here: the output-folder field message (`dirError`) gets no details section (field feedback); the "ไปหน้าตรวจสุขภาพ" action of the enqueue toast stays; `health-panel.tsx:83` (backend 200 with `status: "error"`, no `ApiError`) sends `{ code: "E_TOOL_INSTALL_FAILED", detail: status.message, context: "ffmpeg-install" }`; `lib/jobs.ts` importing from `components/error-report/` is the accepted first `lib → components` import.

- [ ] **Step 1: Update the failing tests** — `web/src/lib/jobs.test.ts`:

Replace (1):
```ts
    const [text, options] = toastMock.error.mock.calls[0]
    expect(text).toBe("ยังไม่มี ffmpeg")
    expect(options.action.label).toBe("ไปหน้าตรวจสุขภาพ")
    options.action.onClick()
    expect(navigate).toHaveBeenCalledWith(HEALTH_PATH)
    expect(HEALTH_PATH).toBe("/settings/health")
```
with:
```ts
    const [text, options] = toastMock.error.mock.calls[0]
    expect(text).toBe("ยังไม่มี ffmpeg")
    expect(options.action.label).toBe("ไปหน้าตรวจสุขภาพ")
    // M6 รอบ B: ค้างจนกดปิด id คงที่ ปุ่มคัดลอกอยู่ในแถว description
    expect(options.id).toBe("enqueue-error")
    expect(options.duration).toBe(Infinity)
    expect(options.description.props.children[1].props.request).toEqual({ code: "E_FFMPEG_MISSING", context: "enqueue" })
    options.action.onClick()
    expect(navigate).toHaveBeenCalledWith(HEALTH_PATH)
    expect(HEALTH_PATH).toBe("/settings/health")
```

Replace (2):
```ts
    await expect(submitEnqueue(client, [newJob], messages, env)).resolves.toBe(
      false
    )
    expect(toastMock.error.mock.calls).toEqual([
      ["ค่าไม่ถูกต้อง"],
      ["ส่งไม่สำเร็จ"],
    ])
  })
})
```
with:
```ts
    await expect(submitEnqueue(client, [newJob], messages, env)).resolves.toBe(
      false
    )
    expect(toastMock.error.mock.calls.map((call) => call[0])).toEqual([
      "ค่าไม่ถูกต้อง",
      "ส่งไม่สำเร็จ",
    ])
    expect(toastMock.error.mock.calls.map((call) => call[1].id)).toEqual([
      "enqueue-error",
      "enqueue-error",
    ])
  })
})
```

- [ ] **Step 2: Run, expect FAIL**

Run: `cd "$WORKTREE/web" && npx vitest run src/lib/jobs.test.ts`
Expected: `options.id` is `undefined` in the `E_FFMPEG_MISSING` test; `call[1]` is `undefined` in the "error อื่น" test.

- [ ] **Step 3: Enqueue toast** — `web/src/lib/jobs.ts`:

Replace (1):
```ts
import { useNavigate } from "react-router"
import { toast } from "sonner"

import { fill } from "@/i18n/th"

import { api, ApiError } from "./api"
import type { Job, JobPatch, NewJob, QueueState } from "./types"

/** ทางลัดสำหรับเทส: ส่ง fetch/token ปลอมต่อให้ api() (ผู้ใช้จริงไม่ต้องส่ง) */
```
with:
```ts
import { useNavigate } from "react-router"
import { toast } from "sonner"

// M6 รอบ B: lib → components ครั้งแรก (toast ต้องมี JSX ของปุ่มคัดลอก) · lib/report.ts ยังไม่มี React
import { showErrorToast } from "@/components/error-report/error-toast"
import { fill } from "@/i18n/th"

import { api, ApiError } from "./api"
import { reportRequest } from "./report"
import type { Job, JobPatch, NewJob, QueueState } from "./types"

/** ทางลัดสำหรับเทส: ส่ง fetch/token ปลอมต่อให้ api() (ผู้ใช้จริงไม่ต้องส่ง) */
```

Replace (2):
```ts
/** ที่อยู่หน้าตรวจสุขภาพ (ติดตั้ง ffmpeg) สำหรับปุ่มใน toast เมื่อเครื่องยังไม่มี ffmpeg */
export const HEALTH_PATH = "/settings/health"

type EnqueueEnv = { navigate: (path: string) => void; deps?: ApiDeps }

/**
```
with:
```ts
/** ที่อยู่หน้าตรวจสุขภาพ (ติดตั้ง ffmpeg) สำหรับปุ่มใน toast เมื่อเครื่องยังไม่มี ffmpeg */
export const HEALTH_PATH = "/settings/health"

/** id ของ toast "ส่งเข้าคิวไม่สำเร็จ" (M6 รอบ B): พลาดซ้ำแทนที่ toast เดิม ไม่ซ้อนกัน */
export const ENQUEUE_TOAST_ID = "enqueue-error"

type EnqueueEnv = { navigate: (path: string) => void; deps?: ApiDeps }

/**
```

Replace (3):
```ts
    )
    return true
  } catch (error) {
    if (
      error instanceof ApiError &&
      error.status === 409 &&
      error.code === "E_FFMPEG_MISSING"
    ) {
      toast.error(error.message, {
        action: {
          label: messages.goHealth,
          onClick: () => env.navigate(HEALTH_PATH),
        },
      })
    } else {
      toast.error(
        error instanceof Error && error.message
          ? error.message
          : messages.failed
      )
    }
    return false
```
with:
```ts
    )
    return true
  } catch (error) {
    const request = reportRequest(error, { context: "enqueue" })
    if (
      error instanceof ApiError &&
      error.status === 409 &&
      error.code === "E_FFMPEG_MISSING"
    ) {
      showErrorToast(error.message, {
        id: ENQUEUE_TOAST_ID,
        request,
        action: {
          label: messages.goHealth,
          onClick: () => env.navigate(HEALTH_PATH),
        },
      })
    } else {
      showErrorToast(
        error instanceof Error && error.message
          ? error.message
          : messages.failed,
        { id: ENQUEUE_TOAST_ID, request }
      )
    }
    return false
```

- [ ] **Step 4: W1 (home)**

`web/src/pages/home.tsx`:

Replace (1):
```tsx
import { CircleX } from "lucide-react"
import { useRef, useState } from "react"

import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
import { Button } from "@/components/ui/button"
import { InputGroup, InputGroupAddon, InputGroupTextarea } from "@/components/ui/input-group"
```
with:
```tsx
import { CircleX } from "lucide-react"
import { useRef, useState } from "react"

import { ErrorDetails } from "@/components/error-report/error-details"
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
import { Button } from "@/components/ui/button"
import { InputGroup, InputGroupAddon, InputGroupTextarea } from "@/components/ui/input-group"
```

Replace (2):
```tsx
            <CircleX aria-hidden />
            <AlertTitle>{th.home.resolveFailed}</AlertTitle>
            <AlertDescription>{error.message}</AlertDescription>
          </Alert>
        )}
      </form>
```
with:
```tsx
            <CircleX aria-hidden />
            <AlertTitle>{th.home.resolveFailed}</AlertTitle>
            <AlertDescription>{error.message}</AlertDescription>
            <ErrorDetails error={error} context="home" className="col-start-2" />
          </Alert>
        )}
      </form>
```

`web/src/pages/home/result-list.tsx` (playlist row error):

Replace (1):
```tsx
import { useEffect, useId, useRef, useState, type ReactNode } from "react"
import { Link } from "react-router"

import { Alert, AlertAction, AlertDescription } from "@/components/ui/alert"
import { Badge } from "@/components/ui/badge"
import { Button, buttonVariants } from "@/components/ui/button"
```
with:
```tsx
import { useEffect, useId, useRef, useState, type ReactNode } from "react"
import { Link } from "react-router"

import { ErrorDetails } from "@/components/error-report/error-details"
import { Alert, AlertAction, AlertDescription } from "@/components/ui/alert"
import { Badge } from "@/components/ui/badge"
import { Button, buttonVariants } from "@/components/ui/button"
```

Replace (2):
```tsx
          <AlertDescription>
            {t.playlistError} · {playlist.error.message}
          </AlertDescription>
          <AlertAction>
            <Button
              variant="outline"
```
with:
```tsx
          <AlertDescription>
            {t.playlistError} · {playlist.error.message}
          </AlertDescription>
          <ErrorDetails error={playlist.error} context="home-playlist" className="col-start-2" />
          <AlertAction>
            <Button
              variant="outline"
```

`web/src/pages/home/use-analyze.tsx` (analyze from a non-home page; `toast` is no longer used in this file):

Replace (1):
```tsx
import { useMutation } from "@tanstack/react-query"
import { useEffect, useEffectEvent, useState, type ReactNode } from "react"
import { useLocation, useNavigate } from "react-router"
import { toast } from "sonner"

import { th } from "@/i18n/th"
import { api } from "@/lib/api"
import { looksLikeYoutube } from "@/lib/paste"
import type { ResolveItem, ResolveResult } from "@/lib/types"

import { AmbiguousDialog } from "./ambiguous-dialog"
```
with:
```tsx
import { useMutation } from "@tanstack/react-query"
import { useEffect, useEffectEvent, useState, type ReactNode } from "react"
import { useLocation, useNavigate } from "react-router"
import { showErrorToast } from "@/components/error-report/error-toast"
import { th } from "@/i18n/th"
import { api } from "@/lib/api"
import { looksLikeYoutube } from "@/lib/paste"
import { reportRequest } from "@/lib/report"
import type { ResolveItem, ResolveResult } from "@/lib/types"

import { AmbiguousDialog } from "./ambiguous-dialog"
```

Replace (2):
```tsx
    },
    onError: (error) => {
      // W1 แสดงข้อความใต้ช่องเอง ส่วนหน้าอื่นไม่มีช่อง จึงแจ้งด้วย toast
      if (!onHome) toast.error(`${th.home.resolveFailed} · ${error.message}`)
    },
  })
```
with:
```tsx
    },
    onError: (error) => {
      // W1 แสดงข้อความใต้ช่องเอง ส่วนหน้าอื่นไม่มีช่อง จึงแจ้งด้วย toast
      if (!onHome) {
        showErrorToast(`${th.home.resolveFailed} · ${error.message}`, {
          id: "analyze-error",
          request: reportRequest(error, { context: "analyze" }),
        })
      }
    },
  })
```

- [ ] **Step 5: Settings tabs**

`web/src/pages/settings/advanced-panel.tsx` (account status load error):

Replace (1):
```tsx

import { UseAccountButton } from "@/components/account/account-button"
import { useDeleteAccount, useNow } from "@/components/account/use-account"
import { Alert, AlertAction, AlertDescription, AlertTitle } from "@/components/ui/alert"
import { Button } from "@/components/ui/button"
import { Skeleton } from "@/components/ui/skeleton"
```
with:
```tsx

import { UseAccountButton } from "@/components/account/account-button"
import { useDeleteAccount, useNow } from "@/components/account/use-account"
import { ErrorDetails } from "@/components/error-report/error-details"
import { Alert, AlertAction, AlertDescription, AlertTitle } from "@/components/ui/alert"
import { Button } from "@/components/ui/button"
import { Skeleton } from "@/components/ui/skeleton"
```

Replace (2):
```tsx
        <CircleX aria-hidden />
        <AlertTitle>{th.general.loadError}</AlertTitle>
        <AlertDescription>{account.error instanceof ApiError ? account.error.message : th.errors.unknown}</AlertDescription>
        <AlertAction>
          <Button variant="outline" size="sm" onClick={() => void account.refetch()}>
            {th.common.retry}
```
with:
```tsx
        <CircleX aria-hidden />
        <AlertTitle>{th.general.loadError}</AlertTitle>
        <AlertDescription>{account.error instanceof ApiError ? account.error.message : th.errors.unknown}</AlertDescription>
        <ErrorDetails error={account.error} context="settings-advanced" className="col-start-2" />
        <AlertAction>
          <Button variant="outline" size="sm" onClick={() => void account.refetch()}>
            {th.common.retry}
```

`web/src/pages/settings/general-panel.tsx` (load error box; save and open-folder toasts; "บันทึกแล้ว" spreads `PLAIN_TOAST` because it shares `TOAST_ID` with the save error):

Replace (1):
```tsx
import { useId, useRef, useState } from "react"
import { toast } from "sonner"

import { Alert, AlertAction, AlertDescription, AlertTitle } from "@/components/ui/alert"
import { Button } from "@/components/ui/button"
import { Field, FieldDescription, FieldError, FieldGroup, FieldTitle } from "@/components/ui/field"
```
with:
```tsx
import { useId, useRef, useState } from "react"
import { toast } from "sonner"

import { showErrorToast } from "@/components/error-report/error-toast"
import { ErrorDetails } from "@/components/error-report/error-details"
import { PLAIN_TOAST } from "@/components/error-report/model"
import { Alert, AlertAction, AlertDescription, AlertTitle } from "@/components/ui/alert"
import { Button } from "@/components/ui/button"
import { Field, FieldDescription, FieldError, FieldGroup, FieldTitle } from "@/components/ui/field"
```

Replace (2):
```tsx
import { Skeleton } from "@/components/ui/skeleton"
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group"
import { th } from "@/i18n/th"
import { openOutputFolder, patchSettings, SETTINGS_KEY, settingsQuery } from "@/lib/settings-api"
import type { Settings } from "@/lib/types"
import { SwitchRow } from "@/pages/video/advanced/switch-row"
```
with:
```tsx
import { Skeleton } from "@/components/ui/skeleton"
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group"
import { th } from "@/i18n/th"
import { reportRequest } from "@/lib/report"
import { openOutputFolder, patchSettings, SETTINGS_KEY, settingsQuery } from "@/lib/settings-api"
import type { Settings } from "@/lib/types"
import { SwitchRow } from "@/pages/video/advanced/switch-row"
```

Replace (3):
```tsx
      queryClient.setQueryData<Settings>(SETTINGS_KEY, next)
      // บันทึกช่องอื่นสำเร็จ ไม่ลบข้อความผิดของช่องโฟลเดอร์ที่ยังแก้ไม่เสร็จ
      if ("outputDir" in patch) setDirError(null)
      toast.success(t.saved, { id: TOAST_ID })
    },
    onError: (error, patch) => {
      // ช่องโฟลเดอร์แสดงข้อความของเซิร์ฟเวอร์ใต้ช่อง ช่องอื่น (เลือกจากรายการ) แจ้งด้วย toast
      if ("outputDir" in patch) setDirError(serverMessage(error))
      else toast.error(serverMessage(error), { id: TOAST_ID })
    },
  })

  const open = useMutation({
    mutationFn: () => openOutputFolder(),
    onError: (error) => toast.error(serverMessage(error)),
  })

  // บันทึกล่าสุดที่ยังรออยู่: "เปิดโฟลเดอร์" รอให้บันทึกจบก่อน จะได้เปิดโฟลเดอร์ที่เพิ่งตั้ง (ไม่ปิดปุ่ม เพราะกดปุ่มทำให้ช่องเสียโฟกัสและบันทึกอัตโนมัติ)
```
with:
```tsx
      queryClient.setQueryData<Settings>(SETTINGS_KEY, next)
      // บันทึกช่องอื่นสำเร็จ ไม่ลบข้อความผิดของช่องโฟลเดอร์ที่ยังแก้ไม่เสร็จ
      if ("outputDir" in patch) setDirError(null)
      // ...PLAIN_TOAST: id เดียวกับ toast error ของการบันทึก ไม่ให้ปุ่มคัดลอก/เวลาค้างติดมากับ "บันทึกแล้ว" (P5)
      toast.success(t.saved, { ...PLAIN_TOAST, id: TOAST_ID })
    },
    onError: (error, patch) => {
      // ช่องโฟลเดอร์แสดงข้อความของเซิร์ฟเวอร์ใต้ช่อง ช่องอื่น (เลือกจากรายการ) แจ้งด้วย toast
      if ("outputDir" in patch) setDirError(serverMessage(error))
      else showErrorToast(serverMessage(error), { id: TOAST_ID, request: reportRequest(error, { context: "settings-general" }) })
    },
  })

  const open = useMutation({
    mutationFn: () => openOutputFolder(),
    onError: (error) =>
      showErrorToast(serverMessage(error), { id: "settings-open", request: reportRequest(error, { context: "settings-general" }) }),
  })

  // บันทึกล่าสุดที่ยังรออยู่: "เปิดโฟลเดอร์" รอให้บันทึกจบก่อน จะได้เปิดโฟลเดอร์ที่เพิ่งตั้ง (ไม่ปิดปุ่ม เพราะกดปุ่มทำให้ช่องเสียโฟกัสและบันทึกอัตโนมัติ)
```

Replace (4):
```tsx
        <CircleX aria-hidden />
        <AlertTitle>{t.loadError}</AlertTitle>
        <AlertDescription>{settings.error.message}</AlertDescription>
        <AlertAction>
          <Button variant="outline" size="sm" disabled={settings.isFetching} onClick={() => void settings.refetch()}>
            {th.common.retry}
```
with:
```tsx
        <CircleX aria-hidden />
        <AlertTitle>{t.loadError}</AlertTitle>
        <AlertDescription>{settings.error.message}</AlertDescription>
        <ErrorDetails error={settings.error} context="settings-general" className="col-start-2" />
        <AlertAction>
          <Button variant="outline" size="sm" disabled={settings.isFetching} onClick={() => void settings.refetch()}>
            {th.common.retry}
```

- [ ] **Step 6: Health page**

`web/src/pages/settings/health-panel.tsx` (load-error details, ffmpeg install toasts with `PLAIN_TOAST` on the non-error ones, shutdown toast, the copy button in the action row):

Replace (1):
```tsx
import { CircleAlert, CircleCheck, CircleX, FlaskConical, Power, RefreshCw } from "lucide-react"
import { toast } from "sonner"

import { ShutdownDialog } from "@/components/queue/shutdown-dialog"
import { Alert, AlertAction, AlertDescription, AlertTitle } from "@/components/ui/alert"
import { Badge } from "@/components/ui/badge"
```
with:
```tsx
import { CircleAlert, CircleCheck, CircleX, FlaskConical, Power, RefreshCw } from "lucide-react"
import { toast } from "sonner"

import { CopyReportButton } from "@/components/error-report/copy-report-button"
import { ErrorDetails } from "@/components/error-report/error-details"
import { showErrorToast } from "@/components/error-report/error-toast"
import { PLAIN_TOAST } from "@/components/error-report/model"
import { ShutdownDialog } from "@/components/queue/shutdown-dialog"
import { Alert, AlertAction, AlertDescription, AlertTitle } from "@/components/ui/alert"
import { Badge } from "@/components/ui/badge"
```

Replace (2):
```tsx
import { localClock } from "@/lib/account"
import { ApiError, api } from "@/lib/api"
import { appShutdown } from "@/lib/events"
import type { AccountHealth, Health, ToolState, ToolStatus } from "@/lib/types"

import { useHealth } from "./use-health"
```
with:
```tsx
import { localClock } from "@/lib/account"
import { ApiError, api } from "@/lib/api"
import { appShutdown } from "@/lib/events"
import { reportRequest } from "@/lib/report"
import type { AccountHealth, Health, ToolState, ToolStatus } from "@/lib/types"

import { useHealth } from "./use-health"
```

Replace (3):
```tsx

  const install = useMutation({
    mutationFn: () => api<ToolStatus>("/tools/ffmpeg/install", { method: "POST" }),
    onMutate: () => toast.loading(th.health.installing, { id: "ffmpeg" }),
    onSuccess: (status) => {
      // backend ตอบ 200 ทั้งที่ติดตั้งไม่สำเร็จได้ ดูสถานะจริงก่อนบอกว่าสำเร็จ
      // warn = มีการโหลดค้างอยู่แล้ว เป็นแค่ข้อมูล ไม่ใช่ข้อผิดพลาด จึงไม่ต้องค้างบนจอ
      if (status.status === "ok") toast.success(th.health.installed, { id: "ffmpeg" })
      else if (status.status === "warn") toast.info(status.message ?? th.health.installing, { id: "ffmpeg" })
      else toast.error(status.message ?? th.errors.unknown, { id: "ffmpeg", duration: Infinity })
      void queryClient.invalidateQueries({ queryKey: ["health"] })
    },
    onError: (error) => toast.error(error.message, { id: "ffmpeg", duration: Infinity }),
  })

  const shutdown = useMutation({
```
with:
```tsx

  const install = useMutation({
    mutationFn: () => api<ToolStatus>("/tools/ffmpeg/install", { method: "POST" }),
    // ...PLAIN_TOAST: id "ffmpeg" เดียวกับ toast error ของการติดตั้งครั้งก่อน ไม่ให้ปุ่มคัดลอก/เวลาค้างติดมา (P5)
    onMutate: () => toast.loading(th.health.installing, { ...PLAIN_TOAST, id: "ffmpeg" }),
    onSuccess: (status) => {
      // backend ตอบ 200 ทั้งที่ติดตั้งไม่สำเร็จได้ ดูสถานะจริงก่อนบอกว่าสำเร็จ
      // warn = มีการโหลดค้างอยู่แล้ว เป็นแค่ข้อมูล ไม่ใช่ข้อผิดพลาด จึงไม่ต้องค้างบนจอ
      if (status.status === "ok") toast.success(th.health.installed, { ...PLAIN_TOAST, id: "ffmpeg" })
      else if (status.status === "warn") toast.info(status.message ?? th.health.installing, { ...PLAIN_TOAST, id: "ffmpeg" })
      else {
        // ไม่มี ApiError (ตอบ 200 แต่ status error): ใช้รหัสของ PRD ข้อ 7 สำหรับกรณีนี้ (spec 1.3)
        showErrorToast(status.message ?? th.errors.unknown, {
          id: "ffmpeg",
          request: { code: "E_TOOL_INSTALL_FAILED", detail: status.message ?? undefined, context: "ffmpeg-install" },
        })
      }
      void queryClient.invalidateQueries({ queryKey: ["health"] })
    },
    onError: (error) =>
      showErrorToast(error.message, { id: "ffmpeg", request: reportRequest(error, { context: "ffmpeg-install" }) }),
  })

  const shutdown = useMutation({
```

Replace (4):
```tsx
        setPendingJobs((error.body as { pendingJobs?: number } | null)?.pendingJobs ?? 0)
        return
      }
      toast.error(error.message)
    },
  })
```
with:
```tsx
        setPendingJobs((error.body as { pendingJobs?: number } | null)?.pendingJobs ?? 0)
        return
      }
      showErrorToast(error.message, { id: "shutdown-error", request: reportRequest(error, { context: "shutdown" }) })
    },
  })
```

Replace (5):
```tsx
        <CircleX aria-hidden />
        <AlertTitle>{th.health.loadError}</AlertTitle>
        <AlertDescription>{health.error.message}</AlertDescription>
        <AlertAction>
          <Button variant="outline" size="sm" onClick={() => void health.refetch()}>
            {th.health.retry}
```
with:
```tsx
        <CircleX aria-hidden />
        <AlertTitle>{th.health.loadError}</AlertTitle>
        <AlertDescription>{health.error.message}</AlertDescription>
        <ErrorDetails error={health.error} context="health-load" className="col-start-2" />
        <AlertAction>
          <Button variant="outline" size="sm" onClick={() => void health.refetch()}>
            {th.health.retry}
```

Replace (6):
```tsx
          <RefreshCw aria-hidden />
          {th.health.recheck}
        </Button>
        <Button variant="outline" onClick={() => shutdown.mutate()} disabled={shutdown.isPending}>
          {shutdown.isPending ? <Spinner /> : <Power aria-hidden />}
          {th.health.shutdown}
```
with:
```tsx
          <RefreshCw aria-hidden />
          {th.health.recheck}
        </Button>
        {/* M6 รอบ B (D4): รายงานของหน้าตรวจสุขภาพไม่มีหัวข้อ error · ถัดจาก "ตรวจอีกครั้ง" ก่อน "ปิดโปรแกรม" */}
        <CopyReportButton request={{ context: "health" }} size="default" />
        <Button variant="outline" onClick={() => shutdown.mutate()} disabled={shutdown.isPending}>
          {shutdown.isPending ? <Spinner /> : <Power aria-hidden />}
          {th.health.shutdown}
```

- [ ] **Step 7: Run, expect PASS**

Run: `cd "$WORKTREE/web" && npm run typecheck && npm run lint && npm test` (prototype after T8-T10: 1,034 passed, ESLint clean).

- [ ] **Step 8: Commit**
```bash
cd "$WORKTREE" && git add web/src/pages/home.tsx web/src/pages/home web/src/pages/settings web/src/lib/jobs.ts web/src/lib/jobs.test.ts && git commit -F- <<'EOF'
feat(web): details and report button on home, settings and health; enqueue toast

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
EOF
```


---

> **WIP:** tasks T11-T12, the spec-coverage table and the execution handoff follow in the next commit of this plan. Do not execute before the plan is complete.
