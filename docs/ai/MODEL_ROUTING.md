# Roteamento de modelos

Status: Accepted for MVP  
Responsável: AI Engineering / Platform  
Última revisão: 2026-09-04 (timeout default dos braços LLM subiu de 60/30s para 120s e o
teto de custo passou a exigir `(tentativas + 1) × reserva` — issue #137. Antes, 2026-09-03:
o OCR passou a ser a primeira chamada do snapshot e a decidir a orientação da folha — ver
"Orientação da folha"; issue #138. Antes, 2026-08-23: `field-photo-classification@1.0.0`,
F-030 T6, adicionada como rota Anthropic sem fallback; rodada real pendente do corpus
humano)

## Rotas padrão

A suite hospedada usada pelo worker (`build_real_provider_suite`) tem três braços diretos, sem
Bedrock nem Textract — o caminho AWS nunca rodou no ambiente publicado (GCP,
[ADR-0025](../adr/0025-homologacao-em-gcp-cloud-run.md)), decisão registrada em
[ADR-0035](../adr/0035-suite-hospedada-openai-anthropic-direto.md).

| Papel | Provedor/modelo | Execução |
|---|---|---|
| Extração — braço primário | Anthropic API direta `claude-opus-5` (`CROQUITO_ANTHROPIC_MODEL`) | page survey, extração de geometria, e um dos dois lados da extração de medida |
| Extração — braço reserva/contraparte (opcional) | OpenAI `gpt-5.6-terra` (`CROQUITO_OPENAI_MODEL`), ligado/desligado por `CROQUITO_OPENAI_ARM_ENABLED` | contraparte da comparação dupla de medida; assume por fallback quando o braço primário falha de forma permanente em survey/geometria |
| OCR auxiliar | Google Cloud Vision, `document text detection` (`GcpVisionOcrAdapter`, `ProviderName.GCP_VISION`) por padrão; Google Document AI (`GcpDocumentAiOcrAdapter`, `ProviderName.GCP_DOCUMENT_AI`) quando `CROQUITO_DOCAI_PROCESSOR` está definido — escalada nomeada em [ADR-0037](../adr/0037-document-ai-como-braco-de-ocr.md) | **primeira** chamada do snapshot: decide a orientação da folha e corrobora cada leitura de medida extraída; uma chamada por documento, não por leitura |
| Leitura de foto de campo (`field-photo-reading`, F-032) — mesmos braços de visão | primário Anthropic `claude-opus-5`; reserva OpenAI `gpt-5.6-terra` quando o braço está ligado | uma chamada por foto confirmada, depois do passe offline de qualidade; transcreve só o que está ESCRITO na foto (placa, anotação, visor), sem coordenada e sem medida derivada |
| Classificação visual de campo (`field-photo-classification`, F-030) | somente Anthropic `claude-opus-5`; sem fallback OpenAI | uma chamada por foto e somente sob pedido explícito; categoria fechada, descrição e topologia não geométrica em rascunho, nunca medida, cena ou decisão humana |
| Transcrição de nota de voz (`audio-transcription`, F-032) — braço próprio, fornecedor próprio | primário **provisório** Groq `whisper-large-v3-turbo` (`CROQUITO_GROQ_TRANSCRIPTION_MODEL`), escolhido por `CROQUITO_TRANSCRIPTION_PRIMARY` (default `groq`); reserva DESLIGADO por default (`CROQUITO_TRANSCRIPTION_FALLBACK`, default `none`; aceita `openai`, que usa `CROQUITO_OPENAI_TRANSCRIPTION_MODEL`, default `whisper-1`) | uma chamada por nota de voz confirmada; produz RASCUNHO (`status: "draft"`) num artefato próprio, sem medida estruturada e sem confirmar nada |

A tarefa `field-photo-classification` nasce em `field-photo-classification@1.0.0`. Seu
schema admite somente `MURO | ALAMBRADO | PORTAO | PATAMAR | EQUIPAMENTOS | DETALHES |
UNKNOWN`, descrição curta, observações topológicas não geométricas e confiança ordinal. Ela
não participa da estratégia geral de fallback: o candidato aprovado para a rodada é
Anthropic `claude-opus-5`, e o runner usa o braço direto sem retry para garantir uma única
chamada por item. O protocolo é `make field-photo-classification-eval` offline e, após o gate
humano do corpus, `make field-photo-classification-eval LIVE=1 CORPUS=<fora-do-git>/corpus.json`
com OpenAI explicitamente desligado, reserva de US$ 0,75 por chamada e teto absoluto de
US$ 5,00. São seis fotos próprias, 6/6 schema e lineage, 6/6 sem inferência geométrica,
categoria correta em ao menos 5/6 e zero erro com confiança alta; a rodada não é repetida
para escolher resultado melhor.

A tarefa `field-photo-reading` nasce em `field-photo-reading@1.0.0` e é a única com template em
português — o que se pede é transcrição literal do que está escrito em português na praça, e
instruir em inglês convidaria à tradução, que altera a evidência. **A calibração do prompt e
dos limiares de qualidade do passe offline é trabalho de eval futura**: nenhuma rodada paga a
exercitou até esta revisão, e o gate correspondente ainda não existe em
[Evaluation Strategy](EVALUATION_STRATEGY.md). Ela segue o mesmo fallback declarado das demais
tarefas de escolha simples (nota `PROVIDER_FALLBACK_FIELD_PHOTO_READING_OPENAI` no artefato de
análise quando o reserva assume; `BUDGET_EXCEEDED` nunca aciona o reserva) e o mesmo teto de
gasto. Duas diferenças de operação, ambas deliberadas: o portão é o entitlement contratual do
TENANT — levantamento não tem `job_id`, então não há consentimento por job a consultar —, e a
falha da chamada não derruba o comando: o artefato de análise é publicado com o passe offline e
com `provider_pass` dizendo o que aconteceu (`skipped_disabled`, `skipped_no_entitlement`,
`failed_transient`, `failed_permanent`).

### Transcrição de voz: fornecedor decidido, roteamento pendente de eval

