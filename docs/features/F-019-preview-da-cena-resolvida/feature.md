# F-019 — Ver a cena resolvida antes de exportar

## Status

`BLOCKED`

> Registrada em 2026-08-19, por seleção humana, e **especificada em 2026-08-23** por seleção
> humana nova, junto da [F-018](../F-018-edicao-de-forma-da-proposta/feature.md).
>
> **Um gate humano** precede o planejamento — só o de design. Ao contrário das outras features
> abertas nesta rodada, esta **não** exige decisão de arquitetura: ela lê uma rota que já
> existe e desenha no cliente. Ver **Human Gates**.

## Classification

`INTERFACE_CHANGE` — a geometria resolvida passa a ser vista. Superfície nova.

## Priority

`HIGH` — é a última chance de ver o que vai ser exportado **antes** de aprovar, e hoje ela
não existe.

## Problem

Quando o traçado resolve, a revisão mostra **texto**. `TraceSolveResponse`
(`services/api/src/croquito_api/main.py:1027`) devolve `solve_status`, `blockers`,
`unapplied_reading_ids`, `residual_summary`, `exact_entity_count` e — desde a
[F-025](../F-025-consultor-do-tracado/feature.md) — `contested_spans` e `applied_spans`. Tudo
isso é diagnóstico preciso e **nada disso é o desenho**.

A pessoa aprova uma cena que nunca viu. O primeiro momento em que a geometria resolvida existe
como imagem é o **render do DXF**, no worker, depois do export — ou seja, depois da aprovação
que ela deveria ter informado.

E a cena está a uma chamada de distância: `GET /v1/jobs/{job_id}/scene` existe
(`main.py:6624`) e devolve o `SceneRevision` inteiro. **A SPA simplesmente não o busca** —
`apps/web/src/api.ts` não tem essa rota. Os tipos já estão gerados e publicados em
`@croquito/contracts` (`scene.generated.ts`), então o cliente já sabe a forma do dado.

Falta desenhar.

## Desired Outcome

Antes de aprovar, a revisora vê a cena resolvida: as entidades, na escala real, com a precisão
de cada uma visível — e vê o que o consultor do traçado já lhe diz por texto (vãos aplicados,
vãos em disputa) **em cima da geometria**, não numa lista ao lado dela.

## Scope

### Desenho no cliente, a partir da cena que a rota já devolve

SVG montado no navegador a partir do `SceneRevision` tipado. Sem rota nova, sem render no
servidor e sem imagem: a arquitetura é explícita em que a API "não renderiza PDF, não chama
modelos e não gera DXF no request path", e um preview de aprovação não é motivo para abrir
exceção.

### A precisão é o que o desenho tem de mostrar

Cada entidade carrega `precision` (`exact` | `derived` | `approximate` | `unresolved`), e é
essa distinção que decide se a cena pode ser exportada. Um preview que desenhe tudo igual
esconde exatamente o que a pessoa precisa julgar. **Cor nunca é o único indicador**: a
diferença aparece também em traço e em legenda escrita.

### O diagnóstico da F-025 sobre a geometria

`applied_spans` e `contested_spans` deixam de ser só lista: aparecem sobre o desenho, onde o
vão em disputa está. É o mesmo dado, no lugar onde ele significa alguma coisa.

### Escala e orientação declaradas

A cena é métrica com **Y para cima**; a tela é Y para baixo. O espelhamento é o mesmo que
`tracing.py` já aplica ("cota manda", Y espelhado), e o preview declara a escala com barra
gráfica — sem ela, um desenho sem cota não diz se aquilo tem 3 ou 30 metros.

## Out of Scope

- **Editar pelo preview.** Ver não é corrigir; corrigir forma é a
  [F-018](../F-018-edicao-de-forma-da-proposta/feature.md).
- **Render no servidor**, imagem gerada, ou reuso do render do DXF (`dxf.py`) — ver `Scope`.
- **Substituir o render do DXF** como prova. O auditor do export continua sendo quem prova que
  o arquivo está correto; este preview é leitura, não laudo.
- **Preview de cena não resolvida.** Sem traçado não há geometria métrica para desenhar, e
  desenhar propostas em pixels aqui confundiria os dois espaços.
- **Sobrepor a prancha** (a imagem da página sob o desenho) — ver Unknown 1.

## Acceptance Criteria

