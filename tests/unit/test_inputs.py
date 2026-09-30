"""ตัวแยกลิงก์ยูทูป (AC-IN-01..05, AC-SEC-05) — ไม่แตะเครือข่ายและไม่รันอะไรเลย"""

from __future__ import annotations

import pytest

from yttoolkit.core.inputs import (
    InputItem,
    is_mix_id,
    parse_line,
    parse_text,
    scan_text,
)

VID = "dQw4w9WgXcQ"
VID2 = "aqz-KE-bpKQ"
PL = "PLrAXtmErZgOeiKm4sgNOknGvNjby9efdf"


def video(line: str, video_id: str = VID) -> InputItem:
    return InputItem(input=line, kind="video", video_id=video_id)


# ---------- AC-IN-01 ----------


def test_ac_in_01_short_link_with_timestamp():
    line = "https://youtu.be/dQw4w9WgXcQ?t=42"
    assert parse_line(line) == video(line)


# ---------- AC-IN-02: ทุกรูปแบบที่รองรับ ----------


@pytest.mark.parametrize(
    "line",
    [
        f"https://www.youtube.com/watch?v={VID}",
        f"https://www.youtube.com/watch?v={VID}&t=1s",
        f"https://www.youtube.com/watch?feature=share&v={VID}",
        f"https://www.youtube.com/watch?pp=abc&v={VID}&index=3",
        f"https://youtube.com/watch?v={VID}",
        f"http://www.youtube.com/watch?v={VID}",
        f"https://m.youtube.com/watch?v={VID}",
        f"https://music.youtube.com/watch?v={VID}",
        f"https://youtu.be/{VID}",
        f"https://youtu.be/{VID}?si=abc",
        f"https://youtu.be/{VID}?t=42&si=abc",
        f"https://www.youtube.com/shorts/{VID}",
        f"https://www.youtube.com/shorts/{VID}?feature=share",
        f"https://m.youtube.com/shorts/{VID}",
        f"https://www.youtube.com/live/{VID}",
        f"https://www.youtube.com/live/{VID}?si=abc",
        f"https://www.youtube.com/embed/{VID}",
        f"https://www.youtube-nocookie.com/embed/{VID}",
        f"https://www.youtube.com/watch?v={VID}#t=10",
        # ไม่มี scheme
        f"www.youtube.com/watch?v={VID}",
        f"youtube.com/watch?feature=share&v={VID}",
        f"m.youtube.com/watch?v={VID}",
        f"youtu.be/{VID}",
        f"youtu.be/{VID}?si=abc",
        f"youtube.com/shorts/{VID}",
        f"youtube-nocookie.com/embed/{VID}",
        # ตัวพิมพ์ใหญ่ที่โดเมน/scheme (ID ต้องคงตัวพิมพ์เดิม)
        f"HTTPS://WWW.YOUTUBE.COM/watch?v={VID}",
        f"HTTPS://YOUTU.BE/{VID}",
        f"WWW.YOUTUBE.COM/watch?v={VID}",
        # เครื่องหมาย / ท้ายลิงก์
        f"https://www.youtube.com/watch/?v={VID}",
        f"https://youtu.be/{VID}/",
        f"https://www.youtube.com/shorts/{VID}/",
        f"https://www.youtube.com/live/{VID}/?si=abc",
        # ID ล้วน
        VID,
    ],
)
def test_ac_in_02_accepted_video_forms(line):
    assert parse_line(line) == video(line)


def test_video_id_keeps_case_and_symbols():
    assert parse_line(VID2).video_id == VID2
    assert parse_line("HTTPS://YOUTU.BE/aB_-cD1234E").video_id == "aB_-cD1234E"


def test_input_is_stripped_but_otherwise_preserved():
    item = parse_line(f"   https://youtu.be/{VID}\t ")
    assert item.input == f"https://youtu.be/{VID}"
    assert item.video_id == VID


# ---------- เพลย์ลิสต์ ----------


