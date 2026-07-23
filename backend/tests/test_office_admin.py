from sqlalchemy import select

from app.auth.security import hash_password
from app.extensions import db
from app.models import (
    AuditLog,
    ExternalAgency,
    LegislativeDocumentType,
    LegislativeDraft,
    LegislativeDraftStatus,
    LegislativeGenerationStatus,
    Role,
    Tenant,
    Territory,
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
    categories = client.get("/api/v1/admin/categorias")
    assert categories.status_code == 200
    category_slas = {item["nome"]: item["slaHoras"] for item in categories.json["content"]}
    assert len(category_slas) >= 30
    assert category_slas["Defesa civil e risco iminente"] == 4
    assert category_slas["Saúde"] == 24
    assert category_slas["Iluminação pública"] == 72
    assert category_slas["Projetos, indicações e requerimentos"] == 240
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
            "cpf": "529.982.247-25",
            "telefone": "(32) 99999-0000",
            "senha": "SenhaForte123!",
            "perfil": "staff",
        },
    )

    assert created.status_code == 201
    assert created.json["perfil"] == "staff"

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


def test_office_admin_reloads_edits_and_logically_deletes_suggested_territories(
    app, client, monkeypatch
):
    def fake_ibge(url):
        assert "/municipios/3136702/distritos" in url
        return [{"nome": "Juiz de Fora"}, {"nome": "Rosário de Minas"}]

    monkeypatch.setattr("app.territory_suggestions._fetch_ibge_json", fake_ibge)
    with app.app_context():
        tenant = db.session.execute(select(Tenant).where(Tenant.slug == "gabinete-a")).scalar_one()
        tenant.chamber_type = "CAMARA_MUNICIPAL"
        tenant.jurisdiction_name = "Juiz de Fora/MG"
        tenant.jurisdiction_city = "Juiz de Fora"
        tenant.jurisdiction_state = "MG"
        tenant.jurisdiction_ibge_code = "3136702"
        db.session.commit()

    csrf = _login(client)
    reloaded = client.post(
        "/api/v1/admin/territorios/recarregar-sugestoes",
        headers={"X-CSRF-TOKEN": csrf},
    )

    assert reloaded.status_code == 200
    names = {item["nome"]: item for item in reloaded.json["content"]}
    assert names["Juiz de Fora"]["ativa"] is True
    assert names["Rosário de Minas"]["ativa"] is True

    updated = client.patch(
        f"/api/v1/admin/territorios/{names['Rosário de Minas']['id']}",
        headers={"X-CSRF-TOKEN": csrf},
        json={"nome": "Rosário de Minas Rural"},
    )
    assert updated.status_code == 200
    assert updated.json["nome"] == "Rosário de Minas Rural"

    deleted = client.delete(
        f"/api/v1/admin/territorios/{names['Juiz de Fora']['id']}",
        headers={"X-CSRF-TOKEN": csrf},
    )
    assert deleted.status_code == 200
    assert deleted.json["ativa"] is False

    with app.app_context():
        stored = db.session.get(Territory, names["Juiz de Fora"]["id"])
        assert stored.active is False


def test_office_admin_reloads_edits_and_logically_deletes_suggested_agencies(app, client):
    with app.app_context():
        tenant = db.session.execute(select(Tenant).where(Tenant.slug == "gabinete-a")).scalar_one()
        tenant.chamber_type = "CAMARA_MUNICIPAL"
        tenant.jurisdiction_name = "Juiz de Fora/MG"
        tenant.jurisdiction_city = "Juiz de Fora"
        tenant.jurisdiction_state = "MG"
        db.session.commit()

    csrf = _login(client)
    reloaded = client.post(
        "/api/v1/admin/orgaos/recarregar-sugestoes",
        headers={"X-CSRF-TOKEN": csrf},
    )

    assert reloaded.status_code == 200
    names = {item["nome"]: item for item in reloaded.json["content"]}
    assert names["Prefeitura Municipal de Juiz de Fora"]["ativa"] is True
    assert names["Secretaria Municipal de Saúde"]["responsavel"] == "A definir"

    updated = client.patch(
        f"/api/v1/admin/orgaos/{names['Secretaria Municipal de Saúde']['id']}",
        headers={"X-CSRF-TOKEN": csrf},
        json={
            "responsavel": "Secretária Municipal",
            "telefone": "(32) 3333-0000",
            "emailContato": "saude@juizdefora.mg.gov.br",
        },
    )
    assert updated.status_code == 200
    assert updated.json["responsavel"] == "Secretária Municipal"
    assert updated.json["telefone"] == "(32) 3333-0000"

    deleted = client.delete(
        f"/api/v1/admin/orgaos/{names['Prefeitura Municipal de Juiz de Fora']['id']}",
        headers={"X-CSRF-TOKEN": csrf},
    )
    assert deleted.status_code == 200
    assert deleted.json["ativa"] is False

    with app.app_context():
        stored = db.session.get(
            ExternalAgency, names["Prefeitura Municipal de Juiz de Fora"]["id"]
        )
        assert stored.active is False


