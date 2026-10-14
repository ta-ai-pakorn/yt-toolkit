# M6 round A: paste button, filename style, clearing temporary data, settings backup (design)

Pete approved the design in conversation on 2026-10-14 (decisions file below). This written spec turns it into an implementable design. Every Thai string is sourced (§9); the gaps are listed in §11 with drafts and wait for Pete.

Round A implements four PRD M6 items:
- the **"วาง"** button in W1 (BRD FR-IN-7, PRD W1 table `PRD.md:101`, AC-IN-08 / AC-IN-09);
- the **filename style** with its live example (BRD FR-OUT-8, `PRD.md:306`, AC-OUT-09 / AC-OUT-10);
- **clearing temporary data** (BRD FR-SET-6, `PRD.md:307`, `:325`, `:619-620`, AC-SET-07 / AC-SET-08);
- **settings backup / import** (BRD FR-SET-7, `PRD.md:307`, `:617-618`, `:814`, AC-SET-09 / AC-SET-10, `E_SETTINGS_INVALID`).

It touches:
- `core/files.py` (one naming function shared with the web), `core/handlers.py` (`_finish` and `_Clip`), `core/download.py` + `core/extractor.py` (audio bitrate fact), `core/queue.py` and `core/jobs.py` (style snapshot), `core/db.py` (schema v3), `lifecycle.py` (leftover sweep);
- a new `core/storage.py` + `api/storage.py`, `core/capture.py` (active capture state);
- `core/settings.py` (tolerant import), `api/settings.py` (export / import), `core/yterrors.py`, `core/videos.py` (`channel` in history);
- the web: `pages/home.tsx`, `lib/paste.ts`, a new `lib/filename.ts`, `pages/settings/general-panel.tsx` and new files beside it, `lib/settings-api.ts`, `lib/types.ts`, `pages/history/queries.ts`, `pages/home/recent.tsx`, `i18n/th.ts`;
- PRD §6.1, §6.2, §6.4, §7 and `docs/acceptance.md` (done in this commit, §8).

Code facts were checked at HEAD `bce3f4b` (branch `main`).

## Owner decisions (2026-10-14)

These are binding. They come from Pete's answers to Q1-Q3 and the approved approach.

| # | Decision | Where |
|---|---|---|
| D1 | **"วาง" replaces the box content** (Q1 = A). A YouTube link starts analysis at once; other text is only filled in. `readText()` is called only on click. Denied or unsupported → the PRD hint under the box + focus the box; no red error, no toast. | §1 |
| D2 | **Clear temporary data** (Q2 = A) clears `data/cache/<id>/` (storyboard, sharp, captures, subs, `pinned.json`) and stale `work/` dirs (`work/<jobId>`, `work/capture-*`). It never deletes the cache or work of an active job or capture, outputs, `app.db` (history, videos, settings), the visitor session (`data/visitor-session.*`) or `run/logs`. Reopening an old clip re-fetches its frames; every cache reader must tolerate a missing folder. | §3 |
| D3 | **Which files get the style** (Q3 = A). `title-channel`: every title-based file of a clip (video, audio, subtitles `.lang`, note `.note`, contact sheet, frames zip). `title-quality`: only video and audio, as `(1080p)` / `(mp3 192k)`; other kinds keep the plain title + their suffix. Unchanged: chapter-split files, captures, the sharp-frames dir and the clip folder `<title> [<id>]`. Too long → cut the title first, then the channel; never the quality part or the extension. FR-OUT-2 rules; path ≤ 240. | §2 |
| D4 | **The job snapshots the style when it starts**; the snapshot stays on the job so a retry keeps the name and the leftover sweep still finds files. Changing the style mid-run does not rename a running job. | §2.4 |
| D5 | **The example is computed in the web without an API call** (AC-OUT-10), by a TS mirror of the Python rules with shared fixture parity tests. It uses the latest opened clip's title, else the PRD's Thai sample. | §2.6 |
| D6 | **Backup / import:** `GET /settings/export` (attachment `yt-toolkit-settings-YYYY-MM-DD.json`, `{app, schema:1, exportedAt, settings}`, no `statsResetAt`, cookies, history or stats). `POST /settings/import`: token, 1 MB cap (413), all-or-nothing validation (non-JSON, `app` ≠ `yt-toolkit`, bad type → 422 `E_SETTINGS_INVALID`, nothing changes), unknown keys skipped, unwritable `outputDir` keeps the old value + `warnings: ["outputDir"]`, returns `{settings, warnings}`, fires the `on_output_dir` hook. `E_SETTINGS_INVALID` goes into `MESSAGES` and `th` with the PRD text. | §4 |
| D7 | **Storage API:** `GET /storage` → `{cacheBytes, workBytes, reclaimableBytes}`, `POST /storage/clear` → `{freedBytes}`, in a new router; reuse the `_remove_cache_folder` safety; sizes within 1 % (AC-SET-07); a running job is safe (AC-SET-08). | §3 |
| D8 | **UI:** the General tab gets a "ข้อมูลในเครื่อง" section (PRD.md:307) and the filename-style Select + example; errors use M6-B `showErrorToast` / `ErrorDetails`. 640 px narrow window. | §5 |
| D9 | **Future sites** (owner constraint, 2026-10-14): do not build multi-site support; nothing new in round A may paint the app into a YouTube-only corner (C12). | C12, §10 |

## Global constraints

Every task in the plan for this round must hold all of these. A reviewer rejects a change that breaks one.

- **C1 No `shell=True`.** No new subprocess is needed in this round.
- **C2 Only `yttoolkit.platform` checks the OS.** No `sys.platform`, `os.name` or `platform.system()` elsewhere. Junction detection in the size walk uses `os.DirEntry.is_junction()` (Python ≥ 3.12, cross-platform API, returns `False` off Windows), not an OS check.
- **C3 `yt_dlp` is imported only in `core/extractor.py`.** The new audio-bitrate fact is read there and passed out through `download.MediaFacts` (§2.3).
- **C4 Nothing personal leaves the app.** No clip titles, channel names, absolute paths, the token, or cookie names / values in `app.log`, SSE or API error bodies. New log lines use ASCII `key=value` fields with ids, counts and error class names only. The import never echoes a value from the file in `detail`. The exported settings file is a user download, not a log or an error; it carries `outputDir` on purpose (FR-SET-7 "เปลี่ยนเครื่อง") and nothing else personal (§4.1).
- **C5 No regression of privacy tests.** `tests/unit/test_handlers.py` (`test_logs_have_no_absolute_paths`, `test_logs_have_no_clip_title`), `tests/unit/test_redact.py`, `tests/api/test_errors.py`, `tests/integration/test_account_privacy.py` keep passing unchanged.
- **C6 LF line endings** in every file except `*.bat` (`.gitattributes`: `* text=auto eol=lf`). The exported JSON is written with `\n`.
- **C7 Thai UI copy:** buttons start with a verb, no "กรุณา", no "!". **Never invent Thai.** Every string comes from the PRD, the BRD, the existing `web/src/i18n/th.ts` or the decisions file (§9). Gaps go to §11 with drafts and are not shipped until Pete answers.
- **C8 Narrow window, not phones.** Target a 640 px-wide desktop window or 200 % zoom. No new phone polish. The app is served on 127.0.0.1 only.
- **C9 New POSTs live under `/api`.** `LocalOnlyMiddleware` (`api/security.py:59-64`) then enforces `X-Toolkit-Token` + Origin. The web calls them through `api()` (`web/src/lib/api.ts:23-45`). The export download uses `downloadFile` (`web/src/lib/download.ts:68-96`, GET + `Content-Disposition`).
- **C10 One naming rule, two languages.** Python `files.plan_names` and TS `planNames` must give the same output for every case in the shared fixture (§2.5). The fixture is generated from Python; the TS test never edits it.
- **C11 No new dependencies**, Python or npm. Vitest stays node-only; component logic goes into `.ts` modules.
- **C12 Future sites (no work now, no new corners).**
  - **Paste:** link detection goes through one predicate, `isSupportedLink(text)` in `web/src/lib/paste.ts`, which today returns `looksLikeYoutube(text)`. The new button and the two existing call sites (`home.tsx:119`, `use-analyze.tsx:152`) call it. A later site only extends that predicate. The UI copy stays as the PRD says.
  - **Naming:** the shared function takes a neutral `uploader` parameter (not `youtubeChannel`) and treats the clip id as an opaque string. No YouTube-id regex inside `plan_names` / `planNames`. The Thai label stays "ช่อง" (BRD FR-OUT-8).
  - **Storage:** the clear walks the cache folders the app actually created and reuses the existing `_remove_cache_folder` id + containment check. It adds **no new place** that hard-codes the 11-character id shape. Known future refactor: replace the `inputs.VIDEO_ID` check in that one helper with a cache-key predicate.
  - **Settings export:** `app` + `schema` are enough; nothing YouTube-specific is added.
  - The YouTube-only assumptions that remain are listed in §10 for awareness only.

