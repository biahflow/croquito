"""Publicação de artefato: temporário + rename, e nada de temporário deixado para trás.

O oráculo destes testes não é o conteúdo gravado, é **como** ele chega ao nome final:
`os.replace` cria um inode novo, então o nome só passa a existir com os bytes inteiros em
disco e leitor concorrente nunca vê artefato pela metade.
"""

from __future__ import annotations

from pathlib import Path

from croquito_worker.io_utils import atomic_write_bytes, atomic_write_text


def _leftovers(directory: Path) -> list[str]:
    """Arquivos temporários deixados para trás; publicar não pode sujar a rodada."""
    return sorted(path.name for path in directory.iterdir() if path.name.startswith("."))


def test_the_text_writer_publishes_through_a_temporary_file_and_a_rename(tmp_path: Path) -> None:
    path = tmp_path / "takeoff-packet.json"
    atomic_write_text(path, "primeiro\n")
    first_inode = path.stat().st_ino

    atomic_write_text(path, "segundo\n")

    assert path.read_text(encoding="utf-8") == "segundo\n"
    # Inode novo é a assinatura do `os.replace`: o nome final passou a apontar para outro
    # arquivo, que só existiu depois de os bytes inteiros estarem em disco.
    assert path.stat().st_ino != first_inode
    assert _leftovers(tmp_path) == []


def test_the_binary_writer_publishes_the_same_way(tmp_path: Path) -> None:
    """A prancha em PDF sobe pela mesma porta; ela não pode ficar de fora da disciplina."""
    path = tmp_path / "prancha-origem.pdf"
    atomic_write_bytes(path, b"%PDF-1.4 primeiro")
    first_inode = path.stat().st_ino

    atomic_write_bytes(path, b"%PDF-1.4 segundo")

    assert path.read_bytes() == b"%PDF-1.4 segundo"
    assert path.stat().st_ino != first_inode
    assert _leftovers(tmp_path) == []


def test_both_writers_create_the_parent_directory(tmp_path: Path) -> None:
    atomic_write_text(tmp_path / "nova" / "arquivo.json", "{}\n")
    atomic_write_bytes(tmp_path / "outra" / "arquivo.bin", b"\x00")

    assert (tmp_path / "nova" / "arquivo.json").read_text(encoding="utf-8") == "{}\n"
    assert (tmp_path / "outra" / "arquivo.bin").read_bytes() == b"\x00"
