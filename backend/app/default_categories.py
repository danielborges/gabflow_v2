from sqlalchemy import select

from app.extensions import db
from app.models import RequestCategory

DEFAULT_REQUEST_CATEGORIES = [
    ("Defesa civil e risco iminente", 4),
    ("Saúde - urgência assistencial", 8),
    ("Assistencia social emergencial", 24),
    ("Seguranca publica", 24),
    ("Defesa animal", 24),
    ("Saúde", 24),
    ("Pessoa idosa", 48),
    ("Pessoa com deficiencia", 48),
    ("Direitos humanos", 48),
    ("Coleta de lixo", 48),
    ("Saneamento básico", 48),
    ("Abastecimento de agua", 48),
    ("Educação", 72),
    ("Iluminação pública", 72),
    ("Limpeza urbana", 72),
    ("Transporte publico", 72),
    ("Meio ambiente", 72),
    ("Cidadania e documentos", 72),
    ("Esporte e lazer", 72),
    ("Cultura", 72),
    ("Trabalho, emprego e renda", 72),
    ("Mobilidade urbana", 96),
    ("Trânsito e sinalização", 96),
    ("Acessibilidade urbana", 96),
    ("Regularização fundiária", 96),
    ("Obras e manutenção viária", 120),
    ("Tapa-buraco e pavimentação", 120),
    ("Habitação", 120),
    ("Urbanismo e fiscalização", 120),
    ("Empreendedorismo e comercio local", 120),
    ("Agricultura e zona rural", 120),
    ("Tributos e taxas municipais", 120),
    ("Atendimento legislativo", 168),
    ("Solicitação de informação pública", 168),
    ("Projetos, indicações e requerimentos", 240),
]


def ensure_default_request_categories(tenant_id) -> bool:
    existing_names = set(
        db.session.execute(
            select(RequestCategory.name).where(
                RequestCategory.tenant_id == tenant_id,
                RequestCategory.parent_id.is_(None),
            )
        ).scalars()
    )
    missing = [
        RequestCategory(tenant_id=tenant_id, name=name, sla_hours=sla_hours)
        for name, sla_hours in DEFAULT_REQUEST_CATEGORIES
        if name not in existing_names
    ]
    if not missing:
        return False
    db.session.add_all(missing)
    return True
