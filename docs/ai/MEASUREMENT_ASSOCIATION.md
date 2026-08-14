# Associação de cotas a propostas geométricas

Status: Implemented as observational review aid  
Responsável: AI Engineering / Geometry  
Última revisão: 2026-08-10

## Objetivo

Reduzir o tempo de revisão ao mostrar, para cada cota recortada, até três linhas,
círculos ou contornos CV próximos. Este estágio só organiza evidência espacial; não
determina escala, unidade, semântica ou geometria CAD.

## Contrato

`AssociationSet` recebe um `ReviewPacket` e um `VisionProposalSet` da mesma página
e do mesmo digest de imagem. A saída registra:

- `reading_id` e `proposal_id`;
- tipo da proposta e relação espacial;
- distância em pixels;
- `proximity_score`, exclusivamente derivado da distância normalizada;
- `visual_quality_score` do detector CV, mantido separado;
- `precision=unresolved` e `export=false` fixos.

O ranking ordena primeiro a menor distância em pixels e usa a qualidade visual
somente para desempate. Ele não mistura score de detector com proximidade nem usa
um score como probabilidade ou confirmação.

## Guardrails

- Dataset, página e SHA-256 devem coincidir; qualquer divergência falha.
- Texto dentro de um círculo gera apenas `inside_or_near_circle`, não uma decisão
  de que a cota é raio ou diâmetro.
- Contornos CV nunca são promovidos a polígono, arco ou spline.
- Resultado sem candidato vira `unassociated_reading_id`, não associação forçada.
- O revisor confirma ou corrige o alvo no fluxo de revisão; o solver só recebe
  leituras confirmadas e constraints explícitas.

## Uso local

```bash
uv run croquitodxf-demo associate-review \
  --packet output/pdf/caso/review/review-packet.json \
  --proposals output/pdf/caso/vision/page-001/vision-proposals.json \
  --output output/pdf/caso/review
```

O comando grava `association-candidates.json`. Ele é idempotente para os mesmos
artefatos de entrada e não modifica o review packet.

## Resultado observacional atual

Nos três casos dourados privados, cada uma das três leituras propostas recebeu
até três candidatos. O Guaxindiba associa a anotação ambígua do círculo a um
candidato `CIRCLE`; Raul Campelo faz o mesmo para o patamar circular. Esses
resultados são evidência de fluxo e não métrica de precisão: a associação correta
ainda depende de gabarito e revisão do domínio.
