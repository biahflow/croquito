# ADR-0014: Reconhecimento nominal de critério de escopo na aprovação

Status: Accepted
Data: 2026-08-10  
Responsável: Product / Engineering

## Contexto

Um caso real raramente é coberto por inteiro pela primeira família geométrica
implementada. No Guaxindiba, o solver retangular resolve o campo principal, mas muros,
portões e patamares continuam fora da cena métrica. Esses critérios são registrados como
`required_blocker_codes` na revisão de leitura e viram `Issue(severity=CRITICAL)` na cena.

`SceneRevision.export_errors()` bloqueia qualquer issue crítica aberta. Com isso, a cena
real do Guaxindiba nunca poderia ser aprovada nem exportada — não por falta de decisão
humana, mas por construção. O marco "primeiro DXF real aprovado" ficava travado sem que
nenhum ato profissional pudesse destravá-lo.

O domínio já tem o vocabulário necessário e não usado: `IssueStatus.ACCEPTED` e, no
contrato `SceneApproval`, o campo obrigatório `limitations_acknowledged: Literal[True]`.

## Decisão

Ao aprovar, o profissional pode reconhecer nominalmente critérios de **escopo** ainda não
cobertos. Cada código reconhecido passa de `OPEN` para `IssueStatus.ACCEPTED` na revisão
aprovada e entra no `aprovacao.json` que viaja dentro do pacote CAD.

A fronteira é dura e verificada no servidor: só é reconhecível um código presente em
`required_blocker_codes_json` da revisão de leitura corrente — isto é, um critério de
cobertura declarado quando a evidência foi carregada. Qualquer outro código recebe
`422 CRITERION_NOT_ACKNOWLEDGEABLE`.

**Nunca são dispensáveis**, porque não são escopo e sim defeito ou dívida de verificação:

- `NUMERIC_RESIDUAL_EXCEEDS_TOLERANCE` e demais conflitos do solver;
- `MEASUREMENT_MISMATCH` entre cota confirmada e geometria;
- `APPROXIMATION_NOT_ACCEPTED` e `UNRESOLVED_ENTITY`;
- `CALIBRATION_SUPERSEDED`;
- `EXACT_WITHOUT_PROVENANCE`.

O reconhecimento acompanha as três verificações explícitas do contrato
(`source_evidence_checked`, `geometry_checked`, `limitations_acknowledged`) e uma
declaração de 20 a 500 caracteres, todas obrigatórias e nunca pré-marcadas na interface.

## Alternativas

- **Esperar cobertura geométrica completa.** Rejeitada para este marco: adiaria o primeiro
  DXF real por famílias geométricas inteiras (muro, portão, patamar), sem ganho de
  segurança — o desenho parcial já é útil e a limitação já é conhecida.
- **Semear o caso sem `required_criteria`.** Rejeitada: entregaria exatamente o mesmo DXF,
  porém sem registro nenhum de que a cena cobre só parte do levantamento. Troca segurança
  por silêncio.
- **Permitir reconhecer qualquer issue crítica.** Rejeitada: transformaria o portão de
  exportação em opcional e permitiria publicar geometria com resíduo numérico ou cota
  incompatível sob assinatura profissional.

## Consequências

### Positivas

- A limitação fica escrita no pacote entregue, não só na cabeça de quem aprovou.
- O primeiro DXF real deixa de depender de trabalho geométrico fora do marco.
- `IssueStatus.ACCEPTED` passa a ter significado operacional, e `export_errors()` continua
  sendo o único portão.

### Negativas

- Um pacote aprovado pode representar parte do desenho; quem consome precisa ler o
  `aprovacao.json` para saber o recorte.
- A responsabilidade técnica do reconhecimento é do profissional que assina, e o produto
  passa a depender de essa declaração ser honesta.

## Riscos e mitigação

| Risco | Mitigação |
|---|---|
| Reconhecimento usado para contornar defeito geométrico | Só códigos de `required_blocker_codes` são aceitáveis; blockers de solver e de medida nunca |
| Usuário não perceber o recorte do DXF | Ressalva no `aprovacao.json` dentro do ZIP e critérios listados em texto na tela de aprovação |
| Reconhecimento acidental por clique | Três verificações separadas, nunca pré-marcadas, mais declaração escrita de 20 a 500 caracteres |
| Critério inventado no seed | `seed-review` valida o padrão do código e o registro fica ligado ao operador que carregou |

## Rastreabilidade

- Requirements: ACC-007, ACC-GUA-001, ACC-GUA-002
- Supersedes: none
- Superseded by:
  [ADR-0017](0017-per-criterion-coverage-declaration-and-trace-parity.md)
  (parcial — o ato único de reconhecimento; a fronteira dura dos códigos declaráveis
  segue valendo)
