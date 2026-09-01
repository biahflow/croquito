# F-040 · T6 — A porta da medição seguinte: herança e prévia antes de gravar

Feature: [F-040](../feature.md) · Plano: [plan.md](../plan.md) · Estado: **Entregue com desvio**

> **A "exceção declarada" descrita no fim deste documento foi desfeita pela
> [T7](T7-previa-no-servidor.md).** Ela não era exceção que coubesse declarar: a regra do
> `apps/web/AGENTS.md` é de produto, e o desvio veio do handoff desta tarefa, que mandou
> calcular a prévia no cliente. A conta passou para o servidor. O restante deste documento é
> preservado como o registro do que a T6 fez e por quê.

## Por que esta tarefa existe

Ela não nasce de requisito novo. Nasce de **três decisões do
[Design Approval Package](../mock/README.md) revisão 1** — aprovado por ato humano em
2026-08-27 — que a T5 deu por entregues e não construiu. A captura da evidência de navegador,
em 2026-08-28, as expôs:

| Decisão aprovada | O que existia depois da T5 |
| --- | --- |
| 1 — a medição seguinte é uma das **duas portas da abertura**, não uma tela separada | um botão na lista de rodadas que criava a rodada **na hora**, com o formulário vazio |
| 4 — a **herança é mostrada antes de qualquer declaração** (contratado, vigente, medido, acumulado, saldo) | nada: não havia tela entre o clique e a rodada criada |
| 6 — a **prévia mostra o efeito código a código antes de gravar** | nada: o efeito só aparecia **depois** de gravar, na memória |

A consequência funcional era a pior parte: como o caminho da medição seguinte não passava pela
abertura, **não havia como declarar uma RE-RA na medição seguinte pela tela**. A API sempre
aceitou `previous_round_id` junto de `amendment`; a tela é que não oferecia. E re-ratificação é
exatamente o que acontece **entre** medições — no período 1 não há o que re-ratificar
([ADR-0056](../../../adr/0056-re-ra-declarada-e-o-consolidado-da-medicao-seguinte.md),
contexto). O caminho principal da feature estava inalcançável pela interface.

Pacote aprovado é contrato da superfície: decisão aprovada e não construída é dívida, não
escolha de quem implementa.

## Objetivo

Fazer a medição seguinte passar pela **mesma porta da abertura**, com a herança da rodada
anterior visível antes de qualquer declaração, a RE-RA declarável ali, e a prévia do efeito
código a código antes do `POST`.

## Escopo

- `apps/web/src/medicao/MedicaoApp.tsx`: a origem da rodada vira escolha de **três** portas
  (orçamento assinado, rodada anterior, catálogo por upload); o botão “Abrir a medição n+1”
  passa a levar à abertura em vez de criar a rodada; os componentes `HerancaDaRodadaAnterior`
  e `PreviaDaReRa`.
- `apps/web/src/medicao/previa.ts` (novo, puro): a aritmética exata em texto, a herança, a
  prévia e os códigos a resolver no catálogo.
- `apps/web/src/medicao/styles.css`: sem cor nova — reaproveita a tabela e o selo petróleo da
  RE-RA.
- Testes: `previa.test.ts`, `MedicaoApp.test.tsx`, `requests.test.ts` e um teste de API que
  **fixa o comportamento já existente** do servidor, para servir de oráculo à prévia.

## Fora de escopo

- Rota nova na API, mudança de modelo de domínio, migração. O servidor **não muda**: ele já
  aceitava `previous_round_id` com `amendment`, e o read-model já traz o contratado por código.
- Redesenhar o que o pacote aprovado decidiu (cores, selos, ordem das colunas).
- O nome legível de quem declarou — hoje sai o `sub` do JWT; é dívida conhecida, registrada em
  [evidence.md](../evidence.md), e não é consertada aqui.
- A prévia na abertura a partir do **orçamento assinado**: ela precisa do contratado código a
  código, e a lista de origens só entrega contagem e total. Fica registrada como lacuna.
- Recaptura das telas novas (`BROWSER_REQUIRED`), que é tarefa própria.

## Critérios de aceite

1. Clicar em “Abrir a medição n+1” leva à abertura com origem, período e `previous_round_id`
   já resolvidos, **sem criar rodada nenhuma** (mock, decisões 1 e 2).
2. A herança da rodada anterior é exibida código a código antes de qualquer declaração, com
   contratado e vigente iguais quando não há RE-RA (mock, decisão 4).
3. É possível declarar uma RE-RA na abertura da medição seguinte, e a rodada nasce
   re-ratificada.
4. A prévia mostra contratado → efeito → vigente → saldo antes de gravar, e os números batem
   com os que a API devolve depois de gravar.
5. Item novo na prévia mostra descrição, unidade e preço resolvidos do catálogo contratual
   (ADR-0056, decisão 7); não resolvido, é declarado pendente por extenso.
6. A abertura a partir do orçamento assinado não muda de comportamento.
7. O vigente continua sem campo onde ser escrito: existe o delta que o produz (mock, decisão 6;
   ADR-0056, decisão 3).

## A exceção declarada à regra “a tela nunca soma”

O [AGENTS.md do web](../../../../apps/web/AGENTS.md) diz que a tela da medição nunca soma,
multiplica ou arredonda dinheiro ou quantidade — exibe as strings decimais que o servidor
mandou. A prévia é a **exceção declarada** desta tarefa, e a fronteira dela é estreita:

- o que a prévia produz é **projeção antes do fato**, rotulada como prévia na própria tela; o
  número que vale depois de gravar continua vindo da resposta da API, e é o servidor que
  permanece autoridade;
- a aritmética vive num módulo puro (`previa.ts`), é **exata em texto** sobre `BigInt` e
  reproduz a semântica de `Decimal` do Python (a escala da soma é a maior das duas). Nada passa
  por `Number`, nada é arredondado;
- **nenhuma conta de dinheiro** acontece: o total medido no período é a string que o boletim do
  servidor já traz;
- os números da prévia são fixados contra os da API por
  `tests/api/test_valuation_round_from_estimate.py::test_a_medicao_seguinte_nasce_re_ratificada`
  e `apps/web/src/medicao/previa.test.ts`, que citam um ao outro: divergir em silêncio reprova
  um dos dois.

## Validação

`uv run python scripts/check_docs.py`, `make check` e `make test` verdes.
