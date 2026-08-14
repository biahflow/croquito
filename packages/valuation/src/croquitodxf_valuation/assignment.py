"""Sugestão lexical de código SCO e confirmação de código pelo orçamentista.

Espelho deliberado de `services/worker/src/croquitodxf_worker/association.py`: o
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
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Final, Literal

from pydantic import Field, field_validator, model_validator

from croquitodxf_valuation.catalog import DomainSynonyms, lexical_similarity, normalize_unit
from croquitodxf_valuation.contract import ContractWorkbook
from croquitodxf_valuation.errors import ValuationValidationError
from croquitodxf_valuation.models import (
    MAX_DESCRIPTION_LENGTH,
    SHA256_PATTERN,
    ExactDecimal,
    PriceCatalog,
    ReviewerDecision,
    ValuationContractModel,
)
from croquitodxf_valuation.sco import SCO_CODE_PATTERN
from croquitodxf_valuation.takeoff import TakeoffItem, TakeoffItemStatus, TakeoffPacket

SUGGESTION_SCHEMA_VERSION: Final = "1.1.0"
"""Não bumpou na Fase 1 do M7 (léxico melhorado + sinônimos), de propósito: nenhum campo
mudou de forma, só de comportamento (`unmatched_item_ids` fica mais raro porque o corte de
`min_lexical_score` caiu, e `CodeCandidate.lexical_score` pode refletir score calculado com
sinônimo). Um artefato 1.1.0 antigo continua carregável pelo mesmo `CodeSuggestionSet`;
`synonyms`/`ExpandedTerms` não têm campo correspondente no artefato — a expansão é
`expanded_terms` da CAMADA do servidor local (observação de busca), não do suggester."""
ASSIGNMENT_SCHEMA_VERSION: Final = "1.0.0"
SCO_SUGGESTER_VERSION: Final = "lexical-sco-suggester-v1"

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

LLM_RERANK_SUFFIX: Final = "+llm-rerank-v1"
"""Sufixo que o refino pago acrescenta ao suggester que produziu a shortlist de entrada."""

SCO_REFINED_SUGGESTER_VERSION: Final = SCO_SUGGESTER_VERSION + LLM_RERANK_SUFFIX
"""A shortlist lexical **depois** de reordenada e anotada pela via paga.

