# T4 — O tema croquito do Keycloak

Task Contract no formato do [template global](../../../engineering-os/templates/task.md),
derivado do [plano válido](../plan.md). Autossuficiente. O primeiro passo é **verificação,
não inferência**: o formato de tema da versão fixada (Keycloak 26.2) é um unknown declarado
do contrato e se resolve lendo a documentação da versão e testando contra a imagem fixada.

## Identity

```text
feature_id: F-007
task_id: T4
parent_plan: docs/features/F-007-tela-de-login/plan.md
depends_on: none
```

## Goal

O tema `croquito` — logo e paleta da folha da marca — veste a página de login e **todas as
páginas que a F-008 vai alcançar**, mais os templates de e-mail; os dois realms apontam
`loginTheme` para ele; e o formulário continua sendo encontrado pelo seletor do smoke
(`#kc-form-login, input[name='username']`). ADR-0032, D7 e D8; critérios 7 e 8 do
[Feature Contract](../feature.md).

## Scope

- **Passo 1 (verificação)**: formato de tema no Keycloak 26.2 e a fase da imagem em que ele
  entra (antes do `kc.sh build` da fase builder ou na fase de runtime) — verificado na
  documentação da versão e num container da imagem fixada
  (`quay.io/keycloak/keycloak:26.2`). O resultado guia o resto e vai no relatório.
- Diretório de tema novo **dentro de `keycloak/`** (o build do workflow usa
  `docker build -f keycloak/Dockerfile keycloak` — contexto restrito à pasta; tema fora
  dela não entra na imagem).
- Templates a vestir: `login.ftl`, `login-reset-password.ftl`, `login-update-password.ftl`,
  `login-verify-email.ftl`, `login-page-expired.ftl` e os templates de e-mail do tema.
  Estender o tema base da versão, sobrescrevendo o mínimo — quanto menor a superfície,
  menor a quebra no upgrade.
- Marca: tokens da tabela do [Design System](../../../engineering/DESIGN_SYSTEM.md)
  (`--bg`, `--surface`, `--ink`, `--accent` só preenchimento, `--accent-text` para texto
  verde) e logos de `apps/web/src/assets/` copiados para o tema (a imagem do Keycloak não
  enxerga `apps/web`). Referência visual: `../mock/03-keycloak-tema-croquito.png`
  (aprovado na revisão 2).
- `keycloak/Dockerfile`: `COPY` do tema na fase correta (a verificada no passo 1).
- `keycloak/croquito-realm.json` e `keycloak/croquito-hml-realm.json`: `"loginTheme":
  "croquito"` — e **nada mais** muda nos realms.
- `docker-compose.local.yml`: se necessário para testar localmente, montar o diretório do
  tema como volume no serviço `keycloak` (que usa a imagem estoque com `start-dev`), sem
  trocar imagem nem flags além do necessário; comentar o porquê no próprio compose.

## Out of Scope

- Qualquer capacidade de conta (SMTP, identity provider, fluxos de reset reais) — é F-008;
  aqui só o **vestuário** das páginas.
- `redirectUris`, roles, mappers ou qualquer outro campo dos realms.
- Segredo ou credencial em arquivo de tema — camada de imagem é legível por quem puxa.
- Deploy em homologação (gate humano pós-merge).
- O seletor do smoke (`e2e/smoke-headless.mjs`) — o tema se adapta ao smoke, nunca o
  contrário: os campos mantêm os nomes/IDs padrão do Keycloak.

## Acceptance Criteria

1. Relatório do passo 1: formato do tema em 26.2 e fase da imagem, com a fonte citada
   (checado por leitura do relatório).
2. Keycloak local servindo o tema: a página de login mostra logo e paleta da marca, e
   `#kc-form-login` e `input[name='username']` continuam presentes (checado por navegação e
   inspeção; critério 7).
3. **Cada um dos seis templates** do escopo aberto e conferido visualmente no Keycloak
   local, com captura arquivada em
   `docs/features/F-007-tela-de-login/tasks/evidencia-tema/` (PNGs sintéticos, versionáveis;
   critério 8 — nenhuma página cai no padrão do Keycloak). Para alcançar páginas que o
   fluxo normal não abre (reset, verify-email), use os caminhos administrativos ou de
   simulação que a versão oferecer; documente como cada uma foi alcançada.
4. E-mails do tema conferidos ao menos por render estático dos templates (a F-008 é quem os
   dispara de verdade); capturas idem.
5. `docker build -f keycloak/Dockerfile keycloak` constrói com o tema dentro (checado
   listando o conteúdo da imagem).
6. `make check` verde; `make test` inalterado e verde.

## Validation

```text
baseline: make check e make test → verdes no commit base; make dev-services sobe o
          Keycloak local em quay.io/keycloak/keycloak:26.2
required: full:  make check
          local: make dev-services + navegação nos templates + capturas
          image: docker build -f keycloak/Dockerfile keycloak
```

## Required Capabilities

```text
READ:     o repositório; documentação oficial do Keycloak 26.2 (rede)
WRITE:    keycloak/** e docker-compose.local.yml, somente
VALIDATE: make check; docker build; stack local
COMMIT:   forbidden
```

## Context to Read First

1. `AGENTS.md` (raiz) e `CLAUDE.md`.
2. `keycloak/Dockerfile` por inteiro — o comentário das linhas 32–36 explica o rename do
   realm; a política "nenhum segredo em camada de imagem" vale para o tema.
3. `docker-compose.local.yml`, serviço `keycloak` (linhas 33–48) e o comentário sobre
   montagem de realm.
4. [ADR-0032](../../../adr/0032-porta-de-entrada-e-estado-sem-sessao.md) D7/D8 e
   `../mock/README.md` (decisões de desenho; "Esqueci minha senha" fica na página do
   Keycloak).
5. [Design System](../../../engineering/DESIGN_SYSTEM.md) — tabela de tokens e regras.

## Known Risks

- Tema acoplado à versão: upgrade de major quebra na tela que todo mundo vê — sobrescrever
  o mínimo e registrar no relatório quais arquivos do tema base foram tocados.
- Copiar valor de cor fora da tabela de tokens — qualquer valor novo é "novo" e não está
  aprovado.
- Quebrar o seletor do smoke com markup custom — os nomes padrão dos campos são contrato.

## Human Gates

- Deploy da imagem nova em homologação: pós-merge, ato humano (gate do Feature Contract).

## Reporting

Encerre com o `BUILD REPORT` completo do
[contrato do Builder](../../../engineering-os/agents/builder.md) e grave o mesmo conteúdo em
`docs/features/F-007-tela-de-login/tasks/T4-build-report.md`.
