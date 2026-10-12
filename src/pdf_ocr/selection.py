"""One-based page selection and normalized regions independent of OCR engines."""

import json
import math
from dataclasses import dataclass
from pathlib import Path


def parse_pages(value: str, total: int | None = None) -> list[int]:
    pages = []
    for piece in value.split(","):
        ends = piece.strip().split("-")
        if len(ends) == 1:
            first = last = int(ends[0])
        elif len(ends) == 2:
            first, last = map(int, ends)
        else:
            raise ValueError("페이지 범위가 올바르지 않습니다.")
        if first < 1 or first > last or (total is not None and last > total):
            raise ValueError("페이지 범위를 확인하세요. 번호는 1부터 시작합니다.")
        for number in range(first, last + 1):
            if number not in pages:
                pages.append(number)
    return pages


def select_pages(value: str, excluded: str, total: int) -> list[int]:
    selected = (
        list(range(1, total + 1))
        if value.strip().lower() == "all"
        else parse_pages(value, total)
    )
    exclusions = parse_pages(excluded, total) if excluded.strip() else []
    selected = sorted(set(selected) - set(exclusions))
    if not selected:
        raise ValueError("처리할 페이지가 없습니다.")
    return selected


@dataclass(frozen=True)
class Region:
    left: float = 0
    top: float = 0
    right: float = 1
    bottom: float = 1

    def __post_init__(self):
        values = (self.left, self.top, self.right, self.bottom)
        if not all(
            isinstance(x, (float, int)) and not isinstance(x, bool) and math.isfinite(x)
            for x in values
        ):
            raise ValueError("영역 좌표는 유한한 숫자여야 합니다.")
        if not (0 <= self.left < self.right <= 1 and 0 <= self.top < self.bottom <= 1):
            raise ValueError(
                "영역은 0~1 범위이며 왼쪽<오른쪽, 위쪽<아래쪽이어야 합니다."
            )

    def values(self):
        return [self.left, self.top, self.right, self.bottom]

    def pixel_box(self, width: int, height: int):
        if width <= 0 or height <= 0:
            raise ValueError("페이지 이미지 크기가 올바르지 않습니다.")
        return (
            math.floor(self.left * width),
            math.floor(self.top * height),
            math.ceil(self.right * width),
            math.ceil(self.bottom * height),
        )

    @classmethod
    def from_pixels(cls, coordinates, width, height):
        if (
            not math.isfinite(width)
            or not math.isfinite(height)
            or width <= 0
            or height <= 0
        ):
            raise ValueError("기준 이미지 크기는 양수여야 합니다.")
        left, top, right, bottom = coordinates
        return cls(left / width, top / height, right / width, bottom / height)


def parse_numbers(value: str, count: int):
    values = [float(x.strip()) for x in value.split(",")]
    if len(values) != count or not all(math.isfinite(x) for x in values):
        raise ValueError(f"쉼표로 구분한 숫자 {count}개가 필요합니다.")
    return values


def load_regions(path: Path | None, total: int) -> dict[int, Region]:
    if path is None:
        return {}
    data = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(data, dict):
        raise TypeError("페이지별 영역 파일은 페이지 번호와 좌표의 객체여야 합니다.")
    regions = {}
    for key, values in data.items():
        number = int(key)
        if (
            number < 1
            or number > total
            or not isinstance(values, list)
            or len(values) != 4
        ):
            raise ValueError(
                "페이지별 영역의 페이지 번호 또는 좌표 개수가 올바르지 않습니다."
            )
        if number in regions:
            raise ValueError("중복된 페이지 영역이 있습니다.")
        regions[number] = Region(*values)
    return regions


def page_coordinates(lines: list[dict], box, width, height):
    results = []
    for line in lines:
        polygon = line.get("polygon")
        translated = (
            None if polygon is None else [[x + box[0], y + box[1]] for x, y in polygon]
        )
        results.append(
            {
                **line,
                "polygon_in_input": polygon,
                "polygon": translated,
                "relative_polygon": None
                if translated is None
                else [[x / width, y / height] for x, y in translated],
            }
        )
    return results
