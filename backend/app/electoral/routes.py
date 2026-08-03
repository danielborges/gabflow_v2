import io
import uuid
from datetime import UTC, date, datetime, timedelta

from flask import Blueprint, current_app, g, jsonify, request, send_file
from flask_jwt_extended import get_jwt, get_jwt_identity
from sqlalchemy import func, select

from app.audit import add_audit
from app.electoral.access import electoral_access_required
from app.electoral.analytics import (
    AVAILABLE_LEVELS,
    COMPARISON_MAX_CANDIDATES,
    COMPARISON_MIN_CANDIDATES,
)
from app.electoral.analytics import (
    candidate_history as load_candidate_history,
)
from app.electoral.analytics import (
    candidate_map as load_candidate_map,
)
from app.electoral.analytics import (
    candidate_results as load_candidate_results,
)
from app.electoral.analytics import (
    compare_candidates as load_candidate_comparison,
)
from app.electoral.analytics import (
    search_candidates as load_candidate_search,
)
from app.electoral.mandate_intelligence import (
    MandateIntelligenceError,
    active_profile,
    create_profile,
    ensure_default_profile,
    generate_snapshot,
    profile_data,
    snapshot_data,
)
from app.electoral.reports import (
    REPORT_EVENT,
    NonRetryableReportError,
    report_bytes,
    signed_report_token,
    verify_report_token,
)
from app.extensions import db
from app.models import (
    ElectoralAccessDelegation,
    ElectoralCandidacy,
    ElectoralCandidate,
    ElectoralDatasetStatus,
    ElectoralDatasetVersion,
    ElectoralElection,
    ElectoralFavorite,
    ElectoralGeneratedReport,
    ElectoralIdentityReview,
    ElectoralMandateSnapshot,
    ElectoralModuleSettings,
    ElectoralOffice,
    ElectoralReportJob,
    ElectoralSavedComparison,
    OutboxEvent,
    Role,
    User,
    UserStatus,
)

electoral_bp = Blueprint("electoral", __name__)

DEFAULT_FEATURE_FLAGS = {
    "catalogo": True,
    "exportacoes": False,
    "camadasMandato": False,
    "ia": False,
    "cenarios": False,
    "delegacao": False,
}


@electoral_bp.get("/electoral/disponibilidade")
@electoral_access_required("consultar_dados_publicos")
def availability():
    tenant_id = uuid.UUID(get_jwt()["tenant_id"])
    user_id = uuid.UUID(get_jwt_identity())
    settings = db.session.get(ElectoralModuleSettings, tenant_id)
    flags = {**DEFAULT_FEATURE_FLAGS, **(settings.feature_flags if settings else {})}
    mandate = g.electoral_mandate
    add_audit(
        tenant_id,
        user_id,
        "electoral.access.granted",
        "mandate",
        mandate.id,
        after={"capability": "consultar_dados_publicos"},
    )
    db.session.commit()
    return jsonify(
        disponivel=True,
        modulo="inteligencia_eleitoral",
        mandato={
            "id": str(mandate.id),
            "cargo": mandate.office,
            "jurisdicao": mandate.jurisdiction,
            "status": mandate.status.value,
        },
        capacidades=g.electoral_capabilities,
        limiarPrivacidade=settings.privacy_threshold if settings else 10,
        funcionalidades=flags,
    )


@electoral_bp.get("/electoral/elections")
@electoral_access_required("consultar_dados_publicos")
def list_elections():
    page = max(1, request.args.get("page", 1, type=int))
    per_page = min(100, max(1, request.args.get("perPage", 20, type=int)))
    filters = [ElectoralDatasetVersion.status == ElectoralDatasetStatus.PUBLISHED]
    if year := request.args.get("year", type=int):
        filters.append(ElectoralElection.year == year)
    if scope := request.args.get("scope", type=str):
        filters.append(ElectoralElection.scope == scope.lower())
    if uf := request.args.get("uf", type=str):
        filters.append(ElectoralElection.uf == uf.upper())
    statement = (
        select(ElectoralElection, ElectoralDatasetVersion)
        .join(
            ElectoralDatasetVersion,
            ElectoralDatasetVersion.id == ElectoralElection.dataset_version_id,
        )
        .where(*filters)
    )
    total = db.session.scalar(select(func.count()).select_from(statement.subquery())) or 0
    rows = db.session.execute(
        statement.order_by(
            ElectoralElection.year.desc(),
            ElectoralElection.round,
            ElectoralElection.name,
        )
        .offset((page - 1) * per_page)
        .limit(per_page)
    ).all()
    _audit_catalog("electoral.catalog.elections_viewed", {"page": page, "year": year})
    return jsonify(
        items=[_election_data(election, dataset) for election, dataset in rows],
        page=page,
        perPage=per_page,
        total=total,
    )


@electoral_bp.get("/electoral/offices")
@electoral_access_required("consultar_dados_publicos")
def list_offices():
    items = db.session.execute(
        select(ElectoralOffice)
        .join(ElectoralCandidacy, ElectoralCandidacy.office_id == ElectoralOffice.id)
        .join(
            ElectoralDatasetVersion,
            ElectoralDatasetVersion.id == ElectoralCandidacy.dataset_version_id,
        )
        .where(ElectoralDatasetVersion.status == ElectoralDatasetStatus.PUBLISHED)
        .distinct()
        .order_by(ElectoralOffice.name)
    ).scalars()
    _audit_catalog("electoral.catalog.offices_viewed")
    return jsonify(
        content=[{"id": str(item.id), "codigo": item.code, "nome": item.name} for item in items]
    )


@electoral_bp.get("/electoral/datasets")
@electoral_access_required("consultar_dados_publicos")
def list_dataset_versions():
    items = db.session.execute(
        select(ElectoralDatasetVersion)
        .where(
            ElectoralDatasetVersion.status.in_(
                [ElectoralDatasetStatus.PUBLISHED, ElectoralDatasetStatus.SUPERSEDED]
            )
        )
        .order_by(
            ElectoralDatasetVersion.election_year.desc(),
            ElectoralDatasetVersion.published_at.desc(),
        )
    ).scalars()
    _audit_catalog("electoral.catalog.datasets_viewed")
    return jsonify(content=[_dataset_data(item) for item in items])


