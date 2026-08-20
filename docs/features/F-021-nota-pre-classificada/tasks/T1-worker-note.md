# T1 — Worker: `kind="note"` completo vira leitura com sugestão de anotação

Task Contract no formato do [template global](../../../engineering-os/templates/task.md),
derivado do [plano válido](../plan.md). Autossuficiente: assuma o Core (pinado em
`docs/engineering-os/`), este contrato e o repositório — nada mais.

## Identity

```text
feature_id: F-021
task_id: T1
parent_plan: docs/features/F-021-nota-pre-classificada/plan.md
depends_on: []
```

## Goal

O provider já classifica leitura como `note` (`measurement-extraction@1.1.1`), mas o
worker descarta esse sinal. Depois desta task, leitura `note` COMPLETA (com
`normalized_value` e `target_hint`) entra no pacote de revisão com
`annotation_suggested=true` e `kind` neutro; leitura `note` SEM valor é descartada com
nota própria; `count`/`unknown` seguem descartados exatamente como hoje.

## Baseline

`make check` e `make test` verdes na árvore atual (há mudanças não commitadas em
`apps/web/src/CroquiApp.tsx` — não são suas, não as toque, não as reverta).

## Scope

Em `services/worker/src/croquito_worker/review.py`:

- `DimensionReading` (linhas 116-145) ganha `annotation_suggested: bool = False`.
  Default `False` mantém pacotes persistidos antigos válidos no
  `ReviewPacket.model_validate(record.packet_json)` da API — NÃO mude nada além do
  campo novo.

Em `services/worker/src/croquito_worker/provider_review.py`:

- No laço de leituras (em torno das linhas 561-630): hoje `_measurement_kind()`
  (141-145) levanta `ProviderContractError` para `note` e o except (568-571) grava
  `READING_{n}_UNSUPPORTED_UNIT_OR_KIND`. Passe a tratar `note` ANTES da conversão:
  - `observation.kind == "note"` e leitura completa (já passou pelo filtro de
    `normalized_value`/`target_hint` da linha 562): monta o `DimensionReading` com
    `kind=MeasurementKind.LENGTH` (neutro declarado — comentário no código dizendo
    que o eixo é irrelevante para anotação e que LENGTH nunca vira restrição sem
    eixo no traçado) e `annotation_suggested=True`.
  - `count`/`unknown`: comportamento IDÊNTICO ao atual (mesma nota).
- ATENÇÃO ao par (braço duplo): `_readings_agree` (298-311) e a divergência de kind
  (577-584). Âncora `note` + contraparte concreta (ex.: `height`): a âncora manda
  (comportamento atual de kind divergente), MAS a divergência continua registrada
  como hoje (`READING_{n}_KIND_DIVERGENCE`). Não invente regra nova de consenso.
- Leitura `note` sem `normalized_value`: HOJE cai em `READING_{n}_INCOMPLETE` na
  linha 562 antes de o kind ser lido. Mantenha o descarte, mas com nota própria
  `READING_{n}_NOTE_WITHOUT_VALUE` quando `observation.kind == "note"` — o dado de
  quantos recados sem número o modelo emitiu é insumo da rodada seguinte. Não mude o
  caso geral de INCOMPLETE.

Em `tests/worker/test_providers.py`:

- Teste novo: extração com `kind="note"` completa → leitura no pacote com
  `annotation_suggested is True` e `kind is MeasurementKind.LENGTH`.
- Teste novo: `note` sem valor → descartada com `READING_{n}_NOTE_WITHOUT_VALUE`.
- Teste novo: `count` → `READING_{n}_UNSUPPORTED_UNIT_OR_KIND` (hoje só há cobertura
  indireta disso em test_transcription.py; a cobertura do caminho principal nasce
  aqui).
- Teste novo: leitura normal (width/height) → `annotation_suggested is False`.
- Use `FixtureProviderAdapter`/`build_provider_review_snapshot` como os testes
  vizinhos (call-sites listados no plano; ex.: linhas 233, 280, 381).

Em `docs/ai/PROMPT_CONTRACTS.md` (seção do `measurement-extraction@1.1.1`, linhas
77-107): documente o destino real de cada kind fora do enum — `note` completo entra
com sugestão, `note` sem valor descartado com nota própria, `count`/`unknown`
descartados. O contrato do prompt NÃO muda (sem bump de versão).

## Out of scope

- `transcription.py` (o caminho paralelo tem `_map_kind` próprio; fica como está).
- Web (T2), prompts, schema gerado (`ReviewPacket` não está no manifesto de
  contratos — verificado; se você concluir o contrário, PARE e reporte).
- Mudar `MeasurementKind` no core.

## Acceptance criteria

1. `make check` e `make test` verdes.
2. Os quatro testes novos passam e nomeiam o comportamento.
3. Pacote persistido antigo (sem o campo) continua validando — coberto por teste ou
   por demonstração no relatório.
4. `make provider-contract-demo` continua verde.

## Validation

```bash
make check
make test
uv run pytest tests/worker/test_providers.py -x -q
make provider-contract-demo
```

## Required capabilities

READ, WRITE, VALIDATE. Sem COMMIT: deixe o diff na árvore.

## Report

`BUILD REPORT` completo do contrato do Builder (docs/engineering-os/agents/builder.md),
gravado em docs/features/F-021-nota-pre-classificada/tasks/T1-build-report.md.
