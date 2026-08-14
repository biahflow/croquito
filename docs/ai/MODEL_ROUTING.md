# Roteamento de modelos

Status: Accepted for MVP  
Responsável: AI Engineering / Platform  
Última revisão: 2026-08-13 (eval paga das tarefas de medição)

## Rotas padrão

| Papel | Provedor/modelo | Execução |
|---|---|---|
| Leitura multimodal A | OpenAI `gpt-5.6-terra` | toda página/região principal |
| Leitura multimodal B | Bedrock `global.anthropic.claude-sonnet-5` | toda página/região principal |
| OCR auxiliar | Amazon Textract `DetectDocumentText` | toda página renderizada |
| Escalonamento A | OpenAI `gpt-5.6-sol` | somente conflito material |
| Escalonamento B | Bedrock Claude Opus 5 disponível no ambiente | somente conflito material |

Model IDs efetivos são resolvidos por configuração validada no startup e gravados
em cada `ProviderReading`. Falha de disponibilidade bloqueia ativação do modelo;
não ocorre substituição silenciosa.

### Caminho alternativo: API direta da Anthropic

Quando o Bedrock não está acessível na conta (caso real em 2026-08-11), os modelos
Claude podem ser chamados pela API direta da Anthropic via `AnthropicProviderAdapter`
(`CROQUITODXF_ANTHROPIC_API_KEY`). O lineage distingue os dois caminhos: API direta
grava `provider: anthropic`; Bedrock grava `provider: bedrock_anthropic`. Relatórios
de eval anteriores a essa distinção (Guaxindiba, 2026-08-11) foram executados pela
API direta apesar de rotulados `bedrock_anthropic`.

O caminho direto é usado hoje apenas pela eval CLI (`croquitodxf-demo
extraction-eval`), que seleciona provedor e modelo pela flag
`--arm nome=provider:model_id` (ex.: `opus=anthropic:claude-opus-5`). A autorização
de providers por job na API (`openai`, `bedrock_anthropic`, `textract`) ainda não
inclui `anthropic`; incluir o caminho direto na sessão autenticada exige atualizar a
lista, o contrato e os testes de contrato — pendência registrada, não implícita.

## Estado de implementação local

O worker possui portas tipadas e mocks determinísticos para OpenAI, Bedrock/Claude
e Textract. Elas são ativadas somente por injeção em teste ou pelo demo sintético;
o worker normal não lê flag de ambiente para fabricar observações e não chama
serviços externos. Adapters reais são configuráveis somente no ambiente local por
`CROQUITODXF_REAL_PROVIDERS_ENABLED=true`; exigem entitlement contratual ativo por
tenant e snapshot imutável por job, credenciais fora do Git, budget, eval
comparativa e plano de rollback. O piloto
processa a primeira página e sinaliza as demais como não analisadas. LocalStack
continua restrito a storage/fila: Bedrock e Textract usam clientes AWS separados.
Antes de cada chamada, o worker reserva o custo estimado configurado para o job;
ultrapassar `CROQUITODXF_AI_MAX_ESTIMATED_COST_USD` bloqueia a chamada.

## Etapas

### Page survey

Recebe página completa e identifica regiões, tipos de desenho, vocabulário e
possíveis cotas. Não produz coordenadas CAD.

### Region extraction

Recebe recorte em alta resolução mais contexto mínimo da página. Produz leituras
no schema do prompt contract.

### Escalation

Ocorre quando:

- Valores normalizados divergem.
- Associação aponta para entidades diferentes.
- Schema é válido, mas regra geométrica falha.
- Texto é ambíguo na precisão material.

Escalonamento recebe somente o recorte, as duas transcrições e a pergunta de
desambiguação. Não recebe a preferência do sistema.

## Falhas

- Textract falha: continuar com `OCR_EVIDENCE_MISSING`.
- Um LLM falha: continuar sem auto-confirmação e criar issue critical.
- Ambos falham: job falha após retries.
- Modelo retorna schema inválido: uma tentativa de repair estritamente estrutural;
  depois tratar como falha.
- Rate limit: retry com backoff e respeito a `Retry-After`.

## Controle de custo

- Nunca escalonar página inteira quando um recorte resolve.
- Deduplicar por image digest + prompt version + model ID.
- Limitar reanálises manuais por tenant e exibir impacto operacional.
- Registrar tokens, duração e custo estimado sem conteúdo.
- Evals usam conjunto fixo; não repetem chamadas para “melhor resultado”.

## Eval comparativa executada (Toca, 2026-08-11)

Primeira eval paga comparativa de extração de geometria, autorizada pelo usuário
(teto US$ 1,50), sobre `golden-toca-v1/page-001.png` via API direta da Anthropic:

| Arm | Modelo | Elementos | Corroboração bruta | Após registro | Custo real |
|---|---|---|---|---|---|
| opus | `claude-opus-5` | 23 | 0,57 | **0,96** ✅ | ≈ US$ 0,14 |
| sonnet | `claude-sonnet-5` | 14 | 0,14 | 0,57 ❌ | ≈ US$ 0,04 |

