# M6 round B: two-layer errors, the problem report and logging (design)

Pete approved the design in conversation on 2026-10-12 (decisions file below). This written spec turns it into an implementable design. Pete answered the spec's five follow-up questions the same day (§9); the copy is final.

Round B implements PRD §7.1 / BRD FR-SET-5:
- every error the staff see gets a folded "ดูรายละเอียด" section (code + raw detail) and a **"คัดลอกข้อมูลแจ้งปัญหา"** button;
- the server builds one ready-to-paste Markdown report (machine state + the error + the last 50 log lines), with one redaction point;
- every job failure and every non-job API error lands in `run/logs/app.log` with its code.

It covers AC-SET-03, AC-SET-04, AC-SET-05 and the M6 part of AC-SET-06 (the report passes the canary rule). These ACs live in PRD §7.1; `docs/acceptance.md` has no rows for them yet (see §5).

It touches:
- `web/src/pages/video/load-error.tsx` and its 9 call sites;
- the queue's failed row, the failed-job toast and 12 other error toasts;
- `ErrorPanel` / `RouteError`;
- the health page;
- a new web module `components/error-report/` and `lib/report.ts`;
- a new endpoint `POST /api/diagnostics` and a new report builder `core/diagnostics.py`;
- `redact.py`, the Platform protocol, `probe.setup_file_log`, `core/queue.py` logging, `api/errors.py`;
- `core/tools.py` (JS-runtime warning text), `core/yterrors.py` and `th.ts` (`E_UNKNOWN` text);
- the docs.

Code facts were checked at HEAD `7ed59a9` (branch `main`).

## Owner decisions (2026-10-12)

These are binding. They come from Pete's answers to Q1-Q3 and the approved approach.

| # | Decision | Notes |
|---|---|---|
| D1 | **The copy button is at every error point** (Q1 = A). Inline error boxes get a collapsed "ดูรายละเอียด" section with the code, the raw detail and a "คัดลอกข้อมูลแจ้งปัญหา" button. Error toasts get the button and stay until dismissed (`duration: Infinity`). | §1 |
| D2 | **`E_JS_RUNTIME_MISSING` is a health-page warning**, not a download error (Q2 = A, corrected against the PRD). Its text is the PRD text. The report shows the JS runtime status. `E_SETTINGS_INVALID` belongs to round A. A corrupt on-disk settings file is not in the PRD and is not added. | §2.6 |
| D3 | **New `E_UNKNOWN` text** (Q3 = A): `มีบางอย่างผิดพลาด กด "คัดลอกข้อมูลแจ้งปัญหา" แล้วส่งให้ผู้ดูแล`. Update PRD §7 and every place the text lives. | §2.7 |
| D4 | **The server builds the whole report**, with one redaction point. Job errors are looked up by job id. Non-job errors send code + detail (+ a short context) from the web. The health page sends no error. | §2.1, §2.2 |
| D5 | **UI points:** LoadError (all users), queue FailedRow (button replaced), the failed-job toast, the other error toasts, ErrorPanel (crash / route error, must still work after a crash), the health page (button next to the re-check button). | §1.3 |
| D6 | **The report follows the PRD §7.1 template exactly.** Copy to the clipboard, then the toast "คัดลอกแล้ว". On failure use an existing error string. The OS version comes from a new Platform method. | §2.2, §2.4 |
| D7 | **Logging:** rotate at 5 MB and keep 3 files; every failed job logs time, code, job id, raw detail and a traceback; non-job API errors log their code; quiet `httpx` INFO lines. | §3 |

## Global constraints

Every task in the plan for this round must hold all of these. A reviewer rejects a change that breaks one.

- **C1 No `shell=True`.** No new subprocess is needed. The report reuses `tools.ffmpeg_status` / `tools.find_js_runtime`, which already call `subprocess.run([...])` with a list.
- **C2 Only `yttoolkit.platform` checks the OS.** No `sys.platform`, `os.name`, `platform.system()`, `sys.getwindowsversion()` or `platform.mac_ver()` outside `src/yttoolkit/platform/`. The OS version comes from `Platform.os_version()` (§2.4).
- **C3 `yt_dlp` is imported only in `src/yttoolkit/core/extractor.py`.** The report gets the yt-dlp version through `tools.ytdlp_status(lookup_latest=False)`, which already imports `extractor.ytdlp_version` lazily. `core/diagnostics.py` and `api/diagnostics.py` import neither `yt_dlp` nor `extractor`.
- **C4 Nothing personal leaves the app.** No personal data, app token, cookie names or values, absolute user-data paths or clip titles in `app.log`, SSE, API error bodies or the report. The report additionally has no cookie *names* at all (PRD §7.1, FR-CK-5). Paths under the home folder appear only as `~\...`. Traceback frame lines (`File "...", line N`) that point at the app's own code are the one existing exception: they keep their path after home redaction, as today.
- **C5 One redaction function, one call site per output.** The report runs every part through `redact.redact_report` in exactly one place (§2.3). The job-failure log line runs through `redact.redact_log_detail` in exactly one place (§3.2). The existing handler filters (`HomePathFilter`, `SecretFilter`) stay as the last safety net and must not be removed.
- **C6 No regression of existing privacy tests.** `tests/unit/test_handlers.py` (`test_logs_have_no_absolute_paths`, `test_logs_have_no_clip_title`, chapter titles), `tests/unit/test_handlers_sharp.py`, `tests/unit/test_redact.py`, `tests/api/test_errors.py` and `tests/integration/test_account_privacy.py` keep passing unchanged, except for the deliberate edits listed in §6.
- **C7 LF line endings** in every file except `*.bat` (`.gitattributes`: `* text=auto eol=lf`).
- **C8 Thai UI copy:** buttons start with a verb, no "กรุณา", no "!". **Never invent Thai.** Every Thai string comes from the PRD, the decisions file or the existing `web/src/i18n/th.ts` (§7). New log lines use ASCII `key=value` fields, so they need no new Thai at all (§3).
- **C9 Narrow window, not phones.** The target is a narrow desktop window: 640 px wide, or 200 % zoom. There is no new phone polish. The app is served on 127.0.0.1 only.
- **C10 The report endpoint is a token-protected `POST`.** `LocalOnlyMiddleware` already enforces `X-Toolkit-Token` + Origin for every non-GET request (`api/security.py:59-64`). Nothing in this round adds a GET that returns log content.
- **C11 No new dependencies**, Python or npm. Vitest stays node-only (no jsdom / testing-library), so component logic goes into `.ts` modules that can be tested without a DOM, as `components/account/dialog-model.ts` does.

## 1. User flow (web)

### 1.1 The shared pieces (`web/src/components/error-report/`, `web/src/lib/report.ts`)

**`lib/report.ts`** (pure, node-testable):
- `type ReportRequest = { jobId?: string; code?: string; detail?: string; context?: string; videoId?: string }`. This mirrors the API body (§2.1).
- `reportRequest(error: unknown, where: { context: string; videoId?: string; jobId?: string }): ReportRequest`:
  - `ApiError` → `code = error.code`, `detail = error.detail ?? undefined`;
  - any other `Error` → `code = "E_UNKNOWN"`, `detail = "<name>: <message>"` plus the first 10 lines of `error.stack` when present;
  - anything else → `code = "E_UNKNOWN"`, no detail;
  - `detail` is cut to `MAX_DETAIL = 4000` characters (the server limit, §2.1), so the server never returns 422 for a real error.
