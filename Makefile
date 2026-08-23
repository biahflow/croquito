UV_CACHE_DIR ?= /private/tmp/uv-cache-croquito
XDG_CACHE_HOME ?= /private/tmp/croquito-xdg-cache
MPLCONFIGDIR ?= /private/tmp/croquito-matplotlib-cache
export UV_CACHE_DIR
export XDG_CACHE_HOME
export MPLCONFIGDIR

.PHONY: docs setup dev dev-api dev-web dev-worker dev-worker-fixtures dev-services down-services db-init db-revision check test demo provider-contract-demo vision-eval ocr-eval solver-eval association-eval association-calibration transcription-eval field-photo-classification-eval extraction-eval extraction-eval-degrau valuation-demo valuation-estimate-demo valuation-eval valuation-extraction-eval valuation-parity valuation-compare smoke-local smoke-hml contracts openapi-snapshot infra-check

setup:
	uv sync --all-groups
	npm install
	$(MAKE) contracts

dev:
	$(MAKE) -j2 dev-api dev-web

dev-services:
	docker compose -f docker-compose.local.yml up -d

down-services:
	docker compose -f docker-compose.local.yml down

# Runner de migrations revisadas (ADR-0029): aplica as revisões que faltam, adota banco
# anterior ao runner por carimbo e recusa banco defasado. Mesmo comando que o job de banco
# da esteira executa.
db-init:
	set -a; test ! -f .env.local || . ./.env.local; set +a; uv run python -m croquito_api.bootstrap

# Gera revisão nova por autogenerate comparando `Base.metadata` com o banco apontado por
# CROQUITO_DATABASE_URL. Este é o ÚNICO uso do `alembic.ini` da raiz — o runtime não o lê.
# O arquivo gerado precisa ser revisto à mão: autogenerate erra em detalhe de índice e
# tipo, e é a revisão humana que o gate de drift do CI cobra depois.
db-revision:
	@test -n "$(MESSAGE)" || { echo "uso: make db-revision MESSAGE=<descricao curta>"; exit 2; }
	set -a; test ! -f .env.local || . ./.env.local; set +a; uv run alembic revision --autogenerate -m "$(MESSAGE)"
	uv run ruff check --fix services/api/src/croquito_api/migrations/versions
	uv run ruff format services/api/src/croquito_api/migrations/versions

dev-api:
	set -a; test ! -f .env.local || . ./.env.local; set +a; uv run uvicorn croquito_api.main:app --reload --port 8000

dev-web:
	npm run web:dev

dev-worker:
	set -a; test ! -f .env.local || . ./.env.local; set +a; uv run croquito-demo local-worker-once

# Mesmo consumidor, com a suíte SINTÉTICA de providers injetada pelo comando: é o caminho
# da fatia 1 do agente de conversa (`answer_chat_turn`) e nenhuma chamada externa é feita.
# A injeção vale para a mensagem consumida, qualquer que seja o comando dela — um
# `process_upload` também será servido por fixture.
dev-worker-fixtures:
	set -a; test ! -f .env.local || . ./.env.local; set +a; uv run croquito-demo local-worker-once --fixtures

contracts:
	uv run python -m croquito_core.schema_export --output-dir packages/contracts
	npm run contracts:generate

# Renderiza os documentos que `docs/portal.manifest.json` lista num HTML único e navegável
# em `output/` (temporário, ignorado pelo Git). A fonte de verdade continua sendo o Markdown
# versionado em `docs/`; esta página é derivada e nunca se edita à mão. Rode depois de mexer
# em documento canônico que esteja no manifesto.
docs:
	uv run python scripts/build_docs_portal.py

# Regenera o snapshot versionado do OpenAPI (tests/api/openapi.snapshot.json) a partir da
# própria aplicação, com settings fixos e sintéticos (services/api/src/croquito_api/
# openapi_export.py). É um ato deliberado: rode só quando a mudança na superfície `/v1` for
# intencional, e revise o diff. `tests/api/test_openapi_contract.py` é o gate que cobra isso.
openapi-snapshot:
	uv run python -m croquito_api.openapi_export --output tests/api/openapi.snapshot.json

