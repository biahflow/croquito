"""Construção de um pacote de revisão sintético válido para `seed-review`.

Os quatro digests de imagem e o digest do documento são amarrados ao que é realmente
gravado em disco, porque é exatamente essa cadeia que o comando verifica.
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from PIL import Image
from pydantic import BaseModel

from croquito_worker.association import AssociationSet
from croquito_worker.ingest import PageManifest, PdfManifest
from croquito_worker.rectangle_solver import RectangleSolveRequest
from croquito_worker.review import (
    DimensionReading,
    EvidenceRegion,
    HumanDecision,
    PixelBox,
    ReadingStatus,
    ReviewPacket,
)
from croquito_worker.vision import (
    PixelCircle,
    PixelLine,
    PixelPoint,
    VisionProposal,
    VisionProposalSet,
)

WIDTH_READING_ID = "rd_1111111111111111"
HEIGHT_READING_ID = "rd_2222222222222222"
CIRCLE_READING_ID = "rd_3333333333333333"
WIDTH_PROPOSAL_ID = "vp_1111111111111111"
HEIGHT_PROPOSAL_ID = "vp_2222222222222222"
CIRCLE_PROPOSAL_ID = "vp_3333333333333333"

ELEVATION_READING_ID = "rd_4444444444444444"
ELEVATION_PROPOSAL_ID = "vp_4444444444444444"

#: As duas cotas-balão da F-051: medida escrita LONGE do que ela mede, ligada ao referente
#: pela letra. A primeira casa com o elemento "B" declarado; a segunda cita um "E" que
#: ninguém declarou, e por isso continua no caminho de hoje (critério de aceite 2).
BALLOON_READING_ID = "rd_5555555555555555"
ORPHAN_BALLOON_READING_ID = "rd_6666666666666666"

WIDTH_M = "25.90"
HEIGHT_M = "21.75"
CIRCLE_DIAMETER_M = "6.00"
ELEVATION_M = "3.80"
BALLOON_M = "25.90"
ORPHAN_BALLOON_M = "4.40"


def _write_json(path: Path, payload: BaseModel) -> Path:
    path.write_text(
        json.dumps(payload.model_dump(mode="json"), ensure_ascii=False), encoding="utf-8"
    )
    return path


def _reading(
    identifier: str,
    *,
    dataset_id: str,
    digest: str,
    value: str,
    kind: str,
    hint: str,
    left: int,
    decided: bool,
    raw_text: str | None = None,
    ocr_corroborated: bool | None = None,
    entity_label: str | None = None,
) -> DimensionReading:
    decision = (
        HumanDecision(
            decision_id="hd_" + "a" * 16,
            action="confirm",
            reviewer_id="reviewer",
            reviewer_role="engineer",
            decided_at=datetime.now(UTC),
            note="Decisão fabricada que o seed precisa recusar.",
        )
        if decided
        else None
    )
    return DimensionReading(
        id=identifier,
        evidence=EvidenceRegion(
            dataset_id=dataset_id,
            page_number=1,
            image_sha256=digest,
            bbox=PixelBox(left=left, top=5, right=left + 20, bottom=15),
        ),
        raw_text=raw_text or f"{value} m",
        value_si=Decimal(value),
        unit="m",
        kind=kind,
        written_decimals=2,
        target_hint=hint,
        target_entity_label=entity_label,
        extractor="local-fixture",
        extractor_version="v1",
        ocr_corroborated=ocr_corroborated,
        status=ReadingStatus.CONFIRMED if decided else ReadingStatus.PROPOSED,
        decision=decision,
    )


def build_packet(
    *,
    dataset_id: str,
    digest: str,
    decided: bool = False,
    elevation: bool = False,
    balloons: bool = False,
) -> ReviewPacket:
    """Pacote sintético do bundle. `elevation` acrescenta uma quarta leitura (F-029/T6).

    A elevação (`h=3,80`, kind `height`) é a leitura SEM papel de geometria de planta que
    o tier de anotação existe para resolver: ela não é citada pelo pedido do solver, e o
    braço de OCR rodou sem encontrá-la — testemunha única, exatamente o caso das 8
    elevações da rodada real V4 que motivaram o ADR-0044.

    `balloons` acrescenta as duas cotas-balão da F-051, escritas LONGE do que medem (`left`
    100 e 120, contra propostas que vivem entre 0 e 30 px) e sem candidata de proximidade
    nenhuma: `C=25,90 m`, que aponta o elemento "B", e `h=4,40 m`, que aponta um "E" que
    ninguém declara. A letra não está no texto da cota: ela chega no rótulo ESTRUTURADO
    (`target_entity_label`, F-051 T1), que é o campo por onde o casamento por identidade
    procura o referente — e é essa separação que a feature existe para explorar.
    """
    return ReviewPacket(
        dataset_id=dataset_id,
        page_number=1,
        image_sha256=digest,
        readings=[
            _reading(
                WIDTH_READING_ID,
                dataset_id=dataset_id,
                digest=digest,
                value=WIDTH_M,
                kind="width",
                hint="campo principal",
                left=0,
                decided=decided,
            ),
            _reading(
                HEIGHT_READING_ID,
                dataset_id=dataset_id,
                digest=digest,
                value=HEIGHT_M,
                kind="height",
                hint="campo principal",
                left=20,
                decided=decided,
            ),
            _reading(
                CIRCLE_READING_ID,
                dataset_id=dataset_id,
                digest=digest,
                value=CIRCLE_DIAMETER_M,
                kind="diameter",
                hint="círculo central",
                left=40,
                decided=decided,
            ),
            *(
                [
                    _reading(
                        ELEVATION_READING_ID,
                        dataset_id=dataset_id,
                        digest=digest,
                        value=ELEVATION_M,
                        kind="height",
                        hint="mureta do fundo",
                        left=60,
                        decided=decided,
                        raw_text=f"h={ELEVATION_M.replace('.', ',')}",
                        ocr_corroborated=False,
                    )
                ]
                if elevation
                else []
            ),
            *(
                [
                    _reading(
                        BALLOON_READING_ID,
                        dataset_id=dataset_id,
                        digest=digest,
                        value=BALLOON_M,
                        kind="width",
                        hint="(B) fecho da área",
                        left=100,
                        decided=decided,
                        raw_text=f"C={BALLOON_M.replace('.', ',')} m",
                        entity_label="B",
                    ),
                    _reading(
                        ORPHAN_BALLOON_READING_ID,
                        dataset_id=dataset_id,
                        digest=digest,
                        value=ORPHAN_BALLOON_M,
                        kind="height",
                        hint="(E) altura do balão órfão",
                        left=120,
                        decided=decided,
                        raw_text=f"h={ORPHAN_BALLOON_M.replace('.', ',')} m",
                        entity_label="E",
                    ),
                ]
                if balloons
                else []
            ),
        ],
        safety_notes=["Fixture local.", "Revisão humana obrigatória."],
    )


def build_associations(
    *,
    dataset_id: str,
    digest: str,
    drop_circle: bool = False,
    elevation: bool = False,
    balloons: bool = False,
    association_confidences: dict[str, float] | None = None,
) -> AssociationSet:
    """Candidatos do bundle sintético; `association_confidences` é opt-in por leitura.

    A fixture não passa por `associate_readings` — os candidatos são escritos à mão —, e
    sem valor explícito cada um fica no default 0.0 do contrato. Esse é o estado histórico
    do bundle e continua sendo o padrão: só quem testa corte de confiança declara números,
    e assim nenhum outro teste muda de comportamento por causa deste parâmetro.
    """
    confidences = association_confidences or {}
    candidates: list[dict[str, Any]] = [
        {
            "reading_id": WIDTH_READING_ID,
            "proposal_id": WIDTH_PROPOSAL_ID,
            "proposal_kind": "line",
            "relation": "nearest_geometry",
            "pixel_distance": 1,
            "proximity_score": 0.9,
            "visual_quality_score": 0.8,
        },
        {
            "reading_id": HEIGHT_READING_ID,
            "proposal_id": HEIGHT_PROPOSAL_ID,
            "proposal_kind": "line",
            "relation": "nearest_geometry",
            "pixel_distance": 1,
            "proximity_score": 0.9,
            "visual_quality_score": 0.8,
        },
        {
            "reading_id": CIRCLE_READING_ID,
            "proposal_id": CIRCLE_PROPOSAL_ID,
            "proposal_kind": "circle",
            "relation": "inside_or_near_circle",
            "pixel_distance": 1,
            "proximity_score": 0.9,
            "visual_quality_score": 0.8,
        },
    ]
    if drop_circle:
        candidates = candidates[:2]
    if elevation:
        candidates.append(
            {
                "reading_id": ELEVATION_READING_ID,
                "proposal_id": ELEVATION_PROPOSAL_ID,
                "proposal_kind": "line",
                "relation": "nearest_geometry",
                "pixel_distance": 1,
                "proximity_score": 0.9,
                "visual_quality_score": 0.8,
            }
        )
    for candidate in candidates:
        confidence = confidences.get(str(candidate["reading_id"]))
        if confidence is not None:
            candidate["association_confidence"] = confidence
    # As cotas-balão nascem SEM candidata: é a definição do caso — o funil de proximidade
    # não alcança o referente do outro lado da folha. Elas entram na lista das não
    # associadas, que é onde o associador as deixa.
    unassociated = [CIRCLE_READING_ID] if drop_circle else []
    if balloons:
        unassociated = [*unassociated, BALLOON_READING_ID, ORPHAN_BALLOON_READING_ID]
    return AssociationSet.model_validate(
        {
            "dataset_id": dataset_id,
            "page_number": 1,
            "image_sha256": digest,
            "candidates": candidates,
            "unassociated_reading_ids": unassociated,
            "safety_notes": ["pixels", "não confirma", "não exporta"],
        }
    )


def build_proposals(*, dataset_id: str, digest: str, elevation: bool = False) -> VisionProposalSet:
    return VisionProposalSet(
        dataset_id=dataset_id,
        page_number=1,
        image_sha256=digest,
        image_width_px=40,
        image_height_px=30,
        configured_limits={"line": 80, "circle": 16, "contour": 16},
        limit_reached=[],
        proposals=[
            VisionProposal(
                id=WIDTH_PROPOSAL_ID,
                kind="line",
                geometry=PixelLine(start=PixelPoint(x=0, y=0), end=PixelPoint(x=30, y=0)),
                algorithm="fixture",
                quality_score=0.9,
            ),
            VisionProposal(
                id=HEIGHT_PROPOSAL_ID,
                kind="line",
                geometry=PixelLine(start=PixelPoint(x=0, y=0), end=PixelPoint(x=0, y=20)),
                algorithm="fixture",
                quality_score=0.9,
            ),
            VisionProposal(
                id=CIRCLE_PROPOSAL_ID,
                kind="circle",
                geometry=PixelCircle(center=PixelPoint(x=15, y=10), radius=4),
                algorithm="fixture",
                quality_score=0.9,
            ),
            # A mureta que a elevação anota: forma aceita como qualquer outra, e o
            # pedido do solver retangular não a cita.
            *(
                [
                    VisionProposal(
                        id=ELEVATION_PROPOSAL_ID,
                        kind="line",
                        geometry=PixelLine(
                            start=PixelPoint(x=30, y=25), end=PixelPoint(x=38, y=25)
                        ),
                        algorithm="fixture",
                        quality_score=0.9,
                    )
                ]
                if elevation
                else []
            ),
        ],
        safety_notes=["fixture", "pixels", "não exportável"],
    )


def build_manifest(*, dataset_id: str, digest: str, source_sha256: str) -> PdfManifest:
    return PdfManifest(
        dataset_id=dataset_id,
        role="golden",
        source_basename="levantamento.pdf",
        source_sha256=source_sha256,
        source_size_bytes=1024,
        page_count=1,
        encrypted=False,
        rendered_at=datetime.now(UTC),
        renderer="pymupdf",
        retention_notice="Retenção local de sete dias.",
        pages=[
            PageManifest(
                number=1,
                width_points=595.0,
                height_points=842.0,
                rotation_degrees=0,
                rendered_width_px=40,
                rendered_height_px=30,
                ink_coverage=0.1,
                text_character_count=10,
                vector_drawing_count=2,
                blank_candidate=False,
                image_sha256=digest,
                render_file="page-001.png",
            )
        ],
    )


def build_request(*, with_centre_circle: bool = True) -> RectangleSolveRequest:
    return RectangleSolveRequest(
        feature_id="campo-principal",
        width_reading_id=WIDTH_READING_ID,
        height_reading_id=HEIGHT_READING_ID,
        centre_circle_reading_id=CIRCLE_READING_ID if with_centre_circle else None,
        require_centre_circle=with_centre_circle,
    )


def write_seed_bundle(
    directory: Path,
    *,
    source_sha256: str,
    dataset_id: str = "golden-local-v1",
    decided: bool = False,
    drop_circle_candidate: bool = False,
    manifest_source_sha256: str | None = None,
    association_confidences: dict[str, float] | None = None,
    elevation: bool = False,
    balloons: bool = False,
) -> dict[str, Path]:
    """Writes the six files `seed-review` requires, with every digest bound to disk."""
    directory.mkdir(parents=True, exist_ok=True)
    image_path = directory / "page-001.png"
    Image.new("RGB", (40, 30), "white").save(image_path)
    digest = hashlib.sha256(image_path.read_bytes()).hexdigest()

    return {
        "image": image_path,
        "packet": _write_json(
            directory / "review-packet.json",
            build_packet(
                dataset_id=dataset_id,
                digest=digest,
                decided=decided,
                elevation=elevation,
                balloons=balloons,
            ),
        ),
        "associations": _write_json(
            directory / "association-candidates.json",
            build_associations(
                dataset_id=dataset_id,
                digest=digest,
                drop_circle=drop_circle_candidate,
                elevation=elevation,
                balloons=balloons,
                association_confidences=association_confidences,
            ),
        ),
        "proposals": _write_json(
            directory / "vision-proposals.json",
            build_proposals(dataset_id=dataset_id, digest=digest, elevation=elevation),
        ),
        "manifest": _write_json(
            directory / "manifest.json",
            build_manifest(
                dataset_id=dataset_id,
                digest=digest,
                source_sha256=manifest_source_sha256 or source_sha256,
            ),
        ),
        "rectangle_request": _write_json(directory / "rectangle-request.json", build_request()),
    }
