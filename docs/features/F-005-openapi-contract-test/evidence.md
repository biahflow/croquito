# F-005 — Pacote de evidências

Status: `DONE`
Responsável: Engineering
Última revisão: 2026-08-17

Este documento registra a autorização humana, a baseline e a validação determinística de
F-005. Ele não é aprovação humana.

## 1. Contrato e decisão

| Artefato | Fonte |
| --- | --- |
| Feature Contract | [feature.md](feature.md) |
| Plano aprovado | [plan.md](plan.md) |
| Exigência que este trabalho fecha (1/2) | [Testing Strategy](../../engineering/TESTING_STRATEGY.md), seção "Contrato" — "OpenAPI snapshots/breaking changes" |
| Exigência que este trabalho fecha (2/2) | [API Contract](../../architecture/API_CONTRACT.md), seção "Compatibilidade" — "OpenAPI gerado deve ser comparado em CI para detectar breaking changes" |
| Precedente de gerador de contrato usado como modelo (não estendido) | `packages/core/src/croquito_core/schema_export.py` |

## 2. Autorização humana

**2026-08-17.** O responsável selecionou F-005 como próxima feature, aprovou o contrato e o
plano, e decidiu dois pontos de desenho que o Feature Contract deixava como `Unknowns`
antes de qualquer código:

| # | Questão | Decisão |
| --- | --- | --- |
| 1 | O que fazer com divergência preexistente que o gate revelasse | **Congelar as 5 divergências preexistentes como exceção declarada de baseline** (constante `BASELINE` em `tests/api/test_openapi_contract.py`); corrigi-las é trabalho próprio, com decisão humana sobre qual lado — código ou documentação — está errado em cada caso |
| 2 | Onde o snapshot vive | **`tests/api/openapi.snapshot.json`**, regenerado por alvo `make` próprio (`make openapi-snapshot`), separado do alvo `contracts` e sem entrada nova em `make check` |

Essas duas decisões não autorizam corrigir nenhuma das 5 divergências, nem estender
`croquito_core.schema_export`, nem alterar rota, modelo ou comportamento de
`services/api/src/croquito_api/main.py`.

## 3. Baseline

| Fato | Valor |
| --- | --- |
| Commit base | `be82529` — `feat(api): runner de migrations revisadas com Alembic (F-004)` |
| Branch de trabalho | `docs/f-002-medicao-v1-contract`, não publicada |
| `git status --short` antes da mudança | limpo |
| Testes coletados por `uv run pytest --co` | **1285** |
| `make check` antes da mudança | exit 0 |
| Rotas `/v1` expostas pela aplicação | **26** (`GET /healthz` tem `include_in_schema=False` e não entra no OpenAPI nem no gate) |
| Falhas preexistentes conhecidas | Nenhuma |

## 4. Validação determinística

| Portão | Resultado |
| --- | --- |
| `uv run pytest tests/api/test_openapi_contract.py -v` | 11 passed |
| Idempotência da geração | `--output` para caminho temporário e `diff` contra o versionado: idênticos |
| `make check` | exit 0 (ruff, ruff format, mypy strict, `check_docs`, drift de contratos, builds web e medição, `terraform fmt`) |
| `uv run pytest` | 1289 passed, 7 skipped — os skips são os testes de migration de F-004, que pulam sem PostgreSQL local, por desenho |
| `make test` | exit 0 — web 346, medição 127 |
| Testes coletados | 1285 na baseline → **1296** (+11) |
| `git status --short services/api/src/croquito_api/main.py` | sem saída — `main.py` não foi tocado |

Os números acima são os da rodada final, depois da correção da seção 6 (achado 3). A rodada
anterior à revisão humana fechara com 10 testes no arquivo, 1288 passed e 1295 coletados.

## 5. Prova de que o gate morde

Três perturbações foram aplicadas e revertidas antes de encerrar o trabalho, confirmando
que cada gate falha nomeando método e caminho, e não apenas "algo divergiu":