@pytest.mark.parametrize(
    "line",
    [
        f"https://www.youtube.com/playlist?list={PL}",
        f"youtube.com/playlist?list={PL}",
        f"https://m.youtube.com/playlist?list={PL}&si=abc",
        f"https://music.youtube.com/playlist?list={PL}",
        f"https://www.youtube.com/playlist/?list={PL}",
        f"https://www.youtube.com/embed/videoseries?list={PL}",
        f"HTTPS://WWW.YOUTUBE.COM/playlist?list={PL}",
    ],
)
def test_playlist_links(line):
    assert parse_line(line) == InputItem(input=line, kind="playlist", playlist_id=PL)


@pytest.mark.parametrize("prefix", ["PL", "UU", "OL", "LL"])
def test_playlist_id_prefixes(prefix):
    pid = prefix + "abcDEF1234567"
    line = f"https://www.youtube.com/playlist?list={pid}"
    assert parse_line(line).playlist_id == pid


# ---------- AC-IN-05: ambiguous ----------


@pytest.mark.parametrize(
    "line",
    [
        f"https://www.youtube.com/watch?v={VID}&list={PL}",
        f"https://www.youtube.com/watch?v={VID}&list={PL}&index=3",
        f"https://www.youtube.com/watch?list={PL}&v={VID}&index=3",
        f"youtube.com/watch?v={VID}&list={PL}&index=3",
        f"https://youtu.be/{VID}?list={PL}",
        f"https://music.youtube.com/watch?v={VID}&list={PL}",
    ],
)
def test_ac_in_05_video_and_list_is_ambiguous(line):
    assert parse_line(line) == InputItem(
        input=line, kind="ambiguous", video_id=VID, playlist_id=PL
    )


def test_watch_with_unusable_list_is_video():
    line = f"https://www.youtube.com/watch?v={VID}&list=x"
    assert parse_line(line) == video(line)


# ---------- ไม่ถูกต้อง ----------


@pytest.mark.parametrize(
    "line",
    [
        # โดเมนอื่น
        "https://vimeo.com/123",
        f"https://vimeo.com/{VID}",
        # ไม่ใช่ลิงก์
        "hello",
        "watch",
        "https://",
        "youtube.com",
        "https://www.youtube.com/",
        "https://www.youtube.com/watch",
        "https://www.youtube.com/watch?v=",
        "https://www.youtube.com/playlist",
        "https://www.youtube.com/playlist?list=",
        "https://www.youtube.com/channel/UC1234567890abcdefghij",
        "https://www.youtube.com/@somebody",
        # ID ผิดรูป
        "dQw4w9WgXc",  # 10 ตัว
        "dQw4w9WgXcQQ",  # 12 ตัว
        "dQw4w9WgXc!",
        f"https://youtu.be/{VID}x",
        "https://youtu.be/short",
        "https://www.youtube.com/watch?v=tooshort",
        "https://www.youtube.com/watch?v=dQw4w9WgXcQtoolong",
        "https://www.youtube.com/shorts/abc",
        "https://www.youtube.com/playlist?list=short",
        # เส้นทางไม่ตรง
        f"https://www.youtube.com/watch/extra/{VID}",
        f"https://youtu.be/{VID}/extra",
        f"https://www.youtube.com/shorts/{VID}/extra",
        f"https://www.youtube.com/embed/{VID}/extra",
        f"https://www.youtube-nocookie.com/watch?v={VID}",
        f"https://youtu.be/watch?v={VID}",
        # โดเมนหลอก
        f"https://youtube.com.evil.example/watch?v={VID}",
        f"youtube.com.evil.example/watch?v={VID}",
        f"https://notyoutube.com/watch?v={VID}",
        f"https://evilyoutube.com/watch?v={VID}",
        f"https://youtu.be.evil.example/{VID}",
        f"https://evil.example/youtube.com/watch?v={VID}",
        f"https://evil.example/?u=youtube.com/watch?v={VID}",
        f"https://www.youtube.com@evil.example/watch?v={VID}",
        f"https://youtube.com:evil@evil.example/watch?v={VID}",
        f"https://www.youtube.com:8080/watch?v={VID}",
        f"https://www.youtube.com./watch?v={VID}",
        f"https://xn--youtube.com/watch?v={VID}",
        f"https://www.youtube.co/watch?v={VID}",
        f"https://www.youtube.com.au/watch?v={VID}",
        # scheme อื่น
        f"ftp://www.youtube.com/watch?v={VID}",
        f"javascript:alert(1)//youtube.com/watch?v={VID}",
        f"file://youtube.com/watch?v={VID}",
        f"data:text/html,youtube.com/watch?v={VID}",
        # AC-SEC-05: อักขระคล้ายคำสั่งเชลล์
        "; rm -rf /",
        "$(whoami)",
        "`whoami`",
        "a | b",
        "a & b",
        f"{VID}; rm -rf /",
        f"{VID}&whoami",
        f"{VID}|calc",
        f"{VID}$(whoami)",
        f"https://youtu.be/{VID};rm -rf /",
        f"https://youtu.be/{VID}?t=1; rm -rf /",
        f"https://www.youtube.com/watch?v={VID}&x=$(whoami)",
        f"https://www.youtube.com/watch?v={VID}|calc.exe",
        f"https://www.youtube.com/watch?v={VID} & calc",
        f"https://www.youtube.com/watch?v={VID}\nhttps://youtu.be/{VID}",
        "https://$(whoami).youtube.com/watch?v=" + VID,
        "https://[::1/watch?v=" + VID,
        "http://[",
        "%0a",
        "\x00",
        "\x00" + VID,
        VID + "\x00",
        "\u200b" + VID,
    ],
)
def test_invalid_inputs(line):
    item = parse_line(line)
    assert item.kind == "invalid"
    assert item.video_id is None
    assert item.playlist_id is None
    assert item.input == line.strip()


