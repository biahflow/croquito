# ADR-0035: Suite hospedada de providers — OpenAI e Anthropic diretos, sem AWS

Status: Proposed
Data: 2026-08-19
Responsável: Engineering / AI Engineering

## Contexto

A homologação hospedada roda em GCP, não em AWS ([ADR-0025](0025-homologacao-em-gcp-cloud-run.md)).
As credenciais disponíveis no ambiente publicado são as chaves diretas de API da OpenAI e da
Anthropic; não existe conta AWS configurada para o projeto `biahflow-hml`, e as variáveis
`AWS_ACCESS_KEY_ID`/`AWS_SECRET_ACCESS_KEY` presentes ali são as chaves HMAC do storage
interoperável com S3 (GCS), não credencial de Bedrock ou Textract.

O [ADR-0002](0002-aws-managed-architecture.md) escolheu Bedrock e Textract dentro de um desenho
de produção em AWS `sa-east-1` que **nunca foi o ambiente publicado**: nenhuma chamada real a
Bedrock ou Textract jamais saiu deste repositório, e todas as evals pagas realizadas até aqui
(Toca, medição, contrato de arco — ver [Model Routing](../ai/MODEL_ROUTING.md)) usaram OpenAI e
Anthropic por API direta.

O diagnóstico de 2026-08-19 (upload real no HML preso em `JOB_NOT_READY`, investigado na F-009)
encontrou três defeitos latentes na suite hospedada, verificados no código antes desta decisão:

- `build_real_provider_suite` montava braços Bedrock/Textract via `boto3` **sem credencial
  explícita** — o caminho AWS nunca rodou; com `CROQUITO_REAL_PROVIDERS_ENABLED` ligado no HML,
  a suite quebraria na primeira chamada, não na construção.
- A chamada de OCR do Textract no snapshot de revisão era **código morto**: executava, validava
  o schema da resposta e descartava o resultado (`provider_review.py:184-190` antes da T1). O
  fallback `OCR_EVIDENCE_MISSING`, documentado em `MODEL_ROUTING.md`, nunca havia sido
  implementado — divergência doc×código resolvida a favor da realidade nesta entrega, não
  silenciosamente escolhida.
- Não existia fallback provider→provider: falha permanente de um braço derrubava o job inteiro
  para reentrega, mesmo quando o outro braço estava saudável.

Esta decisão registra o que a F-009 (T1–T3) implementou para fechar esses três defeitos: uma
suite hospedada honesta, sem AWS, com fallback transparente e um braço de OCR determinístico
próprio do GCP.

## Decisão

**D1. A suite hospedada tem três braços: `openai`, `anthropic` e `ocr`.** `ProviderSuite` perde
os campos `bedrock_anthropic` e `textract` (as classes dos dois adapters permanecem no módulo,
usadas por `build_extraction_arm`, a via de eval por linha de comando, e por teste direto — não
são removidas, apenas deixam de compor a suite hospedada). `build_real_provider_suite` não
importa `boto3`: o braço `openai` usa `OpenAIProviderAdapter` com `CROQUITO_OPENAI_API_KEY`; o
braço `anthropic` usa `AnthropicProviderAdapter` com `CROQUITO_ANTHROPIC_API_KEY`
(`claude-opus-5` como default de modelo); ausência de qualquer uma das duas chaves levanta
`ValueError` nomeando a variável, antes de qualquer chamada de rede.

**D2. Anthropic é o braço primário; OpenAI é reserva e contraparte da comparação dupla.** O
helper `_execute_with_fallback` (`provider_review.py`) executa no braço primário e só chama o
reserva depois de falha permanente (retentativa transitória já se esgotou no
`RetryingProviderAdapter` antes de chegar aqui). A degradação nunca é silenciosa: entra a nota
`PROVIDER_FALLBACK_PAGE_SURVEY_OPENAI` ou `PROVIDER_FALLBACK_GEOMETRY_EXTRACTION_OPENAI` nas
`safety_notes` do pacote. A extração de medida (`MEASUREMENT_EXTRACTION`) é comparação dupla
verdadeira, não fallback: os dois braços são chamados sempre que possível, e o pacote registra
qual sobreviveu. Quando só um braço de extração sobrevive, toda leitura nasce `AMBIGUOUS` (nunca
`PROPOSED`) e a nota `PROVIDER_FALLBACK_SINGLE_EXTRACTOR_ANTHROPIC`/`_OPENAI` nomeia quem
respondeu. `BUDGET_EXCEEDED` nunca aciona fallback nem é absorvido em modo degradado — o teto é
da rodada, não do braço, e re-levanta antes de qualquer chamada de reserva. Quando os dois braços
de extração falham, a exceção do segundo braço propaga e o job falha para reentrega — devolver um
pacote vazio seria menos honesto do que reentregar.

