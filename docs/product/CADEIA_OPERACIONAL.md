# Cadeia operacional: do levantamento ao pagamento

Status: Accepted  
Responsável: Product / Engineering  
Última revisão: 2026-08-21

Este documento é **descritivo**. Ele registra a cadeia real de trabalho — quem faz cada
etapa, que documento sai dela, o que o produto cobre e o que é ato humano fora dele.
Não decide arquitetura, não altera o estado de nenhuma feature, e não substitui o
[Data Flow](../architecture/DATA_FLOW.md) (técnico), o
[Valuation Context](../architecture/VALUATION_CONTEXT.md) (contexto de medição) nem os
[Processing Workflows](../architecture/PROCESSING_WORKFLOWS.md) (pipeline).

Ele existe porque a pergunta "qual documento eu mando para a empresa que vai executar?"
não tinha resposta escrita em lugar nenhum do repositório.

## 1. A licitação é o divisor — e há três momentos, não dois

O [ADR-0027](../adr/0027-price-source-provenance-and-bid-boundary.md) fixou dois momentos
com regras de preço opostas. A operação real tem três:

| momento | quem manda no preço | fontes permitidas | onde no produto |
|---|---|---|---|
| **Pré-licitação** — orçar uma obra que ainda não foi contratada | ninguém ainda; o orçamento é a estimativa que vai ao edital | cascata livre: `sco`, `emop`, `sinapi`, `sicro`, `composition` | jornada Orçamento |
| **Demanda sob contrato** — orçar uma praça dentro de um contrato guarda-chuva já licitado | o contrato | **só a tabela contratual** (na prática `sco`) | jornada Orçamento, guardrail na instalação da fonte (F-033) |
| **Execução / medição** — medir e pagar o que foi feito | o contrato | só `PriceOrigin.sco`, guardrail `BULLETIN_PRICE_ORIGIN_FORBIDDEN` fail-closed | jornada Medição |

O terceiro estado é o que a operação das praças usa, e é o que o modelo ainda não
representa. Está registrado como
[F-033](../features/F-033-demanda-sob-contrato-licitado/feature.md).

<figure>
<div class="figbox">
<svg viewBox="0 0 720 250" role="img" aria-label="Linha do tempo com tres momentos de preco separados pela licitacao e pela execucao: pre-licitacao com cascata livre, demanda sob contrato com guardrail na instalacao da fonte, e medicao com guardrail fail-closed.">
<defs>
<marker id="ar-ink" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse"><path d="M0,0 L10,5 L0,10 z" class="f-ink"/></marker>
<marker id="ar-gap" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse"><path d="M0,0 L10,5 L0,10 z" class="f-gap"/></marker>
</defs>
<line x1="20" y1="196" x2="700" y2="196" class="l-ink" stroke-width="1.5" marker-end="url(#ar-ink)"/>
<line x1="248" y1="34" x2="248" y2="196" class="l-ink" stroke-width="1.5" stroke-dasharray="5 4"/>
<line x1="480" y1="34" x2="480" y2="196" class="l-ink" stroke-width="1.5" stroke-dasharray="5 4"/>
<text x="248" y="26" text-anchor="middle" class="mono" font-size="11.5">LICITAÇÃO</text>
<text x="480" y="26" text-anchor="middle" class="mono" font-size="11.5">EXECUÇÃO</text>
<rect x="24" y="52" width="204" height="122" fill="none" class="l-ink" stroke-width="1"/>
<text x="38" y="76" class="mono" font-size="11">PRÉ-LICITAÇÃO</text>
<text x="38" y="102" font-size="12.5">Orçamento-base</text>
<text x="38" y="124" font-size="12" class="quiet">Cascata livre:</text>
<text x="38" y="142" font-size="12" class="quiet">sco · emop · sinapi</text>
<text x="38" y="160" font-size="12" class="quiet">sicro · composição</text>
<rect x="256" y="52" width="216" height="122" fill="none" class="l-gap" stroke-width="2"/>
<text x="270" y="76" class="mono t-gap" font-size="11">DEMANDA SOB CONTRATO</text>
<text x="270" y="102" font-size="12.5">Orçamento da praça</text>
<text x="270" y="124" font-size="12" class="quiet">Só a tabela do contrato</text>
<text x="270" y="148" class="mono t-gap" font-size="11">GUARDRAIL NA FONTE</text>
<text x="270" y="164" class="mono t-gap" font-size="10">F-033</text>
<rect x="488" y="52" width="208" height="122" fill="none" class="l-ink" stroke-width="1"/>
<text x="502" y="76" class="mono" font-size="11">MEDIÇÃO</text>
<text x="502" y="102" font-size="12.5">Boletim + memória</text>
<text x="502" y="124" font-size="12" class="quiet">Só origin=sco</text>
<text x="502" y="148" font-size="12" class="quiet">Guardrail fail-closed</text>
<path d="M364 178 C 364 214, 590 214, 590 178" fill="none" class="l-gap" stroke-width="1.5" stroke-dasharray="4 3" marker-end="url(#ar-gap)"/>
<text x="477" y="240" text-anchor="middle" font-size="11.5" class="t-gap">código de outra fonte só é recusado aqui — sobre obra já executada</text>
</svg>
</div>
<figcaption>O guardrail existe no terceiro momento e falta no segundo. Um código de fonte não-contratual entra no orçamento sem resistência e só encontra a recusa na medição, meses depois.</figcaption>
</figure>

