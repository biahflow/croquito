# ADR-0047: Catálogo de referência é dado da plataforma, sem dono e endereçado por digest

Status: Accepted  
Data: 2026-08-22 (aceito por ato humano na mesma data)  
Responsável: Product / Engineering

## Contexto

A cascata de fontes de preço do orçamento é alimentada hoje por **upload de um JSON por
rodada**: a orçamentista sobe o arquivo do catálogo, `POST /v1/estimate-rounds/{id}/catalogs`
o lê, valida e grava a entrada em `catalog_cascade_json` daquela rodada. O arquivo vive no
object store sob o prefixo do tenant.

Isso foi atalho de fase de teste, não o produto. Duas consequências, ditas pelo dono do
produto em 2026-08-22:

- **A pessoa errada faz o trabalho errado.** A orçamentista não tem por que saber o que é
  um JSON de catálogo, nem de onde baixá-lo. O software de orçamento consolidado no mercado
  já traz as tabelas de referência prontas e pede que o usuário **escolha**.
- **O mesmo arquivo sobe muitas vezes.** Num contrato guarda-chuva com vinte praças, são
  vinte uploads do mesmo SINAPI, cada um gerando objeto próprio sob o prefixo de um tenant.

A parte difícil já está resolvida: `read_price_catalog` (`catalog.py:418`) para o SCO,
`read_emop_catalog` (`emop.py:391`), `read_sinapi_catalog` (`sinapi.py:323`) e
`read_sicro_catalog` (`sicro.py:326`) leem os quatro formatos e normalizam para o mesmo
`PriceCatalog`, cada um com o layout declarado como dado
([ADR-0027](0027-price-source-provenance-and-bid-boundary.md) decisões 4 e 5,
[ADR-0039](0039-sinapi-sicro-como-origens-de-preco.md)). O que falta é **onde guardar
centralmente** e **como escolher**.

Cinco fatos do código delimitam a decisão:

1. **Todas as 26 tabelas do banco têm `tenant_id`.** Sem exceção, e duas
   (`SurveyRecord`, `SurveyOperationRecord`) o levam à chave primária composta. O docstring
   do módulo declara a intenção: "persistência transacional tenant-scoped". Uma tabela de
   catálogos da plataforma seria a primeira ruptura desse padrão no schema inteiro, e isso
   não pode passar como detalhe de implementação.
2. **Não existe tabela `tenants`.** `tenant_id` vive no Keycloak e como coluna nas tabelas
   de domínio (F-012). Não há entidade "dono" a que amarrar um catálogo da plataforma.
3. **O produto já trata catálogo como dado sem dono.** `CatalogCache`
   (`services/api/src/croquito_api/valuation_rounds.py:623`) compartilha catálogos
   decodificados **entre tenants**, deliberadamente: "não depende de tenant: duas rodadas
   com o mesmo catálogo compartilham a mesma decodificação de propósito, porque o conteúdo
   é idêntico byte a byte por construção". A chave é o digest, e só ele.
4. **A guarda de prefixo está em três lugares, não num.** `signed_artifact_url`
   (`valuation_rounds.py:601-620`), `_preview_urls` (`main.py:2873`) e `_export_response`
   (`main.py:2887`) recusam chave fora de `tenants/{tenant_id}/` por comparação de string.
   `ArtifactStore` (`storage.py`) **não conhece tenant**: o isolamento é convenção de quem
   monta a chave, não propriedade da classe.
5. **A rota de instalação aceita apenas `application/json`** — catálogo **já importado**
   (`_install_catalog`, `main.py:2576-2625`). Os importadores de formato bruto (`.xlsx`,
   `.dbf`) rodam **só no CLI local** (`croquito-valuation import-sinapi` e irmãos), nunca
   em request path da API ou do worker.

## Decisão

1. **Catálogo de referência é dado da PLATAFORMA, não do tenant.** Uma tabela
   `reference_catalogs` sem `tenant_id` — a primeira e, por enquanto, a única. A ausência é
   afirmativa, não esquecimento: uma tabela pública de preços **não tem dono**. Ela não é
   dado de cliente, não deriva de trabalho de cliente e não revela nada sobre nenhum tenant.
   Replicá-la por tenant seria guardar N cópias byte a byte idênticas de um documento
   público para satisfazer um invariante que existe para proteger dado privado.

   A ausência de `tenant_id` vem com uma guarda escrita: **nada em `reference_catalogs` pode
   derivar de conteúdo de cliente**. O que entra ali é arquivo publicado por operador da
   plataforma, e o teste que garante isso é parte da feature.

