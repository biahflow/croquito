"""a etapa de código passa a ser da FOLHA: shortlist e conjunto de códigos por prancha.

Revision ID: 0026
Revises: 0025
Create Date: 2026-08-29

F-046 T4d, ADR-0057 decisão 6
(`docs/adr/0057-multiplas-pranchas-por-praca-na-extracao-de-legenda.md`). A T4c ligou o
boletim da praça à `/v1` e, ao fazê-lo, encontrou o último bloqueador real: não havia onde
guardar o conjunto de códigos das folhas 2..N. `code_assignments_json` é coluna ÚNICA da
revisão, e `CodeAssignmentSet` é por PRANCHA — ele carrega `plate_id`, `page_number` e
`image_sha256`, e o boletim recusa (`CALC_ASSIGNMENT_PACKET_MISMATCH`) um conjunto de outra
folha. Sem esta revisão, uma praça de N folhas revisadas recusa alto e nunca fecha.

Duas colunas de mapa, e as duas espelham exatamente a divisão que
`worksite_plate_packets_json` já faz:

- `valuation_round_revisions.worksite_plate_assignments_json`: `plate_id -> CodeAssignmentSet`
  das folhas além da primeira. O boletim da praça consome a UNIÃO dos conjuntos, um por folha,
  e cada folha continua sendo medida com o conjunto DELA.
- `valuation_round_revisions.worksite_plate_suggestions_json`: `plate_id -> CodeSuggestionSet`
  das folhas além da primeira. A shortlist é observação por ITEM, e os itens são os do pacote
  de uma folha — sem esta coluna, a etapa de código da folha 2 leria os códigos sugeridos para
  elementos que não estão naquela prancha.

## Por que a primeira folha NÃO se muda de lugar

`code_assignments_json` e `code_suggestions_json` continuam sendo a fonte da PRIMEIRA folha,
com o mesmo conteúdo e o mesmo digest de sempre. É isso que mantém a praça de uma folha
byte-idêntica (ADR-0057, decisão 8) e o que dispensa backfill: nenhuma linha existente muda,
e toda rodada anterior a esta revisão continua sendo lida pelo caminho de sempre. As colunas
novas nascem `NULL`, que é "a praça tem uma folha só".

Aditiva e sem backfill, portanto. Não há dado a mover porque não há praça de várias folhas com
código decidido em banco nenhum — a etapa de código por folha nasce daqui para a frente.

Rollback: forward-only (ADR-0029, D2) — reverter é apontar a revisão anterior da imagem, e o
código anterior segue funcionando porque nada de que ele depende foi removido.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0026"
down_revision: str | None = "0025"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "valuation_round_revisions",
        sa.Column("worksite_plate_suggestions_json", sa.JSON(), nullable=True),
    )
    op.add_column(
        "valuation_round_revisions",
        sa.Column("worksite_plate_assignments_json", sa.JSON(), nullable=True),
    )


def downgrade() -> None:
    # Forward-only por decisão (ADR-0029, D2): reverter é apontar a revisão anterior da
    # imagem, não desfazer DDL num banco hospedado.
    raise NotImplementedError(
        "Migrations são forward-only (ADR-0029): reverta apontando a revisão anterior da imagem."
    )
