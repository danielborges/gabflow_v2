import hashlib
import re
import unicodedata
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum

from app.models import RagLearningArtifactType
from app.rag.analytics import structured_query
from app.rag.learning import active_learning_artifacts, learning_influence_data
from app.rag.query_understanding import (
    DOCUMENTARY_FILTER_KEYS,
    understand_documentary_query,
)
from app.rag.retrieval import answer_query


class QueryMethod(StrEnum):
    DOCUMENTAL = "DOCUMENTAL"
    ESTRUTURADO = "ESTRUTURADO"
    HIBRIDO = "HIBRIDO"


@dataclass(frozen=True)
class QueryIntent:
    method: QueryMethod
    structured_payload: dict
    reasons: tuple[str, ...]


_STRUCTURED_PATTERNS = (
    r"\bquant[oa]s?\b",
    r"\btotal\b",
    r"\bcontagem\b",
    r"\bn[uú]mero de\b",
    r"\bm[eé]dia\b",
    r"\bpercentual\b",
    r"\btaxa\b",
    r"\bpor (?:status|situa[cç][aã]o|tema|territ[oó]rio|bairro|regi[aã]o|"
    r"[oó]rg[aã]o|secretaria|tipo|etapa|comiss[aã]o|m[eê]s)\b",
    r"\bprazos? vencidos?\b",
    r"\batrasad[oa]s?\b",
    r"\bquais temas recorrentes\b",
)
_DOCUMENTARY_PATTERNS = (
    r"\bargumentos?\b",
    r"\bfundamentos?\b",
    r"\bjustificativas?\b",
    r"\bevid[eê]ncias?\b",
    r"\bfontes?\b",
    r"\bdocumentos?\b",
    r"\brelatos?\b",
    r"\bresum[aoe]\b",
    r"\bexplique\b",
    r"\bdescreva\b",
    r"\bo que (?:diz|dizem|consta)\b",
    r"\bquais temas recorrentes\b",
)
_STRUCTURED_FILTER_KEYS = {
    "dataset",
    "metrica",
    "agruparPor",
    "inicio",
    "fim",
    "status",
    "tema",
    "territorioId",
    "orgaoId",
}
_FILTER_KEYS = _STRUCTURED_FILTER_KEYS | DOCUMENTARY_FILTER_KEYS


def route_query(
    tenant_id: uuid.UUID,
    role: str | None,
    query: str,
    *,
    limit: int | None = None,
    explicit_filters: dict | None = None,
    learning_artifacts: dict | None = None,
    canary_key: str | None = None,
) -> dict:
    artifacts = (
        active_learning_artifacts(tenant_id, canary_key=canary_key)
        if learning_artifacts is None
        else learning_artifacts
    )
    intent = classify_query(query, explicit_filters=explicit_filters)
    applied_artifacts = []
    routing_artifact = artifacts.get(RagLearningArtifactType.ROUTING_EXAMPLES)
    if routing_artifact is not None:
        intent, routing_applied = _apply_routing_artifact(
            query,
            intent,
            routing_artifact,
        )
        if routing_applied:
            applied_artifacts.append(learning_influence_data(routing_artifact))
    rerank_artifact = artifacts.get(RagLearningArtifactType.RERANK_PROFILE)
    documentary_plan = (
        understand_documentary_query(query, explicit_filters=explicit_filters)
        if intent.method in {QueryMethod.DOCUMENTAL, QueryMethod.HIBRIDO}
        else None
    )
    if intent.method == QueryMethod.DOCUMENTAL:
        answer = answer_query(
            tenant_id,
            role,
            query,
            limit,
            rerank_artifact=rerank_artifact,
            applied_artifacts=applied_artifacts,
            retrieval_plan=documentary_plan,
        )
        return _with_routing(
            answer,
            intent,
            None,
            applied_artifacts,
            documentary_plan=documentary_plan,
        )

    structured = structured_query(tenant_id, intent.structured_payload)
    if intent.method == QueryMethod.ESTRUTURADO:
        answer = _structured_answer(query, intent, structured)
        answer["artefatosAprendizado"] = applied_artifacts
        return answer

    documentary = answer_query(
        tenant_id,
        role,
        query,
        limit,
        rerank_artifact=rerank_artifact,
        applied_artifacts=applied_artifacts,
        retrieval_plan=documentary_plan,
    )
    documentary["resposta"] = (
        f"{_structured_response(structured)} "
        f"Complemento documental: {documentary['resposta']}"
    )
    documentary["fundamentada"] = True
    documentary["recusaConclusiva"] = False
    return _with_routing(
        documentary,
        intent,
        structured,
        applied_artifacts,
        documentary_plan=documentary_plan,
    )


