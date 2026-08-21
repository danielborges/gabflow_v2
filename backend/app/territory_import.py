import io
import json
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from dataclasses import dataclass
from datetime import UTC, datetime
from unicodedata import combining, normalize

import shapefile
from sqlalchemy import select

from app.extensions import db
from app.models import Tenant, Territory, TerritoryNeighborhood
from app.territory_geometry import geometry_area, geometry_contains, normalize_geometry

IBGE_NEIGHBORHOOD_SOURCE = "IBGE_CENSO_2022_BAIRROS"
IBGE_DISTRICT_SOURCE = "IBGE_CENSO_2022_DISTRITOS"
IBGE_DISTRICT_URL = (
    "https://geoftp.ibge.gov.br/organizacao_do_territorio/malhas_territoriais/"
    "malhas_de_setores_censitarios__divisoes_intramunicipais/censo_2022/"
    "distritos/shp/UF/{uf}_distritos_CD2022.zip"
)
IBGE_NEIGHBORHOOD_URL = (
    "https://geoftp.ibge.gov.br/organizacao_do_territorio/malhas_territoriais/"
    "malhas_de_setores_censitarios__divisoes_intramunicipais/censo_2022/"
    "bairros/shp/UF/{uf}_bairros_CD2022.zip"
)
MAX_ARCHIVE_BYTES = 25 * 1024 * 1024
MAX_DISTRICT_ARCHIVE_BYTES = 80 * 1024 * 1024
MAX_MEMBER_BYTES = 100 * 1024 * 1024

MUNICIPAL_TERRITORY_SOURCES = {
    "3136702": {
        "name": "PJF_SISURB_REGIOES_PLANEJAMENTO",
        "version": "PDP_2018",
        "url": (
            "https://sisurb.pjf.mg.gov.br/server/rest/services/"
            "ter_limites_regioes_planejamento/MapServer/1"
        ),
        "name_field": "nome",
        "id_field": "nro",
        "version_field": "ano",
    }
}


class TerritoryImportError(RuntimeError):
    pass


@dataclass(frozen=True)
class TerritoryImportResult:
    source_name: str
    territory_count: int
    neighborhood_count: int
    matched_neighborhood_count: int


def import_official_territories(tenant: Tenant) -> TerritoryImportResult | None:
    source = MUNICIPAL_TERRITORY_SOURCES.get(str(tenant.jurisdiction_ibge_code or ""))
    if source is not None:
        features = _fetch_arcgis_features(source["url"])
    else:
        source, features = _fetch_ibge_districts(tenant)
        if source is None:
            return None
    territories = _upsert_territories(tenant, source, features)
    neighborhoods = _fetch_ibge_neighborhoods(tenant)
    matched = _upsert_neighborhoods(tenant, neighborhoods, territories)
    return TerritoryImportResult(
        source_name=source["name"],
        territory_count=len(territories),
        neighborhood_count=len(neighborhoods),
        matched_neighborhood_count=matched,
    )


def _fetch_ibge_districts(tenant: Tenant) -> tuple[dict | None, list[dict]]:
    uf = str(tenant.jurisdiction_state or "").strip().upper()
    municipality_code = str(tenant.jurisdiction_ibge_code or "").strip()
    if len(uf) != 2 or not municipality_code:
        return None, []
    source_url = IBGE_DISTRICT_URL.format(uf=uf)
    rows = _fetch_ibge_shapes(
        municipality_code=municipality_code,
        source_url=source_url,
        name_field="NM_DIST",
        code_field="CD_DIST",
        max_archive_bytes=MAX_DISTRICT_ARCHIVE_BYTES,
    )
    source = {
        "name": IBGE_DISTRICT_SOURCE,
        "version": "CENSO_2022",
        "url": source_url,
        "name_field": "name",
        "id_field": "external_code",
        "version_field": "source_version",
    }
    features = [
        {
            "type": "Feature",
            "properties": {
                "name": row["name"],
                "external_code": row["external_code"],
                "source_version": row["source_version"],
            },
            "geometry": row["geometry"],
        }
        for row in rows
    ]
    return source, features


