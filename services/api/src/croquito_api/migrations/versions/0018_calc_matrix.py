"""a revisão guarda a matriz de contribuições que gerou a memória de cálculo (ADR-0053).

Revision ID: 0018
Revises: 0017
Create Date: 2026-08-26

Acrescenta uma coluna a `valuation_round_revisions` **e** a `estimate_round_revisions`
(F-038 T8, ADR-0053):

- `calc_matrix_json`: a `CalcMatrix` posta no build — a matriz elemento x serviço que funde
  por código e resolve dependência —, gravada na revisão nova para auditoria e releitura
  antes de alimentar o builder. Guardar a matriz na revisão, e não numa rota "set matriz"
  própria, mantém o dado amarrado ao boletim/orçamento que ele gerou.

As duas são `NULL`-able e nenhuma linha é migrada. `NULL` é exatamente o que declara: a
revisão foi montada no **regime legado** — código único por item, sem matriz —, cujo
resultado continua byte-idêntico ao de hoje (ADR-0053, decisão 3 e riscos). Rodada antiga é
um pacote de um serviço só, que é o que ela é.

Expand/contract: a coluna entra antes de qualquer código exigi-la, e o código anterior
convive com ela porque é opcional (services/api/AGENTS.md). O gate de drift (ADR-0029, D5)
compara o schema migrado com `Base.metadata` e cobra a paridade com os dois modelos ORM.

Rollback: forward-only (ADR-0029, D2) — reverter é apontar a revisão anterior da imagem, e
o código anterior segue funcionando com a coluna presente. Por ser aditiva e nullable, não
é migração destrutiva e não exige aprovação humana extra.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0018"
down_revision: str | None = "0017"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "valuation_round_revisions",
        sa.Column("calc_matrix_json", sa.JSON(), nullable=True),
    )
    op.add_column(
        "estimate_round_revisions",
        sa.Column("calc_matrix_json", sa.JSON(), nullable=True),
    )


def downgrade() -> None:
    raise NotImplementedError(
        "Migrations são forward-only (ADR-0029): reverta apontando a revisão anterior da imagem."
    )
