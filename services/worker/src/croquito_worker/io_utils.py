"""Primitivas pequenas para publicação atômica de artefatos locais."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import Final

DIRECT_WRITE_ENV: Final = "CROQUITO_IO_DIRECT_WRITE"
"""Liga a escrita direta, para volume onde `rename` não é a operação atômica.

Em disco local, a dança `arquivo temporário + os.replace` é o que garante que um leitor
concorrente nunca veja artefato pela metade: o `rename` é atômico e o nome final só passa a
existir com os bytes inteiros em disco.

Num bucket montado por FUSE (o volume da rodada hospedada, ADR-0026) essa garantia não
existe: o `rename` vira copy+delete, que não é atômico, custa a cópia inteira e pode deixar
o temporário para trás. Lá quem dá a atomicidade é o próprio armazenamento — o `close` do
arquivo vira um PUT de objeto, e o objeto só é substituído quando o PUT fecha. Escrever
direto é, nesse volume, MAIS seguro que a dança do temporário, não menos.

Desligada (o default) o comportamento é exatamente o de sempre.
"""

_TRUTHY_VALUES: Final[frozenset[str]] = frozenset({"1", "true", "yes"})


def direct_write_enabled() -> bool:
    """Lê a variável a cada chamada, e não no import.

    O custo é um `os.environ.get` por artefato gravado — irrelevante ao lado do `fsync`
    que vem logo depois — e o ganho é que o modo é observável em teste e trocável sem
    reimportar módulo.
    """
    return os.environ.get(DIRECT_WRITE_ENV, "").strip().casefold() in _TRUTHY_VALUES


def atomic_write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if direct_write_enabled():
        with path.open("w", encoding="utf-8") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        return
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
    if direct_write_enabled():
        with path.open("wb") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        return
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
