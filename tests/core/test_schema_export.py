"""Portões do exportador de contratos multi-modelo (F-003).

O drift check de `make check` compara o schema versionado com o gerado — ele prova que os
dois concordam, **não** que o gerado está certo. Se uma versão do Pydantic mudar o formato
que o exportador reconhece, o colapso de `ExactDecimal` para de acontecer, `make contracts`
regenera com `number` de volta e o drift check continua verde. Estes testes são o portão que
falta: eles olham o conteúdo, não a igualdade.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from croquito_core.schema_export import (
    DEFAULT_MANIFEST,
    _collapse_exact_decimal,
    schema_text_for,
)

MANIFEST_ENTRIES: list[dict[str, Any]] = json.loads(DEFAULT_MANIFEST.read_text(encoding="utf-8"))

DECIMAL_STRING_PATTERN = r"^(?!^[-+.]*$)[+-]?0*\d*\.?\d*$"

MONEY_AND_QUANTITY_FIELDS = frozenset(
    {
        "unit_price",
        "quantity",
        "total",
        "subtotal",
        "value",
        "total_quantity",
        "total_amount",
    }
)
"""Campos que o domínio guarda em `Decimal` porque a precisão escrita da cota importa.

Dinheiro trunca em duas casas e `float` é recusado na fronteira (ADR-0016). Um destes
campos aceitando `number` no schema vira `number | string` em TypeScript e reabre, na
tela, a porta que o domínio fecha em runtime.  Campo opcional sai como `string | null`,
que é válido: o proibido é o ramo `number`, não a ausência de valor.
"""

DECIMAL_UNION_BASELINE: dict[str, str] = {
    "SceneRevision.value_si": (
        "`Decimal | None` gera anyOf de TRÊS ramos (number, string, null) e escapa do "
        "colapso, que só reconhece dois.  É defeito real, e é do contexto do croqui: "
        "corrigi-lo muda `scene.generated.ts`, contrato vivo de `apps/web`, fora do escopo "
        "de F-003.  Fica declarado em vez de silenciado — como a `BASELINE` do gate de "
        "OpenAPI, esta lista só pode encolher."
    ),
}
"""Uniões `number | string` que sobrevivem hoje, cada uma com a razão de não ser corrigida.

