# ADR-0060: O acervo de parcelas de canteiro é receita publicada na plataforma, com autoria de tenant sobre ela

Status: Accepted  
Data: 2026-08-28 (aceito por ato humano em 2026-08-28, Daniel Campos)  
Responsável: Product / Engineering

## Contexto

A [F-042](../features/F-042-acervo-de-parcelas-de-canteiro/feature.md) mede que **24 das 43
linhas preenchidas** do orçamento real do Campo do Toca não têm origem nenhuma na prancha:
canteiro, mão de obra, andaime, transporte e entulho. São 56% do preenchimento, hoje digitado
uma linha por vez, a cada praça.

O modelo do domínio já sabe o que essas linhas são: `ContributionBasis.STANDALONE`
(`packages/valuation/src/croquito_valuation/models.py:250-252`) está definido como "não tem
origem geométrica: canteiro e administração (placa, container, vigia)". O que falta não é
modelagem — é o **acervo**. Uma varredura por `STANDALONE` fora de `models.py`/`calc_matrix.py`
acha apenas testes, o ADR-0053 e o tipo gerado: não existe seed, tabela nem rota, e toda
contribuição é autorada do zero por rodada (`CalcContribution` não tem id, chave nem versão).

O unknown 1 da feature pergunta **onde esse acervo vive**, e nomeia três candidatos com donos
e retenções diferentes. Os três já têm precedente no repositório:

| Molde | Exemplo no repo | Dono | Autorável em runtime? |
|---|---|---|---|
| Seed empacotado com o pacote Python | `haulage.py` + `data/sco-haulage-v1.json` (`haulage.py:141-148`) | o repositório | não — exige deploy |
| Artefato de plataforma publicado em runtime | `ReferenceCatalogRecord` (`services/api/src/croquito_api/database.py:220-247`), **a primeira tabela do projeto sem `tenant_id`** (ADR-0047) | o operador de plataforma | sim, por `platform_operator` |
| Dado do tenant | qualquer tabela com `tenant_id` | o cliente | sim, pelo próprio cliente |

A escolha não é livre, porque o escopo da feature exige **duas coisas ao mesmo tempo**:

1. um acervo versionado, com identidade estável, no molde de `haulage.py` (escopo 1);
2. um caminho para a **orçamentista** salvar as parcelas `STANDALONE` de uma rodada já feita
   como acervo novo ou versão nova (escopo 5).

O item 2 elimina o seed empacotado como regime **único**: exigir deploy do repositório para a
orçamentista guardar o próprio acervo transformaria uma tarefa de trabalho em uma tarefa de
engenharia. E o item 1, combinado com a natureza do dado, empurra contra o tenant puro: uma
parcela de canteiro é **receita** — "banheiro químico = 1 × prazo em meses" —, não medida da
obra e não dado do cliente.

Mas há uma tensão real que o unknown não nomeia: o acervo **autorado a partir de uma rodada
do cliente** não é receita pura. Ele nasce das escolhas daquele cliente naquele contrato — os
códigos que ele usa, os rótulos que ele escreve, o desenho de canteiro que ele pratica. Tratar
isso como artefato de plataforma publicaria a prática de um cliente para todos os outros.

## Decisão

O acervo de parcelas de canteiro tem **duas origens, um contrato de leitura só**.

1. **Acervo de plataforma.** Publicado em runtime por `platform_operator`, no molde do acervo
   de catálogos da F-037: sem `tenant_id`, imutável, endereçado por versão. É o acervo
   curado, distribuído a quem contrata, e é onde vive o acervo padrão de um contrato público.

2. **Acervo do tenant.** Gravado pela própria orçamentista a partir de uma rodada já feita
   (escopo 5 da feature), com `tenant_id`, visível só para o tenant que o autorou. É o
   caminho normal de autoria, e é o único que a jornada do orçamento oferece.

3. **Um único contrato de leitura.** As duas origens produzem o mesmo `SiteSetupKit`, e a
   aplicação não sabe de onde ele veio: `apply_site_setup_kit` recebe o acervo, não a fonte
   dele. A rodada registra na proveniência da contribuição a **versão** do acervo aplicado.

4. **Promoção é ato humano de plataforma, nunca automática.** Um acervo de tenant só vira
   acervo de plataforma por publicação explícita de um `platform_operator`, que é quem
   responde por distribuir a prática de um cliente a outros.

5. **Não há seed empacotado no repositório** para o acervo de canteiro. Diferente da tabela de
   transporte de `haulage.py`, que é propriedade do contrato e é a mesma para todos, o acervo
   de canteiro é autorado por gente a partir de uma praça real, e o primeiro deles não existe
   até que alguém o autore. Empacotar um acervo inventado no `data/` seria distribuir dado
   fabricado com aparência de curadoria.

