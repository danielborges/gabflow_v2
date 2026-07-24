import io
import uuid

from sqlalchemy import select

from app.auth.security import hash_password
from app.extensions import db
from app.models import (
    AuditLog,
    GlobalCatalogStatus,
    GlobalKnowledgeChunk,
    GlobalKnowledgeCollection,
    GlobalKnowledgeDocumentVersion,
    GlobalVersionStatus,
    RagIngestionStatus,
    Role,
    User,
)
from app.outbox.service import process_batch

PASSWORD = "SenhaForte123!"  # noqa: S105


def _csrf_from_cookie(client):
    return client.get_cookie("csrf_access_token").value


def _login_role(app, client, role: Role, email: str):
    with app.app_context():
        db.session.add(
            User(
                tenant_id=None,
                name=f"Usuário {role.value}",
                email=email,
                password_hash=hash_password(PASSWORD),
                role=role,
            )
        )
        db.session.commit()
    response = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": PASSWORD},
    )
    assert response.status_code == 200
    return _csrf_from_cookie(client)


def _create_collection(client, csrf):
    response = client.post(
        "/api/v1/platform/rag-global/colecoes",
        headers={"X-CSRF-TOKEN": csrf},
        json={
            "nome": "Legislação Federal",
            "descricao": "Normas comuns aos gabinetes.",
            "politicaDistribuicao": "OBRIGATORIA",
            "jurisdicao": {"pais": "BR", "esfera": "FEDERAL"},
        },
    )
    assert response.status_code == 201
    return response.json


def _create_document(client, csrf, collection_id):
    response = client.post(
        f"/api/v1/platform/rag-global/colecoes/{collection_id}/documentos",
        headers={"X-CSRF-TOKEN": csrf},
        json={
            "titulo": "Constituição Federal",
            "tipo": "LEGISLACAO",
            "orgao": "Congresso Nacional",
            "jurisdicao": {"pais": "BR", "esfera": "FEDERAL"},
            "proveniencia": "Fonte oficial do Planalto.",
            "nivelConfianca": 1,
        },
    )
    assert response.status_code == 201
    return response.json


def test_only_global_knowledge_admin_manages_catalog(app, client):
    _login_role(app, client, Role.PLATFORM_ADMIN, "platform-catalog@teste.local")
    forbidden = client.get("/api/v1/platform/rag-global/colecoes")
    assert forbidden.status_code == 403

    client.post("/api/v1/auth/logout", headers={"X-CSRF-TOKEN": _csrf_from_cookie(client)})
    csrf = _login_role(
        app,
        client,
        Role.GLOBAL_KNOWLEDGE_ADMIN,
        "knowledge@teste.local",
    )
    me = client.get("/api/v1/auth/me")
    assert me.status_code == 200
    assert me.json["user"]["role"] == "global_knowledge_admin"
    assert me.json["user"]["tenant"] is None

    created = _create_collection(client, csrf)
    assert created["politicaDistribuicao"] == "OBRIGATORIA"
    assert created["jurisdicao"]["pais"] == "BR"

    private = client.get("/api/v1/rag/documentos")
    assert private.status_code == 403


def test_global_document_is_versioned_indexed_and_published(app, client):
    csrf = _login_role(
        app,
        client,
        Role.GLOBAL_KNOWLEDGE_ADMIN,
        "curator@teste.local",
    )
    collection = _create_collection(client, csrf)
    document = _create_document(client, csrf, collection["id"])

    uploaded = client.post(
        (
            f"/api/v1/platform/rag-global/colecoes/{collection['id']}"
            f"/documentos/{document['id']}/versoes"
        ),
        headers={"X-CSRF-TOKEN": csrf},
        data={
            "versao": "1988-original",
            "vigenteDesde": "1988-10-05",
            "urlFonte": "https://www.planalto.gov.br/constituicao/constituicao.htm",
            "arquivo": (
                io.BytesIO(
                    b"Constituicao Federal da Republica Federativa do Brasil. "
                    b"Texto normativo oficial para fundamentacao legislativa."
                ),
                "constituicao.txt",
            ),
        },
        content_type="multipart/form-data",
    )
    assert uploaded.status_code == 202
    assert uploaded.json["statusIngestao"] == "PENDENTE"
    assert uploaded.json["estadoPublicacao"] == "RASCUNHO"
    assert uploaded.json["downloadUrl"]

    premature = client.patch(
        (
            f"/api/v1/platform/rag-global/colecoes/{collection['id']}"
            f"/documentos/{document['id']}/versoes/{uploaded.json['id']}/estado"
        ),
        headers={"X-CSRF-TOKEN": csrf},
        json={"estado": "PUBLICADA"},
    )
    assert premature.status_code == 409

    with app.app_context():
        result = process_batch("global-catalog-test")
        assert result.succeeded == 1
        version = db.session.get(GlobalKnowledgeDocumentVersion, uuid.UUID(uploaded.json["id"]))
        assert version.ingestion_status == RagIngestionStatus.INDEXADO
        assert version.chunk_count > 0
        assert db.session.scalar(select(GlobalKnowledgeChunk.id)) is not None

    published = client.patch(
        (
            f"/api/v1/platform/rag-global/colecoes/{collection['id']}"
            f"/documentos/{document['id']}/versoes/{uploaded.json['id']}/estado"
        ),
        headers={"X-CSRF-TOKEN": csrf},
        json={"estado": "PUBLICADA"},
    )
    assert published.status_code == 200
    assert published.json["estadoPublicacao"] == "PUBLICADA"
    assert published.json["publicadaEm"]

    with app.app_context():
        stored_collection = db.session.get(GlobalKnowledgeCollection, uuid.UUID(collection["id"]))
        version = db.session.get(GlobalKnowledgeDocumentVersion, uuid.UUID(uploaded.json["id"]))
        assert stored_collection.status == GlobalCatalogStatus.PUBLICADA
        assert version.publication_status == GlobalVersionStatus.PUBLICADA
        actions = set(db.session.scalars(select(AuditLog.action)))
        assert {
            "rag_global.collection_created",
            "rag_global.document_created",
            "rag_global.version_created",
            "rag_global.version_indexed",
            "rag_global.version_publicada",
        }.issubset(actions)

    revoked = client.patch(
        (
            f"/api/v1/platform/rag-global/colecoes/{collection['id']}"
            f"/documentos/{document['id']}/versoes/{uploaded.json['id']}/estado"
        ),
        headers={"X-CSRF-TOKEN": csrf},
        json={"estado": "REVOGADA"},
    )
    assert revoked.status_code == 200
    assert revoked.json["estadoPublicacao"] == "REVOGADA"

    collection_after_revoke = client.get(f"/api/v1/platform/rag-global/colecoes/{collection['id']}")
    assert collection_after_revoke.status_code == 200
    assert collection_after_revoke.json["estado"] == "SUSPENSA"
