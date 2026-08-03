import gzip
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from flask import current_app
from sqlalchemy import select, text

from app.electoral.text import normalize_search
from app.extensions import db
from app.models import (
    ElectoralDatasetStatus,
    ElectoralDatasetVersion,
    ElectoralGeometryFeature,
    ElectoralGeometryVersion,
    ElectoralTerritory,
    ElectoralTerritoryCrosswalk,
)

OFFICIAL_GEOMETRY_HOST = "servicodados.ibge.gov.br"
IBGE_GEOMETRY_SOURCE = (
    "https://servicodados.ibge.gov.br/api/v3/malhas/estados/31"
    "?formato=application/vnd.geo+json&qualidade=intermediaria&intrarregiao=municipio"
)
IBGE_LOCALITIES_SOURCE = "https://servicodados.ibge.gov.br/api/v1/localidades/estados/31/municipios"
CURATED_CROSSWALK_ALIASES = {
    "barao de monte alto": "3105509",
    "dona eusebia": "3122900",
    "olhos d agua": "3145455",
    "pingo d agua": "3150539",
    "sao thome das letras": "3165206",
    "sem peixe": "3165560",
}


class ElectoralGeometryError(RuntimeError):
    pass


def download_official_json(source_url: str) -> bytes:
    _validate_source(source_url)
    request = Request(source_url, headers={"User-Agent": "GabFlow-Electoral/1.0"})  # noqa: S310
    with urlopen(  # noqa: S310 - HTTPS and official IBGE host are validated
        request,
        timeout=current_app.config["ELECTORAL_DOWNLOAD_TIMEOUT_SECONDS"],
    ) as response:
        _validate_source(response.geturl())
        payload = response.read(current_app.config["ELECTORAL_MAX_ARCHIVE_BYTES"] + 1)
        content_encoding = str(response.headers.get("Content-Encoding") or "").lower()
    if len(payload) > current_app.config["ELECTORAL_MAX_ARCHIVE_BYTES"]:
        raise ElectoralGeometryError("Malha oficial excede o limite configurado.")
    if content_encoding == "gzip" or payload.startswith(b"\x1f\x8b"):
        payload = gzip.decompress(payload)
    return payload


def import_geometry_geojson(
    payload: bytes,
    localities_payload: bytes,
    *,
    source_url: str,
    reference_year: int,
    uf: str,
    quality: str = "intermediaria",
) -> tuple[ElectoralGeometryVersion, bool, dict]:
    _validate_source(source_url)
    source_hash = hashlib.sha256(payload).hexdigest()
    existing = db.session.execute(
        select(ElectoralGeometryVersion).where(
            ElectoralGeometryVersion.source_hash == source_hash,
            ElectoralGeometryVersion.reference_year == reference_year,
            ElectoralGeometryVersion.uf == uf.upper(),
            ElectoralGeometryVersion.level == "municipality",
            ElectoralGeometryVersion.quality == quality,
        )
    ).scalar_one_or_none()
    if existing:
        _complete_curated_crosswalks(existing)
        db.session.commit()
        return existing, True, existing.source_metadata

    try:
        collection = json.loads(payload)
        localities = json.loads(localities_payload)
    except (TypeError, json.JSONDecodeError) as error:
        raise ElectoralGeometryError("Resposta geográfica oficial inválida.") from error
    features = collection.get("features") if isinstance(collection, dict) else None
    if (
        not isinstance(collection, dict)
        or collection.get("type") != "FeatureCollection"
        or not isinstance(features, list)
    ):
        raise ElectoralGeometryError("A malha não é uma FeatureCollection GeoJSON.")
    locality_names = {
        str(item["id"]): str(item["nome"])
        for item in localities
        if isinstance(item, dict) and item.get("id") and item.get("nome")
    }
    raw_path = _store_raw(payload, source_hash)
    version = ElectoralGeometryVersion(
        source_name="IBGE - Malha Municipal Digital",
        source_url=source_url,
        source_hash=source_hash,
        reference_year=reference_year,
        uf=uf.upper(),
        level="municipality",
        quality=quality,
        status="VALIDATED",
        feature_count=0,
        raw_storage_path=str(raw_path),
        source_metadata={
            "official": True,
            "referenceSystem": "SIRGAS 2000 / EPSG:4326",
            "format": "GeoJSON",
            "crosswalkMatched": 0,
            "crosswalkUnmatched": 0,
        },
    )
    db.session.add(version)
    db.session.flush()
    seen_codes = set()
    geometry_parameters = []
    feature_by_name = {}
    for raw_feature in features:
        code = str((raw_feature.get("properties") or {}).get("codarea") or "")
        geometry = raw_feature.get("geometry") or {}
        if not code or code in seen_codes or code not in locality_names:
            raise ElectoralGeometryError(
                f"Código geográfico ausente, duplicado ou desconhecido: {code}"
            )
        if geometry.get("type") not in {"Polygon", "MultiPolygon"}:
            raise ElectoralGeometryError(
                f"Geometria municipal não suportada: {geometry.get('type')}"
            )
        seen_codes.add(code)
        name = locality_names[code]
        item = ElectoralGeometryFeature(
            geometry_version_id=version.id,
            official_code=code,
            name=name,
            normalized_name=normalize_search(name),
            geometry_type=geometry["type"],
            geometry_geojson=geometry,
            bbox=_bbox(geometry["coordinates"]),
            derived=False,
        )
        db.session.add(item)
        db.session.flush()
        feature_by_name[item.normalized_name] = item
        geometry_parameters.append(
            {"feature_id": item.id, "geometry": json.dumps(geometry, separators=(",", ":"))}
        )
    if db.engine.dialect.name == "postgresql":
        db.session.execute(
            text(
                "UPDATE electoral_geometry_features "
                "SET geometry = ST_Multi(ST_SetSRID(ST_GeomFromGeoJSON(:geometry), 4326)) "
                "WHERE id = :feature_id"
            ),
            geometry_parameters,
        )
        missing_geometry = db.session.scalar(
            text(
                "SELECT count(*) FROM electoral_geometry_features "
                "WHERE geometry_version_id = :version_id AND geometry IS NULL"
            ),
            {"version_id": version.id},
        )
        if missing_geometry:
            raise ElectoralGeometryError("A conversão PostGIS deixou geometrias ausentes.")

    territory_rows = db.session.execute(
        select(
            ElectoralTerritory.municipality_code,
            ElectoralTerritory.municipality_name,
        )
        .join(
            ElectoralDatasetVersion,
            ElectoralDatasetVersion.id == ElectoralTerritory.dataset_version_id,
        )
        .where(
            ElectoralTerritory.uf == uf.upper(),
            ElectoralDatasetVersion.status == ElectoralDatasetStatus.PUBLISHED,
        )
        .distinct()
    ).all()
    electoral_names: dict[str, str] = {}
    for electoral_code, municipality_name in territory_rows:
        electoral_names.setdefault(str(electoral_code), str(municipality_name))
    matched = 0
    for electoral_code, municipality_name in electoral_names.items():
        feature = feature_by_name.get(normalize_search(municipality_name))
        if not feature:
            continue
        matched += 1
        db.session.add(
            ElectoralTerritoryCrosswalk(
                geometry_version_id=version.id,
                geometry_feature_id=feature.id,
                electoral_code=electoral_code,
                official_code=feature.official_code,
                method="exact_normalized_name",
                reviewed=False,
            )
        )
    version.feature_count = len(seen_codes)
    version.status = "PUBLISHED"
    version.published_at = datetime.now(UTC)
    version.source_metadata = {
        **version.source_metadata,
        "crosswalkMatched": matched,
        "crosswalkUnmatched": len(electoral_names) - matched,
    }
    _complete_curated_crosswalks(version)
    previous = db.session.execute(
        select(ElectoralGeometryVersion).where(
            ElectoralGeometryVersion.id != version.id,
            ElectoralGeometryVersion.uf == version.uf,
            ElectoralGeometryVersion.level == version.level,
            ElectoralGeometryVersion.status == "PUBLISHED",
        )
    ).scalars()
    for item in previous:
        item.status = "SUPERSEDED"
    db.session.commit()
    return version, False, version.source_metadata


