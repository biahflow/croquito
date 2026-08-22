# Design Approval Package — F-033, demanda sob contrato licitado

Classification: INTERFACE_CHANGE  
Revision: 1  
Status: **Pendente de aprovação humana**  
Date: 2026-08-22  
Produced by: agente (Claude Code)

> Governado por [design-approval](../../../engineering-os/workflows/design-approval.md). Este
> artefato é evidência para um gate humano. Não é implementação e não deve ser copiado para
> código de aplicação.
>
> O vocabulário desta tela é o que o
> [ADR-0045](../../../adr/0045-terceiro-estado-demanda-sob-contrato.md) fixou (`Accepted`,
> 2026-08-22): "demanda sob contrato" no domínio, "Sob contrato licitado" no selo.

## Registro de aprovação

| Campo | Valor |
| --- | --- |
| O que foi aprovado | — |
| Aprovado por | — |
| Data | — |
| Revisão aprovada | — |
| Explicitamente **não** aprovado | — |

Preenchido ao transcrever uma decisão humana explícita. Nenhum agente aprova design,
inclusive o que produziu o pacote. Aprovar esta revisão não aprova a seguinte.

## Artefato

| Arquivo | O que é |
| --- | --- |
| [`regime.html`](regime.html) | A rendição autocontida. Abre no navegador sem build, sem rede e sem servidor. |
| [`00-pagina-inteira.png`](00-pagina-inteira.png) | Todos os estados numa imagem |
| [`01-cabecalho-regime.png`](01-cabecalho-regime.png) | Cabeçalho da rodada sob o regime, com o selo |
| [`02-cascata-regime.png`](02-cascata-regime.png) | Aba Cascata sob o regime: uma fonte só |
| [`03-recusa-fonte.png`](03-recusa-fonte.png) | Recusa de fonte proibida, na instalação |
| [`04-recusa-declaracao.png`](04-recusa-declaracao.png) | Recusa de declarar o regime com cascata suja |
| [`05-candidato-aditivo.png`](05-candidato-aditivo.png) | Item rejeitado marcado como candidato a aditivo |
| [`06-sem-regime.png`](06-sem-regime.png) | Rodada sem regime — exatamente como hoje |
| [`07-declarar.png`](07-declarar.png) | O ato de declarar o regime |
| [`08-reservado.png`](08-reservado.png) | Bloco reservado, **não** entregue nesta fatia |

## Decisões que este pacote carrega

1. **O selo aparece em dois lugares, não em um.** No cabeçalho, porque o regime vale para a
   rodada inteira; e na aba Cascata, porque é ali que a regra age e ali que a recusa
   acontece. Um selo só no topo faria a recusa parecer arbitrária a quem está na aba.
2. **A recusa é frase de obra, não código.** Ela diz o que aconteceria se a fonte entrasse:
   um preço que a medição recusaria depois, sobre serviço já executado.
3. **Recusar não altera nada.** As duas telas de recusa mostram a cascata intacta e dizem
   por escrito que nada foi gravado.
4. **Declarar o regime é ato próprio**, com seletor e botão, no molde do teto da F-027 — não
   é caixa de marcar escondida no formulário de abertura.
5. **Ausência de regime não tem selo.** A tela 6 é a de hoje, sem nenhuma peça nova:
   ausência não é um valor, é a falta dele.
6. **O produto não mente sobre o que sabe.** A tela do candidato a aditivo diz que a
   orçamentista não achou código na tabela contratual — nunca que o item não existe no
   contrato. E a tela de declarar diz, por escrito, que restringir a origem não confere o
   contrato.

## Procedência de cada valor visual

Citações do sistema existente, todas da jornada do orçamento aprovada na F-020:

| Elemento | De onde vem |
| --- | --- |
| Tokens de cor, tipografia e raio | `apps/web/src/styles.css`, bloco `:root` — verbatim |
| Topbar escura, `eyebrow`, `topbar-meta` | `apps/web/src/orcamento/styles.css` |
| Aviso permanente âmbar | `.aviso-fixo`, a mesma da jornada |
| Cartão de conteúdo | `.painel` |
| Lista numerada da cascata | `.cascata` + `.item-numero` |
| Selo de origem do preço | `.selo` |
| Faixa de erro | `.app-alert` |
| Pastilha âmbar do candidato a aditivo | `.blocked` da casca, mesmas cores |

**Único valor novo, e é o que está sendo decidido:** o selo do regime — contorno claro sobre
a topbar escura (`--dark-ink` sobre `--dark-line-strong`) e sua variante para superfície
clara na aba Cascata. Nenhuma cor nova entra no sistema; o que é novo é a **forma**: um selo
de contorno, distinto dos selos preenchidos que já indicam origem de preço, porque regime da
rodada e origem de uma linha são coisas diferentes e não podem ler igual.

## Fronteira entre entregue e reservado

**Entregue nesta fatia**: telas 1 a 7 — o selo nos dois lugares, a cascata restrita, as duas
recusas, o candidato a aditivo, a rodada sem regime e o ato de declarar.

**Reservado** (tela 8, tracejada e com opacidade reduzida): amarrar a rodada a um contrato
real e conferir data-base e desconto. É a lacuna que o ADR-0045 nomeia e deixa aberta.
Torna-se real quando o orçamento passar a modelar contrato como entidade. Não é construído
aqui, e o `Out of Scope` do contrato diz o mesmo.

## O que a aprovação desta revisão NÃO cobre

- **A copy final.** Os textos são proposta do agente. Aprovação visual não é aprovação de
  texto, e estas frases carregam regra de domínio — merecem sua leitura à parte.
- **O comportamento**, que é do ADR-0045 e já foi aceito: o que a tela mostra é
  consequência, não decisão desta aprovação.
- **A forma da recusa no servidor** (código de erro, status), que é do plano.
- **Os nomes das fontes de preço** e o formato da data-base exibida.

## Questões em aberto

1. O seletor de regime deve permitir **voltar** para pré-licitação depois de declarado? O
   mock mostra o seletor com as duas opções, o que sugere que sim enquanto o orçamento está
   em aberto. O ADR não decidiu isso.
2. O candidato a aditivo deve aparecer também no cabeçalho, como contador ("2 candidatos a
   aditivo"), ou só na lista de códigos? O mock mostra só na lista.