@electoral_bp.get("/electoral/coverage")
@electoral_access_required("consultar_dados_publicos")
def catalog_coverage():
    items = db.session.execute(
        select(ElectoralDatasetVersion)
        .where(ElectoralDatasetVersion.status == ElectoralDatasetStatus.PUBLISHED)
        .order_by(ElectoralDatasetVersion.election_year.desc(), ElectoralDatasetVersion.uf)
    ).scalars()
    content = [
        {
            "ano": item.election_year,
            "escopo": item.election_scope,
            "uf": item.uf,
            "cargoCodigo": item.office_code,
            "linhas": item.row_count,
            "votos": item.total_votes,
            "qualidade": item.quality_score,
            "datasetVersionId": str(item.id),
        }
        for item in items
    ]
    _audit_catalog("electoral.catalog.coverage_viewed")
    return jsonify(content=content, total=len(content))


@electoral_bp.get("/electoral/quality")
@electoral_access_required("consultar_dados_publicos")
def catalog_quality():
    items = list(
        db.session.execute(
            select(ElectoralDatasetVersion)
            .where(ElectoralDatasetVersion.status == ElectoralDatasetStatus.PUBLISHED)
            .order_by(ElectoralDatasetVersion.election_year.desc())
        ).scalars()
    )
    average = (
        round(sum(item.quality_score or 0 for item in items) / len(items), 4) if items else None
    )
    _audit_catalog("electoral.catalog.quality_viewed")
    return jsonify(
        datasets=len(items),
        qualidadeMedia=average,
        divergencias=sum(
            item.validation_manifest.get("totalizationConsistent") is False for item in items
        ),
        content=[_dataset_data(item) for item in items],
    )


@electoral_bp.get("/electoral/coverage-profile")
@electoral_access_required("ver_camadas_mandato")
def get_coverage_profile():
    if disabled := _feature_required("camadasMandato"):
        return disabled
    tenant_id, user_id = _private_context()
    profile = active_profile(tenant_id, g.electoral_mandate.id)
    if profile is None:
        profile = ensure_default_profile(tenant_id, g.electoral_mandate.id, user_id)
        db.session.commit()
    return jsonify(profile_data(profile))


@electoral_bp.post("/electoral/coverage-profile")
@electoral_access_required("ver_camadas_mandato")
def update_coverage_profile():
    if disabled := _feature_required("camadasMandato"):
        return disabled
    if get_jwt().get("role") != Role.REPRESENTATIVE.value:
        return (
            jsonify(
                error="representative_required",
                message="Somente o parlamentar configura o ICT.",
            ),
            403,
        )
    tenant_id, user_id = _private_context()
    try:
        profile = create_profile(
            tenant_id, g.electoral_mandate.id, user_id, request.get_json(silent=True) or {}
        )
    except MandateIntelligenceError as exc:
        return _validation_error(str(exc))
    add_audit(
        tenant_id,
        user_id,
        "electoral.coverage_profile.versioned",
        "electoral_coverage_profile",
        profile.id,
        after={"version": profile.version, "formula": profile.formula_code},
    )
    db.session.commit()
    return jsonify(profile_data(profile)), 201


@electoral_bp.get("/electoral/mandate-snapshots")
@electoral_access_required("ver_camadas_mandato")
def list_mandate_snapshots():
    if disabled := _feature_required("camadasMandato"):
        return disabled
    tenant_id, _ = _private_context()
    limit = min(50, max(1, request.args.get("limit", 20, type=int)))
    items = list(db.session.execute(
        select(ElectoralMandateSnapshot)
        .where(
            ElectoralMandateSnapshot.tenant_id == tenant_id,
            ElectoralMandateSnapshot.mandate_id == g.electoral_mandate.id,
        )
        .order_by(ElectoralMandateSnapshot.created_at.desc())
        .limit(limit)
    ).scalars())
    return jsonify(content=[snapshot_data(item) for item in items])


@electoral_bp.post("/electoral/mandate-snapshots")
@electoral_access_required("ver_camadas_mandato")
def create_mandate_snapshot():
    if disabled := _feature_required("camadasMandato"):
        return disabled
    body = request.get_json(silent=True) or {}
    try:
        period_end = date.fromisoformat(str(body.get("period_end") or date.today()))
        period_start = date.fromisoformat(
            str(body.get("period_start") or (period_end - timedelta(days=89)))
        )
        election_id = uuid.UUID(body["election_id"]) if body.get("election_id") else None
        candidate_id = uuid.UUID(body["candidate_id"]) if body.get("candidate_id") else None
    except (ValueError, TypeError):
        return _validation_error("Datas ou identificadores inválidos.")
    tenant_id, user_id = _private_context()
    try:
        snapshot = generate_snapshot(
            tenant_id,
            g.electoral_mandate.id,
            user_id,
            period_start,
            period_end,
            election_id=election_id,
            candidate_id=candidate_id,
        )
    except MandateIntelligenceError as exc:
        return _validation_error(str(exc))
    add_audit(
        tenant_id,
        user_id,
        "electoral.mandate_snapshot.created",
        "electoral_mandate_snapshot",
        snapshot.id,
        after={
            "period_start": period_start.isoformat(),
            "period_end": period_end.isoformat(),
            "privacy_threshold": snapshot.privacy_threshold,
            "config_hash": snapshot.config_hash,
        },
    )
    db.session.commit()
    return jsonify(snapshot_data(snapshot)), 201


@electoral_bp.get("/electoral/mandate-snapshots/<uuid:snapshot_id>")
@electoral_access_required("ver_camadas_mandato")
def get_mandate_snapshot(snapshot_id):
    if disabled := _feature_required("camadasMandato"):
        return disabled
    tenant_id, _ = _private_context()
    item = db.session.execute(
        select(ElectoralMandateSnapshot).where(
            ElectoralMandateSnapshot.id == snapshot_id,
            ElectoralMandateSnapshot.tenant_id == tenant_id,
            ElectoralMandateSnapshot.mandate_id == g.electoral_mandate.id,
        )
    ).scalar_one_or_none()
    if item is None:
        return jsonify(error="not_found", message="Snapshot territorial não encontrado."), 404
    return jsonify(snapshot_data(item))


