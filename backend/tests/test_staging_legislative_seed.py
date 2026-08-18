from app.models import LegislativeDocumentType
from app.staging_legislative_seed import (
    NORMATIVE_CATALOG,
    SUBJECTS,
    TARGET_CONCLUDED_PROPOSITIONS,
    TARGET_DOCUMENTS,
    TARGET_LINKED_DOCUMENTS,
    TARGET_NORMATIVE_SOURCES,
    _render_document,
)


def test_legislative_seed_targets_and_official_catalog_are_governed():
    assert TARGET_DOCUMENTS >= 100
    assert TARGET_LINKED_DOCUMENTS >= 60
    assert TARGET_CONCLUDED_PROPOSITIONS > TARGET_DOCUMENTS / 2
    assert TARGET_NORMATIVE_SOURCES == len(NORMATIVE_CATALOG) == 14
    assert len({item["key"] for item in NORMATIVE_CATALOG}) == len(NORMATIVE_CATALOG)
    assert all(item["url"].startswith("https://") for item in NORMATIVE_CATALOG)
    assert all(len(item["excerpt"]) >= 80 for item in NORMATIVE_CATALOG)
    assert all("source_type" in item and item["reference"] for item in NORMATIVE_CATALOG)


def test_legislative_seed_renders_realistic_documents_with_normative_citations():
    subject = SUBJECTS["acessibilidade urbana"]
    citations = [
        {
            "titulo": item["title"],
            "referencia": item["reference"],
        }
        for item in NORMATIVE_CATALOG
        if item["key"] in subject["sources"]
    ]
    title = subject["headline"].format(territory="Centro")
    for document_type in LegislativeDocumentType:
        content, justification = _render_document(
            document_type,
            title,
            subject,
            "Centro",
            None,
            citations,
        )
        assert len(content) >= 180
        assert "Centro" in content or document_type == LegislativeDocumentType.PROJETO_LEI
        assert "Lei Brasileira de Inclusão" in justification
        assert "evidências do cotidiano" in justification
