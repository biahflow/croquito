# F-025 — Plano de execução

```text
FEATURE EXECUTION PLAN

feature_id: F-025
goal: a orçamentista aprova nominalmente a medição montada (ato próprio, digest
      amarrado, identidade do JWT) e exporta o boletim .xlsx pelo gate auditado,
      tudo pelas rotas /v1 e pela jornada de medição — sem CLI
assumptions:
  - Design Approval Package rev. 1 aprovado em 2026-08-20 (mock/README.md);
    aprovação em DOIS atos explícitos mantida por decisão humana
  - mapa verificado (exploração de 2026-08-20, main e618fc8):
    - ValuationApproval JÁ existe no domínio (models.py:381-389) como campo de
      Valuation (:408), com content_digest() excluindo a própria aprovação
      (:485-493) e o portão export_errors/ensure_exportable (:495-552) produzindo
      VALUATION_NOT_APPROVED / VALUATION_APPROVAL_REJECTED /
      APPROVAL_CONTENT_MISMATCH / VALUATION_EXPORT_BLOCKED e os códigos de
      contrato/saldo — a F-025 NÃO cria semântica de aprovação, só a exerce
    - valuation_json persiste o model_dump inteiro de Valuation ⇒ aprovação
      embutida na coluna existente; planilha publicada usa
      artifact_refs_json/artifact_digests_json como a F-020 ⇒ SEM migração e o
      gate do ADR-0029 não entra em jogo
    - molde do export por rota: estimate_rounds.py:803-841
      (render_estimate_workbook, *_workbook_key por digest, workbook_audit_failed
      com 500 sem expected/found) e a rota build_estimate (main.py:7659-7781)
    - run_export_valuation NÃO chama ensure_exportable (cli.py:858-882, docstring
      "o portão já correu antes daqui") — a ROTA de export tem de chamá-lo
      explicitamente; esse é o ponto que faz VAL-05 virar recusa de rota
    - web: EtapaId hoje é prancha|revisao|codigos|boletim (etapas.ts:20); a frase
      "sem aprovação" já existe em dois lugares (etapas.ts:224,
      MedicaoApp.tsx:1314) e sai quando a etapa nova entrar; labels.ts NÃO tem
      tradução para nenhum código do portão — entram todas
risks:
  - calc route monta Valuation com calc_plan=None e SEM contrato; o export com
    contrato/saldo (ensure_exportable(contract)) depende do que a rodada tem
    instalado — o Builder de T1 deve espelhar exatamente o que o /calc já usa e
    NUNCA afrouxar o portão para "passar" (contrato ausente ⇒ os códigos de
    contrato não disparam, como no domínio; aprovação continua obrigatória)
  - aprovar cria revisão nova reescrevendo valuation_json com approval embutido;
    o digest aprovado é o content_digest() do documento da CABEÇA — se a cabeça
    mudar depois, o portão recusa com APPROVAL_CONTENT_MISMATCH (o mock desenha
    exatamente esse estado como "aprovação caduca")

tasks:
  - id: T1
    role: builder
    goal: rotas /v1 de aprovação nominal e de exportação auditada do boletim
    scope: services/api/src/croquito_api/valuation_rounds.py (helpers: aprovação
           sobre a cabeça — ReviewerDecision com reviewer_id=principal.subject,
           reviewer_role "orcamentista", decided_at UTC, action "confirm";
           render_valuation_workbook espelhando render_estimate_workbook, com
           VALUATION_WORKBOOK_AUDIT_FAILED 500 sem expected/found;
           bulletin_workbook_key por digest; round_state_payload e
           _bulletin_payload ganham bloco de aprovação {approved, approved_by,
           approved_at, approved_digest, current_digest, stale: bool} e
           workbook_present/sha — payload NUNCA carrega URL assinada),
           services/api/src/croquito_api/main.py (POST
           /v1/valuation-rounds/{round_id}/approve e POST .../bulletin/export ao
           final do arquivo; GET .../bulletin passa a incluir os campos novos e
           workbook_url assinada na leitura, como o GET do estimate), disciplina
           integral (papel primeira linha, Idempotency-Key, base_version,
           problem+json), snapshot OpenAPI por ato deliberado,
           docs/architecture/API_CONTRACT.md,
           tests/api/test_valuation_round_routes.py (aprovar feliz — version
           avança, approval embutido no valuation_json da revisão nova; aprovar
           sem valuation → ROUND_STAGE_NOT_READY; exportar sem aprovação →
           VALUATION_EXPORT_BLOCKED com VALUATION_NOT_APPROVED nos details;
           exportar após mudança da medição → VALUATION_EXPORT_BLOCKED com
           APPROVAL_CONTENT_MISMATCH; export feliz publica por digest e grava
           refs/digests; auditoria divergente → 500 sem publicar; 403/409/
           idempotência nas rotas novas)
    out_of_scope: web (T2); e2e (T3); CLI; mudar o /calc; migração (não há);
                  mudar export_errors/ensure_exportable do domínio
    acceptance_criteria: portão do domínio exercido pela rota (nunca reimplementado);
                         identidade só do JWT; diff OpenAPI só-adição
    depends_on: []
    validation: make check + make test + uv run pytest tests/api/test_valuation_round_routes.py -x -q
    required_capabilities: READ, WRITE, VALIDATE
    risk: contrato/dinheiro — revisão linha a linha
    relative_effort: L
  - id: T2
    role: builder
    goal: a etapa "Aprovação e exportação" da jornada de medição, conforme o
          design aprovado (rev. 1, dois atos explícitos)
    scope: apps/web/src/medicao/etapas.ts (EtapaId ganha a etapa nova depois de
           "boletim"; derivarEtapas com os estados do mock), api.ts
           (postApprove/postBulletinExport + campos novos de BulletinResponse),
           errors.ts (equivalente de workbookAuditFindings do lado orcamento),
           labels.ts (traduções de TODOS os códigos do portão:
           VALUATION_NOT_APPROVED, VALUATION_APPROVAL_REJECTED,
           APPROVAL_CONTENT_MISMATCH, VALUATION_EXPORT_BLOCKED,
           PERIOD_NOT_SEQUENTIAL, BALANCE_EXCEEDED, LINE_PRICE_NOT_IN_CONTRACT,
           LINE_UNIT_NOT_IN_CONTRACT, VALUATION_WORKBOOK_AUDIT_FAILED),
           MedicaoApp.tsx (telas do mock: ato em dois cliques com consequência
           antes do botão e identidade mostrada; aprovação registrada; aprovação
           caduca com os dois digests e única ação "aprovar de novo" — NENHUM
           "exportar assim mesmo"; export em quatro passos escritos; auditoria
           reprovada como tela "nada foi publicado"; 403 sem nomear papel; 409),
           remoção das duas frases "sem aprovação" que a etapa nova torna
           mentirosas (etapas.ts:224, MedicaoApp.tsx:1314 — trocadas pelo estado
           real), testes vitest das etapas/labels/fluxos
    out_of_scope: croqui, orcamento/, estilos novos (tokens existentes; nenhuma
                  cor nova), copy definitiva (texto do mock é rascunho — usar
                  como está e listar no report)
    acceptance_criteria: estados do mock presentes; dois atos explícitos;
                         nenhum caminho de export sem aprovação válida na tela
    depends_on: [T1]
    validation: make check + npm --workspace @croquito/web run test
    required_capabilities: READ, WRITE, VALIDATE
    risk: MedicaoApp.tsx grande e vivo — integração ampla
    relative_effort: L
  - id: T3
    role: builder
    goal: e2e da aprovação nominal + export pelas rotas /v1
    scope: tests/e2e/test_valuation_v1_chain.py (estender ou arquivo novo ao
           lado): cadeia até o calc, aprovar pela rota, exportar, reabrir a
           planilha do store e conferir conteúdo lógico igual ao caminho do CLI
           sobre a mesma medição (criterion 5 da feature — canonicalize_workbook
           como comparador); recusas: export antes de aprovar; aprovação caduca
           após recalc
    out_of_scope: código de produção (achado ⇒ parar e reportar)
    acceptance_criteria: paridade lógica CLI×rota provada; recusas nomeadas
    depends_on: [T1]
    validation: make check + make test + uv run pytest tests/e2e -q
    required_capabilities: READ, WRITE, VALIDATE
    risk: baixo
    relative_effort: M

parallel_groups: [[T2, T3]]
critical_path: T1 → T2 (as duas L; T3 corre com T2)
integration_strategy: branch f-025-boletim-web (base: especificacao-f025-f027,
                      que carrega contrato e mock aprovado). Contratos entre
                      tasks fixados NESTE plano (paths das rotas, campos do
                      payload de aprovação). Integração final: make check +
                      make test + make valuation-demo; rebase sobre a main
                      quando o usuário liberar os merges represados.
human_gates: aprovação deste plano (dada na aprovação do plano da rodada);
             design rev. 1 aprovado (2026-08-20); merge represado — pedir ao
             final; o ATO nominal sobre medição real é do usuário, pós-deploy
planning_findings: nenhum ARCHITECTURE_DECISION_REQUIRED (mecanismo de domínio
                   existe; sem migração); PARALLELISM_RISK ausente entre T2 e T3
                   (arquivos disjuntos)
```
