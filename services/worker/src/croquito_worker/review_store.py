"""Escrita da primeira revisão de leitura; evidência autorizada nunca é sobrescrita."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.engine import Connection, RowMapping

from croquito_core.ids import new_uuid7
from croquito_worker.association import AssociationSet
from croquito_worker.association_confidence import confidence_shadow_json
from croquito_worker.auto_association import (
    AutoDecision,
    apply_auto_association,
    auto_association_mode,
)
from croquito_worker.rectangle_solver import RectangleSolveRequest, solve_rectangle
from croquito_worker.review import ReviewPacket
from croquito_worker.vision import VisionProposalSet


class ReviewAlreadyExistsError(RuntimeError):
    """The job already carries a review revision; seeding refuses to replace evidence."""


def _solver_reading_ids(solver_request: RectangleSolveRequest | None) -> frozenset[str]:
    """Leituras que o pedido do solver usa como geometria de planta desta revisão.

    O `kind` classifica a leitura; este pedido a DESIGNA. Uma leitura citada aqui vira
    lado ou círculo do retângulo com precisão exata (`rectangle_solver`), qualquer que
    seja o `kind` — inclusive `height`, que o pedido aceita como o lado vertical. Ela é
    cota de planta por construção e o tier de anotação, cujo fundamento é que o erro não
    alcança geometria, não pode alcançá-la (ADR-0044, D2). O tier de dupla testemunha
    continua valendo para ela, como sempre valeu.
    """
    if solver_request is None:
        return frozenset()
    return frozenset(
        reading_id
        for reading_id in (
            solver_request.width_reading_id,
            solver_request.height_reading_id,
            solver_request.centre_circle_reading_id,
        )
        if reading_id is not None
    )


@dataclass(frozen=True, slots=True)
class SeededReviewRevision:
    """O que a revisão 1 ficou sendo depois de gravada — o que foi persistido, não o pedido.

    Com o modo automático desligado (o padrão), `packet` e `solver_blockers` são
    exatamente o que o chamador passou e `auto_decisions` é vazio.
    """

    review_id: UUID
    packet: ReviewPacket
    selected_associations: dict[str, str]
    solver_blockers: tuple[str, ...]
    auto_decisions: tuple[AutoDecision, ...]


def json_expression(dialect_name: str, name: str) -> str:
    """Casts a bound JSON string to the column type expected by the dialect."""
    if dialect_name == "postgresql":
        return f"CAST(:{name} AS JSONB)"
    return f"json(:{name})"


def json_column(value: Any) -> Any:
    """Raw SQL returns JSON as text on SQLite and as a structure on PostgreSQL."""
    return json.loads(value) if isinstance(value, str) else value


def _json_parameter(parameters: dict[str, Any], dialect: str, name: str, value: Any) -> str:
    """Binds one JSON column, emitting the literal NULL when there is nothing to store."""
    if value is None:
        return "NULL"
    parameters[name] = json.dumps(value, ensure_ascii=False)
    return json_expression(dialect, name)


def insert_review_revision_v1(
    connection: Connection,
    *,
    tenant_id: str,
    job_id: str,
    packet: ReviewPacket,
    associations: AssociationSet,
    proposals: VisionProposalSet,
    evidence_refs: dict[str, Any],
    solver_request: RectangleSolveRequest | None,
    solver_blockers: list[str],
    required_blocker_codes: list[str],
    required_criteria_texts: dict[str, str],
    created_by: str,
) -> SeededReviewRevision:
    """Persists review revision 1 for a job, refusing to overwrite an existing one.

    É aqui que a revisão 1 nasce com o shadow de confiança computado (F-029): este caminho
    lista as colunas uma a uma e, antes desta task, deixava `confidence_shadow_json` no
    default do servidor — a revisão inicial de todo job entrava no banco sem o registro
    que a calibração precisa, e nenhuma revisão posterior o reconstituía para o instante
    em que ela nasceu.

    Com a dupla chave do ADR-0041 presente, é também aqui que a decisão de ator-máquina
    acontece: um único ponto de escrita para os dois caminhos do worker (a extração por
    provider e a semeadura local), porque duas cópias da regra divergiriam em silêncio
    justamente onde o toque humano deixa de existir.
    """
    existing = connection.execute(
        text(
            "SELECT id FROM review_revisions "
            "WHERE job_id = :job_id AND tenant_id = :tenant_id LIMIT 1"
        ),
        {"job_id": job_id, "tenant_id": tenant_id},
    ).scalar_one_or_none()
    if existing is not None:
        raise ReviewAlreadyExistsError(job_id)

    mode = auto_association_mode()
    outcome = (
        apply_auto_association(
            packet,
            associations,
            mode=mode,
            plan_geometry_reading_ids=_solver_reading_ids(solver_request),
        )
        if mode is not None
        else None
    )
    stored_packet = outcome.packet if outcome is not None else packet
    selected_associations = outcome.selected_associations if outcome is not None else {}
    auto_decisions = outcome.decisions if outcome is not None else ()
    stored_blockers = tuple(solver_blockers)
    if auto_decisions and solver_request is not None:
        # Os blockers gravados descrevem o pacote gravado. Sem isto a revisão diria
        # "falta confirmação humana" sobre uma leitura que ela mesma já registra como
        # decidida e associada — e a pessoa não teria como resolver essa contradição:
        # decidir de novo é `READING_ALREADY_DECIDED`.
        stored_blockers = tuple(
            solve_rectangle(
                stored_packet, solver_request, confirmed_associations=selected_associations
            ).blockers
        )

    # O shadow descreve o que ficou GRAVADO, como no caminho da API: ele é computado sobre
    # o pacote persistido, já com as auto-decisões dentro. As confianças citadas em
    # `auto_decisions` são outra coisa e não se confundem com estas: são as do INSTANTE do
    # ato, e é por elas que a auditoria do pacote responde.
    shadow = confidence_shadow_json(stored_packet, associations, ())
    if auto_decisions:
        # A lista nominal fica NO shadow da revisão em que o ato aconteceu: a auditoria do
        # export cita cada cota que entrou sem toque humano, e o `decision_id` amarra a
        # citação à decisão gravada no pacote — retificada depois, a citação deixa de
        # valer sozinha, sem ninguém precisar limpar registro nenhum.
        shadow["auto_decisions"] = [decision.as_json() for decision in auto_decisions]

    dialect = connection.engine.dialect.name
    review_id = new_uuid7()
    parameters: dict[str, Any] = {
        "id": str(review_id),
        "tenant_id": tenant_id,
        "job_id": job_id,
        "packet": json.dumps(stored_packet.model_dump(mode="json")),
        "associations": json.dumps(associations.model_dump(mode="json")),
        "proposals": json.dumps(proposals.model_dump(mode="json")),
        "selected_associations": json.dumps(selected_associations),
        "declared_chains": json.dumps([]),
        # A revisão 1 nasce sem identidade de elemento declarada: identidade é ato humano
        # (F-051, ADR-0063 decisão 1), e a semente do worker não pratica ato nenhum. Vazia e
        # EXPLÍCITA, e não deixada no default do servidor, pelo mesmo motivo do shadow: este
        # caminho lista as colunas uma a uma, e o que ele não escreve some da revista de
        # quem lê o INSERT.
        "element_declarations": json.dumps([]),
        "confidence_shadow": json.dumps(shadow),
        "evidence_refs": json.dumps(evidence_refs),
        "solver_blockers": json.dumps(list(stored_blockers)),
        "required_blockers": json.dumps(required_blocker_codes),
        "required_criteria_texts": json.dumps(required_criteria_texts, ensure_ascii=False),
        "created_by": created_by,
    }
    if solver_request is None:
        solver_request_expression = "NULL"
    else:
        solver_request_expression = json_expression(dialect, "solver_request")
        parameters["solver_request"] = json.dumps(solver_request.model_dump(mode="json"))

    connection.execute(
        text(
            "INSERT INTO review_revisions "
            "(id, tenant_id, job_id, version, parent_review_id, packet_json, "
            "associations_json, proposals_json, selected_associations_json, "
            "declared_chains_json, element_declarations_json, confidence_shadow_json, "
            "calibration_json, proposal_decisions_json, "
            "evidence_refs_json, "
            "solver_request_json, solver_blockers_json, required_blocker_codes_json, "
            "required_criteria_texts_json, scene_revision_id, created_by, created_at) "
            "VALUES (:id, :tenant_id, :job_id, 1, NULL, "
            f"{json_expression(dialect, 'packet')}, "
            f"{json_expression(dialect, 'associations')}, "
            f"{json_expression(dialect, 'proposals')}, "
            f"{json_expression(dialect, 'selected_associations')}, "
            f"{json_expression(dialect, 'declared_chains')}, "
            f"{json_expression(dialect, 'element_declarations')}, "
            f"{json_expression(dialect, 'confidence_shadow')}, "
            "NULL, NULL, "
            f"{json_expression(dialect, 'evidence_refs')}, "
            f"{solver_request_expression}, "
            f"{json_expression(dialect, 'solver_blockers')}, "
            f"{json_expression(dialect, 'required_blockers')}, "
            f"{json_expression(dialect, 'required_criteria_texts')}, NULL, "
            ":created_by, CURRENT_TIMESTAMP)"
        ),
        parameters,
    )
    return SeededReviewRevision(
        review_id=review_id,
        packet=stored_packet,
        selected_associations=selected_associations,
        solver_blockers=stored_blockers,
        auto_decisions=auto_decisions,
    )


def insert_next_review_revision(
    connection: Connection,
    *,
    tenant_id: str,
    job_id: str,
    base_review: RowMapping,
    review_id: UUID,
    created_by: str,
    proposals_json: dict[str, Any],
    associations_json: dict[str, Any],
    calibration_json: dict[str, Any] | None,
    scene_revision_id: str | None,
) -> None:
    """Persists `base_review.version + 1`, copying every other column from it verbatim.

    Used by `refresh-proposals`, which never touches decisions, the packet or evidence
    refs: only the proposal snapshot, the recomputed association candidates and, when a
    calibration no longer holds, the calibration and the scene it points at change.
    """
    dialect = connection.engine.dialect.name
    parameters: dict[str, Any] = {
        "id": str(review_id),
        "tenant_id": tenant_id,
        "job_id": job_id,
        "version": int(base_review["version"]) + 1,
        "parent_review_id": base_review["id"],
        "created_by": created_by,
        "scene_revision_id": scene_revision_id,
    }
    columns = {
        "packet_json": json_column(base_review["packet_json"]),
        "associations_json": associations_json,
        "proposals_json": proposals_json,
        "selected_associations_json": json_column(base_review["selected_associations_json"]),
        # A cadeia declarada é ato humano da revisão anterior e viaja verbatim: o refresh
        # de propostas não decide nada sobre cotas, e perder a declaração aqui apagaria em
        # silêncio o que uma pessoa afirmou.
        "declared_chains_json": json_column(base_review["declared_chains_json"]),
        # Identidade de elemento é ato humano da revisão anterior e viaja verbatim, pelo
        # mesmo motivo da cadeia declarada: o refresh de propostas não declara nem revoga
        # identidade nenhuma, e perdê-la aqui apagaria em silêncio o que uma pessoa afirmou.
        #
        # `or []` porque a coluna é NOT NULL: uma linha vinda de banco onde a migration
        # `0031` correu sem o default gravaria `NULL` de volta e estouraria na integridade,
        # em vez de dizer a verdade sobre ela — que ninguém declarou identidade nenhuma.
        "element_declarations_json": json_column(base_review["element_declarations_json"]) or [],
        "field_witnesses_json": json_column(base_review["field_witnesses_json"]),
        "field_observations_json": json_column(base_review["field_observations_json"]),
        "calibration_json": calibration_json,
        "proposal_decisions_json": json_column(base_review["proposal_decisions_json"]),
        "trace_acceptance_json": json_column(base_review["trace_acceptance_json"]),
        "evidence_refs_json": json_column(base_review["evidence_refs_json"]),
        "solver_request_json": json_column(base_review["solver_request_json"]),
        "solver_blockers_json": json_column(base_review["solver_blockers_json"]),
        "required_blocker_codes_json": json_column(base_review["required_blocker_codes_json"]),
        "required_criteria_texts_json": json_column(base_review["required_criteria_texts_json"]),
    }
    expressions = {
        name: _json_parameter(parameters, dialect, name, value) for name, value in columns.items()
    }
    connection.execute(
        text(
            "INSERT INTO review_revisions "
            "(id, tenant_id, job_id, version, parent_review_id, packet_json, "
            "associations_json, proposals_json, selected_associations_json, "
            "declared_chains_json, element_declarations_json, "
            "field_witnesses_json, field_observations_json, "
            "calibration_json, proposal_decisions_json, trace_acceptance_json, "
            "evidence_refs_json, solver_request_json, solver_blockers_json, "
            "required_blocker_codes_json, required_criteria_texts_json, "
            "scene_revision_id, created_by, created_at) "
            "VALUES (:id, :tenant_id, :job_id, :version, :parent_review_id, "
            f"{expressions['packet_json']}, {expressions['associations_json']}, "
            f"{expressions['proposals_json']}, {expressions['selected_associations_json']}, "
            f"{expressions['declared_chains_json']}, "
            f"{expressions['element_declarations_json']}, "
            f"{expressions['field_witnesses_json']}, "
            f"{expressions['field_observations_json']}, "
            f"{expressions['calibration_json']}, {expressions['proposal_decisions_json']}, "
            f"{expressions['trace_acceptance_json']}, {expressions['evidence_refs_json']}, "
            f"{expressions['solver_request_json']}, {expressions['solver_blockers_json']}, "
            f"{expressions['required_blocker_codes_json']}, "
            f"{expressions['required_criteria_texts_json']}, "
            ":scene_revision_id, :created_by, CURRENT_TIMESTAMP)"
        ),
        parameters,
    )
