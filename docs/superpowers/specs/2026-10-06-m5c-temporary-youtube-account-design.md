# M5 round C: temporary YouTube account (design)

Pete approved sections 1-2 in conversation on 2026-10-06. He asked for sections 3-4 to go straight into this document. This written spec is awaiting his review.

Round C is the last round of M5. It replaces the PRD's "opt-in YouTube cookies" design (FR-CK-1..8, W6 advanced tab, W7 cookie warning, `/cookies*`, cookie row in `/health`) with a **temporary, in-memory sign-in** that the app throws away on its own.

It touches:
- the W2 error states;
- a new dialog;
- the W6 advanced tab;
- a top banner;
- a new in-memory account service;
- the extractor's yt-dlp entry point;
- the retry rules;
- the API;
- `/health`;
- the docs.

Research and sources for this round are in `docs/m5c-prep.md`, written 2026-10-06 from the PRD/BRD, the code at 89cbcc0 and the yt-dlp wiki/issues.

**Why the design changed from the PRD (Pete, 2026-10-06):**
- Pete's real need today is unlisted clips, which already work without signing in.
- He wants round C anyway, for age-restricted and private clips in future.
- Most staff do not know what a cookie is.
- A sign-in should not linger after the job is done.
- Signing out in a normal browser window would also sign the user out of Gmail/Drive. The sign-in therefore happens in an incognito window, and signing out there revokes only that session.

## Owner decisions (2026-10-06)

| # | Decision | Why |
|---|---|---|
| C1 | **Keep round C** for age-restricted, private and members-only clips, even though unlisted clips already work. | Pete chose "ทำตาม PRD เผื่ออนาคต". |
| C2 | **Always recommend a separate backup Google account.** For private clips, the app explains that the channel owner shares the clip with that account by email. YouTube Studio allows about 32-50 emails per clip. | If the account gets locked, the real channel, Gmail and Drive are safe. A fresh backup account cannot see a private clip unless it is shared with it. |
| C3 | **Temporary use only.** The user imports, downloads, and the app deletes the sign-in on its own. The app then tells the user to sign out in the incognito window. | Pete: "โหลดเสร็จแล้วบอกให้ logout ได้เลย จะได้ไม่ค้างไว้". Signing out revokes every exported copy, including the original `cookies.txt` left in the Downloads folder. |
| C4 | **Import a `cookies.txt` file only, exported from a Chrome incognito window. No Firefox mode.** | Pete chose A. Signing out in incognito leaves the normal window's Google sign-in alone. The app cannot read Firefox private-window cookies, and Firefox mode could silently use the staff member's main account. |
| C5 | **The UI never says "คุกกี้".** It says "บัญชียูทูป" / "เข้าสู่ระบบ". Only the file name `cookies.txt` appears, in the export steps. | Pete: most people don't know what a cookie is. |
| C6 | **Auto-delete when the first of these happens:** (a) a queued job that used the account has finished and the queue is idle; (b) the app shuts down; (c) 2 hours have passed since import. | Pete chose A. See 2.2 for the exact rule, including the grace period. |
| C7 | **Entry point: a button on the error itself.** "ใช้บัญชียูทูปชั่วคราว" sits on the clip-page error and the failed-job row. The same flow is also in Settings > ขั้นสูง. After import, the app retries that clip by itself. | Pete chose A. This overrides FR-CK-1's "no shortcut button" rule. |
| C8 | **Memory only.** The sign-in is never written to disk, in any form. | Pete chose A. Closing the app clears it, including a crash or power loss. Every PRD rule about copies on disk becomes moot. |
| C9 | **Planner rulings, shown to Pete in chat with no objection:** never use the account on `E_BOT_CHECK`; no per-clip "ใช้คุกกี้กับคลิปนี้" checkbox; sharp capture (B2) also retries with the account; members-only joins `E_VIDEO_PRIVATE`; the health row shows status only. | See the sections below. |

