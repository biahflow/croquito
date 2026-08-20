# Design Approval Package — F-027, teto de verba do orçamento-base

Classification: INTERFACE_CHANGE
Revision: 1
Status: Aprovado (2026-08-20)
Date: 2026-08-20
Produced by: agente (Claude Code)

> Governado por [design-approval](../../../engineering-os/workflows/design-approval.md). Este
> artefato é evidência para um gate humano. Não é implementação e não deve ser copiado para
> código de aplicação.

## Registro de aprovação

| Campo | Valor |
| --- | --- |
| O que foi aprovado | a composição visual da revisão 1: as seis telas com seus estados e as decisões do caderno, incluindo o estouro em âmbar sem botão nenhum no aviso |
| Aprovado por | Daniel Campos |
| Data | 2026-08-20 |
| Revisão aprovada | 1 |
| Explicitamente **não** aprovado | copy final; forma exata do payload de leitura da rodada e onde a porcentagem é calculada; código estável da recusa de teto inválido; remover o teto de uma rodada que já o tem; teto por grupo/etapa e mais de uma demanda por rodada (fora de escopo por contrato); tudo o que o pacote da F-020 já aprovou |

O registro nasce vazio e **só um ato humano o preenche**: nenhum agente aprova desenho, nem o
que produziu. Aprovar esta revisão não aprova a seguinte; pacote materialmente alterado é
revisão nova e precisa de registro próprio.

**Dependência de gate anterior.** Este pacote desenha a semântica fixada pelo
[ADR-0040](../../../adr/0040-teto-de-verba-do-orcamento-base.md), aceito por ato humano em 2026-08-20, na MESMA decisão
que aprovou esta revisão — os dois gates andaram juntos. Se a aceitação do ADR mudar qualquer uma das seis decisões, este pacote
fica velho e vira revisão 2 — o desenho não pode ser aprovado contra uma semântica que o ADR
depois recusar.

## Artefato

| Arquivo | O que é |
| --- | --- |
| [`teto.html`](teto.html) | A rendição autocontida. Abre no navegador sem build, sem rede e sem servidor. |
| [`01-declaracao.png`](01-declaracao.png) | Tela 1 — declarar o teto ao abrir a rodada: preenchido, sem teto (o padrão), valor recusado |
| [`02-edicao.png`](02-edicao.png) | Tela 2 — editar o teto na rodada aberta: repouso e gravando |
| [`03-consumo.png`](03-consumo.png) | Tela 3 — o consumo na etapa “BDI e montagem”: dentro do teto, no limite exato, estourado |
| [`04-sem-teto.png`](04-sem-teto.png) | Tela 4 — a mesma etapa numa rodada sem teto |
| [`05-planilha.png`](05-planilha.png) | Tela 5 — estourado na etapa “Planilha”, com a exportação disponível |
| [`06-estados.png`](06-estados.png) | Tela 6 — estados transversais novos: 409 ao gravar o teto e recusa do valor na tela |

As imagens acompanham o HTML de propósito: elas fixam o que foi aprovado independentemente de
fonte instalada, versão de navegador ou plataforma. Foram capturadas do próprio `teto.html` em
2026-08-20, viewport 1440 × 1000, escala 2×, com o Chromium do cache do Playwright
(`chromium-1234`, Google Chrome for Testing 151.0.7922.34), um PNG por tela recortado pela
bbox da seção — o script de captura é descartável e não faz parte do pacote. **Inter não está
instalada na máquina que capturou**, então o texto de interface aparece na fallback do
sistema — é a mesma condição de qualquer máquina sem a fonte, e o que se aprova é a
composição, não o desenho da letra.

A capa, as notas de caderno e o fecho não têm PNG próprio: são texto, e o que eles dizem está
repetido neste README.

## Superfícies e estados incluídos