## 2. A cadeia, etapa por etapa

| # | etapa | quem faz | documento que sai | onde no produto | estado |
|---|---|---|---|---|---|
| 1 | Relação de Praças: escopo itemizado + verba prevista por demanda | prefeitura | relação de demandas | — | ato humano, fora do produto |
| 2 | Levantamento em campo | equipe de campo | fotos + croqui de campo + medidas | app de campo (F-032, ainda em branch própria, fora da `main`) | em construção |
| 3 | Ingestão e leitura das cotas | produto | PNGs 200 DPI + `ReviewPacket` com recorte e digest | `croquito-demo` (`ingest.py`, `vision.py`, `review.py`); jornada Croqui | **no ar** |
| 4 | Revisão humana das cotas, associação e calibração | orçamentista/técnico | `HumanDecision` por leitura, associação `reading_id → proposal_id` | jornada Croqui | **no ar** |
| 5 | Solver e traçado; aprovação da cena | produto + humano | `SceneRevision` aprovada (`SceneApproval` amarrada ao UUID da revisão) | `rectangle_solver.py`, `tracing.py` | **no ar** |
| 6 | Exportação CAD | produto | **DXF auditado** + render + ZIP | `dxf.py`; portão `ensure_exportable()` | **no ar** |
| 7 | Importação no CAD e desenho da prancha | projetista | **prancha** (PDF/DWG) com legenda quantificada | — | ato humano, fora do produto |
| 8 | Orçamento da demanda | orçamentista | **planilha orçamentária** com BDI e coluna `FONTE` por linha | jornada Orçamento (`/v1/estimate-rounds*`), incl. teto da [F-027](../features/F-027-modo-teto-orcamento-invertido/feature.md) | **no ar** (ver §5) |
| 9 | Aprovação do orçamento | prefeitura (papel `aprovador`) | orçamento **assinado** e despachado | jornada Orçamento (`POST /v1/estimate-rounds/{id}/estimate/approve` + `.../export`), [F-035](../features/F-035-aprovacao-do-orcamento/feature.md) | **no ar** |
| 10 | Ordem de Serviço / autorização | prefeitura | **OS**, tendo prancha + orçamento aprovado como anexos | — | ato humano, fora do produto |
| 11 | Execução | empresa de engenharia | obra | — | fora do produto |
| 12 | Medição do executado | fiscal | **boletim de medição** + **memória de cálculo** | jornada Medição (`/v1/valuation-rounds*`) | **no ar** |
| 13 | Item executado sem código no contrato | fiscal | **dossiê do aditivo** (item, quantitativo, justificativa; **sem preço** por construção) | `build_amendment_dossier`, `/v1/valuation-rounds/{id}/amendment-dossier` | **no ar** |
| 14 | Pagamento | prefeitura | — | — | ato humano, fora do produto |

Entre a etapa **6** e a **12** existe, desde a F-047, um **elo declarado**: quem mede diz
qual croqui aprovado alimenta a rodada (`POST /v1/valuation-rounds/{round_id}/scene-link`) e
manda confrontar a legenda com o `quantitativos.csv` daquele pacote
(`POST /v1/valuation-rounds/{round_id}/takeoff/scene-quantities`). O item sem quantidade
recebe a da cena, com a precisão declarada lá; o item que já tinha a da legenda e discorda
além da tolerância abre **divergência**, e ninguém escolhe por ninguém. O elo é ato humano:
nada é ligado por obra de mesmo nome nem por data próxima. A etapa 7 continua fora do
produto — o elo liga o croqui à medição, não dispensa a prancha.

