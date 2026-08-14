# Padrões de código

Status: Accepted baseline  
Responsável: Engineering  
Última revisão: 2026-08-10

## Gerais

- Código e identificadores em inglês; documentação de domínio em português.
- Tipagem estrita em Python e TypeScript.
- Funções pequenas com responsabilidade explícita.
- Erros de domínio estruturados; não analisar strings de exception.
- Tempo sempre UTC; IDs UUIDv7.
- Valores geométricos internos em metros/radianos.
- Nenhum log com payload sensível.

## Python

- Python 3.12.
- `ruff` para lint/format, `mypy` para type check, `pytest` para testes.
- Pydantic para boundaries; dataclasses/types de domínio sem dependência de HTTP.
- SDKs externos apenas em `adapters`.
- I/O assíncrono no API layer; CPU pesado em worker.
- `Decimal` para parsing/preservação de cotas quando a precisão escrita importa;
  solver pode usar float com tolerâncias documentadas.

## TypeScript

- `strict: true`.
- Tipos de API gerados/validados, sem duplicação manual de schema.
- Estado de servidor separado de estado de canvas.
- Operações de revisão são comandos, não mutação arbitrária do scene graph.
- Componentes acessíveis e sem lógica geométrica escondida na UI.

## Banco

- Migrações forward e rollback/mitigação descritos.
- Toda tabela tenant-scoped possui `tenant_id` e índice compatível.
- Concurrency por version column.
- Blobs ficam no S3; banco guarda metadados/digests.

## IA

- Prompt templates fora de handlers.
- Schema validation estrita.
- Model config injetada e registrada.
- Sem fallback silencioso.
- Sem retries para obter resposta semanticamente preferida.

## Geometria

- Algoritmos determinísticos e testados com tolerâncias nomeadas.
- Separar pixel coordinates, normalized page coordinates e model coordinates.
- Não arredondar no solver.
- Validar finite values, topology e constraints.

## Logs

Campos permitidos: IDs opacos, stage, duration, status, error code, model ID, token
counts, cost estimate e entity counts. Conteúdo é proibido.

