# ADR-0034: Camada global da Engineering OS vendorizada e pinada no repositório

Status: Proposed
Data: 2026-08-18
Responsável: Engineering

## Contexto

A Engineering OS é a camada global que define princípios, guardrails, Definition of Done,
contratos de Planner/Builder/Reviewer e os workflows de feature e execução deste e de outros
projetos. Ela mora num repositório git **local do operador**: sem remote, sem tags, sem
release. O que instala essa camada nas ferramentas é um script de adapters que renderiza
bootstraps com **caminhos absolutos da máquina dele**.

O efeito é que a camada global só existe onde o bootstrap pessoal está instalado. O CI não a
alcança; um colaborador novo que clona o croquito não a alcança; um agente rodando em nuvem
não a alcança. Isso contradiz um requisito da própria camada global — o de que todo artefato
necessário para executar ou revisar uma tarefa seja acessível a partir do ambiente de execução
do agente responsável. Uma regra que só um executor enxerga não é uma regra do repositório: é
contexto privado de uma sessão.

O sintoma já estava visível na documentação. `AGENTS.md`, `PROJECT_CONTEXT.md`,
`DEFINITION_OF_DONE.md` e `docs/features/README.md` citavam "o Definition of Done global", "os
contratos globais" e "o template global da Engineering OS" em texto corrido, sem link — as
únicas referências do repositório que o `scripts/check_docs.py` não podia verificar, porque não
apontavam para lugar nenhum. Documentação que remete a um documento inalcançável é texto morto:
ninguém percebe quando ela passa a descrever algo que mudou do outro lado.

## Decisão

**D1. Um espelho completo da camada global vive em `docs/engineering-os/`.** Cópia fiel, em
inglês, sem tradução e sem edição manual. As referências do repositório passam a apontar para
esses arquivos, e o `check_docs.py` valida esses links como valida qualquer outro.

**D2. O espelho é pinado por commit e o pino é declarado.**
`docs/engineering-os/PROVENANCE.md` registra o commit de origem, o estado da árvore
(`clean`/`dirty`), a data da sincronização, o caminho de origem e a contagem de arquivos.
Enquanto não houver nova sincronização, aquele commit **é** a versão da camada global que vale
para este repositório. O checkout vivo do operador continua evoluindo à parte; divergir dele
deixa de ser invisível e passa a ser um fato datado.

**D3. Ressincronizar é ato deliberado, nunca automático.**
`scripts/sync_engineering_os.py` (stdlib, sem dependência nova) espelha a lista de arquivos
rastreados da origem, remove do destino o que saiu de lá, preserva o modo dos arquivos e
reescreve o `PROVENANCE.md`. Ele **recusa origem com árvore suja**, salvo `--allow-dirty`, que
carimba `dirty` no registro — snapshot de trabalho não commitado é snapshot que ninguém
consegue reproduzir. Não há job de CI que sincronize sozinho: a atualização chega por PR, e o
diff é revisado como qualquer outra mudança.

**D4. O espelho fica fora do `ruff format`, dentro do `check_docs.py`.** Fidelidade à origem
vence estilo local, então `docs/engineering-os` entra em `extend-exclude` do ruff. Os links
internos continuam validados: um espelho incompleto quebraria o portão de documentação, que é
exatamente o sinal desejado.

**D5. O `.gitignore` da origem não é copiado.** Um `.gitignore` aninhado mudaria a semântica de
ignore do croquito dentro do diretório vendorizado. O espelho é documentação, não um checkout
funcional.

## Alternativas

- **Publicar o engineeringOS num remote e consumir por submodule ou URL.** É o caminho certo
  quando a publicação existir. Hoje não existe: exigiria publicar o repositório e acoplaria o
  CI a rede e credencial para ler regras que precisam estar disponíveis mesmo offline.
  Vendorizar não fecha essa porta — trocar a fonte do sync por um remote é mudança pequena.
- **Referenciar o caminho absoluto da máquina do operador.** Funciona para exatamente um
  executor e quebra para todos os outros, que é o problema que este ADR resolve.
- **Manter o status quo, com as referências em texto corrido.** Mantém a camada global
  invisível fora da máquina do operador e mantém as únicas referências não verificáveis do
  repositório.
- **Copiar só os trechos citados** (Definition of Done, contratos de agente). Reduz o volume,
  mas quebra os links internos entre os documentos globais e cria uma terceira versão parcial
  da camada — pior de manter do que o espelho inteiro.

## Consequências

### Positivas

- CI, colaborador novo e agente em nuvem passam a enxergar a mesma camada global que o
  operador, a partir do próprio checkout.
- O drift entre origem e cópia vira informação: o `PROVENANCE.md` diz de qual commit veio o que
  está valendo, e a atualização chega por diff revisável.
- As referências à camada global viram links verificados pelo `check_docs.py`; quebrar um deles
  passa a reprovar o portão.

### Negativas

- Cerca de 136 KB de documentação em inglês entram no repositório e aparecem nas buscas — o
  espelho não é fonte de decisão do produto e não deve ser editado aqui.
- O espelho envelhece silenciosamente entre sincronizações: quem mudar a camada global precisa
  lembrar de trazê-la, e o repositório não avisa sozinho.

## Riscos e mitigação

| Risco | Mitigação |
|---|---|
| O espelho fica defasado da origem sem ninguém perceber | `PROVENANCE.md` carrega commit e data; a ressincronização é um comando único e idempotente |
| Alguém edita o espelho à mão e a edição some na próxima sincronização | O `PROVENANCE.md` declara que o diretório não é editado aqui; o sync sobrescreve o arquivo divergente e o diff mostra a perda |
| Snapshot tirado de árvore suja, irreprodutível | O script recusa origem suja por padrão e carimba `dirty` quando `--allow-dirty` é usado |
| A camada global e as regras do projeto divergirem | Precedência já declarada: guardrails globais não são enfraquecidos por regra local; conflito é decisão humana |

## Rastreabilidade

- Requirements: none
- Supersedes: none
- Superseded by: none
