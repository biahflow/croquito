"""Portões do runner de migrations (ADR-0029).

Estes testes exigem PostgreSQL de verdade: SQLite não descreve o schema que as migrations
produzem, e o gate de drift compara o banco real com `Base.metadata`. Sem a variável de
ambiente com a URL, eles são PULADOS — `make test` na máquina do desenvolvedor não passa a
depender de serviço no ar. O CI define a variável, e lá pular seria furar o portão.

Cada teste trabalha num schema PostgreSQL próprio, criado e derrubado por fixture: nenhum
depende de ordem, e nenhum enxerga o estado deixado por outro.
"""

from __future__ import annotations

import os
import types
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

import pytest
import sqlalchemy as sa
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from fastapi.testclient import TestClient
from sqlalchemy import (
    Engine,
    MetaData,
    create_engine,
    event,
    inspect,
    make_url,
    select,
    text,
)

from croquito_api import bootstrap
from croquito_api.bootstrap import (
    BASELINE_REVISION,
    BASELINE_TABLES,
    VERSION_TABLE,
    SchemaAdoptionError,
    apply_migrations,
    build_config,
)
from croquito_api.config import ApiSettings
from croquito_api.database import (
    IDEMPOTENCY_OPERATION_MAX_LENGTH,
    Base,
    Database,
    IdempotencyRecord,
)
from croquito_api.main import create_app
from tests.api.test_idempotency_operations import column_max_length

POSTGRES_URL_ENV = "CROQUITO_TEST_POSTGRES_URL"
_POSTGRES_URL = os.getenv(POSTGRES_URL_ENV)

requires_postgres = pytest.mark.skipif(
    not _POSTGRES_URL,
    reason=(
        f"Defina {POSTGRES_URL_ENV} com um PostgreSQL descartável para exercitar as "
        "migrations (o CI define; localmente é opcional)."
    ),
)

_DDL_VERBS = ("create ", "alter ", "drop ")


@pytest.fixture
def schema_url() -> Iterator[str]:
    """URL apontando para um schema recém-criado e exclusivo deste teste."""
    assert _POSTGRES_URL is not None
    base = make_url(_POSTGRES_URL)
    schema = f"f004_{uuid.uuid4().hex[:12]}"
    admin = create_engine(base, future=True, isolation_level="AUTOCOMMIT")
    with admin.connect() as connection:
        connection.execute(text(f'CREATE SCHEMA "{schema}"'))
    try:
        scoped = base.update_query_dict({"options": f"-csearch_path={schema}"})
        # `hide_password=False`: a representação padrão troca a senha por `***` e o
        # resultado não seria conectável.
        yield scoped.render_as_string(hide_password=False)
    finally:
        with admin.connect() as connection:
            connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        admin.dispose()


def _head_revision() -> str:
    """A cabeça da linha de revisões, lida do próprio diretório de versões.

    Depois da adoção o banco fica em `head`, não na baseline: o carimbo é o ponto de
    PARTIDA, e `apply_migrations` aplica o que falta em seguida. Enquanto a `0001` era a
    única revisão, os dois valores coincidiam e o teste não distinguia um do outro.
    """
    script = ScriptDirectory.from_config(build_config("postgresql+psycopg://ignorada/ignorada"))
    head = script.get_current_head()
    assert head is not None
    return head


def _baseline_era_schema(schema_url: str) -> None:
    """Recria um banco ANTERIOR ao runner: as tabelas da `0001` e nenhum controle de versão.

    `Database.create_schema()` não serve mais de simulação: ele cria o modelo de HOJE, que
    desde F-003 tem tabelas nascidas depois da baseline (`valuation_rounds`). Um banco real
    anterior ao runner foi criado pelo bootstrap aditivo da época e tem exatamente o schema
    da `0001` — carimbá-lo e aplicar o que falta é justamente o que a adoção existe para
    fazer. Aplicar a revisão e derrubar a tabela de versão reproduz esse estado sem
    duplicar DDL aqui.
    """
    command.upgrade(build_config(schema_url), BASELINE_REVISION)
    engine = create_engine(schema_url, future=True)
    try:
        with engine.begin() as connection:
            connection.execute(text(f"DROP TABLE {VERSION_TABLE}"))
    finally:
        engine.dispose()


