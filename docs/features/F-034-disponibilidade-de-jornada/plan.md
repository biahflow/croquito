# F-034 — Plano de execução da fatia 1

feature_id: F-034 (fatia 1)
goal: resolver a disponibilidade de cada jornada no servidor — ambiente, tenant e papel —
e fazer a SPA renderizar a lista que recebeu, sem reimplementar autorização.

assumptions:
- Estado padrão `enabled` quando o ambiente não declara nada (decisão humana de 2026-08-22):
  é a única escolha que não altera o comportamento de nenhum ambiente existente ao subir a
  feature. Ambientes hospedados declaram explicitamente.
- Recusa é `403` com código estável, coerente com o `FORBIDDEN` já usado nas rotas de
  plataforma. O `404` do Unknown 3 do contrato foi descartado: a existência das jornadas já
  é pública no produto, e trocar o código esconderia a causa de quem depura.
- A fatia 2 (administrar o entitlement pela tela) está `BLOCKED`; até lá o entitlement é
  criado apenas por migração/console de banco, o que basta para exercitar `pilot`.

risks:
- `main.py` é arquivo grande e vivo; T1 toca a montagem do app. Mitigação: o portão entra
  em UM lugar (dependência por prefixo), não em 57 rotas.
- Um prefixo novo esquecido no mapa fica sem portão. Mitigação: teste que percorre as rotas
  publicadas e falha se um prefixo `/v1/` não estiver classificado como jornada ou como
  explicitamente fora de jornada.

tasks:
  - id: T1
    role: builder
    goal: disponibilidade resolvida no servidor e aplicada nas rotas
    scope: config (estados por jornada), modelo + migração 0008 do entitlement por jornada,
      função de resolução (ambiente → tenant → papel), portão por prefixo na montagem do
      app, `GET /v1/me` devolvendo `journeys`, snapshot de OpenAPI, testes de API.
    out_of_scope: qualquer arquivo de `apps/web`; tela de administração (fatia 2); mudança
      em papéis; mudança em qualquer regra de preço, cascata ou medição.
    depends_on: []
    validation: make check, make test
    relative_effort: M
  - id: T2
    role: builder
    goal: a SPA renderiza a lista de jornadas que o servidor resolveu
    scope: `apps/web/src/App.tsx` (seletor por `journeys`, aterrissagem na primeira
      disponível, aviso escrito quando a lista vem vazia), tipo em `plataforma/api.ts`,
      testes de `App.test.tsx`.
    out_of_scope: qualquer arquivo de `services/`; lógica de papel no navegador; guarda de
      rota por papel (URL direta segue montando a jornada para o usuário ler o `403`).
    depends_on: [T1]
    validation: npm --workspace @croquito/web run test, run check
    relative_effort: S

parallel_groups: nenhum — T2 consome o contrato que T1 publica.
critical_path: T1 → T2.
integration_strategy: commits separados por task na `main`, com revisão linha a linha entre
  eles; nenhuma task encerra com portão vermelho.
human_gates: fatia 2 permanece `BLOCKED` pelo Design Approval Package. A decisão do estado
  padrão está registrada em assumptions e pode ser revertida sem custo de dado.
