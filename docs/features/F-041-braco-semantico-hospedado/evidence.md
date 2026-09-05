# F-041 — Evidência

Feature: [O braço semântico roda no caminho hospedado](feature.md)
Estado: `DONE` — aceita por ato humano em 2026-09-05
Data: consolidado escrito em 2026-09-05; a implementação é de 2026-08-26

Este documento existe porque a feature foi **implementada antes de ser planejada como
feature**: o [ADR-0054](../../adr/0054-indice-de-embeddings-publicado-e-braco-semantico-hospedado.md)
(aceito em 2026-08-25, com as quatro decisões de desenho exercidas por ato humano no
próprio aceite) foi executado em 2026-08-26 e integrado à `main` pelo
[PR #114](https://github.com/biahflow/croquito/pull/114) — enquanto o contrato,
escrito em 2026-08-28, permaneceu dizendo `READY_FOR_PLANNING`. É a mesma dessincronia
código-à-frente-dos-docs das F-046/F-047 e da F-030, corrigida aqui.

## O que está na `main`, critério a critério

A linha VAL-12 da [rastreabilidade](../../engineering/TRACEABILITY.md) — corrigida na
própria execução, como o contrato exigia — é o mapa completo. O resumo:

| Critério do contrato | Onde está provado |
| --- | --- |
| 1 · Índice publicado → shortlist híbrida após recompute explícito, com `semantic_notes` | `tests/api/test_estimate_semantic_arm.py` (as duas jornadas) |
| 2 · Fonte sem índice entra só léxica, e a nota diz **qual** | mesmo arquivo (degradação declarada por fonte); visto na tela na bancada de 2026-09-05 |
| 3 · O `GET` não paga nada | provado por adapter que falha se tocado (`test_estimate_semantic_arm.py`) |
| 4 · Entitlement degrada, não recusa | mesmo arquivo; exercido na tela em 2026-09-05 (motivo por extenso, recompute inteiro de pé) |
| 5 · `SuggestionSemantics` singular continua legível após o bump | `tests/valuation/test_assignment.py` |
| 6 · Índice de 40,7 MB passa; maior que o teto recusa por extenso | `CATALOG_INDEX_MAX_BYTES` (64 MiB, `reference_catalog_indexes.py`) + `tests/api/test_reference_catalog_indexes.py` |
| 7 · Republicar o mesmo digest recusa; retirar carimba sem apagar | `tests/api/test_reference_catalog_indexes.py` |
| 8 · Nenhuma coluna deriva de conteúdo de cliente | mesmo arquivo, no molde de `test_reference_catalogs.py` |

Telas: `apps/web/src/plataforma/` (listar, publicar e retirar índice; quatro recusas em
português) e `apps/web/src/orcamento/` (`EstadoDoBracoSemantico`: ler não paga, recalcular
pode pagar, notas do servidor como vieram) — tudo com vitest, verde na suíte corrente.

## Evidência de navegador (2026-09-05)

Bancada delegada pelo dono (Chromium/Playwright, sessão OIDC real, stack local, providers
**desligados** — nenhuma chamada paga), sobre a praça-bancada da F-038/F-042. Capturas em
`output/f041-fecho/` (retenção local de 7 dias):

1. **A aba Códigos, antes**: a copy honesta que a feature exigia — "Ler a shortlist não
   chama provider nenhum […] Recalcular é ato à parte e pode ser chamada paga de IA" e
   "Esta shortlist é léxica: nenhuma fonte da cascata entrou com o braço semântico".
2. **A tabela publicada no acervo pela tela** (jornada de Plataforma, papel
   `platform_operator` concedido temporariamente a um usuário local e revogado ao fim):
   "SCO-Rio Out/2023 · origem sco · ref. 10/2023 · 4.964 itens", com origem/data-base/contagem
   lidos de dentro do arquivo.
3. **O índice publicado pela tela** — um índice *fixture* (vetores determinísticos, mesmo
   contrato do índice pago) construído sobre o catálogo real: "em circulação · receita
   code-description-unit-v1 · 64 dimensões · 4.964 códigos", botão "Retirar de circulação"
   e a frase de que retirar não apaga. A tela recusou publicar índice **antes** de a tabela
   existir no acervo, por escrito — o portão do próprio desenho.
4. **O recálculo explícito degradando em vez de recusar** (D8): com providers desligados, a
   shortlist saiu léxica e a seção "Onde o braço semântico não entrou" disse o motivo por
   extenso — "busca semântica indisponível: providers reais desligados neste ambiente".
   Nenhum 403, nenhum recompute derrubado.

## Revisão

Rodada de 2026-09-05, focada sobre o núcleo integrado: a resolução do índice por digest com
cache por `(index_object_sha256, catalog_sha256)`, o cache de vetores de consulta que vive e
morre dentro do ato (emenda do ADR-0054, comentada no próprio código), o teto próprio de
bytes e a degradação por fonte. **`REVIEW_PASS`** — nenhum achado; a suíte completa passou
verde na `main` corrente no mesmo dia.

## Human Gates

| Gate | Estado |
| --- | --- |
| ADR-0054 e as quatro decisões de desenho | ✅ **Aceitos em 2026-08-25** (Daniel Campos); a emenda do cache de consulta, em 2026-08-28 |
| Aceite da feature | ✅ **Aceita por ato humano em 2026-09-05** (Daniel Campos, pelo chat), sobre a evidência acima |

## Dívidas declaradas

- **Publicar o índice REAL** pela tela de Plataforma — ato do operador, com
  [roteiro próprio](ROTEIRO-ATOS-DE-OPERADOR.md). **Achado de 2026-09-05**: o índice de
  40,7 MB construído em 2026-08-25 **não existe mais** — foi escrito em `output/`, que tem
  retenção local de sete dias, e não está em lugar nenhum do disco. Reconstruí-lo custa
  outra chamada paga (~US$ 0,03). O episódio é a própria tese da feature: enquanto o índice
  for arquivo no disco de uma pessoa, ele se perde; publicado, é artefato da plataforma.
- **O recompute pago real**, com o braço híbrido de verdade (o golden mede 12/12 contra
  9/12 do léxico) — primeira rodada é ato humano com autorização de gasto.
- Nada disso roda em HML enquanto o ambiente estiver derrubado por decisão do dono.
