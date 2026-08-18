# ADR-0033: Conta por convite e login federado que vincula, não cria

Status: Accepted
Data: 2026-08-18  
Responsável: Engineering / Security / Product

## Contexto

O produto não tem ciclo de vida de conta: tem um console de administração e um procedimento
manual. Cada acesso novo é um ato humano — e hoje, na prática, alguém digitando uma senha por
outra pessoa. Cada senha esquecida é um chamado, sem caminho de auto-serviço. A pergunta de
produto que originou esta decisão é legítima e é essa: **como reduzir chamado de suporte?**

A resposta intuitiva — abrir autocadastro — foi investigada e **agrava** o problema que pretendia
resolver. O motivo é estrutural, não de configuração:

`tenant_id` é atributo do usuário, levado ao token pelo protocol mapper `tenant-id` do client
`croquito-web`. E `identity_from_claims`, em `packages/core/src/croquito_core/oidc.py`, recusa o
token quando o claim não é string:

```python
if (
    not isinstance(subject, str)
    or not isinstance(tenant_id, str)
    or not all(isinstance(role, str) for role in roles)
):
    raise OidcTokenError()  # -> 401 INVALID_TOKEN
```

Uma conta auto-cadastrada nasce **sem** `tenant_id`. Ela autentica no Keycloak com sucesso, entra
na tela e recebe `401` em toda chamada da API. O chamado não desaparece: "me criem um acesso"
vira "está tudo com erro", que parece defeito e consome depuração antes de alguém chegar à causa.

O repositório, aliás, já havia decidido isto em três lugares independentes, e todos anteriores a
esta conversa:

- `docs/product/NFR.md` declara **`NFR-SEC-001: "Autenticação por convite e isolamento por
  tenant."`** Autocadastro não contraria uma preferência de desenho; contraria um requisito
  não-funcional de segurança.
- `docs/product/` declara **`FR-001: "Usuário convidado cria projeto e envia PDF privado."`** O
  convite está no primeiro requisito funcional.
- O [ADR-0011](0011-oidc-portable-identity.md), `Accepted`, diz que "o produto precisa de
  **convite**, login, papéis e auditoria" e que "o vínculo profissional é atribuído pelo
  administrador do tenant neste MVP". O papel `tenant_admin` — "administra membros" — existe nos
  dois realms desde então e nunca foi exercido para isso.

O [ADR-0012](0012-contractual-ai-processing-entitlements.md) reforça pelo outro lado: a
autorização de processamento de IA é contratual e **por tenant**. Conta sem tenant é conta sem
contrato.

Há, por fim, uma peça de infraestrutura ausente que trava tudo ao mesmo tempo: **`smtpServer` não
existe em nenhum dos dois realms.** Sem envio de e-mail não há convite, não há verificação de
endereço e não há recuperação de senha. E ligar `resetPasswordAllowed` sem SMTP é pior do que
não ligar, porque a tela passa a prometer um e-mail que nunca sai.

## Decisão

**D1. Conta no Croquito nasce por convite, nunca por autocadastro.** Um `tenant_admin` cria a
conta **já com `tenant_id` e papel atribuídos** e dispara o e-mail de ações requeridas. Em nenhum
instante existe conta sem tenant. `registrationAllowed` permanece desligado nos dois realms.

**D2. Quem define a senha é a pessoa, não o administrador.** O convite carrega
`UPDATE_PASSWORD` e `VERIFY_EMAIL` como ações requeridas; o administrador nunca conhece a senha
de ninguém. É o que torna o convite auto-serviço de fato, e não um chamado com outro nome.

**D3. Recuperação de senha é auto-serviço e não revela quem tem acesso.**
`resetPasswordAllowed` é habilitado, e a resposta para endereço existente e inexistente é
indistinguível. `bruteForceProtected` precisa estar ativo nos dois realms antes de a tela existir
— hoje ele está declarado apenas no realm de homologação.

