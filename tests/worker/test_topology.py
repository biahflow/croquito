from croquito_worker.topology import (
    Topology,
    build_topology,
    junction_positions,
    rebuild_all,
)
from croquito_worker.vision import (
    PixelCircle,
    PixelGeometryValue,
    PixelLine,
    PixelPoint,
    PixelPolyline,
    VisionProposal,
)

WIDTH, HEIGHT = 1000, 1000


def _proposal(
    identifier: str, geometry: PixelGeometryValue, *, label: str | None = None
) -> VisionProposal:
    return VisionProposal(
        id=identifier,
        kind="contour" if isinstance(geometry, PixelPolyline) else "line",
        geometry=geometry,
        algorithm="test",
        quality_score=1.0,
        label=label,
    )


def _line(identifier: str, start: tuple[float, float], end: tuple[float, float]) -> VisionProposal:
    return _proposal(
        identifier,
        PixelLine(start=PixelPoint(x=start[0], y=start[1]), end=PixelPoint(x=end[0], y=end[1])),
    )


def _polyline(
    identifier: str, points: list[tuple[float, float]], *, closed: bool = True
) -> VisionProposal:
    return _proposal(
        identifier,
        PixelPolyline(points=[PixelPoint(x=x, y=y) for x, y in points], closed=closed),
    )


def _topology(*proposals: VisionProposal, ratio: float = 0.010) -> Topology:
    return build_topology(
        list(proposals), image_width=WIDTH, image_height=HEIGHT, tolerance_ratio=ratio
    )


def test_two_walls_meeting_at_a_corner_share_one_junction() -> None:
    """É a informação que o sistema recebia e descartava: este canto é um canto só."""
    topology = _topology(
        _line("vp_" + "1" * 16, (100.0, 100.0), (500.0, 100.0)),
        _line("vp_" + "2" * 16, (503.0, 98.0), (500.0, 400.0)),
    )

    assert len(topology.junctions) == 3
    assert topology.shared_junction_count == 1
    shared = next(item for item in topology.junctions if item.shared)
    assert {member.proposal_id for member in shared.members} == {
        "vp_" + "1" * 16,
        "vp_" + "2" * 16,
    }


def test_vertices_of_the_same_element_never_merge() -> None:
    """Um elemento pequeno inteiro dentro da tolerância colapsaria num ponto e sumiria."""
    tiny = _polyline(
        "vp_" + "3" * 16, [(500.0, 500.0), (502.0, 500.0), (502.0, 502.0), (500.0, 502.0)]
    )

    topology = _topology(tiny, ratio=0.5)

    assert len(topology.junctions) == 4
    assert len(topology.edges) == 4  # fecha, então tem segmento de retorno


def test_a_closed_polyline_gets_its_returning_segment() -> None:
    closed = _polyline("vp_" + "4" * 16, [(0.0, 0.0), (100.0, 0.0), (100.0, 100.0)])
    opened = _polyline("vp_" + "5" * 16, [(0.0, 0.0), (100.0, 0.0), (100.0, 100.0)], closed=False)

    assert len(_topology(closed).edges) == 3
    assert len(_topology(opened).edges) == 2


def test_a_circle_contributes_no_junction() -> None:
    """Círculo não tem canto; forçá-lo a um vértice inventaria adjacência."""
    circle = _proposal(
        "vp_" + "6" * 16, PixelCircle(center=PixelPoint(x=500.0, y=500.0), radius=40.0)
    )

    topology = _topology(circle)

    assert topology.junctions == ()
    assert topology.edges == ()


def test_moving_a_junction_carries_every_element_that_touches_it() -> None:
    """O defeito de origem: reescalar uma aresta isolada abria o polígono vizinho."""
    field = _polyline(
        "vp_" + "7" * 16, [(100.0, 100.0), (500.0, 100.0), (500.0, 400.0), (100.0, 400.0)]
    )
    wall = _line("vp_" + "8" * 16, (500.0, 100.0), (900.0, 100.0))
    topology = _topology(field, wall)

    positions = junction_positions(topology)
    corner = next(item for item in topology.junctions if item.shared)
    positions[corner.id] = (600.0, 120.0)
    moved = rebuild_all([field, wall], topology, positions)

    rebuilt_field, rebuilt_wall = moved
    assert isinstance(rebuilt_field.geometry, PixelPolyline)
    assert isinstance(rebuilt_wall.geometry, PixelLine)
    assert (rebuilt_field.geometry.points[1].x, rebuilt_field.geometry.points[1].y) == (
        600.0,
        120.0,
    )
    assert (rebuilt_wall.geometry.start.x, rebuilt_wall.geometry.start.y) == (600.0, 120.0)


def test_rebuild_without_any_move_is_the_identity() -> None:
    field = _polyline(
        "vp_" + "9" * 16, [(100.0, 100.0), (500.0, 100.0), (500.0, 400.0), (100.0, 400.0)]
    )
    topology = _topology(field)

    rebuilt = rebuild_all([field], topology, junction_positions(topology))

    assert rebuilt[0].geometry == field.geometry


def test_junction_identity_is_stable_across_runs() -> None:
    proposals = [
        _polyline(
            "vp_" + "a" * 16, [(100.0, 100.0), (500.0, 100.0), (500.0, 400.0), (100.0, 400.0)]
        ),
        _line("vp_" + "b" * 16, (500.0, 100.0), (900.0, 100.0)),
    ]

    assert _topology(*proposals) == _topology(*proposals)
