# F-044 T2 — O índice de precedentes, com as duas fontes

- **feature_id**: F-044
- **task_id**: T2
- **role**: builder
- **depends_on**: [T1]
- **required_capabilities**: READ, WRITE (`packages/valuation`, `services/api`, `services/worker`, `tests/`), VALIDATE
- **risk**: MÉDIO-ALTO — tabela nova, fronteira de tenant, e ingestão a partir de ato humano existente.
- **relative_effort**: L

## Gates cumpridos

O Human Gate 1 — **medir a repetição e decidir se a feature continua** — foi exercido em
2026-08-28: três orçamentos reais, 80% de repetição, 96,1% dos repetidos com pacote idêntico ou
contido. **A feature continua**, e a prioridade subiu para `HIGH`. Ver
[`../evidence.md`](../evidence.md).

O Design Approval Package revisão 1 está aprovado; ele desenha a **T3** (a shortlist), não esta
task.

Decisão do dono na mesma data: **a semeadura a partir de orçamentos passados entra no escopo
da feature.** Sem ela o índice nasce vazio — só uma rodada real existe no banco — e o ganho
medido esperaria várias praças novas.

## Goal

Um índice de precedentes por (rótulo normalizado, fonte de preço) alimentado por **duas
fontes** — a rodada do próprio sistema e a semeadura de orçamentos passados — e a consulta que
a T3 vai usar. **Nenhuma mudança na shortlist e nenhuma tela nesta task.**

## Scope

### 1. Persistência

Tabela nova de observações de precedente. Uma linha por (praça, rótulo, fonte, código):

- `id`, `tenant_id` (index — **é dado do tenant, sempre**), `worksite_key`,
  `label_normalized` (index), `label_original`, `price_source`, `code`,
  `source` (`round` | `seed`), `created_by`, `created_at`.
- Unicidade `(tenant_id, worksite_key, label_normalized, price_source, code)`: reingerir a
  mesma praça é idempotente, não duplica.
- Migração Alembic nova. **Confira o número da última migração no diretório antes de numerar.**

`label_original` existe para a tela poder mostrar como o rótulo foi escrito; `label_normalized`
é a chave. Guardar rótulo de cliente aqui **não cria fronteira de retenção nova** — é o mesmo
dado que as revisões já guardam (feature.md, Constraints).

### 2. Normalização

Reuse `precedent.normalize_label` da T1, com a estratégia `folded`. A medição mostrou que ela
basta neste corpus, e o motivo está declarado na evidência. **Não invente normalização nova** e
grave a estratégia usada junto da observação, ou num lugar onde uma troca futura possa ser
detectada — reindexar com outra estratégia não pode misturar chaves de duas normalizações.

### 3. Fonte A — a rodada do próprio sistema

As observações nascem **no fechamento do pacote de códigos de um item**
(`POST /v1/estimate-rounds/{id}/code-assignments/closures`), que é o ato humano que diz
"acabou" para aquele elemento. Só entram códigos **confirmados** (`status == "confirmed"`,
`code` não nulo); rejeitado nunca entra.

- O rótulo vem de `TakeoffItem.label` do pacote da revisão; a fonte de preço, de
  `CodeAssignment.catalog_sha256`, como a T1 decidiu e documentou.
- A gravação é **efeito do ato**, na mesma transação: fechar o pacote e registrar o precedente
  não podem divergir.
- Fechar o mesmo item de novo não duplica (a unicidade cobre).

### 4. Fonte B — semeadura de orçamentos passados

Dois passos, e a planilha do cliente **nunca sobe**:

**a) Extração local** — subcomando do CLI `croquito-valuation`:
```
precedent-extract --memoria <arquivo.xlsx>:<aba> --worksite <chave> --output <pacote.json>
```
Reusa `memoria_reader`/`scan_memoria_rows` da T1 — **não reimplemente a leitura**. Produz um
pacote com `worksite_key`, a estratégia de normalização, e as observações (rótulo original,
rótulo normalizado, código, fonte de preço). Blocos sem rótulo são **contados e reportados**,
nunca descartados em silêncio.

**b) Ingestão** — rota nova, do tenant (papel da etapa de códigos):
```
POST /v1/precedents/seed
  body: o pacote produzido por precedent-extract
  → {"worksite_key": ..., "observations_ingested": N, "observations_skipped": N, "labels": N}
```
Idempotente por `(tenant_id, worksite_key)`: reingerir a mesma praça não duplica e não soma
duas vezes na contagem de praças. Praça semeada com a mesma `worksite_key` de uma rodada real
é **recusa nomeada** — misturar as duas origens sob a mesma chave inflaria a contagem de
praças, que é o número que a tela mostra como argumento de autoridade.

### 5. Consulta

Função de aplicação, testada, que a T3 vai consumir:

```python
def precedents_for(session, tenant_id, labels, price_source) -> dict[str, PrecedentEntry]
```

Por rótulo normalizado: os códigos, e a **contagem de praças distintas** que os usaram. A
chave é `(rótulo, fonte de preço)` — precedente de outra fonte **nunca** é devolvido (decisão 4
do escopo da feature). Sem precedente, o rótulo simplesmente não aparece no resultado.

Nenhuma chamada paga, e a consulta **não pode** avançar a versão da rodada nem gravar nada.

### 6. Testes

- fechar o pacote de um item grava as observações; fechar de novo não duplica; código rejeitado
  não entra;
- precedente de um tenant **nunca** aparece para outro (teste com dois tenants);
- semeadura ingere, é idempotente por praça, e recusa colisão com praça de rodada real;
- `precedents_for` devolve os códigos e a contagem de praças; **não** devolve precedente de
  outra fonte de preço;
- extração local produz o pacote a partir de uma planilha sintética escrita pelo próprio teste,
  contando os blocos sem rótulo.

## Out of Scope

- **A shortlist e a tela** — é a T3, e o pacote de design já aprovado a governa.
- `suggestions.py` e `assignment.py`: **não toque**.
- Limiar de "quantas praças fazem um precedente confiável" (unknown 3, decisão humana aberta).
- Promover precedente a decisão automática — precedente é observação, sempre.

## Acceptance Criteria

1. O índice tem as duas fontes e uma consulta só.
2. Precedente nunca atravessa tenant, provado com dois tenants.
3. Reingerir praça ou refechar pacote é idempotente — a contagem de praças não infla.
4. Precedente de outra fonte de preço não é devolvido.
5. Nenhuma planilha real em `tests/`; fixtures sintéticas.
6. Nenhuma chamada paga; a consulta não grava e não avança versão.

## Validation

```bash
cd /Users/danielcampos/workspace/daniel/croquito-f044b
uv run pytest tests/api tests/valuation/test_precedent.py -q
make check
make test
```

## Armadilhas verificadas

- `PriceOrigin` não tem `contract`; **não crie**. A fonte é o dado gravado
  (`catalog_sha256`), como a T1 decidiu.
- A cardinalidade `(item_id, code)` é N:N desde a F-038 — um item com vários códigos é o caso
  normal.
- Rótulo de legenda **nunca** entra em log estruturado.
- Rota nova exige `docs/architecture/API_CONTRACT.md` e `make openapi-snapshot`, e a rota entra
  nas listas do drift guard em `tests/api/test_estimate_round_routes.py` — que é o ponto de
  extensão projetado, não um teste a afrouxar.
- `make check` valida todo link relativo de Markdown, inclusive deste arquivo.
