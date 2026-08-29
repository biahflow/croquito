"""Núcleo de aplicação da rodada de medição, exercitado sem subir a aplicação.

O módulo existe justamente para ser testável assim: se algum destes testes precisasse de
`TestClient`, a lógica teria vazado para a rota. Dois testes são estruturais e olham o
código-fonte — a ausência de HTTP e o `tenant_id` no mesmo `where` do `id` — porque são
invariantes que a próxima rota pode quebrar sem quebrar teste de comportamento nenhum.
"""

from __future__ import annotations

import ast
import hashlib
import inspect
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, Literal

import pytest
from sqlalchemy.orm import Session

from croquito_api import valuation_rounds
from croquito_api.database import (
    Database,
    UploadRecord,
    ValuationRoundPlateRecord,
    ValuationRoundRecord,
    ValuationRoundRevisionRecord,
)
from croquito_api.valuation_rounds import (
    CATALOG_MAX_BYTES,
    WORKSITE_PLATE_LIMIT,
    CatalogCache,
    RoundRefusal,
    append_revision,
    append_round_plate,
    assignments_of,
    current_stage,
    document_digest,
    head_revision,
    load_catalog,
    load_round,
    require_assignments,
    require_base_version,
    require_document,
    require_plate,
    require_plate_object_key,
    require_takeoff_packet,
    round_plates,
    round_state_payload,
    signed_artifact_url,
)
from croquito_core.ids import new_uuid7
from croquito_valuation.assignment import (
    CodeAssignment,
    CodeAssignmentSet,
    ItemPackageClosure,
)
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

_TENANT = "tenant-a"
_OTHER_TENANT = "tenant-b"
_REVIEWER = "orcamentista-sintetico"
_PLATE_ID = "praca-sintetica-norte-prancha-01"
_IMAGE_DIGEST = "a" * 64
_PDF_DIGEST = "b" * 64
_ITEM_1 = "ti_0000000000000001"
_ITEM_2 = "ti_0000000000000002"
_DECIDED_AT = datetime(2026, 8, 17, 12, 0, tzinfo=UTC)


# --- fixtures sintéticas ---------------------------------------------------------------


def _catalog(*, source_label: str = "CATALOGO SINTETICO") -> PriceCatalog:
    return PriceCatalog(
        source_label=source_label,
        reference_month="2026-01",
        source_sha256="c" * 64,
        entries=[
            PriceCatalogEntry(
                code="CE04100010(/)",
                description="ALAMBRADO GALVANIZADO",
                unit="m",
                unit_price=Decimal("50.00"),
                family_code="CE",
                family_name="SERVICOS SINTETICOS",
                subgroup_code="CE0410",
                subgroup_name="ITENS SINTETICOS",
            )
        ],
    )


def _catalog_bytes(catalog: PriceCatalog) -> bytes:
    return catalog.model_dump_json().encode("utf-8")


def _item(
    *,
    item_id: str = _ITEM_1,
    label: str = "ALAMBRADO GALVANIZADO",
    status: TakeoffItemStatus = TakeoffItemStatus.CONFIRMED,
) -> TakeoffItem:
    decided = status in (TakeoffItemStatus.CONFIRMED, TakeoffItemStatus.REJECTED)
    return TakeoffItem(
        id=item_id,
        evidence=PlateEvidence(
            plate_id=_PLATE_ID,
            page_number=1,
            image_sha256=_IMAGE_DIGEST,
            bbox=PlateBox(left=10, top=10, right=110, bottom=60),
        ),
        raw_text=f"{label} 10,00 m",
        label=label,
        quantity=Decimal("10.00"),
        unit="m",
        source="legend_extraction",
        extractor="legend-extractor-sintetico",
        extractor_version="1.0.0",
        status=status,
        decision=(
            ReviewerDecision(
                decision_id="vd_0123456789abcdef",
                action="confirm" if status is TakeoffItemStatus.CONFIRMED else "reject",
                reviewer_id=_REVIEWER,
                reviewer_role="orcamentista",
                decided_at=_DECIDED_AT,
            )
            if decided
            else None
        ),
    )


