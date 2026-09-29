# YT Toolkit: Competitive Feature Survey (2026-09-29)

Scope: read-only desktop research. Sources are fetched pages and search results from this session. Where sources disagreed or were thin, that is marked "unverified". This is not legal advice.

Legend. Value: High / Med / Low for Thai office staff (non-technical) making slides, training material, social posts. Effort: S (days) / M (1-2 weeks) / L (multi-week). Risk: ToS, cookies/login (forbidden for us), legal.

---

## 0. Two findings that matter more than any feature gap

1. **yt-dlp now needs an external JavaScript runtime for YouTube.** Since yt-dlp 2025.11.12, full YouTube support needs a JS runtime (Deno recommended; Deno min 2.3.0 per the wiki, Node 22+, QuickJS, Bun deprecated) plus the yt-dlp-ejs solver. Without it, YouTube support is "deprecated", formats get progressively fewer, and it may eventually stop working entirely. The yt-dlp maintainers advise GUI/wrapper developers to bundle or recommend Deno. yt-dlp looks for the runtime on PATH or next to yt-dlp.exe. Parabolic already ships an "in-app deno update" (release notes V2026.x) and YTDLnis 1.9.0 ships a PO-token server (BgUtils) in advanced settings. Our plan mentions auto-update of yt-dlp and a health check, but does NOT mention Deno. Our health check should verify "JS runtime present and version OK", and the installer/start.bat should bundle deno.exe.
   - https://github.com/yt-dlp/yt-dlp/issues/15012
   - https://github.com/yt-dlp/yt-dlp/wiki/EJS
   - https://github.com/NickvisionApps/Parabolic/releases
   - https://github.com/deniscerri/ytdlnis/releases
2. **The "YouTube to slides" niche is now commercial and AI-heavy, and it targets exactly our users.** SlideExtract/BibiGPT, Video2PPT, CopySlides and videotoslides.org detect slide changes, dedupe frames, and export PDF/PPTX/JPG/ZIP plus a timestamped transcript. Most are paid or limited (Video2PPT free plan: 10-minute cap, 3 conversions/month; Pro $7/month). Our storyboard + contact sheet + zip + sharp-frames planned set covers roughly 70% of it locally and free. What is missing is "unique-slide detection" and "export to PPTX/PDF".
   - https://bibigpt.co/en/features/youtube-slide-extractor
   - https://video2ppt.com/youtube-to-pdf
   - https://copyslides.com/video-to-slides-converter
   - https://videotoslides.org/

---

## 1. Product notes

### 1.1 cobalt.tools (imputnet/cobalt)
Sources: https://github.com/imputnet/cobalt , https://github.com/imputnet/cobalt/blob/main/docs/api.md , https://github.com/imputnet/cobalt/blob/main/web/i18n/en/settings.json , https://cobalt.tools/settings/video , https://cobalt.tools/settings/local

- Philosophy is "paste a link, get the file": no ads, trackers or paywalls, and only free, publicly accessible content. This is the same ethos as ours (no login, no cookies).
- Settings are in a left sidebar with categories: appearance, video, audio, metadata & saving, accessibility, privacy, advanced. Each option carries a one-line honest trade-off note, for example "h264: best compatibility, average quality, 1080p max"; "av1 and vp9 aren't widely supported"; "if preferred quality isn't available, next best is picked". Copy this wording style for our max-quality option.
- Quality fallback is stated in the UI ("next best is picked instead"). It removes "why did I not get 4K?" support questions.
- API/settings knobs worth noting:
  - `videoQuality` from max down to 144 (default 1080).
  - `audioFormat` best/mp3/ogg/wav/opus, `audioBitrate` 320 down to 8 (default 128).
  - `downloadMode` auto/audio/mute (mute = video with no audio).
  - `filenameStyle` classic/pretty/basic/nerdy.
  - `disableMetadata`.
  - `subtitleLang`.
  - YouTube-specific `youtubeVideoCodec` (h264/av1/vp9), `youtubeVideoContainer` (auto/mp4/webm/mkv), `youtubeDubLang`, `youtubeBetterAudio`.
