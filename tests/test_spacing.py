"""로컬 띄어쓰기 보정이 공백 외 글자와 기존 문단을 보존하는지 검증한다."""

import re

import pytest

from pdf_ocr.paragraphs import restore_paragraphs
from pdf_ocr.spacing import LocalSpacingRepair


@pytest.fixture(scope="module")
def repairer():
    """실제 로컬 Kiwi 보정기를 모듈의 검사 동안 재사용한다."""
    return LocalSpacingRepair()


def test_real_local_spacing_rejoins_split_word_without_changing_characters(repairer):
    """실제 Kiwi가 나뉜 단어를 연결하며 글자와 원시 결과를 보존하는지 확인한다."""
    text = "운전자는 제조 사에 수리를 요청했다."
    result = {
        "geometry_applied": True,
        "paragraphs": [{"text": text, "line_indices": [0, 1]}],
        "reviews": [],
        "text": text,
    }
    repaired = repairer.repair(result)
    assert "제조사에" in repaired["text"]
    assert re.sub(r"\s", "", repaired["text"]) == re.sub(r"\s", "", text)
    assert repaired["reviews"][0]["reason"] == "spacing_suggestion"
    assert result["text"] == text


def test_generated_page_without_geometry_is_preserved(repairer):
    """좌표 없는 생성 결과에는 공백 보정을 적용하지 않는지 확인한다."""
    result = restore_paragraphs(
        [{"text": "독립 문단\n\n두 번째 문단", "polygon": None}]
    )
    assert repairer.repair(result) == result


def test_non_whitespace_edits_are_rejected():
    """보정 모델이 공백 외 글자를 바꾸면 적용을 중단하는지 확인한다."""

    class BadModel:
        """원문 글자를 의도적으로 바꾸는 잘못된 보정기 대역이다."""

        def space(self, text, reset_whitespace):
            """문자 보존 오류 확인을 위해 입력과 다른 글자를 반환한다."""
            return "새로운내용"

    repairer = LocalSpacingRepair.__new__(LocalSpacingRepair)
    repairer.kiwi = BadModel()
    with pytest.raises(ValueError, match="원문 글자"):
        repairer.repair(
            {
                "geometry_applied": True,
                "paragraphs": [{"text": "원문", "line_indices": [0]}],
                "reviews": [],
            }
        )
