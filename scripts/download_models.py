"""Download official inference weights; this script never reads user documents."""

import hashlib
import json
import tarfile
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASE = "https://paddle-model-ecology.bj.bcebos.com/paddlex/official_inference_model/paddle3.0.0/"
MODELS = ("PP-OCRv5_mobile_det", "korean_PP-OCRv5_mobile_rec")


def main():
    """공식 검출·한국어 모델을 로컬에 준비하고 출처와 받은 아카이브 해시를 기록한다."""
    destination = ROOT / "models"
    destination.mkdir(exist_ok=True)
    records = []
    for name in MODELS:
        archive = destination / f"{name}_infer.tar"
        url = BASE + archive.name
        target = destination / f"{name}_infer"
        if not target.exists():
            print(f"Downloading {name}", flush=True)
            urllib.request.urlretrieve(url, archive)
            with tarfile.open(archive) as bundle:
                bundle.extractall(destination, filter="data")
        if not (target / "inference.yml").is_file():
            raise RuntimeError(f"Missing model configuration: {target}")
        records.append(
            {
                "name": name,
                "source": url,
                "sha256_archive": hashlib.sha256(archive.read_bytes()).hexdigest(),
            }
        )
    (destination / "manifest.json").write_text(
        json.dumps(records, indent=2), encoding="utf-8"
    )


if __name__ == "__main__":
    main()
