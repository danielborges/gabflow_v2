from sqlalchemy import select

from app.auth.security import hash_password
from app.extensions import db
from app.models import (
    AuditLog,
    LegislativeDocumentType,
    LegislativeDraft,
    LegislativeDraftStatus,
    LegislativeGenerationStatus,
    Role,
    Tenant,
    User,
    UserStatus,
)

PASSWORD = "SenhaForte123!"  # noqa: S105


def _csrf_from_cookie(client):
    return client.get_cookie("csrf_access_token").value


def _login(client, email="admin@teste.local", password=PASSWORD):
    response = client.post(
        "/api/v1/auth/login",
        json={"tenant": "gabinete-a", "email": email, "password": password},
    )
    assert response.status_code == 200
    return _csrf_from_cookie(client)


def test_only_office_admin_accesses_office_administration(app, client):
    with app.app_context():
        tenant = db.session.execute(select(Tenant).where(Tenant.slug == "gabinete-a")).scalar_one()
        db.session.add(
            User(
                tenant_id=tenant.id,
                name="Gestor",
                email="gestor@teste.local",
                password_hash=hash_password(PASSWORD),
                role=Role.MANAGER,
            )
        )
        db.session.commit()

    _login(client, email="gestor@teste.local")

    response = client.get("/api/v1/admin/perfil-gabinete")
    assert response.status_code == 403
    assert client.get("/api/v1/admin/categorias").status_code == 200
    assert client.get("/api/v1/admin/templates-resposta").status_code == 200


def test_office_admin_updates_profile_users_and_audit(app, client):
    csrf = _login(client)

    created = client.post(
        "/api/v1/admin/usuarios",
        headers={"X-CSRF-TOKEN": csrf},
        json={
            "nome": "Assessora Formal",
            "email": "assessora@teste.local",
            "senha": "SenhaForte123!",
            "perfil": "manager",
        },
    )

    assert created.status_code == 201
    assert created.json["perfil"] == "manager"

    profile = client.patch(
        "/api/v1/admin/perfil-gabinete",
        headers={"X-CSRF-TOKEN": csrf},
        json={
            "vereador": {"nomeParlamentar": "Vereadora Teste", "partido": "ABC"},
            "mandato": {"legislatura": "2025-2028", "cargo": "Vereadora"},
            "identidadeVisual": {"corPrimaria": "#2563eb"},
            "chefeGabineteId": created.json["id"],
        },
    )

    assert profile.status_code == 200
    assert profile.json["vereador"]["nomeParlamentar"] == "Vereadora Teste"
    assert profile.json["chefeGabineteId"] == created.json["id"]

    blocked = client.patch(
        f"/api/v1/admin/usuarios/{created.json['id']}",
        headers={"X-CSRF-TOKEN": csrf},
        json={"status": "blocked"},
    )

    assert blocked.status_code == 200
    assert blocked.json["status"] == "blocked"

    audit = client.get("/api/v1/admin/auditoria")
    assert audit.status_code == 200
    actions = {item["acao"] for item in audit.json["content"]}
    assert "tenant.user.created" in actions
    assert "tenant.office_profile.updated" in actions
    paged_audit = client.get("/api/v1/admin/auditoria?page=1&perPage=25")
    assert paged_audit.status_code == 200
    assert paged_audit.json["perPage"] == 25
    assert paged_audit.json["total"] >= len(paged_audit.json["content"])

    with app.app_context():
        user = db.session.execute(
            select(User).where(User.email == "assessora@teste.local")
        ).scalar_one()
        assert user.status == UserStatus.BLOCKED
        assert db.session.execute(select(AuditLog)).scalars().first() is not None


def test_representative_profile_consults_and_approves_without_admin_access(app, client):
    csrf = _login(client)
    created = client.post(
        "/api/v1/admin/usuarios",
        headers={"X-CSRF-TOKEN": csrf},
        json={
            "nome": "Vereadora Titular",
            "email": "vereadora@teste.local",
            "senha": PASSWORD,
            "perfil": "representative",
        },
    )
    assert created.status_code == 201
    assert created.json["perfil"] == "representative"

    with app.app_context():
        tenant = db.session.execute(select(Tenant).where(Tenant.slug == "gabinete-a")).scalar_one()
        admin = db.session.execute(
            select(User).where(User.tenant_id == tenant.id, User.email == "admin@teste.local")
        ).scalar_one()
        draft = LegislativeDraft(
            tenant_id=tenant.id,
            document_type=LegislativeDocumentType.INDICACAO,
            status=LegislativeDraftStatus.EM_REVISAO,
            generation_status=LegislativeGenerationStatus.CONCLUIDA,
            title="Indicacao para manutencao",
            content="Texto em revisao.",
            justification="Demanda prioritaria do territorio.",
            current_version=1,
            created_by_id=admin.id,
        )
        db.session.add(draft)
        db.session.commit()
        draft_id = draft.id

    csrf = _login(client, email="vereadora@teste.local")
    assert client.get("/api/v1/painel/operacional").status_code == 200
    assert client.get("/api/v1/solicitacoes").status_code == 200
    assert client.get("/api/v1/admin/perfil-gabinete").status_code == 403

    blocked_create = client.post(
        "/api/v1/solicitacoes",
        headers={"X-CSRF-TOKEN": csrf},
        json={"origem": "WHATSAPP", "descricao": "Tentativa operacional."},
    )
    assert blocked_create.status_code == 403

    approved = client.post(
        f"/api/v1/legislativo/minutas/{draft_id}/revisao",
        headers={"X-CSRF-TOKEN": csrf},
        json={"acao": "APROVAR", "confirmarFundamentacao": True},
    )
    assert approved.status_code == 200
    assert approved.json["status"] == "APROVADA"
