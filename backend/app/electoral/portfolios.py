import csv
import io
import uuid

from sqlalchemy import select

from app.electoral.scenarios import DISCLAIMER
from app.extensions import db
from app.models import (
    ElectoralScenario,
    ElectoralScenarioPortfolioEvent,
    ElectoralScenarioPortfolioItem,
)

PORTFOLIO_METHODOLOGY_VERSION = "scenario-portfolio-goals-v1"
MAX_SCENARIOS = 20
MAX_GOALS = 100


class PortfolioValidationError(ValueError):
    pass


def portfolio_scenarios(
    portfolio,
) -> list[tuple[ElectoralScenarioPortfolioItem, ElectoralScenario]]:
    memberships = list(
        db.session.scalars(
            select(ElectoralScenarioPortfolioItem)
            .where(
                ElectoralScenarioPortfolioItem.tenant_id == portfolio.tenant_id,
                ElectoralScenarioPortfolioItem.portfolio_id == portfolio.id,
                ElectoralScenarioPortfolioItem.removed_at.is_(None),
            )
            .order_by(
                ElectoralScenarioPortfolioItem.position,
                ElectoralScenarioPortfolioItem.added_at,
            )
        )
    )
    if not memberships:
        return []
    scenarios = {
        item.id: item
        for item in db.session.scalars(
            select(ElectoralScenario).where(
                ElectoralScenario.tenant_id == portfolio.tenant_id,
                ElectoralScenario.id.in_([membership.scenario_id for membership in memberships]),
            )
        )
    }
    return [
        (membership, scenarios[membership.scenario_id])
        for membership in memberships
        if membership.scenario_id in scenarios
    ]


def portfolio_data(portfolio, *, include_evaluation: bool = False) -> dict:
    entries = portfolio_scenarios(portfolio)
    scenarios = [scenario for _, scenario in entries]
    data = {
        "id": str(portfolio.id),
        "name": portfolio.name,
        "description": portfolio.description,
        "status": portfolio.status,
        "reference_scenario_id": (
            str(portfolio.reference_scenario_id) if portfolio.reference_scenario_id else None
        ),
        "goals": portfolio.goals,
        "methodology_version": PORTFOLIO_METHODOLOGY_VERSION,
        "simulation": True,
        "disclaimer": DISCLAIMER,
        "created_by_id": str(portfolio.created_by_id),
        "created_at": portfolio.created_at.isoformat(),
        "updated_at": portfolio.updated_at.isoformat(),
        "scenarios": [
            {
                "membership_id": str(membership.id),
                "id": str(scenario.id),
                "name": scenario.name,
                "label": membership.label,
                "position": membership.position,
                "projected_total_votes": scenario.result["projected_total_votes"],
                "uncertainty_interval": _result_interval(scenario.result),
                "dataset_version": scenario.baseline_snapshot.get("dataset_version"),
                "methodology_version": scenario.methodology_version,
                "is_reference": scenario.id == portfolio.reference_scenario_id,
            }
            for membership, scenario in entries
        ],
    }
    if include_evaluation:
        data["evaluation"] = evaluate_portfolio(portfolio, scenarios)
    return data


def ensure_compatible(existing: list[ElectoralScenario], candidate: ElectoralScenario) -> None:
    if existing and _signature(existing[0]) != _signature(candidate):
        raise PortfolioValidationError(
            "O portfolio aceita apenas cenarios da mesma eleicao, candidatura, nivel e snapshot."
        )


def normalize_goals(goals, scenarios: list[ElectoralScenario]) -> list[dict]:
    if not isinstance(goals, list):
        raise PortfolioValidationError("goals deve ser uma lista.")
    if len(goals) > MAX_GOALS:
        raise PortfolioValidationError(f"O portfolio aceita no maximo {MAX_GOALS} metas.")
    territory_ids = {
        row["territory_id"]
        for scenario in scenarios[:1]
        for row in scenario.result.get("territories", [])
    }
    normalized = []
    seen = set()
    for raw in goals:
        if not isinstance(raw, dict):
            raise PortfolioValidationError("Cada meta deve ser um objeto.")
        scope = str(raw.get("scope") or "TOTAL").strip().upper()
        metric = str(raw.get("metric") or "VOTES").strip().upper()
        territory_id = str(raw.get("territory_id") or "").strip() or None
        if scope not in {"TOTAL", "TERRITORY"}:
            raise PortfolioValidationError("scope deve ser TOTAL ou TERRITORY.")
        if metric not in {"VOTES", "SHARE"}:
            raise PortfolioValidationError("metric deve ser VOTES ou SHARE.")
        if scope == "TOTAL" and territory_id:
            raise PortfolioValidationError("Meta total nao deve informar territorio.")
        if scope == "TERRITORY" and territory_id not in territory_ids:
            raise PortfolioValidationError("Meta territorial fora do recorte dos cenarios.")
        try:
            target_value = float(raw.get("target_value"))
        except (TypeError, ValueError) as error:
            raise PortfolioValidationError("target_value deve ser numerico.") from error
        if target_value < 0 or metric == "SHARE" and target_value > 1:
            raise PortfolioValidationError(
                "Meta deve ser positiva; participacao deve estar entre 0 e 1."
            )
        key = (scope, territory_id, metric)
        if key in seen:
            raise PortfolioValidationError("Nao repita escopo, territorio e metrica nas metas.")
        seen.add(key)
        normalized.append(
            {
                "id": str(raw.get("id") or uuid.uuid4()),
                "scope": scope,
                "territory_id": territory_id,
                "metric": metric,
                "target_value": target_value,
                "rationale": str(raw.get("rationale") or "").strip()[:500],
            }
        )
    return normalized


