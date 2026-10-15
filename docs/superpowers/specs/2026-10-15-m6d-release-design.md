# M6 round D1: v1.0 release preparation (design)

Pete approved this design in conversation on 2026-10-15 (Q1-Q5 below, then the five design sections). Round D is split:
- **D1** is this spec: code, docs and tests that Claude and subagents can do.
- **D2** is Pete's manual sweep on a real Windows machine, using the checklist D1 produces. The `v1.0.0` tag is created only after D2 passes.

Requirements: PRD M6 row `PRD.md:919` (a11y, README Windows, GitHub Actions, every AC on Windows plus the numbers in §8); NFR table `PRD.md:872-879`; Definition of Done `PRD.md:921-926`; BRD M6 exit criteria `BRD.md:767` and `BRD.md:47`; FR-SET-3 `BRD.md:229`, `:736`; `docs/m3-followups.md:60-62` (focus ring); `docs/m5c-prep.md:84-85` (cookies.txt guide); `docs/m5a-followups.md:24` (flaky e2e). Code facts were checked at HEAD `62ce7e4` (branch `main`).

## Owner decisions (2026-10-15)

| # | Decision | Where |
|---|---|---|
| D1 | **No "ตรวจหาอัปเดต" button** (Q1 = A). Updating means closing the app and opening it again: `start.bat` already runs `git pull` on every launch, and `update-ytdlp.yml` bumps yt-dlp daily. BRD FR-SET-3 and `:736` are rewritten to say so, citing Pete 2026-10-15. | §2.4 |
| D2 | **README images are app screenshots taken automatically** from fake mode by a script, stored in `docs/images/` (Q2 = A). Install steps are numbered text. Screenshots are captures of the app, not generated images. | §2.2 |
| D3 | **Two documents** (Q3 = A). `README.md` is the staff guide only, written in Pete's article voice (ผม / ครับ, readers "คุณ"). Developer material moves to `docs/development.md`. | §2.1, §2.3 |
| D4 | **a11y scope** (Q4 = A): fix the focus ring to ≥ 3:1 in both themes; add one keyboard-only e2e journey across W1-W7; recheck health-page colours; add a short NVDA check to the D2 list. | §1 |
| D5 | **D2 checklist is short** (Q5 = A): about 30-40 items that automation cannot cover. In `docs/acceptance.md`, each row that an automated test already proves gets a pointer to that test. | §5 |
| D6 | Controller rulings Pete saw and did not change: version `1.0.0`; a Thai `CHANGELOG.md` in Pete's voice with the DB v3 downgrade warning; fix the flaky e2e tests at the root cause; tag `v1.0.0` only after D2. | §3, §4 |

## Global constraints

- **C1** No new runtime dependencies (Python or npm). Dev-only tooling is allowed only if an existing dev dependency cannot do the job; prefer Playwright, which is already installed.
- **C2** Thai UI copy: no new UI strings except where §1 needs an accessible name that does not exist yet. Any such string must be listed in the plan for Pete. Buttons start with a verb, no "กรุณา", no "!".
- **C3** Docs voice:
  - `README.md` and `CHANGELOG.md` use Pete's article voice: self "ผม", readers "คุณ" or "เพื่อนๆ", sentences end with "ครับ".
  - The audience is non-technical staff: plain language, no jargon without a one-line explanation, no command a staff member must type except the documented install steps.
  - `docs/development.md` keeps the existing developer tone.
- **C4** Privacy: screenshots come from fake mode only (`YT_TOOLKIT_FAKE=1`). No real account, cookie, token, absolute user path or real person's data may appear in any image or doc. Where a screenshot would show the output folder path, the script sets a neutral fake output dir, or the plan masks it.
- **C5** README content rules:
  - The cookies.txt guide must say why a private (incognito) window is used and what happens without one. Without it the account file expires quickly and staff would think the app is broken.
  - It must not name a specific browser extension (`docs/m5c-prep.md:84-85`).
- **C6** a11y: the focus indicator must have a contrast ≥ 3:1 against the surfaces it sits on, in both light and dark (WCAG 2.2 non-text contrast). Text contrast stays ≥ 4.5:1 (BRD `:583`). axe serious/critical stays at zero on every spec that runs it.
- **C7** Flaky tests are fixed at the root cause (a real wait on the state that matters), never by adding retries, raising timeouts alone, `test.fixme` or skipping.
- **C8** Usual repo rules: no `shell=True`; only `yttoolkit.platform` checks the OS; `yt_dlp` only in `core/extractor.py`; LF; commit trailer `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`; `web/dist` only at the final gate; never use port 8787; chromium e2e never creates real jobs except in the existing `queue` project; Playwright with `--workers=1` while developing.

