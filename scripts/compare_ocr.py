import argparse
import json
from pathlib import Path

from pdf_ocr.evaluation import compare_text
from pdf_ocr.text import remove_hanja_annotations


def main():
    parser = argparse.ArgumentParser(description="정답 TXT와 OCR 결과 비교")
    parser.add_argument("reference", type=Path)
    parser.add_argument("results", type=Path, nargs="+")
    parser.add_argument("--exclude-hanja", action="store_true")
    args = parser.parse_args()
    reference = args.reference.read_text(encoding="utf-8")
    normalize = remove_hanja_annotations if args.exclude_hanja else lambda text: text
    records = {
        str(path): compare_text(
            normalize(reference), normalize(path.read_text(encoding="utf-8"))
        )
        for path in args.results
    }
    print(json.dumps(records, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
