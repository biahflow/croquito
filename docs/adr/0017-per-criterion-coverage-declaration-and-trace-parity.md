# ADR-0017: Declaração por critério (coberto × pendente) e paridade do traçado

Status: Accepted  
Data: 2026-08-12  
Responsável: Product / Engineering

## Contexto

O [ADR-0014](0014-scope-criteria-acknowledgement-at-approval.md) criou o critério de
escopo declarado no caso: um código em `required_blocker_codes` da revisão de leitura que
vira `Issue(severity=CRITICAL)` na cena e só sai do caminho por reconhecimento nominal do
profissional que assina. Três defeitos apareceram quando esse contrato encontrou o
estágio de traçado e a folha real.

1. **A issue nasce só num dos dois motores.** O fluxo retangular materializa o critério ao
   gravar a cena do solver; o estágio de traçado
   ([ADR-0015](0015-trace-solve-worker-and-registry.md)) não materializa nada. Uma cena
   traçada nasce sem a issue, e o portão de exportação — que é `export_errors()`, e só ele
   — nunca vê o critério. O caso declarado como não coberto exporta em silêncio. Isso é
   buraco de implementação, não decisão registrada.
2. **O texto do critério não viaja.** `ACC-GUA-001` significa "Perímetro, linha central,
   círculo, áreas e gols são entidades CAD limpas"
   ([Acceptance Criteria](../product/ACCEPTANCE_CRITERIA.md)), mas só o código é
   persistido. A mensagem da issue é uma frase genérica fixa e a tela mostra o código cru.
   O próprio ADR-0014 previa o oposto na sua tabela de riscos: "critérios listados em
   texto na tela de aprovação".
3. **Só existe um ato de declaração.** Reconhecer é dizer "sei que está pendente e assino
   assim mesmo". Não há como dizer o contrário — "este critério está coberto pela cena que
   estou aprovando" —, que é o desfecho normal depois que o traçado cobre o que faltava.
   Os dois viram `ACCEPTED` e o pacote entregue não distingue um do outro.

## Decisão

O critério de escopo passa a ter **texto**, é materializado pelos **dois** motores de
geometria e é declarado na aprovação por **dois atos distintos**.

- **Paridade.** `solve_trace` recebe os critérios exigidos da revisão de leitura corrente
  e anexa uma issue crítica por critério sempre que constrói uma cena. Qualquer caminho
  novo até o DXF materializa o critério ou não cria cena; o portão continua sendo
  `export_errors()`.
- **Dois atos.** Na aprovação, `covered_criteria` declara que a cena cobre o critério e
  leva a issue a `IssueStatus.RESOLVED`; `acknowledged_criteria` mantém a semântica do
  ADR-0014 e leva a `IssueStatus.ACCEPTED`. Os dois conjuntos são disjuntos
  (`422 CRITERION_DECLARATION_CONFLICT`) e ambos entram no `aprovacao.json` do pacote, em
  campos separados. Critério exigido que não recebe nenhuma das duas declarações
  permanece `OPEN` e bloqueia a exportação, como hoje.
- **Texto.** A semeadura da evidência aceita `CODE=Texto do critério` e grava o texto numa
  coluna aditiva `required_criteria_texts_json`. O texto vira a `message` da issue crítica
  e viaja na resposta de revisão como `{code, text}`. Linha antiga sem a coluna cai numa
  frase padrão; nenhuma migração retroativa é feita.

A fronteira dura do ADR-0014 é **mantida sem exceção**: só é declarável — coberto ou
pendente — um código presente em `required_blocker_codes` da revisão corrente. Blocker de
geometria (resíduo do solver, `MEASUREMENT_MISMATCH`, `APPROXIMATION_NOT_ACCEPTED`,
`UNRESOLVED_ENTITY`, `CALIBRATION_SUPERSEDED`, `EXACT_WITHOUT_PROVENANCE`) nunca é
declarável por nenhum dos dois atos. As três verificações explícitas e a declaração
escrita de 20 a 500 caracteres continuam obrigatórias.

## Alternativas

- **Criar `IssueStatus.COVERED`.** Rejeitada: `RESOLVED` já existe no contrato canônico com
  exatamente esse significado — a pendência deixou de existir —, e um valor novo de enum
  quebraria o schema gerado, os tipos TypeScript e todo consumidor do scene graph para
  descrever algo que o vocabulário já descreve.
- **Enriquecer `required_blocker_codes_json` com objetos `{code, text}`.** Rejeitada: a
  coluna é lida em três lugares (API, worker de traçado, resposta de revisão) e passaria a
  ter formato misto por tempo indeterminado, obrigando cada leitor a tolerar as duas
  formas. Uma coluna aditiva paralela mantém cada leitura com um tipo só.
- **Materializar a issue do critério no portão de exportação.** Rejeitada: transformaria
  `export_errors()` em consultor de banco e esconderia o critério do revisor até o último
  passo. A issue existe para ser vista na cena, não para aparecer no fim.
- **Um único ato com um campo booleano "coberto".** Rejeitada: um mesmo campo com dois
  significados dependendo de outro campo é justamente o que produziu a confusão atual;
  dois conjuntos nomeados são auditáveis no pacote entregue sem interpretação.
- **Migrar as linhas existentes para preencher o texto.** Rejeitada neste marco: o
  repositório não tem runner de migração, e o texto correto de um caso antigo é
  conhecimento humano que ninguém pode fabricar em script. O fallback é honesto.

## Consequências

### Positivas

- Uma cena traçada com critério declarado não exporta sem declaração humana; o buraco de
  paridade fecha e passa a ter teste nos dois motores.
- O pacote entregue distingue o que a cena cobre do que ela deixa pendente, com o texto do
  critério e não só o código.
- A construção da issue de critério fica num helper único usado pelos dois motores e pela
  aprovação; um motor novo que a esqueça é uma omissão visível, não um caminho paralelo.

### Negativas

- Aprovações antigas ficam sem `covered_criteria`; ler o histórico exige saber que o campo
  nasceu aqui.
- A coluna nova é criada pelo `create_schema` aditivo, e o repositório continua sem runner
  de migração — dívida registrada no ADR-0015 e não resolvida aqui.
- Declarar "coberto" é uma afirmação técnica mais forte que reconhecer uma pendência, e o
  produto passa a depender de ela ser honesta; o controle é a mesma assinatura nominal.

## Riscos e mitigação

| Risco | Mitigação |
|---|---|
| `covered` usado para contornar defeito geométrico | Só códigos de `required_blocker_codes` são declaráveis; blocker de solver e de medida nunca |
| Critério declarado coberto e pendente ao mesmo tempo | Conjuntos disjuntos validados no modelo e no request path (`CRITERION_DECLARATION_CONFLICT`) |
| Motor novo esquecer de materializar o critério | Construção centralizada em `criteria.scope_criteria_issues`, com teste por motor |
| Texto do critério vazando em log | O texto é conteúdo de domínio: só código, id e status entram em log |
| Linha de revisão antiga sem a coluna de textos | Todo leitor trata ausência como frase padrão; nenhuma leitura exige a coluna |

## Rastreabilidade

- Requirements: ACC-007, ACC-GUA-001, ACC-GUA-002
- Supersedes: ADR-0014 (parcial — o ato único de reconhecimento)
- Superseded by: none
