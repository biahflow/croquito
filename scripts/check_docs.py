"""Validação leve dos contratos Markdown do repositório."""

from __future__ import annotations

import re
import sys
from pathlib import Path
from urllib.parse import unquote

ROOT = Path(__file__).resolve().parents[1]
IGNORED_PARTS = {".venv", "node_modules", "output", ".terraform"}
LINK_PATTERN = re.compile(r"(?<!!)\[[^\]]+\]\(([^)]+)\)")

LIFECYCLE_STATES = {
    "BACKLOG",
    "READY_FOR_SPEC",
    "SPEC_IN_PROGRESS",
    "READY_FOR_PLANNING",
    "PLANNING",
    "READY_FOR_BUILD",
    "IN_PROGRESS",
    "READY_FOR_REVIEW",
    "READY_FOR_HUMAN_REVIEW",
    "DONE",
    "BLOCKED",
    "CANCELLED",
}
ADR_STATES = {"Proposed", "Accepted", "Deprecated", "Superseded", "Rejected"}
# Estados anteriores ao Feature Contract: a linha do roadmap é o registro canônico e ainda
# não existe feature.md para linkar (workflows/feature.md da camada pinada).
PRE_SPEC_STATES = {"BACKLOG", "READY_FOR_SPEC", "SPEC_IN_PROGRESS"}

FEATURE_STATE_LINE = re.compile(r"^\s*`([A-Z_]+)`\s*$")
FEATURE_DIR_PREFIX = re.compile(r"^(F-\d+)")
ADR_FILENAME_PATTERN = re.compile(r"^\d{4}-.*\.md$")
TABLE_LINK_PATTERN = re.compile(r"\[[^\]]*\]\(([^)]+)\)")


def markdown_files() -> list[Path]:
    return sorted(
        path for path in ROOT.rglob("*.md") if not any(part in IGNORED_PARTS for part in path.parts)
    )


def validate_file(path: Path) -> list[str]:
    errors: list[str] = []
    content = path.read_text(encoding="utf-8")
    if content.count("```") % 2:
        errors.append(f"{path.relative_to(ROOT)}: bloco de código não fechado")

    for raw_target in LINK_PATTERN.findall(content):
        target = raw_target.strip().strip("<>").split(maxsplit=1)[0]
        if target.startswith(("http://", "https://", "mailto:", "#")):
            continue
        relative_target = unquote(target.split("#", maxsplit=1)[0])
        if not relative_target:
            continue
        resolved = (path.parent / relative_target).resolve()
        if not resolved.exists():
            errors.append(f"{path.relative_to(ROOT)}: link inexistente -> {relative_target}")
    return errors


def _table_rows_after_heading(content: str, heading: str) -> list[list[str]] | None:
    """Linhas de dados da primeira tabela Markdown após uma linha `heading` exata.

    Retorna `None` quando a linha de cabeçalho de seção ou a tabela em si não existem.
    """
    lines = content.splitlines()
    heading_index = next((i for i, line in enumerate(lines) if line.strip() == heading), None)
    if heading_index is None:
        return None
    table_lines: list[str] = []
    started = False
    for line in lines[heading_index + 1 :]:
        stripped = line.strip()
        if stripped.startswith("|"):
            table_lines.append(stripped)
            started = True
        elif started:
            break
    if len(table_lines) < 2:
        return None
    return [[cell.strip() for cell in raw.strip("|").split("|")] for raw in table_lines[2:]]


def _read_feature_status(feature_path: Path) -> str:
    """Estado declarado na primeira linha não vazia após `## Status` de um `feature.md`."""
    lines = feature_path.read_text(encoding="utf-8").splitlines()
    for index, line in enumerate(lines):
        if line.strip() == "## Status":
            for candidate in lines[index + 1 :]:
                if candidate.strip():
                    match = FEATURE_STATE_LINE.match(candidate)
                    if not match:
                        raise ValueError(
                            f"linha de estado fora do formato esperado -> {candidate.strip()!r}"
                        )
                    return match.group(1)
            raise ValueError("seção '## Status' sem linha de estado após ela")
    raise ValueError("seção '## Status' ausente")


def _read_adr_status(adr_path: Path) -> str:
    """Valor de `Status:` na primeira linha do ADR que começa com esse rótulo."""
    for line in adr_path.read_text(encoding="utf-8").splitlines():
        if line.startswith("Status:"):
            return line[len("Status:") :].strip()
    raise ValueError("linha 'Status:' ausente")


