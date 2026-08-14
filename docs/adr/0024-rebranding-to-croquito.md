# ADR-0024: Rebranding croquiToDXF → croquito

Status: Accepted  
Data: 2026-08-14  
Responsável: Product / Engineering

## Contexto

O nome de trabalho do produto era **croquiToDXF** — descritivo do primeiro caminho
implementado (croqui em papel → DXF auditado) e estreito demais para o que o repositório
já faz. O contexto de medição de obra (`packages/valuation`, `apps/medicao`) entrega
planilha de medição, não DXF, e é hoje metade do produto. O nome novo é **croquito**.

Um rebranding costuma ser cosmético. Este não é: o token do produto está gravado em
identificadores que participam de contratos, de identidade de dado e de saída de arquivo.
Trocá-los muda comportamento observável e precisa ser declarado, não escorregado dentro
de um commit de renomeação.

Os pontos com consequência real:

- **`APP_ID` do XDATA no DXF** (`dxf.py`), que é o registro de aplicação gravado dentro
  de cada arquivo exportado e documentado no
  [DXF Output Spec](../architecture/DXF_OUTPUT_SPEC.md).
- **Cabeçalho de todo template de prompt** (`providers.py`), que compõe o
  `template_hash` — a identidade do prompt no lineage já gravado.
- **Sementes de `uuid5`** do solver retangular e do traçado, que derivam ids
  determinísticos de cena e entidade.
- **Prefixo de variável de ambiente** `CROQUITODXF_`, que é a interface de configuração
  de todo processo local e do futuro deploy.

## Decisão

O produto passa a se chamar **croquito**, e o rename atinge todo o token contíguo
(`croquitodxf`, `CROQUITODXF`, `CroquiToDXF`, escopo npm `@croquitodxf`) em código,
infraestrutura local, documentação e artefatos gerados. O substantivo comum "croqui"
permanece intocado — ele descreve o desenho, não o produto.

Quatro consequências de identidade são assumidas explicitamente:

1. **`APP_ID` do XDATA passa de `CROQUITODXF` para `CROQUITO`.** É mudança de formato de
   saída: um DXF exportado a partir daqui declara outro registro de aplicação. DXFs já
   entregues continuam válidos e legíveis; o que muda é que uma ferramenta que filtrasse
   XDATA pelo APP_ID antigo não encontra o novo. Nenhum consumidor externo depende disso
   hoje (o único DXF real aberto no AutoCAD foi lido por humano, não por script).
2. **Todas as nove tarefas de prompt recebem bump de PATCH**, porque o cabeçalho do
   template mudou (`croquitodxf:<task>@<versão>` → `croquito:<task>@<versão>`) e com ele o
   `template_hash`. Texto novo exige versão nova: `page-survey`, `measurement-extraction`,
   `semantic-elements`, `disagreement-review` e `ocr` vão a `1.1.1`;
   `geometry-extraction` a `2.0.1`; `legend-extraction` a `1.0.1`; `sco-refinement` a
   `1.0.2`; `review-chat` a `1.0.1`. Nenhuma instrução e nenhum schema de saída mudaram —
   por isso PATCH, e por isso **não há eval comparativa nova**: não há hipótese de
   comportamento diferente a testar, e gastar em provider pago para reconfirmar um texto
   idêntico seria desperdício. Os hashes congelados em
   `tests/worker/test_providers.py` foram **recomputados pelo código real**, nunca
   escritos à mão.
3. **O lineage histórico continua válido e não é reescrito.** As evals pagas já
   executadas (Toca e Guaxindiba, `geometry-extraction@2.0.0`; eval sintética do M5,
   `legend-extraction@1.0.0` e `sco-refinement@1.0.1`) descrevem exatamente o que foi
   enviado, sob o nome que o produto tinha. Nenhum artefato gravado é migrado.
4. **Os ids determinísticos de `uuid5` mudam para as mesmas entradas**, porque a semente
   carrega o token (`croquitodxf:` → `croquito:`). Cena e entidade regeradas a partir da
   mesma evidência recebem ids novos. Isso não invalida artefato publicado — id de cena
   viaja dentro do artefato, não é recalculado por quem o lê — mas um golden que fixasse
   UUID precisaria ser regenerado.

Complementarmente: prefixo de env `CROQUITO_`, entry points `croquito-demo` e
`croquito-valuation`, pacotes Python `croquito_{core,valuation,api,worker}`, escopo npm
`@croquito/*`, prefixo de `sessionStorage` `croquito:`, artefato ZIP `croquito.zip`,
realm/cliente Keycloak `croquito`/`croquito-web`, recursos LocalStack `croquito-local-*`
e `project_name` do Terraform `croquito`.

**Nada de identidade visual muda neste ADR**: paleta, tipografia, logo, favicon e layout
seguem como estavam. Marca visual é entrega separada.

