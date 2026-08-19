# Roadmap

Status: Active  
Responsável: Product  
Última revisão: 2026-08-19 (F-012 documentada — operação SaaS da autorização de IA,
ADR-0036 `Proposed`, implementação completa; inventário F-013..F-017 aberto)

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
| F-001 | HIGH | DONE | [Clarificação do roadmap canônico e ambientes](../features/F-001-roadmap-clarification/feature.md) |
| F-002 | HIGH | DONE | [Contrato `/v1` da medição](../features/F-002-medicao-v1-contract/feature.md) |
| F-003 | HIGH | DONE | [Migração da medição para a API `/v1` autenticada](../features/F-003-medicao-v1-migration/feature.md) |
| F-004 | HIGH | DONE | [Runner de migrations revisadas](../features/F-004-migrations-runner/feature.md) |
| F-005 | HIGH | DONE | [Gate de contrato da API: snapshot de OpenAPI e paridade](../features/F-005-openapi-contract-test/feature.md) |
| F-006 | HIGH | DONE | [Conserto e verificação da homologação em GCP](../features/F-006-hml-conserto/feature.md) |
| F-007 | HIGH | READY_FOR_HUMAN_REVIEW | [Porta de entrada: tela de login com marca](../features/F-007-tela-de-login/feature.md) |
| F-008 | HIGH | BLOCKED | [Ciclo de vida de conta: convite, recuperação de senha e Google](../features/F-008-ciclo-de-vida-de-conta/feature.md) |
| F-009 | HIGH | READY_FOR_REVIEW | [Suite hospedada de providers: OpenAI + Anthropic direto, sem AWS](../features/F-009-suite-hospedada-sem-aws/feature.md) |
| F-010 | A DEFINIR | READY_FOR_SPEC | Revisão assistida em lote (a definir em contrato) |
| F-011 | A DEFINIR | READY_FOR_SPEC | Jornada guiada da revisão (a definir em contrato) |
| F-012 | HIGH | READY_FOR_REVIEW | [Operação SaaS da autorização de IA](../features/F-012-operacao-saas-autorizacao-ia/feature.md) |
| F-013 | A DEFINIR | READY_FOR_SPEC | UI de membros do tenant, depende de F-008 (a definir em contrato) |
| F-014 | A DEFINIR | READY_FOR_SPEC | Entidade tenant e onboarding self-service (a definir em contrato) |
| F-015 | A DEFINIR | READY_FOR_SPEC | Recriar o job de upload existente (a definir em contrato) |
| F-016 | A DEFINIR | READY_FOR_SPEC | Rotação de chaves e segredos de provider (a definir em contrato) |
| F-017 | A DEFINIR | READY_FOR_SPEC | Custo agregado por tenant e trilha de auditoria do entitlement na tela (a definir em contrato) |

Origem da seleção: decisão humana de 2026-08-17, registrada na
[seção 10 do evidence de F-001](../features/F-001-roadmap-clarification/evidence.md). F-002
entregou o [ADR-0028](../adr/0028-medicao-na-api-v1-autenticada.md), **aceito por ato humano
em 2026-08-17**, o que fechou F-002 e destravou o planejamento de F-003. O plano de execução
de F-003 foi aprovado por ato humano na mesma data, e a execução fechou em 2026-08-18: as
dezoito rotas existem e estão publicadas, a jornada de `apps/web` fala `/v1` e o modo hospedado
saiu do repositório. O que resta de F-003 não é código — são os atos de produção listados na
[evidência](../features/F-003-medicao-v1-migration/evidence.md).

F-004 nasce na mesma data, também por seleção humana: o esquema da medição está decidido, mas
executar F-003 exige antes o runner de migrations que o
[ADR-0025](../adr/0025-homologacao-em-gcp-cloud-run.md) registra como requisito de produção em
falta. A decisão técnica é o [ADR-0029](../adr/0029-runner-de-migrations-revisadas.md),
**aceito por ato humano em 2026-08-17**, e a implementação foi entregue e revisada na mesma
data. O que resta em F-004 não é código: o primeiro deploy de homologação com o runner, que é
o que exercita o carimbo contra o banco real.

