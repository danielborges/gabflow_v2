import json
from collections import Counter
from pathlib import Path

from app.electoral.safety import POLICY_VERSION, assess_electoral_question

DATASET_PATH = (
    Path(__file__).resolve().parents[2]
    / "docs"
    / "specs"
    / "datasets"
    / "electoral-question-adversarial-v1.json"
)


def test_electoral_question_adversarial_dataset_contract_and_policy(app):
    dataset = json.loads(DATASET_PATH.read_text(encoding="utf-8"))
    assert dataset["datasetId"] == "gabflow-electoral-question-adversarial"
    assert dataset["policyVersion"] == POLICY_VERSION
    assert len(dataset["cases"]) >= 20
    assert len({item["id"] for item in dataset["cases"]}) == len(dataset["cases"])
    categories = Counter(
        item["expectedCategory"] for item in dataset["cases"] if not item["expectedAllowed"]
    )
    assert all(count >= 2 for count in categories.values())
    assert sum(item["expectedAllowed"] for item in dataset["cases"]) >= 5

    with app.app_context():
        for case in dataset["cases"]:
            decision = assess_electoral_question(case["question"])
            assert decision.allowed is case["expectedAllowed"], case["id"]
            assert decision.category == case["expectedCategory"], case["id"]
            assert len(decision.prompt_hash) == 64
            assert case["question"] not in str(decision.audit_data())
