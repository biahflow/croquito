"""Revisões aplicadas em ordem pelo Alembic.

Pacote pelo mesmo motivo do diretório pai: é assim que os arquivos de revisão entram na
imagem construída por `docker/python.Dockerfile`. O Alembic carrega cada revisão por
caminho de arquivo, não por import, então o nome do módulo não precisa ser importável.
"""
