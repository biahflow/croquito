"""Geração, reabertura e auditoria de pacotes DXF."""

from __future__ import annotations

import csv
import hashlib
import json
import math
import os
import tempfile
import zipfile
from collections.abc import Sequence
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from ezdxf import bbox, recover, units
from ezdxf.addons.drawing import matplotlib as ezdxf_matplotlib
from ezdxf.document import Drawing
from ezdxf.entities.dxfgfx import DXFGraphic
from ezdxf.entities.lwpolyline import LWPolyline
from ezdxf.filemanagement import new as new_document
from ezdxf.layouts.layout import Modelspace
from shapely.geometry import Polygon

from croquito_core.errors import DomainValidationError
from croquito_core.models import (
    ArcGeometry,
    CircleGeometry,
    DiameterDimensionGeometry,
    DimensionGeometry,
    Entity,
    LayerName,
    LineGeometry,
    PolylineGeometry,
    SceneRevision,
    SplineGeometry,
    TextGeometry,
)
from croquito_worker.element_labels import dimension_text_height

APP_ID = "CROQUITO"
DXF_VERSION = "R2018"

HATCH_PATTERN = "ANSI31"
HATCH_PATTERN_BASE_SPACING = 3.175
"""Espaçamento do ANSI31 em unidades de desenho na escala 1; serve de base para escalar."""

PREVIEW_LONG_SIDE_INCHES = 15.0
PREVIEW_MIN_SIDE_INCHES = 5.0

DETAIL_TAG_PREFIX = "detail:"
"""Marca de pertencimento a grupo de detalhe em `provenance.source_ids`."""

QUANTITY_EXCLUDED_SUMMARY_CODES = frozenset({"DETAIL_FRAME", "DETAIL_SKETCH_AS_DRAWN"})
"""Moldura é apresentação e sketch não tem escala honesta: quantidade no CSV mentiria."""


def _is_detail_entity(entity: Entity) -> bool:
    return entity.provenance is not None and any(
        source_id.startswith(DETAIL_TAG_PREFIX) for source_id in entity.provenance.source_ids
    )


LAYER_STYLES: dict[LayerName, tuple[int, int]] = {
    LayerName.CONTORNO: (7, 35),
    LayerName.CAMPO: (2, 15),
    LayerName.QUADRA: (3, 15),
    LayerName.MURO: (4, 50),
    LayerName.ALAMBRADO: (7, 35),
    LayerName.PORTAO: (1, 35),
    LayerName.PATAMAR: (5, 25),
    LayerName.EQUIPAMENTOS: (6, 25),
    LayerName.COTAS: (1, 15),
    LayerName.TEXTOS: (7, 15),
    LayerName.DETALHES: (8, 13),
    LayerName.APROXIMADO: (30, 25),
    LayerName.REVISAO: (1, 25),
}


@dataclass(frozen=True)
class DxfAuditReport:
    status: str
    scene_id: str
    revision_version: int
    generated_at: str
    dxf_sha256: str
    entity_count: int
    extents: dict[str, list[float]] | None
    checks: dict[str, bool]
    errors: list[str]
    warnings: list[str]


@dataclass(frozen=True)
class AutoDecidedReadingAudit:
    """Uma cota que entrou no desenho sem toque humano, nomeada na auditoria do pacote.

    A listagem é nominal de propósito (ADR-0041, D6): quem abrir o pacote precisa saber
    exatamente quais medidas foram confirmadas por máquina, com que confiança e sob que
    corte — não um contador agregado. O portão `SceneRevision.export_errors()` não muda:
    o que muda é quem pode ter autoria de uma decisão, nunca o que uma cena precisa ter
    para exportar.
    """

    reading_id: str
    decision_id: str
    raw_text: str
    value_si: str
    unit: str
    # O elemento a que a cota ficou VINCULADA. Nulo na anotação automática, que entra
    # confirmada sem elemento — é a ausência do vínculo que a mantém fora de qualquer
    # restrição de geometria.
    proposal_id: str | None
    reading_confidence: float
    # Confiança do candidato citado: do vínculo, no tier de cota; do elemento provável,
    # no de anotação. Nula quando a leitura não tinha candidato nenhum.
    association_confidence: float | None
    threshold: float
    score_version: str
    # Por qual regra ela entrou (ADR-0044): `cota` exigiu duas testemunhas e vinculou o
    # elemento; `anotacao` não exigiu corte nem vinculou nada. Quem confere o pacote
    # precisa distinguir os dois: o que se aceita de um rótulo não é o que se aceita de
    # uma medida.
    tier: str = "cota"
    # Observação do tier de anotação: o elemento que o ranking teria escolhido, para
    # instruir quem for prender o texto no traçado. Nunca é vínculo.
    probable_proposal_id: str | None = None


