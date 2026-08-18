# T4 — BUILD REPORT

Formato do [contrato do Builder](../../../engineering-os/agents/builder.md) da Engineering
OS. Task Contract: [T4](T4-tema-keycloak.md). Evidência visual:
[`evidencia-tema/`](evidencia-tema/README.md).

## Passo 1 — verificação do formato de tema na 26.2

Feita contra a documentação da versão **e** contra a imagem fixada, nunca por inferência de
versão anterior.

**Fontes.** Guia do desenvolvedor da 26.2
(`https://www.keycloak.org/docs/26.2.5/server_development/index.html`, capítulo Themes),
`/opt/keycloak/themes/README.md` de dentro de `quay.io/keycloak/keycloak:26.2`
(`version.txt` = **26.2.5**), e o conteúdo de
`/opt/keycloak/lib/lib/main/org.keycloak.keycloak-themes-26.2.5.jar`.

**Resultados.**

1. **Formato**: diretório `themes/<nome>/<tipo>/`, com `theme.properties` por tipo,
   `resources/` para estáticos e `messages/` para textos. Tipos existentes: `login`,
   `email`, `account`, `admin`, `welcome`. Chaves usadas: `parent`, `styles`, `darkMode`.
2. **Fase da imagem**: **runtime, e não a fase builder**. Duas razões independentes, as
   duas verificadas:
   - Tema em **diretório não exige `kc.sh build`**. O `themes/README.md` da imagem diz, com
     essas palavras: *"You are also able to create your custom themes in this directory,
     directly. Themes within this directory do not require the `build` command to be
     installed."* O guia da versão só exige o `build` para tema empacotado em **JAR** dentro
     de `providers/`.
   - Na fase de runtime do `keycloak/Dockerfile`, `COPY --from=builder /opt/keycloak/
     /opt/keycloak/` substitui a árvore inteira: qualquer `COPY` de tema anterior a essa
     linha seria apagado. O `COPY` do tema entra **depois** dela.
3. **Confirmação empírica**, e não só documental: a imagem construída aqui, rodando
   `start --optimized` no subpath `/auth` com o realm de homologação importado, serve
   `login/croquito/css/croquito.css` (200, 18.075 B), `img/croquito-mark.svg` (200) e
   `img/favicon.ico` (200), com `body { background-color: rgb(14,17,22) }` computado —
   captura em [`12-imagem-optimized.png`](evidencia-tema/12-imagem-optimized.png).
4. **Tema base**: `parent=keycloak.v2`, não `keycloak`. As notas de versão do Keycloak
   registram que a v2 virou o padrão de todo realm novo a partir da 26.0 e que a v1 *"is now
   deprecated, and will be removed in a future release"*. Herdar o tema deprecado compraria
   a quebra do próximo major de graça. Para o tipo `email` o parent é `keycloak`, porque
   `keycloak.v2` **não tem** o tipo `email` (`theme/keycloak.v2/` no JAR contém só `login`) —
   e parent é resolvido por tipo.

## Status

```text
BUILD REPORT

Status: BUILD_COMPLETE
```

## Files changed

