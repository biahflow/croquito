# Runbook: aceite do BM real da Toca (M5)

Status: Draft  
Responsável: Orçamentista / Engineering  
Última revisão: 2026-08-13

## Objetivo e limite

Conduzir a rodada paga autorizada que fecha o M5 do contexto de medição
([Valuation Context](../architecture/VALUATION_CONTEXT.md)): ler a legenda quantificada
da prancha real da Toca com um provider externo, revisar e confirmar o quantitativo e o
código com o orçamentista, montar o boletim da obra e compará-lo, centavo a centavo, com
o BM real que a prefeitura já publicou. O aceite é literal — **"BM da Toca gerado × real
= zero centavo"** — e só é alcançado quando `croquito-valuation compare-bulletin`
sai com `zero_cent: true` (exit 0) sobre o par gerado/real de verdade, não sobre fixture.

Este runbook **não autoriza** nenhuma chamada paga em massa nem antecipa decisão: cada
ato do orçamentista (revisão do takeoff, confirmação de código) é humano e rastreável, e
qualquer divergência que `compare-bulletin` relatar é achado a levar ao orçamentista —
nunca um ajuste silencioso do lado gerado para bater com o real.

As duas vias pagas que este runbook exercita — `extract-legend-real` (extração de
legenda) e `suggest-codes --refine-arm` (refino de código) — já existem no CLI
`croquito-valuation` e são cobertas offline pelo gate `extraction-eval`
(`make valuation-extraction-eval`); este runbook é a primeira vez que elas rodam sobre o
documento real da Toca, com o braço vencedor da comparação feita antes por
`extraction-eval --arm` ([Evaluation Strategy](../ai/EVALUATION_STRATEGY.md)).

## Pré-condições e segurança

- Autorização de gasto registrada para esta rodada, com o teto explícito por variável de
  ambiente (`CROQUITO_AI_MAX_ESTIMATED_COST_USD`) — nunca implícito.
- Prancha quantificada real e BM real do cliente ficam **fora do repositório** (nunca
  versionados). Todo artefato desta rodada nasce em `output/valuation-toca/…`, que é
  ignorado pelo Git e segue a retenção local de sete dias.
- Template real do layout do cliente (`WorkbookTemplate`) em
  `output/valuation-real/template-real.json`, fora do Git, cobrindo tanto o `catalog`/
  `general`/`amendment` já usados pela importação real (M2.1) quanto o `bulletin` novo
  que este runbook lê. Lacuna de layout real que aparecer aqui vira campo novo de
  template com default do layout atual — nunca exceção no código (filosofia M2.1).
- Catálogo de preços da Toca já importado uma vez do MAPÃO anterior real com
  `import-catalog --template output/valuation-real/template-real.json`, produzindo
  `catalog.json` em `output/valuation-toca/import/`. Esta rodada consome esse catálogo;
  não o reimporta. Não é `import-workbook` completo: o consolidado real da Toca segue
  recusado pelo portão semântico (`CONTRACT_SEMANTICS_DIVERGENT`, dossiê pendente de
  conversa humana no [ADR-0018](../adr/0018-valuation-consolidation-and-balance-semantics.md)),
  então `contract-workbook.json` não existe para esta rodada. Consequência aceita para o
  aceite do BM: `suggest-codes` e `confirm-codes` rodam **sem `--contract`** — a shortlist
  sai sem o sinal `in_contract` no ranking e `confirm-codes` não aplica o gate
  `CODE_NOT_IN_CONTRACT`. Isso não compromete `compare-bulletin`, que confere o boletim
  gerado contra o BM real por código, quantidade e preço, independente do consolidado.
- Chave de API do provider do braço vencedor fora do Git:
  `CROQUITO_ANTHROPIC_API_KEY` para `anthropic`, `CROQUITO_OPENAI_API_KEY` para
  `openai`; o braço `bedrock` usa credenciais AWS via `boto3` (perfil/região local), sem
  chave própria.