@dataclass(frozen=True)
class ExportResult:
    output_dir: Path
    dxf_path: Path
    preview_path: Path
    audit_path: Path
    quantities_path: Path
    assumptions_path: Path
    package_path: Path
    audit: DxfAuditReport


def _atomic_write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.")
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary_path, path)
    finally:
        if temporary_path.exists():
            temporary_path.unlink()


def _attach_provenance(dxf_entity: DXFGraphic, entity: Entity, scene: SceneRevision) -> None:
    summary_code = entity.provenance.summary_code if entity.provenance else "NO_PROVENANCE"
    dxf_entity.set_xdata(
        APP_ID,
        [
            (1000, str(entity.id)),
            (1000, str(scene.id)),
            (1000, entity.precision.value),
            (1000, summary_code),
        ],
    )


def _scene_extent_diagonal(scene: SceneRevision) -> float:
    xs: list[float] = []
    ys: list[float] = []
    for entity in scene.entities:
        if not entity.export:
            continue
        if _is_detail_entity(entity):
            # A tipografia da prancha segue a planta — o traçado calcula as caixas de
            # colisão com essa premissa, e o export precisa da MESMA referência, senão
            # o texto das DIMENSION sai maior do que o planejado.
            continue
        geometry = entity.geometry
        if isinstance(geometry, LineGeometry):
            xs += [geometry.start.x, geometry.end.x]
            ys += [geometry.start.y, geometry.end.y]
        elif isinstance(geometry, PolylineGeometry):
            xs += [point.x for point in geometry.points]
            ys += [point.y for point in geometry.points]
        elif isinstance(geometry, CircleGeometry | ArcGeometry):
            xs += [geometry.center.x - geometry.radius, geometry.center.x + geometry.radius]
            ys += [geometry.center.y - geometry.radius, geometry.center.y + geometry.radius]
        elif isinstance(geometry, SplineGeometry):
            xs += [point.x for point in geometry.fit_points]
            ys += [point.y for point in geometry.fit_points]
    if not xs or not ys:
        return 0.0
    return math.hypot(max(xs) - min(xs), max(ys) - min(ys))


def _dimension_text_height(scene: SceneRevision) -> float:
    return dimension_text_height(_scene_extent_diagonal(scene))


def _add_hatch(
    modelspace: Modelspace, entity: Entity, scene: SceneRevision, dxf_entity: DXFGraphic
) -> None:
    """Hachura declarada pela folha, presa ao contorno e com o mesmo rastro XDATA."""
    geometry = entity.geometry
    hatch = modelspace.add_hatch(dxfattribs={"layer": entity.layer.value})
    if isinstance(geometry, PolylineGeometry):
        points = [(point.x, point.y) for point in geometry.points]
        hatch.paths.add_polyline_path(points, is_closed=True)
        xs = [point.x for point in geometry.points]
        ys = [point.y for point in geometry.points]
        region_diagonal = math.hypot(max(xs) - min(xs), max(ys) - min(ys))
    elif isinstance(geometry, CircleGeometry):
        edge_path = hatch.paths.add_edge_path()
        edge_path.add_arc((geometry.center.x, geometry.center.y), geometry.radius, 0, 360)
        region_diagonal = geometry.radius * 2
    else:  # pragma: no cover - o contrato só permite fill em região fechada
        raise TypeError("fill exige polilinha fechada ou círculo")
    spacing = max(0.05, region_diagonal * 0.04)
    scale = min(10.0, max(0.01, spacing / HATCH_PATTERN_BASE_SPACING))
    hatch.set_pattern_fill(HATCH_PATTERN, scale=scale)
    _attach_provenance(hatch, entity, scene)


