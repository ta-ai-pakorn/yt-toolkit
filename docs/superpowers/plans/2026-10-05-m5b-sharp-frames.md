# M5 round B ภาพคม (sharp frames) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Tasks inside one wave run as parallel subagents, each in its own git worktree (see "Waves" and "Lane rules"). Every task is reviewed by a reviewer subagent before its wave closes.

**Goal:** In W2 the user presses "ขอภาพคม", picks "same times as fast frames" or "every N seconds" in a small dialog (with frame count, temporary download size and resolution shown up front), and the queue downloads the clip video-only at ≤ 720p, cuts one sharp JPG per timecode with ffmpeg (long side 1280 px), deletes the video, and puts the set both in the in-app cache (the frames grid gets a [ภาพเร็ว | ภาพคม] switch) and in a folder in the output folder; a finished full-clip `video` download of ≥ 720p SDR also makes a sharp set automatically from the file on disk (cache only); contact sheet and zip work from either set.

**Spec:** `docs/superpowers/specs/2026-10-05-m5b-sharp-frames-design.md` (owner decisions D1-D8, final Thai copy). Requirements: FR-FRAME-2, FR-FRAME-3, FR-FRAME-5 (sharp source), AC-FRAME-03, AC-FRAME-04, BRD #33 (the `E_NO_STORYBOARD` text changes at M5), and the `source: "sharp"` item of `docs/m4-followups.md`.

**Out of scope (round B):** sharp frames in W3 (D7), more than one sharp set per clip, history of sets, tone-mapping in the automatic step or in the round A cut path, choosing JPG quality or resolution in the UI, YouTube cookies (round C).

**Architecture:**
- **Pure plan, shared by both sides.** `core/sharp.py` (`plan_sharp`) and `web/src/lib/sharp-frames.ts` (`planSharp`) compute the timecodes from the clip's integer `durationS`, the requested `intervalS` and the fast-frame times; both read the same golden cases `tests/fixtures/sharp/plan-cases.json`. The fast-frame times come from the probe stored in the database (`storyboard.plan_frames(pick_storyboard(raw), raw["duration"])`), so the backend never fetches storyboard sheets to plan and the automatic step needs no network.
- **Approach ก (D1): reuse the M4 download path.** The `frames_sharp` handler calls the same `Downloader.download` with a new pure chooser `download.sharp_choice` (video-only, short side ≤ 720, SDR first, avc1 > vp9 > av01, smallest size; muxed fallback), so pacing, the bot-check brake, progress, retry and cancel are the M4 ones. `core/extractor.py` stays the only `yt_dlp` importer; it only learns to report the downloaded format's width, height and dynamic range (`DownloadResult.media`).
- **One ffmpeg call per frame** (`media.frame_args`, `MediaTools.extract_frame`): `-ss <t>` before `-i` on the local file, `scale=w='min(1280,iw)':h='min(1280,ih)':force_original_aspect_ratio=decrease`, `-q:v 2`; a timecode that yields no image is dropped (only possible inside the last second); HDR-only clips get a `setparams` + `zscale` + `tonemap=hable` chain in front (manual job only).
- **Cache + output, both crash-safe.** `core/sharp_store.py` builds `<cache>/<id>/sharp.tmp-<jobId>/`, then swaps it in (`sharp/` → `sharp.old-<jobId>/`, tmp → `sharp/`, delete old). The output folder `<clip folder>/<ชื่อคลิป> - ภาพคม[ (n)]/` is reserved with an exclusive `mkdir`, filled with a `.yttoolkit-partial` marker present, and the marker removed last (`files.move_files_into_dir`). The startup sweep removes leftovers of both (and restores `sharp.old-*` if a crash hit between the two renames).
- **Automatic step (D6)** runs inside the `video` handler after the file is final in the output folder, reads that file, and can never fail the job (every error, cancel and shutdown is caught and logged; the job ends `done`).
- **Web:** a `sharpQuery` (`GET /videos/{id}/sharp`, 404 = `null`), a per-visit fast/sharp choice in `FramesSection`, a `SharpRequestButton` + dialog driven by the pure `sharpDialogModel`, a settings switch, queue text for the two new stages and the folder output, and an SSE hook that refreshes the sharp query when a `frames_sharp` or `video` job of the clip finishes.

**Tech Stack:** unchanged (Python 3.13 + uv, FastAPI, pydantic v2, yt-dlp 2026.08.19 as a library, ffmpeg 8.1 from `bin/` or PATH, Pillow, React + Vite + Tailwind + shadcn/Base UI 1.8 + react-query 5, Vitest, Playwright). No new Python or npm dependency (the radio group is a new shadcn-style wrapper over the installed `@base-ui/react/radio-group`).

---

## Owner decisions (from the spec, 2026-10-05)

| # | Decision | Where in this plan |
|---|---|---|
| D1 | Approach ก: download the whole clip video-only ≤ 720p into the job's work folder, extract with ffmpeg, delete the video | C3 `sharp_choice`, C5, T8 |
| D2 | Sharp frames go to the in-app cache **and** to a folder of JPGs in the output folder | C6, C7, T8 |
| D3 | "ขอภาพคม" opens a small dialog first: "same times" (default) or "every N seconds", with count and download size before queueing | C2, C10, T11, T15 |
| D4 | 720p = short side ≤ 720; frames scaled to long side 1280 (portrait 720×1280); AC-FRAME-03 reads "long side ≥ 1280" | C3, C4, T4, T17 (BRD note) |
| D5 | One sharp set per clip in the app (a new request replaces it); output folders never overwritten (` (2)`) | C6, C7, T5, T8 |
| D6 | Automatic sharp frames after a full-clip `video` job ≥ 720 short side, not HDR; cache only; setting on by default | C1 `autoSharpFrames`, C8, T14, T12 |
| D7 | No sharp frames in W3 in round B (automatic step still applies to W3 `video` jobs) | W3 untouched; T14 covers every `video` job |
| D8 | Manual jobs prefer SDR (tone-map only if no SDR exists); automatic step skips HDR files | C3, C4, T3, T4, T14 |

### Planner decisions (not owner questions; Pete can still object)
- **Format selection lives in `core/download.py`, not `core/extractor.py`.** Spec 3.3 says "inside core/extractor.py, the only place that imports yt_dlp"; every M4/M5-A chooser (`video_choice`, `audio_choice`) is a pure function in `download.py` handed to `Downloader.download` as `choose`, and it imports no `yt_dlp`. `sharp_choice` follows that pattern, so the protocol does not change and the rule "only extractor.py imports yt_dlp" still holds.
- **The output folder sits inside the clip folder:** `<output>/<folder?>/<ชื่อคลิป> [<id>]/<ชื่อคลิป> - ภาพคม/frame_HH-MM-SS.jpg`. Spec 3.5 writes `<output>/<folder?>/<ชื่อคลิป> - ภาพคม/`, but every job of a clip writes into the clip folder (files.py rule, `แหล่งที่มา.txt`, lifecycle sweep), and the stem goes through the same `plan_output` length rules.
- **Folder output:** `OutputFile` gains `files: int | None` and the kind `"folder"`; the API lists it as `{index, name, sizeBytes, files}`. "เปิดโฟลเดอร์" opens the folder itself (`open_folder`, not `reveal`), and `GET /jobs/{id}/outputs/{i}` stays 404 for a folder (the queue row hides "ดาวน์โหลด" for it).
- **Queue title "{title} · ภาพคม {n} ภาพ" is built on the web** (`jobTitle`), with `n` from the folder output's `files` (done) or from the `extracting_frames:i/n` stage (running). The job's stored `title` stays the clip title (the lifecycle sweep finds the clip folder from it). Before extraction starts the row reads "{title} · ภาพคม", exactly the spec's "until it is known".
- **Notes with a value** are stored as `"CODE:value"` (`"SHARP_LOW_RES:480"`, `"SHARP_INTERVAL_RAISED:4"`); `Job.to_api` fills `{h}` / `{n}` into the message. Old notes are unchanged.
- **`E_FFMPEG_MISSING` at enqueue stays HTTP 409** (spec 3.1/6 say 422). The existing API, the web toast with "ไปหน้าตรวจสุขภาพ" and its tests all use 409; `frames_sharp` only joins `FFMPEG_KINDS`.
- **Over 200 frames in "same times" mode:** the dialog shows the over-limit line with `{N}` = the storyboard interval with one decimal (e.g. `4.9`) and sends `intervalS = N2`. A `{}` request on a > 200 storyboard (API caller) still falls back to `N2` with the note.
- **Custom field default** is `max(1, ceil(durationS / 100))` with or without a storyboard (the spec fixes it only for the no-storyboard case; the field needs a value).
- **Size estimate (web):** among `VideoInfo.video[]` with the largest short side ≤ 720, prefer avc1 > vp9 > av01, then the smallest known size (same order as the backend minus the SDR rule, which `VideoInfo` does not carry). No format ≤ 720 at all (rare): the smallest short side above 720, on both sides.
- **Partial output folders are recognised by a marker file** (`.yttoolkit-partial`), not by name alone: the startup sweep deletes a `<prefix> - ภาพคม[ (n)]` folder only when the marker is inside and it is not a done job's output, so a finished folder of the user is never removed even when the job history is gone.
- **Atomic swap on Windows:** renames retry for up to 2 s (`PermissionError` while the browser still reads a frame); the startup sweep restores `sharp.old-*` to `sharp/` when `sharp/` is missing (crash between the two renames), otherwise deletes it.
- **Automatic step reads the file facts from yt-dlp** (`requested_downloads[-1]` carries the merged `width`, `height`, `dynamic_range`); unknown facts (e.g. a fake clip without `media`) = skip, never guess.
- **Sharp contact sheet / zip names** are the same as the fast ones (`<ชื่อคลิป> - contact sheet.jpg`, `<ชื่อคลิป> - frames.zip`); a second file gets ` (2)` by the M4 rule.
- **Toolbar placement:** the "ขอภาพคม" button sits right after the bulk ButtonGroup in the same wrapping row (spec 1.1 "next to"), not inside the ButtonGroup: three joined buttons would overflow the existing 390 px W2 test, a separate item wraps instead.
- **Auto-switch on finish:** the web refreshes `["sharp", videoId]` whenever a `frames_sharp` **or** `video` job of that clip turns `done` (the web cannot tell whether the automatic step ran; a 404 refresh is cheap).
- **No format ≤ 720 at all:** take the smallest short side above 720 (still scaled to long side 1280); no video format at all = `E_UNKNOWN` (`no video format`).
- **The fake extractor reports no `media` unless `behaviors.json` sets it**, so existing fake `video` jobs never run the automatic step; the new fake clip `AUTOSHARP01` does.

## Questions for the owner

None blocking. Every ambiguity is ruled above.

**Owner inputs needed before the network run (T17 writes the test, nobody runs it without approval):**
1. Approval to run `tests/network/test_sharp_network.py`: about 40-70 MB of downloads (`88o5Sk8_m1Y` 720p video-only, 372 s; `IngFfl6DTqY` 720×1280 video-only, 60 s), all deleted after the run.

---

## Waves

Integration branch: `m5b-sharp-frames` (already checked out; the spec is commit `060ab34`).

| Wave | Lanes (one worktree each, file sets disjoint) | Depends on |
|---|---|---|
| 1 | T1 job notes/stages/folder output/settings/error copy · T2 timecode plan (Python + TS parity) and dialog maths · T3 sharp format choice, download media facts, fake clips · T4 frame extraction (ffmpeg args, real + fake) · T5 sharp cache store, output folder, frame names · T6 web strings and types | spec |
| 2 | T7 API (`frames_sharp` params, `source: "sharp"`, `GET /sharp`, folder outputs) · T8 manual `frames_sharp` handler + sharp contact sheet / zip · T9 lifecycle sweep of the new leftovers · T10 W2 frames grid: fast/sharp switch, bulk source, refresh on finish · T11 "ขอภาพคม" button + dialog component · T12 settings switch · T13 queue text and folder row | gate 1 (T7←T1,T2,T3,T5 · T8←T1-T5 · T9←T5 · T10←T6 · T11←T2,T6 · T12←T6 · T13←T6) |
| 3 | T14 automatic sharp step + lifecycle wiring · T15 mount the button in W2 + dialog e2e · T16 queue e2e (real fake backend) · T17 docs + network test (written, not run) | gate 2 (T14←T8,T9,T1 · T15←T10,T11 · T16←T7,T8 (+T14 at the final gate) · T17←all) |
| final | controller: merge, full checks, `npm run build`, `npm run e2e`, commit `web/dist`, reviews, live preview for Pete | gate 3 |

**Critical path:** T3 / T4 / T5 → T8 → T14 → final gate (`queue` e2e project).
**Counts:** 3 waves + final gate · 17 tasks (= 17 lanes).

### Lane rules (every task)
1. **Worktree and branch.** Each task runs in its own git worktree (`isolation: "worktree"`) on branch `m5b/t<N>-<slug>`, branched from the head of `m5b-sharp-frames` at the start of its wave. Do not switch the main checkout's branch.
2. **Files.** A task creates or modifies **only** the files in its **Files** list. Needing another file is a plan bug: stop and report it to the controller; do not edit the file.
3. **Shared files have exactly one owner per wave:**

   | File | W1 owner | W2 owner | W3 owner |
   |---|---|---|---|
   | `src/yttoolkit/core/jobs.py`, `core/settings.py`, `core/yterrors.py`, `tests/unit/test_jobs_store.py`, `tests/unit/test_settings.py` | T1 | — | — |
   | `tests/unit/test_yterrors.py` | T1 | — | T17 |
   | `src/yttoolkit/core/sharp.py`, `web/src/lib/sharp-frames.ts`, `tests/fixtures/sharp/**` | T2 | — | — |
   | `src/yttoolkit/core/download.py`, `core/extractor.py`, `tests/fixtures/downloads/behaviors.json`, `tests/fixtures/README.md` | T3 | — | — |
   | `src/yttoolkit/core/media.py` | T4 | — | — |
   | `src/yttoolkit/core/sharp_store.py`, `core/files.py`, `core/frames.py`, `core/storyboard.py` | T5 | — | — |
   | `web/src/i18n/th.ts`, `web/src/lib/types.ts` | T6 | — | — |
   | `src/yttoolkit/api/jobs.py`, `api/videos.py` | — | T7 | — |
   | `src/yttoolkit/core/handlers.py` | — | T8 | T14 |
   | `src/yttoolkit/lifecycle.py`, `tests/unit/test_lifecycle.py` | — | T9 | T14 |
   | `web/src/pages/video/frames.tsx` | T6 (tooltip only) | T10 | T15 |
   | `web/src/pages/video/queries.ts`, `web/src/lib/events.ts` | — | T10 | — |
   | `web/src/pages/video/tabs.tsx`, `web/e2e/video.spec.ts` | — | — | T15 |
   | `tests/helpers_sharp.py` | — | T8 | — |
   | `web/src/pages/video/sharp-dialog.tsx`, `web/src/components/ui/radio-group.tsx` | — | T11 | — |
   | `web/src/pages/settings/general-*.ts(x)` | T6 (test fixture line only) | T12 | — |
   | `web/src/components/queue/job-text.ts`, `job-row.tsx` | — | T13 | — |
   | `PRD.md`, `BRD.md`, `docs/**` (except this plan), `tests/network*` | — | — | T17 |
   | `web/dist/**` | final gate only; **no lane builds into or commits `web/dist`** | | |

   A lane that needs a Thai string that is not in C10 stops and asks the controller; the controller adds it at the gate (T6 is the only writer of `th.ts`).
4. **Tests.**
   - Python lanes run their own tests, then the full `uv run pytest -q -W error -p no:cacheprovider`.
   - Web lanes run `cd web && npm run typecheck && npm run lint && npm test`.
   - Lanes **do not run Playwright.** Specs are written, typechecked and linted in the lane and run at the final gate (the controller may also run them at gate 2).
   - **No spec in the default `chromium` project may create a real job or change real settings.** A chromium spec that clicks an enqueue button first calls `mockEnqueue(page)`; one that flips a setting stubs `/api/settings` (`stubSettings` in `settings-general.spec.ts`). Real jobs only in `queue-*.spec.ts` (the `queue` project).
   - Network tests (`@pytest.mark.network`) are written in T17 and **never run** without Pete's approval.
5. **Processes.** No lane starts a server. Never touch the owner's app on port 8787. Kill processes by PID only.
6. **Commits.** Every commit message ends with exactly `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`. Use `git commit -F- <<'EOF' … EOF`.
7. **Line endings.** Never change a file's existing line endings: edit with the Edit tool (or `open(..., newline="")`); new files are LF.

### Wave gate procedure (controller, serial)
1. Merge every lane branch of the wave into `m5b-sharp-frames` with `git merge --no-ff m5b/t<N>-<slug>`. A merge conflict means the plan is wrong: stop and report.
2. `uv sync --frozen && uv run pytest -q -W error -p no:cacheprovider` (must pass; real-ffmpeg tests run on the dev machine).
3. `cd web && npm ci && npm run typecheck && npm run lint && npm test`.
4. Gate 2 (recommended, not committed): `cd web && npm run build && npm run e2e` to catch W2 UI failures before wave 3; failures go back to T10/T11/T12 as a fix round. Do **not** commit `web/dist` at gate 1 or 2.
5. Run the two-stage review (spec compliance, then code quality) from superpowers:subagent-driven-development on each task of the wave, and fix findings in the owning lane before the next wave.

### Final gate (controller, after wave 3)
1. Merge T14-T17 (`--no-ff`), then steps 2-3 above.
2. `cd web && npm run build` then `npm run e2e` (project `chromium` on `E2E_PORT` (8799) and project `queue` on `E2E_PORT + 1`, both fake mode, built `dist`). A failing `queue-sharp.spec.ts` goes back to T8/T14/T16; chromium failures to T10/T11/T15.
3. Check total JS gzip ≤ 400 KB excluding fonts (PRD 6.5).
4. Commit the rebuilt `web/dist` as `build(web): web/dist after M5 round B` (with the trailer).
5. Reviews as in step 5 above, then a live preview for Pete on port 8791 (memory rule "preview after QA"): fake mode is enough for the dialog, the grid switch and the automatic step (`AUTOSHARP01`); real downloads only with his approval.

---

## Verified facts (read or measured on 2026-10-05 in this repo)
- **Branch** `m5b-sharp-frames`, head `060ab34` (spec commit). `.gitattributes` keeps every tracked `.py`, `.ts`, `.json`, `.md` LF (`git ls-files --eol` shows `i/lf w/lf` for `behaviors.json` and `th.ts`).
- **Kinds and gates.** `core/jobs.py:23` already lists `frames_sharp` in `JOB_KINDS`; `core/download.py:16` has it in `YOUTUBE_KINDS` (pacing + brake), `:17` `FFMPEG_KINDS = frozenset({"video", "audio"})`, asserted in `tests/unit/test_download_choice.py:346`. `api/jobs.py:248` `NewJobModel.kind` excludes `frames_sharp`; `:221-227` `ContactSheetParams`/`FramesZipParams` have `source: Literal["fast"]`; `:354-356` a missing ffmpeg answers **409** `E_FFMPEG_MISSING`. `tests/api/test_jobs_api.py:145` and `:160` list `frames_sharp` and `source: "sharp"` as 422 rows (T7 removes them).
- **Stages and notes.** `core/jobs.py:25-30` `STAGES` + `SPLIT_STAGE`; `:65-66` `is_stage`; `:281-287` `_encode` and `core/queue.py:97-99` `_JobContext.stage` both validate through `is_stage`, so extending `is_stage` is enough. `Job.to_api` (`core/jobs.py:220`) maps notes with `NOTES[code]`; `_dump_outputs`/`_load_outputs` (`:234-248`) store `root, rel, sizeBytes, kind`.
- **Handlers.** `core/handlers.py:72-87` `HandlerDeps` (no settings access today); `:93-121` `_Reporter`; `:152-162` `_start` (probing, title, output root); `:183-211` `_disk_checked(choice, paths, disk_free, factor)`; `:511-530` `_finish` moves one file and writes `แหล่งที่มา.txt`; `:533-547` `_write_note`; `:557-612` `_video` returns `_finish(...)` at the end; `:791-824` `_frames`/`_contact_sheet`/`_frames_zip` read the storyboard cache; `:827-844` `build_handlers` has no `frames_sharp` entry.
- **Queue end states.** `core/queue.py:340-362` `_run_job`: a handler that **returns** after a cancel request still ends `done` (`_finish`), so the automatic step can swallow `JobCancelled`; `_clear_workdir` deletes `work/<jobId>/` on every end (`:434-436`).
- **Storyboard.** `core/storyboard.py:68-80` `pick_storyboard(raw)`, `:87-102` `plan_frames(sb, duration_s)`; `build` writes exactly `plan_frames(...)` times into `index.json` (`:321`, `:284-290`), so `[s.t_ms for s in plan_frames(pick_storyboard(raw), raw.get("duration"))]` equals the fast set's `tMs` list without fetching any sheet. `_file_name(index)` (`:250-251`) is `f_{index:04d}.jpg`. `build` sweeps only `storyboard.tmp-*` (`:326`). `VideoService.raw` (`core/videos.py:709`) reads the stored probe and probes only when missing.
- **Frames.** `core/frames.py:66` `file_timecode`; `:345-368` `frames_zip` names `frame_HH-MM-SS.jpg` with `_2`, `_3` for the same second; `:271-279` `_load_cell` fits any size into 320×180 with `ImageOps.pad` (downscale of sharp frames works unchanged); `:263-268` `_missing` always raises `E_NO_STORYBOARD`.
- **Files.** `core/files.py:99-124` `plan_output` (budget, `TAIL_MAX`, fallback to `<id>/<id>`); `:162-168` `_candidates` uses `path.stem`/`path.suffix`, which would split a folder named `Ep.1 - ภาพคม` at the dot (folders need their own candidates); `:179-188` `_reserve`; `:191-203` cross-device copy via `.part`; `:206-224` `move_into_place`.
- **Cache API.** `api/videos.py:234-254` storyboard route adds `?v=<index.json mtime_ns>`; `:276-289` `cache_file` marks frames `immutable` and names downloads only when `parts[0] == "storyboard"`; `:50-68` `STATUS_BY_CODE`; `:348-357` `_frame_download_name(folder, file)` reads `index.json` of the frame's own folder.
- **Settings.** `core/settings.py:143-156` `_VALIDATORS`, `:163-178` defaults; `tests/unit/test_settings.py:26-50` asserts the full defaults dict (T1 adds `autoSharpFrames`).
- **Errors.** `core/yterrors.py:22` old `E_NO_STORYBOARD` text; `tests/unit/test_yterrors.py:103-110` asserts it and `:135-147` checks every message against a PRD row (codes without a PRD row go in `PRD_PENDING`, `:25`). PRD line 780 already carries the M5 text in quotes, so the new `E_NO_STORYBOARD` passes; `E_NO_SHARP_FRAMES` is pending until T17 adds its PRD row.
- **yt-dlp merge facts.** `.venv/Lib/site-packages/yt_dlp/YoutubeDL.py:2506-2517` copies `width`, `height`, `dynamic_range`, `vcodec` of the only video format into the merged format; `:2976-2977` fills `dynamic_range = "SDR"` for every video format that lacks it; `:3150` sets `info_dict['requested_downloads']`.
- **Probe fixture BBB** (`tests/fixtures/probe/aqz-KE-bpKQ.json`, 635 s, 128 fast frames): 720p candidates `311` (avc1, HLS, no size), `298` (avc1, 150 524 867 B), `302` (vp9, 112 676 322 B), `398` (av01, 71 283 827 B); no `dynamic_range` field (trimmed probe). ZOO `jNQXAC9IVRw` 19 s, no storyboard, 240p max.
- **ffmpeg 8.1 experiments (scratchpad, Gyan full build):**
  - `-ss 1.000 -i portrait(1080x1920).mp4 -frames:v 1 -vf "scale=w='min(1280,iw)':h='min(1280,ih)':force_original_aspect_ratio=decrease" -q:v 2 p.jpg` → 720×1280; on a 160×90 source → 160×90 (no upscale); on 1920×1080 → 1280×720.
  - `-ss 1.95` or `-ss 5` on the 2.0 s `tests/fixtures/media/video.mp4` (last frame at 1.9 s) → non-zero exit, no file written ("Nothing was written into output file").
  - Tone-map: `zscale=t=linear:...` alone fails with "no path between colorspaces" on a file whose transfer is untagged; `setparams=range=tv:color_primaries=bt2020:color_trc=smpte2084:colorspace=bt2020nc,zscale=t=linear:npl=100,format=gbrpf32le,zscale=p=bt709,tonemap=tonemap=hable:desat=0,zscale=t=bt709:m=bt709:r=tv,format=yuv420p,<scale>` works on that file (1280×720) and on an SDR file.
- **Web.** `web/src/pages/video/frames.tsx:428-446` `NoStoryboard` (disabled stub + tooltip `th.frames.availableLater`), `:459-511` `BulkDownloads` sends `source: "fast"`, `:521-597` `FramesSection({videoId, enabled, mostReplayed})`, rendered from `tabs.tsx:79` (which has `video`). `web/src/lib/types.ts:291` `NewJob.kind` excludes `frames_sharp`; `:191` `JobOutput`; `:276-278` fast-only `source`. `web/src/lib/events.ts:143-161` calls `onJobChange` only when the status changes. `web/src/components/queue/job-row.tsx:158-208` `DoneRow` renders a download link per output. `web/src/components/queue/job-text.ts:26-27` `jobTitle`. Settings literals that must gain the new key: `download-options.test.ts:590`, `download-prefs.test.ts:22`, `general-form.test.ts:19`, `use-advanced-choice.test.ts:22`. `SwitchRow` exists (`web/src/pages/video/advanced/switch-row.tsx`). `@base-ui/react` 1.8 ships `radio-group` and `radio` (no shadcn wrapper in `components/ui` yet). `formatBytes` (`web/src/lib/format.ts:92`) and `resolution` (`web/src/lib/download-options.ts:37`) exist.
- **E2E.** `web/e2e/queue-helpers.ts` exports `mockEnqueue`, `enqueue`, `waitForJob`, `openQueueSheet`, `cancelJobsFor`; `web/e2e/video.spec.ts:13` and `:494-504` assert the old no-storyboard copy and tooltip (T15 updates them); `settings-general.spec.ts` has `stubSettings`. The e2e data root is reset before each run; the backend runs in fake mode without ffmpeg (`FakeMediaTools`).
- **Web test environment:** Vitest runs in node (no jsdom); components are covered by Playwright only, so all logic that needs unit tests is written as pure functions. TS reads shared fixtures with `import raw from "../../../tests/fixtures/...json?raw"` (as `srt-range.test.ts` does).

---

## Global Constraints
**Carried over:** every Global Constraint of `docs/superpowers/plans/2026-10-01-m4-downloads.md` (and through it M3, M2, M1): Python 3.13 + uv; bind `127.0.0.1` only; error envelope `{"error":{"code","message","detail"}}`; `pathlib` everywhere; `core/` never imports `api/` or `platform/`; every screen has loading / empty / error / normal; no TODO comments; unit and API tests never touch the network; network tests carry `@pytest.mark.network`; all web strings live in `web/src/i18n/th.ts`; backend user-facing messages live in `core/yterrors.MESSAGES` and `core/jobs.NOTES`; never log an absolute output path; at most one amber primary button per page (W2: "โหลด mp4").

**Project rules (owner, verbatim):**
- Commit messages end exactly with "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>".
- Never `shell=True` (no `os.system` / `os.popen`; external programs get an argument list).
- Only `yttoolkit.platform` checks the OS.
- `yt_dlp` is imported only in `core/extractor.py`.
- No personal data, tokens or cookie values in logs.
- Kill processes by PID only.
- Never touch the owner's app on port 8787.
- Thai UI copy only from the spec (buttons start with a verb, no "กรุณา", no "!").
- Narrow-window rule BRD #83: check at 640 px (a narrow desktop window / 200% zoom), not phones; nothing overflows horizontally (`document.documentElement.scrollWidth <= clientWidth`); no new phone-only polish.
- Chromium-project e2e specs never create real jobs (`mockEnqueue`); real jobs only in `queue-*.spec.ts`.
- Python edits on Windows must preserve CRLF line endings (blobs are CRLF, core.autocrlf=true) — use the Edit tool or `newline=''`. (Verified fact: tracked `.py` files are currently LF; the rule is applied as "never change a file's existing line endings".)
- Do not build/commit `web/dist` in lanes (the controller builds at the end).

**M5-B specific:**
- `MAX_SHARP_FRAMES = 200` is enforced by the shared plan on both sides; the backend never trusts the web's count.
- The automatic step never changes the `video` job's outcome, outputs or notes, never writes to the output folder, and never touches the network.
- A manual sharp set is never replaced by an automatic one; a manual request always replaces the cache set.
- The startup sweep never deletes a folder in the output folder that lacks `.yttoolkit-partial`; a handler deletes only the folder it created in the same run.
- Log lines name the job id, the stage and the error type only (no paths, no titles).
- Accessibility: the dialog has a title, the radio group is labelled, the number field has an accessible name and an `aria-describedby` error, the toggle group has `aria-label="ชุดภาพเฟรม"`; axe has no serious/critical findings in both themes.

**Tests:**
- Backend: `uv run pytest -q -W error -p no:cacheprovider` (no warnings).
- Web: `cd web && npm run typecheck && npm run lint && npm test` (ESLint 0 errors / 0 warnings).
- Final: `cd web && npm run build` then `npm run e2e`.
- Real-ffmpeg tests use `requires_ffmpeg` from `tests/helpers_ffmpeg.py`.

---

## Review Focus (inputs the spec implies that would most likely bite a real user)
1. **Clip title with a dot, or very long, under a deep output folder** (`Ep.1 วิธีทำ…`, 100 Thai characters) → the folder is `Ep.1 วิธีทำ… - ภาพคม`, a repeat gets ` (2)` after the whole name (never `Ep (2).1 …`), and the longest frame path stays ≤ 240 characters. Pinned by T5 `test_sharp_dir_candidates_keep_dotted_titles` and `test_sharp_dir_fits_240_with_the_longest_frame_name`.
2. **The swap meets a locked folder or a crash** (browser still reading a frame on Windows; app killed between the two renames) → the rename retries, a final failure leaves the previous set intact, and the next start restores `sharp.old-*` when `sharp/` is missing. Pinned by T5 `test_commit_retries_a_locked_rename_then_succeeds`, `test_commit_failure_keeps_the_previous_set`, `test_sweep_restores_the_old_set_when_sharp_is_missing`.
3. **Timecodes in the last second, or a download ffmpeg cannot read at all** → the end frames are dropped and the folder/cache/count show the real number; zero frames = `E_UNKNOWN`, no output folder, the previous cache set untouched. Pinned by T8 `test_frames_near_the_end_are_dropped` and `test_zero_frames_fails_and_keeps_the_old_set`.
4. **A long clip whose fast set has more than 200 frames** → the dialog shows the over-limit sentence with the one-decimal interval and sends `intervalS = N2`; an API `{}` request on the same clip still caps at 200 with the `SHARP_INTERVAL_RAISED` note. Pinned by the T2 golden case `same-times-over-200` (both suites), the T2 `sharpDialogModel` test "same times over 200" in `sharp-frames.test.ts`, and T8 `test_same_times_over_200_falls_back_with_a_note`.
5. **Cancel or app shutdown during the automatic step, or a manual set already in place** → the `video` job ends `done` with its file, no `sharp.tmp-*` is left, a manual set is not replaced. Pinned by T14 `test_cancel_during_auto_sharp_ends_done`, `test_shutdown_during_auto_sharp_ends_done`, `test_manual_set_is_not_replaced`.

---
## Shared contracts (every lane codes against these)

### C1. Notes, stages, folder output, setting, error copy (`core/jobs.py`, `core/settings.py`, `core/yterrors.py`, T1)
```python
# core/jobs.py
COUNT_STAGES = ("extracting_frames", "sharp_frames")
COUNT_STAGE = re.compile(r"(extracting_frames|sharp_frames):(\d{1,4})/(\d{1,4})")
def count_stage(name: str, index: int, total: int) -> str   # "extracting_frames:3/120"; ValueError unless name in
                                                            # COUNT_STAGES and 1 <= index <= total <= 9999
def is_stage(value: str) -> bool                            # STAGES or SPLIT_STAGE or COUNT_STAGE (fullmatch)
NOTE_VALUES = {"SHARP_LOW_RES": "h", "SHARP_INTERVAL_RAISED": "n"}   # notes whose message has one {value}
def valued_note(code: str, value: int) -> str               # "SHARP_LOW_RES:480"; ValueError for other codes / value < 0
def note_api(raw: str) -> dict | None                       # {"code", "message"} with the value filled; unknown/bad = None

@dataclass(frozen=True)
class OutputFile:
    root: str
    rel: str
    size_bytes: int
    kind: str          # + "folder" (M5 รอบ B: rel = the folder, size_bytes = sum of its files)
    files: int | None = None   # kind "folder" only: number of files in the folder
```
New `NOTES` (verbatim): `SHARP_LOW_RES` = `คลิปนี้มีภาพสูงสุด {h}p ภาพจึงเล็กกว่าปกติ` · `SHARP_INTERVAL_RAISED` = `ปรับเป็นทุก {n} วินาทีเพื่อไม่ให้เกิน 200 ภาพ`.
`Job.to_api`: `notes` = `[note_api(raw) for raw in notes]` without `None`; each output = `{"index", "name", "sizeBytes"}` plus `"files": n` when `files is not None`. Outputs JSON in the database gains `"files"` only when set (old rows load with `files=None`).
Settings: `autoSharpFrames: bool`, default `True`, validator accepts only `True`/`False` (`type(value) is bool`).
Errors (`core/yterrors.MESSAGES`, verbatim): `E_NO_STORYBOARD` = `คลิปนี้ไม่มีภาพตัวอย่างแบบเร็ว กด "ขอภาพคม" แทนได้` · `E_NO_SHARP_FRAMES` = `ภาพคมของคลิปนี้ถูกล้างไปแล้ว กด "ขอภาพคม" ใหม่ได้`.

### C2. Timecode plan and dialog maths (`core/sharp.py`, `web/src/lib/sharp-frames.ts`, golden `tests/fixtures/sharp/plan-cases.json`, T2)
```python
MAX_SHARP_FRAMES = 200
MAX_INTERVAL_S = 3600

@dataclass(frozen=True)
class SharpPlan:
    times_ms: tuple[int, ...]
    interval_s: int | None   # None = "same times as fast frames"
    raised: bool             # the interval was raised to fit 200 (note SHARP_INTERVAL_RAISED:<interval_s>)

def default_interval_s(duration_s: int) -> int          # max(1, ceil(duration_s / 100))
def raised_interval_s(duration_s: int) -> int           # ceil(duration_s / 200)
def custom_times(interval_s: int, duration_s: int) -> list[int]   # i*N*1000 while < duration_s*1000
def plan_sharp(duration_s: int, *, interval_s: int | None, fast_times: Sequence[int] | None) -> SharpPlan
    # ValueError: duration_s <= 0, interval_s outside 1..3600, fast_times empty
def fast_times(raw: Mapping[str, Any]) -> list[int] | None   # tMs of plan_frames(pick_storyboard(raw), raw["duration"]); no storyboard = None
```
Rules: same times (`interval_s` None, `fast_times` given) → the list as is, or `raised_interval_s` custom times + `raised` when > 200 · no storyboard (`interval_s` None, `fast_times` None) → `default_interval_s`, never raised · custom N → `custom_times(N)`, or `raised_interval_s` + `raised` when > 200.
```ts
export const MAX_SHARP_FRAMES = 200
export const MAX_INTERVAL_S = 3600
export type SharpPlan = { timesMs: number[]; intervalS: number | null; raised: boolean }
export function defaultIntervalS(durationS: number): number
export function raisedIntervalS(durationS: number): number
export function customTimes(intervalS: number, durationS: number): number[]
export function planSharp(durationS: number, opts: { intervalS: number | null; fastTimes: readonly number[] | null }): SharpPlan
export function parseIntervalText(text: string): number | null       // "  7 " -> 7 · "", "1.5", "0", "3601", "1e3" -> null
export type SharpEstimate = { sizeBytes?: number; shortSide: number | null; portrait: boolean }
export function sharpEstimate(video: readonly VideoFormat[]): SharpEstimate
export type SharpMode = "same" | "custom"
export type SharpFast = { intervalMs: number; timesMs: readonly number[] }
export type SharpResolution = { kind: "wide" } | { kind: "tall" } | { kind: "low"; h: number }
export type SharpDialogModel = {
  sameAvailable: boolean            // a fast set exists (the first radio is shown)
  mode: SharpMode                   // effective mode ("custom" when no fast set)
  sameInterval: string | null       // fast interval in seconds, one decimal ("4.9")
  sameCount: number | null          // fast frame count
  customCount: number | null        // count for the typed N (null when the text is invalid)
  customError: boolean              // custom mode and the text is invalid
  overflow: { n: string; count: number; n2: number } | null   // the over-200 sentence for the effective mode
  params: { intervalS?: number } | null                       // what "เริ่มดึงภาพคม" sends; null = disabled
  sizeBytes: number | null          // temporary download estimate (null = unknown)
  resolution: SharpResolution
  replace: boolean                  // a sharp set already exists
}
export const sharpKey: (videoId: string) => readonly ["sharp", string]   // react-query key of GET /videos/{id}/sharp
export function defaultCustomText(durationS: number): string
export function sharpDialogModel(input: {
  durationS: number; fast: SharpFast | null; mode: SharpMode; customText: string
  video: readonly VideoFormat[]; hasSharp: boolean
}): SharpDialogModel
```
Golden file shape: `{"cases": [{"name", "durationS", "intervalS": int|null, "fast": {"stepMs", "count"}|null, "expect": {"count", "first", "last", "intervalS": int|null, "raised", "times"?: int[]}}]}`; both suites build `fastTimes = [i*stepMs for i in range(count)]`.

### C3. Sharp format and download facts (`core/download.py`, `core/extractor.py`, `behaviors.json`, T3)
```python
FFMPEG_KINDS = frozenset({"video", "audio", "frames_sharp"})
SHARP_MAX_SHORT_SIDE = 720

@dataclass(frozen=True)
class SharpPick:
    format_id: str
    width: int | None
    height: int | None
    dynamic_range: str     # "SDR" when the format has none
    muxed: bool            # True = the format also carries audio (fallback when no video-only format exists)
    size_bytes: int | None
    @property
    def short_side(self) -> int      # min(width, height), height when width unknown, 0 when unknown
    @property
    def hdr(self) -> bool            # dynamic_range != "SDR"

def pick_sharp_format(info: Mapping[str, Any]) -> SharpPick | None
def sharp_choice(info: dict) -> tuple[DownloadChoice, SharpPick]
    # DownloadChoice(format_spec=<format_id>, merge_mp4=True, audio_language=None, notes=(), expected_bytes=size)
    # no video format at all -> YtError("E_UNKNOWN", "no video format")

@dataclass(frozen=True)
class MediaFacts:
    width: int | None
    height: int | None
    dynamic_range: str | None    # None = unknown
    @property
    def short_side(self) -> int | None
    @property
    def hdr(self) -> bool | None   # None = unknown

def media_facts(fmt: Mapping[str, Any]) -> MediaFacts

@dataclass(frozen=True)
class DownloadResult:
    path: Path
    info: dict
    choice: DownloadChoice
    media: MediaFacts | None = None   # facts of the file that was downloaded (None = unknown)
```
Selection: video formats (`_is_video`) with `0 < short side ≤ 720`, video-only first (`acodec == "none"`), muxed only when no video-only format exists; best = smallest key `(not SDR, -short_side, codec rank avc1 0 / vp09|vp9 1 / av01 2 / other 3, size unknown last, size, format_id)`. No format ≤ 720: the smallest short side above 720 (same key with `+short_side`).
`YtDlpExtractor.download` fills `media` from `requested_downloads[-1]` (or the top-level result) of `process_ie_result`; `FakeExtractor.download` fills it from the clip's `behaviors.json` entry `"media": {"width", "height", "dynamic_range"}` (absent = `None`).
New fake clips (both `probeAs` BBB, default steps): `SHARPCLIP01` title `คลิปภาพคม`; `AUTOSHARP01` title `คลิปภาพคมอัตโนมัติ`, `"media": {"width": 1280, "height": 720, "dynamic_range": "SDR"}`.

### C4. Frame extraction (`core/media.py`, T4)
```python
SHARP_LONG_SIDE = 1280
SHARP_JPEG_Q = 2

def scale_filter(long_side: int) -> str
    # "scale=w='min(1280,iw)':h='min(1280,ih)':force_original_aspect_ratio=decrease"
def tonemap_filter(dynamic_range: str) -> str
    # "setparams=range=tv:color_primaries=bt2020:color_trc=<smpte2084 | arib-std-b67 for HLG>:colorspace=bt2020nc,"
    # "zscale=t=linear:npl=100,format=gbrpf32le,zscale=p=bt709,tonemap=tonemap=hable:desat=0,"
    # "zscale=t=bt709:m=bt709:r=tv,format=yuv420p"
def frame_args(ffmpeg: str, src: Path, dst: Path, t_ms: int, *, long_side: int = SHARP_LONG_SIDE,
               dynamic_range: str | None = None) -> list[str]
    # [ffmpeg, -hide_banner, -nostdin, -y, -loglevel, error, -ss, <s.mmm>, -i, src, -frames:v, 1,
    #  -vf, [tonemap_filter(dr) + ","] + scale_filter(long_side), -q:v, 2, dst]
    # ValueError: t_ms < 0, long_side < 1, dynamic_range "" or "SDR" (callers pass None for SDR)

class MediaTools(Protocol):
    def extract_frame(self, src: Path, dst: Path, t_ms: int, *, long_side: int, dynamic_range: str | None,
                      cancel: Callable[[], bool]) -> bool: ...
    # True = a non-empty JPEG is at dst · False = ffmpeg wrote no image (timecode past the last frame)
    # cancel -> JobCancelled · ffmpeg gone -> E_FFMPEG_MISSING · disk full -> E_DISK_FULL

@dataclass(frozen=True)
class FrameCall:
    src_name: str
    dst_name: str
    t_ms: int
    long_side: int
    dynamic_range: str | None

# FakeMediaTools: frames: list[FrameCall]; frame_limit_ms: int | None = None (attribute)
# extract_frame validates like frame_args, records the call, returns False when t_ms >= frame_limit_ms,
# otherwise copies <media_root>/cover.jpg to dst and returns True
```

### C5. Cache store, output folder, frame names (`core/sharp_store.py` new, `core/files.py`, `core/frames.py`, `core/storyboard.py`, T5)
```python
# core/sharp_store.py
FOLDER = "sharp"
INDEX = "index.json"
TMP_PREFIX = "sharp.tmp-"
OLD_PREFIX = "sharp.old-"
ORIGINS = ("manual", "auto")

def read_sharp(cache_root: Path, video_id: str) -> dict | None
    # {"origin", "intervalMs": int|None, "frames": [{"index", "tMs", "file"}], "createdAt"}; missing/corrupt/
    # a frame file missing/bad id = None
def prepare_sharp(cache_root: Path, video_id: str, job_id: str, frames: Sequence[tuple[int, Path]], *,
                  origin: str, interval_ms: int | None, created_at: str) -> Path
    # copies into <cache>/<id>/sharp.tmp-<job_id>/f_0000.jpg … + index.json; returns that folder
    # ValueError: no frames, origin not in ORIGINS, job_id not [A-Za-z0-9-]{1,64}, bad video id
def commit_sharp(cache_root: Path, video_id: str, staged: Path) -> dict
    # sharp/ -> sharp.old-<job>/ ; staged -> sharp/ ; delete old · renames retry up to 2 s · returns the index
    # failure -> YtError("E_UNKNOWN") with the previous set back in place and staged removed
def discard_sharp(staged: Path) -> None           # rmtree, ignores errors
def sweep_sharp_leftovers(cache_root: Path) -> int
    # every <cache>/<id>/: sharp.tmp-* removed; sharp.old-* restored to sharp/ when sharp/ is missing, else removed

# core/files.py
SHARP_DIR_SUFFIX = " - ภาพคม"
PARTIAL_MARKER = ".yttoolkit-partial"
def plan_sharp_dir(root: Path, title: str, video_id: str, group: str | None = None) -> Path
    # <clip folder of plan_output>/<stem> - ภาพคม ; stem shortened so "<folder> (99)/frame_000-00-00_200.jpg" <= 240
def move_files_into_dir(items: Sequence[tuple[Path, str]], planned: Path) -> Path
    # reserve planned, "planned (2)" … "(99)" with an exclusive mkdir, write PARTIAL_MARKER, move (or copy across
    # drives) every (src, name), remove the marker; any failure or cancel removes the folder; OSError -> YtError
    # E_DISK_FULL / E_OUTPUT_NOT_WRITABLE

# core/frames.py
def frame_file_names(times_ms: Sequence[int]) -> list[str]   # frame_HH-MM-SS.jpg, _2, _3 … (frames_zip uses it)
def contact_sheet(frames, title, duration_s, columns=5, *, missing_code: str = "E_NO_STORYBOARD") -> bytes
def frames_zip(frames, *, missing_code: str = "E_NO_STORYBOARD") -> bytes

# core/storyboard.py
def frame_file_name(index: int) -> str   # "f_0000.jpg" (was the private _file_name)
```

### C6. API (`api/jobs.py`, `api/videos.py`, T7)
- `POST /jobs` kind `frames_sharp`: `FramesSharpParams(_Grouped)` with `intervalS: StrictInt | None = Field(None, ge=1, le=3600)`; stored `model_dump(exclude_none=True)` (`{}` or `{"intervalS": N}` plus `folder`). Unknown keys → 422 `E_BAD_REQUEST`.
- `contact_sheet.source` / `frames_zip.source`: `Literal["fast", "sharp"] = "fast"`.
- With a stored probe (`VideoService.peek_cached`): `frames_sharp` on a live clip or `durationS <= 0` → 422 `E_BAD_REQUEST` (`detail` starts with the video id). No stored probe = accepted (the handler re-checks).
- `frames_sharp` without ffmpeg → 409 `E_FFMPEG_MISSING` (through `FFMPEG_KINDS`).
- `GET /videos/{id}/sharp` → 200 `{"origin", "intervalMs", "frames": [{"index", "tMs", "url"}]}`, `url = /api/cache/{id}/sharp/{file}?v=<index.json mtime_ns>`; no set → 404 `E_NO_SHARP_FRAMES`; bad id → 422 `E_INVALID_INPUT`.
- `GET /cache/{id}/sharp/f_NNNN.jpg` is `immutable` like storyboard frames; `?download=1` names it `frame_HH-MM-SS.jpg` from the sharp index.
- `GET /jobs/{id}/outputs/{i}` of a folder output → 404; `POST …/reveal` of a folder output → `ctx.open_folder or ctx.plat.open_folder` on the folder (missing folder → 404).
- `STATUS_BY_CODE["E_NO_SHARP_FRAMES"] = 404`.

### C7. Manual job and sharp sources (`core/handlers.py`, T8)
- `build_handlers` gains `"frames_sharp"`.
- Stages: `probing` → `downloading_video` (from the downloader hooks, with %/speed/ETA) → `extracting_frames:i/n` (progress `(i-1)/n` while working on frame i) → `writing`.
- Live clip → `YtError("E_LIVE_NOT_READY")`; `durationS <= 0` → `YtError("E_UNKNOWN", "duration unknown")`; bad `intervalS` in stored params → `YtError("E_UNKNOWN")`.
- Disk check: `need = ceil(size × 1.1) + n × 400_000` against output root and workdir (`SHARP_SIZE_FACTOR = 1.1`, `SHARP_FRAME_BYTES = 400_000`); unknown size = no check.
- Frames: workdir `frames/0001.jpg …`; `False` from `extract_frame` = dropped; zero frames → `YtError("E_UNKNOWN", "no frames extracted")`; the downloaded video is deleted right after extraction.
- Finish (no cancel check after the last one): `prepare_sharp` → `move_files_into_dir(<frames named by frame_file_names>, plan_sharp_dir(...))` → `commit_sharp`; any failure discards the staged cache folder and deletes the new output folder. `แหล่งที่มา.txt` goes to the clip folder.
- Result: `JobResult(outputs=(OutputFile(root, rel_of_folder, total_bytes, "folder", files=n),), notes, title)`; notes `SHARP_INTERVAL_RAISED:<N2>` (plan raised), `SHARP_LOW_RES:<h>` (picked short side < 720).
- `contact_sheet` / `frames_zip` with `source: "sharp"`: frames from `read_sharp` (missing → `YtError("E_NO_SHARP_FRAMES")`), stages `probing` → `converting` → `writing`, `missing_code="E_NO_SHARP_FRAMES"`, same output names as fast.

### C8. Automatic step (`core/handlers.py`, `lifecycle.py`, T14)
- `HandlerDeps.auto_sharp: Callable[[], bool] = lambda: False`; `lifecycle.open_services` passes `auto_sharp=lambda: bool(settings.get().get("autoSharpFrames", True))`.
- Runs after `_video`'s `_finish` only when: `deps.auto_sharp()`, no `range`, no `sponsorblock`, `splitChapters` false, `result.media` known with short side ≥ 720 and `hdr is False`, `deps.media.available()`, `durationS > 0`, and the clip has no manual set (`read_sharp(...)` is `None` or its origin is `"auto"`).
- Plan: `plan_sharp(durationS, interval_s=None, fast_times=fast_times(raw))`; stage `sharp_frames:i/n`; frames read from the final output file; cache only (`origin="auto"`, `intervalMs` = `interval_s * 1000` or `None`).
- Every `Exception` (including `JobCancelled` and `YtError`) is logged as `งาน <id> ข้ามภาพคมอัตโนมัติ (<type>)`, the staged folder discarded, and the `video` result returned unchanged (no note).

### C9. Startup sweep (`lifecycle.py`, T9)
- `open_services` calls `sweep_sharp_leftovers(paths.cache)` right after `purge_cache_once` (errors logged, never raised).
- `sweep_interrupted_outputs` also removes, in each clip folder of an interrupted job, child folders whose name fullmatches `<prefix (may be shortened)> - ภาพคม[ (2..99)]`, that contain `PARTIAL_MARKER` and are not a done job's output (`shutil.rmtree`, counted as 1 each).

### C10. Thai strings (`web/src/i18n/th.ts`, T6 writes them verbatim; nobody else edits `th.ts`)
```ts
frames: {
  // changed
  noStoryboard: 'คลิปนี้ไม่มีภาพตัวอย่างแบบเร็ว กด "ขอภาพคม" แทนได้',
  // removed: availableLater
  // kept: requestSharp: "ขอภาพคม" (button text and dialog title)
  setLabel: "ชุดภาพเฟรม",
  setFast: "ภาพเร็ว",
  setSharp: "ภาพคม",
},
sharp: {
  busy: "กำลังดึงภาพคม…",
  liveDisabled: "คลิปสดยังขอภาพคมไม่ได้",
  sameTimes: "เวลาเดียวกับภาพเร็ว",
  sameTimesDetail: "ทุก ~{interval} วินาที · {count} ภาพ",
  customPrefix: "ตั้งเอง ทุก",
  customUnit: "วินาที",
  customCount: "· {count} ภาพ",
  intervalError: "ใส่เลขวินาทีเต็ม 1-3600",
  size: "ต้องโหลดวิดีโอชั่วคราวราว {size} (ลบทิ้งเมื่อเสร็จ)",
  sizeUnknown: "ต้องโหลดวิดีโอชั่วคราว ไม่ทราบขนาดล่วงหน้า (ลบทิ้งเมื่อเสร็จ)",
  wide: "ภาพกว้าง 1280 px",
  tall: "ภาพสูง 1280 px",
  lowRes: "คลิปนี้มีภาพสูงสุด {h}p ภาพจะเล็กกว่าปกติ",
  overLimit: "ทุก {N} วินาทีจะได้ {count} ภาพ เกินที่ดึงได้ 200 ภาพ จะใช้ทุก {N2} วินาทีแทน",
  replaceWarning: "ภาพคมชุดเดิมในแอพจะถูกแทนด้วยชุดใหม่ (ไฟล์ในโฟลเดอร์ไม่หาย)",
  cancel: "ยกเลิก",
  start: "เริ่มดึงภาพคม",
},
queue: {
  // additions inside the existing object
  extracting: "กำลังดึงภาพ {i}/{n}",
  autoSharp: "กำลังทำภาพคม {i}/{n}",
  sharpTitle: " · ภาพคม",
  sharpTitleCount: " · ภาพคม {n} ภาพ",
},
general: {
  // additions
  autoSharpFrames: "ทำภาพคมอัตโนมัติตอนโหลดวิดีโอ",
  autoSharpFramesHint: "ใช้ไฟล์ที่โหลดมาแล้ว ไม่ต้องโหลดเพิ่ม ใช้เวลาเพิ่มราว 10-40 วินาทีต่อคลิป",
},
```
Labels built from these: radio 2 = `ตั้งเอง ทุก [N] วินาที · {count} ภาพ` (`customPrefix` + number field + `customUnit` + `customCount`); the dialog title and the trigger use `th.frames.requestSharp`; the enqueue toast reuses `th.queue.added`.

### C11. Web types, queries and components (T6, T10, T11)
```ts
// web/src/lib/types.ts (T6)
export type JobStage = … | `extracting_frames:${number}/${number}` | `sharp_frames:${number}/${number}`
export type JobOutput = { index: number; name: string; sizeBytes: number; files?: number }   // files = folder output
export type FrameSource = "fast" | "sharp"
export type ContactSheetJobParams = GroupFolder & { source: FrameSource; columns: 5 }
export type FramesZipJobParams = GroupFolder & { source: FrameSource }
export type FramesSharpJobParams = GroupFolder & { intervalS?: number }
export type JobParams = … | FramesSharpJobParams
export type NewJob = { videoId: string; kind: JobKind; params: JobParams; title?: string }
export type SharpSet = { origin: "manual" | "auto"; intervalMs: number | null; frames: StoryboardFrame[] }
// Settings gains: autoSharpFrames: boolean

// web/src/pages/video/queries.ts (T10)
export function sharpQuery(videoId: string, enabled: boolean)   // key ["sharp", videoId]; 404 -> null
// web/src/pages/video/frame-set.ts (T10)
export function frameSetShown(o: { hasFast: boolean; hasSharp: boolean; chosen: FrameSource | null }): FrameSource
// web/src/lib/events.ts (T10)
export function sharpRefreshTarget(before: Job | undefined, after: Job): string | null   // videoId to refresh
// web/src/pages/video/frames.tsx (T10): FramesSection({ videoId, enabled, mostReplayed, video })
// web/src/pages/video/sharp-dialog.tsx (T11)
export function SharpRequestButton(props: {
  videoId: string
  video: VideoInfo | undefined
  fast: SharpFast | null          // null = no fast set (no storyboard)
  hasSharp: boolean
  variant?: "secondary" | "outline"   // toolbar = secondary (default), empty state = outline
}): JSX.Element
// web/src/pages/video/sharp-request.ts (T11)
export function sharpJobBusy(jobs: readonly Job[] | undefined, videoId: string): boolean
export type SharpBlock = "loading" | "live" | null
export function sharpBlock(video: Pick<VideoInfo, "isLive" | "durationS"> | undefined): SharpBlock
```
`FramesSection` gains the `video` prop in T15 (`tabs.tsx` passes it); T10 leaves its props unchanged.

### C12. Queue text (`web/src/components/queue/job-text.ts`, `job-row.tsx`, T13)
```ts
export function stageText(stage: JobStage): string   // "extracting_frames:3/40" -> "กำลังดึงภาพ 3/40"; "sharp_frames:2/9" -> "กำลังทำภาพคม 2/9"
export function sharpCount(job: Partial<Pick<Job, "stage" | "outputs">>): number | null   // outputs[0].files, else n of extracting_frames
export const jobTitle: (job: Pick<Job, "title" | "videoId"> & Partial<Pick<Job, "kind" | "params" | "stage" | "outputs">>) => string
// frames_sharp: title + " · ภาพคม {n} ภาพ" | " · ภาพคม"; other kinds unchanged
// DoneRow: an output with `files` has no "ดาวน์โหลด" link
```

### C13. E2E ids and files
Chromium specs (mocked enqueue, mocked `GET /sharp` and its images via `page.route`): `web/e2e/sharp-grid.spec.ts` (T10), `web/e2e/sharp-dialog.spec.ts` (T15), extra tests in `web/e2e/settings-general.spec.ts` (T12) and updates in `web/e2e/video.spec.ts` (T15). Queue spec (real fake backend): `web/e2e/queue-sharp.spec.ts` (T16) using only `SHARPCLIP01` and `AUTOSHARP01`.

---

## File structure

**Backend (new):** `src/yttoolkit/core/sharp.py` (T2) plan maths · `src/yttoolkit/core/sharp_store.py` (T5) cache set.
**Backend (modified):** `core/jobs.py`, `core/settings.py`, `core/yterrors.py` (T1) · `core/download.py`, `core/extractor.py` (T3) · `core/media.py` (T4) · `core/files.py`, `core/frames.py`, `core/storyboard.py` (T5) · `api/jobs.py`, `api/videos.py` (T7) · `core/handlers.py` (T8, T14) · `lifecycle.py` (T9, T14).
**Fixtures:** `tests/fixtures/sharp/plan-cases.json` (T2, new) · `tests/fixtures/downloads/behaviors.json`, `tests/fixtures/README.md` (T3).
**Tests (new):** `tests/unit/test_sharp_plan.py` (T2), `tests/integration/test_sharp_ffmpeg.py` (T4), `tests/unit/test_sharp_store.py` (T5), `tests/unit/test_handlers_sharp.py`, `tests/integration/test_sharp_job_ffmpeg.py` (T8), `tests/unit/test_handlers_auto_sharp.py` (T14), `tests/network/test_sharp_network.py` (T17).
**Tests (modified):** `test_jobs_store.py`, `test_settings.py`, `test_yterrors.py` (T1, T17) · `test_download_choice.py`, `test_extractor_download.py` (T3) · `test_media_args.py` (T4) · `test_files.py`, `test_frames.py` (T5) · `tests/api/test_jobs_api.py`, `tests/api/test_videos_api.py` (T7) · `test_lifecycle.py` (T9, T14).
**Web (new):** `web/src/lib/sharp-frames.ts` + test (T2) · `web/src/pages/video/frame-set.ts` + test (T10) · `web/src/components/ui/radio-group.tsx`, `web/src/pages/video/sharp-dialog.tsx`, `web/src/pages/video/sharp-request.ts` + test (T11) · e2e specs (C13).
**Web (modified):** `th.ts`, `types.ts`, `frames.tsx` (tooltip), four test fixtures (T6) · `frames.tsx`, `queries.ts` (+test), `lib/events.ts` (+test) (T10) · `general-panel.tsx`, `general-form.ts` (+test) (T12) · `job-text.ts` (+test), `job-row.tsx` (T13) · `frames.tsx`, `tabs.tsx`, `web/e2e/video.spec.ts` (T15).
**Test helper (new):** `tests/helpers_sharp.py` (T8, imported by T8 and T14 tests like `helpers_ffmpeg.py`).
**Docs (modified, T17):** `PRD.md`, `BRD.md`, `docs/acceptance.md`, `docs/m4-followups.md`, `docs/m5a-followups.md`, `tests/network_videos.toml`.

---

## Wave 1

### Task 1: Notes with a value, count stages, folder outputs, `autoSharpFrames`, error copy

**Files:**
- Modify: `src/yttoolkit/core/jobs.py` (stage regex + `count_stage`, `is_stage`, `NOTES`, `NOTE_VALUES`, `valued_note`, `note_api`, `OutputFile.files`, `_dump_outputs`, `_load_outputs`, `Job.to_api`)
- Modify: `src/yttoolkit/core/settings.py` (`_validate_bool`, `_VALIDATORS`, defaults)
- Modify: `src/yttoolkit/core/yterrors.py` (`E_NO_STORYBOARD`, `E_NO_SHARP_FRAMES`)
- Modify: `tests/unit/test_jobs_store.py`, `tests/unit/test_settings.py`, `tests/unit/test_yterrors.py`

**Interfaces:**
- Consumes: M5-A `STAGES`, `SPLIT_STAGE`, `NOTES`, `OutputFile`, `SettingsStore`.
- Produces: C1 exactly.

- [ ] **Step 1: Write the failing tests**

In `tests/unit/test_jobs_store.py` extend the import line to:
```python
from yttoolkit.core.jobs import NOTES, InvalidTransition, JobStore, NewJob, OutputFile, count_stage, is_stage, note_api, split_stage, uuid7, valued_note
```
and append:
```python
def test_m5b_count_stages_are_stored(store):
    (job,) = add(store)
    store.transition(job.id, "running")
    for stage in (count_stage("extracting_frames", 3, 120), count_stage("sharp_frames", 1, 1)):
        assert store.update(job.id, stage=stage).stage == stage
    for bad in ("extracting_frames:0x/3", "sharp_frames:", "extracting:1/2", "sharp_frames:1/2/3"):
        with pytest.raises(ValueError):
            store.update(job.id, stage=bad)


def test_count_stage_bounds():
    assert count_stage("extracting_frames", 1, 1) == "extracting_frames:1/1"
    assert is_stage("sharp_frames:2/9") and is_stage("extracting_frames:200/200") and is_stage("splitting:1/2")
    for args in (("extracting_frames", 0, 3), ("extracting_frames", 4, 3), ("sharp_frames", 1, 10_000), ("cutting", 1, 2)):
        with pytest.raises(ValueError):
            count_stage(*args)


def test_valued_notes_fill_their_message():
    assert NOTES["SHARP_LOW_RES"] == "คลิปนี้มีภาพสูงสุด {h}p ภาพจึงเล็กกว่าปกติ"
    assert NOTES["SHARP_INTERVAL_RAISED"] == "ปรับเป็นทุก {n} วินาทีเพื่อไม่ให้เกิน 200 ภาพ"
    assert valued_note("SHARP_LOW_RES", 480) == "SHARP_LOW_RES:480"
    assert note_api("SHARP_LOW_RES:480") == {"code": "SHARP_LOW_RES", "message": "คลิปนี้มีภาพสูงสุด 480p ภาพจึงเล็กกว่าปกติ"}
    assert note_api("SHARP_INTERVAL_RAISED:4") == {
        "code": "SHARP_INTERVAL_RAISED", "message": "ปรับเป็นทุก 4 วินาทีเพื่อไม่ให้เกิน 200 ภาพ"}
    assert note_api("NO_SUBTITLES") == {"code": "NO_SUBTITLES", "message": "คลิปนี้ไม่มีซับ"}
    for bad in ("SHARP_LOW_RES", "SHARP_LOW_RES:x", "SHARP_LOW_RES:-1", "NO_SUBTITLES:3", "NOPE", "NOPE:1"):
        assert note_api(bad) is None
    for args in (("NO_SUBTITLES", 1), ("SHARP_LOW_RES", -1)):
        with pytest.raises(ValueError):
            valued_note(*args)


def test_to_api_fills_valued_notes_and_lists_folder_outputs(store):
    (job,) = add(store, kind="frames_sharp")
    store.transition(job.id, "running")
    folder = OutputFile("C:/out", "คลิป [aqz-KE-bpKQ]/คลิป - ภาพคม", 1234, "folder", files=12)
    done = store.transition(job.id, "done", outputs=(folder,), notes=(valued_note("SHARP_LOW_RES", 360), "BROKEN:1"))
    api = done.to_api()
    assert api["outputs"] == [{"index": 0, "name": "คลิป - ภาพคม", "sizeBytes": 1234, "files": 12}]
    assert api["notes"] == [{"code": "SHARP_LOW_RES", "message": "คลิปนี้มีภาพสูงสุด 360p ภาพจึงเล็กกว่าปกติ"}]
    assert store.get(job.id).outputs == (folder,)


def test_plain_outputs_have_no_files_key(store):
    (job,) = add(store)
    store.transition(job.id, "running")
    plain = OutputFile("C:/out", "a/b.mp4", 9, "video")
    done = store.transition(job.id, "done", outputs=(plain,))
    assert store.get(job.id).outputs[0].files is None
    assert "files" not in done.to_api()["outputs"][0]
```
In `tests/unit/test_settings.py`: add `"autoSharpFrames": True,` after the `"sponsorblockDefault"` line of the dict in `test_defaults_match_the_c5_table`; add these rows to the `bad` list of `test_invalid_patch_is_rejected_and_changes_nothing`:
```python
        {"autoSharpFrames": 1},
        {"autoSharpFrames": "true"},
        {"autoSharpFrames": None},
```
and append:
```python
def test_auto_sharp_frames_can_be_switched_off_and_on(store):
    assert store.patch({"autoSharpFrames": False})["autoSharpFrames"] is False
    assert store.patch({"autoSharpFrames": True})["autoSharpFrames"] is True
```
In `tests/unit/test_yterrors.py`: set `PRD_PENDING: set[str] = {"E_NO_SHARP_FRAMES"}` (T17 adds the PRD row and empties the set again), replace the `E_NO_STORYBOARD` assertion inside `test_messages_are_verbatim_prd_copy` with
```python
    assert MESSAGES["E_NO_STORYBOARD"] == 'คลิปนี้ไม่มีภาพตัวอย่างแบบเร็ว กด "ขอภาพคม" แทนได้'
```
and append:
```python
def test_m5b_messages_are_verbatim_spec_copy() -> None:
    assert MESSAGES["E_NO_SHARP_FRAMES"] == 'ภาพคมของคลิปนี้ถูกล้างไปแล้ว กด "ขอภาพคม" ใหม่ได้'
```

- [ ] **Step 2: Run them, expect FAIL**

Run: `uv run pytest tests/unit/test_jobs_store.py tests/unit/test_settings.py tests/unit/test_yterrors.py -q -W error -p no:cacheprovider`
Expected: FAIL (`ImportError: cannot import name 'count_stage'`, `autoSharpFrames` missing from the defaults, old `E_NO_STORYBOARD` text, `E_NO_SHARP_FRAMES` KeyError).

- [ ] **Step 3: Implement `core/jobs.py`**

After the `SPLIT_STAGE` line add:
```python
# M5 รอบ B: "extracting_frames:<i>/<n>" = กำลังดึงภาพคม (งาน frames_sharp) · "sharp_frames:<i>/<n>" = ภาพคมอัตโนมัติหลังโหลดวิดีโอ
COUNT_STAGES = ("extracting_frames", "sharp_frames")
COUNT_STAGE = re.compile(r"(extracting_frames|sharp_frames):(\d{1,4})/(\d{1,4})")
```
Add to `NOTES` (keep every existing entry):
```python
    "SHARP_LOW_RES": "คลิปนี้มีภาพสูงสุด {h}p ภาพจึงเล็กกว่าปกติ",
    "SHARP_INTERVAL_RAISED": "ปรับเป็นทุก {n} วินาทีเพื่อไม่ให้เกิน 200 ภาพ",
```
After `NOTES`:
```python
# โน้ตที่ข้อความมีค่าเติม (M5 รอบ B) เก็บเป็น "<รหัส>:<ตัวเลข>" เช่น "SHARP_LOW_RES:480" ค่า = ชื่อช่องในข้อความ
NOTE_VALUES = {"SHARP_LOW_RES": "h", "SHARP_INTERVAL_RAISED": "n"}
```
Replace `split_stage`/`is_stage` block with:
```python
def split_stage(index: int, total: int) -> str:
    """ขั้นของการแยกไฟล์ตาม chapter: "splitting:<i>/<n>" (1 <= i <= n <= 9999)"""
    if not 1 <= index <= total <= 9999:
        raise ValueError(f"split stage out of range: {index}/{total}")
    return f"splitting:{index}/{total}"


def count_stage(name: str, index: int, total: int) -> str:
    """ขั้นที่นับทีละภาพของภาพคม: "extracting_frames:<i>/<n>" หรือ "sharp_frames:<i>/<n>" (1 <= i <= n <= 9999)"""
    if name not in COUNT_STAGES or not 1 <= index <= total <= 9999:
        raise ValueError(f"count stage out of range: {name}:{index}/{total}")
    return f"{name}:{index}/{total}"


def is_stage(value: str) -> bool:
    return (
        value in STAGES
        or SPLIT_STAGE.fullmatch(value) is not None
        or COUNT_STAGE.fullmatch(value) is not None
    )


def valued_note(code: str, value: int) -> str:
    """โน้ตที่มีค่าเติม: "<รหัส>:<ค่า>" (รหัสต้องอยู่ใน NOTE_VALUES ค่าเป็นจำนวนเต็มไม่ติดลบ)"""
    if code not in NOTE_VALUES or isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"bad valued note: {code}:{value!r}")
    return f"{code}:{value}"


def note_api(raw: str) -> dict | None:
    """โน้ตที่เก็บไว้ -> {"code", "message"} ของ API (เติมค่าให้โน้ตที่มีค่า) รหัสไม่รู้จักหรือรูปผิด = None (ไม่แสดง)"""
    code, sep, value = raw.partition(":")
    template = NOTES.get(code)
    if template is None:
        return None
    field = NOTE_VALUES.get(code)
    if field is None:
        return None if sep else {"code": code, "message": template}
    if not sep or not value.isdigit():
        return None
    return {"code": code, "message": template.format(**{field: int(value)})}
```
`OutputFile` becomes:
```python
@dataclass(frozen=True)
class OutputFile:
    root: str        # โฟลเดอร์ผลลัพธ์ (absolute) ตอนทำงาน ไม่ส่งให้เบราว์เซอร์
    rel: str         # "<folder>/<file>" ใช้ "/" คั่น (kind "folder" = ตัวโฟลเดอร์)
    size_bytes: int
    kind: str        # "video" | "audio" | "subtitle" | "note" | "image" | "archive" | "folder" (M5 รอบ B ภาพคม)
    files: int | None = None  # kind "folder": จำนวนไฟล์ในโฟลเดอร์
```
In `Job.to_api` replace the `notes = …` line and the outputs block with:
```python
        notes = [note for note in (note_api(raw) for raw in self.notes) if note is not None]
        if notes:
            data["notes"] = notes
        if self.outputs:
            data["outputs"] = [_output_api(i, out) for i, out in enumerate(self.outputs)]
        return data
```
and add above `Handler = …`:
```python
def _output_api(index: int, out: OutputFile) -> dict:
    item: dict[str, Any] = {"index": index, "name": PurePosixPath(out.rel).name, "sizeBytes": out.size_bytes}
    if out.files is not None:
        item["files"] = out.files
    return item
```
Replace `_dump_outputs` / `_load_outputs`:
```python
def _dump_outputs(outputs: Sequence[OutputFile] | None) -> str | None:
    if not outputs:
        return None
    rows: list[dict[str, Any]] = []
    for o in outputs:
        row: dict[str, Any] = {"root": o.root, "rel": o.rel, "sizeBytes": o.size_bytes, "kind": o.kind}
        if o.files is not None:
            row["files"] = o.files
        rows.append(row)
    return json.dumps(rows, ensure_ascii=False)


def _load_outputs(text: str | None) -> tuple[OutputFile, ...]:
    if not text:
        return ()
    return tuple(
        OutputFile(
            str(o["root"]), str(o["rel"]), int(o["sizeBytes"]), str(o["kind"]),
            int(o["files"]) if o.get("files") is not None else None,
        )
        for o in json.loads(text)
    )  # fmt: skip
```

- [ ] **Step 4: Implement `core/settings.py` and `core/yterrors.py`**

`core/settings.py`, after `_validate_last_used`:
```python
def _validate_bool(key: str, value: Any) -> bool:
    # ชนิดต้องเป็น bool จริง: 1 / "true" ไม่นับ (แบบเดียวกับ _one_of)
    if type(value) is not bool:
        raise _bad(key, "must be true or false")
    return value
```
Add to `_VALIDATORS`: `"autoSharpFrames": lambda v: _validate_bool("autoSharpFrames", v),` and to the defaults dict, right after `"sponsorblockDefault"`: `"autoSharpFrames": True,  # M5 รอบ B D6: ทำภาพคมอัตโนมัติหลังโหลดวิดีโอ`.

`core/yterrors.py`: replace the `E_NO_STORYBOARD` entry and add the new code after `E_NO_SUBTITLES`:
```python
    # M5 รอบ B มีโหมดคมแล้ว (BRD #33): ข้อความชวนไปกด "ขอภาพคม"
    "E_NO_STORYBOARD": 'คลิปนี้ไม่มีภาพตัวอย่างแบบเร็ว กด "ขอภาพคม" แทนได้',
    "E_NO_SUBTITLES": "คลิปนี้ไม่มีซับ",
    # ชุดภาพคมใน cache หายไป (ล้าง cache) ก่อนงาน contact sheet / zip แบบภาพคมได้เริ่ม
    "E_NO_SHARP_FRAMES": 'ภาพคมของคลิปนี้ถูกล้างไปแล้ว กด "ขอภาพคม" ใหม่ได้',
```

- [ ] **Step 5: Run the tests, expect PASS** — same command as Step 2, then `uv run pytest -q -W error -p no:cacheprovider` (the existing `test_frames.py` / `test_handlers.py` assertions compare `YtError.code`, not the message, so they stay green).

- [ ] **Step 6: Commit**
```bash
git add src/yttoolkit/core/jobs.py src/yttoolkit/core/settings.py src/yttoolkit/core/yterrors.py tests/unit/test_jobs_store.py tests/unit/test_settings.py tests/unit/test_yterrors.py
git commit -F- <<'EOF'
feat(jobs): M5-B count stages, notes with a value, folder outputs, autoSharpFrames, sharp error copy

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
EOF
```

### Task 2: Timecode plan in Python and TypeScript (golden parity) and the dialog maths

**Files:**
- Create: `src/yttoolkit/core/sharp.py`, `tests/unit/test_sharp_plan.py`
- Create: `tests/fixtures/sharp/plan-cases.json`
- Create: `web/src/lib/sharp-frames.ts`, `web/src/lib/sharp-frames.test.ts`

**Interfaces:**
- Consumes: `storyboard.pick_storyboard`, `storyboard.plan_frames`; web `resolution` (`web/src/lib/download-options.ts:37`), `VideoFormat`.
- Produces: C2 exactly (Python and TS).

- [ ] **Step 1: Write the golden cases** — `tests/fixtures/sharp/plan-cases.json` (LF, 2-space indent):
```json
{
  "cases": [
    {"name": "same-times-as-is", "durationS": 635, "intervalS": null, "fast": {"stepMs": 4961, "count": 128},
     "expect": {"count": 128, "first": 0, "last": 630047, "intervalS": null, "raised": false}},
    {"name": "same-times-exactly-200", "durationS": 1000, "intervalS": null, "fast": {"stepMs": 5000, "count": 200},
     "expect": {"count": 200, "first": 0, "last": 995000, "intervalS": null, "raised": false}},
    {"name": "same-times-over-200", "durationS": 3600, "intervalS": null, "fast": {"stepMs": 10000, "count": 360},
     "expect": {"count": 200, "first": 0, "last": 3582000, "intervalS": 18, "raised": true}},
    {"name": "custom-7", "durationS": 635, "intervalS": 7, "fast": null,
     "expect": {"count": 91, "first": 0, "last": 630000, "intervalS": 7, "raised": false}},
    {"name": "custom-2-raised-to-4", "durationS": 635, "intervalS": 2, "fast": {"stepMs": 4961, "count": 128},
     "expect": {"count": 159, "first": 0, "last": 632000, "intervalS": 4, "raised": true}},
    {"name": "custom-exactly-200", "durationS": 400, "intervalS": 2, "fast": null,
     "expect": {"count": 200, "first": 0, "last": 398000, "intervalS": 2, "raised": false}},
    {"name": "custom-201-raised-to-3", "durationS": 401, "intervalS": 2, "fast": null,
     "expect": {"count": 134, "first": 0, "last": 399000, "intervalS": 3, "raised": true}},
    {"name": "no-storyboard-19s", "durationS": 19, "intervalS": null, "fast": null,
     "expect": {"count": 19, "first": 0, "last": 18000, "intervalS": 1, "raised": false,
                "times": [0, 1000, 2000, 3000, 4000, 5000, 6000, 7000, 8000, 9000, 10000, 11000, 12000, 13000, 14000, 15000, 16000, 17000, 18000]}},
    {"name": "no-storyboard-10h", "durationS": 36000, "intervalS": null, "fast": null,
     "expect": {"count": 100, "first": 0, "last": 35640000, "intervalS": 360, "raised": false}},
    {"name": "near-the-end", "durationS": 10, "intervalS": 3, "fast": null,
     "expect": {"count": 4, "first": 0, "last": 9000, "intervalS": 3, "raised": false, "times": [0, 3000, 6000, 9000]}},
    {"name": "interval-longer-than-clip", "durationS": 5, "intervalS": 3600, "fast": null,
     "expect": {"count": 1, "first": 0, "last": 0, "intervalS": 3600, "raised": false, "times": [0]}},
    {"name": "one-second-clip", "durationS": 1, "intervalS": null, "fast": null,
     "expect": {"count": 1, "first": 0, "last": 0, "intervalS": 1, "raised": false, "times": [0]}},
    {"name": "every-second-of-a-long-clip", "durationS": 100000, "intervalS": 1, "fast": null,
     "expect": {"count": 200, "first": 0, "last": 99500000, "intervalS": 500, "raised": true}}
  ]
}
```

- [ ] **Step 2: Write the failing Python test** — `tests/unit/test_sharp_plan.py`:
```python
"""แผนเวลาภาพคม (M5 รอบ B spec 3.2) ฝั่ง Python · เคสร่วมกับ web/src/lib/sharp-frames.test.ts ห้ามแก้ fixture ให้เทสผ่าน"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from yttoolkit.core.extractor import FakeExtractor
from yttoolkit.core.sharp import (
    MAX_SHARP_FRAMES,
    SharpPlan,
    custom_times,
    default_interval_s,
    fast_times,
    plan_sharp,
    raised_interval_s,
)
from yttoolkit.core.storyboard import build

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
CASES = json.loads((FIXTURES / "sharp" / "plan-cases.json").read_text(encoding="utf-8"))["cases"]


@pytest.mark.parametrize("case", CASES, ids=[c["name"] for c in CASES])
def test_golden_plan_cases(case: dict) -> None:
    fast = case["fast"]
    times = [i * fast["stepMs"] for i in range(fast["count"])] if fast else None
    plan = plan_sharp(case["durationS"], interval_s=case["intervalS"], fast_times=times)
    want = case["expect"]
    assert len(plan.times_ms) == want["count"] <= MAX_SHARP_FRAMES
    assert plan.times_ms[0] == want["first"] and plan.times_ms[-1] == want["last"]
    assert plan.interval_s == want["intervalS"] and plan.raised is want["raised"]
    if "times" in want:
        assert list(plan.times_ms) == want["times"]
    assert list(plan.times_ms) == sorted(set(plan.times_ms))


def test_helpers() -> None:
    assert default_interval_s(19) == 1 and default_interval_s(635) == 7 and default_interval_s(36000) == 360
    assert raised_interval_s(635) == 4 and raised_interval_s(200) == 1
    assert custom_times(3, 10) == [0, 3000, 6000, 9000]
    assert plan_sharp(19, interval_s=None, fast_times=None) == SharpPlan(tuple(range(0, 19_000, 1000)), 1, False)


@pytest.mark.parametrize(
    ("duration_s", "interval_s", "fast"),
    [(0, None, None), (-5, 2, None), (10, 0, None), (10, 3601, None), (10, True, None), (10, None, [])],
)
def test_bad_input_is_a_value_error(duration_s, interval_s, fast) -> None:
    with pytest.raises(ValueError):
        plan_sharp(duration_s, interval_s=interval_s, fast_times=fast)


def test_fast_times_equal_the_storyboard_index_without_fetching(tmp_path: Path) -> None:
    fake = FakeExtractor(FIXTURES)
    raw = fake.probe("aqz-KE-bpKQ")
    planned = fast_times(raw)
    assert fake.calls == [("probe", "aqz-KE-bpKQ")]  # ไม่โหลดแผ่น storyboard
    index = build("aqz-KE-bpKQ", raw, tmp_path / "aqz-KE-bpKQ", fake.fetch)
    assert planned == [frame["tMs"] for frame in index["frames"]]
    assert len(planned) == 128


def test_fast_times_without_a_storyboard_is_none() -> None:
    assert fast_times(FakeExtractor(FIXTURES).probe("jNQXAC9IVRw")) is None
```

- [ ] **Step 3: Run it, expect FAIL** — `uv run pytest tests/unit/test_sharp_plan.py -q -W error -p no:cacheprovider` → `ModuleNotFoundError: No module named 'yttoolkit.core.sharp'`.

- [ ] **Step 4: Implement `src/yttoolkit/core/sharp.py`**
```python
"""ภาพคม (M5 รอบ B spec 3.2): แผนเวลาของภาพ เป็นฟังก์ชันล้วน

ฝั่งเว็บมีชุดเดียวกันใน web/src/lib/sharp-frames.ts และทั้งสองฝั่งอ่านเคสใน tests/fixtures/sharp/plan-cases.json
ความยาวคลิปใช้ durationS ของ VideoInfo (วินาทีเต็ม) เหมือนหน้าเว็บ จำนวนภาพที่ dialog บอกจึงตรงกับงานจริง
เวลาของ "เวลาเดียวกับภาพเร็ว" คิดจากข้อมูลคลิปที่เก็บไว้ (storyboard.plan_frames) ไม่ต้องโหลดแผ่น storyboard
core/ ไม่ import api/ หรือ platform/
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from .storyboard import pick_storyboard, plan_frames

MAX_SHARP_FRAMES = 200  # AC-FRAME-04: ดึงได้ไม่เกิน 200 ภาพต่อครั้ง
MAX_INTERVAL_S = 3600  # ช่อง "ตั้งเอง ทุก N วินาที" รับ 1-3600


@dataclass(frozen=True)
class SharpPlan:
    times_ms: tuple[int, ...]
    interval_s: int | None  # None = เวลาเดียวกับภาพเร็ว
    raised: bool  # ปรับช่วงห่างขึ้นให้ไม่เกิน 200 ภาพ (โน้ต SHARP_INTERVAL_RAISED)


def _ceil_div(a: int, b: int) -> int:
    return -(-a // b)


def default_interval_s(duration_s: int) -> int:
    """ช่วงห่างเริ่มต้นเมื่อคลิปไม่มี storyboard: ราว 100 ภาพต่อคลิป อย่างน้อยทุก 1 วินาที"""
    return max(1, _ceil_div(duration_s, 100))


def raised_interval_s(duration_s: int) -> int:
    """ช่วงห่างที่รับประกันว่าไม่เกิน 200 ภาพ"""
    return _ceil_div(duration_s, MAX_SHARP_FRAMES)


def custom_times(interval_s: int, duration_s: int) -> list[int]:
    """t_i = i × N × 1000 ms ตราบที่ยังน้อยกว่าความยาวคลิป"""
    return list(range(0, duration_s * 1000, interval_s * 1000))


def _is_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _raised(duration_s: int) -> SharpPlan:
    n2 = raised_interval_s(duration_s)
    return SharpPlan(tuple(custom_times(n2, duration_s)), n2, True)


def plan_sharp(duration_s: int, *, interval_s: int | None, fast_times: Sequence[int] | None) -> SharpPlan:
    """เวลาของภาพคมตาม spec 3.2 (ValueError = ค่าที่ API ควรกันไว้แล้ว ผู้เรียกแปลงเป็น error ของงาน)"""
    if not _is_int(duration_s) or duration_s <= 0:
        raise ValueError(f"duration_s must be a positive int: {duration_s!r}")
    if interval_s is not None and (not _is_int(interval_s) or not 1 <= interval_s <= MAX_INTERVAL_S):
        raise ValueError(f"interval_s must be 1..{MAX_INTERVAL_S}: {interval_s!r}")
    if interval_s is None and fast_times is not None:
        times = tuple(int(t) for t in fast_times)
        if not times:
            raise ValueError("fast_times is empty")
        return SharpPlan(times, None, False) if len(times) <= MAX_SHARP_FRAMES else _raised(duration_s)
    if interval_s is None:
        n = default_interval_s(duration_s)
        return SharpPlan(tuple(custom_times(n, duration_s)), n, False)
    if _ceil_div(duration_s, interval_s) > MAX_SHARP_FRAMES:
        return _raised(duration_s)
    return SharpPlan(tuple(custom_times(interval_s, duration_s)), interval_s, False)


def fast_times(raw: Mapping[str, Any]) -> list[int] | None:
    """เวลาของภาพเร็ว (เท่ากับ tMs ใน index.json ของ storyboard ทุกตัว) จากข้อมูลคลิปที่ตัดแล้ว ไม่มี storyboard = None"""
    sb = pick_storyboard(dict(raw))
    if sb is None:
        return None
    times = [spec.t_ms for spec in plan_frames(sb, raw.get("duration"))]
    return times or None
```

- [ ] **Step 5: Run it, expect PASS** — same command as Step 3.

- [ ] **Step 6: Write the failing TS test** — `web/src/lib/sharp-frames.test.ts`:
```ts
/**
 * ภาพคม (M5 รอบ B): แผนเวลาต้องตรงกับ core/sharp.py ทุกเคส (อ่าน fixture ชุดเดียวกับ tests/unit/test_sharp_plan.py)
 * และตัวคำนวณของ dialog "ขอภาพคม" · ห้ามแก้ไฟล์ fixture เพื่อให้เทสนี้ผ่าน
 */
import { describe, expect, it } from "vitest"

import casesRaw from "../../../tests/fixtures/sharp/plan-cases.json?raw"

import {
  MAX_SHARP_FRAMES,
  customTimes,
  defaultCustomText,
  defaultIntervalS,
  parseIntervalText,
  planSharp,
  raisedIntervalS,
  sharpDialogModel,
  sharpEstimate,
  sharpKey,
  type SharpFast,
} from "./sharp-frames"
import type { VideoFormat } from "./types"

type PlanCase = {
  name: string
  durationS: number
  intervalS: number | null
  fast: { stepMs: number; count: number } | null
  expect: { count: number; first: number; last: number; intervalS: number | null; raised: boolean; times?: number[] }
}

const cases = (JSON.parse(casesRaw) as { cases: PlanCase[] }).cases
const steps = (stepMs: number, count: number) => Array.from({ length: count }, (_, i) => i * stepMs)

describe("planSharp (parity with core/sharp.py)", () => {
  it.each(cases.map((c) => [c.name, c] as const))("%s", (_, c) => {
    const plan = planSharp(c.durationS, { intervalS: c.intervalS, fastTimes: c.fast ? steps(c.fast.stepMs, c.fast.count) : null })
    expect(plan.timesMs).toHaveLength(c.expect.count)
    expect(plan.timesMs.length).toBeLessThanOrEqual(MAX_SHARP_FRAMES)
    expect(plan.timesMs[0]).toBe(c.expect.first)
    expect(plan.timesMs.at(-1)).toBe(c.expect.last)
    expect(plan.intervalS).toBe(c.expect.intervalS)
    expect(plan.raised).toBe(c.expect.raised)
    if (c.expect.times) expect(plan.timesMs).toEqual(c.expect.times)
  })

  it("helpers", () => {
    expect([defaultIntervalS(19), defaultIntervalS(635), defaultIntervalS(36000)]).toEqual([1, 7, 360])
    expect([raisedIntervalS(635), raisedIntervalS(200)]).toEqual([4, 1])
    expect(customTimes(3, 10)).toEqual([0, 3000, 6000, 9000])
    expect(sharpKey("aqz-KE-bpKQ")).toEqual(["sharp", "aqz-KE-bpKQ"])
  })

  it.each<[number, number | null, number[] | null]>([
    [0, null, null],
    [10, 0, null],
    [10, 3601, null],
    [10, 1.5, null],
    [10, null, []],
  ])("throws on bad input (%s, %s, %j)", (durationS, intervalS, fastTimes) => {
    expect(() => planSharp(durationS, { intervalS, fastTimes })).toThrow(RangeError)
  })
})

describe("parseIntervalText", () => {
  it.each<[string, number | null]>([
    ["7", 7],
    [" 60 ", 60],
    ["3600", 3600],
    ["1", 1],
    ["", null],
    ["0", null],
    ["3601", null],
    ["1.5", null],
    ["1e3", null],
    ["-2", null],
    ["๕", null],
  ])("%j -> %s", (text, want) => {
    expect(parseIntervalText(text)).toBe(want)
  })
})

const fmt = (over: Partial<VideoFormat> & Pick<VideoFormat, "formatId" | "height">): VideoFormat => ({
  fps: 30,
  vcodec: "avc1.4d401f",
  compat: true,
  ...over,
})

describe("sharpEstimate", () => {
  it("largest short side <= 720, avc1 before vp9 before av01, then the smallest size", () => {
    const video = [
      fmt({ formatId: "299", width: 1920, height: 1080, sizeBytes: 257_000_000 }),
      fmt({ formatId: "398", width: 1280, height: 720, vcodec: "av01.0.08M.08", sizeBytes: 71_000_000 }),
      fmt({ formatId: "302", width: 1280, height: 720, vcodec: "vp9", sizeBytes: 112_000_000 }),
      fmt({ formatId: "298", width: 1280, height: 720, sizeBytes: 150_524_867 }),
      fmt({ formatId: "135", width: 854, height: 480, sizeBytes: 28_000_000 }),
    ]
    expect(sharpEstimate(video)).toEqual({ sizeBytes: 150_524_867, shortSide: 720, portrait: false })
  })

  it("portrait clips are measured on the short side", () => {
    const video = [
      fmt({ formatId: "137", width: 1080, height: 1920 }),
      fmt({ formatId: "136", width: 720, height: 1280, sizeBytes: 9_000_000 }),
    ]
    expect(sharpEstimate(video)).toEqual({ sizeBytes: 9_000_000, shortSide: 720, portrait: true })
  })

  it("low resolution, unknown size, nothing at all", () => {
    expect(sharpEstimate([fmt({ formatId: "134", width: 320, height: 240 })])).toEqual({ shortSide: 240, portrait: false })
    expect(sharpEstimate([])).toEqual({ shortSide: null, portrait: false })
  })

  it("only formats above 720: the smallest of them", () => {
    const video = [fmt({ formatId: "308", width: 2560, height: 1440 }), fmt({ formatId: "299", width: 1920, height: 1080, sizeBytes: 5 })]
    expect(sharpEstimate(video)).toEqual({ sizeBytes: 5, shortSide: 1080, portrait: false })
  })
})

const BBB_FAST: SharpFast = { intervalMs: 4961, timesMs: steps(4961, 128) }
const BBB_VIDEO = [fmt({ formatId: "298", width: 1280, height: 720, sizeBytes: 150_524_867 })]

describe("sharpDialogModel", () => {
  const base = { durationS: 635, fast: BBB_FAST, mode: "same" as const, customText: "7", video: BBB_VIDEO, hasSharp: false }

  it("same times by default: interval with one decimal, count, sends {}", () => {
    expect(sharpDialogModel(base)).toEqual({
      sameAvailable: true,
      mode: "same",
      sameInterval: "5.0",
      sameCount: 128,
      customCount: 91,
      customError: false,
      overflow: null,
      params: {},
      sizeBytes: 150_524_867,
      resolution: { kind: "wide" },
      replace: false,
    })
  })

  it("custom 7 sends intervalS 7", () => {
    const model = sharpDialogModel({ ...base, mode: "custom" })
    expect(model.params).toEqual({ intervalS: 7 })
    expect(model.customCount).toBe(91)
  })

  it("custom 2 on 635 s is over 200: sentence values and intervalS 4 (AC-FRAME-04)", () => {
    const model = sharpDialogModel({ ...base, mode: "custom", customText: "2" })
    expect(model.overflow).toEqual({ n: "2", count: 318, n2: 4 })
    expect(model.params).toEqual({ intervalS: 4 })
  })

  it("same times over 200 (long clip): the one-decimal interval and intervalS N2", () => {
    const fast: SharpFast = { intervalMs: 10_000, timesMs: steps(10_000, 360) }
    const model = sharpDialogModel({ ...base, durationS: 3600, fast })
    expect(model.overflow).toEqual({ n: "10.0", count: 360, n2: 18 })
    expect(model.params).toEqual({ intervalS: 18 })
  })

  it.each(["", "0", "1.5", "abc", "3601"])("custom %j is invalid: error and no params", (customText) => {
    const model = sharpDialogModel({ ...base, mode: "custom", customText })
    expect(model.customError).toBe(true)
    expect(model.customCount).toBeNull()
    expect(model.params).toBeNull()
  })

  it("an invalid custom text does not block the same-times choice", () => {
    expect(sharpDialogModel({ ...base, customText: "abc" }).params).toEqual({})
  })

  it("no storyboard: custom only, default text max(1, ceil(d/100))", () => {
    expect(defaultCustomText(19)).toBe("1")
    expect(defaultCustomText(635)).toBe("7")
    const model = sharpDialogModel({ ...base, durationS: 19, fast: null, customText: defaultCustomText(19), video: [fmt({ formatId: "134", width: 320, height: 240 })] })
    expect(model.sameAvailable).toBe(false)
    expect(model.mode).toBe("custom")
    expect(model.params).toEqual({ intervalS: 1 })
    expect(model.customCount).toBe(19)
    expect(model.resolution).toEqual({ kind: "low", h: 240 })
    expect(model.sizeBytes).toBeNull()
  })

  it("portrait clip and an existing sharp set", () => {
    const model = sharpDialogModel({ ...base, video: [fmt({ formatId: "136", width: 720, height: 1280 })], hasSharp: true })
    expect(model.resolution).toEqual({ kind: "tall" })
    expect(model.replace).toBe(true)
  })
})
```

- [ ] **Step 7: Run it, expect FAIL** — `cd web && npm test -- sharp-frames` → `Failed to resolve import "./sharp-frames"`.

- [ ] **Step 8: Implement `web/src/lib/sharp-frames.ts`**
```ts
import { resolution } from "@/lib/download-options"
import type { VideoFormat } from "@/lib/types"

/**
 * ภาพคม (M5 รอบ B spec 3.2): แผนเวลาชุดเดียวกับ core/sharp.py (เคสร่วม tests/fixtures/sharp/plan-cases.json)
 * และตัวคำนวณของ dialog "ขอภาพคม" (จำนวนภาพ ขนาดวิดีโอชั่วคราว ความละเอียด ค่าที่ส่งเข้าคิว)
 */

export const MAX_SHARP_FRAMES = 200
export const MAX_INTERVAL_S = 3600
/** ภาพคมโหลดด้านสั้นไม่เกิน 720 (D4) */
const SHARP_SHORT_SIDE = 720

export type SharpPlan = { timesMs: number[]; intervalS: number | null; raised: boolean }

/** react-query key ของ GET /videos/{id}/sharp (หน้า W2 และตัวรับข่าว SSE ใช้ตัวเดียวกัน) */
export const sharpKey = (videoId: string) => ["sharp", videoId] as const

export const defaultIntervalS = (durationS: number): number => Math.max(1, Math.ceil(durationS / 100))

export const raisedIntervalS = (durationS: number): number => Math.ceil(durationS / MAX_SHARP_FRAMES)

/** จำนวนภาพของช่วงห่าง N = ceil(d / N) (เท่ากับจำนวน t_i = i × N วินาทีที่ยังน้อยกว่าความยาวคลิป) */
const countFor = (intervalS: number, durationS: number): number => Math.ceil(durationS / intervalS)

export function customTimes(intervalS: number, durationS: number): number[] {
  const out: number[] = []
  for (let t = 0; t < durationS * 1000; t += intervalS * 1000) out.push(t)
  return out
}

function raised(durationS: number): SharpPlan {
  const n2 = raisedIntervalS(durationS)
  return { timesMs: customTimes(n2, durationS), intervalS: n2, raised: true }
}

export function planSharp(
  durationS: number,
  opts: { intervalS: number | null; fastTimes: readonly number[] | null }
): SharpPlan {
  const { intervalS, fastTimes } = opts
  if (!Number.isInteger(durationS) || durationS <= 0) throw new RangeError(`durationS must be a positive integer: ${durationS}`)
  if (intervalS !== null && (!Number.isInteger(intervalS) || intervalS < 1 || intervalS > MAX_INTERVAL_S)) {
    throw new RangeError(`intervalS must be 1..${MAX_INTERVAL_S}: ${intervalS}`)
  }
  if (intervalS === null && fastTimes !== null) {
    if (fastTimes.length === 0) throw new RangeError("fastTimes is empty")
    return fastTimes.length <= MAX_SHARP_FRAMES ? { timesMs: [...fastTimes], intervalS: null, raised: false } : raised(durationS)
  }
  if (intervalS === null) {
    const n = defaultIntervalS(durationS)
    return { timesMs: customTimes(n, durationS), intervalS: n, raised: false }
  }
  if (countFor(intervalS, durationS) > MAX_SHARP_FRAMES) return raised(durationS)
  return { timesMs: customTimes(intervalS, durationS), intervalS, raised: false }
}

/** ช่อง "ตั้งเอง ทุก N วินาที": เลขอารบิกล้วน 1-3600 (ช่องว่างหัวท้ายได้) อย่างอื่น = null */
export function parseIntervalText(text: string): number | null {
  const trimmed = text.trim()
  if (!/^\d{1,4}$/.test(trimmed)) return null
  const n = Number(trimmed)
  return n >= 1 && n <= MAX_INTERVAL_S ? n : null
}

export type SharpEstimate = { sizeBytes?: number; shortSide: number | null; portrait: boolean }

const codecRank = (vcodec: string): number =>
  vcodec.startsWith("avc1") ? 0 : vcodec.startsWith("vp09") || vcodec.startsWith("vp9") ? 1 : vcodec.startsWith("av01") ? 2 : 3

/**
 * format ที่งานภาพคมน่าจะโหลด (ลำดับเดียวกับ download.sharp_choice ยกเว้นเรื่อง SDR ที่ VideoInfo ไม่มี):
 * ด้านสั้นมากสุดที่ไม่เกิน 720 · avc1 ก่อน vp9 ก่อน av01 · ไฟล์เล็กสุด (ไม่รู้ขนาดไว้ท้าย)
 * ไม่มีตัวไหนไม่เกิน 720 = ตัวที่ด้านสั้นน้อยสุด
 */
export function sharpEstimate(video: readonly VideoFormat[]): SharpEstimate {
  const sized = video.filter((f) => resolution(f) > 0)
  if (sized.length === 0) return { shortSide: null, portrait: false }
  const under = sized.filter((f) => resolution(f) <= SHARP_SHORT_SIDE)
  const target = under.length > 0 ? Math.max(...under.map(resolution)) : Math.min(...sized.map(resolution))
  const [best] = sized
    .filter((f) => resolution(f) === target)
    .sort(
      (a, b) =>
        codecRank(a.vcodec) - codecRank(b.vcodec) ||
        (a.sizeBytes ?? Number.MAX_SAFE_INTEGER) - (b.sizeBytes ?? Number.MAX_SAFE_INTEGER) ||
        a.formatId.localeCompare(b.formatId)
    )
  const portrait = best.width !== undefined && best.width < best.height
  return best.sizeBytes === undefined ? { shortSide: target, portrait } : { sizeBytes: best.sizeBytes, shortSide: target, portrait }
}

export type SharpMode = "same" | "custom"
export type SharpFast = { intervalMs: number; timesMs: readonly number[] }
export type SharpResolution = { kind: "wide" } | { kind: "tall" } | { kind: "low"; h: number }

export type SharpDialogModel = {
  sameAvailable: boolean
  mode: SharpMode
  sameInterval: string | null
  sameCount: number | null
  customCount: number | null
  customError: boolean
  overflow: { n: string; count: number; n2: number } | null
  params: { intervalS?: number } | null
  sizeBytes: number | null
  resolution: SharpResolution
  replace: boolean
}

/** ค่าตั้งต้นของช่อง "ตั้งเอง" (spec 1.3: คลิปไม่มี storyboard ใช้ max(1, ceil(d/100)) · มี storyboard ใช้ค่าเดียวกัน) */
export const defaultCustomText = (durationS: number): string => String(defaultIntervalS(Math.max(1, durationS)))

export function sharpDialogModel(input: {
  durationS: number
  fast: SharpFast | null
  mode: SharpMode
  customText: string
  video: readonly VideoFormat[]
  hasSharp: boolean
}): SharpDialogModel {
  const { durationS, fast, customText, video, hasSharp } = input
  const sameAvailable = fast !== null && fast.timesMs.length > 0
  const mode: SharpMode = sameAvailable ? input.mode : "custom"
  const sameCount = sameAvailable ? fast.timesMs.length : null
  const sameInterval = sameAvailable ? (fast.intervalMs / 1000).toFixed(1) : null
  const typed = parseIntervalText(customText)
  const usable = Number.isInteger(durationS) && durationS > 0
  const customCount = typed !== null && usable ? countFor(typed, durationS) : null
  let overflow: SharpDialogModel["overflow"] = null
  let params: SharpDialogModel["params"] = null
  if (usable && mode === "same" && sameCount !== null && sameInterval !== null) {
    if (sameCount > MAX_SHARP_FRAMES) {
      const n2 = raisedIntervalS(durationS)
      overflow = { n: sameInterval, count: sameCount, n2 }
      params = { intervalS: n2 }
    } else params = {}
  } else if (usable && mode === "custom" && typed !== null && customCount !== null) {
    if (customCount > MAX_SHARP_FRAMES) {
      const n2 = raisedIntervalS(durationS)
      overflow = { n: String(typed), count: customCount, n2 }
      params = { intervalS: n2 }
    } else params = { intervalS: typed }
  }
  const estimate = sharpEstimate(video)
  const resolutionLine: SharpResolution =
    estimate.shortSide !== null && estimate.shortSide < SHARP_SHORT_SIDE
      ? { kind: "low", h: estimate.shortSide }
      : estimate.portrait
        ? { kind: "tall" }
        : { kind: "wide" }
  return {
    sameAvailable,
    mode,
    sameInterval,
    sameCount,
    customCount,
    customError: mode === "custom" && typed === null,
    overflow,
    params,
    sizeBytes: estimate.sizeBytes ?? null,
    resolution: resolutionLine,
    replace: hasSharp,
  }
}
```

- [ ] **Step 9: Run the web checks, expect PASS** — `cd web && npm run typecheck && npm run lint && npm test`; then `uv run pytest -q -W error -p no:cacheprovider`.

- [ ] **Step 10: Commit**
```bash
git add src/yttoolkit/core/sharp.py tests/unit/test_sharp_plan.py tests/fixtures/sharp/plan-cases.json web/src/lib/sharp-frames.ts web/src/lib/sharp-frames.test.ts
git commit -F- <<'EOF'
feat(sharp): timecode plan shared by Python and TS (golden cases) and the dialog maths

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
EOF
```

### Task 3: Sharp format choice, downloaded-file facts, fake sharp clips

**Files:**
- Modify: `src/yttoolkit/core/download.py` (`FFMPEG_KINDS`, `SHARP_MAX_SHORT_SIDE`, `MediaFacts`, `media_facts`, `DownloadResult.media`, `SharpPick`, `pick_sharp_format`, `sharp_choice`)
- Modify: `src/yttoolkit/core/extractor.py` (`_downloaded_facts`, `YtDlpExtractor.download` / `_download_media`, `FakeExtractor.download`)
- Modify: `tests/fixtures/downloads/behaviors.json`, `tests/fixtures/README.md`
- Modify: `tests/unit/test_download_choice.py`, `tests/unit/test_extractor_download.py`

**Interfaces:**
- Consumes: `download._is_video`, `_resolution`, `_filesize`, `_number`, `_formats`; `YtError`.
- Produces: C3 exactly (`FFMPEG_KINDS` now contains `frames_sharp`; `DownloadResult` gains a 4th field with a default, so every positional `DownloadResult(path, info, choice)` keeps working).

- [ ] **Step 1: Write the failing tests**

`tests/unit/test_download_choice.py`: extend the `from yttoolkit.core.download import (…)` list with `MediaFacts, SharpPick, media_facts, pick_sharp_format, sharp_choice`, add `from yttoolkit.core.yterrors import YtError`, change the `FFMPEG_KINDS` assertion (line 346) to `assert FFMPEG_KINDS == {"video", "audio", "frames_sharp"}`, and append:
```python
# ---------- ภาพคม (M5 รอบ B spec 3.3) ----------


def _v(fid: str, w: int, h: int, vcodec: str = "avc1.4d401f", *, acodec: str = "none", size: int | None = None,
       dr: str | None = None) -> dict:
    fmt = {"format_id": fid, "width": w, "height": h, "vcodec": vcodec, "acodec": acodec}
    if size is not None:
        fmt["filesize"] = size
    if dr is not None:
        fmt["dynamic_range"] = dr
    return fmt


def _pick(*formats: dict) -> SharpPick | None:
    return pick_sharp_format({"formats": list(formats), "duration": 60})


def test_sharp_pick_on_the_bbb_fixture(fake: FakeExtractor) -> None:
    pick = pick_sharp_format(fake.probe(BBB))
    assert pick == SharpPick("298", 1280, 720, "SDR", False, 150_524_867)
    assert pick.short_side == 720 and pick.hdr is False


def test_sharp_prefers_sdr_over_a_larger_hdr_format() -> None:
    pick = _pick(_v("hdr", 1280, 720, "vp09.02.40.10", dr="HDR10"), _v("sdr", 854, 480))
    assert pick is not None and pick.format_id == "sdr"


def test_sharp_takes_the_largest_short_side_up_to_720() -> None:
    assert _pick(_v("1080", 1920, 1080), _v("720", 1280, 720), _v("480", 854, 480)).format_id == "720"
    portrait = _pick(_v("p1080", 1080, 1920), _v("p720", 720, 1280), _v("p480", 480, 854))
    assert portrait.format_id == "p720" and portrait.short_side == 720


def test_sharp_codec_order_then_smallest_size() -> None:
    assert _pick(_v("av1", 1280, 720, "av01.0.08M.08", size=10), _v("vp9", 1280, 720, "vp9", size=20),
                 _v("h264", 1280, 720, size=30)).format_id == "h264"  # fmt: skip
    assert _pick(_v("av1", 1280, 720, "av01.0.08M.08"), _v("vp9", 1280, 720, "vp09.00.40.08")).format_id == "vp9"
    assert _pick(_v("a", 1280, 720, size=30), _v("b", 1280, 720, size=20), _v("c", 1280, 720)).format_id == "b"


def test_sharp_video_only_before_muxed_and_muxed_fallback() -> None:
    assert _pick(_v("muxed720", 1280, 720, acodec="mp4a.40.2"), _v("vo480", 854, 480)).format_id == "vo480"
    muxed = _pick(_v("18", 640, 360, acodec="mp4a.40.2"))
    assert muxed is not None and muxed.muxed is True and muxed.short_side == 360


def test_sharp_hdr_only_and_nothing_up_to_720() -> None:
    hdr = _pick(_v("hlg", 1280, 720, "vp09.02.40.10", dr="HLG"))
    assert hdr.hdr is True and hdr.dynamic_range == "HLG"
    assert _pick(_v("1440", 2560, 1440, "vp9"), _v("1080", 1920, 1080)).format_id == "1080"


def test_sharp_no_video_format() -> None:
    assert _pick({"format_id": "140", "vcodec": "none", "acodec": "mp4a.40.2"}) is None
    with pytest.raises(YtError) as err:
        sharp_choice({"formats": [], "duration": 60})
    assert err.value.code == "E_UNKNOWN"


def test_sharp_choice_is_a_video_only_download(fake: FakeExtractor) -> None:
    choice, pick = sharp_choice(fake.probe(BBB))
    assert choice.format_spec == "298" and choice.merge_mp4 is True
    assert choice.audio_language is None and choice.notes == () and choice.expected_bytes == 150_524_867
    assert pick.format_id == "298"


def test_media_facts() -> None:
    assert media_facts({"width": 1280, "height": 720, "dynamic_range": "SDR"}) == MediaFacts(1280, 720, "SDR")
    facts = media_facts({"width": 1080.0, "height": 1920, "dynamic_range": "HDR10"})
    assert facts.short_side == 1080 and facts.hdr is True
    unknown = media_facts({"filepath": "x"})
    assert unknown == MediaFacts(None, None, None) and unknown.short_side is None and unknown.hdr is None
    assert media_facts({"height": 720}).short_side == 720
```
`tests/unit/test_extractor_download.py`: add these two entries to the `C14["videos"]` dict (after `CHAPTERS001`):
```python
        "SHARPCLIP01": {"probeAs": BBB, "title": "คลิปภาพคม"},
        "AUTOSHARP01": {"probeAs": BBB, "title": "คลิปภาพคมอัตโนมัติ",
                        "media": {"width": 1280, "height": 720, "dynamic_range": "SDR"}},
```
add `MediaFacts` to the `from yttoolkit.core.download import …` line, and append:
```python
def test_fake_reports_media_facts_only_when_the_behaviour_has_them(fast: FakeExtractor, tmp_path: Path) -> None:
    auto = fast.download("AUTOSHARP01", _video(), tmp_path / "a", Recorder().hooks)
    assert auto.media == MediaFacts(1280, 720, "SDR")
    plain = fast.download(BBB, _video(), tmp_path / "b", Recorder().hooks)
    assert plain.media is None


def test_real_download_reports_the_downloaded_format_facts(dl: type[DownloadYDL], workdir: Path) -> None:
    dl.result = {"id": BBB, "requested_downloads": [
        {"filepath": str(workdir / "media.mp4"), "width": 1280, "height": 720, "dynamic_range": "SDR"}]}
    result = YtDlpExtractor().download(BBB, _video(), workdir, Recorder().hooks)
    assert result.media == MediaFacts(1280, 720, "SDR")


def test_real_download_without_facts_reports_none(dl: type[DownloadYDL], workdir: Path) -> None:
    result = YtDlpExtractor().download(BBB, _video(), workdir, Recorder().hooks)
    assert result.media is None
```

- [ ] **Step 2: Run them, expect FAIL** — `uv run pytest tests/unit/test_download_choice.py tests/unit/test_extractor_download.py -q -W error -p no:cacheprovider` (`ImportError: cannot import name 'MediaFacts'`, C14 mismatch).

- [ ] **Step 3: Implement `core/download.py`**

Imports: add `from .yterrors import YtError`. Replace the kind lines:
```python
YOUTUBE_KINDS = frozenset({"video", "audio", "subtitle", "note", "frames_sharp"})  # note: ซับ + คอมเมนต์ปักหมุด
FFMPEG_KINDS = frozenset({"video", "audio", "frames_sharp"})  # frames_sharp: ffmpeg ดึงภาพจากวิดีโอที่โหลด (M5 รอบ B)
SHARP_MAX_SHORT_SIDE = 720  # D4: ภาพคมโหลดด้านสั้นไม่เกิน 720 แล้วย่อให้ด้านยาว 1280
```
After `DownloadHooks` (before `DownloadResult`):
```python
@dataclass(frozen=True)
class MediaFacts:
    """ขนาดภาพและช่วงสีของไฟล์ที่โหลดจริง (M5 รอบ B ภาพคมอัตโนมัติ) ค่าไหนไม่รู้ = None"""

    width: int | None
    height: int | None
    dynamic_range: str | None  # "SDR" | "HDR10" | "HLG" | ... (yt-dlp ใส่ "SDR" ให้ format วิดีโอที่ไม่บอก)

    @property
    def short_side(self) -> int | None:
        if self.height is None:
            return None
        return self.height if self.width is None else min(self.width, self.height)

    @property
    def hdr(self) -> bool | None:
        return None if self.dynamic_range is None else self.dynamic_range.upper() != "SDR"


def media_facts(fmt: Mapping[str, Any]) -> MediaFacts:
    width, height = _number(fmt.get("width")), _number(fmt.get("height"))
    dynamic = fmt.get("dynamic_range")
    return MediaFacts(
        round(width) if width is not None else None,
        round(height) if height is not None else None,
        dynamic if isinstance(dynamic, str) and dynamic else None,
    )
```
(move `_number` above `MediaFacts`, or keep it where it is: it is only called at runtime, so the order in the file does not matter.)
`DownloadResult` gains `media: MediaFacts | None = None  # ไฟล์ที่โหลดจริง (None = ไม่รู้)` as its last field.
At the end of the file:
```python
# ---------- ภาพคม (M5 รอบ B spec 3.3) ----------


@dataclass(frozen=True)
class SharpPick:
    """format ที่งานภาพคมโหลด"""

    format_id: str
    width: int | None
    height: int | None
    dynamic_range: str  # "SDR" เมื่อ format ไม่บอก
    muxed: bool  # มีเสียงติดมาด้วย (ใช้เมื่อไม่มี format วิดีโอล้วนเลย)
    size_bytes: int | None

    @property
    def short_side(self) -> int:
        return int(_resolution({"width": self.width, "height": self.height}))

    @property
    def hdr(self) -> bool:
        return self.dynamic_range.upper() != "SDR"


def _dynamic_range(fmt: Mapping[str, Any]) -> str:
    value = fmt.get("dynamic_range")
    return value if isinstance(value, str) and value else "SDR"


def _codec_rank(vcodec: str) -> int:
    """avc1 ก่อน vp9 ก่อน av01 (ถอดรหัสเร็วบนเครื่อง iGPU ของผู้ใช้) อื่น ๆ ไว้ท้าย"""
    if vcodec.startswith("avc1"):
        return 0
    if vcodec.startswith(("vp09", "vp9")):
        return 1
    if vcodec.startswith("av01"):
        return 2
    return 3


def _sharp_key(fmt: Mapping[str, Any], *, smallest: bool) -> tuple:
    res = _resolution(fmt)
    size = _filesize(fmt)
    return (
        _dynamic_range(fmt).upper() != "SDR",  # SDR ก่อน (D8)
        res if smallest else -res,
        _codec_rank(str(fmt.get("vcodec") or "")),
        size is None,
        size or 0,
        str(fmt.get("format_id")),
    )


def pick_sharp_format(info: Mapping[str, Any]) -> SharpPick | None:
    """format ของงานภาพคม: วิดีโอล้วน (ไม่มีเลย = ตัวที่มีเสียง) ด้านสั้นไม่เกิน 720 · SDR ก่อน · ด้านสั้นมากสุด ·
    avc1 > vp9 > av01 · ไฟล์เล็กสุด · ไม่มีตัวไหนไม่เกิน 720 = ตัวที่ด้านสั้นน้อยสุด · ไม่มีภาพเลย = None"""
    videos = [f for f in _formats(info) if _is_video(f) and _resolution(f) > 0 and f.get("format_id") is not None]
    if not videos:
        return None
    video_only = [f for f in videos if f.get("acodec") in (None, "none")]
    pool = video_only or videos
    under = [f for f in pool if _resolution(f) <= SHARP_MAX_SHORT_SIDE]
    if under:
        best = min(under, key=lambda f: _sharp_key(f, smallest=False))
    else:
        best = min(pool, key=lambda f: _sharp_key(f, smallest=True))
    width, height = _number(best.get("width")), _number(best.get("height"))
    return SharpPick(
        format_id=str(best["format_id"]),
        width=round(width) if width is not None else None,
        height=round(height) if height is not None else None,
        dynamic_range=_dynamic_range(best),
        muxed=best.get("acodec") not in (None, "none"),
        size_bytes=_filesize(best),
    )


def sharp_choice(info: dict) -> tuple[DownloadChoice, SharpPick]:
    """งาน frames_sharp: โหลด format เดียว (merge_mp4=True แบบงานวิดีโอไม่มีเสียง) ขนาดคาดการณ์ = ขนาดของ format นั้น"""
    pick = pick_sharp_format(info)
    if pick is None:
        raise YtError("E_UNKNOWN", "no video format")
    choice = DownloadChoice(
        format_spec=pick.format_id,
        merge_mp4=True,
        audio_language=None,
        notes=(),
        expected_bytes=pick.size_bytes,
    )
    return choice, pick
```

- [ ] **Step 4: Implement `core/extractor.py`**

Import `MediaFacts, media_facts` from `.download`. Add after `_media_path`:
```python
def _downloaded_facts(result: object) -> MediaFacts | None:
    """ขนาดภาพและช่วงสีของไฟล์ที่โหลดจริง: requested_downloads ตัวสุดท้าย (yt-dlp รวมค่าของภาพไว้ให้ตอนรวมไฟล์)
    หรือผลระดับบน · ไม่รู้ความสูง = None"""
    if not isinstance(result, dict):
        return None
    downloads = result.get("requested_downloads")
    source = downloads[-1] if isinstance(downloads, list) and downloads and isinstance(downloads[-1], dict) else result
    facts = media_facts(source)
    return facts if facts.height is not None else None
```
`_download_media` returns `tuple[Path, MediaFacts | None]`: replace `return _media_path(result, workdir)` with `return _media_path(result, workdir), _downloaded_facts(result)` and update its return annotation. In `YtDlpExtractor.download` replace `path = self._download_media(...)` with `path, media = self._download_media(source, choice, workdir, hooks)` and `return DownloadResult(path=path, info=info, choice=choice, media=media)`.
`FakeExtractor.download`: replace the final `return` with:
```python
        return DownloadResult(path=workdir / target, info=info, choice=choice, media=self._media_of(conf))
```
and add the method:
```python
    @staticmethod
    def _media_of(conf: dict) -> MediaFacts | None:
        """"media" ของคลิปใน behaviors.json (M5 รอบ B ภาพคมอัตโนมัติ) ไม่มี = ไม่รู้ (ภาพคมอัตโนมัติจะข้าม)"""
        media = conf.get("media")
        return media_facts(media) if isinstance(media, dict) else None
```

- [ ] **Step 5: Fixtures and README**

`tests/fixtures/downloads/behaviors.json`: add after the `CHAPTERS001` line (keep one entry per line, LF):
```json
    "SHARPCLIP01": {"probeAs": "aqz-KE-bpKQ", "title": "คลิปภาพคม"},
    "AUTOSHARP01": {"probeAs": "aqz-KE-bpKQ", "title": "คลิปภาพคมอัตโนมัติ", "media": {"width": 1280, "height": 720, "dynamic_range": "SDR"}}
```
(the `CHAPTERS001` line gains a trailing comma). `tests/fixtures/README.md`: append this section at the end of the file:
```markdown
## ภาพคม (M5 รอบ B)
คลิปปลอมใน `downloads/behaviors.json` (probe เป็น aqz-KE-bpKQ 635 วิ ภาพเร็ว 128 ภาพ) ใช้ใน `web/e2e/queue-sharp.spec.ts` เท่านั้น:
- `SHARPCLIP01` "คลิปภาพคม": งาน `frames_sharp` (เลือก format 298 avc1 1280×720 ตาม `download.sharp_choice`)
- `AUTOSHARP01` "คลิปภาพคมอัตโนมัติ": มี `"media": {"width": 1280, "height": 720, "dynamic_range": "SDR"}` = ตัวปลอมบอกว่าไฟล์ที่โหลดเป็น 720p SDR งาน `video` จึงทำภาพคมอัตโนมัติ (คลิปอื่นไม่มี `media` = ไม่รู้ขนาดไฟล์ ภาพคมอัตโนมัติข้าม)

`FakeMediaTools.extract_frame` เขียนสำเนาของ `media/cover.jpg` เป็นภาพคมทุกภาพ (โหมดปลอมไม่มี ffmpeg)
`sharp/plan-cases.json`: เคสแผนเวลาภาพคมที่ `tests/unit/test_sharp_plan.py` และ `web/src/lib/sharp-frames.test.ts` อ่านร่วมกัน (เขียนเอง คำนวณมือตาม spec 3.2)
```

- [ ] **Step 6: Run the tests, expect PASS** — the Step 2 command, then `uv run pytest -q -W error -p no:cacheprovider`.

- [ ] **Step 7: Commit**
```bash
git add src/yttoolkit/core/download.py src/yttoolkit/core/extractor.py tests/fixtures/downloads/behaviors.json tests/fixtures/README.md tests/unit/test_download_choice.py tests/unit/test_extractor_download.py
git commit -F- <<'EOF'
feat(download): sharp format choice (SDR, <=720 short side, avc1 first), downloaded-file facts, fake sharp clips

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
EOF
```

### Task 4: Frame extraction (argument builder, real ffmpeg, fake)

**Files:**
- Modify: `src/yttoolkit/core/media.py` (constants, `scale_filter`, `tonemap_filter`, `_check_frame`, `frame_args`, `MediaTools.extract_frame`, `FfmpegTools.extract_frame`, `FrameCall`, `FakeMediaTools.extract_frame`)
- Modify: `tests/unit/test_media_args.py`
- Create: `tests/integration/test_sharp_ffmpeg.py`

**Interfaces:**
- Consumes: `run_ffmpeg`, `_seconds`, `JobCancelled`, `YtError`.
- Produces: C4 exactly.

- [ ] **Step 1: Write the failing unit tests** — append to `tests/unit/test_media_args.py` (add `FrameCall, frame_args, scale_filter, tonemap_filter` to the import list and `from yttoolkit.core import media as media_module`):
```python
# ---------- ภาพคม (M5 รอบ B spec 3.4) ----------

SCALE = "scale=w='min(1280,iw)':h='min(1280,ih)':force_original_aspect_ratio=decrease"
FRAME_HEAD = [FF, "-hide_banner", "-nostdin", "-y", "-loglevel", "error"]
JPG = Path("f.jpg")


def _no_cancel() -> bool:
    return False


def test_frame_args_sdr_exact() -> None:
    assert scale_filter(1280) == SCALE
    assert frame_args(FF, SRC, JPG, 61_500) == FRAME_HEAD + [
        "-ss", "61.500", "-i", str(SRC), "-frames:v", "1", "-vf", SCALE, "-q:v", "2", str(JPG)]  # fmt: skip


def test_frame_args_hdr_puts_the_tone_map_before_the_scale() -> None:
    args = frame_args(FF, SRC, JPG, 0, dynamic_range="HDR10")
    vf = args[args.index("-vf") + 1]
    assert vf == tonemap_filter("HDR10") + "," + SCALE
    assert vf.startswith("setparams=range=tv:color_primaries=bt2020:color_trc=smpte2084:colorspace=bt2020nc,zscale=t=linear")
    assert "tonemap=tonemap=hable:desat=0" in vf and "format=yuv420p" in vf
    assert "color_trc=arib-std-b67" in tonemap_filter("HLG")


@pytest.mark.parametrize(
    ("t_ms", "long_side", "dynamic_range"),
    [(-1, 1280, None), (0, 0, None), (0, 1280, "SDR"), (0, 1280, ""), (True, 1280, None)],
)
def test_frame_args_rejects_bad_input(t_ms, long_side, dynamic_range) -> None:
    with pytest.raises(ValueError):
        frame_args(FF, SRC, JPG, t_ms, long_side=long_side, dynamic_range=dynamic_range)
    with pytest.raises(ValueError):
        FakeMediaTools(MEDIA_ROOT).extract_frame(
            MEDIA_ROOT / "video.mp4", JPG, t_ms, long_side=long_side, dynamic_range=dynamic_range, cancel=_no_cancel)


def test_fake_extract_frame_copies_the_cover_and_records(tmp_path: Path) -> None:
    fake = FakeMediaTools(MEDIA_ROOT)
    dst = tmp_path / "0001.jpg"
    assert fake.extract_frame(MEDIA_ROOT / "video.mp4", dst, 1000, long_side=1280, dynamic_range=None,
                              cancel=_no_cancel) is True  # fmt: skip
    assert dst.read_bytes() == (MEDIA_ROOT / "cover.jpg").read_bytes()
    assert fake.frames == [FrameCall("video.mp4", "0001.jpg", 1000, 1280, None)]


def test_fake_extract_frame_limit_missing_input_and_cancel(tmp_path: Path) -> None:
    fake = FakeMediaTools(MEDIA_ROOT)
    fake.frame_limit_ms = 2000
    late = tmp_path / "late.jpg"
    assert fake.extract_frame(MEDIA_ROOT / "video.mp4", late, 2000, long_side=1280, dynamic_range=None,
                              cancel=_no_cancel) is False  # fmt: skip
    assert not late.exists()
    gone = tmp_path / "gone.jpg"
    assert fake.extract_frame(tmp_path / "missing.mp4", gone, 0, long_side=1280, dynamic_range=None,
                              cancel=_no_cancel) is False  # fmt: skip
    with pytest.raises(JobCancelled):
        fake.extract_frame(MEDIA_ROOT / "video.mp4", tmp_path / "c.jpg", 0, long_side=1280, dynamic_range=None,
                           cancel=lambda: True)  # fmt: skip
    assert not (tmp_path / "c.jpg").exists()


def test_ffmpeg_extract_frame_failure_is_a_dropped_frame(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def failing(args, **kwargs):
        Path(args[-1]).write_bytes(b"half")
        raise YtError("E_UNKNOWN", "ffmpeg exit 234: Nothing was written into output file")

    monkeypatch.setattr(media_module, "run_ffmpeg", failing)
    dst = tmp_path / "x.jpg"
    tools = FfmpegTools(lambda: Path("ffmpeg"))
    assert tools.extract_frame(tmp_path / "in.mp4", dst, 0, long_side=1280, dynamic_range=None, cancel=_no_cancel) is False
    assert not dst.exists()


@pytest.mark.parametrize("code", ["E_DISK_FULL", "E_FFMPEG_MISSING"])
def test_ffmpeg_extract_frame_passes_other_errors_on(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, code: str) -> None:
    def failing(args, **kwargs):
        raise YtError(code, "x")

    monkeypatch.setattr(media_module, "run_ffmpeg", failing)
    with pytest.raises(YtError) as err:
        FfmpegTools(lambda: Path("ffmpeg")).extract_frame(
            tmp_path / "in.mp4", tmp_path / "x.jpg", 0, long_side=1280, dynamic_range=None, cancel=_no_cancel)
    assert err.value.code == code


def test_ffmpeg_extract_frame_success_and_missing_ffmpeg(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    seen: list[list[str]] = []

    def writing(args, **kwargs):
        seen.append(args)
        Path(args[-1]).write_bytes(b"\xff\xd8jpeg")

    monkeypatch.setattr(media_module, "run_ffmpeg", writing)
    dst = tmp_path / "ok.jpg"
    assert FfmpegTools(lambda: Path("ffmpeg")).extract_frame(
        tmp_path / "in.mp4", dst, 2500, long_side=1280, dynamic_range="HDR10", cancel=_no_cancel) is True
    assert seen[0][seen[0].index("-ss") + 1] == "2.500" and "setparams" in seen[0][seen[0].index("-vf") + 1]
    with pytest.raises(YtError) as err:
        FfmpegTools(lambda: None).extract_frame(tmp_path / "in.mp4", dst, 0, long_side=1280, dynamic_range=None,
                                                cancel=_no_cancel)  # fmt: skip
    assert err.value.code == "E_FFMPEG_MISSING"
```

- [ ] **Step 2: Write the failing real-ffmpeg test** — `tests/integration/test_sharp_ffmpeg.py`:
```python
"""ภาพคม (M5 รอบ B) กับ ffmpeg จริง: ด้านยาว 1280 (แนวนอน/แนวตั้ง) ไม่ขยายภาพเล็ก ภาพตรงเวลา ภาพท้ายคลิปไม่มี และ tone-map"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
from helpers_ffmpeg import find_test_ffmpeg, requires_ffmpeg
from PIL import Image

from yttoolkit.core.cancel import JobCancelled
from yttoolkit.core.media import FfmpegTools

pytestmark = requires_ffmpeg
MEDIA = Path(__file__).resolve().parents[1] / "fixtures" / "media"


def _ffmpeg() -> str:
    found = find_test_ffmpeg()
    assert found is not None
    return found


def _tools() -> FfmpegTools:
    return FfmpegTools(lambda: Path(_ffmpeg()))


def _clip(folder: Path, name: str, size: str, *extra: str) -> Path:
    out = folder / name
    subprocess.run(
        [_ffmpeg(), "-hide_banner", "-loglevel", "error", "-y", "-f", "lavfi", "-i", f"testsrc2=size={size}:rate=10",
         "-t", "6", "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p", *extra, str(out)],
        check=True,
    )  # fmt: skip
    return out


@pytest.fixture(scope="module")
def clips(tmp_path_factory) -> dict[str, Path]:
    folder = tmp_path_factory.mktemp("sharp")
    return {
        "wide": _clip(folder, "wide.mp4", "1920x1080"),
        "portrait": _clip(folder, "portrait.mp4", "1080x1920"),
        "hdr": _clip(folder, "hdr.mp4", "1280x720", "-color_primaries", "bt2020", "-color_trc", "smpte2084",
                     "-colorspace", "bt2020nc"),
    }  # fmt: skip


def _never() -> bool:
    return False


def _size(path: Path) -> tuple[int, int]:
    with Image.open(path) as img:
        assert img.format == "JPEG"
        return img.size


def _gray(path: Path) -> bytes:
    with Image.open(path) as img:
        return img.convert("L").resize((160, 90)).tobytes()


def _decoded(src: Path, at_s: float, folder: Path) -> Path:
    out = folder / f"ref-{at_s}.png"
    subprocess.run([_ffmpeg(), "-hide_banner", "-loglevel", "error", "-y", "-ss", f"{at_s:.3f}", "-i", str(src),
                    "-frames:v", "1", str(out)], check=True)  # fmt: skip
    return out


def test_wide_long_side_is_1280_and_the_picture_is_at_the_timecode(clips, tmp_path: Path) -> None:
    dst = tmp_path / "w.jpg"
    assert _tools().extract_frame(clips["wide"], dst, 3000, long_side=1280, dynamic_range=None, cancel=_never) is True
    assert _size(dst) == (1280, 720)
    here, other = _gray(dst), _gray(_decoded(clips["wide"], 3.0, tmp_path))
    later = _gray(_decoded(clips["wide"], 4.5, tmp_path))
    diff = sum(abs(a - b) for a, b in zip(here, other, strict=True)) / len(here)
    far = sum(abs(a - b) for a, b in zip(here, later, strict=True)) / len(here)
    assert diff < far and diff < 8


def test_portrait_becomes_720_by_1280(clips, tmp_path: Path) -> None:  # D4
    dst = tmp_path / "p.jpg"
    assert _tools().extract_frame(clips["portrait"], dst, 1000, long_side=1280, dynamic_range=None, cancel=_never)
    assert _size(dst) == (720, 1280)


def test_small_video_is_never_upscaled(tmp_path: Path) -> None:
    dst = tmp_path / "s.jpg"
    assert _tools().extract_frame(MEDIA / "video.mp4", dst, 1000, long_side=1280, dynamic_range=None, cancel=_never)
    assert _size(dst) == (160, 90)


def test_a_timecode_past_the_last_frame_yields_no_image(tmp_path: Path) -> None:
    dst = tmp_path / "late.jpg"
    assert _tools().extract_frame(MEDIA / "video.mp4", dst, 1950, long_side=1280, dynamic_range=None,
                                  cancel=_never) is False  # fmt: skip
    assert not dst.exists()


def test_hdr_tone_map_chain_runs(clips, tmp_path: Path) -> None:
    dst = tmp_path / "h.jpg"
    assert _tools().extract_frame(clips["hdr"], dst, 1000, long_side=1280, dynamic_range="HDR10", cancel=_never)
    assert _size(dst) == (1280, 720)


def test_cancel_stops_the_extraction(clips, tmp_path: Path) -> None:
    with pytest.raises(JobCancelled):
        _tools().extract_frame(clips["wide"], tmp_path / "c.jpg", 0, long_side=1280, dynamic_range=None,
                               cancel=lambda: True)  # fmt: skip
```

- [ ] **Step 3: Run them, expect FAIL** — `uv run pytest tests/unit/test_media_args.py tests/integration/test_sharp_ffmpeg.py -q -W error -p no:cacheprovider` (`ImportError: cannot import name 'FrameCall'`).

- [ ] **Step 4: Implement `core/media.py`**

After `CUT_AAC_KBPS`:
```python
# ภาพคม (M5 รอบ B D4): ด้านยาว 1280 ไม่ขยายภาพเล็ก · -q:v 2 ของ mjpeg (คมพอสำหรับงานสไลด์ ไฟล์ราว 150-300 KB)
SHARP_LONG_SIDE = 1280
SHARP_JPEG_Q = 2
_HLG = "HLG"
```
After `cut_args`:
```python
def scale_filter(long_side: int) -> str:
    """ย่อให้ด้านยาวไม่เกิน long_side คงสัดส่วน ไม่ขยาย (แนวนอน 1280x720 · แนวตั้ง 720x1280 · ภาพเล็กคงเดิม)"""
    return f"scale=w='min({long_side},iw)':h='min({long_side},ih)':force_original_aspect_ratio=decrease"


def tonemap_filter(dynamic_range: str) -> str:
    """HDR -> SDR (D8 ใช้เฉพาะคลิปที่ไม่มี format SDR เลย) setparams บอกช่วงสีให้ zscale เองเพราะบางไฟล์ไม่ติดป้าย
    (วัดแล้ว: ไม่มี setparams = "no path between colorspaces") HLG ใช้ arib-std-b67 นอกนั้น smpte2084 (HDR10)"""
    trc = "arib-std-b67" if dynamic_range.strip().upper() == _HLG else "smpte2084"
    return (
        f"setparams=range=tv:color_primaries=bt2020:color_trc={trc}:colorspace=bt2020nc,"
        "zscale=t=linear:npl=100,format=gbrpf32le,zscale=p=bt709,tonemap=tonemap=hable:desat=0,"
        "zscale=t=bt709:m=bt709:r=tv,format=yuv420p"
    )


def _check_frame(t_ms: int, long_side: int, dynamic_range: str | None) -> None:
    """กฎเดียวกันทั้งตัวจริงและตัวปลอม"""
    if isinstance(t_ms, bool) or not isinstance(t_ms, int) or t_ms < 0:
        raise ValueError(f"bad frame time: {t_ms!r}")
    if long_side < 1:
        raise ValueError(f"bad long side: {long_side!r}")
    if dynamic_range is not None and dynamic_range.strip().upper() in ("", "SDR"):
        raise ValueError("pass dynamic_range=None for SDR")


def frame_args(
    ffmpeg: str,
    src: Path,
    dst: Path,
    t_ms: int,
    *,
    long_side: int = SHARP_LONG_SIDE,
    dynamic_range: str | None = None,
) -> list[str]:
    """ภาพคมหนึ่งภาพ (spec 3.4): -ss ก่อน -i บนไฟล์ในเครื่อง = ตรงเวลา · dynamic_range = HDR ที่ต้อง tone-map"""
    _check_frame(t_ms, long_side, dynamic_range)
    scale = scale_filter(long_side)
    vf = scale if dynamic_range is None else f"{tonemap_filter(dynamic_range)},{scale}"
    return [ffmpeg, "-hide_banner", "-nostdin", "-y", "-loglevel", "error", "-ss", _seconds(t_ms), "-i", str(src),
            "-frames:v", "1", "-vf", vf, "-q:v", str(SHARP_JPEG_Q), str(dst)]  # fmt: skip


def _no_progress(_fraction: float | None) -> None:
    """ภาพเดียวจบเร็ว ความคืบหน้านับต่อภาพที่ตัวทำงาน"""
```
Add to the `MediaTools` protocol:
```python
    def extract_frame(
        self,
        src: Path,
        dst: Path,
        t_ms: int,
        *,
        long_side: int,
        dynamic_range: str | None,
        cancel: Callable[[], bool],
    ) -> bool: ...
```
`FfmpegTools`:
```python
    def extract_frame(
        self,
        src: Path,
        dst: Path,
        t_ms: int,
        *,
        long_side: int,
        dynamic_range: str | None,
        cancel: Callable[[], bool],
    ) -> bool:
        """True = ได้ภาพ JPEG ที่ dst · False = ffmpeg ไม่ได้ภาพ (เวลาเลยภาพสุดท้าย ช่วงวินาทีท้ายคลิป) ภาพจึงถูกข้าม
        ffmpeg หาไม่เจอ / ดิสก์เต็ม / ยกเลิก = โยนต่อ"""
        args = frame_args(self._require(), src.resolve(), dst.resolve(), t_ms,
                          long_side=long_side, dynamic_range=dynamic_range)  # fmt: skip
        dst.unlink(missing_ok=True)
        try:
            run_ffmpeg(args, duration_s=None, cancel=cancel, on_progress=_no_progress, popen_flags=self._popen_flags)
        except YtError as exc:
            if exc.code != "E_UNKNOWN":
                raise
            dst.unlink(missing_ok=True)
            return False
        return dst.is_file() and dst.stat().st_size > 0
```
After `CutCall`:
```python
@dataclass(frozen=True)
class FrameCall:
    """ภาพคมหนึ่งภาพของ FakeMediaTools (ภาพที่เขียนเป็นสำเนาของ cover.jpg เสมอ)"""

    src_name: str
    dst_name: str
    t_ms: int
    long_side: int
    dynamic_range: str | None
```
`FakeMediaTools.__init__` gains `self.frames: list[FrameCall] = []` and `self.frame_limit_ms: int | None = None  # เวลาตั้งแต่นี้ไม่ได้ภาพ (เลียนแบบภาพท้ายคลิป)`; update its docstring with `ภาพคม = คัดลอก cover.jpg และจดการเรียกไว้ใน frames` and add:
```python
    def extract_frame(
        self,
        src: Path,
        dst: Path,
        t_ms: int,
        *,
        long_side: int,
        dynamic_range: str | None,
        cancel: Callable[[], bool],
    ) -> bool:
        _check_frame(t_ms, long_side, dynamic_range)
        if cancel():
            raise JobCancelled()
        self.frames.append(FrameCall(src.name, dst.name, t_ms, long_side, dynamic_range))
        if not Path(src).is_file() or (self.frame_limit_ms is not None and t_ms >= self.frame_limit_ms):
            return False
        shutil.copyfile(self._root / "cover.jpg", dst)
        return True
```

- [ ] **Step 5: Run them, expect PASS** — the Step 3 command (the integration file skips itself without ffmpeg), then the full suite.

- [ ] **Step 6: Commit**
```bash
git add src/yttoolkit/core/media.py tests/unit/test_media_args.py tests/integration/test_sharp_ffmpeg.py
git commit -F- <<'EOF'
feat(media): one-frame ffmpeg extraction (long side 1280, HDR tone-map), fake frames

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
EOF
```

### Task 5: Sharp cache store, output folder, frame names

**Files:**
- Create: `src/yttoolkit/core/sharp_store.py`, `tests/unit/test_sharp_store.py`
- Modify: `src/yttoolkit/core/files.py` (`SHARP_DIR_SUFFIX`, `PARTIAL_MARKER`, `plan_sharp_dir`, `_dir_candidates`, `_reserve_dir`, `move_files_into_dir`)
- Modify: `src/yttoolkit/core/frames.py` (`frame_file_names`, `missing_code`)
- Modify: `src/yttoolkit/core/storyboard.py` (rename `_file_name` → `frame_file_name`, 3 places: `:201`, `:250`, `:287`)
- Modify: `tests/unit/test_files.py`, `tests/unit/test_frames.py`

**Interfaces:**
- Consumes: `files.plan_output`, `truncate_title`, `_u16`, `_is_cross_device`, `_copy_across_devices`; `inputs.VIDEO_ID`; `YtError`.
- Produces: C5 exactly.

- [ ] **Step 1: Write the failing tests**

`tests/unit/test_files.py` (append; add `import shutil` to the imports):
```python
# ---------- ภาพคม (M5 รอบ B) ----------

FRAME = "frame_000-00-00_200.jpg"  # ชื่อไฟล์ภาพคมที่ยาวที่สุดที่ตัวทำงานเขียนได้


def _items(tmp_path: Path, names: list[str]) -> list[tuple[Path, str]]:
    src = tmp_path / "work"
    src.mkdir(exist_ok=True)
    made = []
    for i, name in enumerate(names):
        path = src / f"{i:04d}.jpg"
        path.write_bytes(b"jpg%d" % i)
        made.append((path, name))
    return made


def test_sharp_dir_sits_in_the_clip_folder(tmp_path):
    folder = files.plan_sharp_dir(tmp_path, "คลิป: ทดสอบ", ID)
    assert folder.parent == files.plan_output(tmp_path, "คลิป: ทดสอบ", ID, "", "mp4").parent
    assert folder.name == "คลิป ทดสอบ - ภาพคม"
    grouped = files.plan_sharp_dir(tmp_path, "คลิป", ID, "งานลูกค้า")
    assert grouped.parent.parent.name == "งานลูกค้า"


def test_sharp_dir_fits_240_with_the_longest_frame_name(tmp_path):
    root = tmp_path / ("r" * 80)
    folder = files.plan_sharp_dir(root, "ก" * 300, ID)
    assert folder.name.endswith(files.SHARP_DIR_SUFFIX)
    assert files._u16(str(folder)) + files.UNIQUE_RESERVE + 1 + files._u16(FRAME) <= files.PATH_LIMIT
    deep = tmp_path / ("d" * 190)
    with pytest.raises(YtError) as err:
        files.plan_sharp_dir(deep, "ก" * 300, ID)
    assert err.value.code == "E_OUTPUT_NOT_WRITABLE"


def test_sharp_dir_candidates_keep_dotted_titles(tmp_path):  # Review Focus 1
    planned = files.plan_sharp_dir(tmp_path, "Ep.1 วิธีทำ", ID)
    first = files.move_files_into_dir(_items(tmp_path, ["frame_00-00-00.jpg"]), planned)
    second = files.move_files_into_dir(_items(tmp_path, ["frame_00-00-00.jpg"]), planned)
    assert first.name == "Ep.1 วิธีทำ - ภาพคม"
    assert second.name == "Ep.1 วิธีทำ - ภาพคม (2)"
    assert sorted(p.name for p in second.iterdir()) == ["frame_00-00-00.jpg"]  # ไม่มี marker เหลือ


def test_move_files_into_dir_moves_everything_and_removes_the_marker(tmp_path):
    items = _items(tmp_path, ["frame_00-00-00.jpg", "frame_00-00-00_2.jpg", "frame_00-01-00.jpg"])
    final = files.move_files_into_dir(items, tmp_path / "out" / "คลิป [x]" / "คลิป - ภาพคม")
    assert sorted(p.name for p in final.iterdir()) == ["frame_00-00-00.jpg", "frame_00-00-00_2.jpg", "frame_00-01-00.jpg"]
    assert not (final / files.PARTIAL_MARKER).exists()
    assert (final / "frame_00-00-00_2.jpg").read_bytes() == b"jpg1"
    assert not any(src.exists() for src, _ in items)


def test_move_files_into_dir_failure_removes_the_new_folder(tmp_path, monkeypatch):
    items = _items(tmp_path, ["a.jpg", "b.jpg"])
    real = files.os.replace
    calls = {"n": 0}

    def flaky(src, dst):
        calls["n"] += 1
        if calls["n"] == 2:
            raise OSError(errno.ENOSPC, "No space left on device")
        return real(src, dst)

    monkeypatch.setattr(files.os, "replace", flaky)
    planned = tmp_path / "out" / "คลิป - ภาพคม"
    with pytest.raises(YtError) as err:
        files.move_files_into_dir(items, planned)
    assert err.value.code == "E_DISK_FULL"
    assert not planned.exists()


def test_move_files_into_dir_cancel_removes_the_new_folder(tmp_path, monkeypatch):
    items = _items(tmp_path, ["a.jpg"])

    def interrupted(src, dst):
        raise KeyboardInterrupt

    monkeypatch.setattr(files.os, "replace", interrupted)
    planned = tmp_path / "out" / "คลิป - ภาพคม"
    with pytest.raises(KeyboardInterrupt):
        files.move_files_into_dir(items, planned)
    assert not planned.exists()


def test_move_files_into_dir_rejects_paths_as_names(tmp_path):
    with pytest.raises(ValueError):
        files.move_files_into_dir(_items(tmp_path, ["../x.jpg"]), tmp_path / "out" / "d")
    assert not (tmp_path / "out" / "d").exists()
    shutil.rmtree(tmp_path / "work")
```
`tests/unit/test_frames.py` (append; add `frame_file_names` to the `from yttoolkit.core.frames import (…)` list):
```python
def test_frame_file_names_match_the_zip_names() -> None:
    times = [4000, 4100, 4999, 5000, 3_661_000]
    assert frame_file_names(times) == [
        "frame_00-00-04.jpg", "frame_00-00-04_2.jpg", "frame_00-00-04_3.jpg", "frame_00-00-05.jpg", "frame_01-01-01.jpg",
    ]  # fmt: skip


def test_missing_code_can_name_the_sharp_set(tmp_path: Path) -> None:
    for build_it in (
        lambda: contact_sheet([(0, tmp_path / "nope.jpg")], "x", 1, missing_code="E_NO_SHARP_FRAMES"),
        lambda: frames_zip([(0, tmp_path / "nope.jpg")], missing_code="E_NO_SHARP_FRAMES"),
    ):
        with pytest.raises(YtError) as caught:
            build_it()
        assert caught.value.code == "E_NO_SHARP_FRAMES"


def test_sharp_sized_frames_are_downscaled_into_the_cell(tmp_path: Path) -> None:
    big = make_frame(tmp_path / "big.jpg", (200, 30, 30), size=(1280, 720))
    tall = make_frame(tmp_path / "tall.jpg", (30, 200, 30), size=(720, 1280))
    data = contact_sheet([(0, big), (60_000, tall)], "ภาพคม", 120)
    with Image.open(io.BytesIO(data)) as sheet:
        assert sheet.width == 5 * CELL_W + 6 * 8
```
`tests/unit/test_sharp_store.py` (new):
```python
"""ชุดภาพคมใน cache (M5 รอบ B spec 5): อ่าน เตรียม สลับแบบ atomic ทิ้ง และล้างของค้างตอนเปิดโปรแกรม"""

from __future__ import annotations

import json
import pathlib
from pathlib import Path

import pytest

from yttoolkit.core import sharp_store
from yttoolkit.core.sharp_store import (
    FOLDER,
    commit_sharp,
    discard_sharp,
    prepare_sharp,
    read_sharp,
    sweep_sharp_leftovers,
)
from yttoolkit.core.yterrors import YtError

COVER = Path(__file__).resolve().parents[1] / "fixtures" / "media" / "cover.jpg"
BBB = "aqz-KE-bpKQ"
JOB_A = "01900000-0000-7000-8000-00000000000a"
JOB_B = "01900000-0000-7000-8000-00000000000b"
WHEN = "2026-10-05T03:00:00+00:00"


def _frames(times: list[int]) -> list[tuple[int, Path]]:
    return [(t, COVER) for t in times]


def _install(cache: Path, job: str, times: list[int], *, origin: str = "manual", interval_ms: int | None = None) -> dict:
    staged = prepare_sharp(cache, BBB, job, _frames(times), origin=origin, interval_ms=interval_ms, created_at=WHEN)
    return commit_sharp(cache, BBB, staged)


def test_prepare_then_commit_writes_the_index_and_frames(tmp_path: Path) -> None:
    index = _install(tmp_path, JOB_A, [0, 60_000, 120_000], interval_ms=60_000)
    assert index == {
        "origin": "manual", "intervalMs": 60_000, "createdAt": WHEN,
        "frames": [{"index": 0, "tMs": 0, "file": "f_0000.jpg"}, {"index": 1, "tMs": 60_000, "file": "f_0001.jpg"},
                   {"index": 2, "tMs": 120_000, "file": "f_0002.jpg"}],
    }  # fmt: skip
    folder = tmp_path / BBB / FOLDER
    assert sorted(p.name for p in folder.iterdir()) == ["f_0000.jpg", "f_0001.jpg", "f_0002.jpg", "index.json"]
    assert read_sharp(tmp_path, BBB) == index
    assert sorted(p.name for p in (tmp_path / BBB).iterdir()) == [FOLDER]


def test_a_new_set_replaces_the_old_one(tmp_path: Path) -> None:
    _install(tmp_path, JOB_A, [0, 1000, 2000])
    index = _install(tmp_path, JOB_B, [0], origin="auto")
    assert index["origin"] == "auto" and len(index["frames"]) == 1
    assert sorted(p.name for p in (tmp_path / BBB / FOLDER).iterdir()) == ["f_0000.jpg", "index.json"]
    assert sorted(p.name for p in (tmp_path / BBB).iterdir()) == [FOLDER]


def test_staged_set_is_invisible_until_commit_and_discard_removes_it(tmp_path: Path) -> None:
    _install(tmp_path, JOB_A, [0, 1000])
    staged = prepare_sharp(tmp_path, BBB, JOB_B, _frames([5000]), origin="manual", interval_ms=None, created_at=WHEN)
    assert staged.name == f"sharp.tmp-{JOB_B}"
    assert len(read_sharp(tmp_path, BBB)["frames"]) == 2
    discard_sharp(staged)
    assert not staged.exists()
    assert len(read_sharp(tmp_path, BBB)["frames"]) == 2


@pytest.mark.parametrize(
    ("frames", "origin", "job"),
    [([], "manual", JOB_A), ([(0, COVER)], "other", JOB_A), ([(0, COVER)], "manual", "../x")],
)
def test_prepare_rejects_bad_input(tmp_path: Path, frames, origin, job) -> None:
    with pytest.raises(ValueError):
        prepare_sharp(tmp_path, BBB, job, frames, origin=origin, interval_ms=None, created_at=WHEN)
    with pytest.raises(ValueError):
        prepare_sharp(tmp_path, "bad id", JOB_A, [(0, COVER)], origin="manual", interval_ms=None, created_at=WHEN)


def test_read_sharp_rejects_broken_sets(tmp_path: Path) -> None:
    assert read_sharp(tmp_path, BBB) is None
    assert read_sharp(tmp_path, "not an id") is None
    _install(tmp_path, JOB_A, [0, 1000])
    index_path = tmp_path / BBB / FOLDER / "index.json"
    (tmp_path / BBB / FOLDER / "f_0001.jpg").unlink()
    assert read_sharp(tmp_path, BBB) is None  # ไฟล์ภาพหาย
    _install(tmp_path, JOB_B, [0])
    doc = json.loads(index_path.read_text(encoding="utf-8"))
    for broken in ({**doc, "origin": "x"}, {**doc, "intervalMs": True}, {**doc, "frames": []},
                   {**doc, "frames": [{"index": 0, "tMs": -1, "file": "f_0000.jpg"}]}, {**doc, "createdAt": None}):  # fmt: skip
        index_path.write_text(json.dumps(broken), encoding="utf-8")
        assert read_sharp(tmp_path, BBB) is None
    index_path.write_text("{", encoding="utf-8")
    assert read_sharp(tmp_path, BBB) is None


def test_commit_retries_a_locked_rename_then_succeeds(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _install(tmp_path, JOB_A, [0])
    real = pathlib.Path.rename
    locked = {"left": 3}

    def rename(self, target):
        if self.name == FOLDER and locked["left"]:
            locked["left"] -= 1
            raise PermissionError(13, "ไฟล์ถูกเปิดค้างอยู่")
        return real(self, target)

    monkeypatch.setattr(pathlib.Path, "rename", rename)
    monkeypatch.setattr(sharp_store, "RENAME_WAIT_S", 0)
    index = _install(tmp_path, JOB_B, [0, 1000])
    assert len(index["frames"]) == 2 and locked["left"] == 0


def test_commit_failure_keeps_the_previous_set(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _install(tmp_path, JOB_A, [0, 1000, 2000])
    real = pathlib.Path.rename

    def rename(self, target):
        if self.name.startswith("sharp.tmp-"):
            raise PermissionError(13, "ล็อก")
        return real(self, target)

    monkeypatch.setattr(pathlib.Path, "rename", rename)
    monkeypatch.setattr(sharp_store, "RENAME_WAIT_S", 0)
    staged = prepare_sharp(tmp_path, BBB, JOB_B, _frames([0]), origin="manual", interval_ms=None, created_at=WHEN)
    with pytest.raises(YtError) as err:
        commit_sharp(tmp_path, BBB, staged)
    assert err.value.code == "E_UNKNOWN"
    assert len(read_sharp(tmp_path, BBB)["frames"]) == 3
    assert sorted(p.name for p in (tmp_path / BBB).iterdir()) == [FOLDER]


def test_sweep_removes_tmp_and_old_folders(tmp_path: Path) -> None:
    _install(tmp_path, JOB_A, [0])
    (tmp_path / BBB / f"sharp.tmp-{JOB_B}").mkdir()
    (tmp_path / BBB / "sharp.old-x").mkdir()
    (tmp_path / BBB / "storyboard").mkdir()
    (tmp_path / "loose.txt").write_text("x", encoding="utf-8")
    assert sweep_sharp_leftovers(tmp_path) == 2
    assert sorted(p.name for p in (tmp_path / BBB).iterdir()) == [FOLDER, "storyboard"]
    assert read_sharp(tmp_path, BBB) is not None


def test_sweep_restores_the_old_set_when_sharp_is_missing(tmp_path: Path) -> None:  # Review Focus 2
    _install(tmp_path, JOB_A, [0, 1000])
    (tmp_path / BBB / FOLDER).rename(tmp_path / BBB / f"sharp.old-{JOB_B}")  # ดับระหว่างสลับ: ชุดเดิมถูกย้ายออกแล้ว
    (tmp_path / BBB / f"sharp.tmp-{JOB_B}").mkdir()
    assert read_sharp(tmp_path, BBB) is None
    assert sweep_sharp_leftovers(tmp_path) == 2
    assert len(read_sharp(tmp_path, BBB)["frames"]) == 2


def test_sweep_of_a_missing_cache_root_is_zero(tmp_path: Path) -> None:
    assert sweep_sharp_leftovers(tmp_path / "nope") == 0
```

- [ ] **Step 2: Run them, expect FAIL** — `uv run pytest tests/unit/test_sharp_store.py tests/unit/test_files.py tests/unit/test_frames.py -q -W error -p no:cacheprovider` (`ModuleNotFoundError: yttoolkit.core.sharp_store`, `AttributeError: … 'plan_sharp_dir'`, `ImportError: frame_file_names`).

- [ ] **Step 3: `core/storyboard.py`** — rename the helper and keep its body:
```python
def frame_file_name(index: int) -> str:
    """ชื่อไฟล์ภาพใน cache: f_0000.jpg (ภาพคมใน cache ใช้ชื่อแบบเดียวกัน M5 รอบ B)"""
    return f"f_{index:04d}.jpg"
```
and replace the two calls `_file_name(spec.index)` / `_file_name(s.index)` with `frame_file_name(...)`.

- [ ] **Step 4: `core/frames.py`**

Add `from collections.abc import Sequence`. Replace `_missing` and `_load_cell`, and change the two public builders:
```python
def _missing(path: Path, exc: Exception, code: str = "E_NO_STORYBOARD") -> YtError:
    # ไฟล์เฟรมหาย/เสีย = ชุดภาพใน cache ไม่ครบ (ภาพเร็ว: สร้างใหม่ได้ · ภาพคม: ถูกล้างไปแล้ว กดขอใหม่)
    return YtError(code, f"{FRAME_FILE_BAD} ({type(exc).__name__}): {path}")


def _load_cell(path: Path, code: str = "E_NO_STORYBOARD") -> Image.Image:
    try:
        with Image.open(path) as source:
            image = source.convert("RGB")
    except (OSError, ValueError, SyntaxError, Image.DecompressionBombError) as exc:
        raise _missing(Path(path), exc, code) from exc
    if image.size != (CELL_W, CELL_H):
        image = ImageOps.pad(image, (CELL_W, CELL_H), color=(0, 0, 0))  # ภาพคมย่อลงช่อง ภาพเร็วขยายขึ้น
    return image


def frame_file_names(times_ms: Sequence[int]) -> list[str]:
    """frame_HH-MM-SS.jpg ตามลำดับ วินาทีเดียวกันต่อท้าย _2, _3 (ชื่อใน zip และในโฟลเดอร์ภาพคมใช้กฎเดียวกัน)"""
    seen: dict[str, int] = {}
    names: list[str] = []
    for t_ms in times_ms:
        stem = f"frame_{file_timecode(t_ms)}"
        seen[stem] = seen.get(stem, 0) + 1
        names.append(f"{stem}.jpg" if seen[stem] == 1 else f"{stem}_{seen[stem]}.jpg")
    return names
```
`contact_sheet` gets the keyword-only `missing_code: str = "E_NO_STORYBOARD"` after `columns` and calls `_load_cell(path, missing_code)`. `frames_zip` becomes:
```python
def frames_zip(frames: Frames, *, missing_code: str = "E_NO_STORYBOARD") -> bytes:
    """zip แบบไม่บีบอัด (JPEG บีบซ้ำไม่ได้ประโยชน์) ชื่อ frame_HH-MM-SS.jpg ตามลำดับเฟรม (frame_file_names)
    วันที่ในไฟล์ตายตัว จึงได้ไบต์เหมือนเดิมทุกครั้งที่ทำจากเฟรมชุดเดิม"""
    if not frames:
        raise ValueError("ไม่มีเฟรมให้ใส่ zip")
    out = io.BytesIO()
    names = frame_file_names([t_ms for t_ms, _ in frames])
    with zipfile.ZipFile(out, "w", zipfile.ZIP_STORED) as archive:
        for (_t_ms, path), name in zip(frames, names, strict=True):
            info = zipfile.ZipInfo(name, date_time=_ZIP_DATE)
            info.compress_type = zipfile.ZIP_STORED
            info.external_attr = 0o644 << 16
            try:
                data = Path(path).read_bytes()
            except OSError as exc:
                raise _missing(Path(path), exc, missing_code) from exc
            archive.writestr(info, data)
    return out.getvalue()
```

- [ ] **Step 5: `core/files.py`** — add after the `GROUP_FALLBACK` line:
```python
SHARP_DIR_SUFFIX = " - ภาพคม"  # D2: โฟลเดอร์ภาพคม "<ชื่อคลิป> - ภาพคม" ในโฟลเดอร์ของคลิป
PARTIAL_MARKER = ".yttoolkit-partial"  # อยู่ในโฟลเดอร์ภาพคมเฉพาะระหว่างย้ายไฟล์เข้า (เจอตอนเปิดโปรแกรม = ของค้าง)
_LONGEST_FRAME_NAME = "frame_000-00-00_200.jpg"  # ชื่อภาพคมยาวสุด: ชั่วโมง 3 หลัก ภาพที่ 200 ในวินาทีเดียวกัน
```
and after `plan_chapter_output`:
```python
def plan_sharp_dir(root: Path, title: str, video_id: str, group: str | None = None) -> Path:
    """โฟลเดอร์ภาพคม (ยังไม่สร้าง): <โฟลเดอร์ของคลิป>/<ชื่อ> - ภาพคม ชื่อตัดตามกฎของ plan_output แล้วตัดเพิ่มให้
    "<โฟลเดอร์> (99)/<ชื่อภาพยาวสุด>" ไม่เกิน 240 ไม่เหลือที่ = ใช้ videoId ยังยาวเกิน = E_OUTPUT_NOT_WRITABLE"""
    planned = plan_output(root, title, video_id, SHARP_DIR_SUFFIX, "jpg", group)
    folder = planned.with_name(planned.name[: -len(".jpg")])
    limit = PATH_LIMIT - UNIQUE_RESERVE - 1 - _u16(_LONGEST_FRAME_NAME)
    excess = _u16(str(folder)) - limit
    if excess > 0:
        stem = folder.name[: -len(SHARP_DIR_SUFFIX)]
        short = truncate_title(stem, _u16(stem) - excess)
        folder = folder.with_name(f"{short or video_id}{SHARP_DIR_SUFFIX}")
        if _u16(str(folder)) > limit:
            raise YtError("E_OUTPUT_NOT_WRITABLE", "path too long")
    return folder
```
and after `move_into_place`:
```python
def _dir_candidates(path: Path):
    """โฟลเดอร์เดิม แล้ว "<ชื่อ> (2)" ... "(99)" (ต่อท้ายทั้งชื่อ: โฟลเดอร์ไม่มีนามสกุล "Ep.1 - ภาพคม" จึงไม่ถูกตัดที่จุด)"""
    yield path
    for n in range(2, 100):
        yield path.with_name(f"{path.name} ({n})")


def _reserve_dir(planned: Path) -> Path:
    """จองชื่อโฟลเดอร์ด้วย mkdir แบบไม่ยอมให้มีอยู่ก่อน (atomic) หลายงานพร้อมกันจึงไม่ได้ชื่อซ้ำกัน"""
    for candidate in _dir_candidates(planned):
        try:
            candidate.mkdir()
        except FileExistsError:
            continue
        return candidate
    raise YtError("E_OUTPUT_NOT_WRITABLE", f"no free name for {planned.name}")


def move_files_into_dir(items: Sequence[tuple[Path, str]], planned: Path) -> Path:
    """ย้ายไฟล์จากโฟลเดอร์ทำงานเข้าโฟลเดอร์ใหม่ (ชื่อซ้ำต่อ (2)) คืนโฟลเดอร์จริง

    ระหว่างย้ายมี PARTIAL_MARKER อยู่ในโฟลเดอร์ ลบเมื่อครบทุกไฟล์ · พลาดหรือถูกยกเลิกกลางทาง = ลบโฟลเดอร์ที่เพิ่งสร้างทิ้ง
    ดับกลางทาง = เหลือโฟลเดอร์ที่มี marker ให้ lifecycle ล้างตอนเปิดโปรแกรม
    """
    for _src, name in items:
        if not name or Path(name).name != name or name in (".", "..", PARTIAL_MARKER):
            raise ValueError(f"bad file name: {name!r}")
    final: Path | None = None
    try:
        planned.parent.mkdir(parents=True, exist_ok=True)
        final = _reserve_dir(planned)
        marker = final / PARTIAL_MARKER
        marker.write_bytes(b"")
        for src, name in items:
            target = final / name
            try:
                os.replace(src, target)
            except OSError as err:
                if not _is_cross_device(err):
                    raise
                _copy_across_devices(src, target)
        marker.unlink()
    except BaseException as err:
        if final is not None:
            shutil.rmtree(final, ignore_errors=True)
        if isinstance(err, OSError):
            code = "E_DISK_FULL" if err.errno == errno.ENOSPC else "E_OUTPUT_NOT_WRITABLE"
            raise YtError(code, str(err)) from err
        raise
    return final
```
Add `from collections.abc import Sequence` to the imports.

- [ ] **Step 6: `core/sharp_store.py`** (new):
```python
"""ภาพคมใน cache ของแอพ (M5 รอบ B spec 5): หนึ่งชุดต่อคลิป สลับชุดแบบ atomic

โครง: <cache_root>/<video_id>/sharp/{index.json, f_0000.jpg, ...}
index.json = {"origin": "manual"|"auto", "intervalMs": int|null, "frames": [{"index","tMs","file"}], "createdAt"}
สร้างใน sharp.tmp-<jobId>/ ก่อน แล้วสลับ: sharp/ -> sharp.old-<jobId>/ · tmp -> sharp/ · ลบ old
ยกเลิกหรือดับก่อนสลับ = ชุดเดิมอยู่ครบ · ดับระหว่างสองขั้น = sweep_sharp_leftovers คืนชุดเดิมตอนเปิดโปรแกรม
ล้าง cache 30 วัน (db.purge_stale_cache) ลบทั้งโฟลเดอร์ของคลิปอยู่แล้ว · ไม่ import api/platform ไม่แตะเครือข่าย
"""

from __future__ import annotations

import errno
import json
import logging
import re
import shutil
import threading
import time
from collections.abc import Sequence
from pathlib import Path

from .inputs import VIDEO_ID
from .storyboard import frame_file_name
from .yterrors import YtError

log = logging.getLogger("yttoolkit")

FOLDER = "sharp"
INDEX = "index.json"
TMP_PREFIX = "sharp.tmp-"
OLD_PREFIX = "sharp.old-"
ORIGINS = ("manual", "auto")
# Windows: เปลี่ยนชื่อโฟลเดอร์ไม่ได้ชั่วครู่ระหว่างที่เบราว์เซอร์ยังอ่านภาพในโฟลเดอร์อยู่ ลองซ้ำได้ราว 2 วินาที
RENAME_ATTEMPTS = 20
RENAME_WAIT_S = 0.1
_JOB_ID = re.compile(r"[A-Za-z0-9-]{1,64}")
_FRAME_FILE = re.compile(r"f_\d{4,}\.jpg")

_guard = threading.Lock()
_locks: dict[str, threading.Lock] = {}


def _lock_for(video_id: str) -> threading.Lock:
    with _guard:
        return _locks.setdefault(video_id, threading.Lock())


def _clip_dir(cache_root: Path, video_id: str) -> Path:
    if not VIDEO_ID.fullmatch(video_id):
        raise ValueError(f"bad video id: {video_id!r}")
    return Path(cache_root) / video_id


def _valid(data: object, folder: Path) -> bool:
    if not isinstance(data, dict) or data.get("origin") not in ORIGINS or not isinstance(data.get("createdAt"), str):
        return False
    interval = data.get("intervalMs")
    if interval is not None and (type(interval) is not int or interval <= 0):
        return False
    frames = data.get("frames")
    if not isinstance(frames, list) or not frames:
        return False
    for frame in frames:
        if not isinstance(frame, dict):
            return False
        name = frame.get("file")
        if type(frame.get("index")) is not int or type(frame.get("tMs")) is not int or frame["tMs"] < 0:
            return False
        if not (isinstance(name, str) and _FRAME_FILE.fullmatch(name) and (folder / name).is_file()):
            return False
    return True


def read_sharp(cache_root: Path, video_id: str) -> dict | None:
    """ชุดภาพคมของคลิป ไม่มี / index เสีย / ไฟล์ภาพหาย / id ผิดรูปแบบ = None"""
    if not VIDEO_ID.fullmatch(video_id):
        return None
    folder = Path(cache_root) / video_id / FOLDER
    try:
        data = json.loads((folder / INDEX).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return data if _valid(data, folder) else None


def prepare_sharp(
    cache_root: Path,
    video_id: str,
    job_id: str,
    frames: Sequence[tuple[int, Path]],
    *,
    origin: str,
    interval_ms: int | None,
    created_at: str,
) -> Path:
    """คัดลอกภาพ (tMs, ไฟล์) เป็น f_0000.jpg ... พร้อม index.json ลง sharp.tmp-<jobId>/ (ยังไม่มีใครเห็น)"""
    if not frames:
        raise ValueError("no frames")
    if origin not in ORIGINS:
        raise ValueError(f"bad origin: {origin!r}")
    if not _JOB_ID.fullmatch(job_id):
        raise ValueError(f"bad job id: {job_id!r}")
    staged = _clip_dir(cache_root, video_id) / f"{TMP_PREFIX}{job_id}"
    shutil.rmtree(staged, ignore_errors=True)
    try:
        staged.mkdir(parents=True)
        entries = []
        for index, (t_ms, src) in enumerate(frames):
            name = frame_file_name(index)
            shutil.copyfile(src, staged / name)
            entries.append({"index": index, "tMs": int(t_ms), "file": name})
        doc = {"origin": origin, "intervalMs": interval_ms, "frames": entries, "createdAt": created_at}
        (staged / INDEX).write_text(json.dumps(doc, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    except OSError as err:
        shutil.rmtree(staged, ignore_errors=True)
        code = "E_DISK_FULL" if err.errno == errno.ENOSPC else "E_UNKNOWN"
        raise YtError(code, f"prepare sharp set: {type(err).__name__}") from err
    except BaseException:
        shutil.rmtree(staged, ignore_errors=True)
        raise
    return staged


def _rename(src: Path, dst: Path) -> None:
    for attempt in range(RENAME_ATTEMPTS):
        try:
            src.rename(dst)
            return
        except PermissionError:
            if attempt == RENAME_ATTEMPTS - 1:
                raise
            time.sleep(RENAME_WAIT_S)


def commit_sharp(cache_root: Path, video_id: str, staged: Path) -> dict:
    """สลับชุดที่เตรียมไว้เข้าที่ (แทนชุดเดิม D5) พลาด = คืนชุดเดิม ทิ้งชุดใหม่ แล้ว E_UNKNOWN"""
    clip = _clip_dir(cache_root, video_id)
    staged = Path(staged)
    if staged.parent != clip or not staged.name.startswith(TMP_PREFIX):
        raise ValueError(f"not a staged sharp set: {staged.name}")
    target = clip / FOLDER
    old = clip / f"{OLD_PREFIX}{staged.name[len(TMP_PREFIX):]}"
    with _lock_for(video_id):
        moved_old = False
        try:
            if target.exists():
                _rename(target, old)
                moved_old = True
            _rename(staged, target)
        except OSError as exc:
            if moved_old and not target.exists():
                try:
                    _rename(old, target)
                except OSError as back:
                    log.warning("คืนชุดภาพคมเดิมไม่ได้ (%s) รอให้เปิดโปรแกรมรอบหน้าคืนให้", type(back).__name__)
            discard_sharp(staged)
            raise YtError("E_UNKNOWN", f"swap sharp set: {type(exc).__name__}") from exc
        if moved_old:
            shutil.rmtree(old, ignore_errors=True)
    index = read_sharp(cache_root, video_id)
    if index is None:
        raise YtError("E_UNKNOWN", "sharp set unreadable after the swap")
    return index


def discard_sharp(staged: Path) -> None:
    shutil.rmtree(staged, ignore_errors=True)


def sweep_sharp_leftovers(cache_root: Path) -> int:
    """ตอนเปิดโปรแกรม (ยังไม่มีงานรัน): ลบ sharp.tmp-* · sharp.old-* คืนเป็น sharp/ ถ้า sharp/ หายไป (ดับกลางการสลับ)
    ไม่งั้นลบ · คืนจำนวนโฟลเดอร์ที่จัดการ"""
    try:
        clips = [p for p in Path(cache_root).iterdir() if p.is_dir()]
    except OSError:
        return 0
    count = 0
    for clip in clips:
        try:
            children = sorted(p for p in clip.iterdir() if p.is_dir())
        except OSError:
            continue
        target = clip / FOLDER
        for child in children:
            if child.name.startswith(TMP_PREFIX):
                shutil.rmtree(child, ignore_errors=True)
                count += 1
            elif child.name.startswith(OLD_PREFIX):
                if not target.exists():
                    try:
                        child.rename(target)
                        count += 1
                        continue
                    except OSError:
                        pass
                shutil.rmtree(child, ignore_errors=True)
                count += 1
    return count
```

- [ ] **Step 7: Run the tests, expect PASS** — the Step 2 command, then `uv run pytest -q -W error -p no:cacheprovider` (existing frames/zip/storyboard tests stay green: names and codes are unchanged by default).

- [ ] **Step 8: Commit**
```bash
git add src/yttoolkit/core/sharp_store.py src/yttoolkit/core/files.py src/yttoolkit/core/frames.py src/yttoolkit/core/storyboard.py tests/unit/test_sharp_store.py tests/unit/test_files.py tests/unit/test_frames.py
git commit -F- <<'EOF'
feat(sharp): cache set with atomic swap and startup sweep, sharp output folder, shared frame names

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
EOF
```

### Task 6: Web strings and types

**Files:**
- Modify: `web/src/i18n/th.ts` (C10 exactly)
- Modify: `web/src/lib/types.ts` (C11 types)
- Modify: `web/src/pages/video/frames.tsx` (`NoStoryboard` only: drop the tooltip that used `th.frames.availableLater`)
- Modify: `web/src/lib/download-options.test.ts:590`, `web/src/lib/download-prefs.test.ts:22`, `web/src/pages/settings/general-form.test.ts:19`, `web/src/pages/video/advanced/use-advanced-choice.test.ts:22` (add `autoSharpFrames: true` next to `sponsorblockDefault` in each `Settings` literal)

**Interfaces:**
- Consumes: nothing new.
- Produces: C10 strings and C11 types for T10-T13 and T15.

- [ ] **Step 1: `web/src/i18n/th.ts`** — in `frames`: replace `noStoryboard` with `noStoryboard: 'คลิปนี้ไม่มีภาพตัวอย่างแบบเร็ว กด "ขอภาพคม" แทนได้',`, delete the `availableLater` line, and add before the closing brace:
```ts
    // M5 รอบ B: ปุ่มสลับชุดภาพที่หัวส่วน (มีชุดภาพคมแล้ว)
    setLabel: "ชุดภาพเฟรม",
    setFast: "ภาพเร็ว",
    setSharp: "ภาพคม",
```
Add a new top-level object right after `frames`:
```ts
  // M5 รอบ B: ปุ่ม "ขอภาพคม" และ dialog (ปุ่มและหัว dialog ใช้ th.frames.requestSharp)
  sharp: {
    busy: "กำลังดึงภาพคม…",
    liveDisabled: "คลิปสดยังขอภาพคมไม่ได้",
    sameTimes: "เวลาเดียวกับภาพเร็ว",
    sameTimesDetail: "ทุก ~{interval} วินาที · {count} ภาพ",
    customPrefix: "ตั้งเอง ทุก",
    customUnit: "วินาที",
    customCount: "· {count} ภาพ",
    intervalError: "ใส่เลขวินาทีเต็ม 1-3600",
    size: "ต้องโหลดวิดีโอชั่วคราวราว {size} (ลบทิ้งเมื่อเสร็จ)",
    sizeUnknown: "ต้องโหลดวิดีโอชั่วคราว ไม่ทราบขนาดล่วงหน้า (ลบทิ้งเมื่อเสร็จ)",
    wide: "ภาพกว้าง 1280 px",
    tall: "ภาพสูง 1280 px",
    lowRes: "คลิปนี้มีภาพสูงสุด {h}p ภาพจะเล็กกว่าปกติ",
    overLimit: "ทุก {N} วินาทีจะได้ {count} ภาพ เกินที่ดึงได้ 200 ภาพ จะใช้ทุก {N2} วินาทีแทน",
    replaceWarning: "ภาพคมชุดเดิมในแอพจะถูกแทนด้วยชุดใหม่ (ไฟล์ในโฟลเดอร์ไม่หาย)",
    cancel: "ยกเลิก",
    start: "เริ่มดึงภาพคม",
  },
```
In `queue`, after the `choice` line:
```ts
    // M5 รอบ B: ขั้นของภาพคม (stage "extracting_frames:<i>/<n>" / "sharp_frames:<i>/<n>") และชื่องานภาพคมในแถวคิว
    extracting: "กำลังดึงภาพ {i}/{n}",
    autoSharp: "กำลังทำภาพคม {i}/{n}",
    sharpTitle: " · ภาพคม",
    sharpTitleCount: " · ภาพคม {n} ภาพ",
```
In `general`, after `audioDefault`:
```ts
    autoSharpFrames: "ทำภาพคมอัตโนมัติตอนโหลดวิดีโอ",
    autoSharpFramesHint: "ใช้ไฟล์ที่โหลดมาแล้ว ไม่ต้องโหลดเพิ่ม ใช้เวลาเพิ่มราว 10-40 วินาทีต่อคลิป",
```

- [ ] **Step 2: `web/src/lib/types.ts`**
  - `JobStage`: add `| \`extracting_frames:${number}/${number}\`` and `| \`sharp_frames:${number}/${number}\``.
  - `JobOutput`: `export type JobOutput = { index: number; name: string; sizeBytes: number; files?: number }` with the doc comment `/** ไฟล์ที่งานสร้าง: name = ชื่อไฟล์อย่างเดียว · files = งานภาพคม ผลเป็นโฟลเดอร์ (จำนวนภาพ) ไม่มีปุ่มดาวน์โหลด */`.
  - After `StoryboardFrame`/`Storyboard`: `/** ชุดภาพคมของคลิป (GET /videos/{id}/sharp) intervalMs null = เวลาเดียวกับภาพเร็ว */ export type SharpSet = { origin: "manual" | "auto"; intervalMs: number | null; frames: StoryboardFrame[] }`.
  - Replace the two `source: "fast"` params with `export type FrameSource = "fast" | "sharp"`, `ContactSheetJobParams = GroupFolder & { source: FrameSource; columns: 5 }`, `FramesZipJobParams = GroupFolder & { source: FrameSource }`, and add `/** ภาพคม (M5 รอบ B): ไม่มี intervalS = เวลาเดียวกับภาพเร็ว */ export type FramesSharpJobParams = GroupFolder & { intervalS?: number }` to `JobParams`.
  - `export type NewJob = { videoId: string; kind: JobKind; params: JobParams; title?: string }`.
  - `Settings`: add `autoSharpFrames: boolean` after `sponsorblockDefault`.

- [ ] **Step 3: `web/src/pages/video/frames.tsx`** — in `NoStoryboard` replace the comment + `<Tooltip>…</Tooltip>` block inside `<EmptyContent>` with:
```tsx
        {/* ปุ่มที่กดได้จริงมาใน M5 รอบ B ชิ้นถัดไป (T15) จนกว่าจะถึงตอนนั้นยังปิดอยู่ */}
        <Button variant="outline" disabled focusableWhenDisabled>
          {t.requestSharp}
        </Button>
```
(the `Tooltip` imports stay: `ReplayedFilterButton` and `BulkDownloads` use them).

- [ ] **Step 4: Settings literals** — add `autoSharpFrames: true,` right after the `sponsorblockDefault` property in the four test files listed above.

- [ ] **Step 5: Run the web checks, expect PASS** — `cd web && npm run typecheck && npm run lint && npm test` (no test asserts `availableLater`; `video.spec.ts` is updated in T15 and runs at the final gate).

- [ ] **Step 6: Commit**
```bash
git add web/src/i18n/th.ts web/src/lib/types.ts web/src/pages/video/frames.tsx web/src/lib/download-options.test.ts web/src/lib/download-prefs.test.ts web/src/pages/settings/general-form.test.ts web/src/pages/video/advanced/use-advanced-choice.test.ts
git commit -F- <<'EOF'
feat(web): M5-B strings and types (sharp set, frame source, folder output, autoSharpFrames)

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
EOF
```

---

## Wave 2

### Task 7: API — `frames_sharp` params, sharp sources, `GET /videos/{id}/sharp`, folder outputs

**Files:**
- Modify: `src/yttoolkit/api/jobs.py` (docstring line 4, `ContactSheetParams`, `FramesZipParams`, new `FramesSharpParams`, `PARAMS_BY_KIND`, `NewJobModel.kind`, new `sharp_problem`, `create_jobs`, `output_path`, `output_of`, `reveal_output`)
- Modify: `src/yttoolkit/api/videos.py` (`STATUS_BY_CODE`, new route, `cache_file`)
- Modify: `tests/api/test_jobs_api.py`, `tests/api/test_videos_api.py`

**Interfaces:**
- Consumes: C1 (`OutputFile.files`, `E_NO_SHARP_FRAMES`), C2 `MAX_INTERVAL_S`, C3 `FFMPEG_KINDS`, C5 `read_sharp`, `FOLDER`, `INDEX`, `prepare_sharp`/`commit_sharp` (tests).
- Produces: C6 exactly.

- [ ] **Step 1: Write the failing API tests**

`tests/api/test_jobs_api.py`: delete the two rows `{"videoId": "aqz-KE-bpKQ", "kind": "frames_sharp", "params": {}}` and `{"videoId": "aqz-KE-bpKQ", "kind": "contact_sheet", "params": {"source": "sharp"}}` from `test_post_rejects_bad_items` (both valid now), add `{"videoId": "aqz-KE-bpKQ", "kind": "contact_sheet", "params": {"source": "crisp"}}` to that list, and append:
```python
# ---------- M5 รอบ B ภาพคม ----------


def test_post_accepts_frames_sharp_and_sharp_sources(env):
    items = [
        {"videoId": "aqz-KE-bpKQ", "kind": "frames_sharp", "params": {}},
        {"videoId": "aqz-KE-bpKQ", "kind": "frames_sharp", "params": {"intervalS": 60, "folder": "งานลูกค้า"}},
        {"videoId": "aqz-KE-bpKQ", "kind": "contact_sheet", "params": {"source": "sharp", "columns": 5}},
        {"videoId": "aqz-KE-bpKQ", "kind": "frames_zip", "params": {"source": "sharp"}},
    ]
    resp = env.client().post("/api/jobs", json={"items": items}, headers=AUTH)
    assert resp.status_code == 200, resp.text
    assert [job["params"] for job in resp.json()["jobs"]] == [
        {}, {"intervalS": 60, "folder": "งานลูกค้า"}, {"source": "sharp", "columns": 5}, {"source": "sharp"}]


@pytest.mark.parametrize(
    "params",
    [{"intervalS": 0}, {"intervalS": 3601}, {"intervalS": 1.5}, {"intervalS": True}, {"intervalS": "5"},
     {"interval": 5}, {"source": "sharp"}],
)  # fmt: skip
def test_post_rejects_bad_frames_sharp_params(env, params):
    item = {"videoId": "aqz-KE-bpKQ", "kind": "frames_sharp", "params": params}
    resp = env.client().post("/api/jobs", json={"items": [item]}, headers=AUTH)
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "E_BAD_REQUEST"
    assert env.store.pending_count() == 0


def test_post_frames_sharp_checks_a_cached_probe(env, cached, monkeypatch):
    item = {"videoId": "aqz-KE-bpKQ", "kind": "frames_sharp", "params": {"intervalS": 10}}
    assert env.client(**cached).post("/api/jobs", json={"items": [item]}, headers=AUTH).status_code == 200
    uncached = {**item, "videoId": "88o5Sk8_m1Y"}
    assert env.client(**cached).post("/api/jobs", json={"items": [uncached]}, headers=AUTH).status_code == 200
    videos = cached["videos"]
    for info in ({"durationS": 0, "isLive": False}, {"durationS": 900, "isLive": True}):
        monkeypatch.setattr(videos, "peek_cached", lambda video_id, info=info: info)
        resp = env.client(**cached).post("/api/jobs", json={"items": [item]}, headers=AUTH)
        assert resp.status_code == 422
        assert resp.json()["error"]["detail"].startswith("aqz-KE-bpKQ: ")
    assert env.store.pending_count() == 2


def test_post_frames_sharp_without_ffmpeg_is_409(env):
    item = {"videoId": "aqz-KE-bpKQ", "kind": "frames_sharp", "params": {}}
    resp = env.client(media=NoFfmpeg()).post("/api/jobs", json={"items": [item]}, headers=AUTH)
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "E_FFMPEG_MISSING"


def _done_with_folder(env):
    out_root = env.tmp / "out"
    folder = out_root / "คลิป [aqz-KE-bpKQ]" / "คลิป - ภาพคม"
    folder.mkdir(parents=True)
    (folder / "frame_00-00-00.jpg").write_bytes(b"jpg")
    (job,) = env.add(1, kind="frames_sharp")
    output = OutputFile(str(out_root), "คลิป [aqz-KE-bpKQ]/คลิป - ภาพคม", 3, "folder", files=1)
    env.finish(job.id, "done", outputs=(output,))
    return job, folder


def test_folder_output_is_listed_but_not_downloadable(env):
    job, _ = _done_with_folder(env)
    client = env.client()
    listed = next(j for j in client.get("/api/jobs").json()["jobs"] if j["id"] == job.id)
    assert listed["outputs"] == [{"index": 0, "name": "คลิป - ภาพคม", "sizeBytes": 3, "files": 1}]
    assert client.get(f"/api/jobs/{job.id}/outputs/0").status_code == 404


def test_reveal_of_a_folder_output_opens_the_folder(env):
    job, folder = _done_with_folder(env)
    opened: list[Path] = []
    client = env.client(open_folder=opened.append)
    assert client.post(f"/api/jobs/{job.id}/outputs/0/reveal", headers=AUTH).status_code == 200
    assert opened == [folder.resolve()]
    assert client.app.state.ctx.plat.revealed == []
    for child in folder.iterdir():
        child.unlink()
    folder.rmdir()
    assert client.post(f"/api/jobs/{job.id}/outputs/0/reveal", headers=AUTH).status_code == 404
```
`tests/api/test_videos_api.py` (append; add `from yttoolkit.core.sharp_store import commit_sharp, prepare_sharp`):
```python
# ---------- M5 รอบ B ภาพคม ----------

COVER = FIXTURES / "media" / "cover.jpg"


def _sharp_set(client, times=(0, 60_000)) -> dict:
    staged = prepare_sharp(client.cache_root, BBB, "01900000-0000-7000-8000-0000000000aa", [(t, COVER) for t in times],
                           origin="manual", interval_ms=60_000, created_at="2026-10-05T03:00:00+00:00")  # fmt: skip
    return commit_sharp(client.cache_root, BBB, staged)


def test_sharp_set_is_listed_with_versioned_immutable_urls(api):
    client = api()
    _sharp_set(client)
    resp = client.get(f"/api/videos/{BBB}/sharp")
    assert resp.status_code == 200
    body = resp.json()
    assert body["origin"] == "manual" and body["intervalMs"] == 60_000
    assert [(f["index"], f["tMs"]) for f in body["frames"]] == [(0, 0), (1, 60_000)]
    assert re.fullmatch(rf"/api/cache/{BBB}/sharp/f_0001\.jpg\?v=\d+", body["frames"][1]["url"])
    image = client.get(body["frames"][1]["url"])
    assert image.status_code == 200 and image.headers["cache-control"] == "public, max-age=86400, immutable"
    download = client.get(body["frames"][1]["url"] + "&download=1")
    assert download.headers["content-disposition"] == 'attachment; filename="frame_00-01-00.jpg"'


def test_no_sharp_set_is_a_quiet_404(api, caplog):
    client = api()
    with caplog.at_level(logging.WARNING, logger="yttoolkit"):
        resp = client.get(f"/api/videos/{BBB}/sharp")
    assert resp.status_code == 404
    assert resp.json()["error"] == {"code": "E_NO_SHARP_FRAMES", "message": MESSAGES["E_NO_SHARP_FRAMES"], "detail": None}
    assert [r for r in caplog.records if r.levelno >= logging.WARNING] == []


def test_sharp_with_a_bad_id_is_422(api):
    resp = api().get("/api/videos/not-an-id/sharp")
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "E_INVALID_INPUT"
```

- [ ] **Step 2: Run them, expect FAIL** — `uv run pytest tests/api/test_jobs_api.py tests/api/test_videos_api.py -q -W error -p no:cacheprovider` (`frames_sharp` is still 422; `/sharp` is 404 with no envelope code).

- [ ] **Step 3: Implement `api/jobs.py`**

Docstring line 4 → `ค่าของงานแต่ละชนิด (C3 + M5 รอบ A/B) ตรวจด้วย pydantic: key ที่ไม่รู้จักและคุกกี้ = 422`. Add `from ..core.sharp import MAX_INTERVAL_S`. Replace the two frame params classes and add the sharp one:
```python
class ContactSheetParams(_Grouped):
    source: Literal["fast", "sharp"] = "fast"  # M5 รอบ B: "sharp" = ชุดภาพคมใน cache
    columns: Literal[5] = 5


class FramesZipParams(_Grouped):
    source: Literal["fast", "sharp"] = "fast"


class FramesSharpParams(_Grouped):
    """ภาพคม (M5 รอบ B): ไม่ส่ง intervalS = เวลาเดียวกับภาพเร็ว (คลิปไม่มี storyboard = ค่าเริ่มต้นของตัวทำงาน)"""

    intervalS: StrictInt | None = Field(None, ge=1, le=MAX_INTERVAL_S)
```
`PARAMS_BY_KIND` gains `"frames_sharp": FramesSharpParams`; `NewJobModel.kind` becomes `Literal["video", "audio", "subtitle", "note", "frames_sharp", "contact_sheet", "frames_zip"]` (drop the `# frames_sharp = M5` comment). After `clip_problem`:
```python
def sharp_problem(info: Mapping[str, Any] | None) -> str | None:
    """ภาพคมของคลิปที่เก็บข้อมูลไว้: คลิปสดหรือไม่รู้ความยาว = ทำไม่ได้ ไม่มีข้อมูล = None (ตัวทำงานตรวจอีกรอบ)"""
    if info is None:
        return None
    if info.get("isLive") or int(info.get("durationS") or 0) <= 0:
        return "frames_sharp needs a finished clip with a known duration"
    return None
```
In `create_jobs` replace the cached-probe loop with:
```python
        videos = ctx.videos
        if videos is not None:
            for item in body.items:
                if item.kind == "frames_sharp":
                    problem = sharp_problem(videos.peek_cached(item.videoId))
                elif "range" in item.params or item.params.get("splitChapters"):
                    problem = clip_problem(item.params, videos.peek_cached(item.videoId))
                else:
                    continue
                if problem is not None:
                    return error_response(422, "E_BAD_REQUEST", BAD_REQUEST_MESSAGE, f"{item.videoId}: {problem}")
```
`output_path` gains a keyword and the folder rule (replace the last two lines of the function body):
```python
def output_path(out: OutputFile, *, allow_folder: bool = False) -> Path | None:
    """… (keep the existing docstring) · ผลแบบโฟลเดอร์ (ภาพคม) ใช้ได้เฉพาะเมื่อ allow_folder (เปิดโฟลเดอร์ ไม่ใช่ดาวน์โหลด)"""
    …
    if not target.is_relative_to(root):
        return None
    if out.kind == "folder":
        return target if allow_folder and target.is_dir() else None
    return target if target.is_file() else None
```
`output_of(job_id: str, index: int, *, allow_folder: bool = False)` passes `allow_folder` to `output_path`. `reveal_output` becomes:
```python
    @router.post("/jobs/{job_id}/outputs/{index}/reveal")
    def reveal_output(job_id: str, index: int) -> dict:
        target = output_of(job_id, index, allow_folder=True)
        if target.is_dir():
            # ภาพคม: ผลของงานคือโฟลเดอร์ "เปิดโฟลเดอร์" จึงเปิดโฟลเดอร์นั้นเลย
            (ctx.open_folder or ctx.plat.open_folder)(target)
        else:
            (ctx.reveal or ctx.plat.reveal)(target)
        return {"ok": True}
```

- [ ] **Step 4: Implement `api/videos.py`**

Imports: add `from ..core.sharp_store import FOLDER as SHARP_FOLDER`, `from ..core.sharp_store import INDEX as SHARP_INDEX`, `from ..core.sharp_store import read_sharp`. Add `"E_NO_SHARP_FRAMES": 404,` to `STATUS_BY_CODE` (after `E_NO_SUBTITLES`). Add `_FRAME_FOLDERS = (STORYBOARD_FOLDER, SHARP_FOLDER)` under `_FRAME_FILE`. After the storyboard route:
```python
    @router.get("/videos/{video_id}/sharp", response_model=None)
    @maps_yt_errors
    def sharp(video_id: str) -> dict | JSONResponse:
        # ชุดภาพคมของคลิป (M5 รอบ B) ไม่มีชุด = 404 เงียบ ๆ (หน้าเว็บถือว่า "ยังไม่มีภาพคม" ไม่ใช่ error ไม่ต้อง log)
        if not VIDEO_ID.fullmatch(video_id):
            raise YtError("E_INVALID_INPUT", f"video id ไม่ถูกรูปแบบ: {video_id!r}")
        index = read_sharp(cache_root, video_id)
        if index is None:
            return error_response(404, "E_NO_SHARP_FRAMES", MESSAGES["E_NO_SHARP_FRAMES"])
        folder = cache_root / video_id / SHARP_FOLDER
        try:
            query = f"?v={(folder / SHARP_INDEX).stat().st_mtime_ns}"
        except OSError:
            query = ""
        return {
            "origin": index["origin"],
            "intervalMs": index["intervalMs"],
            "frames": [
                {"index": f["index"], "tMs": f["tMs"], "url": f"/api/cache/{video_id}/{SHARP_FOLDER}/{f['file']}{query}"}
                for f in index["frames"]
            ],
        }
```
In `cache_file` change `parts[0] == STORYBOARD_FOLDER` to `parts[0] in _FRAME_FOLDERS` (`_frame_download_name` already reads the `index.json` next to the frame, which has the same name in both folders).

- [ ] **Step 5: Run the tests, expect PASS** — the Step 2 command, then the full suite.

- [ ] **Step 6: Commit**
```bash
git add src/yttoolkit/api/jobs.py src/yttoolkit/api/videos.py tests/api/test_jobs_api.py tests/api/test_videos_api.py
git commit -F- <<'EOF'
feat(api): frames_sharp jobs, sharp contact sheet/zip sources, GET /videos/{id}/sharp, folder outputs open the folder

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
EOF
```

### Task 8: Manual `frames_sharp` handler and sharp contact sheet / zip

**Files:**
- Modify: `src/yttoolkit/core/handlers.py` (module docstring, imports, constants, new helpers, `_frames_sharp`, `_contact_sheet`, `_frames_zip`, `build_handlers`)
- Create: `tests/helpers_sharp.py`, `tests/unit/test_handlers_sharp.py`, `tests/integration/test_sharp_job_ffmpeg.py`

**Interfaces:**
- Consumes: C1 (`count_stage`, `valued_note`, `OutputFile.files`), C2 (`plan_sharp`, `fast_times`, `MAX_INTERVAL_S`), C3 (`sharp_choice`, `SharpPick`, `SHARP_MAX_SHORT_SIDE`), C4 (`extract_frame`, `SHARP_LONG_SIDE`), C5 (`prepare_sharp`, `commit_sharp`, `discard_sharp`, `read_sharp`, `plan_sharp_dir`, `move_files_into_dir`, `frame_file_names`, `missing_code`); M4 `_start`, `_Reporter`, `_hooks`, `_disk_checked`, `_write_note`, `_unique`.
- Produces: C7 exactly, plus `_clip_duration_s(clip) -> int` and `_extract_frames(deps, ctx, report, src, times, *, stage, dynamic_range) -> list[tuple[int, Path]]` (T14 reuses both), and the test helper module `helpers_sharp` (`SharpEnv`, `SharpDownloader`, `Ctx`, `make_job`, `BBB`, `BBB_TITLE`, `ZOO`, `NOW`, `VIDEO`, `MEDIA`, `FIXTURES`).

- [ ] **Step 1: Write the test helper** — `tests/helpers_sharp.py`:
```python
"""ตัวช่วยเทสของภาพคม (M5 รอบ B): บริการจริงบนฐานข้อมูลชั่วคราว (FakeExtractor) ตัวโหลดปลอมที่บอกขนาดไฟล์ได้
และ FakeMediaTools (ภาพคม = สำเนา cover.jpg) · ใช้ใน tests/unit/test_handlers_sharp.py, test_handlers_auto_sharp.py
และ tests/integration/test_sharp_job_ffmpeg.py (import แบบ helpers_ffmpeg)"""

from __future__ import annotations

import shutil
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

from yttoolkit.core.cancel import JobCancelled
from yttoolkit.core.db import Database
from yttoolkit.core.download import DownloadChoice, DownloadHooks, DownloadResult, MediaFacts
from yttoolkit.core.extractor import FakeExtractor
from yttoolkit.core.handlers import HandlerDeps, build_handlers
from yttoolkit.core.jobs import Job, JobResult
from yttoolkit.core.media import FakeMediaTools, MediaTools
from yttoolkit.core.subtitles import SubtitleService
from yttoolkit.core.videos import VideoService
from yttoolkit.core.yterrors import YtError

FIXTURES = Path(__file__).resolve().parent / "fixtures"
MEDIA = FIXTURES / "media"
BBB = "aqz-KE-bpKQ"  # 635 วิ ภาพเร็ว 128 ภาพ format ภาพคม = 298 (avc1 1280x720)
BBB_TITLE = "Big Buck Bunny 60fps 4K - Official Blender Foundation Short Film"
ZOO = "jNQXAC9IVRw"  # 19 วิ ไม่มี storyboard สูงสุด 240p
NOW = datetime(2026, 10, 5, 3, 0, tzinfo=UTC)
JOB_ID = "01900000-0000-7000-8000-000000000001"
PLENTY = 10**13
VIDEO = {"maxQuality": False, "splitChapters": False, "noAudio": False, "audioLanguage": "original"}


class Ctx:
    """JobContext ที่จดขั้น ความคืบหน้า ชื่องาน · cancel_on = ตั้งธงยกเลิกเมื่อถึงขั้นนี้ (เช่น "extracting_frames:2/11")"""

    def __init__(self, workdir: Path, output_root: Path, cancel_on: str | None = None) -> None:
        self.job_id = JOB_ID
        self.workdir = workdir
        self.output_root = output_root
        self.cancel_on = cancel_on
        self.stages: list[str] = []
        self.progresses: list[tuple[float | None, int | None, int | None]] = []
        self.titles: list[str] = []
        self._cancelled = False

    def stage(self, stage: str) -> None:
        self.stages.append(stage)
        if stage == self.cancel_on:
            self._cancelled = True

    def progress(self, fraction: float | None, speed_bps: int | None = None, eta_s: int | None = None) -> None:
        self.progresses.append((fraction, speed_bps, eta_s))

    def set_title(self, title: str) -> None:
        self.titles.append(title)

    def cancelled(self) -> bool:
        return self._cancelled

    def check_cancelled(self) -> None:
        if self._cancelled:
            raise JobCancelled()

    def wait(self, seconds: float) -> None:
        self.check_cancelled()


class SharpDownloader:
    """Downloader ปลอม: choose ได้ probe ของ FakeExtractor (formats_hook แก้รายการ format ได้) แล้วคัดลอกไฟล์จิ๋ว
    งานที่ format มี "+" (วิดีโอ + เสียง) ได้ video.mp4 · นอกนั้นได้ source (ค่าเริ่มต้น video-noaudio.mp4) · media = ที่รายงาน"""

    def __init__(self, fake: FakeExtractor) -> None:
        self.fake = fake
        self.source = MEDIA / "video-noaudio.mp4"
        self.media: MediaFacts | None = None
        self.formats_hook: Callable[[list[dict]], list[dict]] | None = None
        self.choices: list[DownloadChoice] = []

    def download(
        self, video_id: str, choose: Callable[[dict], DownloadChoice], workdir: Path, hooks: DownloadHooks
    ) -> DownloadResult:
        info = self.fake.probe(video_id)
        if self.formats_hook is not None:
            info["formats"] = self.formats_hook(info["formats"])
        choice = choose(info)
        self.choices.append(choice)
        hooks.on_stage("downloading_video")
        for step in (1, 2):
            if hooks.is_cancelled():
                raise JobCancelled()
            hooks.on_progress(step / 2, 1_000_000, 2 - step)
        merged = "+" in choice.format_spec
        target = Path(workdir) / "media.mp4"
        shutil.copyfile(MEDIA / "video.mp4" if merged else self.source, target)
        return DownloadResult(target, info, choice, self.media)

    def fetch(self, url: str) -> bytes:
        if url.startswith(FakeExtractor.STORYBOARD_PREFIX):
            return self.fake.fetch(url)
        raise YtError("E_NETWORK", "fake: ไม่มีภาพปก")


def make_job(kind: str, video_id: str, params: dict) -> Job:
    return Job(
        id=JOB_ID, video_id=video_id, title="", kind=kind, params=params, status="running", stage=None,
        progress=None, speed_bps=None, eta_s=None, attempt=0, bot_checks=0, position=1, error_code=None,
        error_message=None, error_detail=None, notes=(), outputs=(), created_at="2026-10-05T03:00:00.000000+00:00",
        started_at="2026-10-05T03:00:01.000000+00:00", finished_at=None,
    )  # fmt: skip


class SharpEnv:
    def __init__(self, tmp_path: Path, media: MediaTools | None = None) -> None:
        self.tmp = tmp_path
        self.db = Database(tmp_path / "app.db")
        self.db.migrate()
        self.fake = FakeExtractor(FIXTURES)
        self.videos = VideoService(self.db, self.fake, now=lambda: NOW)
        self.subtitles = SubtitleService(self.videos, self.fake.fetch_subtitle, tmp_path / "cache")
        self.downloader = SharpDownloader(self.fake)
        self.media = media if media is not None else FakeMediaTools(MEDIA)
        self.out = tmp_path / "out"
        self.cache = tmp_path / "cache"
        self.free = PLENTY
        self.deps = HandlerDeps(
            videos=self.videos,
            downloader=self.downloader,
            media=self.media,
            subtitles=self.subtitles,
            cache_root=self.cache,
            now=lambda: NOW,
            disk_free=lambda _path: self.free,
        )
        self._runs = 0

    def run(
        self, kind: str, video_id: str, params: dict, *, cancel_on: str | None = None, deps: HandlerDeps | None = None
    ) -> tuple[JobResult, Ctx]:
        self._runs += 1
        workdir = self.tmp / "work" / str(self._runs)
        workdir.mkdir(parents=True)
        ctx = Ctx(workdir, self.out, cancel_on=cancel_on)
        handler = build_handlers(deps or self.deps)[kind]
        return handler(make_job(kind, video_id, params), ctx), ctx

    def close(self) -> None:
        self.db.close()
```

- [ ] **Step 2: Write the failing handler tests** — `tests/unit/test_handlers_sharp.py`:
```python
"""งานภาพคม (M5 รอบ B C7) และ contact sheet / zip จากชุดภาพคม: ตัวโหลดปลอม + FakeMediaTools ไม่แตะเครือข่าย"""

from __future__ import annotations

import io
import logging
import zipfile
from pathlib import Path

import pytest
from helpers_sharp import BBB, BBB_TITLE, NOW, ZOO, SharpEnv
from PIL import Image

from yttoolkit.core import files, handlers
from yttoolkit.core.cancel import JobCancelled
from yttoolkit.core.jobs import JobResult
from yttoolkit.core.sharp import fast_times
from yttoolkit.core.sharp_store import read_sharp
from yttoolkit.core.yterrors import YtError


@pytest.fixture
def env(tmp_path):
    made = SharpEnv(tmp_path)
    yield made
    made.close()


def _folder(result: JobResult) -> Path:
    (out,) = result.outputs
    return Path(out.root) / out.rel


def _clip_folder(env: SharpEnv, video_id: str = BBB, title: str = BBB_TITLE) -> Path:
    return files.plan_output(env.out.resolve(), title, video_id, "", "mp4").parent


def _sharp_dirs(env: SharpEnv, video_id: str = BBB, title: str = BBB_TITLE) -> list[str]:
    folder = _clip_folder(env, video_id, title)
    return sorted(p.name for p in folder.iterdir() if p.is_dir()) if folder.exists() else []


def _cache_children(env: SharpEnv, video_id: str = BBB) -> list[str]:
    folder = env.cache / video_id
    return sorted(p.name for p in folder.iterdir()) if folder.exists() else []


def test_same_times_writes_the_cache_and_a_folder(env):
    result, ctx = env.run("frames_sharp", BBB, {})
    (out,) = result.outputs
    folder = _folder(result)
    assert out.kind == "folder" and out.files == 128
    assert folder == files.plan_sharp_dir(env.out.resolve(), BBB_TITLE, BBB)
    names = sorted(p.name for p in folder.iterdir())
    assert len(names) == 128 and names[0] == "frame_00-00-00.jpg" and files.PARTIAL_MARKER not in names
    assert out.size_bytes == sum(p.stat().st_size for p in folder.iterdir())
    index = read_sharp(env.cache, BBB)
    assert index["origin"] == "manual" and index["intervalMs"] is None
    assert index["createdAt"] == NOW.isoformat(timespec="seconds")
    assert [f["tMs"] for f in index["frames"]] == fast_times(env.videos.raw(BBB))
    extract = [f"extracting_frames:{i}/128" for i in range(1, 129)]
    assert ctx.stages == ["probing", "downloading_video", *extract, "writing"]
    assert {(call.long_side, call.dynamic_range) for call in env.media.frames} == {(1280, None)}
    assert env.downloader.choices[0].format_spec == "298"
    assert not (ctx.workdir / "media.mp4").exists()  # AC-FRAME-03: วิดีโอชั่วคราวถูกลบทันทีที่ดึงภาพเสร็จ
    assert (folder.parent / files.SOURCE_NOTE_NAME).is_file()
    assert result.notes == () and result.title == BBB_TITLE
    assert _cache_children(env) == ["sharp"]


def test_custom_interval_names_the_frames_by_time(env):
    result, ctx = env.run("frames_sharp", BBB, {"intervalS": 60})
    names = sorted(p.name for p in _folder(result).iterdir())
    assert names == [f"frame_00-{m:02d}-00.jpg" for m in range(11)]
    index = read_sharp(env.cache, BBB)
    assert index["intervalMs"] == 60_000 and [f["tMs"] for f in index["frames"]] == list(range(0, 660_000, 60_000))
    assert ctx.titles == [BBB_TITLE]
    fractions = [p[0] for p in ctx.progresses if p[0] is not None]
    assert fractions[-11:] == pytest.approx([i / 11 for i in range(11)])  # ภาพที่ i: (i-1)/n


def test_custom_interval_over_200_is_raised_with_a_note(env):
    result, _ = env.run("frames_sharp", BBB, {"intervalS": 2})
    assert result.outputs[0].files == 159
    assert result.notes == ("SHARP_INTERVAL_RAISED:4",)
    assert read_sharp(env.cache, BBB)["intervalMs"] == 4000


def test_same_times_over_200_falls_back_with_a_note(env, monkeypatch):  # Review Focus 4
    monkeypatch.setattr(handlers, "fast_times", lambda raw: list(range(0, 636_000, 3000)))
    result, _ = env.run("frames_sharp", BBB, {})
    assert result.outputs[0].files == 159
    assert result.notes == ("SHARP_INTERVAL_RAISED:4",)


def test_no_storyboard_uses_the_default_interval_and_notes_low_resolution(env):
    result, _ = env.run("frames_sharp", ZOO, {})
    assert result.outputs[0].files == 19
    assert read_sharp(env.cache, ZOO)["intervalMs"] == 1000
    assert result.notes == ("SHARP_LOW_RES:240",)
    assert env.downloader.choices[0].format_spec == "134"


def test_hdr_only_clip_is_tone_mapped(env):
    env.downloader.formats_hook = lambda formats: [{**f, "dynamic_range": "HDR10"} for f in formats]
    result, _ = env.run("frames_sharp", BBB, {"intervalS": 60})
    assert {call.dynamic_range for call in env.media.frames} == {"HDR10"}
    assert result.notes == ()


def test_frames_near_the_end_are_dropped(env):  # Review Focus 3
    env.media.frame_limit_ms = 600_000
    result, _ = env.run("frames_sharp", BBB, {"intervalS": 60})
    assert result.outputs[0].files == 10
    assert [f["tMs"] for f in read_sharp(env.cache, BBB)["frames"]][-1] == 540_000
    assert len(list(_folder(result).iterdir())) == 10


def test_zero_frames_fails_and_keeps_the_old_set(env):  # Review Focus 3
    env.run("frames_sharp", BBB, {"intervalS": 300})
    env.media.frame_limit_ms = 0
    with pytest.raises(YtError) as err:
        env.run("frames_sharp", BBB, {"intervalS": 60})
    assert err.value.code == "E_UNKNOWN"
    assert len(read_sharp(env.cache, BBB)["frames"]) == 3
    assert _sharp_dirs(env) == [files.plan_sharp_dir(env.out.resolve(), BBB_TITLE, BBB).name]
    assert _cache_children(env) == ["sharp"]


def test_cancel_during_extraction_keeps_the_previous_set(env):
    env.run("frames_sharp", BBB, {"intervalS": 300})
    with pytest.raises(JobCancelled):
        env.run("frames_sharp", BBB, {"intervalS": 60}, cancel_on="extracting_frames:2/11")
    assert len(read_sharp(env.cache, BBB)["frames"]) == 3
    assert len(_sharp_dirs(env)) == 1
    assert _cache_children(env) == ["sharp"]


def test_second_request_replaces_the_cache_and_adds_a_numbered_folder(env):
    env.run("frames_sharp", BBB, {"intervalS": 300})
    second, _ = env.run("frames_sharp", BBB, {"intervalS": 60})
    base = files.plan_sharp_dir(env.out.resolve(), BBB_TITLE, BBB).name
    assert _sharp_dirs(env) == [base, f"{base} (2)"]
    assert _folder(second).name == f"{base} (2)"
    assert read_sharp(env.cache, BBB)["intervalMs"] == 60_000


def test_disk_check_counts_the_video_and_the_frames(env):
    env.free = 1000
    with pytest.raises(YtError) as err:
        env.run("frames_sharp", BBB, {"intervalS": 60})
    assert err.value.code == "E_DISK_FULL"
    assert "170 MB" in err.value.message  # ceil(150 524 867 × 1.1) + 11 × 400 000 ไบต์
    assert env.media.frames == []


def test_live_or_unknown_duration_fails(env, monkeypatch):
    real = env.videos.get
    for patch, code in (({"isLive": True}, "E_LIVE_NOT_READY"), ({"durationS": 0}, "E_UNKNOWN")):
        monkeypatch.setattr(env.videos, "get", lambda video_id, patch=patch, **kw: {**real(video_id, **kw), **patch})
        with pytest.raises(YtError) as err:
            env.run("frames_sharp", BBB, {})
        assert err.value.code == code
    assert env.downloader.choices == []


@pytest.mark.parametrize("bad", [0, 3601, "5", True])
def test_a_broken_stored_interval_fails(env, bad):
    with pytest.raises(YtError) as err:
        env.run("frames_sharp", BBB, {"intervalS": bad})
    assert err.value.code == "E_UNKNOWN"


def test_contact_sheet_from_the_sharp_set(env):
    env.run("frames_sharp", BBB, {"intervalS": 60})
    result, ctx = env.run("contact_sheet", BBB, {"source": "sharp", "columns": 5})
    (out,) = result.outputs
    path = Path(out.root) / out.rel
    assert path == files.plan_output(env.out.resolve(), BBB_TITLE, BBB, " - contact sheet", "jpg")
    assert ctx.stages == ["probing", "converting", "writing"]
    with Image.open(path) as sheet:
        assert sheet.width == 5 * 320 + 6 * 8


def test_frames_zip_from_the_sharp_set(env):
    env.run("frames_sharp", BBB, {"intervalS": 60})
    result, _ = env.run("frames_zip", BBB, {"source": "sharp"})
    (out,) = result.outputs
    with zipfile.ZipFile(io.BytesIO((Path(out.root) / out.rel).read_bytes())) as archive:
        assert archive.namelist() == [f"frame_00-{m:02d}-00.jpg" for m in range(11)]


@pytest.mark.parametrize("kind", ["contact_sheet", "frames_zip"])
def test_sharp_source_without_a_set_fails(env, kind):
    with pytest.raises(YtError) as err:
        env.run(kind, BBB, {"source": "sharp"})
    assert err.value.code == "E_NO_SHARP_FRAMES"
    assert not _clip_folder(env).exists()


def test_a_purged_frame_file_is_no_sharp_frames(env):
    env.run("frames_sharp", BBB, {"intervalS": 60})
    (env.cache / BBB / "sharp" / "f_0003.jpg").unlink()
    with pytest.raises(YtError) as err:
        env.run("contact_sheet", BBB, {"source": "sharp", "columns": 5})
    assert err.value.code == "E_NO_SHARP_FRAMES"


def test_logs_have_no_absolute_paths(env, caplog):
    with caplog.at_level(logging.INFO, logger="yttoolkit"):
        env.run("frames_sharp", BBB, {"intervalS": 60})
    assert all(str(env.tmp) not in r.getMessage() for r in caplog.records)
```

- [ ] **Step 3: Write the failing real-ffmpeg job test** — `tests/integration/test_sharp_job_ffmpeg.py`:
```python
"""งานภาพคมทั้งงานกับ ffmpeg จริง (AC-FRAME-03): เวลาตรงตามแผน ภาพกว้าง 1280 และวิดีโอชั่วคราวถูกลบ"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
from helpers_ffmpeg import find_test_ffmpeg, requires_ffmpeg
from helpers_sharp import ZOO, SharpEnv
from PIL import Image

from yttoolkit.core.media import FfmpegTools
from yttoolkit.core.sharp_store import read_sharp

pytestmark = requires_ffmpeg


def _ffmpeg() -> str:
    found = find_test_ffmpeg()
    assert found is not None
    return found


@pytest.fixture
def env(tmp_path):
    made = SharpEnv(tmp_path, media=FfmpegTools(lambda: Path(_ffmpeg())))
    clip = tmp_path / "zoo-720.mp4"  # ZOO ยาว 19 วิในข้อมูลคลิป: ภาพที่ 0..18 วิ
    subprocess.run([_ffmpeg(), "-hide_banner", "-loglevel", "error", "-y", "-f", "lavfi",
                    "-i", "testsrc2=size=1280x720:rate=5", "-t", "19.5", "-c:v", "libx264", "-preset", "ultrafast",
                    "-pix_fmt", "yuv420p", str(clip)], check=True)  # fmt: skip
    made.downloader.source = clip
    yield made
    made.close()


def test_real_sharp_job_matches_the_plan_and_deletes_the_video(env):
    result, ctx = env.run("frames_sharp", ZOO, {})
    (out,) = result.outputs
    folder = Path(out.root) / out.rel
    files = sorted(folder.iterdir())
    assert out.files == len(files) == 19
    for path in files:
        with Image.open(path) as img:
            assert img.format == "JPEG" and img.size == (1280, 720)
    assert [f["tMs"] for f in read_sharp(env.cache, ZOO)["frames"]] == list(range(0, 19_000, 1000))
    assert not (ctx.workdir / "media.mp4").exists()
    assert result.notes == ("SHARP_LOW_RES:240",)
```

- [ ] **Step 4: Run them, expect FAIL** — `uv run pytest tests/unit/test_handlers_sharp.py tests/integration/test_sharp_job_ffmpeg.py -q -W error -p no:cacheprovider` (`KeyError: 'frames_sharp'` from `build_handlers`).

- [ ] **Step 5: Implement `core/handlers.py`**

Docstring line 1 → `"""ตัวทำงานของแต่ละชนิดงานในคิว (M4 + M5): video, audio, subtitle, note, frames_sharp, contact_sheet, frames_zip`, and add a bullet before `core/ ไม่ import …`:
```
- M5 รอบ B: frames_sharp โหลดวิดีโออย่างเดียว ≤ 720p ดึงภาพคมทีละเวลาด้วย ffmpeg ลบวิดีโอ แล้วเก็บทั้ง cache ของแอพ
  (core/sharp_store) และโฟลเดอร์ "<ชื่อคลิป> - ภาพคม" · contact sheet / zip ใช้ชุดภาพคมได้ (source "sharp")
```
Imports: `from collections.abc import Callable, Iterable, Mapping, Sequence`; extend the `.download` import with `SHARP_MAX_SHORT_SIDE, SharpPick, sharp_choice`; `.frames` with `frame_file_names`; `.jobs` with `count_stage, valued_note`; `.media` with `SHARP_LONG_SIDE`; add
```python
from .sharp import MAX_INTERVAL_S, fast_times, plan_sharp
from .sharp_store import FOLDER as SHARP_FOLDER
from .sharp_store import commit_sharp, discard_sharp, prepare_sharp, read_sharp
```
Constants after `COVER_JPEG_QUALITY`:
```python
SHARP_SIZE_FACTOR = 1.1  # spec 3.5: ที่ว่างสำหรับวิดีโอชั่วคราว = ขนาด × 1.1
SHARP_FRAME_BYTES = 400_000  # spec 3.5: เผื่อภาพคมภาพละ 400 KB
```
Add before `# ---------- ตัวทำงานแต่ละชนิด ----------`:
```python
def _clip_duration_s(clip: _Clip) -> int:
    """ความยาวคลิปเป็นวินาทีเต็มของ VideoInfo (ตัวเลขเดียวกับหน้าเว็บ แผนภาพจึงตรงกับที่ dialog บอก)
    คลิปสด = E_LIVE_NOT_READY · ไม่รู้ความยาว = E_UNKNOWN (API กันไว้แล้วถ้ามีข้อมูลคลิปใน cache ตอนส่งงาน)"""
    if clip.info.get("isLive"):
        raise YtError("E_LIVE_NOT_READY", "live clip")
    value = clip.info.get("durationS")
    if isinstance(value, bool) or not isinstance(value, int | float) or value <= 0:
        raise YtError("E_UNKNOWN", "duration unknown")
    return int(value)


def _sharp_interval(params: Mapping[str, Any]) -> int | None:
    raw = params.get("intervalS")
    if raw is None:
        return None
    if type(raw) is not int or not 1 <= raw <= MAX_INTERVAL_S:
        raise YtError("E_UNKNOWN", f"intervalS: {raw!r}")
    return raw


def _sharp_need(size: int | None, frames: int) -> int | None:
    """ที่ว่างที่ต้องมี: วิดีโอชั่วคราว × 1.1 + 400 KB ต่อภาพ · ไม่รู้ขนาดวิดีโอ = ไม่ตรวจ (กฎเดิมของ M4)"""
    if size is None:
        return None
    return math.ceil(size * SHARP_SIZE_FACTOR) + frames * SHARP_FRAME_BYTES


def _extract_frames(
    deps: HandlerDeps,
    ctx: JobContext,
    report: _Reporter,
    src: Path,
    times: Sequence[int],
    *,
    stage: str,
    dynamic_range: str | None,
) -> list[tuple[int, Path]]:
    """ภาพคมทีละเวลาลง workdir/frames (ffmpeg ครั้งละภาพ) ขั้น "<stage>:i/n" ความคืบหน้า (i-1)/n
    เวลาที่ไม่ได้ภาพ (วินาทีท้ายคลิป) ถูกข้าม · เช็กการยกเลิกก่อนทุกภาพ"""
    folder = Path(ctx.workdir) / "frames"
    folder.mkdir(parents=True, exist_ok=True)
    made: list[tuple[int, Path]] = []
    total = len(times)
    for i, t_ms in enumerate(times, start=1):
        ctx.check_cancelled()
        report.stage(count_stage(stage, i, total))
        report.fraction((i - 1) / total)
        dst = folder / f"{i:04d}.jpg"
        if deps.media.extract_frame(src, dst, t_ms, long_side=SHARP_LONG_SIDE, dynamic_range=dynamic_range,
                                    cancel=ctx.cancelled):  # fmt: skip
            made.append((t_ms, dst))
    ctx.check_cancelled()
    return made


def _created_at(deps: HandlerDeps) -> str:
    return deps.now().astimezone(UTC).isoformat(timespec="seconds")


def _publish_sharp(
    deps: HandlerDeps, job: Job, clip: _Clip, made: list[tuple[int, Path]], *, interval_s: int | None
) -> Path:
    """เก็บชุดภาพคมทั้งสองที่ (D2): เตรียมใน cache (ยังไม่มีใครเห็น) -> ย้ายภาพเข้าโฟลเดอร์ผลลัพธ์ -> สลับชุดใน cache
    พลาดตรงไหนก็ทิ้งชุดที่เตรียมไว้และลบโฟลเดอร์ใหม่ (ชุดเดิมใน cache ยังอยู่ D5) ไม่เช็กการยกเลิกระหว่างนี้: เร็วและต้องจบเป็นชุด"""
    staged = prepare_sharp(
        deps.cache_root, clip.video_id, job.id, made, origin="manual",
        interval_ms=interval_s * 1000 if interval_s is not None else None, created_at=_created_at(deps),
    )  # fmt: skip
    folder: Path | None = None
    try:
        names = frame_file_names([t_ms for t_ms, _ in made])
        items = [(path, name) for (_t_ms, path), name in zip(made, names, strict=True)]
        planned = files.plan_sharp_dir(clip.root, clip.title, clip.video_id, clip.group)
        folder = files.move_files_into_dir(items, planned)
        commit_sharp(deps.cache_root, clip.video_id, staged)
    except BaseException:
        discard_sharp(staged)
        if folder is not None:
            shutil.rmtree(folder, ignore_errors=True)  # โฟลเดอร์ที่งานนี้เพิ่งสร้าง
        raise
    return folder


def _frame_source(params: Mapping[str, Any]) -> str:
    source = params.get("source") or "fast"
    if source not in ("fast", "sharp"):
        raise YtError("E_UNKNOWN", f"source: {source!r}")
    return str(source)


def _missing_code(source: str) -> str:
    return "E_NO_SHARP_FRAMES" if source == "sharp" else "E_NO_STORYBOARD"


def _sharp_set_frames(deps: HandlerDeps, clip: _Clip, ctx: JobContext) -> list[tuple[int, Path]]:
    """ภาพของชุดภาพคมใน cache เรียงตามเวลา ชุดหาย (ล้าง cache ไปแล้ว) = E_NO_SHARP_FRAMES"""
    index = read_sharp(deps.cache_root, clip.video_id)
    if index is None:
        raise YtError("E_NO_SHARP_FRAMES", f"no sharp set for {clip.video_id}")
    folder = Path(deps.cache_root) / clip.video_id / SHARP_FOLDER
    ctx.check_cancelled()
    return [(frame["tMs"], folder / frame["file"]) for frame in index["frames"]]
```
After `_frames` (keep it) add the handler:
```python
def _frames_sharp(deps: HandlerDeps, job: Job, ctx: JobContext) -> JobResult:
    """ภาพคม (D1): แผนเวลา -> โหลดวิดีโออย่างเดียว ≤ 720p (เส้นทางโหลดเดิม: เว้นช่วง เบรก ลองใหม่ ยกเลิก)
    -> ffmpeg ทีละภาพ -> ลบวิดีโอ -> cache + โฟลเดอร์ "<ชื่อคลิป> - ภาพคม" ผลของงาน = โฟลเดอร์นั้น"""
    report = _Reporter(ctx)
    clip = _start(deps, job, ctx, report)
    duration_s = _clip_duration_s(clip)
    interval_s = _sharp_interval(job.params)
    fast = fast_times(deps.videos.raw(clip.video_id)) if interval_s is None else None
    plan = plan_sharp(duration_s, interval_s=interval_s, fast_times=fast)
    notes: list[str] = []
    if plan.raised and plan.interval_s is not None:
        notes.append(valued_note("SHARP_INTERVAL_RAISED", plan.interval_s))
    workdir = Path(ctx.workdir)
    picked: list[SharpPick] = []

    def choose(raw: dict) -> DownloadChoice:
        choice, pick = sharp_choice(raw)
        picked[:] = [pick]
        need = replace(choice, expected_bytes=_sharp_need(choice.expected_bytes, len(plan.times_ms)))
        return _disk_checked(need, (clip.root, workdir), deps.disk_free, factor=1)

    result = deps.downloader.download(clip.video_id, choose, workdir, _hooks(deps, ctx, report))
    ctx.check_cancelled()
    pick = picked[-1]
    if 0 < pick.short_side < SHARP_MAX_SHORT_SIDE:
        notes.append(valued_note("SHARP_LOW_RES", pick.short_side))
    made = _extract_frames(deps, ctx, report, result.path, plan.times_ms, stage="extracting_frames",
                           dynamic_range=pick.dynamic_range if pick.hdr else None)  # fmt: skip
    result.path.unlink(missing_ok=True)  # AC-FRAME-03: ลบวิดีโอชั่วคราวทันทีที่ดึงภาพครบ
    if not made:
        raise YtError("E_UNKNOWN", "no frames extracted")
    report.stage("writing")
    ctx.check_cancelled()
    folder = _publish_sharp(deps, job, clip, made, interval_s=plan.interval_s)
    rel = folder.relative_to(clip.root).as_posix()
    size = sum(p.stat().st_size for p in folder.iterdir() if p.is_file())
    _write_note(deps, ctx, clip, folder.parent)
    log.info("งาน %s บันทึกภาพคม %s ภาพ ที่ %s", ctx.job_id, len(made), rel)
    output = OutputFile(root=str(clip.root), rel=rel, size_bytes=size, kind="folder", files=len(made))
    return JobResult(outputs=(output,), notes=_unique(notes), title=clip.title or None)
```
Replace `_contact_sheet` / `_frames_zip` with:
```python
def _contact_sheet(deps: HandlerDeps, job: Job, ctx: JobContext) -> JobResult:
    report = _Reporter(ctx)
    clip = _start(deps, job, ctx, report)
    source = _frame_source(job.params)
    frames = _sharp_set_frames(deps, clip, ctx) if source == "sharp" else _frames(deps, clip, ctx, report)
    report.stage("converting")
    columns = int(job.params.get("columns") or 5)
    data = contact_sheet(frames, clip.title, int(clip.info.get("durationS") or 0), columns,
                         missing_code=_missing_code(source))  # fmt: skip
    ctx.check_cancelled()
    report.stage("writing")
    out = Path(ctx.workdir) / "out.jpg"
    out.write_bytes(data)
    return _finish(deps, ctx, clip, out, suffix=CONTACT_SHEET_SUFFIX, ext="jpg", kind="image")


def _frames_zip(deps: HandlerDeps, job: Job, ctx: JobContext) -> JobResult:
    report = _Reporter(ctx)
    clip = _start(deps, job, ctx, report)
    source = _frame_source(job.params)
    frames = _sharp_set_frames(deps, clip, ctx) if source == "sharp" else _frames(deps, clip, ctx, report)
    report.stage("converting")
    data = frames_zip(frames, missing_code=_missing_code(source))
    ctx.check_cancelled()
    report.stage("writing")
    out = Path(ctx.workdir) / "out.zip"
    out.write_bytes(data)
    return _finish(deps, ctx, clip, out, suffix=FRAMES_ZIP_SUFFIX, ext="zip", kind="archive")
```
`build_handlers`: docstring → `"""ตัวทำงานของทุกชนิดงาน (M4 + ตัวเลือกขั้นสูง M5 รอบ A + ภาพคม M5 รอบ B)"""` and add `"frames_sharp": bind(_frames_sharp),` to the dict (between `note` and `contact_sheet`).

- [ ] **Step 6: Run the tests, expect PASS** — the Step 4 command, then `uv run pytest -q -W error -p no:cacheprovider` (the existing `test_handlers.py` contact-sheet/zip tests pass `source: "fast"` and keep the old stages).

- [ ] **Step 7: Commit**
```bash
git add src/yttoolkit/core/handlers.py tests/helpers_sharp.py tests/unit/test_handlers_sharp.py tests/integration/test_sharp_job_ffmpeg.py
git commit -F- <<'EOF'
feat(handlers): frames_sharp job (plan, 720p video-only download, ffmpeg frames, cache + folder) and sharp contact sheet/zip

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
EOF
```

### Task 9: Lifecycle sweep of sharp leftovers (cache and output folder)

**Files:**
- Modify: `src/yttoolkit/lifecycle.py` (imports, `sweep_sharp_cache_once`, `open_services` call, `sharp_dir_pattern`, `_sweep_sharp_dirs`, `sweep_interrupted_outputs`)
- Modify: `tests/unit/test_lifecycle.py`

**Interfaces:**
- Consumes: C5 `sweep_sharp_leftovers`, `files.SHARP_DIR_SUFFIX`, `files.PARTIAL_MARKER`; M5-A `_prefixes`, `_UNIQUE`, `_clip_folders`, `keep` set.
- Produces: C9 exactly.

- [ ] **Step 1: Write the failing tests** — append to `tests/unit/test_lifecycle.py` (after the M5-A sweep tests, reusing `TITLE` and `_sweep_env`):
```python
# ---------- M5 รอบ B: ของค้างของภาพคม ----------


@pytest.mark.parametrize(
    ("name", "ours"),
    [
        (f"{TITLE} - ภาพคม", True),
        (f"{TITLE} - ภาพคม (2)", True),
        (f"{TITLE} - ภาพคม (99)", True),
        (f"{TITLE[:5]} - ภาพคม", True),  # ชื่อถูกตัดสั้นตามความยาว path
        (f"{TITLE} - ภาพคม (1)", False),
        (f"{TITLE} - ภาพคม เก่า", False),
        ("อีกคลิป - ภาพคม", False),
        (f"{TITLE}.mp4", False),
    ],
)
def test_sharp_dir_pattern(name, ours):
    assert bool(lifecycle.sharp_dir_pattern(TITLE).fullmatch(name)) is ours


def test_sweep_removes_only_partial_sharp_folders(paths):
    db, store, root, folder, _job_id = _sweep_env(paths)
    try:
        partial = folder / f"{TITLE} - ภาพคม (2)"  # ดับระหว่างย้ายภาพเข้า: ยังมี marker
        partial.mkdir()
        (partial / files.PARTIAL_MARKER).write_bytes(b"")
        (partial / "frame_00-00-00.jpg").write_bytes(b"x")
        finished = folder / f"{TITLE} - ภาพคม"  # ชุดที่เสร็จแล้ว (ไม่มี marker) แม้ไม่อยู่ในประวัติงานแล้ว
        finished.mkdir()
        (finished / "frame_00-00-00.jpg").write_bytes(b"x")
        user = folder / "ภาพของฉัน"  # โฟลเดอร์ของผู้ใช้ที่บังเอิญมี marker
        user.mkdir()
        (user / files.PARTIAL_MARKER).write_bytes(b"")
        stranded = [job.id for job in store.running()]
        store.interrupt_running("หยุดกลางคัน")
        assert lifecycle.sweep_interrupted_outputs(store, root, stranded) == 1
        assert not partial.exists() and finished.exists() and user.exists()
    finally:
        db.close()


def test_sweep_keeps_a_done_jobs_sharp_folder(paths):
    db, store, root, folder, _job_id = _sweep_env(paths)
    try:
        kept = folder / f"{TITLE} - ภาพคม (3)"
        kept.mkdir()
        (kept / files.PARTIAL_MARKER).write_bytes(b"")
        (done,) = store.add([NewJob("aqz-KE-bpKQ", "frames_sharp", {}, TITLE)])
        store.transition(done.id, "running")
        output = OutputFile(str(root), f"{folder.name}/{kept.name}", 0, "folder", files=0)
        store.transition(done.id, "done", outputs=(output,))
        stranded = [job.id for job in store.running()]
        store.interrupt_running("หยุดกลางคัน")
        assert lifecycle.sweep_interrupted_outputs(store, root, stranded) == 0
        assert kept.exists()
    finally:
        db.close()


def test_open_services_sweeps_sharp_leftovers_in_the_cache(paths, fake_platform):
    clip = paths.cache / "aqz-KE-bpKQ"
    stale = clip / "sharp.tmp-01900000-0000-7000-8000-000000000001"
    stale.mkdir(parents=True)
    services = lifecycle.open_services(paths, fake_platform, fake=True)
    try:
        assert not stale.exists()
    finally:
        services.db.close()


def test_sharp_cache_sweep_failure_is_logged_not_raised(paths, fake_platform, monkeypatch, caplog):
    def broken(cache_root):
        raise RuntimeError("boom")

    monkeypatch.setattr(lifecycle, "sweep_sharp_leftovers", broken)
    with caplog.at_level(logging.ERROR, logger="yttoolkit"):
        services = lifecycle.open_services(paths, fake_platform, fake=True)
    try:
        assert any("ภาพคม" in r.getMessage() for r in caplog.records)
    finally:
        services.db.close()
```

- [ ] **Step 2: Run them, expect FAIL** — `uv run pytest tests/unit/test_lifecycle.py -q -W error -p no:cacheprovider` (`AttributeError: module 'yttoolkit.lifecycle' has no attribute 'sharp_dir_pattern'`).

- [ ] **Step 3: Implement `lifecycle.py`**

Add the import `from .core.sharp_store import sweep_sharp_leftovers` (next to the other `.core` imports). In `open_services`, right after `purge_cache_once(db, paths.cache)` add `sweep_sharp_cache_once(paths.cache)`. Add after `purge_cache_once`:
```python
def sweep_sharp_cache_once(cache_root: Path) -> None:
    """ตอนเปิดโปรแกรม (ยังไม่มีงานรัน): ล้างชุดภาพคมที่เตรียมค้าง/สลับค้างใน cache (M5 รอบ B) พลาดแค่บันทึก log"""
    try:
        count = sweep_sharp_leftovers(cache_root)
        if count:
            log.info("จัดการภาพคมที่ค้างใน cache แล้ว %s โฟลเดอร์", count)
    except Exception:
        log.exception("ล้างภาพคมที่ค้างใน cache ไม่สำเร็จ (ข้ามไปก่อน)")
```
After `toolkit_name_pattern`:
```python
def sharp_dir_pattern(prefix: str) -> re.Pattern[str]:
    """ชื่อโฟลเดอร์ภาพคมที่ตัวทำงานสร้างได้ในโฟลเดอร์ของคลิป (files.plan_sharp_dir): <ชื่อ (ตัดสั้นได้)> - ภาพคม[ (N)]"""
    return re.compile(rf"{_prefixes(prefix)}{re.escape(files.SHARP_DIR_SUFFIX)}{_UNIQUE}")


def _sweep_sharp_dirs(folder: Path, ours: re.Pattern[str], keep: set[str]) -> int:
    """ลบโฟลเดอร์ภาพคมที่ย้ายภาพเข้าไม่ครบ: ชื่อตรงแบบ ยังมี PARTIAL_MARKER และไม่ใช่ผลของงานที่เสร็จแล้ว
    โฟลเดอร์ที่ไม่มี marker (ชุดที่เสร็จ ชุดที่ผู้ใช้แก้แล้ว) ไม่ถูกแตะเสมอ"""
    try:
        children = list(folder.iterdir())
    except FileNotFoundError:
        return 0
    except OSError as exc:
        log.warning("อ่านโฟลเดอร์ผลลัพธ์ไม่ได้ตอนล้างภาพคมค้าง: %s", type(exc).__name__)
        return 0
    removed = 0
    for child in children:
        if not ours.fullmatch(child.name) or os.path.normcase(str(child)) in keep:
            continue
        try:
            if child.is_symlink() or not child.is_dir() or not (child / files.PARTIAL_MARKER).is_file():
                continue
        except OSError:
            continue
        shutil.rmtree(child, ignore_errors=True)
        removed += 1
    return removed
```
Add `import shutil` to the imports. In `sweep_interrupted_outputs`, directly after `removed += _sweep_folder(folder, toolkit_name_pattern(prefix), keep)` add:
```python
                removed += _sweep_sharp_dirs(folder, sharp_dir_pattern(prefix), keep)
```
and add one line to its docstring: `โฟลเดอร์ภาพคม "<ชื่อ> - ภาพคม[ (N)]" ที่ยังมี .yttoolkit-partial (ดับระหว่างย้ายภาพเข้า) ลบทั้งโฟลเดอร์ (M5 รอบ B)`.

- [ ] **Step 4: Run the tests, expect PASS** — the Step 2 command, then the full suite.

- [ ] **Step 5: Commit**
```bash
git add src/yttoolkit/lifecycle.py tests/unit/test_lifecycle.py
git commit -F- <<'EOF'
feat(lifecycle): sweep sharp leftovers (cache tmp/old sets, partial sharp output folders)

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
EOF
```

### Task 10: W2 frames grid — fast/sharp switch, bulk source, refresh when a job finishes

**Files:**
- Modify: `web/src/pages/video/frames.tsx` (imports, `BulkDownloads`, new `FrameSetToggle`, `FramesSection`)
- Modify: `web/src/pages/video/queries.ts`, `web/src/pages/video/queries.test.ts` (`sharpQuery`)
- Create: `web/src/pages/video/frame-set.ts`, `web/src/pages/video/frame-set.test.ts`
- Modify: `web/src/lib/events.ts`, `web/src/lib/events.test.ts` (`sharpRefreshTarget`, invalidation)
- Create: `web/e2e/sharp-grid.spec.ts`

**Interfaces:**
- Consumes: C10 (`th.frames.setLabel|setFast|setSharp`), C11 types (`SharpSet`, `FrameSource`), C2 `sharpKey`; existing `FrameGrid`, `ReplayedFilterButton`, `replayedFrameIndexes`, `ToggleGroup`.
- Produces: C11 `sharpQuery`, `frameSetShown`, `sharpRefreshTarget`; `BulkDownloads({ videoId, source })` (T15 places the "ขอภาพคม" button right after it).

- [ ] **Step 1: Write the failing unit tests**

`web/src/pages/video/frame-set.test.ts`:
```ts
import { describe, expect, it } from "vitest"

import { frameSetShown } from "./frame-set"

describe("frameSetShown (spec 2)", () => {
  it("no sharp set: fast, whatever was chosen", () => {
    expect(frameSetShown({ hasFast: true, hasSharp: false, chosen: null })).toBe("fast")
    expect(frameSetShown({ hasFast: true, hasSharp: false, chosen: "sharp" })).toBe("fast")
  })
  it("no fast set (no storyboard): sharp", () => {
    expect(frameSetShown({ hasFast: false, hasSharp: true, chosen: "fast" })).toBe("sharp")
  })
  it("both: sharp by default, the user's choice wins", () => {
    expect(frameSetShown({ hasFast: true, hasSharp: true, chosen: null })).toBe("sharp")
    expect(frameSetShown({ hasFast: true, hasSharp: true, chosen: "fast" })).toBe("fast")
  })
})
```
Append to `web/src/pages/video/queries.test.ts` (extend the import with `sharpQuery`):
```ts
async function observe<T>(client: QueryClient, options: ReturnType<typeof sharpQuery>) {
  const observer = new QueryObserver(client, options)
  const unsubscribe = observer.subscribe(() => undefined)
  await vi.waitFor(() => expect(observer.getCurrentResult().isFetching).toBe(false))
  const result = observer.getCurrentResult()
  unsubscribe()
  return result as { data: T | undefined; error: unknown }
}

describe("sharpQuery", () => {
  it("uses the shared key and the sharp route", async () => {
    const fetch = stubFetch(200, { origin: "manual", intervalMs: 60000, frames: [] })
    expect(sharpQuery("aqz-KE-bpKQ", true).queryKey).toEqual(["sharp", "aqz-KE-bpKQ"])
    await observe(new QueryClient(), sharpQuery("aqz-KE-bpKQ", true))
    expect(fetch).toHaveBeenCalledWith("/api/videos/aqz-KE-bpKQ/sharp", expect.anything())
  })

  it("404 = no sharp set yet (null), not an error", async () => {
    stubFetch(404, envelope("E_NO_SHARP_FRAMES"))
    const result = await observe(new QueryClient(), sharpQuery("aqz-KE-bpKQ", true))
    expect(result.data).toBeNull()
    expect(result.error).toBeNull()
  })

  it("other failures stay errors", async () => {
    stubFetch(502, envelope("E_NETWORK"))
    const result = await observe(new QueryClient(), sharpQuery("aqz-KE-bpKQ", true))
    expect(result.error).toMatchObject({ code: "E_NETWORK" })
  })
})
```
Append to `web/src/lib/events.test.ts` (extend the import from `./events` with `sharpRefreshTarget`):
```ts
describe("sharpRefreshTarget", () => {
  const sharpJob: Job = { ...JOB, kind: "frames_sharp", params: {} }
  it("a frames_sharp or video job that just finished refreshes its clip", () => {
    expect(sharpRefreshTarget({ ...sharpJob, status: "running" }, { ...sharpJob, status: "done" })).toBe("aqz-KE-bpKQ")
    expect(sharpRefreshTarget({ ...JOB, status: "running" }, { ...JOB, status: "done" })).toBe("aqz-KE-bpKQ")
  })
  it("anything else does not", () => {
    expect(sharpRefreshTarget({ ...sharpJob, status: "done" }, { ...sharpJob, status: "done" })).toBeNull()
    expect(sharpRefreshTarget({ ...sharpJob, status: "running" }, { ...sharpJob, status: "failed" })).toBeNull()
    const zip: Job = { ...JOB, kind: "frames_zip", params: { source: "sharp" } }
    expect(sharpRefreshTarget({ ...zip, status: "running" }, { ...zip, status: "done" })).toBeNull()
  })
  it("connectEvents invalidates ['sharp', id] when such a job finishes", () => {
    const client = new QueryClient()
    client.setQueryData(JOBS_KEY, [{ ...sharpJob, status: "running" }])
    const spy = vi.spyOn(client, "invalidateQueries")
    const { source } = connect(client)
    source.emit("job.updated", { id: JOB.id, status: "done" })
    expect(spy).toHaveBeenCalledWith({ queryKey: ["sharp", "aqz-KE-bpKQ"] })
  })
})
```

- [ ] **Step 2: Run them, expect FAIL** — `cd web && npm test -- frame-set queries events` (missing modules / exports).

- [ ] **Step 3: Implement the pure parts**

`web/src/pages/video/frame-set.ts`:
```ts
import type { FrameSource } from "@/lib/types"

/**
 * ชุดภาพที่ส่วนภาพเฟรมแสดง (spec 2): ไม่มีชุดภาพคม = ภาพเร็ว · ไม่มีภาพเร็ว (ไม่มี storyboard) = ภาพคม
 * มีทั้งสองชุด = ที่ผู้ใช้กดเลือกไว้ในรอบที่เปิดหน้านี้ ยังไม่เคยเลือก = ภาพคม (ชุดใหม่ที่เพิ่งเสร็จจึงขึ้นเอง)
 */
export function frameSetShown(o: { hasFast: boolean; hasSharp: boolean; chosen: FrameSource | null }): FrameSource {
  if (!o.hasSharp) return "fast"
  if (!o.hasFast) return "sharp"
  return o.chosen ?? "sharp"
}
```
`web/src/pages/video/queries.ts`: extend the imports (`ApiError` from `@/lib/api`, `sharpKey` from `@/lib/sharp-frames`, `SharpSet` from `@/lib/types`) and append:
```ts
/**
 * ชุดภาพคมของคลิป (M5 รอบ B): 404 = ยังไม่มีชุด คืน null (ไม่ใช่ error) · ข่าว SSE ของงานภาพคม/วิดีโอที่เสร็จสั่งโหลดใหม่
 * URL ภาพมี ?v= อยู่แล้ว เก็บผลไว้สั้น ๆ เหมือน storyboard
 */
export function sharpQuery(videoId: string, enabled: boolean) {
  return queryOptions({
    queryKey: sharpKey(videoId),
    queryFn: async ({ signal }): Promise<SharpSet | null> => {
      try {
        return await api<SharpSet>(`/videos/${videoId}/sharp`, { signal })
      } catch (error) {
        if (error instanceof ApiError && error.status === 404) return null
        throw error
      }
    },
    enabled,
    retry: false,
    staleTime: 60_000,
  })
}
```
`web/src/lib/events.ts`: import `sharpKey` from `./sharp-frames`, add:
```ts
/** งานที่ทำให้ชุดภาพคมของคลิปเปลี่ยนได้: งานภาพคม และงานวิดีโอ (ภาพคมอัตโนมัติ) เพิ่งเสร็จ → videoId ที่ต้องโหลดชุดใหม่ */
export function sharpRefreshTarget(before: Job | undefined, after: Job): string | null {
  if (after.status !== "done" || before?.status === "done") return null
  return after.kind === "frames_sharp" || after.kind === "video" ? after.videoId : null
}
```
and inside `connectEvents`' handler replace the two lines after `applyServerEvent` with:
```ts
      const { before, after } = applyServerEvent(client, event)
      if (after !== undefined && before?.status !== after.status) {
        const refresh = sharpRefreshTarget(before, after)
        if (refresh !== null) void client.invalidateQueries({ queryKey: sharpKey(refresh) })
        opts.onJobChange?.(before, after)
      }
```

- [ ] **Step 4: Run them, expect PASS** — `cd web && npm test -- frame-set queries events`.

- [ ] **Step 5: Implement `frames.tsx`**

Imports: add `ToggleGroup, ToggleGroupItem` from `@/components/ui/toggle-group`; change the type import to `import type { FrameSource, ReplaySegment, StoryboardFrame } from "@/lib/types"`; add `import { frameSetShown } from "./frame-set"` and `sharpQuery` to the `./queries` import.

`BulkDownloads` takes the source:
```tsx
/** ปุ่มโหลดทั้งชุด: ส่งงานเข้าคิว (ไฟล์ลงโฟลเดอร์ปลายทาง) ใช้ชุดภาพที่เห็นอยู่ (source) ตัวกรองไม่มีผล ทุกภาพเสมอ */
function BulkDownloads({ videoId, source }: { videoId: string; source: FrameSource }) {
```
and its `enqueue` call becomes:
```tsx
      await enqueue([
        kind === "sheet"
          ? { videoId, kind: "contact_sheet", params: { source, columns: 5 } }
          : { videoId, kind: "frames_zip", params: { source } },
      ])
```
Add above `type Bulk`:
```tsx
/** ปุ่มสลับ [ภาพเร็ว | ภาพคม] (มีทั้งสองชุดเท่านั้น) · กดปุ่มที่เลือกอยู่ซ้ำไม่ทำอะไร (ต้องมีชุดที่เลือกเสมอ) */
function FrameSetToggle({ value, onChange }: { value: FrameSource; onChange: (next: FrameSource) => void }) {
  return (
    <ToggleGroup
      aria-label={t.setLabel}
      variant="outline"
      size="sm"
      spacing={0}
      value={[value]}
      onValueChange={(next) => {
        const picked = next[0]
        if (picked === "fast" || picked === "sharp") onChange(picked)
      }}
    >
      <ToggleGroupItem value="fast" className={`px-3 ${TOUCH}`}>
        {t.setFast}
      </ToggleGroupItem>
      <ToggleGroupItem value="sharp" className={`px-3 ${TOUCH}`}>
        {t.setSharp}
      </ToggleGroupItem>
    </ToggleGroup>
  )
}
```
Replace `FramesSection`'s body from `const frames = useMemo(…)` down to the end of the component with:
```tsx
  const fastFrames = useMemo(() => storyboard.data?.frames ?? [], [storyboard.data])
  const sharpFrames = useMemo(() => sharp.data?.frames ?? [], [sharp.data])
  // ชุดที่ผู้ใช้กดเลือกเองในรอบที่เปิดหน้านี้ (ของคลิปนี้เท่านั้น ไม่จำข้ามการโหลดหน้า spec 2)
  const [chosen, setChosen] = useState<{ videoId: string; source: FrameSource } | null>(null)
  const hasFast = storyboard.isSuccess && fastFrames.length > 0
  const hasSharp = sharpFrames.length > 0
  const shown = frameSetShown({ hasFast, hasSharp, chosen: chosen?.videoId === videoId ? chosen.source : null })
  const frames = shown === "sharp" ? sharpFrames : fastFrames
  // ภาพที่มีป้าย "ดูซ้ำบ่อย" (รวมภาพแทนของช่วงสั้นที่ไม่มีภาพอยู่ข้างใน) คิดครั้งเดียวต่อชุดภาพที่เห็น
  const marked = useMemo(() => replayedFrameIndexes(frames, mostReplayed), [frames, mostReplayed])
  // ?replayed=1 แต่คลิปไม่มีช่วงหรือไม่มีภาพในช่วง = ไม่สนใจ (เห็นทุกภาพ ไม่มีปุ่ม)
  const filtered = replayed && marked.length > 0
  const unfilter = useCallback(() => update({ replayed: false }), [update])
  const noStoryboard =
    (storyboard.isError && storyboard.error instanceof ApiError && storyboard.error.code === "E_NO_STORYBOARD") ||
    (storyboard.isSuccess && fastFrames.length === 0)
  // รอคำตอบภาพคมก่อนแสดงภาพเร็ว: คลิปที่มีภาพคมเปิดมาที่ภาพคมเลยไม่กระพริบ (ขอภาพคมพลาด = แสดงภาพเร็วตามเดิม)
  const gridShown = shown === "sharp" || (!sharp.isPending && hasFast)

  const grid = (
    <FrameGrid
      frames={frames}
      videoId={videoId}
      at={at}
      marked={marked}
      filtered={filtered}
      onUnfilter={unfilter}
      onViewSubs={onViewSubs}
    />
  )
  let body
  if (gridShown) body = grid
  else if (sharp.isPending) body = <FrameSkeleton />
  else if (noStoryboard) body = <NoStoryboard />
  else if (storyboard.isError) {
    body = <LoadError title={t.loadError} error={storyboard.error} onRetry={() => void storyboard.refetch()} />
  } else body = <FrameSkeleton />

  return (
    <section aria-labelledby="frames-title">
      <Card>
        {/* จอแคบ: หัวข้อ แถวปุ่มโหลด และคำแนะนำ เรียงกันคนละบรรทัด หัวข้อจะได้ไม่ถูกบีบจนขึ้นบรรทัดใหม่ */}
        <CardHeader className="max-sm:grid-cols-1!">
          <CardTitle>
            <h2 id="frames-title" className="text-base font-medium">
              {t.title}
            </h2>
          </CardTitle>
          {/* บอกว่าภาพเฟรมทำอะไรได้บ้าง (คลิกดูใหญ่ / คลิกขวาคัดลอก-โหลด) คนที่ไม่รู้ว่าคลิกขวาได้จะได้เจอ */}
          {gridShown && <CardDescription className="sm:col-span-1">{t.hint}</CardDescription>}
          {gridShown && (
            <CardAction className="max-sm:col-start-1 max-sm:row-span-1 max-sm:row-start-2 max-sm:justify-self-start">
              {/* ตัวกรองไม่มีผลกับไฟล์ที่โหลด: .zip และภาพรวมเฟรมได้ทุกภาพของชุดที่เห็นเสมอ */}
              <div className="flex flex-wrap items-center gap-2">
                {hasFast && hasSharp && (
                  <FrameSetToggle value={shown} onChange={(source) => setChosen({ videoId, source })} />
                )}
                {marked.length > 0 && (
                  <ReplayedFilterButton
                    count={marked.length}
                    pressed={filtered}
                    // เปิดตัวกรอง = ล้างเวลาที่ไฮไลต์ไว้ (?at=) ในก้าวเดียวกัน ไม่งั้นภาพของเวลานั้นที่อยู่นอกช่วง
                    // จะทำให้ตัวกรองปิดตัวเองทันที (ปุ่มดูเหมือนกดไม่ติด) · ปิดตัวกรองไม่แตะเวลา
                    onToggle={() => update(filtered ? { replayed: false } : { replayed: true, at: null })}
                  />
                )}
                <BulkDownloads videoId={videoId} source={shown} />
              </div>
            </CardAction>
          )}
        </CardHeader>
        <CardContent className="flex flex-col gap-3">{body}</CardContent>
      </Card>
    </section>
  )
}
```
Above that block, keep the existing first lines of `FramesSection` and add `const sharp = useQuery(sharpQuery(videoId, enabled))` right after the storyboard query. `FrameGrid` keeps no `key`: switching sets keeps the `?at=` "already revealed" memory, so the focus is not pulled away from the toggle (the lightbox closes itself when the frame list changes).

- [ ] **Step 6: Write the chromium e2e spec** — `web/e2e/sharp-grid.spec.ts`:
```ts
/// <reference lib="dom" />
import path from "node:path"

import AxeBuilder from "@axe-core/playwright"
import { expect, test, type Page } from "@playwright/test"

import type { SharpSet } from "../src/lib/types"

import { mockEnqueue } from "./queue-helpers"

/**
 * M5 รอบ B ส่วนภาพเฟรมเมื่อมีชุดภาพคม (โปรเจกต์ chromium: ชุดภาพคมจำลองด้วย page.route ไม่มีงานจริง)
 * ภาพของชุดจำลองคือ tests/fixtures/media/cover.jpg ทุกภาพ เวลาของภาพทุก 60 วินาที (ต่างจากภาพเร็วที่ทุก ~5 วินาที)
 */

const BBB = "aqz-KE-bpKQ"
const ZOO = "jNQXAC9IVRw"
const COVER = path.join(import.meta.dirname, "../../tests/fixtures/media/cover.jpg")
const FRAME_LIST = "รายการภาพเฟรม"
const FAST_COUNT = 128
const MINUTES = Array.from({ length: 11 }, (_, i) => i * 60_000)

function sharpSet(videoId: string, times: number[]): SharpSet {
  return {
    origin: "manual",
    intervalMs: 60_000,
    frames: times.map((tMs, index) => ({
      index,
      tMs,
      url: `/api/cache/${videoId}/sharp/f_${String(index).padStart(4, "0")}.jpg?v=1`,
    })),
  }
}

async function mockSharp(page: Page, videoId: string, times: number[]) {
  await page.route(`**/api/videos/${videoId}/sharp`, (route) => route.fulfill({ json: sharpSet(videoId, times) }))
  await page.route(`**/api/cache/${videoId}/sharp/**`, (route) => route.fulfill({ path: COVER, contentType: "image/jpeg" }))
}

const items = (page: Page) => page.getByRole("list", { name: FRAME_LIST }).getByRole("listitem")
const toggle = (page: Page) => page.getByRole("group", { name: "ชุดภาพเฟรม" })

async function seriousViolations(page: Page) {
  const results = await new AxeBuilder({ page }).analyze()
  return results.violations.filter((v) => v.impact === "serious" || v.impact === "critical").map((v) => v.id)
}

test("ยังไม่มีชุดภาพคม: ไม่มีปุ่มสลับ แสดงภาพเร็วครบ", async ({ page }) => {
  await page.goto(`/v/${BBB}`)
  await expect(items(page)).toHaveCount(FAST_COUNT)
  await expect(toggle(page)).toHaveCount(0)
})

test("มีชุดภาพคม: เปิดมาที่ภาพคม · สลับไปภาพเร็วและกลับได้", async ({ page }) => {
  await mockSharp(page, BBB, MINUTES)
  await page.goto(`/v/${BBB}`)
  await expect(items(page)).toHaveCount(11)
  await expect(toggle(page).getByRole("button", { name: "ภาพคม" })).toHaveAttribute("aria-pressed", "true")
  await toggle(page).getByRole("button", { name: "ภาพเร็ว" }).click()
  await expect(items(page)).toHaveCount(FAST_COUNT)
  await toggle(page).getByRole("button", { name: "ภาพคม" }).click()
  await expect(items(page)).toHaveCount(11)
  await expect(page.getByRole("button", { name: "ภาพเฟรมที่ 00:10:00" })).toBeVisible()
})

test("เมนูคลิกขวาของภาพคมครบทุกรายการ และ 'คัดลอกเวลา' ใช้เวลาของภาพคม", async ({ page, context }) => {
  await context.grantPermissions(["clipboard-read", "clipboard-write"])
  await mockSharp(page, BBB, MINUTES)
  await page.goto(`/v/${BBB}`)
  await page.getByRole("button", { name: "ภาพเฟรมที่ 00:01:00" }).click({ button: "right" })
  const menu = page.getByRole("menu")
  await expect(menu.getByRole("menuitem")).toHaveText([
    "คัดลอกภาพ", "โหลดภาพนี้", "คัดลอกเวลา", "คัดลอกลิงก์ช่วงนี้", "เปิดในยูทูปตรงเวลานี้", "เล่นจากตรงนี้",
    "ตั้งเป็นจุดเริ่ม", "ตั้งเป็นจุดจบ",
  ])
  await menu.getByRole("menuitem", { name: "คัดลอกเวลา" }).click()
  expect(await page.evaluate(() => navigator.clipboard.readText())).toBe("00:01:00")
})

test("?at= ไฮไลต์ภาพคมที่ใกล้เวลานั้นที่สุด", async ({ page }) => {
  await mockSharp(page, BBB, MINUTES)
  await page.goto(`/v/${BBB}?at=125000`)
  await expect(page.getByRole("button", { name: "ภาพเฟรมที่ 00:02:00" })).toHaveAttribute("aria-current", "true")
})

test("ปุ่มโหลดทั้งชุดส่ง source ตามชุดที่เห็นอยู่", async ({ page }) => {
  const queue = await mockEnqueue(page)
  await mockSharp(page, BBB, MINUTES)
  await page.goto(`/v/${BBB}`)
  await expect(items(page)).toHaveCount(11)
  await page.getByRole("button", { name: "โหลดภาพรวมเฟรม" }).click()
  await expect.poll(() => queue.bodies.length).toBe(1)
  await toggle(page).getByRole("button", { name: "ภาพเร็ว" }).click()
  await page.getByRole("button", { name: "โหลดทั้งหมด (.zip)" }).click()
  await expect.poll(() => queue.bodies.length).toBe(2)
  expect(queue.bodies.map((sent) => [sent[0].kind, sent[0].params])).toEqual([
    ["contact_sheet", { source: "sharp", columns: 5 }],
    ["frames_zip", { source: "fast" }],
  ])
})

test("คลิปไม่มี storyboard แต่มีภาพคม: แสดงภาพคม ไม่มีปุ่มสลับ", async ({ page }) => {
  await mockSharp(page, ZOO, [0, 5000, 10_000, 15_000])
  await page.goto(`/v/${ZOO}`)
  await expect(items(page)).toHaveCount(4)
  await expect(toggle(page)).toHaveCount(0)
  await expect(page.getByText("คลิปนี้ไม่มีภาพตัวอย่างแบบเร็ว", { exact: false })).toHaveCount(0)
})

for (const scheme of ["dark", "light"] as const) {
  test(`axe: ส่วนภาพเฟรมที่มีปุ่มสลับไม่มีปัญหาระดับ serious/critical (${scheme})`, async ({ page }) => {
    await page.emulateMedia({ colorScheme: scheme })
    await mockSharp(page, BBB, MINUTES)
    await page.goto(`/v/${BBB}`)
    await expect(toggle(page)).toBeVisible()
    expect(await seriousViolations(page)).toEqual([])
  })
}

test("หน้าต่างแคบ 640 px: ปุ่มสลับกับปุ่มโหลดไม่ล้นแนวนอน", async ({ page }) => {
  await page.setViewportSize({ width: 640, height: 800 })
  await mockSharp(page, BBB, MINUTES)
  await page.goto(`/v/${BBB}`)
  await expect(toggle(page)).toBeVisible()
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(640)
})
```

- [ ] **Step 7: Run the web checks, expect PASS** — `cd web && npm run typecheck && npm run lint && npm test` (the spec runs at gate 2 / the final gate).

- [ ] **Step 8: Commit**
```bash
git add web/src/pages/video/frames.tsx web/src/pages/video/queries.ts web/src/pages/video/queries.test.ts web/src/pages/video/frame-set.ts web/src/pages/video/frame-set.test.ts web/src/lib/events.ts web/src/lib/events.test.ts web/e2e/sharp-grid.spec.ts
git commit -F- <<'EOF'
feat(web): fast/sharp frame sets in W2 (toggle, bulk source, refresh when a sharp or video job finishes)

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
EOF
```

### Task 11: "ขอภาพคม" button and dialog component

**Files:**
- Create: `web/src/components/ui/radio-group.tsx`
- Create: `web/src/pages/video/sharp-request.ts`, `web/src/pages/video/sharp-request.test.ts`
- Create: `web/src/pages/video/sharp-dialog.tsx`

**Interfaces:**
- Consumes: C2 (`sharpDialogModel`, `defaultCustomText`, `SharpFast`, `SharpMode`, `SharpResolution`), C10 strings, `useEnqueue`/`jobsQuery` (`web/src/lib/jobs.ts`), `formatBytes`, shadcn `Dialog`, `Input`, `FieldError`, `Tooltip`, `Spinner`, `@base-ui/react/radio-group` + `radio`.
- Produces: C11 `SharpRequestButton`, `sharpJobBusy`, `sharpBlock` (mounted by T15).

- [ ] **Step 1: Write the failing unit test** — `web/src/pages/video/sharp-request.test.ts`:
```ts
import { describe, expect, it } from "vitest"

import type { Job } from "@/lib/types"

import { sharpBlock, sharpJobBusy } from "./sharp-request"

const job = (over: Partial<Job>): Job => ({
  id: "j1",
  videoId: "aqz-KE-bpKQ",
  title: "",
  kind: "frames_sharp",
  params: {},
  status: "queued",
  position: 1,
  createdAt: "2026-10-05T03:00:00Z",
  ...over,
})

describe("sharpJobBusy", () => {
  it("a queued or running frames_sharp job of this clip", () => {
    expect(sharpJobBusy([job({})], "aqz-KE-bpKQ")).toBe(true)
    expect(sharpJobBusy([job({ status: "running" })], "aqz-KE-bpKQ")).toBe(true)
  })
  it("finished jobs, other clips, other kinds and no list are not busy", () => {
    expect(sharpJobBusy([job({ status: "done" }), job({ status: "failed" })], "aqz-KE-bpKQ")).toBe(false)
    expect(sharpJobBusy([job({ videoId: "jNQXAC9IVRw" })], "aqz-KE-bpKQ")).toBe(false)
    expect(sharpJobBusy([job({ kind: "frames_zip", params: { source: "sharp" } })], "aqz-KE-bpKQ")).toBe(false)
    expect(sharpJobBusy(undefined, "aqz-KE-bpKQ")).toBe(false)
  })
})

describe("sharpBlock", () => {
  it("loading, live, unknown duration, ok", () => {
    expect(sharpBlock(undefined)).toBe("loading")
    expect(sharpBlock({ isLive: true, durationS: 600 })).toBe("live")
    expect(sharpBlock({ isLive: false, durationS: 0 })).toBe("live")
    expect(sharpBlock({ isLive: false, durationS: 635 })).toBeNull()
  })
})
```

- [ ] **Step 2: Run it, expect FAIL** — `cd web && npm test -- sharp-request` (module not found).

- [ ] **Step 3: `web/src/pages/video/sharp-request.ts`**
```ts
import type { Job, VideoInfo } from "@/lib/types"

/** งานภาพคมของคลิปนี้ที่ยังรอคิวหรือกำลังทำ: ปุ่มเป็น "กำลังดึงภาพคม…" (spec 1.2 กันขอซ้ำ) */
export function sharpJobBusy(jobs: readonly Job[] | undefined, videoId: string): boolean {
  return (jobs ?? []).some(
    (job) => job.videoId === videoId && job.kind === "frames_sharp" && (job.status === "queued" || job.status === "running")
  )
}

export type SharpBlock = "loading" | "live" | null

/** ขอภาพคมไม่ได้เพราะ: ข้อมูลคลิปยังไม่มา (loading) · คลิปสด/ไม่รู้ความยาว (live: tooltip "คลิปสดยังขอภาพคมไม่ได้") */
export function sharpBlock(video: Pick<VideoInfo, "isLive" | "durationS"> | undefined): SharpBlock {
  if (video === undefined) return "loading"
  return video.isLive || !(video.durationS > 0) ? "live" : null
}
```

- [ ] **Step 4: `web/src/components/ui/radio-group.tsx`** (shadcn-style wrapper over Base UI, same look as `checkbox.tsx`)
```tsx
"use client"

import { Radio as RadioPrimitive } from "@base-ui/react/radio"
import { RadioGroup as RadioGroupPrimitive } from "@base-ui/react/radio-group"
import { cn } from "cn"

function RadioGroup({ className, ...props }: RadioGroupPrimitive.Props) {
  return <RadioGroupPrimitive data-slot="radio-group" className={cn("grid w-full gap-2", className)} {...props} />
}

function RadioGroupItem({ className, ...props }: RadioPrimitive.Root.Props) {
  return (
    <RadioPrimitive.Root
      data-slot="radio-group-item"
      className={cn(
        "peer relative flex size-4 shrink-0 items-center justify-center rounded-full border border-input outline-none after:absolute after:-inset-x-3 after:-inset-y-2 focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50 data-disabled:cursor-not-allowed data-disabled:opacity-50 aria-invalid:border-destructive dark:bg-input/30 data-checked:border-primary data-checked:bg-primary dark:data-checked:bg-primary",
        className
      )}
      {...props}
    >
      <RadioPrimitive.Indicator data-slot="radio-group-indicator" className="flex items-center justify-center">
        <span className="size-1.5 rounded-full bg-primary-foreground" />
      </RadioPrimitive.Indicator>
    </RadioPrimitive.Root>
  )
}

export { RadioGroup, RadioGroupItem }
```

- [ ] **Step 5: `web/src/pages/video/sharp-dialog.tsx`**
```tsx
import { useQuery } from "@tanstack/react-query"
import { useId, useState } from "react"

import { Button } from "@/components/ui/button"
import { Dialog, DialogClose, DialogContent, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog"
import { FieldError } from "@/components/ui/field"
import { Input } from "@/components/ui/input"
import { RadioGroup, RadioGroupItem } from "@/components/ui/radio-group"
import { Spinner } from "@/components/ui/spinner"
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip"
import { fill, th } from "@/i18n/th"
import { formatBytes } from "@/lib/format"
import { jobsQuery, useEnqueue } from "@/lib/jobs"
import {
  defaultCustomText,
  sharpDialogModel,
  type SharpFast,
  type SharpMode,
  type SharpResolution,
} from "@/lib/sharp-frames"
import type { VideoInfo } from "@/lib/types"

import { sharpBlock, sharpJobBusy } from "./sharp-request"

const t = th.sharp
// จอแคบ: ปุ่มสูง 44 px ให้นิ้วกดได้ง่าย (แบบเดียวกับปุ่มโหลดทั้งชุด)
const TOUCH = "max-sm:h-11"

const ENQUEUE_MESSAGES = {
  added: th.queue.added,
  addedMany: th.queue.addedMany,
  failed: th.queue.addFailed,
  goHealth: th.queue.goHealth,
}

type Props = {
  videoId: string
  /** ข้อมูลคลิป (ยังไม่มา = ปุ่มปิด) */
  video: VideoInfo | undefined
  /** ภาพเร็วของคลิป · null = ไม่มี storyboard (dialog ไม่มีตัวเลือก "เวลาเดียวกับภาพเร็ว") */
  fast: SharpFast | null
  /** มีชุดภาพคมในแอพแล้ว (dialog เตือนว่าจะถูกแทน) */
  hasSharp: boolean
  /** แถวปุ่มโหลด = secondary · หน้าคลิปไม่มี storyboard = outline */
  variant?: "secondary" | "outline"
}

/**
 * ปุ่ม "ขอภาพคม" (spec 1): เปิด dialog เลือกช่วงเวลา · มีงานภาพคมของคลิปนี้ในคิว = "กำลังดึงภาพคม…" ·
 * คลิปสด/ไม่รู้ความยาว = ปิดพร้อม tooltip (ปุ่มที่ปิดยังโฟกัสได้ ผู้ใช้คีย์บอร์ดจึงเห็นเหตุผล)
 */
export function SharpRequestButton({ videoId, video, fast, hasSharp, variant = "secondary" }: Props) {
  // รายการงานชุดเดียวกับแถบคิว (SSE คอยแก้แคช) ไม่ยิงคำขอเพิ่มเมื่อมีอยู่แล้ว
  const jobs = useQuery({ ...jobsQuery(), staleTime: Infinity })
  const [open, setOpen] = useState(false)
  const size = variant === "secondary" ? "sm" : "default"
  const block = sharpBlock(video)

  if (sharpJobBusy(jobs.data, videoId)) {
    return (
      <Button variant={variant} size={size} className={TOUCH} disabled focusableWhenDisabled>
        <Spinner aria-hidden />
        {t.busy}
      </Button>
    )
  }
  if (block === "live") {
    return (
      <Tooltip>
        <TooltipTrigger render={<Button variant={variant} size={size} className={TOUCH} disabled focusableWhenDisabled />}>
          {th.frames.requestSharp}
        </TooltipTrigger>
        <TooltipContent>{t.liveDisabled}</TooltipContent>
      </Tooltip>
    )
  }
  return (
    <>
      <Button
        variant={variant}
        size={size}
        className={TOUCH}
        disabled={block !== null}
        focusableWhenDisabled
        onClick={() => setOpen(true)}
      >
        {th.frames.requestSharp}
      </Button>
      {video !== undefined && block === null && (
        <SharpDialog open={open} onOpenChange={setOpen} videoId={videoId} video={video} fast={fast} hasSharp={hasSharp} />
      )}
    </>
  )
}

function resolutionText(r: SharpResolution): string {
  if (r.kind === "low") return fill(t.lowRes, { h: r.h })
  return r.kind === "tall" ? t.tall : t.wide
}

type DialogProps = {
  open: boolean
  onOpenChange: (open: boolean) => void
  videoId: string
  video: VideoInfo
  fast: SharpFast | null
  hasSharp: boolean
}

/**
 * dialog "ขอภาพคม" (spec 1.3): เวลาเดียวกับภาพเร็ว (ค่าเริ่มต้น) หรือ ตั้งเอง ทุก N วินาที · จำนวนภาพ ขนาดวิดีโอชั่วคราว
 * และความละเอียดคำนวณสดจาก sharpDialogModel · เกิน 200 ภาพ = ประโยคปรับช่วงห่างแทนจำนวน แล้วส่ง intervalS = N2
 */
function SharpDialog({ open, onOpenChange, videoId, video, fast, hasSharp }: DialogProps) {
  const [mode, setMode] = useState<SharpMode>("same")
  const [customText, setCustomText] = useState(() => defaultCustomText(video.durationS))
  const { enqueue, pending } = useEnqueue(ENQUEUE_MESSAGES)
  const prefixId = useId()
  const unitId = useId()
  const errorId = useId()
  const model = sharpDialogModel({ durationS: video.durationS, fast, mode, customText, video: video.video, hasSharp })
  const customLabel = `${prefixId} ${unitId}`

  async function start() {
    if (model.params === null || pending) return
    const ok = await enqueue([{ videoId, kind: "frames_sharp", params: model.params, title: video.title }])
    if (ok) onOpenChange(false)
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>{th.frames.requestSharp}</DialogTitle>
        </DialogHeader>
        <RadioGroup
          aria-label={th.frames.requestSharp}
          value={model.mode}
          onValueChange={(value) => {
            if (value === "same" || value === "custom") setMode(value)
          }}
          className="gap-3"
        >
          {model.sameAvailable && (
            <label className="flex items-start gap-3">
              <RadioGroupItem value="same" className="mt-0.5" />
              <span className="flex flex-col gap-0.5">
                <span>{t.sameTimes}</span>
                {!(model.mode === "same" && model.overflow) && (
                  <span className="text-muted-foreground">
                    {fill(t.sameTimesDetail, { interval: model.sameInterval ?? "", count: model.sameCount ?? 0 })}
                  </span>
                )}
              </span>
            </label>
          )}
          <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
            <RadioGroupItem value="custom" aria-labelledby={customLabel} />
            <span id={prefixId}>{t.customPrefix}</span>
            <Input
              className="h-8 w-20"
              inputMode="numeric"
              autoComplete="off"
              value={customText}
              aria-labelledby={customLabel}
              aria-invalid={model.customError || undefined}
              aria-describedby={model.customError ? errorId : undefined}
              onFocus={() => setMode("custom")}
              onChange={(event) => {
                setCustomText(event.target.value)
                setMode("custom")
              }}
              onKeyDown={(event) => {
                if (event.key === "Enter") void start()
              }}
            />
            <span id={unitId}>{t.customUnit}</span>
            {model.customCount !== null && !(model.mode === "custom" && model.overflow) && (
              <span className="text-muted-foreground">{fill(t.customCount, { count: model.customCount })}</span>
            )}
          </div>
        </RadioGroup>
        {model.customError && <FieldError id={errorId}>{t.intervalError}</FieldError>}
        {/* ประโยคเกิน 200 ภาพแทนจำนวนภาพแบบสด (AC-FRAME-04) โปรแกรมอ่านหน้าจออ่านให้เมื่อเปลี่ยน */}
        <p role="status" className="empty:hidden">
          {model.overflow && fill(t.overLimit, { N: model.overflow.n, count: model.overflow.count, N2: model.overflow.n2 })}
        </p>
        <ul className="flex flex-col gap-1 text-muted-foreground">
          <li>{model.sizeBytes === null ? t.sizeUnknown : fill(t.size, { size: formatBytes(model.sizeBytes) })}</li>
          <li>{resolutionText(model.resolution)}</li>
          {model.replace && <li>{t.replaceWarning}</li>}
        </ul>
        <DialogFooter>
          <DialogClose render={<Button variant="outline" />}>{t.cancel}</DialogClose>
          <Button disabled={model.params === null || pending} onClick={() => void start()}>
            {pending && <Spinner aria-hidden />}
            {t.start}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
```

- [ ] **Step 6: Run the web checks, expect PASS** — `cd web && npm run typecheck && npm run lint && npm test` (the component is mounted and exercised by T15's e2e spec).

- [ ] **Step 7: Commit**
```bash
git add web/src/components/ui/radio-group.tsx web/src/pages/video/sharp-request.ts web/src/pages/video/sharp-request.test.ts web/src/pages/video/sharp-dialog.tsx
git commit -F- <<'EOF'
feat(web): "ขอภาพคม" button and dialog (same times / every N seconds, count, size, over-200 rule)

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
EOF
```

### Task 12: Settings switch "ทำภาพคมอัตโนมัติตอนโหลดวิดีโอ"

**Files:**
- Modify: `web/src/pages/settings/general-form.ts` (`GeneralKey`)
- Modify: `web/src/pages/settings/general-form.test.ts`
- Modify: `web/src/pages/settings/general-panel.tsx`
- Modify: `web/e2e/settings-general.spec.ts`

**Interfaces:**
- Consumes: C10 `th.general.autoSharpFrames|autoSharpFramesHint`, C11 `Settings.autoSharpFrames`, `SwitchRow` (`web/src/pages/video/advanced/switch-row.tsx`), C1 backend key.
- Produces: the switch (PATCH `{autoSharpFrames: bool}`).

- [ ] **Step 1: Write the failing unit test** — append to `web/src/pages/settings/general-form.test.ts`:
```ts
describe("autoSharpFrames (M5 รอบ B)", () => {
  it("switching sends only that key, the same value sends nothing", () => {
    expect(choicePatch("autoSharpFrames", false, SAVED)).toEqual({ autoSharpFrames: false })
    expect(choicePatch("autoSharpFrames", true, SAVED)).toBeNull()
  })
})
```
- [ ] **Step 2: Run it, expect FAIL** — `cd web && npm test -- general-form` (type error: `"autoSharpFrames"` is not a `GeneralKey`).
- [ ] **Step 3: Implement**

`general-form.ts`: `/** ค่าที่หน้า "ทั่วไป" แก้ได้ (ทั้งหกช่อง) */` and `export type GeneralKey = "outputDir" | "concurrency" | "audioLanguage" | "videoDefault" | "audioDefault" | "autoSharpFrames"`.
`general-panel.tsx`: add `import { SwitchRow } from "@/pages/video/advanced/switch-row"`; change the skeleton count `Array.from({ length: 5 }` to `{ length: 6 }`; after the `audioDefault` `<Field>` add:
```tsx
      {/* M5 รอบ B (D6): ภาพคมจากไฟล์วิดีโอที่โหลดแล้ว เปิดไว้ตั้งต้น */}
      <SwitchRow
        label={t.autoSharpFrames}
        hint={t.autoSharpFramesHint}
        checked={shown.autoSharpFrames}
        onChange={(checked) => choose(choicePatch("autoSharpFrames", checked, shown))}
      />
```
- [ ] **Step 4: Add the e2e test** — append to `web/e2e/settings-general.spec.ts` (before the axe loop):
```ts
test("ทำภาพคมอัตโนมัติ: เปิดอยู่ตั้งต้น · ปิดแล้วบันทึกและคงอยู่ (ใช้ค่าจำลอง ไม่เขียน backend)", async ({ page, request }) => {
  const stub = await stubSettings(page, request)
  await page.goto("/settings/general")
  const toggle = page.getByRole("switch", { name: "ทำภาพคมอัตโนมัติตอนโหลดวิดีโอ" })
  await expect(toggle).toHaveAttribute("aria-checked", "true")
  await expect(page.getByText("ใช้ไฟล์ที่โหลดมาแล้ว ไม่ต้องโหลดเพิ่ม ใช้เวลาเพิ่มราว 10-40 วินาทีต่อคลิป")).toBeVisible()
  await toggle.click()
  await expect(saved(page)).toBeVisible()
  expect(stub.patches).toEqual([{ autoSharpFrames: false }])
  await page.reload()
  await expect(page.getByRole("switch", { name: "ทำภาพคมอัตโนมัติตอนโหลดวิดีโอ" })).toHaveAttribute("aria-checked", "false")
})
```
and in `/settings เปิดที่แท็บทั่วไป พร้อมห้าช่อง` rename the title to `… พร้อมหกช่อง` and add `await expect(page.getByRole("switch", { name: "ทำภาพคมอัตโนมัติตอนโหลดวิดีโอ" })).toBeVisible()`.
- [ ] **Step 5: Run the web checks, expect PASS** — `cd web && npm run typecheck && npm run lint && npm test`.
- [ ] **Step 6: Commit**
```bash
git add web/src/pages/settings/general-form.ts web/src/pages/settings/general-form.test.ts web/src/pages/settings/general-panel.tsx web/e2e/settings-general.spec.ts
git commit -F- <<'EOF'
feat(web): settings switch for automatic sharp frames

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
EOF
```

### Task 13: Queue text for sharp stages, sharp job titles, folder outputs

**Files:**
- Modify: `web/src/components/queue/job-text.ts`, `web/src/components/queue/job-text.test.ts`
- Modify: `web/src/components/queue/job-row.tsx` (`DoneRow`)

**Interfaces:**
- Consumes: C10 `th.queue.extracting|autoSharp|sharpTitle|sharpTitleCount`, C11 `JobStage`, `JobOutput.files`.
- Produces: C12 exactly.

- [ ] **Step 1: Write the failing tests** — append to `web/src/components/queue/job-text.test.ts` (add `sharpCount` to the import):
```ts
describe("ภาพคม (M5 รอบ B)", () => {
  const sharp = (over: Partial<Job> = {}) => job({ kind: "frames_sharp", params: {}, ...over })

  it("stageText of the two sharp stages", () => {
    expect(stageText("extracting_frames:3/40")).toBe("กำลังดึงภาพ 3/40")
    expect(stageText("sharp_frames:2/9")).toBe("กำลังทำภาพคม 2/9")
  })

  it("sharpCount: folder output first, then the extracting stage", () => {
    expect(sharpCount({ outputs: [{ index: 0, name: "x - ภาพคม", sizeBytes: 9, files: 38 }], stage: "extracting_frames:1/40" })).toBe(38)
    expect(sharpCount({ stage: "extracting_frames:3/40" })).toBe(40)
    expect(sharpCount({ stage: "downloading_video" })).toBeNull()
    expect(sharpCount({})).toBeNull()
  })

  it("jobTitle of a sharp job", () => {
    expect(jobTitle(sharp({ status: "queued" }))).toBe("คลิปทดสอบ · ภาพคม")
    expect(jobTitle(sharp({ stage: "downloading_video" }))).toBe("คลิปทดสอบ · ภาพคม")
    expect(jobTitle(sharp({ stage: "extracting_frames:3/40" }))).toBe("คลิปทดสอบ · ภาพคม 40 ภาพ")
    expect(jobTitle(sharp({ status: "done", outputs: [{ index: 0, name: "คลิป - ภาพคม", sizeBytes: 9, files: 38 }] }))).toBe(
      "คลิปทดสอบ · ภาพคม 38 ภาพ"
    )
    expect(jobTitle(sharp({ title: "" }))).toBe("aqz-KE-bpKQ · ภาพคม")
  })

  it("progressLine shows the sharp stage, other kinds keep their titles", () => {
    expect(progressLine(sharp({ stage: "extracting_frames:3/40", progress: 0.05 }))).toBe("กำลังดึงภาพ 3/40 · 5%")
    expect(progressLine(job({ stage: "sharp_frames:2/9" }))).toBe("กำลังทำภาพคม 2/9")
    expect(jobTitle(job())).toBe("คลิปทดสอบ")
  })
})
```
- [ ] **Step 2: Run them, expect FAIL** — `cd web && npm test -- job-text`.
- [ ] **Step 3: Implement `job-text.ts`** — replace the `SPLIT` constant, `stageText` and `jobTitle` with:
```ts
const SPLIT = /^splitting:(\d+)\/(\d+)$/
const EXTRACTING = /^extracting_frames:(\d+)\/(\d+)$/
const AUTO_SHARP = /^sharp_frames:(\d+)\/(\d+)$/
type FixedStage = keyof typeof th.queue.stages

/**
 * ข้อความของขั้นตอน: "splitting:3/12" = "กำลังแยก chapter 3/12" (M5 รอบ A) · "extracting_frames:3/40" = "กำลังดึงภาพ 3/40"
 * · "sharp_frames:2/9" = "กำลังทำภาพคม 2/9" (M5 รอบ B) · ที่เหลือตามตาราง th.queue.stages
 */
export function stageText(stage: JobStage): string {
  const split = SPLIT.exec(stage)
  if (split) return fill(th.queue.splitting, { i: split[1], n: split[2] })
  const extracting = EXTRACTING.exec(stage)
  if (extracting) return fill(th.queue.extracting, { i: extracting[1], n: extracting[2] })
  const auto = AUTO_SHARP.exec(stage)
  if (auto) return fill(th.queue.autoSharp, { i: auto[1], n: auto[2] })
  return th.queue.stages[stage as FixedStage]
}

/** จำนวนภาพของงานภาพคม: งานเสร็จ = จำนวนไฟล์ในโฟลเดอร์ผล · กำลังดึงภาพ = n ของขั้น · ยังไม่รู้ = null */
export function sharpCount(job: Partial<Pick<Job, "stage" | "outputs">>): number | null {
  const files = job.outputs?.[0]?.files
  if (files !== undefined) return files
  const extracting = job.stage === undefined ? null : EXTRACTING.exec(job.stage)
  return extracting ? Number(extracting[2]) : null
}
```
(keep `jobChoice` unchanged) and:
```ts
type TitledJob = Pick<Job, "title" | "videoId"> & Partial<Pick<Job, "kind" | "params" | "stage" | "outputs">>

/**
 * ชื่อที่แสดงของงาน: ชื่อคลิป (ยังไม่รู้ชื่อ = รหัสคลิป) + ตัวเลือกขั้นสูง
 * งานภาพคม: " · ภาพคม {n} ภาพ" เมื่อรู้จำนวน (spec 3.5) ยังไม่รู้ = " · ภาพคม"
 */
export const jobTitle = (job: TitledJob): string => {
  const base = job.title || job.videoId
  if (job.kind === "frames_sharp") {
    const n = sharpCount(job)
    return base + (n === null ? th.queue.sharpTitle : fill(th.queue.sharpTitleCount, { n }))
  }
  return base + (job.params ? jobChoice(job.params) : "")
}
```
`job-row.tsx` `DoneRow`: wrap the `<a … download …>` element in `{output.files === undefined && ( … )}` and add the comment `{/* ผลแบบโฟลเดอร์ (ภาพคม) ดาวน์โหลดผ่านเบราว์เซอร์ไม่ได้: ใช้ "เปิดโฟลเดอร์" */}` above it.
- [ ] **Step 4: Run the web checks, expect PASS** — `cd web && npm run typecheck && npm run lint && npm test`.
- [ ] **Step 5: Commit**
```bash
git add web/src/components/queue/job-text.ts web/src/components/queue/job-text.test.ts web/src/components/queue/job-row.tsx
git commit -F- <<'EOF'
feat(web): queue text for sharp stages and "· ภาพคม n ภาพ" titles; folder outputs open, not download

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
EOF
```

---

## Wave 3

### Task 14: Automatic sharp frames after a `video` job, and its wiring

**Files:**
- Modify: `src/yttoolkit/core/handlers.py` (`HandlerDeps.auto_sharp`, `_auto_sharp_skip`, `_auto_sharp`, end of `_video`)
- Modify: `src/yttoolkit/lifecycle.py` (`open_services`: `auto_sharp=`)
- Create: `tests/unit/test_handlers_auto_sharp.py`
- Modify: `tests/unit/test_lifecycle.py`

**Interfaces:**
- Consumes: T8 `_clip_duration_s`, `_extract_frames`, `_created_at`; C2 `plan_sharp`, `fast_times`; C3 `DownloadResult.media`, `MediaFacts`, `SHARP_MAX_SHORT_SIDE`; C5 `prepare_sharp`, `commit_sharp`, `discard_sharp`, `read_sharp`; C1 setting `autoSharpFrames`; `tests/helpers_sharp.py`.
- Produces: C8 exactly.

- [ ] **Step 1: Write the failing tests** — `tests/unit/test_handlers_auto_sharp.py`:
```python
"""ภาพคมอัตโนมัติหลังงานวิดีโอ (M5 รอบ B D6, C8): ทำเมื่อเงื่อนไขครบ ไม่ทำให้งานวิดีโอล้ม ไม่แทนชุดที่ผู้ใช้ขอเอง"""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import replace
from pathlib import Path

import pytest
from helpers_sharp import BBB, MEDIA, VIDEO, ZOO, SharpEnv

from yttoolkit.core import files
from yttoolkit.core.cancel import JobCancelled
from yttoolkit.core.download import MediaFacts
from yttoolkit.core.events import EventBus
from yttoolkit.core.handlers import build_handlers
from yttoolkit.core.jobs import JobResult, JobStore, NewJob
from yttoolkit.core.media import FakeMediaTools
from yttoolkit.core.queue import QueueRunner
from yttoolkit.core.settings import SettingsStore
from yttoolkit.core.sharp_store import read_sharp
from yttoolkit.core.yterrors import YtError

HD = MediaFacts(1280, 720, "SDR")


class NoFfmpeg(FakeMediaTools):
    def available(self) -> bool:
        return False


class FailingFrames(FakeMediaTools):
    def extract_frame(self, src, dst, t_ms, *, long_side, dynamic_range, cancel):
        raise YtError("E_DISK_FULL", "No space left on device")


class GateMedia(FakeMediaTools):
    """ภาพที่สองรอจนถูกสั่งหยุด แล้วหยุดแบบ ffmpeg ที่ถูก kill ตอนปิดโปรแกรม"""

    def __init__(self, root: Path) -> None:
        super().__init__(root)
        self.reached = threading.Event()

    def extract_frame(self, src, dst, t_ms, *, long_side, dynamic_range, cancel):
        if len(self.frames) == 1:
            self.reached.set()
            deadline = time.monotonic() + 10
            while not cancel() and time.monotonic() < deadline:
                time.sleep(0.01)
            raise JobCancelled()
        return super().extract_frame(src, dst, t_ms, long_side=long_side, dynamic_range=dynamic_range, cancel=cancel)


@pytest.fixture
def env(tmp_path):
    made = SharpEnv(tmp_path)
    made.downloader.media = HD
    made.deps = replace(made.deps, auto_sharp=lambda: True)
    yield made
    made.close()


def _video_file(result: JobResult) -> Path:
    (out,) = result.outputs
    return Path(out.root) / out.rel


def _cache_children(env: SharpEnv, video_id: str = BBB) -> list[str]:
    folder = env.cache / video_id
    return sorted(p.name for p in folder.iterdir()) if folder.exists() else []


def test_auto_sharp_after_a_full_720p_video(env):
    result, ctx = env.run("video", BBB, dict(VIDEO))
    video = _video_file(result)
    assert [o.kind for o in result.outputs] == ["video"] and result.notes == ()
    index = read_sharp(env.cache, BBB)
    assert index["origin"] == "auto" and index["intervalMs"] is None and len(index["frames"]) == 128
    assert ctx.stages[-128:] == [f"sharp_frames:{i}/128" for i in range(1, 129)]
    assert {call.src_name for call in env.media.frames} == {video.name}  # อ่านไฟล์ที่อยู่ในโฟลเดอร์ผลลัพธ์แล้ว
    assert sorted(p.name for p in video.parent.iterdir()) == sorted([video.name, files.SOURCE_NOTE_NAME])
    assert _cache_children(env) == ["sharp"]


@pytest.mark.parametrize(
    ("case", "params"),
    [
        ("setting off", {}),
        ("range", {"range": {"startMs": 0, "endMs": 60_000}}),
        ("sponsorblock", {"sponsorblock": ["sponsor"]}),
        ("split chapters", {"splitChapters": True}),
        ("unknown file", {}),
        ("hdr file", {}),
        ("below 720", {}),
        ("no ffmpeg", {}),
    ],
)
def test_auto_sharp_is_skipped(env, case, params):
    deps = env.deps
    if case == "setting off":
        deps = replace(deps, auto_sharp=lambda: False)
    elif case == "unknown file":
        env.downloader.media = None
    elif case == "hdr file":
        env.downloader.media = MediaFacts(3840, 2160, "HDR10")
    elif case == "below 720":
        env.downloader.media = MediaFacts(854, 480, "SDR")
    elif case == "no ffmpeg":
        deps = replace(deps, media=NoFfmpeg(MEDIA))
    result, ctx = env.run("video", BBB, {**VIDEO, **params}, deps=deps)
    assert result.outputs[0].kind == "video" and _video_file(result).is_file()
    assert read_sharp(env.cache, BBB) is None
    assert not any(stage.startswith("sharp_frames:") for stage in ctx.stages)


def test_a_portrait_720_file_runs(env):
    env.downloader.media = MediaFacts(720, 1280, "SDR")
    env.run("video", BBB, dict(VIDEO))
    assert read_sharp(env.cache, BBB)["origin"] == "auto"


def test_without_a_storyboard_the_default_interval_is_used(env):
    env.run("video", ZOO, dict(VIDEO))
    index = read_sharp(env.cache, ZOO)
    assert index["intervalMs"] == 1000 and len(index["frames"]) == 19


def test_zero_frames_is_not_fatal(env):
    env.media.frame_limit_ms = 0
    result, _ = env.run("video", BBB, dict(VIDEO))
    assert _video_file(result).is_file() and result.notes == ()
    assert read_sharp(env.cache, BBB) is None and _cache_children(env) == []


def test_an_extraction_error_is_logged_not_fatal(env, caplog):
    deps = replace(env.deps, media=FailingFrames(MEDIA))
    with caplog.at_level(logging.INFO, logger="yttoolkit"):
        result, _ = env.run("video", BBB, dict(VIDEO), deps=deps)
    assert _video_file(result).is_file()
    assert any("ข้ามภาพคมอัตโนมัติ (YtError)" in r.getMessage() for r in caplog.records)
    assert all(str(env.tmp) not in r.getMessage() for r in caplog.records)


def test_cancel_during_auto_sharp_ends_done(env):  # Review Focus 5
    result, _ = env.run("video", BBB, dict(VIDEO), cancel_on="sharp_frames:2/128")
    assert _video_file(result).is_file()
    assert read_sharp(env.cache, BBB) is None and _cache_children(env) == []


def test_shutdown_during_auto_sharp_ends_done(tmp_path):  # Review Focus 5
    env = SharpEnv(tmp_path, media=GateMedia(MEDIA))
    env.downloader.media = HD
    try:
        deps = replace(env.deps, auto_sharp=lambda: True)
        store = JobStore(env.db)
        runner = QueueRunner(store, EventBus(), build_handlers(deps), settings=SettingsStore(env.db, env.out),
                             work_root=tmp_path / "queue-work", delay_range=(0.0, 0.0), redact=lambda text: text)  # fmt: skip
        runner.start()
        (job,) = runner.enqueue([NewJob(BBB, "video", dict(VIDEO))])
        assert env.media.reached.wait(10)
        runner.shutdown(timeout=5)
        finished = store.get(job.id)
        assert finished.status == "done" and finished.outputs[0].kind == "video"
        assert read_sharp(env.cache, BBB) is None
    finally:
        env.close()


def test_manual_set_is_not_replaced(env):  # Review Focus 5
    env.run("frames_sharp", BBB, {"intervalS": 60})
    env.run("video", BBB, dict(VIDEO))
    index = read_sharp(env.cache, BBB)
    assert index["origin"] == "manual" and len(index["frames"]) == 11


def test_an_auto_set_is_replaced_by_the_next_auto_set(env):
    env.run("video", BBB, dict(VIDEO))
    env.media.frame_limit_ms = 300_000
    env.run("video", BBB, dict(VIDEO))
    index = read_sharp(env.cache, BBB)
    assert index["origin"] == "auto" and len(index["frames"]) == 61
    assert _cache_children(env) == ["sharp"]
```
Append to `tests/unit/test_lifecycle.py`:
```python
def test_open_services_wires_auto_sharp_to_the_setting(paths, fake_platform, monkeypatch):
    captured = {}
    real = lifecycle.build_handlers

    def spy(deps):
        captured["deps"] = deps
        return real(deps)

    monkeypatch.setattr(lifecycle, "build_handlers", spy)
    services = lifecycle.open_services(paths, fake_platform, fake=True)
    try:
        assert captured["deps"].auto_sharp() is True
        services.settings.patch({"autoSharpFrames": False})
        assert captured["deps"].auto_sharp() is False
    finally:
        services.db.close()
```

- [ ] **Step 2: Run them, expect FAIL** — `uv run pytest tests/unit/test_handlers_auto_sharp.py tests/unit/test_lifecycle.py -q -W error -p no:cacheprovider` (`TypeError: … unexpected keyword argument 'auto_sharp'`).

- [ ] **Step 3: Implement `core/handlers.py`**

Extend the `.download` import with `MediaFacts`. Add to `HandlerDeps` (last field):
```python
    # ทำภาพคมอัตโนมัติหลังงานวิดีโอ (M5 รอบ B D6) lifecycle อ่านค่าตั้ง autoSharpFrames ทุกงาน · ค่าเริ่มต้น (เทส) = ไม่ทำ
    auto_sharp: Callable[[], bool] = lambda: False
```
Add after `_frames_sharp`:
```python
def _auto_sharp_skip(deps: HandlerDeps, params: Mapping[str, Any], media: MediaFacts | None) -> str | None:
    """เหตุผลที่ไม่ทำภาพคมอัตโนมัติ (D6) None = ทำ: ต้องเปิดค่าตั้ง เป็นไฟล์ทั้งคลิป (เส้นเวลาตรงกับคลิป)
    ไฟล์ด้านสั้น ≥ 720 ไม่ใช่ HDR (ไม่ tone-map เอง D8) และมี ffmpeg · ไม่รู้ขนาด/ช่วงสีของไฟล์ = ไม่ทำ"""
    if not deps.auto_sharp():
        return "setting off"
    if params.get("range") is not None or params.get("sponsorblock") or params.get("splitChapters"):
        return "not the full clip"
    if media is None or media.short_side is None or media.hdr is None:
        return "file facts unknown"
    if media.short_side < SHARP_MAX_SHORT_SIDE:
        return "below 720"
    if media.hdr:
        return "hdr"
    if not deps.media.available():
        return "no ffmpeg"
    return None


def _auto_sharp(
    deps: HandlerDeps,
    job: Job,
    ctx: JobContext,
    clip: _Clip,
    report: _Reporter,
    finished: JobResult,
    media: MediaFacts | None,
) -> None:
    """ภาพคมอัตโนมัติจากไฟล์วิดีโอที่อยู่ในโฟลเดอร์ผลลัพธ์แล้ว (ไม่โหลดเพิ่ม ไม่แตะเครือข่าย) ลง cache อย่างเดียว
    พังแบบไหน ถูกยกเลิก หรือปิดโปรแกรม = บันทึก log แล้วจบ งานวิดีโอยังเสร็จพร้อมไฟล์ (ไม่มีโน้ต)
    ชุดที่ผู้ใช้ขอเอง (manual) ไม่ถูกแทน ชุดอัตโนมัติเดิมถูกแทน"""
    reason = _auto_sharp_skip(deps, job.params, media)
    if reason is not None:
        log.info("งาน %s ไม่ทำภาพคมอัตโนมัติ (%s)", ctx.job_id, reason)
        return
    staged: Path | None = None
    try:
        existing = read_sharp(deps.cache_root, clip.video_id)
        if existing is not None and existing.get("origin") == "manual":
            log.info("งาน %s ไม่ทำภาพคมอัตโนมัติ (มีชุดที่ขอเองอยู่แล้ว)", ctx.job_id)
            return
        plan = plan_sharp(_clip_duration_s(clip), interval_s=None, fast_times=fast_times(deps.videos.raw(clip.video_id)))
        (out,) = finished.outputs
        video_file = Path(out.root) / out.rel
        made = _extract_frames(deps, ctx, report, video_file, plan.times_ms, stage="sharp_frames", dynamic_range=None)
        if not made:
            raise YtError("E_UNKNOWN", "no frames extracted")
        staged = prepare_sharp(
            deps.cache_root, clip.video_id, job.id, made, origin="auto",
            interval_ms=plan.interval_s * 1000 if plan.interval_s is not None else None, created_at=_created_at(deps),
        )  # fmt: skip
        commit_sharp(deps.cache_root, clip.video_id, staged)
        staged = None
        log.info("งาน %s ทำภาพคมอัตโนมัติ %s ภาพ", ctx.job_id, len(made))
    except Exception as exc:  # รวม JobCancelled (ยกเลิก/ปิดโปรแกรม) และ YtError: ไฟล์วิดีโอเสร็จแล้ว งานต้องจบ done
        log.info("งาน %s ข้ามภาพคมอัตโนมัติ (%s)", ctx.job_id, type(exc).__name__)
        if staged is not None:
            discard_sharp(staged)
    finally:
        shutil.rmtree(Path(ctx.workdir) / "frames", ignore_errors=True)
```
In `_video` replace the final `return _finish(deps, ctx, clip, out, suffix=suffix, ext="mp4", kind="video", notes=notes)` with:
```python
    finished = _finish(deps, ctx, clip, out, suffix=suffix, ext="mp4", kind="video", notes=notes)
    _auto_sharp(deps, job, ctx, clip, report, finished, result.media)
    return finished
```
(the chapter-split branch returns earlier and never reaches this; `_auto_sharp_skip` also refuses `splitChapters`).

- [ ] **Step 4: Implement `lifecycle.py`** — in `open_services`, add to the `HandlerDeps(...)` call (after `sponsors=extractor, …`):
```python
            # M5 รอบ B D6: อ่านค่าตั้งทุกงาน (ปิดในหน้าตั้งค่าแล้วมีผลกับงานถัดไปทันที)
            auto_sharp=lambda: bool(settings.get().get("autoSharpFrames", True)),
```

- [ ] **Step 5: Run the tests, expect PASS** — the Step 2 command, then `uv run pytest -q -W error -p no:cacheprovider` (`test_handlers.py` builds `HandlerDeps` without `auto_sharp`, so the step stays off there).

- [ ] **Step 6: Commit**
```bash
git add src/yttoolkit/core/handlers.py src/yttoolkit/lifecycle.py tests/unit/test_handlers_auto_sharp.py tests/unit/test_lifecycle.py
git commit -F- <<'EOF'
feat(handlers): automatic sharp frames after a full >=720p SDR video download (cache only, never fatal)

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
EOF
```

### Task 15: Mount "ขอภาพคม" in W2 and the dialog e2e

**Files:**
- Modify: `web/src/pages/video/frames.tsx` (`FramesSectionProps.video`, `NoStoryboard`, toolbar)
- Modify: `web/src/pages/video/tabs.tsx` (pass `video`)
- Modify: `web/e2e/video.spec.ts` (`NO_STORYBOARD_MESSAGE`, the no-storyboard test)
- Create: `web/e2e/sharp-dialog.spec.ts`

**Interfaces:**
- Consumes: T10 `FramesSection` (`hasFast`, `hasSharp`, `fastFrames`, `storyboard`), T11 `SharpRequestButton`, C2 `SharpFast`, C10 strings.
- Produces: the user-visible entry points of spec 1.1 (toolbar button next to the bulk buttons; active button in the no-storyboard empty state).

- [ ] **Step 1: Implement the mount**

`tabs.tsx`: `<FramesSection videoId={videoId} enabled={enabled} mostReplayed={mostReplayed} video={video} />`.
`frames.tsx`:
- imports: `import type { ReactNode } from "react"` (merge into the existing `react` import as `type ReactNode`), `import type { SharpFast } from "@/lib/sharp-frames"`, add `VideoInfo` to the `@/lib/types` type import, and `import { SharpRequestButton } from "./sharp-dialog"`.
- `NoStoryboard` takes the button:
```tsx
function NoStoryboard({ children }: { children: ReactNode }) {
  return (
    <Empty className="border">
      <EmptyHeader>
        <EmptyMedia variant="icon">
          <ImageOff aria-hidden />
        </EmptyMedia>
        <EmptyDescription>{t.noStoryboard}</EmptyDescription>
      </EmptyHeader>
      {/* M5 รอบ B: ปุ่ม "ขอภาพคม" ใช้ได้จริง (spec 1.1) */}
      <EmptyContent>{children}</EmptyContent>
    </Empty>
  )
}
```
- `FramesSectionProps` gains `/** ข้อมูลคลิป (ยังไม่มา = ปุ่มขอภาพคมปิด) */ video?: VideoInfo` and `FramesSection({ videoId, enabled, mostReplayed, video }: FramesSectionProps)`.
- After `const hasSharp = …` add:
```tsx
  // เวลาของภาพเร็วสำหรับ dialog "ขอภาพคม" (ตัวเลือก "เวลาเดียวกับภาพเร็ว") ไม่มี storyboard = null
  const fast = useMemo<SharpFast | null>(
    () => (hasFast && storyboard.data ? { intervalMs: storyboard.data.intervalMs, timesMs: fastFrames.map((f) => f.tMs) } : null),
    [hasFast, storyboard.data, fastFrames]
  )
```
- `else if (noStoryboard) body = <NoStoryboard />` becomes:
```tsx
  else if (noStoryboard) {
    body = (
      <NoStoryboard>
        <SharpRequestButton videoId={videoId} video={video} fast={null} hasSharp={false} variant="outline" />
      </NoStoryboard>
    )
  }
```
- In the toolbar row, right after `<BulkDownloads videoId={videoId} source={shown} />`:
```tsx
                {/* ถัดจากกลุ่มปุ่มโหลด (ไม่อยู่ใน ButtonGroup เดียวกัน): หน้าต่างแคบตัดขึ้นบรรทัดใหม่ได้ ไม่ล้นแนวนอน */}
                <SharpRequestButton videoId={videoId} video={video} fast={fast} hasSharp={hasSharp} />
```

- [ ] **Step 2: Update `web/e2e/video.spec.ts`**

`const NO_STORYBOARD_MESSAGE = 'คลิปนี้ไม่มีภาพตัวอย่างแบบเร็ว กด "ขอภาพคม" แทนได้'` and replace the test at line 494 with:
```ts
  test("คลิปที่ไม่มี storyboard: Empty พร้อมปุ่ม 'ขอภาพคม' ที่กดได้ (M5 รอบ B)", async ({ page }) => {
    await page.goto(`/v/${ZOO}`)
    await expect(page.getByText(NO_STORYBOARD_MESSAGE)).toBeVisible()
    const button = page.getByRole("button", { name: "ขอภาพคม" })
    await expect(button).toBeEnabled()
    await button.click()
    await expect(page.getByRole("dialog", { name: "ขอภาพคม" })).toBeVisible()
    await expect(page.getByRole("button", { name: "โหลดภาพรวมเฟรม" })).toHaveCount(0)
  })
```

- [ ] **Step 3: Write the dialog spec** — `web/e2e/sharp-dialog.spec.ts`:
```ts
/// <reference lib="dom" />
import path from "node:path"

import AxeBuilder from "@axe-core/playwright"
import { expect, test, type Page } from "@playwright/test"

import type { Job, SharpSet, VideoFormat, VideoInfo } from "../src/lib/types"

import { mockEnqueue } from "./queue-helpers"

/**
 * M5 รอบ B dialog "ขอภาพคม" (โปรเจกต์ chromium: mockEnqueue ทุกเทสที่กดเริ่ม ไม่มีงานจริง)
 * BBB 635 วิ ภาพเร็ว 128 ภาพ ทุก 4.961 วิ · format 720p ที่เลือก = 298 (150,524,867 ไบต์) · ZOO 19 วิ ไม่มี storyboard สูงสุด 240p
 */

const BBB = "aqz-KE-bpKQ"
const BBB_TITLE = "Big Buck Bunny 60fps 4K - Official Blender Foundation Short Film"
const ZOO = "jNQXAC9IVRw"
const COVER = path.join(import.meta.dirname, "../../tests/fixtures/media/cover.jpg")

const dialog = (page: Page) => page.getByRole("dialog", { name: "ขอภาพคม" })
const customField = (page: Page) => dialog(page).getByRole("textbox", { name: "ตั้งเอง ทุก วินาที" })
const start = (page: Page) => dialog(page).getByRole("button", { name: "เริ่มดึงภาพคม" })

async function openDialog(page: Page, videoId = BBB) {
  await page.goto(`/v/${videoId}`)
  await page.getByRole("button", { name: "ขอภาพคม" }).click()
  await expect(dialog(page)).toBeVisible()
}

async function patchVideo(page: Page, videoId: string, patch: (info: VideoInfo) => VideoInfo) {
  await page.route(`**/api/videos/${videoId}`, async (route) => {
    const response = await route.fetch()
    await route.fulfill({ response, json: patch((await response.json()) as VideoInfo) })
  })
}

async function seriousViolations(page: Page) {
  const results = await new AxeBuilder({ page }).analyze()
  return results.violations.filter((v) => v.impact === "serious" || v.impact === "critical").map((v) => v.id)
}

test("ค่าเริ่มต้น: เวลาเดียวกับภาพเร็ว 128 ภาพ ขนาดและความละเอียด · เริ่ม = ส่ง {} แล้วปิด dialog", async ({ page }) => {
  const queue = await mockEnqueue(page)
  await openDialog(page)
  await expect(dialog(page).getByRole("radio", { name: /เวลาเดียวกับภาพเร็ว/ })).toBeChecked()
  await expect(dialog(page)).toContainText("ทุก ~5.0 วินาที · 128 ภาพ")
  await expect(dialog(page)).toContainText("ต้องโหลดวิดีโอชั่วคราวราว 151 MB (ลบทิ้งเมื่อเสร็จ)")
  await expect(dialog(page)).toContainText("ภาพกว้าง 1280 px")
  await expect(dialog(page)).not.toContainText("ภาพคมชุดเดิมในแอพ")
  await start(page).click()
  await expect(dialog(page)).toBeHidden()
  await expect(page.getByText("เพิ่มเข้าคิวแล้ว", { exact: true })).toBeVisible()
  expect(queue.bodies).toEqual([[{ videoId: BBB, kind: "frames_sharp", params: {}, title: BBB_TITLE }]])
})

test("ตั้งเอง ทุก 7 วินาที: 91 ภาพ ส่ง intervalS 7", async ({ page }) => {
  const queue = await mockEnqueue(page)
  await openDialog(page)
  await customField(page).fill("7")
  await expect(dialog(page).getByRole("radio", { name: "ตั้งเอง ทุก วินาที" })).toBeChecked()
  await expect(dialog(page)).toContainText("· 91 ภาพ")
  await start(page).click()
  await expect(dialog(page)).toBeHidden()
  expect(queue.bodies[0][0].params).toEqual({ intervalS: 7 })
})

test("AC-FRAME-04: ทุก 2 วินาทีเกิน 200 ภาพ บอกช่วงใหม่แบบสด และส่ง intervalS 4", async ({ page }) => {
  const queue = await mockEnqueue(page)
  await openDialog(page)
  await customField(page).fill("2")
  await expect(dialog(page).getByRole("status")).toHaveText("ทุก 2 วินาทีจะได้ 318 ภาพ เกินที่ดึงได้ 200 ภาพ จะใช้ทุก 4 วินาทีแทน")
  await expect(dialog(page)).not.toContainText("· 318 ภาพ")
  await start(page).click()
  expect(queue.bodies[0][0].params).toEqual({ intervalS: 4 })
})

test("ช่องตั้งเองผิด: ข้อความใต้ช่อง ปุ่มเริ่มกดไม่ได้ · กลับไปเลือกเวลาเดียวกับภาพเร็วแล้วกดได้", async ({ page }) => {
  await mockEnqueue(page)
  await openDialog(page)
  for (const bad of ["0", "1.5", "abc", "3601"]) {
    await customField(page).fill(bad)
    await expect(dialog(page).getByText("ใส่เลขวินาทีเต็ม 1-3600")).toBeVisible()
    await expect(customField(page)).toHaveAttribute("aria-invalid", "true")
    await expect(start(page)).toBeDisabled()
  }
  await dialog(page).getByRole("radio", { name: /เวลาเดียวกับภาพเร็ว/ }).click()
  await expect(dialog(page).getByText("ใส่เลขวินาทีเต็ม 1-3600")).toHaveCount(0)
  await expect(start(page)).toBeEnabled()
})

test("ยกเลิก ปิด dialog โดยไม่ส่งงาน", async ({ page }) => {
  const queue = await mockEnqueue(page)
  await openDialog(page)
  await dialog(page).getByRole("button", { name: "ยกเลิก" }).click()
  await expect(dialog(page)).toBeHidden()
  expect(queue.bodies).toEqual([])
})

test("มีชุดภาพคมแล้ว: เตือนว่าจะถูกแทน", async ({ page }) => {
  const set: SharpSet = { origin: "auto", intervalMs: null, frames: [{ index: 0, tMs: 0, url: `/api/cache/${BBB}/sharp/f_0000.jpg?v=1` }] }
  await page.route(`**/api/videos/${BBB}/sharp`, (route) => route.fulfill({ json: set }))
  await page.route(`**/api/cache/${BBB}/sharp/**`, (route) => route.fulfill({ path: COVER, contentType: "image/jpeg" }))
  await openDialog(page)
  await expect(dialog(page)).toContainText("ภาพคมชุดเดิมในแอพจะถูกแทนด้วยชุดใหม่ (ไฟล์ในโฟลเดอร์ไม่หาย)")
})

test("คลิปไม่มี storyboard: ไม่มีตัวเลือกเวลาเดียวกับภาพเร็ว ช่องตั้งเองเริ่มที่ 1 (19 ภาพ) และบอกว่าภาพเล็กกว่าปกติ", async ({ page }) => {
  const queue = await mockEnqueue(page)
  await openDialog(page, ZOO)
  await expect(dialog(page).getByRole("radio", { name: /เวลาเดียวกับภาพเร็ว/ })).toHaveCount(0)
  await expect(customField(page)).toHaveValue("1")
  await expect(dialog(page)).toContainText("· 19 ภาพ")
  await expect(dialog(page)).toContainText("คลิปนี้มีภาพสูงสุด 240p ภาพจะเล็กกว่าปกติ")
  await start(page).click()
  expect(queue.bodies[0][0].params).toEqual({ intervalS: 1 })
})

test("คลิปแนวตั้ง (Shorts): ภาพสูง 1280 px และขนาดจาก format 720×1280", async ({ page }) => {
  const portrait: VideoFormat[] = [
    { formatId: "137", width: 1080, height: 1920, fps: 30, vcodec: "avc1.640028", compat: true, sizeBytes: 40_000_000 },
    { formatId: "136", width: 720, height: 1280, fps: 30, vcodec: "avc1.4d401f", compat: true, sizeBytes: 9_000_000 },
  ]
  await patchVideo(page, BBB, (info) => ({ ...info, video: portrait }))
  await openDialog(page)
  await expect(dialog(page)).toContainText("ภาพสูง 1280 px")
  await expect(dialog(page)).toContainText("ต้องโหลดวิดีโอชั่วคราวราว 9.0 MB (ลบทิ้งเมื่อเสร็จ)")
})

test("คลิปสด: ปุ่มปิด (ยังโฟกัสได้) พร้อม tooltip", async ({ page }) => {
  await patchVideo(page, BBB, (info) => ({ ...info, isLive: true }))
  await page.goto(`/v/${BBB}`)
  const button = page.getByRole("button", { name: "ขอภาพคม" })
  await expect(button).toBeDisabled()
  await button.hover()
  await expect(page.locator('[data-slot="tooltip-content"]')).toHaveText("คลิปสดยังขอภาพคมไม่ได้")
})

test("มีงานภาพคมของคลิปนี้ในคิว: ปุ่มเป็น 'กำลังดึงภาพคม…' และกดไม่ได้", async ({ page }) => {
  const queued: Job = {
    id: "01900000-0000-7000-8000-0000000000e2",
    videoId: BBB,
    title: BBB_TITLE,
    kind: "frames_sharp",
    params: {},
    status: "queued",
    position: 1,
    createdAt: "2026-10-05T03:00:00Z",
  }
  await page.route("**/api/jobs", (route) =>
    route.request().method() === "GET" ? route.fulfill({ json: { jobs: [queued] } }) : route.fallback()
  )
  await page.goto(`/v/${BBB}`)
  const busy = page.getByRole("button", { name: "กำลังดึงภาพคม…" })
  await expect(busy).toBeVisible()
  await expect(busy).toBeDisabled()
})

for (const scheme of ["dark", "light"] as const) {
  test(`axe: dialog ขอภาพคมไม่มีปัญหาระดับ serious/critical (${scheme})`, async ({ page }) => {
    await page.emulateMedia({ colorScheme: scheme })
    await openDialog(page)
    await customField(page).fill("2")
    expect(await seriousViolations(page)).toEqual([])
  })
}

test("หน้าต่างแคบ 640 px: ปุ่มและ dialog ไม่ล้นแนวนอน", async ({ page }) => {
  await page.setViewportSize({ width: 640, height: 800 })
  await openDialog(page)
  await customField(page).fill("2")
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(640)
})
```

- [ ] **Step 4: Run the web checks, expect PASS** — `cd web && npm run typecheck && npm run lint && npm test`; the controller runs `npm run build && npm run e2e` at the final gate (both new specs plus `video.spec.ts`).

- [ ] **Step 5: Commit**
```bash
git add web/src/pages/video/frames.tsx web/src/pages/video/tabs.tsx web/e2e/video.spec.ts web/e2e/sharp-dialog.spec.ts
git commit -F- <<'EOF'
feat(web): "ขอภาพคม" in the frames toolbar and the no-storyboard state; dialog e2e

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
EOF
```

### Task 16: Queue e2e with the real fake backend

**Files:**
- Create: `web/e2e/queue-sharp.spec.ts`

**Interfaces:**
- Consumes: C3 fake clips `SHARPCLIP01`, `AUTOSHARP01`; `enqueue`, `waitForJob`, `openQueueSheet`, `cancelJobsFor` (`web/e2e/queue-helpers.ts`); T8, T10, T13, T14 behaviour.
- Produces: the `queue`-project proof of the whole round in fake mode (runs at the final gate).

- [ ] **Step 1: Write the spec** — `web/e2e/queue-sharp.spec.ts`:
```ts
import { expect, test, type Page } from "@playwright/test"

import type { SharpSet } from "../src/lib/types"

import { cancelJobsFor, enqueue, openQueueSheet, waitForJob } from "./queue-helpers"

/**
 * M5 รอบ B กับ backend โหมด fake ตัวจริง (โปรเจกต์ queue): ใช้เฉพาะคลิปปลอม SHARPCLIP01 และ AUTOSHARP01
 * (probe = Big Buck Bunny 635 วิ ภาพเร็ว 128 ภาพ) · โหมด fake ไม่มี ffmpeg ภาพคมทุกภาพเป็นสำเนาของ media/cover.jpg
 */

const SHARP = "SHARPCLIP01"
const AUTO = "AUTOSHARP01"
const VIDEO = { maxQuality: false, splitChapters: false, noAudio: false, audioLanguage: "original" }
const FRAMES = (page: Page) => page.getByRole("list", { name: "รายการภาพเฟรม" }).getByRole("listitem")

test.beforeEach(async ({ request }) => {
  await cancelJobsFor(request, [SHARP, AUTO])
})

test("ภาพคมทุก 60 วินาที: เสร็จได้โฟลเดอร์ 11 ภาพ · หน้า W2 ที่เปิดอยู่สลับเป็นภาพคมเอง · แถวคิวไม่มีปุ่มดาวน์โหลด", async ({
  page,
  request,
}) => {
  await page.goto(`/v/${SHARP}`)
  await expect(FRAMES(page)).toHaveCount(128)
  const [job] = await enqueue(request, [{ videoId: SHARP, kind: "frames_sharp", params: { intervalS: 60 } }])
  const done = await waitForJob(request, (j) => j.id === job.id && j.status === "done", { timeout: 30_000 })
  expect(done.outputs).toHaveLength(1)
  expect(done.outputs![0].files).toBe(11)
  expect(done.outputs![0].name).toMatch(/^คลิปภาพคม - ภาพคม( \(\d+\))?$/)

  // ข่าว SSE ของงานที่เสร็จโหลดชุดภาพคมใหม่ แล้วส่วนภาพเฟรมเปิดภาพคมให้เอง
  const toggle = page.getByRole("group", { name: "ชุดภาพเฟรม" })
  await expect(toggle.getByRole("button", { name: "ภาพคม" })).toHaveAttribute("aria-pressed", "true")
  await expect(FRAMES(page)).toHaveCount(11)

  const row = (await openQueueSheet(page)).locator(`[data-job-id="${job.id}"]`)
  await expect(row).toContainText("คลิปภาพคม · ภาพคม 11 ภาพ")
  await expect(row.getByRole("link", { name: /^ดาวน์โหลด / })).toHaveCount(0)
  await expect(row.getByRole("button", { name: /^เปิดโฟลเดอร์/ })).toBeVisible()
  expect((await request.get(`/api/jobs/${job.id}/outputs/0`)).status()).toBe(404)

  const sharp = (await (await request.get(`/api/videos/${SHARP}/sharp`)).json()) as SharpSet
  expect(sharp.origin).toBe("manual")
  expect(sharp.frames.map((f) => f.tMs)).toEqual(Array.from({ length: 11 }, (_, i) => i * 60_000))
})

test("ภาพรวมเฟรมและ zip จากชุดภาพคม", async ({ request }) => {
  const [sharpJob] = await enqueue(request, [{ videoId: SHARP, kind: "frames_sharp", params: { intervalS: 120 } }])
  await waitForJob(request, (j) => j.id === sharpJob.id && j.status === "done", { timeout: 30_000 })
  const [sheet, zip] = await enqueue(request, [
    { videoId: SHARP, kind: "contact_sheet", params: { source: "sharp", columns: 5 } },
    { videoId: SHARP, kind: "frames_zip", params: { source: "sharp" } },
  ])
  const sheetDone = await waitForJob(request, (j) => j.id === sheet.id && j.status === "done", { timeout: 30_000 })
  const zipDone = await waitForJob(request, (j) => j.id === zip.id && j.status === "done", { timeout: 30_000 })
  expect(sheetDone.outputs![0].name).toMatch(/^คลิปภาพคม - contact sheet( \(\d+\))?\.jpg$/)
  expect(zipDone.outputs![0].name).toMatch(/^คลิปภาพคม - frames( \(\d+\))?\.zip$/)
})

test("ภาพคมอัตโนมัติ: งานวิดีโอ 720p ของ AUTOSHARP01 ได้ไฟล์ mp4 อย่างเดียว และชุดภาพคม 128 ภาพในแอพ", async ({ request }) => {
  const [job] = await enqueue(request, [{ videoId: AUTO, kind: "video", params: VIDEO }])
  const done = await waitForJob(request, (j) => j.id === job.id && j.status === "done", { timeout: 30_000 })
  expect(done.outputs!.map((o) => o.name)).toEqual([expect.stringMatching(/\.mp4$/)])
  expect(done.notes ?? []).toEqual([])
  const sharp = (await (await request.get(`/api/videos/${AUTO}/sharp`)).json()) as SharpSet
  expect(sharp.origin).toBe("auto")
  expect(sharp.frames).toHaveLength(128)
})
```
- [ ] **Step 2: Typecheck and lint** — `cd web && npm run typecheck && npm run lint` (the spec runs at the final gate with `npm run e2e`).
- [ ] **Step 3: Commit**
```bash
git add web/e2e/queue-sharp.spec.ts
git commit -F- <<'EOF'
test(e2e): sharp frames jobs, sharp contact sheet/zip and automatic sharp frames in fake mode

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
EOF
```

### Task 17: Docs (PRD, BRD, acceptance, follow-ups) and the network test (written, not run)

**Files:**
- Modify: `PRD.md`, `BRD.md`, `docs/acceptance.md`, `docs/m4-followups.md`, `docs/m5a-followups.md`
- Modify: `tests/network_videos.toml`, `tests/unit/test_yterrors.py` (`PRD_PENDING` back to empty)
- Create: `tests/network/test_sharp_network.py`

**Interfaces:**
- Consumes: everything above (final names, strings, notes, behaviour).
- Produces: docs that match the code (spec 7); a network test Pete can approve and run.

- [ ] **Step 1: PRD.md** — find each anchor with `rg -n` first; edit with the Edit tool (LF kept).
  1. The W2 component row starting `| **ภาพเฟรม** | Card,`: append to the end of its third cell (before the final ` |`): ` · **M5 รอบ B ภาพคม:** ปุ่ม "ขอภาพคม" อยู่ถัดจากปุ่ม "โหลดภาพรวมเฟรม" / "โหลดทั้งหมด (.zip)" และในหน้าคลิปที่ไม่มี storyboard · กดแล้วเปิด dialog: "เวลาเดียวกับภาพเร็ว" (ค่าเริ่มต้น) หรือ "ตั้งเอง ทุก N วินาที" (1-3600) บอกจำนวนภาพ ขนาดวิดีโอชั่วคราว และความละเอียด (ด้านยาว 1280 px) ก่อนส่งเข้าคิว · เกิน 200 ภาพ = บอกช่วงห่างใหม่แบบสดแล้วส่งช่วงนั้น (AC-FRAME-04) · คลิปสด = ปุ่มปิดพร้อม tooltip "คลิปสดยังขอภาพคมไม่ได้" · มีงานในคิว = "กำลังดึงภาพคม…" · มีชุดภาพคมแล้ว หัวส่วนมี Toggle Group [ภาพเร็ว | ภาพคม] (ค่าเริ่มต้นภาพคม จำแค่รอบที่เปิดหน้า) ทุกอย่างของภาพเร็ว (ภาพใหญ่ ▶ เมนูคลิกขวา ดูซ้ำบ่อย ?at=) ใช้กับภาพคมได้ · ปุ่มโหลดทั้งชุดใช้ชุดที่เห็นอยู่ (`source`) · สเปก `docs/superpowers/specs/2026-10-05-m5b-sharp-frames-design.md``.
  2. Replace the three job-table rows:
```markdown
| `frames_sharp` | `{intervalS?: 1-3600, folder?}` (M5 รอบ B · ไม่ส่ง = เวลาเดียวกับภาพเร็ว · คลิปไม่มี storyboard = ทุก max(1, ⌈ความยาว/100⌉) วินาที · เกิน 200 ภาพปรับเป็นทุก ⌈ความยาว/200⌉ วินาทีพร้อมหมายเหตุ `SHARP_INTERVAL_RAISED`) | โหลดวิดีโออย่างเดียว ด้านสั้น ≤ 720 (SDR ก่อน · avc1 > vp9 > av01 · ไฟล์เล็กสุด) ลง `work/` → ffmpeg ดึงทีละภาพ (`-ss` ก่อน `-i` ย่อด้านยาว 1280 ไม่ขยาย `-q:v 2`) → ลบวิดีโอ → เก็บใน cache ของแอพ (`<cache>/<id>/sharp/` แทนชุดเดิม) และโฟลเดอร์ `<ชื่อคลิป> - ภาพคม` ในโฟลเดอร์ของคลิป (`frame_HH-MM-SS.jpg` ซ้ำวินาที `_2` · ชื่อซ้ำ ` (2)`) · ผลของงาน = โฟลเดอร์ (เปิดโฟลเดอร์ได้ ไม่มีดาวน์โหลด) · ขั้น `downloading_video` → `extracting_frames:i/n` → `writing` · ด้านสั้นสูงสุดต่ำกว่า 720 = หมายเหตุ `SHARP_LOW_RES` · มีแต่ HDR = tone-map |
| `contact_sheet` | `{source: fast\|sharp, columns: 5}` | Pillow ประกอบภาพ + ฟอนต์ IBM Plex Sans Thai (ฝังในแอพ) ช่องละ 320×180 (ภาพคมย่อลงช่อง) ชื่อไฟล์ `<ชื่อคลิป> - contact sheet.jpg` · `source: "sharp"` (M5 รอบ B) อ่านชุดภาพคมใน cache ชุดหาย = `E_NO_SHARP_FRAMES` |
| `frames_zip` | `{source: fast\|sharp}` | zip ภาพเฟรม ชื่อไฟล์ `<ชื่อคลิป> - frames.zip` · `source: "sharp"` ตั้งแต่ M5 รอบ B (ชุดหาย = `E_NO_SHARP_FRAMES`) |
```
  3. In the strictness bullet starting `- **ตรวจ params เข้ม**` replace `` `useCookies` (M5 รอบ C) และ `kind: "frames_sharp"` / `source: "sharp"` (M5 รอบ B) ยังถูกปฏิเสธ `` with `` `useCookies` (M5 รอบ C) ยังถูกปฏิเสธ · `frames_sharp` รับ `{intervalS?, folder?}` และ `source: "fast" | "sharp"` แล้ว (M5 รอบ B) · `frames_sharp` ของคลิปสดหรือไม่รู้ความยาว (มีข้อมูลคลิปใน cache) → 422 · ไม่มี ffmpeg → 409 `E_FFMPEG_MISSING` ``.
  4. Error table: replace the `E_NO_STORYBOARD` row and add the new one right after it:
```markdown
| `E_NO_STORYBOARD` | คลิปนี้ไม่มีภาพตัวอย่างแบบเร็ว กด "ขอภาพคม" แทนได้ | ปุ่ม "ขอภาพคม" กดได้ (M5 รอบ B) · M2-M4 ใช้ "…ภาพคมจะใช้ได้ในเวอร์ชันถัดไป" (BRD #33) |
| `E_NO_SHARP_FRAMES` | ภาพคมของคลิปนี้ถูกล้างไปแล้ว กด "ขอภาพคม" ใหม่ได้ | งาน contact sheet / zip แบบ `source: "sharp"` เมื่อชุดภาพคมใน cache หายไป · `GET /videos/{id}/sharp` ตอบ 404 รหัสนี้เมื่อยังไม่มีชุด (หน้าเว็บถือว่า "ยังไม่มีภาพคม") (M5 รอบ B) |
```
     and in the line starting `- **HTTP status ของ error จากยูทูป:**` add `` `E_NO_SHARP_FRAMES` `` to the 404 list (after `` `E_NO_SUBTITLES` ``).
  5. Settings table: after the `sponsorblockDefault` row add `| \`autoSharpFrames\` | bool | \`true\` · ทำภาพคมอัตโนมัติหลังงานวิดีโอทั้งคลิป (ไม่มีช่วงเวลา/ตัดโฆษณา/แยก chapter) ที่ไฟล์ด้านสั้น ≥ 720 และไม่ใช่ HDR · ใช้ไฟล์ที่โหลดแล้ว ลง cache ของแอพอย่างเดียว พังหรือยกเลิกไม่ทำให้งานวิดีโอล้ม (M5 รอบ B D6) |`.
  6. In the bullet starting `- **หมายเหตุของงาน:**` append: ``, `SHARP_LOW_RES` ("คลิปนี้มีภาพสูงสุด {h}p ภาพจึงเล็กกว่าปกติ"), `SHARP_INTERVAL_RAISED` ("ปรับเป็นทุก {n} วินาทีเพื่อไม่ให้เกิน 200 ภาพ") (M5 รอบ B เก็บเป็น `"<รหัส>:<ค่า>"`)``.
  7. Replace the `AC-FRAME-03` row with `| AC-FRAME-03 | โหมดคมให้ timecode ชุดเดียวกับโหมดเร็ว ภาพด้านยาว ≥ 1280 px (แนวนอน 1280×720 · แนวตั้ง 720×1280 BRD D4 ของ M5 รอบ B) และลบไฟล์วิดีโอชั่วคราวหลังเสร็จ | A |`.
- [ ] **Step 2: BRD.md**
  1. Append to the `| 33 |` row's decision cell (before ` · M2 |`): ` · **M5 รอบ B เปลี่ยนแล้ว** ปุ่มกดได้`.
  2. Append after row `| 128 |` (same 4 columns):
```markdown
| 129 | **ภาพคมโหลดทั้งคลิปแบบภาพอย่างเดียว ≤ 720p ลงโฟลเดอร์ทำงาน แล้ว ffmpeg ดึงภาพ ลบวิดีโอทันที** (ไม่ seek เข้าสตรีมยูทูปหรือโหลดทีละช่วง) · M5 รอบ B (D1) | ✅ | 100-200 คำขอติดกันเสี่ยงโดนเช็กบอทจนคิวพัก และพังเมื่อลิงก์หมดอายุ · ใช้เส้นทางโหลดเดิม (เว้นช่วง เบรก ความคืบหน้า ยกเลิก) แลกกับคลิปยาวต้องโหลดเต็ม (1 ชม. ราว 300-800 MB ลบทันที) · พิธอนุมัติ 2026-10-05 |
| 130 | **ภาพคมเก็บทั้งในแอพและเป็นโฟลเดอร์ JPG ในโฟลเดอร์ผลลัพธ์** · M5 รอบ B (D2) | ✅ | ทีมเห็นภาพคมในแอพและได้ไฟล์ใช้ต่อได้ทันที · พิธเลือก 2026-10-05 |
| 131 | **"ขอภาพคม" เปิด dialog เล็กก่อนส่งงาน** เลือกเวลาเดียวกับภาพเร็ว (ค่าเริ่มต้น) หรือทุก N วินาที บอกจำนวนภาพและขนาดวิดีโอชั่วคราว · M5 รอบ B (D3) | ✅ | FR-FRAME-3 ต้องตั้งช่วงห่างเองได้ และการโหลดชั่วคราวอาจใหญ่ ต้องบอกก่อน · พิธเลือก 2026-10-05 |
| 132 | **"720p" = ด้านสั้น ≤ 720 ภาพย่อให้ด้านยาว 1280 px** คลิปแนวตั้งได้ 720×1280 · AC-FRAME-03 "ภาพ ≥ 1280 px กว้าง" อ่านว่า "ด้านยาว ≥ 1280" · M5 รอบ B (D4) | ✅ | ภาพแนวตั้งกว้าง 1280 ต้องโหลด 1080p หนักขึ้นมากโดยไม่ได้ประโยชน์ · ครีมตัดสิน พิธเปลี่ยนได้ 2026-10-05 |
| 133 | **ภาพคมในแอพมีชุดเดียวต่อคลิป** ขอใหม่แทนชุดเดิม · โฟลเดอร์ในโฟลเดอร์ผลลัพธ์ไม่ถูกเขียนทับ ขอซ้ำได้ ` (2)` · M5 รอบ B (D5) | ✅ | ส่วนภาพเฟรมเรียบง่าย ภาพเร็วหนึ่งชุด ภาพคมไม่เกินหนึ่งชุด ไฟล์ที่ผู้ใช้มีแล้วไม่ถูกแตะ · พิธอนุมัติ 2026-10-05 |
| 134 | **ภาพคมอัตโนมัติหลังงานวิดีโอ** (ทั้งคลิป ด้านสั้น ≥ 720 ไม่ใช่ HDR) ลง cache ของแอพอย่างเดียว ค่าตั้ง `autoSharpFrames` เปิดไว้ตั้งต้น · M5 รอบ B (D6) | ✅ | ไฟล์อยู่ในเครื่องแล้ว ไม่ต้องใช้เน็ตและไม่เสี่ยงเช็กบอท (ราว 10-40 วินาทีต่อคลิป) · ไม่ลงโฟลเดอร์ผลลัพธ์เพราะ JPG 100 ไฟล์ข้างทุกวิดีโอรก · พิธเลือก 2026-10-05 |
| 135 | **ยังไม่มีภาพคมใน W3** ในรอบ B (ภาพคมอัตโนมัติยังทำกับงานวิดีโอจาก W3) · M5 รอบ B (D7) | ✅ | คลิปละหลายร้อย MB ติ๊กทั้งเพลย์ลิสต์หนักเกิน เพิ่มทีหลังได้ถ้ามีคนขอ · พิธอนุมัติ 2026-10-05 |
| 136 | **ภาพคมที่ขอเองเลือก format SDR ก่อน (tone-map เฉพาะคลิปที่มีแต่ HDR) ภาพคมอัตโนมัติข้ามไฟล์ HDR** · M5 รอบ B (D8) | ✅ | ยูทูปมี SDR คู่กับ HDR งานที่ขอเองจึงเลี่ยงปัญหาสีซีดได้ ไฟล์ที่ผู้ใช้เลือกโหลดไม่ควรถูก tone-map เงียบ ๆ · พิธอนุมัติ 2026-10-05 |
```
- [ ] **Step 3: docs/acceptance.md** — append after the M5 รอบ A section:
```markdown
## M5 รอบ B (ทำบน Windows 10/11 กับยูทูปจริง)
| AC | ขั้นตอน | ผ่าน |
|---|---|---|
| M5B-DIALOG | เปิดคลิป 720p ขึ้นไป แท็บภาพเฟรม กด "ขอภาพคม" (ถัดจากปุ่มโหลด zip) เห็น dialog "ขอภาพคม" เลือก "เวลาเดียวกับภาพเร็ว" อยู่ บรรทัดรองบอก "ทุก ~… วินาที · … ภาพ" เท่าจำนวนภาพเร็ว · มีบรรทัด "ต้องโหลดวิดีโอชั่วคราวราว … (ลบทิ้งเมื่อเสร็จ)" และ "ภาพกว้าง 1280 px" · กด "เริ่มดึงภาพคม" ขึ้น "เพิ่มเข้าคิวแล้ว" ปุ่มกลายเป็น "กำลังดึงภาพคม…" แถวคิวขึ้น "โหลดภาพ" แล้ว "กำลังดึงภาพ 1/…" | ☐ |
| M5B-RESULT | งานเสร็จ: ชื่องาน "<ชื่อคลิป> · ภาพคม n ภาพ" · "เปิดโฟลเดอร์" เปิดโฟลเดอร์ `<ชื่อคลิป> - ภาพคม` ในโฟลเดอร์ของคลิป ภาพ `frame_HH-MM-SS.jpg` เวลาตรงกับภาพเร็ว กว้าง 1280 px (AC-FRAME-03) · ใน `work/` ของโปรแกรมไม่มีไฟล์วิดีโอค้าง · ไม่มีปุ่ม "ดาวน์โหลด" ในแถวนี้ | ☐ |
| M5B-OVER200 | ใน dialog เลือก "ตั้งเอง" พิมพ์ 2 กับคลิปยาวกว่า 7 นาที ประโยค "ทุก 2 วินาทีจะได้ … ภาพ เกินที่ดึงได้ 200 ภาพ จะใช้ทุก … วินาทีแทน" ขึ้นทันทีขณะพิมพ์ · พิมพ์ 0 หรือ 1.5 ขึ้น "ใส่เลขวินาทีเต็ม 1-3600" และกดเริ่มไม่ได้ (AC-FRAME-04) | ☐ |
| M5B-GRID | ระหว่างเปิดหน้าคลิปไว้ งานภาพคมเสร็จ ส่วนภาพเฟรมเปลี่ยนเป็นภาพคมเองพร้อมปุ่ม [ภาพเร็ว \| ภาพคม] · กดภาพเร็ว/ภาพคมสลับได้ · คลิกภาพคมเปิดภาพใหญ่คม · ▶ เล่นจากเวลาของภาพ · คลิกขวาคัดลอกภาพไปวางใน LINE/PowerPoint ได้ภาพคม · "ตั้งเป็นจุดเริ่ม" ใช้เวลาของภาพคม | ☐ |
| M5B-BULK | เลือกภาพคมแล้วกด "โหลดภาพรวมเฟรม" และ "โหลดทั้งหมด (.zip)": ภาพรวมเฟรมคมกว่าแบบภาพเร็ว zip มีภาพคมครบ · สลับเป็นภาพเร็วแล้วกดอีกครั้งได้ชุดภาพเร็ว | ☐ |
| M5B-AUTO | หน้าตั้งค่า ทั่วไป สวิตช์ "ทำภาพคมอัตโนมัติตอนโหลดวิดีโอ" เปิดอยู่ · โหลด mp4 ทั้งคลิปของคลิป 720p/1080p งานขึ้น "กำลังทำภาพคม i/n" หลังบันทึกไฟล์ เสร็จแล้วหน้าคลิปมีภาพคมโดยไม่ได้กดขอ และโฟลเดอร์ของคลิปมีแค่ mp4 กับแหล่งที่มา.txt · ปิดสวิตช์แล้วโหลดคลิปอื่น ไม่มีขั้น "กำลังทำภาพคม" · โหลดแบบตั้งช่วงเวลาก็ไม่มี | ☐ |
| M5B-SHORTS | คลิปแนวตั้ง (Shorts) ขอภาพคม: dialog บอก "ภาพสูง 1280 px" ได้ภาพ 720×1280 | ☐ |
| M5B-NOSB | คลิปที่ไม่มีภาพตัวอย่าง: ข้อความ "คลิปนี้ไม่มีภาพตัวอย่างแบบเร็ว กด "ขอภาพคม" แทนได้" ปุ่มกดได้ dialog ไม่มีตัวเลือกเวลาเดียวกับภาพเร็ว เสร็จแล้วส่วนภาพเฟรมแสดงภาพคม | ☐ |
| M5B-CANCEL | ยกเลิกงานภาพคมระหว่าง "กำลังดึงภาพ": งานหยุดภายใน 3 วินาที ภาพคมชุดเดิมในแอพยังอยู่ ไม่มีโฟลเดอร์ ` - ภาพคม` ใหม่ · ปิดโปรแกรมด้วย stop.bat ระหว่างงาน เปิดใหม่ไม่มีโฟลเดอร์ค้าง | ☐ |
| M5B-NARROW | ซูม 200% (หรือหน้าต่างกว้าง 640 px) เปิด dialog ขอภาพคมและปุ่มสลับชุดภาพ ไม่มีแถบเลื่อนแนวนอน (BRD #83) | ☐ |
```
- [ ] **Step 4: Follow-ups** — `docs/m4-followups.md`: in the bullet starting `- **ตัวเลือกขั้นสูงของ W2**` replace `` และ `frames_sharp` (ภาพคม รอบ B) ยังได้ 422 `` with `` ยังได้ 422 · `frames_sharp` รับแล้วในรอบ B ``; append ` **(ทำแล้วใน M5 รอบ B)**` to the bullet starting `- **ภาพเฟรมโหมดคม**`. `docs/m5a-followups.md`: append to the bullet starting `- **คลิป HDR:**`: ` · **M5 รอบ B:** ภาพคมที่ขอเองเลือก format SDR ก่อน (tone-map เฉพาะคลิปที่มีแต่ HDR) ภาพคมอัตโนมัติข้ามไฟล์ HDR · การตัดช่วงของรอบ A ยังเหมือนเดิม`.
- [ ] **Step 5: tests/network_videos.toml** — append:
```toml

[sharp]
# M5 รอบ B (T17): คลิปของ tests/network/test_sharp_network.py · ตรวจข้อมูลคลิปซ้ำก่อนรันถ้าห่างหลายเดือน
clip = "88o5Sk8_m1Y"            # 372 วิ มี storyboard มีถึง 1080p: ภาพคม 720p video-only ราว 30-50 MB
portrait_clip = "IngFfl6DTqY"   # 60 วิ แนวตั้ง: ต้องได้ภาพ 720×1280 (D4) ราว 10-20 MB
```
- [ ] **Step 6: tests/unit/test_yterrors.py** — set `PRD_PENDING: set[str] = set()` again (Step 1.4 added the PRD row).
- [ ] **Step 7: Write the network test** — `tests/network/test_sharp_network.py`:
```python
"""M5 รอบ B กับยูทูปจริง: งานภาพคมผ่าน handler ของคิว + yt-dlp จริง + ffmpeg จริง (AC-FRAME-03, D4)

ต้องได้รับอนุญาตจากพิธก่อนรัน: โหลดวิดีโออย่างเดียว 720p ราว 40-70 MB ลง temp ลบทิ้งเมื่อทุกเทสผ่าน
รันเองด้วย: uv run pytest -m network -q tests/network/test_sharp_network.py -s
id ของคลิปอยู่ใน tests/network_videos.toml ([sharp]) · ยูทูปตอบ 429 หรือขอยืนยันว่าไม่ใช่บอท = เทสตก ให้รายงานผล ห้ามแก้เทสให้หลวมลง
"""

from __future__ import annotations

import shutil
import time
import tomllib
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest
from helpers_ffmpeg import requires_ffmpeg
from PIL import Image

from yttoolkit.core.db import Database
from yttoolkit.core.extractor import YtDlpExtractor, visitor_session, ytdlp_version
from yttoolkit.core.handlers import HandlerDeps, build_handlers
from yttoolkit.core.jobs import Job, JobResult
from yttoolkit.core.media import FfmpegTools
from yttoolkit.core.sharp_store import read_sharp
from yttoolkit.core.subtitles import SubtitleService
from yttoolkit.core.videos import VideoService

pytestmark = [pytest.mark.network, requires_ffmpeg]

_TOML = Path(__file__).resolve().parents[1] / "network_videos.toml"
CLIPS: dict[str, str] = tomllib.loads(_TOML.read_text(encoding="utf-8"))["sharp"]
QUEUE_GAP_S = 2
JOB_ID = "01900000-0000-7000-8000-0000000000bb"


class Ctx:
    """JobContext ขั้นต่ำสำหรับเรียก handler ตรง ๆ (ไม่ผ่านคิว)"""

    def __init__(self, workdir: Path, output_root: Path) -> None:
        self.job_id = JOB_ID
        self.workdir = workdir
        self.output_root = output_root

    def stage(self, stage: str) -> None:
        return None

    def progress(self, fraction: float | None, speed_bps: int | None = None, eta_s: int | None = None) -> None:
        return None

    def set_title(self, title: str) -> None:
        return None

    def cancelled(self) -> bool:
        return False

    def check_cancelled(self) -> None:
        return None

    def wait(self, seconds: float) -> None:
        time.sleep(seconds)


def _job(video_id: str, params: dict[str, Any]) -> Job:
    return Job(
        id=JOB_ID, video_id=video_id, title="", kind="frames_sharp", params=params, status="running", stage=None,
        progress=None, speed_bps=None, eta_s=None, attempt=0, bot_checks=0, position=0, error_code=None,
        error_message=None, error_detail=None, notes=(), outputs=(), created_at="2026-10-05T00:00:00Z",
        started_at=None, finished_at=None,
    )  # fmt: skip


@dataclass
class Env:
    root: Path
    handlers: dict
    counter: int = 0
    last: float = 0.0

    def run(self, video_id: str, params: dict[str, Any]) -> tuple[JobResult, Path]:
        wait = QUEUE_GAP_S - (time.monotonic() - self.last)
        if wait > 0:
            time.sleep(wait)
        self.last = time.monotonic()
        self.counter += 1
        workdir = self.root / "work" / str(self.counter)
        workdir.mkdir(parents=True)
        return self.handlers["frames_sharp"](_job(video_id, params), Ctx(workdir, self.root / "output")), workdir


@pytest.fixture(scope="module")
def env(tmp_path_factory: pytest.TempPathFactory, request: pytest.FixtureRequest) -> Iterator[Env]:
    root = tmp_path_factory.mktemp("sharp-network")
    ffmpeg = shutil.which("ffmpeg")
    assert ffmpeg is not None
    ytdlp_version()
    db = Database(root / "app.db")
    db.migrate()
    session = visitor_session(root / "data")
    extractor = YtDlpExtractor(session=session)
    videos = VideoService(db, extractor)
    deps = HandlerDeps(
        videos=videos,
        downloader=extractor,  # type: ignore[arg-type]
        media=FfmpegTools(lambda: Path(ffmpeg)),
        subtitles=SubtitleService(videos, extractor.fetch_subtitle, root / "cache", session=session),
        cache_root=root / "cache",
    )
    try:
        yield Env(root, build_handlers(deps))
    finally:
        extractor.close()
        db.close()
        if request.session.testsfailed:
            print(f"[kept for inspection] {root}")
        else:
            shutil.rmtree(root, ignore_errors=True)


def _sizes(folder: Path) -> set[tuple[int, int]]:
    out = set()
    for path in folder.iterdir():
        with Image.open(path) as img:
            assert img.format == "JPEG"
            out.add(img.size)
    return out


def test_ac_frame_03_landscape_1280_and_the_video_is_deleted(env: Env) -> None:
    result, workdir = env.run(CLIPS["clip"], {"intervalS": 60})
    (out,) = result.outputs
    folder = Path(out.root) / out.rel
    assert out.kind == "folder" and out.files == 7  # 372 วิ: 0, 60, ..., 360
    assert _sizes(folder) == {(1280, 720)}
    assert [f["tMs"] for f in read_sharp(env.root / "cache", CLIPS["clip"])["frames"]] == list(range(0, 420_000, 60_000))
    assert not list(workdir.glob("media.*"))


def test_d4_portrait_clip_gives_720_by_1280(env: Env) -> None:
    result, _ = env.run(CLIPS["portrait_clip"], {"intervalS": 10})
    (out,) = result.outputs
    assert _sizes(Path(out.root) / out.rel) == {(720, 1280)}
```
- [ ] **Step 8: Check without running the network** — `uv run pytest -q -W error -p no:cacheprovider` (the new file is collected but deselected by `-m 'not network'`; `test_yterrors.py` now checks the `E_NO_SHARP_FRAMES` PRD row) and `uv run python -m py_compile tests/network/test_sharp_network.py`. Do **not** run `-m network`.
- [ ] **Step 9: Commit**
```bash
git add PRD.md BRD.md docs/acceptance.md docs/m4-followups.md docs/m5a-followups.md tests/network_videos.toml tests/unit/test_yterrors.py tests/network/test_sharp_network.py
git commit -F- <<'EOF'
docs: M5 round B in PRD/BRD/acceptance/follow-ups; network test for AC-FRAME-03 and portrait frames

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
EOF
```

---

## Spec coverage (self-review)

| Spec item | Task(s) |
|---|---|
| Owner decisions D1-D8 | table at the top; D1 T3/T8 · D2 T5/T8 · D3 T2/T11/T15 · D4 T3/T4/T17 · D5 T5/T8 · D6 T1/T12/T14 · D7 (no W3 change; T14 covers W3 `video` jobs) · D8 T3/T4/T14 |
| §1.1 toolbar button, active empty-state button, no tooltip, `E_NO_STORYBOARD` copy in yterrors + th.ts | T15, T6 (copy, tooltip removed), T1 |
| §1.2 disabled states (live tooltip, "กำลังดึงภาพคม…" + spinner, focusable) | T11 (`sharpBlock`, `sharpJobBusy`), T15 e2e |
| §1.3 dialog: radio group, interval one decimal, count live, 1-3600 validation, size line (known/unknown, largest short side ≤ 720), resolution line (wide/tall/low), over-200 sentence + `intervalS = N2`, replace warning, no-storyboard default, buttons, enqueue toast | T2 (`sharpDialogModel`, `sharpEstimate`, `parseIntervalText`), T11, T15 e2e |
| §1 maths shared with the backend (`sharp-frames.ts` + same cases) | T2 (golden JSON read by both suites) |
| §2 toggle (`aria-label`, default sharp, memory per visit, absent without sharp), auto-switch on `done`, everything works on the sharp set (menu, ▶, now playing, replayed, `?at=`), sharp-only clip, bulk buttons follow the toggle, contact sheet downscale | T10 (+ e2e), T5 (`_load_cell` pad), T16 (auto-switch end to end) |
| §3.1 params, strict keys, `source`, live/unknown 422 + handler re-check, `FFMPEG_KINDS`, `YOUTUBE_KINDS`, web `NewJob`/params types | T7, T3, T8, T6 |
| §3.2 plan (same times, > 200 fallback, custom, raise, no storyboard default, note) | T2, T8 |
| §3.3 format selection (SDR, short side ≤ 720, avc1 > vp9 > av01, size, muxed fallback, low-res note, HDR-only tone-map) | T3, T4, T8 |
| §3.4 one ffmpeg call per frame, `-ss` before `-i`, scale rule, `-q:v 2`, cancel between frames, progress i/n, dropped end frames, zero = `E_UNKNOWN`, fake mirrors validation | T4, T8 |
| §3.5 stages + Thai stage text, queue title, output folder naming (`file_timecode`, `_2`, ` (2)`, safe name), single folder output + "เปิดโฟลเดอร์", cache, work folder deleted (asserted), disk check formula | T1, T13, T5, T7, T8 |
| §4 setting + switch + hint, run conditions, timing after finalize, `sharp_frames:i/n`, same plan, cache only `origin: "auto"`, never fatal, cancel ends `done`, no note | T1, T12, T14 |
| §5 cache layout + index, atomic replacement, startup sweep (tmp/old + partial output folders), `GET /sharp` 200/404, purge (unchanged), sharp contact sheet/zip + `E_NO_SHARP_FRAMES` | T5, T9, T7, T8 |
| §6 edge table (no 720p, HDR, bot check via the M4 download path, disk/ffmpeg preflight, cancel, app closed, live, purged set, two jobs, deleted output folder) | T3, T4, T8, T7, T9, T14; the last two rows reuse the M4 behaviour (`commit_sharp` replaces, ` (2)` folders, reveal 404 → "ไม่พบไฟล์…") |
| §7 docs (PRD rows, BRD D1-D8 + D4 note, acceptance M5-B, m4/m5a follow-ups, network clip + test) | T17 |
| §8 tests: Python units, real-ffmpeg integration (timecodes, 1280 long side, 720×1280, temp video gone), Vitest parity + dialog state + bulk source, chromium e2e (dialog, over-200, replace, live/in-queue, no storyboard, toggle, auto-switch, menu, bulk, settings, axe, 640 px), queue spec, network test | T1-T5, T7-T9, T14 (Python) · T4, T8 (integration) · T2, T10, T11, T13 (Vitest) · T10, T12, T15 (chromium) · T16 (queue) · T17 (network) |
| Review Focus 1-5 | T5, T5, T8, T2+T8, T14 (test names listed in the section) |

Self-review checks run on this plan: no "TBD"/"TODO"/"similar to Task N"; every function a later task uses is defined in a contract and in exactly one earlier task (`count_stage`/`valued_note`/`note_api`/`OutputFile.files` T1 · `plan_sharp`/`fast_times`/`MAX_INTERVAL_S`/`sharpDialogModel`/`sharpKey` T2 · `sharp_choice`/`SharpPick`/`MediaFacts`/`DownloadResult.media` T3 · `extract_frame`/`FrameCall`/`SHARP_LONG_SIDE` T4 · `prepare_sharp`/`commit_sharp`/`discard_sharp`/`read_sharp`/`sweep_sharp_leftovers`/`plan_sharp_dir`/`move_files_into_dir`/`PARTIAL_MARKER`/`frame_file_names`/`frame_file_name` T5 · `SharpSet`/`FrameSource`/`JobOutput.files` T6 · `_clip_duration_s`/`_extract_frames`/`_created_at`/`helpers_sharp` T8 · `sharpQuery`/`frameSetShown`/`sharpRefreshTarget` T10 · `SharpRequestButton`/`sharpBlock`/`sharpJobBusy` T11 · `jobTitle`/`sharpCount` T13 · `HandlerDeps.auto_sharp` T14); names match across tasks (`extracting_frames` / `sharp_frames` everywhere, `SHARP_INTERVAL_RAISED:<n>` / `SHARP_LOW_RES:<h>`, `E_NO_SHARP_FRAMES`, `origin` `"manual"|"auto"`); every file appears in exactly one lane per wave (table in Lane rules); `th.ts` is written only by T6.

---

## Execution handoff

Plan saved to `docs/superpowers/plans/2026-10-05-m5b-sharp-frames.md`. Execute with superpowers:subagent-driven-development: one fresh subagent per task in its own worktree (lanes of a wave in parallel: wave 1 = T1-T6, wave 2 = T7-T13, wave 3 = T14-T17), the wave gate procedure between waves, the two-stage review per task, then the final gate (build, e2e, `web/dist` commit, live preview for Pete in fake mode with `SHARPCLIP01` / `AUTOSHARP01`). The network test runs only after Pete approves the ~40-70 MB download.
