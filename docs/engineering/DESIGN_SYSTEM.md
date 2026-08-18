# Design System — croquito

Status: Accepted (parcial — ver "O que ainda não é sistema")  
Responsável: Product / Engineering  
Última revisão: 2026-08-18

Este documento é a **fonte que um Design Approval Package deve citar**, conforme
`workflows/design-approval.md` da Engineering OS. Ele existe porque a identidade do produto
estava escrita — e bem escrita — dentro de um comentário de `apps/web/src/styles.css`, que não é
onde alguém olha antes de desenhar.

**A folha de estilo continua sendo a fonte de verdade em runtime.** Este documento explica,
justifica e estende; se os dois divergirem, `apps/web/src/styles.css` vence e este arquivo está
velho.

## Identidade

"Grafite técnico": superfície clara e quase neutra, tinta grafite, e um verde vetor que aparece
pouco e sempre com intenção. A referência é a prancha técnica, não o dashboard.

Duas famílias tipográficas com papéis separados: **Inter** para interface e dado, **Georgia**
para títulos. A serifada nos títulos é o que dá ao produto o tom de documento — de peça que se
assina — em vez de tom de ferramenta genérica.

## Cor

Tokens em `:root`, verbatim de `apps/web/src/styles.css`.

| Token | Valor | Papel |
| --- | --- | --- |
| `--bg` | `#fafaf8` | Fundo da aplicação |
| `--surface` | `#ffffff` | Superfície de conteúdo |
| `--surface-subtle` | `#f4f4f1` | Superfície secundária |
| `--surface-sunken` | `#efefeb` | Superfície rebaixada |
| `--ink` | `#14181d` | Texto principal |
| `--ink-secondary` | `#5b6169` | Texto secundário — 6,2:1 sobre branco |
| `--muted` | `#9aa0a8` | Ícone, borda de controle, placeholder, desabilitado |
| `--line` | `#e5e5e0` | Divisor e borda |
| `--accent` | `#00c877` | Verde vetor — **só em preenchimento** |
| `--accent-hover` | `#00b169` | Estado hover do preenchimento |
| `--accent-ink` | `#0e1116` | Tinta **sobre** o preenchimento verde |
| `--accent-text` | `#00744a` | Verde para texto e traço fino — 5,8:1 sobre branco |
| `--accent-soft` | `#e6f6ee` | Fundo verde suave |
| `--accent-line` | `#9bdcc0` | Borda verde suave |
| `--dark` | `#0e1116` | Superfície escura (topbar, painéis) |
| `--dark-ink` | `#f2f4f7` | Tinta sobre escuro |
| `--dark-ink-soft` | `rgba(242,244,247,.72)` | Tinta secundária sobre escuro |
| `--dark-line` | `rgba(242,244,247,.12)` | Divisor sobre escuro |
| `--dark-line-strong` | `rgba(242,244,247,.34)` | Borda de controle sobre escuro |

### Regras de uso, na ordem em que importam

Estas regras não são estilo: são contraste medido, e violá-las é regressão de leitura.

1. **`--accent` só em preenchimento** — CTA, pílula ativa — sempre com `--accent-ink` por cima.
   Ele tem **2,2:1 sobre branco** e por isso **nunca serve de cor de texto sobre claro**.
2. **Texto ou traço fino em verde sobre superfície clara usa `--accent-text`** (5,8:1),
   inclusive indicador de estado: ponto, barra, borda de seleção. Indicador invisível é
   regressão, e o estado continua escrito por extenso além da cor.
3. **Texto secundário sobre claro usa `--ink-secondary`** (6,2:1). `--muted` é para ícone,
   borda de controle, placeholder e desabilitado — **nunca** para texto pequeno vivo.
4. **Cor de domínio não é marca.** Os azuis, laranjas, vermelhos e roxos dos estados de leitura,
   proposta, aviso e amarração mantêm matiz e distinção próprios e não são substituídos pela
   paleta da marca.
