from pathlib import Path
from zipfile import ZipFile

import pytest
from ezdxf.filemanagement import readfile

from croquito_core.errors import DomainValidationError
from croquito_worker.dxf import APP_ID, export_scene_package
from croquito_worker.pipeline import run_synthetic_pipeline
from croquito_worker.synthetic import build_synthetic_scene


def test_synthetic_pipeline_creates_audited_package(tmp_path: Path) -> None:
    result = run_synthetic_pipeline(tmp_path)

    assert result.audit.status == "approved"
    assert result.audit.errors == []
    assert all(result.audit.checks.values())
    assert result.dxf_path.is_file()
    assert result.preview_path.is_file()
    assert result.preview_path.stat().st_size > 0

    document = readfile(result.dxf_path)
    assert document.header["$INSUNITS"] == 6
    assert all(entity.has_xdata(APP_ID) for entity in document.modelspace())
    dimensions = list(document.modelspace().query("DIMENSION"))
    assert [dimension.dxf.angle for dimension in dimensions] == [0.0, 90.0]

    with ZipFile(result.package_path) as archive:
        assert set(archive.namelist()) == {
            "desenho.dxf",
            "preview.png",
            "auditoria.json",
            "quantitativos.csv",
            "hipoteses.json",
        }


def test_export_refuses_unapproved_scene(tmp_path: Path) -> None:
    scene = build_synthetic_scene()
    scene.approved = False

    with pytest.raises(DomainValidationError, match="SCENE_NOT_APPROVED"):
        export_scene_package(scene, tmp_path)