| Superfície | Estado | No pacote |
| --- | --- | --- |
| Abertura de rodada — campos de teto | teto e demanda preenchidos | sim |
| Abertura de rodada — campos de teto | vazios (o caminho normal) | sim |
| Abertura de rodada — campos de teto | valor recusado pela tela, botão indisponível | sim |
| Lista de orçamentos do tenant | rodada com teto (linha extra) e rodada sem teto (sem linha) | sim |
| Painel “Teto da verba” na etapa BDI e montagem | repouso, com teto declarado | sim |
| Painel “Teto da verba” | gravando | sim |
| Painel “Teto da verba” | vazio, em rodada sem teto | sim |
| Bloco de consumo na “Prévia do orçamento” | dentro do teto (consumo e restante) | sim |
| Bloco de consumo | no limite exato — declarado por extenso como **não estouro** | sim |
| Bloco de consumo | estourado (valor e % acima, três consequências escritas) | sim |
| Faixa permanente de estouro | na etapa BDI e montagem | sim |
| Faixa permanente de estouro | na etapa Planilha, com exportação disponível | sim |
| Etapa BDI e montagem | rodada **sem** teto: nada acrescentado à prévia | sim |
| Transversal | 409 ao gravar o teto sobre versão velha, com o valor digitado preservado | sim |
| Transversal | recusa do valor pela validação da tela | sim |
| Documento `.xlsx` impresso | qualquer | **não** — decisão 5 do ADR-0040 é uma *subtração*: o teto não é impresso, o layout não muda, e desenhá-lo aqui convidaria a mexer nele. A afirmação está na Tela 5 e na nota de caderno que a acompanha. |
| Transversal | 403, 409 genérico, recusas de domínio da montagem, vazio/carregando/erro da abertura, auditoria reprovada | **não** — já aprovados no [pacote da F-020](../../F-020-orcamento-base-web/mock/README.md) e **não mudam** por existir teto. Citados na Tela 6, não redesenhados. |
| Teto por grupo/etapa; várias demandas por rodada | qualquer | **não** — fora de escopo por contrato, e **não desenhado nem como reservado** |
| Remover o teto de uma rodada que já o tem | qualquer | **não** — o ADR não decide; ver “Questões em aberto” |
| Todas | foco de teclado, ordem de foco, leitor de tela | **não** — HTML estático não sustenta a afirmação; é requisito de implementação |
| Todas | celular | **não** — jornada é desktop por declaração (piso de 1180px na casca), e exceção nova exige decisão nova |

## Proveniência dos valores visuais

Design System de referência: [`docs/engineering/DESIGN_SYSTEM.md`](../../../engineering/DESIGN_SYSTEM.md),
lido em 2026-08-20. Se este pacote e essa fonte divergirem, a fonte vence e o pacote está velho.
O CSS verbatim do artefato foi **recortado das folhas reais por script**, não redigitado.

