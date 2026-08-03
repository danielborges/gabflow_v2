import click
from flask import Flask, current_app
from sqlalchemy import select

from app.agency_suggestions import reload_suggested_agencies
from app.auth.security import hash_password
from app.default_categories import ensure_default_request_categories
from app.electoral.geography import (
    IBGE_GEOMETRY_SOURCE,
    IBGE_LOCALITIES_SOURCE,
    download_official_json,
    import_geometry_geojson,
)
from app.electoral.ingestion import (
    ElectoralImportError,
    download_official_archive,
    import_dataset_archive,
    publish_validated_dataset,
)
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
    @app.cli.command("electoral-import-geometry")
    @click.option("--source-url", default=IBGE_GEOMETRY_SOURCE, show_default=True)
    @click.option("--localities-url", default=IBGE_LOCALITIES_SOURCE, show_default=True)
    @click.option("--year", type=click.IntRange(2000, 2100), default=2024, show_default=True)
    @click.option("--uf", default="MG", show_default=True)
    @click.option(
        "--quality",
        type=click.Choice(["minima", "intermediaria", "maxima"]),
        default="intermediaria",
        show_default=True,
    )
    def electoral_import_geometry(
        source_url: str,
        localities_url: str,
        year: int,
        uf: str,
        quality: str,
    ) -> None:
        geometry_payload = download_official_json(source_url)
        localities_payload = download_official_json(localities_url)
        version, repeated, manifest = import_geometry_geojson(
            geometry_payload,
            localities_payload,
            source_url=source_url,
            reference_year=year,
            uf=uf,
            quality=quality,
        )
        click.echo(
            f"Geometria {version.id}: status={version.status}, feicoes={version.feature_count}, "
            f"crosswalk={manifest.get('crosswalkMatched')}, idempotente={str(repeated).lower()}."
        )

    @app.cli.command("electoral-import")
    @click.option("--source-url", required=True, help="URL oficial do recurso TSE.")
    @click.option("--file", "archive_file", type=click.Path(exists=True, dir_okay=False))
    @click.option("--year", type=click.IntRange(2012, 2100), required=True)
    @click.option("--scope", type=click.Choice(["municipal", "general"]), required=True)
    @click.option("--uf", type=str, required=True)
    @click.option("--office-code", type=str)
    @click.option("--expected-total-votes", type=click.IntRange(0))
    @click.option("--publish/--no-publish", default=True)
    def electoral_import(
        source_url: str,
        archive_file: str | None,
        year: int,
        scope: str,
        uf: str,
        office_code: str | None,
        expected_total_votes: int | None,
        publish: bool,
    ) -> None:
        downloaded = archive_file is None
        path = download_official_archive(source_url) if downloaded else archive_file
        try:
            dataset, idempotent = import_dataset_archive(
                path,
                source_url=source_url,
                election_year=year,
                election_scope=scope,
                uf=uf,
                office_code=office_code,
                expected_total_votes=expected_total_votes,
                publish=publish,
            )
        except ElectoralImportError as error:
            suffix = f" Dataset: {error.dataset_id}." if error.dataset_id else ""
            raise click.ClickException(f"{error}{suffix}") from error
        finally:
            if downloaded:
                path.unlink(missing_ok=True)
        click.echo(
            f"Dataset {dataset.id}: status={dataset.status.value}, "
            f"linhas={dataset.row_count}, votos={dataset.total_votes}, "
            f"qualidade={dataset.quality_score}, idempotente={str(idempotent).lower()}."
        )

    @app.cli.command("electoral-publish")
    @click.option("--dataset-id", type=click.UUID, required=True)
    def electoral_publish(dataset_id) -> None:
        try:
            dataset = publish_validated_dataset(dataset_id)
        except ElectoralImportError as error:
            raise click.ClickException(str(error)) from error
        click.echo(f"Dataset {dataset.id} publicado com qualidade {dataset.quality_score}.")

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
                            enqueue_operational_memory(item.id, entity_type, entity_id)
                        db.session.commit()
                        total += len(identifiers)
                        cursor = identifiers[-1]
        click.echo(
            f"{total} entidade(s) operacional(is) enfileirada(s) em {len(tenants)} tenant(s)."
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
