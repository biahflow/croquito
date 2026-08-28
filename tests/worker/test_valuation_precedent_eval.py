"""Leitura do que já está gravado das rodadas de orçamento, para medir precedente
(F-044 T1): `estimate_rounds.csv` + `estimate_round_revisions.csv` (entrada A), um JSON
por praça (entrada B), uma planilha `.xlsx` de memória de cálculo real (entrada C,
escopo ampliado), e o comando `precedent-eval` que liga as três ao domínio puro de
`croquito_valuation.precedent`.
"""

from __future__ import annotations

import csv
import json
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pytest
from openpyxl import Workbook

from croquito_valuation.assignment import CodeAssignment, CodeAssignmentSet
from croquito_valuation.errors import ValuationValidationError
from croquito_valuation.models import ReviewerDecision
from croquito_valuation.takeoff import (
    PlateBox,
    PlateEvidence,
    TakeoffItem,
    TakeoffItemStatus,
    TakeoffPacket,
)
from croquito_worker.valuation.cli import main
from croquito_worker.valuation.precedent_eval import (
    MEMORIA_PRICE_SOURCE,
    REASON_MISSING_WORKSITE_KEY,
    REASON_NO_CONFIRMED_ASSIGNMENTS,
    REASON_NO_TAKEOFF_PACKET,
    REASON_UNREADABLE_CODE_ASSIGNMENTS,
    REPORT_FILENAME,
    parse_memoria_spec,
    read_worksites_from_memoria,
    read_worksites_from_revision_dir,
    read_worksites_from_rounds_csv,
    run_precedent_eval,
)

_PLATE_ID = "praca-sintetica-prancha-01"
_SHA = "a" * 64
_DECIDED_AT = datetime(2026, 1, 1, tzinfo=UTC)


def _decision(suffix: str) -> ReviewerDecision:
    return ReviewerDecision(
        decision_id=f"vd_{suffix}",
        action="confirm",
        reviewer_id="orcamentista-eval",
        reviewer_role="orcamentista",
        decided_at=_DECIDED_AT,
    )


def _takeoff_item(suffix: str, label: str) -> TakeoffItem:
    return TakeoffItem(
        id=f"ti_{suffix}",
        evidence=PlateEvidence(
            plate_id=_PLATE_ID,
            page_number=1,
            image_sha256=_SHA,
            bbox=PlateBox(left=1, top=1, right=10, bottom=10),
        ),
        raw_text=label,
        label=label,
        quantity=Decimal("10.00"),
        unit="m2",
        source="legend_extraction",
        extractor="fixture",
        extractor_version="1.0.0",
        status=TakeoffItemStatus.CONFIRMED,
        decision=_decision(suffix),
    )


def _packet(*items: TakeoffItem) -> TakeoffPacket:
    return TakeoffPacket(
        plate_id=_PLATE_ID,
        page_number=1,
        image_sha256=_SHA,
        source_pdf_sha256=_SHA,
        items=list(items),
        safety_notes=["nota 1", "nota 2"],
    )


def _assignment(
    item_suffix: str, code: str, decision_suffix: str, catalog_sha256: str | None
) -> CodeAssignment:
    return CodeAssignment(
        item_id=f"ti_{item_suffix}",
        status="confirmed",
        code=code,
        catalog_sha256=catalog_sha256,
        unit_compatible=True,
        decision=_decision(decision_suffix),
    )


def _assignment_set(*assignments: CodeAssignment) -> CodeAssignmentSet:
    return CodeAssignmentSet(
        schema_version="1.0.0",
        plate_id=_PLATE_ID,
        page_number=1,
        image_sha256=_SHA,
        catalog_sha256=_SHA,
        assignments=list(assignments),
        safety_notes=["nota 1", "nota 2"],
    )


