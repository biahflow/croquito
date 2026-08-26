"""Servidor local de homologação da medição: o contrato de rotas que a UI vai consumir.

Os testes rodam in-process (`TestClient`) sobre um diretório de rodada produzido pelos
comandos **reais** do CLI (`import-workbook` + `extract-legend`) — é assim que o servidor
vai ser usado, e é o que prova que ele lê os artefatos que o CLI grava, com os nomes
padrão, sem atalho em memória.

Como no resto da medição, o que importa numa recusa não é a mensagem: é o que **não**
mudou no diretório. Cada teste de recusa fotografa os digests de todos os arquivos da
rodada antes e depois e exige que nada tenha se movido.

O bloco de upload e extração paga também roda **sem rede**: a fábrica do braço
(`local_server._build_extraction_adapter`) é o seam trocado por um adapter fixture, e as
variáveis de gasto do servidor entram e saem por `monkeypatch` para que o freio do teto
seja exercitado de verdade nos dois sentidos. O PDF de prancha é gerado no próprio teste —
nenhum documento de cliente entra no repositório.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import threading
import time
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass
from dataclasses import field as dataclass_field
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Final

import pymupdf
import pytest
from fastapi.testclient import TestClient

from croquito_valuation.assignment import (
    LLM_RERANK_SUFFIX,
    SCO_HYBRID_SUGGESTER_VERSION,
    SCO_LEXICAL_IDF_SUGGESTER_VERSION,
    CodeSuggestionSet,
    SuggestionRefinement,
)
from croquito_valuation.calc_matrix import (
    CalcContribution,
    CalcMatrix,
    ServiceContributions,
)
from croquito_valuation.models import (
    CalcOperand,
    CalcRecipe,
    ContributionBasis,
    PriceCatalog,
    PriceCatalogEntry,
)
from croquito_valuation.takeoff import load_takeoff_packet
from croquito_worker.providers import (
    EmbeddingsExecution,
    FixtureProviderAdapter,
    LegendExtractionOutput,
    LegendRowOutput,
    NormalizedBox,
    PromptTask,
    ProviderAdapter,
    ProviderExecution,
    ProviderExecutionError,
    ProviderFailureCode,
    ProviderName,
    ProviderRequest,
    ProviderUsage,
)
from croquito_worker.valuation import local_server
from croquito_worker.valuation.cli import (
    AMENDMENT_DOSSIER_FILENAME,
    CALC_MATRIX_FILENAME,
    CALC_PLAN_FILENAME,
    CATALOG_FILENAME,
    CODE_ASSIGNMENTS_FILENAME,
    CODE_SUGGESTIONS_FILENAME,
    TAKEOFF_OVERLAY_FILENAME,
    TAKEOFF_PACKET_FILENAME,
    TAKEOFF_REGISTRATION_REPORT_FILENAME,
    VALUATION_FILENAME,
)
from croquito_worker.valuation.cli import main as cli_main
from croquito_worker.valuation.legend_extraction import run_legend_extraction
from croquito_worker.valuation.local_server import (
    CATALOG_INDEX_NOTES,
    CATALOG_NOTES,
    EXTRACTION_LINEAGE_FILENAME,
    PLATE_MANIFEST_FILENAME,
    PLATE_PDF_FILENAME,
    create_local_app,
    install_round_catalog,
    install_round_catalog_index,
)
from croquito_worker.valuation.plate import PLATE_IMAGE_FILENAME
from croquito_worker.valuation.sco_matching import (
    CATALOG_INDEX_FILENAME,
    QUERY_CACHE_FILENAME,
    index_document,
)
from croquito_worker.valuation.sco_matching_fixtures import (
    FIXTURE_EMBEDDINGS_DIMS,
    FIXTURE_EMBEDDINGS_MODEL,
    fixture_catalog_index,
    fixture_vector,
)
from croquito_worker.valuation.synthetic import build_synthetic_previous_mapao

REVIEWER: Final = "orcamentista-de-teste"

_FROZEN_NOW: Final = datetime(2026, 3, 2, 15, 30, tzinfo=UTC)

_PAVEMENT: Final = "PISO INTERTRAVADO SINTETICO"
_LAWN: Final = "GRAMADO SINTETICO"
_FENCE: Final = "ALAMBRADO SINTETICO"
_BENCH: Final = "BANCO DE CONCRETO SINTETICO"
_LAMP: Final = "LUMINARIA DUPLA SINTETICA"
_INTERVENTION: Final = "AREA DE INTERVENCAO SINTETICA"
_RUBBER: Final = "PISO EMBORRACHADO SINTETICO"

_TAKEOFF_REVIEW: Final[tuple[tuple[str, dict[str, str]], ...]] = (
    (_PAVEMENT, {"action": "confirm"}),
    (_LAWN, {"action": "confirm"}),
    # Alambrado: metro linear convertido em área pelo revisor, com a conta na nota.
    (
        _FENCE,
        {
            "action": "confirm",
            "quantity": "58.50",
            "unit": "m2",
            "note": "convertido para área: 48,75 m x h=1,20 m",
        },
    ),
    (_BENCH, {"action": "confirm"}),
    (_LAMP, {"action": "confirm"}),
    (_INTERVENTION, {"action": "reject", "note": "área de referência da prancha"}),
    # A linha ilegível só fecha porque o revisor informa a quantidade.
    (_RUBBER, {"action": "confirm", "quantity": "18.40", "note": "quantidade lida na prancha"}),
)

_CODE_REVIEW: Final[tuple[tuple[str, dict[str, str]], ...]] = (
    (_PAVEMENT, {"action": "confirm", "code": "AD04050060(/)"}),
    (_LAWN, {"action": "reject", "note": "sem cotação aplicável no contrato sintético"}),
    (_FENCE, {"action": "confirm", "code": "CE02100010(/)"}),
    (_BENCH, {"action": "confirm", "code": "MB01100010(/)"}),
    (_LAMP, {"action": "confirm", "code": "MB01300010(/)"}),
    (_RUBBER, {"action": "confirm", "code": "AD04150010(/)"}),
)

_CODE_OUTSIDE_CATALOG: Final = "ZZ99999999(/)"
"""Tem a estrutura de um código SCO e não existe no catálogo sintético de 32 itens."""

_CODE_IN_CUBIC_METERS: Final = "SP01050010(/)"
"""ESCAVACAO SINTETICA MANUAL EM SOLO, em M3: incompatível com o banco medido em UN."""


def _snapshot(root: Path) -> dict[str, str]:
    """Digest de cada arquivo da rodada; recusa nenhuma pode mover qualquer um deles."""
    return {
        path.name: hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(root.iterdir())
        if path.is_file()
    }


def _build_run(root: Path) -> Path:
    """Diretório de rodada como o orçamentista o teria: MAPÃO importado + prancha extraída."""
    previous = build_synthetic_previous_mapao(root / "previous-mapao.xlsx")
    assert cli_main(["import-workbook", "--input", str(previous), "--output", str(root)]) == 0
    assert cli_main(["extract-legend", "--output", str(root)]) == 0
    return root


def _item_ids(client: TestClient) -> dict[str, str]:
    """Mapa rótulo → id do item, lido do pacote servido (nunca recalculado no teste)."""
    packet = client.get("/takeoff").json()["packet"]
    return {item["label"]: item["id"] for item in packet["items"]}


def _review_takeoff(client: TestClient) -> str:
    """Aplica a revisão inteira do takeoff, uma decisão por requisição.

    Devolve o digest final do pacote; cada chamada usa o digest que a anterior devolveu,
    que é exatamente o que a UI vai fazer.
    """
    identifiers = _item_ids(client)
    digest = str(client.get("/takeoff").json()["packet_sha256"])
    for label, decision in _TAKEOFF_REVIEW:
        response = client.post(
            "/takeoff/decisions",
            json={"item_id": identifiers[label], "base_packet_sha256": digest, **decision},
        )
        assert response.status_code == 200, (label, response.json())
        digest = str(response.json()["packet_sha256"])
    return digest


def _confirm_codes(client: TestClient) -> str:
    """Confirma o código item a item e FECHA o pacote de cada elemento precificado.

    Os dois atos, e não um: confirmar um código deixou de significar que o elemento acabou
    (ADR-0053). Sem o fechamento a rodada ficaria com todo item pendente e `calc/build`
    recusaria em `CALC_PACKAGE_NOT_CLOSED`. A rejeição fecha o item sozinha e não é fechada
    aqui — é ela que vira candidato a aditivo.
    """
    identifiers = _item_ids(client)
    base: str | None = None
    for label, decision in _CODE_REVIEW:
        body: dict[str, object] = {"item_id": identifiers[label], **decision}
        if base is not None:
            body["base_assignments_sha256"] = base
        response = client.post("/codes/decisions", json=body)
        assert response.status_code == 200, (label, response.json())
        base = str(response.json()["assignments_sha256"])

    for label, decision in _CODE_REVIEW:
        if decision.get("action") != "confirm":
            continue
        response = client.post(
            "/codes/closures",
            json={"item_id": identifiers[label], "base_assignments_sha256": base},
        )
        assert response.status_code == 200, (label, response.json())
        base = str(response.json()["assignments_sha256"])

    assert base is not None
    return base


@pytest.fixture(scope="module")
def prepared_root(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Rodada recém-extraída, sem nenhuma decisão. Cara o bastante para rodar uma vez só."""
    return _build_run(tmp_path_factory.mktemp("valuation-run"))


@pytest.fixture(scope="module")
def reviewed_prepared_root(tmp_path_factory: pytest.TempPathFactory, prepared_root: Path) -> Path:
    """Rodada com o takeoff inteiro revisado pelo próprio servidor, pronta para os códigos."""
    root = tmp_path_factory.mktemp("valuation-reviewed") / "run"
    shutil.copytree(prepared_root, root)
    _review_takeoff(TestClient(create_local_app(root, REVIEWER)))
    return root


@pytest.fixture
def root(prepared_root: Path, tmp_path: Path) -> Path:
    """Cópia isolada por teste: cada um muta a própria rodada."""
    destination = tmp_path / "run"
    shutil.copytree(prepared_root, destination)
    return destination


@pytest.fixture
def reviewed_root(reviewed_prepared_root: Path, tmp_path: Path) -> Path:
    destination = tmp_path / "reviewed"
    shutil.copytree(reviewed_prepared_root, destination)
    return destination


@pytest.fixture
def client(root: Path) -> Iterator[TestClient]:
    yield TestClient(create_local_app(root, REVIEWER))


@pytest.fixture
def reviewed_client(reviewed_root: Path) -> Iterator[TestClient]:
    yield TestClient(create_local_app(reviewed_root, REVIEWER))


def test_state_opens_on_the_takeoff_stage_with_the_reviewer_of_the_server(
    client: TestClient, root: Path
) -> None:
    payload = client.get("/state").json()

    assert payload["reviewer_id"] == REVIEWER
    assert payload["reviewer_role"] == "orcamentista"
    assert payload["takeoff"]["review_status"] == "review_required"
    assert payload["takeoff"]["pending"] == 7
    assert payload["takeoff"]["packet_sha256"] == _snapshot(root)[TAKEOFF_PACKET_FILENAME]
    assert payload["codes"]["suggestions_present"] is False
    assert payload["codes"]["assignments_present"] is False
    assert payload["bulletin"]["present"] is False
    assert payload["images"] == {
        "plate": {"present": True, "filename": PLATE_IMAGE_FILENAME},
        "overlay": {"present": True},
    }
    assert payload["artifacts"][CATALOG_FILENAME] == _snapshot(root)[CATALOG_FILENAME]


