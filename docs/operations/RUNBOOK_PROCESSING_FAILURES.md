# Runbook de falhas de processamento

Status: Accepted baseline  
Responsável: Platform / AI / CAD Engineering  
Última revisão: 2026-08-10

## Antes de agir

- Confirme `job_id`, stage, error code e attempt.
- Não abra imagens/respostas sem necessidade e autorização.
- Não reexecute em loop; preserve idempotency key.
- Não troque provider/model silenciosamente.

## `PDF_UNREADABLE`

1. Verificar validation metadata e limites.
2. Confirmar se assinatura/MIME é PDF.
3. Reproduzir somente com fixture autorizada.
4. Se malformado, pedir novo arquivo; não tentar ferramenta insegura.

## Render/CV failure

1. Verificar memory/timeout/task exit.
2. Confirmar page dimensions e pixel limits.
3. Reexecutar uma vez se infraestrutura.
4. Se determinístico, abrir defect com input digest, sem anexar documento.

## Textract failure

1. Conferir status/quota/permission.
2. Após retries, permitir continuação com `OCR_EVIDENCE_MISSING`.
3. Não promover leitura de um LLM por ausência do Textract.

## Um LLM falha

1. Verificar timeout, 429, 5xx, schema ou auth.
2. Retry conforme workflow.
3. Continuar somente para revisão; desabilitar auto-confirmation do item.
4. Se sistêmico, ativar alerta e considerar pausar novos jobs.

## Dois LLMs falham

1. Job deve falhar, não gerar cena parcial aprovada.
2. Verificar provider health e secrets sem expô-los.
3. Permitir retry pelo usuário após restauração.

## Solver conflict

1. Verificar measurements/constraints e provenance.
2. Não remover constraint para “fazer caber”.
3. Criar issue com menor conjunto conflitante disponível.
4. Direcionar usuário à medida/hipótese necessária.

## `EXPORT_AUDIT_FAILED`

1. Revogar qualquer package URL.
2. Guardar error codes e exporter version.
3. Reproduzir com SceneRevision autorizada.
4. Corrigir exporter/scene invariant.
5. Rodar todos os CAD golden tests antes de republicar.

## Job preso

1. Conferir Step Functions execution e ECS task.
2. Se execução ativa sem heartbeat/progresso além do limite, abortar conforme
   procedure e marcar retryable.
3. Verificar objetos temporários/locks.
4. Reexecutar pela API idempotente, não manualmente pelo console.

## DLQ

Mensagens são triadas por error code. Re-drive só após corrigir causa e confirmar
que a ação é idempotente.

