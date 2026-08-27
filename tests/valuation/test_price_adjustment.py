"""Reajuste declarado sobre o consolidado (F-039, ADR-0055).

O que estes testes protegem, em ordem de gravidade: que o passado não se mova, que o preço
vigente seja derivado da declaração, e que uma declaração inconferível não entre.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest
from pydantic import ValidationError

from croquito_valuation.contract import (
    ContractLine,
    ContractWorkbook,
    PeriodProgress,
    PriceAdjustment,
)
from croquito_valuation.errors import valuation_error_codes

_CODE_A = "AD04050050(/)"
_CODE_B = "SP01050010(/)"
_SOURCE_SHA256 = "a" * 64
_CATALOG_SHA256 = "b" * 64
_DECLARED_AT = datetime(2026, 8, 27, 12, 0, tzinfo=UTC)


def _linha(
    code: str, unit_price: str, *, periods: list[PeriodProgress] | None = None
) -> ContractLine:
    lancados = periods or []
    quantidade = sum((item.quantity for item in lancados), Decimal("0.00"))
    valor = sum((item.amount for item in lancados), Decimal("0.00"))
    return ContractLine(
        group_label="PAVIMENTACAO",
        item_number="1" if code == _CODE_A else "2",
        code=code,
        description="TELA GALVANIZADA" if code == _CODE_A else "ALAMBRADO",
        unit="m2",
        unit_price=Decimal(unit_price),
        contract_quantity=Decimal("1000.00"),
        amended_quantity=Decimal("1000.00"),
        periods=lancados,
        accumulated_quantity=quantidade,
        accumulated_amount=valor,
        balance_quantity=Decimal("1000.00") - quantidade,
    )


def _consolidado(
    *,
    adjustments: list[PriceAdjustment] | None = None,
    lines: list[ContractLine] | None = None,
) -> ContractWorkbook:
    return ContractWorkbook(
        source_label="Consolidado sintético",
        source_sha256=_SOURCE_SHA256,
        period_numbers=[],
        lines=lines or [_linha(_CODE_A, "62.40"), _linha(_CODE_B, "118.00")],
        adjustments=adjustments or [],
    )


def _fator(valor: str, *, index_label: str = "INCC-DI") -> PriceAdjustment:
    return PriceAdjustment(
        kind="index_factor",
        declared_by="orcamentista@tenant-a",
        declared_at=_DECLARED_AT,
        reference_period="08/2025 a 07/2026",
        index_label=index_label,
        factor=Decimal(valor),
    )


def test_sem_reajuste_o_vigente_e_o_contratado_bit_a_bit() -> None:
    """O controle da feature: rodada sem declaração se comporta como antes dela existir."""
    consolidado = _consolidado()

    for linha in consolidado.lines:
        assert consolidado.current_unit_price(linha) == linha.unit_price
    assert consolidado.is_adjusted is False


def test_fator_de_indice_produz_o_vigente_com_dinheiro_truncado() -> None:
    """62,40 x 1,0432 = 65,095…, e dinheiro TRUNCA — nunca arredonda para 65,10."""
    consolidado = _consolidado(adjustments=[_fator("1.0432")])

    assert consolidado.current_unit_price(consolidado.lines[0]) == Decimal("65.09")
    assert consolidado.current_unit_price(consolidado.lines[1]) == Decimal("123.09")
    assert consolidado.is_adjusted is True


def test_fatores_compoem_sobre_o_ja_reajustado() -> None:
    """Reajuste anual incide sobre o preço já reajustado, não sobre o contratado original.

    Aplicar os dois fatores sobre o contratado daria 62,40 x (1,0432 + 0,05 - 1) — número que
    não existe em contrato nenhum. A composição é multiplicativa, e o truncamento acontece
    UMA vez, no fim: truncar a cada passo acumularia o erro do truncamento.
    """
    consolidado = _consolidado(adjustments=[_fator("1.0432"), _fator("1.0500")])

    exato = Decimal("62.40") * Decimal("1.0432") * Decimal("1.0500")
    assert consolidado.current_unit_price(consolidado.lines[0]) == Decimal("68.35")
    assert exato > Decimal("68.35")  # o truncamento desce, e é isso que se quer
    # Composição, não soma de percentuais.
    assert consolidado.current_unit_price(consolidado.lines[0]) > Decimal("65.09")


def test_versao_nova_da_tabela_substitui_o_preco() -> None:
    """`catalog_version` não é percentual sobre o contratado: é outro preço, e substitui."""
    consolidado = _consolidado(
        adjustments=[
            PriceAdjustment(
                kind="catalog_version",
                declared_by="orcamentista@tenant-a",
                declared_at=_DECLARED_AT,
                reference_period="data-base 07/2026",
                catalog_label="SCO-PCRJ 07/2026",
                catalog_sha256=_CATALOG_SHA256,
                prices_by_code={_CODE_A: Decimal("65.90"), _CODE_B: Decimal("123.15")},
            )
        ]
    )

    assert consolidado.current_unit_price(consolidado.lines[0]) == Decimal("65.90")
    assert consolidado.current_unit_price(consolidado.lines[1]) == Decimal("123.15")


def test_fator_declarado_depois_da_versao_incide_sobre_ela() -> None:
    """A ordem declarada manda: a versão nova reseta a base, e o fator seguinte compõe nela."""
    consolidado = _consolidado(
        adjustments=[
            PriceAdjustment(
                kind="catalog_version",
                declared_by="orcamentista@tenant-a",
                declared_at=_DECLARED_AT,
                reference_period="data-base 07/2026",
                catalog_label="SCO-PCRJ 07/2026",
                catalog_sha256=_CATALOG_SHA256,
                prices_by_code={_CODE_A: Decimal("65.90"), _CODE_B: Decimal("123.15")},
            ),
            _fator("1.1000"),
        ]
    )

    assert consolidado.current_unit_price(consolidado.lines[0]) == Decimal("72.49")


def test_versao_nova_precisa_precificar_todo_codigo_contratado() -> None:
    """Reprecificar metade do contrato é pior do que não reprecificar."""
    with pytest.raises(ValidationError) as erro:
        _consolidado(
            adjustments=[
                PriceAdjustment(
                    kind="catalog_version",
                    declared_by="orcamentista@tenant-a",
                    declared_at=_DECLARED_AT,
                    reference_period="data-base 07/2026",
                    catalog_label="SCO-PCRJ 07/2026",
                    catalog_sha256=_CATALOG_SHA256,
                    prices_by_code={_CODE_A: Decimal("65.90")},
                )
            ]
        )

    assert valuation_error_codes(erro.value) == ["PRICE_ADJUSTMENT_CODE_MISSING"]


def test_o_passado_nao_se_move_com_o_reajuste() -> None:
    """Período já lançado guarda o valor que valeu, e o acumulado soma bases diferentes."""
    linha = _linha(
        _CODE_A,
        "62.40",
        periods=[
            PeriodProgress(period_number=1, quantity=Decimal("80.00"), amount=Decimal("4992.00")),
            PeriodProgress(
                period_number=2,
                quantity=Decimal("120.00"),
                amount=Decimal("7810.80"),
                # O período 2 foi medido JÁ reajustado, e declara o preço dele.
                unit_price=Decimal("65.09"),
            ),
        ],
    )
    consolidado = ContractWorkbook(
        source_label="Consolidado sintético",
        source_sha256=_SOURCE_SHA256,
        period_numbers=[1, 2],
        lines=[linha],
        adjustments=[_fator("1.0432")],
    )

    # O período 1 foi medido a 62,40 e continua valendo isso; o 2, a 65,09.
    assert linha.periods[0].amount == Decimal("4992.00")
    assert linha.periods[1].amount == Decimal("7810.80")
    assert linha.expected_accumulated_amount == Decimal("12802.80")
    # E o contratado original também não se move: o vigente é derivado dele.
    assert linha.unit_price == Decimal("62.40")
    assert consolidado.current_unit_price(linha) == Decimal("65.09")


class TestDeclaracaoInconferivel:
    """Recusas da declaração: o sistema não valida o VALOR do índice, mas exige que ele seja
    conferível contra a publicação oficial por quem revisa."""

    def test_fator_sem_indice_recusa(self) -> None:
        with pytest.raises(ValidationError) as erro:
            PriceAdjustment(
                kind="index_factor",
                declared_by="orcamentista@tenant-a",
                declared_at=_DECLARED_AT,
                reference_period="08/2025 a 07/2026",
                factor=Decimal("1.0432"),
            )

        assert valuation_error_codes(erro.value) == ["PRICE_ADJUSTMENT_INDEX_INCOMPLETE"]

    def test_fator_nao_positivo_recusa(self) -> None:
        """Zero não é "sem reajuste": sem reajuste é não declarar."""
        with pytest.raises(Exception) as erro:
            PriceAdjustment(
                kind="index_factor",
                declared_by="orcamentista@tenant-a",
                declared_at=_DECLARED_AT,
                reference_period="08/2025 a 07/2026",
                index_label="INCC-DI",
                factor=Decimal("0"),
            )

        assert "factor" in str(erro.value)

    def test_instante_sem_fuso_recusa(self) -> None:
        with pytest.raises(ValidationError) as erro:
            PriceAdjustment(
                kind="index_factor",
                declared_by="orcamentista@tenant-a",
                declared_at=datetime(2026, 8, 27, 12, 0),
                reference_period="08/2025 a 07/2026",
                index_label="INCC-DI",
                factor=Decimal("1.0432"),
            )

        assert valuation_error_codes(erro.value) == ["PRICE_ADJUSTMENT_TIMESTAMP_NAIVE"]

    def test_os_dois_mecanismos_nao_se_misturam(self) -> None:
        """Fator com digest de tabela seria duas declarações fingindo ser uma."""
        with pytest.raises(ValidationError) as erro:
            PriceAdjustment(
                kind="index_factor",
                declared_by="orcamentista@tenant-a",
                declared_at=_DECLARED_AT,
                reference_period="08/2025 a 07/2026",
                index_label="INCC-DI",
                factor=Decimal("1.0432"),
                catalog_sha256=_CATALOG_SHA256,
                prices_by_code={_CODE_A: Decimal("65.90")},
            )

        assert valuation_error_codes(erro.value) == ["PRICE_ADJUSTMENT_KIND_MISMATCH"]

    def test_versao_sem_digest_recusa(self) -> None:
        """Preço sem a versão de onde saiu não é auditável meses depois."""
        with pytest.raises(ValidationError) as erro:
            PriceAdjustment(
                kind="catalog_version",
                declared_by="orcamentista@tenant-a",
                declared_at=_DECLARED_AT,
                reference_period="data-base 07/2026",
                prices_by_code={_CODE_A: Decimal("65.90")},
            )

        assert valuation_error_codes(erro.value) == ["PRICE_ADJUSTMENT_CATALOG_INCOMPLETE"]


def test_consolidado_antigo_continua_validando_sem_reajuste() -> None:
    """`2.0.0` gravado antes da F-039: responde sem reajuste, que é a verdade sobre ele."""
    antigo = ContractWorkbook.model_validate(
        {
            "schema_version": "2.0.0",
            "source_label": "Consolidado anterior",
            "source_sha256": _SOURCE_SHA256,
            "period_numbers": [],
            "lines": [_linha(_CODE_A, "62.40").model_dump(mode="json")],
        }
    )

    assert antigo.adjustments == []
    assert antigo.current_unit_price(antigo.lines[0]) == Decimal("62.40")
