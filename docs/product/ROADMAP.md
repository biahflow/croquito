# Roadmap

Status: Active  
Responsável: Product  
Última revisão: 2026-08-17

## Uso no ciclo de engenharia

Este é o roadmap canônico do repositório e o equivalente documentado de `ROADMAP.md`
da Engineering OS. Ele decide **o que** está planejado; não é um Feature Contract nem
uma autorização de execução. Um item novo selecionado por humano recebe ID estável,
prioridade, estado do ciclo e, quando existir, referência a
`docs/features/<feature-id>/feature.md` conforme o
[Project Context](../engineering/PROJECT_CONTEXT.md).

Os marcos históricos abaixo permanecem como registro de produto. Eles não são
retroativamente convertidos em features nem selecionados automaticamente por agentes.

## Trabalho de engenharia em andamento

| ID | Prioridade | Estado | Contrato |
| --- | --- | --- | --- |
| F-001 | HIGH | IN_PROGRESS | [Clarificação do roadmap canônico e ambientes](../features/F-001-roadmap-clarification/feature.md) |
| F-002 | HIGH | DONE | [Contrato `/v1` da medição](../features/F-002-medicao-v1-contract/feature.md) |
| F-003 | HIGH | READY_FOR_PLANNING | [Migração da medição para a API `/v1` autenticada](../features/F-003-medicao-v1-migration/feature.md) |
| F-004 | HIGH | DONE | [Runner de migrations revisadas](../features/F-004-migrations-runner/feature.md) |
| F-005 | HIGH | DONE | [Gate de contrato da API: snapshot de OpenAPI e paridade](../features/F-005-openapi-contract-test/feature.md) |

Origem da seleção: decisão humana de 2026-08-17, registrada na
[seção 10 do evidence de F-001](../features/F-001-roadmap-clarification/evidence.md). F-002
entregou o [ADR-0028](../adr/0028-medicao-na-api-v1-autenticada.md), **aceito por ato humano
em 2026-08-17**, o que fechou F-002 e destravou o planejamento de F-003. Nenhuma rota de
medição existe em `/v1`: a decisão está tomada, a implementação não começou.

F-004 nasce na mesma data, também por seleção humana: o esquema da medição está decidido, mas
executar F-003 exige antes o runner de migrations que o
[ADR-0025](../adr/0025-homologacao-em-gcp-cloud-run.md) registra como requisito de produção em
falta. A decisão técnica é o [ADR-0029](../adr/0029-runner-de-migrations-revisadas.md),
**aceito por ato humano em 2026-08-17**, e a implementação foi entregue e revisada na mesma
data. O que resta em F-004 não é código: o primeiro deploy de homologação com o runner, que é
o que exercita o carimbo contra o banco real.

## Agora — MVP privado

- Golden dataset e eval harness.
- Upload, processamento, revisão e DXF.
- Guaxindiba, Toca e Raul Campelo.
- Dois provedores, Textract e scene graph.
- AWS gerenciada, retenção e observabilidade.

## Próximo — generalização controlada

- Ampliar regressão com documentos autorizados.
- Biblioteca versionada de símbolos e blocos.
- Melhor associação automática entre cotas e segmentos.
- Curvas e polígonos com constraints adicionais.
- Projetos persistentes com política contratual de retenção.
- Métricas de qualidade por categoria de croqui.

## Agora — medição de obra (contexto valuation, v1 em marcos)

Cadeia do orçamentista: importar a medição anterior, extrair a legenda quantificada da
prancha com revisão humana, sugerir código SCO com confirmação humana, montar memória
de cálculo e exportar a medição seguinte em `.xlsx` auditado. Marcos M1–M5 descritos no
contexto de arquitetura do módulo; IA paga somente no marco final, com os gates de
gasto existentes.

**Marcos seguintes (propostos em 2026-08-13, a especificar):** a primeira rodada real
(Campo do Toca) e a orçamentista do domínio fixaram uma distinção que governa os
próximos marcos — **dois momentos com regras de preço diferentes**:

- **Obra licitada (medição)**: o contrato manda. O preço SCO é composto (mão de obra e
  insumos dentro do código de serviço; a escolha certa é o código de *execução*, não o
  de mero fornecimento — distinção que a UI deve tornar visível). Item que não está na
  lista SCO/contrato **não pode** vir de outra tabela: o caminho é **aditivo de
  contrato** (RE-RA) solicitando a inclusão — o sistema deve detectar esses itens e
  produzir o **dossiê do aditivo** (item, quantitativo, justificativa), nunca precificar
  por fora. Criação/gestão de RE-RA segue no item abaixo.
