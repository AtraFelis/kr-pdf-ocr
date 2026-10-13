"""평가용 KoGEC의 고정 가중치만 내려받으며 사용자 문서는 읽지 않는다."""

import argparse
import json
import os
from pathlib import Path

from pdf_ocr.kogec import REVISIONS

ROOT = Path(__file__).resolve().parents[1]
os.environ["HF_HOME"] = str(ROOT / ".cache/huggingface")


def main():
    """선택한 공개 모델과 출처·리비전·라이선스 확인 상태를 models에 저장한다."""
    from huggingface_hub import snapshot_download

    parser = argparse.ArgumentParser()
    parser.add_argument("--model", choices=REVISIONS, required=True)
    args = parser.parse_args()
    repository, revision = REVISIONS[args.model]
    destination = ROOT / "models" / repository.split("/")[-1]
    snapshot_download(
        repository,
        revision=revision,
        local_dir=destination,
        token=False,
        allow_patterns=["*.json", "*.bin", "*.model", "README.md", "LICENSE*"],
    )
    manifest = {
        "repository": repository,
        "revision": revision,
        "license_status": "cc-by-nc-4.0"
        if args.model == "3.3b"
        else "not_declared; NLLB base is noncommercial",
        "purpose": "local_evaluation_only; no_app_distribution",
    }
    (destination / "download-manifest.json").write_text(
        json.dumps(manifest, indent=2), encoding="utf-8"
    )
    print(f"Downloaded {repository} revision={revision}", flush=True)


if __name__ == "__main__":
    main()