@electoral_bp.get("/electoral/candidates")
@electoral_access_required("consultar_dados_publicos")
def search_candidates():
    election_id = _uuid_argument("election_id", required=True)
    if isinstance(election_id, tuple):
        return election_id
    query = (request.args.get("q") or "").strip()
    if len(query) < 2 or len(query) > 120:
        return _validation_error("q deve possuir entre 2 e 120 caracteres.")
    page = max(1, request.args.get("page", 1, type=int))
    per_page = min(100, max(1, request.args.get("perPage", 20, type=int)))
    party = (request.args.get("party") or "").strip() or None
    office = (request.args.get("office") or "").strip() or None
    content = load_candidate_search(
        election_id,
        query,
        party=party,
        office=office,
        page=page,
        per_page=per_page,
    )
    _audit_catalog(
        "electoral.catalog.candidates_searched",
        {
            "electionId": str(election_id),
            "queryLength": len(query),
            "party": party,
            "office": office,
            "page": page,
        },
    )
    return jsonify(content)


@electoral_bp.get("/electoral/candidates/<uuid:candidate_id>/results")
@electoral_access_required("consultar_dados_publicos")
def candidate_results(candidate_id):
    election_id = _uuid_argument("election_id", required=True)
    if isinstance(election_id, tuple):
        return election_id
    level = (request.args.get("level") or "").strip().lower()
    if level not in AVAILABLE_LEVELS:
        return _validation_error(
            "Nivel territorial indisponivel.",
            availableLevels=list(AVAILABLE_LEVELS),
        )
    parent_id = _uuid_argument("parent_territory_id")
    if isinstance(parent_id, tuple):
        return parent_id
    municipality_code = (request.args.get("municipalityCode") or "").strip() or None
    page = max(1, request.args.get("page", 1, type=int))
    per_page = min(100, max(1, request.args.get("perPage", 50, type=int)))
    sort = (request.args.get("sort") or "votes").lower()
    order = (request.args.get("order") or "desc").lower()
    if sort not in {"name", "rank", "share", "votes"} or order not in {"asc", "desc"}:
        return _validation_error("Ordenacao territorial invalida.")
    content = load_candidate_results(
        candidate_id,
        election_id,
        level,
        municipality_code=municipality_code,
        parent_territory_id=parent_id,
        page=page,
        per_page=per_page,
        sort=sort,
        order=order,
    )
    if content is None:
        return jsonify(error="not_found", message="Candidatura ou territorio nao encontrado."), 404
    _audit_catalog(
        "electoral.catalog.candidate_results_viewed",
        {
            "candidateId": str(candidate_id),
            "electionId": str(election_id),
            "level": level,
            "municipalityCode": municipality_code,
            "page": page,
        },
    )
    return jsonify(content)


@electoral_bp.get("/electoral/candidates/<uuid:candidate_id>/history")
@electoral_access_required("comparar_candidatos")
def candidate_history(candidate_id):
    municipality_code = (request.args.get("municipalityCode") or "").strip() or None
    tenant_id, user_id = _private_context()
    content = load_candidate_history(
        candidate_id,
        municipality_code=municipality_code,
        tenant_id=tenant_id,
        user_id=user_id,
    )
    if content is None:
        return jsonify(error="not_found", message="Candidatura nao encontrada."), 404
    _audit_catalog(
        "electoral.analysis.candidate_history_viewed",
        {"candidateId": str(candidate_id), "municipalityCode": municipality_code},
    )
    return jsonify(content)


@electoral_bp.get("/electoral/candidates/<uuid:candidate_id>/map")
@electoral_access_required("consultar_dados_publicos")
def candidate_map(candidate_id):
    election_id = _uuid_argument("election_id", required=True)
    if isinstance(election_id, tuple):
        return election_id
    level = (request.args.get("level") or "municipality").strip().lower()
    if level not in AVAILABLE_LEVELS:
        return _validation_error(
            "Nivel territorial indisponivel.", availableLevels=list(AVAILABLE_LEVELS)
        )
    municipality_code = (request.args.get("municipalityCode") or "").strip() or None
    tenant_id, user_id = _private_context()
    content = load_candidate_map(
        candidate_id,
        election_id,
        level,
        municipality_code=municipality_code,
        tenant_id=tenant_id,
        user_id=user_id,
    )
    if content is None:
        return jsonify(error="not_found", message="Candidatura nao encontrada."), 404
    _audit_catalog(
        "electoral.analysis.map_viewed",
        {
            "candidateId": str(candidate_id),
            "electionId": str(election_id),
            "level": level,
            "municipalityCode": municipality_code,
            "geometryVersion": content.get("geometry_version"),
        },
    )
    return jsonify(content)


