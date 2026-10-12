"""Reprocess saved OCR JSON without loading models or changing source files."""

import argparse
import json
from pathlib import Path

from .paragraphs import restore_paragraphs


def main():
    """모델 재실행 없이 저장 OCR JSON의 문단·공백을 재처리해 새 출력 경로에 쓴다."""
    parser = argparse.ArgumentParser(description="저장된 OCR 결과의 문단 복원")
    parser.add_argument("input", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--keep-hanja", action="store_true")
    parser.add_argument("--repair-spacing", action="store_true")
    args = parser.parse_args()
    record = json.loads(args.input.read_text(encoding="utf-8-sig"))
    restored = restore_paragraphs(record["lines"], not args.keep_hanja)
    if args.repair_spacing:
        from .spacing import LocalSpacingRepair

        restored = LocalSpacingRepair().repair(restored)
    args.output.mkdir(parents=True, exist_ok=False)
    (args.output / "restored.txt").write_text(restored["text"] + "\n", encoding="utf-8")
    (args.output / "restoration.json").write_text(
        json.dumps(restored, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(
        f"paragraphs={len(restored['paragraphs'])} reviews={len(restored['reviews'])}"
    )


if __name__ == "__main__":
    main()
