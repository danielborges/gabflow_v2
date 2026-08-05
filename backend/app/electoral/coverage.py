from collections import defaultdict

from sqlalchemy import select

from app.extensions import db
from app.models import (
    ElectoralCandidacy,
    ElectoralDatasetStatus,
    ElectoralDatasetVersion,
    ElectoralOffice,
    ElectoralTerritorialDatasetVersion,
    ElectoralTerritory,
)

SUPPORTED_ELECTION_CYCLES = (
    (2012, "municipal"),
    (2014, "general"),
    (2016, "municipal"),
    (2018, "general"),
    (2020, "municipal"),
    (2022, "general"),
    (2024, "municipal"),
)
REQUIRED_OFFICES = {
    "municipal": {"11", "13"},
    "general": {"1", "3", "5", "6", "7"},
}
OFFICIAL_ARCHIVE_TEMPLATE = (
    "https://cdn.tse.jus.br/estatistica/sead/odsele/"
    "votacao_candidato_munzona/votacao_candidato_munzona_{year}.zip"
)


def official_archive_url(year: int) -> str:
    if year not in {item[0] for item in SUPPORTED_ELECTION_CYCLES}:
        raise ValueError("Ano fora da matriz de cobertura eleitoral suportada.")
    return OFFICIAL_ARCHIVE_TEMPLATE.format(year=year)


def validate_election_cycle(year: int, scope: str) -> None:
    if (year, scope) not in SUPPORTED_ELECTION_CYCLES:
        raise ValueError("Ano e escopo nao correspondem a um ciclo eleitoral suportado.")


def coverage_catalog(*, uf: str | None = None) -> dict:
    filters = [ElectoralDatasetVersion.status == ElectoralDatasetStatus.PUBLISHED]
    if uf:
        filters.append(ElectoralDatasetVersion.uf == uf)
    datasets = list(
        db.session.scalars(
            select(ElectoralDatasetVersion)
            .where(*filters)
            .order_by(ElectoralDatasetVersion.election_year.desc(), ElectoralDatasetVersion.uf)
        )
    )
    dataset_ids = [item.id for item in datasets]
    offices_by_dataset: dict = defaultdict(set)
    levels_by_dataset: dict = defaultdict(set)
    for item in datasets:
        manifest = item.validation_manifest or {}
        offices_by_dataset[item.id].update(manifest.get("officeCodes") or [])
        levels_by_dataset[item.id].update(
            str(level).lower() for level in (manifest.get("granularities") or [])
        )
    if dataset_ids:
        for dataset_id, manifest in db.session.execute(
            select(
                ElectoralTerritorialDatasetVersion.dataset_version_id,
                ElectoralTerritorialDatasetVersion.validation_manifest,
            ).where(
                ElectoralTerritorialDatasetVersion.dataset_version_id.in_(dataset_ids),
                ElectoralTerritorialDatasetVersion.status
                == ElectoralDatasetStatus.PUBLISHED,
            )
        ):
            levels_by_dataset[dataset_id].update(
                str(level).lower() for level in ((manifest or {}).get("granularities") or [])
            )
    missing_office_metadata = [item for item in dataset_ids if not offices_by_dataset[item]]
    missing_level_metadata = [item for item in dataset_ids if not levels_by_dataset[item]]
    if missing_office_metadata:
        for dataset_id, office_code in db.session.execute(
            select(ElectoralCandidacy.dataset_version_id, ElectoralOffice.code)
            .join(ElectoralOffice, ElectoralOffice.id == ElectoralCandidacy.office_id)
            .where(ElectoralCandidacy.dataset_version_id.in_(missing_office_metadata))
            .distinct()
        ):
            offices_by_dataset[dataset_id].add(office_code)
    if missing_level_metadata:
        for dataset_id, level in db.session.execute(
            select(ElectoralTerritory.dataset_version_id, ElectoralTerritory.level)
            .where(ElectoralTerritory.dataset_version_id.in_(missing_level_metadata))
            .distinct()
        ):
            levels_by_dataset[dataset_id].add(level.value)

    content = []
    by_jurisdiction: dict[str, dict[tuple[int, str], dict]] = defaultdict(
        lambda: defaultdict(lambda: {"datasets": [], "offices": set(), "levels": set()})
    )
    for item in datasets:
        offices = sorted(offices_by_dataset[item.id])
        source_levels = levels_by_dataset[item.id]
        levels = sorted(source_levels | ({"municipality"} if source_levels else set()))
        content.append(
            {
                "ano": item.election_year,
                "escopo": item.election_scope,
                "uf": item.uf,
                "cargoCodigo": item.office_code,
                "cargos": offices,
                "granularidades": levels,
                "linhas": item.row_count,
                "votos": item.total_votes,
                "qualidade": item.quality_score,
                "datasetVersionId": str(item.id),
            }
        )
        cycle = by_jurisdiction[item.uf][(item.election_year, item.election_scope)]
        cycle["datasets"].append(str(item.id))
        cycle["offices"].update(offices)
        cycle["levels"].update(levels)

    jurisdictions = sorted(by_jurisdiction)
    if uf and uf not in jurisdictions:
        jurisdictions.append(uf)
    summaries = [_jurisdiction_summary(item, by_jurisdiction[item]) for item in jurisdictions]
    return {
        "content": content,
        "total": len(content),
        "resumo": {
            "primeiroAno": SUPPORTED_ELECTION_CYCLES[0][0],
            "ultimoAno": SUPPORTED_ELECTION_CYCLES[-1][0],
            "ciclosEsperados": len(SUPPORTED_ELECTION_CYCLES),
            "jurisdicoes": summaries,
        },
    }


def _jurisdiction_summary(uf: str, available: dict) -> dict:
    cycles = []
    complete = 0
    partial = 0
    for year, scope in SUPPORTED_ELECTION_CYCLES:
        current = available.get((year, scope), {"datasets": [], "offices": set(), "levels": set()})
        required = REQUIRED_OFFICES[scope]
        offices = current["offices"]
        if required.issubset(offices):
            status = "COMPLETE"
            complete += 1
        elif current["datasets"]:
            status = "PARTIAL"
            partial += 1
        else:
            status = "MISSING"
        cycles.append(
            {
                "ano": year,
                "escopo": scope,
                "status": status,
                "cargosEsperados": sorted(required, key=int),
                "cargosDisponiveis": sorted(offices, key=int),
                "cargosAusentes": sorted(required - offices, key=int),
                "granularidades": sorted(current["levels"]),
                "datasetVersionIds": current["datasets"],
                "fonteOficial": official_archive_url(year),
            }
        )
    expected = len(SUPPORTED_ELECTION_CYCLES)
    return {
        "uf": uf,
        "status": "COMPLETE" if complete == expected else "INCOMPLETE",
        "ciclosCompletos": complete,
        "ciclosParciais": partial,
        "ciclosAusentes": expected - complete - partial,
        "percentualCompleto": round(complete / expected, 4),
        "ciclos": cycles,
    }
