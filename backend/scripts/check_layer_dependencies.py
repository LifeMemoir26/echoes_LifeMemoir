"""Static checks for DDD layering, forbidden imports, and naming rules."""

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

IMPORT_RE = re.compile(r"^\s*(from|import)\s+([a-zA-Z0-9_\.]+)")
SNAKE_CASE_FILE_RE = re.compile(r"^[a-z][a-z0-9_]*\.py$")
FORBIDDEN_NAME_PARTS = ("processer", "tmpstorage", "pendingevent")
TEST_SCRIPT_RE = re.compile(r"^(test_.*|.*_test)\.py$")


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


def _module_name(py_file: Path) -> str:
    rel = py_file.relative_to(SRC).with_suffix("")
    return "src." + ".".join(rel.parts)


def _resolve_import(py_file: Path, import_stmt: str) -> str:
    token = import_stmt.strip()
    if not token.startswith("."):
        return token

    module_parts = _module_name(py_file).split(".")
    pkg_parts = module_parts[:-1]
    dot_count = len(token) - len(token.lstrip("."))
    suffix = token[dot_count:]
    keep = max(0, len(pkg_parts) - (dot_count - 1))
    resolved_parts = pkg_parts[:keep]
    if suffix:
        resolved_parts.extend(suffix.split("."))
    return ".".join(resolved_parts)


def _allowed(from_layer: str, to_layer: str, imported_abs: str) -> bool:
    if from_layer == to_layer:
        return True
    if from_layer == "domain":
        return False
    if from_layer == "application":
        return to_layer in {"domain", "infra"}
    if from_layer == "infra":
        return to_layer == "domain" or (
            to_layer == "application" and imported_abs.startswith("src.application.contracts")
        )
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
            imported = m.group(2)
            imported_abs = _resolve_import(py_file, imported)

            if imported_abs.startswith("src.services") or imported_abs.startswith("src.infrastructure"):
                rel = py_file.relative_to(ROOT)
                violations.append(f"{rel}:{lineno}: forbidden legacy import ({imported_abs})")
                continue

            to_layer = _imported_layer(imported_abs)
            if not to_layer:
                continue
            if not _allowed(from_layer, to_layer, imported_abs):
                rel = py_file.relative_to(ROOT)
                violations.append(
                    f"{rel}:{lineno}: disallowed dependency {from_layer} -> {to_layer} ({imported_abs})"
                )

    deprecated_services = SRC / "services"
    if deprecated_services.exists():
        for py_file in sorted(deprecated_services.rglob("*.py")):
            rel = py_file.relative_to(ROOT)
            violations.append(f"{rel}: deprecated path is forbidden (src/services)")

    deprecated_infra = SRC / "infrastructure"
    if deprecated_infra.exists():
        for py_file in sorted(deprecated_infra.rglob("*.py")):
            text = py_file.read_text(encoding="utf-8").strip()
            if "Compatibility alias module; migrate imports to src.infra" not in text:
                rel = py_file.relative_to(ROOT)
                violations.append(
                    f"{rel}: only temporary compatibility aliases are allowed under src/infrastructure"
                )

    for py_file in SRC.rglob("*.py"):
        name = py_file.name
        rel = py_file.relative_to(ROOT)
        if name != "__init__.py" and not SNAKE_CASE_FILE_RE.match(name):
            violations.append(f"{rel}: filename is not snake_case")
        if any(part in name for part in FORBIDDEN_NAME_PARTS):
            violations.append(f"{rel}: filename uses deprecated naming variant")

    deprecated_knowledge_dirs = [
        SRC / "application" / "knowledge" / "extraction_application",
        SRC / "application" / "knowledge" / "refinement_application",
    ]
    for d in deprecated_knowledge_dirs:
        if d.exists():
            violations.append(f"{d.relative_to(ROOT)}: deprecated package path is forbidden")

    scripts_dir = ROOT / "scripts"
    for py_file in scripts_dir.rglob("*.py"):
        if TEST_SCRIPT_RE.match(py_file.name):
            rel = py_file.relative_to(ROOT)
            violations.append(
                f"{rel}: test files are not allowed under backend/scripts; move to backend/tests"
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
