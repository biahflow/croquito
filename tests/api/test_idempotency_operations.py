"""Portão da classe do defeito: nenhuma operação de idempotência pode passar da coluna.

As rotas montam a chave de idempotência por interpolação
(`field-evidence.classification:{job_id}:{origin}:{evidence_id}`) e gravam o resultado em
`idempotency_records.operation`. Em PostgreSQL um valor mais longo que a coluna é
`StringDataRightTruncation` — HTTP 500 na cara de quem clicou. Em SQLite, o banco desta
suíte, o limite do `VARCHAR` é simplesmente **ignorado**: nenhum teste funcional denuncia o
estouro, e foi assim que a coluna `VARCHAR(80)` conviveu com nove operações maiores que ela
até chegar em produção.

Este módulo não testa uma rota: testa a CLASSE. Ele lê `main.py` como árvore sintática,
resolve o valor de `operation` em cada chamada aos dois auxiliares de idempotência,
substitui cada campo pelo maior valor realista que ele pode assumir e reprova quando alguma
operação passa de `IDEMPOTENCY_OPERATION_MAX_LENGTH` — a MESMA constante que declara a
coluna, importada daqui para que o número não exista em dois lugares.

Ler a árvore em vez de casar texto é o que torna o portão exaustivo: a varredura falha
alto quando encontra uma chamada cujo `operation` ela não sabe resolver, em vez de
silenciosamente deixar essa operação de fora da conta.
"""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Final

import pytest
from sqlalchemy import String
from sqlalchemy.orm import DeclarativeBase

from croquito_api import main as api_main
from croquito_api.database import (
    IDEMPOTENCY_OPERATION_MAX_LENGTH,
    ElementProposalRejectionRecord,
    IdempotencyRecord,
    ReviewElementSuggestionRejectionRecord,
)
from croquito_api.journeys import JOURNEYS

#: Os dois auxiliares que leem e gravam `idempotency_records`. Toda chamada a eles carrega
#: um `operation=`, e é esse conjunto que define o universo do portão.
IDEMPOTENCY_HELPERS: Final = frozenset({"_idempotent_response", "_store_idempotent_response"})

_SOURCE: Final = Path(api_main.__file__)


def column_max_length(column: str, model: type[DeclarativeBase] = IdempotencyRecord) -> int:
    """Largura declarada de uma coluna, lida do próprio modelo.

    O `model` existe porque nem todo campo que entra numa operação é limitado pela tabela de
    idempotência: `proposal_id` é limitado pela tabela que guarda a recusa da proposta. Ler
    do modelo dono do campo, e não repetir o número aqui, é o que mantém o portão honesto
    quando a coluna mudar de largura.

    Também usada por `tests/api/test_migrations.py`, que precisa do maior `tenant_id` que
    cabe no registro para montar a operação longa da prova em PostgreSQL. Ler do modelo, e
    não repetir o número, é o que impede as duas metades do portão de divergirem.
    """
    tipo = model.__table__.c[column].type
    assert isinstance(tipo, String), f"`{column}` deixou de ser texto de largura declarada"
    assert tipo.length is not None, f"`{column}` perdeu a largura declarada"
    return tipo.length


#: Comprimento de um UUID canônico com hífens. Todo id de recurso que entra numa operação é
#: `UUID` no parâmetro de rota (ou `str` limitado a 36, no caso de `survey_id`).
_UUID_LENGTH: Final = 36

#: `origin` é `Literal["survey", "standalone"]` em rota e em payload; o maior valor tem 10.
_ORIGIN_MAX: Final = max(len(value) for value in ("survey", "standalone"))

