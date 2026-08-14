"""Cadeia completa da medição de obra, ponta a ponta, pelos comandos reais do CLI.

Cada elo (`import-workbook`, `extract-legend`, `review-takeoff`, `suggest-codes`,
`confirm-codes`, `build-calc`, `export-valuation`) já tem cobertura própria em
`tests/valuation/` e `tests/worker/test_valuation_cli.py`. O que só este teste prova é o
encaixe: cada comando lê o artefato que o comando anterior gravou em disco — não o objeto
em memória —, e a cadeia inteira, de `import-workbook` até a reabertura do `.xlsx`
publicado, fecha sem nenhum atalho substituindo um comando real por chamada direta ao
domínio.

Não há stack HTTP aqui: a cadeia de medição é inteiramente CLI, offline e síncrona
(`croquitodxf_worker.valuation.cli.main`), como em `tests/worker/test_valuation_cli.py`.
A fixture `chain` roda a cadeia cara uma vez por módulo — a extração da prancha sintética
é o passo caro —, devolvendo os artefatos e modelos de cada elo.
`test_full_chain_happy_path` faz as asserções de negócio sobre esse resultado, uma por
elo; os testes de recusa derivam cenários dos mesmos artefatos sem repetir os passos que
já correram com exit 0.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Final, Literal

import pytest
from openpyxl import load_workbook

from croquitodxf_valuation.assignment import (
    CodeAssignmentBatch,
    CodeAssignmentInput,
    CodeAssignmentSet,
    CodeSuggestionSet,
)
from croquitodxf_valuation.contract import ContractWorkbook
from croquitodxf_valuation.models import CalcRecipe, Valuation
from croquitodxf_valuation.takeoff import TakeoffItemStatus, TakeoffPacket, load_takeoff_packet
from croquitodxf_valuation.template import WorkbookTemplate, default_template
from croquitodxf_worker.valuation.cli import (
    AUDIT_FILENAME,
    CALC_PLAN_FILENAME,
    CATALOG_FILENAME,
    CODE_ASSIGNMENTS_FILENAME,
    CODE_SUGGESTIONS_FILENAME,
    CONTRACT_FILENAME,
    TAKEOFF_PACKET_FILENAME,
    VALUATION_FILENAME,
    WORKBOOK_FILENAME,
    main,
)
from croquitodxf_worker.valuation.plate import SYNTHETIC_LEGEND_ROWS, SYNTHETIC_PLATE_ID
from croquitodxf_worker.valuation.synthetic import (
    SYNTHETIC_CODE_DECIDED_AT,
    SYNTHETIC_CONTRACT_LABEL,
    SYNTHETIC_PERIOD_REFERENCE_LABEL,
    SYNTHETIC_PREVIOUS_PERIOD_COUNT,
    SYNTHETIC_TAKEOFF_REVIEWER,
    SYNTHETIC_TAKEOFF_WORKSITE_ADDRESS,
    SYNTHETIC_TAKEOFF_WORKSITE_KEY,
    SYNTHETIC_TAKEOFF_WORKSITE_NAME,
    build_demo_calc_plan,
    build_demo_code_assignments,
    build_demo_takeoff_decisions,
    build_synthetic_approval,
    build_synthetic_previous_mapao,
)
from croquitodxf_worker.valuation.takeoff_fixture import takeoff_item_id

# Rótulos e ids da legenda sintética: a MESMA fonte que `tests/valuation/test_chain_demo.py`
# usa para a obra que nasce da prancha, para que os dois testes não possam divergir sobre
# qual item é qual.
_PAVEMENT_ITEM_ID = takeoff_item_id(SYNTHETIC_PLATE_ID, SYNTHETIC_LEGEND_ROWS[0].label)
_LAWN_ITEM_ID = takeoff_item_id(SYNTHETIC_PLATE_ID, SYNTHETIC_LEGEND_ROWS[1].label)
_FENCE_ITEM_ID = takeoff_item_id(SYNTHETIC_PLATE_ID, SYNTHETIC_LEGEND_ROWS[2].label)
_BENCH_ITEM_ID = takeoff_item_id(SYNTHETIC_PLATE_ID, SYNTHETIC_LEGEND_ROWS[3].label)
_LAMP_ITEM_ID = takeoff_item_id(SYNTHETIC_PLATE_ID, SYNTHETIC_LEGEND_ROWS[4].label)
_RUBBER_ITEM_ID = takeoff_item_id(SYNTHETIC_PLATE_ID, SYNTHETIC_LEGEND_ROWS[6].label)

# Numeração dos itens no boletim da obra oeste depois que o gramado (código rejeitado) sai:
# pavimento, alambrado, banco, luminária, piso emborrachado — mesma ordem fixada em
# `tests/valuation/test_chain_demo.py`.
_FENCE_ITEM_NUMBER = "2"

_EXPECTED_PERIOD_NUMBER = SYNTHETIC_PREVIOUS_PERIOD_COUNT + 1
"""3 na fixture: duas medições já lançadas no MAPÃO anterior, a próxima é a terceira."""

_OUT_OF_CONTRACT_CATALOG_CODE = "AD04100015(/)"
"""Existe no catálogo sintético (32 entradas) e não está entre os 10 códigos do
consolidado — candidato citado pelo próprio spec da Fase C."""

_INCOMPATIBLE_UNIT_CONTRACT_CODE = "SP01050010(/)"
"""Está no contrato (item 6, unidade M3); o banco confirmado mede em UN."""

_MISSING_ASSIGNMENT_BATCH: Final[
    tuple[tuple[str, Literal["confirm", "reject"], str | None], ...]
] = (
    (_PAVEMENT_ITEM_ID, "confirm", "AD04050060(/)"),
    (_LAWN_ITEM_ID, "reject", None),
    (_FENCE_ITEM_ID, "confirm", "CE02100010(/)"),
    (_BENCH_ITEM_ID, "confirm", "MB01100010(/)"),
    (_RUBBER_ITEM_ID, "confirm", "AD04150010(/)"),
    # A luminária (`_LAMP_ITEM_ID`) fica de fora de propósito: é o item confirmado no
    # takeoff que não recebe nenhuma decisão de código neste lote — o que falta para o
    # build-calc acusar CALC_ASSIGNMENT_MISSING.
)


def _stdout(capsys: pytest.CaptureFixture[str]) -> dict[str, object]:
    """Último JSON impresso: cada comando imprime uma linha só."""
    lines = [line for line in capsys.readouterr().out.splitlines() if line.strip()]
    return dict(json.loads(lines[-1]))


def _write_json(path: Path, payload: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(payload, encoding="utf-8")
    return path


def _bulletin_quantity(
    workbook_path: Path, template: WorkbookTemplate, worksite_name: str, code: str
) -> float:
    """Quantidade de um código na aba BM da obra, localizada pela coluna do template.

    Nenhuma célula é fixa aqui: aba, linha e coluna vêm de `default_template()`, como no
    helper equivalente de `tests/worker/test_valuation_cli.py`.
    """
    workbook = load_workbook(workbook_path)
    try:
        sheet_name = template.bulletin_sheet_name(worksite_name)
        worksheet = workbook[sheet_name]
        layout = template.bulletin
        row = layout.header_row + 1
        while True:
            cell_code = worksheet[f"{layout.columns.code.letter}{row}"].value
            if cell_code is None:
                raise AssertionError(f"código {code} ausente da aba {sheet_name}")
            if cell_code == code:
                quantity = worksheet[f"{layout.columns.quantity.letter}{row}"].value
                assert isinstance(quantity, int | float)
                return float(quantity)
            row += 1
    finally:
        workbook.close()


@dataclass(frozen=True, slots=True)
class ChainArtifacts:
    """Artefatos e modelos produzidos por uma passada da cadeia inteira pelo CLI."""

    template: WorkbookTemplate
    catalog_path: Path
    contract_path: Path
    contract: ContractWorkbook
    extracted_packet_path: Path
    extracted_packet: TakeoffPacket
    reviewed_packet_path: Path
    reviewed_packet: TakeoffPacket
    suggestions_path: Path
    suggestions: CodeSuggestionSet
    assignment_decisions_path: Path
    assignments_path: Path
    assignments: CodeAssignmentSet
    valuation_path: Path
    valuation_unapproved: Valuation
    valuation_approved: Valuation
    workbook_path: Path
    audit_path: Path


@pytest.fixture(scope="module")
def chain(tmp_path_factory: pytest.TempPathFactory) -> ChainArtifacts:
    """Percorre a cadeia de medição inteira pelos comandos reais do CLI, uma vez só.

    Roda uma única vez por módulo porque gerar e extrair a prancha sintética é o passo
    caro da cadeia. Cada `assert main([...]) == 0` aqui é o "um comando por elo, exit 0
    em todos" do caminho feliz; as asserções de negócio (contagens, códigos, quantidades)
    ficam em `test_full_chain_happy_path`, que só lê o que esta fixture já produziu. Os
    testes de recusa também partem destes artefatos, sem repetir os passos caros.
    """
    root = tmp_path_factory.mktemp("valuation-chain")
    template = default_template()

    # 1. MAPÃO anterior sintético → import-workbook (catálogo + consolidado).
    previous_path = build_synthetic_previous_mapao(root / "previous-mapao.xlsx")
    import_dir = root / "import"
    assert (
        main(["import-workbook", "--input", str(previous_path), "--output", str(import_dir)]) == 0
    )
    catalog_path = import_dir / CATALOG_FILENAME
    contract_path = import_dir / CONTRACT_FILENAME
    contract = ContractWorkbook.model_validate_json(contract_path.read_text(encoding="utf-8"))

    # 2. extract-legend → pacote proposto (7 itens, 1 ambíguo).
    takeoff_dir = root / "takeoff"
    assert main(["extract-legend", "--output", str(takeoff_dir)]) == 0
    extracted_packet_path = takeoff_dir / TAKEOFF_PACKET_FILENAME
    extracted_packet = load_takeoff_packet(extracted_packet_path)

    # 3. Decisões do orçamentista sintético gravadas → review-takeoff.
    decisions = build_demo_takeoff_decisions(extracted_packet)
    decisions_path = _write_json(
        root / "inputs" / "takeoff-decisions.json", decisions.model_dump_json(indent=2)
    )
    review_dir = root / "review"
    assert (
        main(
            [
                "review-takeoff",
                "--packet",
                str(extracted_packet_path),
                "--decisions",
                str(decisions_path),
                "--output",
                str(review_dir),
            ]
        )
        == 0
    )
    reviewed_packet_path = review_dir / TAKEOFF_PACKET_FILENAME
    reviewed_packet = load_takeoff_packet(reviewed_packet_path)

    # 4. suggest-codes --contract → code-suggestions.json.
    suggest_dir = root / "suggest"
    assert (
        main(
            [
                "suggest-codes",
                "--packet",
                str(reviewed_packet_path),
                "--catalog",
                str(catalog_path),
                "--contract",
                str(contract_path),
                "--output",
                str(suggest_dir),
            ]
        )
        == 0
    )
    suggestions_path = suggest_dir / CODE_SUGGESTIONS_FILENAME
    suggestions = CodeSuggestionSet.model_validate_json(
        suggestions_path.read_text(encoding="utf-8")
    )

    # 5. Decisões de código do orçamentista sintético gravadas → confirm-codes.
    assignment_decisions = build_demo_code_assignments(reviewed_packet)
    assignment_decisions_path = _write_json(
        root / "inputs" / "code-assignment-decisions.json",
        assignment_decisions.model_dump_json(indent=2),
    )
    assign_dir = root / "assign"
    assert (
        main(
            [
                "confirm-codes",
                "--packet",
                str(reviewed_packet_path),
                "--decisions",
                str(assignment_decisions_path),
                "--catalog",
                str(catalog_path),
                "--contract",
                str(contract_path),
                "--output",
                str(assign_dir),
            ]
        )
        == 0
    )
    assignments_path = assign_dir / CODE_ASSIGNMENTS_FILENAME
    assignments = CodeAssignmentSet.model_validate_json(
        assignments_path.read_text(encoding="utf-8")
    )

    # 6. calc-plan.json (decompõe só o alambrado) → build-calc: obra oeste, período 3.
    calc_plan = build_demo_calc_plan(reviewed_packet)
    calc_plan_path = _write_json(
        root / "inputs" / CALC_PLAN_FILENAME, calc_plan.model_dump_json(indent=2)
    )
    calc_dir = root / "calc"
    assert (
        main(
            [
                "build-calc",
                "--packet",
                str(reviewed_packet_path),
                "--assignments",
                str(assignments_path),
                "--catalog",
                str(catalog_path),
                "--worksite-key",
                SYNTHETIC_TAKEOFF_WORKSITE_KEY,
                "--worksite-name",
                SYNTHETIC_TAKEOFF_WORKSITE_NAME,
                "--period-number",
                str(contract.next_period_number),
                "--reference-label",
                SYNTHETIC_PERIOD_REFERENCE_LABEL,
                "--address",
                SYNTHETIC_TAKEOFF_WORKSITE_ADDRESS,
                "--contract-label",
                SYNTHETIC_CONTRACT_LABEL,
                "--calc-plan",
                str(calc_plan_path),
                "--output",
                str(calc_dir),
            ]
        )
        == 0
    )
    valuation_path = calc_dir / VALUATION_FILENAME
    valuation_unapproved = Valuation.model_validate_json(valuation_path.read_text(encoding="utf-8"))

    # 7. Aprovação em código sobre o Valuation lido do artefato, regravando o JSON, e só
    #    então export-valuation.
    valuation_approved = build_synthetic_approval(valuation_unapproved)
    valuation_path.write_text(valuation_approved.model_dump_json(indent=2), encoding="utf-8")

    export_dir = root / "export"
    assert (
        main(
            [
                "export-valuation",
                "--valuation",
                str(valuation_path),
                "--contract",
                str(contract_path),
                "--catalog",
                str(catalog_path),
                "--output",
                str(export_dir),
            ]
        )
        == 0
    )
    workbook_path = export_dir / WORKBOOK_FILENAME
    audit_path = export_dir / AUDIT_FILENAME

    return ChainArtifacts(
        template=template,
        catalog_path=catalog_path,
        contract_path=contract_path,
        contract=contract,
        extracted_packet_path=extracted_packet_path,
        extracted_packet=extracted_packet,
        reviewed_packet_path=reviewed_packet_path,
        reviewed_packet=reviewed_packet,
        suggestions_path=suggestions_path,
        suggestions=suggestions,
        assignment_decisions_path=assignment_decisions_path,
        assignments_path=assignments_path,
        assignments=assignments,
        valuation_path=valuation_path,
        valuation_unapproved=valuation_unapproved,
        valuation_approved=valuation_approved,
        workbook_path=workbook_path,
        audit_path=audit_path,
    )


def test_full_chain_happy_path(chain: ChainArtifacts) -> None:
    """Um comando por elo, exit 0 em todos (já verificado na fixture `chain`).

    Cada comentário numerado confere o que aquele elo deveria ter produzido em disco.
    """
    # 1. import-workbook: consolidado com o período seguinte igual a 3 na fixture.
    assert chain.contract.next_period_number == _EXPECTED_PERIOD_NUMBER

    # 2. extract-legend: pacote proposto com 7 itens, 1 ambíguo (nenhum nasce confirmado).
    assert len(chain.extracted_packet.items) == 7
    assert chain.extracted_packet.confirmed_items() == []
    ambiguous = [
        item for item in chain.extracted_packet.items if item.status is TakeoffItemStatus.AMBIGUOUS
    ]
    assert len(ambiguous) == 1

    # 3. review-takeoff: 6 confirmados, 1 rejeitado (área de intervenção sintética).
    assert len(chain.reviewed_packet.confirmed_items()) == 6
    rejected_takeoff = [
        item for item in chain.reviewed_packet.items if item.status is TakeoffItemStatus.REJECTED
    ]
    assert len(rejected_takeoff) == 1

    # 4. suggest-codes: todo item confirmado tem resposta, sugestão ou unmatched.
    confirmed_ids = {item.id for item in chain.reviewed_packet.confirmed_items()}
    answered = {suggestion.item_id for suggestion in chain.suggestions.suggestions} | set(
        chain.suggestions.unmatched_item_ids
    )
    assert answered == confirmed_ids

    # 5. confirm-codes: 5 confirmados, 1 rejeitado — o gramado, sem cotação no contrato.
    confirmed_assignments = [a for a in chain.assignments.assignments if a.status == "confirmed"]
    rejected_assignments = [a for a in chain.assignments.assignments if a.status == "rejected"]
    assert len(confirmed_assignments) == 5
    assert len(rejected_assignments) == 1
    assert rejected_assignments[0].item_id == _LAWN_ITEM_ID

    # 6. build-calc: obra oeste com 5 linhas; alambrado com bloco PERIMETER_TIMES_HEIGHT e
    #    subtotal 58,50 (48,75 m x 1,20 m), quantidade que o revisor confirmou.
    bulletin = chain.valuation_unapproved.bulletins[0]
    assert bulletin.worksite_key == SYNTHETIC_TAKEOFF_WORKSITE_KEY
    assert len(bulletin.lines) == 5
    fence_line = next(line for line in bulletin.lines if line.item_number == _FENCE_ITEM_NUMBER)
    fence_sheet = chain.valuation_unapproved.calc_sheet_for(
        SYNTHETIC_TAKEOFF_WORKSITE_KEY, _FENCE_ITEM_NUMBER
    )
    assert fence_line.quantity == fence_sheet.total_quantity
    assert [block.recipe for block in fence_sheet.blocks] == [CalcRecipe.PERIMETER_TIMES_HEIGHT]
    assert [operand.value for operand in fence_sheet.blocks[0].operands] == [
        Decimal("48.75"),
        Decimal("1.20"),
    ]
    assert fence_sheet.blocks[0].subtotal == Decimal("58.50")
    assert fence_sheet.total_quantity == Decimal("58.50")

    # 7. Aprovação em código + export-valuation: xlsx e audit publicados com status ok.
    assert chain.valuation_approved.approval is not None
    assert (
        chain.valuation_approved.approval.valuation_digest
        == chain.valuation_approved.content_digest()
    )
    audit = json.loads(chain.audit_path.read_text(encoding="utf-8"))
    assert audit["status"] == "ok"
    assert chain.workbook_path.is_file()

    # 8. Reabertura do medicao.xlsx: PLANILHA GERAL presente, par BM/MEMÓRIA da obra oeste
    #    presente, e a linha do alambrado na BM com quantidade 58,50 — coluna e aba
    #    derivadas do template, não número mágico.
    workbook = load_workbook(chain.workbook_path)
    try:
        assert chain.template.general.sheet_name in workbook.sheetnames
        bulletin_sheet = chain.template.bulletin_sheet_name(SYNTHETIC_TAKEOFF_WORKSITE_NAME)
        memory_sheet = chain.template.memory_sheet_name(SYNTHETIC_TAKEOFF_WORKSITE_NAME)
        assert bulletin_sheet in workbook.sheetnames
        assert memory_sheet in workbook.sheetnames
    finally:
        workbook.close()
    fence_quantity = _bulletin_quantity(
        chain.workbook_path, chain.template, SYNTHETIC_TAKEOFF_WORKSITE_NAME, fence_line.code
    )
    assert fence_quantity == 58.5


def test_export_before_approval_refuses(
    chain: ChainArtifacts, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """`export-valuation` antes da aprovação: VALUATION_EXPORT_BLOCKED com o motivo na lista."""
    unapproved_path = _write_json(
        tmp_path / "inputs" / VALUATION_FILENAME,
        chain.valuation_unapproved.model_dump_json(indent=2),
    )
    output_dir = tmp_path / "export"

    exit_code = main(
        [
            "export-valuation",
            "--valuation",
            str(unapproved_path),
            "--contract",
            str(chain.contract_path),
            "--catalog",
            str(chain.catalog_path),
            "--output",
            str(output_dir),
        ]
    )

    assert exit_code == 2
    payload = _stdout(capsys)
    assert payload["refused"] == "VALUATION_EXPORT_BLOCKED"
    errors = payload["errors"]
    assert isinstance(errors, list)
    assert "VALUATION_NOT_APPROVED" in errors
    assert not (output_dir / WORKBOOK_FILENAME).exists()


def test_confirm_codes_redecision_refuses(
    chain: ChainArtifacts, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """`confirm-codes` de novo com `--previous` e o MESMO lote: re-decisão é recusada."""
    output_dir = tmp_path / "redecision"

    exit_code = main(
        [
            "confirm-codes",
            "--packet",
            str(chain.reviewed_packet_path),
            "--decisions",
            str(chain.assignment_decisions_path),
            "--catalog",
            str(chain.catalog_path),
            "--contract",
            str(chain.contract_path),
            "--previous",
            str(chain.assignments_path),
            "--output",
            str(output_dir),
        ]
    )

    assert exit_code == 2
    payload = _stdout(capsys)
    assert payload["refused"] == "ASSIGNMENT_ITEM_ALREADY_DECIDED"
    assert not (output_dir / CODE_ASSIGNMENTS_FILENAME).exists()


def test_confirm_codes_code_out_of_contract_refuses(
    chain: ChainArtifacts, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Código do catálogo fora dos 10 do consolidado: CODE_NOT_IN_CONTRACT."""
    batch = CodeAssignmentBatch(
        assignments=[
            CodeAssignmentInput(
                item_id=_PAVEMENT_ITEM_ID,
                action="confirm",
                code=_OUT_OF_CONTRACT_CATALOG_CODE,
                reviewer_id=SYNTHETIC_TAKEOFF_REVIEWER,
                reviewer_role="orcamentista",
                decided_at=SYNTHETIC_CODE_DECIDED_AT,
            )
        ]
    )
    decisions_path = _write_json(
        tmp_path / "inputs" / "decisions.json", batch.model_dump_json(indent=2)
    )
    output_dir = tmp_path / "out-of-contract"

    exit_code = main(
        [
            "confirm-codes",
            "--packet",
            str(chain.reviewed_packet_path),
            "--decisions",
            str(decisions_path),
            "--catalog",
            str(chain.catalog_path),
            "--contract",
            str(chain.contract_path),
            "--output",
            str(output_dir),
        ]
    )

    assert exit_code == 2
    payload = _stdout(capsys)
    assert payload["refused"] == "CODE_NOT_IN_CONTRACT"
    assert not (output_dir / CODE_ASSIGNMENTS_FILENAME).exists()


