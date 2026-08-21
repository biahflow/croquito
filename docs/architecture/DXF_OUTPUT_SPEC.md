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
