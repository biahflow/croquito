# T3 — A tela de login do mock aprovado

Task Contract no formato do [template global](../../../engineering-os/templates/task.md),
derivado do [plano válido](../plan.md). Autossuficiente. Os gates humanos desta superfície
estão **fechados**: visual aprovado (mock revisão 2, 2026-08-18), texto aprovado
(2026-08-18, conjunto abaixo), pílula de ambiente decidida (só homologação, 2026-08-18).

## Identity

```text
feature_id: F-007
task_id: T3
parent_plan: docs/features/F-007-tela-de-login/plan.md
depends_on: [T2]
```

## Goal

O estado sem sessão da SPA vira a tela aprovada na revisão 2 do
[mock](../mock/README.md): marca, promessa, CTA com peso de CTA, card de convite, estado de
erro legível — responsiva de 360px a desktop como exceção declarada, sem **nenhuma** peça da
casca das jornadas antes da sessão (ADR-0032, D3).

## Texto aprovado (usar exatamente; mudar texto é gate humano novo)

- Promessa: **"Do croqui ao orçamento."**
- Rótulo do CTA: **"Entrar"**
- Frase do convite: **"O acesso nasce por convite. Peça o seu a quem administra sua
  organização."**
- Ambiente indisponível: **"O ambiente está indisponível agora. Tente de novo em instantes —
  se persistir, avise a operação."**
- Título da aba em `/login`: **"Entrar — Croquito"**

## Scope

- `apps/web/src/App.tsx`: o estado `/login` (placeholder deixado por T2) vira a tela do
  mock; a casca — topbar, pílula de schema, alternância de jornada — renderiza **somente**
  com sessão; o aviso de OIDC não configurado e o estado "ambiente indisponível" viram
  estados legíveis da própria tela (não um `<p>` solto).
- `apps/web/src/styles.css`: classes novas `.login-*`; a exceção de responsividade ao
  `min-width: 1180px` global declarada em comentário (o `min-width` **continua** valendo
  para as jornadas); cores SÓ da tabela de tokens do
  [Design System](../../../engineering/DESIGN_SYSTEM.md) — as cinco regras de uso valem
  (`--accent` só preenchimento com `--accent-ink` por cima; texto/traço verde é
  `--accent-text`); tamanhos/espaçamentos/raios novos do mock são valores **aprovados na
  revisão 2** e devem ser citados como tal em comentário.
- Espaço do login federado: o card nasce com o divisor e a posição do botão "Entrar com
  Google" do mock, mas o botão **não é renderizado** — a condição de render (identity
  provider configurado) é da F-008; nesta task o slot existe no markup/CSS e a condição
  resulta falsa com o realm atual. Nem desabilitado, nem oculto por CSS: **não renderizado**
  (critério 9).
- Pílula de ambiente: aparece **somente em homologação** (decisão humana de 2026-08-18).
  Mecanismo delimitado: derive do hostname de homologação conhecido
  (`croquito-hml.biahflow.ai`) ou de mecanismo de build/env **já existente** no app — não
  crie env var nova sem necessidade; a escolha fica comentada no código e no relatório.
- `apps/web/src/App.test.tsx`: asserções da tela (promessa presente, CTA presente, casca
  ausente sem sessão, botão Google ausente).

## Out of Scope

- Lógica de rota/rebote — entregue por T2; se parecer errada, pare e reporte, não conserte.
- `apps/web/src/auth.ts`; `deploy/nginx.conf`; tema do Keycloak (T4).
- Copiar código de `mock/login.html` — o próprio mock proíbe ("Nada aqui deve ser copiado
  para apps/web como código"); o mock é referência visual, não fonte.
- Tornar as jornadas responsivas.
- Qualquer texto fora do conjunto aprovado acima.

## Acceptance Criteria

1. Em 390px e em 1440px: sem barra de rolagem horizontal, CTA alcançável sem rolagem
   (critério 2; checado no dev server com viewport emulado e registrado com capturas).
2. Fidelidade ao mock aprovado: composição, hierarquia e peso do CTA conferidos contra
   `mock/01-login-desktop.png` e `mock/02-login-celular.png` (checado por comparação visual;
   capturas arquivadas no relatório).
3. Sem sessão, nenhuma peça da casca aparece (teste automatizado; critério de D3).
4. Botão "Entrar com Google" ausente do DOM com o realm atual (teste automatizado;
   critério 9).
5. Pílula de ambiente presente sob hostname de homologação e ausente fora dele (teste
   automatizado do mecanismo escolhido).
6. `make check` e `make test` verdes; nenhum teste removido ou relaxado.

## Validation

```text
baseline: make check e make test → verdes após T2 integrada
required: full: make check
          test: make test
          web:  npm --workspace @croquito/web run test
          dev:  npm --workspace @croquito/web run dev (conferência visual 390/1440)
```

## Required Capabilities

```text
READ:     o repositório (mock/ e DESIGN_SYSTEM.md em particular)
WRITE:    apps/web/src/App.tsx, apps/web/src/styles.css, apps/web/src/App.test.tsx, somente
VALIDATE: make check; make test; dev server com viewport emulado
COMMIT:   forbidden
```

## Context to Read First

1. `apps/web/AGENTS.md` e o [Design System](../../../engineering/DESIGN_SYSTEM.md) —
   inclusive "O que ainda não é sistema": não invente escala tipográfica/raio/espaçamento
   além do que o mock aprovado fixa.
2. [mock/README.md](../mock/README.md) — o que a revisão 2 aprova, o que reserva, e as
   decisões de desenho listadas.
3. `apps/web/src/styles.css` — tokens de `:root` (linha 22) e classes existentes
   (`.topbar` 77, `.button-primary` 436, `.context-bar` 459) para reusar padrão, não
   duplicar.

## Known Risks

- Usar `--accent` como cor de texto (contraste 2,2:1 — proibido; é `--accent-text`).
- A exceção de responsividade vazar para as jornadas — o `min-width` global não muda.
- "Prefeitura de Niterói" do mock é exemplo, não dado real — não vai para o código.

## Human Gates

- Nenhum aberto: visual, texto e pílula decididos e datados acima. Mudança em qualquer um
  reabre o gate — pare e reporte.

## Reporting

Encerre com o `BUILD REPORT` completo do
[contrato do Builder](../../../engineering-os/agents/builder.md) e grave o mesmo conteúdo em
`docs/features/F-007-tela-de-login/tasks/T3-build-report.md`.
