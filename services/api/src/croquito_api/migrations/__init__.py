"""Migrations revisadas do schema da API (ADR-0029).

Este diretório é um pacote Python de propósito: `pyproject.toml` descobre os pacotes com
`[tool.setuptools.packages.find]`, que só enxerga diretório com `__init__.py`. Sem ele as
migrations não entrariam na imagem, e a falha só apareceria no job de banco do deploy.
"""
