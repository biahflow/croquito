# F-038 T3 — A base da contribuição no bloco de cálculo

Issue: [#75](https://github.com/biahflow/croquito/issues/75) · Estado: **aceita**
(`d75847f`, revisada e corrigida em `e51bbf8`)

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

## Revisão (2026-08-26)

Revisão linha a linha do `d75847f`. Os três critérios de aceite passam, e um deles foi
provado por mutação: com os mapas de poda zerados em memória, as duas âncoras de digest
divergem; com eles, batem com o valor literal anterior à F-038. A âncora prova o que afirma.

O diff do golden do orçamento é exatamente a versão mais as três chaves `null` em cada um
dos cinco blocos, e os goldens de planilha não aparecem no diff — nenhuma célula se moveu.

**Dois defeitos, corrigidos em `e51bbf8`:**

- `basis` `FULL`/`DERIVED`/`PARTIAL` com `source_item_id=None` era aceito — o bloco afirmava
  origem em elemento sem nomear o elemento. Vira `CALC_CONTRIBUTION_WITHOUT_SOURCE_ITEM`.
  `DEPENDENT` fica de fora com teste que fixa o silêncio: quem decide é a T4.
- `derived_from_code` só tinha limite de tamanho e aceitava texto que não é código. Vira
  `CALC_CONTRIBUTION_CODE_INVALID`, com o mesmo superset estrutural de `ServiceHaulage`.

**Dívida registrada, não paga aqui**: `^ti_[a-f0-9]{16}$` está duplicado em `calc.py:39`,
`assignment.py:162`, `estimate.py:83` e `amendment_dossier.py:43` além do
`TAKEOFF_ITEM_ID_PATTERN` que esta tarefa criou. Unificar toca arquivos que estão na mão da
T5.

**Achado de fora do escopo**: a branch não passava no `make check` sozinha — `8729c1f`
registrou o ADR-0054 no índice enquanto o arquivo dele seguia não rastreado. Corrigido em
`557b3bd`.
