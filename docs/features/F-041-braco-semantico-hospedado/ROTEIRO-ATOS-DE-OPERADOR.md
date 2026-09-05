# F-041 — Roteiro dos atos de operador

Feature: [O braço semântico roda no caminho hospedado](feature.md) · Preparado em 2026-09-05

As duas dívidas declaradas no aceite são atos seus, não código: **publicar o índice real**
e **exercer o primeiro recompute pago**. Este roteiro é o passo a passo, com o custo e o
que pode dar errado.

## Antes: o índice real precisa ser reconstruído

O índice de 40,7 MB construído em 2026-08-25 (por US$ 0,03) **não existe mais**: ele foi
escrito em `output/`, que tem retenção local de sete dias, e a conferência de 2026-09-05
não o encontrou em lugar nenhum do disco. Isso não é perda de trabalho — é exatamente o
motivo pelo qual a feature existe: enquanto o índice for arquivo no disco de uma pessoa,
ele se perde. Depois de publicado, ele é artefato da plataforma.

Reconstruir custa outra chamada paga, na mesma ordem de grandeza (~US$ 0,03 pelos 4.964
itens do catálogo).

## O roteiro

### 1 · Reconstruir o índice (comando pago, ~US$ 0,03)

```bash
uv run croquito-valuation index-catalog \
  --catalog output/toca-2023-10/catalog.json \
  --output-dir output/f041-indice-real
```

Precisa de `CROQUITO_REAL_PROVIDERS_ENABLED=true` e a chave do provedor de embeddings no
ambiente. O comando escreve `catalog-embeddings.json`; **guarde-o fora de `output/`** se
quiser evitar a retenção de sete dias antes de publicar.

### 2 · Publicar a tabela no acervo (se ainda não estiver lá)

Na jornada **Plataforma** (`?plataforma=`, papel `platform_operator`), seção "Acervo de
tabelas de referência": subir o `catalog.json`, dar o nome de exibição e publicar. Origem,
data-base e contagem vêm de dentro do arquivo — não se digita.

### 3 · Publicar o índice

Mesma jornada, seção "Índices de embeddings": subir o `catalog-embeddings.json`, escolher a
tabela indexada e publicar. O servidor confere o digest de dentro do arquivo contra a
tabela e recusa se não bater — não há como publicar índice de outro catálogo por engano.

> Conferido em 2026-09-05 com um índice *fixture* no mesmo contrato: a publicação apareceu
> como "em circulação · 4.964 códigos", e a tela recusou publicar índice antes de a tabela
> existir no acervo.

### 4 · O primeiro recompute pago

Numa rodada de orçamento com aquela tabela na cascata, etapa **Códigos** → "Recalcular com
a cascata atual". Este é o ato que pode custar: o braço semântico embute os rótulos da
rodada (centésimos de centavo por rodada) e exige entitlement contratual ativo no tenant.

O que conferir depois: a nota deixa de dizer "shortlist é léxica" e passa a declarar as
fontes que entraram com o braço; e a shortlist do caso de vocabulário — `"REFLETOR
EXISTENTE"` → `IP49150409(/)` — passa a trazer o código certo, que é o vão medido de 9/12
para 12/12 no golden.

## O que pode dar errado, e o que significa

| O que aparece | O que é |
| --- | --- |
| "busca semântica indisponível: providers reais desligados neste ambiente" | O ambiente está com `CROQUITO_REAL_PROVIDERS_ENABLED=false`. É o estado normal fora de rodada paga |
| "sem índice de embeddings publicado" citando uma fonte | Aquela tabela da cascata não tem índice — estado normal e declarado, não erro. Só ela entra léxica |
| Recusa na publicação por digest | O índice foi construído sobre outro catálogo (ou outra versão dele). Reconstrua sobre a tabela publicada |
| Recusa por tamanho | O teto é 64 MiB, e o índice real tem ~41 MB. Se estourar, algo mudou na receita — não afrouxe o teto sem entender |

## O que este roteiro não faz

Nada disso roda em homologação: o ambiente está derrubado por decisão de custo. Tudo aqui
é local, e a publicação do índice em HML é ato posterior, quando o ambiente voltar.
