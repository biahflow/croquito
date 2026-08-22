# F-037 — Acervo central de catálogos de preço

## Status

`READY_FOR_HUMAN_REVIEW`

> Nasce em 2026-08-22, de uma conversa sobre o rumo do produto: **o sistema deve trazer as
> tabelas prontas, e o orçamentista escolher**, como faz o software de orçamento
> consolidado no mercado. O upload de JSON por rodada, que está no ar, foi atalho
> deliberado de fase de teste — o dono do produto o descreveu assim: "só pra testar, eu
> deixei; mas a ideia é o sistema já trazer pronto".
>
> Selecionada por decisão humana de 2026-08-22, com prioridade `HIGH` e **precedência sobre
> a [F-035](../F-035-aprovacao-do-orcamento/feature.md)**, porque o dono quer exercitar a
> cadeia com esta parte funcionando.
>
> Eram **dois gates humanos**, ambos precedendo o planejamento. O primeiro foi cumprido: o
> [ADR-0047](../../adr/0047-acervo-de-catalogos-da-plataforma.md) foi **aceito por ato
> humano em 2026-08-22**, fixando as onze decisões que este contrato marcava como decisão
> do ADR — inclusive a tabela sem `tenant_id`, o acervo receber catálogo já normalizado e a
> auditoria pelo tenant do operador.
>
> O segundo também: o **Design Approval Package** (`DESIGN_APPROVAL_REQUIRED`) foi
> **aprovado por ato humano em 2026-08-22**, revisão 1, registro em
> [mock/README.md](mock/README.md). Com os dois gates cumpridos, a feature está
> `READY_FOR_PLANNING`. A implementação deve corresponder à revisão aprovada; divergir dela
> é revisão nova, com registro próprio.

## Classification

`INTERFACE_CHANGE` — cria superfície nova percebida por humano em dois lugares: a escolha
de catálogo na aba Cascata, que substitui o campo de upload como caminho principal, e a
administração do acervo na jornada de Plataforma. Exige Design Approval Package aprovado
antes do planejamento, conforme
[design-approval](../../engineering-os/workflows/design-approval.md).

## Priority

`HIGH` — é o que separa a jornada de uma demonstração de um produto usável. Enquanto a
cascata exigir um JSON, ela exige que a orçamentista saiba obter e reconhecer um artefato
que não faz parte do trabalho dela.

## Problem

A cascata é alimentada por upload: a orçamentista sobe um JSON de catálogo, e
`POST /v1/estimate-rounds/{id}/catalogs` lê, valida e grava a entrada em
`catalog_cascade_json` daquela rodada. Três consequências:

1. **O trabalho está na pessoa errada.** Obter a tabela SINAPI da data-base correta,
   convertê-la para o formato que o sistema lê e subi-la não é trabalho de orçamentista — é
   trabalho de quem opera o software. Hoje o produto delega isso ao cliente.
2. **O mesmo arquivo sobe muitas vezes.** Num contrato guarda-chuva com vinte praças são
   vinte uploads do mesmo catálogo, cada um gerando um objeto próprio sob o prefixo de um
   tenant. Nada liga um ao outro, e nada impede que a praça 12 use uma data-base diferente
   da praça 3 por engano.
3. **O catálogo é anônimo.** A entrada guarda origem, data-base e digest, mas ninguém
   declarou *qual* documento é aquele. Isso encosta na lacuna que o
   [ADR-0045](../../adr/0045-terceiro-estado-demanda-sob-contrato.md) decisão 6 deixou
   aberta: restringir a origem não confere **qual** contrato.

A parte difícil já está feita e não precisa ser refeita: `read_price_catalog`
(`catalog.py:418`, SCO), `read_emop_catalog` (`emop.py:391`), `read_sinapi_catalog`
(`sinapi.py:323`) e `read_sicro_catalog` (`sicro.py:326`) leem os quatro formatos e
normalizam para o mesmo `PriceCatalog`. E o produto já trata catálogo como dado sem dono —
`CatalogCache` (`services/api/src/croquito_api/valuation_rounds.py:623`) compartilha
catálogos decodificados entre tenants de propósito, endereçados por digest.

