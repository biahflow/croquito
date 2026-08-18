"""Primitivas pequenas para publicação atômica de artefatos locais."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path


def atomic_write_text(path: Path, content: str) -> None:
    """Publica o artefato pela dança `arquivo temporário + os.replace`.

    Em disco local é ela que garante que um leitor concorrente nunca veja artefato pela
    metade: o `rename` é atômico e o nome final só passa a existir com os bytes inteiros
    em disco.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.")
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary_path, path)
    finally:
        if temporary_path.exists():
            temporary_path.unlink()


def atomic_write_bytes(path: Path, content: bytes) -> None:
    """Irmã binária de `atomic_write_text`, para o PDF que o projetista envia.

    Mesma disciplina: o arquivo só existe no nome final quando os bytes inteiros já estão
    em disco — leitor concorrente nunca enxerga uma prancha pela metade.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.")
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary_path, path)
    finally:
        if temporary_path.exists():
            temporary_path.unlink()
