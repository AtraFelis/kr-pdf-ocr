"""Conservative removal of explicitly adjacent Hanja annotations."""

import re

HANJA = (
    r"\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff\U00020000-\U0002ffff\U00030000-\U000323af"
)
ADJACENT = re.compile(rf"(?<=[가-힣])[{HANJA}]+")
PARENTHESIZED = re.compile(rf"(?<=[가-힣])[ \t]*[（(][{HANJA} \t]+[)）]")


def remove_hanja_annotations(text: str) -> str:
    """Preserve standalone Hanja and English; never guess misrecognized Hangul."""
    return ADJACENT.sub("", PARENTHESIZED.sub("", text))
