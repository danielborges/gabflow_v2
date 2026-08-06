import io
import uuid
from datetime import datetime
from pathlib import Path

from PIL import Image
from sqlalchemy import select

from app.extensions import db
from app.models import Citizen, Notification, RequestCategory, Tenant
from app.security.encryption import MAGIC

PASSWORD_A = "SenhaForte123!"  # noqa: S105
PASSWORD_B = "OutraSenha123!"  # noqa: S105


def login(client, tenant="gabinete-a", password=PASSWORD_A):
    email = "admin-b@teste.local" if tenant == "gabinete-b" else "admin@teste.local"
    response = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": password},
    )
    assert response.status_code == 200
    return {
        "csrf": client.get_cookie("csrf_access_token").value,
        "user": response.json["user"],
    }


def post(client, path, csrf, payload):
    return client.post(path, json=payload, headers={"X-CSRF-TOKEN": csrf})


def patch(client, path, csrf, payload):
    return client.patch(path, json=payload, headers={"X-CSRF-TOKEN": csrf})


def create_service_request(client, csrf, **extra):
    payload = {
        "origem": "WHATSAPP",
        "titulo": "Demanda de teste",
        "descricao": "Descrição válida para a demanda.",
        **extra,
    }
    response = post(client, "/api/v1/solicitacoes", csrf, payload)
    assert response.status_code == 201
    return response.json


def test_citizen_contacts_consents_and_history_are_tenant_scoped(app, client):
    auth = login(client)
    response = post(
        client,
        "/api/v1/cidadaos",
        auth["csrf"],
        {
            "nome": "Maria da Silva",
            "contatos": [{"tipo": "TELEFONE", "valor": "32999999999"}],
            "enderecos": [{"logradouro": "Rua A", "numero": "10"}],
            "canalPreferencial": "WHATSAPP",
            "consentimentoContato": True,
            "consentimentoDivulgacao": False,
            "baseLegal": "EXECUCAO_POLITICA_PUBLICA",
        },
    )
    assert response.status_code == 201
    citizen = response.json
    assert citizen["consentimentoContato"] is True
    assert citizen["consentimentoDivulgacao"] is False

    created = create_service_request(client, auth["csrf"], cidadaoId=citizen["id"])
    detail = client.get(f"/api/v1/cidadaos/{citizen['id']}")
    assert detail.status_code == 200
    assert detail.json["solicitacoes"][0]["protocolo"] == created["protocolo"]

    client.post("/api/v1/auth/logout", headers={"X-CSRF-TOKEN": auth["csrf"]})
    login(client, tenant="gabinete-b", password=PASSWORD_B)
    assert client.get(f"/api/v1/cidadaos/{citizen['id']}").status_code == 404

    with app.app_context():
        assert db.session.execute(select(Citizen)).scalars().one().legal_basis


def test_organization_create_and_update(client):
    auth = login(client)
    created = post(
        client,
        "/api/v1/organizacoes",
        auth["csrf"],
        {
            "tipo": "ASSOCIACAO",
            "nome": "Associação do Bairro",
            "contatos": [{"tipo": "EMAIL", "valor": "contato@example.org"}],
            "territorio": "Centro",
        },
    )
    assert created.status_code == 201
    updated = patch(
        client,
        f"/api/v1/organizacoes/{created.json['id']}",
        auth["csrf"],
        {"territorio": "Centro e Zona Norte"},
    )
    assert updated.status_code == 200
    assert updated.json["territorio"] == "Centro e Zona Norte"


