# M1 Follow-ups Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task.

**Goal:** Close every item in `docs/m1-followups.md` and the deferred minors from the M1 reviews, so M2 starts from a clean base.

**Architecture:** This plan changes no architecture. It hardens the existing M1 code: lifecycle, start.bat, platform, API, tools, web, and CI. Each task is a self-contained group of fixes with its own tests.

**Tech Stack:** Same as M1: Python 3.13 + uv + FastAPI + pystray, and React 19 + Vite 8 + shadcn Base UI. CI runs on GitHub Actions.

**Note on format:** These are fixes to code that already exists and is well tested. Each task therefore gives exact behaviour, exact strings, and the required tests, but not full code. Implementers read the existing code first and match its style.

## Global Constraints
(Same as the M1 plan. These are copied from `docs/superpowers/plans/2026-09-28-m1-foundation.md`, and all of them still bind.)
- Python `3.13`, managed with `uv` only.
- The server binds to `127.0.0.1` only.
- `Host` must be `127.0.0.1:<port>` or `localhost:<port>`, otherwise respond `421`. POST/PUT/PATCH/DELETE need a matching `X-Toolkit-Token` and a matching `Origin`, otherwise respond `403`.
- API error shape: `{"error": {"code": "E_...", "message": "<Thai>", "detail": "<technical>|null"}}`.
- Call external programs with an argument list. Never use `shell=True`.
- Use `pathlib` for paths.
- Only `yttoolkit.platform` may check the operating system. This includes `sys.platform`, `os.name`, `platform.system()`, `subprocess.CREATE_NO_WINDOW`, and `.exe` naming.
- User-facing text is Thai. Buttons start with a verb. No "กรุณา". No exclamation marks.
- All web UI strings live in `web/src/i18n/th.ts`.
- Studio Dark theme. Thai body text line-height ≥ 1.6. At most one primary (amber) button per page.
- Do not use Magic UI, Aceternity, or Animate UI.
- Every commit ends with `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.
- `web/dist/` is committed and must be rebuilt whenever web source changes. CI checks that it is fresh.
- Lint must report 0 errors and 0 warnings. Test output must be free of warnings.

---

### Task 1: Lifecycle hardening + readiness command

**Files:** `src/yttoolkit/lifecycle.py`, `src/yttoolkit/__main__.py`, `src/yttoolkit/platform/{windows,macos}.py` (try_lock only), `tests/unit/test_lifecycle.py`, `tests/unit/test_platform.py`, `tests/unit/test_runstate.py`

1. **Remove a stale app.json on start.** In `start()` and in `serve()`, delete any existing `run/app.json` (`runstate.clear`) right after the `run/app.lock` lock is acquired. Holding the lock proves no other instance is running, so the file must be stale.
2. **Let `start()` take over if the lock frees up.** `start()` currently waits up to 20 s when it cannot get the lock, polling `find_running`. On each poll, also call `plat.try_lock` again. If that succeeds, continue as the owning instance (clear the stale app.json and call `run_app`) instead of giving up.
3. **Kill only the process that app.json still names.** In `stop()`, right before the force-kill, re-read `run/app.json`. Kill only if it still exists and `pid` and `started_at` match the values read at the start of `stop()`. Otherwise print "YT Toolkit ไม่ได้เปิดอยู่" and do not kill. The final unconditional `runstate.clear` must also run only when the file still matches, so it never deletes a newer instance's app.json.
4. **Clean up after a startup timeout.** If `run_app`'s `wait_until_ready` times out, stop the uvicorn server (`should_exit`), join its thread briefly, release the lock, clear app.json, log the error, and return non-zero.
5. **Handle an unopenable lock file.** In both platforms, `try_lock` must catch an `OSError` from opening the lock file. Log it at warning level, return `None`, and leave no file handle open.
6. **Rotate the log.** `setup_file_logging` must use `logging.handlers.RotatingFileHandler(maxBytes=1_000_000, backupCount=3, encoding="utf-8")`.
7. **Add the readiness command.** Add the CLI subcommand `yttoolkit wait [--timeout SECONDS]` (default 25). It polls `find_running(paths, plat)` every 0.5 s.
   - When an instance answers, print `เปิด YT Toolkit แล้ว ที่ http://127.0.0.1:<port>` and exit 0.
   - On timeout, print `เปิดโปรแกรมไม่สำเร็จ ดูรายละเอียดได้ที่ <absolute path of run/logs/app.log>` and exit 1.
   - `--timeout 0` checks exactly once.
8. **Tests.** Each numbered item gets at least one test:
   - A stale app.json is cleared on start.
   - The start wait loop takes over when the lock frees.
   - The pid-mismatch re-read prevents a kill.
   - The timeout cleanup releases the lock.
   - The unopenable lock returns None. Use a directory path, or monkeypatch `open`.
   - The rotating handler is used.
   - `wait` succeeds, times out, and handles `--timeout 0`.
   - `now_iso` format: an ISO-8601 UTC string with a timezone.

