import os
from pathlib import Path


class LocalVLEngine:
    """Experimental page recognition; no invented line geometry or confidence."""

    def __init__(
        self, root: Path, line_regions: bool = False, model_name="PaddleOCR-VL-1.5"
    ):
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
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
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
