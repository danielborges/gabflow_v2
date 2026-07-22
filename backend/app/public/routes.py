import re
import time

from flask import Blueprint, jsonify, request

from app.extensions import db, limiter
from app.models import PublicLead

public_site_bp = Blueprint("public_site", __name__)

PLANS = {"starter", "professional", "premium"}
AUDIENCES = {"camara_municipal", "assembleia"}
PREFERRED_CONTACTS = {"email", "telefone", "whatsapp"}
DISCOVERY_SOURCES = {
    "instagram",
    "facebook",
    "youtube",
    "representante_comercial",
    "outros_gabinetes",
}
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
PHONE_RE = re.compile(r"^\(?[1-9]{2}\)?\s?(?:9\d{4}|[2-5]\d{3})-?\d{4}$")


@public_site_bp.post("/public/leads")
@limiter.limit("10 per minute")
def create_public_lead():
    payload = request.get_json(silent=True) or {}
    plan = str(payload.get("plano", "")).strip().lower()
    name = str(payload.get("nome", payload.get("administradorGabinete", ""))).strip()
    organization = str(payload.get("organizacao", payload.get("nomeGabinete", ""))).strip()
    admin_name = str(payload.get("administradorGabinete", name)).strip()
    email = str(payload.get("email", "")).strip().lower()
    phone = str(payload.get("telefone", "")).strip()
    whatsapp = str(payload.get("whatsapp", "")).strip()
    city = str(payload.get("cidade", "")).strip()
    state = str(payload.get("uf", "")).strip().upper()
    audience = str(payload.get("tipoInstituicao", "")).strip()
    municipality_ibge_id = payload.get("municipioIbgeId")
    preferred_contact = str(payload.get("formaContato", "")).strip().lower()
    discovery_source = str(payload.get("comoEncontrou", "")).strip().lower()
    message = str(payload.get("observacoes", payload.get("mensagem", ""))).strip()
    started_at = payload.get("iniciadoEm")

    if plan not in PLANS:
        return jsonify(error="validation_error", message="Selecione um plano valido."), 422
    if str(payload.get("website", "")).strip() or str(payload.get("empresa", "")).strip():
        return jsonify(error="validation_error", message="Solicitacao rejeitada."), 422
    if not _passes_timing_check(started_at):
        return jsonify(error="validation_error", message="Revise o formulario e envie novamente."), 422
    if len(name) < 2 or len(organization) < 2:
        return jsonify(error="validation_error", message="Informe nome e instituicao."), 422
    if not EMAIL_RE.match(email):
        return jsonify(error="validation_error", message="Informe um e-mail valido."), 422
    if phone and not PHONE_RE.match(phone):
        return jsonify(error="validation_error", message="Informe um telefone valido com DDD."), 422
    if whatsapp and not PHONE_RE.match(whatsapp):
        return jsonify(error="validation_error", message="Informe um WhatsApp valido com DDD."), 422
    if state and (len(state) != 2 or not state.isalpha()):
        return jsonify(error="validation_error", message="UF deve conter 2 letras."), 422
    if audience not in AUDIENCES:
        return jsonify(error="validation_error", message="Selecione o tipo de jurisdicao."), 422
    if preferred_contact not in PREFERRED_CONTACTS:
        return jsonify(error="validation_error", message="Selecione a forma preferencial de contato."), 422
    if discovery_source not in DISCOVERY_SOURCES:
        return jsonify(error="validation_error", message="Selecione como encontrou o GabFlow."), 422
    try:
        municipality_ibge_id = int(municipality_ibge_id)
    except (TypeError, ValueError):
        return jsonify(error="validation_error", message="Selecione um municipio valido."), 422

    lead = PublicLead(
        plan=plan,
        name=name[:160],
        organization=organization[:180],
        admin_name=admin_name[:160] or None,
        email=email[:254],
        phone=phone[:40] or None,
        whatsapp=whatsapp[:40] or None,
        city=city[:120] or None,
        state=state or None,
        municipality_ibge_id=municipality_ibge_id,
        audience=audience[:80] or None,
        preferred_contact=preferred_contact,
        discovery_source=discovery_source,
        message=message[:2000] or None,
        status="new",
        payment_status="pending",
    )
    db.session.add(lead)
    db.session.commit()
    return jsonify(id=str(lead.id), status=lead.status, plano=lead.plan), 201


def _passes_timing_check(started_at) -> bool:
    try:
        started_at = int(started_at)
    except (TypeError, ValueError):
        return False
    elapsed_ms = int(time.time() * 1000) - started_at
    return 2500 <= elapsed_ms <= 30 * 60 * 1000
