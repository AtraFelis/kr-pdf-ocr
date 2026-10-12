"""Reference-based text comparison; confidence scores are not accuracy."""

import re


def edit_distance(reference: str, actual: str) -> int:
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
