# F-034 — Evidência de execução

feature_id: F-034
status: `DONE` (entrega aceita por ato humano em 2026-08-23)
data da execução: 2026-08-22
data deste pacote: 2026-08-23

> **Este pacote foi montado um dia depois da execução**, ao fechar a dívida documental que a
> rodada de 2026-08-22 deixou: as três tasks foram entregues e commitadas na `main`, mas o
> `feature.md` e o roadmap ficaram em `READY_FOR_PLANNING` e nenhum `evidence.md` foi
> escrito. O que isso custa está declarado em §3.

## 1. Gates humanos

| Gate | Estado |
| --- | --- |
| Seleção | Exercida em 2026-08-22 |
| **Design Approval Package** da fatia 2 | **Aprovado por ato humano em 2026-08-22**, revisão 1 ([mock/README.md](mock/README.md)) |
| Fatia 1 sem pacote próprio | Decisão humana registrada em `Split` do contrato: não introduz valor visual novo, e cita a aprovação da aba Plataforma (F-012) como procedência |
| Declarar os estados por ambiente | **Pendente** — ato humano (§8) |
| Merge e deploy | Cumprido: `5839c19` na `main`, deploy de HML verde |
| **Aceite da entrega** | **Exercido por ato humano em 2026-08-23**, sobre este pacote |

A aprovação da revisão 1 **não** cobriu: a copy final, o estado padrão de uma jornada quando
o ambiente não declara nada, a fatia 1 e o nome das jornadas na tela. As **duas questões em
aberto** do pacote seguem em aberto e a aprovação não as decidiu (§8).

## 2. Baseline

Árvore limpa na `main` antes de cada task; portões verdes antes e depois. Nenhuma falha
preexistente foi atribuída a esta feature, e nenhuma foi introduzida.

## 3. Execução, e o que este pacote não alcança

| Task | Entrega | Commit |
| --- | --- | --- |
| T1 | Disponibilidade resolvida no servidor: estados por ambiente, migração `0008`, portão único por prefixo, `GET /v1/me` devolvendo `journeys` | `07f0cb3` |
| — | Tipo `Journey` e `Me.journeys` no cliente web, aplicado à parte por causa do `PLAN_DEVIATION` (§7) | `5eee5ab` |
| T2 | O seletor da SPA renderiza as jornadas que o servidor resolveu | `3221338` |
| T3 | Administração do entitlement por tenant na tela de Plataforma | `91740c9` |

**Limitação declarada desta rodada de evidência**: o `BUILD REPORT` de cada task —
`PRIMARY_EXECUTION_EVIDENCE` pelo contrato do Builder — viveu na sessão de orquestração de
2026-08-22 e **não é acessível aqui**. A tabela acima é reconstrução a partir das commits, do
diff e dos testes em árvore, todos verificáveis; ela **não substitui** os relatórios. Um
revisor que exija a evidência primária pode devolver `REVIEW_EVIDENCE_INCOMPLETE` com
`EVIDENCE_FINDING` por este motivo, e estará certo: está escrito aqui em vez de escondido.
O que segue nas seções 4 a 6 é evidência de primeira mão, produzida sobre o código como ele
está hoje.

### O que a revisão linha a linha achou na execução

Dois defeitos, ambos corrigidos com teste que foi **provado falhando sem a correção**, e os
dois testes estão em árvore e podem ser reexecutados:

1. **Jornada `disabled` abria sessão de banco antes de recusar** — consulta cujo resultado
   não podia mudar a resposta, no estado que mais segue recebendo tráfego (link antigo, aba
   aberta, bundle velho da SPA). Fixado por
   `tests/api/test_journeys.py::test_jornada_disabled_recusa_sem_consultar_o_banco`; a
   ordem corrigida está em `journey_gate` (`services/api/src/croquito_api/main.py:3867`),
   onde `disabled` recusa antes de `_entitled_journeys`.
2. **A lista de jornadas começava vazia na SPA**, então todo usuário via "nenhuma jornada
   liberada" durante a ida e volta do `/v1/me`. Aviso falso é pior que ausência. "Ainda não
   sei" passou a ser `null` e "sei que não há nenhuma" a ser lista vazia, coberto em
   `apps/web/src/App.test.tsx:158` — *enquanto a lista não foi resolvida, o seletor não
   mostra abas nem aviso*.

## 4. Verificação

Portões **reexecutados no HEAD de 2026-08-23**, com a árvore limpa:

```text
make check   → exit 0   (ruff, mypy strict, check_docs, drift de contratos, build web, terraform fmt)
make test    → exit 0   (pytest 2340 passed / 10 skipped; vitest web 1065; vitest field 261)
```

Testes específicos da feature, em árvore:

| Onde | O que cobre |
| --- | --- |
| `tests/api/test_journeys.py` | 30 testes: resolução pura, configuração de ambiente, portão nas rotas, entitlement e as rotas de plataforma |
| `apps/web/src/App.test.tsx` | `describe("seletor de jornadas")` — o que a SPA renderiza para cada lista recebida |
| `apps/web/src/plataforma/PlatformApp.test.tsx` | `EstadoDasJornadas`, `DisponibilidadeDeJornada`, `ColunaDoAmbiente`, `FormularioDeAutorizacao`, `LinhaAutorizacao` |
| `tests/api/test_migrations.py` | Cadeia linear e drift `migração × Base.metadata`, com a `0008` |

**O teste que cobra classificação de prefixo já pagou duas vezes**:
`test_toda_rota_v1_publicada_esta_classificada` reprova qualquer rota `/v1/` que nenhum
prefixo reivindique. No merge da rodada seguinte ele pegou `/v1/surveys` (F-032) e
`/v1/metrics/summary` (F-031) chegando sem portão; ambos foram classificados como fora de
jornada, com o porquê escrito em `JOURNEYLESS_ROUTE_PREFIXES`
(`services/api/src/croquito_api/journeys.py`). Foi para isso que ele foi escrito.

