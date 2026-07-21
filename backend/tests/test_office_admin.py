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

    parties = client.get("/api/v1/admin/partidos?q=pt")
    assert parties.status_code == 200
    party = next(item for item in parties.json["content"] if item["sigla"] == "PT")
    assert party["numero"] == 13

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

    parliamentarian = client.patch(
        "/api/v1/admin/parlamentar",
        headers={"X-CSRF-TOKEN": csrf},
        json={
            "nomeCompleto": "Maria da Silva Teste",
            "nomeParlamentar": "Vereadora Teste",
            "fotografiaUrl": "https://camara.test/foto.jpg",
            "partidoId": party["id"],
            "partido": party["sigla"],
            "partidoNome": party["nome"],
            "partidoNumero": party["numero"],
            "coligacaoFederacao": "Federacao Teste",
            "email": "vereadora@camara.test",
            "telefoneInstitucional": "(32) 3333-0000",
            "biografia": "Biografia resumida.",
            "areasPrioritarias": ["Saude", "Educacao"],
            "redesSociais": {"instagram": "https://instagram.test/vereadora"},
            "statusMandato": "ATIVO",
            "mandatos": [
                {
                    "legislatura": "2025-2028",
                    "cargo": "Vereadora",
                    "inicio": "2025-01-01",
                    "fim": "2028-12-31",
                    "votos": 1234,
                    "status": "ATUAL",
                },
                {
                    "legislatura": "2021-2024",
                    "cargo": "Vereadora",
                    "votos": 987,
                    "status": "HISTORICO",
                },
            ],
        },
    )

    assert parliamentarian.status_code == 200
    assert parliamentarian.json["nomeCompleto"] == "Maria da Silva Teste"
    assert parliamentarian.json["partido"] == "PT"
    assert parliamentarian.json["partidoNumero"] == 13
    assert parliamentarian.json["mandatos"][0]["votos"] == 1234

    duplicated_active_mandates = client.patch(
        "/api/v1/admin/parlamentar",
        headers={"X-CSRF-TOKEN": csrf},
        json={
            "nomeParlamentar": "Vereadora Teste",
            "mandatos": [{"status": "ATUAL"}, {"status": "ATIVO"}],
        },
    )
    assert duplicated_active_mandates.status_code == 422

    insights = client.post(
        "/api/v1/admin/parlamentar/insights-oficiais",
        headers={"X-CSRF-TOKEN": csrf},
        json={"nome": "Vereadora Teste"},
    )
    assert insights.status_code == 200
    assert any("TSE" in item["nome"] for item in insights.json["fontes"])

    profile = client.patch(
        "/api/v1/admin/perfil-gabinete",
        headers={"X-CSRF-TOKEN": csrf},
        json={
            "identidadeVisual": {
                "corPrimaria": "#2563eb",
                "corSecundaria": "#0f766e",
                "logoUrl": "https://camara.test/logo.png",
                "dadosInstitucionais": {
                    "nomeGabinete": "Gabinete da Vereadora Teste",
                    "camaraMunicipal": "Camara Municipal de Teste",
                    "municipio": "Teste",
                    "estado": "MG",
                    "enderecoInstitucional": "Rua da Camara, 100",
                    "telefone": "(32) 3333-1111",
                    "emailOficial": "gabinete@camara.test",
                    "horarioAtendimento": "Segunda a sexta, 8h as 17h",
                    "site": "https://camara.test/gabinete",
                },
                "redesSociais": {"instagram": "https://instagram.test/gabinete"},
            },
            "chefeGabineteId": created.json["id"],
        },
    )

    assert profile.status_code == 200
    assert profile.json["chefeGabineteId"] == created.json["id"]
    assert profile.json["dadosInstitucionais"]["nomeGabinete"] == (
        "Gabinete da Vereadora Teste"
    )
    assert profile.json["dadosInstitucionais"]["estado"] == "MG"
    assert profile.json["redesSociais"]["instagram"] == "https://instagram.test/gabinete"

    updated = client.patch(
        f"/api/v1/admin/usuarios/{created.json['id']}",
        headers={"X-CSRF-TOKEN": csrf},
        json={
            "nome": "Assessora Formal Atualizada",
            "email": "assessora.atualizada@teste.local",
            "perfil": "staff",
        },
    )

    assert updated.status_code == 200
    assert updated.json["nome"] == "Assessora Formal Atualizada"
    assert updated.json["email"] == "assessora.atualizada@teste.local"
    assert updated.json["perfil"] == "staff"

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
    assert "tenant.parliamentarian.updated" in actions
    assert "tenant.parliamentarian.official_insights.requested" in actions
    assert "tenant.office_profile.updated" in actions
    paged_audit = client.get("/api/v1/admin/auditoria?page=1&perPage=25")
    assert paged_audit.status_code == 200
    assert paged_audit.json["perPage"] == 25
    assert paged_audit.json["total"] >= len(paged_audit.json["content"])

    with app.app_context():
        user = db.session.execute(
            select(User).where(User.email == "assessora.atualizada@teste.local")
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


def test_chief_of_staff_designation_grants_supervision_without_admin_role(app, client):
    csrf = _login(client)
    chief = client.post(
        "/api/v1/admin/usuarios",
        headers={"X-CSRF-TOKEN": csrf},
        json={
            "nome": "Chefe Operacional",
            "email": "chefe@teste.local",
            "senha": PASSWORD,
            "perfil": "staff",
        },
    )
    regular_staff = client.post(
        "/api/v1/admin/usuarios",
        headers={"X-CSRF-TOKEN": csrf},
        json={
            "nome": "Assessor Regular",
            "email": "assessor.regular@teste.local",
            "senha": PASSWORD,
            "perfil": "staff",
        },
    )
    assert chief.status_code == 201
    assert regular_staff.status_code == 201

    profile = client.patch(
        "/api/v1/admin/perfil-gabinete",
        headers={"X-CSRF-TOKEN": csrf},
        json={"chefeGabineteId": chief.json["id"]},
    )
    assert profile.status_code == 200
    assert profile.json["chefeGabineteId"] == chief.json["id"]

    users = client.get("/api/v1/admin/usuarios")
    assert users.status_code == 200
    chief_data = next(item for item in users.json["content"] if item["id"] == chief.json["id"])
    assert chief_data["perfil"] == "staff"
    assert chief_data["chefeGabinete"] is True
    assert chief_data["funcoes"] == ["chefe_gabinete"]

    with app.app_context():
        tenant = db.session.execute(select(Tenant).where(Tenant.slug == "gabinete-a")).scalar_one()
        admin = db.session.execute(
            select(User).where(User.tenant_id == tenant.id, User.email == "admin@teste.local")
        ).scalar_one()
        draft = LegislativeDraft(
            tenant_id=tenant.id,
            document_type=LegislativeDocumentType.INDICACAO,
            status=LegislativeDraftStatus.APROVADA,
            generation_status=LegislativeGenerationStatus.CONCLUIDA,
            title="Indicacao aprovada para protocolo",
            content="Texto aprovado.",
            justification="Demanda prioritaria.",
            current_version=1,
            created_by_id=admin.id,
            approved_by_id=admin.id,
        )
        db.session.add(draft)
        db.session.commit()
        draft_id = draft.id

    csrf = _login(client, email="assessor.regular@teste.local")
    blocked = client.post(
        f"/api/v1/legislativo/minutas/{draft_id}/protocolo",
        headers={"X-CSRF-TOKEN": csrf},
        json={"protocolo": "CM-2026-REGULAR"},
    )
    assert blocked.status_code == 403

    csrf = _login(client, email="chefe@teste.local")
    me = client.get("/api/v1/auth/me")
    assert me.status_code == 200
    assert me.json["user"]["role"] == "staff"
    assert me.json["user"]["chefeGabinete"] is True
    assert client.get("/api/v1/admin/perfil-gabinete").status_code == 403

    protocolled = client.post(
        f"/api/v1/legislativo/minutas/{draft_id}/protocolo",
        headers={"X-CSRF-TOKEN": csrf},
        json={"protocolo": "CM-2026-CHEFE"},
    )
    assert protocolled.status_code == 200
    assert protocolled.json["protocolo"] == "CM-2026-CHEFE"