## 1. User flow (web)

### 1.1 Where the flow starts
- **Clip page (W2), probe failed:** when `GET /videos/{id}` fails with `E_AGE_RESTRICTED` or `E_VIDEO_PRIVATE` and the app holds no account, the existing load-error card shows:
  - the M5 message (copy table, §7);
  - a primary button **"ใช้บัญชียูทูปชั่วคราว"**.
- **Failed job (W4 queue row and its error toast):** for the same two codes, the error toast and the row get the same button. After import, the app re-queues that job (same params). The retry endpoint already exists.
- **Sharp capture (B2):** when a capture fails with one of these codes, the toast gets the same button. After import, the app retries the same `tMs`.
- **Settings > ขั้นสูง (W6, `/settings/advanced`):**
  - a new tab with a short explanation;
  - the button "ใช้บัญชียูทูปชั่วคราว";
  - the current status ("ไม่ได้ใช้บัญชี" / "ใช้บัญชีชั่วคราวอยู่ ลบอัตโนมัติภายใน HH:MM");
  - a secondary button "ลบออกตอนนี้" while active.
  - The PRD's switch, source toggle and Chrome-127 note are dropped.
- **With an account already held**, the same two codes never show the button. They use the "tried with the account" copy instead (§7).

### 1.2 The dialog "ใช้บัญชียูทูปชั่วคราว" (W7)
One dialog, scrolling content, three parts in order:
1. **Warning (danger tint):**
   - the account may be restricted or locked, which also affects Gmail and Drive;
   - use a backup account only, never the channel owner's or your main account;
   - never send the file to anyone.
2. **For private clips:** ask the channel owner to share the private clip with the backup account's email in YouTube Studio. The copy names no Studio menu path, which changes with YouTube's UI and language.
3. **How to export (numbered):**
   1. Open an incognito window (Ctrl+Shift+N).
   2. Sign in to YouTube with the backup account.
   3. In the same tab, open `youtube.com/robots.txt`.
   4. Export `cookies.txt` with a cookies.txt extension. The extension must be allowed in incognito, a one-time setting. The dialog names no extension.
   5. Leave that window open on `robots.txt` and do not browse YouTube in it.
   6. Choose the file below.

- **File picker:** accepts `.txt`, up to 1 MB. The file is read in the browser and sent as text.
- **Buttons:** "ยกเลิก" and **"นำเข้าแล้วลองใหม่"** when opened from an error, or **"นำเข้า"** when opened from Settings. The import button is enabled once a file is chosen.
- **Cancel:** nothing is sent to the server and nothing changes. Esc behaves the same.
- **Import errors:** shown inline under the picker (`E_COOKIES_INVALID` copy). The dialog stays open.
- **Success:** the dialog closes and the banner appears. The originating action is retried: re-probe the clip page, retry the job, or retry the capture.

### 1.3 Banner while the account is held
- **Placement:** a thin bar under the top nav on every page, with an accent tint.
- **Content:** "กำลังใช้บัญชียูทูปชั่วคราว · ลบอัตโนมัติภายใน HH:MM" and a link-style button "ลบออกตอนนี้". The button deletes with no confirm, because it is harmless.
- **After any deletion:**
  - a toast that does not auto-dismiss: "ลบบัญชีออกจากแอพแล้ว · กลับไปกดออกจากระบบในหน้าต่างไม่ระบุตัวตน แล้วปิดหน้าต่าง";
  - the banner disappears.
- **Live updates:** the banner and toast follow server state via the existing SSE stream (§2.5), so an auto-delete shows up in every open tab.

### 1.4 Health row (W6 ตรวจสุขภาพ)
- **Row title:** "บัญชียูทูป".
- **States:**
  - `ok` "ไม่ได้ใช้บัญชี";
  - `ok` "ใช้บัญชีชั่วคราวอยู่ (นำเข้าเมื่อ HH:MM)".
