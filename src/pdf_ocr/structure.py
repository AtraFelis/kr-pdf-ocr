"""로컬 VL 1.6 공식 구조 분석을 페이지·영역 선택과 Markdown 저장에 연결한다."""

import json
import os
import re
import time
from importlib.metadata import version
from pathlib import Path

from .devices import resolve_device
from .pdf import render_pages


class LocalStructureEngine:
    """로컬 배치 분석과 VLM을 사용하며 서버·자동 모델 다운로드를 허용하지 않는다."""

    def __init__(self, root: Path, device: str):
        """명시적 모델 경로와 장치를 검사한 뒤 v1.6 파이프라인을 초기화한다."""
        if tuple(int(x) for x in version("paddleocr").split(".")[:2]) < (3, 6):
            raise RuntimeError(
                "Markdown은 구조 분석 전용 환경(.venv-doc-parser)이 필요합니다."
            )
        layout = root / "models" / "PP-DocLayoutV3"
        vl = root / "models" / "PaddleOCR-VL-1.6"
        if (
            not (layout / "inference.json").is_file()
            or not (vl / "model.safetensors").is_file()
        ):
            raise FileNotFoundError(
                "구조 분석 모델이 없습니다. scripts/download_structure_models.py를 실행하세요."
            )
        os.environ["PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK"] = "True"
        os.environ["PADDLE_PDX_CACHE_HOME"] = str(root / ".cache" / "structure")
        os.environ["HF_HUB_OFFLINE"] = "1"
        os.environ["TRANSFORMERS_OFFLINE"] = "1"
        import paddle
        from paddleocr import PaddleOCRVL

        self.package_versions = {
            "paddleocr": version("paddleocr"),
            "paddlex": version("paddlex"),
            "paddle": paddle.__version__,
        }

        selected = resolve_device(
            device,
            device != "cpu"
            and paddle.is_compiled_with_cuda()
            and paddle.device.cuda.device_count() > 0,
        )
        self.device = "gpu:0" if selected == "gpu" else "cpu"
        self.pipeline = PaddleOCRVL(
            pipeline_version="v1.6",
            device=self.device,
            layout_detection_model_dir=str(layout),
            vl_rec_model_dir=str(vl),
            use_doc_orientation_classify=False,
            use_doc_unwarping=False,
            use_chart_recognition=False,
            markdown_ignore_labels=[],
            use_queues=False,
        )

    def recognize(self, image):
        """선택 이미지 한 장을 구조 분석하고 공식 원시 JSON·Markdown·이미지를 반환한다."""
        import numpy as np

        with image.convert("RGB") as rgb:
            results = self.pipeline.predict(np.asarray(rgb)[:, :, ::-1].copy())
        if len(results) != 1:
            raise ValueError("한 페이지의 구조 분석 결과 개수를 확인하세요.")
        return results[0]


def save_structure(
    result, folder: Path, page: int, box, width: int, height: int
) -> dict:
    """블록·좌표·이미지를 보존하고 원본 이미지 경로를 동시 치환해 저장한다."""
    raw = result.json["res"]
    (folder / f"page-{page:03}-native.json").write_text(
        json.dumps(raw, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    info = result.markdown
    markdown = info["markdown_texts"]
    assets = folder / "assets"
    assets.mkdir(exist_ok=True)
    image_paths = []
    replacements = {}
    for index, (source, image) in enumerate(info["markdown_images"].items(), 1):
        if image is None:
            raise ValueError(f"공식 결과의 이미지 데이터가 없습니다: {source}")
        target = f"assets/page-{page:03}-{index:03}.png"
        image.save(folder / target)
        replacements[source] = target
        image_paths.append({"source_path": source, "path": target})
    if replacements:
        pattern = "|".join(
            re.escape(source) for source in sorted(replacements, key=len, reverse=True)
        )
        markdown = re.sub(pattern, lambda match: replacements[match.group()], markdown)
    blocks = []
    for index, block in enumerate(raw["parsing_res_list"]):
        bbox = block.get("block_bbox")
        full = (
            None
            if bbox is None
            else [
                bbox[0] + box[0],
                bbox[1] + box[1],
                bbox[2] + box[0],
                bbox[3] + box[1],
            ]
        )
        blocks.append(
            {
                "type": block["block_label"],
                "content": block["block_content"],
                "order": block.get("block_order"),
                "source_index": index,
                "bbox_in_input": bbox,
                "bbox": full,
                "relative_bbox": None
                if full is None
                else [
                    full[0] / width,
                    full[1] / height,
                    full[2] / width,
                    full[3] / height,
                ],
            }
        )
    record = {
        "page": page,
        "width": width,
        "height": height,
        "region_pixel_box": list(box),
        "blocks": blocks,
        "raw": raw,
        "markdown": markdown,
        "images": image_paths,
    }
    (folder / f"page-{page:03}.json").write_text(
        json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (folder / f"page-{page:03}.md").write_text(markdown, encoding="utf-8")
    return record


def run_structure(args, root: Path, pages, region, page_regions):
    """선택 페이지를 순차 구조 분석하고 완료 Markdown·원시 결과·실행 상태를 보존한다."""
    engine = None
    records, texts = [], []
    state = "failed"
    try:
        engine = LocalStructureEngine(root, args.device or "auto")
        for number, image in render_pages(args.pdf, pages, args.dpi):
            started = time.perf_counter()
            selected = page_regions.get(number, region)
            box = selected.pixel_box(image.width, image.height)
            cropped = image.crop(box)
            try:
                result = engine.recognize(cropped)
                record = save_structure(
                    result, args.output, number, box, image.width, image.height
                )
                record["region"] = selected.values()
                (args.output / f"page-{number:03}.json").write_text(
                    json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8"
                )
                records.append(record)
                texts.append(record["markdown"])
                (args.output / "combined.md").write_text(
                    "\n\n".join(texts), encoding="utf-8"
                )
            finally:
                cropped.close()
                image.close()
            print(
                f"page={number} lines={len(record['blocks'])} seconds={time.perf_counter() - started:.2f}",
                flush=True,
            )
        state = "completed"
    finally:
        (args.output / "summary.json").write_text(
            json.dumps(
                {
                    "engine": "vl16",
                    "pipeline_version": "v1.6",
                    "format": "md",
                    "device": getattr(engine, "device", None),
                    "requested_device": args.device or "auto",
                    "dpi": args.dpi,
                    "package_versions": getattr(engine, "package_versions", None),
                    "exclude_hanja_annotations": False,
                    "state": state,
                    "selected_pages": pages,
                    "completed_pages": [r["page"] for r in records],
                    "chart_recognition": False,
                    "spacing_repair": False,
                    "network_connections_blocked": True,
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
