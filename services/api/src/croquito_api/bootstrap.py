"""Inicializa o schema de forma aditiva: ambiente local e homologação.

Produção continua exigindo migrations revisadas — este comando cria tabela e coluna
novas, e não sabe alterar nem remover nada. O uso em homologação é decisão declarada
(ADR-0025), com o job de banco rodando antes de cada revisão da API; o runner de
migrations é lacuna registrada no mesmo ADR.
"""

from croquito_api.config import ApiSettings
from croquito_api.database import Database


def main() -> None:
    settings = ApiSettings.from_environment()
    database = Database(settings.database_url)
    database.create_schema()
    print("schema local inicializado")


if __name__ == "__main__":
    main()