- **Pré-licitação (orçamento-base)**: aí sim vale a cadeia **SCO → EMOP → composição
  manual**. Importador da tabela EMOP como segundo catálogo com proveniência
  (`PriceCatalogEntry.origin` vira dado; catálogo digital oficial é **pago** via GRE, em
  .DBF, com sincronização mensal possível por rotina — nova versão com data-base
  própria, nunca troca silenciosa de preço), e composição com coeficientes declarados
  (item → várias linhas: horas, insumos). É o coração do "gerador de orçamento" da fase
  1 da visão de produto.
- **M6 — UI web de homologação da medição** (priorizado pelo usuário em 2026-08-13):
  revisão do takeoff, shortlist com descrição completa do catálogo, confirmação de
  código e boletim — o ato humano da orçamentista numa tela, não no CLI. Destrava a
  homologação da cadeia existente; a rodada real da Toca está estacionada no elo da
  confirmação até este marco.
- **M7 — matcher híbrido de código SCO** (priorizado pelo usuário em 2026-08-13, durante
  a homologação: "não posso correr o risco de o código ter no SCO e não fazer o match"):
  léxico com radical conservador + sinônimos de domínio como dado, retrieval semântico
  por embeddings do catálogo (dado público SCO; índice local por digest) com fusão de
  ranking, e a garantia virando gate de eval — golden set com `recall@20 = 100%`.
  Candidatos sempre com origem e score declarados; confirmar segue ato humano; sem
  chave/teto, o léxico permanece como fallback funcional declarado.
- **M8 — fronteira licitada × pré-licitação** (entregue em código em 2026-08-17,
  [ADR-0027](../adr/0027-price-source-provenance-and-bid-boundary.md)): dossiê do
  aditivo como artefato de fechamento da rodada licitada (VAL-08); `PriceOrigin` +
  importador EMOP offline (.DBF com layout como dado; o arquivo real depende da
  assinatura GRE) + guardrail `BULLETIN_PRICE_ORIGIN_FORBIDDEN`; composição manual
  compilada a catálogo e orçamento-base (`build-estimate`) com cascata declarada e
  proveniência por linha (VAL-09). A UI do orçamento-base e o `.xlsx` no modelo da
  prefeitura ficam para marco futuro, quando houver exemplar real como template.

## Próximo — medição além do v1

Deliberadamente fora do v1, com as portas de extensão já reservadas no modelo:

- Modo teto / orçamento invertido ("escopo dentro de R$ X" da relação de demanda);
  porta: `EstimateTarget` reservado no glossário do contexto.
- Composição própria como caminho de escrita para item sem preço de referência;
  porta: `PriceCatalogEntry.origin`.
- Quantitativo automático derivado do scene graph aprovado; porta: `TakeoffItem.source`
  discriminado + `QuantitySource` lendo o `quantitativos.csv` do export DXF. Depende de
  identidade estruturada de elemento nas entidades (hoje rótulo é texto livre).
- Criação e gestão de re-ratificações (RE-RA); no v1 elas são apenas lidas para o
  cálculo de saldo.
- Reajuste de preços entre medições (data-base móvel).
- UI web de revisão da medição (v1 é CLI-first, como o resto do produto).
- Múltiplas pranchas por praça na extração de legenda.
- Cascata configurável de fontes de preço além do SCO (SINAPI, SICRO, tabelas
  estaduais), cada fonte com importador próprio — tabela de preços é dado, não código.

## Depois — produto comercial ampliado

- DWG após decisão de licenciamento.
- Comparação de versões V1/V2.
- Templates de layers por cliente.
- Multi-page alignment com referências explícitas.
- Integrações CAD e gestão de projetos.
- Modelos especializados somente após dataset licenciado e evals robustas.

## Não planejado sem nova decisão

- Promessa de conversão universal sem revisão.
- Inferência automática de dimensões inexistentes.
- Substituição de responsabilidade técnica do engenheiro.
- BIM/IFC ou modelagem 3D.

## Vocabulário de classificação

As classificações do inventário abaixo são as do Feature Contract de F-001 e têm o
significado declarado aqui. As definições descrevem o que já foi classificado; elas não
autorizam um agente a reclassificar um item.

