# M6 round C: the "สถิติของฉัน" stats tab (design)

Pete approved the design in conversation on 2026-10-15 (Q1-Q3 below, then the four design sections). This written spec turns it into an implementable design. Every Thai string is sourced (§7).

Round C implements one PRD M6 item: the **"สถิติของฉัน"** tab in W6 (BRD §5.13 FR-STAT-1..4 `BRD.md:269-275`, PRD W6 `PRD.md:302`, `:309`, confirm dialog `:326`, API `:625-626`, setting `:751`, AC-STAT-01..04 `PRD.md:504-510`, M6 exit criterion `BRD.md:767`).

It touches:
- a new `core/stats.py` + `api/stats.py`, `core/settings.py` (an internal writer for `statsResetAt`), `app.py` (mount);
- the web: `pages/settings.tsx` (tab), a new `pages/settings/stats-panel.tsx` + `stats.ts` model beside it, a new `lib/stats-api.ts`, `lib/types.ts`, `i18n/th.ts`;
- `docs/acceptance.md` (AC-STAT rows, §8).

No DB schema change: `SCHEMA_VERSION` stays 3. Code facts were checked at HEAD `1933b08` (branch `main`).

## Owner decisions (2026-10-15)

| # | Decision | Where |
|---|---|---|
| D1 | **A file is one piece the user asked for** (Q1 = A). Each entry of a done job's `outputs_json` counts as 1 file; a sharp-frames `folder` counts as 1 file, its bytes are the whole folder's `sizeBytes`. Kinds map to the BRD's four groups: `video` → วิดีโอ, `audio` → เสียง, `subtitle` + `note` → ซับ, `image` + `archive` + `folder` → ภาพ. | §1.2 |
| D2 | **Monthly table = only months with downloads, within the last 12 months, newest first** (Q2 = A). The four totals cover everything since counting started (not just 12 months). A clip downloaded in two months counts in both rows, but once in the total. | §1.3 |
| D3 | **Copy** (Q3 = A): the drafts in §7 are final. The size uses the app's `formatBytes` (MB under 1 GB, GB above) instead of a fixed GB. A tie on "most used" goes to the kind with more bytes. | §7, §3 |
| D4 | **Computed in Python** from the `jobs` table, no SQL aggregation, no schema change, no network. | §1 |
| D5 | **Future sites** (owner constraint, 2026-10-14): the clip id is an opaque string; nothing in stats assumes YouTube. | C8 |

## Global constraints

Every task in the plan must hold all of these.

- **C1 No network.** Nothing in `core/stats.py`, `api/stats.py` or the stats panel makes an outbound request (FR-STAT-3, NFR-SEC-6). The panel calls only `/api/stats` and `/api/stats/reset`.
- **C2 Privacy.** No clip title, channel, path (`root`/`rel`), token or cookie data in the API response, logs or the report. The response holds numbers, kind keys, month keys and one timestamp only.
- **C3 Read-only except `statsResetAt`.** `POST /stats/reset` writes one settings key. It never deletes or edits jobs, videos, history, the queue or output files (FR-STAT-4, AC-STAT-03).
- **C4 `statsResetAt` stays read-only to clients.** `PATCH /settings` still rejects it (`E_BAD_REQUEST`, PRD `:616`), export and import still skip it. Only `SettingsStore.reset_stats()` writes it.
- **C5 Thai time for months.** `byMonth` buckets by the month of `finished_at` in UTC+07:00, a fixed offset (Thailand has no DST), regardless of the machine's time zone (AC-STAT-01).
- **C6 Tolerant of bad rows.** A broken row never fails the endpoint (§1.4).
- **C7 Thai UI copy** comes only from §7. Buttons start with a verb, no "กรุณา", no "!". 640 px narrow window; light and dark.
- **C8 Platform-neutral.** `video_id` is an opaque string; no YouTube id regex, no YouTube wording in stats.
- **C9 Usual repo rules.** No `shell=True`; only `yttoolkit.platform` checks the OS; `yt_dlp` only in `core/extractor.py`; LF; commit trailer `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`; `web/dist` only at the final gate; chromium e2e never creates real jobs and mocks writes.

## 1. Computation (`core/stats.py`)

### 1.1 Which jobs count

```python
def compute(db: Database, since: str | None, now: datetime) -> dict
```

A job counts when all hold:
- `status = 'done'` (failed, cancelled, queued, running, paused never count, FR-STAT-2);
- `finished_at` parses as an ISO 8601 datetime (naive values are read as UTC);
- `since` is None, or `finished_at >= since` (compared as datetimes, not strings). A `since` that does not parse is treated as None (§4).

One query: `SELECT video_id, finished_at, outputs_json FROM jobs WHERE status = 'done'`. The rest is Python. A few thousand rows is the expected size; no index is added.

