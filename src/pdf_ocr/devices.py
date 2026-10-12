"""Resolve explicit device choices without silently changing the user's choice."""

import sys
from pathlib import Path


def ocr_python(root, engine):
    # Paddle and Torch ship different Windows CUDA DLLs. Run Paddle separately
    # so switching models cannot load incompatible DLLs into the same process.
    isolated = Path(root) / ".venv-paddle" / "Scripts" / "python.exe"
    if engine == "paddle" and isolated.is_file():
        return str(isolated)
    return sys.executable


def resolve_device(requested, gpu_available):
    if requested not in ("cpu", "gpu", "auto"):
        raise ValueError("처리 장치는 cpu, gpu 또는 auto를 선택하세요.")
    if requested == "cpu":
        return "cpu"
    if gpu_available:
        return "gpu"
    if requested == "auto":
        return "cpu"
    raise RuntimeError(
        "선택한 모델에서 GPU를 사용할 수 없습니다. "
        "GPU 실행 환경과 NVIDIA 드라이버를 확인하거나 처리 장치를 CPU로 바꿔 주세요."
    )
