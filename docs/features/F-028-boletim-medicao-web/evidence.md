# F-028 — Evidência de execução

Consolidação no formato do template global. Cada `tasks/T*-build-report.md` é
`PRIMARY_EXECUTION_EVIDENCE` da sua task; este documento os referencia.

## Contexto

- Feature Contract: [feature.md](feature.md) (`INTERFACE_CHANGE`).
- Design Approval Package: [mock/README.md](mock/README.md) — revisão 1 **aprovada por
  Daniel Campos em 2026-08-20**, com a aprovação em DOIS atos explícitos mantida por
  decisão humana. Copy final permanece aberta.
- Plano: [plan.md](plan.md) — T1 → (T2 ∥ T3), com um `PLAN_DEVIATION` registrado.
- Execução: 2026-08-20, branch `f-025-boletim-web` (base: `especificacao-f025-f027`),
  worktree `croquito-f025`. Merge REPRESADO por decisão humana da mesma data.

## Baseline

`make setup` + `make check` + `make test` verdes na árvore limpa da branch antes de T1
(pytest 1695+/13, vitest 693). Nenhuma falha preexistente.

## Tasks e Build Reports

| Task | Contrato | Build Report | Status | Executor |
|---|---|---|---|---|
| T1 — rotas approve + bulletin/export | [T1](tasks/T1-rotas-aprovacao-export.md) | [report](tasks/T1-build-report.md) | BUILD_COMPLETE | implementador-opus |
| T2 — etapa "Aprovação e exportação" na jornada | [T2](tasks/T2-etapa-web.md) | [report](tasks/T2-build-report.md) | BUILD_COMPLETE | implementador-opus |
| T3 — e2e /v1 + paridade CLI×rota | [T3](tasks/T3-e2e.md) | [report](tasks/T3-build-report.md) | BUILD_COMPLETE | implementador-sonnet |

Estado final integrado na branch (portões rodados por T2 sobre a árvore com os três
diffs): `make check` exit 0 (mypy strict 194 fontes, contratos sem drift, build web);
pytest **1709 passed / 13 skipped**; vitest **729 passed** (baseline 693).

## Incidente de ambiente

O primeiro turno de T1 foi interrompido por **disco cheio (ENOSPC, 0 bytes livres)** —
BUILD_BLOCKED honesto com estado intermediário declarado. Espaço liberado pelo
orquestrador (venvs recriáveis + temporários; cache do uv de 11 GB segue candidato a
poda quando ocioso); T1 retomado do ponto exato e concluído. Registrado como contexto
de execução.

## PLAN_DEVIATION (registrada em [plan.md](plan.md))

O Builder de T1 provou que o `/calc` regravava `valuation_json` sem `approval` — o
estado "aprovação caduca" do design APROVADO era inatingível (recalcular apagava a
assinatura). Decisão do orquestrador: a ROTA `/calc` carrega a aprovação da cabeça
adiante (`carry_approval_forward`); o domínio não muda; o digest amarrado torna a
aprovação preservada incapaz de autorizar conteúdo novo (`APPROVAL_CONTENT_MISMATCH`).
Consequência de leitura para a tela: no estado caduco, `approved=true` E `stale=true`
— T2 lê os dois.

## Revisão (modelo principal da sessão)

- T1: linha a linha em `carry_approval_forward` (preservar ≠ aprovar; ilegível não
  carrega) e `bulletin_export_contract` (consolidado derivado: códigos de
  contrato/saldo declaradamente inertes — caracterizado por teste de igualdade exata
  `["VALUATION_NOT_APPROVED"]` no caminho feliz —; aprovação integralmente ativa;
  conferência de preço no auditor). Identidade só do JWT. Aprovado.
- T2: spot-check nos pontos vinculantes do design — dois atos explícitos presentes,
  export condicionado a `approved && !stale`, nenhuma cor nova, frases antecipatórias
  "sem aprovação" removidas. Aprovado.
- T3: paridade CLI×rota por canonicalização com `contract=None` nos dois lados (desvio
  justificado: `run_export_valuation` exige ContractWorkbook e imprimiria a GERAL);
  ciclo completo recusa→aprova→exporta→recalc-caduca→reaprova→exporta. Aprovado.

## Decisões e limites declarados

- Payload de auditoria reprovada carrega só `finding_codes` (nunca
  `expected`/`found` — dinheiro do cliente não sai em problem+json).
- `.xlsx` endereçado por digest; URL assinada só no GET, nunca persistida.
- Consolidado derivado com `item_number` de até 3 dígitos (>999 códigos distintos
  falharia na montagem) — risco declarado, irreal hoje.
- VAL-05 atualizado em `docs/product/ACCEPTANCE_CRITERIA.md` (a superfície `/v1`+web
  existe; o ATO real segue pendente). FDD inalterado: sua frase permanece verdadeira.

## Gates humanos

1. Seleção (2026-08-20) — exercida. 2. Design rev. 1 — **aprovado em 2026-08-20**.
3. **Merge — represado por decisão humana; pendente.**
4. Copy final da etapa — pendente (declarado no pacote).
5. **O ATO nominal sobre medição real** (Campo do Toca) — ato do usuário pós-deploy;
   fecha a pendência histórica de VAL-05/TRACEABILITY.
