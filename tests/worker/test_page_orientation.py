"""O voto de orientação e as duas transformações que ele comanda.

Cobre o módulo determinístico isolado: a decisão (`predominant_rotation`), o giro dos
bytes (`rotate_image_upright`) e o giro das coordenadas (`rotate_normalized_box`). A
integração com o snapshot de revisão fica em `test_providers.py`, junto das fixtures de
suite que ela precisa.
"""

from __future__ import annotations

import io

import pytest
from PIL import Image

from croquito_worker.page_orientation import (
    ORIENTATION_MIN_SHARE,
    ORIENTATION_MIN_VOTING_CHARS,
    predominant_rotation,
    rotate_image_upright,
    rotate_normalized_box,
)
from croquito_worker.providers import NormalizedBox, OcrLineOutput


def _line(rotation: int | None, chars: int) -> OcrLineOutput:
    """Linha de OCR cujo peso no voto é exatamente `chars`."""
    return OcrLineOutput(
        raw_text="x" * chars,
        bbox=NormalizedBox(left=0.1, top=0.1, right=0.2, bottom=0.15),
        rotation_ccw_degrees=rotation,
    )


def _png(image: Image.Image) -> bytes:
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def test_predominant_rotation_decides_a_clear_majority() -> None:
    vote = predominant_rotation([_line(90, 15), _line(90, 10), _line(0, 5)])

    assert vote.rotation_ccw_degrees == 90
    assert vote.voting_chars == 30
    assert vote.share == pytest.approx(25 / 30)
    assert vote.decided is True


def test_predominant_rotation_refuses_a_plurality_below_the_share_floor() -> None:
    """Vencedora sem maioria é nomeada, não obedecida: 12 contra 11 e 11 não é veredito."""
    vote = predominant_rotation([_line(90, 12), _line(0, 11), _line(180, 11)])

    assert vote.rotation_ccw_degrees == 90
    assert vote.share < ORIENTATION_MIN_SHARE
    assert vote.decided is False


def test_predominant_rotation_refuses_a_page_with_too_little_text() -> None:
    """Share perfeito não compensa evidência de meia dúzia de caracteres."""
    vote = predominant_rotation([_line(90, ORIENTATION_MIN_VOTING_CHARS - 1)])

    assert vote.rotation_ccw_degrees == 90
    assert vote.share == pytest.approx(1.0)
    assert vote.voting_chars == ORIENTATION_MIN_VOTING_CHARS - 1
    assert vote.decided is False


def test_predominant_rotation_refuses_an_exact_tie() -> None:
    """Metade contra metade dá share 0,5 — que passa no piso e mesmo assim não decide."""
    vote = predominant_rotation([_line(90, 15), _line(180, 15)])

    assert vote.share == pytest.approx(ORIENTATION_MIN_SHARE)
    assert vote.voting_chars == 30
    assert vote.decided is False
    # Sem veredito, a rotação devolvida é a ausência de rotação, não a vencedora sorteada.
    assert vote.rotation_ccw_degrees == 0


def test_predominant_rotation_ignores_lines_without_an_observed_rotation() -> None:
    """Braço que não reporta vértice (Textract, Document AI) não vota nem arrasta o voto."""
    vote = predominant_rotation([_line(None, 40), _line(None, 40)])

    assert vote.rotation_ccw_degrees == 0
    assert vote.voting_chars == 0
    assert vote.share == pytest.approx(0.0)
    assert vote.decided is False


def test_predominant_rotation_of_an_empty_page_decides_nothing() -> None:
    vote = predominant_rotation([])

    assert vote.decided is False
    assert vote.voting_chars == 0


def test_rotate_normalized_box_moves_the_corners_by_hand() -> None:
    """Um quarto de volta anti-horária leva a borda direita da folha para o topo."""
    box = NormalizedBox(left=0.1, top=0.2, right=0.4, bottom=0.5)

    rotated = rotate_normalized_box(box, 90)

    assert rotated.left == pytest.approx(0.2)
    assert rotated.top == pytest.approx(0.6)
    assert rotated.right == pytest.approx(0.5)
    assert rotated.bottom == pytest.approx(0.9)


def test_rotate_normalized_box_composes_180_and_270() -> None:
    box = NormalizedBox(left=0.1, top=0.2, right=0.4, bottom=0.5)

    half = rotate_normalized_box(box, 180)
    three_quarters = rotate_normalized_box(box, 270)

    # 180° é o espelho nos dois eixos, calculado aqui à mão contra a composição.
    assert (half.left, half.top, half.right, half.bottom) == pytest.approx((0.6, 0.5, 0.9, 0.8))
    assert (
        three_quarters.left,
        three_quarters.top,
        three_quarters.right,
        three_quarters.bottom,
    ) == pytest.approx((0.5, 0.1, 0.8, 0.4))


def test_rotate_normalized_box_is_identity_at_zero() -> None:
    box = NormalizedBox(left=0.1, top=0.2, right=0.4, bottom=0.5)

    assert rotate_normalized_box(box, 0) == box


def test_four_quarter_turns_return_the_box_to_where_it_started() -> None:
    """A propriedade que impede um sinal trocado de passar despercebido."""
    box = NormalizedBox(left=0.07, top=0.31, right=0.62, bottom=0.83)

    rotated = box
    for _turn in range(4):
        rotated = rotate_normalized_box(rotated, 90)

    assert (rotated.left, rotated.top, rotated.right, rotated.bottom) == pytest.approx(
        (box.left, box.top, box.right, box.bottom)
    )


def test_rotate_image_upright_swaps_the_dimensions_on_a_quarter_turn() -> None:
    image_bytes = _png(Image.new("RGB", (1400, 1050), "white"))

    for rotation, expected in ((90, (1050, 1400)), (270, (1050, 1400)), (180, (1400, 1050))):
        _payload, width, height = rotate_image_upright(image_bytes, rotation)
        assert (width, height) == expected


def test_rotate_image_upright_at_zero_returns_the_very_same_bytes() -> None:
    """Reencodar mudaria o sha256 da evidência sem mudar um pixel."""
    image_bytes = _png(Image.new("RGB", (12, 8), "white"))

    payload, width, height = rotate_image_upright(image_bytes, 0)

    assert payload is image_bytes
    assert (width, height) == (12, 8)


def test_rotate_image_upright_turns_counterclockwise() -> None:
    """O canto superior-DIREITO vira o superior-esquerdo: é isso que anti-horário quer dizer."""
    source = Image.new("RGB", (4, 2), "white")
    source.putpixel((3, 0), (255, 0, 0))

    payload, width, height = rotate_image_upright(_png(source), 90)

    with Image.open(io.BytesIO(payload)) as rotated:
        assert (width, height) == (2, 4) == rotated.size
        assert rotated.getpixel((0, 0)) == (255, 0, 0)


def test_rotate_image_upright_refuses_an_angle_outside_the_quarter_turn() -> None:
    with pytest.raises(ValueError, match="quarto de volta"):
        rotate_image_upright(_png(Image.new("RGB", (4, 4), "white")), 45)
