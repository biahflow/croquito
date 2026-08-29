# F-047 · T8 — Evidência de navegador

Feature: [F-047](../feature.md) · Plano: [plan.md](../plan.md) · Estado: **Pendente**

## Objetivo

Provar, com as telas reais rodando contra o stack local, que a quantidade atravessa a fronteira
sem digitação e que a divergência aparece — `BROWSER_REQUIRED`, AC 11 do contrato.

## Escopo

- `docs/features/F-047-quantitativo-da-cena-aprovada/evidencia/` e `evidence.md`

## Fora de escopo

- Mudar código para facilitar a captura: se a tela não chegar ao estado, a tarefa **para e
  reporta**
- Dado real de cliente: croqui e legenda da captura são sintéticos

## Critérios de aceite

1. Capturas da tela real: a proposta, o ato de declarar, a quantidade chegando à medição sem
   digitação, a divergência com os dois números e o item bloqueado, e a resolução.
2. `evidence.md` amarra cada critério de aceite do contrato à evidência que o prova e declara o
   que **não** foi exercido.
3. O ambiente é derrubado ao fim; nenhum dado de outra sessão é apagado do banco local sem pedir.

## Validação

`uv run python scripts/check_docs.py` verde.
