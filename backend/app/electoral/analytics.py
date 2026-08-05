import uuid

from sqlalchemy import String, cast, func, literal, or_, select, tuple_
from sqlalchemy.orm import aliased

from app.electoral.text import normalize_search
from app.extensions import db
from app.models import (
    ElectoralCandidacy,
    ElectoralCandidate,
    ElectoralDatasetStatus,
    ElectoralDatasetVersion,
    ElectoralElection,
    ElectoralGeometryFeature,
    ElectoralGeometryVersion,
    ElectoralIdentityReview,
    ElectoralOffice,
    ElectoralParty,
    ElectoralResult,
    ElectoralSectionResult,
    ElectoralTerritorialDatasetVersion,
    ElectoralTerritorialUnit,
    ElectoralTerritory,
    ElectoralTerritoryCrosswalk,
)

AVAILABLE_LEVELS = (
    "municipality",
    "electoral_zone",
    "neighborhood",
    "polling_place",
    "section",
)
BASE_LEVELS = ("municipality", "electoral_zone")
COMPARISON_MIN_CANDIDATES = 2
COMPARISON_MAX_CANDIDATES = 5


class TerritorialLevelUnavailable(ValueError):
    def __init__(self, available_levels: list[str]):
        super().__init__("Nivel territorial indisponivel para este dataset.")
        self.available_levels = available_levels


def search_candidates(
    election_id: uuid.UUID,
    query: str,
    *,
    party: str | None = None,
    office: str | None = None,
    page: int = 1,
    per_page: int = 20,
) -> dict:
    normalized_query = normalize_search(query)
    filters = [
        ElectoralElection.id == election_id,
        ElectoralDatasetVersion.status == ElectoralDatasetStatus.PUBLISHED,
    ]
    if normalized_query:
        filters.append(
            or_(
                ElectoralCandidate.normalized_name.contains(normalized_query),
                ElectoralCandidacy.ballot_number.contains(normalized_query),
                func.lower(ElectoralParty.acronym).contains(normalized_query),
                func.lower(ElectoralParty.name).contains(normalized_query),
            )
        )
    if party:
        normalized_party = normalize_search(party)
        filters.append(
            or_(
                func.lower(ElectoralParty.acronym) == normalized_party,
                func.lower(ElectoralParty.name).contains(normalized_party),
                cast(ElectoralParty.number, String) == normalized_party,
            )
        )
    if office:
        normalized_office = normalize_search(office)
        filters.append(
            or_(
                ElectoralOffice.code == normalized_office,
                func.lower(ElectoralOffice.name).contains(normalized_office),
            )
        )

    statement = (
        select(
            ElectoralCandidate,
            ElectoralCandidacy,
            ElectoralParty,
            ElectoralOffice,
            ElectoralElection,
            ElectoralDatasetVersion,
        )
        .join(ElectoralCandidacy, ElectoralCandidacy.candidate_id == ElectoralCandidate.id)
        .join(ElectoralParty, ElectoralParty.id == ElectoralCandidacy.party_id)
        .join(ElectoralOffice, ElectoralOffice.id == ElectoralCandidacy.office_id)
        .join(ElectoralElection, ElectoralElection.id == ElectoralCandidacy.election_id)
        .join(
            ElectoralDatasetVersion,
            ElectoralDatasetVersion.id == ElectoralCandidacy.dataset_version_id,
        )
        .where(*filters)
    )
    total = db.session.scalar(select(func.count()).select_from(statement.subquery())) or 0
    rows = db.session.execute(
        statement.order_by(ElectoralCandidate.ballot_name, ElectoralCandidacy.ballot_number)
        .offset((page - 1) * per_page)
        .limit(per_page)
    ).all()
    return {
        "items": [
            candidate_data(candidate, candidacy, party_row, office_row, election, dataset)
            for candidate, candidacy, party_row, office_row, election, dataset in rows
        ],
        "page": page,
        "perPage": per_page,
        "total": total,
    }


