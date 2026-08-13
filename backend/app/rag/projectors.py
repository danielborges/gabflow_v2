import re
import uuid
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date
from enum import StrEnum
from types import MappingProxyType
from typing import Protocol

from app.models import RagDocumentAccess

_IDENTIFIER_PATTERN = re.compile(r"^[A-Z][A-Z0-9_]{1,79}$")
_VERSION_PATTERN = re.compile(r"^[1-9]\d*\.[0-9]+\.[0-9]+$")


class ProjectorAction(StrEnum):
    CREATE = "CREATE"
    UPDATE = "UPDATE"
    CANCEL = "CANCEL"
    DELETE = "DELETE"
    ANONYMIZE = "ANONYMIZE"
    RETENTION_EXPIRED = "RETENTION_EXPIRED"
    RECONCILE = "RECONCILE"


@dataclass(frozen=True)
class Projection:
    eligible: bool
    reason: str | None
    title: str
    document_type: str
    purpose: str
    legal_basis: str
    access_level: RagDocumentAccess
    retention_until: date | None
    content: str
    valid_from: date | None = None
    valid_until: date | None = None
    source_url: str | None = None
    agency: str | None = None


@dataclass(frozen=True)
class ProjectorDefinition:
    module: str
    entity_type: str
    version: str
    owner: str
    supported_actions: frozenset[ProjectorAction]
    field_allowlist: frozenset[str]
    purpose: str
    default_legal_basis: str
    access_level: RagDocumentAccess
    retention_data_type: str
    quarantine_policy: str
    purge_policy: str

    def __post_init__(self) -> None:
        for name, value in (
            ("module", self.module),
            ("entity_type", self.entity_type),
            ("purpose", self.purpose),
            ("retention_data_type", self.retention_data_type),
        ):
            if not _IDENTIFIER_PATTERN.fullmatch(value):
                raise ValueError(f"{name} deve ser um identificador canônico em maiúsculas.")
        if not _VERSION_PATTERN.fullmatch(self.version):
            raise ValueError("version deve seguir o formato semântico MAJOR.MINOR.PATCH.")
        if not self.owner.strip():
            raise ValueError("owner é obrigatório.")
        if not self.supported_actions:
            raise ValueError("supported_actions não pode ser vazio.")
        if not self.field_allowlist or any(not field.strip() for field in self.field_allowlist):
            raise ValueError("field_allowlist deve declarar campos permitidos.")
        for name, value in (
            ("default_legal_basis", self.default_legal_basis),
            ("quarantine_policy", self.quarantine_policy),
            ("purge_policy", self.purge_policy),
        ):
            if not value.strip():
                raise ValueError(f"{name} é obrigatório.")


class OperationalMemoryProjector(Protocol):
    definition: ProjectorDefinition

    def project(self, tenant_id: uuid.UUID, entity_id: uuid.UUID) -> Projection: ...

    def created_by(self, tenant_id: uuid.UUID, entity_id: uuid.UUID) -> uuid.UUID: ...

    def entity_ids(self, tenant_id: uuid.UUID) -> Iterable[uuid.UUID]: ...


class ProjectorRegistry:
    def __init__(self) -> None:
        self._by_entity_type: dict[str, OperationalMemoryProjector] = {}
        self._by_module: dict[str, dict[str, OperationalMemoryProjector]] = {}

    def register(
        self, projector: OperationalMemoryProjector
    ) -> OperationalMemoryProjector:
        definition = projector.definition
        if definition.entity_type in self._by_entity_type:
            raise ValueError(
                f"Projetor já registrado para {definition.entity_type}."
            )
        self._by_entity_type[definition.entity_type] = projector
        self._by_module.setdefault(definition.module, {})[
            definition.entity_type
        ] = projector
        return projector

    def require(
        self,
        entity_type: str,
        action: ProjectorAction | None = None,
    ) -> OperationalMemoryProjector:
        projector = self._by_entity_type.get(entity_type)
        if projector is None:
            raise ValueError(
                f"Tipo de entidade operacional sem projetor registrado: {entity_type}."
            )
        if action is not None and action not in projector.definition.supported_actions:
            raise ValueError(
                f"Ação {action.value} não suportada pelo projetor {entity_type}."
            )
        return projector

    def project(
        self,
        tenant_id: uuid.UUID,
        entity_type: str,
        entity_id: uuid.UUID,
    ) -> Projection:
        projector = self.require(entity_type)
        projection = projector.project(tenant_id, entity_id)
        self._validate_projection(projector.definition, projection)
        return projection

    def for_module(self, module: str) -> tuple[OperationalMemoryProjector, ...]:
        return tuple(self._by_module.get(module, {}).values())

    def all(self) -> tuple[OperationalMemoryProjector, ...]:
        return tuple(self._by_entity_type.values())

    @property
    def definitions(self):
        return MappingProxyType(
            {
                entity_type: projector.definition
                for entity_type, projector in self._by_entity_type.items()
            }
        )

    @staticmethod
    def _validate_projection(
        definition: ProjectorDefinition, projection: Projection
    ) -> None:
        if not isinstance(projection, Projection):
            raise TypeError(
                f"Projetor {definition.entity_type} retornou um contrato inválido."
            )
        if projection.purpose != definition.purpose:
            raise ValueError(
                f"Projetor {definition.entity_type} alterou a finalidade registrada."
            )
        if projection.access_level != definition.access_level:
            raise ValueError(
                f"Projetor {definition.entity_type} alterou a ACL registrada."
            )
        if projection.eligible and not projection.content.strip():
            raise ValueError(
                f"Projetor {definition.entity_type} produziu conteúdo elegível vazio."
            )
        if not projection.eligible and projection.content:
            raise ValueError(
                f"Projetor {definition.entity_type} expôs conteúdo inelegível."
            )
