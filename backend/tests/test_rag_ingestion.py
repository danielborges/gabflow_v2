import io
import uuid

from sqlalchemy import select

from app.extensions import db
from app.models import AuditLog, RagChunk, RagDocument
from app.outbox.service import process_batch

PASSWORD = "SenhaForte123!"  # noqa: S105


def _login(client, tenant="gabinete-a", password=PASSWORD):
    response = client.post(
        "/api/v1/auth/login",
        json={"tenant": tenant, "email": "admin@teste.local", "password": password},
    )
    assert response.status_code == 200
    return client.get_cookie("csrf_access_token").value


def _upload(client, csrf, path, fields, name="lei.txt", content=None):
    payload = {
        **fields,
        "arquivo": (
            io.BytesIO(
                content
                or (
                    "Art. 1º Compete ao Município manter os serviços públicos e garantir "
                    "a iluminação adequada das praças, vias e equipamentos urbanos. "
                    "Art. 2º A administração publicará relatórios anuais de execução."
                ).encode()
            ),
            name,
        ),
    }
    return client.post(
        path,
        data=payload,
        headers={"X-CSRF-TOKEN": csrf},
        content_type="multipart/form-data",
    )


def test_rag_document_ingestion_versions_and_lifecycle(app, client):
    csrf = _login(client)
    created = _upload(
        client,
        csrf,
        "/api/v1/rag/documentos",
        {
            "titulo": "Lei de Serviços Urbanos",
            "tipo": "LEGISLACAO",
            "orgao": "Câmara Municipal",
            "nivelAcesso": "INTERNO",
            "versao": "2026.1",
            "vigenteDesde": "2026-01-01",
            "urlFonte": "https://leis.example.test/servicos-urbanos",
        },
    )
    assert created.status_code == 202
    document_id = created.json["id"]
    version_id = created.json["versoes"][0]["id"]
    assert created.json["versoes"][0]["statusIngestao"] == "PENDENTE"
    assert created.json["versoes"][0]["estado"] == "RASCUNHO"

    with app.app_context():
        result = process_batch("rag-test-worker")
        assert result.succeeded == 1

    detail = client.get(f"/api/v1/rag/documentos/{document_id}")
    assert detail.status_code == 200
    version = detail.json["versoes"][0]
    assert version["statusIngestao"] == "INDEXADO"
    assert version["fragmentos"] >= 1
    assert version["modeloEmbedding"] == "gabflow-hash-embedding-v1"
    assert version["checksum"]

    published = client.patch(
        f"/api/v1/rag/documentos/{document_id}/versoes/{version_id}/estado",
        json={"estado": "VIGENTE"},
        headers={"X-CSRF-TOKEN": csrf},
    )
    assert published.status_code == 200
    assert published.json["estado"] == "VIGENTE"

    second = _upload(
        client,
        csrf,
        f"/api/v1/rag/documentos/{document_id}/versoes",
        {"versao": "2026.2", "vigenteDesde": "2026-07-01"},
        name="lei-revisada.txt",
    )
    assert second.status_code == 202
    with app.app_context():
        assert process_batch("rag-version-worker").succeeded == 1
    promoted = client.patch(
        f"/api/v1/rag/documentos/{document_id}/versoes/{second.json['id']}/estado",
        json={"estado": "VIGENTE"},
        headers={"X-CSRF-TOKEN": csrf},
    )
    assert promoted.status_code == 200
    final = client.get(f"/api/v1/rag/documentos/{document_id}").json
    assert [item["estado"] for item in final["versoes"]] == ["VIGENTE", "HISTORICO"]

    with app.app_context():
        assert db.session.execute(select(RagDocument)).scalar_one()
        chunks = db.session.execute(select(RagChunk)).scalars().all()
        assert chunks and len(chunks[0].embedding) == 128
        actions = set(db.session.execute(select(AuditLog.action)).scalars())
        assert {
            "rag_document.created",
            "rag_document.indexed",
            "rag_document.version_created",
            "rag_document.lifecycle_changed",
        }.issubset(actions)


def test_rag_ingestion_failure_reprocess_and_tenant_isolation(app, client):
    csrf = _login(client)
    created = _upload(
        client,
        csrf,
        "/api/v1/rag/documentos",
        {
            "titulo": "Documento restrito",
            "tipo": "PROCEDIMENTO_INTERNO",
            "nivelAcesso": "RESTRITO",
            "versao": "1",
        },
        content=b"curto",
    )
    assert created.status_code == 202
    document_id = created.json["id"]
    version_id = created.json["versoes"][0]["id"]
    with app.app_context():
        assert process_batch("rag-failure-worker").failed == 1
    failed = client.get(f"/api/v1/rag/documentos/{document_id}").json["versoes"][0]
    assert failed["statusIngestao"] == "FALHOU"
    assert "texto suficiente" in failed["erro"]

    reprocessed = client.post(
        f"/api/v1/rag/documentos/{document_id}/versoes/{version_id}/reprocessar",
        headers={"X-CSRF-TOKEN": csrf},
    )
    assert reprocessed.status_code == 202
    assert reprocessed.json["statusIngestao"] == "PENDENTE"

    client.post("/api/v1/auth/logout", headers={"X-CSRF-TOKEN": csrf})
    other_csrf = _login(client, "gabinete-b", "OutraSenha123!")
    assert client.get("/api/v1/rag/documentos").json["content"] == []
    assert client.get(f"/api/v1/rag/documentos/{document_id}").status_code == 404
    assert (
        client.post(
            f"/api/v1/rag/documentos/{document_id}/versoes/{uuid.uuid4()}/reprocessar",
            headers={"X-CSRF-TOKEN": other_csrf},
        ).status_code
        == 404
    )


def test_rag_upload_validates_metadata_and_file_type(client):
    csrf = _login(client)
    invalid_url = _upload(
        client,
        csrf,
        "/api/v1/rag/documentos",
        {
            "titulo": "Documento inválido",
            "tipo": "LEGISLACAO",
            "versao": "1",
            "urlFonte": "file:///segredo",
        },
    )
    assert invalid_url.status_code == 422

    invalid_file = _upload(
        client,
        csrf,
        "/api/v1/rag/documentos",
        {"titulo": "Executável", "tipo": "OUTRO", "versao": "1"},
        name="arquivo.exe",
        content=b"MZ-not-allowed",
    )
    assert invalid_file.status_code == 422