def _fetch_arcgis_features(source_url: str) -> list[dict]:
    params = urllib.parse.urlencode(
        {
            "where": "1=1",
            "outFields": "*",
            "returnGeometry": "true",
            "outSR": "4326",
            "f": "geojson",
        }
    )
    payload = _fetch_bytes(f"{source_url}/query?{params}", max_bytes=20 * 1024 * 1024)
    try:
        data = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise TerritoryImportError("A fonte territorial retornou GeoJSON inválido.") from error
    features = data.get("features") if isinstance(data, dict) else None
    if data.get("type") != "FeatureCollection" or not isinstance(features, list) or not features:
        raise TerritoryImportError("A fonte territorial não retornou polígonos.")
    return features


def _fetch_ibge_neighborhoods(tenant: Tenant) -> list[dict]:
    uf = str(tenant.jurisdiction_state or "").strip().upper()
    municipality_code = str(tenant.jurisdiction_ibge_code or "").strip()
    if len(uf) != 2 or not municipality_code:
        return []
    source_url = IBGE_NEIGHBORHOOD_URL.format(uf=uf)
    return _fetch_ibge_shapes(
        municipality_code=municipality_code,
        source_url=source_url,
        name_field="NM_BAIRRO",
        code_field="CD_BAIRRO",
        max_archive_bytes=MAX_ARCHIVE_BYTES,
    )


def _fetch_ibge_shapes(
    *,
    municipality_code: str,
    source_url: str,
    name_field: str,
    code_field: str,
    max_archive_bytes: int,
) -> list[dict]:
    archive = _fetch_bytes(source_url, max_bytes=max_archive_bytes)
    try:
        with zipfile.ZipFile(io.BytesIO(archive)) as zipped:
            members = {item.filename.lower(): item for item in zipped.infolist()}
            parts = {}
            for extension in (".shp", ".shx", ".dbf"):
                candidates = [item for name, item in members.items() if name.endswith(extension)]
                if len(candidates) != 1 or candidates[0].file_size > MAX_MEMBER_BYTES:
                    raise TerritoryImportError("O arquivo territorial do IBGE está incompleto.")
                parts[extension] = zipped.read(candidates[0])
    except (zipfile.BadZipFile, OSError) as error:
        raise TerritoryImportError("Não foi possível abrir a malha territorial do IBGE.") from error

    try:
        reader = shapefile.Reader(
            shp=io.BytesIO(parts[".shp"]),
            shx=io.BytesIO(parts[".shx"]),
            dbf=io.BytesIO(parts[".dbf"]),
            # Os arquivos de 2022 declaram UTF-8 no CPG, mas os DBFs são
            # publicados com os caracteres acentuados em Latin-1.
            encoding="latin-1",
        )
        rows = []
        for item in reader.iterShapeRecords():
            attributes = item.record.as_dict()
            if str(attributes.get("CD_MUN") or "") != municipality_code:
                continue
            name = str(attributes.get(name_field) or "").strip()
            external_code = str(attributes.get(code_field) or "").strip()
            if not name or not external_code:
                continue
            geometry = normalize_geometry(json.loads(json.dumps(item.shape.__geo_interface__)))
            rows.append(
                {
                    "name": name,
                    "external_code": external_code,
                    "geometry": geometry,
                    "source_url": source_url,
                    "source_version": "CENSO_2022",
                }
            )
        return rows
    except (ValueError, shapefile.ShapefileException) as error:
        raise TerritoryImportError("A malha territorial do IBGE é inválida.") from error


def _upsert_territories(tenant: Tenant, source: dict, features: list[dict]) -> list[Territory]:
    existing = list(
        db.session.execute(select(Territory).where(Territory.tenant_id == tenant.id)).scalars()
    )
    by_key = {_territory_key(item.name): item for item in existing}
    by_ref = {
        item.source_ref: item
        for item in existing
        if item.source_name == source["name"] and item.source_ref
    }
    imported = []
    for feature in features:
        properties = feature.get("properties") or {}
        name = str(properties.get(source["name_field"]) or "").strip()
        source_ref = str(properties.get(source["id_field"]) or "").strip()
        if not name or not source_ref:
            continue
        geometry = normalize_geometry(feature.get("geometry"))
        item = by_ref.get(source_ref) or by_key.get(_territory_key(name))
        if item is None:
            item = Territory(tenant_id=tenant.id, name=name, aliases=[])
            db.session.add(item)
            existing.append(item)
        elif _normalized(item.name) != _normalized(name):
            aliases = list(item.aliases or [])
            if _normalized(name) not in {_normalized(value) for value in aliases}:
                aliases.append(name)
                item.aliases = aliases
        item.geometry = geometry
        item.source_name = source["name"]
        item.source_ref = source_ref
        item.source_url = source["url"]
        item.source_version = str(properties.get(source["version_field"]) or source["version"])
        item.active = True
        imported.append(item)
    if not imported:
        raise TerritoryImportError("A fonte oficial não retornou territórios utilizáveis.")
    db.session.flush()
    return imported