**D4. Login federado vincula conta existente; nunca cria conta.** O Google entra como identity
provider, e o fluxo de first broker login exige conta preexistente, casada por e-mail verificado.
Uma tentativa de login com conta não convidada é recusada **e não deixa usuário novo no realm**.
Sem isso, o Keycloak criaria o usuário sem `tenant_id` e a pessoa cairia no `401` do Contexto —
o mesmo defeito do autocadastro, por outra porta.

**D5. O produto oferece o caminho federado a partir da própria porta de entrada.** `signIn()`
aceita `kc_idp_hint`, que leva direto ao provedor sem passar pelo formulário de usuário e senha.

**D6. Nenhuma capacidade deste ADR entra no ar antes de um e-mail real ter chegado a uma caixa de
entrada real.** Em particular, `verifyEmail` só é habilitado depois disso: habilitá-lo com SMTP
não provado tranca todos para fora, inclusive quem consertaria.

**D7. Os segredos novos — credencial de SMTP e client secret do Google — entram por Terraform**,
no mecanismo do [ADR-0031](0031-segredo-de-homologacao-gerenciado-por-terraform.md), e nunca por
ato manual. Vale aqui a mesma constatação que originou aquele ADR: credencial que só um humano
sabe trocar é credencial que ninguém troca.

**D8. Este ADR não escolhe provedor de e-mail nem domínio remetente.** É decisão pendente, com
efeitos de custo, entregabilidade e propriedade de DNS que não são de arquitetura. Enquanto não
houver escolha, a [F-008](../features/F-008-ciclo-de-vida-de-conta/feature.md) permanece
`BLOCKED`.

## Alternativas

**Autocadastro aberto.** É o pedido original e a via mais direta para "não gerar chamado".
Rejeitada por três razões independentes, qualquer uma bastando: contraria `NFR-SEC-001` e o
`FR-001`; contraria o ADR-0011, que é `Accepted` e portanto imutável — exigiria ADR novo com
`Supersedes`; e, sobretudo, **não funciona**: produz conta que autentica e toma `401` em toda
chamada, trocando um chamado claro por um chamado que parece bug.

**Autocadastro com fila de aprovação.** A pessoa se cadastra, fica pendente, o administrador
aprova e atribui tenant. Preserva o isolamento e evita a conta órfã. Rejeitada por ora porque
desloca o mesmo trabalho do administrador para mais tarde, exige uma tela de aprovação que não
existe, e cria um estado intermediário — "usuário existe mas não pertence a ninguém" — que é
justamente o que D1 quer impedir. Fica registrada como caminho aberto se o volume de convites
tornar o custo do admin real.

**Domínio restrito no Google (`hostedDomain`).** Travaria o provedor a um Google Workspace, o que
é mais forte do que D4 e dispensaria a vinculação. Rejeitada porque a base esperada inclui
orçamentista de prefeitura e parceiro com e-mail de outros domínios; travar por domínio excluiria
usuário legítimo. Se algum dia o acesso for corporativo-only, `hostedDomain` é o parâmetro, e a
mudança é decisão de segurança própria — não ajuste de configuração.

**Provisionamento por diretório (SCIM) ou federação SAML.** Resolveria o ciclo de vida de conta
de forma industrial. Rejeitada por desproporção: exige diretório do lado do cliente, que o
público-alvo deste marco não tem.

**Manter tudo manual, pelo console do Keycloak.** É o estado atual e tem custo zero de
implementação. Rejeitada porque é a origem do problema: senha digitada por terceiro é senha
compartilhada, e senha esquecida sem auto-serviço é chamado garantido.

**Enviar e-mail pela aplicação, e não pelo Keycloak.** Daria controle total do template e do
remetente. Rejeitada porque duplicaria no domínio um fluxo que o provedor de identidade já
implementa com tokens de uso único e expiração — e o ADR-0011 existe justamente para manter esse
tipo de responsabilidade fora da regra de negócio.

## Consequências

### Positivas

