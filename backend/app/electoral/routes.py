import io
import uuid
from datetime import UTC, date, datetime, timedelta

from flask import Blueprint, current_app, g, jsonify, request, send_file
from flask_jwt_extended import get_jwt, get_jwt_identity
from sqlalchemy import String, cast, func, or_, select

from app.audit import add_audit
from app.electoral.access import electoral_access_required
from app.electoral.advanced_features import (
    AdvancedFeatureError,
    agenda_routes,
    create_report_schedule,
    mandate_map_layers,
    pre_visit_briefing,
    preference_data,
    report_schedule_data,
    save_segment,
    save_user_preference,
    segment_catalog,
    segment_data,
    user_preference,
)
from app.electoral.ai_generation import electoral_ai_runtime
from app.electoral.analytics import (
    AVAILABLE_LEVELS,
    COMPARISON_MAX_CANDIDATES,
    COMPARISON_MIN_CANDIDATES,
    TerritorialLevelUnavailable,
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
from app.electoral.commitments import (
    CommitmentError,
    accessible_commitment,
    add_evidence,
    commitment_data,
    create_commitment,
    effective_status,
    operational_map_data,
    update_commitment,
)
from app.electoral.coverage import coverage_catalog
from app.electoral.identity import (
    AUTOMATIC_CPF_METHOD,
    MANUAL_FALLBACK_METHOD,
    manual_fallback_reason,
    reconcile_user_candidacies,
    user_identity_status,
)
from app.electoral.insights import (
    INSIGHT_EVENT,
    MODEL_NAME,
    MODEL_PROVIDER,
    PROMPT_VERSION,
    QUESTION_MODEL_NAME,
    QUESTION_PROMPT_VERSION,
    accessible_insight,
    insight_data,
    record_feedback,
    review_insight,
)
from app.electoral.mandate_intelligence import (
    MandateIntelligenceError,
    active_profile,
    alert_delivery_data,
    alert_feed_data,
    alert_preference,
    alert_preference_data,
    create_profile,
    create_territory_link,
    dispatch_alert_deliveries,
    ensure_default_profile,
    generate_snapshot,
    latest_snapshot,
    profile_data,
    snapshot_data,
    territory_briefing_data,
    territory_link_catalog,
    territory_link_data,
    territory_overlay_data,
    upsert_alert_preference,
)
from app.electoral.portfolios import (
    MAX_SCENARIOS as PORTFOLIO_MAX_SCENARIOS,
)
from app.electoral.portfolios import (
    PortfolioValidationError,
    evaluate_portfolio,
    portfolio_csv,
    portfolio_data,
    portfolio_event_data,
    portfolio_scenarios,
    record_portfolio_event,
)
from app.electoral.portfolios import (
    ensure_compatible as ensure_portfolio_compatible,
)
from app.electoral.portfolios import (
    normalize_goals as normalize_portfolio_goals,
)
from app.electoral.reports import (
    REPORT_EVENT,
    NonRetryableReportError,
    report_bytes,
    signed_report_token,
    verify_report_token,
)
from app.electoral.safety import POLICY_VERSION as ELECTORAL_SAFETY_POLICY_VERSION
from app.electoral.safety import assess_electoral_question
from app.electoral.scenarios import (
    DISCLAIMER as SCENARIO_DISCLAIMER,
)
from app.electoral.scenarios import (
    METHODOLOGY_VERSION as SCENARIO_METHODOLOGY_VERSION,
)
from app.electoral.scenarios import (
    ScenarioValidationError,
    analysis_data,
    build_from_snapshot,
    build_scenario,
    compare_scenarios,
    hash_share_token,
    new_share_token,
    scenario_data,
    sensitivity_analysis,
    share_data,
)
from app.extensions import db
from app.models import (
    ElectoralAccessDelegation,
    ElectoralAlertDelivery,
    ElectoralCandidacy,
    ElectoralCandidate,
    ElectoralDatasetStatus,
    ElectoralDatasetVersion,
    ElectoralElection,
    ElectoralFavorite,
    ElectoralGeneratedReport,
    ElectoralIdentityReview,
    ElectoralInsight,
    ElectoralMandateSnapshot,
    ElectoralModuleSettings,
    ElectoralOffice,
    ElectoralOperationalTerritoryLink,
    ElectoralParty,
    ElectoralPublicCommitment,
    ElectoralReportJob,
    ElectoralReportSchedule,
    ElectoralSavedComparison,
    ElectoralScenario,
    ElectoralScenarioAnalysis,
    ElectoralScenarioPortfolio,
    ElectoralScenarioPortfolioEvent,
    ElectoralScenarioPortfolioItem,
    ElectoralScenarioShare,
    ElectoralTerritorySegment,
    ElectoralUserCandidacy,
    OutboxEvent,
    Role,
    Territory,
    User,
    UserStatus,
)

electoral_bp = Blueprint("electoral", __name__)

DEFAULT_FEATURE_FLAGS = {
    "catalogo": True,
    "exportacoes": False,
    "camadasMandato": False,
    "ia": True,
    "cenarios": False,
    "delegacao": False,
}


@electoral_bp.get("/electoral/disponibilidade")
@electoral_access_required("consultar_dados_publicos")
def availability():
    tenant_id = uuid.UUID(get_jwt()["tenant_id"])
    user_id = uuid.UUID(get_jwt_identity())
    settings = db.session.get(ElectoralModuleSettings, tenant_id)
    flags = _effective_feature_flags(settings)
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
        iaEleitoral=electoral_ai_runtime(),
    )


@electoral_bp.get("/electoral/elections")
@electoral_access_required("consultar_dados_publicos")
def list_elections():
    return _list_elections(explore=False)


@electoral_bp.get("/electoral/elections/explore")
@electoral_access_required("consultar_dados_publicos")
def explore_elections():
    return _list_elections(explore=True)