1. **Rota `/v1` de brinquedo em `main.py`** → `test_toda_rota_exposta_esta_no_contrato` e
   `test_o_snapshot_versionado_descreve_a_superficie_atual` falharam nomeando a rota nova
   (não documentada) e o snapshot desatualizado. Revertido com
   `git checkout -- services/api/src/croquito_api/main.py`.
2. **Remoção de uma linha de rota do `API_CONTRACT.md`** →
   `test_toda_rota_exposta_esta_no_contrato` falhou nomeando a rota que deixou de estar
   documentada. Revertido.
3. **`summary` alterado no snapshot versionado** →
   `test_o_snapshot_versionado_descreve_a_superficie_atual` falhou com
   `GET /v1/meta: definição divergente entre a aplicação e o snapshot versionado`, citando
   `make openapi-snapshot` como caminho de correção. Regenerado com `make openapi-snapshot`.

As três provas foram executadas de novo pelo revisor, depois das correções da seção 6, e não
apenas relatadas pela implementação. As provas 2 e 3 foram executadas **uma terceira vez**
depois da correção do achado 3 (que mexe em `_operations`, usada pelos dois gates), com o
mesmo resultado: `GET /v1/meta: definição divergente entre a aplicação e o snapshot versionado`
para o snapshot adulterado, e as duas mensagens de paridade — rota exposta e ausente do
contrato, rota documentada como vigente e não exposta — para a rota renomeada no
`API_CONTRACT.md`. As duas perturbações foram revertidas por cópia intacta, com `diff`
confirmando a restauração.

## 6. Revisão: três achados corrigidos antes do commit

A revisão linha a linha do diff devolvido pela implementação encontrou dois defeitos, e a
revisão humana de 2026-08-17 acrescentou um terceiro. Os três foram corrigidos e cobertos por
teste; nenhum chegou ao commit.

**Achado 1 — o teste da direção de falha do snapshot não testava nada.** A primeira versão de
`test_documento_alterado_reprova_contra_o_snapshot` afirmava que duas strings literais
diferentes eram diferentes e envolvia um `assert` falso em `pytest.raises(AssertionError)`.
Ele exercitava o `assert` do Python, não o gate: nenhuma linha de lógica de produção era
chamada. O critério de aceite — "existe teste que falha quando o documento gerado difere do
snapshot, e passa quando são iguais; ambas as direções são demonstradas" — não estava
cumprido.

**Correção.** A comparação virou função pura `snapshot_errors(gerado, versionado)`, comparada
por operação (`MÉTODO /caminho`) em vez de texto contra texto, usada tanto pelo teste do
documento real quanto pelo sintético. Ganho colateral: a mensagem de falha passa a nomear
exatamente qual rota entrou, saiu ou mudou de definição, em vez de mandar o leitor comparar
157 KB de JSON à mão. Divergência fora de `paths` nomeia a chave de topo que mudou.

**Achado 2 — o estado PENDENTE/VIGENTE dependia da ordem das seções.** A resolução usava
`setdefault`, ficando com a primeira menção da rota, sob um comentário afirmando que
repetições "pertencem à mesma seção". A afirmação é falsa no documento real:
`POST /v1/uploads/presign` é documentada em "Uploads" (`API_CONTRACT.md:35`, vigente) e citada
de novo dentro de "Medição de obra" (`:605`, pendente), porque a prancha da medição sobe por
ela. O resultado só estava correto porque "Uploads" vem antes no arquivo — reordenar as seções
faria o gate acusar como pendente uma rota exposta e correta. Falso positivo em gate é o que
leva alguém a desligar o gate.

**Correção.** Uma rota é `PENDENTE` apenas quando **todas** as suas menções estão em seção
pendente, o que independe da ordem. Coberto por
`test_rota_citada_em_secao_pendente_e_em_secao_vigente_continua_vigente`, que reproduz o caso
real com as seções invertidas.

Os dois testes acrescentados pela revisão (mais
`test_divergencia_fora_de_paths_nomeia_a_chave_que_mudou`) explicam a diferença entre os 8
testes previstos no plano e os 10 entregues.

