"""Testes de `scripts/check_docs.py`: paridade roadmap/feature, índice/ADR e artefatos.

O módulo é carregado por caminho (não é um pacote importável) para não mexer em
`sys.path` globalmente.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType

_REPO_ROOT = Path(__file__).resolve().parents[2]
_MODULE_PATH = _REPO_ROOT / "scripts" / "check_docs.py"


def _load_check_docs() -> ModuleType:
    spec = importlib.util.spec_from_file_location("check_docs", _MODULE_PATH)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


check_docs = _load_check_docs()


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _write_roadmap(root: Path, rows: list[tuple[str, str, str, str]]) -> None:
    """rows: (feature_id, estado, dir_name, título)."""
    lines = [
        "# Roadmap",
        "",
        "## Trabalho de engenharia em andamento",
        "",
        "| ID | Prioridade | Estado | Contrato |",
        "| --- | --- | --- | --- |",
    ]
    for feature_id, state, dir_name, title in rows:
        lines.append(
            f"| {feature_id} | HIGH | {state} | [{title}](../features/{dir_name}/feature.md) |"
        )
    lines += ["", "Texto de fechamento da seção."]
    _write(root / "docs" / "product" / "ROADMAP.md", "\n".join(lines) + "\n")


def _write_feature(
    root: Path,
    dir_name: str,
    state: str,
    *,
    evidence: bool = False,
    plan: bool = False,
    tasks: bool = False,
    include_status_heading: bool = True,
    state_line: str | None = "__default__",
) -> Path:
    feature_dir = root / "docs" / "features" / dir_name
    lines = [f"# {dir_name}", ""]
    if include_status_heading:
        lines.append("## Status")
        lines.append("")
        if state_line == "__default__":
            lines.append(f"`{state}`")
        elif state_line is not None:
            lines.append(state_line)
    _write(feature_dir / "feature.md", "\n".join(lines) + "\n")
    if evidence:
        _write(feature_dir / "evidence.md", "# Evidence\n")
    if plan:
        _write(feature_dir / "plan.md", "# Plan\n")
    if tasks:
        _write(feature_dir / "tasks" / "task-01.md", "# Task\n")
    return feature_dir


def _write_adr_index(root: Path, rows: list[tuple[str, str, str, str]]) -> None:
    """rows: (número, decisão, status, filename)."""
    lines = [
        "# ADR Index",
        "",
        "## Índice",
        "",
        "| ADR | Decisão | Status |",
        "| --- | --- | --- |",
    ]
    for number, decision, status, filename in rows:
        lines.append(f"| [{number}]({filename}) | {decision} | {status} |")
    lines += ["", "## Processo", "", "Texto do processo."]
    _write(root / "docs" / "adr" / "README.md", "\n".join(lines) + "\n")


def _write_adr(
    root: Path,
    filename: str,
    *,
    status: str = "Accepted",
    trailing_spaces: bool = False,
    include_status_line: bool = True,
) -> None:
    trailer = "  " if trailing_spaces else ""
    lines = [f"# ADR {filename}", ""]
    if include_status_line:
        lines.append(f"Status: {status}{trailer}")
    lines.append("Data: 2026-08-18")
    _write(root / "docs" / "adr" / filename, "\n".join(lines) + "\n")


def _build_baseline(root: Path) -> None:
    """Árvore sintética mínima em paridade total: 2 features + 2 ADRs."""
    _write_roadmap(
        root,
        [
            ("F-101", "DONE", "F-101-primeira", "Primeira feature"),
            ("F-102", "IN_PROGRESS", "F-102-segunda", "Segunda feature"),
        ],
    )
    _write_feature(root, "F-101-primeira", "DONE", evidence=True)
    _write_feature(root, "F-102-segunda", "IN_PROGRESS", plan=True, tasks=True)
    _write_adr_index(
        root,
        [
            ("0001", "Primeira decisão", "Accepted", "0001-primeira.md"),
            ("0002", "Segunda decisão", "Proposed", "0002-segunda.md"),
        ],
    )
    _write_adr(root, "0001-primeira.md", status="Accepted")
    _write_adr(root, "0002-segunda.md", status="Proposed")


def test_tree_in_full_parity_has_no_errors(tmp_path: Path) -> None:
    _build_baseline(tmp_path)

    assert check_docs.validate_roadmap_feature_parity(tmp_path) == []
    assert check_docs.validate_adr_index_parity(tmp_path) == []
    assert check_docs.validate_feature_artifacts(tmp_path) == []


def test_roadmap_state_diverging_from_feature_file_is_reported(tmp_path: Path) -> None:
    _build_baseline(tmp_path)
    # Diverge só o estado da tabela do roadmap; o feature.md continua IN_PROGRESS.
    _write_roadmap(
        tmp_path,
        [
            ("F-101", "DONE", "F-101-primeira", "Primeira feature"),
            ("F-102", "DONE", "F-102-segunda", "Segunda feature"),
        ],
    )

    errors = check_docs.validate_roadmap_feature_parity(tmp_path)

    assert len(errors) == 1
    assert "F-102" in errors[0]
    assert "DONE" in errors[0]
    assert "IN_PROGRESS" in errors[0]


def test_pre_spec_row_without_contract_link_is_allowed(tmp_path: Path) -> None:
    """Item READY_FOR_SPEC vive só como linha de roadmap: sem feature.md, sem erro."""
    _build_baseline(tmp_path)
    roadmap = tmp_path / "docs" / "product" / "ROADMAP.md"
    content = roadmap.read_text(encoding="utf-8").replace(
        "Texto de fechamento da seção.",
        "",
    )
    lines = content.splitlines()
    idx = max(i for i, line in enumerate(lines) if line.startswith("|"))
    lines.insert(idx + 1, "| F-900 | A DEFINIR | READY_FOR_SPEC | — |")
    roadmap.write_text("\n".join(lines) + "\n", encoding="utf-8")

    errors = check_docs.validate_roadmap_feature_parity(tmp_path)

    assert errors == []


def test_pre_spec_state_still_requires_valid_vocabulary(tmp_path: Path) -> None:
    _build_baseline(tmp_path)
    roadmap = tmp_path / "docs" / "product" / "ROADMAP.md"
    lines = roadmap.read_text(encoding="utf-8").splitlines()
    idx = max(i for i, line in enumerate(lines) if line.startswith("|"))
    lines.insert(idx + 1, "| F-901 | A DEFINIR | IN_PROGRESS | — |")
    roadmap.write_text("\n".join(lines) + "\n", encoding="utf-8")

    errors = check_docs.validate_roadmap_feature_parity(tmp_path)

    assert any("F-901" in error and "sem link" in error for error in errors)


def test_roadmap_state_outside_lifecycle_vocabulary_is_reported(tmp_path: Path) -> None:
    _build_baseline(tmp_path)
    _write_roadmap(
        tmp_path,
        [
            ("F-101", "FEITO", "F-101-primeira", "Primeira feature"),
            ("F-102", "IN_PROGRESS", "F-102-segunda", "Segunda feature"),
        ],
    )

    errors = check_docs.validate_roadmap_feature_parity(tmp_path)

    assert any("FEITO" in error and "F-101" in error for error in errors)


def test_orphan_feature_directory_without_roadmap_row_is_reported(tmp_path: Path) -> None:
    _build_baseline(tmp_path)
    _write_feature(tmp_path, "F-999-orfa", "BACKLOG")

    errors = check_docs.validate_roadmap_feature_parity(tmp_path)

    assert any("F-999-orfa" in error for error in errors)


def test_adr_file_missing_from_index_is_reported(tmp_path: Path) -> None:
    _build_baseline(tmp_path)
    _write_adr(tmp_path, "0003-orfao.md", status="Accepted")

    errors = check_docs.validate_adr_index_parity(tmp_path)

    assert any("0003-orfao.md" in error for error in errors)


def test_adr_index_status_diverging_from_file_status_is_reported(tmp_path: Path) -> None:
    _build_baseline(tmp_path)
    _write_adr_index(
        tmp_path,
        [
            ("0001", "Primeira decisão", "Deprecated", "0001-primeira.md"),
            ("0002", "Segunda decisão", "Proposed", "0002-segunda.md"),
        ],
    )

    errors = check_docs.validate_adr_index_parity(tmp_path)

    assert len(errors) == 1
    assert "0001" in errors[0]
    assert "Deprecated" in errors[0]
    assert "Accepted" in errors[0]


def test_adr_status_trailing_spaces_still_match_index_after_strip(tmp_path: Path) -> None:
    _build_baseline(tmp_path)
    _write_adr(tmp_path, "0001-primeira.md", status="Accepted", trailing_spaces=True)

    errors = check_docs.validate_adr_index_parity(tmp_path)

    assert errors == []


def test_feature_done_without_evidence_is_reported(tmp_path: Path) -> None:
    _write_feature(tmp_path, "F-201-sem-evidencia", "DONE")

    errors = check_docs.validate_feature_artifacts(tmp_path)

    assert len(errors) == 1
    assert "F-201-sem-evidencia" in errors[0]
    assert "evidence.md" in errors[0]


def test_feature_in_progress_with_plan_but_no_tasks_is_reported(tmp_path: Path) -> None:
    _write_feature(tmp_path, "F-202-sem-tasks", "IN_PROGRESS", plan=True)

    errors = check_docs.validate_feature_artifacts(tmp_path)

    assert len(errors) == 1
    assert "F-202-sem-tasks" in errors[0]
    assert "tasks" in errors[0]


def test_feature_in_progress_with_plan_and_tasks_has_no_errors(tmp_path: Path) -> None:
    _write_feature(tmp_path, "F-203-completa", "IN_PROGRESS", plan=True, tasks=True)

    errors = check_docs.validate_feature_artifacts(tmp_path)

    assert errors == []


def test_feature_missing_status_heading_reports_parsing_error(tmp_path: Path) -> None:
    _write_feature(tmp_path, "F-301-sem-status", "DONE", include_status_heading=False)

    errors = check_docs.validate_feature_artifacts(tmp_path)

    assert len(errors) == 1
    assert "F-301-sem-status" in errors[0]
    assert "Status" in errors[0]


def test_feature_state_line_without_backticks_reports_parsing_error(tmp_path: Path) -> None:
    _write_feature(tmp_path, "F-302-formato-invalido", "DONE", state_line="DONE")

    errors = check_docs.validate_feature_artifacts(tmp_path)

    assert len(errors) == 1
    assert "F-302-formato-invalido" in errors[0]
