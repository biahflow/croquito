# ADR-0051: Retenção por classe de objeto preserva a evidência de campo durável

Status: Accepted
Data: 2026-08-25 (aceito por ato humano na mesma data)
Responsável: Product / Engineering

## Contexto

A [F-030](../features/F-030-levantamento-de-campo-na-revisao/feature.md)
([ADR-0049](0049-evidencia-de-campo-na-revisao-do-escritorio.md)) leva a evidência de campo
— fotos ancoradas, análises, valores confirmados em foto — à revisão do escritório. Essa
evidência é **trabalho durável do cliente**: o levantamento de praça que sustenta a revisão,
a testemunha da cota, a classificação a confirmar.

A regra de retenção do bucket de artefatos, hoje, apaga tudo:

```hcl
# infra/main.tf — aws_s3_bucket_lifecycle_configuration.artifacts
rule {
  id     = "expire-ephemeral-artifacts"
  status = "Enabled"
  filter {}                                   # TODOS os objetos
  expiration { days = var.artifact_retention_days }   # default 7
}
```

O `filter {}` casa qualquer chave. Com sete dias de retenção, isso expira também os prefixos
que **não são efêmeros**:

- `tenants/{tenant}/jobs/{job}/field-evidence/...` — fotos, `analysis/`, valores confirmados;
- `tenants/{tenant}/surveys/{survey}/...` — mídia, `transcripts/`, `analysis/`, `export`.

Perder isso em sete dias é perda de dado do cliente. O escopo da
[T8](../features/F-030-levantamento-de-campo-na-revisao/tasks/T8-e2e-e-rollout.md) pede
retenção que **preserve** `surveys/` e `jobs/*/field-evidence/`.

### A restrição que fecha o desenho por prefixo

O filtro de lifecycle do S3 usa `prefix` **literal, ancorado à esquerda, sem curinga**. As
chaves nascem sob `tenants/{tenant}/…`, e o segmento que distingue durável de efêmero
(`surveys/`, `jobs/*/field-evidence/`) vem **depois** do `{tenant}` variável. Não existe
`prefix` que case `tenants/*/field-evidence/` entre tenants. Retenção por prefixo, portanto,
não resolve o problema desta base de chaves.

## Decisão

**Retenção por classe de objeto, marcada por tag na escrita.**

1. Objetos **efêmeros** recebem a tag `lifecycle-class=ephemeral` no `PutObject`:
   `tenants/*/uploads/`, `tenants/*/jobs/*/exports/`, `tenants/*/jobs/*/review/`,
   `tenants/*/estimate-rounds/`, `tenants/*/valuation-rounds/`.
2. A regra de expiração passa a filtrar por essa tag, e não por `filter {}`.
3. Objetos **duráveis** — `surveys/` e `jobs/*/field-evidence/` — nascem **sem** a tag e por
   isso **nunca** entram na expiração.

A mudança é **fail-safe**: enquanto o app não escrever a tag, a regra não casa nenhum objeto
e nada expira. O risco de perda de dado desaparece no momento do apply; a limpeza seletiva
dos efêmeros volta quando o app passa a taguear. O custo do interim é armazenamento de
efêmeros não expirados — não perda de dado.

### Implementação em duas partes

- **(a) Infra (este ADR / PR de infra):** a regra `expire-ephemeral-artifacts` troca
  `filter {}` por `filter { tag { key = "lifecycle-class", value = "ephemeral" } }`.
- **(b) App (fatia seguinte, fora deste PR):** os sites de escrita efêmera setam
  `Tagging=lifecycle-class=ephemeral` no `PutObject`, e o presign de upload força a tag no
  objeto que o browser grava. Sem (b), a expiração fica inerte — o estado seguro.

## Alternativas consideradas

- **Re-keyar os duráveis sob um prefixo top-level** (`durable/tenants/…`): resolveria por
  prefixo, mas exige migração das chaves já gravadas e reescrever todos os construtores de
  chave. Migração de dado existente por um ganho que a tag entrega sem mover byte.
- **Bucket separado para o durável:** duplica policy, observabilidade, CORS e KMS; a
  fronteira de retenção não justifica dois buckets.
- **Manter `filter {}`:** perde a evidência de campo em sete dias. Recusada — é o defeito.

## Consequências

- A mudança de retenção **exige aprovação humana** e `terraform plan`/`apply` revisados
  (`infra/AGENTS.md`: "Mudança de retenção exige ADR/aprovação"; "apply exige aprovação
  explícita"). Aceito por ato humano em 2026-08-25; o `terraform plan`/`apply` em HML segue
  como passo humano à parte.
- O teste de policy de lifecycle (a "policy de sete dias testada" do `infra/AGENTS.md`)
  precisa passar a exercitar a regra por tag; a atualização do teste acompanha a parte (a).
- Até a parte (b) existir, os efêmeros não expiram: aceitável como interim seguro, a ser
  fechado na fatia de tagging.
