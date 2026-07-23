from sqlalchemy import select

from app.auth.security import hash_password
from app.extensions import db
from app.models import (
    ContractStatus,
    PlatformContractEvent,
    PublicLead,
    RequestSource,
    Role,
    ServiceRequest,
    Tenant,
    User,
    UserStatus,
)
from app.modules import DEFAULT_MODULES

PASSWORD = "SenhaForte123!"  # noqa: S105


def _csrf_from_cookie(client):
    return client.get_cookie("csrf_access_token").value


def _login_platform(app, client):
    with app.app_context():
        db.session.add(
            User(
                tenant_id=None,
                name="Administrador Geral",
                email="platform@teste.local",
                password_hash=hash_password(PASSWORD),
                role=Role.PLATFORM_ADMIN,
            )
        )
        db.session.commit()
    response = client.post(
        "/api/v1/auth/login",
        json={"email": "platform@teste.local", "password": PASSWORD},
    )
    assert response.status_code == 200
    return _csrf_from_cookie(client)


def _login_tenant_admin(client):
    response = client.post(
        "/api/v1/auth/login",
        json={"tenant": "gabinete-a", "email": "admin@teste.local", "password": PASSWORD},
    )
    assert response.status_code == 200
    return _csrf_from_cookie(client)


def test_tenant_admin_cannot_access_platform_admin(client):
    _login_tenant_admin(client)

    response = client.get("/api/v1/platform/overview")

    assert response.status_code == 403


def test_platform_admin_searches_and_updates_existing_tenant(app, client):
    csrf = _login_platform(app, client)
    with app.app_context():
        tenant = db.session.execute(select(Tenant).where(Tenant.slug == "gabinete-a")).scalar_one()
        tenant.name = "Gabinete Plataforma"
        tenant.plan = "professional"
        tenant.user_limit = 999
        tenant.jurisdiction_name = "Juiz de Fora/MG"
        tenant.jurisdiction_city = "Juiz de Fora"
        tenant.jurisdiction_state = "MG"
        tenant.representative_info = {"nomeParlamentar": "Vereadora Teste"}
        db.session.commit()
        tenant_id = str(tenant.id)

    created = client.post(
        "/api/v1/platform/gabinetes",
        headers={"X-CSRF-TOKEN": csrf},
        json={
            "nome": "Gabinete Plataforma",
            "slug": "gabinete-plataforma",
            "plano": "professional",
            "limiteUsuarios": 12,
            "limiteArmazenamentoMb": 4096,
            "modulosHabilitados": ["solicitacoes", "canais", "privacidade"],
        },
    )

    assert created.status_code == 405
    assert created.json["error"] == "tenant_creation_locked"

    listed = client.get(
        "/api/v1/platform/gabinetes",
        query_string={
            "q": "Plataforma",
            "plano": "professional",
            "jurisdicao": "Juiz",
            "parlamentar": "Vereadora",
        },
    )
    assert listed.status_code == 200
    assert listed.json["content"][0]["id"] == tenant_id
    assert listed.json["content"][0]["limiteUsuarios"] == 15
    assert "limiteArmazenamentoMb" not in listed.json["content"][0]

    missing_reason = client.patch(
        f"/api/v1/platform/gabinetes/{tenant_id}",
        headers={"X-CSRF-TOKEN": csrf},
        json={"contrato": "suspended", "limiteUsuarios": 20},
    )
    assert missing_reason.status_code == 422

    updated = client.post(
        f"/api/v1/platform/gabinetes/{tenant_id}/contrato",
        headers={"X-CSRF-TOKEN": csrf},
        json={"contrato": "suspended", "motivo": "Inadimplencia formalizada"},
    )

    assert updated.status_code == 200
    assert updated.json["tenant"]["contrato"] == "suspended"
    assert updated.json["tenant"]["status"] == "suspended"
    assert updated.json["evento"]["motivo"] == "Inadimplencia formalizada"

    with app.app_context():
        event = db.session.execute(select(PlatformContractEvent)).scalar_one()
        assert event.new_status == ContractStatus.SUSPENDED


