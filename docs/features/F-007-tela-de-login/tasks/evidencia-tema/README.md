# Evidência visual do tema `croquito` — T4

Status: Evidência de execução
Responsável: Engineering
Última revisão: 2026-08-18

Capturas do critério 8 do [Feature Contract](../../feature.md) — "nenhuma página do tema cai
no padrão do Keycloak" — e do critério 7. Feitas contra o Keycloak local
`quay.io/keycloak/keycloak:26.2` (26.2.5) durante a execução da
[T4](../T4-tema-keycloak.md), com fixture sintética: o usuário `engenheiro.local` do realm
local versionado. Nenhuma credencial real, nenhum documento de cliente, nenhum token
legível — os links dos e-mails foram capturados com a rede bloqueada e o corpo do PNG não
resolve nada.

PNG a 1x (o viewport é de 1440 CSS px, exceto onde indicado).

## Páginas de login

| Arquivo | Página | Como foi alcançada |
| --- | --- | --- |
| [`01-login.png`](01-login.png) | `login.ftl` | Endpoint de autorização do realm local |
| [`01b-login-390px.png`](01b-login-390px.png) | `login.ftl` em 390px | Mesmo endereço, viewport de celular; sem rolagem horizontal (medido no script, não no olho) |
| [`02-login-erro.png`](02-login-erro.png) | `login.ftl` com erro | Senha errada de propósito |
| [`03-login-reset-password.png`](03-login-reset-password.png) | `login-reset-password.ftl` | "Forgot Password?", com `resetPasswordAllowed` ligado **só no container** |
| [`04-login-reset-password-enviado.png`](04-login-reset-password-enviado.png) | Confirmação do envio | Submissão do formulário acima |
| [`05-login-update-password.png`](05-login-update-password.png) | `login-update-password.ftl` | Ação obrigatória `UPDATE_PASSWORD` no usuário, via API de administração |
| [`06-login-verify-email.png`](06-login-verify-email.png) | `login-verify-email.ftl` | Ação obrigatória `VERIFY_EMAIL` + SMTP apontado para um sink local |
| [`07-login-page-expired.png`](07-login-page-expired.png) | `login-page-expired.ftl` | GET a `login-actions` com um `execution` que não é o corrente — o histórico do navegador voltando a uma etapa vencida (`SessionCodeChecks.java`, linhas 294-309). Confirmado por `data-page-id=login-login-page-expired`, não por semelhança visual |
| [`08-login-com-provedor-federado.png`](08-login-com-provedor-federado.png) | `login.ftl` + `social-providers.ftl` | Identity provider `google` criado **só no container**, para conferir o vestuário do botão que a [F-008](../../../F-008-ciclo-de-vida-de-conta/feature.md) vai ligar. Nos realms versionados ele continua ausente, e sem provider o botão não é renderizado (critério 9) |

## E-mails

Renderizados a partir do que o Keycloak **enviou de verdade** para um sink SMTP local —
não de um render estático do template.

| Arquivo | Template | Como foi disparado |
| --- | --- | --- |
| [`09-email-convite.png`](09-email-convite.png) | `executeActions.ftl` | `PUT /users/{id}/execute-actions-email` |
| [`10-email-verificacao.png`](10-email-verificacao.png) | `email-verification.ftl` | `PUT /users/{id}/send-verify-email` |
| [`11-email-reset-senha.png`](11-email-reset-senha.png) | `password-reset.ftl` | Formulário de recuperação |

O **texto** desses e-mails é o do Keycloak e não está aprovado: copy de e-mail é
[F-008](../../../F-008-ciclo-de-vida-de-conta/feature.md), com gate próprio
([mock](../../mock/README.md)). Aqui só o layout está sendo conferido.

## A imagem, não só o ambiente de desenvolvimento

| Arquivo | O que prova |
| --- | --- |
| [`12-imagem-optimized.png`](12-imagem-optimized.png) | A mesma tela servida pela imagem construída com `docker build -f keycloak/Dockerfile keycloak`, rodando `start --optimized` no subpath `/auth`, com o realm de **homologação** importado |

Essa última é a que fecha o passo 1 da T4: tema em diretório é servido pelo
`start --optimized` sem `kc.sh build`. As capturas de 01 a 11 vêm do `start-dev` local com
o tema montado por volume, que é onde dá para iterar.

## O que estas capturas **não** provam

- **O idioma.** As páginas aparecem em inglês porque `internationalizationEnabled` é falso
  nos dois realms, e o contrato da T4 proíbe mexer em campo de realm que não seja o tema.
  O mock aprovado mostra português. Está registrado como decisão pendente no
  [BUILD REPORT](../T4-build-report.md).
- **Homologação.** Tudo aqui é local. O deploy da imagem nova é gate humano pós-merge.
- **`resetPasswordAllowed`, SMTP e o identity provider.** Ligados apenas no container
  efêmero, para alcançar as páginas. Os realms versionados não os têm.
