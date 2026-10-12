"""편집 거리·텍스트 평가와 VLM 결과의 실제 좌표 보존을 검증한다."""

import pytest

from pdf_ocr.evaluation import compare_text, edit_distance
from pdf_ocr.vl_engine import LocalVLEngine


@pytest.mark.parametrize(
    "reference,actual,expected",
    [("abc", "abc", 0), ("한자", "한", 1), ("한자", "漢字", 2), ("", "a", 1)],
)
def test_edit_distance(reference, actual, expected):
    """문자 삽입·삭제·치환과 동일 문자열의 편집 거리 기대값을 확인한다."""
    assert edit_distance(reference, actual) == expected


def test_space_errors_are_separate_from_character_errors():
    """공백 누락과 글자 오류를 서로 다른 정규화 지표로 구분하는지 확인한다."""
    result = compare_text("한글 OCR 漢字", "한글OCR漢字")
    assert result["ignore_whitespace"]["character_error_rate"] == 0
    assert result["whitespace_sensitive"]["edit_distance"] == 2


def test_empty_reference_is_rejected():
    """비어 있는 정답에 대해 의미 없는 오류율을 만들지 않는지 확인한다."""
    with pytest.raises(ValueError):
        compare_text("  ", "a")


def test_missing_vl_model_does_not_load_runtime(tmp_path):
    """로컬 모델 파일이 없으면 VLM 런타임 로딩 전에 실패하는지 확인한다."""
    with pytest.raises(FileNotFoundError):
        LocalVLEngine(tmp_path)


def test_hybrid_uses_real_regions_without_inventing_confidence():
    """영역별 VLM 결과에 검출 좌표만 연결하고 신뢰도는 만들지 않는지 확인한다."""
    from PIL import Image

    class Detector:
        """정해진 실제 형태의 사각형을 반환하는 검출기 대역이다."""

        def recognize(self, image):
            """이미지 검출 결과 대역으로 고정 픽셀 다각형을 반환한다."""
            return [{"polygon": [[2, 2], [20, 2], [20, 10], [2, 10]]}]

    engine = LocalVLEngine.__new__(LocalVLEngine)
    engine.detector = Detector()

    def recognize(crop, limit):
        """전달한 자르기 크기·토큰 상한을 확인하고 신뢰도 없는 결과를 반환한다."""
        assert crop.size == (28, 18) and limit == 256
        return {"text": "한글 漢字", "confidence": None, "polygon": None}

    engine.recognize_region = recognize
    with Image.new("RGB", (40, 30)) as image:
        [result] = engine.recognize(image)
    assert result["confidence"] is None
    assert result["polygon"][0] == [2, 2]
    assert result["scope"] == "detected_region"
