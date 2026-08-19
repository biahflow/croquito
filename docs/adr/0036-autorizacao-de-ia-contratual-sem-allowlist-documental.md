# ADR-0036: Autorização de IA contratual, sem allowlist documental por digest

Status: Proposed
Data: 2026-08-19
Responsável: Engineering

## Contexto

O caminho hospedado (HML/produção) exigia dois portões independentes antes de qualquer
documento sair para provider pago: entitlement contratual ativo do tenant + consent por
job (`ai_processing_consents`/`tenant_ai_processing_entitlements`, ver
[ADR-0012](0012-contractual-ai-processing-entitlements.md)), **e** o `sha256` exato do
upload presente em `CROQUITO_AI_EXTRACTION_ALLOWED_DIGESTS`, variável de ambiente do
deploy do worker (`.github/workflows/deploy-hml.yml`), nascendo vazia de propósito
(D6 do [ADR-0035](0035-suite-hospedada-openai-anthropic-direto.md)).

O ADR-0035 já registrava essa allowlist como pendência: "rota de plataforma dedicada
para administrar a allowlist de digest (hoje é variável do workflow de deploy, editada
por PR)". F-012 é essa operação virando produto — croquito é SaaS onde um cliente sobe
N documentos por dia; exigir um PR de deploy por documento não escala e não é o desenho
que a F-012 constrói (tela de plataforma, entitlement por tenant, consent automático por
job). O ritual manual — copiar `sha256` do manifest, editar o workflow, abrir PR, merge,
redeploy — está descrito em
[RUNBOOK_VALUATION_TOCA_ACCEPTANCE.md](../operations/RUNBOOK_VALUATION_TOCA_ACCEPTANCE.md)
e em [HML.md](../operations/HML.md), e foi o obstáculo operacional que motivou esta
decisão.

## Decisão

**O gate de envio de documento a provider pago no caminho hospedado passa a ser
integralmente: entitlement contratual ativo do tenant + consent por job + teto de custo
por invocação + kill switch.** A allowlist de digest deixa de existir nesse caminho:
`LocalWorkerSettings.ai_extraction_allowed_digests`, o parse de
`CROQUITO_AI_EXTRACTION_ALLOWED_DIGESTS` em `from_environment` e a checagem em
`_handle_upload` (`services/worker/src/croquito_worker/local_queue.py`) são removidos.
Qualquer PDF de um tenant com entitlement ativo e consent registrado sai para o provider
sem verificação adicional por documento — decisão de produto ratificada pelo usuário em
2026-08-19.

A allowlist por digest **permanece** no caminho offline de eval
(`extraction_eval.py:152-194`, `allowlisted_digests`/`authorize_page`): ali não existe
tenant, não existe entitlement, e o operador que roda `make extraction-eval` ou o CLI de
medição é a mesma pessoa que autoriza o documento — a allowlist ainda é o vínculo que
impede um PNG solto no diretório de virar chamada paga sem decisão humana explícita. Os
dois caminhos usam a mesma variável de ambiente por nome
(`CROQUITO_AI_EXTRACTION_ALLOWED_DIGESTS`) mas por funções diferentes e sem acoplamento
de código: o worker hospedado nunca lê essa variável depois desta decisão.

## Alternativas

- **Rota de plataforma para administrar a allowlist de digest.** Era a pendência
  registrada no ADR-0035. Rejeitada: mesmo com UI, continuaria exigindo um ato humano
  por documento antes de cada extração — o problema não é a interface do ritual, é o
  ritual em si numa operação SaaS de N documentos por tenant. O que o produto precisa
  controlar é *quem* pode mandar documento a provider (entitlement por tenant), não
  *qual* documento especificamente.
- **Allowlist com expiração automática ou por lote (ex.: por projeto, não por
  documento).** Reduziria o atrito sem eliminá-lo, mas mantém um segundo estado a
  sincronizar com o entitlement e não fecha a lacuna de escala: ainda seria preciso um
  ato humano por lote. Rejeitada pelo mesmo motivo da alternativa anterior.

## Consequências

### Positivas

- Zero redeploy por documento: o fluxo de upload → extração paga passa a depender só de
  entitlement (ato de plataforma, por tenant, não por documento) e consent (automático
  por job quando o entitlement está ativo).
- Remove um segundo estado de autorização que podia divergir do entitlement (allowlist
  vazia com entitlement ativo já bloqueou testes e o próprio piloto de HML).
- O runbook de aceite de medição e o HML.md perdem um passo manual — atualizado pela T4
  desta feature.

### Negativas

- **Supersede parcialmente o D6 do [ADR-0035](0035-suite-hospedada-openai-anthropic-direto.md).**
  O teto por invocação (`CROQUITO_AI_MAX_ESTIMATED_COST_USD`) e o kill switch
  (`CROQUITO_REAL_PROVIDERS_ENABLED`) permanecem exatamente como o D6 os descreveu; só a
  cláusula de allowlist por digest é substituída. O ADR-0035 não é reaberto nem
  reescrito — esta decisão registra o que muda.
- Qualquer documento de um tenant com entitlement ativo sai para provider, sem uma
  segunda barreira por arquivo. O controle de "qual documento" deixa de existir; quem
  quiser impedir um upload específico de gerar extração paga precisa suspender o
  entitlement do tenant (ato de plataforma, mais grosso que revogar um digest).
- A allowlist do caminho offline (`extraction_eval.py`) e a variável de ambiente que a
  alimenta continuam existindo com o mesmo nome; alguém lendo só o nome da variável, sem
  saber que o worker hospedado parou de consumi-la, pode presumir proteção que não existe
  mais nesse caminho — mitigado pela referência cruzada nesta decisão e pela atualização
  de `HML.md`/`RUNBOOK_VALUATION_TOCA_ACCEPTANCE.md` na T4.

## Riscos e mitigação

| Risco | Mitigação |
|---|---|
| Um tenant com entitlement ativo sobe documento sensível por engano e ele sai para provider sem segunda checagem | Consent por job continua exigindo `authorization_source = 'contract'` e entitlement `ACTIVE` — suspender o entitlement do tenant bloqueia todo upload futuro; não há mitigação por documento individual nesta decisão |
| Alguém reintroduz a allowlist no caminho hospedado por hábito ao copiar `extraction_eval.py` como referência | `local_queue.py` não importa nem referencia `extraction_eval.py`; o teste que cobria a allowlist hospedada foi removido, então uma reintrodução precisaria de teste novo, não reativação de um existente |

## Rastreabilidade

- Requirements: NFR-SEC-004 (retenção e escopo do processamento), NFR-OPS-002 (custo
  estimado e teto), ADR-0012 (autorização contratual — a política que este ADR mantém
  como único gate) — ver `docs/nfr/` e `docs/adr/0012-contractual-ai-processing-entitlements.md`.
- Decisões relacionadas: [ADR-0012](0012-contractual-ai-processing-entitlements.md)
  (entitlement e consent contratual — inalterado), [ADR-0035](0035-suite-hospedada-openai-anthropic-direto.md)
  (D6 parcialmente superseded — teto e kill switch preservados, allowlist removida).
- Especificação e execução na feature
  [F-012](../features/F-012-operacao-saas-autorizacao-ia/feature.md), task T1.
- Supersedes: none (revisita parcialmente o D6 do ADR-0035, sem superseder o documento
  inteiro)
- Superseded by: none
