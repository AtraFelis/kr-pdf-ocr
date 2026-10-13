"""재인식 후보의 범위·실패·원시 결과 보존과 비교 UI를 합성 자료로 검증한다."""

import copy
import json
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PIL import Image
from PySide6.QtWidgets import QApplication

from pdf_ocr.retry import retry_lines, retry_reason
from pdf_ocr.retry_ui import RetryDialog


@pytest.mark.parametrize(
    "text,score,reason",
    [
        ("ac", 0.99, "short_text"),
        ("본문인식결과다", 0.99, "possible_missing_punctuation"),
        ("길고불확실한본문입니다.", 0.7, "low_score"),
        ("정상적인긴본문입니다.", 0.99, None),
        ("", 0.2, None),
    ],
)
def test_retry_selection(text, score, reason):
    """후보 선정과 종결 부호·빈 결과의 제외를 확인한다."""
    assert retry_reason({"text": text, "confidence": score}) == reason


def test_retry_clips_coordinates_preserves_raw_and_records_failure(tmp_path):
    """경계 여백을 입력 안으로 제한하고 후보 실패와 원시 글자·좌표를 따로 유지한다."""

    class Engine:
        """첫 조건은 성공하고 두 번째는 실패하는 로컬 모델 대역이다."""

        def __init__(self):
            """후보 호출 수를 초기화한다."""
            self.calls = 0

        def recognize_line(self, image):
            """확대 크기를 검사하고 한 번의 오류를 반환한다."""
            self.calls += 1
            assert image.width > 0 and image.height > 0
            if self.calls == 2:
                raise RuntimeError("합성 실패")
            return {"text": "응?", "confidence": 0.95}

    lines = [
        {
            "text": "ac",
            "confidence": 0.6,
            "polygon": [[0, 0], [10, 0], [10, 10], [0, 10]],
        }
    ]
    before = copy.deepcopy(lines)
    with Image.new("RGB", (20, 20), "white") as image:
        retries = retry_lines(image, lines, Engine(), tmp_path, 2)
    assert lines == before
    assert retries[0]["original"] == "ac"
    candidates = retries[0]["candidates"]
    assert candidates[0]["bbox_in_input"] == [0, 0, 12, 12]
    assert candidates[0]["state"] == "completed" and candidates[0]["text"] == "응?"
    assert candidates[1]["state"] == "failed" and "합성 실패" in candidates[1]["error"]
    assert (tmp_path / candidates[0]["image"]).exists()


def test_retry_limit_and_missing_geometry(tmp_path):
    """좌표 없는 줄을 건너뛰고 페이지의 최대 후보 수를 제한한다."""

    class Engine:
        """원문과 같은 후보만 반환하는 대역이다."""

        def recognize_line(self, image):
            """짧은 합성 결과를 반환한다."""
            return {"text": "응?", "confidence": 0.9}

    lines = [{"text": "응?", "polygon": None}] + [
        {"text": "응?", "polygon": [[0, 0], [10, 0], [10, 10], [0, 10]]}
        for _ in range(3)
    ]
    with Image.new("RGB", (20, 20), "white") as image:
        records = retry_lines(image, lines, Engine(), tmp_path, 1, limit=1)
    assert len(records) == 1 and records[0]["line_index"] == 1


def test_retry_dialog_copies_only_success_and_keeps_original(tmp_path):
    """성공한 후보만 복사하고 실패 안내·원시 파일 보존을 확인한다."""
    app = QApplication.instance() or QApplication([])
    path = tmp_path / "page-001.json"
    record = {
        "page": 1,
        "recognition_retry": [
            {
                "line_index": 0,
                "original": "ac",
                "candidates": [
                    {
                        "scale": 2,
                        "state": "completed",
                        "text": "응?",
                        "confidence": 0.9,
                    },
                    {"scale": 3, "state": "failed", "error": "합성 실패"},
                ],
            }
        ],
    }
    path.write_text(json.dumps(record), encoding="utf-8")
    before = path.read_bytes()
    previous = app.clipboard().text()
    dialog = RetryDialog(tmp_path)
    try:
        dialog.copy_candidate()
        assert app.clipboard().text() == "응?"
        dialog.list.setCurrentRow(1)
        assert (
            not dialog.copy_button.isEnabled()
            and "실패" in dialog.details.toPlainText()
        )
        dialog.copy_candidate()
        assert app.clipboard().text() == "응?"
        assert path.read_bytes() == before
    finally:
        app.clipboard().setText(previous)
        dialog.close()


def test_retry_option_rejected_for_markdown_before_output(tmp_path, monkeypatch):
    """미지원 형식은 모델 실행·출력 생성 전에 거부한다."""
    import sys

    from pdf_ocr import cli

    output = tmp_path / "new"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "ocr",
            "missing.pdf",
            "--engine",
            "vl16",
            "--format",
            "md",
            "--retry-short-lines",
            "--output",
            str(output),
        ],
    )
    with pytest.raises(SystemExit) as error:
        cli.main()
    assert error.value.code == 2 and not output.exists()


def test_quote_and_ellipsis_selected_even_with_high_score():
    """점수가 높아도 따옴표·말줄임표가 있는 줄을 문장부호 비교 대상으로 선정한다."""
    assert (
        retry_reason({"text": "“…긴 문장이 끝났다.”", "confidence": 0.99})
        == "quotation_or_ellipsis"
    )


