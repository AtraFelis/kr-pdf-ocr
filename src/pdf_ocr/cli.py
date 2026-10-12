"""OCR experiment: preserve original line breaks for model evaluation."""

import argparse
import json
import socket
import time
from pathlib import Path

import psutil

from .engine import LocalPaddleEngine
from .pdf import render_pages
from .text import remove_hanja_annotations

ROOT = Path(__file__).resolve().parents[2]


def parse_pages(value: str) -> list[int]:
    pages = []
    for piece in value.split(","):
        ends = piece.strip().split("-")
        if len(ends) == 1:
            numbers = [int(ends[0])]
        elif len(ends) == 2 and int(ends[0]) <= int(ends[1]):
            numbers = range(int(ends[0]), int(ends[1]) + 1)
        else:
            raise ValueError("페이지 범위가 올바르지 않습니다.")
        for number in numbers:
            if number < 1:
                raise ValueError("페이지 번호는 1부터 시작합니다.")
            if number not in pages:
                pages.append(number)
    return pages


def deny_connection(*args, **kwargs):
    raise RuntimeError("문서 처리 중 네트워크 연결은 차단됩니다.")


def main():
    parser = argparse.ArgumentParser(description="로컬 PDF OCR 모델 시험")
    parser.add_argument("pdf", type=Path)
    parser.add_argument("--pages", default="1-2")
    parser.add_argument("--dpi", type=int, default=300)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--engine", choices=("paddle", "vl", "qwen"), default="paddle")
    parser.add_argument(
        "--keep-hanja", action="store_true", help="병기 한자를 삭제하지 않음"
    )
    parser.add_argument(
        "--vl-lines", action="store_true", help="VLM을 검출 줄 영역별로 실행"
    )
    args = parser.parse_args()
    pages = parse_pages(args.pages)
    if not args.pdf.is_file() or args.dpi < 72:
        parser.error("PDF 파일 경로와 DPI(72 이상)를 확인하세요.")
    # Unique output directories protect previous results and user edits.
    args.output.mkdir(parents=True, exist_ok=False)
    socket.socket.connect = deny_connection
    socket.socket.connect_ex = deny_connection
    start = time.perf_counter()
    if args.engine in ("vl", "qwen"):
        from .vl_engine import LocalVLEngine

        engine = LocalVLEngine(
            ROOT,
            line_regions=args.vl_lines,
            model_name="Qwen3-VL-2B-Instruct"
            if args.engine == "qwen"
            else "PaddleOCR-VL-1.5",
        )
    else:
        engine = LocalPaddleEngine(ROOT)
    initialization = time.perf_counter() - start
    records = []
    try:
        for number, image in render_pages(args.pdf, pages, args.dpi):
            started = time.perf_counter()
            lines = engine.recognize(image)
            record = {
                "page": number,
                "width": image.width,
                "height": image.height,
                "seconds": time.perf_counter() - started,
                "rss_bytes": psutil.Process().memory_info().rss,
                "lines": lines,
            }
            image.save(args.output / f"page-{number:03}.png")
            (args.output / f"page-{number:03}.json").write_text(
                json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            raw = "\n".join(line["text"] for line in lines) + "\n"
            (args.output / f"page-{number:03}-raw.txt").write_text(
                raw, encoding="utf-8"
            )
            cleaned = raw if args.keep_hanja else remove_hanja_annotations(raw)
            (args.output / f"page-{number:03}.txt").write_text(
                cleaned, encoding="utf-8"
            )
            image.close()
            records.append(record)
            print(
                f"page={number} lines={len(lines)} seconds={record['seconds']:.2f}",
                flush=True,
            )
    finally:
        (args.output / "summary.json").write_text(
            json.dumps(
                {
                    "engine": args.engine,
                    "vl_line_regions": args.vl_lines,
                    "exclude_hanja_annotations": not args.keep_hanja,
                    "device": getattr(engine, "device", "cpu"),
                    "dpi": args.dpi,
                    "initialization_seconds": initialization,
                    "network_connections_blocked": True,
                    "paragraph_restoration": False,
                    "completed_pages": records,
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )


if __name__ == "__main__":
    main()
