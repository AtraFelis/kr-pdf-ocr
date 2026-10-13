"""합성 문장의 Kiwi·gec_kr 후보와 과잉 교정·자원 사용을 로컬에서 비교한다."""

import argparse
import json
import os
import platform
import socket
import threading
import time
from difflib import SequenceMatcher
from importlib.metadata import version
from pathlib import Path

import psutil

from pdf_ocr.evaluation import compare_text
from pdf_ocr.gec import LocalGEC

ROOT = Path(__file__).resolve().parents[1]


def validate_cases(cases):
    """정답·식별값·원문에 존재하는 보호 표기를 확인해 잘못된 평가를 거부한다."""
    if not isinstance(cases, list) or not cases:
        raise ValueError("평가 사례는 비어 있지 않은 JSON 배열이어야 합니다.")
    identifiers = set()
    for case in cases:
        if not isinstance(case, dict):
            raise TypeError("각 평가 사례는 JSON 객체여야 합니다.")
        for key in ("id", "category", "source", "reference"):
            if not isinstance(case.get(key), str) or not case[key].strip():
                raise ValueError(
                    f"평가 사례에 비어 있지 않은 {key} 문자열이 필요합니다."
                )
        if case["id"] in identifiers:
            raise ValueError("평가 사례 id는 중복될 수 없습니다.")
        identifiers.add(case["id"])
        protected = case.get("protected", [])
        if not isinstance(protected, list) or any(
            not isinstance(value, str) or not value or value not in case["source"]
            for value in protected
        ):
            raise ValueError("보호 표기는 원문에 존재하는 문자열 목록이어야 합니다.")


def reject_network(*args, **kwargs):
    """평가 프로세스에서 Python 소켓의 원격 연결을 오류로 거부한다."""
    raise RuntimeError("문자 교정 평가는 로컬 파일만 사용합니다.")


def changed_spans(before: str, after: str) -> list[dict]:
    """원문 기준 Unicode 코드 포인트의 반개방 구간과 변경 문자열을 기록한다."""
    return [
        {
            "operation": operation,
            "start": start,
            "end": end,
            "before": before[start:end],
            "after": after[new_start:new_end],
        }
        for operation, start, end, new_start, new_end in SequenceMatcher(
            None, before, after, autojunk=False
        ).get_opcodes()
        if operation != "equal"
    ]


class MemorySampler:
    """초기화와 추론 중 프로세스 RSS를 20ms마다 관찰한다."""

    def __init__(self):
        """프로세스와 종료 이벤트를 준비하고 현재 RSS를 초기 최댓값으로 둔다."""
        self.process = psutil.Process()
        self.peak = self.process.memory_info().rss
        self.stop = threading.Event()
        self.thread = threading.Thread(target=self.sample, daemon=True)

    def sample(self):
        """종료 요청까지 RSS를 관찰하며 모든 순간의 피크를 보장하지 않는다."""
        while not self.stop.wait(0.02):
            self.peak = max(self.peak, self.process.memory_info().rss)

    def __enter__(self):
        """관찰 스레드를 시작하고 측정기를 반환한다."""
        self.thread.start()
        return self

    def __exit__(self, *args):
        """소유한 스레드를 종료하고 마지막 RSS를 반영한다."""
        self.stop.set()
        self.thread.join()
        self.peak = max(self.peak, self.process.memory_info().rss)


def summarize(rows: list[dict], method: str) -> dict:
    """정답 대비 문자 오류와 정상 문장 변경·등록 표기 손실을 집계한다.

    실패는 성공률에 포함하지 않고 별도 기록한다. CER은 모든 정답 문자 수를
    분모로 합산하며 정상 문장 변경은 의미 오류와 구분되는 보수적인 표시다.
    """
    successful = [r for r in rows if r[method]["candidate"] is not None]
    normal = [r for r in successful if r["source"] == r["reference"]]
    erroneous = [r for r in successful if r["source"] != r["reference"]]
    metrics = {}
    retained_metrics = {}
    for key in ("whitespace_sensitive", "ignore_whitespace"):
        count = sum(
            r[method]["metrics"][key]["reference_characters"] for r in successful
        )
        errors = sum(r[method]["metrics"][key]["edit_distance"] for r in successful)
        metrics[key] = {
            "errors": errors,
            "reference_characters": count,
            "cer": errors / count if count else None,
        }
        all_count = sum(r["raw"]["metrics"][key]["reference_characters"] for r in rows)
        retained_errors = sum(
            (r[method]["metrics"] or r["raw"]["metrics"])[key]["edit_distance"]
            for r in rows
        )
        retained_metrics[key] = {
            "errors": retained_errors,
            "reference_characters": all_count,
            "cer": retained_errors / all_count if all_count else None,
        }
    return {
        "successful": len(successful),
        "failures": len(rows) - len(successful),
        "exact_matches": sum(
            r[method]["candidate"] == r["reference"] for r in successful
        ),
        "normal_cases": len(normal),
        "normal_changed": sum(r[method]["candidate"] != r["source"] for r in normal),
        "error_cases": len(erroneous),
        "improved": sum(
            r[method]["metrics"]["whitespace_sensitive"]["edit_distance"]
            < r["raw"]["metrics"]["whitespace_sensitive"]["edit_distance"]
            for r in erroneous
        ),
        "worsened": sum(
            r[method]["metrics"]["whitespace_sensitive"]["edit_distance"]
            > r["raw"]["metrics"]["whitespace_sensitive"]["edit_distance"]
            for r in erroneous
        ),
        "protected_text_lost": sum(
            bool(r[method]["lost_protected_text"]) for r in successful
        ),
        "seconds": sum(r[method]["seconds"] for r in rows),
        "metrics": metrics,
        "all_cases_metrics_with_failed_candidates_retaining_raw": retained_metrics,
    }


