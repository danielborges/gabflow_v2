import uuid
from datetime import timedelta

from sqlalchemy import select

from app.extensions import db
from app.models import (
    OutboxEvent,
    RagLearningArtifact,
    RagLearningArtifactStatus,
    RagLearningArtifactType,
    RagLearningRun,
)
from app.outbox.service import process_batch
from app.rag.learning import active_learning_artifacts, record_learning_influence
from tests.test_rag_feedback_capture import _login


def _metrics(score):
    return {
        "precisionAtK": score,
        "recallAtK": score,
        "groundedness": score,
        "citationPrecision": score,
        "disconnectedSourceRate": 1.0 - score,
        "refusalAccuracy": score,
        "routingAccuracy": score,
        "filterAccuracy": score,
        "hardNegativeRate": 1.0 - score,
    }


def _process_calibration(app, worker_id):
    with app.app_context():
        result = process_batch(worker_id)
        event = db.session.scalar(
            select(OutboxEvent)
            .where(OutboxEvent.event_type == "AvaliacaoPerfilQualidadeRag")
            .order_by(OutboxEvent.occurred_at.desc())
        )
        assert result.succeeded == 1, event.last_error


def test_calibration_evaluates_candidate_and_activates_canary(
    app,
    client,
    monkeypatch,
):
    calls = 0

    def fake_evaluation(_tenant_id, _role, *, k, learning_artifacts):
        nonlocal calls
        calls += 1
        candidate = (
            RagLearningArtifactType.QUALITY_PROFILE in learning_artifacts
        )
        return {
            "k": k,
            "questionCount": 8,
            "metrics": _metrics(0.9 if candidate else 0.7),
            "results": [{"candidate": candidate}],
        }

    monkeypatch.setattr(
        "app.rag.evaluation.evaluate_tenant_dataset",
        fake_evaluation,
    )
    csrf = _login(client)
    calibrated = client.post(
        "/api/v1/assistente/calibracoes",
        json={
            "k": 5,
            "parametros": {
                "citationLexicalThreshold": 0.24,
                "entailmentMinScore": 0.8,
            },
        },
        headers={"X-CSRF-TOKEN": csrf},
    )

    assert calibrated.status_code == 202
    assert calibrated.json["tipo"] == "QUALITY_PROFILE"
    assert calibrated.json["estado"] == "CANDIDATO"
    assert calibrated.json["aprovada"] is None
    artifact_id = calibrated.json["id"]
    _process_calibration(app, "quality-calibration-approved")
    detail = client.get(
        f"/api/v1/assistente/aprendizado/artefatos/{artifact_id}"
    )
    assert detail.json["estado"] == "ATIVO"
    assert detail.json["percentualCanario"] == 5
    assert detail.json["rollout"]["estado"] == "MONITORANDO"
    assert detail.json["metricasAntes"]["citationPrecision"] == 0.7
    assert detail.json["metricasDepois"]["citationPrecision"] == 0.9

    activated = client.post(
        f"/api/v1/assistente/aprendizado/artefatos/{artifact_id}/ativacao",
        json={"percentualCanario": 20},
        headers={"X-CSRF-TOKEN": csrf},
    )
    assert activated.status_code == 200
    assert activated.json["estado"] == "ATIVO"
    assert activated.json["modoAtivacao"] == "CANARIO"
    assert activated.json["percentualCanario"] == 20
    with app.app_context():
        run = db.session.scalar(select(RagLearningRun))
        assert run.configuration["origin"] == "QUALITY_CALIBRATION"
        assert run.metrics["aprovado"] is True


def test_quality_rollout_progresses_until_full_promotion(
    app,
    client,
    monkeypatch,
):
    app.config.update(
        RAG_QUALITY_ROLLOUT_STAGES="5,20,100",
        RAG_QUALITY_ROLLOUT_MIN_SAMPLES=1,
        RAG_QUALITY_ROLLOUT_MIN_WINDOW_SECONDS=0,
        RAG_QUALITY_ROLLOUT_CHECK_INTERVAL_SECONDS=0,
        RAG_QUALITY_ONLINE_MIN_SAMPLES=50,
    )

    def fake_evaluation(_tenant_id, _role, *, k, learning_artifacts):
        candidate = RagLearningArtifactType.QUALITY_PROFILE in learning_artifacts
        return {
            "k": k,
            "questionCount": 8,
            "metrics": _metrics(0.9 if candidate else 0.7),
            "results": [],
        }

    monkeypatch.setattr(
        "app.rag.evaluation.evaluate_tenant_dataset",
        fake_evaluation,
    )
    csrf = _login(client)
    response = client.post(
        "/api/v1/assistente/calibracoes",
        json={"parametros": {"entailmentMinScore": 0.8}},
        headers={"X-CSRF-TOKEN": csrf},
    )
    artifact_id = response.json["id"]
    _process_calibration(app, "quality-progressive-calibration")

    valid_answer = {
        "recusaConclusiva": False,
        "geracao": {
            "fallbackUtilizado": False,
            "validacaoCruzada": {
                "entailmentSemantico": {
                    "habilitado": True,
                    "valida": True,
                }
            },
        },
    }
    for expected_percentage in (20, 100, 100):
        with app.app_context():
            artifact = db.session.get(
                RagLearningArtifact,
                uuid.UUID(artifact_id),
            )
            record_learning_influence(
                artifact.tenant_id,
                [{"id": artifact_id}],
                answer=valid_answer,
            )
            db.session.commit()
            result = process_batch(f"quality-rollout-{expected_percentage}")
            event = db.session.scalar(
                select(OutboxEvent)
                .where(
                    OutboxEvent.event_type
                    == "AvaliacaoRolloutPerfilQualidadeRag"
                )
                .order_by(OutboxEvent.occurred_at.desc())
            )
            assert result.succeeded == 1, event.last_error
        detail = client.get(
            f"/api/v1/assistente/aprendizado/artefatos/{artifact_id}"
        )
        assert detail.json["percentualCanario"] == expected_percentage

    assert detail.json["modoAtivacao"] == "TOTAL"
    assert detail.json["rollout"]["estado"] == "PROMOVIDO"
    assert len(detail.json["rollout"]["historico"]) == 6

    listing = client.get("/api/v1/assistente/calibracoes")
    assert listing.status_code == 200
    assert listing.json["perfilAtivo"]["id"] == artifact_id