## 3. Qual documento vai para a empresa

Esta é a pergunta que originou o documento. Os três artefatos financeiros têm as mesmas
colunas (item, código, unidade, quantidade, preço), e é por isso que se confundem — mas
vivem em momentos opostos e **viajam em direções opostas**.

<figure>
<div class="figbox">
<svg viewBox="0 0 720 230" role="img" aria-label="Duas faixas, prefeitura em cima e empresa embaixo: antes da obra desce prancha mais orcamento aprovado como anexo da ordem de servico; depois da execucao sobem boletim de medicao e memoria de calculo.">
<defs>
<marker id="ar-down" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path d="M0,0 L10,5 L0,10 z" class="f-down"/></marker>
<marker id="ar-up" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path d="M0,0 L10,5 L0,10 z" class="f-up"/></marker>
</defs>
<line x1="20" y1="40" x2="700" y2="40" class="l-ink" stroke-width="1"/>
<line x1="20" y1="190" x2="700" y2="190" class="l-ink" stroke-width="1"/>
<text x="20" y="30" class="mono" font-size="11">PREFEITURA</text>
<text x="20" y="208" class="mono" font-size="11">EMPRESA DE ENGENHARIA</text>
<line x1="200" y1="46" x2="200" y2="184" class="l-down" stroke-width="2.5" marker-end="url(#ar-down)"/>
<text x="214" y="86" class="mono t-down" font-size="10.5" letter-spacing="1">ANTES · AUTORIZA</text>
<text x="214" y="108" font-size="12.5" class="t-down">Prancha</text>
<text x="214" y="128" font-size="12.5" class="t-down">+ orçamento aprovado</text>
<text x="214" y="150" font-size="11.5" class="t-down" opacity="0.8">anexos da Ordem de Serviço</text>
<line x1="520" y1="184" x2="520" y2="46" class="l-up" stroke-width="2.5" marker-end="url(#ar-up)"/>
<text x="534" y="86" class="mono t-up" font-size="10.5" letter-spacing="1">DEPOIS · PAGA</text>
<text x="534" y="108" font-size="12.5" class="t-up">Boletim de medição</text>
<text x="534" y="128" font-size="12.5" class="t-up">+ memória de cálculo</text>
<text x="534" y="150" font-size="11.5" class="t-up" opacity="0.8">um boletim por período</text>
<text x="360" y="172" text-anchor="middle" class="mono quiet" font-size="10.5" letter-spacing="1">← EXECUÇÃO →</text>
</svg>
</div>
<figcaption>O boletim não pode acompanhar a Ordem de Serviço: ele mede algo que ainda não aconteceu.</figcaption>
</figure>


**Desce — prefeitura → empresa, antes da obra, autoriza:**

- a **prancha** (o quê e onde);
- a **planilha orçamentária aprovada** (o quanto).

Os dois viram anexo da **Ordem de Serviço**. É o pacote que diz "execute isto, por este
valor". É isto que vai para a empresa.

**Sobe — obra → prefeitura, depois da execução, paga:**

- o **boletim de medição** (o que foi de fato executado no período × preço do contrato);
- a **memória de cálculo**, anexa a ele.

O boletim **não pode** acompanhar a OS: ele mede algo que ainda não aconteceu.

## 4. Orçamento × boletim × memória

| | Orçamento | Boletim de medição | Memória de cálculo |
|---|---|---|---|
| pergunta | quanto **vai** custar? | quanto **foi** feito? | de onde saiu essa quantidade? |
| momento | antes da obra | durante/depois | junto do boletim |
| direção | prefeitura → empresa | obra → prefeitura | anexa ao boletim |
| efeito | autoriza a execução | libera o pagamento | sustenta a auditoria |
| cardinalidade | **um** por demanda | **vários** (um por período) | um por item do boletim |
| tem dinheiro? | sim | sim | **não** — só quantidade |
| modelo | `Estimate` / `EstimateLine` | `WorksiteBulletin` / `BulletinLine` | `CalcSheet` / `CalcBlock` / `CalcOperand` |

