"""Sugestão lexical de código SCO e confirmação de código pelo orçamentista.

Espelho deliberado de `services/worker/src/croquito_worker/association.py`: o
`ADR-0016` proíbe importar do worker, mas a forma do ato se repete de propósito —
ranking observacional determinístico que nunca confirma sozinho. O que muda é o
significado: lá associa-se proposta de visão computacional a uma cota; aqui sugere-se
código de catálogo para um item de takeoff já confirmado.

A sugestão lexical (`suggest_codes`) é o fallback permanente do produto, não um estágio
transitório: mesmo quando a via paga de IA (M5) entrar, ela só vai refinar a shortlist
lexical, nunca substituí-la. Um catálogo sem nenhuma composição paga continua tendo
sugestão determinística.

O refino (`apply_refinement`) é a transformação pura que aplica esse ato: ele **reordena
e anota** a shortlist que a via lexical produziu. Reordenar é a única operação permitida —
código a mais, a menos ou desconhecido recusa o refino inteiro —, e nada aqui confirma
código. Nenhum provider é importado neste módulo: quem fala com a via paga é o worker, que
entrega aqui só a ordem pedida, as anotações e o lineage da chamada.

A confirmação (`apply_code_assignments`) é fail-closed e imutável, no mesmo espírito de
`apply_takeoff_decisions`: recusa item desconhecido, item ainda não confirmado no
takeoff, re-decisão sobre item já decidido, código fora do catálogo ou do contrato, e
unidade incompatível sem nota explícita do orçamentista.

O M8 acrescenta as irmãs de CASCATA — `suggest_codes_over_cascade` e
`apply_code_assignments_over_cascade` —, que são o mesmo ato sobre mais de uma fonte de
preço (SCO → EMOP → composição). Elas existem só na pré-licitação (`ADR-0027`): a medição
de obra licitada continua com um catálogo só, contrato e nada mais, e nenhuma linha do
caminho de um catálogo mudou de comportamento. O que a cascata muda é que a fonte deixa de
ser implícita — cada candidato e cada confirmação declaram de qual catálogo vieram.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Annotated, Final, Literal

from pydantic import Field, field_validator, model_validator

from croquito_valuation.catalog import DomainSynonyms, lexical_similarity, normalize_unit
from croquito_valuation.contract import ContractWorkbook
from croquito_valuation.errors import ValuationValidationError
from croquito_valuation.models import (
    MAX_DESCRIPTION_LENGTH,
    NON_SCO_CODE_PATTERN,
    SHA256_PATTERN,
    ExactDecimal,
    PriceCatalog,
    PriceCatalogEntry,
    PriceOrigin,
    ReviewerDecision,
    ValuationContractModel,
)
from croquito_valuation.sco import SCO_CODE_PATTERN
from croquito_valuation.takeoff import TakeoffItem, TakeoffItemStatus, TakeoffPacket

SUGGESTION_SCHEMA_VERSION: Final = "1.3.0"
"""Bumpou em 2026-08-28 (ADR-0054, aceite humano item 3) porque `semantic` mudou de FORMA:
era **um** bloco de lineage e passou a ser a lista dos braços que participaram da fusão.

A cascata do orçamento-base roda o braço semântico por fonte (ADR-0054 D5), então um
conjunto pode ter nascido de N índices — um por catálogo com índice publicado —, e um campo
singular só conseguiria declarar o primeiro deles. Declarar menos lineage do que a fusão
usou é pior do que não declarar nenhum: a auditoria da ordem publicada ficaria
silenciosamente incompleta.

`1.2.0` continua no `Literal` de `schema_version` e continua sendo lido, com a forma
singular convertida para lista de um elemento na carga (`_wrap_singular_semantics`). Não é
gentileza: os blobs `code_suggestions_json` das rodadas gravadas até aqui declaram `1.2.0`,
e `suggestions_of` trata artefato ilegível como AUSENTE — um conjunto que deixasse de
validar apagaria em silêncio o refino pago que ele carrega.

Não bumpou na Fase 1 do M7 (léxico melhorado + sinônimos), de propósito: nenhum campo
mudou de forma, só de comportamento (`unmatched_item_ids` fica mais raro porque o corte de
`min_lexical_score` caiu, e `CodeCandidate.lexical_score` pode refletir score calculado com
sinônimo). `synonyms`/`ExpandedTerms` não têm campo correspondente no artefato — a expansão
é `expanded_terms` da CAMADA do servidor local (observação de busca), não do suggester."""
ASSIGNMENT_SCHEMA_VERSION: Final = "2.0.0"
"""Bumpou em 2026-08-26 (ADR-0053 decisão 2) porque a IDENTIDADE da confirmação mudou: era o
`item_id` e passou a ser o par `(item_id, code)`, com fechamento explícito de pacote.

`1.0.0` continua no `Literal` de `schema_version` e continua sendo lido com o comportamento
de sempre — unicidade por item, sem fechamento. Não é gentileza: os blobs
`code_assignments_json` são append-only e toda rodada gravada até aqui declara essa versão.
Uma rodada 1:1 é um pacote de um serviço só, que é exatamente o que ela é.

O regime é lido do artefato, nunca do processo. É isso que faz uma rodada antiga produzir o
mesmo boletim depois deste bump, e é isso que impede o regime novo de vazar para trás."""
SCO_SUGGESTER_VERSION: Final = "lexical-sco-suggester-v1"

SCO_CASCADE_SUGGESTER_VERSION: Final = "lexical-cascade-sco-suggester-v1"
"""A shortlist lexical montada sobre a CASCATA de fontes do orçamento-base (M8).

Mesmo algoritmo do `lexical-sco-suggester-v1`, rodado uma vez por catálogo da cascata e
concatenado na ordem dela — o que muda é o universo de códigos, não o ranqueamento. A
versão é própria porque quem lê o artefato precisa saber, pelo cabeçalho, que os
candidatos vêm de fontes diferentes e que cada um declara a sua
(`CodeCandidate.catalog_origin`/`catalog_sha256`). Nada disso vale para a medição licitada:
a cascata só existe pré-licitação (`ADR-0027`)."""

SCO_HYBRID_SUGGESTER_FAMILY: Final = "hybrid-sco-suggester-"
"""Prefixo estável da FAMÍLIA de suggesters híbridos, através de todas as versões.

`CodeSuggestionSet.validate_semantic_lineage` usa este prefixo — não
`SCO_HYBRID_SUGGESTER_VERSION` — para decidir "este conjunto é híbrido e por isso exige
`semantic`?". A distinção importa porque `SCO_HYBRID_SUGGESTER_VERSION` é a versão CORRENTE
(o que o produto escreve hoje), enquanto artefatos antigos gravados em disco (rodada
anterior a um bump) continuam carregando uma versão mais velha da mesma família e continuam
sendo, de fato, híbridos — `startswith(SCO_HYBRID_SUGGESTER_VERSION)` os reprovaria."""

SCO_HYBRID_SUGGESTER_VERSION: Final = SCO_HYBRID_SUGGESTER_FAMILY + "v2"
"""A shortlist montada por FUSÃO de dois braços: cobertura léxica e vizinhança semântica.

Ela não é uma reordenação da lexical — a fusão muda **quem** entra na shortlist, e é essa a
diferença que o M7 Fase 2 entrega: o código certo que a lexical deixava no rank 346 pode
entrar pelo braço semântico. Por isso ela é um suggester próprio, com `semantic` obrigatório
(qual modelo de embedding produziu a ordem), e não um `refinement` do lexical.

Bumpou de `v1` para `v2` na rodada 2.2 (2026-08-13, lista de ruído de legenda): os call
sites de produção (`local_server.py`, `cli.py`) passaram a passar `noise=default_legend_noise()`
ao braço léxico da fusão, o que muda a shortlist híbrida de verdade — não no RANK do código
certo (ranks dos 12 casos reais gateados do golden ficaram byte-idênticos), mas na
COMPOSIÇÃO do top-20 que o orçamentista revisa: `weighted_query_coverage_score` amortece o
peso de palavras de ESTADO da legenda ("existente", "a ser recuperar"), e "REFLETOR
EXISTENTE" caiu de 10/20 para 0/20 itens cujo único mérito era conter "existente" (ver
`tests/valuation/golden/matcher-golden-v1.json`, `note_phase_2_2`). `CodeSuggestionSet`
aceita v1 E v2 no `Literal` de `suggester_version` — artefato antigo continua carregável."""

SCO_LEXICAL_IDF_SUGGESTER_VERSION: Final = "lexical-idf-sco-suggester-v1"
"""A mesma via da fusão híbrida com uma perna a menos: só o braço léxico por COBERTURA.

É o que o produto publica quando não há índice de embeddings, teto de gasto, credencial —
ou quando o operador pediu `--no-semantic`. Nada de semântico participou, então `semantic`
fica ausente e `matching_of` continua dizendo `lexical`; o que muda em relação a
`lexical-sco-suggester-v1` é o ALGORITMO que monta a shortlist, e por isso a versão é
outra.

A diferença medida, e o motivo de ela ter virado o caminho padrão da degradação
(2026-08-21, catálogo real do SCO-Rio com 4.865 itens, gabarito de
`tests/valuation/golden/matcher-golden-v1.json`, 8 itens, k=5):

| via | acertos em k=5 |
|---|---|
| `lexical-sco-suggester-v1` (Dice, `lexical_similarity`) | 3/8 |
| `lexical-idf-sco-suggester-v1` (cobertura ponderada) | 8/8 |
| `hybrid-sco-suggester-v2` (com índice) | 6/8 |