def test_quality_rollout_rolls_back_when_online_gate_fails(
    app,
    client,
    monkeypatch,
):
    app.config.update(
        RAG_QUALITY_ROLLOUT_STAGES="5,100",
        RAG_QUALITY_ROLLOUT_MIN_SAMPLES=1,
        RAG_QUALITY_ROLLOUT_MIN_WINDOW_SECONDS=0,
        RAG_QUALITY_ROLLOUT_CHECK_INTERVAL_SECONDS=0,
        RAG_QUALITY_ONLINE_MIN_SAMPLES=50,
        RAG_QUALITY_ONLINE_MAX_REFUSAL_RATE=0.1,
    )

    monkeypatch.setattr(
        "app.rag.evaluation.evaluate_tenant_dataset",
        lambda _tenant_id, _role, *, k, learning_artifacts: {
            "k": k,
            "questionCount": 8,
            "metrics": _metrics(
                0.9
                if RagLearningArtifactType.QUALITY_PROFILE
                in learning_artifacts
                else 0.7
            ),
            "results": [],
        },
    )
    csrf = _login(client)
    response = client.post(
        "/api/v1/assistente/calibracoes",
        json={"parametros": {"entailmentMinScore": 0.8}},
        headers={"X-CSRF-TOKEN": csrf},
    )
    artifact_id = response.json["id"]
    _process_calibration(app, "quality-rollback-calibration")

    with app.app_context():
        artifact = db.session.get(
            RagLearningArtifact,
            uuid.UUID(artifact_id),
        )
        record_learning_influence(
            artifact.tenant_id,
            [{"id": artifact_id}],
            answer={
                "recusaConclusiva": True,
                "geracao": {
                    "fallbackUtilizado": False,
                    "validacaoCruzada": {
                        "entailmentSemantico": {
                            "habilitado": True,
                            "valida": True,
                        }
                    },
                },
            },
        )
        db.session.commit()
        result = process_batch("quality-rollout-rejection")
        event = db.session.scalar(
            select(OutboxEvent)
            .where(
                OutboxEvent.event_type
                == "AvaliacaoRolloutPerfilQualidadeRag"
            )
            .order_by(OutboxEvent.occurred_at.desc())
        )
        assert result.succeeded == 1, event.last_error
        db.session.refresh(artifact)
        assert artifact.status == RagLearningArtifactStatus.REVOGADO
        assert artifact.rollout_state == "ROLLBACK"
        assert (
            artifact.rollout_history[-1]["motivos"][0]
            == "TAXA_RECUSA_ACIMA_DO_LIMITE"
        )


def test_calibration_rejects_regression(app, client, monkeypatch):
    calls = 0

    def fake_evaluation(_tenant_id, _role, *, k, learning_artifacts):
        nonlocal calls
        calls += 1
        return {
            "k": k,
            "questionCount": 4,
            "metrics": _metrics(0.9 if calls == 1 else 0.2),
            "results": [],
        }

    monkeypatch.setattr(
        "app.rag.evaluation.evaluate_tenant_dataset",
        fake_evaluation,
    )
    csrf = _login(client)
    response = client.post(
        "/api/v1/assistente/calibracoes",
        json={
            "parametros": {"neuralMinScore": 0.35},
            "justificativaSemMelhora": "Mudança operacional documentada.",
        },
        headers={"X-CSRF-TOKEN": csrf},
    )

    assert response.status_code == 202
    _process_calibration(app, "quality-calibration-regression")
    detail = client.get(
        f"/api/v1/assistente/aprendizado/artefatos/{response.json['id']}"
    )
    assert detail.json["estado"] == "REJEITADO"
    assert any(
        reason.startswith("REGRESSAO_")
        for reason in detail.json["detalhesAvaliacao"]["reasons"]
    )