| Arquivo | Por quê |
| --- | --- |
| `keycloak/themes/croquito/login/theme.properties` | **Novo.** `parent=keycloak.v2`, folha da marca depois da folha do pai, `darkMode=false` |
| `keycloak/themes/croquito/login/resources/css/croquito.css` | **Novo.** Todo o vestuário das páginas de login, 474 linhas, zero `.ftl` sobrescrito |
| `keycloak/themes/croquito/login/resources/img/croquito-mark.svg` | **Novo.** Cópia de `apps/web/public/favicon.svg` (a imagem do Keycloak não enxerga `apps/web`) |
| `keycloak/themes/croquito/login/resources/img/favicon.ico` | **Novo.** Ícone de aba nos tamanhos 16/32/48, gerado da geometria exata do SVG acima; sem ele a aba mostrava o ícone do Keycloak |
| `keycloak/themes/croquito/email/theme.properties` | **Novo.** `parent=keycloak` — ver passo 1, item 4 |
| `keycloak/themes/croquito/email/html/template.ftl` | **Novo.** Único `.ftl` sobrescrito no tema inteiro; é o layout por onde passam todos os e-mails HTML |
| `keycloak/Dockerfile` | `COPY themes/croquito` na fase de runtime, depois do `COPY --from=builder` |
| `keycloak/croquito-realm.json` | `loginTheme` e `emailTheme` apontando para `croquito` |
| `keycloak/croquito-hml-realm.json` | idem |
| `docker-compose.local.yml` | Montagem do diretório do tema no serviço `keycloak`, com o porquê no próprio compose |
| `docs/features/F-007-tela-de-login/tasks/evidencia-tema/` | **Novo.** 12 capturas + README explicando como cada página foi alcançada |
| `docs/features/F-007-tela-de-login/tasks/T4-build-report.md` | Este relatório |

**Nenhum arquivo fora de `keycloak/**`, `docker-compose.local.yml` e a pasta de evidência
foi tocado.** `e2e/smoke-headless.mjs`, `apps/web/` e `deploy/nginx.conf` estão intactos.

## Decisão de projeto que atravessa tudo: nenhum `.ftl` de login sobrescrito

O tema veste as páginas **só com CSS** sobre o DOM que o `template.ftl` da v2 já monta.
Três consequências que valem mais que a economia de linhas:

1. **O seletor do smoke é contrato e continua sendo o do Keycloak.** `#kc-form-login` e
   `input[name='username']` existem porque o markup não foi tocado — não porque tomei
   cuidado. Medido em todas as capturas: `#kc-form-login=1`, `input[name='username']=1`.
2. **As páginas que a F-008 vai habilitar já estão vestidas**, inclusive as que herdam de
   `base` e que a v2 nem sobrescreve (`login-verify-email.ftl`, `login-page-expired.ftl`):
   todas usam o mesmo shell.
3. **O risco de upgrade cai.** O contrato pede registrar quais arquivos do tema base foram
   tocados: **nenhum, no tipo `login`**. No tipo `email`, apenas `html/template.ftl`, cujo
   contrato é um `<#nested>` — a superfície mais estável que existe ali.

## Testes novos e o que cobrem

Nenhum teste automatizado novo. O contrato pede verificação **visual** (critérios 2 a 5) e
não define oráculo automatizável; a rede de regressão da feature é a T5
(`e2e/smoke-headless.mjs`), fora do escopo desta tarefa. O que substitui o teste aqui é
evidência com asserção verificável, não semelhança de imagem:

- `#kc-form-login` e `input[name='username']` contados em cada página capturada;
- ausência de rolagem horizontal em 390px medida por
  `document.documentElement.scrollWidth > clientWidth` → `false`;
- a página expirada confirmada por `data-page-id=login-login-page-expired`, e não "porque
  parece";
- os e-mails renderizados a partir do que o Keycloak **enviou** para um sink SMTP local.

## Validation executed

| Portão | Comando | Resultado |
| --- | --- | --- |
| Baseline `check` | `make check` no commit base (522aa4b) | **verde** (exit 0) |
| Baseline `test` | `make test` no commit base | **verde** (exit 0) |
| `full` | `make check` | **verde**: ruff check, ruff format (329 arquivos), mypy strict (185 fontes), `check_docs`, drift de contratos, build do web, `terraform fmt -check` |
| `test` | `make test` | **verde**, inalterado |
| `image` | `docker build -f keycloak/Dockerfile keycloak` | **verde**; conteúdo conferido com `find /opt/keycloak/themes -type f` dentro da imagem |
| `optimized` | imagem rodando `start --optimized` + `--import-realm` | **verde**: realm `croquito` importado, tema servido, três recursos em 200 |
| `local` | `make dev-services` + navegação nos cinco templates e nos três e-mails | **verde**, 12 capturas arquivadas |