def candidate_results(
    candidate_id: uuid.UUID,
    election_id: uuid.UUID,
    level: str,
    *,
    municipality_code: str | None = None,
    parent_territory_id: uuid.UUID | None = None,
    page: int = 1,
    per_page: int = 50,
    sort: str = "votes",
    order: str = "desc",
) -> dict | None:
    context = db.session.execute(
        select(
            ElectoralCandidate,
            ElectoralCandidacy,
            ElectoralParty,
            ElectoralOffice,
            ElectoralElection,
            ElectoralDatasetVersion,
        )
        .join(ElectoralCandidacy, ElectoralCandidacy.candidate_id == ElectoralCandidate.id)
        .join(ElectoralParty, ElectoralParty.id == ElectoralCandidacy.party_id)
        .join(ElectoralOffice, ElectoralOffice.id == ElectoralCandidacy.office_id)
        .join(ElectoralElection, ElectoralElection.id == ElectoralCandidacy.election_id)
        .join(
            ElectoralDatasetVersion,
            ElectoralDatasetVersion.id == ElectoralCandidacy.dataset_version_id,
        )
        .where(
            ElectoralCandidate.id == candidate_id,
            ElectoralElection.id == election_id,
            ElectoralDatasetVersion.status == ElectoralDatasetStatus.PUBLISHED,
        )
    ).one_or_none()
    if context is None:
        return None
    candidate, candidacy, party, office, election, dataset = context

    territorial_version = db.session.scalar(
        select(ElectoralTerritorialDatasetVersion)
        .where(
            ElectoralTerritorialDatasetVersion.dataset_version_id == dataset.id,
            ElectoralTerritorialDatasetVersion.status == ElectoralDatasetStatus.PUBLISHED,
        )
        .order_by(ElectoralTerritorialDatasetVersion.published_at.desc())
    )
    available_levels = list(BASE_LEVELS)
    if territorial_version is not None:
        available_levels.extend(("neighborhood", "polling_place", "section"))
    if level not in available_levels:
        raise TerritorialLevelUnavailable(available_levels)

    if parent_territory_id and not municipality_code:
        municipality_code = _municipality_code_for_id(dataset.id, parent_territory_id)
        if municipality_code is None:
            return None

    aggregated = (
        _territorial_aggregation(
            dataset.id,
            election.id,
            candidacy.office_id,
            level,
            municipality_code,
        )
        if level in BASE_LEVELS
        else _detailed_territorial_aggregation(
            territorial_version.id,
            election.id,
            candidacy.office_id,
            candidacy.id,
            level,
            municipality_code,
        )
    )
    ranked = select(
        *aggregated.c,
        func.sum(aggregated.c.votes)
        .over(partition_by=aggregated.c.territory_key)
        .label("denominator_value"),
        func.rank()
        .over(
            partition_by=aggregated.c.territory_key,
            order_by=aggregated.c.votes.desc(),
        )
        .label("candidate_rank"),
    ).subquery()
    selected = select(ranked).where(ranked.c.candidacy_id == candidacy.id)
    total = db.session.scalar(select(func.count()).select_from(selected.subquery())) or 0
    order_column = {
        "name": ranked.c.territory_name,
        "rank": ranked.c.candidate_rank,
        "share": ranked.c.votes / func.nullif(ranked.c.denominator_value, 0),
        "votes": ranked.c.votes,
    }.get(sort, ranked.c.votes)
    order_by = order_column.asc() if order == "asc" else order_column.desc()
    rows = db.session.execute(
        selected.order_by(order_by, ranked.c.territory_name)
        .offset((page - 1) * per_page)
        .limit(per_page)
    ).mappings()
    warning = (
        "A totalizacao externa do recorte estadual nao foi informada."
        if not dataset.validation_manifest.get("totalizationChecked")
        else None
    )
    items = []
    for row in rows:
        denominator = int(row["denominator_value"] or 0)
        territory_id = (
            str(row["territory_id"])
            if row["territory_id"]
            else str(virtual_territory_id(dataset.id, level, row["territory_key"]))
        )
        mapping_warning = None
        if row["derived"]:
            mapping_warning = (
                "Bairro derivado do cadastro oficial do local de votacao; "
                "nao representa limite geografico oficial."
            )
        items.append(
            {
                "territory_id": territory_id,
                "territory_code": row["territory_key"],
                "territory_name": row["territory_name"],
                "level": level,
                "votes": int(row["votes"]),
                "share": round(int(row["votes"]) / denominator, 8) if denominator else 0,
                "rank": int(row["candidate_rank"]),
                "denominator_value": denominator,
                "quality_warning": mapping_warning or warning,
                "derived": bool(row["derived"]),
                "mapping_type": row["mapping_type"],
            }
        )
    candidate_total = (
        db.session.scalar(
            select(func.sum(ElectoralResult.votes)).where(
                ElectoralResult.dataset_version_id == dataset.id,
                ElectoralResult.election_id == election.id,
                ElectoralResult.candidacy_id == candidacy.id,
            )
        )
        or 0
    )
    return {
        "candidate": candidate_data(candidate, candidacy, party, office, election, dataset),
        "source": dataset.source_url,
        "source_hash": dataset.source_hash,
        "dataset_version": str(dataset.id),
        "quality_score": dataset.quality_score,
        "available_levels": available_levels,
        "level": level,
        "territorial_source": (
            {
                "version": str(territorial_version.id),
                "section_source": territorial_version.section_source_url,
                "location_source": territorial_version.location_source_url,
                "parser_version": territorial_version.parser_version,
            }
            if territorial_version is not None
            else None
        ),
        "candidate_total_votes": int(candidate_total),
        "denominator": {
            "type": "valid_nominal_votes",
            "label": "Votos nominais válidos do mesmo cargo e território",
            "formula": "votos_do_candidato / votos_nominais_validos_do_cargo_no_territorio",
        },
        "items": items,
        "page": page,
        "perPage": per_page,
        "total": total,
    }


