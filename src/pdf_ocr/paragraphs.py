"""Conservative single-column paragraph reconstruction from OCR geometry."""

import re
from itertools import pairwise
from statistics import median

from .text import remove_hanja_annotations

LIST_START = re.compile(r"^(?:[-*•●]\s|\d+[.)]\s)")
PARTICLES = {
    "에",
    "에서",
    "에게",
    "에게서",
    "으로",
    "로",
    "을",
    "를",
    "의",
    "은",
    "는",
    "와",
    "과",
    "도",
}


def join_lines(previous: str, following: str):
    """Return separator and uncertainty; do not rewrite any recognized character."""
    token = following.split()[0].rstrip(".,!?。！？")
    if previous.endswith(tuple(".!?。！？:;")):
        return " ", False
    if re.search(r"[가-힣]$", previous) and re.match(r"[가-힣]", following):
        if token in PARTICLES or (previous.endswith("이") and token == "다"):
            return "", False
        # Line geometry cannot establish a word boundary by itself.
        return " ", True
    if re.search(r"[A-Za-z]$", previous) and re.match(r"[A-Za-z]", following):
        return " ", True
    return " ", False


def restore_paragraphs(lines: list[dict], exclude_hanja: bool = True) -> dict:
    """OCR 줄 좌표로 단일 본문 문단을 복원하고 모호한 연결을 기록한다.

    Args:
        lines: text와 선택적 픽셀 polygon을 포함한 원시 줄 목록.
        exclude_hanja: 명확한 한국어 병기 한자를 최종 텍스트에서 제외할지 여부.

    Returns:
        text, paragraphs, reviews와 좌표 복원 여부 geometry_applied를 담은 사전.
        좌표가 없거나 영역이 겹치면 기존 줄 순서·형태를 보존한다.

    Raises:
        ValueError: 제공된 OCR 영역의 너비나 높이가 유효하지 않은 경우.
    """
    reviews = []
    entries = []
    for index, line in enumerate(lines):
        text = line["text"].strip()
        if exclude_hanja:
            text = remove_hanja_annotations(text)
        if not text:
            continue
        polygon = line.get("polygon")
        if not polygon:
            reviews.append({"line_index": index, "reason": "missing_geometry"})
            return {
                "text": "\n".join(
                    remove_hanja_annotations(x["text"]) if exclude_hanja else x["text"]
                    for x in lines
                ),
                "paragraphs": [],
                "reviews": reviews,
                "geometry_applied": False,
            }
        xs, ys = zip(*polygon, strict=True)
        entries.append(
            {
                "index": index,
                "text": text,
                "left": min(xs),
                "top": min(ys),
                "right": max(xs),
                "bottom": max(ys),
            }
        )
    if not entries:
        return {"text": "", "paragraphs": [], "reviews": [], "geometry_applied": False}
    original_entries = entries[:]
    entries.sort(key=lambda x: (x["top"], x["left"]))
    height = median(x["bottom"] - x["top"] for x in entries)
    if height <= 0:
        raise ValueError("OCR 영역의 높이가 올바르지 않습니다.")
    if any(x["bottom"] <= x["top"] or x["right"] <= x["left"] for x in entries):
        raise ValueError("OCR 영역의 크기가 올바르지 않습니다.")
    body = [
        x for x in entries if 0.85 * height <= x["bottom"] - x["top"] <= 1.3 * height
    ] or entries
    left = min(x["left"] for x in body)
    right = max(x["right"] for x in body)
    centers = [(x["top"] + x["bottom"]) / 2 for x in entries]
    pitches = [
        b - a for a, b in pairwise(centers) if height * 0.5 < b - a <= height * 2
    ]
    pitch = median(pitches) if pitches else height * 1.4
    if any(b - a < height * 0.5 for a, b in pairwise(centers)):
        return {
            "text": "\n".join(x["text"] for x in original_entries),
            "paragraphs": [],
            "reviews": [{"reason": "overlapping_rows_or_columns"}],
            "geometry_applied": False,
        }
    paragraphs = [{"text": entries[0]["text"], "line_indices": [entries[0]["index"]]}]
    for previous, current in pairwise(entries):
        previous_height = previous["bottom"] - previous["top"]
        current_height = current["bottom"] - current["top"]
        gap = (
            current["top"] + current["bottom"] - previous["top"] - previous["bottom"]
        ) / 2
        short_line = previous["right"] < left + 0.8 * (right - left)
        indented = current["left"] > left + height * 0.45
        style_change = (
            max(previous_height, current_height) / min(previous_height, current_height)
            > 1.3
        )
        boundary = (
            gap > pitch * 1.6
            or short_line
            or indented
            or style_change
            or LIST_START.match(current["text"])
            or LIST_START.match(previous["text"])
        )
        if boundary:
            paragraphs.append(
                {"text": current["text"], "line_indices": [current["index"]]}
            )
        else:
            separator, uncertain = join_lines(previous["text"], current["text"])
            paragraphs[-1]["text"] += separator + current["text"]
            paragraphs[-1]["line_indices"].append(current["index"])
            if uncertain:
                reviews.append(
                    {
                        "line_indices": [previous["index"], current["index"]],
                        "reason": "ambiguous_word_boundary",
                        "separator": separator,
                    }
                )
    return {
        "text": "\n\n".join(p["text"] for p in paragraphs),
        "paragraphs": paragraphs,
        "reviews": reviews,
        "geometry_applied": True,
    }