| Classificação | Significado |
| --- | --- |
| `IMPLEMENTADO` | O mecanismo descrito pelo bullet completo está entregue e é verificável em código, testes, evals ou contratos versionados, e o [Status](../STATUS.md) não declara rodada real de homologação pendente para o próprio item. |
| `EM OPERAÇÃO/HOMOLOGAÇÃO` | O mecanismo está entregue **e** o [Status](../STATUS.md) declara, para o próprio item, uma rodada real de uso ou homologação humana ainda não concluída (“o que resta não é código”). |
| `PLANEJADO` | Declarado como trabalho futuro no roadmap canônico, sem seleção humana e sem mecanismo entregue **para o escopo descrito pelo bullet completo** — entrega parcial de um mecanismo citado no bullet não muda a classificação, e fica registrada na observação. |
| `HISTÓRICO` | Registro de marco concluído mantido como memória de produto, não convertido em trabalho. Não utilizada neste inventário. |
| `EXCLUÍDO` | Declarado explicitamente fora de escopo enquanto não houver nova decisão humana. |
| `UNKNOWN` | As fontes versionadas não sustentam nenhuma das anteriores. A lacuna é declarada e nenhuma classificação provável é sugerida. |

## Inventário de classificação F-001

O inventário é congelado nos 34 bullets existentes antes da entrada de F-001. A entrada de
F-001 na seção “Trabalho de engenharia em andamento” não faz parte dele. Cada linha
reproduz o **texto integral** do bullet de origem, com todos os seus qualificadores, e o
título exato da seção em que ele vive — a chave é a unidade de classificação, e um
qualificador suprimido mudaria o escopo classificado. O inventário congelado equivalente
está em
[plan.md](../features/F-001-roadmap-clarification/plan.md).

Evidência que cita apenas este roadmap significa intenção declarada, não verificação
independente. Nenhuma linha afirma estado remoto.