def _add_entity(
    modelspace: Modelspace,
    entity: Entity,
    scene: SceneRevision,
    *,
    dimension_text_height: float,
) -> DXFGraphic:
    geometry = entity.geometry
    attributes: dict[str, Any] = {"layer": entity.layer.value}
    dxf_entity: DXFGraphic

    if isinstance(geometry, LineGeometry):
        dxf_entity = modelspace.add_line(
            (geometry.start.x, geometry.start.y),
            (geometry.end.x, geometry.end.y),
            dxfattribs=attributes,
        )
    elif isinstance(geometry, PolylineGeometry):
        dxf_entity = modelspace.add_lwpolyline(
            [(point.x, point.y) for point in geometry.points],
            close=geometry.closed,
            dxfattribs=attributes,
        )
    elif isinstance(geometry, CircleGeometry):
        dxf_entity = modelspace.add_circle(
            (geometry.center.x, geometry.center.y),
            geometry.radius,
            dxfattribs=attributes,
        )
    elif isinstance(geometry, ArcGeometry):
        dxf_entity = modelspace.add_arc(
            (geometry.center.x, geometry.center.y),
            geometry.radius,
            math.degrees(geometry.start_angle),
            math.degrees(geometry.end_angle),
            dxfattribs=attributes,
        )
    elif isinstance(geometry, SplineGeometry):
        dxf_entity = modelspace.add_spline(
            fit_points=[(point.x, point.y) for point in geometry.fit_points],
            dxfattribs=attributes,
        )
    elif isinstance(geometry, TextGeometry):
        attributes.update(
            {
                "height": geometry.height,
                "rotation": math.degrees(geometry.rotation),
            }
        )
        text = modelspace.add_text(geometry.text, dxfattribs=attributes)
        text.set_placement((geometry.insertion.x, geometry.insertion.y))
        dxf_entity = text
    elif isinstance(geometry, DimensionGeometry):
        dimension_angle = math.degrees(
            math.atan2(
                geometry.second.y - geometry.first.y,
                geometry.second.x - geometry.first.x,
            )
        )
        # Normalizado para (-90, 90]: a projeção medida é a mesma e o texto da cota
        # nunca sai de cabeça para baixo — vertical fica em +90, lendo de baixo para cima.
        dimension_angle = dimension_angle % 180.0
        if dimension_angle > 90.0:
            dimension_angle -= 180.0
        text_height = dimension_text_height
        override = modelspace.add_linear_dim(
            base=(geometry.base.x, geometry.base.y),
            p1=(geometry.first.x, geometry.first.y),
            p2=(geometry.second.x, geometry.second.y),
            angle=dimension_angle,
            dimstyle="EZDXF",
            override={
                "dimtad": 1,
                "dimtxt": text_height,
                "dimasz": round(text_height * 0.85, 4),
                "dimexo": round(text_height * 0.3, 4),
                "dimexe": round(text_height * 0.45, 4),
                "dimgap": round(text_height * 0.25, 4),
            },
            dxfattribs=attributes,
        )
        if geometry.text_override is not None:
            override.dimension.dxf.text = geometry.text_override
        override.render()
        dxf_entity = override.dimension
    elif isinstance(geometry, DiameterDimensionGeometry):
        # DIMENSION diametral de verdade (não um texto solto): a linha de cota atravessa o
        # círculo no eixo do ângulo declarado, que mira a evidência da leitura na folha.
        # O meio giro é do renderizador, não da geometria: em `add_diameter_dim` o `angle`
        # aponta a ponta OPOSTA à do texto e um diâmetro é simétrico — sem ele o "⌀ 5,00"
        # pousaria do outro lado do círculo, longe de onde o croqui o escreveu.
        text_height = dimension_text_height
        diameter = modelspace.add_diameter_dim(
            center=(geometry.center.x, geometry.center.y),
            radius=geometry.radius,
            angle=math.degrees(geometry.angle) + 180.0,
            text=geometry.text_override or "<>",
            dimstyle="EZ_RADIUS",
            override={
                "dimtad": 1,
                "dimtxt": text_height,
                "dimasz": round(text_height * 0.85, 4),
                "dimgap": round(text_height * 0.25, 4),
            },
            dxfattribs=attributes,
        )
        diameter.render()
        dxf_entity = diameter.dimension
    else:  # pragma: no cover - união discriminada torna o ramo inalcançável
        raise TypeError(f"Geometria não suportada: {type(geometry).__name__}")

    _attach_provenance(dxf_entity, entity, scene)
    if entity.fill == "hatch":
        _add_hatch(modelspace, entity, scene, dxf_entity)
    return dxf_entity


