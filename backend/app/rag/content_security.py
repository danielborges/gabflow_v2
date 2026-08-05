import hashlib
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from enum import Enum
from typing import Any

from flask import current_app, has_app_context

from app.rag.content_canonicalization import canonicalize_content
from app.rag.prompt_injection_classifier import (
    PromptInjectionClassification,
    PromptInjectionClassifierError,
    prompt_injection_classifier,
)


class ContentSecurityStatus(str, Enum):
    CLEAN = "CLEAN"
    SUSPICIOUS = "SUSPICIOUS"
    MALICIOUS = "MALICIOUS"
    INDETERMINATE = "INDETERMINATE"


class ContentSecurityAction(str, Enum):
    ALLOW = "ALLOW"
    QUARANTINE = "QUARANTINE"
    BLOCK = "BLOCK"
    RETRY = "RETRY"


class ContentSecuritySurface(str, Enum):
    DOCUMENT_BODY = "DOCUMENT_BODY"
    DOCUMENT_METADATA = "DOCUMENT_METADATA"
    OCR_LAYER = "OCR_LAYER"
    CHUNK_SEQUENCE = "CHUNK_SEQUENCE"
    USER_QUERY = "USER_QUERY"
    FEEDBACK = "FEEDBACK"
    CONNECTOR_CONTENT = "CONNECTOR_CONTENT"


class ContentSecurityReviewDecision(str, Enum):
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


@dataclass(frozen=True)
class ContentSecurityPattern:
    id: str
    text: str
    category: str
    score: float


@dataclass(frozen=True)
class ContentSecurityDecision:
    status: ContentSecurityStatus
    action: ContentSecurityAction
    score: float
    categories: tuple[str, ...]
    signals: tuple[str, ...]
    policy_version: str
    detector_version: str
    classifier: dict[str, Any]
    content_checksum: str
    assessed_at: datetime
    surface: ContentSecuritySurface
    error_code: str | None = None

    @property
    def risky(self) -> bool:
        return self.status in {
            ContentSecurityStatus.SUSPICIOUS,
            ContentSecurityStatus.MALICIOUS,
        }

    def as_dict(self) -> dict:
        return {
            "status": self.status.value,
            "action": self.action.value,
            "score": round(self.score, 4),
            "categories": list(self.categories),
            "signals": list(self.signals),
            "policyVersion": self.policy_version,
            "detectorVersion": self.detector_version,
            "classifier": dict(self.classifier),
            "contentChecksum": self.content_checksum,
            "assessedAt": self.assessed_at.isoformat(),
            "surface": self.surface.value,
            "errorCode": self.error_code,
        }


DEFAULT_POLICY_VERSION = "rag-content-security-v2"
DEFAULT_DETECTOR_VERSION = "canonical-deterministic-v2"

PROMPT_INJECTION_PATTERNS = (
    ContentSecurityPattern(
        "PI_INSTRUCTION_IGNORE_PT",
        "ignore as instrucoes",
        "INSTRUCTION_OVERRIDE",
        0.9,
    ),
    ContentSecurityPattern(
        "PI_INSTRUCTION_IGNORE_ALL_PT",
        "ignore todas as instrucoes",
        "INSTRUCTION_OVERRIDE",
        0.95,
    ),
    ContentSecurityPattern(
        "PI_INSTRUCTION_IGNORE_ALT_PT",
        "ignorar instrucoes",
        "INSTRUCTION_OVERRIDE",
        0.88,
    ),
    ContentSecurityPattern(
        "PI_INSTRUCTION_DISREGARD_PT",
        "desconsidere as instrucoes",
        "INSTRUCTION_OVERRIDE",
        0.9,
    ),
    ContentSecurityPattern(
        "PI_INSTRUCTION_DISREGARD_ALT_PT",
        "desconsiderar instrucoes",
        "INSTRUCTION_OVERRIDE",
        0.88,
    ),
    ContentSecurityPattern(
        "PI_SYSTEM_PROMPT",
        "system prompt",
        "PROMPT_EXTRACTION",
        0.82,
    ),
    ContentSecurityPattern(
        "PI_DEVELOPER_MESSAGE",
        "developer message",
        "FAKE_SYSTEM_MESSAGE",
        0.82,
    ),
    ContentSecurityPattern(
        "PI_REVEAL_PROMPT_PT",
        "revele o prompt",
        "PROMPT_EXTRACTION",
        0.95,
    ),
    ContentSecurityPattern(
        "PI_EXECUTE_COMMAND_PT",
        "execute este comando",
        "TOOL_MANIPULATION",
        0.85,
    ),
    ContentSecurityPattern(
        "PI_OBEY_ONLY_PT",
        "obedeca apenas",
        "INSTRUCTION_OVERRIDE",
        0.88,
    ),
)