F-006 nasce em 2026-08-18, por seleção humana, quando o levantamento das features abertas
mostrou que as cinco anteriores estavam `DONE` e que **tudo o que restava delas eram atos de
produção que o ambiente no chão impedia**. O diagnóstico daquele dia achou uma causa raiz
única — o endereço do banco nos secrets aponta para um endpoint do Neon que não existe mais, o
que derruba o Keycloak e barra a esteira no job de banco desde 2026-08-14 — e uma secundária: a
API está servindo o container de exemplo do Cloud Run. A senha gravada estava correta o tempo
todo; o proxy do Neon é que responde a endpoint desconhecido com falha de autenticação. A decisão técnica é o
[ADR-0031](../adr/0031-segredo-de-homologacao-gerenciado-por-terraform.md) (`Accepted` por ato
humano em 2026-08-18), que
move o valor das credenciais de homologação para o Terraform do repositório central de
infraestrutura. Evidência em
[evidence.md](../features/F-006-hml-conserto/evidence.md).

**O ambiente subiu em 2026-08-18** e a fumaça da esteira prova as quatro rotas, com os quatro
serviços servindo a mesma imagem por SHA. Cinco dos seis critérios estão atendidos; o critério
do carimbo do Alembic não era atendível com banco vazio e segue como ato aberto de F-004. Duas
correções fora do escopo original entraram na mesma rodada, cada uma por ter janela própria:
Keycloak e aplicação compartilhavam o schema `public` — e consertar isso depois do primeiro
usuário do realm custaria esse usuário —, e o deploy corria em paralelo com o portão de
qualidade em vez de esperá-lo. O ADR foi aceito e as pendências operacionais foram declaradas
concluídas pelo responsável humano; F-006 está `DONE`. O critério do carimbo do Alembic continua
explicitamente não atendível neste deploy e segue como follow-up de F-004.

F-007 nasce em 2026-08-18, por seleção humana: o produto não tem porta de entrada.
`deploy/nginx.conf` manda a raiz do host para `/revisao/`, e ali a SPA sem sessão mostra a casca
da revisão vazia, com o "Entrar" reduzido a um botão de segunda ordem na topbar. Duas decisões
humanas da mesma data fixam o desenho: a raiz passa a levar a `/login`, e a marca acompanha a
jornada inteira — inclusive a página do Keycloak, cujo `loginTheme` é `null` nos dois realms. A
prioridade é `HIGH`, **definida por ato humano em 2026-08-18**, e a ordem acordada é **depois da
F-006**, porque sem homologação no ar nenhum critério da feature é verificável em ambiente real. A
decisão técnica é o [ADR-0032](../adr/0032-porta-de-entrada-e-estado-sem-sessao.md), **aceito por
ato humano em 2026-08-18**. Contrato em
[feature.md](../features/F-007-tela-de-login/feature.md).

F-008 nasce em 2026-08-18, na mesma conversa, quando a pergunta virou "e o esqueci a senha, e o
autocadastro?". A investigação mostrou que o autocadastro **agrava** o problema que ele pretendia
resolver: `tenant_id` é atributo do usuário levado ao token pelo mapper `tenant-id`, e
`identity_from_claims` em `packages/core/src/croquito_core/oidc.py` recusa token sem esse claim —
uma conta auto-cadastrada autentica e toma `401` em toda chamada. O
[ADR-0011](../adr/0011-oidc-portable-identity.md) já havia decidido o caminho: convite, com o
vínculo atribuído pelo `tenant_admin`. Decisão humana de 2026-08-18: **convite, não autocadastro**;
Google como método de login de conta que já existe, sem criação automática. A feature nasce
`BLOCKED` porque `smtpServer` está ausente nos dois realms e o provedor de e-mail e o domínio
remetente ainda não foram escolhidos — sem isso, nenhum dos três fluxos existe, e é o D8 do
[ADR-0033](../adr/0033-conta-por-convite-e-login-federado.md), **aceito por ato humano em
2026-08-18**, que registra essa pendência. Contrato em
[feature.md](../features/F-008-ciclo-de-vida-de-conta/feature.md).

