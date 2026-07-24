import hashlib
import uuid

from sqlalchemy import select

from app.auth.security import hash_password
from app.extensions import db
from app.models import (
    GlobalCatalogStatus,
    GlobalDistributionPolicy,
    GlobalEntitlementStatus,
    GlobalKnowledgeChunk,
    GlobalKnowledgeCollection,
    GlobalKnowledgeDocument,
    GlobalKnowledgeDocumentVersion,
    GlobalKnowledgeEntitlement,
    GlobalUpdateMode,
    GlobalVersionStatus,
    RagAssistantQuery,
    RagChunk,
    RagDocument,
    RagDocumentAccess,
    RagDocumentLifecycle,
    RagDocumentVersion,
    RagIngestionStatus,
    Role,
    Tenant,
    User,
)
from app.rag.service import LocalHashEmbeddingProvider

PASSWORD = "SenhaForte123!"  # noqa: S105


def _login(client, tenant="gabinete-a", email="admin@teste.local", password=PASSWORD):
    response = client.post(
        "/api/v1/auth/login",
        json={"tenant": tenant, "email": email, "password": password},
    )
    assert response.status_code == 200
    return client.get_cookie("csrf_access_token").value


def _global_admin(app, email="hierarchy@teste.local"):
    with app.app_context():
        user = User(
            tenant_id=None,
            name="Curador Hierárquico",
            email=email,
            password_hash=hash_password(PASSWORD),
            role=Role.GLOBAL_KNOWLEDGE_ADMIN,
        )
        db.session.add(user)
        db.session.commit()
        return user.id


def _global_source(
    *,
    actor_id,
    name,
    title,
    content,
    policy=GlobalDistributionPolicy.OBRIGATORIA,
    jurisdiction=None,
    publication_status=GlobalVersionStatus.PUBLICADA,
):
    collection_id = uuid.uuid4()
    document_id = uuid.uuid4()
    version_id = uuid.uuid4()
    collection = GlobalKnowledgeCollection(
        id=collection_id,
        name=name,
        distribution_policy=policy,
        jurisdiction=jurisdiction or {},
        status=GlobalCatalogStatus.PUBLICADA,
        created_by_id=actor_id,
    )
    document = GlobalKnowledgeDocument(
        id=document_id,
        collection=collection,
        title=title,
        document_type="LEGISLACAO",
        jurisdiction=jurisdiction or {},
        provenance="Diário oficial verificado.",
        confidence_level=1,
        created_by_id=actor_id,
    )
    version = GlobalKnowledgeDocumentVersion(
        id=version_id,
        document=document,
        version_number=1,
        version_label="1",
        storage_key=f"global/rag/{document_id}/{version_id}/fonte.txt",
        original_name="fonte.txt",
        mime_type="text/plain",
        size_bytes=len(content),
        checksum=hashlib.sha256(content.encode()).hexdigest(),
        extracted_text=content,
        page_count=1,
        embedding_model=LocalHashEmbeddingProvider.model,
        chunk_count=1,
        ingestion_status=RagIngestionStatus.INDEXADO,
        publication_status=publication_status,
        created_by_id=actor_id,
        published_by_id=actor_id,
    )
    chunk = GlobalKnowledgeChunk(
        version=version,
        position=0,
        content=content,
        content_checksum=hashlib.sha256(content.encode()).hexdigest(),
        page_start=1,
        page_end=1,
        embedding=LocalHashEmbeddingProvider().embeddings([content])[0],
        embedding_model=LocalHashEmbeddingProvider.model,
    )
    db.session.add(chunk)
    db.session.flush()
    return collection, document, version


def _private_source(tenant, user, content):
    document_id = uuid.uuid4()
    version_id = uuid.uuid4()
    document = RagDocument(
        id=document_id,
        tenant_id=tenant.id,
        title="Nota técnica do gabinete",
        document_type="PROCEDIMENTO_INTERNO",
        access_level=RagDocumentAccess.INTERNO,
        created_by_id=user.id,
    )
    version = RagDocumentVersion(
        id=version_id,
        tenant_id=tenant.id,
        document=document,
        version_number=1,
        version_label="1",
        lifecycle_status=RagDocumentLifecycle.VIGENTE,
        ingestion_status=RagIngestionStatus.INDEXADO,
        storage_key=f"tenants/{tenant.id}/rag/{document_id}/{version_id}/nota.txt",
        original_name="nota.txt",
        mime_type="text/plain",
        size_bytes=len(content),
        checksum=hashlib.sha256(content.encode()).hexdigest(),
        extracted_text=content,
        page_count=1,
        embedding_model=LocalHashEmbeddingProvider.model,
        chunk_count=1,
        created_by_id=user.id,
    )
    db.session.add(
        RagChunk(
            tenant_id=tenant.id,
            version=version,
            position=0,
            content=content,
            content_checksum=hashlib.sha256(content.encode()).hexdigest(),
            page_start=1,
            page_end=1,
            embedding=LocalHashEmbeddingProvider().embeddings([content])[0],
            embedding_model=LocalHashEmbeddingProvider.model,
        )
    )


