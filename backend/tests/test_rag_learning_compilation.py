import hashlib
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from app.extensions import db
from app.models import (
    OutboxEvent,
    RagAssistantQuery,
    RagLearningArtifact,
    RagLearningArtifactFeedback,
    RagLearningArtifactStatus,
    RagLearningArtifactType,
    RagLearningRun,
)
from app.outbox.service import process_batch
from tests.test_rag_feedback_capture import _login, _seed_query


def _approved_feedback(client, csrf, seeded):
    created = client.post(
        f"/api/v1/assistente/consultas/{seeded['query_id']}/feedback",
        json={
            "avaliacao": "CORRIGIDA",
            "motivos": ["RESPOSTA_INCORRETA", "ROTEAMENTO_INCORRETO"],
            "comentario": "A rota e a fundamentação precisam de ajuste.",
            "respostaCorrigida": (
                "A resposta deve comparar as duas fontes e explicitar a vigência."
            ),
            "metodoEsperado": "HIBRIDO",
            "filtrosEsperados": {"dataset": "solicitacoes", "tema": "mobilidade"},
            "julgamentosFontes": [
                {
                    "documentoId": seeded["document_id"],
                    "versaoId": seeded["version_id"],
                    "chunkId": seeded["chunk_id"],
                    "escopo": "PRIVADO",
                    "julgamento": "RELEVANTE",
                    "motivo": "RESPOSTA_INCORRETA",
                },
                {
                    "documentoId": seeded["second_document_id"],
                    "versaoId": seeded["second_version_id"],
                    "chunkId": seeded["second_chunk_id"],
                    "escopo": "PRIVADO",
                    "julgamento": "IRRELEVANTE",
                    "motivo": "RESPOSTA_INCORRETA",
                },
            ],
        },
        headers={"X-CSRF-TOKEN": csrf},
    )
    assert created.status_code == 201
    approved = client.patch(
        f"/api/v1/assistente/feedback/{created.json['id']}/moderacao",
        json={
            "decisao": "APROVAR",
            "justificativa": "Conteúdo revisado e fontes conferidas.",
        },
        headers={"X-CSRF-TOKEN": csrf},
    )
    assert approved.status_code == 200
    promoted = client.post(
        f"/api/v1/assistente/feedback/{created.json['id']}/promover-avaliacao",
        headers={"X-CSRF-TOKEN": csrf},
    )
    assert promoted.status_code == 201
    return created.json["id"]


def _window():
    now = datetime.now(UTC)
    return {
        "inicio": (now - timedelta(days=1)).isoformat(),
        "fim": now.isoformat(),
    }


def _process_learning_event(worker_id):
    result = process_batch(worker_id)
    event = db.session.scalar(
        select(OutboxEvent)
        .where(OutboxEvent.event_type == "CompilacaoSinaisRag")
        .order_by(OutboxEvent.occurred_at.desc())
    )
    assert result.succeeded == 1, event.last_error


