# F-037 T5 — e2e: publicar no acervo e montar orçamento a partir dele

feature_id: F-037
task_id: T5
parent_plan: ../plan.md
role: builder
depends_on: T2

## Goal

Provar por HTTP, ponta a ponta, que uma tabela publicada uma vez pela plataforma leva um
orçamento até a planilha — e que o resultado é **logicamente idêntico** ao do mesmo catálogo
instalado por upload.

## Leia antes de editar

- [`AGENTS.md`](../../../../AGENTS.md) na raiz.
- `tests/e2e/test_estimate_rounds_v1.py` — a cadeia que este teste espelha
  (`test_estimate_round_full_chain_through_v1_api`, linha 187).
- `tests/fakes.py` e `tests/bundles.py` — fixtures compartilhadas (storage e fila com
  estado; pacote de revisão com digests amarrados).

## Scope

1. **Cadeia completa pelo acervo**, em `tests/e2e/`: o operador publica o catálogo; a
   orçamentista abre a rodada, **escolhe** a tabela da lista, envia a prancha, revisa o
   takeoff, decide os códigos e monta o orçamento.

2. **A prova de equivalência** — o critério que dá sentido à feature: o mesmo catálogo
   instalado pelos dois caminhos (acervo e upload) produz orçamento com a **mesma
   proveniência por linha** e o mesmo `source_sha256`. A procedência é metadado do gesto de
   instalar, não regra que muda preço.

3. **Dois tenants sobre uma publicação**: a mesma tabela publicada uma vez serve rodadas de
   tenants diferentes, sem novo upload.

4. **A recusa que protege o isolamento**: nenhuma resposta da cadeia carrega URL assinada de
   objeto do acervo.

## Out of scope

- Qualquer arquivo de produção (`services/`, `packages/`, `apps/`). Esta task **só**
  acrescenta teste. Se um comportamento necessário não existir, **pare e reporte** — não o
  implemente aqui.
- Qualquer arquivo em `apps/web/`.
- Chamada paga de provider: a cadeia usa fixture offline, como os e2e existentes.

## Acceptance criteria

1. O teste roda offline, sem credencial e sem rede, como os demais de `tests/e2e/`.
2. Equivalência entre os dois caminhos provada por comparação de dado, não por inspeção
   visual.
3. Duas rodadas de tenants diferentes instalam a mesma publicação.
4. `make test` verde; nenhum teste existente enfraquecido.

## Pitfalls

- O `Database` liga `PRAGMA foreign_keys=ON` no SQLite: ordem de inserção errada falha aqui,
  e isso é proposital.
- Reuse as fixtures de `tests/fakes.py` e `tests/bundles.py`; não crie storage próprio.
- Idempotência e `base_version` valem nas mutações — o e2e existente já mostra o padrão.
- Se o teste precisar de um dado que a T1/T2 não publicaram, isso é achado sobre as tasks
  anteriores: **reporte**, não contorne com acesso direto ao banco.

## Validation

```bash
uv run pytest tests/e2e/ -q
make test
```

## Report

Encerre com o `BUILD REPORT` completo do contrato do Builder — todos os campos presentes,
`none` onde não houver entradas. Se um portão reprovar em área que você não tocou, **pare e
reporte**; não conserte área alheia.