### 1.2 Totals and kinds

- `clips` = number of distinct `video_id` among counted jobs (a counted job with no outputs still counts its clip).
- `files` = number of counted output entries (D1). An entry whose `kind` is not one of the seven known output kinds is skipped (not counted, no log).
- `totalBytes` = sum of counted entries' `sizeBytes`. A missing, non-integer or negative `sizeBytes` counts as 0 bytes (the entry still counts as a file).
- `byKind` = one item `{kind, files, bytes}` per group that has ≥ 1 file, `kind` ∈ `"video" | "audio" | "subtitle" | "image"`. Sorted by `files` desc, then `bytes` desc, then the fixed order video, audio, subtitle, image (AC-STAT-01 "sorted descending"; D3 tie rule).

### 1.3 Months

- The month key is `"YYYY-MM"` of `finished_at` converted to UTC+07:00.
- The window is the current month in UTC+07:00 (from `now`) and the 11 months before it. Older months are left out of `byMonth` but still count in the totals (D2).
- `byMonth` = one item `{month, clips, files, bytes}` per month in the window with ≥ 1 counted job, newest first. `clips` is distinct `video_id` within that month.
- A `finished_at` in the future (clock moved back) still buckets by its own month; if that month is after the current month it is left out of `byMonth` but counts in the totals.

### 1.4 Bad rows (C6)

- `outputs_json` NULL, not JSON, not a list → the job counts as a clip with 0 files.
- A list item that is not an object → skipped.
- `finished_at` NULL or unparsable → the job is skipped entirely.
- Nothing is logged for bad rows (no title or path could leak, and the endpoint stays quiet).

### 1.5 Result shape (PRD `:625`)

```json
{"since": "2026-10-15T03:00:00+00:00", "clips": 3, "files": 5, "totalBytes": 123,
 "byKind": [{"kind": "video", "files": 3, "bytes": 100}],
 "byMonth": [{"month": "2026-10", "clips": 2, "files": 3, "bytes": 80}]}
```

`since` is always present: the stored `statsResetAt`, or `null` when never reset (the TS type is `string | null`). Empty → `clips: 0, files: 0, totalBytes: 0, byKind: [], byMonth: []`.

## 2. Reset and API

### 2.1 `SettingsStore.reset_stats(now_iso: str) -> str`

A new public method in `core/settings.py`. It writes `statsResetAt = now_iso` through the existing `_save()` (same transaction and lock as `patch`) and returns the stored value. It is the only writer of `statsResetAt` (C4). `patch()`, `exportable()` and `import_settings()` are unchanged.

### 2.2 `api/stats.py` → `build_stats_router(ctx)`

- `GET /stats` → `compute(ctx.db, settings["statsResetAt"], now)`; 200 with §1.5.
- `POST /stats/reset` → `since = ctx.settings.reset_stats(datetime.now(UTC).isoformat(timespec="microseconds"))`; 200 `{since}`. The stamp has microsecond precision, the same as `jobs.finished_at`, so a job finished a moment before the click is not counted after it (final review I1, 2026-10-15).
- Mounted in `app.py` with prefix `/api`, guarded by `if ctx.settings is not None` (it needs both the DB and settings). Under `/api`, `LocalOnlyMiddleware` already requires the token + Origin on the POST.
- No request body on either route. Errors go through the existing handlers (`E_UNKNOWN` on an unexpected exception, logged by `ErrorLogMiddleware` with no path).
- `ctx.db` access matches the other routers; the call is synchronous and fast, so it runs in FastAPI's thread pool like the history route.

## 3. Web

### 3.1 Tab and route

- `pages/settings.tsx` `TABS` becomes `["general", "advanced", "stats", "health", "about"]` (PRD `:302` lists five tabs; stats sits after advanced, before health). `/settings/stats` is the route (PRD `:88`).
- `th.settings.tabs.stats = "สถิติของฉัน"`.

### 3.2 Data (`lib/stats-api.ts`)

- `STATS_KEY = ["stats"]`, `statsQuery` with `staleTime: 0` and `refetchOnMount: "always"` so opening the tab recomputes (FR-STAT-2).
- `resetStats()` → `api("/stats/reset", { method: "POST" })`; on success, invalidate `STATS_KEY`.
- Types `Stats`, `StatsKind`, `StatsMonth` in `lib/types.ts`.

### 3.3 Model (`pages/settings/stats.ts`, node-testable)

