"""A praça de várias folhas na `/v1` (F-046 T3, ADR-0057).

Duas coisas são provadas aqui, e a primeira manda na segunda:

- **A rodada gravada no formato antigo continua a mesma coisa.** A prancha escalar vira a
  primeira folha da praça pela migração, com a `plate_id` que o pacote já declarava, e a
  partir dela o consolidado e o boletim saem idênticos aos de hoje. Sem isso, tudo o mais
  desta feature seria uma praça nova ao lado da rodada que o cliente já tem.
- **A praça de duas folhas soma por composição e só funde por declaração.** O consolidado
  referencia os pacotes por digest, item repetido entre folhas conta duas vezes até alguém
  declarar, e a declaração carimba autor e instante do lado do SERVIDOR — nunca do corpo.
"""

from __future__ import annotations

import importlib.util
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, cast

from fastapi.testclient import TestClient
from sqlalchemy import select

from croquito_api import valuation_rounds
from croquito_api.database import (
    Database,
    UploadRecord,
    ValuationRoundPlateRecord,
    ValuationRoundRecord,
    ValuationRoundRevisionRecord,
)
from croquito_api.valuation_rounds import (
    document_digest,
    head_revision,
    require_worksite_takeoff,
    round_plates,
    worksite_packets,
)
from croquito_core.ids import new_uuid7
from croquito_valuation.assignment import (
    CodeAssignment,
    CodeAssignmentSet,
    ItemPackageClosure,
)
from croquito_valuation.calc import build_worksite_valuation
from croquito_valuation.models import (
    PriceCatalog,
    PriceCatalogEntry,
    ReviewerDecision,
)
from croquito_valuation.takeoff import (
    PlateBox,
    PlateEvidence,
    TakeoffItem,
    TakeoffItemStatus,
    TakeoffPacket,
)
from croquito_valuation.worksite_calc import (
    WorksitePlateInput,
    build_worksite_takeoff_valuation,
)
from croquito_valuation.worksite_takeoff import build_worksite_takeoff
from tests.api.test_valuation_round_routes import (
    _TENANT,
    _associate_plate,
    _client,
    _create_round,
    _database,
    _headers,
)

_REVIEWER = "orcamentista-sintetica"
_CODE = "AD04050050(/)"
_PRICE = Decimal("89.30")
_CATALOG_DIGEST = "c" * 64
_PDF_DIGEST = "d" * 64
_DECIDED_AT = datetime(2026, 2, 1, 12, 0, tzinfo=UTC)

# O MESMO id de item nas duas folhas de propósito: `ti_...` só é único dentro do pacote, e
# toda resolução da praça é pelo par `(plate_id, item_id)` (ADR-0057, decisão 5).
_ITEM = "ti_00000000000000a1"
_ITEM_OUTRO = "ti_00000000000000a2"


def _decision(action: str = "confirm") -> ReviewerDecision:
    return ReviewerDecision(
        decision_id="vd_0123456789abcdef",
        action=cast(Any, action),
        reviewer_id=_REVIEWER,
        reviewer_role="orcamentista",
        decided_at=_DECIDED_AT,
    )


def _item(
    *,
    plate_id: str,
    image_sha256: str,
    item_id: str = _ITEM,
    quantity: Decimal = Decimal("200.00"),
) -> TakeoffItem:
    return TakeoffItem(
        id=item_id,
        evidence=PlateEvidence(
            plate_id=plate_id,
            page_number=1,
            image_sha256=image_sha256,
            bbox=PlateBox(left=10, top=10, right=110, bottom=60),
        ),
        raw_text=f"PISO INTERTRAVADO SINTETICO {quantity} m2",
        label="PISO INTERTRAVADO SINTETICO",
        quantity=quantity,
        unit="m2",
        source="legend_extraction",
        extractor="legend-extractor-sintetico",
        extractor_version="1.0.0",
        status=TakeoffItemStatus.CONFIRMED,
        decision=_decision(),
    )