1. `make check` e `make test` verdes; goldens intocados.
2. Job sem traçado resolvido se comporta exatamente como hoje, e o preview declara que não há
   o que desenhar — estado honesto, não erro.
3. O desenho distingue as quatro precisões por **traço e legenda**, não só por cor — coberto
   por teste que lê a saída sem depender de cor.
4. `applied_spans` e `contested_spans` aparecem sobre a geometria, e um vão em disputa é
   visualmente distinguível de um aplicado.
5. A orientação está correta: uma cena com Y crescente para cima é desenhada sem espelhar o
   conteúdo — teste com fixture de geometria assimétrica, que é a única que pega inversão.
6. A escala é declarada e verificável: uma barra de escala cuja medida bate com a geometria.
7. Nenhuma chamada nova ao servidor além do `GET /v1/jobs/{job_id}/scene` que já existe.
8. A tela corresponde à revisão aprovada do Design Approval Package.

## Constraints

- `tenant_id` do JWT — a rota de cena já o exige, e nada muda.
- A SPA não resolve geometria: ela desenha o que recebeu. Nenhum cálculo de solver no
  navegador.
- Sem dependência nova de biblioteca de desenho sem revisão de licença e superfície de risco.
- O preview não pode parecer um entregável. Ele é leitura de trabalho, não a prancha.

## Dependencies

- `GET /v1/jobs/{job_id}/scene` e `@croquito/contracts` — ambos existem e não mudam.
- [F-025](../F-025-consultor-do-tracado/feature.md) — `applied_spans` e `contested_spans` vêm
  dela. Entregue, em `READY_FOR_HUMAN_REVIEW`.
- [F-011](../F-011-jornada-guiada-da-revisao/feature.md) — a jornada por etapas é onde o
  preview se encaixa. `DONE`.

## Unknowns

1. **A prancha aparece sob o desenho?** Sobrepor o render da página à geometria é o que mais
   ajuda a achar divergência — e exige registro entre o espaço de pixels e o métrico, que a
   calibração (`proposal_calibration.py`) tem, mas com incerteza própria. Um overlay
   desalinhado é pior que nenhum. Decisão de design, e sai no pacote.
2. **Em qual etapa da jornada ele vive?** Traçado, Aprovação, ou nas duas. Aprovação é onde a
   decisão acontece; Traçado é onde o resultado nasce.
3. **O que fazer com cena grande.** Uma praça inteira com muitas entidades pode ficar
   ilegível na largura do painel. Zoom e recorte são interação, e interação é pacote de
   design.

Nenhum destes é decisão de arquitetura: os três são de tela.

## Risks

- **Aprovar pelo preview.** O maior risco: se o desenho parecer o produto final, a pessoa
  aprova o desenho em vez de aprovar a cena. Mitigação: ele não imita a prancha, e o portão de
  exportação continua sendo `ensure_exportable()`, não o olho.
- **Falsa precisão visual.** Uma linha aproximada desenhada com o mesmo traço de uma exata
  mente sobre o que se sabe. Critério 3 existe por isso.
- **Inversão de eixo passar despercebida** numa geometria simétrica, e aparecer só na obra.
  Critério 5 exige fixture assimétrica.
- **Custo de manutenção de um segundo desenhista.** O produto já desenha no `dxf.py`; este é
  outro caminho de desenho, com outra tecnologia. Divergirem é questão de tempo — o preview
  não é laudo justamente por isso.

## Human Gates

1. **`DESIGN_APPROVAL_REQUIRED`** — Design Approval Package do preview, com os estados de cena
   vazia, cena resolvida, vão em disputa e cena grande, conforme
   [design-approval](../../engineering-os/workflows/design-approval.md).

**Não há `ARCHITECTURE_DECISION_REQUIRED`**, e isso é afirmação, não omissão: a feature não
cria rota, não muda modelo, não toca o portão de exportação e não introduz decisão durável de
arquitetura. Cumprido o gate de design, ela vai direto a `READY_FOR_PLANNING`.

## References

- [Roadmap](../../product/ROADMAP.md) — a linha da F-019
- [ADR-0005](../../adr/0005-canonical-scene-graph.md) — o scene graph como fonte geométrica
- `services/api/src/croquito_api/main.py:6624` — `GET /v1/jobs/{job_id}/scene`
- `packages/contracts/src/scene.generated.ts` — os tipos que o cliente já tem