def _complete_curated_crosswalks(version: ElectoralGeometryVersion) -> None:
    existing_codes = set(
        db.session.scalars(
            select(ElectoralTerritoryCrosswalk.electoral_code).where(
                ElectoralTerritoryCrosswalk.geometry_version_id == version.id
            )
        )
    )
    features_by_code = {
        item.official_code: item
        for item in db.session.scalars(
            select(ElectoralGeometryFeature).where(
                ElectoralGeometryFeature.geometry_version_id == version.id
            )
        )
    }
    territories = db.session.execute(
        select(ElectoralTerritory.municipality_code, ElectoralTerritory.municipality_name)
        .join(
            ElectoralDatasetVersion,
            ElectoralDatasetVersion.id == ElectoralTerritory.dataset_version_id,
        )
        .where(
            ElectoralTerritory.uf == version.uf,
            ElectoralDatasetVersion.status == ElectoralDatasetStatus.PUBLISHED,
        )
        .distinct()
    ).all()
    territory_count = len({str(code) for code, _ in territories})
    for electoral_code, municipality_name in territories:
        electoral_code = str(electoral_code)
        if electoral_code in existing_codes:
            continue
        alias_key = " ".join(
            normalize_search(municipality_name).replace("-", " ").replace("'", " ").split()
        )
        official_code = CURATED_CROSSWALK_ALIASES.get(alias_key)
        feature = features_by_code.get(official_code)
        if not feature:
            continue
        db.session.add(
            ElectoralTerritoryCrosswalk(
                geometry_version_id=version.id,
                geometry_feature_id=feature.id,
                electoral_code=electoral_code,
                official_code=official_code,
                method="curated_name_alias",
                reviewed=True,
                review_notes="Alias TSE–IBGE revisado no catálogo GabFlow.",
            )
        )
        existing_codes.add(electoral_code)
    version.source_metadata = {
        **(version.source_metadata or {}),
        "crosswalkMatched": len(existing_codes),
        "crosswalkUnmatched": max(0, territory_count - len(existing_codes)),
    }


def _bbox(coordinates) -> list[float]:
    points = []

    def collect(value):
        if value and isinstance(value[0], int | float):
            points.append(value)
            return
        for child in value:
            collect(child)

    collect(coordinates)
    if not points:
        raise ElectoralGeometryError("Geometria oficial sem coordenadas.")
    xs = [point[0] for point in points]
    ys = [point[1] for point in points]
    return [min(xs), min(ys), max(xs), max(ys)]


def _store_raw(payload: bytes, source_hash: str) -> Path:
    root = Path(current_app.config["ELECTORAL_STORAGE_PATH"]) / "geometries" / "raw"
    root.mkdir(parents=True, exist_ok=True)
    target = root / f"{source_hash}.geojson"
    if not target.exists():
        target.write_bytes(payload)
    return target


def _validate_source(source_url: str) -> None:
    parsed = urlparse(source_url)
    if parsed.scheme != "https" or parsed.hostname != OFFICIAL_GEOMETRY_HOST:
        raise ElectoralGeometryError("A geometria deve vir do serviço oficial HTTPS do IBGE.")
