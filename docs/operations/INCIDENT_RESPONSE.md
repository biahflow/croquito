# Resposta a incidentes

Status: Accepted baseline  
Responsável: Security / Platform / Product  
Última revisão: 2026-08-10

## Severidades

| Severidade | Exemplo | Resposta inicial alvo |
|---|---|---|
| SEV-1 | vazamento/cross-tenant, DXF incorreto publicado em massa | imediata |
| SEV-2 | export indisponível, provider outage sem fallback | até 1 hora |
| SEV-3 | job isolado, degradação parcial, custo anômalo | mesmo dia útil |
| SEV-4 | defeito sem impacto corrente | backlog priorizado |

Os tempos são objetivos operacionais do MVP, não SLA contratual.

## Processo

1. Detectar e abrir incidente com ID.
2. Nomear incident commander.
3. Conter: bloquear export, revogar URL/credencial ou desativar provider/feature.
4. Preservar evidência mínima sem copiar conteúdo desnecessário.
5. Avaliar clientes/dados afetados.
6. Mitigar e validar recuperação.
7. Comunicar por canal apropriado.
8. Encerrar somente após monitoramento.
9. Fazer post-mortem sem culpa para SEV-1/2.

## Incidentes de dados

- Acionar segurança/jurídico.
- Interromper acesso e rotear novos jobs para caminho seguro.
- Identificar objetos/tenants por audit metadata.
- Não expor conteúdo em tickets ou chat.
- Avaliar obrigações de notificação conforme contrato/lei.

## Incidentes de qualidade de IA

- Suspender auto-confirmação/export afetado.
- Congelar model/prompt versions e eval artifacts.
- Rodar golden comparison autorizada.
- Rebaixar candidate ou provider.
- Identificar exports derivados e avisar revisores.

## Post-mortem

Use [INCIDENT_TEMPLATE.md](../templates/INCIDENT_TEMPLATE.md). Ações possuem owner,
prazo, verificação e link para requisito/ADR quando estrutural.