- Uma pessoa nova entra sem que ninguém digite uma senha por ela, e uma senha esquecida se
  resolve em minutos: o objetivo de produto é atendido sem abrir a porta.
- Não existe, em nenhum caminho, conta sem tenant — o que fecha por construção a classe de
  chamado "está tudo com erro".
- O papel `tenant_admin`, declarado no ADR-0011 e ocioso desde então, passa a ter exercício real.
- O login com Google elimina a maior fonte remanescente de chamado de senha, sem virar caminho de
  criação de conta.
- A infraestrutura de e-mail, uma vez existindo, serve também a notificação futura — mas isso é
  trabalho próprio, não efeito deste ADR.

### Negativas

- Entrar no produto continua dependendo de um ato humano de um `tenant_admin`. O gargalo é
  reduzido, não eliminado.
- Duas superfícies públicas novas — recuperação de senha e federação — passam a existir, num
  ambiente que a [F-006](../features/F-006-hml-conserto/feature.md) acabou de recolocar de pé.
- A entregabilidade de e-mail (SPF, DKIM, reputação de remetente) passa a ser responsabilidade
  operacional, e ela mora em DNS, fora deste repositório.
- O produto passa a depender de um OAuth client no Google Cloud, com consent screen e dono
  próprios — acoplamento operacional a um terceiro, ainda que o ADR-0011 mantenha a portabilidade
  do protocolo.

## Riscos e mitigação

| Risco | Mitigação |
|---|---|
| `verifyEmail` habilitado antes de o SMTP estar provado tranca todos para fora, inclusive quem consertaria | D6: nenhuma capacidade entra no ar antes de um convite real chegar a uma caixa real; habilitar `verifyEmail` é gate humano explícito |
| A tela de recuperação permite enumerar quem tem acesso ao produto | D3: resposta indistinguível é critério de aceite verificado, não configuração assumida |
| O first broker login cria usuário sem `tenant_id` e reintroduz o `401` silenciosamente | Critério de aceite que tenta login com conta não convidada e **lista os usuários do realm antes e depois** para provar que nada foi criado |
| Convite cai em spam e o chamado volta pior — "não recebi o e-mail" | Domínio remetente com SPF e DKIM é pré-requisito declarado, não etapa opcional; o convite é verificado chegando a uma caixa real |
| Flag de realm não chega ao realm em pé: o `Dockerfile` registra que o importador usa `IGNORE_EXISTING`, então reimportar não sobrescreve realm existente | Nenhum critério de aceite pode ser "está no arquivo"; a verificação é o comportamento no ambiente |
| Segredo de SMTP ou do Google vaza em log, em plano publicado ou em commit | D7 e a política de log do repositório (`NFR-SEC-005`); segredo não transita fora do Secret Manager |

## Rastreabilidade

- Requirements: `NFR-SEC-001` (autenticação por convite e isolamento por tenant — esta decisão é
  a sua implementação direta), `FR-001` (usuário convidado), `NFR-SEC-005` (logs sem tokens).
- Decisões preservadas: [ADR-0011](0011-oidc-portable-identity.md) (convite, papéis e vínculo
  atribuído pelo `tenant_admin`), [ADR-0012](0012-contractual-ai-processing-entitlements.md)
  (entitlement por tenant), [ADR-0031](0031-segredo-de-homologacao-gerenciado-por-terraform.md)
  (segredo por Terraform), [ADR-0032](0032-porta-de-entrada-e-estado-sem-sessao.md) (o tema e a
  porta sobre os quais estas capacidades aparecem).
- Especificação e execução na feature
  [F-008](../features/F-008-ciclo-de-vida-de-conta/feature.md), hoje `BLOCKED` por D8. A entrada
  na [matriz de rastreabilidade](../engineering/TRACEABILITY.md) é criada junto da implementação,
  quando existir verificação a citar.
- Supersedes: none — o ADR-0011 é **confirmado**, não substituído.
- Superseded by: none
