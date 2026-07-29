import re
import unicodedata
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum

from app.rag.analytics import structured_query
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
_FILTER_KEYS = {
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


def route_query(
    tenant_id: uuid.UUID,
    role: str | None,
    query: str,
    *,
    limit: int | None = None,
    explicit_filters: dict | None = None,
) -> dict:
    intent = classify_query(query, explicit_filters=explicit_filters)
    if intent.method == QueryMethod.DOCUMENTAL:
        answer = answer_query(tenant_id, role, query, limit)
        return _with_routing(answer, intent, None)

    structured = structured_query(tenant_id, intent.structured_payload)
    if intent.method == QueryMethod.ESTRUTURADO:
        return _structured_answer(query, intent, structured)

    documentary = answer_query(tenant_id, role, query, limit)
    documentary["resposta"] = (
        f"{_structured_response(structured)} "
        f"Complemento documental: {documentary['resposta']}"
    )
    documentary["fundamentada"] = True
    documentary["recusaConclusiva"] = False
    return _with_routing(documentary, intent, structured)


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


def _with_routing(answer: dict, intent: QueryIntent, structured: dict | None) -> dict:
    answer["metodo"] = intent.method.value
    answer["motivosRoteamento"] = list(intent.reasons)
    answer["filtrosAplicados"] = (
        structured["filtros"] if structured is not None else {}
    )
    answer["resultadoEstruturado"] = structured
    return answer


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