#: O maior valor realista de cada campo que aparece numa operação, pela chave que o código
#: usa na interpolação. Campo novo sem entrada aqui REPROVA o teste de propósito: decidir o
#: máximo de um campo é ato consciente, não default silencioso.
_FIELD_MAX_LENGTHS: Final[dict[str, int]] = {
    "estimate_template_id": _UUID_LENGTH,
    "evidence_id": _UUID_LENGTH,
    "job_id": _UUID_LENGTH,
    "payload.evidence_id": _UUID_LENGTH,
    "photo_id": _UUID_LENGTH,
    "reference_catalog_id": _UUID_LENGTH,
    "reference_catalog_index_id": _UUID_LENGTH,
    "round_id": _UUID_LENGTH,
    "session_id": _UUID_LENGTH,
    "site_setup_kit_id": _UUID_LENGTH,
    "survey_id": _UUID_LENGTH,
    "origin": _ORIGIN_MAX,
    "payload.origin": _ORIGIN_MAX,
    # Jornadas são um `Literal` fechado — o teto é o maior nome que existe.
    "journey": max(len(journey) for journey in JOURNEYS),
    # `tenant_id` chega pela rota nas duas operações de plataforma, sem limite declarado no
    # parâmetro. Quem o limita de fato é a própria tabela: um tenant maior que a coluna
    # `idempotency_records.tenant_id` não caberia no registro de jeito nenhum.
    "tenant_id": column_max_length("tenant_id"),
    # `proposal_id` (F-047 T6) é o hash determinístico do conjunto de entidades da proposta,
    # e quem o limita é a coluna que o guarda — a mesma régua do `tenant_id` acima.
    "proposal_id": column_max_length("proposal_id", ElementProposalRejectionRecord),
    # `suggestion_id` (F-051 T3) é o gêmeo, uma etapa antes: o hash determinístico do
    # conjunto de propostas da sugestão, limitado pela coluna que guarda a recusa dela.
    "suggestion_id": column_max_length("suggestion_id", ReviewElementSuggestionRejectionRecord),
}


class _UnresolvedOperation(Exception):
    """A varredura encontrou um `operation=` que ela não sabe transformar em gabarito."""