5. **Cor nunca é o único portador de significado.** Todo estado sinalizado por cor é também
   escrito.

## Tipografia

| Papel | Família | Referência |
| --- | --- | --- |
| Interface, dado, rótulo | `Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif` | `:root` |
| Título | `Georgia, "Times New Roman", serif` | `h1` |

`h1` é 25px, peso 600, em Georgia. `font-synthesis: none` e `text-rendering: optimizeLegibility`
são declarados globalmente: peso falso de fonte não é aceito.

## Marca

| Asset | Uso |
| --- | --- |
| `apps/web/src/assets/croquito-logo.svg` | Wordmark em tinta escura — **fundo claro** |
| `apps/web/src/assets/croquito-logo-dark.svg` | Wordmark em tinta clara — **fundo escuro** |
| `apps/web/public/favicon.svg` | Símbolo: quadrado vetorial verde sobre grafite, canto 22 |

O wordmark tem proporção fixa (viewBox `620 × 150`); em contêiner flexível, largura e altura
precisam ser declaradas, senão ele estica e o desenho recentra dentro do próprio viewBox.

## Layout e alcance

- As **jornadas** (revisão e medição) são desktop por declaração: `body { min-width: 1180px }`.
  É defensável para prancha com viewport, camadas e painel de decisão.
- A **porta de entrada** é a exceção declarada: responsiva, conforme
  [ADR-0032](../adr/0032-porta-de-entrada-e-estado-sem-sessao.md), D6. Exceção nova exige
  decisão nova; não se estende por analogia.

## O que ainda **não** é sistema

Registrado com honestidade, porque um Design Approval Package precisa saber o que pode citar e o
que está inventando. Medido em `apps/web/src/styles.css` e `apps/web/src/medicao/styles.css` em
2026-08-18:

- **Não há escala tipográfica.** Existem **30 valores distintos** de `font-size`.
- **Não há escala de raio.** Existem **11 valores distintos** de `border-radius`, sendo `6px` o
  mais comum (30 ocorrências), seguido de `5px` (13) e `999px` (12).
- **Não há escala de espaçamento.** Margens e paddings são ad hoc.
- **Convivem dois sistemas de unidade**: a folha da casca usa `px`, a folha da medição usa
  `rem`.
- **Não há inventário de componente.** Botão, campo, pílula e painel existem no CSS, mas não
  como contrato nomeado.

**Um agente não deve inventar essas escalas.** Criar escala tipográfica, de espaçamento ou de
raio é decisão de design com efeito em todas as telas: ela passa pelo portão de aprovação
visual, com artefato próprio, e não entra de carona numa feature. Até lá, um pacote de aprovação
que precise de um valor fora da tabela de cor deve **declará-lo como novo**, e não fingir que
citou.

## Como usar num Design Approval Package

1. Cite este documento e a data em que o leu.
2. Todo valor de cor sai da tabela acima. Se não sair, é **novo** e está sendo decidido no
   pacote.
3. As cinco regras de uso valem no artefato como valem no produto — um mock que usa `--accent`
   como cor de texto está errado antes de qualquer discussão de gosto.
4. Tipografia, marca e alcance saem das seções correspondentes.
5. Qualquer valor de tamanho, espaçamento ou raio é, hoje, necessariamente declarado como novo.
   Isso é consequência da seção anterior, não descuido do autor do pacote.

## Referências

- `apps/web/src/styles.css` — fonte de verdade em runtime
- `apps/web/src/medicao/styles.css` — folha da jornada de medição
  ([ADR-0028](../adr/0028-medicao-na-api-v1-autenticada.md), D9)
- [ADR-0024](../adr/0024-rebranding-to-croquito.md) — rebranding para croquito
- [ADR-0032](../adr/0032-porta-de-entrada-e-estado-sem-sessao.md) — porta de entrada e a exceção
  de responsividade
- [Mock aprovado da F-007](../features/F-007-tela-de-login/mock/README.md) — primeiro pacote a
  citar este documento