def test_full_flow_from_review_to_bulletin(client: TestClient, root: Path) -> None:
    """Da revisão do takeoff ao boletim, pelas rotas, com os totais vindo do domínio."""
    overlay_before = (root / TAKEOFF_OVERLAY_FILENAME).read_bytes()

    packet_digest = _review_takeoff(client)

    assert packet_digest == _snapshot(root)[TAKEOFF_PACKET_FILENAME]
    state = client.get("/state").json()
    assert state["takeoff"]["review_status"] == "complete"
    assert state["takeoff"]["confirmed"] == 6
    assert state["takeoff"]["rejected"] == 1
    # O overlay é regravado a cada decisão: as cores de estado mudaram na prancha.
    assert (root / TAKEOFF_OVERLAY_FILENAME).read_bytes() != overlay_before

    suggestions = client.get("/suggestions").json()
    assert suggestions["computed"] is True
    assert (root / CODE_SUGGESTIONS_FILENAME).is_file()
    assert len(suggestions["suggestions"]["suggestions"]) == 6
    assert suggestions["suggestions"]["suggester_version"] == SCO_LEXICAL_IDF_SUGGESTER_VERSION
    # Observação, nunca decisão: a shortlist não confirma nada.
    assert client.get("/codes").json()["assignments"] is None
    assert len(client.get("/codes").json()["pending_items"]) == 6

    _confirm_codes(client)

    codes = client.get("/codes").json()
    assert codes["confirmed"] == 5
    assert codes["rejected"] == 1
    assert codes["pending_items"] == []

    built = client.post(
        "/calc/build",
        json={
            "worksite_key": "praca-sintetica-oeste",
            "worksite_name": "PRACA SINTETICA OESTE",
            "period_number": 3,
            "reference_label": "3ª MEDICAO SINTETICA",
            "address": "RUA SINTETICA, S/N",
            "contract_label": "CONTRATO SINTETICO",
        },
    )
    assert built.status_code == 200
    assert (root / VALUATION_FILENAME).is_file()

    bulletin = client.get("/bulletin").json()
    assert bulletin["valuation_sha256"] == _snapshot(root)[VALUATION_FILENAME]
    lines = bulletin["valuation"]["bulletins"][0]["lines"]
    # O gramado saiu do boletim porque o código dele foi rejeitado.
    assert [line["code"] for line in lines] == [
        "AD04050060(/)",
        "CE02100010(/)",
        "MB01100010(/)",
        "MB01300010(/)",
        "AD04150010(/)",
    ]
    fence = next(line for line in lines if line["code"] == "CE02100010(/)")
    assert fence["quantity"] == "58.50"
    assert Decimal(str(bulletin["total_amount"])) == sum(
        (Decimal(str(line["total"])) for line in lines), Decimal("0.00")
    )
    assert client.get("/state").json()["bulletin"]["present"] is True


def test_calc_build_refuses_plan_and_matrix_in_the_same_round(
    client: TestClient, root: Path
) -> None:
    """Plano por item E matriz por serviço no mesmo diretório é `CALC_PLAN_AND_MATRIX_DECLARED`.

    São dois regimes de memória que não fundem (ADR-0053); a rodada recusa antes de montar.
    """
    _review_takeoff(client)
    _confirm_codes(client)
    (root / CALC_PLAN_FILENAME).write_text('{"plans": []}', encoding="utf-8")
    matrix = CalcMatrix(
        services=[
            ServiceContributions(
                code="CE02100010(/)",
                contributions=[
                    CalcContribution(
                        label="CANTEIRO",
                        basis=ContributionBasis.STANDALONE,
                        recipe=CalcRecipe.DECLARED_PRODUCT,
                        operands=[CalcOperand(name="VB", value=Decimal("1"))],
                    )
                ],
            )
        ]
    )
    (root / CALC_MATRIX_FILENAME).write_text(matrix.model_dump_json(), encoding="utf-8")

    response = client.post(
        "/calc/build",
        json={
            "worksite_key": "praca-sintetica-oeste",
            "worksite_name": "PRACA SINTETICA OESTE",
            "period_number": 3,
            "reference_label": "3ª MEDICAO SINTETICA",
            "address": "RUA SINTETICA, S/N",
            "contract_label": "CONTRATO SINTETICO",
        },
    )

    assert response.status_code == 422, response.text
    assert response.json()["code"] == "CALC_PLAN_AND_MATRIX_DECLARED"
    # Fail-closed: a recusa não grava boletim.
    assert not (root / VALUATION_FILENAME).is_file()


def test_a_second_decision_over_the_same_item_is_refused_and_writes_nothing(
    client: TestClient, root: Path
) -> None:
    identifiers = _item_ids(client)
    first = client.post(
        "/takeoff/decisions",
        json={
            "item_id": identifiers[_PAVEMENT],
            "action": "confirm",
            "base_packet_sha256": client.get("/takeoff").json()["packet_sha256"],
        },
    )
    assert first.status_code == 200
    before = _snapshot(root)

    response = client.post(
        "/takeoff/decisions",
        json={
            "item_id": identifiers[_PAVEMENT],
            "action": "reject",
            "base_packet_sha256": first.json()["packet_sha256"],
        },
    )

    assert response.status_code == 422
    assert response.json()["code"] == "TAKEOFF_ITEM_ALREADY_REVIEWED"
    assert _snapshot(root) == before


def test_a_stale_base_digest_refuses_with_local_state_moved(client: TestClient, root: Path) -> None:
    identifiers = _item_ids(client)
    stale = str(client.get("/takeoff").json()["packet_sha256"])
    accepted = client.post(
        "/takeoff/decisions",
        json={"item_id": identifiers[_PAVEMENT], "action": "confirm", "base_packet_sha256": stale},
    )
    assert accepted.status_code == 200
    before = _snapshot(root)

    response = client.post(
        "/takeoff/decisions",
        json={"item_id": identifiers[_LAWN], "action": "confirm", "base_packet_sha256": stale},
    )

    assert response.status_code == 409
    assert response.headers["content-type"].startswith("application/problem+json")
    payload = response.json()
    assert payload["code"] == "LOCAL_STATE_MOVED"
    assert payload["details"]["base_sha256"] == stale
    assert payload["details"]["current_sha256"] == accepted.json()["packet_sha256"]
    assert _snapshot(root) == before


def test_confirming_the_ambiguous_item_without_quantity_is_refused(
    client: TestClient, root: Path
) -> None:
    before = _snapshot(root)

    response = client.post(
        "/takeoff/decisions",
        json={
            "item_id": _item_ids(client)[_RUBBER],
            "action": "confirm",
            "base_packet_sha256": client.get("/takeoff").json()["packet_sha256"],
        },
    )

    assert response.status_code == 422
    assert response.json()["code"] == "TAKEOFF_ITEM_CONFIRMED_INCOMPLETE"
    assert _snapshot(root) == before


def test_identity_and_timestamp_in_the_body_are_refused(client: TestClient, root: Path) -> None:
    """Quem decide vem da flag do servidor; carimbo é do relógio dele. Corpo não escolhe."""
    before = _snapshot(root)
    digest = client.get("/takeoff").json()["packet_sha256"]
    item_id = _item_ids(client)[_PAVEMENT]

    for forbidden in ("reviewer_id", "reviewer_role", "decided_at", "decision_id"):
        response = client.post(
            "/takeoff/decisions",
            json={
                "item_id": item_id,
                "action": "confirm",
                "base_packet_sha256": digest,
                forbidden: "2020-01-01T00:00:00+00:00",
            },
        )

        assert response.status_code == 422, forbidden
        assert response.json()["code"] == "LOCAL_REQUEST_INVALID"
    assert _snapshot(root) == before


def test_a_quantity_that_is_not_a_number_is_refused(client: TestClient, root: Path) -> None:
    before = _snapshot(root)

    response = client.post(
        "/takeoff/decisions",
        json={
            "item_id": _item_ids(client)[_RUBBER],
            "action": "confirm",
            "quantity": "dezoito e quarenta",
            "base_packet_sha256": client.get("/takeoff").json()["packet_sha256"],
        },
    )

    assert response.status_code == 422
    assert response.json()["code"] == "LOCAL_QUANTITY_INVALID"
    assert _snapshot(root) == before


def test_a_code_outside_the_catalog_is_refused(
    reviewed_client: TestClient, reviewed_root: Path
) -> None:
    before = _snapshot(reviewed_root)

    response = reviewed_client.post(
        "/codes/decisions",
        json={
            "item_id": _item_ids(reviewed_client)[_PAVEMENT],
            "action": "confirm",
            "code": _CODE_OUTSIDE_CATALOG,
        },
    )

    assert response.status_code == 422
    assert response.json()["code"] == "ASSIGNMENT_CODE_NOT_IN_CATALOG"
    assert _snapshot(reviewed_root) == before


def test_an_incompatible_unit_without_a_note_is_refused(
    reviewed_client: TestClient, reviewed_root: Path
) -> None:
    before = _snapshot(reviewed_root)

    response = reviewed_client.post(
        "/codes/decisions",
        json={
            "item_id": _item_ids(reviewed_client)[_BENCH],
            "action": "confirm",
            "code": _CODE_IN_CUBIC_METERS,
        },
    )

    assert response.status_code == 422
    assert response.json()["code"] == "ASSIGNMENT_UNIT_INCOMPATIBLE_WITHOUT_NOTE"
    assert _snapshot(reviewed_root) == before


def test_a_code_decision_without_the_base_digest_is_refused_once_a_set_exists(
    reviewed_client: TestClient, reviewed_root: Path
) -> None:
    identifiers = _item_ids(reviewed_client)
    first = reviewed_client.post(
        "/codes/decisions",
        json={"item_id": identifiers[_PAVEMENT], "action": "confirm", "code": "AD04050060(/)"},
    )
    assert first.status_code == 200
    before = _snapshot(reviewed_root)

    response = reviewed_client.post(
        "/codes/decisions",
        json={"item_id": identifiers[_FENCE], "action": "confirm", "code": "CE02100010(/)"},
    )

    assert response.status_code == 409
    assert response.json()["code"] == "LOCAL_BASE_DIGEST_REQUIRED"
    assert _snapshot(reviewed_root) == before


def test_a_base_digest_before_the_first_code_decision_is_refused(
    reviewed_client: TestClient, reviewed_root: Path
) -> None:
    before = _snapshot(reviewed_root)

    response = reviewed_client.post(
        "/codes/decisions",
        json={
            "item_id": _item_ids(reviewed_client)[_PAVEMENT],
            "action": "confirm",
            "code": "AD04050060(/)",
            "base_assignments_sha256": "0" * 64,
        },
    )

    assert response.status_code == 409
    assert response.json()["code"] == "LOCAL_BASE_DIGEST_UNEXPECTED"
    assert _snapshot(reviewed_root) == before


