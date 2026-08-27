# F-019 · T2 — O componente e a leitura da cena

Feature: [F-019](../feature.md) · Plano: [plan.md](../plan.md) · Estado: **Entregue**

## Objetivo

Desenhar a cena resolvida na etapa de aprovação, com a precisão de cada entidade legível, e
ler a rota `GET /v1/jobs/{job_id}/scene` que a SPA já podia chamar e não chamava.

## Escopo

- `apps/web/src/CroquiApp.tsx` (`PreviewDaCena` e o efeito de leitura), `apps/web/src/api.ts`
  (`getScene`), `apps/web/src/styles.css`, `apps/web/src/CroquiApp.test.tsx`.

## Fora de escopo

- Qualquer mudança de servidor; qualquer rota nova; a prancha sob o desenho.
- Edição pelo preview — é a [F-018](../../F-018-edicao-de-forma-da-proposta/feature.md).

## Critérios de aceite

1. As quatro precisões distinguidas por traço **e** por texto, sem depender de cor.
2. Job sem traçado declara que não há o que desenhar, e não chama a rota.
3. Zoom, arrasto e enquadramento pela mesma interação da prancha.
4. Nenhuma chamada nova além de `GET .../scene`.

## Validação

`make check` = 0, `make test` = 0. Evidência renderizada do componente real em
[evidence.md](../evidence.md).

## Resultado

Entregue. Dois defeitos visuais achados na verificação renderizada e corrigidos antes do
commit: a escala cruzava o contorno e o texto ficava ilegível sobre a linha.