O catálogo do SCO-Rio já foi importado localmente e está pronto para ser o primeiro do
acervo: `origin=sco`, `reference_month=2026-07`, 4.865 entradas, nas duas variantes
(desonerado e onerado).

## Desired Outcome

A orçamentista abre a aba Cascata e **escolhe** a tabela numa lista com nome, origem e
data-base — sem arquivo, sem conversão, sem saber o que é um JSON. O operador da plataforma
publica cada data-base nova uma vez, para todos. Quem tem uma tabela própria licenciada — a
EMOP, ou o catálogo de um contrato específico — continua subindo o arquivo pelo caminho que
já existe.

## Scope

### 1. Acervo como dado da plataforma

Tabela `reference_catalogs` **sem `tenant_id`** — a primeira do projeto, pela decisão 1 do
ADR-0047 — com nome de exibição, origem, data-base, digest do arquivo, digest do catálogo
normalizado, contagem de entradas e estado de disponibilidade. O objeto vive sob prefixo
próprio do acervo, **fora** de `tenants/`.

Cada publicação é entrada nova, imutável, endereçada por digest. Nunca há atualização no
lugar: SINAPI muda de data-base todo mês, e a entrada anterior permanece porque uma rodada
antiga ainda a referencia.

### 2. Administração por `platform_operator`

Rotas sob `/v1/platform/`, no desenho da
[F-012](../F-012-operacao-saas-autorizacao-ia/feature.md) (`_require_platform_operator`,
`main.py:2628`): publicar um catálogo, listar o acervo, e retirar um catálogo de circulação
— retirar **não** apaga, porque rodadas antigas o referenciam; ele deixa de ser oferecido.
Auditado como os demais atos de plataforma, com o `tenant_id` do operador que publicou
(decisão 11 do ADR-0047 — `_record_audit` não aceita tenant nulo).

O que se publica é o **`catalog.json` já normalizado**, não o `.xlsx`/`.dbf` bruto: o
operador importa pelo CLI que já existe (`import-catalog`, `import-sinapi`, `import-sicro`)
e publica o resultado. Trazer parser de planilha para o request path é superfície nova e
está fora de escopo (decisão 9 do ADR-0047).

### 3. Escolha na cascata

`POST /v1/estimate-rounds/{id}/catalogs` passa a aceitar **ou** `upload_id` (o caminho de
hoje) **ou** a referência a um catálogo do acervo — nunca os dois no mesmo ato. Os dois
produzem a mesma `CascadeEntry`, e a entrada **registra de qual dos dois veio**: uma
proveniência que não distingue acervo de upload mentiria sobre a origem do preço.

Todas as regras existentes continuam valendo sem exceção — origem duplicada recusa
(`ESTIMATE_CASCADE_ORIGIN_DUPLICATE`), regime sob contrato recusa origem proibida
(`ESTIMATE_CASCADE_ORIGIN_FORBIDDEN`), e a trava por decisão de código
(`ESTIMATE_CASCADE_LOCKED`) é a mesma.

### 4. Listagem para escolher

`GET /v1/estimate-rounds/{id}/reference-catalogs` (ou equivalente decidido no plano): o que
está disponível, com nome, origem e data-base. Sob regime de contrato, a lista já vem
filtrada pelo que o regime aceita — a tela não oferece o que a instalação vai recusar.

### 5. Tela

A aba Cascata passa a ter a escolha como caminho principal e o upload como alternativa
declarada ("tabela própria"), conforme o Design Approval Package. A jornada de Plataforma
ganha a administração do acervo.

### 7. Presign próprio da plataforma

Decisão humana de 2026-08-22, tomada na revisão da T1: publicar não pode depender da jornada
do croqui. O operador sobe o `catalog.json` por um presign sob `/v1/platform`, com o papel
exigido e o tipo fixo em `application/json`.

O `UploadRecord` continua sendo do tenant do operador, sob `tenants/{tenant_id}/uploads/` —
o arquivo só vira objeto do acervo depois de lido, conferido e gravado sob o prefixo da
plataforma. Subir direto para o prefixo do acervo colocaria nele um arquivo não validado.

**`/v1/uploads` não muda**, e `journeys.py` não é tocado: tirar o presign do croqui do
portão da F-034 resolveria um caso de plataforma enfraquecendo o mecanismo que existe para
desligar módulo imaturo.

