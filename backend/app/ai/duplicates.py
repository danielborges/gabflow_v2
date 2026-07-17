import json
import math
import re
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter
from datetime import timedelta
from typing import Protocol

from flask import current_app
from sqlalchemy import select

from app.extensions import db
from app.models import ServiceRequest


class EmbeddingProviderError(RuntimeError):
    pass


class EmbeddingProvider(Protocol):
    model: str

    def similarities(self, source: str, candidates: list[str]) -> list[float]: ...


class OllamaEmbeddingProvider:
    def __init__(self, base_url: str, model: str, timeout_seconds: int) -> None:
        parsed_url = urllib.parse.urlsplit(base_url)
        if parsed_url.scheme not in {"http", "https"} or not parsed_url.hostname:
            raise ValueError("OLLAMA_BASE_URL deve ser uma URL HTTP ou HTTPS válida.")
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout_seconds = timeout_seconds

    def similarities(self, source: str, candidates: list[str]) -> list[float]:
        response = self._request({"model": self.model, "input": [source, *candidates]})
        embeddings = response.get("embeddings")
        if not isinstance(embeddings, list) or len(embeddings) != len(candidates) + 1:
            raise EmbeddingProviderError("O Ollama retornou embeddings incompletos.")
        source_vector = _numeric_vector(embeddings[0])
        return [_cosine(source_vector, _numeric_vector(vector)) for vector in embeddings[1:]]

    def _request(self, payload: dict) -> dict:
        request = urllib.request.Request(  # noqa: S310 - URL validated in __init__
            f"{self.base_url}/api/embed",
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(  # noqa: S310 - URL validated in __init__
                request,
                timeout=self.timeout_seconds,
            ) as response:
                return json.loads(response.read().decode("utf-8"))
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError) as error:
            raise EmbeddingProviderError("Modelo local de embeddings indisponível.") from error
        except json.JSONDecodeError as error:
            raise EmbeddingProviderError("O Ollama retornou embeddings inválidos.") from error


class LocalSimilarityProvider:
    model = "gabflow-token-similarity-v1"

    def similarities(self, source: str, candidates: list[str]) -> list[float]:
        source_vector = _token_vector(source)
        return [
            _counter_cosine(source_vector, _token_vector(candidate))
            for candidate in candidates
        ]


def duplicate_suggestions(service_request: ServiceRequest) -> dict:
    window_days = current_app.config["AI_DUPLICATE_WINDOW_DAYS"]
    threshold = current_app.config["AI_DUPLICATE_SCORE_THRESHOLD"]
    maximum = current_app.config["AI_DUPLICATE_MAX_SUGGESTIONS"]
    candidate_limit = current_app.config["AI_DUPLICATE_CANDIDATE_LIMIT"]
    start = service_request.created_at - timedelta(days=window_days)
    end = service_request.created_at + timedelta(days=window_days)
    candidates = list(
        db.session.execute(
            select(ServiceRequest)
            .where(
                ServiceRequest.tenant_id == service_request.tenant_id,
                ServiceRequest.id != service_request.id,
                ServiceRequest.created_at.between(start, end),
            )
            .order_by(ServiceRequest.created_at.desc())
            .limit(candidate_limit)
        ).scalars()
    )
    candidates = [
        item
        for item in candidates
        if not (
            service_request.duplicate_group_id
            and item.duplicate_group_id == service_request.duplicate_group_id
        )
    ]
    provider = _embedding_provider()
    used_fallback = False
    error = None
    similarities: list[float] = []
    if candidates:
        try:
            similarities = provider.similarities(
                _request_text(service_request),
                [_request_text(item) for item in candidates],
            )
        except EmbeddingProviderError as provider_error:
            if not current_app.config["AI_TRIAGE_FALLBACK_ENABLED"]:
                raise
            current_app.logger.warning(
                "Falha no modelo de embeddings; usando similaridade local: %s",
                provider_error,
            )
            provider = LocalSimilarityProvider()
            similarities = provider.similarities(
                _request_text(service_request),
                [_request_text(item) for item in candidates],
            )
            used_fallback = True
            error = str(provider_error)

    ranked = []
    for candidate, semantic_score in zip(candidates, similarities, strict=True):
        time_days = abs((service_request.created_at - candidate.created_at).total_seconds()) / 86400
        temporal_score = math.exp(-time_days / 30)
        distance = _distance_km(service_request, candidate)
        geographic_score = math.exp(-distance / 5) if distance is not None else None
        score = _combined_score(semantic_score, temporal_score, geographic_score)
        if score < threshold:
            continue
        ranked.append(
            {
                "id": str(candidate.id),
                "protocolo": candidate.protocol,
                "titulo": candidate.title or "Solicitação sem título",
                "status": candidate.status.value,
                "criadaEm": candidate.created_at.isoformat(),
                "pontuacao": round(score, 4),
                "similaridadeSemantica": round(semantic_score, 4),
                "proximidadeTemporal": round(temporal_score, 4),
                "distanciaKm": round(distance, 2) if distance is not None else None,
                "proximidadeGeografica": (
                    round(geographic_score, 4) if geographic_score is not None else None
                ),
                "justificativas": _reasons(semantic_score, time_days, distance),
            }
        )
    ranked.sort(key=lambda item: item["pontuacao"], reverse=True)
    return {
        "modelo": provider.model,
        "fallbackUtilizado": used_fallback,
        "erroFallback": error,
        "limiar": threshold,
        "janelaDias": window_days,
        "revisaoHumanaObrigatoria": True,
        "candidatos": ranked[:maximum],
    }


