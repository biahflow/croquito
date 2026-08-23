# F-033 — Plano de execução

feature_id: F-033
goal: expressar o terceiro momento de preço — orçar uma demanda dentro de contrato já
licitado — restringindo a cascata à tabela contratual e recusando na INSTALAÇÃO, quando
ainda há o que corrigir.

assumptions:
- **Regime é mão única** (decisão humana de 2026-08-22, não coberta pelo ADR-0045):
  declarado, não volta a pré-licitação. Corrigir um engano exige abrir outra rodada. Fica
  como premissa do plano, no molde do estado padrão da F-034; não altera o ADR, que não
  tratou disso.
- Recusa é `403`/`409` com código estável em `application/problem+json`, como o resto da
  API; o número exato sai na execução, o código estável é o contrato.
- A migração é a `0009`: a `0008` foi da F-034, já na main.

risks:
- `main.py` é arquivo grande e vivo; T1 acrescenta uma rota e altera um chamador.
  Mitigação: a recusa da cascata entra no seam que já existe (`ensure_source_installable`),
  não espalhada pelas rotas.
- O regime muda o que a tela afirma sobre dinheiro público. Mitigação: a T2 é conferida
  contra as capturas aprovadas renderizando com a folha real, e não contra o recorte de CSS
  do mock — foi assim que a F-034 achou três divergências que o recorte escondia.

## O achado que encolheu a feature

O contrato falava em "reusar `build_amendment_dossier`". O levantamento mostrou que **não se
deve chamá-lo**: ele exige que **todo** item confirmado no takeoff já tenha decisão de código
(`AMENDMENT_DOSSIER_ASSIGNMENTS_INCOMPLETE`), porque é artefato de *fechamento* e "não publica
foto parcial". Chamá-lo faria o sinal de candidato a aditivo aparecer só no fim — exatamente o
atraso que a feature existe para eliminar.

O que se reusa é a **regra**, não a função: na cadeia do orçamento o item rejeitado já produz
um `CodeAssignment` de forma idêntica à da medição (`_rejected_assignment`,
`packages/valuation/src/croquito_valuation/assignment.py:1037-1055`), e `round_state_payload`
**já conta** `codes.rejected` (`services/api/src/croquito_api/estimate_rounds.py:995-1003`).
Sob o regime, item rejeitado **é** candidato a aditivo: o sinal existe no instante da
rejeição, sem artefato novo, sem tabela nova e sem builder.

tasks:
  - id: T1
    role: builder
    goal: o regime como dado da rodada, com as duas recusas e o estado publicado
    scope: migração 0009, coluna em `EstimateRoundRecord`, rota de declaração no molde do
      teto, recusa em `ensure_source_installable`, recusa da declaração com cascata suja,
      bloco do regime em `round_state_payload`, snapshot de OpenAPI, testes de API.
    out_of_scope: qualquer arquivo de `apps/web`; qualquer mudança na cadeia de medição;
      chamar `build_amendment_dossier`; amarrar a rodada a um `Contract` real.
    depends_on: []
    validation: make check, make test
    relative_effort: M
  - id: T2
    role: builder
    goal: o selo, a declaração e o candidato a aditivo na tela, conforme a revisão aprovada
    scope: `apps/web/src/orcamento/` — cabeçalho, painel da Cascata, etapa de códigos,
      rótulos e testes.
    out_of_scope: qualquer arquivo de `services/`; o bloco **reservado** do mock (amarrar a
      rodada a um contrato real), que é a lacuna nomeada pelo ADR-0045.
    depends_on: [T1]
    validation: npm --workspace @croquito/web run test, run check
    relative_effort: M

  - id: T3
    role: builder
    goal: a listagem de rodadas diz em que regime cada uma corre
    scope: `pricing_regime` em `EstimateRoundSummary` e em `list_estimate_rounds`, API
      Contract, snapshot de OpenAPI, teste no molde do teto cru.
    out_of_scope: qualquer arquivo de `apps/web`; a criação da rodada, que já grava o
      campo; migração — a coluna já existe em `EstimateRoundRecord`.
    depends_on: []
    validation: make check, make test
    relative_effort: XS
  - id: T4
    role: builder
    goal: o rótulo que não mente, o regime na abertura e o selo no card
    scope: `apps/web/src/orcamento/` — rótulo neutro nas três telas sem rodada, faixa âmbar
      nova para elas, campo Regime no formulário de abertura, selo no card da lista, copy
      do painel de declarar depois, rótulos e testes.
    out_of_scope: qualquer arquivo de `services/`; a tela COM rodada; reordenar os painéis
      da aba Cascata.
    depends_on: [T3]
    validation: npm --workspace @croquito/web run test, npm run web:check, make check
    relative_effort: M

## Ampliação de 2026-08-22 — revisão 2 do pacote de design

T3 e T4 nascem **depois** de T1 e T2 estarem no ar, da revisão 2 do
[pacote de design](mock/README.md), aprovada por ato humano em 2026-08-22. Não é
`PLAN_DEVIATION` de trabalho planejado: é escopo **novo**, registrado no escopo 6 do
contrato, sobre um defeito que só a tela construída revelou — ela afirma um regime onde não
há rodada.

Duas descobertas do levantamento encurtaram o trabalho e estão fixadas nos contratos:

- **Nenhuma migração.** `EstimateRoundRecord.pricing_regime` já existe (`database.py:788`),
  e `POST /v1/estimate-rounds` já aceita e grava o campo. Do servidor, falta só **expor na
  listagem** — daí T3 ser `XS`.
- **A faixa âmbar também mente.** O levantamento afirmou que `AVISO_ORCAMENTO` já era
  neutra; **não é** — ela diz "Orçamento-base **de pré-licitação**". Sem constante nova,
  metade do defeito continuaria no ar depois da feature. Corrigido no contrato da T4.

Uma **divergência deliberada do mock**, por decisão humana de 2026-08-22: `DICA_REGIME` —
"restringir a origem não confere o contrato" — entra **também** no campo da abertura, e não
só no painel de declarar. O mock não a mostra em lugar nenhum, e quem declarasse pela
abertura nunca a leria; ela é a decisão 6 da revisão 1 e a decisão 6 do ADR-0045.

parallel_groups: nenhum — T2 consome o bloco de estado que T1 publica, e T4 consome o campo
  que T3 publica.
critical_path: T1 → T2 (fatia 1) e T3 → T4 (revisão 2).
integration_strategy: commits separados por task na `main`, com revisão linha a linha entre
  eles; nenhuma task encerra com portão vermelho.
human_gates: nenhum aberto. ADR-0045 `Accepted` e Design Approval Package revisão 1 aprovado,
  ambos por ato humano em 2026-08-22. A **copy** da tela segue não aprovada, por declaração
  explícita do registro de aprovação.
