# Design Approval Package — F-032, app de levantamento de campo

Classification: INTERFACE_CHANGE  
Revision: 2  
Status: revisões 1 e 2 Aprovadas (2026-08-21)  
Date: 2026-08-21  
Produced by: agente (Claude Code)

> Governado por [design-approval](../../../engineering-os/workflows/design-approval.md).
> Este artefato é evidência para um gate humano. Não é implementação e não deve ser
> copiado para código de aplicação.

## Registro de aprovação

| Campo | Valor |
| --- | --- |
| O que foi aprovado | a composição visual da revisão 1: as seis pranchas (13 telas de celular com seus estados) da jornada do técnico — ordens, chegada, coleta, medida vinculada, validação/conclusão e sincronização |
| Aprovado por | Daniel Campos |
| Data | 2026-08-21 |
| Revisão aprovada | 1 |
| Explicitamente **não** aprovado | copy final; catálogo completo da biblioteca de elementos; tela de curva/arco em detalhe; captura e revisão de foto (câmera aberta); entrada por voz; tablet e paisagem; iOS; acessibilidade executável (foco, leitor de tela) — requisito de implementação, não de mock |

Aprovar esta revisão não aprova a seguinte. Pacote materialmente alterado é revisão
nova e precisa de registro próprio.

## Registro de aprovação — revisão 2

| Campo | Valor |
| --- | --- |
| O que se pede aprovar | a prancha 7 (3 telas): 7a gravação de nota de voz offline ancorada; 7b aviso não bloqueante de qualidade de foto calculado no aparelho; 7c painel de sincronização com categorias de áudio, estado de transcrição e nota sobre análise de fotos no servidor — MAIS dois ajustes pedidos pelo usuário em 2026-08-21: (a) a marca do croquito (quadrado de traço verde do wordmark) acompanha o nome na barra de TODAS as telas (toque aditivo nas pranchas 1–6 aprovadas); (b) a chegada (prancha 2) mostra local/endereço vindos da ordem em vez de coordenadas — as coordenadas continuam guardadas como dado, nunca exibidas |
| Motivação | escopo reaberto por decisão humana de 2026-08-21 (itens 8–9 do [Feature Contract](../feature.md)); tarefas T12/T15 do [plan-sync.md](../plan-sync.md) só iniciam a parte de UI após esta aprovação |
| Aprovado por | Daniel Campos ("Aprovado", em sessão, após os dois ajustes) |
| Data | 2026-08-21 |
| Explicitamente **não** coberto | fornecedor de IA (gate próprio); comportamento de transcrição/análise (Feature Contract e tarefas); câmera aberta; limiares de nitidez/exposição (implementação); copy final |

As pranchas 1–6 permanecem aprovadas pela revisão 1; a revisão 2 é aditiva (nenhuma
prancha aprovada foi alterada — a 7c estende a 6a com categorias novas, desenhada como
prancha própria justamente para não tocar a aprovada).

## Artefato

| Arquivo | O que é |
| --- | --- |
| [`campo.html`](campo.html) | A rendição autocontida. Abre no navegador sem build, sem rede e sem servidor. |
| [`01-ordens.png`](01-ordens.png) | Prancha 1 — ordens de levantamento: lista, offline, vazio |
| [`02-chegada.png`](02-chegada.png) | Prancha 2 — chegada ao local: instrumento, referência física, GPS como localização |
| [`03-coleta.png`](03-coleta.png) | Prancha 3 — tela principal de coleta e menu Adicionar |
| [`04-medida.png`](04-medida.png) | Prancha 4 — medida vinculada: teclado próprio e divergência de conferência |
| [`05-conclusao.png`](05-conclusao.png) | Prancha 5 — validação: conclusão bloqueada por crítico e liberada com justificativa |
| [`06-sync.png`](06-sync.png) | Prancha 6 — sincronização, conflito e login expirado offline |
| [`07-voz-ia.png`](07-voz-ia.png) | Prancha 7 (revisão 2) — voz, aviso de qualidade de foto e transcrição no painel |

As imagens fixam o que foi renderizado independentemente de fonte, navegador ou
plataforma: capturadas de `campo.html` em 2026-08-21, viewport 1500px, escala 2×, com o
Chromium do Playwright do próprio repositório dirigido por script descartável (não faz
parte do pacote). Inter não instalada na máquina de captura — o texto aparece na
fallback do sistema; o que se aprova é a composição, não o desenho da letra. A moldura
cinza, títulos de seção e legendas são anotação do caderno, fora da aprovação.

## Superfícies e estados incluídos

