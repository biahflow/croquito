# Design Approval Package — F-038 rev.2, autoria da matriz e declaração PARTIAL

Classification: INTERFACE_CHANGE  
Revision: 2  
Status: **Proposed — aguardando aprovação humana**  
Date: 2026-08-26  
Produced by: agente (Claude Code)

> Governado por [design-approval](../../../../engineering-os/workflows/design-approval.md), a
> partir do [template global](../../../../engineering-os/templates/design-approval.md). Este
> artefato é evidência para um gate humano. Não é implementação e não deve ser copiado para
> código de aplicação.
>
> O comportamento N:N que esta interface expõe é do
> [ADR-0053](../../../../adr/0053-cardinalidade-n-n-elemento-servico.md), **aceito por ato humano
> em 2026-08-25**. O que se decide aqui é a **interface de autoria da matriz** e a superfície da
> parcela parcial, não a regra.

## Por que existe uma revisão 2

A [revisão 1](../README.md) foi aprovada em 2026-08-26 sobre a **direção de interface descrita em
texto**, sem telas capturadas — e disse explicitamente que, se a execução revelasse decisões
visuais que o texto não resolvia, elas abririam revisão 2, com pacote e aceite próprios. É o que a
issue [#96](https://github.com/biahflow/croquito/issues/96) tornou concreto: a **decisão 6** da
rev.1 (declarar contribuição `PARTIAL` por par `(item, code)`, com nota obrigatória e teto
`≤ quantidade do item`) **não foi implementada**, por um achado de contrato legítimo na execução
da T8/T9.

### O achado de contrato

- A matriz é aceita como o objeto `CalcMatrix` **inteiro**, no corpo da rota de build
  (`POST .../estimate`, campo `calc_matrix`; espelhado em `POST .../calc/build`) — **não** por par
  nas rotas de decisão ou de fechamento de pacote. Ver `BuildEstimateRequest` e
  `BuildValuationCalcRequest` em `services/api/src/croquito_api/main.py`.
- `ApiModel` usa `model_config = ConfigDict(extra="forbid")`. A fiação por-par assumida na rev.1
  (mandar recipe/operandos/`basis`/nota junto de cada decisão `(item, code)`) seria **recusada com
  `422`** — não por lista negra, pelo `extra="forbid"`.
- Surfacear `PARTIAL` fielmente, então, exige **autorar uma matriz na tela**: receita, operandos,
  código de dependência e ordem topológica sem ciclo. Essa é uma superfície visual que o mock
  rev.1 (text-only) não resolve, e para a qual **não há idioma de UI**: a jornada de medição só
  *renderiza* memória (`apps/web/src/medicao/MedicaoApp.tsx`), e **nenhum cliente web produz
  `calc_matrix` hoje** (`grep calc_matrix apps/web/src` não retorna nada).

Por isso a rev.2 vem **antes** de qualquer implementação, exatamente onde o gate deve estar: a
disputa sobre como a matriz é autorada fica barata enquanto a tela não existe.

## Ressalva sobre o que este pacote é

Diferente da rev.1, esta revisão **traz um rendering autocontido** — [`index.html`](index.html),
que abre em navegador sem build, sem rede e sem CDN. O que ela **não** traz é a captura congelada
(imagem): o agente não abriu um navegador neste ambiente e não inventa screenshots, porque isso
transformaria evidência em ficção. A captura fica **pendente do ato de renderização**: quem aprovar
abre o `index.html`, congela a imagem do que viu, e é a ela que a aprovação se refere. O requisito
de "evidência fixa do que foi renderizado" está, portanto, cumprido quanto ao rendering e
declarado como pendente quanto à imagem — honestamente, como a rev.1 fez com a ausência de telas.

## Registro de aprovação

| Campo | Valor |
| --- | --- |
| O que foi aprovado | — *(nada ainda; aguardando ato humano)* |
| Aprovado por | — *(em branco)* |
| Data | — *(em branco)* |
| Revisão aprovada | — *(em branco; esta é a revisão 2, proposta)* |
| Explicitamente **não** coberto | ver "O que a aprovação não cobre", abaixo |

A aprovação da rev.1 **não** cobre esta rev.2: é pacote materialmente novo (nova superfície de
autoria) e precisa do seu próprio ato. Nenhum agente aprova design, inclusive este; o registro
acima fica em branco de propósito, aguardando ato humano.

## Artefato

| Arquivo | O que é |
| --- | --- |
| [`index.html`](index.html) | Rendering autocontido. Abre sem o build, o toolchain ou a rede do projeto. |
| *(captura congelada)* | **Pendente do ato de renderização.** É a ela que a aprovação passará a se referir. |

## Superfícies e estados incluídos

| Superfície | Estado | No pacote |
| --- | --- | --- |
| Autoria — pacote do elemento (A1) | pacote aberto / pendente, parcelas por código | sim |
| Autoria — editor de parcela (A2) | autorando (receita, operandos, dependência) | sim |
| Autoria — ordem topológica (A3) | dependência declarada, sem ciclo | sim |
| Autoria — ciclo de dependência (A4) | erro crítico (`CALC_MATRIX_DEPENDENCY_CYCLE`) | sim |
| PARTIAL — declaração (B1) | teto respeitado, nota obrigatória | sim |
| PARTIAL — acima do teto (B2) | erro de validação (bloqueado) | sim |
| Pacote (C1) | fechado / resolvido | sim |
| Serviço com parcelas de vários elementos (C2) | fusão por código (478,74 m²) | sim |
| Pacote (C3) | vazio (item sem contribuição) | sim |
| Pacote (C4) | loading | sim |
| Pacote (C5) | não autorizado (403) | sim |
| Memória na jornada do orçamento (D1) | render text-only, já entregue no #95, citado | sim |

Estados deliberadamente **fora** do pacote, com motivo: *sucesso do build/boletim renderizado por
completo* (é da F-038 T6/T8, já entregue no domínio e fora da autoria); *aprovação nominal do
orçamento* (F-035, superfície própria já aprovada); *edição de operando existente* (mesma gramática
do editor A2, sem tela nova).

## Proveniência dos valores visuais

Design system referenciado: [`docs/engineering/DESIGN_SYSTEM.md`](../../../../engineering/DESIGN_SYSTEM.md),
lido em 2026-08-26 (fonte de verdade em runtime: `apps/web/src/styles.css`). Se este pacote e a
folha divergirem, a folha vence e este pacote está velho.

| Valor | Fonte | Novo? |
| --- | --- | --- |
| Todos os tokens de cor (`--bg`, `--surface`, `--ink`, `--accent`, `--dark`, …) | DESIGN_SYSTEM.md, tabela de Cor, verbatim | não |
| `--accent` só em preenchimento; texto/traço verde usa `--accent-text` | DESIGN_SYSTEM.md, regras de uso 1–2 | não |
| Estado sempre escrito por extenso, não só por cor | DESIGN_SYSTEM.md, regra 5 | não |
| Inter (interface/dado) e Georgia (títulos, `h1` 25px/600) | DESIGN_SYSTEM.md, Tipografia | não |
| Wordmark "croquito" na topbar escura | DESIGN_SYSTEM.md, Marca | não (uso), — (asset simulado em texto) |
| Tons de atenção (`--warn-*`) e de erro crítico (`--danger-*`) | — | **sim — sendo decididos aqui** |
| Toda escala de tamanho de fonte, espaçamento e raio (`--sp-*`, `--r`, `font-size` locais) | — | **sim — por DESIGN_SYSTEM.md ("O que ainda não é sistema") não há escala; todo valor é necessariamente novo** |

A rev.1 já dependia da mesma cor de domínio para estado; esta rev.2 a torna explícita e a declara
como nova, em vez de fingir que citou. Nenhuma escala de tipografia/espaçamento/raio foi inventada
como *sistema* — os valores são locais deste artefato de evidência, e criar escala de sistema é
decisão de design com gate próprio (DESIGN_SYSTEM.md).

## Fronteira entregue × reservado

| Elemento | Esta feature | Reservado para | Vira real quando |
| --- | --- | --- | --- |
| Editor de parcela (receita, operandos, dependência) | entrega | — | — |
| Declaração `PARTIAL` com nota e teto | entrega | — | — |
| Fechamento de pacote | já entregue (#77/#81), citado | — | — |
| Render text-only da memória | já entregue (#95), citado | — | — |
| Sugestão automática da pilha construtiva ("suggester de pacote") | desenha espaço só (não aparece nesta tela) | marco próprio, com seed curável e gate próprio (ADR-0053, decisão 6 do ADR) | um marco de suggester for aberto e aprovado |
| Aditivo parcial (pacote incompleto por falta de código no contrato) | fora | fora de escopo da F-038 | — |

Nenhum controle inerte é desenhado: o que é reservado (o suggester) simplesmente **não aparece** na
superfície — a shortlist continua por item, e o humano escolhe quantos códigos quiser dela.

## Decisões que este pacote carrega

O foco é a **decisão 6** da rev.1 (a que o #96 destravou) e a **autoria de matriz** que ela exige.

1. **A matriz é autorada na tela, por par `(item, code)`, e vira um `CalcMatrix` no build.** Como a
   fiação por-par é recusada pelo `extra="forbid"` das rotas de decisão, a tela monta o objeto
   inteiro (a autoria) e o build o recebe (`calc_matrix`). Cada célula declara **receita/grandeza**
   (`length_times_width`, `perimeter_times_height`, `qty_times_months`, `days_times_hours`, e
   `declared_product` para o produto de até quatro fatores `a×b×c×n` da T7), **operandos** digitados
   (o nome de cada fator é dado, em português), e opcionalmente **dependência de outro serviço**.
   *(Painéis A1, A2.)*

2. **A ordem topológica é visível e o ciclo é erro.** O serviço que alimenta outro vem antes; a tela
   mostra a ordem de numeração das linhas, e recusa ciclo (`CALC_MATRIX_DEPENDENCY_CYCLE`) e
   auto-referência (`CALC_MATRIX_SELF_DEPENDENCY`) por extenso, nunca escondidos atrás de interação.
   *(Painéis A3, A4.)*

3. **`PARTIAL` é declarada, com nota obrigatória e teto `≤ quantidade do elemento` (decisão 6).** Os
   170 m² de limpeza dentro dos 418,12 do piso não saem de conta nenhuma: a tela mostra o teto do
   elemento, exige a justificativa e **bloqueia** valor acima do teto (`CALC_PARTIAL_EXCEEDS_ITEM`,
   conferência do build porque o teto depende do `TakeoffItem`). *(Painéis B1, B2.)*

4. **Cor não é o único indicador.** Pacote aberto vs. fechado, parcela parcial e serviço derivado de
   outro têm rótulo textual além da cor; aviso crítico (ciclo, teto excedido) é palavra + código
   estável. *(Todos os painéis; herda a decisão 5 da rev.1.)*

5. **A autoria (seção A) e a memória renderizada (seção D) são o mesmo dado, dos dois lados.** A base
   `parcela parcial declarada` e a proveniência `derivada da quantidade de …` que a memória mostra
   (render text-only entregue no #95) são exatamente o que a autoria grava. A rev.2 mostra a costura,
   sem reinventar o render já aprovado/entregue. *(Painel D1.)*

Herdadas da rev.1 e **não** reabertas aqui: a escolha de código deixar de ser exclusiva (decisão 1),
o fechamento ser ato próprio (decisão 2) e a memória passar a existir na jornada do orçamento
(decisão 3). Elas continuam valendo; a rev.2 só acrescenta a superfície de autoria que faltava.

## Open questions — o que a aprovação **não** cobre

Aprovar esta revisão **não** decide, e o que ficar aqui permanece decisão aberta que um agente não
resolve durante a implementação:

- **A copy final.** Rótulos, dicas e mensagens do `index.html` são ilustrativos; as strings reais
  vivem em `apps/web/src/orcamento/labels.ts` e são decisão à parte (copy não é visual).
- **Os nomes de rotas, campos e códigos de erro.** `calc_matrix`, `CALC_MATRIX_DEPENDENCY_CYCLE`,
  `CALC_PARTIAL_EXCEEDS_ITEM` e afins são do plano/domínio (feature.md, plan.md, ADR-0053), não desta
  aprovação. `CALC_PARTIAL_EXCEEDS_ITEM` em particular é **nome proposto** para o teto de builder que
  o ADR descreve mas ainda não nomeia — confirmá-lo é tarefa de implementação, não deste gate.
- **Os tons de atenção/erro e qualquer escala de tamanho/espaçamento/raio**, marcados como novos na
  proveniência. Se aprovados, passam a ser o que estas telas usam; não viram sistema por isso —
  escala de sistema tem gate próprio.
- **A captura congelada (imagem)**, pendente do ato de renderização (ver "Ressalva").
- **O comportamento N:N em si**, que é do ADR-0053 e já foi aceito.
- **Números ilustrativos** (massa específica 0,25, distância 3,50 dam, dimensões do piso): são
  amostra para tornar a tela legível, não especificação. O oráculo é a planilha do Campo do Toca.

## Notas para quem implementar

- **Intencional, preservar:** a autoria por par `(item, code)`; o teto visível e o bloqueio de
  `PARTIAL` acima dele; a nota obrigatória em `PARTIAL`; a ordem topológica à vista e o ciclo como
  erro por extenso; todo estado escrito, não só colorido.
- **Ilustrativo, não especificação:** copy, valores numéricos, nomes de operando, e o desenho exato
  dos cartões. O `index.html` é evidência, não fonte — não copie o HTML para `apps/web/`.
- **O que o artefato não mostra:** foco/ordem de teclado, acessibilidade além de `role`,
  internacionalização e movimento. A jornada é desktop por declaração (`min-width: 1180px`); o
  rendering foi reduzido para caber na página de evidência.

## Referências

- [Feature Contract](../../feature.md) · [Plano](../../plan.md)
- [Design Approval Package rev.1](../README.md)
- [ADR-0053](../../../../adr/0053-cardinalidade-n-n-elemento-servico.md)
- [Design System](../../../../engineering/DESIGN_SYSTEM.md)
- [Workflow design-approval](../../../../engineering-os/workflows/design-approval.md) ·
  [Template](../../../../engineering-os/templates/design-approval.md)
- Issue [#96](https://github.com/biahflow/croquito/issues/96)
