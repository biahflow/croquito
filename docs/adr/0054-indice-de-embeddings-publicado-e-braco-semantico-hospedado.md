# ADR-0054: Índice de embeddings é artefato publicado da plataforma, e o braço semântico roda no recompute

Status: Accepted  
Data: 2026-08-25 (aceito por ato humano na mesma data)  
Responsável: Product / Engineering

## Contexto

A shortlist de código SCO servida pela API é **só lexical**. Não por escolha: o
[ADR-0021](0021-hybrid-sco-code-retrieval.md) desenhou e entregou o matcher híbrido — braço
léxico (cobertura por IDF, sinônimos, lista de ruído) + braço semântico (embeddings do
catálogo, kNN por cosseno) fundidos por RRF, com gate de `recall@20 = 100%` sobre
`tests/valuation/golden/matcher-golden-v1.json`. O motor está no caminho hospedado e é
chamado com o braço semântico **desligado**:
`services/api/src/croquito_api/valuation_rounds.py:491` passa
`SemanticArm(None, None, "unavailable", SEMANTIC_ARM_ABSENT)` e
`query_cache_path=_NO_QUERY_CACHE` (`Path(os.devnull)`).

O que falta é fora do matcher: **o índice de embeddings nunca chega ao servidor**. Ele é
construído pelo comando pago `index-catalog` (`cli.py:1396`), vive como
`catalog-embeddings.json` no disco local de quem rodou o CLI, e nenhuma rota de `/v1` o
publica — o próprio servidor declara isso em `main.py:9934`.

O custo mede a decisão, e agora está medido em vez de estimado. O ADR-0021 registrou
≈ US$ 0,007 por catálogo; a construção real do índice do catálogo da Toca em 2026-08-25
custou **US$ 0,03** — 4.964 itens, 376.068 tokens de entrada, 3 lotes, 41 s. A ordem de
grandeza da decisão não muda (centavos, **uma vez por catálogo**, idempotente por
`catalog_sha256` + `text_recipe`), mas o número honesto para catálogo SCO inteiro é
US$ 0,03, não US$ 0,007. Não é custo por rodada nem por clique. O que se perde por não ter isso é medido, não estimado: **o braço léxico
sozinho tem teto de 9/12** no golden real; o híbrido fecha 12/12. O vão é de vocabulário —
`"refletor" → "projetor"` não fecha por letra nenhuma, por mais que se ajuste o léxico.