def test_citizen_v2_documents_vip_and_organization_link_are_persisted_securely(app, client):
    auth = login(client)
    organization = post(
        client,
        "/api/v1/organizacoes",
        auth["csrf"],
        {"tipo": "ASSOCIACAO", "nome": "Associação Comunitária"},
    ).json

    created = post(
        client,
        "/api/v1/cidadaos",
        auth["csrf"],
        {
            "nome": "Marina Alves",
            "profissao": "Professora",
            "dataNascimento": "1987-05-14",
            "cpf": "529.982.247-25",
            "tituloEleitor": "123456789012",
            "vip": True,
            "baseLegal": "EXECUCAO_POLITICA_PUBLICA",
            "organizacaoIds": [organization["id"]],
        },
    )

    assert created.status_code == 201
    assert created.json["cpf"] == "52998224725"
    assert created.json["cpfFinal"] == "25"
    assert created.json["tituloEleitor"] == "123456789012"
    assert created.json["profissao"] == "Professora"
    assert created.json["dataNascimento"] == "1987-05-14"
    assert created.json["vip"] is True
    assert created.json["cadastradoPor"] == "Admin A"
    assert created.json["organizacoes"][0]["id"] == organization["id"]

    with app.app_context():
        citizen = db.session.execute(select(Citizen)).scalars().one()
        assert "52998224725" not in citizen.cpf_ciphertext
        assert "123456789012" not in citizen.electoral_title_ciphertext
        assert len(citizen.cpf_fingerprint) == 64
        assert citizen.created_by_id is not None


def test_citizen_v2_rejects_duplicate_cpf_and_returns_existing_citizen(client):
    auth = login(client)
    first = post(
        client,
        "/api/v1/cidadaos",
        auth["csrf"],
        {
            "nome": "Maria Existente",
            "cpf": "52998224725",
            "baseLegal": "EXECUCAO_POLITICA_PUBLICA",
        },
    )
    duplicate = post(
        client,
        "/api/v1/cidadaos",
        auth["csrf"],
        {
            "nome": "Outra Maria",
            "cpf": "529.982.247-25",
            "baseLegal": "EXECUCAO_POLITICA_PUBLICA",
        },
    )

    assert duplicate.status_code == 409
    assert duplicate.json["code"] == "CPF_DUPLICADO"
    assert duplicate.json["cidadao"]["id"] == first.json["id"]
    assert duplicate.json["cidadao"]["nome"] == "Maria Existente"


def test_citizen_v2_duplicate_check_reports_homonyms(client):
    auth = login(client)
    post(
        client,
        "/api/v1/cidadaos",
        auth["csrf"],
        {"nome": "João da Silva", "baseLegal": "EXECUCAO_POLITICA_PUBLICA"},
    )

    response = post(
        client,
        "/api/v1/cidadaos/verificar-duplicidade",
        auth["csrf"],
        {"nome": "  Joao   da Silva "},
    )

    assert response.status_code == 200
    assert response.json["cpfDuplicado"] is None
    assert response.json["homonimos"][0]["nome"] == "João da Silva"


def test_category_applies_sla_to_request(app, client):
    auth = login(client)
    category = post(
        client,
        "/api/v1/admin/categorias",
        auth["csrf"],
        {"nome": "Urgência de saúde", "slaHoras": 12},
    )
    assert category.status_code == 201

    created = create_service_request(
        client,
        auth["csrf"],
        categoriaId=category.json["id"],
    )
    assert created["categoria"] == "Urgência de saúde"
    assert created["situacaoSla"] == "PROXIMO_DO_PRAZO"
    due_at = datetime.fromisoformat(created["prazo"])
    created_at = datetime.fromisoformat(created["criadaEm"])
    assert round((due_at - created_at).total_seconds() / 3600) == 12

    with app.app_context():
        assert db.session.execute(select(RequestCategory)).scalars().one().sla_hours == 12


def test_assignment_task_and_notifications(app, client):
    auth = login(client)
    created = create_service_request(
        client,
        auth["csrf"],
        responsavelId=auth["user"]["id"],
    )
    task = post(
        client,
        f"/api/v1/solicitacoes/{created['id']}/tarefas",
        auth["csrf"],
        {
            "titulo": "Verificar demanda no local",
            "responsavelId": auth["user"]["id"],
            "prioridade": "ALTA",
        },
    )
    assert task.status_code == 201
    assert task.json["status"] == "PENDENTE"

    completed = patch(
        client,
        f"/api/v1/tarefas/{task.json['id']}",
        auth["csrf"],
        {"status": "CONCLUIDA"},
    )
    assert completed.json["concluidaEm"] is not None

    notifications = client.get("/api/v1/notificacoes")
    assert notifications.status_code == 200
    assert notifications.json["naoLidas"] == 2

    with app.app_context():
        assert len(db.session.execute(select(Notification)).scalars().all()) == 2


