"""ตรวจ path ที่มาจาก URL แบบไม่แตะดิสก์ ใช้ร่วมกันระหว่างหน้าเว็บ (static.py) และ /cache (videos.py)"""

from __future__ import annotations

from pathlib import PurePosixPath


def safe_parts(full_path: str) -> tuple[str, ...] | None:
    """แยก path เป็นชิ้น ๆ คืน None ถ้าอาจหลุดออกนอกโฟลเดอร์ที่อนุญาต

    ห้ามส่ง path ที่ผู้ใช้ส่งมาเข้า resolve()/is_file() ตรงๆ เพราะบน Windows
    path แบบ UNC (ขึ้นต้นด้วย backslash สองตัว) จะทำให้เครื่องไปต่อ SMB และหลุด NTLM hash
    """
    if any(ch in full_path for ch in ("\\", ":", "\x00")) or full_path.startswith("/"):
        return None
    parts = tuple(p for p in PurePosixPath(full_path).parts if p not in ("", "."))
    if not parts or ".." in parts:
        return None
    return parts