def _embedding_provider() -> EmbeddingProvider:
    if current_app.config["AI_DUPLICATE_PROVIDER"].lower() == "local":
        return LocalSimilarityProvider()
    return OllamaEmbeddingProvider(
        current_app.config["OLLAMA_BASE_URL"],
        current_app.config["AI_EMBEDDING_MODEL"],
        current_app.config["AI_TRIAGE_TIMEOUT_SECONDS"],
    )


def _request_text(service_request: ServiceRequest) -> str:
    fields = (
        service_request.title,
        service_request.description,
        service_request.address,
        service_request.category,
        service_request.subcategory,
        service_request.theme,
    )
    return "\n".join(str(value).strip() for value in fields if value and str(value).strip())


def _combined_score(semantic: float, temporal: float, geographic: float | None) -> float:
    weighted = semantic * 0.75 + temporal * 0.15
    weight = 0.9
    if geographic is not None:
        weighted += geographic * 0.1
        weight += 0.1
    return weighted / weight


def _reasons(semantic: float, time_days: float, distance: float | None) -> list[str]:
    reasons = [f"Similaridade semântica de {round(semantic * 100)}%"]
    if time_days <= 1:
        reasons.append("Relatos registrados no mesmo período")
    elif time_days <= 7:
        reasons.append("Relatos registrados em até 7 dias")
    if distance is not None:
        if distance <= 0.5:
            reasons.append("Localização a menos de 500 m")
        elif distance <= 5:
            reasons.append("Localização a menos de 5 km")
    return reasons


def _distance_km(first: ServiceRequest, second: ServiceRequest) -> float | None:
    if None in (first.latitude, first.longitude, second.latitude, second.longitude):
        return None
    latitude_1 = math.radians(float(first.latitude))
    latitude_2 = math.radians(float(second.latitude))
    latitude_delta = latitude_2 - latitude_1
    longitude_delta = math.radians(float(second.longitude) - float(first.longitude))
    haversine = (
        math.sin(latitude_delta / 2) ** 2
        + math.cos(latitude_1) * math.cos(latitude_2) * math.sin(longitude_delta / 2) ** 2
    )
    haversine = min(1.0, max(0.0, haversine))
    return 6371 * 2 * math.atan2(math.sqrt(haversine), math.sqrt(1 - haversine))


def _numeric_vector(value: object) -> list[float]:
    if not isinstance(value, list) or not value:
        raise EmbeddingProviderError("O Ollama retornou um vetor de embedding inválido.")
    if any(not isinstance(item, int | float) for item in value):
        raise EmbeddingProviderError("O Ollama retornou um vetor de embedding inválido.")
    return [float(item) for item in value]


def _cosine(first: list[float], second: list[float]) -> float:
    if len(first) != len(second):
        raise EmbeddingProviderError("Os embeddings retornados possuem dimensões incompatíveis.")
    first_norm = math.sqrt(sum(value * value for value in first))
    second_norm = math.sqrt(sum(value * value for value in second))
    if not first_norm or not second_norm:
        return 0
    dot_product = sum(a * b for a, b in zip(first, second, strict=True))
    return max(0.0, min(1.0, dot_product / (first_norm * second_norm)))


def _token_vector(value: str) -> Counter[str]:
    normalized = unicodedata.normalize("NFKD", value.lower())
    ascii_text = "".join(char for char in normalized if not unicodedata.combining(char))
    tokens = re.findall(r"[a-z0-9]{3,}", ascii_text)
    ignored = {"para", "com", "uma", "uns", "das", "dos", "que", "por", "esta", "estao"}
    return Counter(token for token in tokens if token not in ignored)


def _counter_cosine(first: Counter[str], second: Counter[str]) -> float:
    first_norm = math.sqrt(sum(value * value for value in first.values()))
    second_norm = math.sqrt(sum(value * value for value in second.values()))
    if not first_norm or not second_norm:
        return 0
    dot_product = sum(value * second.get(token, 0) for token, value in first.items())
    return dot_product / (first_norm * second_norm)
