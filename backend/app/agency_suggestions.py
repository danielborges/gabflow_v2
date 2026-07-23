from sqlalchemy import select

from app.extensions import db
from app.models import ExternalAgency, Tenant

MUNICIPAL_AGENCIES = [
    "Prefeitura Municipal de {city}",
    "Câmara Municipal de {city}",
    "Secretaria Municipal de Governo",
    "Secretaria Municipal de Administração",
    "Secretaria Municipal de Fazenda",
    "Secretaria Municipal de Saúde",
    "Secretaria Municipal de Educação",
    "Secretaria Municipal de Assistência Social",
    "Secretaria Municipal de Obras",
    "Secretaria Municipal de Serviços Urbanos",
    "Secretaria Municipal de Mobilidade Urbana e Transporte",
    "Secretaria Municipal de Meio Ambiente",
    "Secretaria Municipal de Planejamento Urbano",
    "Secretaria Municipal de Habitação",
    "Secretaria Municipal de Cultura",
    "Secretaria Municipal de Esporte e Lazer",
    "Secretaria Municipal de Desenvolvimento Econômico",
    "Defesa Civil Municipal",
    "Guarda Municipal",
    "Procon Municipal",
    "Conselho Tutelar",
]

STATE_AGENCIES = [
    "Governo do Estado de {state}",
    "Assembleia Legislativa de {state}",
    "Secretaria de Estado de Governo",
    "Secretaria de Estado de Administração",
    "Secretaria de Estado de Fazenda",
    "Secretaria de Estado de Saúde",
    "Secretaria de Estado de Educação",
    "Secretaria de Estado de Assistência Social",
    "Secretaria de Estado de Infraestrutura",
    "Secretaria de Estado de Transportes e Mobilidade",
    "Secretaria de Estado de Meio Ambiente",
    "Secretaria de Estado de Segurança Pública",
    "Defesa Civil Estadual",
    "Polícia Militar",
    "Polícia Civil",
    "Corpo de Bombeiros Militar",
    "Procon Estadual",
    "Ministério Público Estadual",
    "Defensoria Pública Estadual",
]


def suggested_agencies(tenant: Tenant) -> list[dict]:
    if tenant.chamber_type == "ASSEMBLEIA_LEGISLATIVA":
        state = tenant.jurisdiction_state or tenant.jurisdiction_name or "UF"
        names = [template.format(state=state) for template in STATE_AGENCIES]
    else:
        city = tenant.jurisdiction_city or tenant.jurisdiction_name or "Município"
        names = [template.format(city=city) for template in MUNICIPAL_AGENCIES]
    return [
        {
            "nome": name,
            "responsavel": "A definir",
            "telefone": None,
            "emailContato": None,
            "origem": "Sugestão GabFlow",
        }
        for name in names
    ]


def reload_suggested_agencies(tenant: Tenant) -> tuple[list[ExternalAgency], list[dict]]:
    suggestions = suggested_agencies(tenant)
    existing = {
        item.name.casefold(): item
        for item in db.session.execute(
            select(ExternalAgency).where(ExternalAgency.tenant_id == tenant.id)
        ).scalars()
    }
    changed = False
    for suggestion in suggestions:
        item = existing.get(suggestion["nome"].casefold())
        if item:
            if not item.active:
                item.active = True
                changed = True
            continue
        db.session.add(
            ExternalAgency(
                tenant_id=tenant.id,
                name=suggestion["nome"],
                contact_email=suggestion["emailContato"],
                responsible=suggestion["responsavel"],
                phone=suggestion["telefone"],
                source=suggestion["origem"],
            )
        )
        changed = True
    if changed:
        db.session.flush()
    items = db.session.execute(
        select(ExternalAgency)
        .where(ExternalAgency.tenant_id == tenant.id)
        .order_by(ExternalAgency.name)
    ).scalars().all()
    return items, suggestions
