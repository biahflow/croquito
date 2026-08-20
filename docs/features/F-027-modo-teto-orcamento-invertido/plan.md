# F-027 — Plano de execução

```text
FEATURE EXECUTION PLAN

feature_id: F-027
goal: a orçamentista declara a verba da demanda na rodada de orçamento e monta
      vendo o consumo contra o teto; estouro avisa com peso e nunca recusa/corta;
      Estimate e planilha inalterados
assumptions:
  - ADR-0040 Accepted e Design Approval rev. 1 aprovado (2026-08-20) são a
    especificação; as 6 decisões do ADR e as 6 telas do mock são vinculantes
  - teto NÃO muda schema publicado nem goldens (ADR-0040, decisões 1 e 5)
  - base da branch: f-027-especificacao (contém ADR+mock); o código de F-020
    está na main (base da branch); F-028/F-026 NÃO são dependência
  - persistência: duas colunas novas em estimate_rounds (valor como TEXTO exato
    + rótulo), migração 0004 escrita à mão (make db-revision exige banco;
    precedente da 0003) — primeira migração incremental (add_column) do repo,
    forward-only, gate do ADR-0029 no CI
  - mock lista como NÃO aprovado: remover o teto de rodada que já o tem — logo
    NÃO existe rota/ato de remoção nesta feature (editar valor sim; zerar não)
risks:
  - comparação de dinheiro derivada: NUNCA recomputar; usar total_amount do
    estimate_json da cabeça como está (string→Decimal), teto idem — teste no
    limite exato nos dois lados do centavo
  - defeito pré-existente de legibilidade da F-020 (OrcamentoApp.tsx:1125-1144,
    .topbar-meta sobre painel claro) entra como conserto declarado de uma linha
    em T2 — achado do mock, registrado no README dele

tasks:
  - id: T1
    role: builder
    goal: teto como dado da rodada com rotas e payload derivado
    scope: services/api/src/croquito_api/database.py (EstimateRoundRecord ganha
           target_amount: str|None e target_label: str|None — valor como texto
           exato, disciplina Decimal-como-texto),
           migrations/versions/0004_*.py (add_column, à mão, docstring como a 0003),
           services/api/src/croquito_api/estimate_rounds.py (parse/validação do
           teto — >0, decimal exato, recusa ESTIMATE_TARGET_INVALID 422; bloco
           derivado {target: {amount, label}, consumed, remaining, over} no
           round_state_payload e no payload do estimate quando houver teto E
           houver estimate montado; limite exato over=false; sem teto → bloco
           ausente),
           main.py (POST /v1/estimate-rounds aceita target_amount/target_label
           opcionais no corpo de criação; rota nova POST
           /v1/estimate-rounds/{round_id}/target para declarar/editar — papel
           primeira linha, Idempotency-Key, base_version; SEM rota de remoção),
           snapshot OpenAPI (ato deliberado), API_CONTRACT.md,
           tests/api/test_estimate_round_routes.py (criar com teto; criar sem;
           declarar depois; editar com 409 de base_version velho; 403; zero e
           texto ilegível recusam ESTIMATE_TARGET_INVALID; bloco derivado nos
           três estados incluindo limite EXATO — construir estimate cujo
           total_amount == teto — e um centavo acima)
    out_of_scope: web (T2); e2e (T3); domínio valuation (nada muda em
                  packages/); schema/goldens; remoção de teto
    acceptance_criteria: nenhum schema publicado muda; diff OpenAPI só-adição;
                         comparação nunca recomputa dinheiro
    depends_on: []
    validation: make check + make test + uv run pytest tests/api/test_estimate_round_routes.py -x -q + uv run pytest tests/api/test_migrations.py -q
    required_capabilities: READ, WRITE, VALIDATE
    risk: dinheiro comparado — revisão linha a linha; migração incremental nova
    relative_effort: M
  - id: T2
    role: builder
    goal: telas do mock aprovado na jornada do orçamento + conserto declarado de
          legibilidade
    scope: apps/web/src/orcamento/ (api.ts: campos de criação + postTarget +
           bloco target do state; OrcamentoApp.tsx: campos na abertura com
           recusa de 0,00 na tela, painel "Teto da verba" na etapa BDI,
           bloco de consumo com os três estados — dentro/limite exato dito por
           extenso/estourado —, faixa TETO ESTOURADO em âmbar de largura
           inteira SEM botão presente em toda etapa enquanto over; linha de
           teto na lista só em rodada com teto; conserto: metadados da lista
           trocam .topbar-meta por .dica — defeito pré-existente registrado no
           mock/README.md), labels/errors (ESTIMATE_TARGET_INVALID + frases),
           styles.css do diretório (composições do mock; NENHUMA cor nova),
           testes vitest (estados do bloco, recusa de zero, faixa presente em
           etapa != BDI quando over)
    out_of_scope: medicao/, croqui, backend, copy definitiva, remoção de teto
    acceptance_criteria: estados do mock todos presentes; bloco de estouro sem
                         nenhum botão; rodada sem teto idêntica a hoje (teste)
    depends_on: [T1]
    validation: make check + npm --workspace @croquito/web run test
    required_capabilities: READ, WRITE, VALIDATE
    risk: OrcamentoApp.tsx grande e vivo — integração ampla
    relative_effort: M
  - id: T3
    role: builder
    goal: e2e do teto pela cadeia /v1
    scope: tests/e2e/test_estimate_rounds_v1.py (cenário aditivo: declarar teto
           na criação, montar, asserir bloco derivado over=true com valores
           exatos; editar teto para o total EXATO → over=false, remaining=0;
           base_version velho → 409; rodada do teste existente segue sem teto e
           sem bloco — retrocompatibilidade)
    out_of_scope: código de produção (achado ⇒ parar e reportar)
    acceptance_criteria: asserções com valores exatos truncados; teste existente
                         não enfraquecido
    depends_on: [T1]
    validation: make check + make test + uv run pytest tests/e2e -q
    required_capabilities: READ, WRITE, VALIDATE
    risk: baixo
    relative_effort: S

parallel_groups: [[T2, T3]]
critical_path: T1 → T2
integration_strategy: branch f-027-especificacao (vira a branch da feature);
                      contratos entre tasks fixados NESTE plano (nomes dos
                      campos target_amount/target_label, path da rota, forma do
                      bloco derivado). Integração final: make check + make test
                      + make valuation-estimate-demo; rebase sobre a main quando
                      os merges represados forem liberados.
human_gates: plano da rodada aprovado; ADR-0040 e design rev. 1 exercidos
             (2026-08-20); merge represado — pedir ao final
planning_findings: nenhum ARCHITECTURE_DECISION_REQUIRED; PARALLELISM_RISK
                   ausente entre T2 e T3 (arquivos disjuntos)
```