A tarefa `audio-transcription` nasce em `audio-transcription@1.0.0` e é a **única cujo template
não é enviado ao fornecedor**. As duas APIs de fala aceitam um parâmetro `prompt` que ENVIESA a
decodificação — é a forma documentada de sugerir vocabulário ao modelo —, e numa nota que dita
medida sugerir vocabulário é escolher o número por quem falou. O campo vai vazio; o template
versiona a POLÍTICA aplicada pelo adapter (idioma pedido `pt`, `temperature=0`, sem viés, sem
tradução) e continua sendo a identidade dessa política no lineage.

O **fornecedor** foi decidido por ato humano em 2026-08-21: Groq (hospeda Whisper, aceita
`webm/opus` e `mp4/aac` sem transcodificação, API compatível com o formato OpenAI). O que
**não** foi decidido é qual braço é primário e qual é reserva: isso sai da eval comparativa
descrita abaixo. Até ela acontecer, o default é `whisper-large-v3-turbo` por custo/latência,
declaradamente **provisório**, e o reserva nasce desligado — ligar um segundo fornecedor pago
por conta própria decidiria o resultado antes de medi-lo. Reserva igual ao primário é recusado
na construção da suite (seria fallback reexecutando a mesma falha, cobrando de novo).

Variáveis desta rota, todas com prefixo `CROQUITO_`:

| Variável | Default | Efeito |
|---|---|---|
| `CROQUITO_GROQ_API_KEY` | ausente | Sem ela o braço Groq **não existe** e o passe é `skipped_disabled`. Ausência de chave aqui é braço desligado, não erro de construção — ao contrário dos braços de extração, onde a leitura da prancha é o produto; aqui a transcrição é auxiliar e o áudio continua sendo a evidência. |
| `CROQUITO_GROQ_TRANSCRIPTION_MODEL` | `whisper-large-v3-turbo` | Modelo do braço Groq (o outro candidato é `whisper-large-v3`). |
| `CROQUITO_OPENAI_TRANSCRIPTION_MODEL` | `whisper-1` | Modelo do braço OpenAI de transcrição; usa a `CROQUITO_OPENAI_API_KEY` já existente. |
| `CROQUITO_TRANSCRIPTION_PRIMARY` | `groq` | `groq`, `openai` ou `none`. Valor diferente recusa a construção da suite em vez de escolher um modo. |
| `CROQUITO_TRANSCRIPTION_FALLBACK` | `none` | Idem, e não pode repetir o primário. |
| `CROQUITO_AI_ESTIMATED_COST_PER_TRANSCRIPTION_CALL_USD` | `0.01` | Reserva pessimista por nota de voz, no MESMO `CostBudget` da rodada. |

A operação segue as mesmas regras da leitura de foto: portão de entitlement contratual do
TENANT (levantamento não tem `job_id`, então não há consentimento por job a consultar; a suíte
injetada **não** dispensa o portão), `BUDGET_EXCEEDED` nunca aciona o reserva, troca de braço
nunca é silenciosa (nota `PROVIDER_FALLBACK_AUDIO_TRANSCRIPTION_<FORNECEDOR>` no artefato) e a
falha da chamada não derruba o comando — o artefato de transcrição é publicado com
`provider_pass` em `skipped_disabled` | `skipped_no_entitlement` | `failed_transient` |
`failed_permanent`, e reprocessar é o caminho de retomada. A resposta bruta (que contém o texto
e os segmentos com timestamp) só existe no raw-store protegido, sob o prefixo do levantamento.

### Protocolo da eval que promove primário e reserva (PENDENTE DE RODADA PAGA)

Instrumento: `make transcription-eval` (offline) e `croquito-demo transcription-eval --corpus
<manifesto> --live` (pago). Eixos comparados, decididos com o usuário na mesma data:
`Groq·whisper-large-v3`, `Groq·whisper-large-v3-turbo` e `OpenAI·transcrição`.

Métricas, **nesta ordem de peso** (um braço com WER menor e fidelidade de medida pior não
lidera):

1. `measure_recall` / `measure_precision` — fidelidade de números e medidas faladas, com a
   PRECISÃO ESCRITA preservada (`12,40` ≠ `12,4`, contado à parte em
   `written_precision_mismatches`); separador decimal de teclado diferente (`12.40`) não é erro;
2. `wer` / `cer` em pt-BR, normalizados (caixa, pontuação, espaços; acento preservado);
3. quebra por container: `webm/opus` (Android) × `mp4/aac` (iPhone).

O modo offline roda no CI com corpus sintético e adapters GRAVADOS: ele não mede fornecedor
nenhum — o gate exige que o braço exato pontue perfeito e que cada erro injetado seja detectado
pela métrica correspondente, porque uma métrica que não discrimina não serviria para escolher
fornecedor. A **rodada paga** é ato humano separado: exige chaves, teto de gasto aprovado e 10
a 15 clipes gravados pelo usuário em Android e iPhone com a verdade escrita à mão (fora do
repositório — gravação de gente não é fixture versionada). O relatório carrega só métricas,
nunca transcrição nem verdade de referência.

Promoção: o resultado da rodada paga atualiza a linha de `audio-transcription` na tabela de
rotas padrão e o default de `CROQUITO_TRANSCRIPTION_PRIMARY`/`_FALLBACK`, pelo mesmo protocolo
das evals registradas mais abaixo neste documento (uma execução por eixo, sem repetir chamada
atrás de resultado melhor). Enquanto esta seção disser PENDENTE, o roteamento em vigor é
provisório e nenhuma decisão de fornecedor além da escolha da Groq foi tomada com dado medido.

Model IDs efetivos são resolvidos por configuração validada no startup
(`CROQUITO_ANTHROPIC_MODEL`, `CROQUITO_OPENAI_MODEL`) e gravados em cada `ProviderReading`/nota
de lineage. Falha de disponibilidade bloqueia a chamada — 401/403 mapeiam para `REFUSED`,
não-retryável, em todos os adapters REST deste arquivo — e não ocorre substituição silenciosa
de modelo.

### Fallback e comparação dupla

O braço Anthropic é o primário de toda tarefa com escolha simples (`page-survey`,
`geometry-extraction`); o braço OpenAI é o reserva. A degradação nunca é silenciosa:
`PROVIDER_FALLBACK_PAGE_SURVEY_OPENAI` e `PROVIDER_FALLBACK_GEOMETRY_EXTRACTION_OPENAI` entram
nas notas de segurança do pacote sempre que o reserva assume. `BUDGET_EXCEEDED` nunca aciona
fallback — o teto é da rodada, não do braço, e a exceção propaga direto, sem tentar o reserva.

