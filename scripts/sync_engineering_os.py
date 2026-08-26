"""Espelha a camada global da Engineering OS dentro deste repositório (ADR-0034, ADR-0052).

A Engineering OS é publicada em `https://github.com/biahflow/engineeringOS` e versionada por
tag SemVer. Este script busca a tag pinada, espelha os arquivos rastreados dela em
`docs/engineering-os/` e registra o pino no `PROVENANCE.md`.

O pino é a constante `PINNED_TAG`. Avançá-lo é um diff de uma linha, revisado como qualquer
outra mudança do repositório; enquanto ele não muda, aquela tag **é** a camada global que vale
aqui. O script recusa uma referência que não seja tag do remoto: branch se move, e um pino que
se move não é pino.

Uso:

    uv run python scripts/sync_engineering_os.py
    uv run python scripts/sync_engineering_os.py --tag v0.2.0
    CROQUITO_EOS_ORIGIN=/caminho/para/fork uv run python scripts/sync_engineering_os.py
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DESTINATION = ROOT / "docs" / "engineering-os"
DEFAULT_ORIGIN = "https://github.com/biahflow/engineeringOS.git"
PINNED_TAG = "v0.1.0"
PROVENANCE_NAME = "PROVENANCE.md"
# Um `.gitignore` aninhado mudaria a semântica de ignore do croquito dentro do diretório
# vendorizado; o espelho é documentação, não um checkout funcional.
EXCLUDED_NAMES = {".gitignore"}
# Campos voláteis do PROVENANCE: reescrever o arquivo só para trocar a data produziria
# diff sem fato novo. O snapshot continua sendo o da data em que entrou.
VOLATILE_PREFIXES = ("Última revisão:", "| Sincronizado em")


class SyncFailure(RuntimeError):
    """A origem da Engineering OS não está em estado sincronizável."""


def origin() -> str:
    return os.getenv("CROQUITO_EOS_ORIGIN") or DEFAULT_ORIGIN


def _git(*args: str) -> str:
    result = subprocess.run(["git", *args], capture_output=True, text=True, check=False)
    if result.returncode != 0:
        raise SyncFailure(f"git {' '.join(args)} falhou: {result.stderr.strip()}")
    return result.stdout


def resolve_tag(source: str, tag: str) -> str:
    """Resolve a tag para o commit que ela aponta, recusando qualquer coisa que não seja tag.

    Tag anotada tem dois refs no remoto: o objeto de tag e o commit sob `^{}`. O pino é o
    commit — é ele que o `PROVENANCE` declara e que alguém consegue conferir.
    """
    listing = _git("ls-remote", "--tags", source, f"refs/tags/{tag}", f"refs/tags/{tag}^{{}}")
    resolved: dict[str, str] = {}
    for line in listing.splitlines():
        commit, _, reference = line.partition("\t")
        resolved[reference.strip()] = commit.strip()
    if not resolved:
        raise SyncFailure(
            f"tag inexistente no remoto: {tag} em {source}. O pino é uma tag SemVer "
            "publicada; branch se move e não serve de pino."
        )
    return resolved.get(f"refs/tags/{tag}^{{}}") or resolved[f"refs/tags/{tag}"]


def clone(source: str, tag: str, into: Path) -> None:
    _git("clone", "--depth", "1", "--branch", tag, "--quiet", source, str(into))


def tracked_files(checkout: Path) -> list[Path]:
    listing = _git("-C", str(checkout), "ls-files", "-z").split("\0")
    return sorted(
        Path(entry) for entry in listing if entry and Path(entry).name not in EXCLUDED_NAMES
    )


def _copy(source: Path, target: Path) -> bool:
    """Copia preservando o modo. Devolve False quando o destino já é idêntico."""
    payload = source.read_bytes()
    mode = source.stat().st_mode
    if target.exists() and target.read_bytes() == payload and target.stat().st_mode == mode:
        return False
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(payload)
    shutil.copymode(source, target)
    return True


def _prune(expected: set[Path]) -> list[Path]:
    removed: list[Path] = []
    if not DESTINATION.exists():
        return removed
    for path in sorted(DESTINATION.rglob("*")):
        if not path.is_file():
            continue
        relative = path.relative_to(DESTINATION)
        if relative == Path(PROVENANCE_NAME) or relative in expected:
            continue
        path.unlink()
        removed.append(relative)
    for directory in sorted(DESTINATION.rglob("*"), reverse=True):
        if directory.is_dir() and not any(directory.iterdir()):
            directory.rmdir()
    return removed


def provenance_text(source: str, tag: str, commit: str, count: int, today: date) -> str:
    return f"""# Proveniência do snapshot da Engineering OS

