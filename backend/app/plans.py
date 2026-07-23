PLAN_USER_LIMITS = {
    "starter": 5,
    "professional": 15,
    "premium": 9999,
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
