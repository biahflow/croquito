# Design Approval Package — F-050, relatório de risco e pendências do período

Classification: INTERFACE_CHANGE  
Revision: 1  
Status: **Aguarda aprovação**  
Date: 2026-09-05  
Produced by: agente (Claude Code)

> Governado por [design-approval](../../../engineering-os/workflows/design-approval.md). Este
> artefato é evidência para um gate humano. Não é implementação e não deve ser copiado para
> código de aplicação. **Nenhum agente aprova design.**

> Este pacote desenha o que o [Feature Contract](../feature.md) especifica. Ele foi
> produzido numa worktree onde o contrato ainda não existia (vivia numa branch à frente),
> e a citação virou link na integração.

## O gate que vem antes deste

Não existe um ADR único que decida a **semântica agregada** deste relatório — as seis fontes já
têm a sua, cada uma no seu módulo:

- `QuantityDivergence` — tolerância nomeada e resolução por decisão humana registrada
  (ADR-0058).
- Pacote de serviços aberto/fechado e `revocations` — identidade do par `(item, código)` e o ato
  de fechamento (ADR-0053), e o ato inverso de revogar (ADR-0061).
- Boletim vencido (`stale`) — a comparação de digest da aprovação nominal, derivada na leitura
  (`approval_state`, F-028); não tem ADR próprio.
- Testemunha de campo divergente — **ADR-0049**, `Accepted`: a divergência é aviso, nunca veto;
  ela não confirma a cota, não bloqueia a exportação e não escolhe um valor vencedor.

Este pacote decide só a **forma**: como as seis aparecem juntas, agrupadas por consequência, num
documento só. O recorte pelo período de medição e o tratamento da testemunha como observação
(Unknowns 1 e 2 do Feature Contract) são **decisão registrada do dono em 2026-09-05** — não uma
escolha deste pacote, e não estão em aberto aqui. Se um dos ADRs acima mudar a semântica de uma
fonte, este pacote muda com ele.

## Registro de aprovação

| Campo | Valor |
| --- | --- |
| O que se aprova | os cinco estados do documento e as cinco decisões abaixo |
| Aprovado por | — |
| Data | — |
| Revisão | 1 |

## Artefato

| Arquivo | O que é |
| --- | --- |
| [`relatorio-de-risco.html`](relatorio-de-risco.html) | A rendição autocontida. Abre no navegador sem build, sem rede e sem servidor. |
| [`00-pagina-inteira.png`](00-pagina-inteira.png) | Os cinco estados numa imagem |
| [`01.png`](01.png) | Estado 1 — período com pendências: as três classes, com os seis achados |
| [`02.png`](02.png) | Estado 2 — período limpo, com o mesmo peso visual do estado 1 |
| [`03.png`](03.png) | Estado 3 — a testemunha de campo, sempre observação |
| [`04.png`](04.png) | Estado 4 — o documento como entrega, ao lado do BM |
| [`05.png`](05.png) | Estado 5 — pendência que atravessa períodos, com a idade escrita |

## Superfícies e estados incluídos

| Superfície | Estado | No pacote |
| --- | --- | --- |
| Documento do período | com pendências, três classes por consequência | sim (01) |
| Documento do período | limpo — é o estado **vazio** da agregação, e tem a mesma forma dos demais | sim (02) |
| Testemunha de campo | observação, nunca risco, painel isolado | sim (03) |
| Documento do período | forma de entrega (cabeçalho, digest, três classes, ao lado do BM) | sim (04) |
| Pendência individual | recorrente entre períodos, com idade em medições | sim (05) |
| Documento do período | carregando | **não** — a leitura é `GET` sem chamada paga; a agregação é síncrona e não introduz espera nova |
| Documento do período | erro / uma das seis fontes indisponível | **não** — fora do escopo desta revisão; ver Questões abertas |
| Documento do período | não autorizado | **não** — herda a autorização já existente da leitura de medição; nenhum papel novo |

## Proveniência dos valores visuais

| Valor | Origem | Novo? |
| --- | --- | --- |
| Tokens de superfície, tinta e linha (`--bg`, `--surface`, `--ink`, `--muted`, `--line`, `--accent`…) | `apps/web/src/styles.css` | não |
| `--cena`, `--cena-soft`, `--cena-line`, `--cena-ink` (azul de "cena aprovada") | `apps/web/src/medicao/styles.css` | não |
| `--atencao`, `--atencao-line`, `--atencao-soft` (âmbar de divergência/aviso) | `apps/web/src/medicao/styles.css` | não |
| Vermelho de bloqueio `#a33d32` | `apps/web/src/styles.css` (`.decision-error`) e `apps/web/src/medicao/styles.css` (bordas de revogação/recusa) | não |
| Glifos `✕` / `⚠` / `○` / `✓` | Convenção já em uso: `MedicaoApp.tsx` documenta "o estado tem símbolo próprio (`✓`, `▲`, `◐`, `✕`, `○`)", e `⚠` já marca divergência (`medicao/styles.css`) | não |
| Painel de confronto (`.item-confronto`/`.item-valor`/`.item-diferenca`) | Mesma forma de `.confronto`/`.valor`/`.diferenca` do mock da F-030 (`docs/features/F-030-levantamento-de-campo-na-revisao/mock/foto-na-revisao.html`) | não |
| Dados da testemunha do estado 3 (Cota 12, 19,75 m × 19,78 m, Marcos Lima, Ana Ribeiro) | Reaproveitados **verbatim** do estado 5 do mock da F-030, para citar a mesma linguagem com o mesmo caso, não um parecido | não |

