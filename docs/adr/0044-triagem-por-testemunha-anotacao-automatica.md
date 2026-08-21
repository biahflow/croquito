# ADR-0044: Triagem por custo do erro — anotação automática para leitura sem papel de geometria

Status: Accepted  
Data: 2026-08-21 (aceito por ato humano na mesma data, após duas rodadas de
decisão registradas abaixo)  
Responsável: Product / Engineering

> Revisa o alcance do
> [ADR-0041](0041-decisao-de-ator-maquina-atras-de-flag-local.md) (D3/D5) sem
> tocar seus fundamentos: ator-máquina inconfundível, dupla chave local,
> retificação humana, auditoria nominal. Os números 0042/0043 foram tomados
> por frentes paralelas (F-031/F-032) em worktrees próprios.

## Contexto

A primeira rodada real do modo automático (F-029, Guaxindiba V4 local)
auto-decidiu 8 de 21 leituras — as com duas testemunhas — e deixou 13
exceções. O usuário apontou o custo residual ("se eu continuo confirmando
uma a uma, fico como antes"). Das 13 exceções, 8 eram elevações (`h=…`,
kind `height`), que **já não mandam na geometria** quando confirmadas —
viram texto preso ao elemento; exigir toque humano nelas cobra o preço de
cota de um dado que não é cota.

O corte único do ADR-0041 (D5) trata todo erro como igual. Os erros não são
iguais: **cota errada contamina geometria; anotação errada é um rótulo no
elemento errado** — visível, barato e retificável.

## Decisão

1. **Segundo tier de decisão automática, por custo do erro.** Com a MESMA
   dupla chave do ADR-0041, leitura elegível ao tier de anotação é a que
   satisfaz TODAS: (a) sinal `note` do provider (F-021,
   `annotation_suggested`) ou `kind` sem papel de geometria de planta —
   hoje, `height` — e nunca leitura designada como geometria pelo pedido do
   solver; (b) valor e unidade presentes; (c) sem decisão alguma. A
   exigência de `reading_confidence` acima do corte é **dispensada**:
   testemunha única basta, porque o erro não alcança geometria.
1a. **O tier espelha o ato humano de anotação — confirma SEM associação.**
   Emenda de 2026-08-21, mesma sessão, por achado de implementação: no
   mecanismo existente, associação explícita é restrição métrica no
   traçado (`height` puxa o eixo Y), e a regra humana recusa associação em
   anotação ("a anotação da folha é a única confirmação sem elemento
   associado", com 422 na tentativa). A auto-anotação portanto carrega a
   MESMA declaração de anotação do ato humano e NENHUMA entrada em
   `selected_associations`. O candidato mais provável e sua
   `association_confidence` viajam como **observação** (na `note` da
   decisão e na auditoria) para instruir a fixação do texto no aceite do
   traçado — nunca como vínculo. A redação original deste item ("associa
   como no tier 1") está SUPERSEDIDA por esta emenda.
2. **O tier não reclassifica nada.** A leitura entra como está (`kind`,
   valor, unidade e texto como o extrator leu — ADR-0041); o que muda é o
   critério de elegibilidade, não o conteúdo. Cota de planta
   (`length`/`width`/`radius`/`diameter`/`area`/`angle`) NUNCA entra por
   este tier, com qualquer confiança.
3. **Proveniência distingue os tiers.** A decisão de sistema carrega o tier
   (`note` da decisão, auditoria do export e resposta da API): "anotação
   automática" × "cota automática". Contadores da tela e lista nominal da
   auditoria separam os dois.
4. **Mesmos limites do ADR-0041**: só confirma, nunca sobrescreve, nunca
   redecide, retificável pelo caminho declarado, flag local apenas.

## Alternativas

- **Forma máxima — cota de planta de testemunha única estacionada
  (confirmada SEM associação, promovível pelo ato de associar existente)**:
  desenhada por completo em sessão a pedido do usuário e **recusada por ele
  na mesma sessão (2026-08-21)** diante dos custos declarados — leitura-lixo
  da extração entraria confirmada (o "24,75" duplicando o 21,75 da V4
  exigiria retificação para limpar), promoção associaria sem re-conferir o
  valor, e a cena traçada carregaria os warnings de não aplicada.
  Permanece candidata a fatia futura com contrato próprio SE a medição do
  resíduo (quantas cotas de planta de testemunha única sobram por
  levantamento) mostrar que se paga.
- **Reclassificar kind por máquina (length→note)** — rejeitada: máquina
  interpretando o que o extrator leu é o que o ADR-0041 proíbe.
- **Baixar o corte geral para cobrir elevações** — rejeitada: pagaria o
  ganho com erro de GEOMETRIA (a V1 mediu 55% de erro de associação no
  corte 0,6 sem testemunha dupla).

## Consequências

- `apply_auto_association` ganha o tier 2 com elegibilidade por kind;
  auditoria e resposta distinguem os tiers; testes cobrem o não-vazamento
  (nenhuma leitura de planta pelo tier 2; tier 1 inalterado bit a bit).
- A tela de exceções conta três grupos quando houver: cotas automáticas,
  anotações automáticas, exceções.
- A medição pós-rodada (exceções restantes por levantamento, separadas por
  kind) alimenta a decisão futura sobre a forma máxima e o score 1.1.0.