@electoral_bp.put("/electoral/candidates/<uuid:candidate_id>/identity-review")
@electoral_access_required("comparar_candidatos")
def review_candidate_identity(candidate_id):
    payload = request.get_json(silent=True) or {}
    raw_linked_ids = payload.get("linked_candidate_ids") or []
    decision = str(payload.get("decision") or "").strip().upper()
    notes = str(payload.get("notes") or "").strip() or None
    if decision not in {"CONFIRMED", "REJECTED"}:
        return _validation_error("decision deve ser CONFIRMED ou REJECTED.")
    if not isinstance(raw_linked_ids, list) or not 1 <= len(raw_linked_ids) <= 10:
        return _validation_error("Informe entre 1 e 10 candidaturas vinculadas.")
    if notes and len(notes) > 500:
        return _validation_error("notes deve possuir no maximo 500 caracteres.")
    try:
        linked_ids = {uuid.UUID(value) for value in raw_linked_ids}
    except (TypeError, ValueError):
        return _validation_error("linked_candidate_ids deve conter UUIDs validos.")
    if candidate_id in linked_ids:
        return _validation_error("Uma candidatura nao pode ser vinculada a ela mesma.")
    published_ids = set(
        db.session.scalars(
            select(ElectoralCandidate.id)
            .join(
                ElectoralDatasetVersion,
                ElectoralDatasetVersion.id == ElectoralCandidate.dataset_version_id,
            )
            .where(
                ElectoralCandidate.id.in_({candidate_id, *linked_ids}),
                ElectoralDatasetVersion.status == ElectoralDatasetStatus.PUBLISHED,
            )
        )
    )
    if published_ids != {candidate_id, *linked_ids}:
        return _validation_error("Todas as candidaturas devem pertencer a versoes publicadas.")
    tenant_id, user_id = _private_context()
    items = []
    for linked_id in linked_ids:
        subject_id, related_id = sorted((candidate_id, linked_id), key=str)
        item = db.session.execute(
            select(ElectoralIdentityReview).where(
                ElectoralIdentityReview.tenant_id == tenant_id,
                ElectoralIdentityReview.user_id == user_id,
                ElectoralIdentityReview.subject_candidate_id == subject_id,
                ElectoralIdentityReview.linked_candidate_id == related_id,
            )
        ).scalar_one_or_none()
        if item is None:
            item = ElectoralIdentityReview(
                tenant_id=tenant_id,
                user_id=user_id,
                subject_candidate_id=subject_id,
                linked_candidate_id=related_id,
                decision=decision,
            )
            db.session.add(item)
        item.decision = decision
        item.notes = notes
        items.append(item)
    db.session.flush()
    _audit_catalog(
        "electoral.analysis.identity_reviewed",
        {
            "candidateId": str(candidate_id),
            "linkedCandidateIds": [str(item) for item in linked_ids],
            "decision": decision,
        },
    )
    return jsonify(content=[_identity_review_data(item) for item in items])


@electoral_bp.get("/electoral/favorites")
@electoral_access_required("consultar_dados_publicos")
def list_favorites():
    tenant_id, user_id = _private_context()
    items = db.session.scalars(
        select(ElectoralFavorite)
        .where(
            ElectoralFavorite.tenant_id == tenant_id,
            ElectoralFavorite.user_id == user_id,
        )
        .order_by(ElectoralFavorite.created_at.desc())
    )
    return jsonify(content=[_favorite_data(item) for item in items])


@electoral_bp.post("/electoral/favorites")
@electoral_access_required("consultar_dados_publicos")
def create_favorite():
    payload = request.get_json(silent=True) or {}
    target_type = str(payload.get("target_type") or "").strip().lower()
    target_id = str(payload.get("target_id") or "").strip()
    label = str(payload.get("label") or "").strip()
    snapshot = payload.get("snapshot") or {}
    if target_type not in {"candidate", "territory", "comparison"}:
        return _validation_error("Tipo de favorito invalido.")
    if not target_id or len(target_id) > 80 or not label or len(label) > 160:
        return _validation_error("Identificador ou rotulo de favorito invalido.")
    if not isinstance(snapshot, dict) or len(str(snapshot)) > 4000:
        return _validation_error("Snapshot de favorito invalido.")
    tenant_id, user_id = _private_context()
    item = db.session.execute(
        select(ElectoralFavorite).where(
            ElectoralFavorite.tenant_id == tenant_id,
            ElectoralFavorite.user_id == user_id,
            ElectoralFavorite.target_type == target_type,
            ElectoralFavorite.target_id == target_id,
        )
    ).scalar_one_or_none()
    created = item is None
    if item is None:
        item = ElectoralFavorite(
            tenant_id=tenant_id,
            user_id=user_id,
            target_type=target_type,
            target_id=target_id,
            label=label,
            snapshot=snapshot,
        )
        db.session.add(item)
    else:
        item.label = label
        item.snapshot = snapshot
    db.session.flush()
    _audit_catalog(
        "electoral.analysis.favorite_saved",
        {"favoriteId": str(item.id), "targetType": target_type, "targetId": target_id},
    )
    return jsonify(_favorite_data(item)), 201 if created else 200


@electoral_bp.delete("/electoral/favorites/<uuid:favorite_id>")
@electoral_access_required("consultar_dados_publicos")
def delete_favorite(favorite_id):
    tenant_id, user_id = _private_context()
    item = db.session.execute(
        select(ElectoralFavorite).where(
            ElectoralFavorite.id == favorite_id,
            ElectoralFavorite.tenant_id == tenant_id,
            ElectoralFavorite.user_id == user_id,
        )
    ).scalar_one_or_none()
    if item is None:
        return jsonify(error="not_found", message="Favorito nao encontrado."), 404
    db.session.delete(item)
    _audit_catalog("electoral.analysis.favorite_deleted", {"favoriteId": str(favorite_id)})
    return "", 204


@electoral_bp.get("/electoral/saved-comparisons")
@electoral_access_required("comparar_candidatos")
def list_saved_comparisons():
    tenant_id, user_id = _private_context()
    items = db.session.scalars(
        select(ElectoralSavedComparison)
        .where(
            ElectoralSavedComparison.tenant_id == tenant_id,
            ElectoralSavedComparison.user_id == user_id,
        )
        .order_by(ElectoralSavedComparison.updated_at.desc())
    )
    return jsonify(content=[_saved_comparison_data(item) for item in items])