def test_office_admin_validates_user_roles_email_and_unique_singleton_profiles(app, client):
    with app.app_context():
        tenant_b = db.session.execute(
            select(Tenant).where(Tenant.slug == "gabinete-b")
        ).scalar_one()
        db.session.add(
            User(
                tenant_id=tenant_b.id,
                name="Usuario Outro Gabinete",
                email="outro-gabinete@teste.local",
                cpf="67890123469",
                password_hash=hash_password(PASSWORD),
                role=Role.STAFF,
            )
        )
        db.session.commit()

    csrf = _login(client)

    duplicate_admin = client.post(
        "/api/v1/admin/usuarios",
        headers={"X-CSRF-TOKEN": csrf},
        json={
            "nome": "Outro Administrador",
            "email": "outro-admin@teste.local",
            "cpf": "111.444.777-35",
            "senha": PASSWORD,
            "perfil": "admin",
        },
    )
    assert duplicate_admin.status_code == 422
    assert duplicate_admin.json["error"] == "role_limit_reached"

    invalid_email = client.post(
        "/api/v1/admin/usuarios",
        headers={"X-CSRF-TOKEN": csrf},
        json={
            "nome": "Email Invalido",
            "email": "email-invalido",
            "cpf": "390.533.447-05",
            "senha": PASSWORD,
            "perfil": "staff",
        },
    )
    assert invalid_email.status_code == 422

    duplicate_cross_tenant_email = client.post(
        "/api/v1/admin/usuarios",
        headers={"X-CSRF-TOKEN": csrf},
        json={
            "nome": "Email Outro Gabinete",
            "email": "outro-gabinete@teste.local",
            "cpf": "789.012.345-05",
            "senha": PASSWORD,
            "perfil": "staff",
        },
    )
    assert duplicate_cross_tenant_email.status_code == 409

    duplicate_cross_tenant_cpf = client.post(
        "/api/v1/admin/usuarios",
        headers={"X-CSRF-TOKEN": csrf},
        json={
            "nome": "CPF Outro Gabinete",
            "email": "cpf-outro-gabinete@teste.local",
            "cpf": "678.901.234-69",
            "senha": PASSWORD,
            "perfil": "staff",
        },
    )
    assert duplicate_cross_tenant_cpf.status_code == 409

    manager = client.post(
        "/api/v1/admin/usuarios",
        headers={"X-CSRF-TOKEN": csrf},
        json={
            "nome": "Gestor Indevido",
            "email": "gestor-indevido@teste.local",
            "cpf": "935.411.347-80",
            "senha": PASSWORD,
            "perfil": "manager",
        },
    )
    assert manager.status_code == 422

    representative = client.post(
        "/api/v1/admin/usuarios",
        headers={"X-CSRF-TOKEN": csrf},
        json={
            "nome": "Parlamentar Titular",
            "email": "parlamentar@teste.local",
            "cpf": "123.456.789-09",
            "senha": PASSWORD,
            "perfil": "representative",
        },
    )
    assert representative.status_code == 201

    duplicate_representative = client.post(
        "/api/v1/admin/usuarios",
        headers={"X-CSRF-TOKEN": csrf},
        json={
            "nome": "Parlamentar Suplente",
            "email": "parlamentar-suplente@teste.local",
            "cpf": "987.654.321-00",
            "senha": PASSWORD,
            "perfil": "representative",
        },
    )
    assert duplicate_representative.status_code == 422
    assert duplicate_representative.json["error"] == "role_limit_reached"


def test_office_admin_cannot_reactivate_user_above_plan_limit(app, client):
    with app.app_context():
        tenant = db.session.execute(select(Tenant).where(Tenant.slug == "gabinete-a")).scalar_one()
        tenant.plan = "starter"
        tenant.user_limit = 999
        db.session.add_all(
            [
                *[
                    User(
                        tenant_id=tenant.id,
                        name=f"Assessora Ativa {index}",
                        email=f"ativa{index}@teste.local",
                        password_hash=hash_password(PASSWORD),
                        role=Role.STAFF,
                        status=UserStatus.ACTIVE,
                    )
                    for index in range(4)
                ],
                User(
                    tenant_id=tenant.id,
                    name="Assessora Bloqueada",
                    email="bloqueada@teste.local",
                    password_hash=hash_password(PASSWORD),
                    role=Role.STAFF,
                    status=UserStatus.BLOCKED,
                ),
            ]
        )
        db.session.commit()
        blocked_id = db.session.execute(
            select(User.id).where(User.email == "bloqueada@teste.local")
        ).scalar_one()

    csrf = _login(client)
    reactivated = client.patch(
        f"/api/v1/admin/usuarios/{blocked_id}",
        headers={"X-CSRF-TOKEN": csrf},
        json={"status": "active"},
    )

    assert reactivated.status_code == 422
    assert reactivated.json["error"] == "user_limit_reached"


def test_representative_profile_consults_and_approves_without_admin_access(app, client):
    csrf = _login(client)
    created = client.post(
        "/api/v1/admin/usuarios",
        headers={"X-CSRF-TOKEN": csrf},
        json={
            "nome": "Vereadora Titular",
            "email": "vereadora@teste.local",
            "cpf": "222.333.444-05",
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
            "cpf": "345.678.901-75",
            "telefone": "(32) 98888-0000",
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
            "cpf": "456.789.012-49",
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
