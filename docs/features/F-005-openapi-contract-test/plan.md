# FEATURE EXECUTION PLAN — F-005

feature_id: F-005
goal: Criar o gate de contrato da API exigido pela Testing Strategy e pelo API Contract e
hoje inexistente — um snapshot versionado do documento OpenAPI da aplicação e um teste de
paridade entre as rotas `/v1` expostas e as documentadas em
`docs/architecture/API_CONTRACT.md` — sem alterar rota, modelo ou comportamento da API.
assumptions: O [Feature Contract](feature.md) é autoritativo; `docs/architecture/
API_CONTRACT.md` e `docs/engineering/TESTING_STRATEGY.md` permanecem canônicos; as 26 rotas
`/v1` hoje expostas por `services/api/src/croquito_api/main.py` são a superfície observada,
não alterada; `GET /healthz` fica fora do gate por ter `include_in_schema=False` e nunca
aparecer no documento OpenAPI.
risks: Divergência preexistente entre app e contrato poderia ser corrigida em silêncio
dentro desta feature, misturando a criação do gate com a limpeza que ele revela — mitigado
congelando as 5 divergências encontradas como `BASELINE`, com decisão humana pendente por
item. Acoplamento do teste de paridade à formatação editorial do Markdown tornaria o gate
frágil a reescritas legítimas — mitigado extraindo rota de spans de código inline
(crase simples) em vez de ancorar em heading. Regenerar o snapshot só para fazer o teste
passar anularia o propósito do gate — mitigado documentando `make openapi-snapshot` como
ato deliberado, sem modo `--check` concorrente no exportador.

## Tasks

### F005-T01

- role: builder
- goal: Estabelecer a baseline de execução e criar o exportador do snapshot OpenAPI.
- scope: Ler `AGENTS.md`, `CLAUDE.md`, `services/api/AGENTS.md` e este contrato. Registrar
  baseline (`uv run pytest --co`, `make check`, `git status --short`, contagem de rotas
  `/v1`). Criar `services/api/src/croquito_api/openapi_export.py` com `snapshot_text()`
  construindo `ApiSettings` explícito e fixo (nunca `from_environment()`) e
  `Database("sqlite+pysqlite:///:memory:")`, e CLI `--output` sem modo `--check`.
- out_of_scope: Alterar `services/api/src/croquito_api/main.py`, qualquer rota ou modelo da
  API, `croquito_core.schema_export`, `packages/contracts`.
- expected_areas: `services/api/src/croquito_api/openapi_export.py`
- acceptance_criteria: `snapshot_text()` é determinístico (mesmas settings, mesma saída) e
  não lê variável de ambiente; a CLI escreve o arquivo pedido; o comentário no código
  explica por que as settings são fixas (os dois ramos condicionais de `create_app()` —
  backend de fila e header de checksum de upload — não alteram o documento OpenAPI, mas
  ambos constroem cliente de nuvem diferente).
- depends_on: []
- validation: `uv run python -m croquito_api.openapi_export --output /tmp/openapi-check.json`
  roda sem serviço externo de pé.
- risk: Settings fixo que ainda assim vaze dado de ambiente por engano.
- relative_effort: S

### F005-T02

- role: builder
- goal: Alvo `make openapi-snapshot` e primeira geração do snapshot versionado.
- scope: Acrescentar alvo `openapi-snapshot` ao `Makefile`, separado de `contracts`, e ao
  `.PHONY`. Gerar `tests/api/openapi.snapshot.json` executando o alvo — nunca escrito à mão.
  Não acrescentar nada ao alvo `check`.
- out_of_scope: Qualquer entrada nova em `make check`; modo `--check` no exportador.
- expected_areas: `Makefile`, `tests/api/openapi.snapshot.json`
- acceptance_criteria: `make openapi-snapshot` seguido de `git diff --stat` não produz diff
  depois da primeira geração; `check` continua sem referenciar o snapshot.
- depends_on: [F005-T01]
- validation: `make openapi-snapshot && git diff --stat`
- risk: Ordenação não determinística do documento gerado produzindo diff espúrio a cada
  execução — mitigado por `sort_keys=True` no `json.dumps`.
