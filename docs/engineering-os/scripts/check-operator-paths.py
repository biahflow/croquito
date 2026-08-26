#!/usr/bin/env python3
"""Reprova caminho absoluto de máquina em arquivo versionado.

Um adapter carrega `{{EOS_ROOT}}` e só é resolvido na instalação, justamente para que o
repositório continue portátil. Escrever o caminho de uma máquina num arquivo versionado
funciona para exatamente um executor e quebra para todos os outros — e quebra também para
esse um, no dia em que o checkout muda de lugar.

Este portão existe porque isso já aconteceu: um projeto consumidor declarava a camada
global em `~/workspace/engineeringOS` dentro de um arquivo versionado, e a referência
morreu para todo mundo quando o diretório mudou.

O próprio arquivo é ignorado na varredura: a definição da guarda não é uma violação dela.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SELF = Path(__file__).resolve()
# Home absoluto de macOS e Linux seguido de um nome de usuário.
ABSOLUTE_HOME = re.compile(r"/(?:Users|home)/[A-Za-z0-9._-]+")
TEXT_SUFFIXES = {".md", ".sh", ".py", ".yml", ".yaml", ".go", ".mod", ".txt", ""}


def tracked() -> list[Path]:
    listing = subprocess.run(
        ["git", "-C", str(ROOT), "ls-files", "-z"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    return [ROOT / entry for entry in listing.split("\0") if entry]


def main() -> int:
    failures: list[str] = []
    scanned = 0

    for path in tracked():
        if path.resolve() == SELF or path.suffix not in TEXT_SUFFIXES:
            continue
        try:
            content = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        scanned += 1
        for number, line in enumerate(content.splitlines(), 1):
            found = ABSOLUTE_HOME.search(line)
            if found:
                relative = path.relative_to(ROOT)
                failures.append(f"{relative}:{number} contém `{found.group()}`")

    for failure in failures:
        print(f"caminho de máquina versionado: {failure}", file=sys.stderr)
    if failures:
        print(
            "\nUse `{{EOS_ROOT}}` num adapter, ou `$HOME`/`~` em documentação. Caminho "
            "absoluto de máquina só resolve para quem o escreveu.",
            file=sys.stderr,
        )
        return 1
    print(f"Sem caminhos de máquina versionados: {scanned} arquivos de texto.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