@electoral_bp.post("/electoral/saved-comparisons")
@electoral_access_required("comparar_candidatos")
def save_comparison():
    payload = request.get_json(silent=True) or {}
    name = str(payload.get("name") or "").strip()
    raw_candidate_ids = payload.get("candidate_ids") or []
    if not name or len(name) > 160:
        return _validation_error("Nome do comparativo invalido.")
    if not isinstance(raw_candidate_ids, list):
        return _validation_error("candidate_ids deve ser uma lista.")
    if not COMPARISON_MIN_CANDIDATES <= len(raw_candidate_ids) <= COMPARISON_MAX_CANDIDATES:
        return _validation_error("Selecione entre 2 e 5 candidaturas para comparar.")
    try:
        candidate_ids = [uuid.UUID(value) for value in raw_candidate_ids]
        election_id = uuid.UUID(str(payload.get("election_id") or ""))
    except (TypeError, ValueError):
        return _validation_error("Eleicao e candidaturas devem possuir UUIDs validos.")
    level = str(payload.get("level") or "municipality").strip().lower()
    municipality_code = str(payload.get("municipalityCode") or "").strip() or None
    if level not in AVAILABLE_LEVELS:
        return _validation_error("Nivel territorial indisponivel.")
    _, error = load_candidate_comparison(
        candidate_ids,
        election_id,
        level,
        municipality_code=municipality_code,
    )
    if error:
        return _validation_error(error)
    tenant_id, user_id = _private_context()
    item = ElectoralSavedComparison(
        tenant_id=tenant_id,
        user_id=user_id,
        name=name,
        election_id=election_id,
        candidate_ids=[str(value) for value in candidate_ids],
        level=level,
        municipality_code=municipality_code,
        filters=payload.get("filters") if isinstance(payload.get("filters"), dict) else {},
    )
    db.session.add(item)
    db.session.flush()
    _audit_catalog(
        "electoral.analysis.comparison_saved",
        {"comparisonId": str(item.id), "candidateCount": len(candidate_ids)},
    )
    return jsonify(_saved_comparison_data(item)), 201


@electoral_bp.delete("/electoral/saved-comparisons/<uuid:comparison_id>")
@electoral_access_required("comparar_candidatos")
def delete_saved_comparison(comparison_id):
    tenant_id, user_id = _private_context()
    item = db.session.execute(
        select(ElectoralSavedComparison).where(
            ElectoralSavedComparison.id == comparison_id,
            ElectoralSavedComparison.tenant_id == tenant_id,
            ElectoralSavedComparison.user_id == user_id,
        )
    ).scalar_one_or_none()
    if item is None:
        return jsonify(error="not_found", message="Comparativo salvo nao encontrado."), 404
    db.session.delete(item)
    _audit_catalog("electoral.analysis.comparison_deleted", {"comparisonId": str(comparison_id)})
    return "", 204


@electoral_bp.post("/electoral/comparisons")
@electoral_access_required("comparar_candidatos")
def compare_candidates():
    payload = request.get_json(silent=True) or {}
    raw_candidate_ids = payload.get("candidate_ids") or []
    if not isinstance(raw_candidate_ids, list):
        return _validation_error("candidate_ids deve ser uma lista.")
    if not COMPARISON_MIN_CANDIDATES <= len(raw_candidate_ids) <= COMPARISON_MAX_CANDIDATES:
        return _validation_error("Selecione entre 2 e 5 candidaturas para comparar.")
    try:
        candidate_ids = [uuid.UUID(value) for value in raw_candidate_ids]
        election_id = uuid.UUID(payload.get("election_id", ""))
    except (TypeError, ValueError):
        return _validation_error("Eleicao e candidaturas devem possuir UUIDs validos.")
    if len(set(candidate_ids)) != len(candidate_ids):
        return _validation_error("Nao repita candidaturas no comparativo.")
    level = str(payload.get("level") or "municipality").strip().lower()
    if level not in AVAILABLE_LEVELS:
        return _validation_error(
            "Nivel territorial indisponivel.", availableLevels=list(AVAILABLE_LEVELS)
        )
    municipality_code = str(payload.get("municipalityCode") or "").strip() or None
    content, error = load_candidate_comparison(
        candidate_ids,
        election_id,
        level,
        municipality_code=municipality_code,
    )
    if error:
        return _validation_error(error)
    _audit_catalog(
        "electoral.analysis.comparison_viewed",
        {
            "candidateIds": [str(item) for item in candidate_ids],
            "electionId": str(election_id),
            "level": level,
            "municipalityCode": municipality_code,
        },
    )
    return jsonify(content)


@electoral_bp.get("/electoral/report-jobs")
@electoral_access_required("exportar")
def list_report_jobs():
    unavailable = _feature_required("exportacoes")
    if unavailable:
        return unavailable
    tenant_id, user_id = _private_context()
    statement = select(ElectoralReportJob).where(ElectoralReportJob.tenant_id == tenant_id)
    if get_jwt().get("role") != Role.REPRESENTATIVE.value:
        statement = statement.where(ElectoralReportJob.requested_by_id == user_id)
    items = db.session.scalars(statement.order_by(ElectoralReportJob.requested_at.desc()))
    return jsonify(content=[_report_job_data(item) for item in items])


