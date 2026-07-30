import json

from app.extensions import db
from app.rag.retrieval import answer_query
from app.rag.semantic_entailment import (
    EntailmentCase,
    HttpNliProvider,
    verify_entailment,
)
from tests.test_rag_grounded_generation import _seed_source, _tenant_user


class _Response:
    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None

    def read(self):
        return json.dumps(self.payload).encode()


def test_http_nli_provider_uses_closed_classifier_contract(monkeypatch):
    provider = HttpNliProvider(
        "http://nli:8080",
        "multilingual-nli-v1",
        "rag-nli-v2",
        3,
    )
    monkeypatch.setattr(
        "app.rag.semantic_entailment.urllib.request.urlopen",
        lambda request, timeout: _Response(
            {
                "judgments": [
                    {
                        "id": "1",
                        "label": "CONTRADICTION",
                        "score": 0.98,
                        "reason": "A hipótese inverte a proibição da premissa.",
                    }
                ]
            }
        ),
    )

    judgments = provider.verify(
        (
            EntailmentCase(
                "1",
                "O transporte é permitido.",
                "O transporte é proibido.",
            ),
        )
    )

    assert judgments["1"].entailed is False
    assert judgments["1"].contradicted is True
    assert judgments["1"].score == 0.98


def test_nli_rejects_configuration_using_the_generator_model(app):
    with app.app_context():
        app.config.update(
            RAG_NLI_ENABLED=True,
            RAG_NLI_PROVIDER="ollama",
            RAG_NLI_MODEL="generator-test",
            RAG_ANSWER_MODEL="generator-test",
            RAG_NLI_REQUIRE_DISTINCT_MODEL=True,
        )

        outcome = verify_entailment(
            (EntailmentCase("1", "Afirmação.", "Evidência."),)
        )

        assert outcome.applied is False
        assert outcome.fallback_used is True
        assert outcome.independent_model is False
        assert "diferente" in outcome.fallback_error


def test_clear_hybrid_leader_skips_neural_reranker_and_reports_timings(
    app,
    monkeypatch,
):
    with app.app_context():
        tenant, user = _tenant_user()
        _seed_source(
            tenant,
            user,
            "Plano de mobilidade",
            "O plano de mobilidade disciplina o transporte coletivo municipal.",
        )
        db.session.commit()
        app.config.update(
            RAG_NEURAL_RERANK_ENABLED=True,
            RAG_NEURAL_RERANK_ADAPTIVE_ENABLED=True,
            RAG_ANSWER_GENERATION_ENABLED=False,
        )
        monkeypatch.setattr(
            "app.rag.neural_reranker.neural_reranker_provider",
            lambda: (_ for _ in ()).throw(
                AssertionError("O reranker não deveria ser chamado.")
            ),
        )

        answer = answer_query(
            tenant.id,
            "admin",
            "O que o plano de mobilidade disciplina sobre transporte coletivo?",
            limit=3,
        )

        reranker = answer["recuperacao"]["rerankingNeural"]
        assert reranker["skipAdaptativo"] is True
        assert reranker["motivoSkip"] == "CANDIDATO_UNICO"
        assert reranker["latenciaMs"] == 0
        assert answer["latenciaEtapas"]["recuperacaoMs"] >= 1
        assert answer["latenciaEtapas"]["totalMs"] >= 1
        assert answer["latenciaEtapas"]["orcamentoMs"] == 30_000
