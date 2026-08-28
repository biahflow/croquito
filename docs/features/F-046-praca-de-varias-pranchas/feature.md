# F-046 — A praça de várias pranchas

## Status

`READY_FOR_PLANNING`

> Registrada em 2026-08-28, por seleção humana, a partir da
> [issue #101](https://github.com/biahflow/croquito/issues/101). O
> [ADR-0057](../../adr/0057-multiplas-pranchas-por-praca-na-extracao-de-legenda.md) foi
> **aceito por ato humano em 2026-08-28**, com os quatro pontos confirmados sem emenda: o
> pacote continua por prancha com um consolidado acima; item repetido entre folhas são dois
> itens até declaração humana; a identidade que atravessa a praça é `(plate_id, item_id)`; e o
> consolidado falha fechado com qualquer folha pendente.
>
> Falta o `DESIGN_APPROVAL_REQUIRED` antes do plano — a praça de várias folhas é jornada nova
> na tela.

## Classification

`INTERFACE_CHANGE` — hoje a tela da medição é de **uma** prancha: um `<img>`, um overlay, uma
`plate_id` no texto (`apps/web/src/medicao/MedicaoApp.tsx:3326-3368`, `:3457-3458`). A praça de
várias folhas muda a navegação (qual folha estou vendo), o total que o usuário lê e cria um ato
humano novo — declarar que dois itens de folhas diferentes são o mesmo elemento.

## Priority

`HIGH` — é a lacuna que quebra a legenda quantificada como unidade. Praça grande vem em planta
geral, detalhes e cortes; hoje o caminho é abrir uma rodada por folha e somar por fora, e o
total real não é o de nenhuma das rodadas.

## Problem

### O que existe hoje

O pacote de takeoff é de **uma** folha por construção: `TakeoffPacket` carrega `plate_id`,
`page_number` e `image_sha256` no topo
(`packages/valuation/src/croquito_valuation/takeoff.py:150-164`), e `validate_references`
(`takeoff.py:166-191`) recusa com `TAKEOFF_EVIDENCE_MISMATCH` qualquer item cuja evidência
aponte para outra folha. Isso é fail-closed correto, e é exatamente o que impede a praça de
várias pranchas.

A limitação atravessa a cadeia inteira:

- **Ingestão**: `promote_first_page`
  (`services/worker/src/croquito_worker/valuation/round_extraction.py:204-236`) sempre promove a
  página 1 (`PLATE_PAGE_NUMBER = 1`, `:73`); PDF com mais páginas não é recusado, a contagem vai
  declarada no estado e o resto **fica de fora** (comentário em `:74-77`).
- **API**: `POST /v1/valuation-rounds/{round_id}/plate` recusa a segunda prancha com
  `ROUND_PLATE_ALREADY_PRESENT` (`services/api/src/croquito_api/main.py:11358-11363`).
- **Banco**: as colunas de prancha são escalares — `plate_upload_id`, `plate_object_key`,
  `plate_source_sha256`, `plate_page_count`
  (`services/api/src/croquito_api/database.py:942-951`) —, e o pacote inteiro é um blob por
  revisão (`takeoff_packet_json`, `:984`).
- **Códigos**: `CodeAssignmentSet` também é por prancha
  (`packages/valuation/src/croquito_valuation/assignment.py:1154-1224`), e
  `build_worksite_bulletin` recusa com `CALC_ASSIGNMENT_PACKET_MISMATCH` quando os digests
  divergem (`calc.py:171-187`).

### O que já está pronto e é mais do que a issue supõe

O domínio **já sabe** somar várias obras/folhas: `Valuation.bulletins` é
`list[WorksiteBulletin]` com `min_length=1` (`models.py:624`), a consolidação por código entre
boletins existe em `_measured_by_code` (`workbook_writer.py:648-654`) e alimenta a PLANILHA
GERAL, com o guardrail de arredondamento em `_check_consolidated_total` (`:677`). O que nunca
existiu é o **produtor**: `build_worksite_valuation` popula a lista com um elemento só
(`calc.py:413`), porque recebe um pacote de uma rodada.

Também não existe entidade "obra": ela é atributo da rodada (`worksite_key`/`worksite_name`),
por decisão registrada (`database.py:872-874`, ADR-0028 D8).

### O erro que a ausência produz

Duas rodadas para a mesma praça produzem dois boletins que ninguém soma, ou uma soma manual
fora do sistema. O mesmo serviço aparece nas duas, e não há nada que impeça a dupla contagem —
nem nada que a revele.

## Desired Outcome

Uma praça com N folhas tem **um** consolidado, que referencia os pacotes de cada folha sem
reescrevê-los, soma por código com a memória explicando de qual folha veio cada parcela, e
recusa fechar enquanto qualquer folha tiver item pendente. Item que aparece em duas folhas
conta duas vezes até que a orçamentista declare que é o mesmo elemento.

## Scope

1. **`WorksiteTakeoff`, artefato novo de consolidado de praça** (ADR-0057, decisão 2). Lista os
   pacotes da praça por `plate_id` + digest do pacote; **não** contém itens, contém
   referências. Nasce em `packages/valuation/`, com validação própria e digest próprio.
2. **A rodada aceita N pranchas**, cada uma virando seu próprio `TakeoffPacket` com a extração
   que já existe. Quais páginas/PDFs viram prancha da praça é **ato humano explícito** — não há
   promoção automática de todas as páginas de um PDF. Rodada de uma prancha continua sendo o
   caso de N=1 e responde como hoje.
3. **A identidade que atravessa a praça é `(plate_id, item_id)`** (decisão 5). Nenhum id novo é
   cunhado; promove-se a chave que já viaja na evidência.
4. **Vínculo de identidade declarado entre itens de folhas diferentes** (decisão 4): tipo
   próprio, com autor, instante e nota, no mesmo idioma do ato declarado do reajuste e da RE-RA.
   Sem declaração, os dois itens contam. **Nunca** se funde por rótulo, unidade ou proximidade.
5. **`(item_id, code)` sobe para `(plate_id, item_id, code)`** e o fechamento de pacote passa a
   ser por elemento da obra (decisão 6). `CodeAssignmentSet` continua por prancha para a
   confirmação; o boletim da praça consome a **união** dos conjuntos. Item fundido por
   declaração contribui **uma** parcela, não duas.
6. **Boletim e planilha da praça**, alimentando `Valuation.bulletins` com um boletim por folha e
   deixando a consolidação por código já existente fazer o total — com a memória dizendo de qual
   folha veio cada parcela.
7. **Fail-closed do consolidado** (decisão 7): item `proposed`/`ambiguous` em qualquer folha
   bloqueia o boletim da praça, como `pending_items` já bloqueia o da prancha.
8. **Rotas `/v1` e tela**: adicionar/listar as pranchas da praça, ver o consolidado, navegar
   entre folhas com o overlay de cada uma, e declarar o vínculo de identidade.

## Out of Scope

- **Overlay de praça** (decisão 3): não há espaço de pixels comum às folhas. Um overlay por
  folha, e o consolidado é a lista deles.
- **Fusão automática** de item repetido por rótulo, unidade ou proximidade — recusada
  nominalmente no aceite.
- **Mudar `TakeoffPacket` ou `CodeAssignmentSet`** (decisão 8): nenhum ganha campo, nenhum
  digest assinado se move.
- **Entidade "obra" persistente**: a praça continua identificada por `worksite_key` na rodada;
  criar a entidade é outra decisão (ADR-0028 D8).
- Alinhamento geométrico entre folhas, que segue em "Depois — produto comercial ampliado".
- Multi-praça numa rodada só.

## Acceptance Criteria

1. Rodada com duas pranchas produz dois `TakeoffPacket` íntegros, cada um com sua evidência, e
   `TAKEOFF_EVIDENCE_MISMATCH` continua recusando item de outra folha dentro de um pacote.
2. `WorksiteTakeoff` referencia os pacotes por `plate_id` + digest e recusa referência a pacote
   cujo digest não confere.
3. Rodada de **uma** prancha responde byte a byte como hoje: mesmos digests de pacote, de
   assignments e de boletim (teste de não-regressão sobre fixture existente).
4. Item repetido entre folhas conta **duas** vezes no consolidado enquanto não houver
   declaração; o total reflete isso e a memória mostra as duas parcelas com suas folhas.
5. Declarado o vínculo de identidade, o total cai para uma parcela, a declaração aparece na
   memória com autor e instante, e o boletim é reproduzível a partir dela.
6. Vínculo sem autor, sem instante ou entre itens da **mesma** folha é recusado com código de
   erro nomeado.
7. Colisão de `item_id` entre pacotes não confunde nada: toda resolução usa `(plate_id,
   item_id)`, provado por teste com dois pacotes que cunham o mesmo id.
8. Item `proposed`/`ambiguous` em qualquer folha bloqueia o boletim da praça, com o erro
   apontando **qual** folha está pendente.
9. Fechamento de pacote de serviços (F-038) é por `(plate_id, item_id)`; item fundido é fechado
   uma vez, e a matriz de cálculo não duplica contribuição.
10. Planilha da praça sai no gabarito, com a PLANILHA GERAL consolidando por código e o
    guardrail de arredondamento (`_check_consolidated_total`) verde.
11. `make check` e `make test` verdes; snapshot de OpenAPI aditivo.
12. Evidência renderizada da tela real (`BROWSER_REQUIRED`): a praça com duas folhas, a
    navegação entre elas, a dupla contagem visível, a declaração de identidade e o total depois
    dela.

## Constraints

- Nada de associação implícita: nem por rótulo, nem por unidade, nem por proximidade.
- Artefato assinado não muda de digest sem versão; o consolidado nasce **por cima**.
- O erro do fail-closed é sempre para somar demais e visível, nunca para esconder.
- Português no domínio, inglês no código; `Decimal` onde a quantidade escrita importa.

## Dependencies

- [ADR-0057](../../adr/0057-multiplas-pranchas-por-praca-na-extracao-de-legenda.md) —
  `Accepted` em 2026-08-28.
- [ADR-0053](../../adr/0053-cardinalidade-n-n-elemento-servico.md) e a F-038 — o vínculo
  `(item_id, code)` que sobe de chave.
- [ADR-0030](../../adr/0030-overlay-do-takeoff-reconstruido-na-fila.md) — overlay por imagem,
  preservado.
- Design Approval Package aprovado (gate humano, abaixo).

## Unknowns

- Se a praça de várias folhas deve reaproveitar `worksite_key` como chave da praça ou se o
  consolidado precisa de id próprio — a decidir no plano, sem criar entidade nova de obra.
- Como a tela apresenta N folhas sem virar um explorador de arquivos: decisão do Design
  Approval Package.
- Se a extração de páginas 2..N de um mesmo PDF deve ser um ato por página ou um ato em lote com
  seleção — decisão do Design Approval Package.

## Risks

| Risco | Mitigação |
|---|---|
| Dupla contagem passar despercebida no total | Decisão 4 + AC 4: a dupla parcela é visível na memória, com as folhas nomeadas |
| Declaração de identidade virar fusão em massa | Vínculo é par a par, com autor e instante, e recusado dentro da mesma folha |
| Rodada de uma prancha regredir | AC 3: teste de digest byte a byte sobre fixture existente |
| Praça fechar com folha pendente | Decisão 7 + AC 8 |
| Custo de extração multiplicar por folha sem o usuário perceber | O ato de promover cada prancha é explícito; o custo por rodada continua declarado |

## Human Gates

- ~~Aceite do ADR-0057~~ — **satisfeito em 2026-08-28** (Daniel Campos).
- `DESIGN_APPROVAL_REQUIRED`: [Design Approval Package, revisão 1](mock/README.md) —
  **produzido em 2026-08-28, pendente de aprovação humana**. Nada da superfície é implementado
  antes da aprovação. O pacote resolve dois dos três `Unknowns` acima (como a tela apresenta N
  folhas e se a promoção de páginas é ato por página ou em lote) e deixa o terceiro
  explicitamente para o plano.
- Merge do PR e o aceite que fecha a [issue #101](https://github.com/biahflow/croquito/issues/101),
  numa praça real de mais de uma prancha.

## References

- [ADR-0057](../../adr/0057-multiplas-pranchas-por-praca-na-extracao-de-legenda.md)
- [Design Approval Package, revisão 1](mock/README.md) — pendente de aprovação humana
- [Issue #101](https://github.com/biahflow/croquito/issues/101)
- [ROADMAP](../../product/ROADMAP.md), "Próximo — medição além do v1"