check:
	uv run ruff check .
	uv run ruff format --check .
	uv run mypy packages/core/src packages/valuation/src services/api/src services/worker/src tests
	uv run python scripts/check_docs.py
	uv run python -m croquito_core.schema_export --check-dir packages/contracts
	npm run contracts:check
	npm run web:check
	npm run field:check
	$(MAKE) infra-check

test:
	uv run pytest
	npm run web:test
	npm run field:test

demo:
	uv run croquito-demo synthetic --output output/demo

provider-contract-demo:
	uv run croquito-demo provider-contract-demo --output output/provider-contract-demo

vision-eval:
	uv run croquito-demo vision-eval --output output/vision-eval

ocr-eval:
	uv run croquito-demo ocr-eval --output output/ocr-eval

solver-eval:
	uv run croquito-demo solver-eval --output output/solver-eval

association-eval:
	uv run croquito-demo association-eval --output output/association-eval

# Diagnóstico LOCAL, NUNCA CI: replay das revisões reais (CROQUITO_DATABASE_URL) contra o
# shadow de confiança gravado (F-029 T1/T3). Nunca escreve nada de volta no banco e nunca
# escolhe o corte — só instrui a escolha humana do threshold operacional.
association-calibration:
	set -a; test ! -f .env.local || . ./.env.local; set +a; uv run croquito-demo calibration-report --output output/association-calibration

# Eval comparativa dos braços de transcrição de voz (F-032 T13). Offline e determinística
# como as demais: corpus sintético, adapters gravados, nenhuma chave e nenhuma rede — o que
# ela prova é que as métricas (fidelidade de medida falada, WER/CER, container) discriminam.
# A RODADA PAGA que promove primário/reserva é ato humano separado, com clipes reais gravados
# fora do repositório e aprovação de custo:
#   uv run croquito-demo transcription-eval --output output/transcription-eval \
#     --corpus <caminho>/corpus.json --live
transcription-eval:
	uv run croquito-demo transcription-eval --output output/transcription-eval

# Offline por padrão. A rodada real exige `LIVE=1 CORPUS=<fora-do-git>/corpus.json`,
# `CROQUITO_OPENAI_ARM_ENABLED=false`, teto 5.00 e reserva 0.75; o runner chama cada uma
# das seis fotos uma única vez, sem retry e sem fallback.
field-photo-classification-eval:
	set -a; test ! -f .env.local || . ./.env.local; set +a; uv run croquito-demo field-photo-classification-eval \
	  --output output/field-photo-classification-eval $(if $(LIVE),--live --corpus "$(CORPUS)",)

valuation-demo:
	uv run croquito-valuation demo --output output/valuation-demo

# Cadeia de PRÉ-licitação (ADR-0027): catálogo SCO sintético + catálogo EMOP sintético
# (.DBF, pelo importador real) + composição manual formam a cascata do orçamento-base.
# Offline e determinística como as demais demos; nenhuma chamada paga.
valuation-estimate-demo:
	uv run croquito-valuation estimate-demo --output output/valuation-estimate-demo

valuation-eval:
	uv run croquito-valuation takeoff-eval --output output/valuation-eval

# Modo offline do gate da extração paga: braço fixture embutido, nada sai da máquina.
# A rodada paga é local e explícita (--arm NOME=PROVIDER:MODELO), com teto de gasto.
valuation-extraction-eval:
	uv run croquito-valuation extraction-eval --output output/valuation-extraction-eval

# Diagnóstico local, nunca CI: confere fórmula contra valor em cache de uma pasta externa.
# O arquivo analisado fica fora do repositório; só o relatório vai para output/.
valuation-parity:
	@test -n "$(PREVIOUS)" || { echo "uso: make valuation-parity PREVIOUS=<caminho.xlsx>"; exit 2; }
	uv run croquito-valuation parity --previous "$(PREVIOUS)" --output output/valuation-parity