2. **O acervo torna persistente o que o cache já assume.** O `CatalogCache` já compartilha
   catálogo entre tenants endereçado por digest, e está certo. Esta decisão não inventa a
   ideia de catálogo sem dono — ela a move do cache em memória para o armazenamento, com as
   mesmas duas propriedades: **imutável** e **endereçado por conteúdo**.

3. **Cada publicação é um catálogo novo, amarrado por digest.** Nunca há atualização no
   lugar. É a decisão 4 do ADR-0027 aplicada ao acervo, e aqui ela vale com mais força:
   sobrescrever um catálogo central mudaria preço para **todos os tenants ao mesmo tempo**,
   inclusive em rodadas já montadas. SINAPI muda de data-base todo mês; cada data-base é uma
   entrada nova, e a anterior continua existindo porque uma rodada antiga ainda a
   referencia.

4. **Publicar é ato de `platform_operator`.** O mesmo papel e o mesmo desenho de
   administração da [F-012](../features/F-012-operacao-saas-autorizacao-ia/feature.md)
   (`_require_platform_operator`, `main.py:2628`): rotas sob `/v1/platform/`, auditadas.
   Nenhum tenant publica no acervo.

5. **Ler o acervo é livre para quem já opera o orçamento.** Qualquer sessão com o papel do
   orçamento lista e escolhe. Não há entitlement por tenant: são tabelas públicas de
   referência, e cobrar acesso a elas seria cobrar por documento público.

6. **O cliente nunca baixa o catálogo do acervo — ele escolhe.** Nenhuma rota devolve URL
   assinada de objeto do acervo. O servidor lê o objeto internamente e instala a entrada na
   cascata da rodada. Assim as **três** guardas de prefixo existentes — `signed_artifact_url`
   (`valuation_rounds.py:601`), `_preview_urls` (`main.py:2873`) e `_export_response`
   (`main.py:2887`) — **não são afrouxadas**: o objeto global fica fora de `tenants/` e fora
   de todo caminho que assina. Elas continuam recusando por prefixo, e recusar é o
   comportamento correto para uma chave do acervo.

7. **A rodada continua aceitando catálogo próprio do cliente.** `POST .../catalogs` passa a
   aceitar **ou** `upload_id` (o caminho de hoje) **ou** a referência a um catálogo do
   acervo — nunca os dois no mesmo ato. Os dois caminhos produzem a mesma `CascadeEntry`, e
   a entrada registra de qual dos dois veio: proveniência que não distingue acervo de upload
   mentiria sobre a origem do preço.

8. **EMOP fica fora do acervo.** A tabela EMOP é **paga** (informado pelo dono do produto em
   2026-08-22), e a plataforma não distribui o que não pode distribuir. Ela continua
   entrando por upload do próprio cliente, que é quem tem a licença. `composition` também
   fica fora, por natureza: composição é do cliente. O acervo nasce com `sco`, `sinapi` e
   `sicro`.

9. **O acervo recebe catálogo JÁ NORMALIZADO, não formato bruto.** A rota de instalação
   aceita apenas `application/json` (`_install_catalog`, `main.py:2576`), e os importadores
   de `.xlsx`/`.dbf` rodam **só no CLI local** — nunca em request path da API ou do worker.
   Esta decisão **não muda isso**: o operador importa o arquivo bruto pelo CLI que já
   existe (`import-sinapi`, `import-sicro`, `import-catalog`) e publica o `catalog.json`
   resultante. Trazer o parser de planilha para dentro do servidor seria superfície de
   ataque nova — leitor de formato binário sobre arquivo externo — e não é necessária para
   o valor da feature.

10. **Ingestão automática por integração fica para depois.** Nesta decisão o operador
    publica; buscar SINAPI por API a cada data-base é operação contínua e vem em fatia
    própria. O contrato de dados é o mesmo nos dois casos — o que muda é quem aperta o
    botão. Vale registrar o obstáculo concreto apurado em 2026-08-22: o portal da Caixa
    responde `429` a download automatizado mesmo com user-agent de navegador, e o do DNIT
    monta a listagem por JavaScript. Automatizar não é questão de escrever o `curl`.

11. **Auditar ato sem tenant alvo.** `_record_audit` (`main.py:2010`) sempre grava um
    `tenant_id` não-nulo, e publicar no acervo não tem tenant alvo natural. O ato é
    registrado com o `tenant_id` **do operador** que publicou — que é o fato verdadeiro
    ("esta pessoa, deste tenant, publicou") — e com o identificador do catálogo nos
    detalhes. Tornar a coluna nulável seria mudar o modelo de auditoria inteiro por um caso;
    inventar um tenant sentinela criaria um tenant que não existe.