def _packet(items: list[TakeoffItem] | None = None) -> TakeoffPacket:
    return TakeoffPacket(
        plate_id=_PLATE_ID,
        page_number=1,
        image_sha256=_IMAGE_DIGEST,
        source_pdf_sha256=_PDF_DIGEST,
        items=items if items is not None else [_item()],
        safety_notes=[
            "Extração automática da legenda; quantidade não confirmada.",
            "Decisão do orçamentista obrigatória antes de qualquer boletim.",
        ],
    )


def _assignment_set(*, status: Literal["confirmed", "rejected"] = "confirmed") -> CodeAssignmentSet:
    decision = ReviewerDecision(
        decision_id="vd_0123456789abcdff",
        action="confirm" if status == "confirmed" else "reject",
        reviewer_id=_REVIEWER,
        reviewer_role="orcamentista",
        decided_at=_DECIDED_AT,
        note=None if status == "confirmed" else "item sem código no catálogo",
    )
    return CodeAssignmentSet(
        plate_id=_PLATE_ID,
        page_number=1,
        image_sha256=_IMAGE_DIGEST,
        catalog_sha256="c" * 64,
        assignments=[
            CodeAssignment(
                item_id=_ITEM_1,
                status=status,
                code="CE04100010(/)" if status == "confirmed" else None,
                unit_compatible=True,
                decision=decision,
            )
        ],
        # Fixture no regime de pacote (`2.0.0`): o item confirmado nasce com o pacote
        # FECHADO, que é o que a orçamentista faz quando o elemento dispara um serviço só.
        # A rejeição fecha o item sozinha e não leva fechamento declarado.
        closures=(
            [ItemPackageClosure(item_id=_ITEM_1, decision=decision)]
            if status == "confirmed"
            else []
        ),
        safety_notes=[
            "Confirmação de código é ato humano; sugestão não confirma nada.",
            "Código fora do catálogo instalado é recusado.",
        ],
    )


class _RecordingStore:
    """Dublê do object store que CONTA leituras e assinaturas.

    A contagem é o oráculo de dois critérios: o cache não pode reler o catálogo, e a chave
    fora do prefixo do tenant não pode sequer chegar ao presign.
    """

    def __init__(self, objects: dict[str, bytes] | None = None) -> None:
        self.objects: dict[str, bytes] = dict(objects or {})
        self.reads: list[str] = []
        self.signed: list[str] = []

    def read_object(self, *, object_key: str, max_bytes: int) -> bytes | None:
        self.reads.append(object_key)
        payload = self.objects.get(object_key)
        return None if payload is None else payload[: max_bytes + 1]

    def presign_private_read(self, *, object_key: str) -> str:
        self.signed.append(object_key)
        return f"https://storage.invalid/{object_key}?temporary=true"


def _database(tmp_path: Path) -> Database:
    database = Database(f"sqlite+pysqlite:///{tmp_path / 'rounds.db'}")
    database.create_schema()
    return database


def _plate(
    session: Session,
    record: ValuationRoundRecord,
    *,
    source_sha256: str = _PDF_DIGEST,
    page_number: int = 1,
) -> ValuationRoundPlateRecord:
    """Acrescenta uma folha à praça pelo mesmo caminho que a rota usa.

    Reaproveitar `append_round_plate` em vez de montar a linha à mão é o que faz o teste
    exercitar a cunhagem de `plate_id` e o espelho escalar, e não uma imitação deles.
    """
    plate = append_round_plate(
        session,
        round_record=record,
        plates=round_plates(session, round_id=record.id, tenant_id=record.tenant_id),
        # A coluna é chave estrangeira e o banco a cobra: o upload do catálogo é um upload
        # real deste tenant, e serve para o que este ajudante precisa provar.
        upload_id=record.catalog_upload_id or "",
        object_key=f"tenants/{record.tenant_id}/rounds/{record.id}/plate.pdf",
        source_sha256=source_sha256,
        created_by=_REVIEWER,
        page_number=page_number,
    )
    session.flush()
    return plate


