"""OCR 좌표 기반 문단 구분과 문자·원시 결과 보존을 검증한다."""

import pytest

from pdf_ocr.paragraphs import restore_paragraphs


def line(text, y, left=10, right=300, height=20):
    """지정한 텍스트·위치·크기로 합성 OCR 줄을 만든다."""
    return {
        "text": text,
        "polygon": [[left, y], [right, y], [right, y + height], [left, y + height]],
    }


def test_particle_join_and_indent_boundary():
    """명확한 조사 연결과 들여쓰기 문단 구분을 함께 확인한다."""
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
    """마침표가 있어도 같은 본문 문단의 줄을 이어 붙이는지 확인한다."""
    result = restore_paragraphs(
        [line("첫 문장이다.", 0), line("같은 문단의 다음 문장이다.", 30)]
    )
    assert result["text"] == "첫 문장이다. 같은 문단의 다음 문장이다."


def test_ambiguous_korean_boundary_is_flagged_without_rewriting():
    """모호한 단어 경계는 글자 변경 없이 확인 대상으로 기록하는지 확인한다."""
    result = restore_paragraphs([line("한국어 본문", 0), line("복원 작업", 30)])
    assert result["text"] == "한국어 본문 복원 작업"
    assert result["reviews"][0]["reason"] == "ambiguous_word_boundary"


def test_short_line_and_large_gap_keep_paragraphs():
    """짧은 마지막 줄과 큰 간격을 문단 경계로 처리하는지 확인한다."""
    result = restore_paragraphs(
        [line("끝난 문단", 0, right=100), line("다음 문단", 30), line("먼 문단", 120)]
    )
    assert len(result["paragraphs"]) == 3


def test_title_and_list_are_preserved():
    """글자 크기가 다른 제목과 번호 목록의 문단을 보존하는지 확인한다."""
    result = restore_paragraphs(
        [
            line("제목", 0, height=40),
            line("본문 문장.", 60),
            line("1. 목록 하나", 90),
            line("2. 목록 둘", 120),
        ]
    )
    assert result["text"] == "제목\n\n본문 문장.\n\n1. 목록 하나\n\n2. 목록 둘"


@pytest.mark.parametrize(
    "previous,ending,expected",
    [
        ("모두 함께 웃었", "다.", "모두 함께 웃었다."),
        ("그는 대답했", "다.”", "그는 대답했다.”"),
        ("그 사람은 학생이", "다", "그 사람은 학생이다"),
    ],
)
def test_short_ending_height_error_keeps_single_paragraph(previous, ending, expected):
    """높이 비율 1.34의 짧은 어미를 연결하되 원시 좌표·글자·인덱스는 보존한다."""
    import copy

    lines = [line(previous, 0, height=32), line(ending, 45, right=53, height=43)]
    original = copy.deepcopy(lines)
    result = restore_paragraphs(lines)
    assert result["text"] == expected
    assert result["paragraphs"][0]["line_indices"] == [0, 1]
    assert result["reviews"][0]["reason"] == "short_ending_continuation"
    assert result["reviews"][0]["requires_review"]
    assert lines == original


@pytest.mark.parametrize(
    "previous,current",
    [
        (line("앞 문장을 마쳤다.", 0, height=32), line("다.", 45, right=53, height=43)),
        (line("주인공이 웃었", 0, height=32), line("다. 다음 이야기", 45, height=43)),
        (line("주인공이 웃었", 0, height=32), line("다.", 150, right=53, height=43)),
        (
            line("주인공이 웃었", 0, height=32),
            line("다.", 45, left=50, right=93, height=43),
        ),
        (line("주인공이 웃었", 0, height=20), line("다.", 45, right=53, height=43)),
        (line("1. 주인공이 웃었", 0, height=32), line("다.", 45, right=53, height=43)),
    ],
)
def test_short_ending_does_not_override_real_boundaries(previous, current):
    """종결·다른 문장·큰 간격·들여쓰기·큰 글꼴·목록의 실제 경계를 유지한다."""
    result = restore_paragraphs([previous, current])
    assert len(result["paragraphs"]) == 2
    assert not any(
        r["reason"] == "short_ending_continuation" for r in result["reviews"]
    )