def main():
    """새 출력 폴더에 사례별 후보·실패·지표와 실행 환경을 기록한다."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--device", choices=("cpu", "gpu"), required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--cases", type=Path, default=ROOT / "samples/synthetic/gec_cases.json"
    )
    args = parser.parse_args()
    cases = json.loads(args.cases.read_text(encoding="utf-8"))
    validate_cases(cases)
    args.output.mkdir(parents=True, exist_ok=False)
    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["TRANSFORMERS_OFFLINE"] = "1"
    socket.socket.connect = reject_network
    socket.socket.connect_ex = reject_network
    socket.create_connection = reject_network
    from kiwipiepy import Kiwi

    rows = []
    started = time.perf_counter()
    with MemorySampler() as memory:
        engine = LocalGEC(ROOT / "models/gec_kr", args.device)
        kiwi = Kiwi()
        initialization = time.perf_counter() - started
        if args.device == "gpu":
            engine.torch.cuda.reset_peak_memory_stats()
        for case in cases:
            row = dict(case)
            spacing_started = time.perf_counter()
            spacing = kiwi.space(case["source"], reset_whitespace=True)
            spacing_seconds = time.perf_counter() - spacing_started
            if "".join(spacing.split()) != "".join(case["source"].split()):
                raise ValueError("Kiwi가 공백 외 글자를 변경했습니다.")
            for method, source in (
                ("raw", case["source"]),
                ("kiwi", spacing),
                ("gec", case["source"]),
                ("kiwi_gec", spacing),
            ):
                start = time.perf_counter()
                result = (
                    engine.suggest(source)
                    if method in {"gec", "kiwi_gec"}
                    else {"candidate": source, "failure": None}
                )
                result["seconds"] = time.perf_counter() - start
                if method in {"kiwi", "kiwi_gec"}:
                    result["seconds"] += spacing_seconds
                candidate = result["candidate"]
                result["changes_from_original"] = (
                    changed_spans(case["source"], candidate)
                    if candidate is not None
                    else []
                )
                result["metrics"] = (
                    compare_text(case["reference"], candidate)
                    if candidate is not None
                    else None
                )
                result["lost_protected_text"] = [
                    text
                    for text in case.get("protected", [])
                    if candidate is not None and text not in candidate
                ]
                row[method] = result
            rows.append(row)
            (args.output / "cases.json").write_text(
                json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            print(f"{case['id']} completed", flush=True)
    report = {
        "model": engine.manifest,
        "device": engine.device,
        "dtype": "float32",
        "os": platform.platform(),
        "python": platform.python_version(),
        "processor": platform.processor(),
        "logical_cpu_count": psutil.cpu_count(),
        "generation": {
            "max_length": 128,
            "num_beams": 4,
            "repetition_penalty": 2.0,
            "do_sample": False,
        },
        "packages": {
            name: version(name)
            for name in ("torch", "transformers", "kiwipiepy", "psutil")
        },
        "torch_threads": engine.torch.get_num_threads(),
        "gpu": engine.torch.cuda.get_device_name() if args.device == "gpu" else None,
        "initialization_seconds": initialization,
        "total_seconds": time.perf_counter() - started,
        "observed_process_peak_rss_bytes": memory.peak,
        "gpu_peak_allocated_bytes": engine.torch.cuda.max_memory_allocated()
        if args.device == "gpu"
        else None,
        "gpu_peak_reserved_bytes": engine.torch.cuda.max_memory_reserved()
        if args.device == "gpu"
        else None,
        "network": "offline flags + Python socket connect/connect_ex/create_connection rejected; not OS firewall proof",
        "case_count": len(cases),
        "summaries": {
            method: summarize(rows, method)
            for method in ("raw", "kiwi", "gec", "kiwi_gec")
        },
    }
    (args.output / "report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(report["summaries"], ensure_ascii=False, indent=2), flush=True)


if __name__ == "__main__":
    main()