def test_compilation_is_idempotent_and_creates_candidate_artifacts(app, client):
    seeded = _seed_query(app)
    with app.app_context():
        seeded_query = db.session.get(
            RagAssistantQuery,
            uuid.UUID(seeded["query_id"]),
        )
        seeded_query.query_hash = hashlib.sha256(
            seeded_query.query_text.encode("utf-8")
        ).hexdigest()
        db.session.commit()
    csrf = _login(client)
    feedback_id = _approved_feedback(client, csrf, seeded)
    payload = _window()

    created = client.post(
        "/api/v1/assistente/aprendizado/execucoes",
        json=payload,
        headers={"X-CSRF-TOKEN": csrf},
    )
    repeated = client.post(
        "/api/v1/assistente/aprendizado/execucoes",
        json=payload,
        headers={"X-CSRF-TOKEN": csrf},
    )

    assert created.status_code == 202
    assert repeated.status_code == 200
    assert repeated.json["id"] == created.json["id"]
    with app.app_context():
        _process_learning_event("rag-learning-worker")
        assert db.session.scalar(select(db.func.count(RagLearningRun.id))) == 1

    runs = client.get("/api/v1/assistente/aprendizado/execucoes")
    assert runs.status_code == 200
    run = runs.json["content"][0]
    assert run["estado"] == "CONCLUIDA"
    assert run["totalAprovados"] == 1
    assert run["quantidadeArtefatos"] == 4
    assert run["metricas"]["minimumSignalsMet"] is True

    artifacts = client.get("/api/v1/assistente/aprendizado/artefatos")
    assert artifacts.status_code == 200
    assert {item["tipo"] for item in artifacts.json["content"]} == {
        "RERANK_PROFILE",
        "ROUTING_EXAMPLES",
        "EVALUATION_CASES",
        "ANSWER_EXEMPLARS",
    }
    assert all(item["estado"] == "CANDIDATO" for item in artifacts.json["content"])
    assert all(item["feedbacksOrigem"] == [feedback_id] for item in artifacts.json["content"])

    by_type = {item["tipo"]: item for item in artifacts.json["content"]}
    detail = client.get(
        f"/api/v1/assistente/aprendizado/artefatos/"
        f"{by_type['RERANK_PROFILE']['id']}"
    )
    assert detail.status_code == 200
    assert detail.json["proveniencia"][0]["feedbackId"] == feedback_id
    adjustments = [
        item["ajuste"] for item in detail.json["payload"]["entradas"]
    ]
    assert adjustments
    assert all(abs(value) <= 0.12 for value in adjustments)
    assert "comentario" not in str(detail.json).lower()

    answer = client.get(
        f"/api/v1/assistente/aprendizado/artefatos/"
        f"{by_type['ANSWER_EXEMPLARS']['id']}"
    )
    assert answer.json["payload"]["exemplares"][0]["evidenciaFactual"] is False
    assert answer.json["payload"]["exemplares"][0]["usoPermitido"] == (
        "AVALIACAO_E_FORMA"
    )

    with app.app_context():
        assert db.session.scalar(
            select(db.func.count(RagLearningArtifact.id))
        ) == 4
        assert db.session.scalar(
            select(db.func.count(RagLearningArtifactFeedback.id))
        ) == 4


def test_compilation_requires_minimum_or_explicit_small_sample_approval(app, client):
    app.config["RAG_LEARNING_MIN_SIGNALS"] = 3
    seeded = _seed_query(app)
    csrf = _login(client)
    _approved_feedback(client, csrf, seeded)
    window = _window()

    insufficient = client.post(
        "/api/v1/assistente/aprendizado/execucoes",
        json=window,
        headers={"X-CSRF-TOKEN": csrf},
    )
    assert insufficient.status_code == 202
    with app.app_context():
        _process_learning_event("rag-learning-minimum-worker")
    stored = client.get("/api/v1/assistente/aprendizado/execucoes").json["content"][0]
    assert stored["quantidadeArtefatos"] == 0
    assert stored["metricas"]["minimumSignalsMet"] is False

    approved = client.post(
        "/api/v1/assistente/aprendizado/execucoes",
        json={**window, "permitirAmostraPequena": True},
        headers={"X-CSRF-TOKEN": csrf},
    )
    assert approved.status_code == 202
    with app.app_context():
        _process_learning_event("rag-learning-approved-worker")
    artifacts = client.get("/api/v1/assistente/aprendizado/artefatos")
    assert len(artifacts.json["content"]) == 4


def test_learning_artifacts_are_tenant_isolated(app, client):
    seeded = _seed_query(app)
    csrf = _login(client)
    _approved_feedback(client, csrf, seeded)
    response = client.post(
        "/api/v1/assistente/aprendizado/execucoes",
        json=_window(),
        headers={"X-CSRF-TOKEN": csrf},
    )
    assert response.status_code == 202
    with app.app_context():
        _process_learning_event("rag-learning-isolation-worker")
    artifact_id = client.get(
        "/api/v1/assistente/aprendizado/artefatos"
    ).json["content"][0]["id"]

    client.post("/api/v1/auth/logout", headers={"X-CSRF-TOKEN": csrf})
    _login(client, "gabinete-b")
    assert client.get("/api/v1/assistente/aprendizado/execucoes").json["content"] == []
    assert client.get("/api/v1/assistente/aprendizado/artefatos").json["content"] == []
    assert (
        client.get(
            f"/api/v1/assistente/aprendizado/artefatos/{artifact_id}"
        ).status_code
        == 404
    )


