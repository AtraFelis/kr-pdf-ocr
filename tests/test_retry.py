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
