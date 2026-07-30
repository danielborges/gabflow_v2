import re
import unicodedata
from dataclasses import dataclass
from datetime import date

from flask import current_app

DOCUMENTARY_FILTER_KEYS = {
    "tema",
    "tipoDocumento",
    "orgao",
    "jurisdicao",
    "inicio",
    "fim",
}

_DOCUMENT_TYPES = (
    ("LEI_COMPLEMENTAR", r"\blei complementar\b"),
    ("PROJETO_DE_LEI", r"\bprojeto de lei\b|\bpl\b"),
    ("DECRETO", r"\bdecret[oa]\b"),
    ("RESOLUCAO", r"\bresolu[cç][aã]o\b"),
    ("PORTARIA", r"\bportaria\b"),
    ("REGIMENTO", r"\bregimento\b"),
    ("REQUERIMENTO", r"\brequerimento\b"),
    ("INDICACAO", r"\bindica[cç][aã]o\b"),
    ("LEI", r"\blei\b"),
)

_THEMES = {
    "MOBILIDADE_URBANA": (
        "mobilidade",
        "transporte",
        "transito",
        "onibus",
        "ciclovia",
        "estacionamento",
    ),
    "SAUDE": ("saude", "hospital", "ubs", "medicamento", "vacina"),
    "EDUCACAO": ("educacao", "escola", "creche", "ensino", "professor"),
    "ORCAMENTO": ("orcamento", "despesa", "receita", "credito", "emenda"),
    "MEIO_AMBIENTE": (
        "meio ambiente",
        "ambiental",
        "residuo",
        "saneamento",
        "arborizacao",
    ),
    "SEGURANCA_PUBLICA": ("seguranca", "guarda municipal", "violencia"),
    "HABITACAO": ("habitacao", "moradia", "regularizacao fundiaria"),
    "ASSISTENCIA_SOCIAL": ("assistencia social", "vulnerabilidade", "beneficio"),
    "TRIBUTACAO": ("tributo", "imposto", "taxa", "iptu", "iss"),
    "SERVIDOR_PUBLICO": ("servidor", "funcionalismo", "carreira", "remuneracao"),
}

_THEME_EXPANSIONS = {
    "MOBILIDADE_URBANA": "mobilidade urbana transporte coletivo trânsito",
    "SAUDE": "saúde pública atendimento hospitalar atenção básica",
    "EDUCACAO": "educação pública ensino escola creche",
    "ORCAMENTO": "orçamento público despesa receita crédito",
    "MEIO_AMBIENTE": "meio ambiente política ambiental saneamento resíduos",
    "SEGURANCA_PUBLICA": "segurança pública guarda municipal prevenção",
    "HABITACAO": "habitação moradia regularização fundiária",
    "ASSISTENCIA_SOCIAL": "assistência social proteção benefício vulnerabilidade",
    "TRIBUTACAO": "tributação imposto taxa arrecadação",
    "SERVIDOR_PUBLICO": "servidor público carreira remuneração funcionalismo",
}

