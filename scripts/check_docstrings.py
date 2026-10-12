"""Check nonempty docstrings in project code without importing OCR or GUI runtimes."""

import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CODE_DIRECTORIES = ("src", "scripts", "tests")


def missing_docstrings(path: Path) -> list[tuple[int, str]]:
    """Return line numbers and names of undocumented modules and declarations.

    Private and nested classes, functions, async functions and methods are
    included. Lambdas have no docstring body and are outside this check.
    Syntax and file errors propagate to the caller for a nonzero CLI result.
    """
    tree = ast.parse(path.read_text(encoding="utf-8-sig"), filename=str(path))
    missing = []
    for node in ast.walk(tree):
        if not isinstance(
            node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)
        ):
            continue
        if not (ast.get_docstring(node) or "").strip():
            missing.append(
                (getattr(node, "lineno", 1), getattr(node, "name", "module"))
            )
    return sorted(missing)


def main() -> int:
    """Scan fixed project code directories and fail on missing docs or invalid files."""
    paths = sorted(
        path
        for directory in CODE_DIRECTORIES
        for path in (ROOT / directory).rglob("*.py")
    )
    errors = []
    for path in paths:
        relative = path.relative_to(ROOT)
        try:
            for line, name in missing_docstrings(path):
                errors.append(f"{relative}:{line}: missing docstring: {name}")
        except (OSError, UnicodeError, SyntaxError) as error:
            errors.append(f"{relative}: cannot inspect file: {error}")
    if errors:
        print("\n".join(errors), file=sys.stderr)
        return 1
    print(
        f"Docstrings present in all modules and declarations of {len(paths)} Python files."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