def compare_candidates(
    candidate_ids: list[uuid.UUID],
    election_id: uuid.UUID,
    level: str,
    *,
    municipality_code: str | None = None,
) -> tuple[dict | None, str | None]:
    """Return aligned territorial series using one election, office and denominator."""
    contexts = list(
        db.session.execute(
            select(
                ElectoralCandidate,
                ElectoralCandidacy,
                ElectoralParty,
                ElectoralOffice,
                ElectoralElection,
                ElectoralDatasetVersion,
            )
            .join(ElectoralCandidacy, ElectoralCandidacy.candidate_id == ElectoralCandidate.id)
            .join(ElectoralParty, ElectoralParty.id == ElectoralCandidacy.party_id)
            .join(ElectoralOffice, ElectoralOffice.id == ElectoralCandidacy.office_id)
            .join(ElectoralElection, ElectoralElection.id == ElectoralCandidacy.election_id)
            .join(
                ElectoralDatasetVersion,
                ElectoralDatasetVersion.id == ElectoralCandidacy.dataset_version_id,
            )
            .where(
                ElectoralCandidate.id.in_(candidate_ids),
                ElectoralElection.id == election_id,
                ElectoralDatasetVersion.status == ElectoralDatasetStatus.PUBLISHED,
            )
        ).all()
    )
    if len(contexts) != len(candidate_ids):
        return None, "Uma ou mais candidaturas nao pertencem a eleicao publicada selecionada."
    if len({context[1].office_id for context in contexts}) != 1:
        return None, "As candidaturas precisam disputar o mesmo cargo."
    if len({context[1].dataset_version_id for context in contexts}) != 1:
        return None, "As candidaturas precisam usar a mesma versao publicada do dataset."

    by_candidate = {}
    for candidate_id in candidate_ids:
        try:
            result = candidate_results(
                candidate_id,
                election_id,
                level,
                municipality_code=municipality_code,
                page=1,
                per_page=100,
                sort="name",
                order="asc",
            )
        except TerritorialLevelUnavailable as error:
            return None, f"{error} Disponiveis: {', '.join(error.available_levels)}."
        if result is None:
            return None, "Nao foi possivel calcular uma das candidaturas."
        by_candidate[str(candidate_id)] = result

    territories: dict[str, dict] = {}
    for candidate_id, result in by_candidate.items():
        for item in result["items"]:
            territory = territories.setdefault(
                item["territory_code"],
                {
                    "territory_id": item["territory_id"],
                    "territory_code": item["territory_code"],
                    "territory_name": item["territory_name"],
                    "level": level,
                    "denominator_value": item["denominator_value"],
                    "derived": item["derived"],
                    "mapping_type": item["mapping_type"],
                    "series": [],
                },
            )
            if territory["denominator_value"] != item["denominator_value"]:
                return None, "Os denominadores territoriais nao sao comparaveis."
            territory["series"].append(
                {
                    "candidate_id": candidate_id,
                    "votes": item["votes"],
                    "share": item["share"],
                    "rank": item["rank"],
                }
            )

    return {
        "candidates": [
            by_candidate[str(candidate_id)]["candidate"] for candidate_id in candidate_ids
        ],
        "dataset_version": next(iter(by_candidate.values()))["dataset_version"],
        "source": next(iter(by_candidate.values()))["source"],
        "source_hash": next(iter(by_candidate.values()))["source_hash"],
        "level": level,
        "denominator": next(iter(by_candidate.values()))["denominator"],
        "comparability": {"compatible": True, "warnings": []},
        "items": sorted(territories.values(), key=lambda item: item["territory_name"]),
    }, None


