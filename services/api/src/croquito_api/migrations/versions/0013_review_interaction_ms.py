"""revisão de leitura: touch time autorrelatado pela tela.

Revision ID: 0013
Revises: 0012
Create Date: 2026-08-21

Acrescenta a `review_revisions` a coluna `interaction_ms` (F-031 T4), ADITIVA e
NULLABLE: é o tempo de interação humana que a tela de revisão cronometrou e enviou
junto com o lote. Nenhuma linha é migrada e nada é reinterpretado — revisão antiga
fica `NULL`, que é a verdade sobre ela: ninguém mediu o tempo daquele ato.

Sem `server_default`, ao contrário da `0005`/`0006`: a coluna é nullable e `NULL` já é
o valor correto para quem não mediu. Uma instância antiga que continue inserindo
`review_revisions` sem citar esta coluna durante o deploy rolante (ADR-0029, e a regra
de expand/contract do `services/api/AGENTS.md`) segue válida e grava `NULL`, que é
exatamente o que se quer dizer dela.

O dado é OBSERVACIONAL: alimenta `human.interaction_ms_total` do read-model de métricas
e o campo opcional `interaction_ms` dos eventos `review.decisions_recorded.v1` e
`review.rectifications_recorded.v1`. Nenhum portão de exportação, aprovação ou
geometria olha para ele, e valor ausente ou absurdo nunca invalidou a mutação que o
carregava — a rota descarta para `NULL` em vez de recusar o ato humano.

`down_revision = "0009"` encadeia na revisão da T2 desta mesma branch. A numeração final
é assunto do rebase de integração (a `0007` está reservada pela F-029, ver o cabeçalho da
`0008`); o encadeamento relativo T2 → T4 é que precisa sobreviver a ele.

Rollback: forward-only (ADR-0029, D2) — reverter é apontar a revisão anterior da imagem.
Recuperação manual, se um dia for exigida com aprovação humana explícita, seria
`ALTER TABLE review_revisions DROP COLUMN interaction_ms`, que descarta a telemetria e
nada mais: nenhuma outra coluna depende dela.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0013"
down_revision: str | None = "0012"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "review_revisions",
        sa.Column("interaction_ms", sa.Integer(), nullable=True),
    )


def downgrade() -> None:
    # Forward-only por decisão (ADR-0029, D2): reverter é apontar a revisão anterior da
    # imagem, não desfazer DDL num banco hospedado.
    raise NotImplementedError(
        "Migrations são forward-only (ADR-0029): reverta apontando a revisão anterior da imagem."
    )
