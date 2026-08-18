"""Aplica as migrations revisadas do schema da API (ADR-0029).

Este é o comando que o job de banco da esteira executa antes de cada revisão nova da API
(`.github/workflows/deploy-hml.yml`) e que `make db-init` executa no ambiente local. Ele
falha fechado: erro aqui para o deploy antes de qualquer código novo entrar no ar.

Em runtime NÃO se usa o CLI do Alembic nem se lê `alembic.ini`. A imagem instala os
pacotes com `--no-editable`, então não há diretório de trabalho confiável nem arquivo de
configuração: a configuração é montada em Python e o caminho das migrations é resolvido
pelo próprio pacote instalado.

Três estados de banco, e o terceiro é o perigoso:

1. Com tabela de versão — aplica o que falta.
2. Sem tabela de versão e sem nenhuma tabela conhecida — aplica desde a baseline.
3. Sem tabela de versão e COM tabelas — é banco anterior ao runner. Ele é carimbado na
   baseline, sem recriar nada, mas só depois de conferir que ele corresponde à baseline:
   todas as tabelas da revisão `0001` presentes, e todas as colunas que o bootstrap aditivo
   anterior acrescentava também. Se faltar qualquer uma, o comando recusa: carimbar banco
   defasado como se estivesse em dia apenas adiaria a falha.

   A conferência de TABELA não é redundante com a de coluna. Tabela nova nunca teve bloco
   de `ALTER` — ela entrava pelo `create_all` do bootstrap antigo —, então um banco que
   parou de ser atualizado antes de uma tabela nascer tem todas as colunas legadas em dia
   e ainda assim está defasado. Carimbá-lo faria a tabela ausente nunca mais ser criada,
   porque a baseline que a descreve já constaria como aplicada.

   A régua dessa conferência é `BASELINE_TABLES`, e não `Base.metadata`. As duas coincidem
   enquanto a `0001` for a única revisão, mas divergem na primeira migration que criar
   tabela — F-003, com as tabelas da medição. Medir contra o modelo faria o portão exigir
   do banco anterior ao runner uma tabela que ele não pode ter, recusando adoção legítima
   e parando o deploy, quando essa tabela é criada pelo `upgrade` imediatamente depois do
   carimbo.
"""

from __future__ import annotations

import importlib.resources

from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, create_engine, inspect

from croquito_api.config import ApiSettings
from croquito_api.database import Base

#: Revisão que descreve o schema anterior ao runner; é nela que um banco antigo é carimbado.
BASELINE_REVISION = "0001"

#: Nome padrão da tabela de controle do Alembic. Não é sobrescrito em lugar nenhum, e
#: mudá-lo faria todo banco existente parecer não versionado.
VERSION_TABLE = "alembic_version"

#: Tabelas que a revisão `0001` cria — a régua da adoção. Ela descreve a BASELINE e
#: deliberadamente **não** acompanha `Base.metadata`: tabela que nasce numa revisão posterior
#: não existe no banco anterior ao runner e não deve existir, porque é o `upgrade` logo depois
#: do carimbo que a cria. `test_baseline_tables_corresponde_a_revisao_0001` impede que esta
#: lista se desencontre da revisão que ela descreve.
BASELINE_TABLES: frozenset[str] = frozenset(
    {
        "ai_processing_consents",
        "approvals",
        "audit_events",
        "chat_sessions",
        "chat_turns",
        "export_artifacts",
        "idempotency_records",
        "jobs",
        "projects",
        "proposal_decisions",
        "review_decisions",
        "review_revisions",
        "scene_revisions",
        "tenant_ai_processing_entitlements",
        "trace_solves",
        "uploads",
    }
)

#: Colunas que os blocos de `ALTER TABLE … ADD COLUMN` do bootstrap aditivo acrescentavam.
#: São elas que distinguem um banco anterior ao runner porém em dia de um banco defasado.
LEGACY_ADDITIVE_COLUMNS: dict[str, tuple[str, ...]] = {
    "jobs": ("page_count", "failure_code"),
    "review_revisions": (
        "proposals_json",
        "calibration_json",
        "proposal_decisions_json",
        "trace_acceptance_json",
        "required_criteria_texts_json",
    ),
    "approvals": ("approval_json",),
    "review_decisions": ("decision_id", "rectifies_decision_id"),
    "ai_processing_consents": (
        "authorization_source",
        "entitlement_id",
        "agreement_reference",
    ),
}


class SchemaAdoptionError(RuntimeError):
    """Banco anterior ao runner que não corresponde à baseline; carimbar seria mentir."""

    def __init__(self, missing: list[str]) -> None:
        self.missing = missing
        super().__init__(
            "Banco anterior ao runner de migrations está defasado e NÃO foi carimbado. "
            "Faltam: " + ", ".join(missing) + ". "
            "Caminho: recriar o banco (ambiente local, dado sintético) ou tratá-lo à mão "
            "com aprovação humana antes de rodar este comando de novo (ADR-0029)."
        )


def build_config(database_url: str) -> Config:
    """Configuração do Alembic sem `alembic.ini`, com as migrations do pacote instalado."""
    config = Config()
    config.set_main_option(
        "script_location", str(importlib.resources.files("croquito_api.migrations"))
    )
    # A URL viaja por `attributes` e não por `sqlalchemy.url`: assim ela não é escrita em
    # nenhum arquivo nem aparece na representação da configuração.
    config.attributes["sqlalchemy.url"] = database_url
    return config


def _adoption_gaps(engine: Engine, existing_tables: set[str]) -> list[str]:
    """O que impede carimbar este banco na baseline: tabela ausente ou coluna ausente.

    A régua é `BASELINE_TABLES`, não `Base.metadata`. Carimbar afirma "este banco está no
    estado da revisão 0001"; exigir dele uma tabela que só nasce numa revisão posterior
    recusaria justamente o banco que a adoção existe para aceitar — e essa tabela é criada
    pelo `upgrade` logo em seguida.
    """
    inspector = inspect(engine)
    gaps: list[str] = [f"tabela {table}" for table in sorted(BASELINE_TABLES - existing_tables)]
    for table, columns in LEGACY_ADDITIVE_COLUMNS.items():
        if table not in existing_tables:
            continue
        present = {column["name"] for column in inspector.get_columns(table)}
        gaps.extend(f"{table}.{column}" for column in columns if column not in present)
    return gaps


def apply_migrations(engine: Engine, database_url: str) -> str:
    """Leva o banco até `head` e devolve o estado reconhecido, para log e teste."""
    config = build_config(database_url)
    existing_tables = set(inspect(engine).get_table_names())
    if VERSION_TABLE in existing_tables:
        state = "versionado"
    elif not existing_tables & (BASELINE_TABLES | set(Base.metadata.tables)):
        # União, e não só a baseline: banco que carregue qualquer tabela conhecida — inclusive
        # de revisão posterior — não é vazio, e tratá-lo como tal aplicaria DDL sobre schema
        # que já existe.
        state = "vazio"
    else:
        gaps = _adoption_gaps(engine, existing_tables)
        if gaps:
            raise SchemaAdoptionError(gaps)
        command.stamp(config, BASELINE_REVISION)
        state = "adotado"
    command.upgrade(config, "head")
    return state


def main() -> None:
    settings = ApiSettings.from_environment()
    engine = create_engine(settings.database_url, future=True)
    try:
        state = apply_migrations(engine, settings.database_url)
    finally:
        engine.dispose()
    # Nada de URL nem credencial no log: só o estado reconhecido.
    print(f"schema migrado (estado inicial do banco: {state})")


if __name__ == "__main__":
    main()
