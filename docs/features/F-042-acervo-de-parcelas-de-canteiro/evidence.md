# F-042 — Evidência

## As parcelas de canteiro reais, lidas do documento

**Data**: 2026-08-28. Fonte: aba de memória de cálculo dos três orçamentos reais fornecidos
pelo dono. Os arquivos **não estão versionados**; a leitura é local.

As cinco parcelas que a feature cita estão lá, com a forma que ela descreve:

| Item | Código | Rótulo | Conta na memória |
|---|---|---|---|
| `01.5` | `AD14100200(/)` | ALAMBRADO CAMPO E QUADRA | `132,21 (semiperímetro) × 3 (altura) × 1 (ida e volta) × 25 (dist)` |
| `01.10` | `AD19050500(/)` | WC QUIMICO | `1 (qtd) × 2 (meses)` |
| `01.11` | `AD19150100(/)` | CONTAINER | `1 (qtd) × 2 (meses)` |
| `01.15` | `AD19250300(A)` | PLACA | `2,00 (comp) × 1,40 (larg)` |
| `01.30` | `AD39050218(A)` | VIGIA | `23 dias × 12 h` + `8 dias × 24 h` |

Todas cabem no motor entregue pela T1: operandos nomeados, cada um constante ou referência a
um parâmetro de obra, sem nenhuma origem geométrica.

## Refinamento da premissa: nem tudo que a feature chamou de canteiro é `STANDALONE`

A feature parte de que **24 das 43 linhas preenchidas** não têm origem nenhuma na prancha, e
trata as 24 como o alvo do acervo — que, por escopo, só contém contribuições `STANDALONE`.

A leitura da memória mostra que o grupo `23` (transporte e entulho), contado entre essas
linhas, **não é `STANDALONE`**: ele deriva de quantidades que vêm de outros serviços.

```
23.6 CARGA PARA BOTA FORA   PREPARO MANUAL 143,622 × 1,3 (empolamento) = 186,71 m³
23.7 CARGA E DESCARGA       PREPARO MANUAL 478,74 × 1,5 × 0,3 = 215,43 t
23.9 DISPOSIÇÃO FINAL       CAÇAMBA 190 × 1,5 = 285 t
23.3 TRANSPORTE HORIZONTAL  BLOCO (15X20X40) 1,6 × 2,2 × 0,15 × 3,5
```

`478,74` é a mesma área do preparo de solo (`16.21`), e `190` é a quantidade da caçamba
(`23.6`). Isso é exatamente a base `DEPENDENT` (`ContributionBasis.DEPENDENT`), e é o que
`haulage.py` já modela para o transporte — inclusive com a tabela de derivação versionada
como seed.

Consequências, e nenhuma delas invalida o que foi construído:

1. **O acervo de canteiro real é menor que 24 parcelas.** Do documento, as genuinamente
   `STANDALONE` são as cinco da tabela acima; o resto do que a feature agrupou como "canteiro"
   é derivação de quantidade da prancha ou está no grupo 23.
