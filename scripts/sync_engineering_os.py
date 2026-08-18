"""Espelha a camada global da Engineering OS dentro deste repositório (ADR-0034).

O Engineering OS vive num checkout git local do operador, sem remote e sem tags. CI,
colaborador novo e agente em nuvem não alcançam esse caminho, então a camada global é
vendorizada em `docs/engineering-os/` e pinada pelo commit de origem registrado no
`PROVENANCE.md`.

Ressincronizar é ato deliberado: o script recusa origem suja, reescreve o espelho inteiro e
deixa o diff para revisão como qualquer outra mudança.

Uso:

    uv run python scripts/sync_engineering_os.py
    CROQUITO_EOS_SOURCE=/outro/checkout uv run python scripts/sync_engineering_os.py
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DESTINATION = ROOT / "docs" / "engineering-os"
DEFAULT_SOURCE = "~/workspace/engineeringOS"
PROVENANCE_NAME = "PROVENANCE.md"
# Um `.gitignore` aninhado mudaria a semântica de ignore do croquito dentro do diretório
# vendorizado; o espelho é documentação, não um checkout funcional.
EXCLUDED_NAMES = {".gitignore"}
# Campos voláteis do PROVENANCE: reescrever o arquivo só para trocar a data produziria
# diff sem fato novo. O snapshot continua sendo o da data em que entrou.
VOLATILE_PREFIXES = ("Última revisão:", "| Sincronizado em")


class SyncFailure(RuntimeError):
    """A origem da Engineering OS não está em estado sincronizável."""


def source_path() -> Path:
    raw = os.getenv("CROQUITO_EOS_SOURCE") or DEFAULT_SOURCE
    return Path(raw).expanduser().resolve()


def _git(source: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(source), *args],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise SyncFailure(f"git {' '.join(args)} falhou em {source}: {result.stderr.strip()}")
    return result.stdout


def _display_path(path: Path) -> str:
    """Colapsa o home do operador: o caminho é informação de origem, não endereço da máquina."""
    home = Path.home()
    try:
        return f"~/{path.relative_to(home)}"
    except ValueError:
        return str(path)


def validate_source(source: Path) -> None:
    if not source.is_dir():
        raise SyncFailure(
            f"origem inexistente: {source}. Aponte CROQUITO_EOS_SOURCE para o checkout "
            "do engineeringOS."
        )
    if not (source / ".git").exists():
        raise SyncFailure(f"origem não é um repositório git: {source}")


def worktree_state(source: Path, allow_dirty: bool) -> str:
    dirty = bool(_git(source, "status", "--porcelain").strip())
    if dirty and not allow_dirty:
        raise SyncFailure(
            f"árvore suja em {source}: commit ou descarte as mudanças antes de vendorizar, "
            "ou rode com --allow-dirty para registrar o estado sujo no PROVENANCE."
        )
    return "dirty" if dirty else "clean"


def tracked_files(source: Path) -> list[Path]:
    listing = _git(source, "ls-files", "-z").split("\0")
    return sorted(
        Path(entry) for entry in listing if entry and Path(entry).name not in EXCLUDED_NAMES
    )


def _copy(origin: Path, target: Path) -> bool:
    """Copia preservando o modo. Devolve False quando o destino já é idêntico."""
    payload = origin.read_bytes()
    mode = origin.stat().st_mode
    if target.exists() and target.read_bytes() == payload and target.stat().st_mode == mode:
        return False
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(payload)
    shutil.copymode(origin, target)
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


def provenance_text(source: Path, commit: str, state: str, count: int, today: date) -> str:
    return f"""# Proveniência do snapshot da Engineering OS

Status: Generated
Responsável: Engineering
Última revisão: {today.isoformat()}

Este diretório é um **espelho pinado** da camada global da Engineering OS, vendorizado para
que CI, colaborador novo e agente em nuvem enxerguem as mesmas regras que o operador carrega
por fora ([ADR-0034](../adr/0034-camada-global-vendorizada-e-pinada.md)). Os arquivos são
cópia fiel da origem, em inglês, e **não são editados aqui** — nem este registro, que é
gerado pelo script.

| Campo | Valor |
|---|---|
| Commit de origem | `{commit}` |
| Estado da origem | `{state}` |
| Sincronizado em | {today.isoformat()} |
| Caminho de origem | `{_display_path(source)}` |
| Arquivos espelhados | {count} |

## Ressincronizar

```bash
uv run python scripts/sync_engineering_os.py
```

Ressincronizar é ato deliberado, não rotina automática: o script recusa origem com árvore
suja e o diff resultante é revisado como qualquer outra mudança do repositório. Enquanto
não houver nova sincronização, o commit acima é a versão da camada global que vale para
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


def synchronize(allow_dirty: bool) -> int:
    source = source_path()
    validate_source(source)
    state = worktree_state(source, allow_dirty)
    commit = _git(source, "rev-parse", "HEAD").strip()
    files = tracked_files(source)
    if not files:
        raise SyncFailure(f"origem sem arquivos rastreados: {source}")

    copied = [relative for relative in files if _copy(source / relative, DESTINATION / relative)]
    removed = _prune(set(files))
    provenance = provenance_text(source, commit, state, len(files), date.today())
    rewritten = write_provenance(provenance)

    for relative in copied:
        print(f"atualizado: {relative}")
    for relative in removed:
        print(f"removido: {relative}")
    print(
        f"Engineering OS {commit[:7]} ({state}): {len(files)} arquivos espelhados, "
        f"{len(copied)} atualizados, {len(removed)} removidos, "
        f"{len(files) - len(copied)} inalterados, "
        f"PROVENANCE {'reescrito' if rewritten else 'inalterado'}."
    )
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--allow-dirty",
        action="store_true",
        help="aceita origem com árvore suja; o estado fica registrado no PROVENANCE.",
    )
    arguments = parser.parse_args()
    try:
        return synchronize(allow_dirty=arguments.allow_dirty)
    except SyncFailure as error:
        print(str(error), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
