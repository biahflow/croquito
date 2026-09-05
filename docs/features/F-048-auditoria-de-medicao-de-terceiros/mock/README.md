# Design Approval Package — F-048, auditoria de medição de terceiros

Classification: INTERFACE_CHANGE  
Revision: 1  
Status: **Approved — revisão 1 (2026-09-05)**  
Date: 2026-09-05  
Produced by: agente (Claude Code)

> Governado por [design-approval](../../../engineering-os/workflows/design-approval.md). Este
> artefato é evidência para um gate humano. Não é implementação e não deve ser copiado para
> código de aplicação. **Nenhum agente aprova design.**

## O gate que vem antes deste

O [Feature Contract](../feature.md) registra dois `Human Gates` além deste pacote: a seleção e
prioridade da feature (já decidida, `HIGH`), e o **unknown 2** — se a auditoria vira produto
avulso ou parte da jornada de medição.

O unknown 2 **já foi decidido pelo dono em 2026-09-05, e não é reaberto aqui**: a auditoria é
**produto avulso** — jornada própria, sem exigir projeto, prancha, contrato ou rodada no
croquito. Quem entra pode não ser cliente ainda. Esse é o desenho que este pacote assume; se a
decisão mudar, o pacote muda com ela.

Não há ADR atrás deste gate: os três motores que a rota vai reusar
(`compare_bulletin`, a paridade de fórmula e `diagnose_contract`) já existem, já são
determinísticos e não mudam de comportamento por causa deste pacote — a acceptance criterion 4
da feature exige explicitamente que os goldens deles sigam byte-idênticos.

## Registro de aprovação

| Campo | Valor |
| --- | --- |
| O que se aprova | a composição dos seis estados e as seis decisões abaixo |
| Aprovado por | Daniel Campos |
| Data | 2026-09-05 |
| Revisão | 1 |
| Explicitamente **não** aprovado | a copy final; os números, rótulos, arquivos e códigos das capturas, que são sintéticos; corrigir a medição alheia (fora do escopo do contrato); a decisão de preço/empacotamento comercial da jornada |

Aprovação desta revisão não aprova uma revisão seguinte. Pacote materialmente alterado é
revisão nova e precisa de registro próprio.

## Artefato

| Arquivo | O que é |
| --- | --- |
| [`auditoria-de-medicao.html`](auditoria-de-medicao.html) | A rendição autocontida. Abre no navegador sem build, sem rede e sem servidor. |
| [`00-pagina-inteira.png`](00-pagina-inteira.png) | Os seis estados numa imagem |
| [`01.png`](01.png) | Vazio, com convite: o que a jornada faz e qual arquivo aceita |
| [`02.png`](02.png) | Em processamento: arquivo e digest à vista, sem barra de progresso |
| [`03.png`](03.png) | Relatório com furos, agrupado por consequência |
| [`04.png`](04.png) | Relatório limpo: zero centavo é resultado, não ausência de resultado |
| [`05.png`](05.png) | Recusa do arquivo, com o motivo por extenso e o que fazer |
| [`06.png`](06.png) | Histórico de auditorias, o que permite reconferir |

## Superfícies e estados incluídos

| Superfície | Estado | No pacote |
| --- | --- | --- |
| Auditoria de medição | vazio, com convite de upload | sim (01) |
| Auditoria de medição | em processamento (arquivo recebido, digest calculado) | sim (02) |
| Relatório da auditoria | com furos — dinheiro que não fecha, linha de um lado só, observação | sim (03) |
| Relatório da auditoria | limpo — `zero_cent` verdadeiro | sim (04) |
| Auditoria de medição | recusa do arquivo (ilegível, fora do layout, aba ausente) | sim (05) — cinco recusas nomeadas |
| Auditoria de medição | histórico de auditorias já feitas | sim (06) |
| Relatório da auditoria | carregando o histórico | **não** — a lista do estado 6 é um `GET` simples, sem espera nova a desenhar |
| Auditoria de medição | não autorizado / sessão expirada | **não** — é a recusa de sessão que o resto do produto já tem hoje; este pacote não a redesenha |

