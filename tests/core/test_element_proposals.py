"""F-047 T6: o produtor determinístico de propostas assistidas (ADR-0058, decisão 2).

O que estes testes protegem, em uma frase cada: a mesma cena produz sempre as mesmas
propostas, na mesma ordem; entidades já identificadas e anotações (`TEXT`/`DIMENSION`)
nunca entram como candidato; o sinal de procedência agrupa por camada+`summary_code`+
`source_ids`, e pode agrupar ERRADO de propósito (duas coisas distintas do mesmo lote de
detecção) — a recusa humana é o que existe para esse caso; o sinal de proximidade de
rótulo só entra para quem sobrou do sinal de procedência; e sem sinal nenhum, ou com toda
entidade já identificada, a lista vem vazia.
"""

from __future__ import annotations

from croquito_core.element_proposals import propose_element_groups
from croquito_core.ids import new_uuid7
from croquito_core.models import (
    Entity,
    EntityKind,
    LayerName,
    LineGeometry,
    Point2D,
    Precision,
    Provenance,
    SceneRevision,
    TextGeometry,
)

JOB_ID = new_uuid7()


def _line(
    *,
    y: float,
    layer: LayerName = LayerName.MURO,
    provenance: Provenance | None = None,
    element_ref: str | None = None,
) -> Entity:
    return Entity(
        kind=EntityKind.LINE,
        layer=layer,
        precision=Precision.DERIVED,
        geometry=LineGeometry(start=Point2D(x=0.0, y=y), end=Point2D(x=10.0, y=y)),
        provenance=provenance,
        element_ref=element_ref,
    )


def _label(*, x: float, y: float, text: str) -> Entity:
    return Entity(
        kind=EntityKind.TEXT,
        layer=LayerName.TEXTOS,
        precision=Precision.DERIVED,
        geometry=TextGeometry(insertion=Point2D(x=x, y=y), text=text, height=0.2),
    )


def test_mesma_cena_produz_sempre_as_mesmas_propostas_na_mesma_ordem() -> None:
    provenance = Provenance(
        source_type="fixture", source_ids=["batch-1"], summary_code="MURO_SEGMENT"
    )
    scene = SceneRevision(
        job_id=JOB_ID,
        version=1,
        entities=[
            _line(y=0.0, provenance=provenance),
            _line(y=1.0, provenance=provenance),
        ],
    )

    first = propose_element_groups(scene)
    second = propose_element_groups(scene)

    assert first == second
    assert len(first) == 1
    assert first[0].signal == "provenance"
    assert first[0].layer == LayerName.MURO


def test_entidade_ja_identificada_nunca_e_candidata() -> None:
    provenance = Provenance(
        source_type="fixture", source_ids=["batch-1"], summary_code="MURO_SEGMENT"
    )
    scene = SceneRevision(
        job_id=JOB_ID,
        version=1,
        entities=[
            _line(y=0.0, provenance=provenance, element_ref="EL-001"),
            _line(y=1.0, provenance=provenance),
        ],
    )

    proposals = propose_element_groups(scene)

    # Só sobra UMA entidade candidata (a outra já tem identidade): sem par, sem proposta.
    assert proposals == []


def test_anotacao_nunca_e_candidata_a_elemento() -> None:
    """`TEXT` é o rótulo, não o elemento — mesmo com procedência igual a um traço real."""
    provenance = Provenance(
        source_type="fixture", source_ids=["batch-1"], summary_code="MURO_SEGMENT"
    )
    label = Entity(
        kind=EntityKind.TEXT,
        layer=LayerName.MURO,
        precision=Precision.DERIVED,
        geometry=TextGeometry(insertion=Point2D(x=0, y=0), text="MURO 1", height=0.2),
        provenance=provenance,
    )
    scene = SceneRevision(
        job_id=JOB_ID,
        version=1,
        entities=[_line(y=0.0, provenance=provenance), label],
    )

    proposals = propose_element_groups(scene)

    assert proposals == []