def _round(
    session: Session,
    *,
    tenant_id: str = _TENANT,
    round_id: str | None = None,
    catalog_digest: str = "d" * 64,
    catalog_object_key: str | None = None,
) -> ValuationRoundRecord:
    identifier = round_id or str(new_uuid7())
    upload_id = str(new_uuid7())
    session.add(
        UploadRecord(
            id=upload_id,
            tenant_id=tenant_id,
            object_key=f"tenants/{tenant_id}/uploads/{upload_id}/catalog.json",
            filename="catalog.json",
            content_type="application/json",
            size_bytes=1024,
            sha256=catalog_digest,
        )
    )
    record = ValuationRoundRecord(
        id=identifier,
        tenant_id=tenant_id,
        worksite_key="praca-sintetica-norte",
        worksite_name="PRACA SINTETICA NORTE",
        reference_label="MEDICAO 01/2026",
        period_number=1,
        status="OPEN",
        version=1,
        catalog_upload_id=upload_id,
        catalog_object_key=(
            catalog_object_key or f"tenants/{tenant_id}/uploads/{upload_id}/catalog.json"
        ),
        catalog_source_sha256=catalog_digest,
        catalog_summary_json={"entries": 1},
        created_by=_REVIEWER,
    )
    session.add(record)
    session.flush()
    return record


# --- leitura da cabeça e escopo de tenant ----------------------------------------------


def test_a_cabeca_e_a_revisao_de_maior_versao(tmp_path: Path) -> None:
    database = _database(tmp_path)
    with database.sessions() as session:
        record = _round(session)
        first = append_revision(
            session,
            round_record=record,
            created_by=_REVIEWER,
            changes={"takeoff_packet_json": _packet().model_dump(mode="json")},
        )
        second = append_revision(
            session,
            round_record=record,
            created_by=_REVIEWER,
            changes={"code_assignments_json": _assignment_set().model_dump(mode="json")},
        )
        session.commit()

        head = head_revision(session, round_id=record.id, tenant_id=_TENANT)

        assert head is not None
        assert head.id == second.id
        assert (first.version, second.version) == (1, 2)


def test_rodada_de_outro_tenant_e_indistinguivel_de_ausente(tmp_path: Path) -> None:
    """IDOR: o id existe, o tenant não bate, e a resposta é a mesma de rodada inexistente."""
    database = _database(tmp_path)
    with database.sessions() as session:
        record = _round(session)
        append_revision(
            session,
            round_record=record,
            created_by=_REVIEWER,
            changes={"takeoff_packet_json": _packet().model_dump(mode="json")},
        )
        session.commit()

        assert load_round(session, round_id=record.id, tenant_id=_OTHER_TENANT) is None
        assert head_revision(session, round_id=record.id, tenant_id=_OTHER_TENANT) is None
        assert load_round(session, round_id=record.id, tenant_id=_TENANT) is not None


# --- append-only e os dois contadores --------------------------------------------------


def test_a_revisao_nova_carrega_o_que_o_ato_nao_mudou(tmp_path: Path) -> None:
    database = _database(tmp_path)
    with database.sessions() as session:
        record = _round(session)
        packet = _packet().model_dump(mode="json")
        first = append_revision(
            session,
            round_record=record,
            created_by=_REVIEWER,
            changes={
                "takeoff_packet_json": packet,
                "artifact_refs_json": {"plate": f"tenants/{_TENANT}/rounds/x/plate.pdf"},
            },
        )
        second = append_revision(
            session,
            round_record=record,
            created_by=_REVIEWER,
            changes={"code_assignments_json": _assignment_set().model_dump(mode="json")},
        )
        session.commit()

        assert second.takeoff_packet_json == packet
        assert second.artifact_refs_json == first.artifact_refs_json
        assert second.parent_revision_id == first.id
        # A linha anterior continua exatamente como foi gravada: append-only de verdade.
        assert first.code_assignments_json is None
        assert first.takeoff_packet_json is not second.takeoff_packet_json


def test_ato_humano_avanca_a_versao_da_rodada(tmp_path: Path) -> None:
    database = _database(tmp_path)
    with database.sessions() as session:
        record = _round(session)
        append_revision(
            session,
            round_record=record,
            created_by=_REVIEWER,
            changes={"takeoff_packet_json": _packet().model_dump(mode="json")},
        )
        session.commit()

        assert record.version == 2


