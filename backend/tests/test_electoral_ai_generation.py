import json
import uuid
from datetime import UTC, date, datetime
from types import SimpleNamespace

import pytest

from app.electoral.ai_generation import (
    ElectoralAIInvalidResponse,
    ElectoralAIUnavailable,
    ElectoralEvidence,
    OllamaElectoralAIProvider,
    generate_electoral_content,
)
from app.electoral.insights import _attach_mandate_context


def _provider():
    return OllamaElectoralAIProvider(
        "http://ollama:11434",
        "qwen2.5:3b",
        "electoral-grounded-generation-v1",
        10,
        4,
        3,
        512,
        "24h",
    )


def test_ollama_electoral_provider_uses_schema_and_restricts_citations(monkeypatch):
    provider = _provider()
    captured = {}

    def response(payload):
        captured.update(payload)
        return {
            "message": {
                "content": json.dumps(
                    {
                        "resumoExecutivo": {
                            "texto": (
                                "A resposta deve combinar o resultado oficial com a presenca "
                                "territorial agregada do mandato."
                            ),
                            "citacaoIds": ["dataset-1"],
                        },
                        "afirmacoes": [
                            {
                                "texto": "A candidatura recebeu 123 votos no recorte oficial.",
                                "citacaoIds": ["dataset-1"],
                            }
                        ],
                        "leiturasEstrategicas": [
                            {
                                "texto": (
                                    "A diferenca territorial sugere investigar "
                                    "presenca publica local."
                                ),
                                "citacaoIds": ["dataset-1"],
                            }
                        ],
                        "recomendacoes": [
                            {
                                "titulo": "Escuta territorial",
                                "acao": (
                                    "Realize encontros publicos para compreender "
                                    "prioridades locais."
                                ),
                                "justificativa": (
                                    "A diferenca observada merece validacao qualitativa "
                                    "no territorio."
                                ),
                                "citacaoIds": ["dataset-1"],
                                "categoria": "AGENDA",
                                "prioridade": "ALTA",
                                "horizonte": "30_DIAS",
                                "territorio": "Zona Norte",
                            }
                        ],
                        "perguntasInvestigacao": [
                            "Quais fatores publicos merecem investigacao qualitativa?"
                        ],
                        "limitacoes": ["Os dados agregados nao demonstram causalidade."],
                    }
                )
            }
        }

    monkeypatch.setattr(provider, "_request", response)
    result = provider.generate(
        "Explique o resultado.",
        (ElectoralEvidence("dataset-1", "TSE", "Foram registrados 123 votos."),),
    )

    assert result.claims[0].citation_ids == ("dataset-1",)
    assert result.executive_summary.citation_ids == ("dataset-1",)
    assert result.interpretations[0].citation_ids == ("dataset-1",)
    assert result.recommendations[0].title == "Escuta territorial"
    assert result.recommendations[0].category == "AGENDA"
    assert result.recommendations[0].priority == "ALTA"
    assert result.recommendations[0].territory == "Zona Norte"
    assert result.hypotheses[0].endswith("?")
    assert captured["format"]["properties"]["afirmacoes"]["maxItems"] == 4
    assert captured["format"]["properties"]["recomendacoes"]["maxItems"] == 4
    assert captured["options"]["temperature"] == 0
    assert captured["options"]["num_predict"] == 512
    assert captured["keep_alive"] == "24h"


def test_ollama_electoral_provider_rejects_unknown_source(monkeypatch):
    provider = _provider()
    monkeypatch.setattr(
        provider,
        "_request",
        lambda _payload: {
            "message": {
                "content": json.dumps(
                    {
                        "afirmacoes": [
                            {
                                "texto": "Esta afirmacao cita uma fonte que nao foi fornecida.",
                                "citacaoIds": ["internet"],
                            }
                        ],
                        "perguntasInvestigacao": [],
                        "limitacoes": [],
                    }
                )
            }
        },
    )

    with pytest.raises(ElectoralAIInvalidResponse, match="evidencia desconhecida"):
        provider.generate(
            "Explique o resultado.",
            (ElectoralEvidence("dataset-1", "TSE", "Resultado oficial."),),
        )


def test_electoral_generation_falls_back_explicitly_when_provider_is_unavailable(
    app, monkeypatch
):
    class UnavailableProvider:
        def generate(self, _task, _evidence):
            raise ElectoralAIUnavailable("indisponivel no teste")

    with app.app_context():
        app.config.update(
            ELECTORAL_AI_ENABLED=True,
            ELECTORAL_AI_PROVIDER="ollama",
            ELECTORAL_AI_MODEL="qwen2.5:3b",
            ELECTORAL_AI_FALLBACK_ENABLED=True,
        )
        monkeypatch.setattr(
            "app.electoral.ai_generation.electoral_ai_provider",
            lambda: UnavailableProvider(),
        )
        generated, metadata = generate_electoral_content(
            "Explique o resultado.",
            (ElectoralEvidence("dataset-1", "TSE", "Resultado oficial."),),
        )

    assert generated is None
    assert metadata["applied"] is False
    assert metadata["fallbackUsed"] is True
    assert metadata["fallbackReason"] == "ElectoralAIUnavailable"


def test_electoral_generation_receives_latest_aggregated_mandate_context(monkeypatch):
    snapshot_id = uuid.uuid4()
    snapshot = SimpleNamespace(
        id=snapshot_id,
        period_start=date(2026, 1, 1),
        period_end=date(2026, 6, 30),
        source_cutoff_at=datetime(2026, 7, 1, tzinfo=UTC),
        privacy_threshold=10,
        config_hash="a" * 64,
        payload={
            "territories": [
                {
                    "scope": "territory",
                    "territory_name": "Zona Norte",
                    "suppressed": False,
                    "demand_count": 24,
                    "metrics": {"agenda_realized": 0, "overdue": 4},
                    "ict": {"score": 42.5},
                    "alerts": ["Nenhuma agenda territorial realizada no período."],
                    "public_commitments": {"total": 2, "overdue": 1},
                    "electoral_overlay": {"votes": 321},
                }
            ]
        },
    )
    monkeypatch.setattr(
        "app.electoral.insights.latest_snapshot",
        lambda _tenant_id, _mandate_id: snapshot,
    )
    output = {
        "input_snapshot": {},
        "citations": [],
        "_validation_evidence": {},
    }

    _attach_mandate_context(
        SimpleNamespace(tenant_id=uuid.uuid4(), mandate_id=uuid.uuid4()),
        output,
    )

    citation_id = f"mandate-snapshot-{snapshot_id}"
    assert output["input_snapshot"]["mandate_context"]["territory_count"] == 1
    assert output["citations"][0]["source_type"] == "MANDATE_AGGREGATE"
    assert '"territory_name": "Zona Norte"' in output["_validation_evidence"][citation_id]
