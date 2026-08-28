# F-045 T2 — As rotas irmãs e a compensação do índice

- **feature_id**: F-045
- **task_id**: T2
- **role**: builder
- **depends_on**: [T1]
- **required_capabilities**: READ, WRITE (`services/api`, `tests/api`, `docs/architecture`), VALIDATE
- **risk**: ALTO — ato humano gravado, e um efeito colateral no índice que a F-044 lê.
- **relative_effort**: M

## Scope

1. `POST /v1/valuation-rounds/{id}/code-assignments/revocations` e a irmã em
   `estimate-rounds`, com `Idempotency-Key`, `base_version`, auditoria e evento de rodada.
2. `precedents.revoke_closure_precedent`: apaga a observação daquele par — **só desta praça,
   só de origem `round`** — na mesma transação da revogação. A fonte de preço é lida do
   assignment antes de ele sair do conjunto.
3. Recusa provisória `ASSIGNMENT_REVOCATION_AFTER_APPROVAL` quando o orçamento já tem
   aprovação vigente (ADR-0061 D7).
4. `docs/architecture/API_CONTRACT.md`, `tests/api/openapi.snapshot.json` e as duas listas
   fechadas de rotas dos testes de papel.

## Out of Scope

- Tela; migração; qualquer mudança na gravação do índice pelo fechamento.

## Acceptance Criteria

1. Revogar devolve o conjunto novo, com `revocations` e sem o par.
2. A observação daquela praça sai do índice; a de outra praça e a semeada permanecem.
3. Refechar depois de reconfirmar reindexa o par.
4. Versão-base velha devolve `409`; sem motivo, `422`.
5. Com orçamento aprovado, `422 ASSIGNMENT_REVOCATION_AFTER_APPROVAL`.

## Validation

```bash
uv run pytest tests/api/test_precedents.py tests/api/test_valuation_round_routes.py \
  tests/api/test_estimate_round_routes.py tests/api/test_openapi_contract.py
```

## Resultado

Entregue em 2026-08-28. 9 testes novos entre os três arquivos de rota.
