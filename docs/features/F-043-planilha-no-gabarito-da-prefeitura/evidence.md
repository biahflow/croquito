# F-043 — Evidência

## O gabarito real, conferido contra a feature

**Data**: 2026-08-28. Fonte: aba `PLANILHA ORÇAMENTÁRIA` dos três orçamentos reais
fornecidos pelo dono. Os arquivos **não estão versionados**; a leitura é local.

| O que a feature afirmava | Verificado |
|---|---|
| 433 linhas de código | **433** ✓ |
| 21 grupos | **21** ✓ (`1,2,3,4,6,7,8,9,10,11,12,13,14,16,17,18,19,20,21,23,24`) |
| grupos 5, 15 e 22 ausentes por convenção | **confirmado** ✓ |
| 43 linhas com quantidade nesta praça | **43** ✓ (390 zeradas) |
| numeração `GG.N` | confirmada: `01.9` precede `01.10` — é **texto**, não número ✓ |

A estrutura da aba é: cabeçalho na linha 9
(`ITEM | COD. | DESCRIÇÃO | UN | VALOR UNIT (OUT/23) | QUANT | TOTAL`), e uma linha de grupo
que traz **apenas o número do grupo** na coluna A, sem título.

## As fórmulas reais, e o que elas dizem

```
E15 = VLOOKUP(B15,'PLANILHA GERAL'!E:J,5,0)          preço, buscado na lista do contrato
F15 = IFERROR(VLOOKUP(A15,'<aba da memória>'!B:Q,16,FALSE),0)   quantidade, buscada na memória
G15 = TRUNC(F15*$E15,2)                              total da linha
G465 = SUBTOTAL(9,G10:G463)                          TOTAL
G466 = TRUNC(G465/1.18,2)                            TOTAL S/BDI
```

Três consequências para esta feature:

1. **O `VALOR UNIT (OUT/23)` é COM BDI.** O rodapé deriva o total *sem* BDI dividindo o total
   por 1,18 — logo o BDI de 18% já está no preço unitário impresso. Isso **resolve o unknown
   2** da feature, e confirma a suposição com que a T1 foi construída (`unit_price_with_bdi`
   na coluna de preço).

2. **O rodapé real tem duas linhas, não três**: `TOTAL` (com BDI) e `TOTAL S/BDI`, nessa
   ordem. Não existe uma linha "BDI" impressa. O ADR-0038 manda imprimir o BDI como
   diferença entre totais truncados; o documento do cliente **não imprime o BDI**, e deriva o
   total sem BDI por divisão. É divergência de forma a resolver com quem entrega.

3. **As fórmulas do cliente não cabem na gramática fechada** de `canonical.py`:
   `SUBTOTAL(9,…)` não existe nela, `TRUNC(G465/1.18,2)` é divisão, e `TRUNC(F15*$E15,2)`
   usa referência absoluta (`$E15`), que `_REF` não aceita. Isso **não** é um problema para a
   feature: o arquivo que publicamos precisa produzir o mesmo **documento**, não copiar as
   fórmulas do cliente. `TRUNC(F15*E15,2)` e `SUM(...)` cabem na gramática e dão o mesmo
   valor — e são auditáveis, que é o ponto.

## Achado: o TOTAL do cliente não soma tudo que está impresso

`SUBTOTAL(9,…)` **ignora as linhas ocultas por filtro automático**, e as três abas têm
filtro automático ativo (`A4:H463`). O filtro esconde as linhas zeradas — mas em duas das
três praças ele também esconde **linhas com quantidade e valor**, que ficam impressas na
planilha e **fora do total**:

| Praça | TOTAL impresso | Soma real das linhas | Diferença |
|---|---|---|---|
| Campo do Toca | 645.961,09 | 648.956,63 | **2.995,54** |
| Dona Eli | 796.884,55 | 796.884,55 | — |
| Todos os Santos | 161.258,48 | 201.100,13 | **39.841,65** |

As linhas afetadas:

- **Campo do Toca** — `01.10 AD19050500(/)` aluguel de banheiro químico, R$ 2.995,54.
- **Todos os Santos** — `01.5` transporte de andaime R$ 900,00; `01.30` vigia R$ 16.185,60;
  `18.6` R$ 3.177,63; `18.9` R$ 13.080,94; `23.3` transporte horizontal R$ 6.497,48.

Em Todos os Santos isso é **19,8% do valor real da obra** fora do total. O padrão sugere
linhas preenchidas depois que o filtro já estava aplicado: elas continuam escondidas, e o
`SUBTOTAL` as ignora.

**Isto é achado sobre o arquivo do cliente, não sobre o sistema** — e precisa de conferência
humana antes de qualquer conclusão: quem entrega precisa dizer se o total entregue à
prefeitura foi esse mesmo. Se foi, houve serviço orçado e não cobrado.

É também a demonstração mais direta do valor desta feature: o portão de auditoria fail-closed
(`canonicalize_workbook` + recomputação em `Decimal`) pega exatamente esse defeito, porque
recomputa a soma em vez de confiar na célula. Um arquivo gerado por nós não pode ter
`SUBTOTAL` dependente de estado de filtro.

## Segundo achado: o que a memória calcula e a planilha não cobra

A quantidade não viaja sozinha da memória para a planilha. A planilha lê
`IFERROR(VLOOKUP(<item>,'<aba da memória>'!B:Q,16,FALSE),0)` — ou seja, ela busca o item na
memória e pega a **coluna Q daquela linha**. A coluna Q é preenchida à parte: o bloco calcula
o `TOTAL` numa linha própria (coluna J), e alguém **transporta** esse número para o Q do
cabeçalho do bloco. Quando Q fica vazia, o `IFERROR` devolve **0** e a planilha imprime
quantidade zero — sem aviso nenhum.

