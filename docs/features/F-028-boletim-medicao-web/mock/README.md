# Design Approval Package — F-028, aprovação nominal e boletim da medição

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
| O que foi aprovado | a composição visual da revisão 1: as cinco telas com seus estados e as decisões do caderno, incluindo a aprovação em dois atos explícitos (mantida por decisão humana na mesma data) |
| Aprovado por | Daniel Campos |
| Data | 2026-08-20 |
| Revisão aprovada | 1 |
| Explicitamente **não** aprovado | copy final; layout impresso do `.xlsx`; forma do registro de aprovação no servidor; recusa registrada (reprovar a medição); múltiplas alçadas e delegação; papel nomeado na mensagem de 403 |

Aprovar esta revisão não aprova a seguinte. Pacote materialmente alterado é revisão nova e
precisa de registro próprio.

## Artefato

| Arquivo | O que é |
| --- | --- |
| [`boletim.html`](boletim.html) | A rendição autocontida. Abre no navegador sem build, sem rede e sem servidor. |
| [`01-etapa.png`](01-etapa.png) | Tela 1 — onde a etapa entra na jornada, com a etapa bloqueada |
| [`02-ato.png`](02-ato.png) | Tela 2 — o ato de aprovação: repouso, confirmação pedida, gravando |
| [`03-aprovacao.png`](03-aprovacao.png) | Tela 3 — aprovação registrada e aprovação caduca |
| [`04-exportacao.png`](04-exportacao.png) | Tela 4 — exportação: ocioso, exportando, publicado, auditoria reprovada |
| [`05-estados.png`](05-estados.png) | Tela 5 — 403, 409 e recusas de domínio traduzidas |

As imagens acompanham o HTML de propósito: elas fixam o que foi aprovado independentemente de
fonte instalada, versão de navegador ou plataforma. Foram capturadas do próprio `boletim.html`
em 2026-08-20, viewport 1440 × 1000, escala 2×, com o Chromium do cache do Playwright
(`chromium-1234`, Google Chrome for Testing 151.0.7922.34) dirigido por CDP — o script de
captura é descartável e não faz parte do pacote. **Inter não está instalada na máquina que
capturou**, então o texto de interface aparece na fallback do sistema — é a mesma condição de
qualquer máquina sem a fonte, e o que se aprova é a composição, não o desenho da letra.

A capa e o fecho do caderno não têm PNG próprio: são texto, e o que eles dizem está repetido
neste README.

## Superfícies e estados incluídos

| Superfície | Estado | No pacote |
| --- | --- | --- |
| Etapa “Aprovação e exportação” na jornada | disponível, com a medição montada | sim |
| Etapa “Aprovação e exportação” na jornada | bloqueada, com motivo por extenso | sim |
| Ato de aprovação nominal | não aprovada (repouso) | sim |
| Ato de aprovação nominal | confirmação pedida (segundo ato) | sim |
| Ato de aprovação nominal | gravando | sim |
| Registro da aprovação | aprovada (quem, quando, digest, decisão, observação) | sim |
| Registro da aprovação | caduca — medição mudou depois de aprovada | sim |
| Exportação do boletim | ocioso | sim |
| Exportação do boletim | exportando (quatro passos escritos) | sim |
| Exportação do boletim | publicado, com arquivo, digest, data e origem | sim |
| Exportação do boletim | auditoria reprovou, nada publicado, célula divergente visível | sim |
| Transversal | sem autorização (403) | sim |
| Transversal | rodada andou (409) | sim |
| Transversal | recusa de domínio traduzida (quatro códigos) | sim |
| Documento `.xlsx` impresso | qualquer | **não** — o layout já existe em código (`template.py`, `default_template()`, escrito por `write_valuation_workbook`), é o que a prefeitura valida e **não muda nesta feature**. Não é superfície nova e não entra nesta aprovação. |
| Aprovação em múltiplos níveis, delegação | qualquer | **não** — fora de escopo por contrato |
| E-mail ou notificação de aprovação | qualquer | **não** — fora de escopo (sem provedor de e-mail; F-008 BLOCKED) |
| Reprovar a medição (`action: reject`) | qualquer | **não** — ver “Entregue × reservado” |
| Todas | foco de teclado, ordem de foco, leitor de tela | **não** — HTML estático não sustenta a afirmação; é requisito de implementação |
| Todas | celular | **não** — jornada é desktop por declaração (piso de 1180px), e exceção nova exige decisão nova |

## Proveniência dos valores visuais

Design System de referência: [`docs/engineering/DESIGN_SYSTEM.md`](../../../engineering/DESIGN_SYSTEM.md),
lido em 2026-08-20. Se este pacote e essa fonte divergirem, a fonte vence e o pacote está velho.
O CSS verbatim do artefato foi **recortado das folhas reais**, não redigitado.