def test_hierarchical_retrieval_combines_scopes_and_filters_jurisdiction(app, client):
    actor_id = _global_admin(app)
    with app.app_context():
        tenant = db.session.scalar(select(Tenant).where(Tenant.slug == "gabinete-a"))
        tenant.jurisdiction_state = "MG"
        tenant.jurisdiction_city = "Juiz de Fora"
        tenant.chamber_type = "CAMARA_MUNICIPAL"
        user = db.session.scalar(
            select(User).where(User.tenant_id == tenant.id, User.email == "admin@teste.local")
        )
        _global_source(
            actor_id=actor_id,
            name="Normas nacionais",
            title="Regra nacional de iluminação pública",
            content=(
                "A iluminação pública municipal deve observar planejamento, "
                "segurança, eficiência e manutenção preventiva."
            ),
            jurisdiction={"pais": "BR", "esfera": "FEDERAL"},
        )
        _global_source(
            actor_id=actor_id,
            name="Normas paulistas",
            title="Regra estadual de iluminação pública",
            content=(
                "A iluminação pública municipal deve observar planejamento, "
                "segurança e manutenção em São Paulo."
            ),
            policy=GlobalDistributionPolicy.RESTRITA_JURISDICAO,
            jurisdiction={"uf": "SP"},
        )
        _global_source(
            actor_id=actor_id,
            name="Material interno da plataforma",
            title="Manual privado de iluminação",
            content="Iluminação pública municipal com planejamento e manutenção.",
            policy=GlobalDistributionPolicy.PRIVADA_PLATAFORMA,
        )
        _global_source(
            actor_id=actor_id,
            name="Coleção opcional",
            title="Guia opcional de iluminação",
            content="Iluminação pública municipal eficiente e segura.",
            policy=GlobalDistributionPolicy.OPCIONAL,
        )
        _private_source(
            tenant,
            user,
            (
                "O gabinete acompanha pedidos de iluminação pública, manutenção "
                "preventiva, segurança e eficiência nos bairros."
            ),
        )
        db.session.commit()

    csrf = _login(client)
    response = client.post(
        "/api/v1/assistente/consultas",
        json={
            "consulta": (
                "Como planejar iluminação pública com manutenção preventiva, "
                "segurança e eficiência?"
            )
        },
        headers={"X-CSRF-TOKEN": csrf},
    )

    assert response.status_code == 200
    assert response.json["fundamentada"] is True
    assert response.json["escoposConsultados"] == ["GLOBAL", "PRIVADO"]
    assert response.json["recuperacao"]["global"] >= 1
    assert response.json["recuperacao"]["privado"] >= 1
    assert {source["escopo"] for source in response.json["fontes"]} == {
        "GLOBAL",
        "PRIVADO",
    }
    titles = {source["titulo"] for source in response.json["fontes"]}
    assert "Regra nacional de iluminação pública" in titles
    assert "Nota técnica do gabinete" in titles
    assert "Regra estadual de iluminação pública" not in titles
    assert "Manual privado de iluminação" not in titles
    assert "Guia opcional de iluminação" not in titles
    global_source = next(
        source for source in response.json["fontes"] if source["escopo"] == "GLOBAL"
    )
    assert global_source["rotuloFonte"] == "Fonte GabFlow"
    assert global_source["colecao"] == "Normas nacionais"
    assert global_source["proveniencia"] == "Diário oficial verificado."
    assert global_source["checksumDocumento"]

    with app.app_context():
        recorded = db.session.scalar(select(RagAssistantQuery))
        assert {source["escopo"] for source in recorded.sources} == {
            "GLOBAL",
            "PRIVADO",
        }