F-009 nasce em 2026-08-19, por seleção humana, na mesma conversa que diagnosticou o upload real
parado em `JOB_NOT_READY` no HML: a suite de providers hospedada montava os braços Bedrock e
Textract com `boto3` sem nenhuma credencial explícita — o ambiente publicado é GCP
([ADR-0025](../adr/0025-homologacao-em-gcp-cloud-run.md)), o caminho AWS nunca rodou neste
repositório, e a chamada de OCR do Textract no pacote de revisão era código morto. O usuário
aprovou explicitamente, na mesma data: chamada paga de provider, envio do documento a serviço
externo, suite sem AWS (Anthropic primário, OpenAI fallback), braço de OCR determinístico via
Cloud Vision, teto de US$ 5 por rodada e allowlist por env var. A prioridade é `HIGH`. A decisão
técnica é o [ADR-0035](../adr/0035-suite-hospedada-openai-anthropic-direto.md), `Proposed` —
aceitação segue como ato humano. As tarefas T1, T2, T3 e T5 do
[plano](../features/F-009-suite-hospedada-sem-aws/plan.md) estão completas; T4 (esta
documentação) fecha a implementação. A infraestrutura em `biahflow/infra` está APLICADA
(PRs #14 e #15 mesclados, apply verde, secrets com valor write-only, Vision API habilitada,
retenção de 7 dias no bucket). O que resta não é código: aceite do ADR; papel
`platform_operator` e entitlement do tenant; digest do PDF autorizado na allowlist; e o
próprio merge/deploy. Contrato em
[feature.md](../features/F-009-suite-hospedada-sem-aws/feature.md).

F-010 — revisão assistida em lote — nasce em 2026-08-19, por seleção humana, na mesma conversa
da F-009: leitura com tripla concordância (os dois LLMs concordam, o OCR determinístico
confirma, a associação é única e o solver fecha dentro da tolerância) nasce pré-aceita em lote,
e o revisor faz uma conferência e um ato de aprovação no lugar de decisão leitura a leitura. O
gate humano de aprovação e o portão de exportação (`SceneRevision.export_errors()`) permanecem
intocados — o que muda é o ponto de partida da revisão, não quem decide. Depende dos dados reais
da F-009 (upload real corroborado por OCR) para calibrar os limiares de concordância. Ainda sem
Feature Contract: esta linha é o registro canônico até a especificação, e a prioridade é decisão
humana pendente.

F-011 — jornada guiada da revisão — nasce em 2026-08-19, por seleção humana, na primeira revisão
da porta nova: o responsável quer a experiência da revisão como **jornada guiada** — a próxima
tarefa só habilita quando a atual é cumprida, no lugar do formulário aberto de hoje. É mudança de
UX transversal à jornada da revisão (`INTERFACE_CHANGE` na classificação da camada pinada:
exigirá Design Approval Package antes do planejamento). Ainda sem Feature Contract: esta linha é
o registro canônico até a especificação, e a prioridade é decisão humana pendente. **Renumerada
de F-009 para F-011 nesta revisão do roadmap**: a mesma data de nascimento produziu três itens
candidatos a numeração (esta jornada guiada, a suite hospedada sem AWS e a revisão assistida em
lote) e as duas primeiras entradas colidiram no ID `F-009` — a suite hospedada já tinha Feature
Contract, plano e três tasks implementadas sob esse ID quando a colisão foi identificada durante
a execução da F-009, então o item ainda sem contrato escrito é o que se move, não o que já tem
trabalho publicado.

F-012 nasce em 2026-08-19, por seleção humana, na sequência imediata da F-009: o usuário vetou
os dois rituais manuais que a ativação da suite hospedada deixou — entitlement por curl com
token pescado do DevTools, e allowlist de digest por env var exigindo um redeploy por documento
— com a diretriz literal "isso já nasce com a visão de SaaS, não posso ter esses
gargalos/travas". A prioridade é `HIGH`. A decisão técnica é o
[ADR-0036](../adr/0036-autorizacao-de-ia-contratual-sem-allowlist-documental.md), `Proposed`:
o gate de envio a provider pago no caminho hospedado passa a ser integralmente entitlement
contratual ativo do tenant + consent por job + teto de custo por invocação + kill switch, sem
segunda barreira por documento; a allowlist por digest permanece intocada no caminho offline de
eval (`extraction_eval.py`), que não tem tenant nem entitlement. As quatro tarefas do
[plano](../features/F-012-operacao-saas-autorizacao-ia/plan.md) estão completas: a allowlist
saiu do worker e do deploy do HML (T1); `GET /v1/me` e os dois GETs de plataforma
(`/v1/platform/tenants`, `/v1/platform/tenants/{id}/ai-processing-entitlement`) existem, com
snapshot OpenAPI atualizado (T2); a jornada "Plataforma" entrou na SPA — botão condicional ao
papel `platform_operator`, `?plataforma=` fazendo round-trip pelo login, lista de tenants com
ativação/desativação inline e Idempotency-Key nas mutações (T3); e esta documentação fecha a
implementação (T4). O que resta não é código: aceite do ADR-0036 e o próprio merge, que é
deploy. Contrato em
[feature.md](../features/F-012-operacao-saas-autorizacao-ia/feature.md).

