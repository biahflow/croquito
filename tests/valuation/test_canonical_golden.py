"""O canônico da medição sintética é determinístico e está versionado.

São três goldens, e eles respondem perguntas diferentes:

- `valuation-demo.canonical.json` (M1) descreve a pasta de **uma obra**, sem consolidado
  contratual. O conteúdo comparado é montado pela fixture (catálogo sintético → medição →
  planilha), sem passar pelos artefatos em disco: o golden descreve as células, não o
  comando. Ele não é regravado quando a demonstração muda.
- `valuation-demo-m4.canonical.json` descreve a pasta consolidada que a cadeia completa
  produz — PLANILHA GERAL, RE-RA e um par BM/MEMÓRIA por obra, inclusive a obra que nasce
  do takeoff —, e esse é comparado contra o comando `demo` rodando in-process.
- `estimate-demo.canonical.json` (M8) descreve o **orçamento-base** que o comando
  `estimate-demo` publica: as três origens de preço, a proveniência de cada linha, o item
  que nenhuma fonte precificou e os totais. Ele não é planilha nenhuma — é o `estimate.json`
  em si, que é a fonte de verdade daquela cadeia.
- `estimate-workbook.canonical.json` (ADR-0038/T2) descreve a **planilha** `orcamento.xlsx`
  que o mesmo comando `estimate-demo` agora também publica: as colunas que o boletim não
  tem (FONTE, VALOR UNIT. C/ BDI), o BDI declarado uma vez e o bloco de totais em que o
  valor do BDI é a diferença entre os totais truncados. Ele não tem digest nenhum a
  canonicalizar — a planilha do orçamento nunca imprime `image_sha256`/`source_pdf_sha256`
  nem os digests da cascata, só origem e data-base por linha (ambos determinísticos na
  fixture) —, então não precisa da mesma canonicalização mínima do golden do JSON.

O golden do orçamento (JSON) passa por uma canonicalização mínima e declarada: cada digest
de FONTE vira um rótulo do papel dele (`<sha256:catalogo-emop>`, `<sha256:prancha-pdf>`…).
Os bytes de duas fontes sintéticas não se repetem entre execuções — o pymupdf grava
identificadores novos a cada `save` e o openpyxl carimba a hora nos membros do .zip —,
então fixá-los transformaria o golden num detector de relógio. O que ele fixa é a
estrutura, os valores e as RELAÇÕES: uma linha que passasse a apontar para outra fonte
mudaria de rótulo e reprovaria.
"""

from __future__ import annotations

import json
import re
from decimal import Decimal
from pathlib import Path

from croquito_valuation.canonical import canonicalize_workbook
from croquito_valuation.template import default_template
from croquito_worker.valuation.cli import EstimateDemoResult, run_estimate_demo, run_valuation_demo
from croquito_worker.valuation.synthetic import SYNTHETIC_TAKEOFF_REVIEWER
from tests.valuation.builders import build_fixture, write_fixture_workbook

GOLDEN_PATH = Path(__file__).parent / "golden" / "valuation-demo.canonical.json"
GOLDEN_M4_PATH = Path(__file__).parent / "golden" / "valuation-demo-m4.canonical.json"
GOLDEN_ESTIMATE_PATH = Path(__file__).parent / "golden" / "estimate-demo.canonical.json"
GOLDEN_ESTIMATE_WORKBOOK_PATH = (
    Path(__file__).parent / "golden" / "estimate-workbook.canonical.json"
)

_SHA256_RE = re.compile(r"[a-f0-9]{64}")


def canonical_estimate(result: EstimateDemoResult) -> dict[str, object]:
    """O `estimate.json` da demo com cada digest de fonte trocado pelo papel que ele tem.

    A troca é feita pelos digests que a própria execução produziu, então ela não pode
    "consertar" uma proveniência errada: um digest que não fosse o da fonte declarada
    sobraria no texto e a asserção final o pegaria.
    """
    labels = {
        result.estimate.image_sha256: "<sha256:prancha-imagem>",
        result.estimate.source_pdf_sha256: "<sha256:prancha-pdf>",
        **{
            catalog.source_sha256: f"<sha256:catalogo-{catalog.origin.value}>"
            for catalog in result.cascade
        },
    }
    approval = result.estimate.approval
    if approval is not None:
        # O digest assinado é o do conteúdo, que embute o do PDF — e aquele não se repete
        # entre execuções. O rótulo fixa o PAPEL; que ele confira com o conteúdo é o que o
        # teste do artefato da demo assere, não este.
        labels[approval.estimate_digest] = "<sha256:orcamento-conteudo>"
    text = result.estimate.model_dump_json()
    for digest, label in labels.items():
        text = text.replace(digest, label)
    leftover = _SHA256_RE.search(text)
    assert leftover is None, f"digest não declarado no orçamento: {leftover.group()}"
    return dict(json.loads(text))


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

    assert valuation_payload["schema_version"] == "3.0.0"
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


def test_estimate_demo_canonical_matches_the_versioned_golden(tmp_path: Path) -> None:
    result = run_estimate_demo(tmp_path / "estimate-demo")

    assert canonical_estimate(result) == json.loads(
        GOLDEN_ESTIMATE_PATH.read_text(encoding="utf-8")
    )


