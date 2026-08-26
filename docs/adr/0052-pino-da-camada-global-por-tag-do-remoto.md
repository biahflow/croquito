# ADR-0052: Pino da camada global por tag do remoto, não por caminho de máquina

Status: Accepted
Data: 2026-08-26
Responsável: Engineering

## Contexto

A [ADR-0034](0034-camada-global-vendorizada-e-pinada.md) vendorizou a camada global da
Engineering OS em `docs/engineering-os/` e pinou o espelho pelo commit de origem. A origem,
naquele momento, era um checkout git **local do operador**: sem remote, sem tags, sem release.
O script de sincronização lia um caminho absoluto — `~/workspace/engineeringOS` — e recusava
origem com árvore suja.

Aquele ADR listou como alternativa "publicar o engineeringOS num remote e consumir por
submodule ou URL", e a descartou com uma condição explícita: *"é o caminho certo quando a
publicação existir. Hoje não existe."*

Passou a existir. A Engineering OS é publicada em `https://github.com/biahflow/engineeringOS`,
tem CI que valida links, artefatos rastreados, caminhos de máquina, YAML e o módulo Go, e
versiona releases por tag SemVer com um workflow que recusa tag fora de SemVer e tag cujo
commit não é alcançável a partir de `main`.

A condição não só foi satisfeita — a alternativa descartada cobrou seu preço primeiro. O
checkout do operador mudou de `~/workspace/engineeringOS` para `~/workspace/daniel/engineeringOS`.
O `DEFAULT_SOURCE` do script apontava para o caminho antigo e morreu em silêncio; os bootstrap
renderizados nas ferramentas apontavam para o mesmo caminho e passaram a importar treze
arquivos inexistentes, sem erro visível — durante esse período, nenhuma sessão carregou os
guardrails globais. O mesmo caminho morto estava versionado no repositório `one`, num arquivo
que declarava onde a camada global vivia.

O pino por commit também nunca foi verificável: `PROVENANCE.md` declarava um SHA que só
existia na máquina de uma pessoa. Ninguém mais conseguia conferir de onde o espelho veio, nem
ressincronizá-lo.

## Decisão

**D1. A origem é o remote publicado, não um caminho de máquina.**
`scripts/sync_engineering_os.py` clona `https://github.com/biahflow/engineeringOS.git`. A
variável `CROQUITO_EOS_ORIGIN` continua existindo como escape para fork ou espelho interno; ela
não é o caminho normal.

**D2. O pino é uma tag SemVer, declarada no script.**
`PINNED_TAG` é uma constante versionada. Avançar o pino é um diff de uma linha, revisado como
qualquer outra mudança. O `PROVENANCE.md` registra a tag **e** o commit para o qual ela
resolve, de modo que o pino continue conferível mesmo se alguém quebrar a promessa de
imutabilidade da tag.

**D3. O script recusa qualquer referência que não seja tag publicada.**
Isso substitui a guarda de árvore suja da ADR-0034, e pelo mesmo princípio: aquela recusava
snapshot que ninguém consegue reproduzir. Uma branch se move; um pino que se move não é pino.
Passar `--tag main` falha com mensagem explícita.

**D4. O espelho continua vendorizado.**
A sincronização passa a exigir rede; o espelho, não. CI, colaborador novo e agente em nuvem
continuam lendo as regras do próprio checkout, sem rede e sem credencial — que é a razão pela
qual a ADR-0034 recusou submodule, e essa razão não mudou.

Permanecem valendo, sem alteração, as decisões D1, D4 e D5 da ADR-0034: espelho completo e
fiel, fora do `ruff format` e dentro do `check_docs.py`, e `.gitignore` da origem não copiado.

## Alternativas

- **Manter o caminho local, só corrigido.** Foi o primeiro remendo aplicado e é o que já
  falhou uma vez. Funciona até o diretório mudar de novo, e continua deixando o pino
  inconferível para todos menos uma pessoa.
- **Submodule ou dependência apontando para a tag, sem espelho.** Acopla o CI a rede e
  credencial para ler regras que precisam estar disponíveis mesmo offline. Recusado pela
  ADR-0034 pelo mesmo motivo, que continua de pé.
- **Pinar por commit do remote em vez de tag.** Resolve a alcançabilidade mas não a
  legibilidade: um SHA não diz se a mudança do outro lado foi correção de typo ou guardrail
  novo. A tag SemVer carrega essa informação, e o `VERSIONING.md` da origem define o que cada
  número significa em termos de conformidade.
- **Sincronizar automaticamente na tag mais recente.** Transformaria a camada global em
  dependência que se move sozinha, exatamente o que o pino existe para impedir.

## Consequências

### Positivas

- O pino é conferível por qualquer pessoa: a tag existe publicamente e resolve para um commit
  que passou pelos portões da origem.
- Mudar o diretório do checkout do operador deixa de quebrar a sincronização.
- A defasagem passa a ser legível: `v0.1.0` diz mais que um SHA, e o `VERSIONING.md` da origem
  define quando uma mudança pode tornar um projeto conforme em não conforme.
- Ressincronizar deixa de ser privilégio de uma máquina.

### Negativas

- Ressincronizar passa a exigir rede e acesso ao repositório de origem. É ato deliberado e
  raro; o uso diário do espelho continua offline.
- A origem precisa manter disciplina de release: sem tag nova, não há como avançar o pino.

## Riscos e mitigação

| Risco | Mitigação |
|---|---|
| Tag repontada na origem muda as regras sob um pino existente | `PROVENANCE.md` registra o commit além da tag; um repontamento aparece como divergência conferível |
| Espelho envelhece sem ninguém perceber | Inalterado pela ADR-0034: `PROVENANCE.md` carrega tag e data, e a defasagem é fato datado |
| Origem indisponível no momento da ressincronização | O espelho vigente continua válido; a sincronização é adiável por definição |
| Alguém aponta `CROQUITO_EOS_ORIGIN` para um checkout local sujo | O clone é feito por tag; uma tag local ainda é um ponto fixo, e o `PROVENANCE` declara a origem usada |

## Rastreabilidade

- Requirements: none
- Supersedes: [ADR-0034](0034-camada-global-vendorizada-e-pinada.md), decisões D2 e D3
- Superseded by: none