- relative_effort: XS

### F005-T03

- role: builder
- goal: Teste de paridade `/v1` × API Contract e teste de snapshot, com `BASELINE` congelada.
- scope: Criar `tests/api/test_openapi_contract.py` com `documented_routes`,
  `exposed_routes`, `parity_errors` (assinaturas do contrato) e a constante `BASELINE` com
  as 5 divergências preexistentes, cada uma com motivo e localização. Os 8 testes do
  contrato, cobrindo as duas direções de cada um dos dois gates (snapshot e paridade) mais
  a regra de seção pendente e a checagem de obsolescência do próprio `BASELINE`.
- out_of_scope: Corrigir qualquer uma das 5 divergências; marcador pytest novo; dependência
  nova; alterar `scripts/check_docs.py` ou rotas de medição.
- expected_areas: `tests/api/test_openapi_contract.py`
- acceptance_criteria: Os 8 testes existem e passam; toda mensagem de falha nomeia método e
  caminho; `documented_routes` remove blocos de código cercados por crase tripla antes de
  extrair as rotas, para não capturar exemplo de requisição; a rota
  `/v1/valuation-rounds` inteira aparece `PENDENTE` e nenhuma está exposta hoje.
- depends_on: [F005-T02]
- validation: `uv run pytest tests/api/test_openapi_contract.py -v`
- risk: Regex de rota inline capturando texto de prosa que não é rota real, ou perdendo
  rota documentada em formato não previsto.
- relative_effort: M

### F005-T04

- role: builder
- goal: Registrar o gate nos documentos que o exigiam e provar que ele morde.
- scope: Atualizar a seção "Contrato" de `docs/engineering/TESTING_STRATEGY.md` e a seção
  "Compatibilidade" de `docs/architecture/API_CONTRACT.md` (só essas duas seções) citando o
  teste e o comando de atualização; acrescentar entrada de roteamento "Alterar a superfície
  da API" em `docs/INDEX.md`, espelhando "Alterar o schema do banco". Executar as três
  provas do gate (rota de brinquedo em `main.py`, remoção de linha do API Contract, byte
  alterado no snapshot) e revertê-las. Criar `evidence.md`, atualizar `feature.md` para
  `READY_FOR_HUMAN_REVIEW` e a linha de F-005 em `docs/product/ROADMAP.md`.
- out_of_scope: Qualquer alteração de rota do API Contract além de acrescentar a nota de
  compatibilidade; tocar na linha de F-004 do roadmap; commit.
- expected_areas: `docs/engineering/TESTING_STRATEGY.md`, `docs/architecture/
  API_CONTRACT.md`, `docs/INDEX.md`, `docs/features/F-005-openapi-contract-test/`,
  `docs/product/ROADMAP.md`
- acceptance_criteria: `make check` e `make test` passam ao fim; `git status --short` não
  mostra `main.py`; as três provas do gate produzem falha nomeando método e caminho e são
  revertidas antes de encerrar; `evidence.md` registra a autorização humana, a baseline e as
  5 divergências como pendentes de decisão.
- depends_on: [F005-T03]
- validation: `make check`; `make test`; as três provas manuais descritas no spec, cada uma
  revertida.
- risk: Prova do gate não revertida corretamente deixando o worktree sujo.
- relative_effort: S

## critical_path

F005-T01 (S) → F005-T02 (XS) → F005-T03 (M) → F005-T04 (S).

## integration_strategy

Um único diff cobre exportador, alvo `make`, snapshot gerado, teste de paridade e
atualização documental — não há Task Contracts separados; o pacote de evidências é
`evidence.md`.

## human_gates

Aprovação deste plano e do contrato correspondente, em 2026-08-17, incluindo as duas
decisões de desenho registradas em `feature.md` e `evidence.md`: congelar as 5 divergências
preexistentes como exceção declarada de baseline, e alojar o snapshot em `tests/api/` com
alvo `make` próprio. Decisão sobre cada divergência de `BASELINE` (o que é bug de
documentação e o que é rota que não deveria existir) permanece humana e pendente — não é
escopo desta feature.
