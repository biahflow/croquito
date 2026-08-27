# F-019 · T1 — Aritmética do desenho

Feature: [F-019](../feature.md) · Plano: [plan.md](../plan.md) · Estado: **Entregue**

## Objetivo

Toda a matemática do preview num módulo puro, testável sem React: espelhamento do Y,
enquadramento, zoom/recorte, barra de escala, contagem por precisão e a posição dos vãos.

## Escopo

- `apps/web/src/scenePreview.ts` e `apps/web/src/scenePreview.test.ts`.

## Fora de escopo

- SVG, evento de ponteiro, CSS e qualquer chamada de rede — são da T2.
- Reuso de `orcamento/prancha.ts`: aquele módulo enquadra imagem em pixels de página; este,
  geometria em metros com Y espelhado. A convenção do repositório já é ter a aritmética de
  viewport por jornada.

## Critérios de aceite

1. O espelhamento acontece em **um** lugar (`pontoDoDesenho`), e o teste usa fixture
   assimétrica para provar que o alto da cena vira o alto da tela.
2. Texto e cota da cena não viram forma desenhável.
3. Barra de escala é medida redonda, acompanha o zoom e escreve com vírgula.
4. Vão aplicado ancora em `start_m`/`end_m`; vão em disputa não recebe posição ao longo do
   eixo.
5. Cena degenerada (altura zero) continua desenhável.

## Validação

`npm --workspace @croquito/web run test -- src/scenePreview.test.ts` — 21 testes verdes.

## Resultado

Entregue. Nenhum desvio.