def test_candidate_evaluation_activation_influence_and_rollback(
    app,
    client,
    monkeypatch,
):
    seeded = _seed_query(app)
    with app.app_context():
        seeded_query = db.session.get(
            RagAssistantQuery,
            uuid.UUID(seeded["query_id"]),
        )
        seeded_query.query_hash = hashlib.sha256(
            seeded_query.query_text.encode("utf-8")
        ).hexdigest()
        db.session.commit()
    csrf = _login(client)
    _approved_feedback(client, csrf, seeded)
    first_run = client.post(
        "/api/v1/assistente/aprendizado/execucoes",
        json=_window(),
        headers={"X-CSRF-TOKEN": csrf},
    )
    assert first_run.status_code == 202
    with app.app_context():
        _process_learning_event("rag-learning-activation-first")

    metrics = {
        "precisionAtK": 0.5,
        "recallAtK": 0.5,
        "groundedness": 0.5,
        "citationPrecision": 0.5,
        "disconnectedSourceRate": 0.5,
        "refusalAccuracy": 1.0,
        "routingAccuracy": 0.5,
        "filterAccuracy": 0.5,
        "hardNegativeRate": 0.5,
    }
    evaluation_calls = 0

    def fake_evaluation(_tenant_id, _role, *, k, learning_artifacts):
        nonlocal evaluation_calls
        evaluation_calls += 1
        candidate = evaluation_calls % 2 == 0
        values = dict(metrics)
        if candidate:
            values["routingAccuracy"] = 0.8
        return {
            "k": k,
            "questionCount": 1,
            "metrics": values,
            "results": [{"candidate": candidate}],
        }

    monkeypatch.setattr(
        "app.rag.evaluation.evaluate_tenant_dataset",
        fake_evaluation,
    )
    artifacts = client.get(
        "/api/v1/assistente/aprendizado/artefatos?tipo=ROUTING_EXAMPLES"
    ).json["content"]
    first_id = artifacts[0]["id"]
    evaluated = client.post(
        f"/api/v1/assistente/aprendizado/artefatos/{first_id}/avaliacao",
        json={},
        headers={"X-CSRF-TOKEN": csrf},
    )
    assert evaluated.status_code == 200
    assert evaluated.json["estado"] == "APROVADO"
    assert evaluated.json["metricasDepois"]["routingAccuracy"] == 0.8

    activated = client.post(
        f"/api/v1/assistente/aprendizado/artefatos/{first_id}/ativacao",
        json={"percentualCanario": 100},
        headers={"X-CSRF-TOKEN": csrf},
    )
    assert activated.status_code == 200
    assert activated.json["estado"] == "ATIVO"
    assert activated.json["modoAtivacao"] == "TOTAL"

    with app.app_context():
        original_query = db.session.get(
            RagAssistantQuery,
            uuid.UUID(seeded["query_id"]),
        ).query_text
    influenced = client.post(
        "/api/v1/assistente/consultas",
        json={"consulta": original_query},
        headers={"X-CSRF-TOKEN": csrf},
    )
    assert influenced.status_code == 200
    assert influenced.json["artefatosAprendizado"] == [
        {
            "id": first_id,
            "modoAtivacao": "TOTAL",
            "percentualCanario": 100,
            "tipo": "ROUTING_EXAMPLES",
            "versao": 1,
        }
    ]

    second_window = _window()
    second_window["inicio"] = (
        datetime.fromisoformat(second_window["inicio"]) - timedelta(days=1)
    ).isoformat()
    second_run = client.post(
        "/api/v1/assistente/aprendizado/execucoes",
        json={**second_window, "tiposArtefato": ["ROUTING_EXAMPLES"]},
        headers={"X-CSRF-TOKEN": csrf},
    )
    assert second_run.status_code == 202
    with app.app_context():
        _process_learning_event("rag-learning-activation-second")
    second_id = client.get(
        "/api/v1/assistente/aprendizado/artefatos?tipo=ROUTING_EXAMPLES&estado=CANDIDATO"
    ).json["content"][0]["id"]
    assert client.post(
        f"/api/v1/assistente/aprendizado/artefatos/{second_id}/avaliacao",
        json={},
        headers={"X-CSRF-TOKEN": csrf},
    ).status_code == 200
    assert client.post(
        f"/api/v1/assistente/aprendizado/artefatos/{second_id}/ativacao",
        json={"percentualCanario": 25},
        headers={"X-CSRF-TOKEN": csrf},
    ).status_code == 200

    rolled_back = client.post(
        f"/api/v1/assistente/aprendizado/artefatos/{second_id}/rollback",
        json={"motivo": "Regressão observada no canário."},
        headers={"X-CSRF-TOKEN": csrf},
    )
    assert rolled_back.status_code == 200
    assert rolled_back.json["artefatoRevogado"]["estado"] == "REVOGADO"
    assert rolled_back.json["artefatoRestaurado"]["id"] == first_id
    assert rolled_back.json["artefatoRestaurado"]["estado"] == "ATIVO"


