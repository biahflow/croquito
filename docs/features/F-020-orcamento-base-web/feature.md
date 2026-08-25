# F-020 — Jornada web do orçamento-base

## Status

`DONE`

> Implementação integrada em 2026-08-20 na branch `f-020-orcamento-web` (T1–T6,
> [plan.md](plan.md)), com revisão do modelo da sessão e evidência consolidada em
> [evidence.md](evidence.md) e **mergeada na `main`** (`9e5ba91` + `b6c82e7`). **Copy
> final e deploy aceitos por ato humano em 2026-08-25** (Daniel Campos). O `.DBF` real da
> EMOP é pendência de **dado, não de código** — a jornada roda com a fixture EMOP
> sintética, como o próprio contrato prevê — e foi **descopada do MVP** para o follow-up
> #65. Este flip reconcilia o roadmap, que ficara em `READY_FOR_HUMAN_REVIEW`.

> Selecionada por decisão humana de 2026-08-19, numa sessão de revisão visual em que
> o usuário perguntou se "Medição" era o orçamento. Não era: o orçamento-base existe
> desde o M8 no domínio e no CLI, e nunca teve rota `/v1` nem tela — confirmado no
> código e no histórico do Git. O usuário escolheu abrir a jornada hospedada completa
> em vez das alternativas mais baratas (expor no servidor local do ADR-0020, ou
> aguardar o template real), e forneceu o exemplar de planilha que o
> [ADR-0027](../../adr/0027-price-source-provenance-and-bid-boundary.md) listava como
> pré-requisito, confirmando que o orçamento sai no mesmo layout do boletim.

A classificação é `INTERFACE_CHANGE` e o gate de Design Approval precede o
planejamento. O gate foi exercido em 2026-08-20: a revisão 1 do
[pacote de aprovação](mock/README.md) foi aprovada por Daniel Campos, e na mesma
decisão o papel de acesso foi definido (reusar o papel da medição — Unknown 3).

## Classification

`INTERFACE_CHANGE` — cria superfície nova percebida por humano (jornada na SPA) e um
documento gerado cuja apresentação é o entregável (a planilha `.xlsx` que a
orçamentista entrega). Exige Design Approval Package aprovado antes do planejamento,
conforme [design-approval](../../engineering-os/workflows/design-approval.md).

## Priority

`HIGH` — é o "gerador de orçamento" da fase 1 da visão de produto. A cadeia de
domínio já está paga (M8); o que falta é exatamente a parte que o cliente usa.

## Problem

O produto tem duas cadeias de preço com regras opostas, e só uma delas chegou ao
cliente:

- **Medição (obra licitada)** — o contrato manda, só `PriceOrigin.sco`, guardrail
  `BULLETIN_PRICE_ORIGIN_FORBIDDEN`. Tem rotas `/v1` e tela.
- **Orçamento-base (pré-licitação)** — cadeia SCO → EMOP → composição, entregue no
  M8 como `build_worksite_estimate` + `import-emop` + `import-compositions`. **Sem
  rota `/v1`, sem tela, sem exportação.** Só roda por linha de comando.

Consequências práticas: a orçamentista não alcança o orçamento-base pelo produto; a
navegação não deixa claro onde termina a medição e onde começaria o orçamento (foi
literalmente a dúvida que originou esta feature); e o investimento do M8 permanece
sem superfície de uso.

O `.xlsx` e a UI estavam condicionados em ROADMAP e ADR-0027 a "haver exemplar real
do modelo da prefeitura como template". Esse pré-requisito **foi satisfeito** em
2026-08-19.

## Desired Outcome

A orçamentista entra no produto, abre um orçamento-base, instala a cascata de
catálogos na ordem que declarar, associa a prancha, revisa o takeoff, confirma os
códigos citando a fonte, e obtém a planilha orçamentária no layout que a prefeitura
valida — com a proveniência de preço impressa por linha e o BDI declarado, pronta
para submissão. Sem CLI.

## Scope

1. **Contrato gerado** — `Estimate` entra em `packages/contracts/contracts.manifest.json`
   (`module="croquito_valuation.estimate"`, `model="Estimate"`,
   `version_attr="ESTIMATE_SCHEMA_VERSION"`); `make contracts` regenera schema e
   TypeScript. Os gerados nunca são editados à mão.