def test_short_previous_line_still_ends_paragraph():
    """앞줄 자체가 짧으면 어미처럼 보이는 다음 영역도 임의로 합치지 않는다."""
    lines = [
        line("이야기는 끝났", 0, right=120, height=32),
        line("다.", 45, right=53, height=43),
        line("독립적인 본문이다.", 100, right=300, height=32),
    ]
    result = restore_paragraphs(lines)
    assert result["paragraphs"][0]["line_indices"] == [0]
    assert result["paragraphs"][1]["line_indices"] == [1]


def test_page_result_without_geometry_is_not_reflowed():
    """좌표 없는 모델 출력의 기존 문단을 다시 연결하지 않는지 확인한다."""
    result = restore_paragraphs([{"text": "문단 하나\n\n문단 둘", "polygon": None}])
    assert result["text"] == "문단 하나\n\n문단 둘"
    assert not result["geometry_applied"]


def test_columns_keep_original_order_and_require_review():
    """겹치는 다단 줄은 원래 순서를 보존하고 검토 대상으로 남기는지 확인한다."""
    lines = [line("왼쪽", 0, right=100), line("오른쪽", 0, left=200)]
    result = restore_paragraphs(lines)
    assert result["text"] == "왼쪽\n오른쪽"
    assert not result["geometry_applied"]


def test_hanja_option_and_source_immutability():
    """한자 제외 옵션을 따르면서 원시 OCR 줄을 변경하지 않는지 확인한다."""
    lines = [line("본문本文", 0)]
    assert restore_paragraphs(lines)["text"] == "본문"
    assert restore_paragraphs(lines, False)["text"] == "본문本文"
    assert lines[0]["text"] == "본문本文"


def test_empty_lines_and_invalid_geometry():
    """빈 OCR 결과와 높이가 없는 잘못된 영역 처리를 확인한다."""
    assert restore_paragraphs([])["text"] == ""
    with pytest.raises(ValueError):
        restore_paragraphs([line("본문", 0, height=0)])


def test_detached_small_closing_quote_does_not_disable_page():
    """같은 줄의 작은 닫는 따옴표를 연결해 페이지 복원을 유지하고 원시 줄을 보존한다."""
    import copy

    lines = [
        line("첫본문은", 0, right=300, height=50),
        line("여기에계속된다.", 70, right=300, height=50),
        line("끝이다", 140, right=150, height=50),
        line("”", 146, left=148, right=161, height=13),
    ]
    original = copy.deepcopy(lines)
    result = restore_paragraphs(lines)
    assert result["geometry_applied"]
    assert result["text"].endswith("끝이다”")
    assert result["paragraphs"][-1]["line_indices"] == [0, 1, 2, 3]
    assert lines == original
    assert any(
        review == {"reason": "attached_closing_punctuation", "line_indices": [2, 3]}
        for review in result["reviews"]
    )


@pytest.mark.parametrize(
    "fragment",
    [
        line("”", 6, left=400, right=413, height=13),
        line("”", 6, left=100, right=113, height=13),
        line("”", 6, left=298, right=311, height=50),
        line("“", 6, left=298, right=311, height=13),
        line("x", 6, left=298, right=311, height=13),
    ],
)
def test_ambiguous_or_unrelated_fragment_keeps_original_layout(fragment):
    """멀거나 크거나 내부·여는 부호·문자인 영역은 추측 연결하지 않는다."""
    lines = [line("본문", 0, height=50), fragment]
    result = restore_paragraphs(lines)
    assert not result["geometry_applied"]
    assert result["text"] == "본문\n" + fragment["text"]


def test_fragment_with_two_hosts_does_not_merge_columns():
    """문장부호가 두 본문 후보에 걸치면 다단 복원을 생략하고 원래 순서를 지킨다."""
    lines = [
        line("첫영역", 0, right=300, height=50),
        line("다른영역", 5, left=250, right=305, height=50),
        line("”", 10, left=304, right=317, height=13),
    ]
    result = restore_paragraphs(lines)
    assert not result["geometry_applied"]
    assert result["text"] == "첫영역\n다른영역\n”"
