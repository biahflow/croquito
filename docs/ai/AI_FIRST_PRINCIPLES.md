# Princípios AI First

Status: Accepted  
Responsável: Product / AI Engineering  
Última revisão: 2026-08-10

AI First não significa delegar verdade técnica ao modelo. Significa desenhar o
produto em torno das capacidades e limitações de sistemas probabilísticos, com
feedback, evals e intervenção humana desde a primeira versão.

## Princípios

### 1. Evidência antes de confiança

Toda leitura precisa apontar para página, região e texto original. Um score sem
evidência não libera decisão.

### 2. Observação não é geometria

LLMs e OCR observam texto, semântica e relações candidatas. O geometry engine
resolve coordenadas e constraints; o usuário resolve ambiguidade material.

### 3. Incerteza é um estado de produto

`unresolved` e `approximate` são resultados válidos. É proibido converter falta de
informação em aparência de precisão.

### 4. Independência útil

Dois provedores leem independentemente. A segunda leitura reduz erros somente
quando comparada por regra explícita; “maioria” não substitui consistência.

### 5. Determinismo no entorno

Normalização, validação, solver, auditoria e export devem ser reproduzíveis. O
máximo de variabilidade fica isolado nos adapters de modelo.

### 6. Evals são testes de IA

Prompt/model change sem eval é mudança não testada. Golden cases, métricas por
campo e regressão fazem parte do CI/release gate.

### 7. Humano corrige a menor unidade possível

O produto apresenta recorte, divergência e impacto. Não obriga o usuário a
redesenhar tudo nem pede confirmação genérica de uma página inteira.

### 8. Feedback rastreável

Correções humanas geram dados de avaliação. Elas não viram dataset de treinamento
automaticamente; uso posterior depende de licença, anonimização e ADR.

### 9. Fornecedor é substituível

Prompts podem variar por provider, mas o schema interno, evals e regras permanecem.

### 10. Custo e latência são qualidade

Qualidade inclui tempo até aprovação e custo por página, não só acerto OCR.

## Anti-padrões proibidos

- Pedir ao modelo que gere diretamente o DXF final.
- Usar campo de confiança autodeclarado como aprovação.
- Repetir a chamada até obter resposta conveniente.
- Forçar consenso escolhendo o valor visualmente plausível.
- Guardar resposta bruta indefinidamente.
- Otimizar custo antes de estabelecer baseline de qualidade.
- Treinar com documento de cliente sem autorização explícita.

## Resultado desejado

O usuário deve conseguir responder para cada elemento: “de onde veio, por que tem
essa forma, qual é a precisão e quem aprovou?”.

