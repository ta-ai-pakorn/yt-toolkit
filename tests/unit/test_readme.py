"""README คือคู่มือพนักงาน (M6 รอบ D spec §2.1, C3-C5): ไม่มีคำสั่งนักพัฒนา ป้ายตรงกับแอป รูปไม่ใหญ่เกิน"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
README = (ROOT / "README.md").read_text(encoding="utf-8")
TH = (ROOT / "web" / "src" / "i18n" / "th.ts").read_text(encoding="utf-8")


def test_no_developer_commands_for_staff():
    body = README.split("docs/development.md")[0]  # ทุกอย่างก่อนลิงก์ไปเอกสารนักพัฒนา
    for word in ("uv ", "npm", "pytest", "python"):
        assert word not in body.lower(), word


def test_links_to_development_doc():
    assert "docs/development.md" in README


def test_quoted_ui_labels_exist_in_the_app():
    # ป้ายในแอปที่ README อ้างถึงเขียนในเครื่องหมาย “…” (เครื่องหมายคำพูดโค้ง) ทุกป้ายต้องมีอยู่จริงใน th.ts
    labels = re.findall(r"“([^”]+)”", README)
    assert labels, "README should quote at least one UI label"
    missing = [label for label in labels if f'"{label}"' not in TH and label not in TH]
    assert missing == []


def test_cookies_guide_explains_private_window_and_names_no_extension():
    assert "ไม่ระบุตัวตน" in README
    for name in ("Get cookies.txt", "EditThisCookie", "cookies.txt LOCALLY"):
        assert name not in README


def test_images_exist_and_are_small():
    images = sorted((ROOT / "docs" / "images").glob("*.png"))
    assert images
    for image in images:
        assert image.stat().st_size <= 300_000, image.name
        assert f"docs/images/{image.name}" in README, image.name
