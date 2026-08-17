# FEATURE EXECUTION PLAN — F-003

feature_id: F-003
goal: Migrar a cadeia de medição de obra do servidor de rodada
(`services/worker/src/croquito_worker/valuation/local_server.py`) para a API `/v1`
autenticada, migrar as telas de `apps/medicao` para `apps/web` e remover o modo hospedado —
mudando a superfície, nunca o produto.
assumptions: O [ADR-0028](../../adr/0028-medicao-na-api-v1-autenticada.md) (`Accepted`) e a
seção "Medição de obra" do [API Contract](../../architecture/API_CONTRACT.md) são
autoritativos e não se reabrem; o servidor **local** do
[ADR-0020](../../adr/0020-local-homologation-server-for-valuation.md) e o CLI
`croquito-valuation` permanecem vivos; `packages/valuation` sai intacto — a semântica
monetária do [ADR-0016](../../adr/0016-valuation-bounded-context.md) (`TRUNC(x,2)` para
dinheiro, `ROUND(x,2)` para quantidade, recusa de `float` na fronteira) não é tocada.
risks: Migrar superfície e mudar comportamento no mesmo trabalho, tornando a regressão
indistinguível da mudança pretendida — mitigado extraindo a lógica de aplicação para módulos
que o servidor local continua consumindo, de modo que os 2.168 testes de
`tests/worker/test_valuation_local_server.py` sigam cobrindo o mesmo código **sem uma linha
alterada**. Perder o carimbo de identidade do servidor ao reimplementar rotas — mitigado
portando primeiro o teste que o protege. Reescrever os módulos puros de `apps/medicao` em vez
de movê-los — mitigado por `git mv` e portão de revisão: nos módulos sem acoplamento, o diff
só pode conter caminhos de import.

## Baseline

Medido em 2026-08-17, antes da primeira alteração:

| Portão | Estado |
| --- | --- |
| `uv run pytest --co` | 1.298 testes |
| `npm run web:test` | 346 testes, 12 arquivos |
| `npm run medicao:test` | 127 testes, 9 arquivos |
| `uv run ruff check .` | All checks passed |
| `uv run python scripts/check_docs.py` | 113 arquivos Markdown válidos |

## Decisões humanas de 2026-08-17

Registradas aqui porque três delas fecham lacunas que o ADR-0028 deixou explicitamente em
aberto, e uma quarta corrige uma lacuna que nenhuma fonte versionada havia notado.

| Questão | Decisão |
| --- | --- |
| Escopo desta rodada | F-003 inteiro: backend `/v1`, telas em `apps/web` e remoção do modo hospedado |
| Modo hospedado | Parado e não utilizado; sem período de convivência a preservar |
| Rodadas no bucket de homologação | **Nenhuma migração de dados** — fecha a primeira decisão pendente do ADR-0028 |
| `GET` de code-suggestions, que hoje grava artefato | **Persistir sem avançar `version`**: shortlist é artefato derivado, não ato humano |
| Braço semântico de `catalog/search` | **Léxico por padrão**; `arm=hybrid` exige o entitlement contratual do [ADR-0012](../../adr/0012-contractual-ai-processing-entitlements.md) |
| `period_number`, `address`, `contract_label` | **Atributos da rodada**, em `POST /v1/valuation-rounds` — nenhuma rota do contrato os recebia, e sem eles o boletim não fecha |

## Achados que governam a execução

1. **`ExactDecimal` gera `anyOf: [number, string]`** no JSON Schema, atingindo
   `BulletinLine.unit_price`/`.quantity`/`.total`, `CalcBlock.subtotal`, `CalcOperand.value`,
   `CalcSheet.total_quantity` e `WorksiteBulletin.total_amount`. Gerado para TypeScript vira
   `number | string`, e o `float` que o domínio recusa na fronteira entraria pela porta dos
   tipos, contra a regra de que a tela nunca calcula dinheiro. O schema exportado passa a
   fixar `string`.
2. **A API já importa `croquito_worker`**, e `packages/valuation` não o importa — a lógica
   reusável mora em `croquito_worker/valuation/`, não no pacote de domínio.
3. **O gate de paridade de OpenAPI é bidirecional e a pendência é por seção**: não existe
   estado válido com parte das rotas exposta. As rotas nascem fora do documento e são
   publicadas num passo único.
4. **O envelope da fila exige `job_id`**, e o ADR-0016 proíbe `Job` na medição — o despacho
   passa a rotear por comando antes de exigir o campo.
