"""One-based page selection and normalized regions independent of OCR engines."""

import json
import math
from dataclasses import dataclass
from pathlib import Path


def parse_pages(value: str, total: int | None = None) -> list[int]:
    """1 기반 번호·범위를 입력 순서로 해석하고 중복을 제거하며 범위 오류를 거부한다."""
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
    """전체 또는 지정 페이지에서 제외 번호를 빼고 PDF 순서로 반환하며 빈 결과를 거부한다."""
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
    """페이지 크기와 독립적인 0~1 상대 좌표의 유효한 불변 사각형이다."""

    left: float = 0
    top: float = 0
    right: float = 1
    bottom: float = 1

    def __post_init__(self):
        """좌표의 숫자·유한성·순서·0~1 범위를 검사하고 잘못된 영역을 거부한다."""
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
        """왼쪽·위쪽·오른쪽·아래쪽 순서의 상대 좌표 목록을 반환한다."""
        return [self.left, self.top, self.right, self.bottom]

    def pixel_box(self, width: int, height: int):
        """양수 이미지 크기에 맞춰 시작은 내림·끝은 올림한 PIL 자르기 좌표를 반환한다."""
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
        """기준 이미지의 픽셀 좌표를 검증 가능한 상대 영역으로 변환한다."""
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
    """쉼표로 나눈 값을 요청 개수의 유한한 실수 목록으로 해석하고 오류를 거부한다."""
    values = [float(x.strip()) for x in value.split(",")]
    if len(values) != count or not all(math.isfinite(x) for x in values):
        raise ValueError(f"쉼표로 구분한 숫자 {count}개가 필요합니다.")
    return values


def load_regions(path: Path | None, total: int) -> dict[int, Region]:
    """선택적 UTF-8 JSON의 1 기반 페이지별 영역을 읽고 번호·중복·좌표를 검사한다."""
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
    """잘린 입력의 좌표를 보존하면서 전체 페이지 픽셀·상대 좌표를 추가한다.

    Args:
        lines: 원시 텍스트와 선택적 입력 이미지 polygon을 가진 줄 목록.
        box: 전체 페이지 픽셀 기준의 자르기 사각형.
        width: 전체 페이지 이미지 너비이며 양수여야 한다.
        height: 전체 페이지 이미지 높이이며 양수여야 한다.

    Returns:
        polygon_in_input, polygon, relative_polygon을 구분한 새 줄 목록.
        모델이 제공하지 않은 좌표는 None으로 유지하고 입력은 변경하지 않는다.
    """
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
