# F-035 T4 — e2e da cadeia com aprovação e despacho

feature_id: F-035
task_id: T4
parent_plan: ../plan.md
role: builder
depends_on: T2

## Goal

Provar por HTTP, ponta a ponta, que o orçamento só é despachado depois de assinado — e
consertar os dois e2e que hoje esperam a planilha publicada no ato de montar.

## Leia antes de editar

- [`AGENTS.md`](../../../../AGENTS.md) na raiz.
- `tests/e2e/test_estimate_rounds_v1.py` — a cadeia que este teste estende.
- `tests/fakes.py` e `tests/bundles.py` — fixtures compartilhadas.
- `docs/architecture/API_CONTRACT.md`, seção do orçamento, atualizada pela T2.

## O que mudou e por que estes testes quebram

`POST .../estimate` **deixou de publicar** a planilha: agora ele só monta. Publicar exige
assinatura (`POST .../estimate/approve`, papel `aprovador`) e depois o despacho
(`POST .../estimate/export`, papel `orcamentista`).

Dois e2e assertam planilha publicada logo após a montagem e **precisam aprender a cadeia
nova**:

- `tests/e2e/test_estimate_rounds_v1.py` — `workbook_url is not None`, por volta da linha 477;
- `tests/e2e/test_reference_catalog_chain.py` — idem, por volta da linha 687. Este foi
  escrito hoje, na F-037, e a **prova de equivalência** que ele carrega (o mesmo catálogo
  pelos dois caminhos produzindo orçamento idêntico) **precisa continuar valendo** depois de
  passar a assinar e despachar.

## Scope

1. **Cadeia nova**, em `tests/e2e/`: montar → assinar com o papel `aprovador` → despachar
   com o `orcamentista` → ler a planilha publicada. Dois tokens diferentes, porque quem
   monta não assina.

2. **Ajuste dos dois e2e existentes**: eles passam a aprovar e despachar antes de esperar
   `workbook_url`. **Não enfraqueça o que eles já provam** — em especial a equivalência
   entre acervo e upload do `test_reference_catalog_chain.py`, que compara linhas, totais e
   a coluna FONTE da planilha reaberta.

3. **A recusa que dá sentido à feature**: exportar sem assinatura recusa, e **nada é
   escrito** — conferido no store, não só no código de status.

4. **A caducidade pela cadeia**: remontar depois de assinado faz o despacho recusar até um
   ato novo de aprovação.

## Out of scope

- **Qualquer arquivo de produção** (`services/`, `packages/`, `apps/`). Esta task só
  acrescenta e ajusta teste. Se um comportamento necessário não existir, **pare e reporte**
  — não o implemente aqui e não contorne com acesso direto ao banco.
- `tests/api/` — a cobertura de rota é da T2.
- Chamada paga de provider: a cadeia usa fixture offline, como os e2e existentes.

## Acceptance criteria

1. A cadeia nova roda offline, sem credencial e sem rede.
2. Assinar exige o papel `aprovador`; despachar, o `orcamentista` — provado com tokens
   distintos na mesma cadeia.
3. Exportar sem assinatura recusa e o store continua **sem** a planilha.
4. Remontar caduca a assinatura e o despacho recusa até ato novo.
5. Os dois e2e existentes voltam ao verde **sem perder nenhuma asserção** que já faziam.
6. `make test` verde.

## Pitfalls

- O `Database` liga `PRAGMA foreign_keys=ON` no SQLite: ordem de inserção errada falha aqui,
  e isso é proposital.
- Reuse as fixtures de `tests/fakes.py` e `tests/bundles.py`; não crie storage próprio.
- Idempotência e `base_version` valem nas mutações novas.
- **Se algo que a cadeia precisa não existir, reporte.** A T2 é quem entrega comportamento;
  fazer o teste passar mexendo em produção aqui esconderia uma lacuna dela.

## Validation

```bash
uv run pytest tests/e2e/ -q
make test
```

## Report

Encerre com o `BUILD REPORT` completo do contrato do Builder — todos os campos presentes,
`none` onde não houver entradas. Se um portão reprovar em área que você não tocou, **pare e
reporte**; não conserte área alheia.
