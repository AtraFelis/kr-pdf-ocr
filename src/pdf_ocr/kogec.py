"""공개 KoGEC 파일의 토큰 정합성을 검사하고 명시적인 진단 후보만 생성한다."""

import json
import os
from pathlib import Path

REVISIONS = {
    "600m": (
        "sionic-ai/nllb-200-ko-gec-600M",
        "a85a3e39efbcbf647866f681e74140fd293b9338",
    ),
    "3.3b": (
        "sionic-ai/nllb-200-ko-gec-3.3B",
        "413b34e43ffe8c7c5c431d9eb843e7102b0c994d",
    ),
}


class KoGECProbe:
    """논문 방식의 재현 가능성과 한국어→한국어 진단 실행을 구분한다."""

    def __init__(self, root: Path, size: str, diagnostic: bool):
        """고정 파일을 검사하며 설정이 불완전하면 명시적인 진단 모드만 허용한다."""
        os.environ["HF_HUB_OFFLINE"] = "1"
        os.environ["TRANSFORMERS_OFFLINE"] = "1"
        import torch
        from transformers import AutoTokenizer, M2M100ForConditionalGeneration

        repository, revision = REVISIONS[size]
        directory = root / "models" / repository.split("/")[-1]
        manifest = json.loads(
            (directory / "download-manifest.json").read_text(encoding="utf-8")
        )
        if (
            manifest.get("repository") != repository
            or manifest.get("revision") != revision
        ):
            raise ValueError("KoGEC 평가 모델 출처·리비전이 일치하지 않습니다.")
        config = json.loads((directory / "config.json").read_text(encoding="utf-8"))
        self.tokenizer = AutoTokenizer.from_pretrained(
            directory, local_files_only=True, trust_remote_code=False
        )
        vocabulary = self.tokenizer.get_vocab()
        self.audit = {
            "model": manifest,
            "model_vocabulary_size": config["vocab_size"],
            "tokenizer_vocabulary_size": len(self.tokenizer),
            "source_token": vocabulary.get("kor_Hang"),
            "paper_target_token": vocabulary.get("cor_Hang"),
            "other_documented_spellings": {
                name: vocabulary.get(name)
                for name in (
                    "<cor_Hang>",
                    "ko_Hang",
                    "co_Hang",
                    "<ko_Hang>",
                    "<co_Hang>",
                )
            },
            "verified_paper_inference": False,
        }
        if not diagnostic:
            raise ValueError(
                "교정 토큰 매핑을 확인하지 못했습니다. 논문 방식의 성능 평가를 보류하세요. --diagnostic-only만 실행할 수 있습니다."
            )
        if self.audit["source_token"] is None:
            raise ValueError("진단용 한국어 토큰도 없습니다.")
        if not torch.cuda.is_available():
            raise ValueError("이 진단은 명시적인 CUDA GPU가 필요합니다.")
        self.torch = torch
        self.tokenizer.src_lang = "kor_Hang"
        self.dtype = torch.float16 if size == "3.3b" else torch.float32
        self.model, loading = M2M100ForConditionalGeneration.from_pretrained(
            directory,
            local_files_only=True,
            trust_remote_code=False,
            weights_only=True,
            dtype=self.dtype,
            output_loading_info=True,
        )
        if any(
            loading.get(name)
            for name in (
                "missing_keys",
                "unexpected_keys",
                "mismatched_keys",
                "error_msgs",
            )
        ):
            raise ValueError("KoGEC 가중치 로드가 불완전합니다.")
        self.model = self.model.to("cuda").eval()
        self.audit["loading_complete"] = True
        self.audit["diagnostic_condition"] = (
            "kor_Hang to kor_Hang; not paper correction token"
        )

    def suggest(self, text: str) -> dict:
        """한국어→한국어 조건의 진단 결과만 반환하며 미매핑 토큰·빈 출력·잘림은 거부한다."""
        inputs = self.tokenizer(text, return_tensors="pt", truncation=False)
        if not text.strip() or inputs["input_ids"].shape[-1] > 128:
            return {"candidate": None, "failure": "empty_or_overlong_input"}
        with self.torch.inference_mode():
            result = self.model.generate(
                **inputs.to("cuda"),
                forced_bos_token_id=self.audit["source_token"],
                num_beams=4,
                max_new_tokens=128,
                max_length=None,
                do_sample=False,
            )
        ids = result[0].tolist()
        unknown = [token for token in ids if token >= len(self.tokenizer)]
        details = {"generated_tokens": len(ids), "unmapped_token_ids": unknown}
        if (
            unknown
            or len(ids) >= 129
            or not ids
            or ids[-1] != self.model.config.eos_token_id
        ):
            return {
                "candidate": None,
                "failure": "unmapped_token_or_truncated_output",
                **details,
            }
        # Transformers versions differ in registering NLLB language tokens as special.
        decoded = self.tokenizer.decode(
            [token for token in ids if token != self.audit["source_token"]],
            skip_special_tokens=True,
            clean_up_tokenization_spaces=False,
        ).strip()
        return {
            "candidate": decoded or None,
            "failure": None if decoded else "empty_output",
            **details,
        }
