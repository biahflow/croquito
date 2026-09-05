# F-041 — O braço semântico roda no caminho hospedado

## Status

`DONE`

> **Aceita por ato humano em 2026-09-05** (Daniel Campos, pelo chat). A auditoria do fecho
> descobriu que a feature já estava **implementada e integrada desde 2026-08-26**
> ([PR #114](https://github.com/biahflow/croquito/pull/114)) — rotas de plataforma, migração
> `0020`, teto próprio de 64 MiB, braço por fonte, degradação declarada, telas testadas e a
> VAL-12 da rastreabilidade corrigida — enquanto este contrato, escrito dois dias depois,
> permaneceu dizendo `READY_FOR_PLANNING`. A evidência de navegador saiu em 2026-09-05
> (publicação de tabela e índice pela tela, recálculo degradando com o motivo por extenso) e
> a revisão focada terminou `REVIEW_PASS`. Registro completo em [evidence.md](evidence.md).
>
> Dívidas declaradas: **publicar o índice real** (40,7 MB, no disco do operador) e o
> **recompute pago real** — os atos de operador que este contrato já listava.

> Nasce em 2026-08-28, de uma pergunta do dono do produto olhando a aba "Códigos" do
> orçamento: *"aqui você tinha ativado o braço semântico com embeddings, onde foram parar
> essas mudanças?"*. A resposta é que elas nunca existiram como código de plataforma. O
> matcher híbrido foi entregue pela [ADR-0021](../../adr/0021-hybrid-sco-code-retrieval.md)
> e é chamado com o braço desligado; o que faltava — publicar o índice — foi decidido pela
> [ADR-0054](../../adr/0054-indice-de-embeddings-publicado-e-braco-semantico-hospedado.md),
> **aceita em 2026-08-25**, e nunca implementado.
>
> O gate humano do desenho, portanto, **já está cumprido**: as quatro decisões que exigiam
> aceite explícito (chamada paga no request path, escopo do teto de gasto,
> `SuggestionSemantics` plural, catálogo de cliente sem índice) foram exercidas por ato
> humano na mesma data, e estão registradas no ADR. Este contrato não reabre nenhuma delas.

## Classification

`INTERFACE_CHANGE` — muda o que a tela afirma. Hoje a aba "Códigos" declara "Nenhum
provider é chamado: a shortlist é calculada só pelo braço lexical". Depois desta feature
essa frase fica falsa, e a tela precisa dizer a verdade nova: a primeira leitura grava a
shortlist léxica, e a híbrida exige recálculo explícito e pago. Cria também superfície de
administração na jornada de Plataforma, irmã da que a
[F-037](../F-037-acervo-de-catalogos/feature.md) criou para o acervo.

## Priority

`HIGH` — o vão é medido, não estimado: o braço léxico sozinho tem teto de **9/12** no
golden real; o híbrido fecha **12/12**. O caso que falta é de vocabulário
(`"REFLETOR EXISTENTE"` → `IP49150409(/)`), e vocabulário não fecha por letra, por mais
que se ajuste sinônimo ou grafia.

## Problem

O motor híbrido inteiro está no caminho hospedado e é chamado com o braço semântico
desligado. `services/api/src/croquito_api/valuation_rounds.py:518` passa
`SemanticArm(None, None, "unavailable", SEMANTIC_ARM_ABSENT)` e
`query_cache_path=_NO_QUERY_CACHE` (`Path(os.devnull)`); o espelho da cascata faz o mesmo
em `estimate_rounds.py:1102`.

Não é escolha de produto nem degradação por falha. O motivo está escrito no próprio código
(`valuation_rounds.py:442-449`): **o índice de embeddings nunca chega ao servidor.** Ele é
construído pelo comando pago `index-catalog` do CLI, vive como `catalog-embeddings.json` no
disco de quem rodou o comando, e nenhuma rota de `/v1` o publica.

Três consequências:

1. **A orçamentista recebe a shortlist pior, e não sabe que existe uma melhor.** A nota diz
   que o braço está indisponível, mas não que ele existe, funciona e está medido.
2. **O ganho pago em 2026-08-25 está no disco de uma pessoa.** A construção do índice do
   catálogo real custou US$ 0,03 e produziu 40,7 MB que nenhum outro processo alcança.
3. **A rastreabilidade afirma o que não existe.** `docs/engineering/TRACEABILITY.md:78`
   (VAL-12) cita como evidência dois arquivos de teste e uma função que nunca foram
   escritos — a linha foi redigida no ato de aceite do ADR, descrevendo a fatia planejada
   como se estivesse feita.

## Desired Outcome

O índice de embeddings passa a ser artefato publicado da plataforma, irmão do catálogo, e a
shortlist híbrida passa a existir no produto hospedado — sem que o `GET` pague nada, sem
que falta de entitlement derrube o recálculo, e com a cobertura parcial declarada por fonte
em vez de uma frase única.

## Scope

1. **Tabela `reference_catalog_embeddings` e migração `0020_*`**, espelhando
   `ReferenceCatalogRecord` (`database.py:220-271`) — inclusive a **ausência de
   `tenant_id`**, que ali é decisão escrita do ADR-0047 e vale igual aqui: índice de
   catálogo público não tem dono. Colunas conforme ADR-0054 D2. Forward-only, nenhuma linha
   migrada.
2. **Rotas de plataforma** sob `platform_operator`, espelhando as do acervo
   (`main.py:6036` presign, `:6109` publicar, `:6250` listar, `:6280` retirar), com prefixo
   `platform/reference-catalog-indexes/{object_sha256}.json`, fora de `tenants/`.
3. **Leitura no servidor, nunca construção** (ADR-0054 D4). Validação por
   `CatalogEmbeddingIndex.model_validate_json` e cache no processo chaveado por
   `(index_object_sha256, catalog.source_sha256)`. A amarração reusa
   `bind_index_to_catalog` (`sco_matching.py:379`), que já recusa fechado índice de outro
   catálogo ou de outra receita.
4. **Teto de bytes próprio** (`CATALOG_INDEX_MAX_BYTES`, 64 MiB). `CATALOG_MAX_BYTES` é 32
   MiB (`valuation_rounds.py:125`) e o índice real tem 40,7 MB: o artefato de verdade **não
   passa** pelo limite atual. Constante nova, não afrouxamento da existente.
5. **Braço semântico por fonte na cascata** (ADR-0054 D5): roda dentro de cada fonte, e os
   blocos seguem concatenados na ordem instalada por `suggest_codes_over_cascade`
   (`assignment.py:553`). Sem fusão RRF entre fontes.
6. **`SuggestionSemantics` plural** (aceite humano item 3): `index_sha256` singular
   (`assignment.py:268`) vira lista, com bump de `SUGGESTION_SCHEMA_VERSION` e leitura
   retrocompatível da forma singular.
7. **A chamada paga só no recompute** (ADR-0054 D7): o `GET` da shortlist continua sem
   pagar nada — invariante de `main.py:10093`, que ganha teste. A chamada entra em
   `POST .../code-suggestions/recompute` (`main.py:10810` e `:13026`).
8. **Entitlement degrada, não recusa** (ADR-0054 D8): irmão de
   `_require_active_ai_entitlement` (`main.py:2987`) que devolve o motivo em vez de levantar
   `403`. Mesma regra para fonte sem índice (D6).
9. **Adapter de embeddings no `application.state`** (aceite humano item 2), para o
   `CostBudget` ser do processo e não por chamada (`providers.py:3968`).
10. **Tela**: a frase nova sobre shortlist léxica até o recálculo, e `semantic_notes` por
    fonte.
11. **Rastreabilidade corrigida**: os dois testes e a função que `TRACEABILITY.md:78` já
    promete passam a existir — ou a linha é corrigida para o que ficou de fora.

## Out of Scope

- **Construir o índice no servidor.** A construção continua no CLI, onde um humano aperta o
  botão (ADR-0054 D4). Recusado explicitamente pelo ADR como alternativa.
- **Índice para catálogo de upload do cliente** (aceite humano item 4): a plataforma
  distribui SCO/SINAPI/SICRO, e nesta fase só elas têm índice.
- **pgvector / trocar o armazenamento do kNN.** Reavaliado pelo ADR-0054 e mantido
  rejeitado: o brute-force em numpy resolve na escala atual.
- **Refino pago da shortlist por LLM.** Já existe, é outro caminho
  (`require_unrefined_suggestions`), e continua sendo comando do CLI.

## Acceptance Criteria

1. Publicar um índice pela rota nova e ver a shortlist de uma rodada sair híbrida após
   recompute explícito, com `semantic_notes` declarando que o braço rodou.
2. Fonte sem índice contribui só com o braço léxico, e a nota diz **qual** fonte ficou sem
   — não uma frase única.
3. O `GET` da shortlist não faz chamada paga nenhuma, provado por teste.
4. Tenant sem entitlement recebe a shortlist **léxica com o motivo**, nunca um `403` que
   derrube o recompute inteiro.
5. Shortlist gravada na forma singular de `SuggestionSemantics` continua legível após o
   bump de `SUGGESTION_SCHEMA_VERSION`.
6. Índice de 40,7 MB é lido sem esbarrar em teto — e um índice maior que o teto novo é
   recusado por extenso, não truncado.
7. Republicar o mesmo digest é recusado; retirar carimba `withdrawn_at` sem apagar.
8. Nenhuma coluna da tabela nova deriva de conteúdo de cliente, com teste guardando a
   condição, como em `tests/api/test_reference_catalogs.py`.

## Constraints

- Nenhuma chamada de embedding dentro de um `GET` (`main.py:10093`).
- Toda chamada paga anterior a esta é job do worker com consentimento amarrado a `job_id`
  (ADR-0012/0036). Esta é a **primeira fora de um job**, e o ADR-0054 registra que emenda
  aqueles dois nesse ponto.
- O índice é dado de plataforma: lido uma vez por processo, nunca assinado para o cliente.
- Deploy coordenado quando a receita de texto mudar: publicar o índice novo **antes** de
  subir o código que o aceita. Errar a ordem degrada para léxico com motivo declarado —
  `bind_index_to_catalog` recusa receita divergente —, não quebra.

## Dependencies

- [ADR-0054](../../adr/0054-indice-de-embeddings-publicado-e-braco-semantico-hospedado.md)
  — `Accepted`, com os quatro aceites humanos exercidos.
- [ADR-0021](../../adr/0021-hybrid-sco-code-retrieval.md) — o matcher híbrido, emendado pelo
  0054 no ponto em que era local-first.
- [ADR-0047](../../adr/0047-acervo-de-catalogos-da-plataforma.md) e a
  [F-037](../F-037-acervo-de-catalogos/feature.md) — o acervo, cuja forma esta feature
  espelha.

## Unknowns

1. ~~Onde mora o cache de vetores de consulta.~~ **Decidido por ato humano em 2026-08-28**
   (Daniel Campos): **memória do processo, descartado ao fim do recompute**. Cada recompute
   embute os rótulos daquela rodada e joga o cache fora. O custo é de centésimos de centavo
   por recompute — que é ato humano explícito e raro —, e em troca **nenhum vetor derivado
   de texto de cliente é persistido**: a feature não cria fronteira de dado nova para
   governar. As alternativas (objeto sob `tenants/` ou coluna na revisão) evitariam repagar,
   ao custo de persistir dado derivado de conteúdo de cliente com retenção e isolamento
   próprios. Emenda registrada no ADR-0054, que havia deixado o ponto em aberto.
2. **Quantos índices por processo o cache deve guardar.** São ~40 MB cada, multiplicados por
   workers. `CatalogCache` guarda 4 entradas; para índice esse número pode ser caro demais.
   Decidir na execução, com o número justificado no código.

## Risks

- **Objeto grande no processo da API**: ~40 MB por índice, por processo, por entrada de
  cache. O primeiro recompute após um deploy paga a leitura fria. Risco aceito e registrado
  no ADR-0054.
- **Primeira chamada paga fora de job**: o precedente foi aceito por ato humano, mas
  continua sendo precedente. A telemetria (tokens, custo, model id) precisa sair no evento
  de rodada e no log, como `compute_round_suggestions` já promete no docstring.
- **Sessão de banco aberta durante a chamada de embeddings (~200 ms)** no recompute. O
  `services/api/AGENTS.md:23` pede não manter transação durante chamada externa longa; esta
  não é AWS nem é longa, e o ADR-0054 D7 aceitou explicitamente a chamada no request path,
  mas a tensão fica registrada. Separar o ato em duas transações exigiria repensar a
  atomicidade do recompute — e o gatilho para fazê-lo é o recompute deixar de ser raro.
- **Cache de índices com 2 entradas × cascata de 3 fontes indexadas**: haveria expulsão a
  cada recompute, relendo ~40 MB. Não acontece hoje (a cascata típica tem uma ou duas
  fontes de plataforma), e o número está justificado pela memória por processo. O gatilho
  para reler é uma cascata de três fontes com índice publicado.
- **Eval do ganho não roda neste working tree**:
  `tests/valuation/test_matcher_golden.py:406` está sob `skipif` porque
  `output/valuation-toca/import/` e os artefatos pagos não existem aqui. O gate de 12/12
  só volta a ser exercível com os arquivos reais restaurados localmente.

## Human Gates

1. **Design Approval Package** — `INTERFACE_CHANGE`: a frase nova da aba "Códigos" e a tela
   de administração do índice na jornada de Plataforma. Precede o planejamento.
2. ~~Decisão do unknown 1~~ — **cumprido em 2026-08-28**: cache em memória do processo.
3. **Design Approval das duas superfícies** — **aprovado em 2026-08-28**: a frase nova da
   aba "Códigos" e a administração do índice na jornada de Plataforma.
4. **Construir e publicar o índice real** — chamada paga (≈ US$ 0,03 por catálogo) e ato de
   `platform_operator`. O harness prepara o comando; apertar o botão é do dono.
5. **Aceite do ganho** — recompute real em homologação confirmando 12/12.

## References

- `services/worker/src/croquito_worker/valuation/sco_matching.py` — `CatalogEmbeddingIndex`
  (`:212`), `read_catalog_index` (`:369`), `bind_index_to_catalog` (`:379`),
  `resolve_query_vectors` (`:718`).
- `services/worker/src/croquito_worker/valuation/local_server.py:699-723` — `_semantic_state`,
  a referência pronta de como montar o `SemanticArm` a partir de um índice em disco.
- `services/api/src/croquito_api/valuation_rounds.py:442-518` — o braço desligado e o motivo
  escrito.
- `tests/valuation/golden/matcher-golden-v1.json` — o oráculo do 9/12 × 12/12.
