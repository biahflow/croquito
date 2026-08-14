"""Validação leve dos contratos Markdown do repositório."""

from __future__ import annotations

import re
import sys
from pathlib import Path
from urllib.parse import unquote

ROOT = Path(__file__).resolve().parents[1]
IGNORED_PARTS = {".venv", "node_modules", "output", ".terraform"}
LINK_PATTERN = re.compile(r"(?<!!)\[[^\]]+\]\(([^)]+)\)")


def markdown_files() -> list[Path]:
    return sorted(
        path for path in ROOT.rglob("*.md") if not any(part in IGNORED_PARTS for part in path.parts)
    )


def validate_file(path: Path) -> list[str]:
    errors: list[str] = []
    content = path.read_text(encoding="utf-8")
    if content.count("```") % 2:
        errors.append(f"{path.relative_to(ROOT)}: bloco de código não fechado")

    for raw_target in LINK_PATTERN.findall(content):
        target = raw_target.strip().strip("<>").split(maxsplit=1)[0]
        if target.startswith(("http://", "https://", "mailto:", "#")):
            continue
        relative_target = unquote(target.split("#", maxsplit=1)[0])
        if not relative_target:
            continue
        resolved = (path.parent / relative_target).resolve()
        if not resolved.exists():
            errors.append(f"{path.relative_to(ROOT)}: link inexistente -> {relative_target}")
    return errors


def main() -> int:
    files = markdown_files()
    errors = [error for path in files for error in validate_file(path)]
    if errors:
        print("\n".join(errors), file=sys.stderr)
        return 1
    print(f"Documentação válida: {len(files)} arquivos Markdown.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
