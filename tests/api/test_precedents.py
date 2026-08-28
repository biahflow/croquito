"""Índice de precedentes de código na `/v1` (F-044 T2): as duas fontes e a consulta.

Quatro invariantes atravessam a suíte, e são elas que a task existe para garantir:

- **precedente nunca atravessa tenant**. Provado com DOIS tenants, nas duas fontes e na
  consulta: o histórico de decisões de um escritório mostrado a outro seria vazar a forma de
  trabalhar de um cliente para um concorrente;
- **a contagem de praças não infla**. É o número que a tela mostra como argumento de
  autoridade ("você já usou isto em N praças"), e um número inflado é uma autoridade falsa.
  Refechar o pacote e reingerir a praça são idempotentes, e praça semeada que colide com
  rodada real é recusa nomeada;
- **a chave é (rótulo normalizado, fonte de preço)**, nunca o rótulo sozinho: precedente de
  outra fonte não é devolvido nem como resto, porque sugerir código que não existe na tabela
  vigente é pior que não sugerir nada (decisão 4 do escopo da feature);
- **a consulta não escreve e não paga**. Nenhuma revisão nova, nenhuma versão avançada.

Nenhuma planilha real entra aqui: as fixtures são sintéticas, escritas pelo próprio teste.
Nenhuma rota desta suíte chama provider — o índice sai do que já está gravado no banco.
"""

from __future__ import annotations

import hashlib
from decimal import Decimal
from pathlib import Path
from typing import Any, cast

from fastapi.testclient import TestClient
from sqlalchemy import select

from croquito_api import precedents
from croquito_api.config import ApiSettings
from croquito_api.database import (
    Database,
    EstimateRoundRecord,
    EstimateRoundRevisionRecord,
    PrecedentObservationRecord,
)
from croquito_api.main import create_app
from croquito_core.ids import new_uuid7
from croquito_valuation.assignment import CodeAssignment, CodeAssignmentSet
from croquito_valuation.models import (
    PriceCatalog,
    PriceCatalogEntry,
    PriceOrigin,
    ReviewerDecision,
)
from croquito_valuation.precedent import (
    PRICE_SOURCE_UNDECLARED,
    NormalizationStrategy,
    PrecedentSeedObservation,
    PrecedentSeedPacket,
)
from croquito_valuation.takeoff import (
    PlateBox,
    PlateEvidence,
    TakeoffItem,
    TakeoffItemStatus,
    TakeoffPacket,
)
from croquito_worker.valuation.round_extraction import PLATE_IMAGE_DIGEST, PLATE_IMAGE_REF
from tests.fakes import FakeObjectStore

_TENANT = "tenant-a"
_OTHER_TENANT = "tenant-b"

_PISO_CODE = "BP09100050(B)"
"""Pavimento rígido. Junto com a tela de aço, é o pacote N:N que o documento real mostra."""
_TELA_CODE = "ET39050109(/)"

_ITEM_PISO = "ti_00000000000000c1"
_ITEM_ALAMBRADO = "ti_00000000000000c2"

_PISO_LABEL = "PISO EM CONCRETO"
_ALAMBRADO_LABEL = "ALAMBRADO GALVANIZADO"

_IMAGE_DIGEST = "a" * 64
_SUBJECT = "orcamentista-sintetica"


# --- montagem ---------------------------------------------------------------------------


def _client(tmp_path: Path) -> TestClient:
    database = Database(f"sqlite+pysqlite:///{tmp_path / 'precedents-api.db'}")
    database.create_schema()
    settings = ApiSettings(
        database_url=f"sqlite+pysqlite:///{tmp_path / 'precedents-api.db'}",
        artifact_bucket="croquito-test-artifacts",
        aws_region="sa-east-1",
        aws_endpoint_url="http://localhost:4566",
        queue_url=None,
        oidc_issuer=None,
        oidc_audience=None,
        web_origin="http://localhost:5173",
        allow_test_tokens=True,
        real_providers_enabled=False,
    )
    application = create_app(settings=settings, database=database)
    application.state.artifact_store = FakeObjectStore()
    return TestClient(application)


