# ADR-0046: O orçamento tem aprovação nominal própria, e publicar deixa de ser parte de montar

Status: Accepted  
Data: 2026-08-22 (aceito por ato humano na mesma data)  
Responsável: Product / Engineering

## Contexto

A [cadeia operacional](../product/CADEIA_OPERACIONAL.md) tem três documentos financeiros
com as mesmas colunas e momentos opostos. Dois deles descem da prefeitura para a empresa
antes da obra e a autorizam: a prancha e a **planilha orçamentária aprovada**, anexos da
Ordem de Serviço. O terceiro — o boletim de medição — sobe depois da execução e libera o
pagamento.

O boletim tem aprovação nominal desde a [F-028](../features/F-028-boletim-medicao-web/feature.md):
`Valuation.approval` amarrada por digest, `content_digest()` que exclui a própria aprovação
do cálculo, `ensure_exportable()` recusando fechado, e recálculo que **preserva** a
assinatura anterior como caduca em vez de apagá-la. O orçamento não tem nada disso. A etapa
9 da cadeia está classificada como "ato humano, fora do produto", e é literalmente isso: o
gerente aprova no e-mail ou na reunião.

Duas coisas tornam a lacuna mais séria do que "falta um registro".

**Primeira: não existe o instante em que aprovar.** `POST /v1/estimate-rounds/{id}/estimate`
monta o `Estimate`, audita a planilha e **publica o `.xlsx` no mesmo ato**. Um orçamento
nasce despachável. Não há como aprovar "antes do despacho" porque o despacho não é um ato
separado — é consequência automática da montagem. Remontar produz outra planilha
igualmente publicada, e depois não há como afirmar qual das duas foi a aprovada.

**Segunda: o código declara que aprovação não existe aqui.** A decisão 6 do
[ADR-0027](0027-price-source-provenance-and-bid-boundary.md) diz que o orçamento-base é
cadeia própria "sem contrato, sem saldo e sem aprovação **de medição** — o portão é a
auditoria de recomputação". O que foi decidido ali é que o orçamento não passa pelo portão
**contratual** da medição: saldo, período, código no contrato. Nenhum desses conceitos
existe antes da licitação, e isso segue verdadeiro.

Mas a frase foi endurecida na implementação para além do que decidiu, em dois lugares que
hoje afirmam que o orçamento não tem aprovação **alguma**:

- `packages/valuation/src/croquito_valuation/estimate.py` — "Sem período, sem contrato, sem
  saldo e sem aprovação: nenhum desses conceitos existe antes da licitação."
- `docs/architecture/API_CONTRACT.md` — "O que **não** existe aqui, por construção:
  contrato, período, saldo e aprovação."

A afirmação é falsa quanto à aprovação, e a própria cadeia operacional já registrava o
contrário na etapa 9: a aprovação do orçamento existe, é o ato mais consequente da cadeia
antes da obra, e acontece **precisamente** antes da licitação. Confundir "não tem o portão
contratual da medição" com "não tem aprovação" é o que impediu esta feature de nascer.

A [F-035](../features/F-035-aprovacao-do-orcamento/feature.md) está `BLOCKED` esperando
esta decisão. As perguntas que o contrato dela marca como decisão do ADR: se a aprovação
morde de verdade ou só carimba; onde ela vive; quem assina; e se quem montou pode assinar.

## Decisão

1. **O orçamento tem aprovação nominal própria, e ela não é a aprovação da medição.** O
   ADR-0027 **não é substituído**: ele continua `Accepted` e correto no que decidiu — o
   orçamento segue sem contrato, sem saldo e sem período, e nada montado nele alcança um
   boletim sem passar pela medição. O que este ADR fixa é a distinção que a leitura literal
   da decisão 6 apagava: **ausência do portão contratual não é ausência de assinatura**. As
   duas aprovações são atos distintos, de contextos distintos, e nenhuma delas depende da
   outra.

