# F-002 — Pacote de evidências

Status: `DONE`
Responsável: Engineering
Última revisão: 2026-08-17 (aceitação humana do ADR-0028, seção 9)

Este documento registra a autorização humana, a baseline, a apuração do inventário de rotas e
a validação determinística de F-002. Ele não é aprovação humana e **não** aceita o ADR que a
feature produziu.

## 1. Contrato e entregáveis

| Artefato | Fonte |
| --- | --- |
| Feature Contract | [feature.md](feature.md) |
| ADR produzido pela feature (`Accepted` em 2026-08-17, ver seção 9) | [ADR-0028](../../adr/0028-medicao-na-api-v1-autenticada.md) |
| Seção de contrato | [API Contract](../../architecture/API_CONTRACT.md), seção "Medição de obra" |
| Índice de ADRs atualizado | [docs/adr/README.md](../../adr/README.md) |
| Glossário do contexto | [Valuation Context](../../architecture/VALUATION_CONTEXT.md), entrada `Rodada de medição` |
| Feature de execução, ainda bloqueada | [F-003](../F-003-medicao-v1-migration/feature.md) |

## 2. Autorização humana

**2026-08-17.** A seleção deste contrato é a decisão 4 da
[seção 10 do evidence de F-001](../F-001-roadmap-clarification/evidence.md), que escolheu a
migração da medição para a API `/v1` como o item `PLANEJADO` a receber Feature Contract próprio,
decomposto em F-002 (contrato) e F-003 (execução).

Na mesma data, o responsável pelo produto decidiu os quatro pontos que o contrato de F-002
nomeia como portão humano ou risco de decisão indevida:

| # | Questão | Decisão |
| --- | --- | --- |
| 1 | Entidade raiz e path base das rotas de medição | **`ValuationRound`, sob `/v1/valuation-rounds/{round_id}`.** Registrada como D1 do ADR-0028. |
| 2 | Escopo de tenant da rodada (consequência de isolamento de dados) | **`tenant_id` do JWT, sem chave estrangeira para `projects`.** Registrada como D8. |
| 3 | Destino das telas de `apps/medicao` (fronteira entre apps) | **Migram para `apps/web`;** `apps/medicao` sai junto do modo hospedado. Registrada como D9, com a tensão em relação ao ADR-0020 declarada no próprio ADR. |
| 4 | Criação da entrada de F-002 no roadmap canônico | **Autorizada, em commit próprio,** separado do commit que versiona o trabalho de F-001, como manda a seção 10 do evidence de F-001. |

Esta autorização **não** aceita o ADR-0028. Aceitação de ADR é ato humano posterior, e nenhum
agente move um ADR de `Proposed` para `Accepted`.

## 3. Baseline

| Fato | Valor |
| --- | --- |
| Commit base | `a92fda7` — `docs(adr): ratify approved architecture decisions` |
| Branch de trabalho | `docs/f-002-medicao-v1-contract`, criada a partir de `main` |
| Worktree no início | `M docs/product/ROADMAP.md` e os diretórios não rastreados `docs/features/F-001*`, `F-002*`, `F-003*`, `F-005*` — todos saídas de F-001, versionados no primeiro commit desta branch (`beb59db`) |
| Publicação | `main` já estava à frente de `origin/main` antes desta feature; condição preexistente, não tocada aqui |
| Ocorrência operacional | Havia um `.git/index.lock` órfão de 13:13 sem processo git correspondente; removido para permitir o `git add`. Nenhum estado de índice foi perdido |
| Falhas preexistentes conhecidas | Nenhuma registrada |

## 4. Apuração do inventário de rotas

A contagem é apurada a partir do arquivo, não herdada de documento. Comando e saída literal:

```text
$ grep -n "@router\." services/worker/src/croquito_worker/valuation/local_server.py
1994:    @router.get("/state", tags=["state"])
1998:    @router.get("/takeoff", tags=["takeoff"])
2009:    @router.get("/images/plate", tags=["images"])
2027:    @router.get("/images/overlay", tags=["images"])
2034:    @router.post("/plates", status_code=202, tags=["plates"])
2059:    @router.post("/plates/extract", status_code=202, tags=["plates"])
2080:    @router.post("/takeoff/decisions", tags=["takeoff"])
2123:    @router.get("/suggestions", tags=["codes"])
2156:    @router.post("/suggestions/recompute", tags=["codes"])
2224:    @router.get("/catalog/search", tags=["codes"])
2270:    @router.get("/codes", tags=["codes"])
2291:    @router.post("/codes/decisions", tags=["codes"])
2362:    @router.post("/calc/build", tags=["bulletin"])
2395:    @router.get("/bulletin", tags=["bulletin"])
2407:    @router.post("/dossier/build", tags=["bulletin"])
2432:    @router.get("/dossier", tags=["bulletin"])

$ grep -c "@router\." services/worker/src/croquito_worker/valuation/local_server.py
16
```

**Contagem apurada: 16 rotas** no `router`, que é criado em `local_server.py:1960` e incluído no
app em `local_server.py:2447`. As 16 aparecem exatamente uma vez na tabela de inventário do
ADR-0028, cada uma com a linha de origem e o destino declarado.

`GET /healthz` é declarado fora do `router`, em `local_server.py:2505`, dentro de
`create_hosted_app`; é sonda de saúde do app hospedado e o contrato de F-002 o exclui do
inventário por decisão explícita.

O "~7 rotas" citado no [ADR-0020](../../adr/0020-local-homologation-server-for-valuation.md)
antecede M6, M7 e M8. Ele **não** descreve o estado atual e não foi usado como estimativa em
nenhum ponto desta entrega.

## 5. Fronteiras respeitadas

