# F-044 T3a — O precedente na shortlist, e o aceite do pacote numa revisão só (API)

- **feature_id**: F-044
- **task_id**: T3a
- **role**: builder
- **depends_on**: [T1, T2]
- **required_capabilities**: READ, WRITE (`services/api`, `tests/api`), VALIDATE
- **risk**: MÉDIO-ALTO — mexe no `GET` da shortlist, que tem invariantes de custo, e na rota de decisão, que é ato humano.
- **relative_effort**: M

## Gates cumpridos

Human Gate 1 (medir a repetição) **cumprido em 2026-08-28**: a hipótese se confirmou. Design
Approval Package revisão 1 **aprovado** — e é ele que especifica esta superfície. Leia
[`../mock/README.md`](../mock/README.md) e o HTML ao lado antes de começar; as sete decisões
dele valem como requisito.

O índice já existe (T2): `precedents.precedents_for(session, tenant_id, labels, price_source)`
devolve, por rótulo normalizado, os códigos e a **contagem de praças distintas**.

## Scope

### 1. O precedente no payload da shortlist

`GET /v1/estimate-rounds/{round_id}/code-suggestions` ganha um bloco novo. Ele **não pode**
mudar o que já existe: `suggestions` continua igual, na mesma ordem, com os mesmos blocos por
fonte de preço.

```json
{"...": "campos de hoje, intocados",
 "precedents": [
   {"item_id": "ti_...",
    "normalized_label": "piso em concreto",
    "worksite_count": 4,
    "codes": [{"code": "BP09100050(B)", "worksite_count": 4,
               "description": "...", "unit": "m2", "unit_price": "118.42",
               "unit_compatible": true, "catalog_sha256": "..."}]}]}
```

Regras, todas exigidas:

- **O `GET` continua sem pagar nada e sem avançar a versão da rodada** (ADR-0054 D7). A
  consulta ao índice é leitura de banco; nenhuma chamada de provider entra neste caminho.
- **A fonte de preço é a da rodada**, e precedente de outra fonte nunca é devolvido — a T2 já
  garante isso na consulta; não contorne passando outra fonte.
- **Código do precedente que não está no catálogo da cascata desta rodada é OMITIDO**, e a
  omissão não derruba o resto do bloco. É a decisão 7 do pacote: *"sugerir código que não
  existe na tabela vigente é o pior resultado possível — pior que não sugerir nada"*. Se todos
  os códigos de um rótulo saírem, **o item não aparece em `precedents`** (bloco vazio não
  existe, decisão do pacote).
- `description`, `unit`, `unit_price`, `unit_compatible` e `catalog_sha256` vêm do **catálogo
  da cascata**, exatamente como os candidatos da shortlist os trazem — a tela desenha o mesmo
  cartão, e o índice só guarda o código.
- `worksite_count` do rótulo e de cada código: o do rótulo é quantas praças usaram aquele
  rótulo; o do código, quantas usaram aquele código. A tela mostra o do rótulo no cabeçalho.
- Item sem precedente simplesmente não entra na lista.

### 2. O aceite do pacote numa revisão só

`POST /v1/estimate-rounds/{round_id}/code-assignments/decisions` passa a aceitar, além da
decisão de hoje, **um lote de códigos para o mesmo item**:

```json
{"base_version": 12, "item_id": "ti_...", "action": "confirm",
 "codes": ["BP09100050(B)", "ET39050109(/)"],
 "catalog_sha256": "..."}
```

> **Correção de 2026-09-04.** O corpo escrito aqui **omitia `catalog_sha256`**, e a
> [T3b](T3b-precedente-na-shortlist-tela.md) copiou a omissão. A rota, implementada, manteve a
> exigência da fonte em **toda** confirmação — que é o certo, e é o que o
> [API Contract](../../../architecture/API_CONTRACT.md) diz —, então o aceite em lote da tela
> voltava `422` e nada gravava. Ninguém atravessou a fronteira até a evidência de navegador.

- `codes` é **mutuamente exclusivo** com `code`; os dois juntos, ou nenhum dos dois numa
  confirmação, é recusa de fronteira (`422`), no molde das validações que a rota já tem.
- `catalog_sha256` é **obrigatório na confirmação**, lote incluído: os N códigos citam a MESMA
  fonte, e sem citação a rota recusa (`422`). Ele não é exclusivo com nada.
- `codes` só vale para `action: "confirm"`. Com `reject`, é recusa.
- Os N códigos entram numa **revisão só**, pelo `CodeAssignmentBatch` que o domínio já tem
  (`assignment.py:1008-1020`) — **não** faça N chamadas internas nem N revisões.
- Lista vazia, código repetido dentro do lote, e as recusas que já existem (código fora do
  catálogo, unidade incompatível, item já decidido, item não confirmado no takeoff) continuam
  sendo do **domínio** — a rota não as reimplementa.
- **O fechamento do pacote continua sendo ato separado** (decisão 5 do pacote): aceitar o
  precedente não fecha o pacote. Não acrescente `closures` a este caminho.

Como o fechamento é que alimenta o índice (T2), aceitar o precedente e depois fechar o pacote
grava a observação normalmente — nada a fazer aqui além de não atrapalhar.

### 3. Testes

- a shortlist devolve o precedente com a contagem de praças, e **os blocos por fonte
  continuam idênticos** aos de antes (teste que compara o resto do payload);
- o `GET` não avança versão e não grava;
- código do precedente fora do catálogo da cascata é omitido; se todos saírem, o item não
  aparece;
- precedente de outra fonte de preço não é devolvido;
- rótulo inédito não aparece;
- aceite de lote grava os N códigos em **uma** revisão (confira o `version` avançando uma vez
  só, e o conteúdo da revisão com os N pares);
- `codes` com `reject` recusa; `codes` junto com `code` recusa; lote vazio recusa;
- `base_version` defasada é `409` e não grava;
- as recusas de domínio continuam valendo dentro do lote (um código inválido derruba o lote
  inteiro — falha fechada, nada gravado pela metade);
- **precedente nunca vira decisão sem o ato**: um teste que prova que o `GET` não cria
  assignment nenhum.

## Out of Scope

- `apps/web` (é a T3b, em worktree paralela).
- `suggestions.py`, `assignment.py`: **não toque**. O precedente antecede a shortlist, não a
  substitui, e a ordem instalada por fonte não muda.
- Limiar de confiabilidade (unknown 3) — a API devolve a contagem e não julga.

## Acceptance Criteria

1. `precedents` chega no payload sem mudar nada do que já estava lá.
2. O `GET` continua gratuito e sem efeito colateral.
3. Código fora do catálogo vigente nunca é oferecido.
4. O aceite do pacote grava os N códigos numa revisão só.
5. Aceitar o precedente **não** fecha o pacote.
6. Nenhum teste existente afrouxado.

## Validation

```bash
cd /Users/danielcampos/workspace/daniel/croquito-f044-api
uv run pytest tests/api -q
make check
make test
```

## Armadilhas verificadas

- `CodeAssignmentDecisionRequest` (`main.py:1821-1842`) tem `extra="forbid"`: campo novo entra
  no modelo, e o carimbo de identidade continua vindo do `Principal`, nunca do corpo.
- O drift guard `test_os_testes_de_papel_percorrem_toda_a_superficie_de_estimate_rounds` é
  ponto de extensão projetado; rota nova entra nas listas. Aqui não há rota nova — só campos.
- Rótulo de legenda nunca em log estruturado.
- Rota alterada exige `docs/architecture/API_CONTRACT.md` e `make openapi-snapshot`.