def test_empty_and_blank_lines_are_invalid_for_parse_line():
    assert parse_line("").kind == "invalid"
    assert parse_line("   ").kind == "invalid"


# ---------- ลิงก์ที่แอปแชตห่อมา / มีเครื่องหมายท้ายประโยค ----------

URL = f"https://youtu.be/{VID}"


@pytest.mark.parametrize(
    "line",
    [
        f"<{URL}>",
        f'"{URL}"',
        f"'{URL}'",
        f"({URL})",
        f"[คลิปนี้]({URL})",
        f"[https://youtu.be/{VID}]({URL})",
        f"[]({URL})",
        f"<youtu.be/{VID}>",
        f"<{URL}?t=42>",
        f"[watch](https://www.youtube.com/watch?v={VID}&t=1s)",
        f"  <{URL}>  ",
        f"{URL}.",
        f"{URL},",
        f"<{URL}.>",
        f"<{URL}>.",
        f"{VID}.",
        f"{VID},",
        f"https://www.youtube.com/watch?v={VID}.",
        f'"{VID}"',
    ],
)
def test_wrapped_links_are_unwrapped_but_input_keeps_original(line):
    item = parse_line(line)
    assert item.kind == "video"
    assert item.video_id == VID
    assert item.input == line.strip()


def test_wrapped_playlist_and_ambiguous():
    pl = f"https://www.youtube.com/playlist?list={PL}"
    assert parse_line(f"<{pl}>").kind == "playlist"
    amb = f"https://www.youtube.com/watch?v={VID}&list={PL}"
    item = parse_line(f"({amb}),")
    assert (item.kind, item.video_id, item.playlist_id) == ("ambiguous", VID, PL)