| # | Item (seção / bullet integral) | Classificação | Evidência | Observação |
| --- | --- | --- | --- | --- |
| 1 | Agora — MVP privado / Golden dataset e eval harness. | IMPLEMENTADO | [Status](../STATUS.md), [Evaluation Strategy](../ai/EVALUATION_STRATEGY.md) | O Status registra evals e casos dourados; não declara cobertura universal. |
| 2 | Agora — MVP privado / Upload, processamento, revisão e DXF. | IMPLEMENTADO | [Status](../STATUS.md), [Processing Workflows](../architecture/PROCESSING_WORKFLOWS.md) | Cadeia local e sessão autenticada são documentadas como entregues em código. |
| 3 | Agora — MVP privado / Guaxindiba, Toca e Raul Campelo. | UNKNOWN | [Status](../STATUS.md) | O Status apresenta evidências com níveis distintos entre os três casos; o bullet agrupado não sustenta uma classificação única. |
| 4 | Agora — MVP privado / Dois provedores, Textract e scene graph. | IMPLEMENTADO | [Status](../STATUS.md), [ADR-0005](../adr/0005-canonical-scene-graph.md) | Contratos e integrações são documentados; chamadas externas seguem sujeitas a gates. |
| 5 | Agora — MVP privado / AWS gerenciada, retenção e observabilidade. | PLANEJADO | [AWS Deployment](../architecture/AWS_DEPLOYMENT.md), [ADR-0002](../adr/0002-aws-managed-architecture.md) | AWS é desenho-alvo documentado; `infra/` é configuração versionada e não prova recursos aplicados. |
| 6 | Próximo — generalização controlada / Ampliar regressão com documentos autorizados. | PLANEJADO | [Roadmap](ROADMAP.md) | Declarado sob “Próximo”; autorização de documentos continua gate humano. |
| 7 | Próximo — generalização controlada / Biblioteca versionada de símbolos e blocos. | PLANEJADO | [Roadmap](ROADMAP.md) | Declarado sob “Próximo”. |
| 8 | Próximo — generalização controlada / Melhor associação automática entre cotas e segmentos. | PLANEJADO | [Roadmap](ROADMAP.md) | Declarado sob “Próximo”. |
| 9 | Próximo — generalização controlada / Curvas e polígonos com constraints adicionais. | PLANEJADO | [Roadmap](ROADMAP.md) | Declarado sob “Próximo”. |
| 10 | Próximo — generalização controlada / Projetos persistentes com política contratual de retenção. | PLANEJADO | [Roadmap](ROADMAP.md) | Declarado sob “Próximo”. |
| 11 | Próximo — generalização controlada / Métricas de qualidade por categoria de croqui. | PLANEJADO | [Roadmap](ROADMAP.md) | Declarado sob “Próximo”. |
| 12 | Agora — medição de obra (contexto valuation, v1 em marcos) / **Obra licitada (medição)**: o contrato manda. O preço SCO é composto (mão de obra e insumos dentro do código de serviço; a escolha certa é o código de *execução*, não o de mero fornecimento — distinção que a UI deve tornar visível). Item que não está na lista SCO/contrato **não pode** vir de outra tabela: o caminho é **aditivo de contrato** (RE-RA) solicitando a inclusão — o sistema deve detectar esses itens e produzir o **dossiê do aditivo** (item, quantitativo, justificativa), nunca precificar por fora. Criação/gestão de RE-RA segue no item abaixo. | EM OPERAÇÃO/HOMOLOGAÇÃO | [Status](../STATUS.md), [ADR-0027](../adr/0027-price-source-provenance-and-bid-boundary.md) | M8 está entregue em código; o primeiro dossiê real depende da rodada homologada. |
| 13 | Agora — medição de obra (contexto valuation, v1 em marcos) / **Pré-licitação (orçamento-base)**: aí sim vale a cadeia **SCO → EMOP → composição manual**. Importador da tabela EMOP como segundo catálogo com proveniência (`PriceCatalogEntry.origin` vira dado; catálogo digital oficial é **pago** via GRE, em .DBF, com sincronização mensal possível por rotina — nova versão com data-base própria, nunca troca silenciosa de preço), e composição com coeficientes declarados (item → várias linhas: horas, insumos). É o coração do "gerador de orçamento" da fase 1 da visão de produto. | EM OPERAÇÃO/HOMOLOGAÇÃO | [Status](../STATUS.md), [ADR-0027](../adr/0027-price-source-provenance-and-bid-boundary.md) | Caminho offline existe; importação do catálogo EMOP real depende de assinatura GRE. |
| 14 | Agora — medição de obra (contexto valuation, v1 em marcos) / **M6 — UI web de homologação da medição** (priorizado pelo usuário em 2026-08-13): revisão do takeoff, shortlist com descrição completa do catálogo, confirmação de código e boletim — o ato humano da orçamentista numa tela, não no CLI. Destrava a homologação da cadeia existente; a rodada real da Toca está estacionada no elo da confirmação até este marco. | EM OPERAÇÃO/HOMOLOGAÇÃO | [Status](../STATUS.md), [ADR-0020](../adr/0020-local-homologation-server-for-valuation.md) | Mecanismo está entregue; o Status mantém ato humano de homologação como pendência. |
| 15 | Agora — medição de obra (contexto valuation, v1 em marcos) / **M7 — matcher híbrido de código SCO** (priorizado pelo usuário em 2026-08-13, durante a homologação: "não posso correr o risco de o código ter no SCO e não fazer o match"): léxico com radical conservador + sinônimos de domínio como dado, retrieval semântico por embeddings do catálogo (dado público SCO; índice local por digest) com fusão de ranking, e a garantia virando gate de eval — golden set com `recall@20 = 100%`. Candidatos sempre com origem e score declarados; confirmar segue ato humano; sem chave/teto, o léxico permanece como fallback funcional declarado. | EM OPERAÇÃO/HOMOLOGAÇÃO | [Status](../STATUS.md), [ADR-0021](../adr/0021-hybrid-sco-code-retrieval.md) | Eval e mecanismo estão documentados; confirmação de código continua ato humano. |
| 16 | Agora — medição de obra (contexto valuation, v1 em marcos) / **M8 — fronteira licitada × pré-licitação** (entregue em código em 2026-08-17, [ADR-0027](../adr/0027-price-source-provenance-and-bid-boundary.md)): dossiê do aditivo como artefato de fechamento da rodada licitada (VAL-08); `PriceOrigin` + importador EMOP offline (.DBF com layout como dado; o arquivo real depende da assinatura GRE) + guardrail `BULLETIN_PRICE_ORIGIN_FORBIDDEN`; composição manual compilada a catálogo e orçamento-base (`build-estimate`) com cascata declarada e proveniência por linha (VAL-09). A UI do orçamento-base e o `.xlsx` no modelo da prefeitura ficam para marco futuro, quando houver exemplar real como template. | EM OPERAÇÃO/HOMOLOGAÇÃO | [Status](../STATUS.md), [ADR-0027](../adr/0027-price-source-provenance-and-bid-boundary.md) | Entregue em código; validações com fontes reais permanecem pendentes. |
| 17 | Próximo — medição além do v1 / Modo teto / orçamento invertido ("escopo dentro de R$ X" da relação de demanda); porta: `EstimateTarget` reservado no glossário do contexto. | PLANEJADO | [Roadmap](ROADMAP.md) | Declarado fora do v1 como extensão futura; a porta `EstimateTarget` é reserva de glossário, não mecanismo entregue. |
| 18 | Próximo — medição além do v1 / Composição própria como caminho de escrita para item sem preço de referência; porta: `PriceCatalogEntry.origin`. | PLANEJADO | [Roadmap](ROADMAP.md), [ADR-0027](../adr/0027-price-source-provenance-and-bid-boundary.md), [Status](../STATUS.md) | O bullet pede a composição própria **como caminho de escrita** para item sem preço de referência. O M8 entregou a composição compilada a catálogo `origin=composition` para o orçamento-base (ADR-0027, decisão 5); na medição licitada esse caminho segue fechado pelo guardrail `BULLETIN_PRICE_ORIGIN_FORBIDDEN` (ADR-0027, decisão 2). O escopo do bullet completo permanece não entregue. |
| 19 | Próximo — medição além do v1 / Quantitativo automático derivado do scene graph aprovado; porta: `TakeoffItem.source` discriminado + `QuantitySource` lendo o `quantitativos.csv` do export DXF. Depende de identidade estruturada de elemento nas entidades (hoje rótulo é texto livre). | PLANEJADO | [Roadmap](ROADMAP.md) | Declarado fora do v1 e dependente de identidade estruturada de elemento, que o próprio bullet registra como inexistente hoje. |
| 20 | Próximo — medição além do v1 / Criação e gestão de re-ratificações (RE-RA); no v1 elas são apenas lidas para o cálculo de saldo. | PLANEJADO | [Roadmap](ROADMAP.md) | Declarado fora do v1; o bullet registra que no v1 as RE-RA são apenas lidas. |
| 21 | Próximo — medição além do v1 / Reajuste de preços entre medições (data-base móvel). | PLANEJADO | [Roadmap](ROADMAP.md) | Declarado fora do v1 como extensão futura. |
| 22 | Próximo — medição além do v1 / UI web de revisão da medição (v1 é CLI-first, como o resto do produto). | PLANEJADO | [Roadmap](ROADMAP.md), [ADR-0020](../adr/0020-local-homologation-server-for-valuation.md), [ADR-0026](../adr/0026-medicao-hospedada-sessao-autenticada-minima.md), [Status](../STATUS.md) | O M6 entregou `apps/medicao` com tela de revisão do takeoff (ADR-0020, ADR-0026), que o Status declara ponte descartável até a migração da medição para a API `/v1` autenticada. O bullet completo qualifica o v1 como CLI-first; se o M6 já o satisfaz é decisão humana pendente, registrada em [evidence.md](../features/F-001-roadmap-clarification/evidence.md). |
| 23 | Próximo — medição além do v1 / Múltiplas pranchas por praça na extração de legenda. | PLANEJADO | [Roadmap](ROADMAP.md) | Declarado fora do v1 como extensão futura. |
| 24 | Próximo — medição além do v1 / Cascata configurável de fontes de preço além do SCO (SINAPI, SICRO, tabelas estaduais), cada fonte com importador próprio — tabela de preços é dado, não código. | PLANEJADO | [Roadmap](ROADMAP.md), [ADR-0027](../adr/0027-price-source-provenance-and-bid-boundary.md), [Status](../STATUS.md) | O M8 entregou a cascata de fontes declarada como dado e o importador EMOP `.DBF` (ADR-0027, decisões 4 e 6), com o arquivo real dependente da assinatura GRE. SINAPI, SICRO e as demais fontes citadas no bullet seguem sem importador próprio. |
| 25 | Depois — produto comercial ampliado / DWG após decisão de licenciamento. | PLANEJADO | [Roadmap](ROADMAP.md) | Declarado para depois e dependente de decisão de licenciamento. |
| 26 | Depois — produto comercial ampliado / Comparação de versões V1/V2. | PLANEJADO | [Roadmap](ROADMAP.md) | Declarado para depois. |
| 27 | Depois — produto comercial ampliado / Templates de layers por cliente. | PLANEJADO | [Roadmap](ROADMAP.md) | Declarado para depois. |
| 28 | Depois — produto comercial ampliado / Multi-page alignment com referências explícitas. | PLANEJADO | [Roadmap](ROADMAP.md) | Declarado para depois. |
| 29 | Depois — produto comercial ampliado / Integrações CAD e gestão de projetos. | PLANEJADO | [Roadmap](ROADMAP.md) | Declarado para depois. |
| 30 | Depois — produto comercial ampliado / Modelos especializados somente após dataset licenciado e evals robustas. | PLANEJADO | [Roadmap](ROADMAP.md) | Declarado para depois, sujeito a licença e evals. |
| 31 | Não planejado sem nova decisão / Promessa de conversão universal sem revisão. | EXCLUÍDO | [Roadmap](ROADMAP.md) | Declarado explicitamente como não planejado sem nova decisão. |
| 32 | Não planejado sem nova decisão / Inferência automática de dimensões inexistentes. | EXCLUÍDO | [Roadmap](ROADMAP.md) | Declarado explicitamente como não planejado sem nova decisão. |
| 33 | Não planejado sem nova decisão / Substituição de responsabilidade técnica do engenheiro. | EXCLUÍDO | [Roadmap](ROADMAP.md) | Declarado explicitamente como não planejado sem nova decisão. |
| 34 | Não planejado sem nova decisão / BIM/IFC ou modelagem 3D. | EXCLUÍDO | [Roadmap](ROADMAP.md) | Declarado explicitamente como não planejado sem nova decisão. |