Blocos com `TOTAL` calculado e coluna Q vazia:

| Praça | Blocos com total calculado | Não transportados |
|---|---|---|
| Campo do Toca | 61 | **18** |
| Dona Eli | 31 | **0** |
| Todos os Santos | 43 | **9** |

**Não é correto somar esses valores como perda**, e não os somamos aqui. A coluna Q vazia
tem pelo menos duas causas diferentes, e elas se parecem no arquivo:

1. **Alternativa estudada e descartada de propósito.** No Campo do Toca, o maior item nessa
   condição é `17.13 GRAMA SINTÉTICA`, com 1.893,80 m² calculados. Uma praça que pavimenta em
   saibro e grama natural muito provavelmente estudou a grama sintética e decidiu não usá-la.
   A memória é o caderno de contas, e conter alternativa descartada é uso legítimo dela.

2. **Esquecimento de transporte.** O caso que mais parece isso é
   `01.30 VIGIA`, no Campo do Toca: a memória calcula **468 h** (23 dias × 12 h + 8 dias ×
   24 h) e a coluna Q está vazia. Vigia não é alternativa de projeto — é canteiro, e as
   outras quatro parcelas de canteiro da mesma praça (banheiro químico, container, placa e
   transporte de andaime) **foram** transportadas. A 16,86/h, são R$ 7.890,48.

Só quem montou o orçamento pode separar um caso do outro, item a item. O que o dado sustenta
sem ambiguidade é o **mecanismo**: existe um passo manual de transporte entre a memória e a
planilha, ele falha em silêncio, e quando falha o serviço sai com quantidade zero.

O contraste entre as praças reforça isso: a Dona Eli tem **zero** blocos nessa condição, o
que mostra que transportar tudo é o resultado normal quando nada se perde.

Isto **não é escopo desta feature** — é observação levantada ao conferir o documento real, e
vale como candidata a feature própria: o sistema tem a memória e a planilha no mesmo modelo,
então "calculado e não cobrado" é uma conferência que ele pode fazer sozinho, ao contrário da
planilha, onde os dois lados só se encontram por um `VLOOKUP` numa coluna preenchida à mão.

## O motor gerou o gabarito real, e o auditor aprovou

**Data**: 2026-08-28. O gabarito de 433 linhas foi transcrito do documento real para um
`EstimateTemplateLayout` declarado, e um orçamento com as 43 linhas preenchidas do Campo do
Toca foi publicado pelo escritor novo (`write_estimate_grid_workbook`) e auditado
(`audit_estimate_grid_workbook`).

```
ESCRITO: PLANILHA ORÇAMENTÁRIA + MEMÓRIA DE CÁLCULO
  células 4009 | fórmulas 519 | fixadas 2
AUDITORIA: 0 findings
quantidades conferidas contra o arquivo real: 433 iguais, 0 divergentes
linhas zeradas impressas: 390
```

Isso exercita os critérios de aceite 1, 2, 4 e 5 da feature contra o documento real, e não
contra fixture. As duas células fixadas são as em que a fórmula viva do Excel divergiria do
`Decimal` — o mecanismo `EstimatePinnedCell`, que já existia, disparou sozinho em dado real.

As fórmulas emitidas são `=TRUNC(G14*F14,2)`, dentro da gramática fechada; nada em
`canonical.py` precisou ser estendido.

**E o total gerado é 648.956,63** — a soma correta das 43 linhas —, contra os 645.961,09 que
o arquivo do cliente imprime. O arquivo que o sistema publica não reproduz o defeito descrito
acima, porque não usa `SUBTOTAL` nem depende de estado de filtro.

Ressalva: esta verificação usou `bdi_percent = 0` com o preço do gabarito entrando como preço
final, para isolar o layout do arredondamento do BDI. A conferência do BDI de 18% contra o
documento real ainda não foi feita.

## Impacto no Design Approval Package

A revisão 1 foi aprovada em 2026-08-28 com a estrutura **sintética**, declarando que os
códigos, descrições e a estrutura de grupos das capturas não eram especificação. Com o
documento real em mãos, quatro pontos de forma divergem e pedem **revisão 2**:

| No pacote rev.1 | No documento real |
|---|---|
| linha de grupo com título (`01 — SERVIÇOS PRELIMINARES…`) | linha de grupo com **apenas o número** (`1`) |
| rodapé de três linhas: TOTAL SEM BDI, BDI, TOTAL GERAL | duas linhas: **TOTAL** e **TOTAL S/BDI**, nessa ordem, sem linha de BDI |
| coluna rotulada `V. UNIT C/ BDI` | rotulada `VALOR UNIT (OUT/23)` — o valor é o mesmo (com BDI) |
| BDI de 24,50% na rendição | **18%** |

Nenhuma dessas divergências atinge as sete decisões que o pacote carrega — ordem fixa, linhas
zeradas impressas, numeração como texto, lacuna de grupo, carimbo de revisão, recusa de
código ausente, memória só para código com quantidade. A revisão 2 é de fidelidade ao
documento, não de mudança de desenho.

## O que continua aberto

- **Aceite do arquivo gerado** contra o real, por quem entrega à prefeitura (Human Gate 4).
- **A divergência do rodapé**: imprimir o BDI como diferença (ADR-0038) ou reproduzir o
  `TOTAL` / `TOTAL S/BDI` do cliente. É decisão de quem entrega.
- **Se o gabarito é por lote do contrato** (unknown 1) — os três arquivos usam o mesmo
  gabarito de 433 linhas, o que é evidência a favor de um só, mas as três praças são do mesmo
  contrato.
- A publicação do gabarito como artefato de plataforma (decidido em 2026-08-28) ainda não foi
  construída.
