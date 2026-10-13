"""별도 프로세스에서 선택 줄의 원본 이미지를 로컬 VLM으로 재인식한다."""

import argparse
import json
import math
import os
import socket
from pathlib import Path
from uuid import uuid4

from PIL import Image

from .vl_engine import LocalVLEngine

ROOT = Path(__file__).resolve().parents[2]


def deny_connection(*args, **kwargs):
    """문서 재인식 중 외부 소켓 연결을 차단한다."""
    raise RuntimeError("로컬 재인식 중 네트워크 연결은 차단됩니다.")


def retry_visual(page_path: Path, index: int, model: str, device: str):
    """원본 선택 영역 안에서 줄을 다시 읽고 원시 결과를 유지하며 후보만 추가한다.

    이미지·페이지/줄 대응을 검사하고 VLM의 신뢰도를 임의로 생성하지 않는다.
    성공 뒤 페이지 JSON을 원자적으로 교체하며 실패 시 기존 JSON을 유지한다.
    """
    record = json.loads(page_path.read_text(encoding="utf-8"))
    if not 0 <= index < len(record["lines"]):
        raise ValueError("재인식 줄 번호를 확인하세요.")
    line = record["lines"][index]
    if not line.get("polygon"):
        raise ValueError("선택 줄의 원본 좌표가 없습니다.")
    xs, ys = zip(*line["polygon"], strict=True)
    height = max(ys) - min(ys)
    if height <= 0 or max(xs) <= min(xs):
        raise ValueError("선택 줄의 원본 좌표 크기를 확인하세요.")
    padding = max(2, round(height * 0.3))
    folder = page_path.parent
    image_path = page_path.with_suffix(".png")
    with Image.open(image_path) as image:
        bounds = record.get("region_pixel_box", [0, 0, image.width, image.height])
        box = [
            max(0, bounds[0], math.floor(min(xs)) - padding),
            max(0, bounds[1], math.floor(min(ys)) - padding),
            min(image.width, bounds[2], math.ceil(max(xs)) + padding),
            min(image.height, bounds[3], math.ceil(max(ys)) + padding),
        ]
        for other_index, other in enumerate(record["lines"]):
            if other_index == index or not other.get("polygon"):
                continue
            other_x, other_y = zip(*other["polygon"], strict=True)
            if max(other_x) < min(xs) or min(other_x) > max(xs):
                continue
            if max(other_y) <= min(ys):
                box[1] = max(box[1], math.ceil(max(other_y)) + 1)
            elif min(other_y) >= max(ys):
                box[3] = min(box[3], math.floor(min(other_y)) - 1)
        if box[2] <= box[0] or box[3] <= box[1]:
            raise ValueError("선택 영역 안에 재인식할 글자가 없습니다.")
        with image.crop(box) as crop:
            engine = LocalVLEngine(ROOT, model_name=model, device=device)
            recognized = engine.recognize_region(crop, 256)
            if recognized["token_limit_reached"] or not recognized["text"].strip():
                raise ValueError(
                    "재인식 결과가 비었거나 중간에 잘렸습니다. 원문을 확인하세요."
                )
            name = (
                f"retry/page-{record['page']:03}-line-{index:03}-{uuid4().hex[:12]}.png"
            )
            (folder / "retry").mkdir(exist_ok=True)
            crop.save(folder / name)
    candidate = {
        "state": "completed",
        "model": model,
        "scale": 1,
        "padding": padding,
        "bbox": box,
        "bbox_in_input": [
            box[0] - bounds[0],
            box[1] - bounds[1],
            box[2] - bounds[0],
            box[3] - bounds[1],
        ],
        "image": name,
        "text": recognized["text"],
        "confidence": None,
        "requires_review": True,
    }
    retries = record.setdefault("recognition_retry", [])
    target = next((item for item in retries if item["line_index"] == index), None)
    if target is None:
        target = {
            "line_index": index,
            "original": line["text"],
            "reason": "manual_visual_retry",
            "candidates": [],
        }
        retries.append(target)
    target["candidates"].append(candidate)
    temporary = folder / f".{page_path.stem}-{uuid4().hex}.tmp"
    try:
        temporary.write_text(
            json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        os.replace(temporary, page_path)
    finally:
        temporary.unlink(missing_ok=True)
    return candidate


def main():
    """CLI 인자를 검증하고 원본 줄을 별도 로컬 VLM 프로세스에서 다시 읽는다."""
    parser = argparse.ArgumentParser()
    parser.add_argument("page", type=Path)
    parser.add_argument("line", type=int)
    parser.add_argument(
        "--model",
        choices=("PaddleOCR-VL-1.6", "Qwen3-VL-2B-Instruct"),
        default="PaddleOCR-VL-1.6",
    )
    parser.add_argument("--device", choices=("cpu", "gpu"), default="cpu")
    args = parser.parse_args()
    socket.socket.connect = deny_connection
    socket.socket.connect_ex = deny_connection
    candidate = retry_visual(args.page, args.line, args.model, args.device)
    print(json.dumps(candidate, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
