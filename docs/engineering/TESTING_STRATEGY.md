# Estratégia de testes

Status: Accepted for MVP  
Responsável: Engineering / QA / AI  
Última revisão: 2026-08-10

## Pirâmide

### Unitários

- Normalização de número/unidade.
- Matching e consensus states.
- Geometry constraints e precision classification.
- Scene invariants.
- DXF mapping e audit rules.
- Authorization helpers e idempotency keys.
- Calibração pixel→metro determinística, anchors degenerados/paralelos e
  transformação de linha, círculo e contorno apenas para `approximate`.

### Contrato

- OpenAPI snapshots/breaking changes.
- Provider adapter contract com fixtures sintéticas.
- Cada contrato de provider cobre resposta válida, schema inválido, timeout e 429
  sem retry para obter resultado conveniente.
- Scene schema compatibility.
- Step input/output schemas.

### Integração

- PostgreSQL/S3 local ou ambiente isolado.
- Upload→job→scene com providers stubados.
- O caminho stubado é injetado explicitamente e persiste somente revisão sintética
  não exportável; upload normal não recebe leitura mockada.
- Fault injection por provider/stage.
- Revision conflict e ownership.
- Export→reopen→audit.
- Exclusão completa.

### E2E

- Login por fixture autorizada.
- Upload sintético.
- Review e approval.
- Download e validação do ZIP.
- Golden workflows em ambiente controlado.

### Segurança

- Cross-tenant IDOR.
- Expired/invalid JWT e signed URL.
- PDF malformado/limites.
- Log sensitive-data scan.
- Terraform/IAM static checks.

### Carga e resiliência

- Cinco jobs simultâneos.
- Rate limit e backoff.
- Provider timeout/429/5xx.
- Reexecução idempotente de state/task.
- DLQ e alarmes.

## Testes CAD

- `ezdxf` reopen/audit.
- Units e layer allowlist.
- Closed polygons e self-intersection.
- Confirmed dimensions vs entity geometry.
- PNG render do próprio DXF.
- Abertura manual no AutoCAD para golden release.

## Evals

Seguem [Evaluation Strategy](../ai/EVALUATION_STRATEGY.md). Chamadas pagas não
rodam em PR comum; exigem pipeline autorizado e budget.

## Fixtures

- Sintéticas por padrão.
- Dados reais fora do Git.
- Golden manifests usam IDs/hashes.
- Snapshot só quando semântica estável e diff revisável.

## Gates

Pull request deve passar lint, format check, type check, unit, contract e security
checks aplicáveis. Merge que muda IA exige eval record; release exige smoke test e
golden approval quando saída CAD muda.
