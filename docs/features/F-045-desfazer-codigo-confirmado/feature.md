# F-045 — Desfazer um código confirmado

## Status

`DONE`

> **Aceita por ato humano em 2026-09-05** (Daniel Campos, pelo chat), sobre a rodada de
> revisão da mesma data: revisão linha a linha do núcleo (`apply_code_revocation` fail-closed
> — o par sai da lista em vez de ganhar status, o fechamento cai junto, o mesmo par volta a
> ser decidível; a compensação do precedente na mesma transação, com escopo de uma praça e
> origem `round`; a fonte de preço lida antes de o par sair) terminou **`REVIEW_PASS`**, sem
> achado de código. A assimetria entre as jornadas foi conferida e é deliberada: no orçamento
> a D7 recusa revogar pós-aprovação porque o digest da assinatura não caduca; na medição a
> caducidade por digest de fontes já acusa a divergência e bloqueia o export. O código está
> integrado desde os PRs #117 e #118.
>
> O aceite fechou o **unknown 1**: **a recusa da D7 vira definitiva** — revogar depois da
> aprovação do orçamento continua recusado (`ASSIGNMENT_REVOCATION_AFTER_APPROVAL`), e quem
> aprovou desaprova primeiro ou refaz a rodada. Liberar no futuro segue sendo apagar uma
> checagem, com a mesma reversibilidade de sempre. Dívida declarada: nenhum desfazer real de
> orçamentista atravessou ainda; o ato inverso (desfazer uma rejeição) permanece fora de
> escopo, registrado.

> Implementada em 2026-08-28, com os dois gates de decisão cumpridos no mesmo dia: ADR-0061
> aceito e pacote de design revisão 1 aprovado (Daniel Campos).

> Nasce em 2026-08-28, da revisão 2 do pacote de design da
> [F-044](../F-044-precedente-de-codigo/feature.md). Ao decidir marcar o código que veio de
> menos praças que o rótulo, a pergunta seguinte apareceu sozinha: *e se a pessoa aceitar o
> pacote com o código errado dentro?* A resposta era — e ainda é — que não há volta.
>
> A lacuna **não é da F-044**: ela existe desde a [F-038](../F-038-pacote-de-servicos/feature.md),
> quando a identidade da decisão virou o par `(item, código)`. O que a F-044 fez foi
> aumentar o preço dela, ao criar um ato que grava N códigos de uma vez.

## Classification

`INTERFACE_CHANGE` — acrescenta um ato à etapa de códigos, sobre decisão já gravada.

## Priority

`HIGH` — decidido pelo dono em 2026-08-28, na mesma conversa que registrou a lacuna.

## Problem

A etapa de códigos tem três rotas: ler (`GET`), decidir (`decisions`) e fechar o pacote
(`closures`). **Nenhuma delas desfaz.** A identidade da decisão é o par `(item_id, code)`
(ADR-0053), e `_ensure_batch_decidable` recusa re-decidir um par já decidido com
`ASSIGNMENT_ITEM_ALREADY_DECIDED`.

Não existe rollback de revisão: a revisão é imutável e a cadeia só avança. O único conserto
de um código confirmado por engano, hoje, é **começar a rodada de novo** — jogando fora o
takeoff revisado, as calibrações e todas as outras decisões da praça — ou seguir com o
orçamento errado.

A assimetria que isso produz é o problema real:

| Caminho | Custo do erro |
|---|---|
| Desconfiar e **não** aceitar | alguns cliques: o código continua alcançável um a um pelo bloco da fonte e pela busca da etapa, que casa por código |
| Aceitar e **descobrir depois** | irreversível na rodada |

O lado barato é o da cautela, e o lado caro é o do clique fácil — exatamente o inverso do
que a jornada deveria premiar.

## Desired Outcome

A orçamentista pode retirar um código que confirmou por engano, com justificativa, sem
perder o resto do trabalho da praça — e o sistema não finge que a confirmação nunca
aconteceu: ela fica no histórico, revogada por um ato tão rastreável quanto o que a criou.

## Scope

1. **Revogação como ato próprio**, com rota própria nas duas jornadas (medição e
   orçamento-base), justificativa obrigatória, `Idempotency-Key` e `base_version`, como as
   demais mutações da etapa.
2. **Domínio**: o par revogado sai do conjunto corrente de assignments e passa a constar em
   `revocations`, com quem revogou, quando e por quê. A revisão anterior continua existindo
   com o par lá dentro — desfazer não apaga o que foi feito.
3. **O pacote reabre.** Se o item tinha `ItemPackageClosure`, ela cai junto: o pacote mudou,
   e a afirmação de completude precisa ser refeita por quem a fez.
4. **O índice de precedentes é compensado** na mesma transação: a observação
   `(praça, rótulo, fonte, código)` que aquele fechamento gravou é removida. Sem isso, o
   índice ensinaria à praça seguinte um código que esta praça desfez.
5. **Tela**: desfazer no cartão do código confirmado, com o que vai acontecer à vista antes
   do clique — inclusive que o pacote reabre. **Nas duas jornadas**: o orçamento-base na
   revisão 1 do pacote de design, a medição na revisão 2.

## Out of Scope

- **Desfazer a rejeição de um item.** É o ato inverso do outro lado e tem regra própria
  (rejeição fecha o item sozinha); entra quando alguém pedir.
