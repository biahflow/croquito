# Task Contract — F-032 / T17: marca na barra, endereço na chegada, ícone PWA (rev.2)

- Feature: F-032 — [feature.md](../feature.md); nasceu como PLAN_DEVIATION da
  DAP rev.2 (registro em [plan-sync.md](../plan-sync.md)).
- Gate satisfeito: DAP rev.2 aprovada por Daniel Campos em 2026-08-21.
- Esforço: XS. Depende de: nada além do gate (mas executa SEQUENCIAL a T12/T15
  por sobreposição de arquivos de UI no worktree compartilhado).

## Goal

Aplicar no app real os dois ajustes aprovados na rev.2 + o acerto de marca do
ícone: (1) a marca do croquito (quadrado grafite com traço verde do wordmark)
acompanha o nome no `AppBar` de todas as telas; (2) a tela de chegada mostra
local/endereço vindos da ordem em vez de coordenadas (coordenadas continuam
como dado `GpsFix`, nunca exibidas); (3) `apps/field/public/icon.svg` deixa de
ser placeholder azul e vira a marca real.

## Contexto verificado

- Referência visual aprovada: `mock/campo.html` (regra `.appbar .brand::before`
  — quadrado `12px`, borda `3px` verde `--accent`, fundo escuro) e a prancha 2
  re-renderizada (`mock/02-chegada.png`): "Local confirmado — {nome da praça}"
  + "{endereço} — a ~X m do endereço da ordem · a localização serve para achar
  a obra, não para medir".
- Marca canônica: `apps/web/src/assets/croquito-logo-dark.svg` (o `<rect>` de
  traço `#00E389` sobre fundo `#0E1116`).
- `apps/field/src/ui/AppBar.tsx` — brand atual só texto.
- `apps/field/src/ui/ArrivalScreen.tsx` + `apps/field/src/orders/` — a ordem
  fixture precisa carregar `address`/`place_name` (aditivo na fixture local;
  se o tipo da ordem não tiver campo de endereço, acrescente aditivamente e
  registre); o cálculo "a ~X m" só aparece se houver fix GPS E endereço — sem
  geocodificação reversa, sem rede.
- `apps/field/public/icon.svg` — placeholder azul (fora da marca) do scaffold.

## Comportamento exigido

1. `AppBar`: marca antes do nome em todas as telas (CSS ou SVG inline, alvo da
   prancha; sem asset novo pesado). Cor nunca é o único indicador — a marca é
   decorativa (`aria-hidden`).
2. `ArrivalScreen`: check de localização com nome da praça + endereço da ordem;
   coordenadas removidas da tela (o `GpsFix` continua registrado no domínio
   exatamente como hoje — NENHUMA mudança de domínio/outbox); distância ao
   endereço só como texto aproximado quando calculável a partir do fix (senão
   omite a parte "a ~X m").
3. `icon.svg` (e o ícone do manifest PWA, se separado): marca real — quadrado
   grafite com traço verde, fundo `#0e1116`; conferir que o build PWA regenera.
4. Testes: ajuste dos testes de UI existentes que citem o texto antigo de GPS;
   teste do novo texto de chegada com e sem endereço na ordem (fixture legada
   sem endereço não pode quebrar — mostra só o nome/da ordem o que houver).

## Out of scope

- Geocodificação reversa, mapa, qualquer rede; mudança de domínio (`GpsFix`,
  outbox, contrato — nada); `services/**`, `packages/**`; redesenho além dos
  dois ajustes aprovados.

## Validação

```bash
cd /Users/danielcampos/workspace/daniel/croquito-f032
npm --workspace @croquito/field run test -- --run
npm --workspace @croquito/field run check
make check
make test
```

## Gates

COMMIT forbidden. Nenhum gate humano restante (rev.2 aprovada).

## Report

`BUILD REPORT` completo.
