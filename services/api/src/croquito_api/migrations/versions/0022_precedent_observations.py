"""índice de precedentes de código por rótulo de legenda.

Revision ID: 0022
Revises: 0021
Create Date: 2026-08-28

Cria `precedent_observations` (F-044 T2), aditiva e nova: nenhuma tabela existente muda e
nenhuma linha é migrada. Depois desta revisão a jornada do orçamento continua exatamente como
antes — o que ela acrescenta é ONDE o precedente passa a poder existir. A leitura dele
(a shortlist) é trabalho posterior (T3) e não depende desta revisão para o sistema seguir
funcionando.

`tenant_id` é **NOT NULL**, ao contrário de `site_setup_kits` (ADR-0060), e a diferença é
deliberada: acervo de canteiro tem origem de plataforma, precedente não tem. Precedente é o
histórico de decisões de um escritório; uma linha sem dono seria a forma de trabalhar de um
cliente visível para um concorrente. Toda leitura filtra `tenant_id = :tenant`, e a
verificação é por teste com DOIS tenants.

`uq_precedent_observation_identity` sobre
`(tenant_id, worksite_key, label_normalized, price_source, code)` é o que torna a contagem de
praças confiável: refechar o mesmo pacote de códigos e reingerir a mesma praça semeada não
produzem linha nova, então o número que a tela mostra como argumento de autoridade — "você já
usou isto em N praças" — não infla com repetição de ato. Diferente de `site_setup_kits`, aqui
a constraint cobre o caso inteiro: nenhuma coluna da chave é anulável, então não há o buraco
do `NULL` que não colide com `NULL`.

`normalization_strategy` fica na linha, e **não** na chave única. Ela existe para que uma
troca futura de normalização seja detectável: a consulta filtra pela estratégia vigente, e a
linha escrita sob outra deixa de ser devolvida em vez de se misturar com as novas.

Dois índices, um por caminho de acesso real: `tenant_id` (toda leitura filtra por ele, e a
ingestão confere colisão de praça por ele) e `label_normalized` (é por ele que a shortlist
procura o rótulo do elemento que está na tela). A constraint única serve de terceiro caminho
para a conferência de duplicidade da ingestão, que cita a tupla inteira.

Rollback: forward-only (ADR-0029, D2) — reverter é apontar a revisão anterior da imagem.
Recuperação manual, se um dia exigida com aprovação humana explícita, seria
`DROP TABLE precedent_observations`: nenhuma outra tabela depende dela, e nenhuma decisão de
código gravada em `code_assignments_json` se perde — o índice é derivado de atos que
continuam registrados nas revisões.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0022"
down_revision: str | None = "0021"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "precedent_observations",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("tenant_id", sa.String(length=128), nullable=False),
        sa.Column("worksite_key", sa.String(length=64), nullable=False),
        sa.Column("label_normalized", sa.String(length=200), nullable=False),
        sa.Column("label_original", sa.String(length=200), nullable=False),
        sa.Column("price_source", sa.String(length=200), nullable=False),
        sa.Column("code", sa.String(length=40), nullable=False),
        sa.Column("source", sa.String(length=16), nullable=False),
        sa.Column("normalization_strategy", sa.String(length=16), nullable=False),
        sa.Column("created_by", sa.String(length=128), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tenant_id",
            "worksite_key",
            "label_normalized",
            "price_source",
            "code",
            name="uq_precedent_observation_identity",
        ),
    )
    op.create_index(
        op.f("ix_precedent_observations_tenant_id"),
        "precedent_observations",
        ["tenant_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_precedent_observations_label_normalized"),
        "precedent_observations",
        ["label_normalized"],
        unique=False,
    )


def downgrade() -> None:
    # Forward-only por decisão (ADR-0029, D2): reverter é apontar a revisão anterior da
    # imagem, não desfazer DDL num banco hospedado.
    raise NotImplementedError(
        "Migrations são forward-only (ADR-0029): reverta apontando a revisão anterior da imagem."
    )
