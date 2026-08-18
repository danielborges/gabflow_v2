import hashlib
import json
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

SUPPORTED_PROVIDERS = {"LEXML", "SENADO"}
SENADO_FILTERS = {
    "ano",
    "complemento",
    "data",
    "ident",
    "numero",
    "reedicao",
    "seq",
    "tipo",
}
SENADO_NUMERIC_FILTERS = {"ano", "numero", "reedicao", "seq"}


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
    if provider == "SENADO":
        _senado_query_params(search_query)
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
        "message": item.error if item.status == "FALHOU" else None,
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
    connector.next_sync_at = (
        _next_failure_retry_at(connector, now)
        if run.status == "FALHOU"
        else now + timedelta(hours=connector.sync_frequency_hours)
    )
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
    if connector.provider == "LEXML":
        return _fetch_lexml_records(connector)
    if connector.provider == "SENADO":
        return _fetch_senado_records(connector)
    raise NormativeSyncError("Provedor normativo não suportado.")


def _fetch_lexml_records(
    connector: NormativeSourceConnector,
) -> list[ExternalNormativeRecord]:
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
            content_type = str(response.headers.get("Content-Type", "")).lower()
            payload = response.read(5_000_000)
    except (urllib.error.URLError, TimeoutError, OSError) as error:
        raise NormativeSyncError("A fonte oficial está temporariamente indisponível.") from error
    try:
        if "text/html" in content_type or _is_senado_security_challenge(payload):
            raise NormativeSyncError(
                "O LexML apresentou uma verificação de segurança incompatível com "
                "integração automática. Use o provedor Dados Abertos do Senado enquanto "
                "o acesso SRU não estiver liberado para serviço máquina-a-máquina."
            )
        if b"<!DOCTYPE" in payload.upper() or b"<!ENTITY" in payload.upper():
            raise NormativeSyncError("A fonte oficial retornou XML não permitido.")
        root = ET.fromstring(payload)  # noqa: S314 - DTD e entidades são rejeitados acima
    except ET.ParseError as error:
        raise NormativeSyncError("A fonte oficial retornou um documento inválido.") from error
    return _parse_lexml(root, connector.jurisdiction)


def _fetch_senado_records(
    connector: NormativeSourceConnector,
) -> list[ExternalNormativeRecord]:
    params = urllib.parse.urlencode(_senado_query_params(connector.search_query))
    base_url = current_app.config["NORMATIVE_SENADO_BASE_URL"]
    parsed_base = urllib.parse.urlsplit(base_url)
    if parsed_base.scheme != "https" or parsed_base.hostname != "legis.senado.leg.br":
        raise NormativeSyncError("A URL configurada para os Dados Abertos não é segura.")
    url = f"{base_url}?{params}"
    request = urllib.request.Request(  # noqa: S310 - host oficial validado acima
        url,
        headers={
            "Accept": "application/json",
            "User-Agent": "GabFlow-NormativeSync/1.0",
        },
    )
    try:
        with urllib.request.urlopen(  # noqa: S310 - host oficial validado acima
            request, timeout=current_app.config["NORMATIVE_SYNC_TIMEOUT_SECONDS"]
        ) as response:
            content_type = str(response.headers.get("Content-Type", "")).lower()
            payload = response.read(5_000_001)
    except urllib.error.HTTPError as error:
        if error.code == 429:
            raise NormativeSyncError(
                "O Senado limitou temporariamente as requisições. Nova tentativa será agendada."
            ) from error
        if error.code == 503:
            raise NormativeSyncError(
                "Os Dados Abertos do Senado estão temporariamente indisponíveis."
            ) from error
        raise NormativeSyncError(
            f"Os Dados Abertos do Senado retornaram HTTP {error.code}."
        ) from error
    except (urllib.error.URLError, TimeoutError, OSError) as error:
        raise NormativeSyncError(
            "Os Dados Abertos do Senado estão temporariamente indisponíveis."
        ) from error
    if len(payload) > 5_000_000:
        raise NormativeSyncError("A resposta dos Dados Abertos excedeu o limite seguro.")
    if "application/json" not in content_type:
        raise NormativeSyncError("Os Dados Abertos do Senado retornaram formato inesperado.")
    try:
        data = json.loads(payload)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise NormativeSyncError(
            "Os Dados Abertos do Senado retornaram documento inválido."
        ) from error
    return _parse_senado(
        data,
        limit=min(current_app.config["NORMATIVE_SYNC_MAX_RECORDS"], 100),
    )