| Superfície | Estado | No pacote |
| --- | --- | --- |
| Ordens de levantamento | com ordens (baixada / não baixada / concluída com mídia pendente) | sim (1a) |
| Ordens de levantamento | offline — baixadas abrem, baixar desabilitado com motivo | sim (1b) |
| Ordens de levantamento | vazio, com o que acontece a seguir | sim (1c) |
| Chegada ao local | contexto: instrumento, referência, GPS "não é medição", item obrigatório pendente | sim (2) |
| Coleta | em andamento: cotas confirmadas, segmento sem medida (tracejado + escrito), elemento, foto ancorada, pendências de sync no topo | sim (3a) |
| Coleta | menu Adicionar (ponto, segmento, curva, elemento, foto, observação, fechar perímetro) | sim (3b) |
| Medida | registrar: teclado numérico próprio, confirmação que repete valor e destino | sim (4a) |
| Medida | divergência entre 1ª e 2ª medição, acima da tolerância, sem sobrescrita silenciosa | sim (4b) |
| Conclusão | bloqueada: 2 críticos escritos, botão desabilitado com motivo no rótulo | sim (5a) |
| Conclusão | liberada: pendência não crítica com justificativa preservada | sim (5b) |
| Sincronização | enviando: metadados confirmados antes da mídia, progresso por categoria | sim (6a) |
| Sincronização | conflito campo × escritório com origem/autor/instrumento e decisão explícita | sim (6b) |
| Transversal | login expirado offline — coleta continua, reautenticação só ao enviar | sim (6c) |
| Transversal | pílula Offline/Online e contador de pendências em todas as telas | sim (todas) |
| Observação por voz | gravando offline, âncora declarada, parar/cancelar, destino da transcrição escrito | sim (7a, rev.2) |
| Qualidade de foto | aviso não bloqueante pós-captura (nitidez baixa), refazer × manter | sim (7b, rev.2) |
| Sincronização | categorias de áudio + estado de transcrição + nota da análise de fotos | sim (7c, rev.2) |
| Câmera aberta / revisão da foto | qualquer | **não** — depende de UI nativa do aparelho; desenho próprio em revisão futura |
| Biblioteca de elementos (catálogo completo, propriedades por tipo) | qualquer | **não** — o menu 3b mostra a entrada; o catálogo é superfície própria de fatia futura |
| Curva/arco (definição de raio/corda/flecha) | qualquer | **não** — entrada existe no menu; a tela de definição fica para revisão futura |
| Tablet / paisagem | qualquer | **não** — piloto é celular retrato (Feature Contract) |
| iOS | qualquer | **sem prancha própria** — iOS entrou na matriz do piloto (decisão de 2026-08-21), mas a superfície é a mesma (PWA retrato); diferenças são de plataforma (instalação, codec), não de desenho |
| Foco de teclado, ordem de foco, leitor de tela | qualquer | **não** — HTML estático não sustenta a afirmação; requisito de implementação |

## Proveniência dos valores visuais

Design System de referência:
[`docs/engineering/DESIGN_SYSTEM.md`](../../../engineering/DESIGN_SYSTEM.md), lido em
2026-08-21. Se este pacote e essa fonte divergirem, a fonte vence e o pacote está velho.

| Valor | Origem | Novo? |
| --- | --- | --- |
| Todos os tokens `--bg`…`--dark-line-strong` | tabela de cor do DS, verbatim | não |
| Verde `--accent` só em preenchimento, com `--accent-ink` por cima (CTAs) | regra 1 do DS | não |
| Verde de texto/traço `--accent-text`; texto secundário `--ink-secondary` | regras 2–3 do DS | não |
| Inter (interface) e Georgia (títulos de tela) | seção Tipografia do DS | não |
| Barra superior escura `--dark` com tinta `--dark-ink` | tokens de superfície escura do DS | não |
| Estado sempre escrito além da cor | regra 5 do DS | não |
| `--state-ok/warn/error/todo` (+ fundos suaves) — semáforo da validação e do sync | **novo** — cor de domínio do campo (regra 4 do DS: domínio não é marca); ok reusa a família do verde da marca por parentesco intencional | **sim** |
| `--touch: 48px` (alvo mínimo), escala `--s-*`, raios `--r-*`, tamanhos `--fs-*` | **novo** — o DS declara não ter escala; valores mínimos para celular, decididos neste pacote e restritos ao campo | **sim** |
| Pílula Offline invertida (tinta clara sobre `--dark-ink`) para sol | **novo** — decisão de legibilidade de campo | **sim** |
| Ícones em emoji (📷 ✎ ⌫ etc.) | **novo** — placeholder declarado; iconografia final é decisão futura, fora desta aprovação | **sim** (como placeholder) |
| Layout mobile 390px retrato | **novo** — o DS declara as jornadas desktop (min-width 1180px) e uma exceção aprovada (porta de entrada); o campo é a segunda exceção, decidida no ADR-0043/Feature Contract e materializada aqui | **sim** |

## Entregue × reservado

- **Entregue por esta aprovação:** a linguagem visual do campo (pranchas 1–6) que as
  fatias 2+ da F-032 implementarão.
- **Reservado (desenhado só para segurar lugar):** o contador "N pendentes" na barra
  aparece desde já, mas o painel de sincronização (prancha 6) só vira real na fatia de
  sync; o item "Observação (texto ou voz)" do menu aparece com voz citada, mas voz está
  fora de escopo do MVP (Feature Contract) — no MVP o item entra só como texto.
- O shell da fatia 0 (`apps/field/src/ui/FieldShell.tsx`) é anterior a este pacote e
  declaradamente descartável; ele **não** ganha status por esta aprovação.

## O que esta aprovação não cobre

Copy final de todos os textos; unidades além de metro; o formato do pacote exportado
(contrato de dados, não superfície); qualquer comportamento — tolerâncias, regras de
validação e ordem de sync são do Feature Contract e das tarefas, não deste caderno.