def test_artefato_derivado_entra_na_cadeia_sem_mover_o_base_version(tmp_path: Path) -> None:
    """A shortlist é derivada: persistir não pode invalidar o `base_version` da tela.

    O contador da rodada é o token de concorrência (ADR-0028 D3) e só ato humano o move; a
    `version` da revisão é a posição na cadeia append-only e anda sempre — é o que permite
    gravar o derivado sem editar linha nenhuma no lugar.
    """
    database = _database(tmp_path)
    with database.sessions() as session:
        record = _round(session)
        append_revision(
            session,
            round_record=record,
            created_by=_REVIEWER,
            changes={"takeoff_packet_json": _packet().model_dump(mode="json")},
        )
        version_after_human_act = record.version

        derived = append_revision(
            session,
            round_record=record,
            created_by=_REVIEWER,
            changes={"code_suggestions_json": {"schema_version": "1.1.0"}},
            advance_version=False,
        )
        session.commit()

        assert record.version == version_after_human_act
        assert derived.version == 2
        assert derived.takeoff_packet_json is not None


def test_coluna_desconhecida_falha_alto(tmp_path: Path) -> None:
    database = _database(tmp_path)
    with database.sessions() as session:
        record = _round(session)

        with pytest.raises(ValueError, match="coluna de revisão desconhecida"):
            append_revision(
                session,
                round_record=record,
                created_by=_REVIEWER,
                changes={"scene_json": {}},
            )


def test_base_version_divergente_recusa_com_revision_conflict(tmp_path: Path) -> None:
    database = _database(tmp_path)
    with database.sessions() as session:
        record = _round(session)
        append_revision(
            session,
            round_record=record,
            created_by=_REVIEWER,
            changes={"takeoff_packet_json": _packet().model_dump(mode="json")},
        )
        session.commit()

        require_base_version(record, 2)
        with pytest.raises(RoundRefusal) as refusal:
            require_base_version(record, 1)

        assert refusal.value.code == "REVISION_CONFLICT"
        assert refusal.value.http_status == 409
        assert refusal.value.details == {"base_version": 1, "current_version": 2}


# --- guardas de etapa ------------------------------------------------------------------


def test_etapa_anterior_ausente_recusa_com_round_stage_not_ready(tmp_path: Path) -> None:
    database = _database(tmp_path)
    with database.sessions() as session:
        _round(session)
        session.commit()

        for guard in (
            lambda: require_takeoff_packet(None),
            lambda: require_assignments(None),
            lambda: require_plate_object_key([]),
            lambda: require_document(
                None, "valuation_json", stage="bulletin", detail="boletim não construído"
            ),
        ):
            with pytest.raises(RoundRefusal) as refusal:
                guard()
            assert refusal.value.code == "ROUND_STAGE_NOT_READY"
            assert refusal.value.http_status == 409


def test_a_guarda_de_documento_recusa_coluna_inexistente(tmp_path: Path) -> None:
    """Nome de coluna vem do código; errá-lo é defeito, não resposta de domínio."""
    with pytest.raises(ValueError, match="coluna de revisão desconhecida"):
        require_document(None, "scene_json", stage="bulletin", detail="boletim não construído")


def test_a_guarda_devolve_o_artefato_quando_a_etapa_existe(tmp_path: Path) -> None:
    database = _database(tmp_path)
    with database.sessions() as session:
        record = _round(session)
        revision = append_revision(
            session,
            round_record=record,
            created_by=_REVIEWER,
            changes={
                "takeoff_packet_json": _packet().model_dump(mode="json"),
                "code_assignments_json": _assignment_set().model_dump(mode="json"),
                "valuation_json": {"schema_version": "1.0.0"},
            },
        )
        plates = [_plate(session, record)]
        session.commit()

        assert require_takeoff_packet(revision).plate_id == _PLATE_ID
        assert require_assignments(revision).assignments[0].item_id == _ITEM_1
        assert require_plate_object_key(plates).endswith("plate.pdf")
        assert require_document(
            revision, "valuation_json", stage="bulletin", detail="boletim não construído"
        ) == {"schema_version": "1.0.0"}


