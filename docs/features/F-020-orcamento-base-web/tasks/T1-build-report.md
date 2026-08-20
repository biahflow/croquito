# BUILD REPORT — F-020 / T1 — Domínio: BDI no `Estimate` (schema v2)

```text
Status: BUILD_COMPLETE

Files changed:
  - packages/valuation/src/croquito_valuation/estimate.py
      ESTIMATE_SCHEMA_VERSION "1.0.0" -> "2.0.0"; EstimateLine ganha
      unit_price_with_bdi (obrigatório) e expected_total/validate_total passam a
      recomputar sobre ele; Estimate ganha bdi_percent e total_amount_without_bdi
      com os validators novos ESTIMATE_LINE_BDI_MISMATCH e
      ESTIMATE_TOTAL_WITHOUT_BDI_MISMATCH; build_worksite_estimate ganha o
      keyword obrigatório bdi_percent e monta unit_price_with_bdi/total/
      total_amount_without_bdi — escopo do contrato T1.

  - packages/contracts/contracts.manifest.json
      Entrada nova para croquito_valuation.estimate.Estimate no formato exato das
      seis existentes (id/title/schema/typescript), para make contracts publicar
      o schema — escopo do contrato T1.

  - packages/contracts/schemas/estimate.schema.json (novo, gerado)
  - packages/contracts/src/estimate.generated.ts (novo, gerado)
  - packages/contracts/src/index.ts
      Saída de `make contracts`; nenhum edit manual — proibido pelo contrato e
      pelo CLAUDE.md ("NUNCA edite .schema.json/.generated.ts manualmente").

  - services/worker/src/croquito_worker/valuation/cli.py
      `from decimal import Decimal` e import de SYNTHETIC_ESTIMATE_BDI_PERCENT;
      argumento `--bdi` (type=Decimal, obrigatório) no parser de `build-estimate`;
      run_build_estimate e _command_build_estimate repassam bdi_percent;
      run_estimate_demo passa o BDI fixo da fixture — escopo do contrato T1.

  - services/worker/src/croquito_worker/valuation/estimate_fixture.py
      Constante SYNTHETIC_ESTIMATE_BDI_PERCENT = Decimal("25.00"), BDI fixo e
      determinístico da demo, ao lado das outras constantes SYNTHETIC_ESTIMATE_*
      — escopo do contrato T1.

  - tests/valuation/test_estimate.py
      _BDI_PERCENT + _build(bdi_percent=...) com default 25.00; números
      atualizados nos dois testes de caminho feliz pré-existentes que hardcodiam
      total sem BDI (agora o total embute BDI, por decisão do ADR-0038); --bdi
      adicionado a _cli_args; 3 testes novos: ESTIMATE_LINE_BDI_MISMATCH,
      ESTIMATE_TOTAL_WITHOUT_BDI_MISMATCH, e o caso feliz que prova a ordem de
      truncamento (unit_price_with_bdi trunca ANTES de multiplicar pela
      quantidade) com unit_price="10.004" desenhado para que truncar-antes ≠
      truncar-só-no-fim — escopo do contrato T1.

  - tests/e2e/test_valuation_full_chain.py
      Import de SYNTHETIC_ESTIMATE_BDI_PERCENT; --bdi acrescentado às duas
      chamadas de `build-estimate` da cadeia (fixture estimate_chain e o teste de
      recusa por fonte ausente da cascata) — sem isso o argparse rejeitaria o
      argumento obrigatório ausente antes mesmo de chegar na recusa que o teste
      pretende exercitar — escopo do contrato T1.

  - tests/valuation/golden/estimate-demo.canonical.json
      Regenerado UMA vez pelo caminho oficial (run_estimate_demo +
      canonical_estimate de tests/valuation/test_canonical_golden.py, com
      json.dumps(sort_keys=True) para preservar a convenção de chaves ordenadas
      do arquivo original). Diff mostra só os campos novos
      (bdi_percent, unit_price_with_bdi por linha, total_amount_without_bdi) e a
      versão do schema — autorizado pelo contrato T1 ("muda NESTA task por
      decisão declarada no plano").

  - tests/valuation/test_canonical_golden.py
      DESVIO CONSCIENTE (ver seção abaixo): assertions hardcoded do golden do
      orçamento atualizadas para os novos valores com BDI, e duas asserções
      novas (bdi_percent, total_amount_without_bdi) no mesmo teste que já
      hardcodava total/total_amount — necessário para manter make test verde
      depois da regeneração do golden que o próprio contrato autoriza.

Validation executed:
  - uv run ruff check . -> All checks passed!
  - uv run ruff format --check . -> 386 files already formatted
  - uv run mypy packages/core/src packages/valuation/src services/api/src
    services/worker/src tests -> Success: no issues found in 187 source files
  - uv run python scripts/check_docs.py -> Documentação válida: 222 arquivos
    Markdown, paridade de lifecycle verificada.
  - uv run python -m croquito_core.schema_export --check-dir packages/contracts
    -> ok (sem drift, após `make contracts` regenerar e commitar os artefatos)
  - npm run contracts:check -> ok
  - npm run web:check (tsc -b && vite build) -> build ok
  - make infra-check (terraform fmt -check -recursive infra) -> ok
  - make check (comando completo) -> todos os passos acima em sequência, verde
  - make test (uv run pytest + npm run web:test) -> 1643 passed, 13 skipped,
    47 warnings (126.56s) + 32 arquivos / 581 testes web passed
  - uv run pytest tests/valuation/test_estimate.py
    tests/valuation/test_canonical_golden.py -x -q -> 45 passed
  - uv run pytest tests/e2e/test_valuation_full_chain.py -q -> 9 passed
  - make valuation-estimate-demo -> exit 0, determinístico em duas execuções
    seguidas: total_amount "71516.83", total_amount_without_bdi implícito
    "57221.26", cascade ["sco","emop","composition"], unpriced
    ["ti_d16efef092c62fc9"] idênticos nas duas rodadas
  - grep -r "bdi" packages/valuation/src/croquito_valuation/calc.py
    packages/valuation/src/croquito_valuation/workbook_writer.py -> vazio
    (critério de aceite 4 confirmado: BDI não alcança a medição)

Validation skipped: none

Unavailable capabilities: none

Assumptions:
  - `bdi_percent` foi posicionado como terceiro parâmetro keyword de
    build_worksite_estimate (depois de worksite_name, antes de address), já que
    o contrato só exige que seja "keyword obrigatório" sem fixar posição;
    Python aceita argumento keyword-only sem default antes de outros com
    default, então a ordem escolhida agrupa os obrigatórios primeiro.
  - Campos novos (bdi_percent, total_amount_without_bdi) foram posicionados no
    modelo Estimate perto dos campos correlatos (bdi_percent com os dados da
    obra/cascata; total_amount_without_bdi logo antes de total_amount) — o
    contrato não fixa ordem de campo, só que sejam obrigatórios.
  - O valor de teste "10.004" para unit_price no teste que prova a ordem de
    truncamento é sintético e não corresponde a um preço real de catálogo (que
    normalmente tem só 2 casas); é permitido porque ExactDecimal não restringe
    escala e o objetivo do teste é isolar a ordem das operações de truncamento,
    não simular um catálogo real.
  - `--bdi` no CLI usa `type=Decimal` diretamente (não `type=str` com conversão
    manual em Decimal() no handler); argparse chama Decimal(string) do argv, que
    é equivalente a "string decimal" pedido pelo contrato e nunca passa por
    float.

Remaining risks:
  - `decimal.InvalidOperation` (não subclasse de ValueError) não é capturado
    pelo tratamento de erro padrão do argparse para `type=`; um `--bdi` com
    texto não numérico produziria um traceback bruto em vez de uma mensagem de
    uso amigável. Não há teste cobrindo esse caso e o contrato não pediu; fica
    como observação para quem tocar essa CLI depois (T2 ou além).
  - T2 (escritor/auditor de planilha) ainda precisa imprimir a diferença
    total_amount - total_amount_without_bdi como o valor de BDI da planilha
    (ADR-0038 decisão 4) e as duas colunas novas (FONTE, VALOR UNIT. C/ BDI) —
    nada disso foi tocado aqui, por estar fora de escopo desta task.

Human decisions required: none — nenhum gate de produção, migração destrutiva,
chamada paga em massa, envio a serviço externo ou mudança de retenção/
fornecedor foi exercido nesta task.
```