def test_quality_regression_rejects_candidate(app, client, monkeypatch):
    seeded = _seed_query(app)
    csrf = _login(client)
    _approved_feedback(client, csrf, seeded)
    response = client.post(
        "/api/v1/assistente/aprendizado/execucoes",
        json={**_window(), "tiposArtefato": ["ROUTING_EXAMPLES"]},
        headers={"X-CSRF-TOKEN": csrf},
    )
    assert response.status_code == 202
    with app.app_context():
        _process_learning_event("rag-learning-rejection")
        artifact = db.session.scalar(
            select(RagLearningArtifact).where(
                RagLearningArtifact.artifact_type
                == RagLearningArtifactType.ROUTING_EXAMPLES
            )
        )
        artifact_id = str(artifact.id)

    calls = 0

    def regressing_evaluation(_tenant_id, _role, *, k, learning_artifacts):
        nonlocal calls
        calls += 1
        score = 1.0 if calls == 1 else 0.0
        return {
            "k": k,
            "questionCount": 1,
            "metrics": {
                "precisionAtK": score,
                "recallAtK": score,
                "groundedness": score,
                "citationPrecision": score,
                "disconnectedSourceRate": 1.0 - score,
                "refusalAccuracy": score,
                "routingAccuracy": score,
                "filterAccuracy": score,
                "hardNegativeRate": 1.0 - score,
            },
            "results": [],
        }

    monkeypatch.setattr(
        "app.rag.evaluation.evaluate_tenant_dataset",
        regressing_evaluation,
    )
    rejected = client.post(
        f"/api/v1/assistente/aprendizado/artefatos/{artifact_id}/avaliacao",
        json={"justificativaSemMelhora": "Mudança operacional aprovada."},
        headers={"X-CSRF-TOKEN": csrf},
    )
    assert rejected.status_code == 409
    assert rejected.json["estado"] == "REJEITADO"
    assert any(
        reason.startswith("REGRESSAO_")
        for reason in rejected.json["motivosRejeicao"]
    )
    with app.app_context():
        assert (
            db.session.get(RagLearningArtifact, uuid.UUID(artifact_id)).status
            == RagLearningArtifactStatus.REJEITADO
        )