@contextmanager
def _recorded_statements() -> Iterator[list[str]]:
    """Registra o SQL de qualquer engine enquanto o bloco durar, para provar ausência de DDL.

    O ouvinte é na CLASSE `Engine`, não no engine que o teste cria: o runner não migra pelo
    engine que recebe — ele só o inspeciona —, e `command.stamp`/`command.upgrade` abrem o
    seu próprio dentro de `migrations/env.py`. Escutando apenas o engine local, a lista
    chegava sempre vazia e as asserções de DDL passavam por vacuidade.
    """
    recorded: list[str] = []

    def _record(
        _connection: Any,
        _cursor: Any,
        statement: str,
        _parameters: Any,
        _context: Any,
        _executemany: bool,
    ) -> None:
        recorded.append(statement.strip().lower())

    event.listen(Engine, "before_cursor_execute", _record)
    try:
        yield recorded
    finally:
        event.remove(Engine, "before_cursor_execute", _record)

    assert recorded, (
        "O gravador de SQL não viu nenhuma instrução. Toda asserção de DDL feita sobre esta "
        "lista seria vacuamente verdadeira — foi exatamente esse o defeito que este helper "
        "veio corrigir, e ele volta em silêncio se o runner passar a executar por um "
        "caminho que este ouvinte não alcança."
    )


@requires_postgres
def test_baseline_nao_diverge_dos_modelos(schema_url: str) -> None:
    """Gate de drift: modelo alterado sem migration correspondente reprova aqui."""
    engine = create_engine(schema_url, future=True)
    try:
        assert apply_migrations(engine, schema_url) == "vazio"
        with engine.connect() as connection:
            context = MigrationContext.configure(connection)
            difference = compare_metadata(context, Base.metadata)
        assert difference == [], (
            "As migrations e `Base.metadata` divergem. Gere a revisão que falta com "
            "`make db-revision MESSAGE=<descricao>` e revise o arquivo gerado."
        )
    finally:
        engine.dispose()


@requires_postgres
def test_segunda_execucao_nao_emite_ddl(schema_url: str) -> None:
    first = create_engine(schema_url, future=True)
    try:
        apply_migrations(first, schema_url)
    finally:
        first.dispose()

    second = create_engine(schema_url, future=True)
    with _recorded_statements() as recorded:
        try:
            assert apply_migrations(second, schema_url) == "versionado"
        finally:
            second.dispose()

    ddl = [statement for statement in recorded if statement.startswith(_DDL_VERBS)]
    assert ddl == []