### Task 2: start.bat / stop.bat robustness

**Files:** `start.bat`, `stop.bat`, `README.md`, `docs/acceptance.md`

Keep both files UTF-8 without BOM, with CRLF line endings in the working tree. Verify this with `file` and `head -c3 | xxd`.

1. **start.bat: show whether the app really opened.** After `start "" ".venv\Scripts\pythonw.exe" -m yttoolkit start`, run `".venv\Scripts\python.exe" -m yttoolkit wait --timeout 25`. If it exits 0, close the window after 2 s (`timeout /t 2 >nul`). If it fails, go to a new label `:startfail`. That label prints the wait command's message (the command already printed it) plus `ถ่ายภาพหน้าจอนี้ส่งให้ผู้ดูแล แล้วกดปุ่มใดก็ได้เพื่อปิดหน้าต่าง`, then `pause >nul` and `exit /b 1`.
2. **start.bat: don't fail just because the app is already running during an update.** Before `uv sync`, if `.venv\Scripts\python.exe` exists and `python -m yttoolkit wait --timeout 0 >nul` exits 0, the app is already running. In that case:
   - Skip `uv sync`.
   - Print `      โปรแกรมเปิดอยู่แล้ว ถ้าเพิ่งมีอัปเดต ให้ปิดโปรแกรมแล้วเปิดใหม่เพื่อใช้เวอร์ชันล่าสุด`.
   - Continue to step 4/4. The `start` command opens the browser to the running instance.
3. **Both files: restore the console code page.** Save the current code page before `chcp 65001`. For example: `for /f "tokens=2 delims=:." %%a in ('chcp') do set "_OLDCP=%%a"`, then run `chcp %_OLDCP% >nul` before every exit. Also `set "PYTHONUTF8=1"` so Python output matches the UTF-8 console.
4. **README.md:**
   - The "สำหรับผู้พัฒนา" block must say to start the backend before `npm run dev`, and to restart vite if the backend port changes.
   - Also say that the log is at `run/logs/app.log`.
5. **docs/acceptance.md:** Under AC-LIFE-02, add a row checking the new failure screen: rename `.venv\Lib\site-packages\fastapi` temporarily, double-click start.bat, confirm the failure screen shows the log path, then rename the folder back. Do not tick any boxes.
6. **Verify by hand.** You cannot double-click the files.
   - Run `cmd.exe //c stop.bat` while the app is not running.
   - Run the `wait --timeout 0` command directly and check its exit code.
   - Report what you did honestly. Do not run start.bat (it runs `git pull`).

### Task 3: Platform boundary + platform tests

**Files:** `src/yttoolkit/platform/{base,windows,macos}.py`, `src/yttoolkit/core/tools.py`, `src/yttoolkit/lifecycle.py`, `tests/conftest.py` (FakePlatform), `tests/unit/test_platform.py`, `tests/unit/test_tools_status.py`

1. **Add two Platform protocol members and implement them on both platforms and on FakePlatform:**
   - `popen_flags: int`. Windows: `subprocess.CREATE_NO_WINDOW`. macOS: `0`.
   - `exe_name(name: str) -> str`. Windows appends `.exe`; macOS returns `name` unchanged.
2. **Remove every OS check outside `platform/`:**
   - Replace `getattr(subprocess, "CREATE_NO_WINDOW", 0)` in `tools.py` and `lifecycle.py` with `plat.popen_flags`. Thread `plat` through where it is needed. Keep call signatures minimal, and default to `platform.current()` only at the outermost call sites.
   - `find_js_runtime` and `find_ffmpeg` must use `plat.exe_name("deno")` / `plat.exe_name("ffmpeg")` instead of trying hard-coded `.exe` names.
   - Also remove any other `.exe` literals outside `platform/`, except in the ffmpeg zip member names `ffmpeg.exe`/`ffprobe.exe`: that zip is Windows-only by definition, and its code lives under `install_ffmpeg_windows`.
   - `git grep -nE "sys\.platform|os\.name|platform\.system|CREATE_NO_WINDOW|\.exe\b" -- src` must match only `src/yttoolkit/platform/` plus those zip member names.
3. **Tidy the Windows known-folder code.** Set `argtypes`/`restype` for `SHGetKnownFolderPath` and `CoTaskMemFree`, and load `shell32`/`ole32` once at module level, lazily on first use so that importing on macOS still works.
4. **Tests:**
   - `open_folder` and `reveal` on both platform classes: monkeypatch `subprocess.Popen`/`run` and assert the exact argument list, with no `shell=True`.
   - `popen_flags` and `exe_name` on both.
   - `find_js_runtime` uses `exe_name`. Update the existing test that covered the deno/deno.exe fallback.