## Consequências

- A F-042 pode entregar o motor e a autoria **sem** depender de um ato de plataforma: a
  orçamentista autora o primeiro acervo do tenant dela a partir do Campo do Toca, e usa.
- O acervo de tenant carrega rótulos e códigos de um cliente e por isso segue a mesma
  fronteira de retenção do resto da rodada. Ele **não** atravessa tenants por acidente: só por
  promoção explícita.
- Duas tabelas, ou uma tabela com `tenant_id` anulável. A escolha é de execução; o que este
  ADR fixa é que a leitura é uma só e que a fronteira de tenant existe.
- O acervo de plataforma herda o desenho já provado da F-037 — imutável, endereçado, retirável
  de circulação —, e não inventa mecanismo novo.
- Um acervo publicado pode citar código que o catálogo de uma rodada não tem. A aplicação
  recusa por extenso nomeando o código (escopo da F-042); este ADR não cria exceção a isso.

## Alternativas consideradas

**A — Só seed empacotado, no molde de `haulage.py`.** Rejeitada: mata o escopo 5 da feature.
A orçamentista não pode abrir um pull request para guardar o acervo dela, e sem autoria em
runtime o acervo envelhece no repositório enquanto a prática muda no escritório.

**B — Só artefato de plataforma.** Rejeitada: a autoria passaria a exigir `platform_operator`,
papel que a orçamentista não tem, e publicaria a prática de um cliente para os demais sem que
ninguém decidisse isso.

**C — Só dado do tenant.** Rejeitada por perder o caso que motiva a feature no médio prazo: um
contrato público com dezenas de praças e vários escritórios quer o mesmo acervo curado, e sob
o regime só-tenant cada um autora o seu, com divergências silenciosas entre eles.

**D — Inferir o acervo automaticamente de rodadas passadas.** Fora de escopo por decisão da
própria feature, e seria a mesma armadilha da F-044: construir sobre uma hipótese de repetição
que ninguém mediu.

## Gate humano

~~Este ADR está `Proposed`~~ — **aceito por ato humano em 2026-08-28** (Daniel Campos),
cumprindo o terceiro Human Gate da
[F-042](../features/F-042-acervo-de-parcelas-de-canteiro/feature.md). A persistência e as
rotas do acervo podem ser construídas. O motor de
domínio (modelo, aplicação, pré-visualização) não depende dele: `apply_site_setup_kit` é puro
e não sabe onde o acervo mora.

## Emenda 1 (2026-09-04): a proveniência carrega a identidade, não só a versão

Status da emenda: Proposed — aguardando aceite humano.

A decisão 3 mandou a rodada registrar "a **versão** do acervo aplicado" na proveniência da
contribuição, e a execução a seguiu ao pé da letra: `SiteSetupOrigin` guarda `kit_version`
e o merge do apply desduplica **por versão**. O plano da F-042 declarou a consequência como
risco desde 2026-08-28: **dois acervos diferentes que declarem a mesma versão são
indistinguíveis na matriz** — e com as duas origens da decisão (plataforma e tenant), duas
linhagens independentes chamarem sua primeira versão de `v1` não é acidente, é o caso
esperado.

O dono decidiu corrigir em 2026-09-04, antes que o primeiro acervo real exista (o Human
Gate 4 da F-042 ainda não foi exercido — não há dado gravado a migrar).

1. **`SiteSetupOrigin` passa a carregar `kit_id`** ao lado de `kit_version`: a identidade
   do acervo aplicado, não só o rótulo de versão dele. `kit_id` é o identificador imutável
   do registro publicado/autorado — o mesmo que as rotas já devolvem.
2. **O merge do apply desduplica por `(kit_id, kit_version)`**, nunca mais por versão
   sozinha. Reaplicar o mesmo acervo continua idempotente; aplicar OUTRO acervo que por
   coincidência chama sua versão igual deixa de colidir.
3. **Proveniência antiga não é reescrita.** `kit_id` nasce opcional no contrato
   (`None` = "não observado", gravado antes desta emenda); nenhuma rodada existente é
   migrada nem reinterpretada. Como não existe acervo real aplicado até hoje, o caso
   `None` é teórico — mas o contrato o declara em vez de fingir que o passado registrou o
   que não registrou.
4. **Nada mais muda**: as duas origens, o contrato de leitura único e a promoção por ato
   humano seguem como decididos. A emenda conserta a chave da proveniência, não o desenho.
