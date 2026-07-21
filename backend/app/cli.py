import click
from flask import Flask, current_app
from sqlalchemy import select

from app.auth.security import hash_password
from app.extensions import db
from app.models import ExternalAgency, RequestCategory, Role, Tenant, Territory, User
from app.outbox.worker import run_worker


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
