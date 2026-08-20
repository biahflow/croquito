# F-027 — Modo teto: orçamento invertido por verba declarada

## Status

`READY_FOR_SPEC`

> Selecionada por decisão humana de 2026-08-20, na rodada pós-F-020. Realiza o bullet
> reservado do roadmap ("modo teto / orçamento invertido — 'escopo dentro de R$ X' da
> relação de demanda; porta: `EstimateTarget` reservado no glossário do contexto") e o
> ponto de partida da cadeia na visão de produto: a Relação de Praças chega com escopo
> itemizado E verba prevista por demanda. Este contrato **não** está
> `READY_FOR_PLANNING`: faltam os DOIS gates — o ADR da semântica do teto e o Design
> Approval Package. Por decisão do plano da rodada, esta feature é especificada em
> detalhe por último, com o aprendizado de F-025/F-026.

## Classification

`INTERFACE_CHANGE` — o teto declarado e o consumo contra ele aparecem na jornada do
orçamento (montagem/BDI e planilha) e mudam o que a orçamentista percebe e decide.

## Priority

`HIGH` (da seleção) — sequenciada DEPOIS de F-025 e F-026 na rodada.

## Problem

A Relação de Praças traz a verba prevista por demanda, e o orçamento-base da F-020 a
ignora: a orçamentista monta o orçamento às cegas do teto e só descobre o estouro
somando de cabeça. O modelo tem a porta reservada (`EstimateTarget`) e nenhum
mecanismo.

## Desired Outcome

A orçamentista declara o teto da demanda ao abrir (ou editar) a rodada de orçamento; a
montagem mostra o consumo contra o teto (com BDI incluído, que é o total submissível);
o comportamento no estouro é o que o ADR fixar — nunca corte automático de linha, que é
decisão de escopo humana.

## Scope (esboço — fecha no gate)

1. **`EstimateTarget` como conceito de domínio**: teto declarado (`ExactDecimal`),
   comparação sempre contra `total_amount` (com BDI), resultado da comparação como dado
   do `Estimate` — semântica exata (aviso vs. recusa de montagem, teto ausente =
   comportamento atual) é a matéria do ADR-0040.
2. **Rota/persistência**: teto como dado da rodada (`estimate_rounds`), mutação com as
   guardas de sempre.
3. **Tela**: declaração do teto e leitura do consumo na etapa de BDI/montagem + na
   planilha (se e como o teto é impresso é decisão do pacote de design — a planilha é
   documento que a prefeitura valida, imprimir o teto pode não ser desejável).
4. **Contrato gerado**: campos novos no `Estimate` ⇒ bump de `ESTIMATE_SCHEMA_VERSION`
   antes de publicar (disciplina do ADR-0038, decisão 6).

## Out of Scope

- Corte/sugestão automática de itens para caber no teto (decisão de escopo é humana).
- Teto por grupo/etapa; múltiplas demandas por rodada.
- Importar a Relação de Praças como documento (o teto entra declarado).
- Medição licitada (saldo contratual já cumpre esse papel lá).

## Acceptance Criteria (esboço — fecha no gate)

1. `make check`/`make test` verdes; schema com bump antes da publicação; goldens só
   mudam onde o plano declarar.
2. Comportamento no estouro exatamente o do ADR-0040, coberto por teste nos dois lados
   do limite (inclusive o caso truncamento-no-centavo no limite exato).
3. Rodada sem teto se comporta exatamente como hoje (retrocompatibilidade coberta).
4. e2e estende o da F-020 com teto declarado.

## Constraints

- Dinheiro trunca; comparação contra teto usa os totais truncados que o `Estimate` já
  valida — nunca recomputa por fora.
- A SPA não decide o estouro; espelha o dado do servidor.

## Dependencies

- **ADR-0040 (a escrever): semântica do teto** — aviso vs. recusa, teto editável depois
  de montado ou não, impressão na planilha. Gate humano.
- **Design Approval Package** (a produzir) — gate humano.
- F-020 mergeada — satisfeita. F-025/F-026 não bloqueiam tecnicamente; a ordem é
  decisão da rodada.

## Unknowns

1. Estouro recusa a montagem ou monta com aviso declarado? (ADR-0040.)
2. O teto é imutável após a primeira montagem? (ADR-0040.)
3. O teto aparece na planilha impressa? (Design + ADR.)
4. `EstimateTarget` guarda só o valor ou também a origem da verba (rótulo da demanda)?

## Risks

- **Teto virar corte silencioso de escopo** — mitigação: out-of-scope explícito; o ADR
  fixa que teto nunca remove linha.
- **Comparação recomputada divergir do total truncado** — mitigação: comparação usa o
  `total_amount` validado, coberta no limite exato.

## Human Gates

1. Seleção (2026-08-20) — exercida.
2. Aceite do ADR-0040 (a escrever quando esta feature entrar em especificação fina).
3. Design Approval Package aprovado.
4. Merge e deploy.

## References

- [F-020 — jornada web do orçamento-base](../F-020-orcamento-base-web/feature.md)
- [ADR-0038 — BDI como conceito de pré-licitação](../../adr/0038-bdi-como-conceito-de-pre-licitacao.md)
- [Roadmap canônico](../../product/ROADMAP.md) — "Próximo — medição além do v1", modo teto