**D3. O braço `ocr` é Cloud Vision (`document text detection`), sempre presente na suite real, e
corrobora cada leitura por documento — não substitui o Textract com outro fornecedor equivalente,
implementa a corroboração que nunca existiu.** `GcpVisionOcrAdapter`
(`ProviderName.GCP_VISION`) autentica por Application Default Credentials (a service account de
runtime do worker), chama `images:annotate` uma vez por documento — só quando há alguma leitura
do LLM para conferir, nunca à toa — e reserva no **mesmo** `CostBudget` da rodada, sob
`CROQUITO_AI_ESTIMATED_COST_PER_OCR_CALL_USD` (default `0.0015`). Por leitura, a corroboração
compara texto normalizado (`strip`, colapso de espaço, vírgula→ponto) **e** interseção espacial
de bbox contra as linhas do OCR — nunca só texto, para não confirmar por coincidência de dígitos
repetidos na prancha — e grava `READING_{n}_OCR_CONFIRMED` ou `READING_{n}_OCR_EVIDENCE_MISSING`
nas `safety_notes`, sem nunca rebaixar o `status` já calculado da leitura (calibrar o status pela
confirmação de OCR é escopo da F-010, registrada abaixo). `suite.ocr is None` ou falha permanente
do braço somam **uma** nota única `OCR_UNAVAILABLE`, sem nota por leitura, e o pacote segue
normal — degradação declarada, nunca job derrubado por falta de OCR.
`BUDGET_EXCEEDED` do OCR propaga como qualquer outra chamada do job, pela mesma razão de D2.

**D4. Rótulos honestos.** `dataset_id` do snapshot é `f"job-{job_id}"` — identifica o documento
do job, não a origem das respostas (revisões já gravadas antes da T1 mantêm o rótulo antigo,
nenhum caminho reescreve o passado). `created_by` distingue a origem real da suite:
`"hosted-provider-extraction-v1"` quando construída por `build_real_provider_suite`,
`"offline-provider-contract-fixture"` quando injetada por fixture (teste/demo). O registro de
autorização contratual do tenant (`providers_json`) passa a listar `["openai", "anthropic"]` —
**não** inclui `"ocr"`/`"gcp_vision"`: o braço de OCR é suporte determinístico sempre ligado
quando a suite real é construída, não um provider de LLM que o tenant consente por si (decisão
de produto registrada aqui, não implícita; se o produto decidir tratá-lo como provider
consentível, é mudança de escopo com decisão própria).

**D5. Falha de credencial não é retentável.** `_failure_from_http_status`, compartilhado por
todos os adapters REST deste arquivo (OpenAI, Anthropic, Cloud Vision), mapeia HTTP 401 e 403
para `ProviderFailureCode.REFUSED` — fora de `RetryingProviderAdapter.RETRYABLE`. Chave inválida
falha em uma única tentativa, não em três; 429 continua `RATE_LIMITED` e o resto `UNAVAILABLE`,
ambos retentáveis.

**D6. Teto compartilhado por rodada, allowlist por digest, kill switch por flag.** O deploy do
HML fixa `CROQUITO_AI_MAX_ESTIMATED_COST_USD=5.00` (teto por invocação do worker, não por dia
nem por job — uma reentrega do Pub/Sub multiplica o gasto potencial pelo número de tentativas, e
a fila tem até 5 antes da DLQ). `CROQUITO_AI_EXTRACTION_ALLOWED_DIGESTS` nasce vazio no workflow
— fail closed: nenhum documento sai para provider até um humano registrar o `sha256` do PDF
autorizado. `CROQUITO_REAL_PROVIDERS_ENABLED=false` continua sendo o kill switch: desligar essa
flag basta para nenhuma chamada paga sair, sem redeploy de código.

