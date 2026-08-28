# F-044 T1 — Medir a repetição de rótulo entre praças

- **feature_id**: F-044
- **task_id**: T1
- **role**: builder
- **depends_on**: []
- **required_capabilities**: READ, WRITE (`packages/valuation`, `services/worker/.../valuation`, `tests/`), VALIDATE
- **risk**: BAIXO — ferramenta nova, offline, nada em caminho de request.
- **relative_effort**: M

## Por que esta task existe, e o que ela NÃO faz

O primeiro Human Gate da F-044 é **medir a hipótese de repetição** e decidir se a feature
continua: *"Se a repetição for baixa, a feature perde a razão de existir e deve ser cancelada
em vez de construída"* (feature.md, unknown 1). Uma medição anterior foi **retirada** por
medir a coisa errada (sobreposição entre os três lotes do contrato, não entre praças).

Esta task entrega **só o instrumento de medição** e as fixtures que o provam. Ela **não**
constrói o índice de precedentes, **não** mexe na shortlist e **não** toca a tela. Isso vem
depois, e só se o número justificar.

## Goal

Um comando determinístico e offline que, dado o que já está gravado das rodadas de orçamento
de duas ou mais praças, responde com números:

1. quantos rótulos de legenda reaparecem entre praças, sob cada estratégia de normalização;
2. quando reaparecem, o **pacote de códigos** confirmado é o mesmo?

## Scope

### 1. Módulo de medição

`packages/valuation/src/croquito_valuation/precedent.py` (domínio puro, sem I/O de rede):

- `LabelKey` — a chave do precedente: **(rótulo normalizado, fonte de preço)**, nunca o
  rótulo sozinho. É a decisão 4 do escopo da feature, e é barato acertar agora.
  A fonte de preço vem de `CodeAssignment.catalog_sha256` resolvido contra o catálogo, ou de
  `CodeCandidate.catalog_origin` (`PriceOrigin`, `models.py:98-117`) — escolha o caminho que
  o dado gravado sustenta e **escreva na docstring qual foi e por quê**.
- Estratégias de normalização, todas **reusando** o que já existe em `catalog.py`, sem
  reimplementar:
  - `exact` — texto como gravado;
  - `casefold` — `" ".join(text.split()).casefold()` (molde de `bulletin_compare._normalize_label:151`);
  - `folded` — `catalog._lexical_normalize` (`:467-470`, casefold + NFKD sem acento);
  - `tokens` — `catalog.lexical_tokens` (`:473-484`) reunidos em ordem;
  - `stems` — `catalog.lexical_stems` (`:521`).
- `WorksitePrecedents` — o que uma praça contribui: `worksite_key`, e por `LabelKey` o
  conjunto de códigos **confirmados** (`CodeAssignment.status == "confirmed"`, `code` não
  nulo). Rejeitados não entram.
- `measure_repetition(worksites: Sequence[WorksitePrecedents]) -> RepetitionReport`, puro,
  com, por estratégia de normalização:
  - nº de praças, nº de rótulos por praça, nº de rótulos distintos no total;
  - **rótulos que aparecem em ≥2 praças** (contagem e lista);
  - taxa de repetição = rótulos repetidos ÷ rótulos distintos;
  - para cada rótulo repetido, a classificação do pacote entre praças:
    `identical` (mesmo conjunto de códigos), `subset` (um contido no outro),
    `overlapping` (interseção não vazia, nenhum contido), `disjoint` (interseção vazia);
  - taxa de estabilidade = rótulos repetidos com pacote `identical` ÷ rótulos repetidos.
- Nada de heurística de decisão: a função **mede**, não recomenda limiar. O limiar do
  unknown 3 é decisão humana posterior.

### 2. Leitura do que já está gravado

`services/worker/src/croquito_worker/valuation/precedent_eval.py` + subcomando
`precedent-eval` no CLI `croquito-valuation`:

- Entrada A (`--rounds <estimate_rounds.csv> --revisions <estimate_round_revisions.csv>`):
  o export das tabelas, no formato exato de `output/backup-rodadas-2026-08-26/*.csv` —
  há uma amostra real ali para você conferir as colunas. `worksite_key`/`worksite_name` vêm
  de `estimate_rounds`; `takeoff_packet_json` e `code_assignments_json` vêm da revisão. Use
  **a revisão de maior `version`** por rodada que tenha `code_assignments_json` não vazio, e
  **declare essa escolha no relatório**.
- Entrada B (`--revision-dir <dir>`): um JSON por praça, com `worksite_key`,
  `takeoff_packet` e `code_assignments` — para o caso de o dado chegar fora do banco.
