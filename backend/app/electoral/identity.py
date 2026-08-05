import csv
import hashlib
import hmac
import io
import re
import uuid
import zipfile
from datetime import UTC, datetime
from pathlib import Path

from flask import current_app
from sqlalchemy import func, select

from app.electoral.ingestion import ElectoralImportError, _validate_source_url
from app.extensions import db
from app.models import (
    ElectoralCandidacy,
    ElectoralCandidacyOfficialIdentity,
    ElectoralCandidate,
    ElectoralCandidateRegistrySync,
    ElectoralDatasetStatus,
    ElectoralDatasetVersion,
    ElectoralElection,
    ElectoralOffice,
    ElectoralUserCandidacy,
    User,
)

AUTOMATIC_CPF_METHOD = "official_cpf"
MANUAL_FALLBACK_METHOD = "manual_fallback"
REGISTRY_PARSER_VERSION = "tse-consulta-cand-v1"


def official_candidate_registry_url(year: int) -> str:
    return (
        "https://cdn.tse.jus.br/estatistica/sead/odsele/consulta_cand/"
        f"consulta_cand_{int(year)}.zip"
    )


def cpf_fingerprint(cpf: str) -> str:
    digits = _cpf_digits(cpf)
    if len(digits) != 11:
        raise ValueError("CPF deve possuir 11 digitos.")
    secret = str(current_app.config["ELECTORAL_IDENTITY_HMAC_KEY"]).encode()
    return hmac.new(secret, digits.encode(), hashlib.sha256).hexdigest()


def sync_candidate_registry_archive(
    archive_path: str | Path,
    *,
    source_url: str,
    election_year: int,
    uf: str | None = None,
) -> tuple[ElectoralCandidateRegistrySync, bool]:
    path = Path(archive_path).resolve()
    if not path.is_file():
        raise ElectoralImportError("Cadastro oficial de candidaturas nao encontrado.")
    _validate_source_url(source_url)
    election_year = int(election_year)
    normalized_uf = str(uf or "").strip().upper() or None
    if normalized_uf and (len(normalized_uf) != 2 or not normalized_uf.isalpha()):
        raise ElectoralImportError("UF do cadastro de candidaturas invalida.")
    source_hash = _file_hash(path)
    key_version = int(current_app.config["ELECTORAL_IDENTITY_HMAC_KEY_VERSION"])
    existing = db.session.scalar(
        select(ElectoralCandidateRegistrySync).where(
            ElectoralCandidateRegistrySync.source_hash == source_hash,
            ElectoralCandidateRegistrySync.fingerprint_key_version == key_version,
        )
    )
    if existing is not None:
        return existing, True

    sync = ElectoralCandidateRegistrySync(
        election_year=election_year,
        uf=normalized_uf,
        source_url=source_url,
        source_hash=source_hash,
        fingerprint_key_version=key_version,
    )
    db.session.add(sync)
    db.session.flush()

    candidates = _published_candidacy_index(election_year, normalized_uf)
    identities = _official_identity_index(election_year, normalized_uf)
    total = invalid = cpf_rows = 0
    matched_ids: set[uuid.UUID] = set()
    generated_at = None

    try:
        with zipfile.ZipFile(path) as archive:
            infos = [item for item in archive.infolist() if item.filename.lower().endswith(".csv")]
            if not infos:
                raise ElectoralImportError("ZIP do cadastro TSE nao contem arquivo CSV.")
            uncompressed_size = sum(item.file_size for item in infos)
            if uncompressed_size > current_app.config["ELECTORAL_MAX_UNCOMPRESSED_BYTES"]:
                raise ElectoralImportError(
                    "Cadastro TSE descompactado excede o limite configurado."
                )
            for info in infos:
                with archive.open(info) as raw:
                    reader = csv.DictReader(
                        io.TextIOWrapper(raw, encoding="latin-1"), delimiter=";"
                    )
                    for row in reader:
                        if str(row.get("ANO_ELEICAO") or "").strip() != str(election_year):
                            continue
                        row_uf = str(row.get("SG_UF") or "").strip().upper()
                        if normalized_uf and row_uf not in {normalized_uf, "BR"}:
                            continue
                        total += 1
                        cpf = _cpf_digits(row.get("NR_CPF_CANDIDATO"))
                        external_id = str(row.get("SQ_CANDIDATO") or "").strip()
                        office_code = str(row.get("CD_CARGO") or "").strip()
                        ballot_number = str(row.get("NR_CANDIDATO") or "").strip()
                        if len(cpf) != 11 or not external_id or not office_code:
                            invalid += 1
                            continue
                        cpf_rows += 1
                        generated_at = generated_at or str(row.get("DT_GERACAO") or "").strip()
                        fingerprint = cpf_fingerprint(cpf)
                        keys = (
                            (external_id, office_code, ballot_number, row_uf),
                            (external_id, office_code, ballot_number, normalized_uf or row_uf),
                        )
                        candidacy_ids = set()
                        for key in keys:
                            candidacy_ids.update(candidates.get(key, []))
                        for candidacy_id in candidacy_ids:
                            identity = identities.get(candidacy_id)
                            if identity is None:
                                identity = ElectoralCandidacyOfficialIdentity(
                                    candidacy_id=candidacy_id,
                                    registry_sync_id=sync.id,
                                    cpf_fingerprint=fingerprint,
                                    fingerprint_key_version=key_version,
                                )
                                db.session.add(identity)
                                identities[candidacy_id] = identity
                            else:
                                identity.registry_sync_id = sync.id
                                identity.cpf_fingerprint = fingerprint
                                identity.fingerprint_key_version = key_version
                                identity.synchronized_at = datetime.now(UTC)
                            matched_ids.add(candidacy_id)
        sync.row_count = total
        sync.invalid_rows = invalid
        sync.matched_candidacies = len(matched_ids)
        sync.manifest = {
            "parserVersion": REGISTRY_PARSER_VERSION,
            "generatedAt": generated_at,
            "cpfRows": cpf_rows,
            "cpfAvailable": cpf_rows > 0,
            "cpfPersisted": False,
            "fingerprintAlgorithm": "HMAC-SHA256",
        }
        db.session.commit()
        return sync, False
    except Exception:
        db.session.rollback()
        raise


