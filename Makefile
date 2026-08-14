UV_CACHE_DIR ?= /private/tmp/uv-cache-croquito
XDG_CACHE_HOME ?= /private/tmp/croquito-xdg-cache
MPLCONFIGDIR ?= /private/tmp/croquito-matplotlib-cache
export UV_CACHE_DIR
export XDG_CACHE_HOME
export MPLCONFIGDIR

.PHONY: setup dev dev-api dev-web dev-medicao dev-worker dev-worker-fixtures dev-services down-services db-init check test demo provider-contract-demo vision-eval solver-eval extraction-eval valuation-demo valuation-eval valuation-extraction-eval valuation-parity valuation-compare smoke-local contracts infra-check

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

db-init:
	set -a; test ! -f .env.local || . ./.env.local; set +a; uv run python -m croquito_api.bootstrap

dev-api:
	set -a; test ! -f .env.local || . ./.env.local; set +a; uv run uvicorn croquito_api.main:app --reload --port 8000

dev-web:
	npm run web:dev

# UI local de homologação da medição (porta 5174). Ela fala com o servidor local
# `croquito-valuation serve` (porta 8801), não com a API do croqui, por isso fica
# fora do `make dev`.
dev-medicao:
	npm run medicao:dev

dev-worker:
	set -a; test ! -f .env.local || . ./.env.local; set +a; uv run croquito-demo local-worker-once

# Mesmo consumidor, com a suíte SINTÉTICA de providers injetada pelo comando: é o caminho
# da fatia 1 do agente de conversa (`answer_chat_turn`) e nenhuma chamada externa é feita.
# A injeção vale para a mensagem consumida, qualquer que seja o comando dela — um
# `process_upload` também será servido por fixture.
dev-worker-fixtures:
	set -a; test ! -f .env.local || . ./.env.local; set +a; uv run croquito-demo local-worker-once --fixtures

contracts:
	uv run python -m croquito_core.schema_export --output packages/contracts/scene.schema.json
	npm run contracts:generate

check:
	uv run ruff check .
	uv run ruff format --check .
	uv run mypy packages/core/src packages/valuation/src services/api/src services/worker/src tests
	uv run python scripts/check_docs.py
	uv run python -m croquito_core.schema_export --check packages/contracts/scene.schema.json
	npm run contracts:check
	npm run web:check
	npm run medicao:check
	$(MAKE) infra-check

test:
	uv run pytest
	npm run web:test
	npm run medicao:test

demo:
	uv run croquito-demo synthetic --output output/demo

provider-contract-demo:
	uv run croquito-demo provider-contract-demo --output output/provider-contract-demo

vision-eval:
	uv run croquito-demo vision-eval --output output/vision-eval

solver-eval:
	uv run croquito-demo solver-eval --output output/solver-eval

valuation-demo:
	uv run croquito-valuation demo --output output/valuation-demo

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

# Exige os serviços locais de pé (make dev-services, make db-init) e a API em execução.
smoke-local:
	set -a; test ! -f .env.local || . ./.env.local; set +a; uv run python scripts/smoke_local.py

infra-check:
	terraform fmt -check -recursive infra
