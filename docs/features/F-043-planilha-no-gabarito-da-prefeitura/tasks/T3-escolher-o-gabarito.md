# F-043 T3 — Escolher o gabarito na jornada web

- **feature_id**: F-043
- **task_id**: T3
- **role**: builder
- **depends_on**: [T1, T2]
- **required_capabilities**: READ, WRITE (`services/api`, `apps/web/src/orcamento`, `tests/api`), VALIDATE
- **risk**: MÉDIO — toca o despacho, que publica arquivo; o caminho sem gabarito não pode mudar.
- **relative_effort**: L
- **validation**: `BROWSER_REQUIRED` (estado 02 do pacote aprovado)

## Gate cumprido

[Design Approval Package](../mock/README.md) **revisão 3 aprovada por ato humano em
2026-09-01** (Daniel Campos). O estado **02 — publicar: escolher o gabarito e a revisão** é o
que esta tarefa constrói.

## O que faltava, e por quê

A T1 entregou o escritor do gabarito e a T2 o tornou dado publicável. Faltava a ponta: quem
publica a planilha é a **orçamentista**, e ela não é `platform_operator` — a rota de
plataforma administra o acervo, não o oferece. Sem uma rota de leitura pela rodada, o gabarito
era publicável e inalcançável.

E o despacho não tinha onde citá-lo: `render_estimate_workbook(estimate, default_template())`
usava o template fixo, sem `estimate_grid`.

## Escopo

### 1. `GET /v1/estimate-rounds/{round_id}/estimate-templates`

Molde: `list_estimate_site_setup_kits`. Dois filtros — `visible_templates(tenant)` e em
circulação. Papel antes de qualquer lookup; rodada alheia é `404`. Payload próprio
(`template_option_payload`): sem `created_by`, que é identidade de operador de outro tenant.

### 2. `ExportEstimateRequest.estimate_template_id`, opcional

Opcional **de propósito**: a rodada que não entrega àquela prefeitura não tem gabarito a citar,
e exigir um faria a jornada de hoje parar de funcionar.

Quem escolhe o escritor é o **template**, não um parâmetro: `render_estimate_workbook` olha
para `estimate_grid` e chama `write_estimate_grid_workbook`/`audit_estimate_grid_workbook` ou o
par de hoje. Os dois caminhos passam pelo mesmo portão fail-closed — é isso que impede que
escolher o gabarito escolha também uma auditoria mais frouxa.

### 3. O carimbo: `estimate_round_revisions.estimate_template_json` (migração `0030`)

Identidade, revisão e digest do documento. **Não** as linhas: elas vivem em
`estimate_templates`, imutáveis por publicação, e copiá-las criaria uma segunda verdade.

A coluna entra em `REVISION_DOCUMENT_COLUMNS` porque satisfaz as três propriedades da
categoria: é JSON, `NULL` é afirmação ("publicou sem gabarito") e é carregada adiante.

### 4. A tela: `apps/web/src/orcamento/gabarito.ts` + `EscolhaDoGabarito`

Módulo puro para a lógica, componente exportado para o render ser provado fora do App.

**A tela não decide que uma revisão está velha.** Ela não sabe qual é a aceita hoje, e
inventar um critério — a mais nova da lista, a mais recente por data — seria a máquina
decidindo o que é ato de quem entrega à prefeitura. O aviso pede confirmação **sempre**,
nomeando a revisão escolhida.

"Sem gabarito" é opção de primeira classe no seletor, não ausência.

## Out of scope

- O **gabarito real** do cliente, que não está no repositório e não estará.
- Autoria de gabarito por tenant: a coluna existe desde a T2; o caminho, não.
- A pergunta aberta para a orçamentista (o preço do contrato embute BDI?), registrada em
  [`../evidence.md`](../evidence.md).
- O estado "nenhum gabarito disponível", que o pacote deixou em aberto — a lista vazia
  simplesmente não renderiza a superfície, e a jornada segue como hoje.

## Acceptance criteria

1. A rodada oferece os gabaritos em circulação; a orçamentista os lê sem ser operador.
2. Gabarito retirado some da lista **e** é `404` no despacho.
3. Despacho com gabarito carimba identidade, revisão e digest na revisão nova.
4. Despacho **sem** gabarito continua publicando como hoje, e o carimbo é `NULL`.
5. Código do orçamento ausente do gabarito recusa, e **nada** é publicado.
6. O seletor traz a revisão junto do nome; o aviso nomeia a revisão e pede confirmação.
7. `make check` e `make test` verdes; snapshot OpenAPI sem remoção de superfície.
8. Migração `0030` aplica do zero em PostgreSQL.

## Verificação

```bash
uv run pytest tests/api/test_estimate_round_routes.py -k gabarito
uv run pytest tests/api/test_estimate_templates.py tests/api/test_migrations.py
npm --workspace @croquito/web run test -- src/orcamento/gabarito.test.ts
make check && make test
```