def candidate_history(
    candidate_id: uuid.UUID,
    *,
    municipality_code: str | None = None,
    tenant_id: uuid.UUID | None = None,
    user_id: uuid.UUID | None = None,
) -> dict | None:
    """Find versioned candidacies by exact normalized full name.

    The match is intentionally labelled as unreviewed until the identity review table
    planned for the next Increment 3 slice is available.
    """
    origin = db.session.execute(
        select(ElectoralCandidate).where(ElectoralCandidate.id == candidate_id)
    ).scalar_one_or_none()
    if origin is None:
        return None
    candidate_ids = set(
        db.session.scalars(
            select(ElectoralCandidate.id).where(
                ElectoralCandidate.normalized_name == origin.normalized_name
            )
        )
    )
    reviewed_pairs = []
    if tenant_id and user_id:
        reviewed_pairs = list(
            db.session.execute(
                select(ElectoralIdentityReview).where(
                    ElectoralIdentityReview.tenant_id == tenant_id,
                    ElectoralIdentityReview.user_id == user_id,
                    or_(
                        ElectoralIdentityReview.subject_candidate_id == candidate_id,
                        ElectoralIdentityReview.linked_candidate_id == candidate_id,
                    ),
                )
            ).scalars()
        )
        for review in reviewed_pairs:
            other_id = (
                review.linked_candidate_id
                if review.subject_candidate_id == candidate_id
                else review.subject_candidate_id
            )
            if review.decision == "CONFIRMED":
                candidate_ids.add(other_id)
            elif review.decision == "REJECTED":
                candidate_ids.discard(other_id)

    rows = db.session.execute(
        select(
            ElectoralCandidate,
            ElectoralCandidacy,
            ElectoralParty,
            ElectoralOffice,
            ElectoralElection,
            ElectoralDatasetVersion,
        )
        .join(ElectoralCandidacy, ElectoralCandidacy.candidate_id == ElectoralCandidate.id)
        .join(ElectoralParty, ElectoralParty.id == ElectoralCandidacy.party_id)
        .join(ElectoralOffice, ElectoralOffice.id == ElectoralCandidacy.office_id)
        .join(ElectoralElection, ElectoralElection.id == ElectoralCandidacy.election_id)
        .join(
            ElectoralDatasetVersion,
            ElectoralDatasetVersion.id == ElectoralCandidacy.dataset_version_id,
        )
        .where(
            ElectoralCandidate.id.in_(candidate_ids),
            ElectoralDatasetVersion.status == ElectoralDatasetStatus.PUBLISHED,
        )
        .order_by(ElectoralElection.year)
    ).all()
    items = []
    for candidate, candidacy, party, office, election, dataset in rows:
        result = candidate_results(
            candidate.id,
            election.id,
            "municipality",
            municipality_code=municipality_code,
            page=1,
            per_page=100,
            sort="votes",
            order="desc",
        )
        territorial = result["items"][0] if result and result["items"] else None
        items.append(
            {
                "candidate": candidate_data(candidate, candidacy, party, office, election, dataset),
                "territory": territorial,
                "candidate_total_votes": result["candidate_total_votes"] if result else 0,
            }
        )
    warnings = []
    if len({item["candidate"]["party"]["acronym"] for item in items}) > 1:
        warnings.append({"code": "PARTY_CHANGED", "message": "O partido mudou entre as eleicoes."})
    if len({item["candidate"]["office"]["code"] for item in items}) > 1:
        warnings.append({"code": "OFFICE_CHANGED", "message": "O cargo mudou entre as eleicoes."})
    if len({item["candidate"]["election"]["year"] for item in items}) > 1:
        warnings.append(
            {
                "code": "BOUNDARY_REVIEW_REQUIRED",
                "message": (
                    "A equivalencia dos limites territoriais entre anos ainda nao foi revisada."
                ),
            }
        )
    reviewed_candidates = {
        review.linked_candidate_id
        if review.subject_candidate_id == candidate_id
        else review.subject_candidate_id
        for review in reviewed_pairs
        if review.decision == "CONFIRMED"
    }
    related_candidates = {item["candidate"]["id"] for item in items} - {str(candidate_id)}
    fully_reviewed = bool(related_candidates) and related_candidates <= {
        str(item) for item in reviewed_candidates
    }
    return {
        "identity": {
            "method": "human_review" if fully_reviewed else "exact_normalized_full_name",
            "reviewed": fully_reviewed,
            "warning": (
                None
                if fully_reviewed
                else "Vinculo automatico por nome completo; confirme homonimos antes de decidir."
            ),
        },
        "items": items,
        "warnings": warnings,
    }


