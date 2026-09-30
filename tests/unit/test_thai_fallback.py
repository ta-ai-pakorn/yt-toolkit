import os

import pytest

from yttoolkit.core import thai_fallback as tf


@pytest.fixture(autouse=True)
def _keep_data_dir_out_of_home(tmp_path, monkeypatch):
    # PyThaiNLP creates its data folder on first use; keep it out of ~/.
    monkeypatch.setenv(tf.DATA_ENV, str(tmp_path / "pythainlp-data"))


def test_split_words_rejoins_exactly():
    text = "ผมน่ะ ประทับใจมากเลย"
    words = tf.split_words(text)
    assert "".join(words) == text
    assert len(words) >= 4
    assert all(w.strip() for w in words)  # no whitespace-only pieces


def test_leading_space_goes_to_next_word():
    words = tf.split_words("สวัสดี ครับ")
    assert words[-1].startswith(" ")


def test_has_thai():
    assert tf.has_thai("abc ไทย") and not tf.has_thai("hello world")


def test_empty():
    assert tf.split_words("") == []


def test_no_boundary_inside_known_words():
    # Hard-coded from the PyThaiNLP 5.3.8 newmm run recorded in the commit.
    words = tf.split_words("ผมน่ะ ประทับใจมากเลย")
    assert words == ["ผม", "น่ะ", " ประทับใจ", "มาก", "เลย"]
    assert " ประทับใจ" in words  # never ประทับ | ใจ
    assert "มาก" in words and "เลย" in words  # มากเลย splits only between the two words


def test_trailing_whitespace_glued_onto_last_word():
    words = tf.split_words("ผม  ")
    assert "".join(words) == "ผม  "
    assert words == ["ผม  "]


def test_whitespace_only_text_is_kept():
    assert tf.split_words("  ") == ["  "]


def test_newline_between_words_is_glued_forward():
    words = tf.split_words("ผม\nไป")
    assert "".join(words) == "ผม\nไป"
    assert words[-1].startswith("\n")


@pytest.mark.parametrize(
    "text",
    [
        "สวัสดีครับ ทุกคน",
        " เริ่มต้นด้วยช่องว่าง",
        "mixed English และไทย 123",
        "ประโยคที่ยาวมากๆ เพื่อทดสอบการตัดคำ  สองช่องว่าง ",
    ],
)
def test_rejoin_is_exact(text):
    assert "".join(tf.split_words(text)) == text


def test_configure_sets_env_once(tmp_path, monkeypatch):
    monkeypatch.delenv(tf.DATA_ENV, raising=False)
    tf.configure(tmp_path / "pythainlp")
    assert os.environ[tf.DATA_ENV] == str(tmp_path / "pythainlp")
    tf.configure(tmp_path / "other")  # an existing value is never overwritten
    assert os.environ[tf.DATA_ENV] == str(tmp_path / "pythainlp")
