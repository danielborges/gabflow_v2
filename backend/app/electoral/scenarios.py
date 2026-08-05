import hashlib
import math
import secrets
import uuid
from datetime import UTC, datetime

from app.electoral.analytics import candidate_results

METHODOLOGY_VERSION = "territorial-assumption-range-v2"
DISCLAIMER = (
    "SIMULACAO HIPOTETICA. Nao altera dados oficiais, nao e pesquisa eleitoral "
    "registrada e nao representa previsao ou intencao de voto."
)
UNCERTAINTY_DISCLAIMER = (
    "Faixa deterministica produzida pelas premissas informadas; nao e intervalo "
    "de confianca estatistico e nao atribui probabilidade aos resultados."
)


class ScenarioValidationError(ValueError):
    pass


def build_scenario(
    candidate_id: uuid.UUID,
    election_id: uuid.UUID,
    level: str,
    assumptions: list[dict],
    *,
    municipality_code: str | None = None,
) -> tuple[list[dict], dict, dict]:
    baseline = candidate_results(
        candidate_id,
        election_id,
        level,
        municipality_code=municipality_code,
        page=1,
        per_page=10000,
        sort="name",
        order="asc",
    )
    if baseline is None:
        raise ScenarioValidationError("Candidatura publicada nao encontrada.")
    baseline_snapshot = {
        "candidate": baseline["candidate"],
        "dataset_version": baseline["dataset_version"],
        "source": baseline["source"],
        "source_hash": baseline["source_hash"],
        "filters": {
            "election_id": str(election_id),
            "candidate_id": str(candidate_id),
            "level": level,
            "municipality_code": municipality_code,
        },
        "candidate_total_votes": baseline["candidate_total_votes"],
        "items": baseline["items"],
    }
    normalized, result = build_from_snapshot(baseline_snapshot, assumptions)
    return normalized, baseline_snapshot, result


def build_from_snapshot(
    baseline_snapshot: dict, assumptions: list[dict]
) -> tuple[list[dict], dict]:
    items = baseline_snapshot.get("items") or []
    by_territory = {item["territory_id"]: item for item in items}
    normalized = _normalize_assumptions(assumptions, by_territory)
    changes = {item["territory_id"]: item for item in normalized}
    projected = [_project_territory(item, changes.get(item["territory_id"], {})) for item in items]
    lower_total = sum(item["uncertainty_interval"]["lower_votes"] for item in projected)
    projected_total = sum(item["projected_votes"] for item in projected)
    upper_total = sum(item["uncertainty_interval"]["upper_votes"] for item in projected)
    result = {
        "simulation": True,
        "methodology_version": METHODOLOGY_VERSION,
        "formula": {
            "projected_denominator": "baseline_denominator * (1 + denominator_delta)",
            "projected_share": "clamp(baseline_share + candidate_share_delta, 0, 1)",
            "projected_votes": "round(projected_denominator * projected_share)",
            "uncertainty_bounds": "same formulas at premise deltas minus/plus uncertainty",
        },
        "baseline_total_votes": baseline_snapshot["candidate_total_votes"],
        "projected_total_votes": projected_total,
        "uncertainty_interval": {
            "lower_votes": lower_total,
            "projected_votes": projected_total,
            "upper_votes": upper_total,
            "kind": "DETERMINISTIC_ASSUMPTION_RANGE",
            "confidence_level": None,
            "disclaimer": UNCERTAINTY_DISCLAIMER,
        },
        "territories": projected,
        "disclaimer": DISCLAIMER,
    }
    return normalized, result


def compare_scenarios(items: list) -> dict:
    if not 2 <= len(items) <= 5:
        raise ScenarioValidationError("Compare entre 2 e 5 cenarios.")
    anchor = items[0]
    signature = _compatibility_signature(anchor)
    if any(_compatibility_signature(item) != signature for item in items[1:]):
        raise ScenarioValidationError(
            "Cenarios incompativeis: use a mesma eleicao, candidatura, nivel e snapshot de dados."
        )
    summaries = []
    for item in items:
        interval = _result_interval(item.result)
        summaries.append(
            {
                "scenario_id": str(item.id),
                "name": item.name,
                "projected_total_votes": item.result["projected_total_votes"],
                "difference_from_baseline": (
                    item.result["projected_total_votes"] - item.result["baseline_total_votes"]
                ),
                "difference_from_anchor": (
                    item.result["projected_total_votes"]
                    - anchor.result["projected_total_votes"]
                ),
                "uncertainty_interval": interval,
            }
        )
    territories = []
    territory_maps = {
        str(item.id): {row["territory_id"]: row for row in item.result["territories"]}
        for item in items
    }
    for base in anchor.result["territories"]:
        territories.append(
            {
                "territory_id": base["territory_id"],
                "territory_name": base["territory_name"],
                "scenarios": [
                    {
                        "scenario_id": str(item.id),
                        "projected_votes": territory_maps[str(item.id)][base["territory_id"]][
                            "projected_votes"
                        ],
                        "projected_share": territory_maps[str(item.id)][base["territory_id"]][
                            "projected_share"
                        ],
                    }
                    for item in items
                ],
            }
        )
    return {
        "simulation": True,
        "compatible": True,
        "anchor_scenario_id": str(anchor.id),
        "baseline": {
            "election_id": str(anchor.baseline_election_id),
            "candidate_id": str(anchor.candidate_id),
            "level": anchor.level,
            "dataset_version": anchor.baseline_snapshot.get("dataset_version"),
            "source_hash": anchor.baseline_snapshot.get("source_hash"),
        },
        "scenarios": summaries,
        "territories": territories,
        "disclaimer": DISCLAIMER,
    }


