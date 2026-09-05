# Onde a senha de app do Workspace vai (e onde ela nunca pode ir)

Status: instruções de operador
Criado em: 2026-09-05, junto da [Emenda 1 do ADR-0033](../adr/0033-conta-por-convite-e-login-federado.md)

A decisão de e-mail está tomada: transacional pelo Google Workspace, remetente no domínio
principal. Falta **onde colocar a senha de app** — e a resposta é diferente para cada
ambiente, porque o que vale é a D7 do ADR-0033: *segredo entra por Terraform, nunca por ato
manual no console*.

> **Antes de tudo, o que NÃO fazer**, e vale para os dois ambientes:
>
> - **Não cole a senha num chat**, nem aqui nem em qualquer transcrição — inclusive comigo.
>   Senha que passa por um log é senha a trocar.
> - **Não digite a senha no console do Keycloak** (Realm settings → Email). Funciona, e é
>   exatamente o que a D7 proíbe: credencial que só um humano sabe onde está é credencial
>   que ninguém troca.
> - **Não commite em lugar nenhum do repositório.** O `.gitignore` já protege `.env*`, mas
>   o hábito é o que protege de verdade.

## Antes: criar a senha de app

No Google, com a conta do domínio: **Segurança → Verificação em duas etapas** (precisa estar
ligada) → **Senhas de app** → gerar uma para "croquito / Keycloak". O Google mostra 16
caracteres **uma única vez**.

Guarde-a onde você já guarda segredo (gerenciador de senhas). Ela não é a senha da conta e
pode ser revogada isoladamente — se um dia vazar, revogar não derruba o seu e-mail.

## Ambiente local (hoje, para ver funcionando)

Duas linhas no `.env.local` da raiz — o arquivo já é ignorado pelo Git (`.gitignore:3`):

```bash
CROQUITO_SMTP_USER=nao-responda@<seu-domínio>
CROQUITO_SMTP_PASSWORD=<a senha de app, sem espaços>
```

O Google mostra a senha em quatro blocos de quatro; **cole sem os espaços**.

O restante da configuração SMTP não é segredo e vai versionado no realm quando a F-008 for
implementada (host `smtp.gmail.com`, porta 587, STARTTLS, autenticação ligada, remetente e
nome de exibição). Hoje ela ainda não existe em `keycloak/croquito-realm.json` — o
`smtpServer` está ausente nos dois realms, e é justamente o que a feature entrega.

## Homologação e produção (quando o ambiente voltar)

Pelo mecanismo do [ADR-0031](../adr/0031-segredo-de-homologacao-gerenciado-por-terraform.md),
no repositório de infraestrutura (`biahflow/infra`), **não neste repositório**:

1. o segredo nasce no Secret Manager como recurso Terraform, com valor `write-only` (o
   valor não volta no state nem no plano);
2. o serviço do Keycloak recebe a referência do segredo como variável de ambiente;
3. o `smtpServer` do realm passa a citar a variável, e nunca o valor.

O valor em si você informa uma vez, pelo caminho que aquele repositório já usa para as
credenciais de homologação — o mesmo que consertou o incidente do banco em 2026-08-18.

## Como saber que funcionou

Depois da F-008 implementada: no Keycloak, **Realm settings → Email → Test connection**
envia um e-mail de teste para a conta do administrador. Antes disso, não há o que testar —
a configuração ainda não existe.

Se o teste falhar, os dois motivos prováveis, nesta ordem: a verificação em duas etapas não
está ligada na conta (sem ela o Google não gera senha de app válida), ou o remetente não é
um usuário/alias do Workspace — o Google recusa enviar como quem não é dele, que é
exatamente a razão de a Emenda 1 ter escolhido o domínio principal.
