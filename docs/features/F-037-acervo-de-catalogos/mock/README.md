# Design Approval Package — F-037, acervo central de catálogos

Classification: INTERFACE_CHANGE  
Revision: 1  
Status: Approved (2026-08-22)  
Date: 2026-08-22  
Produced by: agente (Claude Code)

> Governado por [design-approval](../../../engineering-os/workflows/design-approval.md). Este
> artefato é evidência para um gate humano. Não é implementação e não deve ser copiado para
> código de aplicação.
>
> O comportamento que estas telas mostram é do
> [ADR-0047](../../../adr/0047-acervo-de-catalogos-da-plataforma.md), **aceito por ato
> humano em 2026-08-22**. O que se decide aqui é a composição visual, não a regra.

## Registro de aprovação

| Campo | Valor |
| --- | --- |
| O que foi aprovado | a composição visual da revisão 1 — os nove estados capturados e as sete decisões listadas em "Decisões que este pacote carrega" |
| Aprovado por | Daniel Campos |
| Data | 2026-08-22 |
| Revisão aprovada | 1 |
| Explicitamente **não** coberto | a copy final (os textos são proposta do agente); o comportamento, que é do ADR-0047 e já foi aceito; os nomes das rotas e códigos de erro, que são do plano; o formato exibido da data-base e do digest curto |

Nenhum agente aprova design, inclusive o que produziu o pacote. Aprovar esta revisão não
aprova a seguinte: pacote materialmente alterado é revisão nova e precisa de registro
próprio.

## Artefato

| Arquivo | O que é |
| --- | --- |
| [`acervo.html`](acervo.html) | A rendição autocontida. Abre no navegador sem build, sem rede e sem servidor. |
| [`00-pagina-inteira.png`](00-pagina-inteira.png) | Todos os estados numa imagem |
| [`01-hoje-o-arquivo.png`](01-hoje-o-arquivo.png) | O que está no ar: o arquivo é problema da orçamentista |
| [`02-escolha-da-lista.png`](02-escolha-da-lista.png) | Proposto: ela escolhe de uma lista |
| [`03-tabela-propria.png`](03-tabela-propria.png) | O upload de hoje, rebaixado a alternativa declarada |
| [`04-procedencia-na-cascata.png`](04-procedencia-na-cascata.png) | A cascata diz de onde cada fonte veio |
| [`05-filtrada-sob-contrato.png`](05-filtrada-sob-contrato.png) | Sob contrato licitado, a lista já vem filtrada |
| [`06-acervo-vazio.png`](06-acervo-vazio.png) | Nenhuma tabela publicada ainda |
| [`07-plataforma-acervo.png`](07-plataforma-acervo.png) | Administração do acervo, com uma tabela fora de circulação |
| [`08-publicar-tabela.png`](08-publicar-tabela.png) | Publicar, e a recusa de republicar o mesmo conteúdo |
| [`09-reservado.png`](09-reservado.png) | Atualização automática, **não** entregue nesta feature |

## Decisões que este pacote carrega

1. **A lista é o caminho principal; o arquivo vira alternativa nomeada.** O upload não
   desaparece — quem tem EMOP licenciada ou o catálogo de um contrato precisa dele —, mas
   deixa de ser a primeira coisa que a orçamentista encontra. A tela 3 diz **para quem** a
   alternativa serve, em vez de deixá-la como escape genérico.

2. **A opção carrega nome, origem, data-base e contagem.** "SCO-Rio FGV06 desonerado · ref.
   07/2026 · 4.865 itens" é o que distingue duas linhas que, sem isso, seriam ambas "SCO".
   A data-base na própria opção é o que faz um catálogo velho ser visível na hora da
   escolha, e não só no banco.

3. **A cascata declara a procedência de cada fonte.** `DO ACERVO` e `TABELA PRÓPRIA` ao
   lado da linha instalada. Uma proveniência que não distinguisse as duas mentiria sobre a
   origem do preço, e a proveniência por linha é justamente o que o ADR-0027 protege.

