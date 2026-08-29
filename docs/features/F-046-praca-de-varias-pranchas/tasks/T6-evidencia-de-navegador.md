# F-046 · T6 — Evidência de navegador

Feature: [F-046](../feature.md) · Plano: [plan.md](../plan.md) · Estado: **Pendente**

## Objetivo

Provar, com a tela real rodando contra o stack local, que a praça de várias folhas se comporta
como o pacote aprovado — `BROWSER_REQUIRED`, AC 12 do contrato.

## Escopo

- `docs/features/F-046-praca-de-varias-pranchas/evidencia/` (PNGs) e `evidence.md`

## Fora de escopo

- Qualquer mudança de código para facilitar a captura. Se a tela não chegar ao estado, a
  tarefa **para e reporta**.
- Dado real de cliente: a praça da captura é sintética.

## Critérios de aceite

1. Capturas da tela real: a praça com duas folhas, a navegação entre elas, o item repetido
   contando duas vezes, a declaração de identidade com a prévia, o total depois da fusão e a
   recusa por folha pendente.
2. `evidence.md` amarra cada critério de aceite do contrato à evidência que o prova, e declara
   o que **não** foi exercido.
3. O ambiente é derrubado ao fim; nenhum dado de outra sessão é apagado do banco local sem
   pedir.

## Validação

`uv run python scripts/check_docs.py` verde.