def test_sinal_de_procedencia_pode_agrupar_dois_elementos_distintos_de_proposito() -> None:
    """Proposta ERRADA construída de propósito: dois muros DIFERENTES, mesmo lote de detecção.

    O sinal é `mesma camada + mesma procedência`, e o mesmo lote de detecção pode ter
    descrito dois traços de elementos fisicamente distintos. A proposta nasce mesmo assim
    — ela é candidato, não verdade —, e é isto que o teste de API (`test_element_proposals`)
    usa para provar que o humano pode recusá-la sem nada ser escrito na cena.
    """
    provenance = Provenance(
        source_type="fixture", source_ids=["batch-1"], summary_code="MURO_SEGMENT"
    )
    scene = SceneRevision(
        job_id=JOB_ID,
        version=1,
        entities=[
            _line(y=0.0, provenance=provenance),
            _line(y=50.0, provenance=provenance),  # longe: outro muro, mesmo lote
        ],
    )

    proposals = propose_element_groups(scene)

    assert len(proposals) == 1
    assert proposals[0].signal == "provenance"
    assert len(proposals[0].entity_ids) == 2


def test_sinal_de_rotulo_so_entra_para_quem_sobrou_da_procedencia() -> None:
    provenance = Provenance(
        source_type="fixture", source_ids=["batch-1"], summary_code="MURO_SEGMENT"
    )
    with_provenance_a = _line(y=0.0, provenance=provenance)
    with_provenance_b = _line(y=0.5, provenance=provenance)
    near_label_a = _line(y=10.0, layer=LayerName.ALAMBRADO)
    near_label_b = _line(y=10.5, layer=LayerName.ALAMBRADO)
    label = _label(x=5.0, y=10.25, text="ALAMBRADO 1")
    scene = SceneRevision(
        job_id=JOB_ID,
        version=1,
        entities=[with_provenance_a, with_provenance_b, near_label_a, near_label_b, label],
    )

    proposals = propose_element_groups(scene)

    assert len(proposals) == 2
    by_signal = {proposal.signal: proposal for proposal in proposals}
    assert by_signal["provenance"].entity_ids == (with_provenance_a.id, with_provenance_b.id)
    assert by_signal["label_proximity"].entity_ids == (near_label_a.id, near_label_b.id)
    assert by_signal["label_proximity"].label == "ALAMBRADO 1"
    assert by_signal["label_proximity"].layer == LayerName.ALAMBRADO


def test_rotulo_longe_demais_nao_agrupa() -> None:
    far_label = _label(x=5.0, y=1000.0, text="MURO 1")
    scene = SceneRevision(
        job_id=JOB_ID,
        version=1,
        entities=[_line(y=0.0), _line(y=0.5), far_label],
    )

    proposals = propose_element_groups(scene)

    assert proposals == []


def test_sem_sinal_nenhum_a_lista_vem_vazia() -> None:
    """Sem procedência e sem rótulo, uma entidade sozinha na camada não propõe nada."""
    scene = SceneRevision(job_id=JOB_ID, version=1, entities=[_line(y=0.0)])

    assert propose_element_groups(scene) == []


def test_procedencia_nao_agrupa_entre_camadas_diferentes() -> None:
    provenance = Provenance(
        source_type="fixture", source_ids=["batch-1"], summary_code="MURO_SEGMENT"
    )
    other_layer_entity = _line(y=0.0, layer=LayerName.ALAMBRADO, provenance=provenance)
    scene = SceneRevision(
        job_id=JOB_ID,
        version=1,
        entities=[_line(y=0.0, provenance=provenance), other_layer_entity],
    )

    proposals = propose_element_groups(scene)

    # Mesma procedência, camadas diferentes: NÃO é o mesmo grupo (a invariante de layer
    # mistura já barraria isto na declaração humana; o produtor não propõe o que a T2
    # recusaria).
    assert proposals == []


def test_grupo_de_procedencia_exige_pelo_menos_duas_entidades() -> None:
    """Uma única entidade com procedência, sozinha na camada, não é um "agrupamento"."""
    provenance = Provenance(
        source_type="fixture", source_ids=["batch-1"], summary_code="MURO_SEGMENT"
    )
    scene = SceneRevision(job_id=JOB_ID, version=1, entities=[_line(y=0.0, provenance=provenance)])

    assert propose_element_groups(scene) == []
