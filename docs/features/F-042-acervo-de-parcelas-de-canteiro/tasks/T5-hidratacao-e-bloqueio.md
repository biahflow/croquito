# F-042 T5 — A tela mostra o bloqueado e recupera o que já está gravado

- **feature_id**: F-042
- **task_id**: T5
- **role**: builder
- **depends_on**: [T3, T4 (contrato de API, fixado abaixo)]
- **required_capabilities**: READ, WRITE (`apps/web/src/orcamento`), VALIDATE
- **risk**: ALTO — `OrcamentoApp.tsx` vivo, e a hidratação toca o estado que a montagem do orçamento consome.
- **relative_effort**: L

## Os dois defeitos que esta task corrige

**1. O beco sem saída da recusa.** A recusa de parâmetro faltante prometia "declare, ou remova
na pré-visualização as parcelas que os citam", mas recusava *antes* da prévia existir. A T4
(worktree paralela) fez a prévia **marcar** em vez de recusar; esta task mostra a marcação.

**2. A matriz tem dois donos.** O `apply` grava a matriz no servidor. A tela monta o rascunho
e manda a matriz inteira no `build`. Enquanto a sessão vive, os dois concordam — mas depois de
um recarregamento a tela perde o rascunho, e **montar o orçamento apaga do banco o que o
acervo aplicou**. A raiz é anterior a esta feature (a matriz nunca foi lida de volta desde a
F-038, e o mesmo vale para as contribuições autoradas à mão), e o acervo a torna grave.

**Decisão do dono, 2026-08-28**: a tela **hidrata** o rascunho a partir da matriz gravada.

## Contrato de API (fixado — a T4 implementa exatamente isto)

```
POST .../site-setup/preview   (não recusa mais por parâmetro faltante nem código ausente)
 → {"round_id","version","kit_id","kit_version",
    "rows":[{"parcel_id","code","label",
             "operands":[{"name","value":"<decimal string>"|null,"unit":string|null,
                          "parameter":string|null}],
             "quantity":"<decimal string>"|null,
             "missing_parameters":["prazo_meses"],
             "code_absent":false}],
    "excluded_parcel_ids":[...],
    "blocked_parcel_ids":[...]}

POST .../site-setup/apply     (continua recusando FECHADO, sem mudança)

GET  .../calc-matrix          (leitura pura)
 → {"round_id","version","calc_matrix":{...}|null}
```

`blocked_parcel_ids` já exclui as parcelas removidas. `quantity: null` é ausência, não zero.

## Scope

### 1. A linha bloqueada na pré-visualização

- No lugar da quantidade, a linha diz **o que falta**, por extenso e nomeando: "falta declarar
  **semiperímetro**" (ou os dois, quando forem dois), ou "código fora do catálogo desta
  rodada" quando `code_absent`.
- A distinção **não pode ser só cor**: texto próprio na célula, como manda a folha.
- A linha bloqueada continua **removível**, e é isso que destrava a saída prometida: remover
  as 2 parcelas bloqueadas deixa as outras 22 aplicáveis.

### 2. O botão de aplicar

Enquanto houver parcela bloqueada **não removida**, aplicar fica indisponível — mas **com o
motivo nomeado ao lado**, nunca só apagado:

> "2 parcelas não podem nascer: falta declarar **semiperímetro** e **altura do alambrado**.
> Declare os parâmetros ou remova essas parcelas."

Isto **não** é a tela assumindo a recusa do servidor: a diferença é que agora a tela tem a
informação exata, parcela a parcela, vinda da prévia. O servidor continua recusando fechado
se o ato chegar mesmo assim, e essa recusa continua tratada.

`podeAplicar` (`acervo.ts`) ganha essa condição, e ela entra nos testes do portão da prévia.

### 3. Hidratação da matriz

Ao entrar na etapa de códigos de uma rodada, a tela lê `GET .../calc-matrix` e reconstrói o
rascunho a partir do que está gravado:

- contribuição **com** `kit_origin` → é parcela de acervo, e alimenta o estado do painel de
  canteiro (incluindo o carimbo do que já foi aplicado: qual `kit_version`, quantas parcelas);
- contribuição **sem** `kit_origin` → é a autorada à mão, e alimenta `contribuicoes`, pela
  chave `contributionKey(itemId, code)` que já existe;
- `calc_matrix: null` é o regime legado: rascunho vazio, exatamente como hoje.

Depois da hidratação, **montar o orçamento não pode perder nada**: a matriz enviada ao build
precisa conter o que estava gravado mais o que a sessão acrescentou. Este é o critério que
importa, e ele precisa de teste explícito — abrir uma rodada com matriz gravada e montar sem
tocar em nada deve produzir uma matriz equivalente à gravada.

A conversão inversa de `assembleCalcMatrix` vive em `matrix.ts`, com o mesmo cuidado de
espelho à mão que o arquivo já declara.

**Cuidado registrado pela T3**: `abrirOrcamento` não zera `contribuicoes` (defeito
pré-existente), então trocar de rodada carrega a matriz da anterior. Com a hidratação isso
vira corrupção silenciosa entre rodadas — **zere o rascunho ao trocar de rodada**, antes de
hidratar. Isso está em escopo agora, porque a hidratação o torna perigoso.

### 4. Testes

- linha bloqueada mostra o que falta, por texto, e continua removível;
- remover as bloqueadas destrava o aplicar — **este é o teste do defeito corrigido**;
- aplicar indisponível traz o motivo nomeado, não só o controle apagado;
- hidratação: rodada com matriz gravada reconstrói contribuições à mão e parcelas de acervo;
- **montar sem tocar em nada, depois de hidratar, não perde contribuição** (o defeito 2);
- `calc_matrix: null` deixa o rascunho vazio;
- trocar de rodada zera o rascunho antes de hidratar.

## Out of Scope

- `services/`, `packages/`, migrações.
- Autoria de acervo (estado 09 do pacote) — segue com a T6.
- Estados que o pacote de design marcou como não incluídos.

## Acceptance Criteria

1. Existe caminho para aplicar as parcelas calculáveis quando outras estão bloqueadas: remover
   as bloqueadas destrava o ato.
2. O motivo de não poder aplicar é lido na tela, nomeando parâmetro ou código.
3. Depois de recarregar, a etapa mostra o que está gravado, e montar o orçamento não apaga
   nada.
4. Trocar de rodada não vaza o rascunho da anterior.
5. Nenhuma aritmética de quantidade no navegador.
6. Nenhum teste existente afrouxado; os que mudam de comportamento (recusa da prévia) são
   adaptados e explicados um por um.

## Validation

```bash
cd /Users/danielcampos/workspace/daniel/croquito-int-web
npm --workspace @croquito/web run test
make check
make test
```

## Armadilhas verificadas

- `assembleCalcMatrix` devolve `null` sem contribuição nenhuma — regime legado, não pode
  quebrar.
- `matrix.ts` é espelho à mão, não contrato gerado.
- Decimais como string; `quantity: null` é ausência, não zero.
- Cor nunca é o único indicador.
- `make check` valida todo link relativo de Markdown, inclusive deste arquivo.