**Achado 3 — chave de path item lida como método HTTP.** Levantado na revisão humana de
2026-08-17, antes do commit. `_operations` tratava **qualquer** chave de um Path Item Object
como método. A spec OpenAPI permite ali, além dos métodos, `parameters`, `summary`,
`description`, `servers` e `$ref`: um documento com esses campos produziria mensagem de falha
como `PARAMETERS /v1/x: definição divergente`, mandando o leitor procurar um método HTTP que
não existe. Nenhuma rota atual expõe esses campos — o documento gerado hoje tem só `get`,
`post` e `put` —, então o defeito era latente, não ativo; o custo dele é o gate perder
credibilidade justamente quando falha.

**Correção.** `_HTTP_METHODS` declara os oito campos de operação da spec (`get`, `put`, `post`,
`delete`, `options`, `head`, `patch`, `trace`) e `_operations` ignora o resto. A lista é
deliberadamente mais larga que a regex `_ROUTE_METHODS` que lê o Markdown do API Contract:
aqui, um método a menos faria uma operação real sumir do gate em silêncio, que é pior que uma
entrada a mais numa lista fechada pela spec. Coberto por
`test_campo_de_nivel_de_caminho_nao_e_lido_como_metodo`. A mensagem do ramo de fallback de
`snapshot_errors` também mudou: com o filtro, uma divergência dentro de `paths` mas fora de
qualquer operação passa a cair nesse ramo, e o texto antigo ("divergente **fora de** `paths`")
se contradiria ao nomear a chave `paths`. Agora ele diz "divergente sem diferença de operação",
verdadeiro nos dois casos.

## 7. Divergências de baseline reveladas (NÃO corrigidas)

O gate de paridade, ao rodar pela primeira vez contra a aplicação e o API Contract reais,
revelou exatamente 5 divergências. Cada uma está registrada como achado, com caminho e
método, na constante `BASELINE` de `tests/api/test_openapi_contract.py`. Nenhuma foi
corrigida nesta feature — a decisão sobre qual lado está errado (código exposto sem
documentação, ou documentação sem implementação) é humana e permanece pendente:

| Rota | Achado | Decisão |
| --- | --- | --- |
| `GET /v1/projects` | Exposta em `services/api/src/croquito_api/main.py:3232`, nunca documentada em `API_CONTRACT.md` | Pendente |
| `POST /v1/jobs/{job_id}/review/dimensions` | Exposta em `services/api/src/croquito_api/main.py:2965`, nunca documentada | Pendente |
| `POST /v1/jobs/{job_id}/review/notes` | Exposta em `services/api/src/croquito_api/main.py:3105`, nunca documentada | Pendente |
| `DELETE /v1/jobs/{job_id}` | Documentada em `API_CONTRACT.md:89`, inexistente na aplicação | Pendente |
| `POST /v1/jobs/{job_id}/regions/{region_id}/reanalyze` | Documentada em `API_CONTRACT.md:498`, inexistente na aplicação | Pendente |

`test_excecao_de_baseline_que_deixou_de_existir_reprova` garante que essa lista não vire
dívida silenciosa: se qualquer uma das 5 deixar de ser uma divergência real (por ter sido
corrigida em trabalho próprio, ou por outra mudança futura), o teste passa a reprovar até a
chave correspondente ser removida de `BASELINE`.

### Limitação residual declarada

A exceção é casada por **rota**, não por tipo de divergência. Se uma das 5 for corrigida de um
lado e quebrada do outro na mesma rota — por exemplo, `GET /v1/projects` passar a ser
documentada e, no mesmo intervalo, deixar de ser exposta —, a divergência muda de natureza mas
continua mascarada, e `test_excecao_de_baseline_que_deixou_de_existir_reprova` não acusa,
porque ainda existe divergência real para aquela chave.

Casar por mensagem completa em vez de por rota fecharia essa fresta. Não foi feito aqui porque
exigiria a lista carregar as mensagens de erro literais, trocando legibilidade da constante por
um risco cujo gatilho é estreito: alguém corrigir e quebrar a mesma rota nos dois sentidos sem
tocar em `BASELINE`. Fica registrado para não se perder, e o fechamento natural é quando cada
uma das 5 for decidida e removida da lista.
