from sqlalchemy import select

from app.extensions import db
from app.models import PublicLead


def test_create_public_lead(app, client):
    response = client.post(
        "/api/v1/public/leads",
        json={
            "plano": "professional",
            "nome": "Maria Silva",
            "organizacao": "Gabinete Modelo",
            "email": "maria@gabinete.local",
            "telefone": "(11) 99999-0000",
            "cidade": "Sao Paulo",
            "uf": "SP",
            "tipoInstituicao": "gabinete_municipal",
            "mensagem": "Quero conhecer o GabFlow.",
        },
    )

    assert response.status_code == 201
    assert response.json["plano"] == "professional"

    with app.app_context():
        lead = db.session.execute(
            select(PublicLead).where(PublicLead.email == "maria@gabinete.local")
        ).scalar_one()
        assert lead.organization == "Gabinete Modelo"
        assert lead.status == "new"


def test_public_lead_validates_plan_and_email(client):
    invalid_plan = client.post(
        "/api/v1/public/leads",
        json={
            "plano": "basic",
            "nome": "Maria Silva",
            "organizacao": "Gabinete Modelo",
            "email": "maria@gabinete.local",
        },
    )
    assert invalid_plan.status_code == 422

    invalid_email = client.post(
        "/api/v1/public/leads",
        json={
            "plano": "starter",
            "nome": "Maria Silva",
            "organizacao": "Gabinete Modelo",
            "email": "maria",
        },
    )
    assert invalid_email.status_code == 422
