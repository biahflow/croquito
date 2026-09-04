# Especificação de saída DXF

Status: Accepted for MVP  
Responsável: CAD / Geometry Engineering  
Última revisão: 2026-08-10

## Formato

- DXF R2018.
- Encoding UTF-8.
- Model space 2D.
- Unidade interna: metros.
- Header `$INSUNITS = 6`.
- Origem local documentada no audit report.

## Mapeamento de entidades

| Scene entity | DXF entity | Condição |
|---|---|---|
| line | `LINE` | segmento isolado |
| polyline/polygon | `LWPOLYLINE` | polygon usa closed flag |
| circle | `CIRCLE` | centro e raio determinados |
| arc | `ARC` | centro, raio e ângulos determinados |
| organic curve | `SPLINE` | somente approximate/revisada |
| text/note | `TEXT` ou `MTEXT` | conforme multiline |
| measurement | `DIMENSION` | quando associação geométrica é válida |
| diameter dimension | `DIMENSION` diametral (⌀) | círculo determinado por cota confirmada de raio/diâmetro |
| symbol | `INSERT` | block versionado existente |

Uma curva não deve ser transformada em arco/círculo apenas por aparência. Splines
usam o mínimo de control points que preserva a forma aceita.

## Layers

| Layer | Uso |
|---|---|
| `CONTORNO` | limite geral |
| `CAMPO` | linhas esportivas |
| `QUADRA` | quadras |
| `MURO` | muros |
| `ALAMBRADO` | alambrados |
| `PORTAO` | portões |
| `PATAMAR` | patamares/pisos |
| `EQUIPAMENTOS` | blocos e equipamentos |
| `COTAS` | dimensions |
| `TEXTOS` | notas |
| `DETALHES` | desenhos auxiliares |
| `APROXIMADO` | geometria aceita sem exatidão |
| `REVISAO` | itens não exportáveis por padrão |

Cores e lineweights são defaults do produto, não alegações de conformidade
automática com norma. Templates por cliente ficam fora do MVP.

Uma exceção declarada em `APROXIMADO`: quando as entidades de um mesmo `element_ref` cairiam
em camadas diferentes, o traçado desenha o elemento inteiro nessa camada para respeitar a
invariante de camada única por elemento — inclusive a entidade `exact` do grupo, que é a
direção conservadora (o contrário promoveria traçado de pixel a camada semântica). A camada
diz onde desenhar; quem declara exatidão é `precision`, que continua no XDATA de cada
entidade, e a cena carrega a `Issue` `ELEMENT_LAYER_HARMONISED`
([Estágio de traçado](TRACE_STAGE.md)).

## Provenance

O DXF inclui XDATA no application registry `CROQUITO` para:

- entity UUID.
- scene revision UUID.
- precision.
- provenance summary code.

O nome do registry acompanhou o rebranding de 2026-08-14 e é mudança de formato de saída:
arquivo exportado a partir dessa data declara `CROQUITO`, e os publicados antes dela
continuam declarando o nome anterior, sem migração
([ADR-0024](../adr/0024-rebranding-to-croquito.md)).

Nenhum texto bruto de cliente ou resposta de modelo entra em XDATA. O relatório
JSON guarda detalhes protegidos no pacote do usuário.

## Auditoria obrigatória

Antes da publicação:

1. Reabrir arquivo com `ezdxf`.
2. Executar auditor interno e rejeitar erros não corrigíveis.
3. Verificar header e units.
4. Verificar layer allowlist.
5. Verificar finite coordinates e extents plausíveis.
6. Verificar fechamento e auto-interseção de polígonos que exigem área.
7. Comparar dimensões confirmadas com geometria exportada.
8. Renderizar PNG do próprio DXF.
9. Gerar digest SHA-256.

## Pacote

```text
project-name/
  project-name.dxf
  preview.png
  auditoria.json
  quantitativos.csv
  hipoteses.json
  aprovacao.json # quando o pacote deriva de revisão profissional
```

`quantitativos.csv` traz `entity_id, layer, kind, precision, length_m, perimeter_m,
area_m2` de sempre. A coluna `element_ref` (ADR-0058) é **aditiva**: só aparece quando
alguma entidade exportável da cena declarou identidade de elemento — um croqui sem
nenhuma sai byte a byte igual ao de antes desse campo existir. Quando aparece, fica ao
lado de `entity_id`, nunca no lugar dele.

A grandeza que cada tipo de geometria contribui: `line` e polilinha **aberta** produzem
só `length_m` (soma euclidiana dos segmentos, no caso da polilinha); polilinha
**fechada** e `circle` produzem só `perimeter_m`/`area_m2`. Polilinha aberta não fecha
região — um muro ou alambrado traçado sem retorno ao ponto inicial nunca ganha
`perimeter_m`/`area_m2`, porque inventar área a partir de um traço aberto seria
geometria fabricada (F-047 T3b). Spline e arco continuam sem produzir grandeza nenhuma.

Regra de agrupamento: entidades exportáveis que compartilham o mesmo `element_ref` viram
**uma linha só**. `entity_id` passa a listar, em ordem de string (não a ordem de
iteração da cena), os IDs das entidades que compõem a linha; `kind` segue a mesma regra
quando o grupo mistura tipos. As grandezas somam por tipo — comprimentos com
comprimentos, perímetros com perímetros, áreas com áreas — nunca cruzando tipos; uma
coluna sem nenhuma contribuição no grupo continua vazia, como hoje. A precisão da linha
agrupada é a **pior** entre as entidades que a compõem, na ordem `exact > derived >
approximate > unresolved`: agrupar nunca promove precisão. Entidade sem `element_ref`
continua produzindo uma linha por entidade, como sempre produziu.

`auditoria.json` registra revision, exporter version, checks, units, entity counts e
digest. Quando alguma cota entrou sem toque humano (modo automático local da F-029,
[ADR-0041](../adr/0041-decisao-de-ator-maquina-atras-de-flag-local.md)), ele ganha
`auto_decided_readings`: a lista **nominal** dessas cotas, cada uma com leitura, valor,
unidade, associação usada, as duas confianças, o corte vigente, a versão do score e o
`tier` por qual regra ela entrou (`cota`, de dupla testemunha, ou `anotacao`, de
testemunha única para leitura sem papel de geometria de planta —
[ADR-0044](../adr/0044-triagem-por-testemunha-anotacao-automatica.md)). Quem confere o
pacote precisa distinguir os dois: o que se aceita de um rótulo não é o que se aceita de
uma medida. No tier `anotacao`, `proposal_id` é nulo — a anotação entra sem elemento
associado, e o que fica registrado é o `probable_proposal_id`, observação que instruiu a
fixação do texto e nunca um vínculo. A chave não aparece quando não houve nenhuma — e uma auto-decisão retificada
por uma pessoa sai da lista, porque deixou de ser automática. Nada disso muda o portão
`export_errors()`: a listagem é auditoria, nunca permissão.
`hipoteses.json` lista apenas aproximações aceitas e omissões.
`aprovacao.json` liga a decisão humana à revisão rascunho e registra os checks
de evidência, geometria e limitações. Fixtures antigas sem etapa de revisão podem
produzir somente os cinco artefatos-base.

## Rejeições

- NaN/infinite coordinate.
- Entity fora da layer allowlist.
- Exact entity sem provenance.
- Confirmed dimension incompatível.
- Self-intersection em área fechada.
- Unresolved entity marcada para export.
- Auditor `ezdxf` com erro estrutural.
