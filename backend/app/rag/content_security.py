import unicodedata

PROMPT_INJECTION_PATTERNS = (
    "ignore as instrucoes",
    "ignorar instrucoes",
    "desconsidere as instrucoes",
    "desconsiderar instrucoes",
    "system prompt",
    "developer message",
    "revele o prompt",
    "execute este comando",
    "obedeca apenas",
)


def has_prompt_injection(content: str) -> bool:
    normalized = unicodedata.normalize("NFKD", str(content or "").lower())
    ascii_text = "".join(
        character
        for character in normalized
        if not unicodedata.combining(character)
    )
    return any(pattern in ascii_text for pattern in PROMPT_INJECTION_PATTERNS)
