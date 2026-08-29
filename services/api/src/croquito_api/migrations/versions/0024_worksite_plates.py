"""as folhas da praça viram tabela filha, e a praça ganha onde guardar o que declara.

Revision ID: 0024
Revises: 0023
Create Date: 2026-08-28

F-046 T3, ADR-0057 (`docs/adr/0057-multiplas-pranchas-por-praca-na-extracao-de-legenda.md`).
Praça grande não cabe numa folha — vem em planta geral, folhas de detalhe e cortes — e a
legenda quantificada é da OBRA. Esta revisão dá lugar às N folhas de uma rodada e ao que a
orçamentista declara por cima delas:

- `valuation_round_plates`: uma linha por folha, com a origem (upload, objeto, digest,
  página) e a `plate_id` que o pacote de takeoff daquela folha carrega. Duas unicidades:
  `(round_id, plate_id)`, que é a identidade exigida pelo consolidado, e
  `(round_id, source_sha256, page_number)`, que é o que impede a MESMA folha de entrar duas
  vezes — a única recusa que sobra de `ROUND_PLATE_ALREADY_PRESENT` depois que a segunda
  folha passou a ser caso normal.
- `valuation_round_revisions.worksite_plate_packets_json`: os pacotes das folhas **além da
  primeira** (`plate_id -> TakeoffPacket`). A primeira continua em `takeoff_packet_json`,
  com o mesmo conteúdo e o mesmo digest — é isso que mantém a rodada de uma folha
  byte-idêntica (ADR-0057, decisão 8).
- `valuation_round_revisions.worksite_identity_links_json`: os vínculos de identidade
  declarados (decisão 4). `NULL` é "ninguém declarou nada", e sem declaração as duas
  leituras contam: o fail-closed erra para somar demais, e visivelmente.

O consolidado (`WorksiteTakeoff`) **não** ganha coluna: ele é derivado das folhas, dos
pacotes e dos vínculos na leitura. Gravá-lo criaria um lugar a mais onde a mesma praça pode
divergir de si mesma — a folha acrescentada depois deixaria o consolidado gravado
descrevendo uma praça que não existe mais.

## O que a migração preserva

Esta é a primeira revisão deste repositório que **move dado**, e ela move só num sentido: a
prancha que a rodada já tinha nas colunas escalares vira a PRIMEIRA folha da praça. Nenhuma
linha é apagada, nenhuma coluna é removida e nenhuma rodada sem prancha ganha folha.

A `plate_id` da folha preservada é lida do pacote de takeoff da cabeça da rodada quando ele
existe, e é `rodada-{round_id}` quando não existe. Não é escolha estética: `plate_id` é o que
amarra a folha ao pacote que nasceu dela e ao endereço `(plate_id, item_id)` que atravessa a
praça (decisão 5), e `rodada-{round_id}` é exatamente o que `round_extraction.dataset_id` já
cunha hoje. Ler do pacote quando ele existe cobre a rodada cuja extração tenha caído no
rótulo de fallback do slug — ali o pacote é a verdade, e a coluna derivada seria a mentira.

`created_by`/`created_at` da folha preservada saem da RODADA: o instante e o autor da
associação da prancha nunca foram gravados, e inventar um agora seria pior do que declarar a
procedência que existe. Toda folha acrescentada a partir daqui carimba o autor do JWT e o
relógio do servidor no próprio ato.

## Expand, não contract

`valuation_rounds.plate_upload_id`, `plate_object_key`, `plate_source_sha256` e
`plate_page_count` **continuam existindo e continuam sendo escritas** como espelho da
primeira folha. Remover coluna é trabalho posterior ao que parou de usá-la e exige aprovação
humana explícita (`services/api/AGENTS.md`), e o comando de fila da extração ainda as lê. A
leitura nova da folha já vem da tabela filha; o espelho é o que faz o deploy rolante e o
worker de hoje continuarem válidos.

Rollback: forward-only (ADR-0029, D2) — reverter é apontar a revisão anterior da imagem, e o
código anterior segue funcionando porque as colunas de que ele depende continuam lá e
continuam preenchidas.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from typing import Any

import sqlalchemy as sa
from alembic import op

# Gerador puro de UUIDv7, com contrato fechado e sem estado (`croquito_core.ids`). É a única
# importação de código da aplicação nesta revisão, e ela existe para que a folha preservada
# nasça com id no mesmo formato de todas as outras — cunhar `uuid4` aqui criaria uma linha
# que se distingue das demais pelo acaso de ter sido migrada.
from croquito_core.ids import new_uuid7

revision: str = "0024"
down_revision: str | None = "0023"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _packet_plate_ids(connection: sa.Connection) -> dict[str, str]:
    """`round_id -> plate_id` do pacote de takeoff da CABEÇA de cada rodada.

    A cabeça é a revisão de maior `version` (a cadeia é append-only). O JSON volta como
    `dict` no PostgreSQL e como `str` no SQLite, e as duas formas são tratadas: uma revisão
    ilegível não derruba a migração — ela apenas deixa a rodada cair no nome derivado.
    """
    revisions = sa.table(
        "valuation_round_revisions",
        sa.column("round_id", sa.String),
        sa.column("version", sa.Integer),
        sa.column("takeoff_packet_json", sa.JSON),
    )
    plate_ids: dict[str, str] = {}
    seen_version: dict[str, int] = {}
    for row in connection.execute(
        sa.select(revisions.c.round_id, revisions.c.version, revisions.c.takeoff_packet_json)
    ).mappings():
        round_id = str(row["round_id"])
        version = int(row["version"])
        if version < seen_version.get(round_id, -1):
            continue
        seen_version[round_id] = version
        document: Any = row["takeoff_packet_json"]
        if isinstance(document, str):
            try:
                document = json.loads(document)
            except ValueError:  # pragma: no cover - revisão ilegível não bloqueia a migração
                document = None
        plate_id = document.get("plate_id") if isinstance(document, dict) else None
        if isinstance(plate_id, str) and plate_id:
            plate_ids[round_id] = plate_id
        else:
            plate_ids.pop(round_id, None)
    return plate_ids


def backfill_round_plates(connection: sa.Connection) -> int:
    """Move a prancha escalar de cada rodada para a primeira folha da praça.

    Devolve quantas folhas foram criadas. É idempotente por construção: rodada que já tem
    folha é pulada, então reaplicar num banco meio migrado não duplica linha nenhuma.
    """
    rounds = sa.table(
        "valuation_rounds",
        sa.column("id", sa.String),
        sa.column("tenant_id", sa.String),
        sa.column("plate_upload_id", sa.String),
        sa.column("plate_object_key", sa.String),
        sa.column("plate_source_sha256", sa.String),
        sa.column("created_by", sa.String),
        sa.column("created_at", sa.DateTime(timezone=True)),
    )
    plates = sa.table(
        "valuation_round_plates",
        sa.column("id", sa.String),
        sa.column("tenant_id", sa.String),
        sa.column("round_id", sa.String),
        sa.column("plate_id", sa.String),
        sa.column("position", sa.Integer),
        sa.column("upload_id", sa.String),
        sa.column("object_key", sa.String),
        sa.column("source_sha256", sa.String),
        sa.column("page_number", sa.Integer),
        sa.column("created_by", sa.String),
        sa.column("created_at", sa.DateTime(timezone=True)),
    )
    already = {
        str(row[0]) for row in connection.execute(sa.select(plates.c.round_id).distinct()).all()
    }
    plate_ids = _packet_plate_ids(connection)
    rows: list[dict[str, Any]] = []
    for record in connection.execute(
        sa.select(
            rounds.c.id,
            rounds.c.tenant_id,
            rounds.c.plate_upload_id,
            rounds.c.plate_object_key,
            rounds.c.plate_source_sha256,
            rounds.c.created_by,
            rounds.c.created_at,
        ).where(rounds.c.plate_object_key.is_not(None))
    ).mappings():
        round_id = str(record["id"])
        if round_id in already:
            continue
        rows.append(
            {
                "id": str(new_uuid7()),
                "tenant_id": record["tenant_id"],
                "round_id": round_id,
                "plate_id": plate_ids.get(round_id, f"rodada-{round_id}"),
                "position": 1,
                "upload_id": record["plate_upload_id"],
                "object_key": record["plate_object_key"],
                # A rodada antiga pôde ser gravada antes de o digest existir na coluna; a
                # folha exige um, e a cadeia vazia é o que declara "não sabemos" sem fingir
                # um digest que ninguém calculou.
                "source_sha256": record["plate_source_sha256"] or "",
                "page_number": 1,
                "created_by": record["created_by"],
                "created_at": record["created_at"],
            }
        )
    if rows:
        connection.execute(sa.insert(plates), rows)
    return len(rows)


def upgrade() -> None:
    op.create_table(
        "valuation_round_plates",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("tenant_id", sa.String(length=128), nullable=False),
        sa.Column("round_id", sa.String(length=36), nullable=False),
        sa.Column("plate_id", sa.String(length=64), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("upload_id", sa.String(length=36), nullable=True),
        sa.Column("object_key", sa.String(length=512), nullable=False),
        sa.Column("source_sha256", sa.String(length=64), nullable=False),
        sa.Column("page_number", sa.Integer(), nullable=False),
        sa.Column("created_by", sa.String(length=128), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["round_id"],
            ["valuation_rounds.id"],
        ),
        sa.ForeignKeyConstraint(
            ["upload_id"],
            ["uploads.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("round_id", "plate_id", name="uq_valuation_round_plate"),
        sa.UniqueConstraint(
            "round_id",
            "source_sha256",
            "page_number",
            name="uq_valuation_round_plate_source",
        ),
    )
    op.create_index(
        op.f("ix_valuation_round_plates_round_id"),
        "valuation_round_plates",
        ["round_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_valuation_round_plates_tenant_id"),
        "valuation_round_plates",
        ["tenant_id"],
        unique=False,
    )
    # Declarado também em `__table_args__`; o gate de drift reprova se existir só de um lado.
    op.create_index(
        "ix_valuation_round_plates_round_position",
        "valuation_round_plates",
        ["round_id", "position"],
        unique=False,
    )
    op.add_column(
        "valuation_round_revisions",
        sa.Column("worksite_plate_packets_json", sa.JSON(), nullable=True),
    )
    op.add_column(
        "valuation_round_revisions",
        sa.Column("worksite_identity_links_json", sa.JSON(), nullable=True),
    )
    backfill_round_plates(op.get_bind())


def downgrade() -> None:
    # Forward-only por decisão (ADR-0029, D2): reverter é apontar a revisão anterior da
    # imagem, não desfazer DDL num banco hospedado.
    raise NotImplementedError(
        "Migrations são forward-only (ADR-0029): reverta apontando a revisão anterior da imagem."
    )
