"""로컬 PP-OCRv5 모델로 줄별 글자·신뢰도·입력 이미지 좌표를 인식한다."""

import math
import os
from pathlib import Path

from .devices import resolve_device

DEFAULT_DET_BOX_THRESH = 0.5


def validate_detection_threshold(value: float) -> float:
    """프로그램의 검출 기준 범위 0.01~1.00 안의 유한한 실수만 반환한다."""
    if not math.isfinite(value) or not 0.01 <= value <= 1.0:
        raise ValueError("글자 영역 검출 기준은 0.01~1.00 사이의 유한한 수여야 합니다.")
    return value


class LocalPaddleEngine:
    """공식 로컬 검출·한국어 인식 모델을 CPU 또는 GPU에서 실행한다."""

    def __init__(self, root: Path, device="cpu", det_box_thresh=DEFAULT_DET_BOX_THRESH):
        """모델·장치를 확인하고 지정한 검출 영역 점수 기준으로 엔진을 초기화한다.

        settings는 실제 초기화에 전달한 검출 설정이며 실행 기록에 저장한다.
        인식 신뢰도는 모델의 반환값을 유지하고 문서 처리 중 다운로드하지 않는다.
        검출 기준은 0.01~1.00이며 잘못된 값은 모델 로딩 전에 ValueError로 거부한다.
        """
        det_box_thresh = validate_detection_threshold(det_box_thresh)
        for name in ("PP-OCRv5_mobile_det", "korean_PP-OCRv5_mobile_rec"):
            for filename in ("inference.yml", "inference.json", "inference.pdiparams"):
                path = root / "models" / f"{name}_infer" / filename
                if not path.is_file():
                    raise FileNotFoundError(f"로컬 모델 파일이 없습니다: {path}")
        # Local directories avoid implicit model downloads during document processing.
        os.environ["PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK"] = "True"
        os.environ["PADDLE_PDX_CACHE_HOME"] = str(root / ".cache" / "paddlex")
        import paddle
        from paddleocr import PaddleOCR

        # GPU-enabled Paddle also supports CPU; the CPU wheel cannot run CUDA.
        available = device != "cpu" and paddle.is_compiled_with_cuda()
        if available:
            available = paddle.device.cuda.device_count() > 0
        selected = resolve_device(device, available)
        self.device = "gpu:0" if selected == "gpu" else "cpu"
        # 검출 영역의 평균 점수 기준이다. 인식 신뢰도와는 별개의 값이며,
        # 0.6에서 누락된 대사를 0.5에서 보존하는 샘플을 확인했다.
        self.settings = {"text_det_box_thresh": det_box_thresh}
        self.engine = PaddleOCR(
            text_detection_model_name="PP-OCRv5_mobile_det",
            text_detection_model_dir=str(root / "models" / "PP-OCRv5_mobile_det_infer"),
            text_recognition_model_name="korean_PP-OCRv5_mobile_rec",
            text_recognition_model_dir=str(
                root / "models" / "korean_PP-OCRv5_mobile_rec_infer"
            ),
            use_doc_orientation_classify=False,
            use_doc_unwarping=False,
            use_textline_orientation=False,
            device=self.device,
            enable_mkldnn=False,
            cpu_threads=8,
            **self.settings,
        )

    def recognize(self, image):
        """입력 PIL 이미지의 줄별 텍스트·모델 신뢰도·픽셀 다각형을 반환한다."""
        import numpy as np

        result = next(
            iter(self.engine.predict(np.asarray(image.convert("RGB"))[:, :, ::-1]))
        )
        return [
            {"text": text, "confidence": float(score), "polygon": polygon.tolist()}
            for text, score, polygon in zip(
                result["rec_texts"],
                result["rec_scores"],
                result["rec_polys"],
                strict=True,
            )
        ]

    def recognize_line(self, image):
        """기존 로컬 검출·인식기로 다시 읽고 단일 줄 결과만 후보로 반환한다."""
        lines = self.recognize(image)
        if len(lines) != 1:
            raise ValueError(
                "재인식에서 단일 줄을 찾지 못했습니다. 원본 영역을 확인하세요."
            )
        return {"text": lines[0]["text"], "confidence": lines[0]["confidence"]}
