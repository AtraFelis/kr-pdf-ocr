"""구조 분석용 공식 배치 모델을 고정 리비전으로 다운로드하며 문서는 읽지 않는다."""

import json
from pathlib import Path

from huggingface_hub import HfApi, snapshot_download

ROOT = Path(__file__).resolve().parents[1]


def main():
    """VL 1.6 인식 모델과 PP-DocLayoutV3 배치 모델을 로컬에 준비한다."""
    for name in ("PP-DocLayoutV3", "PaddleOCR-VL-1.6"):
        repo = f"PaddlePaddle/{name}"
        revision = HfApi(token=False).model_info(repo).sha
        target = ROOT / "models" / name
        snapshot_download(
            repo,
            revision=revision,
            local_dir=target,
            token=False,
            allow_patterns=[
                "*.json",
                "*.yml",
                "*.pdiparams",
                "*.safetensors",
                "*.model",
                "*.txt",
                "*.jinja",
                "README.md",
                "LICENSE*",
            ],
        )
        (target / "download-manifest.json").write_text(
            json.dumps({"repository": repo, "revision": revision}, indent=2),
            encoding="utf-8",
        )
        print(f"Downloaded {repo} revision={revision}", flush=True)


if __name__ == "__main__":
    main()
