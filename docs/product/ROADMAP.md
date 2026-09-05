# Roadmap

Status: Active  
Responsável: Product  
Última revisão: 2026-08-28 (**F-007, F-022, F-029, F-031 e F-032 `DONE`** — as cinco
estavam `READY_FOR_HUMAN_REVIEW` e o dono do produto exerceu o ato humano de aceite na mesma
data. O **ADR-0037 passou a `Accepted`** no mesmo ato. Os residuais que dependem de dinheiro,
credencial ou infraestrutura externa **não** foram exercidos e continuam declarados nos
respectivos `feature.md` e no [STATUS](../STATUS.md). Registrado antes: **F-045 registrada e
entregue** — `READY_FOR_REVIEW`/`HIGH`, com
**ADR-0061 aceito** e pacote de design revisão 1 **aprovado** no mesmo dia. O que a originou: a etapa de códigos não tem como desfazer um par `(item, código)` confirmado, e o único
conserto hoje é refazer a rodada inteira. A lacuna é da F-038, que fez do par a identidade da
decisão; a revisão 2 do pacote da F-044 apenas aumentou o preço dela, ao criar um ato que
grava N códigos de uma vez. Registrado antes: **F-042, F-043 e F-044 `IN_PROGRESS`** — os gates humanos das
três foram exercidos no mesmo dia em que foram registradas: Design Approval Packages
aprovados, **ADR-0060** aceito (o acervo de canteiro tem duas origens, plataforma e tenant,
com um contrato de leitura só), e o gate que podia **cancelar a F-044** foi cumprido — o dono
forneceu três orçamentos reais e a hipótese de repetição se confirmou, com 80% dos rótulos
reaparecendo entre praças e 96,1% dos repetidos com pacote de códigos idêntico ou contido. O
ganho medido, de 54 a 120 linhas por praça, é cerca de cinco vezes a estimativa que originou
a prioridade `MEDIUM` dela — revista pelo dono em 2026-08-28: **elevada a `HIGH`**. Os
pacotes de design da F-042 e da F-043 ganharam **revisão 2** depois que o documento real e a
implementação refutaram premissas do desenho, e as duas revisões foram **aprovadas na mesma
data (2026-08-28)** — este parágrafo dizia "aguardam aprovação" por dessincronia, corrigida
em 2026-09-04. Registrado antes:

> **F-042, F-043 e F-044 registradas** `READY_FOR_PLANNING`, de
uma pergunta de ROI do dono do produto medida contra a planilha orçamentária real do Campo do
Toca: das 43 linhas preenchidas, 24 não têm origem na prancha, e a saída atual não é o
documento que a prefeitura recebe. O **ADR-0059** foi **aceito por ato humano na mesma data** (alternativa A) e é precondição das três —
sem ele a lista de preços do contrato não carrega, porque 2 códigos em 823 não casam o padrão
SCO estrito. Antes: **F-018 e F-019 `DONE`** — Design Approval Packages aprovados,
implementação integrada na `main` pelo PR #105 e **aceite por ato humano** na mesma data; a
correção humana de forma como proposta derivada (ADR-0050) e o preview da cena resolvida antes
da aprovação. O `deploy-hml` da revisão aplicou a migração `0019`. Antes:
**F-030 `READY_FOR_BUILD`** — ADR-0049 emendado, Design Approval
Package revisão 3 aprovado, plano autorizado e oito Task Contracts publicados; antes:
**F-009 e F-012 `DONE`** — ADR-0035/0036 e entregas aceitos por
ato humano após merges, infraestrutura aplicada e rodadas reais no HML; antes: **F-036
`DONE`** — o orçamento assinado vira o contratado da
medição, e seis guardrails que não podiam disparar passam a poder; entrega aceita por ato
humano.
Antes: faixa F-011..F-019 auditada contra o código: **F-011 encerrada
`DONE`** por já estar entregue quando foi registrada, F-015 e F-017 encolhidas ao que de fato
sobrou, e **F-018 e F-019 ganharam Feature Contract**; F-034 **aceita por ato humano** — `DONE`;
F-036 e F-030 ganharam Feature Contract por seleção humana e seus gates foram depois exercidos;
antes disso, estado da F-034 reconciliado — as duas fatias já estavam na main desde 2026-08-22, e o contrato e esta tabela
seguiam em READY_FOR_PLANNING; o pacote de revisão dela foi escrito. Antes, em 2026-08-22:
F-037 (acervo de catálogos, ADR-0047) e F-035 (aprovação do orçamento, ADR-0046) entregues;
F-033 entregue — demanda sob contrato licitado sobre o ADR-0045; F-032 integrada à main com
a fatia de sincronização completa; antes: F-029 aberta com contrato,
absorvendo a fatia 2 da F-023; F-021 e F-022 abertas com contrato, ADR-0037 `Proposed`;
F-012 documentada; inventário
F-013..F-017 aberto; F-018/F-019 abertas; F-020 aberta com contrato)

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
| F-007 | HIGH | DONE | [Porta de entrada: tela de login com marca](../features/F-007-tela-de-login/feature.md) — aceita por ato humano em 2026-08-28; pendem o deploy da imagem nova do Keycloak em homologação e o texto final da tela |
| F-008 | HIGH | READY_FOR_PLANNING | [Ciclo de vida de conta: convite, recuperação de senha e Google](../features/F-008-ciclo-de-vida-de-conta/feature.md) — **destravada em 2026-09-05**: a decisão de e-mail foi tomada por ato humano e virou a [Emenda 1 do ADR-0033](../adr/0033-conta-por-convite-e-login-federado.md) — transacional pelo **Google Workspace já pago**, remetente no domínio principal (subdomínio próprio adiado para junto de uma eventual migração de provedor). F-007 e F-006 já `DONE`. Pendem só atos de operador antes do build: senha de app do Workspace e o segredo por Terraform (D7) |
| F-009 | HIGH | DONE | [Suite hospedada de providers: OpenAI + Anthropic direto, sem AWS](../features/F-009-suite-hospedada-sem-aws/feature.md) |
| F-010 | HIGH | DONE | [Revisão assistida em lote — fatia 1: anotações sugeridas](../features/F-010-revisao-assistida-lote/feature.md) |
| F-011 | — | DONE | [Jornada guiada da revisão](../features/F-011-jornada-guiada-da-revisao/feature.md) — já entregue quando foi registrada |
| F-012 | HIGH | DONE | [Operação SaaS da autorização de IA](../features/F-012-operacao-saas-autorizacao-ia/feature.md) |
| F-013 | A DEFINIR | READY_FOR_SPEC | UI de membros do tenant, depende de F-008 (a definir em contrato) |
| F-014 | A DEFINIR | READY_FOR_SPEC | Entidade tenant e onboarding self-service (a definir em contrato) |
| F-015 | A DEFINIR | READY_FOR_SPEC | Recriar job a partir de upload já usado (`jobs.upload_id` é `UNIQUE`) — a definir em contrato |
| F-016 | A DEFINIR | READY_FOR_SPEC | Rotação de chaves e segredos de provider (a definir em contrato) |
| F-017 | A DEFINIR | READY_FOR_SPEC | Trilha de auditoria do entitlement na tela — o custo por tenant já saiu na F-031 (a definir em contrato) |
| F-018 | HIGH | DONE | [Corrigir a forma da proposta na tela, sem rerodar o provider](../features/F-018-edicao-de-forma-da-proposta/feature.md) |
| F-019 | HIGH | DONE | [Ver a cena resolvida antes de exportar](../features/F-019-preview-da-cena-resolvida/feature.md) |
| F-020 | HIGH | DONE | [Jornada web do orçamento-base](../features/F-020-orcamento-base-web/feature.md) |
| F-021 | HIGH | DONE | [Nota pré-classificada na decisão da leitura](../features/F-021-nota-pre-classificada/feature.md) |
| F-022 | HIGH | DONE | [Document AI como braço de OCR](../features/F-022-document-ai-braco-ocr/feature.md) — aceita por ato humano em 2026-08-28, com o ADR-0037 `Accepted`; pendem provisionamento GCP/env em HML e o eval comparativo pago |
| F-025 | HIGH | DONE | [Consultor do traçado](../features/F-025-consultor-do-tracado/feature.md) |
| F-024 | HIGH | DONE | [Leitura com valor não morre por falta de target_hint](../features/F-024-leitura-sem-target-hint/feature.md) |
| F-023 | HIGH | DONE | [Survey Quality Score](../features/F-023-survey-quality-score/feature.md) |
| F-028 | HIGH | DONE | [Aprovação nominal e boletim da medição pela web](../features/F-028-boletim-medicao-web/feature.md) |
| F-026 | HIGH | DONE | [Importadores SINAPI e SICRO na cascata do orçamento-base](../features/F-026-importadores-sinapi-sicro/feature.md) |
| F-027 | HIGH | DONE | [Modo teto: orçamento invertido por verba declarada](../features/F-027-modo-teto-orcamento-invertido/feature.md) |
| F-029 | HIGH | DONE | [Auto-associação de cotas por confiança calibrada (experimento local)](../features/F-029-auto-associacao-confianca/feature.md) — aceita por ato humano em 2026-08-28; pendem a rodada local com a flag ligada, a calibração com os 7 PDFs reais e a escolha do threshold operacional |
| F-030 | HIGH | DONE | [O levantamento de campo na jornada de revisão: a foto e a medida](../features/F-030-levantamento-de-campo-na-revisao/feature.md) — **aceita por ato humano em 2026-09-05**. As oito tarefas estavam na `main` desde 2026-08-25 (PR #29) com este roadmap parado em READY_FOR_BUILD — o mesmo padrão código-à-frente das F-046/F-047. O fecho produziu a evidência de navegador que faltava (painel de evidência, vínculo do levantamento, duas testemunhas empilhadas com diferença NEUTRA, observação com lineage — provado até o banco) e a revisão focada (`REVIEW_PASS`). Dívidas declaradas: a rodada paga de classificação (corpus de 6 fotos + autorização ≤ US$ 5), o apply do Terraform da retenção (ADR-0051) e a fumaça em HML |
| F-033 | HIGH | DONE | [Demanda sob contrato licitado: cascata restrita à tabela contratual](../features/F-033-demanda-sob-contrato-licitado/feature.md) |
| F-034 | HIGH | DONE | [Disponibilidade de jornada por ambiente e por tenant](../features/F-034-disponibilidade-de-jornada/feature.md) |
| F-035 | HIGH | DONE | [Aprovação nominal do orçamento antes do despacho](../features/F-035-aprovacao-do-orcamento/feature.md) |
| F-036 | HIGH | DONE | [A medição do orçamento aprovado: consolidado contratual de origem](../features/F-036-vinculo-orcamento-medicao/feature.md) |
| F-037 | HIGH | DONE | [Acervo central de catálogos de preço](../features/F-037-acervo-de-catalogos/feature.md) |
| F-038 | HIGH | DONE | [O item de legenda é um pacote de serviços, não um código](../features/F-038-pacote-de-servicos/feature.md) — **aceita por ato humano em 2026-09-05**: as doze tarefas estavam na `main` desde 2026-08-26, e a bancada delegada exerceu o que faltava contra o dado real — o pacote do PISO EM CONCRETO montado e fechado **na tela** numa praça-bancada com o catálogo SCO Out/2023 real, e os critérios numéricos do contrato batidos com o arquivo como oráculo (6 linhas do PISO; `BP04050350(/)` = 478,74 somando as 4 parcelas rotuladas; `BP09100050(B)` = 418,12; pendente até fechar). Dívida declarada: a extração e o aceite reais pela orçamentista |
| F-039 | HIGH | DONE | [Reajuste de preços entre medições](../features/F-039-reajuste-entre-medicoes/feature.md) — **aceita por ato humano em 2026-09-05**, sobre a rodada de revisão da mesma data (`REVIEW_PASS`, linha a linha do núcleo integrado desde o PR #107, 84 testes dirigidos verdes). Decisão exercida no aceite: o fator fica na **linha da declaração**, não como coluna (desvio 2 do pacote aceito como melhoria — o fator é do contrato inteiro, e composição não tem fator único por linha). Dívida declarada: nenhuma medição real com contrato reajustado atravessou — o primeiro uso real é o teste de verdade |
| F-040 | HIGH | DONE | [RE-RA declarada e a medição seguinte](../features/F-040-re-ra-e-medicao-seguinte/feature.md) — **aceita por ato humano em 2026-09-02**, fechando a [issue #100](https://github.com/biahflow/croquito/issues/100). A T6 e a T7 fecharam os três desvios do pacote de design que a captura expôs, e a recaptura dos seis estados foi feita em 2026-09-01, tudo na `main` pelo PR #129. Dívida declarada: nenhuma medição real com contrato re-ratificado atravessou — o aceite é sobre o mecanismo, provado por evidência sintética |
| F-041 | HIGH | DONE | [O braço semântico roda no caminho hospedado](../features/F-041-braco-semantico-hospedado/feature.md) — **aceita por ato humano em 2026-09-05**. Implementada e integrada desde 2026-08-26 (PR #114: rotas de plataforma, migração 0020, teto de 64 MiB, degradação por fonte, telas testadas, VAL-12 corrigida) com o contrato parado em READY_FOR_PLANNING. O fecho produziu a evidência de navegador (tabela e índice publicados pela tela de Plataforma; recálculo degradando com o motivo por extenso — D8 do ADR-0054) e a revisão focada (`REVIEW_PASS`). Dívidas declaradas: publicar o índice REAL (40,7 MB no disco do operador) e o recompute pago real |
| F-042 | HIGH | DONE | [O canteiro sai de um acervo parametrizado, não da digitação](../features/F-042-acervo-de-parcelas-de-canteiro/feature.md) — **aceita por ato humano em 2026-09-05, com o gate 4 cumprido com achado**: a autoria nasceu na tela a partir da praça-bancada real (6 parcelas, `semi_perimetro` e `prazo_meses` como parâmetros) e a aplicação numa praça nova atravessou prévia → apply → montagem, com as 5 linhas de canteiro nascendo **sem digitação** (7.387,50 = 98,50×3×1×25). O achado: serviço `STANDALONE` era imprecificável por construção (fonte citada só nasce de confirmação de código) — reparado no laço da revisão (fonte única resolve; multi-fonte segue recusando; elemento nunca usa o fallback), com o registro no [evidence](../features/F-042-acervo-de-parcelas-de-canteiro/evidence.md). Dívida declarada: a autoria real pela orçamentista; achado menor na issue #177 |
| F-043 | HIGH | DONE | [A planilha sai no gabarito da prefeitura, com memória de cálculo](../features/F-043-planilha-no-gabarito-da-prefeitura/feature.md) — **aceita por ato humano em 2026-09-04, contra o documento real**: o arquivo gerado do Campo do Toca espelha o real linha por linha (454/454), auditoria 0 findings, total 648.956,63. As três tarefas entregues em 2026-09-01 (PRs #115 e #131); a revisão pré-aceite achou e fechou a linha de grupo ausente (PR #143). Decisões exercidas: rodapé pelo ADR-0038 por agora, e o preço do contrato NÃO embute BDI (o `TOTAL S/BDI` do cliente é erro do arquivo dele). O gabarito real foi publicado como artefato de plataforma no mesmo dia (433 linhas, revisão `REV SEAC — OUT/23`, imutável); o unknown do lote fechou em 2026-09-04: gabarito é por lote e a escolha explícita do seletor da rodada é a declaração — nada mais aberto |
| F-044 | HIGH | DONE | [A shortlist aprende com as decisões de código já tomadas](../features/F-044-precedente-de-codigo/feature.md) — **aceita por ato humano em 2026-09-05**, sobre a rodada `REVIEW_PASS` de 2026-09-04 (revisão com reparo no meio: a evidência de navegador que faltava, PR #154, reprovou o aceite em lote — nunca gravava, a tela omitia `catalog_sha256` —, reparado e provado até o banco pelo PR #156). As três decisões exercidas no aceite: o unknown 3 segue **sem limiar** (a contagem de praças visível é o controle; reabre com corpus maior), o aceite **continua do pacote inteiro** (decisão 4 mantida; o erro sem volta é a lacuna que a F-045 fecha) e a **copy fica como está**, inclusive o "Value error, " do Pydantic na recusa nomeada |
| F-045 | HIGH | DONE | [Desfazer um código confirmado](../features/F-045-desfazer-codigo-confirmado/feature.md) — **aceita por ato humano em 2026-09-05**, sobre a rodada de revisão da mesma data (`REVIEW_PASS`, linha a linha do núcleo integrado desde os PRs #117/#118): revogação fail-closed, compensação do precedente na mesma transação, e a assimetria conferida entre jornadas (D7 recusa no orçamento; caducidade por digest acusa na medição). Decisão exercida no aceite: o **unknown 1 fechou** — a recusa de revogar pós-aprovação (`ASSIGNMENT_REVOCATION_AFTER_APPROVAL`) é definitiva, e o ADR-0061 D7 foi anotado. Dívida declarada: nenhum desfazer real de orçamentista atravessou |
| F-046 | HIGH | DONE | [A praça de várias pranchas](../features/F-046-praca-de-varias-pranchas/feature.md) — **aceita por ato humano em 2026-09-02**, fechando a [issue #101](https://github.com/biahflow/croquito/issues/101). Construída e integrada em 2026-08-29 (PRs #125, #127 e #128); evidência de navegador cumprida, com o achado do boletim vencido resolvido pelo #127. Dívida declarada: nenhuma praça real de mais de uma folha atravessou, e a rodada paga de extração não foi autorizada |
| F-047 | HIGH | DONE | [O quantitativo nasce da cena aprovada](../features/F-047-quantitativo-da-cena-aprovada/feature.md) — **aceita por ato humano em 2026-09-02**, fechando a [issue #102](https://github.com/biahflow/croquito/issues/102). Construída e integrada em 2026-08-29 (PR #126); evidência de navegador cumprida, com o 500 da idempotência em PostgreSQL resolvido pelo #124. Dívida declarada: nenhum croqui real chegou à medição sem redigitação, e a rodada paga de extração não foi autorizada |
| F-032 | HIGH | DONE | [App de levantamento de campo (PWA offline-first)](../features/F-032-app-levantamento-campo/feature.md) — aceita por ato humano em 2026-08-28; pendem chave/conta Groq + clipes + eval paga de transcrição, o papel `field_technician` no realm e a decisão de consentimento por levantamento |
| F-031 | MEDIUM | DONE | [Eventos de valor: telemetria de automação e emissão para o portal](../features/F-031-value-events/feature.md) — já integrada à main; aceita por ato humano em 2026-08-28; pendem o provisionamento do tópico Pub/Sub e as migrações no ambiente hospedado |
| F-048 | A DEFINIR | READY_FOR_PLANNING | [Auditoria de medição de terceiros: o furo que ninguém procurou](../features/F-048-auditoria-de-medicao-de-terceiros/feature.md) — **ganhou Feature Contract em 2026-09-05**, escolhida como a primeira das três candidatas da análise Orvia porque o motor já existe e já achou dinheiro errado em arquivo real (os 8 erros de centavo do MAPÃO do cliente, 2026-08-12, viram o caso de aceite). Faltam rota `/v1`, artefato de relatório e tela. Prioridade e Design Approval Package pendem do dono; o unknown 2 (produto avulso × dentro da jornada de medição) precede o planejamento |
| F-049 | A DEFINIR | READY_FOR_SPEC | [Dashboard executivo do contrato: planejado, realizado e saldo](../features/F-049-dashboard-executivo-do-contrato/feature.md) — **ganhou Feature Contract em 2026-09-05**. Sem domínio novo: o consolidado já guarda contratado, vigente, acumulado, saldo e a série por período (F-036/F-039/F-040) e a F-031 publica as métricas; falta apresentar junto. Continua `READY_FOR_SPEC` de propósito — o unknown 1 (para QUEM é a tela: dono da obra, gestor do contrato ou fiscal) precede o Design Approval Package. Cronograma/SPI seguem fora de escopo |
| F-050 | A DEFINIR | READY_FOR_SPEC | [Relatório de risco e pendências do período, pronto para o cliente](../features/F-050-relatorio-de-risco-do-periodo/feature.md) — **ganhou Feature Contract em 2026-09-05**. Agrega seis pendências que já existem isoladas (divergência de quantidade, itens não decididos, pacote aberto, boletim vencido, testemunha divergente, código revogado) e as classifica por consequência. `READY_FOR_SPEC`: dois unknowns precedem o desenho — se o documento é do período de medição ou do mês, e se testemunha observacional entra como risco |
| F-051 | HIGH | DONE | [A cota-balão encontra seu elemento: identidade declarada na revisão](../features/F-051-cota-balao-encontra-seu-elemento/feature.md) — **gate 3 cumprido com achado por ato humano em 2026-09-05**, fechando o ciclo aberto pela [issue #139](https://github.com/biahflow/croquito/issues/139): contra o croqui real do Toca, o elemento "B" foi declarado sobre o fecho da área de lazer, a candidata por identidade foi confirmada pelo portão de sempre e a `C=56` entrou no solver — exata, após o keep_apart da disputa 55×56 que o consultor ofereceu. ADR-0063 e DAP aprovados em 2026-09-04; as 7 tarefas entregues em 2026-09-04 (PRs #161..#172). O achado do gate virou a [issue #174](https://github.com/biahflow/croquito/issues/174) (vão amarra por projeção no eixo; fecho inclinado disputa com a largura — mecanismo anterior à feature). Dívida declarada: a identidade na cena do job real espera uma disputa pré-existente alheia sair da frente ([evidência](../features/F-051-cota-balao-encontra-seu-elemento/evidence.md)) |

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
técnica é o [ADR-0035](../adr/0035-suite-hospedada-openai-anthropic-direto.md), **aceito por
ato humano em 2026-08-23**. As tarefas T1, T2, T3 e T5 do
[plano](../features/F-009-suite-hospedada-sem-aws/plan.md) estão completas; T4 (esta
documentação) fecha a implementação. A infraestrutura em `biahflow/infra` está APLICADA
(PRs #14 e #15 mesclados, apply verde, secrets com valor write-only, Vision API habilitada,
retenção de 7 dias no bucket), e o PR #19 integrou a implementação na `main` (`8333956`). A
V12 exerceu os dois braços; as V14–V17 exerceram o caminho real com Anthropic e OCR. O braço
OpenAI foi desligado depois da V12 por decisão operacional, sem remover a capacidade entregue.
A allowlist hospedada foi removida pela F-012. Entrega aceita por ato humano em 2026-08-23;
F-009 está `DONE`. Contrato e evidência em
[feature.md](../features/F-009-suite-hospedada-sem-aws/feature.md) e
[evidence.md](../features/F-009-suite-hospedada-sem-aws/evidence.md).

F-010 — revisão assistida em lote — nasce em 2026-08-19, por seleção humana, na mesma conversa
da F-009: leitura com tripla concordância (os dois LLMs concordam, o OCR determinístico
confirma, a associação é única e o solver fecha dentro da tolerância) nasce pré-aceita em lote,
e o revisor faz uma conferência e um ato de aprovação no lugar de decisão leitura a leitura. O
gate humano de aprovação e o portão de exportação (`SceneRevision.export_errors()`) permanecem
intocados — o que muda é o ponto de partida da revisão, não quem decide. Depende dos dados reais
da F-009 (upload real corroborado por OCR) para calibrar os limiares de concordância. Ainda sem
Feature Contract: esta linha é o registro canônico até a especificação, e a prioridade é decisão
humana pendente.

F-011 — jornada guiada da revisão — **`DONE` por ato humano em 2026-08-23, sem nunca ter tido
Feature Contract, porque o que ela pedia já existia quando foi registrada.** Nasceu em
2026-08-19, por seleção humana, na primeira revisão da porta nova: o responsável queria a
experiência da revisão como jornada guiada, a próxima tarefa habilitando só quando a atual é
cumprida. A auditoria de 2026-08-23 encontrou isso no ar: `apps/web/src/journey.ts` deriva
quatro etapas — Decisões → Traçado → Aprovação → Exportação —, `JourneyStepStatus` tem
`blocked` com o motivo em língua de obra ("faltam 3 leituras por decidir"), `activeStep` nunca
cai numa etapa bloqueada, e `CroquiApp.tsx` mostra uma etapa por vez. O `deriveJourney` entrou
na tela em **2026-08-17** (`01e5340`, F-003 T14–T16), dois dias **antes** do registro desta
linha.

Fica a lição, que é a mesma já registrada noutro lugar: **conferir se o artefato existe antes
de propor**. O item consumiu um ID e apareceu por quatro dias como trabalho aberto sem sê-lo.
O que permanece de aberto, e é outra coisa: dentro da etapa *Decisões* a tela ainda mostra
todas as cotas de uma vez. Isso não foi pedido aqui e não vira feature sem seleção humana
nova. **Renumerada
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
[ADR-0036](../adr/0036-autorizacao-de-ia-contratual-sem-allowlist-documental.md), **aceito por
ato humano em 2026-08-23**:
o gate de envio a provider pago no caminho hospedado passa a ser integralmente entitlement
contratual ativo do tenant + consent por job + teto de custo por invocação + kill switch, sem
segunda barreira por documento; a allowlist por digest permanece intocada no caminho offline de
eval (`extraction_eval.py`), que não tem tenant nem entitlement. As quatro tarefas do
[plano](../features/F-012-operacao-saas-autorizacao-ia/plan.md) estão completas: a allowlist
saiu do worker e do deploy do HML (T1); `GET /v1/me` e os dois GETs de plataforma
(`/v1/platform/tenants`, `/v1/platform/tenants/{id}/ai-processing-entitlement`) existem, com
snapshot OpenAPI atualizado (T2); a jornada "Plataforma" entrou na SPA — botão condicional ao
papel `platform_operator`, `?plataforma=` fazendo round-trip pelo login, lista de tenants com
ativação/desativação inline e Idempotency-Key nas mutações (T3); e a documentação fecha a
implementação (T4). O PR #20 integrou a entrega na `main` (`345fd2c`), e o caminho hospedado
foi exercitado nas rodadas reais posteriores. Entrega aceita por ato humano em 2026-08-23;
F-012 está `DONE`. Contrato e evidência em
[feature.md](../features/F-012-operacao-saas-autorizacao-ia/feature.md) e
[evidence.md](../features/F-012-operacao-saas-autorizacao-ia/evidence.md).

A F-012 também abriu um inventário de gargalos SaaS ainda sem Feature Contract, registrado
aqui como o registro canônico até a especificação de cada item, todos nascidos em 2026-08-19,
por seleção humana, na mesma conversa: **F-013** UI de membros do tenant (depende do convite da
F-008, `BLOCKED`); **F-014** entidade tenant própria e onboarding self-service (hoje `tenant_id`
só existe no Keycloak e como coluna nas tabelas de domínio); **F-015** recriar o job de upload
existente, sem exigir digest nem allowlist; **F-016** rotação de chaves e segredos de provider;
**F-017** custo agregado por tenant e trilha de auditoria do entitlement, visíveis na própria
tela de plataforma. F-008 permanece `BLOCKED`: o que a impede é a decisão do usuário sobre
provedor de e-mail e domínio remetente, não código.

**Auditoria de 2026-08-23 contra o código**, que encolheu duas destas linhas — o inventário foi
escrito em 2026-08-19 e o produto andou:

- **F-015** perdeu metade da premissa. A allowlist **já saiu** do caminho hospedado: `authorize_page`
  só existe hoje em `services/worker/src/croquito_worker/extraction_eval.py`, que é o caminho
  offline de eval que o ADR-0036 preservou de propósito. O que resta é real e tem trava
  concreta: `jobs.upload_id` é `ForeignKey` **`UNIQUE`**, então um upload já usado não gera
  outro job — e é justamente essa coluna que o [ADR-0049](../adr/0049-evidencia-de-campo-na-revisao-do-escritorio.md)
  decidiu manter como está.
- **F-017** teve a metade do custo entregue pela [F-031](../features/F-031-value-events/feature.md):
  `GET /v1/metrics/summary` já devolve `ai_cost` e `rounds_ai_cost` do tenant. Resta a **trilha
  de auditoria do entitlement na tela**, que o Design Approval Package da
  [F-034](../features/F-034-disponibilidade-de-jornada/feature.md) desenhou como bloco
  **reservado** citando esta feature pelo nome.
- **F-013**, **F-014** e **F-016** seguem intactas e verificadas: não existe tabela `tenants`
  (o `tenant_id` vive no JWT e como coluna nas tabelas de domínio), não há UI de membros, e não
  há mecanismo de rotação de segredo de provider.

F-018 — edição de forma da proposta na UI da revisão — nasce em 2026-08-19, por seleção
humana, na primeira revisão real em nuvem do Guaxindiba V3: o muro com recuo 4,80→3,30
chegou fragmentado da extração paga (duas `line` retas sob `geometry-extraction@2.0.1`), e
a única correção disponível foi trocar o prompt e rerodar o provider — a revisora não tinha
como ajustar vértice ou recuo direto na tela. É mudança de UX na jornada da revisão
(`INTERFACE_CHANGE` na classificação da camada pinada: exigirá Design Approval Package
antes do planejamento). A mesma rodada expôs um achado de mecanismo fora do escopo desta
feature, registrado aqui por não ter destino melhor ainda: quando uma leitura confirmada não
é aplicada, a issue correspondente nasce apenas `warning` e a cena permanece exportável com
a entidade `exact` que ela contradiz — candidato a trabalho no portão de exportação
(`SceneRevision.export_errors()`), com a decisão de virar bloqueio como ato humano pendente.
**Ganhou contrato em 2026-08-23**, por seleção humana, com prioridade `HIGH`. A
especificação fixou o que impedia a feature de ser "deixar editar": proposta é observação de
máquina, e observação não se adultera. A edição **cria proposta nova**, de origem humana,
derivada das originais, que permanecem intactas — mesmo princípio do
[ADR-0019](../adr/0019-proposal-refresh-creates-a-new-review-revision.md). Sem isso a
comparação entre o que o modelo viu e o que a pessoa corrigiu, que é o insumo de toda melhoria
de prompt, some na primeira correção. Três operações: mover vértice, inserir/remover vértice e
**unir fragmentos** — esta última é a que resolve o caso do Guaxindiba. Precisão não sobe pela
edição: forma desenhada à mão nunca vira `exact`. `BLOCKED` por dois gates que precedem o
planejamento (decisão de arquitetura sobre o modelo da proposta de origem humana, e Design
Approval Package). Contrato em
[F-018](../features/F-018-edicao-de-forma-da-proposta/feature.md).

F-019 — preview visual da cena resolvida na revisão — nasce na mesma rodada, 2026-08-19, por
seleção humana: hoje o resultado do traçado só aparece como texto residual (resíduos,
blockers) na tela de revisão, sem a geometria resolvida visível antes do export. A pessoa
aprova uma cena que nunca viu; a primeira imagem da geometria é o render do DXF, **depois** da
aprovação que ela deveria informar.

**Ganhou contrato em 2026-08-23**, por seleção humana, com prioridade `HIGH`. A especificação
achou que a cena está a uma chamada de distância: `GET /v1/jobs/{job_id}/scene` já existe e os
tipos já estão publicados em `@croquito/contracts` — a SPA simplesmente não busca a rota.
Falta desenhar, no cliente, sem render no servidor. É a única feature aberta nesta rodada com
**um** gate só: não cria rota, não muda modelo e não toca o portão de exportação, então não
exige decisão de arquitetura. Cumprido o Design Approval Package, vai direto a
`READY_FOR_PLANNING`. Contrato em
[F-019](../features/F-019-preview-da-cena-resolvida/feature.md).

F-020 — jornada web do orçamento-base — nasce em 2026-08-19, por seleção humana, numa sessão
de revisão visual em que o usuário perguntou se "Medição" era o orçamento. Não era: são dois
momentos do mesmo contexto delimitado, com regras de preço opostas, e só a medição chegou ao
cliente. O orçamento-base existe desde o M8 no domínio, nos importadores e no CLI, e nunca
teve rota `/v1` nem tela — verificado no código e no histórico do Git, não é interface
perdida em migração. A condição que o
[ADR-0027](../adr/0027-price-source-provenance-and-bid-boundary.md) e o bullet 16 desta
seção registravam — "quando houver exemplar real do modelo da prefeitura, como template" —
**foi satisfeita na mesma data**, com o usuário fornecendo o exemplar e confirmando que o
orçamento sai no mesmo layout do boletim. A conferência do arquivo real mostrou que as sete
colunas já estão modeladas como dado no contexto de medição, e que faltam ao layout duas
coisas que o boletim não precisa e o orçamento exige: a coluna de fonte do preço — cuja
informação a proveniência por linha (VAL-09) já carrega — e o BDI, que **não existe em
nenhum arquivo do repositório** e por decisão humana da mesma data entra no escopo, porque
orçamento-base de pré-licitação sem BDI não é submissível. A feature é `INTERFACE_CHANGE` e
exigirá Design Approval Package antes do planejamento; o contrato está em
[F-020](../features/F-020-orcamento-base-web/feature.md), com prioridade `HIGH` por decisão
humana. Segue como dependência externa o arquivo `.DBF` real do catálogo EMOP. Em
2026-08-20 o gate de Design Approval foi exercido — revisão 1 do pacote aprovada, papel de
acesso decidido (reusa o da medição) — e, na mesma data, a implementação inteira (T1–T6:
domínio BDI + contrato gerado, escritor/auditor da planilha, rotas `/v1/estimate-rounds*`,
worker da fila, jornada na SPA, e2e sem CLI) foi integrada e revisada na branch
`f-020-orcamento-web`, levando a feature a `READY_FOR_HUMAN_REVIEW`
([evidência](../features/F-020-orcamento-base-web/evidence.md)). Pendem o aceite do
[ADR-0038](../adr/0038-bdi-como-conceito-de-pre-licitacao.md) (BDI como conceito de
pré-licitação), copy final, conferência contra o exemplar real e o merge.

F-021 — nota pré-classificada na decisão da leitura — e F-022 — Document AI como braço de
OCR — nascem em 2026-08-20, por seleção humana, durante a segunda revisão real do
Guaxindiba. A revisão expôs os dois custos: oito das dez leituras eram grandezas de
elevação que o revisor reclassificou uma a uma como "Anotação da folha", descartando um
sinal (`kind="note"`) que o contrato de extração já emite; e a folha escreve ~16 números
dos quais só 10 viraram leitura — o braço Cloud Vision não alcança a letra manuscrita, e
o `make ocr-eval` sintético não enxerga isso. F-021 transforma o sinal do modelo e o
padrão `h=` em sugestão pré-preenchida mantendo o portão humano; F-022 exerce a escalada
que o [ADR-0035](../adr/0035-suite-hospedada-openai-anthropic-direto.md) registrava
nominalmente, agora como [ADR-0037](../adr/0037-document-ai-como-braco-de-ocr.md)
(Proposed). Contratos em [F-021](../features/F-021-nota-pre-classificada/feature.md) e
[F-022](../features/F-022-document-ai-braco-ocr/feature.md), ambas `HIGH` por decisão
humana. F-018/F-019 permanecem na fila de propósito: o inventário de formas erradas da
próxima rodada real, já com F-021+F-022 no ar, é o insumo dos seus specs.

F-025 — consultor do traçado — nasce em 2026-08-20, na primeira exportação real: a V17
travou em "0 exatos, 11 não aplicadas" por três causas que o solver conhecia e não
contava (formas freeform semeadas por rascunho anterior às decisões; associação herdada
no vizinho da escrita; 1,5 e 8,6 disputando o mesmo vão). O diagnóstico foi feito à mão
reproduzindo o solve localmente; a feature é o solver contar as causas com conserto de
um clique, e o chat da revisão (ADR-0023) como camada de conversa por cima — desenho
proposto pelo usuário: "ao clicar em Aceitar traçado, ver esses erros e corrigir".
Também da mesma sessão: o caminho de aproximação deve se recolher quando o traçado é o
caminho em uso (lista "pendente" gritando à toa — observação para F-011), e a semente
de flags do rascunho deve re-semear quando as decisões mudam. Em 2026-08-20 a feature
foi especificada e planejada por decisão humana (classificação sem Design Approval
Package pelo precedente da F-010; re-semeadura incluída, só de flags não tocados à mão;
disputa de vão com atalhos incluindo manter-separados) — contrato em
[F-025](../features/F-025-consultor-do-tracado/feature.md), prioridade `HIGH`, primeira
da fila combinada F-025 → F-023 → F-019/F-018.

F-023 — Survey Quality Score — nasce em 2026-08-20, por seleção humana, na conversa que
comparou a arquitetura do produto com uma proposta externa: o sistema já sabe quando o
levantamento não sustenta o desenho (blockers, leituras não aplicadas, resíduos,
corroboração), mas não devolve isso como nota com recomendações de campo ("meça a
diagonal A–C"). Sequenciada de propósito DEPOIS da V16: o Document AI muda o que é
"falta de dado", e V14/V15/V16 são as primeiras amostras de calibração. Em
2026-08-20 (mesma data, sessão posterior) a feature foi especificada e planejada por
decisão humana: a fatia 1 liga o motor órfão de fechamento de cadeias de cotas
(`dimension_closure.py`, completo e testado, sem chamadores) ao pipeline, à API e à
tela — incluindo a declaração humana de cadeia, decisão explícita do usuário — e o
score agregado com recomendações de campo fica para as fatias seguintes, calibrado com
V14–V17. Contrato em [F-023](../features/F-023-survey-quality-score/feature.md),
prioridade `HIGH`.

F-028, F-026 e F-027 nascem em 2026-08-20, por seleção humana, na rodada imediatamente
posterior ao merge da [F-020](../features/F-020-orcamento-base-web/feature.md): com a
jornada do orçamento-base no ar, o usuário selecionou as três frentes que a completam.
F-028 nasceu registrada como "F-025" na sessão da rodada do orçamento, em paralelo com a
sessão que registrou F-025 (consultor do traçado) na main; a colisão foi detectada na
integração de 2026-08-20 e o boletim foi renumerado para F-028 — a main é canônica e o
ID que ela publicou primeiro prevalece. Referências históricas a "F-025" em commits da
rodada do orçamento leem-se F-028.
[F-028](../features/F-028-boletim-medicao-web/feature.md) fecha a dívida que a própria
F-020 declarou — aprovação nominal (VAL-05) e exportação `.xlsx` do boletim pela web,
com o mesmo gate auditado que o orçamento já tem; é `INTERFACE_CHANGE`, e a revisão 1
do seu Design Approval Package foi aprovada na mesma data (dois atos explícitos
mantidos), levando-a a `READY_FOR_PLANNING`.
[F-026](../features/F-026-importadores-sinapi-sicro/feature.md) realiza o bullet da
cascata configurável desta seção: SINAPI e SICRO como origens novas de `PriceOrigin`,
um importador por fonte no molde do EMOP
([ADR-0039](../adr/0039-sinapi-sicro-como-origens-de-preco.md), Proposed); sem tela
nova, `READY_FOR_PLANNING`.
[F-027](../features/F-027-modo-teto-orcamento-invertido/feature.md) realiza o bullet do
modo teto (`EstimateTarget` reservado): verba da demanda declarada na rodada e consumo
contra o teto na montagem; especificada em detalhe por último na rodada, com dois gates
antes do planejamento (ADR-0040 da semântica do teto e Design Approval Package).

F-029 — auto-associação de cotas por confiança calibrada — nasce em 2026-08-21, por
seleção humana, na conversa que comparou o produto com uma proposta externa de
"Dimension Association Engine": o gargalo humano da revisão é dizer a qual segmento
cada cota pertence, e hoje 100% das leituras exigem toque duplo (decisão + associação
explícita). A feature realiza o bullet "melhor associação automática entre cotas e
segmentos" da seção de generalização controlada, como **experimento local** (stack
docker-compose, sem HML/GCP): score determinístico com duas confianças distintas
(`reading_confidence` × `association_confidence`), modo shadow sempre computado,
métricas `auto_association_rate`/`review_rate` com eval própria, e modo automático de
leitura + associação atrás de `CROQUITO_AUTO_ASSOCIATION_ENABLED` (default `false`),
com decisão de ator-máquina a nascer como ADR-0041. Três decisões de escopo do usuário
na mesma sessão: o modo automático cobre leitura + associação; a fatia 2 da F-023
(score calibrado com V14–V17) é absorvida por esta feature; a calibração usa
Guaxindiba real + fixtures sintéticas + PDFs de levantamentos fornecidos pelo usuário.
Contrato em [F-029](../features/F-029-auto-associacao-confianca/feature.md),
prioridade `HIGH`.

F-030 — fotos do levantamento na jornada de revisão — nasce na mesma sessão de
2026-08-21, por seleção humana: o levantamento de campo produz fotos junto do croqui,
e a jornada de upload/revisão só recebe o PDF. Foto resolve "o que é" (muro ×
alambrado, portão × detalhe) e corrobora topologia via provider multimodal, mas não
fornece medida (sem escala) — por isso não entra no score determinístico da F-029.

Ganhou contrato em 2026-08-23, por seleção humana, e a especificação corrigiu o tamanho
que este parágrafo supunha. "Upload + storage + retenção + chamada paga" descrevia quatro
coisas, e a F-032 já entregou três: a foto chega com digest e **já ancorada**, o worker
a analisa (`survey_photo_analysis.py`) e `GET /v1/surveys/{id}` já lê com papel de
escritório. O que falta é preciso e menor — a mídia não tem URL para o escritório, o
artefato de análise é **escrito e nunca lido** por nenhuma rota, e nada liga um job ao
levantamento (`survey_export.py` já nomeava a F-030 como quem fecharia isso). Duas
decisões humanas de 2026-08-23: as fotos chegam pelos **dois** caminhos (vínculo e upload
avulso) e a **classificação por IA entra**.

E então uma pergunta mudou o recorte: *as fotos ajudam a identificar melhor as cotas?* Não —
foto não tem escala. Mas a pergunta expôs que o levantamento produz **duas** coisas, e a
outra, a **medida de trena**, toca a cota diretamente: ela é testemunha independente da
prancha, e o que ela tem de valioso é poder **discordar**. Estava presa no mesmo lugar que a
foto. Por decisão humana a feature absorveu as duas, em três fatias — ver, testemunhar,
classificar —, e o **levantamento legado** (sem app, que é de onde vieram Guaxindiba, Toca e
Raul Campelo) passou a ser atendido desde a primeira: o upload avulso vira porta principal, e
o número medido chega escrito na foto do visor da trena, que o passe pago já lê. Ficaram
recusados, com motivo escrito, o PDF como documento de evidência e a síntese de
`SurveyPacket` a partir do croqui legado — o primeiro por **circularidade** (o croqui legado
é a fonte da cota, e testemunharia a si mesmo), o segundo por criar um segundo modelo
geométrico ao lado do `SceneRevision`.

Os dois gates foram **cumpridos em 2026-08-23**: o
[ADR-0049](../adr/0049-evidencia-de-campo-na-revisao-do-escritorio.md) foi **aceito** — o
vínculo é ao job da prancha, porque não existe job sem PDF (`jobs.upload_id` é
`NOT NULL UNIQUE`) — e o Design Approval Package foi primeiro aprovado na revisão 2. A
autorização de implementação emendou o ADR, aprovou a revisão 3 (modal, filtro manual,
múltiplas testemunhas, diferença neutra e observação fora da cena), aprovou o plano e fixou
oito Task Contracts. A feature está `READY_FOR_BUILD`; a rodada paga de seis fotos está
autorizada até US$ 5,00, mas só depois dos gates offline e do recebimento do corpus rotulado.
Contrato em
[F-030](../features/F-030-levantamento-de-campo-na-revisao/feature.md).

F-033 — demanda sob contrato licitado — nasce em 2026-08-21, numa conversa de operação
em que se mapeou a cadeia real das praças (levantamento → DXF → prancha → orçamento →
aprovação → empresa executora). O mapa, registrado em
[Cadeia operacional](CADEIA_OPERACIONAL.md), expôs que o fluxo tem **três** momentos de
preço e o [ADR-0027](../adr/0027-price-source-provenance-and-bid-boundary.md) modela
dois: orçar uma demanda dentro de um contrato guarda-chuva já licitado tem a forma do
orçamento-base e a regra da obra licitada. Hoje nada impede instalar EMOP/SINAPI na
cascata dessa demanda — o orçamento é aprovado, e só na medição
`BULLETIN_PRICE_ORIGIN_FORBIDDEN` recusa o código, sobre serviço já executado. Tem
Feature Contract e está `BLOCKED` por dois gates humanos: a decisão de arquitetura que
refina a fronteira do ADR-0027 (`ARCHITECTURE_DECISION_REQUIRED`) e o Design Approval
Package (`DESIGN_APPROVAL_REQUIRED`), ambos precedendo o planejamento.

F-034 — disponibilidade de jornada por ambiente e por tenant — nasce em 2026-08-22, de uma
pergunta de operação: como impedir que um módulo ainda imaturo (hoje o Croqui) chegue a
homologação, e como depois liberá-lo para um cliente piloto sem liberá-lo para todos. São
duas perguntas de naturezas diferentes — "ainda não está pronto" é condição temporária de
engenharia por ambiente; "este cliente contratou" é decisão comercial duradoura por tenant
— e o produto já resolveu esse mesmo par para o processamento de IA (F-012/ADR-0036). A
feature aplica o par às jornadas, com três estados por ambiente (`enabled`, `pilot`,
`disabled`), entitlement por tenant consultado só em `pilot`, e a resolução das três
perguntas (ambiente, tenant, pessoa) feita no servidor: `GET /v1/me` passa a devolver as
jornadas disponíveis já resolvidas, e a tela renderiza o que recebeu em vez de
reimplementar autorização. Dividida por decisão humana registrada — a fatia 1 não introduz
valor visual novo; a fatia 2, administrar o entitlement na tela de Plataforma, é superfície
nova e ficou `BLOCKED` até o Design Approval Package, **aprovado na mesma data**. **As duas
fatias foram entregues em 2026-08-22** e a **entrega foi aceita por ato humano em
2026-08-23**; o mecanismo está no ar e **dormente**, porque nenhum ambiente declara ainda os
estados de jornada — declará-los é ato de operação, e o aceite não o substitui. Contrato em [F-034](../features/F-034-disponibilidade-de-jornada/feature.md),
evidência em [evidence.md](../features/F-034-disponibilidade-de-jornada/evidence.md).

F-035 e F-036 — aprovação do orçamento e sua ligação com a medição — nascem em 2026-08-22,
de uma conversa de alinhamento sobre a cadeia real, quando ficou visível uma **assimetria**:
a medição tem `POST .../approve` com aprovação nominal registrada, e o orçamento **não tem
aprovação nenhuma**. A cadeia dele termina na planilha. Hoje o gerente aprova fora do
sistema — no e-mail, na reunião —, e o produto não sabe que aquele orçamento foi aprovado,
por quem, nem quando. A F-035 traz esse ato para dentro, no molde do que a medição já faz,
o que a torna barata.

A F-036 é a consequência: quando a obra começa e a medição abre, a rodada de medição **não
herda nada** do orçamento — é criada do zero, com outra prancha, outro catálogo e o
consolidado contratual que o orçamento nem conhece. Nada liga "esta medição mede aquele
orçamento". Não é defeito de implementação: o [ADR-0027](../adr/0027-price-source-provenance-and-bid-boundary.md)
declara que o orçamento não tem contrato nem aprovação. Ligar as duas pontas esbarra na
mesma lacuna que a F-033 deixou aberta — o orçamento não modela contrato como entidade —,
e por isso a F-036 é mais funda que a F-035 e vem depois dela.

As duas nasceram **sem contrato e sem prioridade**, de propósito: a validação com quem está
dentro da prefeitura decidiria se a aprovação precisa ficar registrada no sistema ou se ela
vive bem no processo de fora.

A F-035 saiu desse estado na mesma data, por seleção humana, e ganhou contrato com
prioridade `HIGH`. A conversa de especificação expôs que o problema é mais fundo do que a
falta do registro: `POST .../estimate` **monta e publica o `.xlsx` num ato só**, então não
existe instante em que o orçamento esteja pronto e ainda não despachável — não há o que
aprovar "antes do despacho" porque não há despacho separado. Três decisões humanas de
2026-08-22 fixaram o desenho: portão real em vez de carimbo (separar montar de publicar,
espelhando `calc` → `approve` → `export` da medição), papel `aprovador` novo e distinto de
`orcamentista` com **recusa de auto-aprovação** no código, e despacho por e-mail ou Drive
**fora de escopo** — não há provedor de e-mail, que é o mesmo motivo pelo qual a F-008 está
`BLOCKED` e pelo qual a F-028 deixou o item de fora. Os dois gates humanos que precediam o
planejamento foram cumpridos em 2026-08-22, em atos separados: o
[ADR-0046](../adr/0046-aprovacao-do-orcamento-base.md) foi **aceito** — ele autoriza o
orçamento a ter aprovação própria contra a leitura literal da decisão 6 do ADR-0027 — e o
Design Approval Package foi **aprovado** (revisão 1). A feature foi **executada na mesma data**, das quatro tasks à tela, e
teve a **entrega aceita por ato humano em 2026-08-23**: cinco dos seis guardrails passam a
disparar com teste próprio, o sexto tem teste que prova a inércia declarada, e a cadeia
orçamento → medição fecha no e2e. Faltam merge, deploy e a migração `0016` no hospedado.
Evidência em [evidence.md](../features/F-036-vinculo-orcamento-medicao/evidence.md).
Contrato em [F-035](../features/F-035-aprovacao-do-orcamento/feature.md).

A F-036 saiu desse estado em 2026-08-23, por seleção humana, e ganhou contrato com
prioridade `HIGH`. A conversa de especificação achou o que a leitura anterior não via: o
problema não é principalmente a falta da trilha de auditoria. A rodada de medição da `/v1`
**não tem consolidado contratual nenhum**, e o código diz isso por escrito
(`bulletin_export_contract`) — ele fabrica um consolidado a partir da própria medição, o que
deixa **seis guardrails inertes**: `BALANCE_EXCEEDED`, `CODE_NOT_IN_CONTRACT`,
`PERIOD_NOT_SEQUENTIAL`, `CODE_AMBIGUOUS_IN_CONTRACT`, `LINE_PRICE_NOT_IN_CONTRACT` e
`LINE_UNIT_NOT_IN_CONTRACT` não podem disparar. Para a primeira medição de uma obra orçada
aqui dentro, o orçamento assinado **é** o consolidado que falta.

Duas decisões humanas de 2026-08-23 fixaram o recorte: o vínculo entrega **consolidado
contratual**, não só referência de auditoria; e vale **apenas** sob o regime
`contracted_demand` da F-033, o único em que não há licitação nem deságio entre o orçamento
e o contrato — fora dele, chamar orçamento de contrato seria mentira, e a fronteira do
ADR-0027 continua de pé. Os dois gates humanos que precediam o planejamento foram **cumpridos em
2026-08-23**, em atos separados: o [ADR-0048](../adr/0048-consolidado-contratual-do-orcamento-assinado.md)
foi **aceito** — ele fixa o preço do consolidado sem BDI, a agregação por código e a recusa de
BDI sob o regime, que é um erro de dinheiro existente hoje — e o Design Approval Package foi
**aprovado** (revisão 1). A feature foi **executada na mesma data**, das quatro tasks à tela, e
teve a **entrega aceita por ato humano em 2026-08-23**: cinco dos seis guardrails passam a
disparar com teste próprio, o sexto tem teste que prova a inércia declarada, e a cadeia
orçamento → medição fecha no e2e. Faltam merge, deploy e a migração `0016` no hospedado.
Evidência em [evidence.md](../features/F-036-vinculo-orcamento-medicao/evidence.md). Contrato em
[F-036](../features/F-036-vinculo-orcamento-medicao/feature.md).

F-037 — acervo central de catálogos de preço — nasce em 2026-08-22, na mesma conversa, quando
o dono do produto explicou o rumo: **o sistema deve trazer as tabelas prontas, e o
orçamentista escolher**, como faz o software de orçamento consolidado no mercado. Hoje a
cascata é alimentada por upload de um JSON por rodada — atalho deliberado de fase de teste,
e não o produto: a orçamentista não tem por que saber o que é um JSON de catálogo, e num
contrato guarda-chuva com vinte praças ela sobe o mesmo arquivo vinte vezes. A parte difícil
já existe: `sco.py`, `emop.py`, `sinapi.py` e `sicro.py` leem os quatro formatos e
normalizam para o mesmo `PriceCatalog`, com origem, data-base e digest. O que falta é onde
guardar centralmente, de onde puxar e a tela de escolha.

Duas restrições nascem com ela. A **EMOP é paga** (decisão humana de 2026-08-22, informada
pelo dono do produto), então fica **fora** do acervo central e continua entrando por upload
do próprio cliente — o acervo não distribui tabela que a plataforma não pode distribuir. E o
[ADR-0027](../adr/0027-price-source-provenance-and-bid-boundary.md) decisão 4 já fixou que
cada importação gera catálogo novo amarrado por digest, nunca troca silenciosa de preço:
num acervo central isso vale com mais força, porque uma atualização mudaria preço para todos
os tenants ao mesmo tempo. Selecionada por decisão humana de 2026-08-22 com prioridade
`HIGH` e precedência sobre a F-035, porque o dono quer testar a cadeia com essa parte
funcionando. Contrato em
[F-037](../features/F-037-acervo-de-catalogos/feature.md).
[F-032](../features/F-032-app-levantamento-campo/feature.md) — app de levantamento de
campo — nasce em 2026-08-21, por seleção humana: o levantamento hoje nasce em papel e
todo o pipeline existe para interpretá-lo; a F-032 ataca a ambiguidade na origem, com
coleta estruturada offline-first (PWA em `apps/field`) em que toda medida nasce
vinculada (valor, pontos, elemento, instrumento, evidência) e a validação geométrica
roda ainda no local. O pacote coletado entra no pipeline como observações, sob os
portões do scene graph. Arquitetura no
[ADR-0043](../adr/0043-app-de-campo-pwa-offline-first.md) (aceito por ato humano em 2026-08-21); é
`INTERFACE_CHANGE` e exigirá Design Approval Package antes do planejamento das fatias
de superfície; a fatia 0 (scaffold técnico, sem telas finais) foi autorizada por plano
aprovado pelo usuário na mesma data e executa em branch/worktree própria
(`f-032-app-levantamento-campo`), sem tocar a homologação. O ID salta de F-028 para
F-032 nesta tabela porque F-029, F-030 e F-031 foram reivindicados por sessões
paralelas ainda não integradas à main (F-029/F-030 no checkout de trabalho;
F-031 — eventos de valor — na branch `feat/f-031-value-events`, desde então integradas);
relação direta com a F-030: o app de campo produz as fotos já ancoradas à geometria que
aquela jornada consome, e é dessa entrega que o contrato da F-030 parte.

**F-048, F-049 e F-050** nascem em 2026-09-03, por seleção humana, na mesma conversa: uma
análise do posicionamento da Orvia (orvia.com.br, controladoria independente de obra de alto
padrão privado) mostrou que as entregas que aquele mercado paga como serviço manual — medição
auditada, visão executiva do contrato, matriz de risco mensal — são dados que o croquito já
computa mas ainda não apresenta como produto. Nenhuma das três cria domínio novo. **F-048**
auditoria de medição de terceiros: o `croquito-valuation parity` (fórmula da gramática fechada ×
valor em cache) e o `compare-bulletin` (BM gerado × BM real, linha a linha) já existem como CLI
local e já acharam 8 erros reais de dinheiro num MAPÃO de cliente, mas não há rota `/v1` nem
tela para importar um arquivo externo e devolver o relatório de furos — é o pitch "a
controladora que acha o furo", alinhado à estratégia de vender para empresas de engenharia.
**F-049** dashboard executivo do contrato: o agregado contratual já guarda acumulado e saldo com
validação fechada (`croquito_valuation.contract`, via F-036) e a F-031 publica métricas por job
e por tenant, mas não existe visão de planejado × realizado, acumulado × saldo e avanço
físico-financeiro entre medições; cronograma/SPI ficam explicitamente de fora — a medição do
croquito é físico-financeira, sem noção de tempo planejado. **F-050** relatório de risco e
pendências do período: as pendências hoje são locais — `QuantityDivergence` por item,
`pending_items` por prancha, a flag `boletim vencido` por rodada — e nenhum módulo enumera o
agregado de um período de medição inteiro; a candidata é o documento mensal pronto para o
cliente ao lado do BM. Da mesma análise ficou registrado o que **não** vira feature: BIM/clash
detection (o insumo do croquito é croqui e prancha 2D; o análogo — fechamento de cadeias,
croqui × CAD — já existe), cronograma com caminho crítico, e pós-obra (manutenção/garantias).
O degrau "antes da obra" daquele arco o croquito já cobre: orçamento-base (F-020) e modo teto
(F-027) são a porta de entrada de baixo risco — "comece sabendo o número real".

**F-051** nasce em 2026-09-04 da issue #139, aberta pela primeira revisão completa de croqui
real: a cota-balão (medida escrita longe do elemento, ligada por letra) é inalcançável pelo
funil de proximidade por construção, e o escape `annotation=true` deixa medida confirmada por
humano fora do solver. Dos três caminhos apresentados, o dono escolheu o desenho completo — a
identidade de elemento (`element_ref`, ADR-0058) passa a poder nascer NA REVISÃO, sobre
propostas, pelo mesmo ato humano, e o traçado a transporta para a cena (ADR-0063, `Accepted`
em 2026-09-04). É a ponte que faltava na cadeia croqui→cena→quantitativo da F-047; o Design
Approval Package (revisão 1) foi aprovado na mesma data, com as duas leituras confirmadas.

## Agora — MVP privado

- Golden dataset e eval harness.
- Upload, processamento, revisão e DXF.
- Guaxindiba, Toca e Raul Campelo.
- Dois provedores, Textract e scene graph.
- AWS gerenciada, retenção e observabilidade.

## Próximo — generalização controlada

- Ampliar regressão com documentos autorizados.
- Biblioteca versionada de símbolos e blocos.
- Melhor associação automática entre cotas e segmentos — selecionado em 2026-08-21
  como [F-029](../features/F-029-auto-associacao-confianca/feature.md).
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
  insumos dentro do código de serviço). A relação entre elemento da prancha e código de
  serviço é N:N ([ADR-0053](../adr/0053-cardinalidade-n-n-elemento-servico.md), aceito em
  2026-08-25): um mesmo elemento pode disparar vários códigos e um mesmo código recebe
  parcelas de vários elementos, cada par com sua parcela de quantidade — não é escolher
  execução em vez de mero fornecimento, é um **pacote de serviços**, que a UI deve tornar
  visível. No arquivo real da Toca, `17.23` = `PJ14100500(/)` ("Tela… **Fornecimento** e
  colocação") e `17.25` = `PJ14150203(A)` ("**Alambrado**… estrutura tubular") entram **os
  dois** sobre a mesma área de 783,86 m², ligados por `=F686`, somando 62% do orçamento.
  Item que não está na
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
  prefeitura ficavam para marco futuro, condicionados a haver exemplar real como
  template; a condição foi satisfeita em 2026-08-19 e esse marco virou
  [F-020](../features/F-020-orcamento-base-web/feature.md).

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
| 12 | Agora — medição de obra (contexto valuation, v1 em marcos) / **Obra licitada (medição)**: o contrato manda. O preço SCO é composto (mão de obra e insumos dentro do código de serviço). A relação entre elemento da prancha e código de serviço é N:N ([ADR-0053](../adr/0053-cardinalidade-n-n-elemento-servico.md), aceito em 2026-08-25): um mesmo elemento pode disparar vários códigos e um mesmo código recebe parcelas de vários elementos, cada par com sua parcela de quantidade — não é escolher execução em vez de mero fornecimento, é um **pacote de serviços**, que a UI deve tornar visível. No arquivo real da Toca, `17.23` = `PJ14100500(/)` ("Tela… **Fornecimento** e colocação") e `17.25` = `PJ14150203(A)` ("**Alambrado**… estrutura tubular") entram **os dois** sobre a mesma área de 783,86 m², ligados por `=F686`, somando 62% do orçamento. Item que não está na lista SCO/contrato **não pode** vir de outra tabela: o caminho é **aditivo de contrato** (RE-RA) solicitando a inclusão — o sistema deve detectar esses itens e produzir o **dossiê do aditivo** (item, quantitativo, justificativa), nunca precificar por fora. Criação/gestão de RE-RA segue no item abaixo. | EM OPERAÇÃO/HOMOLOGAÇÃO | [Status](../STATUS.md), [ADR-0027](../adr/0027-price-source-provenance-and-bid-boundary.md) | M8 está entregue em código; o primeiro dossiê real depende da rodada homologada. |
| 13 | Agora — medição de obra (contexto valuation, v1 em marcos) / **Pré-licitação (orçamento-base)**: aí sim vale a cadeia **SCO → EMOP → composição manual**. Importador da tabela EMOP como segundo catálogo com proveniência (`PriceCatalogEntry.origin` vira dado; catálogo digital oficial é **pago** via GRE, em .DBF, com sincronização mensal possível por rotina — nova versão com data-base própria, nunca troca silenciosa de preço), e composição com coeficientes declarados (item → várias linhas: horas, insumos). É o coração do "gerador de orçamento" da fase 1 da visão de produto. | EM OPERAÇÃO/HOMOLOGAÇÃO | [Status](../STATUS.md), [ADR-0027](../adr/0027-price-source-provenance-and-bid-boundary.md) | Caminho offline existe; importação do catálogo EMOP real depende de assinatura GRE. |
| 14 | Agora — medição de obra (contexto valuation, v1 em marcos) / **M6 — UI web de homologação da medição** (priorizado pelo usuário em 2026-08-13): revisão do takeoff, shortlist com descrição completa do catálogo, confirmação de código e boletim — o ato humano da orçamentista numa tela, não no CLI. Destrava a homologação da cadeia existente; a rodada real da Toca está estacionada no elo da confirmação até este marco. | EM OPERAÇÃO/HOMOLOGAÇÃO | [Status](../STATUS.md), [ADR-0020](../adr/0020-local-homologation-server-for-valuation.md) | Mecanismo está entregue; o Status mantém ato humano de homologação como pendência. |
| 15 | Agora — medição de obra (contexto valuation, v1 em marcos) / **M7 — matcher híbrido de código SCO** (priorizado pelo usuário em 2026-08-13, durante a homologação: "não posso correr o risco de o código ter no SCO e não fazer o match"): léxico com radical conservador + sinônimos de domínio como dado, retrieval semântico por embeddings do catálogo (dado público SCO; índice local por digest) com fusão de ranking, e a garantia virando gate de eval — golden set com `recall@20 = 100%`. Candidatos sempre com origem e score declarados; confirmar segue ato humano; sem chave/teto, o léxico permanece como fallback funcional declarado. | EM OPERAÇÃO/HOMOLOGAÇÃO | [Status](../STATUS.md), [ADR-0021](../adr/0021-hybrid-sco-code-retrieval.md) | Eval e mecanismo estão documentados; confirmação de código continua ato humano. |
| 16 | Agora — medição de obra (contexto valuation, v1 em marcos) / **M8 — fronteira licitada × pré-licitação** (entregue em código em 2026-08-17, [ADR-0027](../adr/0027-price-source-provenance-and-bid-boundary.md)): dossiê do aditivo como artefato de fechamento da rodada licitada (VAL-08); `PriceOrigin` + importador EMOP offline (.DBF com layout como dado; o arquivo real depende da assinatura GRE) + guardrail `BULLETIN_PRICE_ORIGIN_FORBIDDEN`; composição manual compilada a catálogo e orçamento-base (`build-estimate`) com cascata declarada e proveniência por linha (VAL-09). A UI do orçamento-base e o `.xlsx` no modelo da prefeitura ficavam para marco futuro, condicionados a haver exemplar real como template. | EM OPERAÇÃO/HOMOLOGAÇÃO | [Status](../STATUS.md), [ADR-0027](../adr/0027-price-source-provenance-and-bid-boundary.md) | Entregue em código; validações com fontes reais permanecem pendentes. A condição do exemplar real foi satisfeita em 2026-08-19 e a UI + `.xlsx` viraram [F-020](../features/F-020-orcamento-base-web/feature.md), que acrescenta a coluna de fonte e o BDI. |
| 17 | Próximo — medição além do v1 / Modo teto / orçamento invertido ("escopo dentro de R$ X" da relação de demanda); porta: `EstimateTarget` reservado no glossário do contexto. | PLANEJADO | [Roadmap](ROADMAP.md) | Declarado fora do v1 como extensão futura; a porta `EstimateTarget` é reserva de glossário, não mecanismo entregue. |
| 18 | Próximo — medição além do v1 / Composição própria como caminho de escrita para item sem preço de referência; porta: `PriceCatalogEntry.origin`. | PLANEJADO | [Roadmap](ROADMAP.md), [ADR-0027](../adr/0027-price-source-provenance-and-bid-boundary.md), [Status](../STATUS.md) | O bullet pede a composição própria **como caminho de escrita** para item sem preço de referência. O M8 entregou a composição compilada a catálogo `origin=composition` para o orçamento-base (ADR-0027, decisão 5); na medição licitada esse caminho segue fechado pelo guardrail `BULLETIN_PRICE_ORIGIN_FORBIDDEN` (ADR-0027, decisão 2). O escopo do bullet completo permanece não entregue. |
| 19 | Próximo — medição além do v1 / Quantitativo automático derivado do scene graph aprovado; porta: `TakeoffItem.source` discriminado + `QuantitySource` lendo o `quantitativos.csv` do export DXF. Depende de identidade estruturada de elemento nas entidades (hoje rótulo é texto livre). | DONE | [Roadmap](ROADMAP.md), [ADR-0058](../adr/0058-quantitativo-derivado-do-scene-graph-e-identidade-de-elemento.md) | Registrado como [issue #102](https://github.com/biahflow/croquito/issues/102). O bloqueio nomeado — identidade estruturada de elemento — é o objeto do [ADR-0058](../adr/0058-quantitativo-derivado-do-scene-graph-e-identidade-de-elemento.md), que propõe `Entity.element_ref` atribuído por ato humano na revisão e a divergência cena×legenda como diagnóstico, nunca sobrescrita. O ADR está `Proposed` e **aguarda aceite humano** antes do planejamento. A [F-047](../features/F-047-quantitativo-da-cena-aprovada/feature.md) o construiu e está na `main` desde 2026-08-29 (PR #126): `Entity.element_ref` atribuído por ato humano na revisão, `QuantitySource` atravessando a fronteira das duas jornadas, e a divergência cena×legenda como diagnóstico com tolerância nomeada — nunca sobrescrita. **Aceita por ato humano em 2026-09-02**, o que fecha a issue #102; fica escrito como dívida que nenhum croqui real chegou à medição sem redigitação — o aceite é sobre o mecanismo. |
| 20 | Próximo — medição além do v1 / Criação e gestão de re-ratificações (RE-RA); no v1 elas são apenas lidas para o cálculo de saldo. | DONE | [Roadmap](ROADMAP.md), [F-040](../features/F-040-re-ra-e-medicao-seguinte/feature.md), [ADR-0056](../adr/0056-re-ra-declarada-e-o-consolidado-da-medicao-seguinte.md) | O efeito da RE-RA sobre o saldo já está entregue e validado desde o M8 (`validate_amendments`); o que falta é procedência, caminho de criação e a **medição seguinte**, que não existe na `/v1` — sem ela a RE-RA só seria declarável no período 1. A [F-040](../features/F-040-re-ra-e-medicao-seguinte/feature.md) ataca os três, e o ADR-0056 aguarda aceite humano. A [F-040](../features/F-040-re-ra-e-medicao-seguinte/feature.md) entregou os três: o ADR-0056 foi aceito, o código está na `main` (PRs #109, #112 e #113) e a T6/T7 — a porta da medição seguinte, a herança, e a prévia calculada pelo servidor — entrou na `main` pelo PR #129, com os seis estados recapturados em 2026-09-01. **Aceita por ato humano em 2026-09-02**, o que fecha a issue #100; fica escrito como dívida que nenhuma medição real com contrato re-ratificado atravessou — o aceite é sobre o mecanismo. |
| 21 | Próximo — medição além do v1 / Reajuste de preços entre medições (data-base móvel). | PLANEJADO | [Roadmap](ROADMAP.md) | Declarado fora do v1 como extensão futura. |
| 22 | Próximo — medição além do v1 / UI web de revisão da medição (v1 é CLI-first, como o resto do produto). | PLANEJADO | [Roadmap](ROADMAP.md), [ADR-0020](../adr/0020-local-homologation-server-for-valuation.md), [ADR-0026](../adr/0026-medicao-hospedada-sessao-autenticada-minima.md), [Status](../STATUS.md) | O M6 entregou `apps/medicao` com tela de revisão do takeoff (ADR-0020, ADR-0026), que o Status declara ponte descartável até a migração da medição para a API `/v1` autenticada. O bullet completo qualifica o v1 como CLI-first; se o M6 já o satisfaz é decisão humana pendente, registrada em [evidence.md](../features/F-001-roadmap-clarification/evidence.md). |
| 23 | Próximo — medição além do v1 / Múltiplas pranchas por praça na extração de legenda. | DONE | [Roadmap](ROADMAP.md), [ADR-0057](../adr/0057-multiplas-pranchas-por-praca-na-extracao-de-legenda.md) | Registrado como [issue #101](https://github.com/biahflow/croquito/issues/101). O [ADR-0057](../adr/0057-multiplas-pranchas-por-praca-na-extracao-de-legenda.md) propõe manter a prancha como unidade de evidência e criar o consolidado de obra `WorksiteTakeoff` acima dela, com item repetido entre folhas contando como dois até uma declaração humana de identidade os fundir. O ADR está `Proposed` e **aguarda aceite humano** antes do planejamento. A [F-046](../features/F-046-praca-de-varias-pranchas/feature.md) o construiu e está na `main` desde 2026-08-29 (PRs #125, #127 e #128): a prancha continua sendo a unidade de evidência, o consolidado `WorksiteTakeoff` fica acima dela, e item repetido entre folhas conta como dois até a declaração humana de identidade os fundir. **Aceita por ato humano em 2026-09-02**, o que fecha a issue #101; fica escrito como dívida que nenhuma praça real de mais de uma folha atravessou — o aceite é sobre o mecanismo. |
| 24 | Próximo — medição além do v1 / Cascata configurável de fontes de preço além do SCO (SINAPI, SICRO, tabelas estaduais), cada fonte com importador próprio — tabela de preços é dado, não código. | PLANEJADO | [Roadmap](ROADMAP.md), [ADR-0027](../adr/0027-price-source-provenance-and-bid-boundary.md), [Status](../STATUS.md) | O M8 entregou a cascata de fontes declarada como dado e o importador EMOP `.DBF` (ADR-0027, decisões 4 e 6), com o arquivo real dependente da assinatura GRE. SINAPI e SICRO ganharam importador próprio na [F-026](../features/F-026-importadores-sinapi-sicro/feature.md) (`sinapi.py`, `sicro.py`), o que fecha as fontes citadas nominalmente pelo bullet; o que **permanece** aberto é a distribuição dessas tabelas ao usuário, hoje por upload de arquivo — tratada na [F-037](../features/F-037-acervo-de-catalogos/feature.md). |
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