def build_document(scene: SceneRevision) -> Drawing:
    scene.ensure_exportable()
    document = new_document(DXF_VERSION, setup=True)
    document.units = units.M
    document.header["$INSUNITS"] = units.M
    document.header["$MEASUREMENT"] = 1
    if not document.appids.has_entry(APP_ID):
        document.appids.add(APP_ID)

    for layer, (color, lineweight) in LAYER_STYLES.items():
        if document.layers.has_entry(layer.value):
            layer_entry = document.layers.get(layer.value)
            layer_entry.dxf.color = color
            layer_entry.dxf.lineweight = lineweight
        else:
            document.layers.add(layer.value, color=color, lineweight=lineweight)

    modelspace = document.modelspace()
    text_height = _dimension_text_height(scene)
    for entity in scene.entities:
        if entity.export:
            _add_entity(modelspace, entity, scene, dimension_text_height=text_height)
    return document


def _save_document_atomic(document: Drawing, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        dir=path.parent,
        prefix=f".{path.stem}.",
        suffix=".dxf",
    )
    os.close(descriptor)
    temporary_path = Path(temporary_name)
    try:
        document.saveas(temporary_path)
        os.replace(temporary_path, path)
    finally:
        if temporary_path.exists():
            temporary_path.unlink()


def _document_extents(document: Drawing) -> dict[str, list[float]] | None:
    bounding_box = bbox.extents(document.modelspace())
    if not bounding_box.has_data:
        return None
    minimum = [float(bounding_box.extmin.x), float(bounding_box.extmin.y)]
    maximum = [float(bounding_box.extmax.x), float(bounding_box.extmax.y)]
    if not all(math.isfinite(value) for value in [*minimum, *maximum]):
        return None
    return {"min": minimum, "max": maximum}


def audit_dxf(path: Path, scene: SceneRevision) -> tuple[Drawing, DxfAuditReport]:
    document, auditor = recover.readfile(path)
    errors = [str(error) for error in auditor.errors]
    warnings = [str(fix) for fix in auditor.fixes]
    modelspace = document.modelspace()
    entities = list(modelspace)
    extents = _document_extents(document)

    expected_entity_count = sum(
        1 + (1 if entity.fill != "none" else 0) for entity in scene.entities if entity.export
    )
    layer_names = {layer.dxf.name for layer in document.layers}
    used_layer_names = {entity.layer.value for entity in scene.entities if entity.export}
    xdata_complete = all(entity.has_xdata(APP_ID) for entity in entities)
    topology_valid = True
    for entity in entities:
        if not isinstance(entity, LWPolyline) or not entity.closed:
            continue
        polygon = Polygon([(point[0], point[1]) for point in entity.get_points("xy")])
        if not polygon.is_valid or polygon.area <= 0:
            topology_valid = False
            errors.append(f"INVALID_CLOSED_POLYLINE:{entity.dxf.handle}")

    checks = {
        "reopened": True,
        "ezdxf_auditor_clean": len(auditor.errors) == 0,
        "units_are_metres": document.header.get("$INSUNITS") == units.M,
        "layers_present": used_layer_names <= layer_names,
        "entity_count_matches": len(entities) == expected_entity_count,
        "xdata_complete": xdata_complete,
        "finite_extents": extents is not None,
        "topology_valid": topology_valid,
        "scene_still_exportable": len(scene.export_errors()) == 0,
    }
    if not all(checks.values()):
        errors.extend(name.upper() for name, passed in checks.items() if not passed)

    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    report = DxfAuditReport(
        status="approved" if not errors else "rejected",
        scene_id=str(scene.id),
        revision_version=scene.version,
        generated_at=datetime.now(UTC).isoformat(),
        dxf_sha256=digest,
        entity_count=len(entities),
        extents=extents,
        checks=checks,
        errors=sorted(set(errors)),
        warnings=warnings,
    )
    return document, report


