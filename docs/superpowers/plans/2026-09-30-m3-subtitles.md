# M3 ซับ (Subtitles) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Tasks inside one wave run as parallel subagents, each in its own git worktree (see "Waves").

**Goal:** On the clip page (W2), the user switches between three tabs: ภาพเฟรม, ซับ and ทรานสคริปต์.
- **ซับ tab:** pick a subtitle track (the app picks the right one by itself), choose a length preset or custom values, see a live preview, then download `.srt` / `.txt` / `.md` or copy the text. Thai lines never break mid-word.
- **ทรานสคริปต์ tab:** search the transcript; clicking a line jumps to the nearest frame.
- **Header:** copy the chapter list and the description.

**Scope (PRD section 10, row M3):**
- Fixtures.
- `/videos/{id}/subtitles`, `/videos/{id}/subtitles/{trackId}/tokens`, plus the M3 stand-in for `/jobs (subtitle)` (see owner decision Q1).
- `srt_builder` in Python and TypeScript, with byte parity.
- The W2 tab bar (ภาพเฟรม · ซับ · ทรานสคริปต์; วิดีโอ/เสียง come in M4), the ซับ and ทรานสคริปต์ sections, and the copy-chapter and copy-description buttons.
- "ดูซับช่วงนี้" in the frame menu.
- The `docs/m2-followups.md` M3 item (tabs).

**Acceptance criteria:**
- AC-SUB-01..09 and 11. AC-SUB-10 (time range) is M5.
- AC-PROBE-03..04.
- NFR "preview ซับ ≤ 200 ms" (PRD section 8, same as AC-SUB-07).

**Architecture:**
- **Backend pipeline:** probe → trimmed caption list stored in `videos.probe_json` (`core/tracks.py`) → the subtitle file is fetched through the extractor (`fetch_subtitle`) and cached under `data/cache/<id>/subs/` → the parser (`core/subparse.py`) turns json3 (fallback vtt) into **tokens** → the pure builder (`core/srt_builder.py`) turns tokens into cues and `.srt/.txt/.md`.
- **Thai word splitting happens only in the parser.** PyThaiNLP runs only there, for tracks without word timing. The TS builder (`web/src/lib/srt-builder.ts`) receives the same tokens from `/tokens`, so parity (AC-SUB-06) is a pure-function port checked against shared golden files.
- **W2 state in the URL:** W2 becomes a Base UI Tabs page. The tab, the chosen track and the "jump to time" live in URL search params.

**Tech Stack:**
- Unchanged from M2.
- New Python dependency: `pythainlp` (newmm engine, Task 2).
- New shadcn components: select, toggle-group, slider, field, collapsible, scroll-area, switch.

---

## Owner decisions (ANSWERED 2026-09-30)

**พิธตอบ 2026-09-30: ตามที่แนะนำทั้งหมด ยกเว้น Q9 = ข** (controller แนะนำ: ซับ TED เป็น CC BY-NC-ND บริษัทใช้เสี่ยงเรื่องเงื่อนไขห้ามใช้เชิงพาณิชย์ จึงใช้ fixture ที่เขียนเอง `OWNERTHSUB1`) → Q1 ก · Q2 ก · Q3 ก · Q4 ก · Q5 ก · Q6 ก · Q7 ก · Q8 ก · Q9 ข · planner defaults ใช้ทั้งหมด · Network test ยังเปิดคลิป TED จริงได้ (ไม่ได้เก็บอะไรลงรีโป)

### Questions as asked

แต่ละข้อมีคำตอบที่แนะนำไว้ ถ้าพิธตอบ "ตามที่แนะนำ" ทั้งหมด แผนนี้ใช้ได้เลยโดยไม่ต้องแก้ controller บันทึกคำตอบลงในหัวข้อนี้ก่อนเริ่ม Wave 1 และ Task 15 ย้ายไปลงบันทึกการตัดสินใจใน BRD

**Q1. โหลดไฟล์ซับยังไงใน M3 (ระบบคิวยังไม่มี มาใน M4)**
- ก. **(แนะนำ)** กด "โหลด .srt / .txt / .md" แล้วเบราว์เซอร์โหลดไฟล์ทันที แบบเดียวกับปุ่มโหลดภาพรวมเฟรมใน M2 ไฟล์ลงโฟลเดอร์ Downloads ของเบราว์เซอร์ พอ M4 มีคิวแล้วค่อยย้ายเข้าคิว และบันทึกลงโฟลเดอร์ผลลัพธ์ `YT-Toolkit`
- ข. M3 มีแค่ปุ่ม "คัดลอกข้อความ" ส่วนปุ่มโหลดไฟล์รอ M4
- ค. ทำคิวแบบย่อสำหรับซับอย่างเดียวใน M3 (งานซ้ำกับ M4 และเสี่ยงต้องรื้อ)

**Q2. ชื่อไฟล์ซับ**
- ก. **(แนะนำ)** `<ชื่อคลิป>.th.srt` (มีรหัสภาษาก่อนนามสกุล) โปรแกรมเล่นอย่าง VLC จะเปิดซับให้เองเมื่อวางไว้ข้างไฟล์ `<ชื่อคลิป>.mp4` ที่ M4 จะโหลดมา
- ข. `<ชื่อคลิป> - ซับไทย.srt` อ่านง่ายกว่า แต่โปรแกรมเล่นไม่เปิดให้เอง

**Q3. ซับที่แสดงสั้นเกินไป แล้วเอาไปรวมกับซับถัดไป ยอมให้ยาวเกินขีดจำกัดได้ไหม**
- เอกสาร 2 ฉบับเขียนไม่ตรงกัน:
  - BRD ข้อ 12.2 บอกว่ารวมได้ถ้าไม่เกิน 1.2 เท่า (preset กลางจะได้ถึง 30 ตัวอักษร)
  - PRD AC-SUB-05 บอกว่าทุกซับต้องไม่เกิน 25 ตัว
- ก. **(แนะนำ)** ห้ามเกินขีดจำกัดเลย ยึด PRD ซับที่สั้นเกินจะถูกยืดเวลาแสดงแทน
- ข. ยอมเกินได้ 1.2 เท่าตาม BRD แล้วแก้ AC-SUB-05 เป็น "≤ 30 ตัวสำหรับซับที่ถูกรวม"

**Q4. ทรานสคริปต์แสดงข้อความจากแทร็กไหน และแบ่งบรรทัดแบบไหน**
- ก. **(แนะนำ)** ใช้แทร็กเดียวกับที่เลือกในแท็บซับ และแบ่งบรรทัดตาม preset ที่เลือกอยู่ เห็นอะไรในทรานสคริปต์ก็ได้แบบนั้นในไฟล์ `.srt` และคลิกบรรทัดแล้วกระโดดไปภาพเฟรมได้แม่น
- ข. แบ่งเป็นย่อหน้าตามช่วงหยุดพูด อ่านต่อเนื่องง่ายกว่า แต่คลิกแล้วได้แค่เวลาต้นย่อหน้า

**Q5. "ตัวเลือกขั้นสูง" (พับไว้) ในแท็บซับ**
- ของข้างในทุกอย่างมาใน M5: ช่วงเวลา, แยกตาม chapter, ตัดโฆษณา และคุกกี้
- ก. **(แนะนำ)** ซ่อนไว้ก่อน แล้วแสดงเมื่อมีตัวเลือกที่ใช้ได้จริง (M4/M5)
- ข. แสดงกล่องพับไว้แต่ข้างในบอกว่า "มาในเวอร์ชันถัดไป"

**Q6. เมนู "ดูซับช่วงนี้" ที่ภาพเฟรม ทำอะไร**
- ก. **(แนะนำ)** สลับไปแท็บทรานสคริปต์ แล้วเลื่อนไปไฮไลต์บรรทัดของเวลานั้น
  - คลิปที่ไม่มีซับจะไม่มีเมนูนี้
  - กดย้อนกลับ (back) แล้วออกจากหน้าคลิปไปหน้าก่อนหน้าเลย ไม่ได้ย้อนทีละแท็บ ตามกฎ breadcrumb ของ M2
- ข. เปิดกล่องเล็ก ๆ บนภาพเฟรม แสดงซับ 3 บรรทัดรอบเวลานั้น ไม่เปลี่ยนแท็บ

**Q7. นับ "ตัวอักษร" ของซับไทยยังไง (preset กลาง = 25 ตัวต่อบรรทัด)**
- ก. **(แนะนำ)** นับตามที่ตาเห็นบนจอ: ไม่นับสระบน สระล่าง และวรรณยุกต์ (เช่น "ที่" = 1 ตัว, "น้ำ" = 2 ตัว) ความยาวบรรทัดจึงใกล้เคียงภาษาอังกฤษจริง ๆ
- ข. นับทุกตัวรวมสระและวรรณยุกต์ บรรทัดไทยจะสั้นกว่าที่ตาเห็นประมาณ 20-30%

**Q8. ถ้าคลิปพูดภาษาอื่น แต่มีซับไทยที่เจ้าของคลิปทำไว้ ควรเลือกซับไทยให้เองไหม**
- ตัวอย่าง: คลิป TED ภาษาอังกฤษที่มีซับไทยจากอาสาสมัคร
- กฎใน FR-SUB-3 ตอนนี้จะเลือกซับภาษาต้นฉบับ (อังกฤษ) ก่อน
- ก. **(แนะนำ)** เลือกซับไทยของเจ้าของคลิปก่อน ถ้ามี แล้วค่อยใช้ลำดับเดิมของ FR-SUB-3 ผู้ใช้เราเป็นพนักงานไทยที่ต้องการซับไทย (US-04) ถ้าต้องการต้นฉบับก็เลือกเองได้ในรายการ
- ข. ยึด FR-SUB-3 เดิม: ภาษาต้นฉบับก่อนเสมอ

**Q9. ข้อมูลทดสอบ "ซับไทยที่เจ้าของคลิปทำเอง"**
- คลิปที่เรามีสัญญาอนุญาต CC BY ไม่มีซับแบบนี้
- ตัวเลือกที่พบคือคลิป TED `iG9CE55wbtY` (สัญญาอนุญาต CC BY-NC-ND ของ TED)
- ก. **(แนะนำ)** ใช้ซับไทยจริงจากคลิป TED ตัดมาแค่ 3 นาทีแรก เก็บในรีโปส่วนตัวเพื่อทดสอบเท่านั้น ใส่เครดิตใน README
  - ข้อมูลจริงจับปัญหาจริงได้ เช่น บรรทัดเครดิตผู้แปล และขึ้นบรรทัดกลางซับ
- ข. ใช้ซับไทยที่เราแต่งเองทั้งหมด (ปลอดภัยด้านสิทธิ์ 100% แต่ไม่เจอปัญหาของข้อมูลจริง)

### Planner defaults (บอกได้ถ้าไม่เห็นด้วย ไม่ต้องตอบก็ได้)
- **ซับแปลอัตโนมัติ ("เมนูย่อยพร้อมคำเตือน"):**
  - รายการเลือกแทร็กมี 2 กลุ่ม (ซับจากเจ้าของคลิป · ซับอัตโนมัติภาษาต้นฉบับ) และแถวสุดท้าย "เลือกซับแปลอัตโนมัติ…"
  - แถวนั้นเปิดกล่องค้นหาภาษาพร้อมคำเตือนว่าคุณภาพต่ำ มีประมาณ 150 ภาษา ยาวเกินกว่าจะใส่ในเมนูย่อย
- **หัวข้อเวลาในไฟล์ `.md`:** ใช้ `[mm:ss]` ตาม BRD และเมื่อถึงชั่วโมงแรกเปลี่ยนเป็น `[h:mm:ss]` (เช่น `[1:05:30]`) ไม่ใช้ `[65:30]`
- **ไฟล์ `.srt` `.txt` `.md`:** UTF-8 ไม่มี BOM ขึ้นบรรทัดแบบ Windows (CRLF) ทั้ง 3 แบบ
- **ตัวอย่างซับ (preview):** เวลาแสดงแบบในไฟล์ `.srt` คือ `00:00:01,560 → 00:00:03,200` ให้เห็นตรงกับไฟล์จริง
- **ปุ่มสีอำพัน:** ใน M3 ไม่มีปุ่มหลักสีอำพันในหน้าคลิป เพราะปุ่มหลักของหน้านี้คือ "โหลด mp4" ที่มาใน M4 ปุ่มโหลดซับเป็นปุ่มรอง
- **จำค่าล่าสุด:** preset และค่าปรับเองจำไว้ในเบราว์เซอร์ (localStorage) แล้วย้ายไปเก็บใน `/settings` เมื่อ API ตั้งค่ามาใน M4/M6
- **ปุ่มคลิปก่อนหน้า/ถัดไป:** เปิดคลิปถัดไปแล้วอยู่ที่แท็บเดิม

---

## Waves

| Wave | Tasks that run in parallel (one worktree each) | Depends on |
|---|---|---|
| 1 | T1 capture fixtures (network) · T2 PyThaiNLP + `thai_fallback` · T3 extractor `fetch_subtitle` · T4 Python `srt_builder` + shared builder cases · T5 web UI kit + all M3 `th.ts` strings · T6 web data layer (types, options, URL state, queries) | Owner answers Q1–Q9 |
| 2 | T7 json3/vtt parsers · T8 caption tracks + probe trim · T9 TS `srt-builder` + `useCues` · T10 W2 tab shell + header copy buttons | Wave 1 gate (T7←T1,T2,T4 · T8←T1 · T9←T4,T6 · T10←T5,T6) |
| 3 | T11 subtitle service + API · T12 real-fixture integration, goldens, TS parity · T13 ซับ tab UI · T14 ทรานสคริปต์ tab + frame linkage | Wave 2 gate (T11←T3,T4,T7,T8 · T12←T4,T7,T9 · T13←T5,T6,T9,T10 · T14←T6,T9,T10) |
| 4 | T15 network tests, docs, acceptance list, final verification, live preview for Pete | Wave 3 gate |

**Critical path:** T1 → T7 → T11 → gate 3 → T15.

### Lane rules (every task)
1. **Worktree and branch.** Each task runs in its own git worktree (`isolation: "worktree"`) on branch `m3/t<N>-<slug>`, branched from the integration branch `m3-subtitles` at the start of its wave.
2. **Files.** A task creates or modifies **only** the files in its **Files** list. Needing another file is a plan bug: stop and report it to the controller, and do not edit the file.
3. **Shared files have exactly one owner:**

   | File | Owner |
   |---|---|
   | `web/src/i18n/th.ts` | T5 (writes every M3 string up front, verbatim from "Shared contracts § C9") |
   | `web/src/lib/types.ts` | T6 |
   | `pyproject.toml`, `uv.lock` | T2 |
   | `web/package.json`, `web/package-lock.json` | T5 |
   | `src/yttoolkit/app.py`, `src/yttoolkit/lifecycle.py`, `src/yttoolkit/api/videos.py` (only the `STATUS_BY_CODE` entry), `src/yttoolkit/core/yterrors.py` | T11 |
   | `PRD.md`, `BRD.md`, `docs/acceptance.md`, `docs/m2-followups.md`, `README.md` | T15 |
   | `web/dist/**` | wave gates and T15 only. No lane task ever builds into or commits `web/dist`. |
   | `.gitattributes` | T12 |

   `tests/fixtures/**` is split by path: T1 owns `probe/**`, `subs/<videoId>/**`, `storyboard/88o5Sk8_m1Y/**` and `README.md`. T4 owns `subs/builder-cases.json`. T12 owns `subs/golden/**` and `subs/tokens/**`.

   A lane that finds it needs a new Thai string stops and asks the controller. The controller adds it to `th.ts` at the gate and hands it back.
4. **Tests.**
   - Lanes run pytest and Vitest for their own files, plus the full `uv run pytest -q -W error` (Python lanes) or `npm run typecheck && npm run lint && npm test` (web lanes).
   - Lanes **do not run Playwright**. E2E specs are written, typechecked and linted in the lane, then executed at the wave gate (port 8799). A spec that fails at the gate goes back to its owning task.
5. **Processes.**
   - No lane starts a server except T1 (network, no server) and T15 (preview on port 8791).
   - Never touch the owner's app on port 8787.
   - Kill processes by PID only.
6. **Commits.** Every commit ends with exactly `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`.

