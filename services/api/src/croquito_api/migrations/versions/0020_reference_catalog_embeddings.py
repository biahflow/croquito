"""índice de embeddings publicado para catálogo do acervo.

Revision ID: 0020
Revises: 0019
Create Date: 2026-08-28

Cria `reference_catalog_embeddings` (F-041 fatia 1, ADR-0054), aditiva e nova: nenhuma
tabela existente muda e nenhuma linha é migrada. O braço semântico continua desligado no
caminho hospedado depois desta revisão — o que ela acrescenta é ONDE o índice construído
pelo comando pago `index-catalog` passa a poder chegar ao servidor.

**Tabela nova, e não colunas em `reference_catalogs`** (ADR-0054 D2): as linhas do acervo
são imutáveis (ADR-0047 D3) e o índice é publicado num ato separado, possivelmente meses
depois do catálogo; além disso um mesmo catálogo pode ter índices sucessivos quando a
receita de texto ou o modelo de embeddings mudam. Acrescentar colunas na tabela imutável
transformaria uma publicação em algo que se edita.

**Esta é a segunda tabela do schema sem `tenant_id`**, e a ausência é decisão escrita, não
descuido: a decisão 1 do ADR-0047 vale igual para o índice de um catálogo público, e o
ADR-0054 a estende explicitamente. A condição que a sustenta — nada aqui deriva de conteúdo
de cliente; tudo vem de dentro do `catalog-embeddings.json` que o operador publicou — está
na docstring de `ReferenceCatalogEmbeddingRecord` e é verificada por teste. Tabela global
nova exige ADR próprio, e este é o ADR.

`uq_reference_catalog_index_object` sobre `object_sha256` é o que torna cada publicação
imutável e endereçada por conteúdo: republicar o mesmo arquivo é recusado pela rota com
código estável, e a constraint é a rede embaixo dela — índice reconstruído com modelo ou
receita nova tem digest novo, logo entrada nova, e a anterior continua existindo.

Sem índice composto além do único, e a decisão é consciente porque aqui — ao contrário do
acervo, que lê a tabela inteira — **existe consulta por chave**:
(`catalog_source_sha256`, `text_recipe`, `status`). Ele não é criado porque a tabela cresce
por publicação manual de catálogo da plataforma (ordem de dezenas de linhas, uma por
catálogo e receita) e a consulta é rara: acontece no recompute explícito, que é ato humano.
Varredura de dezenas de linhas é mais barata que a manutenção de um índice, e índice que
ninguém precisa é custo de escrita sem contrapartida. O gatilho para reler esta decisão
está escrito: se a tabela passar de centenas de linhas, ou se a consulta sair do recompute
para um caminho de alta frequência, o índice composto passa a se justificar.

A FK para `reference_catalogs` é trilha da publicação, não caminho de leitura — a busca do
índice é por digest da fonte (ADR-0054 D3). Ela existe para que não haja índice apontando
para catálogo que nunca foi publicado.

Rollback: forward-only (ADR-0029, D2) — reverter é apontar a revisão anterior da imagem.
Recuperação manual, se um dia exigida com aprovação humana explícita, seria
`DROP TABLE reference_catalog_embeddings`: nenhuma outra tabela depende dela. O objeto
publicado no store não é tocado por DDL nenhuma.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0020"
down_revision: str | None = "0019"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "reference_catalog_embeddings",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("reference_catalog_id", sa.String(length=36), nullable=False),
        sa.Column("catalog_source_sha256", sa.String(length=64), nullable=False),
        sa.Column("text_recipe", sa.String(length=40), nullable=False),
        sa.Column("provider", sa.String(length=40), nullable=False),
        sa.Column("model_id", sa.String(length=160), nullable=False),
        sa.Column("dims", sa.Integer(), nullable=False),
        sa.Column("code_count", sa.Integer(), nullable=False),
        sa.Column("object_key", sa.String(length=512), nullable=False),
        sa.Column("object_sha256", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("published_by", sa.String(length=128), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("withdrawn_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["reference_catalog_id"], ["reference_catalogs.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("object_sha256", name="uq_reference_catalog_index_object"),
    )


def downgrade() -> None:
    # Forward-only por decisão (ADR-0029, D2): reverter é apontar a revisão anterior da
    # imagem, não desfazer DDL num banco hospedado.
    raise NotImplementedError(
        "Migrations são forward-only (ADR-0029): reverta apontando a revisão anterior da imagem."
    )
