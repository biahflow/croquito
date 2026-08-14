# Revisão de cotas e solver retangular

Status: Implemented for synthetic fixture; real golden pending domain approval  
Responsável: AI Engineering / Geometry / Domain Reviewer  
Última revisão: 2026-08-10

## Objetivo

Transformar transcrições propostas em constraints métricos somente depois de uma
decisão humana rastreável. Este estágio liga cada leitura a um recorte da imagem,
preserva o texto original e impede que pixels ou scores definam escala.

## Contratos implementados

`ReviewPacket` contém:

- digest SHA-256 da imagem renderizada, página e dataset lógico;
- `bbox` em pixels da evidência;
- `raw_text`, valor SI, unidade, casas escritas e alvo sugerido;
- extractor e versão;
- estado `proposed`, `ambiguous`, `confirmed` ou `rejected`;
- `HumanDecision` obrigatório para `confirmed` e `rejected`.

Uma leitura `confirmed` sem `decision_id`, revisor, papel e data é inválida no
schema. `quality_score`, consenso de modelos ou legibilidade visual nunca mudam o
estado automaticamente.

## Solver retangular v1

O solver aceita a família controlada `campo retangular`:

- largura e altura confirmadas;
- quatro bordas ortogonais;
- linha central derivada opcional;
- círculo central quando raio ou diâmetro foi confirmado;
- cotas DXF e medidas canônicas;
- resíduos numéricos com tolerância derivada das casas escritas.

Se faltar confirmação, o resultado é `review_required` e não contém cena métrica.
Um círculo maior que o campo produz `conflict` e issue crítica. O solver não usa
proporção da imagem para preencher valores.

Mesmo uma solução sem conflito nasce como `solved_unapproved`. A exportação exige
um `SceneApproval` que:

- aponta para o UUID exato da revisão rascunho;
- registra revisor profissional, papel e timestamp;
- confirma revisão da evidência, geometria e limitações;
- cria uma nova revisão aprovada, sem alterar o rascunho;
- entra como `aprovacao.json` no pacote CAD.

## CLI local

```bash
uv run croquito-demo review-artifacts \
  --packet /caminho/review-input.json \
  --image /caminho/page-001.png \
  --output output/review

uv run croquito-demo apply-review \
  --packet output/review/review-packet.json \
  --decisions /caminho/decisoes.json \
  --image /caminho/page-001.png \
  --output output/review-confirmado

uv run croquito-demo solve-rectangle \
  --packet output/review/review-packet.json \
  --request /caminho/rectangle-request.json \
  --associations /caminho/associacoes-confirmadas.json \
  --output output/review

uv run croquito-demo rectangle-export \
  --solve-result output/review/solve-result.json \
  --approval /caminho/aprovacao.json \
  --output output/export
```

`solve-rectangle` retorna código `2` enquanto houver revisão pendente. Isso é uma
falha segura esperada, não erro de infraestrutura.

`apply-review` não altera o pacote de entrada. Ele preserva a proposta original,
requer revisor, papel e timestamp com timezone, e recusa sobrescrever uma decisão
já confirmada ou rejeitada. Um arquivo de decisões contém somente as leituras que
o revisor quer decidir:

```json
{
  "decisions": [
    {
      "reading_id": "rd_...",
      "action": "confirm",
      "reviewer_id": "registro-do-revisor",
      "reviewer_role": "engineer",
      "decided_at": "2026-08-10T12:00:00-03:00",
      "raw_text": "25,90 m",
      "value_si": "25.90",
      "unit": "m",
      "kind": "width",
      "written_decimals": 2,
      "target_hint": "largura do campo principal"
    }
  ]
}
```

## Sessão autenticada e associação explícita

Na API de produção, o pacote e cada revisão derivada são persistidos por job e
tenant, incluindo candidatos observacionais, digest de evidência e referências a
previews privados. A decisão HTTP não recebe `reviewer_id`, `reviewer_role` nem
`decided_at`; a API os deriva exclusivamente do JWT validado e do relógio do
servidor. Papel não elegível falha fechado.

Uma confirmação também registra um `proposal_id` candidato daquela leitura. O
solver recebe esse mapa de associações explícitas como provenance, mas nunca usa
distância, pixels ou score para calcular dimensão. Se qualquer leitura da família
retangular não tiver decisão humana ou associação, retorna
`EXPLICIT_ASSOCIATION_REQUIRED`/`HUMAN_CONFIRMATION_REQUIRED` e não cria cena
métrica. Ao resolver, a `SceneRevision` é nova e não aprovada; o worker/API anexa
issues críticas para requisitos do caso ainda ausentes, portanto o primeiro
rascunho parcial do Guaxindiba não é exportável sem reconhecimento explícito.

O pacote autorizado entra na sessão por `croquito-demo seed-review`, que liga packet,
associações, propostas e `RectangleSolveRequest` a um job existente. O comando recusa
divergência entre o pacote e o upload do tenant, recusa pacote que já traga decisão
humana e nunca sobrescreve uma revisão existente.

Uma nova decisão de leitura re-executa o solver, e a cena resultante **preserva** as
entidades `approximate` que o profissional aceitou a partir de propostas calibradas. A
calibração é revalidada contra a nova cena: se os anchors desaparecerem ou o transform
divergir além da tolerância nomeada, a calibração é descartada e a cena recebe
`CALIBRATION_SUPERSEDED` como issue crítica. A geometria aceita permanece intacta e
bloqueada até nova calibração — o sistema não reprojeta em silêncio geometria que um
humano aprovou.

## Avaliação executável

```bash
make solver-eval
```

A fixture verifica que:

1. a cena rascunho não exporta antes da aprovação;
2. a aprovação aponta para a revisão correta e cria outra revisão;
3. largura, altura e raio são preservados sem resíduo;
4. o DXF reabre e passa pela auditoria;
5. `aprovacao.json` está dentro do ZIP.

Essa avaliação mede o mecanismo, não a leitura dos PDFs reais.

## Estado do Guaxindiba

O pacote local ignorado pelo Git possui três propostas de revisão:

- cotas globais propostas a partir da anotação `25,90 × 21,75`;
- círculo central marcado `ambiguous`;
- três blockers de confirmação humana.

Nenhum DXF real foi criado. O primeiro golden DXF depende da confirmação de um
profissional do domínio e da revisão das demais entidades exigidas nos critérios
`ACC-GUA`.

## Casos médio e difícil

Os mesmos artefatos locais de revisão foram preparados para a Toca e Raul Campelo:

| Caso | Evidência preparada | Estado seguro |
|---|---|---|
| Toca - médio | `55,00`, `84,0` e uma anotação de portão | largura proposta; altura e associação bloqueadas |
| Raul - difícil | `14,90`, `9,20` na pérgola e `9,60` no patamar circular | contorno orgânico, semântica de cotas e equipamentos bloqueados |

Os três casos permanecem em artefatos privados de revisão. O shell web não traz
esses casos no bundle: após autenticação, ele mostra somente o snapshot retornado
pela API para um job do tenant e mantém DXF bloqueado até aprovação profissional.