A extração de medida (`measurement-extraction`) **não** é fallback: os dois braços são chamados
sempre que possível, porque a comparação dupla é o próprio mecanismo de corroboração. Quando só
um braço sobrevive, a nota `PROVIDER_FALLBACK_SINGLE_EXTRACTOR_ANTHROPIC`/`_OPENAI` nomeia quem
respondeu e toda leitura nasce `AMBIGUOUS` (nunca `PROPOSED`) — sem contraparte não existe
leitura concordante. Quando os dois braços de extração de medida falham, a exceção do segundo
(`openai`) propaga e o job falha para reentrega — um pacote vazio seria menos honesto do que
reentregar.

### Braço OpenAI desligado por configuração

`CROQUITO_OPENAI_ARM_ENABLED=false` tira o braço reserva da suite
(`ProviderSuite.openai is None`): a contraparte não é chamada, não reserva teto e não aparece
no lineage. O efeito no pacote é o **mesmo** do braço único por falha — nota
`PROVIDER_FALLBACK_SINGLE_EXTRACTOR_ANTHROPIC`, toda leitura `AMBIGUOUS`, nenhuma `PROPOSED` —
e é de propósito: para a revisão humana o que muda o valor da leitura é ter uma testemunha só,
não o motivo disso. O motivo fica no log do operador
(`provider_arm_unavailable arm=openai reason=ARM_NOT_CONFIGURED`, uma vez por documento).
Sem reserva não há fallback de survey/geometria: a falha permanente do primário propaga e o
job volta para reentrega, sem nota `PROVIDER_FALLBACK_*` — não houve troca de braço para
registrar.

Desligar é **ato declarado**: a ausência de `CROQUITO_OPENAI_API_KEY` continua recusando a
construção da suite quando a flag está ligada ou ausente. Valor diferente de `true`/`false`
(sem diferenciar caixa) também recusa, em vez de escolher um modo. A rodada de HML de
2026-08-20 está com a flag em `false` por decisão humana, com a chave ainda montada no
serviço para que religar seja só a flag ([HML](../operations/HML.md)).

### Caminho de comparação: eval por linha de comando

`croquito-demo extraction-eval --arm nome=provider:model_id` continua permitindo comparar
eixos — Anthropic direto, Bedrock ou OpenAI, cada um com o modelo escolhido na flag — via
`build_extraction_arm`. Esse caminho é **independente** da suite hospedada descrita acima: é o
que produziu as evals pagas comparativas registradas mais abaixo neste documento (Toca, medição,
contrato de arco), e é a única via deste repositório que ainda fala com Bedrock — nunca chamada
pelo worker normal, e sem braço Textract (nunca existiu ali). O lineage continua distinguindo os
dois caminhos: API direta grava `provider: anthropic`; Bedrock grava
`provider: bedrock_anthropic`. `croquito-demo extraction-eval`, por não ter sido tocado nesta
entrega, mantém o default histórico do eixo `bedrock:...` — ajustar esse default para
`anthropic:` é pendência registrada em
[ADR-0035](../adr/0035-suite-hospedada-openai-anthropic-direto.md).

A autorização de providers por job na API (`providers_json`) passa a listar `["openai",
"anthropic"]` — a lacuna registrada nesta seção antes desta revisão ("ainda não inclui
`anthropic`") está fechada. O braço `ocr` (Cloud Vision ou Document AI, conforme
`CROQUITO_DOCAI_PROCESSOR`) **não** entra nessa lista: é suporte determinístico sempre
ligado quando a suite real é construída, não um provider de LLM que o tenant consente por
si — decisão registrada em
[ADR-0035](../adr/0035-suite-hospedada-openai-anthropic-direto.md) e revisada, na escolha
de fornecedor do braço, pelo [ADR-0037](../adr/0037-document-ai-como-braco-de-ocr.md).

## Estado de implementação local

O worker possui portas tipadas e mocks determinísticos para os três braços da suite hospedada
(OpenAI, Anthropic e o braço `ocr`, montável como Cloud Vision ou Document AI) e, à parte, para
Bedrock/Claude e Textract, usados só pela eval de linha de comando. Eles são ativados somente
por injeção em teste ou pelo demo sintético; o worker normal não lê flag de ambiente para
fabricar observações e não chama serviços externos por conta própria. Adapters reais são
configuráveis por `CROQUITO_REAL_PROVIDERS_ENABLED=true`; exigem entitlement contratual ativo
por tenant e snapshot imutável por job, credenciais fora do Git, budget, eval comparativa e
plano de rollback. O piloto processa a primeira página e sinaliza as demais como não
analisadas. `build_real_provider_suite` não importa `boto3`: os dois braços de extração falam a
API direta do respectivo fornecedor com a própria chave (`CROQUITO_OPENAI_API_KEY`,
`CROQUITO_ANTHROPIC_API_KEY`), e o braço `ocr` autentica por Application Default Credentials da
service account de runtime do worker — nenhuma chave nova, para qualquer um dos dois
fornecedores. Qual dos dois monta é decisão de `CROQUITO_DOCAI_PROCESSOR`: definido (nome
completo do processador), o braço é o Document AI daquele processador; ausente ou vazio, é o
Cloud Vision, exatamente como antes — troca reversível por configuração, sem redeploy de
código ([ADR-0037](../adr/0037-document-ai-como-braco-de-ocr.md)). Nenhum processador está
provisionado em HML até esta revisão; a suite hospedada segue montando Cloud Vision.
Antes de cada chamada (inclusive OCR), o worker reserva o custo estimado configurado
(`CROQUITO_AI_ESTIMATED_COST_PER_LLM_CALL_USD`, `CROQUITO_AI_ESTIMATED_COST_PER_OCR_CALL_USD`,
default `0.0015`) no mesmo `CostBudget` da rodada; ultrapassar
`CROQUITO_AI_MAX_ESTIMATED_COST_USD` bloqueia a chamada, para qualquer braço.

