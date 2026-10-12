"""Resolve explicit device choices without silently changing the user's choice."""

import sys
from pathlib import Path


def ocr_python(root, engine, output_format="txt"):
    """Markdown 전용 환경 또는 PP-OCRv5 전용 Python을 선택하고 나머지는 현재 경로를 쓴다.

    Raises:
        FileNotFoundError: Markdown 전용 환경이 설치되지 않은 경우.
    """
    # Paddle and Torch ship different Windows CUDA DLLs. Run Paddle separately
    # so switching models cannot load incompatible DLLs into the same process.
    if output_format == "md":
        isolated = Path(root) / ".venv-doc-parser" / "Scripts" / "python.exe"
        if not isolated.is_file():
            raise FileNotFoundError(
                "Markdown 전용 환경을 설치하세요. docs/MARKDOWN_EXPORT.md를 참조하세요."
            )
        return str(isolated)
    isolated = Path(root) / ".venv-paddle" / "Scripts" / "python.exe"
    if engine == "paddle" and isolated.is_file():
        return str(isolated)
    return sys.executable


def resolve_device(requested, gpu_available):
    """요청한 장치를 확인하고 명시적 GPU 요청을 보존한다.

    Args:
        requested: cpu, gpu 또는 GPU 우선 자동 선택을 뜻하는 auto.
        gpu_available: 호출한 실행 환경에서 GPU를 사용할 수 있는지 여부.

    Returns:
        선택한 cpu 또는 gpu 문자열.

    Raises:
        ValueError: 지원하지 않는 장치 이름인 경우.
        RuntimeError: 명시적으로 요청한 GPU를 사용할 수 없는 경우.
    """
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
