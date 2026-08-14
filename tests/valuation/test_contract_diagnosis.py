"""Dossiê da recusa semântica: uma leitura, todas as divergências do histórico.

O que se prova aqui é o oposto do resto do leitor: em vez de recusar na primeira violação,
uma única leitura devolve o mapa inteiro — cada classe com o código estável do modelo, a
célula exata e os dois números — sem que dado ruim vire exceção opaca pelo caminho.

Tudo é sintético e nenhuma célula é escrita à mão: linhas e colunas saem do template e do
arquivo gravado (`general_columns`, `general_item_rows`, `amendment_code_rows`).
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

import pytest

from croquitodxf_valuation.contract_diagnosis import (
    ContractDiagnosis,
    ContractSemanticsError,
    SemanticFinding,
    diagnose_contract,
)
from croquitodxf_valuation.errors import ValuationValidationError
from croquitodxf_valuation.template import AmendmentLayout, WorkbookTemplate, default_template
from croquitodxf_valuation.workbook_reader import read_contract_parse, read_contract_workbook
from tests.valuation.builders import (
    PREVIOUS_MAPAO_CONTRACT_LABEL,
    PREVIOUS_MAPAO_PERIOD_NUMBERS,
    PREVIOUS_MAPAO_SOURCE_LABEL,
    GeneralColumns,
    amendment_code_rows,
    build_previous_mapao_workbook,
    general_columns,
    general_item_rows,
    tamper_cell,
)

_PAVING_GROUP = "PAVIMENTACAO SINTETICA"
_SERVICES_GROUP = "SERVICOS PRELIMINARES E MOBILIARIO"
_REDUCED_CODE = "AD04050050(/)"
_VARIANT_A_CODE = "AD04050055(A)"
_VARIANT_B_CODE = "AD04050055(B)"
_DIGGING_CODE = "SP01050010(/)"

Shape = tuple[str, int | None, str | None]


@dataclass(frozen=True, slots=True)
class _DivergentHistory:
    """MAPÃO sintético adulterado e as posições que o gabarito do teste usa."""

    workbook_path: Path
    template: WorkbookTemplate
    columns: GeneralColumns
    rows: dict[tuple[str, str], int]
    amendment_rows: dict[str, int]

    @property
    def amendment_sheet(self) -> str:
        return _amendment_layout(self.template).sheet_name


def _read(path: Path, template: WorkbookTemplate) -> None:
    read_contract_workbook(
        path,
        template,
        source_label=PREVIOUS_MAPAO_SOURCE_LABEL,
        contract_label=PREVIOUS_MAPAO_CONTRACT_LABEL,
    )


def _diagnosis_of(path: Path, template: WorkbookTemplate) -> ContractDiagnosis:
    """Lê esperando recusa semântica e devolve o dossiê que veio com ela."""
    with pytest.raises(ContractSemanticsError) as raised:
        _read(path, template)
    assert raised.value.code == "CONTRACT_SEMANTICS_DIVERGENT"
    assert raised.value.details["summary"] == dict(raised.value.diagnosis.summary)
    return raised.value.diagnosis


def _only(diagnosis: ContractDiagnosis, finding_code: str) -> SemanticFinding:
    found = [finding for finding in diagnosis.findings if finding.finding_code == finding_code]
    assert len(found) == 1, [finding.finding_code for finding in diagnosis.findings]
    return found[0]


def _shape(diagnosis: ContractDiagnosis) -> list[Shape]:
    """Forma comparável do dossiê: classe, linha e célula, na ordem em que saíram."""
    return [(finding.finding_code, finding.row, finding.ref) for finding in diagnosis.findings]


def _amendment_layout(template: WorkbookTemplate) -> AmendmentLayout:
    layout = template.amendment
    assert layout is not None, "a fixture padrão declara a aba da prefeitura"
    return layout


def _divergent_history(path: Path) -> _DivergentHistory:
    """MAPÃO sintético com um histórico divergente em várias classes de uma vez.

    Cada adulteração está comentada com o que ela deve produzir, inclusive as classes que
    vêm de brinde — a linha que quebra dois invariantes ao mesmo tempo é o caso normal no
    arquivo real, e o dossiê existe justamente para mostrar os dois.
    """
    template = default_template()
    general = template.general
    amendment = _amendment_layout(template)
    build_previous_mapao_workbook(path)
    sheet = general.sheet_name
    columns = general_columns(general, len(PREVIOUS_MAPAO_PERIOD_NUMBERS))
    rows = general_item_rows(path, general)
    amendment_rows = amendment_code_rows(path, amendment)

    reduced_row = rows[(_PAVING_GROUP, _REDUCED_CODE)]
    variant_a_row = rows[(_PAVING_GROUP, _VARIANT_A_CODE)]
    variant_b_row = rows[(_PAVING_GROUP, _VARIANT_B_CODE)]
    digging_row = rows[(_SERVICES_GROUP, _DIGGING_CODE)]
    assert general.amended_quantity_column is not None
    assert amendment.amended_quantity_column is not None

    # Deriva de um centavo no valor da 1ª medição, com o acumulado acompanhando:
    # PERIOD_AMOUNT_MISMATCH sozinho, que é a classe do arquivo real.
    tamper_cell(path, sheet, f"{columns.period_amount[0]}{reduced_row}", Decimal("30.01"))
    tamper_cell(path, sheet, f"{columns.accumulated_amount}{reduced_row}", Decimal("50.01"))
    # Quantidade negativa lançada num período: CONTRACT_NEGATIVE_VALUE — que o modelo
    # recusaria por `ge=0`, sem código de domínio —, mais o valor do período e o acumulado
    # de quantidade que deixam de fechar.
    tamper_cell(path, sheet, f"{columns.period_quantity[0]}{variant_a_row}", Decimal("-1.00"))
    # Saldo que não fecha com vigente menos acumulado: CONTRACT_BALANCE_MISMATCH.
    tamper_cell(path, sheet, f"{columns.balance}{variant_b_row}", Decimal("4.60"))
    # Vigente da aba da prefeitura diferente do da GERAL: GENERAL_AMENDED_DIVERGENT.
    tamper_cell(
        path,
        amendment.sheet_name,
        f"{amendment.amended_quantity_column}{amendment_rows[_VARIANT_B_CODE]}",
        Decimal("5.00"),
    )
    # Item repetido dentro do mesmo grupo: CONTRACT_DUPLICATE_ITEM na chave composta.
    tamper_cell(path, sheet, f"{general.item_column}{variant_b_row}", 2)
    # O código da variante A passa a existir em dois grupos e a prefeitura fala dele:
    # CODE_AMBIGUOUS_IN_CONTRACT. O vigente divergente desse código fica suprimido de
    # propósito — escolher a linha seria adivinhar.
    tamper_cell(path, sheet, f"{general.code_column}{digging_row}", _VARIANT_A_CODE)
    # Acumulado acima do vigente, com o saldo declarado coerente: CONTRACT_BALANCE_NEGATIVE
    # sem CONTRACT_BALANCE_MISMATCH, que é a forma do saldo negativo do arquivo real.
    tamper_cell(path, sheet, f"{columns.accumulated_quantity}{digging_row}", Decimal("9.00"))
    tamper_cell(path, sheet, f"{columns.balance}{digging_row}", Decimal("-1.00"))
    # A mesma RE-RA reduz e acrescenta o mesmo código: AMENDMENT_DUPLICATE_CODE — que hoje
    # abortaria a leitura na construção do modelo —, e o delta resultante deixa de explicar
    # o vigente declarado (AMENDMENT_APPLICATION_MISMATCH).
    block = amendment.blocks[0]
    assert block.added_column is not None
    tamper_cell(
        path,
        amendment.sheet_name,
        f"{block.added_column}{amendment_rows[_REDUCED_CODE]}",
        Decimal("2.00"),
    )
    return _DivergentHistory(
        workbook_path=path,
        template=template,
        columns=columns,
        rows=rows,
        amendment_rows=amendment_rows,
    )


def _expected_shape(history: _DivergentHistory) -> list[Shape]:
    """Ordem esperada do dossiê: cada linha da GERAL na ordem da planilha, agregados no fim."""
    general = history.template.general
    columns = history.columns
    amended = general.amended_quantity_column
    reduced_row = history.rows[(_PAVING_GROUP, _REDUCED_CODE)]
    variant_a_row = history.rows[(_PAVING_GROUP, _VARIANT_A_CODE)]
    variant_b_row = history.rows[(_PAVING_GROUP, _VARIANT_B_CODE)]
    digging_row = history.rows[(_SERVICES_GROUP, _DIGGING_CODE)]
    return [
        ("PERIOD_AMOUNT_MISMATCH", reduced_row, f"{columns.period_amount[0]}{reduced_row}"),
        ("AMENDMENT_APPLICATION_MISMATCH", reduced_row, f"{amended}{reduced_row}"),
        ("CONTRACT_NEGATIVE_VALUE", variant_a_row, f"{columns.period_quantity[0]}{variant_a_row}"),
        ("PERIOD_AMOUNT_MISMATCH", variant_a_row, f"{columns.period_amount[0]}{variant_a_row}"),
        (
            "CONTRACT_ACCUMULATED_MISMATCH",
            variant_a_row,
            f"{columns.accumulated_quantity}{variant_a_row}",
        ),
        ("CONTRACT_BALANCE_MISMATCH", variant_b_row, f"{columns.balance}{variant_b_row}"),
        ("GENERAL_AMENDED_DIVERGENT", variant_b_row, f"{amended}{variant_b_row}"),
        (
            "CONTRACT_ACCUMULATED_MISMATCH",
            digging_row,
            f"{columns.accumulated_quantity}{digging_row}",
        ),
        ("CONTRACT_BALANCE_NEGATIVE", digging_row, f"{columns.balance}{digging_row}"),
        ("CONTRACT_DUPLICATE_ITEM", variant_b_row, f"{general.item_column}{variant_b_row}"),
        ("CODE_AMBIGUOUS_IN_CONTRACT", None, None),
        ("AMENDMENT_DUPLICATE_CODE", history.amendment_rows[_REDUCED_CODE], None),
    ]


def test_one_reading_returns_every_divergence_of_the_published_history(tmp_path: Path) -> None:
    history = _divergent_history(tmp_path / "mapao-divergente.xlsx")

    diagnosis = _diagnosis_of(history.workbook_path, history.template)

    assert dict(diagnosis.summary) == {
        "AMENDMENT_APPLICATION_MISMATCH": 1,
        "AMENDMENT_DUPLICATE_CODE": 1,
        "CODE_AMBIGUOUS_IN_CONTRACT": 1,
        "CONTRACT_ACCUMULATED_MISMATCH": 2,
        "CONTRACT_BALANCE_MISMATCH": 1,
        "CONTRACT_BALANCE_NEGATIVE": 1,
        "CONTRACT_DUPLICATE_ITEM": 1,
        "CONTRACT_NEGATIVE_VALUE": 1,
        "GENERAL_AMENDED_DIVERGENT": 1,
        "PERIOD_AMOUNT_MISMATCH": 2,
    }
    assert len(diagnosis.findings) == sum(diagnosis.summary.values())
    assert diagnosis.clean is False


def test_the_dossier_points_at_the_exact_cell_in_a_stable_order(tmp_path: Path) -> None:
    history = _divergent_history(tmp_path / "mapao-divergente.xlsx")

    diagnosis = _diagnosis_of(history.workbook_path, history.template)
    again = _diagnosis_of(history.workbook_path, history.template)

    assert _shape(diagnosis) == _expected_shape(history)
    assert _shape(again) == _shape(diagnosis)


def test_each_finding_carries_the_two_numbers_that_do_not_agree(tmp_path: Path) -> None:
    history = _divergent_history(tmp_path / "mapao-divergente.xlsx")

    diagnosis = _diagnosis_of(history.workbook_path, history.template)

    negative = _only(diagnosis, "CONTRACT_NEGATIVE_VALUE")
    assert (negative.declared, negative.detail["field"]) == ("-1.00", "period_quantity")
    balance = _only(diagnosis, "CONTRACT_BALANCE_NEGATIVE")
    assert (balance.declared, balance.expected) == ("-1.00", "-1.00")
    assert balance.detail["declared_negative"] is True
    assert balance.detail["recomputed_negative"] is True
    mismatch = _only(diagnosis, "CONTRACT_BALANCE_MISMATCH")
    assert (mismatch.declared, mismatch.expected) == ("4.60", "4.50")
    divergent = _only(diagnosis, "GENERAL_AMENDED_DIVERGENT")
    assert (divergent.code, divergent.declared, divergent.expected) == (
        _VARIANT_B_CODE,
        "5.00",
        "6.00",
    )
    assert divergent.detail["amendment_sheet"] == history.amendment_sheet
    applied = _only(diagnosis, "AMENDMENT_APPLICATION_MISMATCH")
    assert (applied.code, applied.declared, applied.expected) == (_REDUCED_CODE, "16.00", "18.00")
    ambiguous = _only(diagnosis, "CODE_AMBIGUOUS_IN_CONTRACT")
    assert ambiguous.code == _VARIANT_A_CODE
    assert ambiguous.detail["groups"] == [_PAVING_GROUP, _SERVICES_GROUP]
    duplicated = _only(diagnosis, "AMENDMENT_DUPLICATE_CODE")
    assert duplicated.sheet == history.amendment_sheet
    assert duplicated.code == _REDUCED_CODE


def test_duplicate_item_and_code_use_the_composite_key(tmp_path: Path) -> None:
    """Grupo+item e grupo+código: o mesmo código em outro grupo continua legítimo."""
    template = WorkbookTemplate.model_validate(
        {**default_template().model_dump(), "amendment": None}
    )
    general = template.general
    path = tmp_path / "mapao-duplicado.xlsx"
    build_previous_mapao_workbook(path, with_amendments=False)
    rows = general_item_rows(path, general)
    first_row = rows[(_PAVING_GROUP, _REDUCED_CODE)]
    second_row = rows[(_PAVING_GROUP, _VARIANT_A_CODE)]
    third_row = rows[(_PAVING_GROUP, _VARIANT_B_CODE)]
    tamper_cell(path, general.sheet_name, f"{general.code_column}{second_row}", _REDUCED_CODE)
    tamper_cell(path, general.sheet_name, f"{general.item_column}{third_row}", 2)

    diagnosis = _diagnosis_of(path, template)

    assert dict(diagnosis.summary) == {"CONTRACT_DUPLICATE_CODE": 1, "CONTRACT_DUPLICATE_ITEM": 1}
    duplicated_code = _only(diagnosis, "CONTRACT_DUPLICATE_CODE")
    assert duplicated_code.row == second_row
    assert duplicated_code.detail["first_row"] == first_row
    assert duplicated_code.group_label == _PAVING_GROUP
    duplicated_item = _only(diagnosis, "CONTRACT_DUPLICATE_ITEM")
    assert duplicated_item.row == third_row
    assert duplicated_item.item_number == "2"


def test_a_layout_failure_refuses_without_a_dossier(tmp_path: Path) -> None:
    """Sem entender a planilha não há o que recomputar: recusa de layout não gera dossiê."""
    template = default_template()
    general = template.general
    fixture = build_previous_mapao_workbook(tmp_path / "mapao-cabecalho-quebrado.xlsx")
    tamper_cell(
        fixture.workbook_path,
        general.sheet_name,
        f"{general.first_period_column}{general.header_row}",
        "SEGUNDA MEDICAO",
    )

    with pytest.raises(ValuationValidationError) as raised:
        _read(fixture.workbook_path, template)

    assert not isinstance(raised.value, ContractSemanticsError)
    assert raised.value.code == "PERIOD_HEADER_UNPARSEABLE"


def test_a_clean_dossier_reraises_the_original_refusal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Invariante que o dossiê não cobre é bug nosso: o erro original sobe, não some."""
    history = _divergent_history(tmp_path / "mapao-divergente.xlsx")
    monkeypatch.setattr(
        "croquitodxf_valuation.workbook_reader.diagnose_contract",
        lambda parse: ContractDiagnosis(findings=(), summary={}),
    )

    with pytest.raises(ValuationValidationError) as raised:
        _read(history.workbook_path, history.template)

    assert not isinstance(raised.value, ContractSemanticsError)
    assert raised.value.code == "CODE_AMBIGUOUS_IN_CONTRACT"


def test_diagnosing_a_sound_contract_finds_nothing(tmp_path: Path) -> None:
    """O recomputo não inventa divergência: o mesmo dossiê sobre planilha íntegra é vazio."""
    fixture = build_previous_mapao_workbook(tmp_path / "mapao-anterior.xlsx")
    parse, notes = read_contract_parse(fixture.workbook_path, default_template())

    diagnosis = diagnose_contract(parse)

    assert diagnosis.clean is True
    assert dict(diagnosis.summary) == {}
    assert notes.period_numbers == PREVIOUS_MAPAO_PERIOD_NUMBERS
