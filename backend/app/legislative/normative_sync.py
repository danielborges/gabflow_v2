import hashlib
import re
import urllib.error
import urllib.parse
import urllib.request
import uuid
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta

from flask import current_app
from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError

from app.extensions import db
from app.models import (
    NormativeCandidateStatus,
    NormativeSource,
    NormativeSourceCandidate,
    NormativeSourceConnector,
    NormativeSourceSyncRun,
)

SUPPORTED_PROVIDERS = {"LEXML"}


class NormativeSyncError(RuntimeError):
    pass


@dataclass(frozen=True)
class ExternalNormativeRecord:
    external_id: str
    source_type: str
    title: str
    reference: str
    excerpt: str
    jurisdiction: str | None
    source_url: str | None
    version: str
    valid_from: date | None = None
    valid_until: date | None = None

    @property
    def checksum(self) -> str:
        return hashlib.sha256(self.excerpt.encode("utf-8")).hexdigest()


def connector_values(payload: dict) -> dict:
    provider = str(payload.get("provedor", "LEXML")).strip().upper()
    name = str(payload.get("nome", "")).strip()
    search_query = str(payload.get("consulta", "")).strip()
    jurisdiction = str(payload.get("jurisdicao", "")).strip() or None
    try:
        frequency = int(payload.get("frequenciaHoras", 24))
    except (TypeError, ValueError) as error:
        raise ValueError("Frequência de sincronização inválida.") from error
    if provider not in SUPPORTED_PROVIDERS:
        raise ValueError("Provedor normativo não suportado.")
    if not name or len(name) > 160:
        raise ValueError("Informe um nome válido para a integração.")
    if len(search_query) < 3 or len(search_query) > 500:
        raise ValueError("A consulta deve possuir entre 3 e 500 caracteres.")
    if jurisdiction and len(jurisdiction) > 120:
        raise ValueError("Jurisdição inválida.")
    if frequency not in {6, 12, 24, 48, 168}:
        raise ValueError("Use uma frequência de 6, 12, 24, 48 ou 168 horas.")
    return {
        "provider": provider,
        "name": name,
        "search_query": search_query,
        "jurisdiction": jurisdiction,
        "sync_frequency_hours": frequency,
        "enabled": bool(payload.get("ativa", True)),
    }


def connector_data(item: NormativeSourceConnector) -> dict:
    pending = db.session.scalar(
        select(db.func.count(NormativeSourceCandidate.id)).where(
            NormativeSourceCandidate.connector_id == item.id,
            NormativeSourceCandidate.status == NormativeCandidateStatus.PENDENTE,
        )
    )
    return {
        "id": str(item.id),
        "provedor": item.provider,
        "nome": item.name,
        "consulta": item.search_query,
        "jurisdicao": item.jurisdiction,
        "frequenciaHoras": item.sync_frequency_hours,
        "ativa": item.enabled,
        "proximaSincronizacaoEm": item.next_sync_at.isoformat() if item.next_sync_at else None,
        "ultimaSincronizacaoEm": item.last_sync_at.isoformat() if item.last_sync_at else None,
        "ultimoStatus": item.last_status,
        "ultimoErro": item.last_error,
        "pendentes": pending or 0,
    }


def candidate_data(item: NormativeSourceCandidate) -> dict:
    connector = db.session.get(NormativeSourceConnector, item.connector_id)
    return {
        "id": str(item.id),
        "integracaoId": str(item.connector_id),
        "integracao": connector.name if connector else None,
        "provedor": connector.provider if connector else None,
        "status": item.status.value,
        "idExterno": item.external_id,
        "tipo": item.source_type,
        "titulo": item.title,
        "referencia": item.reference,
        "trecho": item.excerpt,
        "jurisdicao": item.jurisdiction,
        "url": item.source_url,
        "versao": item.version,
        "checksum": item.checksum,
        "vigenteDesde": item.valid_from.isoformat() if item.valid_from else None,
        "vigenteAte": item.valid_until.isoformat() if item.valid_until else None,
        "fonteExistenteId": str(item.existing_source_id) if item.existing_source_id else None,
        "motivoRevisao": item.review_reason,
        "revisadaEm": item.reviewed_at.isoformat() if item.reviewed_at else None,
        "descobertaEm": item.created_at.isoformat(),
    }


def sync_run_data(item: NormativeSourceSyncRun) -> dict:
    return {
        "id": str(item.id),
        "status": item.status,
        "descobertas": item.discovered_count,
        "novosCandidatos": item.candidate_count,
        "semAlteracao": item.unchanged_count,
        "erro": item.error,
        "iniciadaEm": item.started_at.isoformat(),
        "concluidaEm": item.completed_at.isoformat() if item.completed_at else None,
    }


