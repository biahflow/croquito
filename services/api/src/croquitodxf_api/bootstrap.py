"""Inicializa o schema somente no ambiente local; produção usa migrations revisadas."""

from croquitodxf_api.config import ApiSettings
from croquitodxf_api.database import Database


def main() -> None:
    settings = ApiSettings.from_environment()
    database = Database(settings.database_url)
    database.create_schema()
    print("schema local inicializado")


if __name__ == "__main__":
    main()