Duas restrições do ambiente hospedado moldam a decisão, e nenhuma delas existia quando o
ADR-0021 foi escrito (ele é local-first: *"o índice é dado local, derivado do catálogo do
cliente; ele não é versionado"*, `sco_matching.py:26`):

1. **Nenhuma chamada de embedding pode acontecer dentro de um `GET`** — invariante
   declarada em `main.py:10093`. A shortlist é servida por `GET`.
2. **Toda chamada paga do produto hoje é job do worker**, com snapshot de consentimento
   amarrado ao `job_id` (`ai_processing_consents`, `database.py:277`), conforme
   [ADR-0012](0012-contractual-ai-processing-entitlements.md) e
   [ADR-0036](0036-autorizacao-de-ia-contratual-sem-allowlist-documental.md). Embutir o rótulo da legenda no
   request path da API seria **a primeira chamada paga fora de um job**.

Some-se a isso o acervo de catálogos da plataforma
([ADR-0047](0047-acervo-de-catalogos-da-plataforma.md)), que já resolveu "onde mora o
catálogo, sem dono, endereçado por digest" — a mesma pergunta que o índice faz.

## Decisão

**1. O índice de embeddings é um artefato publicado da plataforma, irmão do catálogo.**
Ele é construído pelo CLI (`index-catalog`), publicado por `platform_operator` num ato
próprio, e guardado sob `platform/reference-catalog-indexes/{object_sha256}.json`, fora de
`tenants/` — pelo mesmo motivo da decisão 1 do ADR-0047: catálogo público não tem dono, e o
índice dele tampouco.

**2. Tabela nova (`reference_catalog_embeddings`), não colunas em `reference_catalogs`.**
As linhas do acervo são imutáveis (ADR-0047 D3) e o índice é publicado num ato separado,
possivelmente meses depois; além disso um mesmo catálogo pode ter índices sucessivos quando
a receita de texto ou o modelo mudam. Colunas: `reference_catalog_id`,
`catalog_source_sha256`, `text_recipe`, `provider`, `model_id`, `dims`, `code_count`,
`object_key`, `object_sha256` (único), `status`, `published_by/at`, `withdrawn_at`.

**3. O índice é encontrado por digest, não por proveniência.** A busca é por
`catalog_source_sha256` + `text_recipe` + `AVAILABLE`. Isso faz o índice servir tanto o
catálogo escolhido do acervo quanto um upload do cliente cujos bytes sejam os mesmos — e é
exatamente a chave que `bind_index_to_catalog` (`sco_matching.py:389`) já confere fechado,
recusando índice de outro catálogo ou de outra receita.

**4. O servidor lê o índice; nunca o constrói.** A construção continua no CLI, onde um
humano aperta o botão. O servidor valida o documento por Pydantic
(`CatalogEmbeddingIndex.model_validate_json`) e mantém um cache no processo, chaveado por
`(index_object_sha256, catalog.source_sha256)`. Isto honra a **razão** da decisão 9 do
ADR-0047 (derivação pesada e paga fica fora do request path), não apenas a sua letra — que
proíbe parser de planilha, e um JSON de vetores validado por Pydantic não é um.

**5. A fusão RRF continua estritamente dentro de uma fonte.** Na cascata, o semântico roda
**por fonte** — cada catálogo com o seu índice — e os blocos são concatenados na ordem
instalada, como `suggest_codes_over_cascade` (`assignment.py:553`) já faz. Fundir entre
fontes faria similaridade de texto desempatar a **precedência da cascata**, que é decisão de
domínio e não de vizinhança vetorial.

**6. Cobertura parcial é estado normal, não erro.** Fonte sem índice contribui só com o
braço léxico, e a nota diz **qual** fonte ficou sem. A degradação continua declarada em
`semantic_notes`, agora distinguindo os casos: índice ausente para a fonte X, índice
recusado na amarração, providers desligados no ambiente, entitlement inativo, teto ou
credencial ausente, falha do provider. Nenhum deles quebra a tela.

**7. A chamada paga acontece só no recompute explícito.** O `GET` da shortlist continua sem
pagar nada — a invariante de `main.py:10093` é preservada. Embutir os rótulos da legenda
acontece em `POST .../code-suggestions/recompute`, que já é ato humano com
`Idempotency-Key`, `base_version`, auditoria e evento de rodada. Consequência que a tela
precisa dizer com todas as letras: **a primeira leitura grava a shortlist léxica; a híbrida
exige recálculo explícito.**

**8. Falta de entitlement degrada, não recusa.** `_require_active_ai_entitlement`
(`main.py:2718`) levanta `403`; usá-lo no recompute faria um tenant sem entitlement perder o
recompute inteiro, inclusive o lexical. O recompute usa um irmão que **devolve o motivo** em
vez de levantar, e a shortlist sai léxica com a nota.

## Alternativas

- **Construir o índice sob demanda no servidor, na primeira sugestão da rodada** —
  rejeitada. Poria 4.964 textos e uma chamada paga em lote dentro do request de um tenant, e
  cobraria de um tenant um artefato que é da plataforma; duas rodadas concorrentes pagariam
  duas vezes pelos mesmos vetores.
- **Guardar o índice no banco com pgvector** — rejeitada nesta fase, mantendo o que o
  ADR-0021 já havia avaliado: o kNN brute-force em numpy resolve na escala atual, e trocar o
  armazenamento não muda o contrato do matcher. O que muda aqui é **de onde vem o arquivo**,
  não como se busca.
- **Índice por rodada, subido junto com o catálogo pela orçamentista** — rejeitada: repete
  o atalho que o ADR-0047 acabou de remover (a pessoa errada fazendo o trabalho errado) e
  multiplica por rodada um custo que é por catálogo.
- **Manter só o léxico e investir em sinônimos** — rejeitada por medição, não por gosto: o
  teto do léxico no golden real é 9/12, e o caso que falta ("REFLETOR EXISTENTE" →
  `IP49150409(/)`) é de vocabulário, não de grafia.

## Decisões que exigiam aceite humano explícito

As quatro foram **aceitas por ato humano em 2026-08-25** (Daniel Campos, dono do produto):
o item 1 conforme a nota abaixo, e os itens 2, 3 e 4 como redigidos. Ficam aqui com o texto
da deliberação, porque é ele que explica o que foi aceito.

> **Item 1 decidido por ato humano em 2026-08-25** (Daniel Campos, dono do produto):
> **request path, no recompute**. A chamada paga de embeddings dos rótulos acontece dentro
> do `POST .../code-suggestions/recompute`, e não como job enfileirado. Fica registrado que
> esta é a primeira chamada paga do produto fora de um job com snapshot de consentimento
> amarrado a `job_id`, e que ela emenda o ADR-0012/0036 nesse ponto. Os itens 2, 3 e 4 foram aceitos
> em seguida, e o documento passou a `Accepted`.

1. **Chamada paga no request path da API × job enfileirado.** A decisão 7 põe uma chamada
   paga (embeddings dos rótulos, ~200 ms, ordem de centésimos de centavo) dentro de um
   `POST` da API. Hoje toda chamada paga é job do worker com consentimento amarrado a
   `job_id` (ADR-0012/0036). A alternativa é o recompute virar job enfileirado, preservando
   o snapshot — ao custo de tornar o recálculo assíncrono e mudar o contrato da tela.
   **Recomendação: request path**, pela latência e porque já existe rota com portão de
   entitlement fora de job (`main.py:10098`). Mas o precedente é do dono do produto.
2. **Escopo do teto de gasto.** `build_embeddings_adapter()` cria um `CostBudget` novo a
   cada chamada (`providers.py:3968`) — o teto é por chamada, não acumulado. Num serviço
   hospedado, recomenda-se um adapter no `application.state` para o teto do processo ser
   real.
3. **`SuggestionSemantics` plural.** Hoje guarda **um** `index_sha256` (`assignment.py:243`)
   e a cascata tem N; vira lista, com bump de `SUGGESTION_SCHEMA_VERSION` e leitura
   retrocompatível da forma singular.
4. **Catálogo de upload do cliente segue sem índice** nesta fase, coerente com a decisão 8
   do ADR-0047 (a plataforma distribui SCO/SINAPI/SICRO).

## Consequências

### Positivas

- O ganho medido do ADR-0021 passa a existir no produto hospedado: de 9/12 para 12/12 no
  golden real, no caso que é de vocabulário e não fecha por letra.
- O custo fica onde a entidade está: por catálogo da plataforma, uma vez, ≈ US$ 0,007.
- A degradação passa a dizer **qual** fonte ficou sem índice, em vez de uma frase única.
- O `GET` continua sem pagar nada, e a invariante que protege isso fica testada.

### Negativas / riscos aceitos

- **Objeto grande no processo da API**: o índice do catálogo real construído em 2026-08-25
  tem **40,7 MB** (4.964 itens × 1.536 dimensões) e `CATALOG_MAX_BYTES` é 32 MiB — o limite
  próprio não é precaução, é requisito medido: o índice real **não passa** pelo limite atual. São ~30 MB por índice por
  processo, multiplicados por workers e por entradas do cache. Ele é dado de plataforma,
  lido uma vez por processo e nunca assinado para o cliente; o primeiro recompute após um
  deploy paga a leitura fria.
- **Deploy coordenado quando a receita de texto mudar**: publicar o índice novo antes de
  subir o código que o aceita. O desfecho de errar a ordem é degradar para léxico com motivo
  declarado — `bind_index_to_catalog` recusa receita divergente —, não quebrar.
- A tela ganha um estado novo para explicar: shortlist gravada é léxica até o recálculo.

## Emenda de 2026-08-28: onde mora o cache de vetores de consulta

Este documento decidiu que a chamada paga acontece no recompute (decisão 7), mas **não
disse onde o cache de vetores de consulta passa a morar** no ambiente hospedado. O ponto
não é acessório: `resolve_query_vectors` (`sco_matching.py:718`) **escreve** no
`cache_path` por escrita atômica sempre que uma consulta nova entra, e esse é um caminho de
escrita em disco desenhado para o CLI. `_NO_QUERY_CACHE = Path(os.devnull)` era o
marcador de que a pergunta seguia aberta.

**Decidido por ato humano em 2026-08-28** (Daniel Campos, dono do produto): **cache em
memória do processo, descartado ao fim do recompute.**

O que isso significa na prática: cada recompute embute os rótulos da legenda daquela rodada
(~15 a 20 textos curtos) e descarta os vetores ao terminar. Recompute repetido repaga.

A razão é a fronteira de dado, não o custo. Um vetor de rótulo é derivado de conteúdo de
cliente; persisti-lo — seja como objeto sob `tenants/`, seja como coluna na revisão —
criaria uma classe nova de dado privado para governar, com retenção, isolamento e ciclo de
vida próprios, em troca de economizar centésimos de centavo num ato humano explícito e
raro. A assimetria decide: o índice do catálogo é dado **público** da plataforma e por isso
é publicado e cacheado; o vetor do rótulo é dado **do cliente** e por isso não sobrevive ao
request que o produziu.

Consequência aceita: o custo do recompute é proporcional ao número de rótulos, toda vez.
Se algum dia o recompute virar frequente — automático, ou em lote sobre muitas rodadas —
esta decisão precisa ser relida, porque a premissa que a sustenta ("ato humano explícito e
raro") terá deixado de valer.

## Emendas

- **[ADR-0021](0021-hybrid-sco-code-retrieval.md)** — escrito sob a premissa local-first. O
  índice deixa de ser "dado local não versionado" e passa a ser artefato de plataforma
  publicado e endereçado por conteúdo. A alternativa "Postgres/pgvector — reavaliar na
  sessão autenticada SaaS" é reavaliada aqui e **mantida rejeitada**.
- **[ADR-0047](0047-acervo-de-catalogos-da-plataforma.md)** — o acervo ganha uma segunda
  classe de objeto, com tabela e rotas próprias. Registra-se explicitamente que a decisão 9
  proíbe **parser de planilha** no servidor e que um JSON de embeddings validado por Pydantic
  não é um; a construção segue no CLI para honrar a razão da decisão.
- **[ADR-0012](0012-contractual-ai-processing-entitlements.md) /
  [ADR-0036](0036-autorizacao-de-ia-contratual-sem-allowlist-documental.md)** — conforme a resposta ao item 1
  das decisões que exigem aceite.
