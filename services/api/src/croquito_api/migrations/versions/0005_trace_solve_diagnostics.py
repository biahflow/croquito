"""tracado: diagnóstico estruturado do trace-solve.

Revision ID: 0004
Revises: 0003
Create Date: 2026-08-20

Acrescenta a `trace_solves` as três colunas JSON do consultor do traçado (F-025),
todas ADITIVAS e nenhuma substituindo coluna existente:

- `unapplied_readings_json`: cada leitura confirmada que não virou vão, com a
  CAUSA declarada no ponto do descarte. `unapplied_reading_ids_json` continua
  intacta e com o mesmo conteúdo e ordem — é contrato publicado, e trocar a
  forma dela quebraria cliente que já lê a lista de ids;
- `contested_spans_json`: os pares de leituras que disputam o mesmo vão. É
  diagnóstico: nenhum blocker novo, nenhum `solve_status` diferente;
- `applied_spans_json`: as âncoras em metros de cada cota aplicada.

Nenhuma linha é migrada e nenhum dado é reinterpretado: registro antigo fica com
lista vazia nas três, que é a verdade sobre ele — o solver que o produziu não
media essas coisas.

Por que `server_default` aqui, ao contrário da `0003`: lá as colunas nasciam
dentro de um `CREATE TABLE`, sem linha nenhuma para preencher e sem instância
antiga escrevendo. Aqui a tabela existe e o deploy é rolante (ADR-0029, e a
regra de expand/contract do `services/api/AGENTS.md`): entre o `upgrade` da
revisão nova e a drenagem da anterior, uma instância antiga ainda pode inserir
um `trace_solves` sem citar estas colunas. O default do servidor é o que faz
esse INSERT continuar válido, e é ele que preenche as linhas já existentes. Ele
é fase de EXPAND: removê-lo (e declará-lo no modelo, se o gate de drift passar a
comparar defaults) é trabalho posterior ao fim da convivência entre revisões, e
exige aprovação humana como qualquer contração.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_DIAGNOSTIC_COLUMNS: tuple[str, ...] = (
    "unapplied_readings_json",
    "contested_spans_json",
    "applied_spans_json",
)


def upgrade() -> None:
    for column in _DIAGNOSTIC_COLUMNS:
        op.add_column(
            "trace_solves",
            sa.Column(column, sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
        )


def downgrade() -> None:
    # Forward-only por decisão (ADR-0029, D2): reverter é apontar a revisão anterior da
    # imagem, não desfazer DDL num banco hospedado.
    raise NotImplementedError(
        "Migrations são forward-only (ADR-0029): reverta apontando a revisão anterior da imagem."
    )
