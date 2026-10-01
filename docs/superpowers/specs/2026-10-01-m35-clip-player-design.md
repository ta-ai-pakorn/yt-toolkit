# M3.5 clip player (W2) — design

The owner (Pete) approved this design on 2026-10-01. M3.5 sits between M3 and M4. It is a web-only milestone: there are no backend API changes, only docs.

## Goal

Watch the clip inside W2 using YouTube's official embedded player. Frames, transcript lines, chapters and most-replayed ranges all become ways to jump the player, and the frames and transcript follow along while it plays.

## 1. Player slot in the header (owner chose "C, docking to the corner like A")

- **Before play:**
  - The cover is shown as now, with a large centred ▶ button. Its accessible name is "เล่นคลิป".
  - Clicking the cover or the ▶ loads the player into the cover's box (same size and aspect ratio) and starts playback.
- **Loading on click only:** no YouTube script, iframe or request is made until the user presses play, or until another control asks the player to play.
- **Player setup:**
  - YouTube IFrame Player API, loaded from `https://www.youtube.com/iframe_api`.
  - Options: `host: "https://www.youtube-nocookie.com"`, `playerVars: { playsinline: 1, rel: 0, origin: location.origin }`.
  - The iframe must get `referrerpolicy="strict-origin-when-cross-origin"`. YouTube returns error 153 without a Referer.
- **The cover lightbox moves to a header button "ดูภาพปก":**
  - The button sits in the action row next to "บันทึกเป็นโน้ต (.md)" and "เปิดในยูทูป".
  - It is always available, in every player state.
  - Opening the lightbox does not pause playback.
- **Docking:**
  - This applies only once playback has started at least once. It does not need to be playing now; paused also counts.
  - When the header player box scrolls out of view (IntersectionObserver), the player moves to a floating mini player fixed at the bottom right.
    - Desktop: about 320 px wide, 16:9.
    - Below 640 px: a full-width bar fixed to the bottom of the screen, video about 40% of the screen width.
  - The same player instance moves between the two spots. Never create a second iframe; reparenting the iframe reloads it, so use a fixed-position wrapper that changes its layout with CSS.
- **The empty header slot while docked:**
  - It shows the cover dimmed, with the text "กำลังเล่นที่มุมจอ".
  - Clicking it scrolls back to the top, and the player returns to its slot.
- **Floating player buttons:**
  - ✕ ("ปิดตัวเล่น"): stops playback and returns the player to the header. The header then shows the cover with ▶ again.
  - "กลับไปที่หัวคลิป": scrolls to the top.
- **Layout guarantees:**
  - The floating player never covers the page's bottom content: add bottom padding to the page while it floats.
  - It must leave room for the M4 queue bar later. Use one CSS variable `--dock-bottom-offset`, default `0px`.
- **Reduced motion:** with `prefers-reduced-motion`, there is no animation when docking.

## 2. Timeline bar under the header player

- Width matches the player. It is shown only when the player is in the header slot (not when floating) and only after playback has started.
- It shows:
  - most-replayed ranges as amber blocks (from `mostReplayed`);
  - chapter starts as thin ticks (from `chapters`);
  - a playhead at `currentMs`.
- Click or tap seeks to that time and plays.
- Keyboard: it is a `role="slider"`, labelled "ตำแหน่งในคลิป", with `aria-valuetext` as a timecode. Left/Right move 5 s and Home/End jump to the ends; each seek happens on keyup.
- Clips with no duration show no bar.

## 3. "เล่นเฉพาะช่วงที่ดูซ้ำบ่อย" (highlight reel)

Amended in the integration round: the start button lives in the header action row, so the header height does not depend on mostReplayed before play. The status ("ช่วง {i} จาก {n}") and the stop button live in the timeline row, or on the docked player.

- A secondary button under the player. It is shown only when the clip has `mostReplayed`.
- It plays each range in order: seek to `startMs`, play, and when `currentMs >= endMs` seek to the next range.
- While a reel runs, the player shows the status text "ช่วง {i} จาก {n}" and a button "หยุดเล่นช่วงไฮไลต์". After the last range it pauses.
- A manual seek (timeline, frame, transcript or chapter) cancels the reel.

## 4. Sync: frames and transcript follow playback

