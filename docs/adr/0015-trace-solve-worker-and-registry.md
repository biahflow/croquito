# ADR-0015: Traçado em lote executa no worker com registro próprio de solves

Status: Accepted
Data: 2026-08-12  
Responsável: Engineering

## Contexto

O estágio de traçado ([Trace Stage](../architecture/TRACE_STAGE.md)) está completo no
worker e validado em dois casos dourados, mas só é acionável pela CLI
(`croquito-demo solve-trace`) com arquivos JSON em disco. A sessão autenticada não
tinha nenhum caminho para aceitar um traçado: o profissional que revisou as cotas na tela
não conseguia transformar a extração aceita em cena métrica sem um operador rodando
comandos locais.

`solve_trace` não é trabalho de request path. Ele constrói a topologia de junções, agrupa
as junções em faixas ortogonais, resolve o sistema de vãos com precedência da cota,
resolve cada grupo de detalhe com escala própria, posiciona cotas, notas, balões, legenda
e carimbo desviando de colisões, e devolve uma `SceneRevision` inteira. A duração cresce
com o número de propostas aceitas e de leituras associadas, e
`services/api/AGENTS.md` é explícito: a API "não renderiza PDF, chama modelos nem gera DXF
no request path".

Também não havia onde registrar o ato: o aceite em lote (`TraceAcceptance`) é a declaração
humana que a regra de exportação exige para geometria `approximate`, e nenhuma tabela
guardava quem aceitou o quê, contra quais versões e com que desfecho.

## Decisão

O traçado em lote roda no worker, acionado por um comando idempotente na mesma fila de
processamento, e cada aceite é registrado em uma tabela própria tenant-scoped. O padrão é
o do [ADR-0013](0013-export-worker-and-artifact-registry.md), estendido com um desfecho
que o export não tem: conflito de versão é resultado consultável, não erro.

- `POST /v1/jobs/{job_id}/trace-solves` valida ownership, papel profissional, versões-base
  e a existência de cada proposta citada; constrói o `TraceAcceptance` com identidade do
  JWT, `decided_at` do relógio do servidor e `acceptance_id` gerado no servidor; persiste
  a linha `QUEUED`, commita e só então publica `{"command": "solve_trace_scene", ...}`.
- A consistência interna do aceite é verificada construindo o próprio contrato do
  traçado. Não existe uma segunda definição do aceite na API: o modelo do worker é
  importado, como já se faz com `VisionProposalSet`.
- As associações efetivas são as `selected_associations` da revisão corrente sobrepostas
  pelo corpo, por `reading_id`. A associação explícita continua obrigatória; proximidade
  em pixels nunca vira associação.
- O worker faz claim atômico `QUEUED|FAILED → RUNNING`, recarrega as versões correntes e,
  se a revisão de leitura ou a cena avançaram, grava `solve_status="conflict"` com
  `failure_code="REVISION_MOVED"` e status `COMPLETED`.
- Um traçado resolvido cria duas linhas na mesma transação: a `SceneRevision` nova (não
  aprovada) e a revisão de leitura que registra o aceite em `trace_acceptance_json`. Uma
  corrida na chave única `(job_id, version)` desfaz as duas e vira o mesmo `conflict`.
- `GET /v1/jobs/{job_id}/trace-solves/{trace_solve_id}` devolve status, desfecho,
  blockers, leituras não aplicadas, contagens, escalas e os ids resultantes.

## Alternativas

- **Resolver no request path da API.** Rejeitada: contraria `services/api/AGENTS.md`,
  prende um worker HTTP por segundos e acopla o motor de geometria ao processo que
  autentica.
- **Devolver `409 REVISION_CONFLICT` quando a revisão andou durante a execução.** Rejeitada:
  o cliente já recebeu `202` e não tem mais um request para receber o erro. Um estado
  terminal consultável é a única forma honesta de contar o que aconteceu depois do aceite.
- **Reusar `export_artifacts` ou `selected_associations_json` para guardar o aceite.**
  Rejeitada: mistura artefato publicado com ato de revisão, e `selected_associations_json`
  é `reading_id → proposal_id`, incapaz de representar vão entre dois elementos ou vão
  declarado por âncoras sem quebrar todo cliente que já a lê.
- **Fila dedicada de traçado.** Rejeitada por ora, pelo mesmo motivo do ADR-0013: o campo
  `command` resolve o roteamento sem alterar `infra/main.tf`.
- **Aceitar o traçado já aprovado.** Rejeitada: aprovação é ato separado, ligada ao UUID
  exato da revisão ([ADR-0006](0006-human-review-and-provenance.md)); a cena traçada nasce
  não aprovada e passa pelos mesmos portões de exportação.

## Consequências

### Positivas

- O profissional aceita um traçado inteiro pela sessão autenticada, sem operador local.
- O aceite fica registrado com quem, quando, contra quais versões e com qual desfecho, e a
  revisão de leitura resultante carrega a declaração completa.
- Replay de mensagem não gera segunda cena; conflito não vira 500 nem cena duplicada.
- Blockers do domínio chegam ao cliente como códigos estáveis, prontos para virar as
  perguntas da tela de revisão.

### Negativas

- O usuário acompanha um estado assíncrono em vez de ver a cena aparecer na hora.
- Uma linha `RUNNING` órfã (processo morto após o claim) exige intervenção operacional;
  não há lease com expiração nesta versão, exatamente como no export.
- A tabela nova e a coluna `trace_acceptance_json` são criadas pelo `create_schema`
  aditivo; o repositório continua sem runner de migração, dívida registrada e não
  resolvida aqui.
- Um aceite grande pode ficar obsoleto entre a fila e a execução. O conflito é barato de
  detectar, mas quem aceitou precisa refazer o lote sobre as versões novas.

## Riscos e mitigação

| Risco | Mitigação |
|---|---|
| Cena traçada nascendo aprovada ou exportável | `approved=False` na gravação e `ensure_exportable()` intacto |
| Dois workers resolvendo o mesmo aceite | Claim atômico `UPDATE ... WHERE status IN ('QUEUED','FAILED')` mais unique de versão |
| Revisão avançando entre o aceite e a execução | Versões recarregadas após o claim; divergência vira `conflict` sem escrever geometria |
| Aceite de outro tenant resolvido | Toda query filtra tenant da mensagem; divergência falha alto sem escrever |
| Evidência do cliente vazando em falha | Só `failure_code` é persistido; a mensagem da exceção não é registrada |
| Blocker do solver escondido do revisor | Blockers viram issues críticas na cena e campo consultável no registro |

## Rastreabilidade

- Requirements: ACC-GUA-001, ACC-TOC-002
- Supersedes: none
- Superseded by: none
