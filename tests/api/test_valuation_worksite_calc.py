"""A praça inteira na `/v1` (F-046 T4c, ADR-0057).

Até aqui o domínio sabia medir a praça (`worksite_calc.py`, T2) e a `/v1` sabia guardá-la
(T3/T4) — mas `POST .../calc` continuava montando o boletim da PRIMEIRA folha. Numa praça de
N folhas isso media `1/N` e não dizia nada, que é exatamente a classe de erro que esta
feature existe para impedir: número parcial com cara de número inteiro.

Quatro coisas são provadas aqui, e a primeira manda nas outras:

- **A praça de UMA folha não muda de número.** O boletim que a rota produz é comparado com
  `calc.build_worksite_valuation` rodando lado a lado sobre os mesmos artefatos gravados.
- **A praça de N folhas é medida inteira, ou recusa.** Folha pendente de revisão e folha sem
  decisão de código recusam com o código do DOMÍNIO, nomeando folhas e itens. Nunca sai
  boletim pela metade.
- **A leitura e a revisão alcançam as folhas 2..N.** `plate_id` opcional nas três leituras e
  no lote de decisões; ausente, tudo responde como antes da praça.
- **A fusão declarada tem prévia no servidor.** A tela de medição não soma, então o efeito do
  vínculo no total é calculado aqui, sem gravar nada.
"""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path
from typing import Any, cast

from fastapi.testclient import TestClient
from sqlalchemy import select

