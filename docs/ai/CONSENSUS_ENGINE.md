# Motor de consenso

Status: Accepted for MVP  
Responsável: AI / Geometry Engineering  
Última revisão: 2026-08-19

## Objetivo

Transformar leituras independentes em candidatos rastreáveis. Consenso não cria
verdade; reduz o conjunto de itens que exigem revisão.

## Normalização determinística

1. Unicode e espaços sem alterar `raw_text` armazenado.
2. Vírgula/ponto decimal conforme padrão numérico.
3. Separação de unidade, prefixos (`h=`, `r=`, `ø`) e valor.
4. Conversão para SI mantendo unidade e precisão escritas.
5. Normalização de sinônimos de entidade por glossário versionado.

Nenhum normalizador corrige dígito por plausibilidade.

## Matching

Implementado em `pair_readings_by_evidence` (`provider_review.py`): casamento guloso
1:1 pelo centro do bbox da EVIDÊNCIA, com tolerância normalizada. `kind` e
`target_hint` ficam **fora** do casamento e do juízo de propósito (revisão de
2026-08-19, prancha real): o mesmo 25,90 saiu `length` num braço e `width` no outro —
divergência de vocabulário não é divergência de medida. Elas viram notas
(`READING_{n}_KIND_DIVERGENCE`), nunca recusa de par. Contrapartes sem par entram na
nota `PROVIDER_UNMATCHED_COUNTERPART_READINGS:{n}`.

## Concordância

O juízo implementado é um booleano por par (`_readings_agree`), não uma máquina de
estados. Um par CONCORDA quando:

- os dois `normalized_value` existem e são iguais como `Decimal` (sem tolerância;
  `None` nunca concorda); e
- as unidades são iguais, **ou** a contraparte se absteve (`unknown`) diante de
  âncora concreta — abstenção não é contradição (V11: o croqui não escreve unidade;
  o prompt manda `unknown` sem evidência, e um braço obedece enquanto o outro infere
  a convenção). O par concordante por abstenção carrega
  `READING_{n}_UNIT_ABSTENTION`: o valor tem duas testemunhas, a unidade tem uma.

Unidades concretas diferentes (`m` × `cm`) são contradição: nota
`READING_{n}_PROVIDER_DISAGREEMENT` e leitura ambígua.

O status resultante nunca confirma nada: leitura sai `proposed` somente com os dois
braços vivos, texto legível e par concordante; qualquer outra combinação (braço
único, ilegível, divergência, sem par) sai `ambiguous`. Toda leitura segue exigindo
`HumanDecision` antes de virar geometria. Tolerância geométrica é aplicada pelo
solver depois, não pelo consenso.

## Papel do Textract

Textract fornece:

- `raw_text` adicional.
- `TextType` quando disponível.
- Bounding boxes/polygons.
- Confidence operacional.

Ele pode reforçar localização ou apontar terceira divergência. Não transforma
`single_source` em `agreed` e não aprova medida sozinho.

## Validação geométrica

Mesmo `agreed` vira issue quando:

- Viola constraint confirmada.
- Cria dimensão fisicamente inconsistente com outras cotas.
- Não possui target associável.
- Exige hipótese de ângulo/diagonal não registrada.

Plausibilidade de domínio gera warning; não substitui evidência.

## Saída

O engine produz `MeasurementCandidate`, links para readings e issues. Somente o
geometry engine ou usuário cria `Measurement` de uma SceneRevision.

## Reprodutibilidade

- Algoritmo e glossário possuem versão.
- Mesmas readings e versões produzem o mesmo resultado.
- Decisões humanas não alteram leituras originais.

