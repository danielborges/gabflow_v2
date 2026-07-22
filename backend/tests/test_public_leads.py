import time

from sqlalchemy import select

from app.extensions import db
from app.models import PublicLead


def _valid_payload(**overrides):
    payload = {
        "plano": "professional",
        "nomeGabinete": "Gabinete Modelo",
        "administradorGabinete": "Maria Silva",
        "email": "maria@gabinete.local",
        "telefone": "(11) 3333-0000",
        "whatsapp": "(11) 99999-0000",
        "cidade": "São Paulo",
        "uf": "SP",
        "municipioIbgeId": 3550308,
        "tipoInstituicao": "camara_municipal",
        "formaContato": "whatsapp",
        "comoEncontrou": "instagram",
        "observacoes": "Quero conhecer o GabFlow.",
        "iniciadoEm": int(time.time() * 1000) - 3000,
    }
    payload.update(overrides)
    return payload


def test_create_public_lead(app, client):
    response = client.post(
        "/api/v1/public/leads",
        json=_valid_payload(),
    )

    assert response.status_code == 201
    assert response.json["plano"] == "professional"

    with app.app_context():
        lead = db.session.execute(
            select(PublicLead).where(PublicLead.email == "maria@gabinete.local")
        ).scalar_one()
        assert lead.organization == "Gabinete Modelo"
        assert lead.admin_name == "Maria Silva"
        assert lead.municipality_ibge_id == 3550308
        assert lead.preferred_contact == "whatsapp"
        assert lead.discovery_source == "instagram"
        assert lead.payment_status == "pending"
        assert lead.status == "new"


def test_public_lead_validates_plan_and_email(client):
    invalid_plan = client.post(
        "/api/v1/public/leads",
        json=_valid_payload(plano="basic"),
    )
    assert invalid_plan.status_code == 422

    invalid_email = client.post(
        "/api/v1/public/leads",
        json=_valid_payload(plano="starter", email="maria"),
    )
    assert invalid_email.status_code == 422


def test_public_lead_rejects_honeypot_and_fast_submit(client):
    honeypot = client.post(
        "/api/v1/public/leads",
        json=_valid_payload(website="https://bot.example"),
    )
    assert honeypot.status_code == 422

    fast_submit = client.post(
        "/api/v1/public/leads",
        json=_valid_payload(iniciadoEm=int(time.time() * 1000)),
    )
    assert fast_submit.status_code == 422
