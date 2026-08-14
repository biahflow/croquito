# Contribuindo com Croquito

Status: Accepted  
Responsável: Engineering  
Última revisão: 2026-08-10

## Fluxo

1. Confirme o objetivo e o critério de aceite.
2. Leia o roteiro aplicável em [docs/INDEX.md](docs/INDEX.md).
3. Classifique a mudança: produto, interface, arquitetura, IA, segurança ou operação.
4. Crie RFC quando houver mais de uma solução materialmente diferente.
5. Crie ADR quando a decisão for transversal, difícil de reverter ou afetar NFRs.
6. Implemente em incrementos verificáveis.
7. Atualize contratos e documentação no mesmo conjunto de mudanças.
8. Execute testes e evals proporcionais ao risco.

## Quando usar RFC

Use [RFC_TEMPLATE.md](docs/templates/RFC_TEMPLATE.md) antes da implementação quando
a proposta:

- Altera um fluxo de usuário relevante.
- Cria ou muda uma API pública.
- Introduz provedor, banco, fila ou formato de arquivo.
- Altera retenção, privacidade ou modelo de confiança.
- Possui alternativas com trade-offs reais.

RFC aprovada pode resultar em um ou mais ADRs.

## Commits

Use mensagens curtas no formato:

```text
<type>(<scope>): <imperative summary>
```

Tipos: `feat`, `fix`, `docs`, `test`, `refactor`, `infra`, `security`, `eval`.

Não misture refatoração ampla com mudança comportamental sem necessidade. Não
inclua PDFs reais, chaves, dumps ou outputs brutos de modelos.

## Revisão

Toda revisão deve confirmar:

- Requisito e critério de aceite rastreáveis.
- Ausência de medidas inventadas ou suposições ocultas.
- Idempotência e falhas parciais nos workflows.
- Isolamento entre tenants.
- Compatibilidade do DXF e auditoria de geometria.
- Testes e evals relevantes.
- Impacto de custo e observabilidade.
- Atualização dos documentos canônicos.

Use [REVIEW_CHECKLIST.md](docs/engineering/REVIEW_CHECKLIST.md) para a revisão
completa.

## Definição de pronto

A fonte canônica é [DEFINITION_OF_DONE.md](docs/engineering/DEFINITION_OF_DONE.md).