Acrescentar chave aqui para silenciar falha nova nunca é uso válido desta constante.
"""


def _walk_properties(node: Any) -> list[tuple[str, dict[str, Any]]]:
    """Todo par (nome da propriedade, subschema) em qualquer profundidade do documento."""
    found: list[tuple[str, dict[str, Any]]] = []
    if isinstance(node, dict):
        properties = node.get("properties")
        if isinstance(properties, dict):
            for name, spec in properties.items():
                if isinstance(spec, dict):
                    found.append((str(name), spec))
        for value in node.values():
            found.extend(_walk_properties(value))
    elif isinstance(node, list):
        for item in node:
            found.extend(_walk_properties(item))
    return found


def _accepts_number(spec: dict[str, Any]) -> bool:
    """O subschema admite `number` — direto ou como ramo de união."""
    if spec.get("type") == "number":
        return True
    any_of = spec.get("anyOf")
    if isinstance(any_of, list):
        return any(isinstance(branch, dict) and branch.get("type") == "number" for branch in any_of)
    return False


@pytest.mark.parametrize("entry", MANIFEST_ENTRIES, ids=lambda e: str(e["model"]))
def test_dinheiro_e_quantidade_nunca_aceitam_numero(entry: dict[str, Any]) -> None:
    """Nenhum campo monetário do manifesto pode chegar ao TypeScript aceitando `number`."""
    schema = json.loads(schema_text_for(entry))

    ofensores = [
        f"{name}: {json.dumps(spec, sort_keys=True)}"
        for name, spec in _walk_properties(schema)
        if name in MONEY_AND_QUANTITY_FIELDS
        and _accepts_number(spec)
        and f"{entry['model']}.{name}" not in DECIMAL_UNION_BASELINE
    ]

    assert ofensores == [], (
        f"{entry['model']}: campo de dinheiro/quantidade aceitando `number`. Gerado assim, "
        "o tipo TypeScript admite `float` — exatamente o que o domínio recusa na fronteira. "
        "Confira o colapso de `ExactDecimal` em `croquito_core.schema_export`.\n"
        + "\n".join(ofensores)
    )


@pytest.mark.parametrize("entry", MANIFEST_ENTRIES, ids=lambda e: str(e["model"]))
def test_nenhum_decimal_sobrevive_como_uniao(entry: dict[str, Any]) -> None:
    """Pega campo `Decimal` NOVO, que ninguém lembrou de acrescentar à lista acima.

    A assinatura que o Pydantic emite para `Decimal` é um `anyOf` com um ramo `number` e um
    ramo `string` com o pattern do decimal. Sobreviver a esse formato é o defeito, tenha o
    campo o nome que tiver.
    """
    schema = json.loads(schema_text_for(entry))

    sobreviventes = []
    for name, spec in _walk_properties(schema):
        any_of = spec.get("anyOf")
        if not isinstance(any_of, list):
            continue
        tem_number = any(isinstance(b, dict) and b.get("type") == "number" for b in any_of)
        tem_decimal_string = any(
            isinstance(b, dict) and b.get("pattern") == DECIMAL_STRING_PATTERN for b in any_of
        )
        if tem_number and tem_decimal_string:
            if f"{entry['model']}.{name}" in DECIMAL_UNION_BASELINE:
                continue
            sobreviventes.append(name)

    assert sobreviventes == [], (
        f"{entry['model']}: campo `Decimal` exportado como união `number | string`: "
        f"{sobreviventes}. O exportador deixou de reconhecer o formato do Pydantic."
    )


def test_excecao_de_baseline_que_deixou_de_existir_reprova() -> None:
    """Impede que a lista de exceções vire dívida silenciosa depois de o defeito sumir."""
    vivas = set()
    for entry in MANIFEST_ENTRIES:
        schema = json.loads(schema_text_for(entry))
        for name, spec in _walk_properties(schema):
            any_of = spec.get("anyOf")
            if not isinstance(any_of, list):
                continue
            if any(isinstance(b, dict) and b.get("type") == "number" for b in any_of) and any(
                isinstance(b, dict) and b.get("pattern") == DECIMAL_STRING_PATTERN for b in any_of
            ):
                vivas.add(f"{entry['model']}.{name}")

    obsoletas = sorted(chave for chave in DECIMAL_UNION_BASELINE if chave not in vivas)

    assert obsoletas == [], (
        "Exceção(ões) de DECIMAL_UNION_BASELINE que deixaram de ser defeito real — "
        f"remova de `tests/core/test_schema_export.py`: {obsoletas}"
    )


def test_o_colapso_nao_toca_uniao_de_outro_pattern() -> None:
    """Falso positivo seria pior que o defeito: colapsaria um campo que aceita número.

    A detecção é estrutural, então precisa ser estreita o bastante para não capturar um
    `str | float` legítimo que por acaso declare pattern.
    """
    intocado = {
        "properties": {
            "codigo_ou_peso": {
                "anyOf": [
                    {"type": "string", "pattern": "^[A-Z]{2}[0-9]{4}$"},
                    {"type": "number"},
                ]
            }
        }
    }

    assert _collapse_exact_decimal(intocado) == intocado


def test_o_colapso_preserva_o_pattern_do_decimal() -> None:
    colapsado = _collapse_exact_decimal(
        {
            "anyOf": [
                {"type": "number", "minimum": 0.0},
                {"type": "string", "pattern": DECIMAL_STRING_PATTERN},
            ],
            "title": "Unit Price",
        }
    )

    assert colapsado == {
        "type": "string",
        "pattern": DECIMAL_STRING_PATTERN,
        "title": "Unit Price",
    }


def test_o_manifesto_aponta_para_arquivos_versionados() -> None:
    """Entrada de manifesto sem schema no disco é drift que o `--check-dir` só veria depois."""
    raiz = Path(DEFAULT_MANIFEST).parent

    faltando = [
        entry["schema"] for entry in MANIFEST_ENTRIES if not (raiz / str(entry["schema"])).is_file()
    ]

    assert faltando == [], f"Schemas declarados no manifesto e ausentes do repositório: {faltando}"