## 1. Paste button "วาง" (W1)

### 1.1 Predicate (`web/src/lib/paste.ts`)
- Add `export function isSupportedLink(text: string): boolean { return looksLikeYoutube(text) }` with a comment that later sites extend this one function (C12).
- `home.tsx:119` (in-box paste) and `pages/home/use-analyze.tsx:152` (`useGlobalPaste`) switch from `looksLikeYoutube` to `isSupportedLink`. Behaviour is identical; existing tests keep passing.

### 1.2 Model (`web/src/pages/home/paste-button.ts`, new, node-testable)
```ts
export type PasteOutcome =
  | { kind: "analyze"; text: string }   // supported link → fill + analyze
  | { kind: "fill"; text: string }      // other non-empty text → fill only
  | { kind: "empty" }                   // clipboard empty / whitespace only → nothing changes
  | { kind: "denied" }                  // readText missing, rejected, or threw

export async function readClipboard(deps?: { clipboard?: Pick<Clipboard, "readText"> | undefined }): Promise<PasteOutcome>
```
- `deps.clipboard` defaults to `navigator.clipboard`. If it or `readText` is missing → `denied` (no throw).
- `await readText()`; any rejection (`NotAllowedError`, `NotFoundError`, …) or synchronous throw → `denied`.
- `text.trim() === ""` → `empty`. `isSupportedLink(text)` → `analyze` with the **untrimmed** text (the analyzer already handles surrounding text). Else `fill`.
- It is called only from the click handler (AC-IN-08: no `readText()` before the click). Nothing else in the app calls `readText`.

### 1.3 UI (`web/src/pages/home.tsx:131-141`)
- In the existing `InputGroupAddon align="block-end"`, change `className="justify-end"` to `"justify-end gap-2"` and put a **secondary** button before "วิเคราะห์": `variant="secondary"`, lucide `Clipboard` icon (`data-icon="inline-start"`, `aria-hidden`), label `th.home.paste` ("วาง"), `type="button"`.
- While analyzing (`pending`), it uses `aria-disabled` + the same classes as the analyze button (focus stays; the handler returns early).
- On click: `const outcome = await readClipboard()`, then:
  - `analyze` → `setPasteDenied(false)`, `selectOnFirstFocus.current = false`, `restoredSelected.current = false`, `analyze(outcome.text)`. `analyze()` already writes the text into `homeStore` (`use-analyze.tsx:70-75`, `:113`), so the box content is **replaced** (D1).
  - `fill` → `setPasteDenied(false)`, reset the two refs, `homeStore.set({ text: outcome.text })` (results stay as they are), focus the box.
  - `empty` → focus the box. No hint.
  - `denied` → `setPasteDenied(true)`, `inputRef.current?.focus()`.
- **The hint** (AC-IN-09): rendered directly under `</InputGroup>`, before the error `Alert`, when `pasteDenied` is true: `<p id="paste-hint" role="status" className="text-sm text-muted-foreground">` with `fill(th.home.pasteDenied, { key: pasteShortcut() })`. Muted text, not destructive, no toast. The textarea gets `aria-describedby="paste-hint"` while it shows. The hint hides on the next `onChange` of the box or the next non-denied click.
- **640 px:** the addon row has two buttons; with `gap-2` and the short labels it fits at 640 px and at 200 % zoom (checked in e2e, §7.4).

## 2. Filename style

### 2.1 Where the style applies (D3)
| Kind (`_finish` call site) | `title` | `title-channel` | `title-quality` |
|---|---|---|---|
| video `handlers.py:779` | `<T><sfx>.mp4` | `<T> - <C><sfx>.mp4` | `<T> (<Q>)<sfx>.mp4` |
| audio `handlers.py:848` | `<T><sfx>.<fmt>` | `<T> - <C><sfx>.<fmt>` | `<T> (<Q>)<sfx>.<fmt>` |
| subtitle `handlers.py:875` | `<T>[ (range)].<lang>.<fmt>` | `<T> - <C>[ (range)].<lang>.<fmt>` | as `title` |
| note `handlers.py:957` | `<T>.note.md` | `<T> - <C>.note.md` | as `title` |
| contact sheet `handlers.py:1091` | `<T> - contact sheet.jpg` | `<T> - <C> - contact sheet.jpg` | as `title` |
| frames zip `handlers.py:1105` | `<T> - frames.zip` | `<T> - <C> - frames.zip` | as `title` |
| chapter split `_finish_chapters :429`, sharp dir `_publish_sharp :687`, captures `capture.py:405`, `:480`, clip folder | unchanged | unchanged | unchanged |

`<T>` = the safe, cut title; `<C>` = the safe, cut uploader (channel); `<Q>` = the quality label (§2.3); `<sfx>` = today's suffix (` (ไม่มีเสียง)`, range, ` (ตัดโฆษณา)`), in today's order after the style part. Example: `ชื่อ (1080p) (ไม่มีเสียง) (01.30-05.00).mp4`. An empty channel (unknown uploader) gives the plain `title` form. A missing quality gives the plain `title` form.

`GET /videos/{id}/note` (`api/videos.py`, browser download, no longer called by the web) is not changed.

