from datetime import date, timedelta
from pathlib import Path

import click
from flask import Flask, current_app
from sqlalchemy import select

from app.agency_suggestions import reload_suggested_agencies
from app.auth.security import hash_password
from app.default_categories import ensure_default_request_categories
from app.electoral.commitments import add_evidence, create_commitment, update_commitment
from app.electoral.coverage import (
    SUPPORTED_ELECTION_CYCLES,
    coverage_catalog,
    official_archive_url,
)
from app.electoral.geography import (
    IBGE_GEOMETRY_SOURCE,
    IBGE_LOCALITIES_SOURCE,
    download_official_json,
    import_geometry_geojson,
)
from app.electoral.identity import (
    official_candidate_registry_url,
    sync_candidate_registry_archive,
)
from app.electoral.ingestion import (
    ElectoralImportError,
    download_official_archive,
    import_dataset_archive,
    publish_validated_dataset,
)
from app.electoral.territorial_ingestion import (
    import_territorial_detail,
    official_location_archive_url,
    official_section_archive_url,
)
from app.extensions import db
from app.models import (
    ElectoralDatasetVersion,
    ElectoralPublicCommitment,
    ExternalAgency,
    LegislativeDraft,
    Mandate,
    RequestCategory,
    Role,
    ServiceRequest,
    Tenant,
    Territory,
    User,
    UserStatus,
)
from app.outbox.worker import run_worker
from app.rag.operational_memory import (
    LEGISLATIVE_DRAFT_ENTITY,
    SERVICE_REQUEST_ENTITY,
    enqueue_operational_memory,
)
from app.tenant_context import tenant_context
from app.territory_suggestions import reload_suggested_territories


