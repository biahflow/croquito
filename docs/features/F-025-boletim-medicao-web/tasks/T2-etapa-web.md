# T2 — Web: etapa "Aprovação e exportação" da jornada de medição

Task Contract derivado do [plano válido](../plan.md). Autossuficiente: assuma o Core,
este contrato, o [feature contract](../feature.md), o
[Design Approval Package aprovado (rev. 1)](../mock/README.md) — **vinculante na
composição; todo texto é rascunho** — e o repositório.

## Identity

```text
feature_id: F-025
task_id: T2
parent_plan: docs/features/F-025-boletim-medicao-web/plan.md
depends_on: [T1]
```

## Goal

A jornada de medição ganha a etapa desenhada no mock aprovado: o ato nominal em DOIS
atos explícitos (decisão humana de 2026-08-20), aprovação registrada/caduca, export em
quatro passos escritos, auditoria reprovada como tela — consumindo as rotas de T1.

## Baseline

T1 integrado na branch; `make check`, `make test` e
`npm --workspace @croquito/web run test` verdes.

## Scope

- `apps/web/src/medicao/etapas.ts`: `EtapaId` (linha 20) ganha `"aprovacao"` depois de
  `"boletim"`; `derivarEtapas` (123-253) deriva os estados do bloco de aprovação do
  payload de T1 (`approved/stale/workbook_present`). A frase antecipatória
  "Medição gravada nesta rodada, sem aprovação." (linha 224) sai — o estado real fala.
- `apps/web/src/medicao/api.ts`: `postApprove(accessToken, roundId, baseVersion)` e
  `postBulletinExport(...)` (rotas de T1); `BulletinResponse` (313-320) ganha os
  campos novos (aprovação + `workbook_present/sha256/url`). Invariantes do cabeçalho
  do arquivo valem (base_version + Idempotency-Key; Decimal string; identidade nunca
  viaja).
- `apps/web/src/medicao/errors.ts`: helpers de auditoria reprovada no molde de
  `apps/web/src/orcamento/errors.ts:24,51,61` (`workbookAuditFindings`), para
  `VALUATION_WORKBOOK_AUDIT_FAILED`.
- `apps/web/src/medicao/labels.ts`, tabela `ERROR_MESSAGES` (176-268): traduções
  novas — `VALUATION_NOT_APPROVED`, `VALUATION_APPROVAL_REJECTED`,
  `APPROVAL_CONTENT_MISMATCH`, `VALUATION_EXPORT_BLOCKED`, `PERIOD_NOT_SEQUENTIAL`,
  `BALANCE_EXCEEDED`, `LINE_PRICE_NOT_IN_CONTRACT`, `LINE_UNIT_NOT_IN_CONTRACT`,
  `VALUATION_WORKBOOK_AUDIT_FAILED`, `ROUND_STAGE_NOT_READY` (se ainda não coberto).
- `apps/web/src/medicao/MedicaoApp.tsx`: seção da etapa nova com as telas do mock —
  1. ato: etiqueta "ATO NOMINAL · VAL-05", consequência em três frases ANTES do
     botão, bloco "Você aprova como <subject>" (mostrado, nunca digitável), botão
     "Aprovar esta medição" → segundo ato que REPETE a consequência ("Confirmar
     aprovação nominal") — dois cliques, mantidos por decisão humana;
  2. aprovação registrada (quem/quando/digest) e aprovação CADUCA (dois digests lado
     a lado, código `APPROVAL_CONTENT_MISMATCH`, única ação: aprovar de novo —
     NENHUM "exportar assim mesmo");
  3. export: quatro passos escritos (montar/gravar/reconferir/publicar), publicado
     (nome do arquivo, sha, data, download), auditoria reprovada como TELA — "nada
     foi publicado" por extenso + tabela da célula divergente
     (`workbookAuditFindings`);
  4. transversais: 403 sem nomear papel, 409 com banner próprio, recusa de domínio
     traduzida. O toast "Boletim e memória gravados na rodada, sem aprovação."
     (linha ~1314) muda para o estado real ("… aguardando aprovação nominal").
- Botão de export desabilitado/ausente sem aprovação válida (o mock diz: "nem
  aparece como disponível") — mas a DEFESA é do servidor; a tela só espelha.
- Testes vitest: etapas derivadas (aprovado/caduco/exportado), traduções novas,
  fluxo dos dois atos, tela de auditoria reprovada.

## Out of scope

- Croqui, `orcamento/`, backend, estilos/cores novos (tokens e classes existentes;
  composições novas seguem a proveniência do mock), copy definitiva (texto do mock
  como rascunho — listar no report).

## Acceptance criteria

1. `make check` e `npm --workspace @croquito/web run test` verdes.
2. Dois atos explícitos; nenhum caminho de export sem aprovação válida na tela.
3. Estados do mock todos presentes (repouso, confirmação, gravando, registrada,
   caduca, export 4 passos, publicado, auditoria reprovada, 403, 409).
4. Nenhuma cor nova (diff prova); identidade nunca em campo digitável.

## Validation

```bash
make check
npm --workspace @croquito/web run test
```

## Required capabilities

READ, WRITE, VALIDATE. Sem COMMIT: deixe o diff na árvore.

## Report

`BUILD REPORT` completo em
docs/features/F-025-boletim-medicao-web/tasks/T2-build-report.md.
