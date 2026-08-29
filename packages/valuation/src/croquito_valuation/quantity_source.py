"""`QuantitySource`: a quantidade da cena aprovada atravessa a fronteira até a legenda.

O adaptador que o `docs/product/ROADMAP.md` reservava e o ADR-0058 decidiu (decisão 5):
ler o `quantitativos.csv` do pacote exportado e alimentar o item de
legenda **pela identidade declarada**, `element_ref` dos dois lados. Não existe casamento
por número igual, por rótulo parecido ou por balão mais próximo: sem identidade num dos
lados o adaptador **não resolve** e diz por quê — a ausência de par é estado legível, nunca
palpite silencioso.

Três limites atravessam o módulo inteiro:

- **Só `exact` e `derived` alimentam** (decisão 4 com a emenda humana de 2026-08-28).
  `approximate` não entra nem com aceite de aproximação registrado na cena, porque o
  carimbo de aproximação sobrevive à tela e morre na planilha, onde o número vira R$.
- **A precisão nunca sobe**: o item nasce com a precisão que a linha da cena declarou.
- **A quantidade só existe a partir de cena aprovada** (decisão 7). Este módulo não
  reimplementa o portão: ele lê um arquivo que só é escrito depois de `ensure_exportable`
  e da auditoria do DXF. Nenhum caminho novo contorna o portão porque não há caminho novo —
  há um leitor do que o portão já deixou passar. Por isso o módulo não importa nada do
  worker (o `ADR-0016` proíbe), e conversa com a cena apenas pelo CSV e pelo vocabulário
  compartilhado do núcleo (`ELEMENT_REF_PATTERN`, `Precision`).

A **divergência** entre a quantidade da cena e a lida na legenda é detectada aqui (F-047 T5)
e nunca conciliada: `feed` recusa alimentar um item que já traz número da legenda, e
`divergence_for`/`record_divergence` gravam os DOIS números com as duas origens para que
alguém decida. A aritmética da tolerância e os modelos da issue vivem em
`quantity_divergence.py`; este módulo é quem confronta a cena com a legenda porque é ele
quem tem o CSV em mãos.
"""

from __future__ import annotations

import csv
from collections.abc import Iterable, Sequence
from decimal import Decimal, InvalidOperation
from enum import StrEnum
from io import StringIO
from pathlib import Path
from typing import Final

from pydantic import Field, model_validator

from croquito_core.models import ELEMENT_REF_PATTERN, Precision
from croquito_valuation.catalog import normalize_unit
from croquito_valuation.errors import ValuationValidationError
from croquito_valuation.models import (
    SCENE_ELIGIBLE_PRECISIONS,
    TAKEOFF_ITEM_ID_PATTERN,
    ExactDecimal,
    ValuationContractModel,
)
from croquito_valuation.quantity_divergence import (
    LegendQuantityOrigin,
    QuantityDivergence,
    SceneQuantityOrigin,
    quantity_divergence_ratio,
    quantity_divergence_tolerance_breakdown,
)
from croquito_valuation.takeoff import TakeoffItem, TakeoffItemStatus

SCENE_QUANTITY_COLUMNS: Final = (
    "entity_id",
    "layer",
    "kind",
    "precision",
    "length_m",
    "perimeter_m",
    "area_m2",
)
"""Colunas que `croquito_worker.dxf._write_quantities` sempre escreve."""

SCENE_QUANTITY_IDENTITY_COLUMN: Final = "element_ref"
"""Coluna aditiva da F-047 T3: só aparece quando alguma entidade exportável declarou
identidade. Croqui sem nenhuma continua saindo com as sete colunas de sempre, e o leitor
aceita os dois cabeçalhos — sem a coluna, nenhuma linha resolve, que é o comportamento
correto e não um erro de formato."""

_LENGTH_UNIT: Final = "m"
_AREA_UNIT: Final = "m2"


class QuantityDimension(StrEnum):
    """A grandeza física que a unidade do item pede da cena.

    Só estas duas existem porque só estas duas o `quantitativos.csv` produz. Unidade de
    contagem (`un`), de volume (`m3`) ou de tempo (`mes`) não tem grandeza correspondente
    na cena: o adaptador recusa em vez de converter.
    """

    LENGTH = "length"
    AREA = "area"