@pytest.mark.parametrize(
    "line",
    [
        # ห่อไม่ครบคู่ / คนละชนิด
        f"<{URL}",
        f"{URL}>",
        f'"{URL}',
        f"{URL}'",
        f"(({URL})",
        f"<{URL})",
        f"\"{URL}'",
        f"[คลิป]({URL}",
        f"[คลิป]{URL}",
        f"[คลิป](<{URL}>)",
        # ห่อซ้อน: ถอดได้แค่ชั้นเดียว
        f"<<{URL}>>",
        f'"<{URL}>"',
        f"(({URL}))",
        f"[a]([b]({URL}))",
        # เนื้อในต้องผ่านการตรวจเดิมทุกข้อ
        "<$(x)>",
        "($(whoami))",
        '"; rm -rf /"',
        "<; rm -rf />",
        f"<{URL}; rm -rf />",
        "[$(x)]($(whoami))",
        f"[x](https://evil.example/watch?v={VID})",
        f"<https://evil.example/{VID}>",
        f"<https://youtube.com.evil.example/watch?v={VID}>",
        "<hello>",
        "<>",
        "()",
        '""',
        "[]()",
        # เครื่องหมายท้ายตัดได้แค่ตัวเดียว
        f"{URL}..",
        f"{URL},.",
        f"{URL};",
        f"{URL}!",
    ],
)
def test_wrapper_edge_cases_stay_invalid(line):
    item = parse_line(line)
    assert item.kind == "invalid"
    assert item.input == line.strip()


def test_wrapped_lines_deduplicate_against_plain_ones():
    items = parse_text("\n".join([URL, f"<{URL}>", f"[x]({URL}),", VID]))
    assert len(items) == 1
    assert items[0].input == URL


# ---------- เส้นทางเก่า /v/ และ /e/ ----------


@pytest.mark.parametrize(
    "line",
    [
        f"https://www.youtube.com/v/{VID}",
        f"https://www.youtube.com/e/{VID}",
        f"youtube.com/v/{VID}?version=3",
        f"https://m.youtube.com/v/{VID}/",
    ],
)
def test_legacy_v_and_e_paths(line):
    assert parse_line(line) == video(line)


@pytest.mark.parametrize(
    "line",
    [
        f"https://youtu.be/v/{VID}",
        f"https://www.youtube-nocookie.com/v/{VID}",
        "https://www.youtube.com/v/short",
        f"https://www.youtube.com/v/{VID}/extra",
    ],
)
def test_legacy_paths_only_where_allowed(line):
    assert parse_line(line).kind == "invalid"


# ---------- watch?list= ไม่มี v ----------


def test_watch_with_only_list_is_playlist():
    line = f"https://www.youtube.com/watch?list={PL}"
    assert parse_line(line) == InputItem(input=line, kind="playlist", playlist_id=PL)


def test_watch_with_bad_v_and_no_list_is_invalid():
    assert parse_line("https://www.youtube.com/watch?v=short").kind == "invalid"


# ---------- RD mix ----------


@pytest.mark.parametrize(
    "line",
    [
        f"https://www.youtube.com/playlist?list=RD{VID}",
        f"https://www.youtube.com/playlist?list=RDMM{VID}",
        f"https://www.youtube.com/watch?list=RD{VID}",
        f"https://www.youtube.com/embed/videoseries?list=RD{VID}",
    ],
)
def test_rd_mix_alone_is_not_a_playlist(line):
    assert parse_line(line).kind == "invalid"


def test_rd_prefix_is_case_sensitive():
    # ID ของยูทูปแยกตัวพิมพ์ใหญ่/เล็ก "rd..." ไม่ใช่ mix
    line = f"https://www.youtube.com/watch?v={VID}&list=rdabcdefghij"
    item = parse_line(line)
    assert item.kind == "ambiguous"
    assert item.is_mix is False


def mix(line: str, mix_id: str = f"RD{VID}") -> InputItem:
    return InputItem(
        input=line, kind="ambiguous", video_id=VID, playlist_id=mix_id, is_mix=True
    )