@requires_postgres
def test_banco_anterior_ao_runner_e_carimbado(schema_url: str) -> None:
    """Adoção: banco anterior ao runner mantém tabelas e dados."""
    _baseline_era_schema(schema_url)
    seed = create_engine(schema_url, future=True)
    try:
        with seed.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO projects (id, tenant_id, name, default_unit, status, "
                    "created_by, created_at, expires_at) "
                    "VALUES ('p-1', 't-1', 'Praça', 'm', 'ACTIVE', 'u-1', now(), now())"
                )
            )
    finally:
        seed.dispose()

    engine = create_engine(schema_url, future=True)
    with _recorded_statements() as recorded:
        try:
            assert apply_migrations(engine, schema_url) == "adotado"
        finally:
            engine.dispose()

    engine = create_engine(schema_url, future=True)
    try:
        with engine.connect() as connection:
            version = connection.execute(
                text(f"SELECT version_num FROM {VERSION_TABLE}")
            ).scalar_one()
            surviving = connection.execute(text("SELECT name FROM projects")).scalar_one()
        assert version == _head_revision()
        assert surviving == "Praça"
        assert set(Base.metadata.tables) <= set(inspect(engine).get_table_names())
    finally:
        engine.dispose()

    # A adoção não reescreve nem destrói o que já existia, e as únicas tabelas criadas são
    # a de versão e as nascidas DEPOIS da baseline, que o `upgrade` logo após o carimbo
    # cria. Nenhuma tabela da baseline aparece como criada.
    #
    # `ADD COLUMN` é a exceção declarada, e não um afrouxamento: até a `0003` toda revisão
    # posterior à baseline só criava tabela, e o teste podia proibir `alter` inteiro. A
    # `0004` fez do ALTER aditivo um caso real em tabela pós-baseline (`estimate_rounds`,
    # criada pela `0003`, ganha coluna de teto) e a `0005` em tabela da PRÓPRIA baseline
    # (`trace_solves` ganha as colunas de diagnóstico do traçado) — evolução aditiva
    # aplicada pelo `upgrade` DEPOIS do carimbo, da mesma natureza dos `CREATE TABLE` que
    # o teste já tolera. O que a adoção continua não podendo emitir é `DROP` ou `ALTER`
    # que remova, retipe ou renomeie o que já existe.
    #
    # `DROP NOT NULL` entrou na lista tolerada com a `0016` (F-036), e pela mesma razão que
    # `ADD COLUMN`: ele **afrouxa** uma restrição, e não remove, retipa nem renomeia coluna
    # nenhuma. Toda linha existente já satisfaz o `NOT NULL` que sai, e todo código anterior
    # continua escrevendo o valor que sempre escreveu — é exatamente o passo "expand" do
    # expand/contract. O que continua proibido é o oposto: `SET NOT NULL` numa coluna que
    # pode ter nulo derruba a adoção de um banco real, e `RENAME` reescreve o que já existe.
    #
    # `TYPE VARCHAR(n)` entrou com a `0023`, e é o terceiro afrouxamento da mesma família:
    # alargar um `VARCHAR` não reescreve a tabela no PostgreSQL desde a 9.2, e nenhuma linha
    # existente muda de valor. O caso oposto — ESTREITAR — não precisa ser proibido por
    # texto, porque o próprio PostgreSQL recusa a instrução enquanto existir linha mais longa
    # que a largura nova: ele não trunca em silêncio. O que a tolerância NÃO cobre é troca de
    # tipo de verdade (`TYPE INTEGER`, `TYPE TEXT`...), que continua caindo como destrutiva.
    ddl = [statement for statement in recorded if statement.startswith(_DDL_VERBS)]
    aditivo = (" add column ", " drop not null", " type varchar(")
    destrutivo = [
        statement
        for statement in ddl
        if statement.startswith("drop ")
        or (statement.startswith("alter ") and not any(marker in statement for marker in aditivo))
    ]
    assert destrutivo == []
    created = {
        statement.removeprefix("create table ").split("(")[0].split()[0].strip('"')
        for statement in ddl
        if statement.startswith("create table ")
    }
    assert VERSION_TABLE in created, ddl
    assert created & set(BASELINE_TABLES) == set(), created


@requires_postgres
def test_banco_defasado_e_recusado_em_vez_de_carimbado(schema_url: str) -> None:
    database = Database(schema_url)
    database.create_schema()
    with database.engine.begin() as connection:
        connection.execute(text("ALTER TABLE jobs DROP COLUMN failure_code"))
    database.engine.dispose()

    engine = create_engine(schema_url, future=True)
    try:
        with pytest.raises(SchemaAdoptionError) as error:
            apply_migrations(engine, schema_url)
        assert error.value.missing == ["jobs.failure_code"]
        assert VERSION_TABLE not in set(inspect(engine).get_table_names())
    finally:
        engine.dispose()


@requires_postgres
def test_tabela_nova_ausente_recusa_mesmo_com_colunas_legadas_em_dia(schema_url: str) -> None:
    """Banco parado antes de uma tabela nascer está defasado, e nenhuma coluna denuncia isso.

    Tabela nova nunca teve bloco de `ALTER`: ela entrava pelo `create_all`. Um banco assim
    tem todas as colunas legadas presentes, e carimbá-lo faria a tabela ausente nunca mais
    ser criada — a baseline que a descreve já constaria como aplicada.
    """
    database = Database(schema_url)
    database.create_schema()
    with database.engine.begin() as connection:
        connection.execute(text("DROP TABLE chat_turns"))
        connection.execute(text("DROP TABLE chat_sessions"))
    database.engine.dispose()

    engine = create_engine(schema_url, future=True)
    try:
        with pytest.raises(SchemaAdoptionError) as error:
            apply_migrations(engine, schema_url)
        assert error.value.missing == ["tabela chat_sessions", "tabela chat_turns"]
        assert VERSION_TABLE not in set(inspect(engine).get_table_names())
    finally:
        engine.dispose()