### 6. Cobertura

Publicar, listar e escolher; catálogo do acervo instalado produzindo linha de orçamento com
a mesma proveniência do caminho de upload; retirada de circulação não quebrando rodada que
já o referencia; papel exigido antes do lookup nas rotas de plataforma; e o teste que
verifica a guarda da decisão 1 do ADR — nenhuma coluna de `reference_catalogs` deriva de
conteúdo de cliente.

## Out of Scope

- **Ingestão automática por integração** (buscar SINAPI por API a cada data-base). É
  operação contínua e vem em fatia própria; o contrato de dados é o mesmo, o que muda é
  quem aperta o botão. Declarado na decisão 9 do ADR-0047.
- **EMOP no acervo.** A tabela é **paga** (informado pelo dono do produto em 2026-08-22), e
  a plataforma não distribui o que não pode distribuir. Continua por upload do cliente, que
  é quem tem a licença. `composition` também fica fora, por ser do cliente por natureza.
- **Amarrar catálogo a um contrato real** (data-base e desconto daquele contrato). O acervo
  dá nome e data-base ao documento, o que é meio caminho; fechar a lacuna do ADR-0045
  decisão 6 exige o orçamento modelar contrato como entidade, e é feature própria.
- **Cobrança ou entitlement por acesso ao acervo.** São tabelas públicas.
- **Migrar catálogos já instalados** em rodadas existentes para o acervo. Elas continuam
  apontando para o objeto do tenant, e nada é reescrito retroativamente.
- **Qualquer mudança na cadeia de medição.**

## Acceptance Criteria

1. `make check` e `make test` verdes; snapshot OpenAPI regravado.
2. Um catálogo publicado uma vez é instalável em rodadas de **tenants diferentes**, sem
   novo upload, e as duas instalações citam o mesmo digest.
3. Publicar a mesma data-base duas vezes **não** sobrescreve: ou é recusado, ou gera entrada
   nova — nunca troca silenciosa de preço (ADR-0027 decisão 4).
4. Retirar um catálogo de circulação não quebra rodada que já o referencia, e ele deixa de
   aparecer na escolha.
5. `POST .../catalogs` com `upload_id` **e** referência do acervo no mesmo corpo recusa; e a
   `CascadeEntry` gravada declara de qual caminho veio.
6. Sob regime de contrato, a listagem só oferece o que o regime aceita, e instalar o que ele
   não aceita continua recusando com o código existente.
7. Nenhuma rota devolve URL assinada de objeto do acervo — coberto por teste, incluindo a
   recusa de `signed_artifact_url` para chave fora de `tenants/`.
8. Publicar exige `platform_operator`, verificado antes de qualquer lookup.
9. Um orçamento montado sobre catálogo do acervo é logicamente idêntico ao montado sobre o
   mesmo catálogo por upload — mesma proveniência por linha, exceto o campo que declara a
   procedência da entrada.
10. As telas correspondem à revisão aprovada do Design Approval Package.

## Constraints

- **A guarda de `signed_artifact_url` não é afrouxada.** Ela recusa chave fora de
  `tenants/{tenant_id}/`, e o acervo fica do lado de fora dela por construção — o cliente
  escolhe, o servidor lê.
- **Nada em `reference_catalogs` deriva de conteúdo de cliente.** É a condição que sustenta
  a ausência de `tenant_id`, e ela é verificada por teste, não confiada à memória.
- Catálogo é imutável e endereçado por digest, como já é na cascata e no `CatalogCache`.
- `packages/valuation` segue sem depender do worker nem do scene graph (ADR-0016), e os
  importadores não mudam.
- O caminho de upload **continua funcionando** exatamente como hoje.

## Dependencies

- **ADR-0047** — `ARCHITECTURE_DECISION_REQUIRED`, **satisfeito em 2026-08-22**
  ([ADR-0047](../../adr/0047-acervo-de-catalogos-da-plataforma.md), `Accepted`). A tabela
  sem `tenant_id` e o objeto fora do prefixo do tenant são decisões de arquitetura, não de
  implementação.
- **Design Approval Package** — `DESIGN_APPROVAL_REQUIRED`, antes do planejamento.
- Importadores da [F-026](../F-026-importadores-sinapi-sicro/feature.md) e do M8 — já na
  main, e é deles que o acervo depende para ler cada formato.
