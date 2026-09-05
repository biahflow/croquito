# F-050 — Relatório de risco e pendências do período, pronto para o cliente

## Status

`READY_FOR_PLANNING`

> **Os dois unknowns respondidos e a prioridade definida por ato humano em 2026-09-05**
> (Daniel Campos): o documento é do **período de medição** — sai junto do BM, com número e
> fecho contratual, que é o recorte que o sistema já tem —, a **testemunha de campo
> divergente entra como observação** (nunca em "impede exportação" ou "muda dinheiro",
> preservando a decisão do ADR-0049 de que ela é neutra), e a prioridade é `MEDIUM`, depois
> da F-049. Resta o Design Approval Package antes do planejamento.

> Registrada como candidata em 2026-09-03, da análise de posicionamento da Orvia, e
> **especificada em 2026-09-05** por seleção humana. Fica em `READY_FOR_SPEC` pela mesma
> razão da [F-049](../F-049-dashboard-executivo-do-contrato/feature.md): há uma pergunta de
> produto que precede o desenho (unknown 1), e ela muda o que o documento é.

## Classification

`INTERFACE_CHANGE` — documento novo, com superfície de leitura e exportação. Exige Design
Approval Package antes do planejamento.

## Priority

`MEDIUM` — **definida por ato humano em 2026-09-05**, e **depois** da F-049: as duas
apresentam o que já existe, mas o dashboard responde a pergunta que se faz toda semana
("como vai o contrato?") e este documento, a que se faz uma vez por mês, junto do boletim.

## Problem

### As pendências existem, mas cada uma no seu canto

Hoje o sistema sabe, e diz, cada risco isoladamente:

- **`QuantityDivergence`** — os dois números, as duas origens, a diferença e a tolerância
  que ela furou, por item ([F-047](../F-047-quantitativo-da-cena-aprovada/feature.md));
- **`pending_items`** — o que o orçamentista ainda não decidiu, por prancha;
- **pacote de serviços aberto** — elemento com código confirmado e fechamento ausente
  ([F-038](../F-038-pacote-de-servicos/feature.md));
- **boletim vencido** (`stale`) — a aprovação aponta para um digest que mudou;
- **testemunha de campo divergente** — a diferença neutra entre cota e trena
  ([F-030](../F-030-levantamento-de-campo-na-revisao/feature.md));
- **códigos revogados** no período ([F-045](../F-045-desfazer-codigo-confirmado/feature.md)).

### O que falta

**Nenhum módulo enumera o agregado de um período de medição inteiro.** Quem quer saber "o
que ficou pendente neste mês, e o que disso é risco de dinheiro" precisa abrir rodada por
rodada, prancha por prancha. O resultado é que ninguém faz — e a pendência aparece na
reunião com o cliente, não antes dela.

### Por que isso é entregável, e não relatório interno

O que a controladoria de obra vende como serviço mensal é exatamente este documento: a
lista do que não fecha, com o número e a origem, entregue **junto do boletim** e antes da
conversa. O croquito já computa cada item da lista; falta juntá-los e dar forma de
documento.

## Desired Outcome

Ao fechar um período de medição, sai — ao lado do BM — um documento com o que ficou
pendente e o que é risco, cada item com origem, número e o ato que o resolveria. Pronto
para mandar ao cliente sem edição.

## Scope

1. **Agregador do período**: percorre as rodadas do período e coleta as pendências das seis
   fontes acima, **sem inventar classe nova de risco** — o que não existe hoje como estado
   não vira risco aqui.
2. **Classificação por consequência**, não por origem: o que **impede a exportação**, o que
   **muda dinheiro** e o que é **observação**. É a hierarquia que o leitor de fora entende.
3. **Documento exportável** ao lado do boletim, com digest e proveniência.
4. **Rota `/v1` de leitura** e tela, sem mutação e sem chamada paga.
5. **Silêncio honesto**: período sem pendência produz o documento dizendo isso — um mês
   limpo é informação, e a ausência de relatório não a transmite.

## Out of Scope

- **Inventar risco novo** (probabilidade, impacto estimado, matriz 5×5). Risco aqui é
  pendência real do sistema, com número; escala subjetiva é outra feature, e provavelmente
  outra empresa.
- **Resolver as pendências pelo documento.** Ele aponta e diz onde se resolve; cada ato
  continua no lugar dele.
- Previsão de impacto futuro — mesma razão da F-049: sem linha de base de tempo, é chute.

## Acceptance Criteria

1. Um período com pendências conhecidas produz o documento com **todas** elas, e a
   conferência é contra as fontes originais (nenhuma pendência aparece só no relatório, e
   nenhuma some).
2. Período limpo produz documento dizendo que está limpo.
3. Cada item aponta a origem (rodada, prancha, item) e o ato que o resolve.
4. A geração não muda estado nem dispara chamada paga, provado por teste.
5. O documento carrega digest e instante; regerar sobre o mesmo estado produz o mesmo
   conteúdo.

## Unknowns

1. ~~**Se o documento é do período de medição ou do mês corrido.**~~ **Respondido em
   2026-09-05: período de medição.** Ele tem número e fecho contratual, cada pendência
   pertence a uma rodada, e o documento sai junto do BM — nada precisa ser inventado. A
   consequência aceita: quando a medição atrasa em relação ao mês, o documento acompanha a
   medição, não o calendário.
2. ~~**Se testemunha divergente entra.**~~ **Respondido em 2026-09-05: entra como
   observação**, nunca nas classes "impede exportação" ou "muda dinheiro". Preserva a
   decisão do ADR-0049 (a testemunha é neutra e não escolhe vencedor) e ainda informa quem
   lê o documento.

## Human Gates

1. ~~**Seleção, prioridade e as respostas dos unknowns 1 e 2**~~ — **cumprido em
   2026-09-05** (Daniel Campos): `MEDIUM`, período de medição, testemunha como observação.
2. **Design Approval Package** — único gate restante antes do planejamento. A
   [revisão 1 do pacote](mock/README.md) foi produzida em 2026-09-05 e **aguarda
   aprovação**: cinco estados e cinco decisões, com as três classes por consequência
   distinguidas por selo escrito e borda (nunca só por cor) e a testemunha de campo presa à
   classe observação, como o ADR-0049 exige.

## References

- `packages/valuation/src/croquito_valuation/quantity_divergence.py` — `QuantityDivergence`
  e a resolução por ato humano.
- `packages/valuation/src/croquito_valuation/takeoff.py:304` — `pending_items`.
- `packages/valuation/src/croquito_valuation/assignment.py` — pacote aberto e revogações.
- [Roadmap](../../product/ROADMAP.md), registro de nascimento das três candidatas.
