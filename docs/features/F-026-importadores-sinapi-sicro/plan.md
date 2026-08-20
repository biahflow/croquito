# F-026 — Plano de execução

```text
FEATURE EXECUTION PLAN

feature_id: F-026
goal: SINAPI e SICRO viram origens nomeadas de PriceOrigin com um importador por
      fonte no molde do EMOP (layout como dado, fail-closed, fixture sintética),
      instaláveis na cascata do orçamento-base sem tela nova
assumptions:
  - ADR-0039 Accepted (2026-08-20) é a especificação semântica
  - mapa verificado (exploração de 2026-08-20): nenhum match exaustivo por origem
    no código — tudo compara == PriceOrigin.SCO ou origem-do-catálogo; só
    SUGGESTION_SCHEMA_VERSION (assignment.py:62, "1.1.0") e
    ESTIMATE_SCHEMA_VERSION (estimate.py:59, "2.0.0") embutem o enum publicado
    (code-suggestions.schema.json:118-125; estimate.schema.json:250-257) — o
    bump da decisão 5 do ADR é minor nesses DOIS e em nenhum outro
  - openpyxl já é dependência (escritores de planilha) — leitor .xlsx dos
    importadores não é dependência nova
  - golden estimate-demo.canonical.json:211 muda schema_version "2.0.0"→"2.1.0"
    como consequência DECLARADA do bump; nenhum outro golden muda
  - labels da web são tabela literal (orcamento/labels.ts:145-167) com fallback
    (?? origin, selo-neutro) — origens novas precisam de texto; o selo cai no
    neutro de propósito (nenhuma cor nova sem design)
risks:
  - cli.py é arquivo único para todos os comandos — os dois importadores novos
    entram na MESMA task para não haver duas mãos no mesmo parser
  - formato real dos arquivos oficiais fecha como dado (layout) quando o usuário
    trouxer os arquivos; fixtures sintéticas fecham a feature (precedente EMOP)

tasks:
  - id: T1
    role: builder
    goal: PriceOrigin ganha sinapi/sicro; bump minor dos DOIS schemas que embutem
          o enum; contratos regenerados; labels da web; guardrail coberto
    scope: packages/valuation/src/croquito_valuation/models.py (enum, linhas 95-107),
           packages/valuation/src/croquito_valuation/assignment.py (SUGGESTION_SCHEMA_VERSION
           "1.1.0"→"1.2.0", linha 62), packages/valuation/src/croquito_valuation/estimate.py
           (ESTIMATE_SCHEMA_VERSION "2.0.0"→"2.1.0", linha 59 + Literal do campo),
           make contracts (gerados), tests/valuation/golden/estimate-demo.canonical.json
           (schema_version — única mudança), apps/web/src/orcamento/labels.ts
           (PRICE_ORIGIN_LABELS: "SINAPI"/"SICRO"; priceOriginSeloClass fica no
           fallback selo-neutro — documentar no report), testes: guardrail
           BULLETIN_PRICE_ORIGIN_FORBIDDEN nomeando sinapi e sicro (padrão de
           tests/valuation/test_calc.py:464 e test_writer_roundtrip.py:219),
           labels.test correspondente
    out_of_scope: importadores (T2), CLI, cascata de demo, cores/CSS novos
    acceptance_criteria: make check sem drift; make test verde; golden com diff
                         SÓ de schema_version; guardrail testado com as duas
                         origens novas; NON_SCO_CODE_PATTERN intocado
    depends_on: []
    validation: make check + make test + make valuation-estimate-demo
    required_capabilities: READ, WRITE, VALIDATE
    risk: bump de schema publicado — revisão linha a linha
    relative_effort: S
  - id: T2
    role: builder
    goal: importadores SINAPI e SICRO no molde do EMOP, com fixtures sintéticas
          e comandos de CLI
    scope: packages/valuation/src/croquito_valuation/sinapi.py (novo) e sicro.py
           (novo) — molde: emop.py (EmopCatalogLayout 75-131,
           read_emop_catalog_with_report 299-388, códigos *_FIELD_MISSING/
           *_ROW_UNPARSEABLE/*_EMPTY/*_LAYOUT_CODE_PATTERN_INVALID por fonte);
           leitor .xlsx mínimo via openpyxl (read_only), layout como dado
           (sheet, header_row, colunas por letra, code_pattern, reference_month,
           source_label); services/worker/src/croquito_worker/valuation/
           sinapi_fixture.py e sicro_fixture.py (novos, molde emop_fixture.py:
           gerador determinístico + gabarito + padrões de código próprios —
           SINAPI numérico puro, SICRO com formato próprio declarado na fixture);
           cli.py: comandos import-sinapi/import-sicro espelhando import-emop
           (parser 2703-2718, run_import_emop 764-807, dispatch 3081);
           tests/valuation/test_sinapi.py e test_sicro.py (novos, espelho da
           estrutura de test_emop.py: feliz, recusa estrutural, campo ausente,
           código fora do padrão, preço não numérico, vazio, layout inválido,
           CLI publica/recusa sem publicar)
    out_of_scope: enum/labels (T1), e2e/cadeia (T3), rota/tela, formato real dos
                  arquivos oficiais (layout é dado; a fixture fixa o sintético)
    acceptance_criteria: importa fixture → catálogo com origin/digest/
                         reference_month corretos; recusas fail-closed campo a
                         campo com códigos estáveis por fonte; Decimal nunca
                         passa por float; CLI não publica nada em recusa
    depends_on: [T1]
    validation: make check + make test + uv run pytest tests/valuation/test_sinapi.py tests/valuation/test_sicro.py -x -q
    required_capabilities: READ, WRITE, VALIDATE
    risk: os dois comandos no MESMO cli.py — por isso uma task só
    relative_effort: M
  - id: T3
    role: builder
    goal: a cadeia do orçamento prova as origens novas de ponta a ponta
    scope: tests/e2e/test_estimate_rounds_v1.py (cascata do e2e ganha uma fonte
           sinapi via importador real sobre fixture, decisão de código citando-a,
           linha com price_origin novo, FONTE impressa na planilha),
           tests/e2e/test_valuation_full_chain.py (cadeia CLI: um teste novo com
           import-sinapi/import-sicro na cascata do build-estimate)
    out_of_scope: código de produção (se a cadeia não fechar, é achado de
                  T1/T2 — parar e reportar), demos (goldens da demo não mudam
                  além do declarado em T1)
    acceptance_criteria: e2e verde com origem nova na cascata e na planilha;
                         testes existentes não enfraquecidos
    depends_on: [T1, T2]
    validation: make check + make test + uv run pytest tests/e2e -q
    required_capabilities: READ, WRITE, VALIDATE
    risk: baixo
    relative_effort: S

parallel_groups: []
critical_path: T1 → T2 → T3 (linear; T2 é o esforço dominante)
integration_strategy: execução sequencial na branch f-026-importadores (base:
                      especificacao-f025-f027, que carrega contrato e ADR).
                      Integração final: make check + make test + demos; rebase
                      sobre a main quando o usuário liberar os merges represados.
human_gates: aprovação deste plano (dada na aprovação do plano da rodada,
             2026-08-20); ADR-0039 Accepted; merge represado por decisão humana
             ("segurar as duas", 2026-08-20) — pedir de novo ao final
planning_findings: nenhum ARCHITECTURE_DECISION_REQUIRED (ADR-0039 cobre);
                   PARALLELISM_RISK interno evitado por T2 unificar os dois
                   importadores no mesmo cli.py
```