def test_calc_build_refuses_a_confirmed_item_without_a_code_decision(
    reviewed_client: TestClient, reviewed_root: Path
) -> None:
    reviewed_client.post(
        "/codes/decisions",
        json={
            "item_id": _item_ids(reviewed_client)[_PAVEMENT],
            "action": "confirm",
            "code": "AD04050060(/)",
        },
    )
    before = _snapshot(reviewed_root)

    response = reviewed_client.post(
        "/calc/build",
        json={
            "worksite_key": "praca-sintetica-oeste",
            "worksite_name": "PRACA SINTETICA OESTE",
            "period_number": 3,
            "reference_label": "3ª MEDICAO SINTETICA",
        },
    )

    assert response.status_code == 422
    assert response.json()["code"] == "CALC_ASSIGNMENT_MISSING"
    assert _snapshot(reviewed_root) == before


def test_dossier_build_and_read_carry_the_rejected_code_item_with_its_justification(
    client: TestClient, root: Path
) -> None:
    """Espelho de `test_full_flow_from_review_to_bulletin` para o outro artefato de
    fechamento da rodada: o gramado (código rejeitado por falta de cotação) vira o único
    item do dossiê, com a nota da rejeição como justificativa — nunca preço."""
    _review_takeoff(client)
    _confirm_codes(client)
    lawn_id = _item_ids(client)[_LAWN]

    built = client.post("/dossier/build")

    assert built.status_code == 200
    assert (root / AMENDMENT_DOSSIER_FILENAME).is_file()
    payload = built.json()
    assert payload["item_count"] == 1
    assert payload["dossier_sha256"] == _snapshot(root)[AMENDMENT_DOSSIER_FILENAME]
    (item,) = payload["dossier"]["items"]
    assert item["item_id"] == lawn_id
    assert item["label"] == _LAWN
    assert item["justification"] == "sem cotação aplicável no contrato sintético"
    assert "price" not in json.dumps(payload["dossier"])
    assert "unit_price" not in json.dumps(payload["dossier"])

    read = client.get("/dossier")
    assert read.status_code == 200
    assert read.json() == payload
    assert client.get("/state").json()["dossier"] == {
        "present": True,
        "dossier_sha256": payload["dossier_sha256"],
    }


def test_dossier_build_without_any_rejection_is_a_valid_empty_dossier(
    reviewed_client: TestClient,
) -> None:
    # Mesmo `_CODE_REVIEW`, mas o gramado ganha um código válido em vez de ser rejeitado:
    # esta rodada não tem nenhuma rejeição de código, então o dossiê é válido e vazio.
    lawn_confirmed: tuple[str, dict[str, str]] = (
        _LAWN,
        {"action": "confirm", "code": "AD04050060(/)"},
    )
    all_confirmed = tuple(
        lawn_confirmed if label == _LAWN else (label, decision) for label, decision in _CODE_REVIEW
    )
    identifiers = _item_ids(reviewed_client)
    base: str | None = None
    for label, decision in all_confirmed:
        body: dict[str, object] = {"item_id": identifiers[label], **decision}
        if base is not None:
            body["base_assignments_sha256"] = base
        response = reviewed_client.post("/codes/decisions", json=body)
        assert response.status_code == 200, (label, response.json())
        base = response.json()["assignments_sha256"]

    built = reviewed_client.post("/dossier/build")

    assert built.status_code == 200
    assert built.json()["dossier"]["items"] == []
    assert built.json()["item_count"] == 0


def test_dossier_build_refuses_without_a_code_assignment_set_and_writes_nothing(
    client: TestClient, root: Path
) -> None:
    """Sem `code-assignments.json` na rodada, o dossiê recusa como artefato ausente — o
    mesmo caminho que `POST /calc/build` já usa para o mesmo artefato-base."""
    before = _snapshot(root)

    response = client.post("/dossier/build")

    assert response.status_code == 404
    assert response.json() == {
        "code": "LOCAL_ARTIFACT_MISSING",
        "detail": "artefato de entrada ausente no diretório da rodada",
        "details": {"artifact": CODE_ASSIGNMENTS_FILENAME},
    }
    assert _snapshot(root) == before


def test_dossier_read_before_it_is_built_is_404(client: TestClient) -> None:
    response = client.get("/dossier")

    assert response.status_code == 404
    assert response.json()["code"] == "LOCAL_ARTIFACT_MISSING"


def test_dossier_read_revalidates_and_a_tampered_file_is_422(
    client: TestClient, root: Path
) -> None:
    _review_takeoff(client)
    _confirm_codes(client)
    client.post("/dossier/build")
    (root / AMENDMENT_DOSSIER_FILENAME).write_text("{}", encoding="utf-8")

    response = client.get("/dossier")

    assert response.status_code == 422


def test_dossier_build_has_no_base_digest_guard_like_calc_build(
    client: TestClient, root: Path
) -> None:
    """`POST /dossier/build` é espelho do `POST /calc/build` real (não da descrição textual
    do spec de handoff): o par `/calc/build`/`/bulletin` NÃO exige `base_*_sha256` no
    corpo — ele só lê os artefatos-base atuais e sobrescreve o artefato de saída. Este
    teste prova que o dossiê segue o MESMO contrato, sem inventar uma guarda que a rota
    espelhada não tem."""
    _review_takeoff(client)
    _confirm_codes(client)

    first = client.post("/dossier/build", json={})
    assert first.status_code == 200
    second = client.post("/dossier/build")
    assert second.status_code == 200
    # As duas chamadas recomputam do mesmo estado-base e publicam o mesmo conteúdo.
    assert first.json()["dossier_sha256"] == second.json()["dossier_sha256"]


def test_suggestions_before_the_review_is_complete_are_refused_and_write_nothing(
    client: TestClient, root: Path
) -> None:
    before = _snapshot(root)

    response = client.get("/suggestions")

    assert response.status_code == 422
    assert response.json()["code"] == "LOCAL_TAKEOFF_REVIEW_INCOMPLETE"
    assert _snapshot(root) == before


def test_suggestions_are_computed_once_and_then_served_from_the_file(
    reviewed_client: TestClient, reviewed_root: Path
) -> None:
    first = reviewed_client.get("/suggestions").json()
    written = _snapshot(reviewed_root)[CODE_SUGGESTIONS_FILENAME]

    second = reviewed_client.get("/suggestions").json()

    assert first["computed"] is True
    assert second["computed"] is False
    assert first["suggestions_sha256"] == second["suggestions_sha256"] == written


def test_recompute_before_the_review_is_complete_refuses_and_writes_nothing(
    client: TestClient, root: Path
) -> None:
    before = _snapshot(root)

    response = client.post("/suggestions/recompute", json={})

    assert response.status_code == 422
    assert response.json()["code"] == "LOCAL_TAKEOFF_REVIEW_INCOMPLETE"
    assert _snapshot(root) == before


def test_recompute_without_a_shortlist_computes_the_first_one(
    reviewed_client: TestClient, reviewed_root: Path
) -> None:
    assert not (reviewed_root / CODE_SUGGESTIONS_FILENAME).exists()

    response = reviewed_client.post("/suggestions/recompute", json={})

    assert response.status_code == 200
    payload = response.json()
    assert payload["computed"] is True
    assert (reviewed_root / CODE_SUGGESTIONS_FILENAME).exists()


def test_recompute_requires_the_base_digest_when_the_shortlist_exists(
    reviewed_client: TestClient, reviewed_root: Path
) -> None:
    reviewed_client.get("/suggestions")
    before = _snapshot(reviewed_root)

    response = reviewed_client.post("/suggestions/recompute", json={})

    assert response.status_code == 409
    assert response.json()["code"] == "LOCAL_BASE_DIGEST_REQUIRED"
    assert _snapshot(reviewed_root) == before


def test_recompute_with_a_stale_base_digest_refuses_and_writes_nothing(
    reviewed_client: TestClient, reviewed_root: Path
) -> None:
    reviewed_client.get("/suggestions")
    before = _snapshot(reviewed_root)

    response = reviewed_client.post(
        "/suggestions/recompute", json={"base_suggestions_sha256": "0" * 64}
    )

    assert response.status_code == 409
    assert response.json()["code"] == "LOCAL_STATE_MOVED"
    assert _snapshot(reviewed_root) == before


