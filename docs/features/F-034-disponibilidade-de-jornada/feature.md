# F-034 — Disponibilidade de jornada por ambiente e por tenant

## Status

`READY_FOR_PLANNING`

> O estado vale para a **fatia 1**, que é a parte planejável. A **fatia 2** está
> `BLOCKED` pelo Design Approval Package e não pode ser planejada — ver **Split**.
>
> Nasce em 2026-08-22, de uma pergunta de operação: como impedir que um módulo ainda
> imaturo — hoje o Croqui — chegue a homologação, e como, mais adiante, liberá-lo para um
> cliente piloto sem liberá-lo para todos.
>
> A feature é dividida por decisão humana registrada (ver **Split**): a fatia 1 não cria
> superfície nova e pode ser planejada; a fatia 2 cria uma seção nova na tela de
> Plataforma e fica `BLOCKED` até o Design Approval Package ser aprovado.

## Classification

`INTERFACE_CHANGE` — a fatia 2 cria superfície nova percebida por humano (a administração
da disponibilidade por tenant, na tela de Plataforma).

## Priority

`HIGH` — sem isso, a única forma de não expor um módulo imaturo é não fazer deploy dele,
o que acopla a maturidade de uma jornada ao ciclo de entrega de todas as outras.

## Problem

Hoje uma jornada existe em todos os ambientes e para todos os tenants assim que o código
sobe. Não há como dizer "o Croqui ainda não está pronto para homologação" nem "o Croqui
está liberado só para este cliente piloto".

As duas perguntas parecem a mesma e não são, e é isso que o produto precisa expressar:

- **"ainda não está pronto"** é uma condição temporária de engenharia, decidida por
  ambiente, que deve desaparecer quando o módulo amadurecer;
- **"este cliente contratou"** é uma decisão comercial duradoura, por tenant, que precisa
  de registro de quem autorizou e quando.

Tratar as duas com o mesmo interruptor produz um dos dois defeitos: ou a decisão temporária
ganha tela de administração e alguém liga um módulo inacabado em produção, ou a decisão
comercial vira variável de ambiente e deixa de ter auditoria.

O produto já resolveu exatamente esse par para o processamento de IA — flag de ambiente
(`CROQUITO_REAL_PROVIDERS_ENABLED`, padrão `false`) mais entitlement por tenant
administrado por `platform_operator` ([F-012](../F-012-operacao-saas-autorizacao-ia/feature.md),
[ADR-0036](../../adr/0036-autorizacao-de-ia-contratual-sem-allowlist-documental.md)). Esta
feature aplica o mesmo par às jornadas.

## Desired Outcome

Cada jornada tem um estado declarado por ambiente. Em `pilot`, ela existe apenas para os
tenants explicitamente autorizados, e essa autorização é um ato nominal e auditável na tela
de Plataforma. A tela mostra só as jornadas que a pessoa pode de fato abrir, e o servidor
recusa as demais — esconder é ergonomia, autorizar é do backend.

## Scope

### Três estados por jornada, declarados no ambiente

```text
enabled    a jornada existe para todos os tenants
pilot      a jornada existe só para tenants com entitlement
disabled   a jornada não existe neste ambiente
```

Três estados em vez de um booleano é o que evita o padrão falho: sem `pilot`, "liberar para
um cliente" exigiria ligar para todos. Jornadas cobertas: `croqui`, `medicao`, `orcamento`.
A Plataforma não entra — ela já é governada por papel e é onde esta feature é administrada.

### As três perguntas compõem, nesta ordem

```text
AMBIENTE  a jornada existe aqui?        →  estado declarado
TENANT    este cliente tem acesso?      →  entitlement, só quando `pilot`
PESSOA    este usuário tem o papel?     →  papel do JWT, como hoje
```

Uma jornada só aparece e só responde quando as três passam. Ordem importa: o ambiente é a
pergunta mais barata e a que menos depende de dado.

### `GET /v1/me` passa a devolver as jornadas disponíveis

A resolução das três perguntas acontece **no servidor**, e a SPA renderiza o que ele
respondeu. É o que impede a tela de reimplementar autorização: hoje ela já lê `roles` de
`/v1/me` em vez de decodificar token, e o mesmo princípio se estende às jornadas.

### Recusa nas rotas

