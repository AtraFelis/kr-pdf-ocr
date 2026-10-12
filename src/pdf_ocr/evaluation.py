"""Reference-based text comparison; confidence scores are not accuracy."""

import re


def edit_distance(reference: str, actual: str) -> int:
    """문자열 사이의 삽입·삭제·치환 횟수인 Levenshtein 편집 거리를 반환한다."""
    previous = list(range(len(actual) + 1))
    for i, expected in enumerate(reference, 1):
        current = [i]
        for j, observed in enumerate(actual, 1):
            current.append(
                min(
                    previous[j] + 1,
                    current[j - 1] + 1,
                    previous[j - 1] + (expected != observed),
                )
            )
        previous = current
    return previous[-1]


def compare_text(reference: str, actual: str) -> dict:
    """공백 정규화·공백 제거 조건별 편집 거리와 문자 오류율을 계산한다.

    Args:
        reference: 사용자가 대조할 정답 텍스트.
        actual: OCR 또는 후처리로 얻은 비교 텍스트.

    Returns:
        조건별 정답 문자 수, 편집 거리와 정답 문자 수 대비 오류율.

    Raises:
        ValueError: 정규화한 정답이 비어 있어 오류율을 계산할 수 없는 경우.
    """
    results = {}
    for key, normalize in (
        ("whitespace_sensitive", lambda s: re.sub(r"\s+", " ", s).strip()),
        ("ignore_whitespace", lambda s: re.sub(r"\s+", "", s)),
    ):
        expected, observed = normalize(reference), normalize(actual)
        if not expected:
            raise ValueError("정답 텍스트가 비어 있습니다.")
        errors = edit_distance(expected, observed)
        results[key] = {
            "reference_characters": len(expected),
            "edit_distance": errors,
            "character_error_rate": errors / len(expected),
        }
    return results
