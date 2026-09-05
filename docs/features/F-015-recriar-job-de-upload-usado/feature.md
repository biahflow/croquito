# F-015 — Reprocessar um PDF já enviado, sem subi-lo de novo

## Status

`READY_FOR_SPEC`

> Nasce em 2026-08-19, no inventário SaaS da
> [F-012](../F-012-operacao-saas-autorizacao-ia/feature.md), e **ganha Feature Contract em
> 2026-09-05** por seleção humana.
>
> A auditoria de 2026-08-23 já **encolheu esta feature pela metade**: a premissa original
> era "recriar job sem exigir digest nem allowlist", e a allowlist **já saiu** do caminho
> hospedado pela F-012 (`authorize_page` só existe hoje no caminho offline de eval, que o
> ADR-0036 preservou de propósito). O que resta é real e tem trava concreta.

## Classification

A definir na especificação de detalhe. Provavelmente **não** é `INTERFACE_CHANGE` se a
recriação couber num ato da tela existente de projetos; vira `INTERFACE_CHANGE` se exigir
superfície nova de escolha entre jobs do mesmo PDF.

## Priority

A definir pelo dono. A recomendação é `LOW` entre as cinco: hoje o contorno é subir o mesmo
arquivo de novo — que funciona, custa um upload e deixa dois uploads iguais no armazenamento.
É incômodo, não impedimento.

## Problem

`jobs.upload_id` é `ForeignKey("uploads.id")`, **`NOT NULL` e `UNIQUE`**
(`database.py:98`): um upload gera **um** job, para sempre. Quem quer reprocessar o mesmo
PDF — porque a extração melhorou, porque a rotação foi consertada (issue #138), porque a
primeira rodada foi descartada — precisa subir o arquivo outra vez.

O caso não é hipotético: as rodadas reais do Campo do Toca descartaram **dois jobs** antes
do que virou o job bom, e cada descarte custou um upload novo do mesmo PDF.

### A trava é decisão, não acidente

A unicidade é o que garante que "um PDF = um job" seja verdade em toda leitura do sistema, e
o [ADR-0049](../../adr/0049-evidencia-de-campo-na-revisao-do-escritorio.md) **decidiu
mantê-la** ao amarrar a evidência de campo ao job da prancha: "não existe job sem PDF" é
premissa daquele desenho. Afrouxar a coluna sem entender isso quebraria a F-030.

## Desired Outcome

Reprocessar um PDF que já está no sistema, com o histórico preservado: o job novo é
declaradamente derivado do anterior, e ninguém precisa procurar o arquivo original no
computador.

## Scope

1. **Ato de reprocessar** a partir de um job existente, criando job novo sobre o **mesmo
   objeto** já armazenado.
2. **Vínculo declarado** entre o job novo e o anterior — quem veio de quem, e por quê.
3. **Preservação do anterior**: nada é apagado. O job velho continua legível, com suas
   decisões e sua cena.

## Out of Scope

- Copiar decisões humanas do job anterior para o novo: a razão de reprocessar é justamente
  a extração mudar, e herdar decisão sobre leitura que não existe mais é como o rascunho
  velho da V17 (ver F-025).
- Apagar ou substituir o job anterior.
- Reprocessar em massa.

## Acceptance Criteria

1. Reprocessar um job cria job novo sobre o mesmo objeto, sem upload novo.
2. O job anterior continua íntegro e legível, com decisões e cena intactas.
3. O vínculo entre os dois é declarado e legível.
4. A evidência de campo do job anterior **não migra em silêncio** — o ADR-0049 amarrou-a
   àquele job.

## Unknowns

1. **Como a unicidade sobrevive.** Três caminhos, e a escolha é ADR: (a) relaxar
   `UNIQUE` e ensinar todo leitor a lidar com N jobs por upload; (b) manter e criar um
   registro de upload novo apontando para o **mesmo objeto** (barato, mas duplica metadado);
   (c) coluna própria de derivação, mantendo a unicidade sobre o par. **Precede o
   planejamento.**
2. **O que acontece com a evidência de campo** vinculada ao job anterior (F-030). Migrar,
   duplicar ou deixar — as três respostas são defensáveis e nenhuma é óbvia.

## Human Gates

1. **Seleção e prioridade** — decisão do dono.
2. **ADR do unknown 1** — mexe numa invariante que outra feature já usa como premissa.

## References

- `services/api/src/croquito_api/database.py:98` — `upload_id` `UNIQUE`.
- [ADR-0049](../../adr/0049-evidencia-de-campo-na-revisao-do-escritorio.md) — "não existe
  job sem PDF" como premissa da evidência de campo.
- [ADR-0036](../../adr/0036-autorizacao-de-ia-contratual-sem-allowlist-documental.md) — a
  allowlist que saiu do caminho hospedado e encolheu esta feature.