- No network request; no error state, since there is no Firefox to fail to read.

## 2. Backend

### 2.1 Account service (`core/account_session.py`, new)
Holds at most one imported sign-in, in memory only. Thread-safe with one lock.

- **`import_text(text: str) -> AccountStatus`:**
  - Strip a UTF-8 BOM and accept LF or CRLF.
  - Parse as a Netscape cookie file using the extractor's jar class (`yt_dlp.cookies.YoutubeDLCookieJar`), loaded from a string. Load through a temp-free path (`io.StringIO`), not a file. Parsing lives in `core/extractor.py`, because only that module may import `yt_dlp`.
  - Keep only cookies whose domain is `youtube.com` / `.youtube.com` / `google.com` / `.google.com` or a subdomain of those. Drop the rest.
  - Require a sign-in cookie. At least one of `SAPISID`, `__Secure-3PSID`, `LOGIN_INFO` must exist for `.youtube.com`; otherwise `E_COOKIES_INVALID`.
  - Reject more than 1 MB, or a parse failure, with `E_COOKIES_INVALID`. The detail names the error class and line number only, never line content.
  - Replace any held account and reset the timers.
- **`clear(reason)`:** drop the jar reference and the state. Publish a `account` SSE event with the reason (`manual` / `queue_done` / `expired` / `shutdown`).
- **`status()`:** returns `{active: bool, importedAt?, expiresAt?, used: bool}`, with no cookie names or values.
- **`jar()`:** the held jar or `None`. The extractor uses this.
- **Python memory:** dropped references are freed by the GC but not zeroed. This is accepted; the threat model is files on disk and logs, not memory forensics.

### 2.2 Auto-delete rule (C6)
- **(c) Expiry:** 2 h after import. A timer on the app's scheduler calls `clear("expired")`; an injectable clock serves the tests.
- **(b) Shutdown:** the lifecycle shutdown path calls `clear("shutdown")`. A crash needs nothing, because the data lives only in memory.
- **(a) Queue done:** when a **queued job that used the account** reaches a final state (done, failed or cancelled), mark `jobUsed = true`. When the queue has no queued or running jobs and `jobUsed` is true, start a **10-minute grace timer**. Paused-with-queued-jobs counts as not idle.
  - **Grace cancelled:** a new job enqueued during the grace cancels it.
  - **Grace elapses:** `clear("queue_done")`.
- **Ruling:** the 10-minute grace is the planner's choice, not Pete's. It lets someone queue several restricted clips one after another without re-importing. Without it the account would vanish between clicks. Cost if wrong: one constant.
- **Interactive use does not trigger (a):** a probe or capture that used the account does not start the grace. Otherwise the import from a clip-page error would be deleted before the user clicks download. Those uses rely on (b), (c) or the manual button.
- **Manual delete while a job is running:** the running job keeps the jar it already holds until it ends, because a download in flight cannot be revoked. No new request uses the account. The real revocation is the sign-out in the incognito window, which the toast asks for.

### 2.3 Extractor (`core/extractor.py`)
- **New mode:** `_ydl(opts, *, with_session=False, with_account=None)`. When an account jar is passed:
  - inject it the same way `_attach_session` injects the visitor jar (`ydl.__dict__["cookiejar"] = jar`);
  - **do not set `cookiefile`**;
  - replace `ydl.save_cookies` with a no-op. Rotated cookies land in the same in-memory jar object, and nothing is written.
- **One or the other:** account and visitor session are never both attached to the same call (PRD rule).
- **Contract test:** like `test_attach_session_on_a_real_youtubedl`, a test on a real `YoutubeDL` checks:
  - its `cookiejar` and request director hold our jar;
  - the params have no `cookiefile`;
  - closing writes no file.
- **Forbidden options:** `verbose`, `print_traffic`, `dump_pages` and `write_pages` must not be set when the account is attached. Assert this in the same test.