- **Certificado CA do Python gerenciado pelo `uv`**: neste macOS, o Python do `uv` não
  encontra os certificados CA do sistema, e o adapter do provider traduz essa falha em
  `TIMEOUT` — com `RetryingProviderAdapter` reservando o custo estimado de cada
  tentativa, um `TIMEOUT` imediato pode virar `BUDGET_EXCEEDED` depois de poucos
  retries, sem nenhuma chamada de verdade ter saído. Antes de qualquer comando pago
  desta rodada, exporte:

  ```bash
  export SSL_CERT_FILE="$(uv run python -c 'import certifi; print(certifi.where())')"
  ```

  Sintoma sem isso: `PROVIDER_EXECUTION_FAILED` com `code: TIMEOUT` já na primeira
  tentativa, ou `BUDGET_EXCEEDED` depois de retries que nunca chegaram a sair da
  máquina.
- **Reserva de gasto é por tentativa, não por chamada útil.** Cada braço reserva
  `CROQUITO_AI_ESTIMATED_COST_PER_LLM_CALL_USD` (default `0.75`) contra o mesmo
  `CostBudget` a cada tentativa — inclusive as que o `RetryingProviderAdapter` refaz
  depois de falha transitória. A cadeia desta rodada faz **duas** chamadas pagas sob o
  mesmo teto (`extract-legend-real`, depois `suggest-codes --refine-arm`), e com o
  default de `0.75`/tentativa um único retry em qualquer uma delas já reserva `1.50` —
  suficiente para estourar um teto pensado como "0,75 por chamada × 2 chamadas =
  1,50". Recomendação validada na primeira rodada paga real: exporte também

  ```bash
  export CROQUITO_AI_ESTIMATED_COST_PER_LLM_CALL_USD=0.35
  export CROQUITO_PROVIDER_TIMEOUT_SECONDS=120
  ```

  ao lado do teto, para que um retry isolado não consuma sozinho o orçamento da rodada
  inteira e para que o provider tenha tempo de responder antes do timeout local disparar
  outro retry.
- Nenhum item de takeoff, código ou decisão desta rodada é fabricado por agente ou
  fixture: `review-takeoff` e `confirm-codes` só aceitam decisões que o orçamentista de
  fato tomou olhando a prancha e o catálogo reais.
- Pare a rodada se a allowlist (`CROQUITO_AI_EXTRACTION_ALLOWED_DIGESTS`) não bater
  com o digest do manifest, se o teto de gasto não estiver setado, ou se qualquer
  comando pago recusar (`refused`) — recusa fechada aqui não é para contornar.

## Passos

Cada comando roda a partir da raiz do repositório, com o `.venv` do `uv sync
--all-groups` ativo. Ajuste os caminhos de `--output` conforme a convenção
`output/valuation-toca/<etapa>`.

1. `croquito-demo ingest` da prancha real → PNGs 200 DPI + manifest com digest, fora
   do Git:

   ```bash
   uv run croquito-demo ingest \
     --input <prancha-toca-real.pdf> \
     --dataset-id toca-prancha-v1 \
     --role legenda-quantificada \
     --output output/valuation-toca/ingest
   ```

2. Exportar o teto de gasto e a allowlist do documento, com o `source_sha256` que o
   `manifest.json` do passo anterior registrou (além do `SSL_CERT_FILE` e da reserva de
   gasto por tentativa das Pré-condições):

   ```bash
   export CROQUITO_AI_MAX_ESTIMATED_COST_USD=<teto autorizado>
   export CROQUITO_AI_EXTRACTION_ALLOWED_DIGESTS=<source_sha256 do manifest>
   ```

