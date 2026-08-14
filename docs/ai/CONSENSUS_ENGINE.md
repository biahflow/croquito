# Motor de consenso

Status: Accepted for MVP  
Responsável: AI / Geometry Engineering  
Última revisão: 2026-08-10

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

Leituras A/B são candidatas ao mesmo item quando:

- Bounding polygons se sobrepõem ou referem o mesmo crop.
- `kind` é compatível.
- `target_hint` converge para a mesma feature proposta.

Matching ambíguo gera issue, não greedy assignment irreversível.

## Estados de comparação

| Estado | Condição | Ação |
|---|---|---|
| `agreed` | valor, unidade, precisão e alvo materialmente iguais | validar geometria |
| `text_only_agreed` | texto igual, alvo diverge | reanalisar associação |
| `value_disagreed` | valores/unidades divergem | escalonar crop |
| `single_source` | somente um LLM válido | revisão humana |
| `illegible` | ambos sem leitura | pedir medida/aceitar unresolved |

Valores coincidem somente se iguais na precisão escrita. Tolerância geométrica é
aplicada pelo solver depois, não pelo consenso OCR.

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

