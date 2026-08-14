"""Wiring da CLI de takeoff: `extract-legend`, `review-takeoff` e `takeoff-demo`.

Como no resto da medição, o que importa na recusa não é a mensagem: é o que **não**
aparece no diretório de saída. Decisão repetida, item desconhecido e imagem que não é a
prancha do pacote saem com 2 e sem gravar nada.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pytest

from croquitodxf_valuation.catalog import file_sha256
from croquitodxf_valuation.takeoff import (
    TakeoffDecisionBatch,
    TakeoffDecisionInput,
    TakeoffItemStatus,
    TakeoffPacket,
    load_takeoff_packet,
)
from croquitodxf_worker.valuation.cli import (
    TAKEOFF_DECISIONS_FILENAME,
    TAKEOFF_OVERLAY_FILENAME,
    TAKEOFF_PACKET_FILENAME,
    main,
)
from croquitodxf_worker.valuation.plate import (
    PLATE_IMAGE_FILENAME,
    PLATE_PDF_FILENAME,
    SYNTHETIC_LEGEND_ROWS,
)

_DECISIONS_FILENAME = "decisions.json"
_DECIDED_AT = datetime(2026, 2, 1, 12, 0, tzinfo=UTC)


def _stdout(capsys: pytest.CaptureFixture[str]) -> dict[str, object]:
    lines = [line for line in capsys.readouterr().out.splitlines() if line.strip()]
    return dict(json.loads(lines[-1]))


def _extract(output_dir: Path) -> int:
    return main(["extract-legend", "--output", str(output_dir)])


def _write_decisions(
    path: Path,
    packet: TakeoffPacket,
    *,
    item_ids: list[str] | None = None,
    quantity: Decimal | None = None,
) -> Path:
    """Lote de decisões do orçamentista sobre os itens citados; por padrão, o primeiro."""
    targets = item_ids if item_ids is not None else [packet.items[0].id]
    batch = TakeoffDecisionBatch(
        decisions=[
            TakeoffDecisionInput(
                item_id=item_id,
                action="confirm",
                reviewer_id="orcamentista-de-teste",
                reviewer_role="orcamentista",
                decided_at=_DECIDED_AT,
                quantity=quantity,
            )
            for item_id in targets
        ]
    )
    path.write_text(batch.model_dump_json(indent=2), encoding="utf-8")
    return path


def _review(
    packet_path: Path,
    decisions_path: Path,
    output_dir: Path,
    image_path: Path | None = None,
) -> int:
    argv = [
        "review-takeoff",
        "--packet",
        str(packet_path),
        "--decisions",
        str(decisions_path),
        "--output",
        str(output_dir),
    ]
    if image_path is not None:
        argv += ["--image", str(image_path)]
    return main(argv)


def _is_empty(directory: Path) -> bool:
    return not directory.exists() or list(directory.iterdir()) == []


def test_extract_legend_generates_the_plate_and_extracts_from_it(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    output_dir = tmp_path / "extract"

    exit_code = _extract(output_dir)

    assert exit_code == 0
    payload = _stdout(capsys)
    assert payload["plate_id"] == "plate-sintetica-v1"
    assert payload["items"] == len(SYNTHETIC_LEGEND_ROWS)
    assert payload["proposed"] == len(SYNTHETIC_LEGEND_ROWS) - 1
    assert payload["ambiguous"] == 1
    assert payload["confirmed"] == 0
    assert payload["review_status"] == "review_required"
    for filename in (
        PLATE_PDF_FILENAME,
        PLATE_IMAGE_FILENAME,
        TAKEOFF_PACKET_FILENAME,
        TAKEOFF_OVERLAY_FILENAME,
    ):
        assert (output_dir / filename).is_file()
    packet = load_takeoff_packet(output_dir / TAKEOFF_PACKET_FILENAME)
    assert (
        payload["image_sha256"]
        == packet.image_sha256
        == file_sha256(output_dir / PLATE_IMAGE_FILENAME)
    )
    assert (
        payload["pdf_sha256"]
        == packet.source_pdf_sha256
        == file_sha256(output_dir / PLATE_PDF_FILENAME)
    )


def test_review_takeoff_confirms_an_item_and_keeps_the_rest_pending(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    extracted = tmp_path / "extract"
    assert _extract(extracted) == 0
    _stdout(capsys)
    packet_path = extracted / TAKEOFF_PACKET_FILENAME
    packet = load_takeoff_packet(packet_path)
    decisions_path = _write_decisions(tmp_path / _DECISIONS_FILENAME, packet)
    output_dir = tmp_path / "review"

    exit_code = _review(packet_path, decisions_path, output_dir, extracted / PLATE_IMAGE_FILENAME)

    assert exit_code == 0
    payload = _stdout(capsys)
    assert payload["confirmed"] == 1
    assert payload["pending"] == len(packet.items) - 1
    assert payload["review_status"] == "review_required"
    reviewed = load_takeoff_packet(output_dir / TAKEOFF_PACKET_FILENAME)
    confirmed = reviewed.confirmed_items()
    assert [item.id for item in confirmed] == [packet.items[0].id]
    assert confirmed[0].decision is not None
    assert confirmed[0].decision.reviewer_id == "orcamentista-de-teste"
    assert (output_dir / TAKEOFF_OVERLAY_FILENAME).is_file()
    # A revisão publica em diretório próprio: o pacote extraído continua como estava.
    assert load_takeoff_packet(packet_path).confirmed_items() == []


def test_review_takeoff_without_an_image_writes_only_the_packet(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    extracted = tmp_path / "extract"
    assert _extract(extracted) == 0
    _stdout(capsys)
    packet_path = extracted / TAKEOFF_PACKET_FILENAME
    decisions_path = _write_decisions(
        tmp_path / _DECISIONS_FILENAME, load_takeoff_packet(packet_path)
    )
    output_dir = tmp_path / "review"

    assert _review(packet_path, decisions_path, output_dir) == 0

    assert _stdout(capsys)["overlay"] is None
    assert [path.name for path in output_dir.iterdir()] == [TAKEOFF_PACKET_FILENAME]


def test_review_takeoff_refuses_a_second_decision_over_the_same_item(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    extracted = tmp_path / "extract"
    assert _extract(extracted) == 0
    _stdout(capsys)
    packet_path = extracted / TAKEOFF_PACKET_FILENAME
    decisions_path = _write_decisions(
        tmp_path / _DECISIONS_FILENAME, load_takeoff_packet(packet_path)
    )
    reviewed_dir = tmp_path / "review"
    assert _review(packet_path, decisions_path, reviewed_dir) == 0
    _stdout(capsys)
    second_dir = tmp_path / "review-again"

    exit_code = _review(reviewed_dir / TAKEOFF_PACKET_FILENAME, decisions_path, second_dir)

    assert exit_code == 2
    assert _stdout(capsys)["refused"] == "TAKEOFF_ITEM_ALREADY_REVIEWED"
    assert _is_empty(second_dir)


def test_review_takeoff_refuses_a_decision_for_an_unknown_item(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    extracted = tmp_path / "extract"
    assert _extract(extracted) == 0
    _stdout(capsys)
    packet_path = extracted / TAKEOFF_PACKET_FILENAME
    decisions_path = _write_decisions(
        tmp_path / _DECISIONS_FILENAME,
        load_takeoff_packet(packet_path),
        item_ids=["ti_ffffffffffffffff"],
        quantity=Decimal("1.00"),
    )
    output_dir = tmp_path / "review"

    exit_code = _review(packet_path, decisions_path, output_dir)

    assert exit_code == 2
    assert _stdout(capsys)["refused"] == "TAKEOFF_DECISION_UNKNOWN_ITEM"
    assert _is_empty(output_dir)


def test_review_takeoff_refuses_an_image_that_is_not_the_plate_of_the_packet(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Overlay de outra imagem mentiria sobre onde o número foi lido: recusa antes de gravar."""
    extracted = tmp_path / "extract"
    assert _extract(extracted) == 0
    _stdout(capsys)
    packet_path = extracted / TAKEOFF_PACKET_FILENAME
    decisions_path = _write_decisions(
        tmp_path / _DECISIONS_FILENAME, load_takeoff_packet(packet_path)
    )
    tampered = extracted / PLATE_IMAGE_FILENAME
    tampered.write_bytes(tampered.read_bytes() + b"\x00")
    output_dir = tmp_path / "review"

    exit_code = _review(packet_path, decisions_path, output_dir, tampered)

    assert exit_code == 2
    assert _stdout(capsys)["refused"] == "TAKEOFF_OVERLAY_DIGEST_MISMATCH"
    assert _is_empty(output_dir)


