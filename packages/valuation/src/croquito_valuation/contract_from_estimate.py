"""Orçamento assinado → consolidado contratual da medição (F-036, ADR-0048).

Sob o regime `contracted_demand` não há licitação entre o orçamento e o contrato: a demanda é
orçada pela tabela do contrato guarda-chuva que já foi licitado. É o único regime em que
chamar o orçamento de contratado não é mentira, e é por isso que esta tradução existe só para
ele — quem restringe é o chamador, porque o `pricing_regime` é dado da RODADA e não do
`Estimate`.

O que este módulo resolve, e que a cadeia da `/v1` não tinha:
`bulletin_export_contract` (`croquito_api.valuation_rounds`) fabrica o consolidado a partir da
própria medição, o que deixa seis guardrails inertes — `BALANCE_EXCEEDED`,
`CODE_NOT_IN_CONTRACT`, `PERIOD_NOT_SEQUENTIAL`, `CODE_AMBIGUOUS_IN_CONTRACT`,
`LINE_PRICE_NOT_IN_CONTRACT` e `LINE_UNIT_NOT_IN_CONTRACT`. Com um consolidado de origem
assinada eles passam a ter o fato que os alimenta.

Três decisões do ADR-0048 vivem aqui, e nenhuma é detalhe:

1. **Preço de FONTE, nunca o preço com BDI** (decisão 2). Sob o regime, `unit_price` é a
   tabela contratual, e é o mesmo número que o boletim imprimirá, porque o boletim precifica
   pelo catálogo `sco` instalado. Assim `BulletinLine.unit_price == ContractLine.unit_price`
   passa a valer por construção — os dois lados leem o mesmo catálogo — em vez de por
   coincidência.
2. **Agrega por código** (decisão 4). `Estimate.validate_lines` recusa `item_number` repetido,
   **não** código repetido: o mesmo serviço em dois trechos da prancha é itemizado duas vezes
   com o mesmo código SCO, e o consolidado tem chave única grupo+código. Somar só é lícito
   porque a cascata do regime tem uma fonte só; preço ou unidade divergentes no mesmo código
   recusam em vez de escolher uma das linhas.
3. **Grupo único e `contract_label` ausente** (decisão 5 e lacuna 4 do ADR-0045). O orçamento
   não modela contrato como entidade; preencher o rótulo do contrato aqui afirmaria uma
   identidade que ninguém conferiu.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Final

from croquito_valuation.contract import ContractLine, ContractWorkbook
from croquito_valuation.errors import ValuationValidationError
from croquito_valuation.estimate import Estimate, EstimateLine

ZERO: Final = Decimal("0.00")


class _Aggregate:
    """Acumulador de um código: a primeira linha manda no texto, as demais só somam."""

    __slots__ = ("code", "description", "quantity", "unit", "unit_price")

    def __init__(self, line: EstimateLine) -> None:
        self.code = line.code
        self.description = line.description
        self.unit = line.unit
        self.unit_price = line.unit_price
        self.quantity = line.quantity

    def absorb(self, line: EstimateLine) -> None:
        if line.unit_price != self.unit_price or line.unit != self.unit:
            raise ValuationValidationError(
                "ESTIMATE_CODE_PRICE_CONFLICT",
                "o mesmo código aparece no orçamento com preço ou unidade diferentes",
                {
                    "code": self.code,
                    "unit": self.unit,
                    "conflicting_unit": line.unit,
                    "unit_price": str(self.unit_price),
                    "conflicting_unit_price": str(line.unit_price),
                    "item_number": line.item_number,
                },
            )
        self.quantity += line.quantity


def build_contract_from_estimate(
    estimate: Estimate,
    *,
    group_label: str,
    source_label: str,
) -> ContractWorkbook:
    """Consolidado contratual da PRIMEIRA medição de uma obra orçada sob contrato.

    O portão do orçamento vem primeiro: sem assinatura válida não há conteúdo aprovado de onde
    tirar o contratado, e `ensure_exportable()` já sabe recusar as três formas disso —
    nunca assinado, assinatura rejeitada e digest caduco por remontagem. Não se inventa código
    novo para condição que o despacho já nomeia.

    Nenhum período é lançado: esta é a primeira medição, então `periods` é vazio, o acumulado é
    zero e o saldo é o contratado inteiro. A segunda medição em diante precisa somar o que já
    foi aprovado (ADR-0048, decisão 8) e é trabalho de quem a construir — esta função não ganha
    parâmetro que nenhum chamador usa hoje.
    """
    estimate.ensure_exportable()
    approval = estimate.approval
    # `ensure_exportable()` acima já recusou o caso `None`; a asserção existe para o type
    # checker e documenta a dependência entre as duas linhas.
    assert approval is not None

    # `dict` preserva a ordem de inserção, então a ordem de leitura do orçamento é a ordem
    # das linhas do consolidado — sem lista paralela que possa divergir da chave.
    aggregates: dict[str, _Aggregate] = {}
    for line in estimate.lines:
        existing = aggregates.get(line.code)
        if existing is None:
            aggregates[line.code] = _Aggregate(line)
        else:
            existing.absorb(line)

    lines = [
        ContractLine(
            group_label=group_label,
            item_number=str(index),
            code=aggregate.code,
            description=aggregate.description,
            unit=aggregate.unit,
            # Preço de FONTE. Trocar por `unit_price_with_bdi` faria toda linha do boletim
            # disparar `LINE_PRICE_NOT_IN_CONTRACT` no primeiro uso.
            unit_price=aggregate.unit_price,
            contract_quantity=aggregate.quantity,
            # Vigente e saldo são derivados (ADR-0056, decisão 3). Sem RE-RA antes da primeira
            # medição, `current_quantity` devolve o contratado e o saldo é o contratado inteiro;
            # não se grava aqui um segundo dono do número.
            periods=[],
            accumulated_quantity=ZERO,
            accumulated_amount=ZERO,
        )
        for index, aggregate in enumerate(aggregates.values(), start=1)
    ]

    return ContractWorkbook(
        source_label=source_label,
        # O digest do conteúdo ASSINADO, não o da medição: quem encontrar este consolidado
        # consegue dizer contra o que a obra está sendo medida.
        source_sha256=approval.estimate_digest,
        contract_label=None,
        period_numbers=[],
        lines=lines,
    )