### Wave gate procedure (controller, serial)
1. Merge every lane branch of the wave into `m3-subtitles` with `--no-ff`. File sets are disjoint, so a merge conflict means the plan is wrong: stop and report.
2. `uv sync --frozen && uv run pytest -q -W error`
3. `cd web && npm ci && npm run typecheck && npm run lint && npm test && npm run build`. Also check the JS gzip size stays ≤ 400 KB, excluding fonts (PRD 6.5).
4. `cd web && npm run e2e`. This uses port 8799 and the temp data root from `playwright.config.ts`, with fake mode.
5. Commit the rebuilt `web/dist` as `build(web): rebuild dist after M3 wave <n>` (with the trailer).
6. Run the two-stage review (spec, then quality) from superpowers:subagent-driven-development on each task of the wave, and fix findings in the owning lane before starting the next wave.

---

## Verified facts

### yt-dlp source (2026.08.19, `.venv/Lib/site-packages/yt_dlp/`, read on 2026-09-30)

**Subtitle formats and track structure**
- **Formats offered:** `extractor/youtube/_video.py:142` has `_SUBTITLE_FORMATS = ('json3', 'srv1', 'srv2', 'srv3', 'ttml', 'srt', 'vtt')`.
- **Entry shape:** `process_language` (`_video.py:4207-4219`) appends one entry per format to `container[lang_code]`: `{ext, url (same base URL with fmt=<ext>), name, impersonate: True, __yt_dlp_client}`. We use only the `json3` and `vtt` entries.

**Owner subs vs auto-captions**
- **Owner subs go to `info['subtitles']`:** tracks with `kind != 'asr'` (`_video.py:4285-4290`).
  - Their machine translations are added only when `writeautomaticsub` or `listsubtitles` is set (`get_translated_subs`, `_video.py:4237-4238`, and the `continue` at `_video.py:4297-4299`).
  - Our probe sets neither, so owner translations never appear.
- **ASR tracks go to `info['automatic_captions']`** (`_video.py:4293-4313`):
  - For the original language L, yt-dlp adds **both** `L-orig` (name "`<Lang>` (Original)") and `L`.
  - These two use the same base URL **without** `tlang`, because `orig_lang == orig_trans_code`.
  - Every other language key adds `tlang=<key>`, which is a machine translation.
  - So in this version the auto `th` of a Thai clip is identical to `th-orig`. **This corrects BRD 11.1**, which says auto `th` is a translation; Task 15 records the correction.
  - With several ASR tracks (dubbed audio), one key can hold both a `tlang` entry and a non-`tlang` entry, because `setdefault` then `append`. So we classify **per entry**, not per key.
- **Untranslatable ASR language (for example `yue`):** `_video.py:4315-4328` adds `L-orig` only if the track `isTranslatable`, otherwise just `L`, with no `tlang`.
- **HLS subtitle entries:** `_video.py:3715-3721` merges subtitles found in HLS manifests into the dict that becomes `automatic_captions` (`_video.py:4041`). These entries have `protocol: 'm3u8_native'` and a `manifest.googlevideo.com/.../hls_timedtext_playlist/` URL. They are not single files, and we must ignore them.
- **Live chat:** live replays put a `live_chat` key into `info['subtitles']` (`_video.py:4396-4402`), and we must drop it.

**PO tokens and impersonation**
- **Missing tracks from PO tokens:** a caption URL carrying experiment `exp=xpe|xpv` needs a PO token, and the whole client's tracks are then skipped (`_video.py:4264-4281`). For default clients this only logs at debug level (`_video.py:3217-3226`). The default `SubsPoTokenPolicy` has `required=False` (`extractor/youtube/_base.py`, `BasePoTokenPolicy` defaults). Result: tracks can silently be missing. The app shows "คลิปนี้ไม่มีซับ" in that case, and the network test (T15) watches for it.
- **Impersonation is not available here:**
  - Each subtitle entry carries `impersonate: True`.
  - `downloader/common.py:511-519` only warns when no impersonation handler exists, and the request goes ahead.
  - `curl_cffi` is **not** installed in `.venv` (site-packages listing).
  - So yt-dlp itself downloads subtitles here without impersonation.

**Fetching**
- We fetch with `YoutubeDL.urlopen` (`YoutubeDL.py:4283`). It returns `networking.common.Response`, an `io.IOBase` with `read()`.
- Errors are `networking.exceptions.HTTPError` (`.status`, `exceptions.py:57-60`) and `RequestError`/`TransportError`.

### Live probes (2026-09-30, yt-dlp 2026.08.19, scratch scripts, nothing committed)
| Clip | License | Subtitle facts |
|---|---|---|
| `88o5Sk8_m1Y` "Thai Listening Practice EP.1", 372 s | CC BY | No owner subs. Auto has `th-orig` + `th`, both without `tlang`, plus 155 translated keys. **json3 th-orig:** 192 events, 95 with `aAppend: 1` whose only text is `"\n"`, 437 segs, 246 with `tOffsetMs`. Event keys are `tStartMs, dDurationMs, id, wWinId, wpWinPosId, wsWinStyleId, aAppend, segs`, and segs carry `acAsrConf`. The first event has no segs; it is a window definition with `dDurationMs` equal to the whole clip. Events overlap, for example event 2 runs 120–14719 ms while event 4 starts at 9160 ms. One token is `" 7:00 "`, with spaces. **vtt th-orig:** rolling style. Each real cue has 2 lines: line 1 repeats the previous text, and line 2 holds the new words as `<00:00:01.120><c>ครับ</c>…`, where the first word has no tag. Between real cues there is a 10 ms cue that only repeats text. The vtt tag times match json3 `tStartMs + tOffsetMs` (for example 1120). |
| `8lpOfyoxcvU` Thairath "3 นาทีคดีดัง", 403 s | CC BY | Audio is `th` "Thai original (default)" with `language_preference` 10, plus an `en-US` dub with preference −1. Auto has `en-US-orig` **and** `th-orig`. **json3 en-US-orig:** 311 events, 155 with `aAppend`, and English segs have a leading space (`" the"`). |
| `jNQXAC9IVRw` "Me at the zoo", 19 s (already a fixture) | none reported | Owner subs `en` and `de` (json3: one seg per event, no `tOffsetMs`, `"\n"` inside the text). Auto `en` and `de` are **HLS m3u8 entries only**. The description is 264 chars, and there are 3 chapters. |
| `aqz-KE-bpKQ` Big Buck Bunny (already a fixture) | CC BY | No subtitles at all (`subtitles == {}`, `automatic_captions == {}`). The description is 230 chars. This is our "no subtitles" clip. |
| `iG9CE55wbtY` TED "Do schools kill creativity?", 1203 s | TED CC BY-NC-ND (YouTube reports no license) | 64 owner languages including `th` (json3: 378 single-seg events, longest 118 chars; the first event is the translator credit). Auto `en-orig`. |

- **Timedtext URLs are signed and expire.** They carry `expire=` about 6–7 hours after the probe (URL expiry vs `time.time()`). The 24 h probe cache can therefore hold dead subtitle URLs, and fetching must re-probe once on 403/404/410. This is the same pattern as `storyboard.get_storyboard`.

### Not yet verified (the named task verifies it and records the result in its commit message)
- The PyThaiNLP version, its dependency tree, whether it works offline, import time, and whether import creates a data folder in the user's home (T2).
- That a translated URL built as `<orig timedtext url>&tlang=<code>` returns the translation. This mirrors `update_url_query` at `_video.py:4313` (T15 network test).

---

## Global Constraints
**Carried over from M2 and M1:**
- Everything under "Global Constraints" in `docs/superpowers/plans/2026-09-29-m2-preview.md` still applies, and through it `docs/superpowers/plans/2026-09-29-m1-followups.md`:
  - Python 3.13 with uv.
  - Bind to `127.0.0.1` only. Wrong Host → 421. Missing token or wrong Origin → 403.
  - The error envelope `{"error":{"code","message","detail"}}`.
  - Call external programs with an argument list, never `shell=True`. Use `pathlib`.
  - Only `yttoolkit.platform` checks the OS.
  - Studio Dark, and no Magic UI / Aceternity / Animate UI.
  - `core/` never imports `api/` or `platform/`.
  - Every screen state has all 4 variants (loading / empty / error / normal).
  - No TODO comments in merged code.
  - Unit and API tests never touch the network. Network tests carry `@pytest.mark.network`.
- **yt-dlp** is imported only in `src/yttoolkit/core/extractor.py`.

**Copy and UI:**
- Thai copy rules: never "กรุณา", no "!" in system text, and button labels start with a verb.
- Every web string lives in `web/src/i18n/th.ts`. The backend's user-facing messages live in `core/yterrors.MESSAGES`.
- At most one amber primary button per page. W2 has **none** in M3 (planner default).

**Build and tests:**
- ESLint reports 0 errors and 0 warnings. `uv run pytest -q -W error` and `npm test` print no warnings.
- `web/dist` is rebuilt and committed, only at wave gates and in T15.

**Line endings:**
- No CRLF in the repo except `*.bat`, **and** the golden subtitle files under `tests/fixtures/subs/golden/`. Those are stored byte-exact, and T12 marks them `-text` in `.gitattributes`.
- Generated `.srt` / `.txt` / `.md` use CRLF, UTF-8, and no BOM (AC-SUB-08).

**Processes:**
- Kill processes by PID only.
- The owner's app runs on :8787; never stop it or bind that port. E2E uses 8799 (`playwright.config.ts`). Manual and preview servers use 8791 with a temp `YT_TOOLKIT_DATA_ROOT`.

**Formats:**
- Frame timecodes stay `HH:MM:SS`. Subtitle times use `HH:MM:SS,mmm` (SRT), and `.md` headings use `[mm:ss]` or `[h:mm:ss]`.

**Commits:**
- Commit trailer, exactly: `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`. Use `git commit -F- <<'EOF' … EOF` so the trailer stays intact.

---

## Shared contracts (every lane codes against these)

### C1. Track ids and groups
- **Track id** = `<prefix>.<key>`, where the key is the yt-dlp caption key. Regex: `^[oat]\.[A-Za-z0-9_-]{1,64}$`.
  - `o.<key>`: owner subtitles (`info.subtitles`), `group: "owner"`. Example: `o.th`, `o.en`.
  - `a.<key>`: auto captions in an original language, `group: "original"`. Example: `a.th-orig`, `a.en-US-orig`, `a.yue`.
  - `t.<key>`: auto translation, `group: "translated"`. Example: `t.fr`.
- **`lang`** is the key without the `-orig` suffix (`a.th-orig` → `th`).
- **`name`** is yt-dlp's `name` (English, from YouTube). The web shows Thai language names via `Intl.DisplayNames` (C8).

### C2. Trimmed probe additions (`videos.probe_json`, written by T8)
```jsonc
{
  "probeVersion": 2,              // rows without it (M2) count as stale -> re-probe
  "description": "…",             // raw yt-dlp description, omitted when empty/whitespace
  "captions": {
    "owner":      [{"key": "th", "name": "Thai", "json3": "<url>", "vtt": "<url>"}],
    "original":   [{"key": "th-orig", "name": "Thai (Original)", "json3": "<url>", "vtt": "<url>"}],
    "translated": [{"key": "fr", "name": "French"}],
    "translateFrom": "th-orig"    // original-group key whose URLs get &tlang=<key>; null when no original track
  }
  // …existing M2 fields unchanged
}
```
**Classification rules (`core/tracks.trim_captions(raw)`):**
1. **Usable entry:** an entry is usable only if `ext in {"json3","vtt"}`, `protocol` is absent or `"https"`, and the URL host is `www.youtube.com` or `fake.invalid`.
2. **Dropping keys:** a key with no usable entry is dropped. `live_chat` is always dropped.
3. **owner:** every remaining `info.subtitles` key, in yt-dlp order. `json3`/`vtt` come from the usable entries without `tlang`.
4. **original:**
   - every `automatic_captions` key ending in `-orig`;
   - plus every other auto key K where `f"{K}-orig"` is not present and K has a usable entry **without** `tlang` (the untranslatable-ASR case).
5. **translated:** every other auto key K where `f"{K}-orig"` is not present and all usable entries of K have `tlang`. It stores `{key, name}` only.
6. **Duplicates:** an auto key K where `f"{K}-orig"` exists is dropped (it duplicates the original or is a mixed entry).
7. **`translateFrom`:** the original-group key chosen by `original_language()` (C3), else the first original key, else `null`.
8. **Translated URLs:** built at fetch time as the `translateFrom` track URL with query `tlang=<key>` added (`urllib.parse`: parse, set, re-encode).

### C3. Default track (`core/tracks.default_track_id`)
- **`original_language(trimmed)`**, first rule that applies:
  1. the base language (`lang.split("-")[0].lower()`) of the audio format that M2's `_audio_formats` marks `isOriginal`, when it matches an original-group key;
  2. that audio language by itself;
  3. the base of the first `-orig` key;
  4. `None`.
- **`default_track_id(tracks, original_lang, prefer="th")`**, first rule that applies:
  1. (Q8 = ก) an owner track whose base is `prefer`;
  2. an owner track whose base is `original_lang`;
  3. the original track `f"{original_lang…}-orig"` (base compare);
  4. the first owner track;
  5. `None`.
- Translated tracks are **never** returned.
- If Q8 = ข, pass `prefer=None`.

### C4. API (all under `/api`, sync `def` routes, `YtError` → envelope via `yt_error_response`)
| Method | Path | Response |
|---|---|---|
| GET | `/videos/{id}/subtitles` | `{tracks:[{id, lang, name, group}], defaultTrackId?}`. No subtitles → `{tracks: []}` (200, not an error). |
| GET | `/videos/{id}/subtitles/{trackId}/tokens` | `{hasWordTiming: bool, tokens:[{t, s, e}]}` (t = text, s/e = ms, ints). An unknown or malformed trackId, or a track that parses to 0 tokens → 404 `E_NO_SUBTITLES`. |
| GET | `/videos/{id}/subtitles/{trackId}/export` | Q1 = ก only. Query: `format=srt\|txt\|md`, `maxChars`, `lines`, `minMs`, `maxMs`, `mode=chars\|tokens`, `tokensPerCue?`. Returns the file as an attachment. The filename follows Q2 = ก: `<safe title>.<lang>.<ext>` in `filename*`, with ASCII fallback `subtitles.<lang>.<ext>`. `Content-Type: application/x-subrip; charset=utf-8` for srt, `text/plain; charset=utf-8` for txt, `text/markdown; charset=utf-8` for md. Bad options → 422 `E_BAD_REQUEST` (pydantic). |

- **Status:** `E_NO_SUBTITLES` → 404 (added to `STATUS_BY_CODE`).
- **Message:** `MESSAGES["E_NO_SUBTITLES"] = "คลิปนี้ไม่มีซับ"` (PRD section 7, verbatim).
- **`VideoInfo`** gains `description?: string`, the raw text, omitted when empty.

### C5. SubOptions, presets, limits (identical in Python and TS)
```ts
type SubOptions = { maxChars: number; lines: 1 | 2; minMs: number; maxMs: number;
                    mode: "chars" | "tokens"; tokensPerCue?: number }
PRESETS = {
  short:  { maxChars: 15, lines: 1, minMs: 800,  maxMs: 3000, mode: "chars" },
  medium: { maxChars: 25, lines: 1, minMs: 1200, maxMs: 5000, mode: "chars" },   // default
  long:   { maxChars: 42, lines: 2, minMs: 1500, maxMs: 7000, mode: "chars" },
}
LIMITS = { maxChars: [10, 60], lines: [1, 2], minMs: [300, 3000] /*step 100*/,
           maxMs: [1000, 10000] /*step 500*/, tokensPerCue: [1, 20] }
```
- `minMs < maxMs`.
- `tokensPerCue` is required when `mode == "tokens"` (the UI default is 3) and ignored otherwise.
- Python field names are snake_case (`max_chars` …). `options_from_dict()` accepts the camelCase keys.

### C6. `srt_builder` algorithm (the parity spec: Python T4 and TS T9 implement exactly this)

**Types**
- `Token{t, s, e}`
- `Cue{startMs, endMs, lines: string[]}`; the builder keeps each cue's token list internally.