@pytest.mark.parametrize(
    ("line", "mix_id"),
    [
        # ลิงก์ที่ยูทูปให้ตอนกดเล่น "มิกซ์" (มักมี start_radio=1 ต่อท้าย)
        (
            f"https://www.youtube.com/watch?v={VID}&list=RD{VID}&start_radio=1",
            f"RD{VID}",
        ),
        (f"https://www.youtube.com/watch?v={VID}&list=RD{VID}&index=2", f"RD{VID}"),
        (
            f"https://www.youtube.com/watch?v={VID}&pp=ygUFbXVzaWM%3D&list=RDMM{VID}&start_radio=1",
            f"RDMM{VID}",
        ),
        (f"https://www.youtube.com/watch?list=RD{VID}&v={VID}", f"RD{VID}"),
        (
            f"https://m.youtube.com/watch?v={VID}&list=RDdQw4w9WgXcQ&index=7&pp=x",
            "RDdQw4w9WgXcQ",
        ),
        (f"https://youtu.be/{VID}?list=RD{VID}", f"RD{VID}"),
        (f"https://youtu.be/{VID}?si=abc&list=RD{VID}&start_radio=1", f"RD{VID}"),
    ],
)
def test_watch_link_with_rd_list_is_an_ambiguous_mix(line, mix_id):
    assert parse_line(line) == mix(line, mix_id)


def test_normal_playlist_link_is_not_a_mix():
    item = parse_line(f"https://www.youtube.com/watch?v={VID}&list={PL}")
    assert item.kind == "ambiguous"
    assert item.is_mix is False


# ---------- ตัวคั่นที่ถูก encode ไม่ถูกถอดรหัส ----------


@pytest.mark.parametrize(
    "line",
    [
        f"https://www.youtube.com/watch%3Fv%3D{VID}",
        f"https://www.youtube.com/watch%3fv=%20{VID}",
        f"https%3A%2F%2Fyoutu.be%2F{VID}",
        f"https://youtu.be%2F{VID}",
        f"https://www.youtube.com%2Fwatch?v={VID}",
    ],
)
def test_encoded_delimiters_are_rejected_not_decoded(line):
    assert parse_line(line).kind == "invalid"


# ---------- parse_text: AC-IN-03 / AC-IN-04 ----------


def test_ac_in_03_five_lines_one_duplicate_one_blank_gives_three():
    text = "\n".join(
        [
            f"https://youtu.be/{VID}",
            "",
            f"https://www.youtube.com/watch?v={VID2}",
            f"https://www.youtube.com/watch?v={VID}&t=5s",  # ซ้ำกับบรรทัดแรก
            f"https://www.youtube.com/playlist?list={PL}",
        ]
    )
    items = parse_text(text)
    assert [i.kind for i in items] == ["video", "video", "playlist"]
    assert [i.video_id for i in items] == [VID, VID2, None]


def test_first_occurrence_wins_and_order_is_kept():
    first = f"https://youtu.be/{VID}"
    text = f"{VID2}\n{first}\nhttps://www.youtube.com/watch?v={VID}\n{VID}\n{VID2}"
    items = parse_text(text)
    assert [i.video_id for i in items] == [VID2, VID]
    assert items[1].input == first


def test_ac_in_04_invalid_line_among_valid_ones():
    text = f"https://youtu.be/{VID}\nhttps://vimeo.com/123\nhttps://youtu.be/{VID2}"
    items = parse_text(text)
    assert [i.kind for i in items] == ["video", "invalid", "video"]
    assert items[1].input == "https://vimeo.com/123"
    assert items[0].video_id == VID and items[2].video_id == VID2


def test_different_invalid_links_are_not_merged_but_repeats_are():
    text = "https://vimeo.com/1\nhttps://vimeo.com/2\nhttps://vimeo.com/1\nyoutube.com"
    items = parse_text(text)
    assert [i.input for i in items] == [
        "https://vimeo.com/1",
        "https://vimeo.com/2",
        "youtube.com",
    ]
    assert all(i.kind == "invalid" for i in items)