### 2.4 Retry rule
- **Order:** every request first goes **without** the account, as today.
- **When to retry:** if it fails with `E_AGE_RESTRICTED` or `E_VIDEO_PRIVATE` and an account is held, retry **once** with the account. This applies to:
  - probe (`GET /videos/{id}` and the probe inside jobs);
  - video/audio/subtitle download jobs;
  - `frames_sharp`;
  - B2 capture (`fetch_frame_piece`).
- **The whole job stays signed in:** once a job or capture switches to the account, every later yt-dlp call in that job uses it too (probe + download), so the format URLs match.
- **Never on these codes:** `E_BOT_CHECK` (C9: YouTube is watching that IP, and attaching an account raises the lock risk), `E_NETWORK` or any other code. The bot-check queue brake is unchanged.
- **Retry fails with the same code:** use the "tried with the account" error copy (§7) and keep the account. It may simply lack access to this clip.
- **Members-only:** add `yterrors.py` rules for yt-dlp's members-only messages ("members-only", "Join this channel to get access") mapping to `E_VIDEO_PRIVATE`. Add fixtures under `tests/fixtures/errors/`.
- **Cache:** probe results fetched with the account are **not** written to the on-disk probe cache, because format URLs are tied to the session. They are kept in memory for the job only. The clip page fetched with the account shows normally, and a reload re-probes.

### 2.5 API and events
- **Paths:** keep the PRD's path names, with new shapes. Behind the usual token and Origin checks:
  - `GET /cookies` returns `status()`.
  - `POST /cookies/import` takes `{text, acceptWarning: true}`. Without `acceptWarning: true` it returns 409 `E_BAD_REQUEST`. A body over 1 MB returns 413. An invalid file returns 422 `E_COOKIES_INVALID`. Success returns `status()`. The request body is never logged.
  - `DELETE /cookies` calls `clear("manual")` and returns `status()`.
- **SSE:** a new `account` event carries `{active, expiresAt?, reason?}`.
- **Settings:** the `cookies` key in settings and `READ_ONLY` is removed from defaults. Old `settings.json` files that still have it are read without error and the key is dropped on the next save.
- **Jobs:** `useCookies` in `POST /jobs` stays rejected (422). The checkbox is dropped (C9).
- **Removed error code:** `E_COOKIES_UNAVAILABLE` is removed (no Firefox mode).

## 3. Safety and privacy

- **No cookie data anywhere but memory.** No file in `data/`, `work/`, `run/`, output folders, settings export, diagnostics report or temp dirs.
  - **Test:** after an import and a signed-in fake job, walk the data root and temp root and grep for canary values.
- **No cookie names or values in logs, SSE, API responses, error `detail` or the diagnostics report.**
  - **Redactor:** add a log filter that masks `Cookie:`/`Set-Cookie:` header text and the values of known YouTube sign-in cookie names, as a safety net.
  - **Install it at the very start of process startup.** This also closes the m4-followups item that the log redactor is installed too late, so failures before the logging setup are not redacted.
  - **Canary test (AC-SET-06 style):** import a file whose values are unique canary strings, then run:
    - a signed-in probe;
    - a failing signed-in job;
    - a diagnostics report;
    - `/health`;
    - `GET /cookies`.

    Assert the canaries appear in none of: `app.log`, captured SSE, API bodies, the report.
- **yt-dlp output:** our `_YtDlpLogger` already filters, and `verbose`/`print_traffic` are forbidden (§2.3). yt-dlp error strings that echo request headers are mapped through `yterrors.py`, and `detail` keeps only the class name. Signed-in paths raise with `from None` so cause chains don't carry headers.
- **Import endpoint:** the size cap is enforced before parsing. A parse failure never echoes a line.
- **Bot-check brake and queue spacing are unchanged.** Account use only ever adds one retry per clip.
- **Explicit non-goal:** the app cannot delete the user's original `cookies.txt` in Downloads. The toast's sign-out instruction is what makes that file worthless.