def test_duplicate_group_keeps_individual_protocols(client):
    auth = login(client)
    first = create_service_request(client, auth["csrf"], titulo="Buraco na Rua A")
    second = create_service_request(client, auth["csrf"], titulo="Mesmo buraco na Rua A")

    grouped = post(
        client,
        "/api/v1/solicitacoes/agrupar-duplicadas",
        auth["csrf"],
        {
            "solicitacaoIds": [first["id"], second["id"]],
            "motivo": "Mesmo local e ocorrência",
        },
    )
    assert grouped.status_code == 201

    detail = client.get(f"/api/v1/solicitacoes/{first['id']}")
    assert detail.json["protocolo"] == first["protocolo"]
    assert detail.json["duplicidades"][0]["protocolo"] == second["protocolo"]


def test_attachment_upload_signed_download_and_malware_block(client):
    auth = login(client)
    created = create_service_request(client, auth["csrf"])

    uploaded = client.post(
        f"/api/v1/solicitacoes/{created['id']}/anexos",
        data={"arquivo": (io.BytesIO(b"conteudo seguro"), "evidencia.txt")},
        headers={"X-CSRF-TOKEN": auth["csrf"]},
        content_type="multipart/form-data",
    )
    assert uploaded.status_code == 201
    assert uploaded.json["statusVerificacao"] == "LIMPO"
    download = client.get(uploaded.json["downloadUrl"])
    assert download.status_code == 200
    assert download.data == b"conteudo seguro"

    blocked = client.post(
        f"/api/v1/solicitacoes/{created['id']}/anexos",
        data={
            "arquivo": (
                io.BytesIO(b"X5O!P%@AP[4\\PZX54(P^)7CC)7}$EICAR"),
                "suspeito.txt",
            )
        },
        headers={"X-CSRF-TOKEN": auth["csrf"]},
        content_type="multipart/form-data",
    )
    assert blocked.status_code == 422
    assert "bloqueado" in blocked.json["message"]


def test_notification_cannot_be_read_by_another_tenant(client):
    auth = login(client)
    create_service_request(client, auth["csrf"], responsavelId=auth["user"]["id"])
    item = client.get("/api/v1/notificacoes").json["content"][0]
    client.post("/api/v1/auth/logout", headers={"X-CSRF-TOKEN": auth["csrf"]})
    other = login(client, tenant="gabinete-b", password=PASSWORD_B)
    response = patch(
        client,
        f"/api/v1/notificacoes/{item['id']}/lida",
        other["csrf"],
        {},
    )
    assert response.status_code == 404


def test_citizen_photo_is_sanitized_encrypted_and_tenant_scoped(app, client):
    auth = login(client)
    citizen = post(
        client,
        "/api/v1/cidadaos",
        auth["csrf"],
        {"nome": "Pessoa com Foto", "baseLegal": "EXECUCAO_POLITICA_PUBLICA"},
    ).json
    source = io.BytesIO()
    Image.new("RGB", (900, 500), color=(22, 80, 120)).save(
        source, format="JPEG", exif=b"Exif\x00\x00metadata"
    )
    uploaded = client.put(
        f"/api/v1/cidadaos/{citizen['id']}/foto",
        data={"foto": (io.BytesIO(source.getvalue()), "camera.jpg", "image/jpeg")},
        headers={"X-CSRF-TOKEN": auth["csrf"]},
        content_type="multipart/form-data",
    )
    assert uploaded.status_code == 200
    photo = client.get(uploaded.json["fotoUrl"])
    assert photo.status_code == 200
    assert photo.content_type == "image/webp"
    with Image.open(io.BytesIO(photo.data)) as processed:
        assert processed.size == (640, 640)
        assert not processed.getexif()

    with app.app_context():
        item = db.session.get(Citizen, uuid.UUID(citizen["id"]))
        stored = Path(app.config["ATTACHMENT_STORAGE_PATH"]) / item.photo_storage_key
        assert stored.read_bytes().startswith(MAGIC)
        assert b"metadata" not in stored.read_bytes()

    client.post("/api/v1/auth/logout", headers={"X-CSRF-TOKEN": auth["csrf"]})
    login(client, tenant="gabinete-b", password=PASSWORD_B)
    assert client.get(uploaded.json["fotoUrl"]).status_code == 404