def test_ambiguous_and_video_of_same_id_are_distinct():
    text = (
        f"https://www.youtube.com/watch?v={VID}\n"
        f"https://www.youtube.com/watch?v={VID}&list={PL}"
    )
    assert [i.kind for i in parse_text(text)] == ["video", "ambiguous"]


def test_mix_and_plain_video_of_same_id_are_distinct():
    text = f"{VID}\nhttps://www.youtube.com/watch?v={VID}&list=RD{VID}"
    items = parse_text(text)
    assert [i.kind for i in items] == ["video", "ambiguous"]
    assert items[1].is_mix is True


def test_same_mix_twice_is_deduplicated():
    text = (
        f"https://www.youtube.com/watch?v={VID}&list=RD{VID}&start_radio=1\n"
        f"https://youtu.be/{VID}?list=RD{VID}"
    )
    assert len(parse_text(text)) == 1


def test_same_playlist_twice_is_deduplicated():
    text = (
        f"https://www.youtube.com/playlist?list={PL}\n"
        f"youtube.com/playlist?list={PL}&si=x"
    )
    assert len(parse_text(text)) == 1


@pytest.mark.parametrize("newline", ["\n", "\r\n", "\r"])
def test_line_endings(newline):
    text = newline.join([VID, VID2])
    assert [i.video_id for i in parse_text(text)] == [VID, VID2]


@pytest.mark.parametrize("text", ["", "\n", "   \n\t\n  ", "\r\n\r\n"])
def test_blank_text_gives_empty_list(text):
    assert parse_text(text) == []


def test_lines_are_stripped_in_parse_text():
    items = parse_text(f"  {VID}  \n\t{VID2}\t")
    assert [i.input for i in items] == [VID, VID2]


def test_input_item_is_frozen():
    item = parse_line(VID)
    with pytest.raises(AttributeError):
        item.kind = "invalid"  # type: ignore[misc]


# ---------- ดึงลิงก์จากข้อความปน (ข้อความจากแชต LINE) ----------

VID3 = "jNQXAC9IVRw"


def _kinds_and_ids(text: str) -> list[tuple[str, str | None]]:
    return [(i.kind, i.video_id) for i in parse_text(text)]


def test_line_chat_message_gives_two_clips_and_skips_the_greeting():
    text = "\n".join(
        [
            "สวัสดีครับ ส่งคลิปให้ดูครับ",
            f"1. https://youtu.be/{VID}",
            f"2. https://www.youtube.com/watch?v={VID2} ขอบคุณครับ",
        ]
    )
    scan = scan_text(text)
    assert [(i.kind, i.video_id) for i in scan.items] == [
        ("video", VID),
        ("video", VID2),
    ]
    # แถวแสดงเฉพาะตัวลิงก์ ไม่ใช่ทั้งบรรทัด
    assert [i.input for i in scan.items] == [
        f"https://youtu.be/{VID}",
        f"https://www.youtube.com/watch?v={VID2}",
    ]
    assert scan.skipped_text is True


@pytest.mark.parametrize(
    "line",
    [
        f"ดูอันนี้https://youtu.be/{VID}",
        f"https://youtu.be/{VID}ขอบคุณครับ",
        f"ดูอันนี้https://youtu.be/{VID}นะคะ",
        f"คลิปนี้ youtu.be/{VID} ค่ะ",
        f"ลิงก์ www.youtube.com/watch?v={VID}&t=5s ครับ",
        f"ลิงก์ m.youtube.com/watch?v={VID}",
        f"music.youtube.com/watch?v={VID} เพลงนี้",
        f"HTTPS://YOUTU.BE/{VID} ตัวใหญ่",
        f"“https://youtu.be/{VID}”",
        f"「https://youtu.be/{VID}」",
        f"‘https://youtu.be/{VID}’ครับ",
    ],
)
def test_links_glued_to_or_surrounded_by_thai_text(line):
    assert _kinds_and_ids(line) == [("video", VID)]