def sensitivity_analysis(item, share_range: float, denominator_range: float, steps: int) -> dict:
    if not 0 <= share_range <= 1 or not 0 <= denominator_range <= 1:
        raise ScenarioValidationError("Amplitude de sensibilidade deve estar entre 0 e 1.")
    if steps < 3 or steps > 11 or steps % 2 == 0:
        raise ScenarioValidationError("steps deve ser impar e estar entre 3 e 11.")
    share_offsets = _steps(-share_range, share_range, steps)
    denominator_offsets = _steps(-denominator_range, denominator_range, steps)
    samples = []
    for share_offset in share_offsets:
        for denominator_offset in denominator_offsets:
            assumptions = [
                {
                    **assumption,
                    "candidate_share_delta": _clamp(
                        assumption.get("candidate_share_delta", 0) + share_offset, -1, 1
                    ),
                    "denominator_delta": _clamp(
                        assumption.get("denominator_delta", 0) + denominator_offset, -1, 1
                    ),
                }
                for assumption in item.assumptions
            ]
            _, result = build_from_snapshot(item.baseline_snapshot, assumptions)
            samples.append(
                {
                    "candidate_share_offset": round(share_offset, 8),
                    "denominator_offset": round(denominator_offset, 8),
                    "projected_total_votes": result["projected_total_votes"],
                }
            )
    totals = [sample["projected_total_votes"] for sample in samples]
    return {
        "simulation": True,
        "scenario_id": str(item.id),
        "parameters": {
            "candidate_share_range": share_range,
            "denominator_range": denominator_range,
            "steps": steps,
            "sample_count": len(samples),
        },
        "baseline_projected_total_votes": item.result["projected_total_votes"],
        "minimum_projected_total_votes": min(totals),
        "maximum_projected_total_votes": max(totals),
        "samples": samples,
        "uncertainty_kind": "DETERMINISTIC_SENSITIVITY_RANGE",
        "confidence_level": None,
        "disclaimer": UNCERTAINTY_DISCLAIMER,
    }


def new_share_token() -> tuple[str, str]:
    token = secrets.token_urlsafe(32)
    return token, hash_share_token(token)


def hash_share_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def scenario_data(item, *, read_only: bool = False) -> dict:
    return {
        "id": str(item.id),
        "name": item.name,
        "baseline_election_id": str(item.baseline_election_id),
        "candidate_id": str(item.candidate_id),
        "level": item.level,
        "assumptions": item.assumptions,
        "baseline_snapshot": item.baseline_snapshot,
        "result": item.result,
        "methodology_version": item.methodology_version,
        "disclaimer": item.disclaimer,
        "created_by_id": str(item.created_by_id),
        "source_scenario_id": str(item.source_scenario_id) if item.source_scenario_id else None,
        "read_only": read_only,
        "created_at": item.created_at.isoformat(),
    }


def analysis_data(item) -> dict:
    return {
        "id": str(item.id),
        "analysis_type": item.analysis_type,
        "anchor_scenario_id": str(item.anchor_scenario_id),
        "scenario_ids": item.scenario_ids,
        "parameters": item.parameters,
        "result": item.result,
        "methodology_version": item.methodology_version,
        "created_by_id": str(item.created_by_id),
        "created_at": item.created_at.isoformat(),
    }


def share_data(item) -> dict:
    now = datetime.now(UTC)
    expires_at = item.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=UTC)
    status = "REVOKED" if item.revoked_at else "EXPIRED" if expires_at <= now else "ACTIVE"
    return {
        "id": str(item.id),
        "scenario_id": str(item.scenario_id),
        "created_by_id": str(item.created_by_id),
        "status": status,
        "read_only": True,
        "expires_at": item.expires_at.isoformat(),
        "revoked_at": item.revoked_at.isoformat() if item.revoked_at else None,
        "access_count": item.access_count,
        "last_accessed_at": (
            item.last_accessed_at.isoformat() if item.last_accessed_at else None
        ),
        "created_at": item.created_at.isoformat(),
    }