A F-012 também abriu um inventário de gargalos SaaS ainda sem Feature Contract, registrado
aqui como o registro canônico até a especificação de cada item, todos nascidos em 2026-08-19,
por seleção humana, na mesma conversa: **F-013** UI de membros do tenant (depende do convite da
F-008, `BLOCKED`); **F-014** entidade tenant própria e onboarding self-service (hoje `tenant_id`
só existe no Keycloak e como coluna nas tabelas de domínio); **F-015** recriar o job de upload
existente, sem exigir digest nem allowlist; **F-016** rotação de chaves e segredos de provider;
**F-017** custo agregado por tenant e trilha de auditoria do entitlement, visíveis na própria
tela de plataforma. F-008 permanece `BLOCKED`: o que a impede é a decisão do usuário sobre
provedor de e-mail e domínio remetente, não código.

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

A verificação remota da homologação foi autorizada e executada em 2026-08-17, repetida e
aprofundada em 2026-08-18. Até 2026-08-17 ela observava só a borda pública; na rodada de
2026-08-18 a autorização foi ampliada e o projeto GCP foi consultado com `gcloud`, somente
leitura, o que trocou "a sessão autenticada não sobe" por **por que** ela não sobe. Produção
AWS e ambiente local continuam sem verificação remota.

| Contexto | Configuração versionada | Afirmação documental | Estado remoto verificado |
| --- | --- | --- | --- |
| Produção AWS | `infra/` (Terraform: S3 SSE-KMS, filas/DLQ, KMS, logs) descreve o desenho em `sa-east-1`. | [AWS Deployment](../architecture/AWS_DEPLOYMENT.md) declara que o desenho-alvo de produção **nunca foi aplicado**; o [Status](../STATUS.md) declara que não há serviços AWS reais. [ADR-0002](../adr/0002-aws-managed-architecture.md) segue valendo como decisão de produção, com a escolha em aberto. | Nenhum. Nada no repositório prova recursos AWS aplicados, e nenhuma consulta a conta AWS foi feita. |
| Homologação GCP | A casca do ambiente é Terraform no repositório `biahflow/infra` (stack `envs/hml/croquito`); aqui, [`.github/workflows/deploy-hml.yml`](../../.github/workflows/deploy-hml.yml) configura imagem e revisão dos serviços `croquito-*-hml` e [`deploy/nginx.conf`](../../deploy/nginx.conf) fixa a borda pública. Configuração de deploy não é prova de deploy. | [HML](../operations/HML.md) deixou de afirmar disponibilidade: a seção “O que está publicado” descreve o desenho e a seção “Estado verificado” carrega data e medição. Fontes: [ADR-0025](../adr/0025-homologacao-em-gcp-cloud-run.md) e [ADR-0031](../adr/0031-segredo-de-homologacao-gerenciado-por-terraform.md). | **Fumaça da esteira em 2026-08-18T14:06, quatro rotas verdes**: `/revisao/`, `/medicao/`, `/api/v1/meta` e o discovery OIDC, este anunciando `https://croquito-hml.biahflow.ai/auth/realms/croquito` — a sessão autenticada está de pé, depois de quatro dias fora do ar. Os quatro serviços servem a mesma imagem por SHA (`:3acbcc1`), não mais o `cloudrun/container/hello`. Estado interno do PostgreSQL verificado nesta data e antes só suposto: as 19 tabelas da aplicação no schema `croquito` com `alembic_version` = `0002`, as 88 do Keycloak em `keycloak`, e `public` vazio depois da limpeza — antes disso os dois componentes dividiam `public`, ao contrário do que a documentação afirmava. `/api/healthz` segue **404** e isso deixou de ser defeito: o Cloud Run reserva `/healthz` na raiz de todo serviço e a requisição nunca alcança o container, então a verificação externa usa `/api/v1/meta`. Não verificado: conteúdo de bucket e entrega do Pub/Sub. Ainda medido só da esteira e do `run.app`: a borda pública `croquito-hml.biahflow.ai` não é alcançável da máquina do operador desta sessão. Registro em [F-006](../features/F-006-hml-conserto/feature.md). |
| Desenvolvimento local | `docker-compose.local.yml` e o [Makefile](../../Makefile) definem PostgreSQL, LocalStack e Keycloak, com bootstrap por `make db-init`. | [Local Development](../engineering/LOCAL_DEVELOPMENT.md) e o [Status](../STATUS.md) descrevem esse ambiente como iniciado e validado localmente. | Não aplicável. Nenhuma afirmação é feita sobre a máquina de qualquer operador. |
