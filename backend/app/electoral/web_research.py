import ipaddress
import json
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import UTC, datetime

from flask import current_app

from app.rag.content_security import has_prompt_injection


@dataclass(frozen=True)
class ElectoralWebSource:
    title: str
    url: str
    snippet: str
    engine: str | None
    published_at: str | None


def research_electoral_context(
    question: str, analysis: dict
) -> tuple[list[ElectoralWebSource], dict]:
    if not current_app.config["ELECTORAL_WEB_RESEARCH_ENABLED"]:
        return [], {"enabled": False, "applied": False, "resultCount": 0}

    queries = _research_queries(question, analysis)
    try:
        sources = []
        seen_urls = set()
        for query in queries:
            for source in _parse_sources(_search(query)):
                if source.url in seen_urls:
                    continue
                seen_urls.add(source.url)
                sources.append(source)
                if len(sources) >= current_app.config["ELECTORAL_WEB_RESEARCH_MAX_RESULTS"]:
                    break
            if len(sources) >= current_app.config["ELECTORAL_WEB_RESEARCH_MAX_RESULTS"]:
                break
    except (OSError, TimeoutError, ValueError, urllib.error.URLError) as error:
        current_app.logger.warning("Pesquisa web eleitoral indisponivel: %s", error)
        return [], {
            "enabled": True,
            "applied": False,
            "resultCount": 0,
            "reason": error.__class__.__name__,
        }
    return sources, {
        "enabled": True,
        "applied": bool(sources),
        "resultCount": len(sources),
        "queries": queries,
        "researchedAt": datetime.now(UTC).isoformat(),
        "provider": "SEARXNG",
    }


def _research_queries(question: str, analysis: dict) -> list[str]:
    candidates = analysis.get("candidates") or [analysis.get("candidate") or {}]
    names = [
        str(item.get("ballot_name") or item.get("full_name") or "").strip()
        for item in candidates
    ]
    names = [name for name in names if name][:5]
    territories = [
        str(item.get("territory_name") or "").strip()
        for item in (analysis.get("items") or [])[:5]
    ]
    territories = list(dict.fromkeys(value for value in territories if value))
    place = territories[0].split(" - ", 1)[0] if territories else ""
    queries = []
    for name in names[:2]:
        prefix = " ".join(filter(None, (f'"{name}"', f'"{place}"' if place else "")))
        queries.extend(
            (f"{prefix} eleicoes campanha propostas", f"{prefix} vereador atuacao noticias")
        )
    if place:
        queries.append(f'"{place}" perfil socioeconomico bairros IBGE')
    return list(dict.fromkeys(query[:300] for query in queries if query.strip()))[:5]


def _research_query(question: str, analysis: dict) -> str:
    """Compatibilidade para diagnosticos que esperam uma consulta representativa."""
    queries = _research_queries(question, analysis)
    return queries[0] if queries else "eleicoes resultado eleitoral"


def _search(query: str) -> dict:
    base_url = current_app.config["ELECTORAL_WEB_RESEARCH_BASE_URL"].rstrip("/")
    parsed = urllib.parse.urlsplit(base_url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("URL do pesquisador web invalida.")
    params = urllib.parse.urlencode(
        {
            "q": query,
            "format": "json",
            "language": "pt-BR",
            "safesearch": "1",
            "categories": "general,news",
        }
    )
    request = urllib.request.Request(  # noqa: S310 - endpoint interno configurado
        f"{base_url}/search?{params}",
        headers={"Accept": "application/json", "User-Agent": "GabFlow-Electoral/1.0"},
    )
    with urllib.request.urlopen(  # noqa: S310 - endpoint interno configurado
        request,
        timeout=current_app.config["ELECTORAL_WEB_RESEARCH_TIMEOUT_SECONDS"],
    ) as response:
        return json.loads(response.read().decode("utf-8"))


def _parse_sources(payload: object) -> list[ElectoralWebSource]:
    if not isinstance(payload, dict) or not isinstance(payload.get("results"), list):
        raise ValueError("Resposta invalida do pesquisador web.")
    maximum = max(1, int(current_app.config["ELECTORAL_WEB_RESEARCH_MAX_RESULTS"]))
    sources = []
    seen_urls = set()
    for row in payload["results"]:
        if not isinstance(row, dict):
            continue
        title = " ".join(str(row.get("title") or "").split())[:240]
        url = str(row.get("url") or "").strip()
        snippet = " ".join(str(row.get("content") or "").split())[:1200]
        if not title or len(snippet) < 30 or not _public_http_url(url):
            continue
        if url in seen_urls or has_prompt_injection(f"{title} {snippet}"):
            continue
        seen_urls.add(url)
        sources.append(
            ElectoralWebSource(
                title=title,
                url=url,
                snippet=snippet,
                engine=str(row.get("engine") or "").strip() or None,
                published_at=str(row.get("publishedDate") or "").strip() or None,
            )
        )
        if len(sources) >= maximum:
            break
    return sources


def _public_http_url(value: str) -> bool:
    parsed = urllib.parse.urlsplit(value)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        return False
    hostname = parsed.hostname.casefold()
    if hostname in {"localhost", "localhost.localdomain"} or hostname.endswith(".local"):
        return False
    try:
        address = ipaddress.ip_address(hostname)
    except ValueError:
        return True
    return not (
        address.is_private
        or address.is_loopback
        or address.is_link_local
        or address.is_reserved
        or address.is_multicast
    )