def test_online_negative_feedback_triggers_automatic_rollback(app, client):
    app.config["RAG_LEARNING_ONLINE_MIN_SAMPLES"] = 1
    app.config["RAG_LEARNING_ONLINE_MAX_NEGATIVE_RATE"] = 0.5
    seeded = _seed_query(app)
    with app.app_context():
        seeded_query = db.session.get(
            RagAssistantQuery,
            uuid.UUID(seeded["query_id"]),
        )
        seeded_query.query_hash = hashlib.sha256(
            seeded_query.query_text.encode("utf-8")
        ).hexdigest()
        original_query = seeded_query.query_text
        db.session.commit()
    csrf = _login(client)
    _approved_feedback(client, csrf, seeded)
    created = client.post(
        "/api/v1/assistente/aprendizado/execucoes",
        json={**_window(), "tiposArtefato": ["ROUTING_EXAMPLES"]},
        headers={"X-CSRF-TOKEN": csrf},
    )
    assert created.status_code == 202
    with app.app_context():
        _process_learning_event("rag-learning-online-rollback")
        artifact = db.session.scalar(select(RagLearningArtifact))
        artifact.status = RagLearningArtifactStatus.ATIVO
        artifact.activation_mode = "TOTAL"
        artifact.rollout_percentage = 100
        artifact.online_metrics = {
            "influencedQueries": 0,
            "ratedQueries": 0,
            "positiveRatings": 0,
            "negativeRatings": 0,
            "negativeRate": 0.0,
        }
        artifact_id = str(artifact.id)
        db.session.commit()

    influenced = client.post(
        "/api/v1/assistente/consultas",
        json={"consulta": original_query},
        headers={"X-CSRF-TOKEN": csrf},
    )
    assert influenced.status_code == 200
    assert influenced.json["artefatosAprendizado"][0]["id"] == artifact_id
    feedback = client.post(
        f"/api/v1/assistente/consultas/{influenced.json['id']}/feedback",
        json={
            "avaliacao": "NEGATIVA",
            "motivos": ["ROTEAMENTO_INCORRETO"],
            "metodoEsperado": "DOCUMENTAL",
        },
        headers={"X-CSRF-TOKEN": csrf},
    )
    assert feedback.status_code == 201
    assert feedback.json["estado"] == "APROVADO"
    detail = client.get(
        f"/api/v1/assistente/aprendizado/artefatos/{artifact_id}"
    )
    assert detail.json["estado"] == "REVOGADO"
    assert detail.json["metricasOnline"]["negativeRate"] == 1.0


def test_revoked_source_feedback_invalidates_artifact_and_recompiles(app, client):
    seeded = _seed_query(app)
    csrf = _login(client)
    feedback_id = _approved_feedback(client, csrf, seeded)
    created = client.post(
        "/api/v1/assistente/aprendizado/execucoes",
        json={**_window(), "tiposArtefato": ["ROUTING_EXAMPLES"]},
        headers={"X-CSRF-TOKEN": csrf},
    )
    assert created.status_code == 202
    with app.app_context():
        _process_learning_event("rag-learning-revocation")
        artifact = db.session.scalar(select(RagLearningArtifact))
        artifact.status = RagLearningArtifactStatus.ATIVO
        artifact.activation_mode = "TOTAL"
        artifact.rollout_percentage = 100
        artifact_id = str(artifact.id)
        db.session.commit()

    revoked = client.patch(
        f"/api/v1/assistente/feedback/{feedback_id}/moderacao",
        json={
            "decisao": "REVOGAR",
            "justificativa": "Fonte de origem deixou de ser elegível.",
        },
        headers={"X-CSRF-TOKEN": csrf},
    )
    assert revoked.status_code == 200
    assert revoked.json["estado"] == "REVOGADO"
    detail = client.get(
        f"/api/v1/assistente/aprendizado/artefatos/{artifact_id}"
    )
    assert detail.json["estado"] == "REVOGADO"
    with app.app_context():
        assert db.session.scalar(select(db.func.count(RagLearningRun.id))) == 2
        pending = db.session.scalar(
            select(OutboxEvent).where(
                OutboxEvent.event_type == "CompilacaoSinaisRag",
                OutboxEvent.published_at.is_(None),
            )
        )
        assert pending is not None
