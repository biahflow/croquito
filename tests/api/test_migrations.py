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
import uuid
from collections.abc import Iterator
from typing import Any

import pytest
from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.runtime.migration import MigrationContext
from sqlalchemy import create_engine, event, inspect, make_url, text

from croquito_api.bootstrap import (
    BASELINE_REVISION,
    VERSION_TABLE,
    SchemaAdoptionError,
    apply_migrations,
    build_config,
)
from croquito_api.database import Base, Database

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


def _statements_of(engine: Any) -> list[str]:
    """Registra o SQL emitido no engine, para provar ausência de DDL."""
    recorded: list[str] = []

    @event.listens_for(engine, "before_cursor_execute")
    def _record(
        _connection: Any,
        _cursor: Any,
        statement: str,
        _parameters: Any,
        _context: Any,
        _executemany: bool,
    ) -> None:
        recorded.append(statement.strip().lower())

    return recorded


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
    recorded = _statements_of(second)
    try:
        assert apply_migrations(second, schema_url) == "versionado"
    finally:
        second.dispose()

    ddl = [statement for statement in recorded if statement.startswith(_DDL_VERBS)]
    assert ddl == []


@requires_postgres
def test_banco_anterior_ao_runner_e_carimbado(schema_url: str) -> None:
    """Adoção: banco criado por `create_schema()` mantém tabelas e dados."""
    database = Database(schema_url)
    database.create_schema()
    with database.engine.begin() as connection:
        connection.execute(
            text(
                "INSERT INTO projects "
                "(id, tenant_id, name, default_unit, status, created_by, created_at, expires_at) "
                "VALUES ('p-1', 't-1', 'Praça', 'm', 'ACTIVE', 'u-1', now(), now())"
            )
        )
    database.engine.dispose()

    engine = create_engine(schema_url, future=True)
    recorded = _statements_of(engine)
    try:
        assert apply_migrations(engine, schema_url) == "adotado"
        with engine.connect() as connection:
            version = connection.execute(
                text(f"SELECT version_num FROM {VERSION_TABLE}")
            ).scalar_one()
            surviving = connection.execute(text("SELECT name FROM projects")).scalar_one()
        assert version == BASELINE_REVISION
        assert surviving == "Praça"
        assert set(Base.metadata.tables) <= set(inspect(engine).get_table_names())
    finally:
        engine.dispose()

    # A única DDL do carimbo é a criação da tabela de versão; nenhuma tabela de domínio é
    # recriada nem alterada.
    ddl = [statement for statement in recorded if statement.startswith(_DDL_VERBS)]
    assert all(VERSION_TABLE in statement for statement in ddl), ddl


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
