"""Critério de escopo: leitura da declaração, issue crítica e os dois atos de declaração.

O helper é o único construtor da issue de critério nos dois motores de geometria e na
aprovação; um defeito aqui apaga o portão do critério em todos eles de uma vez.
"""

from __future__ import annotations

from uuid import NAMESPACE_URL, UUID, uuid5

import pytest

from croquito_core.models import Issue, IssueSeverity, IssueStatus
from croquito_worker.criteria import (
    FALLBACK_CRITERION_MESSAGE,
    ScopeCriterionError,
    apply_criteria_declarations,
    parse_criterion_declaration,
    scope_criteria_issues,
)

CODE = "ACC_GUA_001"
TEXT = "Perímetro, linha central, círculo, áreas e gols são entidades CAD limpas."


def _fixed_uuid(code: str) -> UUID:
    return uuid5(NAMESPACE_URL, f"croquito:teste:{code}")


def test_declaracao_aceita_codigo_puro_e_codigo_com_texto() -> None:
    assert parse_criterion_declaration(CODE) == parse_criterion_declaration(f" {CODE} ")
    assert parse_criterion_declaration(CODE).text is None
    com_texto = parse_criterion_declaration(f"{CODE}={TEXT}")
    assert com_texto.code == CODE
    assert com_texto.text == TEXT
    # O texto pode conter `=`: o corte é no primeiro separador, não em todos.
    assert parse_criterion_declaration(f"{CODE}=a = b").text == "a = b"


@pytest.mark.parametrize(
    ("declaration", "expected_code"),
    [
        ("acc-gua-001", "INVALID_CRITERION_CODE"),
        ("=texto sem código", "INVALID_CRITERION_CODE"),
        (f"{CODE}=", "INVALID_CRITERION_TEXT"),
        (f"{CODE}={'x' * 501}", "INVALID_CRITERION_TEXT"),
    ],
)
def test_declaracao_recusa_fora_do_contrato(declaration: str, expected_code: str) -> None:
    with pytest.raises(ScopeCriterionError) as refusal:
        parse_criterion_declaration(declaration)
    assert refusal.value.code == expected_code


def test_issue_do_criterio_usa_o_texto_do_caso_e_a_frase_padrao() -> None:
    issues = scope_criteria_issues([CODE, "ACC_GUA_002"], {CODE: TEXT})
    assert [issue.code for issue in issues] == [CODE, "ACC_GUA_002"]
    assert all(issue.severity is IssueSeverity.CRITICAL for issue in issues)
    assert all(issue.status is IssueStatus.OPEN for issue in issues)
    assert issues[0].message == TEXT
    assert issues[1].message == FALLBACK_CRITERION_MESSAGE


def test_issue_do_criterio_aceita_id_deterministico() -> None:
    first = scope_criteria_issues([CODE], {}, id_factory=lambda code: _fixed_uuid(code))
    second = scope_criteria_issues([CODE], {}, id_factory=lambda code: _fixed_uuid(code))
    assert first[0].id == second[0].id
    # Sem fábrica o id vem do contrato e não se repete entre cenas.
    assert scope_criteria_issues([CODE], {})[0].id != scope_criteria_issues([CODE], {})[0].id


def test_declaracoes_separam_coberto_de_pendente_e_preservam_o_resto() -> None:
    issues = [
        Issue(code=CODE, severity=IssueSeverity.CRITICAL, message=TEXT),
        Issue(code="ACC_GUA_002", severity=IssueSeverity.CRITICAL, message="Layers distintos."),
        Issue(
            code="MEASUREMENT_MISMATCH",
            severity=IssueSeverity.CRITICAL,
            message="Cota confirmada incompatível com a geometria.",
        ),
    ]

    declared = apply_criteria_declarations(issues, covered=[CODE], acknowledged=["ACC_GUA_002"])

    assert declared[0].status is IssueStatus.RESOLVED
    assert declared[1].status is IssueStatus.ACCEPTED
    # Blocker de geometria não declarado continua aberto, e a lista de entrada é imutável.
    assert declared[2].status is IssueStatus.OPEN
    assert all(issue.status is IssueStatus.OPEN for issue in issues)