Decisão de roteamento: **Opus é o modelo de extração de geometria**. O Sonnet reprovou
mesmo após o registro fino (`register-extraction`): o melhor assentamento exigiu girar o
conjunto 270° e 6 de 14 elementos ficaram sem tinta — estrutura errada, não só
enquadramento. Rollback: desligar `CROQUITODXF_REAL_PROVIDERS_ENABLED` volta ao caminho
OpenCV-only (golden `dxf-toca` demonstra o resultado sem extração).

O gate `corroborated_rate >= 0.7` reprova por desregistro sistemático do VLM; o comando
`register-extraction` corrige assentamento sem poder inventar geometria e preserva a taxa
original em nota. A coluna "Após registro" desta tabela foi medida com a versão do motor
que aplicava **uma única transformação global** por eixo de comparação. O motor atual
acrescenta rotação fina no estágio global e um refino por elemento com garantia de nunca
piorar, descrito em [Vision Proposals](VISION_PROPOSALS.md); comparar números entre as
duas versões exige reexecutar o comando sobre os mesmos artefatos, que é barato porque não
há nova chamada paga. A decisão de roteamento acima não depende dessa diferença: o Sonnet
reprovou por elementos sem tinta nenhuma, que refino nenhum recupera.

## Eval comparativa executada (medição, prancha sintética, 2026-08-13)

Primeira eval paga do contexto de medição, autorizada pelo usuário (teto US$ 1,50 para a
rodada sintética), sobre a prancha sintética via `croquitodxf-valuation extraction-eval
--arm`, API direta da Anthropic. Cobre as duas tarefas novas: `legend-extraction`
(visão) e `sco-refinement` (a primeira tarefa de texto puro do repositório).

| Arm | Modelo | Recall legenda | Quantidade | SCO top-1 (lexical → refinado) | Resultado | Custo real |
|---|---|---|---|---|---|---|
| sonnet | `claude-sonnet-5` | 1,0 | 1,0 | 0,8 → **1,0** | ✅ | ≈ US$ 0,05 |
| opus | `claude-opus-5` | — | — | — | ❌ | ≈ US$ 0,55 (descartado) |

O Opus reprovou duas vezes. A primeira rodada foi invalidada por defeito **nosso** de
contrato — o schema permitia flags sem limite de tamanho e a nota composta do domínio
estourava o teto de 300; corrigido em `sco-refinement@1.0.1` (limite de 120 por flag,
nota do domínio comporta o pior caso do contrato por aritmética). A segunda rodada, já
sob o contrato corrigido, reprovou por violação real: a resposta devolveu quatro códigos
para uma shortlist de três, com um código duplicado, e o domínio recusou com
`REFINEMENT_CODES_MISMATCH` — refino é permutação exata da shortlist, e conformidade de
schema é gate. Não houve terceira rodada: eval não repete chamada para buscar resultado
melhor, e a segunda rodada foi a primeira tentativa justa do Opus.

Decisão de roteamento: **Sonnet é o modelo das duas tarefas de medição**
(`legend-extraction` e `sco-refinement`) para a rodada real da Toca — o inverso da
extração de geometria, onde o Opus venceu; tarefas diferentes, gates diferentes.
Custo real total da rodada ≈ US$ 0,60–0,70, dentro do teto autorizado.

Rollback: nenhum estado novo a desligar. Sem `--refine-arm`, `suggest-codes` publica a
shortlist lexical determinística (fallback permanente do produto); sem
`extract-legend-real`, o takeoff continua nascendo da fixture sintética ou de transcrição
manual. Comando pago que falha recusa fechado e não publica artefato.

Nota operacional da rodada: o Python gerenciado pelo `uv` neste macOS não encontra os
certificados CA do sistema e o adapter traduz a falha de TLS em `TIMEOUT`; com retries,
isso consome teto estimado sem gastar nada. Antes de qualquer comando pago, exportar
`SSL_CERT_FILE` apontando para o bundle do `certifi` — o runbook
[RUNBOOK_VALUATION_TOCA_ACCEPTANCE](../operations/RUNBOOK_VALUATION_TOCA_ACCEPTANCE.md)
registra o sintoma e os valores recomendados de reserva por chamada.

## Eval comparativa executada (contrato de arco `geometry-extraction@2.0.0`, 2026-08-13)

Eval de **contrato** (schema novo × schema antigo, mesmo modelo `claude-opus-5` via API
direta), autorizada pelo usuário (teto US$ 1,00 na env, ok de gasto renovado a cada
lote de chamadas). Candidato: arco com três pontos-âncora observáveis
(`arc_start`/`arc_mid`/`arc_end`), abertura deixando de ser fabricada 0..π. Baselines:
artefatos v1 já pagos de `golden-guaxindiba-v1` e `golden-raul-v1`, ambos reexecutados
com o motor de registro atual antes da comparação (obrigação da seção da Toca acima).

