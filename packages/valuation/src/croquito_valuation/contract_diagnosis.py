"""Dossiê das divergências semânticas do MAPÃO publicado pela prefeitura.

O leitor (`workbook_reader`) recusa fechado na **primeira** violação: o consolidado é um
agregado validante e o Pydantic para no primeiro invariante quebrado. Isso basta para não
importar planilha errada, mas não serve para a conversa com o orçamentista — o arquivo
real traz centenas de linhas de histórico já publicado, e o que precisa aparecer é o mapa
inteiro da divergência, por classe e por célula.

Este módulo é o caminho de **leitura paralelo** que produz esse mapa: recomputa os mesmos
invariantes que `contract.py` valida, sobre os dados já parseados (`ContractParse`), sem
construir modelo nenhum — e por isso enxerga o que o modelo nem chega a avaliar, como o
número negativo que morreria na validação de campo (`ge=0`) antes de qualquer validador.

Três regras mandam no desenho:

1. **Os códigos são os mesmos dos modelos.** Nada de sinônimo: `PERIOD_AMOUNT_MISMATCH`
   aqui é o mesmo `PERIOD_AMOUNT_MISMATCH` de `ContractLine`. A única classe nova é
   `CONTRACT_NEGATIVE_VALUE`, para os campos que o modelo recusa por `ge=0` sem código de
   domínio próprio.
2. **Dado ruim é achado, nunca exceção.** O diagnóstico não levanta nada: se levantasse,
   voltaria a ser uma recusa na primeira violação.
3. **A ordem é estável.** Linha a linha na ordem da planilha, depois os agregados, para
   que dois dossiês do mesmo arquivo sejam comparáveis.

O dossiê **não** é um mecanismo de aceite: a importação continua recusando fechada. Qual
divergência do histórico o orçamentista reconhece como correta é decisão humana pendente,
registrada como tal no ADR-0018.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator, Mapping, Sequence
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Final

from croquito_valuation.errors import ValuationValidationError
from croquito_valuation.rounding import money_trunc

CONTRACT_SEMANTICS_DIVERGENT: Final = "CONTRACT_SEMANTICS_DIVERGENT"
"""Código da recusa agregada: o histórico publicado diverge dos invariantes."""

_ZERO: Final = Decimal("0.00")


@dataclass(frozen=True, slots=True)
class ParsedPeriod:
    """Par QUANTIDADE|VALOR de uma medição, como a planilha o escreve.

    Não é `PeriodProgress`: aqui o número negativo sobrevive à leitura, porque quem o
    classifica é o dossiê, não a validação de campo do modelo.
    """

    number: int
    quantity: Decimal
    amount: Decimal


@dataclass(frozen=True, slots=True)
class ParsedContractLine:
    """Linha de item da PLANILHA GERAL convertida, antes de virar `ContractLine`.

    `amended_quantity` é `None` quando o template não declara a coluna de quantidade
    vigente: nesse layout o vigente não está escrito na GERAL e é derivado do contratual
    mais as RE-RA do código, depois que a aba da prefeitura também foi lida.
    """

    row: int
    group_label: str
    item_number: str
    code: str
    description: str
    unit: str
    unit_price: Decimal
    contract_quantity: Decimal
    amended_quantity: Decimal | None
    periods: tuple[ParsedPeriod, ...]
    accumulated_quantity: Decimal
    accumulated_amount: Decimal
    balance_quantity: Decimal

    def resolved_amended_quantity(self, deltas: Mapping[str, Decimal]) -> Decimal:
        """Vigente declarado na GERAL ou, sem a coluna, contratual mais as RE-RA do código."""
        if self.amended_quantity is not None:
            return self.amended_quantity
        return self.contract_quantity + deltas.get(self.code, _ZERO)

    @property
    def amended_is_derived(self) -> bool:
        """`True` quando o vigente não está escrito na GERAL e foi derivado das RE-RA."""
        return self.amended_quantity is None


@dataclass(frozen=True, slots=True)
class ParsedAmendmentLine:
    """Efeito de uma RE-RA sobre um código, com a linha da aba em que ele foi lido."""

    row: int
    code: str
    quantity_delta: Decimal
    is_new_item: bool


@dataclass(frozen=True, slots=True)
class ParsedAmendmentBlock:
    """Um bloco de RE-RA cru: rótulo e linhas, sem o modelo `Amendment`.

    O modelo valida código repetido na construção; se ele fosse montado na leitura, uma
    RE-RA repetida abortaria a importação antes de qualquer dossiê.
    """

    label: str
    lines: tuple[ParsedAmendmentLine, ...]


@dataclass(frozen=True, slots=True)
class PairColumns:
    """Letras das colunas de um par QUANTIDADE|VALOR, para compor a referência da célula."""

    quantity: str
    amount: str


@dataclass(frozen=True, slots=True)
class ContractParse:
    """Tudo que a leitura extraiu da pasta, antes de qualquer modelo validante.

    É a entrada do dossiê e também o material do caminho estrito: as duas leituras partem
    exatamente dos mesmos números, então o dossiê não pode divergir do que foi recusado.
    """

    general_sheet: str
    amendment_sheet: str | None
    period_numbers: tuple[int, ...]
    period_columns: Mapping[int, PairColumns]
    accumulated_columns: PairColumns
    balance_column: str
    item_column: str
    code_column: str
    contract_quantity_column: str
    unit_price_column: str
    amended_column: str | None
    lines: tuple[ParsedContractLine, ...]
    amendment_blocks: tuple[ParsedAmendmentBlock, ...]
    declared_amended: Mapping[str, Decimal]

    def amendment_deltas(self) -> dict[str, Decimal]:
        """Efeito acumulado das RE-RA por código, na ordem em que a aba as declara."""
        deltas: dict[str, Decimal] = {}
        for block in self.amendment_blocks:
            for line in block.lines:
                deltas[line.code] = deltas.get(line.code, _ZERO) + line.quantity_delta
        return deltas

    def lines_by_code(self) -> dict[str, list[ParsedContractLine]]:
        """Linhas por código; o mesmo código pode responder por mais de um grupo."""
        by_code: dict[str, list[ParsedContractLine]] = {}
        for line in self.lines:
            by_code.setdefault(line.code, []).append(line)
        return by_code


@dataclass(frozen=True, slots=True)
class SemanticFinding:
    """Uma divergência semântica: que invariante caiu, onde, com que números."""

    finding_code: str
    sheet: str
    row: int | None = None
    ref: str | None = None
    group_label: str | None = None
    item_number: str | None = None
    code: str | None = None
    declared: str | None = None
    expected: str | None = None
    detail: dict[str, object] = field(default_factory=dict)

    def as_details(self) -> dict[str, object]:
        """Forma serializável do achado; campo sem valor não ocupa espaço no dossiê."""
        payload: dict[str, object] = {"finding_code": self.finding_code, "sheet": self.sheet}
        optional: tuple[tuple[str, object | None], ...] = (
            ("row", self.row),
            ("ref", self.ref),
            ("group_label", self.group_label),
            ("item_number", self.item_number),
            ("code", self.code),
            ("declared", self.declared),
            ("expected", self.expected),
        )
        payload.update({name: value for name, value in optional if value is not None})
        if self.detail:
            payload["detail"] = dict(self.detail)
        return payload


@dataclass(frozen=True, slots=True)
class ContractDiagnosis:
    """Todas as divergências semânticas de uma importação, com a contagem por classe."""

    findings: tuple[SemanticFinding, ...]
    summary: Mapping[str, int]

    @property
    def clean(self) -> bool:
        """`True` quando o recomputo não encontrou divergência nenhuma."""
        return not self.findings

    def as_details(self) -> list[dict[str, object]]:
        """Achados em forma serializável, na ordem estável do diagnóstico."""
        return [finding.as_details() for finding in self.findings]


class ContractSemanticsError(ValuationValidationError):
    """Recusa agregada da importação, com o dossiê completo pendurado na exceção.

    `details` leva só o resumo: o dossiê inteiro pode ter milhares de achados e quem o
    grava em arquivo é o CLI, não o payload de erro.
    """

    def __init__(self, diagnosis: ContractDiagnosis, *, source_sha256: str) -> None:
        super().__init__(
            CONTRACT_SEMANTICS_DIVERGENT,
            "o histórico publicado no MAPÃO diverge dos invariantes do consolidado",
            {"summary": dict(diagnosis.summary), "finding_count": len(diagnosis.findings)},
        )
        self.diagnosis = diagnosis
        self.source_sha256 = source_sha256


def _ref(column: str | None, row: int) -> str | None:
    """Referência da célula, ou `None` quando o template não declara aquela coluna."""
    return None if column is None else f"{column}{row}"


def _negative_value_findings(
    parse: ContractParse, line: ParsedContractLine
) -> Iterator[SemanticFinding]:
    """Campos que o modelo recusaria por `ge=0` antes de qualquer validador de domínio.

    O saldo fica de fora de propósito: saldo negativo tem classe própria
    (`CONTRACT_BALANCE_NEGATIVE`), e vigente derivado negativo é consequência das RE-RA
    (`AMENDMENT_NEGATIVE_RESULT`) — nenhum dos dois é contado duas vezes.
    """
    checks: list[tuple[str, Decimal, str | None]] = [
        ("unit_price", line.unit_price, parse.unit_price_column),
        ("contract_quantity", line.contract_quantity, parse.contract_quantity_column),
    ]
    if line.amended_quantity is not None:
        checks.append(("amended_quantity", line.amended_quantity, parse.amended_column))
    for period in line.periods:
        pair = parse.period_columns.get(period.number)
        checks.append(("period_quantity", period.quantity, None if pair is None else pair.quantity))
        checks.append(("period_amount", period.amount, None if pair is None else pair.amount))
    checks.append(
        ("accumulated_quantity", line.accumulated_quantity, parse.accumulated_columns.quantity)
    )
    checks.append(("accumulated_amount", line.accumulated_amount, parse.accumulated_columns.amount))
    for field_name, value, column in checks:
        if value >= 0:
            continue
        yield _line_finding(
            "CONTRACT_NEGATIVE_VALUE",
            parse,
            line,
            ref=_ref(column, line.row),
            declared=str(value),
            detail={"field": field_name},
        )


def _line_finding(
    finding_code: str,
    parse: ContractParse,
    line: ParsedContractLine,
    *,
    ref: str | None = None,
    declared: str | None = None,
    expected: str | None = None,
    detail: dict[str, object] | None = None,
) -> SemanticFinding:
    """Achado ancorado numa linha da PLANILHA GERAL, já com grupo, item e código."""
    return SemanticFinding(
        finding_code=finding_code,
        sheet=parse.general_sheet,
        row=line.row,
        ref=ref,
        group_label=line.group_label,
        item_number=line.item_number,
        code=line.code,
        declared=declared,
        expected=expected,
        detail={} if detail is None else detail,
    )


def _period_findings(parse: ContractParse, line: ParsedContractLine) -> Iterator[SemanticFinding]:
    """Valor de cada medição contra quantidade x preço truncado."""
    for period in line.periods:
        expected = money_trunc(period.quantity * line.unit_price)
        if period.amount == expected:
            continue
        pair = parse.period_columns.get(period.number)
        yield _line_finding(
            "PERIOD_AMOUNT_MISMATCH",
            parse,
            line,
            ref=None if pair is None else _ref(pair.amount, line.row),
            declared=str(period.amount),
            expected=str(expected),
            detail={"period_number": period.number, "quantity": str(period.quantity)},
        )


def _accumulated_findings(
    parse: ContractParse, line: ParsedContractLine
) -> Iterator[SemanticFinding]:
    """Acumulado declarado contra a soma dos períodos, em quantidade e em valor."""
    checks = (
        (
            "accumulated_quantity",
            line.accumulated_quantity,
            sum((period.quantity for period in line.periods), _ZERO),
            parse.accumulated_columns.quantity,
        ),
        (
            "accumulated_amount",
            line.accumulated_amount,
            sum((period.amount for period in line.periods), _ZERO),
            parse.accumulated_columns.amount,
        ),
    )
    for field_name, declared, expected, column in checks:
        if declared == expected:
            continue
        yield _line_finding(
            "CONTRACT_ACCUMULATED_MISMATCH",
            parse,
            line,
            ref=_ref(column, line.row),
            declared=str(declared),
            expected=str(expected),
            detail={"field": field_name},
        )


def _balance_findings(
    parse: ContractParse, line: ParsedContractLine, amended: Decimal
) -> Iterator[SemanticFinding]:
    """Saldo: primeiro se ele é negativo, depois se ele fecha com vigente menos acumulado."""
    expected = amended - line.accumulated_quantity
    ref = _ref(parse.balance_column, line.row)
    declared_negative = line.balance_quantity < 0
    recomputed_negative = expected < 0
    if declared_negative or recomputed_negative:
        yield _line_finding(
            "CONTRACT_BALANCE_NEGATIVE",
            parse,
            line,
            ref=ref,
            declared=str(line.balance_quantity),
            expected=str(expected),
            detail={
                "declared_negative": declared_negative,
                "recomputed_negative": recomputed_negative,
                "amended_quantity": str(amended),
                "accumulated_quantity": str(line.accumulated_quantity),
                "amended_is_derived": line.amended_is_derived,
            },
        )
    if line.balance_quantity != expected:
        yield _line_finding(
            "CONTRACT_BALANCE_MISMATCH",
            parse,
            line,
            ref=ref,
            declared=str(line.balance_quantity),
            expected=str(expected),
            detail={
                "amended_quantity": str(amended),
                "accumulated_quantity": str(line.accumulated_quantity),
                "amended_is_derived": line.amended_is_derived,
            },
        )


def _amendment_line_findings(
    parse: ContractParse,
    line: ParsedContractLine,
    deltas: Mapping[str, Decimal],
    ambiguous: bool,
) -> Iterator[SemanticFinding]:
    """O que as RE-RA fazem com esta linha, e o que a aba da prefeitura declara sobre ela.

    `AMENDMENT_APPLICATION_MISMATCH` só existe para vigente **declarado** na GERAL: onde o
    vigente é derivado, comparar derivado com a própria derivação seria tautologia.
    """
    delta = deltas.get(line.code, _ZERO)
    expected = line.contract_quantity + delta
    if expected < 0:
        yield _line_finding(
            "AMENDMENT_NEGATIVE_RESULT",
            parse,
            line,
            ref=_ref(parse.contract_quantity_column, line.row),
            declared=str(line.contract_quantity),
            expected=str(expected),
            detail={"delta": str(delta)},
        )
    if line.amended_quantity is not None and line.amended_quantity != expected:
        yield _line_finding(
            "AMENDMENT_APPLICATION_MISMATCH",
            parse,
            line,
            ref=_ref(parse.amended_column, line.row),
            declared=str(line.amended_quantity),
            expected=str(expected),
            detail={"delta": str(delta), "contract_quantity": str(line.contract_quantity)},
        )
    declared = parse.declared_amended.get(line.code)
    if declared is None or ambiguous:
        return
    resolved = line.resolved_amended_quantity(deltas)
    if resolved != declared:
        yield _line_finding(
            "GENERAL_AMENDED_DIVERGENT",
            parse,
            line,
            ref=_ref(parse.amended_column, line.row),
            declared=str(declared),
            expected=str(resolved),
            detail={
                "amendment_sheet": parse.amendment_sheet,
                "general": str(resolved),
                "amended_is_derived": line.amended_is_derived,
            },
        )


def _line_findings(
    parse: ContractParse,
    line: ParsedContractLine,
    deltas: Mapping[str, Decimal],
    lines_by_code: Mapping[str, Sequence[ParsedContractLine]],
) -> Iterator[SemanticFinding]:
    """Todos os achados de uma linha, na ordem em que a linha é conferida."""
    yield from _negative_value_findings(parse, line)
    yield from _period_findings(parse, line)
    yield from _accumulated_findings(parse, line)
    yield from _balance_findings(parse, line, line.resolved_amended_quantity(deltas))
    ambiguous = len(lines_by_code.get(line.code, ())) > 1
    yield from _amendment_line_findings(parse, line, deltas, ambiguous)


def _duplicate_findings(parse: ContractParse) -> Iterator[SemanticFinding]:
    """Chave composta grupo+item e grupo+código: o mesmo código em outro grupo é legítimo."""
    checks: tuple[tuple[str, Callable[[ParsedContractLine], str], str | None], ...] = (
        ("CONTRACT_DUPLICATE_ITEM", lambda line: line.item_number, parse.item_column),
        ("CONTRACT_DUPLICATE_CODE", lambda line: line.code, parse.code_column),
    )
    for finding_code, key_of, column in checks:
        first_row: dict[tuple[str, str], int] = {}
        reported: set[tuple[str, str]] = set()
        for line in parse.lines:
            key = (line.group_label, key_of(line))
            if key not in first_row:
                first_row[key] = line.row
                continue
            if key in reported:
                continue
            reported.add(key)
            yield _line_finding(
                finding_code,
                parse,
                line,
                ref=_ref(column, line.row),
                detail={"first_row": first_row[key]},
            )


def _ambiguous_code_findings(
    parse: ContractParse,
    deltas: Mapping[str, Decimal],
    lines_by_code: Mapping[str, Sequence[ParsedContractLine]],
) -> Iterator[SemanticFinding]:
    """Código repetido entre grupos sobre o qual a aba da prefeitura fala."""
    for code, lines in lines_by_code.items():
        if len(lines) < 2:
            continue
        if code not in deltas and code not in parse.declared_amended:
            continue
        yield SemanticFinding(
            finding_code="CODE_AMBIGUOUS_IN_CONTRACT",
            sheet=parse.general_sheet,
            code=code,
            detail={
                "groups": [line.group_label for line in lines],
                "rows": [line.row for line in lines],
                "has_delta": code in deltas,
                "has_declared_amended": code in parse.declared_amended,
            },
        )


def _amendment_block_findings(
    parse: ContractParse, lines_by_code: Mapping[str, Sequence[ParsedContractLine]]
) -> Iterator[SemanticFinding]:
    """Achados que são do bloco de RE-RA, não da linha do consolidado."""
    sheet = parse.amendment_sheet or parse.general_sheet
    for block in parse.amendment_blocks:
        first_row: dict[str, int] = {}
        reported: set[str] = set()
        for line in block.lines:
            targets = lines_by_code.get(line.code, ())
            if line.code in first_row and line.code not in reported:
                reported.add(line.code)
                yield SemanticFinding(
                    finding_code="AMENDMENT_DUPLICATE_CODE",
                    sheet=sheet,
                    row=line.row,
                    code=line.code,
                    detail={"label": block.label, "first_row": first_row[line.code]},
                )
            first_row.setdefault(line.code, line.row)
            target = targets[0] if targets else None
            if line.is_new_item:
                if target is None or target.contract_quantity != 0:
                    yield SemanticFinding(
                        finding_code="AMENDMENT_NEW_ITEM_INVALID",
                        sheet=sheet,
                        row=line.row,
                        code=line.code,
                        declared=None if target is None else str(target.contract_quantity),
                        detail={"label": block.label, "in_contract": target is not None},
                    )
            elif target is None:
                yield SemanticFinding(
                    finding_code="AMENDMENT_TARGET_UNKNOWN",
                    sheet=sheet,
                    row=line.row,
                    code=line.code,
                    detail={"label": block.label, "quantity_delta": str(line.quantity_delta)},
                )


def _summary(findings: Sequence[SemanticFinding]) -> dict[str, int]:
    """Contagem por classe, com as classes em ordem alfabética."""
    counted: dict[str, int] = {}
    for finding in findings:
        counted[finding.finding_code] = counted.get(finding.finding_code, 0) + 1
    return {code: counted[code] for code in sorted(counted)}


def diagnose_contract(parse: ContractParse) -> ContractDiagnosis:
    """Recomputa todos os invariantes semânticos e devolve o dossiê completo.

    Nunca levanta exceção: dado ruim vira achado. A ordem é a da planilha — cada linha com
    os seus achados, na ordem em que a linha é conferida — e só então os agregados
    (duplicatas, ambiguidade de código e blocos de RE-RA).
    """
    deltas = parse.amendment_deltas()
    lines_by_code = parse.lines_by_code()
    findings: list[SemanticFinding] = []
    for line in parse.lines:
        findings.extend(_line_findings(parse, line, deltas, lines_by_code))
    findings.extend(_duplicate_findings(parse))
    findings.extend(_ambiguous_code_findings(parse, deltas, lines_by_code))
    findings.extend(_amendment_block_findings(parse, lines_by_code))
    return ContractDiagnosis(findings=tuple(findings), summary=_summary(findings))
