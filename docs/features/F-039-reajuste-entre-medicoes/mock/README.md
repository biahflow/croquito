# Design Approval Package — F-039, reajuste de preços entre medições

Classification: INTERFACE_CHANGE  
Revision: 1  
Status: **Approved (2026-08-27)**  
Date: 2026-08-27  
Produced by: agente (Claude Code)

> Governado por [design-approval](../../../engineering-os/workflows/design-approval.md). Este
> artefato é evidência para um gate humano. Não é implementação e não deve ser copiado para
> código de aplicação. **Nenhum agente aprova design.**
>
> **Os dois gates da F-039 foram cumpridos por ato humano em 2026-08-27**: este pacote, na
> revisão 1, e o
> [ADR-0055](../../../adr/0055-reajuste-como-ato-declarado-sobre-o-consolidado.md), aceito na
> mesma data.

## Registro de aprovação

| Campo | Valor |
| --- | --- |
| O que foi aprovado | a composição visual da revisão 1 e as oito decisões listadas em "Decisões que este pacote carrega" |
| Aprovado por | Daniel Campos |
| Data | 2026-08-27 |
| Revisão aprovada | 1 |
| Explicitamente **não** coberto | a copy final; os números, nomes e datas das capturas, que são sintéticos; o layout impresso do MAPÃO, que segue o modelo da prefeitura e não é decidido aqui; e as decisões do ADR-0055, que são gate próprio |

Aprovar esta revisão não aprova a seguinte: pacote materialmente alterado é revisão nova e
precisa de registro próprio.

## Artefato

| Arquivo | O que é |
| --- | --- |
| [`reajuste-na-medicao.html`](reajuste-na-medicao.html) | A rendição autocontida. Abre no navegador sem build, sem rede e sem servidor. |
| [`00-pagina-inteira.png`](00-pagina-inteira.png) | Os sete estados numa imagem |
| [`01-abertura.png`](01-abertura.png) | Abertura da rodada: sem reajuste, por índice, ou por versão nova da tabela |
| [`02-fator-de-indice.png`](02-fator-de-indice.png) | Fator, índice e período obrigatórios juntos, com prévia da conta |
| [`03-versao-da-tabela.png`](03-versao-da-tabela.png) | Reprecificação por versão nova, e a recusa quando falta um código |
| [`04-memoria-com-a-conta.png`](04-memoria-com-a-conta.png) | Contratado, fator, vigente — e a declaração carimbada |
| [`05-duas-bases.png`](05-duas-bases.png) | Dois períodos com preços diferentes na mesma linha, e o acumulado somando os dois |
| [`06-sem-reajuste.png`](06-sem-reajuste.png) | O controle: rodada sem declaração imprime o que imprime hoje |
| [`07-recusas.png`](07-recusas.png) | Fator sem índice, fator não positivo, e o guardrail de exportação |

Os números são sintéticos, mas **aritmeticamente consistentes**: `62,40 × 1,0432 = 65,09`
truncado, `65,09 × 120 = 7.810,80`, acumulado `4.992,00 + 7.810,80 = 12.802,80`. Um pacote de
design de produto de dinheiro que mostra conta errada ensina a conta errada.

## Decisões que este pacote carrega

1. **O reajuste é declarado na abertura da rodada, e é opcional.** Uma rodada é de um período,
   e declarar ali é exatamente dizer "a partir deste período". Sem declaração, a tela não fala
   de reajuste nenhum — estado 06 existe para provar isso.
2. **As três opções aparecem juntas, como escolha única**: sem reajuste, por índice, por versão
   nova da tabela. Esconder as duas formas atrás de um menu faria a segunda parecer exceção, e
   ela não é: contratos reais usam as duas.
3. **Fator, índice e período são um bloco só.** Fator sem índice não é conferível contra a
   publicação oficial, e o estado 07 recusa. É a mitigação possível para o número digitado — o
   sistema não tem como validar o valor, mas tem como exigir que ele seja auditável.
4. **A prévia da conta aparece antes de declarar.** A pessoa vê `62,40 × 1,0432 = 65,09` antes
   de gravar, e não descobre o efeito depois na memória.
5. **A memória mostra três colunas: contratado, fator, vigente.** É onde este produto já prova
   cada número, e é onde a prefeitura audita. A declaração inteira — autor, data, índice,
   período, fator — fica carimbada abaixo da tabela.
6. **A linha reajustada tem selo escrito, não só fundo colorido.** Cor nunca é o único
   indicador; o selo "reajustada" diz a mesma coisa em preto e branco.
7. **A versão nova da tabela mostra a reprecificação código a código antes de declarar**, e a
   ausência de um código contratado recusa a declaração inteira — reprecificar metade do
   contrato é pior do que não reprecificar.
8. **O passado aparece explicitamente** (estado 05): duas linhas de período com preços
   diferentes e o acumulado somando os dois. É a tradução visual de "o passado é intocável".

## Proveniência de cada valor visual

| Valor | De onde vem |
| --- | --- |
| `--bg`, `--surface`, `--ink`, `--line`, `--accent*`, `--muted` | `apps/web/src/styles.css` — identidade "Grafite técnico" |
| Tabela, cabeçalho em versalete e números tabulares | Padrão já usado nas telas de medição e orçamento |
| Vermelho `#a33d32` da recusa e âmbar `#7c5210` do aviso | Já em uso nas duas jornadas |
| Verde `--accent-soft`/`--accent-text` do selo de contratado | Já em uso |
| **NOVO** — roxo `#6b4ba1` e a família `--reajuste*` para o que foi reajustado | Introduzido por este pacote. Escolhido por não colidir com nenhum significado em uso na medição (confirmado, recusado, aviso, aditivo). |
| **NOVO** — selo "reajustada" e o bloco de conta pontilhado | Introduzidos por este pacote |

## Fronteira entre entregue e reservado

**Entregue nesta feature:** os sete estados — declaração por índice e por versão de tabela, a
prévia, a memória com a conta, o acumulado em duas bases, o controle sem reajuste e as três
recusas.

**Reservado, desenhado para segurar lugar** (hachurado no estado 02): escolher o índice de uma
**tabela de índices importada** em vez de digitar. Vira real quando existir o importador; o
campo já é modelado para recebê-lo sem quebrar contrato publicado.

## O que a aprovação não cobre

- A **copy final** de rótulos, avisos e mensagens de recusa.
- Os **números, nomes e datas** das capturas.
- O **layout impresso** do MAPÃO e do boletim, que segue o modelo da prefeitura — este pacote
  decide o que aparece, não a diagramação da planilha exportada.
- **Fórmula paramétrica por item** (índices distintos para mão de obra e insumos), que o
  ADR-0055 declara como extensão.
- **Reajuste retroativo** e **reequilíbrio econômico-financeiro**, ambos fora de escopo no
  Feature Contract.