def _headers(
    tenant: str = _TENANT, roles: str = "orcamentista", *, key: str = "precedente-001"
) -> dict[str, str]:
    return {
        "Authorization": f"Bearer test:{tenant}:{_SUBJECT}:{roles}",
        "Idempotency-Key": key,
    }


def _database(client: TestClient) -> Database:
    return cast(Database, cast(Any, client.app).state.database)


def _store(client: TestClient) -> FakeObjectStore:
    return cast(FakeObjectStore, cast(Any, client.app).state.artifact_store)


def _observations(client: TestClient) -> list[PrecedentObservationRecord]:
    with _database(client).sessions() as session:
        return list(
            session.scalars(
                select(PrecedentObservationRecord).order_by(
                    PrecedentObservationRecord.label_normalized,
                    PrecedentObservationRecord.code,
                )
            )
        )


def _catalog_bytes() -> bytes:
    """Catálogo sintético com DOIS códigos: é o pacote N:N do rótulo que precisa caber."""
    catalog = PriceCatalog(
        source_label="CATALOGO SINTETICO",
        reference_month="2026-01",
        source_sha256=hashlib.sha256(b"origem-sco").hexdigest(),
        origin=PriceOrigin.SCO,
        entries=[
            PriceCatalogEntry(
                code=code,
                description=description,
                unit="m2",
                unit_price=Decimal("50.00"),
                family_code=code[:2],
                family_name="SERVICOS SINTETICOS",
                subgroup_code=code[:6],
                subgroup_name="ITENS SINTETICOS",
                origin=PriceOrigin.SCO,
            )
            for code, description in (
                (_PISO_CODE, "PAVIMENTO RIGIDO"),
                (_TELA_CODE, "TELA DE ACO SOLDADA"),
            )
        ],
    )
    return catalog.model_dump_json().encode("utf-8")


def _takeoff_item(item_id: str, label: str) -> TakeoffItem:
    return TakeoffItem(
        id=item_id,
        evidence=PlateEvidence(
            plate_id="rodada-sintetica",
            page_number=1,
            image_sha256=_IMAGE_DIGEST,
            bbox=PlateBox(left=10, top=10, right=210, bottom=60),
        ),
        raw_text=f"{label} 418,12 m2",
        label=label,
        quantity=Decimal("418.12"),
        unit="m2",
        source="legend_extraction",
        extractor="legend-extractor-sintetico",
        extractor_version="1.0.0",
        status=TakeoffItemStatus.PROPOSED,
    )


def _publish_takeoff(
    client: TestClient, round_id: str, *, tenant: str, labels: dict[str, str]
) -> int:
    """Publica o takeoff direto na revisão, como o comando de fila faria.

    A extração é PAGA: exercitá-la aqui só para chegar ao takeoff faria cada teste desta
    suíte depender do braço do provider, e o índice de precedentes não paga nada.
    """
    packet = TakeoffPacket(
        plate_id="rodada-sintetica",
        page_number=1,
        image_sha256=_IMAGE_DIGEST,
        source_pdf_sha256="b" * 64,
        items=[_takeoff_item(item_id, label) for item_id, label in labels.items()],
        safety_notes=[
            "Extração automática da legenda; quantidade não confirmada.",
            "Decisão do orçamentista obrigatória antes de qualquer orçamento.",
        ],
    )
    with _database(client).sessions() as session:
        record = session.get(EstimateRoundRecord, round_id)
        assert record is not None
        head = session.scalar(
            select(EstimateRoundRevisionRecord)
            .where(EstimateRoundRevisionRecord.round_id == round_id)
            .order_by(EstimateRoundRevisionRecord.version.desc())
            .limit(1)
        )
        session.add(
            EstimateRoundRevisionRecord(
                id=str(new_uuid7()),
                tenant_id=tenant,
                round_id=round_id,
                version=1 if head is None else head.version + 1,
                parent_revision_id=None if head is None else head.id,
                created_by="estimate-extraction-v1",
                takeoff_packet_json=packet.model_dump(mode="json"),
                artifact_refs_json={
                    PLATE_IMAGE_REF: (
                        f"tenants/{tenant}/estimate-rounds/{round_id}/plate/page-001.png"
                    )
                },
                artifact_digests_json={PLATE_IMAGE_DIGEST: packet.image_sha256},
            )
        )
        record.version += 1
        session.commit()
        return record.version