**O teto precisa comportar mais que uma chamada (issue #137).** `TIMEOUT` nunca devolve a
reserva — `ProviderExecutionError.reached_provider` é `True` por padrão, e só quem PROVA
que a chamada não saiu da máquina aciona `CostBudget.release` — porque o dinheiro pode ter
sido gasto mesmo sem resposta. Cada tentativa que o `RetryingProviderAdapter` refaz depois
de um `TIMEOUT` reserva de novo contra o MESMO teto, e a reserva anterior fica retida. Com
os defaults de hoje — reserva de `CROQUITO_AI_ESTIMATED_COST_PER_LLM_CALL_USD` (US$ 0,75) e
timeout de `DEFAULT_LLM_TIMEOUT_SECONDS` (120 s) — uma cadeia de `TIMEOUT` consecutivos
esgota o prazo de parede default do retry (`DEFAULT_PROVIDER_RETRY_DEADLINE_SECONDS`, 300 s)
em **3 tentativas** antes de o `RetryingProviderAdapter` desistir por conta própria. Um teto
dimensionado para "reserva × 1 chamada" torna esse retry impossível por construção: a 2ª
tentativa já estoura `BUDGET_EXCEEDED`, e a rodada morre sem uma única chamada bem-sucedida
— comportamento real, não hipotético (achado durante a validação do #135, reproduzido de
novo em 2026-09-04 com dois estouros consecutivos de 45,1 s). A regra: **o teto precisa
comportar `(tentativas + 1) × reserva` por chamada** — as tentativas que o braço que falha
pode consumir, mais uma reserva de folga para o braço seguinte (fallback ou a próxima
leitura da rodada) ainda ter uma chance. Com os defaults de hoje isso é `(3 + 1) × 0,75` =
**US$ 3,00 no mínimo**; abaixo disso, um único `TIMEOUT` já compromete o resto da rodada.

## Etapas

### Orientação da folha (determinística, antes de qualquer LLM)

O croqui de campo chega deitado com frequência, e o PDF não declara rotação. A folha é
endireitada **antes** da primeira chamada de modelo, a partir dos vértices de palavra que o
OCR devolve: o vetor v0→v1 de cada palavra diz para onde o texto corre, o quarto de volta
mais próximo é o voto da palavra (peso = número de símbolos), o parágrafo decide por maioria
e a página decide por maioria ponderada pelo tamanho do texto de cada linha
(`croquito_worker.page_orientation`). Com veredito, a página é girada e o pacote ganha a nota
`PAGE_ROTATED_{90|180|270}CCW_FROM_OCR_ORIENTATION`.

O campo `orientation` do `page-survey` **não** é usado para isso: sondado contra o corpus real
de campo (7 páginas, 2026-09-03), ele respondeu `up` para uma folha girada 90°. O voto por
vértice do OCR acertou 7/7 no mesmo corpus, com share entre 52% e 100% — daí o piso de 50%.

Girar uma vez, no começo, é o que mantém a cadeia consistente sem transformar coordenada em
consumidor nenhum: survey, extração, geometria, corroboração de tinta, `source.png` e a tela
da revisão leem a MESMA imagem, e é a girada. O digest do pacote passa a ser o da folha
girada; o `input_digest` da chamada de OCR continua sendo o da folha como chegou, porque foi
essa que saiu para o fornecedor.

### Page survey

Recebe página completa e identifica regiões, tipos de desenho, vocabulário e
possíveis cotas. Não produz coordenadas CAD.

### Region extraction

Recebe recorte em alta resolução mais contexto mínimo da página. Produz leituras
no schema do prompt contract.

### Escalation

Ocorre quando:

- Valores normalizados divergem.
- Associação aponta para entidades diferentes.
- Schema é válido, mas regra geométrica falha.
- Texto é ambíguo na precisão material.

Escalonamento recebe somente o recorte, as duas transcrições e a pergunta de
desambiguação. Não recebe a preferência do sistema.

## Falhas

- Braço primário (Anthropic) falha de forma permanente em `page-survey` ou
  `geometry-extraction`: assume o reserva (OpenAI), com nota `PROVIDER_FALLBACK_*` no pacote —
  nunca silencioso. `BUDGET_EXCEEDED` nunca aciona fallback.
- Os dois braços de extração de medida falham: job falha para reentrega — nenhum pacote vazio é
  publicado como se a página não tivesse cota.
- Um único braço de extração de medida sobrevive (o outro falhou de forma permanente): toda
  leitura nasce `AMBIGUOUS`, nunca `PROPOSED`; a nota
  `PROVIDER_FALLBACK_SINGLE_EXTRACTOR_ANTHROPIC`/`_OPENAI` nomeia quem respondeu.
- Braço OpenAI desligado por configuração (`CROQUITO_OPENAI_ARM_ENABLED=false`): mesmo pacote
  do caso acima, sem chamada nenhuma à contraparte; o primário falhando propaga direto, porque
  não há reserva para assumir.
- OCR (Cloud Vision ou Document AI, conforme `CROQUITO_DOCAI_PROCESSOR`) indisponível, ausente
  da suite, ou falha permanente: uma nota única `OCR_UNAVAILABLE`, sem nota por leitura; pacote
  segue normal. O log de falha do braço nomeia qual dos dois fornecedores caiu
  (`provider=gcp_vision` ou `provider=gcp_document_ai`).
  `OCR_EVIDENCE_MISSING`, documentado numa revisão anterior deste documento, nunca chegou a
  existir como fallback de fato — a chamada de OCR do Textract no snapshot era código morto
  (schema validado e resultado descartado) até a F-009. O comportamento real, implementado por
  ela, é `READING_{n}_OCR_CONFIRMED` / `READING_{n}_OCR_EVIDENCE_MISSING` por leitura quando o
  OCR roda, e `OCR_UNAVAILABLE` (nota única) quando não roda; nenhuma das duas rebaixa o
  `status` já calculado da leitura. A partir da F-010 (2026-08-20), a mesma corroboração
  também chega ao revisor como campo `ocr_corroborated` de cada leitura do pacote — não
  só na nota posicional/telemetria.
- OCR que não sustenta veredito de orientação (voto abaixo de 50% do peso, menos de 20
  caracteres votantes, empate exato, ou braço que não reporta vértice de palavra — Textract e
  Document AI não reportam): a folha **não** é girada e o snapshot segue com a página como ela
  chegou. Não girar é o comportamento seguro: girar errado custaria a extração inteira.
- `BUDGET_EXCEEDED` em qualquer braço, inclusive OCR: propaga sempre, nunca é absorvido em modo
  degradado — o teto é do job, não do braço. Como o OCR passou a ser a primeira chamada, o
  estouro de teto passa a interromper o job antes de qualquer chamada de LLM.
- **Extração de legenda (medição E orçamento) com braço de reserva**, desde 2026-08-21:
  `CROQUITO_EXTRACTION_RESERVE_ARM` (forma `NOME=PROVIDER:MODELO`), **vazia por padrão**.
  Vazia significa comportamento idêntico ao anterior — falha do primário propaga, sem
  reserva e sem nota. Configurada, o primário falhando em definitivo cede a vez à reserva
  e o pacote nasce com a nota `PROVIDER_FALLBACK_LEGEND_EXTRACTION_<PROVIDER>`, nomeando
  quem de fato respondeu; `BUDGET_EXCEEDED` continua sem acionar reserva.

  As duas jornadas compartilham o handler (`_handle_round_extraction`), então a reserva
  vale para `extract_valuation_plate` e `extract_estimate_plate` de uma vez. A env
  existente `CROQUITO_MEDICAO_EXTRACTION_ARM` também governa as duas, apesar do nome — a
  nova não repete o erro.

  Reserva **declarada e inconstruível** (credencial ausente, forma inválida, provider
  `fixture`) recusa a extração inteira em vez de degradar para "sem reserva": quem escreveu
  a variável espera degradação, e descobrir no dia da queda que ela nunca existiu é pior
  que falhar agora. A recusa carrega `role: "reserva"` e o nome da variável, porque os
  códigos de erro são os mesmos dos dois papéis e sem isso o operador depura o braço são.

  Braço eleito na eval de 2026-08-21: **`gpt-5.6-luna`** — não por cobertura (9/15 contra
  14/15 do `gpt-5.6`), e sim por modo de falha: foi o único dos braços OpenAI que não
  inventou nenhum número. Ligar em qualquer ambiente é mudança de IA e pede eval e rollback.
- Modelo retorna schema inválido: uma tentativa de repair estritamente estrutural;
  depois tratar como falha.
- Rate limit (429): retry com backoff e respeito a `Retry-After`. Falha de credencial (401/403):
  `ProviderFailureCode.REFUSED`, sem retentativa — mapeamento comum a todos os adapters REST
  deste arquivo (OpenAI, Anthropic, Cloud Vision).

### Insistência: prazo de parede, não contagem de tentativas

Desde 2026-08-21, `RetryingProviderAdapter` insiste por **prazo**
(`CROQUITO_PROVIDER_RETRY_DEADLINE_SECONDS`, default 300 s), não por número fixo de
tentativas. Contar tentativas dava tempos incomparáveis: cinco tentativas são ~5 min numa
pendurada, porque cada uma custa o timeout inteiro do braço, e ~40 s num 429, porque a
recusa volta em ~1 s. O prazo descreve os dois casos com um número só.

A espera depende da família da falha, porque os relógios são diferentes:

| falha | escada | jitter |
|---|---|---|
| `TIMEOUT` | 250 ms → 500 ms → 1 s → 2 s (satura) | não |
| `RATE_LIMITED`, `UNAVAILABLE` | 5 s → 10 s → 20 s → 40 s → 60 s (satura) | ±25% |

Medido com relógio injetado, prazo de 300 s: pendurada de 60 s por tentativa dá **5
tentativas em 303,8 s**; 429 que volta em 1 s dá **8 tentativas em 294,9 s**.

**O prazo decide quando parar de COMEÇAR tentativa, não interrompe a que está em curso** —
o teto real é o prazo mais a duração de uma tentativa. Com timeout de 60 s isso é ~360 s no
pior caso; com timeout maior, proporcionalmente mais.

`REFUSED`, `INVALID_SCHEMA` e `BUDGET_EXCEEDED` seguem fora da retentativa: insistir em
recusa não busca disponibilidade, busca outra leitura.

**Consequência de operação a conferir antes de subir:** o pior caso por job passou a ser
prazo do primário + prazo do reserva + prazo do OCR ≈ 15 min. O timeout de request do Cloud
Run e o prazo de ack do Pub/Sub vivem no Terraform de `biahflow/infra` e precisam caber
nisso, ou o job vira reentrega.

## Controle de custo

- Nunca escalonar página inteira quando um recorte resolve.
- Deduplicar por image digest + prompt version + model ID.
- Limitar reanálises manuais por tenant e exibir impacto operacional.
- Registrar tokens, duração e custo estimado sem conteúdo.
- Evals usam conjunto fixo; não repetem chamadas para “melhor resultado”.

## Eval comparativa executada (Toca, 2026-08-11)

Primeira eval paga comparativa de extração de geometria, autorizada pelo usuário
(teto US$ 1,50), sobre `golden-toca-v1/page-001.png` via API direta da Anthropic:

| Arm | Modelo | Elementos | Corroboração bruta | Após registro | Custo real |
|---|---|---|---|---|---|
| opus | `claude-opus-5` | 23 | 0,57 | **0,96** ✅ | ≈ US$ 0,14 |
| sonnet | `claude-sonnet-5` | 14 | 0,14 | 0,57 ❌ | ≈ US$ 0,04 |

Decisão de roteamento: **Opus é o modelo de extração de geometria**. O Sonnet reprovou
mesmo após o registro fino (`register-extraction`): o melhor assentamento exigiu girar o
conjunto 270° e 6 de 14 elementos ficaram sem tinta — estrutura errada, não só
enquadramento. Rollback: desligar `CROQUITO_REAL_PROVIDERS_ENABLED` volta ao caminho
OpenCV-only (golden `dxf-toca` demonstra o resultado sem extração).

O gate `corroborated_rate >= 0.7` reprova por desregistro sistemático do VLM; o comando
`register-extraction` corrige assentamento sem poder inventar geometria e preserva a taxa
original em nota. A coluna "Após registro" desta tabela foi medida com a versão do motor
que aplicava **uma única transformação global** por eixo de comparação. O motor atual
acrescenta rotação fina no estágio global e um refino por elemento com garantia de nunca
piorar, descrito em [Vision Proposals](VISION_PROPOSALS.md); comparar números entre as
duas versões exige reexecutar o comando sobre os mesmos artefatos, que é barato porque não
há nova chamada paga. A decisão de roteamento acima não depende dessa diferença: o Sonnet
reprovou por elementos sem tinta nenhuma, que refino nenhum recupera.

## Eval comparativa executada (medição, prancha sintética, 2026-08-13)

Primeira eval paga do contexto de medição, autorizada pelo usuário (teto US$ 1,50 para a
rodada sintética), sobre a prancha sintética via `croquito-valuation extraction-eval
--arm`, API direta da Anthropic. Cobre as duas tarefas novas: `legend-extraction`
(visão) e `sco-refinement` (a primeira tarefa de texto puro do repositório).

| Arm | Modelo | Recall legenda | Quantidade | SCO top-1 (lexical → refinado) | Resultado | Custo real |
|---|---|---|---|---|---|---|
| sonnet | `claude-sonnet-5` | 1,0 | 1,0 | 0,8 → **1,0** | ✅ | ≈ US$ 0,05 |
| opus | `claude-opus-5` | — | — | — | ❌ | ≈ US$ 0,55 (descartado) |

O Opus reprovou duas vezes. A primeira rodada foi invalidada por defeito **nosso** de
contrato — o schema permitia flags sem limite de tamanho e a nota composta do domínio
estourava o teto de 300; corrigido em `sco-refinement@1.0.1` (limite de 120 por flag,
nota do domínio comporta o pior caso do contrato por aritmética). A segunda rodada, já
sob o contrato corrigido, reprovou por violação real: a resposta devolveu quatro códigos
para uma shortlist de três, com um código duplicado, e o domínio recusou com
`REFINEMENT_CODES_MISMATCH` — refino é permutação exata da shortlist, e conformidade de
schema é gate. Não houve terceira rodada: eval não repete chamada para buscar resultado
melhor, e a segunda rodada foi a primeira tentativa justa do Opus.

Decisão de roteamento: **Sonnet é o modelo das duas tarefas de medição**
(`legend-extraction` e `sco-refinement`) para a rodada real da Toca — o inverso da
extração de geometria, onde o Opus venceu; tarefas diferentes, gates diferentes.
Custo real total da rodada ≈ US$ 0,60–0,70, dentro do teto autorizado.

Rollback: nenhum estado novo a desligar. Sem `--refine-arm`, `suggest-codes` publica a
shortlist lexical determinística (fallback permanente do produto); sem
`extract-legend-real`, o takeoff continua nascendo da fixture sintética ou de transcrição
manual. Comando pago que falha recusa fechado e não publica artefato.

Nota operacional da rodada: o Python gerenciado pelo `uv` neste macOS não encontra os
certificados CA do sistema e o adapter traduz a falha de TLS em `TIMEOUT`; com retries,
isso consome teto estimado sem gastar nada. Antes de qualquer comando pago, exportar
`SSL_CERT_FILE` apontando para o bundle do `certifi` — o runbook
[RUNBOOK_VALUATION_TOCA_ACCEPTANCE](../operations/RUNBOOK_VALUATION_TOCA_ACCEPTANCE.md)
registra o sintoma e os valores recomendados de reserva por chamada.

## Eval comparativa executada (contrato de arco `geometry-extraction@2.0.0`, 2026-08-13)

Eval de **contrato** (schema novo × schema antigo, mesmo modelo `claude-opus-5` via API
direta), autorizada pelo usuário (teto US$ 1,00 na env, ok de gasto renovado a cada
lote de chamadas). Candidato: arco com três pontos-âncora observáveis
(`arc_start`/`arc_mid`/`arc_end`), abertura deixando de ser fabricada 0..π. Baselines:
artefatos v1 já pagos de `golden-guaxindiba-v1` e `golden-raul-v1`, ambos reexecutados
com o motor de registro atual antes da comparação (obrigação da seção da Toca acima).

A primeira chamada do candidato reprovou com `INVALID_SCHEMA` e o diagnóstico (payload
bruto preservado em `output/extraction-eval-arc-v2/`) mostrou defeito **nosso** de
contrato, no mesmo padrão do `sco-refinement@1.0.1`: o Opus reportou as três âncoras das
duas meias-luas e omitiu `center`/`radius` — a resposta mais honesta possível, já que
três pontos determinam o círculo — e o validador exigia o par. O contrato foi corrigido
ainda como candidato (arco aceita o par OU as três âncoras; centro e raio derivados do
circuncírculo em pixels; colineares descartam o elemento) e o candidato revisado rodou
uma única vez por imagem:

| Imagem | Métrica | v1 (fabricado) | v2 (observado) |
|---|---|---|---|
| Guaxindiba | coverage_raw meia-lua esq./dir. | 0,0 / 0,0 | **0,163 / 0,283** |
| Guaxindiba | orientation_delta esq./dir. | −104° / +73° | **0° / −7°** |
| Guaxindiba | cobertura refinada das meias-luas | 1,0 (reconquista) | 1,0 (lapidação ±15°) |
| Guaxindiba | corroboração pós-registro | 1,0 (20/20) | 0,952 (20/21)¹ |
| Raul | corroboração pós-registro | 0,944 (17/18) | 0,938 (15/16)¹ |
| Raul | arcos emitidos | 0 | 0² |

¹ Diferenças agregadas na granularidade de 1 elemento com conjuntos de elementos
diferentes entre execuções (variância conhecida do modelo por folha); no Guaxindiba o
não corroborado do v2 é a faixa vegetativa hachurada, sem relação com arco.
² Hipótese secundária **não confirmada**: nomear âncoras no prompt não aumentou a
propensão do Opus a emitir `kind="arc"` no contorno orgânico do Raul — o caminho curvo
continuou vindo como contorno, e uma polilinha reconhecida como arco pelo refino seguiu
o caminho de reconquista (0,171 → 1,0 com −61°), que permanece intacto.

Decisão: **contrato @2.0.0 aprovado e promovido** — âncoras observadas põem o arco na
tinta antes de registro e transformam o refino de orientação em lapidação (janela ±15°),
com 0% de omissão onde houve arco. Custo real da rodada: 4 chamadas (2 perdidas no
defeito de contrato + diagnóstico, 2 do candidato revisado), ≈ US$ 0,45–0,60 total.
Rollback: reverter o commit de contrato/prompt (saída v1 valida sob o schema v2 — campo
aditivo-opcional; artefatos v2 são auto-descritos pelo `prompt_version` no lineage);
`CROQUITO_REAL_PROVIDERS_ENABLED=false` segue sendo o kill switch do caminho pago.

## Eval comparativa executada (degrau em muro de contorno, geometry-extraction@2.0.2, 2026-08-19)

Motivação: a primeira revisão real em nuvem (Guaxindiba V3) devolveu o muro com recuo
4,80→3,30 fragmentado em duas `line` retas do `claude-opus-5` sob o prompt `2.0.1` — o
degrau lateral desapareceu, achatado num traço só. O candidato `2.0.2`
([Prompt Contracts](PROMPT_CONTRACTS.md)) instrui que um degrau/recuo em contorno ou muro
vira vértices de uma única polyline, nunca duas linhas separadas nem uma reta achatada;
schema `2.0.0` intacto.

Protocolo: fixture sintética dedicada ao muro em degrau (`make extraction-eval-degrau`,
[Evaluation Strategy](EVALUATION_STRATEGY.md#gate-do-degrau-em-contorno-extração-de-geometria)),
uma chamada baseline sob `@2.0.1` e uma chamada candidato sob `@2.0.2`, ambas
`claude-opus-5` via API direta, autorizado pelo usuário (teto US$ 1,00 na env). O golden de
regressão do produto não foi rerodado nesta eval — a prova real fica no re-upload do
Guaxindiba pós-deploy.

| Métrica | baseline `@2.0.1` | candidato `@2.0.2` |
|---|---|---|
| Forma emitida | muro fragmentado em 3 polylines sobrepostas, mais uma cauda alucinada | 1 polyline aberta de 4 vértices com o degrau exato |
| Elementos totais | 5 | 2 |
| `step_preserved` | `False` (`STEP_MULTIPLE_CANDIDATES:3`) | `True` |
| Jog observado | — | 29,4 px ≈ 30 px do desenho, rótulo "Contorno com degrau lateral" |
| Latência | 12,6 s | 7,3 s |

Com o harness corrigido (registro contra a tinta antes da corroboração, critério estrutural
do jog no lugar de posição absoluta — commit `9ec75e2`), a validação offline sobre as
respostas pagas já salvas mediu `corroborated_rate=1,000` **nos dois braços** — o baseline
fragmentado corrobora tão bem quanto o candidato porque cada fragmento adere à tinta
individualmente. É a evidência de que corroboração de tinta sozinha não detecta
fragmentação: só o critério estrutural do jog (`assess_step_fidelity`) reprova o baseline e
aprova o candidato.

Custo real: 2 chamadas cobradas ≈ US$ 0,28 (≈ US$ 0,14/chamada, coerente com a eval da
Toca), contra teto autorizado de US$ 1,00. Duas chamadas adicionais foram perdidas por um
defeito local de ambiente, não do modelo nem do contrato: `CERTIFICATE_VERIFY_FAILED` do
`urllib` foi mascarado de `TIMEOUT` pelo mapeamento `URLError→TIMEOUT` do adapter —
registrado aqui como observação de diagnóstico, não como falha do candidato.

Decisão: **`geometry-extraction@2.0.2` aprovado e promovido** — aprovação humana: o usuário
autorizou a rodada e o fluxo em 2026-08-19. Rollback: reverter `PROMPT_VERSIONS` para
`2.0.1` em `providers.py` (schema `2.0.0` não muda, então nenhuma leitura gravada sob o
candidato fica inválida ao reverter);
`CROQUITO_REAL_PROVIDERS_ENABLED=false` segue sendo o kill switch do caminho pago.

## Eval comparativa executada (legenda, PRANCHA REAL do Campo do Toca, 2026-08-21)

Primeira eval de extração de legenda sobre **prancha real** (não fixture): o arquivo do
projetista, 1 página a 200 DPI (9362x6623), 15 itens quantificados na legenda. Autorizada
pelo usuário com teto de US$ 5,00 para a rodada. O gabarito são os 15 itens **confirmados
pelo orçamentista** depois da extração — por isso os números abaixo são recall medido, não
impressão.

Motivação declarada: escolher um **braço de reserva** para quando a Anthropic estiver
indisponível, não trocar o primário.

| Arm | Modelo | Itens | Quantidades | Inventados | Número errado |
|---|---|---|---|---|---|
| sonnet | `claude-sonnet-5` | **15/15** | **15/15** | 0 | — |
| gpt-5.6 | `gpt-5.6` | 15/15 | 14/15 | 1 | `PISO EM SAIBRO` = 969,70 (certo 98,70) |
| opus | `claude-opus-5` | 15/15 | 11/15 | 1 | — |
| luna | `gpt-5.6-luna` | 14/15 | 9/15 | 1 | **nenhum** |
| terra | `gpt-5.6-terra` | 14/15 | 7/15 | 1 | `PISO INTERTRAVADO` = 69,34 (certo 59,34) |
| gpt-5.5 | `gpt-5.5` | 15/15 | 5/15 | 1 | `PISO EM SAIBRO` = 99,70 (certo 98,70) |
| gpt-4o | `gpt-4o` | 0/15 | 0/15 | 5 | — |
| mistral | `mistral-large-latest` | 0/15 | 0/15 | 8 | — |
| gemini | `gemini-3.1-pro-preview` | — | — | — | não mediu: `429` de cota |

**Decisão de roteamento: Sonnet permanece o braço da extração de legenda** — 15/15 em
rótulo, unidade e quantidade, sem um único item inventado. É a segunda confirmação
independente do roteamento de 2026-08-13, agora sobre insumo real.

**Decisão de reserva: `gpt-5.6-luna`**, e o critério não é cobertura, é o modo de falha.
O `gpt-5.6` preenche mais (14/15 contra 9/15) mas produziu um erro de **10x**; o `luna`
deixa a lacuna em branco e não chuta nenhum número. Item sem quantidade nasce ambíguo e
força o revisor a preencher; número errado chega como proposta plausível e pode passar.
Num produto cujo portão é a revisão humana, **omitir é seguro e chutar não é**.

`gpt-4o` e `mistral-large-latest` são **reprovados sem reserva**: os dois não leram a
legenda — fabricaram outra. O Mistral devolveu oito itens bem formatados ("ÁREA DE
REFERÊNCIA 6.559,66m²", "PRAÇA LINEAR COM ESPAÇO DE CONVIVÊNCIA 1.200,00m²") que não
existem na prancha; o gpt-4o devolveu cinco no mesmo estilo. Alucinação com número
plausível é categoricamente pior que leitura incompleta, e nenhum dos dois entra como
reserva.

O Gemini **não foi medido**, e a causa está fechada: com chave nova, em 2026-08-21,
`gemini-2.5-flash`, `gemini-2.0-flash` e `gemini-2.5-pro` devolvem `404 — no longer
available to new users` (o Google aposentou esses modelos para contas novas e a própria
mensagem redireciona ao `gemini-3.6-flash`), e `gemini-3.6-flash` e
`gemini-3.1-pro-preview` devolvem `429 — Your prepayment credits are depleted`. A chave
autentica e o adapter funciona; falta crédito pré-pago no projeto. Fica como eixo em
aberto, reabrível sem trabalho de código: os dois ramos de `build_extraction_arm` e o
`GeminiProviderAdapter` já estão no lugar e cobertos por teste offline.

### Achado de custo de leitura, não de modelo

O reassentamento de bbox (`register_legend_bboxes`) falhou nesta prancha e a causa não era
o modelo: a janela de busca vertical era absoluta (`max(0,5 x vão proposto, 300px)`),
enquanto o desvio do VLM é **proporcional à página** — 822px aqui, 12,4% da altura. As
sete primeiras linhas da legenda caíam fora da janela. Corrigido com um terceiro termo
(`RULING_SEARCH_MARGIN_HEIGHT_RATIO = 0,15` da altura da imagem); depois disso, 15/15
reassentados a 4px da linha real, com `shift_score` 14,9998 de 15.

### Achado do casamento de código sobre catálogo real

Sobre a tabela SCO-Rio de julho/2026 (4.865 itens), com índice de embeddings construído
(`text-embedding-3-small`, US$ 0,03 de reserva, ~US$ 0,007 real):

- o braço léxico por Dice puro erra feio (casa "PISO INTERTRAVADO" com *limpeza de pisos
  vinílicos*, e "BALANÇO DUPLO" com *calço duplo*);
- o híbrido melhora muito — em 9 itens de gabarito, 7 acertos em 1º lugar contra 3 do
  léxico;
- **os dois erros restantes não são de recall, são de corte**: com shortlist de 20,
  `BP09200350` (piso intertravado) aparece em 4º pelo léxico-IDF e 15º pelo híbrido, e
  `PJ14050160` (gola de árvore) em 5º e 11º. O produto publica **3**.

`SuggestionConfig.max_candidates_per_item` tem default `3` e o CLI não expõe o tamanho,
enquanto o gate versionado (`tests/valuation/test_matcher_golden.py`) mede **recall@20**.
Alinhar os dois é a correção de maior retorno medido nesta rodada. Registrado como achado;
a mudança em si é decisão humana.

Segundo achado da mesma medição: nesses dois itens o **léxico ponderado por IDF sozinho
supera o híbrido** (4º contra 15º, 5º contra 11º) — o braço semântico os empurra para
baixo (ranks 114 e 279), embora ajude em outros ("PISO EM CONCRETO", semântico em 2º).
A ponderação da fusão merece ser remedida contra gabarito real antes de qualquer ajuste.

## Embeddings para retrieval de código SCO (M7, 2026-08-13)

O matcher de código do contexto de medição usa retrieval híbrido
([ADR-0021](../adr/0021-hybrid-sco-code-retrieval.md)): braço léxico (cobertura da
consulta ponderada por IDF sobre radicais + sinônimos como dado) fundido por RRF com
braço semântico — embeddings OpenAI `text-embedding-3-small` (env
`CROQUITO_EMBEDDINGS_MODEL` para trocar), índice local por catálogo amarrado por
digest e receita de texto, kNN em numpy. Custos reais medidos: índice de 4.964 itens
≈ US$ 0,007 (uma vez por versão de catálogo); consulta por rótulo ≈ desprezível, com
cache por rodada.

Medições que fixaram a configuração (golden real da Toca, 12 casos):

| Configuração | recall@20 |
|---|---|
| Léxico Fase 1 (radicais + sinônimos, Dice) | 4/12 |
| Híbrido (cobertura simples + RRF, profundidade 50) | 8/12 |
| + IDF no braço léxico | 11/12 |
| + oráculo por família nos casos de variante indiscriminável pelo rótulo | **12/12** |

Receita de texto do índice também foi medida: embeddar sem o prefixo de código piorou
(8/12) e foi descartada — a tabela vive em `INDEX_TEXT_RECIPE_MEASUREMENT`
(`sco_matching.py`) e a receita é amarrada no índice (`INDEX_TEXT_RECIPE_MISMATCH`
recusa carga divergente). Profundidade de braço 50 é ótimo medido antes e depois do
IDF (curva na docstring de `HYBRID_ARM_DEPTH`).

Rollback: sem chave/teto/índice, busca e shortlist degradam para o léxico funcional com
o motivo declarado (`matching: lexical` + aviso no `/state`); nenhum estado novo a
desligar. Embeddings não têm prompt — o lineage é modelo + contagem + digest do lote
([Prompt Contracts](PROMPT_CONTRACTS.md) não se aplica a esta chamada).

## Critérios para trocar modelo

Nova versão só substitui a atual quando:

- Passa schema compliance.
- Não piora false-confident errors.
- Mantém ou melhora cotas e associações nos golden cases.
- Custo/latência estão documentados.
- Existe rollback de configuração.
- [Prompt Change Protocol](PROMPT_CHANGE_PROTOCOL.md) foi seguido.

## Residência e privacidade

O MVP usa processamento global controlado. Enviar somente pixels necessários e
identificadores opacos. Nenhum prompt inclui tenant, nome de pessoa, bucket ou URL
persistente.
