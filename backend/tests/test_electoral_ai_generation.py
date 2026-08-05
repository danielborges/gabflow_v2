import json

import pytest

from app.electoral.ai_generation import (
    ElectoralAIInvalidResponse,
    ElectoralAIUnavailable,
    ElectoralEvidence,
    OllamaElectoralAIProvider,
    generate_electoral_content,
)


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
                        "afirmacoes": [
                            {
                                "texto": "A candidatura recebeu 123 votos no recorte oficial.",
                                "citacaoIds": ["dataset-1"],
                            }
                        ],
                        "leiturasEstrategicas": [
                            {
                                "texto": "A diferenca territorial sugere investigar presenca publica local.",
                                "citacaoIds": ["dataset-1"],
                            }
                        ],
                        "recomendacoes": [
                            {
                                "titulo": "Escuta territorial",
                                "acao": "Realize encontros publicos para compreender prioridades locais.",
                                "justificativa": "A diferenca observada merece validacao qualitativa no territorio.",
                                "citacaoIds": ["dataset-1"],
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
    assert result.interpretations[0].citation_ids == ("dataset-1",)
    assert result.recommendations[0].title == "Escuta territorial"
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