### 2.2 The shared naming function (`core/files.py`)
```python
FILENAME_STYLES = ("title", "title-channel", "title-quality")  # stays in core/settings.py; files imports nothing from settings
CHANNEL_SEP = " - "
QUALITY_LABEL = re.compile(r"[a-z0-9 ]{1,16}")

def plan_names(
    base_len: int,          # UTF-16 length of str(base): the output root, plus "\<group>" when a group folder is used
    title: str,
    clip_id: str,           # opaque; used only as the fallback name and in " [<id>]"
    *,
    suffix: str,
    ext: str,
    style: str = "title",
    uploader: str = "",
    quality: str | None = None,
) -> tuple[str, str]:       # (clip folder name, file name)
```
TS (`web/src/lib/filename.ts`, new):
```ts
export type FilenameStyle = Settings["filenameStyle"]
export type NameInput = {
  baseLen: number; title: string; clipId: string; suffix: string; ext: string
  style?: FilenameStyle; uploader?: string; quality?: string | null
}
export class PathTooLongError extends Error {}
export function planNames(input: NameInput): { folder: string; file: string }  // throws PathTooLongError
export function safeComponent(text: string, fallback: string): string
export function truncateTitle(text: string, limit: number): string
```
**Algorithm** (both languages, in this order). Constants as today: `PATH_LIMIT 240`, `TITLE_MAX 100`, `TAIL_RESERVE 30`, `TAIL_MAX 60`, `UNIQUE_RESERVE 5`, `_MIN_TITLE 8`. All lengths are UTF-16 code units (`_u16`; JS `string.length`).
1. Unknown `style` → `ValueError` / `Error` (programming error). `quality` must match `QUALITY_LABEL` when given, else `ValueError`.
2. `quality_part = f" ({quality})"` only when `style == "title-quality"` and `quality`; else `""`.
3. `tail = quality_part + suffix + "." + ext`; assert `_u16(tail) <= TAIL_MAX`. The worst case today is 54 (` (1080p)` 8 + ` (ไม่มีเสียง)` 13 + ` (1.02.30-1.05.00)` 18 + ` (ตัดโฆษณา)` 11 + `.mp4` 4), so the existing assert stays.
4. `t = safe_component(title, clip_id)`.
5. `budget = PATH_LIMIT - (base_len + 1) - _u16(f" [{clip_id}]") - 1 - TAIL_RESERVE - UNIQUE_RESERVE`; `cap = budget // 2` — exactly `plan_output :113-114` today.
6. `short = truncate_title(t, min(TITLE_MAX, cap))` when `cap >= _MIN_TITLE`, else `""`.
7. **Fallback** (`short == ""`): folder = `clip_id`, file = `clip_id + tail` (the quality part is kept, the channel dropped). Go to step 10.
8. Folder = `f"{short} [{clip_id}]"` (style never changes it). `avail = budget - _u16(short) + TAIL_RESERVE - _u16(tail)` — the stem room, equal to today's `file_cap`.
9. Stem:
   - `c = safe_component(uploader, "")` when `style == "title-channel"`, else `""`.
   - **No channel** (`c == ""`): `stem = short` if `_u16(short) <= avail` else `truncate_title(short, avail)`; empty → `clip_id`. This is today's rule character for character, so `title` names do not change (regression test §7.1).
   - **With channel:**
     1. `short + CHANNEL_SEP + c` fits `avail` → use it.
     2. Cut the title: `t2 = truncate_title(short, max(avail - 3 - _u16(c), _MIN_TITLE))`; `t2 + " - " + c` fits → use it.
     3. Cut the channel: `room = avail - _u16(t2) - 3`; `c2 = truncate_title(c, room)` when `room >= 1`; `c2` non-empty → `t2 + " - " + c2`.
     4. Drop the channel: `truncate_title(short, avail)`, empty → `clip_id`.
   - File = `stem + tail`.
10. If `base_len + 1 + _u16(folder) + 1 + _u16(file) > PATH_LIMIT - UNIQUE_RESERVE` → `YtError("E_OUTPUT_NOT_WRITABLE", "path too long")` (TS: `PathTooLongError`). Same check as `plan_output :126`.

**`plan_output`** becomes a thin wrapper and keeps its positional signature, adding keywords:
```python
def plan_output(root, title, video_id, suffix, ext, group=None, *, style="title", uploader="", quality=None) -> Path:
    base = root / group_folder_name(group) if group else root
    folder, file = plan_names(_u16(str(base)), title, video_id, suffix=suffix, ext=ext,
                              style=style, uploader=uploader, quality=quality)
    return base / folder / file
```
The callers that only use `.parent` (`plan_chapter_output :154`, `plan_sharp_dir :169`, `_finish_chapters :454`, `capture.py:405`, `:480`, `lifecycle._clip_folders :424`) keep calling it without the new keywords; the folder does not depend on the style by construction (step 8).

**Port details the TS mirror must copy exactly:**
- Python `\s` for `str` is not JS `\s`. `safe_component` collapses with `PY_WS = /[\t\n\v\f\r\x1c-\x20\x85\xa0  -     　]+/gu`. (`\x1c-\x1f` are whitespace in Python; `﻿` is whitespace in JS but `Cf` in Python, so it is dropped.) `.strip()` uses the same class.
- Dropped characters: `\ / : * ? " < > |` and `/[\p{Cc}\p{Cf}\p{Cs}]/u`, tested per **code point** (`for (const ch of text)`).
- `truncate_title` iterates code points, adds `ch.length` (1 or 2) per point, and backs off while the next point matches `/\p{M}/u`, so a surrogate pair or a Thai mark is never split. Trailing `". "` are stripped (`/[. ]+$/`).
- Reserved names: `name.split(".", 1)[0].strip().upper()` in the `_RESERVED` set (copy the set, including `COM¹²³` / `LPT¹²³`) → prefix `_`.

