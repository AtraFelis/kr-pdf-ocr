"""사용자 문서를 읽지 않고 고정 리비전의 한국어 교정 평가 모델을 받는다."""

import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPOSITORY = "Soyoung97/gec_kr"
REVISION = "c4a70d9f832fa25e4672aa4ba01c1d88f7787115"
os.environ["HF_HOME"] = str(ROOT / ".cache" / "huggingface")


def main():
    """공개 가중치·토크나이저를 models/gec_kr에 받고 출처와 미확인 라이선스를 기록한다."""
    from huggingface_hub import snapshot_download

    destination = ROOT / "models" / "gec_kr"
    snapshot_download(
        repo_id=REPOSITORY,
        revision=REVISION,
        local_dir=destination,
        token=False,
        allow_patterns=["*.json", "pytorch_model.bin", "README.md", "LICENSE*"],
    )
    (destination / "download-manifest.json").write_text(
        json.dumps(
            {
                "repository": REPOSITORY,
                "revision": REVISION,
                "license_status": "not_declared_in_model_card_or_file_list",
                "purpose": "local_evaluation_only; distribution_not_approved",
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"Downloaded {REPOSITORY} revision={REVISION}", flush=True)


if __name__ == "__main__":
    main()