| Valor | Origem | Novo? |
| --- | --- | --- |
| Tokens de cor (`--bg`, `--ink`, `--accent`, `--accent-text`, `--dark`, …) e reset | cópia verbatim de `apps/web/src/styles.css:24-72` | não |
| Topbar da casca, marca e wordmark | cópia verbatim de `apps/web/src/styles.css:508-556`; o SVG do wordmark é o mesmo do pacote da F-020 | não |
| `h1` em Georgia, 25px, peso 600 | cópia verbatim de `apps/web/src/styles.css:930-946` | não |
| Pílulas do topbar e seletor de jornadas | cópia verbatim de `apps/web/src/styles.css:689-756` | não |
| Painel, cartão, etapa, banner, item, tabela do boletim, campo, selo, chip, `mono`, `digest`, `dica`, `aviso-fixo` | cópia verbatim de `apps/web/src/medicao/styles.css:26-877` (a folha inteira, sem o wrapper `.jornada-medicao`, que uma página só não precisa) | não |
| Texto do aviso permanente da jornada | cópia verbatim de `apps/web/src/medicao/labels.ts:20-22` | não |
| Texto do 409 | cópia verbatim de `MENSAGEM_RODADA_MUDOU`, `apps/web/src/medicao/labels.ts:29-32` | não |
| Códigos `VALUATION_NOT_APPROVED`, `APPROVAL_CONTENT_MISMATCH`, `CODE_NOT_IN_CONTRACT`, `PERIOD_NOT_SEQUENTIAL`, `CELL_VALUE_MISMATCH` | códigos reais do domínio (`packages/valuation/src/croquito_valuation/models.py:495-530` e `canonical.py:439`); as frases que os traduzem são propostas | código não, frase **sim** |
| Âmbar `#b47512` / `#6b3a06` / `#3c2708` / `#fbe6c2`, vermelho `#a02323` / `#7a1212`, cinza `#8a8f8b` | hexes que já vivem na folha da medição, reusados no bloco autoral | não |
| Bloco do ato (`.ato`, borda de 2px em `--accent-text`, etiqueta “ATO NOMINAL” preenchida em `--accent`) | composição nova sobre tokens existentes | **sim** |
| Bloco de identidade de quem aprova (`.ato-identidade`) | composição nova sobre `.cartao`/`.campo` existentes | **sim** |
| Bloco de confirmação em âmbar (`.ato-confirmacao`) | composição nova; o âmbar é o mesmo de `.banner-conflito` | **sim** |
| Registro da aprovação (`.registro`, lista de definição em duas colunas) | forma nova | **sim** |
| Aprovação caduca (`.registro-caduca`: tracejado âmbar + etiqueta escrita) | forma nova, citando o mesmo recurso do `.overlay-bloco.overlay-vencido` já existente | **sim** |
| Comparação de digests lado a lado (`.digest-par`) | forma nova | **sim** |
| Progresso da exportação em quatro passos escritos (`.progresso`, `.passo-estado`) | forma nova | **sim** |
| Moldura do caderno (capa, índice, rótulo de estado, quadro, fecho) | forma nova — é do artefato, não do produto; herdada do pacote da F-020 | **sim** |
| Tamanho, espaçamento e raio de tudo acima | valores novos: o Design System registra que o projeto **não tem** escala tipográfica, de espaçamento nem de raio | **sim** |

Nenhum valor de cor novo entra neste pacote. Criar escala tipográfica, de espaçamento ou de
raio continua sendo decisão com artefato próprio e não entra de carona nesta feature.

## Entregue × reservado

| Elemento | Esta feature | Reservado para | Vira real quando |
| --- | --- | --- | --- |
| Etapa “Aprovação e exportação” na jornada de medição | entrega | — | — |
| Ato de aprovação nominal com consequência escrita e identidade da sessão | entrega | — | — |
| Registro da aprovação (quem, quando, digest, decisão, observação) | entrega | — | — |
| Estado de aprovação caduca, com os dois digests visíveis | entrega | — | — |
| Exportação do `.xlsx` com portão de auditoria fail-closed | entrega | — | — |
| Recusas traduzidas do portão de exportação | entrega | — | — |
| **Reprovar a medição** (`ReviewerDecision.action = "reject"`, que o domínio aceita) | não desenha | revisão futura deste pacote | houver decisão de produto sobre o que a recusa destrava na tela |
| **Múltiplas alçadas e delegação de aprovação** | não desenha | feature futura | houver decisão de autorização; hoje é Out of Scope do contrato |
| **Layout impresso do boletim** | não toca | — | — |

**Nada é desenhado como “reservado” neste pacote**, e isso é decisão: um segundo aprovador em
cinza, ou um botão de reprovar desligado, diria que a coisa existe e está apenas indisponível.
O que não foi decidido simplesmente não aparece na tela.

## Decisões que este pacote carrega