## Proveniência dos valores visuais

| Valor | Origem | Novo? |
| --- | --- | --- |
| `--bg`, `--surface`, `--surface-subtle`, `--surface-sunken`, `--ink`, `--ink-secondary`, `--muted`, `--line` | `apps/web/src/styles.css:24-42` | não |
| `--accent*` do botão primário, do selo "limpo" e do veredito limpo | `apps/web/src/styles.css:24-42` | não |
| `--atencao`, `--atencao-line`, `--atencao-soft` (âmbar do veredito com furos, do selo "furos" e da classe técnica) | `apps/web/src/medicao/styles.css:1726-1728` — o mesmo âmbar que o pacote da F-045 já reaproveitou do aviso de precedente fraco (F-044) | não |
| `--recusa`, `--recusa-ink`, `--recusa-line`, `--recusa-soft` (vermelho do estado 5 e do selo "recusado") | as cores de `.app-alert` (`apps/web/src/styles.css:764-779`), `.decision-error` (`:2224-2229`) e `.identidade-erro` (`:3610-3618`) — quatro nomes novos para os mesmos valores já em uso | não |
| `.digest` (monoespaçada para o hash) | `apps/web/src/medicao/styles.css:1131` e `apps/web/src/orcamento/styles.css:397` | não |
| Inter como família de texto | `apps/web/src/styles.css:47-48` | não |
| **Cor nova** | — | **nenhuma** |

Design system referenciado: `apps/web/src/styles.css`, `apps/web/src/medicao/styles.css` e
`apps/web/src/orcamento/styles.css`, lidos em 2026-09-05. Se este pacote e essa fonte
divergirem, a fonte vence e este pacote está velho.

## Decisões que este pacote carrega

1. **A hierarquia é por CONSEQUÊNCIA, não por origem do achado.** Quem audita de fora não sabe
   o que é `unit_price_diff`; sabe o que é "dinheiro que não fecha". O estado 3 organiza os
   achados em três grupos — dinheiro que não fecha, linha que existe de um lado só, observação
   —, nessa ordem, e a classe técnica (`quantity_diffs`, `unit_price_diffs`,
   `line_total_diffs`, `bulletin_total_diff`, `missing_in_reference`, `missing_in_generated`,
   `unit_notes`) aparece só como rótulo pequeno dentro da linha, nunca como título de seção.

2. **"Fecha centavo a centavo" é primeira classe, não ausência de classe.** O estado 4 usa o
   mesmo componente de veredito (`.veredito`) do estado 3, só trocando a cor de âmbar para
   verde — nenhum dos dois é visualmente menor que o outro. Auditoria limpa é resultado, e o
   documento existe para dizê-lo com todas as letras, junto da contagem do que foi conferido
   ("187 linhas conferidas"), não só da ausência de furo.

3. **O relatório sempre cita o digest do arquivo auditado.** Os estados 2, 3, 4 e 6 mostram o
   digest curto (12 caracteres, o mesmo padrão de `digestCurto`/`shortDigest` já usado nas duas
   jornadas) com o hash inteiro no `title`. Auditoria que não se pode reconferir não vale nada —
   é por isso que o estado 6 (histórico) existe: sem ele, o digest do estado 3 não tem para onde
   apontar de volta.

4. **A tela nunca classifica intenção.** Não existe "suspeito", "fraude" ou "erro de
   digitação" em lugar nenhum do pacote — nem na cor, nem na copy. O que existe é o número: o
   arquivo diz X, a conta dá Y, a diferença é Z reais. Classificar é humano, e o relatório só
   descreve.

5. **Auditar não exige nada do croquito.** Nenhum dos seis estados pede projeto, prancha,
   contrato ou rodada — o convite do estado 1 e o histórico do estado 6 falam só do arquivo e
   de quem o subiu. É o que faz esta jornada alcançar quem ainda não é cliente (decisão do
   dono, unknown 2 da feature).