- **Arquivos reais das tabelas** para publicar — ato humano do operador. O SCO-Rio 07/2026
  **já está importado** localmente; SINAPI e SICRO precisam ser baixados manualmente:
  apurado em 2026-08-22 que o portal da Caixa responde `429` a download automatizado, mesmo
  com user-agent de navegador, e o do DNIT monta a listagem por JavaScript.

## Unknowns

1. **Como o catálogo é publicado** — upload pelo operador (presign de plataforma) ou
   arquivo entregue por outro caminho. Decide no plano.
2. **Se a retirada de circulação é estado ou remoção da listagem** — decide no plano; o
   requisito é só que rodada antiga não quebre.
3. **Nome da rota de listagem** — `/v1/reference-catalogs` (global) ou sob a rodada, que já
   conhece o regime e poderia filtrar. Decide no plano.
4. **Se SCO-Rio pode ser distribuída pela plataforma.** SINAPI (Caixa) e SICRO (DNIT) são
   públicas federais; a tabela da prefeitura precisa da mesma confirmação que a EMOP
   recebeu. **Se não puder, ela sai do acervo e continua por upload** — não muda o desenho,
   muda o conteúdo inicial.

## Risks

- **Precedente de tabela sem `tenant_id`.** Mitigação: o ADR-0047 nomeia a condição, a
  feature entrega o teste que a verifica, e qualquer tabela global futura exige ADR próprio.
- **Objeto do acervo vazar para o caminho que assina URL.** Mitigação: guarda de prefixo já
  existe e recusa; teste cobre explicitamente.
- **Acervo envelhecer em silêncio.** Mitigação: a data-base aparece na escolha e na
  proveniência de cada linha — um catálogo velho é visível na tela, não só no banco.
- **Publicar catálogo errado para todos os tenants de uma vez.** Mitigação: ato de
  `platform_operator`, auditado, e imutável por digest — corrigir é publicar outro e retirar
  o anterior de circulação, nunca reescrever.
- **Escopo escorregar para a integração automática.** Mitigação: está em `Out of Scope` e na
  decisão 9 do ADR, com a razão escrita.
- ~~**O operador publica por um presign que pertence à jornada do croqui.**~~ **Fechado por
  decisão humana de 2026-08-22**, que virou o escopo 7 e a
  [T6](tasks/T6-presign-da-plataforma.md). Fica o registro do que era: o portão de
  disponibilidade da [F-034](../F-034-disponibilidade-de-jornada/feature.md) é dependência
  do router (`main.py:3575-3614`) e `/v1/uploads` cai no prefixo `croqui`
  (`journeys.py:57-63`), então num ambiente com o croqui `disabled` o `platform_operator`
  receberia `403 JOURNEY_UNAVAILABLE` e o acervo ficaria sem como ser alimentado — e o
  croqui é justamente o módulo que a F-034 nasceu para poder desligar.

## Human Gates

1. Seleção (2026-08-22) — exercida.
2. **ADR-0047 aceito** — **exercido em 2026-08-22**.
3. **Design Approval Package aprovado** antes do planejamento — **exercido em 2026-08-22**,
   revisão 1 ([mock/](mock/README.md)).
4. Confirmação de que SCO-Rio pode ser distribuída pela plataforma — pendente (unknown 4).
5. Publicação dos arquivos reais em homologação — ato do operador, pós-deploy.
6. Merge e deploy.

## References

- [ADR-0047 — catálogo de referência como dado da plataforma](../../adr/0047-acervo-de-catalogos-da-plataforma.md)
- [ADR-0027 — proveniência de preço e fronteira licitada × pré-licitação](../../adr/0027-price-source-provenance-and-bid-boundary.md)
- [ADR-0039 — SINAPI e SICRO como origens de preço](../../adr/0039-sinapi-sicro-como-origens-de-preco.md)
- [F-026 — importadores SINAPI e SICRO](../F-026-importadores-sinapi-sicro/feature.md)
- [F-012 — operação SaaS da autorização de IA](../F-012-operacao-saas-autorizacao-ia/feature.md)
- [Roadmap canônico](../../product/ROADMAP.md)