def test_the_estimate_demo_publishes_only_what_the_approval_authorizes(tmp_path: Path) -> None:
    """A cadeia offline do orçamento passou a fechar com assinatura, como a da medição.

    O `estimate.json` publicado é o MESMO artefato que o portão autorizou: o digest gravado
    na aprovação confere com o conteúdo, e quem assinou não é quem montou (ADR-0046).
    """
    result = run_estimate_demo(tmp_path / "estimate-demo")

    payload = json.loads(result.estimate_path.read_text(encoding="utf-8"))

    assert payload["schema_version"] == "3.0.0"
    assert payload["approval"]["estimate_digest"] == result.estimate.content_digest()
    assert payload["approval"]["decision"]["approver_role"] == "aprovador"
    assert payload["approval"]["decision"]["approver_id"] != SYNTHETIC_TAKEOFF_REVIEWER
    assert result.estimate.export_errors() == []
    assert result.workbook_path is not None, result.workbook_audit.findings


def test_the_estimate_golden_carries_the_three_price_origins_and_the_unpriced_item() -> None:
    """O que este golden existe para fixar: a fronteira do ADR-0027 em forma de dado.

    Três fontes na mesma cascata, cada linha declarando de qual veio, e o item que nenhuma
    delas precificou saindo declarado em vez de precificado por semelhança.
    """
    golden = json.loads(GOLDEN_ESTIMATE_PATH.read_text(encoding="utf-8"))

    assert [source["origin"] for source in golden["cascade"]] == ["sco", "emop", "composition"]
    # A ordem é a dos itens confirmados na prancha, não a da cascata: piso e alambrado
    # ficam no SCO, o gramado sai por composição e o mobiliário/emborrachado pela EMOP.
    assert [line["price_origin"] for line in golden["lines"]] == [
        "sco",
        "composition",
        "sco",
        "emop",
        "emop",
    ]
    # Cada linha aponta para a fonte da própria origem, pelo rótulo canonicalizado.
    for line in golden["lines"]:
        assert line["catalog_sha256"] == f"<sha256:catalogo-{line['price_origin']}>"
    # O gramado sai pela composição manual: preço somado de coeficientes, não de tabela.
    lawn = next(line for line in golden["lines"] if line["price_origin"] == "composition")
    assert lawn["unit_price"] == "28.75"
    # Preço com BDI (25%, ADR-0038) truncado por linha; o total recomputa sobre ele.
    assert lawn["unit_price_with_bdi"] == "35.93"
    assert lawn["total"] == "44355.58"
    assert len(golden["unpriced_item_ids"]) == 1
    assert golden["bdi_percent"] == "25.00"
    # Sem BDI é a mesma aritmética que o golden fixava antes do ADR-0038.
    assert golden["total_amount_without_bdi"] == "57221.26"
    assert golden["total_amount"] == "71516.83"


def _canonical_of_estimate_workbook(output_dir: Path) -> dict[str, object]:
    result = run_estimate_demo(output_dir)
    assert result.workbook_path is not None, result.workbook_audit.findings
    return canonicalize_workbook(result.workbook_path, default_template())


def test_estimate_workbook_canonical_matches_the_versioned_golden(tmp_path: Path) -> None:
    canonical = _canonical_of_estimate_workbook(tmp_path / "estimate-demo")

    golden = json.loads(GOLDEN_ESTIMATE_WORKBOOK_PATH.read_text(encoding="utf-8"))

    assert canonical == golden


def test_estimate_workbook_is_idempotent_in_logical_content(tmp_path: Path) -> None:
    first = _canonical_of_estimate_workbook(tmp_path / "estimate-demo-a")
    second = _canonical_of_estimate_workbook(tmp_path / "estimate-demo-b")

    assert first == second


def test_the_estimate_workbook_golden_carries_the_new_columns_and_the_bdi_totals() -> None:
    """O que este golden existe para fixar: as duas colunas aditivas e o bloco de totais
    em que o BDI impresso é a diferença dos truncados (ADR-0038, decisões 4 e 5)."""
    golden = json.loads(GOLDEN_ESTIMATE_WORKBOOK_PATH.read_text(encoding="utf-8"))

    sheets = {sheet["name"]: sheet for sheet in golden["sheets"]}
    assert list(sheets) == ["ORÇAMENTO"]
    cells = {cell["ref"]: cell for cell in sheets["ORÇAMENTO"]["cells"]}

    assert cells["C6"]["value"] == "FONTE"
    assert cells["G6"]["value"] == "VALOR UNIT. C/ BDI"
    # FONTE combina origem e data-base numa célula só; nenhum digest aparece na planilha.
    assert cells["C7"]["value"] == "SCO 2026-01"
    assert cells["A4"]["value"] == "BDI"
    assert cells["C4"]["value"] == "25.00%"
    # bloco de totais: sem BDI, BDI (diferença dos truncados) e total geral.
    total_without_bdi = next(
        cell for cell in sheets["ORÇAMENTO"]["cells"] if cell["value"] == "TOTAL SEM BDI"
    )
    total_row = int(str(total_without_bdi["ref"])[1:])
    without_bdi_cell = cells[f"I{total_row}"]
    bdi_cell = cells[f"I{total_row + 1}"]
    total_cell = cells[f"I{total_row + 2}"]
    assert bdi_cell["formula"] == f"=I{total_row + 2}-I{total_row}"
    assert Decimal(total_cell["value"]) - Decimal(without_bdi_cell["value"]) == Decimal(
        bdi_cell["value"]
    )
    unpriced_label = next(
        cell
        for cell in sheets["ORÇAMENTO"]["cells"]
        if cell["value"] == "ITENS SEM PREÇO NA CASCATA"
    )
    assert unpriced_label["ref"] == "A17"


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