## 1. Accessibility

### 1.1 Focus ring (`web/src/index.css`, `web/src/components/ui/*`)

- Today `--ring: #f5b942` is used as `focus-visible:ring-ring/50` (50 % alpha) in 14 shadcn components, which measures about 1.5:1 (`docs/m3-followups.md:60-62`).
- The fix changes the token(s) and/or the shared ring class so that every focus-visible indicator reaches ≥ 3:1 against `--background`, `--card`/`--popover` and `--muted` in both themes.
  - Prefer one token change plus removing the `/50` alpha in the shared component classes, over per-component overrides.
  - A light-theme `--ring` darker than the brand amber is acceptable. The plan picks exact values and shows the measured ratios.
- **Test:** a chromium e2e focuses a representative button, input, tab and select in both themes. For each it reads the computed ring colour and the background behind it, and asserts a contrast ≥ 3:1. The plan supplies the contrast helper; there is no new dependency.

### 1.2 Keyboard-only journey (`web/e2e/keyboard-journey.spec.ts`, new)

One test, using only `page.keyboard`, with no `click()` after `goto`. It goes through these steps in fake mode with writes mocked as other chromium specs do:
1. paste a link in W1 and analyse it (Enter);
2. open the clip page (W2) and move between its tabs with the arrow keys;
3. open the download tab and start a download. The POST is mocked; no real job is created;
4. reach the queue dock (W5) and expand it;
5. open history (W4);
6. open settings (W6) and switch tabs with the arrow keys;
7. open the "ล้างสถิติ" or "ล้างข้อมูลชั่วคราว" confirm dialog (W7), check that focus moves into it, close it with Escape, and check that focus returns to the trigger.

At each step it asserts that `document.activeElement` is the intended control and that it is visible (`:focus-visible` matches). If a step cannot be reached by keyboard, that is a bug to fix in this round, not a test to bend. The plan lists the exact key sequence after reading the pages.

### 1.3 Health page colours

- Run axe on `/settings/health` in both themes, including the warn and error row states, which already have fake-mode triggers or mocks.
- If a contrast violation shows, fix the token or class.
- If none shows, record "no issue found" in the plan report and close the note.

## 2. Docs

### 2.1 `README.md` (staff guide, Pete's voice)

Sections, in order:
1. **What this app is**: one paragraph.
2. **Install on Windows (once)**: numbered steps, kept from `README.md:6-12` and expanded so a staff member can follow them alone:
   - install Git with the one documented command;
   - accept the GitHub invite;
   - clone;
   - double-click `start.bat`;
   - what the first run looks like and how long it takes (≤ 10 min, BRD `:47`).
3. **Open and close the app; updating** (D1): closing and reopening updates the app automatically; what `stop.bat` is for.
4. **Tour, with screenshots** (§2.2): paste a link, the clip page (frames, subtitles, download), the queue, history, settings.
5. **Where files go**: the output folder and how to change it.
6. **Clips that need a YouTube account (age-restricted or private)**: the temporary-account flow in plain steps, with the cookies.txt export from a private window (C5). Point to the in-app dialog the app already shows; do not duplicate its text, and do not contradict it.
7. **When something goes wrong**: the health page, the "คัดลอกข้อมูลแจ้งปัญหา" button, and who to send the report to (the admin). Keep it generic; do not name a person.

Each Thai UI label quoted in the README must match `web/src/i18n/th.ts` exactly. The plan lists them, and a test greps for them.

### 2.2 Screenshots (`scripts/screenshots.ts` or a Playwright project, `docs/images/*.png`)

- A script, run on demand rather than in CI, starts the app in fake mode on a free port and drives Playwright to each tour screen at 1280 × 800 in the dark theme. It writes the PNGs into `docs/images/`.
- The script is documented in `docs/development.md` as one command.
- Images stay small: PNG, one per tour step, about 6-8 images. They must stay under 300 KB each, by cropping to the relevant area where useful.
- The images are committed. They hold fake-mode data only (C4).

### 2.3 `docs/development.md`