- `fetchReport(req, deps?): Promise<string>` calls `api<{ report: string }>("/diagnostics", { method: "POST", body: JSON.stringify(req) })` and returns `report`. The `api()` helper already adds the token header (`lib/api.ts:29-33`).
- `copyReport(req, deps?): Promise<CopyOutcome>` where `CopyOutcome = { ok: true } | { ok: false; message: string }`. It never throws.
  - Start `const text = fetchReport(req)` at once (still inside the click).
  - If `navigator.clipboard.write` and `ClipboardItem` exist: `clipboard.write([new ClipboardItem({ "text/plain": text.then((t) => new Blob([t], { type: "text/plain" })) })])`. This keeps the write inside the user's click even though the report arrives later, the same pattern as `copyImage` (`lib/clipboard.ts:60-74`). Otherwise: `await clipboard.writeText(await text)`.
  - On failure, decide which side failed: if `text` rejected → `{ ok: false, message: err instanceof ApiError ? err.message : th.errors.unknown }` (for the app being closed this is `th.errors.offline`, set by `api()`); else (the clipboard refused) → `{ ok: false, message: th.errors.copyFailed }`.
  - Add `text.catch(() => {})` so the promise never becomes an unhandled rejection (as `clipboard.ts:72` does).
  - `deps` injects `clipboard`, `ClipboardItem` and `fetchReport` for tests.

**`components/error-report/copy-report-button.tsx`:** `CopyReportButton({ request, variant = "outline", size = "sm" })`.
- Label `th.errors.copyReport` with the lucide `Copy` icon. While pending: disabled + `Spinner`, so a double click sends one request.
- On click: `copyReport(request)`, then `toast.success(th.errors.copied, { id: "report-copy" })` or `toast.error(outcome.message, { id: "report-copy" })`. The fixed id stops repeated clicks from stacking.
- It uses only `useState` and `api()`. No React Query, no account store, no router hooks, so it still works inside `ErrorPanel` after a crash.

**`components/error-report/error-details.tsx`:** `ErrorDetails({ error, context, videoId?, jobId?, defaultOpen? })`. This is the folded section, lifted out of `FailedRow` (`components/queue/job-row.tsx:130-151`) so every box looks the same:
- a `Collapsible` with the link-style trigger `th.errors.details` and the rotating `ChevronDown`, as in `job-row.tsx:132-138`;
- the content, in order:
  - `fill(th.errors.code, { code })`, in `font-mono text-xs`;
  - the raw detail in the existing `<pre className="max-h-40 w-full overflow-auto rounded-md bg-muted p-2 font-mono text-xs break-all whitespace-pre-wrap">`;
  - `CopyReportButton` with `reportRequest(error, { context, videoId, jobId })`;
- `code` / `detail` come from the same request object, so the box shows exactly what is sent;
- **open by default when the code is `E_UNKNOWN`** (`defaultOpen ?? code === "E_UNKNOWN"`). The new `E_UNKNOWN` message tells the user to press the button, so the button must be visible without a hidden step (planner ruling R1);
- `data-testid="error-details"` on the root.

**`components/error-report/error-toast.tsx`:** `showErrorToast(message, opts)`, where `opts = { request: ReportRequest; id?: string | number; description?: ReactNode; action?: Action; cancel?: Action }`. It calls `toast.error(message, { id, duration: Infinity, action, cancel, description: <>{description}<CopyReportButton request={opts.request} /></> })`.
- The copy button sits in the **description** row, not in sonner's `action` slot. Two reasons:
  - sonner closes a toast when its `action` is clicked, and the toast must stay so the user can also press "ดูรายละเอียด" or the account button;
  - the failed-job toast already uses both `action` and `cancel` (`use-queue.ts:188-194`).
- Every error toast passes a stable `id` (table in §1.3). A second failure from the same source replaces the toast instead of stacking another persistent one.

### 1.2 What the user sees
1. An error appears, either inline or as a toast, with the Thai `message` (unchanged).
2. Inline: "ดูรายละเอียด" opens the code, the raw detail and "คัดลอกข้อมูลแจ้งปัญหา". In toasts the button is visible directly.
3. Pressing the button: the button shows a spinner, the report is fetched, written to the clipboard, and the toast "คัดลอกแล้ว" appears.
4. The user pastes into chat (LINE / Teams / an AI) and sends it to the admin.
5. Failure: the toast shows the server message, `th.errors.offline` (app closed), or `th.errors.copyFailed` (clipboard refused). No new Thai.

### 1.3 Call sites that change

**Inline boxes.** `LoadError` gains two required props, `context: string` and optional `videoId?: string`, and renders `<ErrorDetails>` under the button row (`load-error.tsx:37-51`), inside the `Alert`, at `col-start-2`. The existing buttons (account, retry, home) stay.

| Box | File:line | `context` | `videoId` |
|---|---|---|---|
| W2 header (whole clip) | `pages/video/header.tsx:331` | `video-header` | yes |
| W2 subtitles gate | `pages/video/subtitle-gate.tsx:59` | `video-subtitles` | yes |
| W2 subtitle preview | `pages/video/subs/preview.tsx:150` | `video-subs-preview` | yes |
| W2 transcript | `pages/video/transcript-panel.tsx:178` | `video-transcript` | yes |
| W2 frames | `pages/video/frames.tsx:605` | `video-frames` | yes |
| W2 pinned comment | `pages/video/clip-details.tsx:255` | `video-pinned` | yes |
| History (both boxes) | `pages/history.tsx:145`, `:168` | `history` | no |
| Batch | `pages/batch.tsx:234` | `batch` | no |

The transcript panel (`transcript-panel.tsx:178`) was not in the gap analysis but uses `LoadError`, so it gets the section like the others.

Planner ruling R2 (D1 "every error point"): the other inline destructive boxes that show an `error.message` from an API failure get `<ErrorDetails>` too, placed after `AlertDescription`:

| Box | File:line | `context` |
|---|---|---|
| W1 analyze error | `pages/home.tsx:142` | `home` |
| W1 playlist row error | `pages/home/result-list.tsx:304` | `home-playlist` |
| Settings > ขั้นสูง load error | `pages/settings/advanced-panel.tsx:36` | `settings-advanced` |
| Settings > ทั่วไป load error | `pages/settings/general-panel.tsx:86` | `settings-general` |
| Health load error | `pages/settings/health-panel.tsx:117` | `health-load` |

**Not** given the section, because they are field feedback where the message itself is the fix: the output-folder message under the field (`general-panel.tsx` `dirError`) and the `E_COOKIES_INVALID` message in the account dialog. The dialog's message must also never offer a report while a cookie file is in hand.

**Toasts.** Each becomes `showErrorToast(...)` with the request built by `reportRequest(error, …)`:

| Toast | File:line | `context` | toast `id` |
|---|---|---|---|
| Failed job | `components/queue/use-queue.ts:188` | — (`jobId: after.id`, plus `code`/`detail` from `after.error`) | `job-<id>` (existing) |
| Capture failed (both branches) | `pages/video/capture/use-capture.ts:50`, `:55` | `capture` + `videoId` | `capture-error` |
| Enqueue failed (`E_FFMPEG_MISSING` and other) | `lib/jobs.ts:232`, `:239` | `enqueue` | `enqueue-error` |
| Settings save / open folder | `pages/settings/general-panel.tsx:52`, `:58` | `settings-general` | `TOAST_ID` (existing) / `settings-open` |
| Frames file download | `pages/video/frames.tsx:57` | `frames-download` | the existing loading-toast `id` |
| Capture download / delete / reveal | `pages/video/capture/capture-strip.tsx:74`, `:193`, `:215` | `capture-download` / `capture-delete` / `capture-reveal` | existing `id` / `capture-delete` / `capture-reveal` |
| Analyze from a non-home page | `pages/home/use-analyze.tsx:100` | `analyze` | `analyze-error` |
| ffmpeg install (error + exception) | `pages/settings/health-panel.tsx:83`, `:86` | `ffmpeg-install` | `ffmpeg` (existing) |
| Shutdown (health / dialog) | `pages/settings/health-panel.tsx:101`, `components/queue/shutdown-dialog.tsx:55` | `shutdown` | `shutdown-error` |
| W2 background refresh | `pages/video.tsx:57` | `video-refresh` + `videoId` | `video-refresh` |

