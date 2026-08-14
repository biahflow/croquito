# Eval case: {{case id}}

Status: Draft  
Dataset version: {{dataset version}}  
Responsável: {{role}}

## Intenção

{{Failure or capability this case measures.}}

## Entrada

- Logical document/page ID: {{id}}
- Region ID: {{id}}
- Input digest: stored in protected manifest
- Data class: {{synthetic|authorized-golden}}

## Ground truth

```json
{
  "readings": [],
  "associations": [],
  "expected_issues": [],
  "prohibited_outputs": []
}
```

## Métricas aplicáveis

- {{numeric accuracy / association / schema / false-confident error}}

## Critério de sucesso

{{Exact measurable condition.}}

## Evidência de aprovação

- Domain reviewer: {{role}}
- Review date: {{yyyy-mm-dd}}
- Notes: {{non-sensitive summary}}