A primeira chamada do candidato reprovou com `INVALID_SCHEMA` e o diagnóstico (payload
bruto preservado em `output/extraction-eval-arc-v2/`) mostrou defeito **nosso** de
contrato, no mesmo padrão do `sco-refinement@1.0.1`: o Opus reportou as três âncoras das
duas meias-luas e omitiu `center`/`radius` — a resposta mais honesta possível, já que
três pontos determinam o círculo — e o validador exigia o par. O contrato foi corrigido
ainda como candidato (arco aceita o par OU as três âncoras; centro e raio derivados do
circuncírculo em pixels; colineares descartam o elemento) e o candidato revisado rodou
uma única vez por imagem:

| Imagem | Métrica | v1 (fabricado) | v2 (observado) |
|---|---|---|---|
| Guaxindiba | coverage_raw meia-lua esq./dir. | 0,0 / 0,0 | **0,163 / 0,283** |
| Guaxindiba | orientation_delta esq./dir. | −104° / +73° | **0° / −7°** |
| Guaxindiba | cobertura refinada das meias-luas | 1,0 (reconquista) | 1,0 (lapidação ±15°) |
| Guaxindiba | corroboração pós-registro | 1,0 (20/20) | 0,952 (20/21)¹ |
| Raul | corroboração pós-registro | 0,944 (17/18) | 0,938 (15/16)¹ |
| Raul | arcos emitidos | 0 | 0² |

¹ Diferenças agregadas na granularidade de 1 elemento com conjuntos de elementos
diferentes entre execuções (variância conhecida do modelo por folha); no Guaxindiba o
não corroborado do v2 é a faixa vegetativa hachurada, sem relação com arco.
² Hipótese secundária **não confirmada**: nomear âncoras no prompt não aumentou a
propensão do Opus a emitir `kind="arc"` no contorno orgânico do Raul — o caminho curvo
continuou vindo como contorno, e uma polilinha reconhecida como arco pelo refino seguiu
o caminho de reconquista (0,171 → 1,0 com −61°), que permanece intacto.

Decisão: **contrato @2.0.0 aprovado e promovido** — âncoras observadas põem o arco na
tinta antes de registro e transformam o refino de orientação em lapidação (janela ±15°),
com 0% de omissão onde houve arco. Custo real da rodada: 4 chamadas (2 perdidas no
defeito de contrato + diagnóstico, 2 do candidato revisado), ≈ US$ 0,45–0,60 total.
Rollback: reverter o commit de contrato/prompt (saída v1 valida sob o schema v2 — campo
aditivo-opcional; artefatos v2 são auto-descritos pelo `prompt_version` no lineage);
`CROQUITODXF_REAL_PROVIDERS_ENABLED=false` segue sendo o kill switch do caminho pago.

## Embeddings para retrieval de código SCO (M7, 2026-08-13)

O matcher de código do contexto de medição usa retrieval híbrido
([ADR-0021](../adr/0021-hybrid-sco-code-retrieval.md)): braço léxico (cobertura da
consulta ponderada por IDF sobre radicais + sinônimos como dado) fundido por RRF com
braço semântico — embeddings OpenAI `text-embedding-3-small` (env
`CROQUITODXF_EMBEDDINGS_MODEL` para trocar), índice local por catálogo amarrado por
digest e receita de texto, kNN em numpy. Custos reais medidos: índice de 4.964 itens
≈ US$ 0,007 (uma vez por versão de catálogo); consulta por rótulo ≈ desprezível, com
cache por rodada.

Medições que fixaram a configuração (golden real da Toca, 12 casos):

| Configuração | recall@20 |
|---|---|
| Léxico Fase 1 (radicais + sinônimos, Dice) | 4/12 |
| Híbrido (cobertura simples + RRF, profundidade 50) | 8/12 |
| + IDF no braço léxico | 11/12 |
| + oráculo por família nos casos de variante indiscriminável pelo rótulo | **12/12** |

Receita de texto do índice também foi medida: embeddar sem o prefixo de código piorou
(8/12) e foi descartada — a tabela vive em `INDEX_TEXT_RECIPE_MEASUREMENT`
(`sco_matching.py`) e a receita é amarrada no índice (`INDEX_TEXT_RECIPE_MISMATCH`
recusa carga divergente). Profundidade de braço 50 é ótimo medido antes e depois do
IDF (curva na docstring de `HYBRID_ARM_DEPTH`).

Rollback: sem chave/teto/índice, busca e shortlist degradam para o léxico funcional com
o motivo declarado (`matching: lexical` + aviso no `/state`); nenhum estado novo a
desligar. Embeddings não têm prompt — o lineage é modelo + contagem + digest do lote
([Prompt Contracts](PROMPT_CONTRACTS.md) não se aplica a esta chamada).

## Critérios para trocar modelo

Nova versão só substitui a atual quando:

- Passa schema compliance.
- Não piora false-confident errors.
- Mantém ou melhora cotas e associações nos golden cases.
- Custo/latência estão documentados.
- Existe rollback de configuração.
- [Prompt Change Protocol](PROMPT_CHANGE_PROTOCOL.md) foi seguido.

## Residência e privacidade

O MVP usa processamento global controlado. Enviar somente pixels necessários e
identificadores opacos. Nenhum prompt inclui tenant, nome de pessoa, bucket ou URL
persistente.