def test_optional_subscription_and_pinned_global_version(app, client):
    actor_id = _global_admin(app, "pinning@teste.local")
    with app.app_context():
        collection, document, old_version = _global_source(
            actor_id=actor_id,
            name="Mobilidade opcional",
            title="Guia de mobilidade",
            content="A regra antiga de mobilidade prioriza transporte coletivo integrado.",
            policy=GlobalDistributionPolicy.OPCIONAL,
            publication_status=GlobalVersionStatus.SUBSTITUIDA,
        )
        current_content = (
            "A regra nova de mobilidade prioriza exclusivamente transporte individual."
        )
        current_id = uuid.uuid4()
        current = GlobalKnowledgeDocumentVersion(
            id=current_id,
            document=document,
            version_number=2,
            version_label="2",
            storage_key=f"global/rag/{document.id}/{current_id}/fonte-v2.txt",
            original_name="fonte-v2.txt",
            mime_type="text/plain",
            size_bytes=len(current_content),
            checksum=hashlib.sha256(current_content.encode()).hexdigest(),
            extracted_text=current_content,
            page_count=1,
            embedding_model=LocalHashEmbeddingProvider.model,
            chunk_count=1,
            ingestion_status=RagIngestionStatus.INDEXADO,
            publication_status=GlobalVersionStatus.PUBLICADA,
            created_by_id=actor_id,
            published_by_id=actor_id,
        )
        db.session.add(
            GlobalKnowledgeChunk(
                version=current,
                position=0,
                content=current_content,
                content_checksum=hashlib.sha256(current_content.encode()).hexdigest(),
                page_start=1,
                page_end=1,
                embedding=LocalHashEmbeddingProvider().embeddings([current_content])[0],
                embedding_model=LocalHashEmbeddingProvider.model,
            )
        )
        db.session.commit()
        collection_id = str(collection.id)
        old_version_id = str(old_version.id)

    csrf = _login(client)
    listed = client.get("/api/v1/rag/catalogo-global")
    optional = next(item for item in listed.json["content"] if item["id"] == collection_id)
    assert optional["habilitada"] is False
    assert optional["motivoAcesso"] == "OPT_IN_REQUIRED"

    subscribed = client.patch(
        f"/api/v1/rag/catalogo-global/colecoes/{collection_id}/adesao",
        json={
            "habilitada": True,
            "modoAtualizacao": "FIXADA",
            "versaoFixadaId": old_version_id,
            "justificativa": "Manter a versão aprovada pelo gabinete.",
        },
        headers={"X-CSRF-TOKEN": csrf},
    )
    assert subscribed.status_code == 200
    assert subscribed.json["concessao"]["modoAtualizacao"] == "FIXADA"

    answer = client.post(
        "/api/v1/assistente/consultas",
        json={"consulta": "Qual regra antiga prioriza transporte coletivo integrado?"},
        headers={"X-CSRF-TOKEN": csrf},
    )
    assert answer.status_code == 200
    assert any(source["versaoId"] == old_version_id for source in answer.json["fontes"])
    assert all(
        source["versao"] != "2"
        for source in answer.json["fontes"]
        if source["colecao"] == "Mobilidade opcional"
    )


def test_targeted_collection_requires_global_grant(app, client):
    actor_id = _global_admin(app, "grant@teste.local")
    with app.app_context():
        tenant = db.session.scalar(select(Tenant).where(Tenant.slug == "gabinete-a"))
        collection, _, _ = _global_source(
            actor_id=actor_id,
            name="Acervo direcionado",
            title="Parecer direcionado",
            content="Parecer direcionado sobre processo legislativo municipal seguro.",
            policy=GlobalDistributionPolicy.DIRECIONADA,
        )
        tenant_id = str(tenant.id)
        collection_id = str(collection.id)
        db.session.commit()

    tenant_csrf = _login(client)
    assert all(
        item["id"] != collection_id
        for item in client.get("/api/v1/rag/catalogo-global").json["content"]
    )
    client.post("/api/v1/auth/logout", headers={"X-CSRF-TOKEN": tenant_csrf})

    logged = client.post(
        "/api/v1/auth/login",
        json={"email": "grant@teste.local", "password": PASSWORD},
    )
    assert logged.status_code == 200
    global_csrf = client.get_cookie("csrf_access_token").value
    granted = client.put(
        (f"/api/v1/platform/rag-global/colecoes/{collection_id}/concessoes/{tenant_id}"),
        json={
            "estado": "ATIVA",
            "justificativa": "Gabinete participante do programa controlado.",
        },
        headers={"X-CSRF-TOKEN": global_csrf},
    )
    assert granted.status_code == 200
    assert granted.json["concessao"]["origem"] == "GLOBAL_GRANT"

    client.post("/api/v1/auth/logout", headers={"X-CSRF-TOKEN": global_csrf})
    _login(client)
    visible = client.get("/api/v1/rag/catalogo-global").json["content"]
    assert next(item for item in visible if item["id"] == collection_id)["habilitada"]

    with app.app_context():
        entitlement = db.session.scalar(select(GlobalKnowledgeEntitlement))
        assert entitlement.status == GlobalEntitlementStatus.ATIVA
        assert entitlement.update_mode == GlobalUpdateMode.AUTOMATICA
        assert entitlement.grant_source == "GLOBAL_GRANT"
