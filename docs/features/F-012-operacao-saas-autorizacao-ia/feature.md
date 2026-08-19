# F-012 — Operação SaaS da autorização de IA

## Status

`IN_PROGRESS`

> Selecionada e aprovada por decisões humanas de 2026-08-19, na sequência imediata da
> F-009: o usuário vetou os dois rituais manuais que a ativação deixou — entitlement
> por curl com token pescado do DevTools e allowlist de digest por env var (redeploy
> por documento). Diretriz literal: "isso já nasce com a visão de SaaS, não posso ter
> esses gargalos/travas". A postura de segurança foi ratificada na aprovação do
> plano: sem allowlist documental, qualquer PDF de tenant com entitlement ATIVO sai
> para provider — consentimento 100% contratual, com teto por invocação e kill
> switch.

## Priority

`HIGH` — o cliente vai homologar subindo vários PDFs; sem esta feature, cada
documento exige um merge+deploy e cada tenant exige um curl artesanal.

## Problem

A F-009 ligou os providers reais, mas a operação ficou manual em dois pontos:

- **Entitlement por curl**: a única rota de plataforma é o `PUT` do entitlement; não
  há GET de estado, não há listagem de tenants, não há tela. O operador precisa
  pescar o próprio token no DevTools — não é vulnerabilidade (o token de sessão da
  SPA é o modelo OIDC normal; as chaves de provider nunca vão ao navegador), mas é
  ritual inaceitável para SaaS.
- **Allowlist por digest**: cada PDF novo exige sha256 em
  `CROQUITO_AI_EXTRACTION_ALLOWED_DIGESTS` no workflow e um deploy. Redeploy por
  documento não escala para homologação de cliente.

A SPA não conhece papéis (decisão deliberada: autorização é do backend) e não tem
área de plataforma; `tenant_id` não tem tabela própria — vive no Keycloak e como
coluna nas tabelas de domínio.

## Desired Outcome

O operador de plataforma entra no produto, vê a jornada "Plataforma" (só quem tem o
papel), ativa/desativa o entitlement de qualquer tenant com `agreement_reference` —
e a partir daí o cliente sobe quantos PDFs quiser, sem digest, sem curl, sem
redeploy. O gate de envio a provider passa a ser integralmente: entitlement
contratual por tenant + consent automático por job + teto de custo por invocação +
kill switch.

## Scope

- Remoção da allowlist de digest do caminho hospedado (worker + deploy), com
  ADR-0036 registrando a postura; caminho offline de eval (`extraction_eval`)
  intocado.
- `GET /v1/me` (subject, tenant_id, roles) — como a SPA decide mostrar a jornada.
- `GET /v1/platform/tenants` (DISTINCT-union entitlements ∪ projects ∪ uploads +
  estado do entitlement) e `GET /v1/platform/tenants/{id}/ai-processing-entitlement`
  (200 sempre; disabled/nulos quando nunca ativado).
- Jornada "Plataforma" na SPA: kind `plataforma` (`?plataforma=`), botão condicional
  ao papel, lista de tenants com ativação/desativação inline + campo "ativar tenant
  novo" (tenant só-Keycloak não tem pegada no banco).
- Runbook do HML sem os passos manuais; inventário SaaS F-013..F-017 no ROADMAP.

## Out of Scope

Convite/e-mail (F-008, BLOCKED); UI de membros do tenant (F-013); entidade tenant e
onboarding self-service (F-014); recriar job de upload existente (F-015); rotação de
chaves (F-016); custo agregado por tenant e trilha de auditoria na tela (F-017);
BFF; mudanças no PUT do entitlement; caminhos valuation/eval offline.

## Acceptance Criteria

1. `make check` e `make test` verdes; snapshot OpenAPI atualizado por ato
   deliberado com diff só de adição.
2. `ai_extraction_allowed_digests` e `AI_EXTRACTION_NOT_ALLOWLISTED` ausentes do
   worker; testes de eval offline passam sem edição.
3. GETs de plataforma exigem `platform_operator` (403 sem papel); tenant
   nunca-ativado responde 200 disabled; tenant com upload aparece na listagem;
   ciclo ativar→refletir→revogar→refletir coberto por teste.
4. Botão "Plataforma" só aparece com o papel (ausente, não desabilitado);
   `?plataforma=` faz round-trip e sobrevive ao login; mutação envia
   `Idempotency-Key` (provado em teste); erro problem+json legível e persistente.
5. Runbook do HML sem digest/redeploy por documento; ativação descrita pela tela.

## Human Gates

Merge do PR #19 da F-009 (pré-requisito, com aceite do ADR-0035); aceite do
ADR-0036; merge desta feature (= deploy).

## References

- [Plano de execução](plan.md)
- [F-009](../F-009-suite-hospedada-sem-aws/feature.md)
- [ADR-0035](../../adr/0035-suite-hospedada-openai-anthropic-direto.md)
- [Operação do HML](../../operations/HML.md)
- [API Contract](../../architecture/API_CONTRACT.md)
