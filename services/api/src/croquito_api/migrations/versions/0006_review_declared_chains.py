"""revisão de leitura: cadeias de cotas declaradas por uma pessoa.

Revision ID: 0006
Revises: 0005
Create Date: 2026-08-20

Acrescenta a `review_revisions` a coluna `declared_chains_json` (F-023), ADITIVA e
sem substituir nada: cada item é a declaração de que estas parcelas partilham este
total (`chain_id`, `total_id`, `part_ids`, autoria e instante). O resultado da
conferência NÃO é gravado — ele é recomputado contra o pacote corrente a cada
leitura da revisão, e é isso que faz uma cota retificada virar cadeia vencida em vez
de deixar no banco um fechamento que já não vale.

Nenhuma linha é migrada e nenhum dado é reinterpretado: revisão antiga fica com lista
vazia, que é a verdade sobre ela — ninguém declarou cadeia nenhuma antes desta coluna
existir.

`server_default` pelo mesmo motivo da `0005`: a tabela existe e o deploy é rolante
(ADR-0029, e a regra de expand/contract do `services/api/AGENTS.md`). Entre o
`upgrade` desta revisão e a drenagem da anterior, uma instância antiga ainda insere
`review_revisions` sem citar esta coluna, e é o default do servidor que mantém esse
INSERT válido e preenche as linhas já existentes. Ele é fase de EXPAND: removê-lo é
trabalho posterior ao fim da convivência entre revisões e exige aprovação humana.

Rollback: forward-only (ADR-0029, D2) — reverter é apontar a revisão anterior da
imagem. Recuperação manual, se um dia for exigida com aprovação humana explícita,
seria `ALTER TABLE review_revisions DROP COLUMN declared_chains_json`, que descarta
as declarações e nada mais: nenhuma outra coluna depende dela.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "review_revisions",
        sa.Column(
            "declared_chains_json", sa.JSON(), nullable=False, server_default=sa.text("'[]'")
        ),
    )


def downgrade() -> None:
    # Forward-only por decisão (ADR-0029, D2): reverter é apontar a revisão anterior da
    # imagem, não desfazer DDL num banco hospedado.
    raise NotImplementedError(
        "Migrations são forward-only (ADR-0029): reverta apontando a revisão anterior da imagem."
    )