def test_structured_address_resolves_neighborhood_and_active_territory(app, client):
    with app.app_context():
        tenant = db.session.execute(select(Tenant).where(Tenant.slug == "gabinete-a")).scalar_one()
        tenant.jurisdiction_bounds = {
            "minLatitude": -22.0,
            "maxLatitude": -20.0,
            "minLongitude": -44.0,
            "maxLongitude": -42.0,
        }
        db.session.commit()
    auth = login(client)
    territory = post(
        client,
        "/api/v1/admin/territorios",
        auth["csrf"],
        {
            "nome": "São Pedro",
            "aliases": ["Jardim SP", "S. Pedro"],
            "geometria": {
                "type": "Polygon",
                "coordinates": [
                    [
                        [-43.40, -21.80],
                        [-43.30, -21.80],
                        [-43.30, -21.70],
                        [-43.40, -21.70],
                        [-43.40, -21.80],
                    ]
                ],
            },
        },
    )
    assert territory.status_code == 201
    assert territory.json["aliases"] == ["Jardim SP", "S. Pedro"]
    assert territory.json["geometria"]["type"] == "Polygon"
    address = {
        "endereco": "Rua A, 10 - Nome divergente",
        "bairro": "Nome retornado pelo provedor",
        "cidade": "Juiz de Fora",
        "uf": "MG",
        "latitude": -21.76,
        "longitude": -43.35,
        "placeId": "place-123",
    }
    resolved = post(client, "/api/v1/enderecos/resolver", auth["csrf"], address)
    assert resolved.status_code == 200
    assert resolved.json["bairro"] == "Nome retornado pelo provedor"
    assert resolved.json["territorio"] == "São Pedro"
    assert resolved.json["statusResolucao"] == "RESOLVIDO"
    assert resolved.json["metodoResolucao"] == "POLIGONO"

    alias_address = post(
        client,
        "/api/v1/enderecos/resolver",
        auth["csrf"],
        {"endereco": "Endereço sem coordenadas", "bairro": "jardim sp"},
    )
    assert alias_address.status_code == 200
    assert alias_address.json["territorio"] == "São Pedro"
    assert alias_address.json["metodoResolucao"] == "ALIAS"

    collision = post(
        client,
        "/api/v1/admin/territorios",
        auth["csrf"],
        {"nome": "Outro território", "aliases": ["Sao Pedro"]},
    )
    assert collision.status_code == 409

    created = post(
        client,
        "/api/v1/cidadaos",
        auth["csrf"],
        {
            "nome": "Pessoa do Bairro",
            "baseLegal": "EXECUCAO_POLITICA_PUBLICA",
            "endereco": address,
        },
    )
    assert created.status_code == 201
    assert created.json["enderecos"][0]["territorio"] == "São Pedro"