def test_platform_admin_user_limit_follows_plan_and_blocks_downgrade(app, client):
    csrf = _login_platform(app, client)

    with app.app_context():
        tenant = Tenant(
            name="Gabinete Plano",
            slug="gabinete-plano",
            plan="professional",
            enabled_modules=DEFAULT_MODULES,
        )
        db.session.add(tenant)
        db.session.flush()
        db.session.add_all(
            [
                User(
                    tenant_id=tenant.id,
                    name=f"Usuario {index}",
                    email=f"usuario{index}@plano.local",
                    password_hash=hash_password(PASSWORD),
                    role=Role.STAFF,
                )
                for index in range(6)
            ]
        )
        db.session.commit()
        tenant_id = str(tenant.id)

    downgraded = client.patch(
        f"/api/v1/platform/gabinetes/{tenant_id}",
        headers={"X-CSRF-TOKEN": csrf},
        json={"plano": "starter"},
    )
    assert downgraded.status_code == 422
    assert downgraded.json["error"] == "plan_user_limit_conflict"


def test_platform_admin_renamed_tenant_updates_office_profile(app, client):
    csrf = _login_platform(app, client)
    with app.app_context():
        tenant = db.session.execute(select(Tenant).where(Tenant.slug == "gabinete-a")).scalar_one()
        tenant_id = str(tenant.id)

    updated = client.patch(
        f"/api/v1/platform/gabinetes/{tenant_id}",
        headers={"X-CSRF-TOKEN": csrf},
        json={"nome": "Gabinete 01 Matias"},
    )
    assert updated.status_code == 200
    assert updated.json["nome"] == "Gabinete 01 Matias"

    _login_tenant_admin(client)
    profile = client.get("/api/v1/admin/perfil-gabinete")
    assert profile.status_code == 200
    assert profile.json["dadosInstitucionais"]["nomeGabinete"] == "Gabinete 01 Matias"
    assert (
        profile.json["identidadeVisual"]["dadosInstitucionais"]["nomeGabinete"]
        == "Gabinete 01 Matias"
    )


def test_platform_reset_admin_respects_plan_user_limit(app, client):
    csrf = _login_platform(app, client)
    with app.app_context():
        tenant = db.session.execute(select(Tenant).where(Tenant.slug == "gabinete-a")).scalar_one()
        tenant.plan = "starter"
        tenant.user_limit = 999
        blocked = User(
            tenant_id=tenant.id,
            name="Admin Bloqueado",
            email="admin-bloqueado@teste.local",
            password_hash=hash_password(PASSWORD),
            role=Role.STAFF,
            status=UserStatus.BLOCKED,
        )
        db.session.add_all(
            [
                *[
                    User(
                        tenant_id=tenant.id,
                        name=f"Usuario Ativo {index}",
                        email=f"ativo{index}@reset.local",
                        password_hash=hash_password(PASSWORD),
                        role=Role.STAFF,
                    )
                    for index in range(4)
                ],
                blocked,
            ]
        )
        db.session.commit()
        tenant_id = str(tenant.id)

    reset = client.post(
        f"/api/v1/platform/gabinetes/{tenant_id}/reset-admin",
        headers={"X-CSRF-TOKEN": csrf},
        json={"email": "admin-bloqueado@teste.local"},
    )

    assert reset.status_code == 422
    assert reset.json["error"] == "user_limit_reached"