def test_a_folha_meio_associada_e_tratada_como_ausente(tmp_path: Path) -> None:
    """Folha sem `upload_id` é tratada como ausente; devolvê-la pela metade esconderia o buraco."""
    database = _database(tmp_path)
    with database.sessions() as session:
        record = _round(session)
        plate = _plate(session, record)
        plate.upload_id = None
        session.commit()

        with pytest.raises(RoundRefusal) as refusal:
            require_plate([plate])
        assert refusal.value.code == "ROUND_STAGE_NOT_READY"

        plate.upload_id = record.catalog_upload_id
        # A contagem de páginas é da FOLHA desde a T4; a coluna da raiz é só o espelho dela.
        plate.page_count = 3
        session.commit()

        ref = require_plate([plate])
        assert ref.object_key.endswith("plate.pdf")
        assert ref.source_sha256 == _PDF_DIGEST
        assert ref.page_count == 3
        assert ref.plate_id == f"rodada-{record.id}"
        assert ref.position == 1


def test_a_praca_recusa_a_folha_repetida_e_nomeia_a_que_ja_esta_la(tmp_path: Path) -> None:
    """A segunda folha é o caso normal; a MESMA folha duas vezes é que não é (ADR-0057)."""
    database = _database(tmp_path)
    with database.sessions() as session:
        record = _round(session)
        _plate(session, record)
        segunda = _plate(session, record, source_sha256="c" * 64)
        session.commit()

        assert segunda.position == 2
        assert segunda.plate_id == f"rodada-{record.id}-f2"
        # O espelho escalar continua o da PRIMEIRA folha: é ele que o comando de fila lê.
        assert record.plate_source_sha256 == _PDF_DIGEST

        with pytest.raises(RoundRefusal) as refusal:
            _plate(session, record, source_sha256="c" * 64)
        assert refusal.value.code == "ROUND_PLATE_ALREADY_PRESENT"
        assert refusal.value.details["plate_id"] == segunda.plate_id


def test_a_praca_recusa_folha_alem_do_teto(tmp_path: Path) -> None:
    """Cada folha é uma extração paga a mais; o teto é declarado, não descoberto na conta."""
    database = _database(tmp_path)
    with database.sessions() as session:
        record = _round(session)
        for position in range(WORKSITE_PLATE_LIMIT):
            _plate(session, record, source_sha256=f"{position:064d}")
        session.commit()

        with pytest.raises(RoundRefusal) as refusal:
            _plate(session, record, source_sha256="f" * 64)
        assert refusal.value.code == "ROUND_PLATE_LIMIT_REACHED"
        assert refusal.value.details == {"limit": WORKSITE_PLATE_LIMIT}


def test_a_etapa_corrente_e_a_mais_avancada_da_cadeia(tmp_path: Path) -> None:
    """Rótulo da listagem: presença de artefato na ordem da cadeia, e nada além disso."""
    database = _database(tmp_path)
    with database.sessions() as session:
        record = _round(session)
        session.commit()
        assert current_stage(record, None, has_plate=False) == "created"

        _plate(session, record)
        # Extração em voo NÃO é etapa: a rodada segue na prancha até haver pacote.
        record.extraction_status = "running"
        session.commit()
        assert current_stage(record, None, has_plate=True) == "plate"

        revision = append_revision(
            session,
            round_record=record,
            created_by=_REVIEWER,
            changes={"takeoff_packet_json": _packet().model_dump(mode="json")},
        )
        session.commit()
        assert current_stage(record, revision, has_plate=True) == "takeoff"

        for column, stage in (
            ("code_assignments_json", "code_assignments"),
            ("valuation_json", "bulletin"),
            ("amendment_dossier_json", "amendment_dossier"),
        ):
            revision = append_revision(
                session,
                round_record=record,
                created_by=_REVIEWER,
                changes={column: {"schema_version": "1.0.0"}},
            )
            session.commit()
            assert current_stage(record, revision, has_plate=True) == stage


# --- estado da rodada ------------------------------------------------------------------


