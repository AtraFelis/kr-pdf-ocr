"""PR #12 리뷰의 내부 빈 줄과 드문 겹침의 정상 영역 보존을 검증한다."""

import copy
import re

import pytest

from pdf_ocr.page_join import boundary_reason, combine_pages, paragraph_texts
from pdf_ocr.paragraphs import restore_paragraphs
from pdf_ocr.spacing import LocalSpacingRepair


def line(text, y, left=100, right=900, height=40):
    """합성 한 줄의 원문과 픽셀 사각형을 만든다."""
    return {
        "text": text,
        "polygon": [[left, y], [right, y], [right, y + height], [left, y + height]],
        "score": None,
    }


def overlapping_sample():
    """여러 정상 줄 사이에 작은 중복 여는 부호가 겹친 자료를 만든다."""
    lines = [line(f"문장을 이어가는 본문 {i}", i * 60) for i in range(8)]
    lines.insert(5, line('"', 243, left=101, right=112, height=12))
    return lines


def test_internal_blank_line_is_not_an_extra_geometry_paragraph():
    """OCR 한 줄 내부의 빈 줄을 옵션 켬/끔 모두 문단으로 재분할하지 않는다."""
    restored = restore_paragraphs([line("앞 문장\n\n뒤 문장", 0)])
    record = {"page": 1, "restoration": restored}
    for enabled in (False, True):
        result = combine_pages([record], enabled)
        assert result["text"] == "앞 문장\n\n뒤 문장"
        assert len(result["paragraphs"]) == 1


def test_variant_lists_preserve_internal_blank_lines():
    """문단별 보정 비교 배열과 문자열이 내부 개행을 포함해도 정렬을 유지한다."""
    restored = {
        "paragraphs": [{"text": "앞문장\n\n뒤 문장"}, {"text": "끝문장"}],
        "text": "앞문장\n\n뒤 문장\n\n끝문장",
        "spacing": {
            "before": "앞 문장\n\n뒤문장\n\n끝 문장",
            "paragraphs": {"before": ["앞 문장\n\n뒤문장", "끝 문장"]},
        },
    }
    result = combine_pages([{"page": 1, "restoration": restored}], variant="before")
    assert len(result["paragraphs"]) == 2
    assert result["text"] == restored["spacing"]["before"]


def test_legacy_variant_is_aligned_by_characters():
    """이전 보정 문자열도 글자 순서로 문단을 맞추고 내부 빈 줄을 보존한다."""
    restored = {
        "paragraphs": [{"text": "앞문장\n\n뒤문장"}, {"text": "끝문장"}],
        "spacing": {"before": "앞 문장\n\n뒤 문장\n\n끝 문장"},
    }
    assert paragraph_texts(restored, "before") == ["앞 문장\n\n뒤 문장", "끝 문장"]


def test_variant_character_change_is_rejected():
    """비교 배열의 글자 변경을 공백 보정 결과로 받아들이지 않는다."""
    restored = {
        "paragraphs": [{"text": "원문"}],
        "spacing": {"paragraphs": {"before": ["다른문장"]}},
    }
    with pytest.raises(ValueError, match="원문 글자"):
        paragraph_texts(restored, "before")


def test_isolated_overlap_preserves_raw_and_all_indices():
    """드문 겹침의 부호와 원시 좌표/순서를 보존하면서 정상 구간을 복원한다."""
    lines = overlapping_sample()
    original = copy.deepcopy(lines)
    result = restore_paragraphs(lines)
    assert result["partial_geometry_applied"]
    assert lines == original
    indices = [i for p in result["paragraphs"] for i in p["line_indices"]]
    assert sorted(indices) == list(range(len(lines)))
    blocked = [p for p in result["paragraphs"] if not p["geometry_applied"]]
    assert len(blocked) == 1
    assert blocked[0]["line_indices"] == [4, 5]
    assert blocked[0]["text"] == lines[4]["text"] + '\n"'
    assert re.sub(r"\s", "", result["text"]) == re.sub(
        r"\s", "", "".join(l["text"] for l in lines)
    )


def test_dense_columns_stay_unrestored():
    """겹침이 많은 다단 자료를 부분 복원 명목으로 읽기 순서 변경하지 않는다."""
    lines = [line("왼쪽", y, right=400) for y in [0, 60, 120]] + [
        line("오른쪽", y, left=500) for y in [0, 60, 120]
    ]
    result = restore_paragraphs(lines)
    assert not result["geometry_applied"]
    assert result["text"] == "\n".join(l["text"] for l in lines)


def test_kiwi_skips_only_ambiguous_paragraph():
    """부분 복원에서는 Kiwi가 모호한 블록만 건너뛰며 보정 비교 배열을 만든다."""
    restored = restore_paragraphs(overlapping_sample())
    repair = LocalSpacingRepair()
    result = repair.repair(restored)
    index = result["spacing"]["skipped_paragraph_indices"][0]
    assert result["paragraphs"][index]["text"] == restored["paragraphs"][index]["text"]
    assert result["spacing"]["paragraphs"]["before"] == [
        p["text"] for p in restored["paragraphs"]
    ]
    assert re.sub(r"\s", "", result["text"]) == re.sub(r"\s", "", restored["text"])
    for variant in (None, "before", "without_dictionary"):
        assert combine_pages([{"page": 1, "restoration": result}], variant=variant)[
            "text"
        ]


def test_partial_page_does_not_join_across_pages():
    """모호한 부분이 있는 페이지는 페이지 간 연결에서 확인 대상으로 보존한다."""
    previous = {"page": 1, "restoration": {"partial_geometry_applied": True}}
    assert boundary_reason(previous, {"page": 2}) == "partial_geometry_requires_review"