**Parser guarantees** (T7 enforces them; the builder may assume them)
- Tokens are sorted by `s`, with `e >= s` and `e <= next.s`.
- Every `t` contains at least one non-space character.
- The only whitespace in any `t` is ASCII space `U+0020`.

**Helpers**
- `displayLen(text)` counts code points **except** Thai non-spacing marks: U+0E31, U+0E34–U+0E3A and U+0E47–U+0E4E (Q7 = ก). Under Q7 = ข it counts all code points.
- `cueText(tokens)` = the concatenation of `t`, with every run of spaces collapsed to one space (`/ {2,}/g` → `" "`), then trimmed of spaces at both ends.
- `limit = maxChars * lines`.
- `MERGE_LIMIT_FACTOR = 1.0` (Q3 = ก; 1.2 if Q3 = ข).

**1. Greedy grouping**
```
cues = []; cur = []
for tok in tokens:
    if cur:
        close = displayLen(cueText(cur + [tok])) > limit
             or tok.s - cur[-1].e >= 1000
             or tok.e - cur[0].s > maxMs
             or (mode == "tokens" and len(cur) >= tokensPerCue)
        if close: cues.append(Cue(cur)); cur = []
    cur.append(tok)
if cur: cues.append(Cue(cur))
# Cue(cur): startMs = cur[0].s, endMs = cur[-1].e
```

**2. Minimum duration** (index loop, re-check the same index after a merge)
```
i = 0
while i < len(cues):
    c, nxt = cues[i], cues[i+1] if i+1 < len(cues) else None
    if c.endMs - c.startMs < minMs:
        want = c.startMs + minMs
        c.endMs = min(want, nxt.startMs) if nxt else want
        if c.endMs - c.startMs < minMs and nxt is not None:
            merged = c.tokens + nxt.tokens
            if (displayLen(cueText(merged)) <= limit * MERGE_LIMIT_FACTOR
                    and nxt.endMs - c.startMs <= maxMs
                    and (mode != "tokens" or len(merged) <= tokensPerCue)):
                cues[i:i+2] = [Cue(merged, startMs=c.startMs, endMs=nxt.endMs)]
                continue
    i += 1
```

**3. Safety clamp:** for each cue except the last, `endMs = min(endMs, next.startMs)`.

**4. Lines**
- If `lines == 2`, `displayLen(text) > maxChars` and the cue has ≥ 2 tokens: split at the token boundary k (1..n−1) that minimises `|displayLen(cueText(tok[:k])) − displayLen(cueText(tok[k:]))|`. Ties go to the smaller k. The result is `lines = [cueText(tok[:k]), cueText(tok[k:])]`.
- Otherwise `lines = [cueText(tokens)]`.
- A single token longer than the limit stays whole (FR-SUB-9).

**Outputs**
- **`toSrt(cues)`:**
  - Each block is `f"{n}\r\n{ts(start)} --> {ts(end)}\r\n" + "\r\n".join(lines) + "\r\n"`, with n starting at 1.
  - Blocks are joined with `"\r\n"`. No cues → `""`.
  - `ts(ms)` = `HH:MM:SS,mmm`: zero-padded, hours at least 2 digits, floor division.
- **`toTxt(tokens)`:**
  - Paragraphs split where `tok.s − prev.e >= 2000`.
  - Each paragraph is `cueText(paragraph tokens)`.
  - Output = paragraphs joined with `"\r\n\r\n"` + `"\r\n"`. No tokens → `""`.
- **`toMd(tokens, {title, videoId, chapters:[{startMs, title}]})`:** build a list of lines, then join with `"\r\n"` + a trailing `"\r\n"`.
  - Line 1: `"# " + collapse(title)`, then `""`, then `f"https://www.youtube.com/watch?v={videoId}"`.
  - **Sections:**
    - With chapters (sorted by `startMs`), a token belongs to the last chapter with `startMs <= tok.s` (tokens before the first chapter go to the first chapter).
    - Without chapters, a token goes to section `floor(tok.s / 120000)`, whose start is `index * 120000`.
    - Empty sections are skipped.
  - For each section, append:
    - `""`, then `f"## [{mdTime(start)}] {collapse(chapterTitle)}"` (without chapters just `f"## [{mdTime(start)}]"`), then `""`;
    - then the section's paragraphs (same 2 s rule), separated by `""`.
  - `mdTime(ms)` = `mm:ss` when `ms < 3_600_000`, else `h:mm:ss`, with no leading zero on hours.
  - `collapse(x)` = replace every `\s+` with one space and trim; for titles only.
- **`cueStats(cues)` (TS only, for the preview):** `{count, avgChars: one decimal of the mean displayLen(lines.join(" ")), underOneSecond: count of endMs − startMs < 1000}`.

### C7. Parser output (`core/subparse.py`, T7)
- `ParsedTrack(tokens: list[Token], has_word_timing: bool, source: "json3" | "vtt")`
- `PARSER_VERSION = 1`
- `SubParseError(ValueError)` means the data is not usable, which triggers the vtt fallback.

### C8. Web contracts (T6 writes them; T9, T10, T13 and T14 consume them)
**`web/src/lib/types.ts` additions:**
```ts
export type SubtitleGroup = "owner" | "original" | "translated"
export type SubtitleTrack = { id: string; lang: string; name: string; group: SubtitleGroup }
export type SubtitleTracks = { tracks: SubtitleTrack[]; defaultTrackId?: string }
export type SubToken = { t: string; s: number; e: number }
export type SubTokens = { hasWordTiming: boolean; tokens: SubToken[] }
export type SubMode = "chars" | "tokens"
export type SubOptions = { maxChars: number; lines: 1 | 2; minMs: number; maxMs: number; mode: SubMode; tokensPerCue?: number }
export type SubPreset = "short" | "medium" | "long"
export type Cue = { startMs: number; endMs: number; lines: string[] }
export type SubExportFormat = "srt" | "txt" | "md"
// VideoInfo gains: description?: string
```

**`web/src/lib/sub-options.ts`:**
- `PRESETS`
- `LIMITS`
- `DEFAULT_PRESET = "medium"`
- `clampOptions(o: SubOptions): SubOptions`
- `presetOf(o): SubPreset | null`
- `exportPath(videoId, trackId, format, o): string`, which returns `/api/videos/<id>/subtitles/<trackId>/export?format=…&maxChars=…` in the fixed key order `format, maxChars, lines, minMs, maxMs, mode[, tokensPerCue]`.

**`web/src/lib/languages.ts`:** `languageName(code: string): string` uses `Intl.DisplayNames(["th"], {type: "language"})`, falling back to the code itself.

**`web/src/pages/video/url-state.ts`:** `useVideoParams()` returns:
- `tab`: `"frames" | "subs" | "transcript"`. Any other value, or none, means `"frames"`.
- `trackId: string | null`
- `at: number | null` (ms, integer ≥ 0)
- `update(patch: {tab?, trackId?, at?: number | null})`

`update` calls `navigate({search}, {replace: true, preventScrollReset: true, state: location.state})`. `replace` keeps M2's "back to W1 in one step" breadcrumb rule.

**`web/src/pages/video/subs-queries.ts`:**
- `subtitlesQuery(videoId, enabled)`: key `["subtitles", id]`, `retry: false`, `staleTime: 60_000`.
- `tokensQuery(videoId, trackId)`: key `["subtokens", id, trackId]`, enabled only with a trackId, `retry: false`, `staleTime: Infinity`.

**`web/src/pages/video/subs-settings.ts`:** `useSubSettings()` returns `{preset: SubPreset | "custom", options: SubOptions, choosePreset(p), setCustom(o)}`.
- Stored in localStorage under key `yt-toolkit.subs` as `{v: 1, preset, custom}`.
- A wrong version or bad data → defaults (medium).
- When storage is blocked, it keeps the values in memory (same guard pattern as `components/theme-provider.tsx`).

**Hooks written in Wave 2:**
- `web/src/pages/video/use-cues.ts` (T9): `useCues(tokens: SubToken[] | undefined, options): Cue[]`, `useMemo` over `buildCues`.
- `web/src/pages/video/track-label.ts` (T10): `trackLabel(track): string`, using th.subs.names.*.

### C9. Thai strings (T5 writes this block into `th.ts` verbatim; nobody else edits `th.ts`)
Add these keys to `video` and `frames`, then add the `subs` and `transcript` top-level objects:
```ts
// inside video:
    tabs: { label: "เครื่องมือของคลิปนี้", frames: "ภาพเฟรม", subs: "ซับ", transcript: "ทรานสคริปต์" },
    copyGroup: "คัดลอกข้อมูลคลิป",
    copyChapters: "คัดลอก chapter",
    copyDescription: "คัดลอกคำอธิบาย",
    copied: "คัดลอกแล้ว",
    copyFailed: "คัดลอกไม่สำเร็จ ลองอีกครั้ง",
    trackBadge: "ซับ: {name}",
// inside frames:
    viewSubs: "ดูซับช่วงนี้",
// new top-level:
  subs: {
    title: "ซับ",
    loading: "กำลังโหลดซับ",
    loadError: "โหลดซับไม่สำเร็จ",
    none: "คลิปนี้ไม่มีซับ",
    trackLabel: "แทร็กซับ",
    trackPlaceholder: "เลือกแทร็กซับ",
    pickHint: "คลิปนี้ไม่มีซับจากเจ้าของคลิปหรือซับภาษาต้นฉบับ เลือกแทร็กที่ต้องการจากรายการ",
    groups: { owner: "ซับจากเจ้าของคลิป", original: "ซับอัตโนมัติภาษาต้นฉบับ", translated: "ซับแปลอัตโนมัติ" },
    names: { owner: "{lang}", original: "{lang} (อัตโนมัติ)", translated: "{lang} (แปลอัตโนมัติ)" },
    openTranslated: "เลือกซับแปลอัตโนมัติ…",
    translatedTitle: "ซับแปลอัตโนมัติ",
    translatedWarning: "ซับกลุ่มนี้ยูทูปแปลด้วยเครื่อง คุณภาพต่ำและอาจผิดความหมาย ใช้เมื่อไม่มีซับภาษาที่ต้องการเท่านั้น",
    searchLanguage: "ค้นหาภาษา",
    noLanguage: "ไม่พบภาษานี้",
    presetLabel: "ความยาวซับ",
    presets: { short: "สั้น", medium: "กลาง", long: "ยาว" },
    presetHints: { short: "TikTok / Reels", medium: "คลิปทั่วไป", long: "สไตล์ภาพยนตร์" },
    custom: "ปรับเอง",
    customInUse: "ใช้ค่าที่ปรับเอง",
    maxChars: "ตัวอักษรสูงสุดต่อบรรทัด",
    lines: "บรรทัดต่อซับ",
    lineCount: "{n} บรรทัด",
    minSeconds: "แสดงอย่างน้อย (วินาที)",
    maxSeconds: "แสดงนานสุด (วินาที)",
    byWords: "นับเป็นคำ",
    wordsPerCue: "คำต่อซับ",
    previewTitle: "ตัวอย่าง 5 ซับแรก",
    stats: "{n} ซับ · ยาวเฉลี่ย {avg} ตัวอักษร · แสดงสั้นกว่า 1 วินาที {short} ซับ",
    noWordTiming: "แทร็กนี้ไม่มีเวลาระดับคำ ระบบแบ่งคำให้เอง เวลาอาจคลาดเล็กน้อย",
    downloadGroup: "โหลดซับ",
    downloadSrt: "โหลด .srt",
    downloadTxt: "โหลด .txt",
    downloadMd: "โหลด .md",
    copyText: "คัดลอกข้อความ",
    textCopied: "คัดลอกข้อความแล้ว",
    copyFailed: "คัดลอกไม่สำเร็จ ลองอีกครั้ง",
    preparing: "กำลังเตรียมไฟล์…",
    downloadFailed: "โหลดซับไม่สำเร็จ ลองอีกครั้ง",
  },
  transcript: {
    title: "ทรานสคริปต์",
    searchLabel: "ค้นหาคำในทรานสคริปต์",
    searchPlaceholder: "พิมพ์คำที่อยากหา",
    clearSearch: "ล้างคำค้น",
    found: "พบ {n} บรรทัด",
    notFound: "ไม่พบคำนี้ในทรานสคริปต์",
    hint: "คลิกบรรทัดเพื่อดูภาพเฟรมของช่วงนั้น",
    source: "จากแทร็ก {name} · เปลี่ยนแทร็กและความยาวบรรทัดได้ที่แท็บซับ",
    linesLabel: "บรรทัดในทรานสคริปต์",
    goToSubs: "ไปเลือกแทร็กที่แท็บซับ",
  },
```
If Q1 = ข, T5 still writes the whole block; the unused `download*` keys are removed by T15.

### C10. Fixture names (T1 creates them; everyone else refers to them by these names)
| Path | What |
|---|---|
| `tests/fixtures/probe/88o5Sk8_m1Y.json` | Real probe, trimmed like M2, plus `description` and caption dicts (see T1) |
| `tests/fixtures/probe/8lpOfyoxcvU.json` | Real probe (two `-orig` tracks, Thai original audio) |
| `tests/fixtures/probe/OWNERTHSUB1.json` | Synthetic (Q9 = ข): an English-language clip (`language: "en"`, English title "Owner Thai subtitle test", `duration: 240`) with owner `th`, `en` (json3 + vtt) + auto `en-orig`; no storyboard formats |
| `tests/fixtures/probe/aqz-KE-bpKQ.json`, `jNQXAC9IVRw.json` | Existing; T1 adds `description`, `subtitles`, `automatic_captions` |
| `tests/fixtures/probe/LONGTHAI1hr.json` | Synthetic, 3720 s, a 1 h Thai perf clip (json3 URL has `?repeat=10`) |
| `tests/fixtures/probe/VTTFALLBAK1.json` | Synthetic: the json3 URL points at `broken.json3`, the vtt at the real 88o5 vtt |
| `tests/fixtures/probe/NOORIGSUB01.json` | Synthetic: auto `yue` (no tlang) + translated `en`, `th`; no owner, no `-orig` |
| `tests/fixtures/subs/88o5Sk8_m1Y/th-orig.json3`, `th-orig.vtt`, `tlang-en.json3` | Real Thai ASR (CC BY) + one translation |
| `tests/fixtures/subs/8lpOfyoxcvU/en-US-orig.json3`, `th-orig.json3` | Real English ASR (dub) + Thai ASR (CC BY) |
| `tests/fixtures/subs/jNQXAC9IVRw/en.json3`, `en.vtt`, `de.json3` | Real owner subtitles, no word timing |
| `tests/fixtures/subs/OWNERTHSUB1/th.json3`, `en.json3` | Hand-written (Q9 = ข) in the exact shape of real YouTube owner json3 (one seg per event, no word timing, `wpWinPosId`/`wsWinStyleId` fields like `jNQXAC9IVRw/en.json3`): 20 Thai sentences written by us, including one event with an embedded `
` line break, one sentence ≥ 110 characters, a translator-credit line ("แปลโดย ทีมทดสอบ"), and a gap ≥ 3 s; `en.json3` = the matching 20 English sentences |
| `tests/fixtures/subs/VTTFALLBAK1/broken.json3` | The literal text `{"events": [` (truncated JSON) |
| `tests/fixtures/storyboard/88o5Sk8_m1Y/M*.jpg` | Real sb0 grids (CC BY), so the transcript→frame E2E has frames |
| `tests/fixtures/subs/builder-cases.json` | T4: hand-checked builder cases |
| `tests/fixtures/subs/tokens/<name>.json`, `tests/fixtures/subs/golden/<name>.<preset>.{srt,txt,md}` | T12: parser tokens + byte-exact outputs |

**Fake URL scheme:** `https://fake.invalid/subs/<videoId>/<key>.<ext>[?tlang=<code>][&repeat=<n>]`. `FakeExtractor.fetch_subtitle` (T3) maps it:
- plain → `subs/<videoId>/<key>.<ext>`;
- with `tlang` → `subs/<videoId>/tlang-<code>.<ext>`;
- with `repeat=n` (json3 only) → the file tiled n times.

---

## File structure