Status: Generated
Responsável: Engineering
Última revisão: {today.isoformat()}

Este diretório é um **espelho pinado** da camada global da Engineering OS, vendorizado para
que CI, colaborador novo e agente em nuvem enxerguem as mesmas regras que o operador carrega
por fora ([ADR-0034](../adr/0034-camada-global-vendorizada-e-pinada.md), pino por tag na
[ADR-0052](../adr/0052-pino-da-camada-global-por-tag-do-remoto.md)). Os arquivos são cópia
fiel da origem, em inglês, e **não são editados aqui** — nem este registro, que é gerado pelo
script.

| Campo | Valor |
|---|---|
| Origem | `{source}` |
| Tag de origem | `{tag}` |
| Commit de origem | `{commit}` |
| Sincronizado em | {today.isoformat()} |
| Arquivos espelhados | {count} |

## Ressincronizar

Avançar o pino é trocar `PINNED_TAG` em `scripts/sync_engineering_os.py` e rodar:

```bash
uv run python scripts/sync_engineering_os.py
```

Ressincronizar é ato deliberado, não rotina automática: o script recusa referência que não
seja tag publicada, e o diff resultante é revisado como qualquer outra mudança do repositório.
Enquanto não houver nova sincronização, a tag acima é a versão da camada global que vale para
este repositório.
"""


def _stable(text: str) -> str:
    return "\n".join(line for line in text.splitlines() if not line.startswith(VOLATILE_PREFIXES))


def write_provenance(text: str) -> bool:
    target = DESTINATION / PROVENANCE_NAME
    if target.exists() and _stable(target.read_text(encoding="utf-8")) == _stable(text):
        return False
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8")
    return True


def synchronize(tag: str) -> int:
    source = origin()
    commit = resolve_tag(source, tag)

    with tempfile.TemporaryDirectory(prefix="eos-sync-") as scratch:
        checkout = Path(scratch) / "engineeringOS"
        clone(source, tag, checkout)
        files = tracked_files(checkout)
        if not files:
            raise SyncFailure(f"origem sem arquivos rastreados: {source}@{tag}")
        copied = [
            relative for relative in files if _copy(checkout / relative, DESTINATION / relative)
        ]

    removed = _prune(set(files))
    rewritten = write_provenance(provenance_text(source, tag, commit, len(files), date.today()))

    for relative in copied:
        print(f"atualizado: {relative}")
    for relative in removed:
        print(f"removido: {relative}")
    print(
        f"Engineering OS {tag} ({commit[:7]}): {len(files)} arquivos espelhados, "
        f"{len(copied)} atualizados, {len(removed)} removidos, "
        f"{len(files) - len(copied)} inalterados, "
        f"PROVENANCE {'reescrito' if rewritten else 'inalterado'}."
    )
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--tag",
        default=PINNED_TAG,
        help=f"tag da Engineering OS a espelhar; por padrão o pino {PINNED_TAG}.",
    )
    arguments = parser.parse_args()
    try:
        return synchronize(tag=arguments.tag)
    except SyncFailure as error:
        print(str(error), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