| Valor | Origem | Novo? |
| --- | --- | --- |
| Tokens de cor (`--bg`, `--ink`, `--accent`, `--accent-text`, `--dark`, …) e reset | cópia verbatim de `apps/web/src/styles.css:24-72` | não |
| Topbar da casca, marca e wordmark | cópia verbatim de `apps/web/src/styles.css:508-556`; o SVG do wordmark é o mesmo dos pacotes da F-020 e da F-025 | não |
| `h1` em Georgia, 25px, peso 600 | cópia verbatim de `apps/web/src/styles.css:930-946` | não |
| Pílulas do topbar e seletor de jornadas | cópia verbatim de `apps/web/src/styles.css:689-756` | não |
| Painel, cartão, etapa, banner, campo, botão, selo, tabela, `mono`, `digest`, `dica`, `aviso-fixo`, `workspace` | cópia verbatim de `apps/web/src/orcamento/styles.css:31-732` (a folha da **jornada do orçamento** inteira, sem o wrapper `.jornada-orcamento`) | não |
| Texto do aviso permanente da jornada | cópia verbatim de `AVISO_ORCAMENTO`, `apps/web/src/orcamento/labels.ts:29-31` | não |
| Texto do 409 | cópia verbatim de `MENSAGEM_ORCAMENTO_MUDOU`, `apps/web/src/orcamento/labels.ts:38-41` | não |
| Textos do BDI e da montagem | cópia verbatim de `AVISO_BDI` e `DICA_BDI`, `apps/web/src/orcamento/labels.ts:54-61` | não |
| Âmbar `#b47512` / `#6b3a06` / `#3c2708` / `#fbe6c2` / `#f6d99a`, vermelho `#a02323` / `#7a1212` | hexes que já vivem na folha do orçamento (`orcamento/styles.css:120-129`, `:170-198`, `:280-283`, `:478-486`), reusados no bloco autoral | não |
| Bloco de consumo (`.teto-consumo`, `.teto-dentro`, `.teto-limite`, `.teto-estourado`) | composição nova sobre a veste de `.banner-sucesso`/`.banner-conflito` existentes | **sim** |
| Etiqueta escrita do estado (`.teto-etiqueta`) | forma nova, do mesmo feitio do `.selo` existente | **sim** |
| Linhas rótulo → valor com números tabulares (`.teto-linhas`, `.teto-valor`, `.teto-resultado`) | forma nova; `font-variant-numeric: tabular-nums` já é usado em `.tabela .numero` | **sim** |
| Faixa permanente de estouro (`.teto-faixa`, `.teto-faixa-etiqueta`) | forma nova — borda fechada + etiqueta escrita, sobre a margem e as cores dos banners da jornada | **sim** |
| Campos “Teto da verba” e “Demanda de origem” | composição nova sobre `.campo`/`.campo-dica`/`.campo-erro` existentes | **sim** |
| Painel “Teto da verba” na etapa BDI e montagem | composição nova sobre `.painel` existente | **sim** |
| Coluna com dois painéis empilhados (`.coluna-empilhada`) | cola de layout nova, com o mesmo respiro de 16px da grade `.workspace` | **sim** |
| Moldura do caderno (capa, índice, rótulo de estado, quadro, nota de caderno, fecho) | forma nova — é do artefato, não do produto; herdada dos pacotes da F-020 e da F-025, exceto `.mock-nota-caderno`, que é deste | **sim** |
| Tamanho, espaçamento e raio de tudo acima | valores novos: o Design System registra que o projeto **não tem** escala tipográfica, de espaçamento nem de raio | **sim** |

Nenhum valor de cor novo entra neste pacote. Criar escala tipográfica, de espaçamento ou de
raio continua sendo decisão com artefato próprio e não entra de carona nesta feature.

## Entregue × reservado

| Elemento | Esta feature | Reservado para | Vira real quando |
| --- | --- | --- | --- |
| Campos de teto e demanda na abertura da rodada | entrega | — | — |
| Painel “Teto da verba” na etapa BDI e montagem, com guarda de versão | entrega | — | — |
| Bloco de consumo na prévia, nos três estados | entrega | — | — |
| Faixa permanente de estouro, em toda etapa da rodada | entrega | — | — |
| Linha do teto na lista de orçamentos do tenant | entrega | — | — |
| **Teto por grupo ou por etapa; várias demandas por rodada** | não desenha | feature futura | houver decisão de produto; hoje é Out of Scope do contrato |
| **Remover o teto de uma rodada que já o tem** | não desenha | revisão futura deste pacote | o ADR ou o gate disser o que apagar o campo significa |
| **Qualquer corte ou sugestão automática de item** | não desenha, e não desenhará | — | nunca por esta feature: decisão de escopo é humana, por contrato |
| **Layout impresso do `.xlsx`** | não toca | — | — |

**Nada é desenhado como “reservado” neste pacote**, e isso é decisão. Um campo de teto por
grupo em cinza, ou um botão “ajustar escopo” desligado, diria que a coisa existe e está apenas
indisponível — e no caso do corte automático diria o contrário do que o contrato decidiu.

