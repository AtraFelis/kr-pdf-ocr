import re

import pytest

from pdf_ocr.paragraphs import restore_paragraphs
from pdf_ocr.spacing import LocalSpacingRepair


@pytest.fixture(scope="module")
def repairer():
    return LocalSpacingRepair()


def test_real_local_spacing_rejoins_split_word_without_changing_characters(repairer):
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
    result = restore_paragraphs(
        [{"text": "독립 문단\n\n두 번째 문단", "polygon": None}]
    )
    assert repairer.repair(result) == result


def test_non_whitespace_edits_are_rejected():
    class BadModel:
        def space(self, text, reset_whitespace):
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
