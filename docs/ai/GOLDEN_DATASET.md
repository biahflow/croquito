# Golden dataset

Status: Dataset design accepted; content approval required before model claims  
Responsável: Product / Domain Reviewer / AI Engineering  
Última revisão: 2026-08-10

## Política

PDFs originais permanecem fora do Git em storage controlado. Este documento guarda
somente IDs lógicos, classificação e processo de aprovação. Hashes SHA-256 são
capturados pelo comando de ingestão e armazenados no registro protegido do dataset.

## Manifesto lógico

| Dataset ID | Documento lógico | Páginas | Papel |
|---|---|---:|---|
| `golden-guaxindiba-v1` | Levantamento Campo do Guaxindiba | 1 | fácil/golden |
| `golden-toca-v1` | Levantamento Campo da Toca | 1 | médio/golden |
| `golden-raul-v1` | Levantamento Praça Raul Campelo | 1 | difícil/golden |
| `reg-morro-v1` | Levantamento Campo do Morro da Bandeira | 1 | regressão |
| `reg-casinhas-v1` | Levantamento Praça das Casinhas | 2 | regressão |
| `reg-noel-v1` | Levantamento Praça Noel de Carvalho | 1 | regressão |
| `reg-levantamentos-v1` | Levantamentos | 9 | regressão |

Total: 16 páginas.

## Conteúdo do gabarito

Cada golden case possui, em storage protegido:

- Manifest com digest, resolução e rotação.
- Regions aprovadas.
- Transcrições e unidades aprovadas.
- Associação medida→feature.
- Constraints e hipóteses.
- SceneRevision aprovada.
- DXF dourado e audit report.
- Assinatura do domain reviewer.

## Aprovação

1. AI/vision produz uma proposta sem acesso ao gabarito.
2. Revisor confere a imagem e registra correções.
3. Geometry engine gera cena e lista indeterminações.
4. Revisor aceita hipóteses explicitamente.
5. DXF é aberto no AutoCAD e auditado.
6. Manifest é congelado com versão e assinatura.

## Uso permitido

- Evals, regressão e demonstração privada autorizada.
- Não usar para fine-tuning automaticamente.
- Não compartilhar com outro fornecedor sem política e consentimento compatíveis.
- Não criar screenshots públicas sem autorização.

## Versionamento

Correção de gabarito cria nova dataset version e explica a mudança. Resultado de
modelo nunca altera o gabarito automaticamente.

## Regressão sem gabarito total

As páginas restantes verificam:

- Pipeline não quebra.
- Páginas esparsas não são descartadas.
- Conteúdo não determinado vira issue.
- Nenhum DXF inválido é publicado.

Elas não sustentam métrica de precisão enquanto não forem aprovadas pelo domínio.