## Decisões que este pacote carrega

- **O estouro é âmbar, nunca vermelho.** É a decisão de cor do pacote, e ela é uma recusa.
  Nesta jornada o vermelho (`.banner-erro`) significa exatamente uma coisa — “o servidor
  recusou e nada foi gravado”. O estouro não recusa nada (ADR-0040, decisão 4), e vesti-lo de
  vermelho ensinaria a orçamentista a ler recusa onde não há, corroendo o significado do
  vermelho no resto do produto. O peso de primeira ordem vem da **forma e da repetição** —
  faixa de largura inteira com borda fechada, etiqueta escrita, número em destaque, presença
  em toda etapa —, não do matiz.
- **O bloco de estouro não tem botão nenhum.** Toda saída do estouro é decisão humana *fora*
  da tela: cortar escopo, remanejar quantitativo, pedir verba suplementar. “Ajustar para caber”
  seria o corte automático que o contrato proíbe; “rever o teto” colado no aviso ensinaria a
  saída errada — subir o número até o aviso sumir. Editar o teto continua sendo ato do painel
  de teto, na mesma etapa, a dois palmos de distância e sem estar oferecido como remédio.
- **O limite exato não ganha cor própria — de propósito.** “Dentro do teto” e “no limite
  exato” são o mesmo estado de domínio (ADR-0040, decisão 3) e por isso compartilham a mesma
  veste; o que muda é a palavra, e ela diz por extenso que aquilo **não é estouro**. Uma
  terceira cor inventaria uma terceira semântica que o ADR não tem.
- **O consumo mora colado ao Total geral**, dentro da “Prévia do orçamento”, e diz por escrito
  que compara o total **com BDI**. Separar o consumo do número que ele deriva abriria espaço
  para os dois se contradizerem na mesma tela; e como a prévia mostra os dois totais, a
  comparação precisa nomear qual deles usou.
- **O teto é declarado onde a rodada nasce, e editado num painel da etapa de montagem.** Ele é
  parâmetro da rodada, como o BDI — não um passo da cadeia de precificação. Uma etapa própria
  “Teto” foi recusada: daria ao teto o peso de uma etapa, e não há nada a *fazer* com ele.
- **Ausência de teto não é um estado a comunicar.** Sem teto não há bloco, não há faixa, não há
  “teto: —”, não há espaço reservado, e a lista de orçamentos não ganha linha. A Tela 4 existe
  só para provar isso visualmente (ADR-0040, decisão 6) — com **uma ressalva declarada**: o
  painel “Teto da verba”, vazio e silencioso, aparece mesmo assim, porque sem ele uma rodada
  aberta sem teto nunca poderia ganhar um.
- **Zero não é “sem teto”.** O campo vazio é “sem teto”; `0,00` é recusado pela tela, com a
  frase que diz qual é o caminho para não ter teto. O desenho recusa a ambiguidade em vez de
  escolher por quem digitou.
- **A planilha não é redesenhada, e a única afirmação do pacote sobre ela é uma subtração:**
  o `.xlsx` não carrega o teto (decisão 5). A prova está na Tela 5 — a faixa de estouro na
  etapa Planilha, ao lado de um botão de exportar que funciona.
- **Nenhum dialeto novo para o 409.** Gravar o teto é mais uma mutação com versão base, e usa
  a frase que a jornada já tem, sem uma palavra alterada.

## Questões em aberto

Continuam abertas depois da aprovação e **não podem ser resolvidas por um agente** durante a
implementação:

- **Forma exata do payload de leitura da rodada** e onde a porcentagem é calculada — no
  servidor, junto de `{target, consumed, remaining, over}`, ou na tela, a partir dos dois
  valores já truncados. O que este pacote fixa é que **a tela nunca recomputa dinheiro**.