def classify_query(
    query: str,
    *,
    explicit_filters: dict | None = None,
) -> QueryIntent:
    value = " ".join(str(query or "").split())
    if len(value) < 3:
        raise ValueError("Informe uma consulta com pelo menos 3 caracteres.")
    normalized = _normalize(value)
    structured = any(re.search(pattern, normalized) for pattern in _STRUCTURED_PATTERNS)
    documentary = any(re.search(pattern, normalized) for pattern in _DOCUMENTARY_PATTERNS)
    reasons = []
    if structured:
        reasons.append("INDICADOR_QUANTITATIVO_OU_AGRUPAMENTO")
    if documentary:
        reasons.append("EVIDENCIA_SEMANTICA_SOLICITADA")
    method = (
        QueryMethod.HIBRIDO
        if structured and documentary
        else QueryMethod.ESTRUTURADO
        if structured
        else QueryMethod.DOCUMENTAL
    )
    payload = _structured_payload(normalized)
    if explicit_filters is not None:
        if not isinstance(explicit_filters, dict):
            raise ValueError("filtros deve ser um objeto.")
        unknown = set(explicit_filters) - _FILTER_KEYS
        if unknown:
            raise ValueError(
                f"Filtros de roteamento não suportados: {', '.join(sorted(unknown))}."
            )
        payload.update(
            {
                key: value
                for key, value in explicit_filters.items()
                if key in _STRUCTURED_FILTER_KEYS
                if value not in (None, "")
            }
        )
        reasons.append("FILTROS_EXPLICITOS_APLICADOS")
    return QueryIntent(method, payload, tuple(reasons or ["CONSULTA_SEMANTICA"]))


def _structured_payload(query: str) -> dict:
    if re.search(r"\b(tramita|comiss[aã]o|pauta legislativa)\w*", query):
        dataset = "TRAMITACOES"
    elif re.search(r"\b(encaminh|resposta do [oó]rg[aã]o|retorno do [oó]rg[aã]o)\w*", query):
        dataset = "ENCAMINHAMENTOS"
    elif re.search(r"\b(agenda|compromisso|reuni[aã]o|visita)\w*", query):
        dataset = "AGENDA"
    elif re.search(r"\b(fiscaliza|vistoria)\w*", query):
        dataset = "FISCALIZACOES"
    else:
        dataset = "SOLICITACOES"

    if re.search(r"\btempo m[eé]dio\b|\bm[eé]dia.*resolu[cç][aã]o\b", query):
        metric = "TEMPO_MEDIO_RESOLUCAO_HORAS"
        dataset = "SOLICITACOES"
    elif re.search(r"\bprazos? vencidos?\b|\batrasad[oa]s?\b", query):
        metric = "PRAZOS_VENCIDOS"
        if dataset not in {"SOLICITACOES", "ENCAMINHAMENTOS"}:
            dataset = "SOLICITACOES"
    else:
        metric = "CONTAGEM"

    group_patterns = (
        ("STATUS", r"\bpor (?:status|situa[cç][aã]o)\b"),
        ("TEMA", r"\bpor tema\b|\btemas recorrentes\b"),
        ("TERRITORIO", r"\bpor (?:territ[oó]rio|bairro|regi[aã]o)\b"),
        ("ORGAO", r"\bpor (?:[oó]rg[aã]o|secretaria)\b"),
        ("TIPO", r"\bpor tipo\b"),
        ("ETAPA", r"\bpor (?:etapa|comiss[aã]o)\b"),
        ("MES", r"\bpor m[eê]s\b|\bmensal(?:mente)?\b"),
    )
    group_by = next(
        (group for group, pattern in group_patterns if re.search(pattern, query)),
        "NENHUM",
    )
    payload = {
        "dataset": dataset,
        "metrica": metric,
        "agruparPor": group_by,
    }
    days_match = re.search(r"\b(?:ultim[oa]s?|nos ultimos)\s+(\d{1,4})\s+dias\b", query)
    if days_match:
        days = max(1, min(int(days_match.group(1)), 3660))
        today = datetime.now(UTC).date()
        payload["inicio"] = (today - timedelta(days=days)).isoformat()
        payload["fim"] = today.isoformat()
    status = _status_filter(query, dataset)
    if status:
        payload["status"] = status
    return payload


