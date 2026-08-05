import csv
import io
import uuid
import zipfile
from datetime import UTC, datetime
from pathlib import Path

from flask import current_app
from sqlalchemy import insert, select

from app.electoral.ingestion import (
    ElectoralImportError,
    _clean,
    _file_hash,
    _integer,
    _store_raw_archive,
    _validate_source_url,
)
from app.extensions import db
from app.models import (
    ElectoralCandidacy,
    ElectoralCandidate,
    ElectoralDatasetStatus,
    ElectoralDatasetVersion,
    ElectoralElection,
    ElectoralOffice,
    ElectoralSectionResult,
    ElectoralTerritorialDatasetVersion,
    ElectoralTerritorialUnit,
)

TERRITORIAL_PARSER_VERSION = "tse-section-location-v1"
SECTION_ARCHIVE_TEMPLATE = (
    "https://cdn.tse.jus.br/estatistica/sead/odsele/"
    "votacao_secao/votacao_secao_{year}_{uf}.zip"
)
LOCATION_ARCHIVE_TEMPLATE = (
    "https://cdn.tse.jus.br/estatistica/sead/odsele/"
    "eleitorado_locais_votacao/eleitorado_local_votacao_{year}.zip"
)
DETAILED_LEVELS = ("neighborhood", "polling_place", "section")


def official_section_archive_url(year: int, uf: str) -> str:
    return SECTION_ARCHIVE_TEMPLATE.format(year=int(year), uf=uf.strip().upper())


def official_location_archive_url(year: int) -> str:
    return LOCATION_ARCHIVE_TEMPLATE.format(year=int(year))


def import_territorial_detail(
    dataset_id: uuid.UUID,
    section_archive: str | Path,
    location_archive: str | Path,
    *,
    section_source_url: str,
    location_source_url: str,
) -> tuple[ElectoralTerritorialDatasetVersion, bool]:
    dataset = db.session.get(ElectoralDatasetVersion, dataset_id)
    if dataset is None or dataset.status != ElectoralDatasetStatus.PUBLISHED:
        raise ElectoralImportError("Dataset eleitoral publicado nao encontrado.")
    section_path = Path(section_archive).resolve()
    location_path = Path(location_archive).resolve()
    if not section_path.is_file() or not location_path.is_file():
        raise ElectoralImportError("Arquivos territoriais nao encontrados.")
    _validate_source_url(section_source_url)
    _validate_source_url(location_source_url)
    section_hash = _file_hash(section_path)
    location_hash = _file_hash(location_path)
    existing = db.session.scalar(
        select(ElectoralTerritorialDatasetVersion).where(
            ElectoralTerritorialDatasetVersion.dataset_version_id == dataset.id,
            ElectoralTerritorialDatasetVersion.section_source_hash == section_hash,
            ElectoralTerritorialDatasetVersion.location_source_hash == location_hash,
            ElectoralTerritorialDatasetVersion.parser_version == TERRITORIAL_PARSER_VERSION,
        )
    )
    if existing is not None and existing.status == ElectoralDatasetStatus.PUBLISHED:
        return existing, True
    if existing is not None:
        db.session.delete(existing)
        db.session.commit()

    version = ElectoralTerritorialDatasetVersion(
        dataset_version_id=dataset.id,
        section_source_url=section_source_url,
        section_source_hash=section_hash,
        location_source_url=location_source_url,
        location_source_hash=location_hash,
        parser_version=TERRITORIAL_PARSER_VERSION,
        status=ElectoralDatasetStatus.DOWNLOADED,
        validation_manifest={},
        section_storage_path=str(_store_raw_archive(section_path, section_hash)),
        location_storage_path=str(_store_raw_archive(location_path, location_hash)),
    )
    db.session.add(version)
    db.session.commit()
    try:
        manifest = _load_detail(version, dataset, section_path, location_path)
        previous = list(
            db.session.scalars(
                select(ElectoralTerritorialDatasetVersion).where(
                    ElectoralTerritorialDatasetVersion.dataset_version_id == dataset.id,
                    ElectoralTerritorialDatasetVersion.id != version.id,
                    ElectoralTerritorialDatasetVersion.status
                    == ElectoralDatasetStatus.PUBLISHED,
                )
            )
        )
        for item in previous:
            item.status = ElectoralDatasetStatus.SUPERSEDED
        now = datetime.now(UTC)
        version.status = ElectoralDatasetStatus.PUBLISHED
        version.validated_at = now
        version.published_at = now
        version.validation_manifest = manifest
        version.quality_score = manifest["qualityScore"]
        db.session.commit()
        return version, False
    except Exception as error:
        db.session.rollback()
        version = db.session.get(ElectoralTerritorialDatasetVersion, version.id)
        if version is not None:
            version.status = ElectoralDatasetStatus.REJECTED
            version.validation_manifest = {"blockingErrors": [str(error)[:500]]}
            db.session.commit()
        if isinstance(error, ElectoralImportError):
            raise
        raise ElectoralImportError(str(error)) from error


