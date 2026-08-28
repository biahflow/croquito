# F-045 T1 — O domínio da revogação

- **feature_id**: F-045
- **task_id**: T1
- **role**: builder
- **depends_on**: []
- **required_capabilities**: READ, WRITE (`packages/valuation`, `tests/valuation`), VALIDATE
- **risk**: ALTO — mexe no conjunto que o boletim, a exportação e o índice de precedentes leem.
- **relative_effort**: M

## Scope

1. `CodeAssignmentRevocationInput` (ato, com `note` **obrigatória**) e
   `CodeAssignmentRevocation` (registro, com `revocation_id` determinístico no espaço `vr_`).
2. Campo `revocations` no `CodeAssignmentSet`, com default vazio, e recusa no regime `1.0.0`.
3. `apply_code_revocation`: o par sai de `assignments`, o registro entra, o fechamento do item
   cai, o restante do conjunto é preservado.
4. `_ensure_same_plate` extraída de `_ensure_batch_decidable` para valer também aqui.
5. As revogações são carregadas adiante pelos dois `apply_code_assignments*`.

## Out of Scope

- API, tela, migração.
- Desfazer rejeição de item; rollback de revisão.

## Acceptance Criteria

1. O par revogado sai de `confirmed_codes_by_item()`; o conjunto anterior não é alterado.
2. Revogar reabre o pacote (`closed_item_ids()` perde o item).
3. O mesmo par pode ser confirmado de novo depois, e o registro da revogação permanece.
4. Par não confirmado, item fora do takeoff, prancha divergente e regime `1.0.0` são recusas
   nomeadas.
5. `revocation_id` é determinístico e distinto do `vd_` de qualquer decisão.

## Validation

```bash
uv run pytest tests/valuation/test_assignment.py
```

## Resultado

Entregue em 2026-08-28. 12 testes novos em `tests/valuation/test_assignment.py`.
