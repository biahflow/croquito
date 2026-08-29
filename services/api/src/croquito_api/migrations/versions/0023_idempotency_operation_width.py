"""a chave de idempotência passa a caber: `operation` de 80 para 512.

Revision ID: 0023
Revises: 0022
Create Date: 2026-08-29

`idempotency_records.operation` nasceu `VARCHAR(80)` na `0001` e ficou pequena sem que
ninguém percebesse, porque as rotas montam a operação por interpolação
(`field-evidence.classification:{job_id}:{origin}:{evidence_id}`) e o banco dos testes é
SQLite, que **ignora** o limite declarado do `VARCHAR`. Em PostgreSQL o mesmo valor é
`StringDataRightTruncation` — HTTP 500 em toda mutação que a tela manda com
`Idempotency-Key` nas rotas afetadas, já em homologação e em produção.

**Por que 512.** As 69 operações que a API monta são medidas com cada campo no seu máximo
realista:

- ids de recurso (`job_id`, `round_id`, `evidence_id`, `survey_id`, ...) são UUID: 36;
- `origin` e `journey` são `Literal` fechados: 10 e 9;
- `tenant_id` vem da rota nas duas operações de plataforma e é limitado pela própria coluna
  `idempotency_records.tenant_id`, `VARCHAR(128)`.

Nessa régua **nove** operações estouram os 80 de hoje, de 100
(`field-evidence.link-survey`) a 167 (`platform.journey-entitlement`), e uma décima —
`platform.reference-catalog-indexes.withdraw:{reference_catalog_index_id}` — cabe com
exatamente zero de folga, em 80 caracteres redondos.

A pior operação de hoje é `platform.journey-entitlement:{tenant_id}:{journey}`, com 167
caracteres. 512 é folga de três vezes sobre ela e ainda comporta uma operação futura com um
prefixo mais longo e dois UUIDs a mais no sufixo (167 + 74 = 241) — a folga é para o que vem,
já que o defeito consertado aqui é justamente o de um teto que ninguém reavalia ao escrever a
rota seguinte. O portão que impede a recorrência é
`tests/api/test_idempotency_operations.py`, que enumera TODAS as operações do código e reprova
quando uma passa da largura da coluna; a largura não fica maior "por precaução" no lugar de
ser conferida.

Alargar não custa nada em PostgreSQL: `VARCHAR(n)` guarda o que foi escrito, não `n`, e o
índice único `uq_idempotency_scope` indexa o dado gravado. Não há teto de índice em risco —
o maior valor real da tupla `(tenant_id, operation, key)` fica em centenas de bytes ASCII,
muito abaixo do limite de linha de índice B-tree do PostgreSQL.

**Nenhum valor gravado muda.** Isto é um `ALTER COLUMN ... TYPE VARCHAR(512)` de ALARGAMENTO:
desde o PostgreSQL 9.2 ele não reescreve a tabela, e toda linha existente continua com o
mesmo texto. Nenhum registro é truncado, reescrito ou re-hasheado, então um `Idempotency-Key`
já gravado continua casando com exatamente o mesmo replay de antes.

Expand/contract: a coluna alarga antes de qualquer código depender da folga, e a imagem
anterior convive com a coluna larga sem alteração nenhuma — ela só escrevia valores menores.

O número aparece aqui como literal, e não importado de `croquito_api.database`: uma revisão
descreve o schema no instante em que foi escrita e não pode mudar de significado quando a
constante da aplicação mudar. Quem impede os dois de divergirem é o gate de drift
(`test_baseline_nao_diverge_dos_modelos`), que compara as migrations com `Base.metadata`.

Rollback: forward-only (ADR-0029, D2) — reverter é apontar a revisão anterior da imagem, e a
imagem anterior funciona sem tocar em nada, porque a coluna larga aceita tudo que ela
escrevia. Estreitar de volta, se um dia for exigido com aprovação humana explícita, é
`ALTER TABLE idempotency_records ALTER COLUMN operation TYPE VARCHAR(80)`, que o PostgreSQL
recusa enquanto existir linha mais longa — apagar registro de idempotência é ato destrutivo
e não entra aqui.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0023"
down_revision: str | None = "0022"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column(
        "idempotency_records",
        "operation",
        existing_type=sa.String(length=80),
        type_=sa.String(length=512),
        existing_nullable=False,
    )


def downgrade() -> None:
    # Forward-only por decisão (ADR-0029, D2): reverter é apontar a revisão anterior da
    # imagem, não desfazer DDL num banco hospedado.
    raise NotImplementedError(
        "Migrations são forward-only (ADR-0029): reverta apontando a revisão anterior da imagem."
    )