def test_o_estado_declara_as_etapas_por_presenca_e_digest(tmp_path: Path) -> None:
    database = _database(tmp_path)
    with database.sessions() as session:
        record = _round(session)
        packet = _packet([_item(), _item(item_id=_ITEM_2, status=TakeoffItemStatus.PROPOSED)])
        revision = append_revision(
            session,
            round_record=record,
            created_by=_REVIEWER,
            changes={
                "takeoff_packet_json": packet.model_dump(mode="json"),
                "code_assignments_json": _assignment_set().model_dump(mode="json"),
            },
        )
        session.commit()

        state = round_state_payload(record, revision, [])

        assert state["round_id"] == record.id
        assert state["version"] == record.version
        assert state["reviewer_role"] == "orcamentista"
        takeoff = state["takeoff"]
        assert isinstance(takeoff, dict)
        assert takeoff["present"] is True
        assert takeoff["review_status"] == "review_required"
        assert takeoff["items"] == 2
        assert takeoff["pending"] == 1
        # Sem relatório de registro, nenhuma âncora é declarada confiável (fail-closed).
        assert takeoff["anchors_registered"] == 0
        assert takeoff["anchors_raw"] == 2
        assert takeoff["packet_sha256"] == document_digest(packet.model_dump(mode="json"))
        codes = state["codes"]
        assert isinstance(codes, dict)
        assert codes["assignments_present"] is True
        assert codes["confirmed"] == 1
        assert codes["rejected"] == 0
        assert codes["pending"] == 0
        for stage in ("bulletin", "dossier"):
            etapa = state[stage]
            assert isinstance(etapa, dict)
            assert etapa["present"] is False


def test_rodada_sem_revisao_tem_estado_legivel(tmp_path: Path) -> None:
    """A rodada recém-criada não tem revisão, e a tela precisa abrir assim mesmo."""
    database = _database(tmp_path)
    with database.sessions() as session:
        record = _round(session)
        session.commit()

        state = round_state_payload(record, None, [])

        assert state["revision_id"] is None
        assert state["artifacts"] == {}
        for stage in ("takeoff", "plate", "bulletin", "dossier"):
            etapa = state[stage]
            assert isinstance(etapa, dict)
            assert etapa["present"] is False
        extraction = state["extraction"]
        assert isinstance(extraction, dict)
        assert extraction["status"] == "idle"
        codes = state["codes"]
        assert isinstance(codes, dict)
        assert codes["pending"] is None


def test_o_digest_do_artefato_nao_depende_da_ordem_das_chaves() -> None:
    assert document_digest({"a": 1, "b": {"c": 2, "d": 3}}) == document_digest(
        {"b": {"d": 3, "c": 2}, "a": 1}
    )
    assert document_digest({"a": 1}) != document_digest({"a": 2})


def test_a_ancora_confiavel_vem_do_relatorio_de_registro(tmp_path: Path) -> None:
    database = _database(tmp_path)
    with database.sessions() as session:
        record = _round(session)
        revision = append_revision(
            session,
            round_record=record,
            created_by=_REVIEWER,
            changes={
                "takeoff_packet_json": _packet().model_dump(mode="json"),
                "takeoff_registration_json": {
                    "method": "rulings",
                    "adjusted": [{"item_id": _ITEM_1}],
                },
            },
        )
        session.commit()

        takeoff = round_state_payload(record, revision, [])["takeoff"]

        assert isinstance(takeoff, dict)
        assert takeoff["anchors_registered"] == 1
        assert takeoff["anchors_raw"] == 0


def test_os_artefatos_da_revisao_incluem_o_digest_de_blob(tmp_path: Path) -> None:
    database = _database(tmp_path)
    with database.sessions() as session:
        record = _round(session)
        revision = append_revision(
            session,
            round_record=record,
            created_by=_REVIEWER,
            changes={
                "takeoff_packet_json": _packet().model_dump(mode="json"),
                "artifact_digests_json": {"overlay": "f" * 64},
            },
        )
        session.commit()

        artifacts = round_state_payload(record, revision, [])["artifacts"]

        assert isinstance(artifacts, dict)
        assert artifacts["overlay"] == "f" * 64
        assert "takeoff_packet_json" in artifacts


def test_o_conjunto_de_codigos_e_relido_do_documento_gravado(tmp_path: Path) -> None:
    database = _database(tmp_path)
    with database.sessions() as session:
        record = _round(session)
        revision = append_revision(
            session,
            round_record=record,
            created_by=_REVIEWER,
            changes={
                "code_assignments_json": _assignment_set(status="rejected").model_dump(mode="json")
            },
        )
        session.commit()

        assignments = assignments_of(revision)

        assert assignments is not None
        assert assignments.assignments[0].status == "rejected"


