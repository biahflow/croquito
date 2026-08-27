# F-019 — Evidência

Feature: [Ver a cena resolvida antes de exportar](feature.md)  
Estado: `DONE`  
Data: 2026-08-27

## Gates humanos

| Gate | Estado |
| --- | --- |
| `DESIGN_APPROVAL_REQUIRED` | ✅ **Aprovado por ato humano em 2026-08-27**, revisão 1 ([mock/README.md](mock/README.md)) |
| `ARCHITECTURE_DECISION_REQUIRED` | não se aplica — a feature não cria rota, não muda modelo e não toca o portão de exportação |

## O que foi entregue

| Arquivo | O que é |
| --- | --- |
| `apps/web/src/scenePreview.ts` | Toda a aritmética: espelhamento do Y, enquadramento, zoom/recorte, barra de escala, contagem por precisão e a posição dos vãos. Puro, sem React. |
| `apps/web/src/scenePreview.test.ts` | 21 testes, incluindo a fixture **assimétrica** que é a única capaz de pegar inversão de eixo |
| `apps/web/src/CroquiApp.tsx` | Componente `PreviewDaCena` e a busca da cena, disparada só quando a etapa de aprovação está aberta |
| `apps/web/src/CroquiApp.test.tsx` | 6 testes de render estático do componente |
| `apps/web/src/api.ts` | `getScene` — a rota `GET /v1/jobs/{job_id}/scene` que já existia e a SPA não chamava |
| `apps/web/src/styles.css` | Os quatro traços de precisão, cotas, faixa de disputa, escala e estados sem desenho |

**Nenhuma rota nova, nenhuma mudança de servidor, nenhuma dependência nova.** O diff é
inteiramente de cliente, como o contrato exige.

## Critérios de aceite

| # | Critério | Como foi verificado |
| --- | --- | --- |
| 1 | `make check` e `make test` verdes; goldens intocados | `make check` = 0, `make test` = 0 (2546 pytest, 1236 vitest web, 261 field). Nenhum golden tocado. |
| 2 | Job sem traçado se comporta como hoje e declara que não há o que desenhar | `PreviewDaCena` com `estado="sem-cena"` — teste de render e captura [`preview-sem-cena.png`](evidencia/preview-sem-cena.png); o efeito nem chama a rota nesse caso |
| 3 | As quatro precisões distinguidas por **traço e legenda**, não por cor | `PRECISOES_NO_DESENHO` carrega nome e descrição do traço; teste lê os quatro nomes E os quatro traços no markup, e afirma que nenhuma cor viaja no HTML (`stroke=`/`fill=` ausentes) |
| 4 | `applied_spans` e `contested_spans` sobre a geometria, distinguíveis | `vaosAplicadosDesenhados` ancora a cota em `start_m`/`end_m`; `vaosEmDisputaDesenhados` produz faixa de eixo. Testes cobrem os dois e a captura mostra a diferença. |
| 5 | Orientação correta, provada com geometria assimétrica | `scenePreview.test.ts` usa um "L" e afirma que o trecho alto da cena (y = 6) tem o **menor** Y no desenho |
| 6 | Escala declarada e verificável | `barraDeEscala` escolhe medida redonda até ¼ da largura visível e acompanha o zoom; três testes, incluindo a escrita com vírgula |
| 7 | Nenhuma chamada nova além do `GET .../scene` | O único acréscimo em `api.ts` é `getScene`; nenhuma outra rota foi criada ou chamada |
| 8 | A tela corresponde à revisão aprovada do pacote de design | Comparação entre [`mock/01-cena-resolvida.png`](mock/01-cena-resolvida.png) e a captura do componente real, abaixo |

## Validação de navegador/runtime

Classificação: **`BROWSER_REQUIRED`** — superfície visual nova.

A evidência abaixo é do **componente real** com a **folha de estilo real**, renderizado e
capturado em Chromium (não é o mock):

| Captura | Estado |
| --- | --- |
| [`preview-renderizado.png`](evidencia/preview-renderizado.png) | Cena resolvida com as quatro precisões, dois vãos aplicados, um vão em disputa, barra de escala e seta `Y+` |
| [`preview-sem-cena.png`](evidencia/preview-sem-cena.png) | Job sem traçado resolvido |

Dois defeitos foram achados **nessa** verificação e corrigidos antes do commit: a barra de
escala e a seta do eixo cruzavam o contorno (foram para a margem do enquadramento), e o
texto do desenho ficava ilegível ao cruzar uma linha (ganhou halo por `paint-order`).

## Desvios e limitações declaradas

- **`contested_spans` não têm posição.** `ContestedSpanOut` declara eixo, valores e
  leituras, e não `start_m`/`end_m`. A disputa é desenhada como **faixa do eixo**, e a
  tela diz por escrito que a posição não é declarada pelo servidor. Desenhá-la num ponto
  exato inventaria o dado que falta; posicioná-la de verdade seria mudança de contrato da
  API, e portanto outra feature.
- **Texto e cota da cena não são desenhados.** Reproduzi-los faria o preview imitar a
  prancha, que é o risco central que o contrato nomeia.
- **A prancha sob o desenho** continua fora de escopo, como o contrato já dizia; o pacote
  de design registra a condição para ela virar real.

## Riscos remanescentes

- Cena com muitas entidades ainda não foi medida em desempenho: o zoom é por `viewBox` e
  não redesenha o dado, mas o número de nós SVG cresce com a cena.
- O preview é um **segundo desenhista** ao lado do `dxf.py`; divergirem é questão de
  tempo, e é por isso que ele não é laudo — o portão continua sendo `ensure_exportable()`.

## Integração

| Fato | Referência |
| --- | --- |
| PR mergeado na `main` | [#105](https://github.com/biahflow/croquito/pull/105), commit `80d251d` |
| `deploy-hml` da revisão | `success` em 2026-08-27 |
| Aceite | **ato humano de Daniel Campos, 2026-08-27** |

## O que o aceite NÃO cobre

- O preview ainda não foi usado para **decidir** uma aprovação numa rodada real; o aceite é da
  entrega, não de uma sessão de trabalho com ele.
- Desempenho com cena de muitas entidades continua sem medição.