- **Aprovar e exportar viram etapa própria, depois de “Boletim”** — resposta proposta ao
  Unknown 2 do contrato. A alternativa (botão no rodapé da etapa que monta a medição) foi
  recusada pelo motivo que o próprio contrato registra como risco: aprovação vira checkbox sem
  peso. Etapa própria também herda o vocabulário que a jornada já tem — bloqueio com motivo por
  extenso, “concluída”, sobreviver a recarregar.
- **A consequência vem antes do botão, e por extenso.** Três frases fixas: publica seu nome,
  libera a exportação, vale só para esta medição exata. O ato tem bloco próprio, com borda e
  etiqueta “ATO NOMINAL · VAL-05”.
- **A identidade é mostrada, nunca digitável.** Não existe campo de nome do aprovador na tela;
  o que aparece é quem está na sessão, com o papel. É o desenho que torna impossível a tela
  contradizer o critério 3 do contrato.
- **A aprovação é amarrada por digest e caduca sozinha.** Medição alterada depois de aprovada
  derruba a aprovação: o registro velho continua visível, marcado como caduco, com os dois
  digests lado a lado, e a única saída oferecida é aprovar de novo — **não existe “exportar
  assim mesmo”**.
- **A exportação é um portão de quatro passos escritos, não uma barra de progresso.** Três dos
  quatro passos acontecem antes de existir arquivo publicado; barra sugeriria que o arquivo já
  está quase pronto quando ele ainda pode ser descartado.
- **Auditoria reprovada é tela, não rodapé.** “Nada foi publicado” dito por extenso, com a
  célula divergente numa tabela — aba, célula, valor esperado, valor encontrado — e o código
  estável ao lado.
- **Confirmar exige um segundo ato explícito**, e o segundo passo repete a consequência em vez
  de perguntar “tem certeza?”. É a proposta mais descartável do caderno: recusá-la não muda
  mais nada do desenho.
- **O 403 não nomeia papel**, porque nomear papel na mensagem é decisão de copy e de
  autorização, e o texto não pode fingir que ela foi tomada aqui.
- **O `.xlsx` não é redesenhado.** O layout impresso já existe em código, já é o que a
  prefeitura valida e não muda nesta feature; desenhá-lo aqui convidaria a mexer nele.

## Questões em aberto

Continuam abertas depois da aprovação e **não podem ser resolvidas por um agente** durante a
implementação:

- **Forma do registro de aprovação no servidor** (Unknown 1 do contrato) — objeto próprio
  espelhando o `SceneApproval`, coluna na rodada, ou outra coisa. É decisão do planejamento,
  com o mapa do explorador; o que este pacote fixa é o que a tela mostra.
- **Se a etapa é mesmo nova** (Unknown 2) — este pacote propõe; a decisão é sua, no gate.
- **Se reprovar a medição precisa existir na web.** O domínio aceita a decisão de recusa; o
  produto ainda não disse o que ela destrava.
- **Copy final.** Todo texto aqui é proposta. Aprovar o visual não aprova o texto.
- **Nomear o papel no 403** e, com ele, a mensagem definitiva de autorização.

## Notas para quem implementar

- **Intencional, preservar:** a etapa própria depois de “Boletim”; a consequência antes do
  botão; a identidade mostrada e não digitável; o digest como vínculo, com o estado de
  aprovação caduca; a ausência de qualquer caminho de “exportar sem aprovação”; os quatro
  passos escritos da exportação; a tela de auditoria reprovada com a célula divergente; o 403
  sem nome de papel.
- **Ilustrativo, não é especificação:** “Praça do Exemplo”, `praca-do-exemplo`, “Contrato
  05/2024”, todos os códigos, descrições, quantidades, preços, totais, digests, datas, o
  `decision_id`, o nome do arquivo e a contagem de células auditadas.
- **Não copie este HTML.** Ele não tem comportamento, estado, acessibilidade auditada nem
  internacionalização. O CSS é recorte de `apps/web/src/styles.css` e da folha da medição feito
  em 2026-08-20: as folhas são a fonte de verdade, e se divergirem, elas vencem.
- **O que o artefato não mostra e a implementação deve resolver:** ordem de foco, navegação por
  teclado, rótulos para leitor de tela, o comportamento de espera enquanto a exportação corre,
  e o piso de 1180px da casca das jornadas.
- **Onde a superfície vive:** a etapa é da jornada de medição
  ([`apps/web/src/medicao/`](../../../../apps/web/src/medicao/etapas.ts) e a folha dela), não da
  casca nem da jornada de orçamento; o vocabulário de estado (`blocked`/`available`/`done`) já
  existe e a etapa nova entra nele.
- **Precedente:** o [pacote aprovado da F-020](../../F-020-orcamento-base-web/mock/README.md) é
  o modelo deste, inclusive na separação entre aprovação de visual e aprovação de texto.
- **Fronteira de contexto:** medição é contexto delimitado próprio
  ([ADR-0016](../../../adr/0016-valuation-bounded-context.md)); nada desta tela empresta forma
  do croqui além do que a jornada já reusa.