def assess_content_security(
    content: str,
    *,
    surface: ContentSecuritySurface = ContentSecuritySurface.DOCUMENT_BODY,
    metadata: dict[str, Any] | None = None,
) -> ContentSecurityDecision:
    policy_version = _config(
        "RAG_CONTENT_SECURITY_POLICY_VERSION",
        DEFAULT_POLICY_VERSION,
    )
    detector_version = _config(
        "RAG_CONTENT_SECURITY_DETECTOR_VERSION",
        DEFAULT_DETECTOR_VERSION,
    )
    assessed_at = datetime.now(UTC)
    try:
        material = _material(content, metadata)
        checksum = hashlib.sha256(material.encode("utf-8")).hexdigest()
        canonical = canonicalize_content(
            material,
            max_chars=int(_config_value("RAG_CONTENT_SECURITY_MAX_CANONICAL_CHARS", 1_000_000)),
            max_decoded_chars=int(_config_value("RAG_CONTENT_SECURITY_MAX_DECODED_CHARS", 4096)),
        )
        normalized = canonical.text
        matches = tuple(
            pattern for pattern in PROMPT_INJECTION_PATTERNS if pattern.text in normalized
        )
        if _benign_security_context(normalized):
            matches = ()

        signals = [pattern.id for pattern in matches]
        signals.extend(canonical.transformations)
        categories = {pattern.category for pattern in matches}
        categories.update(_canonicalization_categories(canonical.transformations))
        score = max((pattern.score for pattern in matches), default=0.0)
        classification = None
        classifier_state: dict[str, Any] = {}
        classifier_enabled = bool(_config_value("RAG_PROMPT_INJECTION_CLASSIFIER_ENABLED", False))
        classifier_required = bool(_config_value("RAG_PROMPT_INJECTION_CLASSIFIER_REQUIRED", False))
        if classifier_required and not classifier_enabled:
            return _indeterminate_decision(
                policy_version,
                detector_version,
                checksum,
                assessed_at,
                surface,
                "PROMPT_INJECTION_CLASSIFIER_DISABLED",
            )
        if classifier_enabled:
            try:
                classifier = prompt_injection_classifier()
                max_classifier_chars = int(
                    _config_value("RAG_PROMPT_INJECTION_CLASSIFIER_MAX_CHARS", 16_000)
                )
                classification = classifier.classify(
                    normalized[:max_classifier_chars],
                    surface.value,
                )
                classifier_state = _classifier_state(classification)
                categories.update(classification.categories)
                score = max(score, classification.score)
                signals.append("PROMPT_INJECTION_CLASSIFIER")
            except (PromptInjectionClassifierError, ValueError) as error:
                if bool(_config_value("RAG_PROMPT_INJECTION_FAIL_CLOSED", True)):
                    return _indeterminate_decision(
                        policy_version,
                        detector_version,
                        checksum,
                        assessed_at,
                        surface,
                        "PROMPT_INJECTION_CLASSIFIER_UNAVAILABLE",
                        classifier={
                            "applied": False,
                            "provider": str(
                                _config_value(
                                    "RAG_PROMPT_INJECTION_CLASSIFIER_PROVIDER",
                                    "unknown",
                                )
                            ),
                            "model": str(
                                _config_value("RAG_PROMPT_INJECTION_CLASSIFIER_MODEL", "unknown")
                            ),
                            "version": str(
                                _config_value(
                                    "RAG_PROMPT_INJECTION_CLASSIFIER_VERSION",
                                    "unknown",
                                )
                            ),
                            "errorCode": type(error).__name__,
                        },
                    )
                signals.append("PROMPT_INJECTION_CLASSIFIER_FALLBACK")

        risky_label = classification and classification.label in {
            "SUSPICIOUS",
            "MALICIOUS",
        }
        if not matches and not risky_label:
            return ContentSecurityDecision(
                ContentSecurityStatus.CLEAN,
                ContentSecurityAction.ALLOW,
                0.0,
                (),
                tuple(dict.fromkeys(signals)),
                policy_version,
                detector_version,
                classifier_state,
                checksum,
                assessed_at,
                surface,
            )
        status = (
            ContentSecurityStatus.MALICIOUS
            if classification and classification.label == "MALICIOUS"
            else ContentSecurityStatus.SUSPICIOUS
        )
        action = (
            ContentSecurityAction.BLOCK
            if surface == ContentSecuritySurface.USER_QUERY
            else ContentSecurityAction.QUARANTINE
        )
        return ContentSecurityDecision(
            status,
            action,
            score,
            tuple(sorted(categories)),
            tuple(dict.fromkeys(signals)),
            policy_version,
            detector_version,
            classifier_state,
            checksum,
            assessed_at,
            surface,
        )
    except (TypeError, ValueError, UnicodeError):
        fallback = str(content or "")
        return ContentSecurityDecision(
            ContentSecurityStatus.INDETERMINATE,
            ContentSecurityAction.RETRY,
            0.0,
            (),
            ("CONTENT_SECURITY_EVALUATION_ERROR",),
            policy_version,
            detector_version,
            {},
            hashlib.sha256(fallback.encode("utf-8", errors="replace")).hexdigest(),
            assessed_at,
            surface,
            "CONTENT_SECURITY_EVALUATION_ERROR",
        )


