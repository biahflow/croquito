import hashlib
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID

import pytest

from croquito_api.database import (
    Database,
    JobRecord,
    ProjectRecord,
    ReviewRevisionRecord,
    UploadRecord,
)
from croquito_worker.association_confidence import CONFIDENCE_SCORE_VERSION
from croquito_worker.auto_association import AutoAssociationConfigError
from croquito_worker.criteria import ScopeCriterion
from croquito_worker.local_queue import LocalWorkerSettings
from croquito_worker.review_seed import SeedInputs, SeedRefusedError, seed_review
from tests.bundles import (
    CIRCLE_READING_ID,
    ELEVATION_PROPOSAL_ID,
    ELEVATION_READING_ID,
    HEIGHT_PROPOSAL_ID,
    HEIGHT_READING_ID,
    WIDTH_PROPOSAL_ID,
    WIDTH_READING_ID,
    write_seed_bundle,
)
from tests.fakes import FakeObjectStore, synthetic_pdf

JOB_ID = UUID("00000000-0000-7000-8000-000000000901")
TENANT_ID = "tenant-seed"
CRITERION_TEXT = "Perímetro, linha central, círculo, áreas e gols são entidades CAD limpas."


def _seed_database(
    tmp_path: Path, *, source_sha256: str, status: str = "REVIEW_REQUIRED"
) -> tuple[Database, str]:
    database_url = f"sqlite+pysqlite:///{tmp_path / 'seed.db'}"
    database = Database(database_url)
    database.create_schema()
    expires_at = datetime.now(UTC) + timedelta(days=7)
    with database.sessions.begin() as session:
        session.add(
            ProjectRecord(
                id="project-seed",
                tenant_id=TENANT_ID,
                name="Golden",
                default_unit="m",
                created_by="reviewer",
                expires_at=expires_at,
            )
        )
        session.add(
            UploadRecord(
                id="upload-seed",
                tenant_id=TENANT_ID,
                object_key=f"tenants/{TENANT_ID}/uploads/upload-seed/entrada.pdf",
                filename="entrada.pdf",
                content_type="application/pdf",
                size_bytes=1024,
                sha256=source_sha256,
            )
        )
        session.flush()
        session.add(
            JobRecord(
                id=str(JOB_ID),
                tenant_id=TENANT_ID,
                project_id="project-seed",
                upload_id="upload-seed",
                status=status,
                stage="PREVIEWING",
                expires_at=expires_at,
            )
        )
    return database, database_url


def _inputs(
    bundle: dict[str, Path],
    *,
    tenant_id: str = TENANT_ID,
    job_id: UUID = JOB_ID,
    required_criteria: tuple[ScopeCriterion, ...] = (
        ScopeCriterion(code="ACC_GUA_001", text=CRITERION_TEXT),
    ),
) -> SeedInputs:
    return SeedInputs(
        job_id=job_id,
        tenant_id=tenant_id,
        packet_path=bundle["packet"],
        associations_path=bundle["associations"],
        proposals_path=bundle["proposals"],
        rectangle_request_path=bundle["rectangle_request"],
        manifest_path=bundle["manifest"],
        image_path=bundle["image"],
        required_criteria=required_criteria,
        operator_id="tenant-admin-01",
    )


def _criteria_for(mutation: str) -> tuple[ScopeCriterion, ...]:
    """A semeadura é fronteira de confiança e revalida o critério.

    `model_construct` simula quem montou o objeto sem passar pelo contrato — é o único
    jeito de exercitar a guarda, já que `ScopeCriterion` recusa código e texto inválidos
    na construção normal.
    """
    if mutation == "invalid_criterion":
        return (ScopeCriterion.model_construct(code="acc-gua-001", text=None),)
    if mutation == "invalid_criterion_text":
        return (ScopeCriterion.model_construct(code="ACC_GUA_001", text="x" * 501),)
    return (ScopeCriterion(code="ACC_GUA_001", text=CRITERION_TEXT),)


def _settings(database_url: str, *, storage_sse_enabled: bool = True) -> LocalWorkerSettings:
    return LocalWorkerSettings(
        database_url=database_url,
        queue_url="",
        aws_region="sa-east-1",
        aws_endpoint_url="http://localstack",
        storage_sse_enabled=storage_sse_enabled,
    )


