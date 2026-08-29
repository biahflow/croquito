# F-046 · T2 — O boletim da praça: união dos conjuntos e a parcela fundida

Feature: [F-046](../feature.md) · Plano: [plan.md](../plan.md) · Estado: **Pendente**

## Objetivo

Fazer o boletim da praça sair da união dos conjuntos de código das folhas, com a fusão
declarada colapsando duas leituras numa contribuição só, e o consolidado recusando fechar com
qualquer folha pendente.

## Escopo

- `packages/valuation/src/croquito_valuation/calc.py`, `calc_matrix.py`, `assignment.py`
- `packages/valuation/src/croquito_valuation/workbook_writer.py` (memória por folha)
- `tests/valuation/`

## Fora de escopo

- Persistência e rotas (T3); extração (T4); tela (T5)
- Mudar o cálculo de uma folha isolada

## Critérios de aceite

1. `Valuation.bulletins` passa a receber **um boletim por folha** da praça, e a consolidação
   por código entre boletins (`_measured_by_code`) produz o total da praça — com
   `_check_consolidated_total` verde.
2. O fechamento de pacote de serviços (F-038) passa a ser por `(plate_id, item_id, code)`, e o
   `ItemPackageClosure` fecha o pacote do **elemento da obra** (decisão 6).
3. Item fundido por declaração contribui **uma** parcela: a da leitura escolhida em "a parcela
   que fica". A leitura descartada continua gravada e visível na memória, com sua quantidade.
4. Sem declaração, item repetido entre folhas contribui **duas** parcelas, e a memória mostra
   as duas com suas folhas nomeadas.
5. Item `proposed` ou `ambiguous` em **qualquer** folha bloqueia o boletim da praça, com o erro
   nomeando quais folhas estão pendentes (`WORKSITE_TAKEOFF_PLATE_PENDING`).
6. Praça de uma folha produz boletim, memória e digests **byte a byte** iguais aos de hoje
   (teste de não-regressão sobre fixture existente).
7. A memória diz de qual folha veio cada parcela, e o total é reproduzível a partir dela.

## Validação

`uv run pytest tests/valuation tests/worker` verde; `make check` verde.