def candidate_map(
    candidate_id: uuid.UUID,
    election_id: uuid.UUID,
    level: str,
    *,
    municipality_code: str | None = None,
    tenant_id: uuid.UUID | None = None,
    user_id: uuid.UUID | None = None,
) -> dict | None:
    if level != "municipality":
        return {
            "geometry_available": False,
            "level": level,
            "warning": (
                "Não há polígonos oficiais de zonas eleitorais publicados no catálogo; "
                "use a tabela e o ranking."
            ),
            "type": "FeatureCollection",
            "features": [],
        }
    result = candidate_results(
        candidate_id,
        election_id,
        level,
        municipality_code=municipality_code,
        page=1,
        per_page=2000,
        sort="name",
        order="asc",
    )
    if result is None:
        return None
    election = result["candidate"]["election"]
    version = (
        db.session.execute(
            select(ElectoralGeometryVersion)
            .where(
                ElectoralGeometryVersion.uf == election["uf"],
                ElectoralGeometryVersion.level == "municipality",
                ElectoralGeometryVersion.status == "PUBLISHED",
            )
            .order_by(ElectoralGeometryVersion.reference_year.desc())
        )
        .scalars()
        .first()
    )
    if version is None:
        return {
            "geometry_available": False,
            "level": level,
            "warning": "A malha municipal oficial ainda não foi publicada para esta UF.",
            "type": "FeatureCollection",
            "features": [],
        }
    current_by_code = {item["territory_code"]: item for item in result["items"]}
    previous_by_code = {}
    history = candidate_history(
        candidate_id,
        municipality_code=municipality_code,
        tenant_id=tenant_id,
        user_id=user_id,
    )
    previous_items = [
        item
        for item in (history or {}).get("items", [])
        if item["candidate"]["election"]["year"] < election["year"]
    ]
    if previous_items:
        previous = max(previous_items, key=lambda item: item["candidate"]["election"]["year"])
        previous_result = candidate_results(
            uuid.UUID(previous["candidate"]["id"]),
            uuid.UUID(previous["candidate"]["election"]["id"]),
            "municipality",
            municipality_code=municipality_code,
            page=1,
            per_page=2000,
            sort="name",
            order="asc",
        )
        previous_by_code = {
            item["territory_code"]: item for item in (previous_result or {}).get("items", [])
        }

    rows = db.session.execute(
        select(ElectoralTerritoryCrosswalk, ElectoralGeometryFeature)
        .join(
            ElectoralGeometryFeature,
            ElectoralGeometryFeature.id == ElectoralTerritoryCrosswalk.geometry_feature_id,
        )
        .where(
            ElectoralTerritoryCrosswalk.geometry_version_id == version.id,
            ElectoralTerritoryCrosswalk.electoral_code.in_(current_by_code),
        )
    ).all()
    features = []
    for crosswalk, geometry in rows:
        current = current_by_code[crosswalk.electoral_code]
        previous = previous_by_code.get(crosswalk.electoral_code)
        features.append(
            {
                "type": "Feature",
                "id": str(geometry.id),
                "geometry": geometry.geometry_geojson,
                "bbox": geometry.bbox,
                "properties": {
                    "territory_id": current["territory_id"],
                    "territory_code": current["territory_code"],
                    "territory_name": current["territory_name"],
                    "official_code": geometry.official_code,
                    "votes": current["votes"],
                    "share": current["share"],
                    "rank": current["rank"],
                    "variation": current["votes"] - previous["votes"] if previous else None,
                    "crosswalk_reviewed": crosswalk.reviewed,
                    "geometry_official": not geometry.derived,
                },
            }
        )
    warnings = []
    if version.reference_year != election["year"]:
        warnings.append(
            f"A malha oficial de {version.reference_year} é usada para a eleição "
            f"de {election['year']}."
        )
    if any(not feature["properties"]["crosswalk_reviewed"] for feature in features):
        warnings.append("Há vínculos TSE–IBGE automáticos ainda não revisados.")
    return {
        "geometry_available": bool(features),
        "level": level,
        "geometry_version": str(version.id),
        "reference_year": version.reference_year,
        "source": version.source_url,
        "source_hash": version.source_hash,
        "official": True,
        "warnings": warnings,
        "type": "FeatureCollection",
        "features": features,
    }


