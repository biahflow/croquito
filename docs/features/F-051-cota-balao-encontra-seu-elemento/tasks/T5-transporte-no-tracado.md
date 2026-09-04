# F-051 · T5 — O traçado transporta a identidade

Feature: [F-051](../feature.md) · Plano: [plan.md](../plan.md) · Estado: **Pendente**  
`feature_id: F-051` · `task_id: T5` · `depends_on: T2`

## Objetivo

Entidade criada a partir de proposta identificada **nasce** com o `element_ref` e o rótulo
(`SceneRevision.element_labels`) — a letra do balão vira identidade da cena sem redigitação.
Hoje `tracing.py` tem **zero** ocorrências de `element_ref=` (as entidades nascem sem
identidade em todos os 12 pontos de criação); o ato pós-cena (F-047 T2) continua valendo
para o que a revisão não identificou, no mesmo contador.

## Escopo

- `services/worker/src/croquito_worker/tracing.py` — o mapeamento proposta→entidade nos
  pontos de criação relevantes (`:1750-2730`) consulta as declarações da revisão e semeia
  `element_ref`/rótulo; a rota `POST .../trace-solves` (`main.py:12100-12199`) passa as
  declarações da revisão corrente ao solve.
- `packages/core/src/croquito_core/models.py:313-355` — invariantes **inalterados**; a tarefa
  os respeita: camada única por ref (`ELEMENT_REF_LAYER_MISMATCH`, `:329-345`) e nenhum
  rótulo órfão (`ELEMENT_LABEL_UNKNOWN_REF`, `:346-354`).
- **Cuidado com o falso cognato**: `croquito_worker/element_labels.py` (importado por
  `tracing.py:70-75`) é posicionamento de TEXTO no DXF, não identidade — não tocar.
- Testes: `tests/worker/test_tracing.py` (round-trip novo) e `tests/api/test_api.py` (rota).

## Fora de escopo

- Internos do solver (`geometry_solver`, `topology`) — a identidade viaja em volta deles,
  não por dentro.
- Segundo passe pós-traçado (caminho C do ADR-0063) — evolução futura, não entra.
- Ato de identidade da cena (F-047) — continua como está.

## Critérios de aceite

1. **Round-trip completo** (o teste que o risco do contrato pede): declara "B" sobre 2
   propostas na revisão → traçado → cena com as entidades correspondentes carregando
   `element_ref` e `element_labels["EL-NNN"] == "B"` → novo ato de identidade **na cena**
   cunha o ref seguinte do mesmo contador → re-solve preserva a identidade transportada.
2. Propostas de um mesmo elemento que virem entidades em **camadas distintas** no traçado:
   comportamento decidido e testado (não uma surpresa de `ELEMENT_REF_LAYER_MISMATCH` em
   produção) — a resolução esperada é o traçado manter a camada coerente por elemento; se
   isso contrariar outra regra de camada existente, **parar e reportar** em vez de afrouxar o
   invariante.
3. Cena de job sem declaração nenhuma sai **byte a byte** igual à de hoje (o teste de
   regressão que o plano da F-047 consagrou).
4. `SceneRevision` aprovada com identidade transportada passa por `ensure_exportable()` e o
   quantitativo da F-047 agrupa pelo ref (critério 4 do contrato) — teste usando o caminho
   existente do `quantitativos.csv`.

## Validação

```text
baseline: make check && make test verdes na main (registrar o resultado real antes de mudar)
required: uv run pytest tests/worker/test_tracing.py tests/api -x
required: make check && make test
```

## Riscos conhecidos

- O snapshot de propostas do traçado (`proposals_json`) e as declarações moram na mesma
  revisão — o solve precisa ler os dois da MESMA revisão (`base_review_version` já validado
  em `main.py:12116-12129`); misturar versões é o defeito a testar.
- `scene.schema.json` não muda (campos já existem desde a F-047); se `make contracts` acusar
  drift, algo saiu do escopo.