def validate_roadmap_feature_parity(root: Path = ROOT) -> list[str]:
    root = root.resolve()
    errors: list[str] = []
    roadmap_path = root / "docs" / "product" / "ROADMAP.md"
    if not roadmap_path.exists():
        return [f"{roadmap_path.relative_to(root)}: arquivo ausente"]

    content = roadmap_path.read_text(encoding="utf-8")
    rows = _table_rows_after_heading(content, "## Trabalho de engenharia em andamento")
    if rows is None:
        return [
            f"{roadmap_path.relative_to(root)}: seção ou tabela "
            "'## Trabalho de engenharia em andamento' ausente"
        ]

    table_ids: set[str] = set()
    for cells in rows:
        if len(cells) < 4:
            errors.append(
                f"{roadmap_path.relative_to(root)}: linha de tabela mal formada -> {cells}"
            )
            continue
        feature_id, state, contract_cell = cells[0], cells[2], cells[3]
        table_ids.add(feature_id)

        if state not in LIFECYCLE_STATES:
            errors.append(
                f"{roadmap_path.relative_to(root)}: estado '{state}' de {feature_id} fora do "
                "vocabulário de lifecycle"
            )

        link_match = TABLE_LINK_PATTERN.search(contract_cell)
        if not link_match:
            if state in PRE_SPEC_STATES:
                # Antes do contrato, a linha É o registro canônico; não há arquivo a parear.
                continue
            errors.append(
                f"{roadmap_path.relative_to(root)}: célula Contrato de {feature_id} sem link"
            )
            continue
        target = link_match.group(1).strip()
        feature_path = (roadmap_path.parent / target).resolve()
        if not feature_path.exists():
            errors.append(
                f"{roadmap_path.relative_to(root)}: feature.md de {feature_id} não existe -> "
                f"{target}"
            )
            continue

        try:
            feature_state = _read_feature_status(feature_path)
        except ValueError as exc:
            errors.append(f"{feature_path.relative_to(root)}: {exc}")
            continue
        if feature_state != state:
            errors.append(
                f"{roadmap_path.relative_to(root)}: {feature_id} estado '{state}' diverge de "
                f"{feature_path.relative_to(root)} estado '{feature_state}'"
            )

    features_dir = root / "docs" / "features"
    if features_dir.exists():
        for entry in sorted(features_dir.iterdir()):
            if not entry.is_dir():
                continue
            dir_match = FEATURE_DIR_PREFIX.match(entry.name)
            feature_file = entry / "feature.md"
            if not dir_match or not feature_file.exists():
                continue
            if dir_match.group(1) not in table_ids:
                errors.append(
                    f"{feature_file.relative_to(root)}: diretório de feature sem linha "
                    "correspondente no roadmap"
                )
    return errors


def validate_adr_index_parity(root: Path = ROOT) -> list[str]:
    root = root.resolve()
    errors: list[str] = []
    index_path = root / "docs" / "adr" / "README.md"
    if not index_path.exists():
        return [f"{index_path.relative_to(root)}: arquivo ausente"]

    content = index_path.read_text(encoding="utf-8")
    rows = _table_rows_after_heading(content, "## Índice")
    if rows is None:
        return [f"{index_path.relative_to(root)}: seção ou tabela '## Índice' ausente"]

    indexed_numbers: set[str] = set()
    for cells in rows:
        if len(cells) < 3:
            errors.append(f"{index_path.relative_to(root)}: linha de tabela mal formada -> {cells}")
            continue
        adr_cell, status = cells[0], cells[2]

        link_match = TABLE_LINK_PATTERN.search(adr_cell)
        number_match = re.search(r"\d{4}", adr_cell)
        if not link_match or not number_match:
            errors.append(f"{index_path.relative_to(root)}: linha de ADR mal formada -> {adr_cell}")
            continue
        number = number_match.group(0)
        indexed_numbers.add(number)

        if status not in ADR_STATES:
            errors.append(
                f"{index_path.relative_to(root)}: status '{status}' do ADR {number} fora do "
                "vocabulário"
            )

        target = link_match.group(1).strip()
        adr_path = (index_path.parent / target).resolve()
        if not adr_path.exists():
            errors.append(f"{index_path.relative_to(root)}: ADR {number} não existe -> {target}")
            continue

        try:
            adr_status = _read_adr_status(adr_path)
        except ValueError as exc:
            errors.append(f"{adr_path.relative_to(root)}: {exc}")
            continue
        if adr_status != status:
            errors.append(
                f"{index_path.relative_to(root)}: ADR {number} status '{status}' diverge de "
                f"{adr_path.relative_to(root)} status '{adr_status}'"
            )

    adr_dir = root / "docs" / "adr"
    for entry in sorted(adr_dir.iterdir()):
        if entry.name == "README.md" or not entry.is_file():
            continue
        if not ADR_FILENAME_PATTERN.match(entry.name):
            continue
        if entry.name[:4] not in indexed_numbers:
            errors.append(f"{entry.relative_to(root)}: ADR fora do índice")
    return errors


def validate_feature_artifacts(root: Path = ROOT) -> list[str]:
    root = root.resolve()
    errors: list[str] = []
    features_dir = root / "docs" / "features"
    if not features_dir.exists():
        return errors

    for entry in sorted(features_dir.iterdir()):
        if not entry.is_dir():
            continue
        feature_file = entry / "feature.md"
        if not feature_file.exists():
            continue
        try:
            state = _read_feature_status(feature_file)
        except ValueError as exc:
            errors.append(f"{feature_file.relative_to(root)}: {exc}")
            continue

        if state in {"DONE", "READY_FOR_HUMAN_REVIEW"}:
            if not (entry / "evidence.md").exists():
                errors.append(
                    f"{feature_file.relative_to(root)}: estado '{state}' exige evidence.md"
                )
        elif state in {"READY_FOR_BUILD", "IN_PROGRESS", "READY_FOR_REVIEW"}:
            if not (entry / "plan.md").exists():
                errors.append(f"{feature_file.relative_to(root)}: estado '{state}' exige plan.md")
            tasks_dir = entry / "tasks"
            if not (tasks_dir.is_dir() and any(tasks_dir.glob("*.md"))):
                errors.append(
                    f"{feature_file.relative_to(root)}: estado '{state}' exige ao menos um "
                    "arquivo em tasks/*.md"
                )
    return errors


def main() -> int:
    files = markdown_files()
    errors = [error for path in files for error in validate_file(path)]
    errors += validate_roadmap_feature_parity()
    errors += validate_adr_index_parity()
    errors += validate_feature_artifacts()
    if errors:
        print("\n".join(errors), file=sys.stderr)
        return 1
    print(f"Documentação válida: {len(files)} arquivos Markdown, paridade de lifecycle verificada.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
