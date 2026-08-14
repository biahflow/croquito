# Runbook: Keycloak da homologação

Status: Accepted  
Responsável: Platform / Engineering  
Última revisão: 2026-08-14

Como administrar identidade no ambiente hospedado ([HML](HML.md)). A decisão de hospedar
o Keycloak em subpath está no
[ADR-0025](../adr/0025-homologacao-em-gcp-cloud-run.md); a identidade portável, no
[ADR-0011](../adr/0011-oidc-portable-identity.md).

## Regra que não se negocia

**Usuário nunca nasce por import de realm.** O arquivo
[`keycloak/croquito-hml-realm.json`](../../keycloak/croquito-hml-realm.json) não tem bloco
`users` de propósito: usuário versionado significa senha versionada, e senha versionada num
ambiente alcançável pela internet é credencial pública com passos extras. O realm importado
traz realm, papéis, client e mapeadores; pessoa é ato humano, feito aqui.

## Acesso ao console

O console de administração fica em `https://croquito-hml.biahflow.ai/auth/` (o path `/auth`
é fixado na imagem, não é opção de runtime).

Usuário: `admin`. A senha é o segredo `croquito-hml-kc-bootstrap-admin-password`:

```bash
gcloud secrets versions access latest \
  --secret croquito-hml-kc-bootstrap-admin-password --project biahflow-hml
```

Esse comando imprime o segredo no terminal. Não cole a saída em issue, chat, log ou
qualquer canal compartilhado; prefira ler pelo console do Secret Manager quando alguém
estiver olhando a tela.

Duas notas sobre esse admin:

- Ele é criado **apenas na primeira subida com o banco vazio**. Trocar o valor do segredo
  depois disso não muda a senha do admin existente — a troca é feita no próprio console.
- Ele é conta de operação da plataforma, não conta de pessoa. Quem usa o produto entra pelo
  realm `croquito`, nunca pelo `master`.

## Criar um usuário real

No console, com o realm `croquito` selecionado (canto superior esquerdo):

1. **Users → Add user**
   - `Username`: nome curto e estável (ex.: `nome.sobrenome`).
   - `Email`: e-mail real da pessoa; marque `Email verified` se você mesmo confirmou.
   - `Tenant`: o `tenant_id` da organização (ex.: `tenant-scalle`). **Campo obrigatório** —
     o realm declara `tenant_id` no perfil de usuário e o console recusa salvar sem ele
     (`error-user-attribute-required`). Isso é deliberado: `tenant_id` é o que isola dado de
     cliente, e a API só o aceita vindo do token.
   - Use o **mesmo valor** de `tenant_id` para todas as pessoas da mesma organização; um
     caractere diferente cria um segundo tenant vazio.
2. **Role mapping → Assign role → Filter by realm roles**, e atribua o que a pessoa faz:
   - `engineer` — decide leituras, aceita traçado, aprova cena e exporta DXF. É o papel que
     a sessão de cena exige.
   - `orcamentista` — revisa takeoff e confirma código na medição
     ([ADR-0026](../adr/0026-medicao-hospedada-sessao-autenticada-minima.md)).
   - `platform_operator` — administra autorização contratual de IA por tenant. Só para quem
     opera a plataforma; não é papel de cliente.
   - `cad_operator` e `tenant_admin` existem no realm e hoje **não são exigidos por nenhuma
     rota**; atribua apenas se souber por quê.
3. **Credentials → Set password**
   - `Temporary`: **On**. A pessoa troca a senha no primeiro login e nenhuma senha
     escolhida por terceiro sobrevive à primeira sessão.
   - Combine a senha inicial por canal direto com a pessoa; não a registre em documento
     compartilhado.

## Conferir se ficou certo

- **Users → (usuário) → Attributes**: `tenant_id` com o valor esperado.
- **Users → (usuário) → Role mapping**: os papéis atribuídos aparecem como realm roles.
- Login pelo produto: entrar em `https://croquito-hml.biahflow.ai/revisao/` e ver a lista
  de projetos do tenant. Lista vazia com login bem-sucedido normalmente significa
  `tenant_id` diferente do que criou os projetos — não é falta de papel.

## Mudança no realm depois que ele já existe

A imagem sobe com `--import-realm`, e a estratégia do importador é **`IGNORE_EXISTING`**:
realm que já está no banco **não é sobrescrito**. Isso é o que protege os usuários criados à
mão de sumirem a cada deploy — e é também o que faz uma alteração no
`croquito-hml-realm.json` **não** chegar sozinha a um realm que já existe.

Para aplicar uma mudança de realm no ambiente já criado, escolha um destes e registre o que
fez:

- Repetir a mudança no console (caminho normal para papel novo, mapeador ou URI de
  redirecionamento).
- **Realm settings → Action → Partial import**, com o trecho que mudou.
- Recriar o realm (apagar e deixar o import refazer) — **destrutivo**: apaga todos os
  usuários, e por isso exige combinação prévia com quem usa o ambiente.

O arquivo do repositório continua sendo a descrição de como o realm nasce; ele não é
aplicado continuamente.

## Se o login parar de funcionar

1. `gcloud run services logs read croquito-auth-hml --region us-east1 --limit 100` — subida,
   conexão com o banco e erro de hostname aparecem aqui.
2. `curl -sf https://croquito-hml.biahflow.ai/auth/realms/croquito/.well-known/openid-configuration`
   — o campo `issuer` precisa ser exatamente
   `https://croquito-hml.biahflow.ai/auth/realms/croquito`. Issuer diferente do configurado
   na API e na medição derruba todo token, e a causa quase sempre é cabeçalho de proxy
   (`KC_PROXY_HEADERS`/`KC_HOSTNAME`), não credencial.
3. Primeira requisição do dia lenta ou com erro de conexão: o Keycloak subiu do zero e/ou o
   banco estava suspenso. Repetir uma vez é diagnóstico legítimo; repetir em laço não é.
4. Nada resolvido: rollback do serviço de auth para a revisão anterior, pelo procedimento em
   [HML](HML.md).