def test_recompute_overwrites_a_stale_shortlist_with_the_current_algorithm(
    reviewed_client: TestClient, reviewed_root: Path
) -> None:
    """Simula um artefato desatualizado (item movido para `unmatched_item_ids` à mão) e
    confere que o recompute o substitui pelo cálculo corrente, com o item de volta."""
    first = reviewed_client.get("/suggestions").json()
    suggestions = CodeSuggestionSet.model_validate(first["suggestions"])
    assert suggestions.suggestions, "fixture precisa ter ao menos uma sugestão"
    moved = suggestions.suggestions[0]
    stale = suggestions.model_copy(
        update={
            "suggestions": suggestions.suggestions[1:],
            "unmatched_item_ids": [*suggestions.unmatched_item_ids, moved.item_id],
        }
    )
    stale_document = stale.model_dump_json(indent=2) + "\n"
    (reviewed_root / CODE_SUGGESTIONS_FILENAME).write_text(stale_document, encoding="utf-8")
    stale_digest = hashlib.sha256(stale_document.encode("utf-8")).hexdigest()

    response = reviewed_client.post(
        "/suggestions/recompute", json={"base_suggestions_sha256": stale_digest}
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["computed"] is True
    assert payload["suggestions_sha256"] != stale_digest
    assert _snapshot(reviewed_root)[CODE_SUGGESTIONS_FILENAME] == payload["suggestions_sha256"]
    recomputed = CodeSuggestionSet.model_validate(payload["suggestions"])
    assert moved.item_id not in recomputed.unmatched_item_ids
    assert moved.item_id in {suggestion.item_id for suggestion in recomputed.suggestions}


def test_recompute_never_discards_a_paid_refinement(
    reviewed_client: TestClient, reviewed_root: Path
) -> None:
    base = CodeSuggestionSet.model_validate(
        reviewed_client.get("/suggestions").json()["suggestions"]
    )
    assert base.suggester_version == SCO_LEXICAL_IDF_SUGGESTER_VERSION
    refined = base.model_copy(
        update={
            "suggester_version": base.suggester_version + LLM_RERANK_SUFFIX,
            "refinement": SuggestionRefinement(
                provider="anthropic",
                model_id="claude-sonnet-5",
                prompt_version="sco-refinement@1.0.1",
                input_digest="a" * 64,
            ),
        }
    )
    document = refined.model_dump_json(indent=2) + "\n"
    (reviewed_root / CODE_SUGGESTIONS_FILENAME).write_text(document, encoding="utf-8")
    digest = hashlib.sha256(document.encode("utf-8")).hexdigest()
    before = _snapshot(reviewed_root)

    response = reviewed_client.post(
        "/suggestions/recompute", json={"base_suggestions_sha256": digest}
    )

    assert response.status_code == 409
    assert response.json()["code"] == "LOCAL_SUGGESTIONS_REFINED"
    assert _snapshot(reviewed_root) == before


def test_images_are_served_by_the_two_fixed_names(client: TestClient) -> None:
    plate = client.get("/images/plate")
    overlay = client.get("/images/overlay")

    assert plate.status_code == 200
    assert plate.headers["content-type"] == "image/png"
    assert overlay.status_code == 200
    assert overlay.headers["content-type"] == "image/png"


def test_the_plate_is_resolved_by_digest_when_the_name_is_the_page_of_the_ingest(
    root: Path,
) -> None:
    """Prancha real chega como `page-001.png`; quem manda é o digest do pacote."""
    (root / PLATE_IMAGE_FILENAME).rename(root / "page-001.png")
    client = TestClient(create_local_app(root, REVIEWER))

    response = client.get("/images/plate")

    assert response.status_code == 200
    assert client.get("/state").json()["images"]["plate"]["filename"] == "page-001.png"


def test_missing_images_return_404(root: Path) -> None:
    (root / PLATE_IMAGE_FILENAME).unlink()
    (root / TAKEOFF_OVERLAY_FILENAME).unlink()
    client = TestClient(create_local_app(root, REVIEWER))

    plate = client.get("/images/plate")
    overlay = client.get("/images/overlay")

    assert plate.status_code == 404
    assert plate.json()["code"] == "LOCAL_ARTIFACT_MISSING"
    assert overlay.status_code == 404
    assert overlay.json()["details"]["artifact"] == TAKEOFF_OVERLAY_FILENAME


def test_no_route_accepts_a_path_of_its_own(root: Path) -> None:
    """Travessia de diretório é impossível por construção: nenhuma rota tem parâmetro de
    caminho, e as imagens são exatamente dois nomes fixos.

    Os caminhos são lidos do próprio OpenAPI publicado, e não da lista interna de rotas:
    é ele o contrato que o servidor expõe, e ele continua verdadeiro qualquer que seja a
    forma como as rotas foram registradas (direto no app ou por roteador incluído)."""
    application = create_local_app(root, REVIEWER)

    paths = set(application.openapi()["paths"])

    assert {path for path in paths if path.startswith("/images")} == {
        "/images/plate",
        "/images/overlay",
    }
    assert [path for path in paths if "{" in path] == []


def test_a_decision_without_the_plate_image_keeps_the_decision_and_declares_the_overlay(
    root: Path,
) -> None:
    """Falta de imagem não invalida o ato do revisor; ela é declarada no retorno."""
    (root / PLATE_IMAGE_FILENAME).unlink()
    client = TestClient(create_local_app(root, REVIEWER))
    overlay_before = (root / TAKEOFF_OVERLAY_FILENAME).read_bytes()

    response = client.post(
        "/takeoff/decisions",
        json={
            "item_id": _item_ids(client)[_PAVEMENT],
            "action": "confirm",
            "base_packet_sha256": client.get("/takeoff").json()["packet_sha256"],
        },
    )

    assert response.status_code == 200
    assert response.json()["overlay_written"] is False
    assert response.json()["notes"] != []
    assert (root / TAKEOFF_OVERLAY_FILENAME).read_bytes() == overlay_before
    assert client.get("/state").json()["takeoff"]["confirmed"] == 1


# --------------------------------------------------------------------------------------
# Âncora declarada por item (`registered` | `raw`)
# --------------------------------------------------------------------------------------


def _write_registration_report(
    root: Path, *, method: str | None, item_ids: Sequence[str], unmatched: Sequence[str] = ()
) -> None:
    """Relatório de registro na forma que `register-takeoff` publica."""
    report: dict[str, Any] = {
        "adjusted": [
            {"item_id": item_id, "before": {}, "after": {}, "shift_px": 6} for item_id in item_ids
        ],
        "unmatched_item_ids": list(unmatched),
        "band_count": 7,
        "global_scale": None,
        "global_shift_px": None,
        "shift_score": None,
        "shift_confidence": None,
    }
    if method is not None:
        report["method"] = method
    (root / TAKEOFF_REGISTRATION_REPORT_FILENAME).write_text(
        json.dumps(report, ensure_ascii=False), encoding="utf-8"
    )


def _anchors(payload: Mapping[str, Any]) -> dict[str, str]:
    return {item["id"]: item["anchor"] for item in payload["packet"]["items"]}


def test_without_a_registration_report_every_anchor_is_raw(client: TestClient) -> None:
    """Pacote que nunca passou por registro não promete âncora nenhuma."""
    payload = client.get("/takeoff").json()

    assert set(_anchors(payload).values()) == {"raw"}
    assert payload["anchors_registered"] == 0
    assert payload["anchors_raw"] == 7
    assert client.get("/state").json()["takeoff"]["anchors_raw"] == 7


def test_only_the_items_the_report_covers_are_declared_registered(
    client: TestClient, root: Path
) -> None:
    identifiers = _item_ids(client)
    covered = [identifiers[_PAVEMENT], identifiers[_LAWN]]
    others = [item_id for item_id in identifiers.values() if item_id not in covered]
    _write_registration_report(root, method="rulings", item_ids=covered, unmatched=others)

    payload = client.get("/takeoff").json()

    anchors = _anchors(payload)
    assert {anchors[item_id] for item_id in covered} == {"registered"}
    assert {anchors[item_id] for item_id in others} == {"raw"}
    assert payload["anchors_registered"] == 2
    assert payload["anchors_raw"] == 5
    state = client.get("/state").json()["takeoff"]
    assert (state["anchors_registered"], state["anchors_raw"]) == (2, 5)


def test_the_anchor_is_a_read_side_join_and_does_not_touch_the_packet_on_disk(
    client: TestClient, root: Path
) -> None:
    """O digest continua sendo o do ARQUIVO: é ele que a guarda otimista compara depois."""
    _write_registration_report(root, method="text_bands", item_ids=[_item_ids(client)[_PAVEMENT]])
    before = _snapshot(root)

    payload = client.get("/takeoff").json()

    stored = json.loads((root / TAKEOFF_PACKET_FILENAME).read_text(encoding="utf-8"))
    assert all("anchor" not in item for item in stored["items"])
    assert payload["packet_sha256"] == before[TAKEOFF_PACKET_FILENAME]
    assert _snapshot(root) == before


@pytest.mark.parametrize("method", [None, "none", "metodo-desconhecido"])
def test_a_report_without_a_trustworthy_method_leaves_every_anchor_raw(
    client: TestClient, root: Path, method: str | None
) -> None:
    """`none` é o desfecho em que nada passou no gate; método ausente ou estranho idem."""
    _write_registration_report(root, method=method, item_ids=list(_item_ids(client).values()))

    payload = client.get("/takeoff").json()

    assert set(_anchors(payload).values()) == {"raw"}
    assert payload["anchors_registered"] == 0


def test_an_unreadable_registration_report_leaves_every_anchor_raw(
    client: TestClient, root: Path
) -> None:
    (root / TAKEOFF_REGISTRATION_REPORT_FILENAME).write_text("{quebrado", encoding="utf-8")

    payload = client.get("/takeoff").json()

    assert set(_anchors(payload).values()) == {"raw"}


def test_the_decision_response_carries_the_anchor_of_each_item(
    client: TestClient, root: Path
) -> None:
    identifiers = _item_ids(client)
    _write_registration_report(root, method="text_bands", item_ids=[identifiers[_PAVEMENT]])

    response = client.post(
        "/takeoff/decisions",
        json={
            "item_id": identifiers[_PAVEMENT],
            "action": "confirm",
            "base_packet_sha256": client.get("/takeoff").json()["packet_sha256"],
        },
    )

    payload = response.json()
    assert response.status_code == 200
    assert _anchors(payload)[identifiers[_PAVEMENT]] == "registered"
    assert (payload["anchors_registered"], payload["anchors_raw"]) == (1, 6)
    # O contrato que já existia continua inteiro ao lado da junção nova.
    assert payload["review_status"] == "review_required"
    assert payload["confirmed"] == 1
    assert payload["overlay_written"] is True


def _catalog_of(root: Path) -> PriceCatalog:
    return PriceCatalog.model_validate_json((root / CATALOG_FILENAME).read_text(encoding="utf-8"))


def test_catalog_search_ignores_case_and_accent_and_requires_every_word(
    client: TestClient,
) -> None:
    accented = client.get("/catalog/search", params={"q": "PiSo InTeRtRaVaDo SiNtÉtIcO"}).json()
    plain = client.get("/catalog/search", params={"q": "piso intertravado sintetico"}).json()
    disjoint = client.get("/catalog/search", params={"q": "piso alambrado"}).json()

    assert accented["results"] == plain["results"]
    assert accented["terms"] == plain["terms"]
    assert accented["total_matches"] == plain["total_matches"] == 4
    assert all("INTERTRAVADO" in item["description"] for item in accented["results"])
    assert disjoint["total_matches"] == 0
    assert disjoint["results"] == []


def test_catalog_search_finds_the_family_by_code_prefix(client: TestClient) -> None:
    payload = client.get("/catalog/search", params={"q": "ad0405"}).json()

    assert payload["total_matches"] == 4
    assert all(item["code"].startswith("AD0405") for item in payload["results"])


def test_catalog_search_caps_the_page_and_returns_the_full_description(
    client: TestClient, root: Path
) -> None:
    catalog = _catalog_of(root)

    payload = client.get("/catalog/search", params={"q": "sintetico", "limit": 3}).json()

    expected = sum(1 for entry in catalog.entries if "SINTETICO" in entry.description)
    assert expected > 3
    assert payload["total_matches"] == expected
    assert len(payload["results"]) == 3
    first = payload["results"][0]
    entry = catalog.entry_for(first["code"])
    assert first["description"] == entry.description
    assert first["unit_price"] == str(entry.unit_price)
    assert first["unit"] == entry.unit


_SEARCH_ENTRIES: Final[tuple[tuple[str, str, str], ...]] = (
    ("AD04050060(/)", "PISO INTERTRAVADO DE CONCRETO 35 MPA", "m2"),
    (
        "AD04050070(/)",
        "REJUNTAMENTO DE PISO INTERTRAVADO COM AREIA DE QUARTZO LAVADA E SECA",
        "m2",
    ),
    ("AD04150010(/)", "ENCERAMENTO DE PISO EM MADEIRA COM CERA LIQUIDA", "m2"),
    ("CE02100010(/)", "PLANTIO DE GRAMA EM PLACAS, INCLUSIVE PREPARO DO TERRENO", "m2"),
    ("CE02100020(/)", "GRAMADOS: MANUTENCAO PERIODICA COM CORTE E ADUBACAO", "m2"),
    ("CE02100030(/)", "GRAMADO ESMERALDA EM PLACAS", "m2"),
    # Adversariais: contêm "gramado" e "pis" DENTRO de outra palavra.
    ("MB01300010(/)", "PROGRAMADOR DE COMPUTADOR PARA IRRIGACAO AUTOMATIZADA", "un"),
    ("SP01050010(/)", "PISCINA INFANTIL PRE-MOLDADA, FORNECIMENTO E INSTALACAO", "un"),
    # Descrição repetida: prova o desempate por código, não por posição no catálogo.
    ("MB01100020(/)", "BANCO DE CONCRETO PRE-MOLDADO SEM ENCOSTO", "un"),
    ("MB01100010(/)", "BANCO DE CONCRETO PRE-MOLDADO SEM ENCOSTO", "un"),
)
"""Catálogo sintético da busca, com as armadilhas reais da homologação.

As frases são as que o defeito produzia: quem procurava `gramado` recebia
`PROGRAMADOR DE COMPUTADOR`, porque o casamento era por substring."""


def _search_catalog() -> PriceCatalog:
    return PriceCatalog(
        source_label="CATALOGO SINTETICO DE BUSCA",
        reference_month="2026-08",
        source_sha256="b" * 64,
        entries=[
            PriceCatalogEntry(
                code=code,
                description=description,
                unit=unit,
                unit_price=Decimal("12.34"),
                family_code="XX",
                family_name="FAMILIA SINTETICA",
                subgroup_code="XX01",
                subgroup_name="SUBGRUPO SINTETICO",
            )
            for code, description, unit in _SEARCH_ENTRIES
        ],
    )


@pytest.fixture
def search_client(empty_root: Path) -> Iterator[TestClient]:
    """Rodada cujo catálogo é o sintético da busca, servido pela rota real."""
    (empty_root / CATALOG_FILENAME).write_text(
        _search_catalog().model_dump_json(indent=2), encoding="utf-8"
    )
    yield TestClient(create_local_app(empty_root, REVIEWER))


def _search(client: TestClient, query: str, **params: Any) -> dict[str, Any]:
    response = client.get("/catalog/search", params={"q": query, **params})
    assert response.status_code == 200, response.json()
    return dict(response.json())


def _codes(payload: Mapping[str, Any]) -> list[str]:
    return [item["code"] for item in payload["results"]]


def test_catalog_search_never_matches_a_word_inside_another_word(
    search_client: TestClient,
) -> None:
    """Regressão da homologação: `gramado` trazia `PROGRAMADOR DE COMPUTADOR`."""
    payload = _search(search_client, "gramado")

    descriptions = " | ".join(item["description"] for item in payload["results"])
    assert "PROGRAMADOR" not in descriptions
    assert payload["total_matches"] == 3
    assert sorted(_codes(payload)) == ["CE02100010(/)", "CE02100020(/)", "CE02100030(/)"]


def test_catalog_search_matches_the_inflection_of_the_word_in_both_directions(
    search_client: TestClient,
) -> None:
    """`gramado` acha `grama` e `gramados`; a flexão casa, a coincidência de letras não."""
    plural = _search(search_client, "gramados")
    singular = _search(search_client, "grama")

    assert sorted(_codes(plural)) == ["CE02100010(/)", "CE02100020(/)", "CE02100030(/)"]
    assert sorted(_codes(singular)) == ["CE02100010(/)", "CE02100020(/)", "CE02100030(/)"]


def test_catalog_search_expands_a_synonym_whose_stem_differs_from_the_raw_word(
    tmp_path: Path,
) -> None:
    """Regressão: `expand_terms` casa por RADICAL ("alambrado" -> "alambra"), então a busca
    precisa expandir pelo radical da palavra digitada, não pela grafia crua — senão o
    sinônimo `alambrado -> tela de arame galvanizado` nunca dispara, porque nenhum radical
    do grupo é igual à palavra "alambrado" como o usuário a digitou."""
    root = tmp_path / "rodada-sinonimo"
    root.mkdir()
    catalog = PriceCatalog(
        source_label="CATALOGO SINONIMO",
        reference_month="2026-08",
        source_sha256="c" * 64,
        entries=[
            PriceCatalogEntry(
                code="PJ14150050(/)",
                description=(
                    "Cerca com tela de arame galvanizado nº 12, malha quadrada de 1 "
                    "polegada, fixada em montantes de tubos galvanizados."
                ),
                unit="m2",
                unit_price=Decimal("89.30"),
                family_code="PJ",
                family_name="FAMILIA SINTETICA",
                subgroup_code="PJ14",
                subgroup_name="SUBGRUPO SINTETICO",
            )
        ],
    )
    (root / CATALOG_FILENAME).write_text(catalog.model_dump_json(indent=2), encoding="utf-8")
    client = TestClient(create_local_app(root, REVIEWER))

    payload = _search(client, "alambrado")

    assert payload["total_matches"] == 1
    assert payload["results"][0]["code"] == "PJ14150050(/)"
    assert payload["expanded_terms"]["tela"] == ["alambrado"]


def test_catalog_search_ranks_the_closest_description_first(search_client: TestClient) -> None:
    """A revisora vê primeiro o item mais próximo do que digitou, não o mais alto na
    planilha."""
    gramado = _search(search_client, "gramado")
    intertravado = _search(search_client, "piso intertravado")

    assert _codes(gramado)[0] == "CE02100030(/)"
    assert _codes(intertravado) == ["AD04050060(/)", "AD04050070(/)"]
    # `ENCERAMENTO DE PISO` não tem `intertravado`: continua fora, como sempre esteve.
    assert all("ENCERAMENTO" not in item["description"] for item in intertravado["results"])


def test_catalog_search_ignores_a_prefix_shorter_than_the_named_floor(
    search_client: TestClient,
) -> None:
    """`pis` não traz `piscina` nem `piso`: abaixo do piso, prefixo é coincidência."""
    payload = _search(search_client, "pis")

    assert payload["total_matches"] == 0
    assert payload["terms"] == ["pis"]


def test_catalog_search_is_deterministic_and_breaks_ties_by_code(
    search_client: TestClient,
) -> None:
    first = _search(search_client, "banco")
    second = _search(search_client, "banco")

    assert first == second
    assert set(first) == {
        "query",
        "terms",
        "limit",
        "matching",
        "total_matches",
        "semantic_matches",
        "semantic_notes",
        "results",
    }
    assert first["matching"] == "lexical"
    assert _codes(first) == ["MB01100010(/)", "MB01100020(/)"]


def test_catalog_search_refuses_a_query_without_a_usable_word(client: TestClient) -> None:
    response = client.get("/catalog/search", params={"q": "-"})

    assert response.status_code == 422
    assert response.json()["code"] == "LOCAL_SEARCH_QUERY_EMPTY"


def test_catalog_search_refuses_a_limit_above_the_cap(client: TestClient) -> None:
    response = client.get("/catalog/search", params={"q": "sintetico", "limit": 500})

    assert response.status_code == 422
    assert response.json()["code"] == "LOCAL_REQUEST_INVALID"


def test_a_missing_artifact_is_404_with_the_name_of_the_file(root: Path) -> None:
    (root / TAKEOFF_PACKET_FILENAME).unlink()
    client = TestClient(create_local_app(root, REVIEWER))

    response = client.get("/takeoff")

    assert response.status_code == 404
    assert response.json() == {
        "code": "LOCAL_ARTIFACT_MISSING",
        "detail": "artefato de entrada ausente no diretório da rodada",
        "details": {"artifact": TAKEOFF_PACKET_FILENAME},
    }


def test_the_same_sequence_of_calls_produces_byte_identical_artifacts(
    prepared_root: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Determinismo com o relógio fixo: só `decided_at` varia entre duas rodadas iguais.

    `valuation.json` fica de fora de propósito — `Valuation.id` é um UUIDv7 por decisão do
    domínio, então a medição nunca é byte a byte igual entre duas construções.
    """
    monkeypatch.setattr(local_server, "_now", lambda: _FROZEN_NOW)
    artifacts = (TAKEOFF_PACKET_FILENAME, CODE_SUGGESTIONS_FILENAME, CODE_ASSIGNMENTS_FILENAME)

    produced: list[dict[str, bytes]] = []
    for index in range(2):
        root = tmp_path / f"pass-{index}"
        shutil.copytree(prepared_root, root)
        client = TestClient(create_local_app(root, REVIEWER))
        _review_takeoff(client)
        assert client.get("/suggestions").status_code == 200
        _confirm_codes(client)
        produced.append({name: (root / name).read_bytes() for name in artifacts})

    assert produced[0] == produced[1]


def _serve_argv(root: Path, **extra: str) -> list[str]:
    argv = ["serve", "--root", str(root), "--reviewer", REVIEWER]
    for flag, value in extra.items():
        argv += [f"--{flag}", value]
    return argv


def test_serve_hands_the_local_app_to_uvicorn(
    root: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    recorded: dict[str, object] = {}

    def _fake_run(application: Any, *, host: str, port: int) -> None:
        recorded.update({"routes": len(application.routes), "host": host, "port": port})

    monkeypatch.setattr(local_server, "run_local_server", _fake_run)

    assert cli_main(_serve_argv(root)) == 0

    assert recorded["host"] == "127.0.0.1"
    assert recorded["port"] == 8801
    printed = capsys.readouterr().out
    assert '"status": "serving"' in printed
    assert "LOCAL_SERVER_EXPOSED" not in printed


def test_serve_warns_before_binding_outside_localhost(
    root: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(local_server, "run_local_server", lambda *_args, **_kwargs: None)

    assert cli_main(_serve_argv(root, host="0.0.0.0", port="9999")) == 0

    assert "LOCAL_SERVER_EXPOSED" in capsys.readouterr().out


def test_serve_refuses_a_root_that_is_not_a_run_directory(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    exit_code = cli_main(_serve_argv(tmp_path / "nao-existe"))

    assert exit_code == 2
    payload: Mapping[str, object] = _last_json(capsys)
    assert payload["refused"] == "LOCAL_ROOT_MISSING"


def _last_json(capsys: pytest.CaptureFixture[str]) -> dict[str, Any]:
    lines = [line for line in capsys.readouterr().out.splitlines() if line.strip()]
    return dict(json.loads(lines[-1]))


# --------------------------------------------------------------------------------------
# Upload da prancha do projetista e extração paga automática
# --------------------------------------------------------------------------------------

BUDGET_ENV: Final = "CROQUITO_AI_MAX_ESTIMATED_COST_USD"
ANTHROPIC_KEY_ENV: Final = "CROQUITO_ANTHROPIC_API_KEY"
ALLOWLIST_ENV: Final = "CROQUITO_AI_EXTRACTION_ALLOWED_DIGESTS"

_FIXTURE_MODEL_ID: Final = "fixture-legend-v1"
_PROMOTED_PAGE_FILENAME: Final = "page-001.png"


def _plate_pdf(pages: int = 1) -> bytes:
    """Prancha sintética escrita no próprio teste; nenhum documento de cliente no Git."""
    document = pymupdf.open()
    try:
        for number in range(1, pages + 1):
            page = document.new_page(width=595, height=842)
            page.insert_text((60, 120), f"PRANCHA SINTETICA DE TESTE {number}", fontsize=14)
            page.insert_text((60, 160), "PISO INTERTRAVADO SINTETICO 61,20 M2", fontsize=12)
            page.insert_text((60, 190), "PISO EMBORRACHADO SINTETICO --- M2", fontsize=12)
        return bytes(document.tobytes())
    finally:
        document.close()


def _legend_output() -> LegendExtractionOutput:
    """Transcrição fabricada das duas linhas da prancha: uma legível, uma ilegível."""
    return LegendExtractionOutput(
        rows=[
            LegendRowOutput(
                raw_text="PISO INTERTRAVADO SINTETICO 61,20 M2",
                label="PISO INTERTRAVADO SINTETICO",
                quantity_text="61,20",
                unit_text="M2",
                bbox=NormalizedBox(left=0.09, top=0.175, right=0.62, bottom=0.20),
                legibility="clear",
            ),
            LegendRowOutput(
                raw_text="PISO EMBORRACHADO SINTETICO --- M2",
                label="PISO EMBORRACHADO SINTETICO",
                quantity_text=None,
                unit_text="M2",
                bbox=NormalizedBox(left=0.09, top=0.21, right=0.62, bottom=0.235),
                legibility="illegible",
            ),
        ],
        page_notes=["fixture de teste; nenhuma prancha de cliente foi lida"],
    )


def _legend_adapter() -> FixtureProviderAdapter:
    return FixtureProviderAdapter(
        provider=ProviderName.ANTHROPIC,
        model_id=_FIXTURE_MODEL_ID,
        outputs={PromptTask.LEGEND_EXTRACTION: _legend_output()},
    )


@dataclass(frozen=True, slots=True)
class _FailingAdapter:
    """Braço que falha como provider fora do ar; depois dele nada pode ser publicado."""

    code: ProviderFailureCode

    def execute(self, request: ProviderRequest) -> ProviderExecution:
        raise ProviderExecutionError(self.code)


@dataclass(frozen=True, slots=True)
class _BlockingAdapter:
    """Braço que segura a chamada até o teste liberar: é o que torna `running` observável."""

    released: threading.Event
    inner: FixtureProviderAdapter

    def execute(self, request: ProviderRequest) -> ProviderExecution:
        assert self.released.wait(timeout=30), "adapter bloqueado nunca foi liberado"
        return self.inner.execute(request)


def _patch_extraction_arm(monkeypatch: pytest.MonkeyPatch, adapter: ProviderAdapter) -> None:
    """Seam do módulo: nenhuma chamada externa acontece nesta suíte."""
    monkeypatch.setattr(
        local_server,
        "_build_extraction_adapter",
        lambda arm_spec: (arm_spec.partition("=")[0], _FIXTURE_MODEL_ID, adapter),
    )


def _allow_paid_extraction(monkeypatch: pytest.MonkeyPatch) -> None:
    """Servidor com teto de gasto e credencial declarados.

    A allowlist global sai de propósito: neste fluxo o consentimento é o ato de upload, e
    o teste só prova isso se a variável de ambiente estiver comprovadamente ausente.
    """
    monkeypatch.setenv(BUDGET_ENV, "1.50")
    monkeypatch.setenv(ANTHROPIC_KEY_ENV, "chave-de-teste-nunca-usada")
    monkeypatch.delenv(ALLOWLIST_ENV, raising=False)


def _forbid_paid_extraction(monkeypatch: pytest.MonkeyPatch) -> None:
    """Servidor sem nenhuma env de gasto — nem na máquina de quem tem credencial."""
    for name in (BUDGET_ENV, ANTHROPIC_KEY_ENV, ALLOWLIST_ENV):
        monkeypatch.delenv(name, raising=False)


def _upload(client: TestClient, payload: bytes, *, filename: str = "prancha.pdf") -> Any:
    return client.post("/plates", files={"file": (filename, payload, "application/pdf")})


def _extraction_state(client: TestClient) -> dict[str, Any]:
    return dict(client.get("/state").json()["extracao"])


def _wait_for_extraction(
    client: TestClient, status: str, *, timeout: float = 60.0
) -> dict[str, Any]:
    """Acompanha a etapa pelo `/state`, como a tela vai acompanhar."""
    deadline = time.monotonic() + timeout
    seen: dict[str, Any] = {}
    while time.monotonic() < deadline:
        seen = _extraction_state(client)
        if seen["status"] == status:
            return seen
        time.sleep(0.05)
    raise AssertionError(f"a extração não chegou a {status}: {seen}")


@pytest.fixture
def empty_root(tmp_path: Path) -> Path:
    """Rodada nova, sem prancha: é nela que o upload é o primeiro ato."""
    destination = tmp_path / "rodada-nova"
    destination.mkdir()
    return destination


@pytest.fixture
def empty_client(empty_root: Path) -> Iterator[TestClient]:
    yield TestClient(create_local_app(empty_root, REVIEWER))


def test_the_state_of_a_round_without_a_plate_declares_the_extraction_stage(
    empty_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Indisponibilidade aparece na abertura da tela, não depois de o revisor subir o PDF."""
    _allow_paid_extraction(monkeypatch)
    idle = _extraction_state(empty_client)

    _forbid_paid_extraction(monkeypatch)
    unavailable = _extraction_state(empty_client)

    assert idle["status"] == "idle"
    assert idle["plate_pdf_present"] is False
    assert idle["pages"] is None
    assert idle["arm"] == local_server.MEDICAO_EXTRACTION_ARM
    assert unavailable["status"] == "unavailable"
    assert unavailable["error_code"] == "LOCAL_EXTRACTION_UNAVAILABLE"
    assert "teto de gasto" in str(unavailable["message"])


def test_the_upload_ingests_the_plate_and_the_paid_extraction_publishes_the_packet(
    empty_client: TestClient, empty_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Caminho feliz inteiro: upload → ingestão → extração → pacote, overlay e lineage."""
    _allow_paid_extraction(monkeypatch)
    _patch_extraction_arm(monkeypatch, _legend_adapter())
    payload = _plate_pdf()
    digest = hashlib.sha256(payload).hexdigest()

    accepted = _upload(empty_client, payload)

    assert accepted.status_code == 202
    assert accepted.json()["extracao"]["status"] in {"running", "done"}
    extraction = _wait_for_extraction(empty_client, "done")
    assert extraction["error_code"] is None
    # O consentimento é o ato de upload: o digest registrado é o do arquivo enviado.
    assert extraction["consented_source_sha256"] == digest
    assert ALLOWLIST_ENV not in os.environ
    assert extraction["pages"] == 1
    assert extraction["notes"] == []
    execution = extraction["execution"]
    assert execution["provider"] == "anthropic"
    assert execution["model_id"] == _FIXTURE_MODEL_ID
    assert execution["prompt_version"] == "legend-extraction@1.0.1"
    assert set(execution) >= {"latency_ms", "input_tokens", "output_tokens", "estimated_cost_usd"}

    packet = load_takeoff_packet(empty_root / TAKEOFF_PACKET_FILENAME)
    assert packet.source_pdf_sha256 == digest
    assert packet.confirmed_items() == []
    assert [item.status.value for item in packet.items] == ["proposed", "ambiguous"]
    for filename in (
        PLATE_PDF_FILENAME,
        PLATE_MANIFEST_FILENAME,
        _PROMOTED_PAGE_FILENAME,
        TAKEOFF_OVERLAY_FILENAME,
        TAKEOFF_REGISTRATION_REPORT_FILENAME,
        EXTRACTION_LINEAGE_FILENAME,
    ):
        assert (empty_root / filename).is_file(), filename
    lineage = json.loads((empty_root / EXTRACTION_LINEAGE_FILENAME).read_text(encoding="utf-8"))
    report = json.loads(
        (empty_root / TAKEOFF_REGISTRATION_REPORT_FILENAME).read_text(encoding="utf-8")
    )
    # O método do registro viaja no relatório: é ele que autoriza a âncora na tela.
    assert report["method"] in {"rulings", "text_bands", "none"}
    assert lineage["consented_source_sha256"] == digest
    assert lineage["arm"] == local_server.MEDICAO_EXTRACTION_ARM
    assert lineage["execution"]["model_id"] == _FIXTURE_MODEL_ID

    state = empty_client.get("/state").json()
    assert state["takeoff"]["review_status"] == "review_required"
    assert state["takeoff"]["pending"] == 2
    assert state["images"]["plate"] == {"present": True, "filename": _PROMOTED_PAGE_FILENAME}
    assert empty_client.get("/images/plate").status_code == 200
    assert empty_client.get("/images/overlay").status_code == 200


def test_without_the_spending_cap_the_plate_is_ingested_and_the_extraction_is_unavailable(
    empty_client: TestClient, empty_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Sem teto configurado nada é tentado — e o re-disparo fecha a rodada depois."""
    _forbid_paid_extraction(monkeypatch)
    payload = _plate_pdf()

    accepted = _upload(empty_client, payload)

    assert accepted.status_code == 202
    extraction = accepted.json()["extracao"]
    assert extraction["status"] == "unavailable"
    assert extraction["error_code"] == "LOCAL_EXTRACTION_UNAVAILABLE"
    assert "teto de gasto" in extraction["message"]
    assert extraction["details"]["missing_env"] == [BUDGET_ENV, ANTHROPIC_KEY_ENV]
    # A prancha ficou na rodada: rodar a extração depois continua possível.
    assert (empty_root / PLATE_PDF_FILENAME).is_file()
    assert (empty_root / PLATE_MANIFEST_FILENAME).is_file()
    assert (empty_root / _PROMOTED_PAGE_FILENAME).is_file()
    assert not (empty_root / TAKEOFF_PACKET_FILENAME).exists()
    assert not (empty_root / EXTRACTION_LINEAGE_FILENAME).exists()

    refused = empty_client.post("/plates/extract")
    assert refused.status_code == 409
    assert refused.json()["code"] == "LOCAL_EXTRACTION_UNAVAILABLE"

    _allow_paid_extraction(monkeypatch)
    _patch_extraction_arm(monkeypatch, _legend_adapter())
    retried = empty_client.post("/plates/extract")

    assert retried.status_code == 202
    assert _wait_for_extraction(empty_client, "done")["error_code"] is None
    assert load_takeoff_packet(empty_root / TAKEOFF_PACKET_FILENAME).confirmed_items() == []


def test_a_second_plate_on_a_round_that_already_has_one_is_refused_and_writes_nothing(
    client: TestClient, root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _allow_paid_extraction(monkeypatch)
    _patch_extraction_arm(monkeypatch, _legend_adapter())
    before = _snapshot(root)

    response = _upload(client, _plate_pdf())

    assert response.status_code == 409
    payload = response.json()
    assert payload["code"] == "LOCAL_ROUND_ALREADY_HAS_PLATE"
    assert "diretório novo" in payload["detail"]
    assert _snapshot(root) == before


@pytest.mark.parametrize(
    ("filename", "payload"),
    [
        ("legenda.png", b"\x89PNG\r\n\x1a\n dados de imagem"),
        ("prancha.pdf", b"isto nao e um PDF"),
        ("prancha.pdf", b""),
        # Assinatura certa, conteúdo quebrado: a recusa vem da ingestão e desfaz o upload.
        ("prancha.pdf", b"%PDF-1.7\nconteudo truncado"),
    ],
)
def test_a_file_that_is_not_a_plate_pdf_is_refused_and_leaves_the_round_empty(
    empty_client: TestClient, empty_root: Path, filename: str, payload: bytes
) -> None:
    response = _upload(empty_client, payload, filename=filename)

    assert response.status_code == 422
    assert response.json()["code"] == "LOCAL_UPLOAD_INVALID"
    assert list(empty_root.iterdir()) == []


def test_an_upload_above_the_named_limit_is_refused_before_any_write(
    empty_client: TestClient, empty_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(local_server, "MAX_PLATE_PDF_BYTES", 256)

    response = _upload(empty_client, _plate_pdf())

    assert response.status_code == 422
    assert response.json()["details"]["max_bytes"] == 256
    assert list(empty_root.iterdir()) == []


def test_a_provider_failure_publishes_nothing_and_the_retry_closes_the_round(
    empty_client: TestClient, empty_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Falha do provider é visível e não custa o documento: o re-disparo usa a prancha já
    ingerida."""
    _allow_paid_extraction(monkeypatch)
    _patch_extraction_arm(monkeypatch, _FailingAdapter(ProviderFailureCode.TIMEOUT))

    assert _upload(empty_client, _plate_pdf()).status_code == 202

    failed = _wait_for_extraction(empty_client, "failed")
    assert failed["error_code"] == "PROVIDER_EXECUTION_FAILED"
    assert failed["details"] == {"code": "TIMEOUT"}
    assert not (empty_root / TAKEOFF_PACKET_FILENAME).exists()
    assert not (empty_root / TAKEOFF_OVERLAY_FILENAME).exists()
    assert not (empty_root / TAKEOFF_REGISTRATION_REPORT_FILENAME).exists()
    assert not (empty_root / EXTRACTION_LINEAGE_FILENAME).exists()
    assert (empty_root / PLATE_PDF_FILENAME).is_file()
    assert (empty_root / _PROMOTED_PAGE_FILENAME).is_file()

    _patch_extraction_arm(monkeypatch, _legend_adapter())
    assert empty_client.post("/plates/extract").status_code == 202

    assert _wait_for_extraction(empty_client, "done")["error_code"] is None
    assert (empty_root / TAKEOFF_PACKET_FILENAME).is_file()


def test_a_second_extraction_while_one_runs_is_refused_as_busy(
    empty_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    released = threading.Event()
    _allow_paid_extraction(monkeypatch)
    _patch_extraction_arm(monkeypatch, _BlockingAdapter(released=released, inner=_legend_adapter()))
    try:
        assert _upload(empty_client, _plate_pdf()).status_code == 202
        _wait_for_extraction(empty_client, "running")

        busy = empty_client.post("/plates/extract")
        second_plate = _upload(empty_client, _plate_pdf())

        assert busy.status_code == 409
        assert busy.json()["code"] == "LOCAL_EXTRACTION_BUSY"
        assert second_plate.status_code == 409
        assert second_plate.json()["code"] == "LOCAL_ROUND_ALREADY_HAS_PLATE"
    finally:
        released.set()

    assert _wait_for_extraction(empty_client, "done")["error_code"] is None


def test_extracting_without_an_ingested_plate_is_refused_with_the_missing_artifact(
    empty_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _allow_paid_extraction(monkeypatch)
    _patch_extraction_arm(monkeypatch, _legend_adapter())

    response = empty_client.post("/plates/extract")

    assert response.status_code == 404
    assert response.json()["details"]["artifact"] == PLATE_MANIFEST_FILENAME


def test_a_multi_page_pdf_promotes_the_first_page_and_declares_the_count(
    empty_client: TestClient, empty_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Limitação declarada, não escondida: a rodada leu a página 1 e diz quantas havia."""
    _forbid_paid_extraction(monkeypatch)

    extraction = _upload(empty_client, _plate_pdf(pages=3)).json()["extracao"]

    assert extraction["pages"] == 3
    assert extraction["page_number"] == 1
    assert len(extraction["notes"]) == 1
    assert "página 1" in extraction["notes"][0]
    assert sorted(path.name for path in empty_root.glob("*.png")) == [_PROMOTED_PAGE_FILENAME]
    manifest = json.loads((empty_root / PLATE_MANIFEST_FILENAME).read_text(encoding="utf-8"))
    assert manifest["page_count"] == 3


# --------------------------------------------------------------------------------------
# Catálogo de preços da rodada e avisos do banner do `serve`
# --------------------------------------------------------------------------------------

CATALOG_ENV: Final = "CROQUITO_MEDICAO_CATALOG"


@pytest.fixture
def catalog_file(prepared_root: Path, tmp_path: Path) -> Path:
    """Catálogo importado por fora da rodada — a fonte que o operador passa em `--catalog`."""
    source = tmp_path / "catalogo-fonte.json"
    shutil.copy(prepared_root / CATALOG_FILENAME, source)
    return source


def _other_catalog(source: Path, destination: Path) -> Path:
    """Mesmo catálogo com outro rótulo de origem: serve para provar que nada foi trocado."""
    document = json.loads(source.read_text(encoding="utf-8"))
    document["source_label"] = "CATALOGO ALTERNATIVO DE TESTE"
    destination.write_text(json.dumps(document, ensure_ascii=False), encoding="utf-8")
    return destination


@pytest.fixture
def served(monkeypatch: pytest.MonkeyPatch) -> None:
    """`serve` sem subir uvicorn e sem herdar a env de catálogo da máquina."""
    monkeypatch.setattr(local_server, "run_local_server", lambda *_args, **_kwargs: None)
    monkeypatch.delenv(CATALOG_ENV, raising=False)


@pytest.mark.usefixtures("served")
def test_serve_installs_the_catalog_in_a_round_that_has_none(
    empty_root: Path, catalog_file: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Rodada nascida de upload não passou pelo `import-workbook`: o catálogo entra aqui."""
    assert cli_main(_serve_argv(empty_root, catalog=str(catalog_file))) == 0

    installed = empty_root / CATALOG_FILENAME
    assert installed.read_bytes() == catalog_file.read_bytes()
    assert _last_json(capsys)["catalog"] == local_server.CATALOG_NOTES["installed"]
    client = TestClient(create_local_app(empty_root, REVIEWER))
    assert client.get("/catalog/search", params={"q": "sintetico"}).json()["total_matches"] > 0


@pytest.mark.usefixtures("served")
def test_serve_never_overwrites_the_catalog_of_the_round(
    root: Path, catalog_file: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """O catálogo da rodada é a evidência de preço das confirmações já feitas."""
    other = _other_catalog(catalog_file, tmp_path / "outro-catalogo.json")
    before = _snapshot(root)

    assert cli_main(_serve_argv(root, catalog=str(other))) == 0

    assert _snapshot(root) == before
    assert _last_json(capsys)["catalog"] == local_server.CATALOG_NOTES["preserved"]


@pytest.mark.usefixtures("served")
def test_serve_refuses_an_invalid_catalog_and_leaves_the_round_untouched(
    empty_root: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    broken = tmp_path / "nao-e-catalogo.json"
    broken.write_text('{"entries": []}', encoding="utf-8")

    exit_code = cli_main(_serve_argv(empty_root, catalog=str(broken)))

    assert exit_code == 2
    payload = _last_json(capsys)
    assert payload["refused"] == "LOCAL_CATALOG_INVALID"
    assert list(empty_root.iterdir()) == []


@pytest.mark.usefixtures("served")
def test_serve_reads_the_catalog_from_the_environment_and_the_flag_wins(
    empty_root: Path,
    tmp_path: Path,
    catalog_file: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    other = _other_catalog(catalog_file, tmp_path / "catalogo-da-env.json")
    monkeypatch.setenv(CATALOG_ENV, str(other))
    from_env = tmp_path / "rodada-da-env"
    from_env.mkdir()

    assert cli_main(_serve_argv(from_env)) == 0
    assert cli_main(_serve_argv(empty_root, catalog=str(catalog_file))) == 0

    assert (from_env / CATALOG_FILENAME).read_bytes() == other.read_bytes()
    assert (empty_root / CATALOG_FILENAME).read_bytes() == catalog_file.read_bytes()


@pytest.mark.usefixtures("served")
def test_the_serve_banner_declares_the_catalog_and_the_extraction(
    empty_root: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """As duas condições que só dá para corrigir no start aparecem no start."""
    _forbid_paid_extraction(monkeypatch)

    assert cli_main(_serve_argv(empty_root)) == 0
    without = _last_json(capsys)

    _allow_paid_extraction(monkeypatch)
    assert cli_main(_serve_argv(empty_root)) == 0
    with_budget = _last_json(capsys)

    assert without["catalog"] == local_server.CATALOG_NOTES["missing"]
    assert without["extracao"] == (
        "extração automática indisponível: teto de gasto não configurado no servidor"
    )
    assert with_budget["extracao"] == f"disponível ({local_server.MEDICAO_EXTRACTION_ARM})"


def test_the_local_extraction_matches_the_cli_extraction_packet_for_packet(
    empty_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A montagem local troca o portão de consentimento e NADA MAIS.

    O servidor não chama `run_legend_extraction` porque aquele caminho exige a allowlist
    por variável de ambiente, que este fluxo dispensa por decisão registrada — aqui o
    consentimento é o upload. Este teste prende as duas montagens uma na outra: mesmo
    adapter, mesma prancha, mesmo pacote registrado e mesmo digest de documento. Divergência
    silenciosa entre elas reprova aqui.
    """
    _forbid_paid_extraction(monkeypatch)
    client = TestClient(create_local_app(empty_root, REVIEWER))
    payload = _plate_pdf()
    assert _upload(client, payload).status_code == 202
    run = local_server._Run(root=empty_root, reviewer_id=REVIEWER)
    manifest = run.plate_manifest()
    assert manifest is not None

    local = local_server._extract_legend_from_upload(run, manifest, _legend_adapter())

    monkeypatch.setenv(ALLOWLIST_ENV, hashlib.sha256(payload).hexdigest())
    from_cli = run_legend_extraction(
        empty_root / _PROMOTED_PAGE_FILENAME,
        empty_root / PLATE_MANIFEST_FILENAME,
        _legend_adapter(),
        plate_id=local.packet.plate_id,
        page_number=1,
    )

    assert local.packet.model_dump(mode="json") == from_cli.packet.model_dump(mode="json")
    assert local.source_sha256 == from_cli.source_sha256 == hashlib.sha256(payload).hexdigest()


# --------------------------------------------------------------------------------------
# Busca híbrida (M7 Fase 2): índice fabricado, degradação declarada e nenhum gasto oculto
# --------------------------------------------------------------------------------------


def _install_fixture_index(root: Path) -> None:
    """Índice FABRICADO da rodada, amarrado ao catálogo que o `import-workbook` gravou."""
    catalog = PriceCatalog.model_validate_json(
        (root / CATALOG_FILENAME).read_text(encoding="utf-8")
    )
    (root / CATALOG_INDEX_FILENAME).write_text(
        index_document(fixture_catalog_index(catalog)), encoding="utf-8"
    )


@dataclass
class _CountingEmbeddings:
    """Adapter de embeddings dublê que conta chamadas: gasto oculto vira teste que falha."""

    calls: list[list[str]] = dataclass_field(default_factory=list)

    def embed(self, texts: Sequence[str]) -> Any:
        batch = list(texts)
        self.calls.append(batch)
        return EmbeddingsExecution(
            provider=ProviderName.OPENAI,
            model_id=FIXTURE_EMBEDDINGS_MODEL,
            input_count=len(batch),
            input_digest=hashlib.sha256(str(batch).encode()).hexdigest(),
            dims=FIXTURE_EMBEDDINGS_DIMS,
            latency_ms=1,
            usage=ProviderUsage(input_tokens=len(batch)),
            vectors=tuple(fixture_vector(text) for text in batch),
        )


def _patch_embeddings(
    monkeypatch: pytest.MonkeyPatch, adapter: _CountingEmbeddings | None, reason: str | None = None
) -> None:
    monkeypatch.setattr(
        local_server,
        "embeddings_adapter_or_reason",
        lambda: (adapter, reason),
    )


def test_a_round_without_an_index_declares_the_semantic_search_unavailable(
    client: TestClient,
) -> None:
    payload = client.get("/state").json()["busca_semantica"]

    assert payload["status"] == "unavailable"
    assert payload["message"].startswith("busca semântica indisponível")
    assert payload["index_present"] is False
    assert payload["model_id"] is None


def test_with_an_index_and_a_credential_the_state_declares_the_model(
    root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _install_fixture_index(root)
    _patch_embeddings(monkeypatch, _CountingEmbeddings())

    payload = TestClient(create_local_app(root, REVIEWER)).get("/state").json()["busca_semantica"]

    assert payload["status"] == "available"
    assert payload["model_id"] == FIXTURE_EMBEDDINGS_MODEL
    assert payload["index_present"] is True


def test_with_an_index_but_no_credential_the_state_declares_the_cache_limit(
    root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _install_fixture_index(root)
    _patch_embeddings(monkeypatch, None, "via de embeddings indisponível: sem teto de gasto")

    payload = TestClient(create_local_app(root, REVIEWER)).get("/state").json()["busca_semantica"]

    assert payload["status"] == "limited"
    assert "sem teto de gasto" in payload["message"]
    assert payload["index_present"] is True


def test_an_index_of_another_catalog_degrades_the_search_instead_of_breaking_it(
    root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """No servidor, índice velho é degradação declarada: a busca continua, pelo léxico."""
    catalog = PriceCatalog.model_validate_json(
        (root / CATALOG_FILENAME).read_text(encoding="utf-8")
    )
    other = catalog.model_copy(update={"source_sha256": "f" * 64})
    (root / CATALOG_INDEX_FILENAME).write_text(
        index_document(fixture_catalog_index(other)), encoding="utf-8"
    )
    _patch_embeddings(monkeypatch, _CountingEmbeddings())
    client = TestClient(create_local_app(root, REVIEWER))

    state = client.get("/state").json()["busca_semantica"]
    payload = client.get("/catalog/search", params={"q": "sintetico"}).json()

    assert state["status"] == "unavailable"
    assert "INDEX_CATALOG_MISMATCH" in state["message"]
    assert payload["matching"] == "lexical"
    assert payload["results"]


def test_the_hybrid_search_declares_the_arm_of_every_result(
    root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _install_fixture_index(root)
    adapter = _CountingEmbeddings()
    _patch_embeddings(monkeypatch, adapter)
    client = TestClient(create_local_app(root, REVIEWER))

    payload = client.get("/catalog/search", params={"q": "sintetico"}).json()

    assert payload["matching"] == "hybrid"
    assert payload["semantic_matches"] > 0
    assert payload["semantic_notes"] == []
    assert payload["results"]
    assert {item["origin"] for item in payload["results"]} <= {"lexical", "semantic", "both"}
    assert any(item["semantic_score"] is not None for item in payload["results"])
    assert adapter.calls == [["sintetico"]]
    # Segunda busca igual: o cache da rodada responde e nenhuma chamada nova é feita.
    client.get("/catalog/search", params={"q": "sintetico"})
    assert adapter.calls == [["sintetico"]]
    assert (root / QUERY_CACHE_FILENAME).is_file()


def test_the_search_with_the_lexical_arm_pinned_makes_no_embedding_call_and_says_so(
    root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`arm=lexical` fixa o braço léxico mesmo com índice, teto de gasto e credencial
    disponíveis: nenhuma chamada de embedding acontece e `query-cache.json` nunca nasce."""
    _install_fixture_index(root)
    adapter = _CountingEmbeddings()
    _patch_embeddings(monkeypatch, adapter)
    client = TestClient(create_local_app(root, REVIEWER))

    payload = client.get("/catalog/search", params={"q": "sintetico", "arm": "lexical"}).json()

    assert payload["matching"] == "lexical"
    assert payload["results"]
    assert adapter.calls == []
    assert not (root / QUERY_CACHE_FILENAME).exists()
    assert local_server.SEMANTIC_NOT_REQUESTED_MESSAGE in payload["semantic_notes"]


def test_a_query_without_a_usable_word_is_refused_before_any_embedding_call(
    root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _install_fixture_index(root)
    adapter = _CountingEmbeddings()
    _patch_embeddings(monkeypatch, adapter)
    client = TestClient(create_local_app(root, REVIEWER))

    response = client.get("/catalog/search", params={"q": "-"})

    assert response.status_code == 422
    assert response.json()["code"] == "LOCAL_SEARCH_QUERY_EMPTY"
    assert adapter.calls == []


def test_without_a_credential_an_uncached_query_degrades_with_the_reason(
    root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _install_fixture_index(root)
    _patch_embeddings(monkeypatch, None, "via de embeddings indisponível: sem teto de gasto")
    client = TestClient(create_local_app(root, REVIEWER))

    payload = client.get("/catalog/search", params={"q": "sintetico"}).json()

    assert payload["matching"] == "lexical"
    assert payload["semantic_notes"] == ["busca semântica indisponível: SEMANTIC_QUERY_NOT_CACHED"]
    assert payload["results"]
    assert not (root / QUERY_CACHE_FILENAME).exists()


def test_a_provider_failure_degrades_the_search_instead_of_breaking_it(
    root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _install_fixture_index(root)

    class _Failing:
        def embed(self, _texts: Sequence[str]) -> Any:
            raise ProviderExecutionError(ProviderFailureCode.RATE_LIMITED)

    monkeypatch.setattr(local_server, "embeddings_adapter_or_reason", lambda: (_Failing(), None))
    client = TestClient(create_local_app(root, REVIEWER))

    payload = client.get("/catalog/search", params={"q": "sintetico"}).json()

    assert payload["matching"] == "lexical"
    assert payload["semantic_notes"] == ["busca semântica indisponível: provider RATE_LIMITED"]
    assert payload["results"]


def test_the_shortlist_is_hybrid_when_the_round_has_an_index(
    reviewed_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _install_fixture_index(reviewed_root)
    _patch_embeddings(monkeypatch, _CountingEmbeddings())
    client = TestClient(create_local_app(reviewed_root, REVIEWER))

    payload = client.get("/suggestions").json()

    assert payload["matching"] == "hybrid"
    assert payload["semantic_notes"] == []
    assert payload["suggestions"]["suggester_version"] == SCO_HYBRID_SUGGESTER_VERSION
    assert payload["suggestions"]["semantic"]["model_id"] == FIXTURE_EMBEDDINGS_MODEL
    # Servida do arquivo depois, o `matching` continua vindo do artefato, não do processo.
    assert client.get("/suggestions").json()["matching"] == "hybrid"


def test_without_an_index_the_shortlist_stays_lexical_with_the_reason(
    reviewed_client: TestClient,
) -> None:
    payload = reviewed_client.get("/suggestions").json()

    assert payload["matching"] == "lexical"
    assert payload["semantic_notes"] == [
        "busca semântica indisponível: sem índice",
    ]
    assert payload["suggestions"]["suggester_version"] == SCO_LEXICAL_IDF_SUGGESTER_VERSION
    assert payload["suggestions"]["semantic"] is None


def test_recompute_is_hybrid_when_the_round_has_an_index_and_pays_nothing_new(
    reviewed_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """O GET inicial paga e cacheia; o recompute lê o mesmo cache da rodada e não chama
    o adapter de embeddings de novo."""
    _install_fixture_index(reviewed_root)
    adapter = _CountingEmbeddings()
    _patch_embeddings(monkeypatch, adapter)
    client = TestClient(create_local_app(reviewed_root, REVIEWER))

    first = client.get("/suggestions").json()
    assert first["matching"] == "hybrid"
    calls_after_get = len(adapter.calls)
    assert calls_after_get > 0

    response = client.post(
        "/suggestions/recompute",
        json={"base_suggestions_sha256": first["suggestions_sha256"]},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["matching"] == "hybrid"
    assert len(adapter.calls) == calls_after_get


def test_serve_installs_the_index_that_sits_next_to_the_catalog(tmp_path: Path) -> None:
    source_dir = tmp_path / "import"
    _build_run(source_dir)
    _install_fixture_index(source_dir)
    round_dir = tmp_path / "rodada"
    round_dir.mkdir()

    catalog_note = install_round_catalog(round_dir, source_dir / CATALOG_FILENAME)
    index_note = install_round_catalog_index(round_dir, source_dir / CATALOG_FILENAME)

    assert catalog_note == CATALOG_NOTES["installed"]
    assert index_note == CATALOG_INDEX_NOTES["installed"]
    assert (round_dir / CATALOG_INDEX_FILENAME).read_bytes() == (
        source_dir / CATALOG_INDEX_FILENAME
    ).read_bytes()
    # Segunda subida não sobrescreve o índice da rodada.
    assert (
        install_round_catalog_index(round_dir, source_dir / CATALOG_FILENAME)
        == (CATALOG_INDEX_NOTES["preserved"])
    )


def test_serve_never_installs_an_index_of_another_catalog(tmp_path: Path) -> None:
    source_dir = tmp_path / "import"
    _build_run(source_dir)
    catalog = PriceCatalog.model_validate_json(
        (source_dir / CATALOG_FILENAME).read_text(encoding="utf-8")
    )
    other = catalog.model_copy(update={"source_sha256": "a" * 64})
    (source_dir / CATALOG_INDEX_FILENAME).write_text(
        index_document(fixture_catalog_index(other)), encoding="utf-8"
    )
    round_dir = tmp_path / "rodada"
    round_dir.mkdir()
    install_round_catalog(round_dir, source_dir / CATALOG_FILENAME)

    note = install_round_catalog_index(round_dir, source_dir / CATALOG_FILENAME)

    assert note == CATALOG_INDEX_NOTES["mismatch"]
    assert not (round_dir / CATALOG_INDEX_FILENAME).exists()


def test_the_index_cache_revalidates_when_the_file_changes(
    root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """O índice é memoizado por rodada, mas nunca servido depois de o arquivo mudar."""
    _install_fixture_index(root)
    _patch_embeddings(monkeypatch, _CountingEmbeddings())
    client = TestClient(create_local_app(root, REVIEWER))
    assert client.get("/state").json()["busca_semantica"]["status"] == "available"

    catalog = PriceCatalog.model_validate_json(
        (root / CATALOG_FILENAME).read_text(encoding="utf-8")
    )
    other = catalog.model_copy(update={"source_sha256": "b" * 64})
    (root / CATALOG_INDEX_FILENAME).write_text(
        index_document(fixture_catalog_index(other)), encoding="utf-8"
    )

    payload = client.get("/state").json()["busca_semantica"]

    assert payload["status"] == "unavailable"
    assert "INDEX_CATALOG_MISMATCH" in payload["message"]


def test_o_temporario_da_escrita_atomica_nunca_e_confundido_com_a_evidencia(
    empty_root: Path,
) -> None:
    """`Path.glob` casa dotfile, e o escritor de overlay cria `.{stem}.xxxx.png`.

    Sem a guarda, o temporário de uma publicação em curso entra na listagem: se ele tiver
    o digest da evidência, `plate_image` acha DOIS candidatos e devolve `None` (a rodada
    perde o overlay); se ele for renomeado entre listar e ler, o `file_sha256` estoura
    `FileNotFoundError` e derruba a rodada por causa de uma corrida alheia. Foi assim que
    este arquivo ficou intermitente.
    """
    conteudo = b"\x89PNG evidencia sintetica"
    digest = hashlib.sha256(conteudo).hexdigest()
    # A evidência NÃO tem o nome canônico: é o caso da prancha real vinda do ingest
    # (`page-001.png`), o único que chega a percorrer o `glob`. Com o nome canônico o
    # código retorna antes e o teste não exercitaria nada.
    evidencia = empty_root / "page-001.png"
    evidencia.write_bytes(conteudo)
    (empty_root / ".takeoff-overlay.abc123.png").write_bytes(conteudo)

    run = local_server._Run(root=empty_root, reviewer_id=REVIEWER)
    packet = SimpleNamespace(image_sha256=digest)

    assert run.plate_image(packet) == evidencia  # type: ignore[arg-type]
