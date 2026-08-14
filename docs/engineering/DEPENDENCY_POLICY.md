# Política de dependências

Status: Accepted  
Responsável: Engineering / Security  
Última revisão: 2026-08-10

## Critérios

Nova dependência deve ter:

- Necessidade concreta não atendida por runtime/dependência existente.
- Licença compatível com uso comercial.
- Manutenção ativa e releases verificáveis.
- Histórico de segurança aceitável.
- Tamanho e impacto operacional conhecidos.
- Boundary claro para substituição quando for SDK de fornecedor.

## Pinagem

- Aplicações usam lockfiles.
- Container base usa digest ou versão imutável controlada.
- Provider SDK não determina tipos de domínio.
- Atualizações automáticas abrem revisão e executam testes; não fazem merge cego.

## Dependências críticas esperadas

- Python: FastAPI, Pydantic, PyMuPDF, OpenCV, NumPy, SciPy, Shapely, `ezdxf`,
  `openpyxl` (leitura e render auditado da planilha de medição).
- TypeScript: React, Konva, client HTTP/schema gerado.
- Infra: Terraform providers AWS pinados.

A lista final depende do scaffold e deve ser minimizada.

## Segurança

- Scan de CVE em CI e imagens.
- Vulnerabilidade crítica explorável bloqueia release.
- Exceção possui owner, justificativa, compensating control e expiração.

## Remoção

Dependência sem uso, abandonada ou substituída deve ser removida com seu código,
configuração e documentação.