def evaluate_portfolio(portfolio, scenarios: list[ElectoralScenario] | None = None) -> dict:
    if scenarios is None:
        scenarios = [scenario for _, scenario in portfolio_scenarios(portfolio)]
    results = []
    for scenario in scenarios:
        goal_results = []
        territories = {
            row["territory_id"]: row for row in scenario.result.get("territories", [])
        }
        for goal in portfolio.goals or []:
            actual = _goal_actual(scenario, territories, goal)
            target = goal["target_value"]
            goal_results.append(
                {
                    **goal,
                    "actual_value": round(actual, 8),
                    "difference": round(actual - target, 8),
                    "attainment_percent": (
                        round(actual / target * 100, 2) if target else None
                    ),
                    "met": actual >= target,
                }
            )
        results.append(
            {
                "scenario_id": str(scenario.id),
                "name": scenario.name,
                "is_reference": scenario.id == portfolio.reference_scenario_id,
                "projected_total_votes": scenario.result["projected_total_votes"],
                "goals": goal_results,
            }
        )
    return {
        "simulation": True,
        "reference_scenario_id": (
            str(portfolio.reference_scenario_id) if portfolio.reference_scenario_id else None
        ),
        "goal_count": len(portfolio.goals or []),
        "scenarios": results,
        "methodology_version": PORTFOLIO_METHODOLOGY_VERSION,
        "disclaimer": DISCLAIMER,
    }


def record_portfolio_event(portfolio, actor_id, event_type: str, payload: dict) -> None:
    db.session.add(
        ElectoralScenarioPortfolioEvent(
            tenant_id=portfolio.tenant_id,
            portfolio_id=portfolio.id,
            actor_id=actor_id,
            event_type=event_type,
            payload=payload,
        )
    )


def portfolio_event_data(item) -> dict:
    return {
        "id": str(item.id),
        "event_type": item.event_type,
        "actor_id": str(item.actor_id),
        "payload": item.payload,
        "created_at": item.created_at.isoformat(),
    }


def portfolio_csv(portfolio) -> bytes:
    entries = portfolio_scenarios(portfolio)
    evaluation = evaluate_portfolio(portfolio, [scenario for _, scenario in entries])
    output = io.StringIO(newline="")
    writer = csv.writer(output, delimiter=";")
    writer.writerow(["PORTFOLIO DE CENARIOS - SIMULACAO HIPOTETICA"])
    writer.writerow(["Portfolio", portfolio.name])
    writer.writerow(["Metodologia", PORTFOLIO_METHODOLOGY_VERSION])
    writer.writerow(["Aviso", DISCLAIMER])
    writer.writerow([])
    writer.writerow(
        [
            "Cenario",
            "Referencia",
            "Votos projetados",
            "Limite inferior",
            "Limite superior",
            "Dataset",
        ]
    )
    for membership, scenario in entries:
        interval = _result_interval(scenario.result)
        writer.writerow(
            [
                membership.label or scenario.name,
                "SIM" if scenario.id == portfolio.reference_scenario_id else "NAO",
                scenario.result["projected_total_votes"],
                interval["lower_votes"],
                interval["upper_votes"],
                scenario.baseline_snapshot.get("dataset_version"),
            ]
        )
    writer.writerow([])
    writer.writerow(
        ["Cenario", "Escopo", "Territorio", "Metrica", "Meta", "Valor", "Diferenca", "Atingida"]
    )
    for scenario in evaluation["scenarios"]:
        for goal in scenario["goals"]:
            writer.writerow(
                [
                    scenario["name"],
                    goal["scope"],
                    goal.get("territory_id") or "TOTAL",
                    goal["metric"],
                    goal["target_value"],
                    goal["actual_value"],
                    goal["difference"],
                    "SIM" if goal["met"] else "NAO",
                ]
            )
    return output.getvalue().encode("utf-8-sig")


def _goal_actual(scenario, territories: dict, goal: dict) -> float:
    if goal["scope"] == "TOTAL":
        if goal["metric"] == "VOTES":
            return float(scenario.result["projected_total_votes"])
        denominator = sum(row["projected_denominator"] for row in territories.values())
        return scenario.result["projected_total_votes"] / denominator if denominator else 0
    territory = territories[goal["territory_id"]]
    return float(
        territory["projected_votes"]
        if goal["metric"] == "VOTES"
        else territory["projected_share"]
    )


def _signature(item) -> tuple:
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