def _write_csv(path: Path, fieldnames: list[str], rows: list[dict[str, str]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _write_rounds_csv(path: Path, rows: list[dict[str, str]]) -> None:
    _write_csv(path, ["id", "worksite_key"], rows)


def _write_revisions_csv(path: Path, rows: list[dict[str, str]]) -> None:
    _write_csv(path, ["round_id", "version", "takeoff_packet_json", "code_assignments_json"], rows)


# --------------------------------------------------------------------------------------
# Entrada A: estimate_rounds.csv + estimate_round_revisions.csv
# --------------------------------------------------------------------------------------


def test_reads_two_worksites_and_skips_the_round_without_assignments(tmp_path: Path) -> None:
    packet_a = _packet(_takeoff_item("0000000000000001", "PISO EM CONCRETO"))
    assignments_a = _assignment_set(
        _assignment("0000000000000001", "X001", "0000000000000011", _SHA)
    )
    packet_b = _packet(_takeoff_item("0000000000000002", "PISO EM CONCRETO"))
    assignments_b = _assignment_set(
        _assignment("0000000000000002", "X001", "0000000000000012", _SHA)
    )

    rounds_path = tmp_path / "estimate_rounds.csv"
    revisions_path = tmp_path / "estimate_round_revisions.csv"
    _write_rounds_csv(
        rounds_path,
        [
            {"id": "round-a", "worksite_key": "praca-a"},
            {"id": "round-b", "worksite_key": "praca-b"},
            {"id": "round-c", "worksite_key": "praca-c"},
        ],
    )
    _write_revisions_csv(
        revisions_path,
        [
            {
                "round_id": "round-a",
                "version": "1",
                "takeoff_packet_json": packet_a.model_dump_json(),
                "code_assignments_json": assignments_a.model_dump_json(),
            },
            {
                "round_id": "round-b",
                "version": "1",
                "takeoff_packet_json": "",
                "code_assignments_json": "",
            },
            {
                "round_id": "round-b",
                "version": "2",
                "takeoff_packet_json": packet_b.model_dump_json(),
                "code_assignments_json": assignments_b.model_dump_json(),
            },
            {
                "round_id": "round-c",
                "version": "1",
                "takeoff_packet_json": "",
                "code_assignments_json": "null",
            },
        ],
    )

    worksites, skipped = read_worksites_from_rounds_csv(rounds_path, revisions_path)

    assert [worksite.worksite_key for worksite in worksites] == ["praca-a", "praca-b"]
    assert len(skipped) == 1
    assert skipped[0].worksite_key == "praca-c"
    assert skipped[0].reason == REASON_NO_CONFIRMED_ASSIGNMENTS


def test_picks_the_highest_version_with_non_empty_code_assignments(tmp_path: Path) -> None:
    packet_old = _packet(_takeoff_item("0000000000000004", "ROTULO ERRADO"))
    assignments_old = _assignment_set(
        _assignment("0000000000000004", "CODE-ERRADO", "0000000000000014", _SHA)
    )
    packet_new = _packet(_takeoff_item("0000000000000009", "ROTULO CERTO"))
    assignments_new = _assignment_set(
        _assignment("0000000000000009", "CODE-CERTO", "0000000000000019", _SHA)
    )

    rounds_path = tmp_path / "estimate_rounds.csv"
    revisions_path = tmp_path / "estimate_round_revisions.csv"
    _write_rounds_csv(rounds_path, [{"id": "round-a", "worksite_key": "praca-a"}])
    _write_revisions_csv(
        revisions_path,
        [
            {
                "round_id": "round-a",
                "version": "9",
                "takeoff_packet_json": packet_new.model_dump_json(),
                "code_assignments_json": assignments_new.model_dump_json(),
            },
            {
                "round_id": "round-a",
                "version": "4",
                "takeoff_packet_json": packet_old.model_dump_json(),
                "code_assignments_json": assignments_old.model_dump_json(),
            },
        ],
    )

    worksites, skipped = read_worksites_from_rounds_csv(rounds_path, revisions_path)

    assert skipped == []
    assert len(worksites) == 1
    observation = worksites[0].observations[0]
    assert observation.label == "ROTULO CERTO"
    assert observation.codes == frozenset({"CODE-CERTO"})


def test_skips_when_the_selected_revision_has_no_takeoff_packet(tmp_path: Path) -> None:
    assignments = _assignment_set(_assignment("0000000000000001", "X001", "0000000000000011", _SHA))

    rounds_path = tmp_path / "estimate_rounds.csv"
    revisions_path = tmp_path / "estimate_round_revisions.csv"
    _write_rounds_csv(rounds_path, [{"id": "round-a", "worksite_key": "praca-a"}])
    _write_revisions_csv(
        revisions_path,
        [
            {
                "round_id": "round-a",
                "version": "1",
                "takeoff_packet_json": "",
                "code_assignments_json": assignments.model_dump_json(),
            }
        ],
    )

    worksites, skipped = read_worksites_from_rounds_csv(rounds_path, revisions_path)

    assert worksites == []
    assert len(skipped) == 1
    assert skipped[0].reason == REASON_NO_TAKEOFF_PACKET


def test_skips_an_unreadable_code_assignments_blob(tmp_path: Path) -> None:
    packet = _packet(_takeoff_item("0000000000000001", "PISO EM CONCRETO"))

    rounds_path = tmp_path / "estimate_rounds.csv"
    revisions_path = tmp_path / "estimate_round_revisions.csv"
    _write_rounds_csv(rounds_path, [{"id": "round-a", "worksite_key": "praca-a"}])
    _write_revisions_csv(
        revisions_path,
        [
            {
                "round_id": "round-a",
                "version": "1",
                "takeoff_packet_json": packet.model_dump_json(),
                "code_assignments_json": '{"schema_version": "1.0.0"}',
            }
        ],
    )

    worksites, skipped = read_worksites_from_rounds_csv(rounds_path, revisions_path)

    assert worksites == []
    assert len(skipped) == 1
    assert skipped[0].reason == REASON_UNREADABLE_CODE_ASSIGNMENTS


def test_a_round_absent_from_the_revisions_csv_is_skipped_too(tmp_path: Path) -> None:
    rounds_path = tmp_path / "estimate_rounds.csv"
    revisions_path = tmp_path / "estimate_round_revisions.csv"
    _write_rounds_csv(rounds_path, [{"id": "round-a", "worksite_key": "praca-a"}])
    _write_revisions_csv(revisions_path, [])

    worksites, skipped = read_worksites_from_rounds_csv(rounds_path, revisions_path)

    assert worksites == []
    assert skipped[0].reason == REASON_NO_CONFIRMED_ASSIGNMENTS


# --------------------------------------------------------------------------------------
# Entrada B: um JSON por praça num diretório
# --------------------------------------------------------------------------------------


def test_reads_worksites_from_a_directory_of_json_files(tmp_path: Path) -> None:
    packet_a = _packet(_takeoff_item("0000000000000001", "PISO EM CONCRETO"))
    assignments_a = _assignment_set(
        _assignment("0000000000000001", "X001", "0000000000000011", _SHA)
    )
    packet_b = _packet(_takeoff_item("0000000000000002", "PISO EM CONCRETO"))
    assignments_b = _assignment_set(
        _assignment("0000000000000002", "X001", "0000000000000012", _SHA)
    )

    directory = tmp_path / "revisions"
    directory.mkdir()
    (directory / "praca-a.json").write_text(
        json.dumps(
            {
                "worksite_key": "praca-a",
                "takeoff_packet": packet_a.model_dump(mode="json"),
                "code_assignments": assignments_a.model_dump(mode="json"),
            }
        ),
        encoding="utf-8",
    )
    (directory / "praca-b.json").write_text(
        json.dumps(
            {
                "worksite_key": "praca-b",
                "takeoff_packet": packet_b.model_dump(mode="json"),
                "code_assignments": assignments_b.model_dump(mode="json"),
            }
        ),
        encoding="utf-8",
    )
    (directory / "broken.json").write_text(json.dumps({"takeoff_packet": {}}), encoding="utf-8")

    worksites, skipped = read_worksites_from_revision_dir(directory)

    assert [worksite.worksite_key for worksite in worksites] == ["praca-a", "praca-b"]
    assert len(skipped) == 1
    assert skipped[0].reason == REASON_MISSING_WORKSITE_KEY


# --------------------------------------------------------------------------------------
# run_precedent_eval: as duas entradas, recusas e publicação
# --------------------------------------------------------------------------------------


def _two_worksite_csv_inputs(tmp_path: Path) -> tuple[Path, Path]:
    packet_a = _packet(_takeoff_item("0000000000000001", "PISO EM CONCRETO"))
    assignments_a = _assignment_set(
        _assignment("0000000000000001", "X001", "0000000000000011", _SHA)
    )
    packet_b = _packet(_takeoff_item("0000000000000002", "PISO EM CONCRETO"))
    assignments_b = _assignment_set(
        _assignment("0000000000000002", "X001", "0000000000000012", _SHA)
    )
    rounds_path = tmp_path / "estimate_rounds.csv"
    revisions_path = tmp_path / "estimate_round_revisions.csv"
    _write_rounds_csv(
        rounds_path,
        [
            {"id": "round-a", "worksite_key": "praca-a"},
            {"id": "round-b", "worksite_key": "praca-b"},
        ],
    )
    _write_revisions_csv(
        revisions_path,
        [
            {
                "round_id": "round-a",
                "version": "1",
                "takeoff_packet_json": packet_a.model_dump_json(),
                "code_assignments_json": assignments_a.model_dump_json(),
            },
            {
                "round_id": "round-b",
                "version": "1",
                "takeoff_packet_json": packet_b.model_dump_json(),
                "code_assignments_json": assignments_b.model_dump_json(),
            },
        ],
    )
    return rounds_path, revisions_path


def test_run_precedent_eval_publishes_the_report_from_two_worksites(tmp_path: Path) -> None:
    rounds_path, revisions_path = _two_worksite_csv_inputs(tmp_path)
    output_dir = tmp_path / "out"

    report, report_path = run_precedent_eval(
        rounds_path=rounds_path,
        revisions_path=revisions_path,
        revision_dir=None,
        output_dir=output_dir,
    )

    assert report.worksites_used == ("praca-a", "praca-b")
    assert report_path == output_dir / REPORT_FILENAME
    assert report_path.is_file()
    published = json.loads(report_path.read_text(encoding="utf-8"))
    assert published["worksites_used"] == ["praca-a", "praca-b"]


def test_run_precedent_eval_refuses_when_only_rounds_is_given(tmp_path: Path) -> None:
    rounds_path, _ = _two_worksite_csv_inputs(tmp_path)

    with pytest.raises(ValuationValidationError) as excinfo:
        run_precedent_eval(
            rounds_path=rounds_path,
            revisions_path=None,
            revision_dir=None,
            output_dir=tmp_path / "out",
        )

    assert excinfo.value.code == "PRECEDENT_INPUT_INCOMPLETE"


@pytest.mark.parametrize(
    "give_csv, give_dir",
    [(False, False), (True, True)],
    ids=["neither_input", "both_inputs"],
)
def test_run_precedent_eval_refuses_ambiguous_input(
    tmp_path: Path, give_csv: bool, give_dir: bool
) -> None:
    rounds_path, revisions_path = _two_worksite_csv_inputs(tmp_path) if give_csv else (None, None)
    revision_dir = tmp_path if give_dir else None

    with pytest.raises(ValuationValidationError) as excinfo:
        run_precedent_eval(
            rounds_path=rounds_path,
            revisions_path=revisions_path,
            revision_dir=revision_dir,
            output_dir=tmp_path / "out",
        )

    assert excinfo.value.code == "PRECEDENT_INPUT_AMBIGUOUS"


def test_run_precedent_eval_refuses_with_only_one_usable_worksite(tmp_path: Path) -> None:
    packet_a = _packet(_takeoff_item("0000000000000001", "PISO EM CONCRETO"))
    assignments_a = _assignment_set(
        _assignment("0000000000000001", "X001", "0000000000000011", _SHA)
    )
    rounds_path = tmp_path / "estimate_rounds.csv"
    revisions_path = tmp_path / "estimate_round_revisions.csv"
    _write_rounds_csv(
        rounds_path,
        [
            {"id": "round-a", "worksite_key": "praca-a"},
            {"id": "round-b", "worksite_key": "praca-b"},
        ],
    )
    _write_revisions_csv(
        revisions_path,
        [
            {
                "round_id": "round-a",
                "version": "1",
                "takeoff_packet_json": packet_a.model_dump_json(),
                "code_assignments_json": assignments_a.model_dump_json(),
            },
            {
                "round_id": "round-b",
                "version": "1",
                "takeoff_packet_json": "",
                "code_assignments_json": "",
            },
        ],
    )
    output_dir = tmp_path / "out"

    with pytest.raises(ValuationValidationError) as excinfo:
        run_precedent_eval(
            rounds_path=rounds_path,
            revisions_path=revisions_path,
            revision_dir=None,
            output_dir=output_dir,
        )

    assert excinfo.value.code == "PRECEDENT_NOT_ENOUGH_WORKSITES"
    assert excinfo.value.details["worksite_count"] == 1
    assert not output_dir.exists()


# --------------------------------------------------------------------------------------
# CLI: `precedent-eval`
# --------------------------------------------------------------------------------------


def test_cli_precedent_eval_succeeds_and_prints_a_readable_summary(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    rounds_path, revisions_path = _two_worksite_csv_inputs(tmp_path)
    output_dir = tmp_path / "out"

    exit_code = main(
        [
            "precedent-eval",
            "--rounds",
            str(rounds_path),
            "--revisions",
            str(revisions_path),
            "--output",
            str(output_dir),
        ]
    )

    assert exit_code == 0
    captured = capsys.readouterr()
    assert "praças usadas: 2" in captured.out
    assert (output_dir / REPORT_FILENAME).is_file()


def test_cli_precedent_eval_refuses_closed_with_a_stable_json_line(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    rounds_path, _ = _two_worksite_csv_inputs(tmp_path)
    output_dir = tmp_path / "out"

    exit_code = main(
        [
            "precedent-eval",
            "--rounds",
            str(rounds_path),
            "--output",
            str(output_dir),
        ]
    )

    assert exit_code == 2
    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert payload["refused"] == "PRECEDENT_INPUT_INCOMPLETE"
    assert not output_dir.exists()


# --------------------------------------------------------------------------------------
# Entrada C: --memoria <arquivo.xlsx>:<aba> (escopo ampliado, planilha real de orçamento)
# --------------------------------------------------------------------------------------


def _write_memoria_workbook(path: Path, sheet_name: str, rows: list[list[object]]) -> None:
    workbook = Workbook()
    worksheet = workbook.active
    assert worksheet is not None
    worksheet.title = sheet_name
    for row in rows:
        worksheet.append(row)
    workbook.save(path)


def test_parse_memoria_spec_splits_on_the_last_colon() -> None:
    path, sheet = parse_memoria_spec("/tmp/praca-a.xlsx:MEMÓRIA DE CÁLCULO")
    assert path == Path("/tmp/praca-a.xlsx")
    assert sheet == "MEMÓRIA DE CÁLCULO"


@pytest.mark.parametrize("raw", ["", "sem-separador", ":sem-caminho", "arquivo.xlsx:"], ids=repr)
def test_parse_memoria_spec_refuses_malformed_values(raw: str) -> None:
    with pytest.raises(ValuationValidationError) as excinfo:
        parse_memoria_spec(raw)
    assert excinfo.value.code == "PRECEDENT_MEMORIA_SPEC_INVALID"


def test_read_worksites_from_memoria_builds_worksites_and_counts_unlabeled_blocks(
    tmp_path: Path,
) -> None:
    path_a = tmp_path / "praca-a.xlsx"
    _write_memoria_workbook(
        path_a,
        "ABA A",
        [
            [None, "01.10", "AD39050218(A)", "descrição do código"],
            [None, None, None, "VIGIA"],
            [None, "01.11", "ET04600200(/)", "descrição do código 2"],  # sem rótulo
        ],
    )
    path_b = tmp_path / "praca-b.xlsx"
    _write_memoria_workbook(
        path_b,
        "ABA B",
        [
            [None, "01.10", "AD39050218(A)", "descrição do código"],
            [None, None, None, "VIGIA"],
        ],
    )

    worksites, sources = read_worksites_from_memoria([f"{path_a}:ABA A", f"{path_b}:ABA B"])

    assert [worksite.worksite_key for worksite in worksites] == [
        f"{path_a.name}::ABA A",
        f"{path_b.name}::ABA B",
    ]
    assert len(sources) == 2
    assert sources[0].block_count == 2
    assert sources[0].labeled_block_count == 1
    assert sources[0].unlabeled_block_count == 1
    assert sources[0].unlabeled_block_rows == (3,)
    assert sources[0].price_source == MEMORIA_PRICE_SOURCE
    assert sources[1].block_count == 1
    assert sources[1].unlabeled_block_count == 0


def test_run_precedent_eval_with_memoria_alone_detects_the_repeated_label(
    tmp_path: Path,
) -> None:
    path_a = tmp_path / "praca-a.xlsx"
    _write_memoria_workbook(
        path_a,
        "ABA A",
        [
            [None, "01.10", "AD39050218(A)", "descrição"],
            [None, None, None, "VIGIA"],
        ],
    )
    path_b = tmp_path / "praca-b.xlsx"
    _write_memoria_workbook(
        path_b,
        "ABA B",
        [
            [None, "01.10", "AD39050218(A)", "descrição"],
            [None, None, None, "VIGIA"],
        ],
    )
    output_dir = tmp_path / "out"

    report, report_path = run_precedent_eval(
        rounds_path=None,
        revisions_path=None,
        revision_dir=None,
        memoria=[f"{path_a}:ABA A", f"{path_b}:ABA B"],
        output_dir=output_dir,
    )

    assert len(report.worksites_used) == 2
    assert len(report.memoria_sources) == 2
    assert report.skipped == ()
    published = json.loads(report_path.read_text(encoding="utf-8"))
    exact = published["repetition"]["strategies"]["exact"]
    assert exact["repeated_label_count"] == 1
    assert exact["repeated_labels"][0]["normalized_label"] == "VIGIA"
    assert exact["repeated_labels"][0]["classification"] == "identical"
    assert published["memoria_sources"][0]["price_source"] == MEMORIA_PRICE_SOURCE


@pytest.mark.parametrize(
    "with_csv, with_dir",
    [(True, False), (False, True)],
    ids=["memoria_plus_csv", "memoria_plus_dir"],
)
def test_run_precedent_eval_refuses_memoria_combined_with_another_input(
    tmp_path: Path, with_csv: bool, with_dir: bool
) -> None:
    path_a = tmp_path / "praca-a.xlsx"
    _write_memoria_workbook(
        path_a, "ABA A", [[None, "01.10", "AD39050218(A)", "descrição"], [None, None, None, "X"]]
    )
    rounds_path = revisions_path = revision_dir = None
    if with_csv:
        rounds_path, revisions_path = _two_worksite_csv_inputs(tmp_path)
    if with_dir:
        revision_dir = tmp_path

    with pytest.raises(ValuationValidationError) as excinfo:
        run_precedent_eval(
            rounds_path=rounds_path,
            revisions_path=revisions_path,
            revision_dir=revision_dir,
            memoria=[f"{path_a}:ABA A"],
            output_dir=tmp_path / "out",
        )

    assert excinfo.value.code == "PRECEDENT_INPUT_AMBIGUOUS"


def test_cli_precedent_eval_with_memoria_succeeds(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path_a = tmp_path / "praca-a.xlsx"
    _write_memoria_workbook(
        path_a,
        "ABA A",
        [
            [None, "01.10", "AD39050218(A)", "descrição"],
            [None, None, None, "VIGIA"],
            [None, "01.11", "ET04600200(/)", "descrição 2"],
        ],
    )
    path_b = tmp_path / "praca-b.xlsx"
    _write_memoria_workbook(
        path_b,
        "ABA B",
        [
            [None, "01.10", "AD39050218(A)", "descrição"],
            [None, None, None, "VIGIA"],
        ],
    )
    output_dir = tmp_path / "out"

    exit_code = main(
        [
            "precedent-eval",
            "--memoria",
            f"{path_a}:ABA A",
            "--memoria",
            f"{path_b}:ABA B",
            "--output",
            str(output_dir),
        ]
    )

    assert exit_code == 0
    captured = capsys.readouterr()
    assert "praças usadas: 2" in captured.out
    assert "blocos=2 rotulados=1 sem_rotulo=1" in captured.out
    assert (output_dir / REPORT_FILENAME).is_file()
