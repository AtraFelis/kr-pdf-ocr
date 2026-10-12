"""로컬 시각·언어 모델로 페이지 또는 검출 영역의 글자를 추출한다."""

import os
from pathlib import Path

from .devices import resolve_device


class LocalVLEngine:
    """Experimental page recognition; no invented line geometry or confidence."""

    def __init__(
        self,
        root: Path,
        line_regions: bool = False,
        model_name="PaddleOCR-VL-1.5",
        device="auto",
    ):
        """로컬 VLM·명시적 장치와 선택적 CPU 줄 검출기를 원격 코드 없이 초기화한다."""
        directory = root / "models" / model_name
        if not (directory / "config.json").is_file():
            raise FileNotFoundError(f"로컬 VLM이 없습니다: {directory}")
        os.environ["HF_HOME"] = str(root / ".cache" / "huggingface")
        os.environ["HF_HUB_OFFLINE"] = "1"
        os.environ["TRANSFORMERS_OFFLINE"] = "1"
        import torch
        from transformers import AutoModelForImageTextToText, AutoProcessor

        self.torch = torch
        self.prompt = (
            "OCR:"
            if model_name.startswith("PaddleOCR-VL-")
            else "이미지에 보이는 모든 글자를 읽기 순서대로 그대로 옮겨 적어 주세요. "
            "띄어쓰기와 문단을 보존하고, 설명이나 요약을 추가하지 마세요. "
            "보이지 않는 내용을 추측하지 마세요."
        )
        selected = resolve_device(device, device != "cpu" and torch.cuda.is_available())
        self.device = "cuda" if selected == "gpu" else "cpu"
        self.model = (
            AutoModelForImageTextToText.from_pretrained(
                directory,
                local_files_only=True,
                trust_remote_code=False,
                dtype=torch.bfloat16 if self.device == "cuda" else torch.float32,
                attn_implementation="sdpa",
            )
            .to(self.device)
            .eval()
        )
        self.processor = AutoProcessor.from_pretrained(
            directory, local_files_only=True, trust_remote_code=False
        )
        self.detector = None
        if line_regions:
            from .engine import LocalPaddleEngine

            self.detector = LocalPaddleEngine(root)

    def recognize(self, image):
        """페이지 전체 또는 실제 검출 영역별 텍스트를 읽고 제공되지 않은 신뢰도는 비운다."""
        if self.detector is None:
            return [self.recognize_region(image, 2048)]
        results = []
        for region in self.detector.recognize(image):
            points = region["polygon"]
            box = (
                max(0, int(min(p[0] for p in points)) - 8),
                max(0, int(min(p[1] for p in points)) - 8),
                min(image.width, int(max(p[0] for p in points)) + 8),
                min(image.height, int(max(p[1] for p in points)) + 8),
            )
            crop = image.crop(box)
            try:
                recognized = self.recognize_region(crop, 256)
                recognized["polygon"] = points
                recognized["scope"] = "detected_region"
                results.append(recognized)
            finally:
                crop.close()
        return results

    def recognize_region(self, image, token_limit):
        """입력 이미지에서 토큰 상한 내 텍스트를 생성하고 좌표·신뢰도 없이 검토 대상으로 반환한다."""
        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "image", "image": image.convert("RGB")},
                    {"type": "text", "text": self.prompt},
                ],
            }
        ]
        inputs = self.processor.apply_chat_template(
            messages,
            add_generation_prompt=True,
            tokenize=True,
            return_dict=True,
            return_tensors="pt",
            processor_kwargs={
                "images_kwargs": {
                    "size": {
                        "shortest_edge": self.processor.image_processor.size[
                            "shortest_edge"
                        ],
                        "longest_edge": 1280 * 28 * 28,
                    }
                }
            },
        ).to(self.device)
        with self.torch.inference_mode():
            outputs = self.model.generate(
                **inputs, max_new_tokens=token_limit, do_sample=False, use_cache=True
            )
        tokens = outputs[0][inputs["input_ids"].shape[-1] :]
        text = self.processor.decode(tokens, skip_special_tokens=True)
        return {
            "text": text,
            "confidence": None,
            "polygon": None,
            "scope": "page",
            "requires_review": True,
            "token_limit_reached": len(tokens) >= token_limit,
        }
