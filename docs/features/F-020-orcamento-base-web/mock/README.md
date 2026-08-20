# Design Approval Package — F-020, jornada do orçamento-base

Classification: INTERFACE_CHANGE
Revision: 1
Status: Approved (2026-08-20)
Date: 2026-08-19
Produced by: agente (Claude Code)

> Governado por [design-approval](../../../engineering-os/workflows/design-approval.md). Este
> artefato é evidência para um gate humano. Não é implementação e não deve ser copiado para
> código de aplicação.

## Registro de aprovação

| Campo | Valor |
| --- | --- |
| O que foi aprovado | a composição visual da revisão 1: as oito telas com seus estados e as decisões listadas em "Decisões que este pacote carrega" |
| Aprovado por | Daniel Campos |
| Data | 2026-08-20 |
| Revisão aprovada | 1 |
| Explicitamente **não** aprovado | papel de autorização; forma do escritor e do auditor de planilha; BDI por grupo; copy final; conferência contra o exemplar real da prefeitura |

Aprovar esta revisão não aprova a seguinte. Pacote materialmente alterado é revisão nova e
precisa de registro próprio.

## Artefato

| Arquivo | O que é |
| --- | --- |
| [`orcamento.html`](orcamento.html) | A rendição autocontida. Abre no navegador sem build, sem rede e sem servidor. |
| [`01-abertura.png`](01-abertura.png) | Tela 1 — abertura, com os estados vazio, carregando e erro |
| [`02-cascata.png`](02-cascata.png) | Tela 2 — cascata de catálogos, com cascata vazia e recusa de origem repetida |
| [`03-extracao.png`](03-extracao.png) | Tela 3 — prancha e extração, os cinco estados |
| [`04-revisao.png`](04-revisao.png) | Tela 4 — revisão do takeoff |
| [`05-codigos.png`](05-codigos.png) | Tela 5 — códigos com a fonte citada, incluindo item sem preço |
| [`06-bdi.png`](06-bdi.png) | Tela 6 — BDI e montagem, com o BDI por grupo reservado |
| [`07-planilha.png`](07-planilha.png) | Tela 7 — a planilha, com auditoria aprovada e auditoria reprovada |
| [`08-estados.png`](08-estados.png) | Tela 8 — 403, 409 e recusa de domínio traduzida |

As imagens acompanham o HTML de propósito: elas fixam o que foi aprovado independentemente de
fonte instalada, versão de navegador ou plataforma. Foram capturadas do próprio
`orcamento.html` em 2026-08-19, viewport 1440 × 1000, Chromium 1.62.1, escala 2×. **Inter não
está instalada na máquina que capturou**, então o texto de interface aparece na fallback
`system-ui` — é a mesma condição de qualquer máquina sem a fonte, e o que se aprova é a
composição, não o desenho da letra.

## Superfícies e estados incluídos

| Superfície | Estado | No pacote |
| --- | --- | --- |
| Abertura do orçamento | sucesso (lista) | sim |
| Abertura do orçamento | vazio | sim |
| Abertura do orçamento | carregando | sim |
| Abertura do orçamento | erro de leitura | sim |
| Cascata de catálogos | sucesso (três fontes) | sim |
| Cascata de catálogos | vazio | sim |
| Cascata de catálogos | recusa (`ESTIMATE_CASCADE_ORIGIN_DUPLICATE`) | sim |
| Prancha e extração | ociosa, na fila, em curso, concluída, falhou | sim |
| Revisão do takeoff | item confirmado, proposto e rejeitado | sim |
| Códigos | candidato escolhido, candidato com aviso, item sem preço | sim |
| BDI e montagem | preenchido, com elemento reservado | sim |
| Planilha | layout impresso | sim |
| Planilha | publicada (auditoria ok) | sim |
| Planilha | auditoria reprovou, nada publicado | sim |
| Transversal | sem autorização (403) | sim |
| Transversal | orçamento andou (409) | sim |
| Transversal | recusa de domínio traduzida | sim |
| Todas | foco de teclado, ordem de foco, leitor de tela | **não** — HTML estático não sustenta a afirmação; é requisito de implementação |
| Todas | celular | **não** — jornada é desktop por declaração (piso de 1180px), e exceção nova exige decisão nova |
| Prancha | zoom, pan e overlay vencido | **não** — espelho não redesenhado; vale o que a medição já faz |