4. **Sob regime de contrato, a lista já vem filtrada.** Oferecer SINAPI numa rodada que vai
   recusá-la é oferecer uma recusa. A tela 5 diz por escrito **por que** as outras não
   aparecem — silêncio ali pareceria acervo pobre, não regime.

5. **Acervo vazio não é erro.** A tela 6 afirma que a plataforma ainda não publicou, e
   oferece o caminho que funciona hoje. Não é mensagem de falha, é estado.

6. **Retirar de circulação mostra a consequência.** A linha fora de circulação continua
   visível, com a contagem de rodadas que ainda a referenciam. Some da escolha, não do
   registro — porque apagá-la quebraria as rodadas que a usaram.

7. **Rótulo não se digita onde o arquivo já diz.** Origem, data-base e contagem vêm de
   dentro do `catalog.json` publicado; só o nome de exibição é escrito. É o que impede o
   rótulo de discordar do conteúdo — o mesmo princípio do digest amarrado.

## Procedência de cada valor visual

| Elemento | De onde vem |
| --- | --- |
| Tokens de cor, tipografia e raio | `apps/web/src/styles.css`, bloco `:root` — verbatim |
| `.painel`, `.campo`, `.hint`, botões, `.app-alert` | `apps/web/src/orcamento/styles.css` (F-020) |
| `.cascata`, `.item-numero`, selo de origem | revisão 1 da [F-033](../../F-033-demanda-sob-contrato-licitado/mock/README.md) |
| Abas da jornada de Plataforma | `apps/web/src/plataforma/` (F-012) |

**Único valor novo:** o selo de procedência (`DO ACERVO` / `TABELA PRÓPRIA`) e sua reuso
como marca de fora de circulação. Nenhuma cor nova entra no sistema — reusa
`--surface-sunken` e `--ink-secondary`, a mesma veste do selo de regime claro da F-033. É
selo de **procedência**, e por isso lê diferente dos selos preenchidos que indicam origem
de preço: origem é de onde o preço vem, procedência é quem publicou o arquivo.

## Fronteira entre entregue e reservado

**Entregue nesta feature**: telas 1 a 8 — a escolha, a alternativa do arquivo próprio, a
procedência na cascata, o filtro sob regime, o acervo vazio, a administração e a
publicação.

**Reservado** (tela 9, tracejada e com opacidade reduzida): a plataforma buscar as
data-bases novas sozinha. Fora de escopo pela decisão 10 do ADR-0047, e o obstáculo está
nomeado: apurado em 2026-08-22 que o portal da Caixa responde `429` a download automatizado
mesmo com user-agent de navegador, e o do DNIT monta a listagem por JavaScript.

## Divergências apuradas no planejamento (2026-08-22)

Registradas **antes** da implementação (itens 1 a 3) e **durante** (itens 4 a 6), para que a
revisão 1 não seja lida como fiel ao que foi construído. Nenhuma delas muda o conteúdo
aprovado; a primeira muda a **navegação** e por isso é declarada e não presumida.

1. **A jornada de Plataforma não tem abas.** A tela 7 desenha
   `Tenants | Jornadas | Acervo de tabelas` como abas. `PlatformApp.tsx` (810 linhas) **não
   tem mecanismo de aba nenhum**: é composição por `<section className="authenticated-workspace">`
   **empilhada**, uma por assunto — autorização de IA (linhas 296-418) e disponibilidade de
   jornada (`DisponibilidadeDeJornada`, 654-810). A implementação seguirá o padrão que
   existe: o acervo vira uma **terceira seção empilhada**, não uma aba. O conteúdo aprovado
   da tela 7 — a lista, a linha fora de circulação com a contagem de rodadas, o botão de
   retirar — entra inteiro; o que não entra é a fita de abas, que o mock inventou.

