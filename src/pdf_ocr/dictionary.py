"""로컬 고유명사 사전의 입력 검사·식별·안전한 UTF-8 저장을 제공한다."""

import hashlib
import json
import os
import re
import tempfile
from dataclasses import dataclass
from pathlib import Path


def normalize_words(words) -> tuple[str, ...]:
    """빈 줄·중복을 정리하고 동일 글자의 상반된 띄어쓰기 표기를 거부한다."""
    if not isinstance(words, (list, tuple)) or len(words) > 10000:
        raise ValueError("단어 목록은 최대 10,000개로 작성하세요.")
    unique = {}
    for word in words:
        if not isinstance(word, str) or any(
            ord(char) < 32 and char not in "\t" for char in word
        ):
            raise ValueError("각 단어는 줄바꿈·제어 문자가 없는 문자열이어야 합니다.")
        word = re.sub(r"\s+", " ", word).strip()
        if not word:
            continue
        if len(word) > 100:
            raise ValueError("한 단어는 100자 이내로 작성하세요.")
        key = word.replace(" ", "")
        if key in unique and unique[key] != word:
            raise ValueError(
                f"표기 충돌: '{unique[key]}' / '{word}'. 사용할 표기 하나만 남기세요."
            )
        unique[key] = word
    if not unique:
        raise ValueError("사전에 단어를 하나 이상 입력하세요.")
    return tuple(unique.values())


@dataclass(frozen=True)
class UserDictionary:
    """작업 동안 변경되지 않는 버전 1 사전과 내용 식별값을 제공한다."""

    name: str
    words: tuple[str, ...]

    def __post_init__(self):
        """사전 이름과 단어를 검증하고 정규화된 불변 목록을 설정한다."""
        if not isinstance(self.name, str) or not self.name.strip():
            raise ValueError("사전 이름을 입력하세요.")
        if len(self.name.strip()) > 100 or any(ord(c) < 32 for c in self.name):
            raise ValueError("사전 이름은 제어 문자 없이 100자 이내로 작성하세요.")
        object.__setattr__(self, "name", self.name.strip())
        object.__setattr__(self, "words", normalize_words(self.words))

    def payload(self) -> dict:
        """로컬 파일에 저장할 버전·이름·단어 목록을 반환한다."""
        return {"version": 1, "name": self.name, "words": list(self.words)}

    def identity(self) -> dict:
        """이름·단어의 순서까지 구별하는 SHA-256과 실행 조건을 반환한다."""
        data = json.dumps(self.payload(), ensure_ascii=False, sort_keys=True)
        return {
            "version": 1,
            "name": self.name,
            "word_count": len(self.words),
            "sha256": hashlib.sha256(data.encode("utf-8")).hexdigest(),
        }


def load_dictionary(path: Path) -> UserDictionary:
    """UTF-8/BOM JSON 사전을 검사하며 지원하지 않는 버전·형식을 거부한다."""
    data = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    if not isinstance(data, dict) or type(data.get("version")) is not int:
        raise ValueError("버전·이름·단어 목록을 포함한 JSON 사전을 선택하세요.")
    if data["version"] != 1:
        raise ValueError("지원하지 않는 사전 버전입니다. 버전 1 사전을 사용하세요.")
    return UserDictionary(data.get("name"), data.get("words"))


def import_words(path: Path) -> tuple[str, ...]:
    """UTF-8/BOM TXT의 한 줄당 한 단어를 읽고 전체 입력을 검사한다."""
    return normalize_words(Path(path).read_text(encoding="utf-8-sig").splitlines())


def write_local(path: Path, text: str, overwrite: bool = False):
    """UTF-8 파일을 저장하며 기본적으로 기존 파일을 보호한다.

    덮어쓰기는 호출자가 사용자 확인을 받은 경우에만 허용한다.
    새 파일은 배타적으로 생성하고 승인된 덮어쓰기는 임시 파일로 교체한다.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if not overwrite:
        with path.open("x", encoding="utf-8", newline="\n") as file:
            file.write(text)
        return
    descriptor, temporary = tempfile.mkstemp(dir=path.parent, prefix=".dictionary-")
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as file:
            file.write(text)
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


def save_dictionary(path: Path, dictionary: UserDictionary, overwrite: bool = False):
    """정규화된 사전을 UTF-8 JSON으로 저장하며 기존 파일은 승인 없이 보호한다."""
    write_local(
        path,
        json.dumps(dictionary.payload(), ensure_ascii=False, indent=2) + "\n",
        overwrite,
    )
