"""Decide a orientação da folha pelos vértices do OCR e gira a página em pé.

O croqui de campo chega deitado com frequência: o técnico vira a prancheta para desenhar
o lado comprido da praça e o PDF sai com a folha em paisagem, ou girada 90°, sem declarar
rotação nenhuma. Todo consumidor a jusante — survey, extração, geometria, corroboração de
tinta e a própria revisão humana — lê a MESMA imagem (`source_image_bytes` do snapshot),
então girar uma vez, no começo, deixa a cadeia inteira consistente sem transformar
coordenada em consumidor nenhum.

**A orientação vem do OCR, não do modelo.** O campo `orientation` do `page-survey` foi
sondado contra o corpus real de campo (7 páginas, 2026-09-03) e respondeu `up` para uma
folha girada 90° — ele não vê a folha deitada. O voto por vértice de palavra do OCR
acertou 7/7 no mesmo corpus, com share entre 52% e 100%. É esse voto que este módulo
implementa.
"""

from __future__ import annotations

import io
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Final

from PIL import Image

from croquito_worker.providers import NormalizedBox, OcrLineOutput

ORIENTATION_MIN_SHARE: Final = 0.5
"""Fração mínima do peso votante que a rotação vencedora precisa reunir para decidir.

Medido no corpus real: o PIOR caso das sete páginas decidiu com 0,52 — folha com muita
legenda impressa em pé ao lado do desenho manuscrito girado. Um piso mais alto teria
recusado justamente a página que mais precisava do giro; um piso mais baixo aceitaria
uma minoria como veredito. Empate exato NÃO decide, mesmo somando 0,5 de cada lado:
duas metades que se contradizem não são maioria.
"""

ORIENTATION_MIN_VOTING_CHARS: Final = 20
"""Caracteres mínimos somados entre as linhas com rotação legível.

Página quase vazia (um carimbo, um número solto) não sustenta veredito de orientação: o
voto de meia dúzia de caracteres é ruído, e girar a folha errada custa a extração inteira.
Abaixo do piso a saída é não girar — o comportamento que valia antes deste módulo.
"""


@dataclass(frozen=True)
class PageOrientationVote:
    """O veredito de orientação de uma página, com a evidência que o sustenta.

    `decided=False` significa "não gire": voto ausente, minoritário, empatado ou apoiado
    em texto de menos. `rotation_ccw_degrees` é 0 nesses casos — não é uma rotação
    escolhida, é a ausência de rotação.
    """

    rotation_ccw_degrees: int
    share: float
    voting_chars: int
    decided: bool


def predominant_rotation(lines: Sequence[OcrLineOutput]) -> PageOrientationVote:
    """Maioria ponderada pelo tamanho do texto entre as linhas que declararam rotação.

    O peso é `len(raw_text)`, e não uma linha um voto: numa prancha, uma legenda impressa
    de trinta caracteres diz mais sobre a orientação da folha do que três cotas de quatro.
    Linha sem rotação (`None`) não vota nem entra no denominador — braço de OCR que não
    reporta vértice (Textract, Document AI) simplesmente não opina, em vez de arrastar o
    voto para zero.
    """
    weights: dict[int, int] = {}
    for line in lines:
        rotation = line.rotation_ccw_degrees
        if rotation is None:
            continue
        weights[rotation] = weights.get(rotation, 0) + len(line.raw_text)
    total = sum(weights.values())
    if total == 0:
        return PageOrientationVote(rotation_ccw_degrees=0, share=0.0, voting_chars=0, decided=False)
    top = max(weights.values())
    winners = [rotation for rotation, weight in weights.items() if weight == top]
    share = top / total
    if len(winners) > 1:
        # Empate exato entre duas orientações: a folha não tem veredito, e escolher a de
        # menor grau seria desempatar por acaso da ordenação.
        return PageOrientationVote(
            rotation_ccw_degrees=0, share=share, voting_chars=total, decided=False
        )
    return PageOrientationVote(
        rotation_ccw_degrees=winners[0],
        share=share,
        voting_chars=total,
        decided=share >= ORIENTATION_MIN_SHARE and total >= ORIENTATION_MIN_VOTING_CHARS,
    )


_TRANSPOSITIONS: Final[dict[int, Image.Transpose]] = {
    # `ROTATE_90` do PIL é anti-horário, a mesma convenção do voto: k=1 significa "gire a
    # imagem um quarto de volta no sentido anti-horário e o texto fica em pé".
    90: Image.Transpose.ROTATE_90,
    180: Image.Transpose.ROTATE_180,
    270: Image.Transpose.ROTATE_270,
}


def rotate_image_upright(image_bytes: bytes, rotation_ccw_degrees: int) -> tuple[bytes, int, int]:
    """Gira a página e devolve `(png, largura, altura)` da imagem girada.

    Rotação 0 devolve os bytes ORIGINAIS, sem reencodar: reencodar mudaria o sha256 da
    evidência sem mudar um pixel, e o digest é o que amarra pacote, associações e propostas
    à mesma folha.
    """
    if rotation_ccw_degrees == 0:
        with Image.open(io.BytesIO(image_bytes)) as image:
            return image_bytes, image.width, image.height
    transposition = _TRANSPOSITIONS.get(rotation_ccw_degrees)
    if transposition is None:
        raise ValueError(f"rotação fora do quarto de volta: {rotation_ccw_degrees}")
    with Image.open(io.BytesIO(image_bytes)) as image:
        rotated = image.transpose(transposition)
    buffer = io.BytesIO()
    rotated.save(buffer, format="PNG")
    return buffer.getvalue(), rotated.width, rotated.height


def _rotate_point(x: float, y: float, rotation_ccw_degrees: int) -> tuple[float, float]:
    """Um ponto normalizado sob rotação anti-horária da IMAGEM que o contém.

    Um quarto de volta anti-horária leva a borda direita da folha para o topo, então
    `(x, y) -> (y, 1 - x)`. 180° e 270° saem por composição — derivar cada caso à mão
    daria três oportunidades de trocar um sinal.
    """
    for _quarter in range((rotation_ccw_degrees // 90) % 4):
        x, y = y, 1.0 - x
    return x, y


def _clamped(value: float) -> float:
    return min(1.0, max(0.0, value))


def rotate_normalized_box(box: NormalizedBox, rotation_ccw_degrees: int) -> NormalizedBox:
    """Leva uma bbox normalizada para o espaço da imagem girada.

    Os quatro cantos são transformados e a caixa é recomposta por mínimo/máximo: sob 90° o
    canto superior-esquerdo vira o inferior-esquerdo, e reaproveitar os nomes `left`/`top`
    produziria uma caixa de área negativa que o próprio contrato recusaria.

    A área é preservada a menos do arredondamento de `1 - x`; caixa derivada de pixel de
    página real (largura mínima da ordem de 1e-4) atravessa sem colapsar, e caixa que
    colapsasse seria recusada pelo validador de `NormalizedBox` em vez de virar área
    inventada.
    """
    corners = [
        _rotate_point(x, y, rotation_ccw_degrees)
        for x, y in (
            (box.left, box.top),
            (box.right, box.top),
            (box.right, box.bottom),
            (box.left, box.bottom),
        )
    ]
    xs = [corner[0] for corner in corners]
    ys = [corner[1] for corner in corners]
    return NormalizedBox(
        left=_clamped(min(xs)),
        top=_clamped(min(ys)),
        right=_clamped(max(xs)),
        bottom=_clamped(max(ys)),
    )