6. **O relatório é exportável.** Os estados 3 e 4 trazem "Exportar relatório" como ação
   primária, ao lado do veredito — quem audita precisa mandar o resultado adiante; um relatório
   que só existe na tela não serve ao trabalho.

## Questões abertas

- **A copy final** de todos os textos, inclusive as cinco recusas do estado 5.
- **O formato do arquivo exportado** (PDF, xlsx, ambos) — o botão "Exportar relatório" está no
  pacote, o formato não é decisão deste artefato.
- **Se o histórico (estado 6) tem paginação, busca ou filtro** — o pacote mostra quatro linhas
  porque é o que cabe para provar a forma; volume real de uso é decisão de implementação.
- **O limiar entre "acha e mostra tudo" e alguma priorização de severidade dentro de "dinheiro
  que não fecha"** (unknown 1 da feature, "quanto do relatório é compreensível sem contexto da
  obra") — este pacote não introduz gravidade além da ordem dos três grupos.

## Notas para quem implementar

- **Intencional e a preservar**: a ordem fixa dos três grupos do estado 3; o mesmo componente de
  veredito nos estados 3 e 4, só com cor trocada; o digest à vista em todo estado que já tem
  arquivo resolvido; a ausência total de linguagem de intenção/culpa; o botão de exportar ao
  lado do veredito, não escondido.
- **Ilustrativo, e não é especificação**: nomes de arquivo, códigos, descrições de serviço,
  valores em reais, nomes de quem subiu e instantes — tudo sintético, no formato SCO.
- **O que o artefato não mostra**: ordem de foco, comportamento de teclado, leitura por leitor
  de tela, paginação do histórico e o texto de erro vindo da API quando a recusa não é uma das
  cinco nomeadas no estado 5.
- As cinco recusas do estado 5 citam, por trás da copy, os erros reais de
  `packages/valuation/src/croquito_valuation/bulletin_compare.py`:
  `BULLETIN_WORKBOOK_UNREADABLE`, `BULLETIN_SHEET_MISSING`, `BULLETIN_ROW_UNPARSEABLE`,
  `BULLETIN_TOTAL_ROW_MISSING` e `BULLETIN_CELL_NOT_NUMERIC` — a tela traduz por extenso e
  nunca repassa o código cru.
- O estado 3 usa cinco classes de achado nas 5 linhas de "dinheiro que não fecha" (duas de
  `quantity_diffs`, uma de `unit_price_diffs`, uma de `line_total_diffs`, uma de
  `bulletin_total_diff`), três de `missing_in_reference`/`missing_in_generated` e uma de
  `unit_notes` — nomes de classe tirados de
  `packages/valuation/src/croquito_valuation/bulletin_compare.py`, não inventados para a tela.

## Correção de desenho aplicada na revisão (2026-09-05)

A primeira rendição escrevia, no grupo "linha que existe de um lado só", frases do tipo
*"existe na conferência do croquito; não aparece no arquivo enviado"* — e isso
**contradizia a decisão 5 deste mesmo pacote**: no modo avulso não existe conferência do
croquito, porque não há projeto, contrato nem rodada.

A correção fixa o que a auditoria avulsa de fato compara: **as camadas do próprio arquivo do
cliente**. O MAPÃO e o BM são abas do mesmo documento, e é uma contra a outra — além da
fórmula contra o valor em cache, que é o que achou os oito erros de centavo de 2026-08-12 —
que a auditoria confere. Nenhum dos três motores precisa de dado nosso para isso.

**Consequência para quem implementa**: `compare_bulletin` recebe hoje um `Valuation` gerado
e um `ReferenceBulletin` lido de planilha. No caminho avulso, os **dois** lados saem do
arquivo do cliente — o consolidado construído a partir do MAPÃO e o boletim lido da aba do
BM. Se essa montagem não couber no que existe, é fatia própria e precisa ser dita no plano,
não improvisada.
