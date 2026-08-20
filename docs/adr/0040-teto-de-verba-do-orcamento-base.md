# ADR-0040: Teto de verba do orçamento-base — declarado, visível, nunca tesoura

Status: Accepted  
Data: 2026-08-20 (aceito por ato humano na mesma data)  
Responsável: Product / Engineering

## Contexto

A Relação de Praças — ponto de partida da cadeia na visão de produto — chega com escopo
itemizado E verba prevista por demanda. O roadmap reserva desde o v1 o "modo teto /
orçamento invertido ('escopo dentro de R$ X'), porta: `EstimateTarget` reservado no
glossário do contexto". A [F-027](../features/F-027-modo-teto-orcamento-invertido/feature.md)
(seleção humana de 2026-08-20) realiza a reserva; este ADR fixa a semântica que o
Design Approval Package dela desenha e que a implementação seguirá.

As perguntas em aberto no contrato: estouro recusa ou avisa? teto é editável? aparece
na planilha? vive no artefato `Estimate` ou na rodada?

## Decisão

1. **O teto é dado da RODADA, não do artefato.** `EstimateTarget` (valor
   `ExactDecimal > 0` + rótulo opcional da origem da verba, ex.: a demanda da Relação
   de Praças) é declarado e editado na rodada de orçamento
   (`estimate_rounds`), por ato humano com `base_version` + `Idempotency-Key`. O
   artefato `Estimate` **não muda** — sem campo novo, sem bump de
   `ESTIMATE_SCHEMA_VERSION`: o orçamento montado continua puro e recomputável, e o
   teto é o contexto de trabalho sob o qual ele foi montado, registrado na rodada e
   nas suas revisões.
2. **A comparação é derivada na leitura, nunca persistida.** O consumo é
   `Estimate.total_amount` (com BDI — o total submissível), já truncado e validado
   pelo domínio; o payload da rodada deriva `{target, consumed, remaining, over}` a
   cada leitura. Nada recomputa dinheiro por fora; nada grava resultado de comparação.
3. **Limite exato não é estouro.** `over = total_amount > target`, estritamente.
   Centavo a centavo: os dois lados já são valores truncados do domínio.
4. **Estouro nunca recusa nem corta.** A montagem monta, a exportação publica; o
   estado `over` é declarado na jornada com o peso visual de aviso permanente. Cortar
   escopo para caber na verba é decisão humana (qual item sai é julgamento de
   engenharia, não de sistema), e recusar a montagem esconderia exatamente o número
   que a orçamentista precisa ver — o tamanho do estouro — além de travar o fluxo
   legítimo de pedir verba adicional para a demanda.
5. **A planilha impressa não carrega o teto.** O `.xlsx` é o documento que a
   prefeitura valida; a verba prevista da demanda é meta interna de trabalho, não
   linha do orçamento. O teto vive na jornada e no registro da rodada.
6. **Rodada sem teto se comporta exatamente como hoje.** O teto é opcional; ausente,
   nenhum bloco de consumo aparece e nenhuma comparação é derivada.

## Alternativas

- **Teto como campo do `Estimate` (schema v3)** — rejeitada: obrigaria bump e faria o
  artefato carregar meta interna; o documento submissível não muda por existir verba
  prevista, e a rodada já é o lugar do contexto de trabalho (cascata, prancha, teto).
- **Estouro recusa a montagem (fail-closed)** — rejeitada: fail-closed protege
  integridade (dinheiro recomputado, auditoria, aprovação), não meta. Recusar não
  protege nada — só esconde o número e força a orçamentista a montar "no escuro" fora
  do produto, que é o estado atual que a F-027 elimina.
- **Corte/sugestão automática de itens para caber** — rejeitada no contrato da
  feature: decisão de escopo é humana, sempre.
- **Imprimir o teto na planilha (linha informativa)** — rejeitada: layout que a
  prefeitura valida não ganha linha de meta interna; qualquer necessidade futura de
  imprimir vira decisão de design própria com exemplar real na mesa.

## Consequências

### Positivas

- O orçamento invertido da visão de produto vira mecânica: declarar a verba, montar
  vendo o consumo, decidir cortes com o número na tela.
- Zero mudança de contrato publicado; F-027 não mexe em schema nem em goldens do
  `Estimate`.
- A fronteira do ADR-0027/0038 fica intacta: nada disso alcança a medição licitada
  (lá o saldo contratual já cumpre o papel).

### Negativas

- O teto não viaja com o artefato: quem ler `estimate.json` isolado não vê a verba da
  demanda (aceito: a rodada é o registro; imprimir/embutir é decisão futura).
- Aviso permanente sem recusa depende da tela para ter peso — mitigado pelo Design
  Approval Package, que trata o estado `over` como aviso de primeira ordem, e pelo
  payload que o expõe em toda leitura.

## Riscos e mitigação

| Risco | Mitigação |
|---|---|
| Comparação recomputada por fora divergir do total truncado | Decisão 2: deriva de `total_amount` validado; teste no limite exato (== teto) nos dois lados |
| Teto editado depois de montado "mudar o passado" | O teto é da rodada e versionado por `base_version`; o payload deriva contra o teto ATUAL e a jornada mostra isso — o artefato montado nunca muda |
| Aviso virar ruído e ser ignorado | Estado `over` desenhado como aviso permanente no pacote de design (gate humano) |

## Rastreabilidade

- Requirements: visão de produto (orçamento invertido por teto da Relação de
  Demanda); roadmap "Próximo — medição além do v1", bullet do modo teto;
  [F-027](../features/F-027-modo-teto-orcamento-invertido/feature.md)
- Supersedes: none — complementa o [ADR-0038](0038-bdi-como-conceito-de-pre-licitacao.md)
  (o consumo compara o total COM BDI) dentro da fronteira do
  [ADR-0027](0027-price-source-provenance-and-bid-boundary.md)
- Superseded by: none