- Nenhum ADR existente mudou de status. `ADR-0028` nasce `Proposed`.
- Nenhuma decisão fixada foi reaberta: o contexto delimitado do ADR-0016, a identidade OIDC
  portável do ADR-0011, a separação de papéis do ADR-0026 e o ADR-0020, que segue válido para a
  máquina do operador.
- A tensão entre D9 (telas em `apps/web`) e a rejeição de `apps/web` feita pelo ADR-0020 no M6
  está registrada como tensão dentro do próprio ADR-0028, não resolvida em silêncio.
- Nenhum nome proposto usa `Job`, `Measurement*` ou `*Budget*`.
- A seção "Medição de obra" do API Contract abre declarando que descreve rota **proposta e não
  implementada**, para não induzir a erro um teste de paridade entre rotas reais e contrato
  ([F-005](../F-005-openapi-contract-test/feature.md)).
- Os sete códigos de erro propostos ficam em lista própria dentro da seção "Códigos
  obrigatórios", marcados como ainda não implementados; passam para a lista principal quando as
  rotas existirem.

## 6. Fora de escopo, e por quê

- **Aceitar o ADR-0028.** Ato humano.
- **Implementar qualquer coisa**: rota, tabela, migration, contrato TS gerado, tela, realm.
- **Entrada na [matriz de rastreabilidade](../../engineering/TRACEABILITY.md).** A matriz mapeia
  requisito → design → decisão → **verificação**; um ADR sem implementação não tem verificação
  a citar, e isso continua verdade depois da aceitação — o motivo nunca foi o status, foi a
  ausência de código e teste. A linha é criada junto da execução de F-003. O passo 5 do
  processo de ADR fica cumprido pela metade de forma declarada, não por omissão.
- **Mudar o status `BLOCKED` de F-003.** O desbloqueio depende da aceitação do ADR, não da
  existência do rascunho.

## 7. Validação determinística

`make check` executado em 2026-08-17 sobre o estado desta rodada, com **exit code 0**. Os
portões percorridos, na ordem do `Makefile`:

```text
uv run ruff check .
uv run ruff format --check .
uv run mypy packages/core/src packages/valuation/src services/api/src services/worker/src tests
  → Success: no issues found in 166 source files
uv run python scripts/check_docs.py
uv run python -m croquito_core.schema_export --check packages/contracts/scene.schema.json
npm run contracts:check
npm run web:check      → build ok
npm run medicao:check  → build ok
terraform fmt -check -recursive infra
```

`scripts/check_docs.py` é o portão que interessa a uma entrega documental: ele valida bloco de
código fechado e **todo link relativo de Markdown do repositório**, inclusive os links novos do
ADR-0028, da seção do API Contract e deste arquivo.

Nenhum portão foi contornado e nenhuma falha em área não tocada foi corrigida de passagem.

## 8. Escopo verificado do diff

`git status --short` durante a rodada mostra alteração somente sob `docs/`. Nenhum arquivo de
`services/`, `packages/`, `apps/`, `infra/` ou `keycloak/` foi tocado — coerente com uma entrega
que decide contrato e não implementa nada.

As entradas de backlog de F-002, F-003 e F-005 no roadmap canônico vão em **commit próprio**,
separado tanto do commit que versiona o trabalho de F-001 quanto do commit desta entrega, como
determina a seção 10 do evidence de F-001.

## 9. Aceitação humana do ADR-0028

**2026-08-17.** O responsável pelo produto **aceitou o ADR-0028**, depois de a tensão da
decisão D9 lhe ser apresentada nominalmente: as telas de medição passam a viver em `apps/web`,
o que contraria a rejeição que o [ADR-0020](../../adr/0020-local-homologation-server-for-valuation.md)
fez daquele app no M6. A aceitação foi dada com essa tensão à vista, e ela permanece escrita
dentro do próprio ADR.

Este é o ato humano que as seções 2 e 6 registravam como pendente. Ele não altera nada do que
está acima: as seções 1 a 8 continuam preservadas como executadas, inclusive as frases que
descrevem o ADR como `Proposed` — elas eram verdadeiras no momento da entrega, e reescrevê-las
apagaria o registro do processo.

### O que a aceitação muda

| Alvo | Antes | Depois |
| --- | --- | --- |
| `docs/adr/0028-medicao-na-api-v1-autenticada.md` | `Proposed` | `Accepted`; **só a linha de status mudou** — o corpo do ADR congela |
| F-002 (esta feature) | `READY_FOR_HUMAN_REVIEW` | `DONE` |
| F-003 | `BLOCKED` | `READY_FOR_PLANNING` |

Na mesma decisão o responsável escolheu que o trabalho **permanece na branch local**
`docs/f-002-medicao-v1-contract`, sem push, sem PR e sem merge.

### O que a aceitação NÃO muda

- **Nada está implementado.** Nenhuma rota de medição existe em `services/api`, nenhuma tabela
  foi criada, nenhum contrato TS foi gerado e nenhuma tela migrou. A ponte hospedada do
  [ADR-0026](../../adr/0026-medicao-hospedada-sessao-autenticada-minima.md) continua sendo o
  caminho real da homologação, e a condição de remoção dela segue por cumprir.
- **Os demais portões humanos de F-003 continuam de pé**, porque são de execução e não de
  planejamento: decisão sobre o runner de migrations revisadas antes de qualquer tabela
  (lacuna do [ADR-0025](../../adr/0025-homologacao-em-gcp-cloud-run.md)), remoção do serviço
  hospedado e da rota de borda, e alteração de realm Keycloak.
- **O ADR passa a ser imutável.** Rever qualquer uma das nove decisões exige ADR novo com
  `Supersedes`, conforme o [AGENTS.md](../../../AGENTS.md) da raiz — inclusive a D9, se o
  estado de `apps/web` reprovar a escolha na hora de executar.