def _round_ready_for_codes(
    client: TestClient,
    *,
    tenant: str = _TENANT,
    worksite_key: str = "praca-sintetica-norte",
    suffix: str = "a",
    labels: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Rodada com catálogo instalado e takeoff confirmado — o estado da etapa de códigos."""
    created = client.post(
        "/v1/estimate-rounds",
        headers=_headers(tenant, key=f"rodada-{suffix}"),
        json={
            "worksite_key": worksite_key,
            "worksite_name": "PRACA SINTETICA",
            "reference_label": "ORCAMENTO-BASE 2026",
        },
    )
    assert created.status_code == 201, created.text
    round_id = cast(str, created.json()["round_id"])

    payload = _catalog_bytes()
    presign = client.post(
        "/v1/uploads/presign",
        headers=_headers(tenant, key=f"upload-{suffix}"),
        json={
            "filename": "catalogo.json",
            "content_type": "application/json",
            "size_bytes": len(payload),
            "sha256": hashlib.sha256(payload).hexdigest(),
        },
    )
    assert presign.status_code == 200, presign.text
    _store(client).put_direct(
        object_key=presign.json()["object_key"], body=payload, content_type="application/json"
    )
    installed = client.post(
        f"/v1/estimate-rounds/{round_id}/catalogs",
        headers=_headers(tenant, key=f"catalogo-{suffix}"),
        json={"upload_id": presign.json()["upload_id"], "base_version": 1},
    )
    assert installed.status_code == 201, installed.text
    catalog_sha256 = cast(str, installed.json()["cascade"][0]["source_sha256"])

    version = _publish_takeoff(
        client,
        round_id,
        tenant=tenant,
        labels=labels or {_ITEM_PISO: _PISO_LABEL, _ITEM_ALAMBRADO: _ALAMBRADO_LABEL},
    )
    for index, item_id in enumerate(labels or {_ITEM_PISO: "", _ITEM_ALAMBRADO: ""}):
        decided = client.post(
            f"/v1/estimate-rounds/{round_id}/takeoff/decisions",
            headers=_headers(tenant, key=f"takeoff-{suffix}-{index}"),
            json={
                "base_version": version,
                "decisions": [{"item_id": item_id, "action": "confirm"}],
            },
        )
        assert decided.status_code == 200, decided.text
        version = decided.json()["version"]

    return {
        "round_id": round_id,
        "version": version,
        "catalog_sha256": catalog_sha256,
        "tenant": tenant,
    }


def _decide_code(
    client: TestClient,
    state: dict[str, Any],
    *,
    item_id: str,
    action: str = "confirm",
    code: str | None = None,
    key: str,
    note: str | None = None,
) -> None:
    body: dict[str, Any] = {
        "base_version": state["version"],
        "item_id": item_id,
        "action": action,
    }
    if action == "confirm":
        body["code"] = code
        body["catalog_sha256"] = state["catalog_sha256"]
    if note is not None:
        body["note"] = note
    response = client.post(
        f"/v1/estimate-rounds/{state['round_id']}/code-assignments/decisions",
        headers=_headers(state["tenant"], key=key),
        json=body,
    )
    assert response.status_code == 200, response.text
    state["version"] = response.json()["version"]


def _close_package(client: TestClient, state: dict[str, Any], *, item_id: str, key: str) -> Any:
    response = client.post(
        f"/v1/estimate-rounds/{state['round_id']}/code-assignments/closures",
        headers=_headers(state["tenant"], key=key),
        json={"base_version": state["version"], "item_id": item_id},
    )
    if response.status_code == 200:
        state["version"] = response.json()["version"]
    return response


def _round_with_closed_piso(
    client: TestClient,
    *,
    tenant: str = _TENANT,
    worksite_key: str = "praca-sintetica-norte",
    suffix: str = "a",
) -> dict[str, Any]:
    """O caso do documento real: `PISO EM CONCRETO` dispara DOIS códigos, e o pacote fecha."""
    state = _round_ready_for_codes(client, tenant=tenant, worksite_key=worksite_key, suffix=suffix)
    _decide_code(client, state, item_id=_ITEM_PISO, code=_PISO_CODE, key=f"piso-1-{suffix}")
    _decide_code(client, state, item_id=_ITEM_PISO, code=_TELA_CODE, key=f"piso-2-{suffix}")
    closed = _close_package(client, state, item_id=_ITEM_PISO, key=f"fecha-piso-{suffix}")
    assert closed.status_code == 200, closed.text
    return state


# --- fonte A: o fechamento do pacote de códigos --------------------------------------------


def test_fechar_o_pacote_grava_o_precedente_do_rotulo(tmp_path: Path) -> None:
    """O ato que diz "acabou" é o que ensina o índice — e ensina o PACOTE, não um código.

    Indexar na confirmação de cada código ensinaria pacote pela metade: até o fechamento, o
    elemento ainda pode ganhar mais um serviço.
    """
    client = _client(tmp_path)

    state = _round_with_closed_piso(client)

    rows = _observations(client)
    assert [(row.label_normalized, row.code) for row in rows] == [
        ("piso em concreto", _PISO_CODE),
        ("piso em concreto", _TELA_CODE),
    ]
    assert {row.source for row in rows} == {precedents.SOURCE_ROUND}
    assert {row.tenant_id for row in rows} == {_TENANT}
    assert {row.price_source for row in rows} == {state["catalog_sha256"]}
    assert {row.label_original for row in rows} == {_PISO_LABEL}
    assert {row.normalization_strategy for row in rows} == {
        precedents.INDEX_NORMALIZATION_STRATEGY.value
    }


def test_o_item_que_nao_fechou_nao_tem_precedente(tmp_path: Path) -> None:
    """Confirmar código não é fechar: só o elemento declarado completo entra no índice."""
    client = _client(tmp_path)
    state = _round_ready_for_codes(client)

    _decide_code(client, state, item_id=_ITEM_PISO, code=_PISO_CODE, key="piso-1")
    _decide_code(client, state, item_id=_ITEM_ALAMBRADO, code=_TELA_CODE, key="alambrado-1")
    closed = _close_package(client, state, item_id=_ITEM_PISO, key="fecha-piso")
    assert closed.status_code == 200, closed.text

    assert {row.label_normalized for row in _observations(client)} == {"piso em concreto"}


def test_codigo_rejeitado_nunca_entra_no_precedente(tmp_path: Path) -> None:
    """Rejeitar diz que o código NÃO serve para aquele elemento.

    Propagar a rejeição como precedente ensinaria o índice exatamente o contrário do que a
    orçamentista decidiu — e o precedente volta com aparência de acerto.
    """
    client = _client(tmp_path)
    state = _round_ready_for_codes(client)

    _decide_code(
        client,
        state,
        item_id=_ITEM_ALAMBRADO,
        action="reject",
        key="rejeita",
        note="alambrado fora do escopo desta praça",
    )

    assert _observations(client) == []


def test_o_filtro_de_status_e_conferido_sobre_o_conjunto_gravado() -> None:
    """`observations_from_closure` só devolve o que foi CONFIRMADO, item a item.

    Verificado em nível de aplicação porque a leitura recebe o conjunto INTEIRO da rodada e
    tem de recortar dele o item que fechou: um filtro frouxo indexaria o pacote do vizinho
    sob o rótulo errado, e o precedente sairia com autoridade e conteúdo trocado.

    O caso "confirmado e rejeitado para o MESMO item" **não** é testado aqui, e o motivo é
    que ele não existe: `CodeAssignmentSet` já o recusa por invariante do domínio
    (`ASSIGNMENT_REJECT_WITH_CONFIRMED` — rejeitar é declarar que nenhum serviço precifica o
    elemento). Montar essa fixture só provaria que o teste sabe construir um estado
    impossível.
    """
    packet = TakeoffPacket(
        plate_id="rodada-sintetica",
        page_number=1,
        image_sha256=_IMAGE_DIGEST,
        source_pdf_sha256="b" * 64,
        items=[
            _takeoff_item(_ITEM_PISO, _PISO_LABEL),
            _takeoff_item(_ITEM_ALAMBRADO, _ALAMBRADO_LABEL),
        ],
        safety_notes=[
            "Extração automática da legenda; quantidade não confirmada.",
            "Decisão do orçamentista obrigatória antes de qualquer orçamento.",
        ],
    )
    confirmacao = ReviewerDecision(
        decision_id="vd_0000000000000001",
        reviewer_id=_SUBJECT,
        reviewer_role="orcamentista",
        action="confirm",
        decided_at="2026-08-28T12:00:00Z",
    )
    rejeicao = ReviewerDecision(
        decision_id="vd_0000000000000002",
        reviewer_id=_SUBJECT,
        reviewer_role="orcamentista",
        action="reject",
        decided_at="2026-08-28T12:01:00Z",
        note="nenhum serviço do catálogo precifica este elemento",
    )
    assignments = CodeAssignmentSet(
        plate_id="rodada-sintetica",
        page_number=1,
        image_sha256=_IMAGE_DIGEST,
        catalog_sha256="c" * 64,
        safety_notes=[
            "Sugestão de código é observação, nunca decisão.",
            "Toda confirmação exige decisão do orçamentista.",
        ],
        assignments=[
            CodeAssignment(
                item_id=_ITEM_PISO,
                status="confirmed",
                code=_PISO_CODE,
                catalog_sha256="c" * 64,
                unit_compatible=True,
                decision=confirmacao,
            ),
            CodeAssignment(
                item_id=_ITEM_ALAMBRADO,
                status="rejected",
                code=None,
                unit_compatible=True,
                decision=rejeicao,
            ),
        ],
    )

    do_piso = precedents.observations_from_closure(packet, assignments, _ITEM_PISO)
    do_alambrado = precedents.observations_from_closure(packet, assignments, _ITEM_ALAMBRADO)
    de_item_inexistente = precedents.observations_from_closure(
        packet, assignments, "ti_0000000000000fff"
    )

    assert do_piso == [(_PISO_LABEL, "piso em concreto", "c" * 64, _PISO_CODE)]
    assert do_alambrado == []
    assert de_item_inexistente == []


def test_refechar_o_pacote_nao_duplica_e_a_contagem_de_pracas_nao_infla(
    tmp_path: Path,
) -> None:
    """A contagem de praças é o argumento de autoridade da tela; ela não pode se mover.

    Três caminhos de repetição, os três conferidos: o replay da `Idempotency-Key`, o
    refechamento com chave nova (que o domínio recusa) e a chamada direta da camada de
    aplicação, que é a que prova que a idempotência está no ÍNDICE e não só no ato.
    """
    client = _client(tmp_path)
    state = _round_with_closed_piso(client)
    baseline = len(_observations(client))
    assert baseline == 2

    replay = client.post(
        f"/v1/estimate-rounds/{state['round_id']}/code-assignments/closures",
        headers=_headers(key="fecha-piso-a"),
        json={"base_version": state["version"] - 1, "item_id": _ITEM_PISO},
    )
    assert replay.status_code == 200, replay.text
    assert len(_observations(client)) == baseline

    de_novo = _close_package(client, state, item_id=_ITEM_PISO, key="fecha-piso-outra-vez")
    assert de_novo.status_code == 422, de_novo.text
    assert de_novo.json()["detail"]["details"]["code"] == "ASSIGNMENT_DUPLICATE_CLOSURE"
    assert len(_observations(client)) == baseline

    with _database(client).sessions() as session:
        record = session.get(EstimateRoundRecord, state["round_id"])
        assert record is not None
        revision = session.scalar(
            select(EstimateRoundRevisionRecord)
            .where(EstimateRoundRevisionRecord.round_id == state["round_id"])
            .order_by(EstimateRoundRevisionRecord.version.desc())
            .limit(1)
        )
        assert revision is not None
        packet = TakeoffPacket.model_validate(revision.takeoff_packet_json)
        assignments = CodeAssignmentSet.model_validate(revision.code_assignments_json)
        counts = precedents.record_closure_precedents(
            session,
            tenant_id=_TENANT,
            worksite_key=record.worksite_key,
            packet=packet,
            assignments=assignments,
            item_id=_ITEM_PISO,
            created_by=_SUBJECT,
        )
        session.commit()

    assert counts.ingested == 0
    assert counts.skipped == 2
    assert len(_observations(client)) == baseline


# --- fonte B: semeadura de orçamentos passados ---------------------------------------------


def _seed_body(
    *,
    worksite_key: str = "praca-passada-sul",
    price_source: str = "d" * 64,
    pairs: tuple[tuple[str, str], ...] = ((_PISO_LABEL, _PISO_CODE), (_PISO_LABEL, _TELA_CODE)),
    strategy: NormalizationStrategy = NormalizationStrategy.FOLDED,
    normalized: str | None = None,
) -> dict[str, Any]:
    """Pacote como `precedent-extract` o escreveria, com a normalização já calculada."""
    packet = PrecedentSeedPacket(
        worksite_key=worksite_key,
        normalization_strategy=strategy,
        observations=tuple(
            PrecedentSeedObservation(
                label_original=label,
                label_normalized=normalized or precedents.index_key(label),
                code=code,
                price_source=price_source,
            )
            for label, code in pairs
        ),
        block_count=len(pairs),
        labeled_block_count=len(pairs),
    )
    return packet.model_dump(mode="json")


def _seed(client: TestClient, body: dict[str, Any], *, tenant: str = _TENANT, key: str) -> Any:
    return client.post("/v1/precedents/seed", headers=_headers(tenant, key=key), json=body)


def test_a_semeadura_ingere_a_praca_passada(tmp_path: Path) -> None:
    """Sem ela o índice nasce vazio: só uma rodada real existe no banco."""
    client = _client(tmp_path)

    response = _seed(client, _seed_body(), key="semeadura-1")

    assert response.status_code == 200, response.text
    assert response.json() == {
        "worksite_key": "praca-passada-sul",
        "observations_ingested": 2,
        "observations_skipped": 0,
        "labels": 1,
    }
    rows = _observations(client)
    assert {row.source for row in rows} == {precedents.SOURCE_SEED}
    assert {row.worksite_key for row in rows} == {"praca-passada-sul"}
    assert {row.created_by for row in rows} == {_SUBJECT}


def test_reingerir_a_mesma_praca_nao_duplica_nem_soma_na_contagem(tmp_path: Path) -> None:
    """Idempotente por `(tenant_id, worksite_key)`, com chave de idempotência NOVA.

    A chave nova é o ponto: com a mesma, quem responderia seria o registro de idempotência, e
    o teste não diria nada sobre o índice. Aqui a ingestão corre de verdade pela segunda vez
    e mesmo assim não grava linha nenhuma.
    """
    client = _client(tmp_path)
    body = _seed_body()
    assert _seed(client, body, key="semeadura-1").status_code == 200

    de_novo = _seed(client, body, key="semeadura-2")

    assert de_novo.status_code == 200, de_novo.text
    assert de_novo.json()["observations_ingested"] == 0
    assert de_novo.json()["observations_skipped"] == 2
    assert len(_observations(client)) == 2


def test_semear_sobre_praca_de_rodada_real_e_recusa_nomeada(tmp_path: Path) -> None:
    """Misturar as duas origens sob a mesma chave juntaria dados de qualidade diferente.

    A recusa fica do lado da semeadura, e não do fechamento, de propósito: semear é
    importação deliberada, que pode ser refeita; fechar o pacote é o ato central da jornada,
    e travá-lo pela contabilidade de um índice seria a ferramenta impedindo o trabalho.
    """
    client = _client(tmp_path)
    _round_ready_for_codes(client, worksite_key="praca-sintetica-norte")

    response = _seed(client, _seed_body(worksite_key="praca-sintetica-norte"), key="semeadura-1")

    assert response.status_code == 409, response.text
    assert response.json()["detail"]["code"] == precedents.PRECEDENT_SEED_WORKSITE_CONFLICT
    assert _observations(client) == []


def test_semeadura_com_outra_estrategia_de_normalizacao_recusa(tmp_path: Path) -> None:
    """Duas normalizações no mesmo índice dariam duas chaves para o mesmo rótulo.

    A metade errada nunca reencontraria nada — falha silenciosa, cara de descobrir, e é para
    isso que a estratégia viaja escrita no pacote.
    """
    client = _client(tmp_path)

    response = _seed(
        client,
        _seed_body(strategy=NormalizationStrategy.STEMS, normalized="pis concret"),
        key="semeadura-1",
    )

    assert response.status_code == 422, response.text
    assert response.json()["detail"]["code"] == precedents.PRECEDENT_SEED_STRATEGY_UNSUPPORTED
    assert _observations(client) == []


def test_semeadura_com_normalizacao_divergente_recusa_nomeando_a_posicao(
    tmp_path: Path,
) -> None:
    """O servidor recalcula a chave e discorda: extrator e servidor não podem divergir.

    A recusa nomeia a POSIÇÃO da observação, e não o rótulo: quem chamou tem o pacote em
    mãos, e rótulo de legenda não precisa dar mais uma volta pela fronteira.
    """
    client = _client(tmp_path)

    response = _seed(
        client, _seed_body(normalized="chave-que-o-servidor-nao-calcula"), key="semeadura-1"
    )

    assert response.status_code == 422, response.text
    detail = response.json()["detail"]
    assert detail["code"] == precedents.PRECEDENT_SEED_NORMALIZATION_MISMATCH
    assert detail["details"]["observations"] == [0, 1]
    assert _PISO_LABEL not in response.text
    assert _observations(client) == []


def test_semeadura_sem_o_papel_recusa_antes_de_qualquer_escrita(tmp_path: Path) -> None:
    client = _client(tmp_path)

    response = _seed(client, _seed_body(), tenant=_TENANT, key="sem-papel")
    sem_papel = client.post(
        "/v1/precedents/seed",
        headers=_headers(roles="engineer", key="sem-papel-2"),
        json=_seed_body(),
    )

    assert response.status_code == 200, response.text
    assert sem_papel.status_code == 403
    assert sem_papel.json()["detail"]["code"] == "FORBIDDEN"


def test_semeadura_sem_idempotency_key_recusa(tmp_path: Path) -> None:
    client = _client(tmp_path)
    headers = _headers()
    headers.pop("Idempotency-Key")

    response = client.post("/v1/precedents/seed", headers=headers, json=_seed_body())

    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "IDEMPOTENCY_KEY_REQUIRED"


# --- fronteira de tenant -------------------------------------------------------------------


def test_precedente_de_um_tenant_nunca_aparece_para_outro(tmp_path: Path) -> None:
    """A invariante inegociável, provada com dois tenants e com as DUAS fontes.

    O tenant A fecha um pacote e semeia uma praça; o tenant B semeia a mesma praça, com o
    mesmo rótulo e a mesma fonte de preço. Nenhum dos dois enxerga o outro — nem na contagem
    de praças, que ficaria dobrada se a fronteira vazasse.
    """
    client = _client(tmp_path)
    state = _round_with_closed_piso(client, tenant=_TENANT)
    assert (
        _seed(
            client,
            _seed_body(price_source=state["catalog_sha256"]),
            tenant=_TENANT,
            key="semeadura-a",
        ).status_code
        == 200
    )
    assert (
        _seed(
            client,
            _seed_body(price_source=state["catalog_sha256"]),
            tenant=_OTHER_TENANT,
            key="semeadura-b",
        ).status_code
        == 200
    )

    with _database(client).sessions() as session:
        do_a = precedents.precedents_for(session, _TENANT, [_PISO_LABEL], state["catalog_sha256"])
        do_b = precedents.precedents_for(
            session, _OTHER_TENANT, [_PISO_LABEL], state["catalog_sha256"]
        )

    chave = precedents.index_key(_PISO_LABEL)
    # A: a rodada real (praca-sintetica-norte) mais a praça semeada = duas praças.
    assert do_a[chave].worksite_count == 2
    # B: só a praça que ele mesmo semeou. Se a fronteira vazasse, seriam duas aqui também.
    assert do_b[chave].worksite_count == 1
    with _database(client).sessions() as session:
        vazio = precedents.precedents_for(
            session, "tenant-que-nunca-existiu", [_PISO_LABEL], state["catalog_sha256"]
        )
    assert vazio == {}


# --- a consulta que a T3 vai consumir ------------------------------------------------------


def test_a_consulta_devolve_os_codigos_e_a_contagem_de_pracas(tmp_path: Path) -> None:
    """Duas praças com o mesmo rótulo; a segunda com pacote CONTIDO na primeira.

    É o caso `subset` que a medição encontrou em 8 dos 76 rótulos repetidos — escopo menor,
    não erro. A contagem por código é o que deixa isso legível: o rótulo aparece em duas
    praças, mas um dos códigos só apareceu numa.
    """
    client = _client(tmp_path)
    fonte = "d" * 64
    assert (
        _seed(
            client, _seed_body(worksite_key="praca-passada-sul", price_source=fonte), key="s1"
        ).status_code
        == 200
    )
    assert (
        _seed(
            client,
            _seed_body(
                worksite_key="praca-passada-leste",
                price_source=fonte,
                pairs=((_PISO_LABEL, _PISO_CODE),),
            ),
            key="s2",
        ).status_code
        == 200
    )

    with _database(client).sessions() as session:
        entries = precedents.precedents_for(session, _TENANT, [_PISO_LABEL], fonte)

    entry = entries[precedents.index_key(_PISO_LABEL)]
    assert entry.worksite_count == 2
    assert [(code.code, code.worksite_count) for code in entry.codes] == [
        (_PISO_CODE, 2),
        (_TELA_CODE, 1),
    ]
    assert entry.labels_seen == (_PISO_LABEL,)


def test_a_consulta_nao_devolve_precedente_de_outra_fonte_de_preco(tmp_path: Path) -> None:
    """Sugerir código que não existe na tabela vigente é o pior resultado possível.

    Pior que não sugerir nada — e é o que a decisão 4 do escopo da feature existe para
    impedir. A string vazia (`PRICE_SOURCE_UNDECLARED`) é uma fonte PRÓPRIA, e não um
    curinga que case com todas.
    """
    client = _client(tmp_path)
    assert _seed(client, _seed_body(price_source="d" * 64), key="s1").status_code == 200

    with _database(client).sessions() as session:
        outra = precedents.precedents_for(session, _TENANT, [_PISO_LABEL], "e" * 64)
        vazia = precedents.precedents_for(session, _TENANT, [_PISO_LABEL], PRICE_SOURCE_UNDECLARED)
        certa = precedents.precedents_for(session, _TENANT, [_PISO_LABEL], "d" * 64)

    assert outra == {}
    assert vazia == {}
    assert set(certa) == {precedents.index_key(_PISO_LABEL)}


def test_rotulo_inedito_simplesmente_nao_aparece_no_resultado(tmp_path: Path) -> None:
    """Entrada vazia faria a tela desenhar um bloco de precedente sem nada dentro.

    O pacote de design aprovado é explícito: quando não há precedente, o bloco não existe —
    não aparece vazio nem desabilitado.
    """
    client = _client(tmp_path)
    assert _seed(client, _seed_body(price_source="d" * 64), key="s1").status_code == 200

    with _database(client).sessions() as session:
        entries = precedents.precedents_for(
            session, _TENANT, [_PISO_LABEL, "GUARDA CORPO INEDITO"], "d" * 64
        )

    assert set(entries) == {precedents.index_key(_PISO_LABEL)}


def test_a_consulta_nao_grava_e_nao_avanca_a_versao_da_rodada(tmp_path: Path) -> None:
    """O `GET` da shortlist continua sem custo e sem avançar a versão (ADR-0054 D7).

    O precedente não pode introduzir escrita nesse caminho — é leitura do que já está
    gravado, e o índice não paga nada.
    """
    client = _client(tmp_path)
    state = _round_with_closed_piso(client)
    antes_versao = state["version"]
    antes_observacoes = len(_observations(client))
    with _database(client).sessions() as session:
        antes_revisoes = len(
            list(
                session.scalars(
                    select(EstimateRoundRevisionRecord).where(
                        EstimateRoundRevisionRecord.round_id == state["round_id"]
                    )
                )
            )
        )

    with _database(client).sessions() as session:
        entries = precedents.precedents_for(
            session, _TENANT, [_PISO_LABEL, _ALAMBRADO_LABEL], state["catalog_sha256"]
        )

    assert set(entries) == {precedents.index_key(_PISO_LABEL)}
    with _database(client).sessions() as session:
        record = session.get(EstimateRoundRecord, state["round_id"])
        assert record is not None
        assert record.version == antes_versao
        assert (
            len(
                list(
                    session.scalars(
                        select(EstimateRoundRevisionRecord).where(
                            EstimateRoundRevisionRecord.round_id == state["round_id"]
                        )
                    )
                )
            )
            == antes_revisoes
        )
    assert len(_observations(client)) == antes_observacoes
