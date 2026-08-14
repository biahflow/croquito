# ADR-0021: Retrieval híbrido local para sugestão de código SCO

Status: Accepted  
Data: 2026-08-13  
Responsável: Product / Engineering

## Contexto

A homologação real da medição (Campo do Toca) mostrou que o casamento item→código é o
coração do valor do produto e que o sugeridor puramente lexical não sustenta o
requisito fixado pelo usuário: *código existente no SCO não pode deixar de aparecer
como candidato*. Medido no catálogo real (4.964 itens): o léxico da Fase 1 (radicais +
sinônimos) coloca só 4 de 12 códigos esperados no top-20 — o Dice penaliza descrições
longas, e vocabulário de campo ("REFLETOR") não alcança a família certa ("Projetor…")
por letra.

O catálogo SCO é **dado público** (tabela de preços de referência publicada pela
prefeitura); os rótulos de consulta são nomes genéricos de serviço vindos da legenda da
prancha, sob o consentimento da rodada (upload). O contexto é local-first
([ADR-0020](0020-local-homologation-server-for-valuation.md)): 4.964 itens cabem em
memória; não há banco.

## Decisão

A sugestão e a busca de código usam **retrieval híbrido com fusão de ranking**, tudo
local e determinístico dado o índice:

- **Braço léxico**: cobertura da consulta ponderada por IDF sobre radicais expandidos
  por sinônimos de domínio (sinônimos são **dado** versionado e curável pela
  orçamentista, com expansão declarada no resultado). Palavras de ESTADO da legenda
  ("existente", "a ser recuperar") têm o peso **amortecido** — nunca removido — pela
  lista de ruído de legenda, também dado versionado (`sco-legend-noise-v1.json`,
  rodada 2.2): sem o amortecimento, metade do top-20 de "REFLETOR EXISTENTE" era item
  cujo único mérito é conter "existente" (junk-share medido 10/20 → 0/20).
- **Braço semântico**: embeddings do catálogo (`text-embedding-3-small`, uma chamada
  em lote por versão de catálogo ≈ US$ 0,007; índice local `catalog-embeddings.json`
  amarrado por `catalog_sha256` **e** pela receita do texto embeddado
  (`text_recipe`) — índice de outro catálogo ou de outra receita é recusado) + kNN por
  cosseno em numpy; consultas por rótulo com cache na rodada.
- **Fusão**: Reciprocal Rank Fusion com constantes nomeadas e calibradas por varredura
  registrada (profundidade de braço 50; curva medida em docstring).
- **Garantia por eval, não por promessa**: golden set versionado
  (`matcher-golden-v1.json`, rótulos reais da Toca + gabarito sintético) com gate
  `recall@20 = 100%`, pisos ratchet de top-1/top-3 calibrados sobre o medido (só sobem)
  e, nos casos com termo de ruído, gate de composição do top-20 (`hybrid_junk_max`).
  Casos cuja variante não é discriminável pelo rótulo (altura do
  alambrado, refletor halógeno × projetor) têm oráculo por **família** de códigos com
  `family_reason` — o matcher responde pela família; a variante é decisão humana com a
  prancha (`human_choice: true`).
- **Fallback permanente e declarado**: sem chave/teto/índice, tudo degrada para o
  léxico funcional, com o motivo visível (`/state`, `matching: lexical`). Nenhuma tela
  quebra por indisponibilidade de IA.
- Embeddings **nunca confirmam nada**: ordenam candidatos com `origin` e scores
  declarados; confirmar código continua ato humano rastreável; o refino pago do M5
  continua apenas reordenando shortlists.

## Alternativas

- **Só melhorar o léxico** — medido: teto de 9/12 no golden real mesmo com IDF; o vão
  semântico ("refletor"→"projetor") não fecha por letra.
- **RAG completo (LLM responde o código)** — rejeitado: a metade "geração" já existe na
  forma auditável certa (shortlist + confirmação humana); gerar resposta esconderia a
  incerteza que o produto faz questão de mostrar.
- **Postgres/pgvector** — desnecessário na escala local (kNN brute-force < 10 ms);
  reavaliar na sessão autenticada SaaS sem mudar o contrato do matcher.
- **Embeddings locais (sentence-transformers)** — rejeitado nesta fase: dependência
  pesada com download de modelo, contra a política de dependências; o custo do serviço
  gerenciado é da ordem de centavos com o mesmo teto de gasto da casa.
- **Sinal de abstenção "possível aditivo" por limiar de evidência** — medido e
  descartado (rodada 2.2): sobre os 15 rótulos reais, as distribuições de cobertura,
  cosseno e evidência-não-coberta dos 3 aditivos e dos 12 com código se sobrepõem por
  completo (um aditivo tem cobertura 1.000; "MESA COM 03 BANCOS" é gêmea métrica da de
  04 bancos). Aditivo é condição **contratual** (fora do escopo SCO da licitação), não
  distância de retrieval — mesmo limite de evidência do oráculo por família; a decisão
  segue humana via `confirm-codes` fail-closed. Medição completa em
  `matcher-golden-v1.json` (`note_abstention_measurement`).

## Consequências

### Positivas

- O requisito "não perder código existente" vira regressão automatizada (gate de
  recall) sobre casos reais medidos, com ranks registrados por braço.
- Vocabulário de campo entra como dado curável (sinônimos), não como código.
- Custo marginal por rodada ≈ zero (índice reutilizado por digest; consultas em cache).

### Negativas

- Dependência de provider externo para *qualidade máxima* da busca (mitigada pelo
  fallback léxico funcional e declarado).
- Índice de 40 MB por catálogo em disco local (aceito; artefato derivado e
  reconstruível).
- A lista de ruído de legenda amortece, não remove: rótulo composto só de palavras de
  estado ainda depende do braço semântico; termo novo na lista só entra com melhora
  medida no golden (a primeira calibração, por rank do alvo, não viu o ganho — foi a
  métrica de composição do top-20 que o revelou; lição registrada em `note_phase_2_2`).

## Riscos e mitigação

- **Deriva do índice vs catálogo** — digest + receita amarrados; carga recusa
  divergência.
- **Regressão silenciosa de qualidade** — golden gate no CI (parte sintética) e
  local-only (parte real, skipif sem o catálogo), com ranks fixados que não podem
  piorar sem o teste acusar.
- **Custo fora de controle** — mesma disciplina da casa: `CostBudget` com teto por env
  em toda chamada; sem teto, recusa limpa.