## Desvios conscientes do spec

1. **`tests/valuation/test_canonical_golden.py` foi editado**, e o contrato T1 não o
   lista explicitamente na seção "Em testes" (que cita apenas
   `test_estimate.py`, o golden em si, e `test_valuation_full_chain.py`). A edição foi
   necessária porque `test_the_estimate_golden_carries_the_three_price_origins_and_the_unpriced_item`
   hardcodava os valores antigos do MESMO golden que o contrato explicitamente autoriza
   a mudar ("O golden ... muda NESTA task por decisão declarada no plano"); sem
   atualizar essas asserções, `make test` reprovaria por uma consequência direta e
   inevitável da mudança de schema autorizada, não por um defeito. Mantive o escopo da
   edição mínimo: só os dois valores que mudaram (total da linha de composição e total
   do orçamento) mais duas asserções novas (bdi_percent, total_amount_without_bdi) no
   mesmo teste, sem tocar nada além.

2. Nenhum outro golden mudou (`valuation-demo.canonical.json`,
   `valuation-demo-m4.canonical.json` intactos) — confirmado por `make test` verde e por
   `git status` não listar esses arquivos como modificados.

## Oportunidades vistas e NÃO implementadas (fora de escopo)

- Colunas `FONTE` e `VALOR UNIT. C/ BDI` no `.xlsx` do orçamento-base e o cálculo do
  BDI impresso (`total_amount - total_amount_without_bdi`) — pertencem a T2
  (`template.py`, `workbook_writer.py`, `canonical.py`), explicitamente fora de escopo
  deste contrato.
- Mensagem de erro amigável para `--bdi` com valor não decimal no CLI (ver "Remaining
  risks" acima) — não pedida pelo contrato, não fiz.
- `_estimate_payload` (resumo impresso pelo CLI de `build-estimate`/`estimate-demo`) não
  ganhou `bdi_percent`/`total_amount_without_bdi` no JSON de stdout — o contrato só pediu
  os campos no modelo e no artefato publicado, não no resumo de console; não ampliei essa
  superfície sem pedido explícito.