- **Filename style presets** (classic/basic/pretty/nerdy) give non-technical users a way to pick a naming convention without templates.
- **"Mute" download mode** (silent video). Useful for slide backgrounds and social B-roll.
- **"Dubbed audio track by language"** (`youtubeDubLang`): pick a YouTube multi-language dub if available.
- **Saving method** setting: ask / download / share / copy.
- **Processing queue panel** opens automatically (with an "Auto Queue" opt-out). Accessibility toggles: reduce motion, reduce transparency.
- **Remux tab**: drag any local file onto the page and cobalt remuxes it on-device (fixes containers and old-editor compatibility, e.g. Vegas Pro, Windows Media Player). It is a real precedent for our v2 "local file toolkit" and shows what non-technical users actually ask for ("my editor won't open this file"). Sources: https://x.com/uwukko/status/1833340491699499051 , https://cobalt.tools/remux
- **Local processing** ("disabled / preferred / forced"): ffmpeg-based merge/transcode runs on the user's device (cobalt 11, desktop default from 2025-05-29). https://cobalt.tools/settings/local
- Response types include `picker` (multi-item posts, with thumbnails). Relevant only for non-YouTube sources, so skip.
- Infrastructure features (Turnstile, Api-Key, rate limits, custom processing servers) are for hosted instances. Not relevant to a local app.

### 1.2 Parabolic (NickvisionApps/Parabolic)
Sources: https://github.com/NickvisionApps/Parabolic , https://github.com/NickvisionApps/Parabolic/releases

- Frontend for yt-dlp with WinUI on Windows and GTK4/libadwaita on Linux. Formats: mp4, webm, mp3, opus, flac, wav. Concurrent downloads, metadata and subtitles.
- Add-download dialog with **thumbnail preview** and, in a recent release, a **subtitle search bar** in the dialog. Per the release summary the same release added thumbnails in the downloads view, and a "Failed" filter in the downloads view.
- Recent releases (V2026.2.x to V2026.5.0, as summarised by the fetch tool; exact version dates unverified):
  - **Time-frame cutting done with ffmpeg** because yt-dlp's own sectioning was unreliable. Relevant to our time-range cut: do the cut with ffmpeg, not `--download-sections` alone.
  - Preferred frame-rate selection.
  - **Total duration label for playlist items**.
  - **Automatic filename truncation** for very long names.
  - Improved playlist format selection (resolutions/bitrates).
  - Separate toggles for downloading audio and video immediately.
  - Extra yt-dlp args for discovery and download.
  - In-app deno update.
  - Windows portable build and arm64 builds.
  - Automatic translation of embedded metadata and chapters to the app language (supported sites).
- Browser extensions (Chrome/Firefox) and a right-click integration. This is the "send this tab to the app" pattern.
- Disclaimer in the README about DMCA/ToS. A short, visible "use responsibly" notice is the norm.

### 1.3 Stacher / Stacher7 (stacher.io)
Sources: https://stacher.io/ , https://en.linuxadictos.com/Stacher--the-ideal-interface-for-squeezing-out-YT-DLP-without-a-console..html , https://freewares.org/software/stacher7 , https://arroxy.orionus.dev/blog/arroxy-vs-stacher/ , https://github.com/Lacnard/stacher (this last one is a third-party repo whose relationship to the official app is unverified; treat its claims as low-confidence)

