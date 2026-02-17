"""Static check for DDD layer dependency direction.

This checker validates imports inside the new layer directories only:
- src/domain
- src/application
- src/infra
- src/interfaces
"""

from __future__ import annotations

import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"

LAYER_DIRS = {
    "domain": SRC / "domain",
    "application": SRC / "application",
    "infra": SRC / "infra",
    "interfaces": SRC / "interfaces",
}

IMPORT_RE = re.compile(r"^\s*(?:from|import)\s+([a-zA-Z0-9_\.]+)")


def _layer_of_path(path: Path) -> str | None:
    for layer, layer_dir in LAYER_DIRS.items():
        if path.is_relative_to(layer_dir):
            return layer
    return None


def _imported_layer(import_stmt: str) -> str | None:
    token = import_stmt.strip()
    if token.startswith("src.domain"):
        return "domain"
    if token.startswith("src.application"):
        return "application"
    if token.startswith("src.infra"):
        return "infra"
    if token.startswith("src.interfaces"):
        return "interfaces"
    return None


def _allowed(from_layer: str, to_layer: str) -> bool:
    if from_layer == "domain":
        return to_layer not in {"application", "infra", "interfaces"}
    if from_layer == "application":
        return to_layer == "domain"
    if from_layer == "infra":
        return to_layer == "domain"
    if from_layer == "interfaces":
        return to_layer in {"application", "domain"}
    return True


def check() -> int:
    violations: list[str] = []

    for py_file in SRC.rglob("*.py"):
        from_layer = _layer_of_path(py_file)
        if not from_layer:
            continue

        lines = py_file.read_text(encoding="utf-8").splitlines()
        for lineno, line in enumerate(lines, start=1):
            m = IMPORT_RE.match(line)
            if not m:
                continue
            imported = m.group(1)
            to_layer = _imported_layer(imported)
            if not to_layer:
                continue
            if not _allowed(from_layer, to_layer):
                rel = py_file.relative_to(ROOT)
                violations.append(
                    f"{rel}:{lineno}: disallowed dependency {from_layer} -> {to_layer} ({imported})"
                )

    if violations:
        print("Layer dependency violations found:")
        for v in violations:
            print(f"- {v}")
        return 1

    print("Layer dependency check passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(check())
