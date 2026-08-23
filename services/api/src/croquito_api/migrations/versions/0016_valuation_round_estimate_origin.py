"""a medição declara de qual orçamento assinado ela nasceu, e guarda o contratado.

Revision ID: 0016
Revises: 0015
Create Date: 2026-08-23

Acrescenta três colunas a `valuation_rounds` (F-036 T2, ADR-0048):

- `estimate_round_id`: a rodada de orçamento de origem;
- `estimate_digest`: o digest do conteúdo **assinado** contra o qual a obra é medida. É ele,
  e não o id da rodada, que responde "medi contra o quê" — remontar o orçamento depois torna
  a assinatura caduca e não pode reescrever o que já foi medido (ADR-0048, decisão 6);
- `contract_workbook_json`: o consolidado contratual derivado daquele conteúdo, gravado na
  abertura e **imutável na rodada**, como o catálogo instalado (decisão 7). Trocá-lo no meio
  mudaria retroativamente o que já foi conferido.

As três são `NULL`-able e nenhuma linha é migrada. `NULL` nas três é exatamente o que
declara: rodada aberta sem orçamento de origem, que continua conferindo o boletim contra o
consolidado fabricado por `bulletin_export_contract` — comportamento de hoje, preservado de
propósito, porque removê-lo quebraria toda rodada existente (decisão 9).

Afrouxa também `valuation_rounds.catalog_upload_id` para `NULL`-able, e isso é decisão de
contrato, não conveniência: o docstring da própria coluna já previa o caso — "se um dia a
rodada precisar nascer sem catálogo, é decisão de contrato". A rodada aberta a partir de um
orçamento assinado instala o catálogo que o orçamento usou, e esse arquivo pode ter vindo do
**acervo da plataforma** (F-037), onde não existe upload do cliente para citar. As duas
colunas que de fato importam para ler o catálogo — `catalog_object_key` e
`catalog_source_sha256` — continuam obrigatórias, então nenhuma rodada nasce sem catálogo:
o que deixa de ser obrigatório é o upload de origem, que é proveniência e não conteúdo.

Sem chave estrangeira para `estimate_rounds`, e a ausência é decisão, não esquecimento: a
fronteira do contexto delimitado da medição (ADR-0016) já vale no modelo relacional, e
`ValuationRoundRecord` é deliberadamente sem FK para `projects` pelo mesmo motivo. O vínculo
que importa é o digest, que não é chave de linha nenhuma.

Expand/contract: as colunas entram antes de qualquer código exigi-las, e o código anterior
convive com elas porque são opcionais (services/api/AGENTS.md).

Rollback: forward-only (ADR-0029, D2) — reverter é apontar a revisão anterior da imagem, e o
código anterior continua funcionando com as colunas presentes. Recuperação manual, se um dia
exigida com aprovação humana explícita, seria três `ALTER TABLE valuation_rounds DROP COLUMN`
mais restaurar o `NOT NULL` — que só é possível se nenhuma rodada tiver nascido do acervo.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0016"
down_revision: str | None = "0015"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "valuation_rounds",
        sa.Column("estimate_round_id", sa.String(length=36), nullable=True),
    )
    op.add_column(
        "valuation_rounds",
        sa.Column("estimate_digest", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "valuation_rounds",
        sa.Column("contract_workbook_json", sa.JSON(), nullable=True),
    )
    op.alter_column(
        "valuation_rounds",
        "catalog_upload_id",
        existing_type=sa.String(length=36),
        nullable=True,
    )


def downgrade() -> None:
    # Forward-only por decisão (ADR-0029, D2): reverter é apontar a revisão anterior da
    # imagem, não desfazer DDL num banco hospedado.
    raise NotImplementedError(
        "Migrations são forward-only (ADR-0029): reverta apontando a revisão anterior da imagem."
    )
