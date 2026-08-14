# ADR-0023: Conversa da revisão como agente observacional com rascunhos tipados

Status: Accepted  
Data: 2026-08-13  
Responsável: Domain / Backend / AI Engineering

## Contexto

A tela de revisão pergunta muito ao profissional e responde pouco. O
[Trace Stage](../architecture/TRACE_STAGE.md) enumera sete controles — decisão de leitura,
associação, aceite em lote, nota presa, texto de cota, cota derivada, grupo de detalhe — e
cada um deles é uma pergunta que a UI faz. Quando a folha é ambígua (dois traços
coincidentes, uma cota escrita longe do trecho que mede), o revisor fica sozinho: ele tem o
recorte da evidência ao lado da pergunta, mas ninguém com quem conferir a leitura.

O ciclo real do Campo do Guaxindiba, fechado em 2026-08-13, mostrou onde o tempo humano é
gasto: 29 decisões de leitura e oito rodadas de motor até o DXF abrir no AutoCAD. Boa parte
das dúvidas não é geométrica, é de leitura da folha — "essa cota é do patamar ou da
mureta?" —, e é exatamente o tipo de pergunta que um modelo com a página na frente pode
ajudar a organizar.

O risco é igualmente claro, e é o mesmo desde o ADR-0006: um agente que "ajuda" tem uma
inclinação natural a decidir. Um agente que confirmasse leitura, criasse associação ou
aprovasse cena destruiria a única garantia que este produto vende — que a geometria
exportada é a que um profissional identificado assinou.

## Decisão

A conversa da revisão é um **estágio observacional**, com a mesma forma que todo trabalho
pesado já tem neste repositório, e não tem nenhum caminho de escrita para o domínio.

- **O turno é um comando assíncrono na fila existente.** `POST
  /v1/jobs/{id}/chat-sessions/{id}/turns` valida, persiste `QUEUED`, commita e publica
  `{"command": "answer_chat_turn", ...}`; o worker responde e o cliente acompanha por
  polling. É o padrão do [ADR-0013](0013-export-worker-and-artifact-registry.md) e do
  [ADR-0015](0015-trace-solve-worker-and-registry.md), pelo mesmo motivo do
  `services/api/AGENTS.md`: a API não chama modelo no request path.
- **A resposta é observação com rascunhos tipados dos payloads existentes.**
  `ReviewChatOutput.proposed_acts` é uma união discriminada de no máximo três rascunhos —
  decisão de leitura, associação de traçado, `keep_apart`, nota presa e pendência escrita —
  e cada um deles é o corpo que um endpoint **já publicado** aceita. O agente preenche o
  formulário; quem assina é o profissional, pelo comando que já existia.
- **O agente não submete nada, estruturalmente.** Não existe caminho de código do worker de
  conversa para `review_decisions`, `scene_revisions`, `trace_solves` ou `approvals`: o
  handler grava uma linha em `chat_turns` e nada mais. A ausência do caminho é a garantia;
  uma instrução de prompt não seria.
- **Rascunho não pode citar o que não existe.** Todo id em `proposed_acts` é conferido
  contra o snapshot da revisão-base, e uma citação desconhecida recusa o turno **inteiro**
  (`CHAT_ACT_UNKNOWN_REFERENCE`) — o precedente é o refino de código SCO, que recusa a
  permutação inteira quando um código aparece do nada.
- **A conversa é presa a uma revisão.** `chat_sessions.base_review_revision_id` é fixado na
  abertura e não segue a revisão corrente: uma conversa que andasse com o job responderia
  sobre uma folha diferente da que gerou a pergunta.
- **"Ainda não sei" é saída de contrato.** `answer_kind="uncertain"` exige `open_question`
  preenchida. Um agente que sempre responde ensina o revisor a confiar no palpite; um que
  declara a dúvida devolve a pergunta certa para a folha.
- **Conteúdo fica no banco, nunca em log.** Pergunta e resposta vivem em `chat_turns`, como
  o `raw_text` do `packet_json` já vive em `review_revisions`. Log e `AuditRecord` levam
  apenas ids, estágio, duração, código estável e lineage
  ([Observability](../operations/OBSERVABILITY.md)).

A fatia 1, entregue com este ADR, é **100% offline**: a tarefa `review-chat@1.0.0` é servida
por fixture sintética injetada explicitamente (`make dev-worker-fixtures`), e sem suíte
injetada o turno falha com `CHAT_PROVIDER_UNAVAILABLE` sem construir provider algum —
inclusive com `CROQUITODXF_REAL_PROVIDERS_ENABLED` ligado. A via paga real é assunto de
outro ADR: ela traz consentimento de gasto, teto por sessão e roteamento de modelo, que este
não decide.

