# ADR-0057: A praça é o consolidado de pranchas, e a prancha continua a unidade de evidência

Status: Accepted  
Data: 2026-08-27 (aceito por ato humano em 2026-08-28, Daniel Campos — os quatro pontos
confirmados sem emenda)  
Responsável: Product / Engineering

## Contexto

A [issue #101](https://github.com/biahflow/croquito/issues/101) nasce do bullet 23 da seção
"Próximo — medição além do v1" do [ROADMAP](../product/ROADMAP.md): *múltiplas pranchas por
praça na extração de legenda*. Praça grande não cabe numa folha — vem em planta geral,
folhas de detalhe e cortes —, e a legenda quantificada é da **obra**, não de cada folha.

Hoje o caminho de quem tem várias pranchas é abrir uma rodada por prancha e somar por fora.
Isso quebra a legenda quantificada como unidade: o mesmo serviço aparece em duas rodadas e o
total real não é o de nenhuma delas. É exatamente a classe de erro — número parcial que
parece inteiro — que este repositório recusa por princípio.

### O que já existe

O contexto de medição é, do começo ao fim, **de uma prancha e uma página**:

- `TakeoffPacket` amarra o pacote inteiro a `plate_id`, `page_number` e `image_sha256`
  (`takeoff.py:150-164`), e `validate_references` recusa com `TAKEOFF_EVIDENCE_MISMATCH`
  todo item cuja `PlateEvidence` aponte para outra folha (`takeoff.py:166-192`, evidência em
  `takeoff.py:75-83`). A âncora é sempre em pixels da imagem (`coordinate_space =
  source_image_pixels`).
- O id de item é único **dentro do pacote** (`takeoff.py:168-173`), e o padrão
  `^ti_[a-f0-9]{16}$` não carrega procedência de folha.
- A extração declara isso na própria docstring: "Uma rodada é uma prancha, e a prancha é a
  página 1" (`round_extraction.py:74`), e "esta rodada é de uma prancha só"
  (`round_extraction.py:208-210`). As chaves de objeto são de uma página
  (`.../plate/page-001.png`, `.../takeoff/overlay.png`, `round_extraction.py:145-151`).
- O overlay do takeoff é PNG por imagem, reconstruído na fila e conferido pelo digest da
  imagem contra o pacote antes de qualquer traço
  ([ADR-0030](0030-overlay-do-takeoff-reconstruido-na-fila.md)).
- O vínculo do [ADR-0053](0053-cardinalidade-n-n-elemento-servico.md) (F-038) vive dentro de
  um artefato **também por prancha**: `CodeAssignmentSet` carrega `plate_id`, `page_number` e
  `image_sha256` (`assignment.py:1049-1057`), a identidade é o par `(item_id, code)` no regime
  `2.0.0`, e `ItemPackageClosure` fecha o pacote de serviços de **um item**. A memória amarra a
  parcela ao elemento por `CalcBlock.source_item_id`, que é o id do `TakeoffItem`
  (`calc_matrix.py:67`).

O fail-closed por página é **correto para o desenho atual**. É também, precisamente, o que
impede uma praça de várias pranchas: cada folha é uma ilha que não conhece as outras.

### O que não existe

Não há nenhum conceito de **obra** acima da prancha na extração. Não há artefato que agrupe
pacotes de takeoff, não há identidade de item que atravesse folhas, e não há lugar onde a
legenda da praça seja uma coisa só. `grep -rn "worksite\|praca\|multi.*plate" packages/valuation`
não devolve um agrupador — só `worksite` no sentido de *obra orçada* do orçamento, não da
extração. A soma entre folhas acontece hoje na cabeça do orçamentista, fora do sistema, sem
nada que impeça contar duas vezes o serviço que aparece na planta geral **e** no detalhe.

## Decisão

As decisões abaixo foram **aceitas sem emenda** por ato humano em 2026-08-28; a seção final
registra os quatro pontos confirmados. O raciocínio de cada uma é o coração do ADR.

1. **A prancha continua a unidade de evidência, e o pacote de takeoff não muda.**
   `TakeoffPacket` segue de uma folha, com `plate_id`/`page_number`/`image_sha256` e o
   `TAKEOFF_EVIDENCE_MISMATCH` intactos. A âncora é da imagem, o overlay é da imagem, e o
   digest da imagem continua sendo o que casa item e folha antes de qualquer traço. Dissolver
   o pacote num saco multi-prancha obrigaria o validador de evidência a afrouxar — "de qual das
   folhas é este item?" —, reintroduzindo a ambiguidade que o fail-closed por página existe
   para barrar. O que a issue chama de "unidade" não é o pacote: é a legenda da praça, que é um
   nível **acima** do pacote.

2. **A praça é um CONSOLIDADO que referencia pacotes de prancha, não os absorve.** Nasce um
   artefato de obra — provisoriamente `WorksiteTakeoff` — que lista os pacotes de takeoff da
   praça por digest, cada um com seu `plate_id`. Ele não contém itens; contém referências.
   É o mesmo movimento estrutural das decisões recentes do contexto: o consolidado contratual
   soma períodos sem reescrevê-los ([ADR-0055](0055-reajuste-como-ato-declarado-sobre-o-consolidado.md)),
   e a medição seguinte cita a rodada anterior em vez de reconstruí-la
   ([ADR-0056](0056-re-ra-declarada-e-o-consolidado-da-medicao-seguinte.md)). Um agregado que
   referencia artefatos autocontidos preserva a cadeia de auditoria de cada folha e deixa o
   total explicável por composição, não por reextração.

3. **A âncora e o overlay permanecem por imagem, por prancha; o consolidado não renderiza.**
   Nenhuma mudança em `takeoff_overlay.py`, na conferência de digest de imagem nem nas chaves
   de objeto por página — o consolidado apenas endereça os overlays das suas pranchas, como a
   rodada já endereça o overlay da sua. O overlay é observacional (ADR-0030): ele mostra de
   onde cada número foi lido, e cada número foi lido de **uma** folha. Não existe overlay de
   praça porque não existe pixel de praça; existe um overlay por folha, e o consolidado é a
   lista deles.

4. **Item repetido entre folhas são DOIS itens até que um humano declare que são um.** O mesmo
   serviço na planta geral e no detalhe produz dois `TakeoffItem` distintos, com evidências
   distintas e ids distintos — porque são duas leituras, de duas folhas. O sistema **nunca**
   funde por proximidade de pixel nem por igualdade de rótulo: proximidade jamais é associação
   implícita, e rótulo é texto livre. Quando as duas leituras são o mesmo serviço físico
   contado duas vezes, isso é uma **declaração humana no consolidado** — um vínculo de
   identidade tipado (`SamePlateItemLink` ou equivalente), com autor, instante e nota, no
   mesmo idioma do ato declarado do reajuste e da RE-RA. Sem a declaração, ambos contam: o
   fail-closed erra para o lado de somar demais e visível, nunca de esconder. É a declaração
   que muda o total, e é ela que fica auditável.

5. **A identidade que atravessa a praça é `(plate_id, item_id)`, não `item_id` sozinho.** O id
   `ti_...` só é único dentro do pacote (`takeoff.py:168-173`) e dois pacotes podem cunhar o
   mesmo id. No consolidado, todo item é endereçado pelo par `(plate_id, item_id)`, e o
   `plate_id` já viaja na evidência — não se inventa chave nova, promove-se a que já existe. O
   vínculo de identidade da decisão 4 é entre dois pares desses.

6. **O vínculo `(item_id, code)` da F-038 sobe para `(plate_id, item_id, code)`, e o
   fechamento de pacote passa a ser por elemento da obra.** `CodeAssignmentSet` continua por
   prancha para a confirmação — a orçamentista confirma código olhando uma folha —, mas o
   boletim da praça consome a **união** dos conjuntos das pranchas do consolidado. A cardinalidade
   N:N do ADR-0053 já admite que um código receba parcelas de vários elementos; a única regra
   que muda é que "vários elementos" agora pode significar elementos de folhas diferentes. Um
   item ligado por identidade (decisão 4) contribui **uma** parcela, não duas: a fusão declarada
   colapsa as duas leituras numa contribuição só, explicitamente, antes de o boletim somar. O
   `ItemPackageClosure` fecha o pacote de serviços de um item da obra — identificado por
   `(plate_id, item_id)` —, e um item fundido é fechado uma vez.

7. **O consolidado exige toda prancha referenciada extraída e revisada, e falha fechado.** A
   praça não fecha com pacote pendente: item `proposed`/`ambiguous` em qualquer folha do
   consolidado bloqueia o boletim da obra, como `pending_items` já bloqueia o da prancha. Uma
   folha a menos é meia praça, e meia praça somada parece uma praça inteira — o erro exato que
   a issue descreve.

8. **Nenhum artefato existente muda de digest sem versão, e a rodada de uma prancha continua
   byte-idêntica.** `TakeoffPacket` e `CodeAssignmentSet` não ganham campo; o consolidado é
   artefato **novo**. Praça de uma prancha só é um consolidado de um pacote — que é exatamente
   o que ela é — e todo caminho de rodada única responde como hoje. É a mesma disciplina das
   decisões 8 do ADR-0055 e 9 do ADR-0056: o agregado nasce por cima, sem tocar o que já está
   assinado.

## Alternativas

- **Pacote de takeoff multi-prancha (a obra vira o pacote, pranchas viram lista interna)** —
  rejeitada pela decisão 1. Obrigaria `TAKEOFF_EVIDENCE_MISMATCH` a admitir múltiplas
  `(plate_id, image_sha256)` no mesmo pacote, transformando a conferência que hoje amarra item
  a folha numa que só verifica pertencimento ao conjunto. A âncora por imagem, o overlay por
  imagem e o digest por imagem perderiam o pacote autocontido a que se prendem.
- **Fundir automaticamente item repetido por rótulo e unidade iguais entre folhas** —
  rejeitada pela decisão 4. É associação implícita por semelhança de texto, o oposto do
  invariante do produto; fundiria dois muros diferentes que a legenda descreve com o mesmo
  rótulo, e o erro seria silencioso e no total.
- **Somar as folhas fora do sistema (o estado de hoje)** — rejeitada: é a própria issue. O
  total real não é o de nenhuma rodada, e nada impede a dupla contagem.
- **Um `item_id` global único por obra, cunhado na extração** — rejeitada pela decisão 5:
  mudaria o padrão do id e o cálculo do `vd_`/decisão, movendo digests históricos, para
  resolver por reengenharia o que `(plate_id, item_id)` resolve por composição da chave que já
  existe.
- **Overlay consolidado da praça, desenhado sobre as folhas montadas** — rejeitada pela
  decisão 3: não há espaço de pixels comum às folhas, e montar um pressuporia geometria entre
  pranchas que a extração não tem. O overlay por folha já responde "de onde veio este número".
- **Bloquear a praça só no boletim, deixando o consolidado fechar com pacote pendente** —
  rejeitada pela decisão 7: adiaria a detecção para depois de a obra parecer pronta, quando o
  barato é recusar na composição do consolidado.

## Consequências

### Positivas

- A legenda da praça passa a ser uma coisa só e auditável: quem é a obra, quais folhas a
  compõem, e por que o total é o que é.
- A dupla contagem entre planta geral e detalhe vira uma **declaração** visível, não uma
  subtração de cabeça — e fica no histórico com autor e nota.
- Cada folha continua autocontida e byte-idêntica; a auditoria por prancha que já existe não é
  tocada.
- Praça de uma prancha responde exatamente como hoje.

### Negativas

- Nasce um artefato novo (`WorksiteTakeoff`) e um ato declarado novo (o vínculo de
  identidade), com contrato, schema e rota próprios — superfície nova, ainda que aditiva.
- O boletim da praça passa a compor a união dos conjuntos de assignment de várias folhas, e o
  fechamento de pacote passa a ser endereçado por `(plate_id, item_id)`: mais chave para
  carregar em toda a cadeia até a memória e o `.xlsx`.
- A revisão fica em dois níveis — confirmar código na folha, declarar identidade e fechar a
  praça no consolidado —, e a UI precisa tornar visível qual dos dois o orçamentista está
  fazendo.
- O ganho real só aparece quando existe a segunda folha; para a praça de uma prancha, o
  consolidado é peso sem benefício imediato.

## Riscos e mitigação

| Risco | Mitigação |
|---|---|
| Item contado duas vezes entre folhas | Decisão 4: dois itens até declaração explícita; sem ela, ambos contam e o erro é para somar demais, visível |
| Fusão por semelhança de rótulo inventar identidade | Decisão 4: proximidade e igualdade de texto nunca fundem; só a declaração humana funde |
| `TAKEOFF_EVIDENCE_MISMATCH` afrouxar e perder a âncora por folha | Decisão 1: o pacote não muda; a obra é agregado por cima |
| Colisão de `item_id` entre pacotes de folhas | Decisão 5: identidade é `(plate_id, item_id)`, com `plate_id` já na evidência |
| Praça fechar com folha pendente e parecer inteira | Decisão 7: pacote pendente em qualquer folha bloqueia o boletim da obra |
| Digest de artefato assinado se mover | Decisão 8: consolidado é artefato novo; `TakeoffPacket` e `CodeAssignmentSet` não ganham campo |
| Overlay de praça exigir geometria entre folhas | Decisão 3: sem overlay de praça; o consolidado lista os overlays por folha |

## O que o aceite humano confirmou

Em 2026-08-28 (Daniel Campos), os quatro pontos foram confirmados como propostos, sem emenda:

1. **O pacote é por prancha com um consolidado acima** (decisões 1–2), e não um pacote de obra
   que absorve as folhas. É a escolha estrutural que orienta todo o resto.
2. **Item repetido entre folhas são dois itens até declaração** (decisão 4): o total só fica
   correto quando a orçamentista declara a sobreposição, e o sistema erra para somar demais até
   lá. Confirmar que esse é o comportamento desejado, e não uma dedução automática.
3. **A identidade que atravessa a praça é `(plate_id, item_id)`** (decisão 5) e o vínculo da
   F-038 sobe para `(plate_id, item_id, code)` (decisão 6). Confirmar que o fechamento de
   pacote passa a ser por elemento da obra, não da folha.
4. **O consolidado falha fechado com qualquer folha pendente** (decisão 7). Confirmar que
   nenhuma praça mede parcial, nem para adiantar.

Com os quatro confirmados, o trabalho virou Feature Contract e plano na mesma data. A
alternativa de fundir automaticamente item repetido por rótulo e unidade iguais foi
explicitamente recusada no aceite: o total só fica correto quando a orçamentista declara a
sobreposição, e até lá o sistema erra para somar demais, visivelmente.

## Rastreabilidade

- Feature: [F-046](../features/F-046-praca-de-varias-pranchas/feature.md)
- Issue: [#101](https://github.com/biahflow/croquito/issues/101)
- Relacionados: [ADR-0053](0053-cardinalidade-n-n-elemento-servico.md) (o vínculo
  `(item_id, code)` da F-038 que sobe para `(plate_id, item_id, code)`),
  [ADR-0030](0030-overlay-do-takeoff-reconstruido-na-fila.md) (overlay por imagem, preservado),
  [ADR-0016](0016-valuation-bounded-context.md) (o contexto de medição, onde o consolidado
  nasce), [ADR-0055](0055-reajuste-como-ato-declarado-sobre-o-consolidado.md) e
  [ADR-0056](0056-re-ra-declarada-e-o-consolidado-da-medicao-seguinte.md) (o padrão do
  agregado que referencia artefatos autocontidos em vez de reescrevê-los)
- Supersedes: none
- Superseded by: none