@pytest.mark.parametrize(
    "line",
    [
        f"1. https://youtu.be/{VID}",
        f"1) https://youtu.be/{VID}",
        f"12. https://youtu.be/{VID}",
        f"- https://youtu.be/{VID}",
        f"• https://youtu.be/{VID}",
        f"1.https://youtu.be/{VID}",
        f"-https://youtu.be/{VID}",
        f"•youtu.be/{VID}",
    ],
)
def test_numbering_and_bullets_are_not_counted_as_skipped_text(line):
    scan = scan_text(line)
    assert [(i.kind, i.video_id) for i in scan.items] == [("video", VID)]
    assert scan.skipped_text is False


@pytest.mark.parametrize(
    "line",
    [
        f"ดูคลิปนี้ (https://youtu.be/{VID})",
        f"ดูคลิปนี้ https://youtu.be/{VID}.",
        f"ดูคลิปนี้ https://youtu.be/{VID}),",
        f"ดู https://youtu.be/{VID}!",
        f"ดู https://youtu.be/{VID}?",
        f"ดู https://youtu.be/{VID}...",
        f"ดู https://youtu.be/{VID};",
        f"ดู https://youtu.be/{VID}:",
        f"ดู [https://youtu.be/{VID}]",
        f"ดู 'https://youtu.be/{VID}'",
        f'ดู "https://youtu.be/{VID}"',
        f"ดู <https://youtu.be/{VID}>",
    ],
)
def test_trailing_punctuation_and_brackets_are_stripped(line):
    assert _kinds_and_ids(line) == [("video", VID)]


def test_several_links_on_one_line_keep_their_order():
    text = f"https://youtu.be/{VID2} กับ https://youtu.be/{VID}, และ youtu.be/{VID3}."
    assert [i.video_id for i in parse_text(text)] == [VID2, VID, VID3]


def test_links_on_one_line_are_deduplicated_across_lines():
    text = (
        f"https://youtu.be/{VID} https://youtu.be/{VID2}\n"
        f"อีกรอบ https://www.youtube.com/watch?v={VID}"
    )
    assert [i.video_id for i in parse_text(text)] == [VID, VID2]


def test_playlist_and_ambiguous_links_inside_text():
    text = (
        f"เพลย์ลิสต์ https://www.youtube.com/playlist?list={PL} ครับ\n"
        f"คลิป https://www.youtube.com/watch?v={VID}&list={PL}"
    )
    items = parse_text(text)
    assert [(i.kind, i.video_id, i.playlist_id) for i in items] == [
        ("playlist", None, PL),
        ("ambiguous", VID, PL),
    ]


@pytest.mark.parametrize(
    ("line", "link"),
    [
        (
            "ไฟล์อยู่ที่ https://drive.google.com/file/d/abc/view ครับ",
            "https://drive.google.com/file/d/abc/view",
        ),
        (
            "https://www.facebook.com/watch?v=123",
            "https://www.facebook.com/watch?v=123",
        ),
        ("ดู facebook.com/somepage นะ", "facebook.com/somepage"),
        ("www.example.com", "www.example.com"),
        ("https://vimeo.com/123.", "https://vimeo.com/123"),
    ],
)
def test_links_to_other_sites_stay_invalid_rows(line, link):
    items = parse_text(line)
    assert [(i.kind, i.input) for i in items] == [("invalid", link)]


def test_broken_youtube_link_inside_text_is_an_invalid_row():
    items = parse_text("ช่องนี้ https://www.youtube.com/@somebody ครับ")
    assert [(i.kind, i.input) for i in items] == [
        ("invalid", "https://www.youtube.com/@somebody")
    ]


@pytest.mark.parametrize(
    "text",
    [
        "สวัสดีครับ",
        "hello",
        "ขอบคุณครับ\nแล้วเจอกันนะ",
        f"คำว่า {VID} ในประโยคไม่ใช่รหัสคลิป",
        f"1. {VID}",
        f"{VID} ครับ",
        "ไฟล์ report.pdf กับ e.g. ราคา 1.5 บาท",
    ],
)
def test_plain_words_are_skipped_silently_not_invalid_rows(text):
    scan = scan_text(text)
    assert scan.items == []
    assert scan.skipped_text is True