def test_seed_binds_authorized_packet_and_records_honest_blockers(tmp_path: Path) -> None:
    source_sha256 = hashlib.sha256(synthetic_pdf()).hexdigest()
    database, database_url = _seed_database(tmp_path, source_sha256=source_sha256)
    bundle = write_seed_bundle(tmp_path / "bundle", source_sha256=source_sha256)
    storage = FakeObjectStore()

    result = seed_review(_inputs(bundle), _settings(database_url), s3_client=storage)

    assert result.review_version == 1
    assert result.readings == 3
    # Nothing is confirmed by the seed: every solver reading still needs a human.
    assert any(
        blocker.startswith("WIDTH_HUMAN_CONFIRMATION_REQUIRED") for blocker in result.blockers
    )
    assert len(storage.puts) == 1
    assert storage.puts[0]["ServerSideEncryption"] == "AES256"
    with database.sessions() as session:
        review = session.query(ReviewRevisionRecord).filter_by(job_id=str(JOB_ID)).one()
        assert review.version == 1
        assert review.solver_request_json is not None
        assert review.solver_request_json["feature_id"] == "campo-principal"
        assert review.required_blocker_codes_json == ["ACC_GUA_001"]
        # O texto do critério viaja junto do código desde a semeadura.
        assert review.required_criteria_texts_json == {"ACC_GUA_001": CRITERION_TEXT}
        assert review.scene_revision_id is None
        assert review.created_by == "seed-review:tenant-admin-01"
        assert all(reading["status"] == "proposed" for reading in review.packet_json["readings"])


def test_seed_refuses_a_second_run_and_leaves_evidence_untouched(tmp_path: Path) -> None:
    source_sha256 = hashlib.sha256(synthetic_pdf()).hexdigest()
    database, database_url = _seed_database(tmp_path, source_sha256=source_sha256)
    bundle = write_seed_bundle(tmp_path / "bundle", source_sha256=source_sha256)
    storage = FakeObjectStore()
    seed_review(_inputs(bundle), _settings(database_url), s3_client=storage)

    with pytest.raises(SeedRefusedError) as refusal:
        seed_review(_inputs(bundle), _settings(database_url), s3_client=storage)

    assert refusal.value.code == "REVIEW_ALREADY_EXISTS"
    assert len(storage.puts) == 1
    with database.sessions() as session:
        assert session.query(ReviewRevisionRecord).filter_by(job_id=str(JOB_ID)).count() == 1


@pytest.mark.parametrize(
    ("mutation", "expected_code"),
    [
        ("unknown_job", "JOB_NOT_FOUND"),
        ("other_tenant", "JOB_NOT_FOUND"),
        ("job_failed", "JOB_NOT_REVIEWABLE"),
        ("upload_mismatch", "EVIDENCE_DOES_NOT_MATCH_UPLOAD"),
        ("image_mismatch", "IMAGE_DIGEST_MISMATCH"),
        ("decided_packet", "PACKET_CONTAINS_DECISIONS"),
        ("missing_candidate", "SOLVER_READING_HAS_NO_CANDIDATE"),
        ("invalid_criterion", "INVALID_CRITERION_CODE"),
        ("invalid_criterion_text", "INVALID_CRITERION_TEXT"),
    ],
)
def test_seed_refuses_every_divergence(tmp_path: Path, mutation: str, expected_code: str) -> None:
    source_sha256 = hashlib.sha256(synthetic_pdf()).hexdigest()
    database, database_url = _seed_database(
        tmp_path,
        source_sha256=source_sha256,
        status="FAILED" if mutation == "job_failed" else "REVIEW_REQUIRED",
    )
    bundle = write_seed_bundle(
        tmp_path / "bundle",
        source_sha256=source_sha256,
        decided=mutation == "decided_packet",
        drop_circle_candidate=mutation == "missing_candidate",
        manifest_source_sha256="d" * 64 if mutation == "upload_mismatch" else None,
    )
    if mutation == "image_mismatch":
        # Rewriting the page after the bundle was built breaks the digest chain.
        bundle["image"].write_bytes(bundle["image"].read_bytes() + b"\x00")
    storage = FakeObjectStore()

    with pytest.raises(SeedRefusedError) as refusal:
        seed_review(
            _inputs(
                bundle,
                tenant_id="tenant-other" if mutation == "other_tenant" else TENANT_ID,
                job_id=(
                    UUID("00000000-0000-7000-8000-000000000999")
                    if mutation == "unknown_job"
                    else JOB_ID
                ),
                required_criteria=_criteria_for(mutation),
            ),
            _settings(database_url),
            s3_client=storage,
        )

    assert refusal.value.code == expected_code
    assert storage.puts == []
    with database.sessions() as session:
        assert session.query(ReviewRevisionRecord).count() == 0