def _upsert_neighborhoods(
    tenant: Tenant, rows: list[dict], territories: list[Territory]
) -> int:
    existing = {
        item.external_code: item
        for item in db.session.execute(
            select(TerritoryNeighborhood).where(
                TerritoryNeighborhood.tenant_id == tenant.id,
                TerritoryNeighborhood.source_name == IBGE_NEIGHBORHOOD_SOURCE,
            )
        ).scalars()
    }
    matched = 0
    for row in rows:
        territory = _territory_for_geometry(territories, row["geometry"])
        matched += territory is not None
        item = existing.get(row["external_code"])
        if item is None:
            item = TerritoryNeighborhood(
                tenant_id=tenant.id,
                external_code=row["external_code"],
                source_name=IBGE_NEIGHBORHOOD_SOURCE,
                name=row["name"],
                normalized_name=_normalized(row["name"]),
            )
            db.session.add(item)
        item.territory_id = territory.id if territory else None
        item.name = row["name"]
        item.normalized_name = _normalized(row["name"])
        item.geometry = row["geometry"]
        item.source_url = row["source_url"]
        item.source_version = row["source_version"]
        item.updated_at = datetime.now(UTC)
    db.session.flush()
    return matched


def _territory_for_geometry(
    territories: list[Territory], geometry: dict | None
) -> Territory | None:
    point = _geometry_centroid(geometry)
    if point is None:
        return None
    longitude, latitude = point
    containing = [
        territory
        for territory in territories
        if geometry_contains(territory.geometry, latitude, longitude)
    ]
    return min(containing, key=lambda item: geometry_area(item.geometry)) if containing else None


def _geometry_centroid(geometry: dict | None) -> tuple[float, float] | None:
    if not geometry:
        return None
    polygons = (
        geometry.get("coordinates", [])
        if geometry.get("type") == "MultiPolygon"
        else [geometry.get("coordinates", [])]
    )
    best = None
    best_area = 0.0
    for polygon in polygons:
        ring = polygon[0] if polygon else []
        if len(ring) < 4:
            continue
        cross_sum = 0.0
        x_sum = 0.0
        y_sum = 0.0
        for first, second in zip(ring, ring[1:], strict=False):
            cross = first[0] * second[1] - second[0] * first[1]
            cross_sum += cross
            x_sum += (first[0] + second[0]) * cross
            y_sum += (first[1] + second[1]) * cross
        area = abs(cross_sum / 2)
        if area > best_area and abs(cross_sum) > 1e-15:
            best = (x_sum / (3 * cross_sum), y_sum / (3 * cross_sum))
            best_area = area
    return best


def _fetch_bytes(url: str, *, max_bytes: int) -> bytes:
    request = urllib.request.Request(url, headers={"User-Agent": "GabFlow/1.0"})  # noqa: S310
    try:
        with urllib.request.urlopen(request, timeout=20) as response:  # noqa: S310
            length = int(response.headers.get("Content-Length") or 0)
            if length > max_bytes:
                raise TerritoryImportError("A fonte geográfica excede o tamanho permitido.")
            body = response.read(max_bytes + 1)
    except (OSError, TimeoutError, urllib.error.URLError) as error:
        raise TerritoryImportError(
            "Não foi possível consultar a fonte geográfica oficial."
        ) from error
    if len(body) > max_bytes:
        raise TerritoryImportError("A fonte geográfica excede o tamanho permitido.")
    return body


def _territory_key(value: str) -> str:
    key = _normalized(value)
    return key.removeprefix("zona ")


def _normalized(value: str) -> str:
    text = " ".join(str(value).lower().split())
    return "".join(char for char in normalize("NFKD", text) if not combining(char))