3. `extract-legend-real` — extração paga da legenda com o braço vencedor da eval
   sintética (`uv run croquito-valuation extraction-eval --output <dir> --arm
   NOME=PROVIDER:MODELO`; decisão humana sobre o relatório — a rodada de 2026-08-13
   aprovou `sonnet=anthropic:claude-sonnet-5` para as duas tarefas, ver
   [Model Routing](../ai/MODEL_ROUTING.md)):

   ```bash
   uv run croquito-valuation extract-legend-real \
     --image output/valuation-toca/ingest/<página>.png \
     --manifest output/valuation-toca/ingest/manifest.json \
     --arm <braço vencedor> \
     --plate-id toca-prancha-v1 \
     --page-number 1 \
     --output output/valuation-toca/extract
   ```

   Nenhum item nasce confirmado: o pacote sai `review_required`, com o overlay marcado.

4. **Ato humano** — revisão do takeoff pelo orçamentista. As decisões (confirmar ou
   rejeitar cada item, com quantidade e nota quando o item for ambíguo) são registradas
   pelo orçamentista de verdade, olhando a prancha real, e gravadas num
   `TakeoffDecisionBatch` (`packages/valuation/src/croquito_valuation/takeoff.py`)
   antes de rodar:

   ```bash
   uv run croquito-valuation review-takeoff \
     --packet output/valuation-toca/extract/takeoff-packet.json \
     --decisions <decisões-do-orçamentista.json> \
     --image output/valuation-toca/ingest/<página>.png \
     --output output/valuation-toca/review
   ```

   `review_status` no stdout precisa virar `complete`; item pendente aqui bloqueia o
   resto da cadeia.

5. `suggest-codes` — shortlist lexical determinística e, se a eval indicar, refinada por
   provider pago —, seguida do **ato humano** `confirm-codes`. Sem `contract-workbook.json`
   (pré-condição), os dois comandos rodam **sem `--contract`**:

   ```bash
   uv run croquito-valuation suggest-codes \
     --packet output/valuation-toca/review/takeoff-packet.json \
     --catalog output/valuation-toca/import/catalog.json \
     --output output/valuation-toca/suggest \
     [--refine-arm <braço vencedor>]   # só se a eval mostrou ganho sobre a lexical

   uv run croquito-valuation confirm-codes \
     --packet output/valuation-toca/review/takeoff-packet.json \
     --decisions <confirmações-do-orçamentista.json> \
     --catalog output/valuation-toca/import/catalog.json \
     --output output/valuation-toca/confirm
   ```

   `confirm-codes` é fail-closed e sem re-decisão: código fora do catálogo, ambíguo entre
   grupos ou unidade incompatível sem nota recusam. Sem `--contract`, a shortlist do
   `suggest-codes` sai sem o sinal `in_contract` no ranking e `confirm-codes` não aplica o
   gate `CODE_NOT_IN_CONTRACT` (código fora do contrato) — aceitável para o aceite do BM,
   porque `compare-bulletin` confere o boletim gerado contra o BM real independente do
   consolidado.

6. `build-calc` com os dados reais da obra (chave, nome, período e rótulo da medição em
   curso):

   ```bash
   uv run croquito-valuation build-calc \
     --packet output/valuation-toca/review/takeoff-packet.json \
     --assignments output/valuation-toca/confirm/code-assignments.json \
     --catalog output/valuation-toca/import/catalog.json \
     --worksite-key <chave-da-obra-toca> \
     --worksite-name "<nome-da-obra-toca>" \
     --period-number <número-da-medição> \
     --reference-label "<rótulo-da-medição>" \
     --output output/valuation-toca/calc
   ```

   Sai `valuation.json` **sem aprovação** — aprovar e exportar (`export-valuation`)
   continuam atos separados, fora do escopo deste aceite.

7. `compare-bulletin` — a comparação centavo a centavo em si, entre o `valuation.json`
   do passo anterior e a aba BM real que a prefeitura publicou:

   ```bash
   uv run croquito-valuation compare-bulletin \
     --valuation output/valuation-toca/calc/valuation.json \
     --worksite <chave-da-obra-toca> \
     --reference <BM-real-da-toca.xlsx> \
     --sheet "<nome da aba BM na planilha real>" \
     --template output/valuation-real/template-real.json \
     --output output/valuation-toca/compare
   ```

   Nada aqui escreve no `<BM-real-da-toca.xlsx>`; o relatório vai só para
   `output/valuation-toca/compare/bulletin-compare.json`.