def reconcile_user_candidacies(tenant_id: uuid.UUID, user_id: uuid.UUID) -> dict:
    user = db.session.get(User, user_id)
    latest_sync = db.session.scalar(
        select(func.max(ElectoralCandidateRegistrySync.synchronized_at))
    )
    if user is None or not user.cpf:
        return _reconciliation_status("cpf_missing", latest_sync, 0)
    fingerprint = cpf_fingerprint(user.cpf)
    key_version = int(current_app.config["ELECTORAL_IDENTITY_HMAC_KEY_VERSION"])
    matched_ids = list(
        db.session.scalars(
            select(ElectoralCandidacyOfficialIdentity.candidacy_id)
            .join(
                ElectoralCandidacy,
                ElectoralCandidacy.id == ElectoralCandidacyOfficialIdentity.candidacy_id,
            )
            .join(
                ElectoralDatasetVersion,
                ElectoralDatasetVersion.id == ElectoralCandidacy.dataset_version_id,
            )
            .where(
                ElectoralCandidacyOfficialIdentity.cpf_fingerprint == fingerprint,
                ElectoralCandidacyOfficialIdentity.fingerprint_key_version == key_version,
                ElectoralDatasetVersion.status == ElectoralDatasetStatus.PUBLISHED,
            )
        )
    )
    existing = {
        item.candidacy_id: item
        for item in db.session.scalars(
            select(ElectoralUserCandidacy).where(
                ElectoralUserCandidacy.tenant_id == tenant_id,
                ElectoralUserCandidacy.user_id == user_id,
            )
        )
    }
    changed = 0
    for candidacy_id in matched_ids:
        item = existing.get(candidacy_id)
        if item is None:
            db.session.add(
                ElectoralUserCandidacy(
                    tenant_id=tenant_id,
                    user_id=user_id,
                    candidacy_id=candidacy_id,
                    method=AUTOMATIC_CPF_METHOD,
                )
            )
            changed += 1
        elif item.method != AUTOMATIC_CPF_METHOD:
            item.method = AUTOMATIC_CPF_METHOD
            item.confirmed_at = datetime.now(UTC)
            changed += 1
    if changed:
        db.session.commit()
    status = "verified" if matched_ids else "not_found"
    if not matched_ids and latest_sync is None:
        status = "official_data_unavailable"
    result = _reconciliation_status(status, latest_sync, len(matched_ids), changed)
    result["manualFallbackAllowed"] = _manual_fallback_available()
    return result


