# F-035 — Aprovação nominal do orçamento antes do despacho

## Status

`READY_FOR_PLANNING`

> Nasce em 2026-08-22, de uma conversa de alinhamento sobre a cadeia real, quando ficou
> visível uma **assimetria**: a medição tem `POST .../approve` com aprovação nominal
> registrada desde a [F-028](../F-028-boletim-medicao-web/feature.md), e o orçamento — o
> documento que **desce** para a empresa e autoriza a obra acontecer — não tem aprovação
> nenhuma. Sua cadeia termina na planilha.
>
> Selecionada por decisão humana de 2026-08-22, com o desenho fixado na mesma data por
> três escolhas registradas em `Scope`: portão real (não carimbo), papel novo de aprovador
> com recusa de auto-aprovação, e despacho por e-mail/Drive fora de escopo.
>
> Eram **dois gates humanos**, ambos precedendo o planejamento, e os dois foram cumpridos
> em 2026-08-22, em atos separados: o
> [ADR-0046](../../adr/0046-aprovacao-do-orcamento-base.md) foi **aceito**, fixando as oito
> decisões que este contrato marcava como decisão do ADR — inclusive o portão no domínio, a
> quebra declarada de `POST .../estimate` e a recusa de auto-aprovação —, e o **Design
> Approval Package** foi **aprovado**, revisão 1 ([mock/README.md](mock/README.md)).
>
> Com os dois cumpridos, a feature está `READY_FOR_PLANNING`. A implementação deve
> corresponder à revisão aprovada; divergir dela é revisão nova, com registro próprio.

## Classification

`INTERFACE_CHANGE` — etapa nova percebida por humano na jornada do orçamento: o ato de
aprovar com peso de ato, o registro da assinatura, a aprovação caduca e a recusa de
auto-aprovação. O layout impresso do `.xlsx` **não** é superfície nova: ele já existe em
`estimate_workbook.py`, já é auditado e é o que a prefeitura lê — o que se aprova aqui é a
tela, não a planilha. Exige Design Approval Package aprovado antes do planejamento,
conforme [design-approval](../../engineering-os/workflows/design-approval.md).

## Priority

`HIGH` — o orçamento é o documento que autoriza gastar dinheiro público, e hoje ele tem
menos rastro que o boletim que o liquida. Enquanto a assinatura vive no e-mail, o produto
não sabe dizer qual versão do orçamento foi aprovada, e a planilha sai despachável no mesmo
instante em que é montada.

## Problem

A [cadeia operacional](../../product/CADEIA_OPERACIONAL.md) tem três momentos de preço, e a
etapa 9 — aprovação do orçamento — está classificada como "ato humano, fora do produto". O
gerente aprova no e-mail ou na reunião. O produto não registra quem assumiu aquele
orçamento, quando, nem sobre qual conteúdo.

A ausência do registro não é o pior. `POST /v1/estimate-rounds/{id}/estimate`
(`services/api/src/croquito_api/main.py`) **monta, audita e publica o `.xlsx` num ato só**.
Não existe um instante em que o orçamento esteja pronto e ainda não despachável — logo não
há o que aprovar "antes do despacho", porque não há despacho separado da montagem.

A consequência prática, na ordem em que acontece:

1. a orçamentista monta o orçamento e a planilha nasce publicada;
2. a planilha circula — vira anexo da Ordem de Serviço, desce para a empresa;
3. alguém aprova por fora, sobre uma cópia, sem o produto saber qual versão foi;
4. o orçamento é remontado (BDI corrigido, código trocado) e uma planilha nova nasce
   publicada, igualmente despachável;
5. não há como afirmar, depois, qual das duas foi a aprovada.

A medição resolveu exatamente isso e o mecanismo está pronto para copiar: `Valuation`
carrega `approval` amarrada por digest, `content_digest()` exclui a própria aprovação do
cálculo, `ensure_exportable()` recusa fechado, e remontar preserva a assinatura anterior
como **caduca** em vez de apagá-la em silêncio.

## Desired Outcome

O orçamento montado é um artefato **assinável e ainda não despachado**. Uma pessoa com o
papel de aprovador — que não é quem montou — assume o orçamento como está, e a assinatura
fica amarrada ao conteúdo exato assinado. Só então a planilha é publicada, atrás do mesmo
portão fail-closed da medição. Mudar o orçamento depois de assinado não invalida a
assinatura em silêncio: ela fica caduca, visível, e o despacho recusa até um ato novo.

## Scope

1. **Aprovação no domínio** (`packages/valuation/src/croquito_valuation/estimate.py`):
   `Estimate.approval` amarrada por digest, com `content_digest()` que a exclui do cálculo,
   e `export_errors()`/`ensure_exportable()` próprios. Tipo de decisão **próprio**, não
   reuso do `ReviewerDecision` da medição — `reviewer_role` lá é
   `Literal["orcamentista"]`, e ampliá-lo contaminaria a cadeia licitada. O repo já pratica
   essa duplicação deliberada e diz por quê no docstring de `ReviewerDecision`: o que se
   repete é a forma, não o significado.