Serviços derrubados ao final (`make down-services`); containers, imagem e banco de apoio
removidos; `output/` limpo. `git status` fecha com exatamente os arquivos da tabela acima.

## Validation skipped

`none`.

## Unavailable capabilities

`none`.

## Assumptions

1. **A cor do véu verde do fundo, `rgba(0, 200, 119, .16)`, é `--accent` com alfa** e não
   está na tabela do Design System. Não é valor novo decidido aqui: é o mesmo do
   [mock aprovado](../mock/login.html) por decisão humana de 2026-08-18 (regra `.kc`). A
   geometria do gradiente foi ampliada porque no mock o recorte tinha ~700px de altura e
   aqui a janela é a tela inteira; a **cor** é a mesma.
2. **Tamanho, espaçamento e raio são valores novos**, e o Design System registra por quê: o
   projeto não tem escala tipográfica, de espaçamento nem de raio. Os valores usados são os
   do mock aprovado, não uma escala inventada aqui.
3. **`#a3322a` / `#fdf3f2` no estado de erro do campo** saem do bloco `.alert` do mock
   aprovado. Regra 4 do Design System: cor de domínio não é marca.
4. **A palavra "Croquito" no cabeçalho dos e-mails** é o nome do produto, não copy nova. É
   o mínimo para o e-mail ter remetente reconhecível sem depender de imagem (cliente de
   e-mail bloqueia imagem remota por padrão). Nenhum outro texto foi acrescentado.

## Desvios conscientes do contrato

### 1. `emailTheme` nos dois realms — além do `loginTheme` que o contrato autoriza

**O contrato diz** (Scope): `"loginTheme": "croquito"` — e **nada mais** muda nos realms.
**Foi mudado também** `"emailTheme": "croquito"`.

**Por quê.** O Goal do próprio contrato exige que o tema vista "mais os templates de
e-mail", e o [ADR-0032](../../../adr/0032-porta-de-entrada-e-estado-sem-sessao.md), D7, diz
que o tema "veste todos os templates de login **e de e-mail**". No Keycloak isso é
impossível por `loginTheme`: o tipo `email` é resolvido por um campo separado,
`emailTheme`. **Medido, não deduzido**: com `loginTheme=croquito` e `emailTheme` nulo, o
e-mail de recuperação saiu com o layout de `base` — `<html lang="en" dir="ltr"><body>` sem
marca, sem tipografia e sem margem (capturas `01`–`03` do sink, descartadas). Só depois de
`emailTheme=croquito` os e-mails passaram a sair vestidos.

Sem esse campo, o tipo `email` do tema entraria na imagem e nunca seria usado — dívida
silenciosa exatamente do tipo que a F-006 registrou ter custado quatro dias.

**Natureza da mudança.** É o ponteiro do tema, mesma classe de `loginTheme`, e não uma
capacidade: nenhum SMTP, nenhum fluxo, nenhum `redirectUri`, nenhuma role, nenhum mapper.
Os campos que o Out of Scope nomeia continuam intocados.

### 2. Evidência do botão federado, que o contrato não pediu

Capturei também `login.ftl` com um identity provider ligado
([`08`](evidencia-tema/08-login-com-provedor-federado.png)). O contrato não pede, mas o
botão "Entrar com Google" está no mock aprovado e é a superfície que a F-008 liga; conferir
o vestuário dele agora é o que evita redesenhar uma tela já aprovada. O provider foi criado
**apenas no container efêmero** e removido depois — os realms versionados seguem sem
identity provider, que é o que o critério 9 do Feature Contract exige.

## Remaining risks

### 1. As páginas do Keycloak aparecem em INGLÊS; o mock aprovado está em português

`internationalizationEnabled` é falso nos dois realms, então o Keycloak resolve as
mensagens em `Locale.ENGLISH`: a tela diz "Sign in to your account", "Username or email",
"Forgot Password?". O [mock aprovado](../mock/README.md) mostra "Entrar", "Usuário ou
e-mail", "Esqueci minha senha".

