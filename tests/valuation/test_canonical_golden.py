"""O canônico da medição sintética é determinístico e está versionado.

São dois goldens, e eles respondem perguntas diferentes:

- `valuation-demo.canonical.json` (M1) descreve a pasta de **uma obra**, sem consolidado
  contratual. O conteúdo comparado é montado pela fixture (catálogo sintético → medição →
  planilha), sem passar pelos artefatos em disco: o golden descreve as células, não o
  comando. Ele não é regravado quando a demonstração muda.
- `valuation-demo-m4.canonical.json` descreve a pasta consolidada que a cadeia completa
  produz — PLANILHA GERAL, RE-RA e um par BM/MEMÓRIA por obra, inclusive a obra que nasce
  do takeoff —, e esse é comparado contra o comando `demo` rodando in-process.
"""

from __future__ import annotations

import json
from pathlib import Path

from croquitodxf_valuation.canonical import canonicalize_workbook
from croquitodxf_worker.valuation.cli import run_valuation_demo
from tests.valuation.builders import build_fixture, write_fixture_workbook

GOLDEN_PATH = Path(__file__).parent / "golden" / "valuation-demo.canonical.json"
GOLDEN_M4_PATH = Path(__file__).parent / "golden" / "valuation-demo-m4.canonical.json"


def _canonical_of_fixture(output_dir: Path) -> dict[str, object]:
    fixture = build_fixture(output_dir)
    workbook_path = output_dir / "medicao.xlsx"
    report = write_fixture_workbook(fixture, workbook_path)
    assert report.pinned_cells
    return canonicalize_workbook(workbook_path, fixture.template)


def test_synthetic_canonical_matches_the_versioned_golden(tmp_path: Path) -> None:
    canonical = _canonical_of_fixture(tmp_path / "medicao")

    golden = json.loads(GOLDEN_PATH.read_text(encoding="utf-8"))

    assert canonical == golden


def test_synthetic_workbook_is_idempotent_in_logical_content(tmp_path: Path) -> None:
    first = _canonical_of_fixture(tmp_path / "medicao")
    second = _canonical_of_fixture(tmp_path / "medicao")

    assert first == second


def test_demo_writes_the_six_artifacts_of_the_consolidated_chain(tmp_path: Path) -> None:
    result = run_valuation_demo(tmp_path / "demo")

    assert result.previous_path.is_file()
    assert result.catalog_path.is_file()
    assert result.contract_path.is_file()
    assert result.workbook_path.is_file()
    assert result.valuation_path.is_file()
    assert result.audit_path.is_file()

    valuation_payload = json.loads(result.valuation_path.read_text(encoding="utf-8"))
    audit_payload = json.loads(result.audit_path.read_text(encoding="utf-8"))
    contract_payload = json.loads(result.contract_path.read_text(encoding="utf-8"))

    assert valuation_payload["schema_version"] == "2.0.0"
    assert valuation_payload["period_number"] == contract_payload["period_numbers"][-1] + 1
    assert valuation_payload["approval"]["valuation_digest"] == result.valuation.content_digest()
    assert audit_payload["schema_version"] == "2.0.0"
    assert audit_payload["status"] == "ok"
    assert audit_payload["findings"] == []
    assert audit_payload["workbook_sha256"] == result.write_report.workbook_sha256
    assert audit_payload["general_sheet"] == "PLANILHA GERAL"
    assert audit_payload["amendment_sheet"] == "MAPÃO - PREFEITURA"
    assert audit_payload["total_amount"] == "38859.46"
    assert [worksite["worksite_key"] for worksite in audit_payload["worksites"]] == [
        "praca-sintetica-norte",
        "praca-sintetica-sul",
        "praca-sintetica-leste",
        "praca-sintetica-oeste",
    ]
    # A medição do período fecha com o consolidado que ela mesma vai gerar.
    assert result.valuation.export_errors(result.contract) == []


def test_demo_canonical_matches_the_versioned_m4_golden(tmp_path: Path) -> None:
    """O golden do M2 foi substituído por este, e nada do M2 deixou de ser fixado.

    O golden do M2 fixava a saída do comando `demo`, e o demo do M4 estende os dados
    sintéticos do contrato — a PLANILHA GERAL gerada muda de qualquer forma, porque o
    contrato passou a contratar os códigos que a legenda da prancha mede. Os
    comportamentos que o golden do M2 provava (pares históricos copiados literais, RE-RA
    carregada adiante, acumulado e saldo como fórmulas vivas) continuam fixados aqui, nas
    mesmas células.
    """
    result = run_valuation_demo(tmp_path / "demo")

    canonical = canonicalize_workbook(result.workbook_path, result.template)

    assert canonical == json.loads(GOLDEN_M4_PATH.read_text(encoding="utf-8"))


def test_the_m4_golden_carries_the_consolidation_evidence() -> None:
    golden = json.loads(GOLDEN_M4_PATH.read_text(encoding="utf-8"))

    sheets = {sheet["name"]: sheet for sheet in golden["sheets"]}
    assert list(sheets) == [
        "PLANILHA GERAL",
        "MAPÃO - PREFEITURA",
        "BM PRACA SINTETICA NORTE",
        "MEMÓRIA PRACA SINTETICA NORTE",
        "BM PRACA SINTETICA SUL",
        "MEMÓRIA PRACA SINTETICA SUL",
        "BM PRACA SINTETICA LESTE",
        "MEMÓRIA PRACA SINTETICA LESTE",
        "BM PRACA SINTETICA OESTE",
        "MEMÓRIA PRACA SINTETICA OESTE",
    ]
    general = {cell["ref"]: cell for cell in sheets["PLANILHA GERAL"]["cells"]}
    # O mesmo código medido em duas obras (2,00 + 3,00) vira uma linha só do consolidado,
    # e o valor dela é TRUNC da soma: 446,50, sem deriva contra a soma dos boletins.
    assert general["M8"]["value"] == "5.00"
    assert general["N8"]["formula"] == "=TRUNC(M8*G8,2)"
    assert general["N8"]["value"] == "446.50"
    # Acumulado soma células alternadas (quinta forma) e o saldo é diferença viva (sexta).
    assert general["O8"]["formula"] == "=SUM(I8,K8,M8)"
    assert general["O8"]["value"] == "19.00"
    assert general["Q8"]["formula"] == "=H8-O8"
    assert general["Q8"]["value"] == "16.00"
    # A RE-RA é carregada adiante como leitura preservada, não recriada aqui.
    amendment = {cell["ref"]: cell for cell in sheets["MAPÃO - PREFEITURA"]["cells"]}
    assert amendment["I4"]["value"] == "1ª RE-RA"
    assert amendment["I5"]["value"] == "5.00"


def test_golden_carries_the_truncation_evidence() -> None:
    golden = json.loads(GOLDEN_PATH.read_text(encoding="utf-8"))

    sheets = {sheet["name"]: sheet for sheet in golden["sheets"]}
    bulletin = sheets["BM PRACA SINTETICA NORTE"]
    values = {cell["ref"]: cell for cell in bulletin["cells"]}

    # 1,15 x 10,30 vale 11,84 truncado; arredondado seria 11,85.
    assert values["G13"]["value"] == "11.84"
    assert values["G13"]["formula"] == "=TRUNC(F13*E13,2)"
    # Célula fixada: o produto em ponto flutuante cairia para 4352,51.
    assert values["G11"]["value"] == "4352.52"
    assert values["G11"]["kind"] == "number"
    assert values["G16"]["value"] == "59074.11"
    assert values["G16"]["formula"] == "=SUM(G8:G15)"