## Proveniência dos valores visuais

Design System de referência: [`docs/engineering/DESIGN_SYSTEM.md`](../../../engineering/DESIGN_SYSTEM.md),
lido em 2026-08-19. Se este pacote e essa fonte divergirem, a fonte vence e o pacote está velho.

| Valor | Origem | Novo? |
| --- | --- | --- |
| Tokens de cor (`--bg`, `--ink`, `--accent`, `--accent-text`, …) | cópia verbatim de `apps/web/src/styles.css:22-70` | não |
| Topbar, marca e seletor de jornadas | cópia verbatim de `apps/web/src/styles.css:506-554` e `:687-754` | não |
| `h1` em Georgia, 25px, peso 600 | cópia verbatim de `apps/web/src/styles.css:928-945` | não |
| Painel, cartão, etapa, banner, item, cartão de código, selo, chip, campo | cópia verbatim de `apps/web/src/medicao/styles.css` (a folha inteira, sem o wrapper `.jornada-medicao`, que uma página só não precisa) | não |
| Âmbar `#b47512` / `#6b3a06` / `#fbe6c2`, vermelho `#a02323` / `#7a1212`, cinza `#8a8f8b` / `#5a625c` | hexes que já vivem na folha da medição, reusados no bloco autoral | não |
| Selo de fonte do preço (SCO / EMOP / composição / ausente) | composição nova sobre `.selo` existente, sem cor nova | **sim** |
| Cartão numerado da cascata | composição nova sobre `.cartao` e `.item-numero` existentes | **sim** |
| Bloco `reservado` (tracejado âmbar + hachura + etiqueta) | forma nova | **sim** |
| Rendição da planilha (grade, letras de coluna, tinta verde da coluna nova, blocos de total) | forma nova | **sim** |
| Moldura do caderno (capa, índice, rótulo de estado, quadro) | forma nova — é do artefato, não do produto | **sim** |
| Tamanho, espaçamento e raio de tudo acima | valores novos: o Design System registra que o projeto **não tem** escala tipográfica, de espaçamento nem de raio | **sim** |

Nenhum valor de cor novo entra neste pacote. Criar escala tipográfica, de espaçamento ou de
raio continua sendo decisão com artefato próprio e não entra de carona nesta feature.

## Entregue × reservado

| Elemento | Esta feature | Reservado para | Vira real quando |
| --- | --- | --- | --- |
| Jornada “Orçamento” no seletor, com rota própria | entrega | — | — |
| Cascata de catálogos com ordem declarada | entrega | — | — |
| Selo de fonte por candidato e por linha | entrega | — | — |
| BDI percentual único, na tela e na planilha | entrega | — | — |
| Bloco “itens sem preço na cascata” | entrega | — | — |
| Exportação `.xlsx` com portão de auditoria | entrega | — | — |
| **BDI por grupo** | desenha só o espaço | feature futura | o item carregar grupo como dado **e** houver ADR aceito. Até lá **não é renderizado**: some da tela, não vira controle desligado. |
| **Ponte croqui → orçamento** (quantitativo do scene graph) | não desenha | roadmap, “Próximo — medição além do v1” | existir identidade estruturada de elemento nas entidades |

## Decisões que este pacote carrega

- **“Orçamento” é jornada, não modo da medição.** Terceiro botão no seletor, rota própria,
  cabeçalho próprio. A alternativa — um seletor dentro da medição — foi recusada: foi
  exatamente a ambiguidade que originou a feature, e resolvê-la com mais um controle dentro da
  tela ambígua a mantém.
