import pytest

from app import create_app
from app.auth.security import hash_password
from app.config import TestConfig
from app.extensions import db
from app.models import PoliticalParty, Role, Tenant, User


@pytest.fixture()
def app(tmp_path):
    application = create_app(TestConfig)
    application.config["ATTACHMENT_STORAGE_PATH"] = str(tmp_path / "attachments")
    application.config["RAG_STORAGE_PATH"] = str(tmp_path / "rag")
    with application.app_context():
        db.create_all()
        tenant_a = Tenant(name="Gabinete A", slug="gabinete-a")
        tenant_b = Tenant(name="Gabinete B", slug="gabinete-b")
        db.session.add_all([tenant_a, tenant_b])
        db.session.flush()
        db.session.add_all(
            [
                PoliticalParty(
                    acronym="PT",
                    name="PARTIDO DOS TRABALHADORES",
                    ballot_number=13,
                    registration_date="11.2.1982",
                    national_president="EDSON ANTONIO EDINHO DA SILVA",
                    source_url="https://www.tse.jus.br/partidos/partidos-registrados-no-tse/partido-dos-trabalhadores",
                ),
                PoliticalParty(
                    acronym="MDB",
                    name="MOVIMENTO DEMOCRÁTICO BRASILEIRO",
                    ballot_number=15,
                    registration_date="30.6.1981",
                    national_president="LUIZ FELIPE BALEIA TENUTO ROSSI",
                    source_url="https://www.tse.jus.br/partidos/partidos-registrados-no-tse/movimento-democratico-brasileiro",
                ),
            ]
        )
        db.session.add_all(
            [
                User(
                    tenant_id=tenant_a.id,
                    name="Admin A",
                    email="admin@teste.local",
                    password_hash=hash_password("SenhaForte123!"),
                    role=Role.ADMIN,
                ),
                User(
                    tenant_id=tenant_b.id,
                    name="Admin B",
                    email="admin-b@teste.local",
                    password_hash=hash_password("OutraSenha123!"),
                    role=Role.ADMIN,
                ),
            ]
        )
        db.session.commit()

    yield application

    with application.app_context():
        db.session.remove()
        db.drop_all()


@pytest.fixture()
def client(app):
    return app.test_client()
