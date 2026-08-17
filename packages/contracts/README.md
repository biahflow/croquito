# Contratos compartilhados

Os arquivos `*.schema.json` e `src/*.generated.ts` são artefatos gerados a partir de
modelos Pydantic de `croquito_core` e `croquito_valuation`, registrados como dado em
`contracts.manifest.json` (ADR-0028, "Desenho do pipeline de contratos multi-modelo").
Não os edite manualmente nem edite o manifesto para apontar caminhos que não existem —
adicione uma entrada nova ao registrar um modelo novo.

Use `make contracts` para regenerar e `make check` para detectar divergências; a
mensagem de erro nomeia o arquivo específico desatualizado.

