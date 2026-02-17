"""Check naming conventions and deprecated module aliases in migrated paths."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

DEPRECATED_FILES = [
    ROOT / "src" / "services" / "interview" / "dialogue_storage" / "eventsupplement.py",
    ROOT / "src" / "services" / "interview" / "dialogue_storage" / "interviewsuggestion.py",
]


def main() -> int:
    problems: list[str] = []

    for f in DEPRECATED_FILES:
        if f.exists():
            problems.append(f"deprecated alias file still exists: {f.relative_to(ROOT)}")

    if problems:
        print("Module naming check failed:")
        for item in problems:
            print(f"- {item}")
        return 1

    print("Module naming check passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
