# F-025 — Aprovação nominal e boletim da medição pela web

## Status

`READY_FOR_HUMAN_REVIEW`

> Implementação integrada em 2026-08-20 na branch `f-025-boletim-web` (T1–T3,
> [plan.md](plan.md), um `PLAN_DEVIATION` registrado), revisada e com evidência em
> [evidence.md](evidence.md). Pendem o merge (represado) e os gates listados ao final.

> Selecionada por decisão humana de 2026-08-20, na rodada pós-F-020. É a dívida que a
> própria F-020 declarou em Out of Scope: "aprovação nominal e exportação `.xlsx` do
> boletim seguem fora da web, em marco próprio". O gate de Design Approval foi
> exercido na mesma data: a revisão 1 do [pacote](mock/README.md) foi aprovada por
> Daniel Campos, mantendo a aprovação em dois atos explícitos. Copy final permanece
> aberta, como o pacote declara.

## Classification

`INTERFACE_CHANGE` — etapa nova percebida por humano na jornada de medição (o ato de
aprovação nominal e os estados do boletim exportado). O documento `.xlsx` do boletim em
si NÃO é superfície nova: o layout já existe em código (`template.py`), já é exportado
pelo CLI com auditoria e é o que a prefeitura valida — o que se aprova aqui é a tela,
não a planilha.

## Priority

`HIGH` — VAL-05 diz que medição só é exportada ao cliente após aprovação nominal do
orçamentista responsável. O mecanismo existe desde o M2; o ATO continua impossível pelo
produto: hoje exige CLI. Com a F-020 no ar, o orçamento-base exporta planilha pela web
e a medição — a cadeia mais antiga — não.

## Problem

A jornada de medição termina em "códigos/boletim" sem fechamento: a orçamentista revisa
takeoff, confirma códigos e monta o cálculo, mas a aprovação nominal (VAL-05) e o
`.xlsx` do boletim só existem por `croquito-valuation` no terminal
(`run_export_valuation`, com auditoria fail-closed). Consequências: o ato nominal sobre
medição real permanece pendente desde o M2 (registrado em TRACEABILITY), e o produto
hospedado entrega menos que o CLI exatamente no passo que o cliente paga para ver.

## Desired Outcome

A orçamentista, na jornada de medição, aprova nominalmente a medição montada (ato
próprio, com identidade do JWT — nunca digitada) e exporta o boletim `.xlsx` no layout
da prefeitura pelo mesmo desenho de gate da F-020: gravar, reabrir, auditar centavo a
centavo, publicar só com auditoria aprovada. Sem CLI.

## Scope

1. **Rota de aprovação nominal** em `/v1/valuation-rounds/{id}`: ato humano explícito
   sobre a medição montada (`valuation_json` da cabeça), amarrado por digest ao
   artefato aprovado, identidade vinda do JWT, `Idempotency-Key` + `base_version`.
   Aprovação de artefato que mudou recusa (o digest é o vínculo — mesmo desenho do
   `SceneApproval` do croqui e do gate `ensure_exportable` do domínio).
2. **Rota de exportação do boletim**: monta/renderiza pelo escritor existente
   (`write_valuation_workbook` + `audit_workbook`), portão fail-closed no request
   (molde: `render_estimate_workbook` de `estimate_rounds.py`), `.xlsx` no object
   store endereçado por digest, `estimate`-style GET com URL assinada. Sem aprovação
   nominal válida, a exportação recusa — VAL-05 vira recusa de rota, não convenção.
3. **Etapa/estados na jornada de medição** (`apps/web/src/medicao/`): o ato de aprovar
   (com o peso visual de ato, não de botão qualquer), estados exportado/auditoria
   reprovada ("nada foi publicado"), 403/409 e recusas traduzidas — conforme o Design
   Approval Package desta feature.
4. **e2e** da aprovação nominal + export pela rota, espelhando o e2e `/v1` existente da
   medição.

## Out of Scope

- Mudar o layout impresso do boletim (`template.py` permanece; colunas da F-020
  continuam aditivas e opcionais).
- Aprovação em múltiplos níveis/alçadas; delegação de aprovação.
- Dossiê de aditivo (já tem rotas próprias) e RE-RA (segue leitura).
- Orçamento-base (F-020 fechou o lado dele).
- E-mail/notificação de aprovação (sem provedor de e-mail — F-008 BLOCKED).

## Acceptance Criteria

1. `make check` e `make test` verdes; snapshot OpenAPI com diff só de adição.
2. Exportação sem aprovação nominal válida recusa com código estável; aprovação sobre
   artefato de digest divergente recusa; ambos cobertos por teste de rota.
3. Identidade do aprovador vem do JWT; nenhum campo de "nome do aprovador" viaja do
   cliente.
4. `.xlsx` publicado só após auditoria de recomputação aprovada; falha do auditor não
   publica nada (coberto por teste, incluindo o estado na tela).
5. Boletim exportado pela rota é logicamente idêntico ao do CLI sobre a mesma medição
   (goldens/canonicalização como detector).
6. e2e novo cobre a cadeia com aprovação + export por `/v1`, sem CLI.
7. Papel da medição exigido inclusive nas leituras novas; `Idempotency-Key` e
   `base_version`/409 nas mutações.

## Constraints

- A API não recebe upload no request path; o que ela grava é artefato que ela mesma
  montou e auditou (precedente `write_object`, F-020).
- A SPA não decide autorização; etapas são espelho do estado do servidor.
- `BULLETIN_PRICE_ORIGIN_FORBIDDEN` e o cálculo de saldo permanecem intocados.

## Dependencies

- Design Approval Package aprovado (ver Human Gates) — em produção como revisão 1.
- F-020 mergeada (padrões de export/gate) — satisfeita.
- Mecanismo de domínio VAL-05 (`ensure_exportable`, aprovação por digest) — existe
  desde o M2.

## Unknowns

1. **Forma exata do registro de aprovação nominal na medição** — o domínio da medição
   tem o gate, mas o objeto de aprovação da rodada web (espelho do `SceneApproval`?)
   é decisão do planejamento, com o mapa do explorador.
2. **Onde a etapa entra na jornada** (etapa nova vs. estado final da etapa "boletim") —
   proposta na revisão 1 do pacote de design; decisão fecha no gate.

## Risks

- **Dois caminhos de export (CLI e rota) divergirem** — mitigação: mesmíssimo escritor
  e auditor por import; critério 5 compara.
- **Aprovação virar checkbox sem peso** — mitigação: o pacote de design trata o ato
  como tela própria com consequência dita por extenso.
- **Export sem aprovação por corrida** — mitigação: digest amarrado + `base_version`;
  recusa coberta por teste.

## Human Gates

1. Seleção (2026-08-20) — exercida.
2. **Design Approval Package** aprovado antes do planejamento — exercido em
   2026-08-20, revisão 1 aprovada (dois atos explícitos mantidos):
   [`mock/`](mock/README.md).
3. Merge e deploy.
4. O ATO nominal sobre medição real (Campo do Toca) — ato do usuário pós-deploy, fecha
   a pendência de TRACEABILITY.

## References

- [F-020 — jornada web do orçamento-base](../F-020-orcamento-base-web/feature.md)
- [ADR-0016 — medição como contexto delimitado](../../adr/0016-valuation-bounded-context.md)
- [ADR-0027 — proveniência de preço e fronteira](../../adr/0027-price-source-provenance-and-bid-boundary.md)
- VAL-05 em [Acceptance Criteria do produto](../../product/ACCEPTANCE_CRITERIA.md)
- [Roadmap canônico](../../product/ROADMAP.md)
