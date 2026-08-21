# F-029 / T2 — Shadow log persistido e exposto na resposta de review

- Feature: [F-029](../feature.md) · Plano: [plan.md](../plan.md)
- Papel: builder · Esforço relativo: S · Depende de: T1

## Objetivo

Toda revisão de review grava o shadow log (o que teria sido auto-decidido em
cada threshold da grade) e a resposta de review expõe, como campos
observacionais, as confianças por leitura/candidato, o shadow e as métricas
`auto_association_rate`/`review_rate`. Nenhuma decisão é tomada; nenhuma rota
muda de comportamento.

## Fontes a ler antes de editar

- `AGENTS.md` (raiz) e `services/api/AGENTS.md`.
- `services/api/src/croquito_api/database.py` — `ReviewRevisionRecord`
  (145-191): colunas JSON existentes (`packet_json`, `associations_json`,
  `declared_chains_json` 165-172 com o padrão "resultado não gravado,
  recomputado").
- `services/api/src/croquito_api/migrations/versions/0006_review_declared_chains.py`
  — molde da migração aditiva (coluna JSON, `nullable=False`,
  `server_default`, `downgrade()` levanta `NotImplementedError`, docstring
  ADR-0029). Próximo número livre: **0007**.
- `services/api/src/croquito_api/main.py` — `ReviewResponse` (554-588) e o
  precedente de replay idempotente da F-023 (567-575: `default_factory=list`
  para respostas gravadas antes dos campos existirem).
- `tests/api/test_api.py` — testes da F-023 como molde, em especial
  `test_idempotent_replay_of_a_response_stored_before_the_chain_fields`
  (linha ~2265).

## Escopo

1. Migração `0007_review_confidence_shadow.py`: coluna JSON aditiva em
   `review_revisions` (ex. `confidence_shadow_json`), padrão do 0006;
   forward-only.
2. Cômputo na gravação da revisão (mesmo ponto que monta
   `suggested_chains`): confidências via T1 + `shadow_decisions` sobre uma
   grade fixa de thresholds nomeada em constante.
3. `ReviewResponse` ganha campos observacionais com `default_factory` (replay
   de resposta idempotente gravada antes dos campos não quebra):
   confidências por leitura e por candidato, shadow por threshold,
   `auto_association_rate` e `review_rate` da revisão corrente.
4. `make openapi-snapshot` deliberado; `docs/engineering/API_CONTRACT.md`
   atualizado se o documento listar campos de review.
5. Testes: resposta traz os campos; replay idempotente pré-campos; shadow
   não altera decisões, blockers, cena nem export; migração na cadeia
   (`tests/api/test_migrations.py`).

## Fora de escopo

Qualquer decisão automática; flag; tela; eval; mudança em rotas existentes
além dos campos aditivos; mudança no scene schema (`make contracts` não deve
ser necessário — se parecer necessário, parar e reportar).

## Critérios de aceite

1. Revisão nova grava shadow; revisão antiga sem a coluna preenchida continua
   legível (campo vazio, nunca erro).
2. Campos observacionais idênticos entre duas leituras da mesma revisão
   (determinismo fim a fim).
3. `blockers`, decisões e export bit a bit como antes.
4. Snapshot OpenAPI regenerado deliberadamente; drift zero no `make check`.

## Baseline

`main` com T1 integrada, portões verdes. Falha nova em área não tocada:
parar e reportar.

## Validação (comandos reais)

```bash
make check
uv run pytest tests/api
make test
```

## Gates e relatório

Nenhum gate humano dentro desta task. Encerrar com `BUILD REPORT` completo
(`docs/engineering-os/agents/builder.md`).