def test_confirm_codes_unit_incompatible_without_note_refuses(
    chain: ChainArtifacts, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Código do contrato com unidade incompatível e sem nota: recusa fail-closed."""
    batch = CodeAssignmentBatch(
        assignments=[
            CodeAssignmentInput(
                item_id=_BENCH_ITEM_ID,
                action="confirm",
                code=_INCOMPATIBLE_UNIT_CONTRACT_CODE,
                reviewer_id=SYNTHETIC_TAKEOFF_REVIEWER,
                reviewer_role="orcamentista",
                decided_at=SYNTHETIC_CODE_DECIDED_AT,
            )
        ]
    )
    decisions_path = _write_json(
        tmp_path / "inputs" / "decisions.json", batch.model_dump_json(indent=2)
    )
    output_dir = tmp_path / "unit-incompatible"

    exit_code = main(
        [
            "confirm-codes",
            "--packet",
            str(chain.reviewed_packet_path),
            "--decisions",
            str(decisions_path),
            "--catalog",
            str(chain.catalog_path),
            "--contract",
            str(chain.contract_path),
            "--output",
            str(output_dir),
        ]
    )

    assert exit_code == 2
    payload = _stdout(capsys)
    assert payload["refused"] == "ASSIGNMENT_UNIT_INCOMPATIBLE_WITHOUT_NOTE"
    assert not (output_dir / CODE_ASSIGNMENTS_FILENAME).exists()


def test_build_calc_missing_assignment_refuses(
    chain: ChainArtifacts, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Lote de código parcial (sem a luminária), montado à parte: CALC_ASSIGNMENT_MISSING."""
    batch = CodeAssignmentBatch(
        assignments=[
            CodeAssignmentInput(
                item_id=item_id,
                action=action,
                code=code,
                reviewer_id=SYNTHETIC_TAKEOFF_REVIEWER,
                reviewer_role="orcamentista",
                decided_at=SYNTHETIC_CODE_DECIDED_AT,
                note=None if action == "confirm" else "sem cotação aplicável no contrato sintético",
            )
            for item_id, action, code in _MISSING_ASSIGNMENT_BATCH
        ]
    )
    decisions_path = _write_json(
        tmp_path / "inputs" / "decisions.json", batch.model_dump_json(indent=2)
    )
    partial_assign_dir = tmp_path / "partial-assign"
    assert (
        main(
            [
                "confirm-codes",
                "--packet",
                str(chain.reviewed_packet_path),
                "--decisions",
                str(decisions_path),
                "--catalog",
                str(chain.catalog_path),
                "--contract",
                str(chain.contract_path),
                "--output",
                str(partial_assign_dir),
            ]
        )
        == 0
    )
    partial_assignments_path = partial_assign_dir / CODE_ASSIGNMENTS_FILENAME

    output_dir = tmp_path / "build-calc"
    exit_code = main(
        [
            "build-calc",
            "--packet",
            str(chain.reviewed_packet_path),
            "--assignments",
            str(partial_assignments_path),
            "--catalog",
            str(chain.catalog_path),
            "--worksite-key",
            SYNTHETIC_TAKEOFF_WORKSITE_KEY,
            "--worksite-name",
            SYNTHETIC_TAKEOFF_WORKSITE_NAME,
            "--period-number",
            str(chain.contract.next_period_number),
            "--reference-label",
            SYNTHETIC_PERIOD_REFERENCE_LABEL,
            "--output",
            str(output_dir),
        ]
    )

    assert exit_code == 2
    payload = _stdout(capsys)
    assert payload["refused"] == "CALC_ASSIGNMENT_MISSING"
    details = payload["details"]
    assert isinstance(details, dict)
    assert details["item_ids"] == [_LAMP_ITEM_ID]
    assert not (output_dir / VALUATION_FILENAME).exists()


def test_suggest_codes_before_review_refuses(
    chain: ChainArtifacts, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """`suggest-codes` sobre o pacote ainda proposto (antes de `review-takeoff`)."""
    output_dir = tmp_path / "suggest-before-review"

    exit_code = main(
        [
            "suggest-codes",
            "--packet",
            str(chain.extracted_packet_path),
            "--catalog",
            str(chain.catalog_path),
            "--output",
            str(output_dir),
        ]
    )

    assert exit_code == 2
    payload = _stdout(capsys)
    assert payload["refused"] == "SUGGESTION_NO_CONFIRMED_ITEMS"
    assert not (output_dir / CODE_SUGGESTIONS_FILENAME).exists()