- **O código estável da recusa de teto inválido no servidor.** A validação desenhada aqui é a
  da tela; nomear invariante de domínio é ato do plano de execução.
- **Remover o teto de uma rodada que já o tem.** Apagar o campo é voltar a ser rodada sem
  teto, ou é ato que o servidor recusa? O ADR-0040 não decide e este caderno não inventa: não
  há botão de remover.
- **Se o painel “Teto da verba” pode aparecer recolhido** atrás de um link em rodada sem teto,
  devolvendo a etapa ao estado idêntico ao de hoje. É a recusa mais barata do caderno.
- **Copy final.** Todo texto aqui é proposta — inclusive as três consequências escritas do
  bloco de estouro, que são a parte mais autoral e a mais fácil de errar. Aprovar o visual não
  aprova o texto.

## Notas para quem implementar

- **Intencional, preservar:** o âmbar do estouro (e a ausência de vermelho); a faixa presente
  em toda etapa, inclusive na Planilha; a ausência de qualquer botão dentro do bloco de
  estouro; o limite exato dito por extenso como não-estouro; o consumo colado ao Total geral,
  nomeando o total com BDI; a rodada sem teto sem nenhum acréscimo à prévia; `0,00` recusado
  com a frase que ensina o campo vazio.
- **Ilustrativo, não é especificação:** “Praça do Exemplo”, `praca-do-exemplo`, “Largo
  Sintético”, “ORÇAMENTO-BASE 2026”, “Relação de Praças 2026 · demanda 14”, todos os valores,
  percentuais, digests, nomes de arquivo e datas. Os totais foram herdados do pacote da F-020
  para que os dois cadernos falem do mesmo orçamento.
- **Não copie este HTML.** Ele não tem comportamento, estado, acessibilidade auditada nem
  internacionalização. O CSS é recorte de `apps/web/src/styles.css` e de
  `apps/web/src/orcamento/styles.css` feito em 2026-08-20: as folhas são a fonte de verdade, e
  se divergirem, elas vencem.
- **O que o artefato não mostra e a implementação deve resolver:** ordem de foco, navegação
  por teclado, rótulos para leitor de tela, o anúncio do estado de estouro para leitor de tela
  quando ele muda, o comportamento de espera enquanto o teto grava, e o piso de 1180px da
  casca das jornadas.
- **Onde a superfície vive:** a jornada é o orçamento
  ([`apps/web/src/orcamento/`](../../../../apps/web/src/orcamento/etapas.ts) e a folha dela),
  não a medição nem a casca. A etapa `montagem` (“BDI e montagem”) já existe em
  `etapas.ts:66-73`; este pacote **não acrescenta etapa**.
- **Defeito pré-existente encontrado no caminho, e deliberadamente não consertado:** a lista
  “Orçamentos do tenant” renderiza os metadados de cada rodada com `.topbar-meta`
  (`apps/web/src/orcamento/OrcamentoApp.tsx:1125-1144`), cuja cor é `--dark-ink-soft` — a
  tinta do topbar **escuro**. Sobre a superfície clara do painel, esse texto fica praticamente
  invisível. É defeito da F-020, alheio a esta feature e fora do escopo deste artefato; o mock
  usa `.dica` nessas linhas e declara a troca na própria tela. Consertá-lo é trabalho de
  outra tarefa.
- **Precedentes:** o [pacote aprovado da F-020](../../F-020-orcamento-base-web/mock/README.md)
  é a jornada em que esta feature entra, e o
  [pacote aprovado da F-025](../../F-025-boletim-medicao-web/mock/README.md) é o modelo de
  estrutura deste — inclusive na separação entre aprovação de visual e aprovação de texto.
- **Fronteira:** nada disto alcança a medição licitada. Lá o saldo contratual já cumpre o
  papel, e a fronteira do [ADR-0027](../../../adr/0027-price-source-provenance-and-bid-boundary.md)
  continua intacta.