def candidate_data(candidate, candidacy, party, office, election, dataset) -> dict:
    return {
        "id": str(candidate.id),
        "candidacy_id": str(candidacy.id),
        "external_id": candidate.external_id,
        "full_name": candidate.full_name,
        "ballot_name": candidate.ballot_name,
        "number": candidacy.ballot_number,
        "status": candidacy.status,
        "party": {
            "number": party.number,
            "acronym": party.acronym,
            "name": party.name,
        },
        "office": {"id": str(office.id), "code": office.code, "name": office.name},
        "election": {
            "id": str(election.id),
            "name": election.name,
            "year": election.year,
            "round": election.round,
            "uf": election.uf,
        },
        "dataset_version": str(dataset.id),
        "source": dataset.source_url,
    }


def municipality_territory_id(dataset_id: uuid.UUID, municipality_code: str) -> uuid.UUID:
    return uuid.uuid5(
        uuid.NAMESPACE_URL,
        f"gabflow:electoral:{dataset_id}:municipality:{municipality_code}",
    )


def virtual_territory_id(dataset_id: uuid.UUID, level: str, territory_key: str) -> uuid.UUID:
    return uuid.uuid5(
        uuid.NAMESPACE_URL,
        f"gabflow:electoral:{dataset_id}:{level}:{territory_key}",
    )


