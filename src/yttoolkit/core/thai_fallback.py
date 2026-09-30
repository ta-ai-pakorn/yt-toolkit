"""Thai word splitting for the subtitle builder's fallback path.

YouTube's Thai captions have no word timings, so the SRT builder needs a way
to cut long Thai lines at word boundaries instead of in the middle of a word.
PyThaiNLP's dictionary-based ``newmm`` tokenizer does that. The dictionary
ships inside the wheel, so nothing is downloaded and it works offline.

PyThaiNLP is imported lazily inside ``split_words``: it costs about half a
second to load, and most runs never see Thai text.
"""

from __future__ import annotations

import os
import re
import threading
from pathlib import Path

# PyThaiNLP's data-dir variable. ``PYTHAINLP_DATA_DIR`` is the deprecated
# spelling (it emits a DeprecationWarning, and setting both raises ValueError).
DATA_ENV = "PYTHAINLP_DATA"

_THAI_RE = re.compile("[\u0e00-\u0e7f]")
_lock = threading.Lock()


def configure(data_dir: Path) -> None:
    """Point PyThaiNLP's data folder at ``data_dir`` (call before first use).

    An existing value is never overwritten, so a user's own setting wins.
    """
    os.environ.setdefault(DATA_ENV, str(data_dir))


def has_thai(text: str) -> bool:
    """True when any character is in the Thai block (U+0E00 to U+0E7F)."""
    return _THAI_RE.search(text) is not None


def split_words(text: str) -> list[str]:
    """Split ``text`` into newmm words, keeping every character.

    Whitespace never stands alone: a space between words becomes a leading
    space on the next word, and trailing whitespace is glued onto the last
    word. ``"".join(result) == text`` always holds, and empty text gives [].
    """
    if not text:
        return []
    from pythainlp.tokenize import word_tokenize

    with _lock:
        pieces = word_tokenize(text, engine="newmm", keep_whitespace=True)

    words: list[str] = []
    pending = ""
    for piece in pieces:
        if not piece:
            continue
        if piece.strip() == "":
            pending += piece
            continue
        words.append(pending + piece)
        pending = ""
    if pending:
        if words:
            words[-1] += pending
        else:
            words.append(pending)
    return words
