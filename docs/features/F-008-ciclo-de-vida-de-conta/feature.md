# F-008 — Ciclo de vida de conta: convite, recuperação de senha e Google

## Status

`BLOCKED`

> Selecionada por decisão humana de 2026-08-18, a partir de uma observação de produto: cada
> acesso novo e cada senha esquecida viram chamado de suporte. O objetivo é esse — o desenho
> abaixo é o que a evidência do repositório permite.
>
> Bloqueada por **uma decisão** e **duas features**: falta escolher o provedor de e-mail e o
> domínio remetente (sem isso nenhum dos três fluxos existe, e um Planner só poderia inventar);
> a [F-007](../F-007-tela-de-login/feature.md) entrega o tema sobre o qual estas páginas
> aparecem; e a [F-006](../F-006-hml-conserto/feature.md) devolve o ambiente onde tudo se
> verifica. Decidido o provedor e entregue a F-007, o estado passa a `READY_FOR_PLANNING`.

## Priority

`HIGH` — definida por ato humano em 2026-08-18.

## Problem

O produto não tem ciclo de vida de conta. Ele tem um console de administração e um
procedimento manual.

- **Conta nasce à mão.** `keycloak/croquito-hml-realm.json` importa o realm com `users: []`, e
  o `keycloak/Dockerfile` registra a razão: "nenhuma senha de fixture entra num ambiente
  hospedado. Usuário real nasce pelo console de administração, com o procedimento em
  `docs/operations/HML_KEYCLOAK.md`". Cada pessoa nova é um ato humano — e, hoje, alguém
  digitando uma senha por outra pessoa.
- **Senha esquecida não tem saída.** `resetPasswordAllowed` está ausente nos dois realms.
- **Nada disso pode existir enquanto não sair e-mail: `smtpServer` está ausente nos dois
  realms.** É a peça única que trava convite, verificação de e-mail e recuperação de senha ao
  mesmo tempo. Ligar `resetPasswordAllowed` sem SMTP é pior do que não ligar: a tela promete um
  e-mail que nunca sai.

**Autocadastro aberto não resolve isso — piora.** `tenant_id` é um atributo do usuário, levado
ao token pelo protocol mapper `tenant-id` do client `croquito-web`. E
`packages/core/src/croquito_core/oidc.py`, em `identity_from_claims`, recusa o token quando o
claim não é string:

```python
if (
    not isinstance(subject, str)
    or not isinstance(tenant_id, str)
    or not all(isinstance(role, str) for role in roles)
):
    raise OidcTokenError()  # -> 401 INVALID_TOKEN
```

Uma conta auto-cadastrada nasce sem `tenant_id`. Ela autentica no Keycloak, entra na tela e
recebe **401 em toda chamada da API**. O chamado não desaparece: ele troca "me criem um acesso"
por "está tudo com erro", que consome depuração antes de alguém descobrir a causa.

O [ADR-0011](../../adr/0011-oidc-portable-identity.md), `Accepted`, já tinha decidido o
caminho certo: "O produto precisa de **convite**, login, papéis e auditoria" e "O vínculo
profissional é atribuído pelo administrador do tenant neste MVP". O papel `tenant_admin` —
"administra membros" — existe nos dois realms desde então e nunca foi usado para isso.

## Desired Outcome

Uma pessoa nova entra sem que ninguém digite uma senha por ela, e uma senha esquecida se
resolve sozinha em minutos — sem que exista, em nenhum momento, caminho para uma conta nascer
sem tenant.

## Scope

- **Infraestrutura de e-mail**: provedor SMTP, domínio remetente, registros de entregabilidade
  (SPF/DKIM), credencial em Secret Manager **pelo Terraform** conforme
  [ADR-0031](../../adr/0031-segredo-de-homologacao-gerenciado-por-terraform.md), e o bloco
  `smtpServer` nos realms.
- **Flags de realm**: `resetPasswordAllowed`, `loginWithEmailAllowed` e `verifyEmail` nos dois
  realms, e `bruteForceProtected` no realm local — hoje ele existe só em homologação.
- **Convite**: o fluxo pelo qual um `tenant_admin` cria a conta já com `tenant_id` e papel e
  dispara o e-mail de ações requeridas (`UPDATE_PASSWORD` + `VERIFY_EMAIL`), mais o runbook em
  `docs/operations/`. A conta nunca existe sem tenant, em nenhum instante.