- **Cada jornada declara seu momento em uma linha fixa.** O aviso permanente do orçamento diz
  que o preço vem da cascata e que nada dali alcança um boletim; o da medição continua o que
  já é. É a fronteira do [ADR-0027](../../../adr/0027-price-source-provenance-and-bid-boundary.md)
  dita na tela, não só no código.
- **A cascata é visível, numerada e reordenável.** A ordem é a regra de precificação; ordem
  implícita seria a regra escondida no lugar onde ela mais importa.
- **A fonte do preço entra na decisão de código, não só no relatório.** Confirmar um código é
  escolher de qual catálogo e com que data-base aquele preço sai — o selo aparece em cada
  candidato, com a posição na cascata.
- **Item sem preço é declarado, nunca precificado por fora.** Ele aparece na tela e ganha bloco
  próprio na planilha.
- **Layout da planilha:** as sete colunas do boletim mais duas — `FONTE` (origem + data-base
  numa célula) e `VALOR UNIT. C/ BDI`. Recusadas: coluna de data-base separada (três colunas
  novas num layout que a prefeitura já valida) e BDI como percentual por linha (repetir o mesmo
  número em toda linha esconde que ele é único).
- **O BDI impresso é a diferença entre os totais truncados**, não o percentual aplicado ao
  total. Cada linha trunca no centavo antes de somar, como todo dinheiro do módulo, e a
  planilha imprime a soma — a alternativa faria a planilha discordar dela mesma no centavo.
- **A falha da auditoria é uma tela, não um rodapé.** “Nada foi publicado” dito por extenso,
  com a célula divergente visível.
- **O 403 não nomeia papel**, porque o papel ainda não foi decidido.

## Questões em aberto

Continuam abertas depois da aprovação e **não podem ser resolvidas por um agente** durante a
implementação:

- **Qual papel autoriza a jornada** — reusar `orcamentista` da medição ou criar um de
  pré-licitação. Decisão de autorização, sua.
- **Como o escritor de planilha passa a aceitar `Estimate`** — adaptador ou generalização do
  escritor. Decisão técnica do plano; o que se aprova aqui é o layout impresso.
- **Forma do auditor de recomputação** — reusar o da medição ou escrever um próprio. O pacote
  fixa que existe portão e que ele falha fechado, não como ele é feito.
- **Copy final.** Todo texto aqui é proposta. Aprovar o visual não aprova o texto.
- **Conferência contra o exemplar real da prefeitura.** Enquanto o arquivo não for lido, o
  layout sai do modelo do boletim que já existe em código (`template.py`, `default_template()`).

## Notas para quem implementar

- **Intencional, preservar:** a jornada como terceiro botão do seletor; a cascata numerada e
  reordenável; o selo de fonte em candidato e em linha; o BDI único declarado na planilha; o
  bloco de itens sem preço; a tela de auditoria reprovada; o 403 sem nome de papel.
- **Ilustrativo, não é especificação:** “Praça do Exemplo”, “Largo Sintético”, todos os
  códigos, quantidades, preços, digests e datas; o desenho vetorial da prancha; a contagem de
  itens dos catálogos; o número de células auditadas.
- **Não copie este HTML.** Ele não tem comportamento, estado, acessibilidade auditada nem
  internacionalização. Os tokens são cópia de `apps/web/src/styles.css` e da folha da medição
  feita em 2026-08-19: as folhas são a fonte de verdade, e se divergirem, elas vencem.
- **O que o artefato não mostra e a implementação deve resolver:** ordem de foco, navegação por
  teclado, rótulos para leitor de tela, comportamento de carregamento incremental e o piso de
  1180px da casca das jornadas.
- **Precedente:** o [mock aprovado da F-007](../../F-007-tela-de-login/mock/README.md) é o
  modelo deste pacote, inclusive na separação entre aprovação de visual e aprovação de texto.