def _project_territory(item: dict, assumption: dict) -> dict:
    share_delta = assumption.get("candidate_share_delta", 0.0)
    denominator_delta = assumption.get("denominator_delta", 0.0)
    share_uncertainty = assumption.get("candidate_share_uncertainty", 0.0)
    denominator_uncertainty = assumption.get("denominator_uncertainty", 0.0)
    projected_denominator = max(0, round(item["denominator_value"] * (1 + denominator_delta)))
    projected_share = _clamp(item["share"] + share_delta, 0, 1)
    projected_votes = round(projected_denominator * projected_share)
    lower_votes = round(
        max(0, item["denominator_value"] * (1 + denominator_delta - denominator_uncertainty))
        * _clamp(item["share"] + share_delta - share_uncertainty, 0, 1)
    )
    upper_votes = round(
        max(0, item["denominator_value"] * (1 + denominator_delta + denominator_uncertainty))
        * _clamp(item["share"] + share_delta + share_uncertainty, 0, 1)
    )
    return {
        "territory_id": item["territory_id"],
        "territory_name": item["territory_name"],
        "baseline_votes": item["votes"],
        "projected_votes": projected_votes,
        "vote_difference": projected_votes - item["votes"],
        "baseline_share": item["share"],
        "projected_share": round(projected_share, 8),
        "baseline_denominator": item["denominator_value"],
        "projected_denominator": projected_denominator,
        "uncertainty_interval": {
            "lower_votes": min(lower_votes, projected_votes),
            "projected_votes": projected_votes,
            "upper_votes": max(upper_votes, projected_votes),
            "kind": "DETERMINISTIC_ASSUMPTION_RANGE",
            "confidence_level": None,
        },
    }


def _normalize_assumptions(assumptions: list[dict], territories: dict[str, dict]) -> list[dict]:
    if not isinstance(assumptions, list) or not assumptions:
        raise ScenarioValidationError("Informe ao menos uma premissa territorial explicita.")
    if len(assumptions) > 100:
        raise ScenarioValidationError("O cenario aceita no maximo 100 premissas territoriais.")
    normalized = []
    seen = set()
    for assumption in assumptions:
        if not isinstance(assumption, dict):
            raise ScenarioValidationError("Cada premissa deve ser um objeto.")
        territory_id = str(assumption.get("territory_id") or "")
        if territory_id not in territories:
            raise ScenarioValidationError("Uma premissa referencia territorio fora do recorte.")
        if territory_id in seen:
            raise ScenarioValidationError("Nao repita territorio nas premissas.")
        try:
            share_delta = float(assumption.get("candidate_share_delta", 0))
            denominator_delta = float(assumption.get("denominator_delta", 0))
            share_uncertainty = float(assumption.get("candidate_share_uncertainty", 0))
            denominator_uncertainty = float(assumption.get("denominator_uncertainty", 0))
        except (TypeError, ValueError) as error:
            raise ScenarioValidationError("Deltas e incertezas devem ser numericos.") from error
        if not all(
            math.isfinite(value)
            for value in (
                share_delta,
                denominator_delta,
                share_uncertainty,
                denominator_uncertainty,
            )
        ):
            raise ScenarioValidationError("Deltas e incertezas devem ser numeros finitos.")
        if not -1 <= share_delta <= 1 or not -1 <= denominator_delta <= 1:
            raise ScenarioValidationError("Deltas devem estar entre -1 e 1.")
        if not 0 <= share_uncertainty <= 1 or not 0 <= denominator_uncertainty <= 1:
            raise ScenarioValidationError("Incertezas devem estar entre 0 e 1.")
        rationale = " ".join(str(assumption.get("rationale") or "").split())
        if not rationale:
            raise ScenarioValidationError("Toda premissa deve possuir justificativa explicita.")
        seen.add(territory_id)
        normalized.append(
            {
                "territory_id": territory_id,
                "candidate_share_delta": share_delta,
                "denominator_delta": denominator_delta,
                "candidate_share_uncertainty": share_uncertainty,
                "denominator_uncertainty": denominator_uncertainty,
                "rationale": rationale[:500],
            }
        )
    return normalized


def _compatibility_signature(item) -> tuple:
    return (
        str(item.baseline_election_id),
        str(item.candidate_id),
        item.level,
        item.baseline_snapshot.get("dataset_version"),
        item.baseline_snapshot.get("source_hash"),
        item.baseline_snapshot.get("filters", {}).get("municipality_code"),
    )


def _result_interval(result: dict) -> dict:
    return result.get("uncertainty_interval") or {
        "lower_votes": result["projected_total_votes"],
        "projected_votes": result["projected_total_votes"],
        "upper_votes": result["projected_total_votes"],
        "kind": "DETERMINISTIC_ASSUMPTION_RANGE",
        "confidence_level": None,
    }


def _steps(start: float, end: float, count: int) -> list[float]:
    distance = (end - start) / (count - 1)
    return [start + distance * index for index in range(count)]


def _clamp(value: float, lower: float, upper: float) -> float:
    return min(upper, max(lower, value))