# Diagnóstico local, nunca CI: compara o boletim gerado (JSON) com o BM real do cliente,
# centavo a centavo. O arquivo analisado fica fora do repositório; só o relatório vai
# para output/.
valuation-compare:
	@test -n "$(VALUATION)" || { echo "uso: make valuation-compare VALUATION=<valuation.json> WORKSITE=<chave> REFERENCE=<BM.xlsx> SHEET=<aba>"; exit 2; }
	@test -n "$(WORKSITE)" || { echo "uso: make valuation-compare VALUATION=<valuation.json> WORKSITE=<chave> REFERENCE=<BM.xlsx> SHEET=<aba>"; exit 2; }
	@test -n "$(REFERENCE)" || { echo "uso: make valuation-compare VALUATION=<valuation.json> WORKSITE=<chave> REFERENCE=<BM.xlsx> SHEET=<aba>"; exit 2; }
	@test -n "$(SHEET)" || { echo "uso: make valuation-compare VALUATION=<valuation.json> WORKSITE=<chave> REFERENCE=<BM.xlsx> SHEET=<aba>"; exit 2; }
	uv run croquito-valuation compare-bulletin --valuation "$(VALUATION)" --worksite "$(WORKSITE)" \
	  --reference "$(REFERENCE)" --sheet "$(SHEET)" --output output/valuation-compare

# Chama providers pagos e envia a página para fora. Exige budget explícito e o digest do
# documento em CROQUITO_AI_EXTRACTION_ALLOWED_DIGESTS; sem isso recusa antes de sair.
extraction-eval:
	set -a; test ! -f .env.local || . ./.env.local; set +a; uv run croquito-demo extraction-eval \
	  --image $(IMAGE) --manifest $(MANIFEST) --output output/extraction-eval \
	  --arm opus=bedrock:anthropic.claude-opus-5 \
	  --arm sonnet=bedrock:anthropic.claude-sonnet-5

# Gate do degrau (defeito real da primeira revisão do Guaxindiba V3, 2026-08-19): o Opus
# devolveu um muro em recuo como duas `line` retas, e a corroboração de tinta sozinha não
# pegou — cada trecho, sozinho, adere à tinta tanto quanto o muro fiel. Gera a fixture
# sintética do muro-degrau e roda a eval com o gabarito de fidelidade
# (`--step-gabarito`), que reprova geometria achatada mesmo com corroboração alta. Chama
# providers pagos: exige budget e o digest do documento em
# CROQUITO_AI_EXTRACTION_ALLOWED_DIGESTS, como o `extraction-eval` acima.
extraction-eval-degrau:
	uv run croquito-demo degrau-fixture --output output/extraction-eval-degrau
	set -a; test ! -f .env.local || . ./.env.local; set +a; uv run croquito-demo extraction-eval \
	  --image output/extraction-eval-degrau/degrau.png \
	  --manifest output/extraction-eval-degrau/manifest.json \
	  --output output/extraction-eval-degrau/eval \
	  --arm opus=anthropic:claude-opus-5 \
	  --step-gabarito output/extraction-eval-degrau/step-gabarito.json

# Exige os serviços locais de pé (make dev-services, make db-init) e a API em execução.
smoke-local:
	set -a; test ! -f .env.local || . ./.env.local; set +a; uv run python scripts/smoke_local.py

# Fumaça da borda pública de homologação: só HTTP, sem credencial. BASE_URL sobrescreve o
# host padrão (útil para apontar direto ao Cloud Run e tirar a CDN da equação).
smoke-hml:
	uv run python scripts/smoke_hml.py $(if $(BASE_URL),--base-url $(BASE_URL),)

infra-check:
	terraform fmt -check -recursive infra
