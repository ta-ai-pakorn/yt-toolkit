# M6 follow-ups (after v1.0 round D1)

Items found during M6 round D1 that were judged safe to leave for later. None of them block v1.0.

## Abrupt stops (audit 2026-10-16, the 3 must-fix items are done)

- **C2:** check that `uv.exe` actually runs, not only that it exists.
- **B2:** a watchdog for a dead server thread.
- **A2:** neutral wording for E_INTERRUPTED when the PC lost power and nobody pressed stop.
- **A4:** a power cut right after a finished move can roll back the `done` commit (`synchronous=NORMAL`). The job then shows interrupted while the file is already in the output folder, a retry makes "<name> (2)", and stats are off by one. Option: `synchronous=FULL` for the job-finish commit.
- **A5:** no database `quick_check` or quarantine on start.
- **C5:** start.bat's TEMP self-copies can pile up if the window is closed early.
- **E1:** after sleep or resume, restart the network retry budget when the wall clock jumps by 60 s or more.
- **Ffmpeg shims:** a Chocolatey or Scoop `ffmpeg` shim, or Git's `cmd\git.exe`, can start the real exe before the app adds the shim to its job, so that grandchild can outlive the app. Our own `bin/ffmpeg` is not affected.
- **Already-stuck installs:** installs stuck under the old start.bat have no marker, so the new repair cannot see them. Fix by hand once: delete `.git\index.lock`, then `git reset --hard origin/main`.
- **Non-fast-forward repair:** if the repair finds that `origin/main` is not a fast-forward, it goes back to the old version and leftover files keep later updates skipped. This needs an admin, as before.

## CI and tests

- **`queue-flow.spec.ts:94`:** the queue sheet did not appear after a reload, once on CI. This is not reproduced. CI now keeps traces of failed tests (no screencast), so the next failure shows the cause.
- **Port overlap:** `tests/integration/test_queue_serve.py` uses ports 8850-8869. Do not run a debug server in that range during a pytest run.

## Server

- **10054 resets:** a socket handle leaks on each connection reset from a closed browser tab (CPython 3.13 proactor `_call_connection_lost`), and that can add up to 3 s to shutdown. Live connections are not affected. The console still prints the 10054 tracebacks; `ConnectionResetNoiseFilter` already removes them from `app.log`.

## UI

- **Fake mode:** a link that is not a fixture shows "คลิปนี้ไม่มีให้ดู". Fake mode should say clearly that only the sample clips work.

## From CI flake round 3

- **Null clip data without an abort:** a 200 whose body cannot be read (backend reset mid-response) still makes `api()` return `null`, and `home/queries.ts` / `videoQuery` can write that into `["video", id]`. That is the same crash class as the fixed abort case. Fix: write only when the result is not `null`, or return `null` only for a truly empty body. This is rare on 127.0.0.1.
- **Blank page when an entry file fails to load:** if a file the entry script needs fails to load (local socket starvation from antivirus or VPN filters, or the backend dying mid-load during an update), staff see a blank white page with no message. `importWithReload` only covers lazy chunks. Option: a tiny inline script in `index.html` that reloads once (guarded by `sessionStorage`) and then shows a one-line Thai message telling staff to press F5. The message is new copy, so Pete has to approve it.
- **`account.spec.ts:186/190`:** the test asserts the cancel mechanism, not the symptom. Wait for the stale request to settle, then assert that the banner stays gone.
- **HTTP vs SSE ordering with two tabs:** a late import response can overwrite an SSE "inactive" event. This was already in main before this round.

## Public repo (decided 2026-10-21)

- **Replace the real third-party fixtures with synthetic ones,** or with clips that pakorn owns. This covers the KOD THAI storyboards `tests/fixtures/storyboard/88o5Sk8_m1Y/M0-M8.jpg` (they show the host's face) and that clip's auto-captions, the Thairath auto-captions and description, and the "Me at the zoo" subtitles. Big Buck Bunny is CC-BY and can stay. The old files stay in git history; Pete decided not to rewrite history.
- **Commit email:** new commits could use the GitHub noreply address instead of the company address. All past commits keep the company address.
