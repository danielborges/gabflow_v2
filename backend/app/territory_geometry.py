from math import isfinite


class TerritoryGeometryError(ValueError):
    pass


def normalize_geometry(value) -> dict | None:
    if value in (None, ""):
        return None
    if not isinstance(value, dict):
        raise TerritoryGeometryError("A geometria deve ser um objeto GeoJSON.")
    if value.get("type") == "Feature":
        value = value.get("geometry")
    if not isinstance(value, dict) or value.get("type") not in {"Polygon", "MultiPolygon"}:
        raise TerritoryGeometryError("Use uma geometria GeoJSON Polygon ou MultiPolygon.")
    coordinates = value.get("coordinates")
    polygons = coordinates if value["type"] == "MultiPolygon" else [coordinates]
    if not isinstance(polygons, list) or not polygons:
        raise TerritoryGeometryError("A geometria não possui polígonos.")
    normalized = []
    coordinate_count = 0
    for polygon in polygons:
        if not isinstance(polygon, list) or not polygon:
            raise TerritoryGeometryError("Polígono GeoJSON inválido.")
        rings = []
        for ring in polygon:
            if not isinstance(ring, list) or len(ring) < 4:
                raise TerritoryGeometryError("Cada anel deve possuir ao menos quatro pontos.")
            points = [_coordinate(point) for point in ring]
            coordinate_count += len(points)
            if coordinate_count > 100_000:
                raise TerritoryGeometryError("A geometria excede 100 mil coordenadas.")
            if points[0] != points[-1]:
                raise TerritoryGeometryError("Os anéis GeoJSON devem estar fechados.")
            if len({tuple(point) for point in points[:-1]}) < 3:
                raise TerritoryGeometryError(
                    "Cada anel deve possuir ao menos três vértices distintos."
                )
            if abs(_ring_area(points)) <= 1e-12:
                raise TerritoryGeometryError("O anel GeoJSON não pode possuir área igual a zero.")
            rings.append(points)
        for hole in rings[1:]:
            if not _ring_contains(rings[0], hole[0]):
                raise TerritoryGeometryError(
                    "Os vazios do polígono devem ficar dentro do anel externo."
                )
        normalized.append(rings)
    return {
        "type": value["type"],
        "coordinates": normalized if value["type"] == "MultiPolygon" else normalized[0],
    }


def geometry_contains(geometry: dict | None, latitude: float, longitude: float) -> bool:
    if not geometry:
        return False
    polygons = (
        geometry["coordinates"]
        if geometry.get("type") == "MultiPolygon"
        else [geometry.get("coordinates")]
    )
    point = (longitude, latitude)
    for polygon in polygons:
        if not polygon or not _ring_contains(polygon[0], point):
            continue
        if not any(_ring_contains(hole, point) for hole in polygon[1:]):
            return True
    return False


def geometry_area(geometry: dict | None) -> float:
    if not geometry:
        return float("inf")
    polygons = (
        geometry["coordinates"]
        if geometry.get("type") == "MultiPolygon"
        else [geometry["coordinates"]]
    )
    return sum(abs(_ring_area(polygon[0])) for polygon in polygons if polygon)


def _coordinate(value) -> list[float]:
    if not isinstance(value, list | tuple) or len(value) < 2:
        raise TerritoryGeometryError("Coordenada GeoJSON inválida.")
    try:
        longitude, latitude = float(value[0]), float(value[1])
    except (TypeError, ValueError) as error:
        raise TerritoryGeometryError("Coordenada GeoJSON inválida.") from error
    if (
        not isfinite(longitude)
        or not isfinite(latitude)
        or not -180 <= longitude <= 180
        or not -90 <= latitude <= 90
    ):
        raise TerritoryGeometryError("Coordenada fora dos limites geográficos.")
    return [longitude, latitude]


def _ring_contains(ring, point) -> bool:
    x, y = point
    inside = False
    previous = ring[-1]
    for current in ring:
        x1, y1 = previous
        x2, y2 = current
        if _on_segment(x, y, x1, y1, x2, y2):
            return True
        if (y1 > y) != (y2 > y):
            crossing = (x2 - x1) * (y - y1) / (y2 - y1) + x1
            if x < crossing:
                inside = not inside
        previous = current
    return inside


def _on_segment(x, y, x1, y1, x2, y2) -> bool:
    cross = (x - x1) * (y2 - y1) - (y - y1) * (x2 - x1)
    return (
        abs(cross) <= 1e-10 and min(x1, x2) <= x <= max(x1, x2) and min(y1, y2) <= y <= max(y1, y2)
    )


def _ring_area(ring) -> float:
    return (
        sum(
            ring[index][0] * ring[index + 1][1] - ring[index + 1][0] * ring[index][1]
            for index in range(len(ring) - 1)
        )
        / 2
    )
