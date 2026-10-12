import os
from pathlib import Path

from .devices import resolve_device


class LocalPaddleEngine:
    def __init__(self, root: Path, device="cpu"):
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