- There is one player store, with `currentMs` updated about every 250 ms while playing.
- **Frames tab:**
  - The frame nearest to `currentMs` (the existing `nearestFrameIndex`) gets a "now playing" outline. It must look different from the focus ring, from the `?at=` highlight and from the amber most-replayed ring.
  - There is no auto-scroll of the grid.
  - Each frame gets a small ▶ button in a corner, shown on hover and on focus within. Its name is "เล่นจากตรงนี้ {timecode}". It plays from that frame's time. (Integration ruling: it is not in the Tab order, `tabindex="-1"`; keyboard users use the context-menu item below via Shift+F10.)
  - Clicking the image itself still opens the lightbox.
  - The context menu gets the item "เล่นจากตรงนี้".
- **Transcript tab:**
  - The last line whose start is at or before `currentMs` is highlighted (a karaoke-style band) and gets `aria-current="true"`. It stays lit through silent gaps and clears after the final line ends. (Integration ruling.)
  - Auto-follow: the list scrolls (the list only, never the page) so the highlighted line sits in the vertical centre of the list, clamped at the start and end. (Owner ruling in the final review; it was block "nearest".)
  - If the user scrolls the list themselves (wheel, touch or keyboard), auto-follow pauses and a button "กลับไปบรรทัดที่กำลังเล่น" appears. Pressing it resumes auto-follow.
  - Clicking a line's time plays from that line.
- **Info tab:** the chapter and most-replayed time buttons now play the player from that time, instead of jumping to the frames tab. The stale-jump guard is no longer needed for these buttons.
- **Unchanged:** the URL `?at=` behaviour for deep links and the frames highlight.

## 5. Errors

- `onError` codes:
  - 101 / 150 (embedding disabled): in the slot, show "เจ้าของคลิปไม่อนุญาตให้เล่นนอกยูทูป" plus the "เปิดในยูทูป" link (with `&t=` at the requested time).
  - 2 / 5 / 100 / 153 / other: show "เล่นคลิปนี้ในแอพไม่ได้" plus the "เปิดในยูทูป" link.
- If the API script fails to load (offline): show "ต้องต่ออินเทอร์เน็ตก่อนถึงจะเล่นคลิปได้" plus a "ลองอีกครั้ง" button.
- After an embed_blocked or unplayable error, "play from here" actions elsewhere do nothing except focus the error message in the slot.
- Offline is different: any play request (the slot's "ลองอีกครั้ง" or a "play from here" elsewhere) retries loading the script, then plays from the requested time if it loads. If iframe_api loaded but www-widgetapi.js did not, the app clears the stale `window.YT` first so the retry really reloads.
- When an error message first appears, it takes focus only if focus is on body or inside the player slot or dock. It never steals focus from another control.

## 6. Accessibility and copy

- Thai copy follows the existing rules: buttons start with a verb, no "กรุณา", no "!".
- The player iframe gets the title "ตัวเล่นคลิป: {title}".
- The floating player is a `region` labelled "ตัวเล่นคลิป (ลอย)". It is not a modal, and focus is never trapped.
- Run axe on W2 with the player in each state.

## 7. Testing

- The e2e and fake modes never contact YouTube. Tests intercept `https://www.youtube.com/iframe_api` and serve a fake `YT` API, helper `web/e2e/fake-yt.ts`, that simulates ready / play / pause / seek / currentTime / error.
- Unit tests:
  - the player store (state machine, reel progression, cancellation);
  - the transcript current-line lookup;
  - timeline geometry.
- e2e tests:
  - no request to YouTube before play;
  - click ▶ loads the player;
  - scroll → docks, and scroll back → returns;
  - ✕ stops it;
  - timeline seek;
  - frame ▶ and context menu;
  - transcript highlight, auto-follow and its pause/resume;
  - info-tab time buttons;
  - the reel progresses and stops;
  - error 150 → message and link;
  - script load failure → message and retry;
  - "ดูภาพปก" works in every state;
  - 360 px layout;
  - axe.

## Out of scope / later

- **M5 (with range download):** "ตั้งจุดเริ่ม/ตั้งจุดจบ" on the player, to send a range to the download form.
- Autoplay on page load, remembering the last position, and custom player controls. We use YouTube's own controls.