# --- URL assinada ----------------------------------------------------------------------


def test_a_url_assinada_sai_para_chave_do_proprio_tenant() -> None:
    store = _RecordingStore()
    key = f"tenants/{_TENANT}/rounds/r1/plate.png"

    url = signed_artifact_url(store, object_key=key, tenant_id=_TENANT)

    assert url is not None
    assert store.signed == [key]


@pytest.mark.parametrize(
    "object_key",
    [
        f"tenants/{_OTHER_TENANT}/rounds/r1/plate.png",
        "rounds/r1/plate.png",
        f"prefixo/tenants/{_TENANT}/rounds/r1/plate.png",
        f"tenants/{_TENANT}/../{_OTHER_TENANT}/plate.png",
        None,
    ],
)
def test_chave_fora_do_prefixo_do_tenant_nao_chega_ao_presign(object_key: str | None) -> None:
    """Recusa ANTES de assinar: assinar e conferir depois já teria vazado a URL."""
    store = _RecordingStore()

    assert signed_artifact_url(store, object_key=object_key, tenant_id=_TENANT) is None
    assert store.signed == []


def test_tenant_vazio_nunca_assina() -> None:
    store = _RecordingStore()

    assert signed_artifact_url(store, object_key="tenants//x.png", tenant_id="") is None
    assert store.signed == []


# --- catálogo e cache ------------------------------------------------------------------


def test_o_catalogo_e_decodificado_uma_vez_por_digest(tmp_path: Path) -> None:
    catalog = _catalog()
    payload = _catalog_bytes(catalog)
    digest = hashlib.sha256(payload).hexdigest()
    database = _database(tmp_path)
    with database.sessions() as session:
        record = _round(session, catalog_digest=digest)
        session.commit()
        store = _RecordingStore({record.catalog_object_key: payload})
        cache = CatalogCache()

        first = load_catalog(store, record, cache=cache)
        second = load_catalog(store, record, cache=cache)

        assert first.source_label == "CATALOGO SINTETICO"
        assert second is first
        assert store.reads == [record.catalog_object_key]


def test_catalogo_trocado_devolve_o_novo(tmp_path: Path) -> None:
    """A chave do cache é o digest: catálogo novo é entrada nova, nunca o velho servido."""
    old_payload = _catalog_bytes(_catalog())
    new_payload = _catalog_bytes(_catalog(source_label="CATALOGO SINTETICO REVISADO"))
    database = _database(tmp_path)
    with database.sessions() as session:
        record = _round(session, catalog_digest=hashlib.sha256(old_payload).hexdigest())
        session.commit()
        store = _RecordingStore({record.catalog_object_key: old_payload})
        cache = CatalogCache()
        assert load_catalog(store, record, cache=cache).source_label == "CATALOGO SINTETICO"

        store.objects[record.catalog_object_key] = new_payload
        record.catalog_source_sha256 = hashlib.sha256(new_payload).hexdigest()

        assert (
            load_catalog(store, record, cache=cache).source_label == "CATALOGO SINTETICO REVISADO"
        )


def test_o_cache_e_limitado_e_descarta_o_menos_recente(tmp_path: Path) -> None:
    cache = CatalogCache(max_entries=1)
    cache.put("a" * 64, _catalog())
    cache.put("b" * 64, _catalog(source_label="OUTRO"))

    assert cache.get("a" * 64) is None
    assert cache.get("b" * 64) is not None


def test_catalogo_ausente_no_store_recusa_com_catalog_required(tmp_path: Path) -> None:
    database = _database(tmp_path)
    with database.sessions() as session:
        record = _round(session)
        session.commit()

        with pytest.raises(RoundRefusal) as refusal:
            load_catalog(_RecordingStore(), record, cache=CatalogCache())

        assert refusal.value.code == "CATALOG_REQUIRED"
        assert refusal.value.http_status == 409


def test_catalogo_com_digest_divergente_recusa(tmp_path: Path) -> None:
    payload = _catalog_bytes(_catalog())
    database = _database(tmp_path)
    with database.sessions() as session:
        record = _round(session, catalog_digest="e" * 64)
        session.commit()
        store = _RecordingStore({record.catalog_object_key: payload})

        with pytest.raises(RoundRefusal) as refusal:
            load_catalog(store, record, cache=CatalogCache())

        assert refusal.value.code == "CATALOG_REQUIRED"


