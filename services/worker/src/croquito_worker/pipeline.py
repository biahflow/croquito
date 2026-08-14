"""Orquestração local do primeiro vertical slice."""

from __future__ import annotations

import json
from pathlib import Path

from croquito_worker.dxf import ExportResult, export_scene_package
from croquito_worker.synthetic import build_synthetic_scene, render_synthetic_input


def run_synthetic_pipeline(output_dir: Path) -> ExportResult:
    """Gera entrada, cena, DXF, auditoria e pacote reprodutíveis localmente."""
    output_dir.mkdir(parents=True, exist_ok=True)
    scene = build_synthetic_scene()
    render_synthetic_input(output_dir / "entrada-sintetica.png")
    serialized_scene = json.dumps(
        scene.model_dump(mode="json"),
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
    )
    (output_dir / "scene.json").write_text(
        f"{serialized_scene}\n",
        encoding="utf-8",
    )
    return export_scene_package(scene, output_dir, package_stem="demonstracao-sintetica")