def _load_detail(version, dataset, section_path: Path, location_path: Path) -> dict:
    locations, location_file = _load_locations(
        location_path, year=dataset.election_year, uf=dataset.uf
    )
    candidacies = {
        (election.external_id, candidate.external_id, office.code): candidacy.id
        for candidacy, candidate, election, office in db.session.execute(
            select(ElectoralCandidacy, ElectoralCandidate, ElectoralElection, ElectoralOffice)
            .join(ElectoralCandidate, ElectoralCandidate.id == ElectoralCandidacy.candidate_id)
            .join(ElectoralElection, ElectoralElection.id == ElectoralCandidacy.election_id)
            .join(ElectoralOffice, ElectoralOffice.id == ElectoralCandidacy.office_id)
            .where(ElectoralCandidacy.dataset_version_id == dataset.id)
        )
    }
    if not candidacies:
        raise ElectoralImportError("Dataset base nao possui candidaturas para vincular.")

    batch_size = max(current_app.config["ELECTORAL_IMPORT_BATCH_SIZE"], 10_000)
    result_batch: dict[tuple[uuid.UUID, uuid.UUID], int] = {}
    units: dict[tuple[str, int, int], uuid.UUID] = {}
    matched_rows = invalid_rows = unmatched_rows = total_votes = mapped_neighborhoods = 0
    section_file = None
    try:
        with zipfile.ZipFile(section_path) as archive:
            info = _section_csv(archive, dataset.uf)
            section_file = info.filename
            with archive.open(info) as raw:
                rows = csv.DictReader(io.TextIOWrapper(raw, encoding="latin-1"), delimiter=";")
                for row in rows:
                    if _clean(row.get("ANO_ELEICAO")) != str(dataset.election_year):
                        continue
                    if _clean(row.get("SG_UF")).upper() != dataset.uf:
                        continue
                    candidacy_id = candidacies.get(
                        (
                            _clean(row.get("CD_ELEICAO")),
                            _clean(row.get("SQ_CANDIDATO")),
                            _clean(row.get("CD_CARGO")),
                        )
                    )
                    if candidacy_id is None:
                        unmatched_rows += 1
                        continue
                    try:
                        municipality_code = _required(row, "CD_MUNICIPIO")
                        zone = _integer(_required(row, "NR_ZONA"), "NR_ZONA")
                        section = _integer(_required(row, "NR_SECAO"), "NR_SECAO")
                        votes = _integer(_required(row, "QT_VOTOS"), "QT_VOTOS")
                        if votes < 0:
                            raise ValueError("QT_VOTOS nao pode ser negativo.")
                        unit_key = (municipality_code, zone, section)
                        unit_id = units.get(unit_key)
                        if unit_id is None:
                            location = locations.get(unit_key, {})
                            neighborhood = _nullable(location.get("NM_BAIRRO"))
                            unit_id = uuid.uuid4()
                            unit = ElectoralTerritorialUnit(
                                id=unit_id,
                                territorial_dataset_version_id=version.id,
                                uf=dataset.uf,
                                municipality_code=municipality_code,
                                municipality_name=_required(row, "NM_MUNICIPIO"),
                                zone=zone,
                                section=section,
                                polling_place_number=_integer(
                                    _required(row, "NR_LOCAL_VOTACAO"), "NR_LOCAL_VOTACAO"
                                ),
                                polling_place_name=(
                                    _nullable(location.get("NM_LOCAL_VOTACAO"))
                                    or _required(row, "NM_LOCAL_VOTACAO")
                                ),
                                polling_place_address=(
                                    _nullable(location.get("DS_ENDERECO"))
                                    or _nullable(row.get("DS_LOCAL_VOTACAO_ENDERECO"))
                                ),
                                neighborhood=neighborhood,
                                latitude=_coordinate(location.get("NR_LATITUDE")),
                                longitude=_coordinate(location.get("NR_LONGITUDE")),
                                mapping_type=("OFFICIAL" if location else "OFFICIAL_SECTION_ONLY"),
                                mapping_metadata={
                                    "neighborhoodDerivedFromPollingPlace": bool(neighborhood),
                                    "locationRegistryMatched": bool(location),
                                },
                            )
                            db.session.add(unit)
                            units[unit_key] = unit_id
                            mapped_neighborhoods += bool(neighborhood)
                        result_key = (candidacy_id, unit_id)
                        result_batch[result_key] = result_batch.get(result_key, 0) + votes
                        matched_rows += 1
                        total_votes += votes
                    except ValueError:
                        invalid_rows += 1
                    if len(result_batch) >= batch_size:
                        _flush_results(version.id, result_batch)
        if result_batch:
            _flush_results(version.id, result_batch)
        db.session.commit()
    except zipfile.BadZipFile as error:
        raise ElectoralImportError("ZIP territorial invalido.") from error

    if matched_rows == 0:
        raise ElectoralImportError("Nenhum voto nominal foi vinculado ao dataset base.")
    if invalid_rows:
        raise ElectoralImportError(f"Carga territorial possui {invalid_rows} linha(s) invalida(s).")
    if total_votes != dataset.total_votes:
        raise ElectoralImportError(
            f"Total territorial ({total_votes}) diverge do dataset base ({dataset.total_votes})."
        )
    unit_count = len(units)
    neighborhood_coverage = mapped_neighborhoods / unit_count if unit_count else 0
    version.row_count = matched_rows
    version.invalid_rows = invalid_rows
    version.total_votes = total_votes
    return {
        "matchedRows": matched_rows,
        "invalidRows": invalid_rows,
        "unmatchedNonCandidateRows": unmatched_rows,
        "totalVotes": total_votes,
        "baseTotalVotes": dataset.total_votes,
        "totalizationConsistent": True,
        "territorialUnits": unit_count,
        "neighborhoodMappedUnits": mapped_neighborhoods,
        "neighborhoodCoverage": round(neighborhood_coverage, 6),
        "qualityScore": round(0.8 + (0.2 * neighborhood_coverage), 4),
        "parserVersion": TERRITORIAL_PARSER_VERSION,
        "sourceFiles": [section_file, location_file],
        "granularities": [
            "municipality",
            "electoral_zone",
            "neighborhood",
            "polling_place",
            "section",
        ],
        "derivedGranularities": ["neighborhood"],
    }


