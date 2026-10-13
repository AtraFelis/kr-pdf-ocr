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
@pytest.mark.parametrize("threshold", [None, 0.01, 0.6, 1.0])
def test_detection_threshold_is_explicit_for_both_devices(
    paddle_engine, device, threshold
):
    """CPU·GPU에서 같은 검출 기준을 명시하고 제공된 인식 결과를 보존한다."""
    options = {} if threshold is None else {"det_box_thresh": threshold}
    engine = LocalPaddleEngine(paddle_engine, device, **options)
    expected = 0.5 if threshold is None else threshold
    assert engine.settings == {"text_det_box_thresh": expected}
    assert engine.engine.settings["text_det_box_thresh"] == expected
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


@pytest.mark.parametrize("threshold", [0, -0.1, 1.01, float("nan"), float("inf")])
def test_invalid_threshold_fails_before_model_load(tmp_path, threshold):
    """범위 밖·비유한 값을 모델 파일 확인이나 런타임 초기화 전에 거부한다."""
    with pytest.raises(ValueError, match="0.01~1.00"):
        LocalPaddleEngine(tmp_path, det_box_thresh=threshold)


@pytest.mark.parametrize("value", ["0", "-1", "1.1", "nan", "inf"])
def test_cli_invalid_threshold_does_not_create_output(tmp_path, monkeypatch, value):
    """CLI의 무효한 값을 PDF·모델 로딩과 출력 생성 전에 거부한다."""
    from pdf_ocr import cli

    output = tmp_path / "result"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "ocr",
            str(tmp_path / "missing.pdf"),
            "--det-box-thresh",
            value,
            "--output",
            str(output),
        ],
    )
    with pytest.raises(SystemExit) as error:
        cli.main()
    assert error.value.code == 2
    assert not output.exists()


@pytest.mark.parametrize("engine,format", [("vl16", "md"), ("qwen", "txt")])
def test_cli_rejects_threshold_for_other_engines(tmp_path, monkeypatch, engine, format):
    """미지원 모델의 검출 값은 조용히 무시하지 않고 출력 생성 전에 거부한다."""
    from pdf_ocr import cli

    output = tmp_path / "result"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "ocr",
            str(tmp_path / "missing.pdf"),
            "--det-box-thresh",
            "0.5",
            "--engine",
            engine,
            "--format",
            format,
            "--output",
            str(output),
        ],
    )
    with pytest.raises(SystemExit) as error:
        cli.main()
    assert error.value.code == 2
    assert not output.exists()