2. **Montar e publicar deixam de ser um ato só.** `POST .../estimate` passa a **só montar**
   o orçamento; publicar o `.xlsx` vira ato próprio, atrás do portão, na forma que a
   medição já tem (`calc` monta → `approve` assina → `bulletin/export` publica). É mudança
   de contrato de rota existente, declarada, não aditiva: quem consumia a resposta esperando
   planilha publicada precisa mudar. Aceitamos a quebra porque a alternativa é manter um
   orçamento que nasce despachável, e aí a aprovação seria decorativa.

3. **A aprovação vive no DOMÍNIO, não na camada de aplicação.** `Estimate.approval`, com
   `content_digest()` que a exclui do cálculo — assinar não muda o que foi assinado — e
   `export_errors()`/`ensure_exportable()` próprios do `Estimate`. É o que faz o CLI
   obedecer à mesma regra que a API: um portão que morasse na rota deixaria
   `croquito-valuation` publicando sem assinatura, e passaria a haver duas verdades sobre o
   mesmo artefato. O portão do orçamento **não recebe contrato por parâmetro**, ao contrário
   do da medição, e é isso que mantém o ADR-0027 de pé: os códigos de saldo, período e
   contrato não existem deste lado da fronteira.

4. **O tipo de decisão é próprio, não reuso.** `ReviewerDecision` tem `reviewer_role:
   Literal["orcamentista"]`, e ampliá-lo faria um papel do orçamento aparecer no vocabulário
   da medição. O orçamento ganha o seu, na mesma forma. É a duplicação deliberada que o
   [ADR-0016](0016-valuation-bounded-context.md) já sustenta e que o docstring de
   `ReviewerDecision` explica: o que se repete é a forma, não o significado.

5. **`aprovador` é papel novo, distinto de `orcamentista`.** Na cadeia real quem assina o
   orçamento não é quem o montou — é o gestor, do lado da prefeitura. O produto passa a
   modelar essa separação em vez de deixá-la implícita. A leitura das rotas do orçamento
   aceita os dois papéis, porque o aprovador precisa abrir a jornada para ver o que assina;
   a mutação da cadeia continua exigindo `orcamentista`; a rota de aprovação exige
   `aprovador`. A checagem de papel continua vindo antes de qualquer lookup.

6. **A rota de aprovação recusa auto-aprovação.** Quando o `sub` do JWT é quem montou o
   orçamento da cabeça, a rota recusa — mesmo que a pessoa acumule os dois papéis. Sem isso
   o papel novo seria cerimônia: bastaria atribuir os dois a uma pessoa para a segregação
   evaporar sem deixar rastro. Para isso a revisão grava **quem montou** no ato que monta,
   em vez de descobri-lo por arqueologia na cadeia append-only, onde `created_by` é de quem
   fez o último ato e não de quem montou.

7. **Despachar não é assinar.** A exportação exige `orcamentista`, não `aprovador`: assinar
   é assumir o conteúdo, despachar é operar o envio. São atos diferentes e o produto não os
   funde só porque acontecem em sequência.

8. **Remontar não apaga a assinatura: torna-a caduca.** Igual à medição. A aprovação
   anterior é levada adiante amarrada ao digest antigo, a leitura mostra os dois digests, e
   o despacho recusa com `APPROVAL_CONTENT_MISMATCH` até um ato novo. Descartar a assinatura
   apagaria em silêncio o fato de que alguém assinou.

## Alternativas

- **Aprovação como carimbo, sem portão** (registrar quem aprovou, mantendo `POST
  .../estimate` publicando) — rejeitada: a planilha continuaria saindo antes da assinatura,
  e o registro descreveria um ato que não governa nada. Seria o mesmo problema de hoje com
  uma linha a mais no banco.
- **Congelar a rodada ao aprovar** (proibir remontar depois da assinatura) — rejeitada:
  troca um problema por outro. Corrigir um BDI errado exigiria abrir rodada nova e refazer
  todas as decisões de código, e a aprovação caduca já resolve com honestidade — mostra que
  mudou e recusa despachar.
- **Reusar `ValuationApproval` e ampliar `ReviewerDecision`** — rejeitada pela decisão 4:
  acopla os dois contextos delimitados pelo tipo, contra o ADR-0016, para economizar um
  modelo de seis campos.