def user_identity_status(user_id: uuid.UUID) -> dict:
    user = db.session.get(User, user_id)
    latest_sync = db.session.scalar(
        select(func.max(ElectoralCandidateRegistrySync.synchronized_at))
    )
    if user is None or not user.cpf:
        return _reconciliation_status("cpf_missing", latest_sync, 0)
    fingerprint = cpf_fingerprint(user.cpf)
    key_version = int(current_app.config["ELECTORAL_IDENTITY_HMAC_KEY_VERSION"])
    matched = db.session.scalar(
        select(func.count())
        .select_from(ElectoralCandidacyOfficialIdentity)
        .join(
            ElectoralCandidacy,
            ElectoralCandidacy.id == ElectoralCandidacyOfficialIdentity.candidacy_id,
        )
        .join(
            ElectoralDatasetVersion,
            ElectoralDatasetVersion.id == ElectoralCandidacy.dataset_version_id,
        )
        .where(
            ElectoralCandidacyOfficialIdentity.cpf_fingerprint == fingerprint,
            ElectoralCandidacyOfficialIdentity.fingerprint_key_version == key_version,
            ElectoralDatasetVersion.status == ElectoralDatasetStatus.PUBLISHED,
        )
    ) or 0
    status = "verified" if matched else "not_found"
    if not matched and latest_sync is None:
        status = "official_data_unavailable"
    result = _reconciliation_status(status, latest_sync, matched)
    result["manualFallbackAllowed"] = _manual_fallback_available()
    return result


def manual_fallback_reason(candidacy_id: uuid.UUID, user_id: uuid.UUID) -> str | None:
    user = db.session.get(User, user_id)
    if user is None or not user.cpf:
        return "cpf_missing"
    official = db.session.scalar(
        select(ElectoralCandidacyOfficialIdentity).where(
            ElectoralCandidacyOfficialIdentity.candidacy_id == candidacy_id
        )
    )
    if official is None:
        return "official_data_unavailable"
    if official.cpf_fingerprint != cpf_fingerprint(user.cpf):
        return "official_data_divergence"
    return None


def _published_candidacy_index(year: int, uf: str | None) -> dict[tuple, list[uuid.UUID]]:
    statement = (
        select(
            ElectoralCandidacy.id,
            ElectoralCandidate.external_id,
            ElectoralOffice.code,
            ElectoralCandidacy.ballot_number,
            ElectoralElection.uf,
        )
        .join(ElectoralCandidate, ElectoralCandidate.id == ElectoralCandidacy.candidate_id)
        .join(ElectoralOffice, ElectoralOffice.id == ElectoralCandidacy.office_id)
        .join(ElectoralElection, ElectoralElection.id == ElectoralCandidacy.election_id)
        .join(
            ElectoralDatasetVersion,
            ElectoralDatasetVersion.id == ElectoralCandidacy.dataset_version_id,
        )
        .where(
            ElectoralElection.year == year,
            ElectoralDatasetVersion.status == ElectoralDatasetStatus.PUBLISHED,
        )
    )
    if uf:
        statement = statement.where(ElectoralElection.uf == uf)
    result: dict[tuple, list[uuid.UUID]] = {}
    rows = db.session.execute(statement)
    for candidacy_id, external_id, office_code, ballot_number, election_uf in rows:
        key = (external_id, office_code, ballot_number, election_uf)
        result.setdefault(key, []).append(candidacy_id)
    return result


def _official_identity_index(
    year: int, uf: str | None
) -> dict[uuid.UUID, ElectoralCandidacyOfficialIdentity]:
    statement = (
        select(ElectoralCandidacyOfficialIdentity)
        .join(
            ElectoralCandidacy,
            ElectoralCandidacy.id == ElectoralCandidacyOfficialIdentity.candidacy_id,
        )
        .join(ElectoralElection, ElectoralElection.id == ElectoralCandidacy.election_id)
        .join(
            ElectoralDatasetVersion,
            ElectoralDatasetVersion.id == ElectoralCandidacy.dataset_version_id,
        )
        .where(
            ElectoralElection.year == year,
            ElectoralDatasetVersion.status == ElectoralDatasetStatus.PUBLISHED,
        )
    )
    if uf:
        statement = statement.where(ElectoralElection.uf == uf)
    return {item.candidacy_id: item for item in db.session.scalars(statement)}


def _manual_fallback_available() -> bool:
    return db.session.scalar(
        select(ElectoralCandidacy.id)
        .join(
            ElectoralDatasetVersion,
            ElectoralDatasetVersion.id == ElectoralCandidacy.dataset_version_id,
        )
        .outerjoin(
            ElectoralCandidacyOfficialIdentity,
            ElectoralCandidacyOfficialIdentity.candidacy_id == ElectoralCandidacy.id,
        )
        .where(
            ElectoralDatasetVersion.status == ElectoralDatasetStatus.PUBLISHED,
            ElectoralCandidacyOfficialIdentity.id.is_(None),
        )
        .limit(1)
    ) is not None


def _reconciliation_status(status: str, latest_sync, matched: int, changed: int = 0) -> dict:
    return {
        "status": status,
        "matchedCandidacies": matched,
        "createdOrUpdated": changed,
        "lastOfficialSyncAt": latest_sync.isoformat() if latest_sync else None,
        "manualFallbackAllowed": status != "verified",
    }


def _cpf_digits(value) -> str:
    return re.sub(r"\D", "", str(value or ""))


def _file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()