- **Google como identity provider**: OAuth client no Google Cloud, client secret por Terraform,
  e o fluxo de first broker login configurado para **exigir conta existente** — vinculação por
  e-mail, sem criação automática.
- **`apps/web`**: `signIn()` aceita `kc_idp_hint=google`, que é o que faz o botão do `/login`
  pular direto para o Google em vez de passar pelo formulário.
- **Templates de e-mail no tema `croquito`** (convite, recuperação, verificação), sobre a base
  que a F-007 entrega.
- **[ADR-0033](../../adr/0033-conta-por-convite-e-login-federado.md)**, redigido e **aceito por
  ato humano** em 2026-08-18: conta por convite e não por autocadastro; Google como método de
  login de conta existente; e onde vivem os segredos novos.

## Out of Scope

- **Autocadastro aberto.** Contradiz o ADR-0011, que é `Accepted` e portanto imutável; mudar
  exigiria ADR novo com `Supersedes`. E produziria a conta órfã descrita no Problem.
- **Autocadastro com fila de aprovação.** Avaliado e recusado por ora: precisa de uma tela de
  aprovação que não existe e desloca para o admin o mesmo trabalho do convite, mais tarde.
- **MFA, federação SAML e provisionamento por diretório (SCIM).** Nenhum foi pedido.
- **Tela de administração de membros dentro do Croquito.** No MVP o console do Keycloak
  resolve; uma UI própria é feature de produto e tem contrato próprio.
- **Troca de tenant pelo próprio usuário.** O vínculo é ato do `tenant_admin` (ADR-0011).
- **Alertas e observabilidade de entrega de e-mail.** Trabalho próprio, como a observabilidade
  de homologação registrada em F-006.

## Acceptance Criteria

1. Um convite disparado por um `tenant_admin` chega na caixa de entrada, e o link abre a
   página de definir senha **no tema `croquito`**, não no padrão do Keycloak.
2. A conta criada por convite entra e completa **pelo menos uma chamada `/v1` autenticada com
   sucesso**. É a prova direta de que `tenant_id` está no token — o critério que separa esta
   feature do autocadastro.
3. "Esqueci minha senha" envia o e-mail para conta existente e, para e-mail inexistente,
   devolve **resposta indistinguível** — sem enumeração de usuário.
4. Login com Google de conta já convidada entra e mantém `tenant_id` e papéis no token.
5. Login com Google de conta **não** convidada é recusado **e não cria usuário no realm**.
   Verificado listando os usuários do realm antes e depois da tentativa.
6. Nenhuma das páginas ou e-mails novos aparece sem o tema.
7. Nenhum segredo — SMTP ou client secret do Google — aparece em log, em plano publicado no
   resumo do job, ou em mensagem de commit.
8. `make check` e `make test` verdes.

## Constraints

- **Segredo entra por Terraform**, nunca por `gcloud secrets versions add` — decisão humana de
  2026-08-18 registrada na F-006 e no ADR-0031.
- **Reimportar o realm não muda realm que já existe.** O `keycloak/Dockerfile` registra que a
  estratégia do importador de diretório é `IGNORE_EXISTING`, "então subir uma revisão nova não
  sobrescreve usuário criado à mão". A mesma propriedade significa que **mudar uma flag no
  JSON não a aplica ao realm em pé**: a mudança precisa de um ato explícito, e o critério que a
  verifica não pode ser "está no arquivo".
- **A entregabilidade depende de DNS fora deste repositório.** SPF e DKIM vivem na zona do
  domínio; sem eles o convite chega em spam e o chamado volta pior do que era.
- **`bruteForceProtected` precisa estar ligado nos dois realms antes** de existir tela pública
  de recuperação de senha.
- **E-mail é dado pessoal.** Convite e recuperação carregam nome e endereço; a política de log
  do repositório vale para eles.
- O `redirect_uri` e os `redirectUris` dos realms não mudam por causa desta feature.

## Dependencies

- **Decisão humana**: provedor de e-mail e domínio remetente. É o que mantém esta feature
  `BLOCKED`.
- [F-007](../F-007-tela-de-login/feature.md): o tema `croquito` e o espaço do botão no card.
- [F-006](../F-006-hml-conserto/feature.md): sem ambiente no ar não há como verificar.
- [ADR-0011](../../adr/0011-oidc-portable-identity.md) — convite, papéis e vínculo por
  `tenant_admin`.