class QuantityUnresolvedReason(StrEnum):
    """Por que a quantidade da cena NÃO alimentou o item. Cada motivo é uma recusa nomeada.

    O chamador lê o enum, nunca o texto: é o mesmo contrato dos códigos de erro do módulo.
    """

    ITEM_WITHOUT_ELEMENT_REF = "item_without_element_ref"
    """O item de legenda não declarou identidade de elemento."""

    ELEMENT_REF_ABSENT_FROM_SCENE = "element_ref_absent_from_scene"
    """A identidade do item não aparece em nenhuma linha do `quantitativos.csv`."""

    PRECISION_NOT_ELIGIBLE = "precision_not_eligible"
    """A linha da cena é `approximate` ou `unresolved`: não atravessa a fronteira."""

    UNIT_NOT_DERIVABLE_FROM_SCENE = "unit_not_derivable_from_scene"
    """A unidade do item não é de comprimento nem de área; a cena não a produz."""

    UNIT_MISMATCH = "unit_mismatch"
    """A linha traz a outra grandeza: área para item em metro, comprimento para item em m²."""

    LENGTH_AMBIGUOUS = "length_ambiguous"
    """A linha traz comprimento E perímetro; somar os dois inventaria qual deles a legenda
    mede, e escolher um por conta própria seria palpite."""

    QUANTITY_ABSENT = "quantity_absent"
    """A linha da cena não traz grandeza nenhuma (ex.: polilinha aberta, que hoje não
    produz comprimento no `quantitativos.csv`)."""

    QUANTITY_NOT_POSITIVE = "quantity_not_positive"
    """A grandeza da cena é zero ou negativa; quantidade de medição é sempre positiva."""


class SceneQuantityRow(ValuationContractModel):
    """Uma linha do `quantitativos.csv`, já tipada.

    `entity_id` e `kind` chegam como o texto que o export escreveu — um grupo agregado lista
    vários, separados por `; ` (F-047 T3). Eles vão junto por rastreabilidade: o elo que
    resolve quantidade é `element_ref`, não eles.
    """

    element_ref: str | None = Field(default=None, pattern=ELEMENT_REF_PATTERN)
    entity_id: str = Field(min_length=1, max_length=4000)
    layer: str = Field(min_length=1, max_length=60)
    kind: str = Field(min_length=1, max_length=400)
    precision: Precision
    length_m: ExactDecimal | None = None
    perimeter_m: ExactDecimal | None = None
    area_m2: ExactDecimal | None = None

    def magnitude(self, dimension: QuantityDimension) -> Decimal | None:
        """A grandeza pedida, ou `None` quando a linha não a produz.

        Comprimento aceita `length_m` (traço aberto) ou `perimeter_m` (região fechada), mas
        nunca os dois: com as duas grandezas presentes o chamador recusa por
        `LENGTH_AMBIGUOUS` em vez de escolher.
        """
        if dimension is QuantityDimension.AREA:
            return self.area_m2
        if self.length_m is not None and self.perimeter_m is not None:
            return None
        return self.length_m if self.length_m is not None else self.perimeter_m

    def has_any_magnitude(self) -> bool:
        """`True` quando a linha traz ao menos uma grandeza física."""
        return any(value is not None for value in (self.length_m, self.perimeter_m, self.area_m2))


