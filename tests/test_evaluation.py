import pytest

from pdf_ocr.evaluation import compare_text, edit_distance
from pdf_ocr.vl_engine import LocalVLEngine


@pytest.mark.parametrize(
    "reference,actual,expected",
    [("abc", "abc", 0), ("한자", "한", 1), ("한자", "漢字", 2), ("", "a", 1)],
)
def test_edit_distance(reference, actual, expected):
    assert edit_distance(reference, actual) == expected


def test_space_errors_are_separate_from_character_errors():
    result = compare_text("한글 OCR 漢字", "한글OCR漢字")
    assert result["ignore_whitespace"]["character_error_rate"] == 0
    assert result["whitespace_sensitive"]["edit_distance"] == 2


def test_empty_reference_is_rejected():
    with pytest.raises(ValueError):
        compare_text("  ", "a")


def test_missing_vl_model_does_not_load_runtime(tmp_path):
    with pytest.raises(FileNotFoundError):
        LocalVLEngine(tmp_path)


def test_hybrid_uses_real_regions_without_inventing_confidence():
    from PIL import Image

    class Detector:
        def recognize(self, image):
            return [{"polygon": [[2, 2], [20, 2], [20, 10], [2, 10]]}]

    engine = LocalVLEngine.__new__(LocalVLEngine)
    engine.detector = Detector()

    def recognize(crop, limit):
        assert crop.size == (28, 18) and limit == 256
        return {"text": "한글 漢字", "confidence": None, "polygon": None}

    engine.recognize_region = recognize
    with Image.new("RGB", (40, 30)) as image:
        [result] = engine.recognize(image)
    assert result["confidence"] is None
    assert result["polygon"][0] == [2, 2]
    assert result["scope"] == "detected_region"