- **Mesmo papel `orcamentista` para montar e assinar** (o que a F-028 fez na medição) —
  rejeitada para o orçamento: na medição quem mede e quem assina são a mesma função
  profissional, e no orçamento não são. Copiar a F-028 aqui seria copiar a forma ignorando
  o significado.
- **Recusar auto-aprovação só por convenção documentada** — rejeitada: convenção que o
  código não sustenta é a mesma coisa que nada, e a segregação foi pedida explicitamente.
- **Bloquear a publicação por flag de configuração em vez de aprovação** — rejeitada: move
  a decisão para o ambiente, onde ela não tem autor nem instante, que é exatamente o que a
  assinatura existe para registrar.

## Consequências

### Positivas

- O documento que autoriza gastar dinheiro público passa a ter o mesmo rastro que o
  documento que o liquida: quem assumiu, quando, e sobre qual conteúdo exato.
- Existe um estado novo e útil — orçamento **pronto e ainda não despachado** —, que é onde a
  revisão humana cabe.
- Editar depois de assinar deixa de ser silencioso: a caducidade é visível e o despacho
  recusa.
- O portão no domínio faz API e CLI obedecerem à mesma regra, sem duas verdades.
- A separação entre quem orça e quem autoriza fica no sistema, não no costume.

### Negativas

- **Quebra de contrato de rota existente.** `POST .../estimate` deixa de publicar. Hoje o
  único consumidor é `apps/web`, entregue na mesma feature, mas a quebra é real e aparece no
  snapshot de OpenAPI.
- **Operação de uma pessoa só fica sem caminho.** Um tenant onde a mesma pessoa orça e
  assina não consegue despachar. É o preço da segregação pedida; a saída é atribuir o papel
  a outra pessoa, não afrouxar o código.
- **A demo determinística passa a exigir aprovação sintética**, como a da medição já exige.
- **Goldens do orçamento mudam** — `Estimate` ganha campo e sobe `schema_version`.
- **Um papel novo para administrar** no realm de cada ambiente, e enquanto ninguém o tiver,
  nenhum orçamento é despachável.

## Riscos e mitigação

| Risco | Mitigação |
|---|---|
| Jornada travada por ninguém ter o papel `aprovador` | Papel e usuário local entram no realm na mesma entrega; a atribuição em HML é gate humano listado no contrato da feature |
| A quebra de `POST .../estimate` passar despercebida por um consumidor | Snapshot de OpenAPI e o teste de paridade com o API Contract reprovam divergência; a mudança é registrada no contrato antes do código |
| Aprovação virar botão sem peso | Pacote de Design Approval trata o ato como tela própria em dois passos, com as consequências ditas por extenso — o mesmo desenho aprovado na F-028 |
| Despachar sem assinatura por corrida entre atos | Digest amarrado ao conteúdo + `base_version`; a recusa é coberta por teste |
| Portão do orçamento herdar códigos contratuais da medição por cópia descuidada | `Estimate.export_errors()` não recebe `ContractWorkbook` por assinatura: não há como o código de saldo entrar |
| Auto-aprovação contornada por acúmulo de papéis | A recusa compara identidade, não papel; teste cobre o caso com os dois papéis no token |

## Rastreabilidade

- Requirements: VAL-05 (o irmão na medição), critério novo do orçamento em
  [Acceptance Criteria](../product/ACCEPTANCE_CRITERIA.md)
- Feature: [F-035](../features/F-035-aprovacao-do-orcamento/feature.md)
- Relacionado: [ADR-0016](0016-valuation-bounded-context.md),
  [ADR-0027](0027-price-source-provenance-and-bid-boundary.md),
  [ADR-0038](0038-bdi-como-conceito-de-pre-licitacao.md),
  [ADR-0045](0045-terceiro-estado-demanda-sob-contrato.md)
- Supersedes: none — o ADR-0027 segue `Accepted`; este ADR refina a leitura da decisão 6
- Superseded by: none