O nome carrega os dois estágios de propósito: o refino não substitui o suggester lexical,
ele opera sobre a saída dele. Quem lê o artefato sabe, pela versão, que a ordem publicada
passou por um provider — e o bloco `refinement` diz por qual."""

SCO_REFINED_HYBRID_SUGGESTER_VERSION: Final = SCO_HYBRID_SUGGESTER_VERSION + LLM_RERANK_SUFFIX
"""A shortlist híbrida depois do refino pago: os dois lineages viajam juntos no artefato."""

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

    `code` exige o padrão SCO estrito (não a forma nua do contrato): só código com preço
    publicado no catálogo é candidato, e a forma nua nunca tem preço.

    `refinement_note` só existe depois de `apply_refinement`: é a justificativa do refino
    pago para a ordem publicada, anotada no candidato que ficou em primeiro. Ela é
    observação anexada ao candidato, nunca um campo que altere preço, unidade ou score.
    """

    code: str = Field(pattern=SCO_CODE_PATTERN)
    description: str = Field(min_length=1, max_length=MAX_DESCRIPTION_LENGTH)
    unit: str = Field(min_length=1, max_length=20)
    unit_price: ExactDecimal = Field(ge=0)
    unit_compatible: bool
    in_contract: bool
    lexical_score: float = Field(ge=0, le=1)
    status: Literal["suggested"] = "suggested"
    refinement_note: str | None = Field(default=None, max_length=_REFINEMENT_NOTE_MAX_LENGTH)


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
    """Lineage do braço semântico que participou da fusão.

    Embedding não tem prompt: o que identifica a ordem produzida é o modelo, a dimensão do
    espaço e o digest do índice do catálogo usado (`catalog-embeddings.json`). O digest do
    próprio catálogo já viaja em `CodeSuggestionSet.catalog_sha256`, e é o índice que fica
    amarrado a ele — trocar de índice sem trocar de catálogo aparece aqui.

    `provider` é string simples pelo mesmo motivo de `SuggestionRefinement.provider`: o
    `ADR-0016` proíbe este pacote de importar o enum de provider do worker.
    """

    provider: str = Field(min_length=1, max_length=40)
    model_id: str = Field(min_length=1, max_length=160)
    dims: int = Field(ge=1, le=8192)
    index_sha256: str = Field(pattern=SHA256_PATTERN)


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
    """

    schema_version: Literal["1.1.0"] = SUGGESTION_SCHEMA_VERSION
    plate_id: str = Field(min_length=1, max_length=64)
    page_number: int = Field(ge=1)
    image_sha256: str = Field(pattern=SHA256_PATTERN)
    catalog_sha256: str = Field(pattern=SHA256_PATTERN)
    contract_sha256: str | None = Field(default=None, pattern=SHA256_PATTERN)
    suggester_version: Literal[
        "lexical-sco-suggester-v1",
        "lexical-sco-suggester-v1+llm-rerank-v1",
        "hybrid-sco-suggester-v1",
        "hybrid-sco-suggester-v1+llm-rerank-v1",
        "hybrid-sco-suggester-v2",
        "hybrid-sco-suggester-v2+llm-rerank-v1",
    ] = SCO_SUGGESTER_VERSION
    refinement: SuggestionRefinement | None = None
    semantic: SuggestionSemantics | None = None
    suggestions: list[CodeSuggestion]
    unmatched_item_ids: list[str]
    safety_notes: list[str] = Field(min_length=3)

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

    max_candidates_per_item: int = 3
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
) -> CodeSuggestionSet:
    """Aplica o refino pago sobre a shortlist lexical; nunca muta o conjunto de entrada.

    Reordenar e anotar é tudo o que o refino pode fazer. A ordem pedida para um item tem
    de ser **permutação exata** dos códigos que a via lexical já elegeu para ele: código
    novo, código a mais ou código a menos recusa com `REFINEMENT_CODES_MISMATCH`, porque
    aceitar qualquer um dos três deixaria o provider substituir a shortlist em vez de
    refiná-la. Item citado que não existe no conjunto recusa com
    `REFINEMENT_UNKNOWN_ITEM`; item do conjunto que o refino não citou mantém a ordem
    lexical intocada, sem nota.

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
        if ranked is not None and sorted(ranked) != sorted(shortlist):
            raise ValuationValidationError(
                "REFINEMENT_CODES_MISMATCH",
                "ordem refinada deve ser permutação exata da shortlist lexical do item",
                {
                    "item_id": suggestion.item_id,
                    "shortlist": sorted(shortlist),
                    "ranked": list(ranked),
                },
            )
        ordered = (
            list(suggestion.candidates)
            if ranked is None
            else [candidates_by_code[code] for code in ranked]
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


class CodeAssignmentInput(ValuationContractModel):
    """Decisão do orçamentista sobre o código de um item; espelho de `TakeoffDecisionInput`.

    `code` não declara `pattern` no campo: a validação usa `re.fullmatch` explícito no
    validador de modelo para que a falha suba como `ASSIGNMENT_CODE_INVALID` (código
    estável), em vez do erro genérico de padrão que o Pydantic devolveria sem o embrulho
    de `ValuationValidationError`.
    """

    item_id: str = Field(pattern=_ITEM_ID_PATTERN)
    action: Literal["confirm", "reject"]
    code: str | None = None
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
        if self.code is not None and re.fullmatch(SCO_CODE_PATTERN, self.code) is None:
            raise ValuationValidationError(
                "ASSIGNMENT_CODE_INVALID",
                "código informado não tem a estrutura de um código SCO com preço publicado",
                {"item_id": self.item_id, "code": self.code},
            )
        return self


class CodeAssignmentBatch(ValuationContractModel):
    """Lote de decisões de confirmação de código; no máximo uma decisão por item."""

    assignments: list[CodeAssignmentInput] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_unique_items(self) -> CodeAssignmentBatch:
        item_ids = [assignment.item_id for assignment in self.assignments]
        if len(item_ids) != len(set(item_ids)):
            raise ValuationValidationError(
                "ASSIGNMENT_DUPLICATE_ITEM",
                "um item só pode receber uma decisão de código por lote",
                {"item_ids": sorted(item_ids)},
            )
        return self


class CodeAssignment(ValuationContractModel):
    """Resultado imutável da confirmação/rejeição de código de um item."""

    item_id: str = Field(pattern=_ITEM_ID_PATTERN)
    status: Literal["confirmed", "rejected"]
    code: str | None = None
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
        return self


class CodeAssignmentSet(ValuationContractModel):
    """Conjunto imutável de confirmações/rejeições de código de uma prancha."""

    schema_version: Literal["1.0.0"] = ASSIGNMENT_SCHEMA_VERSION
    plate_id: str = Field(min_length=1, max_length=64)
    page_number: int = Field(ge=1)
    image_sha256: str = Field(pattern=SHA256_PATTERN)
    catalog_sha256: str = Field(pattern=SHA256_PATTERN)
    contract_sha256: str | None = Field(default=None, pattern=SHA256_PATTERN)
    assignments: list[CodeAssignment]
    safety_notes: list[str] = Field(min_length=2)

    @model_validator(mode="after")
    def validate_unique_items(self) -> CodeAssignmentSet:
        item_ids = [assignment.item_id for assignment in self.assignments]
        duplicated = sorted({item_id for item_id in item_ids if item_ids.count(item_id) > 1})
        if duplicated:
            raise ValuationValidationError(
                "ASSIGNMENT_DUPLICATE_ITEM",
                "há mais de um assignment para o mesmo item",
                {"item_ids": duplicated},
            )
        return self


_ASSIGNMENT_SAFETY_NOTES: Final = (
    "Confirmação de código é ato humano rastreável; a sugestão lexical nunca confirma sozinha.",
    "Preço e unidade impressos continuam sendo conferidos contra catálogo e contrato no "
    "portão de exportação.",
)


def _assignment_decision_id(item: TakeoffItem, decision: CodeAssignmentInput) -> str:
    """Id determinístico da decisão: espelho de `_decision_id` de `takeoff.py`."""
    canonical = json.dumps(
        {
            "item_id": item.id,
            "action": decision.action,
            "code": decision.code,
            "reviewer_id": decision.reviewer_id,
            "reviewer_role": decision.reviewer_role,
            "decided_at": decision.decided_at.isoformat(),
            "note": decision.note,
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return f"vd_{hashlib.sha256(canonical.encode()).hexdigest()[:16]}"


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
    """
    if previous is not None:
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
        if previous.catalog_sha256 != catalog.source_sha256:
            raise ValuationValidationError(
                "ASSIGNMENT_CATALOG_MISMATCH",
                "conjunto de assignments anterior foi calculado com outro catálogo",
                {"expected": catalog.source_sha256, "previous": previous.catalog_sha256},
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

    previous_ids = (
        {assignment.item_id for assignment in previous.assignments} if previous else set()
    )
    already_decided = sorted(set(batch_ids) & previous_ids)
    if already_decided:
        raise ValuationValidationError(
            "ASSIGNMENT_ITEM_ALREADY_DECIDED",
            "item já possui confirmação de código anterior; re-decisão é recusada",
            {"item_ids": already_decided},
        )

    assignments_by_item = {assignment.item_id: assignment for assignment in batch.assignments}
    new_assignments: list[CodeAssignment] = []
    for item in packet.items:
        input_assignment = assignments_by_item.get(item.id)
        if input_assignment is None:
            continue

        if input_assignment.action == "reject":
            decision = ReviewerDecision(
                decision_id=_assignment_decision_id(item, input_assignment),
                action="reject",
                reviewer_id=input_assignment.reviewer_id,
                reviewer_role=input_assignment.reviewer_role,
                decided_at=input_assignment.decided_at,
                note=input_assignment.note,
            )
            new_assignments.append(
                CodeAssignment(
                    item_id=item.id,
                    status="rejected",
                    code=None,
                    unit_compatible=False,
                    decision=decision,
                )
            )
            continue

        code = input_assignment.code
        assert code is not None  # garantido por ASSIGNMENT_CODE_REQUIRED no modelo de input
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

        entry = catalog.entry_for(code)
        unit_compatible = normalize_unit(item.unit) == normalize_unit(entry.unit)
        if not unit_compatible and input_assignment.note is None:
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

        decision = ReviewerDecision(
            decision_id=_assignment_decision_id(item, input_assignment),
            action="confirm",
            reviewer_id=input_assignment.reviewer_id,
            reviewer_role=input_assignment.reviewer_role,
            decided_at=input_assignment.decided_at,
            note=input_assignment.note,
        )
        new_assignments.append(
            CodeAssignment(
                item_id=item.id,
                status="confirmed",
                code=code,
                unit_compatible=unit_compatible,
                decision=decision,
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
        safety_notes=list(_ASSIGNMENT_SAFETY_NOTES),
    )
