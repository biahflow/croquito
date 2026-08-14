# ADR-0004: Estratégia com dois provedores multimodais

Status: Accepted  
Data: 2026-08-10  
Responsável: AI Engineering / Product

## Contexto

Croquis manuscritos produzem erros difíceis de detectar. Uma única leitura não
oferece evidência independente suficiente para uma demo de qualidade.

## Decisão

Executar GPT-5.6 Terra e Claude Sonnet 5 independentemente em toda região
principal. Usar Textract como OCR auxiliar. Conflitos materiais são reanalisados
com tiers superiores e, se persistirem, revisados por humano.

## Alternativas

- Um modelo: menor custo, menor capacidade de detectar divergências.
- Votação de três LLMs: custo alto e falsa sensação de certeza.

## Consequências

- Melhor explicabilidade de conflitos.
- Custo e latência maiores.
- Necessidade de adapters, normalização e evals por provider.

## Riscos e mitigação

Erros correlacionados: consenso nunca é aprovação final; regras geométricas e HITL
permanecem obrigatórios.