| File | Responsibility | Task |
|---|---|---|
| `src/yttoolkit/core/thai_fallback.py` | Thai word split (PyThaiNLP newmm), lazy import, data dir config | T2 |
| `src/yttoolkit/core/extractor.py` | + `fetch_subtitle(url)` on the protocol, the real extractor and the fake | T3 |
| `src/yttoolkit/core/srt_builder.py` | Pure tokens → cues → srt/txt/md | T4 |
| `src/yttoolkit/core/subparse.py` | json3 / vtt bytes → tokens (+ block splitting) | T7 |
| `src/yttoolkit/core/tracks.py` | Raw captions → trimmed captions; track list; default track | T8 |
| `src/yttoolkit/core/videos.py` | Trim adds `probeVersion`, `description`, `captions`; VideoInfo adds `description` | T8 |
| `src/yttoolkit/core/subtitles.py` | SubtitleService: tracks, tokens (cache, fallback, re-probe), export | T11 |
| `src/yttoolkit/api/subtitles.py` | 3 routes | T11 |
| `web/src/lib/srt-builder.ts` | TS port of C6 | T9 |
| `web/src/pages/video/tabs.tsx` | Tab bar + panels | T10 |
| `web/src/pages/video/subs-panel.tsx` + `subs/*` | ซับ tab | T13 |
| `web/src/pages/video/transcript-panel.tsx` + `transcript/*` | ทรานสคริปต์ tab | T14 |

---

## Wave 1

### Task 1: Capture subtitle fixtures from real YouTube (network)

**Files:**
- Modify: `tests/fixtures/probe/aqz-KE-bpKQ.json`, `tests/fixtures/probe/jNQXAC9IVRw.json`, `tests/fixtures/README.md`
- Create: every other `tests/fixtures/probe/*.json` and `tests/fixtures/subs/<videoId>/*` row of C10, plus `tests/fixtures/storyboard/88o5Sk8_m1Y/M*.jpg`
- Scratch only (not committed): `<scratchpad>/capture_m3.py`

**Depends on:** nothing. It needs network and the Q9 answer.

**Interfaces:**
- Consumes: `YtDlpExtractor().probe(id)` (existing) for probes, and `yt_dlp.YoutubeDL({"quiet": True}).urlopen(url).read()` for subtitle bytes. This is allowed in a scratch script; it mirrors what T3 will implement.
- Produces: the C10 files, with the fake URL scheme.

- [ ] **Step 1: Write the capture script in the scratchpad.** For each real clip (`88o5Sk8_m1Y`, `8lpOfyoxcvU`, `jNQXAC9IVRw`, `aqz-KE-bpKQ`):
  1. Probe it with `YtDlpExtractor().probe`.
  2. Keep the M2 field set listed in `tests/fixtures/README.md`, plus `description`, `subtitles` and `automatic_captions`.
  3. Inside `subtitles`/`automatic_captions`, keep per key only the entries with `ext` in `json3`/`vtt`, plus any `protocol: m3u8_native` entries (jNQ has them; keep them, rewritten to `https://fake.invalid/hls/<id>/<key>.m3u8`, so T8 can prove they are ignored).
  4. Keep entry fields `ext, url, name, protocol` (when present).
  5. Rewrite every timedtext URL to `https://fake.invalid/subs/<id>/<key>.<ext>`, keeping `?tlang=<code>` when the real URL had one.
  6. Limit translated auto keys to `en, ja, fr, ko, zh-Hans` (whichever exist).
  7. (Q9 = ข) No TED capture. `OWNERTHSUB1` is written by hand in Step 3; before writing it, look at the real owner json3 of `jNQXAC9IVRw` (and, read-only in the scratchpad, any real owner Thai json3) so the hand-made file copies the real field shape. Nothing from a third-party clip is committed.
  8. Rewrite storyboard fragment URLs exactly as M2 did (`https://fake.invalid/storyboard/<id>/M<n>.jpg` for sb0; other sb formats get `/sbN/` paths).
- [ ] **Step 2: Download the subtitle files listed in C10** with the real (pre-rewrite) URLs, byte for byte:
  - (Q9 = ข) `OWNERTHSUB1/th.json3` and `en.json3` are hand-written in Step 3, not downloaded.
  - For `88o5Sk8_m1Y/tlang-en.json3`: take the json3 entry of auto key `en`, which has `tlang=en`.
  - Download the 88o5 sb0 grids to `tests/fixtures/storyboard/88o5Sk8_m1Y/M<n>.jpg`, the same way M2 captured BBB.
- [ ] **Step 3: Write the synthetic probes** (same trimmed shape; `live_status: "not_live"`; no storyboard formats; `channel: "ชุดทดสอบ"`):

  | File | Contents |
  |---|---|
  | `LONGTHAI1hr.json` | `id: "LONGTHAI1hr"`, `title: "ทดสอบซับยาว 1 ชั่วโมง"`, `duration: 3720`. Auto `th-orig` json3 = `https://fake.invalid/subs/88o5Sk8_m1Y/th-orig.json3?repeat=10`, vtt = `…/th-orig.vtt`. Audio format `{format_id: "140", vcodec: "none", acodec: "mp4a.40.2", language: "th", format_note: "Thai original (default), medium", language_preference: 10}`. |
  | `VTTFALLBAK1.json` | `id: "VTTFALLBAK1"`, `duration: 372`. Auto `th-orig`: json3 → `https://fake.invalid/subs/VTTFALLBAK1/broken.json3`, vtt → `https://fake.invalid/subs/88o5Sk8_m1Y/th-orig.vtt`. |
  | `NOORIGSUB01.json` | `id: "NOORIGSUB01"`, `duration: 372`, no `subtitles`. Auto: `yue` = `[{ext: json3, url: "https://fake.invalid/subs/88o5Sk8_m1Y/th-orig.json3"}]`; `en` and `th` = json3 entries whose URL ends in `?tlang=en` / `?tlang=th` on the same base. |
  | `subs/VTTFALLBAK1/broken.json3` | `{"events": [` |
| `OWNERTHSUB1.json` + `subs/OWNERTHSUB1/{th,en}.json3` | Q9 = ข, hand-written. See C10 for the exact contents. Owner `th`/`en` json3 entries use URLs `https://fake.invalid/subs/OWNERTHSUB1/<key>.json3`, and auto `en-orig` points at `…/en.json3`. |

- [ ] **Step 4: Check the fixtures.** Run `uv run pytest -q -W error`: M2 tests must still pass, because the fixtures only gain fields. Also check:
  - `python -c` load every probe JSON;
  - `88o5Sk8_m1Y/th-orig.json3` has ≥ 90 events with `aAppend`;
  - `th-orig.vtt` starts with `WEBVTT`;
  - every file is LF or binary as downloaded (vtt from YouTube is LF; do not convert).
- [ ] **Step 5: Update `tests/fixtures/README.md`.** Add sections `subs/`, the new probes and the new storyboard folder:
  - capture date, yt-dlp version, the URL rewrite rules, the trimming rules, `tlang`, `repeat` and `broken.json3`;
  - licenses: 88o5Sk8_m1Y and 8lpOfyoxcvU are CC BY (channel names from the probe, with links); "Me at the zoo" stays as before; `OWNERTHSUB1` is synthetic, written by the project (no third-party text); TED clip not stored. Old: test-only, private repo (Q9 = ก).
- [ ] **Step 6: Commit.**
```bash
git add tests/fixtures
git commit -F- <<'EOF'
test(fixtures): capture M3 subtitle fixtures (Thai json3 with aAppend, English json3, auto vtt, owner subs)

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
EOF
```

### Task 2: PyThaiNLP dependency and `core/thai_fallback.py`

**Files:**
- Modify: `pyproject.toml`, `uv.lock`
- Create: `src/yttoolkit/core/thai_fallback.py`, `tests/unit/test_thai_fallback.py`

**Interfaces (produces):**
- `DATA_ENV: str`: the name of PyThaiNLP's data-dir env var (found in Step 1).
- `configure(data_dir: Path) -> None`: sets `os.environ[DATA_ENV]` before first import, only if it is not set already.
- `has_thai(text: str) -> bool`: any char in U+0E00–U+0E7F.
- `split_words(text: str) -> list[str]`: newmm words.
  - Whitespace-only pieces are glued as a leading space onto the next word. Trailing whitespace is glued onto the last word.
  - `"".join(result) == text` always.
  - Empty text → `[]`.

- [ ] **Step 1: Research and record.**
  1. `uv add pythainlp` (latest).
  2. Record in the commit message: the version, `uv tree --package pythainlp` (the dependency list), and the license.
  3. Check that `word_tokenize("ผมน่ะ ประทับใจมากเลย", engine="newmm", keep_whitespace=True)` works **offline**. Test with the network disabled, or check that the dictionary ships in the wheel.
  4. Measure the cold import + first call time.
  5. Grep the installed package for the data-dir env var name (`PYTHAINLP_DATA_DIR` or `PYTHAINLP_DATA`) and whether import creates `~/pythainlp-data`.
  6. If the dependency tree pulls anything heavy (torch, numpy > needed, network downloads for newmm), stop and report to the controller.
- [ ] **Step 2: Write the failing tests** in `tests/unit/test_thai_fallback.py`:
```python
import os

from yttoolkit.core import thai_fallback as tf

def test_split_words_rejoins_exactly():
    text = "ผมน่ะ ประทับใจมากเลย"
    words = tf.split_words(text)
    assert "".join(words) == text
    assert len(words) >= 4
    assert all(w.strip() for w in words)          # no whitespace-only pieces

def test_leading_space_goes_to_next_word():
    words = tf.split_words("สวัสดี ครับ")
    assert words[-1].startswith(" ")

def test_has_thai():
    assert tf.has_thai("abc ไทย") and not tf.has_thai("hello world")

def test_empty():
    assert tf.split_words("") == []

def test_configure_sets_env_once(tmp_path, monkeypatch):
    # tf.DATA_ENV = the env var name found in Step 1 (module constant)
    monkeypatch.delenv(tf.DATA_ENV, raising=False)
    tf.configure(tmp_path / "pythainlp")
    assert os.environ[tf.DATA_ENV] == str(tmp_path / "pythainlp")
    tf.configure(tmp_path / "other")                  # an existing value is never overwritten
    assert os.environ[tf.DATA_ENV] == str(tmp_path / "pythainlp")
```
  Also add a test that no word boundary falls inside `"ประทับใจ"` and `"มากเลย"`. The expected splits come from the Step 1 run; hard-code them.