**Não corrigi, de propósito**, e as duas saídas possíveis estão fora do que a T4 autoriza:

- ligar `internationalizationEnabled` + `defaultLocale: pt-BR` é campo de realm que o
  contrato proíbe;
- traduzir por `messages/messages_en.properties` dentro do tema é escrever **copy** —
  proibido pelo Out of Scope ("aqui só o vestuário das páginas") e sujeito ao gate de texto.

**Decisão humana necessária.** É a diferença entre o que foi aprovado e o que vai ao ar, e
não é bug do tema. A correção cabe naturalmente na
[F-008](../../F-008-ciclo-de-vida-de-conta/feature.md), que já mexe em conta e em copy.

### 2. Acoplamento à versão

Vale o risco que o ADR-0032 já registra. Ele foi **reduzido ao mínimo praticável** — zero
`.ftl` de login sobrescrito —, mas não some: a folha depende de nomes de classe e de
variáveis `--pf-v5-*` da PatternFly 5. Um major que troque a PatternFly quebra o vestuário
(nunca o formulário, que é markup do Keycloak). O upgrade passa a exigir reconferir estas
12 capturas.

### 3. Cor do link dentro do corpo do e-mail

O `<a>` do corpo vem das mensagens do Keycloak, sem classe nem `style`. A cor da marca
entra por `<style>` no `<head>`, que parte dos clientes de e-mail descarta — nesses, o link
sai no azul padrão do cliente. É legível e funcional, só não é da marca. Não há saída melhor
sem reescrever cada `.ftl` de e-mail, o que aumentaria a superfície de upgrade para ganhar
uma cor.

### 4. `--pf-v5-global--primary-color--100` recebeu `--accent-text`, e não `--accent`

A PatternFly usa esse token também em texto e traço, onde `--accent` daria 2,2:1 sobre
branco e violaria a regra 1 da folha. O preenchimento do CTA é tratado no bloco do botão. Se
uma tela futura da F-008 esperar o verde vivo em algum preenchimento que herde esse token,
ela virá mais escura — e será um ajuste local, não uma regressão de contraste.

## Human decisions required

1. **Idioma das páginas do Keycloak** (risco 1): manter em inglês, ou ligar i18n no realm —
   decisão de produto, e provavelmente escopo da F-008.
2. **Aceitar o desvio 1** (`emailTheme` nos dois realms), ou instruir a reverter e assumir
   que o tipo `email` do tema fica inerte até a F-008.
3. **Deploy da imagem nova em homologação** — gate declarado no Feature Contract, ato humano
   pós-merge. `COMMIT` continua `forbidden` nesta tarefa: nada foi commitado.

## Oportunidades vistas e NÃO implementadas

- **`accountTheme` e `adminTheme` seguem no padrão do Keycloak.** O console de conta e o de
  administração não estão no escopo da F-007 e ninguém que não seja operador os vê.
- **Sem `messages/` no tema.** É onde entraria a tradução e a copy — F-008, com gate de
  texto próprio.
- **O grupo do campo de senha** (input + botão de olho) mostra o anel de foco só na parte do
  input, porque a v2 os separa em dois itens de `input-group`. Corrigir exigiria sobrescrever
  `field.ftl`, trocando superfície de upgrade por um detalhe de foco que já está visível.
- **O ícone dos alertas de sucesso/aviso não é renderizado**: `kcFeedbackSuccessIcon` e
  companhia não estão definidos no `theme.properties` da `keycloak.v2`. É lacuna do tema
  embutido, não do nosso. Preencher essas chaves seria uma melhoria de uma linha cada, mas
  acrescenta acoplamento a nomes de ícone da PatternFly sem que nenhum critério peça — e a
  regra 5 já está satisfeita, porque todo estado está escrito por extenso.
- **`docs/operations/HML_KEYCLOAK.md` não menciona o tema.** Reconciliação documental é T6.
