import hashlib
import re
import unicodedata
from dataclasses import dataclass

from app.rag.content_security import (
    ContentSecurityAction,
    ContentSecuritySurface,
    assess_content_security,
)

POLICY_VERSION = "electoral-question-safety-v1"


@dataclass(frozen=True)
class ElectoralQuestionDecision:
    allowed: bool
    category: str | None
    reason: str | None
    prompt_hash: str
    prompt_length: int
    policy_version: str
    signals: tuple[str, ...]
    content_security: dict

    def audit_data(self) -> dict:
        return {
            "allowed": self.allowed,
            "category": self.category,
            "promptHash": self.prompt_hash,
            "promptLength": self.prompt_length,
            "policyVersion": self.policy_version,
            "signals": list(self.signals),
            "contentSecurity": {
                "status": self.content_security.get("status"),
                "action": self.content_security.get("action"),
                "policyVersion": self.content_security.get("policyVersion"),
                "detectorVersion": self.content_security.get("detectorVersion"),
                "categories": self.content_security.get("categories", []),
                "signals": self.content_security.get("signals", []),
            },
        }


RULES = (
    (
        "INDIVIDUAL_VOTE_INFERENCE",
        (
            r"\bquem\s+votou\b",
            r"\bem\s+quem\s+.+\s+vot(?:ou|ara|aria)\b",
            r"\bcomo\s+.+\s+vot(?:ou|ara|aria)\b",
            r"\bidentifi(?:que|car).{0,40}\beleitor(?:a|es|as)?\b",
            r"\blista.{0,30}\beleitor(?:a|es|as)?\b",
            r"\bcpf\b.{0,50}\bvot",
        ),
        "Nao e permitido inferir ou identificar o voto de uma pessoa.",
    ),
    (
        "VOTE_INTENTION_OR_PREDICTION",
        (
            r"\binten[cç][aã]o\s+de\s+voto\b",
            r"\b(?:vai|pretende|deve)\s+votar\b",
            r"\bprevej[ao].{0,40}\bvot",
            r"\bprobabilidade.{0,40}\bvotar\b",
            r"\bquem\s+vai\s+ganhar\b",
        ),
        "Resultados historicos nao autorizam inferencia de intencao de voto ou previsao.",
    ),
    (
        "SENSITIVE_ATTRIBUTE_INFERENCE",
        (
            r"\b(?:qual|infira|deduza|classifique|perfil).{0,50}\bideologi",
            r"\b(?:qual|infira|deduza|classifique|perfil).{0,50}\b(?:religia|religio)",
            r"\b(?:infira|deduza|classifique|perfil).{0,50}\b(?:ra[cç]a|etnia|sexual|sa[uú]de|defici[eê]ncia)\b",
            r"\bsegment(?:e|ar).{0,50}\b(?:ideologi|religia|ra[cç]a|etnia|sexual|sa[uú]de)\b",
        ),
        "Nao e permitido inferir ideologia ou atributos pessoais sensiveis.",
    ),
    (
        "UNSUPPORTED_CAUSALITY",
        (
            r"\bpor\s+que.{0,80}\bvot(?:ou|aram|a[cç][aã]o)\b",
            r"\bo\s+que\s+causou.{0,80}\bvot",
            r"\bcausa.{0,50}\bresultado\s+eleitoral\b",
            r"\bprove.{0,50}\b(?:porque|causou|devido)\b",
        ),
        "Os dados disponiveis nao demonstram causalidade sobre comportamento eleitoral.",
    ),
    (
        "SMALL_GROUP_OR_PERSON_IDENTIFICATION",
        (
            r"\b(?:nome|endere[cç]o|telefone|email).{0,50}\beleitor",
            r"\b(?:familia|moradores?|pessoas?).{0,50}\bcomo\s+vot",
            r"\bpor\s+rua\b.{0,60}\bvot",
        ),
        "Nao e permitido identificar pessoas ou pequenos grupos a partir de dados eleitorais.",
    ),
)


def assess_electoral_question(question: str) -> ElectoralQuestionDecision:
    value = " ".join(str(question or "").split())
    prompt_hash = hashlib.sha256(value.encode("utf-8")).hexdigest()
    content_decision = assess_content_security(
        value,
        surface=ContentSecuritySurface.USER_QUERY,
    )
    content_state = content_decision.as_dict()
    if content_decision.action != ContentSecurityAction.ALLOW:
        return ElectoralQuestionDecision(
            False,
            "PROMPT_INJECTION_OR_UNSAFE_INSTRUCTION",
            "A pergunta contem uma instrucao insegura ou tentativa de manipular o assistente.",
            prompt_hash,
            len(value),
            POLICY_VERSION,
            tuple(content_decision.signals),
            content_state,
        )

    normalized = _normalize(value)
    for category, patterns, reason in RULES:
        matched = tuple(pattern for pattern in patterns if re.search(pattern, normalized))
        if matched:
            return ElectoralQuestionDecision(
                False,
                category,
                reason,
                prompt_hash,
                len(value),
                POLICY_VERSION,
                matched,
                content_state,
            )
    return ElectoralQuestionDecision(
        True,
        None,
        None,
        prompt_hash,
        len(value),
        POLICY_VERSION,
        (),
        content_state,
    )


def _normalize(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", value.casefold())
    return "".join(character for character in decomposed if not unicodedata.combining(character))