def apply_content_security_decision(
    target,
    decision: ContentSecurityDecision,
) -> None:
    target.security_status = decision.status
    target.security_action = decision.action
    target.security_score = decision.score
    target.security_categories = list(decision.categories)
    target.security_signals = list(decision.signals)
    target.security_policy_version = decision.policy_version
    target.security_detector_version = decision.detector_version
    target.security_classifier = dict(decision.classifier)
    target.security_content_checksum = decision.content_checksum
    target.security_scanned_at = decision.assessed_at
    target.security_error_code = decision.error_code


def apply_approved_review(
    target,
    decision: ContentSecurityDecision,
) -> ContentSecurityDecision:
    review_decision = getattr(target, "security_review_decision", None)
    review_value = review_decision.value if isinstance(review_decision, Enum) else review_decision
    review_checksum = getattr(target, "security_review_checksum", None)
    if (
        not decision.risky
        or review_value != ContentSecurityReviewDecision.APPROVED.value
        or review_checksum != decision.content_checksum
    ):
        return decision
    classifier = dict(decision.classifier)
    classifier["manualReview"] = {
        "decision": ContentSecurityReviewDecision.APPROVED.value,
        "checksumBound": True,
    }
    return replace(
        decision,
        status=ContentSecurityStatus.CLEAN,
        action=ContentSecurityAction.ALLOW,
        classifier=classifier,
    )


def record_content_security_review(
    target,
    decision: ContentSecurityReviewDecision,
    *,
    reviewer_id,
    reason: str,
) -> None:
    target.security_review_decision = decision
    target.security_review_checksum = target.security_content_checksum
    target.security_reviewed_by_id = reviewer_id
    target.security_reviewed_at = datetime.now(UTC)
    target.security_review_reason = reason


