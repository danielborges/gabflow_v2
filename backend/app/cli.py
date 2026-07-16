import click
from flask import Flask
from sqlalchemy import select

from app.auth.security import hash_password
from app.extensions import db
from app.models import ExternalAgency, RequestCategory, Role, Tenant, Territory, User


def register_commands(app: Flask) -> None:
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
        db.session.commit()
        click.echo(f"Seed do tenant {tenant} aplicado para {email}.")
