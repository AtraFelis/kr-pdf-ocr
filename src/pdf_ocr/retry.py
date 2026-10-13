"""짧거나 불확실한 OCR 줄의 이미지 재인식 후보를 원시 결과와 분리해 보존한다."""

import math
import re
from pathlib import Path

from PIL import Image


def retry_reason(line: dict) -> str | None:
    """짧은 줄·낮은 모델 점수·종결 표현의 부호 누락 가능성을 후보 선정에만 사용한다."""
    compact = re.sub(r"\s", "", line["text"])
    if not compact:
        return None
    if len(compact) <= 6:
        return "short_text"
    score = line.get("confidence")
    if score is not None and math.isfinite(score) and score < 0.88:
        return "low_score"
    if compact.endswith(("다", "요", "죠", "까", "니")):
        return "possible_missing_punctuation"
    return None


def retry_lines(image, lines: list[dict], engine, folder: Path, page: int, limit=24):
    """여백·배율 두 조건으로 후보를 생성하며 원문을 교체하거나 점수로 자동 채택하지 않는다.

    좌표는 선택 입력 이미지 기준이다. 줄별 실패를 기록하며 성공한 후보와 원시
    결과는 유지한다. 확대는 재표본화이며 원본에 없던 영상 정보를 생성하지 않는다.
    """
    records = []
    for index, line in enumerate(lines):
        reason = retry_reason(line)
        if reason is None or not line.get("polygon"):
            continue
        if len(records) >= limit:
            break
        xs, ys = zip(*line["polygon"], strict=True)
        height = max(ys) - min(ys)
        if height <= 0 or max(xs) <= min(xs):
            continue
        record = {
            "line_index": index,
            "original": line["text"],
            "reason": reason,
            "candidates": [],
        }
        records.append(record)
        for scale, margin in ((2, 0.1), (3, 0.25)):
            padding = max(2, round(height * margin))
            box = [
                max(0, math.floor(min(xs)) - padding),
                max(0, math.floor(min(ys)) - padding),
                min(image.width, math.ceil(max(xs)) + padding),
                min(image.height, math.ceil(max(ys)) + padding),
            ]
            candidate = {"scale": scale, "padding": padding, "bbox_in_input": box}
            record["candidates"].append(candidate)
            try:
                if box[2] <= box[0] or box[3] <= box[1]:
                    raise ValueError("재인식 영역이 입력 이미지 밖입니다.")
                with (
                    image.crop(box) as crop,
                    crop.resize(
                        (crop.width * scale, crop.height * scale),
                        Image.Resampling.LANCZOS,
                    ) as enlarged,
                ):
                    name = f"retry/page-{page:03}-line-{index:03}-{scale}.png"
                    (folder / "retry").mkdir(exist_ok=True)
                    enlarged.save(folder / name)
                    candidate["image"] = name
                    candidate.update(engine.recognize_line(enlarged))
                candidate["state"] = "completed"
            except (OSError, ValueError, RuntimeError) as error:
                candidate.update(state="failed", error=str(error))
    return records
