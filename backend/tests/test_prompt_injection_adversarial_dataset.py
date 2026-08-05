import json
from collections import Counter
from pathlib import Path

from app.rag.content_security import ContentSecuritySurface, assess_content_security

DATASET_ROOT = Path(__file__).resolve().parents[2] / "docs" / "specs" / "datasets"
DATASET_PATH = DATASET_ROOT / "prompt-injection-adversarial-v1.json"
SCHEMA_PATH = DATASET_ROOT / "prompt-injection-adversarial.schema.json"


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_prompt_injection_dataset_contract_and_coverage():
    schema = _load(SCHEMA_PATH)
    dataset = _load(DATASET_PATH)

    assert schema["$schema"].endswith("2020-12/schema")
    assert dataset["datasetId"] == "gabflow-prompt-injection-adversarial"
    assert dataset["$schema"] == "./prompt-injection-adversarial.schema.json"
    assert dataset["version"] == "1.0.0"

    cases = dataset["cases"]
    ids = [case["id"] for case in cases]
    assert len(cases) >= 20
    assert len(ids) == len(set(ids))

    kinds = Counter(case["kind"] for case in cases)
    partitions = Counter(case["partition"] for case in cases)
    languages = {case["language"] for case in cases}
    surfaces = {case["surface"] for case in cases}

    assert kinds["ADVERSARIAL"] >= 15
    assert kinds["BENIGN_CONTROL"] >= 8
    assert partitions["REGRESSION"] > 0
    assert partitions["HOLDOUT"] > 0
    assert {"pt-BR", "en", "es", "encoded"}.issubset(languages)
    assert {
        "DOCUMENT_BODY",
        "DOCUMENT_METADATA",
        "OCR_LAYER",
        "CHUNK_SEQUENCE",
        "USER_QUERY",
        "FEEDBACK",
        "CONNECTOR_CONTENT",
    }.issubset(surfaces)


def test_adversarial_expectations_fail_closed_and_benign_controls_allow():
    cases = _load(DATASET_PATH)["cases"]
    serialized_inputs = set()

    for case in cases:
        serialized = json.dumps(
            case["input"],
            ensure_ascii=False,
            sort_keys=True,
        )
        assert serialized not in serialized_inputs
        serialized_inputs.add(serialized)
        assert case["techniques"]
        assert case["rationale"].strip()

        expected = case["expected"]
        if case["kind"] == "ADVERSARIAL":
            assert case["id"].startswith("ADV-")
            assert expected["status"] in {"SUSPICIOUS", "MALICIOUS"}
            assert expected["action"] in {"QUARANTINE", "BLOCK"}
            assert expected["categories"]
            assert expected["minimumScore"] >= 0.8
        else:
            assert case["id"].startswith("BEN-")
            assert expected == {
                "status": "CLEAN",
                "action": "ALLOW",
                "categories": [],
            }


def test_adversarial_dataset_is_an_executable_gateway_regression(app):
    app.config.update(
        RAG_PROMPT_INJECTION_CLASSIFIER_ENABLED=True,
        RAG_PROMPT_INJECTION_CLASSIFIER_REQUIRED=True,
        RAG_PROMPT_INJECTION_CLASSIFIER_PROVIDER="local",
        RAG_PROMPT_INJECTION_CLASSIFIER_MODEL="gabflow-prompt-injection-rules-v1",
        RAG_PROMPT_INJECTION_CLASSIFIER_VERSION="prompt-injection-classifier-v1",
        RAG_PROMPT_INJECTION_REQUIRE_DISTINCT_MODEL=True,
        RAG_PROMPT_INJECTION_FAIL_CLOSED=True,
    )
    with app.app_context():
        for case in _load(DATASET_PATH)["cases"]:
            input_data = case["input"]
            content = input_data.get("text") or "\n".join(input_data.get("fragments", []))
            decision = assess_content_security(
                content,
                surface=ContentSecuritySurface(case["surface"]),
                metadata=input_data.get("metadata"),
            )
            expected = case["expected"]
            assert decision.status.value == expected["status"], case["id"]
            assert decision.action.value == expected["action"], case["id"]
            assert set(expected["categories"]).issubset(decision.categories), case["id"]
            if "minimumScore" in expected:
                assert decision.score >= expected["minimumScore"], case["id"]
            assert decision.classifier.get("applied") is True, case["id"]
            if content:
                assert content not in json.dumps(decision.classifier), case["id"]