def _own_nodes(node: ast.AST) -> list[ast.AST]:
    """Nós dentro de `node`, sem entrar em função ou classe aninhada (elas viram escopo)."""
    nodes: list[ast.AST] = []
    for child in ast.iter_child_nodes(node):
        nodes.append(child)
        if isinstance(child, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
            continue
        nodes.extend(_own_nodes(child))
    return nodes


def _template(expr: ast.expr, scopes: list[dict[str, ast.expr]], seen: frozenset[str]) -> str:
    """O gabarito da operação: literais como estão, campos como `{nome}`.

    Aceita literal, f-string e nome resolvível a uma das duas coisas. Qualquer outra forma
    é erro alto — uma operação montada por caminho que a varredura não entende ficaria fora
    da conta, e o portão passaria a mentir.
    """
    if isinstance(expr, ast.Constant) and isinstance(expr.value, str):
        return expr.value
    if isinstance(expr, ast.JoinedStr):
        parts: list[str] = []
        for piece in expr.values:
            if isinstance(piece, ast.Constant):
                parts.append(str(piece.value))
            elif isinstance(piece, ast.FormattedValue):
                parts.append("{" + ast.unparse(piece.value) + "}")
            else:  # pragma: no cover - forma que o Python não produz numa f-string
                raise _UnresolvedOperation(f"pedaço inesperado de f-string: {ast.dump(piece)}")
        return "".join(parts)
    if isinstance(expr, ast.Name):
        if expr.id in seen:
            raise _UnresolvedOperation(f"`{expr.id}` se define em círculo")
        for scope in scopes:
            if expr.id in scope:
                return _template(scope[expr.id], scopes, seen | {expr.id})
        raise _UnresolvedOperation(f"nome `{expr.id}` sem atribuição visível")
    raise _UnresolvedOperation(f"forma não suportada: {ast.unparse(expr)}")


def _helper_name(call: ast.Call) -> str | None:
    if isinstance(call.func, ast.Name):
        return call.func.id
    if isinstance(call.func, ast.Attribute):
        return call.func.attr
    return None


def _scan(node: ast.AST, parents: list[dict[str, ast.expr]]) -> list[tuple[int, str]]:
    """Percorre um escopo, resolve as chamadas dele e desce para os escopos aninhados."""
    assignments: dict[str, ast.expr] = {}
    for inner in _own_nodes(node):
        if isinstance(inner, ast.Assign):
            for target in inner.targets:
                if isinstance(target, ast.Name):
                    assignments[target.id] = inner.value
        elif (
            isinstance(inner, ast.AnnAssign)
            and isinstance(inner.target, ast.Name)
            and inner.value is not None
        ):
            assignments[inner.target.id] = inner.value

    scopes = [assignments, *parents]
    found: list[tuple[int, str]] = []
    for inner in _own_nodes(node):
        if isinstance(inner, ast.Call) and _helper_name(inner) in IDEMPOTENCY_HELPERS:
            keywords = [keyword for keyword in inner.keywords if keyword.arg == "operation"]
            if len(keywords) != 1:
                raise _UnresolvedOperation(
                    f"{_SOURCE.name}:{inner.lineno} chama o auxiliar de idempotência sem um "
                    "único `operation=` nomeado"
                )
            try:
                found.append((inner.lineno, _template(keywords[0].value, scopes, frozenset())))
            except _UnresolvedOperation as error:
                raise _UnresolvedOperation(f"{_SOURCE.name}:{inner.lineno}: {error}") from error
        if isinstance(inner, ast.FunctionDef | ast.AsyncFunctionDef):
            found.extend(_scan(inner, scopes))
    return found


def _call_sites() -> list[tuple[int, str]]:
    return _scan(ast.parse(_SOURCE.read_text(encoding="utf-8")), [])


def _worst_case_length(template: str) -> int:
    """Comprimento do gabarito com cada campo no seu maior valor realista."""
    length = len(template)
    for piece in template.split("{")[1:]:
        field = piece.split("}")[0]
        if field not in _FIELD_MAX_LENGTHS:
            pytest.fail(
                f"A operação `{template}` usa o campo `{field}`, que não tem máximo "
                f"declarado em `_FIELD_MAX_LENGTHS`. Declare o maior valor que ele pode "
                f"assumir — sem isso o portão deixaria de medir esta operação."
            )
        length += _FIELD_MAX_LENGTHS[field] - len(field) - len("{}")
    return length


def test_a_varredura_enxerga_o_mecanismo_de_idempotencia() -> None:
    """Guarda contra vacuidade: um portão que não acha nada passa sem medir nada.

    Se alguém renomear os auxiliares ou trocar o mecanismo, a varredura devolveria lista
    vazia e o teste de comprimento passaria por não ter o que reprovar. Estas asserções são
    o que transforma esse cenário em falha visível.
    """
    source = ast.parse(_SOURCE.read_text(encoding="utf-8"))
    defined = {
        node.name
        for node in ast.walk(source)
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef)
    }
    assert defined >= IDEMPOTENCY_HELPERS, (
        "Os auxiliares de idempotência não existem mais com estes nomes em `main.py`. "
        "Atualize `IDEMPOTENCY_HELPERS`, ou este portão para de olhar para o mecanismo."
    )

    call_sites = _call_sites()
    assert len(call_sites) >= 100, (
        f"A varredura achou só {len(call_sites)} chamadas de idempotência; a API tem mais de "
        "cem. Uma queda dessas significa que o mecanismo mudou de forma e a varredura "
        "parou de enxergá-lo."
    )
    assert len({template for _, template in call_sites}) >= 30


def test_toda_operacao_de_idempotencia_cabe_na_coluna() -> None:
    """A classe inteira do defeito: nenhuma operação estoura a largura da coluna.

    Sem o alargamento da `0023` este teste reprova com nove operações, a pior delas 87
    caracteres além do teto de 80 que a coluna tinha.
    """
    medidas = {template: _worst_case_length(template) for _, template in _call_sites()}
    estouros = sorted(
        (
            (template, length)
            for template, length in medidas.items()
            if length > IDEMPOTENCY_OPERATION_MAX_LENGTH
        ),
        key=lambda item: -item[1],
    )
    detalhe = "\n".join(
        f"  {length:4d} caracteres ({length - IDEMPOTENCY_OPERATION_MAX_LENGTH} além do "
        f"teto): {template}"
        for template, length in estouros
    )
    assert not estouros, (
        f"{len(estouros)} operação(ões) de idempotência passam de "
        f"`IDEMPOTENCY_OPERATION_MAX_LENGTH` ({IDEMPOTENCY_OPERATION_MAX_LENGTH}) com os "
        f"maiores valores realistas de cada campo. Em PostgreSQL isso é HTTP 500 na rota, e "
        f"o SQLite desta suíte não denuncia:\n{detalhe}"
    )