def content_security_state(target) -> dict:
    status = getattr(target, "security_status", ContentSecurityStatus.INDETERMINATE)
    action = getattr(target, "security_action", ContentSecurityAction.RETRY)
    review_decision = getattr(target, "security_review_decision", None)
    return {
        "status": status.value if isinstance(status, Enum) else str(status),
        "action": action.value if isinstance(action, Enum) else str(action),
        "score": round(float(getattr(target, "security_score", 0.0) or 0.0), 4),
        "categories": list(getattr(target, "security_categories", None) or []),
        "signals": list(getattr(target, "security_signals", None) or []),
        "policyVersion": getattr(target, "security_policy_version", None),
        "detectorVersion": getattr(target, "security_detector_version", None),
        "classifier": dict(getattr(target, "security_classifier", None) or {}),
        "contentChecksum": getattr(target, "security_content_checksum", None),
        "scannedAt": (
            target.security_scanned_at.isoformat()
            if getattr(target, "security_scanned_at", None)
            else None
        ),
        "errorCode": getattr(target, "security_error_code", None),
        "quarantinedAt": (
            target.security_quarantined_at.isoformat()
            if getattr(target, "security_quarantined_at", None)
            else None
        ),
        "purgedAt": (
            target.security_purged_at.isoformat()
            if getattr(target, "security_purged_at", None)
            else None
        ),
        "review": {
            "decision": (
                review_decision.value if isinstance(review_decision, Enum) else review_decision
            ),
            "checksum": getattr(target, "security_review_checksum", None),
            "reviewedById": (
                str(target.security_reviewed_by_id)
                if getattr(target, "security_reviewed_by_id", None)
                else None
            ),
            "reviewedAt": (
                target.security_reviewed_at.isoformat()
                if getattr(target, "security_reviewed_at", None)
                else None
            ),
            "reason": getattr(target, "security_review_reason", None),
        },
    }


def has_prompt_injection(content: str) -> bool:
    return assess_content_security(content).risky


def _material(content: str, metadata: dict[str, Any] | None) -> str:
    values = [str(content or "")]
    if metadata:
        for key in sorted(metadata):
            value = metadata[key]
            if value is None:
                continue
            values.append(f"{key}: {value}")
    return "\n".join(values)


def _canonicalization_categories(transformations: tuple[str, ...]) -> set[str]:
    categories = set()
    if {"CANONICAL_BASE64_DECODED", "CANONICAL_HEX_DECODED"}.intersection(transformations):
        categories.add("ENCODED_INSTRUCTION")
    if "CANONICAL_CHARACTER_SPACING" in transformations:
        categories.add("OBFUSCATION")
    if "CANONICAL_INVISIBLE_REMOVED" in transformations:
        categories.add("UNICODE_OBFUSCATION")
    if "CANONICAL_TYPOGLYCEMIA_REPAIRED" in transformations:
        categories.add("TYPOGLYCEMIA")
    return categories


def _benign_security_context(content: str) -> bool:
    markers = (
        "devem ser identificados e recusados",
        "deve ser identificado e recusado",
        "e vedado ao sistema revelar",
        "example of indirect prompt injection",
        "must be quarantined",
        "manual de prevencao a prompt injection",
        "proibem revelar o prompt",
        "nenhuma acao foi realizada",
        "recomendou sua quarentena",
    )
    return any(marker in content for marker in markers)


def _classifier_state(classification: PromptInjectionClassification) -> dict[str, Any]:
    return {
        "applied": True,
        "provider": classification.provider,
        "model": classification.model,
        "version": classification.version,
        "label": classification.label,
        "score": round(classification.score, 4),
        "categories": list(classification.categories),
    }


def _indeterminate_decision(
    policy_version: str,
    detector_version: str,
    checksum: str,
    assessed_at: datetime,
    surface: ContentSecuritySurface,
    error_code: str,
    *,
    classifier: dict[str, Any] | None = None,
) -> ContentSecurityDecision:
    return ContentSecurityDecision(
        ContentSecurityStatus.INDETERMINATE,
        ContentSecurityAction.RETRY,
        0.0,
        (),
        (error_code,),
        policy_version,
        detector_version,
        classifier or {},
        checksum,
        assessed_at,
        surface,
        error_code,
    )


def _config(name: str, default: str) -> str:
    if not has_app_context():
        return default
    return str(current_app.config.get(name, default))


def _config_value(name: str, default):
    if not has_app_context():
        return default
    return current_app.config.get(name, default)