Rota de jornada indisponível recusa com código estável, do mesmo modo que a rota de
plataforma recusa sem `platform_operator`. Esconder a aba não basta: a URL continua
alcançável.

## Split

Decisão humana de 2026-08-22, registrada conforme o workflow de design approval, que prevê
dividir para que trabalho sem superfície prossiga com o gate aberto:

- **Fatia 1** — estados por ambiente, tabela de entitlement, resolução em `/v1/me`, recusa
  nas rotas, e a aba passando a consumir a lista de jornadas. **Não introduz valor visual
  novo**: renderizar condicionalmente um botão do seletor conforme permissão vinda do
  backend é exatamente o mecanismo já aprovado e em produção para a aba Plataforma
  (F-012). Nenhuma cor, tipografia, espaçamento ou componente novo. Por isso segue para
  planejamento sem pacote próprio, citando aquela aprovação como procedência.
- **Fatia 2** — a seção de administração por tenant na tela de Plataforma. Superfície nova,
  `DESIGN_APPROVAL_REQUIRED`, `BLOCKED` até aprovação.

Se a leitura da fatia 1 for contestada, ela volta para trás do gate — a decisão está
registrada aqui justamente para poder ser contestada.

## Out of Scope

- Papel novo, ou mudança em qual papel autoriza qual jornada.
- Gradual rollout por percentual de usuários, canary ou teste A/B.
- Disponibilidade por projeto, por obra ou por rodada — a granularidade aqui é a jornada.
- Mudança em qualquer regra de preço, cascata ou medição.

## Acceptance Criteria

1. `make check` e `make test` verdes; goldens intocados.
2. Ambiente sem configuração declarada se comporta exatamente como hoje — coberto por
   teste que estende os existentes sem enfraquecê-los.
3. Jornada `disabled`: some do seletor, e cada rota dela recusa com código estável mesmo
   quando chamada direto, com papel válido.
4. Jornada `pilot`: tenant com entitlement abre; tenant sem entitlement recebe a mesma
   recusa da `disabled`, sem vazar a existência do piloto.
5. `GET /v1/me` devolve a lista de jornadas já resolvida pelas três perguntas.
6. A tela não recalcula papel: ela renderiza a lista que recebeu.
7. Fatia 2: a tela corresponde à revisão aprovada do Design Approval Package, e o ato de
   autorizar registra quem autorizou e quando, no molde da autorização de IA.

## Constraints

- Fail-closed em erro de leitura: se a lista de jornadas não puder ser resolvida, a SPA não
  oferece jornada nenhuma — é o comportamento que `/v1/me` já tem hoje para papéis.
- `tenant_id` vem sempre do JWT, nunca do corpo.
- O entitlement por tenant é administrado apenas por `platform_operator`.
- Nenhuma decisão de disponibilidade é tomada no navegador.

## Dependencies

- **Design Approval Package** da fatia 2 — `DESIGN_APPROVAL_REQUIRED`, ato humano, precede
  o planejamento dela.
- F-012 (autorização de IA por tenant) — é o molde de dado, de rota e de tela que esta
  feature copia.

## Unknowns

1. **Padrão do estado quando o ambiente não declara nada.** A proposta é `enabled` para
   todas, para que nenhum ambiente existente mude de comportamento ao subir esta feature,
   e que os ambientes hospedados declarem explicitamente. É a única escolha que não exige
   configurar tudo antes de fazer deploy, mas é fail-open: um módulo novo nasce visível a
   menos que alguém o declare. **Decisão humana pendente.**
2. **Quem é a fonte da lista de jornadas** — configuração de ambiente por jornada, ou uma
   lista única. Detalhe de forma, não de comportamento; sai no plano.
3. Se `disabled` deve devolver `404` em vez de `403`, para não revelar que a jornada
   existe. Depende de a existência do módulo ser ou não informação sensível.

## Risks

- **Interruptor esquecido**: flag de release que nunca é removida vira dívida silenciosa.
  Mitigação: cada jornada em `disabled` ou `pilot` nasce com dono e data de revisão
  registrados no roadmap, e o estado aparece em `/v1/me`, que é legível em qualquer
  ambiente.
- **Falsa sensação de proteção**: esconder a aba não protege nada por si. Mitigação: o
  critério de aceite 3 exige que a recusa seja testada na rota, com papel válido.