Pure functions, no React:
- `kindLabel(kind)` → วิดีโอ / เสียง / ซับ / ภาพ;
- `topKind(stats)` → the first `byKind` item or null;
- `monthLabel("2026-10")` → "ตุลาคม 2569" (`Intl.DateTimeFormat("th-TH", {month: "long", year: "numeric", timeZone: "UTC"})` on the 1st of that month UTC, so the label never shifts by time zone);
- `sinceLabel(iso)` → the date in Thai long form ("15 ตุลาคม 2569"), in `Asia/Bangkok`, matching C5;
- `count(n)` → `n.toLocaleString("th-TH")` (thousands separators).

### 3.4 Panel (`pages/settings/stats-panel.tsx`)

Layout, top to bottom:
1. Four stat tiles in a grid (2 × 2 at 640 px, 4 across when wide): **คลิป**, **ไฟล์**, **ขนาดรวม** (`formatBytes(totalBytes)`), **ใช้บ่อยที่สุด** (kind label, with a small line "<n> ไฟล์" under it).
2. The monthly table (`components/ui/table.tsx`): columns เดือน · คลิป · ไฟล์ · ขนาด; numbers right-aligned; header cells `scope="col"`.
3. The small note "คำนวณในเครื่องนี้เท่านั้น ไม่ส่งไปที่ไหน".
4. When `since` is set: "นับตั้งแต่ <วันที่>".
5. The ghost button "ล้างสถิติ", shown only when `clips > 0`. It opens an AlertDialog: title "เริ่มนับสถิติใหม่?", body "ประวัติและไฟล์ที่โหลดไว้ยังอยู่ครบ", buttons ยกเลิก / ล้างสถิติ. Confirm → `resetStats()` → toast "ล้างสถิติแล้ว"; the panel refetches and shows the empty state with "นับตั้งแต่ <วันที่>".

States:
- **Loading:** skeleton tiles (the existing Skeleton component).
- **Empty** (`clips === 0`): the Empty component with "ยังไม่มีสถิติ"; the privacy note and "นับตั้งแต่" (if set) still show under it; no tiles, no table, no reset button.
- **Load error:** the M6-B `ErrorDetails` with the copy-report button, context `"stats"`.
- **Reset error:** `showErrorToast` (M6-B) with context `"stats-reset"`; the dialog closes; numbers stay as they were.

The confirm button is disabled while the reset request runs (no double submit).

## 4. Errors and edge cases

| Case | Behaviour |
|---|---|
| Never reset, no done jobs | Empty state, no "นับตั้งแต่" |
| Reset, nothing done since | Empty state + "นับตั้งแต่ <date>" (AC-STAT-03 "0 everywhere and has `since`") |
| Reset twice | The second reset moves `since` forward; nothing else changes |
| A job finishes during the reset | Counted if its `finished_at >= since` (datetime compare, inclusive) |
| `statsResetAt` stored but unparsable | `statsResetAt` has no settings validator, so the raw value reaches stats. `compute()` treats a `since` that is not a string or does not parse as ISO 8601 as `None`: it counts everything and returns `since: null` |
| Machine time zone is not Thailand | Months still bucket in UTC+07:00 (C5); "นับตั้งแต่" shows the Bangkok date |
| Corrupt `outputs_json` / missing size | §1.4 |
| Network cut | `/stats` still answers (it never leaves the process) |

## 5. Testing

### 5.1 Python unit (`tests/unit/test_stats.py`)

- **AC-STAT-01:** 5 done jobs from 3 clips over 2 months, 2 failed, 1 cancelled → `clips 3`, `files 5`, `totalBytes` = sum of the outputs' `sizeBytes`; `byKind` sorted desc; `byMonth` has 2 rows.
- Month edge in Thai time: `finished_at = 2026-09-30T17:30:00+00:00` buckets to `"2026-10"`; `…T16:59:59+00:00` buckets to `"2026-09"`.
- 12-month window: a job 13 months back counts in totals, not in `byMonth`; the oldest month in the window is included.
- D1 mapping: note → subtitle, archive + folder + image → image; a folder counts 1 file with its bytes.
- Tie rule: equal files → more bytes first; equal both → fixed order.
- `since`: a job at exactly `since` counts; one second before does not; naive `finished_at` is read as UTC; an unparsable stored `since` counts everything and returns `since: null`.
- §1.4: NULL / non-JSON / non-list `outputs_json`, a non-object item, an unknown kind, a negative or string `sizeBytes`, an unparsable `finished_at`.
- A clip in two months appears in both rows and once in `clips`.
- `reset_stats` writes the key; `patch({"statsResetAt": …})` still raises; `exportable()` still has no `statsResetAt`.

### 5.2 Python API (`tests/api/test_stats_api.py`)

