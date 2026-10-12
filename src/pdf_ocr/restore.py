"""저장 OCR을 모델 재실행 없이 새 경로에서 재보정하고 비교 결과를 보존한다."""

import argparse
import json
from pathlib import Path

from .dictionary import load_dictionary, save_dictionary
from .paragraphs import restore_paragraphs


def saved_pages(source: Path) -> list[tuple[Path, dict]]:
    """원시 lines가 있는 페이지 JSON을 검사하고 페이지 번호 순서로 반환한다."""
    paths = sorted(source.glob("page-*.json")) if source.is_dir() else [source]
    records = []
    numbers = set()
    for path in paths:
        record = json.loads(path.read_text(encoding="utf-8-sig"))
        if not isinstance(record, dict) or not isinstance(record.get("lines"), list):
            raise TypeError(
                f"{path.name}: 원시 lines를 포함한 OCR 페이지 JSON이 필요합니다."
            )
        number = record.get("page", len(records) + 1)
        if type(number) is not int or number < 1 or number in numbers:
            raise ValueError(
                f"{path.name}: 중복되지 않는 1 이상 페이지 번호가 필요합니다."
            )
        numbers.add(number)
        record = {**record, "page": number}
        if not record["lines"] or any(
            not isinstance(line, dict) or not isinstance(line.get("text"), str)
            for line in record["lines"]
        ):
            raise ValueError(f"{path.name}: 재보정할 OCR 텍스트를 확인하세요.")
        records.append((path, record))
    if not records:
        raise ValueError("선택한 폴더에 page-*.json OCR 결과가 없습니다.")
    return sorted(records, key=lambda item: item[1].get("page", 0))


def reprocess(source: Path, output: Path, spacing=None, keep_hanja=False):
    """원시 결과로 재보정하고 비교 TXT·JSON을 새 폴더에 저장한다.

    사용자 편집본과 원본 파일은 수정하지 않는다. 사전은 좌표 복원이 가능한
    결과에만 적용하며 완료한 페이지는 실패·취소 뒤에도 디스크에 남는다.
    """
    pages = saved_pages(source)
    output.mkdir(parents=True, exist_ok=False)
    dictionary = getattr(spacing, "dictionary", None)
    if dictionary:
        save_dictionary(output / "dictionary.json", dictionary)
    texts, baselines, originals = [], [], []
    for index, (path, record) in enumerate(pages, 1):
        restored = restore_paragraphs(record["lines"], not keep_hanja)
        if spacing and dictionary and not restored["geometry_applied"]:
            raise ValueError(
                f"{path.name}: 좌표가 없거나 겹쳐 사전 보정을 적용할 수 없습니다."
            )
        before = restored["text"]
        if spacing:
            restored = spacing.repair(restored)
        texts.append(restored["text"])
        originals.append(before)
        baselines.append(restored.get("spacing", {}).get("without_dictionary", before))
        stem = f"page-{record.get('page', index):03}"
        (output / f"{stem}.json").write_text(
            json.dumps(
                {**record, "restoration": restored}, ensure_ascii=False, indent=2
            ),
            encoding="utf-8",
        )
        (output / f"{stem}.txt").write_text(restored["text"] + "\n", encoding="utf-8")
        for name, values in (
            ("combined.txt", texts),
            ("without-dictionary.txt", baselines),
            ("before-spacing.txt", originals),
        ):
            (output / name).write_text("\n\n".join(values) + "\n", encoding="utf-8")
        if len(pages) == 1:
            (output / "restored.txt").write_text(
                restored["text"] + "\n", encoding="utf-8"
            )
            (output / "restoration.json").write_text(
                json.dumps(restored, ensure_ascii=False, indent=2), encoding="utf-8"
            )
        print(f"page={index} lines={len(record['lines'])}", flush=True)


def main():
    """CLI의 사전·보정 옵션을 검사하고 저장 OCR을 새 출력 폴더로 재처리한다."""
    parser = argparse.ArgumentParser(description="저장된 OCR 결과의 문단·사전 재보정")
    parser.add_argument("input", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--keep-hanja", action="store_true")
    parser.add_argument("--repair-spacing", action="store_true")
    parser.add_argument("--dictionary", type=Path)
    args = parser.parse_args()
    try:
        dictionary = load_dictionary(args.dictionary) if args.dictionary else None
        if dictionary and not args.repair_spacing:
            parser.error("사전은 --repair-spacing과 함께 사용하세요.")
        spacing = None
        if args.repair_spacing:
            from .spacing import LocalSpacingRepair

            spacing = LocalSpacingRepair(dictionary)
        reprocess(args.input, args.output, spacing, args.keep_hanja)
    except (ValueError, TypeError, OSError, KeyError) as error:
        parser.error(str(error))


if __name__ == "__main__":
    main()