def synchronize_connector(
    connector: NormativeSourceConnector, *, commit: bool = True
) -> NormativeSourceSyncRun:
    now = datetime.now(UTC)
    run = NormativeSourceSyncRun(
        tenant_id=connector.tenant_id,
        connector_id=connector.id,
        status="PROCESSANDO",
    )
    db.session.add(run)
    db.session.flush()
    try:
        records = _fetch_records(connector)
        run.discovered_count = len(records)
        for record in records:
            if _stage_record(connector, run, record):
                run.candidate_count += 1
            else:
                run.unchanged_count += 1
        run.status = "CONCLUIDA"
        connector.last_status = "CONCLUIDA"
        connector.last_error = None
    except NormativeSyncError as error:
        run.status = "FALHOU"
        run.error = str(error)[:1000]
        connector.last_status = "FALHOU"
        connector.last_error = str(error)[:1000]
    run.completed_at = datetime.now(UTC)
    connector.last_sync_at = now
    connector.next_sync_at = now + timedelta(hours=connector.sync_frequency_hours)
    if commit:
        db.session.commit()
    else:
        db.session.flush()
    return run


def sync_due_connectors(tenant_id: uuid.UUID) -> int:
    now = datetime.now(UTC)
    connectors = list(
        db.session.scalars(
            select(NormativeSourceConnector).where(
                NormativeSourceConnector.tenant_id == tenant_id,
                NormativeSourceConnector.enabled.is_(True),
                or_(
                    NormativeSourceConnector.next_sync_at.is_(None),
                    NormativeSourceConnector.next_sync_at <= now,
                ),
            )
        )
    )
    for connector in connectors:
        synchronize_connector(connector)
    return len(connectors)


def review_candidate(
    candidate: NormativeSourceCandidate,
    reviewer_id: uuid.UUID,
    *,
    approve: bool,
    reason: str,
) -> NormativeSource | None:
    if candidate.status != NormativeCandidateStatus.PENDENTE:
        raise ValueError("Esta atualização já foi revisada.")
    reason = reason.strip()
    if len(reason) < 5 or len(reason) > 500:
        raise ValueError("Informe um motivo de 5 a 500 caracteres.")
    candidate.review_reason = reason
    candidate.reviewed_by_id = reviewer_id
    candidate.reviewed_at = datetime.now(UTC)
    if not approve:
        candidate.status = NormativeCandidateStatus.REJEITADA
        db.session.flush()
        return None

    connector = db.session.get(NormativeSourceConnector, candidate.connector_id)
    if connector is None or connector.tenant_id != candidate.tenant_id:
        raise ValueError("A integração de origem não está disponível.")
    existing = None
    if candidate.existing_source_id:
        existing = db.session.get(NormativeSource, candidate.existing_source_id)
    if existing and existing.checksum == candidate.checksum:
        raise ValueError("O conteúdo já corresponde à versão publicada.")
    if existing:
        existing.active = False
    version = candidate.version
    if db.session.scalar(
        select(NormativeSource.id).where(
            NormativeSource.tenant_id == candidate.tenant_id,
            NormativeSource.title == candidate.title,
            NormativeSource.reference == candidate.reference,
            NormativeSource.version == version,
        )
    ):
        version = f"{version}-{candidate.checksum[:8]}"[:80]
    source = NormativeSource(
        tenant_id=candidate.tenant_id,
        source_type=candidate.source_type,
        title=candidate.title,
        reference=candidate.reference,
        excerpt=candidate.excerpt,
        jurisdiction=candidate.jurisdiction,
        source_url=candidate.source_url,
        official_source_url=candidate.source_url,
        version=version,
        checksum=candidate.checksum,
        valid_from=candidate.valid_from,
        valid_until=candidate.valid_until,
        active=True,
        origin="SINCRONIZADA",
        provider=connector.provider,
        external_id=candidate.external_id,
        imported_at=candidate.created_at,
        reviewed_by_id=reviewer_id,
        reviewed_at=candidate.reviewed_at,
        supersedes_source_id=existing.id if existing else None,
        created_by_id=reviewer_id,
    )
    db.session.add(source)
    candidate.status = NormativeCandidateStatus.APROVADA
    db.session.flush()
    return source


def _stage_record(
    connector: NormativeSourceConnector,
    run: NormativeSourceSyncRun,
    record: ExternalNormativeRecord,
) -> bool:
    existing = db.session.scalar(
        select(NormativeSource).where(
            NormativeSource.tenant_id == connector.tenant_id,
            NormativeSource.provider == connector.provider,
            NormativeSource.external_id == record.external_id,
            NormativeSource.active.is_(True),
        )
    )
    if existing and existing.checksum == record.checksum:
        return False
    duplicate = db.session.scalar(
        select(NormativeSourceCandidate.id).where(
            NormativeSourceCandidate.connector_id == connector.id,
            NormativeSourceCandidate.external_id == record.external_id,
            NormativeSourceCandidate.checksum == record.checksum,
        )
    )
    if duplicate:
        return False
    candidate = NormativeSourceCandidate(
            tenant_id=connector.tenant_id,
            connector_id=connector.id,
            sync_run_id=run.id,
            external_id=record.external_id,
            source_type=record.source_type,
            title=record.title,
            reference=record.reference,
            excerpt=record.excerpt,
            jurisdiction=record.jurisdiction or connector.jurisdiction,
            source_url=record.source_url,
            version=record.version,
            checksum=record.checksum,
            valid_from=record.valid_from,
            valid_until=record.valid_until,
            existing_source_id=existing.id if existing else None,
        )
    try:
        with db.session.begin_nested():
            db.session.add(candidate)
            db.session.flush()
    except IntegrityError:
        return False
    return True