class QuantityResolution(ValuationContractModel):
    """O resultado de olhar a cena por um item de legenda: ou a quantidade, ou o motivo.

    Nunca as duas coisas e nunca nenhuma das duas — `resolved` discrimina, e o validador
    impede o estado meio-termo em que um chamador distraído leria `quantity=None` como zero.
    """

    item_id: str = Field(pattern=TAKEOFF_ITEM_ID_PATTERN)
    element_ref: str | None = Field(default=None, pattern=ELEMENT_REF_PATTERN)
    resolved: bool
    quantity: ExactDecimal | None = Field(default=None, gt=0)
    unit: str | None = Field(default=None, min_length=1, max_length=20)
    dimension: QuantityDimension | None = None
    precision: Precision | None = None
    reason: QuantityUnresolvedReason | None = None

    @model_validator(mode="after")
    def validate_outcome(self) -> QuantityResolution:
        if self.resolved:
            if self.reason is not None:
                raise ValuationValidationError(
                    "QUANTITY_RESOLUTION_INCONSISTENT",
                    "resolução com quantidade não carrega motivo de recusa",
                    {"item_id": self.item_id},
                )
            if (
                self.quantity is None
                or self.unit is None
                or self.dimension is None
                or self.precision is None
                or self.element_ref is None
            ):
                raise ValuationValidationError(
                    "QUANTITY_RESOLUTION_INCOMPLETE",
                    "resolução com quantidade exige identidade, unidade, grandeza e precisão",
                    {"item_id": self.item_id},
                )
            if self.precision not in SCENE_ELIGIBLE_PRECISIONS:
                raise ValuationValidationError(
                    "QUANTITY_RESOLUTION_PRECISION_NOT_ELIGIBLE",
                    "só entidade exact ou derived alimenta quantidade da medição",
                    {"item_id": self.item_id, "precision": self.precision.value},
                )
        else:
            if self.reason is None:
                raise ValuationValidationError(
                    "QUANTITY_RESOLUTION_WITHOUT_REASON",
                    "resolução sem quantidade exige o motivo da recusa",
                    {"item_id": self.item_id},
                )
            if self.quantity is not None:
                raise ValuationValidationError(
                    "QUANTITY_RESOLUTION_INCONSISTENT",
                    "resolução recusada não pode carregar quantidade",
                    {"item_id": self.item_id},
                )
        return self


def _parse_decimal(raw_value: str, *, column: str, line: int) -> Decimal | None:
    """Lê a grandeza do CSV como `Decimal` a partir do TEXTO, nunca por `float`.

    O export escreve `f"{valor:.6f}"`; passar por `float` aqui reintroduziria o binário que
    o resto do módulo recusa em campo decimal.
    """
    text = raw_value.strip()
    if not text:
        return None
    try:
        return Decimal(text)
    except InvalidOperation as error:
        raise ValuationValidationError(
            "QUANTITY_SOURCE_CSV_INVALID",
            "grandeza do quantitativo da cena não é um decimal legível",
            {"column": column, "line": line, "value": text},
        ) from error


def parse_scene_quantities(text: str) -> list[SceneQuantityRow]:
    """Lê o conteúdo de um `quantitativos.csv` e devolve as linhas tipadas.

    Falha fechada: cabeçalho ausente, coluna faltando, coluna desconhecida, precisão fora do
    vocabulário do núcleo ou grandeza ilegível recusam o arquivo inteiro. Um CSV que o
    adaptador não entende por completo não é um CSV do qual ele possa tirar quantidade.
    """
    reader = csv.DictReader(StringIO(text, newline=""))
    fieldnames = reader.fieldnames
    if not fieldnames:
        raise ValuationValidationError(
            "QUANTITY_SOURCE_CSV_INVALID",
            "quantitativo da cena sem cabeçalho",
            {},
        )
    columns = set(fieldnames)
    missing = sorted(set(SCENE_QUANTITY_COLUMNS) - columns)
    unknown = sorted(columns - set(SCENE_QUANTITY_COLUMNS) - {SCENE_QUANTITY_IDENTITY_COLUMN})
    if missing or unknown:
        raise ValuationValidationError(
            "QUANTITY_SOURCE_CSV_INVALID",
            "colunas do quantitativo da cena não conferem com o contrato do export",
            {"missing": missing, "unknown": unknown},
        )

    rows: list[SceneQuantityRow] = []
    for line, raw_row in enumerate(reader, start=2):
        raw_precision = (raw_row.get("precision") or "").strip()
        try:
            precision = Precision(raw_precision)
        except ValueError as error:
            raise ValuationValidationError(
                "QUANTITY_SOURCE_CSV_INVALID",
                "precisão do quantitativo da cena está fora do vocabulário do núcleo",
                {"line": line, "value": raw_precision},
            ) from error
        raw_ref = (raw_row.get(SCENE_QUANTITY_IDENTITY_COLUMN) or "").strip()
        rows.append(
            SceneQuantityRow(
                element_ref=raw_ref or None,
                entity_id=(raw_row.get("entity_id") or "").strip(),
                layer=(raw_row.get("layer") or "").strip(),
                kind=(raw_row.get("kind") or "").strip(),
                precision=precision,
                length_m=_parse_decimal(
                    raw_row.get("length_m") or "", column="length_m", line=line
                ),
                perimeter_m=_parse_decimal(
                    raw_row.get("perimeter_m") or "", column="perimeter_m", line=line
                ),
                area_m2=_parse_decimal(raw_row.get("area_m2") or "", column="area_m2", line=line),
            )
        )
    return rows


