# Threat model

Status: Accepted baseline  
Responsável: Security / Engineering  
Última revisão: 2026-08-10

## Escopo

Upload, armazenamento, processamento, revisão e exportação na arquitetura MVP.
Reavaliar quando houver acesso público, integrações externas ou persistência longa.

## Ativos

- Documentos, imagens, cotas e scene graphs.
- Identidade, tenant e autorização.
- Chaves de fornecedores e IAM roles.
- DXFs e relatórios.
- Budget de APIs/infraestrutura.
- Integridade do golden dataset e prompts.

## Atores e fronteiras

- Usuário autenticado pode ser malicioso ou ter conta comprometida.
- PDF e texto dentro dele são conteúdo não confiável.
- Browser não é fonte de autorização.
- Provedores são subprocessadores externos.
- Worker processa bytes potencialmente malformados.

## Ameaças e controles

| Categoria | Ameaça | Controle principal |
|---|---|---|
| Spoofing | JWT roubado | OIDC, TTL, TLS, revogação e MFA quando habilitado |
| Tampering | Troca de object key/revision | IDs server-side, digest, ownership e optimistic lock |
| Repudiation | Negar aprovação | audit event com usuário, revisão e timestamp |
| Information disclosure | Cross-tenant ou URL vazada | tenant filters, signed URL curta, S3 privado |
| Denial of service | PDF enorme/zip bomb/model loop | limites, validation, quotas, retries limitados, WAF |
| Elevation | Worker/role ampla | container sem privilégio e IAM least privilege |
| Prompt injection | Texto instrui o modelo | documento tratado como data, schema e sem tools |
| Supply chain | Biblioteca/SDK comprometido | pinagem, CVE scan, review de dependência |
| Cost abuse | Reanálise repetida | rate limit, budget, idempotência e quota por tenant |
| Dataset poisoning | Gabarito alterado | manifest versionado, hash e aprovação do domínio |

## Upload seguro

- Allowlist PDF e validação de assinatura, não apenas MIME do browser.
- Limites de bytes, páginas e pixels.
- Timeout e memory limit para render.
- Sem execução de JavaScript, anexos ou links do PDF.
- Fargate task não privilegiada e filesystem temporário.
- Objetos nunca são servidos publicamente.

## Autorização

- Toda query inclui `tenant_id` derivado do token.
- IDs opacos não substituem autorização.
- Signed URL só é criada após ownership check.
- Admin actions usam role separada e CloudTrail.

## IA

- Sem credenciais ou identifiers pessoais no prompt.
- Sem tool calling para prompts de documento.
- Output validado antes de persistir.
- Payload logging de Bedrock desabilitado.
- Reprocessamento tem limite e trilha de auditoria.

## Verificação

- Testes negativos de autorização.
- Fuzzing/fixtures de PDF malformado.
- Scan de logs por padrões sensíveis.
- IAM policy review e Terraform static analysis.
- Fault injection de providers.
- Revisão trimestral durante desenvolvimento ativo ou após mudança material.
