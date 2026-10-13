"""원시 페이지를 보존하며 연속 페이지의 단일 본문 문단만 선택적으로 연결한다."""

import json
import math
import re
from pathlib import Path
from statistics import median

from .paragraphs import LIST_START, join_lines


def bounds(line: dict) -> tuple[float, float, float, float]:
    """전체 페이지 픽셀 polygon의 왼쪽·위·오른쪽·아래 경계를 반환한다."""
    points = line["polygon"]
    if len(points) < 3 or any(
        len(point) != 2 or any(not math.isfinite(value) for value in point)
        for point in points
    ):
        raise ValueError("유효한 OCR polygon이 필요합니다.")
    return (
        min(p[0] for p in points),
        min(p[1] for p in points),
        max(p[0] for p in points),
        max(p[1] for p in points),
    )


def boundary_reason(previous: dict, following: dict) -> str | None:
    """페이지 경계를 연결할 근거가 부족하면 보존 이유를 반환한다.

    1 기반 연속 페이지·단일 본문 복원·같은 상대 영역을 요구한다.
    본문 마지막 줄이 짧거나 다음 줄이 들여쓰기/목록/다른 글자 크기이면
    새 문단으로 보존한다. 머리말·쪽번호를 추측 삭제하지 않는다.
    """
    if following["page"] != previous["page"] + 1:
        return "nonconsecutive_pages"
    for record in (previous, following):
        restored = record.get("restoration") or {}
        if restored.get("partial_geometry_applied"):
            return "partial_geometry_requires_review"
        if not restored.get("geometry_applied") or not restored.get("paragraphs"):
            return "missing_or_ambiguous_geometry"
        if any(
            not isinstance(record.get(key), (float, int))
            or not math.isfinite(record[key])
            or record[key] <= 0
            for key in ("width", "height")
        ):
            return "missing_page_dimensions"
    if previous.get("region", [0, 0, 1, 1]) != following.get("region", [0, 0, 1, 1]):
        return "different_regions"
    left = previous["restoration"]["paragraphs"][-1]
    right = following["restoration"]["paragraphs"][0]
    if not left["text"].strip() or not right["text"].strip():
        return "empty_boundary"
    if re.search(r"[.!?。！？…:;\"\'”’」』)\]}]\s*$", left["text"]):
        return "closed_sentence_or_dialogue"
    if re.match(r"[\"'“‘「『]", right["text"].lstrip()):
        return "new_dialogue"
    if (
        LIST_START.match(right["text"])
        or LIST_START.match(left["text"])
        or re.fullmatch(r"[\d\W]+", left["text"].strip())
        or re.fullmatch(r"[\d\W]+", right["text"].strip())
    ):
        return "list_or_page_furniture"
    layouts = []
    for record, paragraph, last in ((previous, left, True), (following, right, False)):
        lines = record.get("lines", [])
        indices = paragraph.get("line_indices", [])
        if (
            len(lines) < 2
            or not indices
            or any(type(i) is not int or not 0 <= i < len(lines) for i in indices)
        ):
            return "insufficient_boundary_lines"
        try:
            boxes = [bounds(line) for line in lines]
        except (KeyError, ValueError, TypeError, IndexError):
            return "missing_or_ambiguous_geometry"
        height = median(box[3] - box[1] for box in boxes)
        if height <= 0:
            return "invalid_geometry"
        body = [
            box for box in boxes if 0.85 * height <= box[3] - box[1] <= 1.3 * height
        ] or boxes
        body_left, body_right = min(b[0] for b in body), max(b[2] for b in body)
        if body_right <= body_left:
            return "invalid_geometry"
        # Attachments may contribute several raw fragments to one logical line.
        boundary_index = indices[-1] if last else indices[0]
        edge_box = boxes[boundary_index]
        if not 0.7 * height <= edge_box[3] - edge_box[1] <= 1.3 * height:
            return "boundary_font_change"
        same_row = [
            boxes[i]
            for i in indices
            if abs((boxes[i][1] + boxes[i][3]) / 2 - (edge_box[1] + edge_box[3]) / 2)
            <= height * 0.5
        ]
        edge_left, edge_right = min(b[0] for b in same_row), max(b[2] for b in same_row)
        if last and edge_right < body_left + 0.8 * (body_right - body_left):
            return "short_last_line"
        if not last and edge_left > body_left + height * 0.45:
            return "indented_first_line"
        if (
            not last
            and len(indices) == 1
            and edge_right < body_left + 0.8 * (body_right - body_left)
        ):
            return "short_first_paragraph"
        layouts.append(
            (height / record["height"], (body_right - body_left) / record["width"])
        )
    if (
        min(layouts[0][0], layouts[1][0]) <= 0
        or max(layouts[0][0], layouts[1][0]) / min(layouts[0][0], layouts[1][0]) > 1.3
    ):
        return "font_size_change"
    if abs(layouts[0][1] - layouts[1][1]) > 0.15:
        return "body_width_change"
    return None


