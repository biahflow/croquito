"""Registro fino dos bboxes da legenda contra a tinta — espelho do `register-extraction`.

O oráculo é o gabarito da prancha sintética (`PlateArtifacts.rows`, via
`extract_takeoff_fixture`): itens propostos com o bbox deslocado precisam recuperar a
linha verdadeira depois de `register_legend_bboxes`, e um item jogado longe de qualquer
faixa de texto tem de ficar intocado em vez de casar às cegas. Como o bbox registrado é
recortado bem justo à tinta (bem menor que o retângulo de linha inteira do gabarito), a
comparação usa CONTENÇÃO — quanto do bbox recuperado cai dentro do bbox do gabarito — e
não interseção-sobre-união clássica, que penalizaria a precisão do recorte.

Duas famílias de teste espelham os dois defeitos reais vistos na Toca: desvio vertical
praticamente constante (1ª rodada — `_row_grid_centers`/`_span_at`, casamento por Δ puro,
`scale=1.0`) e erro de ESCALA na normalização Y do provedor (2ª rodada — seção "Modelo
afim", `scale != 1.0`). Nenhum teste aqui lê artefato de rodada real (`output/`); a
calibração contra o pacote real da Toca é verificação local, fora do repositório.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import cv2
import pytest
from PIL import Image, ImageDraw

from croquitodxf_valuation.catalog import file_sha256
from croquitodxf_valuation.errors import ValuationValidationError
from croquitodxf_valuation.takeoff import (
    PlateBox,
    PlateEvidence,
    TakeoffDecisionBatch,
    TakeoffDecisionInput,
    TakeoffItem,
    TakeoffItemStatus,
    TakeoffPacket,
    apply_takeoff_decisions,
    load_takeoff_packet,
)
from croquitodxf_worker.valuation.cli import (
    TAKEOFF_OVERLAY_FILENAME,
    TAKEOFF_PACKET_FILENAME,
    TAKEOFF_REGISTRATION_REPORT_FILENAME,
    main,
)
from croquitodxf_worker.valuation.legend_registration import (
    LabeledSpan,
    TextBand,
    detect_text_bands,
    estimate_global_transform,
    match_spans_to_bands,
    register_legend_bboxes,
    resolve_item_bands,
    restore_raw_bboxes,
)
from croquitodxf_worker.valuation.plate import PlateArtifacts, render_synthetic_plate
from croquitodxf_worker.valuation.takeoff_fixture import extract_takeoff_fixture, takeoff_item_id

CONTAINMENT_THRESHOLD = 0.6
"""Tolerância do teste (a mesma citada no spec): fração do bbox RECUPERADO que precisa
cair dentro do bbox do gabarito para contar como "casou com a linha certa"."""

_DECIDED_AT = datetime(2026, 2, 1, 12, 0, tzinfo=UTC)


# --------------------------------------------------------------------------------------
# Fixtures e helpers
# --------------------------------------------------------------------------------------


@pytest.fixture(scope="module")
def plate(tmp_path_factory: pytest.TempPathFactory) -> PlateArtifacts:
    """Gerar a prancha é caro; a imagem não muda entre os testes deste módulo."""
    return render_synthetic_plate(tmp_path_factory.mktemp("legend-registration-plate"))


@pytest.fixture()
def truth(plate: PlateArtifacts) -> TakeoffPacket:
    """Pacote com os bboxes VERDADEIROS do gabarito — o que o registro deveria recuperar."""
    return extract_takeoff_fixture(plate)


def _shift(item: TakeoffItem, delta: int) -> TakeoffItem:
    """Um item com o bbox deslocado verticalmente em `delta` pixels; resto intocado."""
    payload = item.model_dump()
    box = payload["evidence"]["bbox"]
    payload["evidence"] = {
        **payload["evidence"],
        "bbox": {**box, "top": box["top"] + delta, "bottom": box["bottom"] + delta},
    }
    return TakeoffItem.model_validate(payload)


def _repackage(template: TakeoffPacket, items: list[TakeoffItem]) -> TakeoffPacket:
    """Novo pacote com os MESMOS metadados de `template`, só a lista de itens trocada."""
    payload = template.model_dump()
    payload["items"] = [item.model_dump() for item in items]
    return TakeoffPacket.model_validate(payload)


def _containment(candidate: PlateBox, expected: PlateBox) -> float:
    """Fração de `candidate` que cai dentro de `expected`, em Y."""
    top = max(candidate.top, expected.top)
    bottom = min(candidate.bottom, expected.bottom)
    intersection = max(0, bottom - top)
    return intersection / (candidate.bottom - candidate.top)


def _assert_recovers_the_gabarito(registered: TakeoffPacket, truth: TakeoffPacket) -> None:
    expected_by_id = {item.id: item.evidence.bbox for item in truth.items}
    for item in registered.items:
        containment = _containment(item.evidence.bbox, expected_by_id[item.id])
        assert containment > CONTAINMENT_THRESHOLD, (item.id, containment)


# --------------------------------------------------------------------------------------
# register_legend_bboxes — casamento
# --------------------------------------------------------------------------------------


def test_a_uniform_downward_shift_is_recovered_for_every_item(
    plate: PlateArtifacts, truth: TakeoffPacket
) -> None:
    """O defeito real da 1ª rodada da Toca: todo bbox deslocado por um viés constante."""
    shifted = _repackage(truth, [_shift(item, 140) for item in truth.items])

    registered, report = register_legend_bboxes(plate.image_path, shifted)

    assert report.unmatched_item_ids == []
    assert len(report.adjusted) == len(truth.items)
    assert report.band_count > len(truth.items)  # sobra pelo menos o cabeçalho da tabela
    _assert_recovers_the_gabarito(registered, truth)


def test_a_heterogeneous_downward_shift_is_recovered_for_every_item(
    plate: PlateArtifacts, truth: TakeoffPacket
) -> None:
    """Deslocamento heterogêneo (90 a 180 px) sem relação afim nenhuma com a posição —
    ruído puro, não o defeito real de nenhuma das duas rodadas. Com só 7 itens e sem
    estrutura para explicar, a transformação afim NÃO seria aplicada (ver
    `test_estimate_global_transform_is_not_applied_when_the_winner_does_not_match_every_item`)
    — mas a prancha sintética é uma tabela com bordas, e a bijeção aparada por réguas
    (8 células — cabeçalho de coluna + 7 itens — para 7 itens, `method="rulings"`)
    recupera todo item sem precisar de transformação nenhuma."""
    shifts = [90, 150, 110, 170, 120, 180, 140]
    shifted = _repackage(
        truth, [_shift(item, delta) for item, delta in zip(truth.items, shifts, strict=True)]
    )

    registered, report = register_legend_bboxes(plate.image_path, shifted)

    assert report.method == "rulings"
    assert report.unmatched_item_ids == []
    assert len(report.adjusted) == len(truth.items)
    _assert_recovers_the_gabarito(registered, truth)


def test_an_item_thrown_into_an_empty_area_leaves_the_whole_batch_untouched(
    plate: PlateArtifacts, truth: TakeoffPacket
) -> None:
    """Sem faixa de texto por perto do item deslocado, NENHUMA transformação explica
    TODOS os itens (exigência de casar todo mundo — ver `estimate_global_transform`), e
    a bijeção de réguas (8 células para 7 itens) também recusa: o item fora do lugar
    puxa o desvio de posição bem longe do resto, estourando o teto de consistência da
    bijeção aparada. Antes da 4ª rodada, o fallback residual ainda recuperava os OUTROS
    6 itens "de qualquer jeito"; com o fallback retirado, o pacote inteiro fica intocado
    — inclusive os itens que, sozinhos, estariam certos. É o preço da regra "nunca
    desliza": sem confiança sobre o lote inteiro, ninguém é assentado."""
    target = truth.items[3]
    stray_box = PlateBox(
        left=target.evidence.bbox.left, top=1100, right=target.evidence.bbox.right, bottom=1140
    )
    items = [
        TakeoffItem.model_validate(
            {
                **item.model_dump(),
                "evidence": {**item.model_dump()["evidence"], "bbox": stray_box.model_dump()},
            }
        )
        if item.id == target.id
        else item
        for item in truth.items
    ]
    packet = _repackage(truth, items)

    registered, report = register_legend_bboxes(plate.image_path, packet)

    assert report.method == "none"
    assert report.adjusted == []
    assert sorted(report.unmatched_item_ids) == sorted(item.id for item in truth.items)
    assert registered is packet