`review-chat` é a **primeira tarefa imagem+texto** do repositório. As duas famílias
anteriores tinham uma evidência só, e `input_digest` era o digest dela; aqui há duas, e
escolher uma faria o lineage descrever metade do que foi enviado. O digest passa a ser o do
envelope canônico `{"image_sha256": …, "text_sha256": …}`
([Prompt Contracts](../ai/PROMPT_CONTRACTS.md)).

## Alternativas

- **Responder no request path da API.** Rejeitada: contraria `services/api/AGENTS.md`,
  prende um worker HTTP por segundos de latência de modelo e acopla a API a um provider.
- **Deixar o agente aplicar o ato e oferecer desfazer.** Rejeitada. Desfazer não é o mesmo
  que não fazer: a decisão de leitura é imutável por construção
  ([ADR-0022](0022-declared-rectification-of-review-decisions.md)), e um ato criado por
  agente traria uma `HumanDecision` sem humano — exatamente o que o
  [ADR-0006](0006-human-review-and-provenance.md) proíbe.
- **Rascunho como texto livre para o revisor copiar.** Rejeitada: texto livre não é
  verificável. Rascunho tipado permite conferir cada id contra o snapshot antes de mostrar
  qualquer coisa, e permite que a tela preencha o formulário sem interpretar prosa.
- **Reusar `disagreement-review` em vez de criar tarefa.** Rejeitada: `template_hash` é a
  identidade do prompt no lineage já gravado, e reaproveitar o texto reescreveria a
  proveniência de leituras existentes. Tarefa nova nasce com versão e ramo próprios.
- **Recortar a evidência antes de enviar ao modelo.** Rejeitada nesta fatia: a dúvida do
  revisor costuma ser justamente sobre o entorno ("esse traço continua?"), e um recorte
  decidido pelo sistema esconderia o contexto que a pergunta pede. A página inteira é o
  contexto; economia de token é problema da fatia paga.
- **Permitir rascunho de aprovação ou de calibração.** Rejeitada: aprovação é declaração
  nominal com verificações assinadas ([ADR-0014](0014-scope-criteria-acknowledgement-at-approval.md)),
  e sugerir o texto dela é sugerir a assinatura.

## Consequências

### Positivas

- O revisor tem com quem conferir a leitura da folha sem sair da tela, e o que ele recebe é
  um formulário preenchido — não uma prosa para reinterpretar.
- Cada turno fica registrado com pergunta, resposta e lineage (provider, modelo, versão de
  prompt, digest, latência, tokens, custo estimado), inclusive quando o turno é recusado.
- A fila e o padrão de polling já existiam: não há infraestrutura nova, e o roteamento sai
  do campo `command` sem tocar `infra/main.tf`.
- A recusa por id desconhecido é um gate real e medido, não uma promessa de prompt.

### Negativas

- O usuário acompanha um estado assíncrono em vez de ver a resposta aparecer na hora.
- Uma linha `RUNNING` órfã (processo morto após o claim) exige intervenção operacional; não
  há lease com expiração nesta versão, exatamente como no export e no traçado.
- As tabelas `chat_sessions`/`chat_turns` nascem pelo `create_schema` aditivo; o repositório
  continua sem runner de migração, dívida registrada e não resolvida aqui.
- Um turno por vez por sessão é uma limitação real: perguntas paralelas sobre a mesma folha
  esperam. Duas respostas sem ordem entre si não seriam uma conversa.
- A fixture da fatia 1 cita o par sintético canônico do repositório. Contra um job real cujo
  snapshot não o contém, o turno é recusado com `CHAT_ACT_UNKNOWN_REFERENCE` — é o portão
  funcionando, mas significa que `make dev-worker-fixtures` só produz resposta útil sobre
  uma revisão semeada com esse par.

## Riscos e mitigação

| Risco | Mitigação |
|---|---|
| Agente confirmando leitura ou aprovando cena | Nenhum caminho de escrita no handler; o ato humano continua sendo o comando existente |
| Rascunho citando id de outra folha | Conferência contra o snapshot da revisão-base; turno inteiro recusado |
| Valor de medida inventado ou reescrito na resposta | Regra no template e no contrato; a resposta cita `reading_id` e a folha continua sendo a fonte |
| Prompt injection escrito no croqui ou na pergunta | Folha e mensagem declaradas dados não confiáveis no template; saída restrita ao schema estrito |
| Pergunta ou resposta vazando em log | Conteúdo só em banco; log e auditoria levam ids, estágio e códigos |
| Chamada paga acidental na fatia offline | Sem suíte injetada o turno falha com `CHAT_PROVIDER_UNAVAILABLE` sem construir provider |
| Conversa respondendo sobre uma folha que mudou | Revisão-base fixada na abertura da sessão e nunca atualizada |

## Rastreabilidade

- Requirements: ACC-GUA-001
- Supersedes: none
- Superseded by: none
