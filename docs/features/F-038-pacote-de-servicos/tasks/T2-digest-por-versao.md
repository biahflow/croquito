# F-038 T2 — O digest de aprovação é governado pela versão declarada

Issue: [#74](https://github.com/biahflow/croquito/issues/74) · Estado: **entregue**
(`b4b5af5`)

## Goal

Impedir que o primeiro campo novo em `CalcBlock` invalide orçamentos e medições já
assinados. É pré-requisito de toda tarefa que acrescente campo — por isso vem antes de T3.

## Leia antes de editar

- [ADR-0048](../../../adr/0048-consolidado-contratual-do-orcamento-assinado.md) — o que faz
  do digest do orçamento assinado um contrato, e não só um teste.
- `packages/valuation/src/croquito_valuation/models.py`, `Valuation.content_digest`
- `packages/valuation/src/croquito_valuation/estimate.py`, `Estimate.content_digest`

## Mapa verificado

`content_digest()` faz `json.dumps(model_dump(mode="json", exclude={"approval"}))`;
`calc_sheets` entra no payload. `export_errors()` recomputa e devolve
`APPROVAL_CONTENT_MISMATCH` quando o digest não bate.

## Scope

`versioned_content_digest(payload, schema_version, pruning)` computa o digest sobre o
payload **como a versão declarada pelo artefato o define**, podando por caminho os campos
que aquela versão não conhecia. `DigestPruning` aceita **várias** podas por versão — uma
versão nova costuma tocar mais de um nível.

Os dois mapas nascem vazios; a entrada nasce com o primeiro campo novo (T3).

## Out of scope

Os campos em si, que são de T3. Esta tarefa entrega só o mecanismo e a prova de que ele
funciona.

## Acceptance criteria

- Duas âncoras de digest com valor literal, determinísticas entre execuções.
- Goldens intocados.
- `make check` e `make test` verdes.

## Pitfalls

**`exclude_none=True` é a saída errada.** Resolveria o campo novo e de quebra derrubaria
`CalcOperand.unit=None`, mudando o digest de tudo que se queria preservar. A poda é
declarada, nunca inferida.

## Validation

```bash
uv run pytest tests/valuation/test_content_digest.py
git diff --stat tests/valuation/golden   # precisa sair vazio
```

## Report

10 testes. O mecanismo foi validado simulando o campo futuro: com `source_item_id` em
`CalcBlock` e sem poda declarada, as duas âncoras reprovam; declarando a poda, passam. O
experimento foi revertido depois.

**Desvio do spec**: o tipo de `DigestPruning` passou de um caminho por versão para uma
sequência de caminhos, porque T3 toca dois níveis (`CalcBlock` e `CalcOperand`). Sem isso,
T3 esbarraria na estrutura.
