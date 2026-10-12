import pytest

from pdf_ocr.paragraphs import restore_paragraphs


def line(text, y, left=10, right=300, height=20):
    return {
        "text": text,
        "polygon": [[left, y], [right, y], [right, y + height], [left, y + height]],
    }


def test_particle_join_and_indent_boundary():
    result = restore_paragraphs(
        [
            line("운전자는 제조사", 0, left=24),
            line("에 수리를 요청했다.", 30),
            line("다음 문단이다.", 60, left=24),
        ]
    )
    assert result["text"] == "운전자는 제조사에 수리를 요청했다.\n\n다음 문단이다."
    assert not result["reviews"]


def test_sentence_end_does_not_force_paragraph():
    result = restore_paragraphs(
        [line("첫 문장이다.", 0), line("같은 문단의 다음 문장이다.", 30)]
    )
    assert result["text"] == "첫 문장이다. 같은 문단의 다음 문장이다."


def test_ambiguous_korean_boundary_is_flagged_without_rewriting():
    result = restore_paragraphs([line("한국어 본문", 0), line("복원 작업", 30)])
    assert result["text"] == "한국어 본문 복원 작업"
    assert result["reviews"][0]["reason"] == "ambiguous_word_boundary"


def test_short_line_and_large_gap_keep_paragraphs():
    result = restore_paragraphs(
        [line("끝난 문단", 0, right=100), line("다음 문단", 30), line("먼 문단", 120)]
    )
    assert len(result["paragraphs"]) == 3


def test_title_and_list_are_preserved():
    result = restore_paragraphs(
        [
            line("제목", 0, height=40),
            line("본문 문장.", 60),
            line("1. 목록 하나", 90),
            line("2. 목록 둘", 120),
        ]
    )
    assert result["text"] == "제목\n\n본문 문장.\n\n1. 목록 하나\n\n2. 목록 둘"


def test_page_result_without_geometry_is_not_reflowed():
    result = restore_paragraphs([{"text": "문단 하나\n\n문단 둘", "polygon": None}])
    assert result["text"] == "문단 하나\n\n문단 둘"
    assert not result["geometry_applied"]


def test_columns_keep_original_order_and_require_review():
    lines = [line("왼쪽", 0, right=100), line("오른쪽", 0, left=200)]
    result = restore_paragraphs(lines)
    assert result["text"] == "왼쪽\n오른쪽"
    assert not result["geometry_applied"]


def test_hanja_option_and_source_immutability():
    lines = [line("본문本文", 0)]
    assert restore_paragraphs(lines)["text"] == "본문"
    assert restore_paragraphs(lines, False)["text"] == "본문本文"
    assert lines[0]["text"] == "본문本文"


def test_empty_lines_and_invalid_geometry():
    assert restore_paragraphs([])["text"] == ""
    with pytest.raises(ValueError):
        restore_paragraphs([line("본문", 0, height=0)])
