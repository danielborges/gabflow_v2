import uuid
from dataclasses import replace

import pytest

from app.models import RagDocumentAccess
from app.rag.operational_memory import (
    AGENDA_EVENT_ENTITY,
    AUDIO_TRANSCRIPTION_ENTITY,
    DOCUMENT_OCR_ENTITY,
    LEGISLATIVE_DRAFT_ENTITY,
    LEGISLATIVE_TRAMITATION_ENTITY,
    OVERSIGHT_ACTION_ENTITY,
    REQUEST_FORWARDING_ENTITY,
    SERVICE_REQUEST_ENTITY,
    THEMATIC_MEMORY_ENTITY,
    enqueue_operational_memory,
    projector_registry,
)
from app.rag.projectors import (
    Projection,
    ProjectorAction,
    ProjectorDefinition,
    ProjectorRegistry,
)


class FakeProjector:
    definition = ProjectorDefinition(
        module="TESTES",
        entity_type="FAKE_ENTITY",
        version="1.2.0",
        owner="Testes automatizados",
        supported_actions=frozenset({ProjectorAction.CREATE, ProjectorAction.UPDATE}),
        field_allowlist=frozenset({"title", "content"}),
        purpose="TESTE_CONTROLADO",
        default_legal_basis="TESTE_AUTOMATIZADO",
        access_level=RagDocumentAccess.INTERNO,
        retention_data_type="TESTE",
        quarantine_policy="REJECT",
        purge_policy="PURGE",
    )

    def __init__(self, projection: Projection | None = None):
        self._projection = projection or Projection(
            eligible=True,
            reason=None,
            title="Fonte de teste",
            document_type="MEMORIA_TESTE",
            purpose=self.definition.purpose,
            legal_basis=self.definition.default_legal_basis,
            access_level=self.definition.access_level,
            retention_until=None,
            content="Conteúdo canônico de teste.",
        )

    def project(self, tenant_id, entity_id):
        return self._projection

    def created_by(self, tenant_id, entity_id):
        return uuid.uuid4()

    def entity_ids(self, tenant_id):
        return ()


def test_builtin_projectors_expose_versioned_governance_contract():
    request = projector_registry.require(SERVICE_REQUEST_ENTITY)
    forwarding = projector_registry.require(REQUEST_FORWARDING_ENTITY)
    ocr = projector_registry.require(DOCUMENT_OCR_ENTITY)
    transcription = projector_registry.require(AUDIO_TRANSCRIPTION_ENTITY)
    draft = projector_registry.require(LEGISLATIVE_DRAFT_ENTITY)
    tramitation = projector_registry.require(LEGISLATIVE_TRAMITATION_ENTITY)
    agenda = projector_registry.require(AGENDA_EVENT_ENTITY)
    oversight = projector_registry.require(OVERSIGHT_ACTION_ENTITY)
    thematic = projector_registry.require(THEMATIC_MEMORY_ENTITY)

    assert request.definition.module == "SOLICITACOES"
    assert request.definition.version == "1.0.0"
    assert "description" in request.definition.field_allowlist
    assert "address" not in request.definition.field_allowlist
    assert ProjectorAction.CANCEL in request.definition.supported_actions

    assert forwarding.definition.module == "SOLICITACOES"
    assert forwarding.definition.version == "1.0.0"
    assert "response" in forwarding.definition.field_allowlist
    assert "agency.email" not in forwarding.definition.field_allowlist
    assert ProjectorAction.ANONYMIZE in forwarding.definition.supported_actions
    assert projector_registry.for_module("SOLICITACOES") == (
        request,
        forwarding,
        ocr,
        transcription,
    )

    assert draft.definition.module == "LEGISLATIVO"
    assert draft.definition.version == "1.0.0"
    assert "content" in draft.definition.field_allowlist
    assert projector_registry.for_module("LEGISLATIVO") == (draft, tramitation)
    assert agenda.definition.field_allowlist.isdisjoint({"participants", "photos", "citizen"})
    assert oversight.definition.field_allowlist.isdisjoint(
        {"responsible_parties", "photos", "location"}
    )
    assert thematic.definition.module == "ANALITICA"

    with pytest.raises(TypeError):
        projector_registry.definitions[SERVICE_REQUEST_ENTITY] = draft.definition


def test_registry_rejects_duplicates_and_unsupported_actions():
    registry = ProjectorRegistry()
    projector = FakeProjector()
    registry.register(projector)

    assert registry.require("FAKE_ENTITY", ProjectorAction.CREATE) is projector
    with pytest.raises(ValueError, match="Ação DELETE não suportada"):
        registry.require("FAKE_ENTITY", ProjectorAction.DELETE)
    with pytest.raises(ValueError, match="já registrado"):
        registry.register(FakeProjector())


def test_registry_validates_projection_against_registered_policy():
    invalid = Projection(
        eligible=True,
        reason=None,
        title="Fonte inválida",
        document_type="MEMORIA_TESTE",
        purpose="FINALIDADE_DIVERGENTE",
        legal_basis="TESTE_AUTOMATIZADO",
        access_level=RagDocumentAccess.INTERNO,
        retention_until=None,
        content="Conteúdo.",
    )
    registry = ProjectorRegistry()
    registry.register(FakeProjector(invalid))

    with pytest.raises(ValueError, match="alterou a finalidade"):
        registry.project(uuid.uuid4(), "FAKE_ENTITY", uuid.uuid4())


def test_projector_definition_requires_allowlist_and_semantic_version():
    with pytest.raises(ValueError, match="version"):
        replace(FakeProjector.definition, version="v1")
    with pytest.raises(ValueError, match="field_allowlist"):
        replace(FakeProjector.definition, field_allowlist=frozenset())


def test_unregistered_entity_cannot_enter_operational_memory(app):
    with app.app_context():
        with pytest.raises(ValueError, match="sem projetor registrado"):
            enqueue_operational_memory(uuid.uuid4(), "UNREGISTERED_ENTITY", uuid.uuid4())
