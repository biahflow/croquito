# F-033 T1 — O regime como dado da rodada, com as duas recusas

feature_id: F-033
task_id: T1
parent_plan: ../plan.md
role: builder

## Goal

A rodada de orçamento passa a poder declarar que corre sob contrato licitado. A partir daí a
cascata só aceita `sco`, e a recusa acontece na **instalação** — quando ainda há o que
corrigir —, nunca na montagem.

## Scope

1. **Migração `0009`**, forward-only no molde da `0004_estimate_round_target.py`
   (`downgrade()` levanta `NotImplementedError`): `op.add_column` de coluna **nullable** em
   `estimate_rounds`. A `0008` é da F-034 e já está na main.
2. **Coluna** em `EstimateRoundRecord` — `database.py:600-608` (o teto) é o molde exato.
3. **Declaração do regime**, no molde de `POST /v1/estimate-rounds/{round_id}/target`
   (`main.py:7712-7776`): `base_version` + `Idempotency-Key` + `_require_valuation_reviewer`,
   gravando direto no registro (regime é parâmetro da rodada, como o teto e o BDI — **não** é
   revisão append-only) e `version += 1`. Também aceito na criação da rodada, como o teto.
4. **Mão única**: tentar voltar para pré-licitação recusa com código estável próprio. Não
   existe caminho de reversão — decisão humana de 2026-08-22 registrada no plano.
5. **Recusa da declaração com cascata suja**: havendo fonte com origem ≠ `sco` instalada, a
   declaração recusa com código estável, **sem gravar nada**. Remover usa `/catalogs/remove`,
   que já existe.
6. **Recusa na instalação**: `ensure_source_installable` (`estimate_rounds.py:428-451`) ganha
   o regime como entrada; origem ≠ `sco` recusa com código estável novo, no mesmo ponto onde
   `ESTIMATE_CASCADE_ORIGIN_DUPLICATE` já recusa. Chamador único: `main.py:7826`.
7. **Estado da rodada**: `round_state_payload` (`estimate_rounds.py:965-1045`) ganha o bloco
   do regime, no molde do `**target_state(...)` que já entra por spread na linha 1042 — bloco
   **vazio** quando não há regime. É deste bloco que a T2 vive.
8. **Snapshot de OpenAPI** regenerado por `make openapi-snapshot`.

## Out of scope

- Qualquer arquivo em `apps/web/` (é a T2).
- Qualquer mudança na cadeia de medição: `BULLETIN_PRICE_ORIGIN_FORBIDDEN` segue sendo a
  última linha de defesa, não a primeira.
- **Chamar `build_amendment_dossier`.** Ver "Candidato a aditivo" abaixo.
- Amarrar a rodada a um `Contract` real, ou conferir data-base/desconto do catálogo. É a
  lacuna que o ADR-0045 nomeia e deixa aberta de propósito.

## Candidato a aditivo — leia antes de implementar

O contrato da feature fala em "reusar `amendment_dossier.py`". Reuse a **regra**, não a
função. `build_amendment_dossier` exige que **todo** item confirmado no takeoff já tenha
decisão de código (`AMENDMENT_DOSSIER_ASSIGNMENTS_INCOMPLETE`) porque é artefato de
fechamento; chamá-lo faria o sinal aparecer só no fim, que é o atraso que a feature combate.

O sinal já existe no dado: item rejeitado produz `CodeAssignment(status="rejected")` idêntico
ao da medição (`assignment.py:1037-1055`), e `round_state_payload` já conta `codes.rejected`
(`estimate_rounds.py:995-1003`). **Sob o regime, item rejeitado é candidato a aditivo** — e a
leitura disso é da tela (T2). Se algo faltar no estado para a T2 fazer essa leitura, publique
no bloco do regime; não crie artefato, tabela nem builder.

## Acceptance criteria

1. Rodada **sem** regime declarado percorre a jornada exatamente como hoje, provado por teste
   que estende os existentes sem enfraquecê-los.
2. Sob o regime: `sco` instala; `emop`, `sinapi`, `sicro` e `composition` recusam com código
   estável, e a cascata **não muda**.
3. Declarar o regime com fonte proibida instalada recusa e não grava nada.
4. Declarar é possível na criação e depois, com `base_version` e `Idempotency-Key`; voltar
   para pré-licitação recusa.
5. `base_version` velho recusa sem gravar, como no teto.
6. O bloco do regime aparece no estado da rodada e fica vazio quando não há regime.
7. `make check` e `make test` verdes; goldens intocados.

## Pitfalls

- `packages/valuation` não pode passar a depender do worker nem do scene graph (ADR-0016).
- Erros de domínio são estruturados; não faça parsing de string de exceção.
- O snapshot de OpenAPI é ato deliberado: regenere pelo alvo do Makefile.
- Testes: reuse `_create_round(**overrides)`, `_install_catalog(origin=...)`,
  `_round_with_cascade_and_takeoff` e `_confirm_code` de
  `tests/api/test_estimate_round_routes.py`.

## Validation

```bash
make check
make test
uv run pytest tests/api/test_estimate_round_routes.py -q
```