_REFERENCE_PATTERN = re.compile(
    r"\b(?P<type>lei(?:\s+complementar)?|decreto|resolu[cç][aã]o|portaria|"
    r"projeto\s+de\s+lei|requerimento|indica[cç][aã]o)"
    r"\s*(?:n[º°o.]?\s*)?(?P<number>\d[\d.]*)"
    r"(?:\s*(?:[/\-]|\bde\b)\s*(?P<year>(?:19|20)\d{2}))?",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class DocumentaryQueryPlan:
    original_query: str
    intent: str
    themes: tuple[str, ...]
    document_types: tuple[str, ...]
    references: tuple[str, ...]
    expansions: tuple[str, ...]
    filters: dict
    reasons: tuple[str, ...]

    @property
    def search_queries(self) -> tuple[str, ...]:
        return (self.original_query, *self.expansions)

    @property
    def retrieval_filters(self) -> dict:
        values = dict(self.filters)
        theme = values.get("tema")
        if theme:
            theme_text = _THEME_EXPANSIONS.get(
                theme,
                str(theme).replace("_", " "),
            )
            terms = list(
                dict.fromkeys(
                    token
                    for token in _normalize(theme_text).split()
                    if len(token) > 3
                )
            )
            values["temaBusca"] = " OR ".join(terms)
        return values

    def audit_data(self) -> dict:
        return {
            "intencaoDocumental": self.intent,
            "temas": list(self.themes),
            "tiposDocumento": list(self.document_types),
            "referenciasNormativas": list(self.references),
            "consultaOriginal": self.original_query,
            "consultasExpandidas": list(self.expansions),
            "filtrosDocumentais": self.filters,
            "motivos": list(self.reasons),
            "provedor": "DETERMINISTICO",
            "modelo": "gabflow-query-understanding-v1",
            "versao": "query-understanding-v1",
        }


def understand_documentary_query(
    query: str,
    *,
    explicit_filters: dict | None = None,
) -> DocumentaryQueryPlan:
    original = " ".join(str(query or "").split())
    normalized = _normalize(original)
    document_types = tuple(
        value
        for value, pattern in _DOCUMENT_TYPES
        if re.search(pattern, normalized, re.IGNORECASE)
    )
    # "LEI" é termo genérico e não deve duplicar classificações específicas.
    if any(value in document_types for value in ("LEI_COMPLEMENTAR", "PROJETO_DE_LEI")):
        document_types = tuple(value for value in document_types if value != "LEI")
    themes = tuple(
        theme
        for theme, keywords in _THEMES.items()
        if any(_contains_keyword(normalized, keyword) for keyword in keywords)
    )
    references = tuple(
        dict.fromkeys(
            _canonical_reference(match)
            for match in _REFERENCE_PATTERN.finditer(original)
        )
    )
    intent = _intent(document_types, references, themes)
    inferred_filters = {}
    if len(document_types) == 1:
        inferred_filters["tipoDocumento"] = document_types[0]
    if len(themes) == 1:
        inferred_filters["tema"] = themes[0]
    inferred_filters.update(_temporal_filters(normalized))
    explicit = _validate_explicit_filters(explicit_filters or {})
    filters = {**inferred_filters, **explicit}
    reasons = []
    if document_types:
        reasons.append("TIPO_DOCUMENTAL_IDENTIFICADO")
    if references:
        reasons.append("REFERENCIA_NORMATIVA_IDENTIFICADA")
    if themes:
        reasons.append("TEMA_IDENTIFICADO")
    if any(key in filters for key in ("inicio", "fim")):
        reasons.append("PERIODO_IDENTIFICADO")
    if explicit:
        reasons.append("FILTROS_DOCUMENTAIS_EXPLICITOS")
    expansions = _expansions(original, document_types, themes, references)
    if expansions:
        reasons.append("EXPANSAO_CONTROLADA_APLICADA")
    return DocumentaryQueryPlan(
        original_query=original,
        intent=intent,
        themes=themes,
        document_types=document_types,
        references=references,
        expansions=expansions,
        filters=filters,
        reasons=tuple(reasons or ["CONSULTA_DOCUMENTAL_GERAL"]),
    )


def _intent(
    document_types: tuple[str, ...],
    references: tuple[str, ...],
    themes: tuple[str, ...],
) -> str:
    if references:
        return "ATO_NORMATIVO_ESPECIFICO"
    if document_types:
        return "TIPO_DOCUMENTAL"
    if themes:
        return "PESQUISA_TEMATICA"
    return "PESQUISA_DOCUMENTAL_GERAL"


def _canonical_reference(match: re.Match) -> str:
    reference_type = _normalize(match.group("type")).upper().replace(" ", "_")
    number = match.group("number")
    year = match.group("year")
    return f"{reference_type} {number}" + (f"/{year}" if year else "")


def _temporal_filters(query: str) -> dict:
    between = re.search(
        r"\b(?:entre|de)\s+((?:19|20)\d{2})\s+(?:e|a|ate)\s+((?:19|20)\d{2})\b",
        query,
    )
    if between:
        start, end = sorted((int(between.group(1)), int(between.group(2))))
        return {"inicio": f"{start:04d}-01-01", "fim": f"{end:04d}-12-31"}
    in_year = re.search(r"\b(?:em|no ano de|do ano de)\s+((?:19|20)\d{2})\b", query)
    if in_year:
        year = int(in_year.group(1))
        return {"inicio": f"{year:04d}-01-01", "fim": f"{year:04d}-12-31"}
    return {}


def _expansions(
    original: str,
    document_types: tuple[str, ...],
    themes: tuple[str, ...],
    references: tuple[str, ...],
) -> tuple[str, ...]:
    limit = max(0, min(5, current_app.config["RAG_QUERY_EXPANSION_MAX_QUERIES"]))
    if not limit:
        return ()
    values = []
    for reference in references:
        normalized_reference = reference.replace("_", " ").replace("/", " ")
        values.append(normalized_reference)
        values.append(f"{normalized_reference} legislação norma artigo")
    for theme in themes:
        values.append(_THEME_EXPANSIONS[theme])
    if document_types and themes:
        values.append(
            f"{document_types[0].replace('_', ' ')} {_THEME_EXPANSIONS[themes[0]]}"
        )
    original_normalized = _normalize(original)
    result = []
    for raw in values:
        value = " ".join(raw.split())[:500]
        if (
            value
            and _normalize(value) != original_normalized
            and _normalize(value) not in {_normalize(item) for item in result}
        ):
            result.append(value)
        if len(result) >= limit:
            break
    return tuple(result)


def _validate_explicit_filters(filters: dict) -> dict:
    result = {}
    for key in DOCUMENTARY_FILTER_KEYS:
        if key not in filters or filters[key] in (None, ""):
            continue
        value = " ".join(str(filters[key]).split())
        maximum = 180 if key == "orgao" else 120
        if not value or len(value) > maximum:
            raise ValueError(f"Filtro documental {key} inválido.")
        if key in {"inicio", "fim"}:
            try:
                value = date.fromisoformat(value).isoformat()
            except ValueError as error:
                raise ValueError(f"Filtro documental {key} deve usar AAAA-MM-DD.") from error
        result[key] = value
    if result.get("inicio") and result.get("fim"):
        if date.fromisoformat(result["inicio"]) > date.fromisoformat(result["fim"]):
            raise ValueError("O início do filtro documental deve ser anterior ao fim.")
    return result


def _normalize(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value.casefold())
    return "".join(character for character in normalized if not unicodedata.combining(character))


def _contains_keyword(text: str, keyword: str) -> bool:
    return bool(
        re.search(
            rf"(?<!\w){re.escape(_normalize(keyword))}(?!\w)",
            text,
        )
    )