Nenhuma cor nova é introduzida por este pacote — as três cores das classes já existem no design
system e já significam o que aqui significam (vermelho = bloqueio/erro, âmbar = divergência/
aviso, cinza = observação). O que é novo é **reuni-las numa única hierarquia de severidade por
consequência** num documento que hoje não existe — isso é decisão (nº 1 abaixo), não cor nova.

## Decisões que este pacote carrega

1. **Três classes por consequência** — impede a exportação, muda dinheiro, observação —, nunca
   por origem técnica do achado. Um orçamentista lê "pacote de serviços aberto" e "boletim
   vencido" como problemas de módulos diferentes; o cliente só precisa saber que os dois travam
   a entrega. É a hierarquia que quem não conhece o sistema entende de primeira.

2. **O recorte é o período de medição**, não o mês de calendário — com a consequência aceita: se
   a medição atrasa em relação ao mês, o documento acompanha a medição. Ele sai ao lado do BM,
   que já tem número e fecho contratual; atá-lo ao mês criaria um segundo calendário que a
   medição não segue, e um relatório que não bate com o boletim ao lado dele confundiria mais do
   que ajudaria.

3. **Testemunha de campo é sempre observação.** Promovê-la a risco contradiria o ADR-0049. Ela é
   a pendência que mais "parece" risco — dois números discordando é visualmente idêntico a uma
   divergência de quantidade — e é exatamente por isso que ganha estado próprio (3) e a frase
   escrita: sem isso, a próxima pessoa que tocar o código a promoveria por analogia com a
   divergência de quantidade, que tem a cara parecida e a consequência oposta.

4. **Cada item aponta o ato que o resolve.** Relatório que só acusa gera trabalho de procurar; o
   documento diz onde se resolve. As seis fontes já existem cada uma no seu módulo, com sua
   própria rota de resolução — o valor do relatório é não obrigar quem lê a redescobrir isso
   rodada por rodada, prancha por prancha. A única exceção declarada é a testemunha (estado 3):
   ela não tem ato que a resolva porque não pede decisão nenhuma.

5. **Nenhuma classe de risco é inventada.** Risco aqui é pendência real do sistema, com número, e
   a conferência é contra as seis fontes que já existem — não contra uma opinião sobre o futuro.
   Probabilidade, impacto estimado e matriz 5×5 ficam fora, e o pacote diz que ficam: uma
   categoria subjetiva não teria fonte para conferir, e o documento perderia a propriedade que o
   torna auditável.

## Questões abertas

- **A copy final** de todos os textos, inclusive os nomes das classes e dos atos.
- **Contrato, período, rodadas, elementos, códigos, valores e digests das capturas** são
  **sintéticos** e ilustrativos — não são especificação de formato.
- **Resolver as pendências pelo documento.** Ele aponta e diz onde se resolve; cada ato (fechar
  pacote, decidir divergência, assinar boletim de novo, decidir item de takeoff) continua no
  módulo que já o resolve hoje.
- **Previsão de impacto futuro.** O documento é sobre o que já aconteceu no período fechado, não
  sobre o que pode acontecer no próximo.
- **O recorte por mês de calendário** — recusado por decisão do dono (2026-09-05): ver decisão 2
  acima. Não é uma opção que ficou de fora por esquecimento; é uma alternativa considerada e
  rejeitada.
- **A partir de quantas medições consecutivas** uma pendência recorrente (estado 5) merece
  destaque adicional além da idade escrita — o pacote mostra a idade em todo caso, mas não define
  um limiar de "recorrência grave". Fica para quando houver dado real de quanto tempo uma
  pendência típica leva para fechar.

## Notas para quem implementar

- **Intencional e a preservar**: a classificação por consequência, não por origem; o "ato que
  resolve" em cada item (menos a testemunha, que não tem); o período limpo com o mesmo peso
  visual dos demais estados; a testemunha nunca aparecendo fora da classe observação; a ausência
  de matriz de risco.
- **Ilustrativo, e não é especificação**: contrato, período, rodadas, elementos, códigos, preços,
  digests, nomes e datas das capturas.
- **O que o artefato não mostra**: ordem de foco, comportamento de teclado, leitura por leitor de
  tela, paginação/quebra de página do documento exportável, e o texto de erro vindo da API quando
  uma das seis fontes não puder ser lida.
- A leitura é `GET`, sem mutação e sem chamada paga (Scope item 4 da feature): a agregação
  percorre as rodadas do período e monta o documento na leitura; nada é gravado, e regerar sobre
  o mesmo estado produz o mesmo conteúdo e o mesmo digest (Acceptance Criteria 5).
- As **seis fontes** que este pacote agrega são exatamente estas, e nenhuma outra:
  `QuantityDivergence` (`packages/valuation/src/croquito_valuation/quantity_divergence.py`),
  `pending_items` (`packages/valuation/src/croquito_valuation/takeoff.py:304`), pacote de
  serviços aberto e `revocations` (`packages/valuation/src/croquito_valuation/assignment.py`),
  boletim vencido (`approval_state`, `services/api/src/croquito_api/valuation_rounds.py`) e
  testemunha de campo divergente (`field_witnesses`, F-030/ADR-0049). Uma sétima fonte
  encontrada durante a implementação não vira classe nova por analogia; é questão para o dono.