def _load_locations(path: Path, *, year: int, uf: str) -> tuple[dict, str]:
    locations = {}
    try:
        with zipfile.ZipFile(path) as archive:
            infos = [item for item in archive.infolist() if item.filename.lower().endswith(".csv")]
            if not infos:
                raise ElectoralImportError("ZIP de locais nao contem CSV.")
            info = infos[0]
            with archive.open(info) as raw:
                rows = csv.DictReader(io.TextIOWrapper(raw, encoding="latin-1"), delimiter=";")
                for row in rows:
                    if _clean(row.get("AA_ELEICAO")) != str(year):
                        continue
                    if _clean(row.get("SG_UF")).upper() != uf:
                        continue
                    key = (
                        _required(row, "CD_MUNICIPIO"),
                        _integer(_required(row, "NR_ZONA"), "NR_ZONA"),
                        _integer(_required(row, "NR_SECAO"), "NR_SECAO"),
                    )
                    locations[key] = row
            return locations, info.filename
    except zipfile.BadZipFile as error:
        raise ElectoralImportError("ZIP de locais invalido.") from error


def _section_csv(archive: zipfile.ZipFile, uf: str) -> zipfile.ZipInfo:
    infos = [item for item in archive.infolist() if item.filename.lower().endswith(".csv")]
    state = [item for item in infos if item.filename.lower().endswith(f"_{uf.lower()}.csv")]
    if state:
        return state[0]
    if len(infos) == 1:
        return infos[0]
    raise ElectoralImportError("ZIP de secoes nao possui particao da UF declarada.")


def _flush_results(version_id: uuid.UUID, batch: dict) -> None:
    db.session.flush()
    values = [
        {
            "id": uuid.uuid4(),
            "territorial_dataset_version_id": version_id,
            "candidacy_id": candidacy_id,
            "territory_id": territory_id,
            "votes": votes,
        }
        for (candidacy_id, territory_id), votes in batch.items()
    ]
    if db.session.get_bind().dialect.name == "postgresql":
        driver_connection = db.session.connection().connection.driver_connection
        with driver_connection.cursor().copy(
            "COPY electoral_section_results "
            "(id, territorial_dataset_version_id, candidacy_id, territory_id, votes) "
            "FROM STDIN"
        ) as copy:
            for value in values:
                copy.write_row(
                    (
                        value["id"],
                        value["territorial_dataset_version_id"],
                        value["candidacy_id"],
                        value["territory_id"],
                        value["votes"],
                    )
                )
    else:
        db.session.execute(insert(ElectoralSectionResult), values)
    db.session.commit()
    batch.clear()


def _required(row: dict, key: str) -> str:
    value = _clean(row.get(key))
    if not value or value in {"-1", "#NULO#", "NULO"}:
        raise ValueError(f"Campo obrigatorio ausente: {key}.")
    return value


def _nullable(value) -> str | None:
    cleaned = _clean(value)
    return None if not cleaned or cleaned in {"-1", "#NULO#", "NULO"} else cleaned


def _coordinate(value) -> float | None:
    cleaned = _nullable(value)
    if cleaned is None:
        return None
    try:
        return float(cleaned.replace(",", "."))
    except ValueError:
        return None