def _fetch_records(connector: NormativeSourceConnector) -> list[ExternalNormativeRecord]:
    if connector.provider != "LEXML":
        raise NormativeSyncError("Provedor normativo não suportado.")
    params = urllib.parse.urlencode(
        {
            "operation": "searchRetrieve",
            "version": "1.1",
            "query": connector.search_query,
            "maximumRecords": min(current_app.config["NORMATIVE_SYNC_MAX_RECORDS"], 100),
            "recordSchema": "dc",
        }
    )
    base_url = current_app.config["NORMATIVE_LEXML_BASE_URL"]
    parsed_base = urllib.parse.urlsplit(base_url)
    if parsed_base.scheme != "https" or not parsed_base.hostname:
        raise NormativeSyncError("A URL configurada para a fonte oficial não é segura.")
    url = f"{base_url}?{params}"
    request = urllib.request.Request(  # noqa: S310 - URL HTTPS validada acima
        url,
        headers={"Accept": "application/xml", "User-Agent": "GabFlow-NormativeSync/1.0"},
    )
    try:
        with urllib.request.urlopen(  # noqa: S310 - URL HTTPS validada acima
            request, timeout=current_app.config["NORMATIVE_SYNC_TIMEOUT_SECONDS"]
        ) as response:
            payload = response.read(5_000_000)
    except (urllib.error.URLError, TimeoutError, OSError) as error:
        raise NormativeSyncError("A fonte oficial está temporariamente indisponível.") from error
    try:
        if b"<!DOCTYPE" in payload.upper() or b"<!ENTITY" in payload.upper():
            raise NormativeSyncError("A fonte oficial retornou XML não permitido.")
        root = ET.fromstring(payload)  # noqa: S314 - DTD e entidades são rejeitados acima
    except ET.ParseError as error:
        raise NormativeSyncError("A fonte oficial retornou um documento inválido.") from error
    return _parse_lexml(root, connector.jurisdiction)


def _parse_lexml(root: ET.Element, jurisdiction: str | None) -> list[ExternalNormativeRecord]:
    records: list[ExternalNormativeRecord] = []
    for node in root.iter():
        if _local_name(node.tag) != "recordData":
            continue
        fields: dict[str, list[str]] = {}
        for child in node.iter():
            text = " ".join((child.text or "").split())
            if text:
                fields.setdefault(_local_name(child.tag).lower(), []).append(text)
        title = _first(fields, "title")
        external_id = _first(fields, "identifier")
        excerpt = _first(fields, "description", "abstract", "subject")
        if not title or not external_id or len(excerpt) < 20:
            continue
        url = next(
            (value for value in fields.get("identifier", []) if value.startswith(("http://", "https://"))),
            None,
        )
        reference = _reference(title, external_id)
        published = _parse_date(_first(fields, "date"))
        records.append(
            ExternalNormativeRecord(
                external_id=external_id[:500],
                source_type=_source_type(" ".join(fields.get("type", [])), title),
                title=title[:240],
                reference=reference[:240],
                excerpt=excerpt[:20000],
                jurisdiction=jurisdiction,
                source_url=(
                    url
                    or (
                        external_id
                        if external_id.startswith(("http://", "https://"))
                        else None
                    )
                ),
                version=(
                    published.isoformat()
                    if published
                    else hashlib.sha256(excerpt.encode()).hexdigest()[:12]
                ),
                valid_from=published,
            )
        )
    return records


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1].rsplit(":", 1)[-1]


def _first(fields: dict[str, list[str]], *names: str) -> str:
    for name in names:
        if fields.get(name):
            return fields[name][0]
    return ""


def _reference(title: str, external_id: str) -> str:
    match = re.search(
        r"\b(?:lei|decreto|resolu[cç][aã]o|portaria)\s+"
        r"(?:n[º°o.]\s*)?[\d.]+(?:/\d{4})?",
        title,
        re.I,
    )
    return (match.group(0) if match else external_id)[:240]


def _source_type(type_text: str, title: str) -> str:
    value = f"{type_text} {title}".lower()
    if "lei orgânica" in value:
        return "LEI_ORGANICA"
    if "regimento" in value:
        return "REGIMENTO_INTERNO"
    if "decreto" in value:
        return "DECRETO"
    if "plano diretor" in value:
        return "PLANO_DIRETOR"
    if "lei" in value:
        return "LEI_MUNICIPAL"
    return "OUTRO"


def _parse_date(value: str) -> date | None:
    match = re.search(r"\d{4}-\d{2}-\d{2}", value)
    if not match:
        return None
    try:
        return date.fromisoformat(match.group(0))
    except ValueError:
        return None