def test_no_band_detected_returns_the_original_packet_and_marks_every_item_unmatched(
    tmp_path: Path, plate: PlateArtifacts, truth: TakeoffPacket
) -> None:
    """Caso degenerado (prancha em branco): nada para casar, nada é tocado."""
    blank_path = tmp_path / "blank.png"
    Image.new("RGB", (plate.image_width, plate.image_height), "white").save(blank_path)
    payload = truth.model_dump()
    blank_digest = file_sha256(blank_path)
    payload["image_sha256"] = blank_digest
    for item in payload["items"]:
        item["evidence"]["image_sha256"] = blank_digest
    packet = TakeoffPacket.model_validate(payload)

    registered, report = register_legend_bboxes(blank_path, packet)

    assert report.band_count == 0
    assert report.adjusted == []
    assert sorted(report.unmatched_item_ids) == sorted(item.id for item in packet.items)
    assert registered is packet


def test_content_fields_are_byte_identical_only_the_bbox_moves(
    plate: PlateArtifacts, truth: TakeoffPacket
) -> None:
    shifted = _repackage(truth, [_shift(item, 140) for item in truth.items])

    registered, _ = register_legend_bboxes(plate.image_path, shifted)

    for before, after in zip(shifted.items, registered.items, strict=True):
        assert after.id == before.id
        assert after.raw_text == before.raw_text
        assert after.label == before.label
        assert after.quantity == before.quantity
        assert after.unit == before.unit
        assert after.source == before.source
        assert after.extractor == before.extractor
        assert after.extractor_version == before.extractor_version
        assert after.note == before.note
        assert after.status == before.status
        assert after.decision == before.decision
        assert after.evidence.plate_id == before.evidence.plate_id
        assert after.evidence.page_number == before.evidence.page_number
        assert after.evidence.image_sha256 == before.evidence.image_sha256
        assert after.evidence.bbox.left == before.evidence.bbox.left
        assert after.evidence.bbox.right == before.evidence.bbox.right
        assert after.evidence.bbox != before.evidence.bbox


def test_registration_is_fully_deterministic(plate: PlateArtifacts, truth: TakeoffPacket) -> None:
    shifted = _repackage(truth, [_shift(item, 140) for item in truth.items])

    first_packet, first_report = register_legend_bboxes(plate.image_path, shifted)
    second_packet, second_report = register_legend_bboxes(plate.image_path, shifted)

    assert first_packet.model_dump_json() == second_packet.model_dump_json()
    assert first_report == second_report


# --------------------------------------------------------------------------------------
# register_legend_bboxes — recusas fail-closed
# --------------------------------------------------------------------------------------


def test_a_packet_with_any_decided_item_is_refused(
    plate: PlateArtifacts, truth: TakeoffPacket
) -> None:
    """Mover a âncora depois de uma decisão do orçamentista reescreveria o que ele viu."""
    proposed = next(item for item in truth.items if item.quantity is not None)
    batch = TakeoffDecisionBatch(
        decisions=[
            TakeoffDecisionInput(
                item_id=proposed.id,
                action="confirm",
                reviewer_id="orcamentista-de-teste",
                reviewer_role="orcamentista",
                decided_at=_DECIDED_AT,
            )
        ]
    )
    reviewed = apply_takeoff_decisions(truth, batch)

    with pytest.raises(ValuationValidationError) as raised:
        register_legend_bboxes(plate.image_path, reviewed)

    assert raised.value.code == "REGISTRATION_AFTER_DECISION"
    assert raised.value.details["decided_item_ids"] == [proposed.id]


def test_a_digest_mismatch_is_refused(
    plate: PlateArtifacts, truth: TakeoffPacket, tmp_path: Path
) -> None:
    """Âncora sobre a imagem errada mente: recusa antes de olhar um pixel."""
    tampered = tmp_path / "tampered.png"
    tampered.write_bytes(plate.image_path.read_bytes() + b"\x00")

    with pytest.raises(ValuationValidationError) as raised:
        register_legend_bboxes(tampered, truth)

    assert raised.value.code == "LEGEND_REGISTRATION_DIGEST_MISMATCH"


# --------------------------------------------------------------------------------------
# Desvio vertical constante — o defeito da 1ª rodada da Toca: casamento ordem-preservado
# sozinho "desliza em bloco" quando o desvio passa do passo entre linhas e há faixa de
# sobra (título, cabeçalho de seção) para a distância mínima vazar para a interpretação
# errada. `estimate_global_transform` estima Δ (caso particular `scale=1.0`) antes de
# casar, e só aplica com confiança suficiente.
# --------------------------------------------------------------------------------------

_JITTER_PATTERN = (0, 2, -1, 3, -2, 1, 0, -3, 2, -1, 1, 0, -2, 3, -1, 2, 0, -1, 3, -2, 1, -3, 2, 0)
"""Variação pequena e determinística do passo entre linhas (px), usada para imitar texto
real: um grid perfeitamente periódico faz até a hipótese ERRADA (deslizada N passos)
alinhar tudo com distância zero, ambiguidade que nenhum algoritmo resolve sem mais
informação. Um pouco de jitter — a variação natural de texto renderizado/escaneado — já
basta para a hipótese certa abrir margem sobre a vizinha; ver
`test_estimate_global_transform_declares_ambiguity_for_a_perfectly_periodic_pattern` para
o caso SEM jitter, que é o de ambiguidade genuína."""

_ROW_PITCH_PX = 70.0
_BAND_HEIGHT_PX = 15.0