## Alternativas

- **Vertex AI para os modelos Claude/Gemini.** Preço por token equivalente ao caminho direto;
  os ganhos (billing consolidado, VPC-SC, quota compartilhada) são relevantes só em cenário
  enterprise, que o HML não é. Rejeitada por agora; caminho aberto se produção um dia exigir
  perímetro de rede único no GCP.
- **Google Document AI no lugar de Cloud Vision para o braço de OCR.** Registrada como
  **escalada**, não como alternativa descartada: se o eval de recall de corroboração
  (`make ocr-eval`) reprovar contra uma prancha real (a fixture sintética da T3 mede recall
  100%, mas não é evidência sobre letra manuscrita/impressa real), Document AI é o próximo
  candidato — decisão do usuário registrada em 2026-08-19.
- **Manter Bedrock/Textract como suite real, corrigindo só a credencial.** Rejeitada: exigiria
  provisionar conta e credencial AWS no projeto GCP do HML só para replicar um caminho que nunca
  rodou, quando OpenAI e Anthropic diretos já são as vias validadas por toda eval paga anterior
  deste repositório.

## Consequências

### Positivas

- A suite hospedada deixa de depender de AWS: o upload real no HML pode atravessar a cadeia
  inteira (providers → pacote de revisão → solver → aprovação → DXF) sem uma credencial que
  nunca existiu no ambiente.
- Falha permanente de um braço deixa de derrubar o job inteiro — degrada com nota visível, em vez
  de forçar reentrega para um cenário que o fallback já resolveria.
- Cada leitura ganha uma segunda fonte de evidência independente dos dois LLMs (Cloud Vision),
  sem custo por chamada isolada por leitura (uma chamada por documento).
- Rótulos de auditoria (`dataset_id`, `created_by`, `providers_json`) passam a descrever a
  origem real da revisão, fechando uma lacuna que existia desde antes da T1.

### Negativas

- **Revisita parcialmente o [ADR-0002](0002-aws-managed-architecture.md).** A decisão de
  produção em AWS gerenciada **não é substituída** — ela permanece `Accepted` e aberta para
  quando produção existir. O que esta entrega estabelece é que a suite **hospedada** (HML) não
  depende de AWS; se produção um dia migrar para AWS, religar Bedrock/Textract é decisão nova,
  com eval comparativa própria (o Sonnet e o Opus já divergem por tarefa nas evals existentes —
  ver `MODEL_ROUTING.md`).
- Custo de reentrega: o teto de `CROQUITO_AI_MAX_ESTIMATED_COST_USD` é por invocação do worker,
  não por job. No pior caso — 5 entregas até a DLQ — o gasto potencial de um único job é até
  **5× o teto configurado**.
- Respostas brutas de provider (inclusive do braço `ocr`) continuam retidas por 7 dias no bucket
  `croquito-hml-artifacts`, agora com a `lifecycle_rule` correspondente aplicada no Terraform
  (fechando uma lacuna que `docs/security/DATA_RETENTION.md` já prometia e o bucket não
  cumpria).
- O braço Anthropic ganha timeout default de 60s contra 30s do braço OpenAI (mesmo default do
  `AnthropicProviderAdapter` e de `build_extraction_arm` em toda outra via do repositório;
  `CROQUITO_PROVIDER_TIMEOUT_SECONDS`, quando definida, unifica os dois).

## Pendências registradas

- Rota de plataforma dedicada para administrar a allowlist de digest (hoje é variável do
  workflow de deploy, editada por PR).
- Multi-página: o piloto processa só a primeira página do documento.
- Pacote só-CV (sem chamada a LLM) permanece fora de escopo desta suite.
- UX do `JOB_NOT_READY` no front, que motivou o diagnóstico original desta feature.
- Roteamento por tarefa dentro do braço Anthropic (hoje um modelo único, `claude-opus-5`, para
  todas as tarefas do braço).
- Eval comparativa do braço OpenAI de extração de geometria (a decisão de roteamento de
  `MODEL_ROUTING.md` para geometria vem de eval só com Anthropic/Bedrock).
