# F-036 · T1 — Traduzir o orçamento assinado em consolidado contratual

feature_id: F-036  
task_id: T1  
role: builder  
plano: [plan.md](../plan.md)

## Goal

Uma função de domínio que recebe um `Estimate` **assinado** e devolve o `ContractWorkbook` que
a rodada de medição usará como contratado.

## Scope

- Módulo novo `packages/valuation/src/croquito_valuation/contract_from_estimate.py`.
- Testes em `tests/valuation/test_contract_from_estimate.py`.

## Comportamento

1. **Portão primeiro.** A função chama `estimate.ensure_exportable()` antes de qualquer outra
   coisa. Orçamento nunca assinado, assinatura rejeitada ou digest caduco recusam com o mesmo
   erro que o despacho já usa — não se inventa código novo para a mesma condição.
2. **Uma linha por código, quantidades somadas.** `Estimate.validate_lines` recusa
   `item_number` repetido, **não** `code`; o consolidado tem chave única grupo+código.
3. **Preço sem BDI**: `ContractLine.unit_price = EstimateLine.unit_price`, nunca
   `unit_price_with_bdi` (ADR-0048, decisão 2).
4. **Conflito recusa, não escolhe.** Duas linhas do mesmo código com `unit_price` ou `unit`
   diferentes levantam `ESTIMATE_CODE_PRICE_CONFLICT` com o código e os valores em conflito.
5. **Grupo único**, recebido por parâmetro (o chamador passa a referência da rodada de
   orçamento). `description` vem da primeira linha daquele código, na ordem do orçamento.
6. **Sem período lançado**: `periods=[]`, `accumulated_quantity` e `accumulated_amount` zero,
   `balance_quantity = contract_quantity = amended_quantity`.
7. **`source_sha256` é o digest assinado** (`estimate.approval.estimate_digest`), não o da
   medição. `source_label` é recebido por parâmetro e descreve a origem em texto.
8. **`contract_label` fica `None`.** O orçamento não modela contrato como entidade — é a
   lacuna 4 do ADR-0045, declarada fora de escopo. Preencher com o rótulo da rodada afirmaria
   uma identidade de contrato que ninguém conferiu.
9. **`item_number` sequencial** a partir de `"1"`, na ordem determinística dos códigos.

## Fora de escopo

- Qualquer arquivo de `services/`, `apps/` ou migração.
- A recusa de BDI sob o regime — é T2, onde o `pricing_regime` existe.
- Persistir o consolidado, e a segunda medição em diante (ADR-0048 decisão 8). A função
  **não** ganha parâmetro para períodos já lançados: parâmetro que nenhum chamador usa é
  generalidade especulativa, e a decisão 8 vira trabalho quando houver a segunda medição.

## Critérios de aceite

1. `uv run pytest tests/valuation/` e `make check` verdes; goldens intocados.
2. Orçamento com o mesmo código em dois itens produz **uma** linha, com a soma das
   quantidades — teste com o caso do serviço em dois trechos.
3. Preço divergente entre linhas do mesmo código recusa com `ESTIMATE_CODE_PRICE_CONFLICT`, e
   unidade divergente idem — dois testes.
4. O consolidado gerado usa `unit_price` e **não** `unit_price_with_bdi` — teste com BDI > 0
   que falharia se a implementação trocasse os campos.
5. Orçamento sem assinatura, com assinatura rejeitada e com digest caduco recusam pelos três
   caminhos — três testes.
6. `source_sha256` é o digest assinado; `contract_label` é `None`; saldo igual ao contratado.
7. O `ContractWorkbook` produzido **valida** (os `model_validator` dele passam), o que é a
   prova real de que a tradução respeita as invariantes do consolidado.

## Verificação

```bash
uv run pytest tests/valuation/test_contract_from_estimate.py -q
uv run pytest tests/valuation/ -q
make check
```