- [ ] **Step 3: Run** `uv run pytest tests/unit/test_thai_fallback.py -q -W error`. Expected: FAIL (module missing).
- [ ] **Step 4: Implement** a lazy `from pythainlp.tokenize import word_tokenize` inside `split_words`, a module-level `threading.Lock`, and `configure()` setting the env var **only** if it is not already set. Test `configure` with `monkeypatch.delenv`.
- [ ] **Step 5: Run** the file, then `uv run pytest -q -W error`. Expected: PASS, with no warnings (PyThaiNLP must not emit DeprecationWarning; if it does, pin a version that doesn't and record why).
- [ ] **Step 6: Commit** `pyproject.toml uv.lock src/yttoolkit/core/thai_fallback.py tests/unit/test_thai_fallback.py` with the message `feat(core): Thai word split fallback via PyThaiNLP newmm`. The body holds the Step 1 findings, followed by the trailer.

### Task 3: Extractor `fetch_subtitle` (real + fake)

**Files:**
- Modify: `src/yttoolkit/core/extractor.py`, `tests/unit/test_extractor.py`

**Interfaces (produces):**
- `Extractor.fetch_subtitle(self, url: str) -> bytes` is added to the Protocol.
- `YtDlpExtractor.fetch_subtitle` fetches through `yt_dlp.YoutubeDL({**_PROBE_OPTS, "logger": _YtDlpLogger()}).urlopen(url)` inside `with` blocks and returns `resp.read()`. Error mapping:
  - `networking.exceptions.HTTPError` with `.status == 429` → `YtError("E_BOT_CHECK", …)`
  - `.status in (403, 404, 410)` → `YtError("E_NETWORK", …)` (a dead signed link; the caller re-probes)
  - any other `HTTPError` or `RequestError` → `YtError("E_NETWORK", …)`
  - any other `YoutubeDLError` → `classify(msg)`
  - any other `Exception` → `E_UNKNOWN`
  - ANSI codes are stripped as in `_extract`.
- `FakeExtractor.SUBS_PREFIX = "https://fake.invalid/subs/"` and `FakeExtractor.fetch_subtitle(url)`:
  - records `("fetch_subtitle", url)` in `calls`;
  - parses path `<videoId>/<name>.<ext>` and query;
  - every path part must match `_SAFE_NAME` (after stripping the extension), and the resolved path must stay under `root/"subs"`;
  - `tlang=X` → file `tlang-X.<ext>`;
  - `repeat=n` (1..50, json3 only):
    1. load the JSON;
    2. `span` = `max(tStartMs + dDurationMs)` over all events, rounded up to the next 1000 ms;
    3. output `events` = n copies, with copy k shifting every event's `tStartMs` by `k*span`;
    4. other top-level keys are kept from the original;
    5. dump `ensure_ascii=False`.
  - A missing file or bad path → `YtError("E_NETWORK", "fake: ไม่มีไฟล์สำหรับ …")`.

- [ ] **Step 1: Write the failing tests** (no network: use `tmp_path` fixture trees and monkeypatch `yt_dlp.YoutubeDL`).
  - **Fake:** plain file bytes returned unchanged.
  - **Fake:** `?tlang=en` maps to `tlang-en.json3`.
  - **Fake:** `?repeat=3` on a 2-event json3 gives 6 events, with the third copy shifted by `2*span`.
  - **Fake:** `..`, `%2e%2e`, backslash and absolute paths, another host, and a missing file → `E_NETWORK`.
  - **Fake:** calls recorded.
  - **Real** (monkeypatched `YoutubeDL` whose `urlopen` returns `io.BytesIO(b"x")` or raises `HTTPError`): the status 429/404/500 mapping, and the `RequestError` mapping. Build a real `yt_dlp.networking.exceptions.HTTPError` from a `yt_dlp.networking.common.Response(io.BytesIO(b""), url, {}, status=404)`.
  - The `Extractor` Protocol `isinstance` check passes for both classes.
- [ ] **Step 2: Run** `uv run pytest tests/unit/test_extractor.py -q -W error`. Expected: the new tests FAIL.
- [ ] **Step 3: Implement** as specified. Import `yt_dlp` lazily inside the method, like `_extract`.
- [ ] **Step 4: Run** the file, then `uv run pytest -q -W error`. Expected: PASS.
- [ ] **Step 5: Commit** with the message `feat(core): fetch subtitle files through yt-dlp (fake mode maps fake.invalid/subs)` + trailer.

### Task 4: Python `srt_builder` + shared builder cases

**Files:**
- Create: `src/yttoolkit/core/srt_builder.py`, `tests/unit/test_srt_builder.py`, `tests/fixtures/subs/builder-cases.json`

**Interfaces (produces):**
```python
@dataclass(frozen=True) class Token: t: str; s: int; e: int
@dataclass(frozen=True) class SubOptions: max_chars: int; lines: int; min_ms: int; max_ms: int; mode: str = "chars"; tokens_per_cue: int | None = None
@dataclass(frozen=True) class Cue: start_ms: int; end_ms: int; lines: tuple[str, ...]
PRESETS: dict[str, SubOptions]          # "short" | "medium" | "long" (C5)
MERGE_LIMIT_FACTOR: float               # C6 (Q3)
def options_from_dict(d: Mapping[str, Any]) -> SubOptions   # camelCase keys, validates C5 LIMITS, raises ValueError
def display_len(text: str) -> int
def cue_text(tokens: Sequence[Token]) -> str
def build_cues(tokens: Sequence[Token], opts: SubOptions) -> list[Cue]
def to_srt(cues: Sequence[Cue]) -> str
def to_txt(tokens: Sequence[Token]) -> str
def to_md(tokens: Sequence[Token], *, title: str, video_id: str, chapters: Sequence[tuple[int, str]]) -> str
```

**`builder-cases.json` schema** (read by the TS tests in T9):
```json
{"version": 1, "cases": [
  {"name": "english-char-limit",
   "options": {"maxChars": 25, "lines": 1, "minMs": 1200, "maxMs": 5000, "mode": "chars"},
   "tokens": [{"t": "Hello", "s": 0, "e": 400}],
   "cues": [{"startMs": 0, "endMs": 1200, "lines": ["Hello"]}],
   "srt": "1\r\n00:00:00,000 --> 00:00:01,200\r\nHello\r\n",
   "txt": "Hello\r\n"}
]}
```
Optionally a case also carries `"md": {"title", "videoId", "chapters": [{"startMs", "title"}], "out": "…"}`.

- [ ] **Step 1: Write `builder-cases.json`** with these hand-checked cases. Work each one out on paper from C6; the worked answers for the first three are given.
  1. **`english-char-limit` (medium).** Tokens `Hello`(0-400) ` world`(400-900) ` this`(900-1300) ` is`(1300-1500) ` a`(1500-1600) ` test`(1600-2000) ` of`(2000-2200) ` subs`(2200-2600).
     - Cues: `[0,1600,"Hello world this is a"]` (adding " test" makes 26 > 25) and `[1600,2800,"test of subs"]` (the last cue is extended to 1200 ms).
     - SRT: `"1\r\n00:00:00,000 --> 00:00:01,600\r\nHello world this is a\r\n\r\n2\r\n00:00:01,600 --> 00:00:02,800\r\ntest of subs\r\n"`.
  2. **`thai-display-len` (maxChars 3, lines 1, minMs 300, maxMs 5000).**
     - Tokens `ที่`(0-500) `น้ำ`(500-1000) `ดี`(1000-1500) have display lengths 1, 2, 2.
     - Cues: `[0,1000,"ที่น้ำ"]` (length 3 fits) and `[1000,1500,"ดี"]`.
  3. **`silence-gap` (medium).** Tokens `a`(0-500), ` b`(1500-2000) (gap 1000 → split) and ` c`(2999-3100) (gap 999 → same cue as b).
     - Before extension: `[0,500,"a"]`, `[1500,3100,"b c"]`.
     - `a` is short (500 < 1200), so it is extended to `min(0+1200, 1500) = 1200`. That reaches `minMs`, so no merge is tried.
     - Final: `[0,1200,"a"]`, `[1500,3100,"b c"]`.
  4. **`max-duration`** (maxMs 3000; tokens every 1000 ms without gaps) → a split when `tok.e − cur[0].s > 3000`.
  5. **`tokens-mode`** (mode `tokens`, tokensPerCue 3; 7 short tokens) → cues of 3, 3 and 1 tokens (then the min-duration rules).
  6. **`single-long-token`** (a 40-char token at medium) → one cue with that token alone; the neighbours are in their own cues.
  7. **`min-extend-adjacent`** → a short cue extended only up to the next cue's start, and left short because the merge would exceed the limit (allowed: adjacent).
  8. **`min-merge`** → a short cue merged with the next when the merged length is ≤ limit × factor.
  9. **`merge-refused-over-limit`** → a merge refused (length 26 at medium with factor 1.0).
  10. **`two-lines-middle`** (long preset; 50 chars across 8 tokens) → a split at the balanced boundary. Include a tie that must pick the smaller k.
  11. **`two-lines-fits-one`** (long preset; 30 chars) → a single line.
  12. **`whitespace-collapse`** → tokens with `"  "` inside and at the edges; the text is collapsed and trimmed.
  13. **`over-one-hour`** → SRT timestamps `01:02:03,004`, and numbering continues past 9.
  14. **`empty`** → no tokens gives `cues: []`, `srt: ""`, `txt: ""`.
  15. **`txt-paragraphs`** → gap 2000 starts a new paragraph (`"\r\n\r\n"`); gap 1999 doesn't.
  16. **`md-chapters` and `md-two-minute-sections`** → both md rules, including `[1:00:00]` formatting and skipping empty sections.
- [ ] **Step 2: Write the failing tests.**
  - A parametrized test runs every JSON case through `build_cues`, `to_srt`, `to_txt` and (when present) `to_md`, comparing exactly.
  - Property tests over random token lists (seeded `random.Random(3)`, 200 runs, all presets). They assert:
    - cues partition the tokens in order;
    - no `end > next.start`;
    - `start < end` except zero-duration input;
    - every line ≤ limit unless the cue has one token;
    - a cue shorter than `min_ms` exists only when its `end_ms == next.start_ms` (AC-SUB-05);
    - numbering in SRT is 1..n;
    - `"\n"` appears only as part of `"\r\n"` (AC-SUB-08).
  - `options_from_dict` rejects values outside `LIMITS`, `minMs >= maxMs`, and a missing `tokensPerCue` in tokens mode.
- [ ] **Step 3: Run** `uv run pytest tests/unit/test_srt_builder.py -q -W error`. Expected: FAIL (module missing).
- [ ] **Step 4: Implement** C6 exactly. It is a pure module with no imports from the app except `dataclasses`/`typing`/`re`.
- [ ] **Step 5: Run** until green, then `uv run pytest -q -W error`.
- [ ] **Step 6: Commit** the 3 files with the message `feat(core): srt_builder (tokens -> cues -> srt/txt/md) with shared cases` + trailer.

### Task 5: Web UI kit + all M3 Thai strings

**Files:**
- Modify: `web/src/i18n/th.ts`, `web/package.json`, `web/package-lock.json` (only if shadcn adds dependencies)
- Create: `web/src/components/ui/{select,toggle-group,toggle,slider,field,label,collapsible,scroll-area,switch}.tsx` (whatever the CLI generates for those components)

- [ ] **Step 1: Add the components.** In `web/`, run `npx shadcn@latest add select toggle-group slider field collapsible scroll-area switch`.
  - **Do not** pass `--overwrite`. Existing files (button, dialog…) must stay untouched; confirm with `git diff --stat src/components/ui` showing only new files.
  - Check that the generated files import from `@base-ui/react` (the project style). Fix anything that imports Radix.
- [ ] **Step 2: Paste the C9 block into `th.ts`** verbatim at the stated places.
- [ ] **Step 3: Check the copy.**
  - `grep -n "กรุณา\|!" src/i18n/th.ts` → no new hits.
  - Every new button label starts with a verb (โหลด, คัดลอก, เลือก, ล้าง).
- [ ] **Step 4: Run** `npm run typecheck && npm run lint && npm test`. Expected: PASS, with 0 lint errors/warnings (the ui folder already has the react-refresh rule off).
- [ ] **Step 5: Commit** with the message `feat(web): M3 UI kit (select, toggle-group, slider, field, collapsible, scroll-area, switch) and Thai strings` + trailer.

### Task 6: Web data layer (types, options, URL state, queries, settings, language names)

**Files:**
- Modify: `web/src/lib/types.ts`
- Create:
  - `web/src/lib/sub-options.ts` (+ `sub-options.test.ts`)
  - `web/src/lib/languages.ts` (+ `languages.test.ts`)
  - `web/src/pages/video/url-state.ts` (+ `url-state.test.ts`)
  - `web/src/pages/video/subs-queries.ts`
  - `web/src/pages/video/subs-settings.ts` (+ `subs-settings.test.ts`)

**Interfaces:** exactly C8. Nothing here uses `th.ts`.

**Why pure helpers:** Vitest here runs in the node environment, with no jsdom or Testing Library (checked: `web/node_modules` has neither, and existing hook tests such as `use-analyze.test.ts` test pure helpers). So each hook is a thin wrapper over pure, exported helpers, and the tests cover the helpers. The hooks themselves are covered by the E2E specs of T10, T13 and T14. The helpers:
- in `url-state.ts`: `readVideoParams(search: URLSearchParams): {tab, trackId, at}` and `patchSearch(search: URLSearchParams, patch): string` (returns the new `?…` string, keeping unrelated params);
- in `subs-settings.ts`: `loadSubSettings(storage: Pick<Storage, "getItem"> | null)` and `saveSubSettings(storage: Pick<Storage, "setItem"> | null, value)`.

- [ ] **Step 1: Write the failing Vitest tests.**
  - **`sub-options`:**
    - `presetOf(PRESETS.medium) === "medium"`, and a modified one gives `null`;
    - `clampOptions` clamps every field to `LIMITS`, forces `minMs < maxMs` (raising `maxMs` to `minMs + 500`), and drops `tokensPerCue` in chars mode;
    - `exportPath("aqz-KE-bpKQ", "a.th-orig", "srt", PRESETS.medium)` equals `/api/videos/aqz-KE-bpKQ/subtitles/a.th-orig/export?format=srt&maxChars=25&lines=1&minMs=1200&maxMs=5000&mode=chars`.
  - **`languages`:** `languageName("th")` is `"ไทย"`, `languageName("en-US")` contains `"อังกฤษ"`, and `languageName("xx-bogus")` returns `"xx-bogus"`.
  - **`url-state`:**
    - `readVideoParams(new URLSearchParams("tab=subs&track=a.th-orig&at=90500"))` reads all three;
    - `tab=weird` reads as `frames`;
    - `at=-5`, `at=abc` and `at=1.5` read as null;
    - a malformed `track` (`x.th`) reads as null;
    - `patchSearch(params, {tab: "transcript", at: 1000})` keeps `track` and returns `?tab=transcript&track=a.th-orig&at=1000`;
    - `{at: null}` removes `at`;
    - `{tab: "frames"}` removes `tab` (the default stays out of the URL).

    The `useVideoParams` wrapper calls `navigate({search: patchSearch(…)}, {replace: true, preventScrollReset: true, state: location.state})`. Its replace semantics are checked by T10's E2E back-button test.
  - **`subs-settings`:**
    - `loadSubSettings(null)` and an empty store → medium;
    - a stored `{v: 1, preset: "short"}` → short;
    - a stored custom value → `preset: "custom"`, with the options clamped;
    - bad JSON, `v: 2` or a wrong shape → medium;
    - a `getItem` that throws → medium, with no error;
    - `saveSubSettings` writes `{"v":1,…}` and swallows a throwing `setItem`.

    The `useSubSettings` hook keeps state in `useState` initialised from `loadSubSettings(safeLocalStorage())`, and saves on change.
- [ ] **Step 2: Run** `npx vitest run src/lib/sub-options.test.ts src/lib/languages.test.ts src/pages/video`. Expected: FAIL.
- [ ] **Step 3: Implement** per C8. `url-state` uses `useSearchParams` + `useNavigate` + `useLocation` from `react-router`. The queries use `api()` from `@/lib/api`.
- [ ] **Step 4: Run** `npm run typecheck && npm run lint && npm test`. Expected: PASS.
- [ ] **Step 5: Commit** with the message `feat(web): subtitle data layer (types, options, URL state, queries, settings)` + trailer.

---

## Wave 2

### Task 7: json3 / vtt parsers `core/subparse.py`

**Files:**
- Create: `src/yttoolkit/core/subparse.py`, `tests/unit/test_subparse.py`

**Depends on:** T1 (fixtures), T2 (`thai_fallback`), T4 (`Token`, `display_len`).

**Interfaces:**
- Consumes: `srt_builder.Token` (T4) and `thai_fallback.split_words` / `has_thai` (T2).
- Produces:
  - `PARSER_VERSION = 1`
  - `class SubParseError(ValueError)`
  - `@dataclass(frozen=True) ParsedTrack(tokens: tuple[Token, ...], has_word_timing: bool, source: str)`
  - `normalize_text(s: str) -> str`: remove U+200B, U+200C, U+200D and U+FEFF; turn every other `str.isspace()` char (including `\n` and NBSP) into `" "`. It does not collapse.
  - `split_block(text: str, start_ms: int, end_ms: int) -> list[Token]`
  - `parse_json3(data: bytes) -> ParsedTrack`
  - `parse_vtt(data: bytes) -> ParsedTrack`

**Rules**

*json3:*
1. **Load.** Decode UTF-8 (BOM allowed). JSON must be an object with list `events`, else `SubParseError`.
2. **Skip events** with a truthy `aAppend`, without `segs`, or whose normalized joined text is blank.
3. **Word timing.** `has_word_timing` = any kept event has ≥ 2 segs, or any seg has `tOffsetMs`.
4. **Timed file** (`has_word_timing` true):
   - Every seg with non-blank normalized text becomes a token: `s = tStartMs + (tOffsetMs or 0)`, `e` = the next token's `s` within the event, and the last one gets `tStartMs + dDurationMs`.
   - A whitespace-only seg is glued as a leading space onto the next seg of the same event.
   - Nothing is ever split further (FR-SUB-9: YouTube's own boundaries).
5. **Untimed file:** each event is a block → `split_block(normalized text, tStartMs, tStartMs + dDurationMs)`.
   - Every block except the first gets its first token prefixed with `" "` when that token does not already start with a space. Owner lines are sentences.
   - Skip a block whose collapsed text equals the previous block's collapsed text when it starts before the previous block ends (repeats).

*`split_block`:*
- Collapse runs of spaces in the text. Words come from `thai_fallback.split_words` when `has_thai(text)`, else from `re.findall(r" ?[^ ]+", text)` with trailing spaces glued on.
- Time is spread by `display_len` share with integer maths: `s_i = start + (dur * cum_before_i) // total`, `e_i = s_{i+1}`, and the last `e = end`. A zero-length total → all tokens at `start`.

*vtt:*
1. **Load.** Decode UTF-8. The file must start with `WEBVTT`. Cue timing lines match `(?:(\d+):)?(\d{2}):(\d{2})\.(\d{3}) --> (?:(\d+):)?(\d{2}):(\d{2})\.(\d{3})`; the rest of the line (settings) is ignored.
2. **Word timing.** `has_word_timing` = any cue text contains `<\d{2}:\d{2}:\d{2}\.\d{3}>`.
3. **Timed mode:**
   - Skip cues shorter than 50 ms.
   - For each remaining cue take its **last non-blank line** (YouTube's rolling layout: line 1 repeats, line 2 is new).
   - The text before the first time tag is a token at the cue start. Each `<ts><c>word</c>` is a token at `ts`.
   - Strip `<c>`, `</c>`, `<c.*>` and any other tags. Unescape `&amp; &lt; &gt; &nbsp; &lrm; &rlm;`.
   - `e` = the next token's `s` in the cue, and the last one gets the cue end.
4. **Untimed mode:** each cue's lines are joined with `" "` (tags stripped) and handled as a block, exactly like untimed json3 (including the repeat skip and the space prefix).

*Both formats, final pass:*
1. Stable sort by `s`.
2. Clamp `e = min(e, next.s)` and `e = max(e, s)`.
3. Collapse runs of spaces inside each token.
4. Drop tokens that are blank after collapsing, gluing their space onto the next token.

- [ ] **Step 1: Write the failing tests**, using the T1 fixtures:
  - **AC-SUB-03 (parser half), `88o5Sk8_m1Y/th-orig.json3`:**
    - no token is blank or contains `\n`;
    - the token count equals the non-blank segs in non-`aAppend` events (compute it in the test from the raw JSON);
    - tokens are sorted, non-overlapping, and `has_word_timing` is true;
    - the first token is `สวัสดี` at 120 ms.
  - **AC-SUB-04 (parser half):** `"".join(t.t for t in tokens).replace(" ", "")` equals the concatenation of every kept seg's normalized text with spaces removed.
  - **English `8lpOfyoxcvU/en-US-orig.json3`:** tokens keep their leading spaces (`" the"`), and `cue_text` of the first 5 tokens reads as English words separated by single spaces.
  - **Owner `jNQXAC9IVRw/en.json3`:** `has_word_timing` false, the first token is `"All"`, and the tokens of block 2 start with a space.
  - **Owner Thai `OWNERTHSUB1/th.json3` (hand-written):**
    - rejoined text (spaces removed) equals the source (spaces removed);
    - no token boundary falls inside a newmm word: compare with `split_words` over each block;
    - the times are monotonic within each block, and the first and last tokens of each block hit the block start and end.
  - **AC-SUB-11 (parser half), `88o5Sk8_m1Y/th-orig.vtt`:**
    - `has_word_timing` true; no repeated words (the joined vtt text without spaces equals the joined json3 text without spaces);
    - the first token is `สวัสดี` at 120 ms; the second is `ครับ` at 1120 ms.
    - If the real data shows a YouTube-side difference, record it in the test docstring, then assert `difflib.SequenceMatcher(None, a, b).ratio() >= 0.98` plus the per-token checks. Never loosen the checks for a parser bug.
  - **`jNQXAC9IVRw/en.vtt`:** untimed and parses to the same text as `en.json3` (spaces normalized).
  - **Errors:** `broken.json3` → `SubParseError`; `b"{}"` → `SubParseError`; bytes that are not WEBVTT → `SubParseError`.
  - **AC-SUB-09 (parser half):** `split_block` of a 60-char Thai sentence with no spaces yields ≥ 4 tokens, whose times sum to the block span and whose boundaries equal `split_words`.
- [ ] **Step 2: Run** `uv run pytest tests/unit/test_subparse.py -q -W error`. Expected: FAIL.
- [ ] **Step 3: Implement** the rules above.
- [ ] **Step 4: Run** the file, then the full suite. Expected: PASS.
- [ ] **Step 5: Commit** with the message `feat(core): json3/vtt subtitle parsers with Thai block fallback` + trailer.

### Task 8: Caption tracks + probe trim `core/tracks.py`, `core/videos.py`

**Files:**
- Create: `src/yttoolkit/core/tracks.py`, `tests/unit/test_tracks.py`
- Modify: `src/yttoolkit/core/videos.py`, `tests/unit/test_videos.py`, and `tests/api/test_videos_api.py` (only assertions that enumerate VideoInfo keys)

**Depends on:** T1.

**Interfaces (produces):**
```python
TRACK_ID: re.Pattern            # C1
@dataclass(frozen=True) class Track: id: str; lang: str; name: str; group: str; json3: str | None; vtt: str | None
def trim_captions(raw: dict) -> dict                   # C2
def list_tracks(trimmed: dict) -> list[Track]           # owner, original, translated (translated urls built with tlang)
def original_language(trimmed: dict) -> str | None      # C3
def default_track_id(tracks: list[Track], original_lang: str | None, prefer: str | None = "th") -> str | None
def tracks_payload(trimmed: dict) -> dict               # {"tracks":[{id,lang,name,group}], "defaultTrackId"?}
def find_track(trimmed: dict, track_id: str) -> Track | None
```
`videos.py` changes:
- `PROBE_VERSION = 2`.
- `trim_probe` adds `probeVersion`, `description` (when `str(raw.get("description") or "").strip()` is non-empty; store the raw string) and `captions = trim_captions(raw)`.
- `to_video_info` adds `description` when present.
- `_cached_info` returns `None` (stale) when the stored `probeVersion != PROBE_VERSION`. `_stored_hit` (the offline fallback) still accepts old rows.
- `original_language` needs the audio `isOriginal` logic from `videos._audio_formats`. To avoid an import cycle, `tracks.py` receives it as the trimmed `formats` list and imports the helper from `videos.py`. `videos.py` imports `trim_captions` from `tracks.py` **inside** `trim_probe`, which avoids a circular import at module load.

- [ ] **Step 1: Write the failing tests** (`test_tracks.py` uses the T1 probe fixtures through `json.loads`):
  - **`88o5Sk8_m1Y` (AC-SUB-01):**
    - the original group has only `th-orig` (the auto `th` duplicate is dropped);
    - translated keys ⊆ {en, ja, fr, ko, zh-Hans};
    - default = `a.th-orig`;
    - `t.en` has json3 URL `https://fake.invalid/subs/88o5Sk8_m1Y/th-orig.json3?tlang=en`.
  - **`8lpOfyoxcvU`:** the original group has `en-US-orig` and `th-orig`; `original_language` = `th` (audio original); default = `a.th-orig`, not `a.en-US-orig`.
  - **`jNQXAC9IVRw`:** owner `o.en` and `o.de`; the HLS auto entries are ignored, so there is no original or translated group; default = `o.en`.
  - **`OWNERTHSUB1`** (Q9 = ข, synthetic English clip): owner `th` and `en`, and original `en-orig`. With `prefer="th"` the default is `o.th`; with `prefer=None` it is `o.en` (Q8).
  - **`NOORIGSUB01` (AC-SUB-02):** the original group is `[a.yue]`, translated is `[t.en, t.th]`, and the default is `None`, so the payload has no `defaultTrackId`.
  - **`aqz-KE-bpKQ`:** `{"tracks": []}`.
  - **Synthetic:** `live_chat` dropped; a key whose entries are all `srv3` dropped; a mixed key (`th` with one tlang and one non-tlang entry) + `th-orig` → `th` dropped.
  - **`find_track`:** a malformed id (`"x.th"`, `"a."`, `"a.th/../x"`) → None.
  - **`test_videos.py`:**
    - update the VideoInfo key set (add `description`);
    - BBB has the description of the fixture;
    - a row stored without `probeVersion` counts as stale (the extractor is called again) but is still used as the offline fallback when the extractor raises `E_NETWORK`;
    - `trim_probe` output contains `captions` and `probeVersion: 2`.
- [ ] **Step 2: Run** `uv run pytest tests/unit/test_tracks.py tests/unit/test_videos.py -q -W error`. Expected: FAIL.
- [ ] **Step 3: Implement** C1–C3 and the `videos.py` changes.
- [ ] **Step 4: Run** the full suite. Expected: PASS. Fix `tests/api/test_videos_api.py` only where it enumerates VideoInfo keys.
- [ ] **Step 5: Commit** with the message `feat(core): caption track list, default track choice, description in VideoInfo` + trailer.

### Task 9: TS `srt-builder` + `useCues`

**Files:**
- Create: `web/src/lib/srt-builder.ts`, `web/src/lib/srt-builder.test.ts`, `web/src/pages/video/use-cues.ts`

**Depends on:** T4 (`builder-cases.json`), T6 (types, `sub-options`).

**Interfaces (produces):**
- `displayLen(text: string): number`
- `cueText(tokens: SubToken[]): string`
- `buildCues(tokens: SubToken[], o: SubOptions): Cue[]`
- `toSrt(cues: Cue[]): string`
- `toTxt(tokens: SubToken[]): string`
- `toMd(tokens: SubToken[], meta: {title: string; videoId: string; chapters: {startMs: number; title: string}[]}): string`
- `cueStats(cues: Cue[]): {count: number; avgChars: number; underOneSecond: number}`
- `MERGE_LIMIT_FACTOR`
- `useCues(tokens, options)` in `use-cues.ts`

Everything is exactly C6. Use code-point iteration (`for (const ch of text)`), not UTF-16 length.

- [ ] **Step 1: Write the failing test.** Load the shared cases with Vite's raw import (this is typed by `vite/client`, and the tsconfig has no node types):
```ts
import casesRaw from "../../../tests/fixtures/subs/builder-cases.json?raw"
const { cases } = JSON.parse(casesRaw) as { cases: BuilderCase[] }
describe.each(cases)("builder case $name", (c) => {
  it("cues", () => expect(buildCues(c.tokens, c.options)).toEqual(c.cues))
  it("srt", () => expect(toSrt(buildCues(c.tokens, c.options))).toBe(c.srt))
  it("txt", () => expect(toTxt(c.tokens)).toBe(c.txt))
})
```
  Also:
  - `displayLen("ที่") === 1`, `displayLen("น้ำ") === 2`, and an emoji counts as 1.
  - `cueStats` on case 1 → `{count: 2, avgChars: 16.5, underOneSecond: 0}`.
  - **Performance guard:** 20,000 synthetic Thai tokens (3 chars, 300 ms each) through `buildCues` with medium options take a median of 5 runs < 100 ms (`performance.now()`). This leaves headroom under the 200 ms AC-SUB-07 budget, which also includes rendering.
  - If `?raw` cannot resolve the path outside `web/` in Vitest, set `server.fs.allow: [".."]` under `test` in `vite.config.ts`. **Do not** edit `vite.config.ts` in this task: report it to the controller, who applies it at the gate (it is a one-line config change).
- [ ] **Step 2: Run** `npx vitest run src/lib/srt-builder.test.ts`. Expected: FAIL.
- [ ] **Step 3: Implement** per C6. `useCues` = `useMemo(() => (tokens ? buildCues(tokens, options) : []), [tokens, options])`.
- [ ] **Step 4: Run** `npm run typecheck && npm run lint && npm test`. Expected: PASS.
- [ ] **Step 5: Commit** with the message `feat(web): TypeScript srt-builder port checked against shared cases` + trailer.

### Task 10: W2 tab shell, header copy buttons, track badge

**Files:**
- Modify: `web/src/pages/video.tsx`, `web/src/pages/video/header.tsx`, `web/src/pages/video/sequence.tsx`
- Create:
  - `web/src/pages/video/tabs.tsx`
  - `web/src/pages/video/copy-info.tsx`
  - `web/src/pages/video/track-label.ts` (+ `track-label.test.ts`)
  - `web/src/pages/video/subtitle-gate.tsx`
  - `web/src/pages/video/subs-panel.tsx` (initial version; T13 replaces its body)
  - `web/src/pages/video/transcript-panel.tsx` (initial version; T14 replaces its body)
  - `web/src/lib/chapters.ts` (+ `chapters.test.ts`)
  - `web/e2e/video-tabs.spec.ts`

**Depends on:** T5 (strings, Tabs), T6 (URL state, queries).

**Interfaces:**
- Produces:
  - `formatChapters(chapters: Chapter[]): string`: lines `HH:MM:SS <title>` sorted by `startS`, joined with `"\n"` (clipboard text uses LF; AC-PROBE-03), using `formatTimecode(startS*1000)`.
  - `trackLabel(track: SubtitleTrack): string` = `fill(th.subs.names[group], {lang: languageName(track.lang)})`.
  - `SubtitleGate({videoId, enabled, children: (data: SubtitleTracks) => ReactNode})`, which renders the 4 states:
    - loading: 3 Skeleton rows + sr-only `th.subs.loading`
    - error: `LoadError` with `th.subs.loadError` and retry
    - empty (`tracks.length === 0`): an `Empty` with a Captions-off icon and `th.subs.none`
    - normal: `children(data)`
  - `SubsPanel({videoId, enabled})` and `TranscriptPanel({videoId, enabled})`: in this task both are just `<SubtitleGate …>{() => null}</SubtitleGate>`, so the tabs work end to end. T13/T14 own the files afterwards.
  - `VideoTabs({videoId, enabled})`.

**Behaviour:**
1. **Tab bar.** `VideoTabs` renders Base UI `Tabs` with `value = tab` from `useVideoParams()` and `onValueChange(v) → update({tab: v, at: null})`.
   - Tabs in order: ภาพเฟรม (`frames` → `<FramesSection>`), ซับ (`subs` → `<SubsPanel>`), ทรานสคริปต์ (`transcript` → `<TranscriptPanel>`).
   - `TabsList` has `aria-label={th.video.tabs.label}` and the classes `w-full justify-start overflow-x-auto flex-nowrap`. Triggers get `shrink-0`, so narrow screens scroll sideways instead of wrapping (PRD W2).
   - Each trigger is at least 44 px tall.
2. **Page layout.** `video.tsx` keeps breadcrumb/sequence and header above the tabs. It renders `VideoTabs` in place of the direct `FramesSection`. When the video query has failed without data, it renders no tabs, the same as M2 hid the frames.
3. **Header copy buttons.** Under the meta line there is a `ButtonGroup` (`aria-label={th.video.copyGroup}`) of ghost buttons:
   - "คัดลอก chapter" is shown only when `chapters.length > 0` and copies `formatChapters(chapters)`.
   - "คัดลอกคำอธิบาย" is shown only when `description` is non-empty and copies the description **byte-exact** (no trimming).
   - Toasts: `th.video.copied` on success, `th.video.copyFailed` on error.
   - The group is hidden when both buttons are hidden.
   - "คัดลอกเครดิต" is M4.
4. **Track badge.** The header shows a `Badge` `fill(th.video.trackBadge, {name: trackLabel(track)})` for the track in effect (URL `trackId` ?? `defaultTrackId`). It is shown only when the subtitles query succeeded and a track is in effect.
5. **Clip sequence.** `sequence.tsx` builds `"/v/<id>" + (tab !== "frames" ? "?tab=" + tab : "")`. It keeps the tab and drops `track` and `at`.

- [ ] **Step 1: Write the failing unit tests.**
  - `chapters.test.ts` (AC-PROBE-03 U): 3 chapters given out of order → exactly `"00:00:00 บทนำ\n00:01:05 ส่วนกลาง\n01:02:03 สรุป"`; an empty list → `""`.
  - `track-label.test.ts`: `{lang: "th", group: "original"}` → `"ไทย (อัตโนมัติ)"`.
- [ ] **Step 2: Write `web/e2e/video-tabs.spec.ts`** (runs at the gate):
  - `/v/aqz-KE-bpKQ` shows 3 tabs; ภาพเฟรม is selected with 128 frames.
  - Clicking ซับ changes the URL to `?tab=subs` and shows "คลิปนี้ไม่มีซับ" (BBB has no subtitles).
  - Reloading keeps ซับ selected.
  - Going back from W1 → W2 (subs) → back returns to W1 in **one** step.
  - The tab row scrolls sideways at 360 px width (`scrollWidth > clientWidth` or no wrap: all triggers share one `offsetTop`).
  - **AC-PROBE-03 E:** on `/v/jNQXAC9IVRw`, "คัดลอก chapter" puts 3 `HH:MM:SS title` lines on the clipboard (grant clipboard permissions) and shows the "คัดลอกแล้ว" toast. BBB has no such button.
  - **AC-PROBE-04 E:** on `/v/aqz-KE-bpKQ`, "คัดลอกคำอธิบาย" puts exactly the fixture's `description` on the clipboard (read the fixture JSON in the spec with `node:fs`; e2e has node types).
  - `/v/88o5Sk8_m1Y` shows the badge `ซับ: ไทย (อัตโนมัติ)`.
  - axe reports no serious/critical issues on `/v/aqz-KE-bpKQ?tab=subs` in both themes.
- [ ] **Step 3: Run** `npx vitest run src/lib/chapters.test.ts src/pages/video/track-label.test.ts`. Expected: FAIL. Implement until green.
- [ ] **Step 4: Run** `npm run typecheck && npm run lint && npm test`. Expected: PASS. The existing `video.spec.ts` must remain valid: the default tab is ภาพเฟรม and no frame UI changed.
- [ ] **Step 5: Commit** with the message `feat(web): W2 tabs (frames, subs, transcript), copy chapter/description, track badge` + trailer.

---

## Wave 3

### Task 11: Subtitle service + API

**Files:**
- Create: `src/yttoolkit/core/subtitles.py`, `src/yttoolkit/api/subtitles.py`, `tests/unit/test_subtitles.py`, `tests/api/test_subtitles_api.py`
- Modify:
  - `src/yttoolkit/core/yterrors.py` (add `E_NO_SUBTITLES` to `MESSAGES`)
  - `src/yttoolkit/api/videos.py` (add `"E_NO_SUBTITLES": 404` to `STATUS_BY_CODE`, nothing else)
  - `src/yttoolkit/app.py` (`AppContext.subtitles`, include the router)
  - `src/yttoolkit/lifecycle.py` (build the service, `thai_fallback.configure`)
  - `tests/unit/test_lifecycle.py` (only if it unpacks `open_services`)

**Depends on:** T3, T4, T7, T8.

**Interfaces:**
```python
class SubtitleService:
    def __init__(self, videos: VideoService, fetch_subtitle: Callable[[str], bytes], cache_root: Path) -> None
    def tracks(self, video_id: str) -> dict                                   # tracks_payload
    def tokens(self, video_id: str, track_id: str) -> ParsedTrack
    def export(self, video_id: str, track_id: str, fmt: str, opts: SubOptions) -> tuple[str, str, bytes]
        # (filename, ascii_fallback, utf-8 bytes); fmt in {"srt","txt","md"}
def build_subtitles_router(ctx: AppContext) -> APIRouter
```

**Service rules:**
1. **Trimmed probe:** `trimmed = videos.raw(video_id)`. If `"captions"` is missing (an M2 row), call `videos.get(video_id, refresh=True)` once and read `raw()` again. Errors propagate.
2. **`tokens`:**
   1. `find_track` (T8); None → `YtError("E_NO_SUBTITLES", f"ไม่มีแทร็ก {track_id}")`.
   2. **Cache hit:** `cache_root/<id>/subs/<track_id>.tokens.json` with `v == PARSER_VERSION` → return it.
   3. **Otherwise** (under a per-(video, track) `threading.Lock`):
      - fetch json3 → `parse_json3`;
      - on `SubParseError`, zero tokens, or a missing json3 URL → fetch vtt → `parse_vtt`;
      - on `YtError("E_NETWORK")` from either fetch: `videos.get(video_id, refresh=True)`, re-read the track and retry the whole load **once**; a second failure propagates;
      - `E_BOT_CHECK` propagates at once, with no retry and no fallback;
      - both parsers give 0 tokens or fail → `YtError("E_NO_SUBTITLES", …)`.
   4. **Write the cache** atomically (tmp + replace): the raw bytes as `<track_id>.<ext>` and `{v, hasWordTiming, source, tokens: [[t, s, e], …]}`. Written only on success.
3. **`export`:**
   - `info = videos.get(video_id)`.
   - Tokens as above; build the file with `srt_builder`: srt from `build_cues(tokens, opts)`, txt from `to_txt(tokens)`, md from `to_md(tokens, title=info["title"], video_id=…, chapters=[(c["startS"]*1000, c["title"]) for c in info["chapters"]])`.
   - Filename (Q2 = ก): `f"{safe_title(title) or video_id}.{track.lang}.{fmt}"`; fallback `f"subtitles.{track.lang}.{fmt}"`. Reuse `safe_title` from `api/videos.py`; the router computes the filename, and the service returns the stem parts.
   - Bytes = `text.encode("utf-8")`, with no BOM.
   - 0 tokens is already `E_NO_SUBTITLES`.

**Routes (C4):**
- `trackId` is validated with `TRACK_ID`; a mismatch → `E_NO_SUBTITLES` (404).
- The export query is a pydantic model with C5 limits (`Field(ge=…, le=…)`), `format: Literal["srt","txt","md"]` and a `model_validator` for `minMs < maxMs` and tokens-mode `tokensPerCue`. Validation errors go through the existing 422 `E_BAD_REQUEST` handler.
- Response headers use `attachment_header(fallback, filename)` from `api/videos.py`.
- All routes are sync `def` and wrapped with `_maps_yt_errors`. Import it; do not copy it.

**Wiring:**
- `AppContext.subtitles: SubtitleService | None = None`.
- `create_app` includes `build_subtitles_router(ctx)` when `ctx.subtitles` is set.
- `lifecycle.open_services` calls `thai_fallback.configure(paths.data_root / "pythainlp")` and builds `SubtitleService(videos, extractor.fetch_subtitle, paths.cache)`. Return it and pass it into the `AppContext` in both `run_app` and `serve` paths.

- [ ] **Step 1: Write the failing service tests** (`FakeExtractor` over `tests/fixtures`, tmp db and cache):
  - **Tracks:** `tracks("88o5Sk8_m1Y")` → the default is `a.th-orig`; `tracks("aqz-KE-bpKQ")` → `{"tracks": []}`.
  - **Tokens:** `tokens("88o5Sk8_m1Y", "a.th-orig")` → `source == "json3"` and ≥ 200 tokens.
    - A second call makes **no** `fetch_subtitle` call (cache).
    - A cache file with `v: 0` is ignored and rebuilt.
  - **AC-SUB-11:** `tokens("VTTFALLBAK1", "a.th-orig")` → `source == "vtt"`, with the same joined text (spaces removed) as the 88o5 json3.
  - **Signed-URL expiry:** wrap `fetch_subtitle` to raise `E_NETWORK` on its first call. Result: exactly one `videos.get(refresh=True)` (count `probe` calls on the fake) and success on the retry. If it always raises `E_NETWORK`, the error propagates after exactly one re-probe.
  - **Bot check:** `E_BOT_CHECK` → propagates with no re-probe.
  - **No subtitles:** an unknown track → `E_NO_SUBTITLES`.
  - **M2 row:** a row stored without `captions` → one refresh, then success.
  - **Export (AC-SUB-08 A):**
    - `export(…, "srt", PRESETS["medium"])` bytes: no BOM (`not data.startswith(b"\xef\xbb\xbf")`), every `\n` preceded by `\r`, numbering 1..n in order, and times non-overlapping (parse them back).
    - The filename is `f"{safe_title(fixture_title)}.th.srt"`, which is `"Thai Listening Practice EP.1 Beginner.th.srt"` for the captured title "Thai Listening Practice | EP.1 | Beginner". Assert both the computed and the literal value.
    - `md` contains `# ` + the title and `https://www.youtube.com/watch?v=88o5Sk8_m1Y`.
- [ ] **Step 2: Write the failing API tests** (`make_client(videos=…, extractor=…, cache_root=…, subtitles=…)`):
  - All 3 routes return 200 on the happy path, with the shapes in C4 (exact key sets).
  - `tokens` JSON tokens are `{t, s, e}` with int s/e.
  - `/subtitles/zz.bad/tokens` → 404 `E_NO_SUBTITLES` with the Thai message "คลิปนี้ไม่มีซับ".
  - Export validation: `maxChars=5` → 422 `E_BAD_REQUEST`; `minMs=5000&maxMs=3000` → 422; `mode=tokens` without `tokensPerCue` → 422.
  - Export headers: `Content-Disposition` has `filename*=UTF-8''` and the ASCII fallback `subtitles.th.srt`; the content type is as in C4.
  - `UPCOMINGLV1` → 409 `E_LIVE_NOT_READY`; `PRIVATEVID1` → 404.
  - Security: the routes are GET, so no token is needed, but a cross-site `Sec-Fetch-Site` → 403 (existing middleware; one assertion).
- [ ] **Step 3: Run** `uv run pytest tests/unit/test_subtitles.py tests/api/test_subtitles_api.py -q -W error`. Expected: FAIL.
- [ ] **Step 4: Implement** the service, router and wiring.
- [ ] **Step 5: Run** `uv run pytest -q -W error`. Expected: PASS, including `test_lifecycle.py` and `tests/integration/test_serve.py`.
- [ ] **Step 6: Commit** with the message `feat(api): subtitles, tokens and subtitle export endpoints` + trailer.

### Task 12: Real-fixture integration, goldens, TS parity

**Files:**
- Create:
  - `tests/unit/test_subtitles_fixtures.py`
  - `tests/unit/test_srt_golden.py`
  - `tests/fixtures/subs/tokens/*.json`
  - `tests/fixtures/subs/golden/*`
  - `web/src/lib/srt-parity.test.ts`
- Modify: `.gitattributes`

**Depends on:** T4, T7, T9.

**Golden set:**
- Names: `th-asr` (88o5 th-orig.json3), `th-vtt` (88o5 th-orig.vtt), `en-asr` (8lpO en-US-orig.json3), `en-owner` (jNQ en.json3), `th-owner` (iG9C th.json3).
- For each name `N`:
  - `tokens/N.json` = `{"tokens": [{t, s, e}], "hasWordTiming": …, "md": {"title": "Golden N", "videoId": "<fixture id>", "chapters": [{"startMs", "title"}]}}` from the parser. The `md` block is the single source of the `.md` meta for both Python and TS;
  - `golden/N.<preset>.srt` for short, medium and long;
  - `golden/N.txt`;
  - `golden/N.md` (title "Golden <N>", videoId from the fixture, and chapters `[]`, except `en-owner`, which uses the 3 jNQ chapters).
- Plus one custom-options golden `golden/th-asr.custom-tokens.srt`, with `{maxChars: 30, lines: 2, minMs: 1000, maxMs: 6000, mode: "tokens", tokensPerCue: 4}`.

- [ ] **Step 1: Mark goldens binary.** Add to `.gitattributes`: `tests/fixtures/subs/golden/** -text`. They must keep CRLF byte-for-byte on every OS.
- [ ] **Step 2: Write `test_srt_golden.py`.**
  - It parses each fixture, compares with `tokens/N.json`, builds every output and compares **bytes** with the golden files.
  - With env `YT_UPDATE_GOLDEN=1`, it (re)writes the golden and token files instead (the only way they are produced). Without it, a missing golden fails.
  - Write goldens with `Path.write_bytes(text.encode("utf-8"))` and compare with `read_bytes()`. Never use text mode, which would translate newlines on Windows.
  - Generate once with `YT_UPDATE_GOLDEN=1 uv run pytest tests/unit/test_srt_golden.py`. Then **read** a sample of each golden by eye:
    - Thai lines end at word boundaries;
    - no duplicated line pairs;
    - the medium Thai lines are around 25 visible chars.
  - Then run without the env var and confirm PASS.
- [ ] **Step 3: Write `test_subtitles_fixtures.py`** (AC checks on real data, all presets):
  - **AC-SUB-03:** `th-asr` and `th-vtt` have no two adjacent cues with identical text, and no cue text contains a line that equals the previous cue's text in full. Also: no cue text is empty.
  - **AC-SUB-04:** for every fixture and preset, the concatenation of all cue texts with spaces removed equals the concatenation of token texts with spaces removed, and each cue's first line starts with its first token's stripped text.
  - **AC-SUB-05:** for medium on every fixture, each line has `display_len ≤ 25` unless the cue has exactly one token, and a cue shorter than 1200 ms has `end_ms == next.start_ms`.
  - **AC-SUB-09:** a synthetic untimed json3 (built in the test: one event, 60 Thai chars, no spaces, 6 s) at medium → ≥ 3 cues, and every cue boundary is a boundary of `thai_fallback.split_words` of the text.
  - **AC-SUB-11:** `th-vtt` cues at medium pass the AC-SUB-03 and 04 checks, and their joined text equals `th-asr`'s (or satisfies the documented ratio from T7).
  - **AC-SUB-08:** every srt golden is valid UTF-8 with no BOM, contains no lone `\n`, numbers 1..n, and has non-overlapping times.
- [ ] **Step 4: Write `web/src/lib/srt-parity.test.ts`** (AC-SUB-06):
```ts
const tokens = import.meta.glob("../../../tests/fixtures/subs/tokens/*.json", { query: "?raw", import: "default", eager: true }) as Record<string, string>
const golden = import.meta.glob("../../../tests/fixtures/subs/golden/*", { query: "?raw", import: "default", eager: true }) as Record<string, string>
// for each tokens/N.json and each preset: expect(toSrt(buildCues(tokens, PRESETS[p]))).toBe(golden[`…/N.${p}.srt`])
// plus N.txt, N.md (meta from the "md" block of tokens/N.json), and th-asr.custom-tokens.srt
```
  Also assert that the glob found ≥ 16 golden files (otherwise the glob silently matched nothing).
- [ ] **Step 5: Run everything.** `uv run pytest -q -W error`, then in `web/` run `npx vitest run src/lib/srt-parity.test.ts && npm run typecheck && npm run lint`. Expected: PASS.
  - A parity mismatch is a bug in `srt-builder.ts` or `srt_builder.py` against C6. Fix the side that deviates from C6.
  - That fix touches a file owned by T4/T9, so hand the diff to the controller, who applies it at the gate. Never edit the goldens to make TS pass.
- [ ] **Step 6: Commit** with the message `test: real-fixture subtitle ACs, byte goldens and TS/Python parity` + trailer. Also run `git ls-files --eol tests/fixtures/subs/golden | head` and confirm the golden files show `-text`/CRLF.

### Task 13: ซับ tab UI

**Files:**
- Modify: `web/src/pages/video/subs-panel.tsx` (replace T10's body)
- Create:
  - `web/src/pages/video/subs/track-select.tsx`
  - `web/src/pages/video/subs/translated-dialog.tsx`
  - `web/src/pages/video/subs/preset-controls.tsx`
  - `web/src/pages/video/subs/preview.tsx`
  - `web/src/pages/video/subs/export-buttons.tsx`
  - `web/src/pages/video/subs/track-groups.ts` (+ `track-groups.test.ts`)
  - `web/e2e/subs.spec.ts`

**Depends on:** T5, T6, T9, T10. It uses the T11 API at the gate.

**Layout** (inside `SubtitleGate`, a Card titled `th.subs.title`):
1. **Track picker.** `Select` labelled `th.subs.trackLabel`.
   - Groups `th.subs.groups.owner` and `groups.original` list their tracks, sorted by `trackLabel`, with the original language first.
   - A final item `th.subs.openTranslated` opens `TranslatedDialog`.
   - The value is the URL `trackId` ?? `defaultTrackId`, else empty with placeholder `th.subs.trackPlaceholder` and the hint `th.subs.pickHint` below (AC-SUB-02).
   - Choosing a track → `update({trackId})`.
   - A translated track that is selected shows in the trigger as `trackLabel(track)` (`… (แปลอัตโนมัติ)`).
2. **`TranslatedDialog`.** A `Dialog` with title `th.subs.translatedTitle` and a warning `Alert` (`th.subs.translatedWarning`) **above** a search `InputGroup` (`th.subs.searchLanguage`).
   - A `ScrollArea` list of translated tracks, sorted by Thai language name and filtered by substring over the Thai name and the code. The empty result shows `th.subs.noLanguage`.
   - Choosing one closes the dialog and sets `trackId`.
3. **Preset controls.**
   - `ToggleGroup` (single) short/medium/long. Each item shows `th.subs.presets.*` with a tooltip of `presetHints`. Its value is `presetOf(options)`: none selected when custom.
   - A `Collapsible` "ปรับเอง" (ghost trigger `th.subs.custom`, closed by default) holding `Field`s:
     - maxChars `Slider` 10–60;
     - lines `ToggleGroup` 1/2;
     - minSeconds `Slider` 0.3–3.0 (step 0.1; stored in ms);
     - maxSeconds `Slider` 1–10 (step 0.5);
     - `Switch` byWords, which when on shows a wordsPerCue `Slider` 1–20 (default 3).
   - Every value shows its number next to the label in Plex Mono.
   - Changes go through `clampOptions`, then `setCustom`.
   - When custom is active, a `Badge` `th.subs.customInUse` sits beside the toggle group.
   - "ตัวเลือกขั้นสูง" is not rendered (Q5 = ก).
4. **Preview.** `useCues(tokens, options)`. A box titled `th.subs.previewTitle` lists the first 5 cues as `HH:MM:SS,mmm → HH:MM:SS,mmm` (mono) + the lines. Below it, `th.subs.stats` from `cueStats`.
   - When `hasWordTiming` is false, a muted note `th.subs.noWordTiming`.
   - Tokens loading: 5 Skeleton rows. Tokens error: `LoadError` with retry. `E_NO_SUBTITLES` on tokens: an Empty `th.subs.none`.
5. **Export buttons.** A `ButtonGroup` (`aria-label` `th.subs.downloadGroup`) of **secondary** buttons "โหลด .srt", "โหลด .txt", "โหลด .md", plus a ghost "คัดลอกข้อความ".
   - The download buttons (Q1 = ก) call `downloadFile(exportPath(videoId, trackId, fmt, options), \`subtitles.${lang}.${fmt}\`)` with the loading toast `th.subs.preparing`, an error toast `errorMessage(e, th.subs.downloadFailed)`, a Spinner on the busy button, all disabled while busy, and `focusableWhenDisabled`. The pattern is the same as `BulkDownloads` in `frames.tsx`.
   - Copy writes `toTxt(tokens)` with `\r\n` replaced by `\n` (clipboard), then toast `th.subs.textCopied`.
   - Everything is disabled until a track is selected.
   - If Q1 = ข, render only the copy button.
6. **Settings.** Options come from `useSubSettings()`, so the preset is remembered.

- [ ] **Step 1: Write failing tests for the pure helpers.** Vitest has no DOM here (see T6), so put the logic in pure helpers and test those:
  - `buildTrackGroups(tracks, originalLang)` in `subs/track-groups.ts`:
    - owner and original groups sorted by Thai label, with tracks whose `lang` base equals `originalLang` first;
    - translated tracks excluded;
    - empty groups omitted.
  - `filterTranslated(tracks, query)`: a Thai substring over `languageName(lang)` or a case-insensitive match on the code; an empty query returns everything, sorted by Thai name.
  - `previewTime(ms)` → `HH:MM:SS,mmm`.

  The rendered components are covered by `subs.spec.ts`.
- [ ] **Step 2: Write `web/e2e/subs.spec.ts`** (runs at the gate):
  - **AC-SUB-01 E:** `/v/88o5Sk8_m1Y?tab=subs` shows the Select value `ไทย (อัตโนมัติ)`; the preview shows 5 cues whose first line contains `สวัสดี`; the stats line matches `/^\d+ ซับ/`.
  - **Presets:** clicking สั้น changes the preview's first cue text length (≤ 15 visible chars), and a reload keeps สั้น (localStorage).
  - **AC-SUB-02 E:** `/v/NOORIGSUB01?tab=subs` has the Select empty with the hint visible and the main list containing only `yue`. "เลือกซับแปลอัตโนมัติ…" opens a dialog that contains the warning text **before** the list. Choosing `อังกฤษ` sets the URL `track=t.en`.
  - **Download:** "โหลด .srt" triggers a download whose suggested filename is `Thai Listening Practice EP.1 Beginner.th.srt`. `safe_title` drops the `|` characters and collapses the spaces; the T11 API test pins the same value. The downloaded file's first bytes are `1\r\n00:00:00,120`.
  - **Copy:** "คัดลอกข้อความ" → the clipboard starts with `สวัสดีครับ`.
  - **AC-SUB-11 E:** `/v/VTTFALLBAK1?tab=subs` shows the preview, which starts with `สวัสดี`.
  - **No subtitles:** `/v/aqz-KE-bpKQ?tab=subs` shows "คลิปนี้ไม่มีซับ" and no Select.
  - **AC-SUB-07 / preview ≤ 200 ms:**
    1. Open `/v/LONGTHAI1hr?tab=subs`, wait for the preview and open "ปรับเอง".
    2. Focus the maxChars slider thumb.
    3. In `page.evaluate`, install a `MutationObserver` on the stats element that resolves with `performance.now()` on the first change.
    4. Record `t0 = performance.now()` inside the same evaluate right before `thumb.dispatchEvent(new KeyboardEvent("keydown", {key: "ArrowRight", bubbles: true}))`.
    5. Assert `t1 − t0 ≤ 200`. Take the median of 5 presses. Also assert the token count behind the page is ≥ 4000 (this checks the 1 h fixture is really 1 h).
  - axe: no serious/critical issues on `?tab=subs` for 88o5, with "ปรับเอง" open and the translated dialog open, in both themes.
- [ ] **Step 3: Implement** the components.
- [ ] **Step 4: Run** `npm run typecheck && npm run lint && npm test`. Expected: PASS.
- [ ] **Step 5: Commit** with the message `feat(web): subtitles tab (track picker, presets, custom, live preview, export, copy)` + trailer.

### Task 14: ทรานสคริปต์ tab + frame linkage ("ดูซับช่วงนี้", highlight)

**Files:**
- Modify: `web/src/pages/video/transcript-panel.tsx` (replace T10's body), `web/src/pages/video/frames.tsx`
- Create:
  - `web/src/pages/video/transcript/search.ts` (+ `search.test.ts`)
  - `web/src/pages/video/transcript/line-list.tsx`
  - `web/src/pages/video/frame-target.ts` (+ `frame-target.test.ts`)
  - `web/e2e/transcript.spec.ts`

**Depends on:** T6, T9, T10.

**Interfaces (produces):**
- `searchLines(cues: Cue[], query: string): number[]`: indexes of cues whose `lines.join(" ")` contains the query. It is case-insensitive (`toLocaleLowerCase("th")`) and compares after NFC normalization and collapsing spaces. An empty query → all indexes.
- `nearestFrameIndex(frames: StoryboardFrame[], atMs: number): number`: the minimal `|tMs − at|`, ties go to the earlier frame. Empty → −1.
- `cueIndexAt(cues: Cue[], atMs: number): number`: the last cue with `startMs <= at`, else 0. Empty → −1.

**Transcript panel** (inside `SubtitleGate`; cues = `useCues(tokens, useSubSettings().options)` for the track in effect, per Q4 = ก):
1. **Header.** Title `th.transcript.title` + a muted line `fill(th.transcript.source, {name: trackLabel(track)})`.
   - No track in effect (the AC-SUB-02 case) → the `th.subs.pickHint` text plus a secondary button `th.transcript.goToSubs` that switches to the ซับ tab (`update({tab: "subs"})`).
2. **Search.** `InputGroup` (`aria-label` `th.transcript.searchLabel`, placeholder `searchPlaceholder`) with a clear button (`aria-label` `clearSearch`, shown when the query is non-empty).
   - Below it, the result count `fill(found, {n})` in an `aria-live="polite"` region, or `notFound`.
3. **Lines.** A `ScrollArea` with `max-h-[360px]` and a `ul` (`aria-label` `th.transcript.linesLabel`). Each cue is a `button`: mono `HH:MM:SS` (`formatTimecode(startMs)`) + the text.
   - Search matches are wrapped in `<mark>`. Non-matching lines are hidden while a query is set.
   - `th.transcript.hint` sits above the list.
   - Clicking a line → `update({tab: "frames", at: cue.startMs})` (FR-SUB-8, PRD W2).
4. **Arriving with `at`.** When `at` is set (for example from "ดูซับช่วงนี้"): the cue `cueIndexAt(cues, at)` gets `aria-current="true"`, an accent ring (2 px `--accent`), `scrollIntoView({block: "center"})` inside the ScrollArea viewport, and focus.

**Frames changes (`frames.tsx`):**
1. **Highlight from `at`.** `FramesSection` reads `at` from `useVideoParams()`. When set and the frames are loaded, the frame `nearestFrameIndex(frames, at)` gets `data-highlighted` styling (2 px `--accent` ring, BRD 10.7) and is scrolled into view (`block: "center"`) and focused once per distinct `at` value.
2. **"ดูซับช่วงนี้".** A fifth `ContextMenuItem` "ดูซับช่วงนี้" (icon `Captions`) after "คัดลอกลิงก์ช่วงนี้". It calls `update({tab: "transcript", at: frame.tMs})` (Q6 = ก). Visibility:
   - rendered only when `subtitlesQuery(videoId, true)` has succeeded with ≥ 1 track **and** a track is in effect;
   - otherwise the menu stays exactly as in M2 (4 items). BBB has no subtitles, so the M2 E2E `MENU_ITEMS` stays valid.

- [ ] **Step 1: Write failing unit tests.**
  - `searchLines`: Thai substring; English case-insensitive; `"  "` in the query is collapsed; empty query.
  - `nearestFrameIndex`: exact match, midpoint tie → earlier, before the first frame, after the last frame, empty.
  - `cueIndexAt`: before the first cue, inside a cue, in a gap between cues, after the last cue.
- [ ] **Step 2: Write `web/e2e/transcript.spec.ts`** (runs at the gate; `88o5Sk8_m1Y` has storyboard fixtures and subtitles):
  - **FR-SUB-8 search:** `/v/88o5Sk8_m1Y?tab=transcript` → typing `กรุงเทพ` shows "พบ N บรรทัด" with N ≥ 1, and every visible line contains a `mark` with `กรุงเทพ`.
  - **Transcript → frames:** clicking the first visible line → the URL has `tab=frames&at=<ms>`; the frame nearest that time has the highlight ring (`data-highlighted`), is inside the viewport and is focused. Going back returns to W1/home in one step (replace semantics).
  - **Frames → transcript (Q6):** right-click frame `00:00:10` → the menu has 5 items, the last being "ดูซับช่วงนี้". Choosing it → `tab=transcript`, and the line covering 10 s has `aria-current="true"` and is visible.
  - **Keyboard:** the same through Shift+F10 on a focused frame.
  - **No subtitles:** `/v/aqz-KE-bpKQ` frame menu still has exactly 4 items; `?tab=transcript` shows "คลิปนี้ไม่มีซับ".
  - **No track in effect:** `/v/NOORIGSUB01?tab=transcript` shows the pick hint and the button to the ซับ tab.
  - axe: no serious/critical issues on the transcript tab with a search active, in both themes.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run** `npm run typecheck && npm run lint && npm test`. Expected: PASS.
- [ ] **Step 5: Commit** with the message `feat(web): transcript tab with search, transcript-frame linking, view subtitles here` + trailer.

---

## Wave 4

### Task 15: Network tests, docs, acceptance list, final verification, live preview

**Files:**
- Create: `tests/network/test_subtitles_network.py`, `tests/network_videos.toml`
- Modify: `PRD.md`, `BRD.md`, `docs/acceptance.md`, `docs/m2-followups.md`, `README.md`, `web/dist/**`, and `web/src/i18n/th.ts` (only to remove the `download*` keys if Q1 = ข)

**Depends on:** the wave 3 gate.

- [ ] **Step 1: Create `tests/network_videos.toml`** (PRD section 9 list, the M3 part):
```toml
[subtitles]
thai_asr = "88o5Sk8_m1Y"      # th-orig, CC BY
multi_audio_orig = "8lpOfyoxcvU"  # th original + en-US dub, two -orig tracks, CC BY
owner_subs_chapters = "jNQXAC9IVRw"  # owner en/de, 3 chapters
owner_thai = "iG9CE55wbtY"    # owner th (TED)
no_subs = "aqz-KE-bpKQ"
```
- [ ] **Step 2: Write `tests/network/test_subtitles_network.py`** (`@pytest.mark.network`). It uses the real extractor with a temp db and cache, and `SubtitleService`.
  - Each clip's tracks match the fake-fixture expectations (default track ids as in T8).
  - `88o5Sk8_m1Y` `a.th-orig` tokens come from json3 and pass the AC-SUB-03/04 checks at medium.
  - A forced vtt path (call `parse_vtt(fetch_subtitle(track.vtt))` directly) passes the same checks.
  - The translated `t.en` URL built with `tlang` returns English text (ASCII letters in ≥ 50% of the chars). This verifies the "not yet verified" item.
  - Report the timings of probe + tokens.
  - Run `uv run pytest -m network -q tests/network/test_subtitles_network.py -s` once and paste the result into the commit message. A failure caused by YouTube (bot check) is reported, not "fixed" by loosening tests.
- [ ] **Step 3: Update the docs.**
  - **`PRD.md`:**
    - API table: the `/subtitles/{trackId}/export` row (Q1 = ก), and the note "M4 moves subtitle export into `/jobs` (`subtitle`) and saves to the output folder".
    - Add `E_NO_SUBTITLES` to the 404 list in the HTTP status note.
    - W2: the URL params `tab`/`track`/`at` with replace semantics; the "ดูซับช่วงนี้" behaviour (Q6); the ตัวเลือกขั้นสูง note (Q5); the header track badge; the translated-subtitle dialog.
    - Section 9: mark "Fixture ที่ต้องเก็บก่อนเริ่ม M3" as collected, and point to `tests/fixtures/README.md`.
    - AC-SUB-05 wording if Q3 = ข; FR mapping unchanged.
  - **`BRD.md`:**
    - Decision log rows #49 onwards, one per owner answer Q1–Q9, dated with the answer date and written in the log's style.
    - A correction note under 11.1: "yt-dlp 2026.08.19: auto `th` of a Thai clip = the same file as `th-orig` (no `tlang`); translations carry `tlang`".
    - Under 12.2 step 3, a note on the merge factor (Q3).
    - Under 12.3 a note that splitting happens in the parser, and so applies to the whole untimed track.
    - FR-SUB-3 amended if Q8 = ก.
  - **`docs/acceptance.md`:** a new "## M3" table of manual checks:
    - open a downloaded `.srt` in Notepad (Thai readable; line breaks correct) and in CapCut/Premiere or VLC with any video (the cues show at the right times);
    - AC-SUB-07 by feel (drag the slider on a 1 h clip, and the preview follows without lag);
    - copy chapter and description, then paste into LINE and Word;
    - transcript line → frame, and "ดูซับช่วงนี้" → transcript;
    - a real Thai clip with no owner subtitles picks the automatic Thai track;
    - a TED clip picks Thai owner subtitles (Q8 = ก).
  - **`docs/m2-followups.md`:** move the M3 tabs item to a "ทำแล้วใน M3" line.
  - **`README.md`** (dev section): the list of fake clip ids for M3 (`88o5Sk8_m1Y`, `NOORIGSUB01`, `VTTFALLBAK1`, `LONGTHAI1hr`) and what each shows.
  - Docs written in Pete's voice follow the existing style of those files.
- [ ] **Step 4: Run the full verification** on the integration branch:
  - `uv run pytest -q -W error`
  - `cd web && npm ci && npm run typecheck && npm run lint && npm test && npm run build && npm run e2e`
  - The bundle is ≤ 400 KB gz without fonts.
  - `git grep -n "TODO" -- src web/src` → none.
  - `git grep -nI $'\r' -- ':!*.bat' ':!tests/fixtures/subs/golden/**' ':!web/dist/**'` → none.
  - `git grep -n "import yt_dlp\|from yt_dlp" -- src` → only `core/extractor.py`.
  - `git grep -n "shell=True" -- src` → none.
  - `git grep -n "sys.platform\|os.name\|platform.system" -- src ':!src/yttoolkit/platform'` → none.
  - Rebuild and commit `web/dist` (`build(web): rebuild dist for M3`).
- [ ] **Step 5: Live preview for Pete** (memory: preview after QA).
  1. Start the real (non-fake) app with `YT_TOOLKIT_DATA_ROOT=<scratchpad>/m3-preview uv run python -m yttoolkit serve --port 8791` in the background, and record its PID.
  2. Open `http://127.0.0.1:8791/` in the Browser pane.
  3. Give Pete a short Thai checklist:
     - วางลิงก์คลิปไทยที่ไม่มีซับเจ้าของ เช่น `https://youtu.be/88o5Sk8_m1Y`
     - ลองแท็บซับ: สลับสั้น/กลาง/ยาว, ปรับเอง, โหลด .srt แล้วเปิดดู
     - ลองแท็บทรานสคริปต์: ค้นหา, คลิกบรรทัดแล้วไปภาพเฟรม
     - คลิกขวาภาพเฟรม → ดูซับช่วงนี้
     - คัดลอก chapter (`https://youtu.be/jNQXAC9IVRw`)
     - คลิป TED `https://youtu.be/iG9CE55wbtY` ได้ซับไทย
  4. Stop the server **by PID** only after Pete says he is done. Never touch :8787.
- [ ] **Step 6: Commit** the docs and network test with the message `docs: M3 decisions, API rows, acceptance checklist; network subtitle checks` + trailer.
  - Push the branch and open the PR **only when the controller says so** (the owner decides). Then watch CI until all 4 jobs (python on Windows and macOS, web, e2e) are green.

---

## AC coverage

| AC | Test level | Where |
|---|---|---|
| AC-SUB-01 | U | T8 `test_tracks.py` (88o5, 8lpO) · also E in T13 |
| AC-SUB-02 | U, E | T8 (`NOORIGSUB01` default None, groups) · T13 e2e (empty select + hint, dialog with warning) |
| AC-SUB-03 | U | T7 (no aAppend/`\n` tokens) · T12 (no identical adjacent cues, all presets, json3 + vtt) |
| AC-SUB-04 | U | T7 (tokens rejoin to the source) · T12 (cues at token boundaries) · T4 property test |
| AC-SUB-05 | U | T4 property test · T12 (medium on real fixtures) |
| AC-SUB-06 | U (both) | T12 byte goldens: Python `test_srt_golden.py` + TS `srt-parity.test.ts` · T4/T9 shared `builder-cases.json` |
| AC-SUB-07 / NFR 200 ms | E (+U guard) | T13 e2e on `LONGTHAI1hr` · T9 perf guard |
| AC-SUB-08 | U | T4 property test · T11 export bytes · T12 goldens |
| AC-SUB-09 | U | T7 `split_block` · T12 end-to-end at medium |
| AC-SUB-11 | U (+E) | T7 vtt parser · T11 fallback via `VTTFALLBAK1` · T12 · T13 e2e |
| AC-PROBE-03 | U, E | T10 `chapters.test.ts` + `video-tabs.spec.ts` |
| AC-PROBE-04 | E | T10 `video-tabs.spec.ts` (BBB description byte-exact) |
| FR-SUB-5 (4 exports) | U, E | T4 (txt/md rules) · T11 API · T13 e2e |
| FR-SUB-8 | E | T14 |
| W2 tabs (BRD #48) | E | T10, T14 |
| "ดูซับช่วงนี้" | E | T14 |
