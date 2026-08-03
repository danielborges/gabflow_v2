PLAN_USER_LIMITS = {
    "starter": 5,
    "professional": 15,
    "premium": 9999,
}
PLAN_RESTRICTED_MODULES = {
    "inteligencia_eleitoral": {"premium"},
}
USER_LIMIT_REACHED_MESSAGE = (
    "Limite de usuarios atingido. Faça um upgrade no seu plano e continue aumentando "
    "a produtividade do seu gabinente."
)

PLANS = set(PLAN_USER_LIMITS)


def normalize_plan(value) -> str:
    plan = str(value or "starter").strip().lower()
    if plan not in PLANS:
        raise ValueError("Plano contratado invalido.")
    return plan


def user_limit_for_plan(value) -> int:
    return PLAN_USER_LIMITS[normalize_plan(value)]


def module_entitled_for_plan(module: str, plan) -> bool:
    entitled_plans = PLAN_RESTRICTED_MODULES.get(str(module).strip().lower())
    return entitled_plans is None or normalize_plan(plan) in entitled_plans


def entitled_modules_for_plan(modules, plan) -> list[str]:
    return sorted(
        module
        for module in {str(item).strip().lower() for item in modules or [] if str(item).strip()}
        if module_entitled_for_plan(module, plan)
    )