def test_visual_retry_preserves_raw_and_clips_selection(tmp_path, monkeypatch):
    """VLM 후보의 영역·모델·미제공 점수를 기록하고 원시 인식과 문단 결과를 유지한다."""
    from pdf_ocr import retry_vl

    class Model:
        """외부 모델 없이 VLM 결과를 제공하는 대역이다."""

        def __init__(self, *args, **kwargs):
            """모델 설치를 생략한다."""

        def recognize_region(self, image, limit):
            """선택 영역 크기를 확인하고 짧은 대사를 반환한다."""
            assert image.size == (14, 14)
            return {"text": "“응?”", "token_limit_reached": False}

    monkeypatch.setattr(retry_vl, "LocalVLEngine", Model)
    page = tmp_path / "page-001.json"
    raw = {
        "page": 1,
        "region_pixel_box": [10, 10, 24, 24],
        "lines": [
            {
                "text": "ac",
                "confidence": 0.6,
                "polygon": [[10, 10], [22, 10], [22, 22], [10, 22]],
            }
        ],
        "restoration": {"text": "ac"},
    }
    page.write_text(json.dumps(raw), encoding="utf-8")
    with Image.new("RGB", (40, 40), "white") as image:
        image.save(page.with_suffix(".png"))
    candidate = retry_vl.retry_visual(page, 0, "PaddleOCR-VL-1.6", "cpu")
    saved = json.loads(page.read_text(encoding="utf-8"))
    assert saved["lines"] == raw["lines"] and saved["restoration"] == raw["restoration"]
    assert candidate["bbox"] == [10, 10, 24, 24] and candidate["bbox_in_input"] == [
        0,
        0,
        14,
        14,
    ]
    assert candidate["confidence"] is None and candidate["requires_review"]
    assert (tmp_path / candidate["image"]).is_file()


def test_visual_retry_truncated_result_keeps_existing_json(tmp_path, monkeypatch):
    """잘린 VLM 결과를 후보로 채택하지 않고 원래 페이지 JSON을 바꾸지 않는다."""
    from pdf_ocr import retry_vl

    class Model:
        """토큰 상한 도달을 반환하는 대역이다."""

        def __init__(self, *args, **kwargs):
            """실제 환경 설치를 생략한다."""

        def recognize_region(self, image, limit):
            """잘린 결과를 반환한다."""
            return {"text": "일부", "token_limit_reached": True}

    monkeypatch.setattr(retry_vl, "LocalVLEngine", Model)
    page = tmp_path / "page-001.json"
    page.write_text(
        json.dumps(
            {
                "page": 1,
                "lines": [
                    {"text": "ac", "polygon": [[0, 0], [10, 0], [10, 10], [0, 10]]}
                ],
            }
        ),
        encoding="utf-8",
    )
    before = page.read_bytes()
    with Image.new("RGB", (20, 20), "white") as image:
        image.save(page.with_suffix(".png"))
    with pytest.raises(ValueError, match="잘렸"):
        retry_vl.retry_visual(page, 0, "PaddleOCR-VL-1.6", "cpu")
    assert page.read_bytes() == before


def test_visual_retry_excludes_adjacent_line_fragments(tmp_path, monkeypatch):
    """재인식 여백이 앞뒤 줄의 일부를 포함하지 않도록 원본 좌표로 제한한다."""
    from pdf_ocr import retry_vl

    class Model:
        """영역 크기를 검사하는 합성 모델이다."""

        def __init__(self, *args, **kwargs):
            """실제 모델 설치를 생략한다."""

        def recognize_region(self, image, limit):
            """앞뒤 줄을 제외한 이미지 크기만 허용한다."""
            assert image.size == (42, 22)
            return {"text": "응?", "token_limit_reached": False}

    monkeypatch.setattr(retry_vl, "LocalVLEngine", Model)
    page = tmp_path / "page-001.json"
    lines = [
        {"text": "위", "polygon": [[10, 20], [40, 20], [40, 38], [10, 38]]},
        {"text": "ac", "polygon": [[10, 40], [40, 40], [40, 60], [10, 60]]},
        {"text": "아래", "polygon": [[10, 62], [40, 62], [40, 80], [10, 80]]},
    ]
    page.write_text(json.dumps({"page": 1, "lines": lines}), encoding="utf-8")
    with Image.new("RGB", (80, 100), "white") as image:
        image.save(page.with_suffix(".png"))
    candidate = retry_vl.retry_visual(page, 1, "PaddleOCR-VL-1.6", "cpu")
    assert candidate["bbox"] == [4, 39, 46, 61]


@pytest.mark.parametrize(
    "text,applied",
    [
        ("😀 앞문장\nac\n뒷문장", True),
        ("ac 와 ac", False),
        ("vacation", False),
        ("이미 수정한 문장", False),
    ],
)
def test_candidate_apply_requires_unique_match_and_supports_undo(
    tmp_path, text, applied
):
    """선택 후보만 유일한 구간에 반영하며 중복·수정본·영문 부분 단어와 이모지를 보존한다."""
    from PySide6.QtWidgets import QPlainTextEdit, QWidget

    app = QApplication.instance() or QApplication([])
    parent = QWidget()
    parent.editor = QPlainTextEdit(parent)
    parent.editor.setPlainText(text)
    page = tmp_path / "page-001.json"
    page.write_text(
        json.dumps(
            {
                "page": 1,
                "recognition_retry": [
                    {
                        "line_index": 0,
                        "original": "ac",
                        "candidates": [
                            {
                                "state": "completed",
                                "text": "“응?”",
                                "confidence": None,
                                "scale": 1,
                                "model": "PaddleOCR-VL-1.6",
                            }
                        ],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    before = page.read_bytes()
    dialog = RetryDialog(tmp_path, parent)
    dialog.apply_candidate()
    if applied:
        assert parent.editor.toPlainText() == text.replace("ac", "“응?”")
        parent.editor.undo()
    assert parent.editor.toPlainText() == text
    assert page.read_bytes() == before
    dialog.close()
    parent.close()
    app.processEvents()
