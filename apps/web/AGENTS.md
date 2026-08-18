# Instruções para agentes — web

Estas regras estendem o [AGENTS.md](../../AGENTS.md). Leia também
[FDD](../../docs/product/FDD.md),
[API Contract](../../docs/architecture/API_CONTRACT.md) e
[Human in the Loop](../../docs/ai/HUMAN_IN_THE_LOOP.md). Para criar ou reestilizar tela, leia
antes o [Design System](../../docs/engineering/DESIGN_SYSTEM.md).

Para mexer na jornada de medição (`src/medicao/`), leia também
[Valuation Context](../../docs/architecture/VALUATION_CONTEXT.md), a seção "Medição de
obra" do [FDD](../../docs/product/FDD.md),
[ADR-0020](../../docs/adr/0020-local-homologation-server-for-valuation.md),
[ADR-0026](../../docs/adr/0026-medicao-hospedada-sessao-autenticada-minima.md) e
[ADR-0028](../../docs/adr/0028-medicao-na-api-v1-autenticada.md).

## Boundary

O web app apresenta projetos, status, revisão e exportação. Ele não resolve
geometria, escolhe consenso ou autoriza tenant por conta própria.

Ele carrega duas jornadas numa sessão OIDC só (ADR-0028, D9): a revisão do croqui
(`src/CroquiApp.tsx`) e a medição de obra (`src/medicao/`), com a fronteira em
`src/route.ts` e a casca em `src/App.tsx`. A jornada de medição apresenta a rodada, a
revisão do takeoff, a confirmação de código e o boletim; ela não calcula dinheiro, não
decide código e não chama provider.

## Regras

- React + TypeScript strict + Vite.
- O desenho é SVG nativo sobre a imagem, sem biblioteca de canvas: rendering/interação
  somente, e o scene domain permanece serializável.
- API data e canvas state são separados.
- Edições enviam operations allowlisted com `base_version`.
- Não alterar entidades exatas por drag; somente approximate control points.
- Cor nunca é o único indicador de precision/issue.
- Zoom/pan de imagem e overlay usam transform compartilhado e testado.
- Não esconder warning/critical para “limpar” a interface.
- Não persistir documento ou JWT em storage durável desnecessário.
- Nunca logar scene, OCR ou signed URLs no browser telemetry.
- Todo texto visível em português do Brasil; identificadores em inglês.
- Sem lib de router, estado global, canvas ou UI kit.

## Regras da jornada de medição (`src/medicao/`)

São regras de produto, não do app descartável de onde estas telas vieram: elas valem
enquanto a jornada existir, e o critério de aceite VAL-07 as cita.

- A tela **nunca** soma, multiplica ou arredonda dinheiro/quantidade: exibe as strings
  decimais que o servidor mandou (`format.ts` só troca pontuação, e é testado nisso).
- Mutações sempre citam `base_version` da rodada, mandam `Idempotency-Key` e nunca
  carregam `reviewer_id`, `reviewer_role`, `decided_at` ou `decision_id` — o servidor
  recusa e o client não tenta.
- Decisão é por item; nada nasce pré-marcado; "confirmar tudo" não existe.
- Cor nunca é o único indicador (estado por extenso + forma no SVG); erro é persistente
  (`role="alert"`), sucesso pode expirar; `409 REVISION_CONFLICT` preserva o formulário e
  oferece recarregar, e o overlay vencido do takeoff
  ([ADR-0030](../../docs/adr/0030-overlay-do-takeoff-reconstruido-na-fila.md)) é declarado
  em palavra, nunca só na borda.
- Chamada que grava artefato no servidor só por gesto explícito do usuário (ex.: o
  cálculo da shortlist fica atrás de botão que declara o que será gravado).
- Nenhum dado de obra em `localStorage`; nada de telemetry com conteúdo de catálogo ou
  medição.

## Testes mínimos

- Componentes e reducers/commands.
- Revision conflict.
- Estados loading/empty/error/expired.
- Acessibilidade de issues/properties.
- E2E fácil, médio e difícil.
- Performance do canvas conforme NFR.
- Medição: módulos puros com `*.test.ts` irmão (derivação de etapas, classificação do
  envelope de erro incl. `REVISION_CONFLICT` e o código de domínio em `details.code`,
  idade do overlay, formatação pt-BR com round-trip textual, heurística
  fornecimento×execução com frases reais do catálogo, viewport), transporte com `fetch`
  mockado provando caminho, `Idempotency-Key` e `base_version`, e `MedicaoApp.test.tsx`
  com SSR estático do estado sem sessão, sem dados fabricados.

## Smoke headless (local, nunca CI)

`npm --workspace @croquito/web run smoke:headless` (fonte em `e2e/smoke-headless.mjs`)
abre a tela num Chromium, faz o login real no Keycloak local e confere que a jornada
renderizou e que o `?job` do link sobreviveu ao redirect do OIDC. É o único teste que
alcança o redirect de verdade; o resto do comportamento é coberto por teste puro.

Pré-requisitos, na ordem:

```bash
make dev-services && make db-init && make dev
npx playwright install chromium   # uma vez; não roda no postinstall
cp .env.local.example .env.local  # dentro de apps/web, se ainda não existir
```

Variáveis (todas opcionais, com default do ambiente local): `CROQUITO_SMOKE_WEB_URL`,
`CROQUITO_SMOKE_JOB` (sem ele a checagem do `?job` não roda), `CROQUITO_SMOKE_USER`,
`CROQUITO_SMOKE_PASSWORD`, `CROQUITO_SMOKE_TIMEOUT_MS`.

Cena opcional da conversa da revisão, com `CROQUITO_SMOKE_CHAT=1` (exige
`CROQUITO_SMOKE_JOB`): abre o painel, envia a pergunta, espera a resposta e confere
que "Usar este rascunho" só pré-preenche. Ela **depende de um consumidor de fixtures
rodando**, porque a resposta é servida por fixture sintética e nenhum provider é chamado:

```bash
make dev-worker-fixtures   # noutro terminal, depois de a pergunta ser enviada
```

`make dev-worker-fixtures` serve **uma** mensagem por execução. O teto de espera é
`CROQUITO_SMOKE_CHAT_TIMEOUT_MS` (120 s por padrão). A fixture cita o par sintético
canônico do repositório: contra um job cujo pacote não o contém, o turno é recusado com
`CHAT_ACT_UNKNOWN_REFERENCE` — o portão funcionando — e a cena reprova por não haver
rascunho para conferir.

O smoke não imprime documento, cota, token nem URL assinada — só passo, estado e IDs
opacos. Pergunta e resposta da conversa também não são impressas.

## Conclusão

Mudança de comportamento atualiza FDD/acceptance; mudança de contrato atualiza API
e tipos gerados.

Na jornada de medição, mudança de comportamento atualiza a seção de medição do FDD e os
critérios VAL-*; mudança de contrato é feita primeiro nas rotas de `/v1`
(`services/api/src/croquito_api/main.py`, testes lá) e na seção "Medição de obra" do
[API Contract](../../docs/architecture/API_CONTRACT.md), e só depois refletida aqui.

