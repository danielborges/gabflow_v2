import json
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass

from flask import current_app

_DATASETS = {
    "SOLICITACOES",
    "CIDADAOS",
    "ENCAMINHAMENTOS",
    "AGENDA",
    "FISCALIZACOES",
    "TRAMITACOES",
}
_METRICS = {"CONTAGEM", "TEMPO_MEDIO_RESOLUCAO_HORAS", "PRAZOS_VENCIDOS"}
_GROUPS = {"NENHUM", "STATUS", "TEMA", "TERRITORIO", "ORGAO", "TIPO", "ETAPA", "MES"}


@dataclass(frozen=True)
class StructuredInterpretation:
    payload: dict
    applied: bool
    fallback_error: str | None = None


def interpret_structured_query(query: str, deterministic_payload: dict) -> StructuredInterpretation:
    if not current_app.config["RAG_STRUCTURED_INTERPRETATION_ENABLED"]:
        return StructuredInterpretation(dict(deterministic_payload), False)
    if current_app.config["RAG_STRUCTURED_INTERPRETATION_PROVIDER"].lower() != "ollama":
        return StructuredInterpretation(
            dict(deterministic_payload),
            False,
            "Provider de interpretação estruturada não suportado.",
        )

    try:
        interpreted = _request_ollama(query, deterministic_payload)
        return StructuredInterpretation(
            _validated_merge(deterministic_payload, interpreted),
            True,
        )
    except (ValueError, KeyError, TypeError, urllib.error.URLError, TimeoutError) as error:
        current_app.logger.warning(
            "Interpretação estruturada por IA indisponível; usando regras determinísticas: %s",
            error,
        )
        return StructuredInterpretation(dict(deterministic_payload), False, str(error)[:200])


def _request_ollama(query: str, deterministic_payload: dict) -> dict:
    base_url = str(current_app.config["OLLAMA_BASE_URL"]).rstrip("/")
    parsed_url = urllib.parse.urlsplit(base_url)
    if parsed_url.scheme not in {"http", "https"} or not parsed_url.hostname:
        raise ValueError("OLLAMA_BASE_URL inválida.")
    model = str(current_app.config["RAG_STRUCTURED_INTERPRETATION_MODEL"])
    body = {
        "model": model,
        "stream": False,
        "keep_alive": "5m",
        "format": _schema(),
        "options": {
            "temperature": 0,
            "num_ctx": 2048,
            "num_predict": max(
                64,
                int(current_app.config["RAG_STRUCTURED_INTERPRETATION_MAX_TOKENS"]),
            ),
        },
        "messages": [
            {
                "role": "system",
                "content": (
                    "Você interpreta perguntas quantitativas de um sistema de gabinete. "
                    "Escolha somente valores permitidos pelo schema e não responda à pergunta. "
                    "Pessoa, pessoas, morador, munícipe e eleitor, quando descritos como "
                    "cadastrados ou filtrados por nome, referem-se ao cadastro de CIDADAOS. "
                    "Demandas, pedidos e atendimentos referem-se a SOLICITACOES. Extraia nome "
                    "somente quando a pergunta solicitar filtro pelo nome de uma pessoa. Não "
                    "invente filtros. O plano inicial "
                    "é apenas uma hipótese e deve ser corrigido conforme o sentido da pergunta."
                ),
            },
            {
                "role": "user",
                "content": json.dumps(
                    {"pergunta": query, "planoInicial": deterministic_payload},
                    ensure_ascii=False,
                ),
            },
        ],
    }
    request = urllib.request.Request(  # noqa: S310 - URL validada acima
        f"{base_url}/api/chat",
        data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(  # noqa: S310 - URL validada acima
        request,
        timeout=current_app.config["RAG_STRUCTURED_INTERPRETATION_TIMEOUT_SECONDS"],
    ) as response:
        result = json.loads(response.read().decode("utf-8"))
    content = result["message"]["content"]
    return json.loads(content)


def _validated_merge(deterministic_payload: dict, interpreted: dict) -> dict:
    dataset = str(interpreted["dataset"]).upper()
    metric = str(interpreted["metrica"]).upper()
    group = str(interpreted["agruparPor"]).upper()
    confidence = float(interpreted["confianca"])
    if dataset not in _DATASETS or metric not in _METRICS or group not in _GROUPS:
        raise ValueError("A interpretação retornou valores fora do contrato.")
    if not 0 <= confidence <= 1:
        raise ValueError("A interpretação retornou confiança inválida.")
    if confidence < 0.6:
        return dict(deterministic_payload)
    if metric == "TEMPO_MEDIO_RESOLUCAO_HORAS" and dataset != "SOLICITACOES":
        raise ValueError("A interpretação retornou combinação inválida.")
    if metric == "PRAZOS_VENCIDOS" and dataset not in {"SOLICITACOES", "ENCAMINHAMENTOS"}:
        raise ValueError("A interpretação retornou combinação inválida.")

    merged = {
        **deterministic_payload,
        "dataset": dataset,
        "metrica": metric,
        "agruparPor": group,
    }
    name = " ".join(str(interpreted.get("nome") or "").split())
    if dataset == "CIDADAOS" and name:
        merged["nome"] = name[:80]
    else:
        merged.pop("nome", None)
    return merged


def _schema() -> dict:
    return {
        "type": "object",
        "properties": {
            "dataset": {"type": "string", "enum": sorted(_DATASETS)},
            "metrica": {"type": "string", "enum": sorted(_METRICS)},
            "agruparPor": {"type": "string", "enum": sorted(_GROUPS)},
            "nome": {"type": ["string", "null"]},
            "confianca": {"type": "number", "minimum": 0, "maximum": 1},
        },
        "required": ["dataset", "metrica", "agruparPor", "nome", "confianca"],
        "additionalProperties": False,
    }
