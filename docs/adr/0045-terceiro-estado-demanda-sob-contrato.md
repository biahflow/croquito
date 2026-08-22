# ADR-0045: Demanda sob contrato — o terceiro estado entre pré-licitação e medição

Status: Proposed  
Data: 2026-08-22  
Responsável: Product / Engineering

## Contexto

O [ADR-0027](0027-price-source-provenance-and-bid-boundary.md) (`Accepted`) fixou uma
fronteira **binária** entre dois momentos com regras de preço opostas: pré-licitação, com
cascata livre de fontes; e obra licitada, onde só `PriceOrigin.sco` vale e o guardrail
`BULLETIN_PRICE_ORIGIN_FORBIDDEN` recusa fechado.

O mapeamento da cadeia real das praças, registrado em
[Cadeia operacional](../product/CADEIA_OPERACIONAL.md), mostrou que a operação tem **três**
momentos, não dois. Quando existe contrato guarda-chuva já licitado, cada demanda — uma
praça — é orçada **depois** da licitação e **antes** da execução. Esse orçamento tem a
**forma** do orçamento-base (previsão, teto de verba vindo da Relação de Praças, planilha
orçamentária como entregável) e está sob a **regra** da obra licitada: o preço já foi
fixado pelo contrato, e só a tabela contratual vale.

Nada no produto expressa isso. `estimate_rounds.ensure_source_installable` só recusa origem
duplicada; a rodada não tem como declarar que corre sob contrato. A falha que isso permite
é silenciosa e cara: instala-se EMOP ou SINAPI na cascata da demanda contratada, confirma-se
o código, o orçamento monta e é aprovado, a empresa executa — e só na medição o guardrail
recusa, sobre serviço já feito, quando a única saída é aditivo. **O defeito nasce no
orçamento e só se manifesta no pagamento.**

A [F-033](../features/F-033-demanda-sob-contrato-licitado/feature.md) está `BLOCKED`
esperando esta decisão. As perguntas que o contrato dela marca como "decisão do ADR, não do
plano": o que fazer com rodada que já tem fonte proibida instalada; como o regime se chama;
e se o orçamento pode dizer algo sobre item que não tem código no contrato.

## Decisão

1. **O terceiro estado existe e se chama "demanda sob contrato".** O ADR-0027 **não é
   substituído**: ele continua `Accepted` e correto nos dois estados que descreve. Este ADR
   acrescenta o do meio. Na tela, o selo é "Sob contrato licitado".

2. **O regime é dado da RODADA, não do artefato.** Declarado na abertura da rodada de
   orçamento ou editado depois, sempre por ato humano com `base_version` +
   `Idempotency-Key` — o mesmo desenho do teto no [ADR-0040](0040-teto-de-verba-do-orcamento-base.md).
   O artefato `Estimate` não muda: sem campo novo, sem bump de versão de schema. Ausência do
   regime **não é um valor**, é a falta dele, e significa o comportamento de hoje
   (pré-licitação, cascata livre).

3. **Sob o regime, a cascata só aceita `sco`, e a recusa é na INSTALAÇÃO.** Instalar
   catálogo com origem diferente recusa em `ensure_source_installable`, com código estável,
   no momento em que ainda há o que corrigir — exatamente onde
   `ESTIMATE_CASCADE_ORIGIN_DUPLICATE` já recusa. Recusar na montagem seria repetir o
   defeito que a feature existe para eliminar: descobrir tarde.

4. **Declarar o regime com cascata suja recusa; não limpa nem tolera.** Rodada que já tem
   fonte não-`sco` instalada recusa a declaração, com código estável próprio, até a fonte
   ser removida pelo caminho que já existe. As duas alternativas foram descartadas: aceitar
   e barrar só instalações futuras deixaria existir rodada "sob contrato" com EMOP dentro —
   precisamente o estado que a feature quer tornar impossível; e aceitar marcando as
   decisões afetadas criaria um estado intermediário novo (decisão suja) com tela, teste e
   semântica próprios, alargando a fatia sem resolver nada que a remoção não resolva.

5. **Item sem código no contrato é sinalizado como candidato a aditivo — e o sinal vem do
   julgamento humano, não de uma conferência que o sistema não pode fazer.** A rodada de
   orçamento **não conhece contrato**, e isso é deliberado: o módulo declara que "o que este
   contexto NÃO tem, de propósito: contrato, saldo, período e aprovação". Portanto o sinal
   **não pode** alegar que conferiu o item contra o contrato. Ele se deriva do que já
   existe e é honesto: item confirmado no takeoff cuja **confirmação de código foi
   rejeitada** pela orçamentista. É a mesma regra do dossiê de aditivo da medição, cujo
   construtor `build_amendment_dossier(packet, assignments)` não recebe catálogo nem
   contrato e tem `contract_sha256` opcional — reusável na cadeia do orçamento sem inventar
   entidade nova. O que o produto afirma é "a orçamentista não achou código na tabela
   contratual", nunca "este item não existe no contrato".

6. **Restringir a origem não é conferir o contrato, e o produto diz isso.** O regime garante
   que o preço veio do SCO; **não** garante que veio da tabela, data-base e desconto
   **daquele** contrato. `PriceOrigin.sco` é monolítico e o orçamento não modela `Contract`
   como entidade. Essa lacuna fica nomeada aqui e no documento da cadeia operacional, e
   fechá-la é feature própria — não se resolve com um selo.

7. **A medição não muda.** `BULLETIN_PRICE_ORIGIN_FORBIDDEN` continua sendo a última linha
   de defesa, não a primeira. Este ADR adianta a recusa; não a substitui.

## Consequências

- Uma classe inteira de defeito silencioso deixa de ser possível: sob o regime, o preço
  fora da tabela contratual não chega a entrar no orçamento.
- A distância entre o erro e a sua descoberta cai de meses (execução → medição) para
  segundos (instalação da fonte).
- O produto passa a ter três regimes de preço, o que exige que a jornada diga em qual a
  rodada está — daí a feature ser `INTERFACE_CHANGE` e depender de Design Approval Package.
- O sinal de candidato a aditivo antecipa para o orçamento uma informação que hoje só
  aparece na medição, sem prometer precisão que o sistema não tem.
- Fica dívida nomeada: o vínculo entre catálogo instalado e contrato específico.

## Alternativas consideradas

- **Não fazer nada e confiar na disciplina** (instalar só o catálogo `sco`, como a cadeia
  operacional recomenda hoje). Descartada: é a mitigação atual, e depende de a pessoa
  lembrar, exatamente no ponto em que o erro não dá sinal.
- **Emendar o ADR-0027 em vez de escrever um ADR novo.** Descartada: o ADR-0027 está
  correto no que decidiu; reescrevê-lo apagaria o registro de que a fronteira binária foi
  uma decisão consciente que a operação depois mostrou incompleta.
- **Modelar `Contract` como entidade do orçamento agora**, amarrando a rodada ao contrato
  real. Descartada para esta fatia: é o que fecharia a lacuna do item 6, mas exige trazer
  contrato, saldo e RE-RA para um contexto que os excluiu de propósito. Feature própria.
- **Deduzir o regime automaticamente** (por exemplo, presumir contrato quando só há
  catálogo `sco`). Descartada: presunção silenciosa produz o mesmo tipo de erro tardio que
  a feature combate, e o regime é uma afirmação sobre o mundo que só a orçamentista pode
  fazer.