- [ADR-0012](../../adr/0012-contractual-ai-processing-entitlements.md) — a autorização de
  processamento é por tenant, o que é outra razão para conta não existir sem tenant.
- [ADR-0031](../../adr/0031-segredo-de-homologacao-gerenciado-por-terraform.md) — o mecanismo
  pelo qual os segredos novos entram.
- [ADR-0033](../../adr/0033-conta-por-convite-e-login-federado.md) — `Accepted` por ato humano
  em 2026-08-18. O D8 dele é o que mantém esta feature `BLOCKED`.

## Unknowns

Não decididos. Nenhum deve ser respondido por suposição.

- **Qual provedor de e-mail e qual domínio remetente.** Decide custo, entregabilidade, quem
  administra o DNS e onde mora o segredo.
- **Se o Google é o Workspace de vocês** e se haverá orçamentista de fora dele. A decisão
  humana de 2026-08-18 foi "qualquer conta Google, mas só vinculando conta existente"; se
  amanhã o acesso for restrito a um domínio, `hostedDomain` é o parâmetro, e isso é decisão de
  segurança, não ajuste.
- **Quem é dono do projeto no Google Cloud** e do consent screen do OAuth client.
- **Se o convite exibe o nome do tenant** para quem o recebe — o mock supõe que sim, e isso
  depende de o convite carregar essa informação.
- **Como uma flag de realm chega ao realm em pé**, dado o `IGNORE_EXISTING`: import parcial,
  Admin API, ou Terraform provider do Keycloak. Não decidido.
- **Se `verifyEmail` liga junto com o resto ou numa rodada depois** — ver o primeiro risco.
- **O texto dos e-mails.** Nenhuma linha foi aprovada.

## Risks

- **Ligar `verifyEmail` antes de o SMTP estar provado tranca todo mundo do lado de fora** —
  inclusive quem consertaria. É o análogo, nesta feature, do loop de login da F-007: falha
  total, causada por uma flag. Mitigação: `verifyEmail` só depois de um convite real ter
  chegado numa caixa de entrada real.
- **Enumeração de usuário** na tela de recuperação: resposta diferente para e-mail existente e
  inexistente entrega a lista de quem tem acesso ao produto. Vira o critério 3.
- **Convite em spam.** O chamado que se queria eliminar volta como "não recebi o e-mail", que é
  mais difícil de diagnosticar do que "me criem um acesso".
- **Google criando conta sozinho.** Se o first broker login não for configurado para exigir
  conta existente, o Keycloak cria o usuário — sem `tenant_id` — e a pessoa cai no 401 do
  Problem. É o critério 5 justamente porque é silencioso.
- **`IGNORE_EXISTING` mascarando que a flag não entrou.** O deploy passa, o arquivo está
  correto, e o comportamento no ar continua o antigo.
- **Duas superfícies públicas novas** (recuperação e federação) num ambiente que a F-006 acabou
  de tirar do chão.

## Human Gates

- Escolha do provedor de e-mail e do domínio remetente — é o que desbloqueia a feature.
- ~~Aceitação do ADR-0033~~ — **aceito por ato humano em 2026-08-18**.
- Criação do OAuth client no Google Cloud e do consent screen, atos fora deste repositório.
- `terraform apply` dos segredos novos, com plano revisado.
- Autorização explícita para ligar `verifyEmail`.
- Aprovação do texto dos e-mails de convite, recuperação e verificação.

## References

- [ROADMAP](../../product/ROADMAP.md)
- [F-006](../F-006-hml-conserto/feature.md),
  [F-007](../F-007-tela-de-login/feature.md)
- [ADR-0033](../../adr/0033-conta-por-convite-e-login-federado.md) — a decisão desta feature
- [ADR-0011](../../adr/0011-oidc-portable-identity.md),
  [ADR-0012](../../adr/0012-contractual-ai-processing-entitlements.md),
  [ADR-0031](../../adr/0031-segredo-de-homologacao-gerenciado-por-terraform.md),
  [ADR-0032](../../adr/0032-porta-de-entrada-e-estado-sem-sessao.md)
- [HML_KEYCLOAK](../../operations/HML_KEYCLOAK.md)
- Fontes lidas para este contrato: `keycloak/croquito-realm.json`,
  `keycloak/croquito-hml-realm.json`, `keycloak/Dockerfile`,
  `packages/core/src/croquito_core/oidc.py`, `services/api/src/croquito_api/auth.py`,
  `apps/web/src/auth.ts`.
