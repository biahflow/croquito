# F-044 — Evidência

## Human Gate 1 — a hipótese de repetição, medida

**Data**: 2026-08-28  
**Resultado**: **hipótese confirmada**. A feature continua.

### O que foi medido

Três orçamentos reais, fornecidos pelo dono do produto em 2026-08-28, todos com revisão
SEAC do mesmo contrato:

| Praça | Aba de memória | Blocos | Com rótulo | Rótulos distintos |
|---|---|---|---|---|
| Campo do Toca | `PRAÇA CAMPO DO TOCA` | 129 | 125 | 76 |
| Dona Eli | `MEMÓRIA DE CÁLCULO` | 133 | 130 | 84 |
| Todos os Santos (Quadra do Condomínio) | `MEMÓRIA RESIDENCIAL MIRANTE` | 71 | 67 | 48 |

Os arquivos são dados de cliente: **não estão versionados**, e nenhum rótulo, código ou
valor deles entra em `tests/`. A leitura é local, no molde de
`make valuation-parity PREVIOUS=<caminho>`.

O par medido é (**rótulo do elemento na memória de cálculo** → **conjunto de códigos SCO que
ele dispara**). Cada bloco da memória traz item, código e, abaixo, o rótulo do elemento; um
mesmo rótulo aparece em vários blocos, que é exatamente o pacote N:N da
[F-038](../F-038-pacote-de-servicos/feature.md).

### Repetição entre praças

```
rótulos distintos no total       95
rótulos presentes em ≥2 praças   76   (80,0% de repetição)
```

Estabilidade do pacote de códigos, entre as praças em que o rótulo reaparece:

| Classe | Quantos | % dos repetidos |
|---|---|---|
| `identical` — mesmo conjunto de códigos | 65 | 85,5% |
| `subset` — um pacote contido no outro | 10 | 13,2% |
| `overlapping` — interseção sem contenção | 0 | 0,0% |
| `disjoint` — nenhum código em comum | **1** | 1,3% |

**98,7% dos rótulos repetidos têm pacote idêntico ou contido.** O único caso `disjoint` em
76 é `PONTOS DE SOLDA`: `SC19050600(/)` no Campo do Toca contra `SC14050400(/)` na Dona Eli.

Os dez `subset` não são erro — são escopo menor. `CAMADA DE BRITA` dispara um código no
Campo do Toca e quatro em Todos os Santos, porque ali há drenagem; `GUARDA CORPO` perde o
código de instalação na praça que não o tem.

### Ganho prático, cada praça tratada como a nova

| Praça nova | Rótulos com precedente | Pacote exato | Linhas de código cobertas |
|---|---|---|---|
| Campo do Toca | 70/76 (92%) | 63/70 | 111/125 (89%) |
| Dona Eli | 76/84 (90%) | 71/76 | 120/130 (92%) |
| Todos os Santos | 43/48 (90%) | 36/43 | 54/67 (81%) |

### O que estes números mudam na feature

A F-044 foi registrada com prioridade `MEDIUM` e estimativa de **cerca de 12 linhas**
preenchidas sem decisão humana. A medição diz outra coisa: **54 a 120 linhas de código por
praça** têm precedente com pacote exato ou contido.

Isso a coloca acima da [F-042](../F-042-acervo-de-parcelas-de-canteiro/feature.md) (24
linhas) em volume, e a estimativa original está subdimensionada por um fator de cerca de
cinco. A prioridade merece revisão pelo dono.

### Unknown 2 — como normalizar o rótulo

Medido com duas estratégias, `exact` (texto como escrito) e `folded` (casefold, sem acento,
pontuação colapsada): **resultado idêntico nas duas**, nos três arquivos. Neste corpus os
rótulos já chegam padronizados, e normalização agressiva não é necessária.

Isso **não** encerra o unknown: o corpus é de um escritório só (ver limitações). A conclusão
sustentada é a mais fraca — normalização leve basta aqui, e não há evidência que justifique
uma agressiva.

## Limitações desta medição, declaradas

1. **Um escritório, um contrato.** Os três arquivos são revisão SEAC do mesmo contrato e
   compartilham a estrutura da planilha, a numeração `GG.N` e a lista de preços. A medição
   prova a repetição **dentro de um escritório**, que é o caso de uso real do produto, e
   **não** prova nada sobre praças de projetistas diferentes. O risco "rótulo instável entre
   projetistas", declarado na feature, continua aberto e não foi testado.

2. **O rótulo medido é o da memória de cálculo, não o da legenda da prancha.** É a melhor
   aproximação disponível — a memória é onde o rótulo do elemento encosta no código —, mas o
   índice que a feature vai construir se chaveia pelo rótulo da **legenda**, extraído da
   prancha. Se os dois divergirem sistematicamente, o recall medido aqui é otimista.

3. **A perda de recall já aparece no corpus.** O código `BP09100050(B)` é `PASSEIO` no Campo
   do Toca e `CALÇADA DE ACESSO` nas outras duas: o mesmo serviço com dois rótulos. Nenhuma
   normalização razoável funde os dois, e nenhuma deveria. É perda de recall, não erro — e é
   parte de por que a cobertura fica em 90% e não em 100%.

4. **A medição foi feita por script de análise**, fora do repositório, e reproduzida em
   seguida pela ferramenta `precedent-eval`. A ferramenta é o artefato reproduzível; o
   script foi o instrumento da primeira leitura.

## Human Gate 2 — Design Approval Package

Revisão 1 **aprovada em 2026-08-28** (Daniel Campos), condicionada a este gate 1 — que agora
está cumprido. Ver [`mock/README.md`](mock/README.md).

## Human Gate 3 — ADR-0059

Cumprido em 2026-08-28.

## O que continua aberto

- **Unknown 3 — quantas praças fazem um precedente confiável.** A medição não decide limiar.
  Com três praças, o caso de "uma praça só" é comum e é justamente o que o desenho marca com
  aviso.
- **A prioridade da feature**, à luz do volume medido.
- A construção do índice, a mudança na shortlist e a tela — nenhuma iniciada.
