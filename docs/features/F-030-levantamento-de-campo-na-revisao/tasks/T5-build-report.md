# T5 — BUILD REPORT

Relatório do Builder para o [Task Contract T5](T5-testemunhas-web.md) da
[F-030](../feature.md). Executado na branch `feat/f-030-t5-t7`, sem push.

```text
BUILD REPORT

Status: BUILD_COMPLETE

Files changed:
  - apps/web/src/api.ts
    Tipos FieldWitness/FieldWitnessSource/ReviewWitnessCommand/FieldPhotoValueDraft,
    campo field_witnesses em Review, e os clientes mutateReviewWitnesses (associate/
    retract) e confirmFieldPhotoValue (Ato 1, POST append-only + re-GET). Decimal do
    servidor tipado como string; cliente nunca envia valor nem diferença.
  - apps/web/src/fieldEvidence.ts
    Helpers puros: eligibleWitnessSources (medidas confirmed + valores confirmados em
    foto, menos pares já associados; leitura de máquina crua nunca entra),
    witnessSourceOptionValue/parse (roundtrip), witnessEyebrow, witnessSourceValueLabel,
    witnessMeters (magnitude neutra), pendingPhotoValues, mmFromValueHint.
  - apps/web/src/fieldEvidencePanel.tsx
    Ato 1 do legado (estado 7): FieldPhotoValueBlock + ValueConfirmForm, integrados no
    FieldPhotoCard/FieldEvidenceBody e no container (estado editingValueKey, handler
    onConfirmValue com recarga em 409). O painel nunca oferece associação.
  - apps/web/src/CroquiApp.tsx
    Atos 2 (estados 5-6): FieldWitnessesSection (bloco puro exportado) com testemunhas
    empilhadas, diferença neutra, retratação individual e o fluxo de associar em dois
    tempos com carga preguiçosa das fontes elegíveis. Estado/handlers no container,
    reset ao trocar de leitura, 409 no banner global.
  - apps/web/src/labels.ts
    measurementKindLabel ganha diagonal/level/drop (espécies aceitas ao confirmar valor).
  - apps/web/src/styles.css
    Composições .witness-panel/.testemunha/.confronto/.valor/.diferenca e formulários,
    sobre tokens existentes; zero cor nova, diferença sem veste de alerta.
  - apps/web/src/fieldEvidence.test.ts
    Helpers puros de testemunha + transporte de mutateReviewWitnesses e
    confirmFieldPhotoValue (Idempotency-Key, base_version, 409, sem valor no corpo).
  - apps/web/src/fieldEvidencePanel.test.tsx
    Estado 7: valor a confirmar com dois atos, valor confirmado com fronteira, edição;
    o painel nunca contém "Associar". Props novas nos helpers de render.
  - apps/web/src/CroquiApp.test.tsx
    FieldWitnessesSection: uma testemunha (diferença neutra, sem vocabulário de
    concordância nem tom), duas empilhadas sem vencedora, gate de leitura não
    confirmada, ready-vazio sem botão morto, loading/error.

Validation executed:
  - npm --workspace @croquito/web run test .......... exit 0 (1121 passed, 45 files)
  - npm --workspace @croquito/web run build ......... exit 0 (tsc -b + vite build)
  - make check ..................................... green até infra-check
    Ruff/formatação, mypy strict, check_docs, drift de contratos e build web/field
    passaram. O passo final `terraform fmt -check` não roda: o binário terraform não
    está instalado neste ambiente (limitação pré-existente). T5 não toca infra/.

Validation skipped: terraform fmt (binário ausente no ambiente; nenhuma mudança em infra)

Unavailable capabilities: terraform CLI

Assumptions:
  - Decimal do servidor (reading_value_mm, source_value_mm, difference_mm) chega como
    string no JSON; a tela exibe a magnitude formatada em pt-BR sem reescrever precisão.
  - As fontes elegíveis são carregadas por getFieldEvidence no clique de associar, fora
    do painel de evidência (autocontido). Obsolescência residual cai nos erros nomeados
    do servidor (FIELD_WITNESS_SOURCE_NOT_FOUND/NOT_CONFIRMED), exibidos por extenso.
  - A confirmação de valor lido (Ato 1) usa evidence.version como base_version; 409
    recarrega a evidência e pede nova confirmação.

Remaining risks:
  - Nenhuma tolerância foi inventada. A diferença é número neutro; classificar concordância
    exige calibração futura, fora desta task (decisão humana de 2026-08-23).

Human decisions required: none
```