def test_calibration_rejects_candidate_above_latency_slo(
    app,
    client,
    monkeypatch,
):
    calls = 0

    def fake_evaluation(_tenant_id, _role, *, k, learning_artifacts):
        nonlocal calls
        calls += 1
        values = _metrics(0.7 if calls == 1 else 0.8)
        values["latencyP95Ms"] = 10_000 if calls == 1 else 20_000
        return {
            "k": k,
            "questionCount": 5,
            "metrics": values,
            "results": [],
        }

    monkeypatch.setattr(
        "app.rag.evaluation.evaluate_tenant_dataset",
        fake_evaluation,
    )
    csrf = _login(client)
    response = client.post(
        "/api/v1/assistente/calibracoes",
        json={"parametros": {"entailmentMinScore": 0.8}},
        headers={"X-CSRF-TOKEN": csrf},
    )

    assert response.status_code == 202
    _process_calibration(app, "quality-calibration-latency")
    detail = client.get(
        f"/api/v1/assistente/aprendizado/artefatos/{response.json['id']}"
    )
    assert "SLO_LATENCIA_EXCEDIDO" in detail.json["detalhesAvaliacao"]["reasons"]


def test_quality_profile_rolls_back_on_semantic_rejection_rate(app):
    app.config.update(
        RAG_QUALITY_ONLINE_MIN_SAMPLES=1,
        RAG_QUALITY_ONLINE_MAX_FALLBACK_RATE=1.0,
        RAG_QUALITY_ONLINE_MAX_SEMANTIC_REJECTION_RATE=0.2,
    )
    with app.app_context():
        from app.models import Tenant, User

        tenant = db.session.scalar(
            select(Tenant).where(Tenant.slug == "gabinete-a")
        )
        user = db.session.scalar(
            select(User).where(User.tenant_id == tenant.id)
        )
        now = user.created_at
        run = RagLearningRun(
            tenant_id=tenant.id,
            window_start=now,
            window_end=now + timedelta(microseconds=1),
            configuration={"origin": "QUALITY_CALIBRATION"},
            configuration_hash="a" * 64,
            initiated_by_id=user.id,
        )
        db.session.add(run)
        db.session.flush()
        artifact = RagLearningArtifact(
            tenant_id=tenant.id,
            run_id=run.id,
            artifact_type=RagLearningArtifactType.QUALITY_PROFILE,
            version=1,
            payload={},
            payload_hash="b" * 64,
            status=RagLearningArtifactStatus.ATIVO,
            activated_by_id=user.id,
            activation_mode="CANARIO",
            rollout_percentage=10,
        )
        db.session.add(artifact)
        db.session.flush()

        with app.test_request_context("/api/v1/assistente/consultas"):
            record_learning_influence(
                tenant.id,
                [{"id": str(artifact.id)}],
                answer={
                    "recusaConclusiva": True,
                    "geracao": {
                        "fallbackUtilizado": False,
                        "validacaoCruzada": {
                            "entailmentSemantico": {
                                "habilitado": True,
                                "valida": False,
                            }
                        }
                    },
                },
            )

        assert artifact.status == RagLearningArtifactStatus.REVOGADO
        assert artifact.rollout_percentage == 0
        assert artifact.online_metrics["semanticRejectionRate"] == 1.0


def test_quality_canary_keeps_previous_profile_outside_candidate_bucket(app):
    with app.app_context():
        from app.models import Tenant, User

        tenant = db.session.scalar(select(Tenant).where(Tenant.slug == "gabinete-a"))
        user = db.session.scalar(select(User).where(User.tenant_id == tenant.id))
        now = user.created_at
        run = RagLearningRun(
            tenant_id=tenant.id,
            window_start=now,
            window_end=now + timedelta(microseconds=1),
            configuration={"origin": "QUALITY_CALIBRATION"},
            configuration_hash="c" * 64,
            initiated_by_id=user.id,
        )
        db.session.add(run)
        db.session.flush()
        candidate = RagLearningArtifact(
            tenant_id=tenant.id,
            run_id=run.id,
            artifact_type=RagLearningArtifactType.QUALITY_PROFILE,
            version=2,
            payload={},
            payload_hash="d" * 64,
            status=RagLearningArtifactStatus.ATIVO,
            activated_by_id=user.id,
            activation_mode="CANARIO",
            rollout_percentage=5,
        )
        db.session.add(candidate)
        db.session.flush()
        baseline = RagLearningArtifact(
            tenant_id=tenant.id,
            run_id=run.id,
            artifact_type=RagLearningArtifactType.QUALITY_PROFILE,
            version=1,
            payload={},
            payload_hash="e" * 64,
            status=RagLearningArtifactStatus.SUBSTITUIDO,
            replaced_by_id=candidate.id,
            rollout_percentage=100,
        )
        db.session.add(baseline)
        db.session.commit()

        selected = {
            active_learning_artifacts(
                tenant.id,
                canary_key=f"query-{index}",
            )[RagLearningArtifactType.QUALITY_PROFILE].id
            for index in range(200)
        }
        assert candidate.id in selected
        assert baseline.id in selected