## Alternativas

- **Acervo por tenant** (cada cliente sobe uma vez e reusa) — rejeitada: resolve o
  re-upload, não resolve o problema real, que é a orçamentista ter de conhecer e obter o
  arquivo. E guardaria N cópias idênticas de um documento público.
- **Replicar a linha do catálogo em cada tenant para preservar `tenant_id`** — rejeitada:
  satisfaz o invariante pela letra e o trai pelo espírito. O invariante existe para isolar
  dado de cliente; aplicá-lo a documento público não protege ninguém e cria N verdades sobre
  um arquivo que é um só.
- **Embutir as tabelas no repositório, como fixture** — rejeitada: catálogo real tem 2,4 MB
  e ~5.000 entradas por data-base, muda todo mês, e versioná-lo no Git faria o repositório
  crescer sem limite por dado que não é código. Fixtures sintéticas continuam no Git; dado
  real, não.
- **Devolver URL assinada do catálogo do acervo, para o cliente baixar** — rejeitada: não há
  motivo de produto (ele escolhe, não baixa) e obrigaria a afrouxar a guarda de prefixo de
  `signed_artifact_url`, que hoje é uma recusa simples e auditável.
- **Deixar o acervo sobrescrever o catálogo quando a data-base muda** — rejeitada pela
  decisão 3: mudaria preço retroativamente para todos, que é exatamente o que o ADR-0027
  proibiu ao amarrar catálogo por digest.

## Consequências

### Positivas

- A orçamentista escolhe a tabela de uma lista, em vez de obter e subir um arquivo que ela
  não tem por que conhecer.
- Uma tabela de referência passa a existir **uma vez** na plataforma, e não uma vez por
  rodada por tenant.
- O acervo dá nome, origem e data-base ao que hoje é um arquivo anônimo — meio caminho para
  a lacuna que o [ADR-0045](0045-terceiro-estado-demanda-sob-contrato.md) decisão 6 deixou
  aberta (restringir a origem não confere **qual** contrato).
- O caminho de upload continua existindo, então nenhum cliente perde a capacidade de usar a
  tabela dele — inclusive a EMOP que ele licenciou.

### Negativas

- **Primeira tabela sem `tenant_id`.** O invariante "toda tabela tem `tenant_id`" deixa de
  ser universal e passa a ser "toda tabela de dado de cliente tem `tenant_id`". A distinção
  precisa ser escrita e testada, não confiada à memória de quem vier depois.
- **Objeto fora do prefixo do tenant**, com o prefixo próprio do acervo — e uma guarda a
  mais para não vazar para o caminho que assina URL.
- **Operação contínua nova**: alguém publica a data-base nova todo mês, ou o acervo
  envelhece em silêncio.
- **Crescimento monotônico**: nunca se apaga catálogo referenciado; o acervo só cresce.

## Riscos e mitigação

| Risco | Mitigação |
| --- | --- |
| Tabela sem `tenant_id` virar precedente para dado de cliente sem isolamento | A decisão 1 nomeia a condição (nada derivado de conteúdo de cliente) e a feature entrega o teste que a verifica; qualquer tabela global futura exige ADR próprio |
| Objeto do acervo vazar para `signed_artifact_url` | O acervo vive fora de `tenants/`, e a guarda existente já recusa por prefixo; teste cobre a recusa explicitamente |
| Catálogo do acervo envelhecer e ninguém notar | A data-base é exibida na escolha e na proveniência de cada linha do orçamento — um catálogo velho aparece na tela, não só no banco |
| Publicar catálogo errado para todos os tenants | Publicação é de `platform_operator`, auditada, e imutável por digest: corrigir é publicar outro e parar de oferecer o anterior, nunca reescrever |
| Distribuir tabela sem direito de distribuição | Decisão 8: o acervo nasce só com fontes públicas; EMOP e composição ficam no caminho de upload, sob a licença de quem a tem |

## Rastreabilidade

- Requirements: VAL-09 (proveniência por linha na cascata do orçamento-base)
- Feature: [F-037](../features/F-037-acervo-de-catalogos/feature.md)
- Relacionado: [ADR-0027](0027-price-source-provenance-and-bid-boundary.md) (catálogo por
  digest, cascata como dado), [ADR-0039](0039-sinapi-sicro-como-origens-de-preco.md),
  [ADR-0045](0045-terceiro-estado-demanda-sob-contrato.md) (a lacuna de identidade do
  contrato), [ADR-0036](0036-autorizacao-de-ia-contratual-sem-allowlist-documental.md)
  (o desenho de administração por `platform_operator`)
- Supersedes: none
- Superseded by: none
