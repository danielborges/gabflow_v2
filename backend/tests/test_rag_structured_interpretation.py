import io
import json

import pytest

from app.rag.structured_interpretation import (
    _schema,
    _validated_merge,
    interpret_structured_query,
)

BASE_PAYLOAD = {
    "dataset": "SOLICITACOES",
    "metrica": "CONTAGEM",
    "agruparPor": "NENHUM",
}


def test_interpretation_remains_disabled_by_default(app):
    with app.app_context():
        result = interpret_structured_query("Quantas pessoas existem?", BASE_PAYLOAD)

    assert result.payload == BASE_PAYLOAD
    assert result.applied is False
    assert result.fallback_error is None


def test_interpretation_rejects_unsupported_provider(app):
    with app.app_context():
        app.config.update(
            RAG_STRUCTURED_INTERPRETATION_ENABLED=True,
            RAG_STRUCTURED_INTERPRETATION_PROVIDER="bedrock",
        )
        result = interpret_structured_query("Quantas pessoas existem?", BASE_PAYLOAD)

    assert result.payload == BASE_PAYLOAD
    assert result.applied is False
    assert "não suportado" in result.fallback_error


def test_ollama_interpretation_uses_closed_schema_and_corrects_dataset(
    app,
    monkeypatch,
):
    captured = {}

    def fake_urlopen(request, timeout):
        captured["url"] = request.full_url
        captured["timeout"] = timeout
        captured["body"] = json.loads(request.data.decode("utf-8"))
        content = json.dumps(
            {
                "dataset": "CIDADAOS",
                "metrica": "CONTAGEM",
                "agruparPor": "NENHUM",
                "nome": "Adriana",
                "confianca": 0.98,
            }
        )
        return io.BytesIO(
            json.dumps({"message": {"content": content}}).encode("utf-8")
        )

    monkeypatch.setattr("app.rag.structured_interpretation.urllib.request.urlopen", fake_urlopen)
    with app.app_context():
        app.config.update(
            RAG_STRUCTURED_INTERPRETATION_ENABLED=True,
            RAG_STRUCTURED_INTERPRETATION_PROVIDER="ollama",
            RAG_STRUCTURED_INTERPRETATION_MODEL="qwen2.5:0.5b",
            RAG_STRUCTURED_INTERPRETATION_MAX_TOKENS=128,
            RAG_STRUCTURED_INTERPRETATION_TIMEOUT_SECONDS=45,
            OLLAMA_BASE_URL="http://127.0.0.1:11434",
        )
        result = interpret_structured_query(
            "Quantas pessoas com o nome Adriana estão cadastradas?",
            BASE_PAYLOAD,
        )

    assert result.applied is True
    assert result.payload == {
        "dataset": "CIDADAOS",
        "metrica": "CONTAGEM",
        "agruparPor": "NENHUM",
        "nome": "Adriana",
    }
    assert captured["url"] == "http://127.0.0.1:11434/api/chat"
    assert captured["timeout"] == 45
    assert captured["body"]["model"] == "qwen2.5:0.5b"
    assert captured["body"]["format"] == _schema()
    assert captured["body"]["options"] == {
        "temperature": 0,
        "num_ctx": 2048,
        "num_predict": 128,
    }


def test_interpretation_falls_back_when_ollama_url_is_invalid(app):
    with app.app_context():
        app.config.update(
            RAG_STRUCTURED_INTERPRETATION_ENABLED=True,
            RAG_STRUCTURED_INTERPRETATION_PROVIDER="ollama",
            OLLAMA_BASE_URL="not-a-url",
        )
        result = interpret_structured_query("Quantas pessoas existem?", BASE_PAYLOAD)

    assert result.payload == BASE_PAYLOAD
    assert result.applied is False
    assert "OLLAMA_BASE_URL" in result.fallback_error


def test_low_confidence_preserves_deterministic_payload():
    result = _validated_merge(
        BASE_PAYLOAD,
        {
            "dataset": "CIDADAOS",
            "metrica": "CONTAGEM",
            "agruparPor": "NENHUM",
            "nome": "Adriana",
            "confianca": 0.4,
        },
    )

    assert result == BASE_PAYLOAD


@pytest.mark.parametrize(
    "interpreted",
    [
        {
            "dataset": "INEXISTENTE",
            "metrica": "CONTAGEM",
            "agruparPor": "NENHUM",
            "nome": None,
            "confianca": 0.9,
        },
        {
            "dataset": "CIDADAOS",
            "metrica": "CONTAGEM",
            "agruparPor": "NENHUM",
            "nome": None,
            "confianca": 2,
        },
        {
            "dataset": "CIDADAOS",
            "metrica": "TEMPO_MEDIO_RESOLUCAO_HORAS",
            "agruparPor": "NENHUM",
            "nome": None,
            "confianca": 0.9,
        },
        {
            "dataset": "AGENDA",
            "metrica": "PRAZOS_VENCIDOS",
            "agruparPor": "NENHUM",
            "nome": None,
            "confianca": 0.9,
        },
    ],
)
def test_interpretation_rejects_values_outside_contract(interpreted):
    with pytest.raises(ValueError, match="interpretação retornou"):
        _validated_merge(BASE_PAYLOAD, interpreted)


def test_non_citizen_interpretation_removes_name_filter():
    result = _validated_merge(
        {**BASE_PAYLOAD, "nome": "Anterior"},
        {
            "dataset": "SOLICITACOES",
            "metrica": "CONTAGEM",
            "agruparPor": "TEMA",
            "nome": "Não deve permanecer",
            "confianca": 0.95,
        },
    )

    assert result == {
        "dataset": "SOLICITACOES",
        "metrica": "CONTAGEM",
        "agruparPor": "TEMA",
    }


def test_territory_interpretation_normalizes_percentage_confidence_and_group():
    result = _validated_merge(
        {"dataset": None, "metrica": "CONTAGEM", "agruparPor": "NENHUM"},
        {
            "dataset": "TERRITORIOS",
            "metrica": "CONTAGEM",
            "agruparPor": "TERRITORIO",
            "nome": "Territórios cadastrados",
            "confianca": 100,
        },
    )

    assert result == {
        "dataset": "TERRITORIOS",
        "metrica": "CONTAGEM",
        "agruparPor": "NENHUM",
    }