5. **Health status tidy-ups:**
   - Make the `disk_status` message format consistent: one format, `เหลือ {n:.0f} GB`, in both the ok and warn branches.
   - When no JS runtime is found, the status must have `name=None` and the Thai message `ไม่พบตัวช่วยของ yt-dlp (deno)`. Keep the status value it has today.
   - Fix the `collect_health` type hint for its network parameter.

### Task 4: API envelope, security edges, ffmpeg install edges, yt-dlp auto-update

**Files:** `src/yttoolkit/app.py`, `src/yttoolkit/api/{errors,security,static,routes}.py`, `src/yttoolkit/core/tools.py`, `src/yttoolkit/lifecycle.py` (`ensure_ffmpeg`), `.github/workflows/update-ytdlp.yml`, `uv.lock`, `pyproject.toml`, `PRD.md` (error table), tests under `tests/api/` and `tests/unit/`

1. **Global exception handlers in `create_app`.** Every error body must use the envelope:
   - Starlette `HTTPException` 404 → `E_NOT_FOUND`, message `ไม่พบสิ่งที่ขอ`.
   - `RequestValidationError` → 422 `E_BAD_REQUEST`, message `ข้อมูลที่ส่งมาไม่ถูกต้อง ลองรีเฟรชหน้าเว็บ`.
   - Any other `HTTPException` keeps its status, with code `E_HTTP_<status>` and the same Thai message as `E_BAD_REQUEST`.
   - Unhandled `Exception` → 500 `E_UNKNOWN`, message `มีบางอย่างผิดพลาด ถ่ายภาพหน้าจอนี้ส่งให้ผู้ดูแล`, with the exception logged with its traceback.
   - Add `E_NOT_FOUND` and `E_BAD_REQUEST` rows to the PRD section 7 error table.
2. **Redact the home folder in `detail`.** `error_body`/`error_response` must replace every occurrence of the user's home directory (`str(Path.home())`, compared case-insensitively on the path prefix) with `~` in `detail` before sending it. Test this with a detail string containing the home path.
3. **Security middleware edges (`security.py`):**
   - `websocket` scopes: apply the same Host check. Also require an `Origin` that is in the allowed set. If either check fails, send `{"type": "websocket.close", "code": 1008}` and do not call the app.
   - Other non-http, non-websocket scopes (for example `lifespan`) pass through unchanged.
   - Duplicate `Host`, `Origin`, or `X-Toolkit-Token` headers are rejected: 421 for Host, 403 for the others. Do not let the last one win.
   - Tests for each case.
4. **Do not serve a raw copy of `index.html` (`static.py`).** Before returning a `FileResponse` for a validated candidate, check whether it is the same file as `dist/index.html` (`os.path.samefile`, wrapped for `OSError`). If it is, serve the token-injected index instead. Test with `/index.html.` and an uppercase variant. The 8.3 short name cannot be created reliably in tests; the samefile check covers it by design.
5. **Routes:**
   - Add a return annotation to the install route.
   - Add a direct test that `POST /api/tools/ffmpeg/install` without a token returns 403 with the envelope.
6. **ffmpeg install edges (`tools.py`):**
   - At the start of an install, while holding the lock, remove leftover `bin/*.part` files.
   - Replace `ffprobe` first and `ffmpeg` second. The presence of `ffmpeg` means the install is complete.
   - `ensure_ffmpeg` in lifecycle catches `Exception` (not only `ToolInstallError`) and logs it with its traceback, so the daemon thread never dies with a raw traceback.
   - Tests for the `.part` cleanup and the replace order.
7. **yt-dlp auto-update (BRD section 7, "อัปเดต yt-dlp": GitHub Actions checks daily and commits an updated `uv.lock`).** Create `.github/workflows/update-ytdlp.yml`:
   - Triggers: `schedule: cron "17 2 * * *"` and `workflow_dispatch`.
   - `permissions: contents: write`.
   - Runs on `windows-latest`.
   - Steps: checkout `main`, then setup-uv (`astral-sh/setup-uv@v10.2.0`, since there is no floating v10 tag), then `uv lock --upgrade-package yt-dlp --upgrade-package yt-dlp-ejs`.
   - If `uv.lock` did not change, stop.
   - If it changed, run `uv sync --frozen` and `uv run pytest -q`. Only if the tests pass, commit `uv.lock` as `github-actions[bot]` with the message `chore: update yt-dlp` followed by a blank line and the Co-Authored-By trailer, then push to `main`.
   - Also run this upgrade locally now so the lock is current. The health check currently warns because the locked yt-dlp is older than 30 days. Run the full test suite after the upgrade.
