"""로컬 검출 설정 전달과 모델이 제공한 글자·신뢰도·좌표 보존을 검사한다."""

import sys
from types import SimpleNamespace

import numpy as np
import pytest
from PIL import Image

from pdf_ocr.engine import LocalPaddleEngine


@pytest.fixture
def paddle_engine(tmp_path, monkeypatch):
    """합성 모델 파일과 런타임 대역으로 실제 다운로드 없이 엔진을 생성한다."""
    for model in ("PP-OCRv5_mobile_det", "korean_PP-OCRv5_mobile_rec"):
        folder = tmp_path / "models" / f"{model}_infer"
        folder.mkdir(parents=True)
        for filename in ("inference.yml", "inference.json", "inference.pdiparams"):
            (folder / filename).touch()
    for name in ("PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK", "PADDLE_PDX_CACHE_HOME"):
        monkeypatch.setenv(name, "test")

    class PaddleOCR:
        """초기화 설정을 기록하고 합성 인식 결과를 반환하는 대역이다."""

        def __init__(self, **settings):
            """장치 및 검출 기준의 전달값을 기록한다."""
            self.settings = settings

        def predict(self, image):
            """글자와 모델 신뢰도를 임의 보정하지 않는지 확인할 결과를 반환한다."""
            assert image.shape == (20, 80, 3)
            yield {
                "rec_texts": ["“하하. 있지~.”"],
                "rec_scores": [0.79],
                "rec_polys": [np.array([[1, 2], [79, 2], [79, 18], [1, 18]])],
            }

    monkeypatch.setitem(
        sys.modules,
        "paddle",
        SimpleNamespace(
            is_compiled_with_cuda=lambda: True,
            device=SimpleNamespace(cuda=SimpleNamespace(device_count=lambda: 1)),
        ),
    )
    monkeypatch.setitem(sys.modules, "paddleocr", SimpleNamespace(PaddleOCR=PaddleOCR))
    return tmp_path


@pytest.mark.parametrize("device", ["cpu", "gpu"])
def test_detection_threshold_is_explicit_for_both_devices(paddle_engine, device):
    """CPU·GPU에서 같은 검출 기준을 명시하고 제공된 인식 결과를 보존한다."""
    engine = LocalPaddleEngine(paddle_engine, device)
    assert engine.settings == {"text_det_box_thresh": 0.5}
    assert engine.engine.settings["text_det_box_thresh"] == 0.5
    assert engine.device == ("cpu" if device == "cpu" else "gpu:0")
    with Image.new("RGB", (80, 20), "white") as image:
        lines = engine.recognize(image)
    assert lines == [
        {
            "text": "“하하. 있지~.”",
            "confidence": 0.79,
            "polygon": [[1, 2], [79, 2], [79, 18], [1, 18]],
        }
    ]


def test_retry_uses_same_detection_without_rewriting_text(paddle_engine):
    """단일 줄 재인식도 같은 엔진 설정과 원본 인식 신뢰도를 사용한다."""
    engine = LocalPaddleEngine(paddle_engine)
    with Image.new("RGB", (80, 20), "white") as image:
        assert engine.recognize_line(image) == {
            "text": "“하하. 있지~.”",
            "confidence": 0.79,
        }