- **Rollback de revisão.** Voltar a rodada inteira a um ponto anterior é outra feature, de
  outro tamanho, e não é o que resolve este problema.
- **Desfazer depois do orçamento aprovado.** A aprovação é gate humano com efeito próprio; o
  que acontece com ela é decisão que esta feature não toma. Ver Unknowns.
- **Editar uma confirmação** (trocar o código sem desfazer). Revogar e confirmar de novo são
  dois atos, e são dois de propósito: a troca esconderia a decisão original.

## Acceptance Criteria

1. Revogar um par confirmado remove-o do conjunto corrente e o registra em `revocations`
   com autor, instante e justificativa.
2. A revisão anterior continua intacta e legível, com o par ainda confirmado nela.
3. Revogar o último código confirmado de um item fechado **reabre** o pacote, e a resposta
   diz isso.
4. A observação de precedente daquele par, gravada pelo fechamento desta praça, é removida
   na mesma transação — a contagem de praças do índice cai.
5. Revogar par inexistente, par já revogado ou item fora do takeoff é recusa nomeada.
6. Revogação sem justificativa é recusa.
7. Depois de revogar, o mesmo par pode ser confirmado outra vez — desfazer não bane o código.
8. Conjunto no regime `1.0.0` (um código por item, anterior ao ADR-0053) não aceita
   revogação.
9. Nenhum teste existente afrouxado; o boletim e o portão de exportação continuam recusando
   pacote aberto.

## Constraints

- A revisão é imutável e a cadeia só avança: revogar é **decisão nova**, nunca edição de
  revisão gravada.
- Justificativa é obrigatória, como na rejeição — desfazer é ato que alguém vai auditar.
- A compensação do índice só apaga observação desta praça e de origem `round`; observação
  semeada de orçamento passado ([F-044](../F-044-precedente-de-codigo/feature.md) fonte B)
  não é tocada por um ato de rodada.

## Dependencies

- [ADR-0053](../../adr/0053-cardinalidade-n-n-elemento-servico.md) — o par `(item, código)`
  como identidade, que é o que se revoga.
- [F-038](../F-038-pacote-de-servicos/feature.md) — o pacote e o fechamento.
- [F-044](../F-044-precedente-de-codigo/feature.md) — o índice que precisa ser compensado.
- ADR desta feature: a semântica da revogação (ato próprio, reabertura do pacote e
  compensação do índice) precisa de decisão registrada antes da implementação.

## Unknowns

1. **O que fazer quando o orçamento já foi aprovado.** Aprovar é gate humano, e a aprovação
   amarra por digest o conteúdo do orçamento; revogar **não** remonta o orçamento, então a
   assinatura continuaria conferindo enquanto os códigos por baixo dela mudaram.
   > **Estado**: a implementação **recusa** (`ASSIGNMENT_REVOCATION_AFTER_APPROVAL`) — e a
   > recusa deixou de ser provisória: **decidida como definitiva em 2026-09-05** (Daniel
   > Campos, no aceite da feature). Quem aprovou desaprova primeiro ou refaz a rodada; se um
   > dia for liberada, continua sendo apagar uma checagem.
2. **Se a revogação deve reabrir o pacote ou exigir reabertura explícita.** Esta feature
   propõe reabrir junto, por não criar beco sem saída; a alternativa é uma rota de
   reabertura própria, que é mais cerimônia para o mesmo efeito.

## Risks

- **Desfazer barato demais convida a decidir sem olhar.** O ato precisa continuar custando
  uma justificativa escrita: é ela que preserva a seriedade da confirmação.
- **Índice compensado só de um lado.** Se a remoção da observação falhar e a revogação
  passar, o precedente ensina o que foi desfeito. Por isso a mesma transação, e não um
  efeito posterior.
- **Reabrir pacote em silêncio.** Quem revoga pode não perceber que o elemento voltou a
  "incompleto" e que o boletim vai recusar. A resposta e a tela precisam dizer.

## Human Gates

1. ~~**ADR da semântica da revogação**~~ — [ADR-0061](../../adr/0061-revogacao-de-codigo-confirmado.md)
   **aceito em 2026-08-28** (Daniel Campos), com as sete decisões.
2. ~~**Design Approval Package**~~ — revisão 1 **aprovada em 2026-08-28** (Daniel Campos).
3. ~~**Unknown 1** (revogar depois da aprovação do orçamento)~~ — **fechado em 2026-09-05**
   (Daniel Campos): a recusa da D7 vira **definitiva**. Quem aprovou desaprova primeiro ou
   refaz a rodada; liberar no futuro segue sendo apagar uma checagem.

## References

- `packages/valuation/src/croquito_valuation/assignment.py:1100-1210` — `CodeAssignmentSet`,
  `closed_item_ids` e `confirmed_codes_by_item`, que a revogação precisa atravessar.
- `packages/valuation/src/croquito_valuation/assignment.py:1301-1400` —
  `_ensure_batch_decidable`, onde mora `ASSIGNMENT_ITEM_ALREADY_DECIDED`.
- `services/api/src/croquito_api/main.py:14255-14371` — as rotas de decisão e fechamento das
  quais a revogação será irmã.
- `services/api/src/croquito_api/precedents.py:395-425` — `record_closure_precedents`, o
  efeito que precisa de compensação.
