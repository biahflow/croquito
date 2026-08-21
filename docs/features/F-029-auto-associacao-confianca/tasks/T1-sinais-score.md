# F-029 / T1 — Sinais tipados e duas confianças no worker

- Feature: [F-029](../feature.md) · Plano: [plan.md](../plan.md)
- Papel: builder · Esforço relativo: M · Depende de: nada

## Objetivo

Cada leitura e cada candidato de associação passam a carregar confianças
determinísticas 0–1 — `reading_confidence` ("li certo?") e
`association_confidence` ("sei onde encaixa?") — compostas de sinais tipados,
mais uma função pura de shadow que responde "o que seria auto-decidido em
cada threshold". Nada decide, nada persiste, nada muda de comportamento.

## Fontes a ler antes de editar

- `AGENTS.md` (raiz) e `services/worker/AGENTS.md`.
- `services/worker/src/croquito_worker/association.py` — candidato atual:
  `AssociationCandidate` (linhas 31-40: `pixel_distance`, `proximity_score`,
  `visual_quality_score`), ranking por `(pixel_distance,
  -visual_quality_score, proposal_id)` (152-159), `AssociationConfig`
  (64-65), `safety_notes` (168-172).
- `services/worker/src/croquito_worker/review.py` — `DimensionReading`
  (116-154), `ocr_corroborated: bool | None` (136), `EvidenceRegion` (54-59,
  só `bbox`).
- `services/worker/src/croquito_worker/dimension_closure.py` —
  `suggest_chains` (185-233), `verify_chain` (148-182), `DimensionChain.closes`
  (75-77).
- `services/worker/src/croquito_worker/vision.py` — `PixelLine.start/end`
  (70-74) para direção do segmento; `VisionProposal.quality_score` (104).
- `services/worker/src/croquito_worker/tracing.py` — `TraceSolveResult`
  (349-371: `residuals`, `unapplied_reading_ids`) como forma do sinal
  opcional de solver.

## Escopo

1. Campos **aditivos** no candidato de associação (`association.py`), todos
   opcionais/derivados, sem remover nem renomear nada:
   `orientation_alignment` (0–1: alinhamento entre o eixo dominante do bbox
   da evidência da leitura e a direção do segmento candidato; `None` para
   candidato sem direção, ex. círculo), `association_confidence` (0–1).
2. Módulo novo `services/worker/src/croquito_worker/association_confidence.py`:
   - `reading_confidence(reading, chains) -> float` — sinais:
     `ocr_corroborated` (booleano existente), participação em cadeia que
     fecha (`DimensionChain.closes` com a leitura entre os termos), presença
     de valor+unidade coerentes. Pesos nomeados como constantes.
   - `association_confidence(candidate, reading, ...) -> float` — sinais:
     `proximity_score`, `visual_quality_score`, `orientation_alignment`,
     margem sobre o segundo candidato (ambiguidade), e sinal OPCIONAL de
     solver (resíduo da leitura quando um diagnóstico de solve existir para
     a revisão — ausente ⇒ neutro, nunca requisito).
   - `shadow_decisions(packet, associations, chains, thresholds) -> ...` —
     função pura: para cada threshold da grade, quais leituras/associações
     estariam acima (leitura E associação, conforme decisão do spec), sem
     efeito colateral.
3. Determinismo: mesma entrada ⇒ mesmos números, sem relógio, sem aleatório.
4. Testes: `tests/worker/test_association_confidence.py` (novo) cobrindo
   monotonicidade dos sinais, candidato ambíguo rebaixado pela margem,
   círculo sem orientação, leitura sem cadeia, determinismo (duas chamadas
   idênticas); atualização mínima de `tests/worker/test_association.py`
   para os campos novos.

## Fora de escopo

Persistência, API, migração, flag, tela, eval, mudança em
`dimension_closure.py`, mudança de contrato de provider, qualquer decisão
automática. `safety_notes` da associação continuam declarando que nada é
confirmado automaticamente.

## Critérios de aceite

1. Campos novos presentes e serializáveis no `AssociationSet` sem quebrar
   nenhum consumidor existente (testes atuais passam sem edição de
   comportamento).
2. As duas confianças são 0–1, determinísticas e distintas — nunca fundidas
   num número só.
3. `shadow_decisions` é pura e coberta por teste.
4. `make check` e `uv run pytest tests/worker` verdes.

## Baseline

`main` limpa, portões verdes (registrado no plano em 2026-08-21). Falha nova
em área não tocada: parar e reportar, não consertar.

## Validação (comandos reais)

```bash
make check
uv run pytest tests/worker/test_association.py tests/worker/test_association_confidence.py
make test
```

## Gates e relatório

Nenhum gate humano dentro desta task. Encerrar com `BUILD REPORT` completo
(contrato do Builder da camada pinada em `docs/engineering-os/agents/builder.md`).