8. **pyproject:** set `description = "เครื่องมือจัดการสื่อจากยูทูปที่รันบนเครื่องของคุณ"`.

### Task 5: Web fixes

**Files:** under `web/src/` (`lib/api.ts`, `lib/api.test.ts`, `i18n/th.ts`, `pages/home.tsx`, `pages/settings.tsx`, `pages/settings/{health-panel,about-panel}.tsx`, new `pages/settings/use-health.ts`, `components/layout.tsx`, `components/ui/spinner.tsx`), `web/index.html`, `web/e2e/*`, `web/playwright.config.ts`, `web/README.md`, `web/dist`

1. **`api()` Content-Type.** Set `Content-Type: application/json` only when `typeof init.body === "string"` and the caller has not already set a Content-Type. Test both cases: a `FormData` body gets no forced header, and a caller-supplied header is kept.
2. **Tests** for `readToken(doc)` (meta present and absent), `fill()` (known and unknown keys), and HEAD requests not sending the token.
3. **Move `useHealth` into `pages/settings/use-health.ts`.** Import it from both panels, and remove the file-level `eslint-disable` in health-panel.
4. **ffmpeg install result.** `onSuccess(status)`: if `status.status === "ok"`, show `toast.success(th.health.installed)`. Otherwise show `toast.error(status.message ?? th.errors.unknown)`. Either way, invalidate the health query.
5. **Shutdown:**
   - On success, call `toast.dismiss()` before showing `ShutdownScreen`.
   - The shutdown button shows `<Spinner />` while pending, the same as the install button.
6. **Health row description.** Replace the `detail(...) || " "` placeholder with a real empty-safe render: only render `ItemDescription` when the detail text is non-empty.
7. **Settings nav link.** Render the header "ตั้งค่า" as a real link, with no `role="button"`: `<NavLink to="/settings/health" className={buttonVariants({ variant: "ghost", size: "sm" })}>`. Import `buttonVariants` from `@/components/ui/button`, and keep the icon and text.
8. **Theme before hydration.** Add a small inline script in `web/index.html` `<head>`. It reads `localStorage.getItem("theme")` inside a try/catch (the storage key is `"theme"`, the ThemeProvider default). It resolves `system` through `matchMedia("(prefers-color-scheme: dark)")` and adds `dark` or `light` to `document.documentElement` before first paint.
9. **Spinner label.** Add `th.common.loading = "กำลังโหลด"` and use it for the Spinner's `aria-label`. This is a small edit to generated `ui/spinner.tsx`, which is acceptable.
10. **Home page:**
    - Clear `note` whenever the textarea value changes.
    - Make the paste listener always call the latest `analyze`, using React 19's `useEffectEvent` if the installed React exports it, or a ref-to-latest pattern otherwise. The effect deps stay honest.
    - Change the heading to `leading-relaxed`, and the usage note from `text-xs` to `text-sm`.
11. **e2e:**
    - The about test matches the version with `/\d+\.\d+\.\d+/` instead of the hard-coded `0.1.0`.
    - Add Playwright `globalSetup` that deletes the tmp data root (`os.tmpdir()/yt-toolkit-e2e`) before the run.
    - Existing e2e tests must still pass, including the hotkey guard added in the fix wave.
12. **Replace `web/README.md`** (Vite template text) with 3 lines in Thai, pointing to the root README's "สำหรับผู้พัฒนา" section.
13. Run `npm run typecheck && npm run lint && npm test && npm run build && npm run e2e`, and commit the rebuilt `web/dist`.

### Task 6: CI + docs close-out

**Files:** `.github/workflows/ci.yml`, `docs/m1-followups.md`, `README.md` (if needed)

1. **ci.yml:**
   - Pin the `web` job to `ubuntu-24.04` so the dist-freshness check does not break when `ubuntu-latest` moves to 26.
   - In `e2e`, cache Playwright browsers with `actions/cache@v5` (check the latest major with `gh api repos/actions/cache/releases/latest`). Key the cache on `web/package-lock.json`, with path `~\AppData\Local\ms-playwright` on Windows. Keep `npx playwright install chromium`, which is fast when cached.
2. **Rewrite `docs/m1-followups.md`** into a short record:
   - What was closed, as one line per group.
   - What intentionally remains and why. For example, AC items that need manual checks, and FR-SET-3's "ตรวจหาอัปเดต" button, which is scheduled for M4/M6.
   - Write it in Pete's documentation voice: Thai, ผม/เรา, ending with ครับ.
3. Push the branch and get CI fully green, including the new workflow file's syntax (validate it with `gh workflow view update-ytdlp.yml` after the push, or with actionlint if available). Do not trigger the update workflow on main from the branch.
