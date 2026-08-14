"""Publicação de artefato: temporário + rename no disco local, escrita direta no FUSE.

O oráculo destes testes não é o conteúdo gravado (os dois modos gravam o mesmo), é **como**
ele chega ao nome final: `os.replace` cria um inode novo, a escrita direta reaproveita o
que já existe. É essa diferença que importa no volume montado por FUSE da rodada hospedada
(ADR-0026), onde `rename` vira copy+delete e deixa de ser a operação atômica.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from croquito_worker.io_utils import (
    DIRECT_WRITE_ENV,
    atomic_write_bytes,
    atomic_write_text,
    direct_write_enabled,
)


def _leftovers(directory: Path) -> list[str]:
    """Arquivos temporários deixados para trás; nenhum modo pode sujar a rodada."""
    return sorted(path.name for path in directory.iterdir() if path.name.startswith("."))


def test_the_default_publishes_through_a_temporary_file_and_a_rename(tmp_path: Path) -> None:
    path = tmp_path / "takeoff-packet.json"
    atomic_write_text(path, "primeiro\n")
    first_inode = path.stat().st_ino

    atomic_write_text(path, "segundo\n")

    assert path.read_text(encoding="utf-8") == "segundo\n"
    # Inode novo é a assinatura do `os.replace`: o nome final passou a apontar para outro
    # arquivo, que só existiu depois de os bytes inteiros estarem em disco.
    assert path.stat().st_ino != first_inode
    assert _leftovers(tmp_path) == []


def test_direct_write_replaces_the_content_in_place(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(DIRECT_WRITE_ENV, "1")
    path = tmp_path / "takeoff-packet.json"
    atomic_write_text(path, "primeiro\n")
    first_inode = path.stat().st_ino

    atomic_write_text(path, "segundo\n")

    assert path.read_text(encoding="utf-8") == "segundo\n"
    assert path.stat().st_ino == first_inode
    assert _leftovers(tmp_path) == []


def test_direct_write_also_applies_to_the_binary_writer(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A prancha em PDF sobe pela mesma porta; ela não pode ficar de fora do modo."""
    monkeypatch.setenv(DIRECT_WRITE_ENV, "true")
    path = tmp_path / "prancha-origem.pdf"
    atomic_write_bytes(path, b"%PDF-1.4 primeiro")
    first_inode = path.stat().st_ino

    atomic_write_bytes(path, b"%PDF-1.4 segundo")

    assert path.read_bytes() == b"%PDF-1.4 segundo"
    assert path.stat().st_ino == first_inode


def test_both_writers_create_the_parent_directory_in_every_mode(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(DIRECT_WRITE_ENV, "yes")

    atomic_write_text(tmp_path / "nova" / "arquivo.json", "{}\n")
    atomic_write_bytes(tmp_path / "outra" / "arquivo.bin", b"\x00")

    assert (tmp_path / "nova" / "arquivo.json").read_text(encoding="utf-8") == "{}\n"
    assert (tmp_path / "outra" / "arquivo.bin").read_bytes() == b"\x00"


@pytest.mark.parametrize("value", ["1", "true", "TRUE", " yes ", "Yes"])
def test_the_mode_is_read_from_the_environment_on_every_call(
    monkeypatch: pytest.MonkeyPatch, value: str
) -> None:
    monkeypatch.setenv(DIRECT_WRITE_ENV, value)

    assert direct_write_enabled() is True


@pytest.mark.parametrize("value", ["", " ", "0", "false", "no", "sim", "on"])
def test_anything_that_is_not_a_declared_truthy_keeps_the_default(
    monkeypatch: pytest.MonkeyPatch, value: str
) -> None:
    """Default desligado, e só três grafias ligam: valor estranho no ambiente não pode
    trocar a forma de publicar artefato por engano."""
    monkeypatch.setenv(DIRECT_WRITE_ENV, value)

    assert direct_write_enabled() is False


def test_the_variable_absent_is_the_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(DIRECT_WRITE_ENV, raising=False)

    assert direct_write_enabled() is False