2. **Montar e publicar deixam de ser um ato só** (decisão humana de 2026-08-22, fixada no
   ADR-0046). `POST .../estimate` passa a **só montar**; publicar vira ato próprio atrás do
   portão, como `calc` → `approve` → `bulletin/export` na medição. É mudança de contrato de
   rota existente, declarada e não aditiva.

3. **Papel `aprovador`**, novo e distinto de `orcamentista` (decisão humana de 2026-08-22).
   Na cadeia real quem assina o orçamento não é quem o montou, e o produto passa a modelar
   isso. A leitura das rotas do orçamento aceita os dois papéis — o aprovador precisa abrir
   a jornada para ver o que assina —, a mutação da cadeia continua exigindo `orcamentista`,
   e a rota de aprovação exige `aprovador`.

4. **Recusa de auto-aprovação** (decisão humana de 2026-08-22): a rota recusa quando o
   `sub` do JWT é quem montou o orçamento da cabeça, mesmo que a pessoa acumule os dois
   papéis. Segregação de fato, não convenção — acumular papel não contorna.

5. **Aprovação caduca**, no molde de `carry_approval_forward` da medição: remontar leva a
   assinatura anterior adiante já caduca. Descartá-la apagaria em silêncio o fato de que
   alguém assinou.

6. **Etapa nova na jornada do orçamento** (`apps/web/src/orcamento/`), conforme o Design
   Approval Package: o ato em dois passos, o registro da assinatura, os dois digests lado a
   lado na caducidade, e o despacho deixando de depender só da existência da planilha.

7. **Cobertura**: exportar sem aprovação recusa sem escrever nada; quem montou não aprova;
   corpo com identidade recusa; remontar caduca e o despacho recusa até ato novo; auditoria
   reprovada não publica; papel exigido antes do lookup nas três rotas; planilha da rota
   logicamente idêntica à do CLI sobre o mesmo orçamento.

## Out of Scope

- **Despacho por e-mail ou Drive** — decisão humana de 2026-08-22. Não há provedor de
  e-mail no projeto; a [F-008](../F-008-ciclo-de-vida-de-conta/feature.md) está `BLOCKED`
  exatamente por isso, e a F-028 deixou o mesmo item fora pela mesma razão. Esta feature
  entrega o ato e o portão; entregar o envio exige o provedor primeiro.
- **Vínculo entre orçamento aprovado e rodada de medição** — é a F-036, e é mais funda:
  depende de o orçamento modelar contrato como entidade, a mesma lacuna que a F-033 deixou
  aberta e que o [ADR-0045](../../adr/0045-terceiro-estado-demanda-sob-contrato.md) nomeia
  na decisão 6.
- **Aprovação em múltiplos níveis, alçadas por valor, delegação** — a segregação entregue
  aqui é de uma camada só.
- **Qualquer mudança na cadeia de medição.** `Valuation`, `ReviewerDecision` e o portão
  `VALUATION_EXPORT_BLOCKED` ficam intocados.
- **Layout impresso do `.xlsx`** e o escritor/auditor da planilha.
- **Congelar a rodada depois de aprovada.** Remontar continua permitido; o que muda é que a
  assinatura caduca e o despacho recusa.

## Acceptance Criteria

1. `make check` e `make test` verdes; `make valuation-estimate-demo` verde com aprovação
   sintética.
2. `POST .../estimate/export` sem aprovação válida recusa com `ESTIMATE_EXPORT_BLOCKED` e
   **nada é escrito** — nem em arquivo temporário, nem no object store.
3. Quem montou o orçamento não o aprova: recusa com `ESTIMATE_SELF_APPROVAL_FORBIDDEN`
   mesmo com os dois papéis no token.
4. Identidade do aprovador vem do JWT; corpo com `approver_id` (ou qualquer campo além de
   `base_version`) recusa `422`.
5. Remontar o orçamento faz a aprovação caducar — `stale: true` na leitura, com os dois
   digests — e a exportação recusa com `APPROVAL_CONTENT_MISMATCH` até um ato novo.
6. Auditoria de round-trip reprovada não publica nada e devolve só os códigos dos achados,
   nunca valor do cliente.
7. Papel exigido antes de qualquer lookup nas três rotas: quem não tem papel não descobre,
   pela diferença entre `403` e `404`, se a rodada existe.
8. Planilha publicada pela rota é logicamente idêntica à do CLI sobre o mesmo orçamento.
9. Snapshot OpenAPI regravado e `API_CONTRACT.md` concordando com a aplicação — inclusive a
   remoção da frase que hoje declara que aprovação não existe neste lado da fronteira.
10. A tela corresponde à revisão aprovada do Design Approval Package.

## Constraints

- O portão é do **domínio**, não da rota: `ensure_exportable()` é a regra, e a rota a
  invoca. É o que faz o CLI obedecer à mesma regra que a API.