def combine_pages(
    records: list[dict], enabled: bool = False, variant: str | None = None
) -> dict:
    """통합 TXT용 문단·경계 결정을 만들며 페이지 records를 변경하지 않는다.

    variant는 Kiwi의 before/without_dictionary 비교 결과를 선택한다.
    단어 경계가 모호하면 공백으로 연결하고 확인 기록을 남긴다. 문자가
    바뀌는 교정은 하지 않으며 페이지 건너뛰기·실패·좌표 미확인은 연결하지 않는다.
    """
    paragraphs, decisions, originals = [], [], []
    previous = None
    for record in records:
        restored = record.get("restoration") or {}
        source = restored.get("paragraphs") or []
        text = restored.get("text")
        if text is None:
            text = record.get(
                "combined_text",
                "\n".join(line["text"] for line in record.get("lines", [])),
            )
        alternative = restored.get("spacing", {}).get(variant) if variant else None
        if alternative is not None:
            text = alternative
        originals.append(text)
        values = paragraph_texts(restored, variant) if source else [text.rstrip()]
        if source and len(values) != len(source):
            raise ValueError("페이지 문단과 비교 텍스트의 개수가 일치하지 않습니다.")
        incoming = [
            {
                "text": value,
                "sources": [
                    {
                        "page": record["page"],
                        "paragraph_index": index,
                        "line_indices": list(source[index].get("line_indices", []))
                        if source
                        else [],
                    }
                ],
            }
            for index, value in enumerate(values)
        ]
        if previous is not None:
            reason = boundary_reason(previous, record) if enabled else "disabled"
            decision = {
                "previous_page": previous["page"],
                "next_page": record["page"],
                "status": "kept",
                "reason": reason,
            }
            if reason is None and paragraphs and incoming:
                separator, uncertain = join_lines(
                    paragraphs[-1]["text"], incoming[0]["text"]
                )
                paragraphs[-1]["text"] += separator + incoming[0]["text"]
                paragraphs[-1]["sources"].extend(incoming.pop(0)["sources"])
                decision.update(
                    status="joined",
                    separator=separator,
                    reason="continuation_geometry",
                    review_required=uncertain,
                )
            decisions.append(decision)
        paragraphs.extend(incoming)
        previous = record
    combined = "\n\n".join(p["text"] for p in paragraphs)
    if re.sub(r"\s", "", combined) != re.sub(r"\s", "", "".join(originals)):
        raise ValueError("페이지 연결이 공백 외의 문자를 변경했습니다.")
    return {
        "enabled": enabled,
        "text": combined,
        "paragraphs": paragraphs,
        "boundaries": decisions,
    }


def paragraph_texts(restored: dict, variant: str | None) -> list[str]:
    """문단 객체/보정 배열에서 텍스트를 읽고 내부 빈 줄을 문단 경계로 오인하지 않는다.

    이전 형식의 보정 문자열은 원문 글자 수와 실제 생성 구분자에 맞춰
    정렬한다. 정렬 근거가 부족하면 다시 보정하도록 오류를 낸다.
    """
    source = [paragraph["text"] for paragraph in restored["paragraphs"]]
    if variant is None:
        return source
    spacing = restored.get("spacing", {})
    aligned = spacing.get("paragraphs", {}).get(variant)
    if aligned is not None:
        if (
            not isinstance(aligned, list)
            or len(aligned) != len(source)
            or any(not isinstance(value, str) for value in aligned)
        ):
            raise ValueError("문단별 보정 텍스트 형식/개수를 확인하세요.")
        if any(
            re.sub(r"\s", "", before) != re.sub(r"\s", "", after)
            for before, after in zip(source, aligned, strict=True)
        ):
            raise ValueError("문단별 보정 비교가 원문 글자를 변경했습니다.")
        return aligned[:]
    text = spacing.get(variant)
    if text is None:
        return source
    if not isinstance(text, str) or re.sub(r"\s", "", text) != re.sub(
        r"\s", "", "".join(source)
    ):
        raise ValueError("보정 비교 텍스트의 원문 글자를 확인하세요.")
    if len(source) == 1:
        return [text]
    result, offset = [], 0
    for index, paragraph in enumerate(source):
        wanted = re.sub(r"\s", "", paragraph)
        begin = offset
        found = ""
        while offset < len(text) and len(found) < len(wanted):
            if not text[offset].isspace():
                found += text[offset]
            offset += 1
        if not wanted or found != wanted:
            raise ValueError(
                "이전 보정 결과의 문단을 정렬할 수 없습니다. 원시 JSON을 다시 보정하세요."
            )
        if index == len(source) - 1:
            result.append(text[begin:])
        else:
            if not text.startswith("\n\n", offset):
                raise ValueError("이전 보정 결과의 문단 경계가 일치하지 않습니다.")
            result.append(text[begin:offset])
            offset += 2
    return result


def save_combined(
    output: Path,
    records: list[dict],
    enabled: bool = False,
    variant: str | None = None,
    filename: str = "combined.txt",
) -> dict:
    """소유한 새 결과 폴더의 통합 TXT를 원자적으로 갱신하고 기본 경계 JSON을 저장한다."""
    result = combine_pages(records, enabled, variant)
    target = output / filename
    temporary = target.with_suffix(target.suffix + ".tmp")
    temporary.write_text(result["text"] + "\n", encoding="utf-8")
    temporary.replace(target)
    if filename == "combined.txt":
        target = output / "connections.json"
        temporary = target.with_suffix(".json.tmp")
        temporary.write_text(
            json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        temporary.replace(target)
    return result
