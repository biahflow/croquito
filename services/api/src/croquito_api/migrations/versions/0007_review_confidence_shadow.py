"""revisão de leitura: shadow log de confiança por threshold.

Revision ID: 0007
Revises: 0006
Create Date: 2026-08-21

Acrescenta a `review_revisions` a coluna `confidence_shadow_json` (F-029), ADITIVA e
sem substituir nada: guarda as confianças determinísticas de leitura e o que TERIA
sido auto-decidido em cada ponto da grade de thresholds, mais os denominadores das
métricas observacionais. Nada aqui decide: o registro é observação para calibração,
e nenhuma rota muda de comportamento por causa dele.

Ao contrário da `0006` — que guarda a declaração e recomputa o veredito — aqui o
RESULTADO é gravado de propósito: o valor de um shadow é ser o que o pipeline teria
feito NAQUELE instante, com aquele pacote e aqueles candidatos. Recomputá-lo depois
compararia a decisão humana de ontem com o score de hoje, que é exatamente a
comparação que a calibração não pode fazer.

Nenhuma linha é migrada e nenhum dado é reinterpretado: revisão antiga fica com
objeto vazio, que é a verdade sobre ela — nenhum shadow foi computado antes desta
coluna existir.

`server_default` pelo mesmo motivo da `0005` e da `0006`: a tabela existe e o deploy é
rolante (ADR-0029, e a regra de expand/contract do `services/api/AGENTS.md`). Entre o
`upgrade` desta revisão e a drenagem da anterior, uma instância antiga ainda insere
`review_revisions` sem citar esta coluna, e é o default do servidor que mantém esse
INSERT válido e preenche as linhas já existentes. O mesmo default cobre o caminho de
escrita do worker (`review_store.insert_review_revision_v1`), que lista as colunas uma
a uma e não conhece esta. Ele é fase de EXPAND: removê-lo é trabalho posterior ao fim
da convivência entre revisões e exige aprovação humana.

Rollback: forward-only (ADR-0029, D2) — reverter é apontar a revisão anterior da
imagem. Recuperação manual, se um dia for exigida com aprovação humana explícita,
seria `ALTER TABLE review_revisions DROP COLUMN confidence_shadow_json`, que descarta
o registro observacional e nada mais: nenhuma outra coluna depende dela, e nenhuma
decisão de produto foi tomada a partir dela.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "review_revisions",
        sa.Column(
            "confidence_shadow_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'")
        ),
    )


def downgrade() -> None:
    # Forward-only por decisão (ADR-0029, D2): reverter é apontar a revisão anterior da
    # imagem, não desfazer DDL num banco hospedado.
    raise NotImplementedError(
        "Migrations são forward-only (ADR-0029): reverta apontando a revisão anterior da imagem."
    )
