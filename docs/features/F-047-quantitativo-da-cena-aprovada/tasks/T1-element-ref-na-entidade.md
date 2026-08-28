# F-047 · T1 — `element_ref` na entidade e o contrato gerado

Feature: [F-047](../feature.md) · Plano: [plan.md](../plan.md) · Estado: **Pendente**

## Objetivo

Dar à `Entity` uma identidade de elemento estruturada, ao lado do `id` e do texto livre, sem
mover nenhum digest de croqui existente.

## Escopo

- `packages/core/src/croquito_core/models.py`
- `packages/contracts/` (gerado por `make contracts` — **nunca** editado à mão)
- `tests/core/` (ou o diretório equivalente dos testes de domínio do croqui)

## Fora de escopo

- Atribuir identidade (T2), export (T3), medição (T4 em diante)
- Trocar `TextGeometry.text` por chave: o texto livre continua sendo o que o humano lê

## Critérios de aceite

1. `Entity.element_ref` existe, é **opcional**, e não substitui `id` nem o texto do rótulo
   (decisão 1).
2. A identidade sobrevive à criação de revisão nova — inclusive à da aprovação, que hoje cunha
   `SceneRevision.id` novo e `version + 1` (`services/api/src/croquito_api/main.py:10069-10094`).
3. O formato e o escopo de unicidade ficam **decididos e escritos** aqui (o `Unknown` do
   contrato), com o motivo no código: identidade duplicada dentro da mesma cena recusa.
4. `make contracts` regenera `scene.schema.json` e `scene.generated.ts`, e `make check` passa no
   drift.
5. `export_errors()` / `ensure_exportable()` **não** mudam de comportamento: `element_ref` não
   entra em nenhuma condição do portão.
6. Cena sem `element_ref` produz DXF e pacote **byte a byte** iguais aos de hoje.

## Validação

`uv run pytest tests` verde; `make contracts && make check` verdes.
