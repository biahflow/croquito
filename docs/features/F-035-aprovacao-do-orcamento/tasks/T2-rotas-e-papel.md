# F-035 T2 — Montar deixa de publicar, e a assinatura vira a condição do despacho

feature_id: F-035
task_id: T2
parent_plan: ../plan.md
role: builder
depends_on: T1

## Goal

`POST .../estimate` passa a **só montar**. Assinar e despachar viram atos próprios, e o
despacho recusa fechado sem assinatura válida. Um papel novo, `aprovador`, assina — e quem
montou não assina, mesmo acumulando papéis.

## Leia antes de editar

- [`AGENTS.md`](../../../../AGENTS.md) na raiz e `services/api/AGENTS.md`.
- [ADR-0046](../../../adr/0046-aprovacao-do-orcamento-base.md) (`Accepted`) — decisões
  **2, 5, 6 e 7**.
- [ADR-0029](../../../adr/0029-runner-de-migrations-revisadas.md) — forward-only.
- [Feature contract](../feature.md), escopos 2, 3 e 4, e `Constraints`.

## O que a T1 já entregou

- `Estimate.approval`, `content_digest()` (que **exclui** a aprovação) e
  `export_errors()`/`ensure_exportable()` **sem parâmetro**.
- `schema_version` em `2.2.0`.

**Armadilha**: a T1 pôs o portão dentro de `run_export_estimate_workbook`, que é o
exportador do **CLI**. A API **não passa por ali** — ela chama `render_estimate_workbook`
(`estimate_rounds.py:1083-1103`). Você precisa invocar `ensure_exportable()` **na rota**,
antes de qualquer escrita, como a medição faz em `main.py:8948-8950`. Sem isso o CLI exige
assinatura e a rota não, e passam a existir duas verdades sobre o mesmo artefato.

## Scope

### 1. Migração `0015` e "quem montou"

A recusa de auto-aprovação precisa comparar o `sub` do JWT com **quem montou o orçamento da
cabeça**. `created_by` da revisão não serve: `append_revision` grava nele quem fez o
**último** ato, então depois de uma aprovação ele já não é quem montou.

Coluna nova em `estimate_round_revisions`, preenchida por quem monta e **carregada adiante**
pelos atos seguintes. Isso exige uma **terceira categoria** em `append_revision`
(`estimate_rounds.py:363-409`): hoje ele carrega JSON-documento (default `None`) e
JSON-mapa (default `{}`), e um escalar `str | None` não cabe em nenhuma.

As três alternativas já foram consideradas e **recusadas** — não as reabra: dentro do
`estimate_json` contaminaria o digest e os goldens e poria identidade no domínio; em
`artifact_refs_json` seria abusar de um campo cuja docstring diz que ele guarda chave de
objeto; e descobrir o autor comparando revisão com a pai é a arqueologia que a decisão 6 do
ADR recusou.

Migração forward-only no molde da `0014_reference_catalogs.py` (`downgrade()` levanta
`NotImplementedError`). A `0014` é a revisão de topo.

### 2. `POST .../estimate` passa a só montar

Handler em `main.py:10708-10832`. Hoje ele monta (10757), renderiza e audita (10771) e
**publica** (10772-10785) no mesmo ato. Auditoria e publicação **saem daqui** e vão para o
export — exatamente como `calc` faz na medição, que monta e não publica.

Grave também quem montou, na coluna nova.

**É quebra declarada de contrato de rota.** O snapshot de OpenAPI terá diff de **mudança**,
não só de adição, e isso é esperado.

### 3. `POST .../estimate/approve`

Molde: `main.py:8791-8889`. Corpo **só** `base_version` — `ApiModel` tem `extra="forbid"`,
então corpo com identidade recusa `422` sozinho, e a classe deve documentar por quê.

- Papel **`aprovador`**, antes de qualquer lookup.
- **Recusa de auto-aprovação**: `sub` do JWT igual a quem montou recusa com código estável,
  mesmo que a pessoa tenha os dois papéis. Sem isso o papel novo é cerimônia.
- Idempotência, `base_version`, revalidação antes de assinar, e a revisão nova **avança**
  `version` — aprovar é ato humano deliberado.
- Identidade e instante são do **servidor**.

### 4. `POST .../estimate/export`

Molde: `main.py:8891-9009`. Papel **`orcamentista`** — assinar é assumir o conteúdo,
despachar é operar o envio (ADR-0046, decisão 7).

