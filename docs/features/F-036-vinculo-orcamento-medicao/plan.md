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

PLAN_DEVIATION (2026-08-23, T2): o plano não previa mexer em `valuation_rounds.catalog_upload_id`,
  e foi preciso. A coluna é `NOT NULL`, e um orçamento cuja tabela contratual veio do **acervo
  da plataforma** (F-037) não tem upload do cliente para citar — a rodada nascida dele não
  teria o que gravar ali. A coluna passa a ser `NULL`-able na migração `0016`. O docstring
  dela já previa o caso: "se um dia a rodada precisar nascer sem catálogo, é decisão de
  contrato". Impacto: nenhum no comportamento existente; `catalog_object_key` e
  `catalog_source_sha256`, que são o que a rodada usa para LER o catálogo, seguem
  obrigatórias, então nenhuma rodada nasce sem catálogo. O que deixou de ser obrigatório é a
  proveniência do upload.

PLAN_DEVIATION (2026-08-23, T2): a recusa de BDI sob o regime quebrou
  `tests/e2e/test_estimate_rounds_v1.py::test_estimate_round_contracted_demand_regime_through_v1_api`,
  que montava com 25% sobre preço que já embutia BDI. O e2e foi atualizado para provar a
  recusa **e** seguir com zero — a quebra é a consequência que o ADR-0048 declarou, não um
  teste a consertar.

ACHADO PARA A T3 (2026-08-23, ao terminar a T4): `EstimateRoundSummary` **não diz se o
  orçamento está assinado**. Ela traz `pricing_regime` e `stage`, e `stage` chega no máximo a
  `estimate` — que é "montado", não "assinado". O Design Approval Package aprovado mostra o
  selo **Assinado** na lista de origem (estado 1), então a tela não pode deduzir: ou a
  listagem passa a contar, ou a tela oferece orçamento que o servidor vai recusar com
  `ESTIMATE_ORIGIN_NOT_SIGNED`.

  É lacuna da T2, não da T3: o dado é do servidor. A listagem já busca a cabeça de cada
  rodada da página (`_estimate_round_heads`), então a informação está à mão e o custo é
  aditivo. **Fazer isto abre a T3**, e vira `PLAN_DEVIATION` da T2 quando for feito.

parallel_groups: T3 e T4 correm juntas depois de T2 — escopos disjuntos (`apps/web` × `tests/e2e`).
critical_path: T1 → T2 → T3.
integration_strategy: commits separados por task na `main`, com revisão linha a linha entre
  elas; nenhuma task encerra com portão vermelho.
human_gates: nenhum aberto. Os dois que precediam o planejamento foram cumpridos em
  2026-08-23. A migração `0016` no hospedado é ato de deploy, aplicada pelo job de banco.