def _row_grid_centers(count: int, *, jitter: bool) -> list[float]:
    centers: list[float] = []
    y = 500.0
    for index in range(count):
        centers.append(y)
        step = _ROW_PITCH_PX + (_JITTER_PATTERN[index % len(_JITTER_PATTERN)] if jitter else 0)
        y += step
    return centers


def _section_grid_centers(
    *, first: int, second: int, start: float = 1000.0, pitch: float = 50.0, gap: float = 90.0
) -> list[float]:
    """Duas seções de linha, como a legenda real: passo dentro da seção, vão maior entre
    seções — não um grid único perfeitamente periódico. Um grid de frequência única (só
    `_row_grid_centers`) deixa espaço para uma hipótese de escala levemente diferente de
    1.0 imitar o desvio puro quase tão bem quanto a resposta certa (a estimativa de
    transformação, ao contrário do Δ isolado da 1ª versão deste módulo, também varre
    escala); a assimetria entre as duas seções quebra esse empate."""
    centers: list[float] = []
    y = start
    for _ in range(first):
        centers.append(y)
        y += pitch
    y += gap
    for _ in range(second):
        centers.append(y)
        y += pitch
    return centers


def _band_at(center: float) -> TextBand:
    return TextBand(
        top=round(center - _BAND_HEIGHT_PX / 2), bottom=round(center + _BAND_HEIGHT_PX / 2)
    )


def _span_at(item_id: str, center: float, shift: float) -> LabeledSpan:
    return LabeledSpan(id=item_id, top=center + shift - 30, bottom=center + shift + 30)


_LEGACY_FALLBACK_HEIGHT_RATIO = 16.0
"""Espelha, só para as duas provas didáticas `falha antes` abaixo, a trava generosa por
ALTURA que o fallback residual usava antes da 3ª rodada de homologação — a produção não
tem mais essa constante (retirada de vez na 4ª rodada, junto com o fallback inteiro): os
testes `falha antes` continuam existindo para mostrar por que um casamento ingênuo sem
transformação é perigoso, chamando `match_spans_to_bands` diretamente com um limiar fixo
próprio, não mais um da produção."""