def test_review_takeoff_refuses_a_batch_outside_the_contract(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    extracted = tmp_path / "extract"
    assert _extract(extracted) == 0
    _stdout(capsys)
    decisions_path = tmp_path / _DECISIONS_FILENAME
    decisions_path.write_text(json.dumps({"decisions": []}), encoding="utf-8")
    output_dir = tmp_path / "review"

    exit_code = _review(extracted / TAKEOFF_PACKET_FILENAME, decisions_path, output_dir)

    assert exit_code == 2
    assert _stdout(capsys)["refused"] == "MODEL_VALIDATION_FAILED"
    assert _is_empty(output_dir)


def test_takeoff_demo_closes_the_review_with_a_traceable_decision(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    output_dir = tmp_path / "demo"

    exit_code = main(["takeoff-demo", "--output", str(output_dir)])

    assert exit_code == 0
    payload = _stdout(capsys)
    assert payload["review_status"] == "complete"
    assert payload["pending"] == 0
    assert payload["confirmed"] == len(SYNTHETIC_LEGEND_ROWS)
    assert payload["proposed_pending"] == len(SYNTHETIC_LEGEND_ROWS)
    packet = load_takeoff_packet(output_dir / TAKEOFF_PACKET_FILENAME)
    assert packet.pending_items() == []
    assert all(
        item.decision is not None and item.decision.reviewer_id == "orcamentista-sintetico"
        for item in packet.items
    )
    ambiguous_now_confirmed = next(
        item for item in packet.items if item.label == "PISO EMBORRACHADO SINTETICO"
    )
    assert ambiguous_now_confirmed.status is TakeoffItemStatus.CONFIRMED
    assert ambiguous_now_confirmed.quantity == Decimal("18.40")
    for filename in (
        PLATE_PDF_FILENAME,
        PLATE_IMAGE_FILENAME,
        TAKEOFF_DECISIONS_FILENAME,
        TAKEOFF_PACKET_FILENAME,
        TAKEOFF_OVERLAY_FILENAME,
    ):
        assert (output_dir / filename).is_file()


def test_takeoff_demo_decisions_can_be_replayed_by_hand(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """O lote gravado é o que fechou a revisão: `review-takeoff` o reaplica na extração."""
    demo_dir = tmp_path / "demo"
    assert main(["takeoff-demo", "--output", str(demo_dir)]) == 0
    _stdout(capsys)
    extracted = tmp_path / "extract"
    assert _extract(extracted) == 0
    _stdout(capsys)
    output_dir = tmp_path / "review"

    exit_code = _review(
        extracted / TAKEOFF_PACKET_FILENAME,
        demo_dir / TAKEOFF_DECISIONS_FILENAME,
        output_dir,
        extracted / PLATE_IMAGE_FILENAME,
    )

    assert exit_code == 0
    assert _stdout(capsys)["review_status"] == "complete"


def test_takeoff_eval_exits_zero_and_publishes_the_report(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    output_dir = tmp_path / "eval"

    exit_code = main(["takeoff-eval", "--output", str(output_dir)])

    assert exit_code == 0
    payload = _stdout(capsys)
    assert payload["passed"] is True
    assert payload["legend_recall"] == 1.0
    assert (output_dir / "takeoff-eval.json").is_file()
