import click
from flask import Flask, current_app
from sqlalchemy import select

from app.agency_suggestions import reload_suggested_agencies
from app.auth.security import hash_password
from app.default_categories import ensure_default_request_categories
from app.extensions import db
from app.models import (
    ExternalAgency,
    LegislativeDraft,
    RequestCategory,
    Role,
    ServiceRequest,
    Tenant,
    Territory,
    User,
)
from app.outbox.worker import run_worker
from app.rag.operational_memory import (
    LEGISLATIVE_DRAFT_ENTITY,
    SERVICE_REQUEST_ENTITY,
    enqueue_operational_memory,
)
from app.tenant_context import tenant_context
from app.territory_suggestions import reload_suggested_territories


def register_commands(app: Flask) -> None:
    @app.cli.command("worker")
    @click.option("--once", is_flag=True, help="Processa um lote e encerra.")
    def worker(once: bool) -> None:
        result = run_worker(current_app._get_current_object(), once=once)
        click.echo(
            "Outbox processado: "
            f"{result.succeeded} sucesso(s), "
            f"{result.retried} reagendado(s), "
            f"{result.failed} falha(s) definitiva(s)."
        )

    @app.cli.command("sync-operational-memory")
    @click.option("--tenant", help="Slug do tenant. Sem a opção, sincroniza todos.")
    @click.option("--batch-size", default=500, type=click.IntRange(10, 5000))
    def sync_operational_memory(tenant: str | None, batch_size: int) -> None:
        statement = select(Tenant)
        if tenant:
            statement = statement.where(Tenant.slug == tenant)
        tenants = list(db.session.scalars(statement.order_by(Tenant.slug)))
        if tenant and not tenants:
            raise click.ClickException("Tenant não encontrado.")
        total = 0
        for item in tenants:
            with tenant_context(item.id):
                for model, entity_type in (
                    (ServiceRequest, SERVICE_REQUEST_ENTITY),
                    (LegislativeDraft, LEGISLATIVE_DRAFT_ENTITY),
                ):
                    cursor = None
                    while True:
                        statement = (
                            select(model.id)
                            .where(model.tenant_id == item.id)
                            .order_by(model.id)
                            .limit(batch_size)
                        )
                        if cursor is not None:
                            statement = statement.where(model.id > cursor)
                        identifiers = list(db.session.scalars(statement))
                        if not identifiers:
                            break
                        for entity_id in identifiers:
                            enqueue_operational_memory(
                                item.id, entity_type, entity_id
                            )
                        db.session.commit()
                        total += len(identifiers)
                        cursor = identifiers[-1]
        click.echo(
            f"{total} entidade(s) operacional(is) enfileirada(s) "
            f"em {len(tenants)} tenant(s)."
        )

    @app.cli.command("seed")
    @click.option("--tenant", default="gabinete-demo")
    @click.option("--email", default="admin@gabflow.local")
    @click.option("--password", envvar="SEED_ADMIN_PASSWORD", required=True)
    def seed(tenant: str, email: str, password: str) -> None:
        existing = db.session.execute(
            select(Tenant).where(Tenant.slug == tenant)
        ).scalar_one_or_none()
        if existing is None:
            existing = Tenant(name="Gabinete Demonstração", slug=tenant)
            db.session.add(existing)
            db.session.flush()
        if existing.jurisdiction_name is None:
            existing.chamber_type = "CAMARA_MUNICIPAL"
            existing.jurisdiction_name = "Juiz de Fora/MG"
            existing.jurisdiction_city = "Juiz de Fora"
            existing.jurisdiction_state = "MG"
            existing.jurisdiction_ibge_code = "3136702"
            existing.jurisdiction_center_latitude = -21.7619
            existing.jurisdiction_center_longitude = -43.3496
            existing.jurisdiction_bounds = {
                "minLatitude": -21.92,
                "maxLatitude": -21.58,
                "minLongitude": -43.58,
                "maxLongitude": -43.17,
            }

        user = db.session.execute(
            select(User).where(User.tenant_id == existing.id, User.email == email.lower())
        ).scalar_one_or_none()
        if user is None:
            db.session.add(
                User(
                    tenant_id=existing.id,
                    name="Administrador",
                    email=email.lower(),
                    password_hash=hash_password(password),
                    role=Role.ADMIN,
                )
            )

        has_categories = db.session.execute(
            select(RequestCategory.id).where(RequestCategory.tenant_id == existing.id).limit(1)
        ).scalar_one_or_none()
        if has_categories is None:
            db.session.add_all(
                [
                    RequestCategory(
                        tenant_id=existing.id,
                        name="Iluminação pública",
                        sla_hours=72,
                    ),
                    RequestCategory(
                        tenant_id=existing.id,
                        name="Saúde",
                        sla_hours=24,
                    ),
                    RequestCategory(
                        tenant_id=existing.id,
                        name="Mobilidade urbana",
                        sla_hours=96,
                    ),
                ]
            )
        ensure_default_request_categories(existing.id)
        has_territories = db.session.execute(
            select(Territory.id).where(Territory.tenant_id == existing.id).limit(1)
        ).scalar_one_or_none()
        if has_territories is None:
            db.session.add_all(
                [
                    Territory(tenant_id=existing.id, name="Centro"),
                    Territory(tenant_id=existing.id, name="Zona Norte"),
                    Territory(tenant_id=existing.id, name="Zona Sul"),
                ]
            )
        reload_suggested_territories(existing)
        has_agencies = db.session.execute(
            select(ExternalAgency.id).where(ExternalAgency.tenant_id == existing.id).limit(1)
        ).scalar_one_or_none()
        if has_agencies is None:
            db.session.add_all(
                [
                    ExternalAgency(tenant_id=existing.id, name="Secretaria de Obras"),
                    ExternalAgency(tenant_id=existing.id, name="Secretaria de Saúde"),
                    ExternalAgency(tenant_id=existing.id, name="Secretaria de Mobilidade"),
                ]
            )
        reload_suggested_agencies(existing)
        db.session.commit()
        click.echo(f"Seed do tenant {tenant} aplicado para {email}.")

    @app.cli.command("seed-platform-admin")
    @click.option("--email", default="platform@gabflow.local")
    @click.option("--password", envvar="SEED_PLATFORM_ADMIN_PASSWORD", required=True)
    def seed_platform_admin(email: str, password: str) -> None:
        normalized_email = email.lower()
        user = db.session.execute(
            select(User).where(User.tenant_id.is_(None), User.email == normalized_email)
        ).scalar_one_or_none()
        if user is None:
            db.session.add(
                User(
                    tenant_id=None,
                    name="Administrador Geral",
                    email=normalized_email,
                    password_hash=hash_password(password),
                    role=Role.PLATFORM_ADMIN,
                )
            )
        else:
            user.role = Role.PLATFORM_ADMIN
            user.password_hash = hash_password(password)
        db.session.commit()
        click.echo(f"Administrador Geral do GabFlow aplicado para {normalized_email}.")

    @app.cli.command("seed-global-knowledge-admin")
    @click.option("--email", default="knowledge@gabflow.local")
    @click.option("--password", envvar="SEED_GLOBAL_KNOWLEDGE_ADMIN_PASSWORD", required=True)
    def seed_global_knowledge_admin(email: str, password: str) -> None:
        normalized_email = email.lower()
        user = db.session.execute(
            select(User).where(User.tenant_id.is_(None), User.email == normalized_email)
        ).scalar_one_or_none()
        if user is None:
            db.session.add(
                User(
                    tenant_id=None,
                    name="Curador Global de Conhecimento",
                    email=normalized_email,
                    password_hash=hash_password(password),
                    role=Role.GLOBAL_KNOWLEDGE_ADMIN,
                )
            )
        else:
            user.role = Role.GLOBAL_KNOWLEDGE_ADMIN
            user.password_hash = hash_password(password)
        db.session.commit()
        click.echo(f"Curador global do GabFlow aplicado para {normalized_email}.")
