#!/usr/bin/env python3
"""Valida que todo YAML versionado é parseável e não está vazio.

Os manifests de adapter declaram capacidades que o router lê para escolher um worker; um
manifest que não parseia derruba o roteamento no ponto mais caro, já com a tarefa em mãos.
Os workflows de CI têm o mesmo problema com sintoma pior: um YAML inválido em
`.github/workflows/` não reprova o PR, ele simplesmente não roda, e a ausência do check é
lida como ausência de problema.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]


def tracked() -> list[Path]:
    listing = subprocess.run(
        ["git", "-C", str(ROOT), "ls-files", "-z", "*.yml", "*.yaml"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    return [ROOT / entry for entry in listing.split("\0") if entry]


def main() -> int:
    failures: list[str] = []
    documents = tracked()

    for path in documents:
        relative = path.relative_to(ROOT)
        try:
            loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
        except yaml.YAMLError as error:
            failures.append(f"{relative}: {str(error).splitlines()[0]}")
            continue
        if loaded is None:
            failures.append(f"{relative}: documento vazio")

    for failure in failures:
        print(f"YAML inválido: {failure}", file=sys.stderr)
    if failures:
        return 1
    print(f"YAML válido: {len(documents)} arquivos.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
