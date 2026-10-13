"""로컬 교정 모델의 평가 전용 실행으로 원문을 보존한 후보를 생성한다."""

import json
import os
from pathlib import Path


class LocalGEC:
    """사용자 채택이나 자동 저장 없이 gec_kr 후보와 실패를 반환한다."""

    def __init__(self, directory: Path, device: str):
        """로컬 고정 모델을 명시적인 CPU/GPU 장치의 FP32로 로드한다.

        Args:
            directory: 다운로드 기록·가중치·토크나이저가 든 로컬 폴더.
            device: cpu 또는 gpu. GPU 불가 시 오류를 내며 자동 전환하지 않는다.

        Raises:
            ValueError: 모델 출처·리비전 또는 장치가 평가 대상과 다른 경우.
            FileNotFoundError: 필수 모델 파일이 없는 경우.
        """
        os.environ["HF_HUB_OFFLINE"] = "1"
        os.environ["TRANSFORMERS_OFFLINE"] = "1"
        import torch
        from transformers import BartForConditionalGeneration, PreTrainedTokenizerFast

        manifest = json.loads(
            (directory / "download-manifest.json").read_text(encoding="utf-8")
        )
        if (
            manifest.get("repository") != "Soyoung97/gec_kr"
            or manifest.get("revision") != "c4a70d9f832fa25e4672aa4ba01c1d88f7787115"
        ):
            raise ValueError("평가용 gec_kr 출처·리비전이 일치하지 않습니다.")
        if device not in {"cpu", "gpu"}:
            raise ValueError("cpu 또는 gpu를 지정하세요.")
        if device == "gpu" and not torch.cuda.is_available():
            raise ValueError("CUDA GPU를 사용할 수 없습니다. CPU를 명시해 실행하세요.")
        self.torch = torch
        self.device = "cuda" if device == "gpu" else "cpu"
        self.manifest = manifest
        self.tokenizer = PreTrainedTokenizerFast.from_pretrained(
            directory, local_files_only=True
        )
        self.model = (
            BartForConditionalGeneration.from_pretrained(
                directory, local_files_only=True, weights_only=True, dtype=torch.float32
            )
            .to(self.device)
            .eval()
        )

    def suggest(self, text: str) -> dict:
        """공식 예제의 BOS/EOS·빔 탐색 조건으로 후보를 만들고 잘림·빈 출력은 거부한다.

        입력은 한 문장이다. 원문은 변경하지 않으며 128 토큰 출력 상한에
        닿으면 강제 EOS가 있더라도 성공으로 표시하지 않는다. 긴 입력을 자르지 않는다.
        """
        ids = self.tokenizer.encode(text, add_special_tokens=False)
        ids = [self.tokenizer.bos_token_id, *ids, self.tokenizer.eos_token_id]
        if not text.strip() or len(ids) > self.model.config.max_position_embeddings:
            return {"candidate": None, "failure": "empty_or_overlong_input"}
        tensor = self.torch.tensor([ids], device=self.device)
        with self.torch.inference_mode():
            result = self.model.generate(
                tensor,
                attention_mask=self.torch.ones_like(tensor),
                max_length=128,
                eos_token_id=1,
                num_beams=4,
                early_stopping=True,
                repetition_penalty=2.0,
                do_sample=False,
            )
        output_ids = result[0].tolist()
        decoded = self.tokenizer.decode(output_ids, skip_special_tokens=True).strip()
        if len(output_ids) >= 128 or not decoded:
            return {"candidate": None, "failure": "token_limit_or_empty_output"}
        return {"candidate": decoded, "failure": None}
