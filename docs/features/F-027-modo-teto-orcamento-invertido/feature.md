# F-027 — Modo teto: orçamento invertido por verba declarada

## Status

`DONE`

> Implementação integrada em 2026-08-20 na branch `f-027-especificacao` (T1–T3,
> [plan.md](plan.md)), revisada e com evidência em [evidence.md](evidence.md) e
> **mergeada na `main`** em `8dd1a5a` (com a migração `0004_estimate_round_target`).
> **Deploy e aceitação confirmados por ato humano em 2026-08-25** (Daniel Campos).
> Este flip reconcilia o roadmap, que ficara em `READY_FOR_HUMAN_REVIEW` após o merge.

> Selecionada por decisão humana de 2026-08-20, na rodada pós-F-020. Os DOIS gates
> foram exercidos na mesma data: o [ADR-0040](../../adr/0040-teto-de-verba-do-orcamento-base.md)
> foi aceito e a revisão 1 do [Design Approval Package](mock/README.md) foi aprovada
> por Daniel Campos (estouro em âmbar sem botão no aviso, mantido). Realiza o bullet
> reservado do roadmap ("modo teto / orçamento invertido — 'escopo dentro de R$ X' da
> relação de demanda; porta: `EstimateTarget` reservado no glossário do contexto") e o
> ponto de partida da cadeia na visão de produto: a Relação de Praças chega com escopo
> itemizado E verba prevista por demanda.

## Classification

`INTERFACE_CHANGE` — o teto declarado e o consumo contra ele aparecem na jornada do
orçamento (montagem/BDI e planilha) e mudam o que a orçamentista percebe e decide.

## Priority

`HIGH` (da seleção) — sequenciada DEPOIS de F-028 e F-026 na rodada.

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

## Scope (fixado pelo ADR-0040 e pelo design aprovado)

1. **Teto como dado da RODADA** (`estimate_rounds`: valor `ExactDecimal > 0` + rótulo
   opcional da demanda), declarado na abertura ou editado depois, sempre com
   `base_version` + `Idempotency-Key`; zero recusa (`sem teto` é ausência, não zero).
2. **Comparação derivada na leitura** no payload da rodada: `{target, consumed,
   remaining, over}` a partir do `total_amount` (com BDI) da cabeça; limite exato não
   é estouro; nada persiste resultado de comparação.
3. **Tela conforme o mock aprovado**: campos na abertura, painel "Teto da verba" na
   etapa BDI/montagem, bloco de consumo com os três estados, aviso permanente de
   estouro em âmbar SEM botão, rodada sem teto idêntica a hoje.
4. **`Estimate` e planilha INALTERADOS** — sem campo novo, sem bump, teto nunca
   impresso (ADR-0040, decisões 1 e 5).

## Out of Scope

- Corte/sugestão automática de itens para caber no teto (decisão de escopo é humana).
- Teto por grupo/etapa; múltiplas demandas por rodada.
- Importar a Relação de Praças como documento (o teto entra declarado).
- Medição licitada (saldo contratual já cumpre esse papel lá).

## Acceptance Criteria (esboço — fecha no gate)

1. `make check`/`make test` verdes; NENHUM schema publicado muda; goldens intocados.
2. Comportamento no estouro exatamente o do ADR-0040, coberto por teste nos dois lados
   do limite (inclusive o caso truncamento-no-centavo no limite exato).
3. Rodada sem teto se comporta exatamente como hoje (retrocompatibilidade coberta).
4. e2e estende o da F-020 com teto declarado.

## Constraints

- Dinheiro trunca; comparação contra teto usa os totais truncados que o `Estimate` já
  valida — nunca recomputa por fora.
- A SPA não decide o estouro; espelha o dado do servidor.

## Dependencies

- [ADR-0040](../../adr/0040-teto-de-verba-do-orcamento-base.md) — **Accepted em
  2026-08-20**; decisões 1–6 são a especificação.
- [Design Approval Package rev. 1](mock/README.md) — **aprovado em 2026-08-20**.
- F-020 mergeada — satisfeita. F-028/F-026 não bloqueiam tecnicamente; a ordem é
  decisão da rodada.

## Unknowns

1. RESOLVIDO (ADR-0040, decisão 4): monta com aviso permanente; nunca recusa.
2. RESOLVIDO (ADR-0040, decisão 1): editável por ato humano com `base_version`.
3. RESOLVIDO (ADR-0040, decisão 5): não aparece; o teto vive na jornada e na rodada.
4. RESOLVIDO (ADR-0040, decisão 1): valor + rótulo opcional da demanda de origem.

## Risks

- **Teto virar corte silencioso de escopo** — mitigação: out-of-scope explícito; o ADR
  fixa que teto nunca remove linha.
- **Comparação recomputada divergir do total truncado** — mitigação: comparação usa o
  `total_amount` validado, coberta no limite exato.

## Human Gates

1. Seleção (2026-08-20) — exercida.
2. Aceite do [ADR-0040](../../adr/0040-teto-de-verba-do-orcamento-base.md) —
   exercido em 2026-08-20.
3. Design Approval Package aprovado — revisão 1, exercido em 2026-08-20:
   [mock/](mock/README.md).
4. Merge e deploy.

## References

- [F-020 — jornada web do orçamento-base](../F-020-orcamento-base-web/feature.md)
- [ADR-0038 — BDI como conceito de pré-licitação](../../adr/0038-bdi-como-conceito-de-pre-licitacao.md)
- [Roadmap canônico](../../product/ROADMAP.md) — "Próximo — medição além do v1", modo teto
