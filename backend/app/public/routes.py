import re

from flask import Blueprint, jsonify, request

from app.extensions import db, limiter
from app.models import PublicLead

public_site_bp = Blueprint("public_site", __name__)

PLANS = {"starter", "professional", "premium", "enterprise"}
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


@public_site_bp.post("/public/leads")
@limiter.limit("10 per minute")
def create_public_lead():
    payload = request.get_json(silent=True) or {}
    plan = str(payload.get("plano", "")).strip().lower()
    name = str(payload.get("nome", "")).strip()
    organization = str(payload.get("organizacao", "")).strip()
    email = str(payload.get("email", "")).strip().lower()
    phone = str(payload.get("telefone", "")).strip()
    city = str(payload.get("cidade", "")).strip()
    state = str(payload.get("uf", "")).strip().upper()
    audience = str(payload.get("tipoInstituicao", "")).strip()
    message = str(payload.get("mensagem", "")).strip()

    if plan not in PLANS:
        return jsonify(error="validation_error", message="Selecione um plano valido."), 422
    if len(name) < 2 or len(organization) < 2:
        return jsonify(error="validation_error", message="Informe nome e instituicao."), 422
    if not EMAIL_RE.match(email):
        return jsonify(error="validation_error", message="Informe um e-mail valido."), 422
    if state and (len(state) != 2 or not state.isalpha()):
        return jsonify(error="validation_error", message="UF deve conter 2 letras."), 422

    lead = PublicLead(
        plan=plan,
        name=name[:160],
        organization=organization[:180],
        email=email[:254],
        phone=phone[:40] or None,
        city=city[:120] or None,
        state=state or None,
        audience=audience[:80] or None,
        message=message[:2000] or None,
    )
    db.session.add(lead)
    db.session.commit()
    return jsonify(id=str(lead.id), status=lead.status, plano=lead.plan), 201
