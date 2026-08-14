# ADR-0009: Golden dataset e gates de avaliação

Status: Accepted  
Data: 2026-08-10  
Responsável: AI Engineering / Domain Reviewer

## Contexto

Promessas de “95%” sem definição não são verificáveis. O MVP precisa provar
qualidade em casos fácil, médio e difícil.

## Decisão

Manter três casos dourados aprovados por domínio e 13 páginas de regressão segura.
Mudanças de IA passam por métricas por campo, false-confident errors, geometria,
custo e tempo de revisão.

## Alternativas

- Avaliação visual ad hoc: rejeitada por irreprodutibilidade.
- Métrica OCR única: rejeitada por não medir associação nem CAD.

## Consequências

- Requer investimento inicial em gabarito.
- Melhoria deixa de depender de opinião.
- Dados reais ficam fora do Git e sob controle de acesso.

## Riscos e mitigação

Overfitting aos três casos: regressão nas 16 páginas e expansão somente com dados
autorizados.

