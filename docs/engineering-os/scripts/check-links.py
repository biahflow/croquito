#!/usr/bin/env python3
"""Valida todo link relativo de Markdown do repositório.

A camada global é vendorizada como espelho completo nos projetos consumidores, onde os
portões de documentação deles validam estes mesmos links. Um link quebrado aqui vira
falha lá, num repositório que não pode consertá-lo — então ele é reprovado na origem.

`{{EOS_ROOT}}` é placeholder de adapter, resolvido só na instalação; não é link.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LINK = re.compile(r"\[([^\]]*)\]\(([^)]+)\)")
EXTERNAL = ("http://", "https://", "mailto:", "#")


def tracked_markdown() -> list[Path]:
    listing = subprocess.run(
        ["git", "-C", str(ROOT), "ls-files", "-z", "*.md"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    return [ROOT / entry for entry in listing.split("\0") if entry]


def broken(document: Path) -> list[str]:
    failures: list[str] = []
    for number, line in enumerate(document.read_text(encoding="utf-8").splitlines(), 1):
        for _, target in LINK.findall(line):
            if target.startswith(EXTERNAL) or "{{" in target:
                continue
            path = target.split("#")[0]
            if not path:
                continue
            if not (document.parent / path).resolve().exists():
                failures.append(f"{document.relative_to(ROOT)}:{number} -> {target}")
    return failures


def main() -> int:
    documents = tracked_markdown()
    failures = [failure for document in documents for failure in broken(document)]
    for failure in failures:
        print(f"link inexistente: {failure}", file=sys.stderr)
    if failures:
        print(f"\n{len(failures)} link(s) quebrado(s) em {len(documents)} documentos.", file=sys.stderr)
        return 1
    print(f"Links válidos: {len(documents)} documentos Markdown.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