- **Multiple configuration profiles** (Stacher 7's headline feature): e.g. "best quality video", "podcast audio", "whole playlist". You switch profile instead of retweaking options. This maps to our "default formats" setting but as named, one-click presets.
- Default of 3 parallel downloads (we cap at 3, good match).
- **Trimming tool with start/end sliders**: download only the part of interest. A slider UX is friendlier than typed timestamps.
- **Clipboard listener** for automatic URL detection.
- **"Configuration Spotlight" (Ctrl+P)**: a search box over all settings. Fine for a very large settings surface; we do not need it.
- Subscriptions tied to profiles (auto-download new uploads). Tray minimise, "Pro Mode", command-line builder for power users.
- Licensing is unclear across sources (freeware per freewares.org, "freemium/proprietary" per the Arroxy comparison). Unverified; not important for us.
- Third-party repo claims: SQLite history with search and re-download, "open file / open folder" quick actions, encrypted credential vault. The credential vault is irrelevant to us.

### 1.4 Open Video Downloader / youtube-dl-gui (jely2002)
Sources: https://github.com/jely2002/youtube-dl-gui , https://github.com/jely2002/youtube-dl-gui/releases

- Version 3 is a rewrite in Vue 3 + Rust (Tauri) for speed and small footprint. Windows/macOS/Linux.
- Smart queue that balances concurrency to avoid slowing the PC (similar in spirit to our 1-3 cap).
- 3.2.x: **input filtering** (by date, size, custom params), **import URLs from a file**, **clipboard monitoring**, codec and track selection, timestamps/chapters for partial download, per-video setting overrides, 30 fps re-encode option, thumbnail extraction, **separate "creator-provided" vs "auto-generated" subtitle choices**.
- 3.1.x: pause/resume, folder organisation and **separate audio/video output folders**, global keyboard shortcuts, FLAC/WAV, subtitle embedding, path-traversal security fixes (relevant lesson for any local server writing files).
- Cookies, basic auth, password-protected videos (all things we forbid).
- Auto-updates for both the app and yt-dlp; light/dark follows the system.

### 1.5 Seal (JunkFood02/Seal, Android)
Sources: https://github.com/JunkFood02/Seal , https://github.com/JunkFood02/Seal/releases

- Material Design 3, dynamic colour. Simple, guided flow for casual users with advanced options behind it. 900+ sites via yt-dlp.
- Playlist download in one tap; **format and playlist selection inside "Quick Download"**.
- **Custom command templates** (saved yt-dlp arguments) plus embedded aria2c.
- Subtitles: download auto-translated subtitles; **remembers subtitle preferences**; search inside subtitle options.
- **Search inside download history; export/import history** to file or clipboard.
- Resume failed/cancelled downloads. Queue plus concurrent downloading (v2 alphas).
- Metadata + thumbnail embedding for audio. Remux to MKV for compatibility.

### 1.6 YTDLnis (deniscerri, Android)
Sources: https://github.com/deniscerri/ytdlnis , https://github.com/deniscerri/ytdlnis/releases

- **Per-item customisation inside playlists** (each item can have its own format and folder), batch format selection.
- **Scheduling**: download at a chosen date/time. Also "observe sources" (channel/playlist watching, minute-level intervals in 1.9.0).
- Video **cut by timestamp or chapter**, **split by chapters**, **SponsorBlock removal** with chapter embedding, video **cropping** (ffmpeg) in 1.8.x, metadata editing (title, author).
- Command templates, format presets, an in-app terminal, and backup/restore of settings and templates.
- **Filename template preview** (see the resulting name before saving).
- Batch links from a text file; "quick download" mode; incognito mode (no history); download logs for troubleshooting.
- Version 1.9.0 (Sept 2026) adds Python 3.14 with curl-cffi, an internal PO-token (BgUtils) server, YouTube-style history layout. Shows how fast the YouTube anti-bot situation is moving.
- Cookie management with enable/disable toggles (forbidden for us).

### 1.7 Tartube
Sources: https://tartube.sourceforge.io/ (docs page returned 403, so details come from the home page only)

- Video database organised into folders that mirror the filesystem; multiple databases across drives.
- **Classic Mode**: a simplified tab for quick paste-and-download without database management. A useful "two tiers of UI" precedent: our main page is effectively classic mode.
- Channel/playlist monitoring with scheduled checks; livestream detection and notifications (not relevant to us).
- **Video clips** (from chapter list or custom timestamps) and **video slicing** (remove sections via SponsorBlock or custom ranges).
- Profiles for download configurations; bandwidth limiting; duplicate prevention across platforms; bookmarks/favourites; "missing video detection".
- ffmpeg conversions (video to audio, change formats).
- Reputation: powerful but dense UI. Do not copy the density.

### 1.8 4K Video Downloader Plus (commercial benchmark)
Sources: https://www.4kdownload.com/products/videodownloader-42 , https://tidbits.com/watchlist/4k-video-downloader-plus-26-2/

- "Paste link, pick quality, download" with one-click playlists and channels; auto-download subscriptions.
- Subtitles in SRT in 50+ languages; MP4/MKV video, MP3/M4A/OGG audio; up to 8K, 3D and 360 videos.
- **Smart Mode**: pre-set format, quality, subtitles and destination once, and it applies to every later paste. Same idea as our "default formats", but presented as an obvious "remember my choices / don't ask again" mode. Good UX.
- Commercial split: free tier with quantity limits; Lite $15/yr, Personal $25 lifetime, Pro $45 lifetime including commercial-use rights (prices as scraped from the product page; may drift).
- Notes they have to care about: subscription refresh throttled to avoid IP restriction by YouTube (release 26.2); private/login content and an in-app proxy that "bypasses school or workplace firewall" (do not copy).
- Premium AI audio tools (vocal removal, voice isolation, echo removal). Adjacent to our v2 ideas.
- Only the Pro tier explicitly grants commercial use. This shows the market treats "work use" as a licensing concern for the tool itself, not for the content.

### 1.9 Others (2025-2026)

**Self-hosted yt-dlp web UIs (same form factor as ours: browser front end, server-side yt-dlp)**
- MeTube https://github.com/alexta69/metube : queue with concurrency limit, per-download quality/format/folder, **yt-dlp preset bundles**, chapter splitting, output templates, subscriptions, completed list with auto-removal, separate audio directory, browser extension/bookmarklet, iOS/Android shortcuts, light/dark/auto.
- Pinchflat https://github.com/kieraneglin/pinchflat : "sources + media profiles", title filters and cutoff dates, Shorts/livestream rules, SponsorBlock, **podcast RSS feeds** from downloads, Plex/Jellyfin integration, Apprise notifications, websocket live updates. Mostly archival-oriented; little for us except media profiles.
- yt-dlp-web-ui https://github.com/marcopiovanello/yt-dlp-web-ui : JSON-RPC, format selection "disabled by default, user-enabled" (progressive disclosure), themes, multi-language.

**YouTube to slides / lecture extraction**
- SlideExtract / BibiGPT https://bibigpt.co/en/features/youtube-slide-extractor : AI detects slide transitions, dedupes, exports PDF / editable PPTX / ZIP of hi-res key frames / scene-by-scene timestamped transcript (searchable, exportable to Markdown for Notion/Obsidian). Pro feature. UI languages include Thai.
- Video2PPT https://video2ppt.com/youtube-to-pdf : YouTube or MP4 to PDF, PPTX, JPG/PNG with transcript; "replace youtube with videoppt in the URL" trick; free 10 minutes / 3 per month, Pro $7/month, lifetime $198; says batch of 20+ videos.
- CopySlides https://copyslides.com/video-to-slides-converter : OCR turns captured frames into editable PPTX elements.
- videotoslides.org https://videotoslides.org/ : duplicate removal + OCR.
- Slideshow-Extractor (open source) https://github.com/TalentedB/Slideshow-Extractor : YouTube link or local file to PDF of slides.

**Transcript and summary tools**
- Glasp, NoteGPT, Eightify, Tactiq, HappyScribe (summary of tools: https://www.happyscribe.com/blog/how-to-summarize-youtube-videos , https://glasp.co/articles/best-youtube-summarizer-tools , https://notegpt.io/blog/top-10-youtube-summary-tools-you-must-try-in-2025). Common features: timestamps toggle, TXT/Markdown/CSV export, transcript highlight and notes, export to Notion/Obsidian, summaries by ChatGPT/Claude/Gemini, mind maps/flashcards/quizzes (NoteGPT), batch over a playlist (NoteGPT).
- Google NotebookLM accepts YouTube video transcripts as sources and generates audio/video overviews, slide decks and infographics (Nov 2025). https://en.wikipedia.org/wiki/NotebookLM (Thai coverage in the article: not confirmed).

**Frame and screenshot tools**
- Browser tools with a **contact-sheet / storyboard mode**, interval capture (every 1/2/5/10/30 s), timestamp labels on frames, thumbnail-candidate grids (12-30 evenly spaced), PNG/JPG/WebP output: Video Frame Grabber https://myguy.tools/tools/video-frame-grabber , TheFluxTrain https://thefluxtrain.com/tools/video-frame-extractor/ , WuTools https://wutools.com/video/extract-frames , VidShift https://vidshift.io/extract-frames/ , Small Video Tools https://smallvideotools.com/ , Firefox extension "Screenshot for YouTube" https://addons.mozilla.org/en-US/firefox/addon/youtube-frame-extractor/ , CLI vcsi https://pypi.org/project/vcsi/7.0.14/ .
- Conclusion: our contact sheet, zip and sharp-frames set is at or beyond the free-tool norm. The additions others have are timestamp labels on frames and an interval picker.

**Local transcription**
- Buzz https://github.com/chidiwilliams/buzz : free, offline Whisper on Windows; import audio/video; export TXT/SRT/VTT. Subtitle Edit (MIT) for timed captions. MacWhisper is Mac-only and commercial. Thai support specifics not confirmed in the results. Sources: https://chidiwilliams.github.io/buzz/docs , https://sourceforge.net/projects/buzz-captions/
- YouTube auto-generated Thai subtitles have been widely available since early 2026 (source is a forum post; treat as indicative): https://aseannow.com/topic/1338708-auto-generated-thai-now-widely-available-on-youtube/ . Thai has no spaces between words, so cue splitting needs a word tokenizer (e.g. `pythainlp` / ICU BreakIterator), otherwise cues break mid-word. Reference: https://sonix.ai/auto-caption-thai-videos (general statement about Thai captions needing tokenizer-based line breaks).

---

## 2. Consolidated gap list (features NOT in our v1 plan or v2 notes)

Ordered by value/effort. "Who" lists products where I saw the feature described in a source above.

| # | Gap | Who has it | Value | Effort | Risk / notes |
|---|-----|-----------|-------|--------|--------------|
| 1 | **JS runtime (Deno) bundled, checked in health page, updated with yt-dlp** | Parabolic (in-app deno update); yt-dlp maintainers recommend | High (without it YouTube downloads degrade/fail) | S-M | No ToS issue. Windows: deno.exe next to yt-dlp.exe is auto-detected. Deno min version 2.3.0. Add "JS runtime OK" to health check and copy-report. |
| 2 | **Named presets / profiles** ("Slides 1080p mp4", "Podcast mp3 192", "Subtitles only") selectable with one click on the preview page, plus "remember my choice" | Stacher 7 profiles; 4KVD Smart Mode; MeTube presets; Pinchflat media profiles; YTDLnis format presets | High | S-M | None. We already have "default formats" in Settings; presets are the more usable framing for non-technical staff. |
| 3 | **Clipboard watcher / auto-detect link on tab focus** (offer "paste from clipboard" button at least) | Stacher; Open Video Downloader (clipboard monitoring) | Med-High | S | Browsers only allow clipboard reads after a user gesture or permission, so ship a "Paste" button first. Never auto-read silently. |
| 4 | **Unique-slide detection** (scene-change / dedupe) that selects only slide transitions from a presentation-style video, with export to **PDF** and optionally **PPTX** | SlideExtract/BibiGPT, Video2PPT, CopySlides, videotoslides, Slideshow-Extractor | High (this is exactly "make slides from clips") | M (detection with ffmpeg scene filter + dedupe by hash) / L (editable PPTX) | Copyright: slides in someone else's talk are still their work. Show the ToS/copyright reminder. Keep it local (competitors are paid and cloud-based; local is our selling point). Consider PDF first, PPTX later. |
| 5 | **Timestamp labels on frames / contact sheet, and interval capture picker** (every N seconds; jump to exact time) | Small Video Tools, TheFluxTrain, WuTools, VidShift, Video Frame Grabber | Med-High | S | Font must support Thai (labels are digits; the clip title in the header needs a Thai font in the sheet renderer). |
| 6 | **Scene-by-scene transcript**: transcript cues aligned with frames, exported as Markdown with thumbnails | SlideExtract/BibiGPT; Glasp (timestamped, highlight, export) | High for training material | M | Depends on subtitle availability (see #8). |
| 7 | **"Copy" affordances**: copy transcript, copy link with timestamp, copy chapters list as text, copy description | cobalt (saving method includes "copy"); Glasp/NoteGPT (copy/export) | Med-High | S | None. Chapters-as-text is cheap: yt-dlp already returns chapters. |
| 8 | **Local speech-to-text fallback (Whisper) when a video has no captions, especially for Thai** | Buzz (free, offline, TXT/SRT/VTT), MacWhisper (Mac only), Subtitle Edit | High if many source clips have no Thai captions | L (model download, CPU-only speed on Radeon 680M / 16 GB RAM; Thai accuracy differs by model size) | No ToS/cookies issue; heavy install; v2 "optional layer" candidate. Note that YouTube now offers auto Thai captions widely (early 2026), so this may matter less than it did. |
| 9 | **Thai word-aware cue splitting** (tokenizer-based line breaks, presets by character/second) | Documented as an industry need for Thai captions (Sonix); none of the yt-dlp GUIs do it | High (Thai-specific differentiator) | M | Our plan says "Thai-friendly" and "cue-length presets" already. Gap is specifically word-boundary tokenization rather than character counts; verify it is planned. |
| 10 | **Filename style choices and preview** (classic/basic/pretty/nerdy in cobalt; template preview in YTDLnis) plus **auto-truncation of long names** | cobalt; YTDLnis; Parabolic (auto truncation) | Med | S | Thai titles plus Windows 260-char path limit are a real failure mode. Repo log shows a title-truncation commit already; confirm it covers the whole path length, not only titles. |
| 11 | **Mute (video-only) download mode** | cobalt (`downloadMode: mute`) | Med (slide backgrounds, social B-roll) | S | None. ffmpeg `-an` or yt-dlp video-only stream. |
| 12 | **Time-range cut via visual sliders / scrubber on a preview with start/end handles** (we have typed range) | Stacher (sliders); Parabolic (frame-accurate ffmpeg cut); Tartube | Med-High | M | Use ffmpeg for the actual cut (Parabolic replaced yt-dlp sections because they were unreliable). Frame-accurate vs keyframe cut choice should be explained in plain words. |
| 13 | **Subtitle source choice: creator-provided vs auto-generated, remember preference** | Open Video Downloader 3.2.x; Seal (remembers prefs) | Med | S | None. Helps staff avoid using low-quality auto captions by accident. |
| 14 | **Search inside history, export/import history** | Seal; Stacher (SQLite search) | Med | S | None. Export as CSV helps staff keep a record of where clips came from (attribution for training material). |
| 15 | **Source attribution record** per download (title, channel, URL, license, date) saved next to the file and copyable as a credit line | None found as a shipped feature (idea derived from the CC/ToS and Thai Copyright Act sections below) | Med-High (office use, credit lines in slides) | S | Cheap way to support responsible use. Also show YouTube licence type (CC-BY vs standard) since yt-dlp exposes it. Reference: https://support.google.com/youtube/answer/2797468 |
| 16 | **Import URLs from a text/CSV file; drag-drop of a .txt** | Open Video Downloader; YTDLnis | Low-Med (paste of many links already planned) | S | None. |
| 17 | **Separate output folders for audio/video/frames; per-type subfolders** | Open Video Downloader 3.1; MeTube | Med | S | None. |
| 18 | **Embed metadata/thumbnail; edit title/author before saving** | Seal; YTDLnis; Parabolic | Low-Med | S-M | None. |
| 19 | **Browser extension / bookmarklet: "send this tab to YT Toolkit"** | Parabolic (Chrome/Firefox extensions); MeTube (bookmarklet) | Med | M | Extension store review effort; a bookmarklet is S. Must respect our cross-site guard (recent repo commit blocks cross-site /api calls), so it should open the app with `?url=`. Beware putting anything sensitive in the URL (only the public video URL is fine). |
| 20 | **Playlist-item picker with per-item options and total-duration label** | Parabolic (duration label); YTDLnis (per-item customization); Seal (playlist selection) | Med | S-M | Verify our 200-item playlist UI has select-all/none, ranges, and duration sum. |
| 21 | **Pause/resume of a single download** (not only global emergency pause) | Open Video Downloader 3.1.2; Seal; Stacher | Low-Med | M | yt-dlp resumes partial files; pausing is mostly "cancel but keep .part". |
| 22 | **Scheduling ("download at 22:00")** | YTDLnis; Tartube | Low | M | None. Only helps slow office bandwidth. |
| 23 | **Channel/playlist subscriptions & auto-download** | Tartube; Stacher; MeTube; Pinchflat; 4KVD; YTDLnis | Low (archival, not our use) | L | 4KVD had to throttle subscription refresh to avoid IP restriction: rate-limit risk for a shared office IP. Skip for v1. |
| 24 | **Notification when a queue finishes** (browser notification / Windows toast) | Open Video Downloader; Seal; YTDLnis | Med | S | Browser Notification permission prompt; keep opt-in. |
| 25 | **Local file remux/convert drag-drop** (already v2 "file toolkit") | cobalt Remux tab | Med | M | Already on our v2 list. cobalt's framing "fix files your editor won't open" is the user-facing pitch to reuse. |
| 26 | **AI summary / key points / chapters draft** (already v2 "AI layer") | Glasp, NoteGPT, Eightify, NotebookLM | Med-High | M | Already on our v2 list. Competitors export to Markdown and Notion/Obsidian. Prefer local-first; sending transcripts to a cloud LLM is a privacy issue to state clearly. |
| 27 | **Accessibility toggles** (reduce motion, reduce transparency, larger text) | cobalt | Low-Med | S | Cheap and good for older staff. |
| 28 | **Setup/portable distribution** (portable zip, winget/scoop) | Parabolic (portable Windows build); Arroxy (Winget, Scoop) | Low-Med | M | Our planned start.bat with git-based updates is fine; check that staff without git can still update. |
| 29 | **Settings backup/restore** | YTDLnis | Low | S | Useful when a PC is replaced. |
| 30 | **Download logs shown in-app** (beyond copy-report) | YTDLnis | Low-Med | S | Planned diagnostics button probably covers this. |

Top 10 by combined score (value first, then effort): #1, #2, #4, #5, #6, #9, #7, #3, #15, #12.

### Notes on the gap list
- Gaps 1, 2, 4, 5, 6, 9, 15 are the ones that separate "a downloader" from "a tool that helps make slides and training material", which is our real differentiator. None of the desktop yt-dlp GUIs offer them; the slide-extractor products offer 4-6 but as paid cloud services.
- Gaps 3 and 7 are small polish items that produce a lot of perceived usability.

---

## 3. Ideas we should explicitly NOT copy

| Idea | Seen in | Reason |
|------|---------|--------|
| Browser cookies, cookie files, per-domain cookie vault, netrc, basic auth, password-protected videos | Open Video Downloader, Stacher, Parabolic (credentials), YTDLnis (cookie management), MeTube (cookies) | We forbid login and cookies. Also raises account-ban risk and stores sensitive data on shared office PCs. |
| Private, members-only or age-restricted downloads | 4KVD ("private videos and playlists" with access rights) | Needs login; ToS and access-control problems. |
| In-app proxy / bypassing school or workplace firewalls | 4KVD | Circumvents IT policy of the employer; damaging to an office tool's reputation. |
| Channel subscriptions and mass archive of an entire channel | Tartube, Pinchflat, 4KVD, MeTube | Archival, not our use case. Mass scraping raises IP-throttling risk (4KVD throttled its refresh schedule for this reason) and ToS exposure. Out of scope for v1. |
| Livestream capture, missing-video detection, media-server (Plex/Jellyfin) and podcast-RSS feeds | Tartube, Pinchflat | Piracy/archival-oriented; irrelevant to office work. |
| Custom yt-dlp command terminal / raw argument boxes, command builder, plugins | Seal, YTDLnis, Stacher Pro Mode, MeTube JSON options | Non-technical users; a foot-gun and a security surface (arbitrary arguments on a local server). If needed, keep it hidden behind an explicit Advanced flag, not in v1. |
| Cloud processing and hosted-instance features (Turnstile, Api-Key, custom processing servers) | cobalt | Not applicable to a local app; would also send user data off-machine. |
| Analytics/telemetry | cobalt has opt-out analytics | Our stance (no login, local-only) is stronger without telemetry. Diagnostics stay copy-report only. |
| Cloud "paste your video to our site" slide/summary services as the default path | BibiGPT, Video2PPT, NotebookLM | Uploading staff's work material to third parties is a privacy and compliance issue and costs money per use. Offer local first; any AI layer stays optional and explicit. |
| Dense "power user" UI (Tartube database trees, Stacher Spotlight, 100+ options) | Tartube, Stacher | Contradicts our audience. Use progressive disclosure (Seal, yt-dlp-web-ui hide format selection by default). |
| Aggressive "remove DRM/ads" or "bypass region" claims | (general class of downloader marketing) | Legal exposure and off-mission. Keep copy neutral: "for content you have the right to use." |
| Auto-clipboard read without a user gesture | Stacher / OVD do it natively | In a browser it is blocked or a privacy prompt; offer a Paste button instead. |
| Selling "commercial use" rights as a licence tier | 4KVD Pro | Misleading: the tool licence does not grant rights to the content. Our copy must not imply that downloading confers permission to reuse. |

---

## 4. Legal / ToS risk notes for the app's copy and defaults

- YouTube ToS says content may not be downloaded unless specifically permitted by the Service or with written permission from YouTube or the rights holder; the exception commonly cited is videos under a Creative Commons licence (attribution required, and some CC variants restrict commercial use). Sources: https://www.techsmith.com/blog/download-youtube-videos/ , https://support.google.com/youtube/answer/2797468 , https://www.termsfeed.com/blog/youtube-license-types/ . Secondary sources; read YouTube's own terms before making product claims.
- Thai Copyright Act B.E. 2537 s.32 is a general "does not conflict with normal exploitation and does not unreasonably prejudice the owner" test; listed exceptions include educational reproduction by a teacher or institution not for profit, and comment/criticism/introduction with acknowledgement of the owner. Commercial training material and social posts by a company may fall outside those exceptions. Sources: https://www.wipo.int/wipolex/en/legislation/details/3801 , https://library.siam-legal.com/thai-law/copyright-act-b-e-2537-exceptions-of-infringement-sections-32-35/ . Suggest a short Thai first-run notice ("use only content you have the right to use; give credit") and a credit-line copy button (gap #15). Get an actual Thai lawyer's view before publishing the app to third parties.
- Every competitor that is open source carries a similar responsibility disclaimer (cobalt README: users bear responsibility; Parabolic README: DMCA notice). Copy the pattern, keep it short.

---

## 5. Source list (all URLs referenced)

- cobalt: https://github.com/imputnet/cobalt , https://github.com/imputnet/cobalt/blob/main/docs/api.md , https://github.com/imputnet/cobalt/blob/main/web/i18n/en/settings.json , https://cobalt.tools/settings/video , https://cobalt.tools/settings/local , https://cobalt.tools/remux , https://x.com/uwukko/status/1833340491699499051
- Parabolic: https://github.com/NickvisionApps/Parabolic , https://github.com/NickvisionApps/Parabolic/releases
- Stacher: https://stacher.io/ , https://en.linuxadictos.com/Stacher--the-ideal-interface-for-squeezing-out-YT-DLP-without-a-console..html , https://freewares.org/software/stacher7 , https://arroxy.orionus.dev/blog/arroxy-vs-stacher/ , https://github.com/Lacnard/stacher
- Open Video Downloader: https://github.com/jely2002/youtube-dl-gui , https://github.com/jely2002/youtube-dl-gui/releases
- Seal: https://github.com/JunkFood02/Seal , https://github.com/JunkFood02/Seal/releases
- YTDLnis: https://github.com/deniscerri/ytdlnis , https://github.com/deniscerri/ytdlnis/releases
- Tartube: https://tartube.sourceforge.io/
- 4K Video Downloader Plus: https://www.4kdownload.com/products/videodownloader-42 , https://tidbits.com/watchlist/4k-video-downloader-plus-26-2/
- Web UIs: https://github.com/alexta69/metube , https://github.com/kieraneglin/pinchflat , https://github.com/marcopiovanello/yt-dlp-web-ui
- yt-dlp JS runtime: https://github.com/yt-dlp/yt-dlp/issues/15012 , https://github.com/yt-dlp/yt-dlp/wiki/EJS , https://github.com/yt-dlp/yt-dlp/issues/14404
- Slides tools: https://bibigpt.co/en/features/youtube-slide-extractor , https://video2ppt.com/youtube-to-pdf , https://copyslides.com/video-to-slides-converter , https://videotoslides.org/ , https://github.com/TalentedB/Slideshow-Extractor
- Transcript/summary tools: https://www.happyscribe.com/blog/how-to-summarize-youtube-videos , https://glasp.co/articles/best-youtube-summarizer-tools , https://notegpt.io/blog/top-10-youtube-summary-tools-you-must-try-in-2025 , https://en.wikipedia.org/wiki/NotebookLM
- Frame tools: https://myguy.tools/tools/video-frame-grabber , https://thefluxtrain.com/tools/video-frame-extractor/ , https://wutools.com/video/extract-frames , https://vidshift.io/extract-frames/ , https://smallvideotools.com/ , https://addons.mozilla.org/en-US/firefox/addon/youtube-frame-extractor/ , https://pypi.org/project/vcsi/7.0.14/
- Local transcription and Thai: https://github.com/chidiwilliams/buzz , https://chidiwilliams.github.io/buzz/docs , https://sourceforge.net/projects/buzz-captions/ , https://aseannow.com/topic/1338708-auto-generated-thai-now-widely-available-on-youtube/ , https://sonix.ai/auto-caption-thai-videos
- Legal: https://www.techsmith.com/blog/download-youtube-videos/ , https://support.google.com/youtube/answer/2797468 , https://www.termsfeed.com/blog/youtube-license-types/ , https://www.wipo.int/wipolex/en/legislation/details/3801 , https://library.siam-legal.com/thai-law/copyright-act-b-e-2537-exceptions-of-infringement-sections-32-35/

Caveats: page contents were summarised by a fetch tool, so exact wording and version numbers (especially Parabolic and YTDLnis release lists, 4KVD prices, and Video2PPT plan limits) should be re-verified before quoting externally. The Tartube docs and Stacher docs pages were not reachable (403/404). The Lacnard/stacher repo may not be the official Stacher product. Thai-specific accuracy claims for Whisper models and YouTube auto captions were not confirmed from primary sources.
