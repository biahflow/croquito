import json
from pathlib import Path
from zipfile import ZipFile

import pytest
from ezdxf.filemanagement import readfile

from croquito_core.errors import DomainValidationError
from croquito_worker.dxf import APP_ID, AutoDecidedReadingAudit, export_scene_package
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


def test_a_auditoria_so_ganha_a_lista_nominal_quando_houve_cota_automatica(
    tmp_path: Path,
) -> None:
    """Sem auto-decisão a auditoria sai exatamente como sempre saiu; com ela, nomeada.

    A chave é acrescentada só quando existe o que listar: um `[]` fixo mudaria o conteúdo
    de todo pacote publicado por um modo que nem está ligado.
    """
    without = run_synthetic_pipeline(tmp_path / "sem")
    audit_without = json.loads(without.audit_path.read_text(encoding="utf-8"))
    assert "auto_decided_readings" not in audit_without

    scene = build_synthetic_scene()
    with_auto = export_scene_package(
        scene,
        tmp_path / "com",
        auto_decided_readings=[
            AutoDecidedReadingAudit(
                reading_id="rd_1111111111111111",
                decision_id="hd_1111111111111111",
                raw_text="25,90",
                value_si="25.90",
                unit="m",
                proposal_id="vp_1111111111111111",
                reading_confidence=0.85,
                association_confidence=0.9,
                threshold=0.6,
                score_version="1.0.0",
            ),
            # Tier de anotação (ADR-0044, D1a): entrou com UMA testemunha e SEM vínculo,
            # e o pacote diz as duas coisas — quem confere não aceita de um rótulo o que
            # aceita de uma medida, e precisa ver que nada foi preso ao elemento.
            AutoDecidedReadingAudit(
                reading_id="rd_2222222222222222",
                decision_id="hd_2222222222222222",
                raw_text="h=3,80",
                value_si="3.80",
                unit="m",
                proposal_id=None,
                reading_confidence=0.45,
                association_confidence=0.9,
                threshold=0.6,
                score_version="1.0.0",
                tier="anotacao",
                probable_proposal_id="vp_2222222222222222",
            ),
        ],
    )
    audit_with = json.loads(with_auto.audit_path.read_text(encoding="utf-8"))
    assert audit_with["status"] == "approved"
    assert audit_with["auto_decided_readings"] == [
        {
            "reading_id": "rd_1111111111111111",
            "decision_id": "hd_1111111111111111",
            "raw_text": "25,90",
            "value_si": "25.90",
            "unit": "m",
            "proposal_id": "vp_1111111111111111",
            "reading_confidence": 0.85,
            "association_confidence": 0.9,
            "threshold": 0.6,
            "score_version": "1.0.0",
            "tier": "cota",
            "probable_proposal_id": None,
        },
        {
            "reading_id": "rd_2222222222222222",
            "decision_id": "hd_2222222222222222",
            "raw_text": "h=3,80",
            "value_si": "3.80",
            "unit": "m",
            "proposal_id": None,
            "reading_confidence": 0.45,
            "association_confidence": 0.9,
            "threshold": 0.6,
            "score_version": "1.0.0",
            "tier": "anotacao",
            "probable_proposal_id": "vp_2222222222222222",
        },
    ]
    # O portão de exportação não muda: a listagem é auditoria, não permissão.
    assert audit_with["checks"] == audit_without["checks"]


def test_export_refuses_unapproved_scene(tmp_path: Path) -> None:
    scene = build_synthetic_scene()
    scene.approved = False

    with pytest.raises(DomainValidationError, match="SCENE_NOT_APPROVED"):
        export_scene_package(scene, tmp_path)
