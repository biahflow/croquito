"""F-051 T2: o ato humano de identidade de elemento na REVISÃO, sobre propostas (ADR-0063).

O que estes testes protegem, em uma frase cada: o `element_ref` é cunhado pelo servidor e
recusado quando o cliente tenta escolhê-lo; o namespace é UM por job, nos dois sentidos
(cena → revisão e revisão → cena); um grupo só cita proposta que pertence ao snapshot da
revisão; o rótulo é único entre as identidades ativas do job e a recusa aponta o existente;
revogar registra o ato sem apagar a identidade do histórico, sem devolver o ref ao estoque e
**sem desfazer associação já confirmada**; renomear é ato declarado, não edição silenciosa;
as declarações são herdadas por atos que não têm nada com elas; e, sem declaração nenhuma, o
caminho da revisão responde como hoje.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any, cast

from fastapi.testclient import TestClient
from sqlalchemy import delete, select

from croquito_api.database import AuditRecord, Database, ReviewRevisionRecord
from tests.api.test_api import _client, _headers, _seed_review_session

TENANT = "tenant-a"

#: Propostas do `_seed_review_session`: duas linhas, um círculo e um contorno. As duas
#: primeiras são o "elemento B" sintético destes testes.
PROPOSAL_A = "vp_1111111111111111"
PROPOSAL_B = "vp_2222222222222222"

#: Id BEM formado que o snapshot da revisão não conhece — erro de domínio, não de formato.
PROPOSAL_FORA_DO_SNAPSHOT = "vp_ffffffffffffffff"


def _database(client: TestClient) -> Database:
    return cast(Database, cast(Any, client.app).state.database)


def _declare(
    client: TestClient,
    job_id: Any,
    *,
    proposal_ids: list[str],
    base_version: int,
    key: str,
    tenant_id: str = TENANT,
    roles: str = "engineer",
    element_ref: str | None = None,
    label: str | None = None,
    reason: str = "Estas propostas são o elemento B da folha.",
) -> Any:
    body: dict[str, Any] = {
        "base_version": base_version,
        "proposal_ids": proposal_ids,
        "reason": reason,
    }
    if element_ref is not None:
        body["element_ref"] = element_ref
    if label is not None:
        body["label"] = label
    return client.post(
        f"/v1/jobs/{job_id}/review/elements",
        headers={**_headers(tenant_id, roles), "Idempotency-Key": key},
        json=body,
    )


def _revoke(
    client: TestClient,
    job_id: Any,
    *,
    element_ref: str,
    base_version: int,
    key: str,
    reason: str = "Agrupamento errado, refazer.",
) -> Any:
    return client.post(
        f"/v1/jobs/{job_id}/review/elements/revocations",
        headers={**_headers(TENANT), "Idempotency-Key": key},
        json={"base_version": base_version, "element_ref": element_ref, "reason": reason},
    )


def _relabel(
    client: TestClient,
    job_id: Any,
    *,
    element_ref: str,
    label: str,
    base_version: int,
    key: str,
    reason: str = "Nome conferido com a folha.",
) -> Any:
    return client.post(
        f"/v1/jobs/{job_id}/review/elements/labels",
        headers={**_headers(TENANT), "Idempotency-Key": key},
        json={
            "base_version": base_version,
            "element_ref": element_ref,
            "label": label,
            "reason": reason,
        },
    )


def _declare_scene_element(client: TestClient, job_id: Any, *, base_version: int, key: str) -> Any:
    """O ato de identidade da CENA (F-047 T2), usado para provar o namespace comum."""
    return client.post(
        f"/v1/jobs/{job_id}/elements",
        headers={**_headers(TENANT), "Idempotency-Key": key},
        json={
            "base_version": base_version,
            "entity_ids": ["00000000-0000-7000-8000-000000000401"],
            "reason": "Este traço é a quadra.",
        },
    )


def _stored_declarations(client: TestClient, job_id: Any, version: int) -> list[dict[str, Any]]:
    with _database(client).sessions.begin() as session:
        record = session.scalar(
            select(ReviewRevisionRecord).where(
                ReviewRevisionRecord.job_id == str(job_id),
                ReviewRevisionRecord.version == version,
            )
        )
        assert record is not None
        return [dict(item) for item in record.element_declarations_json]


def test_declaracao_cunha_o_ref_no_servidor_e_registra_papel_e_instante(tmp_path: Path) -> None:
    client = _client(tmp_path)
    job_id = _seed_review_session(client)
    before = datetime.now(UTC)

    response = _declare(
        client,
        job_id,
        proposal_ids=[PROPOSAL_A, PROPOSAL_B],
        base_version=1,
        key="declare-1",
        label="B",
    )

    assert response.status_code == 200
    body = response.json()
    assert body["act"] == "declared"
    assert body["element_ref"] == "EL-001"
    assert body["label"] == "B"
    assert body["proposal_ids"] == [PROPOSAL_A, PROPOSAL_B]
    # O papel profissional do ato, nunca o subject de quem o praticou.
    assert body["acted_by_role"] == "engineer"
    assert "reviewer" not in response.text
    acted_at = datetime.fromisoformat(body["acted_at"])
    assert acted_at.tzinfo is not None and acted_at >= before
    assert body["review_version"] == 2
    assert body["declarations"] == [
        {
            "element_ref": "EL-001",
            "label": "B",
            "proposal_ids": [PROPOSAL_A, PROPOSAL_B],
            "status": "active",
            "declared_by_role": "engineer",
            "declared_at": body["acted_at"],
            "revoked_by_role": None,
            "revoked_at": None,
        }
    ]

    # A revisão de origem nunca é editada; a nova carrega a declaração e o autor.
    assert _stored_declarations(client, job_id, 1) == []
    gravadas = _stored_declarations(client, job_id, 2)
    assert gravadas[0]["element_ref"] == "EL-001"
    assert gravadas[0]["declared_by"] == "reviewer"
    with _database(client).sessions.begin() as session:
        audit = session.scalars(
            select(AuditRecord).where(AuditRecord.action == "REVIEW_ELEMENT_IDENTITY_DECLARED")
        ).all()
        assert len(audit) == 1
        assert audit[0].metadata_json["element_ref"] == "EL-001"
        assert audit[0].metadata_json["labeled"] is True
        # O TEXTO do rótulo é conteúdo do croqui e não entra em auditoria.
        assert audit[0].metadata_json.get("label") is None


def test_element_ref_mandado_pelo_cliente_recusa_com_codigo_estavel(tmp_path: Path) -> None:
    client = _client(tmp_path)
    job_id = _seed_review_session(client)

    response = _declare(
        client,
        job_id,
        proposal_ids=[PROPOSAL_A],
        base_version=1,
        key="declare-choose",
        element_ref="EL-042",
    )

    assert response.status_code == 422
    assert response.headers["content-type"].startswith("application/problem+json")
    assert response.json()["code"] == "ELEMENT_REF_NOT_ASSIGNABLE"
    assert _stored_declarations(client, job_id, 1) == []


def test_o_namespace_e_um_so_por_job_da_cena_para_a_revisao(tmp_path: Path) -> None:
    """Cena cunhou `EL-001`; a revisão do mesmo job cunha `EL-002`, nunca `EL-001`."""
    client = _client(tmp_path)
    job_id = _seed_review_session(client)

    na_cena = _declare_scene_element(client, job_id, base_version=1, key="cena-1")
    assert na_cena.status_code == 200
    assert na_cena.json()["element_ref"] == "EL-001"

    na_revisao = _declare(
        client, job_id, proposal_ids=[PROPOSAL_A], base_version=1, key="revisao-1"
    )

    assert na_revisao.status_code == 200
    assert na_revisao.json()["element_ref"] == "EL-002"


def test_o_namespace_e_um_so_por_job_da_revisao_para_a_cena(tmp_path: Path) -> None:
    """O sentido oposto: a revisão cunhou `EL-001`, e a cena continua de `EL-002`."""
    client = _client(tmp_path)
    job_id = _seed_review_session(client)

    na_revisao = _declare(
        client, job_id, proposal_ids=[PROPOSAL_A], base_version=1, key="revisao-1"
    )
    assert na_revisao.status_code == 200
    assert na_revisao.json()["element_ref"] == "EL-001"

    na_cena = _declare_scene_element(client, job_id, base_version=1, key="cena-1")

    assert na_cena.status_code == 200
    assert na_cena.json()["element_ref"] == "EL-002"


def test_grupo_sem_proposta_ou_com_proposta_de_fora_do_snapshot_recusa(tmp_path: Path) -> None:
    client = _client(tmp_path)
    job_id = _seed_review_session(client)

    vazio = client.post(
        f"/v1/jobs/{job_id}/review/elements",
        headers={**_headers(TENANT), "Idempotency-Key": "vazio"},
        json={"base_version": 1, "proposal_ids": [], "reason": "Sem proposta nenhuma."},
    )
    fora = _declare(
        client, job_id, proposal_ids=[PROPOSAL_FORA_DO_SNAPSHOT], base_version=1, key="fora"
    )
    repetida = _declare(
        client, job_id, proposal_ids=[PROPOSAL_A, PROPOSAL_A], base_version=1, key="repetida"
    )

    assert vazio.status_code == 422
    assert fora.status_code == 422
    assert fora.json()["code"] == "DOMAIN_VALIDATION_FAILED"
    assert fora.json()["detail"]["details"]["proposal_ids"] == [PROPOSAL_FORA_DO_SNAPSHOT]
    assert repetida.status_code == 422
    assert repetida.json()["code"] == "DOMAIN_VALIDATION_FAILED"
    assert _stored_declarations(client, job_id, 1) == []


def test_proposta_ja_declarada_exige_revogar_antes_de_mudar_de_elemento(tmp_path: Path) -> None:
    client = _client(tmp_path)
    job_id = _seed_review_session(client)
    _declare(client, job_id, proposal_ids=[PROPOSAL_A], base_version=1, key="d1")

    response = _declare(
        client, job_id, proposal_ids=[PROPOSAL_A, PROPOSAL_B], base_version=2, key="d2"
    )

    assert response.status_code == 409
    assert response.json()["code"] == "ELEMENT_ALREADY_DECLARED"
    assert response.json()["detail"]["details"]["proposal_ids"] == [PROPOSAL_A]


def test_rotulo_repetido_no_job_recusa_apontando_o_elemento_existente(tmp_path: Path) -> None:
    """Leitura confirmada no aceite do DAP: rótulo de elemento é único por job na revisão."""
    client = _client(tmp_path)
    job_id = _seed_review_session(client)
    _declare(client, job_id, proposal_ids=[PROPOSAL_A], base_version=1, key="d1", label="B")

    repetido = _declare(
        client, job_id, proposal_ids=[PROPOSAL_B], base_version=2, key="d2", label="B"
    )
    aparado = _declare(
        client, job_id, proposal_ids=[PROPOSAL_B], base_version=2, key="d3", label="  B  "
    )
    outro_nome = _declare(
        client, job_id, proposal_ids=[PROPOSAL_B], base_version=2, key="d4", label="C"
    )

    assert repetido.status_code == 409
    assert repetido.json()["code"] == "ELEMENT_LABEL_ALREADY_USED"
    assert repetido.json()["detail"]["details"]["element_ref"] == "EL-001"
    # O aparo acontece ANTES da conferência: `"  B  "` é o mesmo nome, não um nome novo.
    assert aparado.status_code == 409
    assert aparado.json()["code"] == "ELEMENT_LABEL_ALREADY_USED"
    # Nome diferente segue valendo, e cunha o ref seguinte.
    assert outro_nome.status_code == 200
    assert outro_nome.json()["element_ref"] == "EL-002"


def test_declarar_sem_rotulo_continua_valido(tmp_path: Path) -> None:
    """Identidade sem nome é identidade: o rótulo é opcional, como na cena."""
    client = _client(tmp_path)
    job_id = _seed_review_session(client)

    primeiro = _declare(client, job_id, proposal_ids=[PROPOSAL_A], base_version=1, key="d1")
    segundo = _declare(client, job_id, proposal_ids=[PROPOSAL_B], base_version=2, key="d2")

    assert primeiro.json()["label"] is None
    # Dois sem nome não colidem: a unicidade é do rótulo escrito, não da ausência dele.
    assert segundo.status_code == 200
    assert segundo.json()["element_ref"] == "EL-002"


def test_rotulo_so_de_espaco_recusa_com_codigo_estavel(tmp_path: Path) -> None:
    client = _client(tmp_path)
    job_id = _seed_review_session(client)

    response = _declare(
        client, job_id, proposal_ids=[PROPOSAL_A], base_version=1, key="branco", label="   "
    )

    assert response.status_code == 422
    assert response.json()["code"] == "ELEMENT_LABEL_INVALID"
    assert _stored_declarations(client, job_id, 1) == []


def test_revogar_registra_o_ato_sem_apagar_a_identidade_e_sem_reaproveitar_o_ref(
    tmp_path: Path,
) -> None:
    client = _client(tmp_path)
    job_id = _seed_review_session(client)
    _declare(client, job_id, proposal_ids=[PROPOSAL_A], base_version=1, key="d1", label="B")
    _declare(client, job_id, proposal_ids=[PROPOSAL_B], base_version=2, key="d2", label="C")

    revogado = _revoke(client, job_id, element_ref="EL-001", base_version=3, key="r1")

    assert revogado.status_code == 200
    body = revogado.json()
    assert body["act"] == "revoked"
    assert body["acted_by_role"] == "engineer"
    # Nem o subject de quem declarou nem o de quem revogou saem da API, embora os dois
    # fiquem gravados na declaração.
    assert "reviewer" not in revogado.text
    assert datetime.fromisoformat(body["acted_at"]).tzinfo is not None
    assert body["review_version"] == 4
    revogada = next(item for item in body["declarations"] if item["element_ref"] == "EL-001")
    # A identidade revogada NÃO sai do histórico: fica com o nome que teve e o carimbo.
    assert revogada["status"] == "revoked"
    assert revogada["label"] == "B"
    assert revogada["revoked_by_role"] == "engineer"
    assert revogada["revoked_at"] == body["acted_at"]
    assert (
        next(item for item in body["declarations"] if item["element_ref"] == "EL-002")["status"]
        == "active"
    )
    # A revisão que declarou continua dizendo o que dizia.
    assert _stored_declarations(client, job_id, 2)[0]["status"] == "active"

    # O ref revogado não volta ao estoque, e a proposta liberada pode ser declarada de novo.
    de_novo = _declare(client, job_id, proposal_ids=[PROPOSAL_A], base_version=4, key="d3")
    assert de_novo.json()["element_ref"] == "EL-003"

    with _database(client).sessions.begin() as session:
        audit = session.scalars(
            select(AuditRecord).where(AuditRecord.action == "REVIEW_ELEMENT_IDENTITY_REVOKED")
        ).all()
        assert len(audit) == 1
        assert audit[0].metadata_json["element_ref"] == "EL-001"


def test_revogar_nao_desfaz_associacao_ja_confirmada(tmp_path: Path) -> None:
    """Leitura confirmada no aceite do DAP: corrigir associação é retificação de decisão."""
    client = _client(tmp_path)
    job_id = _seed_review_session(client)
    confirmada = client.post(
        f"/v1/jobs/{job_id}/review/decisions",
        headers={**_headers(TENANT), "Idempotency-Key": "confirma-1"},
        json={
            "base_version": 1,
            "decisions": [
                {
                    "reading_id": "rd_1111111111111111",
                    "action": "confirm",
                    "justification": "Cota conferida na folha antes de declarar identidade.",
                    "association_proposal_id": PROPOSAL_A,
                }
            ],
        },
    )
    assert confirmada.status_code == 200
    selecionadas = confirmada.json()["selected_associations"]
    assert selecionadas == {"rd_1111111111111111": PROPOSAL_A}

    _declare(client, job_id, proposal_ids=[PROPOSAL_A], base_version=2, key="d1", label="B")
    _revoke(client, job_id, element_ref="EL-001", base_version=3, key="r1")

    depois = client.get(f"/v1/jobs/{job_id}/review", headers=_headers(TENANT))
    assert depois.status_code == 200
    assert depois.json()["selected_associations"] == selecionadas


def test_revogar_ou_renomear_o_que_nao_esta_declarado_recusa_com_codigo_estavel(
    tmp_path: Path,
) -> None:
    client = _client(tmp_path)
    job_id = _seed_review_session(client)
    _declare(client, job_id, proposal_ids=[PROPOSAL_A], base_version=1, key="d1")
    _revoke(client, job_id, element_ref="EL-001", base_version=2, key="r1")

    inexistente = _revoke(client, job_id, element_ref="EL-007", base_version=3, key="r2")
    ja_revogado = _revoke(client, job_id, element_ref="EL-001", base_version=3, key="r3")
    renomear_revogado = _relabel(
        client, job_id, element_ref="EL-001", label="B", base_version=3, key="rl-1"
    )

    for response in (inexistente, ja_revogado, renomear_revogado):
        assert response.status_code == 409
        assert response.json()["code"] == "ELEMENT_NOT_DECLARED"


def test_renomear_e_ato_declarado_com_papel_instante_e_revisao_nova(tmp_path: Path) -> None:
    client = _client(tmp_path)
    job_id = _seed_review_session(client)
    _declare(client, job_id, proposal_ids=[PROPOSAL_A], base_version=1, key="d1", label="B")

    response = _relabel(
        client, job_id, element_ref="EL-001", label="grade B", base_version=2, key="rl-1"
    )

    assert response.status_code == 200
    body = response.json()
    assert body["act"] == "relabeled"
    assert body["element_ref"] == "EL-001"
    assert body["label"] == "grade B"
    assert body["proposal_ids"] == [PROPOSAL_A]
    assert body["acted_by_role"] == "engineer"
    assert body["review_version"] == 3
    # A revisão anterior continua dizendo o nome que dizia: o passado não é reescrito.
    assert _stored_declarations(client, job_id, 2)[0]["label"] == "B"
    assert _stored_declarations(client, job_id, 3)[0]["label"] == "grade B"
    # Renomear não move proposta e não troca a identidade.
    assert _stored_declarations(client, job_id, 3)[0]["proposal_ids"] == [PROPOSAL_A]
    with _database(client).sessions.begin() as session:
        audit = session.scalars(
            select(AuditRecord).where(AuditRecord.action == "REVIEW_ELEMENT_LABEL_CHANGED")
        ).all()
        assert len(audit) == 1
        assert audit[0].metadata_json["element_ref"] == "EL-001"
        assert "grade B" not in str(audit[0].metadata_json)


def test_renomear_para_rotulo_ja_usado_recusa_apontando_o_existente(tmp_path: Path) -> None:
    client = _client(tmp_path)
    job_id = _seed_review_session(client)
    _declare(client, job_id, proposal_ids=[PROPOSAL_A], base_version=1, key="d1", label="B")
    _declare(client, job_id, proposal_ids=[PROPOSAL_B], base_version=2, key="d2", label="C")

    colidindo = _relabel(
        client, job_id, element_ref="EL-002", label="B", base_version=3, key="rl-1"
    )
    proprio_nome = _relabel(
        client, job_id, element_ref="EL-002", label="C", base_version=3, key="rl-2"
    )

    assert colidindo.status_code == 409
    assert colidindo.json()["code"] == "ELEMENT_LABEL_ALREADY_USED"
    assert colidindo.json()["detail"]["details"]["element_ref"] == "EL-001"
    # Renomear para o próprio nome não colide consigo mesmo.
    assert proprio_nome.status_code == 200


def test_os_tres_atos_exigem_idempotency_key_e_repetem_a_mesma_resposta(tmp_path: Path) -> None:
    client = _client(tmp_path)
    job_id = _seed_review_session(client)

    sem_chave = client.post(
        f"/v1/jobs/{job_id}/review/elements",
        headers={"Authorization": f"Bearer test:{TENANT}:reviewer:engineer"},
        json={"base_version": 1, "proposal_ids": [PROPOSAL_A], "reason": "Um elemento."},
    )
    assert sem_chave.status_code == 400

    primeira = _declare(client, job_id, proposal_ids=[PROPOSAL_A], base_version=1, key="same")
    repetida = _declare(client, job_id, proposal_ids=[PROPOSAL_A], base_version=1, key="same")

    assert primeira.status_code == 200
    assert repetida.json() == primeira.json()
    # O replay não cria revisão nova: a chave devolve o que já foi gravado.
    with _database(client).sessions.begin() as session:
        assert sorted(session.scalars(select(ReviewRevisionRecord.version))) == [1, 2]

    reusada = _declare(
        client,
        job_id,
        proposal_ids=[PROPOSAL_A],
        base_version=1,
        key="same",
        reason="Outro motivo agora.",
    )
    assert reusada.status_code == 409
    assert reusada.json()["code"] == "IDEMPOTENCY_KEY_REUSED"


def test_base_version_desatualizada_recusa_como_revision_conflict(tmp_path: Path) -> None:
    client = _client(tmp_path)
    job_id = _seed_review_session(client)
    _declare(client, job_id, proposal_ids=[PROPOSAL_A], base_version=1, key="d1")

    stale = _declare(client, job_id, proposal_ids=[PROPOSAL_B], base_version=1, key="d2")

    assert stale.status_code == 409
    assert stale.json()["code"] == "REVISION_CONFLICT"


def test_declaracao_concorrente_no_mesmo_numero_perde_a_corrida_sem_duplicar_o_ref(
    tmp_path: Path,
    monkeypatch: Any,
) -> None:
    """Duas declarações simultâneas cunham `EL-001`; a segunda a gravar colide e recusa.

    A corrida é encenada onde ela de fato acontece: entre ler a versão corrente e gravar a
    revisão nova. O patch grava, na MESMA transação e com a MESMA versão, a revisão que a
    outra requisição teria criado — o que faz `uq_review_version` reprovar o `flush` seguinte.
    """
    import croquito_api.main as api_main

    client = _client(tmp_path)
    job_id = _seed_review_session(client)
    original = api_main._next_element_ref

    def _mint_after_a_competing_revision(session: Any, **kwargs: Any) -> str:
        minted = original(session, **kwargs)
        current = session.scalar(
            select(ReviewRevisionRecord).where(ReviewRevisionRecord.job_id == str(job_id))
        )
        assert current is not None
        session.add(
            ReviewRevisionRecord(
                id="00000000-0000-7000-8000-0000000009f1",
                tenant_id=TENANT,
                job_id=str(job_id),
                version=2,
                parent_review_id=current.id,
                packet_json=current.packet_json,
                associations_json=current.associations_json,
                proposals_json=current.proposals_json,
                evidence_refs_json=current.evidence_refs_json,
                created_by="outra-sessao",
            )
        )
        session.flush()
        return minted

    monkeypatch.setattr(api_main, "_next_element_ref", _mint_after_a_competing_revision)
    response = _declare(client, job_id, proposal_ids=[PROPOSAL_A], base_version=1, key="race")

    assert response.status_code == 409
    assert response.json()["code"] == "REVISION_CONFLICT"
    # A recusa vem da COLISÃO na gravação, não da conferência de `base_version` — que já
    # passou. Sem esta asserção o teste continuaria verde se o guarda de corrida sumisse.
    assert response.json()["detail"]["detail"] == (
        "Um ato concorrente de identidade criou outra revisão."
    )
    with _database(client).sessions.begin() as session:
        declaradas = [
            item
            for declarations in session.scalars(
                select(ReviewRevisionRecord.element_declarations_json)
            )
            for item in declarations
        ]
        assert declaradas == []


def test_job_de_outro_tenant_responde_not_found(tmp_path: Path) -> None:
    client = _client(tmp_path)
    job_id = _seed_review_session(client)

    response = _declare(
        client, job_id, proposal_ids=[PROPOSAL_A], base_version=1, key="d1", tenant_id="tenant-b"
    )

    assert response.status_code == 404
    assert response.json()["code"] == "NOT_FOUND"


def test_papel_sem_qualificacao_profissional_nao_declara_identidade(tmp_path: Path) -> None:
    client = _client(tmp_path)
    job_id = _seed_review_session(client)

    declarar = _declare(
        client, job_id, proposal_ids=[PROPOSAL_A], base_version=1, key="d1", roles="cad_operator"
    )
    revogar = client.post(
        f"/v1/jobs/{job_id}/review/elements/revocations",
        headers={**_headers(TENANT, "cad_operator"), "Idempotency-Key": "r1"},
        json={"base_version": 1, "element_ref": "EL-001", "reason": "Sem papel."},
    )
    renomear = client.post(
        f"/v1/jobs/{job_id}/review/elements/labels",
        headers={**_headers(TENANT, "cad_operator"), "Idempotency-Key": "rl1"},
        json={"base_version": 1, "element_ref": "EL-001", "label": "B", "reason": "Sem papel."},
    )

    for response in (declarar, revogar, renomear):
        assert response.status_code == 403
        assert response.json()["code"] == "FORBIDDEN"


def test_ato_nao_relacionado_herda_as_declaracoes_intactas(tmp_path: Path) -> None:
    """Critério 5: quem cria revisão sucessora carrega a identidade sem saber que ela existe."""
    client = _client(tmp_path)
    job_id = _seed_review_session(client)
    declarada = _declare(
        client, job_id, proposal_ids=[PROPOSAL_A], base_version=1, key="d1", label="B"
    )
    assert declarada.status_code == 200
    gravadas = _stored_declarations(client, job_id, 2)

    # Um ato que não tem nada com identidade: decidir uma leitura.
    decisao = client.post(
        f"/v1/jobs/{job_id}/review/decisions",
        headers={**_headers(TENANT), "Idempotency-Key": "decide-1"},
        json={
            "base_version": 2,
            "decisions": [
                {
                    "reading_id": "rd_2222222222222222",
                    "action": "confirm",
                    "justification": "Altura conferida na folha sintética.",
                    "association_proposal_id": PROPOSAL_B,
                }
            ],
        },
    )

    assert decisao.status_code == 200
    assert _stored_declarations(client, job_id, 3) == gravadas


def test_sem_declaracao_nenhuma_o_caminho_da_revisao_responde_como_hoje(tmp_path: Path) -> None:
    """Critério 6: a F-051 é aditiva — nada da identidade vaza para a rota que já existia."""
    client = _client(tmp_path)
    job_id = _seed_review_session(client)

    antes = client.get(f"/v1/jobs/{job_id}/review", headers=_headers(TENANT))
    assert antes.status_code == 200
    assert "element_declaration" not in antes.text

    declarada = _declare(
        client, job_id, proposal_ids=[PROPOSAL_A], base_version=1, key="d1", label="B"
    )
    assert declarada.status_code == 200
    depois = client.get(f"/v1/jobs/{job_id}/review", headers=_headers(TENANT))

    assert depois.status_code == 200
    # Nenhum campo NOVO: a identidade declarada não aparece na resposta que já existia.
    assert depois.json().keys() == antes.json().keys()
    # E nenhum campo MUDADO, exceto os que toda revisão sucessora muda por si — a identidade
    # da revisão nova e a família de confiança, que `_carried_confidence_shadow` recomputa em
    # QUALQUER ato da revisão (a revisão 1 da fixture nasce sem shadow gravado). Nada disso é
    # efeito desta feature: é o comportamento de sempre da cadeia de revisões.
    esperado_mudar = {
        "review_id",
        "version",
        "confidence_shadow",
        "reading_confidences",
        "auto_association_rate",
        "review_rate",
    }
    diferentes = {chave for chave in antes.json() if antes.json()[chave] != depois.json()[chave]}
    assert diferentes <= esperado_mudar
    # O que a revisão de fato entrega — pacote, candidatas, associações confirmadas,
    # propostas, cena e blockers — sai byte a byte igual depois do ato de identidade.
    assert (
        diferentes
        & {
            "packet",
            "associations",
            "selected_associations",
            "proposals",
            "scene",
            "blockers",
        }
        == set()
    )
    assert depois.json()["version"] == 2
    assert "element_declaration" not in depois.text


def test_revisao_sem_snapshot_de_propostas_recusa_com_codigo_estavel(tmp_path: Path) -> None:
    client = _client(tmp_path)
    job_id = _seed_review_session(client)
    with _database(client).sessions.begin() as session:
        record = session.scalar(
            select(ReviewRevisionRecord).where(ReviewRevisionRecord.job_id == str(job_id))
        )
        assert record is not None
        record.proposals_json = None

    response = _declare(client, job_id, proposal_ids=[PROPOSAL_A], base_version=1, key="d1")

    assert response.status_code == 409
    assert response.json()["code"] == "PROPOSALS_NOT_READY"


def test_job_sem_revisao_de_leitura_recusa_como_job_not_ready(tmp_path: Path) -> None:
    """Job que existe mas ainda não tem pacote de revisão: recusa nomeada, nunca 404."""
    client = _client(tmp_path)
    job_id = _seed_review_session(client)
    with _database(client).sessions.begin() as session:
        session.execute(delete(ReviewRevisionRecord))

    response = _declare(client, job_id, proposal_ids=[PROPOSAL_A], base_version=1, key="d1")

    assert response.status_code == 409
    assert response.json()["code"] == "JOB_NOT_READY"