2. **BDI como conceito de domínio** — percentual declarado no `Estimate`, e por linha
   o preço unitário sem e com BDI, com `total` recomputado sobre o preço com BDI.
   Mesma disciplina do módulo: `ExactDecimal` (recusa `float`), dinheiro trunca,
   quantidade arredonda. Os `model_validator` recomputam o BDI junto com o total,
   para a revalidação na leitura seguir sendo o portão. Exige bump de
   `ESTIMATE_SCHEMA_VERSION`, feito **antes** da publicação no manifesto.
3. **Rotas `/v1`** espelhando `/v1/valuation-rounds*`: abrir orçamento, instalar
   catálogos da cascata por presign, associar prancha, disparar extração, decidir
   takeoff, sugerir e confirmar código, montar o orçamento, ler. Papel exigido
   inclusive na leitura; `Idempotency-Key` em toda mutação; `base_version` com
   `409 REVISION_CONFLICT`; erros em `application/problem+json` com a invariante
   recusada em `details.code`.
4. **Persistência** — tabelas espelhando `ValuationRoundRecord` e
   `ValuationRoundRevisionRecord` (revisões append-only, blobs no object store por
   chave, metadados e digests no banco). Migração Alembic forward-only.
5. **Tela** em `apps/web`, espelhando a jornada de medição: tipos de domínio vindos
   de `@croquito/contracts`, etapas como espelho do estado do servidor (nunca máquina
   de estados própria), erros de domínio traduzidos por tabela — nunca mensagem
   inventada, `Decimal` sempre string. Entrada nova no seletor de jornadas e na rota.
6. **Exportação `.xlsx`** no layout da prefeitura, reusando o modelo de layout de
   `template.py`, acrescido da coluna de fonte e das colunas de BDI, com portão de
   auditoria de recomputação antes de publicar.

## Out of Scope

- **Ponte croqui → orçamento** (quantitativo derivado do scene graph aprovado):
  segue bloqueada por identidade estruturada de elemento, conforme
  [ADR-0016](../../adr/0016-valuation-bounded-context.md) e o bullet reservado no
  roadmap. O insumo continua sendo a prancha lida pela extração da própria cadeia.
- **Dívidas da medição**: aprovação nominal e exportação `.xlsx` do boletim seguem
  fora da web, em marco próprio.
- **Aplicar BDI à medição**: o preço contratado já o embute.
- **Versionar planilha real de cliente**: o template real vive fora do Git; a fixture
  permanece sintética.
- Curva ABC, cronograma físico-financeiro e memorial descritivo.

## Acceptance Criteria

1. `make check` e `make test` verdes; snapshot OpenAPI atualizado por ato deliberado,
   com diff só de adição.
2. `Estimate` publicado no manifesto de contratos, com schema e TypeScript gerados
   por `make contracts` e sem drift em `make check`.
3. A cadeia inteira do orçamento roda pelas rotas `/v1` num teste e2e novo,
   espelhando `tests/e2e/test_valuation_full_chain.py`, sem passar pelo CLI.
4. Rotas de orçamento exigem o papel de autorização inclusive na leitura (403 sem
   papel); mutação sem `Idempotency-Key` recusa; `base_version` desatualizado devolve
   `409 REVISION_CONFLICT` — todos cobertos por teste.
5. Toda `EstimateLine` do `.xlsx` imprime a fonte do preço e a data-base; a planilha
   declara o BDI e traz preço unitário sem e com BDI.
6. O `.xlsx` só é publicado depois que a auditoria reabre o arquivo e reconfere os
   valores; falha do auditor não publica nada.
7. `make valuation-estimate-demo` continua verde e determinística.
8. A exportação do boletim de medição permanece byte-idêntica: as colunas novas do
   modelo de layout são aditivas e opcionais.
9. Nenhum preço de EMOP ou composição alcança a medição:
   `BULLETIN_PRICE_ORIGIN_FORBIDDEN` segue coberto.

## Constraints

- `packages/valuation` é contexto delimitado: pode depender de `croquito_core` para
  ids e utilidades, **nunca** do worker nem do scene graph (ADR-0016).
- A cascata de fontes é dado do chamador, nunca lógica embutida; a proveniência por
  linha (VAL-09) e a revalidação na leitura são o portão do orçamento — a API deve
  reler e revalidar o artefato, não confiar em cache.
- Migrações forward-only; o CI compara o schema resultante com os modelos e reprova
  divergência (ADR-0029).
- O modelo de layout de planilha é compartilhado com o escritor do boletim.
- A SPA não decide autorização; o backend decide.

## Dependencies

- **Arquivo `.DBF` real do catálogo EMOP** — depende de assinatura GRE, ato do
  usuário. Enquanto não chega, a jornada roda com fixture sintética; o importador e
  seu layout-como-dado já existem.