Notes:
- **`health-panel.tsx:83`** (backend answered 200 with `status: "error"`) has no `ApiError`. Pass `{ code: "E_TOOL_INSTALL_FAILED", detail: status.message ?? undefined, context: "ffmpeg-install" }`. That is the PRD code for this case (§7).
- **Existing actions stay.** The failed-job toast keeps account / "ดูรายละเอียด" in `action` / `cancel`; the enqueue toast keeps "ไปหน้าตรวจสุขภาพ"; the capture toast keeps "ใช้บัญชียูทูปชั่วคราว".
- **Every row above becomes `duration: Infinity`** (D1). The ones that already have it (failed job, ffmpeg install, capture with account) are unchanged.
- **Layering:** `lib/jobs.ts` will import `showErrorToast` from `components/error-report/`. This is the first `lib → components` import; it is accepted because the toast needs JSX. Keep `lib/report.ts` free of React so it stays node-testable.
**Small action toasts (Pete, spec Q5 = the alternative, 2026-10-12).** These toasts today show a fixed local string and drop the error object. They get the copy button too, through `showErrorToast`:
- each keeps its current text;
- each catches the dropped error (`catch (error)` / `onError: (error) => …`) and passes it to `reportRequest`, so the server code and detail reach the report;
- each uses `duration: Infinity` and the stable id below.

| Toast (current text) | File:line | `context` | toast `id` |
|---|---|---|---|
| Cancel / retry a job failed (`th.queue.actionFailed`) | `components/queue/use-queue.ts:249` (`runJobAction`, add `catch (error)`) | `queue-action` + `jobId` | `queue-action-<id>` |
| Reorder failed (`th.queue.actionFailed`) | `components/queue/use-queue.ts:276` (`useReorder`, add `catch (error)`) | `queue-reorder` | `queue-reorder` |
| Resume the paused queue failed (`th.queue.actionFailed`) | `components/queue/pause-alert.tsx:37` | `queue-resume` | `queue-resume` |
| Delete the temporary account failed (`th.queue.actionFailed`) | `components/account/use-account.ts:34` | `account-delete` | `account-delete` |
| Open the output folder failed (`th.queue.fileMissing` for 404 / `th.queue.revealFailed`) | `components/queue/use-queue.ts:162` (`revealWithToast`) | `queue-reveal` + `jobId` | `queue-reveal-<id>` |
| Save the SponsorBlock default failed (`th.general.saveFailed`) | `pages/video/advanced/use-advanced-choice.ts:122` (use the `_error` argument) | `advanced-save` | `advanced-save` |

The account-delete report contains only the status line, like every report (C4).

**Still excluded:** toasts that come from no server request:
- the copy-failure toasts (`job-row.tsx:98`, removed by §1.4; `capture-strip.tsx:64`; `clip-details.tsx:32`; `frames.tsx:67`, `:76`; `subs/export-buttons.tsx:40`);
- the local validation toast at `pages/video/player/range-mark-buttons.tsx:21`;
- the report's own failure toast (`CopyReportButton`), so a failed report never offers another report.

### 1.4 Queue FailedRow (`components/queue/job-row.tsx:93-151`)
- **Replace** the "คัดลอกรายละเอียด" button (`:146-149`) and delete `copyDetails` (`:93-100`). In their place: `CopyReportButton` with `{ jobId: job.id, code, detail, context: "queue" }`. The server prefers the job store; `code`/`detail` are the fallback if the job is gone.
- Keep the "ดูรายละเอียด" collapsible, the code line and the `<pre>`. The row moves to `ErrorDetails` (with `jobId`) so the markup is shared. It must keep the `data-details-trigger=""` attribute and the controlled `open` state that the toast's "ดูรายละเอียด" uses to force it open (`:104-111`). Add `open` / `onOpenChange` props to `ErrorDetails`.
- Remove `th.queue.copyDetails` from `th.ts:499`. No other user (checked with grep).
- `web/e2e/queue-flow.spec.ts:195-203` keeps passing: the "ดูรายละเอียด" button and "รหัส E_YT_REFUSED" text stay.

### 1.5 ErrorPanel after a crash (`components/error-panel.tsx`)
- Keep the title, the message (`th.errors.chunk` / `th.errors.crash`) and the reload button.
- Add `CopyReportButton` in `AlertAction`, before the reload button. The request is `reportRequest(error, { context: isChunkLoadError(error) ? "chunk" : "crash" })`. This gives `E_UNKNOWN` plus `name: message` and up to 10 stack lines.
- **Toaster after a route error:** `RouteError` (`components/route-error.tsx`) replaces `Layout`, and `Layout` is where `<Toaster>` lives (`components/layout.tsx:102`). `RouteError` must therefore render its own `<Toaster position="bottom-right" />`, or "คัดลอกแล้ว" would not show. `PageErrorBoundary` renders inside `Layout`, so it needs nothing.
- The report still builds after a crash. The browser only needs `api()` and the token `<meta>`, which survive a React crash. The server builds everything else.

### 1.6 Health page (`pages/settings/health-panel.tsx:166-175`)
- In the bottom action row, put `CopyReportButton` (`variant="outline"`, default size, matching the row) **right after** "ตรวจอีกครั้ง" (`th.health.recheck`; the decisions call it "ตรวจใหม่", but the real label is "ตรวจอีกครั้ง") and before "ปิดโปรแกรม".
- The request is `{ context: "health" }`, so the report has no error section (D4).
- The button shows while the health data is loaded. The health-load-error box has its own `ErrorDetails` (R2).

### 1.7 Layout, keyboard and a11y
- **Width:** at 640 px nothing scrolls sideways. The `<pre>` uses `break-all whitespace-pre-wrap` and the button rows use `flex-wrap`. Inside a toast (~356 px) the button wraps under the description.
- **Keyboard:** the trigger and the button are normal buttons in tab order. Sonner's toast region is reachable with its hotkey (Alt+T) as today.
- **Feedback:** "คัดลอกแล้ว" is a sonner toast, which is already a polite live region.
- **Contrast:** axe in light and dark on an expanded section inside a destructive `Alert` and inside a toast (§6.4).

## 2. Backend

### 2.1 API: `POST /api/diagnostics` (`src/yttoolkit/api/diagnostics.py`, new)

**Shape decision.** The PRD named `GET /api/diagnostics?jobId=`. This spec uses **`POST /api/diagnostics` with a JSON body** instead:
1. **Non-job errors must send code + detail from the web (D4).** Detail is raw technical text up to 4,000 characters and may hold paths or messages. A query string would put it in the URL, browser history and any tool that logs URLs. A body keeps it out of URLs.
2. **The token protects it.** `LocalOnlyMiddleware` checks `X-Toolkit-Token` + Origin only on non-GET methods (C10). The report carries the log tail, the most sensitive thing the app can return, so it must be behind the token.
3. **One endpoint for every case:** job, non-job and health.

**Router:** `build_diagnostics_router(ctx)` is included unconditionally in `create_app` (`app.py:85` area). It reads `ctx.queue` (job store), `ctx.db` (titles), `ctx.accounts`; each may be `None`.

**Body:** a JSON object. Every key is optional; any other key is rejected:

| Key | Rule |
|---|---|
| `jobId` | string, `^[A-Za-z0-9_-]{1,64}$` |
| `code` | string, `^E_[A-Z0-9_]{1,40}$` (covers `E_HTTP_502`, `E_OFFLINE`) |
| `detail` | string, ≤ 4,000 characters |
| `context` | string, `^[a-z][a-z0-9-]{0,31}$` |
| `videoId` | string, `^[A-Za-z0-9_-]{11}$` |

**Validation:**
- Validate by hand, like `api/account.py:36-39`, not with a pydantic model, so a rejected value is never echoed back.
- A body that is not an object, has an unknown key, a wrong type, a pattern mismatch or a too-long `detail` → **422 `E_BAD_REQUEST`** with `BAD_REQUEST_MESSAGE` and a fixed English detail naming the field and the rule only (for example `"detail longer than 4000 characters"`). It never names the value.
- An empty body `{}` is valid (the health report).
- There is no separate byte cap. The field caps bound the body, and `jobId` / `code` / `context` / `videoId` are tiny.

**Error section source:**
1. `jobId` given and `ctx.queue.store.get(jobId)` finds the job → the section comes from the job (code, kind, video id, detail). Body `code`/`detail` are ignored.
2. Otherwise, if any of `code` / `detail` / `jobId` is given → the section comes from the body (`jobId` without a match: use the body `code`/`detail`; nothing at all → code `ไม่มี`).
3. Otherwise → no error section (health, D4).

It never answers 404 for an unknown job: the copy button must always produce a report.

**Response:** `200 {"report": "<markdown>"}` with `Cache-Control: no-store`.

**Logging:** after building, log `INFO diagnostics code=<code|-> context=<context|-> job=<jobId|->`. The values are already validated tokens. Never log `detail`. The log tail is read **before** this line is written.

**PRD update** (done in this commit, §7.1): the button paragraph now says `POST /api/diagnostics` and describes the body and the rules above. AC-SET-04 now reads "`POST /api/diagnostics` ที่มี `jobId`". The plan's docs task also adds this row to the PRD §6.2 API table:

| POST | `/diagnostics` | `{jobId?, code?, detail?, context?, videoId?}` (detail ≤ 4,000) | `{report}` Markdown ตามแม่แบบใน §7.1 · token เหมือนคำขออื่นที่ไม่ใช่ GET · ช่องผิดรูป = 422 `E_BAD_REQUEST` |

### 2.2 Report builder (`src/yttoolkit/core/diagnostics.py`, new)

One module, pure apart from reading the log files. It does not import FastAPI, `yt_dlp` or `extractor`.

**Inputs:**

```python
@dataclass(frozen=True)
class ErrorSection:
    code: str | None          # None → "ไม่มี"
    detail: str | None
    kind: str | None = None   # job kind ("video", "audio", ...) for job errors
    video_id: str | None = None
    context: str | None = None  # non-job errors only

@dataclass(frozen=True)
class ReportInputs:
    now: datetime             # aware local time (api passes datetime.now().astimezone(); tests inject)
    version: str              # ctx.version
    commit: str | None        # ctx.commit (git short sha) or None
    os_version: str           # ctx.plat.os_version()
    ytdlp: ToolStatus         # tools.ytdlp_status(lookup_latest=False)  — no PyPI call
    ffmpeg: ToolStatus        # tools.ffmpeg_status(paths, plat)
    js_runtime: ToolStatus    # tools.find_js_runtime(plat)
    account_active: bool      # ctx.accounts.status()["active"]; False when ctx.accounts is None
    error: ErrorSection | None
    log_dir: Path             # ctx.paths.logs
    token: str                # ctx.token, only to mask it
    titles: tuple[str, ...]   # job.title and videos.title for the video id (see below)

def build_report(inputs: ReportInputs) -> str: ...
```

- **`titles`:** the API collects them. They are `job.title` (when a job was found) and `SELECT title FROM videos WHERE video_id = ?` for the job's or the body's `videoId` (when `ctx.db` exists). Empty titles are dropped.
- **No network:** the builder never calls `collect_health`, whose network check takes up to 5 s. The report needs no network.

**Exact output.** It matches the PRD §7.1 template line by line. `{…}` are values; every line ends in LF:

```
## รายงานปัญหา YT Toolkit
- เวลา: {YYYY-MM-DD HH:MM} ({±HH:MM})
- แอพ: {version} (commit {commit|ไม่มี}) · ระบบ: {os_version}
- yt-dlp: {ytdlp.version|ไม่มี} · ffmpeg: {ffmpeg.version|ไม่มี} · JS runtime: {js|ไม่มี}
- บัญชียูทูป: {ไม่ได้ใช้บัญชี|ใช้บัญชีชั่วคราวอยู่}
### error
- รหัส: {code|ไม่มี} · งาน: {kind} (videoId {video_id})
- รายละเอียด: {detail|ไม่มี}
### log ล่าสุด (50 บรรทัด)
```text
{log lines | ไม่มี}
```
```

**Field rules:**
- **Time:**
  - `now.strftime("%Y-%m-%d %H:%M")`, then a space, then the offset in brackets;
  - the offset is `now.strftime("%z")` (`+0700`) with a colon inserted (`+07:00`);
  - a naive `now` is a programming error (assert).
- **Commit:** `None` → `commit ไม่มี`.
- **Tool versions:**
  - **yt-dlp:** `ytdlp.version` or `ไม่มี`;
  - **ffmpeg:** `ffmpeg.version` only when `ffmpeg.status == "ok"`, else `ไม่มี` (missing, broken or still installing);
  - **JS runtime:** `"{name} {version}"` when `js_runtime.name` is set (`deno 2.9.7`, or `node 22.11.0` for the node fallback), else `ไม่มี`.
- **Account line:** only the two PRD phrases. Never the import time, names or values (AC-SET-06).
- **Error section** (omitted entirely, heading included, when `error is None`):
  - **Job error:** `- รหัส: {code} · งาน: {kind} (videoId {video_id})`, exactly the template.
  - **Non-job error:** `- รหัส: {code}`, then ` · หน้าจอ: {context}` when there is a context, then ` (videoId {id})` when there is a video id. The context is the raw ASCII tag from §1.3, after the Thai label `หน้าจอ: ` (Pete, spec Q1). Example: `- รหัส: E_NETWORK · หน้าจอ: video-header (videoId dQw4w9WgXcQ)`.
  - **Detail:** `- รายละเอียด: ` + detail. Collapse `\r\n` to `\n`. A multi-line detail puts its first line after the label and every further line on its own line indented by two spaces (a Markdown list continuation). Empty or `None` → `ไม่มี`.
