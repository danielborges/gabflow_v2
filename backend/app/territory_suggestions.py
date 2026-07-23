import json
import gzip
import urllib.error
import urllib.request

from sqlalchemy import select

from app.extensions import db
from app.models import Tenant, Territory

IBGE_LOCALIDADES_URL = "https://servicodados.ibge.gov.br/api/v1/localidades"
DEFAULT_MUNICIPAL_TERRITORIES = ["Centro", "Zona Norte", "Zona Sul", "Zona Leste", "Zona Oeste", "Zona Rural"]


def suggested_territory_names(tenant: Tenant) -> list[str]:
    if tenant.chamber_type == "ASSEMBLEIA_LEGISLATIVA" and tenant.jurisdiction_state:
        rows = _fetch_ibge_json(f"{IBGE_LOCALIDADES_URL}/estados/{tenant.jurisdiction_state}/municipios")
        return _unique_sorted(row.get("nome") for row in rows)
    if tenant.jurisdiction_ibge_code:
        rows = _fetch_ibge_json(
            f"{IBGE_LOCALIDADES_URL}/municipios/{tenant.jurisdiction_ibge_code}/distritos"
        )
        names = _unique_sorted(row.get("nome") for row in rows)
        if names:
            return names
    if tenant.jurisdiction_city:
        return _unique_sorted([tenant.jurisdiction_city, *DEFAULT_MUNICIPAL_TERRITORIES])
    return DEFAULT_MUNICIPAL_TERRITORIES


def reload_suggested_territories(tenant: Tenant) -> tuple[list[Territory], list[str]]:
    suggestions = suggested_territory_names(tenant)
    existing = {
        item.name.casefold(): item
        for item in db.session.execute(
            select(Territory).where(Territory.tenant_id == tenant.id)
        ).scalars()
    }
    changed = False
    for name in suggestions:
        item = existing.get(name.casefold())
        if item:
            if not item.active:
                item.active = True
                changed = True
            continue
        db.session.add(Territory(tenant_id=tenant.id, name=name))
        changed = True
    if changed:
        db.session.flush()
    items = db.session.execute(
        select(Territory).where(Territory.tenant_id == tenant.id).order_by(Territory.name)
    ).scalars().all()
    return items, suggestions


def _fetch_ibge_json(url: str) -> list[dict]:
    try:
        request = urllib.request.Request(url, headers={"User-Agent": "GabFlow/1.0"})
        with urllib.request.urlopen(request, timeout=12) as response:
            body = response.read()
            if response.headers.get("Content-Encoding") == "gzip" or body.startswith(b"\x1f\x8b"):
                body = gzip.decompress(body)
            payload = json.loads(body.decode("utf-8"))
            return payload if isinstance(payload, list) else []
    except (OSError, TimeoutError, urllib.error.URLError, json.JSONDecodeError, UnicodeDecodeError):
        return []


def _unique_sorted(values) -> list[str]:
    names = {str(value).strip() for value in values if str(value or "").strip()}
    return sorted(names, key=lambda value: value.casefold())