### 2.3 Quality label (derived at finish time)
| Kind | Label | Source |
|---|---|---|
| video | `f"{short_side}p"` (e.g. `1080p`, `2160p`; a vertical 1080×1920 clip gives `1080p`, the app's short-side rule) | `result.media.short_side` (`download.MediaFacts`, the file that was really downloaded) |
| video, facts unknown (`media is None` or no height) | no quality part | — |
| audio mp3 | `f"mp3 {kbps}k"` | `int(params.get("mp3Kbps") or DEFAULT_MP3_KBPS)` (`handlers.py:79`, `:836`) |
| audio m4a | `f"m4a {round(abr)}k"`; unknown bitrate → `m4a` | new `MediaFacts.abr_kbps` |
| audio wav | `wav` | — |

**Audio bitrate fact:** add `abr_kbps: int | None = None` to `MediaFacts` (`core/download.py:47`); `media_facts(fmt)` fills it from `_number(fmt.get("abr"))`, rounded. `extractor._downloaded_facts` (`extractor.py:542-551`) returns the facts when **height or abr** is known (today: height only). The video path and `_auto_sharp_skip` keep reading `height` / `short_side`, so nothing else changes. The fake extractor's `_media_of` (`:1036`) reads the same keys from `behaviors.json`.

`_video` passes `quality=_video_quality(result.media)` and `_audio` passes `quality=_audio_quality(fmt, params, result.media)` to `_finish`. These two helpers live in `handlers.py`. The other kinds pass `quality=None`.

### 2.4 Style snapshot on the job (D4)
- **DB schema v3** (`core/db.py`): `SCHEMA_VERSION = 3`. Add `filename_style TEXT` (NULL = not started yet, or a job from before M6; read as `"title"`) to `_JOBS`. **Freeze** today's `_JOBS` text as `_JOBS_V2` and use it in `_MIGRATIONS[2]`, otherwise a v1 → v2 → v3 upgrade would create the column in step 2 and fail on step 3's `ALTER`. `_MIGRATIONS[3] = "ALTER TABLE jobs ADD COLUMN filename_style TEXT; UPDATE schema_version SET version = 3;"`.
- **`core/jobs.py`:** `Job.filename_style: str | None`; the row mapping reads it; `transition(..., filename_style=...)` writes it through the existing field list. It is **not** added to the API job shape (internal).
- **`SettingsView`** (`queue.py:117`) gains `def filename_style(self) -> str: ...`; `SettingsStore.filename_style()` returns `get()["filenameStyle"]`. The fake in `tests/unit/test_queue.py` gets the method.
- **`QueueRunner._start`** (`queue.py:359-366`): after `output_root = self._settings.output_dir()`, `style = job.filename_style or self._settings.filename_style()`, then `self.store.transition(job.id, "running", filename_style=style)`. The first start fixes it; every retry (`failed`/`interrupted` → `queued` → `running`, the bot-check requeue, the in-run `E_NETWORK` retries) keeps it.
- **`JobContext`** (`jobs.py:195`) gains `filename_style: str`; `_JobContext.__init__` takes it from the started job. Handlers read `ctx.filename_style`.
- **`_Clip`** (`handlers.py:152`) gains `style: str` and `uploader: str`; `_start` (`:180`) sets `style=ctx.filename_style` and `uploader=str(info.get("channel") or "")`. `_finish` (`:552`) passes `style=clip.style, uploader=clip.uploader, quality=quality`.
- The uploader is **not** snapshotted: it is read from the clip info each run, and the sweep reads `videos.channel` (§2.7). A channel rename between two runs only changes the name, which is harmless.

### 2.5 Parity fixtures (C10)
- `tests/fixtures/names/cases.json`: a list of `NameInput` objects in camelCase (`baseLen`, `title`, `clipId`, `suffix`, `ext`, `style`, `uploader`, `quality`), each with a short `name`.
- `tests/fixtures/names/golden.json`: `{ "<name>": {"folder": "...", "file": "..."} | {"error": "path too long"} }`, written only by `YT_UPDATE_GOLDEN=1 uv run pytest tests/unit/test_names_golden.py` (the same pattern as `test_srt_golden.py`; the test fails on purpose after regenerating).
- `web/src/lib/filename-parity.test.ts` reads both with `import.meta.glob("../../../tests/fixtures/names/*.json", { query: "?raw", import: "default", eager: true })` (as `srt-parity.test.ts:14-23`) and compares `planNames` for every case.
- Minimum cases: the AC-OUT-01 title `ทดสอบ: "A/B" <ภาค 1>?` and a 300-character title (AC-OUT-02) in all three styles with `quality` `1080p` and `mp3 192k`; Thai marks and an emoji at the cut point; `\x1c`, `﻿`, `​` and a tab inside the title; reserved names `CON`, `com1.txt`, `LPT¹`; trailing dots and spaces; an empty title (→ id); an empty or forbidden-only uploader (→ plain); a 120-character uploader; the longest suffix (no-audio + range + ads); a subtitle `.th` suffix; `.note`; contact sheet; `baseLen` 3, 60, 150, 200 (fallback branch) and 230 (path too long); a non-ASCII clip id (proves it is opaque).

### 2.6 Settings field and live example (W6, AC-OUT-10)
- **History gives the channel.** `VideoService.recent` (`core/videos.py:772-826`) selects `v.channel` and returns `"channel": row["channel"] or ""` in each item. `HistoryItem` (`web/src/lib/types.ts:146`) gains `channel: string`. PRD §6.2 `/history` row updated (§8).
- **Shared query.** Move the W1 "ล่าสุด" query into `pages/history/queries.ts` as `recentQuery(limit = 5)` (key `["history", { limit, scope: "opened" }]`, unchanged); `recent.tsx:21-25` uses it. The style field calls the same `useQuery(recentQuery())`, so it shares the cache and makes no request when the style changes.
- **Model** (`pages/settings/filename-example.ts`, new, pure):
  ```ts
  export function exampleFileName(style: FilenameStyle, clip: { title: string; channel: string; videoId: string } | undefined, outputDir: string): string
  ```
  - clip = `history.data?.items[0]` when present, else the sample (`th.general.filenameSample`, `th.general.filenameSampleChannel`, `SAMPLE_CLIP_ID = "abcdefghijk"`), see §11 Q1.
  - `planNames({ baseLen: outputDir.length, title, clipId, uploader: channel, style, quality: "1080p", suffix: "", ext: "mp4" }).file`. `PathTooLongError` → retry with `baseLen: 0`. The example is always the video form, as the PRD line says ("ตัวอย่าง: <ชื่อไฟล์>.mp4").
- **Field** (`pages/settings/filename-style-field.tsx`, new), placed right after `OutputDirField` in `GeneralPanel` (`general-panel.tsx:114-121`):
  - `FieldTitle id="general-filename"` `th.general.filenameStyle`;
  - the existing `ChoiceSelect` with options from `FILENAME_STYLES` (`general-form.ts`, new constant `["title", "title-channel", "title-quality"]`) labelled `th.general.filenameStyles[value]`;
  - `<FieldDescription id="general-filename-example" className="font-mono break-all">` = `fill(th.general.filenameExample, { name })`, recomputed from `shown.filenameStyle` (so it changes on select, before the PATCH returns);
  - saving uses `choose(choicePatch("filenameStyle", value, shown))`; add `"filenameStyle"` to `GeneralKey` (`general-form.ts:7-14`). The usual "บันทึกแล้ว" toast follows.
- AC-OUT-10's "jobs started after the change use the new style" holds through D4: the queue reads the setting at each first start.

### 2.7 Leftover sweep and interrupted outputs (`lifecycle.py`)
- `JobStore.channel_of(video_id) -> str` (next to `chapters_json`, `jobs.py:552`): `SELECT channel FROM videos`; missing or error → `""`.
- `sweep_interrupted_outputs` (`:434-470`) passes `style=job.filename_style or "title"` and `uploader=store.channel_of(job.video_id)` into a new `toolkit_name_pattern(prefix, *, style="title", uploader="")`:
  - `title`: **today's pattern, unchanged** (existing tests at `test_lifecycle.py:1531`, `:1602`, `:2016` keep passing).
  - `title-channel`: the name part becomes `{_prefixes(prefix)}(?: - {_prefixes(c)})?` where `c = files.safe_component(uploader, "")` (omitted when empty), used in all four alternatives (media, cut, subtitle, subtitle range), because any part can be cut.
  - `title-quality`: the media and cut alternatives get `(?: \((?:\d{3,4}p|(?:mp3|m4a) \d{2,3}k|m4a|wav)\))?` right after the name part, and the name part is `_prefixes(prefix)` (a long tail may cut the title). Subtitle alternatives as `title`.
  - The safety rules are unchanged: only 0-byte reservations and `.part` files, never a `done` output (`keep`), only inside the clip folder.
- `_clip_folders` (`:417-431`) is unchanged (folders do not depend on the style).
- **Privacy:** `queue.job_titles(job, chapters_json, channel="")` gains the channel, so `job_failed` lines and reports also scrub it (file names now contain it). Callers: `queue.py:378` (`log_job_failed`), `:418` (`_log_crash`), `api/diagnostics.py` — each passes `store.channel_of(job.video_id)`. `scrub_titles` already skips names under 4 characters.

## 3. Clear temporary data

### 3.1 What is counted and what is cleared
| Location | `cacheBytes` / `workBytes` | Clearable (`reclaimableBytes`) |
|---|---|---|
| `data/cache/<name>/` where `db.cache_folder(root, name)` passes (the existing id + containment check, §3.4) | cache | yes, unless `name` is the video id of an active job or of the running capture, or the folder holds **in-progress staging**: a direct child whose name contains `.tmp-` (`storyboard.tmp-*`, `sharp.tmp-*`) modified less than `STAGING_GRACE_S = 600` s ago |
| `data/cache/.clear-<32 hex>/` (left by an interrupted clear) | cache | yes |
| any other entry in `data/cache/` | cache | no |
| `work/<36 chars [0-9a-f-]>/` (job dirs, uuid7) | work | yes, unless an active job id |
| `work/capture-<32 hex>/` | work | yes, unless the running capture's dir |
| `work/.clear-<32 hex>/` | work | yes |
| any other entry in `work/` (e.g. the ffmpeg zip during an install, `tools.py:333`) | work | no |

- Sizes are the sum of `st_size` of regular files, found with an `os.scandir` walk that never follows symlinks or junctions (`entry.is_symlink()`, `entry.is_junction()`). Unreadable entries count as 0 and are skipped (`OSError`). A missing root counts as 0.
- `videos` rows, `jobs`, `settings`, `data/visitor-session.*`, `data/app.db*`, `run/` and every output folder are outside both roots and never touched (D2).

### 3.2 Concurrency
- **Active set.** `QueueRunner.hold_active()` is a context manager: it takes `self._lock` (the existing `RLock`, `queue.py:295`, the same lock `tick` holds while starting jobs, `:334`) and yields `ActiveJobs(job_ids, video_ids)` from `self._active`. `_JobContext` gains `video_id`. A job started before the hold is in the set; a job cannot start during it. Auto sharp frames run inside the video job (`handlers.py:780`), so its `sharp.tmp-<jobId>` folder is covered by the video id.
- **Captures.** `CaptureService` gains `_current: tuple[str, str] | None` (video id, tmp dir name), set under `_guard` right after `_busy.acquire` succeeds (`capture.py:279`) and before `_capture_locked` creates `work/capture-<uuid>` (`:294`), cleared in the `finally` that releases `_busy`. `CaptureService.hold_active()` takes `_guard` and yields `_current`. `_guard` must never be held while calling out of the service (today it only guards `_clip_locks`, `:205-207`), so the lock order **queue `_lock` → captures `_guard`** cannot deadlock.
- **Two phases.** `StorageService.clear()`:
  1. **Under both holds** (milliseconds): list the two roots, decide the clearable entries (§3.1) and `os.rename` each into a fresh trash dir in the **same root**: `data/cache/.clear-<hex>/` and `work/.clear-<hex>/` (same parent, so the rename never crosses a volume). A rename that fails (a file open on Windows, `PermissionError`) leaves that entry in place and it is not counted.
  2. **Outside the holds:** `trash_bytes = size(trash)`; `shutil.rmtree(trash, ignore_errors=True)`; `left = size(trash)`; remove the empty trash dir; `freed = trash_bytes - left`. A locked leftover stays in `.clear-*` and is cleared next time or at startup.
- A second `clear()` while one runs waits on a `threading.Lock` in the service and then frees what is left (usually 0).
- `usage()` takes both holds only to snapshot the active set and the listing, then measures outside the holds.
- **Startup:** `lifecycle` calls `storage.sweep_clear_leftovers(cache_root)` next to `sweep_sharp_cache_once` (`lifecycle.py:671-679`): removes `data/cache/.clear-*`. `work/.clear-*` is already removed by `QueueRunner.recover` → `_empty_work_root` (`queue.py:680-683`).
- **Requests that write the cache during a clear** (another tab opening W2: storyboard build, subtitle tokens, pinned comment) are not blocked. The staging rule protects a storyboard build in progress. The atomic writers recreate their folder (`mkdir(parents=True)`) or log a warning and retry next time (`subtitles.py:357`, `comments.py:160`). See Review Focus 2.

### 3.3 Readers that must tolerate a missing cache (checked, no change needed)
| Reader | Behaviour when `data/cache/<id>/` is gone |
|---|---|
| `storyboard.build` / `get_storyboard` (`storyboard.py:298-376`) | `_read_index` → None → rebuilds from `videos.raw`; signed links expired → `E_NETWORK` → re-probe once (`:372-376`). Offline → the W2 frames error box (expected: "เปิดคลิปเก่าต้องดึงภาพใหม่"). |
| `sharp_store.read_sharp` (`sharp_store.py:87-91`) | None → no sharp set; `frames_sharp`/contact sheet `source: "sharp"` → `E_NO_SHARP_FRAMES` (existing). |
| `CaptureService._read_entries` / `list` (`capture.py:215-221`, `:430-442`) | `[]` → the capture strip is empty. Output copies under `ภาพที่ถ่าย/` stay. |
| `subtitles._read_cache` (`subtitles.py:302-310`) | None → re-download. |
| `PinnedCommentService._read` (`comments.py:122-126`) | `_MISS` → re-fetch. |
| `api/videos._cache_target` (`api/videos.py:343-375`) | 404 for a stale image URL. |
| `sweep_sharp_leftovers`, `purge_stale_cache` | iterate what exists; a `.clear-*` dir has no `sharp.tmp-*` children and is not an id. |

The plan adds one test per row (§7.1).

**Web after a clear:** `queryClient.removeQueries` for the keys `["storyboard"]`, `["sharp"]`, `["captures"]`, `["subtokens"]`, `["pinned-comment"]`, then `invalidateQueries({ queryKey: STORAGE_KEY })`. `["video"]`, `["history"]`, `["subtitles"]` (track lists from the probe) and `["settings"]` stay.

### 3.4 Module and API
- **`core/db.py`:** split `_remove_cache_folder` (`:206-222`) into `cache_folder(root, name) -> Path | None` (the existing `VIDEO_ID` fullmatch + `resolve()` + containment check, returning the folder or None) and the existing remover that calls it. `purge_stale_cache` behaves as today. `core/storage.py` uses `cache_folder` to decide clearable folders. No new id regex (C12).
- **`core/storage.py`** (new; imports no `api`, `platform` or `yt_dlp`):
  ```python
  @dataclass(frozen=True)
  class StorageUsage:
      cache_bytes: int
      work_bytes: int
      reclaimable_bytes: int

  class ActiveSource(Protocol):
      def hold_active(self) -> AbstractContextManager[...]: ...

  class StorageService:
      def __init__(self, cache_root: Path, work_root: Path, *, queue: QueueRunner | None, captures: CaptureService | None, now: Callable[[], float] = time.time) -> None: ...
      def usage(self) -> StorageUsage: ...
      def clear(self) -> int: ...   # freed bytes

  def sweep_clear_leftovers(cache_root: Path) -> int: ...
  ```
  Logging: one `INFO storage_clear freed=<bytes> entries=<n> skipped=<n>` line per clear; a failed rename logs `DEBUG storage_skip reason=<ErrorClassName>`. No paths, ids only where unavoidable (none needed).
- **`api/storage.py`** (new), `build_storage_router(ctx)`, included in `create_app` when `ctx.cache_root is not None` (`app.py:85-102`). It builds one `StorageService(ctx.cache_root, ctx.paths.work, queue=ctx.queue, captures=ctx.captures)` per app. Both routes are sync `def` (threadpool).

| Method | Path | Body | Answer |
|---|---|---|---|
| GET | `/api/storage` | — | `200 {"cacheBytes": int, "workBytes": int, "reclaimableBytes": int}`, `Cache-Control: no-store` |
| POST | `/api/storage/clear` | none (ignored) | `200 {"freedBytes": int}`, `Cache-Control: no-store`; token + Origin by middleware (403 `E_FORBIDDEN`) |

An unexpected `OSError` on a root (not `FileNotFoundError`) reaches the M6-B handler: 500 `E_UNKNOWN`, logged by `ErrorLogMiddleware` with its code only.

## 4. Settings backup and import

### 4.1 Export (`GET /api/settings/export`, `api/settings.py`)
- Body: `{"app": "yt-toolkit", "schema": 1, "exportedAt": "<UTC ISO 8601, seconds, +00:00>", "settings": {...}}`. `settings` = `store.get()` minus every `READ_ONLY` key (`statsResetAt`). `cookies` is already not a key (`RETIRED_KEYS`). Nothing else is added (C12).
- Serialised with `json.dumps(doc, ensure_ascii=False, indent=2, allow_nan=False) + "\n"`, UTF-8, no BOM.
- Headers: `Content-Type: application/json`, `Content-Disposition: attachment_header(name, name)` (`api/videos.py:120-122`, imported from there), `Cache-Control: no-store`. `name = f"yt-toolkit-settings-{datetime.now().astimezone():%Y-%m-%d}.json"` (local date).
- A GET, so no token, like `GET /settings` which already returns the same values.

### 4.2 Import (`POST /api/settings/import`)
**API layer** (`async def`, reads the raw body):
1. `Content-Length` > `MAX_SETTINGS_IMPORT_BYTES = 1_048_576` → **413** `E_SETTINGS_INVALID`, detail `"file larger than 1048576 bytes"`, before reading. Read with `request.stream()` and stop at cap + 1 → 413 likewise (no or wrong `Content-Length`).
2. Decode `utf-8-sig` (Notepad may add a BOM); `UnicodeDecodeError` → 422.
3. `json.loads(text, parse_constant=_reject)` (NaN / Infinity rejected); error → 422 `detail "not JSON"`.
4. `await run_in_threadpool(store.import_settings, doc)` → `200 {"settings": ..., "warnings": [...]}`.
5. `SettingsError` with code `E_SETTINGS_INVALID` → 422 with `MESSAGES["E_SETTINGS_INVALID"]` and the error's fixed detail.

The body is never logged (`ErrorLogMiddleware` logs method, path, status, code). Detail strings are fixed English and name a key at most, never a value (C4).

**Store layer** — `SettingsStore.import_settings(doc: object) -> tuple[dict, list[str]]` (`core/settings.py`, new):
1. **Shape:** `doc` is a dict; `doc.get("app") == "yt-toolkit"`; `type(doc.get("schema")) is int and doc["schema"] == 1`; `doc.get("settings")` is a dict. Else `SettingsError("E_SETTINGS_INVALID", "<which field> invalid")`.
2. **Keys:** for each `(key, value)` in `settings`:
   - `key in READ_ONLY or key in RETIRED_KEYS or key not in _VALIDATORS` → skipped silently (unknown keys skipped, `statsResetAt` / `cookies` never imported);
   - `outputDir`: not a `str` → `E_SETTINGS_INVALID` ("bad type"). A string is checked later (step 3);
   - any other key: `validator(value)`; a `SettingsError` → `SettingsError("E_SETTINGS_INVALID", f"{key}: invalid value", key=key)`.
   All keys are validated before anything is written: one bad key → 422, nothing changes (AC-SET-10).
3. **`outputDir`** (only after step 2 passed, outside the lock, as `patch :225-228` does): `_validate_output_dir(value)` then `ensure_writable(Path(clean))`. **Any** failure — wrong format on this machine (a macOS path on Windows, a missing drive) or not writable — drops the key and appends `"outputDir"` to `warnings` (FR-SET-7 "คงโฟลเดอร์เดิมและบอกผู้ใช้"). This is a deliberate reading of AC-SET-09: a string path that does not work here is a machine difference, not a damaged file.
4. **Write:** if `clean` is non-empty, one `with self._lock, self._db.transaction() as tx:` block deletes `RETIRED_KEYS` rows and upserts every clean key (the same SQL as `patch :229-238`). Keys absent from the file keep their current value.
5. `saved = self.get()`; if `"outputDir" in clean` and `self.on_output_dir` → call it with `Path(saved["outputDir"])` outside the lock (`redact.set_output_roots` through `lifecycle.wire_output_roots`).
6. Return `(saved, warnings)`. `settings: {}` is valid and changes nothing.

`patch()` is unchanged (strict: unknown keys and `statsResetAt` → 422 `E_BAD_REQUEST`).

**`core/yterrors.py`:** add `"E_SETTINGS_INVALID": 'ไฟล์นี้ไม่ใช่ไฟล์ค่าตั้งของ YT Toolkit หรือไฟล์เสียหาย ลองเลือกไฟล์ที่ได้จากปุ่ม "สำรองค่าตั้ง"'` (PRD §7, `PRD.md:814`). `SettingsError`'s docstring lists the new code. `test_yterrors.py` already checks every `MESSAGES` code against PRD §7.

### 4.3 Web
- `lib/settings-api.ts`:
  - `exportSettings(deps?)` → `downloadFile("/api/settings/export", "yt-toolkit-settings.json", deps)`;
  - `importSettings(text: string, deps?)` → `api<{ settings: Settings; warnings: string[] }>("/settings/import", { method: "POST", body: text })`. `api()` adds the token and `Content-Type: application/json` (`api.ts:29-33`);
  - `STORAGE_KEY = ["storage"]`, `storageQuery()`, `clearStorage()` (`POST /storage/clear`);
  - `MAX_SETTINGS_FILE_BYTES = 1_048_576`.
- Import flow: a hidden `<input type="file" accept=".json,application/json">` opened by the "นำเข้าค่าตั้ง" button. On pick: `file.size > MAX` → `showErrorToast(th.general.settingsInvalid, { id: "settings-import", request: { code: "E_SETTINGS_INVALID", detail: "file larger than 1048576 bytes", context: "settings-import" } })` without sending; else `await file.text()` → `importSettings`. The input value is reset so the same file can be picked again.
- Success: `queryClient.setQueryData(SETTINGS_KEY, result.settings)` (theme and download defaults follow at once). No warnings → `toast.success(th.general.saved, { ...PLAIN_TOAST, id: "settings-import" })`. `warnings` includes `"outputDir"` → a warning toast with the copy of §11 Q3 (pending).
- Failure: `showErrorToast(serverMessage(error), { id: "settings-import", request: reportRequest(error, { context: "settings-import" }) })`.
- Export failure: `showErrorToast(error.message, { id: "settings-export", request: reportRequest(error, { context: "settings-export" }) })`; success shows no toast (the browser shows the download).

## 5. "ข้อมูลในเครื่อง" section (W6 General)

`pages/settings/local-data-section.tsx` (new) renders after the last field of `GeneralPanel` (`general-panel.tsx:208-213`), inside the same `FieldGroup`:
- `FieldSet` + `FieldLegend` `th.general.localData`.
- A `flex flex-wrap gap-2` row of three `variant="secondary"` buttons:
  1. **"ล้างข้อมูลชั่วคราว (<ขนาด>)"** — `fill(th.general.clearTemp, { size: formatBytes(reclaimableBytes) })` (`lib/format.ts:92`, gives `1.2 GB` as in BRD FR-SET-6). While `storageQuery` loads or failed: `th.general.clearTempPlain` ("ล้างข้อมูลชั่วคราว") and disabled; the failure is silent (secondary data, as `recent.tsx`). `reclaimableBytes === 0` → disabled.
  2. **"สำรองค่าตั้ง"** — `exportSettings()`.
  3. **"นำเข้าค่าตั้ง"** — opens the file picker (§4.3). Pending → `Spinner` + disabled.
- **Confirm** (`AlertDialog`, as `components/queue/shutdown-dialog.tsx`): title `fill(th.general.clearConfirmTitle, { size })`, description `th.general.clearConfirmBody`, `AlertDialogCancel` `th.general.clearCancel` ("ยกเลิก"), action `th.general.clearConfirm` ("ล้างเลย") with a spinner while pending. The size in the title is the same `reclaimableBytes` as on the button.
- **After the clear:** the dialog closes; `toast.success(fill(th.general.cleared, { size: formatBytes(freedBytes) }), { ...PLAIN_TOAST, id: "storage-clear" })`; the query cleanup of §3.3. Failure: `showErrorToast(serverMessage(error), { id: "storage-clear", request: reportRequest(error, { context: "storage-clear" }) })`.
- `storageQuery` refetches on window focus (React Query default) and after a clear. It is not polled.
- `context` tags for reports: `settings-import`, `settings-export`, `storage-clear` (all match `^[a-z][a-z0-9-]{0,31}$`, M6-B §2.1).
- **640 px:** the button row wraps; the dialog uses the existing responsive `AlertDialogContent`. No horizontal scroll (e2e, §7.4).

## 6. Errors and edge cases

- **Paste while analyzing:** the button is `aria-disabled`; the click returns early.
- **Paste with the result list open:** link → new analysis replaces the list (as a pasted link today); text → only the box changes.
- **Clipboard holds an image only:** `readText()` resolves `""` in Chromium → `empty` → focus only.
- **Style change during a run:** the running job keeps its snapshot; queued jobs take the new style when they start (AC-OUT-10).
- **Two jobs of one clip, different styles:** both land in the same clip folder (folder independent of style), with different file names.
- **Long channel:** the title is cut to at least 8 characters before the channel is cut (§2.2 step 9).
- **Clear while a job runs** (AC-SET-08): its `work/<jobId>` and its `data/cache/<videoId>` are skipped; the job finishes normally.
- **Clear while a capture runs:** its clip's cache and its `work/capture-*` are skipped. A capture that starts during phase 1 waits a few milliseconds on `_guard`.
- **Clear with a file open in another program** (Windows): that folder is skipped, counted as not freed; `freedBytes` reports only what was removed.
- **App closed mid-clear:** the `.clear-*` dirs are removed at the next start (§3.2).
- **Import on a machine without the exported folder:** the old folder stays, the toast says so (§11 Q3), other keys are imported.
- **Import of a newer `schema`:** 422 `E_SETTINGS_INVALID` (the app cannot know the newer shape).
- **Import while a job runs:** a new `outputDir` applies to jobs that start later (the queue reads it at each start, `queue.py:361`); the hook updates log masking at once.

## 7. Testing

### 7.1 Python unit
- **`tests/unit/test_names_golden.py`** (new): the golden check of §2.5, plus Python-only asserts:
  - `style="title"` gives exactly today's `plan_output` result for a table of existing inputs (copy the cases from `tests/unit/test_files.py`): no name changes for current users;
  - AC-OUT-09: all three styles with the AC-OUT-01 and AC-OUT-02 titles → no forbidden characters, path ≤ 240, the `(1080p)` / `(mp3 192k)` part and the extension intact, and the folder name identical across styles.
- **`tests/unit/test_handlers.py`:** one finish per kind × style (§2.1 table), using the fake downloader's `media` facts (height 1080 → `(1080p)`, `abr` 129.5 → `(m4a 130k)`, mp3 192 → `(mp3 192k)`, wav → `(wav)`, no facts → no part); chapter-split, sharp and capture names unchanged under every style; the job's `filename_style` drives the name, not the current setting.
- **`tests/unit/test_queue.py`:** first start stores the setting; a retry after a style change keeps the old snapshot; a job queued before a change and started after it uses the new one; `hold_active()` blocks `tick` from starting a job while held.
- **`tests/unit/test_db.py`:** v1 → v3 and v2 → v3 migrations keep every row and add `filename_style` NULL; a fresh DB has the column; `_MIGRATIONS[2]` still uses the frozen `_JOBS_V2`.
- **`tests/unit/test_lifecycle.py`:** the sweep removes a 0-byte `<T> - <C>.mp4`, `<T> (1080p).mp4`, a cut `<T…> - <C…> (01.30-05.00).mp4.part` and `<T> (mp3 192k).mp3`; it keeps a done output and a user file `<T> - notes.mp4` with content; `title` patterns unchanged (existing parametrised tests).
- **`tests/unit/test_storage.py`** (new):
  - three cache folders totalling 50 MB → `usage()` within ±1 % of the bytes written (AC-SET-07); `clear()` → `data/cache/` empty, `freedBytes` equal to the previous `reclaimable_bytes`, outputs, `app.db`, `visitor-session.*` and `run/logs` untouched;
  - an active job (`hold_active` fake) keeps its `work/<jobId>` and its clip cache (AC-SET-08); the running capture keeps its clip cache and tmp dir;
  - a young `storyboard.tmp-*` keeps the folder; an old one does not;
  - unknown entries in both roots are neither counted as reclaimable nor removed; a symlink / junction is not followed;
  - a failed rename (monkeypatched `os.rename` raising `PermissionError`) → that entry stays and is not counted;
  - `sweep_clear_leftovers` removes `.clear-*`;
  - a log check: no absolute path, no title in `caplog.text`.
- **Missing-cache readers** (one test each, §3.3 table): delete `data/cache/<id>/` and call the reader.
- **`tests/unit/test_settings.py`:** `import_settings` — round trip with `get()` (AC-SET-09); unknown keys, `statsResetAt` and `cookies` skipped; `concurrency: 5`, `theme: 1`, `outputDir: 3` → `E_SETTINGS_INVALID` and **no** row changed (compare the whole table); `app` / `schema` / `settings` wrong → invalid; unwritable `outputDir` and a relative `outputDir` → old value kept + `["outputDir"]`; the hook fires once with the new folder and not on a warning; all writes in one transaction (a failing upsert leaves nothing).
- **`tests/unit/test_yterrors.py`:** the new message equals PRD §7.
- **`tests/unit/test_extractor*.py`:** `_downloaded_facts` returns `abr_kbps` for an audio-only download and still returns None when neither height nor abr is known.

### 7.2 Python API
- **`tests/api/test_storage_api.py`** (new): shapes and `no-store`; POST without token / wrong Origin → 403; GET needs no token; a running fake job survives a clear and completes (AC-SET-08, with the queue fixture).
- **`tests/api/test_settings_api.py`:** export headers (`attachment`, the dated name, UTF-8 `filename*`), body shape, no `statsResetAt`; import on a fresh `data/` → `GET /settings` equal for every exported key (AC-SET-09); 413 above 1 MB (with and without `Content-Length`); 422 `E_SETTINGS_INVALID` for non-JSON, invalid UTF-8, `app` wrong, `NaN`, a bad type, and the settings table unchanged (AC-SET-10); a BOM file imports; the 422 body never contains the bad value; token / Origin → 403.
- **`tests/api/test_history_api.py`:** items have `channel`.

### 7.3 Privacy canary (`tests/integration/test_account_privacy.py`)
While the canary account is held: call `GET /settings/export` and assert that the body contains none of the canary cookie values, the canary cookie name, `SAPISID`, `__Secure-3PSID`, `LOGIN_INFO`, nor the app token; also call `GET /storage` and `POST /storage/clear` and run the existing file-walk afterwards (the clear must not have written cookie data anywhere).

### 7.4 Web
- **Vitest (node):**
  - `lib/filename-parity.test.ts` (§2.5) and `lib/filename.test.ts` (whitespace class, surrogate pairs, `\p{M}` back-off);
  - `pages/home/paste-button.test.ts`: the four outcomes, missing `navigator.clipboard`, missing `readText`, a rejection, a synchronous throw;
  - `lib/paste.test.ts`: `isSupportedLink` equals `looksLikeYoutube` on the existing table;
  - `pages/settings/filename-example.test.ts`: latest clip vs sample, all three styles, the `PathTooLongError` fallback;
  - `lib/settings-api.test.ts`: request shapes for import / export / storage;
  - `general-form.test.ts`: `filenameStyle` in `choicePatch`.
- **Chromium e2e** (project `chromium`, API mocked with `page.route`, **no real jobs**):
  - `web/e2e/home-paste.spec.ts`: grant `clipboard-read` → write a link → "วาง" → the box holds the link and `/api/resolve` is called (AC-IN-08); plain text → filled, no resolve; spy on `navigator.clipboard.readText` via `addInitScript` and assert 0 calls before the click; deny (`addInitScript` making `readText` reject with `NotAllowedError`) and remove `readText` → the hint text, the box focused, no `role="alert"`, no toast (AC-IN-09); at 640 px the addon row does not overflow.
  - `web/e2e/settings-local-data.spec.ts`: change the style → the example changes with **no** request to `/api/*` after the change apart from the `PATCH /api/settings` save (AC-OUT-10: count requests); mock `/api/history?…scope=opened` with and without an item; clear: button shows the mocked size, dialog title, "ล้างเลย" → `POST /api/storage/clear` → toast "ล้างแล้ว ได้พื้นที่คืน …"; cancel sends nothing; export → a download event with the dated name; import a valid file → toast "บันทึกแล้ว" and the new values on screen; import → mocked 422 → error toast with the copy-report button; a 2 MB file → no request, `E_SETTINGS_INVALID` toast.
  - **Axe** (`analyzeSettled`): light and dark on the General tab with the new section and on the open dialog; the W1 page with the paste hint shown.
  - **640 px:** `document.documentElement.scrollWidth <= 640` on the General tab with a 300-character example and on W1 with the hint.

## 8. Docs (done in this commit)

- **PRD.md:**
  - §6.1 `jobs`: column `filename_style` and `schema_version` comment (v3, M6);
  - §6.2 `/history` row: `channel`; `/settings/import` row: 413, `utf-8` + BOM, `schema` = 1, `statsResetAt` / `cookies` skipped, any `outputDir` that cannot be used → warning; `/storage` rows: what counts as reclaimable;
  - §6.2 HTTP status line: `E_SETTINGS_INVALID` 422 (413 above 1 MB);
  - §6.3 output-name line: which kinds get each style and the snapshot;
  - §6.4 `filenameStyle` row: the D3 rules;
  - §7 `E_SETTINGS_INVALID` row: 413 above 1 MB.
- **docs/acceptance.md:** a new "M6 รอบ A" section of manual Windows checks, written from the PRD AC text only (§9).
- **Not changed:** BRD (the decisions refine, they do not contradict it).

## 9. Thai copy (all sourced)

| Key (`th.ts`) | Copy | Source |
|---|---|---|
| `home.paste` | วาง | PRD W1 `:101`, BRD FR-IN-7 |
| `home.pasteDenied` | เบราว์เซอร์ไม่อนุญาตให้อ่านคลิปบอร์ด คลิกในช่องแล้วกด {key} แทน | PRD W1 `:101` (Ctrl+V / ⌘V through `pasteShortcut()`) |
| `general.filenameStyle` | รูปแบบชื่อไฟล์ | PRD `:306`, BRD FR-OUT-8 |
| `general.filenameStyles.title` | ชื่อคลิป | BRD FR-OUT-8 |
| `general.filenameStyles["title-channel"]` | ชื่อคลิป - ช่อง | BRD FR-OUT-8 |
| `general.filenameStyles["title-quality"]` | ชื่อคลิป (คุณภาพ) | BRD FR-OUT-8 |
| `general.filenameExample` | ตัวอย่าง: {name} | PRD `:306` |
| `general.filenameSample`, `general.filenameSampleChannel` | **pending, §11 Q1** | — |
| `general.localData` | ข้อมูลในเครื่อง | PRD `:307` |
| `general.clearTemp` | ล้างข้อมูลชั่วคราว ({size}) | PRD `:307`, BRD FR-SET-6 |
| `general.clearTempPlain` | ล้างข้อมูลชั่วคราว | BRD FR-SET-6 |
| `general.clearConfirmTitle` | ล้างข้อมูลชั่วคราว {size}? | PRD W7 `:325` |
| `general.clearConfirmBody` | ไฟล์ที่โหลดไว้ ประวัติ และค่าตั้งยังอยู่ครบ แต่เปิดคลิปเก่าต้องดึงภาพใหม่ | PRD W7 `:325` |
| `general.clearCancel` | ยกเลิก | PRD W7 `:325` |
| `general.clearConfirm` | ล้างเลย | PRD W7 `:325` |
| `general.cleared` | ล้างแล้ว ได้พื้นที่คืน {size} | PRD `:307` |
| `general.backup` | สำรองค่าตั้ง | PRD `:307`, BRD FR-SET-7 |
| `general.import` | นำเข้าค่าตั้ง | PRD `:307`, BRD FR-SET-7 |
| `general.settingsInvalid` | ไฟล์นี้ไม่ใช่ไฟล์ค่าตั้งของ YT Toolkit หรือไฟล์เสียหาย ลองเลือกไฟล์ที่ได้จากปุ่ม "สำรองค่าตั้ง" | PRD §7 `:814` |
| import success | บันทึกแล้ว (`general.saved`, reused) | PRD W6 `:303`; see §11 Q2 |
| import warning `outputDir` | **pending, §11 Q3** | — |

Sizes use the existing `formatBytes` (`GB` with one decimal, `MB`), matching the BRD example "1.2 GB". Copy rules: buttons start with a verb ("วาง", "ล้าง…", "สำรอง…", "นำเข้า…"); no "กรุณา"; no "!".

## 10. Known YouTube-only assumptions (future milestone, awareness only, no work)

- The video id regex (`core/inputs.VIDEO_ID`, `web/src/lib/paste.ts` `BARE_ID`, API path checks) and the `_remove_cache_folder` / `cache_folder` check that uses it.
- Clip folders `<title> [<id>]`: ids from different sites could collide in one output folder and in `data/cache/<id>/`.
- "ยูทูป" in the UI copy and in error messages (`E_YT_REFUSED`, `E_BOT_CHECK`, the W1 title, the temporary-account copy).
- The temporary YouTube account (FR-CK) and the anonymous visitor session.
- The storyboard (fast frames) and the sharp frames / capture paths, which rely on YouTube formats and storyboards.
- SponsorBlock segments and YouTube chapters as cut / split sources.

## 11. Open questions for the owner (with verbatim drafts)

The spec does not ship these strings until Pete answers.

| # | Question | Draft(s) |
|---|---|---|
| Q1 | **Sample clip for the example** when no clip was opened yet. PRD `:306` says "ชื่อตัวอย่างภาษาไทย" but gives none, and `title-channel` also needs a sample channel. | **A** reuse the PRD AC-OUT-01 title: title `ทดสอบ: "A/B" <ภาค 1>?` (shows the safe-name rule: `ทดสอบ AB ภาค 1`), channel `ช่องตัวอย่าง` · **B** title `สอนทำกับข้าวง่าย ๆ ใน 10 นาที`, channel `ครัวบ้านเรา` |
| Q2 | **Import success toast.** The spec reuses "บันทึกแล้ว" (W6 already uses it after every change). A dedicated line? | **A** keep `บันทึกแล้ว` · **B** `นำเข้าค่าตั้งแล้ว` |
| Q3 | **Import warning when the folder in the file cannot be used here** (FR-SET-7 "คงโฟลเดอร์เดิมและบอกผู้ใช้"; no copy in PRD/BRD). Shown as a warning toast that stays until dismissed. | `นำเข้าค่าตั้งแล้ว แต่ใช้โฟลเดอร์ผลลัพธ์ในไฟล์บนเครื่องนี้ไม่ได้ จึงใช้โฟลเดอร์เดิมต่อ` |
| Q4 | **m4a quality label.** The spec uses the format name the staff pick plus the measured bitrate, e.g. `(m4a 130k)` (YouTube's ~129.5 kbps rounds to 130). Alternative: the nominal `(m4a 128k)` by rounding to the nearest of 48/64/96/128/160/256 k. Not Thai copy, but visible in every file name. | **A** measured, rounded: `(m4a 130k)` · **B** nominal: `(m4a 128k)` |

## 12. Review focus (top 5 failure modes the tests may miss)

1. **Unicode drift between Python and the browser.** `unicodedata` (Python 3.13: Unicode 15.1) and the browser's `\p{…}` tables (Chrome's ICU) can classify a new character differently, so a preview may differ from the real name by one character for very new emoji or marks. The fixture pins today's tables; check that the fixture includes a recent emoji and a Thai mark, and that a mismatch only affects the example, never the file.
2. **Clear vs. a cache writer outside the queue.** A second tab building a storyboard or saving subtitle tokens while the clear renames that folder. The staging rule covers the storyboard build; the atomic writers recreate the folder or log and retry. Check by clearing while another tab loads a long clip's frames: no 500, and the next open works.
3. **Windows rename while a file is open.** `os.rename` of a cache folder fails when the browser or Explorer holds a thumbnail open; `rmtree` may also leave files. Check that `freedBytes` is honest (not the planned size), the button size drops to the real remainder after refetch, and the `.clear-*` leftover disappears on the next start.
4. **The sweep pattern for styled names.** The `title-channel` / `title-quality` patterns are looser than today's (`_prefixes` on both parts, an optional quality group). Only 0-byte and `.part` files are ever deleted, but check a user file named like a cut toolkit name (`<title> - <something>.mp4.part` from another app) in a clip folder.
5. **Snapshot vs. retry from another path.** The style lives in the new `jobs.filename_style` column. Any code path that rebuilds a job (requeue on bot check, account retry, a future "duplicate job") must copy or keep it, or a retry gets a different name and the leftover sweep looks for the wrong pattern. Grep every `transition(..., "queued")` and every job insert.

## Out of scope (round A)
- Multi-site support (C12, §10).
- Renaming existing files when the style changes; a style per job in W2 / W3.
- Clearing the ffmpeg install leftovers in `work/`, `run/logs`, or `videos` rows.
- The statistics tab (FR-STAT) and the rest of M6.
- Phone layouts (C8).
