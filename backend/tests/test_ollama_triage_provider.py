import io
import json
import urllib.error

import pytest

from app.ai.provider import (
    AIProviderInvalidResponse,
    AIProviderUnavailable,
    OllamaTriageProvider,
    TriageAgency,
    TriageCategory,
    TriageInput,
)


class FakeResponse:
    def __init__(self, payload: dict) -> None:
        self.body = io.BytesIO(json.dumps(payload).encode("utf-8"))

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None

    def read(self) -> bytes:
        return self.body.read()


def provider() -> OllamaTriageProvider:
    return OllamaTriageProvider(
        base_url="http://ollama:11434",
        model="qwen2.5:3b",
        prompt_version="triage-v2",
        timeout_seconds=10,
    )


def triage_input() -> TriageInput:
    return TriageInput(
        title="Poste apagado",
        description="A Rua das Flores está sem iluminação.",
        categories=(TriageCategory(id="category-1", name="Iluminação pública"),),
        agencies=(TriageAgency(id="agency-1", name="Secretaria de Iluminação"),),
    )


def test_ollama_provider_uses_json_schema_and_validates_response(monkeypatch):
    content = {
        "categoriaId": "category-1",
        "subcategoria": "Poste apagado",
        "orgaoId": "agency-1",
        "prioridadeSugerida": "MEDIA",
        "impacto": "MEDIO",
        "urgencia": "MEDIO",
        "confianca": 0.91,
        "resumo": "Poste sem iluminação na Rua das Flores.",
        "resumoEstruturado": {
            "situacao": "Poste sem iluminação.",
            "local": "Rua das Flores",
            "afetados": None,
            "informacoesAusentes": ["Número do poste"],
        },
        "justificativa": "O relato trata diretamente de iluminação pública.",
        "conteudoOfensivo": False,
        "marcadoresConteudo": [],
        "emergencia": False,
        "orientacaoEmergencia": None,
        "entidades": {
            "endereco": "Rua das Flores",
            "bairro": None,
            "datas": [],
            "pessoas": [],
            "protocolos": [],
            "servicos": ["Iluminação pública"],
        },
    }
    captured = {}

    def fake_urlopen(request, timeout):
        captured["payload"] = json.loads(request.data.decode("utf-8"))
        captured["timeout"] = timeout
        return FakeResponse({"message": {"content": json.dumps(content)}})

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    result = provider().classify(triage_input())

    assert captured["payload"]["format"]["additionalProperties"] is False
    assert captured["payload"]["options"]["temperature"] == 0
    assert captured["timeout"] == 10
    assert result.category == "Iluminação pública"
    assert result.agency == "Secretaria de Iluminação"
    assert result.structured_summary["informacoesAusentes"] == ["Número do poste"]
    assert result.confidence == 0.91


def test_ollama_provider_rejects_unknown_category(monkeypatch):
    content = {
        "categoriaId": "unknown",
        "subcategoria": None,
        "orgaoId": None,
        "prioridadeSugerida": "MEDIA",
        "impacto": "MEDIO",
        "urgencia": "MEDIO",
        "confianca": 0.5,
        "resumo": "Resumo.",
        "resumoEstruturado": {
            "situacao": "Resumo.",
            "local": None,
            "afetados": None,
            "informacoesAusentes": [],
        },
        "justificativa": "Justificativa.",
        "conteudoOfensivo": False,
        "marcadoresConteudo": [],
        "emergencia": False,
        "orientacaoEmergencia": None,
        "entidades": {
            "endereco": None,
            "bairro": None,
            "datas": [],
            "pessoas": [],
            "protocolos": [],
            "servicos": [],
        },
    }
    monkeypatch.setattr(
        "urllib.request.urlopen",
        lambda *_args, **_kwargs: FakeResponse(
            {"message": {"content": json.dumps(content)}}
        ),
    )

    with pytest.raises(AIProviderInvalidResponse, match="categoria inexistente"):
        provider().classify(triage_input())


def test_ollama_provider_reports_connection_failure(monkeypatch):
    def unavailable(*_args, **_kwargs):
        raise urllib.error.URLError("connection refused")

    monkeypatch.setattr("urllib.request.urlopen", unavailable)

    with pytest.raises(AIProviderUnavailable, match="indisponível"):
        provider().classify(triage_input())


def test_ollama_provider_combines_deterministic_content_safety(monkeypatch):
    content = {
        "categoriaId": "category-1",
        "subcategoria": None,
        "orgaoId": None,
        "prioridadeSugerida": "MEDIA",
        "impacto": "MEDIO",
        "urgencia": "MEDIO",
        "confianca": 0.7,
        "resumo": "Pedido de atendimento.",
        "resumoEstruturado": {
            "situacao": "Pedido de atendimento.",
            "local": None,
            "afetados": None,
            "informacoesAusentes": [],
        },
        "justificativa": "Classificação temática.",
        "conteudoOfensivo": False,
        "marcadoresConteudo": [],
        "emergencia": False,
        "orientacaoEmergencia": None,
        "entidades": {
            "endereco": None,
            "bairro": None,
            "datas": [],
            "pessoas": [],
            "protocolos": [],
            "servicos": [],
        },
    }
    monkeypatch.setattr(
        "urllib.request.urlopen",
        lambda *_args, **_kwargs: FakeResponse(
            {"message": {"content": json.dumps(content)}}
        ),
    )
    data = triage_input()
    offensive_input = TriageInput(
        title=data.title,
        description="O secretário é incompetente e preciso de atendimento.",
        categories=data.categories,
        agencies=data.agencies,
    )

    result = provider().classify(offensive_input)

    assert result.offensive_content is True
    assert result.content_markers == ["xingamento"]
