# F-036 — Evidência de execução

feature_id: F-036  
status: `DONE` (entrega aceita por ato humano em 2026-08-23)  
data: 2026-08-23

## 1. Gates humanos

| Gate | Estado |
| --- | --- |
| Seleção | Exercida em 2026-08-23 |
| **ADR-0048** | **Aceito por ato humano em 2026-08-23** ([ADR-0048](../../adr/0048-consolidado-contratual-do-orcamento-assinado.md), `Accepted`) |
| **Design Approval Package** | **Aprovado por ato humano em 2026-08-23**, revisão 1 ([mock/README.md](mock/README.md)) |
| Migração `0016` no hospedado | **Pendente** — ato de deploy, aplicada pelo job de banco antes da API |
| **Aceite da entrega** | **Exercido por ato humano em 2026-08-23**, sobre este pacote |
| Merge e deploy | **Pendente** |
| Primeira medição real a partir de orçamento assinado | **Pendente** — ato do usuário, pós-deploy |

A **copy** das telas segue fora da aprovação da revisão 1, por declaração do registro.

## 2. Baseline

`make check` e `make test` verdes antes da primeira mudança (2374 passed no ponto de partida
da T3, 2340 no início da feature). Nenhuma falha preexistente.

## 3. Execução

As quatro tasks foram executadas **pelo modelo da sessão**, não delegadas: a sessão tem
instrução explícita de não acionar subagente sem pedido do usuário. Não há `BUILD REPORT` de
subagente a preservar, e este documento é a evidência primária.

| Task | Entrega | Commit |
| --- | --- | --- |
| T1 | `contract_from_estimate.py` — orçamento assinado → `ContractWorkbook` | `330d3cd` |
| T2 | Migração `0016`, segunda origem em `POST /v1/valuation-rounds`, regime de conferência na leitura, portão usando o consolidado gravado, recusa de BDI sob o regime | `25c9b5f` |
| — | BDI **opcional** sob o regime e migração exercitada contra PostgreSQL real | `e1f31a8` |
| T4 | Os seis guardrails, e a cadeia fechando no e2e | `f2a504b` |
| T3a | `GET /v1/valuation-origins` | `0fe4306` |
| T3 | A escolha da origem na tela e o regime de conferência no painel | `db28f1f` |

## 4. Validação

```text
make check                     → exit 0
make test                      → exit 0  (pytest 2381 passed / 10 skipped;
                                          vitest web 1075; vitest field 261)
tests/api/test_migrations.py   → 12 passed com PostgreSQL REAL (docker local)
```

A migração `0016` foi exercitada contra PostgreSQL de verdade, incluindo o drift
`migração × Base.metadata` e a cadeia linear `0001 → 0016`. Não ficou em `SKIPPED`.

## 5. O que a feature prova, e como

O valor da F-036 é um número: o consolidado contratual de origem assinada. Se ele nascer
torto, seis portões viram seis carimbos — e carimbo ninguém confere depois. Por isso a prova
é explícita:

- **Os dois testes centrais da T1 foram provados FALHANDO sem a correção.** Trocar
  `unit_price` por `unit_price_with_bdi` derruba o teste do BDI; não agregar por código
  derruba três, um deles sendo o próprio `ContractWorkbook` recusando código repetido no
  grupo — que é a prova de que a tradução respeita as invariantes do consolidado, e não só as
  asserções do teste.
- **Cinco guardrails disparam**, um teste cada: `BALANCE_EXCEEDED`, `CODE_NOT_IN_CONTRACT`,
  `LINE_PRICE_NOT_IN_CONTRACT`, `LINE_UNIT_NOT_IN_CONTRACT` e `PERIOD_NOT_SEQUENTIAL`. Mais
  um provando o guardrail sabendo **ficar quieto** quando a medição está dentro do saldo.
- **O sexto continua inerte, e o teste prova a inércia** em vez de deixá-la na prosa do ADR:
  `CODE_AMBIGUOUS_IN_CONTRACT` exige o mesmo código em dois grupos, e o consolidado derivado
  de orçamento tem grupo único (ADR-0048, decisão 5).
- **A cadeia fecha no e2e**: o orçamento assinado pela cadeia real abre a medição, que
  declara `signed_estimate` com o mesmo digest que a rota do orçamento devolveu.

## 6. Um erro de dinheiro que existia hoje, fechado

A F-033 restringiu a cascata a `sco` sob `contracted_demand` **sem tocar no BDI**, e o preço
da tabela contratual já o embute. Uma rodada sob o regime aplicava BDI duas vezes — o erro que
o [ADR-0038](../../adr/0038-bdi-como-conceito-de-pre-licitacao.md) já nomeara ao manter o BDI
fora da medição.

O e2e do regime **quebrou** ao ser corrigido, porque montava com 25% sobre preço que já os
continha. A quebra é a consequência que o ADR-0048 declarou, e o teste foi atualizado para
provar a recusa **e** seguir sem BDI — não para tornar o vermelho verde.

