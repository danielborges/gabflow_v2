import hashlib
import uuid

from sqlalchemy import select

from app.extensions import db
from app.models import AuditLog, RagEvaluationQuestion
from tests.test_rag_feedback_capture import _login, _seed_query


def _reference(seeded, *, second=False):
    prefix = "second_" if second else ""
    return {
        "documentoId": seeded[f"{prefix}document_id"],
        "versaoId": seeded[f"{prefix}version_id"],
        "chunkId": seeded[f"{prefix}chunk_id"],
        "escopo": "PRIVADO",
    }


def _payload(seeded):
    return {
        "consultaId": seeded["query_id"],
        "motivos": [
            "DOCUMENTOS_DESCONEXOS",
            "FONTE_RELEVANTE_AUSENTE",
        ],
        "severidade": "ALTA",
        "tags": ["licitações", "ranking"],
        "fontesEsperadas": [_reference(seeded)],
        "fontesIrrelevantes": [_reference(seeded, second=True)],
        "metodoEsperado": "DOCUMENTAL",
        "filtrosEsperados": {"tema": "licitações"},
        "observacoes": "Caso reproduzido em teste manual.",
    }


def test_regression_case_captures_minimized_baseline_and_is_idempotent(app, client):
    seeded = _seed_query(app)
    csrf = _login(client)

    created = client.post(
        "/api/v1/assistente/avaliacoes/casos-regressao",
        json=_payload(seeded),
        headers={"X-CSRF-TOKEN": csrf},
    )

    assert created.status_code == 201
    data = created.get_json()
    assert data["origem"] == "REGRESSAO"
    assert data["consultaOrigemId"] == seeded["query_id"]
    assert data["motivosFalha"] == [
        "DOCUMENTOS_DESCONEXOS",
        "FONTE_RELEVANTE_AUSENTE",
    ]
    assert data["severidade"] == "ALTA"
    assert data["tags"] == ["licitações", "ranking"]
    assert data["fontesEsperadas"] == [_reference(seeded)]
    assert data["hardNegatives"] == [_reference(seeded, second=True)]
    assert data["baseline"]["schemaVersion"] == "rag-regression-baseline-v1"
    assert data["baseline"]["consultaId"] == seeded["query_id"]
    assert data["baseline"]["respostaHash"] == hashlib.sha256(
        b"A regra consta na fonte citada."
    ).hexdigest()
    assert "resposta" not in data["baseline"]
    assert all("trecho" not in source for source in data["baseline"]["fontes"])
    assert data["baselineCapturadoEm"] is not None

    repeated = client.post(
        "/api/v1/assistente/avaliacoes/casos-regressao",
        json={**_payload(seeded), "severidade": "CRITICA"},
        headers={"X-CSRF-TOKEN": csrf},
    )
    assert repeated.status_code == 200
    assert repeated.get_json()["id"] == data["id"]
    assert repeated.get_json()["severidade"] == "ALTA"

    listed = client.get(
        "/api/v1/assistente/avaliacoes/perguntas"
        "?origem=REGRESSAO&severidade=ALTA&ativa=true"
    )
    assert listed.status_code == 200
    assert [item["id"] for item in listed.get_json()["content"]] == [data["id"]]

    with app.app_context():
        item = db.session.scalar(
            select(RagEvaluationQuestion).where(
                RagEvaluationQuestion.id == uuid.UUID(data["id"])
            )
        )
        audit = db.session.scalar(
            select(AuditLog).where(
                AuditLog.action == "rag_evaluation.regression_case_created"
            )
        )
        assert item.source_query_id == uuid.UUID(seeded["query_id"])
        assert audit is not None


def test_regression_case_preserves_signals_but_allows_deactivation(app, client):
    seeded = _seed_query(app)
    csrf = _login(client)
    created = client.post(
        "/api/v1/assistente/avaliacoes/casos-regressao",
        json=_payload(seeded),
        headers={"X-CSRF-TOKEN": csrf},
    ).get_json()

    rejected = client.patch(
        f"/api/v1/assistente/avaliacoes/perguntas/{created['id']}",
        json={"pergunta": "Tentar alterar a pergunta original"},
        headers={"X-CSRF-TOKEN": csrf},
    )
    assert rejected.status_code == 409

    updated = client.patch(
        f"/api/v1/assistente/avaliacoes/perguntas/{created['id']}",
        json={"observacoes": "Validado pela equipe.", "ativa": False},
        headers={"X-CSRF-TOKEN": csrf},
    )
    assert updated.status_code == 200
    assert updated.get_json()["ativa"] is False
    assert updated.get_json()["observacoes"] == "Validado pela equipe."
    assert updated.get_json()["fontesEsperadas"] == created["fontesEsperadas"]


def test_regression_case_enforces_tenant_and_source_boundaries(app, client):
    tenant_a = _seed_query(app, "gabinete-a")
    tenant_b = _seed_query(app, "gabinete-b")
    csrf = _login(client, "gabinete-b")

    cross_tenant = client.post(
        "/api/v1/assistente/avaliacoes/casos-regressao",
        json=_payload(tenant_a),
        headers={"X-CSRF-TOKEN": csrf},
    )
    assert cross_tenant.status_code == 404

    invalid_hard_negative = _payload(tenant_b)
    invalid_hard_negative["fontesIrrelevantes"] = [
        {
            "documentoId": tenant_b["second_document_id"],
            "versaoId": tenant_b["second_version_id"],
            "chunkId": str(uuid.uuid4()),
            "escopo": "PRIVADO",
        }
    ]
    rejected = client.post(
        "/api/v1/assistente/avaliacoes/casos-regressao",
        json=invalid_hard_negative,
        headers={"X-CSRF-TOKEN": csrf},
    )
    assert rejected.status_code == 422


def test_regression_case_participates_in_evaluation(app, client, monkeypatch):
    seeded = _seed_query(app)
    csrf = _login(client)
    created = client.post(
        "/api/v1/assistente/avaliacoes/casos-regressao",
        json=_payload(seeded),
        headers={"X-CSRF-TOKEN": csrf},
    )
    assert created.status_code == 201

    def fake_route_query(*_args, **_kwargs):
        return {
            "fontes": [_reference(seeded)],
            "fundamentada": True,
            "recusaConclusiva": False,
            "metodo": "DOCUMENTAL",
            "filtrosAplicados": {"tema": "licitações"},
        }

    monkeypatch.setattr("app.rag.evaluation.route_query", fake_route_query)
    evaluated = client.post(
        "/api/v1/assistente/avaliacoes/executar",
        json={"k": 5},
        headers={"X-CSRF-TOKEN": csrf},
    )

    assert evaluated.status_code == 201
    metrics = evaluated.get_json()
    assert metrics["precisionAtK"] == 1.0
    assert metrics["recallAtK"] == 1.0
    assert metrics["taxaFontesDesconexas"] == 0.0
    assert metrics["taxaHardNegatives"] == 0.0
    assert metrics["acuraciaRoteamento"] == 1.0
    assert metrics["acuraciaFiltros"] == 1.0