def _municipality_code_for_id(dataset_id: uuid.UUID, territory_id: uuid.UUID) -> str | None:
    codes = db.session.execute(
        select(ElectoralTerritory.municipality_code)
        .where(ElectoralTerritory.dataset_version_id == dataset_id)
        .distinct()
    ).scalars()
    return next(
        (code for code in codes if municipality_territory_id(dataset_id, code) == territory_id),
        None,
    )


def _territorial_aggregation(dataset_id, election_id, office_id, level, municipality_code):
    filters = [
        ElectoralResult.dataset_version_id == dataset_id,
        ElectoralResult.election_id == election_id,
        ElectoralCandidacy.office_id == office_id,
    ]
    if municipality_code:
        filters.append(ElectoralTerritory.municipality_code == municipality_code)
    if level == "municipality":
        territory_key = ElectoralTerritory.municipality_code
        territory_name = ElectoralTerritory.municipality_name
        territory_id = cast(literal(None), String)
        group_by = [territory_key, territory_name, ElectoralResult.candidacy_id]
    else:
        territory_key = (
            ElectoralTerritory.municipality_code
            + literal(":")
            + cast(ElectoralTerritory.zone, String)
        )
        territory_name = (
            ElectoralTerritory.municipality_name
            + literal(" · Zona ")
            + cast(ElectoralTerritory.zone, String)
        )
        territory_id = ElectoralTerritory.id
        group_by = [
            ElectoralTerritory.id,
            ElectoralTerritory.municipality_code,
            ElectoralTerritory.municipality_name,
            ElectoralTerritory.zone,
            ElectoralResult.candidacy_id,
        ]
    return (
        select(
            territory_key.label("territory_key"),
            territory_name.label("territory_name"),
            territory_id.label("territory_id"),
            ElectoralResult.candidacy_id.label("candidacy_id"),
            func.sum(ElectoralResult.votes).label("votes"),
            literal(False).label("derived"),
            literal("OFFICIAL").label("mapping_type"),
        )
        .join(ElectoralTerritory, ElectoralTerritory.id == ElectoralResult.territory_id)
        .join(ElectoralCandidacy, ElectoralCandidacy.id == ElectoralResult.candidacy_id)
        .where(*filters)
        .group_by(*group_by)
        .subquery()
    )