@requires_postgres
def test_tabela_nascida_depois_da_baseline_nao_impede_adocao(
    schema_url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Carimbar afirma "este banco está no estado da 0001" — o modelo de hoje não é a régua.

    Cenário de F-003, agora real: a `0002` acrescentou `valuation_rounds` e
    `valuation_round_revisions` ao modelo sem acrescentá-las à baseline. O banco de
    homologação, anterior ao runner e em dia com a baseline, não tem essas tabelas e não
    deveria: é o `upgrade` logo depois do carimbo que as cria. Medir a adoção contra
    `Base.metadata` faria o portão recusar exatamente o banco que ele existe para adotar, e
    o deploy pararia.

    A tabela fictícia continua no teste para que ele siga valendo para a PRÓXIMA revisão que
    criar tabela, e não só para a `0002`.
    """
    _baseline_era_schema(schema_url)

    futuro = MetaData()
    for table in Base.metadata.tables.values():
        table.to_metadata(futuro)
    sa.Table("valuation_rounds_futura", futuro, sa.Column("id", sa.String(36), primary_key=True))
    monkeypatch.setattr(bootstrap, "Base", types.SimpleNamespace(metadata=futuro))

    engine = create_engine(schema_url, future=True)
    try:
        assert apply_migrations(engine, schema_url) == "adotado"
        with engine.connect() as connection:
            version = connection.execute(
                text(f"SELECT version_num FROM {VERSION_TABLE}")
            ).scalar_one()
        assert version == _head_revision()
    finally:
        engine.dispose()


def test_toda_revisao_e_forward_only() -> None:
    """ADR-0029 D2: não existe `downgrade`, e cada revisão nova precisa continuar assim.

    A regra vale para a linha inteira, não só para a baseline: uma revisão que trouxesse um
    `downgrade` funcional abriria em ambiente hospedado exatamente o caminho que a decisão
    fechou, e o template de revisão nova é fácil de editar sem perceber.
    """
    script = ScriptDirectory.from_config(build_config("postgresql+psycopg://ignorada/ignorada"))
    revisions = list(script.walk_revisions())
    assert len(revisions) >= 2, "a linha de revisões encolheu; esperava baseline mais F-003"
    for revision in revisions:
        with pytest.raises(NotImplementedError):
            revision.module.downgrade()


@requires_postgres
def test_medicao_nasce_depois_da_baseline_com_o_indice_da_listagem(schema_url: str) -> None:
    """As tabelas pós-baseline não estão na `0001`, e o índice de cada listagem existe.

    O gate de drift prova que migration e modelo coincidem, mas coincidiriam também se o
    índice composto faltasse nos DOIS lados. As listagens com cursor opaco de
    `GET /v1/valuation-rounds` (ADR-0028 D2) e `GET /v1/estimate-rounds` (ADR-0027)
    ordenam por `(tenant_id, created_at, id)`, e é esse índice que sustenta as duas.

    O conjunto de tabelas pós-baseline CRESCE a cada migração que cria tabela nova — a
    `0002` acrescentou as da medição, a `0003` as do orçamento-base, a `0007` as do
    levantamento de campo (que não têm índice composto de listagem: não há listagem com
    cursor opaco de `/v1/surveys`, e um índice sem consulta que o use seria custo de
    escrita sem leitura correspondente). Não há constante
    central para esse conjunto (`BASELINE_TABLES`, em `bootstrap.py`, descreve só a
    `0001`, de propósito: ver o comentário ao lado dela); a lista abaixo é literal e
    precisa crescer junto com cada migração pós-baseline futura que criar tabela nova —
    `test_baseline_nao_diverge_dos_modelos` (gate de drift) reprova se o modelo e a
    migration divergirem entre si, mas nenhum dos dois avisa este teste.
    """
    command.upgrade(build_config(schema_url), BASELINE_REVISION)
    engine = create_engine(schema_url, future=True)
    try:
        assert "valuation_rounds" not in set(inspect(engine).get_table_names())
        command.upgrade(build_config(schema_url), "head")
        inspector = inspect(engine)
        criadas = set(inspector.get_table_names()) - {VERSION_TABLE} - set(BASELINE_TABLES)
        assert criadas == {
            "valuation_rounds",
            "valuation_round_revisions",
            "estimate_rounds",
            "estimate_round_revisions",
            # `0008` (F-034): entitlement de jornada por tenant. Sem índice composto aqui —
            # ela não tem listagem com cursor; a consulta é sempre por
            # (`tenant_id`, `journey`), coberta pela unicidade do par.
            "tenant_journey_entitlements",
            "survey_records",
            "survey_operation_records",
            "survey_media_records",
            # `0017` (F-030): vínculo da evidência ao job, fotos avulsas, estado comum
            # das análises explícitas e confirmações humanas append-only.
            "job_survey_links",
            "job_field_photo_records",
            "field_evidence_analyses",
            "field_photo_value_confirmations",
            "job_stage_events",
            "domain_events",
            # `0014` (F-037): acervo de catálogos da plataforma. Primeira tabela sem
            # `tenant_id` (ADR-0047 decisão 1) e, por isso mesmo, sem índice de listagem por
            # tenant: a listagem é do acervo inteiro, de dezenas de linhas.
            "reference_catalogs",
            # `0020` (F-041): índice de embeddings do catálogo público (ADR-0054 D2). A
            # SEGUNDA e, até aqui, última tabela sem `tenant_id`: índice de catálogo sem
            # dono também não tem dono. Sem índice composto para a consulta por
            # (`catalog_source_sha256`, `text_recipe`, `status`) — a tabela é de dezenas de
            # linhas e a consulta acontece no recompute, que é ato humano.
            "reference_catalog_embeddings",
            # `0021` (F-042): acervo de parcelas de canteiro. Entrou sem passar por esta
            # lista e derrubou o `quality` da `main` — a docstring acima avisa que nenhum
            # dos outros dois gates cobre este teste, e foi exatamente o que aconteceu.
            "site_setup_kits",
            # `0022` (F-044): observações de precedente de código, que alimentam a
            # shortlist. Entrou na mesma rodada e pela mesma porta.
            "precedent_observations",
            # `0024` (F-046): as folhas da praça. Filha da rodada, com índice próprio por
            # (`round_id`, `position`) — a praça é sempre lida inteira e na ordem em que as
            # folhas entraram —, e sem índice de listagem por tenant: não há listagem de
            # folha, elas saem sempre pela rodada.
            "valuation_round_plates",
            # `0027` (F-047): a recusa humana de uma proposta assistida de agrupamento. Só a
            # RECUSA é gravada — a proposta é recomputada a cada leitura, determinística sobre
            # a cena —, e a unicidade `(tenant_id, job_id, proposal_id)` é o que torna recusar
            # duas vezes o mesmo ato. Índices por `tenant_id` e por `job_id`, os dois caminhos
            # de leitura reais.
            "element_proposal_rejections",
        }
        for table, index_name in (
            ("valuation_rounds", "ix_valuation_rounds_tenant_created"),
            ("estimate_rounds", "ix_estimate_rounds_tenant_created"),
        ):
            indices = {
                index["name"]: tuple(index["column_names"])
                for index in inspector.get_indexes(table)
            }
            assert indices[index_name] == ("tenant_id", "created_at", "id"), table
    finally:
        engine.dispose()


@requires_postgres
def test_a_0023_preserva_a_prancha_como_a_primeira_folha_da_praca(schema_url: str) -> None:
    """F-046 T3, critério 1: a migração MOVE dado, e o que ela move é a prancha da rodada.

    Exercita o `upgrade` de verdade, e não o backfill chamado à mão: uma rodada gravada no
    formato de antes da `0023` — prancha em colunas escalares — atravessa a revisão e sai
    com a folha correspondente, na posição 1, com a `plate_id` que o pacote já declarava.

    As colunas escalares continuam preenchidas depois da migração, e isso é a metade
    `expand` do expand/contract (`services/api/AGENTS.md`): removê-las é trabalho posterior
    ao que parou de usá-las, com aprovação humana explícita.
    """
    command.upgrade(build_config(schema_url), "0022")
    engine = create_engine(schema_url, future=True)
    try:
        with engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO uploads (id, tenant_id, object_key, filename, content_type, "
                    "size_bytes, sha256, status, created_at) VALUES ('u-1', 't-1', "
                    "'tenants/t-1/uploads/u-1/prancha.pdf', 'prancha.pdf', 'application/pdf', "
                    "2048, 'd', 'VERIFIED', now())"
                )
            )
            connection.execute(
                text(
                    "INSERT INTO valuation_rounds (id, tenant_id, worksite_key, worksite_name, "
                    "reference_label, period_number, status, version, catalog_upload_id, "
                    "catalog_object_key, catalog_source_sha256, catalog_summary_json, "
                    "plate_upload_id, plate_object_key, plate_source_sha256, plate_page_count, "
                    "extraction_status, created_by, created_at, updated_at) VALUES "
                    "('r-1', 't-1', 'praca-norte', 'PRACA NORTE', 'MEDICAO 01/2026', 1, 'OPEN', "
                    "3, 'u-1', 'tenants/t-1/catalogo.json', 'c', '{}', 'u-1', "
                    "'tenants/t-1/valuation-rounds/r-1/plate/origem.pdf', 'd', 1, 'done', "
                    "'orcamentista', now(), now())"
                )
            )
            connection.execute(
                text(
                    "INSERT INTO valuation_round_revisions (id, tenant_id, round_id, version, "
                    "takeoff_packet_json, artifact_refs_json, artifact_digests_json, "
                    "created_by, created_at) VALUES ('rev-1', 't-1', 'r-1', 1, "
                    "'{\"plate_id\": \"rodada-legada\"}', '{}', '{}', 'extracao', now())"
                )
            )

        command.upgrade(build_config(schema_url), "head")

        with engine.connect() as connection:
            folha = (
                connection.execute(
                    text(
                        "SELECT plate_id, position, page_number, object_key, source_sha256, "
                        "upload_id, tenant_id, created_by FROM valuation_round_plates "
                        "WHERE round_id = 'r-1'"
                    )
                )
                .mappings()
                .one()
            )
            espelho = (
                connection.execute(
                    text(
                        "SELECT plate_object_key, plate_source_sha256, plate_page_count "
                        "FROM valuation_rounds WHERE id = 'r-1'"
                    )
                )
                .mappings()
                .one()
            )
        assert folha["plate_id"] == "rodada-legada"
        assert folha["position"] == 1
        assert folha["page_number"] == 1
        assert folha["object_key"].endswith("origem.pdf")
        assert folha["source_sha256"] == "d"
        assert folha["upload_id"] == "u-1"
        assert folha["tenant_id"] == "t-1"
        assert folha["created_by"] == "orcamentista"
        assert espelho["plate_object_key"].endswith("origem.pdf")
        assert espelho["plate_source_sha256"] == "d"
        assert espelho["plate_page_count"] == 1
    finally:
        engine.dispose()


@requires_postgres
def test_a_0024_preserva_o_estado_de_extracao_na_primeira_folha(schema_url: str) -> None:
    """F-046 T4: o estado de extração e a contagem de páginas descem da rodada para a folha.

    Sem este backfill, uma rodada JÁ extraída apareceria com a folha em estado nulo, e o
    espelho da raiz — que passou a ser derivado das folhas — a reescreveria para "nunca
    extraída" no primeiro ato seguinte. Perda de estado real, e silenciosa.

    Exercita o `upgrade` de verdade a partir da revisão anterior, e não o backfill chamado à
    mão: é a passagem inteira que precisa preservar o dado.
    """
    command.upgrade(build_config(schema_url), "0022")
    engine = create_engine(schema_url, future=True)
    try:
        with engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO uploads (id, tenant_id, object_key, filename, content_type, "
                    "size_bytes, sha256, status, created_at) VALUES ('u-2', 't-2', "
                    "'tenants/t-2/uploads/u-2/prancha.pdf', 'prancha.pdf', 'application/pdf', "
                    "2048, 'd', 'VERIFIED', now())"
                )
            )
            connection.execute(
                text(
                    "INSERT INTO valuation_rounds (id, tenant_id, worksite_key, worksite_name, "
                    "reference_label, period_number, status, version, catalog_upload_id, "
                    "catalog_object_key, catalog_source_sha256, catalog_summary_json, "
                    "plate_upload_id, plate_object_key, plate_source_sha256, plate_page_count, "
                    "extraction_id, extraction_status, extraction_failure_code, "
                    "extraction_requested_by, created_by, created_at, updated_at) VALUES "
                    "('r-2', 't-2', 'praca-sul', 'PRACA SUL', 'MEDICAO 02/2026', 2, 'OPEN', "
                    "4, 'u-2', 'tenants/t-2/catalogo.json', 'c', '{}', 'u-2', "
                    "'tenants/t-2/valuation-rounds/r-2/plate/origem.pdf', 'd', 7, "
                    "'ext-2', 'failed', 'PROVIDER_EXECUTION_FAILED', 'orcamentista', "
                    "'orcamentista', now(), now())"
                )
            )

        command.upgrade(build_config(schema_url), "head")

        with engine.connect() as connection:
            folha = (
                connection.execute(
                    text(
                        "SELECT page_count, extraction_id, extraction_status, "
                        "extraction_failure_code, extraction_requested_by "
                        "FROM valuation_round_plates WHERE round_id = 'r-2'"
                    )
                )
                .mappings()
                .one()
            )
        assert folha["page_count"] == 7
        assert folha["extraction_id"] == "ext-2"
        assert folha["extraction_status"] == "failed"
        assert folha["extraction_failure_code"] == "PROVIDER_EXECUTION_FAILED"
        assert folha["extraction_requested_by"] == "orcamentista"
    finally:
        engine.dispose()


@requires_postgres
def test_baseline_tables_corresponde_a_revisao_0001(schema_url: str) -> None:
    """`BASELINE_TABLES` é dado declarado; este teste impede que ele apodreça.

    A constante descreve o schema da revisão `0001` e **não** acompanha `Base.metadata`. Uma
    revisão futura que mexesse na baseline, ou um nome escrito errado, passaria despercebido
    sem esta conferência — e o portão de adoção é justamente o que não pode mentir.
    """
    command.upgrade(build_config(schema_url), BASELINE_REVISION)
    engine = create_engine(schema_url, future=True)
    try:
        criadas = set(inspect(engine).get_table_names()) - {VERSION_TABLE}
    finally:
        engine.dispose()

    assert criadas == set(BASELINE_TABLES)


@requires_postgres
def test_tabela_ausente_tambem_recusa(schema_url: str) -> None:
    """Banco com parte das tabelas é defasado, não vazio: carimbá-lo esconderia a falha."""
    engine = create_engine(schema_url, future=True)
    try:
        with engine.begin() as connection:
            connection.execute(text("CREATE TABLE projects (id VARCHAR(36) PRIMARY KEY)"))
        with pytest.raises(SchemaAdoptionError) as error:
            apply_migrations(engine, schema_url)
        assert "tabela jobs" in error.value.missing
    finally:
        engine.dispose()


def test_configuracao_resolve_as_migrations_pelo_pacote_instalado() -> None:
    """Sem `alembic.ini` e sem diretório de trabalho: é assim que o runtime funciona."""
    config = build_config("postgresql+psycopg://ignorada/ignorada")
    location = config.get_main_option("script_location")
    assert location is not None
    assert os.path.isfile(os.path.join(location, "env.py"))
    assert os.path.isfile(os.path.join(location, "versions", f"{BASELINE_REVISION}_baseline.py"))


@requires_postgres
def test_alargar_operation_preserva_o_registro_ja_gravado(schema_url: str) -> None:
    """A `0023` alarga a coluna sem tocar em nenhuma linha: replay antigo continua casando.

    Registro de idempotência é promessa: "este `Idempotency-Key` já foi processado, e a
    resposta foi esta". Reescrever, truncar ou re-hashear o que já está gravado quebraria
    essa promessa em silêncio — o mesmo comando reenviado deixaria de ser reconhecido, ou
    (pior) um comando diferente passaria a casar com a resposta de outro. O teste grava uma
    linha no schema ANTERIOR à revisão e confere campo a campo depois dela.
    """
    command.upgrade(build_config(schema_url), "0022")
    gravado = {
        "id": "01920000-0000-7000-8000-000000000001",
        "tenant_id": "tenant-antigo",
        "operation": "review.decisions:01920000-0000-7000-8000-0000000000ff",
        "key": "chave-de-antes-da-0023",
        "request_hash": "a" * 64,
    }
    engine = create_engine(schema_url, future=True)
    try:
        with engine.begin() as connection:
            connection.execute(
                text(
                    "INSERT INTO idempotency_records "
                    "(id, tenant_id, operation, key, request_hash, response_json, created_at) "
                    "VALUES (:id, :tenant_id, :operation, :key, :request_hash, "
                    '\'{"status": "ok"}\', now())'
                ),
                gravado,
            )

        command.upgrade(build_config(schema_url), "head")

        colunas = {
            coluna["name"]: getattr(coluna["type"], "length", None)
            for coluna in inspect(engine).get_columns("idempotency_records")
        }
        with engine.connect() as connection:
            depois = (
                connection.execute(
                    text(
                        "SELECT id, tenant_id, operation, key, request_hash, response_json "
                        "FROM idempotency_records"
                    )
                )
                .mappings()
                .all()
            )
    finally:
        engine.dispose()

    # A migration e o modelo têm de coincidir: a largura que o banco ficou é a mesma que
    # `database.py` declara.
    assert colunas["operation"] == IDEMPOTENCY_OPERATION_MAX_LENGTH
    assert len(depois) == 1
    assert {campo: depois[0][campo] for campo in gravado} == gravado
    assert depois[0]["response_json"] == {"status": "ok"}


@requires_postgres
def test_operacao_longa_de_idempotencia_grava_em_postgres(schema_url: str) -> None:
    """A prova em banco de verdade: operação longa passa pelo caminho real e volta 2xx.

    `tests/api/test_idempotency_operations.py` fecha a classe do defeito lendo o código; ele
    não prova que o banco aceita. Esta é a outra metade, e ela só existe em PostgreSQL de
    propósito: o SQLite do resto da suíte ignora a largura do `VARCHAR`, então este mesmo
    request passava lá enquanto devolvia HTTP 500 em homologação e em produção.

    A rota escolhida é a de entitlement de IA porque ela monta
    `platform.ai-processing-entitlement:{tenant_id}` sem precisar de job, upload nem cena —
    o request exercita `_store_idempotent_response` pelo caminho de sempre, sem SQL cru. Com
    um `tenant_id` do tamanho máximo que a tabela aceita, a operação mede 163 caracteres;
    antes da `0023` a coluna tinha 80 e o `commit` estourava em
    `StringDataRightTruncation`.
    """
    engine = create_engine(schema_url, future=True)
    try:
        apply_migrations(engine, schema_url)
    finally:
        engine.dispose()

    tenant_id = "tenant-" + "z" * (column_max_length("tenant_id") - len("tenant-"))
    operation = f"platform.ai-processing-entitlement:{tenant_id}"
    assert len(operation) > 80, "o teste precisa estourar a largura ANTIGA para provar algo"

    database = Database(schema_url)
    application = create_app(
        settings=ApiSettings(
            database_url=schema_url,
            artifact_bucket="croquito-test-artifacts",
            aws_region="sa-east-1",
            aws_endpoint_url="http://localhost:4566",
            queue_url=None,
            oidc_issuer=None,
            oidc_audience=None,
            web_origin="http://localhost:5173",
            allow_test_tokens=True,
        ),
        database=database,
    )
    headers = {
        "Authorization": "Bearer test:plataforma:operador:platform_operator",
        "Idempotency-Key": "operacao-longa-em-postgres",
    }
    body = {"enabled": True, "agreement_reference": "ctr-operacao-longa-v1"}
    try:
        with TestClient(application) as client:
            gravado = client.put(
                f"/v1/platform/tenants/{tenant_id}/ai-processing-entitlement",
                headers=headers,
                json=body,
            )
            assert gravado.status_code == 200, gravado.text
            assert gravado.json()["tenant_id"] == tenant_id

            # O reenvio prova que a linha gravada é ENCONTRÁVEL pela mesma operação: uma
            # coluna que truncasse silenciosamente devolveria replay para operações
            # diferentes que compartilhassem os primeiros caracteres.
            replay = client.put(
                f"/v1/platform/tenants/{tenant_id}/ai-processing-entitlement",
                headers=headers,
                json=body,
            )
            assert replay.status_code == 200, replay.text
            assert replay.json() == gravado.json()

        with database.sessions() as session:
            gravada = session.scalars(select(IdempotencyRecord.operation)).all()
        assert list(gravada) == [operation]
    finally:
        database.engine.dispose()


@requires_postgres
def test_upgrade_pelo_cli_programatico_chega_na_cabeca(schema_url: str) -> None:
    """`command.upgrade` direto (sem o runner) também leva o banco vazio até `head`."""
    config = build_config(schema_url)
    command.upgrade(config, "head")
    engine = create_engine(schema_url, future=True)
    try:
        with engine.connect() as connection:
            context = MigrationContext.configure(connection)
            assert context.get_current_revision() is not None
    finally:
        engine.dispose()
