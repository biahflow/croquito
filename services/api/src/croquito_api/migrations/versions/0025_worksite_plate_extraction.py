"""a extração passa a ser da FOLHA: estado, contagem de páginas e registro por folha.

Revision ID: 0025
Revises: 0024
Create Date: 2026-08-29

F-046 T4, ADR-0057 (`docs/adr/0057-multiplas-pranchas-por-praca-na-extracao-de-legenda.md`).
A T3 deu à praça as suas folhas; esta revisão dá a cada folha o que a extração produz e o que
ela custa, porque extrair uma praça de três folhas é pagar três chamadas e nenhuma delas pode
esconder o desfecho das outras:

- `valuation_round_plates.page_count`: as páginas do PDF de origem DESTA folha. A contagem
  continua declarada — agora por folha, e não só na raiz —, porque duas folhas podem vir de
  documentos diferentes e uma contagem só na rodada descreveria um deles como se fosse o
  outro.
- `valuation_round_plates.extraction_id`, `extraction_status`, `extraction_failure_code`,
  `extraction_requested_by` e `extraction_updated_at`: o estado da extração POR folha. É o que
  faz uma folha que falha não derrubar as demais. O estado da raiz passa a ser derivado das
  folhas e reescrito na mesma transação de quem mudou uma delas
  (`local_queue._mirror_round_extraction`), sempre errando para o lado de "ainda não acabou".
- `valuation_round_revisions.worksite_plate_registrations_json`: os relatórios do registro
  fino de bbox das folhas **além da primeira** (`plate_id -> relatório`), espelho exato da
  divisão que `worksite_plate_packets_json` já faz. A primeira folha continua em
  `takeoff_registration_json`. Sem esta coluna, toda âncora da folha 2 em diante seria
  declarada não confiável na tela — o relatório é o que separa `registered` de `raw`.

## O que a migração preserva

A folha existente herda o que a rodada já dizia sobre ela: `plate_page_count` vira o
`page_count` da PRIMEIRA folha, e o estado de extração da rodada vira o estado dessa mesma
folha. Não é conveniência de tela: sem o backfill, uma rodada já extraída apareceria com a
folha em estado nulo e o espelho da raiz a reescreveria para "nunca extraída" no primeiro ato
seguinte — perda de estado real, silenciosa.

Só a primeira folha é preenchida porque só ela existe em banco anterior a esta revisão: a
praça de várias folhas nasce daqui para a frente.

## Expand, não contract

As colunas escalares de prancha da raiz (`plate_upload_id`, `plate_object_key`,
`plate_source_sha256`, `plate_page_count`) **continuam existindo e continuam sendo escritas**
como espelho da primeira folha. A T4 tirou a última LEITURA delas — o comando de fila da
extração passou a ler a folha da tabela filha —, e é isso que torna o passo de `contract`
possível. Executá-lo é trabalho posterior e exige aprovação humana explícita
(`services/api/AGENTS.md`).

Rollback: forward-only (ADR-0029, D2) — reverter é apontar a revisão anterior da imagem, e o
código anterior segue funcionando porque nada de que ele depende foi removido.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0025"
down_revision: str | None = "0024"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def backfill_plate_extraction(connection: sa.Connection) -> int:
    """Copia para a PRIMEIRA folha o que a rodada já dizia sobre a extração dela.

    Devolve quantas folhas foram atualizadas. Idempotente por construção: só toca a folha de
    `position = 1` cujo `extraction_status` ainda é nulo, então reaplicar num banco meio
    migrado não sobrescreve estado que o worker já escreveu.
    """
    rounds = sa.table(
        "valuation_rounds",
        sa.column("id", sa.String),
        sa.column("plate_page_count", sa.Integer),
        sa.column("extraction_id", sa.String),
        sa.column("extraction_status", sa.String),
        sa.column("extraction_failure_code", sa.String),
        sa.column("extraction_requested_by", sa.String),
        sa.column("extraction_updated_at", sa.DateTime(timezone=True)),
    )
    plates = sa.table(
        "valuation_round_plates",
        sa.column("round_id", sa.String),
        sa.column("position", sa.Integer),
        sa.column("page_count", sa.Integer),
        sa.column("extraction_id", sa.String),
        sa.column("extraction_status", sa.String),
        sa.column("extraction_failure_code", sa.String),
        sa.column("extraction_requested_by", sa.String),
        sa.column("extraction_updated_at", sa.DateTime(timezone=True)),
    )
    updated = 0
    for record in connection.execute(
        sa.select(
            rounds.c.id,
            rounds.c.plate_page_count,
            rounds.c.extraction_id,
            rounds.c.extraction_status,
            rounds.c.extraction_failure_code,
            rounds.c.extraction_requested_by,
            rounds.c.extraction_updated_at,
        )
    ).mappings():
        result = connection.execute(
            sa.update(plates)
            .where(
                plates.c.round_id == record["id"],
                plates.c.position == 1,
                plates.c.extraction_status.is_(None),
            )
            .values(
                page_count=record["plate_page_count"],
                extraction_id=record["extraction_id"],
                extraction_status=record["extraction_status"],
                extraction_failure_code=record["extraction_failure_code"],
                extraction_requested_by=record["extraction_requested_by"],
                extraction_updated_at=record["extraction_updated_at"],
            )
        )
        updated += result.rowcount or 0
    return updated


def upgrade() -> None:
    op.add_column("valuation_round_plates", sa.Column("page_count", sa.Integer(), nullable=True))
    op.add_column(
        "valuation_round_plates", sa.Column("extraction_id", sa.String(length=36), nullable=True)
    )
    op.add_column(
        "valuation_round_plates",
        sa.Column("extraction_status", sa.String(length=16), nullable=True),
    )
    op.add_column(
        "valuation_round_plates",
        sa.Column("extraction_failure_code", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "valuation_round_plates",
        sa.Column("extraction_requested_by", sa.String(length=128), nullable=True),
    )
    op.add_column(
        "valuation_round_plates",
        sa.Column("extraction_updated_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "valuation_round_revisions",
        sa.Column("worksite_plate_registrations_json", sa.JSON(), nullable=True),
    )
    backfill_plate_extraction(op.get_bind())


def downgrade() -> None:
    # Forward-only por decisão (ADR-0029, D2): reverter é apontar a revisão anterior da
    # imagem, não desfazer DDL num banco hospedado.
    raise NotImplementedError(
        "Migrations são forward-only (ADR-0029): reverta apontando a revisão anterior da imagem."
    )