Depois de o usuário pedir "tira o BDI se está dando erro", a **fricção** saiu e o guarda
ficou: `bdi_percent` é opcional, ausência vale zero sob o regime, e só um valor não-zero
declarado recusa. Fora do regime segue obrigatório — assumir zero na pré-licitação inventaria
a decisão mais consequente da planilha.

## 7. Quebras de contrato declaradas

Todas visíveis no diff do snapshot de OpenAPI, e nenhuma silenciosa:

- `CreateValuationRoundRequest`: `worksite_key`, `worksite_name` e `catalog_upload_id` passam
  a **opcionais**, e nasce `estimate_round_id`. Exatamente uma origem por pedido.
- `bdi_percent` de `POST .../estimate` passa a **opcional**.
- `valuation_rounds.catalog_upload_id` passa a `NULL`-able no banco (ver §8).
- `GET /v1/valuation-rounds/{id}` ganha o bloco `contracted`.
- Rota nova `GET /v1/valuation-origins`.

## 8. Desvios de plano

Três `PLAN_DEVIATION`, todos registrados no [plano](plan.md):

1. **`catalog_upload_id` virou `NULL`-able.** Um orçamento cuja tabela contratual veio do
   **acervo da plataforma** (F-037) não tem upload do cliente para citar. O docstring da
   própria coluna previa o dia: "se um dia a rodada precisar nascer sem catálogo, é decisão de
   contrato". `catalog_object_key` e `catalog_source_sha256` seguem obrigatórias, então
   nenhuma rodada nasce sem catálogo — o que deixou de ser obrigatório é a proveniência.
2. **O e2e do regime foi atualizado** (§6).
3. **Nasceu `GET /v1/valuation-origins`**, que o plano não previa. Sem ela a tela não tinha
   como saber quais orçamentos podem originar uma medição: `EstimateRoundSummary` traz
   `stage`, e `stage` chega no máximo a `estimate` — que é montado, não assinado.

O teste de adoção de migração cobrou uma decisão: `alter column ... drop not null` era tratado
como destrutivo pela regra, que só tolerava `add column`. Afrouxar um `NOT NULL` não remove,
retipa nem renomeia — é o passo *expand* do expand/contract, e entrou na lista tolerada com a
razão escrita. O oposto (`SET NOT NULL`) continua proibido.

## 9. Divergências do pacote de design

Três, registradas em [mock/README.md](mock/README.md). Duas têm a mesma raiz — **o mock
desenhou dado que nenhuma rota devolve** (o rótulo do catálogo na procedência) —, e a terceira
é o padrão da escolha de origem, que as capturas 1 e 2 descrevem **em conjunto** sem que
nenhuma delas o mostre sozinha. Nenhuma muda a composição visual aprovada.

## 10. Disciplina de mudança

| Documento | O que mudou |
| --- | --- |
| `docs/architecture/API_CONTRACT.md` | `GET /v1/valuation-origins`, as duas origens de `POST /v1/valuation-rounds`, e o bloco `contracted` do estado da rodada |
| `docs/adr/README.md` | ADR-0048 `Accepted` |
| `docs/product/ROADMAP.md` | Estado da F-036 |

## 11. Riscos remanescentes

- **A premissa de domínio que sustenta o preço.** Tudo em §5 e §6 apoia-se no fato declarado
  por ato humano em 2026-08-23: sob `contracted_demand`, o `sco` instalado **é** a tabela
  contratual, com BDI e desconto já embutidos. Se algum contrato real não for assim, a recusa
  de BDI é o que torna o desvio visível — ela expõe o caso em vez de o esconder num total.
- **A lacuna 4 do ADR-0045 permanece.** Nada aqui confere que o orçamento assinado é do
  contrato certo, só que ele foi assinado e que o regime é o contratado. Está desenhada como
  bloco **reservado** no pacote e declarada fora de escopo no contrato.
- **Da segunda medição em diante.** O ADR-0048 decisão 8 fixa a regra (o consolidado deriva do
  orçamento **mais** as medições aprovadas anteriores), e a implementação entrega o caso sem
  período lançado. A segunda medição vinculada é trabalho de quem a construir, e a função de
  domínio não ganhou parâmetro especulativo para ela.
- **Rodada sob o regime montada com BDI antes do deploy** tem total inflado. Depois desta
  entrega ela deixa de montar, e remontar é ato normal da jornada — mas o número antigo
  existiu e pode ter circulado.
- **Migração `0016` não aplicada no hospedado.** É ato de deploy: o job de banco a aplica
  antes da API.

## 12. Decisões humanas pendentes

1. ~~Aceitar a entrega~~ — ✅ **exercido em 2026-08-23**.
2. **Confirmar as três divergências do pacote de design** (§9).
3. **Confirmar os códigos de recusa criados na execução**, que o ADR nomeava sem fixar:
   `ESTIMATE_ORIGIN_REGIME_REQUIRED` → `409`, `ESTIMATE_ORIGIN_NOT_SIGNED` → `409`,
   `ESTIMATE_CODE_PRICE_CONFLICT` (domínio) e `ESTIMATE_BDI_FORBIDDEN_UNDER_REGIME` → `422`.
4. Merge, deploy e a migração `0016` no hospedado.