## 4. Errors and edge cases

- **Expired or revoked file:** the user signed out early, or YouTube rotated the cookies because the user browsed YouTube in that window. The signed-in retry fails with the same code, so the "tried with the account" copy appears, which suggests re-importing.
- **Account has no access to the private clip:** same as above. The copy names this case.
- **Import while the queue is paused for a bot check:** allowed, but nothing uses the account until the queue resumes, and never for the bot check itself.
- **Two browser tabs:** both get the SSE `account` events and show the same banner.
- **Re-import while active:** replaces the old account and resets the 2 h timer and the grace.
- **App update/restart:** the account is gone (memory). The banner disappears, and the next restricted clip shows the button again.
- **Live clips, geo-blocked clips:** unchanged. They never trigger a signed-in retry.
- **Embedded player:** `youtube-nocookie.com` still cannot play age-restricted clips. The W2 player keeps its existing "เปิดในยูทูป" fallback. Downloads, frames, subtitles and capture work through the account.

## 5. Docs to update (part of the plan)
- **PRD.md:**
  - Replace FR-CK / W6 ขั้นสูง / W7 cookie row / `/cookies*` rows / `/health` cookie row / §7 messages `E_AGE_RESTRICTED`, `E_VIDEO_PRIVATE`, `E_COOKIES_*` with this design.
  - Drop `E_COOKIES_UNAVAILABLE`, Firefox, the switch and `useCookies`.
  - Rewrite AC-CK-01..09 to match.
  - Update the status-code list.
- **BRD.md cookie section:**
  - Re-point the `[^ck-guide]` footnote from yt-dlp.net (a third-party site) to the official yt-dlp wiki/FAQ.
  - Fix the `E_BOT_CHECK` rationale: cookies can pass the bot check, and we refuse to protect the account.
  - Record decisions C1-C8.
- **docs/acceptance.md:** add the round C rows.
- **docs/m4-followups.md:** close "useCookies 422" (it stays 422, by design) and "log redactor installed late" (fixed here).
- **docs/m5c-prep.md:** commit it as the research record for this round.

## 6. Testing
- **Unit:**
  - parser/filter/sign-in detection: BOM, CRLF, foreign domains dropped, missing sign-in cookie, over-size, garbage, no line echo;
  - account service state machine with an injected clock: expiry, grace start/cancel/elapse, interactive use not starting grace, shutdown, re-import;
  - `yterrors` members-only fixtures;
  - retry rule per call site, with a fake extractor where a clip needs the account (fails anonymously, succeeds with the account) and one where the account lacks access;
  - capture retry.
- **Contract:** the real-`YoutubeDL` injection test (§2.3).
- **API:** status/import/delete, 409/413/422 paths, SSE `account` events, settings with a legacy `cookies` key.
- **Privacy:** the canary test and the no-files-on-disk walk (§3).
- **Web (vitest):** the dialog state, banner countdown formatting, and the error-to-button mapping.
- **E2E chromium (mocked, no real jobs):**
  - clip-page error, then the button, then the dialog: Cancel sends nothing; Import with a bad file shows the inline error; a good file closes the dialog, shows the banner and re-probes;
  - "ลบออกตอนนี้", then the toast;
  - the Settings > ขั้นสูง tab;
  - axe light/dark on the dialog and banner;
  - 640 px width.
- **E2E queue project (fake backend, `--workers=1`):**
  - a fake clip that needs the account: queue it, it fails, import, auto-retry, done;
  - after the grace (test hook shortens it), the account clears and the toast shows.
- **Network test (owner-gated, Pete's approval and Pete's own backup-account export):**
  - one age-restricted clip: anonymous returns `E_AGE_RESTRICTED`, signed-in probe + small download succeeds;
  - the cookie file path comes from an env var, never committed;
  - the clip ID goes in `tests/network_videos.toml`.