def test_platform_admin_manages_tenant_users(app, client):
    csrf = _login_platform(app, client)
    with app.app_context():
        tenant = db.session.execute(select(Tenant).where(Tenant.slug == "gabinete-a")).scalar_one()
        tenant.plan = "starter"
        tenant.user_limit = 999
        db.session.commit()
        tenant_id = str(tenant.id)

    created = client.post(
        f"/api/v1/platform/gabinetes/{tenant_id}/usuarios",
        headers={"X-CSRF-TOKEN": csrf},
        json={
            "nome": "Usuario Plataforma",
            "email": "usuario-plataforma@teste.local",
            "cpf": "529.982.247-25",
            "telefone": "(32) 99999-0000",
            "senha": PASSWORD,
            "perfil": "staff",
        },
    )

    assert created.status_code == 201
    assert created.json["email"] == "usuario-plataforma@teste.local"
    assert created.json["cpf"] == "529.982.247-25"

    listed = client.get(f"/api/v1/platform/gabinetes/{tenant_id}/usuarios")
    assert listed.status_code == 200
    assert any(item["email"] == "usuario-plataforma@teste.local" for item in listed.json["content"])

    updated = client.patch(
        f"/api/v1/platform/gabinetes/{tenant_id}/usuarios/{created.json['id']}",
        headers={"X-CSRF-TOKEN": csrf},
        json={"nome": "Usuario Plataforma Editado", "status": "blocked", "senha": "NovaSenha123!"},
    )

    assert updated.status_code == 200
    assert updated.json["nome"] == "Usuario Plataforma Editado"
    assert updated.json["status"] == "blocked"

    blocked = client.delete(
        f"/api/v1/platform/gabinetes/{tenant_id}/usuarios/{created.json['id']}",
        headers={"X-CSRF-TOKEN": csrf},
    )

    assert blocked.status_code == 200
    assert blocked.json["status"] == "blocked"


def test_platform_admin_tenant_user_creation_respects_plan_limit(app, client):
    csrf = _login_platform(app, client)
    with app.app_context():
        tenant = db.session.execute(select(Tenant).where(Tenant.slug == "gabinete-a")).scalar_one()
        tenant.plan = "starter"
        tenant.user_limit = 999
        db.session.add_all(
            [
                User(
                    tenant_id=tenant.id,
                    name=f"Usuario Limite {index}",
                    email=f"limite{index}@teste.local",
                    cpf=f"0000000000{index}",
                    password_hash=hash_password(PASSWORD),
                    role=Role.STAFF,
                    status=UserStatus.ACTIVE,
                )
                for index in range(4)
            ]
        )
        db.session.commit()
        tenant_id = str(tenant.id)

    response = client.post(
        f"/api/v1/platform/gabinetes/{tenant_id}/usuarios",
        headers={"X-CSRF-TOKEN": csrf},
        json={
            "nome": "Usuario Excedente",
            "email": "excedente@teste.local",
            "cpf": "529.982.247-25",
            "senha": PASSWORD,
            "perfil": "staff",
        },
    )

    assert response.status_code == 422
    assert response.json["error"] == "user_limit_reached"


def test_platform_usage_is_aggregated_without_internal_content(app, client):
    csrf = _login_platform(app, client)
    with app.app_context():
        tenant = db.session.execute(select(Tenant).where(Tenant.slug == "gabinete-a")).scalar_one()
        admin = db.session.execute(
            select(User).where(User.tenant_id == tenant.id, User.email == "admin@teste.local")
        ).scalar_one()
        db.session.add(
            ServiceRequest(
                tenant_id=tenant.id,
                protocol="GF-TEST-001",
                source=RequestSource.PRESENCIAL,
                title="Conteudo privado nao deve aparecer",
                description="Detalhe interno sensivel",
                created_by_id=admin.id,
            )
        )
        db.session.commit()
        tenant_id = str(tenant.id)

    usage = client.get(f"/api/v1/platform/gabinetes/{tenant_id}/consumo")
    overview = client.get("/api/v1/platform/overview")

    assert usage.status_code == 200
    assert usage.json["consumo"]["solicitacoes"] == 1
    assert "Conteudo privado" not in usage.get_data(as_text=True)
    assert "Detalhe interno" not in overview.get_data(as_text=True)

    support = client.post(
        "/api/v1/platform/suporte",
        headers={"X-CSRF-TOKEN": csrf},
        json={
            "tenantId": tenant_id,
            "solicitadoPor": "Admin do gabinete",
            "autorizadoPor": "Chefia",
            "motivo": "Chamado formal de suporte",
            "escopo": "Validar configuracao de webhook",
        },
    )

    assert support.status_code == 201
    assert support.json["escopo"] == "Validar configuracao de webhook"