def _detailed_territorial_aggregation(
    territorial_version_id,
    election_id,
    office_id,
    target_candidacy_id,
    level,
    municipality_code,
):
    filters = [
        ElectoralSectionResult.territorial_dataset_version_id == territorial_version_id,
        ElectoralCandidacy.election_id == election_id,
        ElectoralCandidacy.office_id == office_id,
    ]
    if municipality_code:
        filters.append(ElectoralTerritorialUnit.municipality_code == municipality_code)

    target_unit = aliased(ElectoralTerritorialUnit)
    target_rows = (
        select(target_unit)
        .join(
            ElectoralSectionResult,
            ElectoralSectionResult.territory_id == target_unit.id,
        )
        .where(
            ElectoralSectionResult.territorial_dataset_version_id
            == territorial_version_id,
            ElectoralSectionResult.candidacy_id == target_candidacy_id,
        )
    )
    if municipality_code:
        target_rows = target_rows.where(target_unit.municipality_code == municipality_code)

    if level == "neighborhood":
        neighborhood = func.coalesce(ElectoralTerritorialUnit.neighborhood, "Nao informado")
        territory_key = (
            ElectoralTerritorialUnit.municipality_code
            + literal(":bairro:")
            + neighborhood
        )
        territory_name = (
            ElectoralTerritorialUnit.municipality_name
            + literal(" · Bairro ")
            + neighborhood
        )
        territory_id = cast(literal(None), String)
        derived = literal(True)
        mapping_type = literal("DERIVED")
        group_by = [
            ElectoralTerritorialUnit.municipality_code,
            ElectoralTerritorialUnit.municipality_name,
            neighborhood,
            ElectoralSectionResult.candidacy_id,
        ]
        target_keys = target_rows.with_only_columns(
            target_unit.municipality_code,
            func.coalesce(target_unit.neighborhood, "Nao informado"),
        )
        filters.append(
            tuple_(
                ElectoralTerritorialUnit.municipality_code,
                func.coalesce(ElectoralTerritorialUnit.neighborhood, "Nao informado"),
            ).in_(target_keys)
        )
    elif level == "polling_place":
        territory_key = (
            ElectoralTerritorialUnit.municipality_code
            + literal(":")
            + cast(ElectoralTerritorialUnit.zone, String)
            + literal(":")
            + cast(ElectoralTerritorialUnit.polling_place_number, String)
        )
        territory_name = (
            ElectoralTerritorialUnit.polling_place_name
            + literal(" · Local ")
            + cast(ElectoralTerritorialUnit.polling_place_number, String)
        )
        territory_id = cast(literal(None), String)
        derived = literal(False)
        mapping_type = literal("OFFICIAL")
        group_by = [
            ElectoralTerritorialUnit.municipality_code,
            ElectoralTerritorialUnit.zone,
            ElectoralTerritorialUnit.polling_place_number,
            ElectoralTerritorialUnit.polling_place_name,
            ElectoralSectionResult.candidacy_id,
        ]
        target_keys = target_rows.with_only_columns(
            target_unit.municipality_code,
            target_unit.zone,
            target_unit.polling_place_number,
        )
        filters.append(
            tuple_(
                ElectoralTerritorialUnit.municipality_code,
                ElectoralTerritorialUnit.zone,
                ElectoralTerritorialUnit.polling_place_number,
            ).in_(target_keys)
        )
    else:
        territory_key = (
            ElectoralTerritorialUnit.municipality_code
            + literal(":")
            + cast(ElectoralTerritorialUnit.zone, String)
            + literal(":")
            + cast(ElectoralTerritorialUnit.section, String)
        )
        territory_name = (
            ElectoralTerritorialUnit.polling_place_name
            + literal(" · Seção ")
            + cast(ElectoralTerritorialUnit.section, String)
        )
        territory_id = ElectoralTerritorialUnit.id
        derived = literal(False)
        mapping_type = ElectoralTerritorialUnit.mapping_type
        group_by = [
            ElectoralTerritorialUnit.id,
            ElectoralTerritorialUnit.municipality_code,
            ElectoralTerritorialUnit.zone,
            ElectoralTerritorialUnit.section,
            ElectoralTerritorialUnit.polling_place_name,
            ElectoralTerritorialUnit.mapping_type,
            ElectoralSectionResult.candidacy_id,
        ]
        target_keys = target_rows.with_only_columns(target_unit.id)
        filters.append(ElectoralTerritorialUnit.id.in_(target_keys))
    return (
        select(
            territory_key.label("territory_key"),
            territory_name.label("territory_name"),
            territory_id.label("territory_id"),
            ElectoralSectionResult.candidacy_id.label("candidacy_id"),
            func.sum(ElectoralSectionResult.votes).label("votes"),
            derived.label("derived"),
            mapping_type.label("mapping_type"),
        )
        .join(
            ElectoralTerritorialUnit,
            ElectoralTerritorialUnit.id == ElectoralSectionResult.territory_id,
        )
        .join(ElectoralCandidacy, ElectoralCandidacy.id == ElectoralSectionResult.candidacy_id)
        .where(*filters)
        .group_by(*group_by)
        .subquery()
    )
