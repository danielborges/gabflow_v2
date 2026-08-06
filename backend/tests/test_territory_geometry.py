import pytest

from app.territory_geometry import (
    TerritoryGeometryError,
    geometry_contains,
    normalize_geometry,
)


def test_polygon_contains_boundary_and_excludes_hole():
    geometry = normalize_geometry(
        {
            "type": "Polygon",
            "coordinates": [
                [[0, 0], [10, 0], [10, 10], [0, 10], [0, 0]],
                [[4, 4], [6, 4], [6, 6], [4, 6], [4, 4]],
            ],
        }
    )
    assert geometry_contains(geometry, 2, 2)
    assert geometry_contains(geometry, 0, 5)
    assert not geometry_contains(geometry, 5, 5)
    assert not geometry_contains(geometry, 20, 20)


def test_geometry_accepts_feature_and_rejects_open_ring():
    feature = normalize_geometry(
        {
            "type": "Feature",
            "properties": {"name": "Teste"},
            "geometry": {
                "type": "Polygon",
                "coordinates": [[[1, 1], [2, 1], [2, 2], [1, 2], [1, 1]]],
            },
        }
    )
    assert feature["type"] == "Polygon"
    with pytest.raises(TerritoryGeometryError, match="fechados"):
        normalize_geometry(
            {
                "type": "Polygon",
                "coordinates": [[[1, 1], [2, 1], [2, 2], [1, 2]]],
            }
        )


def test_geometry_rejects_degenerate_ring_and_external_hole():
    with pytest.raises(TerritoryGeometryError, match="três vértices distintos"):
        normalize_geometry(
            {
                "type": "Polygon",
                "coordinates": [[[1, 1], [2, 2], [1, 1], [1, 1]]],
            }
        )
    with pytest.raises(TerritoryGeometryError, match="dentro do anel externo"):
        normalize_geometry(
            {
                "type": "Polygon",
                "coordinates": [
                    [[0, 0], [4, 0], [4, 4], [0, 4], [0, 0]],
                    [[5, 5], [6, 5], [6, 6], [5, 6], [5, 5]],
                ],
            }
        )
