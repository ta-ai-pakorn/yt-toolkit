# M5 round C บัญชียูทูปชั่วคราว (temporary YouTube account) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Tasks inside one wave run as parallel subagents, each in its own controller-created git worktree (see "Waves" and "Lane rules"). Every task is reviewed by a reviewer subagent before its wave closes.

**Goal:** When a clip page (W2), a queued job or a sharp capture fails with `E_AGE_RESTRICTED` / `E_VIDEO_PRIVATE` (members-only included), staff press "ใช้บัญชียูทูปชั่วคราว", import a `cookies.txt` exported from a Chrome incognito window with a backup Google account, and the app retries the same thing signed in; the sign-in lives in memory only and is deleted by itself (2 h after import, at app shutdown, or 10 min after the queue goes idle following a job that used it), after which every tab tells the user to sign out in the incognito window.

**Spec:** `docs/superpowers/specs/2026-10-06-m5c-temporary-youtube-account-design.md` (binding: owner decisions C1-C9, Thai copy §7 used verbatim). Research record: `docs/m5c-prep.md`.

**Out of scope (round C):** Firefox or Chrome direct cookie reading, keeping the sign-in across restarts, a "test the sign-in" button, using the account against bot checks, other sites' sign-ins, naming a cookies.txt extension in the app, the diagnostics report (`/api/diagnostics`, M6).

**Architecture:**
- **Error copy (`core/yterrors.py`).** New spec §7 copy for `E_AGE_RESTRICTED` / `E_VIDEO_PRIVATE`, new `E_COOKIES_INVALID`; members-only phrases map to `E_VIDEO_PRIVATE`; `ACCOUNT_CODES` and `YtError(..., account_tried=True)` switch the message to the "tried with the account" copy while keeping the code and HTTP status.
- **Log redaction from process start (`yttoolkit/redact.py`, new, stdlib only).** `redact_secrets` masks `Cookie:`/`Set-Cookie:` header values and values of known Google sign-in cookie names; `SecretFilter` + the moved `HomePathFilter` are attached when `probe.setup_file_log` creates the `app.log` handler (before `lifecycle` is imported) and to the `serve` console handlers.
- **Account service (`core/account_session.py`, new, no `yt_dlp`).** One held jar in memory behind one lock; `import_text` / `clear(reason)` / `status()` / `jar()` / `mark_used(job_id)`; 2 h expiry and the 10 min queue-idle grace run on an injectable scheduler/clock; every state change is published as SSE `account` `{active, expiresAt?, reason?}`. `QueueRunner` gets a `listener` (`job_queued()` / `job_ended(job_id)`, called outside the queue lock).
- **Extractor account mode (`core/extractor.py` + `core/account_scope.py`).** `parse_account_cookies(text)` pre-validates lines (never echoing them), keeps youtube.com/google.com only, requires a `.youtube.com` sign-in cookie and loads a `YoutubeDLCookieJar` from `io.StringIO`. A `ContextVar` scope (`signed_in(jar)` / `current_jar()`) makes every visitor-session call site pass `with_account=current_jar()` to `_ydl`, which injects the jar like `_attach_session`, drops `cookiefile`, no-ops `save_cookies` and refuses traffic-printing options. `FakeExtractor` honours `needsAccount` in `behaviors.json`.
- **Retry rule (`with_account_retry`).** One helper wraps the three call sites (W2 `GET /videos/{id}`, each queue job handler as a whole, `CaptureService.capture` as a whole): anonymous first; on an account code with a held jar, run the whole call once more inside `signed_in(jar)`; the signed-in failure is re-raised `from None` with a neutral detail and `account_tried`. Signed-in probes stay in `VideoService` memory (never the DB, never "ล่าสุด") until the account is cleared or replaced.
- **API:** `GET /cookies`, `POST /cookies/import` (`{text, acceptWarning: true}`; 409 / 413 / 422), `DELETE /cookies`; `/health` gains `account: {status: "ok", active, importedAt}`; the `cookies` setting is retired (old rows ignored, dropped on the next save).
- **Web:** strings, types and `lib/account.ts` (pure helpers + react-query `["account"]` kept fresh by SSE); one app-wide dialog (store + reducer), a banner under the header, a non-dismissing "removed" toast on every `account` removal event; buttons on the W2 load error, the failed-job row and toast, and the capture toast; Settings › ขั้นสูง tab and a health row.

**Tech Stack:** unchanged (Python 3.13 + uv, FastAPI, pydantic v2, yt-dlp 2026.08.19 as a library, React ^19.2 + Vite + Tailwind v4 + shadcn/Base UI + react-query 5 + sonner, Vitest 5 (node), Playwright + axe). No new Python or npm dependency.

---

## Open questions for the owner (Pete)

Each is kept to one constant/string so the answer is a one-line change after the round; the plan ships the default shown.

- **Q1 — banner countdown wording.** Spec §6/§7 say "ลบอัตโนมัติภายใน HH:MM"; the plan renders the **time remaining** ("02:00" right after import = in 2 hours), which a reader may take for a clock time ("at 02:00"). The alternative is the clock time of deletion ("17:05"). One-line switch: `DELETE_TIME_STYLE` in `web/src/lib/account.ts` (`"remaining"` → `"clock"`), used by the banner and the Settings › ขั้นสูง status (T5, T8, T11). If Pete picks "clock", the e2e literals `02:00` in `account.spec.ts` / `settings-advanced.spec.ts` change with it.
- **Q2 — file picker label.** Spec §7 has no Thai label for the file input; its accessible name is `cookies.txt` (`th.account.fileLabel`, T5). A Thai label from Pete replaces that one string (e2e `getByLabel("cookies.txt")` follows).

**Owner inputs needed before the network run (T13 writes the test; nobody runs it without approval):** Pete's approval, one short age-restricted clip ID for `tests/network_videos.toml` `[account] age_restricted`, and the path of a `cookies.txt` exported from **his own backup account** in env `YT_TOOLKIT_TEST_COOKIES` (never copied into the repo). The run downloads one small audio file (about 1-5 MB) to a pytest temp folder; afterwards Pete signs out in the incognito window and deletes the file.

## Planner rulings (controller decisions baked into this plan)

- **R1 — account-probed clip info lives in memory until the account is cleared or replaced** (never on disk). Refines spec §2.4 "kept in memory for the job only / a reload re-probes": W2 tabs, queue handlers and captures reuse the signed-in copy instead of re-probing, and `AccountService.clear`/re-import calls `VideoService.forget_signed_in()` (C6, T6, T9).
- **R2 — on the clip page only clip info, queue jobs and capture retry with the account** (spec §2.4 list). The tabs' own fetches (subtitle files, frame images, pinned comment) stay anonymous.
- **R3 — no `/api/diagnostics` exists yet (M6).** The canary test covers `app.log` + captured log records, SSE, every API body, `/health`, `GET /cookies` and a walk of the data root and temp root (T9); `docs/m4-followups.md` records that the report must join the same test in M6 (T13).
- **R4 — members-only fixtures are synthesized** from YouTube's reason text as yt-dlp passes it through `raise_no_formats` in `extractor/youtube/_video.py` (no members-only clip to probe); the fixture README says so (T1).
- **R5 — failed-job toast:** "ใช้บัญชียูทูปชั่วคราว" becomes the primary (sonner `action`) button and "ดูรายละเอียด" the secondary (`cancel`) button; the post-delete toast reuses the existing "ปิด" (`th.common.close`) as its action (T8, T10).
- **R6 — clips opened only with the account are not written to history / "ล่าสุด"** (no `videos` row; consequence of R1).
- **R7 — fix the pre-existing failure `web/e2e/queue-flow.spec.ts:297`** ("แถบตั้ง --dock-bottom-offset … axe ทั้งสองธีมตอนชีตเปิด"). Cause (measured on the prototype): while `SLOWDOWNLD1` runs, every progress event restarts the `width` CSS transition of the queue bar's progress line (`data-testid="queue-bar-progress"`, `transition-[width] duration-300`), so `settleAnimations` in `web/e2e/axe-settled.ts` (added in `ca6103b`) never sees zero running animations. Fix without loosening axe: the helper ignores only **`width` transitions** of the documented `KEEPS_ANIMATING` selector (`[data-testid="queue-bar-progress"], [data-slot="progress-indicator"]`); every other transition on those elements (colours on a theme switch) is still awaited and axe still scans the whole page with no rule or node excluded. Folded into T5 (only owner of `axe-settled.ts`); verified at gate 1 with `queue-flow.spec.ts` + two other axe specs (prototype: queue-flow 8/8, settings-general + nav + account 41/41, queue-batch + queue-account 11/11).

### Planner decisions (not owner questions; Pete can still object)
- **Scope by `contextvars`, not by threading a parameter.** `signed_in(jar)` around a whole call makes every `_ydl` inside it (probe, `_extract_for_download`, `_download_media`, subtitle fetch, `fetch_frame_piece`) use the same account, so format URLs match (spec §2.4 "the whole job stays signed in"); each queue job runs in its own thread, so concurrent jobs never share the scope. Playlist extraction never uses the account.
- **The retry wraps the whole unit:** the queue handler (`build_handlers.bind`), `CaptureService.capture`, and the W2 `GET /videos/{id}` route. A nested `with_account_retry` inside an open scope calls straight through (no double retry).
- **Interactive use marks `mark_used(None)`**, queue jobs `mark_used(job.id)`; only the latter can start the grace (spec §2.2).
- **The parser pre-validates every non-comment line** (7 tab-separated fields, numeric expiry) and raises `E_COOKIES_INVALID` with `line N: …` only: yt-dlp's `YoutubeDLCookieJar.load` writes bad lines to stderr and `http.cookiejar` echoes them in `LoadError`. A domain flag that disagrees with the leading dot is fixed (some extensions write it wrong); `#HttpOnly_` lines are cookies.
- **`POST /cookies/import` checks the body by hand** (pydantic validation errors echo the submitted value); the size cap is checked before parsing; 413 answers `E_COOKIES_INVALID` with the standard copy.
- **`status()` = `{active:false, used:false}` or `{active:true, importedAt, expiresAt, used}`**; `expiresAt` is the earliest deadline (2 h or a running grace). SSE `account` carries `{active, expiresAt}` on import/grace changes and `{active:false, reason}` on removal; never cookie names or values.
- **`api/videos.py` reads the service with `getattr(ctx, "accounts", None)`** at call time, so T6 does not depend on T7's `AppContext.accounts` field (same wave).
- **Grace override for e2e:** env `YT_TOOLKIT_ACCOUNT_GRACE_S` is honoured only in fake mode and only for `0 < value ≤ 600` (`account_grace_s`, T9); `playwright.config.ts` sets `"5"` (T12).
- **Shutdown order:** `clear("shutdown")` runs after the queue stops and before `app.shutdown` is published, so open tabs get the removal toast first.
- **Web state:** `["account"]` query (`staleTime: Infinity`, 404 from an older backend = inactive) is patched by SSE; an `active:true` event for an account this tab has no `importedAt` for triggers a refetch; reconnect reloads it. The banner countdown ticks every 15 s, rounds minutes up and never shows more than the 2 h left at import (`importedAt` clamps a slow page clock); its number is `aria-live="off"`.
- **One removed-toast id** (`account-removed`) so the local delete and the SSE event that follows do not stack two toasts.
- **Buttons:** on the W2 load error the account button is the primary (`default` variant); there is no "ลองใหม่" next to it because `canRetry` (`pages/video/errors.ts` `FINAL_CODES`) already hides it for these two codes; in the failed-job row it is an `outline` `sm` button; after import the row calls the existing retry mutation, the toast calls `retryJob` directly.
- **Retired setting:** `cookies` leaves the defaults and `READ_ONLY`; `RETIRED_KEYS = ("cookies",)` rows are skipped on read and deleted inside the next `patch` transaction.

---


## Waves

Integration branch: `m5c-temp-account` (already checked out in the main checkout; based on `main` `4b02feb`; the spec is commit `e868ac6`, this plan the next commit).

| Wave | Lanes (one worktree each, file sets disjoint) | Depends on |
|---|---|---|
| 1 | T1 error copy + members-only rule + PRD §7 rows · T2 log redaction from process start · T3 account service + queue listener · T4 extractor account mode + parser + fake clips · T5 web strings/types/data layer/SSE + R7 axe-settle fix | spec |
| 2 | T6 retry rule at every call site + signed-in probes in memory · T7 `/cookies` API + health row + retire the `cookies` setting · T8 web dialog, banner, store, removed toast | gate 1 (T6←T1,T4 · T7←T1,T3,T4 · T8←T5) |
| 3 | T9 lifecycle wiring + privacy canary · T10 buttons on clip/job/capture errors + mocked e2e · T11 Settings › ขั้นสูง + health row + e2e · T12 queue e2e (fake backend) · T13 docs + network test (written, not run) | gate 2 (T9←T2,T3,T4,T6,T7 · T10←T5,T8 · T11←T5,T8 · T12←T9,T10 (runs at the final gate) · T13←all) |
| final | controller: merge, full checks, `npm run build`, `npm run e2e`, commit `web/dist`, reviews, live preview for Pete | gate 3 |

**Critical path:** T4 → T6 → T9 → T12 (queue project at the final gate).
**Counts:** 3 waves + final gate · 13 tasks (= 13 lanes: 5 + 3 + 5).

### Lane rules (every task)
1. **Worktree and branch.** The controller creates one worktree per lane **before** dispatching it: `git worktree add .claude/worktrees/m5c-<lane> -b m5c/t<N>-<slug> m5c-temp-account` (branched from the head of `m5c-temp-account` at the start of the wave), and gives the lane its absolute path as `WORKTREE`. The harness option `isolation: "worktree"` is unreliable and is **not** used. The lane starts **every** shell command with `cd "$WORKTREE" &&` (the shell does not keep the directory between calls) and edits files only by their absolute path under `WORKTREE`. Never switch the main checkout's branch; never edit files outside `WORKTREE`.
2. **Files.** A task creates or modifies **only** the files in its **Files** list. Needing another file is a plan bug: stop and report it to the controller; do not edit the file.
3. **Shared files have exactly one owner per wave:**

   | File | W1 owner | W2 owner | W3 owner |
   |---|---|---|---|
   | `src/yttoolkit/core/yterrors.py`, `tests/unit/test_yterrors.py`, `tests/fixtures/errors/E_VIDEO_PRIVATE-4.txt`, `-5.txt` | T1 | — | — |
   | `PRD.md` | T1 (§7 error rows + note only) | — | T13 |
   | `tests/fixtures/README.md` | T1 (errors rows) | — | T13 |
   | `src/yttoolkit/redact.py`, `probe.py`, `api/errors.py`, `tests/unit/test_redact.py` | T2 | — | — |
   | `src/yttoolkit/lifecycle.py` | T2 (filters only) | — | T9 |
   | `src/yttoolkit/core/account_session.py`, `core/queue.py`, `tests/unit/test_account_session.py`, `tests/unit/test_queue.py` | T3 | — | — |
   | `src/yttoolkit/core/extractor.py`, `tests/fixtures/downloads/behaviors.json`, `tests/unit/test_extractor_download.py`, `tests/unit/test_extractor_account.py` | T4 | — | — |
   | `src/yttoolkit/core/account_scope.py` | T4 (`current_jar`, `signed_in`) | T6 (`AccountGate`, `with_account_retry`) | — |
   | `web/src/i18n/th.ts`, `web/src/lib/types.ts`, `lib/account.ts` (+test), `lib/events.ts` (+test), `lib/settings-api.ts`, the four Settings test literals, `web/e2e/axe-settled.ts` | T5 | — | — |
   | `core/videos.py`, `core/handlers.py`, `core/capture.py`, `api/videos.py`, `tests/unit/test_account_retry.py`, `test_videos_account.py`, `test_handlers_account.py`, `test_capture_account.py`, `tests/api/test_videos_api.py` | — | T6 | — |
   | `api/account.py`, `app.py`, `api/routes.py`, `core/settings.py`, `tests/api/test_account_api.py`, `tests/unit/test_settings.py`, `tests/api/test_settings_api.py` | — | T7 | — |
   | `web/src/components/account/**`, `web/src/components/layout.tsx` | — | T8 | — |
   | `web/src/components/queue/use-queue.ts` | — | T8 (`account` event toast) | T10 (failed-job toast) |
   | `tests/unit/test_lifecycle.py`, `tests/integration/test_account_privacy.py` | — | — | T9 |
   | `pages/video/load-error.tsx`, `pages/video/header.tsx`, `components/queue/job-row.tsx`, `pages/video/capture/use-capture.ts`, `capture-store.test.ts`, `web/e2e/account.spec.ts`, `web/e2e/video.spec.ts` | — | — | T10 |
   | `pages/settings.tsx`, `pages/settings/advanced-panel.tsx`, `pages/settings/health-panel.tsx`, `web/e2e/settings-advanced.spec.ts`, `web/e2e/health.spec.ts` | — | — | T11 |
   | `web/e2e/queue-account.spec.ts`, `web/playwright.config.ts` | — | — | T12 |
   | `BRD.md`, `docs/**` (except this plan), `tests/network_videos.toml`, `tests/network/test_account_network.py` | — | — | T13 |
   | `web/dist/**` | final gate only; **no lane builds into or commits `web/dist`** | | |

   A lane that needs a Thai string that is not in C5 stops and asks the controller (T5 is the only writer of `th.ts`; the controller adds a missing string at the gate, never inventing copy: spec §7 or Pete only).
4. **Tests.**
   - Python lanes run their own tests, then the full `uv run pytest -q -W error -p no:cacheprovider`.
   - Web lanes run `cd "$WORKTREE/web" && npm run typecheck && npm run lint && npm test`.
   - Lanes **do not run Playwright.** Specs are written, typechecked and linted in the lane and run at the gates by the controller.
   - The `queue` Playwright project is **always** run with `--workers=1` (the npm `e2e` script does this); never run it in parallel and never run two Playwright invocations at once.
   - **No spec in the default `chromium` project may create a real job, import a real account or change real settings.** Chromium specs mock `/api/cookies*` (and the clip's `/api/videos/<id>` error) with `page.route`; real imports and real jobs happen only in `queue-account.spec.ts` against the fake backend with fake cookie values.
   - Network tests (`@pytest.mark.network`) are written in T13 and **never run** without Pete's approval and his own backup-account export. No lane makes any request to YouTube.
5. **Processes.** No lane starts a server. Never touch the owner's app on port 8787. Kill processes by PID only (never by image name). Never `shell=True`.
6. **Commits.** Every commit message ends with exactly `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>` (this overrides any harness default trailer). Use `git commit -F- <<'EOF' … EOF`.
7. **Line endings.** Never change a file's existing line endings (every touched file is LF: `git ls-files --eol` shows `i/lf w/lf`): edit with the Edit tool (or `open(..., newline="")`); new text files are LF.

### Wave gate procedure (controller, serial)
1. Merge every lane branch of the wave into `m5c-temp-account` with `git merge --no-ff m5c/t<N>-<slug>`. A merge conflict means the plan is wrong: stop and report. Then `git worktree remove .claude/worktrees/m5c-<lane>` for each merged lane.
2. `uv sync --frozen && uv run pytest -q -W error -p no:cacheprovider` (must pass).
3. `cd web && npm ci && npm run typecheck && npm run lint && npm test`.
4. **Gate 1 only (R7 verification, required):** `cd web && npm run build` then `npx playwright test --project=queue --workers=1 e2e/queue-flow.spec.ts` (all 8 pass, including `:297` "แถบตั้ง --dock-bottom-offset …") and `npx playwright test --project=chromium e2e/settings-general.spec.ts e2e/nav.spec.ts` (two other axe specs, all pass). Do **not** commit `web/dist` at gate 1 or 2 (`git checkout -- web/dist` after the build if it shows changes).
5. Run the two-stage review (spec compliance, then code quality) from superpowers:subagent-driven-development on each task of the wave, and fix findings in the owning lane before the next wave.

### Final gate (controller, after wave 3)
1. Merge T9-T13 (`--no-ff`), then steps 2-3 above.
2. `cd web && npm run build` then `npm run e2e` (project `chromium` on `E2E_PORT` (8799), then project `queue` on `E2E_PORT + 1` with `--workers=1`, both fake mode, built `dist`; `playwright.config.ts` passes `YT_TOOLKIT_ACCOUNT_GRACE_S=5`). A failing `queue-account.spec.ts` goes back to T9/T10/T12; `account.spec.ts`/`video.spec.ts` to T8/T10; `settings-advanced.spec.ts`/`health.spec.ts` to T11.
3. Check total JS gzip ≤ 400 KB excluding fonts (PRD 6.5; the prototype build was 104 KB gzip for the main chunk).
4. Commit the rebuilt `web/dist` as `build(web): web/dist after M5 round C` (with the trailer).
5. Reviews as in step 5 above, then a live preview for Pete on port 8791 in fake mode (memory rule "preview after QA"): open `/v/ACCOUNTAGE1` → button → dialog (cancel / bad file / a fake `cookies.txt` with a `SAPISID` line) → banner → "ลบออกตอนนี้" → toast; queue `ACCOUNTAGE1` from W2 without an account → failed toast with the account button → import → the job retries; Settings › ขั้นสูง and the health row; a 640 px window. Real YouTube only through T13's network test after Pete's approval.

---

## Verified facts (read on 2026-10-06 at `81f78db` = code of `4b02feb`; the prototype was built from the same tree)
- **Line endings:** `.gitattributes` `* text=auto eol=lf`; every file this plan touches is `i/lf w/lf`.
- **Errors.** `core/yterrors.py:15-47` `MESSAGES` (`E_VIDEO_PRIVATE` :19, `E_AGE_RESTRICTED` :22, `E_UNKNOWN` last); `:51` `MESSAGES_NO_PARAMS`; `:73-76` the `E_VIDEO_PRIVATE` rule `("private video", "this video is private", "this playlist is private")`; `:135` `class YtError(Exception)` (`code`, `detail`, `retry_after`, `params`; `message` property fills templates). `tests/unit/test_yterrors.py` checks every `MESSAGES` entry against the PRD §7 table (`_prd_row`), every fixture `tests/fixtures/errors/<CODE>-<n>.txt` through `classify`, and `PRD` = repo `PRD.md`. Existing fixtures: `E_VIDEO_PRIVATE-1..3`. PRD §7 rows: `E_VIDEO_PRIVATE` `PRD.md:781`, `E_AGE_RESTRICTED` :784, `E_COOKIES_INVALID` :805, `E_COOKIES_UNAVAILABLE` :806, note :815. yt-dlp passes YouTube's playability `reason` (+ `. {subreason}`) to `raise_no_formats` at `yt_dlp/extractor/youtube/_video.py:4076`; no members-only text exists in yt-dlp's source.
- **Logging.** `api/errors.py:23-49` `_home_aliases` / `redact_home` (tests patch `errors.Path.home`); `lifecycle.py:114-137` `HomePathFilter`, `:165-170` `install_log_filters`, `:173-175` `setup_file_logging`, `:869` `serve()` calls `logging.basicConfig(level=logging.INFO)` at `:874`; `probe.py:64` `setup_file_log(paths)` (stdlib only) is what `__main__` calls first for `start` and `stop` (`__main__.py:32, :47`) before importing `lifecycle`; `docs/m4-followups.md:49` records the late-redactor gap.
- **Queue.** `core/queue.py:56` `SettingsView`; `:234` `_stopping` init; `:261` `tick` (`_SPAWN_FAILED` → `break`); `:417` `_end` (publishes the final state); `:440` `enqueue`; `:450` `cancel` (queued → cancelled at once; running with a context → `request_stop`; stale running → cancelled); `:473` `retry`; `:527` `pending_count()` = `JobStore.pending_count()` (queued + running, paused counts); `:540` `_publish_job`. `tests/unit/test_queue.py` `runner_factory` fixture, `jobs_of(kind, n)`.
- **Extractor.** `core/extractor.py:11` `import functools`; `:40` `from .frame_piece import …`; `:193` `_cookie_jar(filename)` (`YoutubeDLCookieJar`); `:200` `visitor_session`; `:205-225` `_attach_session` (`ydl.__dict__["cookiejar"] = jar`, `save_cookies` replaced); `:479` `class YtDlpExtractor`; `:495-508` `_ydl(opts, *, with_session=False)`; `:527` `probe`; `:559` `fetch_subtitle` (`_ydl(_PROBE_OPTS, with_session=True)` :568); `:689` `_extract_for_download` (:697); `:708` `_download_media` (:715); `:725` `fetch_frame_piece` (:744); `:788` `_extract(url, opts, with_session)` (playlist uses `with_session=False`); `:809` `FakeExtractor` (`PRIVATE_ID = "PRIVATEVID1"` :821, `probe` :841, behavior lookup :849). `tests/unit/test_extractor.py:1188` `test_attach_session_on_a_real_youtubedl` (the pattern for the new contract test). yt-dlp 2026.08.19: `YoutubeDL.cookiejar` is a cached property (pre-seeding `__dict__` works), every request handler holds `ydl.cookiejar`, the real option names are `verbose`, `debug_printtraffic`, `dump_intermediate_pages`, `write_pages`.
- **Videos / handlers / capture.** `core/videos.py:551` `VideoService.__init__`, `:576` `get(video_id, refresh=False, peek=False)`, `:657` `_probe_and_store`, `:709` `raw(video_id)`; `core/handlers.py:96` `HandlerDeps` (`auto_sharp` :112), `:1105-1113` `build_handlers` / `bind`; `core/capture.py:179` `CaptureService`, `:182` `__init__(…, *, work_root, now)`, `:250` `capture(video_id, t_ms)`; `tests/helpers_capture.py` (`BBB`, `MEDIA`, `FakeVideos`, `FixtureFetcher`, `StubQueue`, `StubSettings`, `clip_info`).
- **API / app.** `api/videos.py:177` `ctx_bot_check`, `:188` `# ---------- resolve ----------`, `:238` `video_info` (`@maps_yt_errors`); `E_AGE_RESTRICTED` → 409, `E_VIDEO_PRIVATE` → 404 (`STATUS_BY_CODE`); `app.py:74` `captures` field, `:77` `create_app` (routers only when the service is set); `api/routes.py:38-44` `/health`; `api/errors.py` `BAD_REQUEST_MESSAGE`, `error_response(status, code, message, detail)`; `tests/api/conftest.py:15` `make_client(**overrides)`. `core/settings.py:41` `READ_ONLY = ("cookies", "statsResetAt")`, `:188` the `cookies` default, `:225` `if clean:` (the write transaction). Tests pinning the old shape: `tests/unit/test_settings.py` defaults dict + `:161` `test_get_exposes_only_cookie_status_fields`; `tests/api/test_settings_api.py:10` `SETTING_KEYS`; `tests/unit/test_extractor_download.py` literal `C14` (must equal `behaviors.json`).
- **Lifecycle.** `lifecycle.py:259` `Services`; `:274` `open_services` (`deps.on_bot_check = queue.brake` :333, `CaptureService(...)` after it); `:523` `shutdown_services` (queue shutdown, then `events.publish("app.shutdown", {})`); `:747` `ctx.captures = services.captures`; `tests/unit/test_lifecycle.py:733` `_run_capturing_ctx(paths, fake_platform, monkeypatch, ready=True, **extra)`.
- **Web.** `pages/video/load-error.tsx:22` `LoadError`; `pages/video/errors.ts` `canRetry` (`FINAL_CODES` includes both account codes); `pages/video/header.tsx:331-337` `<LoadError … />`; `components/queue/job-row.tsx:100` `FailedRow`; `components/queue/use-queue.ts:163` `notifyJobChange`, `:185` `useServerEvents`; `pages/video/capture/use-capture.ts:40` the `runCapture` catch; `components/layout.tsx:86` `</header>`, `:95` `ShutdownDialog`; `pages/settings.tsx:12` `TABS`; `pages/settings/health-panel.tsx:46` `HealthPanel`, `:141` `</ItemGroup>`; `i18n/th.ts:243` `subs:` (new `account` section goes before it), settings tabs and health rows in the `settings`/`health` sections; `lib/types.ts:11` `Health`, `:330` `Settings.cookies`; `lib/events.ts:18` `EVENT_NAMES`, `:186` reconnect `reload(client, QUEUE_KEY)`; `lib/events.test.ts:320` listener count `7`, two reconnect tests expect `toHaveBeenCalledTimes(2)`; `e2e/video.spec.ts:11` `PRIVATE_MESSAGE`; `e2e/queue-flow.spec.ts:297` (R7); `components/queue/queue-bar.tsx:80` `queue-bar-progress`; `components/ui/progress.tsx:44` `progress-indicator` (`transition-all`); `playwright.config.ts:24` backend `env`. Vitest 5 (node), TypeScript `~6`, Prettier `printWidth` 80 is not enforced by lint (ESLint only).
- **Not present:** `/api/diagnostics` (M6); any `useCookies` support (still 422).

---

## Global Constraints
**Carried over:** every Global Constraint of `docs/superpowers/plans/2026-10-05-m5b2-capture-and-theater.md` (and through it M5-B, M5-A, M4, M3, M2, M1): Python 3.13 + uv; bind `127.0.0.1` only; error envelope `{"error":{"code","message","detail"}}`; `pathlib` everywhere; `core/` never imports `api/` or `platform/`; every screen has loading / empty / error / normal; no TODO comments; unit and API tests never touch the network; all web strings live in `web/src/i18n/th.ts`; backend user-facing messages live in `core/yterrors.MESSAGES` (+ `ACCOUNT_TRIED_MESSAGE`); never log an absolute output path; at most one amber primary button per page area.

**Project rules (owner, verbatim):**
- Commit messages end exactly with "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>".
- Never `shell=True` (no `os.system` / `os.popen`; external programs get an argument list).
- Only `yttoolkit.platform` checks the OS.
- `yt_dlp` is imported only in `src/yttoolkit/core/extractor.py` (never in tests; tests build a real `YoutubeDL` only through `YtDlpExtractor._ydl`).
- No personal data, tokens, cookie names/values, absolute output paths or clip titles in logs, SSE or API errors.
- Never change existing line endings (LF).
- Thai UI copy verbatim from spec §7; buttons start with a verb; no "กรุณา"; no "!"; never invent Thai strings.
- Chromium e2e never creates real jobs (mock POST `/api/jobs`); the `queue` Playwright project runs `--workers=1`.
- `web/dist` is committed only at the final gate.
- Narrow-window target 640 px (BRD #83): nothing overflows horizontally (`document.documentElement.scrollWidth <= 640`); no new phone-only polish.
- Never touch port 8787; kill processes by PID only.
- Network tests are marked `network` and owner-gated.

**M5-C specific (spec):**
- The sign-in is never written to disk in any form (C8): no file in `data/`, `work/`, `run/`, output folders, settings export or temp dirs; `cookiefile` is never set with an account; `save_cookies` is a no-op.
- The UI never says "คุกกี้" (C5); only the file name `cookies.txt` appears.
- Never use the account on `E_BOT_CHECK`, `E_NETWORK` or any code outside `ACCOUNT_CODES` (C9); the bot-check brake and queue spacing are unchanged; the account adds at most one retry per call.
- Account and visitor session are never attached to the same `YoutubeDL`; `verbose` / `debug_printtraffic` / `dump_intermediate_pages` / `write_pages` (and the CLI spellings `print_traffic` / `dump_pages`) are refused with an account.
- Error `detail` of a parse failure names the problem and line number only; signed-in failures are re-raised `from None` with a neutral detail.
- Accessibility: the dialog is labelled by its title, the file input has an accessible name, the inline error is linked with `aria-describedby` and `aria-invalid`; the banner countdown is `aria-live="off"`; axe (serious/critical) is clean in both themes.

**Tests:**
- Backend: `uv run pytest -q -W error -p no:cacheprovider` (no warnings).
- Web: `cd web && npm run typecheck && npm run lint && npm test` (ESLint 0 errors / 0 warnings).
- Final: `cd web && npm run build` then `npm run e2e` (queue project serial).

---

## Review Focus (inputs the spec implies that would most likely bite a real user)
1. **A real extension's `cookies.txt`:** UTF-8 BOM, CRLF, `#HttpOnly_` lines, a domain flag that disagrees with the leading dot, cookies of unrelated sites, a JSON export or a random text file → a valid file imports with only youtube.com/google.com kept; anything else is `E_COOKIES_INVALID` whose detail names the line number but never echoes content, nothing printed to the console, the held account unchanged. Pinned by T4 `test_bom_crlf_and_no_header_are_fine`, `test_a_wrong_domain_flag_is_fixed_not_fatal`, `test_keeps_only_youtube_and_google_domains`, `test_garbage_is_invalid_and_never_echoes_the_line` (JSON case included), T7 `test_an_invalid_file_is_422_and_keeps_the_held_account`.
2. **Several restricted clips queued one after another, a queue paused by a bot check, or a manual delete while a job downloads** → no deletion in the middle of a batch (grace only when the queue has no queued or running job; a new job cancels it; stale timers do nothing), the running job keeps its jar. Pinned by T3 `test_no_grace_while_the_queue_still_has_work`, `test_a_new_job_cancels_the_grace`, `test_stale_timers_after_clear_do_nothing`, `test_listener_hears_every_final_state_after_it_is_stored`, `test_spawn_failure_is_heard_as_ended`.
3. **The backup account has no access, or the user signed out / browsed YouTube in that window (rotated cookies)** → the same code with the "ลองด้วยบัญชีแล้ว…" copy, no account button loop, the account kept. Pinned by T6 `test_signed_in_failure_with_the_same_code_uses_the_tried_copy`, `test_an_account_without_access_gets_the_tried_copy` (API, handlers, capture), T10 e2e "ถือบัญชีอยู่แล้วแต่ยังเปิดไม่ได้…", T12 `queue-account.spec.ts` (PRIVATEVID1 part).
4. **Secrets in yt-dlp error text, tracebacks or a crash before logging is set up** → masked in `app.log`, never in SSE / API / files. Pinned by T2 `test_app_log_hides_a_secret_written_before_lifecycle_loads`, `test_secret_filter_masks_args_and_traceback`, `test_secret_values_are_masked`, T6 `test_signed_in_failure_with_the_same_code_uses_the_tried_copy` (`__cause__` None), T9 `test_canaries_never_leave_memory`.
5. **A bot check during the signed-in retry, or as the first error** → the account is never used for it and the queue brake still fires on `E_BOT_CHECK`. Pinned by T6 `test_other_codes_never_use_the_account`, `test_signed_in_bot_check_keeps_its_code_for_the_queue_brake`, `test_a_bot_check_is_never_retried_with_the_account`.

---


## Shared contracts (every lane codes against these)

### C1. Error copy and the members-only rule (`core/yterrors.py`, T1)
```python
MESSAGES["E_VIDEO_PRIVATE"] = "คลิปนี้เป็นส่วนตัวหรือเฉพาะสมาชิก ต้องเข้าสู่ระบบด้วยบัญชีที่มีสิทธิ์ดู"
MESSAGES["E_AGE_RESTRICTED"] = "คลิปนี้จำกัดอายุ ต้องเข้าสู่ระบบยูทูปถึงจะเปิดได้"
MESSAGES["E_COOKIES_INVALID"] = "ไฟล์นี้ใช้ไม่ได้ ตรวจว่าเข้าสู่ระบบยูทูปแล้วก่อนส่งออก แล้วส่งออก cookies.txt ใหม่"
ACCOUNT_CODES = frozenset({"E_AGE_RESTRICTED", "E_VIDEO_PRIVATE"})  # never E_BOT_CHECK (C9)
ACCOUNT_TRIED_MESSAGE = "ลองด้วยบัญชีแล้วยังเปิดไม่ได้ บัญชีนี้อาจไม่มีสิทธิ์ดูคลิปนี้ หรือการเข้าสู่ระบบหมดอายุแล้ว ลองนำเข้าใหม่"

class YtError(Exception):
    def __init__(self, code: str, detail: str = "", *, retry_after: int | None = None,
                 params: Mapping[str, str] | None = None, account_tried: bool = False) -> None
    account_tried: bool
    @property
    def message(self) -> str   # ACCOUNT_TRIED_MESSAGE when account_tried and code in ACCOUNT_CODES
# classify(): "members-only content", "join this channel to get access", "available to this channel's members" -> E_VIDEO_PRIVATE
```
`E_COOKIES_UNAVAILABLE` does not exist (no Firefox mode). HTTP statuses are unchanged (`E_AGE_RESTRICTED` 409, `E_VIDEO_PRIVATE` 404); `E_COOKIES_INVALID` is answered by `api/account.py` (422 / 413).

### C2. Redaction (`yttoolkit/redact.py`, new, stdlib only, T2)
```python
MASK = "<hidden>"
SIGN_IN_COOKIE_NAMES: tuple[str, ...]  # SAPISID, APISID, HSID, SID, SSID, SIDCC, LOGIN_INFO, __Secure-1PSID, __Secure-3PSID, ...
def redact_secrets(text: str) -> str          # Cookie:/Set-Cookie: values and NAME=value / NAME<TAB>value / "NAME": "value"
def redact_home(text: str) -> str             # moved from api/errors.py (same behaviour)
def _home_aliases(home: str) -> tuple[str, ...]   # moved, functools.cache
class HomePathFilter(logging.Filter)          # moved from lifecycle.py (message, args, traceback, stack)
class SecretFilter(logging.Filter)            # same mechanics with redact_secrets
def add_redaction(handler: logging.Handler) -> None   # adds both filters once (idempotent)
```
Old names keep working: `api/errors.redact_home`, `api/errors._home_aliases`, `api/errors._redact_home`, `lifecycle.HomePathFilter` (re-exports; `api/errors.py` keeps `from pathlib import Path` because tests patch `errors.Path.home`). `probe.setup_file_log` adds both filters when it creates (or finds) the `app.log` handler; `lifecycle.install_log_filters` adds `SecretFilter` too; `lifecycle.serve` adds both to the `basicConfig` console handlers.

### C3. Account service and the queue listener (`core/account_session.py` new, `core/queue.py`, T3)
```python
MAX_IMPORT_BYTES = 1_048_576
EXPIRY_S = 7200          # 2 h after import
GRACE_S = 600            # queue idle 10 min after a job that used the account
CLEAR_REASONS = frozenset({"manual", "queue_done", "expired", "shutdown"})

class AccountService:
    def __init__(self, parse: Callable[[str], Any], *, publish: Callable[[str, dict], None] | None = None,
                 busy: Callable[[], bool] = lambda: False, on_clear: Callable[[], None] | None = None,
                 now: Callable[[], datetime] = _utcnow, schedule: Callable[[float, Callable[[], None]], None] = _timer_schedule,
                 expiry_s: float = EXPIRY_S, grace_s: float = GRACE_S) -> None
    def import_text(self, text: str) -> dict      # replaces any held jar, restarts timers; YtError E_COOKIES_INVALID keeps the old one
    def clear(self, reason: str) -> dict          # no account = silent no-op; unknown reason = ValueError
    def status(self) -> dict                      # {"active": False, "used": False} | {"active": True, "importedAt", "expiresAt", "used"}
    def jar(self) -> Any | None
    def mark_used(self, job_id: str | None) -> None   # job id = counts for the grace; None = interactive (W2 / capture)
    def job_queued(self) -> None                  # QueueListener: cancels a running grace
    def job_ended(self, job_id: str) -> None      # QueueListener: starts the grace when a job that used the account ended and not busy()
```
Times are UTC ISO 8601 with seconds (`2026-10-06T05:00:00+00:00`). Events: `publish("account", {"active": True, "expiresAt": …})` on import and on grace start/cancel; `publish("account", {"active": False, "reason": reason})` on clear. `on_clear()` runs on clear and on replacing a held account. `publish`/`on_clear` errors are logged, never raised.
```python
# core/queue.py
class QueueListener(Protocol):
    def job_queued(self) -> None: ...
    def job_ended(self, job_id: str) -> None: ...
QueueRunner.listener: QueueListener | None = None   # set by lifecycle (T9)
```
Called outside the queue lock, after the state is stored: `job_queued()` once per `enqueue` call (non-empty) and per `retry`; `job_ended(id)` from `_end`, from `cancel` of a queued job or a stale running job, and for a spawn failure in `tick`. Listener exceptions are logged and swallowed.

### C4. Extractor account mode (`core/account_scope.py` part 1 + `core/extractor.py`, T4)
```python
# core/account_scope.py (T4 part; stdlib only)
def current_jar() -> Any | None
@contextmanager
def signed_in(jar: Any) -> Iterator[None]     # jar None = ValueError; resets on exit

# core/extractor.py
ACCOUNT_SIGN_IN_COOKIES = frozenset({"SAPISID", "__Secure-3PSID", "LOGIN_INFO"})
ACCOUNT_DOMAINS = ("youtube.com", "google.com")
ACCOUNT_FORBIDDEN_OPTS = frozenset({"verbose", "debug_printtraffic", "print_traffic", "dump_intermediate_pages", "dump_pages", "write_pages"})
def parse_account_cookies(text: str) -> Any   # YoutubeDLCookieJar | YtError("E_COOKIES_INVALID", "line N: expected 7 tab-separated fields" | "line N: expiry is not a number" | "<ExceptionClass>" | "no YouTube sign-in cookie")
class YtDlpExtractor:
    @contextmanager
    def _ydl(self, opts: dict, *, with_session: bool = False, with_account: Any | None = None) -> Iterator[Any]
```
`with_account` set: forbidden opts → `ValueError`; `cookiefile` removed; the jar is injected (`ydl.__dict__["cookiejar"] = jar`) and `save_cookies` is a no-op; the visitor session is not attached. `probe`, `fetch_subtitle`, `_extract_for_download`, `_download_media`, `fetch_frame_piece` pass `with_account=current_jar()`; `_extract` passes it only when `with_session` (playlists never). `FakeExtractor.probe`: an entry with `"needsAccount": "<CODE>"` raises `YtError(CODE, "ERROR: [youtube] <id>: fake: needs a signed-in account")` outside a `signed_in` scope; `PRIVATEVID1` stays private inside one. Fake clips (`behaviors.json`, `probeAs` BBB): `ACCOUNTAGE1` "คลิปจำกัดอายุ" (`E_AGE_RESTRICTED`), `ACCOUNTMEM1` "คลิปเฉพาะสมาชิก" (`E_VIDEO_PRIVATE`).

### C5. Web strings, types, data layer, SSE (`th.ts`, `types.ts`, `lib/account.ts`, `lib/events.ts`, T5 only)
```ts
// th.ts — new section before `subs` (verbatim spec §7; no "คุกกี้")
account: { use, title, warning, privateClips, steps: string[6], fileLabel: "cookies.txt", cancel, importRetry, import,
           invalid, banner: "กำลังใช้บัญชียูทูปชั่วคราว · ลบอัตโนมัติภายใน {time}", removeNow, removed, intro,
           statusOff, statusOn: "ใช้บัญชีชั่วคราวอยู่ ลบอัตโนมัติภายใน {time}", healthOn: "ใช้บัญชีชั่วคราวอยู่ (นำเข้าเมื่อ {time})" }
settings.tabs.advanced = "ขั้นสูง" · health.rows.account = "บัญชียูทูป"
// types.ts
export type AccountHealth = { status: "ok"; active: boolean; importedAt: string | null }
export type AccountStatus = { active: boolean; importedAt?: string; expiresAt?: string; used: boolean }
// Health gains `account?: AccountHealth`; Settings loses `cookies`
// lib/account.ts
export const ACCOUNT_KEY = ["account"] as const
export const ACCOUNT_CODES: ReadonlySet<string>          // E_AGE_RESTRICTED, E_VIDEO_PRIVATE
export const MAX_COOKIE_FILE_BYTES = 1_048_576
export const INACTIVE: AccountStatus                     // { active: false, used: false }
export type AccountEvent = { active: boolean; expiresAt?: string; reason?: string }
export function accountQuery()                           // GET /api/cookies, 404 = INACTIVE, staleTime Infinity, retry false
export function importAccount(text: string): Promise<AccountStatus>   // POST /cookies/import {text, acceptWarning: true}
export function deleteAccount(): Promise<AccountStatus>
export function isAccountCode(code: string | null | undefined): boolean
export function needsAccount(error: unknown): boolean
export function showAccountButton(code: string | null | undefined, active: boolean): boolean
export function remainingClock(expiresAt: string, now: number, importedAt?: string): string   // "HH:MM" left, minutes rounded up
export function localClock(iso: string): string                                                // local "HH:MM", "" if unreadable
export const DELETE_TIME_STYLE: "remaining" | "clock"   // Q1 switch, default "remaining"
export function deleteTime(status: { expiresAt: string; importedAt?: string }, now: number, style?: "remaining" | "clock"): string
export function fileTooBig(size: number): boolean
export function applyAccountEvent(prev: AccountStatus | undefined, event: AccountEvent): AccountStatus | undefined
// lib/events.ts
ServerEvent gains ({ type: "account" } & AccountEvent); EVENT_NAMES gains "account"
ConnectOptions gains onAccount?: (event: AccountEvent) => void   // called after the cache is updated
// reconnect also reloads ACCOUNT_KEY
// web/e2e/axe-settled.ts
export const KEEPS_ANIMATING = '[data-testid="queue-bar-progress"], [data-slot="progress-indicator"]'
```

### C6. Retry rule and signed-in probes (`core/account_scope.py` part 2, `videos.py`, `handlers.py`, `capture.py`, `api/videos.py`, T6)
```python
class AccountGate(Protocol):
    def jar(self) -> Any | None: ...
    def mark_used(self, job_id: str | None) -> None: ...
def with_account_retry(accounts: AccountGate | None, call: Callable[[], T], *, job_id: str | None = None) -> T

class VideoService:
    def forget_signed_in(self) -> None          # drop every clip probed with the account
HandlerDeps.accounts: AccountGate | None = None  # read at run time by build_handlers.bind
CaptureService.__init__(..., *, work_root, now=..., accounts: AccountGate | None = None)
def ctx_accounts(ctx: AppContext) -> AccountGate | None   # api/videos.py, getattr(ctx, "accounts", None)
```
Signed-in failure: `YtError(code, f"signed-in retry failed ({code})", retry_after=…, params=…, account_tried=code in ACCOUNT_CODES)` raised `from None`. Inside `signed_in`, `VideoService.get` probes with `_probe_signed_in` (trimmed probe kept in `_signed`, never written to `videos`, never in history); `get` and `raw` serve a kept copy (deep copies) before probing.

### C7. Account API, health row, retired setting (`api/account.py` new, `app.py`, `api/routes.py`, `core/settings.py`, T7)
`AppContext.accounts: AccountService | None = None`; `create_app` includes `build_account_router(ctx)` under `/api` only when set.

| Method | Path | Body | Answer |
|---|---|---|---|
| GET | `/api/cookies` | — | `status()` |
| POST | `/api/cookies/import` | `{text: str, acceptWarning: true}` (no other keys) | 200 `status()` · 422 `E_BAD_REQUEST` (shape) · 409 `E_BAD_REQUEST` (`acceptWarning` not `true`) · 413 `E_COOKIES_INVALID` (> 1 MB UTF-8) · 422 `E_COOKIES_INVALID` (parse, detail from the parser) |
| DELETE | `/api/cookies` | — | 200 `clear("manual")` |

`GET /api/health` adds `account: {"status": "ok", "active": bool, "importedAt": str | None}` when `ctx.accounts` is set. `core/settings.py`: `READ_ONLY = ("statsResetAt",)`, `RETIRED_KEYS = ("cookies",)` (skipped on read because not in the defaults, deleted in the next `patch` transaction); `cookies` leaves the defaults.

### C8. Web account UI (`web/src/components/account/`, `layout.tsx`, `use-queue.ts` part 1, T8)
```ts
// account-store.ts
export type AccountDialogRequest = { origin: "error" | "settings"; onImported?: () => void }
export type AccountDialogState = { open: boolean; request: AccountDialogRequest | null }
export const accountDialog: { get, open(request), close(), subscribe(listener) }
export function openAccountDialog(request: AccountDialogRequest): void
export function useAccountDialog(): AccountDialogState
// dialog-model.ts
export type DialogState = { fileName: string | null; text: string | null; error: string | null; pending: boolean }
export type DialogAction = picked | rejected | submitting | failed | reset
export const EMPTY_DIALOG: DialogState
export function dialogReducer(state, action): DialogState
export function canImport(state: DialogState): boolean
export function importLabel(request: AccountDialogRequest | null): string   // "นำเข้าแล้วลองใหม่" | "นำเข้า"
// use-account.ts
export const REMOVED_TOAST_ID = "account-removed"
export function showRemovedToast(): void          // toast.info(th.account.removed, {duration: Infinity, action: ปิด})
export function useAccountStatus(): AccountStatus // INACTIVE while loading / on error
export function useDeleteAccount(): { remove: () => void; pending: boolean }
export function useNow(active: boolean, intervalMs?: number): number   // ticks every 15 s while active
// account-dialog.tsx  export function AccountDialog()      (mounted once in layout; data-testid="account-dialog")
// account-banner.tsx  export function AccountBanner()      (data-testid="account-banner", under </header>)
// account-button.tsx  export function UseAccountButton(props: { onImported?; origin?: "error" | "settings"; variant?: "default" | "outline"; size?: "sm" | "default"; className? })
```
`useServerEvents` passes `onAccount`: an event with `active: false` and a `reason` shows the removed toast in every tab.

### C9. Lifecycle (`lifecycle.py` part 2, T9)
`Services.accounts: AccountService | None = None`; `ACCOUNT_GRACE_ENV = "YT_TOOLKIT_ACCOUNT_GRACE_S"`; `account_grace_s(fake: bool) -> float` (fake mode and `0 < v ≤ 600` only, else `GRACE_S`); `open_services` builds `AccountService(parse_account_cookies, publish=events.publish, busy=lambda: queue.pending_count() > 0, on_clear=videos.forget_signed_in, grace_s=account_grace_s(fake))`, sets `queue.listener` and `deps.accounts`, passes `accounts=` to `CaptureService`; `shutdown_services` calls `clear("shutdown")` after the queue stops and before `app.shutdown`; `_run_server` sets `ctx.accounts = services.accounts`.

### C10. Web entry points (T10)
`LoadError` prop `account?: { onImported: () => void }` (header passes `video.refetch`); `FailedRow` shows `UseAccountButton` (outline, sm) with `onImported` = the row's retry mutation; the failed-job toast uses `action` = account / `cancel` = details when `showAccountButton(code, active)`; `runCapture`'s error toast gets the account action that re-runs the same `tMs`. Every placement shows the button only when `showAccountButton(code, useAccountStatus().active)`.

### C11. Settings › ขั้นสูง and the health row (T11)
`TABS = ["general", "advanced", "health", "about"]` (`/settings/advanced`); `AdvancedPanel` (intro, `data-testid="account-status"` line with `statusOff` / `statusOn` + "ลบออกตอนนี้", `UseAccountButton origin="settings"`; skeleton while loading, retry alert on error); `HealthPanel` renders `AccountRow` (`data-testid="tool-account"`, always "พร้อม") when `health.account` exists.

### C12. E2E files
Chromium (mocked `/api/cookies*`): `web/e2e/account.spec.ts` + one changed test in `video.spec.ts` (T10), `web/e2e/settings-advanced.spec.ts` + two tests appended to `health.spec.ts` (T11). Queue (real fake backend, serial): `web/e2e/queue-account.spec.ts` (T12) with `ACCOUNTAGE1` and `PRIVATEVID1`, grace shortened to 5 s by `playwright.config.ts`.

---

## File structure

**Backend (new):** `src/yttoolkit/redact.py` (T2) · `core/account_session.py` (T3) · `core/account_scope.py` (T4, grown by T6) · `api/account.py` (T7).
**Backend (modified):** `core/yterrors.py` (T1) · `probe.py`, `api/errors.py`, `lifecycle.py` (T2) · `core/queue.py` (T3) · `core/extractor.py` (T4) · `core/videos.py`, `core/handlers.py`, `core/capture.py`, `api/videos.py` (T6) · `app.py`, `api/routes.py`, `core/settings.py` (T7) · `lifecycle.py` (T9).
**Fixtures:** `tests/fixtures/errors/E_VIDEO_PRIVATE-4.txt`, `-5.txt` (T1, new) · `tests/fixtures/README.md` (T1 errors rows, T13 account section) · `tests/fixtures/downloads/behaviors.json` (T4) · `tests/network_videos.toml` (T13).
**Tests (new):** `tests/unit/test_redact.py` (T2) · `test_account_session.py` (T3) · `test_extractor_account.py` (T4) · `test_account_retry.py`, `test_videos_account.py`, `test_handlers_account.py`, `test_capture_account.py` (T6) · `tests/api/test_account_api.py` (T7) · `tests/integration/test_account_privacy.py` (T9) · `tests/network/test_account_network.py` (T13).
**Tests (modified):** `test_yterrors.py` (T1) · `test_queue.py` (T3) · `test_extractor_download.py` (T4) · `tests/api/test_videos_api.py` (T6) · `test_settings.py`, `tests/api/test_settings_api.py` (T7) · `test_lifecycle.py` (T9).
**Web (new):** `web/src/lib/account.ts` + test (T5) · `web/src/components/account/{account-store.ts, dialog-model.ts, dialog-model.test.ts, use-account.ts, account-dialog.tsx, account-banner.tsx, account-button.tsx}` (T8) · `web/src/pages/settings/advanced-panel.tsx` (T11) · `web/e2e/account.spec.ts` (T10), `settings-advanced.spec.ts` (T11), `queue-account.spec.ts` (T12).
**Web (modified):** `th.ts`, `types.ts`, `events.ts` (+test), `settings-api.ts`, four Settings test literals, `e2e/axe-settled.ts` (T5) · `layout.tsx`, `queue/use-queue.ts` (T8) · `load-error.tsx`, `header.tsx`, `queue/job-row.tsx`, `queue/use-queue.ts`, `capture/use-capture.ts`, `capture-store.test.ts`, `e2e/video.spec.ts` (T10) · `settings.tsx`, `settings/health-panel.tsx`, `e2e/health.spec.ts` (T11) · `playwright.config.ts` (T12).
**Docs (modified):** `PRD.md` (T1 §7 rows; T13 the rest) · `BRD.md`, `docs/acceptance.md`, `docs/m4-followups.md`, `docs/m5c-prep.md` (T13).

---


## Wave 1

### Task 1: Error copy, the members-only rule, the tried-with-account message, PRD §7 rows

**Files:**
- Modify: `src/yttoolkit/core/yterrors.py` (copy, `ACCOUNT_CODES`, `ACCOUNT_TRIED_MESSAGE`, `account_tried`, members-only phrases)
- Modify: `tests/unit/test_yterrors.py`
- Create: `tests/fixtures/errors/E_VIDEO_PRIVATE-4.txt`, `tests/fixtures/errors/E_VIDEO_PRIVATE-5.txt` (synthesized, R4)
- Modify: `tests/fixtures/README.md` (two `errors/` rows only)
- Modify: `PRD.md` (§7: the `E_VIDEO_PRIVATE`, `E_AGE_RESTRICTED`, `E_COOKIES_INVALID` rows, drop `E_COOKIES_UNAVAILABLE`, the note under the table; nothing else, T13 owns the rest)

**Interfaces:**
- Consumes: `MESSAGES`, `MESSAGES_NO_PARAMS`, `classify`, `YtError` (`core/yterrors.py`); the PRD row check in `test_yterrors.py`.
- Produces: C1 exactly (`ACCOUNT_CODES`, `ACCOUNT_TRIED_MESSAGE`, `YtError(..., account_tried=)`, the three messages, the members-only rule).

- [ ] **Step 1: Write the failing tests and fixtures**

Create `tests/fixtures/errors/E_VIDEO_PRIVATE-4.txt` (one line, LF, trailing newline):
```text
ERROR: [youtube] Ab3dEfGhIjK: Join this channel to get access to members-only content like this video, and other exclusive perks.
```

Create `tests/fixtures/errors/E_VIDEO_PRIVATE-5.txt`:
```text
ERROR: [youtube] Ab3dEfGhIjK: This video is available to this channel's members on level: Supporter (or any higher level). Join this channel to get access to members-only content and other exclusive perks.
```

In `tests/unit/test_yterrors.py`:
Replace (1):
```python

import pytest

from yttoolkit.core.yterrors import MESSAGES, MESSAGES_NO_PARAMS, YtError, classify

ERRORS_DIR = Path(__file__).resolve().parents[1] / "fixtures" / "errors"
FIXTURES = sorted(ERRORS_DIR.glob("*.txt"))
```
with:
```python

import pytest

from yttoolkit.core.yterrors import (
    ACCOUNT_CODES,
    ACCOUNT_TRIED_MESSAGE,
    MESSAGES,
    MESSAGES_NO_PARAMS,
    YtError,
    classify,
)

ERRORS_DIR = Path(__file__).resolve().parents[1] / "fixtures" / "errors"
FIXTURES = sorted(ERRORS_DIR.glob("*.txt"))
```

Replace (2):
```python
    )
    assert YtError("E_QUEUE_PAUSED").message == MESSAGES["E_BOT_CHECK"]
    assert "{time}" not in str(YtError("E_QUEUE_PAUSED"))
```
with:
```python
    )
    assert YtError("E_QUEUE_PAUSED").message == MESSAGES["E_BOT_CHECK"]
    assert "{time}" not in str(YtError("E_QUEUE_PAUSED"))


# ---------- M5 รอบ C: บัญชียูทูปชั่วคราว ----------


def test_m5c_messages_are_verbatim_spec_copy() -> None:
    assert MESSAGES["E_AGE_RESTRICTED"] == "คลิปนี้จำกัดอายุ ต้องเข้าสู่ระบบยูทูปถึงจะเปิดได้"
    assert MESSAGES["E_VIDEO_PRIVATE"] == "คลิปนี้เป็นส่วนตัวหรือเฉพาะสมาชิก ต้องเข้าสู่ระบบด้วยบัญชีที่มีสิทธิ์ดู"
    assert MESSAGES["E_COOKIES_INVALID"] == (
        "ไฟล์นี้ใช้ไม่ได้ ตรวจว่าเข้าสู่ระบบยูทูปแล้วก่อนส่งออก แล้วส่งออก cookies.txt ใหม่"
    )
    assert ACCOUNT_TRIED_MESSAGE == (
        "ลองด้วยบัญชีแล้วยังเปิดไม่ได้ บัญชีนี้อาจไม่มีสิทธิ์ดูคลิปนี้ หรือการเข้าสู่ระบบหมดอายุแล้ว ลองนำเข้าใหม่"
    )
    assert "E_COOKIES_UNAVAILABLE" not in MESSAGES  # ไม่มีโหมด Firefox (C4)


def test_account_codes_never_include_the_bot_check() -> None:
    assert ACCOUNT_CODES == {"E_AGE_RESTRICTED", "E_VIDEO_PRIVATE"}


@pytest.mark.parametrize("code", sorted(ACCOUNT_CODES))
def test_account_tried_switches_the_message_and_keeps_the_code(code: str) -> None:
    err = YtError(code, "signed-in retry failed", account_tried=True)
    assert err.code == code and err.account_tried is True
    assert err.message == ACCOUNT_TRIED_MESSAGE
    assert YtError(code).account_tried is False and YtError(code).message == MESSAGES[code]


def test_account_tried_does_not_change_other_codes() -> None:
    assert YtError("E_NETWORK", account_tried=True).message == MESSAGES["E_NETWORK"]
    assert YtError("E_BOT_CHECK", account_tried=True).message == MESSAGES["E_BOT_CHECK"]


@pytest.mark.parametrize(
    "message",
    [
        "Join this channel to get access to members-only content like this video, and other exclusive perks.",
        "This video is available to this channel's members on level: Supporter (or any higher level).",
        "ERROR: [youtube] x: JOIN THIS CHANNEL TO GET ACCESS to members-only content",
    ],
)
def test_members_only_is_private(message: str) -> None:
    assert classify(message) == "E_VIDEO_PRIVATE"


def test_account_tried_note_is_in_prd() -> None:
    assert f'"{ACCOUNT_TRIED_MESSAGE}"' in PRD.read_text(encoding="utf-8")


def test_prd_has_no_firefox_cookie_code() -> None:
    assert _prd_row(PRD.read_text(encoding="utf-8"), "E_COOKIES_UNAVAILABLE") is None
```

- [ ] **Step 2: Run them, expect FAIL**

Run: `cd "$WORKTREE" && uv run pytest tests/unit/test_yterrors.py -q -W error -p no:cacheprovider`
Expected: collection error `ImportError: cannot import name 'ACCOUNT_CODES' from 'yttoolkit.core.yterrors'`.

- [ ] **Step 3: Implement `core/yterrors.py`**
Replace (1):
```python
    "E_INVALID_INPUT": "ลิงก์นี้ไม่ใช่ลิงก์ยูทูป ลองคัดลอกจากแถบที่อยู่ของเบราว์เซอร์อีกครั้ง",
    # PRD ข้อ 7 "ตั้งแต่ M4" (มีคิวแล้ว): คิวพักเองแบบเบรกฉุกเฉิน
    "E_BOT_CHECK": "ยูทูปขอให้ยืนยันว่าไม่ใช่บอท พักคิวไว้ 10 นาทีก่อนนะ",
    "E_VIDEO_PRIVATE": "คลิปนี้เป็นส่วนตัว เจ้าของต้องเปิดเป็นสาธารณะก่อน",
    "E_VIDEO_UNAVAILABLE": "คลิปนี้ถูกลบหรือไม่มีแล้ว",
    "E_GEO_BLOCKED": "คลิปนี้ดูในประเทศไทยไม่ได้",
    "E_AGE_RESTRICTED": "คลิปนี้จำกัดอายุ ต้องล็อกอินถึงจะโหลดได้ ซึ่งเวอร์ชันนี้ยังไม่รองรับ",
    "E_LIVE_NOT_READY": "คลิปนี้ยังถ่ายทอดสดอยู่หรือยังไม่เผยแพร่ ลองใหม่หลังจบไลฟ์",
    # M5 รอบ B มีโหมดคมแล้ว (BRD #33): ข้อความชวนไปกด "ขอภาพคม"
    "E_NO_STORYBOARD": 'คลิปนี้ไม่มีภาพตัวอย่างแบบเร็ว กด "ขอภาพคม" แทนได้',
```
with:
```python
    "E_INVALID_INPUT": "ลิงก์นี้ไม่ใช่ลิงก์ยูทูป ลองคัดลอกจากแถบที่อยู่ของเบราว์เซอร์อีกครั้ง",
    # PRD ข้อ 7 "ตั้งแต่ M4" (มีคิวแล้ว): คิวพักเองแบบเบรกฉุกเฉิน
    "E_BOT_CHECK": "ยูทูปขอให้ยืนยันว่าไม่ใช่บอท พักคิวไว้ 10 นาทีก่อนนะ",
    # M5 รอบ C (spec 7): ข้อความตอนยังไม่ได้ใช้บัญชี หน้าเว็บมีปุ่ม "ใช้บัญชียูทูปชั่วคราว" ต่อท้าย
    "E_VIDEO_PRIVATE": "คลิปนี้เป็นส่วนตัวหรือเฉพาะสมาชิก ต้องเข้าสู่ระบบด้วยบัญชีที่มีสิทธิ์ดู",
    "E_VIDEO_UNAVAILABLE": "คลิปนี้ถูกลบหรือไม่มีแล้ว",
    "E_GEO_BLOCKED": "คลิปนี้ดูในประเทศไทยไม่ได้",
    "E_AGE_RESTRICTED": "คลิปนี้จำกัดอายุ ต้องเข้าสู่ระบบยูทูปถึงจะเปิดได้",
    "E_LIVE_NOT_READY": "คลิปนี้ยังถ่ายทอดสดอยู่หรือยังไม่เผยแพร่ ลองใหม่หลังจบไลฟ์",
    # M5 รอบ B มีโหมดคมแล้ว (BRD #33): ข้อความชวนไปกด "ขอภาพคม"
    "E_NO_STORYBOARD": 'คลิปนี้ไม่มีภาพตัวอย่างแบบเร็ว กด "ขอภาพคม" แทนได้',
```

Replace (2):
```python
    "E_JOB_STATE": "งานนี้เปลี่ยนสถานะไปแล้ว ลองรีเฟรชหน้าเว็บ",
    # ยูทูปตอบ 4xx อื่นที่ไม่ใช่ 429 (เช่น 403 ตอนโหลดไฟล์) ไม่ใช่เน็ตหลุด จึงไม่ลองใหม่อัตโนมัติและไม่พักคิว (Q2)
    "E_YT_REFUSED": "ยูทูปไม่ยอมส่งไฟล์ของคลิปนี้ตอนนี้ ลองใหม่ภายหลัง",
    "E_UNKNOWN": "มีบางอย่างผิดพลาด ถ่ายภาพหน้าจอนี้ส่งให้ผู้ดูแล",
}
```
with:
```python
    "E_JOB_STATE": "งานนี้เปลี่ยนสถานะไปแล้ว ลองรีเฟรชหน้าเว็บ",
    # ยูทูปตอบ 4xx อื่นที่ไม่ใช่ 429 (เช่น 403 ตอนโหลดไฟล์) ไม่ใช่เน็ตหลุด จึงไม่ลองใหม่อัตโนมัติและไม่พักคิว (Q2)
    "E_YT_REFUSED": "ยูทูปไม่ยอมส่งไฟล์ของคลิปนี้ตอนนี้ ลองใหม่ภายหลัง",
    # M5 รอบ C: ไฟล์ cookies.txt ที่นำเข้าใช้ไม่ได้ (ไม่ใช่รูปแบบ Netscape ใหญ่เกิน 1 MB หรือไม่มีคุกกี้เข้าสู่ระบบของยูทูป)
    "E_COOKIES_INVALID": "ไฟล์นี้ใช้ไม่ได้ ตรวจว่าเข้าสู่ระบบยูทูปแล้วก่อนส่งออก แล้วส่งออก cookies.txt ใหม่",
    "E_UNKNOWN": "มีบางอย่างผิดพลาด ถ่ายภาพหน้าจอนี้ส่งให้ผู้ดูแล",
}
```

Replace (3):
```python
    # ไม่รู้เวลาที่คิวจะกลับมา (ไม่ควรเกิด capture ส่งเวลาเสมอ): ใช้ข้อความของ E_BOT_CHECK ที่มีอยู่แล้ว
    "E_QUEUE_PAUSED": "ยูทูปขอให้ยืนยันว่าไม่ใช่บอท พักคิวไว้ 10 นาทีก่อนนะ",
}

# ตรวจตามลำดับนี้ รหัสที่เจาะจงมาก่อนคำกว้าง ๆ เพราะข้อความจริงมักมีหลายวลีปนกัน เช่น
# "Video unavailable. ... blocked it in your country" = ติดประเทศ ไม่ใช่คลิปหาย
```
with:
```python
    # ไม่รู้เวลาที่คิวจะกลับมา (ไม่ควรเกิด capture ส่งเวลาเสมอ): ใช้ข้อความของ E_BOT_CHECK ที่มีอยู่แล้ว
    "E_QUEUE_PAUSED": "ยูทูปขอให้ยืนยันว่าไม่ใช่บอท พักคิวไว้ 10 นาทีก่อนนะ",
}

# M5 รอบ C: รหัสที่ลองใหม่ด้วยบัญชียูทูปชั่วคราวได้ (spec 2.4) ห้ามเพิ่ม E_BOT_CHECK (C9: ปกป้องบัญชี)
ACCOUNT_CODES = frozenset({"E_AGE_RESTRICTED", "E_VIDEO_PRIVATE"})
# ข้อความของ ACCOUNT_CODES เมื่อลองด้วยบัญชีแล้วยังได้รหัสเดิม (spec 7) ใช้แทน MESSAGES ของรหัสนั้น
ACCOUNT_TRIED_MESSAGE = (
    "ลองด้วยบัญชีแล้วยังเปิดไม่ได้ บัญชีนี้อาจไม่มีสิทธิ์ดูคลิปนี้ หรือการเข้าสู่ระบบหมดอายุแล้ว ลองนำเข้าใหม่"
)

# ตรวจตามลำดับนี้ รหัสที่เจาะจงมาก่อนคำกว้าง ๆ เพราะข้อความจริงมักมีหลายวลีปนกัน เช่น
# "Video unavailable. ... blocked it in your country" = ติดประเทศ ไม่ใช่คลิปหาย
```

Replace (4):
```python
    ),
    (
        "E_VIDEO_PRIVATE",
        ("private video", "this video is private", "this playlist is private"),
    ),
    (
        "E_GEO_BLOCKED",
```
with:
```python
    ),
    (
        "E_VIDEO_PRIVATE",
        (
            "private video",
            "this video is private",
            "this playlist is private",
            # M5 รอบ C: คลิปเฉพาะสมาชิกของช่อง (เหตุผลที่ยูทูปส่งผ่าน raise_no_formats ของ extractor/youtube/_video.py)
            "members-only content",
            "join this channel to get access",
            "available to this channel's members",
        ),
    ),
    (
        "E_GEO_BLOCKED",
```

Replace (5):
```python

    retry_after = อีกกี่วินาทีลองใหม่ได้ (มีเฉพาะ E_SESSION_WARMING) API ส่งเป็น retryAfterSeconds และ Retry-After
    params = ค่าที่เติมลงข้อความ (เช่น E_DISK_FULL ใช้ {"size": "3.2 GB"}) ไม่มี = ข้อความตามตาราง
    """

    code: str
    detail: str
    retry_after: int | None
    params: Mapping[str, str] | None

    def __init__(
        self,
```
with:
```python

    retry_after = อีกกี่วินาทีลองใหม่ได้ (มีเฉพาะ E_SESSION_WARMING) API ส่งเป็น retryAfterSeconds และ Retry-After
    params = ค่าที่เติมลงข้อความ (เช่น E_DISK_FULL ใช้ {"size": "3.2 GB"}) ไม่มี = ข้อความตามตาราง
    account_tried = ลองด้วยบัญชียูทูปชั่วคราวแล้ว (M5 รอบ C) รหัสใน ACCOUNT_CODES ใช้ ACCOUNT_TRIED_MESSAGE
    """

    code: str
    detail: str
    retry_after: int | None
    params: Mapping[str, str] | None
    account_tried: bool

    def __init__(
        self,
```

Replace (6):
```python
        *,
        retry_after: int | None = None,
        params: Mapping[str, str] | None = None,
    ) -> None:
        self.code = code
        self.detail = detail
        self.retry_after = retry_after
        self.params = params
        super().__init__(f"{code}: {detail or self.message}")

    @property
```
with:
```python
        *,
        retry_after: int | None = None,
        params: Mapping[str, str] | None = None,
        account_tried: bool = False,
    ) -> None:
        self.code = code
        self.detail = detail
        self.retry_after = retry_after
        self.params = params
        self.account_tried = account_tried
        super().__init__(f"{code}: {detail or self.message}")

    @property
```

Replace (7):
```python

        ข้อความที่มี {ชื่อ} เติมค่าจาก params ไม่มี params หรือค่าไม่ครบ = ข้อความสำรองใน MESSAGES_NO_PARAMS
        (error ห้ามพังซ้อน และห้ามโชว์ {ชื่อ} ดิบ) ข้อความธรรมดาไม่สน params
        """
        template = MESSAGES.get(self.code, MESSAGES["E_UNKNOWN"])
        fallback = MESSAGES_NO_PARAMS.get(self.code)
        if fallback is None:
```
with:
```python

        ข้อความที่มี {ชื่อ} เติมค่าจาก params ไม่มี params หรือค่าไม่ครบ = ข้อความสำรองใน MESSAGES_NO_PARAMS
        (error ห้ามพังซ้อน และห้ามโชว์ {ชื่อ} ดิบ) ข้อความธรรมดาไม่สน params
        ลองด้วยบัญชีแล้ว (account_tried) และรหัสอยู่ใน ACCOUNT_CODES = ACCOUNT_TRIED_MESSAGE
        """
        if self.account_tried and self.code in ACCOUNT_CODES:
            return ACCOUNT_TRIED_MESSAGE
        template = MESSAGES.get(self.code, MESSAGES["E_UNKNOWN"])
        fallback = MESSAGES_NO_PARAMS.get(self.code)
        if fallback is None:
```

- [ ] **Step 4: PRD §7 rows and the fixture README rows**

In `PRD.md` (edit only these lines; each `old` is unique):
Replace (1):
```markdown
|---|---|---|
| `E_INVALID_INPUT` | ลิงก์นี้ไม่ใช่ลิงก์ยูทูป ลองคัดลอกจากแถบที่อยู่ของเบราว์เซอร์อีกครั้ง | ทำรายการอื่นต่อ |
| `E_BOT_CHECK` | ยูทูปขอให้ยืนยันว่าไม่ใช่บอท รอสัก 10 นาทีแล้วค่อยลองใหม่ | เบรกฉุกเฉิน · **ตั้งแต่ M4** (มีคิวแล้ว) เปลี่ยนข้อความเป็น "ยูทูปขอให้ยืนยันว่าไม่ใช่บอท พักคิวไว้ 10 นาทีก่อนนะ" และเบรกฉุกเฉิน · **งานที่เจอครั้งแรก (Q1, BRD #84)** กลับไปหัวคิวหนึ่งครั้ง (สถานะ `running → queued` ในธุรกรรมเดียว นับ `bot_checks` = 1) แล้วเริ่มเองเมื่อพักครบ · เจอซ้ำในงานเดียวกัน → งานล้มเหลวด้วย `E_BOT_CHECK` · ผู้ใช้กด "ลองใหม่" เองนับเป็นรอบใหม่ (ได้โอกาสอีกหนึ่งครั้ง) · **ตัดสินจากรหัส error เท่านั้น ไม่ดู HTTP status** · `E_TRANSLATION_BLOCKED`, `E_SESSION_WARMING` และรหัสอื่นไม่เบรก · เจอระหว่างพักอยู่ = ต่อเวลาพักออกไปอีก 10 นาที · "ลองต่อเลย" (`POST /queue/resume`) ปลดพักทันที · ส่ง `queue.paused` / `queue.resumed` ทาง SSE |
| `E_VIDEO_PRIVATE` | คลิปนี้เป็นส่วนตัว เจ้าของต้องเปิดเป็นสาธารณะก่อน | งานล้มเหลว · **ตั้งแต่ M5** (มีคุกกี้แล้ว) เปลี่ยนข้อความเป็น "คลิปนี้เป็นส่วนตัวหรือเฉพาะสมาชิก ถ้าบัญชี YouTube ของคุณมีสิทธิ์ดู เปิดใช้คุกกี้ได้ที่ ตั้งค่า > ขั้นสูง" และถ้าเปิดคุกกี้ไว้ ลองใหม่ด้วยคุกกี้ 1 ครั้ง (FR-CK-7) |
| `E_VIDEO_UNAVAILABLE` | คลิปนี้ถูกลบหรือไม่มีแล้ว | งานล้มเหลว |
| `E_GEO_BLOCKED` | คลิปนี้ดูในประเทศไทยไม่ได้ | งานล้มเหลว |
| `E_AGE_RESTRICTED` | คลิปนี้จำกัดอายุ ต้องล็อกอินถึงจะโหลดได้ ซึ่งเวอร์ชันนี้ยังไม่รองรับ | งานล้มเหลว · **ตั้งแต่ M5** (มีคุกกี้แล้ว) เปลี่ยนข้อความเป็น "คลิปนี้จำกัดอายุ ต้องใช้บัญชี YouTube ถึงจะโหลดได้ เปิดใช้ได้ที่ ตั้งค่า > ขั้นสูง" และถ้าเปิดคุกกี้ไว้ ลองใหม่ด้วยคุกกี้ 1 ครั้ง (FR-CK-7) |
| `E_LIVE_NOT_READY` | คลิปนี้ยังถ่ายทอดสดอยู่หรือยังไม่เผยแพร่ ลองใหม่หลังจบไลฟ์ | งานล้มเหลว |
| `E_NO_SUBTITLES` | คลิปนี้ไม่มีซับ | ไม่นับเป็น error ในหน้าจอ |
| `E_TRANSLATION_BLOCKED` | ยูทูปยังไม่ให้โหลดซับแปลอัตโนมัติในตอนนี้ เลือกซับภาษาต้นฉบับแทน | (M3) ยูทูปตอบ 429 เฉพาะคำขอซับแปล (`t.*` ลิงก์ `tlang`) ทั้งที่เซสชันผู้ชมอายุถึงแล้วและลองซ้ำหลัง 20 วินาทีแล้ว (owner round 3) ไม่ใช่การขอยืนยันว่าไม่ใช่บอท จึง**ไม่**เบรกฉุกเฉินและไม่พักคิว · หน้าเว็บไม่มีปุ่มลองใหม่และไม่ยิงซ้ำเมื่อสลับแท็บ มีปุ่ม "ใช้ซับภาษาต้นฉบับ" (เมื่อคลิปมีแทร็กเริ่มต้น) · ซับของเจ้าของคลิปและซับภาษาต้นฉบับที่โดน 429 ยังเป็น `E_BOT_CHECK` |
```
with:
```markdown
|---|---|---|
| `E_INVALID_INPUT` | ลิงก์นี้ไม่ใช่ลิงก์ยูทูป ลองคัดลอกจากแถบที่อยู่ของเบราว์เซอร์อีกครั้ง | ทำรายการอื่นต่อ |
| `E_BOT_CHECK` | ยูทูปขอให้ยืนยันว่าไม่ใช่บอท รอสัก 10 นาทีแล้วค่อยลองใหม่ | เบรกฉุกเฉิน · **ตั้งแต่ M4** (มีคิวแล้ว) เปลี่ยนข้อความเป็น "ยูทูปขอให้ยืนยันว่าไม่ใช่บอท พักคิวไว้ 10 นาทีก่อนนะ" และเบรกฉุกเฉิน · **งานที่เจอครั้งแรก (Q1, BRD #84)** กลับไปหัวคิวหนึ่งครั้ง (สถานะ `running → queued` ในธุรกรรมเดียว นับ `bot_checks` = 1) แล้วเริ่มเองเมื่อพักครบ · เจอซ้ำในงานเดียวกัน → งานล้มเหลวด้วย `E_BOT_CHECK` · ผู้ใช้กด "ลองใหม่" เองนับเป็นรอบใหม่ (ได้โอกาสอีกหนึ่งครั้ง) · **ตัดสินจากรหัส error เท่านั้น ไม่ดู HTTP status** · `E_TRANSLATION_BLOCKED`, `E_SESSION_WARMING` และรหัสอื่นไม่เบรก · เจอระหว่างพักอยู่ = ต่อเวลาพักออกไปอีก 10 นาที · "ลองต่อเลย" (`POST /queue/resume`) ปลดพักทันที · ส่ง `queue.paused` / `queue.resumed` ทาง SSE |
| `E_VIDEO_PRIVATE` | คลิปนี้เป็นส่วนตัวหรือเฉพาะสมาชิก ต้องเข้าสู่ระบบด้วยบัญชีที่มีสิทธิ์ดู | งานล้มเหลว · (M5 รอบ C) รวมคลิปเฉพาะสมาชิกของช่อง ("members-only content", "Join this channel to get access") · ยังไม่ได้ใช้บัญชี = ข้อความนี้พร้อมปุ่ม "ใช้บัญชียูทูปชั่วคราว" ที่ error ของหน้า W2 แถวงานในคิวกับ toast และ toast ของถ่ายภาพคม · มีบัญชีชั่วคราวอยู่ = ลองใหม่ด้วยบัญชี 1 ครั้งเอง (ดูหมายเหตุใต้ตาราง) |
| `E_VIDEO_UNAVAILABLE` | คลิปนี้ถูกลบหรือไม่มีแล้ว | งานล้มเหลว |
| `E_GEO_BLOCKED` | คลิปนี้ดูในประเทศไทยไม่ได้ | งานล้มเหลว |
| `E_AGE_RESTRICTED` | คลิปนี้จำกัดอายุ ต้องเข้าสู่ระบบยูทูปถึงจะเปิดได้ | งานล้มเหลว · (M5 รอบ C) ยังไม่ได้ใช้บัญชี = ข้อความนี้พร้อมปุ่ม "ใช้บัญชียูทูปชั่วคราว" แบบเดียวกับ `E_VIDEO_PRIVATE` · มีบัญชีชั่วคราวอยู่ = ลองใหม่ด้วยบัญชี 1 ครั้งเอง · ตัวเล่นฝังของ W2 ยังเล่นคลิปจำกัดอายุไม่ได้ (ใช้ "เปิดในยูทูป") |
| `E_LIVE_NOT_READY` | คลิปนี้ยังถ่ายทอดสดอยู่หรือยังไม่เผยแพร่ ลองใหม่หลังจบไลฟ์ | งานล้มเหลว |
| `E_NO_SUBTITLES` | คลิปนี้ไม่มีซับ | ไม่นับเป็น error ในหน้าจอ |
| `E_TRANSLATION_BLOCKED` | ยูทูปยังไม่ให้โหลดซับแปลอัตโนมัติในตอนนี้ เลือกซับภาษาต้นฉบับแทน | (M3) ยูทูปตอบ 429 เฉพาะคำขอซับแปล (`t.*` ลิงก์ `tlang`) ทั้งที่เซสชันผู้ชมอายุถึงแล้วและลองซ้ำหลัง 20 วินาทีแล้ว (owner round 3) ไม่ใช่การขอยืนยันว่าไม่ใช่บอท จึง**ไม่**เบรกฉุกเฉินและไม่พักคิว · หน้าเว็บไม่มีปุ่มลองใหม่และไม่ยิงซ้ำเมื่อสลับแท็บ มีปุ่ม "ใช้ซับภาษาต้นฉบับ" (เมื่อคลิปมีแทร็กเริ่มต้น) · ซับของเจ้าของคลิปและซับภาษาต้นฉบับที่โดน 429 ยังเป็น `E_BOT_CHECK` |
```

Replace (2):
```markdown
| `E_OUTPUT_NOT_WRITABLE` | บันทึกลงโฟลเดอร์นี้ไม่ได้ ลองเปลี่ยนโฟลเดอร์ในหน้าตั้งค่า | งานล้มเหลว |
| `E_INTERRUPTED` | งานหยุดกลางคันเพราะปิดโปรแกรม | รอผู้ใช้กดลองใหม่ (M4: ตอนเปิดโปรแกรมใหม่งาน `running` ที่ค้างกลายเป็น `interrupted` และล้างไฟล์ชั่วคราวของงานนั้น) |
| `E_JOB_STATE` | งานนี้เปลี่ยนสถานะไปแล้ว ลองรีเฟรชหน้าเว็บ | (M4) กดยกเลิกงานที่จบไปแล้ว หรือกด "ลองใหม่" กับงานที่ไม่ใช่ `failed` / `interrupted` (เช่น เปิดสองแท็บแล้วกดซ้ำ) · HTTP 409 · งานไม่เปลี่ยนแปลง |
| `E_COOKIES_INVALID` | ไฟล์นี้ไม่ใช่ cookies.txt หรือไม่มีคุกกี้ของยูทูป ลองส่งออกใหม่จากเบราว์เซอร์ที่ล็อกอินยูทูปไว้ | คงสถานะคุกกี้เดิม (M5) |
| `E_COOKIES_UNAVAILABLE` | อ่านคุกกี้จาก Firefox ไม่ได้ ตรวจว่าลง Firefox และล็อกอินยูทูปไว้แล้ว หรือเปลี่ยนไปใช้ไฟล์ cookies.txt | งานนั้นทำต่อแบบไม่ใช้คุกกี้ แถว "คุกกี้" ในหน้าตรวจสุขภาพเป็น `error` (M5) |
| `E_SETTINGS_INVALID` | ไฟล์นี้ไม่ใช่ไฟล์ค่าตั้งของ YT Toolkit หรือไฟล์เสียหาย ลองเลือกไฟล์ที่ได้จากปุ่ม "สำรองค่าตั้ง" | ไม่เปลี่ยนค่าตั้ง (M6) |
| `E_TOOL_INSTALL_FAILED` | โหลดโปรแกรมที่ต้องใช้ไม่สำเร็จ ตรวจเน็ตแล้วกด "โหลด ffmpeg ใหม่" อีกครั้ง | คงสถานะเดิม |
| `E_FORBIDDEN` | คำขอนี้ไม่ได้รับอนุญาต ลองรีเฟรชหน้าเว็บ | ตอบ 403 (NFR-SEC-3) |
```
with:
```markdown
| `E_OUTPUT_NOT_WRITABLE` | บันทึกลงโฟลเดอร์นี้ไม่ได้ ลองเปลี่ยนโฟลเดอร์ในหน้าตั้งค่า | งานล้มเหลว |
| `E_INTERRUPTED` | งานหยุดกลางคันเพราะปิดโปรแกรม | รอผู้ใช้กดลองใหม่ (M4: ตอนเปิดโปรแกรมใหม่งาน `running` ที่ค้างกลายเป็น `interrupted` และล้างไฟล์ชั่วคราวของงานนั้น) |
| `E_JOB_STATE` | งานนี้เปลี่ยนสถานะไปแล้ว ลองรีเฟรชหน้าเว็บ | (M4) กดยกเลิกงานที่จบไปแล้ว หรือกด "ลองใหม่" กับงานที่ไม่ใช่ `failed` / `interrupted` (เช่น เปิดสองแท็บแล้วกดซ้ำ) · HTTP 409 · งานไม่เปลี่ยนแปลง |
| `E_COOKIES_INVALID` | ไฟล์นี้ใช้ไม่ได้ ตรวจว่าเข้าสู่ระบบยูทูปแล้วก่อนส่งออก แล้วส่งออก cookies.txt ใหม่ | (M5 รอบ C) `POST /cookies/import`: ไฟล์ไม่ใช่รูปแบบ Netscape ใหญ่เกิน 1 MB (413) หรือไม่มีคุกกี้เข้าสู่ระบบของ `.youtube.com` (`SAPISID` / `__Secure-3PSID` / `LOGIN_INFO`) · HTTP 422 · บัญชีที่ถืออยู่เดิมไม่เปลี่ยน · `detail` บอกแค่ชนิดปัญหาและเลขบรรทัด ไม่ยกเนื้อไฟล์ · หน้าเว็บแสดงใต้ช่องเลือกไฟล์ใน dialog |
| `E_SETTINGS_INVALID` | ไฟล์นี้ไม่ใช่ไฟล์ค่าตั้งของ YT Toolkit หรือไฟล์เสียหาย ลองเลือกไฟล์ที่ได้จากปุ่ม "สำรองค่าตั้ง" | ไม่เปลี่ยนค่าตั้ง (M6) |
| `E_TOOL_INSTALL_FAILED` | โหลดโปรแกรมที่ต้องใช้ไม่สำเร็จ ตรวจเน็ตแล้วกด "โหลด ffmpeg ใหม่" อีกครั้ง | คงสถานะเดิม |
| `E_FORBIDDEN` | คำขอนี้ไม่ได้รับอนุญาต ลองรีเฟรชหน้าเว็บ | ตอบ 403 (NFR-SEC-3) |
```

Replace (3):
```markdown
| `E_NOT_FOUND` | ไม่พบสิ่งที่ขอ | ตอบ 404 (path ที่ไม่มีใน API) |
| `E_BAD_REQUEST` | ข้อมูลที่ส่งมาไม่ถูกต้อง ลองรีเฟรชหน้าเว็บ | ตอบ 422 (ข้อมูลไม่ผ่านการตรวจ) · HTTP error อื่นใช้ข้อความเดียวกันกับรหัส `E_HTTP_<status>` |

หมายเหตุ `E_AGE_RESTRICTED` / `E_VIDEO_PRIVATE`: ถ้าลองด้วยคุกกี้แล้วยังได้รหัสเดิม ใช้ข้อความ "ลองด้วยคุกกี้แล้วยังโหลดไม่ได้ คุกกี้อาจหมดอายุหรือบัญชีนี้ไม่มีสิทธิ์ดู ลองนำเข้าคุกกี้ใหม่" แทน

หมายเหตุ `E_NETWORK`: จุดที่ไม่ได้ลองใหม่อัตโนมัติ (เช่นหน้าผลลัพธ์ใน M2) ใช้ข้อความ "เน็ตหลุด ลองใหม่อีกครั้ง" แทน ข้อความที่มีตัวนับ (ครั้งที่ n/3) ใช้เมื่อคิวงานใน M4 เป็นผู้ลองใหม่ (หน้าเว็บสร้างข้อความนี้เองจาก `attempt` ของงาน)
```
with:
```markdown
| `E_NOT_FOUND` | ไม่พบสิ่งที่ขอ | ตอบ 404 (path ที่ไม่มีใน API) |
| `E_BAD_REQUEST` | ข้อมูลที่ส่งมาไม่ถูกต้อง ลองรีเฟรชหน้าเว็บ | ตอบ 422 (ข้อมูลไม่ผ่านการตรวจ) · HTTP error อื่นใช้ข้อความเดียวกันกับรหัส `E_HTTP_<status>` |

หมายเหตุ `E_AGE_RESTRICTED` / `E_VIDEO_PRIVATE` (M5 รอบ C): ถ้าลองด้วยบัญชีชั่วคราวแล้วยังได้รหัสเดิม ใช้ข้อความ "ลองด้วยบัญชีแล้วยังเปิดไม่ได้ บัญชีนี้อาจไม่มีสิทธิ์ดูคลิปนี้ หรือการเข้าสู่ระบบหมดอายุแล้ว ลองนำเข้าใหม่" แทน (รหัสเดิม HTTP status เดิม) และคงบัญชีไว้ เพราะบัญชีอาจแค่ไม่มีสิทธิ์ดูคลิปนี้

หมายเหตุ `E_NETWORK`: จุดที่ไม่ได้ลองใหม่อัตโนมัติ (เช่นหน้าผลลัพธ์ใน M2) ใช้ข้อความ "เน็ตหลุด ลองใหม่อีกครั้ง" แทน ข้อความที่มีตัวนับ (ครั้งที่ n/3) ใช้เมื่อคิวงานใน M4 เป็นผู้ลองใหม่ (หน้าเว็บสร้างข้อความนี้เองจาก `attempt` ของงาน)
```

In `tests/fixtures/README.md` (the `errors/` table):
Replace
```markdown
| `E_VIDEO_PRIVATE-3` | `'skip': 'This playlist is private'` ใน `extractor/youtube/_tab.py` ในรูป `YouTube said: ...` ของ `extractor/youtube/_base.py` |
```
with
```markdown
| `E_VIDEO_PRIVATE-3` | `'skip': 'This playlist is private'` ใน `extractor/youtube/_tab.py` ในรูป `YouTube said: ...` ของ `extractor/youtube/_base.py` |
| `E_VIDEO_PRIVATE-4` | (M5 รอบ C) **สังเคราะห์ ไม่ได้ probe จริง** (ไม่มีคลิปเฉพาะสมาชิกให้ทดสอบ): เหตุผลที่ยูทูปแสดงบนคลิปเฉพาะสมาชิก ("Join this channel to get access to members-only content like this video, and other exclusive perks.") ซึ่ง yt-dlp ส่งต่อทาง `raise_no_formats(reason)` ใน `extractor/youtube/_video.py` ในรูป `ERROR: [youtube] <id>: <reason>` |
| `E_VIDEO_PRIVATE-5` | (M5 รอบ C) **สังเคราะห์** แบบเดียวกับ `-4`: เหตุผลที่ระบุระดับสมาชิก ("This video is available to this channel's members on level: ...") ต่อด้วย `subreason` (". " + ประโยคเดียวกับ `-4`) ตามที่ `_video.py` ต่อ `reason += f'. {subreason}'` |
```

- [ ] **Step 5: Run the tests, expect PASS**

Run: `cd "$WORKTREE" && uv run pytest tests/unit/test_yterrors.py -q -W error -p no:cacheprovider` (all pass: both new fixtures classify as `E_VIDEO_PRIVATE`, every `MESSAGES` entry matches its PRD row, the tried note is in the PRD, no `E_COOKIES_UNAVAILABLE` row), then `cd "$WORKTREE" && uv run pytest -q -W error -p no:cacheprovider`.

- [ ] **Step 6: Commit**
```bash
cd "$WORKTREE" && git add src/yttoolkit/core/yterrors.py tests/unit/test_yterrors.py tests/fixtures/errors/E_VIDEO_PRIVATE-4.txt tests/fixtures/errors/E_VIDEO_PRIVATE-5.txt tests/fixtures/README.md PRD.md && git commit -F- <<'EOF'
feat(errors): M5-C account error copy, members-only rule and tried-with-account message

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
EOF
```

### Task 2: Log redaction installed at process start (`yttoolkit/redact.py`)

**Files:**
- Create: `src/yttoolkit/redact.py`
- Modify: `src/yttoolkit/probe.py` (`setup_file_log` adds the filters)
- Modify: `src/yttoolkit/api/errors.py` (re-export the moved helpers)
- Modify: `src/yttoolkit/lifecycle.py` (only: import from `redact`, remove the local `HomePathFilter`, `install_log_filters` adds `SecretFilter`, `serve()` adds redaction to the console handlers — the account wiring in this file is T9)
- Test: `tests/unit/test_redact.py` (new)

**Interfaces:**
- Consumes: `redact_home` / `_home_aliases` (`api/errors.py:23-49`), `HomePathFilter` (`lifecycle.py:114-137`), `setup_file_log` (`probe.py:64`), `install_log_filters` / `setup_file_logging` (`lifecycle.py:165-175`).
- Produces: C2 exactly. T9 and T13 rely on `SecretFilter` being on `app.log` from the first line.

- [ ] **Step 1: Write the failing test** — create `tests/unit/test_redact.py`:
```python
"""ตัวซ่อนข้อมูลส่วนตัวใน log (yttoolkit.redact · M5 รอบ C spec 3): ค่าคุกกี้และโฟลเดอร์ผู้ใช้ ตั้งแต่บรรทัดแรกของ app.log"""

from __future__ import annotations

import logging
import logging.handlers
import subprocess
import sys
from pathlib import Path

import pytest

from yttoolkit import lifecycle, probe, redact
from yttoolkit.api import errors
from yttoolkit.redact import MASK, HomePathFilter, SecretFilter, add_redaction, redact_secrets

CANARY = "canary-7f3a9e"


@pytest.fixture
def restore_root_logging():
    root = logging.getLogger()
    before = list(root.handlers)
    level = root.level
    yield root
    for h in list(root.handlers):
        if h not in before:
            root.removeHandler(h)
            h.close()
    root.setLevel(level)


@pytest.mark.parametrize(
    "text",
    [
        f"Cookie: SAPISID={CANARY}; PREF=f6=8",
        f"set-cookie: __Secure-3PSID={CANARY}; Path=/; Secure",
        f"headers={{'Cookie': 'LOGIN_INFO={CANARY}; x=1', 'User-Agent': 'ua'}}",
        f".youtube.com\tTRUE\t/\tTRUE\t1999999999\tSAPISID\t{CANARY}",
        f"#HttpOnly_.youtube.com\tTRUE\t/\tTRUE\t1999999999\t__Secure-1PSIDTS\t{CANARY}",
        f'{{"SID": "{CANARY}"}}',
        f"jar has SSID={CANARY},HSID={CANARY}",
    ],
)
def test_secret_values_are_masked(text: str) -> None:
    out = redact_secrets(text)
    assert CANARY not in out
    assert MASK in out


def test_other_text_is_left_alone() -> None:
    for text in (
        "probe aqz-KE-bpKQ: 200 OK",
        "Extracting cookies from firefox",
        "VISITOR_INFO1_LIVE expired",  # คุกกี้ผู้ชมแบบไม่ระบุตัวตน ไม่ใช่การเข้าสู่ระบบ
        "PSID=1 is not a sign-in name, nor is XSAPISID=2",
    ):
        assert redact_secrets(text) == text


def _format(record: logging.LogRecord, *filters: logging.Filter) -> str:
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("%(message)s"))
    for f in filters:
        handler.addFilter(f)
    assert handler.filter(record)
    return handler.format(record)


def test_secret_filter_masks_args_and_traceback() -> None:
    try:
        raise RuntimeError(f"request failed with Cookie: SAPISID={CANARY}")
    except RuntimeError:
        exc_info = sys.exc_info()
    record = logging.LogRecord(
        "yttoolkit", logging.ERROR, __file__, 1, "ส่ง %s ไม่ได้", (f"SID={CANARY}",), exc_info
    )
    text = _format(record, SecretFilter())
    assert CANARY not in text
    assert "Traceback" in text and "RuntimeError" in text


def test_home_filter_moved_but_keeps_its_old_names() -> None:
    assert lifecycle.HomePathFilter is HomePathFilter
    assert errors.redact_home is redact.redact_home
    assert errors._home_aliases is redact._home_aliases
    home = str(Path.home())
    record = logging.LogRecord("yttoolkit", logging.INFO, __file__, 1, "เปิด %s", (f"{home}\\x.mp4",), None)
    assert _format(record, HomePathFilter()) == "เปิด ~\\x.mp4"


def test_add_redaction_is_idempotent() -> None:
    handler = logging.StreamHandler()
    add_redaction(handler)
    add_redaction(handler)
    kinds = [type(f) for f in handler.filters]
    assert kinds.count(HomePathFilter) == 1 and kinds.count(SecretFilter) == 1


def test_app_log_hides_a_secret_written_before_lifecycle_loads(paths, restore_root_logging) -> None:
    # สิ่งที่ __main__ ทำเป็นอย่างแรก (ก่อน import lifecycle): ตัวกรองต้องอยู่แล้ว
    probe.setup_file_log(paths)
    added = [h for h in restore_root_logging.handlers if isinstance(h, logging.handlers.RotatingFileHandler)
             and h.baseFilename == str((paths.logs / "app.log").resolve())]  # fmt: skip
    assert len(added) == 1
    assert {type(f) for f in added[0].filters} >= {HomePathFilter, SecretFilter}
    logging.getLogger("yttoolkit").error("เปิดโปรแกรมไม่สำเร็จ: Cookie: SAPISID=%s home=%s", CANARY, Path.home())
    added[0].flush()
    text = (paths.logs / "app.log").read_text(encoding="utf-8")
    assert "เปิดโปรแกรมไม่สำเร็จ" in text
    assert CANARY not in text and str(Path.home()) not in text


def test_lifecycle_adds_the_secret_filter_once(paths, restore_root_logging) -> None:
    probe.setup_file_log(paths)
    lifecycle.setup_file_logging(paths)
    lifecycle.setup_file_logging(paths)
    handler = next(h for h in restore_root_logging.handlers if isinstance(h, logging.handlers.RotatingFileHandler)
                   and h.baseFilename == str((paths.logs / "app.log").resolve()))  # fmt: skip
    assert [type(f) for f in handler.filters].count(SecretFilter) == 1


def test_redact_module_does_not_load_the_web_stack() -> None:
    code = (
        "import sys, yttoolkit.redact\n"
        "print(','.join(sorted({'httpx', 'fastapi', 'uvicorn', 'starlette'} & set(sys.modules))))\n"
    )
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=60, check=True)
    assert out.stdout.strip() == ""
```

- [ ] **Step 2: Run it, expect FAIL**

Run: `cd "$WORKTREE" && uv run pytest tests/unit/test_redact.py -q -W error -p no:cacheprovider`
Expected: `ImportError: cannot import name 'redact' from 'yttoolkit'` (collection error).

- [ ] **Step 3: Create `src/yttoolkit/redact.py`**
```python
"""ตัวซ่อนข้อมูลส่วนตัวในข้อความ log / error (stdlib ล้วน: probe ใช้ได้ก่อนโหลดเว็บ)

- redact_home: แทนโฟลเดอร์ผู้ใช้ด้วย ~ (ชื่อผู้ใช้ Windows ห้ามหลุดไปกับ log หรือภาพหน้าจอ)
- redact_secrets (M5 รอบ C): ปิดค่าของ header Cookie / Set-Cookie และค่าของคุกกี้เข้าสู่ระบบของยูทูป
  เป็นตาข่ายกันพลาดชั้นสุดท้าย โค้ดของแอพไม่ log ค่าพวกนี้อยู่แล้ว
- HomePathFilter / SecretFilter: ตัวกรองของ logging.Handler ที่ใช้สองตัวข้างบน (ข้อความ + traceback)
  probe.setup_file_log ใส่ให้ app.log ตั้งแต่สร้าง handler (ก่อนโหลด lifecycle) จึงครอบความล้มเหลวตอนเปิดโปรแกรมด้วย
"""

from __future__ import annotations

import functools
import logging
import re
from pathlib import Path

MASK = "<hidden>"
# คุกกี้เข้าสู่ระบบของ Google/ยูทูปที่รู้จัก (เก็บแค่ชื่อ ค่าถูกแทนด้วย MASK)
SIGN_IN_COOKIE_NAMES = (
    "SAPISID",
    "APISID",
    "HSID",
    "SID",
    "SSID",
    "SIDCC",
    "LOGIN_INFO",
    "__Secure-1PSID",
    "__Secure-3PSID",
    "__Secure-1PAPISID",
    "__Secure-3PAPISID",
    "__Secure-1PSIDTS",
    "__Secure-3PSIDTS",
    "__Secure-1PSIDCC",
    "__Secure-3PSIDCC",
)
# Cookie: a=b · Set-Cookie: a=b · 'Cookie': 'a=b' (repr ของ dict header) ปิดค่าถึงท้ายบรรทัดหรืออัญประกาศ
_HEADER = re.compile(r"(?i)(\b(?:set-)?cookie['\"]?\s*:\s*['\"]?)[^\r\n'\"]*")
# SAPISID=abc · SAPISID<TAB>abc (บรรทัดของ cookies.txt) · "SAPISID": "abc" · ไม่จับชื่อที่เป็นส่วนของชื่ออื่น
_NAMES = "|".join(re.escape(n) for n in sorted(SIGN_IN_COOKIE_NAMES, key=len, reverse=True))
_NAMED = re.compile(rf"(?<![A-Za-z0-9_-])({_NAMES})(['\"]?(?:\s*[=:]\s*|\t+)['\"]?)([^\s;,'\"]+)")


def redact_secrets(text: str) -> str:
    """ปิดค่าคุกกี้ใน text: header Cookie / Set-Cookie ทั้งค่า และค่าของคุกกี้เข้าสู่ระบบที่รู้จักชื่อ"""
    text = _HEADER.sub(lambda m: f"{m.group(1)}{MASK}", text)
    return _NAMED.sub(lambda m: f"{m.group(1)}{m.group(2)}{MASK}", text)


@functools.cache
def _home_aliases(home: str) -> tuple[str, ...]:
    """ชื่ออื่นของโฟลเดอร์ผู้ใช้ (Windows: ชื่อสั้นแบบ 8.3 เช่น SOMCHA~1) หาครั้งเดียวแล้วจำไว้"""
    from .platform import current

    try:
        return tuple(current().path_aliases(Path(home)))
    except (OSError, RuntimeError):
        return ()


def redact_home(text: str) -> str:
    """แทนโฟลเดอร์ผู้ใช้ด้วย ~ เพื่อไม่ให้ชื่อผู้ใช้หลุดไปกับภาพหน้าจอที่ส่งต่อ"""
    home = str(Path.home())
    if not home.strip("/\\"):
        return text
    # แบบปกติ, แบบ / และแบบ backslash สองตัว (มาจาก repr เช่น str(OSError) บน Windows) ทั้งชื่อเต็มและชื่อสั้น
    variants = {
        form
        for name in (home, *_home_aliases(home))
        for form in (name, name.replace("\\", "/"), name.replace("\\", "\\\\"))
    }
    # รวมเป็น regex เดียว เรียงยาวก่อน จึงไม่มีแบบไหนไปจับแค่บางส่วนของอีกแบบ
    alternatives = "|".join(re.escape(v) for v in sorted(variants, key=len, reverse=True))
    # ไม่แตะโฟลเดอร์ข้างเคียงที่ชื่อขึ้นต้นเหมือนกัน เช่น C:\Users\Som กับ C:\Users\Somchai
    # ผลข้างเคียงที่ตั้งใจ: home ที่ตามด้วยจุดทันที (เช่นท้ายประโยค) จะไม่ถูกแทน เพราะจุดเป็นส่วนของชื่อโฟลเดอร์ได้
    return re.sub(f"(?:{alternatives})" + r"(?![\w.\-])", "~", text, flags=re.IGNORECASE)


class _RewriteFilter(logging.Filter):
    """แก้ข้อความ log (รวม args) traceback และ stack ด้วย rewrite ก่อนเขียน"""

    _formatter = logging.Formatter()

    def rewrite(self, text: str) -> str:
        raise NotImplementedError

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            message = record.getMessage()
        except Exception:
            return True  # ข้อความจัดรูปไม่ได้ ปล่อยให้ logging รายงานตามปกติ
        record.msg = self.rewrite(message)
        record.args = None
        if record.exc_info and not record.exc_text:
            record.exc_text = self._formatter.formatException(record.exc_info)
        if record.exc_text:
            record.exc_text = self.rewrite(record.exc_text)
        if record.stack_info:
            record.stack_info = self.rewrite(record.stack_info)
        return True


class HomePathFilter(_RewriteFilter):
    """แทนโฟลเดอร์ผู้ใช้ด้วย ~ ในข้อความ log และ traceback ก่อนเขียนลงไฟล์

    log.exception ของคิวงานและ lifecycle อาจมี path เต็ม ซึ่งมีชื่อผู้ใช้ Windows ติดไปกับไฟล์ log ที่ส่งต่อ
    """

    def rewrite(self, text: str) -> str:
        return redact_home(text)


class SecretFilter(_RewriteFilter):
    """ปิดค่าคุกกี้ (header Cookie / Set-Cookie และคุกกี้เข้าสู่ระบบของยูทูป) ในข้อความ log และ traceback"""

    def rewrite(self, text: str) -> str:
        return redact_secrets(text)


def add_redaction(handler: logging.Handler) -> None:
    """ใส่ HomePathFilter และ SecretFilter ให้ handler (เรียกซ้ำได้ ไม่ใส่ซ้ำ)"""
    for kind in (HomePathFilter, SecretFilter):
        if not any(isinstance(f, kind) for f in handler.filters):
            handler.addFilter(kind())
```

- [ ] **Step 4: Wire it into `probe.py`, `api/errors.py` and `lifecycle.py`**

`src/yttoolkit/probe.py`:
Replace (1):
```python
from . import runstate
from .config import HOST, Paths, default_paths
from .platform import Platform, current

PING_TIMEOUT = 2
```
with:
```python
from . import runstate
from .config import HOST, Paths, default_paths
from .platform import Platform, current
from .redact import add_redaction

PING_TIMEOUT = 2
```

Replace (2):
```python
    target = os.path.abspath(filename)
    for existing in root.handlers:
        if isinstance(existing, logging.handlers.RotatingFileHandler) and existing.baseFilename == target:
            return
    handler = logging.handlers.RotatingFileHandler(filename, maxBytes=1_000_000, backupCount=3, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    root.addHandler(handler)
```
with:
```python
    target = os.path.abspath(filename)
    for existing in root.handlers:
        if isinstance(existing, logging.handlers.RotatingFileHandler) and existing.baseFilename == target:
            add_redaction(existing)
            return
    handler = logging.handlers.RotatingFileHandler(filename, maxBytes=1_000_000, backupCount=3, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    # M5 รอบ C: ซ่อนโฟลเดอร์ผู้ใช้และค่าคุกกี้ตั้งแต่สร้าง handler (ก่อนโหลด lifecycle) ไม่มีบรรทัดไหนหลุดก่อนตั้ง log
    add_redaction(handler)
    root.addHandler(handler)
```

`src/yttoolkit/api/errors.py` (the helpers move to `redact.py`; the old names stay importable; keep `from pathlib import Path` because existing tests patch `errors.Path.home`, which is the same class `redact.py` uses):
Replace (1):
```python
from __future__ import annotations

import functools
import logging
import re
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
```
with:
```python
from __future__ import annotations

import logging
from pathlib import Path  # noqa: F401  เทสเดิมแก้ errors.Path.home (คลาสเดียวกับที่ redact.py ใช้)

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
```

Replace (2):
```python
from starlette.exceptions import HTTPException

from ..core.yterrors import MESSAGES

log = logging.getLogger("yttoolkit")
```
with:
```python
from starlette.exceptions import HTTPException

from ..core.yterrors import MESSAGES
from ..redact import _home_aliases, redact_home  # noqa: F401  ย้ายไป redact.py (M5 รอบ C) ชื่อเดิมยังใช้ได้

log = logging.getLogger("yttoolkit")
```

Replace (3):
```python
BAD_REQUEST_MESSAGE = "ข้อมูลที่ส่งมาไม่ถูกต้อง ลองรีเฟรชหน้าเว็บ"
UNKNOWN_MESSAGE = MESSAGES["E_UNKNOWN"]
VALIDATION_DETAIL_MAX = 500


@functools.cache
def _home_aliases(home: str) -> tuple[str, ...]:
    """ชื่ออื่นของโฟลเดอร์ผู้ใช้ (Windows: ชื่อสั้นแบบ 8.3 เช่น SOMCHA~1) หาครั้งเดียวแล้วจำไว้"""
    from ..platform import current

    try:
        return tuple(current().path_aliases(Path(home)))
    except (OSError, RuntimeError):
        return ()


def redact_home(text: str) -> str:
    """แทนโฟลเดอร์ผู้ใช้ด้วย ~ เพื่อไม่ให้ชื่อผู้ใช้หลุดไปกับภาพหน้าจอที่ส่งต่อ"""
    home = str(Path.home())
    if not home.strip("/\\"):
        return text
    # แบบปกติ, แบบ / และแบบ backslash สองตัว (มาจาก repr เช่น str(OSError) บน Windows) ทั้งชื่อเต็มและชื่อสั้น
    variants = {
        form
        for name in (home, *_home_aliases(home))
        for form in (name, name.replace("\\", "/"), name.replace("\\", "\\\\"))
    }
    # รวมเป็น regex เดียว เรียงยาวก่อน จึงไม่มีแบบไหนไปจับแค่บางส่วนของอีกแบบ
    alternatives = "|".join(re.escape(v) for v in sorted(variants, key=len, reverse=True))
    # ไม่แตะโฟลเดอร์ข้างเคียงที่ชื่อขึ้นต้นเหมือนกัน เช่น C:\Users\Som กับ C:\Users\Somchai
    # ผลข้างเคียงที่ตั้งใจ: home ที่ตามด้วยจุดทันที (เช่นท้ายประโยค) จะไม่ถูกแทน เพราะจุดเป็นส่วนของชื่อโฟลเดอร์ได้
    return re.sub(f"(?:{alternatives})" + r"(?![\w.\-])", "~", text, flags=re.IGNORECASE)


# ชื่อเดิม (ก่อน M4) ยังใช้อยู่ในโมดูลอื่น
```
with:
```python
BAD_REQUEST_MESSAGE = "ข้อมูลที่ส่งมาไม่ถูกต้อง ลองรีเฟรชหน้าเว็บ"
UNKNOWN_MESSAGE = MESSAGES["E_UNKNOWN"]
VALIDATION_DETAIL_MAX = 500


# ชื่อเดิม (ก่อน M4) ยังใช้อยู่ในโมดูลอื่น
```

`src/yttoolkit/lifecycle.py`:
Replace (1):
```python

# ตัวจริงอยู่ใน probe (stdlib ล้วน) ที่นี่ส่งต่อชื่อเดิมให้โค้ดและเทสที่เรียกผ่าน lifecycle
from .probe import base_url, find_running, is_alive, setup_file_log  # noqa: F401

log = logging.getLogger("yttoolkit")
```
with:
```python

# ตัวจริงอยู่ใน probe (stdlib ล้วน) ที่นี่ส่งต่อชื่อเดิมให้โค้ดและเทสที่เรียกผ่าน lifecycle
from .probe import base_url, find_running, is_alive, setup_file_log  # noqa: F401
from .redact import HomePathFilter, SecretFilter, add_redaction

log = logging.getLogger("yttoolkit")
```

Replace (2):
```python
    return out.stdout.strip() or None


class HomePathFilter(logging.Filter):
    """แทนโฟลเดอร์ผู้ใช้ด้วย ~ ในข้อความ log และ traceback ก่อนเขียนลงไฟล์

    log.exception ของคิวงานและ lifecycle อาจมี path เต็ม ซึ่งมีชื่อผู้ใช้ Windows ติดไปกับไฟล์ log ที่ส่งต่อ
    """

    _formatter = logging.Formatter()

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            message = record.getMessage()
        except Exception:
            return True  # ข้อความจัดรูปไม่ได้ ปล่อยให้ logging รายงานตามปกติ
        record.msg = redact_home(message)
        record.args = None
        if record.exc_info and not record.exc_text:
            record.exc_text = self._formatter.formatException(record.exc_info)
        if record.exc_text:
            record.exc_text = redact_home(record.exc_text)
        if record.stack_info:
            record.stack_info = redact_home(record.stack_info)
        return True


class ConnectionResetNoiseFilter(logging.Filter):
    """ทิ้งเฉพาะรายงาน ConnectionResetError ของ asyncio ตอนปิดการเชื่อมต่อ (_call_connection_lost)
```
with:
```python
    return out.stdout.strip() or None


class ConnectionResetNoiseFilter(logging.Filter):
    """ทิ้งเฉพาะรายงาน ConnectionResetError ของ asyncio ตอนปิดการเชื่อมต่อ (_call_connection_lost)
```

Replace (3):
```python


def install_log_filters(paths: Paths) -> None:
    """ใส่ HomePathFilter และ ConnectionResetNoiseFilter ให้ handler ของ app.log ที่ตั้งไว้แล้ว (เรียกซ้ำได้ ไม่ใส่ซ้ำ)"""
    for handler in _app_log_handlers(paths):
        for kind in (ConnectionResetNoiseFilter, HomePathFilter):
            if not any(isinstance(f, kind) for f in handler.filters):
                handler.addFilter(kind())
```
with:
```python


def install_log_filters(paths: Paths) -> None:
    """ใส่ ConnectionResetNoiseFilter, HomePathFilter และ SecretFilter ให้ handler ของ app.log ที่ตั้งไว้แล้ว
    (เรียกซ้ำได้ ไม่ใส่ซ้ำ · probe.setup_file_log ใส่สองตัวหลังไว้ตั้งแต่สร้าง handler แล้ว)"""
    for handler in _app_log_handlers(paths):
        for kind in (ConnectionResetNoiseFilter, HomePathFilter, SecretFilter):
            if not any(isinstance(f, kind) for f in handler.filters):
                handler.addFilter(kind())
```

Replace (4):
```python
    plat = current()
    paths.ensure()
    logging.basicConfig(level=logging.INFO)
    prepare_environment()
    try:
        lock = plat.try_lock(paths.run / "app.lock")
```
with:
```python
    plat = current()
    paths.ensure()
    logging.basicConfig(level=logging.INFO)
    for handler in logging.getLogger().handlers:  # M5 รอบ C: log ของ serve (stderr) ก็ซ่อนโฟลเดอร์ผู้ใช้และค่าคุกกี้
        add_redaction(handler)
    prepare_environment()
    try:
        lock = plat.try_lock(paths.run / "app.lock")
```

- [ ] **Step 5: Run the tests, expect PASS**

Run: `cd "$WORKTREE" && uv run pytest tests/unit/test_redact.py tests/unit/test_lifecycle.py tests/api/test_errors.py -q -W error -p no:cacheprovider`, then the full suite `cd "$WORKTREE" && uv run pytest -q -W error -p no:cacheprovider`.

- [ ] **Step 6: Commit**
```bash
cd "$WORKTREE" && git add src/yttoolkit/redact.py src/yttoolkit/probe.py src/yttoolkit/api/errors.py src/yttoolkit/lifecycle.py tests/unit/test_redact.py && git commit -F- <<'EOF'
feat(log): M5-C mask cookie values in logs from the first app.log line

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
EOF
```

### Task 3: In-memory account service and the queue listener

**Files:**
- Create: `src/yttoolkit/core/account_session.py`
- Modify: `src/yttoolkit/core/queue.py` (`QueueListener`, `QueueRunner.listener`, notify calls)
- Test: `tests/unit/test_account_session.py` (new), `tests/unit/test_queue.py` (append)

**Interfaces:**
- Consumes: `YtError` (`core/yterrors.py`); `QueueRunner.enqueue/retry/cancel/_end/tick`, `pending_count` (`core/queue.py:261-527`); the `runner_factory` fixture and `jobs_of` helper of `test_queue.py`.
- Produces: C3 exactly. The service takes the parser as an argument (no `yt_dlp` here); T7 builds it with `parse_account_cookies` in tests, T9 in `open_services`.

- [ ] **Step 1: Write the failing tests** — create `tests/unit/test_account_session.py`:
```python
"""บัญชียูทูปชั่วคราว (core/account_session.py · M5 รอบ C spec 2.1-2.2): สถานะ เวลาลบเอง และ grace ของคิว

ใช้นาฬิกาและตัวตั้งเวลาปลอม (ไม่รอเวลาจริง) และตัวอ่านไฟล์ปลอม (ไม่แตะ yt-dlp)
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime, timedelta

import pytest

from yttoolkit.core.account_session import EXPIRY_S, GRACE_S, MAX_IMPORT_BYTES, AccountService
from yttoolkit.core.yterrors import YtError

T0 = datetime(2026, 10, 6, 3, 0, tzinfo=UTC)
GOOD = "# Netscape HTTP Cookie File\n.youtube.com\tTRUE\t/\tTRUE\t0\tSAPISID\tvalue-1\n"


class FakeJar:
    def __init__(self, text: str) -> None:
        self.text = text


def fake_parse(text: str) -> FakeJar:
    if "bad" in text:
        raise YtError("E_COOKIES_INVALID", "line 1: expected 7 tab-separated fields")
    return FakeJar(text)


class Clock:
    """นาฬิกาปลอม + ตัวตั้งเวลาปลอม: advance(s) เดินเวลาแล้วเรียกงานที่ถึงเวลาตามลำดับ"""

    def __init__(self) -> None:
        self.now = T0
        self.timers: list[tuple[datetime, Callable[[], None]]] = []

    def __call__(self) -> datetime:
        return self.now

    def schedule(self, delay: float, fn: Callable[[], None]) -> None:
        self.timers.append((self.now + timedelta(seconds=delay), fn))

    def advance(self, seconds: float) -> None:
        self.now += timedelta(seconds=seconds)
        due = sorted((t for t in self.timers if t[0] <= self.now), key=lambda t: t[0])
        self.timers = [t for t in self.timers if t[0] > self.now]
        for _, fn in due:
            fn()


class Env:
    def __init__(self) -> None:
        self.clock = Clock()
        self.events: list[tuple[str, dict]] = []
        self.busy = False
        self.cleared = 0

        def on_clear() -> None:
            self.cleared += 1

        self.service = AccountService(
            fake_parse,
            publish=lambda name, data: self.events.append((name, data)),
            busy=lambda: self.busy,
            on_clear=on_clear,
            now=self.clock,
            schedule=self.clock.schedule,
        )

    def last(self) -> dict:
        name, data = self.events[-1]
        assert name == "account"
        return data


@pytest.fixture
def env() -> Env:
    return Env()


def _iso(moment: datetime) -> str:
    return moment.isoformat(timespec="seconds")


def test_nothing_held_at_start(env: Env) -> None:
    assert env.service.status() == {"active": False, "used": False}
    assert env.service.jar() is None


def test_import_holds_the_jar_and_reports_times_only(env: Env) -> None:
    status = env.service.import_text(GOOD)
    expires = _iso(T0 + timedelta(seconds=EXPIRY_S))
    assert status == {"active": True, "importedAt": _iso(T0), "expiresAt": expires, "used": False}
    assert env.service.status() == status
    assert isinstance(env.service.jar(), FakeJar)
    assert env.events == [("account", {"active": True, "expiresAt": expires})]
    assert "value-1" not in repr(status) and "SAPISID" not in repr(env.events)


def test_oversize_text_is_rejected_before_parsing(env: Env) -> None:
    calls: list[str] = []
    service = AccountService(lambda text: calls.append(text) or FakeJar(text))
    with pytest.raises(YtError) as info:
        service.import_text("#" * (MAX_IMPORT_BYTES + 1))
    assert info.value.code == "E_COOKIES_INVALID"
    assert calls == [] and service.jar() is None


def test_a_bad_file_keeps_the_held_account(env: Env) -> None:
    env.service.import_text(GOOD)
    held = env.service.jar()
    with pytest.raises(YtError) as info:
        env.service.import_text("bad file")
    assert info.value.code == "E_COOKIES_INVALID"
    assert env.service.jar() is held
    assert len(env.events) == 1


def test_expires_two_hours_after_import(env: Env) -> None:
    env.service.import_text(GOOD)
    env.clock.advance(EXPIRY_S - 1)
    assert env.service.status()["active"] is True
    env.clock.advance(1)
    assert env.service.status() == {"active": False, "used": False}
    assert env.last() == {"active": False, "reason": "expired"}
    assert env.cleared == 1


def test_reimport_replaces_the_account_and_restarts_the_clock(env: Env) -> None:
    env.service.import_text(GOOD)
    env.clock.advance(3600)
    env.service.import_text(GOOD + "\n")
    assert env.cleared == 1  # ข้อมูลที่ได้มาด้วยบัญชีเดิมถูกทิ้ง
    env.clock.advance(3601)  # ครบ 2 ชม. ของรอบแรกแล้ว แต่รอบแรกถูกแทนไป
    assert env.service.status()["active"] is True
    env.clock.advance(EXPIRY_S - 3601)
    assert env.service.status()["active"] is False
    assert env.last()["reason"] == "expired"


def test_grace_starts_when_a_job_that_used_the_account_ends_and_the_queue_is_idle(env: Env) -> None:
    env.service.import_text(GOOD)
    env.service.mark_used("job-1")
    env.clock.advance(60)
    env.service.job_ended("job-1")
    grace_end = _iso(env.clock.now + timedelta(seconds=GRACE_S))
    assert env.service.status()["expiresAt"] == grace_end
    assert env.service.status()["used"] is True
    assert env.last() == {"active": True, "expiresAt": grace_end}
    env.clock.advance(GRACE_S)
    assert env.service.status()["active"] is False
    assert env.last() == {"active": False, "reason": "queue_done"}


def test_no_grace_while_the_queue_still_has_work(env: Env) -> None:
    env.service.import_text(GOOD)
    env.service.mark_used("job-1")
    env.busy = True  # มีงานรอคิว (รวมคิวที่พักเพราะยูทูปขอตรวจสอบ) หรือกำลังทำอยู่
    env.service.job_ended("job-1")
    env.clock.advance(GRACE_S + 1)
    assert env.service.status()["active"] is True
    env.busy = False
    env.service.job_ended("job-2")  # งานสุดท้ายจบ (ไม่ได้ใช้บัญชี) คิวว่างแล้ว
    env.clock.advance(GRACE_S)
    assert env.service.status()["active"] is False


def test_a_new_job_cancels_the_grace(env: Env) -> None:
    env.service.import_text(GOOD)
    env.service.mark_used("job-1")
    env.service.job_ended("job-1")
    env.clock.advance(GRACE_S - 1)
    env.service.job_queued()
    assert env.last() == {"active": True, "expiresAt": _iso(T0 + timedelta(seconds=EXPIRY_S))}
    env.clock.advance(5)
    assert env.service.status()["active"] is True
    env.service.job_ended("job-2")  # งานใหม่จบ คิวว่างอีกครั้ง: นับ grace ใหม่
    env.clock.advance(GRACE_S)
    assert env.service.status()["active"] is False


def test_interactive_use_never_starts_the_grace(env: Env) -> None:
    env.service.import_text(GOOD)
    env.service.mark_used(None)  # หน้า W2 หรือถ่ายภาพคมใช้บัญชี
    env.service.job_ended("job-1")  # งานอื่นที่ไม่ได้ใช้บัญชีจบ
    env.clock.advance(GRACE_S + 1)
    status = env.service.status()
    assert status["active"] is True and status["used"] is True


def test_a_job_that_did_not_use_the_account_does_not_start_the_grace(env: Env) -> None:
    env.service.import_text(GOOD)
    env.service.job_ended("job-1")
    env.clock.advance(GRACE_S + 1)
    assert env.service.status()["active"] is True


def test_manual_clear_and_shutdown(env: Env) -> None:
    env.service.import_text(GOOD)
    env.service.mark_used("job-1")
    assert env.service.clear("manual") == {"active": False, "used": False}
    assert env.last() == {"active": False, "reason": "manual"}
    env.service.job_ended("job-1")  # งานที่ใช้บัญชีเก่าจบหลังลบ: ไม่มีอะไรเกิดขึ้น
    assert env.service.jar() is None
    env.service.import_text(GOOD)
    env.service.clear("shutdown")
    assert env.last() == {"active": False, "reason": "shutdown"}
    assert env.cleared == 2


def test_clear_without_an_account_is_silent(env: Env) -> None:
    assert env.service.clear("manual") == {"active": False, "used": False}
    assert env.events == [] and env.cleared == 0
    with pytest.raises(ValueError):
        env.service.clear("because")


def test_stale_timers_after_clear_do_nothing(env: Env) -> None:
    env.service.import_text(GOOD)
    env.service.mark_used("job-1")
    env.service.job_ended("job-1")
    env.service.clear("manual")
    env.service.import_text(GOOD)
    env.clock.advance(GRACE_S)  # grace ของบัญชีก่อนหน้าครบเวลา
    assert env.service.status()["active"] is True


def test_listener_errors_never_break_the_service() -> None:
    def boom(*_args: object) -> None:
        raise RuntimeError("bus closed")

    service = AccountService(fake_parse, publish=boom, on_clear=boom)
    assert service.import_text(GOOD)["active"] is True
    assert service.clear("manual")["active"] is False
```

Append to `tests/unit/test_queue.py`:
Replace (1):
```python
    r.tick()
    spawn.run_all()
    assert (r.store.get(job.id).status, r.store.get(job.id).error_code) == ("failed", "E_UNKNOWN")
```
with:
```python
    r.tick()
    spawn.run_all()
    assert (r.store.get(job.id).status, r.store.get(job.id).error_code) == ("failed", "E_UNKNOWN")


# ---------- M5 รอบ C: ผู้ฟังคิว (grace ของบัญชียูทูปชั่วคราว) ----------


class RecordingListener:
    """จดทุกครั้งที่คิวแจ้ง: ("queued",) / ("ended", job_id, สถานะในฐานข้อมูลตอนนั้น, จำนวนงานค้าง, ถือล็อกคิวอยู่ไหม)"""

    def __init__(self, runner) -> None:
        self.runner = runner
        self.calls: list[tuple] = []

    def job_queued(self) -> None:
        self.calls.append(("queued", self.runner._lock._is_owned()))

    def job_ended(self, job_id: str) -> None:
        job = self.runner.store.get(job_id)
        self.calls.append(("ended", job_id, job.status, self.runner.pending_count(), self.runner._lock._is_owned()))


def test_listener_hears_enqueue_and_retry_once_per_call(runner_factory):
    r, spawn, h = runner_factory(concurrency=1, fail={"vid00000001": "E_YT_REFUSED"})
    heard = r.listener = RecordingListener(r)
    a, _b = r.enqueue(jobs_of("frames_zip", 2))
    assert heard.calls == [("queued", False)]
    r.tick()
    spawn.run_all()
    heard.calls.clear()
    r.retry(a.id)
    assert heard.calls == [("queued", False)]


def test_listener_hears_every_final_state_after_it_is_stored(runner_factory):
    r, spawn, h = runner_factory(concurrency=2, fail={"vid00000002": "E_YT_REFUSED"})
    heard = r.listener = RecordingListener(r)
    a, b, c = r.enqueue(jobs_of("frames_zip", 3))
    r.cancel(c.id)
    r.tick()
    spawn.run_all()
    ended = [call[1:] for call in heard.calls if call[0] == "ended"]
    # c ยกเลิกตอนรอคิว (a, b ยังรอ) · a เสร็จตอน b ยังทำอยู่ · b จบเป็นงานสุดท้าย · ไม่มีครั้งไหนถือล็อกคิว
    assert ended == [(c.id, "cancelled", 2, False), (a.id, "done", 1, False), (b.id, "failed", 0, False)]


def test_last_job_ends_with_an_empty_queue(runner_factory):
    r, spawn, h = runner_factory(concurrency=1)
    heard = r.listener = RecordingListener(r)
    (job,) = r.enqueue(jobs_of("frames_zip", 1))
    r.tick()
    spawn.run_all()
    assert heard.calls[-1] == ("ended", job.id, "done", 0, False)


def test_spawn_failure_is_heard_as_ended(runner_factory):
    def broken_spawn(fn):
        raise RuntimeError("can't start new thread")

    r, spawn, h = runner_factory(spawn=broken_spawn)
    heard = r.listener = RecordingListener(r)
    (job,) = r.enqueue(jobs_of("frames_zip", 1))
    r.tick()
    assert heard.calls[-1] == ("ended", job.id, "failed", 0, False)


def test_listener_errors_do_not_break_the_queue(runner_factory):
    class Broken:
        def job_queued(self) -> None:
            raise RuntimeError("boom")

        def job_ended(self, job_id: str) -> None:
            raise RuntimeError("boom")

    r, spawn, h = runner_factory()
    r.listener = Broken()
    (job,) = r.enqueue(jobs_of("frames_zip", 1))
    r.tick()
    spawn.run_all()
    assert r.store.get(job.id).status == "done"
```

- [ ] **Step 2: Run them, expect FAIL**

Run: `cd "$WORKTREE" && uv run pytest tests/unit/test_account_session.py tests/unit/test_queue.py -q -W error -p no:cacheprovider`
Expected: `ModuleNotFoundError: No module named 'yttoolkit.core.account_session'`; with that file present, the new queue tests fail with `assert [] == [('queued', False)]` (no listener calls yet).

- [ ] **Step 3: Create `src/yttoolkit/core/account_session.py`**
```python
"""บัญชียูทูปชั่วคราว (M5 รอบ C spec 2.1-2.2): ถือการเข้าสู่ระบบได้ครั้งละหนึ่งบัญชี ในหน่วยความจำเท่านั้น

- import_text: ตรวจขนาด (≤ 1 MB) แล้วให้ parse (core/extractor.parse_account_cookies) อ่านเป็น jar ของ yt-dlp
  แทนบัญชีเดิม (ถ้ามี) และเริ่มนับเวลาใหม่ · ไม่มีอะไรลงดิสก์ ไม่ว่ารูปไหน (C8)
- ลบเองเมื่อ (C6): ครบ 2 ชั่วโมงหลังนำเข้า · ปิดโปรแกรม · งานในคิวที่ใช้บัญชีจบแล้วคิวว่างครบ 10 นาที (grace)
  การดึงข้อมูลคลิปหรือถ่ายภาพคมที่ใช้บัญชี (mark_used(None)) ไม่เริ่ม grace
- ทุกครั้งที่สถานะเปลี่ยนประกาศข่าว "account" ทาง publish: {active, expiresAt?, reason?} ไม่มีชื่อหรือค่าคุกกี้
- เธรดไหนเรียกก็ได้ (ล็อกเดียว) · publish / on_clear เรียกนอกล็อก
- ลบแล้ว jar เดิมถูกปล่อยให้ GC เก็บ (ไม่ได้ลบค่าในหน่วยความจำทิ้ง: ภัยที่กันคือไฟล์บนดิสก์และ log ไม่ใช่การอ่านหน่วยความจำ)
core ไม่ import api/ หรือ platform/ และโมดูลนี้ไม่ import yt_dlp (ตัวอ่านไฟล์ส่งมาจากผู้สร้าง)
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any

from .yterrors import YtError

log = logging.getLogger("yttoolkit")

MAX_IMPORT_BYTES = 1_048_576  # spec 1.2 / 2.1: ไฟล์ cookies.txt ไม่เกิน 1 MB
EXPIRY_S = 2 * 60 * 60  # C6 (c): ลบเองเมื่อครบ 2 ชั่วโมงหลังนำเข้า
GRACE_S = 10 * 60  # C6 (a): คิวว่างครบ 10 นาทีหลังงานที่ใช้บัญชีจบ (planner ruling spec 2.2)
CLEAR_REASONS = frozenset({"manual", "queue_done", "expired", "shutdown"})

Schedule = Callable[[float, Callable[[], None]], None]
Publish = Callable[[str, dict], None]


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _timer_schedule(delay: float, fn: Callable[[], None]) -> None:
    timer = threading.Timer(max(delay, 0.0), fn)
    timer.daemon = True  # timer ที่ค้างอยู่ไม่ขวางการปิดโปรแกรม (ปิดโปรแกรม = clear("shutdown") อยู่แล้ว)
    timer.start()


def _iso(moment: datetime) -> str:
    return moment.astimezone(UTC).isoformat(timespec="seconds")


class AccountService:
    """C3: import_text / clear / status / jar / mark_used และ job_queued / job_ended (QueueListener ของคิว)"""

    def __init__(
        self,
        parse: Callable[[str], Any],
        *,
        publish: Publish | None = None,
        busy: Callable[[], bool] = lambda: False,
        on_clear: Callable[[], None] | None = None,
        now: Callable[[], datetime] = _utcnow,
        schedule: Schedule = _timer_schedule,
        expiry_s: float = EXPIRY_S,
        grace_s: float = GRACE_S,
    ) -> None:
        """parse(text) -> jar (YtError E_COOKIES_INVALID เมื่ออ่านไม่ได้) · busy() = คิวมีงานรอหรือกำลังทำ
        on_clear() = ทิ้งข้อมูลที่ได้มาด้วยบัญชีนี้ (VideoService.forget_signed_in) เรียกเมื่อลบหรือแทนบัญชี"""
        self._parse = parse
        self._publish = publish
        self._busy = busy
        self._on_clear = on_clear
        self._now = now
        self._schedule = schedule
        self._expiry_s = expiry_s
        self._grace_s = grace_s
        self._lock = threading.Lock()
        self._jar: Any | None = None
        self._imported_at: datetime | None = None
        self._expires_at: datetime | None = None
        self._generation = 0  # เพิ่มทุกครั้งที่นำเข้าหรือลบ timer ที่ค้างจากรุ่นก่อนจึงไม่มีผล
        self._grace_seq = 0
        self._grace_token: int | None = None  # grace ที่กำลังนับ (None = ไม่ได้นับ)
        self._grace_until: datetime | None = None
        self._used = False
        self._job_used = False  # spec 2.2 (a): งานในคิวที่ใช้บัญชีจบไปแล้วอย่างน้อยหนึ่งงาน
        self._jobs: set[str] = set()  # งานที่กำลังใช้บัญชีอยู่ (job id)

    # ---------- อ่านสถานะ ----------

    def jar(self) -> Any | None:
        with self._lock:
            return self._jar

    def status(self) -> dict:
        with self._lock:
            return self._status_locked()

    def _status_locked(self) -> dict:
        if self._jar is None or self._imported_at is None:
            return {"active": False, "used": False}
        return {
            "active": True,
            "importedAt": _iso(self._imported_at),
            "expiresAt": _iso(self._deadline_locked()),
            "used": self._used,
        }

    def _deadline_locked(self) -> datetime:
        """เวลาที่จะลบเองเร็วที่สุด: ครบ 2 ชั่วโมง หรือ grace ที่กำลังนับ"""
        assert self._expires_at is not None
        if self._grace_until is not None and self._grace_until < self._expires_at:
            return self._grace_until
        return self._expires_at

    # ---------- นำเข้า / ลบ ----------

    def import_text(self, text: str) -> dict:
        """นำเข้า cookies.txt (ข้อความ) แทนบัญชีเดิม คืน status() · ใช้ไม่ได้ = YtError E_COOKIES_INVALID บัญชีเดิมไม่เปลี่ยน"""
        if not isinstance(text, str) or len(text.encode("utf-8")) > MAX_IMPORT_BYTES:
            raise YtError("E_COOKIES_INVALID", f"file larger than {MAX_IMPORT_BYTES} bytes")
        jar = self._parse(text)  # ตรวจก่อนแตะสถานะ: ไฟล์เสีย = บัญชีเดิมยังอยู่ครบ
        with self._lock:
            replaced = self._jar is not None
            self._generation += 1
            generation = self._generation
            self._jar = jar
            self._imported_at = self._now()
            self._expires_at = self._imported_at + timedelta(seconds=self._expiry_s)
            self._grace_token = None
            self._grace_until = None
            self._used = False
            self._job_used = False
            self._jobs.clear()
            status = self._status_locked()
        if replaced:
            self._forget_signed_in()
        self._schedule(self._expiry_s, lambda: self._expire(generation))
        log.info("นำเข้าบัญชียูทูปชั่วคราวแล้ว ลบเองภายใน %s", status["expiresAt"])
        self._announce({"active": True, "expiresAt": status["expiresAt"]})
        return status

    def clear(self, reason: str) -> dict:
        """ลบบัญชีที่ถืออยู่ (ไม่มี = ไม่ทำอะไร ไม่ประกาศ) คืน status() · งานที่กำลังโหลดด้วยบัญชีนี้ใช้ต่อจนจบ"""
        if reason not in CLEAR_REASONS:
            raise ValueError(f"reason ไม่รู้จัก: {reason!r}")
        with self._lock:
            if self._jar is None:
                return self._status_locked()
            self._generation += 1
            self._jar = None
            self._imported_at = None
            self._expires_at = None
            self._grace_token = None
            self._grace_until = None
            self._used = False
            self._job_used = False
            self._jobs.clear()
            status = self._status_locked()
        self._forget_signed_in()
        log.info("ลบบัญชียูทูปชั่วคราวออกจากแอพแล้ว (%s)", reason)
        self._announce({"active": False, "reason": reason})
        return status

    # ---------- การใช้งาน ----------

    def mark_used(self, job_id: str | None) -> None:
        """มีคำขอที่ต้องใช้บัญชี: job_id = งานในคิว (นับเข้ากฎคิวว่าง) · None = หน้าเว็บ/ถ่ายภาพคม (ไม่นับ)"""
        with self._lock:
            if self._jar is None:
                return
            self._used = True
            if job_id is not None:
                self._jobs.add(job_id)

    # ---------- QueueListener (core/queue.py เรียก) ----------

    def job_queued(self) -> None:
        """มีงานเข้าคิว (ใหม่หรือกดลองใหม่): ยกเลิก grace ที่กำลังนับ"""
        with self._lock:
            if self._grace_token is None:
                return
            self._grace_token = None
            self._grace_until = None
            event = {"active": True, "expiresAt": _iso(self._deadline_locked())}
        self._announce(event)

    def job_ended(self, job_id: str) -> None:
        """งานจบ (เสร็จ พลาด ยกเลิก หยุดกลางคัน): งานที่ใช้บัญชีจบแล้ว + คิวว่าง = เริ่ม grace"""
        with self._lock:
            if job_id in self._jobs:
                self._jobs.discard(job_id)
                if self._jar is not None:
                    self._job_used = True
            if self._jar is None or not self._job_used or self._grace_token is not None:
                return
            if self._busy():
                return
            self._grace_seq += 1
            token = self._grace_seq
            self._grace_token = token
            self._grace_until = self._now() + timedelta(seconds=self._grace_s)
            event = {"active": True, "expiresAt": _iso(self._deadline_locked())}
        log.info("คิวว่างแล้ว ลบบัญชียูทูปชั่วคราวในอีก %d วินาที", int(self._grace_s))
        self._schedule(self._grace_s, lambda: self._grace_due(token))
        self._announce(event)

    # ---------- ภายใน ----------

    def _expire(self, generation: int) -> None:
        with self._lock:
            if generation != self._generation or self._jar is None:
                return
        self.clear("expired")

    def _grace_due(self, token: int) -> None:
        with self._lock:
            if token != self._grace_token or self._jar is None:
                return
        self.clear("queue_done")

    def _forget_signed_in(self) -> None:
        if self._on_clear is None:
            return
        try:
            self._on_clear()
        except Exception:
            log.exception("ล้างข้อมูลคลิปที่ได้มาด้วยบัญชีไม่สำเร็จ")

    def _announce(self, data: dict) -> None:
        if self._publish is None:
            return
        try:
            self._publish("account", data)
        except Exception:
            log.exception("ประกาศสถานะบัญชียูทูปไม่สำเร็จ")
```

- [ ] **Step 4: Add the listener to `core/queue.py`** (the `cancel` rewrite keeps every branch's behaviour; only the running-with-context branch returns early because its final state arrives later through `_end`):
Replace (1):
```python
class SettingsView(Protocol):
    def concurrency(self) -> int: ...
    def output_dir(self) -> Path: ...


def _thread_spawn(fn: Callable[[], None]) -> None:
```
with:
```python
class SettingsView(Protocol):
    def concurrency(self) -> int: ...
    def output_dir(self) -> Path: ...


class QueueListener(Protocol):
    """ผู้ฟังสถานะคิว (M5 รอบ C: AccountService นับ grace ของบัญชีชั่วคราว) เรียกนอกล็อกของคิวเสมอ"""

    def job_queued(self) -> None: ...
    def job_ended(self, job_id: str) -> None: ...


def _thread_spawn(fn: Callable[[], None]) -> None:
```

Replace (2):
```python
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._stopping = False

    # ---------- ตัวจัดคิว ----------
```
with:
```python
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._stopping = False
        # ผู้ฟัง (lifecycle ต่อ AccountService ให้หลังสร้าง) None = ไม่มีใครฟัง
        self.listener: QueueListener | None = None

    # ---------- ตัวจัดคิว ----------
```

Replace (3):
```python

    def tick(self) -> list[str]:
        started: list[str] = []
        with self._lock:
            if self._stopping or self.pause_state() is not None:
                return started
```
with:
```python

    def tick(self) -> list[str]:
        started: list[str] = []
        spawn_failed: list[str] = []
        with self._lock:
            if self._stopping or self.pause_state() is not None:
                return started
```

Replace (4):
```python
                    continue  # รอเว้นช่วง งานที่ไม่ต้องคุยกับยูทูปข้างหลังยังเริ่มได้
                outcome = self._start(job)
                if outcome == _SPAWN_FAILED:
                    break  # เปิดเธรดไม่ได้ อย่าลากงานที่เหลือในคิวให้ล้มตามกันหมดในรอบเดียว รอรอบหน้า
                if outcome == _STARTED:
                    started.append(job.id)
                    slots -= 1
                    if youtube:
                        self._next_youtube_at = self._monotonic() + self._rng.uniform(*self._delay_range)
        return started

    def _start(self, job: Job) -> str:
```
with:
```python
                    continue  # รอเว้นช่วง งานที่ไม่ต้องคุยกับยูทูปข้างหลังยังเริ่มได้
                outcome = self._start(job)
                if outcome == _SPAWN_FAILED:
                    spawn_failed.append(job.id)
                    break  # เปิดเธรดไม่ได้ อย่าลากงานที่เหลือในคิวให้ล้มตามกันหมดในรอบเดียว รอรอบหน้า
                if outcome == _STARTED:
                    started.append(job.id)
                    slots -= 1
                    if youtube:
                        self._next_youtube_at = self._monotonic() + self._rng.uniform(*self._delay_range)
        for job_id in spawn_failed:
            self._notify_ended(job_id)
        return started

    def _start(self, job: Job) -> str:
```

Replace (5):
```python
            return False
        self._forget(job.id, ctx)
        self._publish_job(ended)
        return True

    def _forget(self, job_id: str, ctx: _JobContext) -> None:
```
with:
```python
            return False
        self._forget(job.id, ctx)
        self._publish_job(ended)
        self._notify_ended(job.id)
        return True

    def _forget(self, job_id: str, ctx: _JobContext) -> None:
```

Replace (6):
```python
            for job in jobs:
                self._bus.publish("job.created", self.job_api(job))
        self._wake.set()
        return jobs

    def cancel(self, job_id: str) -> Job:
```
with:
```python
            for job in jobs:
                self._bus.publish("job.created", self.job_api(job))
        self._wake.set()
        if jobs:
            self._notify_queued()
        return jobs

    def cancel(self, job_id: str) -> Job:
```

Replace (7):
```python
            if job.status == "queued":
                job = self.store.transition(job_id, "cancelled")
                self._publish_job(job)
                return job
            if job.status != "running":
                raise InvalidTransition(f"{job.status} -> cancelled")
            ctx = self._active.get(job_id)
            if ctx is None:
                # running ค้างจากที่ไม่มีเธรดไหนทำอยู่แล้ว ยกเลิกในฐานข้อมูลได้เลย
                job = self.store.transition(job_id, "cancelled")
                self._publish_job(job)
                return job
            ctx.request_stop(_USER)
            self._bus.job_updated(job_id, {"cancelling": True})
        return job

    def retry(self, job_id: str) -> Job:
```
with:
```python
            if job.status == "queued":
                job = self.store.transition(job_id, "cancelled")
                self._publish_job(job)
            elif job.status != "running":
                raise InvalidTransition(f"{job.status} -> cancelled")
            elif (ctx := self._active.get(job_id)) is None:
                # running ค้างจากที่ไม่มีเธรดไหนทำอยู่แล้ว ยกเลิกในฐานข้อมูลได้เลย
                job = self.store.transition(job_id, "cancelled")
                self._publish_job(job)
            else:
                ctx.request_stop(_USER)
                self._bus.job_updated(job_id, {"cancelling": True})
                return job  # สถานะ cancelled มากับเธรดงาน (_end แจ้งผู้ฟังเอง)
        self._notify_ended(job_id)
        return job

    def retry(self, job_id: str) -> Job:
```

Replace (8):
```python
            job = self.store.requeue(job_id, reset_bot_checks=True)
            self._publish_job(job)
        self._wake.set()
        return job

    def reorder(self, ids: Sequence[str]) -> None:
```
with:
```python
            job = self.store.requeue(job_id, reset_bot_checks=True)
            self._publish_job(job)
        self._wake.set()
        self._notify_queued()
        return job

    def reorder(self, ids: Sequence[str]) -> None:
```

Replace (9):
```python
        if error and error.get("detail"):
            data["error"] = {**error, "detail": self._redact(error["detail"])}
        return data

    def _publish_job(self, job: Job) -> None:
        """ข่าวเปลี่ยนสถานะ: ส่งทุกคีย์ ค่าที่ไม่มีแล้วส่งเป็น null (เช่น error เก่าหลังลองใหม่)"""
```
with:
```python
        if error and error.get("detail"):
            data["error"] = {**error, "detail": self._redact(error["detail"])}
        return data

    def _notify_queued(self) -> None:
        listener = self.listener
        if listener is None:
            return
        try:
            listener.job_queued()
        except Exception:
            log.exception("แจ้งผู้ฟังว่ามีงานเข้าคิวไม่สำเร็จ")

    def _notify_ended(self, job_id: str) -> None:
        listener = self.listener
        if listener is None:
            return
        try:
            listener.job_ended(job_id)
        except Exception:
            log.exception("แจ้งผู้ฟังว่างาน %s จบไม่สำเร็จ", job_id)

    def _publish_job(self, job: Job) -> None:
        """ข่าวเปลี่ยนสถานะ: ส่งทุกคีย์ ค่าที่ไม่มีแล้วส่งเป็น null (เช่น error เก่าหลังลองใหม่)"""
```

- [ ] **Step 5: Run the tests, expect PASS** — same command as Step 2, then the full suite.

- [ ] **Step 6: Commit**
```bash
cd "$WORKTREE" && git add src/yttoolkit/core/account_session.py src/yttoolkit/core/queue.py tests/unit/test_account_session.py tests/unit/test_queue.py && git commit -F- <<'EOF'
feat(core): M5-C in-memory account service with auto-delete and a queue listener

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
EOF
```

### Task 4: Extractor account mode, the cookies.txt parser, the real-YoutubeDL contract test, fake clips that need the account

**Files:**
- Create: `src/yttoolkit/core/account_scope.py` (part 1: `current_jar`, `signed_in`; T6 adds the retry helper)
- Modify: `src/yttoolkit/core/extractor.py`
- Modify: `tests/fixtures/downloads/behaviors.json` (`ACCOUNTAGE1`, `ACCOUNTMEM1`)
- Modify: `tests/unit/test_extractor_download.py` (the `C14` literal must equal `behaviors.json`)
- Test: `tests/unit/test_extractor_account.py` (new)

**Interfaces:**
- Consumes: `_cookie_jar`, `_attach_session`, `YtDlpExtractor._ydl` and its call sites (`core/extractor.py:193-225, 495-788`), `FakeExtractor.probe` (`:841-849`), `DownloadChoice`/`DownloadHooks` (`core/download.py`), `YtError`.
- Produces: C4 exactly. T6 adds to `account_scope.py`; T6/T7/T9 use `parse_account_cookies`, `ACCOUNTAGE1`, `ACCOUNTMEM1`.

- [ ] **Step 1: Write the failing tests** — create `tests/unit/test_extractor_account.py` (no `yt_dlp` import: the real `YoutubeDL` is built through `YtDlpExtractor._ydl`):
```python
"""บัญชียูทูปชั่วคราวใน core/extractor.py (M5 รอบ C spec 2.1, 2.3): ตัวอ่าน cookies.txt และการต่อ jar เข้า yt-dlp

ไม่ต่อเน็ต ไม่ import yt_dlp ตรง ๆ (YoutubeDL จริงสร้างผ่าน YtDlpExtractor._ydl เท่านั้น)
"""

from __future__ import annotations

import json
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import pytest

from yttoolkit.core.account_scope import current_jar, signed_in
from yttoolkit.core.download import DownloadChoice, DownloadHooks
from yttoolkit.core.extractor import (
    ACCOUNT_FORBIDDEN_OPTS,
    FakeExtractor,
    YtDlpExtractor,
    parse_account_cookies,
    visitor_session,
)
from yttoolkit.core.yterrors import YtError

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
CANARY = "canary-acc-41d2"
HEADER = "# Netscape HTTP Cookie File\n"


def _line(domain: str, name: str, value: str = CANARY, *, flag: str | None = None, expires: str = "1999999999") -> str:
    flag = flag if flag is not None else ("TRUE" if domain.startswith(".") else "FALSE")
    return "\t".join((domain, flag, "/", "TRUE", expires, name, value))


GOOD = HEADER + "\n".join(
    (
        _line(".youtube.com", "SAPISID"),
        "#HttpOnly_" + _line(".youtube.com", "__Secure-3PSID"),
        _line(".google.com", "SID"),
        _line("accounts.google.com", "LSID"),
        _line(".example.com", "TRACKER"),
        _line(".youtube.com.evil.test", "SAPISID"),
        "",
        "# a comment line",
    )
) + "\n"


def _names(jar: Any) -> set[tuple[str, str]]:
    return {(c.domain, c.name) for c in jar}


# ---------- parse_account_cookies ----------


def test_keeps_only_youtube_and_google_domains() -> None:
    jar = parse_account_cookies(GOOD)
    assert _names(jar) == {
        (".youtube.com", "SAPISID"),
        (".youtube.com", "__Secure-3PSID"),
        (".google.com", "SID"),
        ("accounts.google.com", "LSID"),
    }


def test_bom_crlf_and_no_header_are_fine() -> None:
    text = "﻿" + _line(".youtube.com", "LOGIN_INFO") + "\r\n" + _line("www.youtube.com", "PREF") + "\r\n"
    assert _names(parse_account_cookies(text)) == {(".youtube.com", "LOGIN_INFO"), ("www.youtube.com", "PREF")}


def test_a_wrong_domain_flag_is_fixed_not_fatal() -> None:
    jar = parse_account_cookies(_line(".youtube.com", "SAPISID", flag="FALSE") + "\n")
    assert _names(jar) == {(".youtube.com", "SAPISID")}


@pytest.mark.parametrize(
    "text",
    [
        _line(".youtube.com", "PREF") + "\n",  # ไม่มีคุกกี้เข้าสู่ระบบ
        _line(".google.com", "SAPISID") + "\n",  # คุกกี้เข้าสู่ระบบของ google.com อย่างเดียวไม่พอ
        "",
        HEADER,
    ],
)
def test_no_youtube_sign_in_cookie_is_invalid(text: str) -> None:
    with pytest.raises(YtError) as info:
        parse_account_cookies(text)
    assert (info.value.code, info.value.detail) == ("E_COOKIES_INVALID", "no YouTube sign-in cookie")


@pytest.mark.parametrize(
    ("text", "detail"),
    [
        (HEADER + f"garbage {CANARY}\n", "line 2: expected 7 tab-separated fields"),
        (HEADER + _line(".youtube.com", "SAPISID") + f"\t{CANARY}\n", "line 2: expected 7 tab-separated fields"),
        ('[{"domain": ".youtube.com", "value": "' + CANARY + '"}]', "line 1: expected 7 tab-separated fields"),
        (HEADER + _line(".youtube.com", "SAPISID", expires=f"x{CANARY}") + "\n", "line 2: expiry is not a number"),
    ],
)
def test_garbage_is_invalid_and_never_echoes_the_line(text: str, detail: str, capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(YtError) as info:
        parse_account_cookies(text)
    assert (info.value.code, info.value.detail) == ("E_COOKIES_INVALID", detail)
    assert info.value.__cause__ is None
    assert CANARY not in str(info.value)
    out = capsys.readouterr()
    assert CANARY not in out.out and CANARY not in out.err  # ตัวอ่านของ yt-dlp ไม่ได้พิมพ์บรรทัดที่เสีย


def test_parsing_writes_no_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    parse_account_cookies(GOOD)
    assert list(tmp_path.iterdir()) == []


# ---------- _ydl(with_account=...) กับ YoutubeDL จริง (สัญญา API ภายในของ yt-dlp) ----------


def test_attach_account_on_a_real_youtubedl(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """เหมือน test_attach_session_on_a_real_youtubedl: ต้องผ่านทุกครั้งที่อัปเดต yt-dlp ไม่ต่อเน็ต"""
    monkeypatch.chdir(tmp_path)
    jar = parse_account_cookies(GOOD)
    session = visitor_session(tmp_path / "data")
    ext = YtDlpExtractor(session=session)
    with ext._ydl({"quiet": True, "no_warnings": True, "cookiefile": "x.txt"}, with_session=True, with_account=jar) as ydl:
        assert ydl.cookiejar is jar
        assert all(handler.cookiejar is jar for handler in ydl._request_director.handlers.values())
        assert "cookiefile" not in ydl.params or ydl.params["cookiefile"] is None
        assert not any(ydl.params.get(key) for key in ACCOUNT_FORBIDDEN_OPTS)
        assert CANARY in (ydl.cookiejar.get_cookie_header("https://www.youtube.com/watch?v=x") or "")
        ydl._load_cookies(f"ROTATED={CANARY}; Domain=.youtube.com", autoscope=False)  # ยูทูปหมุนคุกกี้ระหว่างงาน
        ydl.save_cookies()
    assert list(tmp_path.iterdir()) == []  # ไม่มี x.txt ไม่มีไฟล์เซสชันผู้ชม ไม่มีไฟล์อื่น
    assert "ROTATED" in {c.name for c in jar}  # คุกกี้ใหม่อยู่ใน jar ก้อนเดิมในหน่วยความจำ


@pytest.mark.parametrize("key", sorted(ACCOUNT_FORBIDDEN_OPTS))
def test_traffic_printing_options_are_refused_with_an_account(key: str) -> None:
    jar = parse_account_cookies(GOOD)
    with pytest.raises(ValueError):
        with YtDlpExtractor()._ydl({"quiet": True, key: True}, with_account=jar):
            pass


# ---------- ทุกจุดที่ใช้เซสชันผู้ชมส่งบัญชีของขอบเขตไปที่ _ydl ----------


class FakeYDL:
    def __init__(self) -> None:
        self.params: dict = {}

    def extract_info(self, url: str, download: bool = False) -> dict:
        return {"id": "aqz-KE-bpKQ", "live_status": "not_live", "formats": []}

    def sanitize_info(self, info: dict, remove_private_keys: bool = False) -> dict:
        return dict(info)

    def process_ie_result(self, info: dict, download: bool = True) -> dict:
        raise YtError("E_NETWORK", "fake: stop before downloading")

    def urlopen(self, request: Any) -> Any:
        class Response:
            def __enter__(self) -> Response:
                return self

            def __exit__(self, *exc: object) -> None:
                return None

            def read(self) -> bytes:
                return b"{}"

        return Response()


def _recording(ext: YtDlpExtractor, monkeypatch: pytest.MonkeyPatch) -> list[Any]:
    seen: list[Any] = []

    @contextmanager
    def fake_ydl(opts: dict, *, with_session: bool = False, with_account: Any | None = None):
        seen.append(with_account)
        yield FakeYDL()

    monkeypatch.setattr(ext, "_ydl", fake_ydl)
    return seen


def _hooks() -> DownloadHooks:
    return DownloadHooks(on_stage=lambda s: None, on_progress=lambda *a: None, is_cancelled=lambda: False,
                         ffmpeg_location=None)  # fmt: skip


def _choose(info: dict) -> DownloadChoice:
    return DownloadChoice("bv*+ba", True, None, (), None)


def test_every_signed_in_call_site_passes_the_scope_jar(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    ext = YtDlpExtractor()
    seen = _recording(ext, monkeypatch)
    jar = object()
    with signed_in(jar):
        ext.probe("aqz-KE-bpKQ")
        ext.fetch_subtitle("https://www.youtube.com/api/timedtext?v=x")
        with pytest.raises(YtError):
            ext.download("aqz-KE-bpKQ", _choose, tmp_path, _hooks())
        with pytest.raises(YtError) as info:
            ext.fetch_frame_piece("aqz-KE-bpKQ", 1000, None, tmp_path / "piece.mp4")
        assert info.value.code == "E_CAPTURE_UNSUPPORTED"  # ไม่มี format ให้เลือก (FakeYDL) แต่ _ydl ได้ jar แล้ว
    assert seen == [jar] * 5  # probe, ซับ, ดึงข้อมูลก่อนโหลด, โหลด, ถ่ายภาพคม


def test_without_a_scope_nothing_is_signed_in(monkeypatch: pytest.MonkeyPatch) -> None:
    ext = YtDlpExtractor()
    seen = _recording(ext, monkeypatch)
    ext.probe("aqz-KE-bpKQ")
    assert seen == [None]


def test_playlists_never_use_the_account(monkeypatch: pytest.MonkeyPatch) -> None:
    ext = YtDlpExtractor()
    seen = _recording(ext, monkeypatch)
    with signed_in(object()):
        ext.playlist("PLfakeplaylist250", 10)
    assert seen == [None]


def test_scope_resets_after_the_block() -> None:
    jar = object()
    with signed_in(jar):
        assert current_jar() is jar
    assert current_jar() is None
    with pytest.raises(ValueError):
        with signed_in(None):
            pass


# ---------- FakeExtractor: คลิปที่ต้องใช้บัญชี ----------


@pytest.mark.parametrize(("video_id", "code"), [("ACCOUNTAGE1", "E_AGE_RESTRICTED"), ("ACCOUNTMEM1", "E_VIDEO_PRIVATE")])
def test_fake_clip_needs_the_account(video_id: str, code: str) -> None:
    fake = FakeExtractor(FIXTURES)
    with pytest.raises(YtError) as info:
        fake.probe(video_id)
    assert info.value.code == code
    with signed_in(object()):
        info_dict = fake.probe(video_id)
    assert info_dict["id"] == video_id


def test_fake_private_clip_stays_private_with_the_account() -> None:
    fake = FakeExtractor(FIXTURES)
    with signed_in(object()), pytest.raises(YtError) as info:
        fake.probe(FakeExtractor.PRIVATE_ID)
    assert info.value.code == "E_VIDEO_PRIVATE"


def test_fake_download_follows_the_same_rule(tmp_path: Path) -> None:
    doc = json.loads((FIXTURES / "downloads" / "behaviors.json").read_text(encoding="utf-8"))
    for entry in [doc["default"], *doc["videos"].values()]:
        entry["stepMs"] = 0
    behaviors = tmp_path / "behaviors.json"
    behaviors.write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")
    fake = FakeExtractor(FIXTURES, behaviors=behaviors)
    with pytest.raises(YtError):
        fake.download("ACCOUNTAGE1", _choose, tmp_path / "w1", _hooks())
    with signed_in(object()):
        result = fake.download("ACCOUNTAGE1", _choose, tmp_path / "w2", _hooks())
    assert result.path.is_file()
```

In `tests/unit/test_extractor_download.py` (the `C14` literal):
Replace (1):
```python
        "CAPTURENO01": {"probeAs": BBB, "title": "คลิปถ่ายภาพคมไม่ได้", "captureError": "E_CAPTURE_UNSUPPORTED"},
        "CAPTUREBOT1": {"probeAs": BBB, "title": "คลิปถ่ายภาพคมติดบอท", "captureError": "E_BOT_CHECK"},
        "CAPTURENET1": {"probeAs": BBB, "title": "คลิปถ่ายภาพคมเน็ตหลุด", "captureError": "E_NETWORK"},
    },
}
```
with:
```python
        "CAPTURENO01": {"probeAs": BBB, "title": "คลิปถ่ายภาพคมไม่ได้", "captureError": "E_CAPTURE_UNSUPPORTED"},
        "CAPTUREBOT1": {"probeAs": BBB, "title": "คลิปถ่ายภาพคมติดบอท", "captureError": "E_BOT_CHECK"},
        "CAPTURENET1": {"probeAs": BBB, "title": "คลิปถ่ายภาพคมเน็ตหลุด", "captureError": "E_NETWORK"},
        "ACCOUNTAGE1": {"probeAs": BBB, "title": "คลิปจำกัดอายุ", "needsAccount": "E_AGE_RESTRICTED"},
        "ACCOUNTMEM1": {"probeAs": BBB, "title": "คลิปเฉพาะสมาชิก", "needsAccount": "E_VIDEO_PRIVATE"},
    },
}
```

- [ ] **Step 2: Run them, expect FAIL**

Run: `cd "$WORKTREE" && uv run pytest tests/unit/test_extractor_account.py tests/unit/test_extractor_download.py -q -W error -p no:cacheprovider`
Expected: `ModuleNotFoundError: No module named 'yttoolkit.core.account_scope'`, and `test_behaviors_file_is_c14_verbatim` fails until `behaviors.json` has the two clips.

- [ ] **Step 3: Create `src/yttoolkit/core/account_scope.py`**
```python
"""ขอบเขตของงานที่ใช้บัญชียูทูปชั่วคราว (M5 รอบ C spec 2.3-2.4)

signed_in(jar) ครอบงานหนึ่งชิ้น (probe ของหน้า W2 / งานในคิวทั้งงาน / ถ่ายภาพคมหนึ่งครั้ง) ทุกคำขอ yt-dlp ใน
ขอบเขตนี้ใช้บัญชีนั้น (core/extractor อ่าน current_jar() แล้วส่งให้ _ydl(with_account=...)) และ VideoService
ไม่เขียนข้อมูลคลิปลงดิสก์ ค่าเก็บใน contextvars จึงแยกตามเธรด/งาน ไม่รั่วไปงานอื่นที่รันพร้อมกัน
ใช้แค่ stdlib กับ core/yterrors (ไม่ import yt_dlp)
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any

_JAR: ContextVar[Any | None] = ContextVar("yttoolkit_account_jar", default=None)


def current_jar() -> Any | None:
    """jar ของบัญชีที่งานนี้ใช้อยู่ None = ไม่ได้ใช้บัญชี (คำขอแบบไม่ระบุตัวตนตามปกติ)"""
    return _JAR.get()


@contextmanager
def signed_in(jar: Any) -> Iterator[None]:
    """ให้ทุกคำขอยูทูปในบล็อกนี้ใช้ jar ของบัญชีชั่วคราว (ออกจากบล็อก = กลับเป็นค่าเดิม)"""
    if jar is None:
        raise ValueError("signed_in ต้องมี jar")
    token = _JAR.set(jar)
    try:
        yield
    finally:
        _JAR.reset(token)
```

- [ ] **Step 4: Implement `core/extractor.py`**
Replace (1):
```python

import functools
import importlib.metadata
import json
import logging
import math
```
with:
```python

import functools
import importlib.metadata
import io
import json
import logging
import math
```

Replace (2):
```python
    SponsorSegment,
    media_facts,
)
from .frame_piece import PieceInfo, fetch_piece, pick_capture_format, piece_info, read_index, write_piece
from .inputs import PLAYLIST_ID, VIDEO_ID, is_mix_id
from .visitor_session import VisitorSession
```
with:
```python
    SponsorSegment,
    media_facts,
)
from .account_scope import current_jar
from .frame_piece import PieceInfo, fetch_piece, pick_capture_format, piece_info, read_index, write_piece
from .inputs import PLAYLIST_ID, VIDEO_ID, is_mix_id
from .visitor_session import VisitorSession
```

Replace (3):
```python
    from yt_dlp.cookies import YoutubeDLCookieJar

    return YoutubeDLCookieJar(filename)


def visitor_session(folder: Path) -> VisitorSession:
```
with:
```python
    from yt_dlp.cookies import YoutubeDLCookieJar

    return YoutubeDLCookieJar(filename)


# ---------- บัญชียูทูปชั่วคราว (M5 รอบ C spec 2.1, 2.3) ----------

# คุกกี้ที่บอกว่าเข้าสู่ระบบแล้ว ต้องมีอย่างน้อยหนึ่งตัวของ .youtube.com
ACCOUNT_SIGN_IN_COOKIES = frozenset({"SAPISID", "__Secure-3PSID", "LOGIN_INFO"})
ACCOUNT_DOMAINS = ("youtube.com", "google.com")  # เก็บเฉพาะโดเมนนี้และโดเมนย่อย ที่เหลือทิ้ง
# ค่าตั้งของ yt-dlp ที่พิมพ์คำขอ/หน้าเว็บ (มี header Cookie) ห้ามใช้คู่กับบัญชี
# "print_traffic" / "dump_pages" คือชื่อของตัวเลือกบรรทัดคำสั่ง ใส่ไว้กันพลาดด้วย
ACCOUNT_FORBIDDEN_OPTS = frozenset(
    {"verbose", "debug_printtraffic", "print_traffic", "dump_intermediate_pages", "dump_pages", "write_pages"}
)
_HTTPONLY_PREFIX = "#HttpOnly_"
_NETSCAPE_HEADER = "# Netscape HTTP Cookie File\n"
_EXPIRES = re.compile(r"[0-9]+(?:\.[0-9]+)?")


def _account_domain(domain: str) -> bool:
    bare = domain.lower().lstrip(".")
    return any(bare == d or bare.endswith(f".{d}") for d in ACCOUNT_DOMAINS)


def parse_account_cookies(text: str) -> Any:
    """cookies.txt (Netscape) -> jar ของ yt-dlp ในหน่วยความจำ ไม่มีไฟล์ใด ๆ (อ่านผ่าน io.StringIO)

    - ตัด BOM รับ LF / CRLF · บรรทัด #HttpOnly_ คือคุกกี้ บรรทัด # อื่นและบรรทัดว่างข้าม
    - ทุกบรรทัดคุกกี้ต้องมี 7 ช่องคั่นด้วยแท็บ วันหมดอายุเป็นตัวเลข ไม่งั้นทั้งไฟล์ใช้ไม่ได้ (ตรวจเองก่อนให้ yt-dlp อ่าน:
      ตัวอ่านของ yt-dlp พิมพ์บรรทัดที่เสียลงจอ และ http.cookiejar ยกบรรทัดใส่ข้อความ error)
    - เก็บเฉพาะโดเมน youtube.com / google.com และโดเมนย่อย · ต้องมี SAPISID / __Secure-3PSID / LOGIN_INFO ของ .youtube.com
    error ทุกแบบ = YtError("E_COOKIES_INVALID") ที่ detail บอกแค่ชนิดปัญหาและเลขบรรทัด ไม่ยกเนื้อหาของบรรทัด
    """
    from yt_dlp.cookies import YoutubeDLCookieJar

    kept: list[str] = []
    for number, line in enumerate(text.removeprefix("\ufeff").splitlines(), start=1):
        entry = line[len(_HTTPONLY_PREFIX) :] if line.startswith(_HTTPONLY_PREFIX) else line
        if not entry.strip() or entry.startswith("#"):
            continue
        fields = entry.split("\t")
        if len(fields) != 7 or not fields[0].strip():
            raise YtError("E_COOKIES_INVALID", f"line {number}: expected 7 tab-separated fields")
        if fields[4] and not _EXPIRES.fullmatch(fields[4]):
            raise YtError("E_COOKIES_INVALID", f"line {number}: expiry is not a number")
        if not _account_domain(fields[0]):
            continue
        # ช่องที่ 2 ต้องตรงกับจุดนำหน้าโดเมน (http.cookiejar assert ไว้ ส่วนขยายบางตัวเขียนไม่ตรง) จัดให้ตรงเอง
        fields[1] = "TRUE" if fields[0].startswith(".") else "FALSE"
        prefix = _HTTPONLY_PREFIX if line.startswith(_HTTPONLY_PREFIX) else ""
        kept.append(prefix + "\t".join(fields))
    jar = YoutubeDLCookieJar()
    try:
        jar.load(io.StringIO(_NETSCAPE_HEADER + "".join(f"{entry}\n" for entry in kept)))
    except Exception as exc:
        raise YtError("E_COOKIES_INVALID", type(exc).__name__) from None
    if not any(c.name in ACCOUNT_SIGN_IN_COOKIES and c.domain.lower().lstrip(".") == "youtube.com" for c in jar):
        raise YtError("E_COOKIES_INVALID", "no YouTube sign-in cookie")
    return jar


def _no_save() -> None:
    """save_cookies ของ YoutubeDL ที่ใช้บัญชี: ไม่เขียนอะไรเลย (คุกกี้ที่ยูทูปหมุนให้อยู่ใน jar ก้อนเดิมในหน่วยความจำ)"""


def _attach_account(ydl: Any, jar: Any) -> None:
    """ให้ YoutubeDL ตัวนี้ใช้ jar ของบัญชีชั่วคราว ไม่มี cookiefile และปิดตัวบันทึกคุกกี้

    API ภายในของ yt-dlp แบบเดียวกับ _attach_session (cookiejar เป็น cached_property ใส่ล่วงหน้าใน __dict__ ก่อนคำขอแรก)
    เทสสัญญา test_attach_account_on_a_real_youtubedl ตรวจกับ YoutubeDL จริงทุกครั้งที่อัปเดต yt-dlp
    """
    ydl.__dict__["cookiejar"] = jar
    ydl.save_cookies = _no_save


def visitor_session(folder: Path) -> VisitorSession:
```

Replace (4):
```python
        self.session = session

    @contextmanager
    def _ydl(self, opts: dict, *, with_session: bool = False) -> Iterator[Any]:
        """YoutubeDL หนึ่งตัว with_session = ใช้เซสชันผู้ชม (ผ่าน cookiefile) แล้วบันทึกคืนตอนปิด"""
        import yt_dlp

        # opts ที่มี logger ของตัวเอง (ตัวโหลดใช้ตัวที่ซ่อน path) ใช้ตัวนั้น ไม่งั้นใช้ตัวปกติ
        params = {"logger": _YtDlpLogger(), **opts}
        session = self.session if with_session else None
        if session is not None:
            params["cookiefile"] = str(session.path)
```
with:
```python
        self.session = session

    @contextmanager
    def _ydl(self, opts: dict, *, with_session: bool = False, with_account: Any | None = None) -> Iterator[Any]:
        """YoutubeDL หนึ่งตัว with_session = ใช้เซสชันผู้ชม (ผ่าน cookiefile) แล้วบันทึกคืนตอนปิด

        with_account = jar ของบัญชียูทูปชั่วคราว (M5 รอบ C): ใช้แทนเซสชันผู้ชม ไม่ใช่ทั้งสองอย่าง ไม่มี cookiefile
        ไม่บันทึกคุกกี้ลงไฟล์ และห้ามมีค่าตั้งที่พิมพ์คำขอ (ACCOUNT_FORBIDDEN_OPTS = ValueError)
        """
        import yt_dlp

        # opts ที่มี logger ของตัวเอง (ตัวโหลดใช้ตัวที่ซ่อน path) ใช้ตัวนั้น ไม่งั้นใช้ตัวปกติ
        params = {"logger": _YtDlpLogger(), **opts}
        if with_account is not None:
            forbidden = sorted(key for key in ACCOUNT_FORBIDDEN_OPTS if params.get(key))
            if forbidden:
                raise ValueError(f"ค่าตั้งเหล่านี้ใช้คู่กับบัญชีไม่ได้: {forbidden}")
            params.pop("cookiefile", None)
            with yt_dlp.YoutubeDL(params) as ydl:
                _attach_account(ydl, with_account)
                yield ydl
            return
        session = self.session if with_session else None
        if session is not None:
            params["cookiefile"] = str(session.path)
```

Replace (5):
```python
        from yt_dlp.utils import YoutubeDLError

        try:
            with self._ydl(_PROBE_OPTS, with_session=True) as ydl:
                with ydl.urlopen(_subtitle_request(ydl, url)) as resp:
                    return resp.read()
        except YtError:
```
with:
```python
        from yt_dlp.utils import YoutubeDLError

        try:
            with self._ydl(_PROBE_OPTS, with_session=True, with_account=current_jar()) as ydl:
                with ydl.urlopen(_subtitle_request(ydl, url)) as resp:
                    return resp.read()
        except YtError:
```

Replace (6):
```python
        ทำกับ --load-info-json (sanitize_info แบบ remove_private_keys) ก่อนส่งต่อ
        """
        try:
            with self._ydl(_PROBE_OPTS, with_session=True) as ydl:
                raw = ydl.extract_info(url, download=False)
                if raw is None:
                    raise YtError("E_UNKNOWN", f"yt-dlp ไม่คืนข้อมูลสำหรับ {url}")
```
with:
```python
        ทำกับ --load-info-json (sanitize_info แบบ remove_private_keys) ก่อนส่งต่อ
        """
        try:
            with self._ydl(_PROBE_OPTS, with_session=True, with_account=current_jar()) as ydl:
                raw = ydl.extract_info(url, download=False)
                if raw is None:
                    raise YtError("E_UNKNOWN", f"yt-dlp ไม่คืนข้อมูลสำหรับ {url}")
```

Replace (7):
```python
        """YoutubeDL ตัวที่สองโหลดตาม choice แล้วคืนไฟล์ใน workdir กับขนาดภาพของไฟล์นั้น"""
        from yt_dlp.utils import DownloadCancelled

        try:
            with self._ydl(_download_opts(choice, workdir, hooks), with_session=True) as ydl:
                result = ydl.process_ie_result(source, download=True)
            return _media_path(result, workdir), _downloaded_facts(result)
        except (YtError, JobCancelled):
```
with:
```python
        """YoutubeDL ตัวที่สองโหลดตาม choice แล้วคืนไฟล์ใน workdir กับขนาดภาพของไฟล์นั้น"""
        from yt_dlp.utils import DownloadCancelled

        account = current_jar()
        try:
            with self._ydl(_download_opts(choice, workdir, hooks), with_session=True, with_account=account) as ydl:
                result = ydl.process_ie_result(source, download=True)
            return _media_path(result, workdir), _downloaded_facts(result)
        except (YtError, JobCancelled):
```

Replace (8):
```python

        fetched = 0
        try:
            with self._ydl(_PROBE_OPTS, with_session=True) as ydl:
                raw = ydl.extract_info(f"https://www.youtube.com/watch?v={video_id}", download=False)
                if raw is None:
                    raise YtError("E_UNKNOWN", f"yt-dlp ไม่คืนข้อมูลสำหรับ {video_id}")
```
with:
```python

        fetched = 0
        try:
            with self._ydl(_PROBE_OPTS, with_session=True, with_account=current_jar()) as ydl:
                raw = ydl.extract_info(f"https://www.youtube.com/watch?v={video_id}", download=False)
                if raw is None:
                    raise YtError("E_UNKNOWN", f"yt-dlp ไม่คืนข้อมูลสำหรับ {video_id}")
```

Replace (9):
```python
        """เรียก yt-dlp แล้วแปลงทุกความผิดพลาดเป็น YtError (ห้ามมี exception ดิบหลุดออกไป)"""
        from yt_dlp.utils import YoutubeDLError

        try:
            with self._ydl(opts, with_session=with_session) as ydl:
                info = ydl.extract_info(url, download=False)
                if info is None:
                    raise YtError("E_UNKNOWN", f"yt-dlp ไม่คืนข้อมูลสำหรับ {url}")
```
with:
```python
        """เรียก yt-dlp แล้วแปลงทุกความผิดพลาดเป็น YtError (ห้ามมี exception ดิบหลุดออกไป)"""
        from yt_dlp.utils import YoutubeDLError

        # บัญชีชั่วคราวใช้เฉพาะคำขอที่ใช้เซสชันผู้ชมอยู่แล้ว (probe) เพลย์ลิสต์ไม่ใช้ (spec 2.4)
        account = current_jar() if with_session else None
        try:
            with self._ydl(opts, with_session=with_session, with_account=account) as ydl:
                info = ydl.extract_info(url, download=False)
                if info is None:
                    raise YtError("E_UNKNOWN", f"yt-dlp ไม่คืนข้อมูลสำหรับ {url}")
```

Replace (10):
```python
    งานโหลด (download) ทำตาม behaviors (C14 ค่าตั้งต้น <fixtures_root>/downloads/behaviors.json):
    จำนวนขั้น เวลาต่อขั้น และ error ที่ตั้งไว้ต่อคลิป แล้วคัดลอกไฟล์จาก media/ ไม่ใช้ ffmpeg ไม่ต่อเน็ต
    ภาพคมตรงจุด (fetch_frame_piece) ตัดชิ้นจาก capture/piece.mp4 ตาม "captureError" ใน behaviors (M5 รอบ B2)
    """

    PRIVATE_ID = "PRIVATEVID1"
```
with:
```python
    งานโหลด (download) ทำตาม behaviors (C14 ค่าตั้งต้น <fixtures_root>/downloads/behaviors.json):
    จำนวนขั้น เวลาต่อขั้น และ error ที่ตั้งไว้ต่อคลิป แล้วคัดลอกไฟล์จาก media/ ไม่ใช้ ffmpeg ไม่ต่อเน็ต
    ภาพคมตรงจุด (fetch_frame_piece) ตัดชิ้นจาก capture/piece.mp4 ตาม "captureError" ใน behaviors (M5 รอบ B2)
    "needsAccount" ของคลิป (M5 รอบ C) = probe แบบไม่ใช้บัญชีได้รหัสนั้น ใช้บัญชี (signed_in) แล้วผ่าน
    (download / fetch_frame_piece เรียก probe จึงได้กฎเดียวกัน) · PRIVATEVID1 ส่วนตัวเสมอ แม้ใช้บัญชี
    """

    PRIVATE_ID = "PRIVATEVID1"
```

Replace (11):
```python
                "E_VIDEO_PRIVATE", f"ERROR: [youtube] {video_id}: Private video"
            )
        entry = self._behavior_doc()["videos"].get(video_id) or {}
        probe_as = entry.get("probeAs")
        info = self._load("probe", probe_as if probe_as else video_id)
        if info is None:
```
with:
```python
                "E_VIDEO_PRIVATE", f"ERROR: [youtube] {video_id}: Private video"
            )
        entry = self._behavior_doc()["videos"].get(video_id) or {}
        needs = entry.get("needsAccount")
        if needs and current_jar() is None:
            raise YtError(str(needs), f"ERROR: [youtube] {video_id}: fake: needs a signed-in account")
        probe_as = entry.get("probeAs")
        info = self._load("probe", probe_as if probe_as else video_id)
        if info is None:
```

- [ ] **Step 5: Add the fake clips to `tests/fixtures/downloads/behaviors.json`**
Replace (1):
```json
    "CAPTURE0001": {"probeAs": "aqz-KE-bpKQ", "title": "คลิปถ่ายภาพคม"},
    "CAPTURENO01": {"probeAs": "aqz-KE-bpKQ", "title": "คลิปถ่ายภาพคมไม่ได้", "captureError": "E_CAPTURE_UNSUPPORTED"},
    "CAPTUREBOT1": {"probeAs": "aqz-KE-bpKQ", "title": "คลิปถ่ายภาพคมติดบอท", "captureError": "E_BOT_CHECK"},
    "CAPTURENET1": {"probeAs": "aqz-KE-bpKQ", "title": "คลิปถ่ายภาพคมเน็ตหลุด", "captureError": "E_NETWORK"}
  }
}
```
with:
```json
    "CAPTURE0001": {"probeAs": "aqz-KE-bpKQ", "title": "คลิปถ่ายภาพคม"},
    "CAPTURENO01": {"probeAs": "aqz-KE-bpKQ", "title": "คลิปถ่ายภาพคมไม่ได้", "captureError": "E_CAPTURE_UNSUPPORTED"},
    "CAPTUREBOT1": {"probeAs": "aqz-KE-bpKQ", "title": "คลิปถ่ายภาพคมติดบอท", "captureError": "E_BOT_CHECK"},
    "CAPTURENET1": {"probeAs": "aqz-KE-bpKQ", "title": "คลิปถ่ายภาพคมเน็ตหลุด", "captureError": "E_NETWORK"},
    "ACCOUNTAGE1": {"probeAs": "aqz-KE-bpKQ", "title": "คลิปจำกัดอายุ", "needsAccount": "E_AGE_RESTRICTED"},
    "ACCOUNTMEM1": {"probeAs": "aqz-KE-bpKQ", "title": "คลิปเฉพาะสมาชิก", "needsAccount": "E_VIDEO_PRIVATE"}
  }
}
```

- [ ] **Step 6: Run the tests, expect PASS** — same command as Step 2 plus `tests/unit/test_extractor.py` (the visitor-session contract test must still pass), then the full suite. `test_attach_account_on_a_real_youtubedl` must pass with the pinned yt-dlp; if it fails after a yt-dlp update, stop and report (internal API contract).

- [ ] **Step 7: Commit**
```bash
cd "$WORKTREE" && git add src/yttoolkit/core/account_scope.py src/yttoolkit/core/extractor.py tests/fixtures/downloads/behaviors.json tests/unit/test_extractor_download.py tests/unit/test_extractor_account.py && git commit -F- <<'EOF'
feat(extractor): M5-C account mode, in-memory cookies.txt parser and fake clips that need an account

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
EOF
```

### Task 5: Web strings, types, data layer, SSE `account` event; R7 axe-settle fix

**Files:**
- Modify: `web/src/i18n/th.ts` (`account` section, `settings.tabs.advanced`, `health.rows.account`)
- Modify: `web/src/lib/types.ts` (`AccountHealth`, `AccountStatus`, `Health.account?`, drop `Settings.cookies`)
- Create: `web/src/lib/account.ts`, `web/src/lib/account.test.ts`
- Modify: `web/src/lib/events.ts`, `web/src/lib/events.test.ts`
- Modify: `web/src/lib/settings-api.ts`
- Modify: `web/src/lib/download-options.test.ts`, `web/src/lib/download-prefs.test.ts`, `web/src/pages/settings/general-form.test.ts`, `web/src/pages/video/advanced/use-advanced-choice.test.ts` (drop the `cookies:` line of the `Settings` literal)
- Modify: `web/e2e/axe-settled.ts` (R7)

**Interfaces:**
- Consumes: `api`, `ApiError` (`lib/api.ts`), `connectEvents` / `applyServerEvent` / `parseServerEvent` (`lib/events.ts`), `QUEUE_KEY`/`JOBS_KEY` (`lib/jobs.ts`).
- Produces: C5 exactly (T8, T10, T11 import from these files; nobody else edits them).

- [ ] **Step 1: Write the failing tests** — create `web/src/lib/account.test.ts`:
```ts
import { describe, expect, it } from "vitest"

import {
  ACCOUNT_CODES,
  applyAccountEvent,
  DELETE_TIME_STYLE,
  deleteTime,
  fileTooBig,
  INACTIVE,
  isAccountCode,
  localClock,
  MAX_COOKIE_FILE_BYTES,
  needsAccount,
  remainingClock,
  showAccountButton,
} from "./account"
import { ApiError } from "./api"
import type { AccountStatus } from "./types"

const NOW = Date.parse("2026-10-06T03:00:00Z")
const ACTIVE: AccountStatus = {
  active: true,
  importedAt: "2026-10-06T03:00:00+00:00",
  expiresAt: "2026-10-06T05:00:00+00:00",
  used: false,
}

describe("error → ปุ่ม", () => {
  it("เฉพาะรหัสจำกัดอายุ / ส่วนตัว และยังไม่ได้ถือบัญชี", () => {
    expect([...ACCOUNT_CODES].sort()).toEqual(["E_AGE_RESTRICTED", "E_VIDEO_PRIVATE"])
    expect(showAccountButton("E_AGE_RESTRICTED", false)).toBe(true)
    expect(showAccountButton("E_VIDEO_PRIVATE", false)).toBe(true)
    expect(showAccountButton("E_VIDEO_PRIVATE", true)).toBe(false) // ถืออยู่แล้ว = ข้อความ "ลองด้วยบัญชีแล้ว…"
    for (const code of ["E_BOT_CHECK", "E_NETWORK", "E_GEO_BLOCKED", "E_UNKNOWN", undefined, null]) {
      expect(showAccountButton(code, false)).toBe(false)
    }
    expect(isAccountCode("E_AGE_RESTRICTED")).toBe(true)
  })

  it("needsAccount ดูเฉพาะ ApiError", () => {
    expect(needsAccount(new ApiError(409, "E_AGE_RESTRICTED", "m", null, null))).toBe(true)
    expect(needsAccount(new ApiError(429, "E_BOT_CHECK", "m", null, null))).toBe(false)
    expect(needsAccount(new Error("E_AGE_RESTRICTED"))).toBe(false)
  })
})

describe("remainingClock (แถบบนหน้า: ลบอัตโนมัติภายใน HH:MM)", () => {
  it("ชั่วโมง:นาทีที่เหลือ ปัดนาทีขึ้น", () => {
    expect(remainingClock("2026-10-06T05:00:00Z", NOW)).toBe("02:00")
    expect(remainingClock("2026-10-06T04:59:59Z", NOW)).toBe("02:00")
    expect(remainingClock("2026-10-06T03:09:01Z", NOW)).toBe("00:10")
    expect(remainingClock("2026-10-06T03:00:01Z", NOW)).toBe("00:01")
  })
  it("นาฬิกาของหน้าเว็บช้ากว่าเวลานำเข้า = นับจากเวลานำเข้า (ไม่โชว์ 02:01)", () => {
    expect(remainingClock("2026-10-06T05:00:00Z", NOW - 14_000, "2026-10-06T03:00:00Z")).toBe("02:00")
    expect(remainingClock("2026-10-06T03:10:00Z", NOW + 60_000, "2026-10-06T01:00:00Z")).toBe("00:09")
  })
  it("เลยเวลาแล้ว หรืออ่านไม่ได้ = 00:00", () => {
    expect(remainingClock("2026-10-06T02:00:00Z", NOW)).toBe("00:00")
    expect(remainingClock("nonsense", NOW)).toBe("00:00")
  })
})

describe("deleteTime (คำถามเปิด Q1: เวลาที่เหลือ หรือเวลาบนนาฬิกา)", () => {
  it("ค่าเริ่มต้นเป็นเวลาที่เหลือตามสเปก", () => {
    expect(DELETE_TIME_STYLE).toBe("remaining")
    expect(deleteTime({ expiresAt: "2026-10-06T05:00:00+00:00", importedAt: ACTIVE.importedAt }, NOW)).toBe("02:00")
  })
  it("แบบ clock = เวลาตามนาฬิกาของเครื่องตอนที่จะลบ", () => {
    const at = new Date(2026, 9, 6, 17, 5)
    expect(deleteTime({ expiresAt: at.toISOString() }, NOW, "clock")).toBe("17:05")
  })
})

describe("localClock (หน้าตรวจสุขภาพ: นำเข้าเมื่อ HH:MM)", () => {
  it("นาฬิกาตามเครื่อง สองหลัก", () => {
    const at = new Date(2026, 9, 6, 9, 5)
    expect(localClock(at.toISOString())).toBe("09:05")
  })
  it("อ่านไม่ได้ = ว่าง", () => {
    expect(localClock("x")).toBe("")
  })
})

describe("fileTooBig", () => {
  it("เกิน 1 MB เท่านั้น", () => {
    expect(fileTooBig(MAX_COOKIE_FILE_BYTES)).toBe(false)
    expect(fileTooBig(MAX_COOKIE_FILE_BYTES + 1)).toBe(true)
  })
})

describe("applyAccountEvent", () => {
  it("ลบแล้ว = ไม่ได้ใช้บัญชี", () => {
    expect(applyAccountEvent(ACTIVE, { active: false, reason: "expired" })).toEqual(INACTIVE)
    expect(applyAccountEvent(undefined, { active: false, reason: "manual" })).toEqual(INACTIVE)
  })
  it("ยังถืออยู่ = เปลี่ยนเวลาลบ (grace เริ่ม/ยกเลิก)", () => {
    expect(applyAccountEvent(ACTIVE, { active: true, expiresAt: "2026-10-06T03:10:00+00:00" })).toEqual({
      ...ACTIVE,
      expiresAt: "2026-10-06T03:10:00+00:00",
    })
  })
  it("เพิ่งนำเข้าจากแท็บอื่น = ไม่รู้เวลานำเข้า ต้องโหลดใหม่", () => {
    expect(applyAccountEvent(INACTIVE, { active: true, expiresAt: "2026-10-06T05:00:00+00:00" })).toBeUndefined()
    expect(applyAccountEvent(undefined, { active: true })).toBeUndefined()
  })
})
```

In `web/src/lib/events.test.ts`:
Replace (1):
```ts
  parseServerEvent,
  sharpRefreshTarget,
} from "./events"
import { JOBS_KEY, QUEUE_KEY } from "./jobs"
import type { Job, QueueState } from "./types"

/** ปล่อยให้ promise ที่ค้าง (ยกเลิกคำขอ แล้วโหลดใหม่) ทำงานจนจบ */
const flush = () => new Promise((resolve) => setTimeout(resolve, 0))
```
with:
```ts
  parseServerEvent,
  sharpRefreshTarget,
} from "./events"
import { ACCOUNT_KEY, INACTIVE } from "./account"
import { JOBS_KEY, QUEUE_KEY } from "./jobs"
import type { AccountStatus, Job, QueueState } from "./types"

/** ปล่อยให้ promise ที่ค้าง (ยกเลิกคำขอ แล้วโหลดใหม่) ทำงานจนจบ */
const flush = () => new Promise((resolve) => setTimeout(resolve, 0))
```

Replace (2):
```ts
    await flush()
    expect(invalidate).toHaveBeenCalledWith({ queryKey: JOBS_KEY })
    expect(invalidate).toHaveBeenCalledWith({ queryKey: QUEUE_KEY })
    expect(invalidate).toHaveBeenCalledTimes(2)
    source.emit("open")
    await flush()
    expect(invalidate).toHaveBeenCalledTimes(2)
  })

  it("open ระหว่างที่คำขอรายการงานแรกยังไม่ตอบ: ยกเลิกคำขอนั้นแล้วโหลดใหม่ (คำตอบเดิมคำนวณก่อนต่อติด)", async () => {
```
with:
```ts
    await flush()
    expect(invalidate).toHaveBeenCalledWith({ queryKey: JOBS_KEY })
    expect(invalidate).toHaveBeenCalledWith({ queryKey: QUEUE_KEY })
    expect(invalidate).toHaveBeenCalledWith({ queryKey: ACCOUNT_KEY })
    expect(invalidate).toHaveBeenCalledTimes(3)
    source.emit("open")
    await flush()
    expect(invalidate).toHaveBeenCalledTimes(3)
  })

  it("open ระหว่างที่คำขอรายการงานแรกยังไม่ตอบ: ยกเลิกคำขอนั้นแล้วโหลดใหม่ (คำตอบเดิมคำนวณก่อนต่อติด)", async () => {
```

Replace (3):
```ts
    await flush()
    expect(invalidate).toHaveBeenCalledWith({ queryKey: JOBS_KEY })
    expect(invalidate).toHaveBeenCalledWith({ queryKey: QUEUE_KEY })
    expect(invalidate).toHaveBeenCalledTimes(2)
    source.emit("open")
    await flush()
    expect(invalidate).toHaveBeenCalledTimes(2)
  })

  it("ฟังก์ชันที่คืนมาถอด listener ทั้งหมดและปิดการเชื่อมต่อ", () => {
    const client = new QueryClient()
    const { source, disconnect } = connect(client)
    expect(source.count()).toBe(7)
    disconnect()
    expect(source.count()).toBe(0)
    expect(source.closed).toBe(true)
```
with:
```ts
    await flush()
    expect(invalidate).toHaveBeenCalledWith({ queryKey: JOBS_KEY })
    expect(invalidate).toHaveBeenCalledWith({ queryKey: QUEUE_KEY })
    expect(invalidate).toHaveBeenCalledWith({ queryKey: ACCOUNT_KEY })
    expect(invalidate).toHaveBeenCalledTimes(3)
    source.emit("open")
    await flush()
    expect(invalidate).toHaveBeenCalledTimes(3)
  })

  it("ฟังก์ชันที่คืนมาถอด listener ทั้งหมดและปิดการเชื่อมต่อ", () => {
    const client = new QueryClient()
    const { source, disconnect } = connect(client)
    expect(source.count()).toBe(8)
    disconnect()
    expect(source.count()).toBe(0)
    expect(source.closed).toBe(true)
```

Replace (4):
```ts
    expect(spy).toHaveBeenCalledWith({ queryKey: ["sharp", "aqz-KE-bpKQ"] })
  })
})
```
with:
```ts
    expect(spy).toHaveBeenCalledWith({ queryKey: ["sharp", "aqz-KE-bpKQ"] })
  })
})

describe("ข่าวบัญชียูทูปชั่วคราว (M5 รอบ C)", () => {
  const ACTIVE: AccountStatus = {
    active: true,
    importedAt: "2026-10-06T03:00:00+00:00",
    expiresAt: "2026-10-06T05:00:00+00:00",
    used: true,
  }

  it("parseServerEvent อ่าน account (ไม่มีอย่างอื่นนอกจาก active / expiresAt / reason)", () => {
    expect(parseServerEvent("account", '{"active":false,"reason":"queue_done"}')).toEqual({
      type: "account",
      active: false,
      reason: "queue_done",
    })
    expect(parseServerEvent("account", '{"active":true,"expiresAt":"2026-10-06T03:10:00+00:00","x":1}')).toEqual({
      type: "account",
      active: true,
      expiresAt: "2026-10-06T03:10:00+00:00",
    })
    expect(parseServerEvent("account", '{"active":"yes"}')).toBeNull()
  })

  it("ลบแล้ว: แคชเป็นไม่ได้ใช้บัญชี และเรียก onAccount พร้อม reason", () => {
    const client = new QueryClient()
    client.setQueryData(ACCOUNT_KEY, ACTIVE)
    const onAccount = vi.fn()
    let source: FakeSource | undefined
    connectEvents(client, {
      onShutdown: vi.fn(),
      onAccount,
      createSource: (url) => {
        source = new FakeSource(url)
        return source as unknown as EventSource
      },
    })
    source!.emit("account", { active: true, expiresAt: "2026-10-06T03:10:00+00:00" })
    expect(client.getQueryData(ACCOUNT_KEY)).toEqual({ ...ACTIVE, expiresAt: "2026-10-06T03:10:00+00:00" })
    source!.emit("account", { active: false, reason: "expired" })
    expect(client.getQueryData(ACCOUNT_KEY)).toEqual(INACTIVE)
    expect(onAccount).toHaveBeenLastCalledWith({ type: "account", active: false, reason: "expired" })
  })

  it("นำเข้าจากแท็บอื่น: โหลดสถานะเต็มใหม่", () => {
    const client = new QueryClient()
    client.setQueryData(ACCOUNT_KEY, INACTIVE)
    const invalidate = vi.spyOn(client, "invalidateQueries")
    applyServerEvent(client, { type: "account", active: true, expiresAt: "2026-10-06T05:00:00+00:00" })
    expect(invalidate).toHaveBeenCalledWith({ queryKey: ACCOUNT_KEY })
  })
})
```

Drop the retired field from the four `Settings` literals:

`web/src/lib/download-options.test.ts`:
Replace (1):
```ts
    captureQuality: "max",
    theme: "system",
    filenameStyle: "title",
    cookies: { enabled: false, source: null, warningAccepted: false },
    statsResetAt: null,
    lastUsed: {},
  }
```
with:
```ts
    captureQuality: "max",
    theme: "system",
    filenameStyle: "title",
    statsResetAt: null,
    lastUsed: {},
  }
```

`web/src/lib/download-prefs.test.ts`:
Replace (1):
```ts
  captureQuality: "max",
  theme: "system",
  filenameStyle: "title",
  cookies: { enabled: false, source: null, warningAccepted: false },
  statsResetAt: null,
  lastUsed: {},
}
```
with:
```ts
  captureQuality: "max",
  theme: "system",
  filenameStyle: "title",
  statsResetAt: null,
  lastUsed: {},
}
```

`web/src/pages/settings/general-form.test.ts`:
Replace (1):
```ts
  captureQuality: "max",
  theme: "system",
  filenameStyle: "title",
  cookies: { enabled: false, source: null, warningAccepted: false },
  statsResetAt: null,
  lastUsed: {},
}
```
with:
```ts
  captureQuality: "max",
  theme: "system",
  filenameStyle: "title",
  statsResetAt: null,
  lastUsed: {},
}
```

`web/src/pages/video/advanced/use-advanced-choice.test.ts`:
Replace (1):
```ts
    captureQuality: "max",
    theme: "system",
    filenameStyle: "title",
    cookies: { enabled: false, source: null, warningAccepted: false },
    statsResetAt: null,
    lastUsed: {},
  }
```
with:
```ts
    captureQuality: "max",
    theme: "system",
    filenameStyle: "title",
    statsResetAt: null,
    lastUsed: {},
  }
```

- [ ] **Step 2: Run them, expect FAIL**

Run: `cd "$WORKTREE/web" && npx vitest run src/lib/account.test.ts src/lib/events.test.ts`
Expected: `Failed to resolve import "./account"` for both files.

- [ ] **Step 3: Strings and types**

`web/src/i18n/th.ts` (verbatim spec §7; the file picker's accessible name is `cookies.txt` until Pete gives a Thai label, Q2):
Replace (1):
```ts
    cancel: "ยกเลิก",
    deleted: "ลบภาพแล้ว",
  },
  subs: {
    title: "ซับ",
    loading: "กำลังโหลดซับ",
```
with:
```ts
    cancel: "ยกเลิก",
    deleted: "ลบภาพแล้ว",
  },
  // M5 รอบ C บัญชียูทูปชั่วคราว (สเปก 7 ทุกตัวอักษร · UI ไม่ใช้คำว่า "คุกกี้" มีแค่ชื่อไฟล์ cookies.txt)
  account: {
    use: "ใช้บัญชียูทูปชั่วคราว",
    title: "ใช้บัญชียูทูปชั่วคราว",
    warning:
      "บัญชี Google ที่ใช้อาจถูกจำกัดหรือถูกล็อก และกระทบ Gmail กับ Drive ของบัญชีนั้นได้ ใช้บัญชีสำรองเท่านั้น ห้ามใช้บัญชีเจ้าของช่องหรือบัญชีงานหลัก และอย่าส่งไฟล์ให้ใคร",
    privateClips: "คลิปส่วนตัว: ให้เจ้าของช่องแชร์คลิปให้อีเมลของบัญชีสำรองใน YouTube Studio ก่อน",
    steps: [
      "เปิดหน้าต่างไม่ระบุตัวตน (Ctrl+Shift+N)",
      "เข้าสู่ระบบยูทูปด้วยบัญชีสำรอง",
      "เปิด youtube.com/robots.txt ในแท็บเดิม",
      "ส่งออกไฟล์ cookies.txt ด้วยส่วนขยาย (ต้องอนุญาตให้ทำงานในหน้าต่างไม่ระบุตัวตน)",
      "เปิดหน้าต่างนั้นค้างไว้ ไม่ต้องเปิดยูทูปในหน้าต่างนั้น",
      "เลือกไฟล์ด้านล่าง",
    ],
    fileLabel: "cookies.txt",
    cancel: "ยกเลิก",
    importRetry: "นำเข้าแล้วลองใหม่",
    import: "นำเข้า",
    invalid: "ไฟล์นี้ใช้ไม่ได้ ตรวจว่าเข้าสู่ระบบยูทูปแล้วก่อนส่งออก แล้วส่งออก cookies.txt ใหม่",
    banner: "กำลังใช้บัญชียูทูปชั่วคราว · ลบอัตโนมัติภายใน {time}",
    removeNow: "ลบออกตอนนี้",
    removed: "ลบบัญชีออกจากแอพแล้ว · กลับไปกดออกจากระบบในหน้าต่างไม่ระบุตัวตน แล้วปิดหน้าต่าง",
    intro:
      "ใช้เมื่อต้องโหลดคลิปจำกัดอายุ คลิปส่วนตัว หรือคลิปเฉพาะสมาชิก แอพเก็บการเข้าสู่ระบบไว้ชั่วคราวและลบเองเมื่อโหลดเสร็จ",
    statusOff: "ไม่ได้ใช้บัญชี",
    statusOn: "ใช้บัญชีชั่วคราวอยู่ ลบอัตโนมัติภายใน {time}",
    healthOn: "ใช้บัญชีชั่วคราวอยู่ (นำเข้าเมื่อ {time})",
  },
  subs: {
    title: "ซับ",
    loading: "กำลังโหลดซับ",
```

Replace (2):
```ts
  },
  settings: {
    title: "ตั้งค่า",
    tabs: { health: "ตรวจสุขภาพระบบ", about: "เกี่ยวกับ", general: "ทั่วไป" },
  },
  health: {
    status: { ok: "พร้อม", warn: "เตือน", error: "ใช้ไม่ได้" },
```
with:
```ts
  },
  settings: {
    title: "ตั้งค่า",
    tabs: { health: "ตรวจสุขภาพระบบ", about: "เกี่ยวกับ", general: "ทั่วไป", advanced: "ขั้นสูง" },
  },
  health: {
    status: { ok: "พร้อม", warn: "เตือน", error: "ใช้ไม่ได้" },
```

Replace (3):
```ts
      disk: "พื้นที่ดิสก์",
      output: "โฟลเดอร์ผลลัพธ์",
      network: "การเชื่อมต่อยูทูป",
    },
    reinstallFfmpeg: "โหลด ffmpeg ใหม่",
    installing: "กำลังโหลด ffmpeg อาจใช้เวลา 1-3 นาที",
```
with:
```ts
      disk: "พื้นที่ดิสก์",
      output: "โฟลเดอร์ผลลัพธ์",
      network: "การเชื่อมต่อยูทูป",
      account: "บัญชียูทูป",
    },
    reinstallFfmpeg: "โหลด ffmpeg ใหม่",
    installing: "กำลังโหลด ffmpeg อาจใช้เวลา 1-3 นาที",
```

`web/src/lib/types.ts`:
Replace (1):
```ts
  path: string | null
}

export type Health = {
  version: string
  commit: string | null
```
with:
```ts
  path: string | null
}

/** แถว "บัญชียูทูป" ของ /health (M5 รอบ C): สถานะอย่างเดียว ไม่ต่อเน็ต ไม่มีชื่อหรือค่าคุกกี้ */
export type AccountHealth = { status: "ok"; active: boolean; importedAt: string | null }

export type Health = {
  version: string
  commit: string | null
```

Replace (2):
```ts
  disk: ToolStatus
  output: ToolStatus
  network: ToolStatus
  mode?: "fake" // มีเฉพาะตอน backend รันโหมดข้อมูลปลอม (serve + YT_TOOLKIT_FAKE=1)
}

export type VideoFormat = {
  formatId: string
```
with:
```ts
  disk: ToolStatus
  output: ToolStatus
  network: ToolStatus
  account?: AccountHealth // M5 รอบ C · backend รุ่นก่อนไม่มีแถวนี้
  mode?: "fake" // มีเฉพาะตอน backend รันโหมดข้อมูลปลอม (serve + YT_TOOLKIT_FAKE=1)
}

/** บัญชียูทูปชั่วคราว (M5 รอบ C, GET /cookies) · expiresAt = เวลาที่จะลบเองเร็วที่สุด (ครบ 2 ชม. หรือคิวว่างครบ 10 นาที) */
export type AccountStatus = { active: boolean; importedAt?: string; expiresAt?: string; used: boolean }

export type VideoFormat = {
  formatId: string
```

Replace (3):
```ts
  captureQuality: CaptureQuality
  theme: "system" | "dark" | "light"
  filenameStyle: "title" | "title-channel" | "title-quality"
  cookies: { enabled: boolean; source: "file" | "firefox" | null; warningAccepted: boolean; importedAt?: string }
  statsResetAt: string | null
  lastUsed: Record<string, unknown>
}
```
with:
```ts
  captureQuality: CaptureQuality
  theme: "system" | "dark" | "light"
  filenameStyle: "title" | "title-channel" | "title-quality"
  statsResetAt: string | null
  lastUsed: Record<string, unknown>
}
```

`web/src/lib/settings-api.ts`:
Replace (1):
```ts

/** เปลี่ยนเฉพาะค่าที่ส่งไป (ทั้งหมดหรือไม่เปลี่ยนเลย) คืนการตั้งค่าทั้งหมดหลังเปลี่ยน · ค่าผิด = ApiError 422 */
export function patchSettings(
  partial: Partial<Omit<Settings, "cookies" | "statsResetAt">>,
  deps?: ApiDeps
): Promise<Settings> {
  return api<Settings>(
```
with:
```ts

/** เปลี่ยนเฉพาะค่าที่ส่งไป (ทั้งหมดหรือไม่เปลี่ยนเลย) คืนการตั้งค่าทั้งหมดหลังเปลี่ยน · ค่าผิด = ApiError 422 */
export function patchSettings(
  partial: Partial<Omit<Settings, "statsResetAt">>,
  deps?: ApiDeps
): Promise<Settings> {
  return api<Settings>(
```

- [ ] **Step 4: Create `web/src/lib/account.ts`** (`DELETE_TIME_STYLE` is the Q1 one-line switch):
```ts
import { queryOptions } from "@tanstack/react-query"

import { api, ApiError } from "./api"
import type { AccountStatus } from "./types"

/** บัญชียูทูปชั่วคราว (M5 รอบ C): สถานะจาก GET /api/cookies ข่าว SSE "account" แก้แคชนี้ (events.ts) */
export const ACCOUNT_KEY = ["account"] as const

/** รหัสที่ใช้บัญชีชั่วคราวช่วยได้ (backend core/yterrors.ACCOUNT_CODES) ไม่รวม E_BOT_CHECK */
export const ACCOUNT_CODES: ReadonlySet<string> = new Set(["E_AGE_RESTRICTED", "E_VIDEO_PRIVATE"])

/** ไฟล์ cookies.txt ไม่เกิน 1 MB (backend ตอบ 413 เมื่อเกิน) */
export const MAX_COOKIE_FILE_BYTES = 1_048_576

export const INACTIVE: AccountStatus = { active: false, used: false }

/** ข่าว SSE "account": {active, expiresAt?, reason?} · reason = manual | queue_done | expired | shutdown */
export type AccountEvent = { active: boolean; expiresAt?: string; reason?: string }

/** สถานะบัญชี · SSE คอยแก้แคชให้ จึงไม่โหลดซ้ำเอง · backend รุ่นที่ไม่มี API นี้ (404) = ถือว่าไม่ได้ใช้บัญชี */
export function accountQuery() {
  return queryOptions({
    queryKey: ACCOUNT_KEY,
    queryFn: async ({ signal }): Promise<AccountStatus> => {
      try {
        return await api<AccountStatus>("/cookies", { signal })
      } catch (error) {
        if (error instanceof ApiError && error.status === 404) return INACTIVE
        throw error
      }
    },
    staleTime: Infinity,
    retry: false,
  })
}

/** นำเข้าข้อความของ cookies.txt (ยอมรับคำเตือนใน dialog แล้ว) · ใช้ไม่ได้ = ApiError 422/413 E_COOKIES_INVALID */
export function importAccount(text: string): Promise<AccountStatus> {
  return api<AccountStatus>("/cookies/import", { method: "POST", body: JSON.stringify({ text, acceptWarning: true }) })
}

/** ลบบัญชีออกจากแอพทันที (ไม่ต้องยืนยัน) */
export function deleteAccount(): Promise<AccountStatus> {
  return api<AccountStatus>("/cookies", { method: "DELETE" })
}

export function isAccountCode(code: string | null | undefined): boolean {
  return code != null && ACCOUNT_CODES.has(code)
}

/** error จาก backend ที่บัญชีชั่วคราวช่วยได้ (จำกัดอายุ / ส่วนตัว / เฉพาะสมาชิก) */
export function needsAccount(error: unknown): boolean {
  return error instanceof ApiError && isAccountCode(error.code)
}

/** ปุ่ม "ใช้บัญชียูทูปชั่วคราว" ขึ้นเมื่อรหัสเป็นของบัญชีและยังไม่ได้ถือบัญชี (ถืออยู่แล้ว = ข้อความ "ลองด้วยบัญชีแล้ว…" แทน) */
export function showAccountButton(code: string | null | undefined, active: boolean): boolean {
  return isAccountCode(code) && !active
}

/**
 * เวลาที่เหลือก่อนลบเอง "HH:MM" (ชั่วโมง:นาที ปัดนาทีขึ้น ไม่ติดลบ) เช่น 2 ชม. = "02:00" · 9 นาที 1 วินาที = "00:10"
 * importedAt = ไม่นับเวลาก่อนนำเข้า (นาฬิกาของหน้าเว็บเดินทุก 15 วินาที อาจช้ากว่าเวลานำเข้า ห้ามโชว์เกิน 2 ชม.)
 */
export function remainingClock(expiresAt: string, now: number, importedAt?: string): string {
  const end = Date.parse(expiresAt)
  const start = importedAt === undefined ? Number.NaN : Date.parse(importedAt)
  const from = Number.isNaN(start) ? now : Math.max(now, start)
  const minutes = Number.isNaN(end) ? 0 : Math.max(0, Math.ceil((end - from) / 60_000))
  return `${String(Math.floor(minutes / 60)).padStart(2, "0")}:${String(minutes % 60).padStart(2, "0")}`
}

/** นาฬิกาตามเครื่อง "HH:MM" ของเวลา ISO (เวลานำเข้าในหน้าตรวจสุขภาพ) อ่านไม่ได้ = "" */
export function localClock(iso: string): string {
  const at = new Date(iso)
  if (Number.isNaN(at.getTime())) return ""
  return `${String(at.getHours()).padStart(2, "0")}:${String(at.getMinutes()).padStart(2, "0")}`
}

/**
 * คำถามเปิด Q1 ของพี่พิธ: "ลบอัตโนมัติภายใน HH:MM" ของแถบบนหน้าและแท็บขั้นสูง
 * "remaining" = เวลาที่เหลือ ("02:00" = อีก 2 ชั่วโมง) ตามสเปก 6 · "clock" = เวลาบนนาฬิกาที่จะลบ (เช่น "17:05")
 * เปลี่ยนแบบที่แสดงได้ด้วยบรรทัดนี้บรรทัดเดียว
 */
export const DELETE_TIME_STYLE = "remaining" as "remaining" | "clock"

/** เวลาใน "ลบอัตโนมัติภายใน {time}" ตาม DELETE_TIME_STYLE (หรือ style ที่ส่งมา สำหรับเทส) */
export function deleteTime(
  status: { expiresAt: string; importedAt?: string },
  now: number,
  style: "remaining" | "clock" = DELETE_TIME_STYLE,
): string {
  return style === "clock" ? localClock(status.expiresAt) : remainingClock(status.expiresAt, now, status.importedAt)
}

export function fileTooBig(size: number): boolean {
  return size > MAX_COOKIE_FILE_BYTES
}

/**
 * ใส่ข่าว SSE ลงสถานะในแคช: ไม่ถือบัญชี = INACTIVE · ยังถืออยู่ = เวลาลบใหม่ (grace เริ่ม/ยกเลิก)
 * · เพิ่งนำเข้าแต่แคชไม่รู้เวลานำเข้า = undefined (ผู้เรียกโหลดสถานะเต็มใหม่)
 */
export function applyAccountEvent(prev: AccountStatus | undefined, event: AccountEvent): AccountStatus | undefined {
  if (!event.active) return INACTIVE
  if (prev?.active && event.expiresAt !== undefined) return { ...prev, expiresAt: event.expiresAt }
  return undefined
}
```

- [ ] **Step 5: The SSE `account` event in `web/src/lib/events.ts`**
Replace (1):
```ts
import type { QueryClient } from "@tanstack/react-query"
import { useSyncExternalStore } from "react"

import { JOBS_KEY, mergeJobPatch, QUEUE_KEY, upsertJob } from "./jobs"
import { sharpKey } from "./sharp-frames"
import type { Job, JobPatch, QueueState } from "./types"

/** เหตุการณ์จาก GET /api/events (SSE สัญญา C6) ที่อ่านแล้ว */
export type ServerEvent =
```
with:
```ts
import type { QueryClient } from "@tanstack/react-query"
import { useSyncExternalStore } from "react"

import { ACCOUNT_KEY, applyAccountEvent, type AccountEvent } from "./account"
import { JOBS_KEY, mergeJobPatch, QUEUE_KEY, upsertJob } from "./jobs"
import { sharpKey } from "./sharp-frames"
import type { AccountStatus, Job, JobPatch, QueueState } from "./types"

/** เหตุการณ์จาก GET /api/events (SSE สัญญา C6) ที่อ่านแล้ว */
export type ServerEvent =
```

Replace (2):
```ts
  | { type: "queue.paused"; until: string; reason: string }
  | { type: "queue.resumed" }
  | { type: "app.shutdown" }

export const EVENTS_URL = "/api/events"
```
with:
```ts
  | { type: "queue.paused"; until: string; reason: string }
  | { type: "queue.resumed" }
  | { type: "app.shutdown" }
  | ({ type: "account" } & AccountEvent)

export const EVENTS_URL = "/api/events"
```

Replace (3):
```ts
  "queue.paused",
  "queue.resumed",
  "app.shutdown",
] as const

const isRecord = (value: unknown): value is Record<string, unknown> =>
```
with:
```ts
  "queue.paused",
  "queue.resumed",
  "app.shutdown",
  "account",
] as const

const isRecord = (value: unknown): value is Record<string, unknown> =>
```

Replace (4):
```ts
      return { type: "queue.resumed" }
    case "app.shutdown":
      return { type: "app.shutdown" }
    default:
      return null
  }
```
with:
```ts
      return { type: "queue.resumed" }
    case "app.shutdown":
      return { type: "app.shutdown" }
    case "account": {
      // M5 รอบ C: {active, expiresAt?, reason?} ไม่มีชื่อหรือค่าคุกกี้
      if (typeof body.active !== "boolean") return null
      const event: { type: "account" } & AccountEvent = { type: "account", active: body.active }
      if (typeof body.expiresAt === "string") event.expiresAt = body.expiresAt
      if (typeof body.reason === "string") event.reason = body.reason
      return event
    }
    default:
      return null
  }
```

Replace (5):
```ts
      return {}
    case "app.shutdown":
      return {}
  }
}
```
with:
```ts
      return {}
    case "app.shutdown":
      return {}
    case "account": {
      const next = applyAccountEvent(client.getQueryData<AccountStatus>(ACCOUNT_KEY), event)
      // เพิ่งนำเข้า (จากแท็บอื่น) ยังไม่รู้เวลานำเข้า = โหลดสถานะเต็มใหม่
      if (next === undefined) void client.invalidateQueries({ queryKey: ACCOUNT_KEY })
      else client.setQueryData<AccountStatus>(ACCOUNT_KEY, next)
      return {}
    }
  }
}
```

Replace (6):
```ts
  onShutdown: () => void
  /** สถานะของงานเปลี่ยนในแท็บนี้ (before = ไม่รู้จักงานนี้มาก่อน) */
  onJobChange?: (before: Job | undefined, after: Job) => void
  /** สำหรับเทส: สร้าง EventSource ปลอม */
  createSource?: (url: string) => EventSource
}
```
with:
```ts
  onShutdown: () => void
  /** สถานะของงานเปลี่ยนในแท็บนี้ (before = ไม่รู้จักงานนี้มาก่อน) */
  onJobChange?: (before: Job | undefined, after: Job) => void
  /** ข่าวบัญชียูทูปชั่วคราว (M5 รอบ C) หลังใส่ลงแคชแล้ว: มี reason = เพิ่งถูกลบ (ทุกแท็บเด้ง toast) */
  onAccount?: (event: AccountEvent) => void
  /** สำหรับเทส: สร้าง EventSource ปลอม */
  createSource?: (url: string) => EventSource
}
```

Replace (7):
```ts
        return
      }
      const { before, after } = applyServerEvent(client, event)
      if (after !== undefined && before?.status !== after.status) {
        const refresh = sharpRefreshTarget(before, after)
        if (refresh !== null)
```
with:
```ts
        return
      }
      const { before, after } = applyServerEvent(client, event)
      if (event.type === "account") {
        opts.onAccount?.(event)
        return
      }
      if (after !== undefined && before?.status !== after.status) {
        const refresh = sharpRefreshTarget(before, after)
        if (refresh !== null)
```

Replace (8):
```ts
    lostConnection = false
    reload(client, JOBS_KEY)
    reload(client, QUEUE_KEY)
  }

  for (const [name, handler] of handlers) source.addEventListener(name, handler)
```
with:
```ts
    lostConnection = false
    reload(client, JOBS_KEY)
    reload(client, QUEUE_KEY)
    reload(client, ACCOUNT_KEY) // ข่าวบัญชีที่พลาดไประหว่างหลุด (เช่นถูกลบเพราะครบเวลา)
  }

  for (const [name, handler] of handlers) source.addEventListener(name, handler)
```

- [ ] **Step 6: Run the web checks, expect PASS**

Run: `cd "$WORKTREE/web" && npm run typecheck && npm run lint && npm test` (the new `account.test.ts` and the `events.test.ts` additions pass; listener count 8; reconnect invalidates 3 keys).

- [ ] **Step 7: Commit**
```bash
cd "$WORKTREE" && git add web/src/i18n/th.ts web/src/lib/types.ts web/src/lib/account.ts web/src/lib/account.test.ts web/src/lib/events.ts web/src/lib/events.test.ts web/src/lib/settings-api.ts web/src/lib/download-options.test.ts web/src/lib/download-prefs.test.ts web/src/pages/settings/general-form.test.ts web/src/pages/video/advanced/use-advanced-choice.test.ts && git commit -F- <<'EOF'
feat(web): M5-C account strings, types, data layer and the SSE account event

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
EOF
```

- [ ] **Step 8: R7 — let axe settle while a job's progress bar keeps moving**

The failing test is `web/e2e/queue-flow.spec.ts:297` (pre-existing at `4b02feb`): with `SLOWDOWNLD1` running, every progress event restarts the queue bar line's `width` transition, so `settleAnimations` polls until its 5 s timeout. Replace the whole file `web/e2e/axe-settled.ts` with:
```ts
import AxeBuilder from "@axe-core/playwright"
import { expect, type Page } from "@playwright/test"

/**
 * แถบความคืบหน้าที่ยาวตาม % ของงาน: ทุกครั้งที่งานรายงาน % ความกว้างเริ่มทรานซิชันใหม่ ระหว่างงานวิ่งจึงไม่มีวันนิ่ง
 * ทรานซิชัน "width" ของสองตัวนี้ไม่เปลี่ยนสี (axe จึงอ่านคอนทราสต์ได้ถูกอยู่แล้ว) จึงไม่ต้องรอ ทรานซิชันอื่นของมันยังรอตามปกติ
 * - queue-bar-progress = เส้นอำพันบนแถบคิว (components/queue/queue-bar.tsx)
 * - progress-indicator = Progress ของ shadcn (แถวงานที่กำลังทำในชีตคิว)
 */
export const KEEPS_ANIMATING = '[data-testid="queue-bar-progress"], [data-slot="progress-indicator"]'

/**
 * รอให้ทรานซิชัน/แอนิเมชันของหน้าจบก่อน แล้วค่อยให้ axe วัด
 * เหตุผล: axe อ่านสีที่ "คำนวณแล้ว" ตอนนั้น ถ้าปุ่มกำลังไล่สี (เช่น ปุ่มที่เพิ่งกด หรือเพิ่งสลับธีม)
 * จะได้สีกลางทางที่คอนทราสต์ต่ำชั่วขณะ แล้วเทสต์ล้มเป็นครั้งคราวเฉพาะตอนเครื่องหน่วง
 * ทรานซิชันของ CSS นับอยู่ใน document.getAnimations() ด้วย
 * (แอนิเมชันที่วนไม่รู้จบ เช่นวงหมุนโหลด ไม่มีวันจบ จึงข้าม · ทรานซิชัน width ของแถบความคืบหน้า KEEPS_ANIMATING ก็ข้าม)
 */
export async function settleAnimations(page: Page) {
  await expect
    .poll(
      () =>
        page.evaluate(async (keepsAnimating) => {
          // รอสองเฟรมก่อน เพื่อให้ทรานซิชันที่เพิ่งถูกสั่งเริ่มวิ่งจริง (จะได้อยู่ในรายการ)
          await new Promise<void>((resolve) => requestAnimationFrame(() => requestAnimationFrame(() => resolve())))
          const progressWidth = (a: Animation) => {
            const target = a.effect instanceof KeyframeEffect ? a.effect.target : null
            return a instanceof CSSTransition && a.transitionProperty === "width" && target?.matches(keepsAnimating) === true
          }
          return document
            .getAnimations()
            .filter((a) => a.playState === "running" && a.effect?.getComputedTiming().iterations !== Infinity)
            .filter((a) => !progressWidth(a)).length
        }, KEEPS_ANIMATING),
      { message: "รอให้ทรานซิชัน/แอนิเมชันจบก่อนตรวจ axe" },
    )
    .toBe(0)
}

/** รัน axe หลังรอให้หน้านิ่ง (เงื่อนไขตรวจไม่ผ่อน ไม่ยกเว้นกฎหรือโหนดใด ๆ) ใช้ configure ถ้าต้องตั้งขอบเขตเพิ่ม */
export async function analyzeSettled(page: Page, configure?: (builder: AxeBuilder) => AxeBuilder) {
  await settleAnimations(page)
  const builder = new AxeBuilder({ page })
  return (configure ? configure(builder) : builder).analyze()
}
```

Do not change any spec, do not exclude rules or nodes, do not add a `data-*` attribute to app code. Run `cd "$WORKTREE/web" && npx tsc -p tsconfig.node.json --noEmit && npx eslint e2e/axe-settled.ts` (Playwright runs at gate 1: `queue-flow.spec.ts` all 8 + `settings-general.spec.ts` + `nav.spec.ts`).

- [ ] **Step 9: Commit**
```bash
cd "$WORKTREE" && git add web/e2e/axe-settled.ts && git commit -F- <<'EOF'
test(e2e): M5-C axe settle ignores only the width transition of progress bars

queue-flow.spec.ts:297 never settled while a slow fake job reported progress:
each progress event restarts the queue bar line's width transition. Width
transitions of the documented KEEPS_ANIMATING selector do not change colours,
so they are no longer awaited; every other transition still is, and axe still
scans the whole page with no rule or node excluded.

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
EOF
```

---


## Wave 2

### Task 6: Retry rule at every call site; signed-in probes kept in memory only

**Files:**
- Modify: `src/yttoolkit/core/account_scope.py` (part 2: `AccountGate`, `with_account_retry`)
- Modify: `src/yttoolkit/core/videos.py` (`_signed` memory copies, `forget_signed_in`, `_probe_signed_in`, `get` / `raw`)
- Modify: `src/yttoolkit/core/handlers.py` (`HandlerDeps.accounts`, `bind` wraps the whole job)
- Modify: `src/yttoolkit/core/capture.py` (`accounts=` kwarg, `capture` wraps `_capture_once`)
- Modify: `src/yttoolkit/api/videos.py` (`ctx_accounts`, `GET /videos/{id}` wrapped)
- Test: `tests/unit/test_account_retry.py`, `tests/unit/test_videos_account.py`, `tests/unit/test_handlers_account.py`, `tests/unit/test_capture_account.py` (new), `tests/api/test_videos_api.py` (append)

**Interfaces:**
- Consumes: C1 (`ACCOUNT_CODES`, `ACCOUNT_TRIED_MESSAGE`, `YtError(account_tried=)`, T1), C4 (`current_jar`, `signed_in`, `FakeExtractor` `needsAccount`, `ACCOUNTAGE1`, T4); `VideoService.get/raw` (`core/videos.py:576, 709`), `build_handlers.bind` (`core/handlers.py:1108`), `CaptureService.capture` (`core/capture.py:250`), `video_info` (`api/videos.py:238`), `tests/helpers_capture.py`.
- Produces: C6 exactly. `AccountService` (T3) satisfies `AccountGate` structurally; T9 wires it (`deps.accounts`, `CaptureService(accounts=)`, `on_clear=videos.forget_signed_in`, `ctx.accounts`). `api/videos.py` reads `ctx.accounts` with `getattr` so this lane does not need T7's `AppContext` field.

- [ ] **Step 1: Write the failing tests**

Create `tests/unit/test_account_retry.py`:
```python
"""กฎลองซ้ำด้วยบัญชียูทูปชั่วคราว (core/account_scope.with_account_retry · M5 รอบ C spec 2.4)

ทุกจุดเรียกยูทูป (probe ของหน้า W2, งานในคิว, ถ่ายภาพคม) ใช้ตัวนี้ตัวเดียว เทสที่นี่ครอบกฎ เทสของแต่ละจุดเรียกอยู่ใน
test_videos_account.py, test_handlers_account.py, test_capture_account.py และ tests/api/test_videos_api.py
"""

from __future__ import annotations

from typing import Any

import pytest

from yttoolkit.core.account_scope import current_jar, signed_in, with_account_retry
from yttoolkit.core.yterrors import ACCOUNT_TRIED_MESSAGE, MESSAGES, YtError

JAR = object()


class Gate:
    def __init__(self, jar: Any | None = JAR) -> None:
        self._jar = jar
        self.used: list[str | None] = []

    def jar(self) -> Any | None:
        return self._jar

    def mark_used(self, job_id: str | None) -> None:
        self.used.append(job_id)


class Call:
    """จำลองคำขอ: anonymous / signed = รหัส error ของแต่ละแบบ (None = สำเร็จ) และจดว่ารอบไหนใช้ jar อะไร"""

    def __init__(self, anonymous: str | None, signed: str | None = None) -> None:
        self.anonymous = anonymous
        self.signed = signed
        self.jars: list[Any] = []

    def __call__(self) -> str:
        jar = current_jar()
        self.jars.append(jar)
        code = self.anonymous if jar is None else self.signed
        if code is not None:
            raise YtError(code, f"ERROR: [youtube] x: raw yt-dlp text Cookie: SAPISID=secret ({code})")
        return "ok"


@pytest.mark.parametrize("code", ["E_AGE_RESTRICTED", "E_VIDEO_PRIVATE"])
def test_account_codes_retry_once_signed_in(code: str) -> None:
    gate, call = Gate(), Call(anonymous=code)
    assert with_account_retry(gate, call, job_id="job-1") == "ok"
    assert call.jars == [None, JAR]
    assert gate.used == ["job-1"]
    assert current_jar() is None  # ขอบเขตจบพร้อมงาน


def test_success_needs_no_account() -> None:
    gate, call = Gate(), Call(anonymous=None)
    assert with_account_retry(gate, call) == "ok"
    assert call.jars == [None] and gate.used == []


@pytest.mark.parametrize("code", ["E_BOT_CHECK", "E_NETWORK", "E_GEO_BLOCKED", "E_LIVE_NOT_READY", "E_VIDEO_UNAVAILABLE"])
def test_other_codes_never_use_the_account(code: str) -> None:
    gate, call = Gate(), Call(anonymous=code)
    with pytest.raises(YtError) as info:
        with_account_retry(gate, call)
    assert info.value.code == code and info.value.account_tried is False
    assert call.jars == [None] and gate.used == []


def test_no_account_held_keeps_the_plain_error() -> None:
    call = Call(anonymous="E_AGE_RESTRICTED")
    for gate in (None, Gate(jar=None)):
        with pytest.raises(YtError) as info:
            with_account_retry(gate, call)
        assert info.value.message == MESSAGES["E_AGE_RESTRICTED"]
        assert "SAPISID" in info.value.detail  # ข้อความดิบของรอบไม่ใช้บัญชีคงเดิม (ไม่มีคุกกี้ในรอบนี้)


@pytest.mark.parametrize("code", ["E_AGE_RESTRICTED", "E_VIDEO_PRIVATE"])
def test_signed_in_failure_with_the_same_code_uses_the_tried_copy(code: str) -> None:
    gate, call = Gate(), Call(anonymous=code, signed=code)
    with pytest.raises(YtError) as info:
        with_account_retry(gate, call)
    err = info.value
    assert err.code == code and err.account_tried is True and err.message == ACCOUNT_TRIED_MESSAGE
    assert err.detail == f"signed-in retry failed ({code})"
    assert err.__cause__ is None and err.__suppress_context__ is True  # ไม่มีข้อความดิบของรอบที่ใช้บัญชีหลุดไป log
    assert gate.jar() is JAR  # บัญชียังอยู่ (อาจแค่ไม่มีสิทธิ์ดูคลิปนี้)


def test_signed_in_bot_check_keeps_its_code_for_the_queue_brake() -> None:
    gate, call = Gate(), Call(anonymous="E_AGE_RESTRICTED", signed="E_BOT_CHECK")
    with pytest.raises(YtError) as info:
        with_account_retry(gate, call)
    assert info.value.code == "E_BOT_CHECK" and info.value.account_tried is False
    assert "SAPISID" not in str(info.value)


def test_inside_a_signed_in_scope_there_is_no_second_retry() -> None:
    gate, call = Gate(), Call(anonymous="E_AGE_RESTRICTED", signed="E_AGE_RESTRICTED")
    other = object()
    with signed_in(other):
        with pytest.raises(YtError) as info:
            with_account_retry(gate, call)
    assert call.jars == [other] and gate.used == []
    assert info.value.account_tried is False  # รอบนอก (ผู้เปิดขอบเขต) เป็นคนตัดสินข้อความ


def test_interactive_use_is_marked_without_a_job_id() -> None:
    gate = Gate()
    with_account_retry(gate, Call(anonymous="E_VIDEO_PRIVATE"))
    assert gate.used == [None]
```

Create `tests/unit/test_videos_account.py`:
```python
"""VideoService กับบัญชียูทูปชั่วคราว (M5 รอบ C spec 2.4 "Cache"): probe ที่ใช้บัญชีอยู่ในหน่วยความจำ ไม่ลงฐานข้อมูล"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from yttoolkit.core.account_scope import signed_in
from yttoolkit.core.db import Database
from yttoolkit.core.extractor import FakeExtractor
from yttoolkit.core.videos import VideoService
from yttoolkit.core.yterrors import YtError

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
AGE = "ACCOUNTAGE1"
BBB = "aqz-KE-bpKQ"


@pytest.fixture
def env(tmp_path: Path):
    db = Database(tmp_path / "app.db")
    db.migrate()
    fake = FakeExtractor(FIXTURES)
    videos = VideoService(db, fake, now=lambda: datetime(2026, 10, 6, 3, tzinfo=UTC))
    yield db, fake, videos
    db.close()


def _rows(db: Database, video_id: str) -> list:
    return db.execute("SELECT video_id FROM videos WHERE video_id = ?", (video_id,))


def _probes(fake: FakeExtractor) -> int:
    return sum(1 for name, _ in fake.calls if name == "probe")


def test_signed_in_probe_is_never_written_to_the_database(env) -> None:
    db, fake, videos = env
    with signed_in(object()):
        info = videos.get(AGE)
    assert info["videoId"] == AGE and info["title"] == "คลิปจำกัดอายุ"
    assert _rows(db, AGE) == []
    assert videos.recent(10, scope="all") == ([], 0)


def test_the_kept_copy_serves_later_reads_without_the_account(env) -> None:
    db, fake, videos = env
    with signed_in(object()):
        videos.get(AGE, peek=True)
    before = _probes(fake)
    assert videos.get(AGE)["title"] == "คลิปจำกัดอายุ"  # หน้า W2 แท็บอื่น / ตัวทำงานในคิว อ่านซ้ำได้
    assert videos.raw(AGE)["id"] == AGE  # storyboard / ภาพคมอ่านข้อมูลดิบที่ตัดแล้ว
    assert _probes(fake) == before
    assert _rows(db, AGE) == []


def test_forget_signed_in_drops_every_kept_copy(env) -> None:
    db, fake, videos = env
    with signed_in(object()):
        videos.get(AGE)
    videos.forget_signed_in()
    with pytest.raises(YtError) as info:
        videos.get(AGE)  # ไม่มีบัญชีแล้ว: probe แบบไม่ใช้บัญชี ได้ error เดิม
    assert info.value.code == "E_AGE_RESTRICTED"


def test_raw_inside_a_scope_probes_signed_in(env) -> None:
    db, fake, videos = env
    with signed_in(object()):
        assert videos.raw(AGE)["id"] == AGE
    assert _rows(db, AGE) == []


def test_kept_copies_are_independent(env) -> None:
    db, fake, videos = env
    with signed_in(object()):
        videos.get(AGE)
    videos.raw(AGE)["title"] = "เปลี่ยน"
    assert videos.get(AGE)["title"] == "คลิปจำกัดอายุ"


def test_public_clips_still_use_the_database_cache(env) -> None:
    db, fake, videos = env
    videos.get(BBB)
    assert len(_rows(db, BBB)) == 1
    with signed_in(object()):
        assert videos.get(BBB)["videoId"] == BBB  # มี cache อยู่แล้ว ไม่ probe ใหม่ด้วยบัญชี
    assert _probes(fake) == 1
```

Create `tests/unit/test_handlers_account.py`:
```python
"""งานในคิวกับบัญชียูทูปชั่วคราว (M5 รอบ C spec 2.4): ทั้งงานลองแบบไม่ใช้บัญชีก่อน แล้วทำใหม่ทั้งงานด้วยบัญชีครั้งเดียว

ใช้ FakeExtractor ตัวจริง (คลิป ACCOUNTAGE1 ต้องใช้บัญชี · PRIVATEVID1 ส่วนตัวเสมอ) FakeMediaTools และฐานข้อมูลชั่วคราว
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from yttoolkit.core.account_scope import current_jar
from yttoolkit.core.cancel import JobCancelled
from yttoolkit.core.db import Database
from yttoolkit.core.extractor import FakeExtractor
from yttoolkit.core.handlers import HandlerDeps, build_handlers
from yttoolkit.core.jobs import Job
from yttoolkit.core.media import FakeMediaTools
from yttoolkit.core.subtitles import SubtitleService
from yttoolkit.core.videos import VideoService
from yttoolkit.core.yterrors import ACCOUNT_TRIED_MESSAGE, YtError

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
AGE = "ACCOUNTAGE1"
PRIVATE = FakeExtractor.PRIVATE_ID
JAR = object()


class Gate:
    def __init__(self, jar: Any | None = JAR) -> None:
        self._jar = jar
        self.used: list[str | None] = []

    def jar(self) -> Any | None:
        return self._jar

    def mark_used(self, job_id: str | None) -> None:
        self.used.append(job_id)


class Ctx:
    def __init__(self, workdir: Path, output_root: Path) -> None:
        self.job_id = "01900000-0000-7000-8000-00000000000c"
        self.workdir = workdir
        self.output_root = output_root
        self.stages: list[str] = []

    def stage(self, stage: str) -> None:
        self.stages.append(stage)

    def progress(self, fraction: float | None, speed_bps: int | None = None, eta_s: int | None = None) -> None:
        pass

    def set_title(self, title: str) -> None:
        pass

    def cancelled(self) -> bool:
        return False

    def check_cancelled(self) -> None:
        if self.cancelled():
            raise JobCancelled()

    def wait(self, seconds: float) -> None:
        pass


class SpyExtractor(FakeExtractor):
    """FakeExtractor ที่จดว่า download แต่ละครั้งรันใต้บัญชีไหม"""

    def __init__(self, root: Path, behaviors: Path) -> None:
        super().__init__(root, behaviors=behaviors)
        self.download_jars: list[Any] = []

    def download(self, video_id, choose, workdir, hooks):  # type: ignore[override]
        self.download_jars.append(current_jar())
        return super().download(video_id, choose, workdir, hooks)


@pytest.fixture
def env(tmp_path: Path):
    doc = json.loads((FIXTURES / "downloads" / "behaviors.json").read_text(encoding="utf-8"))
    for entry in [doc["default"], *doc["videos"].values()]:
        entry["stepMs"] = 0
    behaviors = tmp_path / "behaviors.json"
    behaviors.write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")
    db = Database(tmp_path / "app.db")
    db.migrate()
    fake = SpyExtractor(FIXTURES, behaviors)
    videos = VideoService(db, fake)
    deps = HandlerDeps(
        videos=videos,
        downloader=fake,  # type: ignore[arg-type]
        media=FakeMediaTools(FIXTURES / "media"),
        subtitles=SubtitleService(videos, fake.fetch_subtitle, tmp_path / "cache"),
        cache_root=tmp_path / "cache",
    )
    yield deps, fake, db, tmp_path
    db.close()


def _job(video_id: str, kind: str = "video", params: dict | None = None) -> Job:
    base = {"maxQuality": False, "splitChapters": False, "noAudio": False, "audioLanguage": "original"}
    return Job(
        id=f"job-{video_id}", video_id=video_id, title="", kind=kind, params=base if params is None else params,
        status="running", stage=None, progress=None, speed_bps=None, eta_s=None, attempt=0, bot_checks=0, position=1,
        error_code=None, error_message=None, error_detail=None, notes=(), outputs=(),
        created_at="2026-10-06T03:00:00.000000+00:00", started_at="2026-10-06T03:00:01.000000+00:00", finished_at=None,
    )  # fmt: skip


def _run(env, job: Job):
    deps, fake, db, tmp = env
    work = tmp / "work" / job.id
    work.mkdir(parents=True, exist_ok=True)
    return build_handlers(deps)[job.kind](job, Ctx(work, tmp / "out"))


def test_restricted_video_job_retries_the_whole_job_with_the_account(env) -> None:
    deps, fake, db, tmp = env
    deps.accounts = gate = Gate()
    result = _run(env, _job(AGE))
    (output,) = result.outputs
    assert (tmp / "out" / output.rel).is_file()
    assert fake.download_jars == [JAR]  # รอบแรกพลาดตั้งแต่ probe จึงไม่ถึงขั้นโหลด · รอบสองโหลดด้วยบัญชี
    assert gate.used == [f"job-{AGE}"]
    assert db.execute("SELECT video_id FROM videos WHERE video_id = ?", (AGE,)) == []


def test_without_an_account_the_job_fails_with_the_plain_copy(env) -> None:
    deps, fake, db, tmp = env
    with pytest.raises(YtError) as info:
        _run(env, _job(AGE))
    assert info.value.code == "E_AGE_RESTRICTED" and info.value.account_tried is False


def test_an_account_without_access_fails_with_the_tried_copy(env) -> None:
    deps, fake, db, tmp = env
    deps.accounts = Gate()
    with pytest.raises(YtError) as info:
        _run(env, _job(PRIVATE))
    assert info.value.code == "E_VIDEO_PRIVATE"
    assert info.value.message == ACCOUNT_TRIED_MESSAGE


@pytest.mark.parametrize(
    ("kind", "params"),
    [
        ("audio", {"format": "m4a", "splitChapters": False, "audioLanguage": "original"}),
        ("subtitle", {"format": "srt", "options": {"maxChars": 25, "lines": 1, "minMs": 1200, "maxMs": 5000}}),
        ("frames_sharp", {}),
    ],
)
def test_every_youtube_job_kind_uses_the_same_rule(env, kind: str, params: dict) -> None:
    deps, fake, db, tmp = env
    deps.accounts = gate = Gate()
    result = _run(env, _job(AGE, kind, params))
    assert result.outputs or result.notes  # ซับ: คลิปนี้ไม่มีซับ = จบแบบมีโน้ต NO_SUBTITLES (ไม่ใช่ error)
    assert gate.used == [f"job-{AGE}"]
```

Create `tests/unit/test_capture_account.py`:
```python
"""ถ่ายภาพคมตรงจุดกับบัญชียูทูปชั่วคราว (M5 รอบ C spec 2.4 "B2 capture"): ถ่ายแบบไม่ใช้บัญชีก่อน แล้วถ่ายใหม่ทั้งครั้งด้วยบัญชี"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from helpers_capture import BBB, MEDIA, FakeVideos, FixtureFetcher, StubQueue, StubSettings, clip_info

from yttoolkit.core.account_scope import current_jar
from yttoolkit.core.capture import CaptureService
from yttoolkit.core.media import FakeMediaTools
from yttoolkit.core.yterrors import ACCOUNT_TRIED_MESSAGE, YtError

JAR = object()


class Gate:
    def __init__(self, jar: Any | None = JAR) -> None:
        self._jar = jar
        self.used: list[str | None] = []

    def jar(self) -> Any | None:
        return self._jar

    def mark_used(self, job_id: str | None) -> None:
        self.used.append(job_id)


class RestrictedVideos(FakeVideos):
    """อ่านข้อมูลคลิปได้เฉพาะใต้บัญชี (คลิปจำกัดอายุ)"""

    def get(self, video_id: str, refresh: bool = False, peek: bool = False) -> dict:
        if current_jar() is None:
            raise YtError("E_AGE_RESTRICTED", "fake: needs the account")
        return super().get(video_id, refresh, peek)


class RecordingFetcher(FixtureFetcher):
    def __init__(self, code_without_account: str | None = None) -> None:
        super().__init__()
        self.code = code_without_account
        self.jars: list[Any] = []

    def fetch_frame_piece(self, video_id: str, t_ms: int, max_short_side: int | None, dest: Path):  # type: ignore[override]
        self.jars.append(current_jar())
        if self.code is not None and current_jar() is None:
            raise YtError(self.code, "fake: needs the account")
        return super().fetch_frame_piece(video_id, t_ms, max_short_side, dest)


def _service(tmp_path: Path, videos: FakeVideos, fetcher: FixtureFetcher, gate: Gate | None) -> CaptureService:
    return CaptureService(videos, fetcher, FakeMediaTools(MEDIA), tmp_path / "cache", StubSettings(tmp_path / "out"),
                          StubQueue(), work_root=tmp_path / "work", now=lambda: datetime(2026, 10, 6, 3, tzinfo=UTC),
                          accounts=gate)  # fmt: skip


def test_a_restricted_clip_is_captured_with_the_account(tmp_path: Path) -> None:
    gate, fetcher = Gate(), RecordingFetcher()
    service = _service(tmp_path, RestrictedVideos({BBB: clip_info()}), fetcher, gate)
    capture, created = service.capture(BBB, 2_000)
    assert created and capture.id == "c_2000"
    assert fetcher.jars == [JAR]  # อ่านข้อมูลคลิปและโหลดชิ้นภาพใต้บัญชีเดียวกัน
    assert gate.used == [None]  # ใช้แบบโต้ตอบ ไม่นับเข้ากฎคิวว่าง


def test_a_piece_that_needs_the_account_retries_the_whole_capture(tmp_path: Path) -> None:
    gate, fetcher = Gate(), RecordingFetcher("E_VIDEO_PRIVATE")
    service = _service(tmp_path, FakeVideos({BBB: clip_info()}), fetcher, gate)
    capture, created = service.capture(BBB, 3_000)
    assert created and fetcher.jars == [None, JAR]
    assert not list((tmp_path / "work").glob("capture-*"))


def test_without_an_account_the_capture_fails_plainly(tmp_path: Path) -> None:
    service = _service(tmp_path, RestrictedVideos({BBB: clip_info()}), RecordingFetcher(), None)
    with pytest.raises(YtError) as info:
        service.capture(BBB, 2_000)
    assert info.value.code == "E_AGE_RESTRICTED" and info.value.account_tried is False


def test_an_account_without_access_gets_the_tried_copy(tmp_path: Path) -> None:
    fetcher = RecordingFetcher()
    fetcher.error = YtError("E_VIDEO_PRIVATE", "fake: private for everyone")
    service = _service(tmp_path, FakeVideos({BBB: clip_info()}), fetcher, Gate())
    with pytest.raises(YtError) as info:
        service.capture(BBB, 2_000)
    assert info.value.message == ACCOUNT_TRIED_MESSAGE
    assert fetcher.jars == [None, JAR]


def test_a_bot_check_is_never_retried_with_the_account(tmp_path: Path) -> None:
    gate, fetcher = Gate(), RecordingFetcher()
    fetcher.error = YtError("E_BOT_CHECK", "fake")
    service = _service(tmp_path, FakeVideos({BBB: clip_info()}), fetcher, gate)
    with pytest.raises(YtError) as info:
        service.capture(BBB, 2_000)
    assert info.value.code == "E_BOT_CHECK"
    assert fetcher.jars == [None] and gate.used == []
```

Append to `tests/api/test_videos_api.py` (uses the file's existing `api` fixture, `PRIVATE` and `MESSAGES`):
Replace (1):
```python
        "E_OUTPUT_NOT_WRITABLE")} == {
        "E_CAPTURE_UNSUPPORTED": 422, "E_CAPTURE_BUSY": 409, "E_QUEUE_PAUSED": 409, "E_FFMPEG_MISSING": 409,
        "E_DISK_FULL": 507, "E_OUTPUT_NOT_WRITABLE": 409}  # fmt: skip
```
with:
```python
        "E_OUTPUT_NOT_WRITABLE")} == {
        "E_CAPTURE_UNSUPPORTED": 422, "E_CAPTURE_BUSY": 409, "E_QUEUE_PAUSED": 409, "E_FFMPEG_MISSING": 409,
        "E_DISK_FULL": 507, "E_OUTPUT_NOT_WRITABLE": 409}  # fmt: skip


# ---------- M5 รอบ C: บัญชียูทูปชั่วคราว (spec 2.4) ----------


class _Gate:
    def __init__(self) -> None:
        self._jar = object()
        self.used: list[str | None] = []

    def jar(self) -> object:
        return self._jar

    def mark_used(self, job_id: str | None) -> None:
        self.used.append(job_id)


def test_restricted_clip_is_probed_again_with_the_account(api) -> None:
    client = api()
    resp = client.get("/api/videos/ACCOUNTAGE1")
    assert resp.status_code == 409
    assert resp.json()["error"] == {
        "code": "E_AGE_RESTRICTED",
        "message": MESSAGES["E_AGE_RESTRICTED"],
        "detail": "ERROR: [youtube] ACCOUNTAGE1: fake: needs a signed-in account",
    }
    client.app.state.ctx.accounts = gate = _Gate()
    resp = client.get("/api/videos/ACCOUNTAGE1")
    assert resp.status_code == 200 and resp.json()["title"] == "คลิปจำกัดอายุ"
    assert gate.used == [None]
    assert client.get("/api/history").json()["items"] == []  # probe ที่ใช้บัญชีไม่ลงฐานข้อมูล


def test_an_account_without_access_gets_the_tried_copy(api) -> None:
    client = api()
    client.app.state.ctx.accounts = _Gate()
    resp = client.get(f"/api/videos/{PRIVATE}")
    assert resp.status_code == 404
    assert resp.json()["error"] == {
        "code": "E_VIDEO_PRIVATE",
        "message": "ลองด้วยบัญชีแล้วยังเปิดไม่ได้ บัญชีนี้อาจไม่มีสิทธิ์ดูคลิปนี้ หรือการเข้าสู่ระบบหมดอายุแล้ว ลองนำเข้าใหม่",
        "detail": "signed-in retry failed (E_VIDEO_PRIVATE)",
    }
```

- [ ] **Step 2: Run them, expect FAIL**

Run: `cd "$WORKTREE" && uv run pytest tests/unit/test_account_retry.py tests/unit/test_videos_account.py tests/unit/test_handlers_account.py tests/unit/test_capture_account.py tests/api/test_videos_api.py -q -W error -p no:cacheprovider`
Expected: `ImportError: cannot import name 'with_account_retry' from 'yttoolkit.core.account_scope'`; `TypeError: CaptureService.__init__() got an unexpected keyword argument 'accounts'`; the API tests get 409 after setting `ctx.accounts`.

- [ ] **Step 3: The retry helper in `core/account_scope.py`**
Replace (1):
```python

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any

_JAR: ContextVar[Any | None] = ContextVar("yttoolkit_account_jar", default=None)


def current_jar() -> Any | None:
    """jar ของบัญชีที่งานนี้ใช้อยู่ None = ไม่ได้ใช้บัญชี (คำขอแบบไม่ระบุตัวตนตามปกติ)"""
    return _JAR.get()


@contextmanager
```
with:
```python

from __future__ import annotations

import logging
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any, Protocol, TypeVar

from .yterrors import ACCOUNT_CODES, YtError

log = logging.getLogger("yttoolkit")

T = TypeVar("T")
_JAR: ContextVar[Any | None] = ContextVar("yttoolkit_account_jar", default=None)


class AccountGate(Protocol):
    """ส่วนของ AccountService ที่จุดเรียกยูทูปใช้ (core/account_session.py)"""

    def jar(self) -> Any | None: ...
    def mark_used(self, job_id: str | None) -> None: ...


def current_jar() -> Any | None:
    """jar ของบัญชีที่งานนี้ใช้อยู่ None = ไม่ได้ใช้บัญชี (คำขอแบบไม่ระบุตัวตนตามปกติ)"""
    return _JAR.get()


def with_account_retry(accounts: AccountGate | None, call: Callable[[], T], *, job_id: str | None = None) -> T:
    """กฎลองซ้ำของ spec 2.4: เรียกแบบไม่ใช้บัญชีก่อนเสมอ ได้ E_AGE_RESTRICTED / E_VIDEO_PRIVATE และถือบัญชีอยู่
    = เรียก call() ซ้ำอีกครั้งเดียวทั้งก้อนใน signed_in(jar) (ทุกคำขอของงานนั้นใช้บัญชีเดียวกัน)

    - รหัสอื่น (E_BOT_CHECK, E_NETWORK ฯลฯ) ไม่ลองด้วยบัญชี โยนต่อทันที (C9)
    - รอบที่ใช้บัญชีพลาด = YtError รหัสเดิม detail กลาง ๆ ไม่มีข้อความดิบของ yt-dlp และตัดสาย exception (from None)
      รหัสใน ACCOUNT_CODES ติด account_tried (ข้อความ "ลองด้วยบัญชีแล้ว...") บัญชียังอยู่
    - อยู่ในขอบเขตที่ใช้บัญชีแล้ว (งานซ้อนงาน) = เรียกตรง ๆ ไม่ลองซ้ำซ้อน
    job_id = งานในคิว (นับเข้ากฎคิวว่างของ AccountService) · None = หน้าเว็บ/ถ่ายภาพคม
    """
    if accounts is None or _JAR.get() is not None:
        return call()
    try:
        return call()
    except YtError as exc:
        if exc.code not in ACCOUNT_CODES:
            raise
        jar = accounts.jar()
        if jar is None:
            raise
        code = exc.code
    log.info("ลองอีกครั้งด้วยบัญชียูทูปชั่วคราว (%s)", code)
    accounts.mark_used(job_id)
    with signed_in(jar):
        try:
            return call()
        except YtError as exc:
            raise YtError(
                exc.code,
                f"signed-in retry failed ({exc.code})",
                retry_after=exc.retry_after,
                params=exc.params,
                account_tried=exc.code in ACCOUNT_CODES,
            ) from None


@contextmanager
```

- [ ] **Step 4: Signed-in probes in memory only (`core/videos.py`)**
Replace (1):
```python

from __future__ import annotations

import json
import logging
import math
```
with:
```python

from __future__ import annotations

import copy
import json
import logging
import math
```

Replace (2):
```python
from datetime import UTC, datetime, timedelta
from typing import Any

from .db import PEEK_SENTINEL, Database
from .extractor import Extractor
from .inputs import PLAYLIST_ID, VIDEO_ID, is_mix_id
```
with:
```python
from datetime import UTC, datetime, timedelta
from typing import Any

from .account_scope import current_jar
from .db import PEEK_SENTINEL, Database
from .extractor import Extractor
from .inputs import PLAYLIST_ID, VIDEO_ID, is_mix_id
```

Replace (3):
```python
        self._now = now
        self._guard = threading.Lock()
        self._id_locks: dict[str, threading.Lock] = {}

    def _id_lock(self, video_id: str) -> threading.Lock:
        with self._guard:
```
with:
```python
        self._now = now
        self._guard = threading.Lock()
        self._id_locks: dict[str, threading.Lock] = {}
        # M5 รอบ C: ข้อมูลคลิปที่ probe ด้วยบัญชีชั่วคราว (trim_probe แล้ว) อยู่ในหน่วยความจำเท่านั้น ไม่ลงฐานข้อมูล
        # ทิ้งทั้งหมดเมื่อบัญชีถูกลบหรือถูกแทน (AccountService on_clear -> forget_signed_in)
        self._signed: dict[str, dict] = {}
        self._signed_lock = threading.Lock()

    def forget_signed_in(self) -> None:
        """ทิ้งข้อมูลคลิปทุกคลิปที่ได้มาด้วยบัญชีชั่วคราว (ลบบัญชีแล้ว เปิดคลิปนั้นใหม่ = probe ใหม่แบบไม่ใช้บัญชี)"""
        with self._signed_lock:
            self._signed.clear()

    def _signed_raw(self, video_id: str) -> dict | None:
        with self._signed_lock:
            data = self._signed.get(video_id)
        return copy.deepcopy(data) if data is not None else None

    def _id_lock(self, video_id: str) -> threading.Lock:
        with self._guard:
```

Replace (4):
```python
            info = self._cached_hit(video_id, peek)
            if info is not None:
                return info
        lock = self._id_lock(video_id)
        contended = not lock.acquire(blocking=False)
        if contended:
```
with:
```python
            info = self._cached_hit(video_id, peek)
            if info is not None:
                return info
            kept = self._signed_raw(video_id)
            if kept is not None:
                return to_video_info(kept)
        if current_jar() is not None:
            return self._probe_signed_in(video_id)
        lock = self._id_lock(video_id)
        contended = not lock.acquire(blocking=False)
        if contended:
```

Replace (5):
```python
                "UPDATE videos SET opened_at = ? WHERE video_id = ?", (stamp, video_id)
            )
        return info

    def _probe_and_store(self, video_id: str, peek: bool = False) -> dict:
        trimmed = trim_probe(self._extractor.probe(video_id))
```
with:
```python
                "UPDATE videos SET opened_at = ? WHERE video_id = ?", (stamp, video_id)
            )
        return info

    def _probe_signed_in(self, video_id: str) -> dict:
        """probe ด้วยบัญชีชั่วคราว (อยู่ใน account_scope.signed_in): เก็บในหน่วยความจำ ไม่แตะฐานข้อมูลเลย
        (ไม่มีแถวใน videos ไม่ขึ้นใน "ล่าสุด" ลิงก์ format ผูกกับเซสชันของบัญชี spec 2.4 "Cache")"""
        trimmed = trim_probe(self._extractor.probe(video_id))
        with self._signed_lock:
            self._signed[video_id] = trimmed
        return to_video_info(copy.deepcopy(trimmed))

    def _probe_and_store(self, video_id: str, peek: bool = False) -> dict:
        trimmed = trim_probe(self._extractor.probe(video_id))
```

Replace (6):
```python
                    data = None
                if isinstance(data, dict):
                    return data
            self.get(video_id, refresh=True, peek=True)
        raise YtError("E_UNKNOWN", f"อ่านข้อมูลคลิป {video_id} ที่เก็บไว้ไม่ได้")
```
with:
```python
                    data = None
                if isinstance(data, dict):
                    return data
            kept = self._signed_raw(video_id)
            if kept is not None:
                return kept
            self.get(video_id, refresh=True, peek=True)
        raise YtError("E_UNKNOWN", f"อ่านข้อมูลคลิป {video_id} ที่เก็บไว้ไม่ได้")
```

- [ ] **Step 5: Queue jobs (`core/handlers.py`) and capture (`core/capture.py`)**

`src/yttoolkit/core/handlers.py`:
Replace (1):
```python
from PIL import Image

from . import files
from .advanced import ADS_SUFFIX, ChapterPart, Interval, chapter_parts, keep_intervals, kept_ms, range_suffix
from .download import (
    AUTO_SHARP_MAX_SHORT_SIDE,
```
with:
```python
from PIL import Image

from . import files
from .account_scope import AccountGate, with_account_retry
from .advanced import ADS_SUFFIX, ChapterPart, Interval, chapter_parts, keep_intervals, kept_ms, range_suffix
from .download import (
    AUTO_SHARP_MAX_SHORT_SIDE,
```

Replace (2):
```python
    sponsors: SponsorSource | None = None
    # ทำภาพคมอัตโนมัติหลังงานวิดีโอ (M5 รอบ B D6) lifecycle อ่านค่าตั้ง autoSharpFrames ทุกงาน · ค่าเริ่มต้น (เทส) = ไม่ทำ
    auto_sharp: Callable[[], bool] = lambda: False


# ---------- ตัวช่วย ----------
```
with:
```python
    sponsors: SponsorSource | None = None
    # ทำภาพคมอัตโนมัติหลังงานวิดีโอ (M5 รอบ B D6) lifecycle อ่านค่าตั้ง autoSharpFrames ทุกงาน · ค่าเริ่มต้น (เทส) = ไม่ทำ
    auto_sharp: Callable[[], bool] = lambda: False
    # บัญชียูทูปชั่วคราว (M5 รอบ C) lifecycle ต่อให้หลังสร้าง AccountService · None = ไม่มีการลองซ้ำด้วยบัญชี
    accounts: AccountGate | None = None


# ---------- ตัวช่วย ----------
```

Replace (3):
```python

    def bind(fn: Callable[[HandlerDeps, Job, JobContext], JobResult]) -> Handler:
        def handler(job: Job, ctx: JobContext) -> JobResult:
            return fn(deps, job, ctx)

        handler.__name__ = fn.__name__.lstrip("_")
        return handler
```
with:
```python

    def bind(fn: Callable[[HandlerDeps, Job, JobContext], JobResult]) -> Handler:
        def handler(job: Job, ctx: JobContext) -> JobResult:
            # M5 รอบ C spec 2.4: ทั้งงานลองแบบไม่ใช้บัญชีก่อน ติดจำกัดอายุ/ส่วนตัว + ถือบัญชีอยู่ = ทำทั้งงานใหม่ด้วยบัญชี
            # (probe + โหลด + ซับ ใช้บัญชีเดียวกันทั้งงาน) อ่าน deps.accounts ตอนรันงาน (lifecycle ต่อให้หลังสร้าง)
            return with_account_retry(deps.accounts, lambda: fn(deps, job, ctx), job_id=job.id)

        handler.__name__ = fn.__name__.lstrip("_")
        return handler
```

`src/yttoolkit/core/capture.py`:
Replace (1):
```python

from PIL import Image, UnidentifiedImageError

from .cancel import JobCancelled
from .files import PATH_LIMIT, ensure_output_root, plan_output
from .frame_piece import PieceInfo, max_short_side
```
with:
```python

from PIL import Image, UnidentifiedImageError

from .account_scope import AccountGate, with_account_retry
from .cancel import JobCancelled
from .files import PATH_LIMIT, ensure_output_root, plan_output
from .frame_piece import PieceInfo, max_short_side
```

Replace (2):
```python
        *,
        work_root: Path,
        now: Callable[[], datetime] = _utcnow,
    ) -> None:
        self._videos = videos
        self._extractor = extractor
```
with:
```python
        *,
        work_root: Path,
        now: Callable[[], datetime] = _utcnow,
        accounts: AccountGate | None = None,
    ) -> None:
        self._videos = videos
        self._extractor = extractor
```

Replace (3):
```python
        self._queue = queue
        self._work_root = Path(work_root)
        self._now = now
        self._busy = threading.Lock()  # ถ่ายได้ครั้งละภาพทั้งแอพ (ไม่รอ: ถือไว้อยู่ = E_CAPTURE_BUSY)
        self._guard = threading.Lock()
        self._clip_locks: dict[str, threading.Lock] = {}
```
with:
```python
        self._queue = queue
        self._work_root = Path(work_root)
        self._now = now
        self._accounts = accounts  # M5 รอบ C: ลองซ้ำด้วยบัญชีชั่วคราว (ทั้งการอ่านคลิปและการโหลดชิ้นภาพ)
        self._busy = threading.Lock()  # ถ่ายได้ครั้งละภาพทั้งแอพ (ไม่รอ: ถือไว้อยู่ = E_CAPTURE_BUSY)
        self._guard = threading.Lock()
        self._clip_locks: dict[str, threading.Lock] = {}
```

Replace (4):
```python
            raise YtError("E_INVALID_INPUT", f"video id ไม่ถูกรูปแบบ: {video_id!r}")
        if isinstance(t_ms, bool) or not isinstance(t_ms, int):
            raise CaptureRejected("tMs must be an integer")
        try:
            info = self._videos.get(video_id, peek=True)  # ไม่มีในที่เก็บ = probe ใหม่ (ติดบอทได้)
        except YtError as exc:
```
with:
```python
            raise YtError("E_INVALID_INPUT", f"video id ไม่ถูกรูปแบบ: {video_id!r}")
        if isinstance(t_ms, bool) or not isinstance(t_ms, int):
            raise CaptureRejected("tMs must be an integer")
        # M5 รอบ C spec 2.4: ถ่ายแบบไม่ใช้บัญชีก่อน จำกัดอายุ/ส่วนตัว + ถือบัญชีอยู่ = ถ่ายใหม่ทั้งครั้งด้วยบัญชี (ไม่นับเข้ากฎคิว)
        return with_account_retry(self._accounts, lambda: self._capture_once(video_id, t_ms))

    def _capture_once(self, video_id: str, t_ms: int) -> tuple[Capture, bool]:
        try:
            info = self._videos.get(video_id, peek=True)  # ไม่มีในที่เก็บ = probe ใหม่ (ติดบอทได้)
        except YtError as exc:
```

- [ ] **Step 6: The clip page (`api/videos.py`)**
Replace (1):
```python
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, Field

from ..core.capture import CAPTURE_FOLDER
from ..core.comments import PinnedCommentService
from ..core.frames import file_timecode
```
with:
```python
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, Field

from ..core.account_scope import AccountGate, with_account_retry
from ..core.capture import CAPTURE_FOLDER
from ..core.comments import PinnedCommentService
from ..core.frames import file_timecode
```

Replace (2):
```python
    return call


# ---------- resolve ----------
```
with:
```python
    return call


def ctx_accounts(ctx: AppContext) -> AccountGate | None:
    """บัญชียูทูปชั่วคราวของแอพ (M5 รอบ C) อ่านตอนเรียกจริง: lifecycle ใส่ ctx.accounts หลังสร้าง router ได้
    (getattr: AppContext ที่ยังไม่มีฟิลด์นี้ = ไม่มีบัญชี)"""
    return getattr(ctx, "accounts", None)


# ---------- resolve ----------
```

Replace (3):
```python
    @maps_yt_errors
    def video_info(video_id: str, refresh: bool = False, peek: bool = False) -> dict:
        # peek=1: หน้าเว็บขอแค่ชื่อ/ภาพปก (รายการผล W1) ไม่นับว่าเปิดคลิป จึงไม่ขึ้น "ล่าสุด"
        return videos.get(video_id, refresh=refresh, peek=peek)

    @router.get("/videos/{video_id}/pinned-comment", response_model=None)
    @maps_yt_errors
```
with:
```python
    @maps_yt_errors
    def video_info(video_id: str, refresh: bool = False, peek: bool = False) -> dict:
        # peek=1: หน้าเว็บขอแค่ชื่อ/ภาพปก (รายการผล W1) ไม่นับว่าเปิดคลิป จึงไม่ขึ้น "ล่าสุด"
        # M5 รอบ C: จำกัดอายุ/ส่วนตัว + ถือบัญชีชั่วคราวอยู่ = probe ซ้ำด้วยบัญชีหนึ่งครั้ง (ผลอยู่ในหน่วยความจำเท่านั้น)
        return with_account_retry(ctx_accounts(ctx), lambda: videos.get(video_id, refresh=refresh, peek=peek))

    @router.get("/videos/{video_id}/pinned-comment", response_model=None)
    @maps_yt_errors
```

- [ ] **Step 7: Run the tests, expect PASS** — same command as Step 2 plus `tests/unit/test_capture.py tests/unit/test_handlers.py tests/unit/test_videos.py` (unchanged behaviour without an account), then the full suite.

- [ ] **Step 8: Commit**
```bash
cd "$WORKTREE" && git add src/yttoolkit/core/account_scope.py src/yttoolkit/core/videos.py src/yttoolkit/core/handlers.py src/yttoolkit/core/capture.py src/yttoolkit/api/videos.py tests/unit/test_account_retry.py tests/unit/test_videos_account.py tests/unit/test_handlers_account.py tests/unit/test_capture_account.py tests/api/test_videos_api.py && git commit -F- <<'EOF'
feat(core): M5-C retry once with the temporary account at every YouTube call site

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
EOF
```

### Task 7: `/cookies` API, the health account row, retire the `cookies` setting

**Files:**
- Create: `src/yttoolkit/api/account.py`
- Modify: `src/yttoolkit/app.py` (`AppContext.accounts`, include the router)
- Modify: `src/yttoolkit/api/routes.py` (`/health` `account` row)
- Modify: `src/yttoolkit/core/settings.py` (`READ_ONLY`, `RETIRED_KEYS`, drop the default)
- Test: `tests/api/test_account_api.py` (new), `tests/unit/test_settings.py`, `tests/api/test_settings_api.py`

**Interfaces:**
- Consumes: C3 `AccountService`, `MAX_IMPORT_BYTES` (T3); C4 `parse_account_cookies` (T4, tests only); C1 `MESSAGES["E_COOKIES_INVALID"]` (T1); `error_response`, `BAD_REQUEST_MESSAGE` (`api/errors.py`); `make_client(**overrides)` (`tests/api/conftest.py:15`); `EventBus`, `format_event`.
- Produces: C7 exactly. T9 sets `ctx.accounts`; T10/T11 call these routes from the web.

- [ ] **Step 1: Write the failing tests** — create `tests/api/test_account_api.py`:
```python
"""API บัญชียูทูปชั่วคราว (api/account.py · M5 รอบ C spec 2.5) + แถวบัญชีใน /health + ข่าว SSE "account"

ใช้ AccountService ตัวจริงกับตัวอ่าน cookies.txt ตัวจริง (core/extractor.parse_account_cookies) ไม่ต่อเน็ต
"""

from __future__ import annotations

import pytest

from yttoolkit.api.events import format_event
from yttoolkit.core.account_session import MAX_IMPORT_BYTES, AccountService
from yttoolkit.core.events import Event, EventBus
from yttoolkit.core.extractor import parse_account_cookies
from yttoolkit.core.yterrors import MESSAGES

BASE = "http://127.0.0.1:8787"
AUTH = {"X-Toolkit-Token": "test-token", "Origin": BASE}
CANARY = "canary-api-9c1e"
GOOD = (
    "# Netscape HTTP Cookie File\n"
    f".youtube.com\tTRUE\t/\tTRUE\t1999999999\tSAPISID\t{CANARY}\n"
    f".youtube.com\tTRUE\t/\tTRUE\t1999999999\tLOGIN_INFO\t{CANARY}\n"
)
HEALTH = {"tools": {}, "disk": {}, "output": {}, "network": {}}


@pytest.fixture
def bus():
    events = EventBus()
    yield events
    events.close()


@pytest.fixture
def service(bus):
    return AccountService(parse_account_cookies, publish=bus.publish)


@pytest.fixture
def client(make_client, service):
    return make_client(accounts=service, health=lambda: dict(HEALTH))


def _no_secret(text: str) -> None:
    assert CANARY not in text
    assert "SAPISID" not in text and "LOGIN_INFO" not in text


def test_status_starts_inactive(client) -> None:
    assert client.get("/api/cookies").json() == {"active": False, "used": False}


def test_no_router_without_the_service(make_client) -> None:
    assert make_client().get("/api/cookies").status_code == 404


def test_import_then_status_then_delete(client, service) -> None:
    resp = client.post("/api/cookies/import", json={"text": GOOD, "acceptWarning": True}, headers=AUTH)
    assert resp.status_code == 200
    body = resp.json()
    assert set(body) == {"active", "importedAt", "expiresAt", "used"} and body["active"] is True
    _no_secret(resp.text)
    assert client.get("/api/cookies").json() == body
    assert service.jar() is not None
    gone = client.delete("/api/cookies", headers=AUTH)
    assert gone.status_code == 200 and gone.json() == {"active": False, "used": False}
    assert service.jar() is None


def test_changes_need_the_token(client, service) -> None:
    assert client.post("/api/cookies/import", json={"text": GOOD, "acceptWarning": True}).status_code == 403
    assert client.delete("/api/cookies").status_code == 403
    assert service.jar() is None


def test_import_without_accepting_the_warning_is_409(client, service) -> None:
    for body in ({"text": GOOD}, {"text": GOOD, "acceptWarning": False}, {"text": GOOD, "acceptWarning": "yes"}):
        resp = client.post("/api/cookies/import", json=body, headers=AUTH)
        assert resp.status_code == 409 and resp.json()["error"]["code"] == "E_BAD_REQUEST"
        _no_secret(resp.text)
    assert service.jar() is None


@pytest.mark.parametrize(
    "body",
    [[GOOD], {"text": 5, "acceptWarning": True}, {"text": GOOD, "acceptWarning": True, "cookies": GOOD}, {}],
)
def test_a_malformed_body_is_422_without_echoing_it(client, body) -> None:
    resp = client.post("/api/cookies/import", json=body, headers=AUTH)
    assert resp.status_code == 422 and resp.json()["error"]["code"] == "E_BAD_REQUEST"
    _no_secret(resp.text)


def test_more_than_1_mb_is_413(client, service) -> None:
    text = GOOD + "#" * MAX_IMPORT_BYTES
    resp = client.post("/api/cookies/import", json={"text": text, "acceptWarning": True}, headers=AUTH)
    assert resp.status_code == 413
    assert resp.json()["error"]["code"] == "E_COOKIES_INVALID"
    assert resp.json()["error"]["message"] == MESSAGES["E_COOKIES_INVALID"]
    assert service.jar() is None


def test_an_invalid_file_is_422_and_keeps_the_held_account(client, service) -> None:
    client.post("/api/cookies/import", json={"text": GOOD, "acceptWarning": True}, headers=AUTH)
    held = service.jar()
    bad = f"# Netscape HTTP Cookie File\nnot a cookie line {CANARY}\n"
    resp = client.post("/api/cookies/import", json={"text": bad, "acceptWarning": True}, headers=AUTH)
    assert resp.status_code == 422
    assert resp.json()["error"] == {
        "code": "E_COOKIES_INVALID",
        "message": MESSAGES["E_COOKIES_INVALID"],
        "detail": "line 2: expected 7 tab-separated fields",
    }
    assert service.jar() is held


def test_import_and_delete_are_announced_on_the_event_stream(client, bus) -> None:
    sub = bus.subscribe()
    client.post("/api/cookies/import", json={"text": GOOD, "acceptWarning": True}, headers=AUTH)
    client.delete("/api/cookies", headers=AUTH)
    first, second = sub.get(1), sub.get(1)
    assert isinstance(first, Event) and first.name == "account"
    assert set(first.data) == {"active", "expiresAt"} and first.data["active"] is True
    assert isinstance(second, Event) and second.data == {"active": False, "reason": "manual"}
    wire = format_event(first) + format_event(second)
    assert wire.startswith("event: account\n")
    _no_secret(wire)


def test_health_has_the_account_row_with_status_only(client) -> None:
    assert client.get("/api/health").json()["account"] == {"status": "ok", "active": False, "importedAt": None}
    client.post("/api/cookies/import", json={"text": GOOD, "acceptWarning": True}, headers=AUTH)
    resp = client.get("/api/health")
    row = resp.json()["account"]
    assert row["status"] == "ok" and row["active"] is True and row["importedAt"]
    _no_secret(resp.text)


def test_health_without_the_service_has_no_account_row(make_client) -> None:
    assert "account" not in make_client(health=lambda: dict(HEALTH)).get("/api/health").json()


def test_jobs_still_refuse_use_cookies(make_client) -> None:
    # useCookies ใน POST /jobs ยังได้ 422 ตามเดิม (C9: ไม่มี checkbox ต่อคลิป) เทสเดิมอยู่ใน test_jobs_api.py
    # ที่นี่ยืนยันว่า API ใหม่ไม่ได้เปิดทางอื่นให้ส่งคุกกี้ไปกับงาน
    from yttoolkit.api.jobs import VideoParams

    assert "useCookies" not in VideoParams.model_fields
```

In `tests/unit/test_settings.py` (the defaults dict loses `cookies`; the old shape test becomes the legacy-row test):
Replace (1):
```python
        "captureQuality": "max",
        "theme": "system",
        "filenameStyle": "title",
        "cookies": {"enabled": False, "source": None, "warningAccepted": False},
        "statsResetAt": None,
        "lastUsed": {},
    }
```
with:
```python
        "captureQuality": "max",
        "theme": "system",
        "filenameStyle": "title",
        "statsResetAt": None,
        "lastUsed": {},
    }
```

Replace (2):
```python
    assert info.value.code == "E_BAD_REQUEST"


def test_get_exposes_only_cookie_status_fields(store):
    assert set(store.get()["cookies"]) == {"enabled", "source", "warningAccepted"}


def test_corrupt_stored_row_falls_back_to_default(db, store):
```
with:
```python
    assert info.value.code == "E_BAD_REQUEST"


def test_legacy_cookies_row_is_ignored_then_dropped_on_the_next_save(db, store):  # M5 รอบ C spec 2.5
    db.execute(
        "INSERT INTO settings (key, value_json) VALUES ('cookies', ?)",
        ('{"enabled": true, "source": "file", "warningAccepted": true}',),
    )
    assert "cookies" not in store.get()
    store.patch({"theme": "dark"})
    assert db.execute("SELECT key FROM settings WHERE key = 'cookies'") == []
    assert store.get()["theme"] == "dark"


def test_corrupt_stored_row_falls_back_to_default(db, store):
```

In `tests/api/test_settings_api.py`:
Replace (1):
```python
    "captureQuality",
    "theme",
    "filenameStyle",
    "cookies",
    "statsResetAt",
    "lastUsed",
}
```
with:
```python
    "captureQuality",
    "theme",
    "filenameStyle",
    "statsResetAt",
    "lastUsed",
}
```

- [ ] **Step 2: Run them, expect FAIL**

Run: `cd "$WORKTREE" && uv run pytest tests/api/test_account_api.py tests/unit/test_settings.py tests/api/test_settings_api.py -q -W error -p no:cacheprovider`
Expected: `TypeError: AppContext.__init__() got an unexpected keyword argument 'accounts'` in the account tests; the settings tests fail on the extra `cookies` key.

- [ ] **Step 3: Create `src/yttoolkit/api/account.py`**
```python
"""API บัญชียูทูปชั่วคราว (M5 รอบ C spec 2.5): GET /cookies · POST /cookies/import · DELETE /cookies

ชื่อ path คงตาม PRD เดิม (/cookies) แต่ไม่มีไฟล์คุกกี้ใด ๆ: ทุกอย่างอยู่ในหน่วยความจำของ AccountService
คำขอที่เปลี่ยนสถานะผ่าน token + Origin ของ LocalOnlyMiddleware เหมือน API อื่น
body ของการนำเข้าไม่ถูก log และไม่ถูกสะท้อนกลับใน error (ตรวจรูปร่างเองแทน pydantic ที่ยกค่าที่ส่งมาใส่ข้อความ error)
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from fastapi import APIRouter, Body
from fastapi.responses import JSONResponse

from ..core.account_session import MAX_IMPORT_BYTES
from ..core.yterrors import MESSAGES, YtError
from .errors import BAD_REQUEST_MESSAGE, error_response

if TYPE_CHECKING:
    from ..app import AppContext

IMPORT_KEYS = frozenset({"text", "acceptWarning"})


def build_account_router(ctx: AppContext) -> APIRouter:
    router = APIRouter()
    accounts = ctx.accounts
    assert accounts is not None  # create_app เรียกต่อเมื่อมี ctx.accounts เท่านั้น

    @router.get("/cookies")
    def account_status() -> dict:
        return accounts.status()

    @router.post("/cookies/import", response_model=None)
    def import_account(body: Any = Body(...)) -> dict | JSONResponse:
        if not isinstance(body, dict) or set(body) - IMPORT_KEYS or not isinstance(body.get("text"), str):
            return error_response(422, "E_BAD_REQUEST", BAD_REQUEST_MESSAGE, "body must be {text, acceptWarning}")
        if body.get("acceptWarning") is not True:
            return error_response(409, "E_BAD_REQUEST", BAD_REQUEST_MESSAGE, "acceptWarning must be true")
        if len(body["text"].encode("utf-8")) > MAX_IMPORT_BYTES:
            return error_response(
                413, "E_COOKIES_INVALID", MESSAGES["E_COOKIES_INVALID"], f"file larger than {MAX_IMPORT_BYTES} bytes"
            )
        try:
            return accounts.import_text(body["text"])
        except YtError as exc:
            return error_response(422, exc.code, exc.message, exc.detail or None)

    @router.delete("/cookies")
    def delete_account() -> dict:
        return accounts.clear("manual")

    return router
```

- [ ] **Step 4: `app.py`, `api/routes.py`, `core/settings.py`**

`src/yttoolkit/app.py`:
Replace (1):
```python

from fastapi import FastAPI

from .api.captures import build_captures_router
from .api.errors import install_error_handlers
from .api.events import build_events_router
```
with:
```python

from fastapi import FastAPI

from .api.account import build_account_router
from .api.captures import build_captures_router
from .api.errors import install_error_handlers
from .api.events import build_events_router
```

Replace (2):
```python
from .platform import Platform

if TYPE_CHECKING:  # โมดูลของ M4 ที่ lane อื่นสร้าง ใช้แค่เป็นชนิดของฟิลด์
    from .core.capture import CaptureService
    from .core.events import EventBus
    from .core.media import MediaTools
```
with:
```python
from .platform import Platform

if TYPE_CHECKING:  # โมดูลของ M4 ที่ lane อื่นสร้าง ใช้แค่เป็นชนิดของฟิลด์
    from .core.account_session import AccountService
    from .core.capture import CaptureService
    from .core.events import EventBus
    from .core.media import MediaTools
```

Replace (3):
```python
    open_folder: Callable[[Path], None] | None = None
    # M5 รอบ B2 ถ่ายภาพคมตรงจุด (run_app สร้างให้) ไม่มี = ไม่เปิด API /videos/{id}/captures
    captures: CaptureService | None = None


def create_app(ctx: AppContext) -> FastAPI:
```
with:
```python
    open_folder: Callable[[Path], None] | None = None
    # M5 รอบ B2 ถ่ายภาพคมตรงจุด (run_app สร้างให้) ไม่มี = ไม่เปิด API /videos/{id}/captures
    captures: CaptureService | None = None
    # M5 รอบ C บัญชียูทูปชั่วคราว (run_app สร้างให้) ไม่มี = ไม่เปิด API /cookies* ไม่มีแถวบัญชีใน /health ไม่ลองซ้ำด้วยบัญชี
    accounts: AccountService | None = None


def create_app(ctx: AppContext) -> FastAPI:
```

Replace (4):
```python
        app.include_router(build_videos_router(ctx), prefix="/api")
    if ctx.captures is not None:
        app.include_router(build_captures_router(ctx), prefix="/api")
    if ctx.subtitles is not None:
        app.include_router(build_subtitles_router(ctx), prefix="/api")
    if ctx.settings is not None:
```
with:
```python
        app.include_router(build_videos_router(ctx), prefix="/api")
    if ctx.captures is not None:
        app.include_router(build_captures_router(ctx), prefix="/api")
    if ctx.accounts is not None:
        app.include_router(build_account_router(ctx), prefix="/api")
    if ctx.subtitles is not None:
        app.include_router(build_subtitles_router(ctx), prefix="/api")
    if ctx.settings is not None:
```

`src/yttoolkit/api/routes.py`:
Replace (1):
```python
    @router.get("/health")
    def health() -> dict:
        body = {"version": ctx.version, "commit": ctx.commit, **_health()}
        if ctx.fake:  # มีเฉพาะตอนโหมดข้อมูลปลอม หน้าเว็บจะแสดงแถบบอกไว้
            body["mode"] = "fake"
        return body
```
with:
```python
    @router.get("/health")
    def health() -> dict:
        body = {"version": ctx.version, "commit": ctx.commit, **_health()}
        if ctx.accounts is not None:
            # M5 รอบ C spec 1.4: บอกแค่สถานะ ไม่ต่อเน็ต ไม่มีชื่อหรือค่าคุกกี้ (status เป็น ok เสมอ)
            status = ctx.accounts.status()
            body["account"] = {"status": "ok", "active": status["active"], "importedAt": status.get("importedAt")}
        if ctx.fake:  # มีเฉพาะตอนโหมดข้อมูลปลอม หน้าเว็บจะแสดงแถบบอกไว้
            body["mode"] = "fake"
        return body
```

`src/yttoolkit/core/settings.py`:
Replace (1):
```python
CONCURRENCY = (1, 2, 3)
THEMES = ("system", "dark", "light")
FILENAME_STYLES = ("title", "title-channel", "title-quality")
READ_ONLY = ("cookies", "statsResetAt")


class SettingsError(Exception):
```
with:
```python
CONCURRENCY = (1, 2, 3)
THEMES = ("system", "dark", "light")
FILENAME_STYLES = ("title", "title-channel", "title-quality")
READ_ONLY = ("statsResetAt",)
# key ที่เลิกใช้แล้ว: แถวเก่าในฐานข้อมูลถูกข้ามตอนอ่าน (ไม่อยู่ในค่าเริ่มต้น) และถูกลบตอนบันทึกครั้งถัดไป
# "cookies" = สถานะคุกกี้ของ PRD เดิม M5 รอบ C ใช้บัญชีชั่วคราวในหน่วยความจำแทน (C8)
RETIRED_KEYS = ("cookies",)


class SettingsError(Exception):
```

Replace (2):
```python
            "captureQuality": "max",  # M5 รอบ B2 spec 2.4: ภาพคมตรงจุดใช้ format ที่ละเอียดที่สุด
            "theme": "system",
            "filenameStyle": "title",
            "cookies": {"enabled": False, "source": None, "warningAccepted": False},
            "statsResetAt": None,
            "lastUsed": {},
        }
```
with:
```python
            "captureQuality": "max",  # M5 รอบ B2 spec 2.4: ภาพคมตรงจุดใช้ format ที่ละเอียดที่สุด
            "theme": "system",
            "filenameStyle": "title",
            "statsResetAt": None,
            "lastUsed": {},
        }
```

Replace (3):
```python
            ensure_writable(Path(clean["outputDir"]))
        if clean:
            with self._lock, self._db.transaction() as tx:
                for key, value in clean.items():
                    tx.execute(
                        "INSERT INTO settings (key, value_json) VALUES (?, ?) "
```
with:
```python
            ensure_writable(Path(clean["outputDir"]))
        if clean:
            with self._lock, self._db.transaction() as tx:
                for key in RETIRED_KEYS:
                    tx.execute("DELETE FROM settings WHERE key = ?", (key,))
                for key, value in clean.items():
                    tx.execute(
                        "INSERT INTO settings (key, value_json) VALUES (?, ?) "
```

- [ ] **Step 5: Run the tests, expect PASS** — same command as Step 2 plus `tests/api/test_routes.py tests/api/test_security.py tests/api/test_jobs_api.py` (`useCookies` still 422), then the full suite.

- [ ] **Step 6: Commit**
```bash
cd "$WORKTREE" && git add src/yttoolkit/api/account.py src/yttoolkit/app.py src/yttoolkit/api/routes.py src/yttoolkit/core/settings.py tests/api/test_account_api.py tests/unit/test_settings.py tests/api/test_settings_api.py && git commit -F- <<'EOF'
feat(api): M5-C /cookies import, status and delete; health account row; retire the cookies setting

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
EOF
```

### Task 8: Web dialog, banner, dialog store, removed toast

**Files:**
- Create: `web/src/components/account/account-store.ts`, `dialog-model.ts`, `dialog-model.test.ts`, `use-account.ts`, `account-dialog.tsx`, `account-banner.tsx`, `account-button.tsx`
- Modify: `web/src/components/layout.tsx` (banner under the header, dialog mounted once)
- Modify: `web/src/components/queue/use-queue.ts` (part 1: `onAccount` → removed toast; T10 changes the failed-job toast)

**Interfaces:**
- Consumes: C5 (`th.account`, `ACCOUNT_KEY`, `accountQuery`, `importAccount`, `deleteAccount`, `deleteTime`, `fileTooBig`, `INACTIVE`, `AccountEvent`, `AccountStatus`, `connectEvents(..., { onAccount })`, T5); shadcn `Dialog`, `Alert`, `Field`, `Input`, `Button`, `Spinner`; `th.common.close`, `th.queue.actionFailed`, `th.errors.unknown`.
- Produces: C8 exactly (T10 and T11 use `UseAccountButton`, `useAccountStatus`, `useDeleteAccount`, `useNow`, `openAccountDialog`, `accountDialog`, `showRemovedToast`).

- [ ] **Step 1: Write the failing test** — create `web/src/components/account/dialog-model.test.ts`:
```ts
import { describe, expect, it } from "vitest"

import { accountDialog, openAccountDialog } from "./account-store"
import { canImport, dialogReducer, EMPTY_DIALOG, importLabel } from "./dialog-model"

describe("dialogReducer", () => {
  it("เลือกไฟล์แล้วกดนำเข้าได้ · กำลังส่งกดซ้ำไม่ได้", () => {
    expect(canImport(EMPTY_DIALOG)).toBe(false)
    const picked = dialogReducer(EMPTY_DIALOG, { type: "picked", fileName: "cookies.txt", text: "x" })
    expect(canImport(picked)).toBe(true)
    const sending = dialogReducer(picked, { type: "submitting" })
    expect(sending.pending).toBe(true)
    expect(canImport(sending)).toBe(false)
  })

  it("ไฟล์ใหญ่เกิน = ข้อความใต้ช่อง ไม่มีข้อความให้ส่ง", () => {
    const rejected = dialogReducer(EMPTY_DIALOG, { type: "rejected", fileName: "big.txt", message: "ใช้ไม่ได้" })
    expect(rejected).toEqual({ fileName: "big.txt", text: null, error: "ใช้ไม่ได้", pending: false })
    expect(canImport(rejected)).toBe(false)
    expect(dialogReducer(rejected, { type: "submitting" })).toBe(rejected)
  })

  it("backend ไม่รับ = ข้อความใต้ช่อง ยังเลือกไฟล์เดิมอยู่และลองใหม่ได้ · เลือกไฟล์ใหม่ล้างข้อความ", () => {
    const sending = dialogReducer(dialogReducer(EMPTY_DIALOG, { type: "picked", fileName: "a.txt", text: "x" }), {
      type: "submitting",
    })
    const failed = dialogReducer(sending, { type: "failed", message: "ไฟล์นี้ใช้ไม่ได้" })
    expect(failed.error).toBe("ไฟล์นี้ใช้ไม่ได้")
    expect(canImport(failed)).toBe(true)
    expect(dialogReducer(failed, { type: "picked", fileName: "b.txt", text: "y" }).error).toBeNull()
    expect(dialogReducer(failed, { type: "reset" })).toEqual(EMPTY_DIALOG)
  })
})

describe("importLabel และที่เก็บสถานะ dialog", () => {
  it("เปิดจาก error = นำเข้าแล้วลองใหม่ · จากหน้าตั้งค่า = นำเข้า", () => {
    expect(importLabel({ origin: "error" })).toBe("นำเข้าแล้วลองใหม่")
    expect(importLabel({ origin: "settings" })).toBe("นำเข้า")
    expect(importLabel(null)).toBe("นำเข้า")
  })

  it("openAccountDialog เปิดพร้อมคำขอ close ล้างคำขอ", () => {
    const onImported = () => undefined
    openAccountDialog({ origin: "error", onImported })
    expect(accountDialog.get()).toEqual({ open: true, request: { origin: "error", onImported } })
    accountDialog.close()
    expect(accountDialog.get()).toEqual({ open: false, request: null })
  })
})
```

- [ ] **Step 2: Run it, expect FAIL**

Run: `cd "$WORKTREE/web" && npx vitest run src/components/account/dialog-model.test.ts`
Expected: `Failed to resolve import "./account-store"`.

- [ ] **Step 3: The store and the pure dialog model**

Create `web/src/components/account/account-store.ts`:
```ts
import { useSyncExternalStore } from "react"

/**
 * dialog "ใช้บัญชียูทูปชั่วคราว" มีตัวเดียวทั้งแอพ (วางไว้ที่ layout) ทุกทางเข้าเปิดผ่าน openAccountDialog
 * origin "error" = ปุ่มบน error (ปุ่มนำเข้า "นำเข้าแล้วลองใหม่") · "settings" = แท็บขั้นสูง ("นำเข้า")
 * onImported = สิ่งที่ทำต่อหลังนำเข้าสำเร็จ (โหลดข้อมูลคลิปใหม่ / ลองงานใหม่ / ถ่ายภาพเดิมใหม่)
 */
export type AccountDialogRequest = { origin: "error" | "settings"; onImported?: () => void }
export type AccountDialogState = { open: boolean; request: AccountDialogRequest | null }

const CLOSED: AccountDialogState = { open: false, request: null }

function createStore() {
  let state: AccountDialogState = CLOSED
  const listeners = new Set<() => void>()
  const set = (next: AccountDialogState) => {
    state = next
    listeners.forEach((listener) => listener())
  }
  return {
    get: () => state,
    open: (request: AccountDialogRequest) => set({ open: true, request }),
    close: () => set(CLOSED),
    subscribe(listener: () => void) {
      listeners.add(listener)
      return () => void listeners.delete(listener)
    },
  }
}

export const accountDialog = createStore()

export function openAccountDialog(request: AccountDialogRequest): void {
  accountDialog.open(request)
}

export function useAccountDialog(): AccountDialogState {
  return useSyncExternalStore(accountDialog.subscribe, accountDialog.get, accountDialog.get)
}
```

Create `web/src/components/account/dialog-model.ts`:
```ts
import { th } from "@/i18n/th"

import type { AccountDialogRequest } from "./account-store"

/**
 * สถานะของ dialog "ใช้บัญชียูทูปชั่วคราว" (spec 1.2): ไฟล์ที่เลือก (อ่านเป็นข้อความแล้ว) · ข้อความ error ใต้ช่อง · กำลังส่ง
 * ส่งไม่ได้จนกว่าจะเลือกไฟล์ที่อ่านได้ · error = dialog ยังเปิดอยู่ (ผู้ใช้เลือกไฟล์ใหม่ได้)
 */
export type DialogState = { fileName: string | null; text: string | null; error: string | null; pending: boolean }

export type DialogAction =
  | { type: "picked"; fileName: string; text: string }
  | { type: "rejected"; fileName: string | null; message: string }
  | { type: "submitting" }
  | { type: "failed"; message: string }
  | { type: "reset" }

export const EMPTY_DIALOG: DialogState = { fileName: null, text: null, error: null, pending: false }

export function dialogReducer(state: DialogState, action: DialogAction): DialogState {
  switch (action.type) {
    case "picked":
      return { fileName: action.fileName, text: action.text, error: null, pending: false }
    case "rejected":
      return { fileName: action.fileName, text: null, error: action.message, pending: false }
    case "submitting":
      return state.text === null ? state : { ...state, error: null, pending: true }
    case "failed":
      return { ...state, error: action.message, pending: false }
    case "reset":
      return EMPTY_DIALOG
  }
}

/** ปุ่มนำเข้ากดได้: มีไฟล์ที่อ่านได้ และไม่ได้กำลังส่ง */
export function canImport(state: DialogState): boolean {
  return state.text !== null && !state.pending
}

/** ปุ่มนำเข้า: เปิดจาก error = "นำเข้าแล้วลองใหม่" · จากหน้าตั้งค่า = "นำเข้า" */
export function importLabel(request: AccountDialogRequest | null): string {
  return request?.origin === "error" ? th.account.importRetry : th.account.import
}
```

- [ ] **Step 4: Hooks and components**

Create `web/src/components/account/use-account.ts`:
```ts
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { useEffect, useState } from "react"
import { toast } from "sonner"

import { th } from "@/i18n/th"
import { ACCOUNT_KEY, accountQuery, deleteAccount, INACTIVE } from "@/lib/account"
import type { AccountStatus } from "@/lib/types"

/** toast หลังลบบัญชี (ทุกเหตุผล ทุกแท็บ): ไม่หายเอง มีปุ่ม "ปิด" · id เดียว = ลบในแท็บนี้แล้วข่าว SSE ตามมาไม่เด้งซ้ำ */
export const REMOVED_TOAST_ID = "account-removed"

export function showRemovedToast(): void {
  toast.info(th.account.removed, {
    id: REMOVED_TOAST_ID,
    duration: Infinity,
    action: { label: th.common.close, onClick: () => undefined },
  })
}

/** สถานะบัญชีชั่วคราว (ยังโหลดไม่เสร็จหรือโหลดไม่ได้ = ถือว่าไม่ได้ใช้บัญชี) */
export function useAccountStatus(): AccountStatus {
  return useQuery(accountQuery()).data ?? INACTIVE
}

/** "ลบออกตอนนี้": ไม่ต้องยืนยัน (spec 1.3) · สำเร็จ = แคชเป็นไม่ได้ใช้บัญชี + toast · ไม่สำเร็จ = toast ทั่วไป */
export function useDeleteAccount(): { remove: () => void; pending: boolean } {
  const client = useQueryClient()
  const mutation = useMutation({
    mutationFn: () => deleteAccount(),
    onSuccess: (status) => {
      client.setQueryData<AccountStatus>(ACCOUNT_KEY, status)
      showRemovedToast()
    },
    onError: () => toast.error(th.queue.actionFailed),
  })
  return { remove: () => mutation.mutate(), pending: mutation.isPending }
}

/** เวลาปัจจุบันที่เดินทุก intervalMs เฉพาะตอน active (นับถอยหลังของแถบบนหน้าและแท็บขั้นสูง) */
export function useNow(active: boolean, intervalMs = 15_000): number {
  const [now, setNow] = useState(() => Date.now())
  useEffect(() => {
    if (!active) return
    const timer = window.setInterval(() => setNow(Date.now()), intervalMs)
    return () => window.clearInterval(timer)
  }, [active, intervalMs])
  return now
}
```

Create `web/src/components/account/account-dialog.tsx` (title = accessible name; the inline error is linked with `aria-describedby`; Esc / "ยกเลิก" / closing resets the state and sends nothing):
```tsx
import { useQueryClient } from "@tanstack/react-query"
import { TriangleAlert } from "lucide-react"
import { useId, useReducer } from "react"

import { Alert, AlertDescription } from "@/components/ui/alert"
import { Button } from "@/components/ui/button"
import { Dialog, DialogClose, DialogContent, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog"
import { FieldError } from "@/components/ui/field"
import { Input } from "@/components/ui/input"
import { Spinner } from "@/components/ui/spinner"
import { th } from "@/i18n/th"
import { ACCOUNT_KEY, fileTooBig, importAccount } from "@/lib/account"
import { ApiError } from "@/lib/api"
import type { AccountStatus } from "@/lib/types"

import { accountDialog, useAccountDialog } from "./account-store"
import { canImport, dialogReducer, EMPTY_DIALOG, importLabel } from "./dialog-model"

const t = th.account

/**
 * dialog "ใช้บัญชียูทูปชั่วคราว" (spec 1.2) ตัวเดียวทั้งแอพ: คำเตือน (สีอันตราย) · คลิปส่วนตัว · ขั้นตอนส่งออก · ช่องเลือกไฟล์
 * ยกเลิก / Esc / ปิด = ไม่ส่งอะไร · ไฟล์เกิน 1 MB หรือ backend ไม่รับ = ข้อความใต้ช่อง dialog ยังเปิด
 * สำเร็จ = ปิด dialog แคชสถานะเป็นใช้บัญชีอยู่ (แถบบนหน้าขึ้นทันที) แล้วทำสิ่งที่ผู้เปิดขอไว้ (onImported)
 */
export function AccountDialog() {
  const { open, request } = useAccountDialog()
  const client = useQueryClient()
  const [state, dispatch] = useReducer(dialogReducer, EMPTY_DIALOG)
  const errorId = useId()

  const close = () => {
    accountDialog.close()
    dispatch({ type: "reset" })
  }

  async function pick(file: File | undefined) {
    if (file === undefined) {
      dispatch({ type: "reset" })
      return
    }
    if (fileTooBig(file.size)) {
      dispatch({ type: "rejected", fileName: file.name, message: t.invalid })
      return
    }
    dispatch({ type: "picked", fileName: file.name, text: await file.text() })
  }

  async function submit() {
    if (!canImport(state) || state.text === null) return
    dispatch({ type: "submitting" })
    try {
      const status = await importAccount(state.text)
      client.setQueryData<AccountStatus>(ACCOUNT_KEY, status)
      const then = request?.onImported
      close()
      then?.()
    } catch (error) {
      dispatch({ type: "failed", message: error instanceof ApiError ? error.message : th.errors.unknown })
    }
  }

  return (
    <Dialog open={open} onOpenChange={(next) => (next ? undefined : close())}>
      <DialogContent data-testid="account-dialog" className="max-h-[calc(100dvh-2rem)] overflow-y-auto sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>{t.title}</DialogTitle>
        </DialogHeader>
        <Alert variant="destructive">
          <TriangleAlert aria-hidden />
          <AlertDescription>{t.warning}</AlertDescription>
        </Alert>
        <p>{t.privateClips}</p>
        <ol className="flex list-decimal flex-col gap-1 pl-5">
          {t.steps.map((step) => (
            <li key={step}>{step}</li>
          ))}
        </ol>
        <div className="flex flex-col gap-1.5">
          <Input
            type="file"
            accept=".txt,text/plain"
            aria-label={t.fileLabel}
            aria-invalid={state.error !== null || undefined}
            aria-describedby={state.error !== null ? errorId : undefined}
            disabled={state.pending}
            onChange={(event) => void pick(event.target.files?.[0])}
          />
          {state.error !== null && <FieldError id={errorId}>{state.error}</FieldError>}
        </div>
        <DialogFooter>
          <DialogClose render={<Button variant="outline" />}>{t.cancel}</DialogClose>
          <Button disabled={!canImport(state)} onClick={() => void submit()}>
            {state.pending && <Spinner aria-hidden />}
            {importLabel(request)}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
```

Create `web/src/components/account/account-banner.tsx` (the time comes from `deleteTime`, Q1):
```tsx
import { UserRound } from "lucide-react"

import { Button } from "@/components/ui/button"
import { th } from "@/i18n/th"
import { deleteTime } from "@/lib/account"

import { useAccountStatus, useDeleteAccount, useNow } from "./use-account"

/**
 * แถบบาง ๆ ใต้เมนูบนทุกหน้าเมื่อถือบัญชีชั่วคราวอยู่ (spec 1.3): "กำลังใช้บัญชียูทูปชั่วคราว · ลบอัตโนมัติภายใน HH:MM"
 * + ปุ่มแบบลิงก์ "ลบออกตอนนี้" (ไม่ต้องยืนยัน) · ตามสถานะของเซิร์ฟเวอร์ผ่าน SSE (ลบเอง = แถบหายในทุกแท็บ)
 * ตัวเลขนับถอยหลังไม่ถูกอ่านซ้ำทุกครั้งที่เปลี่ยน (aria-live off)
 */
export function AccountBanner() {
  const status = useAccountStatus()
  const now = useNow(status.active)
  const remove = useDeleteAccount()
  if (!status.active || status.expiresAt === undefined) return null
  const [before, after] = th.account.banner.split("{time}")
  return (
    <div data-testid="account-banner" className="border-y border-primary/30 bg-primary/10">
      <div className="mx-auto flex max-w-[960px] flex-wrap items-center gap-x-3 gap-y-1 px-4 py-1 text-sm">
        <UserRound aria-hidden className="size-4 shrink-0 text-accent-text" />
        <p className="min-w-0 flex-1">
          {before}
          <span aria-live="off" className="font-mono tabular-nums">
            {deleteTime({ expiresAt: status.expiresAt, importedAt: status.importedAt }, now)}
          </span>
          {after}
        </p>
        <Button
          variant="ghost"
          size="sm"
          className="h-7 shrink-0 px-1.5 underline underline-offset-4"
          disabled={remove.pending}
          onClick={remove.remove}
        >
          {th.account.removeNow}
        </Button>
      </div>
    </div>
  )
}
```

Create `web/src/components/account/account-button.tsx`:
```tsx
import { UserRound } from "lucide-react"

import { Button } from "@/components/ui/button"
import { th } from "@/i18n/th"

import { openAccountDialog, type AccountDialogRequest } from "./account-store"

type Props = {
  /** หลังนำเข้าสำเร็จ (ลองสิ่งที่เพิ่งพลาดใหม่) · ไม่มี = เปิดจากหน้าตั้งค่า */
  onImported?: () => void
  origin?: AccountDialogRequest["origin"]
  variant?: "default" | "outline"
  size?: "sm" | "default"
  className?: string
}

/** ปุ่ม "ใช้บัญชียูทูปชั่วคราว" (spec 1.1): เปิด dialog ตัวกลาง ผู้วางปุ่มตัดสินเองว่าควรแสดงไหม (showAccountButton) */
export function UseAccountButton({ onImported, origin = "error", variant = "outline", size = "sm", className }: Props) {
  return (
    <Button variant={variant} size={size} className={className} onClick={() => openAccountDialog({ origin, onImported })}>
      <UserRound aria-hidden />
      {th.account.use}
    </Button>
  )
}
```

- [ ] **Step 5: Mount them and toast on removal**

`web/src/components/layout.tsx`:
Replace (1):
```tsx
import { History, House, Settings, type LucideIcon } from "lucide-react"
import { Link, Outlet, ScrollRestoration, useLocation, useSearchParams } from "react-router"

import { QueueBar } from "@/components/queue/queue-bar"
import { ShutdownDialog } from "@/components/queue/shutdown-dialog"
import { useServerEvents } from "@/components/queue/use-queue"
```
with:
```tsx
import { History, House, Settings, type LucideIcon } from "lucide-react"
import { Link, Outlet, ScrollRestoration, useLocation, useSearchParams } from "react-router"

import { AccountBanner } from "@/components/account/account-banner"
import { AccountDialog } from "@/components/account/account-dialog"
import { QueueBar } from "@/components/queue/queue-bar"
import { ShutdownDialog } from "@/components/queue/shutdown-dialog"
import { useServerEvents } from "@/components/queue/use-queue"
```

Replace (2):
```tsx
          </ul>
        </nav>
      </header>
      {/*
        เว้นที่ท้ายหน้าเท่าความสูงแถบคิว เนื้อหาล่างสุดจึงไม่ถูกแถบบัง
        ตอนตัวเล่นลอย body เว้นที่ให้ทั้งตัวเล่นและแถบคิวแล้ว (index.css) main จึงกลับเป็น pb-16 ไม่เว้นซ้ำ
```
with:
```tsx
          </ul>
        </nav>
      </header>
      {/* M5 รอบ C: แถบ "กำลังใช้บัญชียูทูปชั่วคราว" ใต้เมนูบนทุกหน้า (ไม่ได้ใช้บัญชี = ไม่มีอะไร) */}
      {!closed && <AccountBanner />}
      {/*
        เว้นที่ท้ายหน้าเท่าความสูงแถบคิว เนื้อหาล่างสุดจึงไม่ถูกแถบบัง
        ตอนตัวเล่นลอย body เว้นที่ให้ทั้งตัวเล่นและแถบคิวแล้ว (index.css) main จึงกลับเป็น pb-16 ไม่เว้นซ้ำ
```

Replace (3):
```tsx
      </main>
      {!closed && <QueueBar />}
      {!closed && <ShutdownDialog open={params.get(CONFIRM_SHUTDOWN) === "1"} onClose={closeConfirm} />}
      {/* ระยะจากขอบล่างมาจากตัวแปร CSS (index.css): ตัวเล่นลอยอยู่ = toast ขึ้นเหนือตัวเล่น · แถบคิวตั้ง --dock-bottom-offset เท่าความสูงของตัวเอง */}
      <Toaster position="bottom-right" offset={{ bottom: "var(--toast-bottom-offset)" }} mobileOffset={{ bottom: "var(--toast-mobile-bottom-offset)" }} />
      {/* ย้อนกลับ (ปุ่ม back / "รายการที่วาง") = กลับไปตำแหน่งเลื่อนเดิม · เปิดหน้าใหม่ = เริ่มบนสุด */}
```
with:
```tsx
      </main>
      {!closed && <QueueBar />}
      {!closed && <ShutdownDialog open={params.get(CONFIRM_SHUTDOWN) === "1"} onClose={closeConfirm} />}
      {!closed && <AccountDialog />}
      {/* ระยะจากขอบล่างมาจากตัวแปร CSS (index.css): ตัวเล่นลอยอยู่ = toast ขึ้นเหนือตัวเล่น · แถบคิวตั้ง --dock-bottom-offset เท่าความสูงของตัวเอง */}
      <Toaster position="bottom-right" offset={{ bottom: "var(--toast-bottom-offset)" }} mobileOffset={{ bottom: "var(--toast-mobile-bottom-offset)" }} />
      {/* ย้อนกลับ (ปุ่ม back / "รายการที่วาง") = กลับไปตำแหน่งเลื่อนเดิม · เปิดหน้าใหม่ = เริ่มบนสุด */}
```

`web/src/components/queue/use-queue.ts`:
Replace (1):
```ts
import { useCallback, useEffect, useSyncExternalStore } from "react"
import { toast } from "sonner"

import { fill, th } from "@/i18n/th"
import { ApiError } from "@/lib/api"
import { connectEvents } from "@/lib/events"
import { cancelJob, JOBS_KEY, jobsQuery, queueQuery, reorderJobs, retryJob, revealOutput } from "@/lib/jobs"
```
with:
```ts
import { useCallback, useEffect, useSyncExternalStore } from "react"
import { toast } from "sonner"

import { showRemovedToast } from "@/components/account/use-account"
import { fill, th } from "@/i18n/th"
import type { AccountEvent } from "@/lib/account"
import { ApiError } from "@/lib/api"
import { connectEvents } from "@/lib/events"
import { cancelJob, JOBS_KEY, jobsQuery, queueQuery, reorderJobs, retryJob, revealOutput } from "@/lib/jobs"
```

Replace (2):
```ts
  }
}

/** ต่อ SSE ครั้งเดียวต่อหน้า (วางไว้ที่ layout) · เด้ง toast เมื่องานเสร็จหรือพลาดระหว่างเปิดแท็บนี้อยู่ */
export function useServerEvents(): void {
  const client = useQueryClient()
  useEffect(
    () => connectEvents(client, { onShutdown: () => toast.dismiss(), onJobChange: notifyJobChange }),
    [client],
  )
}
```
with:
```ts
  }
}

/** ข่าวบัญชียูทูปชั่วคราว (M5 รอบ C): ถูกลบ (มี reason) = toast ให้ไปออกจากระบบในหน้าต่างไม่ระบุตัวตน ทุกแท็บ */
function notifyAccount(event: AccountEvent): void {
  if (!event.active && event.reason !== undefined) showRemovedToast()
}

/** ต่อ SSE ครั้งเดียวต่อหน้า (วางไว้ที่ layout) · เด้ง toast เมื่องานเสร็จหรือพลาดระหว่างเปิดแท็บนี้อยู่ และเมื่อบัญชีชั่วคราวถูกลบ */
export function useServerEvents(): void {
  const client = useQueryClient()
  useEffect(
    () =>
      connectEvents(client, {
        onShutdown: () => toast.dismiss(),
        onJobChange: notifyJobChange,
        onAccount: notifyAccount,
      }),
    [client],
  )
}
```

- [ ] **Step 6: Run the web checks, expect PASS** — `cd "$WORKTREE/web" && npm run typecheck && npm run lint && npm test`.

- [ ] **Step 7: Commit**
```bash
cd "$WORKTREE" && git add web/src/components/account web/src/components/layout.tsx web/src/components/queue/use-queue.ts && git commit -F- <<'EOF'
feat(web): M5-C account dialog, banner and removed-account toast

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
EOF
```

---


## Wave 3

### Task 9: Lifecycle wiring, the privacy canary and the no-files walk

**Files:**
- Modify: `src/yttoolkit/lifecycle.py` (part 2: account service wiring; T2's filter changes are already merged)
- Test: `tests/unit/test_lifecycle.py` (append), `tests/integration/test_account_privacy.py` (new)

**Interfaces:**
- Consumes: C3 `AccountService`, `GRACE_S` (T3); C4 `parse_account_cookies` (T4); C6 `VideoService.forget_signed_in`, `HandlerDeps.accounts`, `CaptureService(accounts=)` (T6); C7 `AppContext.accounts`, the `/cookies` router (T7); C2 filters on `app.log` (T2); `open_services` / `shutdown_services` / `_run_server` (`lifecycle.py:274, 523, 747`); `_run_capturing_ctx` (`tests/unit/test_lifecycle.py:733`).
- Produces: C9 exactly; the running app has the full round C backend (T12's queue e2e depends on it, including `YT_TOOLKIT_ACCOUNT_GRACE_S`).

- [ ] **Step 1: Write the failing tests**

Append to `tests/unit/test_lifecycle.py`:
Replace (1):
```python
        assert not leftover.exists()
    finally:
        services.db.close()
```
with:
```python
        assert not leftover.exists()
    finally:
        services.db.close()


# ---------- M5 รอบ C: บัญชียูทูปชั่วคราว ----------

ACCOUNT_FILE = "# Netscape HTTP Cookie File\n.youtube.com\tTRUE\t/\tTRUE\t1999999999\tSAPISID\tlifecycle-test\n"


def test_open_services_wires_the_account_service(paths, fake_platform):
    from yttoolkit.core.account_session import GRACE_S, AccountService

    services = lifecycle.open_services(paths, fake_platform, fake=True)
    try:
        accounts = services.accounts
        assert isinstance(accounts, AccountService)
        assert services.queue.listener is accounts
        assert accounts._grace_s == GRACE_S
        with pytest.raises(YtError) as info:
            services.captures.capture("ACCOUNTAGE1", 1_000)
        assert info.value.code == "E_AGE_RESTRICTED"
        sub = services.events.subscribe()
        accounts.import_text(ACCOUNT_FILE)
        capture, created = services.captures.capture("ACCOUNTAGE1", 1_000)  # ถ่ายภาพคมลองซ้ำด้วยบัญชี
        assert created
        assert services.videos.get("ACCOUNTAGE1")["title"] == "คลิปจำกัดอายุ"  # ข้อมูลจากรอบที่ใช้บัญชี (หน่วยความจำ)
        accounts.clear("manual")
        with pytest.raises(YtError):
            services.videos.get("ACCOUNTAGE1")  # ลบบัญชีแล้ว ข้อมูลที่ได้มาด้วยบัญชีหายด้วย
        names = []
        while (item := sub.get(0)) is not None:
            names.append((item.name, item.data.get("active")))
        assert ("account", True) in names and ("account", False) in names
    finally:
        services.db.close()


def test_run_app_puts_the_account_service_on_the_context(paths, fake_platform, monkeypatch):
    from yttoolkit.core.account_session import AccountService

    code, ctx = _run_capturing_ctx(paths, fake_platform, monkeypatch, fake=True)
    assert code == 0 and isinstance(ctx.accounts, AccountService)


def test_shutdown_clears_the_account_before_announcing_the_shutdown(paths, fake_platform):
    services = lifecycle.open_services(paths, fake_platform, fake=True)
    try:
        services.accounts.import_text(ACCOUNT_FILE)
        sub = services.events.subscribe()
        lifecycle.shutdown_services(services, timeout=0.5)
        seen = []
        while isinstance(item := sub.get(0), Event):
            seen.append((item.name, item.data))
        assert seen == [("account", {"active": False, "reason": "shutdown"}), ("app.shutdown", {})]
        assert services.accounts.jar() is None
    finally:
        services.db.close()


@pytest.mark.parametrize(
    ("fake", "raw", "expected"),
    [(True, "3", 3.0), (True, None, 600.0), (True, "0", 600.0), (True, "x", 600.0), (True, "601", 600.0),
     (False, "3", 600.0)],
)
def test_account_grace_can_be_shortened_only_in_fake_mode(monkeypatch, fake, raw, expected):
    if raw is None:
        monkeypatch.delenv(lifecycle.ACCOUNT_GRACE_ENV, raising=False)
    else:
        monkeypatch.setenv(lifecycle.ACCOUNT_GRACE_ENV, raw)
    assert lifecycle.account_grace_s(fake) == expected
```

Create `tests/integration/test_account_privacy.py` (R3: no `/api/diagnostics` yet; covers captured log records, `app.log`, SSE, every API body including `/health` and `GET /cookies`, and every file under the data root and the temp root):
```python
"""ค่าคุกกี้ของบัญชีชั่วคราวต้องอยู่ในหน่วยความจำเท่านั้น (M5 รอบ C spec 3 · แบบเดียวกับ AC-SET-06)

นำเข้าไฟล์ที่ค่าทุกตัว (และชื่อคุกกี้หนึ่งตัว) เป็น canary ที่ไม่ซ้ำกับอะไร แล้วใช้แอพเต็มชุดในโหมดข้อมูลปลอม
(open_services + create_app ตัวจริง คิวทำงานจริง ไม่ต่อเน็ต): probe ที่ใช้บัญชี งานที่ใช้บัญชีแล้วสำเร็จ
งานที่ใช้บัญชีแล้วพลาด /health และ GET /cookies · แล้วตรวจว่า canary ไม่อยู่ใน log (ทั้งที่จับได้และ app.log)
ข่าว SSE คำตอบของ API ทุกคำตอบ และไม่มีไฟล์ใดในโฟลเดอร์ข้อมูลหรือโฟลเดอร์ temp ที่มี canary
รายงานแจ้งปัญหา (/api/diagnostics) ยังไม่มีในแอพ (M6) จึงยังไม่ได้ตรวจ ดู docs/m4-followups.md
"""

from __future__ import annotations

import logging
import tempfile
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from yttoolkit import lifecycle, probe
from yttoolkit.app import AppContext, create_app
from yttoolkit.core.events import Event

PORT = 8787
TOKEN = "privacy-token"
BASE = f"http://127.0.0.1:{PORT}"
AUTH = {"X-Toolkit-Token": TOKEN, "Origin": BASE}
CANARIES = ("cnry-sapisid-5e1f0a", "cnry-3psid-77b2c4", "cnry-login-0d9e31", "cnry-name-a4f6e8", "cnry-pref-31c7d5")
ACCOUNT_FILE = (
    "# Netscape HTTP Cookie File\n"
    f".youtube.com\tTRUE\t/\tTRUE\t1999999999\tSAPISID\t{CANARIES[0]}\n"
    f"#HttpOnly_.youtube.com\tTRUE\t/\tTRUE\t1999999999\t__Secure-3PSID\t{CANARIES[1]}\n"
    f".youtube.com\tTRUE\t/\tTRUE\t1999999999\tLOGIN_INFO\t{CANARIES[2]}\n"
    f".youtube.com\tTRUE\t/\tFALSE\t1999999999\t{CANARIES[3]}\tx\n"
    f".google.com\tTRUE\t/\tFALSE\t0\tPREF\t{CANARIES[4]}\n"
)
VIDEO = {"maxQuality": False, "splitChapters": False, "noAudio": False, "audioLanguage": "original"}


def _assert_clean(text: str, where: str) -> None:
    for canary in CANARIES:
        assert canary not in text, f"{canary} หลุดไปที่ {where}"


def _wait_done(services, job_id: str, timeout: float = 20.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        job = services.queue.store.get(job_id)
        if job is not None and job.status in ("done", "failed", "cancelled", "interrupted"):
            return job
        time.sleep(0.05)
    raise AssertionError(f"งาน {job_id} ไม่จบใน {timeout} วินาที")


@pytest.fixture
def app_env(paths, fake_platform, tmp_path, monkeypatch, caplog):
    temp_root = tmp_path / "temp-root"
    temp_root.mkdir()
    monkeypatch.setattr(tempfile, "tempdir", str(temp_root))  # ไฟล์ชั่วคราวทุกไฟล์ของโปรเซสนี้มาอยู่ที่นี่
    root = logging.getLogger()
    before = list(root.handlers)
    probe.setup_file_log(paths)  # app.log จริงพร้อมตัวกรอง (แบบเดียวกับ start)
    caplog.set_level(logging.DEBUG)
    services = lifecycle.open_services(paths, fake_platform, fake=True)
    ctx = AppContext(
        paths=paths, plat=fake_platform, port=PORT, token=TOKEN, version="0.1.0", commit=None,
        output_dir=services.settings.output_dir(), request_shutdown=lambda: None,
        health=lambda: {"tools": {}, "disk": {}, "output": {}, "network": {}},
        db=services.db, videos=services.videos, extractor=services.extractor, cache_root=paths.cache, fake=True,
        subtitles=services.subtitles, settings=services.settings, queue=services.queue, events=services.events,
        media=services.media, pinned=services.pinned, on_bot_check=services.queue.brake,
    )  # fmt: skip
    ctx.captures = services.captures
    ctx.accounts = services.accounts
    client = TestClient(create_app(ctx), base_url=BASE)
    sub = services.events.subscribe()
    services.queue.start()
    try:
        yield services, client, sub, temp_root
    finally:
        lifecycle.shutdown_services(services, timeout=2.0)
        services.db.close()
        for handler in list(root.handlers):
            if handler not in before:
                root.removeHandler(handler)
                handler.close()


def test_canaries_never_leave_memory(app_env, paths, caplog) -> None:
    services, client, sub, temp_root = app_env
    bodies: list[str] = []

    def call(method: str, url: str, **kwargs) -> dict:
        resp = client.request(method, url, **kwargs)
        bodies.append(resp.text)
        return resp.json()

    status = call("POST", "/api/cookies/import", json={"text": ACCOUNT_FILE, "acceptWarning": True}, headers=AUTH)
    assert status["active"] is True
    call("POST", "/api/cookies/import", json={"text": "broken " + CANARIES[0], "acceptWarning": True}, headers=AUTH)
    assert call("GET", "/api/videos/ACCOUNTAGE1")["title"] == "คลิปจำกัดอายุ"  # probe ที่ใช้บัญชี
    private = call("GET", "/api/videos/PRIVATEVID1")  # บัญชีไม่มีสิทธิ์: ข้อความ "ลองด้วยบัญชีแล้ว..."
    assert private["error"]["code"] == "E_VIDEO_PRIVATE"
    jobs = call("POST", "/api/jobs", headers=AUTH, json={"items": [
        {"videoId": "ACCOUNTAGE1", "kind": "video", "params": VIDEO},
        {"videoId": "PRIVATEVID1", "kind": "video", "params": VIDEO},
    ]})["jobs"]  # fmt: skip
    done, failed = (_wait_done(services, job["id"]) for job in jobs)
    assert done.status == "done"
    assert failed.status == "failed" and failed.error_code == "E_VIDEO_PRIVATE"
    call("GET", "/api/jobs")
    call("GET", "/api/health")
    assert call("GET", "/api/cookies")["active"] is True
    assert call("DELETE", "/api/cookies", headers=AUTH)["active"] is False

    for text in bodies:
        _assert_clean(text, "คำตอบของ API")
    events = []
    while isinstance(item := sub.get(0), Event):
        events.append(item)
    assert any(e.name == "account" for e in events)
    for event in events:
        _assert_clean(repr(event.data), f"ข่าว SSE {event.name}")
    for record in caplog.records:
        _assert_clean(record.getMessage(), "log")
        if record.exc_info:
            _assert_clean(logging.Formatter().formatException(record.exc_info), "traceback ใน log")
    for handler in logging.getLogger().handlers:
        handler.flush()
    log_file = paths.logs / "app.log"
    assert log_file.is_file()
    _assert_clean(log_file.read_text(encoding="utf-8"), "app.log")

    for folder in (paths.data_root, temp_root):  # data/ work/ run/ cache/ output/ app.db และ temp
        for path in Path(folder).rglob("*"):
            _assert_clean(path.name, f"ชื่อไฟล์ {path.name}")
            if path.is_file():
                data = path.read_bytes()
                for canary in CANARIES:
                    assert canary.encode() not in data, f"{canary} อยู่ในไฟล์ {path.relative_to(folder)}"
```

- [ ] **Step 2: Run them, expect FAIL**

Run: `cd "$WORKTREE" && uv run pytest tests/unit/test_lifecycle.py tests/integration/test_account_privacy.py -q -W error -p no:cacheprovider`
Expected: `AttributeError: 'Services' object has no attribute 'accounts'` and `AttributeError: module 'yttoolkit.lifecycle' has no attribute 'ACCOUNT_GRACE_ENV'`.

- [ ] **Step 3: Wire the service in `lifecycle.py`**
Replace (1):
```python
from .app import AppContext, create_app
from .config import CODE_ROOT, HOST, Paths, default_paths, env_flag
from .core import files, thai_fallback, tools
from .core.advanced import ADS_SUFFIX
from .core.capture import CaptureService
from .core.comments import PinnedCommentService
from .core.db import Database, purge_stale_cache
from .core.events import CLOSED, Event, EventBus
from .core.extractor import Extractor, FakeExtractor, YtDlpExtractor, visitor_session
from .core.handlers import (
    CONTACT_SHEET_SUFFIX,
    FRAMES_ZIP_SUFFIX,
```
with:
```python
from .app import AppContext, create_app
from .config import CODE_ROOT, HOST, Paths, default_paths, env_flag
from .core import files, thai_fallback, tools
from .core.account_session import GRACE_S, AccountService
from .core.advanced import ADS_SUFFIX
from .core.capture import CaptureService
from .core.comments import PinnedCommentService
from .core.db import Database, purge_stale_cache
from .core.events import CLOSED, Event, EventBus
from .core.extractor import Extractor, FakeExtractor, YtDlpExtractor, parse_account_cookies, visitor_session
from .core.handlers import (
    CONTACT_SHEET_SUFFIX,
    FRAMES_ZIP_SUFFIX,
```

Replace (2):
```python
# โหมดข้อมูลปลอม (E2E) ไม่ต้องเว้นช่วงเริ่มงานยูทูป 2-5 วินาทีเหมือนของจริง
FAKE_DELAY_RANGE = (0.05, 0.2)
QUEUE_SHUTDOWN_TIMEOUT_S = 5.0  # รองานที่กำลังทำหยุดตอนปิดโปรแกรมไม่เกินเท่านี้
GRACEFUL_SHUTDOWN_S = 3  # uvicorn รอ request ที่ค้าง (เช่นสตรีมข่าว) ไม่เกินเท่านี้
TRAY_REFRESH_INTERVAL_S = 1.0  # อัปเดตตัวเลขงานในเมนู tray ไม่เกิน 1 ครั้งต่อวินาที
# ตอนเปิดโปรแกรม ล้างไฟล์ค้างในโฟลเดอร์ของงานที่หยุดกลางคันล่าสุดไม่เกินเท่านี้งาน (รวมงานที่เพิ่งกู้คืนเสมอ)
```
with:
```python
# โหมดข้อมูลปลอม (E2E) ไม่ต้องเว้นช่วงเริ่มงานยูทูป 2-5 วินาทีเหมือนของจริง
FAKE_DELAY_RANGE = (0.05, 0.2)
QUEUE_SHUTDOWN_TIMEOUT_S = 5.0  # รองานที่กำลังทำหยุดตอนปิดโปรแกรมไม่เกินเท่านี้
# M5 รอบ C: ย่น grace 10 นาทีของบัญชีชั่วคราว (วินาที) ใช้ได้เฉพาะโหมดข้อมูลปลอม (e2e ของคิว)
ACCOUNT_GRACE_ENV = "YT_TOOLKIT_ACCOUNT_GRACE_S"
GRACEFUL_SHUTDOWN_S = 3  # uvicorn รอ request ที่ค้าง (เช่นสตรีมข่าว) ไม่เกินเท่านี้
TRAY_REFRESH_INTERVAL_S = 1.0  # อัปเดตตัวเลขงานในเมนู tray ไม่เกิน 1 ครั้งต่อวินาที
# ตอนเปิดโปรแกรม ล้างไฟล์ค้างในโฟลเดอร์ของงานที่หยุดกลางคันล่าสุดไม่เกินเท่านี้งาน (รวมงานที่เพิ่งกู้คืนเสมอ)
```

Replace (3):
```python
    queue: QueueRunner
    pinned: PinnedCommentService | None = None  # ส่งต่อเป็น ctx.pinned (router ข้อมูลคลิปใช้ตัวนี้ ไม่สร้างใหม่)
    captures: CaptureService | None = None  # M5 รอบ B2 ถ่ายภาพคมตรงจุด ส่งต่อเป็น ctx.captures


def open_services(paths: Paths, plat: Platform, fake: bool = False) -> Services:
```
with:
```python
    queue: QueueRunner
    pinned: PinnedCommentService | None = None  # ส่งต่อเป็น ctx.pinned (router ข้อมูลคลิปใช้ตัวนี้ ไม่สร้างใหม่)
    captures: CaptureService | None = None  # M5 รอบ B2 ถ่ายภาพคมตรงจุด ส่งต่อเป็น ctx.captures
    accounts: AccountService | None = None  # M5 รอบ C บัญชียูทูปชั่วคราว ส่งต่อเป็น ctx.accounts


def account_grace_s(fake: bool) -> float:
    """grace ของบัญชีชั่วคราว: ปกติ 10 นาที · โหมดข้อมูลปลอมย่นได้ด้วย YT_TOOLKIT_ACCOUNT_GRACE_S (0 < ค่า ≤ 600)"""
    raw = os.environ.get(ACCOUNT_GRACE_ENV) if fake else None
    try:
        value = float(raw) if raw else GRACE_S
    except ValueError:
        return GRACE_S
    return value if 0 < value <= GRACE_S else GRACE_S


def open_services(paths: Paths, plat: Platform, fake: bool = False) -> Services:
```

Replace (4):
```python
        )
        # ตัวทำงานอ่าน deps ตอนรันงาน: E_BOT_CHECK ที่งานโน้ตกลืนไว้ (คอมเมนต์ปักหมุด) ยังพักคิวได้
        deps.on_bot_check = queue.brake
        # M5 รอบ B2: ถ่ายภาพคมตรงจุดไม่ผ่านคิว แต่เคารพการพักคิว (ยูทูปขอตรวจสอบ) และสั่งพักคิวเองเมื่อเจอ
        captures = CaptureService(
            videos,
```
with:
```python
        )
        # ตัวทำงานอ่าน deps ตอนรันงาน: E_BOT_CHECK ที่งานโน้ตกลืนไว้ (คอมเมนต์ปักหมุด) ยังพักคิวได้
        deps.on_bot_check = queue.brake
        # M5 รอบ C: บัญชียูทูปชั่วคราวในหน่วยความจำ ฟังคิว (grace เมื่อคิวว่าง) ประกาศสถานะทาง SSE
        # ลบ/แทนบัญชี = ทิ้งข้อมูลคลิปที่ได้มาด้วยบัญชีนั้น · งานในคิวและถ่ายภาพคมลองซ้ำด้วยบัญชีผ่านตัวนี้
        accounts = AccountService(
            parse_account_cookies,
            publish=events.publish,
            busy=lambda: queue.pending_count() > 0,
            on_clear=videos.forget_signed_in,
            grace_s=account_grace_s(fake),
        )
        queue.listener = accounts
        deps.accounts = accounts
        # M5 รอบ B2: ถ่ายภาพคมตรงจุดไม่ผ่านคิว แต่เคารพการพักคิว (ยูทูปขอตรวจสอบ) และสั่งพักคิวเองเมื่อเจอ
        captures = CaptureService(
            videos,
```

Replace (5):
```python
            settings,
            queue,
            work_root=paths.work,
        )
    except BaseException:
        db.close()
```
with:
```python
            settings,
            queue,
            work_root=paths.work,
            accounts=accounts,
        )
    except BaseException:
        db.close()
```

Replace (6):
```python
        queue=queue,
        pinned=pinned,
        captures=captures,
    )
```
with:
```python
        queue=queue,
        pinned=pinned,
        captures=captures,
        accounts=accounts,
    )
```

Replace (7):
```python
        services.queue.shutdown(timeout=timeout)
    except Exception:
        log.exception("หยุดคิวงานไม่สำเร็จ")
    services.events.publish("app.shutdown", {})
    services.events.close()
```
with:
```python
        services.queue.shutdown(timeout=timeout)
    except Exception:
        log.exception("หยุดคิวงานไม่สำเร็จ")
    if services.accounts is not None:
        try:
            services.accounts.clear("shutdown")  # C6 (b): ปิดโปรแกรม = ลบบัญชีชั่วคราว (แท็บที่เปิดอยู่ได้ข่าวก่อน app.shutdown)
        except Exception:
            log.exception("ลบบัญชียูทูปชั่วคราวตอนปิดโปรแกรมไม่สำเร็จ")
    services.events.publish("app.shutdown", {})
    services.events.close()
```

Replace (8):
```python
    )
    # M5 รอบ B2: API ถ่ายภาพคม (create_app เปิด router เมื่อมีค่านี้) ตั้งแบบนี้ lane ของ app.py จึงไม่ชนกัน
    ctx.captures = services.captures
    if fake:
        # โหมดข้อมูลปลอมไม่เปิดหน้าต่างจริง (E2E รันบนเครื่องพนักงานได้โดยไม่มีหน้าต่างโผล่)
        ctx.open_folder = _fake_open_folder
```
with:
```python
    )
    # M5 รอบ B2: API ถ่ายภาพคม (create_app เปิด router เมื่อมีค่านี้) ตั้งแบบนี้ lane ของ app.py จึงไม่ชนกัน
    ctx.captures = services.captures
    ctx.accounts = services.accounts  # M5 รอบ C: API /cookies* แถวบัญชีใน /health และการลองซ้ำของ GET /videos/{id}
    if fake:
        # โหมดข้อมูลปลอมไม่เปิดหน้าต่างจริง (E2E รันบนเครื่องพนักงานได้โดยไม่มีหน้าต่างโผล่)
        ctx.open_folder = _fake_open_folder
```

- [ ] **Step 4: Run the tests, expect PASS** — same command as Step 2, then the full suite (the canary test runs the real queue in fake mode: about 2-5 s).

- [ ] **Step 5: Commit**
```bash
cd "$WORKTREE" && git add src/yttoolkit/lifecycle.py tests/unit/test_lifecycle.py tests/integration/test_account_privacy.py && git commit -F- <<'EOF'
feat(app): M5-C wire the temporary account service; canary test for logs, SSE, API and files

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
EOF
```

### Task 10: "ใช้บัญชียูทูปชั่วคราว" on the clip-page error, the failed-job row and toast, the capture toast; mocked chromium e2e

**Files:**
- Modify: `web/src/pages/video/load-error.tsx` (`account?` prop), `web/src/pages/video/header.tsx` (passes it)
- Modify: `web/src/components/queue/job-row.tsx` (`FailedRow`), `web/src/components/queue/use-queue.ts` (part 2: failed-job toast, R5)
- Modify: `web/src/pages/video/capture/use-capture.ts`, `web/src/pages/video/capture/capture-store.test.ts`
- Create: `web/e2e/account.spec.ts`
- Modify: `web/e2e/video.spec.ts` (`PRIVATE_MESSAGE` + the button)

**Interfaces:**
- Consumes: C5 (`showAccountButton`, `ACCOUNT_KEY`, T5); C8 (`UseAccountButton`, `useAccountStatus`, `openAccountDialog`, `accountDialog`, T8); `LoadError` (`load-error.tsx:22`), `FailedRow` (`job-row.tsx:100`, its `retry` mutation), `notifyJobChange` (`use-queue.ts:163`), `runCapture` (`use-capture.ts`), `analyzeSettled` (`e2e/axe-settled.ts`, T5).
- Produces: C10. The e2e mocks `/api/cookies*` and the BBB clip's error (no real import, no job).

- [ ] **Step 1: Write the failing unit test** — in `web/src/pages/video/capture/capture-store.test.ts`:
Replace (1):
```ts
import { QueryClient } from "@tanstack/react-query"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

import { ApiError } from "@/lib/api"
import { QUEUE_KEY } from "@/lib/jobs"
import type { Capture } from "@/lib/types"
```
with:
```ts
import { QueryClient } from "@tanstack/react-query"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

import { accountDialog } from "@/components/account/account-store"
import { ACCOUNT_KEY } from "@/lib/account"
import { ApiError } from "@/lib/api"
import { QUEUE_KEY } from "@/lib/jobs"
import type { Capture } from "@/lib/types"
```

Replace (2):
```ts
    expect(invalidate).toHaveBeenCalledWith({ queryKey: QUEUE_KEY })
    expect(captureStore.get().busy).toBe(false)
  })
})
```
with:
```ts
    expect(invalidate).toHaveBeenCalledWith({ queryKey: QUEUE_KEY })
    expect(captureStore.get().busy).toBe(false)
  })

  it("M5 รอบ C: จำกัดอายุ/ส่วนตัวและยังไม่ได้ใช้บัญชี = toast มีปุ่ม ใช้บัญชียูทูปชั่วคราว นำเข้าแล้วถ่ายเวลาเดิมใหม่", async () => {
    const client = new QueryClient()
    api.postCapture.mockRejectedValueOnce(new ApiError(409, "E_AGE_RESTRICTED", "คลิปนี้จำกัดอายุ", null, null))
    await runCapture(client, BBB, 2_000)
    const [message, options] = toast.error.mock.lastCall as [string, { action: { label: string; onClick: () => void } }]
    expect(message).toBe("คลิปนี้จำกัดอายุ")
    expect(options.action.label).toBe("ใช้บัญชียูทูปชั่วคราว")
    options.action.onClick()
    const request = accountDialog.get().request
    expect(request?.origin).toBe("error")
    api.postCapture.mockResolvedValueOnce(item(2_000))
    request?.onImported?.()
    await vi.waitFor(() => expect(api.postCapture).toHaveBeenLastCalledWith(BBB, 2_000))
    accountDialog.close()
  })

  it("M5 รอบ C: ถือบัญชีอยู่แล้ว = ไม่มีปุ่ม (ข้อความ ลองด้วยบัญชีแล้ว… มาจาก backend)", async () => {
    const client = new QueryClient()
    client.setQueryData(ACCOUNT_KEY, { active: true, used: true })
    api.postCapture.mockRejectedValueOnce(new ApiError(404, "E_VIDEO_PRIVATE", "ลองด้วยบัญชีแล้วยังเปิดไม่ได้", null, null))
    await runCapture(client, BBB, 0)
    expect(toast.error).toHaveBeenLastCalledWith("ลองด้วยบัญชีแล้วยังเปิดไม่ได้")
  })
})
```

- [ ] **Step 2: Run it, expect FAIL**

Run: `cd "$WORKTREE/web" && npx vitest run src/pages/video/capture/capture-store.test.ts`
Expected: the first new test fails at `options.action` (`toast.error` was called with the message only).

- [ ] **Step 3: The capture toast (`use-capture.ts`)**
Replace (1):
```ts
import { useEffect, useState } from "react"
import { toast } from "sonner"

import { fill, th } from "@/i18n/th"
import { QUEUE_KEY, queueQuery } from "@/lib/jobs"
import type { Capture, VideoInfo } from "@/lib/types"

import { errorMessage, hasCode } from "../errors"
import { capturesKey, postCapture, withCapture } from "./capture-api"
```
with:
```ts
import { useEffect, useState } from "react"
import { toast } from "sonner"

import { openAccountDialog } from "@/components/account/account-store"
import { fill, th } from "@/i18n/th"
import { ACCOUNT_KEY, showAccountButton } from "@/lib/account"
import { ApiError } from "@/lib/api"
import { QUEUE_KEY, queueQuery } from "@/lib/jobs"
import type { AccountStatus, Capture, VideoInfo } from "@/lib/types"

import { errorMessage, hasCode } from "../errors"
import { capturesKey, postCapture, withCapture } from "./capture-api"
```

Replace (2):
```ts
      action: { label: th.capture.view, onClick: () => captureStore.view({ videoId, id: capture.id }) },
    })
  } catch (error) {
    toast.error(errorMessage(error, th.errors.unknown))
    if (hasCode(error, "E_BOT_CHECK") || hasCode(error, "E_QUEUE_PAUSED")) {
      void client.invalidateQueries({ queryKey: QUEUE_KEY })
    }
```
with:
```ts
      action: { label: th.capture.view, onClick: () => captureStore.view({ videoId, id: capture.id }) },
    })
  } catch (error) {
    // M5 รอบ C: จำกัดอายุ/ส่วนตัว + ยังไม่ได้ใช้บัญชี = toast มีปุ่ม "ใช้บัญชียูทูปชั่วคราว" นำเข้าแล้วถ่ายเวลาเดิมใหม่
    const active = client.getQueryData<AccountStatus>(ACCOUNT_KEY)?.active === true
    const account = showAccountButton(error instanceof ApiError ? error.code : null, active)
    const message = errorMessage(error, th.errors.unknown)
    if (account) {
      const retry = () => void runCapture(client, videoId, ms)
      toast.error(message, {
        action: { label: th.account.use, onClick: () => openAccountDialog({ origin: "error", onImported: retry }) },
      })
    } else {
      toast.error(message)
    }
    if (hasCode(error, "E_BOT_CHECK") || hasCode(error, "E_QUEUE_PAUSED")) {
      void client.invalidateQueries({ queryKey: QUEUE_KEY })
    }
```

- [ ] **Step 4: The clip-page error**

`web/src/pages/video/load-error.tsx`:
Replace (1):
```tsx
import type { Ref } from "react"
import { Link } from "react-router"

import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
import { Button, buttonVariants } from "@/components/ui/button"
import { th } from "@/i18n/th"

import { canRetry, errorMessage } from "./errors"
```
with:
```tsx
import type { Ref } from "react"
import { Link } from "react-router"

import { UseAccountButton } from "@/components/account/account-button"
import { useAccountStatus } from "@/components/account/use-account"
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert"
import { Button, buttonVariants } from "@/components/ui/button"
import { th } from "@/i18n/th"
import { showAccountButton } from "@/lib/account"
import { ApiError } from "@/lib/api"

import { canRetry, errorMessage } from "./errors"
```

Replace (2):
```tsx
  showHome?: boolean
  /** ให้กล่องรับโฟกัสจากโค้ดได้ (tabIndex -1) ใช้กับ error ของทั้งหน้าที่ไม่มีชื่อคลิปให้โฟกัส */
  ref?: Ref<HTMLDivElement>
}

/** กล่อง error ของหน้า W2: ข้อความไทยจาก envelope + ปุ่มลองใหม่ (ซ่อนเมื่อลองใหม่ไม่ช่วย) */
export function LoadError({ title, error, onRetry, showHome = false, ref }: Props) {
  const retry = canRetry(error)
  return (
    <Alert ref={ref} tabIndex={ref ? -1 : undefined} variant="destructive" className="outline-none">
      <CircleX aria-hidden />
      <AlertTitle>{title}</AlertTitle>
      <AlertDescription>{errorMessage(error, th.errors.unknown)}</AlertDescription>
      {(retry || showHome) && (
        <div className="col-start-2 mt-2 flex flex-wrap gap-2">
          {retry && (
            <Button variant="outline" size="sm" onClick={onRetry}>
              {th.common.retry}
```
with:
```tsx
  showHome?: boolean
  /** ให้กล่องรับโฟกัสจากโค้ดได้ (tabIndex -1) ใช้กับ error ของทั้งหน้าที่ไม่มีชื่อคลิปให้โฟกัส */
  ref?: Ref<HTMLDivElement>
  /** M5 รอบ C: error จำกัดอายุ/ส่วนตัว + ยังไม่ได้ใช้บัญชี = ปุ่มหลัก "ใช้บัญชียูทูปชั่วคราว" แล้วทำ onImported หลังนำเข้า */
  account?: { onImported: () => void }
}

/** กล่อง error ของหน้า W2: ข้อความไทยจาก envelope + ปุ่มลองใหม่ (ซ่อนเมื่อลองใหม่ไม่ช่วย) */
export function LoadError({ title, error, onRetry, showHome = false, ref, account }: Props) {
  const retry = canRetry(error)
  const { active } = useAccountStatus()
  const offerAccount = account !== undefined && showAccountButton(error instanceof ApiError ? error.code : null, active)
  return (
    <Alert ref={ref} tabIndex={ref ? -1 : undefined} variant="destructive" className="outline-none">
      <CircleX aria-hidden />
      <AlertTitle>{title}</AlertTitle>
      <AlertDescription>{errorMessage(error, th.errors.unknown)}</AlertDescription>
      {(retry || showHome || offerAccount) && (
        <div className="col-start-2 mt-2 flex flex-wrap gap-2">
          {offerAccount && <UseAccountButton variant="default" onImported={account.onImported} />}
          {retry && (
            <Button variant="outline" size="sm" onClick={onRetry}>
              {th.common.retry}
```

`web/src/pages/video/header.tsx`:
Replace (1):
```tsx
          title={t.loadError}
          error={video.error}
          onRetry={() => void video.refetch()}
        />
      )
    }
```
with:
```tsx
          title={t.loadError}
          error={video.error}
          onRetry={() => void video.refetch()}
          account={{ onImported: () => void video.refetch() }}
        />
      )
    }
```

- [ ] **Step 5: The failed job (row and toast, R5)**

`web/src/components/queue/job-row.tsx`:
Replace (1):
```tsx
import { useState, type ComponentProps, type ReactNode } from "react"
import { toast } from "sonner"

import { Badge } from "@/components/ui/badge"
import { Button, buttonVariants } from "@/components/ui/button"
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from "@/components/ui/collapsible"
import { Progress } from "@/components/ui/progress"
import { Spinner } from "@/components/ui/spinner"
import { fill, th } from "@/i18n/th"
import { outputUrl } from "@/lib/jobs"
import type { Job } from "@/lib/types"
import { cn } from "cn"
```
with:
```tsx
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
import { showAccountButton } from "@/lib/account"
import { outputUrl } from "@/lib/jobs"
import type { Job } from "@/lib/types"
import { cn } from "cn"
```

Replace (2):
```tsx
  const Icon = interrupted ? CirclePause : CircleX
  const code = job.error?.code
  const detail = job.error?.detail
  return (
    <li className={ROW} data-job-id={job.id}>
      <Icon aria-hidden className={cn("mt-0.5 size-4 shrink-0", interrupted ? "text-warning" : "text-destructive")} />
      <div className="flex min-w-0 flex-1 flex-col gap-0.5">
        <RowTitle job={job} />
        <p className={cn("text-sm", !interrupted && "text-destructive")}>{job.error?.message ?? th.queue.interrupted}</p>
        {code && (
          <Collapsible open={open} onOpenChange={setOpen}>
            <CollapsibleTrigger
```
with:
```tsx
  const Icon = interrupted ? CirclePause : CircleX
  const code = job.error?.code
  const detail = job.error?.detail
  // M5 รอบ C: จำกัดอายุ/ส่วนตัว + ยังไม่ได้ใช้บัญชี = ปุ่ม "ใช้บัญชียูทูปชั่วคราว" นำเข้าแล้วลองงานนี้ใหม่ (params เดิม)
  const { active } = useAccountStatus()
  const offerAccount = showAccountButton(code, active)
  return (
    <li className={ROW} data-job-id={job.id}>
      <Icon aria-hidden className={cn("mt-0.5 size-4 shrink-0", interrupted ? "text-warning" : "text-destructive")} />
      <div className="flex min-w-0 flex-1 flex-col gap-0.5">
        <RowTitle job={job} />
        <p className={cn("text-sm", !interrupted && "text-destructive")}>{job.error?.message ?? th.queue.interrupted}</p>
        {offerAccount && (
          <div className="pt-1">
            <UseAccountButton onImported={() => retry.mutate()} />
          </div>
        )}
        {code && (
          <Collapsible open={open} onOpenChange={setOpen}>
            <CollapsibleTrigger
```

`web/src/components/queue/use-queue.ts`:
Replace (1):
```ts
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { useCallback, useEffect, useSyncExternalStore } from "react"
import { toast } from "sonner"

import { showRemovedToast } from "@/components/account/use-account"
import { fill, th } from "@/i18n/th"
import type { AccountEvent } from "@/lib/account"
import { ApiError } from "@/lib/api"
import { connectEvents } from "@/lib/events"
import { cancelJob, JOBS_KEY, jobsQuery, queueQuery, reorderJobs, retryJob, revealOutput } from "@/lib/jobs"
import type { Job } from "@/lib/types"

import { jobTitle } from "./job-text"
```
with:
```ts
import { useMutation, useQuery, useQueryClient, type QueryClient } from "@tanstack/react-query"
import { useCallback, useEffect, useSyncExternalStore } from "react"
import { toast } from "sonner"

import { openAccountDialog } from "@/components/account/account-store"
import { showRemovedToast } from "@/components/account/use-account"
import { fill, th } from "@/i18n/th"
import { ApiError } from "@/lib/api"
import { ACCOUNT_KEY, showAccountButton, type AccountEvent } from "@/lib/account"
import { connectEvents } from "@/lib/events"
import { cancelJob, JOBS_KEY, jobsQuery, queueQuery, reorderJobs, retryJob, revealOutput } from "@/lib/jobs"
import type { AccountStatus, Job } from "@/lib/types"

import { jobTitle } from "./job-text"
```

Replace (2):
```ts
  }
}

function notifyJobChange(before: Job | undefined, after: Job): void {
  const kind = jobToast(before, after)
  const title = jobTitle(after)
  if (kind === "finished") {
```
with:
```ts
  }
}

/** ลองงานใหม่หลังนำเข้าบัญชีจาก toast (แถวในชีตใช้ useJobAction) · ไม่สำเร็จ = toast แล้วโหลดรายการงานใหม่ */
async function retryAfterImport(client: QueryClient, id: string): Promise<void> {
  try {
    const job = await retryJob(id)
    client.setQueryData<Job[]>(JOBS_KEY, (old) => applyActionResult(old, job))
  } catch {
    toast.error(th.queue.actionFailed)
    void client.invalidateQueries({ queryKey: JOBS_KEY })
  }
}

function notifyJobChange(client: QueryClient, before: Job | undefined, after: Job): void {
  const kind = jobToast(before, after)
  const title = jobTitle(after)
  if (kind === "finished") {
```

Replace (3):
```ts
        : undefined,
    })
  } else if (kind === "failed") {
    toast.error(fill(th.queue.failed, { title }), {
      id: `job-${after.id}`,
      description: after.error?.message,
      duration: Infinity,
      action: { label: th.queue.details, onClick: () => queueSheet.open(after.id) },
    })
  }
}
```
with:
```ts
        : undefined,
    })
  } else if (kind === "failed") {
    const details = { label: th.queue.details, onClick: () => queueSheet.open(after.id) }
    // M5 รอบ C: จำกัดอายุ/ส่วนตัว + ยังไม่ได้ใช้บัญชี = ปุ่มหลักของ toast คือ "ใช้บัญชียูทูปชั่วคราว" (ดูรายละเอียดเป็นปุ่มรอง)
    const active = client.getQueryData<AccountStatus>(ACCOUNT_KEY)?.active === true
    const account = showAccountButton(after.error?.code, active)
      ? {
          label: th.account.use,
          onClick: () => openAccountDialog({ origin: "error", onImported: () => void retryAfterImport(client, after.id) }),
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

Replace (4):
```ts
    () =>
      connectEvents(client, {
        onShutdown: () => toast.dismiss(),
        onJobChange: notifyJobChange,
        onAccount: notifyAccount,
      }),
    [client],
```
with:
```ts
    () =>
      connectEvents(client, {
        onShutdown: () => toast.dismiss(),
        onJobChange: (before, after) => notifyJobChange(client, before, after),
        onAccount: notifyAccount,
      }),
    [client],
```

- [ ] **Step 6: E2E (written here, run at the final gate)**

Create `web/e2e/account.spec.ts`:
```ts
/// <reference lib="dom" />
import { expect, test, type Page } from "@playwright/test"

import { analyzeSettled } from "./axe-settled"

/**
 * M5 รอบ C บัญชียูทูปชั่วคราว (spec 1.1-1.3): error ของหน้า W2 → ปุ่ม → dialog → นำเข้า → แถบบนหน้า → ลบออกตอนนี้
 * โปรเจกต์ chromium: /api/cookies* และข้อมูลคลิปตอนติดจำกัดอายุจำลองด้วย page.route ทั้งหมด (ไม่นำเข้าจริง ไม่ต่อยูทูป)
 * ใช้คลิป Big Buck Bunny ของ backend ปลอม: คำขอแรกตอบ E_AGE_RESTRICTED หลังนำเข้าปล่อยผ่านไปที่ backend
 */

const BBB = "aqz-KE-bpKQ"
const AGE_MESSAGE = "คลิปนี้จำกัดอายุ ต้องเข้าสู่ระบบยูทูปถึงจะเปิดได้"
const TRIED_MESSAGE =
  "ลองด้วยบัญชีแล้วยังเปิดไม่ได้ บัญชีนี้อาจไม่มีสิทธิ์ดูคลิปนี้ หรือการเข้าสู่ระบบหมดอายุแล้ว ลองนำเข้าใหม่"
const INVALID = "ไฟล์นี้ใช้ไม่ได้ ตรวจว่าเข้าสู่ระบบยูทูปแล้วก่อนส่งออก แล้วส่งออก cookies.txt ใหม่"
const REMOVED = "ลบบัญชีออกจากแอพแล้ว · กลับไปกดออกจากระบบในหน้าต่างไม่ระบุตัวตน แล้วปิดหน้าต่าง"
const USE = "ใช้บัญชียูทูปชั่วคราว"
const GOOD_FILE = "# Netscape HTTP Cookie File\n.youtube.com\tTRUE\t/\tTRUE\t2000000000\tSAPISID\te2e-not-a-real-value\n"

type AccountMock = { imports: unknown[]; deletes: number; videoCalls: number; active: boolean }

/** จำลองบัญชีและข้อมูลคลิป: ยังไม่นำเข้า = /videos/BBB ตอบ error (code) · นำเข้าแล้ว = ปล่อยไป backend */
async function mockAccount(page: Page, options: { active?: boolean; code?: string; message?: string } = {}) {
  const state: AccountMock = { imports: [], deletes: 0, videoCalls: 0, active: options.active ?? false }
  // แบบเดียวกับ backend: เวลานำเข้าและเวลาลบมาจากวินาทีเดียวกัน (ตัดเศษมิลลิวินาที) ห่างกัน 2 ชม. พอดี
  const status = () => {
    if (!state.active) return { active: false, used: false }
    const at = Math.floor(Date.now() / 1000) * 1000
    return { active: true, importedAt: new Date(at).toISOString(), expiresAt: new Date(at + 7_200_000).toISOString(), used: false }
  }
  await page.route("**/api/cookies", (route) => {
    if (route.request().method() === "DELETE") {
      state.deletes += 1
      state.active = false
    }
    return route.fulfill({ json: status() })
  })
  await page.route("**/api/cookies/import", (route) => {
    const body = route.request().postDataJSON() as { text: string; acceptWarning: boolean }
    state.imports.push(body)
    if (!body.text.includes("SAPISID")) {
      return route.fulfill({
        status: 422,
        json: { error: { code: "E_COOKIES_INVALID", message: INVALID, detail: "no YouTube sign-in cookie" } },
      })
    }
    state.active = true
    return route.fulfill({ json: status() })
  })
  await page.route(`**/api/videos/${BBB}`, (route) => {
    state.videoCalls += 1
    if (state.active && !options.code) return route.continue()
    const code = options.code ?? "E_AGE_RESTRICTED"
    const message = options.message ?? AGE_MESSAGE
    return route.fulfill({ status: code === "E_VIDEO_PRIVATE" ? 404 : 409, json: { error: { code, message, detail: null } } })
  })
  return state
}

const errorCard = (page: Page) => page.getByRole("alert").filter({ hasText: "เปิดข้อมูลคลิปไม่สำเร็จ" })
const dialog = (page: Page) => page.getByRole("dialog", { name: USE })
const banner = (page: Page) => page.getByTestId("account-banner")
const toast = (page: Page, text: string) => page.locator("[data-sonner-toast]").filter({ hasText: text })

async function chooseFile(page: Page, text: string, name = "cookies.txt") {
  await dialog(page).getByLabel("cookies.txt").setInputFiles({ name, mimeType: "text/plain", buffer: Buffer.from(text) })
}

async function seriousViolations(page: Page) {
  const results = await analyzeSettled(page)
  return results.violations.filter((v) => v.impact === "serious" || v.impact === "critical").map((v) => v.id)
}

test("error จำกัดอายุ: ข้อความใหม่ + ปุ่ม · dialog มีคำเตือน คลิปส่วนตัว และ 6 ขั้นตอน · ยกเลิก/Esc ไม่ส่งอะไร", async ({ page }) => {
  const state = await mockAccount(page)
  await page.goto(`/v/${BBB}`)
  await expect(errorCard(page)).toContainText(AGE_MESSAGE)
  await expect(errorCard(page).getByRole("button", { name: "ลองใหม่" })).toHaveCount(0)
  await errorCard(page).getByRole("button", { name: USE }).click()
  const box = dialog(page)
  await expect(box).toBeVisible()
  await expect(box.getByRole("alert")).toContainText("ใช้บัญชีสำรองเท่านั้น")
  await expect(box).toContainText("คลิปส่วนตัว: ให้เจ้าของช่องแชร์คลิปให้อีเมลของบัญชีสำรองใน YouTube Studio ก่อน")
  await expect(box.getByRole("listitem")).toHaveText([
    "เปิดหน้าต่างไม่ระบุตัวตน (Ctrl+Shift+N)",
    "เข้าสู่ระบบยูทูปด้วยบัญชีสำรอง",
    "เปิด youtube.com/robots.txt ในแท็บเดิม",
    "ส่งออกไฟล์ cookies.txt ด้วยส่วนขยาย (ต้องอนุญาตให้ทำงานในหน้าต่างไม่ระบุตัวตน)",
    "เปิดหน้าต่างนั้นค้างไว้ ไม่ต้องเปิดยูทูปในหน้าต่างนั้น",
    "เลือกไฟล์ด้านล่าง",
  ])
  await expect(box.getByRole("button", { name: "นำเข้าแล้วลองใหม่" })).toBeDisabled()
  await expect(box.getByText(/คุกกี้/)).toHaveCount(0) // C5: UI ไม่พูดคำว่าคุกกี้
  await chooseFile(page, GOOD_FILE)
  await box.getByRole("button", { name: "ยกเลิก" }).click()
  await expect(box).toHaveCount(0)
  await errorCard(page).getByRole("button", { name: USE }).click()
  await chooseFile(page, GOOD_FILE)
  await page.keyboard.press("Escape")
  await expect(dialog(page)).toHaveCount(0)
  expect(state.imports).toEqual([])
  await expect(banner(page)).toHaveCount(0)
})

test("ไฟล์ใช้ไม่ได้ = ข้อความใต้ช่อง dialog ยังเปิด · ไฟล์เกิน 1 MB ไม่ถูกส่ง", async ({ page }) => {
  const state = await mockAccount(page)
  await page.goto(`/v/${BBB}`)
  await errorCard(page).getByRole("button", { name: USE }).click()
  await chooseFile(page, "not a cookie file\n")
  await dialog(page).getByRole("button", { name: "นำเข้าแล้วลองใหม่" }).click()
  await expect(dialog(page)).toContainText(INVALID)
  await expect(dialog(page).getByLabel("cookies.txt")).toHaveAttribute("aria-invalid", "true")
  expect(state.imports).toEqual([{ text: "not a cookie file\n", acceptWarning: true }])
  await chooseFile(page, "#".repeat(1_048_577), "big.txt")
  await expect(dialog(page)).toContainText(INVALID)
  await expect(dialog(page).getByRole("button", { name: "นำเข้าแล้วลองใหม่" })).toBeDisabled()
  expect(state.imports).toHaveLength(1)
})

test("นำเข้าไฟล์ที่ใช้ได้: dialog ปิด แถบบนหน้าขึ้น โหลดข้อมูลคลิปใหม่เอง · ลบออกตอนนี้ = toast ค้างไว้ แถบหาย", async ({ page }) => {
  const state = await mockAccount(page)
  await page.goto(`/v/${BBB}`)
  await errorCard(page).getByRole("button", { name: USE }).click()
  await chooseFile(page, GOOD_FILE)
  const calls = state.videoCalls
  await dialog(page).getByRole("button", { name: "นำเข้าแล้วลองใหม่" }).click()
  await expect(dialog(page)).toHaveCount(0)
  await expect(page.getByRole("heading", { level: 1 })).toContainText("Big Buck Bunny")
  expect(state.videoCalls).toBeGreaterThan(calls)
  expect(state.imports).toEqual([{ text: GOOD_FILE, acceptWarning: true }])
  await expect(banner(page)).toContainText(/กำลังใช้บัญชียูทูปชั่วคราว · ลบอัตโนมัติภายใน 02:00/)
  await page.goto("/history") // แถบอยู่ทุกหน้า
  await expect(banner(page)).toBeVisible()
  await banner(page).getByRole("button", { name: "ลบออกตอนนี้" }).click()
  await expect(toast(page, REMOVED)).toBeVisible()
  await expect(banner(page)).toHaveCount(0)
  expect(state.deletes).toBe(1)
  await page.waitForTimeout(5_000) // toast ไม่หายเอง
  await expect(toast(page, REMOVED)).toBeVisible()
})

test("ถือบัญชีอยู่แล้วแต่ยังเปิดไม่ได้: ข้อความ ลองด้วยบัญชีแล้ว… ไม่มีปุ่ม", async ({ page }) => {
  await mockAccount(page, { active: true, code: "E_VIDEO_PRIVATE", message: TRIED_MESSAGE })
  await page.goto(`/v/${BBB}`)
  await expect(errorCard(page)).toContainText(TRIED_MESSAGE)
  await expect(errorCard(page).getByRole("button", { name: USE })).toHaveCount(0)
  await expect(banner(page)).toBeVisible()
})

for (const scheme of ["light", "dark"] as const) {
  test(`axe ${scheme}: dialog และแถบบนหน้า ไม่มีปัญหาระดับ serious/critical`, async ({ page }) => {
    await page.emulateMedia({ colorScheme: scheme })
    await mockAccount(page)
    await page.goto(`/v/${BBB}`)
    await expect(page.locator("html")).toHaveClass(scheme === "dark" ? /dark/ : /light/)
    await errorCard(page).getByRole("button", { name: USE }).click()
    await expect(dialog(page)).toBeVisible()
    expect(await seriousViolations(page)).toEqual([])
    await chooseFile(page, GOOD_FILE)
    await dialog(page).getByRole("button", { name: "นำเข้าแล้วลองใหม่" }).click()
    await expect(banner(page)).toBeVisible()
    expect(await seriousViolations(page)).toEqual([])
  })
}

test("หน้าต่างแคบ 640 px: dialog และแถบบนหน้าไม่เลื่อนซ้ายขวา", async ({ page }) => {
  await page.setViewportSize({ width: 640, height: 720 })
  await mockAccount(page)
  await page.goto(`/v/${BBB}`)
  await errorCard(page).getByRole("button", { name: USE }).click()
  await expect(dialog(page)).toBeVisible()
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(640)
  await chooseFile(page, GOOD_FILE)
  await dialog(page).getByRole("button", { name: "นำเข้าแล้วลองใหม่" }).click()
  await expect(banner(page)).toBeVisible()
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(640)
})
```

In `web/e2e/video.spec.ts` (new `E_VIDEO_PRIVATE` copy from T1, and the button on the private clip's error):
Replace (1):
```ts
const ZOO = "jNQXAC9IVRw"
const UPCOMING = "UPCOMINGLV1"
const PRIVATE = "PRIVATEVID1"
const PRIVATE_MESSAGE = "คลิปนี้เป็นส่วนตัว เจ้าของต้องเปิดเป็นสาธารณะก่อน"
const BOT_MESSAGE = "ยูทูปขอให้ยืนยันว่าไม่ใช่บอท รอสัก 10 นาทีแล้วค่อยลองใหม่"
const NO_STORYBOARD_MESSAGE = 'คลิปนี้ไม่มีภาพตัวอย่างแบบเร็ว กด "ขอภาพคม" แทนได้'
const FRAME_LIST = "รายการภาพเฟรม"
```
with:
```ts
const ZOO = "jNQXAC9IVRw"
const UPCOMING = "UPCOMINGLV1"
const PRIVATE = "PRIVATEVID1"
const PRIVATE_MESSAGE = "คลิปนี้เป็นส่วนตัวหรือเฉพาะสมาชิก ต้องเข้าสู่ระบบด้วยบัญชีที่มีสิทธิ์ดู"
const BOT_MESSAGE = "ยูทูปขอให้ยืนยันว่าไม่ใช่บอท รอสัก 10 นาทีแล้วค่อยลองใหม่"
const NO_STORYBOARD_MESSAGE = 'คลิปนี้ไม่มีภาพตัวอย่างแบบเร็ว กด "ขอภาพคม" แทนได้'
const FRAME_LIST = "รายการภาพเฟรม"
```

Replace (2):
```ts
    await expect(page.locator('[data-slot="skeleton"]')).toHaveCount(0)
  })

  test("คลิปส่วนตัว: Alert ข้อความจาก backend + กลับหน้าแรก ไม่มีปุ่มลองใหม่ และไม่มีส่วนภาพเฟรม", async ({ page }) => {
    await page.goto(`/v/${PRIVATE}`)
    const alert = page.getByRole("alert")
    await expect(alert).toContainText("เปิดข้อมูลคลิปไม่สำเร็จ")
    await expect(alert).toContainText(PRIVATE_MESSAGE)
    await expect(alert.getByRole("button", { name: "ลองใหม่" })).toHaveCount(0)
    await expect(alert.getByRole("link", { name: "กลับหน้าแรก" })).toHaveAttribute("href", "/")
    await expect(page.getByRole("heading", { name: "ภาพเฟรม" })).toHaveCount(0)
```
with:
```ts
    await expect(page.locator('[data-slot="skeleton"]')).toHaveCount(0)
  })

  test("คลิปส่วนตัว: Alert ข้อความจาก backend + ใช้บัญชียูทูปชั่วคราว + กลับหน้าแรก ไม่มีปุ่มลองใหม่ และไม่มีส่วนภาพเฟรม", async ({ page }) => {
    await page.goto(`/v/${PRIVATE}`)
    const alert = page.getByRole("alert")
    await expect(alert).toContainText("เปิดข้อมูลคลิปไม่สำเร็จ")
    await expect(alert).toContainText(PRIVATE_MESSAGE)
    await expect(alert.getByRole("button", { name: "ใช้บัญชียูทูปชั่วคราว" })).toBeVisible() // M5 รอบ C
    await expect(alert.getByRole("button", { name: "ลองใหม่" })).toHaveCount(0)
    await expect(alert.getByRole("link", { name: "กลับหน้าแรก" })).toHaveAttribute("href", "/")
    await expect(page.getByRole("heading", { name: "ภาพเฟรม" })).toHaveCount(0)
```

- [ ] **Step 7: Run the web checks, expect PASS** — `cd "$WORKTREE/web" && npm run typecheck && npm run lint && npm test` (no Playwright in the lane).

- [ ] **Step 8: Commit**
```bash
cd "$WORKTREE" && git add web/src/pages/video/load-error.tsx web/src/pages/video/header.tsx web/src/components/queue/job-row.tsx web/src/components/queue/use-queue.ts web/src/pages/video/capture/use-capture.ts web/src/pages/video/capture/capture-store.test.ts web/e2e/account.spec.ts web/e2e/video.spec.ts && git commit -F- <<'EOF'
feat(web): M5-C use-account button on clip, failed-job and capture errors

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
EOF
```

### Task 11: Settings › ขั้นสูง tab and the health account row

**Files:**
- Modify: `web/src/pages/settings.tsx` (`TABS`, trigger, panel)
- Create: `web/src/pages/settings/advanced-panel.tsx`
- Modify: `web/src/pages/settings/health-panel.tsx` (`AccountRow`)
- Create: `web/e2e/settings-advanced.spec.ts`
- Modify: `web/e2e/health.spec.ts` (append two tests)

**Interfaces:**
- Consumes: C5 (`th.account.*`, `th.settings.tabs.advanced`, `th.health.rows.account`, `accountQuery`, `deleteTime`, `localClock`, `AccountHealth`, T5); C8 (`UseAccountButton`, `useDeleteAccount`, `useNow`, T8); `HealthPanel` (`health-panel.tsx:46-141`), `TONE`, `th.general.loadError`, `th.common.retry`.
- Produces: C11.

- [ ] **Step 1: Write the e2e specs (run at the final gate)**

Create `web/e2e/settings-advanced.spec.ts`:
```ts
/// <reference lib="dom" />
import { expect, test, type Page } from "@playwright/test"

import { analyzeSettled } from "./axe-settled"

/**
 * M5 รอบ C แท็บ ตั้งค่า > ขั้นสูง (/settings/advanced, spec 1.1) และแถว "บัญชียูทูป" ในหน้าตรวจสุขภาพ (spec 1.4)
 * โปรเจกต์ chromium: /api/cookies* จำลองด้วย page.route (ไม่นำเข้าจริง)
 */

const INTRO =
  "ใช้เมื่อต้องโหลดคลิปจำกัดอายุ คลิปส่วนตัว หรือคลิปเฉพาะสมาชิก แอพเก็บการเข้าสู่ระบบไว้ชั่วคราวและลบเองเมื่อโหลดเสร็จ"
const USE = "ใช้บัญชียูทูปชั่วคราว"
const GOOD_FILE = "# Netscape HTTP Cookie File\n.youtube.com\tTRUE\t/\tTRUE\t2000000000\tLOGIN_INFO\te2e-not-a-real-value\n"

async function mockAccount(page: Page) {
  const state = { active: false, imports: 0, deletes: 0 }
  const status = () => {
    if (!state.active) return { active: false, used: false }
    const at = Math.floor(Date.now() / 1000) * 1000
    return { active: true, importedAt: new Date(at).toISOString(), expiresAt: new Date(at + 7_200_000).toISOString(), used: false }
  }
  await page.route("**/api/cookies", (route) => {
    if (route.request().method() === "DELETE") {
      state.deletes += 1
      state.active = false
    }
    return route.fulfill({ json: status() })
  })
  await page.route("**/api/cookies/import", (route) => {
    state.imports += 1
    state.active = true
    return route.fulfill({ json: status() })
  })
  return state
}

const panelStatus = (page: Page) => page.getByTestId("account-status")

test("แท็บขั้นสูง: คำอธิบาย สถานะ ปุ่ม · dialog ปุ่มนำเข้าเป็น นำเข้า · นำเข้าแล้วมีเวลาที่จะลบและปุ่มลบออกตอนนี้", async ({ page }) => {
  const state = await mockAccount(page)
  await page.goto("/settings")
  await page.getByRole("tab", { name: "ขั้นสูง" }).click()
  await expect(page).toHaveURL(/\/settings\/advanced$/)
  await expect(page.getByText(INTRO)).toBeVisible()
  await expect(panelStatus(page)).toHaveText("ไม่ได้ใช้บัญชี")
  await expect(panelStatus(page).getByRole("button", { name: "ลบออกตอนนี้" })).toHaveCount(0)
  await expect(page.getByRole("switch")).toHaveCount(0) // ไม่มี Switch หรือตัวเลือกแหล่งแบบ PRD เดิม
  await page.getByRole("button", { name: USE }).click()
  const dialog = page.getByRole("dialog", { name: USE })
  await expect(dialog.getByRole("button", { name: "นำเข้าแล้วลองใหม่" })).toHaveCount(0)
  await dialog.getByLabel("cookies.txt").setInputFiles({ name: "cookies.txt", mimeType: "text/plain", buffer: Buffer.from(GOOD_FILE) })
  await dialog.getByRole("button", { name: "นำเข้า", exact: true }).click()
  await expect(dialog).toHaveCount(0)
  await expect(panelStatus(page)).toContainText(/ใช้บัญชีชั่วคราวอยู่ ลบอัตโนมัติภายใน 02:00/)
  await panelStatus(page).getByRole("button", { name: "ลบออกตอนนี้" }).click()
  await expect(panelStatus(page)).toHaveText("ไม่ได้ใช้บัญชี")
  await expect(page.locator("[data-sonner-toast]").filter({ hasText: "ลบบัญชีออกจากแอพแล้ว" })).toBeVisible()
  expect([state.imports, state.deletes]).toEqual([1, 1])
})

for (const scheme of ["dark", "light"] as const) {
  test(`axe ${scheme}: แท็บขั้นสูงไม่มีปัญหาระดับ serious/critical`, async ({ page }) => {
    await page.emulateMedia({ colorScheme: scheme })
    await mockAccount(page)
    await page.goto("/settings/advanced")
    await expect(page.getByText(INTRO)).toBeVisible()
    await expect(page.locator("html")).toHaveClass(scheme === "dark" ? /dark/ : /light/)
    const results = await analyzeSettled(page)
    expect(results.violations.filter((v) => v.impact === "serious" || v.impact === "critical").map((v) => v.id)).toEqual([])
  })
}

test("หน้าต่างแคบ 640 px: แท็บขั้นสูงไม่เลื่อนซ้ายขวา", async ({ page }) => {
  await page.setViewportSize({ width: 640, height: 800 })
  await mockAccount(page)
  await page.goto("/settings/advanced")
  await expect(page.getByText(INTRO)).toBeVisible()
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(640)
})
```

Append to `web/e2e/health.spec.ts`:
Replace (1):
```ts
  await expect(page.getByText("ปิดโปรแกรมแล้ว")).toBeVisible()
  await expect(page.getByText("แจ้งเตือนเก่า")).toHaveCount(0)
})
```
with:
```ts
  await expect(page.getByText("ปิดโปรแกรมแล้ว")).toBeVisible()
  await expect(page.getByText("แจ้งเตือนเก่า")).toHaveCount(0)
})

test("M5 รอบ C: แถว บัญชียูทูป บอกสถานะอย่างเดียว · ไม่ได้ใช้บัญชี", async ({ page }) => {
  await page.goto("/settings/health")
  const row = page.getByTestId("tool-account")
  await expect(row).toContainText("บัญชียูทูป", { timeout: 15_000 })
  await expect(row).toContainText("ไม่ได้ใช้บัญชี")
  await expect(row).toContainText("พร้อม")
})

test("M5 รอบ C: ใช้บัญชีอยู่ = ใช้บัญชีชั่วคราวอยู่ (นำเข้าเมื่อ HH:MM) · backend รุ่นก่อนไม่มีแถวนี้", async ({ page }) => {
  let withRow = true
  await page.route("**/api/health", async (route) => {
    const response = await route.fetch()
    const body = await response.json()
    if (withRow) body.account = { status: "ok", active: true, importedAt: "2026-10-06T02:05:00Z" }
    else delete body.account
    await route.fulfill({ response, json: body })
  })
  await page.goto("/settings/health")
  await expect(page.getByTestId("tool-account")).toContainText(/ใช้บัญชีชั่วคราวอยู่ \(นำเข้าเมื่อ \d{2}:\d{2}\)/, {
    timeout: 15_000,
  })
  withRow = false
  await page.reload()
  await expect(page.getByTestId("tool-network")).toBeVisible({ timeout: 15_000 })
  await expect(page.getByTestId("tool-account")).toHaveCount(0)
})
```

- [ ] **Step 2: Create `web/src/pages/settings/advanced-panel.tsx`** (loading skeleton, error alert with retry, normal; there is no empty state: "ไม่ได้ใช้บัญชี" is the normal state without an account)
```tsx
import { useQuery } from "@tanstack/react-query"
import { CircleX, UserRound } from "lucide-react"

import { UseAccountButton } from "@/components/account/account-button"
import { useDeleteAccount, useNow } from "@/components/account/use-account"
import { Alert, AlertAction, AlertDescription, AlertTitle } from "@/components/ui/alert"
import { Button } from "@/components/ui/button"
import { Skeleton } from "@/components/ui/skeleton"
import { fill, th } from "@/i18n/th"
import { accountQuery, deleteTime } from "@/lib/account"
import { ApiError } from "@/lib/api"

const t = th.account

/**
 * แท็บ "ขั้นสูง" (W6 /settings/advanced · M5 รอบ C spec 1.1): คำอธิบายสั้น · สถานะบัญชีชั่วคราว · ปุ่ม "ใช้บัญชียูทูปชั่วคราว"
 * (dialog ตัวกลาง ปุ่มนำเข้าเป็น "นำเข้า") · ถือบัญชีอยู่ = ปุ่มรอง "ลบออกตอนนี้" · ไม่มี Switch ไม่มีตัวเลือกแหล่งคุกกี้
 */
export function AdvancedPanel() {
  const account = useQuery(accountQuery())
  const now = useNow(account.data?.active === true)
  const remove = useDeleteAccount()

  if (account.isPending) {
    return (
      <div className="flex max-w-xl flex-col gap-4" aria-busy="true">
        <Skeleton className="h-10 w-full" />
        <Skeleton className="h-14 w-full" />
        <Skeleton className="h-9 w-56" />
      </div>
    )
  }

  if (account.isError) {
    return (
      <Alert variant="destructive">
        <CircleX aria-hidden />
        <AlertTitle>{th.general.loadError}</AlertTitle>
        <AlertDescription>{account.error instanceof ApiError ? account.error.message : th.errors.unknown}</AlertDescription>
        <AlertAction>
          <Button variant="outline" size="sm" onClick={() => void account.refetch()}>
            {th.common.retry}
          </Button>
        </AlertAction>
      </Alert>
    )
  }

  const { active, expiresAt, importedAt } = account.data
  const held = active && expiresAt !== undefined
  return (
    <div className="flex max-w-xl flex-col gap-4">
      <p>{t.intro}</p>
      <div data-testid="account-status" className="flex flex-wrap items-center gap-x-3 gap-y-2 rounded-lg border p-3">
        <UserRound aria-hidden className="size-4 shrink-0 text-muted-foreground" />
        <p className="min-w-0 flex-1">
          {held ? fill(t.statusOn, { time: deleteTime({ expiresAt, importedAt }, now) }) : t.statusOff}
        </p>
        {held && (
          <Button variant="outline" size="sm" disabled={remove.pending} onClick={remove.remove}>
            {t.removeNow}
          </Button>
        )}
      </div>
      <div>
        <UseAccountButton origin="settings" variant="default" size="default" />
      </div>
    </div>
  )
}
```

- [ ] **Step 3: The tab and the health row**

`web/src/pages/settings.tsx`:
Replace (1):
```tsx

import { ShutdownScreen } from "./shutdown"
import { AboutPanel } from "./settings/about-panel"
import { GeneralPanel } from "./settings/general-panel"
import { HealthPanel } from "./settings/health-panel"

const TABS = ["general", "health", "about"] as const
type Tab = (typeof TABS)[number]

// แท็บที่ไม่ได้เลือก: สี muted ผ่านเกณฑ์ contrast บนพื้น bg-muted ทั้งธีมสว่างและมืด (ค่าเริ่มต้น text-foreground/60 ได้ 4.32:1
```
with:
```tsx

import { ShutdownScreen } from "./shutdown"
import { AboutPanel } from "./settings/about-panel"
import { AdvancedPanel } from "./settings/advanced-panel"
import { GeneralPanel } from "./settings/general-panel"
import { HealthPanel } from "./settings/health-panel"

const TABS = ["general", "advanced", "health", "about"] as const
type Tab = (typeof TABS)[number]

// แท็บที่ไม่ได้เลือก: สี muted ผ่านเกณฑ์ contrast บนพื้น bg-muted ทั้งธีมสว่างและมืด (ค่าเริ่มต้น text-foreground/60 ได้ 4.32:1
```

Replace (2):
```tsx
      <Tabs value={current} onValueChange={(value) => navigate(`/settings/${value}`)}>
        <TabsList>
          <TabsTrigger value="general" className={TRIGGER}>{th.settings.tabs.general}</TabsTrigger>
          <TabsTrigger value="health" className={TRIGGER}>{th.settings.tabs.health}</TabsTrigger>
          <TabsTrigger value="about" className={TRIGGER}>{th.settings.tabs.about}</TabsTrigger>
        </TabsList>
        <TabsContent value="general" className="pt-4">
          <GeneralPanel />
        </TabsContent>
        <TabsContent value="health" className="pt-4">
          <HealthPanel onShutdown={() => setClosed(true)} />
```
with:
```tsx
      <Tabs value={current} onValueChange={(value) => navigate(`/settings/${value}`)}>
        <TabsList>
          <TabsTrigger value="general" className={TRIGGER}>{th.settings.tabs.general}</TabsTrigger>
          <TabsTrigger value="advanced" className={TRIGGER}>{th.settings.tabs.advanced}</TabsTrigger>
          <TabsTrigger value="health" className={TRIGGER}>{th.settings.tabs.health}</TabsTrigger>
          <TabsTrigger value="about" className={TRIGGER}>{th.settings.tabs.about}</TabsTrigger>
        </TabsList>
        <TabsContent value="general" className="pt-4">
          <GeneralPanel />
        </TabsContent>
        <TabsContent value="advanced" className="pt-4">
          <AdvancedPanel />
        </TabsContent>
        <TabsContent value="health" className="pt-4">
          <HealthPanel onShutdown={() => setClosed(true)} />
```

`web/src/pages/settings/health-panel.tsx`:
Replace (1):
```tsx
import { Item, ItemActions, ItemContent, ItemDescription, ItemGroup, ItemMedia, ItemTitle } from "@/components/ui/item"
import { Skeleton } from "@/components/ui/skeleton"
import { Spinner } from "@/components/ui/spinner"
import { th } from "@/i18n/th"
import { ApiError, api } from "@/lib/api"
import { appShutdown } from "@/lib/events"
import type { Health, ToolState, ToolStatus } from "@/lib/types"

import { useHealth } from "./use-health"
```
with:
```tsx
import { Item, ItemActions, ItemContent, ItemDescription, ItemGroup, ItemMedia, ItemTitle } from "@/components/ui/item"
import { Skeleton } from "@/components/ui/skeleton"
import { Spinner } from "@/components/ui/spinner"
import { fill, th } from "@/i18n/th"
import { localClock } from "@/lib/account"
import { ApiError, api } from "@/lib/api"
import { appShutdown } from "@/lib/events"
import type { AccountHealth, Health, ToolState, ToolStatus } from "@/lib/types"

import { useHealth } from "./use-health"
```

Replace (2):
```tsx
    key === "output" ? tool.path : null,
  ]
  return parts.filter(Boolean).join(" · ")
}

export function HealthPanel({ onShutdown }: { onShutdown: () => void }) {
```
with:
```tsx
    key === "output" ? tool.path : null,
  ]
  return parts.filter(Boolean).join(" · ")
}

/** แถว "บัญชียูทูป" (M5 รอบ C spec 1.4): สถานะอย่างเดียว พร้อมเสมอ ไม่ต่อเน็ต */
function AccountRow({ account }: { account: AccountHealth }) {
  const text =
    account.active && account.importedAt !== null
      ? fill(th.account.healthOn, { time: localClock(account.importedAt) })
      : th.account.statusOff
  return (
    <Item variant="outline" data-testid="tool-account">
      <ItemMedia>
        <CircleCheck aria-hidden className={TONE.ok} />
      </ItemMedia>
      <ItemContent>
        <ItemTitle>{th.health.rows.account}</ItemTitle>
        <ItemDescription>{text}</ItemDescription>
      </ItemContent>
      <ItemActions>
        <Badge variant="outline">{th.health.status.ok}</Badge>
      </ItemActions>
    </Item>
  )
}

export function HealthPanel({ onShutdown }: { onShutdown: () => void }) {
```

Replace (3):
```tsx
            </Item>
          )
        })}
      </ItemGroup>
      <div className="flex flex-wrap justify-end gap-2">
        <Button variant="outline" onClick={() => void health.refetch()} disabled={health.isFetching}>
```
with:
```tsx
            </Item>
          )
        })}
        {health.data.account && <AccountRow account={health.data.account} />}
      </ItemGroup>
      <div className="flex flex-wrap justify-end gap-2">
        <Button variant="outline" onClick={() => void health.refetch()} disabled={health.isFetching}>
```

- [ ] **Step 4: Run the web checks, expect PASS** — `cd "$WORKTREE/web" && npm run typecheck && npm run lint && npm test`.

- [ ] **Step 5: Commit**
```bash
cd "$WORKTREE" && git add web/src/pages/settings.tsx web/src/pages/settings/advanced-panel.tsx web/src/pages/settings/health-panel.tsx web/e2e/settings-advanced.spec.ts web/e2e/health.spec.ts && git commit -F- <<'EOF'
feat(web): M5-C Settings advanced tab and the health account row

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
EOF
```

### Task 12: Queue e2e with the real fake backend and a shortened grace

**Files:**
- Create: `web/e2e/queue-account.spec.ts`
- Modify: `web/playwright.config.ts` (backend env `YT_TOOLKIT_ACCOUNT_GRACE_S: "5"`)

**Interfaces:**
- Consumes: the running fake backend with T9 (`account_grace_s`, `/api/cookies*`), T4 fake clips (`ACCOUNTAGE1`, `PRIVATEVID1`), T10 (row button), T8 (dialog, banner, toast); `queue-helpers.ts` (`enqueue`, `waitForJob`, `openQueueSheet`, `cancelJobsFor`, `token`).
- Produces: the spec §6 queue scenario (fail → import from the row → automatic retry → done; tried copy for an account without access; grace elapses → removed toast). It runs only at the final gate (`--project=queue --workers=1`).

- [ ] **Step 1: Shorten the grace for the e2e backends** — `web/playwright.config.ts` (the backend reads it only in fake mode; both projects get it, only this spec waits for it):
Replace (1):
```ts
    reuseExistingServer: false,
    timeout: 60_000,
    // FAKE=1: ข้อมูลคลิปมาจาก tests/fixtures ไม่ต่อยูทูปจริง (health ไม่ใช้ตัวดึงข้อมูล จึงไม่กระทบ)
    env: { YT_TOOLKIT_DATA_ROOT: root, YT_TOOLKIT_FFMPEG_PATH_LOOKUP: "0", YT_TOOLKIT_FAKE: "1" },
  }
}
```
with:
```ts
    reuseExistingServer: false,
    timeout: 60_000,
    // FAKE=1: ข้อมูลคลิปมาจาก tests/fixtures ไม่ต่อยูทูปจริง (health ไม่ใช้ตัวดึงข้อมูล จึงไม่กระทบ)
    // ACCOUNT_GRACE_S (M5 รอบ C): ย่น grace 10 นาทีของบัญชีชั่วคราวเหลือ 5 วินาที (backend อ่านเฉพาะโหมดข้อมูลปลอม)
    env: {
      YT_TOOLKIT_DATA_ROOT: root,
      YT_TOOLKIT_FFMPEG_PATH_LOOKUP: "0",
      YT_TOOLKIT_FAKE: "1",
      YT_TOOLKIT_ACCOUNT_GRACE_S: "5",
    },
  }
}
```

- [ ] **Step 2: Create `web/e2e/queue-account.spec.ts`** (the imported file has fake values; it always deletes the account and cancels its jobs in `finally`, so later queue specs start clean):
```ts
/// <reference lib="dom" />
import { expect, test, type APIRequestContext, type Page } from "@playwright/test"

import { cancelJobsFor, enqueue, openQueueSheet, token, waitForJob } from "./queue-helpers"

/**
 * M5 รอบ C บัญชียูทูปชั่วคราวกับ backend โหมดปลอมจริง (project queue รันทีละ spec --workers=1):
 * ACCOUNTAGE1 = คลิปปลอมที่ probe แบบไม่ใช้บัญชีได้ E_AGE_RESTRICTED (FakeExtractor "needsAccount")
 * PRIVATEVID1 = ส่วนตัวเสมอแม้ใช้บัญชี (บัญชีไม่มีสิทธิ์ดู)
 * ไฟล์ที่นำเข้าเป็นค่าปลอม (ตัวอ่าน cookies.txt ตัวจริงของ backend อ่าน ไม่มีคำขอไปยูทูป)
 * playwright.config ตั้ง YT_TOOLKIT_ACCOUNT_GRACE_S=5: คิวว่างหลังงานที่ใช้บัญชีจบ 5 วินาทีแล้วบัญชีถูกลบเอง (ของจริง 10 นาที)
 */

const AGE = "ACCOUNTAGE1"
const PRIVATE = "PRIVATEVID1"
const USE = "ใช้บัญชียูทูปชั่วคราว"
const AGE_MESSAGE = "คลิปนี้จำกัดอายุ ต้องเข้าสู่ระบบยูทูปถึงจะเปิดได้"
const TRIED_MESSAGE =
  "ลองด้วยบัญชีแล้วยังเปิดไม่ได้ บัญชีนี้อาจไม่มีสิทธิ์ดูคลิปนี้ หรือการเข้าสู่ระบบหมดอายุแล้ว ลองนำเข้าใหม่"
const REMOVED = "ลบบัญชีออกจากแอพแล้ว · กลับไปกดออกจากระบบในหน้าต่างไม่ระบุตัวตน แล้วปิดหน้าต่าง"
const COOKIES =
  "# Netscape HTTP Cookie File\n" +
  ".youtube.com\tTRUE\t/\tTRUE\t2000000000\tSAPISID\te2e-fake-sapisid\n" +
  ".youtube.com\tTRUE\t/\tTRUE\t2000000000\tLOGIN_INFO\te2e-fake-login\n"
const VIDEO = { maxQuality: false, splitChapters: false, noAudio: false, audioLanguage: "original" }

const banner = (page: Page) => page.getByTestId("account-banner")
const toast = (page: Page, text: string) => page.locator("[data-sonner-toast]").filter({ hasText: text })

async function accountStatus(request: APIRequestContext): Promise<{ active: boolean }> {
  return (await (await request.get("/api/cookies")).json()) as { active: boolean }
}

/** ลบบัญชีที่ค้าง (spec ถัดไปของ project queue ต้องเริ่มแบบไม่มีบัญชี) */
async function dropAccount(page: Page): Promise<void> {
  const origin = new URL(page.url()).origin
  await page.request.delete("/api/cookies", { headers: { "X-Toolkit-Token": await token(page), Origin: origin } })
}

test("งานคลิปจำกัดอายุพลาด → ปุ่มในแถวคิว → นำเข้า → ลองงานเดิมใหม่เอง → เสร็จ · บัญชีไม่มีสิทธิ์ = ข้อความ ลองด้วยบัญชีแล้ว… · คิวว่างแล้วลบเอง", async ({
  page,
  request,
}) => {
  test.setTimeout(60_000)
  await page.goto("/")
  try {
    expect((await accountStatus(request)).active).toBe(false)
    const [job] = await enqueue(request, [{ videoId: AGE, kind: "video", params: VIDEO, title: "คลิปจำกัดอายุ" }])
    const failed = await waitForJob(request, (j) => j.id === job.id && j.status === "failed")
    expect(failed.error).toMatchObject({ code: "E_AGE_RESTRICTED", message: AGE_MESSAGE })

    const sheet = await openQueueSheet(page)
    const row = sheet.locator(`[data-job-id="${job.id}"]`)
    await expect(row).toContainText(AGE_MESSAGE)
    await row.getByRole("button", { name: USE }).click()
    const dialog = page.getByRole("dialog", { name: USE })
    await dialog.getByLabel("cookies.txt").setInputFiles({ name: "cookies.txt", mimeType: "text/plain", buffer: Buffer.from(COOKIES) })
    await dialog.getByRole("button", { name: "นำเข้าแล้วลองใหม่" }).click()
    await expect(dialog).toHaveCount(0)
    await expect(banner(page)).toContainText("กำลังใช้บัญชียูทูปชั่วคราว")
    const done = await waitForJob(request, (j) => j.id === job.id && j.status === "done")
    expect(done.outputs?.length).toBe(1)

    // บัญชียังอยู่ (grace เพิ่งเริ่ม) งานใหม่ของคลิปที่บัญชีไม่มีสิทธิ์: ลองด้วยบัญชีแล้วยังพลาด ข้อความเปลี่ยน ไม่มีปุ่ม
    const [denied] = await enqueue(request, [{ videoId: PRIVATE, kind: "video", params: VIDEO }])
    const deniedJob = await waitForJob(request, (j) => j.id === denied.id && j.status === "failed")
    expect(deniedJob.error).toMatchObject({ code: "E_VIDEO_PRIVATE", message: TRIED_MESSAGE })
    const deniedRow = sheet.locator(`[data-job-id="${denied.id}"]`)
    await expect(deniedRow).toContainText(TRIED_MESSAGE)
    await expect(deniedRow.getByRole("button", { name: USE })).toHaveCount(0)

    // คิวว่างครบ grace (5 วินาทีในโหมดทดสอบ): ลบเอง แถบหาย toast บอกให้ไปออกจากระบบ (ค้างไว้ ไม่หายเอง)
    await expect(toast(page, REMOVED)).toBeVisible({ timeout: 15_000 })
    await expect(banner(page)).toHaveCount(0)
    expect((await accountStatus(request)).active).toBe(false)
  } finally {
    await cancelJobsFor(request, [AGE, PRIVATE])
    await dropAccount(page)
  }
})
```

- [ ] **Step 3: Typecheck and lint** — `cd "$WORKTREE/web" && npm run typecheck && npm run lint` (the controller runs it at the final gate: `npx playwright test --project=queue --workers=1 e2e/queue-account.spec.ts`).

- [ ] **Step 4: Commit**
```bash
cd "$WORKTREE" && git add web/e2e/queue-account.spec.ts web/playwright.config.ts && git commit -F- <<'EOF'
test(e2e): M5-C queue flow with a temporary account and a shortened grace

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
EOF
```

### Task 13: Docs (PRD, BRD, acceptance, m4-followups, research note, fixture README) and the owner-gated network test

**Files:**
- Modify: `PRD.md` (everything about cookies outside §7, which T1 did), `BRD.md`, `docs/acceptance.md`, `docs/m4-followups.md`, `docs/m5c-prep.md`, `tests/fixtures/README.md` (account section), `tests/network_videos.toml`
- Create: `tests/network/test_account_network.py` (written, **not run**)

**Interfaces:**
- Consumes: every final name, string, code and behaviour above (spec §5).
- Produces: docs matching the code; a network test Pete can approve and run with his own backup-account export.

Every `old` text below occurs exactly once in its file (LF kept; use the Edit tool). Docs are Pete-style Thai prose, not UI copy; UI strings quoted in them are the spec §7 strings.

- [ ] **Step 1: PRD.md**
**US-13 (section 2):** replace
```markdown
| US-13 | โหลดคลิปจำกัดอายุหรือคลิปที่บัญชีของฉันดูได้ | ใช้คลิปที่ต้องล็อกอินยูทูปถึงจะดูได้ | FR-CK |
```
with
```markdown
| US-13 | โหลดคลิปจำกัดอายุ คลิปส่วนตัว หรือคลิปเฉพาะสมาชิก ด้วยบัญชียูทูปสำรองแบบชั่วคราว | ใช้คลิปที่ต้องเข้าสู่ระบบยูทูปถึงจะดูได้ โดยแอพไม่เก็บการเข้าสู่ระบบไว้หลังใช้เสร็จ | FR-CK (M5 รอบ C) |
```

**W2 advanced-options row: drop the per-clip checkbox:** replace
```markdown
 · (M5 รอบ C) Checkbox "ใช้คุกกี้กับคลิปนี้" (แสดงเฉพาะเมื่อเปิดคุกกี้ไว้ FR-CK-7) |
```
with
```markdown
 · (M5 รอบ C) ไม่มี checkbox ต่อคลิป: บัญชียูทูปชั่วคราวถูกใช้เองเมื่อคลิปต้องเข้าสู่ระบบ (BRD #152) |
```

**new W2 block right before the W3 heading:** replace
```markdown
### W3 เลือกคลิป (เพลย์ลิสต์ / หลายลิงก์)
```
with
```markdown
**บัญชียูทูปชั่วคราว (M5 รอบ C · พิธอนุมัติ 2026-10-06 · BRD #144-#152 · สเปก `docs/superpowers/specs/2026-10-06-m5c-temporary-youtube-account-design.md`):**
- **ปุ่มบน error:** เปิดข้อมูลคลิปไม่ได้ด้วย `E_AGE_RESTRICTED` หรือ `E_VIDEO_PRIVATE` (รวมคลิปเฉพาะสมาชิก) และแอพยังไม่ได้ถือบัญชี = กล่อง error ของ W2 มีข้อความตามข้อ 7 และปุ่มหลัก "ใช้บัญชียูทูปชั่วคราว" (ไม่มีปุ่ม "ลองใหม่") · ถือบัญชีอยู่แล้วแต่ยังเปิดไม่ได้ = ข้อความ "ลองด้วยบัญชีแล้ว…" (หมายเหตุใต้ตารางข้อ 7) ไม่มีปุ่ม · ปุ่มเดียวกันอยู่ในแถวงานที่พลาดของคิว (W4) ใน toast ของงานที่พลาด (เป็นปุ่มหลัก "ดูรายละเอียด" เป็นปุ่มรอง) และใน toast ของ "ถ่ายภาพคมตรงนี้"
- **dialog "ใช้บัญชียูทูปชั่วคราว" (W7):** คำเตือนสีอันตราย · วิธีให้เจ้าของช่องแชร์คลิปส่วนตัว · ขั้นตอนส่งออก 6 ข้อจากหน้าต่างไม่ระบุตัวตน (ไม่บอกชื่อส่วนขยาย) · ช่องเลือกไฟล์ `.txt` ไม่เกิน 1 MB (อ่านในเบราว์เซอร์แล้วส่งเป็นข้อความ) · ปุ่ม "ยกเลิก" และ "นำเข้าแล้วลองใหม่" (เปิดจาก error) หรือ "นำเข้า" (เปิดจากหน้าตั้งค่า) กดได้เมื่อเลือกไฟล์แล้ว · ยกเลิกหรือ Esc = ไม่ส่งอะไร · ไฟล์ใช้ไม่ได้ = ข้อความ `E_COOKIES_INVALID` ใต้ช่อง dialog ยังเปิด · สำเร็จ = dialog ปิด แถบบนหน้าขึ้น แล้วลองสิ่งที่เพิ่งพลาดใหม่เอง (โหลดข้อมูลคลิปใหม่ / ลองงานเดิมใหม่ด้วยค่าเดิม / ถ่ายภาพเวลาเดิมใหม่)
- **แถบบนหน้า:** แถบบางใต้เมนูบนทุกหน้า "กำลังใช้บัญชียูทูปชั่วคราว · ลบอัตโนมัติภายใน HH:MM" และปุ่มแบบลิงก์ "ลบออกตอนนี้" (ไม่ต้องยืนยัน) · ลบด้วยเหตุผลใดก็ตาม = แถบหายในทุกแท็บ และ toast ที่ไม่หายเอง "ลบบัญชีออกจากแอพแล้ว · กลับไปกดออกจากระบบในหน้าต่างไม่ระบุตัวตน แล้วปิดหน้าต่าง" (ปุ่ม "ปิด")
- **UI ไม่มีคำว่า "คุกกี้"** (BRD #148) มีแค่ชื่อไฟล์ `cookies.txt` · คลิปที่เปิดได้ด้วยบัญชีเท่านั้นไม่ขึ้นใน "ล่าสุด" และประวัติ (ข้อมูลคลิปอยู่ในหน่วยความจำจนบัญชีถูกลบ) · แท็บของ W2 ที่โหลดของเอง (ไฟล์ซับ ภาพเฟรม คอมเมนต์ปักหมุด) ไม่ใช้บัญชี · ตัวเล่นฝัง (`youtube-nocookie.com`) ยังเล่นคลิปจำกัดอายุไม่ได้ ใช้ "เปิดในยูทูป" เหมือนเดิม

### W3 เลือกคลิป (เพลย์ลิสต์ / หลายลิงก์)
```

**W6 ทั่วไป: no cookie exception any more:** replace
```markdown
ค่าทั้งหมดในข้อ 6.4 ยกเว้นคุกกี้ ·
```
with
```markdown
ค่าทั้งหมดในข้อ 6.4 ·
```

**W6 ขั้นสูง:** replace
```markdown
- **ขั้นสูง** (M5): คุกกี้ยูทูป (FR-CK) · Switch "ใช้คุกกี้ยูทูป" (ปิดไว้เป็นค่าเริ่มต้น) · เปิดครั้งแรก → Alert Dialog คำเตือน (W7) · เลือกแหล่ง: Toggle Group "ไฟล์ cookies.txt" / "Firefox" · ปุ่ม "นำเข้า cookies.txt" · ข้อความเล็ก "Chrome บน Windows อ่านคุกกี้ไม่ได้ตั้งแต่ Chrome 127 ใช้ Firefox หรือส่งออก cookies.txt แทน" · สถานะปัจจุบัน (นำเข้าเมื่อ <วันที่>) · ปุ่มรอง "ลบคุกกี้"
```
with
```markdown
- **ขั้นสูง** (M5 รอบ C, `/settings/advanced`): บัญชียูทูปชั่วคราว (FR-CK) · คำอธิบายสั้น "ใช้เมื่อต้องโหลดคลิปจำกัดอายุ คลิปส่วนตัว หรือคลิปเฉพาะสมาชิก แอพเก็บการเข้าสู่ระบบไว้ชั่วคราวและลบเองเมื่อโหลดเสร็จ" · สถานะ "ไม่ได้ใช้บัญชี" / "ใช้บัญชีชั่วคราวอยู่ ลบอัตโนมัติภายใน HH:MM" · ปุ่ม "ใช้บัญชียูทูปชั่วคราว" (เปิด dialog ของ W7 ปุ่มนำเข้าเป็น "นำเข้า") · ปุ่มรอง "ลบออกตอนนี้" เมื่อถือบัญชีอยู่ · ไม่มี Switch ไม่มีตัวเลือกแหล่ง (Firefox) และไม่มีข้อความเรื่อง Chrome 127 (BRD #147)
```

**W6 ตรวจสุขภาพระบบ: the account row:** replace
```markdown
พื้นที่ดิสก์, คุกกี้ (M5, FR-CK-8) ·
```
with
```markdown
พื้นที่ดิสก์, บัญชียูทูป (M5 รอบ C, FR-CK-8: สถานะอย่างเดียว "ไม่ได้ใช้บัญชี" / "ใช้บัญชีชั่วคราวอยู่ (นำเข้าเมื่อ HH:MM)" เป็น "พร้อม" เสมอ ไม่ต่อเน็ต) ·
```

**W7 failed-job toast row:** replace
```markdown
| งานผิดพลาด | Toast (ไม่หายเอง) + รายละเอียดในแถวคิว | ข้อความจากข้อ 7 | รายละเอียด |
```
with
```markdown
| งานผิดพลาด | Toast (ไม่หายเอง) + รายละเอียดในแถวคิว | ข้อความจากข้อ 7 | รายละเอียด · (M5 รอบ C) `E_AGE_RESTRICTED` / `E_VIDEO_PRIVATE` และยังไม่ได้ใช้บัญชี = ใช้บัญชียูทูปชั่วคราว (ปุ่มหลัก) + ดูรายละเอียด |
```

**W7 cookie dialog row becomes the account dialog + removed toast:** replace
```markdown
| เปิดคุกกี้ครั้งแรก (M5) | Alert Dialog | "ใช้คุกกี้ยูทูป? บัญชี Google ที่ใช้อาจถูกจำกัดหรือถูกล็อก และกระทบ Gmail กับ Drive ของบัญชีนั้นได้ ใช้บัญชีสำรองที่ไม่ใช่บัญชีงานหลัก และอย่าส่งไฟล์คุกกี้ให้ใคร" | ยกเลิก / เปิดใช้คุกกี้ |
```
with
```markdown
| ใช้บัญชียูทูปชั่วคราว (M5 รอบ C) | Dialog (เลื่อนในกล่องได้) | คำเตือน "บัญชี Google ที่ใช้อาจถูกจำกัดหรือถูกล็อก และกระทบ Gmail กับ Drive ของบัญชีนั้นได้ ใช้บัญชีสำรองเท่านั้น ห้ามใช้บัญชีเจ้าของช่องหรือบัญชีงานหลัก และอย่าส่งไฟล์ให้ใคร" · คลิปส่วนตัว · ขั้นตอนส่งออก `cookies.txt` 6 ข้อ · ช่องเลือกไฟล์ (ดู W2 "บัญชียูทูปชั่วคราว") | ยกเลิก / นำเข้าแล้วลองใหม่ (จาก error) หรือ นำเข้า (จากหน้าตั้งค่า) |
| ลบบัญชียูทูปชั่วคราวแล้ว (M5 รอบ C: ครบ 2 ชม. คิวว่าง 10 นาทีหลังงานที่ใช้บัญชี ปิดโปรแกรม หรือกด "ลบออกตอนนี้") | Toast (ไม่หายเอง ทุกแท็บ) | "ลบบัญชีออกจากแอพแล้ว · กลับไปกดออกจากระบบในหน้าต่างไม่ระบุตัวตน แล้วปิดหน้าต่าง" | ปิด |
```

**AC-SET-07: no cookie file on disk any more:** replace
```markdown
ไฟล์ผลลัพธ์ ประวัติ ค่าตั้ง และ `data/cookies.txt` ยังอยู่ครบ
```
with
```markdown
ไฟล์ผลลัพธ์ ประวัติ และค่าตั้งยังอยู่ครบ
```

**AC-SET-09: no `cookies` key any more:** replace
```markdown
ไฟล์ที่ส่งออกไม่มี key `cookies` และ `statsResetAt`
```
with
```markdown
ไฟล์ที่ส่งออกไม่มี key `statsResetAt` (M5 รอบ C ไม่มี key `cookies` แล้ว)
```

**section 5.10 rewritten (heading to the AC-SET-06 note):** replace
```markdown
### 5.10 คุกกี้ยูทูป (ทางเลือก)
| AC | เงื่อนไข → ผลที่ต้องได้ | เทส |
|---|---|---|
| AC-CK-01 | ติดตั้งใหม่ → `cookies.enabled` = false และทุกการเรียก yt-dlp ไม่มี `cookiesfrombrowser` และไม่มี `cookiefile` ที่ชี้ไปคุกกี้ของผู้ใช้ (`data/cookies.txt`) · ยกเว้นเซสชันผู้ชมแบบไม่ระบุตัวตนที่แอพสร้างเอง (`data/visitor-session.txt`, ข้อ 6.6, owner round 3) ซึ่ง probe และการโหลดซับใช้ตั้งแต่ M3 | U, A |
| AC-CK-02 | เปิด Switch คุกกี้ครั้งแรก → Alert Dialog ตาม W7 · กดยกเลิก → ยังปิดอยู่และไม่มีไฟล์ใน `data/` · ต้องกด "เปิดใช้คุกกี้" จึงเปิดได้ | E |
| AC-CK-03 | นำเข้า `cookies.txt` ที่มีคุกกี้ของ `youtube.com`, `google.com` และ `example.com` → เก็บที่ `data/cookies.txt` เท่านั้น เหลือแค่ 2 โดเมนแรก · ไม่มีสำเนาใน `work/`, `run/` หรือโฟลเดอร์ผลลัพธ์ · `GET /settings` ไม่มีค่าคุกกี้ | A |
| AC-CK-04 | ไฟล์ที่ไม่ใช่รูปแบบ Netscape หรือไม่มีคุกกี้ของยูทูป → 422 `E_COOKIES_INVALID` และสถานะเดิมไม่เปลี่ยน | A |
| AC-CK-05 | กด "ลบคุกกี้" → `data/cookies.txt` หายไป, `cookies.enabled` = false และงานถัดไปไม่มีตัวเลือกคุกกี้ | A |
| AC-CK-06 | เปิดคุกกี้ไว้: คลิปสาธารณะ → เรียกครั้งแรกโดยไม่ใช้คุกกี้ · ได้ `E_AGE_RESTRICTED` หรือ `E_VIDEO_PRIVATE` → ลองใหม่ด้วยคุกกี้ 1 ครั้ง (ทั้ง probe และงานโหลด) · ได้ `E_BOT_CHECK`, `E_NETWORK` หรือรหัสอื่น → ไม่ใช้คุกกี้ · ติ๊ก "ใช้คุกกี้กับคลิปนี้" → ใช้คุกกี้ตั้งแต่ครั้งแรก | U |
| AC-CK-07 | แถว "คุกกี้" ใน `/health`: ปิด → `ok` "ปิดอยู่" · เปิดด้วยไฟล์ → `ok` พร้อมวันที่นำเข้า · เปิดด้วย Firefox แต่หาโปรไฟล์ Firefox ไม่เจอ → `error` พร้อมวิธีแก้ | A |
| AC-CK-08 | แท็บขั้นสูงไม่มีตัวเลือก Chrome และมีข้อความเรื่อง Chrome 127 ตาม W6 | E |
| AC-CK-09 | คลิปจำกัดอายุในชุด network test + คุกกี้ของบัญชีสำรอง → โหลดได้ · ไม่มีคุกกี้ → `E_AGE_RESTRICTED` พร้อมข้อความตามข้อ 7 | N |

AC ที่ว่าค่าคุกกี้ต้องไม่อยู่ใน log และรายงานแจ้งปัญหาคือ AC-SET-06 (ข้อ 7.1)
```
with
```markdown
### 5.10 บัญชียูทูปชั่วคราว (M5 รอบ C)
| AC | เงื่อนไข → ผลที่ต้องได้ | เทส |
|---|---|---|
| AC-CK-01 | ติดตั้งใหม่หรือเปิดโปรแกรมใหม่ → ไม่ได้ใช้บัญชี (`GET /cookies` = `{active:false, used:false}`) และทุกการเรียก yt-dlp ไม่มี `cookiesfrombrowser` และไม่มี `cookiefile` ของผู้ใช้ · ยกเว้นเซสชันผู้ชมแบบไม่ระบุตัวตนที่แอพสร้างเอง (`data/visitor-session.txt`, ข้อ 6.6) | U, A |
| AC-CK-02 | error `E_AGE_RESTRICTED` / `E_VIDEO_PRIVATE` ของหน้า W2 แถวงานที่พลาด toast ของงาน และ toast ของถ่ายภาพคม (ยังไม่ได้ใช้บัญชี) → มีปุ่ม "ใช้บัญชียูทูปชั่วคราว" · กดแล้วเปิด dialog ของ W7 · "ยกเลิก" หรือ Esc → ไม่มีคำขอนำเข้า ไม่มีแถบบนหน้า | E |
| AC-CK-03 | นำเข้า `cookies.txt` ที่มีคุกกี้ของ `youtube.com`, `google.com` และ `example.com` → ถือไว้ในหน่วยความจำเท่านั้น เหลือแค่ 2 โดเมนแรก · ไม่มีไฟล์ใดใน `data/`, `work/`, `run/`, โฟลเดอร์ผลลัพธ์ หรือ temp ที่มีค่าคุกกี้ · คำตอบมีแค่ `{active, importedAt, expiresAt, used}` | U, A |
| AC-CK-04 | ไฟล์ที่ไม่ใช่รูปแบบ Netscape หรือไม่มีคุกกี้เข้าสู่ระบบของ `.youtube.com` (`SAPISID` / `__Secure-3PSID` / `LOGIN_INFO`) → 422 `E_COOKIES_INVALID` (เกิน 1 MB → 413) · `detail` ไม่ยกเนื้อไฟล์ · บัญชีที่ถืออยู่เดิมไม่เปลี่ยน · หน้าเว็บแสดงข้อความใต้ช่องเลือกไฟล์ dialog ยังเปิด | U, A, E |
| AC-CK-05 | ลบบัญชี (กด "ลบออกตอนนี้" ครบ 2 ชม. หลังนำเข้า ปิดโปรแกรม หรือคิวว่างครบ 10 นาทีหลังงานในคิวที่ใช้บัญชีจบ) → คำขอถัดไปไม่ใช้บัญชี · ข่าว SSE `account` ไปทุกแท็บ แถบหาย toast ให้ไปออกจากระบบ · ดูข้อมูลคลิปหรือถ่ายภาพคมด้วยบัญชีไม่เริ่มนับ 10 นาที · งานใหม่เข้าคิวระหว่างนับ = ยกเลิกการนับ | U, A, E |
| AC-CK-06 | ถือบัญชีอยู่: ทุกคำขอลองแบบไม่ใช้บัญชีก่อน · ได้ `E_AGE_RESTRICTED` หรือ `E_VIDEO_PRIVATE` → ลองใหม่ด้วยบัญชี 1 ครั้งทั้งก้อน (ข้อมูลคลิปของ W2, งานในคิวทั้งงาน, ถ่ายภาพคม) · ได้ `E_BOT_CHECK`, `E_NETWORK` หรือรหัสอื่น → ไม่ใช้บัญชี · ใช้บัญชีแล้วยังได้รหัสเดิม → ข้อความ "ลองด้วยบัญชีแล้ว…" และบัญชียังอยู่ | U, A |
| AC-CK-07 | แถว "บัญชียูทูป" ใน `/health` → `ok` เสมอ "ไม่ได้ใช้บัญชี" หรือ "ใช้บัญชีชั่วคราวอยู่ (นำเข้าเมื่อ HH:MM)" ไม่ต่อเน็ต ไม่มีชื่อหรือค่าคุกกี้ | A, E |
| AC-CK-08 | แท็บขั้นสูง: คำอธิบาย สถานะ ปุ่ม "ใช้บัญชียูทูปชั่วคราว" และ "ลบออกตอนนี้" ตาม W6 · ไม่มี Switch ไม่มีตัวเลือก Firefox · UI ไม่มีคำว่า "คุกกี้" (มีแค่ชื่อไฟล์ `cookies.txt`) · axe ผ่านทั้งสองธีม และกว้าง 640 px ไม่ล้น | E |
| AC-CK-09 | คลิปจำกัดอายุในชุด network test + `cookies.txt` ของบัญชีสำรอง (env `YT_TOOLKIT_TEST_COOKIES`) → ไม่ใช้บัญชีได้ `E_AGE_RESTRICTED` · ใช้บัญชีดึงข้อมูลได้และโหลดไฟล์เสียงเล็กได้ | N |

AC ที่ว่าชื่อและค่าคุกกี้ต้องไม่อยู่ใน log, ข่าว SSE, คำตอบของ API และรายงานแจ้งปัญหาคือ AC-SET-06 (ข้อ 7.1)
```

**API `/health` row:** replace
```markdown
| GET | `/health` | — | `{version, commit, tools:{ffmpeg, ytdlp, jsRuntime}, disk, output, network, cookies, mode?}` (`cookies` มาใน M5 บอกแค่สถานะและแหล่ง ไม่มีค่าคุกกี้ · `mode: "fake"` มีเฉพาะโหมดข้อมูลปลอม) ทุกตัวเป็น `ToolStatus = {status: ok\|warn\|error, name, version, message, path}` (ใช้เวลาได้ถึง 5 วิเพราะเช็คเน็ต) |
```
with
```markdown
| GET | `/health` | — | `{version, commit, tools:{ffmpeg, ytdlp, jsRuntime}, disk, output, network, account?, mode?}` (`account` มาใน M5 รอบ C = `{status:"ok", active, importedAt}` บอกแค่สถานะ ไม่ต่อเน็ต ไม่มีชื่อหรือค่าคุกกี้ · `mode: "fake"` มีเฉพาะโหมดข้อมูลปลอม) ทุกตัวยกเว้น `account` เป็น `ToolStatus = {status: ok\|warn\|error, name, version, message, path}` (ใช้เวลาได้ถึง 5 วิเพราะเช็คเน็ต) |
```

**API `PATCH /settings`:** replace
```markdown
หรือแตะ `cookies` / `statsResetAt` → 422 `E_BAD_REQUEST`
```
with
```markdown
หรือแตะ `statsResetAt` (หรือส่ง `cookies` ที่เลิกใช้แล้วใน M5 รอบ C) → 422 `E_BAD_REQUEST`
```

**API `GET /settings/export`:** replace
```markdown
· `settings` ไม่มี `cookies` และ `statsResetAt` |
```
with
```markdown
· `settings` ไม่มี `statsResetAt` |
```

**API `/cookies*` rows (the two old rows become three):** replace
```markdown
| POST | `/cookies/import` | `{text}` เนื้อไฟล์ `cookies.txt` (ไม่เกิน 1 MB) | (M5) `{enabled:true, source:"file", importedAt, kept}` (`kept` = จำนวนคุกกี้ที่เก็บหลังกรองโดเมน) · ต้องยอมรับคำเตือนแล้ว ไม่งั้น 409 · ไฟล์ใช้ไม่ได้ → 422 `E_COOKIES_INVALID` |
| DELETE | `/cookies` | — | (M5) `{ok:true}` ลบ `data/cookies.txt` และตั้ง `cookies.enabled=false` (FR-CK-6) |
```
with
```markdown
| GET | `/cookies` | — | (M5 รอบ C) `{active:false, used:false}` หรือ `{active:true, importedAt, expiresAt, used}` (`expiresAt` = เวลาที่จะลบเองเร็วที่สุด: ครบ 2 ชม. หรือคิวว่างครบ 10 นาที · `used` = มีคำขอที่ใช้บัญชีแล้ว) · ไม่มีชื่อหรือค่าคุกกี้ |
| POST | `/cookies/import` | `{text, acceptWarning: true}` เนื้อไฟล์ `cookies.txt` (ไม่เกิน 1 MB) | (M5 รอบ C) แบบเดียวกับ `GET /cookies` · ถือไว้ในหน่วยความจำเท่านั้น แทนบัญชีเดิมและเริ่มนับเวลาใหม่ · ไม่มี `acceptWarning: true` → 409 `E_BAD_REQUEST` · body รูปร่างผิด → 422 `E_BAD_REQUEST` · เกิน 1 MB → 413 `E_COOKIES_INVALID` · ไฟล์ใช้ไม่ได้ → 422 `E_COOKIES_INVALID` (บัญชีเดิมไม่เปลี่ยน) · ไม่ log body |
| DELETE | `/cookies` | — | (M5 รอบ C) ลบบัญชีที่ถืออยู่ทันที (ไม่มีก็ได้) คืนแบบเดียวกับ `GET /cookies` · ส่งข่าว `account` (`reason: "manual"`) · งานที่กำลังโหลดด้วยบัญชีนี้ใช้ต่อจนจบ |
```

**status list: 413 note:** replace
```markdown
`E_INVALID_INPUT`, `E_SETTINGS_INVALID`, `E_COOKIES_INVALID`, `E_CAPTURE_UNSUPPORTED` 422
```
with
```markdown
`E_INVALID_INPUT`, `E_SETTINGS_INVALID`, `E_COOKIES_INVALID` (เกิน 1 MB = 413), `E_CAPTURE_UNSUPPORTED` 422
```

**status list: drop `E_COOKIES_UNAVAILABLE`:** replace
```markdown
`E_GEO_BLOCKED`, `E_COOKIES_UNAVAILABLE`, `E_JOB_STATE`
```
with
```markdown
`E_GEO_BLOCKED`, `E_JOB_STATE`
```

**SSE table: the `account` event:** replace
```markdown
| `app.shutdown` | `{}` | กำลังปิดโปรแกรม (หน้าเว็บแสดง "ปิดโปรแกรมแล้ว") |
```
with
```markdown
| `app.shutdown` | `{}` | กำลังปิดโปรแกรม (หน้าเว็บแสดง "ปิดโปรแกรมแล้ว") |
| `account` | `{active, expiresAt?, reason?}` | (M5 รอบ C) บัญชียูทูปชั่วคราว: นำเข้า (`active:true, expiresAt`) · เริ่มหรือยกเลิกการนับ 10 นาทีของคิว (`expiresAt` ใหม่) · ลบ (`active:false, reason: manual \| queue_done \| expired \| shutdown`) · ไม่มีชื่อหรือค่าคุกกี้ |
```

**6.3 job params: `useCookies` bullet:** replace
```markdown
- ทุก kind ที่ต้องต่อยูทูป (`video`, `audio`, `subtitle`, `frames_sharp`) รับ `useCookies?: bool` เพิ่ม (M5) = ผู้ใช้ติ๊ก "ใช้คุกกี้กับคลิปนี้" (FR-CK-7) · ไม่ส่งมา = ลองแบบไม่ใช้คุกกี้ก่อน
```
with
```markdown
- (M5 รอบ C) งานไม่มีตัวเลือกบัญชีต่อคลิป (`useCookies` ถูกปฏิเสธด้วย 422 ตามกฎตรวจ params ด้านล่าง) · ทุก kind ที่ต้องต่อยูทูป (`video`, `audio`, `subtitle`, `frames_sharp`) ทำทั้งงานแบบไม่ใช้บัญชีก่อน ได้ `E_AGE_RESTRICTED` / `E_VIDEO_PRIVATE` และแอพถือบัญชีชั่วคราวอยู่ = ทำทั้งงานใหม่ด้วยบัญชี 1 ครั้ง (ดึงข้อมูล + โหลด ใช้บัญชีเดียวกัน) · ถ่ายภาพคมตรงจุดใช้กฎเดียวกัน
```

**6.3 strict params:** replace
```markdown
`useCookies` (M5 รอบ C) ยังถูกปฏิเสธ
```
with
```markdown
`useCookies` ยังถูกปฏิเสธ (M5 รอบ C ไม่มี checkbox ต่อคลิป BRD #152)
```

**6.3 cookie bullet:** replace
```markdown
- **คุกกี้ (M5):** ใส่ `cookiefile=data/cookies.txt` หรือ `cookiesfrombrowser=("firefox",)` เฉพาะครั้งที่ FR-CK-7 อนุญาต (ครั้งนั้นใช้แทนเซสชันผู้ชม ไม่ใช้สองไฟล์พร้อมกัน) · ห้ามใช้ `verbose` หรือ `print_traffic` ตอนใช้คุกกี้ และทุกข้อความจาก yt-dlp ผ่านตัวปิดบังค่าคุกกี้ก่อนลง log
```
with
```markdown
- **บัญชียูทูปชั่วคราว (M5 รอบ C):** ใส่ jar ในหน่วยความจำให้ YoutubeDL ตรง ๆ (แบบเดียวกับเซสชันผู้ชม) เฉพาะรอบที่ลองซ้ำด้วยบัญชี และใช้แทนเซสชันผู้ชม (ไม่ใช่ทั้งสองอย่าง) · ไม่มี `cookiefile` และไม่บันทึกคุกกี้ลงไฟล์ (คุกกี้ที่ยูทูปหมุนให้อยู่ใน jar ก้อนเดิม) · ห้ามใช้ `verbose`, `debug_printtraffic`, `dump_intermediate_pages`, `write_pages` คู่กับบัญชี · ตัวกรองของ log ปิดค่า header `Cookie`/`Set-Cookie` และค่าคุกกี้เข้าสู่ระบบที่รู้จักชื่อตั้งแต่เริ่มโปรเซส · เพลย์ลิสต์และคอมเมนต์ปักหมุดไม่ใช้บัญชี
```

**6.4 settings: delete the `cookies` row (keep the `filenameStyle` row above it):** replace
```markdown
| `filenameStyle` | `title` \| `title-channel` \| `title-quality` | `title` (FR-OUT-8) |
| `cookies` | `{enabled: bool, source: "file" \| "firefox" \| null, warningAccepted: bool, importedAt?: string}` | `{enabled:false, source:null, warningAccepted:false}` · เก็บแค่สถานะ ค่าคุกกี้อยู่ใน `data/cookies.txt` เท่านั้น · ไม่ถูกส่งออกใน `/settings/export` (FR-CK) |
```
with
```markdown
| `filenameStyle` | `title` \| `title-channel` \| `title-quality` | `title` (FR-OUT-8) |
```

**6.6 visitor session note:** replace
```markdown
**ไม่นำเข้าคุกกี้จากเบราว์เซอร์** (นั่นคือ M5 แบบเลือกเปิดเอง)
```
with
```markdown
**ไม่นำเข้าคุกกี้จากเบราว์เซอร์** (บัญชียูทูปชั่วคราวของ M5 รอบ C อยู่ในหน่วยความจำเท่านั้น ไม่ปนกับไฟล์นี้)
```

**7.1 report sample line:** replace
```markdown
- คุกกี้: ปิดอยู่
```
with
```markdown
- บัญชียูทูป: ไม่ได้ใช้บัญชี
```

**7.1 report rule:** replace
```markdown
- ไม่ใส่ค่าคุกกี้ในรายงานและใน log เลย บอกได้แค่สถานะ (ปิดอยู่ / เปิด ใช้ไฟล์ / เปิด ใช้ Firefox) (FR-CK-5)
```
with
```markdown
- ไม่ใส่ชื่อหรือค่าคุกกี้ในรายงานและใน log เลย บอกได้แค่สถานะบัญชียูทูป (ไม่ได้ใช้บัญชี / ใช้บัญชีชั่วคราวอยู่) (FR-CK-5) · ตัวกรองของ log ปิดค่า header `Cookie`/`Set-Cookie` และค่าคุกกี้เข้าสู่ระบบที่รู้จักชื่อ ติดตั้งตั้งแต่สร้างไฟล์ `app.log` (ก่อนโหลดเว็บ M5 รอบ C)
```

**AC-SET-06:** replace
```markdown
| AC-SET-06 | นำเข้า `cookies.txt` ที่มีค่าคุกกี้ปลอมที่จำง่าย (canary) แล้วทำให้เกิด error ทั้งตอน probe และตอนโหลดด้วยคุกกี้ → ค่า canary ไม่อยู่ใน `run/logs/*`, `/api/diagnostics`, `detail` ของ error และคำตอบของ API ใด ๆ · รายงานมีแค่บรรทัดสถานะคุกกี้ | A |
```
with
```markdown
| AC-SET-06 | นำเข้า `cookies.txt` ที่ค่าคุกกี้ (และชื่อคุกกี้หนึ่งตัว) เป็นค่าปลอมที่จำง่าย (canary) แล้วเปิดคลิปด้วยบัญชี ทำงานที่ใช้บัญชีทั้งที่สำเร็จและพลาด เรียก `/health` และ `GET /cookies` → ค่า canary ไม่อยู่ใน `run/logs/*` (รวม `app.log`), ข่าว SSE, `detail` ของ error และคำตอบของ API ใด ๆ และไม่มีไฟล์ใดในโฟลเดอร์ข้อมูลหรือ temp ที่มี canary · (M6) `/api/diagnostics` ต้องผ่านเงื่อนไขเดียวกัน และรายงานมีแค่บรรทัดสถานะบัญชี | A |
```

**9 network-test list:** replace
```markdown
คลิปจำกัดอายุ (AC-CK-09) รันด้วยคุกกี้ของบัญชีสำรองบนเครื่องผู้พัฒนาเท่านั้น ห้าม commit คุกกี้
```
with
```markdown
คลิปจำกัดอายุ (AC-CK-09, `[account]` ใน toml) รันด้วย `cookies.txt` ของบัญชีสำรองที่ชี้ด้วย env `YT_TOOLKIT_TEST_COOKIES` บนเครื่องผู้พัฒนาเท่านั้นหลังพิธอนุมัติ ห้าม commit ไฟล์
```

**10 milestone M5:** replace
```markdown
คุกกี้ยูทูปแบบเลือกเปิด (W6 แท็บขั้นสูง, `/cookies*`, แถวคุกกี้ใน `/health`)
```
with
```markdown
บัญชียูทูปชั่วคราว (รอบ C: ปุ่มบน error, dialog, แถบบนหน้า, W6 แท็บขั้นสูง, `/cookies*`, แถวบัญชีใน `/health`)
```

**10 milestone M6:** replace
```markdown
README Windows (รวมวิธีใช้คุกกี้ผ่าน Firefox / cookies.txt)
```
with
```markdown
README Windows (รวมวิธีส่งออก `cookies.txt` จากหน้าต่างไม่ระบุตัวตนสำหรับบัญชียูทูปชั่วคราว)
```

**11 traceability:** replace
```markdown
| FR-CK-1..8 | W2, W6, W7 | `/settings`, `/cookies*`, `/health`, `/jobs` (`useCookies`) | AC-CK-01..09, AC-SET-06 |
```
with
```markdown
| FR-CK-1..8 | W2, W4, W6, W7 | `/cookies*`, `/health`, SSE `account` | AC-CK-01..09, AC-SET-06 |
```

- [ ] **Step 2: BRD.md** (the `[^ck-guide]` footnote moves from the third-party yt-dlp.net page to the official yt-dlp wiki FAQ; the `E_BOT_CHECK` rationale becomes "protect the account"; decisions C1-C9 become #144-#152)
**1 summary row:** replace
```markdown
**คุกกี้ยูทูป: ค่าเริ่มต้นไม่ใช้** เปิดใช้เองได้สำหรับคลิปจำกัดอายุหรือคลิปที่บัญชีของผู้ใช้มีสิทธิ์ดู (ข้อ 5.12)
```
with
```markdown
**บัญชียูทูป: ค่าเริ่มต้นไม่ใช้** ใช้บัญชีสำรองแบบชั่วคราวได้เมื่อคลิปต้องเข้าสู่ระบบ แอพถือไว้ในหน่วยความจำและลบเอง (ข้อ 5.12)
```

**4 scope (in):** replace
```markdown
- คุกกี้ยูทูปแบบเลือกเปิดเอง **ปิดไว้เป็นค่าเริ่มต้น** (ข้อ 5.12)
```
with
```markdown
- บัญชียูทูปชั่วคราว (ข้อ 5.12) **ไม่ได้ใช้เป็นค่าเริ่มต้น** ใช้เมื่อผู้ใช้นำเข้าเองจากปุ่มบน error หรือหน้าตั้งค่า และแอพลบเอง
```

**4 scope (out):** replace
```markdown
(คุกกี้ยูทูปแบบเลือกเปิดในข้อ 5.12 ใช้บัญชียูทูปของผู้ใช้เอง ไม่ใช่ระบบบัญชีของแอพ)
```
with
```markdown
(บัญชียูทูปชั่วคราวในข้อ 5.12 คือบัญชียูทูปสำรองของผู้ใช้เอง ไม่ใช่ระบบบัญชีของแอพ)
```

**FR-SET-4:** replace
```markdown
และแสดงว่าเปิดใช้คุกกี้อยู่หรือไม่ (FR-CK-8)
```
with
```markdown
และแสดงว่าใช้บัญชียูทูปชั่วคราวอยู่หรือไม่ (FR-CK-8)
```

**FR-SET-5:** replace
```markdown
ห้ามมีค่าคุกกี้ใน log และรายงาน (FR-CK-5)
```
with
```markdown
ห้ามมีชื่อหรือค่าคุกกี้ใน log และรายงาน (FR-CK-5)
```

**section 5.12 rewritten (heading through the `[^ck-guide]` footnote; `[^ck-chrome]` and `[^ck-issue]` below it stay):** replace
```markdown
### 5.12 คุกกี้ยูทูป (ทางเลือก ปิดไว้เป็นค่าเริ่มต้น) (FR-CK)
ค่าเริ่มต้นของแอพยังเป็น "ไม่ใช้คุกกี้" ตามบันทึกการตัดสินใจข้อ 8 ส่วนนี้เพิ่มทางเลือกให้ผู้ใช้เปิดเองได้ (ข้อ 24) สำหรับ 3 กรณี: คลิปจำกัดอายุ, คลิปส่วนตัวที่บัญชีของผู้ใช้มีสิทธิ์ดู และคลิปเฉพาะสมาชิกช่อง
คุกกี้คือ "บัตรผ่าน" ที่ทำให้ใครก็ตามที่ถือไฟล์นั้นเข้าบัญชียูทูปของผู้ใช้ได้โดยไม่ต้องใช้รหัสผ่าน[^ck-guide] จึงต้องมีรั้วกั้นทุกข้อด้านล่าง

| รหัส | ความต้องการ |
|---|---|
| FR-CK-1 | **ปิดไว้เป็นค่าเริ่มต้น** เปิดได้ที่ ตั้งค่า > ขั้นสูง เท่านั้น ไม่มีปุ่มลัดหรือหน้าต่างชวนเปิดจากที่อื่น นอกจากข้อความ error ที่บอกว่าเปิดได้ที่ไหน |
| FR-CK-2 | **แหล่งคุกกี้ 2 แบบ**: (1) นำเข้าไฟล์ `cookies.txt` (รูปแบบ Netscape ที่ส่งออกจากส่วนขยายของเบราว์เซอร์) (2) อ่านจาก Firefox ตอนใช้งาน (`--cookies-from-browser firefox`) · **Chrome บน Windows อ่านตรงไม่ได้** ตั้งแต่ Chrome 127 เพราะ Chrome เข้ารหัสคุกกี้ด้วยกุญแจที่ผูกกับตัวแอพ (app-bound encryption)[^ck-chrome][^ck-guide] หน้าจอต้องบอกเรื่องนี้ และแนะนำให้ใช้ Firefox หรือส่งออก `cookies.txt` แทน |
| FR-CK-3 | **คำเตือนตอนเปิดครั้งแรก** เป็นกล่องยืนยันที่บอกว่า บัญชี Google ที่ใช้อาจถูกจำกัดหรือถูกล็อก (ยูทูปจับได้ว่าเซสชันถูกใช้กับตัวโหลด)[^ck-guide][^ck-issue] ซึ่งอาจกระทบ Gmail และ Drive ของบัญชีนั้นด้วย แนะนำให้ใช้ **บัญชีสำรอง** ไม่ใช้บัญชีงานหลัก และห้ามส่งไฟล์คุกกี้ให้คนอื่น ต้องกดยืนยันก่อนจึงเปิดได้ |
| FR-CK-4 | **เก็บใน `data/` ที่เดียว** ไฟล์ที่นำเข้าเก็บเป็น `data/cookies.txt` และเก็บเฉพาะคุกกี้ของโดเมน `youtube.com` และ `google.com` ส่วนโดเมนอื่นทิ้งตอนนำเข้า · ห้ามคัดลอกไปไว้ที่ `work/`, `run/`, โฟลเดอร์ผลลัพธ์ หรือไฟล์สำรองค่าตั้ง (FR-SET-7) · โหมด Firefox ไม่เก็บคุกกี้ไว้เลย อ่านใหม่ทุกครั้งที่ใช้ |
| FR-CK-5 | **ไม่หลุดออกทาง log หรือรายงาน** ค่าคุกกี้ต้องไม่อยู่ใน `app.log`, รายงานแจ้งปัญหา, `detail` ของ error และคำตอบของ API ใด ๆ (API บอกได้แค่ว่าเปิดอยู่ไหม ใช้แหล่งไหน และนำเข้าเมื่อไร) · ข้อความจาก yt-dlp ที่อาจมี header `Cookie` ต้องปิดบังก่อนบันทึก |
| FR-CK-6 | ปุ่ม **"ลบคุกกี้"** ลบ `data/cookies.txt` และปิดการใช้คุกกี้ทันที งานที่เริ่มหลังจากนั้นไม่ใช้คุกกี้อีก |
| FR-CK-7 | **ใช้เฉพาะเมื่อจำเป็น** ถึงเปิดไว้แล้ว ทุกคำขอก็ยังลองแบบไม่ใช้คุกกี้ก่อน แล้วใช้คุกกี้เฉพาะ (1) ลองใหม่ 1 ครั้งหลังได้ `E_AGE_RESTRICTED` หรือ `E_VIDEO_PRIVATE` ทั้งตอนดึงข้อมูลคลิปและตอนโหลด หรือ (2) ผู้ใช้ติ๊ก "ใช้คุกกี้กับคลิปนี้" ในตัวเลือกขั้นสูงของคลิปนั้น · ไม่ใช้คุกกี้แก้ `E_BOT_CHECK` เพราะคุกกี้แก้กำแพงบอทไม่ได้[^ck-guide] และจะทำให้บัญชีถูกผูกกับคำขอที่ถูกมองว่าเป็นบอท · การหน่วงเวลาของคิว (FR-Q-3) ใช้เหมือนเดิม |
| FR-CK-8 | หน้าตรวจสุขภาพระบบมีแถว "คุกกี้" บอกสถานะ: ปิดอยู่ (ค่าเริ่มต้น) / เปิดอยู่ ใช้ไฟล์ที่นำเข้าเมื่อ <วันที่> / เปิดอยู่ ใช้ Firefox / เปิดไว้แต่อ่านไม่ได้ (พร้อมวิธีแก้) · รายงานแจ้งปัญหาบอกสถานะนี้ได้ แต่ไม่มีค่าคุกกี้ |

[^ck-guide]: yt-dlp, "Cookies" guide: วิธีใช้ `--cookies` / `--cookies-from-browser`, Firefox เป็นตัวเลือกที่แนะนำ, Chrome 127 ขึ้นไปอ่านคุกกี้ไม่ได้, cookies.txt คือเซสชันที่ใช้ได้จริงในรูปข้อความล้วน, แนะนำให้ใช้บัญชีทิ้งได้เพราะเว็บจับเซสชันที่ใช้กับตัวโหลดได้ และคุกกี้ไม่ช่วยเรื่องกำแพงบอท https://yt-dlp.net/guides/cookies (เข้าถึง 2026-09-29)
```
with
```markdown
### 5.12 บัญชียูทูปชั่วคราว (ไม่ได้ใช้เป็นค่าเริ่มต้น) (FR-CK)
ค่าเริ่มต้นของแอพยังเป็น "ไม่ใช้บัญชี" ตามบันทึกการตัดสินใจข้อ 8 ส่วนนี้ให้ผู้ใช้ยืมการเข้าสู่ระบบของ**บัญชีสำรอง**มาใช้ชั่วคราว (ข้อ 24 ปรับใหม่ในข้อ 144-152 ของ M5 รอบ C) สำหรับ 3 กรณี: คลิปจำกัดอายุ คลิปส่วนตัวที่เจ้าของช่องแชร์ให้บัญชีนั้น และคลิปเฉพาะสมาชิกช่อง
ไฟล์ `cookies.txt` คือ "บัตรผ่าน" ที่ทำให้ใครก็ตามที่ถือไฟล์นั้นเข้าบัญชียูทูปได้โดยไม่ต้องใช้รหัสผ่าน[^ck-guide] รอบ C จึงให้แอพถือไว้ในหน่วยความจำเท่านั้นและลบเองเร็วที่สุด แล้วให้ผู้ใช้ออกจากระบบในหน้าต่างไม่ระบุตัวตน ซึ่งทำให้ไฟล์ทุกสำเนาใช้ไม่ได้

| รหัส | ความต้องการ |
|---|---|
| FR-CK-1 | **ไม่ได้ใช้เป็นค่าเริ่มต้น เข้าได้จาก error เอง** ปุ่ม "ใช้บัญชียูทูปชั่วคราว" อยู่บน error `E_AGE_RESTRICTED` / `E_VIDEO_PRIVATE` ของหน้า W2 แถวงานและ toast ของงานที่พลาด และ toast ของถ่ายภาพคม และใน ตั้งค่า > ขั้นสูง · นำเข้าแล้วแอพลองสิ่งที่เพิ่งพลาดใหม่เอง (ข้อ 150 แทนกฎ "ไม่มีปุ่มลัด" เดิม) |
| FR-CK-2 | **แหล่งเดียว: ไฟล์ `cookies.txt` ที่ส่งออกจากหน้าต่างไม่ระบุตัวตนของ Chrome** (รูปแบบ Netscape) ตามขั้นตอนในกล่อง: เปิดหน้าต่างไม่ระบุตัวตน เข้าสู่ระบบด้วยบัญชีสำรอง เปิด `youtube.com/robots.txt` ในแท็บเดิม ส่งออกด้วยส่วนขยาย แล้วเปิดหน้าต่างนั้นค้างไว้[^ck-export] · ไม่มีโหมดอ่านจาก Firefox (อาจใช้บัญชีหลักโดยไม่รู้ตัว) · Chrome บน Windows อ่านคุกกี้ตรงไม่ได้ตั้งแต่ Chrome 127[^ck-chrome] จึงไม่มีโหมดอ่านจากเบราว์เซอร์เลย · แอพไม่บอกชื่อส่วนขยาย |
| FR-CK-3 | **คำเตือนในกล่องนำเข้าทุกครั้ง** บัญชี Google ที่ใช้อาจถูกจำกัดหรือถูกล็อก (ยูทูปจับได้ว่าเซสชันถูกใช้กับตัวโหลด)[^ck-export][^ck-issue] ซึ่งกระทบ Gmail และ Drive ของบัญชีนั้นด้วย · ใช้**บัญชีสำรอง**เท่านั้น ห้ามใช้บัญชีเจ้าของช่องหรือบัญชีงานหลัก และห้ามส่งไฟล์ให้คนอื่น · คลิปส่วนตัวต้องให้เจ้าของช่องแชร์ให้อีเมลของบัญชีสำรองก่อน · UI ไม่ใช้คำว่า "คุกกี้" (มีแค่ชื่อไฟล์) |
| FR-CK-4 | **อยู่ในหน่วยความจำเท่านั้น** ไม่เขียนลงดิสก์ในรูปใดเลย (`data/`, `work/`, `run/`, โฟลเดอร์ผลลัพธ์ ไฟล์สำรองค่าตั้ง temp) · เก็บเฉพาะคุกกี้ของ `youtube.com` และ `google.com` ส่วนโดเมนอื่นทิ้งตอนนำเข้า · ข้อมูลคลิปที่ได้มาด้วยบัญชีก็อยู่ในหน่วยความจำ ไม่ขึ้นในประวัติ · ปิดโปรแกรม (รวมเครื่องดับ) = หายหมด |
| FR-CK-5 | **ไม่หลุดออกทาง log หรือรายงาน** ชื่อและค่าคุกกี้ต้องไม่อยู่ใน `app.log`, ข่าว SSE, รายงานแจ้งปัญหา, `detail` ของ error และคำตอบของ API ใด ๆ (API บอกได้แค่ว่าถือบัญชีอยู่ไหม นำเข้าเมื่อไร และจะลบเมื่อไร) · ตัวกรองของ log ปิดค่า header `Cookie` และค่าคุกกี้เข้าสู่ระบบที่รู้จักชื่อ ติดตั้งตั้งแต่เริ่มโปรเซส |
| FR-CK-6 | **ลบเองเมื่อถึงอย่างแรก:** ครบ 2 ชั่วโมงหลังนำเข้า · ปิดโปรแกรม · งานในคิวที่ใช้บัญชีจบแล้วคิวว่างครบ 10 นาที (งานใหม่เข้าคิวระหว่างนั้น = ยกเลิกการนับ) · มีปุ่ม "ลบออกตอนนี้" (ไม่ต้องยืนยัน) · ลบแล้วทุกแท็บขึ้น toast ให้ไปกดออกจากระบบในหน้าต่างไม่ระบุตัวตน (ทำให้ไฟล์ต้นฉบับในโฟลเดอร์ดาวน์โหลดใช้ไม่ได้ด้วย) · งานที่กำลังโหลดอยู่ใช้ต่อจนจบ |
| FR-CK-7 | **ใช้เฉพาะเมื่อจำเป็น** ถือบัญชีอยู่ก็ยังลองแบบไม่ใช้บัญชีก่อนเสมอ แล้วลองใหม่ด้วยบัญชี 1 ครั้งทั้งก้อนหลังได้ `E_AGE_RESTRICTED` หรือ `E_VIDEO_PRIVATE` (ดึงข้อมูลคลิปของ W2, งานในคิวทั้งงาน, ถ่ายภาพคม) · **ไม่ใช้บัญชีกับ `E_BOT_CHECK`** แม้คุกกี้ที่เข้าสู่ระบบจะผ่านการขอยืนยันว่าไม่ใช่บอทได้[^ck-bot] เพราะตอนนั้นยูทูปกำลังจับตา IP นี้ การผูกบัญชีเข้าไปเพิ่มโอกาสที่บัญชีจะถูกล็อก (เลือกปกป้องบัญชี) · การหน่วงเวลาของคิว (FR-Q-3) และการพักคิวใช้เหมือนเดิม |
| FR-CK-8 | หน้าตรวจสุขภาพระบบมีแถว "บัญชียูทูป" บอกสถานะอย่างเดียว: ไม่ได้ใช้บัญชี / ใช้บัญชีชั่วคราวอยู่ (นำเข้าเมื่อ HH:MM) · ไม่ส่งคำขอทดสอบไปยูทูป · รายงานแจ้งปัญหาบอกสถานะนี้ได้ แต่ไม่มีค่าคุกกี้ |

[^ck-guide]: yt-dlp wiki (ทางการ บน GitHub), FAQ "How do I pass cookies to yt-dlp?": ไฟล์คุกกี้ต้องเป็นรูปแบบ Mozilla/Netscape (บรรทัดแรก `# Netscape HTTP Cookie File`) ส่งออกได้ด้วยส่วนขยายของเบราว์เซอร์ และให้ระวังตอนติดตั้งส่วนขยาย https://github.com/yt-dlp/yt-dlp/wiki/FAQ#how-do-i-pass-cookies-to-yt-dlp (เข้าถึง 2026-10-06) · แทนแหล่งเดิม yt-dlp.net ซึ่งเป็นเว็บบุคคลที่สาม ไม่ใช่ของโครงการ yt-dlp
[^ck-export]: yt-dlp wiki (ทางการ), Extractors "Exporting YouTube cookies": ยูทูปหมุนคุกกี้บ่อยในแท็บที่เปิดยูทูปอยู่ วิธีที่ได้ไฟล์ใช้ได้นานคือ หน้าต่างส่วนตัว → เข้าสู่ระบบ → เปิด `youtube.com/robots.txt` ในแท็บเดิม → ส่งออก → ปิดหน้าต่าง · ใช้บัญชีกับ yt-dlp เสี่ยงโดนแบน "ชั่วคราวหรือถาวร" https://github.com/yt-dlp/yt-dlp/wiki/Extractors#exporting-youtube-cookies (เข้าถึง 2026-10-06)
[^ck-bot]: yt-dlp issue #3766 (รายการปัญหาที่รู้แล้วของยูทูป): "Sign in to confirm you're not a bot" แก้ได้ทางหนึ่งด้วยคุกกี้ที่เข้าสู่ระบบ แลกกับความเสี่ยงที่บัญชีจะถูกบล็อก https://github.com/yt-dlp/yt-dlp/issues/3766 (เข้าถึง 2026-10-06)
```

**8 project tree: `cookies.py` line:** replace
```markdown
│     ├─ cookies.py          # คุกกี้แบบเลือกเปิด: นำเข้า/กรองโดเมน/ลบ, ปิดบังค่าใน log
```
with
```markdown
│     ├─ account_session.py  # บัญชียูทูปชั่วคราวในหน่วยความจำ: นำเข้า ลบเอง (2 ชม. / คิวว่าง 10 นาที / ปิดโปรแกรม)
│     ├─ account_scope.py    # กฎลองซ้ำด้วยบัญชี 1 ครั้ง (ขอบเขตของงานที่ใช้บัญชี)
```

**8 project tree: `data/` comment:** delete this text (the new text is empty):
```markdown
cookies.txt (มีเฉพาะเมื่อผู้ใช้นำเข้าเอง), 
```

**13 error table: private / members-only row:** replace
```markdown
· คลิปส่วนตัวหรือเฉพาะสมาชิกบอกเพิ่มว่า ถ้าบัญชีของผู้ใช้มีสิทธิ์ดู เปิดใช้คุกกี้ได้ที่ ตั้งค่า > ขั้นสูง | ถ้าเปิดคุกกี้ไว้ ลองใหม่ด้วยคุกกี้ 1 ครั้ง (FR-CK-7) ถ้าไม่ได้ ทำเครื่องหมายว่าล้มเหลว ทำงานอื่นต่อ |
```
with
```markdown
· คลิปส่วนตัวหรือเฉพาะสมาชิกบอกว่าต้องเข้าสู่ระบบด้วยบัญชีที่มีสิทธิ์ดู พร้อมปุ่ม "ใช้บัญชียูทูปชั่วคราว" | ถือบัญชีชั่วคราวอยู่ = ลองใหม่ด้วยบัญชี 1 ครั้ง (FR-CK-7) ถ้ายังไม่ได้ บอกว่าบัญชีอาจไม่มีสิทธิ์หรือหมดอายุ ทำเครื่องหมายว่าล้มเหลว ทำงานอื่นต่อ |
```

**13 error table: age-restricted row:** replace
```markdown
| คลิปจำกัดอายุ | คลิปนี้จำกัดอายุ ต้องใช้บัญชี YouTube ถึงจะโหลดได้ เปิดใช้ได้ที่ ตั้งค่า > ขั้นสูง | ถ้าเปิดคุกกี้ไว้ ลองใหม่ด้วยคุกกี้ 1 ครั้ง (FR-CK-7) ถ้ายังไม่ได้ บอกว่าคุกกี้อาจหมดอายุ · ถ้าไม่ได้เปิดไว้ ข้าม |
```
with
```markdown
| คลิปจำกัดอายุ | คลิปนี้จำกัดอายุ ต้องเข้าสู่ระบบยูทูปถึงจะเปิดได้ พร้อมปุ่ม "ใช้บัญชียูทูปชั่วคราว" | ถือบัญชีชั่วคราวอยู่ = ลองใหม่ด้วยบัญชี 1 ครั้ง (FR-CK-7) ถ้ายังไม่ได้ ใช้ข้อความ "ลองด้วยบัญชีแล้ว…" และคงบัญชีไว้ · ไม่ได้ถือบัญชี = ข้าม |
```

**13 error table: invalid file row:** replace
```markdown
| ไฟล์คุกกี้ใช้ไม่ได้ / อ่านคุกกี้จาก Firefox ไม่ได้ | บอกสาเหตุ และแนะนำให้นำเข้าใหม่หรือเปลี่ยนแหล่ง | คงสถานะเดิม แถว "คุกกี้" ในหน้าตรวจสุขภาพเป็น "อ่านไม่ได้" |
```
with
```markdown
| ไฟล์ cookies.txt ที่นำเข้าใช้ไม่ได้ (ไม่ใช่รูปแบบ Netscape เกิน 1 MB หรือไม่มีคุกกี้เข้าสู่ระบบของยูทูป) | ข้อความใต้ช่องเลือกไฟล์ในกล่องนำเข้า แนะนำให้ตรวจว่าเข้าสู่ระบบแล้วและส่งออกใหม่ | บัญชีที่ถืออยู่เดิมไม่เปลี่ยน ไม่ยกเนื้อไฟล์ใน error |
```

**15 network tests:** replace
```markdown
คลิปจำกัดอายุทดสอบด้วยคุกกี้ของบัญชีสำรองเท่านั้น และรันเองบนเครื่องผู้พัฒนา
```
with
```markdown
คลิปจำกัดอายุทดสอบด้วย `cookies.txt` ของบัญชีสำรองเท่านั้น (path จาก env ไม่ commit) และรันเองบนเครื่องผู้พัฒนาหลังได้รับอนุญาต
```

**16 milestone M5 (1):** replace
```markdown
คุกกี้ยูทูปแบบเลือกเปิด (ข้อ 5.12)
```
with
```markdown
บัญชียูทูปชั่วคราว (ข้อ 5.12 รอบ C)
```

**16 milestone M5 (2):** replace
```markdown
คลิปจำกัดอายุโหลดได้ด้วยคุกกี้ของบัญชีสำรอง และไม่มีค่าคุกกี้ใน log หรือรายงาน
```
with
```markdown
คลิปจำกัดอายุโหลดได้ด้วยบัญชีสำรองแบบชั่วคราว ไม่มีอะไรลงดิสก์ และไม่มีค่าคุกกี้ใน log หรือรายงาน
```

**18 risk row:** replace
```markdown
| **ผู้ใช้เปิดคุกกี้แล้วบัญชี Google ถูกจำกัดหรือถูกล็อก** หรือไฟล์คุกกี้หลุดไปถึงคนอื่น (ไฟล์คุกกี้ใช้เข้าบัญชีได้โดยไม่ต้องมีรหัสผ่าน)[^ck-guide][^ck-issue] | กลาง (เฉพาะคนที่เปิดใช้) | สูง | ปิดไว้เป็นค่าเริ่มต้น (FR-CK-1) · คำเตือนตอนเปิดครั้งแรกแนะนำบัญชีสำรอง (FR-CK-3) · ใช้คุกกี้เฉพาะเมื่อจำเป็น (FR-CK-7) · เก็บใน `data/` ที่เดียวและกรองเหลือแค่โดเมนยูทูป/Google (FR-CK-4) · ไม่อยู่ใน log และรายงาน (FR-CK-5) · มีปุ่มลบคุกกี้ (FR-CK-6) · Chrome บน Windows อ่านไม่ได้อยู่แล้ว[^ck-chrome] ผู้ใช้จึงต้องใช้ Firefox หรือ `cookies.txt` ซึ่งต้องบอกวิธีใน README |
```
with
```markdown
| **ผู้ใช้ใช้บัญชีชั่วคราวแล้วบัญชี Google ถูกจำกัดหรือถูกล็อก** หรือไฟล์ `cookies.txt` หลุดไปถึงคนอื่น (ไฟล์ใช้เข้าบัญชีได้โดยไม่ต้องมีรหัสผ่าน)[^ck-guide][^ck-issue] | กลาง (เฉพาะคนที่ใช้) | สูง | ไม่ได้ใช้เป็นค่าเริ่มต้น และคำเตือนในกล่องนำเข้าทุกครั้งให้ใช้บัญชีสำรองเท่านั้น (FR-CK-3) · ใช้เฉพาะเมื่อจำเป็น ไม่ใช้กับ `E_BOT_CHECK` (FR-CK-7) · อยู่ในหน่วยความจำเท่านั้นและกรองเหลือแค่โดเมนยูทูป/Google (FR-CK-4) · ไม่อยู่ใน log และรายงาน (FR-CK-5) · ลบเองภายใน 2 ชั่วโมงหรือหลังคิวว่าง แล้วบอกให้ออกจากระบบในหน้าต่างไม่ระบุตัวตน ซึ่งทำให้ไฟล์ทุกสำเนาใช้ไม่ได้ (FR-CK-6) · แอพลบไฟล์ต้นฉบับในโฟลเดอร์ดาวน์โหลดเองไม่ได้ |
```

**19 decision #8:** replace
```markdown
แต่เพิ่มคุกกี้แบบเลือกเปิดเองในข้อ 24 |
```
with
```markdown
แต่เพิ่มคุกกี้แบบเลือกเปิดเองในข้อ 24 (M5 รอบ C เปลี่ยนเป็นบัญชียูทูปชั่วคราวในหน่วยความจำ ข้อ 144-152) |
```

**19 decision #24:** replace
```markdown
| 24 | **คุกกี้ยูทูปแบบเลือกเปิดเอง ปิดไว้เป็นค่าเริ่มต้น** (ข้อ 5.12) · M5 · เปลี่ยนข้อ 8 บางส่วน | ✅ | ข้อ 8 ยังเป็นค่าเริ่มต้น (ไม่มีล็อกอินของแอพ ค่าเริ่มต้นไม่ใช้คุกกี้) แต่พนักงานบางคนต้องใช้คลิปจำกัดอายุ คลิปส่วนตัวที่บัญชีตัวเองดูได้ และคลิปเฉพาะสมาชิก · ความเสี่ยงคือบัญชีถูกจำกัดและไฟล์คุกกี้หลุด จึงมีรั้วกั้นครบ (FR-CK-1..8, ข้อ 18) · พิธอนุมัติ (2026-09-29) |
```
with
```markdown
| 24 | **คุกกี้ยูทูปแบบเลือกเปิดเอง ปิดไว้เป็นค่าเริ่มต้น** (ข้อ 5.12) · M5 · เปลี่ยนข้อ 8 บางส่วน | ✅ | ข้อ 8 ยังเป็นค่าเริ่มต้น (ไม่มีล็อกอินของแอพ ค่าเริ่มต้นไม่ใช้คุกกี้) แต่พนักงานบางคนต้องใช้คลิปจำกัดอายุ คลิปส่วนตัวที่บัญชีตัวเองดูได้ และคลิปเฉพาะสมาชิก · ความเสี่ยงคือบัญชีถูกจำกัดและไฟล์คุกกี้หลุด จึงมีรั้วกั้นครบ (FR-CK-1..8, ข้อ 18) · พิธอนุมัติ (2026-09-29) · **M5 รอบ C ปรับรูปแบบเป็นบัญชียูทูปชั่วคราวในหน่วยความจำ** ดูข้อ 144-152 |
```

**19 decisions #144-#152 (C1-C9) right after row 143:** replace
```markdown
| 143 | **ลบภาพที่ถ่ายได้** ลบจากแถบ cache ของแอพ และโฟลเดอร์ของคลิป หลังยืนยัน · ลบเฉพาะไฟล์เดิมที่บันทึกไว้ ไม่ตามลิงก์ · M5 รอบ B2 (E7) | ✅ | หยุดผิดจังหวะบ่อย · ครีมเสนอในดีไซน์ พิธเห็นและอนุมัติ 2026-10-05 |
```
with
```markdown
| 143 | **ลบภาพที่ถ่ายได้** ลบจากแถบ cache ของแอพ และโฟลเดอร์ของคลิป หลังยืนยัน · ลบเฉพาะไฟล์เดิมที่บันทึกไว้ ไม่ตามลิงก์ · M5 รอบ B2 (E7) | ✅ | หยุดผิดจังหวะบ่อย · ครีมเสนอในดีไซน์ พิธเห็นและอนุมัติ 2026-10-05 |
| 144 | **รอบ C ทำต่อเพื่ออนาคต** สำหรับคลิปจำกัดอายุ คลิปส่วนตัว และคลิปเฉพาะสมาชิก แม้คลิป unlisted ใช้ได้โดยไม่ต้องเข้าสู่ระบบอยู่แล้ว · M5 รอบ C (C1) | ✅ | ความต้องการจริงตอนนี้ของพิธคือคลิป unlisted ซึ่งใช้ได้แล้ว แต่อยากมีไว้เผื่อคลิปจำกัดอายุและคลิปส่วนตัว · พิธเลือก "ทำตาม PRD เผื่ออนาคต" 2026-10-06 |
| 145 | **แนะนำบัญชี Google สำรองเสมอ** คลิปส่วนตัวให้เจ้าของช่องแชร์ให้อีเมลของบัญชีสำรองใน YouTube Studio (ราว 32-50 อีเมลต่อคลิป) · M5 รอบ C (C2) | ✅ | บัญชีถูกล็อก = ช่องจริง Gmail และ Drive ยังปลอดภัย · บัญชีสำรองใหม่ดูคลิปส่วนตัวไม่ได้จนกว่าจะถูกแชร์ · พิธอนุมัติ 2026-10-06 |
| 146 | **ใช้ชั่วคราวเท่านั้น** นำเข้า โหลด แอพลบเอง แล้วบอกให้ออกจากระบบในหน้าต่างไม่ระบุตัวตน · M5 รอบ C (C3) | ✅ | พิธ: "โหลดเสร็จแล้วบอกให้ logout ได้เลย จะได้ไม่ค้างไว้" · การออกจากระบบทำให้ทุกสำเนาของไฟล์ใช้ไม่ได้ รวมไฟล์ต้นฉบับในโฟลเดอร์ดาวน์โหลด |
| 147 | **นำเข้า `cookies.txt` จากหน้าต่างไม่ระบุตัวตนของ Chrome อย่างเดียว ไม่มีโหมด Firefox** · M5 รอบ C (C4) | ✅ | ออกจากระบบในหน้าต่างไม่ระบุตัวตนไม่กระทบการเข้าสู่ระบบในหน้าต่างปกติ · แอพอ่านคุกกี้ของหน้าต่างส่วนตัวของ Firefox ไม่ได้ และโหมด Firefox อาจใช้บัญชีหลักของพนักงานโดยไม่รู้ตัว · พิธเลือก A 2026-10-06 |
| 148 | **UI ไม่ใช้คำว่า "คุกกี้"** ใช้ "บัญชียูทูป" / "เข้าสู่ระบบ" มีแค่ชื่อไฟล์ `cookies.txt` ในขั้นตอนส่งออก · M5 รอบ C (C5) | ✅ | พิธ: พนักงานส่วนใหญ่ไม่รู้ว่าคุกกี้คืออะไร |
| 149 | **ลบเองเมื่อถึงอย่างแรก:** งานในคิวที่ใช้บัญชีจบแล้วคิวว่างครบ 10 นาที · ปิดโปรแกรม · ครบ 2 ชั่วโมงหลังนำเข้า · M5 รอบ C (C6) | ✅ | พิธเลือก A 2026-10-06 · 10 นาทีเป็นค่าที่ planner เลือก ให้ส่งคลิปจำกัดอายุหลายคลิปต่อกันได้โดยไม่ต้องนำเข้าใหม่ · ดูข้อมูลคลิปหรือถ่ายภาพคมไม่เริ่มนับ (ไม่งั้นบัญชีหายก่อนกดโหลด) |
| 150 | **ทางเข้าคือปุ่มบน error เอง** "ใช้บัญชียูทูปชั่วคราว" บน error ของหน้า W2 งานที่พลาด และถ่ายภาพคม และอยู่ใน ตั้งค่า > ขั้นสูง ด้วย · นำเข้าแล้วลองใหม่เอง · M5 รอบ C (C7) | ✅ | พิธเลือก A 2026-10-06 · แทนกฎ "ไม่มีปุ่มลัด" ของ FR-CK-1 เดิม |
| 151 | **อยู่ในหน่วยความจำเท่านั้น** ไม่เขียนการเข้าสู่ระบบลงดิสก์ในรูปใดเลย ปิดโปรแกรม (รวมเครื่องดับ) = หาย · ข้อมูลคลิปที่ได้ด้วยบัญชีก็อยู่ในหน่วยความจำจนลบบัญชี ไม่ขึ้นในประวัติ · M5 รอบ C (C8) | ✅ | พิธเลือก A 2026-10-06 · กฎเรื่องสำเนาบนดิสก์ทุกข้อของ PRD เดิมจึงไม่ต้องมี · หน่วยความจำของ Python ไม่ถูกล้างค่าทิ้งทันที (ภัยที่กันคือไฟล์และ log ไม่ใช่การอ่านหน่วยความจำ) |
| 152 | **กฎของ planner (แสดงให้พิธดูแล้วไม่ค้าน):** ไม่ใช้บัญชีกับ `E_BOT_CHECK` · ไม่มี checkbox "ใช้คุกกี้กับคลิปนี้" · ถ่ายภาพคมตรงจุดลองซ้ำด้วยบัญชีด้วย · คลิปเฉพาะสมาชิกรวมอยู่ใน `E_VIDEO_PRIVATE` · แถวในหน้าตรวจสุขภาพบอกสถานะอย่างเดียว · M5 รอบ C (C9) | ✅ | ปกป้องบัญชีตอนยูทูปจับตา IP · ลดตัวเลือกที่พนักงานไม่เข้าใจ · คลิปจำกัดอายุต้องถ่ายภาพคมได้เหมือนโหลด · ไม่ส่งคำขอทดสอบที่เสี่ยงโดนจับ |
```

**20 legal note:** replace
```markdown
- คุกกี้ (ข้อ 5.12) ใช้ได้กับบัญชีของผู้ใช้เองและคลิปที่บัญชีนั้นมีสิทธิ์ดูเท่านั้น การโหลดด้วยคุกกี้ไม่ได้ทำให้มีสิทธิ์นำเนื้อหาไปใช้ต่อ
```
with
```markdown
- บัญชียูทูปชั่วคราว (ข้อ 5.12) ใช้ได้กับคลิปที่บัญชีสำรองนั้นมีสิทธิ์ดูเท่านั้น การโหลดด้วยบัญชีไม่ได้ทำให้มีสิทธิ์นำเนื้อหาไปใช้ต่อ
```

- [ ] **Step 3: docs/acceptance.md**
**append the round C section after the last M5 รอบ B2 row:** replace
```markdown
| M5B2-NARROW | ซูม 200% (หรือหน้าต่างกว้าง 640 px): ไม่มีแถบเลื่อนแนวนอน · ต่ำกว่า 640 px ไม่มีปุ่มขยาย และกด T ไม่เปลี่ยน | ☐ |
```
with
```markdown
| M5B2-NARROW | ซูม 200% (หรือหน้าต่างกว้าง 640 px): ไม่มีแถบเลื่อนแนวนอน · ต่ำกว่า 640 px ไม่มีปุ่มขยาย และกด T ไม่เปลี่ยน | ☐ |

## M5 รอบ C (ทำบน Windows 10/11 กับยูทูปจริง ด้วยบัญชี Google สำรองของพิธ)
| AC | ขั้นตอน | ผ่าน |
|---|---|---|
| M5C-ERROR | เปิดคลิปจำกัดอายุ: ข้อความ "คลิปนี้จำกัดอายุ ต้องเข้าสู่ระบบยูทูปถึงจะเปิดได้" และปุ่ม "ใช้บัญชียูทูปชั่วคราว" (ไม่มีปุ่มลองใหม่) · กดแล้ว dialog มีคำเตือนสีแดง ข้อความคลิปส่วนตัว และ 6 ขั้นตอน · ไม่มีคำว่า "คุกกี้" บนจอ (มีแค่ชื่อไฟล์ cookies.txt) · "ยกเลิก" และ Esc ปิดโดยไม่มีอะไรเปลี่ยน | ☐ |
| M5C-EXPORT | ทำตาม 6 ขั้นตอนใน dialog เองด้วย Chrome (หน้าต่างไม่ระบุตัวตน บัญชีสำรอง `youtube.com/robots.txt` ส่วนขยายที่อนุญาตในหน้าต่างไม่ระบุตัวตน) ได้ไฟล์ cookies.txt โดยไม่ต้องถามใคร | ☐ |
| M5C-IMPORT | เลือกไฟล์ที่ไม่ใช่ cookies.txt (เช่นไฟล์ข้อความอื่น): ข้อความ "ไฟล์นี้ใช้ไม่ได้…" ใต้ช่อง dialog ยังเปิด · เลือกไฟล์จริงแล้ว "นำเข้าแล้วลองใหม่": dialog ปิด หน้าคลิปเปิดได้ แถบ "กำลังใช้บัญชียูทูปชั่วคราว · ลบอัตโนมัติภายใน 02:00" อยู่ทุกหน้า · คลิปนี้ไม่ขึ้นใน "ล่าสุด" | ☐ |
| M5C-JOB | โหลด mp4 คลิปจำกัดอายุ (ก่อนนำเข้าก็ได้: งานพลาด toast มีปุ่ม "ใช้บัญชียูทูปชั่วคราว" เป็นปุ่มหลัก "ดูรายละเอียด" เป็นปุ่มรอง แถวในคิวมีปุ่มเดียวกัน · นำเข้าแล้วงานเดิมลองใหม่เอง) ไฟล์เปิดเล่นได้ · "ถ่ายภาพคมตรงนี้" ของคลิปนี้ได้ | ☐ |
| M5C-GRACE | หลังงานที่ใช้บัญชีเสร็จและคิวว่าง รอราว 10 นาที: แถบหาย toast "ลบบัญชีออกจากแอพแล้ว · กลับไปกดออกจากระบบในหน้าต่างไม่ระบุตัวตน แล้วปิดหน้าต่าง" ค้างจนกดปิด (เปิดสองแท็บไว้ ทั้งสองแท็บเห็น) · ส่งคลิปจำกัดอายุอีกคลิประหว่างรอ = ไม่ถูกลบกลางทาง | ☐ |
| M5C-REMOVE | "ลบออกตอนนี้" ที่แถบ: หายทันทีไม่ต้องยืนยัน toast เดียวกัน · ปิดโปรแกรมตอนถือบัญชีอยู่แล้วเปิดใหม่: ไม่มีแถบ คลิปจำกัดอายุขึ้นปุ่มอีกครั้ง · ออกจากระบบในหน้าต่างไม่ระบุตัวตนแล้วนำเข้าไฟล์เดิมอีกครั้ง: คลิปจำกัดอายุขึ้นข้อความ "ลองด้วยบัญชีแล้วยังเปิดไม่ได้…" | ☐ |
| M5C-SETTINGS | ตั้งค่า > ขั้นสูง: คำอธิบาย สถานะ "ไม่ได้ใช้บัญชี" ปุ่ม "ใช้บัญชียูทูปชั่วคราว" (ปุ่มใน dialog เป็น "นำเข้า") · นำเข้าแล้วสถานะมีเวลาที่จะลบและปุ่ม "ลบออกตอนนี้" · ตรวจสุขภาพระบบ แถว "บัญชียูทูป" พร้อม "ใช้บัญชีชั่วคราวอยู่ (นำเข้าเมื่อ HH:MM)" ตรงกับนาฬิกาเครื่อง | ☐ |
| M5C-PRIVACY | หลังทดลองทุกแถว: ค้นคำว่า `SAPISID` และค่าคุกกี้สักตัวจากไฟล์ใน `run/logs/app.log` และทั้งโฟลเดอร์ `data/` (เช่น `findstr /s`): ไม่เจอ · ลบไฟล์ cookies.txt ในโฟลเดอร์ดาวน์โหลดเองเมื่อเสร็จ | ☐ |
| M5C-NARROW | ซูม 200% (หรือหน้าต่างกว้าง 640 px): dialog เลื่อนอ่านได้ครบ แถบบนหน้าไม่ล้น ไม่มีแถบเลื่อนแนวนอน | ☐ |
```

- [ ] **Step 4: docs/m4-followups.md** (closes "useCookies 422" and "log redactor installed late"; records R3)
**close the `useCookies` 422 item:** replace
```markdown
· `useCookies` (คุกกี้ รอบ C) ยังได้ 422
```
with
```markdown
· `useCookies` ยังได้ 422 โดยตั้งใจ (**ปิดแล้วใน M5 รอบ C:** ไม่มี checkbox ต่อคลิป บัญชีชั่วคราวใช้เองเมื่อจำเป็น BRD #152)
```

**close the user-cookies item:** replace
```markdown
- **คุกกี้ผู้ใช้:** ตอน FR-CK-7 ให้ใช้คุกกี้ต้องใช้แทนเซสชันผู้ชมของการโหลด (ไม่ใช้สองไฟล์พร้อมกัน) เหมือนที่จดไว้ใน M3
```
with
```markdown
- **คุกกี้ผู้ใช้ (ปิดแล้วใน M5 รอบ C):** รอบที่ใช้บัญชีชั่วคราวใส่ jar ในหน่วยความจำแทนเซสชันผู้ชม ไม่ใช้สองอย่างพร้อมกัน และไม่มี `cookiefile` (`core/extractor.py` `_ydl(with_account=...)`)
```

**close the late log-redactor part of the log/tray item:** replace
```markdown
ตัวกรองที่เปลี่ยน path โฟลเดอร์ผู้ใช้เป็น `~` ติดตั้งตอนตั้งค่า log ของแอพ จึงยังไม่ทำงานกับความล้มเหลวที่เกิดก่อนตั้งค่า log ใน `__main__` และในคำสั่ง probe ·
```
with
```markdown
**(ส่วน log ปิดแล้วใน M5 รอบ C)** ตัวกรองที่เปลี่ยน path โฟลเดอร์ผู้ใช้เป็น `~` และตัวกรองค่าคุกกี้ (`yttoolkit/redact.py`) ติดตั้งตั้งแต่สร้าง handler ของ `app.log` ใน `probe.setup_file_log` (ก่อน import lifecycle) และ `serve` ใส่ให้ log บนจอด้วย ·
```

**new M6 item: the diagnostics report is not covered by the canary yet:** replace
```markdown
## เลื่อนไป M6
```
with
```markdown
## เลื่อนไป M6

- **รายงานแจ้งปัญหา (`/api/diagnostics`) ยังไม่มีในแอพ:** เทส canary ของ M5 รอบ C (`tests/integration/test_account_privacy.py`) ตรวจ log, `app.log`, ข่าว SSE, คำตอบของ API, `/health`, `GET /cookies` และไฟล์บนดิสก์ · ตอนทำรายงานใน M6 ต้องเพิ่มรายงานเข้าเทสเดียวกัน (AC-SET-06)
```

- [ ] **Step 5: docs/m5c-prep.md**
**pointer to the approved spec under the header notes:** replace
```markdown
> ข้อความ UI ในโน้ตนี้ ถ้าไม่ได้ยกมาจาก PRD จะติดป้าย **(ข้อเสนอ)** ไว้ ยังไม่ใช่ข้อความจริง
```
with
```markdown
> ข้อความ UI ในโน้ตนี้ ถ้าไม่ได้ยกมาจาก PRD จะติดป้าย **(ข้อเสนอ)** ไว้ ยังไม่ใช่ข้อความจริง
> **อัปเดต 2026-10-06:** พิธตัดสินครบแล้ว ดีไซน์ที่ใช้จริงคือบัญชียูทูปชั่วคราวในหน่วยความจำ (ไม่มีโหมด Firefox ไม่มี Switch) ดูสเปก `docs/superpowers/specs/2026-10-06-m5c-temporary-youtube-account-design.md` และแผน `docs/superpowers/plans/2026-10-06-m5c-temporary-youtube-account.md` · โน้ตนี้เก็บไว้เป็นบันทึกการค้นคว้าของรอบ C
```

- [ ] **Step 6: tests/fixtures/README.md**
**a round C section right after the capture clips line (end of the `capture/` section):** replace
```markdown
- คลิปปลอมใน `downloads/behaviors.json` (ทุกตัว `probeAs` BBB): `CAPTURE0001` ถ่ายได้ปกติ · `CAPTURENO01` (`captureError: E_CAPTURE_UNSUPPORTED`) · `CAPTUREBOT1` (`E_BOT_CHECK`) · `CAPTURENET1` (`E_NETWORK`) · คลิปอื่นทุกตัวถ่ายได้จาก fixture เดียวกัน
```
with
```markdown
- คลิปปลอมใน `downloads/behaviors.json` (ทุกตัว `probeAs` BBB): `CAPTURE0001` ถ่ายได้ปกติ · `CAPTURENO01` (`captureError: E_CAPTURE_UNSUPPORTED`) · `CAPTUREBOT1` (`E_BOT_CHECK`) · `CAPTURENET1` (`E_NETWORK`) · คลิปอื่นทุกตัวถ่ายได้จาก fixture เดียวกัน

## บัญชียูทูปชั่วคราว (M5 รอบ C)
- คลิปปลอมใน `downloads/behaviors.json` (ทุกตัว `probeAs` BBB): `ACCOUNTAGE1` "คลิปจำกัดอายุ" (`needsAccount: E_AGE_RESTRICTED`) · `ACCOUNTMEM1` "คลิปเฉพาะสมาชิก" (`needsAccount: E_VIDEO_PRIVATE`) · `FakeExtractor.probe` ของคลิปที่มี `needsAccount` พลาดด้วยรหัสนั้นเมื่อไม่อยู่ใน `account_scope.signed_in(...)` และผ่านเมื่ออยู่ (`download` และ `fetch_frame_piece` เรียก probe จึงได้กฎเดียวกัน) · `PRIVATEVID1` ส่วนตัวเสมอแม้ใช้บัญชี (บัญชีไม่มีสิทธิ์ดู) · ใช้ใน `test_extractor_account.py`, `test_videos_account.py`, `test_handlers_account.py`, `tests/api/test_videos_api.py`, `test_account_privacy.py`, `test_lifecycle.py` และ `web/e2e/queue-account.spec.ts`
```

- [ ] **Step 7: tests/network_videos.toml** (the clip ID stays empty until Pete picks one; empty = the test skips)
Replace (1):
```toml
[capture]
# M5 รอบ B2 (T15): คลิปของ tests/network/test_capture_network.py · ตรวจข้อมูลคลิปซ้ำก่อนรันถ้าห่างหลายเดือน
landscape = "aqz-KE-bpKQ"  # Big Buck Bunny 635 วิ, CC BY, mp4 avc1 ถึง 1080 และ av01 ถึง 2160 (spike 2026-10-05: 1080p 2.0 MB / 4K 7.5 MB ต่อภาพ)
```
with:
```toml
[capture]
# M5 รอบ B2 (T15): คลิปของ tests/network/test_capture_network.py · ตรวจข้อมูลคลิปซ้ำก่อนรันถ้าห่างหลายเดือน
landscape = "aqz-KE-bpKQ"  # Big Buck Bunny 635 วิ, CC BY, mp4 avc1 ถึง 1080 และ av01 ถึง 2160 (spike 2026-10-05: 1080p 2.0 MB / 4K 7.5 MB ต่อภาพ)

[account]
# M5 รอบ C (T13): คลิปของ tests/network/test_account_network.py · ว่าง = ข้าม · พิธเลือกคลิปจำกัดอายุที่สั้นก่อนรัน
# ไฟล์ cookies.txt ของบัญชีสำรองมาจาก env YT_TOOLKIT_TEST_COOKIES เท่านั้น ห้าม commit
age_restricted = ""
```

- [ ] **Step 8: Network test** — create `tests/network/test_account_network.py` (do **not** run it with the env var set; without `YT_TOOLKIT_TEST_COOKIES` both tests skip before any request):
```python
"""M5 รอบ C กับยูทูปจริง: คลิปจำกัดอายุกับบัญชียูทูปชั่วคราว (spec 6 "Network test" · AC-CK-09)

ต้องได้รับอนุญาตจากพิธก่อนรัน และใช้ไฟล์ cookies.txt ของบัญชีสำรองของพิธเอง (ส่งออกจากหน้าต่างไม่ระบุตัวตนตามขั้นตอนใน dialog):
  - path ของไฟล์มาจาก env YT_TOOLKIT_TEST_COOKIES เท่านั้น ห้ามคัดลอกไฟล์เข้า repo ห้าม commit · ไม่ตั้ง = ข้ามทั้งไฟล์
  - id ของคลิปอยู่ใน tests/network_videos.toml ([account] age_restricted) · ว่าง = ข้ามทั้งไฟล์
  - โหลดเสียงไฟล์เล็กที่สุดของคลิปหนึ่งไฟล์ (ราว 1-5 MB) ลง temp ของ pytest · ไฟล์ cookies.txt ถูกอ่านเข้าหน่วยความจำครั้งเดียว
รันเองด้วย: YT_TOOLKIT_TEST_COOKIES=<path ของ cookies.txt> uv run pytest -m network -q tests/network/test_account_network.py -s
รันเสร็จแล้ว: ออกจากระบบในหน้าต่างไม่ระบุตัวตนแล้วปิดหน้าต่าง (แบบเดียวกับที่แอพบอกผู้ใช้) แล้วลบไฟล์ cookies.txt
ยูทูปตอบ 429 หรือขอยืนยันว่าไม่ใช่บอท = เทสตก ให้รายงานผล ห้ามแก้เทสให้หลวมลง
"""

from __future__ import annotations

import os
import time
import tomllib
from pathlib import Path
from typing import Any

import pytest

from yttoolkit.core.account_scope import signed_in
from yttoolkit.core.download import DownloadChoice, DownloadHooks
from yttoolkit.core.extractor import YtDlpExtractor, parse_account_cookies
from yttoolkit.core.yterrors import YtError

pytestmark = pytest.mark.network

COOKIES_ENV = "YT_TOOLKIT_TEST_COOKIES"
_TOML = Path(__file__).resolve().parents[1] / "network_videos.toml"
CLIP: str = tomllib.loads(_TOML.read_text(encoding="utf-8")).get("account", {}).get("age_restricted", "")
GAP_S = 2  # เว้นช่วงระหว่างคำขอไปยูทูป (แบบเดียวกับ network test อื่น)
MAX_AUDIO_BYTES = 20_000_000


@pytest.fixture(scope="module")
def jar() -> Any:
    path = os.environ.get(COOKIES_ENV, "")
    if not path:
        pytest.skip(f"ตั้ง {COOKIES_ENV} เป็น path ของ cookies.txt ของบัญชีสำรองก่อนรัน")
    if not CLIP:
        pytest.skip("ใส่ id คลิปจำกัดอายุใน tests/network_videos.toml [account] age_restricted ก่อนรัน")
    return parse_account_cookies(Path(path).read_text(encoding="utf-8"))


def _smallest_audio(info: dict) -> DownloadChoice:
    return DownloadChoice("worstaudio[ext=m4a]/worstaudio", False, None, (), None)


def _hooks() -> DownloadHooks:
    return DownloadHooks(on_stage=lambda s: None, on_progress=lambda *a: None, is_cancelled=lambda: False,
                         ffmpeg_location=None)  # fmt: skip


def test_without_the_account_the_clip_is_age_restricted(jar: Any) -> None:
    with pytest.raises(YtError) as info:
        YtDlpExtractor().probe(CLIP)
    assert info.value.code == "E_AGE_RESTRICTED"
    time.sleep(GAP_S)


def test_signed_in_probe_and_a_small_download(jar: Any, tmp_path: Path) -> None:
    ext = YtDlpExtractor()
    workdir = tmp_path / "work"
    workdir.mkdir()
    with signed_in(jar):
        info = ext.probe(CLIP)
        assert info["id"] == CLIP
        time.sleep(GAP_S)
        result = ext.download(CLIP, _smallest_audio, workdir, _hooks())
    size = result.path.stat().st_size
    assert 0 < size < MAX_AUDIO_BYTES
    assert [p.name for p in tmp_path.rglob("*") if p.is_file()] == [result.path.name]  # ไม่มีไฟล์คุกกี้ลงดิสก์
    print(f"{CLIP}: {result.path.name} {size / 1e6:.1f} MB")
    time.sleep(GAP_S)
```

- [ ] **Step 9: Verify**

Run: `cd "$WORKTREE" && uv run pytest tests/unit/test_yterrors.py -q -W error -p no:cacheprovider` (PRD rows still match `MESSAGES`), `cd "$WORKTREE" && uv run pytest -m network --collect-only -q tests/network/test_account_network.py` (2 tests collected, nothing executed), then the full suite (network tests are deselected by `addopts = "-m 'not network'"`). Finally `cd "$WORKTREE" && git grep -n -i "E_COOKIES_UNAVAILABLE\|ใช้คุกกี้กับคลิปนี้\|data/cookies.txt" -- PRD.md BRD.md` prints only the BRD decision #152 mention of the dropped checkbox.

- [ ] **Step 10: Commit**
```bash
cd "$WORKTREE" && git add PRD.md BRD.md docs/acceptance.md docs/m4-followups.md docs/m5c-prep.md tests/fixtures/README.md tests/network_videos.toml tests/network/test_account_network.py && git commit -F- <<'EOF'
docs: M5 round C temporary account in PRD/BRD/acceptance; network test (written, not run)

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
EOF
```

---


## Spec coverage (self-review)

| Spec item | Task(s) |
|---|---|
| Owner decisions C1-C9 | C1 T13 docs · C2 dialog copy T5/T8 · C3 auto-delete + sign-out toast T3/T8/T9 · C4 cookies.txt only, no Firefox T4/T13 · C5 no "คุกกี้" in UI T5 (e2e asserts it, T10) · C6 T3/T9 · C7 buttons T10/T11 · C8 memory only T3/T4/T6/T9 (canary) · C9 no bot-check retry, no checkbox, capture retry, members-only = `E_VIDEO_PRIVATE`, status-only health row T1/T6/T7/T11 |
| §1.1 clip-page error button (no account) / tried copy (account held) | T10 `LoadError` + `showAccountButton`, e2e "error จำกัดอายุ…" and "ถือบัญชีอยู่แล้ว…"; T1 copy; T6 `account_tried` |
| §1.1 failed job row + toast, re-queue with the same params | T10 `FailedRow` (retry mutation) and toast `retryAfterImport` (R5); T12 queue e2e |
| §1.1 sharp capture toast, retry the same `tMs` | T10 `runCapture` + `capture-store.test.ts`; T6 capture retry |
| §1.1 Settings › ขั้นสูง (intro, button, status, "ลบออกตอนนี้"; no switch/source/Chrome note) | T11 + `settings-advanced.spec.ts` |
| §1.2 dialog: warning, private clips, 6 steps, `.txt` ≤ 1 MB read in the browser, buttons by origin, enabled after a file, cancel/Esc send nothing, inline `E_COOKIES_INVALID`, success closes + banner + retries | T8 (`dialogReducer`, `importLabel`, `AccountDialog`), T5 copy, T10 e2e (cancel, Esc, bad file, > 1 MB, success) |
| §1.3 banner on every page, countdown, link-style "ลบออกตอนนี้" without confirm, non-dismissing toast after any deletion, live via SSE in all tabs | T8 banner + `showRemovedToast` + `onAccount`; T5 `applyAccountEvent`; T10 e2e (banner on `/history`, toast still there after 5 s); T12 (grace removal) |
| §1.4 health row "บัญชียูทูป" ok + two texts, no network | T7 `/health` row; T11 `AccountRow` + health e2e |
| §2.1 import (BOM, CRLF, `StringIO`, domains, sign-in cookie, > 1 MB, line-number detail, replace + reset timers), `clear`, `status`, `jar` | T4 parser, T3 service (+ tests listed in Review Focus 1-2) |
| §2.2 expiry 2 h, shutdown, queue-done with 10 min grace (cancel on new job, paused = not idle), interactive use does not start grace, manual delete while running | T3 (`test_expires_two_hours_after_import`, grace tests, `test_interactive_use_never_starts_the_grace`), T9 shutdown + `busy=pending_count`, T6 `mark_used(None)` |
| §2.3 `_ydl(with_account=)`: inject like `_attach_session`, no `cookiefile`, `save_cookies` no-op, never with the visitor session, contract test, forbidden options | T4 `test_attach_account_on_a_real_youtubedl`, `test_traffic_printing_options_are_refused_with_an_account` |
| §2.4 anonymous first, one signed-in retry for probe / jobs / `frames_sharp` / capture, whole job signed in, never other codes, tried copy keeps the account, members-only rules + fixtures, signed-in probes not on disk | T6 (all four call sites), T1 (rules + fixtures), R1/R2/R6 |
| §2.5 `GET/POST/DELETE /cookies` with 409/413/422, body never logged, SSE `account`, settings key retired (old files read, dropped on save), `useCookies` still 422, `E_COOKIES_UNAVAILABLE` removed | T7, T3 events, T5 SSE parsing, T1 |
| §3 no cookie data outside memory; redactor at process start; canary test; `from None`; size cap before parsing; bot-check brake unchanged | T2, T9 `test_canaries_never_leave_memory` (R3), T6, T7 |
| §4 edge cases: expired/revoked, no access, import while paused (allowed, unused until resume), two tabs, re-import, restart, live/geo unchanged, embedded player unchanged | T6 tried copy; T3 re-import + busy; T5/T8 SSE in all tabs; T9 shutdown; T6 `test_other_codes_never_use_the_account`; player untouched |
| §5 docs (PRD, BRD footnote + bot-check rationale + C1-C8, acceptance, m4-followups, m5c-prep) | T1 (PRD §7) + T13 |
| §6 unit, contract, API, privacy, vitest, chromium e2e (error → dialog, cancel, bad file, good file, delete → toast, Settings tab, axe light/dark, 640 px), queue e2e (fail → import → retry → done; grace → toast), network test (env path, toml ID) | T1-T13 as listed; e2e at the final gate |
| §7 Thai copy | T5 `th.account` + T1 `MESSAGES`/`ACCOUNT_TRIED_MESSAGE`, both verbatim; Q1/Q2 open |
| R7 pre-existing `queue-flow.spec.ts:297` failure | T5 Steps 8-9, verified at gate 1 |
| Review Focus 1-5 | T4+T7, T3, T6+T10+T12, T2+T6+T9, T6 (test names in the section) |

Self-review checks run on this plan:
- **Placeholders:** no "TBD"/"TODO"/"similar to Task N"; every code step carries the full code (new files whole, changed files as exact old/new blocks generated from the prototype and checked to rebuild the target file).
- **Prototype run (scratchpad copy of `4b02feb` + every task):** `pytest -q -W error` 3213 passed (44 network tests deselected); web `tsc` app + node, `eslint src e2e` clean, `vitest run` 989 passed; Playwright chromium `account`, `settings-advanced`, `health`, `video`, `settings-general`, `nav` specs passed, queue project `queue-flow` 8/8 (R7 fixed), `queue-batch` + `queue-account` 11/11.
- **Lane isolation run:** each task was applied on top of `4b02feb` plus only the tasks of earlier waves (the exact tree its lane will see) and its own tests run: T1 86, T2 206, T3 69, T4 247, T6 214, T7 109, T9 188, T13 86 Python tests passed; T5, T8, T10, T11, T12 typecheck + lint + vitest (982-989) passed. No task needs a file from a same-wave or later task.
- **Type/name consistency:** `ACCOUNT_CODES` (Python + TS), `ACCOUNT_TRIED_MESSAGE`, `account_tried`, `parse_account_cookies`, `current_jar`/`signed_in`, `with_account_retry`/`AccountGate`, `AccountService(parse, *, publish, busy, on_clear, now, schedule, expiry_s, grace_s)`, `QueueListener.job_queued/job_ended`, `forget_signed_in`, `HandlerDeps.accounts`, `CaptureService(accounts=)`, `AppContext.accounts`, `Services.accounts`, `ACCOUNT_GRACE_ENV`/`account_grace_s`, `ACCOUNT_KEY`, `AccountStatus`/`AccountHealth`/`AccountEvent`, `deleteTime`/`DELETE_TIME_STYLE`, `openAccountDialog`/`accountDialog`, `UseAccountButton`, `REMOVED_TOAST_ID`, test ids `account-banner` / `account-dialog` / `account-status` / `tool-account`, fake clips `ACCOUNTAGE1` / `ACCOUNTMEM1` / `PRIVATEVID1`, env `YT_TOOLKIT_ACCOUNT_GRACE_S` / `YT_TOOLKIT_TEST_COOKIES`: each is defined once (contract + owning task) and used with the same spelling everywhere.
- **Files:** every prototype change belongs to exactly one task per wave (Lane rules table); tests that pinned the old shape are in the owning task (`SETTING_KEYS`, defaults dict, `test_get_exposes_only_cookie_status_fields`, `C14`, the four web `Settings` literals, `events.test.ts` counts, `video.spec.ts` `PRIVATE_MESSAGE`).
- **Review Focus:** five input classes listed, each with named tests in the owning tasks.

---

## Execution handoff

Plan saved to `docs/superpowers/plans/2026-10-06-m5c-temporary-youtube-account.md`. Execute with superpowers:subagent-driven-development: the controller creates one worktree per lane under `.claude/worktrees/m5c-<lane>` on `m5c/t<N>-<slug>` and dispatches one fresh subagent per task with its absolute `WORKTREE` (wave 1 = T1-T5, wave 2 = T6-T8, wave 3 = T9-T13, lanes of a wave in parallel), runs the wave gate procedure between waves (gate 1 adds the R7 Playwright check), the two-stage review per task, then the final gate (build, `npm run e2e` with the queue project serial, `web/dist` commit, live preview for Pete in fake mode with `ACCOUNTAGE1`). Before execution Pete reviews the plan and answers Q1/Q2 (or accepts the defaults); the network test runs only after his approval with his own backup-account export.