- **Log heading:** always `### log ล่าสุด (50 บรรทัด)`, even when fewer lines exist (the template's fixed title).
- **Code fence:** ```` ```text ```` … ```` ``` ````. If any log line contains a run of backticks of length ≥ 3, use a fence one backtick longer than the longest run, so a line can never close the block early.

**Log tail (`_tail_lines(log_dir, want=50) -> list[str]`):**
- **Files:** newest first: `app.log`, `app.log.1`, `app.log.2` (D7: three files, §3.1). An older `app.log.3` left by an earlier version is ignored.
- **Per file:** open in binary and seek to `max(0, size - 64 KiB)`. Read to the end. Decode with `utf-8`, `errors="replace"`. If the seek offset was > 0, drop the first, partial, line. Split with `splitlines()` (this also strips `\r`).
- **Order:** take lines from the end of `app.log` backwards. Move to the next older file only when the current file was read **whole** (`size ≤ 64 KiB`) and still gave fewer than 50 lines. This way the tail never has a gap. Return oldest-first.
- **Missing or unreadable files:**
  - a missing file is skipped;
  - `OSError` on open or read → skip that file, plus one `DEBUG` log;
  - no lines at all → the single line `ไม่มี` inside the fence.
- **Rotation race (Windows):** while reading, hold the lock of the root `RotatingFileHandler` whose `baseFilename` is `log_dir/app.log`, found by walking `logging.getLogger().handlers`. `handler.acquire()` / `release()` is the same lock `emit` → `doRollover` takes. On Windows, a rename while our read handle is open would fail. No handler found (tests) → read without a lock.

**Length caps.** Applied after redaction (§2.3), so a cut never splits a home path and leaks half a username:
- `DETAIL_MAX = 2000` characters for the detail. A cut ends with `…`.
- `LOG_LINE_MAX = 300` characters per log line. A cut ends with `…`.
- `REPORT_MAX = 8000` characters for the whole report. If it is longer, drop the **oldest** log lines one at a time until it fits. The heading keeps saying "50 บรรทัด". If even zero log lines don't fit (an impossible detail), cut the detail further. 8,000 leaves room under common chat limits; see Review Focus 1.

**Assembly order** (the only order allowed):
1. collect the raw parts: header values, error lines, log lines;
2. `redact_report` on every part (§2.3);
3. apply the caps;
4. join with `\n` and end with a trailing `\n`.

### 2.3 Redaction (`src/yttoolkit/redact.py`, extended)

Reuse the existing functions. Add small, stdlib-only helpers so `redact.py` keeps loading before the web stack (`tests/unit/test_redact.py:242`).

- **`redact_home` (extended, benefits every caller):** besides the existing forms (as-is, `/`, doubled `\`, 8.3 aliases, any case), also match the **percent-encoded** forms of each, `urllib.parse.quote(form, safe="")` and `quote(form.replace("\\", "/"), safe="/")`. These cover `file:///C:/Users/...` and URL-encoded paths in yt-dlp messages. The sibling-folder guard (`(?![\w.\-])`) is unchanged.
- **`mask_user_paths(text) -> str` (new):** replaces absolute paths that are **not** under home (home is already `~` by then) with `<path>`:
  - **What counts as a path:** a drive path `[A-Za-z]:[\\/]…` or a UNC path `\\server\share…`.
  - **Extent:** if the path starts right after a `'` or `"`, it runs to the matching closing quote, which covers `OSError` reprs whose paths contain spaces. Otherwise it runs to the next whitespace or one of `'"<>|,;)`.
  - **Exemption:** lines that match `^\s*File ".*", line \d+` (traceback frames, C4) are left alone.
- **`scrub_titles(text, titles) -> str` (new):** replaces, case-sensitively, each title with `<title>`. Then it does the same for `files.safe_component(title, "")`. The import is lazy; `files` is stdlib-only.
  - **Truncated file names:** if the safe name is ≥ 16 characters, any run that starts with its first 16 characters, up to the next `\`, `/`, `'`, `"`, line break or the end, becomes `<title>`. This catches file names that were cut short.
  - Titles shorter than 4 characters are skipped, because masking them would hit ordinary words.
- **`mask_media_urls(text) -> str` (new):** any `https?://` URL whose host ends with `googlevideo.com` becomes `<url>`. These are signed media links that carry the client IP, the same idea as `extractor._MEDIA_URL`.
- **`redact_log_detail(text, titles) -> str` (new):** `redact_home` → `redact_secrets` → `mask_user_paths` → `mask_media_urls` → `scrub_titles`. Used only by the job-failure log line (§3.2).
- **`redact_report(text, *, token, titles) -> str` (new):** `redact_log_detail(text, titles)` plus two more steps:
  - replace every occurrence of `token` with `<hidden>` (when the token is non-empty);
  - replace every whole-word sign-in cookie **name** from `SIGN_IN_COOKIE_NAMES` with `<hidden>`, where whole-word means not preceded or followed by `[A-Za-z0-9_-]`. After `redact_secrets`, `SAPISID=<hidden>` becomes `<hidden>=<hidden>`. The report has no cookie names at all (C4).

  Used only by `build_report` step 2.

What the report deliberately keeps: video ids, job ids, error codes, tool versions, app code paths in traceback frames, and `~\...` paths (the PRD example `~\Downloads`).

### 2.4 OS version (`Platform.os_version`)
- **`platform/base.py`:** add `def os_version(self) -> str: ...` to the `Platform` protocol, with the docstring "ชื่อและเลขรุ่นของระบบปฏิบัติการสำหรับรายงานแจ้งปัญหา".
- **`platform/windows.py`:**
  - read `v = sys.getwindowsversion()`;
  - name it `Windows 11` when `v.major == 10 and v.build >= 22000`, `Windows 10` when `v.major == 10`, otherwise `Windows {v.major}`;
  - return `f"{name} ({v.major}.{v.minor}.{v.build})"`, which gives `Windows 11 (10.0.26200)`, matching the PRD;
  - do not use `platform.release()`, because older Pythons report "10" on Windows 11;
  - any exception → `"Windows"`.
- **`platform/macos.py`:** `release = platform.mac_ver()[0]`; return `f"macOS {release}"` when set, else `"macOS"`. The import is the stdlib `platform` module (absolute import), not the package.
- **`tests/conftest.py` `FakePlatform`:** add the field `os_version_text: str = "Windows 11 (10.0.26200)"` and the method `os_version()` returning it.

### 2.5 Where the API gets each input
`api/diagnostics.py` assembles `ReportInputs`:
- `now`: `datetime.now().astimezone()`;
- `version` / `commit` / `token`: from `ctx`;
- `os_version`: `ctx.plat.os_version()`;
- the three tool statuses: from `core/tools.py`, with `ctx.paths` and `ctx.plat`;
- `account_active`: `ctx.accounts.status()["active"]` (status only);
- the job: `ctx.queue.store.get(job_id)` (`core/jobs.py:406`), which has `video_id`, `title`, `kind`, `error_code`, `error_detail`;
- the title row: from `ctx.db`;
- `log_dir`: `ctx.paths.logs`.

It runs as a sync endpoint (threadpool). The subprocess version checks take well under a second.

### 2.6 Health JS-runtime warning (D2)
- In `core/tools.py:124`, the "no runtime found" status keeps `status="warn"` and `name=None`. Its message changes from `ไม่พบตัวช่วยของ yt-dlp (deno)` to the PRD §7 text for `E_JS_RUNTIME_MISSING`: **`บางคุณภาพอาจไม่แสดง เพราะเครื่องยังไม่มีตัวช่วยที่ yt-dlp ต้องใช้`**.
- The health page already shows `tool.message` for that row (`health-panel.tsx:37-45`), so the web needs no change.
- The node fallback (`ใช้ node แทน deno`) is unchanged.
- Update `tests/unit/test_tools_status.py:118`.
- `E_JS_RUNTIME_MISSING` stays out of `yterrors.MESSAGES`: no job or API ever fails with it.

### 2.7 New `E_UNKNOWN` text (D3)
- `core/yterrors.py:50`: `"E_UNKNOWN": 'มีบางอย่างผิดพลาด กด "คัดลอกข้อมูลแจ้งปัญหา" แล้วส่งให้ผู้ดูแล'`.
- `api/errors.py:18`: `UNKNOWN_MESSAGE = MESSAGES["E_UNKNOWN"]` already follows it. No edit is needed, only a test.
- `web/src/i18n/th.ts:590`: `unknown: 'มีบางอย่างผิดพลาด กด "คัดลอกข้อมูลแจ้งปัญหา" แล้วส่งให้ผู้ดูแล'`.
- Tests that pin the old text: `tests/api/test_errors.py:63`, `tests/unit/test_yterrors.py:131`, `web/e2e/settings-general.spec.ts:233` (a mocked envelope; update it for consistency).
- **Not changed:** `start.bat:88`, `:95` ("ถ่ายภาพหน้าจอนี้ส่งให้ผู้ดูแล…"). That screen shows when the app failed to open, so there is no web page and no button. Pete confirmed it keeps its text (spec Q3).
- PRD §7 is updated in this commit.

## 3. Logging

### 3.1 File log (`probe.setup_file_log`, `probe.py:65-80`)
- Use `RotatingFileHandler(filename, maxBytes=5_000_000, backupCount=2, encoding="utf-8")`. That is **3 files**: `app.log`, `.1`, `.2`, at most 15 MB, matching PRD "หมุนไฟล์ที่ 5 MB เก็บ 3 ไฟล์" (Pete, spec Q4). Today it is 1 MB × (1 + 3).
- Add `logging.getLogger("httpx").setLevel(logging.WARNING)` in the same function, before the handler is created. It is set by name, so `probe` still does not import `httpx`, which `tests/unit/test_probe.py:30` asserts. This drops the per-request INFO lines that carry full thumbnail/image URLs.
- The format string and the redaction filters are unchanged.

### 3.2 Job failures (`core/queue.py`)
Today a `YtError` failure logs only `INFO งาน {id} ({kind}) จบด้วย {code}` (`:351`). An unexpected exception logs a traceback without a code (`:375`), and a spawn failure (`:316`) logs without a code. New rule: **one detailed line per failure, written in `_fail`** (`:406`), the single path every failure goes through:
- `_fail(job, ctx, code, message, detail, exc=None)` gains an `exc` parameter.
  - `_run_job` passes the caught exception: the `YtError` call at `:371`, the unexpected one at `:376`.
  - `_bot_check` passes its `exc` on its final-failure call (`:430`).
  - `JobCancelled` without a reason (`:362`) passes `None`.
- The line is:

  ```
  job_failed id=<job.id> kind=<job.kind> code=<code> detail=<detail>
  <traceback>
  ```

  - `detail` = `redact_log_detail(detail or "-", titles=(job.title,))`, cut to 2,000 characters, with line breaks escaped as `\n`.
  - `<traceback>` = `"".join(traceback.format_exception(exc))` run through `redact_log_detail` with the same titles. It is part of the message, not `exc_info`, so the title scrub also covers the exception text inside the traceback (an `OSError` naming the output file, for example). It is omitted when `exc is None`.
- **Level:**
  - `WARNING` for a `YtError` failure;
  - `ERROR` for `E_UNKNOWN` from an unexpected exception;
  - `WARNING` with no traceback for `exc is None`.
- **Remove** the separate `log.exception` at `:375`, so a crash is logged once, with its code.
- **Spawn failure** (`:316`): replace `log.exception("เริ่มงาน %s ไม่ได้", job.id)` with the same `job_failed` line (`code=E_UNKNOWN`, `ERROR`, traceback).
- The summary line at `:351` stays (it covers done/cancelled too).
- **AC-SET-03** is met by the `job_failed` line: time (from the formatter), code, job id, detail and traceback.

### 3.3 Non-job API errors (`api/errors.py`)
Add a pure ASGI middleware `ErrorLogMiddleware`. In `create_app` (`app.py:101`), add it **after** `LocalOnlyMiddleware`, so it is outermost and also sees the middleware's own 403/421.
- **Scope:** `http` requests whose path starts with `/api` only.
- **Watching the response:**
  - On `http.response.start`, note the status and `content-type`.
  - When the status is ≥ 400 and the type is `application/json`, parse the first `http.response.body` chunk (≤ 64 KiB) as JSON and read `error.code`, or `?` when it can't be read.
  - Messages are passed through untouched and never held back.
- **The line:** `api_error method=<METHOD> path=<scope["path"]> status=<n> code=<code>`. The query string is never logged, nor the body, nor `detail`. The path has ids only (video ids, job ids).
- **Level:**
  - `DEBUG` for 404 (normal "not yet" answers such as `GET /videos/{id}/sharp`; DEBUG is not written, since root is INFO);
  - `WARNING` for ≥ 500;
  - `INFO` otherwise (400-499 except 404: for example 403, 409, 413, 422). A 502 such as `E_YT_REFUSED` counts as ≥ 500, so WARNING.
- **`_unhandled_error`** (`api/errors.py:55`) keeps its traceback line; add `code=E_UNKNOWN` to its message.
- Errors that never reach the server (`E_OFFLINE`, crashes) are logged when the user asks for a report (`diagnostics code=…`, §2.1).

### 3.4 Privacy rules for the new lines
- **Allowed fields:** ids, codes, kinds, status numbers, methods, API paths. `detail` and the traceback appear only in `job_failed`, and only through `redact_log_detail`.
- **Never logged:** `POST /api/diagnostics` bodies, `POST /cookies/import` bodies (unchanged rule), query strings.
- **Order safety:** `HomePathFilter` / `SecretFilter` still run on the file handler. Because `redact_log_detail` already redacted the text in the message, the `caplog`-based tests see clean text whatever the handler order.

## 4. Errors and edge cases

- **App closed when the button is pressed:** `api()` throws `E_OFFLINE`; the toast shows `th.errors.offline`. Nothing is copied.
- **Clipboard refused** (permission denied, document not focused): the toast shows `th.errors.copyFailed`. Nothing else changes: there is no manual-copy box (Pete, spec Q2).
- **Slow report** (ffmpeg / deno version checks on a slow PC): the `ClipboardItem` promise path keeps the user gesture. On the `writeText` fallback, a long wait may lose focus, and that case shows `copyFailed`.
- **Job deleted or unknown id:** the body's `code`/`detail` are used (§2.1), and a report is always produced.
- **Interrupted job** (`E_INTERRUPTED`): the same as a failed job. `FailedRow` already covers both.
- **Crash inside the copy button itself:** `CopyReportButton` has no data hooks. A crash on the page shows `ErrorPanel`, whose button builds a fresh request.
- **Fake mode** (`YT_TOOLKIT_FAKE=1`, e2e): ffmpeg lookup is off, so the report says `ffmpeg: ไม่มี`. The report is otherwise real.
- **Two tabs:** each builds its own report. Nothing is stored.
- **Log file missing** (first run, or a deleted folder): the log block says `ไม่มี`.
- **Report while a rotation is due:** the handler lock serialises it (§2.2).
- **Very long detail from the web** (a stack): the client cuts it to 4,000 characters, the server rejects anything longer with 422, and the report shows ≤ 2,000.

## 5. Docs to update (part of the plan)
- **PRD.md:**
  - §7 `E_UNKNOWN` row and §7.1 (API shape, button placement, AC-SET-04): **done in this commit**;
  - add the §6.2 table row from §2.1;
  - add FR-SET-5 traceability if §11 lacks it.
- **docs/acceptance.md:** add a "M6 รอบ B" section of manual Windows checks, written by the plan from the PRD AC text:
  - copy the report from a clip-page error and from a failed job, then paste it into LINE and Notepad;
  - check `~`, with no username and no clip title;
  - press the health-page button;
  - check the 640 px window.
- **docs/m1-followups.md:58** and **docs/m4-followups.md:40:** close the diagnostics items (done in M6 round B; the canary test now covers the report).
- **tests/integration/test_account_privacy.py** module docstring: drop "ยังไม่มีในแอพ (M6) จึงยังไม่ได้ตรวจ".

## 6. Testing

### 6.1 Python unit
- **`tests/unit/test_redact.py`:**
  - percent-encoded and `file:///` home forms;
  - `mask_user_paths` on a quoted `OSError` repr with spaces, on UNC paths, and on an unquoted path at the end of a line;
  - traceback frame lines are exempt;
  - `~\...` is kept;
  - `mask_media_urls` (googlevideo only);
  - `scrub_titles` on an exact title, on its `safe_component` form, on a truncated file name and on a title under 4 characters (kept);
  - `redact_report` drops cookie names (all of `SIGN_IN_COOKIE_NAMES`) and the token;
  - `redact.py` still does not load the web stack.
- **`tests/unit/test_diagnostics.py` (new), for the builder with fixed inputs:**
  - **Template:** the exact text for a job error (golden string), including `เวลา: 2026-10-05 14:32 (+07:00)` from an injected `now` in UTC+7.
  - **Placeholders:** `commit ไม่มี`; each tool missing → `ไม่มี`; the node fallback → `node <ver>`.
  - **Error section:** both account lines; the non-job line with and without context / videoId; no error section when `error=None`; multi-line detail indentation.
  - **Log tail:** across rotation (`app.log` 20 lines + `app.log.1` 40 → 30 + 20, in order); with no files → `ไม่มี`; invalid UTF-8 bytes → `�`; a partial first line dropped after the seek; a big `app.log` does not pull from `.1`; a backtick run in a line → a longer fence.
  - **Caps:** a long line cut at 300 with `…`; the report ≤ 8,000 with the oldest lines dropped first; caps applied after redaction (a home path at the cut point is still `~`).
- **`tests/unit/test_platform.py`:**
  - Windows: `os_version` for build 26200 → `Windows 11 (10.0.26200)`, build 19045 → `Windows 10 (10.0.19045)`, via a monkeypatched `sys.getwindowsversion` inside the windows module; an exception → `Windows`.
  - macOS: `mac_ver` set / empty.
  - A live Windows test asserts the prefix `Windows `.
- **`tests/unit/test_probe.py:109-110`:** `maxBytes == 5_000_000`, `backupCount == 2`; `logging.getLogger("httpx").level == WARNING`; `httpx` is still not imported.
- **`tests/unit/test_tools_status.py:118`:** the new PRD message.
- **`tests/unit/test_yterrors.py:131`:** the new `E_UNKNOWN` text.
- **`tests/unit/test_queue*.py` (AC-SET-03, log test):**
  - a `YtError` failure → exactly one `job_failed` record at WARNING with `id=`, `code=`, `detail=` and a `Traceback` in the message;
  - an unexpected exception → one ERROR record with `code=E_UNKNOWN` and no second traceback record;
  - a spawn failure → a `job_failed` line;
  - the bot-check second failure → a `job_failed` line;
  - a detail holding the job title and a tmp path → neither appears in `caplog.text`, and `<title>` / `<path>` or `~` do;
  - end to end: with `probe.setup_file_log(paths)`, the line is in `run/logs/app.log`.

### 6.2 Python API (`tests/api/test_diagnostics.py`, new) — AC-SET-04
- **Job report:** POST with the `jobId` of a failed job whose detail contains a fake home path (`Path.home` monkeypatched to `C:\Users\somchai`, as `test_errors.py` does), the job title and an output path on `D:\`. Check:
  - every PRD heading and line label appears, in order;
  - `~` is used, and `somchai`, the title, `D:\` and the token are absent;
  - `videoId <id>` and the code are present.
- **The other shapes:** a non-job body (code + detail + context + videoId); `{}` → no `### error`; an unknown `jobId` → falls back to the body code.
- **422:** an unknown key, `code` pattern, `jobId` pattern, `videoId` pattern, `context` pattern, `detail` over 4,000, a non-object body and a wrong type. Each answers 422 `E_BAD_REQUEST`, the response never contains the bad value, and a 422 still logs `api_error … code=E_BAD_REQUEST`.
- **Token:** no token or a wrong Origin → 403 `E_FORBIDDEN`. GET → 405 / not routed (no GET handler exists).
- **Headers and log:** `Cache-Control: no-store`; one `diagnostics code=… context=… job=…` INFO line and no detail in the log.
- **Error-log middleware:** a 409 `E_JOB_STATE` → an INFO `api_error` line with method, path and code; a 404 → no INFO line; the query string is never in the log; a 500 → a WARNING line plus the traceback line with `code=E_UNKNOWN`.

### 6.3 Privacy canary (`tests/integration/test_account_privacy.py`) — AC-SET-06 (M6)
Extend `test_canaries_never_leave_memory` (`:91`):
- after the failing signed-in job, POST `/api/diagnostics` with its `jobId`, and also once with `{code, detail, context}` and once with `{}`;
- `_assert_clean(report)` for each report;
- also assert that `SAPISID`, `__Secure-3PSID`, `LOGIN_INFO` and the canary *name* `cnry-name-a4f6e8` are not in any report;
- the account line reads `บัญชียูทูป: ใช้บัญชีชั่วคราวอยู่`, and nothing else in the report mentions the account;
- the existing file-walk and `app.log` checks run after these calls, so the new log lines are covered too.

### 6.4 Web
- **Vitest (node), `web/src/lib/report.test.ts`:**
  - `reportRequest` for `ApiError`, plain `Error` (10 stack lines max) and a non-error value;
  - the 4,000 cut;
  - `copyReport` with injected deps:
    - the `ClipboardItem` path writes `text/plain` with the report;
    - no `ClipboardItem` → the `writeText` fallback;
    - a fetch rejection (`ApiError`) → `{ ok: false, message: <server message> }`;
    - `E_OFFLINE` → `th.errors.offline`;
    - a clipboard rejection → `th.errors.copyFailed`;
    - no unhandled rejection in any case.
- **Vitest for the toast and details models:** keep the logic of `showErrorToast` / `ErrorDetails` in `components/error-report/model.ts`: build the request from `(error, where)`, the default-open rule for `E_UNKNOWN`, toast options with `duration: Infinity` and the given id. Test it there. Update `components/queue/use-queue.test.ts` for the failed-job toast options: copy button present, existing action/cancel unchanged.
- **Chromium e2e (new `web/e2e/error-report.spec.ts`, project `chromium`, no real jobs)** for AC-SET-05. Every test calls `context.grantPermissions(["clipboard-read", "clipboard-write"])` (as `clip-info.spec.ts:195`). The `/api/diagnostics` call goes to the real fake-mode backend; the failing calls are mocked with `page.route`.
  - **Clip page:**
    - mock `GET /api/videos/<id>` → 502 `E_YT_REFUSED` with a detail;
    - open `/v/<id>`, press "ดูรายละเอียด" and see `รหัส E_YT_REFUSED` and the detail;
    - press "คัดลอกข้อมูลแจ้งปัญหา" and see the toast "คัดลอกแล้ว";
    - `navigator.clipboard.readText()` starts with `## รายงานปัญหา YT Toolkit` and contains `- รหัส: E_YT_REFUSED · หน้าจอ: video-header (videoId <id>)` and `### log ล่าสุด (50 บรรทัด)`;
    - the request body has `code`, `detail`, `context` and `videoId`.
  - **`E_UNKNOWN` box:** the details are open on arrival and the button is visible without a click.
  - **Toast:**
    - mock `POST /api/jobs` → 500 `E_UNKNOWN` and press a download button;
    - the toast is still visible after 6 s (beyond sonner's 4 s default) and has the copy button;
    - pressing it gives "คัดลอกแล้ว", and the toast stays.
  - **Health page:** the button sits right after "ตรวจอีกครั้ง"; the clipboard text has no `### error`.
  - **Crash:**
    - abort the lazy video chunk route (as `home.spec.ts:639-659` does) so `ErrorPanel` shows;
    - the copy button works and the toast "คัดลอกแล้ว" appears (proves the Toaster after a crash);
    - the clipboard has `E_UNKNOWN` and `context` `chunk`.
  - **Failure paths:**
    - `addInitScript` makes `clipboard.write` / `writeText` reject → the toast "คัดลอกไม่สำเร็จ ลองอีกครั้ง";
    - mock `POST /api/diagnostics` → `route.abort()` → the toast shows `th.errors.offline`.
  - **Axe (`analyzeSettled` from `e2e/axe-settled.ts`):** light and dark on the expanded details in a W2 `LoadError`, on the health page with the new button, and on an error toast with the button.
  - **640 px:** `page.setViewportSize({ width: 640, height: 800 })` with an expanded details section holding a 300-character unbroken detail, then assert that `document.documentElement.scrollWidth <= 640`.
- **Queue project:** `queue-flow.spec.ts:195-203` keeps passing. Add one assertion there: the failed row has "คัดลอกข้อมูลแจ้งปัญหา" and no "คัดลอกรายละเอียด". That project already runs real fake jobs; no new queue spec is needed.

## 7. Thai copy (all sourced — nothing new)

| Where | Copy | Source |
|---|---|---|
| Copy button (everywhere) | คัดลอกข้อมูลแจ้งปัญหา | PRD §7.1, decisions D1 |
| Folded section trigger | ดูรายละเอียด | `th.queue.details` (moved to shared key) |
| Code line | รหัส {code} | `th.queue.errorCode` (moved to shared key) |
| Copied toast | คัดลอกแล้ว | PRD AC-SET-05, `th.video.copied` |
| Clipboard refused | คัดลอกไม่สำเร็จ ลองอีกครั้ง | `th.video.copyFailed` |
| Report fetch failed, app closed | เชื่อมต่อโปรแกรมไม่ได้ ถ้าปิดโปรแกรมไปแล้ว เปิดใหม่ด้วย start.bat | `th.errors.offline` |
| `E_UNKNOWN` | มีบางอย่างผิดพลาด กด "คัดลอกข้อมูลแจ้งปัญหา" แล้วส่งให้ผู้ดูแล | decisions D3 |
| Health, no JS runtime | บางคุณภาพอาจไม่แสดง เพราะเครื่องยังไม่มีตัวช่วยที่ yt-dlp ต้องใช้ | PRD §7 `E_JS_RUNTIME_MISSING` |
| Report labels | รายงานปัญหา YT Toolkit · เวลา · แอพ · ระบบ · บัญชียูทูป · รหัส · งาน · รายละเอียด · log ล่าสุด (50 บรรทัด) | PRD §7.1 template |
| Report label, non-job errors | หน้าจอ | Pete, spec Q1 (2026-10-12) |
| Report account line | ไม่ได้ใช้บัญชี / ใช้บัญชีชั่วคราวอยู่ | PRD §7.1 |
| Report placeholder | ไม่มี | decisions (Section 2) |

**`th.ts` changes:**
- add `errors.copyReport`, `errors.details`, `errors.code`, `errors.copied`, `errors.copyFailed`, with the values above;
- change `errors.unknown`;
- remove `queue.copyDetails`.

`queue.details` / `queue.errorCode` stay: the toast's "ดูรายละเอียด" action still uses `queue.details`.

Copy rules: buttons start with a verb; no "กรุณา"; no "!".

## 8. Review focus (top 5 failure modes the tests may miss)

1. **The report is too long for chat.** The caps are 8,000 / 300 / 2,000. LINE, Teams or a browser AI may truncate or reject at their own limits. The two-space continuation lines and the nested fence must render properly once pasted. Check by pasting a real worst-case report (a long traceback plus 50 long lines) into the chat Pete's staff actually use, and into Notepad.
2. **The home path in a form the regex misses:**
   - a redirected or OneDrive profile;
   - a home on another drive;
   - `\\?\C:\Users\…`;
   - JSON-escaped twice;
   - lowercase drive letters with forward slashes inside a URL;
   - the bare username on its own (e.g. `user somchai` inside a yt-dlp or Windows message), which no rule masks;
   - a username that is also a common word.

   Grep a real report from Pete's machine for his username.
3. **Persistent toasts pile up.** Now every error toast is `Infinity`. A flaky network on the W2 page could raise `video-refresh`, `capture-error` and `frames-download` toasts together, and a batch of 20 failing jobs gives 20 `job-<id>` toasts. Sonner shows 3 and keeps the rest stacked. Check:
   - stable ids really replace (same id → same toast);
   - "ปิดโปรแกรม" still clears them all (`toast.dismiss()`);
   - the stack does not cover the queue bar at 640 px.
4. **A clip title leaks through a path or a chained exception.**
   - Titles reach file names after `safe_component` + `truncate_title`.
   - A chapter-split job names its sub-folder after the title, and the chapter files after chapter titles.
   - A batch may write a playlist title.
   - The `scrub_titles` input is only `job.title` and the videos row, so chapter names and playlist titles are not covered.
   - Check `job_failed` lines and reports for split-chapter and batch jobs that fail at the write step (`E_OUTPUT_NOT_WRITABLE` / `E_DISK_FULL` with an `OSError` cause).
5. **Log rotation vs the tail reader on Windows.** `doRollover` renames `app.log` while the reader might hold it open. Python's `open()` on Windows does not share delete/rename, so the rename fails and the record is lost (`handleError` prints to stderr). The design takes the handler lock while reading; check that it is the same lock, that `serve` mode's console handlers don't matter, and that a report during heavy logging (a running batch) neither blocks a worker thread for long nor deadlocks (the builder never logs while holding the lock: the `diagnostics` line comes after).

## 9. Spec questions (all answered by Pete, 2026-10-12)

These are the spec's own questions, separate from the decision-file Q1-Q3 above. All five are answered and are folded into the sections shown.

| # | Question | Answer | Where |
|---|---|---|---|
| Spec Q1 | Label for non-job errors in the report | The Thai label: `- รหัส: E_NETWORK · หน้าจอ: video-header (videoId dQw4w9WgXcQ)` | §2.2, §6.4, §7, PRD §7.1 |
| Spec Q2 | Manual copy when the clipboard is blocked | No manual box. Only the toast "คัดลอกไม่สำเร็จ ลองอีกครั้ง", which already exists in `th.ts` (`video.copyFailed` at `th.ts:124`, `frames.copyFailed` at `:175`, `subs.copyFailed` at `:309`) | §1.2, §4 |
| Spec Q3 | `start.bat` failure screen | It keeps its current text ("ถ่ายภาพหน้าจอนี้ส่งให้ผู้ดูแล…") | §2.7 |
| Spec Q4 | How many log files | 3 files in total: `backupCount=2`, 15 MB at most | §3.1 |
| Spec Q5 | Small action toasts | They get the copy button, keep their text, pass the dropped error, and use `duration: Infinity` + a stable id | §1.3 |

## Out of scope (round B)
- `E_SETTINGS_INVALID` and settings import/export (round A).
- A corrupt on-disk `settings.json` (not in the PRD).
- Field-level messages: the output-folder field and the cookies-dialog import error.
- Removing absolute paths from API error `detail` in general. API `detail` keeps today's home redaction; only logs and the report get the stronger path masking.
- A "send the report" button, an upload, or any network use by the report.
- Phone layouts (C9).
- macOS `.command` launchers (M7). `MacPlatform.os_version` is only a stub so the protocol is complete.
