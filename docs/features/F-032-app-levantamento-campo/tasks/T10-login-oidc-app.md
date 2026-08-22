# Task Contract — F-032 / T10: login OIDC no app com tolerância a expiração offline

- Feature: F-032 — [feature.md](../feature.md)
- Plano pai: [plan-sync.md](../plan-sync.md) (tarefa T10)
- Depende de: T7 (integrada). Independente de T8/T9 (nenhuma chamada de API aqui —
  o SyncEngine da T9 consumirá o token via interface desta tarefa).
- Superfície de design: prancha 6c do DAP rev.1 (aprovada) — "login expirado
  offline: coleta continua, reautenticação só ao enviar". Nenhuma superfície nova
  fora dela (sem tela de login custom — o redirect do Keycloak é a tela).
- Baseline declarada: portões verdes na branch após o commit da onda anterior
  (registro em [evidence-sync.md](../evidence-sync.md)).

## Goal

Dar identidade ao técnico no aparelho: login OIDC (Keycloak, papel
`field_technician`) no padrão do repositório, com sessão persistente entre
reinícios offline e um estado explícito "reautenticação necessária" que NUNCA
bloqueia a coleta — só o envio (prancha 6c).

## Contexto verificado (ler antes de editar)

- `apps/web/src/auth.ts` — padrão OIDC do repositório (`oidc-client-ts`):
  `UserManager` condicional a `VITE_OIDC_AUTHORITY`/`VITE_OIDC_CLIENT_ID`,
  `response_type: "code"`, `scope: "openid profile"`, `automaticSilentRenew`,
  `silent_redirect_uri` dedicado (`silent-renew.html` — comentário sobre o
  incidente de 2026-08-19 se essa URI faltar), funções de módulo
  `signIn`/`signOut`/`readSession`/`renewAccessToken`.
- `apps/web/src/silent-renew.ts` — entry mínimo do iframe de renovação.
- Diferença deliberada do campo vs. escritório: `apps/web` usa
  `WebStorageStateStore` sobre `sessionStorage`; o app de campo precisa sobreviver
  a reinício do navegador dias depois, offline → usar `localStorage` no
  `userStore` e tratar token expirado como estado, não como logout.
- `apps/field/src/ui/FieldApp.tsx` e `apps/field/src/ui/` — shell atual do app
  (integração mínima: estado de identidade no AppBar/painel, sem redesenhar telas).
- `apps/field/AGENTS.md` — regras do workspace (domínio puro, persistência antes de
  feedback visual). O login NÃO passa pelo outbox.
- `apps/field/vite.config.ts` — para registrar o entry `silent-renew.html` do app.

## Comportamento exigido

1. Módulo novo `apps/field/src/auth/` (espelho adaptado de `apps/web/src/auth.ts`):
   - `UserManager` condicional às envs `VITE_OIDC_AUTHORITY` /
     `VITE_OIDC_CLIENT_ID` (sem env → app opera em modo local sem identidade, como
     hoje; nada quebra).
   - `userStore` sobre `localStorage` (sessão sobrevive a reinício offline).
   - `silent-renew.html` + entry próprios do app; silent renew só faz sentido
     online — falha silenciosa de renovação NÃO derruba a sessão local.
   - API do módulo: `signIn()`, `signOut()`, `readIdentity()` →
     `{subject, name?, roles, tenant}` ou `null`, `getFreshAccessToken()` →
     token válido ou `AUTH_REAUTH_REQUIRED` (erro tipado/estado, não exception
     string), a ser consumido pela T9.
2. Estados de identidade (máquina explícita, testável, em módulo puro):
   `signed_out` | `active` | `expired_offline` (token vencido, sem rede) |
   `reauth_required` (vencido, com rede). Transições cobertas por teste unitário.
   Em `expired_offline`/`reauth_required` a coleta continua integral; apenas o
   envio (T9) exigirá `active`.
3. UI mínima conforme 6c: indicador de identidade no shell (nome/estado) +
   ação "Entrar"/"Entrar novamente" quando aplicável. Nenhuma tela nova além
   disso; cor nunca é o único indicador (convenção do repo).
4. Papel: `readIdentity()` expõe `roles` do token (claim `realm_access.roles`,
   como `croquito_core/oidc.py:83-101` lê no backend); o app apenas EXIBE aviso se
   `field_technician` estiver ausente — autorização de verdade é do backend.
5. Testes (vitest): máquina de estados; `getFreshAccessToken` nos 4 estados
   (com `UserManager` fake — sem rede real); app sem env OIDC continua operando
   (modo local).

## Out of scope (não tocar)

- SyncEngine/transporte (T9 consome a interface; não implementá-la aqui).
- `services/**`, `apps/web/**`, realm Keycloak (criação de client/papel é ato
  humano — gate registrado no plano).
- Outbox/domínio de coleta (login não passa pelo outbox).
- Não "consertar" área alheia se um portão reprovar fora do escopo.

## Validação (comandos reais, nesta ordem)

```bash
cd /Users/danielcampos/workspace/daniel/croquito-f032
npm --workspace @croquito/field run test -- --run
npm --workspace @croquito/field run check
make check
make test
```

## Gates nomeados

- COMMIT forbidden (revisão e commit são do modelo principal).
- Papel `field_technician` + path do app no realm = ato humano, fora desta tarefa.

## Report

Encerrar com o `BUILD REPORT` completo (todos os campos), incluindo as envs novas
esperadas (`VITE_OIDC_*` do app de campo) e qualquer decisão de UX tomada dentro da
prancha 6c.