def dimension_of_unit(unit: str) -> QuantityDimension | None:
    """A grandeza que a unidade do item pede, ou `None` quando a cena não a produz.

    A normalização é a do catálogo (`m²`→`m2`, `ml`→`m`): a unidade escrita na legenda é a
    mesma que a planilha importa, então normalizá-la de outro jeito aqui abriria duas
    verdades sobre o que `ml` significa.
    """
    normalized = normalize_unit(unit)
    if normalized == _AREA_UNIT:
        return QuantityDimension.AREA
    if normalized == _LENGTH_UNIT:
        return QuantityDimension.LENGTH
    return None


class QuantitySource:
    """Lê o `quantitativos.csv` da cena aprovada e resolve quantidade por `element_ref`.

    A instância é um índice imutável por identidade de elemento. Linha sem `element_ref`
    continua na lista (`rows`) por rastreabilidade, mas não entra no índice: ela não tem como
    ser casada com item nenhum, e é exatamente isso que o produto quer que aconteça.
    """

    def __init__(
        self,
        rows: Sequence[SceneQuantityRow],
        *,
        scene_revision_id: str | None = None,
    ) -> None:
        index: dict[str, SceneQuantityRow] = {}
        for row in rows:
            if row.element_ref is None:
                continue
            if row.element_ref in index:
                # Depois do agrupamento da F-047 T3 o export escreve UMA linha por
                # elemento. Duas linhas com o mesmo ref significam que o arquivo não é o
                # que este adaptador sabe ler; somar ou pegar a primeira inventaria uma
                # quantidade que ninguém declarou.
                raise ValuationValidationError(
                    "QUANTITY_SOURCE_DUPLICATE_ELEMENT_REF",
                    "identidade de elemento repetida no quantitativo da cena",
                    {"element_ref": row.element_ref},
                )
            index[row.element_ref] = row
        self._rows: tuple[SceneQuantityRow, ...] = tuple(rows)
        self._index = index
        self._scene_revision_id = scene_revision_id

    @classmethod
    def from_csv_text(cls, text: str, *, scene_revision_id: str | None = None) -> QuantitySource:
        """Constrói a partir do conteúdo de um `quantitativos.csv`."""
        return cls(parse_scene_quantities(text), scene_revision_id=scene_revision_id)

    @classmethod
    def from_quantities_csv(
        cls, path: Path, *, scene_revision_id: str | None = None
    ) -> QuantitySource:
        """Constrói a partir do `quantitativos.csv` publicado no pacote da cena aprovada."""
        return cls.from_csv_text(
            path.read_text(encoding="utf-8"), scene_revision_id=scene_revision_id
        )

    @property
    def rows(self) -> tuple[SceneQuantityRow, ...]:
        """Todas as linhas lidas, com e sem identidade, na ordem do arquivo."""
        return self._rows

    @property
    def scene_revision_id(self) -> str | None:
        """A revisão aprovada declarada por quem leu o pacote, quando houve declaração."""
        return self._scene_revision_id

    def row_for(self, element_ref: str) -> SceneQuantityRow | None:
        """A linha da cena com aquela identidade, ou `None`."""
        return self._index.get(element_ref)

    def resolve(self, item: TakeoffItem) -> QuantityResolution:
        """Olha a cena por este item e devolve a quantidade OU o motivo de não haver uma.

        Nunca levanta por regra de negócio: recusa é resultado, não exceção. A ordem das
        checagens vai do elo (identidade) ao conteúdo (precisão, unidade, grandeza), para
        que o motivo devolvido seja o primeiro que de fato impede a travessia.
        """
        if item.element_ref is None:
            return QuantityResolution(
                item_id=item.id,
                resolved=False,
                reason=QuantityUnresolvedReason.ITEM_WITHOUT_ELEMENT_REF,
            )
        row = self._index.get(item.element_ref)
        if row is None:
            return QuantityResolution(
                item_id=item.id,
                element_ref=item.element_ref,
                resolved=False,
                reason=QuantityUnresolvedReason.ELEMENT_REF_ABSENT_FROM_SCENE,
            )
        if row.precision not in SCENE_ELIGIBLE_PRECISIONS:
            return QuantityResolution(
                item_id=item.id,
                element_ref=item.element_ref,
                resolved=False,
                precision=row.precision,
                reason=QuantityUnresolvedReason.PRECISION_NOT_ELIGIBLE,
            )

        def refuse(reason: QuantityUnresolvedReason) -> QuantityResolution:
            return QuantityResolution(
                item_id=item.id,
                element_ref=item.element_ref,
                resolved=False,
                precision=row.precision,
                reason=reason,
            )

        dimension = dimension_of_unit(item.unit)
        if dimension is None:
            return refuse(QuantityUnresolvedReason.UNIT_NOT_DERIVABLE_FROM_SCENE)
        if not row.has_any_magnitude():
            return refuse(QuantityUnresolvedReason.QUANTITY_ABSENT)
        quantity = row.magnitude(dimension)
        if quantity is None:
            if (
                dimension is QuantityDimension.LENGTH
                and row.length_m is not None
                and row.perimeter_m is not None
            ):
                return refuse(QuantityUnresolvedReason.LENGTH_AMBIGUOUS)
            # A linha traz a OUTRA grandeza: área para item em metro, ou comprimento para
            # item em metro quadrado. Converter uma na outra é impossível sem inventar a
            # dimensão que falta, então a recusa é nomeada (ADR-0058: nada por palpite).
            return refuse(QuantityUnresolvedReason.UNIT_MISMATCH)
        if quantity <= 0:
            return refuse(QuantityUnresolvedReason.QUANTITY_NOT_POSITIVE)
        return QuantityResolution(
            item_id=item.id,
            element_ref=item.element_ref,
            resolved=True,
            quantity=quantity,
            unit=item.unit,
            dimension=dimension,
            precision=row.precision,
        )

    def resolve_all(self, items: Iterable[TakeoffItem]) -> list[QuantityResolution]:
        """`resolve` item a item, preservando a ordem recebida."""
        return [self.resolve(item) for item in items]

    def divergence_for(self, item: TakeoffItem) -> QuantityDivergence | None:
        """A divergência entre o número da cena e o lido na legenda, ou `None`.

        Devolve `None` — e não uma recusa — em toda situação em que **não há duas
        quantidades para confrontar**, porque nenhuma delas é anomalia:

        - o item não traz número da legenda (nada a comparar);
        - o item já nasceu da cena (`source = scene_graph`): não existe leitura de legenda;
        - a cena não resolve por este item (identidade ausente, unidade não derivável,
          grandeza ausente) — inclusive quando a linha é `approximate` ou `unresolved`, que
          **não alimenta e por isso também não diverge** (ADR-0058 decisão 4). Comparar
          `approximate` produziria uma issue sem decisão possível: escolher "a cena" seria
          promover a precisão que o pipeline proíbe do croqui até o DXF;
        - os dois números se afastam no MÁXIMO a tolerância nomeada — igual à tolerância
          ainda é igual (`>`, nunca `>=`).
        """
        legend_quantity = item.quantity
        legend_source = item.source
        if legend_quantity is None or legend_source == "scene_graph":
            return None
        resolution = self.resolve(item)
        if not resolution.resolved:
            return None
        # `validate_outcome` já garante que uma resolução resolvida traz os quatro campos.
        assert resolution.quantity is not None
        assert resolution.element_ref is not None
        assert resolution.precision is not None
        difference = abs(resolution.quantity - legend_quantity)
        breakdown = quantity_divergence_tolerance_breakdown(legend_quantity)
        tolerance = breakdown.tolerance
        if difference <= tolerance:
            return None
        decision = item.decision
        return QuantityDivergence(
            scene=SceneQuantityOrigin(
                quantity=resolution.quantity,
                element_ref=resolution.element_ref,
                precision=resolution.precision,
                scene_revision_id=self._scene_revision_id,
            ),
            legend=LegendQuantityOrigin(
                quantity=legend_quantity,
                source=legend_source,
                extractor=item.extractor,
                extractor_version=item.extractor_version,
                read_by=None if decision is None else decision.reviewer_id,
                read_at=None if decision is None else decision.decided_at,
            ),
            difference=difference,
            tolerance=tolerance,
            relative_tolerance=breakdown.relative_tolerance,
            absolute_floor=breakdown.absolute_floor,
            tolerance_bound=breakdown.tolerance_bound,
            legend_ratio=quantity_divergence_ratio(
                difference=difference, legend_quantity=legend_quantity
            ),
        )

    def record_divergence(self, item: TakeoffItem) -> TakeoffItem:
        """Devolve uma CÓPIA do item com a divergência gravada; nunca muta o item de entrada.

        Item sem divergência volta inalterado — gravar uma issue vazia diria que houve
        confronto e que ele deu certo, o que é mais do que este módulo sabe.

        Regravar sobre uma divergência que já existe é recusado: se ela está aberta, a
        segunda gravação apagaria o número que alguém está olhando na tela; se está
        resolvida, apagaria a decisão humana junto. Reconfrontar um item é ato de quem
        reabre, não efeito colateral de reler o CSV.
        """
        if item.scene_divergence is not None:
            raise ValuationValidationError(
                "QUANTITY_DIVERGENCE_ALREADY_RECORDED",
                "este item já tem divergência de quantidade gravada",
                {"id": item.id},
            )
        divergence = self.divergence_for(item)
        if divergence is None:
            return item
        return TakeoffItem.model_validate(
            {**item.model_dump(), "scene_divergence": divergence.model_dump()}
        )

    def feed(self, item: TakeoffItem) -> TakeoffItem:
        """Devolve uma CÓPIA do item alimentada pela cena; nunca muta o item de entrada.

        Recusa, com código estável, tudo que a travessia não autoriza:

        - item já revisado (`confirmed`/`rejected`) — a decisão humana é soberana;
        - item que já traz quantidade da legenda — a cena não sobrescreve a legenda
          (ADR-0058 decisão 6); comparar as duas é a F-047 T5, e o resultado dela é uma
          Issue, não uma conciliação silenciosa;
        - qualquer resolução recusada, com o motivo em `details`.

        O item volta `proposed`: a quantidade da cena é uma PROPOSTA com origem declarada,
        e continua exigindo a decisão do orçamentista para virar `confirmed`.
        """
        if item.status in {TakeoffItemStatus.CONFIRMED, TakeoffItemStatus.REJECTED}:
            raise ValuationValidationError(
                "TAKEOFF_ITEM_ALREADY_REVIEWED",
                "item de takeoff já revisado não pode ser sobrescrito pela cena",
                {"id": item.id, "status": item.status.value},
            )
        if item.quantity is not None:
            raise ValuationValidationError(
                "QUANTITY_SOURCE_ITEM_ALREADY_QUANTIFIED",
                "quantidade da cena não sobrescreve a quantidade lida na legenda",
                {"id": item.id},
            )
        resolution = self.resolve(item)
        if not resolution.resolved:
            reason = resolution.reason
            raise ValuationValidationError(
                "QUANTITY_SOURCE_UNRESOLVED",
                "a cena aprovada não tem quantidade para este item de legenda",
                {"id": item.id, "reason": reason.value if reason is not None else None},
            )
        return TakeoffItem.model_validate(
            {
                **item.model_dump(),
                "quantity": resolution.quantity,
                "source": "scene_graph",
                "scene_precision": resolution.precision,
                "status": TakeoffItemStatus.PROPOSED,
            }
        )
