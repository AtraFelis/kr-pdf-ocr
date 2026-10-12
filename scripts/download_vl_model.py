"""Download a pinned official VLM snapshot without reading any user document."""

import argparse
import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
os.environ["HF_HOME"] = str(ROOT / ".cache" / "huggingface")

from huggingface_hub import HfApi, snapshot_download


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--model", choices=("paddle", "paddle16", "qwen"), default="paddle"
    )
    args = parser.parse_args()
    repo = {
        "paddle": "PaddlePaddle/PaddleOCR-VL-1.5",
        "paddle16": "PaddlePaddle/PaddleOCR-VL-1.6",
        "qwen": "Qwen/Qwen3-VL-2B-Instruct",
    }[args.model]
    revision = HfApi(token=False).model_info(repo).sha
    destination = ROOT / "models" / repo.split("/")[-1]
    snapshot_download(
        repo_id=repo,
        revision=revision,
        local_dir=destination,
        token=False,
        allow_patterns=[
            "*.json",
            "*.safetensors",
            "*.txt",
            "*.model",
            "*.jinja",
            "README.md",
            "LICENSE*",
        ],
    )
    (destination / "download-manifest.json").write_text(
        json.dumps({"repository": repo, "revision": revision}, indent=2),
        encoding="utf-8",
    )
    print(f"Downloaded {repo} revision={revision}", flush=True)


if __name__ == "__main__":
    main()
