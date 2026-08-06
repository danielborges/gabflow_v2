import uuid
from unicodedata import combining, normalize

from sqlalchemy import select

from app.extensions import db
from app.models import Tenant, Territory
from app.territory_geometry import geometry_area, geometry_contains


class CitizenAddressError(ValueError):
    pass


def resolve_address(tenant_id: uuid.UUID, value: dict) -> dict:
    if not isinstance(value, dict):
        raise CitizenAddressError("Endereço deve ser um objeto estruturado.")
    formatted = str(value.get("endereco") or value.get("enderecoFormatado") or "").strip()
    if not formatted:
        raise CitizenAddressError("Informe o endereço.")
    latitude = _coordinate(value.get("latitude"), -90, 90, "latitude")
    longitude = _coordinate(value.get("longitude"), -180, 180, "longitude")
    neighborhood = str(value.get("bairro") or "").strip() or None
    tenant = db.session.get(Tenant, tenant_id)
    outside = _outside_bounds(latitude, longitude, tenant.jurisdiction_bounds if tenant else None)
    territory, method = _matching_territory(
        tenant_id, neighborhood, latitude=latitude, longitude=longitude
    )
    if outside:
        status = "FORA_DA_JURISDICAO"
        territory = None
        method = None
    elif territory:
        status = "RESOLVIDO"
    elif neighborhood:
        status = "TERRITORIO_NAO_ENCONTRADO"
    else:
        status = "BAIRRO_NAO_IDENTIFICADO"
    return {
        "endereco": formatted[:500],
        "logradouro": str(value.get("logradouro") or "").strip()[:180] or None,
        "numero": str(value.get("numero") or "").strip()[:30] or None,
        "complemento": str(value.get("complemento") or "").strip()[:120] or None,
        "cep": str(value.get("cep") or "").strip()[:12] or None,
        "bairro": neighborhood[:120] if neighborhood else None,
        "cidade": str(value.get("cidade") or "").strip()[:120] or None,
        "uf": str(value.get("uf") or "").strip()[:2].upper() or None,
        "latitude": latitude,
        "longitude": longitude,
        "placeId": str(value.get("placeId") or "").strip()[:255] or None,
        "territorioId": str(territory.id) if territory else None,
        "territorio": territory.name if territory else None,
        "statusResolucao": status,
        "metodoResolucao": method,
    }


def _coordinate(value, minimum: float, maximum: float, label: str) -> float | None:
    if value in (None, ""):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError) as error:
        raise CitizenAddressError(f"{label.capitalize()} inválida.") from error
    if not minimum <= number <= maximum:
        raise CitizenAddressError(f"{label.capitalize()} inválida.")
    return number


def _outside_bounds(latitude, longitude, bounds) -> bool:
    if latitude is None or longitude is None or not isinstance(bounds, dict):
        return False
    try:
        return not (
            float(bounds["minLatitude"]) <= latitude <= float(bounds["maxLatitude"])
            and float(bounds["minLongitude"]) <= longitude <= float(bounds["maxLongitude"])
        )
    except (KeyError, TypeError, ValueError):
        return False


def _matching_territory(
    tenant_id: uuid.UUID,
    neighborhood: str | None,
    *,
    latitude: float | None,
    longitude: float | None,
):
    territories = list(
        db.session.execute(
            select(Territory).where(Territory.tenant_id == tenant_id, Territory.active.is_(True))
        ).scalars()
    )
    if latitude is not None and longitude is not None:
        containing = [
            territory
            for territory in territories
            if geometry_contains(territory.geometry, latitude, longitude)
        ]
        if containing:
            return min(containing, key=lambda item: geometry_area(item.geometry)), "POLIGONO"
    if neighborhood:
        expected = _key(neighborhood)
        for territory in territories:
            names = [territory.name, *(territory.aliases or [])]
            if expected in {_key(name) for name in names}:
                method = "NOME" if expected == _key(territory.name) else "ALIAS"
                return territory, method
    return None, None


def _key(value: str) -> str:
    text = " ".join(value.lower().split())
    return "".join(char for char in normalize("NFKD", text) if not combining(char))