2. **A seção da cascata não usa `eyebrow`.** O mock desenha `<span class="eyebrow">CASCATA
   DE FONTES DE PREÇO</span>`; a tela real (`OrcamentoApp.tsx:1980-2100`) usa
   `<div className="painel-cabecalho"><h2>Cascata de fontes de preço</h2></div>`. A
   implementação segue a tela real. É fidelidade do mock, não defeito do código.

3. **A `CascadeEntry` não tinha campo de procedência** (`orcamento/api.ts:206-218`): ela
   carregava proveniência do **catálogo** (`origin`, `reference_month`, `source_sha256`),
   não do gesto que o instalou. O selo `DO ACERVO`/`TABELA PRÓPRIA` da tela 4 exigiu campo
   novo, **entregue pela T2** — não era leitura de algo que já existia.

## Divergências apuradas na implementação (2026-08-22)

4. **A contagem "3 rodadas ainda a referenciam" não existe** e **não foi fabricada.** A tela
   7 a desenha na linha fora de circulação; nenhuma rota devolve esse número, e criar uma
   para ele estava fora do escopo da T3. A linha continua visível com a **palavra** e a data
   da retirada, que é o que sustenta a decisão 6 do pacote — mostrar a consequência. Um
   teste negativo fixa a ausência, para o número não nascer inventado depois. Fechar isso
   exige rota nova e é fatia própria.

5. **A publicação é a coluna direita da mesma seção**, não um painel separado com `h2` como
   a tela 8 sugere. A jornada de Plataforma compõe duas colunas por seção — é o que
   `FormularioDeAutorizacao` faz na seção da F-034 —, e um painel próprio seria padrão novo
   numa tela que não tem abas nem painéis independentes.

6. **O acervo não tem toast de sucesso, e isso corrige um erro do Task Contract.** A T3 foi
   instruída a dar ao acervo "seu próprio toast, exatamente como `DisponibilidadeDeJornada`
   faz" — e `DisponibilidadeDeJornada` **não tem toast**. A afirmação era falsa e produziu
   uma segunda faixa `position: fixed` no mesmo canto da tela (`.app-toast`,
   `styles.css:811-815`), que se sobreporia à da seção de autorização quando dois atos
   acontecessem na mesma janela. Corrigido na revisão: a confirmação é a releitura da lista,
   como na seção irmã, e um teste fixa a decisão.

7. **A alternativa "tabela própria" é um botão com aparência de link**, não um `<a>`: ela
   troca o painel, não navega. O mock a desenha como link porque HTML estático não tem
   estado.

8. **Os títulos internos dos dois modos são `<h3>`**, porque o painel real já carrega o
   `<h2>` do `painel-cabecalho` — a hierarquia de cabeçalho da tela não é a do mock, que
   desenhou cada estado isolado.

9. **O aviso da lista filtrada sob regime não nomeia origem nenhuma.** A frase que lista as
   origens aceitas continua sendo a que o servidor manda (`allowed_cascade_origins`), pela
   mesma razão da revisão 1 da F-033: a tela não guarda cópia da regra.

## Questões abertas

1. **Onde a alternativa "tabela própria" vive** — link que troca o painel, como desenhado,
   ou os dois formulários lado a lado. O desenho escolhe o link para que a lista tenha
   precedência visual clara; lado a lado empataria os dois caminhos.
2. **O que aparece quando o acervo tem muitas data-bases da mesma tabela.** Com uma ou duas
   por origem a lista simples serve; com doze meses de SINAPI ela fica longa. A proposta é
   oferecer só a mais recente de cada origem e um "ver versões anteriores" — **não
   desenhado nesta revisão**, e é a primeira coisa a revisitar quando o acervo crescer.
3. **Se a tela de publicação aceita `.xlsx` no futuro.** Hoje não, por decisão 9 do ADR: o
   import roda no CLI. Se um dia rodar no servidor, esta tela muda.
