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

parallel_groups: nenhum — T2 consome o bloco de estado que T1 publica.
critical_path: T1 → T2.
integration_strategy: commits separados por task na `main`, com revisão linha a linha entre
  eles; nenhuma task encerra com portão vermelho.
human_gates: nenhum aberto. ADR-0045 `Accepted` e Design Approval Package revisão 1 aprovado,
  ambos por ato humano em 2026-08-22. A **copy** da tela segue não aprovada, por declaração
  explícita do registro de aprovação.
