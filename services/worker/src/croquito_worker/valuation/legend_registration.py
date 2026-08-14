"""Registro fino dos bboxes da legenda contra a tinta da prancha.

Espelho de `croquito_worker.vision.register_to_ink`: mesma disciplina de assentamento
determinístico contra a tinta, aplicada à legenda em vez de à geometria. Este módulo
corrige o **assentamento**, nunca o **conteúdo**: rótulo, quantidade, unidade, id e
status permanecem exatamente os que a extração leu. Só `evidence.bbox` pode mudar.

Quatro rodadas reais de homologação mostraram quatro defeitos distintos, e o método
reflete os quatro:

- **Toca, 1ª rodada**: bboxes deslocados verticalmente por um viés aproximadamente
  constante. Um Δ único bastava, mas o casamento ordem-preservado sozinho "deslizava em
  bloco" quando o desvio passava do passo entre linhas e havia faixa de sobra (título,
  cabeçalho de seção) para a distância mínima vazar para a interpretação errada.
- **Toca, 2ª rodada**: medindo no overlay da 1ª correção, o desvio NÃO era constante —
  crescia com Y (item 1: +585 px; item 15: +890 px), razão consistente ~1,23-1,28. É
  erro de ESCALA na normalização Y do provedor, não deslocamento. Um Δ puro nunca casa
  esse padrão; o modelo teve que virar afim (`y' = a·y + b`), com Δ puro como caso
  particular (`a=1`).
- **Toca, 3ª rodada (homologação)**: uma extração NOVA do mesmo PDF veio com bboxes de
  x-range diferente do calibrado; o filtro de faixas por divisor não reduziu o ruído
  (34 faixas, não as ~17 esperadas) e o gate afim recusou CERTO (confiança ~1,8e-5) —
  mas o **fallback antigo** (trava generosa por altura da faixa) assentou 11 itens
  deslizados ~6 linhas cada, com âncora de evidência mentindo sobre onde o número foi
  lido. Duas correções: (a) um estágio de detecção PREFERENCIAL por réguas de tabela —
  a legenda real e a sintética são tabelas com bordas, e cabeçalho de SEÇÃO (não o
  cabeçalho de COLUNA da própria tabela) fica fora delas e some por construção; quando o
  número de células bordejadas bate exatamente com o número de itens, o casamento é uma
  bijeção direta, sem precisar de transformação nenhuma; (b) o fallback residual (usado
  só quando NADA — nem réguas, nem afim — passa no gate de confiança) parou de absorver
  qualquer distância: passou a só assentar item cuja faixa mais próxima estivesse a no
  máximo 1,2x o passo mediano de distância — o resto ficava intocado.
- **Toca, 4ª rodada (homologação)**: uma extração NOVA repetiu o erro de ESCALA da 2ª
  rodada, e o afim recusou CERTO de novo — 14/15, a célula de NOTA no meio da tabela
  quebra a bijeção exata por 1. Mas a trava de 1,2x o passo da 3ª rodada ainda assentou 9
  itens na SEÇÃO VIZINHA errada: 1,2x o passo é MAIOR que o próprio passo entre linhas
  adjacentes, então dentro de um aglomerado denso de linhas sempre existe alguma célula
  "perto o bastante" — o limite geométrico sozinho não garante nada. Duas correções
  estruturais, não mais calibração incremental: (a) um filtro de célula por RÉGUA
  VERTICAL INTERNA — linha de ITEM de verdade tem um divisor rótulo|valor DENTRO da
  própria célula, com tinta dos dois lados; célula de NOTA mesclada (largura total, sem
  divisor nenhum) não tem — na Toca isso derruba as células de 20 para as 15 esperadas,
  fechando a bijeção exata sem precisar de transformação nenhuma; (b) o fallback residual
  foi **retirado por completo**: sem bijeção de réguas e sem transformação global
  confiante, NENHUM item é assentado — todos ficam intocados e em `unmatched_item_ids`.
  Errado nunca; intocado e declarado, sempre.

O método é determinístico e sem chamada paga:

0. **Réguas de tabela (estágio preferencial)**: dentro da coluna da legenda, procuram-se
   linhas horizontais quase contínuas e finas (réguas — bordas de célula); o intervalo
   entre duas réguas consecutivas com tinta de texto dentro é uma célula candidata a
   linha de item. Dessas células, só sobrevivem as que têm um divisor vertical INTERNO
   (rótulo|valor) com tinta dos dois lados — uma célula de NOTA mesclada, sem divisor
   nenhum, cai fora (`_filter_cells_by_internal_divider`); se NENHUMA célula do conjunto
   tem divisor interno (prancha cuja tabela não desenha essa linha, como a fixture
   sintética original deste repositório), o filtro não tem sinal pra decidir e mantém
   todas. Com célula-por-item exato, a ordem já é a resposta (bijeção); senão, as células
   (um conjunto tipicamente bem mais limpo que faixas de texto) entram no mesmo
   estimador de transformação do passo 2. Sem réguas confiáveis, cai para os passos 1-2
   com faixas de texto.
1. **Detecção de faixas de texto + filtro de faixas candidatas**: na coluna da legenda
   (união dos intervalos X dos bboxes dos itens), soma-se tinta por linha Y e extraem-se
   faixas contíguas; uma linha de item tem tinta TANTO na região do rótulo (esquerda)
   quanto na de quantidade/unidade (direita, depois do divisor da tabela) — título de
   seção só tem tinta na esquerda. Fallback: se sobrar menos faixas que itens, usa-se o
   conjunto sem filtro.
2. **Estimativa da transformação global**: varre-se hipóteses de `(a, b)` a partir de
   pares ordem-consistentes de (item, faixa/célula) e escolhe-se a que melhor alinha
   `{a·centro do item + b}` ao conjunto de candidatas. Se a melhor hipótese não vence a
   segunda melhor hipótese DISTINTA por margem nomeada, ou não explica TODOS os itens, a
   transformação não é aplicada: nunca se chuta entre duas interpretações plausíveis.
3. **Casamento preservando a ordem**: itens (já transformados, quando confiante)
   ordenados pelo topo atual do bbox e candidatas ordenadas pelo topo, casados por
   programação dinâmica que minimiza, em primeiro lugar, o número de itens sem par e,
   só depois, a soma das distâncias entre centros. SEM transformação global confiante
   (nem por réguas, nem por afim), o casamento nem roda: nenhum item é assentado, todos
   ficam intocados em `unmatched_item_ids` — a 4ª rodada mostrou que qualquer trava fixa
   de distância residual, por mais apertada, ainda pode cair dentro do aglomerado denso
   de linhas vizinhas e assentar errado.

`restore_raw_bboxes` é o companheiro operacional do registro: reverte `evidence.bbox`
para o `before` gravado num `LegendRegistrationReport.adjusted` de uma rodada anterior,
permitindo reprocessar um pacote já registrado do zero — com um pipeline mais novo, sem
nova chamada paga (ver `--restore-raw` de `register-takeoff`).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from itertools import pairwise
from pathlib import Path
from typing import Final, Literal

import cv2
import numpy as np

from croquito_valuation.catalog import file_sha256
from croquito_valuation.errors import ValuationValidationError
from croquito_valuation.takeoff import PlateBox, TakeoffItem, TakeoffPacket

# --- constantes nomeadas -----------------------------------------------------------

INK_LUMINANCE_THRESHOLD: Final = 200
"""Luminância (0-255, cinza) abaixo da qual um pixel conta como tinta. Separa o texto da
legenda (escrito em cor escura) do papel branco e das linhas claras do grid da tabela —
um limiar fixo, não Otsu, para que o resultado não dependa de quanto desenho existe no
resto da página (que não tem relação nenhuma com a legenda)."""

ROW_INK_RATIO_THRESHOLD: Final = 0.02
"""Fração mínima de pixels de tinta numa linha Y, sobre a largura da coluna da legenda,
para a linha contar como parte de uma faixa de texto. Baixa o bastante para pegar o
traço fino de uma letra isolada, alta o bastante para não confundir ruído de
anti-aliasing disperso com texto."""

BAND_MERGE_GAP_PX: Final = 6
"""Vão vertical (linhas sem tinta suficiente) tolerado DENTRO da mesma faixa — maior que
o espaço entre as hastes de uma letra, bem menor que o espaço entre duas linhas da
legenda; existe para não fatiar uma única linha de texto em várias faixas por causa de
uma falha isolada de amostragem."""

MIN_BAND_HEIGHT_PX: Final = 6
"""Faixa mais baixa que isto é ruído (borda fina de grade, artefato de compressão), não
uma linha de texto: descartada antes do casamento."""

BAND_LABEL_REGION_END_RATIO: Final = 1.0 / 3.0
"""Fim da região de RÓTULO, como fração da largura da coluna da legenda: onde o nome do
elemento certamente cai, título de seção incluído. Toda faixa candidata precisa de tinta
aqui — ver `_filter_item_row_bands`."""

BAND_VALUE_REGION_START_RATIO: Final = 2.0 / 3.0
"""Início da região de QUANTIDADE/UNIDADE, como fração da largura da coluna — "o último
terço". Fallback do filtro de faixa candidata quando nenhum divisor de tabela confiável
é detectado (ver `BAND_DIVIDER_MIN_AGREEMENT_COUNT`): exigir alguma tinta aqui, e não só
na região de rótulo, já derruba título/cabeçalho de seção na maioria dos casos. Calibrado
contra a coluna real da Toca: o texto de quantidade/unidade das linhas de item começa em
~70% da largura e o de título nunca passa de ~22%."""

BAND_DIVIDER_SEARCH_START_RATIO: Final = 1.0 / 3.0
"""Onde a busca pelo divisor label|valor da tabela começa, como fração da largura da
coluna — evita confundir com o alinhamento à esquerda do rótulo: quase toda linha começa
tinta perto de x=0, o que teria alta concordância ali por um motivo completamente
diferente de linha de grade."""

BAND_DIVIDER_COVERAGE_RATIO: Final = 0.8
"""Fração mínima de linhas de uma faixa com tinta numa coluna candidata para essa coluna
contar como "o divisor atravessa esta faixa". Uma linha de grade vertical cruza quase
100% da altura de QUALQUER faixa que ela atravesse — rótulo, item de verdade, ou um
cabeçalho de seção contaminado por anotação vizinha na mesma altura; um traço de
caractere que só cruza aquela coluna por acaso cobre bem menos e varia faixa a faixa
(depende de qual dígito/letra caiu ali). Foi exatamente essa diferença — 100% de
cobertura numa linha de item de verdade contra 42% numa faixa de cabeçalho contaminada
por um texto de área vizinho, medida na prancha real da Toca — que motivou não usar só
"tem tinta em algum lugar do último terço" (ambas tinham)."""

BAND_DIVIDER_MIN_AGREEMENT_COUNT: Final = 3
"""Quantidade mínima de faixas cruas concordando (cobertura alta na MESMA coluna) para o
divisor contar como confiavelmente detectado. Prancha sem linha de grade nenhuma (a
fixture sintética deste repositório, por exemplo, que separa rótulo e quantidade só por
posição de texto, sem traçar linha) nunca atinge isso — o filtro cai então para o
critério mais simples de região (`BAND_VALUE_REGION_START_RATIO`)."""

BAND_VERTICAL_MARGIN_PX: Final = 4
"""Folga somada acima e abaixo da faixa de tinta ao formar o bbox novo do item: o texto
tem hastes e cedilhas que passam um pouco da caixa de tinta detectada; sem a folga o
recorte cortaria a própria letra."""

MAX_MATCH_DISTANCE_PITCH_RATIO: Final = 0.5
"""Fração do passo mediano entre faixas vizinhas usada como distância máxima aceita no
casamento FINAL, depois da transformação aplicada (ou sem nenhuma, ver
`resolve_item_bands`). Metade do passo é o próprio limite geométrico de ambiguidade
entre duas linhas adjacentes — além disso o item está objetivamente mais perto da linha
vizinha do que da própria."""

MATCH_SCORE_DISTANCE_SCALE: Final = 1_000_000.0
"""Converte o custo do casamento ordem-preservado — `(itens casados, soma das
distâncias)` — num único número para escolher entre hipóteses: o número de itens casados
SEMPRE domina (a soma das distâncias, dividida por isto, nunca alcança 1.0 para qualquer
imagem de tamanho real), e a distância só desempata entre hipóteses que casam o MESMO
número de itens. Ver `_hypothesis_score`."""

GLOBAL_TRANSFORM_PEAK_SEPARATION_RATIO: Final = 0.5
"""Duas hipóteses só competem pela confiança se a posição que cada uma prediz para o
item mediano (ver `estimate_global_transform`) estiver separada por pelo menos esta
fração do passo mediano entre faixas. Sem essa distância mínima, uma hipótese vizinha da
vencedora (mesma interpretação de linha, só um pouco diferente por causa de qual par
âncora gerou o `(a, b)`) contaria como "segunda melhor hipótese" e bloquearia toda
aplicação — a competição real é entre interpretações de LINHA diferentes."""

GLOBAL_TRANSFORM_CONFIDENCE_MARGIN_RATIO: Final = 0.05
"""Margem mínima, como fração do placar máximo teórico (nº de itens — cada item
contribui no máximo 1.0), que a melhor hipótese tem de vencer da segunda melhor hipótese
DISTINTA para ser aplicada. Sem essa margem — o caso da legenda perfeitamente periódica,
em que deslizar um passo inteiro casa tudo de novo do mesmo jeito, placar idêntico até a
última casa — a transformação não é aplicada: nunca se chuta entre duas interpretações
igualmente plausíveis. O valor é baixo de propósito: com a tolerância apertada de
`GLOBAL_TRANSFORM_SCORE_TOLERANCE_PITCH_RATIO`, uma hipótese genuinamente correta já
abre margem de várias unidades sobre a concorrente mais próxima; só o padrão exatamente
periódico chega a margem zero."""

GLOBAL_AFFINE_SCALE_MIN: Final = 0.7
GLOBAL_AFFINE_SCALE_MAX: Final = 1.4
"""Intervalo aceito para o coeficiente de escala `a` do modelo afim `y' = a·y + b`. Cobre
o defeito real observado na 2ª rodada da Toca (escala ~1,23-1,28) com folga nos dois
sentidos, sem aceitar uma transformação absurda (encolher pela metade ou dobrar a
legenda) que quase certamente seria erro de casamento, não normalização de VLM."""

GLOBAL_AFFINE_MIN_SEPARATION_PITCH_RATIO: Final = 3.0
"""Separação vertical mínima entre os dois itens-âncora de uma hipótese `(a, b)`, como
múltiplo do passo mediano entre faixas. Derivar `a` de dois pontos quase coincidentes
amplifica qualquer ruído de pixel numa escala absurda; exigir vários passos de distância
mantém a hipótese numericamente estável."""

GLOBAL_AFFINE_SCALE_GRID_STEP: Final = 0.01
GLOBAL_AFFINE_OFFSET_GRID_STEP_PX: Final = 4.0
"""Granularidade da grade em que as hipóteses `(a, b)` são arredondadas antes de
pontuadas. Pares-âncora diferentes que descrevem a MESMA leitura de linha geram `(a, b)`
numericamente próximos, não idênticos; sem colapsar numa grade, cada um pagaria o custo
de pontuação de novo — com dezenas de itens e faixas, ficaria caro à toa. A grade também
é o que torna o resultado determinístico e independente da ordem de geração dos pares."""

RULING_SEARCH_MARGIN_RATIO: Final = 0.5
"""Margem de busca de réguas/faixas, acima e abaixo da união dos bboxes propostos, como
fração do PRÓPRIO vão (topo do primeiro item ao fundo do último item). Generoso o
bastante pra cobrir desvios reais (a 3ª rodada da Toca deslizou até ~220px, bem dentro
da margem pro vão de ~1500px dos 15 itens), apertado o bastante pra excluir tabelas
completamente alheias que por acaso caem na mesma coluna X mais adiante na página —
visto na prancha real: uma tabela em y~5300-5900, bem longe da legenda de interesse,
tinha estrutura parecida o bastante pra passar pelo filtro de conteúdo quando a busca
não tinha limite de altura nenhum."""

RULING_SEARCH_MIN_MARGIN_PX: Final = 300
"""Piso da margem de busca — cobre o caso degenerado de um vão curto entre o primeiro e
o último item (poucos itens, ou proposta pouco espalhada), quando a margem proporcional
sozinha seria curta demais pra alcançar a linha verdadeira."""

RULING_MIN_WIDTH_RATIO: Final = 0.6
"""Fração mínima da largura da coluna com tinta numa linha Y para ela contar como régua
(borda horizontal de célula da tabela) — bem mais exigente que o limiar de faixa de
texto (`ROW_INK_RATIO_THRESHOLD`, 2%), porque uma régua de verdade atravessa quase toda
a largura da tabela, não só o traço de uma letra. Calibrado contra a coluna real da
Toca: a borda de célula cobre ~83% da largura (não 100%, porque a coluna de busca é
folgada em relação à borda física da tabela); 60% separa isso com folga do texto mais
largo que existe (uma linha de item inteira, que também pode chegar perto de 80-90%,
mas não de forma FINA — ver `RULING_MAX_HEIGHT_PX`)."""

RULING_MAX_HEIGHT_PX: Final = 3
"""Altura máxima de uma régua, em pixels — uma linha de grade é fina (1-2px na prancha
real e na sintética); texto largo o bastante pra cruzar `RULING_MIN_WIDTH_RATIO` da
coluna ainda tem a altura de uma linha de fonte inteira, bem mais que isto."""

RULING_MERGE_GAP_PX: Final = 2
"""Vão vertical tolerado dentro da mesma régua — anti-aliasing pode deixar 1px sem
atingir o limiar de largura entre dois pixels que são, na prática, a mesma linha."""

RULING_MIN_CELL_HEIGHT_PX: Final = MIN_BAND_HEIGHT_PX
"""Altura mínima do vão entre duas réguas consecutivas para contar como célula — mesmo
piso da faixa de texto: um vão mais raso que isso é ruído de detecção de régua, não uma
linha de item."""

VERTICAL_DIVIDER_MARGIN_RATIO: Final = 0.1
"""Margem, como fração da largura da célula, que qualquer candidata a divisor vertical
tem de guardar de `left`/`right` para entrar na busca por `detect_vertical_rulings` — sem
essa margem, a própria borda EXTERIOR da tabela (esquerda/direita) seria confundida com o
divisor rótulo|valor interno: a fixture sintética deste repositório desenha cada linha
como um retângulo fechado (`page.draw_rect` em `plate.py`), e o bbox de cada item é
recortado exatamente na mesma posição da borda esquerda/direita da tabela — sem margem,
o anti-aliasing daquela borda vazaria "tinta" pros dois lados do próprio traço, por um
motivo que nada tem a ver com texto de rótulo/valor de verdade. O divisor real fica perto
do meio da célula; a borda exterior fica nas pontas — 10% de folga de cada lado separa
os dois com sobra."""

VERTICAL_DIVIDER_MIN_HEIGHT_RATIO: Final = 0.6
"""Fração mínima da ALTURA da célula com tinta numa coluna X para ela contar como régua
vertical (divisor interno rótulo|valor) — mesma ideia de `RULING_MIN_WIDTH_RATIO`,
transposta: linha por coluna, não coluna por linha. Um divisor de verdade atravessa quase
toda a própria altura da célula; um traço de caractere (dígito, letra) que por acaso
alinha numa coluna fica bem abaixo disso."""

VERTICAL_DIVIDER_MAX_WIDTH_PX: Final = 3
"""Largura máxima de uma régua vertical, em pixels — mesma ideia de `RULING_MAX_HEIGHT_PX`,
transposta: um divisor de tabela é fino, texto largo o bastante pra cruzar
`VERTICAL_DIVIDER_MIN_HEIGHT_RATIO` da altura ainda tem a largura de um traço de fonte
inteiro, bem mais que isto."""

VERTICAL_DIVIDER_MERGE_GAP_PX: Final = 2
"""Vão horizontal tolerado dentro da mesma régua vertical — mesma ideia de
`RULING_MERGE_GAP_PX`, transposta."""

RULING_TRIMMED_BIJECTION_MAX_STD_PITCH_RATIO: Final = 0.6
"""Quando há exatamente UMA célula a mais que itens, a régua sobrando costuma ser o
cabeçalho de COLUNA da própria tabela (`ELEMENTO/QUANT/UN` ou equivalente) — sempre a
PRIMEIRA célula da tabela, por convenção — mas também pode ser lixo em qualquer ponta.
Este módulo tenta as duas bijeções possíveis (descartando a primeira célula, ou a
última) e mede o quão CONSISTENTE cada uma é: o desvio de posição de cada item pra sua
célula deveria ser quase igual entre todos os itens, já que um único cabeçalho de tabela
espúrio não muda a relação entre os itens de verdade. A hipótese vencedora só é aceita
se o desvio-padrão dos deslocamentos, como fração do passo mediano entre células, ficar
abaixo deste teto — senão nenhuma das duas bijeções é confiável (ex.: a célula extra é
uma nota no MEIO da tabela, não numa ponta — visto na prancha real da Toca) e o módulo
cai para a estimativa de transformação completa sobre todas as células. Calibrado: o
caso do cabeçalho de coluna (prancha sintética, desvio uniforme OU heterogêneo mas ainda
sistemático) fica em ~0,007-0,45; o caso da nota no meio da tabela real fica em ~2,8 —
folga grande nos dois sentidos."""

LEGEND_REGISTRATION_DIGEST_MISMATCH: Final = "LEGEND_REGISTRATION_DIGEST_MISMATCH"
"""Código próprio deste módulo, e não o do overlay (`TAKEOFF_OVERLAY_DIGEST_MISMATCH`):
o defeito que os dois checam é o mesmo — âncora de evidência sobre a imagem errada mente
— mas são operações diferentes (registro de bbox, não renderização), e um código
compartilhado confundiria quem lê o log tentando saber qual das duas rodou."""


@dataclass(frozen=True, slots=True)
class TextBand:
    """Uma faixa contígua de tinta detectada na coluna da legenda, em pixels da imagem."""

    top: int
    bottom: int

    @property
    def height(self) -> int:
        return self.bottom - self.top

    @property
    def center(self) -> float:
        return (self.top + self.bottom) / 2.0


@dataclass(frozen=True, slots=True)
class LabeledSpan:
    """Um item reduzido ao que o casamento realmente usa: id e intervalo vertical.

    Existe para que a lógica de casamento (`match_spans_to_bands`,
    `estimate_global_transform`) seja testável com faixas e posições sintéticas, sem
    construir `TakeoffItem`/`TakeoffPacket` inteiros — o mesmo motivo por que
    `balloon_layout` em `takeoff_overlay.py` opera sobre `PlateBox`, não sobre o item."""

    id: str
    top: float
    bottom: float

    @property
    def center(self) -> float:
        return (self.top + self.bottom) / 2.0


@dataclass(frozen=True, slots=True)
class GlobalTransformEstimate:
    """Resultado da varredura de `(a, b)`: a melhor hipótese, o placar dela e se ela
    venceu com confiança suficiente para ser aplicada. `scale=1.0` é o caso particular de
    um desvio vertical puro — o defeito da 1ª rodada da Toca; `scale` diferente de 1 é o
    erro de normalização visto na 2ª rodada."""

    scale: float
    offset_px: float
    score: float
    confidence_margin: float
    applied: bool


RegistrationMethod = Literal["rulings", "text_bands", "none"]
"""Qual fonte de candidatas decidiu o casamento final: `"rulings"` — réguas de tabela,
por bijeção direta ou por transformação confiante sobre as células; `"text_bands"` —
faixas de texto (com filtro de divisor/região), por transformação confiante; `"none"` —
nenhuma das duas teve confiança suficiente; NADA foi assentado (o fallback residual foi
retirado na 4ª rodada — ver módulo), todo item aparece intocado em `unmatched_item_ids`."""


@dataclass(frozen=True, slots=True)
class LegendRegistrationReport:
    """O que o registro ajustou, o que ficou intocado e como a transformação global se
    saiu.

    `adjusted` é uma lista de `{item_id, before, after, shift_px}` — `before`/`after` são
    o `PlateBox` (`model_dump()`) antes e depois, `shift_px` é o deslocamento vertical do
    topo (`after.top - before.top`). `unmatched_item_ids` são os itens sem par confiável:
    o bbox deles não muda. `band_count` é o número de candidatas (réguas ou faixas de
    texto, o que o `method` declara) que o casamento realmente usou. `method` diz qual
    fonte decidiu — ver `RegistrationMethod`.
    `global_scale`/`global_shift_px`/`shift_score`/`shift_confidence` vêm de
    `GlobalTransformEstimate` (todos `None` quando não há candidatas suficientes para
    estimar uma transformação, OU quando o casamento foi por bijeção direta de réguas —
    não precisa de transformação nenhuma); `global_scale`/`global_shift_px` em particular
    são `None` sempre que a transformação estimada NÃO foi aplicada — inclusive quando
    `shift_score`/`shift_confidence` existem, porque a ambiguidade foi detectada e
    declarada, não escondida."""

    adjusted: list[dict[str, object]]
    unmatched_item_ids: list[str]
    band_count: int
    method: RegistrationMethod
    global_scale: float | None
    global_shift_px: int | None
    shift_score: float | None
    shift_confidence: float | None


def detect_text_bands(image: np.ndarray, *, left: int, right: int) -> list[TextBand]:
    """Faixas de tinta na coluna [left, right) da imagem, mescladas e filtradas — SEM o
    filtro de linha de item (ver `_filter_item_row_bands`, aplicado por
    `register_legend_bboxes` em cima do resultado desta função).

    Varre a imagem inteira em Y (não só a vizinhança dos bboxes atuais): o item pode ter
    sido proposto longe da própria linha, e é exatamente essa distância que o registro
    precisa enxergar para corrigir. Pública para ser testável diretamente com uma imagem
    sintética, sem passar pelo resto do pipeline."""
    column = image[:, left:right]
    grayscale = cv2.cvtColor(column, cv2.COLOR_BGR2GRAY)
    ink = grayscale < INK_LUMINANCE_THRESHOLD
    row_ink = ink.sum(axis=1)
    width = right - left
    row_threshold = max(1.0, width * ROW_INK_RATIO_THRESHOLD)
    is_ink_row = row_ink >= row_threshold

    indices = np.flatnonzero(is_ink_row)
    if indices.size == 0:
        return []
    runs: list[list[int]] = [[int(indices[0]), int(indices[0]) + 1]]
    for value in indices[1:]:
        value = int(value)
        if value - runs[-1][1] <= BAND_MERGE_GAP_PX:
            runs[-1][1] = value + 1
        else:
            runs.append([value, value + 1])
    return [
        TextBand(top=start, bottom=end) for start, end in runs if end - start >= MIN_BAND_HEIGHT_PX
    ]


def detect_rulings(image: np.ndarray, *, left: int, right: int) -> list[int]:
    """Posição Y (centro) de cada régua horizontal detectada na coluna [left, right) —
    borda de célula de tabela: linha quase contínua (`RULING_MIN_WIDTH_RATIO` da
    largura) e fina (`RULING_MAX_HEIGHT_PX`). Pública para ser testável diretamente com
    uma imagem sintética."""
    column = image[:, left:right]
    grayscale = cv2.cvtColor(column, cv2.COLOR_BGR2GRAY)
    ink = grayscale < INK_LUMINANCE_THRESHOLD
    width = right - left
    row_ink_fraction = ink.mean(axis=1) if width > 0 else np.zeros(0)
    is_ruling_row = row_ink_fraction >= RULING_MIN_WIDTH_RATIO

    indices = np.flatnonzero(is_ruling_row)
    if indices.size == 0:
        return []
    runs: list[list[int]] = [[int(indices[0]), int(indices[0])]]
    for value in indices[1:]:
        value = int(value)
        if value - runs[-1][1] <= RULING_MERGE_GAP_PX:
            runs[-1][1] = value
        else:
            runs.append([value, value])
    return [
        round((start + end) / 2) for start, end in runs if (end - start + 1) <= RULING_MAX_HEIGHT_PX
    ]


def _cells_from_rulings(
    rulings: list[int], image: np.ndarray, *, left: int, right: int
) -> list[TextBand]:
    """Intervalos entre réguas consecutivas com tinta de TEXTO dentro — célula candidata
    a linha de item. Um vão entre réguas sem tinta nenhuma (linha em branco da tabela,
    ou duas réguas vizinhas por artefato) não vira célula."""
    if len(rulings) < 2:
        return []
    width = right - left
    row_threshold = max(1.0, width * ROW_INK_RATIO_THRESHOLD)
    cells: list[TextBand] = []
    for top, bottom in pairwise(sorted(rulings)):
        if bottom - top < RULING_MIN_CELL_HEIGHT_PX:
            continue
        strip = image[top:bottom, left:right]
        grayscale = cv2.cvtColor(strip, cv2.COLOR_BGR2GRAY)
        row_ink = (grayscale < INK_LUMINANCE_THRESHOLD).sum(axis=1)
        if not bool((row_ink >= row_threshold).any()):
            continue
        cells.append(TextBand(top=top, bottom=bottom))
    return cells


def detect_vertical_rulings(image: np.ndarray, *, left: int, right: int) -> list[int]:
    """Posição X (centro) de cada régua vertical quase contínua na ALTURA da imagem
    recebida (tipicamente uma célula já recortada em Y) — divisor interno rótulo|valor de
    uma linha de tabela. Mesma técnica de `detect_rulings`, transposta: coluna por coluna
    em vez de linha por linha (`VERTICAL_DIVIDER_MIN_HEIGHT_RATIO`/
    `VERTICAL_DIVIDER_MAX_WIDTH_PX`). Pública para ser testável diretamente com uma célula
    sintética."""
    column = image[:, left:right]
    grayscale = cv2.cvtColor(column, cv2.COLOR_BGR2GRAY)
    ink = grayscale < INK_LUMINANCE_THRESHOLD
    height = image.shape[0]
    width = max(0, right - left)
    col_ink_fraction = ink.mean(axis=0) if height > 0 else np.zeros(width)
    is_divider_col = col_ink_fraction >= VERTICAL_DIVIDER_MIN_HEIGHT_RATIO

    indices = np.flatnonzero(is_divider_col)
    if indices.size == 0:
        return []
    runs: list[list[int]] = [[int(indices[0]), int(indices[0])]]
    for value in indices[1:]:
        value = int(value)
        if value - runs[-1][1] <= VERTICAL_DIVIDER_MERGE_GAP_PX:
            runs[-1][1] = value
        else:
            runs.append([value, value])
    return [
        left + round((start + end) / 2)
        for start, end in runs
        if (end - start + 1) <= VERTICAL_DIVIDER_MAX_WIDTH_PX
    ]


def _cell_has_internal_divider(image: np.ndarray, cell: TextBand, *, left: int, right: int) -> bool:
    """A célula tem um divisor vertical INTERNO com tinta dos dois lados — sinal de linha
    de ITEM de verdade (rótulo à esquerda, quantidade/unidade à direita do divisor). Uma
    célula de NOTA mesclada (largura total, sem divisor nenhum, visto na prancha real da
    Toca) não tem nenhuma régua vertical AQUI: a busca fica restrita a
    `VERTICAL_DIVIDER_MARGIN_RATIO` de folga longe de `left`/`right`, pra nunca confundir
    a própria borda EXTERIOR da tabela — que também é uma linha vertical fina e contínua
    na altura de QUALQUER célula que ela atravesse — com o divisor de verdade."""
    width = right - left
    margin = max(1, round(width * VERTICAL_DIVIDER_MARGIN_RATIO))
    search_left, search_right = left + margin, right - margin
    if search_right <= search_left:
        return False
    strip = image[cell.top : cell.bottom, :]
    dividers = detect_vertical_rulings(strip, left=search_left, right=search_right)
    if not dividers:
        return False
    grayscale = cv2.cvtColor(strip, cv2.COLOR_BGR2GRAY)
    ink = grayscale < INK_LUMINANCE_THRESHOLD

    def _row_threshold(side_width: int) -> float:
        return max(1.0, side_width * ROW_INK_RATIO_THRESHOLD)

    for divider_x in dividers:
        left_width, right_width = divider_x - left, right - divider_x - 1
        if left_width <= 0 or right_width <= 0:
            continue
        left_ink_rows = ink[:, left:divider_x].sum(axis=1)
        right_ink_rows = ink[:, divider_x + 1 : right].sum(axis=1)
        has_left_ink = bool((left_ink_rows >= _row_threshold(left_width)).any())
        has_right_ink = bool((right_ink_rows >= _row_threshold(right_width)).any())
        if has_left_ink and has_right_ink:
            return True
    return False


def _filter_cells_by_internal_divider(
    image: np.ndarray, cells: list[TextBand], *, left: int, right: int
) -> list[TextBand]:
    """Mantém só as células de régua com divisor vertical interno (rótulo|valor) — ver
    `_cell_has_internal_divider`. Graciosamente NÃO filtra quando NENHUMA célula do
    conjunto tem divisor: a fixture sintética original deste repositório desenha cada
    linha como um retângulo fechado, sem traço nenhum entre rótulo e valor, e ali o filtro
    não tem sinal algum para decidir — melhor manter tudo (o resto do pipeline, bijeção ou
    transformação, já lida com esse caso) do que descartar às cegas."""
    flags = [_cell_has_internal_divider(image, cell, left=left, right=right) for cell in cells]
    if not any(flags):
        return list(cells)
    return [cell for cell, flag in zip(cells, flags, strict=True) if flag]


def _band_column_coverage(
    image: np.ndarray, band: TextBand, *, left: int, right: int
) -> np.ndarray:
    """Fração de linhas do `band` com tinta, por coluna X — índice 0 é `left`.

    Uma coluna cruzada por uma linha de grade vertical se aproxima de 1.0 (a linha
    atravessa quase toda a altura da faixa); uma coluna que só cruza um traço de
    caractere fica bem abaixo disso."""
    if band.bottom <= band.top or right <= left:
        return np.zeros(max(0, right - left))
    strip = image[band.top : band.bottom, left:right]
    grayscale = cv2.cvtColor(strip, cv2.COLOR_BGR2GRAY)
    return (grayscale < INK_LUMINANCE_THRESHOLD).mean(axis=0)


def _detect_divider_offset(coverage_by_band: list[np.ndarray], *, width: int) -> int | None:
    """Posição X do divisor label|valor da tabela (relativa a `left`), se houver um
    confiável — `None` se nenhuma coluna reunir concordância suficiente entre faixas
    (ver `BAND_DIVIDER_MIN_AGREEMENT_COUNT`), caso em que quem chama cai no filtro mais
    simples de região."""
    search_start = round(width * BAND_DIVIDER_SEARCH_START_RATIO)
    if search_start >= width:
        return None
    agreement = np.zeros(width, dtype=int)
    for coverage in coverage_by_band:
        agreement += coverage >= BAND_DIVIDER_COVERAGE_RATIO
    best_offset = search_start + int(np.argmax(agreement[search_start:]))
    if agreement[best_offset] < BAND_DIVIDER_MIN_AGREEMENT_COUNT:
        return None
    return best_offset


def _filter_item_row_bands(
    image: np.ndarray,
    bands: list[TextBand],
    *,
    left: int,
    right: int,
    item_count: int,
) -> list[TextBand]:
    """Mantém só as faixas com tinta na região de rótulo E na região de quantidade/
    unidade — título de seção só tem tinta na esquerda, e o resto do que a coluna X larga
    também capta (desenho, notas, títulos de outras caixas) raramente tem as duas.

    Quando a prancha tem linha de grade (divisor entre rótulo e valor — a maioria das
    tabelas reais tem), o lado do valor é checado ali especificamente, por COBERTURA
    (`BAND_DIVIDER_COVERAGE_RATIO`), não por presença de qualquer tinta: uma anotação
    vizinha que também caia no último terço da coluna (visto na prancha real da Toca,
    onde "ÁREA DE INTERVENÇÃO = ..." ficou ao lado do título "PISO E REVESTIMENTO") tem
    tinta ali, mas não cobre a coluna do divisor como uma linha de grade contínua cobre.
    Sem divisor confiável (prancha sem linha de grade, como a fixture sintética deste
    repositório), cai para "alguma tinta no último terço" (`BAND_VALUE_REGION_START_RATIO`).

    Fallback final: se sobrar menos faixas candidatas que itens no pacote, o filtro
    devolve o conjunto ORIGINAL — um filtro agressivo demais que deixa itens sem para
    onde ir é pior que nenhum filtro; a trava de distância e o gate de confiança já
    protegem contra casamento errado de qualquer forma."""
    width = right - left
    coverage_by_band = [
        _band_column_coverage(image, band, left=left, right=right) for band in bands
    ]
    divider_offset = _detect_divider_offset(coverage_by_band, width=width)
    label_end = round(width * BAND_LABEL_REGION_END_RATIO)
    value_start = round(width * BAND_VALUE_REGION_START_RATIO)

    candidates: list[TextBand] = []
    for band, coverage in zip(bands, coverage_by_band, strict=True):
        if not bool(coverage[:label_end].any()):
            continue
        has_value_ink = (
            bool(coverage[divider_offset] >= BAND_DIVIDER_COVERAGE_RATIO)
            if divider_offset is not None
            else bool(coverage[value_start:].any())
        )
        if has_value_ink:
            candidates.append(band)
    return candidates if len(candidates) >= item_count else list(bands)


def _median(values: list[float]) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    middle = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[middle]
    return (ordered[middle - 1] + ordered[middle]) / 2.0


def _median_pitch(bands: Sequence[TextBand]) -> float | None:
    """Passo mediano entre centros de faixas VIZINHAS — o "tamanho de uma linha" da
    legenda em pixels. `None` com menos de duas faixas: não há passo para medir."""
    if len(bands) < 2:
        return None
    centers = sorted(band.center for band in bands)
    return _median([b - a for a, b in pairwise(centers)])


def _dp_match_cost(
    spans: Sequence[LabeledSpan],
    bands: Sequence[TextBand],
    *,
    scale: float,
    offset: float,
    max_distance: float,
) -> tuple[int, float]:
    """O custo final — `(spans sem faixa, soma das distâncias)` — que
    `match_spans_to_bands` chegaria para esta hipótese, sem reconstruir a atribuição.

    Existe para pontuar uma hipótese de transformação com o MESMO critério que decide o
    casamento de verdade (preserva ordem, preserva unicidade de faixa), não uma
    aproximação por vizinho mais próximo independente por item — essa aproximação deixa
    uma hipótese ERRADA "roubar" placar reatribuindo itens a faixas fora de ordem, que o
    casamento de verdade nunca aceitaria. Só a linha anterior da tabela de programação
    dinâmica é mantida (não a matriz inteira): mais barato, e é tudo que a pontuação
    precisa."""
    if not spans or not bands:
        return (len(spans), 0.0)
    ordered = sorted(spans, key=lambda span: span.top)
    band_count = len(bands)
    previous: list[tuple[int, float]] = [(0, 0.0)] * (band_count + 1)
    for span in ordered:
        span_center = scale * span.center + offset
        current: list[tuple[int, float]] = [(previous[0][0] + 1, previous[0][1])]
        for j in range(1, band_count + 1):
            best = current[j - 1]
            skip_span_cost = (previous[j][0] + 1, previous[j][1])
            if skip_span_cost < best:
                best = skip_span_cost
            distance = abs(span_center - bands[j - 1].center)
            if distance <= max_distance:
                match_cost = (previous[j - 1][0], previous[j - 1][1] + distance)
                if match_cost < best:
                    best = match_cost
            current.append(best)
        previous = current
    return previous[band_count]


def _hypothesis_score(matched_count: int, total_distance: float) -> float:
    """Um único número para escolher e comparar hipóteses — ver `MATCH_SCORE_DISTANCE_SCALE`."""
    return matched_count - total_distance / MATCH_SCORE_DISTANCE_SCALE


def _affine_hypotheses(
    spans: Sequence[LabeledSpan], bands: Sequence[TextBand], *, min_separation: float
) -> list[tuple[float, float]]:
    """Gera hipóteses `(a, b)` de todo par ordem-consistente (item_i, item_k) x (faixa_j,
    faixa_l), com `i<k`, `j<l`, separação vertical mínima e escala dentro do intervalo
    aceito — arredondadas numa grade para colapsar hipóteses numericamente próximas
    (ver `GLOBAL_AFFINE_SCALE_GRID_STEP`/`GLOBAL_AFFINE_OFFSET_GRID_STEP_PX`).

    Como as faixas são ordenadas por topo, `band_gap` cresce monotonicamente com `l` para
    `j` fixo — a busca interna corta assim que `band_gap` passa do máximo aceito."""
    ordered_spans = sorted(spans, key=lambda span: span.top)
    ordered_bands = sorted(bands, key=lambda band: band.top)
    band_centers = [band.center for band in ordered_bands]
    span_count, band_count = len(ordered_spans), len(ordered_bands)

    seen: dict[tuple[float, float], tuple[float, float]] = {}
    for i in range(span_count):
        span_i_center = ordered_spans[i].center
        for k in range(i + 1, span_count):
            span_gap = ordered_spans[k].center - span_i_center
            if span_gap < min_separation:
                continue
            min_band_gap = GLOBAL_AFFINE_SCALE_MIN * span_gap
            max_band_gap = GLOBAL_AFFINE_SCALE_MAX * span_gap
            for j in range(band_count):
                band_j_center = band_centers[j]
                for right_index in range(j + 1, band_count):
                    band_gap = band_centers[right_index] - band_j_center
                    if band_gap < min_band_gap:
                        continue
                    if band_gap > max_band_gap:
                        break
                    scale = band_gap / span_gap
                    offset = band_j_center - scale * span_i_center
                    key = (
                        round(scale / GLOBAL_AFFINE_SCALE_GRID_STEP)
                        * GLOBAL_AFFINE_SCALE_GRID_STEP,
                        round(offset / GLOBAL_AFFINE_OFFSET_GRID_STEP_PX)
                        * GLOBAL_AFFINE_OFFSET_GRID_STEP_PX,
                    )
                    seen.setdefault(key, key)
    return sorted(seen.values())


def estimate_global_transform(
    spans: Sequence[LabeledSpan], bands: Sequence[TextBand]
) -> GlobalTransformEstimate | None:
    """Estima a transformação afim `y' = a·y + b` mais plausível entre itens e faixas.

    `None` quando não há dado suficiente: sem item, ou com menos de duas faixas (não
    existe passo entre elas para calibrar a trava e a separação mínima).
    Determinístico: as hipóteses vêm de uma grade fixa (ver `_affine_hypotheses`) e o
    desempate de `max()` sempre fica com a primeira hipótese em ordem crescente de
    `(a, b)` entre as empatadas."""
    if not spans or len(bands) < 2:
        return None
    pitch = _median_pitch(bands)
    assert pitch is not None  # len(bands) >= 2 garante um passo
    max_distance = MAX_MATCH_DISTANCE_PITCH_RATIO * pitch

    hypotheses = _affine_hypotheses(
        spans, bands, min_separation=GLOBAL_AFFINE_MIN_SEPARATION_PITCH_RATIO * pitch
    )
    if not hypotheses:
        return None
    scored = [
        (
            scale,
            offset,
            *_dp_match_cost(spans, bands, scale=scale, offset=offset, max_distance=max_distance),
        )
        for scale, offset in hypotheses
    ]

    def score_of(entry: tuple[float, float, int, float]) -> float:
        _scale, _offset, skipped, distance = entry
        return _hypothesis_score(len(spans) - skipped, distance)

    best_scale, best_offset, best_skipped, best_distance = max(scored, key=score_of)
    best_score = _hypothesis_score(len(spans) - best_skipped, best_distance)

    # "Distinta" é medida pela posição que a hipótese prediz para o item mediano — não
    # por `(a, b)` diretamente, porque duas hipóteses com `a` bem diferente podem prever
    # quase o mesmo lugar para os itens realmente em jogo (e vice-versa).
    reference_center = _median([span.center for span in spans])
    assert reference_center is not None  # spans não é vazio (checado acima)
    best_prediction = best_scale * reference_center + best_offset
    minimum_separation = GLOBAL_TRANSFORM_PEAK_SEPARATION_RATIO * pitch
    competing_scores = [
        score_of(entry)
        for entry in scored
        if abs((entry[0] * reference_center + entry[1]) - best_prediction) >= minimum_separation
    ]
    second_best_score = max(competing_scores, default=0.0)
    confidence_margin = best_score - second_best_score
    required_margin = GLOBAL_TRANSFORM_CONFIDENCE_MARGIN_RATIO * len(spans)
    # Com poucos itens, um ajuste de 2 parâmetros livres (a, b) pode achar coincidência
    # espúria que vence toda concorrente por margem confortável SEM explicar todo mundo —
    # visto num teste sintético de ruído heterogêneo (7 itens): a hipótese vencedora batia
    # 6 de 7 com folga sobre a segunda melhor, e ainda assim era só coincidência, não a
    # transformação real (que, para ruído genuinamente não-afim, não existe). Exigir que a
    # vencedora explique TODOS os itens fecha essa brecha: uma transformação de verdade
    # (viés sistemático do provedor) atinge todo item da legenda, não a maioria.
    best_matched = len(spans) - best_skipped
    return GlobalTransformEstimate(
        scale=best_scale,
        offset_px=best_offset,
        score=best_score,
        confidence_margin=confidence_margin,
        applied=confidence_margin >= required_margin and best_matched == len(spans),
    )


def match_spans_to_bands(
    spans: Sequence[LabeledSpan],
    bands: Sequence[TextBand],
    *,
    scale: float = 1.0,
    offset: float = 0.0,
    max_distance: float,
) -> dict[str, TextBand]:
    """Casamento span→faixa ótimo, preservando ordem, por programação dinâmica.

    `dp[i][j]` é o custo lexicográfico — `(spans sem faixa, soma das distâncias)` — de
    casar os `i` primeiros spans (ordenados pelo topo atual) usando faixas entre as `j`
    primeiras (ordenadas pelo topo). Três transições por célula: deixar o span `i-1` sem
    faixa (`+1` no primeiro componente), deixar a faixa `j-1` sem uso (`+0`), ou casar os
    dois (só permitido dentro de `max_distance`, soma a distância no segundo componente).
    Comparar por tupla garante que a solução SEMPRE prefere casar mais spans, mesmo que
    isso não minimize a soma bruta de distâncias — é o que evita o casamento "vazar" em
    bloco para faixas vizinhas quando o deslocamento residual é maior que a trava.

    `scale`/`offset` transformam o CENTRO de cada span antes de medir distância — usado
    para casar já com a transformação global (`estimate_global_transform`) compensada,
    sem alterar `spans`. Os padrões (`scale=1.0, offset=0.0`) reproduzem o casamento sem
    transformação nenhuma."""
    if not spans or not bands:
        return {}
    ordered = sorted(spans, key=lambda span: span.top)

    span_count, band_count = len(ordered), len(bands)
    # custo[i][j] = (spans sem faixa, soma das distâncias) usando spans[:i] e bands[:j].
    cost: list[list[tuple[int, float]]] = [
        [(0, 0.0)] * (band_count + 1) for _ in range(span_count + 1)
    ]
    choice: list[list[str]] = [["" for _ in range(band_count + 1)] for _ in range(span_count + 1)]
    for i in range(1, span_count + 1):
        skipped, distance = cost[i - 1][0]
        cost[i][0] = (skipped + 1, distance)
        choice[i][0] = "skip_span"
    for i in range(1, span_count + 1):
        span_center = scale * ordered[i - 1].center + offset
        for j in range(1, band_count + 1):
            best_cost = cost[i][j - 1]
            best_choice = "skip_band"
            skip_span_cost = (cost[i - 1][j][0] + 1, cost[i - 1][j][1])
            if skip_span_cost < best_cost:
                best_cost, best_choice = skip_span_cost, "skip_span"
            distance = abs(span_center - bands[j - 1].center)
            if distance <= max_distance:
                match_cost = (cost[i - 1][j - 1][0], cost[i - 1][j - 1][1] + distance)
                if match_cost < best_cost:
                    best_cost, best_choice = match_cost, "match"
            cost[i][j] = best_cost
            choice[i][j] = best_choice

    assignment: dict[str, TextBand] = {}
    i, j = span_count, band_count
    while i > 0 and j > 0:
        decision = choice[i][j]
        if decision == "match":
            assignment[ordered[i - 1].id] = bands[j - 1]
            i, j = i - 1, j - 1
        elif decision == "skip_span":
            i -= 1
        else:
            j -= 1
    return assignment


def resolve_item_bands(
    spans: Sequence[LabeledSpan], bands: Sequence[TextBand]
) -> tuple[dict[str, TextBand], GlobalTransformEstimate | None]:
    """O casamento completo: estima a transformação global, aplica-a se confiante, casa.

    Sem transformação confiante (poucas candidatas para estimar, ou ambiguidade — ver
    `estimate_global_transform`), NENHUM item é assentado: a 4ª rodada de homologação
    real mostrou que mesmo uma trava fixa e apertada de distância residual (1,2x o passo
    mediano) ainda cabe dentro do aglomerado denso de linhas vizinhas — 1,2x o passo é
    MAIOR que o próprio passo entre linhas adjacentes, então sempre existe alguma
    candidata "perto o bastante" pra alguém morder o anzol errado. O fallback residual foi
    retirado por completo: sem transformação, o pacote volta do jeito que veio, e todo
    item aparece em `unmatched_item_ids`. Com transformação confiante, a trava do
    casamento final é `MAX_MATCH_DISTANCE_PITCH_RATIO` do passo: depois de compensar o
    viés sistemático, um item que ainda precisa de mais que isso para achar uma candidata
    é sinal de candidata errada, não de ruído fino."""
    if not spans or not bands:
        return {}, None
    estimate = estimate_global_transform(spans, bands)
    if estimate is not None and estimate.applied:
        pitch = _median_pitch(bands)
        assert pitch is not None
        assignment = match_spans_to_bands(
            spans,
            bands,
            scale=estimate.scale,
            offset=estimate.offset_px,
            max_distance=MAX_MATCH_DISTANCE_PITCH_RATIO * pitch,
        )
        return assignment, estimate
    return {}, estimate


def _bijection(spans: Sequence[LabeledSpan], cells: Sequence[TextBand]) -> dict[str, TextBand]:
    """Casamento 1-para-1 direto, por ordem: o item mais alto vai pra célula mais alta, e
    assim por diante. Só faz sentido — e só é chamado — quando `len(cells) == len(spans)`:
    aí a ordem JÁ é a resposta, sem precisar estimar transformação nenhuma."""
    ordered_spans = sorted(spans, key=lambda span: span.top)
    ordered_cells = sorted(cells, key=lambda cell: cell.top)
    return dict(zip((span.id for span in ordered_spans), ordered_cells, strict=True))


def _trimmed_bijection(
    spans: Sequence[LabeledSpan], cells: Sequence[TextBand]
) -> dict[str, TextBand] | None:
    """Quando há exatamente uma célula a mais que itens, tenta descartar a primeira ou a
    última e aceita a bijeção resultante só se o desvio de posição entre item e célula for
    consistente entre todos os itens — ver `RULING_TRIMMED_BIJECTION_MAX_STD_PITCH_RATIO`.
    `None` quando nenhuma das duas é confiável o bastante."""
    if len(cells) != len(spans) + 1 or not spans:
        return None
    pitch = _median_pitch(cells)
    if pitch is None:
        return None
    ordered_spans = sorted(spans, key=lambda span: span.top)
    ordered_cells = sorted(cells, key=lambda cell: cell.top)
    best: tuple[float, dict[str, TextBand]] | None = None
    for trimmed in (ordered_cells[1:], ordered_cells[:-1]):
        offsets = [
            cell.center - span.center for span, cell in zip(ordered_spans, trimmed, strict=True)
        ]
        mean_offset = sum(offsets) / len(offsets)
        variance = sum((value - mean_offset) ** 2 for value in offsets) / len(offsets)
        deviation = variance**0.5
        if best is None or deviation < best[0]:
            best = (deviation, dict(zip((span.id for span in ordered_spans), trimmed, strict=True)))
    assert best is not None
    deviation, assignment = best
    if deviation > RULING_TRIMMED_BIJECTION_MAX_STD_PITCH_RATIO * pitch:
        return None
    return assignment


def resolve_ruling_cells(
    spans: Sequence[LabeledSpan], cells: Sequence[TextBand]
) -> tuple[dict[str, TextBand], GlobalTransformEstimate | None, bool]:
    """Casamento por células de régua de tabela: bijeção direta quando `len(cells) ==
    len(spans)` (a ordem já é a resposta — devolve `(assignment, None, True)`); quando há
    exatamente uma célula a mais (tipicamente o cabeçalho de COLUNA da própria tabela,
    sempre a primeira célula por convenção — ver `RULING_TRIMMED_BIJECTION_MAX_STD_PITCH_RATIO`
    para a verificação de consistência antes de aceitar), tenta a bijeção aparada; senão,
    cai na mesma estimativa de transformação usada para faixas de texto
    (`resolve_item_bands`), devolvendo `(assignment, estimate, estimate.applied)`."""
    if not spans or not cells:
        return {}, None, False
    if len(cells) == len(spans):
        return _bijection(spans, cells), None, True
    trimmed = _trimmed_bijection(spans, cells)
    if trimmed is not None:
        return trimmed, None, True
    assignment, estimate = resolve_item_bands(spans, cells)
    applied = estimate is not None and estimate.applied
    return assignment, estimate, applied


def _with_bbox(item: TakeoffItem, box: PlateBox) -> TakeoffItem:
    payload = item.model_dump()
    payload["evidence"] = {**payload["evidence"], "bbox": box.model_dump()}
    return TakeoffItem.model_validate(payload)


def _with_items(packet: TakeoffPacket, items: list[TakeoffItem]) -> TakeoffPacket:
    payload = packet.model_dump()
    payload["items"] = [item.model_dump() for item in items]
    return TakeoffPacket.model_validate(payload)


def register_legend_bboxes(
    image_path: Path, packet: TakeoffPacket
) -> tuple[TakeoffPacket, LegendRegistrationReport]:
    """Reassenta `evidence.bbox` de cada item contra a tinta da prancha, fail-closed.

    Recusa antes de olhar um pixel sequer: pacote com QUALQUER item já decidido pelo
    orçamentista (`REGISTRATION_AFTER_DECISION` — mover a âncora depois de uma decisão
    reescreveria o que o revisor viu) e digest da imagem divergente do pacote
    (`LEGEND_REGISTRATION_DIGEST_MISMATCH` — âncora sobre imagem errada mente). Nenhum
    dos dois escreve nada; a função é pura.

    Sem faixa candidata alguma (caso degenerado — prancha em branco, coluna sem tinta) o
    pacote volta inalterado e todo item aparece em `unmatched_item_ids`."""
    decided = [item.id for item in packet.items if item.decision is not None]
    if decided:
        raise ValuationValidationError(
            "REGISTRATION_AFTER_DECISION",
            "pacote com item já decidido pelo orçamentista não pode ter a âncora de "
            "evidência movida",
            {"plate_id": packet.plate_id, "decided_item_ids": sorted(decided)},
        )
    resolved_image_path = image_path.resolve(strict=True)
    if file_sha256(resolved_image_path) != packet.image_sha256:
        raise ValuationValidationError(
            LEGEND_REGISTRATION_DIGEST_MISMATCH,
            "digest da imagem não corresponde ao pacote de takeoff; âncora sobre imagem "
            "errada mente",
            {"image": resolved_image_path.name, "expected": packet.image_sha256},
        )

    image = cv2.imread(str(resolved_image_path), cv2.IMREAD_COLOR)
    if image is None:
        raise ValuationValidationError(
            "LEGEND_REGISTRATION_IMAGE_UNREADABLE",
            "imagem da prancha ilegível para o registro fino da legenda",
            {"image": resolved_image_path.name},
        )
    height, width = image.shape[0], image.shape[1]

    left = max(0, min(width - 1, min(item.evidence.bbox.left for item in packet.items)))
    right = max(left + 1, min(width, max(item.evidence.bbox.right for item in packet.items)))
    item_count = len(packet.items)
    spans = [
        LabeledSpan(id=item.id, top=item.evidence.bbox.top, bottom=item.evidence.bbox.bottom)
        for item in packet.items
    ]

    # Janela de busca vertical: acima e abaixo da união dos bboxes PROPOSTOS, não a
    # imagem inteira — sem isso, uma tabela completamente alheia mais adiante na mesma
    # coluna X (visto na prancha real) pode ser confundida com a legenda de interesse.
    proposed_top = min(item.evidence.bbox.top for item in packet.items)
    proposed_bottom = max(item.evidence.bbox.bottom for item in packet.items)
    search_margin = max(
        round(RULING_SEARCH_MARGIN_RATIO * (proposed_bottom - proposed_top)),
        RULING_SEARCH_MIN_MARGIN_PX,
    )
    search_top = max(0, proposed_top - search_margin)
    search_bottom = min(height, proposed_bottom + search_margin)
    search_image = image[search_top:search_bottom, :]

    def _offset(bands: list[TextBand]) -> list[TextBand]:
        return [
            TextBand(top=band.top + search_top, bottom=band.bottom + search_top) for band in bands
        ]

    rulings = [y + search_top for y in detect_rulings(search_image, left=left, right=right)]
    raw_ruling_cells = _cells_from_rulings(rulings, image, left=left, right=right)
    ruling_cells = (
        _filter_cells_by_internal_divider(image, raw_ruling_cells, left=left, right=right)
        if raw_ruling_cells
        else []
    )

    raw_text_bands = _offset(detect_text_bands(search_image, left=left, right=right))
    text_bands = _filter_item_row_bands(
        image, raw_text_bands, left=left, right=right, item_count=item_count
    )

    method: RegistrationMethod
    if ruling_cells:
        assignment, transform_estimate, ruling_applied = resolve_ruling_cells(spans, ruling_cells)
        if ruling_applied:
            method = "rulings"
            bands = ruling_cells
        else:
            assignment, transform_estimate = resolve_item_bands(spans, text_bands)
            text_applied = transform_estimate is not None and transform_estimate.applied
            method = "text_bands" if text_applied else "none"
            bands = text_bands
    else:
        assignment, transform_estimate = resolve_item_bands(spans, text_bands)
        text_applied = transform_estimate is not None and transform_estimate.applied
        method = "text_bands" if text_applied else "none"
        bands = text_bands

    adjusted: list[dict[str, object]] = []
    unmatched: list[str] = []
    updated_items: list[TakeoffItem] = []
    changed = False
    for item in packet.items:
        band = assignment.get(item.id)
        if band is None:
            unmatched.append(item.id)
            updated_items.append(item)
            continue
        before = item.evidence.bbox
        after = PlateBox(
            left=before.left,
            top=max(0, band.top - BAND_VERTICAL_MARGIN_PX),
            right=before.right,
            bottom=min(height, band.bottom + BAND_VERTICAL_MARGIN_PX),
        )
        if after == before:
            updated_items.append(item)
            continue
        changed = True
        adjusted.append(
            {
                "item_id": item.id,
                "before": before.model_dump(),
                "after": after.model_dump(),
                "shift_px": after.top - before.top,
            }
        )
        updated_items.append(_with_bbox(item, after))

    applied = (
        transform_estimate
        if transform_estimate is not None and transform_estimate.applied
        else None
    )
    report = LegendRegistrationReport(
        adjusted=adjusted,
        unmatched_item_ids=unmatched,
        band_count=len(bands),
        method=method,
        global_scale=None if applied is None else applied.scale,
        global_shift_px=None if applied is None else round(applied.offset_px),
        shift_score=None if transform_estimate is None else transform_estimate.score,
        shift_confidence=None
        if transform_estimate is None
        else transform_estimate.confidence_margin,
    )
    registered_packet = _with_items(packet, updated_items) if changed else packet
    return registered_packet, report


def restore_raw_bboxes(
    packet: TakeoffPacket, adjusted: Sequence[Mapping[str, object]]
) -> TakeoffPacket:
    """Reverte `evidence.bbox` dos itens ajustados por uma rodada de registro anterior
    para o `before` gravado no relatório (`LegendRegistrationReport.adjusted`, o mesmo
    formato que `register-takeoff` publica em `takeoff-registration.json`).

    Existe para reprocessar do BRUTO sem nova chamada paga: um pipeline mais novo (com um
    filtro ou modelo melhor) corrige o assentamento de uma rodada anterior só se partir da
    posição que a extração leu de verdade, não da posição que a rodada anterior (talvez
    com um defeito ainda não corrigido) já tinha movido — ver `--restore-raw` de
    `register-takeoff`. Fail-closed, mesma regra e mesmo código de `register_legend_bboxes`:
    pacote com QUALQUER item já decidido é recusado, porque mover a âncora depois de uma
    decisão reescreveria o que o orçamentista viu. Item de `adjusted` cujo id não existe
    mais no pacote é ignorado silenciosamente — o pacote pode ter evoluído entre rodadas."""
    decided = [item.id for item in packet.items if item.decision is not None]
    if decided:
        raise ValuationValidationError(
            "REGISTRATION_AFTER_DECISION",
            "pacote com item já decidido pelo orçamentista não pode ter a âncora de "
            "evidência restaurada",
            {"plate_id": packet.plate_id, "decided_item_ids": sorted(decided)},
        )
    before_by_id = {
        str(entry["item_id"]): PlateBox.model_validate(entry["before"]) for entry in adjusted
    }
    if not before_by_id:
        return packet
    updated_items = [
        _with_bbox(item, before_by_id[item.id]) if item.id in before_by_id else item
        for item in packet.items
    ]
    return _with_items(packet, updated_items)
