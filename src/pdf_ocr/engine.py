"""로컬 PP-OCRv5 모델로 줄별 글자·신뢰도·입력 이미지 좌표를 인식한다."""

import os
from pathlib import Path

from .devices import resolve_device


class LocalPaddleEngine:
    """공식 로컬 검출·한국어 인식 모델을 CPU 또는 GPU에서 실행한다."""

    def __init__(self, root: Path, device="cpu"):
        """모델 파일과 요청 장치를 확인하고 다운로드 없이 OCR 엔진을 초기화한다."""
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
