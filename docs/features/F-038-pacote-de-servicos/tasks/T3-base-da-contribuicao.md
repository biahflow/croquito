# F-038 T3 — A base da contribuição no bloco de cálculo

Issue: [#75](https://github.com/biahflow/croquito/issues/75) · Estado: **entregue**
(`d75847f`)

## Goal

Dar nome ao eixo das parcelas: hoje `CalcBlock.label` é texto livre, e na planilha real esse
rótulo **é** o item de legenda. Sem a amarração, T5 e T6 não têm onde se apoiar.

## Leia antes de editar

- [ADR-0053](../../../adr/0053-cardinalidade-n-n-elemento-servico.md), decisões 1 e 3.
- T2 (#74), que precisa estar entregue: sem a poda, o campo novo invalida assinatura.

## Mapa verificado

`CalcSheet` já é indexada pelo `item_number` da **linha**, não pelo item de takeoff — a
matriz já existe na forma; falta o eixo das parcelas ter nome. A aritmética de
`expected_subtotal` não muda.

## Scope

`ContributionBasis` (cinco valores), três campos opcionais em `CalcBlock`, validador de
coerência, bumps para 3.0.0 com `Literal` alargado, e as podas de T2 preenchidas.

## Out of scope

Teto e nota de `PARTIAL`: dependem do `TakeoffItem`, que o modelo não alcança. É conferência
de builder (T4/T6).

## Acceptance criteria

- Diff do golden do orçamento contém **só** a versão e as chaves novas como `null`.
- Digest de artefato que declara a versão antiga não se move.
- Goldens de planilha byte-idênticos.

## Pitfalls

**`basis` nasce `None`, não `FULL`.** Default afirmaria sobre blocos antigos algo que
ninguém declarou — um `PERIMETER_TIMES_HEIGHT` do M4 é `DERIVED`.

## Validation

```bash
uv run pytest tests/valuation/test_models.py tests/valuation/test_content_digest.py
make contracts && make check && make test
```

## Report

**Desvio do spec, com evidência**: o plano pedia cinco receitas novas e um enum
`CalcQuantityKind` de quinze grandezas. A memória real tem 45 formas de fórmula e 43 termos
de operando, 21 de ocorrência única. Entrou **uma** receita, `DECLARED_PRODUCT`;
`CalcQuantityKind` ficou fora.

As âncoras de T2 passaram a reconstruir o artefato **como está gravado no banco** — sem as
chaves que a matriz criou —, que é o payload que precisa continuar rendendo o mesmo digest.