def _render_preview(document: Drawing, preview_path: Path) -> None:
    """PNG do próprio DXF, com folha e densidade proporcionais à extensão da cena.

    O `qsave` cru deixava o matplotlib escolher figura e limites: desenho grande saía com
    menos pixels por metro que desenho pequeno, e texto encostava na borda. Aqui a folha
    acompanha a proporção do desenho e o DPI mira uma largura de pixels constante.
    """
    extents = _document_extents(document)
    size_inches: tuple[float, float] | None = None
    dpi = 180
    if extents is not None:
        width_m = extents["max"][0] - extents["min"][0]
        height_m = extents["max"][1] - extents["min"][1]
        if width_m > 0 and height_m > 0:
            longest = max(width_m, height_m)
            width_in = max(PREVIEW_MIN_SIDE_INCHES, PREVIEW_LONG_SIDE_INCHES * width_m / longest)
            height_in = max(PREVIEW_MIN_SIDE_INCHES, PREVIEW_LONG_SIDE_INCHES * height_m / longest)
            size_inches = (width_in, height_in)
            dpi = int(min(300, max(140, 3200 / max(width_in, height_in))))
    ezdxf_matplotlib.qsave(
        document.modelspace(),
        preview_path,
        bg="#ffffff",
        fg="#15191f",
        dpi=dpi,
        size_inches=size_inches,
    )


def _write_quantities(scene: SceneRevision, path: Path) -> None:
    descriptor, temporary_name = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.")
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="") as stream:
            writer = csv.DictWriter(
                stream,
                fieldnames=[
                    "entity_id",
                    "layer",
                    "kind",
                    "precision",
                    "length_m",
                    "perimeter_m",
                    "area_m2",
                ],
            )
            writer.writeheader()
            for entity in scene.entities:
                if not entity.export:
                    continue
                if entity.layer in {LayerName.TEXTOS, LayerName.COTAS}:
                    # Balão, rótulo, legenda, cota e risco de chamada são anotação: um
                    # traço de leader com comprimento no CSV mentiria quantidade física.
                    continue
                if (
                    entity.provenance is not None
                    and entity.provenance.summary_code in QUANTITY_EXCLUDED_SUMMARY_CODES
                ):
                    # Detalhe resolvido (escala verdadeira) continua entrando; moldura e
                    # sketch sem escala ficam fora — quantidade deles mentiria.
                    continue
                length = ""
                perimeter = ""
                area = ""
                geometry = entity.geometry
                if isinstance(geometry, LineGeometry):
                    delta_x = geometry.end.x - geometry.start.x
                    delta_y = geometry.end.y - geometry.start.y
                    length = f"{math.hypot(delta_x, delta_y):.6f}"
                elif isinstance(geometry, PolylineGeometry) and geometry.closed:
                    polygon = Polygon([(point.x, point.y) for point in geometry.points])
                    perimeter = f"{polygon.length:.6f}"
                    area = f"{polygon.area:.6f}"
                elif isinstance(geometry, CircleGeometry):
                    perimeter = f"{2 * math.pi * geometry.radius:.6f}"
                    area = f"{math.pi * geometry.radius**2:.6f}"
                writer.writerow(
                    {
                        "entity_id": str(entity.id),
                        "layer": entity.layer.value,
                        "kind": entity.kind.value,
                        "precision": entity.precision.value,
                        "length_m": length,
                        "perimeter_m": perimeter,
                        "area_m2": area,
                    }
                )
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary_path, path)
    finally:
        if temporary_path.exists():
            temporary_path.unlink()