- `GET /api/stats` shape and values over seeded jobs.
- **AC-STAT-02 (server half):** with `socket.socket.connect` patched to raise, `GET /api/stats` still returns 200.
- **AC-STAT-03:** after `POST /api/stats/reset`, `GET /api/stats` is all zero with `since`; `GET /api/history` returns the same body as before; the jobs rows and the output files on disk are unchanged; a job finished afterwards is counted.
- `POST /api/stats/reset` without the token → 403 (existing middleware), and `statsResetAt` is unchanged.
- The response body contains no title, channel, `root` or `rel` from the seeded jobs (C2 canary).

### 5.3 Web

- Vitest for `stats.ts`: kind labels, `topKind`, `monthLabel` (no time-zone shift), `sinceLabel` in Bangkok, `count`.
- Vitest for the panel model if the panel needs any branching beyond the model.
- Chromium e2e `e2e/settings-stats.spec.ts`, with `/api/stats` and `/api/stats/reset` mocked:
  - **AC-STAT-02 (browser half):** every request while the tab is open goes to `127.0.0.1:<port>` (Playwright request log).
  - **AC-STAT-04:** an empty response shows "ยังไม่มีสถิติ".
  - Filled response: four tiles, the table rows in order, the month label in Thai.
  - Reset: confirm dialog copy, cancel keeps the numbers, confirm calls the POST once and shows "ล้างสถิติแล้ว" and "นับตั้งแต่ …".
  - Load error shows ErrorDetails with the copy button.
  - axe (serious/critical) light and dark; 640 px no horizontal scroll.

## 6. Review focus (top failure modes the tests may miss)

1. **Time zone drift.** Month keys or the "นับตั้งแต่" date shift by one when the browser or server is not in UTC+07:00. Expect: both pinned to Thai time.
2. **String compare of timestamps.** `finished_at` and `since` with different offsets or precision compared as text. Expect: datetime compare.
3. **One broken old row takes the tab down.** Expect: §1.4 skips, 200 always.
4. **Reset leaks into other data.** Expect: only `statsResetAt` changes (AC-STAT-03).
5. **A title or path in the response or a log.** Expect: numbers and keys only (C2).

## 7. Thai copy (all sourced)

| Key | Text | Source |
|---|---|---|
| tab | สถิติของฉัน | BRD `:272`, PRD `:302` |
| tiles | คลิป · ไฟล์ · ขนาดรวม · ใช้บ่อยที่สุด | Pete Q3 = A (PRD `:309` names the four) |
| top-kind sub line | `{n} ไฟล์` | Pete Q3 = A |
| kinds | วิดีโอ · เสียง · ซับ · ภาพ | BRD `:272` |
| table headers | เดือน · คลิป · ไฟล์ · ขนาด | PRD `:309` |
| privacy note | คำนวณในเครื่องนี้เท่านั้น ไม่ส่งไปที่ไหน | PRD `:309` |
| since | นับตั้งแต่ {date} | PRD `:309` |
| empty | ยังไม่มีสถิติ | PRD `:309` |
| reset button | ล้างสถิติ | PRD `:309`, `:326` |
| dialog title | เริ่มนับสถิติใหม่? | PRD `:326` |
| dialog body | ประวัติและไฟล์ที่โหลดไว้ยังอยู่ครบ | PRD `:326` |
| dialog buttons | ยกเลิก · ล้างสถิติ | PRD `:326` |
| reset toast | ล้างสถิติแล้ว | Pete Q3 = A |

The month label ("ตุลาคม 2569") and the size ("1.4 GB", "350 MB") are formatted, not copy.

## 8. Docs (done in the plan's first task)

- `docs/acceptance.md`: add AC-STAT-01..04 rows in the existing table style, pointing at the tests in §5.
- PRD `:309`: add "ขนาดใช้หน่วยตามขนาดจริง (MB ต่ำกว่า 1 GB)" next to "ขนาดรวม GB" with "(Pete 2026-10-15)", and the D1 kind mapping next to FR-STAT-1's kinds.

## 9. Spec questions (answered by Pete, 2026-10-15)

| Q | Question | Answer |
|---|---|---|
| Q1 | How to count files and group kinds | A: one piece the user asked for; four groups (D1) |
| Q2 | Which months the table shows | A: only months with downloads, last 12, newest first (D2) |
| Q3 | Copy not in the PRD, size unit | A: the §7 drafts; size by `formatBytes` (D3) |

Controller rulings in this spec (not owner questions): `since` is always present (null when never reset); the stats tab sits between ขั้นสูง and ตรวจสุขภาพระบบ; the reset button is hidden in the empty state; months bucket on a fixed UTC+07:00.

## Out of scope (round C)

- Charts (the PRD calls for a table only).
- Exporting stats to a file; stats in the settings backup (FR-SET-7 excludes them).
- Counting single-frame captures (they are not `jobs` rows; FR-STAT-2 counts `jobs` only).
- A DB index or schema change.