## Reconciliação de ambientes

Cada ambiente é lido em três eixos separados, que não se substituem: o que o repositório
**configura**, o que a documentação **afirma** e o que foi **verificado remotamente**.
Nenhuma verificação remota foi executada por F-001 — nem foi autorizada.

| Contexto | Configuração versionada | Afirmação documental | Estado remoto verificado |
| --- | --- | --- | --- |
| Produção AWS | `infra/` (Terraform: S3 SSE-KMS, filas/DLQ, KMS, logs) descreve o desenho em `sa-east-1`. | [AWS Deployment](../architecture/AWS_DEPLOYMENT.md) declara que o desenho-alvo de produção **nunca foi aplicado**; o [Status](../STATUS.md) declara que não há serviços AWS reais. [ADR-0002](../adr/0002-aws-managed-architecture.md) segue valendo como decisão de produção, com a escolha em aberto. | Nenhum. Nada no repositório prova recursos AWS aplicados, e nenhuma consulta a conta AWS foi feita. |
| Homologação GCP | [`.github/workflows/deploy-hml.yml`](../../.github/workflows/deploy-hml.yml) configura o deploy no projeto `biahflow-hml`, região `us-east1`, para os serviços `croquito-*-hml`; [`deploy/nginx.conf`](../../deploy/nginx.conf) fixa a borda pública. Configuração de deploy não é prova de deploy. | [HML](../operations/HML.md) tem a seção “O que está no ar”, que **afirma** rotas públicas, serviços Cloud Run, buckets, tópico Pub/Sub e PostgreSQL gerenciado em operação; o [Status](../STATUS.md) afirma, no presente, que a homologação em GCP hospeda o servidor de medição como ponte declarada. Fontes: [ADR-0025](../adr/0025-homologacao-em-gcp-cloud-run.md) e [ADR-0026](../adr/0026-medicao-hospedada-sessao-autenticada-minima.md). Isso é afirmação documental, não verificação. | Nenhum. F-001 não executou os comandos de smoke de [HML](../operations/HML.md) nem qualquer chamada externa; o estado atual dos serviços permanece não verificado por esta feature. |
| Desenvolvimento local | `docker-compose.local.yml` e o [Makefile](../../Makefile) definem PostgreSQL, LocalStack e Keycloak, com bootstrap por `make db-init`. | [Local Development](../engineering/LOCAL_DEVELOPMENT.md) e o [Status](../STATUS.md) descrevem esse ambiente como iniciado e validado localmente. | Não aplicável. Nenhuma afirmação é feita sobre a máquina de qualquer operador. |