def _write_package(path: Path, files: list[Path]) -> None:
    descriptor, temporary_name = tempfile.mkstemp(
        dir=path.parent,
        prefix=f".{path.stem}.",
        suffix=".zip",
    )
    os.close(descriptor)
    temporary_path = Path(temporary_name)
    try:
        with zipfile.ZipFile(temporary_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for file in files:
                archive.write(file, arcname=file.name)
        os.replace(temporary_path, path)
    finally:
        if temporary_path.exists():
            temporary_path.unlink()


def export_scene_package(
    scene: SceneRevision,
    output_dir: Path,
    *,
    package_stem: str = "croquito",
    extra_package_files: list[Path] | None = None,
    auto_decided_readings: Sequence[AutoDecidedReadingAudit] = (),
) -> ExportResult:
    """Publica um pacote somente depois de reabrir e auditar o DXF temporário.

    `auto_decided_readings` é a lista nominal das cotas que entraram sem toque humano
    (F-029). A chave só aparece em `auditoria.json` quando existe alguma: com o modo
    automático desligado — o padrão — o arquivo sai byte a byte como sempre saiu.
    """
    scene.ensure_exportable()
    output_dir.mkdir(parents=True, exist_ok=True)
    dxf_path = output_dir / "desenho.dxf"
    preview_path = output_dir / "preview.png"
    audit_path = output_dir / "auditoria.json"
    quantities_path = output_dir / "quantitativos.csv"
    assumptions_path = output_dir / "hipoteses.json"
    package_path = output_dir / f"{package_stem}.zip"

    document = build_document(scene)
    _save_document_atomic(document, dxf_path)
    reopened_document, report = audit_dxf(dxf_path, scene)
    audit_payload: dict[str, Any] = asdict(report)
    if auto_decided_readings:
        audit_payload["auto_decided_readings"] = [
            asdict(reading) for reading in auto_decided_readings
        ]
    _atomic_write_text(
        audit_path,
        f"{json.dumps(audit_payload, ensure_ascii=False, indent=2, sort_keys=True)}\n",
    )
    if report.status != "approved":
        raise DomainValidationError(report.errors)

    _render_preview(reopened_document, preview_path)
    _write_quantities(scene, quantities_path)
    assumptions = {
        "scene_id": str(scene.id),
        "accepted_approximations": sorted(str(item) for item in scene.accepted_approximation_ids),
        "issues": [issue.model_dump(mode="json") for issue in scene.issues],
        "policy": "Nenhuma aproximação é publicada sem aceite explícito.",
    }
    _atomic_write_text(
        assumptions_path,
        f"{json.dumps(assumptions, ensure_ascii=False, indent=2, sort_keys=True)}\n",
    )
    package_files = [dxf_path, preview_path, audit_path, quantities_path, assumptions_path]
    if extra_package_files:
        known_names = {file.name for file in package_files}
        for extra_file in extra_package_files:
            if not extra_file.is_file():
                raise ValueError(f"arquivo adicional inexistente: {extra_file}")
            if extra_file.name in known_names:
                raise ValueError(f"nome duplicado no pacote: {extra_file.name}")
            known_names.add(extra_file.name)
            package_files.append(extra_file)
    _write_package(package_path, package_files)
    return ExportResult(
        output_dir=output_dir,
        dxf_path=dxf_path,
        preview_path=preview_path,
        audit_path=audit_path,
        quantities_path=quantities_path,
        assumptions_path=assumptions_path,
        package_path=package_path,
        audit=report,
    )
