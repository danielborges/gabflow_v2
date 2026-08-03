import csv
import hashlib
import io
import json
import os
import shutil
import tempfile
import uuid
import zipfile
from datetime import UTC, date, datetime
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from flask import current_app
from sqlalchemy import delete, func, insert, select

from app.electoral.text import normalize_search
from app.extensions import db
from app.models import (
    ElectoralCandidacy,
    ElectoralCandidate,
    ElectoralDatasetStatus,
    ElectoralDatasetVersion,
    ElectoralElection,
    ElectoralOffice,
    ElectoralParty,
    ElectoralResult,
    ElectoralStagingResult,
    ElectoralTerritory,
    ElectoralTerritoryLevel,
    OutboxEvent,
)

PARSER_VERSION = "tse-munzona-v2"
OFFICIAL_SOURCE_HOSTS = {"cdn.tse.jus.br", "dadosabertos.tse.jus.br"}
IMPORTED_EVENT = "electoral.dataset.imported"
PUBLISHED_EVENT = "electoral.dataset.published"
NULL_VALUES = {"", "#NULO#", "NULO", "-1"}


class ElectoralImportError(RuntimeError):
    def __init__(self, message: str, dataset_id: uuid.UUID | None = None):
        super().__init__(message)
        self.dataset_id = dataset_id


def download_official_archive(source_url: str) -> Path:
    _validate_source_url(source_url)
    storage = _storage_root() / "downloads"
    storage.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix="tse-", suffix=".zip", dir=storage)
    os.close(descriptor)
    target = Path(temporary_name)
    request = Request(  # noqa: S310 - URL validated against HTTPS TSE allowlist
        source_url, headers={"User-Agent": "GabFlow-Electoral/1.0"}
    )
    total = 0
    try:
        with (
            urlopen(  # noqa: S310 - host and final URL are explicitly allowlisted
                request, timeout=current_app.config["ELECTORAL_DOWNLOAD_TIMEOUT_SECONDS"]
            ) as response,
            target.open("wb") as output,
        ):
            _validate_source_url(response.geturl())
            while chunk := response.read(1024 * 1024):
                total += len(chunk)
                if total > current_app.config["ELECTORAL_MAX_ARCHIVE_BYTES"]:
                    raise ElectoralImportError("Arquivo eleitoral excede o limite configurado.")
                output.write(chunk)
        return target
    except Exception:
        target.unlink(missing_ok=True)
        raise


