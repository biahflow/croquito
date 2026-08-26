#!/usr/bin/env python3
"""Reprova artefato gerado e arquivo grande rastreados.

Esta camada é vendorizada como espelho completo dentro de cada projeto consumidor: tudo
que é rastreado aqui é copiado para lá. Cinco binários Go compilados e nove relatórios de
cobertura já levaram o espelho de 144 KB para 25 MB antes de existir este portão.

O `.gitignore` impede que voltem por acidente; este portão impede que voltem por `git add
-f` ou por um caminho novo que o ignore não previu. O limite de tamanho é o backstop
genérico: um repositório de documentação e fonte Go pequena não tem arquivo de 1 MB.
"""

from __future__ import annotations

import fnmatch
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SIZE_LIMIT = 1_000_000

GENERATED = (
    "*.cov",
    "*.out",
    "*.html",
    "biah/bin/*",
    "biah/e2e-demo",
    "biah/e2e-integration-test",
    "biah/cmd/*/e2e-integration-test",
)


def tracked() -> list[str]:
    listing = subprocess.run(
        ["git", "-C", str(ROOT), "ls-files", "-z"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    return [entry for entry in listing.split("\0") if entry]


def main() -> int:
    failures: list[str] = []
    files = tracked()

    for entry in files:
        for pattern in GENERATED:
            if fnmatch.fnmatch(entry, pattern):
                failures.append(f"artefato gerado rastreado: {entry} (casa com `{pattern}`)")
                break

    for entry in files:
        size = (ROOT / entry).stat().st_size
        if size > SIZE_LIMIT:
            failures.append(f"arquivo grande rastreado: {entry} ({size // 1024} KB)")

    for failure in failures:
        print(failure, file=sys.stderr)
    if failures:
        print(
            "\nRemova do índice com `git rm --cached <arquivo>` e cubra o caminho no "
            "`.gitignore`. Todo arquivo rastreado aqui é vendorizado em cada consumidor.",
            file=sys.stderr,
        )
        return 1
    print(f"Sem artefatos gerados rastreados: {len(files)} arquivos.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
