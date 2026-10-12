"""Local OCR with original results and conservative paragraph restoration."""

import argparse
import json
import socket
import time
from pathlib import Path

import psutil
from PIL import ImageDraw

from .engine import LocalPaddleEngine
from .paragraphs import restore_paragraphs
from .pdf import page_count, render_pages
from .selection import (
    Region,
    load_regions,
    page_coordinates,
    parse_numbers,
    select_pages,
)
from .text import remove_hanja_annotations

ROOT = Path(__file__).resolve().parents[2]


def deny_connection(*args, **kwargs):
    """문서 처리 중 소켓 연결을 거부하고 RuntimeError를 발생시킨다."""
    raise RuntimeError("문서 처리 중 네트워크 연결은 차단됩니다.")


def main():
    """선택 페이지·영역을 로컬 OCR하고 원시 결과·복원 TXT·실행 기록을 저장한다."""
    parser = argparse.ArgumentParser(description="로컬 PDF OCR 모델 시험")
    parser.add_argument("pdf", type=Path)
    parser.add_argument("--pages", default="all", help="all 또는 1,3,5-7")
    parser.add_argument("--exclude-pages", default="", help="제외할 페이지 번호·범위")
    parser.add_argument("--dpi", type=int, default=300)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--engine", choices=("paddle", "vl", "vl16", "qwen"), default="paddle"
    )
    parser.add_argument(
        "--device",
        choices=("cpu", "gpu", "auto"),
        help="처리 장치: 생략하면 PP-OCRv5는 CPU, VLM은 GPU 우선",
    )
    parser.add_argument(
        "--keep-hanja", action="store_true", help="병기 한자를 삭제하지 않음"
    )
    parser.add_argument(
        "--vl-lines", action="store_true", help="VLM을 검출 줄 영역별로 실행"
    )
    parser.add_argument(
        "--keep-line-breaks", action="store_true", help="문단 복원을 적용하지 않음"
    )
    parser.add_argument(
        "--repair-spacing", action="store_true", help="로컬 Kiwi로 띄어쓰기 보정 제안"
    )
    region_options = parser.add_mutually_exclusive_group()
    region_options.add_argument(
        "--region", help="상대 좌표: 왼쪽,위쪽,오른쪽,아래쪽 (0~1)"
    )
    region_options.add_argument("--region-px", help="기준 이미지의 픽셀 좌표 4개")
    region_options.add_argument("--y-range", help="기준 높이의 위쪽,아래쪽 픽셀 범위")
    parser.add_argument("--reference-size", help="픽셀 좌표의 기준 너비,높이")
    parser.add_argument(
        "--reference-height", type=float, help="y-range 기준 높이 (기본 1000)"
    )
    parser.add_argument("--regions-file", type=Path, help="페이지별 상대 좌표 JSON")
    args = parser.parse_args()
    if args.keep_line_breaks and args.repair_spacing:
        parser.error("띄어쓰기 보정은 문단 복원과 함께 사용하세요.")
    if not args.pdf.is_file() or args.dpi < 72:
        parser.error("PDF 파일 경로와 DPI(72 이상)를 확인하세요.")
    if args.reference_size and not args.region_px:
        parser.error("reference-size는 region-px와 함께 사용하세요.")
    if args.reference_height is not None and not args.y_range:
        parser.error("reference-height는 y-range와 함께 사용하세요.")
    try:
        total_pages = page_count(args.pdf)
        pages = select_pages(args.pages, args.exclude_pages, total_pages)
        region = Region()
        if args.region:
            region = Region(*parse_numbers(args.region, 4))
        elif args.region_px:
            if not args.reference_size:
                parser.error("region-px에는 reference-size가 필요합니다.")
            region = Region.from_pixels(
                parse_numbers(args.region_px, 4), *parse_numbers(args.reference_size, 2)
            )
        elif args.y_range:
            top, bottom = parse_numbers(args.y_range, 2)
            region = Region.from_pixels(
                [0, top, 1, bottom],
                1,
                args.reference_height if args.reference_height is not None else 1000,
            )
        page_regions = load_regions(args.regions_file, total_pages)
    except (ValueError, TypeError, OSError) as error:
        parser.error(str(error))
    # Unique output directories protect previous results and user edits.
    args.output.mkdir(parents=True, exist_ok=False)
    socket.socket.connect = deny_connection
    socket.socket.connect_ex = deny_connection
    start = time.perf_counter()
    requested_device = args.device or ("cpu" if args.engine == "paddle" else "auto")
    if args.engine in ("vl", "vl16", "qwen"):
        from .vl_engine import LocalVLEngine

        engine = LocalVLEngine(
            ROOT,
            line_regions=args.vl_lines,
            model_name={
                "qwen": "Qwen3-VL-2B-Instruct",
                "vl": "PaddleOCR-VL-1.5",
                "vl16": "PaddleOCR-VL-1.6",
            }[args.engine],
            device=requested_device,
        )
    else:
        engine = LocalPaddleEngine(ROOT, device=requested_device)
    initialization = time.perf_counter() - start
    spacing = None
    if args.repair_spacing:
        from .spacing import LocalSpacingRepair

        spacing = LocalSpacingRepair()
    records = []
    combined = []
    try:
        for number, image in render_pages(args.pdf, pages, args.dpi):
            started = time.perf_counter()
            selected_region = page_regions.get(number, region)
            box = selected_region.pixel_box(image.width, image.height)
            cropped = image.crop(box)
            try:
                lines = page_coordinates(
                    engine.recognize(cropped), box, image.width, image.height
                )
                cropped.save(args.output / f"page-{number:03}-input.png")
            finally:
                cropped.close()
            restored = (
                None
                if args.keep_line_breaks
                else restore_paragraphs(lines, not args.keep_hanja)
            )
            if spacing is not None:
                restored = spacing.repair(restored)
            record = {
                "page": number,
                "width": image.width,
                "height": image.height,
                "region": selected_region.values(),
                "region_pixel_box": box,
                "seconds": time.perf_counter() - started,
                "rss_bytes": psutil.Process().memory_info().rss,
                "lines": lines,
                "restoration": restored,
            }
            image.save(args.output / f"page-{number:03}.png")
            preview = image.copy()
            ImageDraw.Draw(preview).rectangle(
                (box[0], box[1], box[2] - 1, box[3] - 1), outline="red", width=3
            )
            preview.save(args.output / f"page-{number:03}-selection.png")
            preview.close()
            (args.output / f"page-{number:03}.json").write_text(
                json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            raw = "\n".join(line["text"] for line in lines) + "\n"
            (args.output / f"page-{number:03}-raw.txt").write_text(
                raw, encoding="utf-8"
            )
            cleaned = raw if args.keep_hanja else remove_hanja_annotations(raw)
            if restored is not None:
                cleaned = restored["text"] + "\n"
            (args.output / f"page-{number:03}.txt").write_text(
                cleaned, encoding="utf-8"
            )
            image.close()
            records.append(record)
            combined.append(cleaned.rstrip())
            (args.output / "combined.txt").write_text(
                "\n\n".join(combined) + "\n", encoding="utf-8"
            )
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
                    "requested_device": requested_device,
                    "dpi": args.dpi,
                    "initialization_seconds": initialization,
                    "network_connections_blocked": True,
                    "paragraph_restoration": not args.keep_line_breaks,
                    "spacing_repair": args.repair_spacing,
                    "total_pages": total_pages,
                    "selected_pages": pages,
                    "default_region": region.values(),
                    "page_regions": {
                        str(k): v.values() for k, v in page_regions.items()
                    },
                    "completed_pages": records,
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )


if __name__ == "__main__":
    main()
