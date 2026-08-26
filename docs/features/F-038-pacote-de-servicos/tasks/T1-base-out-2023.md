# F-038 T1 — A base de preço é a da planilha, não a nossa

Issue: [#73](https://github.com/biahflow/croquito/issues/73) · Estado: **entregue**
(`9c4a0c7`)

## Goal

Importar a base SCO Out/2023 que a obra efetivamente aplica. Sem ela nenhum número do
arquivo pode ser reproduzido como oráculo — a base publicada do repositório é de jul/2026.

## Mapa verificado

Três níveis distintos no mesmo arquivo: `FGV06` é o SCO puro (4.965 códigos); a
`PLANILHA GERAL` traz o custo contratado (427 códigos, SCO × 0,99845); a
`PLANILHA PADRÃO ORDENADA` traz o preço com BDI (× 1,18178). O orçamento aplica o **custo
sem BDI**, e é da `PLANILHA GERAL` que a orçamentária puxa a coluna de preço.

## Scope

O catálogo de referência **não precisou de código**: a aba `FGV06` bate com o template já
versionado em `output/sco-rio-2026-07/template-sco-rio-fgv06.json`. O catálogo contratado
exigiu costura, em `scripts/import_contract_catalog.py`.

## Acceptance criteria

- 4.964 entradas com `reference_month: "2023-10"`.
- 427 códigos contratados, com preço conferido contra a planilha.
- Acentuação preservada.

## Pitfalls

**Preço da `PLANILHA GERAL`, texto da `FGV06`.** 376 das 427 descrições da `PLANILHA GERAL`
estão sem acento, e os dois braços do matcher tratam acento de forma oposta:
`_lexical_normalize` remove, `normalize_query_text` **preserva de propósito**. Importar o
texto achatado degradaria o retrieval sem que nada acusasse.

**`source_sha256` é o digest do conteúdo, não do arquivo.** Os dois catálogos saem da mesma
planilha; repetir o digest os tornaria indistinguíveis na cascata.

## Validation

```bash
uv run croquito-valuation import-catalog --input "<planilha>.xlsx" \
  --template output/sco-rio-2026-07/template-sco-rio-fgv06.json --reference-month 2023-10 \
  --output output/toca-2023-10
uv run python scripts/import_contract_catalog.py --input "<planilha>.xlsx" \
  --catalog output/toca-2023-10/catalog.json --reference-month 2023-10 \
  --output output/toca-2023-10/contract-catalog.json
```

## Report

**Correção do aceite**: são 4.964 entradas, não 4.965. `IP06100100(/)` está "sem cotação" e
o template já declara esse marcador — o descarte está correto; a contagem original é que
incluía o item sem preço.

Oito preços conferidos ao centavo. O BDI real do contrato é **18,178%**, e o rodapé do
arquivo divide por 1,18 um total que já é sem BDI — furo de cálculo confirmado pela
orçamentista, a não replicar.