5. **O presign só assina PDF**, mas `catalog_upload_id` é JSON — lacuna de contrato fechada
   nesta feature, com o API Contract atualizado junto.
6. **Nem todo artefato cabe em coluna JSON**: catálogo (2,4 MB), índice de embeddings (39 MB),
   PDF e PNGs vão ao object store por digest, pela própria regra de blobs do ADR-0028 D2.
7. **`/calc` e `/amendment-dossier` não têm guarda de concorrência hoje** e passam a poder
   devolver `409`. Há teste que congela essa ausência; é mudança pretendida e fica declarada.
8. **`local_server` importa `REVIEWER_ROLE` de `hosted_auth`**: o servidor que sobrevive
   depende do módulo que será removido. Desarmado antes de tudo.

## Tasks

### Fase 0 e 1 — fundação, sem rota e sem tabela

- **T0** Mover `REVIEWER_ROLE`/`REVIEWER_ID_MAX_LENGTH` para fora de `hosted_auth.py`.
- **T1** Extrair de `local_server.py` para `round_view.py`, `catalog_search.py`,
  `round_extraction.py` e `suggestions.py`; o servidor local vira o adaptador de disco.
  *Aceite:* os 2.168 testes passam sem edição; nenhum módulo novo importa `fastapi` nem
  `croquito_api`.
- **T2** Pipeline de contratos multi-modelo sobre manifesto único versionado em
  `packages/contracts`, com o portão do achado 1. *Aceite:* `scene.schema.json` e
  `scene.generated.ts` byte-idênticos; `croquito_core` sem importar `croquito_valuation`.

### Fase 2 — persistência

- **T3** `valuation_rounds` e `valuation_round_revisions` em `database.py` + migration `0002`
  revisada à mão. *Aceite:* `BASELINE_TABLES` não muda — as tabelas nascem depois da
  baseline, como o [ADR-0029](../../adr/0029-runner-de-migrations-revisadas.md) previu.

### Fase 3 — superfície `/v1`

- **T4** núcleo de aplicação sem HTTP; **T5** presign aceita catálogo; **T6** criar, listar e
  estado; **T7** prancha, imagem assinada e enfileiramento; **T8** comando
  `extract_valuation_plate` no worker, com claim atômico para que reentrega nunca repague o
  provider; **T9** takeoff; **T10** códigos e catálogo; **T11** boletim e dossiê.
- **T12** Publicar a superfície: documento OpenAPI, remoção do aviso de pendência do API
  Contract e inversão do teste que hoje ancora a ausência das rotas.
- **T13** E2E da cadeia inteira sobre `/v1`; o e2e do CLI permanece intacto.

### Fase 4 — telas

- **T14** fronteira de jornada como módulo puro; **T15** casca de `apps/web` com a sessão
  içada; **T16** CSS escopado; **T17** `git mv` dos módulos e limpeza de workspace;
  **T18** barrel de contratos; **T19** extração dos puros de `api.ts`; **T20** cliente `/v1`;
  **T21** imagem por URL assinada; **T22** dicionário de erros remapeado; **T23** etapas sobre
  o estado novo; **T24** a rodada como recurso; **T25** as telas sobre `/v1`.

### Fase 5 — remoção e fechamento

- **T26** Remoção no repositório: modo hospedado, `hosted_auth.py`, flag `--hosted`,
  `CROQUITO_IO_DIRECT_WRITE` e rota de borda. O servidor local fica.
- **T27** Atos de produção — **humanos**.
- **T28** Documentação canônica e `evidence.md`.

## critical_path

T0 → T1 → T3 → T4 → (T5…T11) → T12 → T13 → T26 → T28. T2 e a Fase 4 até T17 correm em
paralelo por não dependerem das rotas.

## integration_strategy

Um commit por tarefa, cada um com `make check` e `make test` verdes. As rotas ficam fora do
documento OpenAPI até T12, porque o gate de paridade não admite superfície parcial. As
regenerações (`make contracts`, `make openapi-snapshot`, `make db-revision`) acontecem dentro
da tarefa que as torna necessárias.

## human_gates

- Aprovação deste plano e da execução, em 2026-08-17.
- **T27** — remoção do serviço Cloud Run, da rota de borda e alteração de realm compartilhado.
- Aplicação da migration em ambiente remoto: criar a revisão é execução; aplicá-la, não.
- Nenhuma chamada paga de provider é feita por esta feature; a extração é exercitada por
  fixture pelo seam já existente.
- A homologação real da orçamentista permanece pendente e **não** é substituída por esta
  migração.
