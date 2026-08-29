# F-046 · T2b — O centavo da praça: a GERAL governa a deriva

Feature: [F-046](../feature.md) · Plano: [plan.md](../plan.md) · Estado: **Pendente**

## Objetivo

Fazer a deriva de truncamento entre folhas deixar de recusar a pasta e passar a ser declarada,
com o valor da PLANILHA GERAL governando — [ADR-0062](../../../adr/0062-a-deriva-de-centavo-entre-folhas-da-praca.md),
aceito por ato humano em 2026-08-29.

## Por que existe

A T2 fez a praça produzir **um boletim por folha**. O mesmo serviço na planta geral e no
detalhe passa a ser o caso normal, e com ele `TRUNC(Σq×preço) ≠ Σ TRUNC(q_i×preço)`.
`_check_consolidated_total` (`packages/valuation/src/croquito_valuation/workbook_writer.py:677`)
recusava a pasta inteira com `TRUNC_CONSOLIDATION_DRIFT` — correto enquanto o caso era de
exceção, parede quando vira rotina.

## Escopo

- `packages/valuation/src/croquito_valuation/workbook_writer.py`
- `tests/valuation/`

## Critérios de aceite

1. O valor consolidado do código continua sendo `TRUNC(Σ quantidade × preço)` — a decisão (c)
   do ADR-0018, agora com o caso ambíguo resolvido — e é ele que a GERAL imprime.
2. `TRUNC_CONSOLIDATION_DRIFT` deixa de ser erro fatal: a pasta é gerada e a deriva vira
   **registro declarado**, com o valor da GERAL, a soma dos boletins, a diferença e os códigos
   em que ela ocorreu.
3. O boletim de cada folha continua truncando a própria linha; nenhuma linha de folha é
   ajustada para fechar com a GERAL.
4. Onde a deriva é declarada fica **visível a quem confere** o artefato, não só no log.
5. Praça de uma folha e rodada de obra única respondem byte a byte como hoje (não há duas
   parcelas do mesmo código).
6. Teste com deriva construída de propósito: dois boletins do mesmo código cujas quantidades
   truncam diferente, provando que a pasta gera, que a GERAL traz `TRUNC(Σq×p)` e que a
   diferença aparece declarada.
7. Deriva **grande** continua sendo sinal de outro problema: o registro traz os dois valores
   para que a conferência distinga centavo de erro.

## Fora de escopo

- Mudar a regra de truncamento de dinheiro em qualquer outro lugar.
- Ajustar linha de boletim para absorver diferença (rejeitado no ADR-0062).
- Persistência, rotas e tela (T3 em diante).

## Validação

`uv run pytest tests/valuation` verde; `make check` e `make test` verdes.