def _status_filter(query: str, dataset: str) -> str | None:
    values = {
        "SOLICITACOES": (
            "NOVA",
            "TRIAGEM",
            "EM_ATENDIMENTO",
            "AGUARDANDO_ORGAO",
            "AGUARDANDO_CIDADAO",
            "RESOLVIDA",
            "ENCERRADA",
            "CANCELADA",
        ),
        "ENCAMINHAMENTOS": (
            "ENCAMINHADO",
            "AGUARDANDO_RETORNO",
            "RESPONDIDO",
            "ENCERRADO",
        ),
        "AGENDA": ("AGENDADO", "REALIZADO", "CANCELADO"),
        "FISCALIZACOES": ("PLANEJADA", "EM_ANDAMENTO", "CONCLUIDA", "CANCELADA"),
        "TRAMITACOES": (
            "PROTOCOLADA",
            "DISTRIBUIDA",
            "EM_COMISSAO",
            "EM_PAUTA",
            "APROVADA",
            "REJEITADA",
            "SANCIONADA",
            "VETADA",
            "ARQUIVADA",
            "RETIRADA",
        ),
    }
    comparable = query.replace(" ", "_")
    for status in values[dataset]:
        if _normalize(status.lower()) in comparable:
            return status
    return None


def _structured_answer(query: str, intent: QueryIntent, result: dict) -> dict:
    return {
        "consulta": " ".join(str(query).split()),
        "resposta": _structured_response(result),
        "fundamentada": True,
        "recusaConclusiva": False,
        "conteudoTratadoComoDado": True,
        "limiarEvidencia": 0.0,
        "modeloEmbedding": "NAO_APLICAVEL",
        "fallbackUtilizado": False,
        "erroFallback": None,
        "seguranca": {
            "promptInjectionDetectado": False,
            "fontesComRisco": [],
            "politica": (
                "Consulta estruturada parametrizada, sem execução de "
                "instruções do usuário."
            ),
        },
        "geracao": {
            "habilitada": False,
            "aplicada": False,
            "modelo": None,
            "versaoPrompt": None,
            "fallbackUtilizado": False,
            "erroFallback": None,
            "afirmacoes": 0,
            "citacoes": 0,
            "validacaoCruzada": {
                "valida": False,
                "motivo": "CONSULTA_ESTRUTURADA",
            },
        },
        "citacoes": [],
        "fontes": [],
        "escoposConsultados": ["PRIVADO"],
        "recuperacao": {
            "total": 0,
            "global": 0,
            "privado": 0,
            "modo": "ESTRUTURADO",
        },
        "metodo": intent.method.value,
        "motivosRoteamento": list(intent.reasons),
        "filtrosAplicados": result["filtros"],
        "resultadoEstruturado": result,
    }


def _with_routing(
    answer: dict,
    intent: QueryIntent,
    structured: dict | None,
    applied_artifacts: list | None = None,
    documentary_plan=None,
) -> dict:
    answer["metodo"] = intent.method.value
    answer["motivosRoteamento"] = list(intent.reasons)
    structured_filters = structured["filtros"] if structured is not None else {}
    documentary_filters = (
        documentary_plan.filters if documentary_plan is not None else {}
    )
    answer["filtrosAplicados"] = {
        **structured_filters,
        **documentary_filters,
    }
    answer["entendimentoConsulta"] = (
        documentary_plan.audit_data() if documentary_plan is not None else None
    )
    answer["resultadoEstruturado"] = structured
    answer["artefatosAprendizado"] = applied_artifacts or []
    return answer


def _apply_routing_artifact(query: str, intent: QueryIntent, artifact):
    normalized = " ".join(str(query or "").split())
    query_hash = hashlib.sha256(normalized.encode("utf-8")).hexdigest()
    example = next(
        (
            item
            for item in artifact.payload.get("exemplos", [])
            if item.get("consultaHash") == query_hash
        ),
        None,
    )
    if example is None:
        return intent, False
    method_value = example.get("metodoEsperado") or intent.method.value
    try:
        method = QueryMethod(method_value)
    except ValueError:
        return intent, False
    filters = dict(intent.structured_payload)
    filters.update(
        {
            key: value
            for key, value in (example.get("filtrosEsperados") or {}).items()
            if key in _FILTER_KEYS and value not in (None, "")
        }
    )
    reasons = tuple(
        dict.fromkeys((*intent.reasons, "EXEMPLO_DE_ROTEAMENTO_APROVADO"))
    )
    return QueryIntent(method, filters, reasons), True


def _structured_response(result: dict) -> str:
    total = result["total"]
    metric = result["metrica"].lower().replace("_", " ")
    total_label = total if total is not None else "sem dados"
    response = f"Resultado estruturado para {metric}: {total_label}."
    if result["itens"]:
        groups = "; ".join(
            f"{item['grupo']}: {item['valor'] if item['valor'] is not None else 'sem dados'}"
            for item in result["itens"][:20]
        )
        response = f"{response} Agrupamentos: {groups}."
    return response


def _normalize(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value.casefold())
    return "".join(char for char in normalized if not unicodedata.combining(char))
