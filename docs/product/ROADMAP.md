# Roadmap

Status: Active  
Responsável: Product  
Última revisão: 2026-08-12

## Agora — MVP privado

- Golden dataset e eval harness.
- Upload, processamento, revisão e DXF.
- Guaxindiba, Toca e Raul Campelo.
- Dois provedores, Textract e scene graph.
- AWS gerenciada, retenção e observabilidade.

## Próximo — generalização controlada

- Ampliar regressão com documentos autorizados.
- Biblioteca versionada de símbolos e blocos.
- Melhor associação automática entre cotas e segmentos.
- Curvas e polígonos com constraints adicionais.
- Projetos persistentes com política contratual de retenção.
- Métricas de qualidade por categoria de croqui.

## Agora — medição de obra (contexto valuation, v1 em marcos)

Cadeia do orçamentista: importar a medição anterior, extrair a legenda quantificada da
prancha com revisão humana, sugerir código SCO com confirmação humana, montar memória
de cálculo e exportar a medição seguinte em `.xlsx` auditado. Marcos M1–M5 descritos no
contexto de arquitetura do módulo; IA paga somente no marco final, com os gates de
gasto existentes.

**Marcos seguintes (propostos em 2026-08-13, a especificar):** a primeira rodada real
(Campo do Toca) e a orçamentista do domínio fixaram uma distinção que governa os
próximos marcos — **dois momentos com regras de preço diferentes**:

- **Obra licitada (medição)**: o contrato manda. O preço SCO é composto (mão de obra e
  insumos dentro do código de serviço; a escolha certa é o código de *execução*, não o
  de mero fornecimento — distinção que a UI deve tornar visível). Item que não está na
  lista SCO/contrato **não pode** vir de outra tabela: o caminho é **aditivo de
  contrato** (RE-RA) solicitando a inclusão — o sistema deve detectar esses itens e
  produzir o **dossiê do aditivo** (item, quantitativo, justificativa), nunca precificar
  por fora. Criação/gestão de RE-RA segue no item abaixo.
- **Pré-licitação (orçamento-base)**: aí sim vale a cadeia **SCO → EMOP → composição
  manual**. Importador da tabela EMOP como segundo catálogo com proveniência
  (`PriceCatalogEntry.origin` vira dado; catálogo digital oficial é **pago** via GRE, em
  .DBF, com sincronização mensal possível por rotina — nova versão com data-base
  própria, nunca troca silenciosa de preço), e composição com coeficientes declarados
  (item → várias linhas: horas, insumos). É o coração do "gerador de orçamento" da fase
  1 da visão de produto.
- **M6 — UI web de homologação da medição** (priorizado pelo usuário em 2026-08-13):
  revisão do takeoff, shortlist com descrição completa do catálogo, confirmação de
  código e boletim — o ato humano da orçamentista numa tela, não no CLI. Destrava a
  homologação da cadeia existente; a rodada real da Toca está estacionada no elo da
  confirmação até este marco.
- **M7 — matcher híbrido de código SCO** (priorizado pelo usuário em 2026-08-13, durante
  a homologação: "não posso correr o risco de o código ter no SCO e não fazer o match"):
  léxico com radical conservador + sinônimos de domínio como dado, retrieval semântico
  por embeddings do catálogo (dado público SCO; índice local por digest) com fusão de
  ranking, e a garantia virando gate de eval — golden set com `recall@20 = 100%`.
  Candidatos sempre com origem e score declarados; confirmar segue ato humano; sem
  chave/teto, o léxico permanece como fallback funcional declarado.
- **M8 — fontes de preço pré-licitação**: o bloco EMOP + composição acima, consumindo a
  mesma UI depois.

## Próximo — medição além do v1

Deliberadamente fora do v1, com as portas de extensão já reservadas no modelo:

- Modo teto / orçamento invertido ("escopo dentro de R$ X" da relação de demanda);
  porta: `EstimateTarget` reservado no glossário do contexto.
- Composição própria como caminho de escrita para item sem preço de referência;
  porta: `PriceCatalogEntry.origin`.
- Quantitativo automático derivado do scene graph aprovado; porta: `TakeoffItem.source`
  discriminado + `QuantitySource` lendo o `quantitativos.csv` do export DXF. Depende de
  identidade estruturada de elemento nas entidades (hoje rótulo é texto livre).
- Criação e gestão de re-ratificações (RE-RA); no v1 elas são apenas lidas para o
  cálculo de saldo.
- Reajuste de preços entre medições (data-base móvel).
- UI web de revisão da medição (v1 é CLI-first, como o resto do produto).
- Múltiplas pranchas por praça na extração de legenda.
- Cascata configurável de fontes de preço além do SCO (SINAPI, SICRO, tabelas
  estaduais), cada fonte com importador próprio — tabela de preços é dado, não código.

## Depois — produto comercial ampliado

- DWG após decisão de licenciamento.
- Comparação de versões V1/V2.
- Templates de layers por cliente.
- Multi-page alignment com referências explícitas.
- Integrações CAD e gestão de projetos.
- Modelos especializados somente após dataset licenciado e evals robustas.

## Não planejado sem nova decisão

- Promessa de conversão universal sem revisão.
- Inferência automática de dimensões inexistentes.
- Substituição de responsabilidade técnica do engenheiro.
- BIM/IFC ou modelagem 3D.

