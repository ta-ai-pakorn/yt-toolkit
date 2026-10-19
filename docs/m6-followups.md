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