- O rótulo vem de `TakeoffItem.label` (`takeoff.py:96`); o par vem de
  `CodeAssignmentSet.assignments` (`assignment.py:1036-1073`, `item_id` + `code`), que é
  N:N desde a F-038 — um `item_id` com vários códigos é o caso normal, não anomalia.
- Rodada sem `code_assignments_json`, ou com pacote de takeoff ausente, é **pulada com aviso
  nomeado no relatório**, nunca em silêncio.
- **Menos de duas praças na entrada → recusa** `PRECEDENT_NOT_ENOUGH_WORKSITES`, dizendo
  quantas foram encontradas. Medir repetição com uma praça é o erro que já aconteceu uma vez.

### 3. Relatório

- Grava em `--output <dir>`: um `precedent-repetition.json` (o `RepetitionReport` completo,
  determinístico e ordenado) e um resumo legível em texto no stdout.
- O JSON **contém rótulo de legenda, que é texto de cliente**: a saída vai para `output/`,
  que é ignorado pelo Git e tem retenção local de 7 dias. Não versione nenhum relatório real
  e não escreva rótulo em log — o resumo do stdout pode mostrar rótulos, o **log
  estruturado** não (`CLAUDE.md`, seção de logs).
- Zero chamada paga, zero rede.

### 4. Testes

`tests/valuation/test_precedent.py` e um teste do leitor. Fixtures **sintéticas** com **duas
praças**, cobrindo de propósito os quatro casos que a medição precisa distinguir:

- rótulo idêntico entre praças com pacote de códigos idêntico;
- rótulo que só reaparece após normalização (ex.: acento/caixa/espaço diferentes);
- rótulo igual com pacotes diferentes (`overlapping`/`disjoint`) — o caso que derruba a
  hipótese;
- mesmo rótulo em **fontes de preço diferentes**, que **não** pode ser contado como
  repetição (é a decisão 4 do escopo).

Cubra também: entrada com uma praça só recusada; revisão sem assignments pulada com aviso;
determinismo (mesma entrada, mesmo JSON byte a byte).

## Out of Scope

- **O índice de precedentes**, a mudança na shortlist e o aceite de pacote em um clique. Só
  nascem depois que o número existir e o gate humano decidir.
- `apps/web`, `services/api`, migrações, `suggestions.py`, `assignment.py`.
- Recomendar limiar ou julgar se a hipótese está provada.

## Acceptance Criteria

1. Rodando sobre duas praças sintéticas, o relatório dá as taxas de repetição e estabilidade
   por estratégia de normalização, e classifica cada rótulo repetido.
2. Mesmo rótulo em fontes de preço diferentes **não** conta como repetição.
3. Entrada com menos de duas praças é recusada por nome.
4. Determinístico: mesma entrada, mesmo JSON.
5. Nenhuma chamada paga, nenhuma rede, nada gravado fora de `--output`.
6. O comando roda contra `output/backup-rodadas-2026-08-26/*.csv` sem estourar exceção — ali
   há **uma** praça real com assignments, então o resultado esperado é a **recusa** do
   critério 3. Registre essa execução no BUILD REPORT: é a prova de que o leitor entende o
   formato real.

## Validation

```bash
cd /Users/danielcampos/workspace/daniel/croquito-f044
uv run pytest tests/valuation/test_precedent.py -q
make check
make test
uv run croquito-valuation precedent-eval \
  --rounds output/backup-rodadas-2026-08-26/estimate_rounds.csv \
  --revisions output/backup-rodadas-2026-08-26/estimate_round_revisions.csv \
  --output output/precedent-eval
```

## Armadilhas verificadas

- `PriceOrigin` (`models.py:98-117`) tem hoje `sco`, `emop`, `composition`, `sinapi`, `sicro`
  — **não** tem `contract`. O ADR-0059 foi aceito mas o valor ainda não existe no enum.
  **Não crie** o valor nesta task; trate a fonte como o dado gravado a expõe.
- A cardinalidade `(item_id, code)` é N:N e vive no contrato Pydantic
  (`CodeAssignmentSet.schema_version == "2.0.0"`), não em coluna de banco.
- A fixture multi-obra que já existe (`synthetic.py:687-725`) é da cadeia de **medição** e vai
  na direção oposta à hipótese (mesmo código com rótulos diferentes). Não a reaproveite como
  se fosse evidência de repetição.
- `make check` valida todo link relativo de Markdown do repositório, inclusive deste arquivo.