def _packet(
    plate_id: str, *, image_sha256: str, items: list[TakeoffItem] | None = None
) -> TakeoffPacket:
    return TakeoffPacket(
        plate_id=plate_id,
        page_number=1,
        image_sha256=image_sha256,
        source_pdf_sha256=_PDF_DIGEST,
        items=items or [_item(plate_id=plate_id, image_sha256=image_sha256)],
        safety_notes=[
            "Extração automática da legenda; quantidade não confirmada.",
            "Decisão do orçamentista obrigatória antes de qualquer boletim.",
        ],
    )


def _catalog() -> PriceCatalog:
    return PriceCatalog(
        source_label="CATALOGO SINTETICO",
        reference_month="2026-01",
        source_sha256=_CATALOG_DIGEST,
        entries=[
            PriceCatalogEntry(
                code=_CODE,
                description="PISO INTERTRAVADO SINTETICO 6CM",
                unit="m2",
                unit_price=_PRICE,
                family_code="AD",
                family_name="SERVICOS SINTETICOS",
                subgroup_code="AD0405",
                subgroup_name="ITENS SINTETICOS",
            )
        ],
    )


def _assignments(packet: TakeoffPacket) -> CodeAssignmentSet:
    return CodeAssignmentSet(
        plate_id=packet.plate_id,
        page_number=packet.page_number,
        image_sha256=packet.image_sha256,
        catalog_sha256=_CATALOG_DIGEST,
        assignments=[
            CodeAssignment(
                item_id=item.id,
                status="confirmed",
                code=_CODE,
                unit_compatible=True,
                decision=_decision(),
            )
            for item in packet.items
        ],
        closures=[
            ItemPackageClosure(item_id=item.id, decision=_decision()) for item in packet.items
        ],
        safety_notes=[
            "Confirmação de código é ato humano rastreável; a sugestão lexical nunca "
            "confirma sozinha.",
            "Preço e unidade impressos continuam sendo conferidos contra catálogo e "
            "contrato no portão de exportação.",
        ],
    )


# --------------------------------------------------------------------------------------
# a folha que a migração preserva
# --------------------------------------------------------------------------------------


