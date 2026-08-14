# ADR-0026: Medição hospedada com sessão autenticada mínima

Status: Accepted  
Data: 2026-08-14  
Responsável: Product / Engineering

## Contexto

O [ADR-0020](0020-local-homologation-server-for-valuation.md) entregou a homologação da
medição por um servidor local fino (`croquito-valuation serve`) com uma fronteira escrita:
"ferramenta local, nunca produção", sem autenticação, identidade por flag de inicialização
(`--reviewer`), bind em `127.0.0.1` — e a condição de saída declarada no próprio ADR: "o
dia em que houver segundo usuário é o dia da sessão autenticada".

Esse dia chegou por duas vias ao mesmo tempo. A orçamentista do domínio homologa de outra
máquina, e a homologação hospedada ([ADR-0025](0025-homologacao-em-gcp-cloud-run.md)) põe o
servidor num host público. Levar o servidor local para lá como está seria publicar um
processo sem autenticação, em que "quem decidiu" é um parâmetro de linha de comando — ou
seja, o oposto do que a medição existe para registrar.

A sessão autenticada **completa** (tabelas próprias, rotas `/v1`, contratos TS gerados,
concorrência otimista real) continua sendo o destino de produto e continua custando um
marco grande. O que falta hoje não é esse marco: é o mínimo que torna honesta a frase
"a orçamentista aprovou".

## Decisão

O servidor de medição passa a ter um **modo hospedado explícito** (`serve --hosted`), e é
só nesse modo que ele pode subir fora da máquina do operador. O modo muda quatro coisas e
**nenhuma regra de domínio**:

- **Bearer JWT obrigatório em toda rota**, validado pelo validador compartilhado
  (`croquito_core.oidc`) contra o **mesmo realm** da sessão de cena — mesmo issuer, mesma
  audience, mesmo JWKS. Uma identidade só no ambiente; o servidor de medição não ganha
  fornecedor próprio nem lista de usuários própria.
- **Papel `orcamentista` exigido** como claim de realm. O papel existe no realm por causa
  desta decisão e não por conveniência: quem revisa takeoff e confirma código não é quem
  aprova cena.
- **`reviewer_id` derivado do token** (subject, com `preferred_username` como rótulo
  legível), no lugar da flag `--reviewer`. O carimbo continua sendo do servidor —
  `reviewer_role` e `decided_at` também —, e o corpo das requisições continua recusando
  esses campos (`extra="forbid"`). A diferença é a origem: claim assinado em vez de
  argumento de processo.
- **CORS restrito à origem do host público** e bind aberto permitido apenas neste modo. Sem
  `--hosted`, o comportamento local do ADR-0020 fica idêntico ao que é hoje, inclusive o
  aviso ao expor em outra interface.

O estado da rodada continua sendo um diretório de artefatos JSON atômicos, agora num volume
Cloud Storage montado por FUSE. Nada do domínio muda: as mesmas funções fail-closed do CLI,
a mesma guarda otimista por digest (`LOCAL_STATE_MOVED`), a mesma recusa de re-decisão, os
mesmos totais recomputados pelo servidor.

### O que continua limitado, e declarado

- **Uma rodada por ambiente.** O servidor sobe apontando um diretório (`--root`); trocar de
  rodada é trocar o argumento e publicar revisão nova.
- **No máximo uma instância.** O volume por FUSE não dá lock, e duas instâncias sobre o
  mesmo diretório não têm árbitro. Concorrência é resolvida pela guarda de digest entre
  abas do mesmo usuário, não entre processos.
- **Sem `base_version` real.** A lacuna registrada no ADR-0020 e no
  [Valuation Context](../architecture/VALUATION_CONTEXT.md) continua aberta: ela pertence à
  sessão autenticada completa, com banco.
- **As rotas continuam fora do [API Contract](../architecture/API_CONTRACT.md)**, que segue
  exclusivo da API autenticada de cena. O contrato do servidor de medição vive no docstring
  do módulo e nos testes.
