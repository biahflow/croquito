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

## Human Gates

1. **Design Approval Package** — revisão 1 aprovada em 2026-08-28 (Daniel Campos); a
   implementação expôs um beco sem saída na recusa, e a **revisão 2** aguarda aprovação. Ver
   [`mock/README.md`](mock/README.md).
2. ~~Aceite do ADR-0059~~ — cumprido em 2026-08-28.
3. ~~Decisão do unknown 1 (onde o acervo vive)~~ — cumprido em 2026-08-28: ADR-0060 `Accepted`.
4. **Autoria do primeiro acervo** — **pendente**. É ato da orçamentista. As cinco parcelas
   acima são o rascunho que o documento real sustenta; quais entram, com que parâmetros e sob
   que nome, é decisão dela.