def test_platform_admin_manages_contracting_interests(app, client):
    csrf = _login_platform(app, client)
    with app.app_context():
        lead = PublicLead(
            plan="professional",
            name="Maria Silva",
            organization="Gabinete Modelo",
            admin_name="Maria Silva",
            email="maria@gabinete.local",
            phone="(11) 3333-0000",
            whatsapp="(11) 99999-0000",
            city="São Paulo",
            state="SP",
            municipality_ibge_id=3550308,
            audience="camara_municipal",
            preferred_contact="whatsapp",
            discovery_source="instagram",
            payment_status="pending",
        )
        db.session.add(lead)
        db.session.commit()
        lead_id = str(lead.id)

    listed = client.get("/api/v1/platform/interesses-contratacao")
    assert listed.status_code == 200
    assert listed.json["content"][0]["nomeGabinete"] == "Gabinete Modelo"

    updated = client.patch(
        f"/api/v1/platform/interesses-contratacao/{lead_id}",
        headers={"X-CSRF-TOKEN": csrf},
        json={
            "status": "payment_pending",
            "pagamento": "invoice_sent",
            "dataOnboarding": "2026-08-10",
            "observacoesContrato": "Aguardando pagamento.",
            "tentativaContato": {
                "canal": "whatsapp",
                "resultado": "retorno solicitado",
                "observacao": "Administrador pediu proposta formal.",
            },
        },
    )

    assert updated.status_code == 200
    assert updated.json["status"] == "payment_pending"
    assert updated.json["pagamento"] == "invoice_sent"
    assert updated.json["dataOnboarding"] == "2026-08-10"
    assert updated.json["tentativasContato"][0]["canal"] == "whatsapp"

    action_update = client.patch(
        f"/api/v1/platform/interesses-contratacao/{lead_id}",
        headers={"X-CSRF-TOKEN": csrf},
        json={
            "documentoContrato": {"nome": "Contrato assinado", "tipo": "contrato_assinado"},
            "pagamentoItem": {
                "tipo": "onboarding",
                "status": "paid",
                "valor": 1500,
                "vencimento": "2026-08-01",
            },
            "onboarding": {
                "data": "2026-08-15",
                "local": "remota",
                "tecnicoResponsavel": "Equipe GabFlow",
            },
            "gerarContrato": True,
        },
    )
    assert action_update.status_code == 200
    assert action_update.json["pagamentos"][0]["status"] == "paid"
    assert action_update.json["onboarding"]["local"] == "remota"
    assert action_update.json["documentosContrato"][0]["tipo"] == "contrato_gerado"

    converted = client.post(
        f"/api/v1/platform/interesses-contratacao/{lead_id}/converter",
        headers={"X-CSRF-TOKEN": csrf},
        json={"slug": "gabinete-modelo-convertido"},
    )
    assert converted.status_code == 201
    assert converted.json["tenant"]["slug"] == "gabinete-modelo-convertido"
    assert converted.json["tenant"]["modulosHabilitados"] == DEFAULT_MODULES
    assert converted.json["interesse"]["status"] == "converted"


def test_disabled_module_blocks_tenant_endpoint(app, client):
    with app.app_context():
        tenant = db.session.execute(select(Tenant).where(Tenant.slug == "gabinete-a")).scalar_one()
        tenant.enabled_modules = ["solicitacoes"]
        db.session.commit()

    _login_tenant_admin(client)

    allowed = client.get("/api/v1/solicitacoes")
    blocked = client.get("/api/v1/agenda/compromissos")

    assert allowed.status_code == 200
    assert blocked.status_code == 403
    assert blocked.json["error"] == "module_disabled"
    assert blocked.json["module"] == "agenda"


def test_contract_suspension_blocks_login(app, client):
    with app.app_context():
        tenant = db.session.execute(select(Tenant).where(Tenant.slug == "gabinete-a")).scalar_one()
        tenant.contract_status = ContractStatus.SUSPENDED
        db.session.commit()

    response = client.post(
        "/api/v1/auth/login",
        json={"tenant": "gabinete-a", "email": "admin@teste.local", "password": PASSWORD},
    )

    assert response.status_code == 401
