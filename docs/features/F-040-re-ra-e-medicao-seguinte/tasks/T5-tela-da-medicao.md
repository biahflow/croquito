# F-040 · T5 — A tela: declarar a RE-RA e abrir a medição seguinte

Feature: [F-040](../feature.md) · Plano: [plan.md](../plan.md) · Estado: **Planejado**

## Objetivo

Levar à tela da medição as duas jornadas aprovadas no Design Approval Package: declarar a
RE-RA na abertura e abrir a medição seguinte a partir da anterior, com a prévia contratado →
vigente → saldo antes de gravar.

## Escopo

- `apps/web/src/medicao/` (`MedicaoApp.tsx`, `api.ts` e componentes).
- Tipos gerados de `@croquito/contracts` (após `make contracts`), nunca escritos à mão.
- `apps/web` testes de componente.

## Fora de escopo

- Copy final; números/nomes/datas das capturas (sintéticos); layout impresso da planilha.

## Critérios de aceite

1. As duas portas da abertura aparecem juntas; a rodada anterior entra na lista com o selo de
   aprovada, e a não aprovada não entra, com o motivo dito no lugar da escolha (mock,
   decisões 1 e 3).
2. O período não é digitado — é calculado da rodada anterior e mostrado (mock, decisão 2).
3. A prévia mostra o efeito código a código antes de gravar; o vigente aparece como resultado
   de uma conta visível, sem campo onde escrevê-lo (mock, decisão 6).
4. O selo "re-ratificada" nunca depende só de cor; a linha continua legível em preto e branco
   (mock, decisão 9). Edições são operations allowlisted com `base_version`.
5. Classificação de validação `BROWSER_REQUIRED`: evidência renderizada da tela real
   (`browser-runtime-validation` do EngineeringOS), gravada em `evidence.md`.

## Validação

`npm --workspace @croquito/web run test` verde; `make check` (build web + drift) verde;
evidência de navegador registrada.
