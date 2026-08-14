# Instruções para agentes — web

Estas regras estendem o [AGENTS.md](../../AGENTS.md). Leia também
[FDD](../../docs/product/FDD.md),
[API Contract](../../docs/architecture/API_CONTRACT.md) e
[Human in the Loop](../../docs/ai/HUMAN_IN_THE_LOOP.md).

## Boundary

O web app apresenta projetos, status, revisão e exportação. Ele não resolve
geometria, escolhe consenso ou autoriza tenant por conta própria.

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

## Testes mínimos

- Componentes e reducers/commands.
- Revision conflict.
- Estados loading/empty/error/expired.
- Acessibilidade de issues/properties.
- E2E fácil, médio e difícil.
- Performance do canvas conforme NFR.

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