- **O client `apps/medicao` segue descartável por construção.** Ele ganha login OIDC contra
  o mesmo realm, e nada mais: quando a sessão autenticada completa existir, as telas e os
  módulos puros migram e o servidor sai.
- **Sem multi-tenant.** O ambiente hospeda uma organização; o `tenant_id` do token não
  particiona rodada. Segundo tenant é a sessão autenticada completa, não um parâmetro.

## Alternativas

- **Manter só o servidor local do ADR-0020.** Rejeitada: a homologação continuaria presa a
  uma máquina, e a alternativa prática seria alguém operar em nome da orçamentista —
  exatamente o que enfraquece o ato humano que o registro existe para provar.
- **Migrar a medição para a API autenticada agora** (tabelas, rotas `/v1`, contratos
  gerados, fila). Rejeitada por custo e sequência: é o marco grande que o ADR-0020 já
  adiara, e ele ficaria entre a orçamentista e a primeira homologação hospedada.
- **Proteger com autenticação de borda** (proxy autenticador na frente do serviço).
  Rejeitada como substituto: a borda diz quem *entrou*, e o que a medição precisa é de quem
  *decidiu*, carimbado no artefato a partir de um claim assinado. Um segundo emissor de
  identidade ainda criaria duas verdades sobre a mesma pessoa.
- **Token de serviço compartilhado** (segredo único no ambiente). Rejeitada: identidade
  coletiva não registra ato individual, que é o conteúdo da decisão.

## Consequências

### Positivas

- A homologação real deixa de depender da máquina do desenvolvedor sem inventar um segundo
  mecanismo de identidade: mesmo realm, mesmo validador, mesmo formato de claim.
- O `reviewer_id` gravado no artefato passa a ser derivado de token assinado — a mesma
  qualidade de prova que a sessão de cena já tinha.
- O papel `orcamentista` entra no realm com um significado testado antes de a sessão
  autenticada completa existir, e migra sem tradução.

### Negativas

- Continua havendo duas superfícies de contrato temporárias (rotas locais × `/v1`), agora
  com uma delas exposta na internet.
- Uma instância e uma rodada por ambiente significam que dois usuários simultâneos disputam
  o mesmo diretório com a guarda de digest como único árbitro; é aceitável para homologação
  e não é operação de tenant.
- O modo hospedado é código que existirá até a sessão autenticada completa e depois será
  removido — dívida com data, e o ADR é onde ela fica escrita.

## Riscos e mitigação

| Risco | Mitigação |
|---|---|
| Servidor subir hospedado sem autenticação por engano | O modo é explícito (`--hosted`) e fail-closed: sem issuer/audience configurados o processo recusa subir, e sem a flag o bind continua local |
| Escrita concorrente sobre o volume por FUSE corromper artefato | Máximo de uma instância, escrita atômica e guarda otimista por digest; corrida entre processos continua fora do caso de uso |
| Token expirar no meio de uma revisão longa | O client renova pelo fluxo padrão OIDC; a rota recusa com código estável e a tela preserva o formulário, como já faz em `LOCAL_STATE_MOVED` |
| Papel `orcamentista` concedido a quem não decide medição | Criação de usuário é ato humano com procedimento escrito ([HML_KEYCLOAK](../operations/HML_KEYCLOAK.md)); o papel é separado dos papéis de cena |
| Modo hospedado virar "produção de fato" | Os limites acima (uma rodada, uma instância, sem tenant, sem `base_version`) estão escritos aqui e continuam sendo a definição do que falta |

## Rastreabilidade

- Requirements: fatia do destino declarado em
  [ADR-0020](0020-local-homologation-server-for-valuation.md) (que **não** é substituído — o
  servidor local segue existindo para a máquina do operador),
  [ADR-0011](0011-oidc-portable-identity.md) (identidade OIDC portável),
  [ADR-0016](0016-valuation-bounded-context.md) (contexto delimitado) e
  [ADR-0025](0025-homologacao-em-gcp-cloud-run.md) (ambiente que o hospeda).
- Supersedes: none
- Superseded by: none