@electoral_bp.post("/electoral/report-jobs")
@electoral_access_required("exportar")
def create_report_job():
    unavailable = _feature_required("exportacoes")
    if unavailable:
        return unavailable
    payload = request.get_json(silent=True) or {}
    report_format = str(payload.get("format") or "").strip().upper()
    report_type = str(payload.get("report_type") or "").strip().lower()
    purpose = str(payload.get("purpose") or "").strip()
    level = str(payload.get("level") or "municipality").strip().lower()
    municipality_code = str(payload.get("municipality_code") or "").strip() or None
    if report_format not in {"PDF", "CSV", "XLSX"}:
        return _validation_error("format deve ser PDF, CSV ou XLSX.")
    if report_type not in {"candidate", "comparison"}:
        return _validation_error("report_type deve ser candidate ou comparison.")
    if not 10 <= len(purpose) <= 500:
        return _validation_error("Informe a finalidade da exportacao entre 10 e 500 caracteres.")
    if level not in AVAILABLE_LEVELS:
        return _validation_error(
            "Nivel territorial indisponivel.", availableLevels=list(AVAILABLE_LEVELS)
        )
    raw_ids = payload.get("candidate_ids") or []
    expected = (
        (1, 1)
        if report_type == "candidate"
        else (
            COMPARISON_MIN_CANDIDATES,
            COMPARISON_MAX_CANDIDATES,
        )
    )
    if not isinstance(raw_ids, list) or not expected[0] <= len(raw_ids) <= expected[1]:
        return _validation_error(
            "Informe uma candidatura para relatorio ou entre 2 e 5 para comparacao."
        )
    try:
        candidate_ids = [uuid.UUID(value) for value in raw_ids]
        election_id = uuid.UUID(str(payload.get("election_id") or ""))
    except (TypeError, ValueError):
        return _validation_error("Eleicao e candidaturas devem possuir UUIDs validos.")
    if len(set(candidate_ids)) != len(candidate_ids):
        return _validation_error("Nao repita candidaturas na exportacao.")

    if report_type == "candidate":
        analysis = load_candidate_results(
            candidate_ids[0],
            election_id,
            level,
            municipality_code=municipality_code,
            page=1,
            per_page=1,
        )
        error = None if analysis is not None else "Candidatura publicada nao encontrada."
    else:
        analysis, error = load_candidate_comparison(
            candidate_ids,
            election_id,
            level,
            municipality_code=municipality_code,
        )
    if error:
        return _validation_error(error)

    tenant_id, user_id = _private_context()
    job = ElectoralReportJob(
        tenant_id=tenant_id,
        mandate_id=g.electoral_mandate.id,
        requested_by_id=user_id,
        report_type=report_type,
        format=report_format,
        purpose=purpose,
        filters={
            "election_id": str(election_id),
            "candidate_ids": [str(value) for value in candidate_ids],
            "level": level,
            "municipality_code": municipality_code,
        },
        source_metadata={
            "dataset_version": analysis.get("dataset_version"),
            "source": analysis.get("source"),
        },
    )
    db.session.add(job)
    db.session.flush()
    event = OutboxEvent(
        tenant_id=tenant_id,
        event_type=REPORT_EVENT,
        aggregate_type="electoral_report_job",
        aggregate_id=str(job.id),
        payload={
            "jobId": str(job.id),
            "requestedById": str(user_id),
            "schemaVersion": 1,
            "idempotencyKey": str(job.id),
        },
    )
    db.session.add(event)
    add_audit(
        tenant_id,
        user_id,
        "electoral.report.requested",
        "electoral_report_job",
        job.id,
        after={
            "format": report_format,
            "reportType": report_type,
            "purpose": purpose,
            "candidateCount": len(candidate_ids),
        },
    )
    db.session.commit()
    return jsonify(_report_job_data(job)), 202


@electoral_bp.get("/electoral/report-jobs/<uuid:job_id>")
@electoral_access_required("exportar")
def get_report_job(job_id):
    unavailable = _feature_required("exportacoes")
    if unavailable:
        return unavailable
    job = _accessible_report_job(job_id)
    if job is None:
        return jsonify(error="not_found", message="Exportacao nao encontrada."), 404
    return jsonify(_report_job_data(job))


@electoral_bp.post("/electoral/report-jobs/<uuid:job_id>/retry")
@electoral_access_required("exportar")
def retry_report_job(job_id):
    unavailable = _feature_required("exportacoes")
    if unavailable:
        return unavailable
    job = _accessible_report_job(job_id)
    if job is None:
        return jsonify(error="not_found", message="Exportacao nao encontrada."), 404
    if job.status != "FAILED" or job.revoked_at is not None:
        return _validation_error("Somente exportacoes com falha podem ser reenfileiradas.")
    job.status = "QUEUED"
    job.error = None
    job.retry_count += 1
    job.started_at = None
    job.completed_at = None
    db.session.add(
        OutboxEvent(
            tenant_id=job.tenant_id,
            event_type=REPORT_EVENT,
            aggregate_type="electoral_report_job",
            aggregate_id=str(job.id),
            payload={
                "jobId": str(job.id),
                "requestedById": str(job.requested_by_id),
                "schemaVersion": 1,
                "idempotencyKey": f"{job.id}:retry:{job.retry_count}",
            },
        )
    )
    add_audit(
        job.tenant_id,
        uuid.UUID(get_jwt_identity()),
        "electoral.report.retried",
        "electoral_report_job",
        job.id,
        after={"retryCount": job.retry_count},
    )
    db.session.commit()
    return jsonify(_report_job_data(job)), 202


@electoral_bp.post("/electoral/report-jobs/<uuid:job_id>/share")
@electoral_access_required("exportar")
def share_report_job(job_id):
    unavailable = _feature_required("exportacoes")
    if unavailable:
        return unavailable
    job = _accessible_report_job(job_id)
    if job is None:
        return jsonify(error="not_found", message="Exportacao nao encontrada."), 404
    report = _generated_report(job)
    if report is None or job.status != "COMPLETED" or not _report_is_active(report):
        return _validation_error("O arquivo ainda nao esta disponivel ou foi revogado.")
    token = signed_report_token(report)
    url = f"/api/v1/electoral/reports/{report.id}/download?token={token}"
    add_audit(
        job.tenant_id,
        uuid.UUID(get_jwt_identity()),
        "electoral.report.shared",
        "electoral_generated_report",
        report.id,
        after={"expiresInSeconds": current_app.config["ELECTORAL_REPORT_LINK_MAX_AGE_SECONDS"]},
    )
    db.session.commit()
    return jsonify(
        download_url=url,
        expires_in=current_app.config["ELECTORAL_REPORT_LINK_MAX_AGE_SECONDS"],
    )


@electoral_bp.get("/electoral/reports/<uuid:report_id>/download")
@electoral_access_required("exportar")
def download_report(report_id):
    unavailable = _feature_required("exportacoes")
    if unavailable:
        return unavailable
    tenant_id, user_id = _private_context()
    report = db.session.execute(
        select(ElectoralGeneratedReport).where(
            ElectoralGeneratedReport.id == report_id,
            ElectoralGeneratedReport.tenant_id == tenant_id,
        )
    ).scalar_one_or_none()
    token = request.args.get("token") or ""
    if report is None or not verify_report_token(token, report_id, tenant_id):
        return jsonify(error="invalid_token", message="Link invalido ou expirado."), 403
    if not _report_is_active(report):
        return jsonify(error="not_found", message="Relatorio revogado ou expirado."), 404
    try:
        content = report_bytes(report)
    except NonRetryableReportError:
        return jsonify(error="not_found", message="Arquivo do relatorio nao encontrado."), 404
    report.download_count += 1
    report.last_downloaded_at = datetime.now(UTC)
    add_audit(
        tenant_id,
        user_id,
        "electoral.report.downloaded",
        "electoral_generated_report",
        report.id,
        after={"format": report.filename.rsplit(".", 1)[-1].upper()},
    )
    db.session.commit()
    return send_file(
        io.BytesIO(content),
        mimetype=report.mime_type,
        as_attachment=True,
        download_name=report.filename,
        max_age=0,
    )