Os modelos estão em
[`packages/valuation/src/croquito_valuation/models.py`](../../packages/valuation/src/croquito_valuation/models.py).

**A memória nunca viaja sozinha.** Memória sem boletim não é documento entregável: ela
existe para justificar a quantidade de uma linha específica do boletim.

A costura entre os dois é protegida no domínio: `CalcSheet.total_quantity` tem de bater
com a `quantity` da linha do boletim, e um plano de cálculo que não fecha recusa com
`CALC_PLAN_QUANTITY_MISMATCH` em vez de ajustar qualquer um dos dois — a quantidade que o
humano confirmou nunca é a que cede
([`calc.py`](../../packages/valuation/src/croquito_valuation/calc.py)).

Aritmética, que difere entre os dois: dinheiro **trunca** (`money_trunc`), quantidade
**arredonda** (`quantity_round`).

## 5. Lacunas conhecidas

1. ~~**Demanda sob contrato não tem guardrail de fonte.**~~ **Fechada em 2026-08-22** pela
   [F-033](../features/F-033-demanda-sob-contrato-licitado/feature.md), sobre o
   [ADR-0045](../adr/0045-terceiro-estado-demanda-sob-contrato.md) (`Accepted`).
   A rodada declara que corre sob contrato licitado, e a partir daí instalar fonte com
   origem diferente de `sco` recusa na **instalação** (`ESTIMATE_CASCADE_ORIGIN_FORBIDDEN`)
   — quando ainda há o que corrigir, e não meses depois no pagamento. O regime é mão única
   e declará-lo com fonte proibida já instalada também recusa, sem reescrever nada.
   `BULLETIN_PRICE_ORIGIN_FORBIDDEN` continua existindo; deixou de ser o primeiro a ver.
   Fica registrado o que era a mitigação manual enquanto isso não existia — instalar uma
   fonte só, o catálogo `sco` do contrato —, porque ela ainda é a boa prática: o guardrail
   trata da **origem**, não da identidade do contrato (item 4).

2. **A etapa 8 depende de chamada paga para ler a legenda da prancha.**
   `POST /v1/estimate-rounds/{id}/plate/extractions` exige, nesta ordem: entitlement de
   IA ativo no tenant (administrado só por `platform_operator`),
   `CROQUITO_REAL_PROVIDERS_ENABLED` no ambiente, e worker consumindo a fila. Faltando
   qualquer um, a cadeia para ali e o teste ponta a ponta sai mais barato pelo CLI
   (`make valuation-estimate-demo`).

3. ~~**Etapas 7, 9, 10, 11 e 14 são atos humanos fora do produto.**~~ **A etapa 9 entrou
   em 2026-08-22** pela [F-035](../features/F-035-aprovacao-do-orcamento/feature.md)
   ([ADR-0046](../adr/0046-aprovacao-do-orcamento-base.md)): a aprovação do orçamento é ato
   registrado, com papel próprio (`aprovador`, que não é quem montou), amarrada por digest
   ao conteúdo exato assinado, e é ela que abre o despacho da planilha — montar deixou de
   publicar. Remontar depois de assinado não apaga a assinatura: torna-a **caduca**, e o
   despacho recusa até um ato novo.

   As etapas **7, 10, 11 e 14** seguem como atos humanos fora do produto. O produto entrega
   o DXF auditado (6) e recebe a prancha de volta (8); entre um e outro há trabalho de CAD
   que ele não faz nem acompanha.

4. **Restringir a origem não garante o contrato certo.** Com a F-033 entregue, esta é a
   lacuna que **permanece**: nada confere se o catálogo `sco` instalado é o da data-base e
   do desconto daquele contrato. Está declarada fora do escopo dela e nomeada na decisão 6
   do [ADR-0045](../adr/0045-terceiro-estado-demanda-sob-contrato.md); o pacote de design
   a desenha como bloco **reservado**. Fechá-la exige o orçamento modelar contrato como
   entidade, o que é feature própria.

## Documentos relacionados

- [ADR-0027 — fontes de preço com proveniência e a fronteira licitada × pré-licitação](../adr/0027-price-source-provenance-and-bid-boundary.md)
- [Valuation Context](../architecture/VALUATION_CONTEXT.md)
- [Data Flow](../architecture/DATA_FLOW.md)
- [FDD](FDD.md) e [Glossary](GLOSSARY.md)
