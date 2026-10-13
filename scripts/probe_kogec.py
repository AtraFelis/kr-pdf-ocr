"""KoGEC 공개 토큰의 불일치를 보존하면서 제한된 로컬 GPU 진단을 기록한다."""

import argparse
import json
import socket
import time
from pathlib import Path

from evaluate_gec import (
    MemorySampler,
    changed_spans,
    reject_network,
    summarize,
    validate_cases,
)

from pdf_ocr.evaluation import compare_text
from pdf_ocr.kogec import KoGECProbe

ROOT = Path(__file__).resolve().parents[1]


def main():
    """새 폴더에 진단 후보를 기록하며 미확인 토큰을 사용한 공식 성능 평가를 금지한다."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", choices=("600m", "3.3b"), required=True)
    parser.add_argument("--diagnostic-only", action="store_true")
    parser.add_argument(
        "--cases", type=Path, default=ROOT / "samples/synthetic/gec_cases.json"
    )
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if not args.diagnostic_only:
        parser.error("교정 토큰 매핑이 미확인입니다. --diagnostic-only만 지원합니다.")
    cases = json.loads(args.cases.read_text(encoding="utf-8"))
    validate_cases(cases)
    args.output.mkdir(parents=True, exist_ok=False)
    socket.socket.connect = reject_network
    socket.socket.connect_ex = reject_network
    socket.create_connection = reject_network
    from kiwipiepy import Kiwi

    rows = []
    started = time.perf_counter()
    with MemorySampler() as memory:
        engine = KoGECProbe(ROOT, args.model, args.diagnostic_only)
        initialization = time.perf_counter() - started
        engine.torch.cuda.reset_peak_memory_stats()
        kiwi = Kiwi()
        for case in cases:
            row = dict(case)
            spacing = kiwi.space(case["source"], reset_whitespace=True)
            if "".join(spacing.split()) != "".join(case["source"].split()):
                raise ValueError("Kiwi 공백 외 글자가 변경됐습니다.")
            for method, source in (
                ("raw", case["source"]),
                ("kiwi", spacing),
                ("diagnostic", case["source"]),
                ("kiwi_diagnostic", spacing),
            ):
                start = time.perf_counter()
                result = (
                    engine.suggest(source)
                    if "diagnostic" in method
                    else {"candidate": source, "failure": None}
                )
                result["seconds"] = time.perf_counter() - start
                candidate = result["candidate"]
                result["metrics"] = (
                    compare_text(case["reference"], candidate)
                    if candidate is not None
                    else None
                )
                result["changes_from_original"] = (
                    changed_spans(case["source"], candidate)
                    if candidate is not None
                    else []
                )
                result["lost_protected_text"] = [
                    v
                    for v in case.get("protected", [])
                    if candidate is not None and v not in candidate
                ]
                row[method] = result
            rows.append(row)
            (args.output / "cases.json").write_text(
                json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            print(f"{case['id']} completed", flush=True)
    report = {
        "audit": engine.audit,
        "official_quality_evaluation": False,
        "generation": {
            "target": "kor_Hang, not paper correction token",
            "num_beams": 4,
            "max_new_tokens": 128,
        },
        "device": engine.torch.cuda.get_device_name(),
        "dtype": str(engine.dtype),
        "initialization_seconds": initialization,
        "total_seconds": time.perf_counter() - started,
        "observed_peak_rss_bytes": memory.peak,
        "gpu_peak_allocated_bytes": engine.torch.cuda.max_memory_allocated(),
        "gpu_peak_reserved_bytes": engine.torch.cuda.max_memory_reserved(),
        "diagnostic_summaries": {
            method: summarize(rows, method)
            for method in ("raw", "kiwi", "diagnostic", "kiwi_diagnostic")
        },
        "restriction": "Do not interpret diagnostic CER as paper reproduction or model-quality ranking.",
        "network": "Local files + offline flags + Python socket connection rejection; not OS firewall verification",
    }
    (args.output / "report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(report, ensure_ascii=False, indent=2), flush=True)


if __name__ == "__main__":
    main()
