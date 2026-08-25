# F-024 — Leitura com valor não morre por falta de target_hint

## Status

`DONE`

> Selecionada por decisão humana de 2026-08-20, diagnóstico da V16 do Guaxindiba
> medido no raw-store: a extração devolveu 27 leituras (24 legíveis), 13 cotas de
> chão em metros com valor — e 12 delas morreram no funil como
> `READING_{n}_INCOMPLETE` por falta de `target_hint`. O pacote abriu com 8
> leituras, todas recado, zero cota de chão.

> Corrigida e **commitada na `main`** em `7b15d1f` (funil de `provider_review.py`,
> testes e snapshot OpenAPI aditivo). A **entrega foi aceita em uso real**: com o funil
> consertado, a V17 do Guaxindiba extraiu 29 leituras (13 de chão), registrada em
> `35bf5fa` e no `STATUS.md`. Este flip apenas reconcilia o roadmap, que ficara em
> `READY_FOR_HUMAN_REVIEW` depois do commit.

## Classification

Não é `INTERFACE_CHANGE` — o campo já é opcional no tipo do web.

## Priority

`HIGH` — caminho crítico do DXF: sem cota de chão no pacote não há traçado.

## Problem

`provider_review.py:562` descarta leitura sem `target_hint` como INCOMPLETE. Mas o
`target_hint` é dica de contexto ("hipótese, não ID definitivo" — contrato do
prompt), e quem liga leitura a elemento é o revisor pela associação explícita, com
candidatos por proximidade de bbox (`association.py`) — o hint não participa. Uma
cota de chão solta no desenho não tem rótulo de elemento; o modelo omite o hint
com razão, e o pipeline joga fora número claro com valor e unidade.

## Desired Outcome

Leitura COM valor e sem hint entra no pacote (ambígua como qualquer outra), com
nota `READING_{n}_WITHOUT_TARGET_HINT` para o dado não se perder. Leitura sem
valor continua descartada como hoje. V17 do Guaxindiba abre com as cotas de chão.

## Scope

1. `DimensionReading.target_hint` opcional (`str | None = None`) em
   `services/worker/src/croquito_worker/review.py` (hoje `min_length=1`).
2. Funil em `provider_review.py`: o teste da linha 562 separa valor (continua
   fatal) de hint (vira nota + leitura entra com `target_hint=None`).
3. Testes em `tests/worker/test_providers.py`; snapshot OpenAPI (mudança mecânica
   de nullable); docs `PROMPT_CONTRACTS.md` e `API_CONTRACT.md` dizendo a regra.

## Out of Scope

- `transcription.py` (caminho paralelo de demo/CLI, razão `missing_target_hint`
  própria — alinhamento fica anotado, não feito aqui).
- Web (o tipo `target_hint?` já é opcional; nenhuma tela quebra com ausência).
- Mudar prompt/contrato do provider.

## Acceptance Criteria

1. `make check` e `make test` verdes.
2. Teste novo: leitura `length` com valor e sem hint entra no pacote com
   `target_hint is None` e a nota nova; sem valor continua fora com a nota atual.
3. Retrocompatibilidade: pacote persistido com hint continua validando.
4. Snapshot OpenAPI: mudança de nullable apenas.

## Human Gates

Aprovação do plano (concedida na seleção, 2026-08-20); deploy é a esteira.