def test_catalogo_invalido_recusa_sem_republicar_o_erro_do_dominio(tmp_path: Path) -> None:
    payload = b'{"source_label": "X", "entries": []}'
    database = _database(tmp_path)
    with database.sessions() as session:
        record = _round(session, catalog_digest=hashlib.sha256(payload).hexdigest())
        session.commit()
        store = _RecordingStore({record.catalog_object_key: payload})

        with pytest.raises(RoundRefusal) as refusal:
            load_catalog(store, record, cache=CatalogCache())

        assert refusal.value.code == "CATALOG_REQUIRED"
        assert refusal.value.details["reason"] == "MODEL_VALIDATION_FAILED"


def test_catalogo_maior_que_o_teto_recusa_sem_decodificar(tmp_path: Path) -> None:
    """O teto existe para que o request path nunca carregue um blob do tamanho do cliente."""
    payload = b"x" * (CATALOG_MAX_BYTES + 1)
    database = _database(tmp_path)
    with database.sessions() as session:
        record = _round(session, catalog_digest=hashlib.sha256(payload).hexdigest())
        session.commit()
        store = _RecordingStore({record.catalog_object_key: payload})

        with pytest.raises(RoundRefusal) as refusal:
            load_catalog(store, record, cache=CatalogCache())

        assert refusal.value.code == "CATALOG_REQUIRED"
        assert refusal.value.details["max_bytes"] == CATALOG_MAX_BYTES


# --- invariantes estruturais -----------------------------------------------------------


def _module_source() -> str:
    return Path(inspect.getfile(valuation_rounds)).read_text(encoding="utf-8")


def test_o_nucleo_nao_conhece_http() -> None:
    """Critério de aceite do módulo: nenhuma função dele fala HTTP.

    O teste olha os IMPORTS, e não o texto solto, porque é o import que torna possível
    receber `Request` ou devolver `Response` — e é ele que a próxima rota tentaria
    acrescentar por conveniência.
    """
    tree = ast.parse(_module_source())
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            imported.add(node.module.split(".")[0])

    assert {"fastapi", "starlette"}.isdisjoint(imported), sorted(imported)


def test_toda_query_da_rodada_filtra_por_tenant_no_mesmo_where() -> None:
    """Isolamento por tenant não pode depender de conferência posterior.

    Um `where` que cite a rodada sem citar `tenant_id` é um IDOR esperando a próxima rota
    que copie o trecho — por isso o portão é sobre a EXPRESSÃO, não sobre o resultado de
    uma chamada específica.
    """
    source = _module_source()
    tree = ast.parse(source)
    faltantes = [
        segmento
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "where"
        and (segmento := ast.get_source_segment(source, node)) is not None
        and "ValuationRound" in segmento
        and "tenant_id" not in segmento
    ]

    assert faltantes == [], faltantes


def test_as_colunas_de_revisao_cobrem_a_tabela() -> None:
    """A allowlist do append é a tabela, sem coluna esquecida nem coluna inventada."""
    columns = {
        column.name
        for column in ValuationRoundRevisionRecord.__table__.columns
        if column.name.endswith("_json")
    }

    assert set(valuation_rounds.REVISION_COLUMNS) == columns


def test_a_rodada_e_a_revisao_nao_pendem_de_projeto() -> None:
    """Fronteira do ADR-0016 também no relacional: nenhuma FK para o contexto do croqui."""
    referred: set[str] = set()
    for table in (ValuationRoundRecord.__table__, ValuationRoundRevisionRecord.__table__):
        referred.update(key.column.table.name for key in table.foreign_keys)

    assert referred <= {"uploads", "valuation_rounds"}


def test_o_dublê_de_store_satisfaz_o_protocolo() -> None:
    """O `Protocol` é o contrato que a rota vai injetar; o dublê tem de caber nele."""
    store: valuation_rounds.RoundArtifactStore = _RecordingStore()
    payload: Any = store.read_object(object_key="ausente", max_bytes=8)

    assert payload is None
