# ADR-0013: Export DXF executa no worker com registro próprio de artefatos

Status: Proposed  
Data: 2026-08-10  
Responsável: Engineering

## Contexto

Até este marco o DXF só era gerado pela CLI (`croquitodxf-demo rectangle-export`). A
sessão autenticada não tinha caminho para produzir o pacote CAD, o que impedia o
primeiro DXF real mesmo depois de uma aprovação técnica válida.

Gerar o pacote é trabalho pesado e não determinístico em duração: `export_scene_package`
monta o documento, grava em disco, reabre com `ezdxf.recover`, roda nove checks de
auditoria, renderiza um preview com matplotlib e empacota cinco a seis arquivos. As
instruções em `services/api/AGENTS.md` são explícitas: a API "não renderiza PDF, chama
modelos nem gera DXF no request path".

Também não havia onde registrar o resultado: `ArtifactStore` só sabia presignar leitura
e upload de PDF, e nenhuma tabela guardava a chave do pacote, o digest ou a auditoria.

## Decisão

O export roda no worker, acionado por um comando idempotente na mesma fila de
processamento, e cada pacote publicado é registrado em uma tabela própria
tenant-scoped, lida apenas por URL assinada de curta duração.

- `POST /v1/jobs/{id}/exports` valida ownership, exige cena aprovada com `ApprovalRecord`,
  revalida `export_errors()` no servidor, persiste a linha `QUEUED`, commita e só então
  publica `{"command": "export_scene_package", ...}`.
- O worker despacha por `command` (o default `process_upload` preserva mensagens antigas),
  faz claim atômico `QUEUED|FAILED → RUNNING`, gera o pacote em diretório temporário por
  task e só envia o ZIP ao object store **depois** da auditoria aprovada.
- `export_artifacts` tem `UniqueConstraint(job_id, scene_revision_id, format)`: uma revisão
  aprovada tem no máximo um pacote, independente da `Idempotency-Key` usada.
- `GET /v1/jobs/{id}/exports/{export_id}` devolve `package_url` somente em `COMPLETED`,
  após conferir o prefixo `tenants/{tenant_id}/`.

## Alternativas

- **Gerar no request path da API.** Rejeitada: contraria `services/api/AGENTS.md`, prende
  um worker HTTP por segundos e acopla matplotlib e ezdxf ao processo que autentica.
- **Reusar `evidence_refs_json` da revisão de leitura para guardar a chave do pacote.**
  Rejeitada: mistura evidência de leitura, que é entrada da revisão, com artefato
  publicado, que é saída aprovada — e não tem onde registrar auditoria nem digest.
- **Fila dedicada de export.** Rejeitada por ora: uma fila com campo `command` resolve o
  roteamento sem alterar `infra/main.tf`. Uma fila separada volta a ser justificável
  quando export e ingestão tiverem perfis de latência ou de retry conflitantes.
- **Gravar o ZIP antes de auditar, marcando o registro depois.** Rejeitada: publicaria um
  pacote reprovado no object store, ainda que sem link.

## Consequências

### Positivas

- O request path continua barato e a API mantém apenas autorização e lifecycle.
- A publicação é atômica do ponto de vista do usuário: o ZIP só existe se a auditoria
  aprovou, e o link só é assinado quando o registro está `COMPLETED`.
- Replay de mensagem não regenera nem reenvia pacote; falha determinística não entra em
  loop de retry, e falha transitória de object store devolve a mensagem à fila.
- O digest e os checks ficam registrados, o que torna o pacote rastreável sem abrir o ZIP.

### Negativas

- O usuário precisa acompanhar um estado assíncrono em vez de baixar na hora.
- Uma linha `RUNNING` órfã (processo morto após o claim) exige intervenção operacional;
  não há lease com expiração nesta versão.
- A tabela nova é criada pelo `create_schema` aditivo; o repositório continua sem runner
  de migração, dívida registrada e não resolvida aqui.

## Riscos e mitigação

| Risco | Mitigação |
|---|---|
| Pacote publicado sem auditoria aprovada | `export_scene_package` levanta antes de montar o ZIP; upload ocorre só após sucesso |
| Dois workers exportando a mesma revisão | Claim atômico por `UPDATE ... WHERE status IN ('QUEUED','FAILED')` mais unique de destino |
| URL assinada vazando em log | `package_url` nunca é auditada nem registrada; só é devolvida na resposta |
| Cena de outro tenant exportada | Toda query filtra tenant da mensagem; divergência vai para DLQ sem escrever |
| Volume local antigo com versões duplicadas de cena | `CREATE UNIQUE INDEX` falha alto e o runbook manda recriar o banco local |

## Rastreabilidade

- Requirements: ACC-007, ACC-008, ACC-009, ACC-010
- Supersedes: none
- Superseded by: none