- `make extraction-eval` continua com default de arm `bedrock:...`, herdado do desenho anterior;
  não ajustado por esta entrega.
- **F-010 — revisão assistida em lote**, aprovada por ato humano em 2026-08-19: leitura com
  tripla concordância (os dois LLMs concordam, OCR confirma, associação única, solver fecha
  dentro da tolerância) nasce pré-aceita em lote, com um ato de conferência e aprovação do
  revisor no lugar de decisão leitura a leitura. Depende dos dados reais desta entrega para
  calibrar os limiares; especificação futura, registrada no
  [Roadmap](../product/ROADMAP.md).

## Riscos e mitigação

| Risco | Mitigação |
|---|---|
| Granularidade de "linha" do OCR é o parágrafo do `fullTextAnnotation`, não a reconstrução por `detectedBreak` símbolo a símbolo | Aceitável para cotas curtas (uma ou poucas palavras); se `make ocr-eval` contra prancha real mostrar recall baixo, é o primeiro lugar a revisar (risco registrado na T3) |
| Erro embutido no corpo 200 do Cloud Vision (`responses[0].error`) sempre mapeia para `UNAVAILABLE` (retentável) | Mesmo tratamento já usado para exceções de client do Textract; sem tabela de `error.code` do Vision para diferenciar permanente de transitório nesta entrega |
| Reentrega multiplica custo: pior caso 5× o teto por job | Teto por invocação é intencional (barato de auditar); DLQ em 5 tentativas é o limite superior conhecido, sem mudança nesta entrega |
| `TF_VAR_openai_api_key`/`TF_VAR_anthropic_api_key` chegam como string vazia se o GitHub Actions secret existir mas estiver vazio (Terraform não falha por variável ausente nesse caso) | Confirmar valor não vazio ao criar os secrets (runbook em [HML](../operations/HML.md)); risco registrado na T5, sem mecanismo automático de detecção ainda |
| Primeiro `apply` do stack `hml_croquito` falhou com 403 ao tentar habilitar `vision.googleapis.com` (a SA `infra-deploy` não tinha `serviceusage.services.enable`) | PR biahflow/infra#15 concede `roles/serviceusage.serviceUsageAdmin`; ato humano pendente é mergear e re-rodar o apply que falhou |
| `providers.json` do braço Anthropic real nunca chamou a API de verdade neste repositório (só testado com `http_post` injetado) | Primeira chamada paga é ato humano do runbook, depois da infraestrutura concluída |

## Rastreabilidade

- Requirements: FR-001, NFR-REL-004 (degradação de OCR/LLM com issue, sem corrupção de estado —
  redigida para Textract, o comportamento real agora é o braço Cloud Vision), NFR-QUAL-003
  (proveniência por chamada), NFR-QUAL-004 (eval comparativa antes de mudar roteamento),
  NFR-SEC-004 (retenção de 7 dias), NFR-SEC-005 (nenhum segredo/URL assinada em log),
  NFR-OPS-002 (custo estimado e alerta de budget).
- Decisões relacionadas: [ADR-0002](0002-aws-managed-architecture.md) (revisitado parcialmente,
  não substituído — ver Consequências), [ADR-0004](0004-dual-model-provider-strategy.md) (dois
  provedores multimodais, estratégia preservada com braços diferentes), [ADR-0008](0008-global-ai-processing-and-retention.md)
  (processamento global e retenção), [ADR-0012](0012-contractual-ai-processing-entitlements.md)
  (autorização contratual por tenant — `providers_json` desta entrega é o dado que ele
  governa), [ADR-0025](0025-homologacao-em-gcp-cloud-run.md) (ambiente hospedado em GCP, o
  contexto que motiva esta decisão), [ADR-0031](0031-segredo-de-homologacao-gerenciado-por-terraform.md)
  (segredo de homologação por Terraform — o mesmo caminho write-only serve as duas chaves de
  provider).
- Especificação e execução na feature
  [F-009](../features/F-009-suite-hospedada-sem-aws/feature.md); tarefas T1–T3 implementaram o
  que este ADR descreve, T5 preparou o deploy. A entrada na
  [matriz de rastreabilidade](../engineering/TRACEABILITY.md) é criada junto da implementação
  aceita.
- Supersedes: none
- Superseded by: none