def test_a_revisao_1_nasce_com_o_shadow_de_confianca_computado(tmp_path: Path) -> None:
    """A lacuna que a F-029/T4 fecha: este caminho lista as colunas e pulava o shadow.

    Sem isto a revisão inicial de todo job entrava no banco com o objeto vazio do default
    do servidor, e nenhuma revisão posterior reconstituía o registro para o instante em
    que ela nasceu — a calibração perderia justamente a foto anterior ao primeiro toque
    humano. Com o modo automático desligado (o padrão) nada mais muda: o pacote gravado é
    o pacote passado, sem associação selecionada e sem decisão nenhuma.
    """
    source_sha256 = hashlib.sha256(synthetic_pdf()).hexdigest()
    database, database_url = _seed_database(tmp_path, source_sha256=source_sha256)
    bundle = write_seed_bundle(tmp_path / "bundle", source_sha256=source_sha256)

    result = seed_review(_inputs(bundle), _settings(database_url), s3_client=FakeObjectStore())

    assert result.auto_decided_reading_ids == ()
    with database.sessions() as session:
        review = session.query(ReviewRevisionRecord).filter_by(job_id=str(JOB_ID)).one()
        shadow = review.confidence_shadow_json
        assert shadow["score_version"] == CONFIDENCE_SCORE_VERSION
        assert shadow["readings_total"] == 3
        assert shadow["readings_with_candidate"] == 3
        assert len(shadow["decisions"]) == 36
        assert {item["reading_id"] for item in shadow["reading_confidences"]} == {
            WIDTH_READING_ID,
            HEIGHT_READING_ID,
            CIRCLE_READING_ID,
        }
        # Nenhum ato: registro de auto-decisão não existe com o modo desligado.
        assert "auto_decisions" not in shadow
        assert review.selected_associations_json == {}
        assert all(reading["decision"] is None for reading in review.packet_json["readings"])
        assert any(
            blocker.startswith("WIDTH_HUMAN_CONFIRMATION_REQUIRED")
            for blocker in review.solver_blockers_json
        )


