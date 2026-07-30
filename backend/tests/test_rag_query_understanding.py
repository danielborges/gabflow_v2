import hashlib
import uuid

from sqlalchemy import select

from app.extensions import db
from app.models import (
    RagChunk,
    RagDocument,
    RagDocumentAccess,
    RagDocumentLifecycle,
    RagDocumentVersion,
    RagIngestionStatus,
    Tenant,
    User,
)
from app.rag.query_understanding import understand_documentary_query
from app.rag.service import LocalHashEmbeddingProvider

PASSWORD = "SenhaForte123!"  # noqa: S105


def _login(client):
    response = client.post(
        "/api/v1/auth/login",
        json={
            "tenant": "gabinete-a",
            "email": "admin@teste.local",
            "password": PASSWORD,
        },
    )
    assert response.status_code == 200
    return client.get_cookie("csrf_access_token").value


def _source(tenant, user, title, document_type, content):
    document_id = uuid.uuid4()
    version_id = uuid.uuid4()
    document = RagDocument(
        id=document_id,
        tenant_id=tenant.id,
        title=title,
        document_type=document_type,
        agency="Secretaria Municipal de Mobilidade",
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
        storage_key=f"tenants/{tenant.id}/rag/{document_id}/{version_id}/fonte.txt",
        original_name="fonte.txt",
        mime_type="text/plain",
        size_bytes=len(content.encode()),
        checksum=hashlib.sha256(content.encode()).hexdigest(),
        extracted_text=content,
        page_count=1,
        embedding_model=LocalHashEmbeddingProvider.model,
        chunk_count=1,
        created_by_id=user.id,
    )
    chunk = RagChunk(
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
    db.session.add(chunk)
    return document


def test_understanding_extracts_normative_reference_theme_period_and_expansions(app):
    with app.app_context():
        plan = understand_documentary_query(
            "Quais regras de transporte constam no Decreto nº 9.117/2007 "
            "entre 2020 e 2024?"
        )

        assert plan.intent == "ATO_NORMATIVO_ESPECIFICO"
        assert plan.document_types == ("DECRETO",)
        assert plan.themes == ("MOBILIDADE_URBANA",)
        assert plan.references == ("DECRETO 9.117/2007",)
        assert plan.filters == {
            "tipoDocumento": "DECRETO",
            "tema": "MOBILIDADE_URBANA",
            "inicio": "2020-01-01",
            "fim": "2024-12-31",
        }
        assert len(plan.expansions) == 3
        assert plan.search_queries[0].startswith("Quais regras")
        assert "transporte" in plan.retrieval_filters["temaBusca"]


def test_understanding_uses_word_boundaries_and_validates_explicit_filters(app):
    with app.app_context():
        plan = understand_documentary_query(
            "protocolo legislativo parecer comissão votação",
            explicit_filters={
                "tipoDocumento": "PARECER",
                "orgao": "Câmara Municipal",
                "jurisdicao": "Campinas",
            },
        )

        assert plan.themes == ()
        assert plan.filters == {
            "tipoDocumento": "PARECER",
            "orgao": "Câmara Municipal",
            "jurisdicao": "Campinas",
        }
        assert plan.expansions == ()
        normative = understand_documentary_query(
            "O que consta no Decreto 9.117 de 2007?"
        )
        assert normative.references == ("DECRETO 9.117/2007",)


def test_documentary_filters_and_expansion_are_applied_before_reranking(
    app,
    client,
):
    with app.app_context():
        tenant = db.session.scalar(select(Tenant).where(Tenant.slug == "gabinete-a"))
        user = db.session.scalar(
            select(User).where(
                User.tenant_id == tenant.id,
                User.email == "admin@teste.local",
            )
        )
        relevant = _source(
            tenant,
            user,
            "Plano de mobilidade urbana",
            "DECRETO",
            "A mobilidade urbana prioriza circulação viária e trânsito sustentável.",
        )
        relevant_id = str(relevant.id)
        _source(
            tenant,
            user,
            "Manual tributário",
            "INSTRUCAO",
            "A arrecadação de impostos segue o calendário fiscal municipal.",
        )
        db.session.commit()

    csrf = _login(client)
    response = client.post(
        "/api/v1/assistente/consultas",
        json={
            "consulta": "Quais normas tratam de ônibus?",
            "limite": 5,
            "filtros": {
                "tipoDocumento": "DECRETO",
                "orgao": "Secretaria Municipal de Mobilidade",
            },
        },
        headers={"X-CSRF-TOKEN": csrf},
    )

    assert response.status_code == 200
    assert [source["documentoId"] for source in response.json["fontes"]] == [
        relevant_id
    ]
    assert response.json["filtrosAplicados"] == {
        "tema": "MOBILIDADE_URBANA",
        "tipoDocumento": "DECRETO",
        "orgao": "Secretaria Municipal de Mobilidade",
    }
    understanding = response.json["entendimentoConsulta"]
    assert understanding["intencaoDocumental"] == "PESQUISA_TEMATICA"
    assert understanding["consultasExpandidas"]
    assert response.json["recuperacao"]["expansaoConsultaAplicada"] is True
    assert response.json["recuperacao"]["quantidadeConsultasBusca"] > 1
