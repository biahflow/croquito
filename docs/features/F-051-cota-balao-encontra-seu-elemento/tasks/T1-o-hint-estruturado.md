# F-051 · T1 — O hint estruturado sobrevive até a leitura

Feature: [F-051](../feature.md) · Plano: [plan.md](../plan.md) · Estado: **Pendente**  
`feature_id: F-051` · `task_id: T1` · `depends_on: —`

## Objetivo

`entity_label` chega estruturado do provider e hoje morre achatado numa string de exibição.
Depois desta tarefa, a leitura carrega o rótulo como campo próprio até o pacote de revisão e
até o comando de decisão — sem nenhum consumidor ainda (a T4 é o consumidor), e sem mudar o
comportamento de nenhum pacote existente.

## Escopo

- `services/worker/src/croquito_worker/review.py:180-218` — `DimensionReading` ganha
  `target_entity_label: str | None` (aditivo); a string legível `target_hint` continua
  existindo para exibição. `ReviewPacket.schema_version` (`review.py:222`):
  `Literal["1.0.0","1.1.0"]` → inclui `"1.2.0"`, novo default.
- Os **dois** achatadores param de descartar o rótulo:
  `services/worker/src/croquito_worker/provider_review.py:777-780` e
  `services/worker/src/croquito_worker/transcription.py:474`. `TargetHint` está em
  `providers.py:456-458` (`entity_label`, `feature`).
- `services/api/src/croquito_api/main.py:1073` e `:1106` — os comandos de decisão que já
  aceitam `target_hint` ganham o campo estruturado (aditivo), gravado em `:8948`/`:9199`;
  a regra de no-op de `:6685` acompanha.
- `apps/web/src/api.ts:59-82` — `ReviewReading` ganha o campo (tipo manual, aditivo).
- Trio de superfície: `tests/api/openapi.snapshot.json` e
  `docs/architecture/API_CONTRACT.md` (aditivo).
- Testes nos moldes existentes: `tests/worker/test_providers.py:841-904` (hint ausente e
  pacote legado) e `tests/worker/test_transcription.py:232-281` (achatamento campo a campo).

## Fora de escopo

- Consumir o campo (casamento, candidata) — é a T4.
- Mudar a regra de `transcription.py:431-439` que **descarta** leitura sem hint
  (`missing_target_hint`): regra própria daquele caminho, preservada.
- Renderizar o campo na tela — é a T6.
- Qualquer mudança em `scene.schema.json`/`make contracts` (o ReviewPacket está fora do
  manifesto; se o drift check acusar algo, a tarefa saiu do escopo).

## Critérios de aceite

1. Leitura extraída com `TargetHint("B", "fecho")` produz `target_entity_label == "B"` e
   `target_hint == "B: fecho"` nos **dois** caminhos de extração — teste novo em cada molde.
2. Pacote persistido com `schema_version` anterior valida sem erro e sem mudança de
   comportamento (molde `test_legacy_packet_with_target_hint_still_validates`,
   `test_providers.py:904`).
3. Decisão/retificação pode corrigir `target_entity_label` (ato registrado, nunca edição
   silenciosa), e decisão sem o campo não o altera — teste de API.
4. Snapshot de OpenAPI atualizado de forma aditiva; `API_CONTRACT.md` cita o campo.

## Validação

```text
baseline: make check && make test verdes na main (registrar o resultado real antes de mudar)
required: uv run pytest tests/worker/test_providers.py tests/worker/test_transcription.py tests/api -x
required: make check && make test
```

## Riscos conhecidos

- O `Literal` de `schema_version` recusa pacote novo em código velho — é o comportamento
  desejado (fail-closed), mas o teste do critério 2 protege a direção inversa.
- `transcription.py` trunca o hint em 120 (`[:474]`); o campo estruturado respeita os limites
  do `TargetHint` (1-120), não inventa outros.