## 5. Critérios de aceite

| # | Critério | Onde está provado |
| --- | --- | --- |
| 1 | `make check` e `make test` verdes; goldens intocados | §4 |
| 2 | Ambiente sem configuração declarada se comporta como hoje | `test_ambiente_sem_variavel_declarada_deixa_as_tres_jornadas_ligadas`, `test_sem_configuracao_declarada_a_rota_da_jornada_responde_como_hoje` |
| 3 | `disabled` some do seletor e a rota recusa com código estável, mesmo com papel válido | `test_jornada_disabled_recusa_403_com_codigo_estavel_mesmo_com_papel_valido`, `test_jornada_disabled_some_da_lista_de_me` |
| 4 | `pilot` abre para o tenant autorizado e recusa **igual** para os demais, sem vazar o piloto | `test_piloto_abre_para_o_tenant_autorizado_e_recusa_igual_para_os_demais`, `test_entitlement_de_uma_jornada_nao_abre_outra`; a recusa única está em `_journey_unavailable` |
| 5 | `GET /v1/me` devolve a lista já resolvida pelas três perguntas | `test_resolucao_compoe_ambiente_tenant_e_papel_nesta_ordem`, `test_conceder_e_revogar_mudam_o_que_o_tenant_ve_em_me` |
| 6 | A tela não recalcula papel: renderiza a lista que recebeu | `describe("seletor de jornadas")` em `App.test.tsx` |
| 7 | Fatia 2 corresponde à revisão aprovada, e autorizar registra quem e quando | `describe("DisponibilidadeDeJornada")` e `LinhaAutorizacao` em `PlatformApp.test.tsx`; `test_conceder_registra_contrato_autor_e_data_e_aparece_na_listagem`, `test_revogar_carimba_a_data_e_mantem_a_linha_na_lista` |

O bloco de histórico do pacote de design ficou **reservado** de propósito — é a F-017 — e há
teste que prova que ele não foi construído (`não constrói o bloco reservado ao histórico`).

## 6. Superfície entregue

| Superfície | O que é |
| --- | --- |
| `CROQUITO_JOURNEY_CROQUI` / `_MEDICAO` / `_ORCAMENTO` | Estado por ambiente; valor inválido recusa na **subida** da API, não no primeiro request |
| Migração `0008_tenant_journey_entitlements` | Entitlement por (tenant, jornada), no molde exato do entitlement de IA |
| `GET /v1/me` | Ganhou `journeys` |
| `GET /v1/platform/journeys` | Estado das três jornadas e toda autorização concedida, inclusive as revogadas |
| `PUT /v1/platform/tenants/{tenant_id}/journey-entitlements/{journey}` | Concede ou revoga por ato nominal, com `Idempotency-Key` e referência de contrato obrigatória |
| `services/api/src/croquito_api/journeys.py` | A parte pura: tipos, mapa de prefixo → jornada, e as funções de decisão, sem importar `config`, `database` nem `fastapi` |

O portão entra **uma vez**, como dependência do router (`dependencies=[Depends(journey_gate)]`),
e declara só `Request` — qualquer outro parâmetro viraria `security`/`parameters` no OpenAPI
de todas as rotas, inclusive das públicas, e abriria sessão de banco até no `/healthz`.

## 7. Desvios de plano

`PLAN_DEVIATION` registrado no [plano](plan.md), achado na revisão **antes** do despacho: o
plano declarava "sem `PARALLELISM_RISK`" entre T2 e T3, e estava errado — as duas editariam
`apps/web/src/plataforma/api.ts`. Resolução: o tipo (`Journey` + `Me.journeys`) saiu do escopo
da T2 e foi aplicado à parte (`5eee5ab`), deixando T2 com `App.tsx`/`App.test.tsx` e T3 com
`plataforma/**` e as rotas. Impacto no comportamento entregue: nenhum.

## 8. Riscos remanescentes e decisões humanas pendentes

1. **Nenhum ambiente declara estado de jornada.** `.github/workflows/deploy-hml.yml` não
   define `CROQUITO_JOURNEY_*`, então HML roda com o padrão `enabled` nas três. O mecanismo
   está no ar e **dormente**: a pergunta que originou a feature — desligar o Croqui em
   homologação — só é respondida quando alguém declarar o estado. É ato humano de operação,
   não código.
2. **O padrão `enabled` é fail-open**, por decisão humana de 2026-08-22 registrada nas
   premissas do plano: um módulo novo nasce visível a menos que alguém o declare. Foi a
   única escolha que não muda o comportamento de nenhum ambiente existente ao subir a
   feature, e é reversível sem custo de dado.
3. **O entitlement por tenant só é exercitável em `pilot`.** Conceder numa jornada `enabled`
   ou `disabled` é recusado pelo servidor, com a frase por extenso — e enquanto nenhum
   ambiente declara `pilot` (risco 1), a seção nova da tela não tem o que administrar.
4. **As duas questões em aberto do pacote de design** seguem sem decisão, e o código não as
   decidiu em silêncio: se a lista deve mostrar **todos** os tenants conhecidos ou só os que
   têm autorização (hoje mostra só os que têm), e se revogar deve pedir confirmação (hoje não
   pede).
5. **A copy das telas novas** está fora da aprovação da revisão 1, por declaração do próprio
   registro.
6. **Migração `0008`**: aplicada no hospedado pelo job de banco no deploy de `5839c19`, que
   saiu verde.