Ordem obrigatória, e é o coração da feature:

1. portão do domínio (`ensure_exportable()`) — **antes de qualquer escrita**;
2. auditoria de round-trip (`render_estimate_workbook`, que já falha fechado);
3. só então `write_object` e a revisão nova.

O `.xlsx` passa a ser endereçado pelo **`content_digest()`**, não pelo
`document_digest(document)` de hoje (`main.py:10769`) — senão assinar mudaria o endereço da
planilha.

### 5. Estado e leitura

`GET .../estimate` ganha o bloco `approval` (`approved`, quem, quando, os dois digests,
`stale`), com `stale` **derivado na leitura, nunca gravado**. `round_state_payload`
(`estimate_rounds.py:1207-1288`) ganha o bloco no padrão `**target_state(...)` /
`**regime_state(...)`: bloco ausente é chave ausente.

Remontar **leva a assinatura anterior adiante**, já caduca — molde de
`carry_approval_forward` (`valuation_rounds.py:859-881`). Descartá-la apagaria em silêncio
o fato de que alguém assinou.

### 6. Papel `aprovador`

- Constante em `journeys.py` (ao lado de `VALUATION_REVIEWER_ROLE`, linha 45) e o papel
  entrando em `JOURNEY_ROLES["orcamento"]` — o aprovador precisa **abrir a jornada** para
  ver o que assina.
- As **11 leituras** de `/v1/estimate-rounds` aceitam os dois papéis; as **11 mutações**
  continuam exigindo `orcamentista`; `approve` exige `aprovador`.
- Realms `keycloak/croquito-realm.json` e `croquito-hml-realm.json` ganham o papel; o local
  ganha um usuário, no molde de `orcamentista.local`.

### 7. Documentação e snapshot

`API_CONTRACT.md`: as três rotas, e **remover a frase** que declara que aprovação não existe
deste lado da fronteira (`docs/architecture/API_CONTRACT.md:1192`, apontada pelo ADR).
`make openapi-snapshot`.

## Out of scope

- **Qualquer arquivo em `apps/web/`** — a tela é a T3.
- **Qualquer arquivo em `tests/e2e/`** — é a T4.
- Qualquer mudança na cadeia de medição.
- Mudar o domínio entregue pela T1.

## Acceptance criteria

1. Exportar sem aprovação válida recusa e **nada é escrito** — nem temporário, nem no object
   store. Provado por teste que confere o store depois da recusa.
2. **Quem montou não aprova**, mesmo com os dois papéis no token. **Este teste não tem molde
   na medição** — ela não segrega montar de assinar —, então nasce novo.
3. Corpo com identidade recusa `422`.
4. Remontar caduca a assinatura; exportar recusa até ato novo; o registro anterior continua
   legível.
5. Auditoria reprovada não publica nada e devolve só os códigos, nunca valor do cliente.
6. **Com só `aprovador`: as 11 leituras passam e as 11 mutações recusam.** Teste irmão de
   `test_sem_o_papel_toda_rota_recusa_antes_do_lookup`
   (`tests/api/test_estimate_round_routes.py:513`), que já enumera as 22 rotas. **É o
   critério que impede afrouxar uma mutação por engano** — o maior risco desta task.
7. Papel exigido antes de qualquer lookup nas rotas novas.
8. Baseline: `make check` e `make test` verdes antes e depois.

## Pitfalls

- **O portão da T1 não protege a rota.** Ver a armadilha no topo.
- `POST .../estimate` deixar de publicar quebra os e2e existentes — eles são da **T4**. Se
  `make test` reprovar só neles, **reporte** em vez de consertar: são de outra task, e
  arrumá-los aqui esconderia a quebra que a T4 precisa ver.
- O snapshot de OpenAPI é ato deliberado: regenere pelo alvo do Makefile.
- Erros de domínio são estruturados; não faça parsing de string de exceção.
- Logs e auditoria nunca carregam valor do cliente, chave de objeto ou URL assinada.
- Helper de teste existente: `_round_ready_for_estimate`
  (`tests/api/test_estimate_round_routes.py:1751-1785`) chega até "pronto para montar".

## Validation

```bash
make check
make test
uv run pytest tests/api/test_estimate_round_routes.py -q
```

## Report

Encerre com o `BUILD REPORT` completo do contrato do Builder — todos os campos presentes,
`none` onde não houver entradas. Se um portão reprovar em área que você não tocou, **pare e
reporte**; não conserte área alheia.