def test_bare_id_line_still_works():
    scan = scan_text(f"{VID}\n  {VID2}  ")
    assert [i.video_id for i in scan.items] == [VID, VID2]
    assert scan.skipped_text is False


def test_clean_links_have_no_skipped_text():
    scan = scan_text(
        f"https://youtu.be/{VID}\n\n[คลิป](https://youtu.be/{VID2})\n<youtu.be/{VID3}>"
    )
    assert len(scan.items) == 3
    assert scan.skipped_text is False


@pytest.mark.parametrize(
    "line",
    [
        f"https://youtu.be/{VID};rm -rf /",
        f"https://www.youtube.com/watch?v={VID}&x=$(whoami)",
        f"https://youtu.be/{VID}`whoami`",
    ],
)
def test_shell_characters_glued_to_a_link_keep_it_invalid(line):
    # AC-SEC-05: ชิ้นลิงก์ที่มีอักขระคำสั่งเชลล์ติดมายังไม่ผ่าน ไม่ถูกตัดทิ้งแล้วกลายเป็นคลิป
    assert [i.kind for i in parse_text(line)] == ["invalid"]


def test_extracted_links_are_checked_strictly():
    items = parse_text(
        f"ลิงก์ปลอม https://youtube.com.evil.example/watch?v={VID} กับ https://youtu.be/{VID}x"
    )
    assert [i.kind for i in items] == ["invalid", "invalid"]


@pytest.mark.parametrize(
    "text",
    [
        "a" * 20_000,
        "a." * 10_000,
        "http" * 5_000,
        ("x" * 30 + "://") * 600,
        "1." * 10_000,
        "ก" * 20_000,
    ],
    ids=["letters", "dots", "http", "schemes", "numbering", "thai"],
)
def test_long_text_is_scanned_without_a_clip(text):
    # ข้อความยาวสุดที่ /resolve รับ (20,000 ตัว): regex เริ่มหาได้เฉพาะต้นคำ ไม่วนหาซ้ำจนค้าง
    assert all(item.kind == "invalid" for item in scan_text(text).items)


# ---------- เพลย์ลิสต์ของ YouTube Music (RDCLAK) ไม่ใช่มิกซ์ (D6, 2026-09-30) ----------

CURATED = "RDCLAK5uy_kmPRjHDECIcuVwnKsx2Ng7fyNgFKWNJFs"


@pytest.mark.parametrize(
    "line",
    [
        f"https://www.youtube.com/watch?v={VID}&list={CURATED}",
        f"https://music.youtube.com/watch?v={VID}&list={CURATED}",
        f"https://youtu.be/{VID}?list={CURATED}",
    ],
)
def test_watch_link_with_a_curated_music_playlist_is_ambiguous_not_a_mix(line):
    assert parse_line(line) == InputItem(
        input=line, kind="ambiguous", video_id=VID, playlist_id=CURATED
    )


@pytest.mark.parametrize(
    "line",
    [
        f"https://www.youtube.com/playlist?list={CURATED}",
        f"https://music.youtube.com/playlist?list={CURATED}",
        f"music.youtube.com/playlist?list={CURATED}&si=abc",
        f"https://www.youtube.com/watch?list={CURATED}",
    ],
)
def test_bare_curated_music_playlist_is_a_playlist(line):
    assert parse_line(line) == InputItem(
        input=line, kind="playlist", playlist_id=CURATED
    )


@pytest.mark.parametrize(
    ("list_id", "expected"),
    [
        (f"RD{VID}", True),
        (f"RDMM{VID}", True),
        ("RDCLAK5uy_abcdefghij", False),
        ("RDCLA" + "x" * 10, True),
        ("rdabcdefghij", False),
        (PL, False),
    ],
)
def test_is_mix_id_is_the_one_rule(list_id, expected):
    assert is_mix_id(list_id) is expected
