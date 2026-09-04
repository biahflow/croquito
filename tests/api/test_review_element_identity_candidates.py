"""F-051 T4: a candidata por identidade nasce e morre NO ATO (ADR-0063, decisão 3).

As candidatas de associação são persistidas em `associations_json` e a API nunca as
recomputa na leitura — então cada ato que pode mudar o casamento hint↔elemento recunha as
candidatas por identidade da revisão que ele cria. São cinco: declarar, revogar, renomear
(F-051 T2) e os dois que corrigem o `target_entity_label` da leitura, decisão e retificação
declarada (F-051 T1).

O que estes testes protegem, em uma frase cada: declarar dá à cota-balão uma candidata de
cada proposta do elemento, ALÉM das de proximidade e nunca no lugar delas; a confirmação
passa pelo portão único de sempre, sem caminho novo de escrita; revogar tira as candidatas
não confirmadas e não toca a associação já confirmada (leitura do aceite do DAP); corrigir
o hint troca o elemento de referência; renomear o elemento move o casamento junto; e um job
sem declaração nenhuma grava `associations_json` byte a byte igual ao de antes da feature.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, cast

from fastapi.testclient import TestClient
from sqlalchemy import select

from croquito_api.database import Database, ReviewRevisionRecord
from tests.api.test_api import _client, _current_decision_id, _headers, _seed_review_session
from tests.api.test_review_element_identity import (
    PROPOSAL_A,
    PROPOSAL_B,
    _declare,
    _relabel,
    _revoke,
)

#: A cota-balão da fixture: "C=56,00 m" com o hint estruturado "B", no canto oposto ao
#: "elemento B" sintético — o caso real do Campo da Toca reduzido a três leituras.
COTA_BALAO = "rd_5555555555555555"

#: O vizinho da cota-balão, e a única candidata que ela tem antes de existir identidade.
CONTORNO_VIZINHO = "vp_4444444444444444"

#: Proposta que o "elemento B" não contém — serve para provar que o portão continua fechado.
CIRCULO_ALHEIO = "vp_3333333333333333"


def _associations(client: TestClient, job_id: Any, version: int) -> dict[str, Any]:
    database = cast(Database, cast(Any, client.app).state.database)
    with database.sessions.begin() as session:
        record = session.scalar(
            select(ReviewRevisionRecord).where(
                ReviewRevisionRecord.job_id == str(job_id),
                ReviewRevisionRecord.version == version,
            )
        )
        assert record is not None
        return dict(record.associations_json)


def _selected(client: TestClient, job_id: Any, version: int) -> dict[str, str]:
    database = cast(Database, cast(Any, client.app).state.database)
    with database.sessions.begin() as session:
        record = session.scalar(
            select(ReviewRevisionRecord).where(
                ReviewRevisionRecord.job_id == str(job_id),
                ReviewRevisionRecord.version == version,
            )
        )
        assert record is not None
        return dict(record.selected_associations_json)


def _identity_pairs(associations: dict[str, Any]) -> list[tuple[str, str]]:
    return [
        (candidate["reading_id"], candidate["proposal_id"])
        for candidate in associations["candidates"]
        if candidate["relation"] == "element_identity"
    ]


def _other_candidates(associations: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        candidate
        for candidate in associations["candidates"]
        if candidate["relation"] != "element_identity"
    ]


def _decide_balloon(
    client: TestClient,
    job_id: Any,
    *,
    base_version: int,
    key: str,
    **overrides: Any,
) -> Any:
    payload: dict[str, Any] = {
        "reading_id": COTA_BALAO,
        "action": "confirm",
        "justification": "Cota-balão conferida contra a folha original.",
        "annotation": True,
    }
    payload.update(overrides)
    return client.post(
        f"/v1/jobs/{job_id}/review/decisions",
        headers={**_headers("tenant-a"), "Idempotency-Key": key},
        json={"base_version": base_version, "decisions": [payload]},
    )


def test_declarar_o_elemento_cunha_a_candidata_de_cada_proposta_dele(tmp_path: Path) -> None:
    """Critério 1: duas propostas declaradas, duas candidatas novas, e nada mais muda."""
    client = _client(tmp_path)
    job_id = _seed_review_session(client, balloon_reading=True)
    antes = _associations(client, job_id, 1)

    response = _declare(
        client,
        job_id,
        proposal_ids=[PROPOSAL_A, PROPOSAL_B],
        base_version=1,
        key="declara-b",
        label="B",
    )

    assert response.status_code == 200
    depois = _associations(client, job_id, 2)
    assert _identity_pairs(antes) == []
    assert _identity_pairs(depois) == [(COTA_BALAO, PROPOSAL_A), (COTA_BALAO, PROPOSAL_B)]
    # As de proximidade saem intactas: a candidata por identidade se SOMA a elas.
    assert _other_candidates(depois) == _other_candidates(antes)
    nova = next(
        candidate
        for candidate in depois["candidates"]
        if candidate["relation"] == "element_identity"
    )
    assert nova["precision"] == "unresolved"
    assert nova["export"] is False
    # A distância real viaja como fato — 236 px, muito além do alcance do funil (64,9 px
    # nesta imagem): é exatamente por isso que a proximidade nunca alcançaria o referente.
    assert nova["pixel_distance"] > 200
    assert nova["proximity_score"] == 0.0
    assert nova["association_confidence"] == 0.0


def test_a_candidata_por_identidade_e_confirmavel_pelo_portao_de_sempre(tmp_path: Path) -> None:
    """Critério 3: nenhum caminho novo de escrita — o portão único aceita, e só ele."""
    client = _client(tmp_path)
    job_id = _seed_review_session(client, balloon_reading=True)
    assert (
        _declare(
            client,
            job_id,
            proposal_ids=[PROPOSAL_A, PROPOSAL_B],
            base_version=1,
            key="declara-b",
            label="B",
        ).status_code
        == 200
    )

    alheia = _decide_balloon(
        client,
        job_id,
        base_version=2,
        key="confirma-alheia",
        annotation=False,
        association_proposal_id=CIRCULO_ALHEIO,
    )
    confirmada = _decide_balloon(
        client,
        job_id,
        base_version=2,
        key="confirma-identidade",
        annotation=False,
        association_proposal_id=PROPOSAL_A,
    )

    # Proposta que não é candidata desta leitura continua recusada pelo mesmo portão.
    assert alheia.status_code == 422
    assert alheia.json()["detail"]["code"] == "DOMAIN_VALIDATION_FAILED"
    assert confirmada.status_code == 200
    assert _selected(client, job_id, 3)[COTA_BALAO] == PROPOSAL_A


def test_revogar_tira_a_candidata_solta_e_preserva_a_associacao_confirmada(
    tmp_path: Path,
) -> None:
    """Critério 4, as duas metades — leitura confirmada no aceite do DAP.

    A candidata que SUSTENTA a associação confirmada fica: tirá-la deixaria
    `selected_associations` apontando para um par que não é mais candidato da leitura, e a
    próxima retificação daquela cota morreria no portão sem ninguém ter decidido nada.
    """
    client = _client(tmp_path)
    job_id = _seed_review_session(client, balloon_reading=True)
    assert (
        _declare(
            client,
            job_id,
            proposal_ids=[PROPOSAL_A, PROPOSAL_B],
            base_version=1,
            key="declara-b",
            label="B",
        ).status_code
        == 200
    )
    assert (
        _decide_balloon(
            client,
            job_id,
            base_version=2,
            key="confirma-identidade",
            annotation=False,
            association_proposal_id=PROPOSAL_A,
        ).status_code
        == 200
    )

    revogado = _revoke(client, job_id, element_ref="EL-001", base_version=3, key="revoga-b")

    assert revogado.status_code == 200
    assert _identity_pairs(_associations(client, job_id, 4)) == [(COTA_BALAO, PROPOSAL_A)]
    assert _selected(client, job_id, 4)[COTA_BALAO] == PROPOSAL_A


def test_revogar_sem_confirmacao_devolve_o_conjunto_ao_estado_de_antes(tmp_path: Path) -> None:
    client = _client(tmp_path)
    job_id = _seed_review_session(client, balloon_reading=True)
    antes = _associations(client, job_id, 1)
    assert (
        _declare(
            client,
            job_id,
            proposal_ids=[PROPOSAL_A, PROPOSAL_B],
            base_version=1,
            key="declara-b",
            label="B",
        ).status_code
        == 200
    )

    assert (
        _revoke(client, job_id, element_ref="EL-001", base_version=2, key="revoga-b").status_code
        == 200
    )

    assert _associations(client, job_id, 3) == antes


def test_renomear_o_elemento_move_o_casamento_junto(tmp_path: Path) -> None:
    """O rótulo é por onde o hint procura: renomear "B" para "C" desfaz o casamento."""
    client = _client(tmp_path)
    job_id = _seed_review_session(client, balloon_reading=True)
    assert (
        _declare(
            client,
            job_id,
            proposal_ids=[PROPOSAL_A],
            base_version=1,
            key="declara-b",
            label="B",
        ).status_code
        == 200
    )

    renomeado = _relabel(
        client, job_id, element_ref="EL-001", label="C", base_version=2, key="renomeia"
    )

    assert renomeado.status_code == 200
    assert _identity_pairs(_associations(client, job_id, 2)) == [(COTA_BALAO, PROPOSAL_A)]
    assert _identity_pairs(_associations(client, job_id, 3)) == []


def test_o_rotulo_descritivo_alcanca_o_balao_pela_palavra_inteira(tmp_path: Path) -> None:
    """A decisão da normalização, exercida ponta a ponta: o hint "B" acha "grade B"."""
    client = _client(tmp_path)
    job_id = _seed_review_session(client, balloon_reading=True)

    assert (
        _declare(
            client,
            job_id,
            proposal_ids=[PROPOSAL_A],
            base_version=1,
            key="declara-grade-b",
            label="grade B",
        ).status_code
        == 200
    )

    assert _identity_pairs(_associations(client, job_id, 2)) == [(COTA_BALAO, PROPOSAL_A)]


def test_corrigir_o_hint_na_decisao_e_na_retificacao_recunha_as_candidatas(
    tmp_path: Path,
) -> None:
    """Critério 5, nos dois caminhos da T1: o "B" errado vira "C", e depois volta.

    A cota-balão é confirmada como anotação da folha (o caminho honesto de hoje) para que o
    teste isole a correção do hint do ato de associar.
    """
    client = _client(tmp_path)
    job_id = _seed_review_session(client, balloon_reading=True)
    assert (
        _declare(
            client, job_id, proposal_ids=[PROPOSAL_A], base_version=1, key="declara-b", label="B"
        ).status_code
        == 200
    )
    assert (
        _declare(
            client,
            job_id,
            proposal_ids=[CIRCULO_ALHEIO],
            base_version=2,
            key="declara-c",
            label="C",
        ).status_code
        == 200
    )
    assert _identity_pairs(_associations(client, job_id, 3)) == [(COTA_BALAO, PROPOSAL_A)]

    corrigido = _decide_balloon(
        client, job_id, base_version=3, key="decide-c", target_entity_label="C"
    )
    assert corrigido.status_code == 200
    assert _identity_pairs(_associations(client, job_id, 4)) == [(COTA_BALAO, CIRCULO_ALHEIO)]

    retificado = client.post(
        f"/v1/jobs/{job_id}/review/rectifications",
        headers={**_headers("tenant-a"), "Idempotency-Key": "retifica-b"},
        json={
            "base_version": 4,
            "rectifications": [
                {
                    "reading_id": COTA_BALAO,
                    "action": "confirm",
                    "rectifies_decision_id": _current_decision_id(client, job_id, COTA_BALAO),
                    "justification": "A letra do balão é B; a leitura anterior trocou.",
                    "annotation": True,
                    "target_entity_label": "B",
                }
            ],
        },
    )

    assert retificado.status_code == 200
    assert _identity_pairs(_associations(client, job_id, 5)) == [(COTA_BALAO, PROPOSAL_A)]


def test_sem_declaracao_nenhuma_o_conjunto_persistido_e_o_de_hoje(tmp_path: Path) -> None:
    """Critério 7: o controle da tarefa — a feature desligada não muda um byte.

    Os dois caminhos que a T4 tocou são exercidos: a decisão (que agora recunha depois de
    decidir) e o ato de identidade (que agora grava candidatas em vez de copiá-las), aqui
    com um rótulo que hint nenhum do pacote alcança.
    """
    client = _client(tmp_path)
    job_id = _seed_review_session(client, balloon_reading=True)
    antes = _associations(client, job_id, 1)

    assert (
        _decide_balloon(client, job_id, base_version=1, key="decide-sem-elemento").status_code
        == 200
    )
    assert (
        _declare(
            client,
            job_id,
            proposal_ids=[PROPOSAL_A],
            base_version=2,
            key="declara-z",
            label="Z",
        ).status_code
        == 200
    )

    assert _associations(client, job_id, 2) == antes
    assert _associations(client, job_id, 3) == antes