- O portão vem **antes de qualquer escrita**, como em `main.py` na exportação do boletim —
  nada em disco temporário antes de o domínio autorizar.
- `packages/valuation` segue sem depender do worker nem do scene graph (ADR-0016).
- A SPA não decide autorização; as etapas são espelho do estado do servidor.
- Nenhuma planilha já publicada é apagada ou torna-se inacessível pela mudança.
- Resposta de rota nunca carrega URL assinada em `POST`, nem valor divergente de auditoria.

## Dependencies

- **ADR-0046** — `ARCHITECTURE_DECISION_REQUIRED`, **satisfeito em 2026-08-22**
  (`Accepted`). O [ADR-0027](../../adr/0027-price-source-provenance-and-bid-boundary.md)
  decisão 6 e o código dele derivado declaravam que o orçamento é "sem aprovação"; autorizar
  a aprovação própria era decisão de arquitetura, não do plano.
- **Design Approval Package** — `DESIGN_APPROVAL_REQUIRED`, **satisfeito em 2026-08-22**
  (revisão 1).
- **Papel no realm** — `aprovador` precisa existir no Keycloak local e no de HML, e ser
  atribuído a alguém. Atribuir papel a pessoa é ato humano.
- F-028 na main — o molde inteiro que esta feature copia.

## Unknowns

1. **Onde a etapa entra na jornada** — etapa nova depois de "Planilha", ou a etapa
   "Planilha" passa a ter dois atos? Proposta no pacote de design; decide no gate.
2. ~~**Se o despacho exige `orcamentista` ou aceita também `aprovador`**~~ → **decidido por
   ato humano em 2026-08-22**: o despacho é do `orcamentista`. Quem orça **não** assina —
   a assinatura é de um superior, o gestor —, mas despachar o que já foi aprovado é
   operação normal de quem montou. Fixado na decisão 7 do
   [ADR-0046](../../adr/0046-aprovacao-do-orcamento-base.md).
3. **Nome do estado "despachado" na tela** — vocabulário fecha no pacote de design.
4. **Nome do papel** — `aprovador`, escolhido por ato humano em 2026-08-22, nomeia o ato e
   não o cargo, para não presumir que todo tenant tenha "gestor" na estrutura. Trocar por
   `gestor` é uma constante, enquanto não houver implementação nem realm publicado.

## Risks

- **Quebra de contrato de rota existente.** `POST .../estimate` deixa de publicar, e quem
  já consome a resposta esperando planilha publicada quebra. Mitigação: hoje o único
  consumidor é `apps/web`, entregue na mesma feature; o snapshot OpenAPI e o teste de
  paridade tornam a mudança visível, não silenciosa.
- **A demo determinística quebra.** `run_estimate_demo` chama a exportação, que passa a
  exigir aprovação. Mitigação: aprovação sintética espelhando `build_synthetic_approval` da
  medição — o mesmo caminho que a medição já usa.
- **Goldens mudam.** `Estimate` ganha campo e sobe `schema_version`. Mitigação: regravar é
  esperado e o diff deve ser só isso; um diff maior é sinal de que algo mais mudou.
- **Jornada travada por falta de papel.** Sem ninguém com `aprovador` no realm, nenhum
  orçamento é despachável. Mitigação: o realm ganha o papel e um usuário local na mesma
  entrega; em HML a atribuição é ato humano listado nos gates.
- **Auto-aprovação recusada em operação de uma pessoa só.** Um tenant pequeno, onde a mesma
  pessoa orça e assina, fica sem caminho. Mitigação: declarado como consequência aceita no
  ADR-0046 — é o preço da segregação pedida —, e a saída é atribuir o papel a outra pessoa,
  não afrouxar o código.

## Human Gates

1. Seleção (2026-08-22) — exercida.
2. **ADR-0046 aceito** — **exercido em 2026-08-22**.
3. **Design Approval Package aprovado** antes do planejamento — **exercido em 2026-08-22**,
   revisão 1 ([mock/](mock/README.md)).
4. Papel `aprovador` atribuído no realm de HML — pendente.
5. Merge e deploy.
6. O ato nominal sobre um orçamento real — ato do usuário, pós-deploy.

## References

- [F-028 — aprovação nominal e boletim da medição pela web](../F-028-boletim-medicao-web/feature.md)
- [F-020 — jornada web do orçamento-base](../F-020-orcamento-base-web/feature.md)
- [ADR-0027 — proveniência de preço e fronteira licitada × pré-licitação](../../adr/0027-price-source-provenance-and-bid-boundary.md)
- [ADR-0045 — o terceiro estado entre pré-licitação e medição](../../adr/0045-terceiro-estado-demanda-sob-contrato.md)
- [Cadeia operacional](../../product/CADEIA_OPERACIONAL.md) — etapa 9
- [Roadmap canônico](../../product/ROADMAP.md)