## 7. Thai copy (proposed — Pete approves during spec review, then it is final)

| Where | Proposed copy |
|---|---|
| Error `E_AGE_RESTRICTED` (no account held) | คลิปนี้จำกัดอายุ ต้องเข้าสู่ระบบยูทูปถึงจะเปิดได้ |
| Error `E_VIDEO_PRIVATE` (no account held) | คลิปนี้เป็นส่วนตัวหรือเฉพาะสมาชิก ต้องเข้าสู่ระบบด้วยบัญชีที่มีสิทธิ์ดู |
| Both codes, after the signed-in retry also failed | ลองด้วยบัญชีแล้วยังเปิดไม่ได้ บัญชีนี้อาจไม่มีสิทธิ์ดูคลิปนี้ หรือการเข้าสู่ระบบหมดอายุแล้ว ลองนำเข้าใหม่ |
| Button on the errors / in Settings | ใช้บัญชียูทูปชั่วคราว |
| Dialog title | ใช้บัญชียูทูปชั่วคราว |
| Dialog warning | บัญชี Google ที่ใช้อาจถูกจำกัดหรือถูกล็อก และกระทบ Gmail กับ Drive ของบัญชีนั้นได้ ใช้บัญชีสำรองเท่านั้น ห้ามใช้บัญชีเจ้าของช่องหรือบัญชีงานหลัก และอย่าส่งไฟล์ให้ใคร |
| Dialog, private clips | คลิปส่วนตัว: ให้เจ้าของช่องแชร์คลิปให้อีเมลของบัญชีสำรองใน YouTube Studio ก่อน |
| Dialog steps | 1. เปิดหน้าต่างไม่ระบุตัวตน (Ctrl+Shift+N) · 2. เข้าสู่ระบบยูทูปด้วยบัญชีสำรอง · 3. เปิด youtube.com/robots.txt ในแท็บเดิม · 4. ส่งออกไฟล์ cookies.txt ด้วยส่วนขยาย (ต้องอนุญาตให้ทำงานในหน้าต่างไม่ระบุตัวตน) · 5. เปิดหน้าต่างนั้นค้างไว้ ไม่ต้องเปิดยูทูปในหน้าต่างนั้น · 6. เลือกไฟล์ด้านล่าง |
| Dialog buttons | ยกเลิก · นำเข้าแล้วลองใหม่ (from an error) / นำเข้า (from Settings) |
| `E_COOKIES_INVALID` (inline) | ไฟล์นี้ใช้ไม่ได้ ตรวจว่าเข้าสู่ระบบยูทูปแล้วก่อนส่งออก แล้วส่งออก cookies.txt ใหม่ |
| Banner | กำลังใช้บัญชียูทูปชั่วคราว · ลบอัตโนมัติภายใน HH:MM · ลบออกตอนนี้ |
| Toast after deletion | ลบบัญชีออกจากแอพแล้ว · กลับไปกดออกจากระบบในหน้าต่างไม่ระบุตัวตน แล้วปิดหน้าต่าง |
| Health row | บัญชียูทูป: ไม่ได้ใช้บัญชี / ใช้บัญชีชั่วคราวอยู่ (นำเข้าเมื่อ HH:MM) |
| Settings > ขั้นสูง intro | ใช้เมื่อต้องโหลดคลิปจำกัดอายุ คลิปส่วนตัว หรือคลิปเฉพาะสมาชิก แอพเก็บการเข้าสู่ระบบไว้ชั่วคราวและลบเองเมื่อโหลดเสร็จ |

Copy rules: buttons start with a verb; no "กรุณา"; no "!".

## Out of scope (round C)
- Firefox or Chrome direct cookie reading.
- Persisting the sign-in across restarts.
- A "test the sign-in" button that makes requests (C9).
- Using the account to pass bot checks.
- Other sites' sign-ins (TikTok etc., backlog).
- Naming a specific cookies.txt extension in the app (README in M6 may).