@electoral_bp.delete("/electoral/report-jobs/<uuid:job_id>")
@electoral_access_required("exportar")
def revoke_report_job(job_id):
    unavailable = _feature_required("exportacoes")
    if unavailable:
        return unavailable
    job = _accessible_report_job(job_id)
    if job is None:
        return jsonify(error="not_found", message="Exportacao nao encontrada."), 404
    now = datetime.now(UTC)
    actor_id = uuid.UUID(get_jwt_identity())
    job.status = "REVOKED"
    job.revoked_at = now
    job.revoked_by_id = actor_id
    report = _generated_report(job)
    if report:
        report.revoked_at = now
    add_audit(
        job.tenant_id,
        actor_id,
        "electoral.report.revoked",
        "electoral_report_job",
        job.id,
    )
    db.session.commit()
    return "", 204


@electoral_bp.get("/electoral/delegations")
@electoral_access_required("delegar_acesso")
def list_delegations():
    unavailable = _feature_required("delegacao")
    if unavailable:
        return unavailable
    tenant_id, _ = _private_context()
    delegations = db.session.scalars(
        select(ElectoralAccessDelegation)
        .where(
            ElectoralAccessDelegation.tenant_id == tenant_id,
            ElectoralAccessDelegation.mandate_id == g.electoral_mandate.id,
        )
        .order_by(ElectoralAccessDelegation.created_at.desc())
    )
    users = db.session.scalars(
        select(User)
        .where(
            User.tenant_id == tenant_id,
            User.status == UserStatus.ACTIVE,
            User.id != g.electoral_mandate.representative_user_id,
        )
        .order_by(User.name)
    )
    return jsonify(
        content=[_delegation_data(item) for item in delegations],
        eligible_users=[
            {"id": str(user.id), "name": user.name, "role": user.role.value} for user in users
        ],
    )


@electoral_bp.post("/electoral/delegations")
@electoral_access_required("delegar_acesso")
def create_delegation():
    unavailable = _feature_required("delegacao")
    if unavailable:
        return unavailable
    payload = request.get_json(silent=True) or {}
    reason = str(payload.get("reason") or "").strip()
    capabilities = payload.get("capabilities") or []
    try:
        grantee_id = uuid.UUID(str(payload.get("grantee_user_id") or ""))
        valid_days = int(payload.get("valid_days", 7))
    except (TypeError, ValueError):
        return _validation_error("Assessor e prazo devem ser validos.")
    allowed = set(g.electoral_capabilities) - {"delegar_acesso"}
    if not isinstance(capabilities, list) or not capabilities:
        return _validation_error("Selecione ao menos uma capacidade.")
    if set(capabilities) - allowed:
        return _validation_error("Uma ou mais capacidades nao podem ser delegadas.")
    if not 1 <= valid_days <= 90:
        return _validation_error("O prazo deve estar entre 1 e 90 dias.")
    if not 10 <= len(reason) <= 500:
        return _validation_error("Informe o motivo entre 10 e 500 caracteres.")
    tenant_id, grantor_id = _private_context()
    grantee = db.session.execute(
        select(User).where(
            User.id == grantee_id,
            User.tenant_id == tenant_id,
            User.status == UserStatus.ACTIVE,
        )
    ).scalar_one_or_none()
    if grantee is None or grantee.id == grantor_id:
        return _validation_error("Assessor elegivel nao encontrado.")
    now = datetime.now(UTC)
    delegation = ElectoralAccessDelegation(
        tenant_id=tenant_id,
        mandate_id=g.electoral_mandate.id,
        grantor_user_id=grantor_id,
        grantee_user_id=grantee.id,
        capabilities=sorted(set(capabilities)),
        reason=reason,
        valid_from=now,
        valid_until=now + timedelta(days=valid_days),
    )
    db.session.add(delegation)
    db.session.flush()
    add_audit(
        tenant_id,
        grantor_id,
        "electoral.delegation.granted",
        "electoral_access_delegation",
        delegation.id,
        after={
            "granteeUserId": str(grantee.id),
            "capabilities": delegation.capabilities,
            "validUntil": delegation.valid_until.isoformat(),
            "reason": reason,
        },
    )
    db.session.commit()
    return jsonify(_delegation_data(delegation)), 201


@electoral_bp.delete("/electoral/delegations/<uuid:delegation_id>")
@electoral_access_required("delegar_acesso")
def revoke_delegation(delegation_id):
    unavailable = _feature_required("delegacao")
    if unavailable:
        return unavailable
    tenant_id, actor_id = _private_context()
    delegation = db.session.execute(
        select(ElectoralAccessDelegation).where(
            ElectoralAccessDelegation.id == delegation_id,
            ElectoralAccessDelegation.tenant_id == tenant_id,
            ElectoralAccessDelegation.mandate_id == g.electoral_mandate.id,
        )
    ).scalar_one_or_none()
    if delegation is None:
        return jsonify(error="not_found", message="Delegacao nao encontrada."), 404
    if delegation.revoked_at is None:
        delegation.revoked_at = datetime.now(UTC)
        delegation.revoked_by_id = actor_id
        add_audit(
            tenant_id,
            actor_id,
            "electoral.delegation.revoked",
            "electoral_access_delegation",
            delegation.id,
            after={"granteeUserId": str(delegation.grantee_user_id)},
        )
        db.session.commit()
    return "", 204


def _election_data(item: ElectoralElection, dataset: ElectoralDatasetVersion) -> dict:
    return {
        "id": str(item.id),
        "codigoTse": item.external_id,
        "nome": item.name,
        "year": item.year,
        "scope": item.scope,
        "round": item.round,
        "rounds": item.round,
        "data": item.election_date.isoformat() if item.election_date else None,
        "uf": item.uf,
        "dataset_version": str(dataset.id),
        "quality_score": dataset.quality_score,
        "fonte": dataset.source_url,
    }


