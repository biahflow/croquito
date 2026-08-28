# F-047 · T2 — O ato humano de identidade na revisão

Feature: [F-047](../feature.md) · Plano: [plan.md](../plan.md) · Estado: **Pendente**

## Objetivo

Permitir que um humano declare, na revisão, que um conjunto de traços é um elemento — com autor,
instante e registro, no mesmo idioma dos outros atos declarados do produto.

## Escopo

- `services/api/src/croquito_api/main.py` (rota da declaração) e o modelo de decisão
- `services/worker/src/croquito_worker/review.py` se a decisão couber ao pacote de revisão
- migração, se a declaração precisar de persistência própria
- `tests/api/`

## Fora de escopo

- Proposta assistida (T6) — aqui a declaração é sempre manual
- Qualquer inferência automática de identidade

## Critérios de aceite

1. A declaração registra autor (do JWT, nunca do body), instante com fuso e as entidades que
   passam a compartilhar o `element_ref`.
2. Declarar sobre cena **aprovada** não muda a cena aprovada: a declaração cria revisão nova,
   como todo ato do produto.
3. Identidade declarada é reversível por outro ato declarado, também registrado — nunca por
   edição silenciosa.
4. `Idempotency-Key` e `base_version` como nas demais mutações; erro em
   `application/problem+json` com código estável.
5. Snapshot de OpenAPI aditivo.
6. Sem declaração nenhuma, todo o caminho da revisão responde como hoje.

## Validação

`uv run pytest tests/api` verde; `make check` verde.