def _list_elections(*, explore: bool):
    page = max(1, request.args.get("page", 1, type=int))
    per_page = min(100, max(1, request.args.get("perPage", 20, type=int)))
    filters = [ElectoralDatasetVersion.status == ElectoralDatasetStatus.PUBLISHED]
    year = request.args.get("year", type=int)
    if year:
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
    if not explore:
        tenant_id, _ = _private_context()
        statement = (
            statement.join(
                ElectoralCandidacy,
                ElectoralCandidacy.election_id == ElectoralElection.id,
            )
            .join(
                ElectoralUserCandidacy,
                ElectoralUserCandidacy.candidacy_id == ElectoralCandidacy.id,
            )
            .where(
                ElectoralUserCandidacy.tenant_id == tenant_id,
                ElectoralUserCandidacy.user_id == _identity_owner_id(),
            )
            .distinct()
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
    _audit_catalog(
        "electoral.catalog.elections_explored"
        if explore
        else "electoral.catalog.own_elections_viewed",
        {"page": page, "year": year},
    )
    return jsonify(
        items=[_election_data(election, dataset) for election, dataset in rows],
        page=page,
        perPage=per_page,
        total=total,
    )


@electoral_bp.get("/electoral/identity")
@electoral_access_required("consultar_dados_publicos")
def get_electoral_identity():
    tenant_id, _ = _private_context()
    owner_id = _identity_owner_id()
    reconciliation = user_identity_status(owner_id)
    rows = db.session.execute(_identity_candidacies_statement(tenant_id, owner_id)).all()
    owner = db.session.get(User, owner_id)
    return jsonify(
        configured=bool(rows),
        ownerUserId=str(owner_id),
        canManage=_actor_is_identity_owner(),
        cpfConfigured=bool(owner and owner.cpf),
        identityStatus=reconciliation["status"],
        lastOfficialSyncAt=reconciliation["lastOfficialSyncAt"],
        manualFallbackAllowed=reconciliation["manualFallbackAllowed"],
        candidacies=[_user_candidacy_data(*row) for row in rows],
    )


@electoral_bp.post("/electoral/identity/reconcile")
@electoral_access_required("consultar_dados_publicos")
def reconcile_electoral_identity():
    tenant_id, actor_id = _private_context()
    owner_id = _identity_owner_id()
    result = reconcile_user_candidacies(tenant_id, owner_id)
    add_audit(
        tenant_id,
        actor_id,
        "electoral.identity.reconciliation_requested",
        "user",
        owner_id,
        after={
            "status": result["status"],
            "matchedCandidacies": result["matchedCandidacies"],
            "createdOrUpdated": result["createdOrUpdated"],
        },
    )
    db.session.commit()
    return jsonify(result)


@electoral_bp.post("/electoral/identity/candidacies")
@electoral_access_required("consultar_dados_publicos")
def confirm_electoral_candidacy():
    if not _actor_is_identity_owner():
        return jsonify(
            error="representative_required",
            message="Somente o parlamentar titular pode confirmar uma candidatura propria.",
        ), 403
    payload = request.get_json(silent=True) or {}
    try:
        candidacy_id = uuid.UUID(str(payload.get("candidacy_id") or ""))
    except (ValueError, TypeError, AttributeError):
        return _validation_error("candidacy_id deve ser um UUID valido.")
    published = db.session.scalar(
        select(ElectoralCandidacy.id)
        .join(
            ElectoralDatasetVersion,
            ElectoralDatasetVersion.id == ElectoralCandidacy.dataset_version_id,
        )
        .where(
            ElectoralCandidacy.id == candidacy_id,
            ElectoralDatasetVersion.status == ElectoralDatasetStatus.PUBLISHED,
        )
    )
    if published is None:
        return jsonify(error="not_found", message="Candidatura publicada nao encontrada."), 404
    tenant_id, actor_id = _private_context()
    owner_id = _identity_owner_id()
    fallback_reason = manual_fallback_reason(candidacy_id, owner_id)
    if fallback_reason is None:
        reconcile_user_candidacies(tenant_id, owner_id)
        existing = db.session.scalar(
            select(ElectoralUserCandidacy).where(
                ElectoralUserCandidacy.tenant_id == tenant_id,
                ElectoralUserCandidacy.user_id == owner_id,
                ElectoralUserCandidacy.candidacy_id == candidacy_id,
            )
        )
        if existing is not None:
            row = db.session.execute(
                _identity_candidacies_statement(tenant_id, owner_id).where(
                    ElectoralUserCandidacy.id == existing.id
                )
            ).one()
            return jsonify(_user_candidacy_data(*row)), 200
    existing = db.session.scalar(
        select(ElectoralUserCandidacy).where(
            ElectoralUserCandidacy.tenant_id == tenant_id,
            ElectoralUserCandidacy.user_id == owner_id,
            ElectoralUserCandidacy.candidacy_id == candidacy_id,
        )
    )
    if existing is None:
        existing = ElectoralUserCandidacy(
            tenant_id=tenant_id,
            user_id=owner_id,
            candidacy_id=candidacy_id,
            method=MANUAL_FALLBACK_METHOD,
        )
        db.session.add(existing)
        db.session.flush()
        add_audit(
            tenant_id,
            actor_id,
            "electoral.identity.candidacy_confirmed",
            "electoral_user_candidacy",
            existing.id,
            after={
                "candidacyId": str(candidacy_id),
                "method": existing.method,
                "fallbackReason": fallback_reason,
            },
        )
        db.session.commit()
    row = db.session.execute(
        _identity_candidacies_statement(tenant_id, _identity_owner_id()).where(
            ElectoralUserCandidacy.id == existing.id
        )
    ).one()
    return jsonify(_user_candidacy_data(*row)), 201


@electoral_bp.delete("/electoral/identity/candidacies/<uuid:candidacy_id>")
@electoral_access_required("consultar_dados_publicos")
def remove_electoral_candidacy(candidacy_id):
    if not _actor_is_identity_owner():
        return jsonify(
            error="representative_required",
            message="Somente o parlamentar titular pode remover uma candidatura propria.",
        ), 403
    tenant_id, actor_id = _private_context()
    item = db.session.scalar(
        select(ElectoralUserCandidacy).where(
            ElectoralUserCandidacy.tenant_id == tenant_id,
            ElectoralUserCandidacy.user_id == _identity_owner_id(),
            ElectoralUserCandidacy.candidacy_id == candidacy_id,
        )
    )
    if item is None:
        return jsonify(error="not_found", message="Participacao confirmada nao encontrada."), 404
    if item.method == AUTOMATIC_CPF_METHOD:
        return jsonify(
            error="automatic_identity_link",
            message=(
                "A participacao foi vinculada automaticamente pelo CPF oficial. "
                "Corrija o CPF cadastrado ou solicite revisao da divergencia."
            ),
        ), 409
    item_id = item.id
    db.session.delete(item)
    add_audit(
        tenant_id,
        actor_id,
        "electoral.identity.candidacy_removed",
        "electoral_user_candidacy",
        item_id,
        before={"candidacyId": str(candidacy_id)},
    )
    db.session.commit()
    return "", 204


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
    uf = str(request.args.get("uf") or "").strip().upper() or None
    if uf is not None and (len(uf) != 2 or not uf.isalpha()):
        return _validation_error("UF deve possuir duas letras.")
    content = coverage_catalog(uf=uf)
    _audit_catalog("electoral.catalog.coverage_viewed", {"uf": uf})
    return jsonify(content)


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


@electoral_bp.get("/electoral/preferences")
@electoral_access_required("consultar_dados_publicos")
def get_electoral_preferences():
    tenant_id, user_id = _private_context()
    return jsonify(preference_data(user_preference(tenant_id, g.electoral_mandate.id, user_id)))


@electoral_bp.put("/electoral/preferences")
@electoral_access_required("consultar_dados_publicos")
def put_electoral_preferences():
    tenant_id, user_id = _private_context()
    body = request.get_json(silent=True) or {}
    if body.get("election_id"):
        try:
            election_id = uuid.UUID(str(body["election_id"]))
        except ValueError:
            return _validation_error("election_id inválido.")
        if not _participated_in_election(election_id):
            return _election_scope_error()
    try:
        item = save_user_preference(tenant_id, g.electoral_mandate.id, user_id, body)
    except AdvancedFeatureError as exc:
        return _validation_error(str(exc))
    add_audit(
        tenant_id, user_id, "electoral.preferences.updated", "electoral_user_preference", item.id
    )
    db.session.commit()
    return jsonify(preference_data(item))


@electoral_bp.get("/electoral/territory-segments")
@electoral_access_required("consultar_dados_publicos")
def list_territory_segments():
    try:
        election_id = uuid.UUID(str(request.args["election_id"]))
    except (KeyError, ValueError):
        return _validation_error("election_id inválido.")
    if not _participated_in_election(election_id):
        return _election_scope_error()
    tenant_id, user_id = _private_context()
    return jsonify(segment_catalog(tenant_id, g.electoral_mandate.id, user_id, election_id))


@electoral_bp.post("/electoral/territory-segments")
@electoral_access_required("consultar_dados_publicos")
def post_territory_segment():
    tenant_id, user_id = _private_context()
    body = request.get_json(silent=True) or {}
    try:
        election_id = uuid.UUID(str(body.get("election_id") or ""))
    except ValueError:
        return _validation_error("election_id inválido.")
    if not _participated_in_election(election_id):
        return _election_scope_error()
    try:
        item = save_segment(tenant_id, g.electoral_mandate.id, user_id, body)
    except AdvancedFeatureError as exc:
        return _validation_error(str(exc))
    add_audit(
        tenant_id,
        user_id,
        "electoral.territory_segment.created",
        "electoral_territory_segment",
        item.id,
    )
    db.session.commit()
    return jsonify(segment_data(item)), 201


@electoral_bp.patch("/electoral/territory-segments/<uuid:segment_id>")
@electoral_access_required("consultar_dados_publicos")
def patch_territory_segment(segment_id):
    tenant_id, user_id = _private_context()
    item = db.session.execute(
        select(ElectoralTerritorySegment).where(
            ElectoralTerritorySegment.id == segment_id,
            ElectoralTerritorySegment.tenant_id == tenant_id,
            ElectoralTerritorySegment.mandate_id == g.electoral_mandate.id,
            ElectoralTerritorySegment.user_id == user_id,
        )
    ).scalar_one_or_none()
    if item is None:
        return jsonify(error="not_found", message="Segmento territorial não encontrado."), 404
    body = {**segment_data(item), **(request.get_json(silent=True) or {})}
    try:
        item = save_segment(tenant_id, g.electoral_mandate.id, user_id, body, item=item)
    except AdvancedFeatureError as exc:
        return _validation_error(str(exc))
    add_audit(
        tenant_id,
        user_id,
        "electoral.territory_segment.updated",
        "electoral_territory_segment",
        item.id,
    )
    db.session.commit()
    return jsonify(segment_data(item))


@electoral_bp.delete("/electoral/territory-segments/<uuid:segment_id>")
@electoral_access_required("consultar_dados_publicos")
def delete_territory_segment(segment_id):
    tenant_id, user_id = _private_context()
    item = db.session.execute(
        select(ElectoralTerritorySegment).where(
            ElectoralTerritorySegment.id == segment_id,
            ElectoralTerritorySegment.tenant_id == tenant_id,
            ElectoralTerritorySegment.mandate_id == g.electoral_mandate.id,
            ElectoralTerritorySegment.user_id == user_id,
        )
    ).scalar_one_or_none()
    if item is None:
        return jsonify(error="not_found", message="Segmento territorial não encontrado."), 404
    db.session.delete(item)
    add_audit(
        tenant_id,
        user_id,
        "electoral.territory_segment.deleted",
        "electoral_territory_segment",
        item.id,
    )
    db.session.commit()
    return "", 204


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


@electoral_bp.get("/electoral/territory-links")
@electoral_access_required("ver_camadas_mandato")
def list_territory_links():
    if disabled := _feature_required("camadasMandato"):
        return disabled
    try:
        election_id = uuid.UUID(str(request.args["election_id"]))
    except (KeyError, ValueError):
        return _validation_error("election_id inválido.")
    tenant_id, _ = _private_context()
    return jsonify(territory_link_catalog(tenant_id, g.electoral_mandate.id, election_id))


@electoral_bp.post("/electoral/territory-links")
@electoral_access_required("ver_camadas_mandato")
def post_territory_link():
    if disabled := _feature_required("camadasMandato"):
        return disabled
    if get_jwt().get("role") != Role.REPRESENTATIVE.value:
        return jsonify(
            error="representative_required",
            message="Somente o parlamentar revisa vínculos territoriais.",
        ), 403
    tenant_id, user_id = _private_context()
    try:
        item, territory, electoral = create_territory_link(
            tenant_id, g.electoral_mandate.id, user_id, request.get_json(silent=True) or {}
        )
    except MandateIntelligenceError as exc:
        return _validation_error(str(exc))
    add_audit(
        tenant_id,
        user_id,
        "electoral.territory_link.reviewed",
        "electoral_operational_territory_link",
        item.id,
        after={
            "territory_id": str(item.territory_id),
            "electoral_territory_id": str(item.electoral_territory_id),
        },
    )
    db.session.commit()
    return jsonify(territory_link_data(item, territory, electoral)), 201


@electoral_bp.delete("/electoral/territory-links/<uuid:link_id>")
@electoral_access_required("ver_camadas_mandato")
def delete_territory_link(link_id):
    if disabled := _feature_required("camadasMandato"):
        return disabled
    if get_jwt().get("role") != Role.REPRESENTATIVE.value:
        return jsonify(
            error="representative_required",
            message="Somente o parlamentar revisa vínculos territoriais.",
        ), 403
    tenant_id, user_id = _private_context()
    item = db.session.execute(
        select(ElectoralOperationalTerritoryLink).where(
            ElectoralOperationalTerritoryLink.id == link_id,
            ElectoralOperationalTerritoryLink.tenant_id == tenant_id,
            ElectoralOperationalTerritoryLink.mandate_id == g.electoral_mandate.id,
            ElectoralOperationalTerritoryLink.active.is_(True),
        )
    ).scalar_one_or_none()
    if item is None:
        return jsonify(error="not_found", message="Vínculo territorial não encontrado."), 404
    item.active = False
    add_audit(
        tenant_id,
        user_id,
        "electoral.territory_link.deactivated",
        "electoral_operational_territory_link",
        item.id,
    )
    db.session.commit()
    return "", 204


@electoral_bp.get("/electoral/mandate-snapshots")
@electoral_access_required("ver_camadas_mandato")
def list_mandate_snapshots():
    if disabled := _feature_required("camadasMandato"):
        return disabled
    tenant_id, _ = _private_context()
    limit = min(50, max(1, request.args.get("limit", 20, type=int)))
    items = list(
        db.session.execute(
            select(ElectoralMandateSnapshot)
            .where(
                ElectoralMandateSnapshot.tenant_id == tenant_id,
                ElectoralMandateSnapshot.mandate_id == g.electoral_mandate.id,
            )
            .order_by(ElectoralMandateSnapshot.created_at.desc())
            .limit(limit)
        ).scalars()
    )
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
    dispatch_alert_deliveries(
        tenant_id,
        g.electoral_mandate.id,
        snapshot=snapshot,
        frequencies={"IMMEDIATE"},
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


@electoral_bp.get("/electoral/territories/<uuid:territory_id>/mandate-overlay")
@electoral_access_required("ver_camadas_mandato")
def get_mandate_overlay(territory_id):
    if disabled := _feature_required("camadasMandato"):
        return disabled
    tenant_id, user_id = _private_context()
    try:
        snapshot = latest_snapshot(
            tenant_id,
            g.electoral_mandate.id,
            snapshot_id=_uuid_query_argument("snapshot_id"),
            period_start=_date_query_argument("from"),
            period_end=_date_query_argument("to"),
        )
    except ValueError as exc:
        return _validation_error(str(exc))
    if snapshot is None:
        return jsonify(
            error="not_found",
            message="Nenhum snapshot territorial corresponde aos filtros informados.",
        ), 404
    try:
        content = territory_overlay_data(snapshot, territory_id)
    except MandateIntelligenceError as exc:
        return jsonify(error="not_found", message=str(exc)), 404
    add_audit(
        tenant_id,
        user_id,
        "electoral.mandate_overlay.viewed",
        "territory",
        territory_id,
        after={"snapshot_id": str(snapshot.id), "suppressed": content["territory"]["suppressed"]},
    )
    db.session.commit()
    return jsonify(content)


@electoral_bp.get("/electoral/territories/<uuid:territory_id>/briefing")
@electoral_access_required("ver_camadas_mandato")
def get_territory_briefing(territory_id):
    if disabled := _feature_required("camadasMandato"):
        return disabled
    tenant_id, user_id = _private_context()
    try:
        snapshot = latest_snapshot(
            tenant_id,
            g.electoral_mandate.id,
            snapshot_id=_uuid_query_argument("snapshot_id"),
        )
    except ValueError as exc:
        return _validation_error(str(exc))
    if snapshot is None:
        return jsonify(error="not_found", message="Snapshot territorial não encontrado."), 404
    try:
        content = territory_briefing_data(snapshot, territory_id)
    except MandateIntelligenceError as exc:
        return jsonify(error="not_found", message=str(exc)), 404
    add_audit(
        tenant_id,
        user_id,
        "electoral.territory_briefing.viewed",
        "territory",
        territory_id,
        after={"snapshot_id": str(snapshot.id), "suppressed": content["privacy"]["suppressed"]},
    )
    db.session.commit()
    return jsonify(content)


@electoral_bp.get("/electoral/agenda-events/<uuid:event_id>/pre-visit-briefing")
@electoral_access_required("ver_camadas_mandato")
def get_pre_visit_briefing(event_id):
    if disabled := _feature_required("camadasMandato"):
        return disabled
    tenant_id, user_id = _private_context()
    try:
        content = pre_visit_briefing(
            tenant_id,
            g.electoral_mandate.id,
            event_id,
            snapshot_id=_uuid_query_argument("snapshot_id"),
        )
    except (AdvancedFeatureError, ValueError) as exc:
        return _validation_error(str(exc))
    add_audit(tenant_id, user_id, "electoral.pre_visit_briefing.viewed", "agenda_event", event_id)
    db.session.commit()
    return jsonify(content)


@electoral_bp.get("/electoral/mandate-map-layers")
@electoral_access_required("ver_camadas_mandato")
def get_mandate_map_layers():
    if disabled := _feature_required("camadasMandato"):
        return disabled
    tenant_id, user_id = _private_context()
    try:
        content = mandate_map_layers(
            tenant_id,
            g.electoral_mandate.id,
            snapshot_id=_uuid_query_argument("snapshot_id"),
        )
    except (AdvancedFeatureError, ValueError) as exc:
        return _validation_error(str(exc))
    add_audit(
        tenant_id, user_id, "electoral.mandate_map_layers.viewed", "mandate", g.electoral_mandate.id
    )
    db.session.commit()
    return jsonify(content)


@electoral_bp.get("/electoral/agenda-routes")
@electoral_access_required("ver_camadas_mandato")
def get_electoral_agenda_routes():
    if disabled := _feature_required("camadasMandato"):
        return disabled
    try:
        start = date.fromisoformat(str(request.args.get("from") or date.today()))
        end = date.fromisoformat(str(request.args.get("to") or (start + timedelta(days=7))))
    except ValueError:
        return _validation_error("Período inválido.")
    if end < start or (end - start).days > 31:
        return _validation_error("A rota deve cobrir de 1 a 31 dias.")
    tenant_id, user_id = _private_context()
    content = agenda_routes(tenant_id, g.electoral_mandate.id, start, end)
    add_audit(
        tenant_id, user_id, "electoral.agenda_route.viewed", "mandate", g.electoral_mandate.id
    )
    db.session.commit()
    return jsonify(content)


@electoral_bp.get("/electoral/alert-preferences")
@electoral_access_required("ver_camadas_mandato")
def get_alert_preferences():
    if disabled := _feature_required("camadasMandato"):
        return disabled
    tenant_id, user_id = _private_context()
    item = alert_preference(tenant_id, g.electoral_mandate.id, user_id)
    return jsonify(alert_preference_data(item))


@electoral_bp.put("/electoral/alert-preferences")
@electoral_access_required("ver_camadas_mandato")
def put_alert_preferences():
    if disabled := _feature_required("camadasMandato"):
        return disabled
    tenant_id, user_id = _private_context()
    try:
        item = upsert_alert_preference(
            tenant_id,
            g.electoral_mandate.id,
            user_id,
            request.get_json(silent=True) or {},
        )
    except MandateIntelligenceError as exc:
        return _validation_error(str(exc))
    add_audit(
        tenant_id,
        user_id,
        "electoral.alert_preferences.updated",
        "electoral_alert_preference",
        item.id,
        after={
            "enabled": item.enabled,
            "channels": item.channels,
            "frequency": item.frequency,
            "alert_types": item.alert_types,
        },
    )
    db.session.commit()
    return jsonify(alert_preference_data(item))


@electoral_bp.get("/electoral/alerts")
@electoral_access_required("ver_camadas_mandato")
def list_electoral_alerts():
    if disabled := _feature_required("camadasMandato"):
        return disabled
    tenant_id, user_id = _private_context()
    preference = alert_preference(tenant_id, g.electoral_mandate.id, user_id)
    snapshot = latest_snapshot(tenant_id, g.electoral_mandate.id)
    content = alert_feed_data(snapshot, preference)
    add_audit(
        tenant_id,
        user_id,
        "electoral.alerts.viewed",
        "mandate",
        g.electoral_mandate.id,
        after={"snapshot_id": content["snapshot_id"], "count": len(content["content"])},
    )
    db.session.commit()
    return jsonify(content)


@electoral_bp.get("/electoral/alert-deliveries")
@electoral_access_required("ver_camadas_mandato")
def list_electoral_alert_deliveries():
    if disabled := _feature_required("camadasMandato"):
        return disabled
    tenant_id, user_id = _private_context()
    limit = min(100, max(1, request.args.get("limit", 30, type=int)))
    items = list(
        db.session.execute(
            select(ElectoralAlertDelivery)
            .where(
                ElectoralAlertDelivery.tenant_id == tenant_id,
                ElectoralAlertDelivery.mandate_id == g.electoral_mandate.id,
                ElectoralAlertDelivery.user_id == user_id,
            )
            .order_by(ElectoralAlertDelivery.created_at.desc())
            .limit(limit)
        ).scalars()
    )
    return jsonify(content=[alert_delivery_data(item) for item in items])


@electoral_bp.get("/electoral/public-commitments")
@electoral_access_required("ver_camadas_mandato")
def list_public_commitments():
    if disabled := _feature_required("camadasMandato"):
        return disabled
    tenant_id, _ = _private_context()
    statement = select(ElectoralPublicCommitment).where(
        ElectoralPublicCommitment.tenant_id == tenant_id,
        ElectoralPublicCommitment.mandate_id == g.electoral_mandate.id,
    )
    if territory_id := request.args.get("territory_id"):
        try:
            statement = statement.where(
                ElectoralPublicCommitment.territory_id == uuid.UUID(territory_id)
            )
        except ValueError:
            return _validation_error("territory_id inválido.")
    items = list(
        db.session.execute(
            statement.order_by(
                ElectoralPublicCommitment.due_on,
                ElectoralPublicCommitment.created_at.desc(),
            ).limit(200)
        ).scalars()
    )
    if status := request.args.get("status"):
        items = [item for item in items if effective_status(item) == status.upper()]
    territories = list(
        db.session.execute(
            select(Territory)
            .where(Territory.tenant_id == tenant_id, Territory.active.is_(True))
            .order_by(Territory.name)
        ).scalars()
    )
    responsible_users = list(
        db.session.execute(
            select(User)
            .where(User.tenant_id == tenant_id, User.status == UserStatus.ACTIVE)
            .order_by(User.name)
        ).scalars()
    )
    return jsonify(
        content=[commitment_data(item) for item in items],
        can_manage=get_jwt().get("role") == Role.REPRESENTATIVE.value,
        territories=[{"id": str(item.id), "name": item.name} for item in territories],
        responsible_users=[
            {"id": str(item.id), "name": item.name, "role": item.role.value}
            for item in responsible_users
        ],
    )


@electoral_bp.post("/electoral/public-commitments")
@electoral_access_required("ver_camadas_mandato")
def post_public_commitment():
    if disabled := _feature_required("camadasMandato"):
        return disabled
    if denied := _commitment_mutation_required():
        return denied
    tenant_id, user_id = _private_context()
    try:
        item = create_commitment(
            tenant_id,
            g.electoral_mandate.id,
            user_id,
            request.get_json(silent=True) or {},
        )
    except CommitmentError as exc:
        return _validation_error(str(exc))
    add_audit(
        tenant_id,
        user_id,
        "electoral.public_commitment.created",
        "electoral_public_commitment",
        item.id,
        after={"territory_id": str(item.territory_id), "due_on": item.due_on.isoformat()},
    )
    db.session.commit()
    return jsonify(commitment_data(item, include_history=True)), 201


@electoral_bp.get("/electoral/public-commitments/<uuid:commitment_id>")
@electoral_access_required("ver_camadas_mandato")
def get_public_commitment(commitment_id):
    if disabled := _feature_required("camadasMandato"):
        return disabled
    tenant_id, _ = _private_context()
    item = accessible_commitment(tenant_id, g.electoral_mandate.id, commitment_id)
    if item is None:
        return jsonify(error="not_found", message="Compromisso público não encontrado."), 404
    return jsonify(commitment_data(item, include_history=True))


@electoral_bp.patch("/electoral/public-commitments/<uuid:commitment_id>")
@electoral_access_required("ver_camadas_mandato")
def patch_public_commitment(commitment_id):
    if disabled := _feature_required("camadasMandato"):
        return disabled
    if denied := _commitment_mutation_required():
        return denied
    tenant_id, user_id = _private_context()
    item = accessible_commitment(tenant_id, g.electoral_mandate.id, commitment_id)
    if item is None:
        return jsonify(error="not_found", message="Compromisso público não encontrado."), 404
    before = commitment_data(item)
    try:
        update_commitment(item, user_id, request.get_json(silent=True) or {})
    except CommitmentError as exc:
        return _validation_error(str(exc))
    add_audit(
        tenant_id,
        user_id,
        "electoral.public_commitment.updated",
        "electoral_public_commitment",
        item.id,
        before={"status": before["status"], "progress": before["progress"]},
        after={"status": item.status, "progress": item.progress},
    )
    db.session.commit()
    return jsonify(commitment_data(item, include_history=True))


@electoral_bp.post("/electoral/public-commitments/<uuid:commitment_id>/evidence")
@electoral_access_required("ver_camadas_mandato")
def post_public_commitment_evidence(commitment_id):
    if disabled := _feature_required("camadasMandato"):
        return disabled
    if denied := _commitment_mutation_required():
        return denied
    tenant_id, user_id = _private_context()
    item = accessible_commitment(tenant_id, g.electoral_mandate.id, commitment_id)
    if item is None:
        return jsonify(error="not_found", message="Compromisso público não encontrado."), 404
    try:
        evidence = add_evidence(item, user_id, request.get_json(silent=True) or {})
    except CommitmentError as exc:
        return _validation_error(str(exc))
    add_audit(
        tenant_id,
        user_id,
        "electoral.public_commitment.evidence_added",
        "electoral_public_commitment",
        item.id,
        after={
            "evidence_id": str(evidence.id),
            "evidence_date": evidence.evidence_date.isoformat(),
        },
    )
    db.session.commit()
    return jsonify(commitment_data(item, include_history=True)), 201


@electoral_bp.get("/electoral/operational-map")
@electoral_access_required("ver_camadas_mandato")
def get_operational_map():
    if disabled := _feature_required("camadasMandato"):
        return disabled
    tenant_id, user_id = _private_context()
    content = operational_map_data(tenant_id, g.electoral_mandate.id)
    add_audit(
        tenant_id,
        user_id,
        "electoral.operational_map.viewed",
        "mandate",
        g.electoral_mandate.id,
        after={"located_commitments": len(content["features"])},
    )
    db.session.commit()
    return jsonify(content)


@electoral_bp.get("/electoral/candidates")
@electoral_access_required("consultar_dados_publicos")
def search_candidates():
    election_id = _uuid_argument("election_id", required=True)
    if isinstance(election_id, tuple):
        return election_id
    explore = str(request.args.get("explore") or "").lower() == "true"
    if not explore and not _participated_in_election(election_id):
        return _election_scope_error()
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
            "explore": explore,
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
    explore = str(request.args.get("explore") or "").lower() == "true"
    if not explore and not _participated_in_election(election_id):
        return _election_scope_error()
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
    try:
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
    except TerritorialLevelUnavailable as error:
        return _validation_error(str(error), availableLevels=error.available_levels)
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
    explore = str(request.args.get("explore") or "").lower() == "true"
    if not explore and not _participated_in_election(election_id):
        return _election_scope_error()
    level = (request.args.get("level") or "municipality").strip().lower()
    if level not in AVAILABLE_LEVELS:
        return _validation_error(
            "Nivel territorial indisponivel.", availableLevels=list(AVAILABLE_LEVELS)
        )
    municipality_code = (request.args.get("municipalityCode") or "").strip() or None
    tenant_id, user_id = _private_context()
    try:
        content = load_candidate_map(
            candidate_id,
            election_id,
            level,
            municipality_code=municipality_code,
            tenant_id=tenant_id,
            user_id=user_id,
        )
    except TerritorialLevelUnavailable as error:
        return _validation_error(str(error), availableLevels=error.available_levels)
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
    if not _participated_in_election(election_id):
        return _election_scope_error()
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
    if not _participated_in_election(election_id):
        return _election_scope_error()
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


@electoral_bp.get("/electoral/insights")
@electoral_access_required("usar_ia")
def list_insights():
    unavailable = _feature_required("ia")
    if unavailable:
        return unavailable
    tenant_id, user_id = _private_context()
    page = max(1, request.args.get("page", 1, type=int))
    per_page = min(25, max(5, request.args.get("perPage", 10, type=int)))
    analysis_type = str(request.args.get("type") or "").strip().lower()
    status = str(request.args.get("status") or "").strip().upper()
    search = " ".join(str(request.args.get("q") or "").split())[:100]
    if analysis_type and analysis_type not in {"candidate", "comparison", "question"}:
        return _validation_error("Tipo de analise invalido.")
    allowed_statuses = {"QUEUED", "PROCESSING", "COMPLETED", "FAILED", "REFUSED", "HIDDEN"}
    if status and status not in allowed_statuses:
        return _validation_error("Status de analise invalido.")

    filters = [ElectoralInsight.tenant_id == tenant_id]
    if get_jwt().get("role") != Role.REPRESENTATIVE.value:
        filters.append(ElectoralInsight.requested_by_id == user_id)
    if analysis_type:
        filters.append(ElectoralInsight.analysis_type == analysis_type)
    if status:
        filters.append(ElectoralInsight.status == status)
    if search:
        pattern = f"%{search}%"
        filters.append(
            or_(
                cast(ElectoralInsight.request_payload, String).ilike(pattern),
                cast(ElectoralInsight.input_snapshot, String).ilike(pattern),
                cast(ElectoralInsight.facts, String).ilike(pattern),
            )
        )

    statement = select(ElectoralInsight).where(*filters)
    total = db.session.scalar(select(func.count()).select_from(statement.subquery())) or 0
    items = db.session.scalars(
        statement.order_by(ElectoralInsight.requested_at.desc())
        .offset((page - 1) * per_page)
        .limit(per_page)
    )
    return jsonify(
        content=[insight_data(item) for item in items],
        page=page,
        perPage=per_page,
        total=total,
        totalPages=max(1, (total + per_page - 1) // per_page),
    )


@electoral_bp.post("/electoral/insights")
@electoral_access_required("usar_ia")
def create_insight():
    unavailable = _feature_required("ia")
    if unavailable:
        return unavailable
    payload = request.get_json(silent=True) or {}
    analysis_type = str(payload.get("type") or "").strip().lower()
    if analysis_type not in {"candidate", "comparison", "question"}:
        return _validation_error("type deve ser candidate, comparison ou question.")
    question = " ".join(str(payload.get("question") or "").split())
    if analysis_type == "question" and not 10 <= len(question) <= 1000:
        return _validation_error("A pergunta deve ter entre 10 e 1000 caracteres.")
    raw_ids = payload.get("candidate_ids") or []
    expected = (
        (1, 1)
        if analysis_type == "candidate"
        else (2, 5)
        if analysis_type == "comparison"
        else (1, 5)
    )
    if not isinstance(raw_ids, list) or not expected[0] <= len(raw_ids) <= expected[1]:
        return _validation_error("Quantidade de candidaturas invalida para o tipo de insight.")
    try:
        candidate_ids = [uuid.UUID(str(value)) for value in raw_ids]
        election_id = uuid.UUID(str(payload.get("election_id") or ""))
    except (TypeError, ValueError):
        return _validation_error("Eleicao e candidaturas devem possuir UUIDs validos.")
    if not _participated_in_election(election_id):
        return _election_scope_error()
    if len(set(candidate_ids)) != len(candidate_ids):
        return _validation_error("Nao repita candidaturas no insight.")
    reference_candidate_id = None
    if analysis_type == "question":
        try:
            reference_candidate_id = uuid.UUID(
                str(payload.get("reference_candidate_id") or candidate_ids[0])
            )
        except (TypeError, ValueError):
            return _validation_error("A candidatura de referencia deve possuir UUID valido.")
        if reference_candidate_id not in candidate_ids:
            return _validation_error(
                "A candidatura de referencia deve estar entre as candidaturas selecionadas."
            )
    level = str(payload.get("level") or "municipality").strip().lower()
    if level not in AVAILABLE_LEVELS:
        return _validation_error(
            "Nivel territorial indisponivel.", availableLevels=list(AVAILABLE_LEVELS)
        )
    municipality_code = str(payload.get("municipality_code") or "").strip() or None
    tenant_id, user_id = _private_context()
    safety = assess_electoral_question(question) if analysis_type == "question" else None
    if safety and not safety.allowed:
        insight = ElectoralInsight(
            tenant_id=tenant_id,
            mandate_id=g.electoral_mandate.id,
            requested_by_id=user_id,
            analysis_type="question",
            status="REFUSED",
            review_status="NOT_REQUIRED",
            request_payload={
                "question_hash": safety.prompt_hash,
                "question_length": safety.prompt_length,
            },
            safety_classification=safety.audit_data(),
            model_provider=MODEL_PROVIDER,
            model_name=QUESTION_MODEL_NAME,
            prompt_version=QUESTION_PROMPT_VERSION,
            refusal_reason=safety.reason,
            limitations=[safety.reason],
            completed_at=datetime.now(UTC),
        )
        db.session.add(insight)
        db.session.flush()
        add_audit(
            tenant_id,
            user_id,
            "electoral.insight.question_refused",
            "electoral_insight",
            insight.id,
            after=safety.audit_data(),
        )
        db.session.commit()
        return jsonify(insight_data(insight)), 200

    effective_type = (
        "candidate"
        if analysis_type == "question" and len(candidate_ids) == 1
        else "comparison"
        if analysis_type == "question"
        else analysis_type
    )
    if effective_type == "candidate":
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
            candidate_ids, election_id, level, municipality_code=municipality_code
        )
    if error:
        return _validation_error(error)

    auditable_request = {
        "election_id": str(election_id),
        "candidate_ids": [str(value) for value in candidate_ids],
        "level": level,
        "municipality_code": municipality_code,
        "dataset_version": analysis.get("dataset_version"),
        **(
            {"reference_candidate_id": str(reference_candidate_id)}
            if reference_candidate_id
            else {}
        ),
        **(
            {
                "question": question,
                "question_hash": safety.prompt_hash,
                "question_length": safety.prompt_length,
                "requester_role": get_jwt().get("role"),
            }
            if safety
            else {}
        ),
    }
    ai_runtime = electoral_ai_runtime()
    requested_provider = (
        ai_runtime["provider"] if ai_runtime["mode"] == "GENERATIVE" else MODEL_PROVIDER
    )
    requested_model = (
        ai_runtime["model"]
        if ai_runtime["mode"] == "GENERATIVE"
        else QUESTION_MODEL_NAME
        if safety
        else MODEL_NAME
    )
    requested_prompt = (
        ai_runtime["promptVersion"]
        if ai_runtime["mode"] == "GENERATIVE"
        else QUESTION_PROMPT_VERSION
        if safety
        else PROMPT_VERSION
    )
    insight = ElectoralInsight(
        tenant_id=tenant_id,
        mandate_id=g.electoral_mandate.id,
        requested_by_id=user_id,
        analysis_type=analysis_type,
        request_payload=auditable_request,
        model_provider=requested_provider,
        safety_classification=(
            safety.audit_data()
            if safety
            else {
                "allowed": True,
                "category": None,
                "policyVersion": ELECTORAL_SAFETY_POLICY_VERSION,
            }
        ),
        model_name=requested_model,
        prompt_version=requested_prompt,
    )
    db.session.add(insight)
    db.session.flush()
    db.session.add(
        OutboxEvent(
            tenant_id=tenant_id,
            event_type=INSIGHT_EVENT,
            aggregate_type="electoral_insight",
            aggregate_id=str(insight.id),
            payload={
                "insightId": str(insight.id),
                "requestedById": str(user_id),
                "schemaVersion": 1,
                "idempotencyKey": str(insight.id),
            },
        )
    )
    add_audit(
        tenant_id,
        user_id,
        "electoral.insight.requested",
        "electoral_insight",
        insight.id,
        after={
            "analysisType": analysis_type,
            "candidateCount": len(candidate_ids),
            "datasetVersion": analysis.get("dataset_version"),
            "modelVersion": requested_model,
            "modelProvider": requested_provider,
            "questionHash": safety.prompt_hash if safety else None,
            "safetyPolicyVersion": ELECTORAL_SAFETY_POLICY_VERSION,
        },
    )
    db.session.commit()
    return jsonify(insight_data(insight)), 202


@electoral_bp.get("/electoral/insights/review-queue")
@electoral_access_required("usar_ia")
def list_insight_review_queue():
    unavailable = _feature_required("ia")
    if unavailable:
        return unavailable
    if get_jwt().get("role") != Role.REPRESENTATIVE.value:
        return (
            jsonify(
                error="representative_required",
                message="Revisao reservada ao parlamentar.",
            ),
            403,
        )
    tenant_id, _ = _private_context()
    items = db.session.scalars(
        select(ElectoralInsight)
        .where(
            ElectoralInsight.tenant_id == tenant_id,
            ElectoralInsight.review_status == "PENDING",
            ElectoralInsight.status.in_({"COMPLETED", "HIDDEN"}),
        )
        .order_by(ElectoralInsight.requested_at)
        .limit(100)
    )
    return jsonify(content=[insight_data(item) for item in items])


@electoral_bp.post("/electoral/insights/<uuid:insight_id>/review")
@electoral_access_required("usar_ia")
def review_electoral_insight(insight_id):
    unavailable = _feature_required("ia")
    if unavailable:
        return unavailable
    if get_jwt().get("role") != Role.REPRESENTATIVE.value:
        return (
            jsonify(
                error="representative_required",
                message="Revisao reservada ao parlamentar.",
            ),
            403,
        )
    tenant_id, user_id = _private_context()
    insight = accessible_insight(
        insight_id,
        tenant_id,
        user_id,
        representative=True,
    )
    if insight is None:
        return jsonify(error="not_found", message="Insight nao encontrado."), 404
    if insight.status not in {"COMPLETED", "HIDDEN"}:
        return _validation_error("Este insight nao esta disponivel para revisao.")
    payload = request.get_json(silent=True) or {}
    decision = str(payload.get("decision") or "").strip().upper()
    notes = " ".join(str(payload.get("notes") or "").split())
    if decision not in {"APPROVE", "REJECT", "RESTORE"}:
        return _validation_error("decision deve ser APPROVE, REJECT ou RESTORE.")
    if len(notes) < 5 or len(notes) > 1000:
        return _validation_error("Informe uma justificativa entre 5 e 1000 caracteres.")
    try:
        review_insight(insight, user_id, decision, notes)
    except ValueError as error:
        return _validation_error(str(error))
    db.session.commit()
    return jsonify(insight_data(insight))


@electoral_bp.get("/electoral/insights/<uuid:insight_id>")
@electoral_access_required("usar_ia")
def get_insight(insight_id):
    unavailable = _feature_required("ia")
    if unavailable:
        return unavailable
    tenant_id, user_id = _private_context()
    item = accessible_insight(
        insight_id,
        tenant_id,
        user_id,
        representative=get_jwt().get("role") == Role.REPRESENTATIVE.value,
    )
    if item is None:
        return jsonify(error="not_found", message="Insight nao encontrado."), 404
    return jsonify(insight_data(item))


@electoral_bp.post("/electoral/insights/<uuid:insight_id>/feedback")
@electoral_access_required("usar_ia")
def create_insight_feedback(insight_id):
    unavailable = _feature_required("ia")
    if unavailable:
        return unavailable
    tenant_id, user_id = _private_context()
    insight = accessible_insight(
        insight_id,
        tenant_id,
        user_id,
        representative=get_jwt().get("role") == Role.REPRESENTATIVE.value,
    )
    if insight is None:
        return jsonify(error="not_found", message="Insight nao encontrado."), 404
    if insight.status not in {"COMPLETED", "HIDDEN"}:
        return _validation_error("Somente insights concluidos recebem feedback.")
    payload = request.get_json(silent=True) or {}
    rating = str(payload.get("rating") or "").strip().upper()
    reason = str(payload.get("reason") or "").strip() or None
    comment = str(payload.get("comment") or "").strip() or None
    if rating not in {"ACCEPTED", "DISCARDED", "CONTESTED"}:
        return _validation_error("rating deve ser ACCEPTED, DISCARDED ou CONTESTED.")
    if reason and len(reason) > 160 or comment and len(comment) > 1000:
        return _validation_error("Motivo ou comentario excede o limite permitido.")
    feedback = record_feedback(insight, user_id, rating, reason, comment)
    db.session.commit()
    return jsonify(
        id=str(feedback.id),
        insight_id=str(insight.id),
        rating=feedback.rating,
        hidden=insight.status == "HIDDEN",
        model_version=feedback.model_version,
        created_at=feedback.created_at.isoformat(),
    ), 201


@electoral_bp.get("/electoral/scenarios")
@electoral_access_required("criar_cenario")
def list_scenarios():
    unavailable = _feature_required("cenarios")
    if unavailable:
        return unavailable
    tenant_id, user_id = _private_context()
    statement = select(ElectoralScenario).where(ElectoralScenario.tenant_id == tenant_id)
    if get_jwt().get("role") != Role.REPRESENTATIVE.value:
        statement = statement.where(ElectoralScenario.created_by_id == user_id)
    items = db.session.scalars(statement.order_by(ElectoralScenario.created_at.desc()).limit(50))
    return jsonify(content=[scenario_data(item) for item in items])


@electoral_bp.post("/electoral/scenarios/preview")
@electoral_access_required("criar_cenario")
def preview_scenario():
    unavailable = _feature_required("cenarios")
    if unavailable:
        return unavailable
    payload = request.get_json(silent=True) or {}
    try:
        election_id, candidate_id, level, assumptions, baseline, result = _build_scenario_request(
            payload
        )
    except ScenarioValidationError as error:
        return _validation_error(str(error))
    tenant_id, user_id = _private_context()
    add_audit(
        tenant_id,
        user_id,
        "electoral.scenario.previewed",
        "mandate",
        g.electoral_mandate.id,
        after={
            "baselineElectionId": str(election_id),
            "candidateId": str(candidate_id),
            "level": level,
            "datasetVersion": baseline["dataset_version"],
            "assumptionCount": len(assumptions),
            "methodologyVersion": SCENARIO_METHODOLOGY_VERSION,
        },
    )
    db.session.commit()
    return jsonify(
        simulation=True,
        persisted=False,
        candidate=baseline["candidate"],
        baseline={
            "election_id": str(election_id),
            "candidate_id": str(candidate_id),
            "level": level,
            "dataset_version": baseline["dataset_version"],
            "source": baseline["source"],
            "source_hash": baseline["source_hash"],
        },
        assumptions=assumptions,
        result=result,
        methodology_version=SCENARIO_METHODOLOGY_VERSION,
        disclaimer=SCENARIO_DISCLAIMER,
    )


@electoral_bp.post("/electoral/scenarios/compare")
@electoral_access_required("criar_cenario")
def create_scenario_comparison():
    unavailable = _feature_required("cenarios")
    if unavailable:
        return unavailable
    payload = request.get_json(silent=True) or {}
    raw_ids = payload.get("scenario_ids")
    if not isinstance(raw_ids, list) or not 2 <= len(raw_ids) <= 5:
        return _validation_error("Informe entre 2 e 5 cenarios para comparacao.")
    try:
        scenario_ids = [uuid.UUID(str(value)) for value in raw_ids]
    except (TypeError, ValueError):
        return _validation_error("Todos os cenarios devem possuir UUIDs validos.")
    if len(set(scenario_ids)) != len(scenario_ids):
        return _validation_error("Nao repita cenarios na comparacao.")
    tenant_id, user_id = _private_context()
    statement = select(ElectoralScenario).where(
        ElectoralScenario.tenant_id == tenant_id,
        ElectoralScenario.id.in_(scenario_ids),
    )
    if get_jwt().get("role") != Role.REPRESENTATIVE.value:
        statement = statement.where(ElectoralScenario.created_by_id == user_id)
    found = {item.id: item for item in db.session.scalars(statement)}
    if len(found) != len(scenario_ids):
        return jsonify(error="not_found", message="Um ou mais cenarios nao foram encontrados."), 404
    scenarios = [found[item_id] for item_id in scenario_ids]
    try:
        result = compare_scenarios(scenarios)
    except ScenarioValidationError as error:
        return _validation_error(str(error))
    analysis = ElectoralScenarioAnalysis(
        tenant_id=tenant_id,
        mandate_id=g.electoral_mandate.id,
        created_by_id=user_id,
        analysis_type="COMPARISON",
        anchor_scenario_id=scenarios[0].id,
        scenario_ids=[str(item.id) for item in scenarios],
        parameters={},
        result=result,
        methodology_version=SCENARIO_METHODOLOGY_VERSION,
    )
    db.session.add(analysis)
    db.session.flush()
    add_audit(
        tenant_id,
        user_id,
        "electoral.scenario.compared",
        "electoral_scenario_analysis",
        analysis.id,
        after={"scenarioIds": analysis.scenario_ids},
    )
    db.session.commit()
    return jsonify(analysis_data(analysis)), 201


@electoral_bp.get("/electoral/scenarios/shared/<token>")
@electoral_access_required("consultar_dados_publicos")
def get_shared_scenario(token):
    unavailable = _feature_required("cenarios")
    if unavailable:
        return unavailable
    tenant_id, user_id = _private_context()
    share = db.session.execute(
        select(ElectoralScenarioShare).where(
            ElectoralScenarioShare.tenant_id == tenant_id,
            ElectoralScenarioShare.token_hash == hash_share_token(token),
        )
    ).scalar_one_or_none()
    now = datetime.now(UTC)
    if share is None:
        return jsonify(error="not_found", message="Compartilhamento nao encontrado."), 404
    expires_at = share.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=UTC)
    if share.revoked_at is not None or expires_at <= now:
        return jsonify(error="share_unavailable", message="Link revogado ou expirado."), 410
    scenario = db.session.execute(
        select(ElectoralScenario).where(
            ElectoralScenario.tenant_id == tenant_id,
            ElectoralScenario.id == share.scenario_id,
        )
    ).scalar_one_or_none()
    if scenario is None:
        return jsonify(error="not_found", message="Cenario nao encontrado."), 404
    share.access_count += 1
    share.last_accessed_at = now
    add_audit(
        tenant_id,
        user_id,
        "electoral.scenario.share_accessed",
        "electoral_scenario_share",
        share.id,
        after={"scenarioId": str(scenario.id), "readOnly": True},
    )
    db.session.commit()
    return jsonify(scenario_data(scenario, read_only=True))


@electoral_bp.post("/electoral/scenarios")
@electoral_access_required("criar_cenario")
def create_scenario():
    unavailable = _feature_required("cenarios")
    if unavailable:
        return unavailable
    payload = request.get_json(silent=True) or {}
    name = str(payload.get("name") or "").strip()
    if not name or len(name) > 160:
        return _validation_error("Nome do cenario e obrigatorio e deve ter ate 160 caracteres.")
    try:
        election_id, candidate_id, level, assumptions, baseline, result = _build_scenario_request(
            payload
        )
    except ScenarioValidationError as error:
        return _validation_error(str(error))
    tenant_id, user_id = _private_context()
    item = ElectoralScenario(
        tenant_id=tenant_id,
        mandate_id=g.electoral_mandate.id,
        created_by_id=user_id,
        name=name,
        baseline_election_id=election_id,
        candidate_id=candidate_id,
        level=level,
        assumptions=assumptions,
        baseline_snapshot=baseline,
        result=result,
        methodology_version=SCENARIO_METHODOLOGY_VERSION,
        disclaimer=SCENARIO_DISCLAIMER,
    )
    db.session.add(item)
    db.session.flush()
    add_audit(
        tenant_id,
        user_id,
        "electoral.scenario.created",
        "electoral_scenario",
        item.id,
        after={
            "baselineElectionId": str(election_id),
            "candidateId": str(candidate_id),
            "datasetVersion": baseline["dataset_version"],
            "assumptionCount": len(assumptions),
            "methodologyVersion": SCENARIO_METHODOLOGY_VERSION,
        },
    )
    db.session.commit()
    return jsonify(scenario_data(item)), 201


def _build_scenario_request(payload: dict) -> tuple:
    try:
        election_id = uuid.UUID(str(payload.get("baseline_election_id") or ""))
        candidate_id = uuid.UUID(str(payload.get("candidate_id") or ""))
    except (TypeError, ValueError) as error:
        raise ScenarioValidationError(
            "Eleicao-base e candidatura devem possuir UUIDs validos."
        ) from error
    if not _participated_in_election(election_id):
        raise ScenarioValidationError(
            "A eleicao-base nao pertence as participacoes confirmadas do parlamentar."
        )
    level = str(payload.get("level") or "municipality").strip().lower()
    if level not in AVAILABLE_LEVELS:
        raise ScenarioValidationError(
            f"Nivel territorial indisponivel. Use: {', '.join(AVAILABLE_LEVELS)}."
        )
    municipality_code = str(payload.get("municipality_code") or "").strip() or None
    assumptions, baseline, result = build_scenario(
        candidate_id,
        election_id,
        level,
        payload.get("assumptions"),
        municipality_code=municipality_code,
    )
    return election_id, candidate_id, level, assumptions, baseline, result


@electoral_bp.get("/electoral/scenarios/<uuid:scenario_id>")
@electoral_access_required("criar_cenario")
def get_scenario(scenario_id):
    unavailable = _feature_required("cenarios")
    if unavailable:
        return unavailable
    tenant_id, user_id = _private_context()
    statement = select(ElectoralScenario).where(
        ElectoralScenario.id == scenario_id,
        ElectoralScenario.tenant_id == tenant_id,
    )
    if get_jwt().get("role") != Role.REPRESENTATIVE.value:
        statement = statement.where(ElectoralScenario.created_by_id == user_id)
    item = db.session.execute(statement).scalar_one_or_none()
    if item is None:
        return jsonify(error="not_found", message="Cenario nao encontrado."), 404
    return jsonify(scenario_data(item))


@electoral_bp.post("/electoral/scenarios/<uuid:scenario_id>/copy")
@electoral_access_required("criar_cenario")
def copy_scenario(scenario_id):
    unavailable = _feature_required("cenarios")
    if unavailable:
        return unavailable
    source = _accessible_scenario(scenario_id)
    if source is None:
        return jsonify(error="not_found", message="Cenario nao encontrado."), 404
    payload = request.get_json(silent=True) or {}
    name = str(payload.get("name") or f"{source.name} - copia").strip()
    if not name or len(name) > 160:
        return _validation_error("Nome da copia deve ter ate 160 caracteres.")
    assumptions_payload = payload.get("assumptions")
    try:
        assumptions, result = build_from_snapshot(
            source.baseline_snapshot,
            source.assumptions if assumptions_payload is None else assumptions_payload,
        )
    except ScenarioValidationError as error:
        return _validation_error(str(error))
    tenant_id, user_id = _private_context()
    item = ElectoralScenario(
        tenant_id=tenant_id,
        mandate_id=g.electoral_mandate.id,
        created_by_id=user_id,
        source_scenario_id=source.id,
        name=name,
        baseline_election_id=source.baseline_election_id,
        candidate_id=source.candidate_id,
        level=source.level,
        assumptions=assumptions,
        baseline_snapshot=source.baseline_snapshot,
        result=result,
        methodology_version=SCENARIO_METHODOLOGY_VERSION,
        disclaimer=SCENARIO_DISCLAIMER,
    )
    db.session.add(item)
    db.session.flush()
    add_audit(
        tenant_id,
        user_id,
        "electoral.scenario.copied",
        "electoral_scenario",
        item.id,
        after={"sourceScenarioId": str(source.id), "assumptionCount": len(assumptions)},
    )
    db.session.commit()
    return jsonify(scenario_data(item)), 201


@electoral_bp.post("/electoral/scenarios/<uuid:scenario_id>/share")
@electoral_access_required("criar_cenario")
def share_scenario(scenario_id):
    unavailable = _feature_required("cenarios")
    if unavailable:
        return unavailable
    scenario = _accessible_scenario(scenario_id)
    if scenario is None:
        return jsonify(error="not_found", message="Cenario nao encontrado."), 404
    payload = request.get_json(silent=True) or {}
    try:
        expires_in_days = int(payload.get("expires_in_days", 7))
    except (TypeError, ValueError):
        return _validation_error("expires_in_days deve ser inteiro.")
    if not 1 <= expires_in_days <= 30:
        return _validation_error("expires_in_days deve estar entre 1 e 30.")
    tenant_id, user_id = _private_context()
    token, token_hash = new_share_token()
    share = ElectoralScenarioShare(
        tenant_id=tenant_id,
        scenario_id=scenario.id,
        created_by_id=user_id,
        token_hash=token_hash,
        expires_at=datetime.now(UTC) + timedelta(days=expires_in_days),
    )
    db.session.add(share)
    db.session.flush()
    add_audit(
        tenant_id,
        user_id,
        "electoral.scenario.shared",
        "electoral_scenario_share",
        share.id,
        after={"scenarioId": str(scenario.id), "expiresAt": share.expires_at.isoformat()},
    )
    db.session.commit()
    path = f"/inteligencia-eleitoral/cenarios/compartilhado/{token}"
    return jsonify(
        id=str(share.id),
        scenario_id=str(scenario.id),
        read_only=True,
        expires_at=share.expires_at.isoformat(),
        url=f"{request.host_url.rstrip('/')}{path}",
    ), 201


@electoral_bp.get("/electoral/scenarios/<uuid:scenario_id>/shares")
@electoral_access_required("criar_cenario")
def list_scenario_shares(scenario_id):
    unavailable = _feature_required("cenarios")
    if unavailable:
        return unavailable
    scenario = _accessible_scenario(scenario_id)
    if scenario is None:
        return jsonify(error="not_found", message="Cenario nao encontrado."), 404
    tenant_id, user_id = _private_context()
    statement = select(ElectoralScenarioShare).where(
        ElectoralScenarioShare.scenario_id == scenario.id,
        ElectoralScenarioShare.tenant_id == tenant_id,
    )
    if get_jwt().get("role") != Role.REPRESENTATIVE.value:
        statement = statement.where(ElectoralScenarioShare.created_by_id == user_id)
    items = db.session.scalars(statement.order_by(ElectoralScenarioShare.created_at.desc()))
    return jsonify(content=[share_data(item) for item in items])


@electoral_bp.delete("/electoral/scenarios/<uuid:scenario_id>/shares/<uuid:share_id>")
@electoral_access_required("criar_cenario")
def revoke_scenario_share(scenario_id, share_id):
    unavailable = _feature_required("cenarios")
    if unavailable:
        return unavailable
    scenario = _accessible_scenario(scenario_id)
    if scenario is None:
        return jsonify(error="not_found", message="Cenario nao encontrado."), 404
    tenant_id, user_id = _private_context()
    statement = select(ElectoralScenarioShare).where(
        ElectoralScenarioShare.id == share_id,
        ElectoralScenarioShare.scenario_id == scenario.id,
        ElectoralScenarioShare.tenant_id == tenant_id,
    )
    if get_jwt().get("role") != Role.REPRESENTATIVE.value:
        statement = statement.where(ElectoralScenarioShare.created_by_id == user_id)
    share = db.session.execute(statement).scalar_one_or_none()
    if share is None:
        return jsonify(error="not_found", message="Compartilhamento nao encontrado."), 404
    if share.revoked_at is None:
        share.revoked_at = datetime.now(UTC)
        add_audit(
            tenant_id,
            user_id,
            "electoral.scenario.share_revoked",
            "electoral_scenario_share",
            share.id,
            after={"scenarioId": str(scenario.id)},
        )
        db.session.commit()
    return "", 204


@electoral_bp.post("/electoral/scenarios/<uuid:scenario_id>/sensitivity")
@electoral_access_required("criar_cenario")
def create_scenario_sensitivity(scenario_id):
    unavailable = _feature_required("cenarios")
    if unavailable:
        return unavailable
    scenario = _accessible_scenario(scenario_id)
    if scenario is None:
        return jsonify(error="not_found", message="Cenario nao encontrado."), 404
    payload = request.get_json(silent=True) or {}
    try:
        share_range = float(payload.get("candidate_share_range_pp", 5)) / 100
        denominator_range = float(payload.get("denominator_range_percent", 5)) / 100
        steps = int(payload.get("steps", 5))
        result = sensitivity_analysis(scenario, share_range, denominator_range, steps)
    except (TypeError, ValueError, ScenarioValidationError) as error:
        return _validation_error(str(error))
    tenant_id, user_id = _private_context()
    analysis = ElectoralScenarioAnalysis(
        tenant_id=tenant_id,
        mandate_id=g.electoral_mandate.id,
        created_by_id=user_id,
        analysis_type="SENSITIVITY",
        anchor_scenario_id=scenario.id,
        scenario_ids=[str(scenario.id)],
        parameters=result["parameters"],
        result=result,
        methodology_version=SCENARIO_METHODOLOGY_VERSION,
    )
    db.session.add(analysis)
    db.session.flush()
    add_audit(
        tenant_id,
        user_id,
        "electoral.scenario.sensitivity_created",
        "electoral_scenario_analysis",
        analysis.id,
        after={"scenarioId": str(scenario.id), **result["parameters"]},
    )
    db.session.commit()
    return jsonify(analysis_data(analysis)), 201


@electoral_bp.get("/electoral/scenario-analyses/<uuid:analysis_id>")
@electoral_access_required("criar_cenario")
def get_scenario_analysis(analysis_id):
    unavailable = _feature_required("cenarios")
    if unavailable:
        return unavailable
    tenant_id, user_id = _private_context()
    statement = select(ElectoralScenarioAnalysis).where(
        ElectoralScenarioAnalysis.id == analysis_id,
        ElectoralScenarioAnalysis.tenant_id == tenant_id,
    )
    if get_jwt().get("role") != Role.REPRESENTATIVE.value:
        statement = statement.where(ElectoralScenarioAnalysis.created_by_id == user_id)
    item = db.session.execute(statement).scalar_one_or_none()
    if item is None:
        return jsonify(error="not_found", message="Analise de cenario nao encontrada."), 404
    return jsonify(analysis_data(item))


def _accessible_scenario(scenario_id):
    tenant_id, user_id = _private_context()
    statement = select(ElectoralScenario).where(
        ElectoralScenario.id == scenario_id,
        ElectoralScenario.tenant_id == tenant_id,
    )
    if get_jwt().get("role") != Role.REPRESENTATIVE.value:
        statement = statement.where(ElectoralScenario.created_by_id == user_id)
    return db.session.execute(statement).scalar_one_or_none()


@electoral_bp.get("/electoral/scenario-portfolios")
@electoral_access_required("criar_cenario")
def list_scenario_portfolios():
    unavailable = _feature_required("cenarios")
    if unavailable:
        return unavailable
    tenant_id, user_id = _private_context()
    statement = select(ElectoralScenarioPortfolio).where(
        ElectoralScenarioPortfolio.tenant_id == tenant_id
    )
    if get_jwt().get("role") != Role.REPRESENTATIVE.value:
        statement = statement.where(ElectoralScenarioPortfolio.created_by_id == user_id)
    items = db.session.scalars(
        statement.order_by(ElectoralScenarioPortfolio.updated_at.desc()).limit(50)
    )
    return jsonify(content=[portfolio_data(item) for item in items])


@electoral_bp.post("/electoral/scenario-portfolios")
@electoral_access_required("criar_cenario")
def create_scenario_portfolio():
    unavailable = _feature_required("cenarios")
    if unavailable:
        return unavailable
    payload = request.get_json(silent=True) or {}
    name = str(payload.get("name") or "").strip()
    description = str(payload.get("description") or "").strip() or None
    if not name or len(name) > 160 or description and len(description) > 1000:
        return _validation_error("Nome e obrigatorio; descricao deve ter ate 1000 caracteres.")
    raw_ids = payload.get("scenario_ids") or []
    if not isinstance(raw_ids, list) or len(raw_ids) > PORTFOLIO_MAX_SCENARIOS:
        return _validation_error(
            f"O portfolio aceita no maximo {PORTFOLIO_MAX_SCENARIOS} cenarios."
        )
    try:
        scenario_ids = [uuid.UUID(str(value)) for value in raw_ids]
    except (TypeError, ValueError):
        return _validation_error("Cenarios devem possuir UUIDs validos.")
    if len(set(scenario_ids)) != len(scenario_ids):
        return _validation_error("Nao repita cenarios no portfolio.")
    scenarios = []
    try:
        for scenario_id in scenario_ids:
            scenario = _accessible_scenario(scenario_id)
            if scenario is None:
                return jsonify(error="not_found", message="Cenario nao encontrado."), 404
            ensure_portfolio_compatible(scenarios, scenario)
            scenarios.append(scenario)
    except PortfolioValidationError as error:
        return _validation_error(str(error))
    tenant_id, user_id = _private_context()
    item = ElectoralScenarioPortfolio(
        tenant_id=tenant_id,
        mandate_id=g.electoral_mandate.id,
        created_by_id=user_id,
        name=name,
        description=description,
        goals=[],
        reference_scenario_id=scenarios[0].id if scenarios else None,
    )
    db.session.add(item)
    db.session.flush()
    for position, scenario in enumerate(scenarios):
        db.session.add(
            ElectoralScenarioPortfolioItem(
                tenant_id=tenant_id,
                portfolio_id=item.id,
                scenario_id=scenario.id,
                added_by_id=user_id,
                position=position,
            )
        )
    record_portfolio_event(
        item,
        user_id,
        "CREATED",
        {"scenarioIds": [str(value) for value in scenario_ids]},
    )
    add_audit(
        tenant_id,
        user_id,
        "electoral.scenario_portfolio.created",
        "electoral_scenario_portfolio",
        item.id,
        after={"scenarioCount": len(scenarios)},
    )
    db.session.commit()
    return jsonify(portfolio_data(item, include_evaluation=True)), 201


@electoral_bp.get("/electoral/scenario-portfolios/<uuid:portfolio_id>")
@electoral_access_required("criar_cenario")
def get_scenario_portfolio(portfolio_id):
    unavailable = _feature_required("cenarios")
    if unavailable:
        return unavailable
    item = _accessible_portfolio(portfolio_id)
    if item is None:
        return jsonify(error="not_found", message="Portfolio nao encontrado."), 404
    return jsonify(portfolio_data(item, include_evaluation=True))


@electoral_bp.patch("/electoral/scenario-portfolios/<uuid:portfolio_id>")
@electoral_access_required("criar_cenario")
def update_scenario_portfolio(portfolio_id):
    unavailable = _feature_required("cenarios")
    if unavailable:
        return unavailable
    item = _accessible_portfolio(portfolio_id)
    if item is None:
        return jsonify(error="not_found", message="Portfolio nao encontrado."), 404
    payload = request.get_json(silent=True) or {}
    name = str(payload.get("name", item.name)).strip()
    description = str(payload.get("description", item.description or "")).strip() or None
    status = str(payload.get("status", item.status)).strip().upper()
    if not name or len(name) > 160 or description and len(description) > 1000:
        return _validation_error("Nome e obrigatorio; descricao deve ter ate 1000 caracteres.")
    if status not in {"ACTIVE", "ARCHIVED"}:
        return _validation_error("status deve ser ACTIVE ou ARCHIVED.")
    before = {"name": item.name, "description": item.description, "status": item.status}
    item.name, item.description, item.status = name, description, status
    tenant_id, user_id = _private_context()
    record_portfolio_event(item, user_id, "UPDATED", {"before": before, "status": status})
    add_audit(
        tenant_id,
        user_id,
        "electoral.scenario_portfolio.updated",
        "electoral_scenario_portfolio",
        item.id,
        before=before,
        after={"name": name, "status": status},
    )
    db.session.commit()
    return jsonify(portfolio_data(item, include_evaluation=True))


@electoral_bp.post("/electoral/scenario-portfolios/<uuid:portfolio_id>/scenarios")
@electoral_access_required("criar_cenario")
def add_scenario_to_portfolio(portfolio_id):
    unavailable = _feature_required("cenarios")
    if unavailable:
        return unavailable
    portfolio = _accessible_portfolio(portfolio_id)
    if portfolio is None:
        return jsonify(error="not_found", message="Portfolio nao encontrado."), 404
    if portfolio.status != "ACTIVE":
        return _validation_error("Portfolio arquivado nao pode ser alterado.")
    payload = request.get_json(silent=True) or {}
    try:
        scenario_id = uuid.UUID(str(payload.get("scenario_id") or ""))
    except (TypeError, ValueError):
        return _validation_error("scenario_id deve possuir UUID valido.")
    scenario = _accessible_scenario(scenario_id)
    if scenario is None:
        return jsonify(error="not_found", message="Cenario nao encontrado."), 404
    entries = portfolio_scenarios(portfolio)
    if len(entries) >= PORTFOLIO_MAX_SCENARIOS:
        return _validation_error(
            f"O portfolio aceita no maximo {PORTFOLIO_MAX_SCENARIOS} cenarios."
        )
    try:
        ensure_portfolio_compatible([item for _, item in entries], scenario)
    except PortfolioValidationError as error:
        return _validation_error(str(error))
    tenant_id, user_id = _private_context()
    membership = db.session.execute(
        select(ElectoralScenarioPortfolioItem).where(
            ElectoralScenarioPortfolioItem.tenant_id == tenant_id,
            ElectoralScenarioPortfolioItem.portfolio_id == portfolio.id,
            ElectoralScenarioPortfolioItem.scenario_id == scenario.id,
        )
    ).scalar_one_or_none()
    label = str(payload.get("label") or "").strip() or None
    if label and len(label) > 160:
        return _validation_error("Rotulo deve ter ate 160 caracteres.")
    if membership and membership.removed_at is None:
        return _validation_error("Cenario ja pertence ao portfolio.")
    if membership:
        membership.removed_at = None
        membership.removed_by_id = None
        membership.added_by_id = user_id
        membership.label = label
        membership.position = len(entries)
        membership.added_at = datetime.now(UTC)
    else:
        db.session.add(
            ElectoralScenarioPortfolioItem(
                tenant_id=tenant_id,
                portfolio_id=portfolio.id,
                scenario_id=scenario.id,
                added_by_id=user_id,
                label=label,
                position=len(entries),
            )
        )
    if portfolio.reference_scenario_id is None:
        portfolio.reference_scenario_id = scenario.id
    portfolio.updated_at = datetime.now(UTC)
    record_portfolio_event(
        portfolio, user_id, "SCENARIO_ADDED", {"scenarioId": str(scenario.id), "label": label}
    )
    add_audit(
        tenant_id,
        user_id,
        "electoral.scenario_portfolio.scenario_added",
        "electoral_scenario_portfolio",
        portfolio.id,
        after={"scenarioId": str(scenario.id)},
    )
    db.session.commit()
    return jsonify(portfolio_data(portfolio, include_evaluation=True)), 201


@electoral_bp.delete(
    "/electoral/scenario-portfolios/<uuid:portfolio_id>/scenarios/<uuid:scenario_id>"
)
@electoral_access_required("criar_cenario")
def remove_scenario_from_portfolio(portfolio_id, scenario_id):
    unavailable = _feature_required("cenarios")
    if unavailable:
        return unavailable
    portfolio = _accessible_portfolio(portfolio_id)
    if portfolio is None:
        return jsonify(error="not_found", message="Portfolio nao encontrado."), 404
    if portfolio.status != "ACTIVE":
        return _validation_error("Portfolio arquivado nao pode ser alterado.")
    tenant_id, user_id = _private_context()
    membership = db.session.execute(
        select(ElectoralScenarioPortfolioItem).where(
            ElectoralScenarioPortfolioItem.tenant_id == tenant_id,
            ElectoralScenarioPortfolioItem.portfolio_id == portfolio.id,
            ElectoralScenarioPortfolioItem.scenario_id == scenario_id,
            ElectoralScenarioPortfolioItem.removed_at.is_(None),
        )
    ).scalar_one_or_none()
    if membership is None:
        return jsonify(error="not_found", message="Cenario nao pertence ao portfolio."), 404
    membership.removed_at = datetime.now(UTC)
    membership.removed_by_id = user_id
    if portfolio.reference_scenario_id == scenario_id:
        remaining = [item for _, item in portfolio_scenarios(portfolio) if item.id != scenario_id]
        portfolio.reference_scenario_id = remaining[0].id if remaining else None
    portfolio.updated_at = datetime.now(UTC)
    record_portfolio_event(portfolio, user_id, "SCENARIO_REMOVED", {"scenarioId": str(scenario_id)})
    add_audit(
        tenant_id,
        user_id,
        "electoral.scenario_portfolio.scenario_removed",
        "electoral_scenario_portfolio",
        portfolio.id,
        after={"scenarioId": str(scenario_id)},
    )
    db.session.commit()
    return "", 204


@electoral_bp.put("/electoral/scenario-portfolios/<uuid:portfolio_id>/goals")
@electoral_access_required("criar_cenario")
def replace_scenario_portfolio_goals(portfolio_id):
    unavailable = _feature_required("cenarios")
    if unavailable:
        return unavailable
    portfolio = _accessible_portfolio(portfolio_id)
    if portfolio is None:
        return jsonify(error="not_found", message="Portfolio nao encontrado."), 404
    if portfolio.status != "ACTIVE":
        return _validation_error("Portfolio arquivado nao pode ser alterado.")
    scenarios = [scenario for _, scenario in portfolio_scenarios(portfolio)]
    try:
        goals = normalize_portfolio_goals(
            (request.get_json(silent=True) or {}).get("goals"), scenarios
        )
    except PortfolioValidationError as error:
        return _validation_error(str(error))
    tenant_id, user_id = _private_context()
    portfolio.goals = goals
    portfolio.updated_at = datetime.now(UTC)
    record_portfolio_event(portfolio, user_id, "GOALS_REPLACED", {"goalCount": len(goals)})
    add_audit(
        tenant_id,
        user_id,
        "electoral.scenario_portfolio.goals_replaced",
        "electoral_scenario_portfolio",
        portfolio.id,
        after={"goalCount": len(goals)},
    )
    db.session.commit()
    return jsonify(portfolio_data(portfolio, include_evaluation=True))


@electoral_bp.put("/electoral/scenario-portfolios/<uuid:portfolio_id>/reference")
@electoral_access_required("criar_cenario")
def set_scenario_portfolio_reference(portfolio_id):
    unavailable = _feature_required("cenarios")
    if unavailable:
        return unavailable
    portfolio = _accessible_portfolio(portfolio_id)
    if portfolio is None:
        return jsonify(error="not_found", message="Portfolio nao encontrado."), 404
    if portfolio.status != "ACTIVE":
        return _validation_error("Portfolio arquivado nao pode ser alterado.")
    payload = request.get_json(silent=True) or {}
    try:
        scenario_id = uuid.UUID(str(payload.get("scenario_id") or ""))
    except (TypeError, ValueError):
        return _validation_error("scenario_id deve possuir UUID valido.")
    active_ids = {scenario.id for _, scenario in portfolio_scenarios(portfolio)}
    if scenario_id not in active_ids:
        return _validation_error("A referencia deve ser um cenario ativo do portfolio.")
    tenant_id, user_id = _private_context()
    before = portfolio.reference_scenario_id
    portfolio.reference_scenario_id = scenario_id
    portfolio.updated_at = datetime.now(UTC)
    record_portfolio_event(
        portfolio,
        user_id,
        "REFERENCE_SET",
        {"before": str(before) if before else None, "scenarioId": str(scenario_id)},
    )
    add_audit(
        tenant_id,
        user_id,
        "electoral.scenario_portfolio.reference_set",
        "electoral_scenario_portfolio",
        portfolio.id,
        after={"scenarioId": str(scenario_id), "predictive": False},
    )
    db.session.commit()
    return jsonify(portfolio_data(portfolio, include_evaluation=True))


@electoral_bp.get("/electoral/scenario-portfolios/<uuid:portfolio_id>/evaluation")
@electoral_access_required("criar_cenario")
def get_scenario_portfolio_evaluation(portfolio_id):
    unavailable = _feature_required("cenarios")
    if unavailable:
        return unavailable
    portfolio = _accessible_portfolio(portfolio_id)
    if portfolio is None:
        return jsonify(error="not_found", message="Portfolio nao encontrado."), 404
    return jsonify(evaluate_portfolio(portfolio))


@electoral_bp.get("/electoral/scenario-portfolios/<uuid:portfolio_id>/history")
@electoral_access_required("criar_cenario")
def get_scenario_portfolio_history(portfolio_id):
    unavailable = _feature_required("cenarios")
    if unavailable:
        return unavailable
    portfolio = _accessible_portfolio(portfolio_id)
    if portfolio is None:
        return jsonify(error="not_found", message="Portfolio nao encontrado."), 404
    items = db.session.scalars(
        select(ElectoralScenarioPortfolioEvent)
        .where(
            ElectoralScenarioPortfolioEvent.tenant_id == portfolio.tenant_id,
            ElectoralScenarioPortfolioEvent.portfolio_id == portfolio.id,
        )
        .order_by(ElectoralScenarioPortfolioEvent.created_at.desc())
        .limit(200)
    )
    return jsonify(content=[portfolio_event_data(item) for item in items])


@electoral_bp.post("/electoral/scenario-portfolios/<uuid:portfolio_id>/export")
@electoral_access_required("exportar")
def export_scenario_portfolio(portfolio_id):
    unavailable = _feature_required("exportacoes")
    if unavailable:
        return unavailable
    portfolio = _accessible_portfolio(portfolio_id)
    if portfolio is None:
        return jsonify(error="not_found", message="Portfolio nao encontrado."), 404
    purpose = str((request.get_json(silent=True) or {}).get("purpose") or "").strip()
    if not 10 <= len(purpose) <= 500:
        return _validation_error("Informe a finalidade da exportacao entre 10 e 500 caracteres.")
    tenant_id, user_id = _private_context()
    content = portfolio_csv(portfolio)
    record_portfolio_event(portfolio, user_id, "EXPORTED", {"format": "CSV", "purpose": purpose})
    add_audit(
        tenant_id,
        user_id,
        "electoral.scenario_portfolio.exported",
        "electoral_scenario_portfolio",
        portfolio.id,
        after={"format": "CSV", "purpose": purpose, "sizeBytes": len(content)},
    )
    db.session.commit()
    return send_file(
        io.BytesIO(content),
        mimetype="text/csv; charset=utf-8",
        as_attachment=True,
        download_name=f"portfolio-cenarios-{portfolio.id}.csv",
    )


def _accessible_portfolio(portfolio_id):
    tenant_id, user_id = _private_context()
    statement = select(ElectoralScenarioPortfolio).where(
        ElectoralScenarioPortfolio.id == portfolio_id,
        ElectoralScenarioPortfolio.tenant_id == tenant_id,
    )
    if get_jwt().get("role") != Role.REPRESENTATIVE.value:
        statement = statement.where(ElectoralScenarioPortfolio.created_by_id == user_id)
    return db.session.execute(statement).scalar_one_or_none()


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


@electoral_bp.get("/electoral/report-schedules")
@electoral_access_required("exportar")
def list_report_schedules():
    if unavailable := _feature_required("exportacoes"):
        return unavailable
    tenant_id, user_id = _private_context()
    statement = select(ElectoralReportSchedule).where(
        ElectoralReportSchedule.tenant_id == tenant_id,
        ElectoralReportSchedule.mandate_id == g.electoral_mandate.id,
    )
    if get_jwt().get("role") != Role.REPRESENTATIVE.value:
        statement = statement.where(ElectoralReportSchedule.created_by_id == user_id)
    items = list(
        db.session.execute(statement.order_by(ElectoralReportSchedule.created_at.desc())).scalars()
    )
    recipients = list(
        db.session.execute(
            select(User)
            .where(
                User.tenant_id == tenant_id,
                User.status == UserStatus.ACTIVE,
            )
            .order_by(User.name)
        ).scalars()
    )
    return jsonify(
        content=[report_schedule_data(item) for item in items],
        available_recipients=[
            {"id": str(item.id), "name": item.name, "email": item.email} for item in recipients
        ],
    )


@electoral_bp.post("/electoral/report-schedules")
@electoral_access_required("exportar")
def post_report_schedule():
    if unavailable := _feature_required("exportacoes"):
        return unavailable
    tenant_id, user_id = _private_context()
    try:
        item = create_report_schedule(
            tenant_id, g.electoral_mandate.id, user_id, request.get_json(silent=True) or {}
        )
    except AdvancedFeatureError as exc:
        return _validation_error(str(exc))
    add_audit(
        tenant_id,
        user_id,
        "electoral.report_schedule.created",
        "electoral_report_schedule",
        item.id,
    )
    db.session.commit()
    return jsonify(report_schedule_data(item)), 201


@electoral_bp.delete("/electoral/report-schedules/<uuid:schedule_id>")
@electoral_access_required("exportar")
def delete_report_schedule(schedule_id):
    if unavailable := _feature_required("exportacoes"):
        return unavailable
    tenant_id, user_id = _private_context()
    statement = select(ElectoralReportSchedule).where(
        ElectoralReportSchedule.id == schedule_id,
        ElectoralReportSchedule.tenant_id == tenant_id,
        ElectoralReportSchedule.mandate_id == g.electoral_mandate.id,
    )
    if get_jwt().get("role") != Role.REPRESENTATIVE.value:
        statement = statement.where(ElectoralReportSchedule.created_by_id == user_id)
    item = db.session.execute(statement).scalar_one_or_none()
    if item is None:
        return jsonify(error="not_found", message="Agendamento de relatório não encontrado."), 404
    item.active = False
    add_audit(
        tenant_id,
        user_id,
        "electoral.report_schedule.deactivated",
        "electoral_report_schedule",
        item.id,
    )
    db.session.commit()
    return "", 204


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
    if not _participated_in_election(election_id):
        return _election_scope_error()
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


def _identity_owner_id() -> uuid.UUID:
    return g.electoral_mandate.representative_user_id


def _actor_is_identity_owner() -> bool:
    return uuid.UUID(get_jwt_identity()) == _identity_owner_id()


def _participated_in_election(election_id: uuid.UUID) -> bool:
    tenant_id, _ = _private_context()
    return (
        db.session.scalar(
            select(ElectoralUserCandidacy.id)
            .join(
                ElectoralCandidacy,
                ElectoralCandidacy.id == ElectoralUserCandidacy.candidacy_id,
            )
            .where(
                ElectoralUserCandidacy.tenant_id == tenant_id,
                ElectoralUserCandidacy.user_id == _identity_owner_id(),
                ElectoralCandidacy.election_id == election_id,
            )
            .limit(1)
        )
        is not None
    )


def _election_scope_error():
    return jsonify(
        error="election_outside_parliamentarian_context",
        message=(
            "A eleicao nao pertence as participacoes confirmadas do parlamentar. "
            "Use Explorar outras eleicoes para pesquisa publica."
        ),
    ), 422


def _identity_candidacies_statement(tenant_id: uuid.UUID, user_id: uuid.UUID):
    return (
        select(
            ElectoralUserCandidacy,
            ElectoralCandidacy,
            ElectoralCandidate,
            ElectoralElection,
            ElectoralOffice,
            ElectoralParty,
            ElectoralDatasetVersion,
        )
        .join(
            ElectoralCandidacy,
            ElectoralCandidacy.id == ElectoralUserCandidacy.candidacy_id,
        )
        .join(ElectoralCandidate, ElectoralCandidate.id == ElectoralCandidacy.candidate_id)
        .join(ElectoralElection, ElectoralElection.id == ElectoralCandidacy.election_id)
        .join(ElectoralOffice, ElectoralOffice.id == ElectoralCandidacy.office_id)
        .join(ElectoralParty, ElectoralParty.id == ElectoralCandidacy.party_id)
        .join(
            ElectoralDatasetVersion,
            ElectoralDatasetVersion.id == ElectoralCandidacy.dataset_version_id,
        )
        .where(
            ElectoralUserCandidacy.tenant_id == tenant_id,
            ElectoralUserCandidacy.user_id == user_id,
            ElectoralDatasetVersion.status == ElectoralDatasetStatus.PUBLISHED,
        )
        .order_by(
            ElectoralElection.year.desc(),
            ElectoralElection.election_date.desc(),
            ElectoralUserCandidacy.confirmed_at.desc(),
        )
    )


def _user_candidacy_data(
    identity: ElectoralUserCandidacy,
    candidacy: ElectoralCandidacy,
    candidate: ElectoralCandidate,
    election: ElectoralElection,
    office: ElectoralOffice,
    party: ElectoralParty,
    dataset: ElectoralDatasetVersion,
) -> dict:
    return {
        "id": str(identity.id),
        "candidacy_id": str(candidacy.id),
        "candidate": {
            "id": str(candidate.id),
            "candidacy_id": str(candidacy.id),
            "external_id": candidate.external_id,
            "full_name": candidate.full_name,
            "ballot_name": candidate.ballot_name,
            "number": candidacy.ballot_number,
            "office": {"id": str(office.id), "code": office.code, "name": office.name},
            "party": {
                "number": party.number,
                "acronym": party.acronym,
                "name": party.name,
            },
            "election": {"id": str(election.id), "year": election.year},
            "dataset_version": str(dataset.id),
            "source": dataset.source_url,
        },
        "election": _election_data(election, dataset),
        "method": identity.method,
        "automatic": identity.method == AUTOMATIC_CPF_METHOD,
        "confirmed_at": identity.confirmed_at.isoformat(),
    }


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
    now = datetime.now(UTC) if item.valid_until.tzinfo else datetime.now(UTC).replace(tzinfo=None)
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


def _effective_feature_flags(settings: ElectoralModuleSettings | None) -> dict:
    flags = {**DEFAULT_FEATURE_FLAGS, **(settings.feature_flags if settings else {})}
    # A IA eleitoral e uma capacidade permanente do modulo. Valores legados nao podem
    # desabilita-la por gabinete.
    flags["ia"] = True
    return flags


def _feature_required(name: str):
    tenant_id = uuid.UUID(get_jwt()["tenant_id"])
    settings = db.session.get(ElectoralModuleSettings, tenant_id)
    flags = _effective_feature_flags(settings)
    if flags.get(name):
        return None
    return (
        jsonify(
            error="feature_disabled",
            message=f"Funcionalidade eleitoral desabilitada: {name}.",
        ),
        403,
    )


def _commitment_mutation_required():
    if get_jwt().get("role") == Role.REPRESENTATIVE.value:
        return None
    return (
        jsonify(
            error="representative_required",
            message="Somente o parlamentar pode alterar compromissos públicos.",
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
    now = datetime.now(UTC) if report.expires_at.tzinfo else datetime.now(UTC).replace(tzinfo=None)
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


def _uuid_query_argument(name: str) -> uuid.UUID | None:
    value = (request.args.get(name) or "").strip()
    if not value:
        return None
    try:
        return uuid.UUID(value)
    except ValueError as exc:
        raise ValueError(f"{name} deve ser um UUID válido.") from exc


def _date_query_argument(name: str) -> date | None:
    value = (request.args.get(name) or "").strip()
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"{name} deve ser uma data ISO válida.") from exc


def _validation_error(message: str, **details):
    return jsonify(error="validation_error", message=message, **details), 422
