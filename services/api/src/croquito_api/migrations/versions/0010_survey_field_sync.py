"""levantamento de campo: tabelas da sincronização do app do técnico.

Revision ID: 0010
Revises: 0009
Create Date: 2026-08-21

Cria as três tabelas da família `/v1/surveys` (F-032, ADR-0043): `survey_records`
(raiz do levantamento com o último pacote consolidado e o contador de versão),
`survey_operation_records` (histórico do outbox do aparelho, uma linha por
operação, nunca editada) e `survey_media_records` (metadado e digest de cada foto
ou áudio; os bytes ficam no object store, como manda a regra de blobs do ADR-0028
D2).

ADITIVA: nenhuma tabela existente é alterada, nenhuma coluna é removida ou
retipada e nenhuma linha é migrada. O croqui, a medição e o orçamento-base não
enxergam estas tabelas, e nenhuma delas referencia `projects` ou `jobs` — o
levantamento de campo entra no pipeline como observação, por trabalho posterior
(T11), e não como filho de um job existente.

`survey_records` e `survey_operation_records` têm chave primária COMPOSTA por
`(tenant_id, id)`, e as chaves estrangeiras dos filhos são compostas pelo mesmo
par. A razão é que estes dois `id` nascem NO APARELHO, offline: uma chave global
faria o identificador escolhido por um tenant recusar o de outro — e o app já
persistiu id que não é UUID (`survey-local`, do scaffold da fatia 0), onde a
colisão entre tenants deixa de ser hipótese remota. Pelo mesmo motivo o
`tenant_id` entra em `uq_survey_operation_seq` e em `uq_survey_media_digest`: sem
ele, dois tenants com o mesmo `survey_id` disputariam a mesma posição de sequência
ou o mesmo digest. `survey_media_records` mantém `id` simples porque o dele é
gerado pelo servidor (UUIDv7).

`tenant_id` não ganha índice próprio em `survey_records` nem em
`survey_operation_records`: a chave primária composta já começa por ele, e um
índice extra na mesma coluna líder custaria escrita sem servir a nenhuma leitura
que a PK não sirva. Em `survey_media_records`, cuja PK é simples, o índice de
`tenant_id` continua existindo, como em toda tabela do repositório.

Deploy rolante (ADR-0029 e a regra de expand/contract do `services/api/AGENTS.md`):
como esta revisão só CRIA tabelas, a instância antiga continua funcionando sem
saber que elas existem — não há coluna nova em tabela viva e, portanto, nada a
preencher com `server_default`. A fase de contract não se aplica aqui: não há
coluna transitória a remover depois.

`BASELINE_TABLES` em `croquito_api.bootstrap` deliberadamente NÃO recebe estas
tabelas, pelo mesmo motivo da `0002` e da `0003`: ela descreve a revisão `0001`, e
um banco anterior ao runner não pode tê-las. É este `upgrade`, aplicado depois do
carimbo, que as cria.

Rollback: forward-only (ADR-0029, D2) — reverter é apontar a revisão anterior da
imagem. Recuperação manual, se um dia for exigida com aprovação humana explícita,
seria derrubar as três tabelas na ordem inversa da criação (mídia, operações,
raiz), o que descarta todo levantamento sincronizado e nada mais: nenhuma outra
tabela depende delas.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0010"
down_revision: str | None = "0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "survey_records",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("tenant_id", sa.String(length=128), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("order_ref", sa.String(length=200), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        # `NOT NULL` sem `server_default`, no precedente de `catalog_cascade_json` da
        # `0003`: o default vazio é do modelo, e declará-lo também no servidor faria o
        # gate de drift acusar divergência com `Base.metadata`.
        sa.Column("snapshot_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        # Composta porque `id` nasce no aparelho: ver o cabeçalho desta revisão.
        sa.PrimaryKeyConstraint("tenant_id", "id", name="pk_survey_records"),
    )
    op.create_table(
        "survey_operation_records",
        # `id` é o `operation_id` do aparelho: reenvio do mesmo lote é fato normal em rede
        # de campo, e a unicidade natural é o que torna o reconhecimento idempotente sem
        # uma chave de deduplicação paralela — dentro do tenant, que é como ele é lido.
        sa.Column("id", sa.String(length=64), nullable=False),
        sa.Column("tenant_id", sa.String(length=128), nullable=False),
        sa.Column("survey_id", sa.String(length=36), nullable=False),
        sa.Column("device_id", sa.String(length=128), nullable=False),
        sa.Column("seq", sa.Integer(), nullable=False),
        sa.Column("type", sa.String(length=100), nullable=False),
        sa.Column("payload_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["tenant_id", "survey_id"],
            ["survey_records.tenant_id", "survey_records.id"],
            name="fk_survey_operation_records_survey",
        ),
        sa.PrimaryKeyConstraint("tenant_id", "id", name="pk_survey_operation_records"),
        sa.UniqueConstraint(
            "tenant_id", "survey_id", "device_id", "seq", name="uq_survey_operation_seq"
        ),
    )
    op.create_index(
        op.f("ix_survey_operation_records_survey_id"),
        "survey_operation_records",
        ["survey_id"],
        unique=False,
    )
    op.create_table(
        "survey_media_records",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("tenant_id", sa.String(length=128), nullable=False),
        sa.Column("survey_id", sa.String(length=36), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("mime_type", sa.String(length=100), nullable=False),
        sa.Column("byte_size", sa.Integer(), nullable=False),
        sa.Column("object_key", sa.String(length=512), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["tenant_id", "survey_id"],
            ["survey_records.tenant_id", "survey_records.id"],
            name="fk_survey_media_records_survey",
        ),
        # `id` simples: este é gerado pelo servidor (UUIDv7), não pelo aparelho.
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("object_key"),
        sa.UniqueConstraint("tenant_id", "survey_id", "sha256", name="uq_survey_media_digest"),
    )
    op.create_index(
        op.f("ix_survey_media_records_survey_id"),
        "survey_media_records",
        ["survey_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_survey_media_records_tenant_id"),
        "survey_media_records",
        ["tenant_id"],
        unique=False,
    )


def downgrade() -> None:
    # Forward-only por decisão (ADR-0029, D2): reverter é apontar a revisão anterior da
    # imagem, não desfazer DDL num banco hospedado.
    raise NotImplementedError(
        "Migrations são forward-only (ADR-0029): reverta apontando a revisão anterior da imagem."
    )