def _typical_band_height(bands: list[TextBand]) -> float:
    """Altura mediana das faixas — só o suficiente para montar a trava antiga do teste,
    sem alcançar a função privada do módulo."""
    heights = sorted(band.height for band in bands)
    return float(heights[len(heights) // 2])


_SHIFT_ITEM_COUNT = 15
_SHIFT_MAGNITUDE = (
    300.0  # > trava antiga (altura mediana x 16) e > 2 * passo — vaza pro bloco maior
)


def test_match_spans_to_bands_without_shift_correction_slides_into_the_wrong_rows() -> None:
    """`falha antes`: o casamento ordem-preservado sozinho (sem corrigir o desvio) desliza
    em bloco quando o desvio é maior que o passo e sobram faixas depois do bloco
    verdadeiro — reproduz o defeito real da 1ª rodada da Toca (itens casados linhas
    abaixo da própria porque a distância mínima vazou)."""
    grid = _section_grid_centers(first=6, second=9)  # 15 faixas de linha "reais" no grid
    distractors = [700.0, 900.0]  # título/cabeçalho, fora do grid — como a Toca
    bands = sorted([_band_at(center) for center in distractors + grid], key=lambda band: band.top)
    spans = [_span_at(f"item{i}", grid[i], _SHIFT_MAGNITUDE) for i in range(_SHIFT_ITEM_COUNT)]
    true_band_by_id = {f"item{i}": _band_at(grid[i]) for i in range(_SHIFT_ITEM_COUNT)}

    median_height = _typical_band_height(bands)
    old_style_assignment = match_spans_to_bands(
        spans, bands, max_distance=_LEGACY_FALLBACK_HEIGHT_RATIO * median_height
    )

    correctly_recovered = {
        item_id
        for item_id, band in old_style_assignment.items()
        if band == true_band_by_id[item_id]
    }
    assert correctly_recovered == set()  # nada casou com a própria linha


def test_resolve_item_bands_recovers_the_correct_rows_via_global_transform_estimation() -> None:
    """`passa depois`: a MESMA situação, mas pelo casamento completo — estima a
    transformação, aplica com confiança (`scale=1.0`, o caso particular de desvio puro) e
    casa cada item com a própria linha."""
    grid = _section_grid_centers(first=6, second=9)
    distractors = [700.0, 900.0]
    bands = sorted([_band_at(center) for center in distractors + grid], key=lambda band: band.top)
    spans = [_span_at(f"item{i}", grid[i], _SHIFT_MAGNITUDE) for i in range(_SHIFT_ITEM_COUNT)]
    true_band_by_id = {f"item{i}": _band_at(grid[i]) for i in range(_SHIFT_ITEM_COUNT)}

    assignment, estimate = resolve_item_bands(spans, bands)

    assert estimate is not None
    assert estimate.applied is True
    assert estimate.scale == pytest.approx(1.0)
    assert estimate.offset_px == pytest.approx(-_SHIFT_MAGNITUDE)
    assert len(assignment) == _SHIFT_ITEM_COUNT
    assert assignment == true_band_by_id


def test_estimate_global_transform_declares_ambiguity_for_a_perfectly_periodic_pattern() -> None:
    """Grid perfeitamente periódico, SEM jitter: deslizar um passo inteiro casa tudo de
    novo do mesmo jeito — ambiguidade genuína. O placar é calculado (declarado), mas o
    gate de confiança recusa aplicar: nunca se chuta entre duas leituras igualmente boas."""
    grid = _row_grid_centers(20, jitter=False)
    item_count = 10
    shift = 220.0  # não é múltiplo exato do passo (70): ainda assim, ambíguo com o vizinho
    bands = [_band_at(center) for center in grid]
    spans = [_span_at(f"item{i}", grid[i], shift) for i in range(item_count)]

    estimate = estimate_global_transform(spans, bands)

    assert estimate is not None
    assert estimate.applied is False
    assert estimate.confidence_margin == pytest.approx(0.0, abs=1e-9)
    assert estimate.score is not None  # declarado, mesmo sem ser aplicado


def test_estimate_global_transform_is_not_applied_when_the_winner_does_not_match_every_item() -> (
    None
):
    """Com poucos itens, um ajuste de 2 parâmetros livres `(a, b)` pode achar uma
    coincidência que vence toda hipótese concorrente por margem confortável SEM explicar
    TODOS os itens — ruído heterogêneo sem estrutura nenhuma (nem desvio constante, nem
    escala), o caso que não corresponde a nenhum dos dois defeitos reais. Exigir que a
    vencedora explique todo item fecha essa brecha."""
    grid = _row_grid_centers(8, jitter=True)
    item_count = 7
    heterogeneous_shifts = [90, 150, 110, 170, 120, 180, 140]
    spans = [
        _span_at(f"item{i}", grid[i], shift)
        for i, shift in enumerate(heterogeneous_shifts[:item_count])
    ]
    bands = [_band_at(center) for center in grid]

    estimate = estimate_global_transform(spans, bands)

    assert estimate is not None
    assert estimate.applied is False


def _draw_ink_bands(
    path: Path, *, width: int, height: int, x_range: tuple[int, int], centers: list[float]
) -> None:
    image = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(image)
    left, right = x_range
    for center in centers:
        top, bottom = round(center - _BAND_HEIGHT_PX / 2), round(center + _BAND_HEIGHT_PX / 2)
        draw.rectangle((left, top, right, bottom), fill="black")
    image.save(path, format="PNG")


def _synthetic_packet(plate_id: str, image_sha256: str, boxes: list[PlateBox]) -> TakeoffPacket:
    items = [
        TakeoffItem(
            id=takeoff_item_id(plate_id, f"ITEM {index}"),
            evidence=PlateEvidence(
                plate_id=plate_id, page_number=1, image_sha256=image_sha256, bbox=box
            ),
            raw_text=f"ITEM {index} 1,00 UN",
            label=f"ITEM {index}",
            quantity=None,
            unit="un",
            source="legend_extraction",
            extractor="teste",
            extractor_version="1.0.0",
            status=TakeoffItemStatus.AMBIGUOUS,
        )
        for index, box in enumerate(boxes)
    ]
    return TakeoffPacket(
        plate_id=plate_id,
        page_number=1,
        image_sha256=image_sha256,
        source_pdf_sha256="a" * 64,
        items=items,
        safety_notes=["nota de teste 1", "nota de teste 2"],
    )


def test_register_legend_bboxes_recovers_a_block_shift_end_to_end(tmp_path: Path) -> None:
    """A MESMA prova de ponta a ponta, pela função pública que `run_legend_extraction` e
    `register-takeoff` realmente chamam — não só pelas peças internas de casamento."""
    grid = _section_grid_centers(first=6, second=9)
    distractors = [700.0, 900.0]
    image_path = tmp_path / "synthetic-legend.png"
    _draw_ink_bands(
        image_path, width=600, height=2000, x_range=(100, 500), centers=distractors + grid
    )
    image_sha256 = file_sha256(image_path)
    shift = int(_SHIFT_MAGNITUDE)
    boxes = [
        PlateBox(
            left=100, top=round(grid[i] + shift - 25), right=500, bottom=round(grid[i] + shift + 25)
        )
        for i in range(_SHIFT_ITEM_COUNT)
    ]
    packet = _synthetic_packet("plate-teste-recuperacao", image_sha256, boxes)

    registered, report = register_legend_bboxes(image_path, packet)

    assert report.global_scale == pytest.approx(1.0)
    assert report.global_shift_px == -shift
    assert report.unmatched_item_ids == []
    by_id = {item.id: item for item in registered.items}
    for index, item in enumerate(packet.items):
        got = by_id[item.id].evidence.bbox
        true_top, true_bottom = (
            round(grid[index] - _BAND_HEIGHT_PX / 2),
            round(grid[index] + _BAND_HEIGHT_PX / 2),
        )
        contained = min(got.bottom, true_bottom) - max(got.top, true_top)
        assert contained > (got.bottom - got.top) * CONTAINMENT_THRESHOLD


def test_register_legend_bboxes_declares_ambiguity_without_applying_a_wrong_shift(
    tmp_path: Path,
) -> None:
    """Padrão periódico sem distratora nenhuma, pela função pública: a transformação não
    é aplicada e o report declara o placar mesmo assim — nada é escondido. Sem réguas
    nesta prancha (`_draw_ink_bands` não desenha bordas) e sem transformação confiante, o
    fallback residual retirado na 4ª rodada significa que NENHUM item é assentado:
    `method="none"`, `adjusted=[]`, todo item em `unmatched_item_ids`, pacote intocado."""
    grid = _row_grid_centers(20, jitter=False)
    image_path = tmp_path / "periodic-legend.png"
    _draw_ink_bands(image_path, width=500, height=2500, x_range=(100, 400), centers=grid)
    image_sha256 = file_sha256(image_path)
    item_count = 10
    shift = 220
    boxes = [
        PlateBox(
            left=100, top=round(grid[i] + shift - 30), right=400, bottom=round(grid[i] + shift + 30)
        )
        for i in range(item_count)
    ]
    packet = _synthetic_packet("plate-teste-ambiguidade", image_sha256, boxes)

    registered, report = register_legend_bboxes(image_path, packet)

    assert report.method == "none"
    assert report.adjusted == []
    assert sorted(report.unmatched_item_ids) == sorted(item.id for item in packet.items)
    assert registered is packet
    assert report.global_scale is None
    assert report.global_shift_px is None
    assert report.shift_score is not None
    assert report.shift_confidence is not None
    assert report.shift_confidence == pytest.approx(0.0, abs=1e-9)


# --------------------------------------------------------------------------------------
# Modelo afim — o defeito da 2ª rodada da Toca: medindo no overlay da 1ª correção, o
# desvio NÃO era constante — crescia com Y (item 1: +585 px; item 15: +890 px), razão
# consistente ~1,23-1,28. É erro de ESCALA na normalização Y do provedor, não
# deslocamento; um Δ puro nunca casa esse padrão. As faixas distratoras aqui imitam
# título/cabeçalho de seção: tinta só no lado do RÓTULO (esquerda), nunca no lado do
# valor — exatamente o padrão que `_filter_item_row_bands` existe para excluir (na
# prancha real, derrubou 38 faixas detectadas para as ~17 candidatas a linha de item).
# --------------------------------------------------------------------------------------

_AFFINE_LEFT, _AFFINE_RIGHT = 100, 500
_AFFINE_WIDTH = _AFFINE_RIGHT - _AFFINE_LEFT
_AFFINE_SCALE = 1.24
_AFFINE_OFFSET = 60.0
"""Parâmetros do defeito SINTÉTICO — como o VLM normalizaria Y na leitura observada,
`y_obs = escala·y_real + deslocamento` — na mesma ordem de grandeza medida na Toca real
(~1,23-1,28). O `global_scale`/`global_shift_px` que o módulo relata são a correção
inversa (leva `y_obs` de volta a `y_real`), não estes dois números diretamente — por isso
os testes verificam a POSIÇÃO recuperada, não `report.global_scale == 1.24`."""


def _affine_true_centers() -> list[float]:
    """Duas seções de linha, como a legenda real: passo dentro da seção, vão maior entre
    seções — não um grid único e perfeitamente periódico (isso teria o mesmo risco de
    ambiguidade do padrão puramente repetitivo, ver a seção de desvio constante acima)."""
    centers: list[float] = []
    y = 1000.0
    for _ in range(6):
        centers.append(y)
        y += 50.0
    y += 90.0
    for _ in range(4):
        centers.append(y)
        y += 50.0
    return centers


def _draw_affine_scenario(path: Path) -> tuple[str, list[float]]:
    """Desenha linhas de item (tinta na esquerda E na direita) e duas distratoras de
    título/cabeçalho (tinta só na esquerda); devolve o digest e os centros verdadeiros."""
    trues = _affine_true_centers()
    image = Image.new("RGB", (600, 1700), "white")
    draw = ImageDraw.Draw(image)
    for center in trues:
        top, bottom = round(center - _BAND_HEIGHT_PX / 2), round(center + _BAND_HEIGHT_PX / 2)
        draw.rectangle(
            (_AFFINE_LEFT, top, _AFFINE_LEFT + round(_AFFINE_WIDTH * 0.25), bottom), fill="black"
        )
        draw.rectangle(
            (_AFFINE_LEFT + round(_AFFINE_WIDTH * 0.75), top, _AFFINE_RIGHT, bottom), fill="black"
        )
    for center in (700.0, 900.0):  # título/cabeçalho de seção: só rótulo, longe do grid
        top, bottom = (
            round(center - _BAND_HEIGHT_PX / 2 - 1),
            round(center + _BAND_HEIGHT_PX / 2 + 1),
        )
        draw.rectangle(
            (_AFFINE_LEFT, top, _AFFINE_LEFT + round(_AFFINE_WIDTH * 0.2), bottom), fill="black"
        )
    image.save(path, format="PNG")
    return file_sha256(path), trues


def _affine_boxes(trues: list[float]) -> list[PlateBox]:
    return [
        PlateBox(
            left=_AFFINE_LEFT,
            top=round(_AFFINE_SCALE * center + _AFFINE_OFFSET - 25),
            right=_AFFINE_RIGHT,
            bottom=round(_AFFINE_SCALE * center + _AFFINE_OFFSET + 25),
        )
        for center in trues
    ]


def test_a_scale_error_without_the_filter_and_affine_model_matches_the_wrong_rows(
    tmp_path: Path,
) -> None:
    """`falha antes`: o casamento ordem-preservado com a trava antiga (sem filtrar as
    distratoras nem corrigir a escala) não recupera as linhas certas."""
    image_path = tmp_path / "affine-legend.png"
    image_sha256, trues = _draw_affine_scenario(image_path)
    boxes = _affine_boxes(trues)
    packet = _synthetic_packet("plate-teste-afim-sem-correcao", image_sha256, boxes)
    spans = [
        LabeledSpan(id=item.id, top=item.evidence.bbox.top, bottom=item.evidence.bbox.bottom)
        for item in packet.items
    ]

    image = cv2.imread(str(image_path))
    assert image is not None
    raw_bands = detect_text_bands(image, left=_AFFINE_LEFT, right=_AFFINE_RIGHT)
    median_height = _typical_band_height(raw_bands)
    naive_assignment = match_spans_to_bands(
        spans, raw_bands, max_distance=_LEGACY_FALLBACK_HEIGHT_RATIO * median_height
    )

    true_band_by_id = {item.id: _band_at(trues[index]) for index, item in enumerate(packet.items)}
    correctly_recovered = {
        item_id for item_id, band in naive_assignment.items() if band == true_band_by_id[item_id]
    }
    # sem filtrar as distratoras nem corrigir a escala, nada casa com a própria linha —
    # o que casou, casou errado (bloco deslizado), e o resto nem casa (unmatched).
    assert correctly_recovered == set()


def test_a_scale_error_is_recovered_with_the_filter_and_affine_model_end_to_end(
    tmp_path: Path,
) -> None:
    """`passa depois`: pela função pública, com o filtro (derruba as distratoras
    título/cabeçalho) e o modelo afim (recupera a escala) juntos — os seis primeiros
    itens assentam nas seis linhas da primeira seção, e a segunda seção também."""
    image_path = tmp_path / "affine-legend.png"
    image_sha256, trues = _draw_affine_scenario(image_path)
    boxes = _affine_boxes(trues)
    packet = _synthetic_packet("plate-teste-afim", image_sha256, boxes)

    registered, report = register_legend_bboxes(image_path, packet)

    assert report.unmatched_item_ids == []
    assert report.global_scale is not None
    assert report.global_scale != pytest.approx(1.0)  # não é um desvio puro: é escala
    assert report.shift_confidence is not None
    by_id = {item.id: item for item in registered.items}
    for index, item in enumerate(packet.items):
        got = by_id[item.id].evidence.bbox
        true_top = round(trues[index] - _BAND_HEIGHT_PX / 2)
        true_bottom = round(trues[index] + _BAND_HEIGHT_PX / 2)
        contained = min(got.bottom, true_bottom) - max(got.top, true_top)
        assert contained > (got.bottom - got.top) * CONTAINMENT_THRESHOLD, item.label


# --------------------------------------------------------------------------------------
# Réguas de tabela e fallback residual — os defeitos da 3ª e da 4ª rodada de homologação.
# 3ª rodada: extração nova veio com x-range diferente, o filtro de divisor não reduziu o
# ruído (34 faixas), o gate afim recusou CERTO — e o fallback ANTIGO (trava generosa por
# altura) assentou 11 itens deslizados ~6 linhas, com âncora mentindo pra revisora.
# 4ª rodada: MESMO a trava apertada que corrigiu a 3ª rodada (1,2x o passo) ainda assentou
# 9 itens na seção vizinha errada — 1,2x o passo é maior que o próprio passo entre linhas
# adjacentes, então dentro do aglomerado denso sempre existe alguma candidata "perto o
# bastante". A correção final retirou o fallback residual por completo: sem bijeção de
# réguas e sem transformação global confiante, NADA é assentado.
# --------------------------------------------------------------------------------------


def _multi_section_grid_centers(
    sizes: list[int], *, pitch: float = 47.0, gap: float = 95.0, start: float = 2350.0
) -> list[float]:
    """Como `_section_grid_centers`, mas para quantas seções `sizes` pedir — imita uma
    legenda real com várias seções (PISO E REVESTIMENTO, MOBILIÁRIO URBANO, ...)."""
    centers: list[float] = []
    y = start
    for size in sizes:
        for _ in range(size):
            centers.append(y)
            y += pitch
        y += gap - pitch
    return centers


def test_without_a_confident_transform_the_retired_fallback_leaves_everything_untouched() -> None:
    """Emula o defeito da 3ª rodada (item com desvio grande, ~300px, a magnitude
    relatada — "verdadeiro ≈2400-2460, foi parar em top=2737") sobre uma legenda em
    seções, com ruído heterogêneo o bastante nos outros itens pra recusar a
    transformação — E o defeito da 4ª rodada: mesmo a trava de 1,2x o passo (que corrigia
    a 3ª) ainda deixava itens vizinhos morderem o anzol errado quando caíam dentro do
    aglomerado denso de linhas. A correção final não tem trava nenhuma pra calibrar: sem
    transformação confiante, `resolve_item_bands` não assenta NINGUÉM — o dict de
    casamento vem vazio, todo item intocado."""
    grid = _multi_section_grid_centers([6, 5, 2, 2])
    bands = [_band_at(center) for center in grid]
    item_count = len(grid)
    # item0 imita o "PISO EM CONCRETO" do bug real; os demais têm deslocamentos
    # heterogêneos variados (não afins entre si) — o mesmo tipo de ruído que fez o gate
    # recusar na rodada real, alguns bem dentro do aglomerado denso de linhas vizinhas.
    shifts = [307.0, 157, 155, 155, 154, 94, 218, 205, 205, 116, 116, 8, 8, 20, 25][:item_count]
    spans = [_span_at(f"item{i}", grid[i], shift) for i, shift in enumerate(shifts)]

    estimate = estimate_global_transform(spans, bands)
    assert estimate is not None
    assert estimate.applied is False  # confiança recusada, como na rodada real

    assignment, returned_estimate = resolve_item_bands(spans, bands)

    assert assignment == {}  # fallback residual morreu: nenhum item é assentado
    assert returned_estimate == estimate  # a estimativa ainda é declarada, só não aplicada


def _draw_ruled_table(path: Path, *, rows: int, top0: int, row_height: int) -> list[float]:
    """Desenha uma tabela com bordas — réguas horizontais em cada fronteira de linha,
    sem cabeçalho — e devolve os centros verdadeiros de cada linha."""
    image = Image.new("RGB", (600, top0 + rows * row_height + 200), "white")
    draw = ImageDraw.Draw(image)
    for index in range(rows + 1):
        y = top0 + index * row_height
        draw.line((100, y, 500, y), fill="black", width=1)
    centers = []
    for index in range(rows):
        y = top0 + index * row_height
        draw.rectangle((105, y + 15, 200, y + 30), fill="black")
        draw.rectangle((420, y + 15, 495, y + 30), fill="black")
        centers.append(y + row_height / 2)
    image.save(path, format="PNG")
    return centers


def test_ruling_cells_give_an_exact_bijection_even_with_a_scale_applied_to_the_boxes(
    tmp_path: Path,
) -> None:
    """Tabela com bordas, sem cabeçalho: 7 réguas-célula para 7 itens é bijeção EXATA
    (nenhuma transformação estimada), robusta mesmo com escala e deslocamento aplicados
    aos bboxes propostos — a ordem já é a resposta."""
    image_path = tmp_path / "ruled-table.png"
    true_centers = _draw_ruled_table(image_path, rows=7, top0=300, row_height=50)
    image_sha256 = file_sha256(image_path)
    scale, offset = 1.3, -100.0
    boxes = [
        PlateBox(
            left=100,
            top=round(scale * center + offset - 15),
            right=500,
            bottom=round(scale * center + offset + 15),
        )
        for center in true_centers
    ]
    packet = _synthetic_packet("plate-teste-reguas-exatas", image_sha256, boxes)

    registered, report = register_legend_bboxes(image_path, packet)

    assert report.method == "rulings"
    assert report.band_count == len(true_centers)
    assert report.unmatched_item_ids == []
    assert report.global_scale is None  # bijeção direta: não precisou estimar nada
    assert report.global_shift_px is None
    by_id = {item.id: item for item in registered.items}
    for index, item in enumerate(packet.items):
        got = by_id[item.id].evidence.bbox
        true_top = round(true_centers[index] - 25)
        true_bottom = round(true_centers[index] + 25)
        contained = min(got.bottom, true_bottom) - max(got.top, true_top)
        assert contained > (got.bottom - got.top) * CONTAINMENT_THRESHOLD


def test_a_plate_without_rulings_falls_back_to_the_text_band_pipeline(tmp_path: Path) -> None:
    """Legenda sem linha de grade nenhuma (só posição de texto, como a fixture sintética
    original deste repositório): réguas não encontram nada confiável, e o casamento
    reproduz o pipeline de faixas de texto + afim de antes — `method="text_bands"`."""
    grid = _section_grid_centers(first=6, second=9)
    distractors = [700.0, 900.0]
    image_path = tmp_path / "no-rulings.png"
    _draw_ink_bands(
        image_path, width=600, height=2000, x_range=(100, 500), centers=distractors + grid
    )
    image_sha256 = file_sha256(image_path)
    shift = 300
    boxes = [
        PlateBox(
            left=100, top=round(center + shift - 25), right=500, bottom=round(center + shift + 25)
        )
        for center in grid
    ]
    packet = _synthetic_packet("plate-teste-sem-reguas", image_sha256, boxes)

    registered, report = register_legend_bboxes(image_path, packet)

    assert report.method == "text_bands"
    assert report.global_scale == pytest.approx(1.0)
    assert report.global_shift_px == -shift
    assert report.unmatched_item_ids == []
    by_id = {item.id: item for item in registered.items}
    for index, item in enumerate(packet.items):
        got = by_id[item.id].evidence.bbox
        true_top = round(grid[index] - _BAND_HEIGHT_PX / 2)
        true_bottom = round(grid[index] + _BAND_HEIGHT_PX / 2)
        contained = min(got.bottom, true_bottom) - max(got.top, true_top)
        assert contained > (got.bottom - got.top) * CONTAINMENT_THRESHOLD


# --------------------------------------------------------------------------------------
# Filtro de célula por régua vertical interna — o defeito da 4ª rodada de homologação:
# uma célula de NOTA mesclada no MEIO da tabela (não numa ponta — a bijeção aparada não
# alcança esse caso) quebrava a bijeção exata por 1 (16 réguas para 15 itens, ou pior).
# Linha de ITEM de verdade tem um divisor vertical rótulo|valor DENTRO da própria célula,
# com tinta dos dois lados; a nota, mesclada e sem divisor nenhum, não tem. A prancha
# sintética original deste repositório (`test_ruling_cells_give_an_exact_bijection_...`,
# `test_a_plate_without_rulings_falls_back_...` acima) não desenha divisor interno algum
# — o filtro tem de continuar gracioso ali (mantém tudo), o que essas duas já provam
# continuar acontecendo sem precisar de um teste extra dedicado.
# --------------------------------------------------------------------------------------


def _draw_ruled_table_with_a_merged_note(
    path: Path, *, item_rows: int, note_at: int, top0: int, row_height: int
) -> list[float]:
    """Tabela com bordas como `_draw_ruled_table`, mas com uma linha de NOTA mesclada
    (célula de largura total, texto curto — bem mais baixo que a própria célula, então
    nenhuma coluna chega perto de `VERTICAL_DIVIDER_MIN_HEIGHT_RATIO` da altura) inserida
    no ÍNDICE `note_at` entre as linhas de item — mesma posição do defeito real (nota no
    MEIO da tabela, não numa ponta, onde a bijeção aparada já resolveria sozinha). Linha
    de ITEM tem, além do texto de rótulo e de valor, um divisor vertical interno alto o
    bastante para contar como régua. Devolve os centros verdadeiros só das linhas de
    ITEM, na ordem em que aparecem na tabela."""
    total_rows = item_rows + 1
    image = Image.new("RGB", (600, top0 + total_rows * row_height + 200), "white")
    draw = ImageDraw.Draw(image)
    for index in range(total_rows + 1):
        y = top0 + index * row_height
        draw.line((100, y, 500, y), fill="black", width=1)
    item_centers: list[float] = []
    for index in range(total_rows):
        y = top0 + index * row_height
        if index == note_at:
            draw.rectangle((105, y + 18, 495, y + 32), fill="black")  # nota: bloco só, sem divisor
            continue
        draw.rectangle((105, y + 15, 200, y + 30), fill="black")  # rótulo
        draw.rectangle((420, y + 15, 495, y + 30), fill="black")  # valor
        draw.line((300, y + 5, 300, y + row_height - 5), fill="black", width=1)  # divisor interno
        item_centers.append(y + row_height / 2)
    image.save(path, format="PNG")
    return item_centers


def test_a_merged_note_cell_without_an_internal_divider_is_excluded_and_bijection_still_works(
    tmp_path: Path,
) -> None:
    """O defeito real da 4ª rodada: célula de NOTA no MEIO da tabela (não numa ponta) é
    o caso "N+1 no meio" que a bijeção aparada não alcança sozinha. O filtro de régua
    vertical interna exclui a nota (ela não tem divisor nenhum, só texto curto) ANTES do
    casamento — sobram exatamente as células de item, e a bijeção exata fecha de novo."""
    image_path = tmp_path / "ruled-table-with-note.png"
    item_centers = _draw_ruled_table_with_a_merged_note(
        image_path, item_rows=6, note_at=3, top0=300, row_height=50
    )
    image_sha256 = file_sha256(image_path)
    boxes = [
        PlateBox(left=100, top=round(center - 15), right=500, bottom=round(center + 15))
        for center in item_centers
    ]
    packet = _synthetic_packet("plate-teste-nota-no-meio", image_sha256, boxes)

    registered, report = register_legend_bboxes(image_path, packet)

    assert report.method == "rulings"
    assert report.band_count == len(item_centers)  # a nota não entra na contagem
    assert report.unmatched_item_ids == []
    assert report.global_scale is None  # bijeção direta: não precisou estimar nada
    assert report.global_shift_px is None
    by_id = {item.id: item for item in registered.items}
    for index, item in enumerate(packet.items):
        got = by_id[item.id].evidence.bbox
        true_top = round(item_centers[index] - 25)
        true_bottom = round(item_centers[index] + 25)
        contained = min(got.bottom, true_bottom) - max(got.top, true_top)
        assert contained > (got.bottom - got.top) * CONTAINMENT_THRESHOLD


# --------------------------------------------------------------------------------------
# restore_raw_bboxes — reprocessar do bruto sem nova chamada paga
# --------------------------------------------------------------------------------------


def test_restore_raw_bboxes_reverts_only_the_adjusted_items_to_their_before_value(
    plate: PlateArtifacts, truth: TakeoffPacket
) -> None:
    """Registra uma vez (produz `adjusted` com `before`/`after`), constrói um pacote
    "já mexido" a partir do `after`, e confere que `restore_raw_bboxes` devolve
    exatamente o bbox `before` de cada item ajustado — item que não foi ajustado (se
    houver) fica como está, e nenhum campo fora do bbox muda."""
    shifted = _repackage(truth, [_shift(item, 140) for item in truth.items])
    registered, report = register_legend_bboxes(plate.image_path, shifted)
    assert report.adjusted  # a prancha real sempre ajusta pelo menos um item aqui

    restored = restore_raw_bboxes(registered, report.adjusted)

    before_by_id = {
        str(entry["item_id"]): PlateBox.model_validate(entry["before"]) for entry in report.adjusted
    }
    original_by_id = {item.id: item for item in shifted.items}
    for item in restored.items:
        assert item.evidence.bbox == before_by_id[item.id]
        assert item.evidence.bbox == original_by_id[item.id].evidence.bbox
        assert item.label == original_by_id[item.id].label
        assert item.quantity == original_by_id[item.id].quantity


def test_restore_raw_bboxes_is_a_no_op_without_any_adjusted_entry(
    plate: PlateArtifacts, truth: TakeoffPacket
) -> None:
    restored = restore_raw_bboxes(truth, [])
    assert restored is truth


def test_restore_raw_bboxes_refuses_a_packet_with_a_decided_item(
    plate: PlateArtifacts, truth: TakeoffPacket
) -> None:
    """Mesma regra e mesmo código de `register_legend_bboxes`: mover a âncora depois de
    uma decisão do orçamentista reescreveria o que ele viu — restaurando ou não."""
    proposed = next(item for item in truth.items if item.quantity is not None)
    batch = TakeoffDecisionBatch(
        decisions=[
            TakeoffDecisionInput(
                item_id=proposed.id,
                action="confirm",
                reviewer_id="orcamentista-de-teste",
                reviewer_role="orcamentista",
                decided_at=_DECIDED_AT,
            )
        ]
    )
    reviewed = apply_takeoff_decisions(truth, batch)

    with pytest.raises(ValuationValidationError) as raised:
        restore_raw_bboxes(reviewed, [])

    assert raised.value.code == "REGISTRATION_AFTER_DECISION"
    assert raised.value.details["decided_item_ids"] == [proposed.id]


# --------------------------------------------------------------------------------------
# CLI — register-takeoff
# --------------------------------------------------------------------------------------


def _stdout(capsys: pytest.CaptureFixture[str]) -> dict[str, object]:
    lines = [line for line in capsys.readouterr().out.splitlines() if line.strip()]
    return dict(json.loads(lines[-1]))


def _is_empty(directory: Path) -> bool:
    return not directory.exists() or list(directory.iterdir()) == []


def _extract(output_dir: Path) -> None:
    assert main(["extract-legend", "--output", str(output_dir)]) == 0


def _register(packet_path: Path, image_path: Path, output_dir: Path) -> int:
    return main(
        [
            "register-takeoff",
            "--packet",
            str(packet_path),
            "--image",
            str(image_path),
            "--output",
            str(output_dir),
        ]
    )


def _register_restore_raw(packet_path: Path, image_path: Path, output_dir: Path) -> int:
    return main(
        [
            "register-takeoff",
            "--packet",
            str(packet_path),
            "--image",
            str(image_path),
            "--output",
            str(output_dir),
            "--restore-raw",
        ]
    )


def test_register_takeoff_publishes_the_packet_overlay_and_report(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    extracted = tmp_path / "extract"
    _extract(extracted)
    _stdout(capsys)
    output_dir = tmp_path / "register"

    exit_code = _register(
        extracted / TAKEOFF_PACKET_FILENAME, extracted / "prancha.png", output_dir
    )

    assert exit_code == 0
    payload = _stdout(capsys)
    assert payload["adjusted"] == 7
    assert payload["unmatched"] == 0
    # A prancha sintética é tabela com bordas: 8 réguas-célula (cabeçalho de coluna + 7
    # itens) para 7 itens é o caso "N+1" — bijeção aparada, sem precisar de transformação
    # nenhuma (por isso os campos de transformação ficam None, mesmo com ajuste).
    assert payload["method"] == "rulings"
    assert payload["global_scale"] is None
    assert payload["global_shift_px"] is None
    assert payload["shift_score"] is None
    assert payload["shift_confidence"] is None
    for filename in (
        TAKEOFF_PACKET_FILENAME,
        TAKEOFF_OVERLAY_FILENAME,
        TAKEOFF_REGISTRATION_REPORT_FILENAME,
    ):
        assert (output_dir / filename).is_file()
    registered = load_takeoff_packet(output_dir / TAKEOFF_PACKET_FILENAME)
    original = load_takeoff_packet(extracted / TAKEOFF_PACKET_FILENAME)
    assert [item.id for item in registered.items] == [item.id for item in original.items]
    assert registered.items[0].evidence.bbox != original.items[0].evidence.bbox
    report = json.loads((output_dir / TAKEOFF_REGISTRATION_REPORT_FILENAME).read_text())
    assert len(report["adjusted"]) == 7
    assert report["unmatched_item_ids"] == []
    assert report["band_count"] == payload["band_count"]
    assert report["global_scale"] == payload["global_scale"]
    assert report["global_shift_px"] == payload["global_shift_px"]
    assert report["shift_score"] == payload["shift_score"]
    assert report["shift_confidence"] == payload["shift_confidence"]


def test_register_takeoff_refuses_a_packet_with_a_decided_item_and_publishes_nothing(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    extracted = tmp_path / "extract"
    _extract(extracted)
    _stdout(capsys)
    packet = load_takeoff_packet(extracted / TAKEOFF_PACKET_FILENAME)
    proposed = next(item for item in packet.items if item.quantity is not None)
    batch = TakeoffDecisionBatch(
        decisions=[
            TakeoffDecisionInput(
                item_id=proposed.id,
                action="confirm",
                reviewer_id="orcamentista-de-teste",
                reviewer_role="orcamentista",
                decided_at=_DECIDED_AT,
            )
        ]
    )
    decisions_path = tmp_path / "decisions.json"
    decisions_path.write_text(batch.model_dump_json(indent=2), encoding="utf-8")
    reviewed_dir = tmp_path / "reviewed"
    assert (
        main(
            [
                "review-takeoff",
                "--packet",
                str(extracted / TAKEOFF_PACKET_FILENAME),
                "--decisions",
                str(decisions_path),
                "--output",
                str(reviewed_dir),
            ]
        )
        == 0
    )
    _stdout(capsys)
    output_dir = tmp_path / "register"

    exit_code = _register(
        reviewed_dir / TAKEOFF_PACKET_FILENAME, extracted / "prancha.png", output_dir
    )

    assert exit_code == 2
    assert _stdout(capsys)["refused"] == "REGISTRATION_AFTER_DECISION"
    assert _is_empty(output_dir)


def test_register_takeoff_refuses_an_image_that_is_not_the_plate_of_the_packet(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    extracted = tmp_path / "extract"
    _extract(extracted)
    _stdout(capsys)
    tampered = tmp_path / "tampered.png"
    tampered.write_bytes((extracted / "prancha.png").read_bytes() + b"\x00")
    output_dir = tmp_path / "register"

    exit_code = _register(extracted / TAKEOFF_PACKET_FILENAME, tampered, output_dir)

    assert exit_code == 2
    assert _stdout(capsys)["refused"] == "LEGEND_REGISTRATION_DIGEST_MISMATCH"
    assert _is_empty(output_dir)


def test_register_takeoff_with_restore_raw_reprocesses_from_the_original_extraction(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """`--restore-raw` reverte o pacote (já registrado por uma rodada anterior) pro bruto
    usando o `before` do `takeoff-registration.json` que já existe ao lado dele, e
    registra de novo — o resultado é idêntico ao de registrar o pacote ORIGINAL da
    extração, ponta a ponta: mesmo pipeline determinístico, mesmo bruto."""
    extracted = tmp_path / "extract"
    _extract(extracted)
    _stdout(capsys)
    first_output = tmp_path / "register-first"
    assert (
        _register(extracted / TAKEOFF_PACKET_FILENAME, extracted / "prancha.png", first_output) == 0
    )
    first_payload = _stdout(capsys)

    second_output = tmp_path / "register-restored"
    exit_code = _register_restore_raw(
        first_output / TAKEOFF_PACKET_FILENAME, extracted / "prancha.png", second_output
    )

    assert exit_code == 0
    second_payload = _stdout(capsys)
    assert second_payload["adjusted"] == first_payload["adjusted"]
    assert second_payload["unmatched"] == first_payload["unmatched"]
    assert second_payload["method"] == first_payload["method"]
    first_registered = load_takeoff_packet(first_output / TAKEOFF_PACKET_FILENAME)
    second_registered = load_takeoff_packet(second_output / TAKEOFF_PACKET_FILENAME)
    assert [item.evidence.bbox for item in second_registered.items] == [
        item.evidence.bbox for item in first_registered.items
    ]


def test_register_takeoff_with_restore_raw_refuses_without_a_prior_report(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Sem um `takeoff-registration.json` de rodada anterior ao lado do pacote, não há
    bruto nenhum pra restaurar — recusa fechada, nada publicado."""
    extracted = tmp_path / "extract"
    _extract(extracted)
    _stdout(capsys)
    output_dir = tmp_path / "register"

    exit_code = _register_restore_raw(
        extracted / TAKEOFF_PACKET_FILENAME, extracted / "prancha.png", output_dir
    )

    assert exit_code == 2
    assert _stdout(capsys)["refused"] == "REGISTRATION_RESTORE_RAW_REPORT_MISSING"
    assert _is_empty(output_dir)


def test_register_takeoff_with_restore_raw_refuses_a_packet_with_a_decided_item(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    extracted = tmp_path / "extract"
    _extract(extracted)
    _stdout(capsys)
    rodada_dir = tmp_path / "rodada"
    assert (
        _register(extracted / TAKEOFF_PACKET_FILENAME, extracted / "prancha.png", rodada_dir) == 0
    )
    _stdout(capsys)
    registered = load_takeoff_packet(rodada_dir / TAKEOFF_PACKET_FILENAME)
    proposed = next(item for item in registered.items if item.quantity is not None)
    batch = TakeoffDecisionBatch(
        decisions=[
            TakeoffDecisionInput(
                item_id=proposed.id,
                action="confirm",
                reviewer_id="orcamentista-de-teste",
                reviewer_role="orcamentista",
                decided_at=_DECIDED_AT,
            )
        ]
    )
    decisions_path = tmp_path / "decisions.json"
    decisions_path.write_text(batch.model_dump_json(indent=2), encoding="utf-8")
    # revisa no mesmo diretório da rodada de registro: o takeoff-registration.json de lá
    # continua ao lado do pacote, do jeito que uma rodada real reaproveitaria o artefato.
    assert (
        main(
            [
                "review-takeoff",
                "--packet",
                str(rodada_dir / TAKEOFF_PACKET_FILENAME),
                "--decisions",
                str(decisions_path),
                "--output",
                str(rodada_dir),
            ]
        )
        == 0
    )
    _stdout(capsys)
    output_dir = tmp_path / "register-restore"

    exit_code = _register_restore_raw(
        rodada_dir / TAKEOFF_PACKET_FILENAME, extracted / "prancha.png", output_dir
    )

    assert exit_code == 2
    assert _stdout(capsys)["refused"] == "REGISTRATION_AFTER_DECISION"
    assert _is_empty(output_dir)
