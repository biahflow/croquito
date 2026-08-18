"""Ambiente do Alembic para o schema da API (ADR-0029).

A URL do banco nunca é lida de valor fixo no `alembic.ini`: ela vem de quem chama
(`config.attributes`, para teste e para o runner) ou de `ApiSettings.from_environment()`,
que é a mesma fonte que a API usa. O `alembic.ini` da raiz existe apenas para o CLI de
desenvolvimento gerar revisão nova; em runtime `croquito_api.bootstrap` monta a
configuração em Python, porque a imagem instala os pacotes com `--no-editable` e não tem
diretório de trabalho confiável nem `.ini`.
"""

from __future__ import annotations

from alembic import context
from sqlalchemy import Connection, MetaData, create_engine, pool

from croquito_api.config import ApiSettings
from croquito_api.database import Base

config = context.config

#: Alvo do autogenerate e do gate de drift: os modelos são a única descrição do schema.
target_metadata: MetaData = Base.metadata


def database_url() -> str:
    """URL efetiva, na ordem: injetada pelo chamador, `alembic.ini`, ambiente."""
    injected = config.attributes.get("sqlalchemy.url")
    if isinstance(injected, str) and injected:
        return injected
    configured = config.get_main_option("sqlalchemy.url", None)
    if configured:
        return configured
    return ApiSettings.from_environment().database_url


def _run_migrations(connection: Connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_offline() -> None:
    """Emite o SQL sem conectar; serve para revisar DDL, nunca para aplicar em ambiente."""
    context.configure(
        url=database_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    injected_connection = config.attributes.get("connection")
    if isinstance(injected_connection, Connection):
        _run_migrations(injected_connection)
        return
    engine = create_engine(database_url(), poolclass=pool.NullPool, future=True)
    try:
        with engine.connect() as connection:
            _run_migrations(connection)
    finally:
        engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