def test_citizen_etag_history_and_cursor_pages_are_safe(client):
    auth = login(client)
    citizens = []
    for name in ("Ana Cursor", "Bruno Cursor", "Carla Cursor"):
        response = post(
            client,
            "/api/v1/cidadaos",
            auth["csrf"],
            {"nome": name, "baseLegal": "EXECUCAO_POLITICA_PUBLICA"},
        )
        assert response.status_code == 201
        citizens.append(response.json)

    first_page = client.get("/api/v1/cidadaos?limite=2")
    assert first_page.status_code == 200
    assert [item["nome"] for item in first_page.json["content"]] == [
        "Ana Cursor",
        "Bruno Cursor",
    ]
    assert first_page.json["letrasDisponiveis"] == ["A", "B", "C"]
    assert first_page.json["proximoCursor"]
    by_letter = client.get("/api/v1/cidadaos", query_string={"letra": "C"})
    assert [item["nome"] for item in by_letter.json["content"]] == ["Carla Cursor"]
    assert by_letter.json["letrasDisponiveis"] == ["A", "B", "C"]
    assert (
        client.get(
            "/api/v1/cidadaos",
            query_string={"letra": "A", "cursor": first_page.json["proximoCursor"]},
        ).status_code
        == 422
    )
    second_page = client.get(
        "/api/v1/cidadaos",
        query_string={"limite": 2, "cursor": first_page.json["proximoCursor"]},
    )
    assert [item["nome"] for item in second_page.json["content"]] == ["Carla Cursor"]
    assert client.get("/api/v1/cidadaos?cursor=adulterado").status_code == 422

    citizen = citizens[0]
    detail = client.get(f"/api/v1/cidadaos/{citizen['id']}")
    assert detail.headers["ETag"] == '"1"'
    missing_version = client.patch(
        f"/api/v1/cidadaos/{citizen['id']}",
        json={"nome": "Ana Atualizada"},
        headers={"X-CSRF-TOKEN": auth["csrf"]},
    )
    assert missing_version.status_code == 428
    stale = client.patch(
        f"/api/v1/cidadaos/{citizen['id']}",
        json={"nome": "Ana Atualizada"},
        headers={"X-CSRF-TOKEN": auth["csrf"], "If-Match": '"99"'},
    )
    assert stale.status_code == 412
    updated = client.patch(
        f"/api/v1/cidadaos/{citizen['id']}",
        json={"nome": "Ana Atualizada"},
        headers={"X-CSRF-TOKEN": auth["csrf"], "If-Match": detail.headers["ETag"]},
    )
    assert updated.status_code == 200
    assert updated.headers["ETag"] == '"2"'

    history = client.get(f"/api/v1/cidadaos/{citizen['id']}/historico?limite=1")
    assert history.status_code == 200
    assert history.json["content"][0]["acao"] == "CADASTRO_ATUALIZADO"
    assert "nome" in history.json["content"][0]["camposAlterados"]
    assert "Ana Atualizada" not in str(history.json)
    assert history.json["proximoCursor"]
    older = client.get(
        f"/api/v1/cidadaos/{citizen['id']}/historico",
        query_string={"cursor": history.json["proximoCursor"], "limite": 1},
    )
    assert older.json["content"][0]["acao"] == "CADASTRO_CRIADO"


def test_citizen_requests_and_flow_metrics_are_paginated_and_tenant_scoped(client):
    auth = login(client)
    citizen = post(
        client,
        "/api/v1/cidadaos",
        auth["csrf"],
        {"nome": "Pessoa Timeline", "baseLegal": "EXECUCAO_POLITICA_PUBLICA"},
    ).json
    for index in range(3):
        create_service_request(
            client,
            auth["csrf"],
            cidadaoId=citizen["id"],
            titulo=f"Demanda {index}",
        )
    page = client.get(f"/api/v1/cidadaos/{citizen['id']}/solicitacoes?limite=2")
    assert page.status_code == 200
    assert len(page.json["content"]) == 2
    assert page.json["proximoCursor"]
    remainder = client.get(
        f"/api/v1/cidadaos/{citizen['id']}/solicitacoes",
        query_string={"limite": 2, "cursor": page.json["proximoCursor"]},
    )
    assert len(remainder.json["content"]) == 1

    metric = post(
        client,
        "/api/v1/cidadaos/metricas-fluxo",
        auth["csrf"],
        {"evento": "CADASTRO_CONCLUIDO", "duracaoMs": 42000},
    )
    assert metric.status_code == 204
    metrics = client.get("/api/v1/cidadaos/metricas-fluxo")
    assert metrics.status_code == 200
    assert metrics.json["eventos"]["CADASTRO_CONCLUIDO"] == 1
    assert metrics.json["tempoMedioCadastroMs"] == 42000

    client.post("/api/v1/auth/logout", headers={"X-CSRF-TOKEN": auth["csrf"]})
    login(client, tenant="gabinete-b", password=PASSWORD_B)
    assert client.get(f"/api/v1/cidadaos/{citizen['id']}/historico").status_code == 404
