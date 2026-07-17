import pytest

from app.ai.duplicates import EmbeddingProviderError, OllamaEmbeddingProvider
from app.outbox.service import process_batch

PASSWORD = "SenhaForte123!"  # noqa: S105


def test_ollama_embedding_provider_calculates_cosine_similarity(monkeypatch):
    provider = OllamaEmbeddingProvider("http://ollama:11434", "nomic-embed-text", 10)
    monkeypatch.setattr(
        provider,
        "_request",
        lambda _payload: {"embeddings": [[1, 0], [1, 0], [0, 1]]},
    )

    assert provider.similarities("origem", ["igual", "diferente"]) == [1, 0]


def test_ollama_embedding_provider_rejects_incomplete_vectors(monkeypatch):
    provider = OllamaEmbeddingProvider("http://ollama:11434", "nomic-embed-text", 10)
    monkeypatch.setattr(provider, "_request", lambda _payload: {"embeddings": [[1, 0]]})

    with pytest.raises(EmbeddingProviderError, match="incompletos"):
        provider.similarities("origem", ["candidato"])


def _login(client, tenant="gabinete-a", password=PASSWORD):
    client.post(
        "/api/v1/auth/login",
        json={
            "tenant": tenant,
            "email": "admin@teste.local",
            "password": password,
        },
    )
    return client.get_cookie("csrf_access_token").value


def _create_request(client, csrf, description, latitude, longitude):
    response = client.post(
        "/api/v1/solicitacoes",
        json={
            "origem": "WHATSAPP",
            "titulo": "Iluminação apagada",
            "descricao": description,
            "endereco": "Rua das Flores, 120",
            "latitude": latitude,
            "longitude": longitude,
        },
        headers={"X-CSRF-TOKEN": csrf},
    )
    assert response.status_code == 201
    return response.json


def test_triage_suggests_semantic_duplicates_and_requires_group_confirmation(app, client):
    csrf = _login(client)
    first = _create_request(
        client,
        csrf,
        "Poste apagado na Rua das Flores deixa toda a via escura.",
        -23.55052,
        -46.63331,
    )
    second = _create_request(
        client,
        csrf,
        "Poste apagado na Rua das Flores deixa a via muito escura.",
        -23.55062,
        -46.63341,
    )

    with app.app_context():
        process_batch("duplicate-detection-worker")

    details = client.get(f"/api/v1/solicitacoes/{second['id']}").json
    analysis = details["triagemIA"]["resultado"]["analiseDuplicidade"]
    candidate = next(item for item in analysis["candidatos"] if item["id"] == first["id"])

    assert analysis["revisaoHumanaObrigatoria"] is True
    assert analysis["modelo"] == "gabflow-token-similarity-v1"
    assert candidate["pontuacao"] >= analysis["limiar"]
    assert candidate["similaridadeSemantica"] > 0.8
    assert candidate["distanciaKm"] < 0.1
    assert details["grupoDuplicidadeId"] is None

    grouped = client.post(
        "/api/v1/solicitacoes/agrupar-duplicadas",
        json={
            "solicitacaoIds": [second["id"], candidate["id"]],
            "motivo": "Similaridade semântica confirmada pelo usuário.",
        },
        headers={"X-CSRF-TOKEN": csrf},
    )

    assert grouped.status_code == 201
    grouped_details = client.get(f"/api/v1/solicitacoes/{second['id']}").json
    assert grouped_details["grupoDuplicidadeId"] == grouped.json["id"]
    assert grouped_details["duplicidades"][0]["id"] == first["id"]


def test_semantic_duplicate_search_is_isolated_by_tenant(app, client):
    other_csrf = _login(client, "gabinete-b", "OutraSenha123!")
    _create_request(
        client,
        other_csrf,
        "Poste apagado na Rua das Flores deixa toda a via escura.",
        -23.55052,
        -46.63331,
    )
    csrf = _login(client)
    own_request = _create_request(
        client,
        csrf,
        "Poste apagado na Rua das Flores deixa toda a via escura.",
        -23.55052,
        -46.63331,
    )

    with app.app_context():
        process_batch("duplicate-tenant-worker")

    details = client.get(f"/api/v1/solicitacoes/{own_request['id']}").json
    analysis = details["triagemIA"]["resultado"]["analiseDuplicidade"]
    assert analysis["candidatos"] == []