def test_com_a_dupla_chave_a_revisao_1_nasce_com_decisoes_de_ator_maquina(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Acima do corte a cota entra sem toque humano; abaixo dele continua exceção."""
    monkeypatch.setenv("CROQUITO_AUTO_ASSOCIATION_ENABLED", "true")
    monkeypatch.setenv("CROQUITO_AUTO_ASSOCIATION_THRESHOLD", "0.6")
    source_sha256 = hashlib.sha256(synthetic_pdf()).hexdigest()
    database, database_url = _seed_database(tmp_path, source_sha256=source_sha256)
    bundle = write_seed_bundle(
        tmp_path / "bundle",
        source_sha256=source_sha256,
        association_confidences={
            WIDTH_READING_ID: 0.9,
            HEIGHT_READING_ID: 0.9,
            # Abaixo do corte no eixo da ASSOCIAÇÃO: a cota é legível, mas não se sabe a
            # qual segmento pertence — exatamente o caso que continua exigindo gente.
            CIRCLE_READING_ID: 0.4,
        },
    )

    result = seed_review(_inputs(bundle), _settings(database_url), s3_client=FakeObjectStore())

    assert set(result.auto_decided_reading_ids) == {WIDTH_READING_ID, HEIGHT_READING_ID}
    with database.sessions() as session:
        review = session.query(ReviewRevisionRecord).filter_by(job_id=str(JOB_ID)).one()
    readings = {reading["id"]: reading for reading in review.packet_json["readings"]}
    decision = readings[WIDTH_READING_ID]["decision"]
    assert readings[WIDTH_READING_ID]["status"] == "confirmed"
    assert decision["actor"] == "system"
    assert decision["action"] == "confirm"
    assert decision["reviewer_id"] == f"system:auto-association@{CONFIDENCE_SCORE_VERSION}"
    assert decision["reviewer_role"] is None
    assert "0.6" in decision["note"]
    # A exceção continua pendente, sem decisão e sem associação explícita.
    assert readings[CIRCLE_READING_ID]["status"] == "proposed"
    assert readings[CIRCLE_READING_ID]["decision"] is None
    assert review.selected_associations_json == {
        WIDTH_READING_ID: WIDTH_PROPOSAL_ID,
        HEIGHT_READING_ID: HEIGHT_PROPOSAL_ID,
    }
    # Os blockers gravados descrevem o pacote gravado: o que a máquina resolveu sai da
    # lista, o que ela não resolveu permanece.
    blockers = set(review.solver_blockers_json)
    assert not [blocker for blocker in blockers if blocker.startswith("WIDTH_")]
    assert not [blocker for blocker in blockers if blocker.startswith("HEIGHT_")]
    assert f"CENTRE_CIRCLE_HUMAN_CONFIRMATION_REQUIRED:{CIRCLE_READING_ID}" in blockers
    assert f"EXPLICIT_ASSOCIATION_REQUIRED:{CIRCLE_READING_ID}" in blockers
    assert blockers == set(result.blockers)
    # O ato fica nomeado no shadow da revisão em que aconteceu, com corte e confianças.
    recorded = {
        item["reading_id"]: item for item in review.confidence_shadow_json["auto_decisions"]
    }
    assert set(recorded) == {WIDTH_READING_ID, HEIGHT_READING_ID}
    assert recorded[WIDTH_READING_ID]["threshold"] == 0.6
    assert recorded[WIDTH_READING_ID]["association_confidence"] == 0.9
    assert recorded[WIDTH_READING_ID]["reading_confidence"] == 0.65
    assert recorded[WIDTH_READING_ID]["score_version"] == CONFIDENCE_SCORE_VERSION
    assert recorded[WIDTH_READING_ID]["decision_id"] == decision["decision_id"]


def test_a_elevacao_entra_pelo_tier_de_anotacao_e_a_cota_de_planta_nao(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A revisão 1 grava os dois tiers separados, e o corte é um só (ADR-0044).

    Com o corte em 0,7, nenhuma leitura do bundle passa no eixo de LEITURA (0,65 sem
    braço de OCR; 0,45 na elevação, que o OCR não encontrou). As cotas de planta
    continuam exceção — é o que a dupla testemunha cobra. A elevação, que não manda na
    geometria de planta, entra com a testemunha única que tem.
    """
    monkeypatch.setenv("CROQUITO_AUTO_ASSOCIATION_ENABLED", "true")
    monkeypatch.setenv("CROQUITO_AUTO_ASSOCIATION_THRESHOLD", "0.7")
    source_sha256 = hashlib.sha256(synthetic_pdf()).hexdigest()
    database, database_url = _seed_database(tmp_path, source_sha256=source_sha256)
    bundle = write_seed_bundle(
        tmp_path / "bundle",
        source_sha256=source_sha256,
        elevation=True,
        association_confidences={
            WIDTH_READING_ID: 0.99,
            HEIGHT_READING_ID: 0.99,
            CIRCLE_READING_ID: 0.99,
            ELEVATION_READING_ID: 0.9,
        },
    )

    result = seed_review(_inputs(bundle), _settings(database_url), s3_client=FakeObjectStore())

    # Associação altíssima não compra cota de planta em tier nenhum.
    assert result.auto_decided_reading_ids == (ELEVATION_READING_ID,)
    with database.sessions() as session:
        review = session.query(ReviewRevisionRecord).filter_by(job_id=str(JOB_ID)).one()
    readings = {reading["id"]: reading for reading in review.packet_json["readings"]}
    decision = readings[ELEVATION_READING_ID]["decision"]
    assert readings[ELEVATION_READING_ID]["status"] == "confirmed"
    assert decision["actor"] == "system"
    assert decision["auto_tier"] == "anotacao"
    assert decision["note"].startswith("Anotação automática")
    # O tier não reclassifica: o kind e o texto entram como o extrator os leu.
    assert readings[ELEVATION_READING_ID]["kind"] == "height"
    assert readings[ELEVATION_READING_ID]["raw_text"] == "h=3,80"
    # NENHUMA associação é gravada pela anotação automática (ADR-0044, D1a): é a ausência
    # do vínculo que a mantém fora de qualquer restrição de geometria, em qualquer solve.
    assert review.selected_associations_json == {}
    for plan_reading_id in (WIDTH_READING_ID, HEIGHT_READING_ID, CIRCLE_READING_ID):
        assert readings[plan_reading_id]["decision"] is None
    # Os blockers do retângulo continuam inteiros: a elevação não é lado nem círculo dele.
    blockers = set(review.solver_blockers_json)
    assert f"WIDTH_HUMAN_CONFIRMATION_REQUIRED:{WIDTH_READING_ID}" in blockers
    assert f"HEIGHT_HUMAN_CONFIRMATION_REQUIRED:{HEIGHT_READING_ID}" in blockers
    recorded = review.confidence_shadow_json["auto_decisions"]
    assert [(item["reading_id"], item["tier"]) for item in recorded] == [
        (ELEVATION_READING_ID, "anotacao")
    ]
    # O elemento provável fica gravado como observação, ao lado do vínculo vazio.
    assert recorded[0]["proposal_id"] is None
    assert recorded[0]["probable_proposal_id"] == ELEVATION_PROPOSAL_ID
    # A confiança de leitura é GRAVADA mesmo sem ter decidido nada: é o dado da próxima
    # calibração sobre quanto custaria exigir a segunda testemunha aqui.
    assert recorded[0]["reading_confidence"] == 0.45


def test_o_lado_do_retangulo_nunca_entra_pelo_tier_de_anotacao(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`height` citada pelo pedido do solver é cota de planta por designação, não por kind.

    `rectangle_solver` publica esse lado com precisão exata; ali o erro de uma testemunha
    única alcança a geometria, e o fundamento do tier de anotação não vale.
    """
    monkeypatch.setenv("CROQUITO_AUTO_ASSOCIATION_ENABLED", "true")
    monkeypatch.setenv("CROQUITO_AUTO_ASSOCIATION_THRESHOLD", "0.7")
    source_sha256 = hashlib.sha256(synthetic_pdf()).hexdigest()
    database, database_url = _seed_database(tmp_path, source_sha256=source_sha256)
    bundle = write_seed_bundle(
        tmp_path / "bundle",
        source_sha256=source_sha256,
        association_confidences={HEIGHT_READING_ID: 0.99},
    )

    result = seed_review(_inputs(bundle), _settings(database_url), s3_client=FakeObjectStore())

    assert result.auto_decided_reading_ids == ()
    with database.sessions() as session:
        review = session.query(ReviewRevisionRecord).filter_by(job_id=str(JOB_ID)).one()
    assert "auto_decisions" not in review.confidence_shadow_json
    assert review.selected_associations_json == {}


def test_flag_ligada_sem_corte_recusa_a_semeadura_sem_gravar_nada(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Erro de configuração impede o modo; nada é decidido e nada é persistido."""
    monkeypatch.setenv("CROQUITO_AUTO_ASSOCIATION_ENABLED", "true")
    monkeypatch.delenv("CROQUITO_AUTO_ASSOCIATION_THRESHOLD", raising=False)
    source_sha256 = hashlib.sha256(synthetic_pdf()).hexdigest()
    database, database_url = _seed_database(tmp_path, source_sha256=source_sha256)
    bundle = write_seed_bundle(tmp_path / "bundle", source_sha256=source_sha256)

    with pytest.raises(AutoAssociationConfigError) as refusal:
        seed_review(_inputs(bundle), _settings(database_url), s3_client=FakeObjectStore())

    assert "CROQUITO_AUTO_ASSOCIATION_THRESHOLD" in str(refusal.value)
    with database.sessions() as session:
        assert session.query(ReviewRevisionRecord).count() == 0


def test_seed_omits_server_side_encryption_when_the_storage_refuses_it(tmp_path: Path) -> None:
    source_sha256 = hashlib.sha256(synthetic_pdf()).hexdigest()
    _database, database_url = _seed_database(tmp_path, source_sha256=source_sha256)
    bundle = write_seed_bundle(tmp_path / "bundle", source_sha256=source_sha256)
    storage = FakeObjectStore()

    result = seed_review(
        _inputs(bundle), _settings(database_url, storage_sse_enabled=False), s3_client=storage
    )

    assert result.review_version == 1
    assert len(storage.puts) == 1
    assert storage.puts[0]["ContentType"] == "image/png"
    assert "ServerSideEncryption" not in storage.puts[0]