def _migration_module() -> Any:
    """Carrega a revisão `0023` pelo caminho: o nome do módulo começa com dígito.

    O teste chama o backfill DA MIGRAÇÃO, e não uma cópia dele: um backfill reimplementado
    aqui provaria que o teste sabe migrar, e não que a migração sabe.
    """
    versions = Path(valuation_rounds.__file__).parent / "migrations" / "versions"
    path = versions / "0024_worksite_plates.py"
    spec = importlib.util.spec_from_file_location("croquito_migration_0023", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _round_no_formato_antigo(
    session: Any, *, packet: TakeoffPacket
) -> tuple[ValuationRoundRecord, ValuationRoundRevisionRecord]:
    """Uma rodada como ela era gravada antes da F-046: prancha em colunas escalares."""
    upload_id = str(new_uuid7())
    session.add(
        UploadRecord(
            id=upload_id,
            tenant_id=_TENANT,
            object_key=f"tenants/{_TENANT}/uploads/{upload_id}/prancha.pdf",
            filename="prancha.pdf",
            content_type="application/pdf",
            size_bytes=2048,
            sha256=_PDF_DIGEST,
        )
    )
    round_id = str(new_uuid7())
    record = ValuationRoundRecord(
        id=round_id,
        tenant_id=_TENANT,
        worksite_key="praca-sintetica-norte",
        worksite_name="PRACA NORTE",
        reference_label="MEDICAO 01/2026",
        period_number=1,
        status="OPEN",
        version=3,
        catalog_upload_id=upload_id,
        catalog_object_key=f"tenants/{_TENANT}/uploads/{upload_id}/catalogo.json",
        catalog_source_sha256=_CATALOG_DIGEST,
        catalog_summary_json={},
        plate_upload_id=upload_id,
        plate_object_key=f"tenants/{_TENANT}/valuation-rounds/{round_id}/plate/origem.pdf",
        plate_source_sha256=_PDF_DIGEST,
        plate_page_count=1,
        created_by=_REVIEWER,
    )
    session.add(record)
    revision = ValuationRoundRevisionRecord(
        id=str(new_uuid7()),
        tenant_id=_TENANT,
        round_id=round_id,
        version=1,
        created_by="valuation-extraction-v1",
        takeoff_packet_json=packet.model_dump(mode="json"),
        artifact_refs_json={},
        artifact_digests_json={},
    )
    session.add(revision)
    session.commit()
    return record, revision


def test_a_migracao_preserva_a_prancha_como_a_primeira_folha_da_praca(tmp_path: Path) -> None:
    """Critério 1: a folha escalar vira linha filha, com a `plate_id` que o pacote declarava.

    A `plate_id` sai do PACOTE e não de um nome derivado: é ela que amarra a folha ao
    consolidado e ao endereço `(plate_id, item_id)`, e ler do pacote é o que faz a rodada
    cuja extração cunhou outro rótulo continuar coerente depois de migrada.
    """
    database = Database(f"sqlite+pysqlite:///{tmp_path / 'migracao.db'}")
    database.create_schema()
    packet = _packet("rodada-legada-de-outro-nome", image_sha256="a" * 64)
    with database.sessions() as session:
        record, _ = _round_no_formato_antigo(session, packet=packet)
        round_id = record.id

    with database.engine.begin() as connection:
        criadas = _migration_module().backfill_round_plates(connection)
    assert criadas == 1

    with database.sessions() as session:
        plates = round_plates(session, round_id=round_id, tenant_id=_TENANT)
        assert len(plates) == 1
        folha = plates[0]
        assert folha.plate_id == "rodada-legada-de-outro-nome"
        assert folha.position == 1
        assert folha.page_number == 1
        assert folha.source_sha256 == _PDF_DIGEST
        assert folha.object_key.endswith("origem.pdf")
        assert folha.upload_id is not None


def test_a_migracao_e_idempotente_e_nao_inventa_folha(tmp_path: Path) -> None:
    """Reaplicar num banco meio migrado não duplica folha, e rodada sem prancha não ganha uma."""
    database = Database(f"sqlite+pysqlite:///{tmp_path / 'idempotente.db'}")
    database.create_schema()
    packet = _packet("rodada-legada", image_sha256="a" * 64)
    with database.sessions() as session:
        record, _ = _round_no_formato_antigo(session, packet=packet)
        # Rodada aberta e sem prancha nenhuma: a migração não pode fabricar folha para ela.
        sem_prancha = ValuationRoundRecord(
            id=str(new_uuid7()),
            tenant_id=_TENANT,
            worksite_key="praca-sintetica-sul",
            worksite_name="PRACA SUL",
            reference_label="MEDICAO 01/2026",
            period_number=1,
            status="OPEN",
            version=1,
            catalog_upload_id=record.catalog_upload_id,
            catalog_object_key=record.catalog_object_key,
            catalog_source_sha256=_CATALOG_DIGEST,
            catalog_summary_json={},
            created_by=_REVIEWER,
        )
        session.add(sem_prancha)
        session.commit()

    module = _migration_module()
    with database.engine.begin() as connection:
        assert module.backfill_round_plates(connection) == 1
    with database.engine.begin() as connection:
        assert module.backfill_round_plates(connection) == 0

    with database.sessions() as session:
        assert len(session.scalars(select(ValuationRoundPlateRecord)).all()) == 1


def test_a_rodada_migrada_produz_o_mesmo_consolidado_e_o_mesmo_boletim(tmp_path: Path) -> None:
    """Critério 2, sobre dado gravado no formato antigo.

    O boletim não é comparado com um retrato gravado, e sim com o builder de HOJE
    (`calc.build_worksite_valuation`) rodando lado a lado sobre o mesmo pacote: é assim que
    uma mudança futura no caminho de uma folha tem de mover as duas cadeias juntas.
    """
    database = Database(f"sqlite+pysqlite:///{tmp_path / 'nao-regressao.db'}")
    database.create_schema()
    packet = _packet("rodada-legada", image_sha256="a" * 64)
    with database.sessions() as session:
        record, _ = _round_no_formato_antigo(session, packet=packet)
        round_id = record.id
    with database.engine.begin() as connection:
        _migration_module().backfill_round_plates(connection)

    with database.sessions() as session:
        migrada = session.get(ValuationRoundRecord, round_id)
        assert migrada is not None
        revision = head_revision(session, round_id=round_id, tenant_id=_TENANT)
        plates = round_plates(session, round_id=round_id, tenant_id=_TENANT)
        consolidado = require_worksite_takeoff(migrada, revision, plates)

    assert consolidado == build_worksite_takeoff(record.worksite_key, [packet])
    assert [p.plate_id for p in consolidado.plates] == [packet.plate_id]
    assert consolidado.identity_links == []

    catalog = _catalog()
    da_praca = build_worksite_takeoff_valuation(
        consolidado,
        [WorksitePlateInput(packet=packet, assignments=_assignments(packet))],
        catalog,
        worksite_name=record.worksite_name,
        period_number=record.period_number,
        reference_label=record.reference_label,
    )
    de_hoje = build_worksite_valuation(
        packet,
        _assignments(packet),
        catalog,
        worksite_key=record.worksite_key,
        worksite_name=record.worksite_name,
        period_number=record.period_number,
        reference_label=record.reference_label,
    )
    assert da_praca.model_dump(mode="json", exclude={"id"}) == de_hoje.model_dump(
        mode="json", exclude={"id"}
    )
    # O `id` é UUIDv7 novo a cada build; alinhados, os dois digests têm de coincidir.
    alinhado = de_hoje.model_copy(update={"id": da_praca.id})
    assert alinhado.content_digest() == da_praca.content_digest()


# --------------------------------------------------------------------------------------
# a praça na `/v1`
# --------------------------------------------------------------------------------------


def _praca_de_duas_folhas(client: TestClient) -> dict[str, Any]:
    """Rodada com duas folhas e o pacote de cada uma publicado, como a T4 fará.

    Os pacotes são escritos direto na revisão porque a extração é PAGA e é trabalho da T4:
    exercitá-la aqui faria o teste da praça depender do braço do provider.
    """
    created = _create_round(client)
    round_id = created["round_id"]
    assert _associate_plate(client, round_id).status_code == 200
    assert _associate_plate(client, round_id, base_version=2, key="folha-2").status_code == 200
    with _database(client).sessions() as session:
        plates = round_plates(session, round_id=round_id, tenant_id=_TENANT)
        primeira, segunda = plates[0].plate_id, plates[1].plate_id
        packet_a = _packet(primeira, image_sha256="a" * 64)
        packet_b = _packet(
            segunda,
            image_sha256="b" * 64,
            items=[
                # MESMO `item_id` da folha A, e é o par `(plate_id, item_id)` que separa os dois.
                _item(plate_id=segunda, image_sha256="b" * 64, quantity=Decimal("50.00")),
                _item(
                    plate_id=segunda,
                    image_sha256="b" * 64,
                    item_id=_ITEM_OUTRO,
                    quantity=Decimal("30.00"),
                ),
            ],
        )
        record = session.get(ValuationRoundRecord, round_id)
        assert record is not None
        session.add(
            ValuationRoundRevisionRecord(
                id=str(new_uuid7()),
                tenant_id=_TENANT,
                round_id=round_id,
                version=1,
                created_by="valuation-extraction-v1",
                takeoff_packet_json=packet_a.model_dump(mode="json"),
                worksite_plate_packets_json={segunda: packet_b.model_dump(mode="json")},
                artifact_refs_json={},
                artifact_digests_json={},
            )
        )
        record.version += 1
        session.commit()
        version = record.version
    return {
        "round_id": round_id,
        "version": version,
        "plate_a": primeira,
        "plate_b": segunda,
        "packet_a": packet_a,
        "packet_b": packet_b,
    }


def test_a_praca_sem_folha_extraida_nao_fecha_e_diz_qual_falta(tmp_path: Path) -> None:
    """Critério 4: leitura tolerante — a praça pendente é estado declarado, não erro."""
    client = _client(tmp_path)
    created = _create_round(client)
    assert _associate_plate(client, created["round_id"]).status_code == 200

    response = client.get(
        f"/v1/valuation-rounds/{created['round_id']}/worksite", headers=_headers()
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert len(body["plates"]) == 1
    assert body["plates"][0]["takeoff_present"] is False
    assert body["plates"][0]["position"] == 1
    assert body["consolidated"]["present"] is False
    assert body["consolidated"]["pending_plate_ids"] == [body["plates"][0]["plate_id"]]
    assert body["consolidated"]["refusal_code"] == "ROUND_STAGE_NOT_READY"
    assert body["plate_limit"] == valuation_rounds.WORKSITE_PLATE_LIMIT


def test_a_praca_de_duas_folhas_referencia_os_dois_pacotes_por_digest(tmp_path: Path) -> None:
    """Critério 4: o consolidado é a lista das folhas, cada uma pelo digest do pacote dela."""
    client = _client(tmp_path)
    praca = _praca_de_duas_folhas(client)

    body = client.get(
        f"/v1/valuation-rounds/{praca['round_id']}/worksite", headers=_headers()
    ).json()

    assert [folha["plate_id"] for folha in body["plates"]] == [praca["plate_a"], praca["plate_b"]]
    assert all(folha["takeoff_present"] for folha in body["plates"])
    assert body["plates"][1]["item_count"] == 2
    consolidado = body["consolidated"]
    assert consolidado["present"] is True
    assert consolidado["pending_plate_ids"] == []
    esperado = build_worksite_takeoff(
        "praca-sintetica-norte", [praca["packet_a"], praca["packet_b"]]
    )
    assert consolidado["document"] == esperado.model_dump(mode="json")
    assert consolidado["worksite_takeoff_sha256"] == document_digest(
        esperado.model_dump(mode="json")
    )


def test_declarar_identidade_cria_revisao_nova_com_autor_e_instante_do_servidor(
    tmp_path: Path,
) -> None:
    """Critério 5: a declaração é ato humano, append-only, e o corpo não carimba procedência."""
    client = _client(tmp_path)
    praca = _praca_de_duas_folhas(client)

    response = client.post(
        f"/v1/valuation-rounds/{praca['round_id']}/worksite/identity-links",
        headers=_headers(key="vinculo-1"),
        json={
            "base_version": praca["version"],
            "kept": {"plate_id": praca["plate_a"], "item_id": _ITEM},
            "discarded": {"plate_id": praca["plate_b"], "item_id": _ITEM},
            "note": "mesma quadra na planta geral e no detalhe",
        },
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["version"] == praca["version"] + 1
    assert len(body["identity_links"]) == 1
    vinculo = body["identity_links"][0]
    assert vinculo["declared_by"] == "orcamentista-sintetica"
    assert vinculo["kept"] == {"plate_id": praca["plate_a"], "item_id": _ITEM}
    assert vinculo["discarded"] == {"plate_id": praca["plate_b"], "item_id": _ITEM}
    assert vinculo["note"] == "mesma quadra na planta geral e no detalhe"
    assert datetime.fromisoformat(vinculo["declared_at"]).tzinfo is not None
    assert body["consolidated"]["document"]["identity_links"] == [vinculo]

    with _database(client).sessions() as session:
        revisoes = session.scalars(
            select(ValuationRoundRevisionRecord)
            .where(ValuationRoundRevisionRecord.round_id == praca["round_id"])
            .order_by(ValuationRoundRevisionRecord.version)
        ).all()
        # Append-only: a revisão anterior continua sem vínculo nenhum.
        assert [r.version for r in revisoes] == [1, 2]
        assert revisoes[0].worksite_identity_links_json is None
        assert revisoes[1].worksite_identity_links_json is not None
        # O pacote da segunda folha viajou para a revisão nova sem ser tocado.
        assert set(worksite_packets(revisoes[1])) == {praca["plate_a"], praca["plate_b"]}


def test_o_corpo_nao_pode_carimbar_quem_declarou(tmp_path: Path) -> None:
    """Procedência é do servidor: um corpo que tente declará-la é recusado, não ignorado.

    Ignorar em silêncio deixaria quem chama acreditando que carimbou o que não carimbou.
    """
    client = _client(tmp_path)
    praca = _praca_de_duas_folhas(client)

    response = client.post(
        f"/v1/valuation-rounds/{praca['round_id']}/worksite/identity-links",
        headers=_headers(key="vinculo-forjado"),
        json={
            "base_version": praca["version"],
            "kept": {"plate_id": praca["plate_a"], "item_id": _ITEM},
            "discarded": {"plate_id": praca["plate_b"], "item_id": _ITEM},
            "note": "procedência forjada",
            "declared_by": "quem-nao-declarou",
            "declared_at": "2020-01-01T00:00:00+00:00",
        },
    )

    assert response.status_code == 422
    with _database(client).sessions() as session:
        assert len(session.scalars(select(ValuationRoundRevisionRecord)).all()) == 1


def test_o_vinculo_dentro_da_mesma_folha_recusa_com_o_codigo_do_dominio(tmp_path: Path) -> None:
    """Critério 6: a recusa da T1 chega ao cliente em problem+json, nunca como 500."""
    client = _client(tmp_path)
    praca = _praca_de_duas_folhas(client)

    response = client.post(
        f"/v1/valuation-rounds/{praca['round_id']}/worksite/identity-links",
        headers=_headers(key="vinculo-mesma-folha"),
        json={
            "base_version": praca["version"],
            "kept": {"plate_id": praca["plate_b"], "item_id": _ITEM},
            "discarded": {"plate_id": praca["plate_b"], "item_id": _ITEM_OUTRO},
            "note": "duas leituras da mesma folha",
        },
    )

    assert response.status_code == 422
    detail = response.json()["detail"]
    assert detail["code"] == "DOMAIN_VALIDATION_FAILED"
    assert detail["details"]["code"] == "WORKSITE_LINK_SAME_PLATE"
    with _database(client).sessions() as session:
        record = session.get(ValuationRoundRecord, praca["round_id"])
        assert record is not None
        assert record.version == praca["version"]
        assert len(session.scalars(select(ValuationRoundRevisionRecord)).all()) == 1


def test_o_vinculo_para_item_inexistente_recusa_sem_gravar(tmp_path: Path) -> None:
    """O endereço é conferido contra o pacote REAL da folha, não contra o formato do id."""
    client = _client(tmp_path)
    praca = _praca_de_duas_folhas(client)

    response = client.post(
        f"/v1/valuation-rounds/{praca['round_id']}/worksite/identity-links",
        headers=_headers(key="vinculo-fantasma"),
        json={
            "base_version": praca["version"],
            "kept": {"plate_id": praca["plate_a"], "item_id": _ITEM},
            "discarded": {"plate_id": praca["plate_b"], "item_id": "ti_00000000000000ff"},
            "note": "item que não existe",
        },
    )

    assert response.status_code == 422
    assert response.json()["detail"]["details"]["code"] == "WORKSITE_LINK_UNKNOWN_TARGET"


def test_declarar_identidade_com_folha_sem_pacote_e_etapa_fora_de_ordem(tmp_path: Path) -> None:
    """Fail-closed: não se declara identidade sobre uma praça que ninguém terminou de ler."""
    client = _client(tmp_path)
    created = _create_round(client)
    assert _associate_plate(client, created["round_id"]).status_code == 200

    response = client.post(
        f"/v1/valuation-rounds/{created['round_id']}/worksite/identity-links",
        headers=_headers(key="vinculo-cedo"),
        json={
            "base_version": 2,
            "kept": {"plate_id": "rodada-a", "item_id": _ITEM},
            "discarded": {"plate_id": "rodada-b", "item_id": _ITEM},
            "note": "cedo demais",
        },
    )

    assert response.status_code == 409
    detail = response.json()["detail"]
    assert detail["code"] == "ROUND_STAGE_NOT_READY"
    assert detail["details"]["stage"] == "worksite"
    assert detail["details"]["pending_plate_ids"] == [f"rodada-{created['round_id']}"]


def test_a_declaracao_repetida_com_a_mesma_chave_devolve_a_mesma_resposta(
    tmp_path: Path,
) -> None:
    """Idempotência: repetir o comando não declara duas vezes nem move a versão de novo."""
    client = _client(tmp_path)
    praca = _praca_de_duas_folhas(client)
    corpo = {
        "base_version": praca["version"],
        "kept": {"plate_id": praca["plate_a"], "item_id": _ITEM},
        "discarded": {"plate_id": praca["plate_b"], "item_id": _ITEM},
        "note": "mesma quadra na planta geral e no detalhe",
    }
    primeira = client.post(
        f"/v1/valuation-rounds/{praca['round_id']}/worksite/identity-links",
        headers=_headers(key="vinculo-idem"),
        json=corpo,
    )
    assert primeira.status_code == 200, primeira.text

    repetida = client.post(
        f"/v1/valuation-rounds/{praca['round_id']}/worksite/identity-links",
        headers=_headers(key="vinculo-idem"),
        json=corpo,
    )

    assert repetida.status_code == 200
    assert repetida.json() == primeira.json()
    with _database(client).sessions() as session:
        record = session.get(ValuationRoundRecord, praca["round_id"])
        assert record is not None
        assert record.version == praca["version"] + 1


def test_base_version_divergente_recusa_a_declaracao_sem_gravar(tmp_path: Path) -> None:
    client = _client(tmp_path)
    praca = _praca_de_duas_folhas(client)

    response = client.post(
        f"/v1/valuation-rounds/{praca['round_id']}/worksite/identity-links",
        headers=_headers(key="vinculo-conflito"),
        json={
            "base_version": praca["version"] + 7,
            "kept": {"plate_id": praca["plate_a"], "item_id": _ITEM},
            "discarded": {"plate_id": praca["plate_b"], "item_id": _ITEM},
            "note": "versão que já andou",
        },
    )

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "REVISION_CONFLICT"
    with _database(client).sessions() as session:
        assert len(session.scalars(select(ValuationRoundRevisionRecord)).all()) == 1


def test_a_praca_de_outro_tenant_e_inexistente(tmp_path: Path) -> None:
    """IDOR: rodada de outro tenant é `404`, nunca `403` — nem na leitura, nem na declaração."""
    client = _client(tmp_path)
    praca = _praca_de_duas_folhas(client)
    outro = "tenant-vizinho"

    leitura = client.get(
        f"/v1/valuation-rounds/{praca['round_id']}/worksite", headers=_headers(outro)
    )
    declaracao = client.post(
        f"/v1/valuation-rounds/{praca['round_id']}/worksite/identity-links",
        headers=_headers(outro, key="vinculo-vizinho"),
        json={
            "base_version": praca["version"],
            "kept": {"plate_id": praca["plate_a"], "item_id": _ITEM},
            "discarded": {"plate_id": praca["plate_b"], "item_id": _ITEM},
            "note": "praça que não é dele",
        },
    )

    assert leitura.status_code == 404
    assert declaracao.status_code == 404


def test_a_praca_exige_o_papel_de_orcamentista(tmp_path: Path) -> None:
    client = _client(tmp_path)
    praca = _praca_de_duas_folhas(client)

    response = client.get(
        f"/v1/valuation-rounds/{praca['round_id']}/worksite",
        headers=_headers(roles="engineer"),
    )

    assert response.status_code == 403


def test_a_praca_de_uma_folha_continua_respondendo_como_hoje(tmp_path: Path) -> None:
    """Critério 10: N=1 é o caso da vida real, e nada nele muda de forma."""
    client = _client(tmp_path)
    created = _create_round(client)
    assert _associate_plate(client, created["round_id"]).status_code == 200

    prancha = client.get(
        f"/v1/valuation-rounds/{created['round_id']}/plate", headers=_headers()
    ).json()
    estado = client.get(f"/v1/valuation-rounds/{created['round_id']}", headers=_headers()).json()

    assert prancha["page_count"] is None
    assert prancha["image_url"] is None
    assert estado["plate"]["present"] is True
    assert estado["plate"]["page_count"] is None
    assert estado["worksite"]["plate_count"] == 1
    assert estado["worksite"]["identity_link_count"] == 0
    listagem = client.get("/v1/valuation-rounds", headers=_headers()).json()
    assert listagem["items"][0]["stage"] == "plate"