def _sync_electoral_identities(year: int, uf: str) -> None:
    source_url = official_candidate_registry_url(year)
    path = None
    try:
        path = download_official_archive(source_url)
        sync, idempotent = sync_candidate_registry_archive(
            path,
            source_url=source_url,
            election_year=year,
            uf=uf,
        )
        click.echo(
            f"Identidades {year}: candidaturas vinculaveis={sync.matched_candidacies}, "
            f"idempotente={str(idempotent).lower()}."
        )
    except ElectoralImportError as error:
        current_app.logger.warning(
            "Falha ao sincronizar cadastro oficial de candidaturas year=%s uf=%s: %s",
            year,
            uf,
            error,
        )
        click.echo(
            f"Aviso: resultados publicados, mas a sincronizacao de identidades falhou: {error}",
            err=True,
        )
    finally:
        if path is not None:
            path.unlink(missing_ok=True)


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
    @click.option("--sync-identities/--no-sync-identities", default=True)
    def electoral_import(
        source_url: str,
        archive_file: str | None,
        year: int,
        scope: str,
        uf: str,
        office_code: str | None,
        expected_total_votes: int | None,
        publish: bool,
        sync_identities: bool,
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
        if publish and sync_identities:
            _sync_electoral_identities(year, uf)

    @app.cli.command("electoral-sync-candidate-registry")
    @click.option("--source-url", help="URL oficial do cadastro TSE; derivada do ano por padrao.")
    @click.option("--file", "archive_file", type=click.Path(exists=True, dir_okay=False))
    @click.option("--year", type=click.IntRange(2012, 2100), required=True)
    @click.option("--uf", type=str)
    def electoral_sync_candidate_registry(
        source_url: str | None,
        archive_file: str | None,
        year: int,
        uf: str | None,
    ) -> None:
        source_url = source_url or official_candidate_registry_url(year)
        downloaded = archive_file is None
        path = download_official_archive(source_url) if downloaded else Path(archive_file)
        try:
            sync, idempotent = sync_candidate_registry_archive(
                path,
                source_url=source_url,
                election_year=year,
                uf=uf,
            )
        except ElectoralImportError as error:
            raise click.ClickException(str(error)) from error
        finally:
            if downloaded:
                path.unlink(missing_ok=True)
        click.echo(
            f"Cadastro TSE {sync.id}: ano={sync.election_year}, linhas={sync.row_count}, "
            f"candidaturas vinculaveis={sync.matched_candidacies}, "
            f"idempotente={str(idempotent).lower()}."
        )

    @app.cli.command("electoral-publish")
    @click.option("--dataset-id", type=click.UUID, required=True)
    def electoral_publish(dataset_id) -> None:
        try:
            dataset = publish_validated_dataset(dataset_id)
        except ElectoralImportError as error:
            raise click.ClickException(str(error)) from error
        click.echo(f"Dataset {dataset.id} publicado com qualidade {dataset.quality_score}.")

    @app.cli.command("electoral-import-territories")
    @click.option("--dataset-id", type=click.UUID, required=True)
    @click.option("--section-file", type=click.Path(exists=True, dir_okay=False))
    @click.option("--location-file", type=click.Path(exists=True, dir_okay=False))
    def electoral_import_territories(
        dataset_id,
        section_file: str | None,
        location_file: str | None,
    ) -> None:
        dataset = db.session.get(ElectoralDatasetVersion, dataset_id)
        if dataset is None:
            raise click.ClickException("Dataset eleitoral nao encontrado.")
        section_url = official_section_archive_url(dataset.election_year, dataset.uf)
        location_url = official_location_archive_url(dataset.election_year)
        downloaded_section = section_file is None
        downloaded_location = location_file is None
        section_path = (
            download_official_archive(section_url) if downloaded_section else Path(section_file)
        )
        location_path = (
            download_official_archive(location_url)
            if downloaded_location
            else Path(location_file)
        )
        try:
            version, idempotent = import_territorial_detail(
                dataset.id,
                section_path,
                location_path,
                section_source_url=section_url,
                location_source_url=location_url,
            )
        except ElectoralImportError as error:
            raise click.ClickException(str(error)) from error
        finally:
            if downloaded_section:
                section_path.unlink(missing_ok=True)
            if downloaded_location:
                location_path.unlink(missing_ok=True)
        click.echo(
            f"Cobertura territorial {version.id}: status={version.status.value}, "
            f"linhas={version.row_count}, votos={version.total_votes}, "
            f"qualidade={version.quality_score}, idempotente={str(idempotent).lower()}."
        )

    @app.cli.command("electoral-backfill")
    @click.option("--uf", type=str, required=True, help="UF cuja serie historica sera coberta.")
    @click.option(
        "--year",
        "years",
        multiple=True,
        type=click.Choice([str(item[0]) for item in SUPPORTED_ELECTION_CYCLES]),
        help="Ano a importar. Pode ser repetido; sem a opcao importa toda a matriz.",
    )
    @click.option("--publish/--no-publish", default=True)
    @click.option("--dry-run", is_flag=True, help="Exibe o plano sem baixar arquivos.")
    @click.option("--force", is_flag=True, help="Revalida inclusive ciclos ja completos.")
    def electoral_backfill(
        uf: str,
        years: tuple[str, ...],
        publish: bool,
        dry_run: bool,
        force: bool,
    ) -> None:
        uf = uf.strip().upper()
        if len(uf) != 2 or not uf.isalpha():
            raise click.ClickException("UF deve possuir duas letras.")
        selected = {int(item) for item in years} if years else None
        cycles = [
            (year, scope)
            for year, scope in SUPPORTED_ELECTION_CYCLES
            if selected is None or year in selected
        ]
        summary = coverage_catalog(uf=uf)["resumo"]["jurisdicoes"][0]
        status_by_year = {item["ano"]: item["status"] for item in summary["ciclos"]}
        plan = [
            (year, scope, official_archive_url(year), status_by_year[year])
            for year, scope in cycles
            if force or status_by_year[year] != "COMPLETE"
        ]
        for year, scope, source_url, status in plan:
            click.echo(f"{year} {scope} {uf}: {status} -> {source_url}")
        if dry_run:
            click.echo(f"Plano: {len(plan)} ciclo(s) a importar.")
            return
        for year, scope, source_url, _status in plan:
            stored_dataset = db.session.scalar(
                select(ElectoralDatasetVersion)
                .where(
                    ElectoralDatasetVersion.election_year == year,
                    ElectoralDatasetVersion.election_scope == scope,
                    ElectoralDatasetVersion.uf == uf,
                    ElectoralDatasetVersion.office_code.is_(None),
                )
                .order_by(ElectoralDatasetVersion.downloaded_at.desc())
            )
            stored_path = Path(stored_dataset.raw_storage_path) if stored_dataset else None
            uses_stored_archive = stored_path is not None and stored_path.is_file()
            path = stored_path if uses_stored_archive else download_official_archive(source_url)
            try:
                dataset, idempotent = import_dataset_archive(
                    path,
                    source_url=source_url,
                    election_year=year,
                    election_scope=scope,
                    uf=uf,
                    office_code=None,
                    publish=publish,
                )
            except ElectoralImportError as error:
                suffix = f" Dataset: {error.dataset_id}." if error.dataset_id else ""
                raise click.ClickException(f"Falha no ciclo {year}: {error}{suffix}") from error
            finally:
                if not uses_stored_archive:
                    path.unlink(missing_ok=True)
            click.echo(
                f"{year}: dataset={dataset.id}, status={dataset.status.value}, "
                f"linhas={dataset.row_count}, idempotente={str(idempotent).lower()}."
            )
            if publish:
                _sync_electoral_identities(year, uf)

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

    @app.cli.command("seed-electoral-commitments-demo")
    @click.option("--tenant", default="gabinete-demo", show_default=True)
    def seed_electoral_commitments_demo(tenant: str) -> None:
        """Cria compromissos territoriais inequivocamente sintéticos para homologação."""
        tenant_item = db.session.execute(
            select(Tenant).where(Tenant.slug == tenant)
        ).scalar_one_or_none()
        if tenant_item is None:
            raise click.ClickException("Tenant não encontrado.")

        with tenant_context(tenant_item.id):
            mandate = db.session.execute(
                select(Mandate).where(
                    Mandate.tenant_id == tenant_item.id,
                    Mandate.status == "ACTIVE",
                )
            ).scalar_one_or_none()
            if mandate is None:
                raise click.ClickException("Mandato ativo não encontrado.")

            representative = db.session.get(User, mandate.representative_user_id)
            if representative is None or representative.status != UserStatus.ACTIVE:
                raise click.ClickException("Parlamentar ativo não encontrado.")

            territories = {
                item.name: item
                for item in db.session.scalars(
                    select(Territory).where(
                        Territory.tenant_id == tenant_item.id,
                        Territory.active.is_(True),
                    )
                )
            }
            required_territories = {"Centro", "Zona Norte", "Zona Sul", "Zona Leste"}
            missing = sorted(required_territories - territories.keys())
            if missing:
                raise click.ClickException(
                    "Territórios necessários não encontrados: " + ", ".join(missing)
                )

            active_users = list(
                db.session.scalars(
                    select(User)
                    .where(
                        User.tenant_id == tenant_item.id,
                        User.status == UserStatus.ACTIVE,
                    )
                    .order_by(User.role.desc(), User.name)
                )
            )
            staff = [item for item in active_users if item.role == Role.STAFF]
            responsibles = staff or [representative]
            today = date.today()
            fixtures = [
                {
                    "title": "[DEMO] Revitalização participativa da Praça Central",
                    "description": (
                        "Cenário sintético para testar compromisso concluído, evidência "
                        "pública e marcador cartográfico. Não representa ação real do mandato."
                    ),
                    "territory": "Centro",
                    "responsible": representative,
                    "due_on": today - timedelta(days=45),
                    "status": "COMPLETED",
                    "progress": 100,
                    "location": (
                        "Parque Halfeld — ponto público demonstrativo",
                        -21.7595,
                        -43.3488,
                    ),
                    "evidence": (
                        "[DEMO] Registro fotográfico de homologação",
                        "https://example.org/gabflow-demo/praca-central",
                    ),
                },
                {
                    "title": "[DEMO] Rota segura para acesso a serviços públicos",
                    "description": (
                        "Cenário sintético em andamento para validar atualização de progresso, "
                        "responsável e sincronização tabela–mapa."
                    ),
                    "territory": "Zona Norte",
                    "responsible": responsibles[0],
                    "due_on": today + timedelta(days=35),
                    "status": "IN_PROGRESS",
                    "progress": 60,
                    "location": ("Praça pública — referência demonstrativa", -21.7005, -43.4370),
                    "evidence": (
                        "[DEMO] Relatório parcial de vistoria",
                        "https://example.org/gabflow-demo/rota-segura",
                    ),
                },
                {
                    "title": "[DEMO] Painel comunitário de acompanhamento de obras",
                    "description": (
                        "Cenário sintético planejado para testar prazo futuro e compromisso "
                        "ainda sem evidência."
                    ),
                    "territory": "Zona Sul",
                    "responsible": responsibles[min(1, len(responsibles) - 1)],
                    "due_on": today + timedelta(days=90),
                    "status": "PLANNED",
                    "progress": 0,
                    "location": ("Campus público — referência demonstrativa", -21.7766, -43.3722),
                },
                {
                    "title": "[DEMO] Mutirão de escuta sobre mobilidade de bairro",
                    "description": (
                        "Cenário sintético propositalmente vencido para validar alertas e o "
                        "estado derivado de atraso."
                    ),
                    "territory": "Zona Leste",
                    "responsible": responsibles[min(2, len(responsibles) - 1)],
                    "due_on": today - timedelta(days=15),
                    "status": "IN_PROGRESS",
                    "progress": 35,
                    "location": (
                        "Equipamento público — referência demonstrativa",
                        -21.7500,
                        -43.3250,
                    ),
                },
                {
                    "title": "[DEMO] Agenda itinerante de prestação de contas",
                    "description": (
                        "Cenário sintético sem coordenadas para validar a contagem de itens não "
                        "mapeados e sua permanência na tabela."
                    ),
                    "territory": "Centro",
                    "responsible": representative,
                    "due_on": today + timedelta(days=20),
                    "status": "IN_PROGRESS",
                    "progress": 20,
                },
                {
                    "title": "[DEMO] Oficina territorial substituída",
                    "description": (
                        "Cenário sintético cancelado para testar filtros e exclusão do mapa "
                        "operacional sem apagar o histórico."
                    ),
                    "territory": "Zona Norte",
                    "responsible": representative,
                    "due_on": today + timedelta(days=10),
                    "status": "CANCELLED",
                    "progress": 0,
                },
            ]

            existing_titles = set(
                db.session.scalars(
                    select(ElectoralPublicCommitment.title).where(
                        ElectoralPublicCommitment.tenant_id == tenant_item.id,
                        ElectoralPublicCommitment.mandate_id == mandate.id,
                        ElectoralPublicCommitment.title.in_(
                            [fixture["title"] for fixture in fixtures]
                        ),
                    )
                )
            )
            created = 0
            for fixture in fixtures:
                if fixture["title"] in existing_titles:
                    continue
                payload = {
                    "title": fixture["title"],
                    "description": fixture["description"],
                    "territory_id": str(territories[fixture["territory"]].id),
                    "responsible_user_id": str(fixture["responsible"].id),
                    "due_on": fixture["due_on"].isoformat(),
                }
                if location := fixture.get("location"):
                    payload.update(
                        {
                            "public_location_name": location[0],
                            "latitude": location[1],
                            "longitude": location[2],
                            "location_is_public": True,
                        }
                    )
                commitment = create_commitment(
                    tenant_item.id,
                    mandate.id,
                    representative.id,
                    payload,
                )
                update_commitment(
                    commitment,
                    representative.id,
                    {
                        "status": fixture["status"],
                        "progress": fixture["progress"],
                    },
                )
                if evidence := fixture.get("evidence"):
                    add_evidence(
                        commitment,
                        representative.id,
                        {
                            "title": evidence[0],
                            "description": (
                                "Evidência exclusivamente sintética para testes funcionais."
                            ),
                            "public_url": evidence[1],
                            "evidence_date": today.isoformat(),
                        },
                    )
                created += 1
            db.session.commit()

        click.echo(
            f"Carga DEMO aplicada em {tenant}: {created} criado(s), "
            f"{len(fixtures) - created} já existente(s)."
        )

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