8. **Aceite** = exit `0` com `zero_cent: true`. Qualquer divergência relatada
   (`missing_in_reference`, `missing_in_generated`, `quantity_diffs`,
   `unit_price_diffs`, `line_total_diffs`, `bulletin_total_diff`) é achado a levar ao
   orçamentista para decidir a origem — quantidade tomada errado na revisão, código
   confirmado errado, ou de fato um erro no BM publicado pela prefeitura. **Nunca** é
   corrigido ajustando o lado gerado só para o relatório fechar; `unit_notes` sozinho
   (unidade escrita diferente com os números batendo) não bloqueia o aceite.

## Rollback / limpeza

- Ao fim da sessão, `unset` de todas as variáveis exportadas nos passos 2 e nas
  pré-condições (`CROQUITO_AI_MAX_ESTIMATED_COST_USD`,
  `CROQUITO_AI_EXTRACTION_ALLOWED_DIGESTS`, `SSL_CERT_FILE`,
  `CROQUITO_AI_ESTIMATED_COST_PER_LLM_CALL_USD`,
  `CROQUITO_PROVIDER_TIMEOUT_SECONDS`) — nenhuma delas deve sobreviver à sessão nem
  ir para `.env.local` versionado.
- Nenhum artefato desta rodada (prancha, manifest, pacotes, relatório de comparação) é
  persistido fora da máquina local; tudo vive em `output/valuation-toca/` e segue a
  retenção máxima de sete dias do repositório.
- Se a rodada foi interrompida por recusa fechada (`refused`) em qualquer passo pago,
  nenhum artefato daquele passo foi publicado — confira o diretório de saída antes de
  repetir o comando, para não confundir uma tentativa anterior incompleta com a atual.

## Validação do mecanismo

Antes da sessão paga, confirme que a cadeia offline e o comparador continuam corretos
sobre fixture sintética (sem custo, sem rede):

```bash
uv run pytest tests/valuation/test_bulletin_compare.py tests/worker/test_valuation_compare_cli.py -x
uv run pytest tests/valuation tests/worker
uv run croquito-valuation demo --output output/valuation-demo
make valuation-eval
make valuation-extraction-eval
```

Os testes cobrem a leitura do BM real (linha de total, linha separadora, código
duplicado, aba/chave ausente) e a comparação (zero centavo, diff de quantidade/preço/
total de linha/total da obra, código ausente de cada lado, nota de unidade) contra
oráculo sintético — não substituem a decisão do orçamentista sobre o BM real da Toca.
`valuation-extraction-eval` exercita os gates de gasto, allowlist e permutação da
shortlist que este runbook depende, sempre no braço fixture offline por padrão.

## Pós-condições

- Nenhuma decisão do orçamentista, chamada paga ou aceite é fabricado por este runbook.
- `docs/STATUS.md` só deixa de indicar a rodada paga da Toca como pendente depois que o
  aceite (passo 8) realmente ocorrer nesta sessão, com `zero_cent: true` sobre os
  arquivos de verdade — não sobre fixture.
- O braço vencedor usado nos passos 3 e 5, o custo efetivo registrado no lineage de cada
  chamada (`_execution_payload` no stdout de `extract-legend-real`/`suggest-codes`) e o
  relatório final de `compare-bulletin` ficam registrados fora do repositório, em local
  de acesso controlado, junto com a decisão do orçamentista sobre qualquer achado.
- O caminho de código para `compare-bulletin` existe e está coberto por teste; isso não
  antecipa nenhum aceite real. O aceite só é verdadeiro depois de rodar este runbook
  contra o BM real da Toca.