def import_dataset_archive(
    archive_path: str | Path,
    *,
    source_url: str,
    election_year: int,
    election_scope: str,
    uf: str,
    office_code: str | None = None,
    expected_total_votes: int | None = None,
    publish: bool = True,
) -> tuple[ElectoralDatasetVersion, bool]:
    path = Path(archive_path).resolve()
    if not path.is_file():
        raise ElectoralImportError("Arquivo eleitoral nao encontrado.")
    _validate_source_url(source_url)
    values = _coverage_values(election_year, election_scope, uf, office_code)
    source_hash = _file_hash(path)
    coverage_key = hashlib.sha256(
        json.dumps(values, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    existing = db.session.execute(
        select(ElectoralDatasetVersion).where(
            ElectoralDatasetVersion.source_hash == source_hash,
            ElectoralDatasetVersion.coverage_key == coverage_key,
            ElectoralDatasetVersion.parser_version == PARSER_VERSION,
        )
    ).scalar_one_or_none()
    if existing is not None:
        return existing, True

    raw_path = _store_raw_archive(path, source_hash)
    now = datetime.now(UTC)
    dataset = ElectoralDatasetVersion(
        source_name="Tribunal Superior Eleitoral - Dados Abertos",
        source_url=source_url,
        source_hash=source_hash,
        source_format="ZIP_CSV",
        parser_version=PARSER_VERSION,
        coverage_key=coverage_key,
        coverage=values,
        source_metadata={"license": "CC-BY", "official": True},
        validation_manifest={},
        raw_storage_path=str(raw_path),
        status=ElectoralDatasetStatus.DOWNLOADED,
        downloaded_at=now,
        **values,
    )
    db.session.add(dataset)
    db.session.commit()
    try:
        manifest = _stage_archive(dataset, path, expected_total_votes)
        _promote_staging(dataset)
        dataset.status = ElectoralDatasetStatus.VALIDATED
        dataset.validated_at = datetime.now(UTC)
        dataset.validation_manifest = manifest
        dataset.quality_score = manifest["qualityScore"]
        _enqueue_dataset_event(dataset, IMPORTED_EVENT)
        if publish:
            _publish_dataset(dataset)
        db.session.execute(
            delete(ElectoralStagingResult).where(
                ElectoralStagingResult.dataset_version_id == dataset.id
            )
        )
        db.session.commit()
        return dataset, False
    except Exception as error:
        db.session.rollback()
        dataset = db.session.get(ElectoralDatasetVersion, dataset.id)
        if dataset is not None:
            dataset.status = ElectoralDatasetStatus.REJECTED
            dataset.validation_manifest = {
                **(dataset.validation_manifest or {}),
                "blockingErrors": [str(error)[:500]],
            }
            db.session.commit()
        if isinstance(error, ElectoralImportError):
            error.dataset_id = dataset.id if dataset else None
            raise
        raise ElectoralImportError(str(error), dataset.id if dataset else None) from error


def publish_validated_dataset(dataset_id: uuid.UUID) -> ElectoralDatasetVersion:
    dataset = db.session.get(ElectoralDatasetVersion, dataset_id)
    if dataset is None:
        raise ElectoralImportError("Versao eleitoral nao encontrada.")
    if dataset.status == ElectoralDatasetStatus.PUBLISHED:
        return dataset
    if dataset.status != ElectoralDatasetStatus.VALIDATED:
        raise ElectoralImportError("Somente uma versao validada pode ser publicada.")
    _publish_dataset(dataset)
    db.session.commit()
    return dataset


def _stage_archive(
    dataset: ElectoralDatasetVersion,
    path: Path,
    expected_total_votes: int | None,
) -> dict:
    batch_size = current_app.config["ELECTORAL_IMPORT_BATCH_SIZE"]
    batch = []
    matched = invalid = total_votes = 0
    error_samples = []
    with zipfile.ZipFile(path) as archive:
        infos = [info for info in archive.infolist() if info.filename.lower().endswith(".csv")]
        if not infos:
            raise ElectoralImportError("ZIP do TSE nao contem arquivo CSV.")
        state_partition = [
            info for info in infos if info.filename.lower().endswith(f"_{dataset.uf.lower()}.csv")
        ]
        if state_partition:
            infos = state_partition
        else:
            national_partition = [
                info for info in infos if info.filename.lower().endswith("_brasil.csv")
            ]
            if national_partition:
                infos = national_partition
        uncompressed = sum(info.file_size for info in infos)
        if uncompressed > current_app.config["ELECTORAL_MAX_UNCOMPRESSED_BYTES"]:
            raise ElectoralImportError("Conteudo descompactado excede o limite configurado.")
        row_number = 0
        for info in infos:
            with archive.open(info) as raw:
                reader = csv.DictReader(io.TextIOWrapper(raw, encoding="latin-1"), delimiter=";")
                for source_row in reader:
                    row_number += 1
                    if not _matches_coverage(source_row, dataset):
                        continue
                    matched += 1
                    try:
                        canonical = _canonical_row(source_row, dataset)
                        total_votes += canonical["votes"]
                        validation_error = None
                    except ValueError as error:
                        canonical = {}
                        validation_error = str(error)[:500]
                        invalid += 1
                        if len(error_samples) < 20:
                            error_samples.append({"row": row_number, "error": validation_error})
                    batch.append(
                        {
                            "id": uuid.uuid4(),
                            "dataset_version_id": dataset.id,
                            "row_number": row_number,
                            "canonical_data": canonical,
                            "validation_error": validation_error,
                            "created_at": datetime.now(UTC),
                        }
                    )
                    if len(batch) >= batch_size:
                        db.session.execute(insert(ElectoralStagingResult), batch)
                        db.session.commit()
                        batch.clear()
    if batch:
        db.session.execute(insert(ElectoralStagingResult), batch)
        db.session.commit()
    dataset.status = ElectoralDatasetStatus.PARSED
    dataset.row_count = matched - invalid
    dataset.invalid_rows = invalid
    dataset.total_votes = total_votes
    consistency = None if expected_total_votes is None else expected_total_votes == total_votes
    completeness = (matched - invalid) / matched if matched else 0
    quality = round(
        completeness
        if consistency is None
        else 0.7 * completeness + 0.3 * (1 if consistency else 0),
        4,
    )
    manifest = {
        "matchedRows": matched,
        "validRows": matched - invalid,
        "invalidRows": invalid,
        "totalVotes": total_votes,
        "expectedTotalVotes": expected_total_votes,
        "totalizationChecked": consistency is not None,
        "totalizationConsistent": consistency,
        "errorSamples": error_samples,
        "qualityScore": quality,
        "parserVersion": PARSER_VERSION,
        "sourceFiles": [info.filename for info in infos],
    }
    dataset.validation_manifest = manifest
    db.session.commit()
    if matched == 0:
        raise ElectoralImportError("Nenhuma linha corresponde ao recorte informado.")
    if invalid:
        raise ElectoralImportError(f"Carga possui {invalid} linha(s) invalida(s).")
    if consistency is False:
        raise ElectoralImportError("Total de votos diverge da totalizacao esperada.")
    return manifest


def _promote_staging(dataset: ElectoralDatasetVersion) -> None:
    offices = {item.code: item for item in db.session.scalars(select(ElectoralOffice))}
    elections = {}
    parties = {}
    candidates = {}
    candidacies = {}
    territories = {}
    results = {}
    rows = db.session.execute(
        select(ElectoralStagingResult)
        .where(
            ElectoralStagingResult.dataset_version_id == dataset.id,
            ElectoralStagingResult.validation_error.is_(None),
        )
        .order_by(ElectoralStagingResult.row_number)
    ).scalars()
    for staged in rows:
        row = staged.canonical_data
        office = offices.get(row["officeCode"])
        if office is None:
            office = ElectoralOffice(code=row["officeCode"], name=row["officeName"])
            db.session.add(office)
            db.session.flush()
            offices[office.code] = office
        election = elections.get(row["electionExternalId"])
        if election is None:
            election = ElectoralElection(
                dataset_version_id=dataset.id,
                external_id=row["electionExternalId"],
                name=row["electionName"],
                year=row["year"],
                round=row["round"],
                scope=dataset.election_scope,
                election_date=_parse_date(row.get("electionDate")),
                uf=row["uf"],
            )
            db.session.add(election)
            db.session.flush()
            elections[election.external_id] = election
        party = parties.get(row["partyNumber"])
        if party is None:
            party = ElectoralParty(
                dataset_version_id=dataset.id,
                number=row["partyNumber"],
                acronym=row["partyAcronym"],
                name=row["partyName"],
            )
            db.session.add(party)
            db.session.flush()
            parties[party.number] = party
        candidate = candidates.get(row["candidateExternalId"])
        if candidate is None:
            candidate = ElectoralCandidate(
                dataset_version_id=dataset.id,
                external_id=row["candidateExternalId"],
                full_name=row["candidateName"],
                ballot_name=row["candidateBallotName"],
                normalized_name=normalize_search(
                    f"{row['candidateName']} {row['candidateBallotName']}"
                ),
            )
            db.session.add(candidate)
            db.session.flush()
            candidates[candidate.external_id] = candidate
        candidacy_key = (election.id, candidate.id, office.id)
        candidacy = candidacies.get(candidacy_key)
        if candidacy is None:
            candidacy = ElectoralCandidacy(
                dataset_version_id=dataset.id,
                election_id=election.id,
                office_id=office.id,
                candidate_id=candidate.id,
                party_id=party.id,
                ballot_number=row["candidateNumber"],
                status=row.get("candidateStatus"),
            )
            db.session.add(candidacy)
            db.session.flush()
            candidacies[candidacy_key] = candidacy
        territory_key = (row["uf"], row["municipalityCode"], row["zone"])
        territory = territories.get(territory_key)
        if territory is None:
            territory = ElectoralTerritory(
                dataset_version_id=dataset.id,
                level=ElectoralTerritoryLevel.ELECTORAL_ZONE,
                uf=row["uf"],
                municipality_code=row["municipalityCode"],
                municipality_name=row["municipalityName"],
                zone=row["zone"],
                derived=False,
            )
            db.session.add(territory)
            db.session.flush()
            territories[territory_key] = territory
        result_key = (election.id, candidacy.id, territory.id)
        result = results.get(result_key)
        if result is None:
            result = ElectoralResult(
                dataset_version_id=dataset.id,
                election_id=election.id,
                candidacy_id=candidacy.id,
                territory_id=territory.id,
                votes=row["votes"],
                calculation_metadata={"sourceField": "QT_VOTOS_NOMINAIS"},
            )
            db.session.add(result)
            results[result_key] = result
        else:
            result.votes += row["votes"]
    db.session.flush()
    promoted_votes = (
        db.session.scalar(
            select(func.sum(ElectoralResult.votes)).where(
                ElectoralResult.dataset_version_id == dataset.id
            )
        )
        or 0
    )
    if promoted_votes != dataset.total_votes:
        raise ElectoralImportError("Total promovido diverge do staging validado.")


def _publish_dataset(dataset: ElectoralDatasetVersion) -> None:
    previous = db.session.execute(
        select(ElectoralDatasetVersion).where(
            ElectoralDatasetVersion.id != dataset.id,
            ElectoralDatasetVersion.status == ElectoralDatasetStatus.PUBLISHED,
            ElectoralDatasetVersion.election_year == dataset.election_year,
            ElectoralDatasetVersion.election_scope == dataset.election_scope,
            ElectoralDatasetVersion.uf == dataset.uf,
            ElectoralDatasetVersion.office_code == dataset.office_code,
        )
    ).scalars()
    for version in previous:
        version.status = ElectoralDatasetStatus.SUPERSEDED
    dataset.status = ElectoralDatasetStatus.PUBLISHED
    dataset.published_at = datetime.now(UTC)
    _enqueue_dataset_event(dataset, PUBLISHED_EVENT)


def _enqueue_dataset_event(dataset: ElectoralDatasetVersion, event_type: str) -> None:
    event_id = uuid.uuid4()
    payload = {
        "event_id": str(event_id),
        "event_version": 1,
        "occurred_at": datetime.now(UTC).isoformat(),
        "idempotency_key": f"{event_type}:{dataset.id}",
        "dataset_version_id": str(dataset.id),
    }
    if event_type == IMPORTED_EVENT:
        payload["source_hash"] = dataset.source_hash
    else:
        payload["quality_score"] = dataset.quality_score
    db.session.add(
        OutboxEvent(
            id=event_id,
            tenant_id=None,
            event_type=event_type,
            aggregate_type="electoral_dataset_version",
            aggregate_id=str(dataset.id),
            payload=payload,
        )
    )


def _canonical_row(row: dict, dataset: ElectoralDatasetVersion) -> dict:
    values = {
        "year": _integer(_required(row, "ANO_ELEICAO"), "ANO_ELEICAO"),
        "round": _integer(_required(row, "NR_TURNO"), "NR_TURNO"),
        "electionExternalId": _required(row, "CD_ELEICAO"),
        "electionName": _required(row, "DS_ELEICAO"),
        "electionDate": _clean(row.get("DT_ELEICAO")),
        "uf": _required(row, "SG_UF").upper(),
        "municipalityCode": _required(row, "CD_MUNICIPIO"),
        "municipalityName": _required(row, "NM_MUNICIPIO"),
        "zone": _integer(_required(row, "NR_ZONA"), "NR_ZONA"),
        "officeCode": _required(row, "CD_CARGO"),
        "officeName": _required(row, "DS_CARGO"),
        "candidateExternalId": _required(row, "SQ_CANDIDATO"),
        "candidateNumber": _required(row, "NR_CANDIDATO"),
        "candidateName": _required(row, "NM_CANDIDATO"),
        "candidateBallotName": _required(row, "NM_URNA_CANDIDATO"),
        "candidateStatus": _clean(row.get("DS_SITUACAO_CANDIDATURA")),
        "partyNumber": _integer(_required(row, "NR_PARTIDO"), "NR_PARTIDO"),
        "partyAcronym": _required(row, "SG_PARTIDO"),
        "partyName": _required(row, "NM_PARTIDO"),
        "votes": _integer(_required(row, "QT_VOTOS_NOMINAIS"), "QT_VOTOS_NOMINAIS"),
    }
    if values["votes"] < 0:
        raise ValueError("QT_VOTOS_NOMINAIS nao pode ser negativo.")
    if values["year"] != dataset.election_year or values["uf"] != dataset.uf:
        raise ValueError("Linha fora da cobertura declarada.")
    return values


def _matches_coverage(row: dict, dataset: ElectoralDatasetVersion) -> bool:
    year = _clean(row.get("ANO_ELEICAO"))
    uf = _clean(row.get("SG_UF")).upper()
    office = _clean(row.get("CD_CARGO"))
    return (
        year == str(dataset.election_year)
        and uf == dataset.uf
        and (dataset.office_code is None or office == dataset.office_code)
    )


def _coverage_values(year, scope, uf, office_code) -> dict:
    try:
        year = int(year)
    except (TypeError, ValueError) as error:
        raise ElectoralImportError("Ano eleitoral invalido.") from error
    scope = str(scope).strip().lower()
    uf = str(uf).strip().upper()
    office_code = str(office_code).strip() if office_code else None
    if year < 2012 or scope not in {"municipal", "general"} or len(uf) != 2:
        raise ElectoralImportError("Cobertura eleitoral invalida.")
    return {
        "election_year": year,
        "election_scope": scope,
        "uf": uf,
        "office_code": office_code,
    }


def _required(row: dict, key: str) -> str:
    value = _clean(row.get(key))
    if value.upper() in NULL_VALUES:
        raise ValueError(f"Campo obrigatorio ausente: {key}.")
    return value


def _clean(value) -> str:
    return str(value or "").strip().strip('"')


def _integer(value, field: str) -> int:
    try:
        return int(str(value))
    except (TypeError, ValueError) as error:
        raise ValueError(f"Campo inteiro invalido: {field}.") from error


def _parse_date(value) -> date | None:
    if not value:
        return None
    for pattern in ("%d/%m/%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(value, pattern).date()
        except ValueError:
            continue
    return None


def _validate_source_url(value: str) -> None:
    parsed = urlparse(str(value))
    if parsed.scheme != "https" or parsed.hostname not in OFFICIAL_SOURCE_HOSTS:
        raise ElectoralImportError("Origem deve pertencer a um host oficial do TSE.")


def _file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _store_raw_archive(source: Path, source_hash: str) -> Path:
    root = _storage_root() / "raw" / source_hash[:2]
    root.mkdir(parents=True, exist_ok=True)
    target = root / f"{source_hash}.zip"
    if not target.exists():
        shutil.copyfile(source, target)
    return target


def _storage_root() -> Path:
    return Path(current_app.config["ELECTORAL_STORAGE_PATH"]).resolve()
