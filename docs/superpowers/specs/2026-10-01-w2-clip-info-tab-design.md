# W2 clip info tab, scannable stats, pinned comment author label, note fields, open in YouTube

Approved by the owner (Pete) on 2026-10-01, after the M3 round 2-3 preview.

## Problems the owner reported

1. The note's front matter has `views`, but no likes, comments or pinned comment.
2. A pinned comment should say whether the channel owner wrote it or a viewer did. Some clips (for example the WUKONG live set) show "ไม่มีคอมเมนต์ปักหมุด" because the pin is a viewer's comment, and the app filters those out.
3. The stats read like one long sentence. To find a single number, the eye has to scan the whole line.
4. The description, pinned comment and tags clutter the header. Expanding them pushes the frames, subtitles and transcript tabs down the page. The owner wants these opened on demand, with copy buttons visible only after opening, and placed with reading patterns in mind.
5. There is no way to open the clip on YouTube.

## Design

### 1. W2 header (fixed height, no expandable content)

- Keep in the header:
  - cover, title, channel;
  - the category badge and subtitle-track badge;
  - the buttons "บันทึกเป็นโน้ต (.md)" and the new "เปิดในยูทูป".
- **Stat tiles:** ยอดวิว · ไลก์ · คอมเมนต์ · ผู้ติดตาม · ความยาว · เผยแพร่.
  - Each tile shows a small muted label above a large value.
  - Layout: 6 in one row on wide screens; 3 per row below 640 px.
  - A tile whose value is missing is not rendered.
  - Number formatting stays as now: Thai compact "long" (for example "5.8 แสน"). The full number goes in `title` and `aria-label`.
- **Cover:**
  - It becomes a link to `https://www.youtube.com/watch?v={id}`, opening in a new tab (`target="_blank" rel="noopener noreferrer"`).
  - A play-icon overlay appears on hover and focus.
  - Accessible name: "เปิดในยูทูป: {title}".
- **"เปิดในยูทูป" button:** a secondary button styled link with an external-link icon, opening the same URL in a new tab.
- **Removed from the header:** description, chapters, pinned comment, tags and the most-replayed summary line. All of them move to the new tab.
- **Phone layout:** the round-2 layout stays (128 px cover beside the title, title clamped to 3 lines). The tab bar must still start within the first 800 px at 360 px wide, with long titles.

### 2. New fourth tab "ข้อมูลคลิป" (`?tab=info`)

- **Tab order:** ภาพเฟรม · ซับ · ทรานสคริปต์ · ข้อมูลคลิป. The default tab stays ภาพเฟรม.
- **Layout:**
  - From lg: two columns. Left column: คำอธิบาย, then Chapter, then ช่วงที่คนดูซ้ำบ่อย. Right column: คอมเมนต์ปักหมุด, then แท็ก.
  - Below lg: a single column in the same order (left column first).
- **Sections:**
  - Each section has an h2 heading and its own copy button. Copy buttons exist only inside this tab.
  - Sections are shown fully, with no accordions inside the tab: opening the tab is the "open to view" action.
  - A section with no data is not rendered.
  - If nothing at all is available, the tab shows one muted line "คลิปนี้ไม่มีข้อมูลเพิ่มเติม".
- **Description:** `white-space: pre-line`. URLs stay plain text, the existing rule.
- **Chapter and most-replayed time buttons:** behave as now (`?at=`, which jumps to the frames tab).
- **Pinned comment:**
  - It is fetched when the info tab is first opened, not on page load.
  - It shows a badge "เจ้าของช่อง" or "ผู้ชม" from `byUploader`. No author name is shown or stored.
  - The skeleton and the error/retry behaviour stay as now.
- **Tags:** all chips are visible, plus a copy button.

### 3. Frame context menu

- New item "เปิดในยูทูปตรงเวลานี้". It opens `https://www.youtube.com/watch?v={id}&t={floor(seconds)}s` in a new tab, with noopener.
- It is available from both the mouse and the keyboard menu, the same way as the existing items.

### 4. Pinned comment contract change (C-A2 v2)

- `GET /api/videos/{id}/pinned-comment` returns `{comment: {text, likes?, publishedText?, byUploader: boolean} | null}`.
- **Filter:** any comment with `is_pinned is True`. It is no longer limited to the uploader's own comments.
- **byUploader:** `author_is_uploader is True`.
- **Author fields:** still none (no name, id, avatar or URL). This is PDPA-minimal; only the boolean is new.
- **Disk cache:** files written by the old rule must not be trusted. Add a schema version to `pinned.json` and treat older files as a miss, so the WUKONG-type clips re-fetch once.
- **Fake backend:** add one fake id whose pin is a viewer's comment (`byUploader: false`), next to the existing fake ids.

### 5. Note (.md) additions (C-A3 v2)

- **Front matter:**
  - Add `likes`, `comments` and `channel_followers` as ints, in the same style as `views`.
  - Each key is omitted when its value is missing.
  - Order: `views`, `likes`, `comments`, `channel_followers`, then `source`.
- **Body:**
  - After Chapter and before the transcript, add `## คอมเมนต์ปักหมุด (เจ้าของช่อง)` or `## คอมเมนต์ปักหมุด (ผู้ชม)`, followed by the comment text lines.
- **Where the note gets the pinned comment:** from the pinned-comment service (it uses the cache and fetches on a miss).
  - Any error (E_NETWORK, E_BOT_CHECK, E_UNKNOWN, ...) or null means the section is omitted.
  - The note itself never fails because of the pinned comment.

## Out of scope

- Showing the comment author's name.
- A side drawer.
- Link-ifying URLs in descriptions.

## Testing

- Update existing unit tests and e2e tests that assert header-placed description, chapters, pinned comment or tags, so they test the same intent in the info tab. Do not delete their intent.
- New tests:
  - stat tiles (missing values hidden);
  - the info tab via URL and keyboard;
  - lazy pinned fetch;
  - the byUploader badge for both values;
  - the cover link and the header link, checking href, target and rel;
  - the context-menu item URL with `&t=`;
  - the note front-matter keys and the pinned section, both variants plus the omitted case;
  - the pinned-cache schema bump;
  - axe on the info tab;
  - the 360 px tab bar ≤ 800 px check stays green.
