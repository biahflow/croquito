# Contribuindo com Croquito

Status: Accepted  
Responsável: Engineering  
Última revisão: 2026-08-18

## Fluxo

O ciclo de vida do trabalho planejado é o da Engineering OS, aplicado pelo
[Project Context](docs/engineering/PROJECT_CONTEXT.md): item de roadmap selecionado
por humano → `feature.md` → plano → execução → evidência → gate humano.

Para qualquer mudança:

1. Confirme o objetivo e o critério de aceite.
2. Leia o roteiro aplicável em [docs/INDEX.md](docs/INDEX.md).
3. Classifique a mudança: produto, interface, arquitetura, IA, segurança ou operação.
4. Decisão com impacto durável segue o [processo de ADR](docs/adr/README.md);
   alternativas materialmente diferentes podem passar antes por RFC (abaixo).
5. Implemente em incrementos verificáveis.
6. Atualize contratos e documentação no mesmo conjunto de mudanças.
7. Execute testes e evals proporcionais ao risco.

## Quando usar RFC

Use [RFC_TEMPLATE.md](docs/templates/RFC_TEMPLATE.md) antes da implementação quando
a proposta:

- Altera um fluxo de usuário relevante.
- Cria ou muda uma API pública.
- Introduz provedor, banco, fila ou formato de arquivo.
- Altera retenção, privacidade ou modelo de confiança.
- Possui alternativas com trade-offs reais.

RFC aprovada pode resultar em um ou mais ADRs, sempre pelo
[processo de ADR](docs/adr/README.md).

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