2. **A métrica de aceite 6 da feature** ("linhas preenchidas sem decisão humana sobe de 0/43
   para ~24/43") está superestimada na parte que atribui ao acervo. Uma parte dessas linhas
   depende de `haulage.py`/`DEPENDENT`, que é outro mecanismo — já existente, e não construído
   por esta feature.
3. **O motor não muda.** Ele faz exatamente o que precisa fazer para as parcelas `STANDALONE`,
   e a validação que proíbe `STANDALONE` com `source_item_id` continua sendo o que impede
   alguém de forçar uma parcela derivada para dentro do acervo.
4. **Fica uma pergunta de produto**, não de engenharia: se o acervo deve um dia carregar também
   as receitas `DEPENDENT` do canteiro (o transporte de container, a carga de bota-fora), ou se
   isso continua sendo domínio de `haulage.py`. As duas respostas são defensáveis, e a decisão
   é do dono.

## Achado menor: `#N/A` na memória do Campo do Toca

O bloco `23.8 TC09050350(/)` (carga e descarga mecânica) traz `#N/A` no lugar do valor —
`PREPARO MANUAL #N/A × 1,5`. É um `VLOOKUP` que não encontrou o que procurava e nunca foi
notado. A linha correspondente na planilha sai com quantidade zero.

Relacionado, mas distinto, dos dois achados registrados na
[evidência da F-043](../F-043-planilha-no-gabarito-da-prefeitura/evidence.md).

## Evidência de navegador da T6 — o estado 09 renderizado

**Data**: 2026-09-04. Chromium 1440 px, `deviceScaleFactor: 2`, sessão OIDC real no Keycloak
local (`orcamentista.local`, tenant `tenant-local`), API e web servidos **do código da T6**.
A rodada é **sintética** e foi semeada pelas funções dos próprios testes apontadas ao servidor
real — o método da [evidência da F-043](../F-043-planilha-no-gabarito-da-prefeitura/evidence.md),
seção "Método". Nenhum dado de cliente entra; nenhuma chamada paga acontece.

A rodada semeada tem **duas parcelas de canteiro gravadas**: uma vinda de acervo
(`kit_origin` preenchido) e uma autorada à mão — que é o par que a frase do estado 09 conta.

| Captura | O que ela prova |
| --- | --- |
| [`00-painel-com-o-ato-de-guardar.png`](evidencia/00-painel-com-o-ato-de-guardar.png) | O ato "Guardar como acervo" ao lado de "Aplicar um acervo", no mesmo painel de onde as parcelas são recortadas |
| [`09-autoria-real.png`](evidencia/09-autoria-real.png) | O estado 09 renderizado: os dois painéis, a contagem por origem, o aviso âmbar, a declaração por operando e o selo "novo" |
| [`10-recusa-de-nome-repetido.png`](evidencia/10-recusa-de-nome-repetido.png) | A recusa `409 SITE_SETUP_KIT_ALREADY_PUBLISHED` **de verdade**, provocada guardando a versão que já existe |
| [`12-o-acervo-novo-na-lista.png`](evidencia/12-o-acervo-novo-na-lista.png) | O acervo guardado aparecendo na lista da aplicação, com "cita 2 parâmetros de obra" — os bindings declarados chegaram ao documento |

O desfecho lido na tela, palavra por palavra:

```text
Acervo "CANTEIRO — CONTRATO SINTETICO T6E", versão 2, guardado com 2 parcelas de canteiro.
Ele já aparece na lista de acervos desta rodada. A rodada não mudou: nada foi gravado nela.
```

### O defeito que a evidência achou: a tela em branco da matriz gravada

Na primeira tentativa de captura, a jornada do orçamento **não renderizou nada** — página em
branco, sem mensagem e sem como voltar. O console dizia
`Cannot read properties of null (reading 'kit_version')`.

A causa é da T5, não da T6, e é anterior a esta captura: `disassembleCalcMatrix`
(`apps/web/src/orcamento/matrix.ts`) testava a proveniência com
`contribution.kit_origin !== undefined`, mas o servidor manda **`kit_origin: null`** para a
parcela autorada à mão — `model_dump` do Pydantic serializa o campo opcional ausente como
`null` em vez de omiti-lo. O `null` entrava no ramo e era desreferenciado.

O alcance é maior que o desta task: **qualquer rodada com uma contribuição autorada à mão na
matriz gravada derrubava a etapa de códigos ao ser aberta**. Nenhum teste pegava porque as
fixturas da suíte montam a matriz com o campo AUSENTE, que é a forma que a tela produz — não a
que ela recebe.

Corrigido nesta task, com regressão em `matrix.test.ts` ("kit_origin nulo no fio é parcela
autorada à mão, e não derruba a leitura"). É desvio consciente de escopo, registrado aqui
porque ele era o bloqueio direto da evidência que a T6 exigia.

## Human Gates

1. **Design Approval Package** — revisão 1 aprovada em 2026-08-28 (Daniel Campos); a
   implementação expôs um beco sem saída na recusa, e a **revisão 2** foi aprovada na mesma
   data. Ver [`mock/README.md`](mock/README.md).
2. ~~Aceite do ADR-0059~~ — cumprido em 2026-08-28.
3. ~~Decisão do unknown 1 (onde o acervo vive)~~ — cumprido em 2026-08-28: ADR-0060 `Accepted`.
4. **Autoria do primeiro acervo** — **cumprido com achado em 2026-09-05** (seção abaixo).
   A execução foi da bancada delegada pelo dono; o veredito foi dele, pelo chat. A autoria
   real pela orçamentista — quais parcelas entram, com que parâmetros e sob que nome —
   segue como a dívida declarada do aceite.

## Human Gate 4 — a autoria e a aplicação, contra dado real (2026-09-05)

**Cumprido com achado por ato humano em 2026-09-05** (Daniel Campos, pelo chat). A bancada
(Playwright, sessão OIDC real como `orcamentista.local`, banco próprio `croquito_f038f042`,
API em `127.0.0.1:8010`) exerceu o ciclo inteiro sobre dado real:

1. **A praça feita.** A praça-bancada do Campo do Toca nasceu pelo caminho de produção:
   catálogo SCO-Rio Out/2023 **real** (4.964 entradas) instalado por upload, takeoff com os
   elementos reais, pacotes de código decididos (o do PISO na tela, pela bancada da F-038),
   e a matriz transcrita da memória do documento — inclusive as **6 parcelas de canteiro
   `STANDALONE`** com os operandos como o arquivo os nomeia (`SEMI PERIMETRO 132,21 ×
   ALTURA 3 × IDA E VOLTA 1 × DIST 25`, as duas parcelas do VIGIA, etc.).
2. **O achado.** Ao montar o orçamento da praça feita, o serviço `STANDALONE` recusou com
   `ESTIMATE_ASSIGNMENT_CATALOG_REQUIRED`: o builder exige fonte citada por confirmação de
   código, o canteiro não tem elemento para confirmar, e o apply não grava citação. Nenhum
   teste do repositório montava orçamento com contribuição standalone — o ROI central da
   feature (24 linhas sem digitação) nunca tinha chegado a uma linha. A própria mensagem
   de erro carregava o desenho pretendido ("**com mais de uma tabela**, quem escolhe a
   fonte é o orçamentista").
3. **O reparo** (laço de revisão, [PR #178](https://github.com/biahflow/croquito/pull/178)):
   serviço sem NENHUMA confirmação de código e sem parcela de elemento precifica pela
   **fonte única** da cascata; com mais de uma tabela, a recusa continua; parcela de
   elemento nunca alcança o fallback — o portão dela fecha antes, por
   `ESTIMATE_ASSIGNMENT_MISSING` (os três casos têm teste em
   `tests/valuation/test_estimate.py`). Com o reparo, o orçamento da praça feita saiu com
   **11 linhas** — as 6 do PISO e as 5 do canteiro, todas batendo a memória real.
4. **A autoria, na tela** (estado 09): "Guardar como acervo" sobre a praça feita, modo
   acervo novo, nome "CANTEIRO PADRÃO — DO CAMPO DO TOCA", versão 1.0.0;
   `SEMI PERIMETRO` e os dois `MESES` citados como parâmetros (`semi_perimetro`,
   `prazo_meses`), todo o resto constante. O banco confirma o documento: 6 parcelas,
   `origin` tenant, `source_label` = a praça de origem.
5. **A aplicação, na tela**, numa praça nova: escolher o acervo (cartão com "6 parcelas ·
   cita 2 parâmetros de obra"), declarar `semi_perimetro = 98,50` e `prazo_meses = 3`,
   rever a prévia com a conta viva (`98,50 × 3 × 1 × 25 = 7.387,50`) e aplicar. A matriz
   da praça nova gravou as 6 parcelas com proveniência `acervo 1.0.0` e os parâmetros
   resolvidos, e a montagem produziu as 5 linhas de canteiro **sem digitação de
   quantidade**: 7.387,50 m².km · 3,00 · 3,00 · 2,80 m² · 468,00 h.

Achado menor registrado: [issue #177](https://github.com/biahflow/croquito/issues/177) —
a etapa Códigos rende o mesmo takeoff item duas vezes (warning de chave duplicada do
React); o dado gravado não é afetado.

Rastros verificáveis: banco local `croquito_f038f042` (rodadas `01a070b1…` e `01a070bf…`,
kit em `site_setup_kits`); capturas e scripts das fases em `output/f038-f042-fecho/`
(retenção local de 7 dias — as quantidades e rótulos vêm do documento real do cliente e
não são versionados).
