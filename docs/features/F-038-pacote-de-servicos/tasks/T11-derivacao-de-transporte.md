# F-038 T11 — A tabela de derivação de transporte vira dado

Issue: [#83](https://github.com/biahflow/croquito/issues/83) · Estado: **entregue**
(`011e4bb`)

## Goal

O capítulo de transporte, carga e bota-fora é função do resto do orçamento, e hoje é
redigitado a cada praça. Transformá-lo em seed versionado e curável.

## Mapa verificado

O item `23.3` não tem memória própria: é uma tabela onde cada linha é
`=IFERROR(VLOOKUP(<item>; B:Q; 16; FALSO); 0)` multiplicado por fatores. Os blocos `23.6`,
`23.7` e `23.8` seguem a mesma forma com outros destinos.

## Scope

Seed em `packages/valuation/src/croquito_valuation/data/sco-haulage-v1.json`, no molde de
`sco-synonyms-v1.json`; modelo, loader e cálculo em `haulage.py`; extrator com proveniência
em `scripts/extract_haulage_table.py`.

## Out of scope

Percorrer o orçamento montado gerando as linhas sozinhas: depende da matriz (T4).

## Acceptance criteria

Sete casos reais reproduzidos ao centavo: 365,86 · 754,02 · 251,34 · 20,58 · 10,98 · 10,97 ·
29,91.

## Pitfalls

**Não existe uma fórmula, existem cinco.** A forma muda com o destino. Ler por posição
produziria número errado em silêncio; os fatores são lidos do cabeçalho que a memória
declara.

**A chave é o código, nunca o número do item**: 330 dos 433 itens têm código diferente
entre duas abas para o mesmo número.

**O cabeçalho `VOLUME x EMP = TOTAL`** põe a coluna do total dentro da faixa dos fatores;
sem filtrar, o total multiplicaria a si mesmo.

## Validation

```bash
uv run pytest tests/valuation/test_haulage.py
uv run python scripts/extract_haulage_table.py --input "<planilha>.xlsx" \
  --source-label "..." --output /tmp/seed.json   # byte-idêntico ao versionado
```

## Report

111 derivações; 6 materiais sem código no contrato desta obra saem declarados em
`unmapped_labels`. 19 testes. A distância virou fator nomeado com `overrides` por obra, em
vez de padrão global — responde à pergunta aberta sem travar a entrega.
