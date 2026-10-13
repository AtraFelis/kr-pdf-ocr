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


def attach_closing_punctuation(entries: list[dict]) -> tuple[list[dict], list[dict]]:
    """같은 줄 오른쪽에 분리된 작은 닫는 문장부호를 유일한 본문 줄에 연결한다.

    문장부호를 생성·교체하지 않는다. 높이·너비·오른쪽 경계·중심 높이가
    가까운 본문 후보가 하나일 때만 연결하며 입력과 원시 좌표는 변경하지 않는다.
    연결한 줄의 모든 원본 인덱스를 보존하고 모호한 배치는 그대로 반환한다.
    """
    closing = re.compile(r"^[\"'”’」』)\]}.,!?…。，！？]+$")
    fragments = [entry for entry in entries if closing.fullmatch(entry["text"])]
    hosts = [entry for entry in entries if not closing.fullmatch(entry["text"])]
    attachments = {}
    reviews = []
    for fragment in fragments:
        candidates = []
        for host in hosts:
            height = host["bottom"] - host["top"]
            center = (fragment["top"] + fragment["bottom"]) / 2
            if (
                fragment["bottom"] - fragment["top"] <= height * 0.6
                and fragment["right"] - fragment["left"] <= height * 0.75
                and host["top"] <= center <= host["bottom"]
                and host["right"] - height * 0.25
                <= fragment["left"]
                <= host["right"] + height * 0.6
                and fragment["right"] >= host["right"]
            ):
                candidates.append(host)
        if len(candidates) == 1:
            attachments.setdefault(candidates[0]["index"], []).append(fragment)
    attached = {f["index"] for group in attachments.values() for f in group}
    result = []
    for entry in entries:
        if entry["index"] in attached:
            continue
        suffixes = sorted(attachments.get(entry["index"], []), key=lambda x: x["left"])
        if not suffixes:
            result.append(entry)
            continue
        group = [entry, *suffixes]
        indices = [item["index"] for item in group]
        result.append(
            {
                **entry,
                "text": "".join(item["text"] for item in group),
                "line_indices": indices,
                "left": min(item["left"] for item in group),
                "right": max(item["right"] for item in group),
                "top": min(item["top"] for item in group),
                "bottom": max(item["bottom"] for item in group),
            }
        )
        reviews.append(
            {"reason": "attached_closing_punctuation", "line_indices": indices}
        )
    return result, reviews


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


def restore_paragraphs(
    lines: list[dict], exclude_hanja: bool = True, allow_partial: bool = True
) -> dict:
    """OCR 줄 좌표로 단일 본문 문단을 복원하고 모호한 연결을 기록한다.

    Args:
        lines: text와 선택적 픽셀 polygon을 포함한 원시 줄 목록.
        exclude_hanja: 명확한 한국어 병기 한자를 최종 텍스트에서 제외할지 여부.
        allow_partial: 드문 겹침 영역을 보존하고 정상 구간만 복원할지 여부.

    Returns:
        text, paragraphs, reviews와 좌표 복원 여부 geometry_applied를 담은 사전.
        같은 줄 끝의 작은 닫는 문장부호만 연결한 뒤 좌표를 검사한다.
        좌표 누락·광범위한 겹침은 기존 순서·형태를 보존한다.
        드문 겹침은 모호한 블록을 그대로 두고 정상 구간만 부분 복원한다.

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
                "line_indices": [index],
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
    if any(x["bottom"] <= x["top"] or x["right"] <= x["left"] for x in entries):
        raise ValueError("OCR 영역의 크기가 올바르지 않습니다.")
    entries, attachments = attach_closing_punctuation(entries)
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
    overlaps = {
        position
        for i, (a, b) in enumerate(pairwise(centers))
        if b - a < height * 0.5
        for position in (i, i + 1)
    }
    if overlaps:
        if (
            allow_partial
            and len(overlaps) <= 4
            and len(overlaps) / len(entries) <= 0.25
        ):
            return restore_partial(lines, entries, overlaps, exclude_hanja)
        return {
            "text": "\n".join(x["text"] for x in original_entries),
            "paragraphs": [],
            "reviews": [{"reason": "overlapping_rows_or_columns"}],
            "geometry_applied": False,
        }
    reviews.extend(attachments)
    paragraphs = [
        {"text": entries[0]["text"], "line_indices": entries[0]["line_indices"][:]}
    ]
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
                {"text": current["text"], "line_indices": current["line_indices"][:]}
            )
        else:
            separator, uncertain = join_lines(previous["text"], current["text"])
            paragraphs[-1]["text"] += separator + current["text"]
            paragraphs[-1]["line_indices"].extend(current["line_indices"])
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


def restore_partial(
    lines: list[dict], entries: list[dict], overlaps: set[int], exclude_hanja: bool
) -> dict:
    """드문 겹침 블록은 원문 줄로 보존하고 나머지 연속 구간만 좌표 복원한다.

    raw lines·좌표·글자는 변경하지 않는다. 정상 구간의 로컬 줄 인덱스를
    원래 페이지 인덱스로 매핑하고 겹침 문단은 Kiwi 적용 제외로 표시한다.
    다단처럼 겹침이 많으면 호출하지 않으며 누락 좌표는 기존 보존 정책을 따른다.
    """
    groups = []
    for position, entry in enumerate(entries):
        ambiguous = position in overlaps
        if not groups or groups[-1][0] != ambiguous:
            groups.append((ambiguous, []))
        groups[-1][1].extend(entry["line_indices"])
    paragraphs, reviews = [], []
    for ambiguous, original_indices in groups:
        indices = sorted(set(original_indices))
        if ambiguous:
            texts = [
                remove_hanja_annotations(lines[i]["text"].strip())
                if exclude_hanja
                else lines[i]["text"].strip()
                for i in indices
            ]
            paragraphs.append(
                {
                    "text": "\n".join(texts),
                    "line_indices": indices,
                    "geometry_applied": False,
                }
            )
            reviews.append(
                {"reason": "overlapping_region_preserved", "line_indices": indices}
            )
            continue
        restored = restore_paragraphs(
            [lines[i] for i in indices], exclude_hanja, allow_partial=False
        )
        if not restored["geometry_applied"]:
            paragraphs.append(
                {
                    "text": restored["text"],
                    "line_indices": indices,
                    "geometry_applied": False,
                }
            )
        else:
            paragraphs.extend(
                {
                    **paragraph,
                    "line_indices": [indices[i] for i in paragraph["line_indices"]],
                    "geometry_applied": True,
                }
                for paragraph in restored["paragraphs"]
            )
        for review in restored["reviews"]:
            mapped = dict(review)
            if "line_index" in mapped:
                mapped["line_index"] = indices[mapped["line_index"]]
            if "line_indices" in mapped:
                mapped["line_indices"] = [indices[i] for i in mapped["line_indices"]]
            reviews.append(mapped)
    applied = any(paragraph.get("geometry_applied") for paragraph in paragraphs)
    return {
        "text": "\n\n".join(p["text"] for p in paragraphs),
        "paragraphs": paragraphs,
        "reviews": reviews,
        "geometry_applied": applied,
        "partial_geometry_applied": applied,
    }
