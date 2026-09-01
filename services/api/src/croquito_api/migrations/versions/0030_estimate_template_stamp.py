"""a revisão do orçamento carimba qual gabarito produziu o arquivo.

Revision ID: 0030
Revises: 0029
Create Date: 2026-09-01

Acrescenta `estimate_round_revisions.estimate_template_json` (F-043 T3), aditiva e
**anulável**: `NULL` é a planilha publicada sem gabarito, que continua sendo o caminho de
quem não entrega àquela prefeitura. Nenhuma linha existente muda de significado — todas
nasceram sem gabarito porque ele não existia, e `NULL` diz exatamente isso.

O carimbo guarda identidade, revisão e digest do documento; **não** guarda as linhas. Elas
vivem em `estimate_templates` e são imutáveis por publicação, então copiá-las aqui só criaria
uma segunda verdade que poderia divergir. O digest é o que permite conferir, depois, que o
gabarito citado é byte a byte o que está no acervo.

Sem esta coluna a rodada não saberia dizer com qual revisão do gabarito publicou — e a
revisão é justamente o que o arquivo imprime para se identificar quando estiver fora do
sistema.

Rollback: forward-only (ADR-0029, D2) — reverter é apontar a revisão anterior da imagem.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0030"
down_revision: str | None = "0029"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "estimate_round_revisions",
        sa.Column("estimate_template_json", sa.JSON(), nullable=True),
    )


def downgrade() -> None:
    # Forward-only por decisão (ADR-0029, D2): reverter é apontar a revisão anterior da
    # imagem, não desfazer DDL num banco hospedado.
    raise NotImplementedError(
        "Migrations são forward-only (ADR-0029): reverta apontando a revisão anterior da imagem."
    )