- Design Approval Package aprovado (ver Human Gates).
- Marco M8 (entregue): domínio, importadores e CLI do orçamento-base.

## Unknowns

1. **Como o escritor de planilha passa a aceitar `Estimate`.** Hoje ele escreve a
   partir dos modelos da medição. Reusar o layout não é reusar a função: é preciso um
   adaptador `Estimate → linhas de planilha`, ou generalizar o escritor. Não decidido
   — é a maior incerteza técnica da feature.
2. **Forma do auditor de recomputação do orçamento.** A medição tem auditoria que
   reabre o `.xlsx` e compara centavo a centavo; o orçamento não tem equivalente.
   Reaproveitar o mesmo auditor ou escrever um próprio, não decidido.
3. **Papel de acesso.** Resolvido por decisão humana de 2026-08-20: **reusa o papel
   da medição** — a mesma orçamentista opera as duas cadeias; papel próprio de
   pré-licitação fica como possibilidade futura, sem espaço reservado em código.
4. **Granularidade do BDI.** Decisão humana de 2026-08-19: **percentual único por
   orçamento**, com o BDI por grupo reservado como espaço futuro. Desenhado assim na
   revisão 1 do [pacote de aprovação](mock/README.md), que ainda não foi aprovada.
5. **Nome e lugar da jornada na navegação**, dado que a dúvida de origem foi
   justamente medição × orçamento. Proposta na revisão 1 do
   [pacote de aprovação](mock/README.md): terceira jornada no seletor, rota própria e
   uma linha fixa em cada jornada declarando o momento. Pendente do gate humano.

## Risks

- **Colisão com a exportação da medição**: acrescentar coluna obrigatória ao modelo
  de layout quebraria o boletim. Mitigação: colunas novas aditivas e opcionais, com
  teste que prova a planilha da medição inalterada.
- **Publicar planilha sem auditoria**: se o `.xlsx` entrar sem o portão de
  recomputação, a feature entrega documento com garantia menor que o resto do
  produto. Mitigação: critério de aceite 6, fail-closed.
- **Confusão de fronteira**: com BDI e EMOP na base de código, cresce o risco de
  alguém "consertar" a medição achando que faltou. Mitigação: registrar em ADR que
  BDI é conceito de pré-licitação, e manter o guardrail coberto por teste.
- **Quebra de contrato tardia**: acrescentar campo obrigatório ao `Estimate` depois
  de publicá-lo no manifesto é caro. Mitigação: bump de versão antes da publicação.
- **Dado de cliente no repositório**: o exemplar de planilha usado como referência é
  dado real e não pode ser versionado nem virar fixture.

## Human Gates

1. **Seleção de prioridade** — exercida em 2026-08-19 (registro no roadmap canônico).
2. **Design Approval Package** aprovado antes do planejamento; nenhum agente aprova
   design — exercido em 2026-08-20, revisão 1 aprovada: [`mock/`](mock/README.md).
   Copy final e conferência contra o exemplar real permanecem abertas.
3. **Aceite do ADR** que estende a fronteira do ADR-0027 com o BDI:
   [ADR-0038](../../adr/0038-bdi-como-conceito-de-pre-licitacao.md) — **aceito por
   ato humano em 2026-08-20**.
4. **Obtenção do `.DBF` real da EMOP** (assinatura GRE) — **descopada do MVP** para o
   follow-up #65; a jornada roda com fixture sintética até o arquivo real chegar.
5. **Merge e deploy** — exercidos; aceitos por ato humano em 2026-08-25.

## References

- [Design Approval Package, revisão 1](mock/README.md)

- [ADR-0027 — proveniência de preço e fronteira licitada × pré-licitação](../../adr/0027-price-source-provenance-and-bid-boundary.md)
- [ADR-0016 — medição como contexto delimitado](../../adr/0016-valuation-bounded-context.md)
- [ADR-0028 — medição na API `/v1` autenticada](../../adr/0028-medicao-na-api-v1-autenticada.md)
- [ADR-0029 — runner de migrations revisadas](../../adr/0029-runner-de-migrations-revisadas.md)
- [F-003 — migração da medição para a API `/v1`](../F-003-medicao-v1-migration/feature.md)
- [Contexto da medição](../../architecture/VALUATION_CONTEXT.md)
- [API Contract](../../architecture/API_CONTRACT.md)
- [Roadmap canônico](../../product/ROADMAP.md)
