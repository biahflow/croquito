"""Exporta os JSON Schemas canônicos consumidos pelos demais runtimes.

O registro modelo → arquivo de schema vive em `contracts.manifest.json`, como dado
(ADR-0028, seção "Desenho do pipeline de contratos multi-modelo"): este pacote passa a
exportar também modelos do pacote de domínio da medição sem importá-lo estaticamente —
cada entrada do manifesto é resolvida em runtime por `importlib.import_module` +
`getattr`, nunca por `import` de topo de arquivo. Este módulo não pode citar o nome do
pacote de domínio da medição em nenhuma forma textual — o gate de camada roda `grep`
sobre o diretório inteiro, não só sobre statements de `import`.
"""

from __future__ import annotations

import argparse
import importlib
import json
import sys
from pathlib import Path
from typing import Any

from pydantic import BaseModel

DEFAULT_MANIFEST = Path(__file__).resolve().parents[3] / "contracts" / "contracts.manifest.json"

_EXACT_DECIMAL_STRING_PATTERN = r"^(?!^[-+.]*$)[+-]?0*\d*\.?\d*$"
"""Pattern que o Pydantic emite para a ramificação `string` de todo campo `Decimal`
(o `ExactDecimal` do pacote de domínio da medição), estável entre campos porque não
deriva de nenhuma constraint declarada no `Field`."""


def _load_manifest(path: Path) -> list[dict[str, Any]]:
    entries = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(entries, list):
        raise TypeError(f"manifesto malformado (esperava lista): {path}")
    return entries


def _resolve_model(entry: dict[str, Any]) -> tuple[type[BaseModel], Any]:
    module = importlib.import_module(entry["module"])
    candidate = getattr(module, entry["model"])
    if not (isinstance(candidate, type) and issubclass(candidate, BaseModel)):
        raise TypeError(
            f"{entry['module']}.{entry['model']} não é um modelo Pydantic (contracts.manifest.json)"
        )
    return candidate, module


def _collapse_exact_decimal(node: Any) -> Any:
    """Colapsa o `anyOf: [number, string]` de campos `ExactDecimal` em `string` pura.

    Pydantic exporta `Decimal` aceitando `number` OU `string` no JSON Schema. Isso reabre,
    nos tipos gerados, a porta que o domínio fecha em runtime: `ExactDecimal` recusa
    `float` na entrada porque dinheiro e quantidade nunca nascem de ponto flutuante
    binário (ADR-0016). Um `number | string` gerado deixaria a tela aceitar `float` como
    tipo válido de `unit_price`/`quantity`/`total` etc. O schema exportado declara sempre
    só `string`, preservando o `pattern` — o valor entra como texto decimal, igual à
    leitura de planilha.

    Detecção estrutural, não por nome de campo: qualquer `anyOf` de dois ramos onde um é
    `{"type": "string", "pattern": <pattern do Decimal>}` e o outro é `{"type": "number",
    ...}` é a assinatura gerada para `ExactDecimal`, dentro ou fora de `$defs`.

    Limitação conhecida e declarada: um campo **opcional** (`ExactDecimal | None`) gera três
    ramos — `number`, `string` e `null` — e não é colapsado por esta regra de dois ramos.
    Nenhum modelo do manifesto tem hoje um campo assim (o `quantity` opcional do pacote de
    takeoff já nasce sem o ramo `number`); o único caso vivo é `SceneRevision.value_si`, do
    contexto do croqui, cujo contrato gerado é consumido por `apps/web` e cuja correção é
    trabalho próprio, não carona de outra feature. `tests/core/test_schema_export.py` vigia
    os dois lados: reprova campo novo que escape e reprova a exceção que deixar de existir.
    """
    if isinstance(node, dict):
        collapsed = {key: _collapse_exact_decimal(value) for key, value in node.items()}
        any_of = collapsed.get("anyOf")
        if isinstance(any_of, list) and len(any_of) == 2:
            string_branch = next(
                (
                    item
                    for item in any_of
                    if isinstance(item, dict)
                    and item.get("type") == "string"
                    and item.get("pattern") == _EXACT_DECIMAL_STRING_PATTERN
                ),
                None,
            )
            has_number_branch = any(
                isinstance(item, dict) and item.get("type") == "number" for item in any_of
            )
            if string_branch is not None and has_number_branch:
                del collapsed["anyOf"]
                collapsed["type"] = "string"
                collapsed["pattern"] = string_branch["pattern"]
        return collapsed
    if isinstance(node, list):
        return [_collapse_exact_decimal(item) for item in node]
    return node


def schema_text_for(entry: dict[str, Any]) -> str:
    """Gera o texto do JSON Schema de uma entrada do manifesto."""
    model, module = _resolve_model(entry)
    version = getattr(module, entry["version_attr"])
    schema = model.model_json_schema()
    schema = _collapse_exact_decimal(schema)
    schema["$id"] = entry["id"].format(version=version)
    schema["title"] = entry["title"]
    return f"{json.dumps(schema, ensure_ascii=False, indent=2, sort_keys=True)}\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--output-dir", type=Path)
    mode.add_argument("--check-dir", type=Path)
    args = parser.parse_args()

    entries = _load_manifest(args.manifest)

    if args.output_dir is not None:
        for entry in entries:
            target = args.output_dir / entry["schema"]
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(schema_text_for(entry), encoding="utf-8")
        return 0

    stale: list[str] = []
    for entry in entries:
        target = args.check_dir / entry["schema"]
        expected = schema_text_for(entry)
        current = target.read_text(encoding="utf-8") if target.exists() else ""
        if current != expected:
            stale.append(str(target))

    if stale:
        for path in stale:
            print(f"Contrato desatualizado: {path}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