O Dice divide pelo tamanho dos DOIS lados, então descrição de um parágrafo é penalizada
por ser longa: o código certo de "PISO INTERTRAVADO" (cuja descrição diz "Revestimento
intertravado…" e nunca escreve "piso") cai para o rank 1807 por Dice e sobe ao topo pela
cobertura ponderada por IDF. Antes desta rodada o produto servia o Dice na degradação
enquanto `hybrid_candidates(index=None)` — que já degradava sozinho para a cobertura —
ficava sem chamador.

A linha do híbrido acima NÃO autoriza mexer na fusão: são 8 amostras de uma prancha contra
os 12/12 contra 4/12 que calibraram os pesos noutro catálogo (`ADR-0021`). Reponderar é decisão
humana pendente, não conclusão desta medição."""

SCO_HYBRID_CASCADE_SUGGESTER_VERSION: Final = SCO_HYBRID_SUGGESTER_FAMILY + "cascade-v1"
"""A fusão híbrida rodada **por fonte** da cascata do orçamento-base (ADR-0054 D5).

Pertence à FAMÍLIA híbrida — o prefixo é o mesmo — porque é isso que faz
`validate_semantic_lineage` exigir `semantic` dela: o conjunto declara que pelo menos uma
fonte teve vizinhança semântica na fusão, e sem o lineage ninguém saberia qual índice
produziu a ordem daquele bloco.

A versão é própria, e não `hybrid-sco-suggester-v2`, porque o que ela afirma é diferente em
dois pontos que a auditoria precisa distinguir: os candidatos vêm de catálogos diferentes
(cada um declara o seu em `CodeCandidate.catalog_origin`/`catalog_sha256`) e a COBERTURA
semântica é parcial por construção — fonte sem índice publicado entra na mesma shortlist com
o braço léxico só (ADR-0054 D6), e `semantic` tem uma entrada por fonte que de fato teve
índice, nunca uma por fonte da cascata."""

LLM_RERANK_SUFFIX: Final = "+llm-rerank-v1"
"""Sufixo que o refino pago acrescenta ao suggester que produziu a shortlist de entrada."""

SCO_REFINED_SUGGESTER_VERSION: Final = SCO_SUGGESTER_VERSION + LLM_RERANK_SUFFIX
"""A shortlist lexical **depois** de reordenada e anotada pela via paga.

O nome carrega os dois estágios de propósito: o refino não substitui o suggester lexical,
ele opera sobre a saída dele. Quem lê o artefato sabe, pela versão, que a ordem publicada
passou por um provider — e o bloco `refinement` diz por qual."""

SCO_REFINED_HYBRID_SUGGESTER_VERSION: Final = SCO_HYBRID_SUGGESTER_VERSION + LLM_RERANK_SUFFIX
"""A shortlist híbrida depois do refino pago: os dois lineages viajam juntos no artefato."""

SCO_REFINED_LEXICAL_IDF_SUGGESTER_VERSION: Final = (
    SCO_LEXICAL_IDF_SUGGESTER_VERSION + LLM_RERANK_SUFFIX
)
"""A shortlist do braço léxico por cobertura depois do refino pago.

Existe porque o refino é ortogonal ao braço semântico: `suggest-codes --no-semantic
--refine-arm=...` monta a shortlist sem embedding e a manda reordenar. Sem esta forma no
`Literal`, `apply_refinement` recusaria a própria saída que o comando produz."""

_ITEM_ID_PATTERN: Final = r"^ti_[a-f0-9]{16}$"

_REFINEMENT_NOTE_MAX_LENGTH: Final = 1000
"""Espaço da nota composta (`rationale | flags: ...`), dimensionado pelo contrato de saída.

A conta é a que torna o estouro impossível por construção, e não uma folga arbitrária:
300 (rationale) + 10 (` | flags: `) + 5 x (120 + 2) (cinco flags com separador) = 920.
Uma resposta que respeita o contrato do provider cabe sempre; `REFINEMENT_NOTE_TOO_LONG`
continua existindo como defesa do domínio — que não depende de contrato de provider
nenhum —, mas deixa de ser alcançável por quem obedeceu ao schema. Antes disso, uma
resposta obediente com flags longas era recusada por defeito nosso.
"""


class CodeCandidate(ValuationContractModel):
    """Um código do catálogo elegível para um item, com o porquê da ordem.

    A forma exigida do `code` depende de `catalog_origin`, pelo mesmo desenho de
    `PriceCatalogEntry.validate_code_for_origin`: origem `sco` exige o padrão SCO estrito
    (não a forma nua do contrato — só código com preço publicado é candidato, e a forma nua
    nunca tem preço), as demais o superset estrutural não-SCO. Os defaults (`sco`/`None`)
    preservam byte a byte todo artefato M1-M7 relido sem os campos novos.

    `catalog_sha256` é a proveniência do candidato quando a shortlist nasce de uma CASCATA
    de fontes (orçamento-base, `suggest_codes_over_cascade`): com um catálogo só, o digest
    já está no cabeçalho do conjunto e o campo continua vazio.

    `refinement_note` só existe depois de `apply_refinement`: é a justificativa do refino
    pago para a ordem publicada, anotada no candidato que ficou em primeiro. Ela é
    observação anexada ao candidato, nunca um campo que altere preço, unidade ou score.
    """

    code: str = Field(min_length=1, max_length=30)
    description: str = Field(min_length=1, max_length=MAX_DESCRIPTION_LENGTH)
    unit: str = Field(min_length=1, max_length=20)
    unit_price: ExactDecimal = Field(ge=0)
    unit_compatible: bool
    in_contract: bool
    lexical_score: float = Field(ge=0, le=1)
    status: Literal["suggested"] = "suggested"
    refinement_note: str | None = Field(default=None, max_length=_REFINEMENT_NOTE_MAX_LENGTH)
    catalog_origin: PriceOrigin = PriceOrigin.SCO
    catalog_sha256: str | None = Field(default=None, pattern=SHA256_PATTERN)

    @model_validator(mode="after")
    def validate_code_for_origin(self) -> CodeCandidate:
        pattern = (
            SCO_CODE_PATTERN if self.catalog_origin == PriceOrigin.SCO else NON_SCO_CODE_PATTERN
        )
        if re.fullmatch(pattern, self.code) is None:
            raise ValuationValidationError(
                "CANDIDATE_CODE_INVALID_FOR_ORIGIN",
                "código do candidato não tem o formato esperado para a origem do catálogo",
                {"code": self.code, "catalog_origin": self.catalog_origin.value},
            )
        return self


class CodeSuggestion(ValuationContractModel):
    """As sugestões elegíveis de um item, já ordenadas e cortadas em `max_candidates_per_item`."""

    item_id: str = Field(pattern=_ITEM_ID_PATTERN)
    candidates: list[CodeCandidate] = Field(min_length=1)


class SuggestionRefinement(ValuationContractModel):
    """Lineage da chamada paga que reordenou a shortlist de uma prancha.

    Guarda o suficiente para reproduzir a auditoria da ordem publicada — quem respondeu,
    com qual modelo, sob qual versão de prompt e sobre qual payload (`input_digest` é o
    sha256 do texto enviado). `provider` é uma string simples de propósito: o `ADR-0016`
    proíbe este pacote de importar o worker, então o enum de provider fica do lado de lá e
    aqui entra só o valor dele.
    """

    provider: str = Field(min_length=1, max_length=40)
    model_id: str = Field(min_length=1, max_length=160)
    prompt_version: str = Field(min_length=1, max_length=80)
    input_digest: str = Field(pattern=SHA256_PATTERN)


class SuggestionSemantics(ValuationContractModel):
    """Lineage do braço semântico de UMA fonte que participou da fusão.

    Embedding não tem prompt: o que identifica a ordem produzida é o modelo, a dimensão do
    espaço e o digest do índice do catálogo usado (`catalog-embeddings.json`). O digest do
    próprio catálogo já viaja em `CodeSuggestionSet.catalog_sha256`, e é o índice que fica
    amarrado a ele — trocar de índice sem trocar de catálogo aparece aqui.

    `catalog_sha256` diz de QUAL fonte é este lineage, e existe porque desde o ADR-0054 D5 o
    conjunto pode carregar N destes blocos, um por catálogo da cascata com índice publicado.
    Com um bloco só ele é redundante com o cabeçalho, e é por isso que ele é opcional:
    ausente significa "a fonte do cabeçalho", que é exatamente o que um artefato gravado
    antes deste campo afirmava. Deduzir a fonte pela POSIÇÃO na lista seria amarrar a
    auditoria à ordem da cascata do dia em que o conjunto foi gravado.

    `provider` é string simples pelo mesmo motivo de `SuggestionRefinement.provider`: o
    `ADR-0016` proíbe este pacote de importar o enum de provider do worker.
    """

    provider: str = Field(min_length=1, max_length=40)
    model_id: str = Field(min_length=1, max_length=160)
    dims: int = Field(ge=1, le=8192)
    index_sha256: str = Field(pattern=SHA256_PATTERN)
    catalog_sha256: str | None = Field(default=None, pattern=SHA256_PATTERN)


class CodeSuggestionSet(ValuationContractModel):
    """Pacote de sugestões de uma prancha: observação, nunca decisão.

    `suggester_version` conta a origem da ordem publicada, em duas dimensões independentes:
    quem MONTOU a shortlist (lexical determinístico ou fusão híbrida) e se ela foi
    **reordenada** depois por provider pago (sufixo `+llm-rerank-v1`). Os dois blocos de
    lineage seguem a mesma regra de existir se e somente se o estágio aconteceu:
    `refinement` para a chamada de refino, `semantic` para o braço de embeddings. É o que
    impede o artefato de dizer "refinado" ou "híbrido" sem lineage — ou de carregar lineage
    de uma chamada que não aconteceu.

    O `Literal` de `suggester_version` aceita `hybrid-sco-suggester-v1` E
    `hybrid-sco-suggester-v2` (mais as formas `+llm-rerank-v1` de ambas): um artefato
    gravado antes do bump para `v2` (rodada 2.2, amortecimento de ruído de legenda)
    continua válido ao ser relido, e `validate_semantic_lineage` reconhece as duas versões
    como híbridas pelo prefixo de família `SCO_HYBRID_SUGGESTER_FAMILY`, não pela versão
    corrente — só a produção NOVA escreve `v2`.

    `lexical-idf-sco-suggester-v1` é a fusão SEM a perna semântica (nenhum embedding
    participou, `semantic` ausente) e é o que a degradação publica desde 2026-08-21;
    `lexical-sco-suggester-v1` continua no `Literal` porque artefato de rodada anterior
    — e a via Dice, que segue viva na cascata do orçamento-base — carrega essa versão.

    Com `lexical-cascade-sco-suggester-v1` (orçamento-base, `suggest_codes_over_cascade`) o
    conjunto abrange mais de um catálogo: `catalog_sha256` do cabeçalho é o do catálogo
    **cabeça** da cascata e a proveniência autoritativa passa a ser a de cada candidato
    (`CodeCandidate.catalog_origin`/`catalog_sha256`). O cabeçalho continua existindo
    porque ele amarra o conjunto à rodada; ele não afirma que todo candidato veio dali.

    `semantic` é a LISTA dos braços semânticos que participaram (ADR-0054, aceite humano
    item 3): uma entrada por fonte que tinha índice publicado, e nenhuma para as que
    entraram só com o braço léxico. Continua valendo "existe se e somente se o estágio
    aconteceu" — `None` quando nenhum embedding participou, e nunca lista vazia, que seria
    um terceiro estado dizendo a mesma coisa que `None`. A forma SINGULAR gravada até
    `1.2.0` é convertida na carga, porque uma shortlist que deixasse de validar seria tratada
    como ausente por `suggestions_of` e levaria junto o refino pago que ela carrega.
    """

    schema_version: Literal["1.2.0", "1.3.0"] = SUGGESTION_SCHEMA_VERSION
    plate_id: str = Field(min_length=1, max_length=64)
    page_number: int = Field(ge=1)
    image_sha256: str = Field(pattern=SHA256_PATTERN)
    catalog_sha256: str = Field(pattern=SHA256_PATTERN)
    contract_sha256: str | None = Field(default=None, pattern=SHA256_PATTERN)
    suggester_version: Literal[
        "lexical-sco-suggester-v1",
        "lexical-sco-suggester-v1+llm-rerank-v1",
        "lexical-idf-sco-suggester-v1",
        "lexical-idf-sco-suggester-v1+llm-rerank-v1",
        "lexical-cascade-sco-suggester-v1",
        "hybrid-sco-suggester-v1",
        "hybrid-sco-suggester-v1+llm-rerank-v1",
        "hybrid-sco-suggester-v2",
        "hybrid-sco-suggester-v2+llm-rerank-v1",
        "hybrid-sco-suggester-cascade-v1",
        "hybrid-sco-suggester-cascade-v1+llm-rerank-v1",
    ] = SCO_SUGGESTER_VERSION
    refinement: SuggestionRefinement | None = None
    semantic: Annotated[list[SuggestionSemantics], Field(min_length=1)] | None = None
    suggestions: list[CodeSuggestion]
    unmatched_item_ids: list[str]
    safety_notes: list[str] = Field(min_length=3)

    @field_validator("semantic", mode="before")
    @classmethod
    def wrap_singular_semantics(cls, value: object) -> object:
        """Lê a forma SINGULAR de `semantic` gravada até o schema `1.2.0` como lista de um.

        A conversão é de leitura, não de escrita: nada aqui grava a forma antiga. Ela existe
        porque `suggestions_of` (`valuation_rounds.py`) trata artefato ilegível como
        AUSENTE, e uma shortlist gravada antes deste bump que deixasse de validar apagaria em
        silêncio o refino pago que ela carrega — o lineage da chamada que explica por que a
        ordem publicada é aquela.

        Só o que é inequivocamente um bloco só entra na conversão: um mapa (o artefato JSON
        relido) ou um `SuggestionSemantics` já construído (o chamador em Python). Qualquer
        outra coisa segue intacta para o pydantic recusar com a mensagem dele.
        """
        if isinstance(value, Mapping | SuggestionSemantics):
            return [value]
        return value

    @model_validator(mode="after")
    def validate_refinement_lineage(self) -> CodeSuggestionSet:
        refined = self.suggester_version.endswith(LLM_RERANK_SUFFIX)
        if refined and self.refinement is None:
            raise ValuationValidationError(
                "SUGGESTION_REFINEMENT_MISSING",
                "conjunto declarado como refinado exige o lineage da chamada de refino",
                {"suggester_version": self.suggester_version},
            )
        if not refined and self.refinement is not None:
            raise ValuationValidationError(
                "SUGGESTION_REFINEMENT_UNEXPECTED",
                "conjunto não refinado não pode carregar lineage de refino",
                {"suggester_version": self.suggester_version},
            )
        return self

    @model_validator(mode="after")
    def validate_semantic_lineage(self) -> CodeSuggestionSet:
        # Prefixo de FAMÍLIA, não a versão corrente: um artefato v1 relido depois do bump
        # para v2 continua sendo híbrido e continua exigindo `semantic` — só a versão
        # exata mudaria com `startswith(SCO_HYBRID_SUGGESTER_VERSION)`.
        hybrid = self.suggester_version.startswith(SCO_HYBRID_SUGGESTER_FAMILY)
        if hybrid and self.semantic is None:
            raise ValuationValidationError(
                "SUGGESTION_SEMANTIC_MISSING",
                "conjunto declarado como híbrido exige o lineage do braço semântico",
                {"suggester_version": self.suggester_version},
            )
        if not hybrid and self.semantic is not None:
            raise ValuationValidationError(
                "SUGGESTION_SEMANTIC_UNEXPECTED",
                "conjunto lexical não pode carregar lineage de braço semântico",
                {"suggester_version": self.suggester_version},
            )
        return self

    @model_validator(mode="after")
    def validate_suggestions(self) -> CodeSuggestionSet:
        item_ids = [suggestion.item_id for suggestion in self.suggestions]
        duplicated = sorted({item_id for item_id in item_ids if item_ids.count(item_id) > 1})
        if duplicated:
            raise ValuationValidationError(
                "SUGGESTION_SET_INCONSISTENT",
                "há mais de uma sugestão para o mesmo item",
                {"item_ids": duplicated},
            )
        overlap = sorted(set(item_ids) & set(self.unmatched_item_ids))
        if overlap:
            raise ValuationValidationError(
                "SUGGESTION_SET_INCONSISTENT",
                "item não pode estar em suggestions e unmatched_item_ids ao mesmo tempo",
                {"item_ids": overlap},
            )
        return self


@dataclass(frozen=True)
class SuggestionConfig:
    """Parâmetros de corte da sugestão lexical.

    `min_lexical_score` deixou de ser o corte que decidia "tem candidato ou não": ele é só
    o piso de RUÍDO — score abaixo dele nem entra na competição do top-N. O corte antigo
    (0.2) escondia candidatos fracos mas corretos (o caso que motivou a Fase 1 do M7:
    "GRAMADO" não tinha token idêntico a "grama" no catálogo real, e o score ficava abaixo
    de 0.2 mesmo quando o candidato certo existia). O valor abaixo é o piso calibrado pelo
    golden set (`tests/valuation/test_matcher_golden.py`) sobre o catálogo real: baixo o
    bastante para não esconder candidato fraco-mas-correto, alto o bastante para não
    encher a shortlist de ruído puro (score do SequenceMatcher nunca é exatamente zero
    entre dois textos com QUALQUER caractere em comum).
    """

    max_candidates_per_item: int = 15
    """Quantos candidatos a shortlist publica por item, POR fonte de preço.

    Subiu de 3 para 15 em 2026-08-21, e o número é medido, não escolhido por gosto. Contra
    os 12 casos com código esperado do gabarito humano
    (`tests/valuation/golden/matcher-golden-v1.json`, catálogo real da Toca), o recall da
    shortlist híbrida por tamanho é:

    | k | 3 | 5 | 10 | 12 | **15** | 20 |
    |---|---|---|----|----|--------|----|
    | acertos | 5/12 | 6/12 | 8/12 | 10/12 | **12/12** | 12/12 |

    15 é onde a curva satura. Cortar em 3 escondia o código certo da orçamentista em 7 dos
    12 casos, e em 5 ainda escondia em 6 — ela teria de ir à busca manual num catálogo de
    ~5 mil itens em metade dos itens da prancha. O gate de recall do eval não depende deste
    valor: ele mede em 20 explicitamente (`extraction_eval._MATCHER_RECALL_CANDIDATES`).

    "Por fonte" é o que vale na cascata do orçamento-base (`suggest_codes_over_cascade`):
    3 catálogos passam a render até 45 candidatos por item, em BLOCOS na ordem da cascata.
    Não há corte global de propósito — ver a docstring daquela função.

    **Consequência medida no refino pago:** este número deixou de ser o que viaja ao
    provider. A shortlist inteira não cabia no `text_payload` (20000 caracteres) — numa
    prancha de 15 itens o payload ia a 335% do teto com k=15 —, então o refino passou a
    enviar uma JANELA por item (`sco_suggestion.TRANSMITTED_CANDIDATE_WINDOW`, hoje 10, o
    máximo que o contrato de saída do prompt consegue devolver) e a fatiar os itens em
    lotes que caibam no payload, uma chamada paga por lote. Mexer neste 15 muda quantos
    candidatos a orçamentista vê e quanta CAUDA fica fora do alcance do refino; não muda
    quantos o modelo reordena."""

    min_lexical_score: float = 0.03


_SUGGESTION_SAFETY_NOTES: Final = (
    "Sugestão lexical é observação determinística; nenhum código foi confirmado.",
    "Compatibilidade de unidade e presença no contrato não substituem a decisão do orçamentista.",
    "Item sem candidato exige busca manual no catálogo antes da confirmação.",
)


def suggest_codes(
    packet: TakeoffPacket,
    catalog: PriceCatalog,
    contract: ContractWorkbook | None = None,
    *,
    config: SuggestionConfig | None = None,
    synonyms: DomainSynonyms | None = None,
) -> CodeSuggestionSet:
    """Sugere códigos de catálogo para os itens confirmados do takeoff.

    Ordenação determinística e total: unidade compatível domina, depois presença no
    contrato, depois similaridade lexical, com o código como desempate final. Item vira
    candidato do top-N sempre que `lexical_similarity` (item, entrada do catálogo) fica
    acima do piso de ruído de `SuggestionConfig.min_lexical_score` — não existe mais um
    corte que troque "candidato fraco" por "sem candidato nenhum". `unmatched_item_ids`
    passa a significar, na prática: nenhuma entrada do catálogo passou do piso de ruído
    para este item — não que o candidato certo não exista.

    `synonyms` expande os radicais do item e da descrição do catálogo antes do cálculo de
    similaridade (`lexical_similarity`), o que aproxima termos de domínio que não
    compartilham nenhum token literal (`refletor` → também compara como `projetor`). Sem
    `synonyms`, o comportamento é o puramente lexical de sempre.
    """
    effective_config = config or SuggestionConfig()
    if effective_config.max_candidates_per_item < 1 or not (
        0 <= effective_config.min_lexical_score <= 1
    ):
        raise ValuationValidationError(
            "SUGGESTION_CONFIG_INVALID",
            "configuração de sugestão de código inválida",
            {
                "max_candidates_per_item": effective_config.max_candidates_per_item,
                "min_lexical_score": effective_config.min_lexical_score,
            },
        )

    confirmed_items = packet.confirmed_items()
    if not confirmed_items:
        raise ValuationValidationError(
            "SUGGESTION_NO_CONFIRMED_ITEMS",
            "pacote de takeoff não possui item confirmado; revise o takeoff antes de sugerir",
            {"plate_id": packet.plate_id},
        )

    contract_codes = {line.code for line in contract.lines} if contract is not None else frozenset()
    suggestions: list[CodeSuggestion] = []
    unmatched_item_ids: list[str] = []
    for item in confirmed_items:
        eligible: list[CodeCandidate] = []
        for entry in catalog.entries:
            score = lexical_similarity(item.label, entry.description, synonyms=synonyms)
            if score < effective_config.min_lexical_score:
                continue
            unit_compatible = normalize_unit(item.unit) == normalize_unit(entry.unit)
            in_contract = entry.code in contract_codes
            eligible.append(
                CodeCandidate(
                    code=entry.code,
                    description=entry.description,
                    unit=entry.unit,
                    unit_price=entry.unit_price,
                    unit_compatible=unit_compatible,
                    in_contract=in_contract,
                    lexical_score=score,
                    catalog_origin=catalog.origin,
                )
            )
        if not eligible:
            unmatched_item_ids.append(item.id)
            continue
        ordered = sorted(
            eligible,
            key=lambda candidate: (
                not candidate.unit_compatible,
                not candidate.in_contract,
                -candidate.lexical_score,
                candidate.code,
            ),
        )
        suggestions.append(
            CodeSuggestion(
                item_id=item.id,
                candidates=ordered[: effective_config.max_candidates_per_item],
            )
        )

    return CodeSuggestionSet(
        plate_id=packet.plate_id,
        page_number=packet.page_number,
        image_sha256=packet.image_sha256,
        catalog_sha256=catalog.source_sha256,
        contract_sha256=contract.source_sha256 if contract else None,
        suggestions=suggestions,
        unmatched_item_ids=unmatched_item_ids,
        safety_notes=list(_SUGGESTION_SAFETY_NOTES),
    )


def ensure_price_cascade(cascade: Sequence[PriceCatalog]) -> None:
    """Portão da cascata de fontes do orçamento-base: ordem é dado, uma origem por fonte.

    A ORDEM é a que o chamador declarou (a sequência de `--catalog` do comando), nunca uma
    preferência embutida em código: "SCO primeiro" é decisão de quem monta o orçamento, não
    do módulo (`ADR-0027`). O que se recusa aqui é a cascata que não teria leitura única —
    vazia, ou com duas fontes da mesma origem, caso em que "o preço veio da EMOP" deixaria
    de identificar de qual arquivo ele veio.

    Mora neste módulo porque os dois atos daqui (sugerir e confirmar código) já operam
    sobre a cascata; `estimate.py` reusa o mesmo portão antes de montar o orçamento.
    """
    if not cascade:
        raise ValuationValidationError(
            "ESTIMATE_CASCADE_EMPTY",
            "orçamento-base exige ao menos um catálogo na cascata de fontes",
            {},
        )
    origins = [catalog.origin.value for catalog in cascade]
    duplicated = sorted({origin for origin in origins if origins.count(origin) > 1})
    if duplicated:
        raise ValuationValidationError(
            "ESTIMATE_CASCADE_ORIGIN_DUPLICATE",
            "cascata tem mais de um catálogo da mesma origem de preço; a origem deixaria "
            "de identificar a fonte do preço de cada linha",
            {"origins": duplicated},
        )


def suggest_codes_over_cascade(
    packet: TakeoffPacket,
    cascade: Sequence[PriceCatalog],
    *,
    config: SuggestionConfig | None = None,
    synonyms: DomainSynonyms | None = None,
) -> CodeSuggestionSet:
    """Shortlist lexical sobre a cascata de fontes; observação, como a de um catálogo só.

    O algoritmo é o mesmo de `suggest_codes`, rodado uma vez por catálogo: o que muda é o
    universo de códigos. Os candidatos saem na ordem da CASCATA (todos os do primeiro
    catálogo, depois os do segundo), cada bloco com o ranqueamento interno que a via lexical
    produziu — misturar os blocos por score faria a ordem das fontes, que é decisão
    declarada de quem monta o orçamento, ser desempatada por similaridade de texto.

    O corte de `max_candidates_per_item` vale POR fonte, de propósito: uma fonte não pode
    ser espremida para fora da shortlist por outra que ficou na frente da cascata.

    Não há contrato aqui: pré-licitação não tem contrato, então `in_contract` é sempre
    falso e `contract_sha256` fica vazio. Cada candidato declara a origem e o digest do
    catálogo de onde veio.
    """
    ensure_price_cascade(cascade)

    candidates_by_item: dict[str, list[CodeCandidate]] = {}
    for catalog in cascade:
        for suggestion in suggest_codes(
            packet, catalog, None, config=config, synonyms=synonyms
        ).suggestions:
            # `catalog_origin` já vem carimbado da construção (é ele que valida a forma do
            # código); aqui só entra o digest, que é o que distingue duas fontes da MESMA
            # origem em rodadas diferentes.
            candidates_by_item.setdefault(suggestion.item_id, []).extend(
                candidate.model_copy(update={"catalog_sha256": catalog.source_sha256})
                for candidate in suggestion.candidates
            )

    suggestions: list[CodeSuggestion] = []
    unmatched_item_ids: list[str] = []
    for item in packet.confirmed_items():
        candidates = candidates_by_item.get(item.id)
        if not candidates:
            unmatched_item_ids.append(item.id)
            continue
        suggestions.append(CodeSuggestion(item_id=item.id, candidates=candidates))

    return CodeSuggestionSet(
        plate_id=packet.plate_id,
        page_number=packet.page_number,
        image_sha256=packet.image_sha256,
        catalog_sha256=cascade[0].source_sha256,
        contract_sha256=None,
        suggester_version=SCO_CASCADE_SUGGESTER_VERSION,
        suggestions=suggestions,
        unmatched_item_ids=unmatched_item_ids,
        safety_notes=list(_SUGGESTION_SAFETY_NOTES),
    )


def _refinement_note(rationale: str | None, flags: Sequence[str]) -> str | None:
    """Junta rationale e flags de um item numa única anotação, sem descartar nada.

    A representação é uma escolha declarada: **uma** nota por item, gravada no candidato
    que ficou em primeiro lugar. As flags entram na mesma nota, atrás do separador
    `" | flags: "`, porque flag sem o contexto do rationale vira aviso órfão — e porque o
    modelo de domínio guarda anotação no candidato, não no item. Nada é truncado: nota
    maior que o limite do campo recusa o refino inteiro em `apply_refinement`.
    """
    parts: list[str] = []
    cleaned_rationale = (rationale or "").strip()
    if cleaned_rationale:
        parts.append(cleaned_rationale)
    cleaned_flags = [flag.strip() for flag in flags if flag.strip()]
    if cleaned_flags:
        parts.append("flags: " + "; ".join(cleaned_flags))
    if not parts:
        return None
    return " | ".join(parts)


def apply_refinement(
    suggestions: CodeSuggestionSet,
    ranked_codes_by_item: Mapping[str, Sequence[str]],
    notes_by_item: Mapping[str, str] | None,
    flags_by_item: Mapping[str, Sequence[str]] | None,
    refinement: SuggestionRefinement,
    *,
    transmitted_window: int | None = None,
) -> CodeSuggestionSet:
    """Aplica o refino pago sobre a shortlist lexical; nunca muta o conjunto de entrada.

    Reordenar e anotar é tudo o que o refino pode fazer. A ordem pedida para um item tem
    de ser **permutação exata do que foi ENVIADO** ao provider para aquele item: código
    novo, código a mais ou código a menos recusa com `REFINEMENT_CODES_MISMATCH`, porque
    aceitar qualquer um dos três deixaria o provider substituir a shortlist em vez de
    refiná-la. Item citado que não existe no conjunto recusa com
    `REFINEMENT_UNKNOWN_ITEM`; item do conjunto que o refino não citou mantém a ordem
    lexical intocada, sem nota.

    `transmitted_window` é quantos candidatos de cada item o chamador de fato transmitiu.
    `None` — o default e o caso de sempre — significa "a shortlist inteira", e aí a
    exigência continua sendo permutação exata dela. Com um número, o refino ranqueia só o
    **prefixo** de `min(transmitted_window, len(shortlist))` candidatos e o resultado é
    `[cabeça reordenada] + [cauda intocada]`. Existe porque o contrato de saída do provider
    (`ScoItemRefinementOutput.ranked_codes`) e o teto do `text_payload` limitam quantos
    candidatos cabem numa chamada, enquanto a shortlist publicada para a orçamentista é
    maior — dois números com trabalhos diferentes.

    Invariantes que a janela **não** afrouxa:

    - nenhum código entra e nenhum sai: o conjunto publicado é exatamente o mesmo, só a
      ordem da cabeça muda;
    - tem de ser o PREFIXO, não um subconjunto qualquer. Quem escolhe o que é enviado somos
      nós; aceitar qualquer subconjunto deixaria o provider escolher sobre o que opinar, e
      isso não é verificável a partir da resposta;
    - a CAUDA mantém a ordem relativa que a via léxica deu — ela não foi transmitida, então
      ninguém opinou sobre ela;
    - shortlist menor ou igual à janela cai no caso de sempre: permutação exata.

    O que atravessa sem alteração: `unmatched_item_ids`, `safety_notes`, os digests da
    prancha/catálogo/contrato, o lineage `semantic` de quem montou a shortlist e todo campo
    de candidato que não seja a posição ou a `refinement_note` — `lexical_score`,
    `unit_compatible`, `in_contract`, preço e `status` continuam sendo o que a via
    determinística mediu.

    O `suggester_version` publicado é o de ENTRADA mais o sufixo do refino: refinar a
    shortlist lexical dá `lexical-...+llm-rerank-v1`, refinar a híbrida dá
    `hybrid-...+llm-rerank-v1`. Refinar duas vezes é recusado — a segunda chamada não teria
    onde gravar o próprio lineage sem apagar o da primeira.
    """
    if suggestions.suggester_version.endswith(LLM_RERANK_SUFFIX):
        raise ValuationValidationError(
            "REFINEMENT_ALREADY_APPLIED",
            "conjunto já refinado não pode ser refinado de novo",
            {"suggester_version": suggestions.suggester_version},
        )
    if transmitted_window is not None and transmitted_window < 1:
        raise ValuationValidationError(
            "REFINEMENT_WINDOW_INVALID",
            "janela de refino precisa transmitir ao menos um candidato por item",
            {"transmitted_window": transmitted_window},
        )
    ranked_by_item = {item_id: list(codes) for item_id, codes in ranked_codes_by_item.items()}
    notes = dict(notes_by_item or {})
    flags = {item_id: list(values) for item_id, values in (flags_by_item or {}).items()}

    known_ids = {suggestion.item_id for suggestion in suggestions.suggestions}
    unknown_ids = sorted((set(ranked_by_item) | set(notes) | set(flags)) - known_ids)
    if unknown_ids:
        raise ValuationValidationError(
            "REFINEMENT_UNKNOWN_ITEM",
            "refino aponta para item que não está na shortlist lexical",
            {"unknown_ids": unknown_ids},
        )

    refined_suggestions: list[CodeSuggestion] = []
    for suggestion in suggestions.suggestions:
        ranked = ranked_by_item.get(suggestion.item_id)
        note = _refinement_note(notes.get(suggestion.item_id), flags.get(suggestion.item_id, []))
        if ranked is None and note is None:
            refined_suggestions.append(suggestion)
            continue

        candidates_by_code = {candidate.code: candidate for candidate in suggestion.candidates}
        shortlist = [candidate.code for candidate in suggestion.candidates]
        head_length = (
            len(shortlist)
            if transmitted_window is None
            else min(transmitted_window, len(shortlist))
        )
        transmitted, retained = shortlist[:head_length], shortlist[head_length:]
        if ranked is not None and sorted(ranked) != sorted(transmitted):
            raise ValuationValidationError(
                "REFINEMENT_CODES_MISMATCH",
                "ordem refinada deve ser permutação exata dos candidatos transmitidos do item",
                {
                    "item_id": suggestion.item_id,
                    "transmitted": sorted(transmitted),
                    "shortlist": sorted(shortlist),
                    "ranked": list(ranked),
                },
            )
        ordered = (
            list(suggestion.candidates)
            if ranked is None
            else [candidates_by_code[code] for code in (*ranked, *retained)]
        )
        if note is not None:
            if len(note) > _REFINEMENT_NOTE_MAX_LENGTH:
                raise ValuationValidationError(
                    "REFINEMENT_NOTE_TOO_LONG",
                    "anotação do refino excede o limite do candidato; nada é truncado",
                    {
                        "item_id": suggestion.item_id,
                        "length": len(note),
                        "max_length": _REFINEMENT_NOTE_MAX_LENGTH,
                    },
                )
            ordered = [ordered[0].model_copy(update={"refinement_note": note}), *ordered[1:]]
        refined_suggestions.append(suggestion.model_copy(update={"candidates": ordered}))

    return CodeSuggestionSet.model_validate(
        {
            **suggestions.model_dump(),
            "suggester_version": suggestions.suggester_version + LLM_RERANK_SUFFIX,
            "refinement": refinement.model_dump(),
            "suggestions": [item.model_dump() for item in refined_suggestions],
        }
    )


def _is_structural_code(code: str, *, cited_catalog: bool) -> bool:
    """A estrutura mínima que um código confirmado precisa ter na ENTRADA da decisão.

    Sem catálogo citado, a fonte é o catálogo único da rodada e o formato exigido continua
    sendo o SCO exato — é a medição licitada e todo o M4-M7. Com catálogo citado, a rodada
    tem mais de uma fonte e o formato exato depende da origem daquela fonte, que este
    modelo não conhece: aqui basta o superset estrutural (SCO **ou** não-SCO) e a checagem
    forte acontece onde o catálogo existe (`apply_code_assignments_over_cascade`,
    `build_worksite_estimate`).
    """
    if re.fullmatch(SCO_CODE_PATTERN, code) is not None:
        return True
    return cited_catalog and re.fullmatch(NON_SCO_CODE_PATTERN, code) is not None


class CodeAssignmentInput(ValuationContractModel):
    """Decisão do orçamentista sobre o código de um item; espelho de `TakeoffDecisionInput`.

    `code` não declara `pattern` no campo: a validação usa `re.fullmatch` explícito no
    validador de modelo para que a falha suba como `ASSIGNMENT_CODE_INVALID` (código
    estável), em vez do erro genérico de padrão que o Pydantic devolveria sem o embrulho
    de `ValuationValidationError`.

    `catalog_sha256` é a fonte que o orçamentista citou ao confirmar o código, e só faz
    sentido quando existe mais de uma (orçamento-base, `apply_code_assignments_over_cascade`):
    ausente — o default, que é o da medição licitada e de todo artefato M4-M7 — a fonte é o
    único catálogo da rodada. A citação muda o que a ESTRUTURA do código precisa ser: sem
    ela vale o padrão SCO exato de sempre; com ela basta o superset estrutural, porque um
    código EMOP ou de composição não tem a forma do SCO. Quem checa que o código realmente
    pertence ao catálogo citado é a aplicação, onde o catálogo existe.
    """

    item_id: str = Field(pattern=_ITEM_ID_PATTERN)
    action: Literal["confirm", "reject"]
    code: str | None = None
    catalog_sha256: str | None = Field(default=None, pattern=SHA256_PATTERN)
    reviewer_id: str = Field(min_length=1, max_length=120)
    reviewer_role: Literal["orcamentista"]
    decided_at: datetime
    note: str | None = Field(default=None, min_length=1, max_length=500)

    @field_validator("decided_at")
    @classmethod
    def validate_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValuationValidationError(
                "ASSIGNMENT_DECISION_TIMESTAMP_NAIVE",
                "decisão de confirmação de código exige data e hora com fuso horário",
                {"decided_at": value.isoformat()},
            )
        return value

    @model_validator(mode="after")
    def validate_action_and_code(self) -> CodeAssignmentInput:
        if self.action == "confirm" and self.code is None:
            raise ValuationValidationError(
                "ASSIGNMENT_CODE_REQUIRED",
                "confirmação de código exige o código escolhido",
                {"item_id": self.item_id},
            )
        if self.action == "reject" and self.code is not None:
            raise ValuationValidationError(
                "ASSIGNMENT_CODE_ON_REJECT",
                "rejeição de código não deve informar código",
                {"item_id": self.item_id, "code": self.code},
            )
        if self.action == "reject" and self.catalog_sha256 is not None:
            raise ValuationValidationError(
                "ASSIGNMENT_CATALOG_ON_REJECT",
                "rejeição de código não cita fonte de preço; ela é a recusa de todas",
                {"item_id": self.item_id, "catalog_sha256": self.catalog_sha256},
            )
        if self.code is not None and not _is_structural_code(
            self.code, cited_catalog=self.catalog_sha256 is not None
        ):
            raise ValuationValidationError(
                "ASSIGNMENT_CODE_INVALID",
                "código informado não tem a estrutura de um código com preço publicado",
                {"item_id": self.item_id, "code": self.code},
            )
        return self


class CodeAssignmentRevocationInput(ValuationContractModel):
    """Retirada de um par `(item, código)` já confirmado — o ato que a etapa não tinha.

    Desde o ADR-0053 a identidade da decisão é o par, e até a F-045 nada o desfazia: um
    código confirmado por engano só se consertava refazendo a rodada inteira. Este input é o
    ato inverso, e é ato PRÓPRIO — não uma terceira `action` de `CodeAssignmentInput`, porque
    revogar não decide nada sobre o código: decide sobre uma decisão.

    `note` é **obrigatória**, ao contrário de toda outra nota desta etapa. Desfazer é o ato
    que alguém vai auditar depois, e é a frase escrita que separa o conserto do descuido
    (ADR-0061 D1).
    """

    item_id: str = Field(pattern=_ITEM_ID_PATTERN)
    code: str = Field(min_length=1, max_length=64)
    reviewer_id: str = Field(min_length=1, max_length=120)
    reviewer_role: Literal["orcamentista"]
    revoked_at: datetime
    note: str = Field(min_length=1, max_length=500)

    @field_validator("revoked_at")
    @classmethod
    def validate_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValuationValidationError(
                "ASSIGNMENT_DECISION_TIMESTAMP_NAIVE",
                "revogação de código exige data e hora com fuso horário",
                {"revoked_at": value.isoformat()},
            )
        return value


class CodeAssignmentRevocation(ValuationContractModel):
    """O registro do que foi desfeito, no conjunto CORRENTE.

    A prova de que o par existiu está na revisão anterior, que continua gravada — mas quem lê
    o conjunto corrente precisa distinguir "nunca foi decidido" de "foi decidido e desfeito"
    sem ter de comparar revisões. É essa distinção que uma auditoria procura, e é por isso
    que o registro fica aqui em vez de só no histórico (ADR-0061 D2).

    Um par revogado pode ser confirmado outra vez (D5). Quando isso acontece, ele aparece nos
    dois lugares — em `assignments`, corrente, e aqui, como o que já foi desfeito uma vez —, e
    é a leitura que decide o que mostrar. Apagar o registro na reconfirmação perderia o ato.
    """

    item_id: str = Field(pattern=_ITEM_ID_PATTERN)
    code: str = Field(min_length=1, max_length=64)
    revocation_id: str = Field(pattern=r"^vr_[a-f0-9]{16}$")
    reviewer_id: str = Field(min_length=1, max_length=120)
    reviewer_role: Literal["orcamentista"]
    revoked_at: datetime
    note: str = Field(min_length=1, max_length=500)


class ItemPackageClosureInput(ValuationContractModel):
    """Declaração de que o pacote de serviços de um elemento está COMPLETO.

    Ato próprio, e não uma bandeira na última confirmação: a rota posta uma decisão por
    request, então um pacote de seis códigos nasce em seis atos e ninguém sabe de antemão
    qual será o último. Quem fecha afirma o que a confirmação não afirma — que não vem mais
    nada —, e afirmação precisa de autor, instante e, quando houver, justificativa.
    """

    item_id: str = Field(pattern=_ITEM_ID_PATTERN)
    reviewer_id: str = Field(min_length=1, max_length=120)
    reviewer_role: Literal["orcamentista"]
    decided_at: datetime
    note: str | None = Field(default=None, min_length=1, max_length=500)

    @field_validator("decided_at")
    @classmethod
    def validate_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValuationValidationError(
                "ASSIGNMENT_DECISION_TIMESTAMP_NAIVE",
                "fechamento de pacote exige data e hora com fuso horário",
                {"decided_at": value.isoformat()},
            )
        return value


def _ensure_package_shape(pairs: Sequence[tuple[str, str | None]]) -> None:
    """Unicidade sob o regime de pacote, com três recusas que dizem coisas diferentes.

    `pairs` é `(item_id, code)` por decisão, com `code=None` na rejeição.

    - O mesmo par duas vezes é decisão repetida (`ASSIGNMENT_DUPLICATE_PAIR`). É o que
      `ASSIGNMENT_DUPLICATE_ITEM` significava no regime 1:1, e é por isso que ele não podia
      simplesmente ser reinterpretado: o significado antigo continua existindo, só que
      aplicado ao par.
    - Mais de uma rejeição para o mesmo item continua sendo duplicidade de item, e mantém o
      código estável `ASSIGNMENT_DUPLICATE_ITEM` — o mesmo que a tela já sabe traduzir.
    - Rejeitar e confirmar o mesmo item é contradição, não pacote
      (`ASSIGNMENT_REJECT_WITH_CONFIRMED`): rejeitar é dizer que NENHUM serviço precifica o
      elemento, e isso não coexiste com um serviço que o precifica.
    """
    entries = list(pairs)
    confirmed = [(item_id, code) for item_id, code in entries if code is not None]
    duplicated_pairs = sorted(
        {f"{item_id}:{code}" for item_id, code in confirmed if confirmed.count((item_id, code)) > 1}
    )
    if duplicated_pairs:
        raise ValuationValidationError(
            "ASSIGNMENT_DUPLICATE_PAIR",
            "há mais de uma decisão para o mesmo par de item e código",
            {"pairs": duplicated_pairs},
        )

    rejected_ids = [item_id for item_id, code in entries if code is None]
    duplicated_items = sorted({item for item in rejected_ids if rejected_ids.count(item) > 1})
    if duplicated_items:
        raise ValuationValidationError(
            "ASSIGNMENT_DUPLICATE_ITEM",
            "há mais de uma rejeição para o mesmo item",
            {"item_ids": duplicated_items},
        )

    contradicted = sorted(set(rejected_ids) & {item_id for item_id, _ in confirmed})
    if contradicted:
        raise ValuationValidationError(
            "ASSIGNMENT_REJECT_WITH_CONFIRMED",
            "rejeitar é declarar que nenhum serviço precifica o elemento; não coexiste com "
            "código confirmado para o mesmo item",
            {"item_ids": contradicted},
        )


def _ensure_unique_closures(item_ids: Sequence[str]) -> None:
    """Fechar duas vezes o mesmo pacote não é reforço; é ambiguidade sobre qual ato vale."""
    entries = list(item_ids)
    duplicated = sorted({item for item in entries if entries.count(item) > 1})
    if duplicated:
        raise ValuationValidationError(
            "ASSIGNMENT_DUPLICATE_CLOSURE",
            "há mais de um fechamento de pacote para o mesmo item",
            {"item_ids": duplicated},
        )


class CodeAssignmentBatch(ValuationContractModel):
    """Lote de decisões de código e de fechamentos de pacote.

    Os dois atos viajam juntos porque um lote é uma sessão de trabalho da orçamentista, e
    não uma decisão só: ela pode acrescentar o quinto código de um elemento e fechar o
    pacote de outro no mesmo envio. Lote só com fechamento também é legítimo — o fechamento
    costuma vir depois do último código —, e é por isso que `assignments` deixou de exigir
    `min_length=1`. O que não existe é lote vazio.
    """

    assignments: list[CodeAssignmentInput] = Field(default_factory=list)
    closures: list[ItemPackageClosureInput] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_batch(self) -> CodeAssignmentBatch:
        if not self.assignments and not self.closures:
            raise ValuationValidationError(
                "ASSIGNMENT_BATCH_EMPTY",
                "lote exige ao menos uma decisão de código ou um fechamento de pacote",
                {},
            )
        _ensure_package_shape(
            [(assignment.item_id, assignment.code) for assignment in self.assignments]
        )
        _ensure_unique_closures([closure.item_id for closure in self.closures])
        return self


class CodeAssignment(ValuationContractModel):
    """Resultado imutável da confirmação/rejeição de código de um item.

    `catalog_sha256` carrega adiante a fonte citada na confirmação (vazio quando a rodada
    tem um catálogo só, como em toda a medição licitada). É por ele que o orçamento-base
    sabe, linha a linha, de qual tabela o preço veio — `build_worksite_estimate` exige a
    citação e recusa a que não estiver na cascata.
    """

    item_id: str = Field(pattern=_ITEM_ID_PATTERN)
    status: Literal["confirmed", "rejected"]
    code: str | None = None
    catalog_sha256: str | None = Field(default=None, pattern=SHA256_PATTERN)
    unit_compatible: bool
    decision: ReviewerDecision

    @model_validator(mode="after")
    def validate_state(self) -> CodeAssignment:
        if self.status == "confirmed":
            if self.code is None or self.decision.action != "confirm":
                raise ValuationValidationError(
                    "ASSIGNMENT_STATE_INVALID",
                    "assignment confirmado exige código e decisão de confirmação",
                    {"item_id": self.item_id},
                )
        elif self.code is not None or self.decision.action != "reject":
            raise ValuationValidationError(
                "ASSIGNMENT_STATE_INVALID",
                "assignment rejeitado não pode carregar código e exige decisão de rejeição",
                {"item_id": self.item_id},
            )
        elif self.catalog_sha256 is not None:
            raise ValuationValidationError(
                "ASSIGNMENT_STATE_INVALID",
                "assignment rejeitado não cita fonte de preço; a rejeição vale para todas",
                {"item_id": self.item_id},
            )
        return self


class ItemPackageClosure(ValuationContractModel):
    """Ato humano que declara o pacote de serviços de um elemento COMPLETO.

    Existe porque, com a cardinalidade N:N, a presença de um assignment deixou de responder
    "este item acabou?". Um elemento com um de seis códigos pareceria pronto e produziria
    boletim parcial em silêncio; o fechamento é o que separa "resolvido" de "pela metade".
    Nunca é inferido da contagem de códigos — ninguém, além da orçamentista, sabe quantos
    serviços um elemento dispara.
    """

    item_id: str = Field(pattern=_ITEM_ID_PATTERN)
    decision: ReviewerDecision

    @model_validator(mode="after")
    def validate_state(self) -> ItemPackageClosure:
        if self.decision.action != "confirm":
            raise ValuationValidationError(
                "ASSIGNMENT_STATE_INVALID",
                "fechamento de pacote é afirmação, não recusa; exige decisão de confirmação",
                {"item_id": self.item_id},
            )
        return self


class CodeAssignmentSet(ValuationContractModel):
    """Conjunto imutável de confirmações/rejeições de código de uma prancha.

    O `schema_version` declara o REGIME, e não só a forma dos campos:

    - `1.0.0` — um código por item, sem fechamento. É o que está gravado em toda rodada
      anterior ao ADR-0053, e relê com o comportamento exato de antes.
    - `2.0.0` — a identidade é o par `(item_id, code)`, e o pacote de um elemento só está
      completo quando um `ItemPackageClosure` diz que está.

    Pacote aberto é estado NORMAL e persistido, não erro: o segundo dos seis códigos chega
    num lote seguinte, e entre um e outro a rodada precisa poder ser gravada e relida. Quem
    recusa pacote aberto é o portão que monta o boletim, onde a metade vira número errado.
    """

    schema_version: Literal["1.0.0", "2.0.0"] = ASSIGNMENT_SCHEMA_VERSION
    plate_id: str = Field(min_length=1, max_length=64)
    page_number: int = Field(ge=1)
    image_sha256: str = Field(pattern=SHA256_PATTERN)
    catalog_sha256: str = Field(pattern=SHA256_PATTERN)
    contract_sha256: str | None = Field(default=None, pattern=SHA256_PATTERN)
    assignments: list[CodeAssignment]
    closures: list[ItemPackageClosure] = Field(default_factory=list)
    revocations: list[CodeAssignmentRevocation] = Field(default_factory=list)
    safety_notes: list[str] = Field(min_length=2)

    @model_validator(mode="after")
    def validate_package_integrity(self) -> CodeAssignmentSet:
        if self.schema_version == "1.0.0":
            if self.closures:
                raise ValuationValidationError(
                    "ASSIGNMENT_CLOSURE_NOT_SUPPORTED",
                    "conjunto no regime de código único não tem pacote para fechar",
                    {"item_ids": sorted({closure.item_id for closure in self.closures})},
                )
            if self.revocations:
                raise ValuationValidationError(
                    "ASSIGNMENT_REVOCATION_NOT_SUPPORTED",
                    "conjunto no regime de código único não aceita revogação; ali a "
                    "confirmação era o pacote inteiro",
                    {"item_ids": sorted({item.item_id for item in self.revocations})},
                )
            item_ids = [assignment.item_id for assignment in self.assignments]
            duplicated = sorted({item_id for item_id in item_ids if item_ids.count(item_id) > 1})
            if duplicated:
                raise ValuationValidationError(
                    "ASSIGNMENT_DUPLICATE_ITEM",
                    "há mais de um assignment para o mesmo item",
                    {"item_ids": duplicated},
                )
            return self

        _ensure_package_shape(
            [(assignment.item_id, assignment.code) for assignment in self.assignments]
        )
        closure_ids = [closure.item_id for closure in self.closures]
        _ensure_unique_closures(closure_ids)
        confirmed_ids = {
            assignment.item_id
            for assignment in self.assignments
            if assignment.status == "confirmed"
        }
        orphan = sorted(set(closure_ids) - confirmed_ids)
        if orphan:
            raise ValuationValidationError(
                "ASSIGNMENT_CLOSURE_WITHOUT_ASSIGNMENT",
                "fechamento de pacote exige ao menos um código confirmado para o item; "
                "rejeição já fecha o item sozinha",
                {"item_ids": orphan},
            )
        return self

    def closed_item_ids(self) -> frozenset[str]:
        """Itens cujo pacote está completo: o fechamento declarado, mais toda rejeição.

        A rejeição fecha o item sozinha — declarar que nenhum serviço precifica o elemento
        já é dizer que não vem mais nada, e pedir um fechamento em cima disso seria exigir
        duas vezes a mesma afirmação.

        Em `1.0.0` não existe pacote aberto: lá a confirmação ERA o fechamento, porque um
        código era o pacote inteiro. Todo item decidido conta como fechado, e é isso que faz
        uma rodada antiga produzir o mesmo boletim de antes.
        """
        if self.schema_version == "1.0.0":
            return frozenset(assignment.item_id for assignment in self.assignments)
        rejected = {
            assignment.item_id for assignment in self.assignments if assignment.status == "rejected"
        }
        return frozenset({closure.item_id for closure in self.closures} | rejected)

    def open_package_item_ids(self) -> frozenset[str]:
        """Itens que já receberam código e ainda esperam o ato de fechamento."""
        return frozenset(
            {assignment.item_id for assignment in self.assignments} - self.closed_item_ids()
        )

    def confirmed_codes_by_item(self) -> dict[str, tuple[str, ...]]:
        """Códigos confirmados de cada item, na ordem em que foram decididos.

        A ordem é a do próprio conjunto, e ela importa: é ela que o boletim usa para numerar
        as linhas de um pacote, e determinismo é obrigatório porque `valuation-demo` é
        golden.
        """
        packages: dict[str, tuple[str, ...]] = {}
        for assignment in self.assignments:
            if assignment.status != "confirmed" or assignment.code is None:
                continue
            packages[assignment.item_id] = (*packages.get(assignment.item_id, ()), assignment.code)
        return packages


_ASSIGNMENT_SAFETY_NOTES: Final = (
    "Confirmação de código é ato humano rastreável; a sugestão lexical nunca confirma sozinha.",
    "Preço e unidade impressos continuam sendo conferidos contra catálogo e contrato no "
    "portão de exportação.",
)


def _assignment_decision_id(item: TakeoffItem, decision: CodeAssignmentInput) -> str:
    """Id determinístico da decisão: espelho de `_decision_id` de `takeoff.py`.

    `catalog_sha256` entra no conteúdo digerido **só quando existe**: citar outra fonte é
    outra decisão, mas incluir a chave com `null` mudaria o id de toda decisão M4-M7 já
    gravada, que continua sendo a mesma decisão. A omissão é a compatibilidade, não uma
    lacuna do conteúdo.
    """
    payload: dict[str, object] = {
        "item_id": item.id,
        "action": decision.action,
        "code": decision.code,
        "reviewer_id": decision.reviewer_id,
        "reviewer_role": decision.reviewer_role,
        "decided_at": decision.decided_at.isoformat(),
        "note": decision.note,
    }
    if decision.catalog_sha256 is not None:
        payload["catalog_sha256"] = decision.catalog_sha256
    canonical = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return f"vd_{hashlib.sha256(canonical.encode()).hexdigest()[:16]}"


def _closure_decision_id(closure: ItemPackageClosureInput) -> str:
    """Id determinístico do fechamento; irmão de `_assignment_decision_id`.

    O payload leva `"kind": "package_closure"` e não leva `code`. O discriminador é o que
    garante id distinto do de uma confirmação do mesmo item, feita pelo mesmo revisor, no
    mesmo instante — e ele mora só aqui de propósito: acrescentar uma chave ao payload de
    `_assignment_decision_id` moveria todo `vd_` já gravado desde o M4.
    """
    payload: dict[str, object] = {
        "kind": "package_closure",
        "item_id": closure.item_id,
        "reviewer_id": closure.reviewer_id,
        "reviewer_role": closure.reviewer_role,
        "decided_at": closure.decided_at.isoformat(),
        "note": closure.note,
    }
    canonical = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return f"vd_{hashlib.sha256(canonical.encode()).hexdigest()[:16]}"


def _closure_of(closure: ItemPackageClosureInput) -> ItemPackageClosure:
    """Fechamento resolvido, com a decisão humana carimbada."""
    return ItemPackageClosure(
        item_id=closure.item_id,
        decision=ReviewerDecision(
            decision_id=_closure_decision_id(closure),
            action="confirm",
            reviewer_id=closure.reviewer_id,
            reviewer_role=closure.reviewer_role,
            decided_at=closure.decided_at,
            note=closure.note,
        ),
    )


def _carried_revocations(
    previous: CodeAssignmentSet | None,
) -> list[CodeAssignmentRevocation]:
    """As revogações que o conjunto anterior leva adiante.

    Nada é construído aqui, ao contrário de `_carried_closures`: no regime `1.0.0` não existe
    revogação nenhuma para migrar, e inventar uma seria assinar um ato que ninguém praticou.
    """
    if previous is None or previous.schema_version == "1.0.0":
        return []
    return list(previous.revocations)


def _carried_closures(previous: CodeAssignmentSet | None) -> list[ItemPackageClosure]:
    """Fechamentos que o conjunto anterior leva adiante, inclusive os do regime antigo.

    Uma rodada gravada em `1.0.0` não tem `closures`, mas cada confirmação dela ERA um
    fechamento: naquele regime um código era o pacote inteiro. Ao migrar para `2.0.0` na
    primeira decisão nova, o fechamento é construído REUSANDO a `ReviewerDecision` que já
    está no assignment — o mesmo `vd_`, o mesmo autor, o mesmo instante.

    Reusar em vez de carimbar de novo é o ponto: fabricar uma decisão nova aqui seria
    assinar um ato humano que ninguém praticou, e o `decision_id` novo seria a prova de que
    o sistema inventou. A rejeição não entra porque ela já fecha o item por si.
    """
    if previous is None:
        return []
    if previous.schema_version != "1.0.0":
        return list(previous.closures)
    return [
        ItemPackageClosure(item_id=assignment.item_id, decision=assignment.decision)
        for assignment in previous.assignments
        if assignment.status == "confirmed"
    ]


def _ensure_same_plate(packet: TakeoffPacket, previous: CodeAssignmentSet) -> None:
    """O conjunto anterior é da MESMA prancha, página e imagem que o pacote em mãos.

    Extraída de `_ensure_batch_decidable` para valer também na revogação, que não tem lote:
    aplicar um ato sobre um conjunto de outra prancha gravaria decisão no lugar errado, e a
    checagem não pode existir só no caminho que a descobriu primeiro.
    """
    if (
        previous.plate_id != packet.plate_id
        or previous.page_number != packet.page_number
        or previous.image_sha256 != packet.image_sha256
    ):
        raise ValuationValidationError(
            "ASSIGNMENT_PACKET_MISMATCH",
            "conjunto de assignments anterior pertence a outra prancha",
            {
                "expected_plate_id": packet.plate_id,
                "expected_page_number": packet.page_number,
                "expected_image_sha256": packet.image_sha256,
                "previous_plate_id": previous.plate_id,
                "previous_page_number": previous.page_number,
                "previous_image_sha256": previous.image_sha256,
            },
        )


def _ensure_batch_decidable(
    packet: TakeoffPacket,
    batch: CodeAssignmentBatch,
    previous: CodeAssignmentSet | None,
    *,
    expected_catalog_sha256: str,
) -> None:
    """Pré-checagens comuns às duas confirmações de código (medição e orçamento-base).

    Na ordem: divergência de prancha/catálogo com `previous`, item desconhecido no pacote,
    item ainda não confirmado no takeoff e re-decisão de item já decidido. Nada aqui olha
    para código ou preço — isso é da confirmação em si, que difere entre as duas cadeias.
    """
    if previous is not None:
        _ensure_same_plate(packet, previous)
        if previous.catalog_sha256 != expected_catalog_sha256:
            raise ValuationValidationError(
                "ASSIGNMENT_CATALOG_MISMATCH",
                "conjunto de assignments anterior foi calculado com outro catálogo",
                {"expected": expected_catalog_sha256, "previous": previous.catalog_sha256},
            )

    known_ids = {item.id for item in packet.items}
    batch_ids = [assignment.item_id for assignment in batch.assignments]
    unknown_ids = sorted({item_id for item_id in batch_ids if item_id not in known_ids})
    if unknown_ids:
        raise ValuationValidationError(
            "ASSIGNMENT_UNKNOWN_ITEM",
            "lote de confirmação aponta para item de takeoff desconhecido",
            {"unknown_ids": unknown_ids},
        )

    items_by_id = {item.id: item for item in packet.items}
    not_confirmed = sorted(
        item_id
        for item_id in batch_ids
        if items_by_id[item_id].status is not TakeoffItemStatus.CONFIRMED
    )
    if not_confirmed:
        raise ValuationValidationError(
            "ASSIGNMENT_ITEM_NOT_CONFIRMED",
            "associação de código só existe sobre quantitativo confirmado no takeoff",
            {"item_ids": not_confirmed},
        )

    previous_pairs = (
        {(assignment.item_id, assignment.code) for assignment in previous.assignments}
        if previous
        else set()
    )
    batch_pairs = [(assignment.item_id, assignment.code) for assignment in batch.assignments]
    already_decided = sorted(
        f"{item_id}:{code}" if code is not None else item_id
        for item_id, code in dict.fromkeys(batch_pairs)
        if (item_id, code) in previous_pairs
    )
    if already_decided:
        raise ValuationValidationError(
            "ASSIGNMENT_ITEM_ALREADY_DECIDED",
            "este par de item e código já foi decidido; re-decisão é recusada",
            {"pairs": already_decided},
        )

    # A contradição entre lotes, antes da recusa por pacote fechado. A rejeição fecha o item,
    # então sem esta checagem um item rejeitado que recebesse código cairia em
    # `ASSIGNMENT_ITEM_ALREADY_CLOSED` — recusa correta com mensagem falsa, porque ninguém
    # declarou pacote nenhum como completo ali. `_ensure_package_shape` já cobre a
    # contradição DENTRO de um lote; esta cobre a que atravessa dois.
    previous_rejected = {
        assignment.item_id
        for assignment in (previous.assignments if previous else ())
        if assignment.status == "rejected"
    }
    previous_confirmed = {
        assignment.item_id
        for assignment in (previous.assignments if previous else ())
        if assignment.status == "confirmed"
    }
    contradicted = sorted(
        {
            assignment.item_id
            for assignment in batch.assignments
            if (assignment.action == "confirm" and assignment.item_id in previous_rejected)
            or (assignment.action == "reject" and assignment.item_id in previous_confirmed)
        }
    )
    if contradicted:
        raise ValuationValidationError(
            "ASSIGNMENT_REJECT_WITH_CONFIRMED",
            "rejeitar é declarar que nenhum serviço precifica o elemento; não coexiste com "
            "código confirmado para o mesmo item",
            {"item_ids": contradicted},
        )

    # A partir daqui só o pacote: acrescentar código a item já fechado, e fechar o que não
    # dá para fechar. Sem esta checagem o fechamento não afirmaria nada — bastaria mandar
    # mais um código depois dele.
    closed_ids = previous.closed_item_ids() if previous else frozenset()
    reopened = sorted({item_id for item_id in batch_ids if item_id in closed_ids})
    if reopened:
        raise ValuationValidationError(
            "ASSIGNMENT_ITEM_ALREADY_CLOSED",
            "o pacote deste item já foi declarado completo; acrescentar código é recusado",
            {"item_ids": reopened},
        )

    closure_ids = [closure.item_id for closure in batch.closures]
    unknown_closures = sorted({item_id for item_id in closure_ids if item_id not in known_ids})
    if unknown_closures:
        raise ValuationValidationError(
            "ASSIGNMENT_UNKNOWN_ITEM",
            "fechamento de pacote aponta para item de takeoff desconhecido",
            {"unknown_ids": unknown_closures},
        )

    already_closed = sorted({item_id for item_id in closure_ids if item_id in closed_ids})
    if already_closed:
        raise ValuationValidationError(
            "ASSIGNMENT_DUPLICATE_CLOSURE",
            "o pacote deste item já foi declarado completo",
            {"item_ids": already_closed},
        )

    # Fechar exige ter o que fechar. A checagem também existe no modelo do conjunto, mas
    # aqui ela chega ANTES da montagem: quem chamou recebe o código de domínio estável em
    # vez do erro de validação do Pydantic embrulhando a mesma coisa.
    confirmed_ids = {
        assignment.item_id
        for assignment in (previous.assignments if previous else ())
        if assignment.status == "confirmed"
    } | {assignment.item_id for assignment in batch.assignments if assignment.action == "confirm"}
    empty_closures = sorted({item_id for item_id in closure_ids if item_id not in confirmed_ids})
    if empty_closures:
        raise ValuationValidationError(
            "ASSIGNMENT_CLOSURE_WITHOUT_ASSIGNMENT",
            "fechamento de pacote exige ao menos um código confirmado para o item; "
            "rejeição já fecha o item sozinha",
            {"item_ids": empty_closures},
        )

    # F-047 T5 (ADR-0058 decisão 6): o item não fecha enquanto a divergência entre a
    # quantidade da cena e a lida na legenda estiver aberta. Fechar é afirmar que o pacote
    # do elemento acabou, e não acabou enquanto ninguém disse QUAL das duas quantidades vale.
    # A recusa é só do FECHAMENTO: confirmar código a um item divergente continua permitido,
    # porque saber qual serviço precifica o elemento não depende de quanto ele mede.
    divergent_closures = sorted(
        {item_id for item_id in closure_ids if items_by_id[item_id].has_open_divergence()}
    )
    if divergent_closures:
        raise ValuationValidationError(
            "ASSIGNMENT_QUANTITY_DIVERGENCE_OPEN",
            "o item tem divergência de quantidade em aberto entre a cena e a legenda; "
            "resolva a divergência antes de declarar o pacote completo",
            {"item_ids": divergent_closures},
        )


def _inputs_by_item(batch: CodeAssignmentBatch) -> dict[str, list[CodeAssignmentInput]]:
    """Decisões do lote agrupadas por item, preservando a ordem de chegada.

    Era um `dict[str, CodeAssignmentInput]`, e a troca para lista é a cardinalidade em si:
    o dict de antes ficava com a ÚLTIMA decisão de cada item e descartava as outras sem
    dizer nada. Sob N:N isso silenciaria cinco dos seis códigos de um elemento.

    A ordem importa e é a do lote: é ela que decide em que sequência os pares entram no
    conjunto, e daí a numeração das linhas do boletim. `valuation-demo` é golden.
    """
    grouped: dict[str, list[CodeAssignmentInput]] = {}
    for assignment in batch.assignments:
        grouped.setdefault(assignment.item_id, []).append(assignment)
    return grouped


def _is_single_code_item(
    previous_codes: Mapping[str, tuple[str, ...]],
    item_id: str,
    item_inputs: Sequence[CodeAssignmentInput],
) -> bool:
    """O item termina esta aplicação com exatamente um código confirmado?

    É a condição do regime espelho, onde a recusa de unidade divergente continua valendo.
    Conta o conjunto RESULTANTE — o que já estava em `previous` mais o que este lote traz —,
    porque é o resultado que diz se o elemento virou pacote ou continua 1:1.

    Consequência aceita e declarada no ADR-0053: um pacote montado em lotes sucessivos passa
    por este estado no primeiro lote, e ali a recusa ainda se aplica. Seguir a regra ao pé
    da letra é preferível a inventar uma terceira, que precisaria adivinhar a intenção de
    quem ainda não mandou o segundo código.
    """
    confirmed_now = sum(1 for entry in item_inputs if entry.action == "confirm")
    return len(previous_codes.get(item_id, ())) + confirmed_now == 1


def _rejected_assignment(
    item: TakeoffItem, input_assignment: CodeAssignmentInput
) -> CodeAssignment:
    """Rejeição de código: nenhum preço, nenhuma fonte, decisão humana preservada."""
    return CodeAssignment(
        item_id=item.id,
        status="rejected",
        code=None,
        catalog_sha256=None,
        unit_compatible=False,
        decision=ReviewerDecision(
            decision_id=_assignment_decision_id(item, input_assignment),
            action="reject",
            reviewer_id=input_assignment.reviewer_id,
            reviewer_role=input_assignment.reviewer_role,
            decided_at=input_assignment.decided_at,
            note=input_assignment.note,
        ),
    )


def _confirmed_assignment(
    item: TakeoffItem,
    input_assignment: CodeAssignmentInput,
    entry: PriceCatalogEntry,
    *,
    catalog_sha256: str | None,
    single_code_item: bool,
) -> CodeAssignment:
    """Confirmação de código já resolvida contra a entrada de catálogo escolhida.

    A unidade incompatível sem nota recusa aqui, nas duas cadeias — mas só quando o item
    tem EXATAMENTE um código confirmado, o regime espelho em que a unidade do elemento e a
    do serviço deveriam mesmo coincidir (ADR-0053, consequência declarada).

    Com pacote, a divergência é o caso normal e não o suspeito: um elemento medido em m²
    alimenta legitimamente saibro em m³, tela em kg e meio-fio em m. Recusar ali faria a
    nota virar ruído em toda confirmação, e nota que sempre aparece é nota que ninguém lê —
    o resultado seria menos atenção sobre a divergência, não mais. Quem explica a conversão
    no mundo do pacote é a `basis`/`recipe` da contribuição.

    `unit_compatible` continua gravado como observação nos dois regimes: o que muda é
    quando o sistema RECUSA, nunca o que ele registra.
    """
    code = entry.code
    unit_compatible = normalize_unit(item.unit) == normalize_unit(entry.unit)
    if single_code_item and not unit_compatible and input_assignment.note is None:
        raise ValuationValidationError(
            "ASSIGNMENT_UNIT_INCOMPATIBLE_WITHOUT_NOTE",
            "unidade do item diverge da unidade do catálogo; confirme com nota explícita",
            {
                "item_id": item.id,
                "code": code,
                "item_unit": item.unit,
                "catalog_unit": entry.unit,
            },
        )
    return CodeAssignment(
        item_id=item.id,
        status="confirmed",
        code=code,
        catalog_sha256=catalog_sha256,
        unit_compatible=unit_compatible,
        decision=ReviewerDecision(
            decision_id=_assignment_decision_id(item, input_assignment),
            action="confirm",
            reviewer_id=input_assignment.reviewer_id,
            reviewer_role=input_assignment.reviewer_role,
            decided_at=input_assignment.decided_at,
            note=input_assignment.note,
        ),
    )


def apply_code_assignments(
    packet: TakeoffPacket,
    batch: CodeAssignmentBatch,
    catalog: PriceCatalog,
    contract: ContractWorkbook | None = None,
    *,
    previous: CodeAssignmentSet | None = None,
) -> CodeAssignmentSet:
    """Cria um novo `CodeAssignmentSet` imutável; nunca muta `packet`, `batch` ou `previous`.

    Fail-closed, na ordem: divergência de pacote/catálogo com `previous`, item
    desconhecido no pacote, item não confirmado no takeoff, re-decisão de item já
    presente em `previous`, e por fim as checagens específicas de confirmação (código no
    catálogo, código no contrato, unidade compatível ou nota explícita).

    Divergência de preço/unidade entre catálogo e contrato não é checada aqui: o portão
    de exportação (`Valuation.export_errors`) já responde por isso via
    `LINE_PRICE_NOT_IN_CONTRACT`/`LINE_UNIT_NOT_IN_CONTRACT`; duplicar a checagem aqui
    adiantaria uma decisão que o portão já toma de forma auditável.

    A rodada aqui tem **um** catálogo. Uma decisão pode citá-lo (`catalog_sha256`), e nesse
    caso a citação é conferida contra ele (`ASSIGNMENT_CATALOG_UNKNOWN`) e carregada adiante
    no assignment; decisão sem citação — o caso de toda a medição — continua exatamente como
    antes. Confirmação sobre mais de uma fonte é `apply_code_assignments_over_cascade`.
    """
    _ensure_batch_decidable(packet, batch, previous, expected_catalog_sha256=catalog.source_sha256)

    inputs_by_item = _inputs_by_item(batch)
    previous_codes = previous.confirmed_codes_by_item() if previous is not None else {}
    new_assignments: list[CodeAssignment] = []
    for item in packet.items:
        item_inputs = inputs_by_item.get(item.id)
        if item_inputs is None:
            continue

        single_code_item = _is_single_code_item(previous_codes, item.id, item_inputs)
        for input_assignment in item_inputs:
            if input_assignment.action == "reject":
                new_assignments.append(_rejected_assignment(item, input_assignment))
                continue

            code = input_assignment.code
            assert code is not None  # garantido por ASSIGNMENT_CODE_REQUIRED no modelo de input
            cited_catalog = input_assignment.catalog_sha256
            if cited_catalog is not None and cited_catalog != catalog.source_sha256:
                raise ValuationValidationError(
                    "ASSIGNMENT_CATALOG_UNKNOWN",
                    "decisão cita uma fonte de preço que não é o catálogo desta rodada",
                    {
                        "item_id": item.id,
                        "cited": cited_catalog,
                        "available": catalog.source_sha256,
                    },
                )
            if not catalog.has_code(code):
                raise ValuationValidationError(
                    "ASSIGNMENT_CODE_NOT_IN_CATALOG",
                    "código confirmado não existe no catálogo de preços importado",
                    {"item_id": item.id, "code": code},
                )
            if contract is not None:
                matches = contract.lines_for_code(code)
                if not matches:
                    raise ValuationValidationError(
                        "CODE_NOT_IN_CONTRACT",
                        "código confirmado não existe no consolidado contratual importado",
                        {"item_id": item.id, "code": code},
                    )
                if len(matches) > 1:
                    raise ValuationValidationError(
                        "CODE_AMBIGUOUS_IN_CONTRACT",
                        "código confirmado existe em mais de um grupo do consolidado contratual",
                        {
                            "item_id": item.id,
                            "code": code,
                            "groups": [line.group_label for line in matches],
                        },
                    )

            new_assignments.append(
                _confirmed_assignment(
                    item,
                    input_assignment,
                    catalog.entry_for(code),
                    catalog_sha256=cited_catalog,
                    single_code_item=single_code_item,
                )
            )

    previous_assignments = list(previous.assignments) if previous is not None else []
    return CodeAssignmentSet(
        plate_id=packet.plate_id,
        page_number=packet.page_number,
        image_sha256=packet.image_sha256,
        catalog_sha256=catalog.source_sha256,
        contract_sha256=contract.source_sha256 if contract else None,
        assignments=[*previous_assignments, *new_assignments],
        closures=[*_carried_closures(previous), *(_closure_of(c) for c in batch.closures)],
        # O que já foi desfeito continua registrado: confirmar outro código não apaga o ato
        # de quem desfez um. Um par revogado que volta a ser confirmado aparece nos dois
        # lugares, e é a leitura que decide o que mostrar (ADR-0061 D2/D5).
        revocations=_carried_revocations(previous),
        safety_notes=list(_ASSIGNMENT_SAFETY_NOTES),
    )


def _revocation_id(revocation: CodeAssignmentRevocationInput) -> str:
    """Id determinístico da revogação; irmão de `_assignment_decision_id`.

    Prefixo próprio (`vr_`) e não `vd_`: revogar não é uma decisão sobre o código, é um ato
    sobre uma decisão, e misturar os dois espaços faria uma busca por `vd_` devolver coisas
    de naturezas diferentes.
    """
    canonical = json.dumps(
        {
            "kind": "assignment_revocation",
            "item_id": revocation.item_id,
            "code": revocation.code,
            "reviewer_id": revocation.reviewer_id,
            "reviewer_role": revocation.reviewer_role,
            "revoked_at": revocation.revoked_at.isoformat(),
            "note": revocation.note,
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return f"vr_{hashlib.sha256(canonical.encode()).hexdigest()[:16]}"


def apply_code_revocation(
    packet: TakeoffPacket,
    revocation: CodeAssignmentRevocationInput,
    previous: CodeAssignmentSet,
) -> CodeAssignmentSet:
    """Retira do conjunto corrente um par `(item, código)` já confirmado (F-045, ADR-0061).

    O que ela faz, e por quê:

    - **o par sai de `assignments`** em vez de ganhar um status novo. Marcar como revogado o
      manteria na lista, e todo consumidor — boletim, exportação, precedente, contagens —
      passaria a depender de lembrar de filtrar; um consumidor esquecido imprimiria linha
      revogada. Sair da lista é falha fechada (D2);
    - **o registro entra em `revocations`**, com autor, instante e motivo, para que o conjunto
      corrente distinga "nunca decidido" de "decidido e desfeito";
    - **o fechamento do item cai junto**. A completude foi afirmada sobre um pacote que acabou
      de mudar, e mantê-la deixaria em pé uma afirmação que ninguém refez (D3). O efeito
      adiante é real e é o desejado: o portão de exportação volta a recusar aquele elemento
      até alguém fechar de novo;
    - **o código não é banido**: depois disto o mesmo par volta a ser decidível, porque a
      recusa de re-decisão olha para `assignments`, de onde ele saiu (D5).

    O que ela **não** faz: tocar em revisão gravada. Quem chama grava o conjunto devolvido
    como revisão nova, e a anterior continua existindo com o par confirmado lá dentro (D1).
    """
    if previous.schema_version == "1.0.0":
        raise ValuationValidationError(
            "ASSIGNMENT_REVOCATION_NOT_SUPPORTED",
            "esta rodada é do regime de um código por elemento; nela não há pacote para desfazer",
            {"item_id": revocation.item_id, "code": revocation.code},
        )

    _ensure_same_plate(packet, previous)

    known_ids = {item.id for item in packet.items}
    if revocation.item_id not in known_ids:
        raise ValuationValidationError(
            "ASSIGNMENT_UNKNOWN_ITEM",
            "revogação aponta para item de takeoff desconhecido",
            {"unknown_ids": [revocation.item_id]},
        )

    target = [
        assignment
        for assignment in previous.assignments
        if assignment.item_id == revocation.item_id
        and assignment.status == "confirmed"
        and assignment.code == revocation.code
    ]
    if not target:
        raise ValuationValidationError(
            "ASSIGNMENT_REVOCATION_PAIR_UNKNOWN",
            "não há código confirmado com este par de elemento e código para desfazer",
            {"item_id": revocation.item_id, "code": revocation.code},
        )

    remaining = [assignment for assignment in previous.assignments if assignment not in target]
    # O fechamento do item cai com a revogação — inclusive quando sobram outros códigos no
    # pacote: o que se afirmou completo foi um pacote com este código dentro.
    closures = [
        closure for closure in _carried_closures(previous) if closure.item_id != revocation.item_id
    ]
    return CodeAssignmentSet(
        schema_version=previous.schema_version,
        plate_id=previous.plate_id,
        page_number=previous.page_number,
        image_sha256=previous.image_sha256,
        catalog_sha256=previous.catalog_sha256,
        contract_sha256=previous.contract_sha256,
        assignments=remaining,
        closures=closures,
        revocations=[
            *_carried_revocations(previous),
            CodeAssignmentRevocation(
                item_id=revocation.item_id,
                code=revocation.code,
                revocation_id=_revocation_id(revocation),
                reviewer_id=revocation.reviewer_id,
                reviewer_role=revocation.reviewer_role,
                revoked_at=revocation.revoked_at,
                note=revocation.note,
            ),
        ],
        safety_notes=list(previous.safety_notes),
    )


def apply_code_assignments_over_cascade(
    packet: TakeoffPacket,
    batch: CodeAssignmentBatch,
    cascade: Sequence[PriceCatalog],
    *,
    previous: CodeAssignmentSet | None = None,
) -> CodeAssignmentSet:
    """Confirmação de código do ORÇAMENTO-BASE: a decisão cita de qual fonte veio o preço.

    Irmã de `apply_code_assignments`, com as mesmas pré-checagens fail-closed
    (`_ensure_batch_decidable`) e a mesma regra de unidade. As diferenças são as da
    pré-licitação:

    - a rodada tem mais de uma fonte, então **toda confirmação cita** a sua
      (`ASSIGNMENT_CATALOG_REQUIRED`) — resolver o código "na ordem da cascata" faria a
      máquina escolher a tabela que precifica o item, e essa escolha é do orçamentista;
    - a citação precisa estar na cascata (`ASSIGNMENT_CATALOG_UNKNOWN`) e o código precisa
      existir naquele catálogo (`ASSIGNMENT_CODE_NOT_IN_CATALOG`), nunca em outro dela;
    - não há contrato: contrato é da obra licitada, e lá a cascata não existe (`ADR-0027`).

    O cabeçalho do conjunto (`catalog_sha256`) fica com o catálogo CABEÇA da cascata, que é
    o que amarra o conjunto à rodada; a fonte de cada linha é a citada em cada assignment.
    """
    ensure_price_cascade(cascade)
    catalogs_by_digest = {catalog.source_sha256: catalog for catalog in cascade}
    _ensure_batch_decidable(
        packet, batch, previous, expected_catalog_sha256=cascade[0].source_sha256
    )

    inputs_by_item = _inputs_by_item(batch)
    previous_codes = previous.confirmed_codes_by_item() if previous is not None else {}
    new_assignments: list[CodeAssignment] = []
    for item in packet.items:
        item_inputs = inputs_by_item.get(item.id)
        if item_inputs is None:
            continue

        single_code_item = _is_single_code_item(previous_codes, item.id, item_inputs)
        for input_assignment in item_inputs:
            if input_assignment.action == "reject":
                new_assignments.append(_rejected_assignment(item, input_assignment))
                continue

            code = input_assignment.code
            assert code is not None  # garantido por ASSIGNMENT_CODE_REQUIRED no modelo de input
            cited_catalog = input_assignment.catalog_sha256
            if cited_catalog is None:
                raise ValuationValidationError(
                    "ASSIGNMENT_CATALOG_REQUIRED",
                    "com mais de uma fonte de preço, a confirmação precisa citar de qual "
                    "catálogo o código veio",
                    {"item_id": item.id, "code": code},
                )
            catalog = catalogs_by_digest.get(cited_catalog)
            if catalog is None:
                raise ValuationValidationError(
                    "ASSIGNMENT_CATALOG_UNKNOWN",
                    "decisão cita uma fonte de preço que não está na cascata desta rodada",
                    {
                        "item_id": item.id,
                        "cited": cited_catalog,
                        "available": [entry.source_sha256 for entry in cascade],
                    },
                )
            if not catalog.has_code(code):
                raise ValuationValidationError(
                    "ASSIGNMENT_CODE_NOT_IN_CATALOG",
                    "código confirmado não existe no catálogo citado pela decisão",
                    {"item_id": item.id, "code": code, "catalog_sha256": cited_catalog},
                )

            new_assignments.append(
                _confirmed_assignment(
                    item,
                    input_assignment,
                    catalog.entry_for(code),
                    catalog_sha256=cited_catalog,
                    single_code_item=single_code_item,
                )
            )

    previous_assignments = list(previous.assignments) if previous is not None else []
    return CodeAssignmentSet(
        plate_id=packet.plate_id,
        page_number=packet.page_number,
        image_sha256=packet.image_sha256,
        catalog_sha256=cascade[0].source_sha256,
        contract_sha256=None,
        assignments=[*previous_assignments, *new_assignments],
        closures=[*_carried_closures(previous), *(_closure_of(c) for c in batch.closures)],
        # O que já foi desfeito continua registrado: confirmar outro código não apaga o ato
        # de quem desfez um. Um par revogado que volta a ser confirmado aparece nos dois
        # lugares, e é a leitura que decide o que mostrar (ADR-0061 D2/D5).
        revocations=_carried_revocations(previous),
        safety_notes=list(_ASSIGNMENT_SAFETY_NOTES),
    )