from croquito_api.database import (
    ValuationRoundRecord,
    ValuationRoundRevisionRecord,
)
from croquito_api.valuation_rounds import (
    document_digest,
    head_revision,
    load_catalog,
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
from croquito_valuation.models import Valuation
from croquito_valuation.takeoff import (
    PlateBox,
    PlateEvidence,
    TakeoffItem,
    TakeoffItemStatus,
    TakeoffPacket,
)
from croquito_worker.valuation.round_extraction import (
    PLATE_IMAGE_REF,
    TAKEOFF_OVERLAY_DIGEST,
    TAKEOFF_OVERLAY_PACKET_DIGEST,
    TAKEOFF_OVERLAY_REF,
    plate_ref_key,
)
from tests.api.test_valuation_round_routes import (
    _TENANT,
    _associate_plate,
    _build_calc,
    _client,
    _create_round,
    _database,
    _headers,
    _observed_queue,
    _round_with_decided_code,
)
from tests.api.test_valuation_worksite import (
    _ITEM,
    _ITEM_OUTRO,
    _decision,
    _item,
    _packet,
)

_CODIGO_DA_RODADA = "CE04100010(/)"
"""O código do catálogo que `_create_round` instala; a praça mede com ELE, não com o do
catálogo sintético do arquivo vizinho — o boletim é montado contra o catálogo DA RODADA."""

_LEITURA = {"Authorization": f"Bearer test:{_TENANT}:orcamentista-sintetica:orcamentista"}
"""Cabeçalho sem `Idempotency-Key`: a prévia é leitura e não aceita chave de idempotência."""


def _item_proposto(*, plate_id: str, image_sha256: str, item_id: str) -> TakeoffItem:
    """Uma leitura ainda por revisar: é ela que torna a folha pendente para a praça."""
    return TakeoffItem(
        id=item_id,
        evidence=PlateEvidence(
            plate_id=plate_id,
            page_number=1,
            image_sha256=image_sha256,
            bbox=PlateBox(left=10, top=80, right=110, bottom=130),
        ),
        raw_text="MURO DE ARRIMO SINTETICO 12 m2",
        label="MURO DE ARRIMO SINTETICO",
        quantity=Decimal("12.00"),
        unit="m2",
        source="legend_extraction",
        extractor="legend-extractor-sintetico",
        extractor_version="1.0.0",
        status=TakeoffItemStatus.PROPOSED,
    )


def _assignments_da_rodada(packet: TakeoffPacket) -> CodeAssignmentSet:
    """Conjunto de códigos de uma folha, com o código do catálogo que a rodada instalou."""
    return CodeAssignmentSet(
        plate_id=packet.plate_id,
        page_number=packet.page_number,
        image_sha256=packet.image_sha256,
        catalog_sha256="c" * 64,
        assignments=[
            CodeAssignment(
                item_id=item.id,
                status="confirmed",
                code=_CODIGO_DA_RODADA,
                unit_compatible=True,
                decision=_decision(),
            )
            for item in packet.confirmed_items()
        ],
        closures=[
            ItemPackageClosure(item_id=item.id, decision=_decision())
            for item in packet.confirmed_items()
        ],
        safety_notes=[
            "Confirmação de código é ato humano rastreável; a sugestão lexical nunca "
            "confirma sozinha.",
            "Preço e unidade impressos continuam sendo conferidos contra catálogo e "
            "contrato no portão de exportação.",
        ],
    )


def _praca_na_v1(
    client: TestClient,
    *,
    segunda_pendente: bool = False,
    catalog_unit_price: Decimal = Decimal("50.00"),
    quantidade_folha_1: Decimal = Decimal("200.00"),
    quantidade_folha_2: Decimal = Decimal("50.00"),
    **round_overrides: Any,
) -> dict[str, Any]:
    """Praça de duas folhas com o artefato de cada folha publicado, como a extração publica.

    Escrever a revisão à mão é o mesmo caminho de `_praca_de_duas_folhas` e pelo mesmo motivo:
    a extração é PAGA. O que muda aqui é que as REFERÊNCIAS por folha também são gravadas — com
    o sufixo que `plate_ref_key` cunha —, porque é isso que a leitura por folha lê.

    Preço do catálogo, quantidade de cada folha e atributos da rodada (`round_overrides`) são
    parametrizáveis para exercitar o que a fixture de sempre não alcança: a 50,00 nenhuma
    quantidade de duas casas trunca centavo, e o nome longo da praça estoura o teto de 31
    caracteres do nome de aba quando o sufixo de folha entra.

    O conjunto de códigos gravado é o da PRIMEIRA folha, que é o que a `/v1` sabe guardar hoje:
    a coluna é uma só. É essa limitação que faz a praça de duas folhas recusar por
    `CALC_ASSIGNMENT_MISSING` em vez de fechar — e é ela que a etapa de código por folha
    (ADR-0057, decisão 6) vai remover.
    """
    created = _create_round(
        client,
        catalog_unit="m2",
        catalog_unit_price=catalog_unit_price,
        key="praca-v1",
        **round_overrides,
    )
    round_id = created["round_id"]
    assert _associate_plate(client, round_id, key="praca-v1-f1").status_code == 200
    assert _associate_plate(client, round_id, base_version=2, key="praca-v1-f2").status_code == 200
    with _database(client).sessions() as session:
        plates = round_plates(session, round_id=round_id, tenant_id=_TENANT)
        primeira, segunda = plates[0].plate_id, plates[1].plate_id
        packet_a = _packet(
            primeira,
            image_sha256="a" * 64,
            items=[_item(plate_id=primeira, image_sha256="a" * 64, quantity=quantidade_folha_1)],
        )
        itens_b: list[TakeoffItem] = [
            _item(plate_id=segunda, image_sha256="b" * 64, quantity=quantidade_folha_2)
        ]
        if segunda_pendente:
            itens_b.append(
                _item_proposto(plate_id=segunda, image_sha256="b" * 64, item_id=_ITEM_OUTRO)
            )
        packet_b = _packet(segunda, image_sha256="b" * 64, items=itens_b)
        documento_a = packet_a.model_dump(mode="json")
        documento_b = packet_b.model_dump(mode="json")
        base = f"tenants/{_TENANT}/valuation-rounds/{round_id}"
        refs = {
            PLATE_IMAGE_REF: f"{base}/plate/page-001.png",
            TAKEOFF_OVERLAY_REF: f"{base}/takeoff/overlay.png",
            plate_ref_key(PLATE_IMAGE_REF, position=2, plate_id=segunda): (
                f"{base}/plate/page-002.png"
            ),
            plate_ref_key(TAKEOFF_OVERLAY_REF, position=2, plate_id=segunda): (
                f"{base}/takeoff/overlay-002.png"
            ),
        }
        digests = {
            TAKEOFF_OVERLAY_DIGEST: "e" * 64,
            TAKEOFF_OVERLAY_PACKET_DIGEST: document_digest(documento_a),
            plate_ref_key(TAKEOFF_OVERLAY_DIGEST, position=2, plate_id=segunda): "f" * 64,
            plate_ref_key(
                TAKEOFF_OVERLAY_PACKET_DIGEST, position=2, plate_id=segunda
            ): document_digest(documento_b),
        }
        record = session.get(ValuationRoundRecord, round_id)
        assert record is not None
        session.add(
            ValuationRoundRevisionRecord(
                id=str(new_uuid7()),
                tenant_id=_TENANT,
                round_id=round_id,
                version=1,
                created_by="valuation-extraction-v1",
                takeoff_packet_json=documento_a,
                worksite_plate_packets_json={segunda: documento_b},
                code_assignments_json=_assignments_da_rodada(packet_a).model_dump(mode="json"),
                artifact_refs_json=refs,
                artifact_digests_json=digests,
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
        "refs": refs,
    }


# --------------------------------------------------------------------------------------
# o boletim da praça
# --------------------------------------------------------------------------------------


def test_o_calc_de_uma_folha_continua_byte_a_byte_o_boletim_de_hoje(tmp_path: Path) -> None:
    """Critério 1, e o primeiro teste a existir: a praça de UMA folha não muda de número.

    A rodada é montada pelas ROTAS de sempre — takeoff decidido, código confirmado, pacote
    fechado — e a medição que a rota produz é comparada com `calc.build_worksite_valuation`
    rodando lado a lado sobre os MESMOS artefatos gravados. O oráculo é o builder de hoje, e
    não um retrato gravado: assim uma mudança futura no caminho de uma folha tem de mover as
    duas cadeias juntas ou reprovar aqui.
    """
    client = _client(tmp_path)
    preparada = _round_with_decided_code(client, key="praca-uma-folha")
    round_id = preparada["round_id"]

    resposta = _build_calc(client, round_id, base_version=preparada["version"], key="calc-praca")

    assert resposta.status_code == 200, resposta.text
    da_rota = Valuation.model_validate(resposta.json()["valuation"])
    with _database(client).sessions() as session:
        record = session.get(ValuationRoundRecord, round_id)
        assert record is not None
        # Os dois artefatos de origem são lidos da CABEÇA: a revisão do boletim os carrega
        # adiante intactos, e é sobre eles que a rota acabou de medir.
        cabeca = head_revision(session, round_id=round_id, tenant_id=_TENANT)
        assert cabeca is not None
        de_hoje = build_worksite_valuation(
            TakeoffPacket.model_validate(cabeca.takeoff_packet_json),
            CodeAssignmentSet.model_validate(cabeca.code_assignments_json),
            load_catalog(
                cast(Any, client.app).state.artifact_store,
                record,
                cache=cast(Any, client.app).state.catalog_cache,
            ),
            worksite_key=record.worksite_key,
            worksite_name=record.worksite_name,
            period_number=record.period_number,
            reference_label=record.reference_label,
            address=record.address,
            contract_label=record.contract_label,
        )
        chave_da_praca = record.worksite_key

    assert da_rota.model_dump(mode="json", exclude={"id"}) == de_hoje.model_dump(
        mode="json", exclude={"id"}
    )
    # O `id` é UUIDv7 novo a cada build; alinhados, os dois digests têm de coincidir.
    alinhado = de_hoje.model_copy(update={"id": da_rota.id})
    assert alinhado.content_digest() == da_rota.content_digest()
    # E a chave do boletim continua a da PRAÇA, sem sufixo de folha (ADR-0057, decisão 8).
    assert [bulletin.worksite_key for bulletin in da_rota.bulletins] == [chave_da_praca]


def test_o_calc_da_praca_recusa_folha_pendente_nomeando_qual(tmp_path: Path) -> None:
    """Critério 2: o portão da T2 passa a ser alcançável pela rota, e vem ANTES do código.

    Meia praça somada parece uma praça inteira: com uma folha ainda por revisar, o boletim não
    é montado, e a recusa diz QUAL folha e quantos itens faltam nela.
    """
    client = _client(tmp_path)
    praca = _praca_na_v1(client, segunda_pendente=True)

    resposta = _build_calc(
        client, praca["round_id"], base_version=praca["version"], key="calc-pendente"
    )

    assert resposta.status_code == 422, resposta.text
    detalhe = resposta.json()["detail"]
    assert detalhe["code"] == "DOMAIN_VALIDATION_FAILED"
    assert detalhe["details"]["code"] == "WORKSITE_TAKEOFF_PLATE_PENDING"
    assert detalhe["details"]["plate_ids"] == [praca["plate_b"]]
    assert detalhe["details"]["pending_by_plate"] == {praca["plate_b"]: 1}
    # Nada foi gravado: a praça recusada não deixa boletim nenhum para trás.
    with _database(client).sessions() as session:
        assert (
            session.scalars(
                select(ValuationRoundRevisionRecord).where(
                    ValuationRoundRevisionRecord.valuation_json.is_not(None)
                )
            ).all()
            == []
        )


def test_o_calc_da_praca_cobra_a_segunda_folha_em_vez_de_medir_so_a_primeira(
    tmp_path: Path,
) -> None:
    """Critério 1, pelo avesso: a rota mede a PRAÇA, então a folha 2 sem código recusa.

    É o coração da T4c. Antes dela esta mesma rodada devolvia `200` com o boletim da primeira
    folha — `1/N` da praça, sem dizer nada. Agora a folha 2 entra no boletim, e a ausência de
    decisão de código nela é nomeada item por item.

    A recusa vem do DOMÍNIO (`CALC_ASSIGNMENT_MISSING`), e não desta camada: a etapa de código
    de `/v1` ainda guarda um conjunto só, e é ela que precisa crescer para a praça fechar.
    """
    client = _client(tmp_path)
    praca = _praca_na_v1(client)

    resposta = _build_calc(
        client, praca["round_id"], base_version=praca["version"], key="calc-sem-codigo-2"
    )

    assert resposta.status_code == 422, resposta.text
    detalhe = resposta.json()["detail"]
    assert detalhe["details"]["code"] == "CALC_ASSIGNMENT_MISSING"
    assert detalhe["details"]["item_ids"] == [_ITEM]


def test_o_calc_sem_folha_extraida_e_ordem_da_cadeia_e_nao_boletim_parcial(
    tmp_path: Path,
) -> None:
    """Folha da praça ainda sem pacote não vira boletim da folha que tem: é etapa fora de ordem."""
    client = _client(tmp_path)
    praca = _praca_na_v1(client)
    with _database(client).sessions() as session:
        cabeca = head_revision(session, round_id=praca["round_id"], tenant_id=_TENANT)
        assert cabeca is not None
        cabeca.worksite_plate_packets_json = None
        session.commit()

    resposta = _build_calc(
        client, praca["round_id"], base_version=praca["version"], key="calc-sem-folha-2"
    )

    assert resposta.status_code == 409, resposta.text
    detalhe = resposta.json()["detail"]
    assert detalhe["code"] == "ROUND_STAGE_NOT_READY"
    assert detalhe["details"]["stage"] == "worksite"
    assert detalhe["details"]["pending_plate_ids"] == [praca["plate_b"]]


# --------------------------------------------------------------------------------------
# leitura e revisão por folha
# --------------------------------------------------------------------------------------


def test_a_leitura_do_takeoff_por_folha_serve_o_pacote_daquela_folha(tmp_path: Path) -> None:
    """Critério 3: `plate_id` ausente é a primeira folha; presente, a folha nomeada."""
    client = _client(tmp_path)
    praca = _praca_na_v1(client)
    url = f"/v1/valuation-rounds/{praca['round_id']}/takeoff"

    sem_folha = client.get(url, headers=_headers())
    primeira = client.get(url, headers=_headers(), params={"plate_id": praca["plate_a"]})
    segunda = client.get(url, headers=_headers(), params={"plate_id": praca["plate_b"]})
    inexistente = client.get(url, headers=_headers(), params={"plate_id": "folha-de-outra-praca"})

    assert sem_folha.status_code == 200, sem_folha.text
    # Ausente e primeira folha são a MESMA resposta, campo por campo: é essa igualdade que faz
    # a tela que ainda não conhece a praça continuar funcionando sem mudar uma linha.
    assert sem_folha.json() == primeira.json()
    assert sem_folha.json()["packet"]["plate_id"] == praca["plate_a"]
    assert segunda.status_code == 200, segunda.text
    assert segunda.json()["packet"]["plate_id"] == praca["plate_b"]
    assert segunda.json()["packet_sha256"] == document_digest(
        praca["packet_b"].model_dump(mode="json")
    )
    assert inexistente.status_code == 404
    assert inexistente.json()["detail"]["code"] == "ROUND_PLATE_NOT_FOUND"


def test_a_imagem_e_o_overlay_por_folha_saem_da_chave_sufixada(tmp_path: Path) -> None:
    """Critério 3: cada folha tem imagem e overlay próprios, e a idade é comparada com o pacote
    DAQUELA folha — não existe pixel de praça (ADR-0057, decisão 3)."""
    client = _client(tmp_path)
    praca = _praca_na_v1(client)
    prancha = f"/v1/valuation-rounds/{praca['round_id']}/plate"
    overlay = f"/v1/valuation-rounds/{praca['round_id']}/takeoff/overlay"

    imagem_1 = client.get(prancha, headers=_headers())
    imagem_2 = client.get(prancha, headers=_headers(), params={"plate_id": praca["plate_b"]})
    desenho_1 = client.get(overlay, headers=_headers())
    desenho_2 = client.get(overlay, headers=_headers(), params={"plate_id": praca["plate_b"]})

    assert imagem_1.status_code == 200, imagem_1.text
    assert "page-001.png" in imagem_1.json()["image_url"]
    assert imagem_2.status_code == 200, imagem_2.text
    assert "page-002.png" in imagem_2.json()["image_url"]
    assert desenho_1.status_code == 200, desenho_1.text
    assert "overlay.png" in desenho_1.json()["image_url"]
    assert desenho_1.json()["stale"] is False
    assert desenho_2.status_code == 200, desenho_2.text
    assert "overlay-002.png" in desenho_2.json()["image_url"]
    assert desenho_2.json()["image_sha256"] == "f" * 64
    # A idade é do par (overlay, pacote) DAQUELA folha: os dois nasceram juntos, e nenhum
    # deles envelhece porque a outra folha mudou.
    assert desenho_2.json()["stale"] is False
    assert desenho_2.json()["packet_sha256"] == document_digest(
        praca["packet_b"].model_dump(mode="json")
    )


def test_a_decisao_do_takeoff_alcanca_a_segunda_folha_sem_tocar_a_primeira(
    tmp_path: Path,
) -> None:
    """Critério 4: o lote decide NA folha indicada, e grava no lugar daquela folha."""
    client = _client(tmp_path)
    praca = _praca_na_v1(client, segunda_pendente=True)
    fila = _observed_queue(client)

    resposta = client.post(
        f"/v1/valuation-rounds/{praca['round_id']}/takeoff/decisions",
        headers=_headers(key="decisao-folha-2"),
        json={
            "base_version": praca["version"],
            "plate_id": praca["plate_b"],
            "decisions": [{"item_id": _ITEM_OUTRO, "action": "reject", "note": "fora do escopo"}],
        },
    )

    assert resposta.status_code == 200, resposta.text
    corpo = resposta.json()
    assert corpo["packet"]["plate_id"] == praca["plate_b"]
    assert corpo["review_status"] == "complete"
    # O overlay daquela folha nasce vencido, e é isso que a resposta declara — o re-render
    # ainda é comando da primeira folha, então NADA foi enfileirado. A fila vazia só diz algo
    # porque a MESMA fila recebe `rerender_takeoff_overlay` no lote da primeira folha, o que
    # `test_a_decisao_grava_revisao_avanca_a_rodada_e_enfileira_o_overlay` prova.
    assert corpo["overlay"]["stale"] is True
    assert list(fila.messages) == []
    with _database(client).sessions() as session:
        cabeca = head_revision(session, round_id=praca["round_id"], tenant_id=_TENANT)
        assert cabeca is not None
        # A primeira folha viajou intacta; só o mapa da praça mudou.
        assert cabeca.takeoff_packet_json == praca["packet_a"].model_dump(mode="json")
        packets = worksite_packets(cabeca)
        assert packets[praca["plate_b"]].items[1].status is TakeoffItemStatus.REJECTED


def test_a_decisao_em_folha_inexistente_e_recurso_ausente_e_nao_grava(tmp_path: Path) -> None:
    """Folha que não é desta praça é `404`, e a recusa não deixa revisão para trás."""
    client = _client(tmp_path)
    praca = _praca_na_v1(client, segunda_pendente=True)

    resposta = client.post(
        f"/v1/valuation-rounds/{praca['round_id']}/takeoff/decisions",
        headers=_headers(key="decisao-folha-fantasma"),
        json={
            "base_version": praca["version"],
            "plate_id": "folha-de-outra-praca",
            "decisions": [{"item_id": _ITEM_OUTRO, "action": "reject", "note": "fora do escopo"}],
        },
    )

    assert resposta.status_code == 404
    assert resposta.json()["detail"]["code"] == "ROUND_PLATE_NOT_FOUND"
    with _database(client).sessions() as session:
        record = session.get(ValuationRoundRecord, praca["round_id"])
        assert record is not None
        assert record.version == praca["version"]
        assert len(session.scalars(select(ValuationRoundRevisionRecord)).all()) == 1


# --------------------------------------------------------------------------------------
# a prévia da fusão
# --------------------------------------------------------------------------------------


def test_a_previa_da_fusao_diz_o_total_antes_e_depois_sem_gravar_nada(tmp_path: Path) -> None:
    """Critério 5: a conta é do SERVIDOR, sai como texto, e nada é gravado."""
    client = _client(tmp_path)
    praca = _praca_na_v1(client)

    resposta = client.post(
        f"/v1/valuation-rounds/{praca['round_id']}/worksite/identity-links/preview",
        headers=_LEITURA,
        json={
            "kept": {"plate_id": praca["plate_a"], "item_id": _ITEM},
            "discarded": {"plate_id": praca["plate_b"], "item_id": _ITEM},
        },
    )

    assert resposta.status_code == 200, resposta.text
    corpo = resposta.json()
    assert corpo["version"] == praca["version"]
    assert corpo["worksite_key"] == "praca-sintetica-norte"
    assert corpo["kept"] == {
        "plate_id": praca["plate_a"],
        "item_id": _ITEM,
        "label": "PISO INTERTRAVADO SINTETICO",
        "unit": "m2",
        "status": "confirmed",
        "quantity": "200.00",
    }
    assert corpo["discarded"]["plate_id"] == praca["plate_b"]
    assert corpo["discarded"]["quantity"] == "50.00"
    assert corpo["unit_mismatch"] is False
    # 200,00 + 50,00 contadas hoje; 200,00 depois de declarar que são o mesmo elemento.
    assert corpo["total_before"] == "250.00"
    assert corpo["total_after"] == "200.00"
    with _database(client).sessions() as session:
        record = session.get(ValuationRoundRecord, praca["round_id"])
        assert record is not None
        # Leitura: a versão não anda e nenhum vínculo foi declarado.
        assert record.version == praca["version"]
        assert len(session.scalars(select(ValuationRoundRevisionRecord)).all()) == 1
        cabeca = head_revision(session, round_id=praca["round_id"], tenant_id=_TENANT)
        assert cabeca is not None
        assert cabeca.worksite_identity_links_json is None


def test_a_previa_nao_soma_unidades_diferentes(tmp_path: Path) -> None:
    """Duas leituras em unidades diferentes não têm soma; um número ali teria cara de conta."""
    client = _client(tmp_path)
    praca = _praca_na_v1(client)
    with _database(client).sessions() as session:
        cabeca = head_revision(session, round_id=praca["round_id"], tenant_id=_TENANT)
        assert cabeca is not None
        armazenado = cast(dict[str, Any], cabeca.worksite_plate_packets_json)
        pacote = dict(cast(dict[str, Any], armazenado[praca["plate_b"]]))
        itens = [dict(cast(dict[str, Any], item)) for item in cast(list[Any], pacote["items"])]
        itens[0]["unit"] = "m"
        pacote["items"] = itens
        cabeca.worksite_plate_packets_json = {praca["plate_b"]: pacote}
        session.commit()

    resposta = client.post(
        f"/v1/valuation-rounds/{praca['round_id']}/worksite/identity-links/preview",
        headers=_LEITURA,
        json={
            "kept": {"plate_id": praca["plate_a"], "item_id": _ITEM},
            "discarded": {"plate_id": praca["plate_b"], "item_id": _ITEM},
        },
    )

    assert resposta.status_code == 200, resposta.text
    corpo = resposta.json()
    assert corpo["unit_mismatch"] is True
    assert corpo["total_before"] is None
    assert corpo["total_after"] is None
    # As duas parcelas continuam à vista: quem vai declarar precisa ver o que está declarando.
    assert corpo["kept"]["unit"] == "m2"
    assert corpo["discarded"]["unit"] == "m"


def test_a_previa_recusa_o_que_a_declaracao_recusaria(tmp_path: Path) -> None:
    """Prévia que dissesse "pode" para o que o ato recusa seria pior do que prévia nenhuma."""
    client = _client(tmp_path)
    praca = _praca_na_v1(client, segunda_pendente=True)
    url = f"/v1/valuation-rounds/{praca['round_id']}/worksite/identity-links/preview"

    mesma_folha = client.post(
        url,
        headers=_LEITURA,
        json={
            "kept": {"plate_id": praca["plate_b"], "item_id": _ITEM},
            "discarded": {"plate_id": praca["plate_b"], "item_id": _ITEM_OUTRO},
        },
    )
    alvo_fantasma = client.post(
        url,
        headers=_LEITURA,
        json={
            "kept": {"plate_id": praca["plate_a"], "item_id": _ITEM},
            "discarded": {"plate_id": praca["plate_b"], "item_id": "ti_00000000000000ff"},
        },
    )
    outro_tenant = client.post(
        url,
        headers={"Authorization": "Bearer test:tenant-vizinho:intruso:orcamentista"},
        json={
            "kept": {"plate_id": praca["plate_a"], "item_id": _ITEM},
            "discarded": {"plate_id": praca["plate_b"], "item_id": _ITEM},
        },
    )
    sem_papel = client.post(
        url,
        headers={"Authorization": f"Bearer test:{_TENANT}:sem-papel:engineer"},
        json={
            "kept": {"plate_id": praca["plate_a"], "item_id": _ITEM},
            "discarded": {"plate_id": praca["plate_b"], "item_id": _ITEM},
        },
    )

    assert mesma_folha.status_code == 422
    assert mesma_folha.json()["detail"]["details"]["code"] == "WORKSITE_LINK_SAME_PLATE"
    assert alvo_fantasma.status_code == 422
    assert alvo_fantasma.json()["detail"]["details"]["code"] == "WORKSITE_LINK_UNKNOWN_TARGET"
    # IDOR: praça de outro tenant é inexistente, nunca proibida.
    assert outro_tenant.status_code == 404
    assert sem_papel.status_code == 403