## Alternativas

- **Manter `APP_ID = "CROQUITODXF"` e as versões de prompt, renomeando só o resto.**
  Evitaria mudança de formato de saída e recongelamento de hash, ao custo de deixar o
  nome antigo gravado dentro de cada DXF entregue e no cabeçalho de cada prompt enviado —
  exatamente os dois lugares onde o nome é lido por terceiros. Rejeitada: um rebranding
  que não alcança a saída não é um rebranding, é uma renomeação de variáveis.
- **Bump de MINOR ou MAJOR nos prompts.** MAJOR significa schema ou semântica
  incompatível e MINOR significa capacidade nova ([Prompt
  Contracts](../ai/PROMPT_CONTRACTS.md)); nenhum dos dois aconteceu. PATCH é o degrau
  honesto para "o texto mudou sem mudar o que se pede".
- **Manter as versões de prompt e apenas recongelar os hashes.** Seria o único caminho
  que reescreve proveniência: dois textos diferentes passariam a responder pelo mesmo
  `<task>@<versão>`, e um lineage gravado deixaria de descrever o prompt que o produziu.
  Rejeitada por violar o ADR-0010.
- **Renomear o diretório de trabalho e o repositório remoto no mesmo passo.** Fora de
  escopo aqui; o repositório local segue em `croquiToDXF` até que a movimentação seja
  feita deliberadamente, e nada no código depende do nome da pasta.

## Consequências

### Positivas

- O nome do produto deixa de prometer só DXF, o que já não descrevia metade do
  repositório (medição de obra).
- A identidade de prompt volta a ser verdadeira: cada `<task>@<versão>` corresponde a um
  único texto, e o `template_hash` continua sendo prova disso.
- Um só token em todo o repositório: `grep -ri croquitodxf` vazio é o gate permanente
  contra rename pela metade.

### Negativas

- DXF gerado a partir daqui declara `CROQUITO` no XDATA; um consumidor que filtrasse pelo
  APP_ID antigo precisaria ser ajustado (nenhum existe hoje).
- Ambiente local precisa ser reprovisionado: o banco, o bucket, as filas, o secret, a
  state machine e o realm têm nomes novos. `make down-services && make dev-services &&
  make db-init` recria tudo; dado local antigo não é migrado.
- `.env.local` fora do Git precisa do prefixo novo em cada máquina — sem isso a
  configuração cai silenciosamente no default.
- A `sco-refinement@1.0.2` foi consumida por este patch; a dica de tamanho de `rationale`
  cogitada em 2026-08-13 nasce na `1.0.3`.

## Riscos e mitigação

| Risco | Mitigação |
|---|---|
| Substituir "croqui"/"croquis" (substantivo comum) junto com o token do produto | Replace restrito a token contíguo; contagem de `\bcroquis?\b` conferida antes e depois (101 = 101) |
| Rename pela metade deixando referência morta | `grep -ri croquitodxf` com exclusão de diretórios gerados deve retornar vazio; `make check` e `make test` como portão |
| Hash de prompt inventado à mão no recongelamento | Hashes recomputados executando `PROMPT_SPECS` do módulo real e conferidos pelo teste que os congela |
| Lineage histórico parecer inválido | Registrado aqui e em [Prompt Contracts](../ai/PROMPT_CONTRACTS.md): versão antiga descreve o texto antigo, e nenhum artefato é migrado |
| Golden quebrar por UUID determinístico novo | As quatro evals determinísticas (`demo`, `vision-eval`, `solver-eval`, `valuation-eval`) rodam no mesmo trabalho; golden que dependa de identidade é regenerado pelo procedimento do repositório, nunca contornado |
| Ambiente local subir com nome velho e falhar obscuro | Nomes novos em `docker-compose.local.yml`, `localstack/init/01-bootstrap.sh` e `keycloak/croquito-realm.json`, com o passo de reprovisionamento declarado acima |

## Rollback

Revert do commit de rebranding. Ele é autocontido: código, infra local, docs e arquivos
gerados voltam juntos. Depois do revert é preciso reprovisionar o ambiente local de novo
(`make down-services && make dev-services && make db-init`) e reexecutar `uv sync
--all-groups`, `npm install` e `make contracts`, porque lock files e contratos gerados
fazem parte do commit. Artefatos já publicados não precisam de nada: eles não são lidos
pelo nome do produto.

## Rastreabilidade

- Requirements: relacionado a ADR-0007 (DXF como saída do MVP, formato do XDATA) e
  ADR-0010 (versionamento de prompts, modelos e respostas). Nenhum dos dois é
  substituído — este ADR aplica a regra do ADR-0010 a uma mudança de texto de template.
- Supersedes: none
- Superseded by: none