def _dataset_data(item: ElectoralDatasetVersion) -> dict:
    return {
        "id": str(item.id),
        "status": item.status.value,
        "ano": item.election_year,
        "escopo": item.election_scope,
        "uf": item.uf,
        "cargoCodigo": item.office_code,
        "fonte": item.source_url,
        "hash": item.source_hash,
        "parser": item.parser_version,
        "qualidade": item.quality_score,
        "linhas": item.row_count,
        "votos": item.total_votes,
        "manifesto": item.validation_manifest,
        "publicadoEm": item.published_at.isoformat() if item.published_at else None,
    }


def _identity_review_data(item: ElectoralIdentityReview) -> dict:
    return {
        "id": str(item.id),
        "subject_candidate_id": str(item.subject_candidate_id),
        "linked_candidate_id": str(item.linked_candidate_id),
        "decision": item.decision,
        "method": item.method,
        "notes": item.notes,
        "reviewed_at": item.reviewed_at.isoformat(),
    }


def _favorite_data(item: ElectoralFavorite) -> dict:
    return {
        "id": str(item.id),
        "target_type": item.target_type,
        "target_id": item.target_id,
        "label": item.label,
        "snapshot": item.snapshot,
        "created_at": item.created_at.isoformat(),
    }


def _saved_comparison_data(item: ElectoralSavedComparison) -> dict:
    return {
        "id": str(item.id),
        "name": item.name,
        "election_id": str(item.election_id),
        "candidate_ids": item.candidate_ids,
        "level": item.level,
        "municipalityCode": item.municipality_code,
        "filters": item.filters,
        "created_at": item.created_at.isoformat(),
        "updated_at": item.updated_at.isoformat(),
    }


def _report_job_data(item: ElectoralReportJob) -> dict:
    report = _generated_report(item)
    return {
        "id": str(item.id),
        "report_type": item.report_type,
        "format": item.format,
        "purpose": item.purpose,
        "filters": item.filters,
        "source_metadata": item.source_metadata,
        "status": item.status,
        "retry_count": item.retry_count,
        "error": item.error,
        "requested_by_id": str(item.requested_by_id),
        "requested_at": item.requested_at.isoformat(),
        "started_at": item.started_at.isoformat() if item.started_at else None,
        "completed_at": item.completed_at.isoformat() if item.completed_at else None,
        "revoked_at": item.revoked_at.isoformat() if item.revoked_at else None,
        "report": (
            {
                "id": str(report.id),
                "filename": report.filename,
                "mime_type": report.mime_type,
                "size_bytes": report.size_bytes,
                "sha256": report.sha256,
                "expires_at": report.expires_at.isoformat(),
                "download_count": report.download_count,
                "available": _report_is_active(report),
            }
            if report
            else None
        ),
    }


def _delegation_data(item: ElectoralAccessDelegation) -> dict:
    grantee = db.session.get(User, item.grantee_user_id)
    now = (
        datetime.now(UTC)
        if item.valid_until.tzinfo
        else datetime.now(UTC).replace(tzinfo=None)
    )
    return {
        "id": str(item.id),
        "grantee_user_id": str(item.grantee_user_id),
        "grantee_name": grantee.name if grantee else "Usuario removido",
        "capabilities": item.capabilities,
        "reason": item.reason,
        "valid_from": item.valid_from.isoformat(),
        "valid_until": item.valid_until.isoformat(),
        "revoked_at": item.revoked_at.isoformat() if item.revoked_at else None,
        "active": item.revoked_at is None and item.valid_from <= now < item.valid_until,
        "created_at": item.created_at.isoformat(),
    }


def _feature_required(name: str):
    tenant_id = uuid.UUID(get_jwt()["tenant_id"])
    settings = db.session.get(ElectoralModuleSettings, tenant_id)
    flags = {**DEFAULT_FEATURE_FLAGS, **(settings.feature_flags if settings else {})}
    if flags.get(name):
        return None
    return (
        jsonify(
            error="feature_disabled",
            message=f"Funcionalidade eleitoral desabilitada: {name}.",
        ),
        403,
    )


def _accessible_report_job(job_id: uuid.UUID) -> ElectoralReportJob | None:
    tenant_id, user_id = _private_context()
    statement = select(ElectoralReportJob).where(
        ElectoralReportJob.id == job_id,
        ElectoralReportJob.tenant_id == tenant_id,
    )
    if get_jwt().get("role") != Role.REPRESENTATIVE.value:
        statement = statement.where(ElectoralReportJob.requested_by_id == user_id)
    return db.session.execute(statement).scalar_one_or_none()


def _generated_report(job: ElectoralReportJob) -> ElectoralGeneratedReport | None:
    return db.session.execute(
        select(ElectoralGeneratedReport).where(
            ElectoralGeneratedReport.report_job_id == job.id,
            ElectoralGeneratedReport.tenant_id == job.tenant_id,
        )
    ).scalar_one_or_none()


def _report_is_active(report: ElectoralGeneratedReport) -> bool:
    now = (
        datetime.now(UTC)
        if report.expires_at.tzinfo
        else datetime.now(UTC).replace(tzinfo=None)
    )
    return report.revoked_at is None and report.expires_at > now


def _private_context() -> tuple[uuid.UUID, uuid.UUID]:
    return uuid.UUID(get_jwt()["tenant_id"]), uuid.UUID(get_jwt_identity())


def _audit_catalog(action: str, filters: dict | None = None) -> None:
    tenant_id = uuid.UUID(get_jwt()["tenant_id"])
    user_id = uuid.UUID(get_jwt_identity())
    add_audit(
        tenant_id,
        user_id,
        action,
        "electoral_catalog",
        None,
        after={"filters": filters or {}},
    )
    db.session.commit()


def _uuid_argument(name: str, *, required: bool = False):
    value = (request.args.get(name) or "").strip()
    if not value:
        return _validation_error(f"Parametro obrigatorio ausente: {name}.") if required else None
    try:
        return uuid.UUID(value)
    except ValueError:
        return _validation_error(f"Parametro UUID invalido: {name}.")


def _validation_error(message: str, **details):
    return jsonify(error="validation_error", message=message, **details), 422