def _senado_query_params(search_query: str) -> dict[str, str]:
    try:
        pairs = urllib.parse.parse_qsl(
            search_query,
            keep_blank_values=True,
            strict_parsing=True,
            max_num_fields=10,
        )
    except ValueError as error:
        raise ValueError(
            "Use filtros do Senado no formato tipo=LEI&ano=2026."
        ) from error
    if not pairs or len({key for key, _ in pairs}) != len(pairs):
        raise ValueError("Informe filtros únicos para a consulta do Senado.")
    params = {key: value.strip() for key, value in pairs}
    if not set(params).issubset(SENADO_FILTERS) or any(not value for value in params.values()):
        raise ValueError(
            "A consulta contém filtros não aceitos pelos Dados Abertos do Senado."
        )
    if any(not params[key].isdigit() for key in set(params) & SENADO_NUMERIC_FILTERS):
        raise ValueError("Ano, número, sequência e reedição devem ser numéricos.")
    if not ({"tipo", "numero", "ano", "data"} & set(params)):
        raise ValueError("Informe ao menos tipo, número, ano ou data na consulta do Senado.")
    return params


def _parse_senado(data: dict, *, limit: int) -> list[ExternalNormativeRecord]:
    documents = (
        data.get("ListaDocumento", {}).get("documentos", {}).get("documento", [])
    )
    if isinstance(documents, dict):
        documents = [documents]
    if not isinstance(documents, list):
        raise NormativeSyncError("Os Dados Abertos do Senado mudaram o formato da resposta.")
    records: list[ExternalNormativeRecord] = []
    for document in documents:
        if not isinstance(document, dict):
            continue
        identifier = str(document.get("id", "")).strip()
        title = str(document.get("normaNome", "")).strip()
        excerpt = " ".join(str(document.get("ementa", "")).split())
        reference = str(document.get("norma", "")).strip() or title
        if not identifier or not title or len(excerpt) < 20:
            continue
        published = _parse_brazilian_date(str(document.get("dataassinatura", "")))
        records.append(
            ExternalNormativeRecord(
                external_id=f"senado:{identifier}",
                source_type=_senado_source_type(
                    str(document.get("tipo", "")),
                    str(document.get("descricao", "")),
                    title,
                ),
                title=title[:240],
                reference=reference[:240],
                excerpt=excerpt[:20000],
                jurisdiction="Federal",
                source_url=f"https://legis.senado.leg.br/norma/{identifier}",
                version=(
                    published.isoformat()
                    if published
                    else hashlib.sha256(excerpt.encode()).hexdigest()[:12]
                ),
                valid_from=published,
            )
        )
        if len(records) >= limit:
            break
    return records


def _is_senado_security_challenge(payload: bytes) -> bool:
    lowered = payload[:100_000].lower()
    return b"verifica" in lowered and b"seguran" in lowered and b"senado federal" in lowered


def _next_failure_retry_at(
    connector: NormativeSourceConnector, now: datetime
) -> datetime:
    recent_statuses = list(
        db.session.scalars(
            select(NormativeSourceSyncRun.status)
            .where(NormativeSourceSyncRun.connector_id == connector.id)
            .order_by(NormativeSourceSyncRun.started_at.desc())
            .limit(10)
        )
    )
    consecutive_failures = 0
    for status in recent_statuses:
        if status != "FALHOU":
            break
        consecutive_failures += 1
    base = max(current_app.config["NORMATIVE_SYNC_FAILURE_RETRY_BASE_MINUTES"], 1)
    maximum = max(current_app.config["NORMATIVE_SYNC_FAILURE_RETRY_MAX_MINUTES"], base)
    delay = min(base * (2 ** max(consecutive_failures - 1, 0)), maximum)
    delay = min(delay, connector.sync_frequency_hours * 60)
    return now + timedelta(minutes=delay)


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


def _senado_source_type(type_text: str, description: str, title: str) -> str:
    value = f"{type_text} {description} {title}".lower()
    if "constitui" in value:
        return "CONSTITUICAO"
    if "decreto" in value:
        return "DECRETO"
    if "lei" in value:
        return "LEI_FEDERAL"
    return "OUTRO"


def _parse_date(value: str) -> date | None:
    match = re.search(r"\d{4}-\d{2}-\d{2}", value)
    if not match:
        return None
    try:
        return date.fromisoformat(match.group(0))
    except ValueError:
        return None


def _parse_brazilian_date(value: str) -> date | None:
    match = re.fullmatch(r"(\d{2})/(\d{2})/(\d{4})", value.strip())
    if not match:
        return None
    try:
        return date(int(match.group(3)), int(match.group(2)), int(match.group(1)))
    except ValueError:
        return None
