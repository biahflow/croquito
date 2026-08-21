# F-029 / T6 — Tier de anotação automática (ADR-0044)

- Feature: [F-029](../feature.md) · ADR: [0044](../../../adr/0044-triagem-por-testemunha-anotacao-automatica.md) (Accepted 2026-08-21)
- Papel: builder · Esforço: S/M · Depende de: T4, T5 (integradas)
- Gate de entrada satisfeito: ADR-0044 aceito por ato humano em 2026-08-21.

## Objetivo

Com a dupla chave ligada, leitura de testemunha única SEM papel de geometria
de planta (kind `height`, ou sinal `note` do provider — F-021) e com
`association_confidence` do candidato escolhido acima do corte entra
auto-confirmada E associada (tier "anotação automática"). `reading_confidence`
dispensada neste tier. Cota de planta NUNCA entra por ele. Proveniência,
auditoria, resposta e tela distinguem os dois tiers.

## Escopo

1. `auto_association.py`: elegibilidade do tier 2 (kind height OU sinal note
   do provider — localizar o campo da F-021 no `DimensionReading`,
   review.py:~173); decisão de sistema idêntica à do tier 1 exceto a `note`,
   que nomeia o tier ("anotação automática…") e as confianças; associação
   explícita gravada como no tier 1. `AutoDecision` ganha campo `tier:
   Literal["cota","anotacao"]` (aditivo) — viaja no shadow
   (`auto_decisions`) e na auditoria.
2. `dxf.py`: `AutoDecidedReadingAudit` com o tier; `auditoria.json` separa
   as listas ou carrega o campo por item.
3. Tela (padrões da T5): contador novo "anotações automáticas" na
   `ExceptionsBand` quando houver; badge da linha distingue
   "⚙ anotação automática" de "⚙ associada pelo sistema" (texto, não só
   cor). Tipos/labels aditivos.
4. Testes: tier 2 nunca decide leitura de planta (teste de não-vazamento
   com length de alta associação e baixa leitura); height de testemunha
   única com associação acima do corte entra; height com associação fraca
   NÃO entra; tier 1 bit a bit inalterado (mesmos casos da T4 passam sem
   edição); auditoria e resposta carregam o tier; contador da tela.

## Fora de escopo

Forma máxima (cota estacionada — recusada no ADR-0044); mudança de kind;
qualquer mudança com flag desligada; threshold próprio por tier (o corte é
um só, do ADR-0041 D5).

## Validação (comandos reais)

```bash
make check
uv run pytest tests/worker/test_auto_association.py tests/api tests/e2e/test_full_flow.py
npm --workspace @croquito/web run test -- --run
make test
```

## Baseline e relatório

`main` com T1–T5 integradas (working tree não commitada, com trabalho de
outras sessões — preservar; não commitar). Encerrar com BUILD REPORT
completo (`docs/engineering-os/agents/builder.md`).
