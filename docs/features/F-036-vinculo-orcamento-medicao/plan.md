# F-036 — Plano de execução

feature_id: F-036
goal: sob `contracted_demand`, a rodada de medição nasce com o consolidado contratual derivado
do orçamento assinado, e os seis guardrails que hoje não podem disparar passam a poder.

assumptions:
- O [ADR-0048](../../adr/0048-consolidado-contratual-do-orcamento-assinado.md) foi aceito por
  ato humano em 2026-08-23 e o Design Approval Package está aprovado (revisão 1). As nove
  decisões do ADR são premissa deste plano, não escolha das tasks.
- O consolidado é gravado na rodada de medição, e a forma de gravá-lo — coluna na raiz — sai
  aqui: raiz, e não revisão, porque ele é imutável na rodada como o catálogo instalado, e
  revisão é para o que muda.
- A recusa de BDI sob o regime (ADR-0048 decisão 3) é da montagem do orçamento, não da
  abertura da medição: é lá que o `pricing_regime` e o `bdi_percent` se encontram.

risks:
- **A tradução é o ponto de maior consequência da feature.** Um consolidado torto transforma
  seis portões em seis carimbos. Mitigação: T1 é domínio puro, sem API e sem banco, com teste
  para cada recusa e para o caso de agregação.
- `main.py` é arquivo grande e vivo; T2 acrescenta rota e toca a criação de rodada. Mitigação:
  o consolidado chega pronto de T1, e T2 não recalcula nada.
- Rodada existente sem vínculo tem de continuar idêntica. Mitigação: critério de aceite 2 e
  teste que percorre o caminho antigo sem tocá-lo.

tasks:
  - id: T1
    role: builder
    goal: traduzir orçamento assinado em `ContractWorkbook`, no domínio
    scope: módulo novo em `packages/valuation/src/croquito_valuation/`, agregação por código,
      preço sem BDI, grupo único, recusas de domínio, e testes em `tests/valuation/`.
    out_of_scope: qualquer arquivo de `services/`, `apps/` ou migração; a recusa de BDI sob o
      regime (é T2); persistência.
    depends_on: []
    validation: uv run pytest tests/valuation/, make check
    relative_effort: M

  - id: T2
    role: builder
    goal: persistir o vínculo e o consolidado, abrir a medição a partir do orçamento, e
      recusar BDI sob o regime
    scope: migração `0016`, colunas de vínculo (`estimate_round_id`, `estimate_digest`) e do
      consolidado em `valuation_rounds`, `POST /v1/valuation-rounds` aceitando a origem,
      leitura da rodada devolvendo o regime de conferência, `bulletin_export_contract` usando
      o consolidado gravado quando houver, recusa `ESTIMATE_BDI_FORBIDDEN_UNDER_REGIME` na
      montagem, snapshot de OpenAPI, testes de API.
    out_of_scope: qualquer arquivo de `apps/web`; mudar a tradução entregue por T1.
    depends_on: [T1]
    validation: make check, make test, tests/api/test_migrations.py com PostgreSQL real
    relative_effort: L

  - id: T3
    role: builder
    goal: a escolha da origem na abertura da medição e o regime de conferência na rodada
    scope: `apps/web/src/medicao/` — seção "Abrir rodada nova" com a escolha de origem, a
      faixa de procedência, o painel da rodada declarando contra o que ela confere, e os
      estados de vazio, carregando, recusa e sem papel, correspondendo à revisão 1 aprovada.
    out_of_scope: qualquer arquivo de `services/`; decidir autorização no navegador.
    depends_on: [T2]
    relative_effort: M
    validation: npm --workspace @croquito/web run test, make check

  - id: T4
    role: builder
    goal: e2e da cadeia com vínculo, e a prova de que os guardrails disparam
    scope: `tests/e2e/` — orçamento sob o regime assinado, medição aberta a partir dele, e um
      teste por guardrail que passa a poder disparar.
    out_of_scope: mudar comportamento entregue por T1–T3.
    depends_on: [T2]
    relative_effort: M
    validation: make test

parallel_groups: T3 e T4 correm juntas depois de T2 — escopos disjuntos (`apps/web` × `tests/e2e`).
critical_path: T1 → T2 → T3.
integration_strategy: commits separados por task na `main`, com revisão linha a linha entre
  elas; nenhuma task encerra com portão vermelho.
human_gates: nenhum aberto. Os dois que precediam o planejamento foram cumpridos em
  2026-08-23. A migração `0016` no hospedado é ato de deploy, aplicada pelo job de banco.