Holds everything removed from the README: dev commands (`README.md:26-41`), the fake-mode table (`:42-79`), the frames note (`:80-81`), the screenshot command and a pointer to CI. The README links to it once, at the bottom.

### 2.4 BRD / PRD edits

- BRD `:229` (FR-SET-3) becomes: updating = close and reopen (`start.bat` runs `git pull` + `uv sync` on launch), no in-app button, Pete 2026-10-15.
- BRD `:736` (emergency update) gets the same note.
- PRD: wherever an update button is mentioned, align it the same way. The plan greps for "ตรวจหาอัปเดต".

## 3. Release preparation

- Bump `pyproject.toml` `version` to `1.0.0`. Update `uv.lock` if it records the project version (`uv lock`). The About panel reads the version through `importlib.metadata`, so it changes by itself; check the existing test that pins the version string, if any.
- Add `CHANGELOG.md` (Pete's voice, Thai) with a `1.0.0` entry, made of:
  - a short "what you can do" summary by area (download, frames, subtitles, notes, captures, queue, history, settings, errors, stats);
  - a **"ก่อนอัปเดต / ข้อควรรู้"** block saying that the database is now version 3, so after updating you cannot go back to an older version of the app;
  - a "known limits" list (YouTube only, Windows only until M7, needs Git).
- No tag in D1 (D6).

## 4. Green CI

- Fix the flaky e2e tests seen in this milestone:
  - `queue-capture.spec.ts:78` (capture button not found while the bot-check pause is shown);
  - `queue-account.spec.ts:46`;
  - `download-tabs.spec.ts:378` (axe audio tab, light, under load);
  - `player.spec.ts:260`.

  For each, find the race and wait on the real condition (C7). Prove the fix by running the spec with `--repeat-each=10` under `--workers=4` and requiring 10/10.
- Check the latest `ci.yml` run on `main` with `gh run list --workflow ci.yml --limit 5` (read-only). If it is red for a reason in this repo, fix that too. If it is red for an external reason, record it in the report.

## 5. D2 checklist (`docs/v1-checklist.md`) and acceptance pointers

- `docs/v1-checklist.md`: about 30-40 items in one order that can be done in one sitting.
  - Each item has: what to do, what should happen, a target number where one exists, and a blank result field.
  - It must cover:
    - a fresh Windows account install following the README, timed (≤ 10 min);
    - the second launch (≤ 5 s) and idle RAM (≤ 300 MB, Task Manager);
    - frame mode median (≤ 5 s) and subtitle preview (≤ 200 ms) by stopwatch or the existing in-app timing;
    - one real download of each kind (video, audio, subtitles, note, frames zip, contact sheet), a time range, ad removal (SponsorBlock), chapters split, sharp frames, a capture;
    - the temporary YouTube account with an age-restricted clip (Pete's spare account);
    - network unplugged (AC-LIFE-05);
    - opening the app from another LAN machine must fail (AC-SEC-01);
    - the stats tab after real downloads;
    - clearing temporary data while a download runs;
    - settings backup and restore;
    - a short NVDA pass on W1, W2 and W6;
    - the keyboard-only pass by hand.
- `docs/acceptance.md`: for each row an automated test already proves, add the test pointer in the row (format `auto: <file>::<test>`). Leave the pass box for D2. Rows that need a human stay as they are and are referenced from the checklist.

## 6. Testing summary

- e2e: focus-ring contrast (both themes), keyboard journey, health-page axe states, a README-labels check (§2.1, a vitest or node test that reads `README.md` and `th.ts`).
- Flaky specs at 10/10 with repeat.
- Full gate: `uv run pytest -q -W error -p no:cacheprovider`; web typecheck, lint, vitest, build; full Playwright `--workers=4`.

## 7. Review focus

1. A focus ring that passes on `--background` but not inside a card, popover or dialog: expect ≥ 3:1 on every surface it appears on.
2. A keyboard trap in a dialog, popover or the player: expect Escape or Tab to leave, and focus to return to the trigger.
3. README steps that only work on a developer machine (e.g. assume `uv` or Python is installed): expect them to work on a Windows account with only Git.
4. Screenshots that leak a real path, user name or token: expect fake data only.
5. A flaky fix that only raises a timeout: expect a wait on the real condition.

## Out of scope (round D1)

- A graphical installer, auto-update inside the app, a keyboard-shortcut help page (backlog), macOS (M7), multi-site (future milestone).
- The manual sweep itself (D2) and the `v1.0.0` tag.
