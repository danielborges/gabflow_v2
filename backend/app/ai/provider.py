import json
import re
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class TriageCategory:
    id: str
    name: str


@dataclass(frozen=True)
class TriageInput:
    title: str
    description: str
    categories: tuple[TriageCategory, ...]


@dataclass(frozen=True)
class TriageResult:
    category_id: str | None
    category: str | None
    subcategory: str | None
    priority: str
    impact: str
    urgency: str
    confidence: float
    summary: str
    rationale: str
    emergency: bool
    emergency_guidance: str | None
    entities: dict


class TriageProvider(Protocol):
    provider: str
    model: str
    prompt_version: str

    def classify(self, data: TriageInput) -> TriageResult: ...


class AIProviderError(RuntimeError):
    pass


class AIProviderUnavailable(AIProviderError):
    pass


class AIProviderInvalidResponse(AIProviderError):
    pass


class LocalTriageProvider:
    provider = "LOCAL"

    CATEGORY_KEYWORDS = {
        "iluminacao": ("poste", "lâmpada", "lampada", "iluminação", "iluminacao", "escuro"),
        "saude": ("saúde", "saude", "vacina", "médico", "medico", "hospital", "posto"),
        "mobilidade": ("ônibus", "onibus", "trânsito", "transito", "rua", "buraco", "calçada"),
    }
    EMERGENCY_TERMS = (
        "risco de vida",
        "ameaça de morte",
        "ameaca de morte",
        "incêndio",
        "incendio",
        "desabamento",
        "sangramento",
        "inconsciente",
        "arma",
    )
    ADDRESS_PATTERN = re.compile(
        r"\b(?:rua|avenida|av\.|travessa|praça|praca)\s+[^,.;\n]{3,80}",
        re.IGNORECASE,
    )

    def __init__(self, model: str, prompt_version: str) -> None:
        self.model = model
        self.prompt_version = prompt_version

    def classify(self, data: TriageInput) -> TriageResult:
        text = f"{data.title}\n{data.description}".strip()
        normalized = _normalize(text)
        category_id, category, score = self._category(data.categories, normalized)
        emergency = any(_normalize(term) in normalized for term in self.EMERGENCY_TERMS)
        urgency = "CRITICO" if emergency else ("ALTO" if score >= 2 else "MEDIO")
        impact = "ALTO" if emergency or _contains_many_people(normalized) else "MEDIO"
        priority = "CRITICA" if emergency else ("ALTA" if urgency == "ALTO" else "MEDIA")
        confidence = min(0.96, 0.48 + score * 0.12 + (0.12 if category else 0))
        address = self.ADDRESS_PATTERN.search(text)
        entities = {"endereco": address.group(0).strip()} if address else {}
        summary = _summary(data.description)
        rationale = (
            f"A sugestão considera {score} indicador(es) temático(s)"
            + (f" associados à categoria {category}." if category else ".")
        )
        guidance = (
            "Há indício de risco imediato. Oriente o cidadão a acionar o serviço de "
            "emergência competente; o gabinete não substitui esse atendimento."
            if emergency
            else None
        )
        return TriageResult(
            category_id=category_id,
            category=category,
            subcategory=category,
            priority=priority,
            impact=impact,
            urgency=urgency,
            confidence=round(confidence, 2),
            summary=summary,
            rationale=rationale,
            emergency=emergency,
            emergency_guidance=guidance,
            entities=entities,
        )

    def _category(
        self,
        categories: tuple[TriageCategory, ...],
        normalized_text: str,
    ) -> tuple[str | None, str | None, int]:
        best = (None, None, 0)
        for category in categories:
            normalized_name = _normalize(category.name)
            keywords = set(normalized_name.split())
            for key, values in self.CATEGORY_KEYWORDS.items():
                if key in normalized_name:
                    keywords.update(_normalize(value) for value in values)
            score = sum(keyword in normalized_text for keyword in keywords if len(keyword) > 2)
            if score > best[2]:
                best = (category.id, category.name, score)
        return best


class OllamaTriageProvider:
    provider = "OLLAMA"
    LEVELS = ("BAIXO", "MEDIO", "ALTO", "CRITICO")
    PRIORITIES = ("BAIXA", "MEDIA", "ALTA", "CRITICA")

    def __init__(
        self,
        base_url: str,
        model: str,
        prompt_version: str,
        timeout_seconds: int,
    ) -> None:
        parsed_url = urllib.parse.urlsplit(base_url)
        if parsed_url.scheme not in {"http", "https"} or not parsed_url.hostname:
            raise ValueError("OLLAMA_BASE_URL deve ser uma URL HTTP ou HTTPS válida.")
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.prompt_version = prompt_version
        self.timeout_seconds = timeout_seconds

    def classify(self, data: TriageInput) -> TriageResult:
        category_ids = {category.id for category in data.categories}
        response = self._request(
            {
                "model": self.model,
                "stream": False,
                "format": self._schema(data.categories),
                "options": {"temperature": 0},
                "messages": [
                    {"role": "system", "content": self._system_prompt(data.categories)},
                    {
                        "role": "user",
                        "content": json.dumps(
                            {"titulo": data.title, "descricao": data.description},
                            ensure_ascii=False,
                        ),
                    },
                ],
            }
        )
        try:
            content = response["message"]["content"]
            result = json.loads(content)
        except (KeyError, TypeError, json.JSONDecodeError) as error:
            raise AIProviderInvalidResponse("O Ollama retornou uma resposta inválida.") from error

        category_id = result.get("categoriaId") or None
        if category_id is not None and category_id not in category_ids:
            raise AIProviderInvalidResponse("O Ollama sugeriu uma categoria inexistente.")
        category = next(
            (item.name for item in data.categories if item.id == category_id),
            None,
        )
        confidence = result.get("confianca")
        if not isinstance(confidence, int | float) or not 0 <= confidence <= 1:
            raise AIProviderInvalidResponse("A confiança retornada pelo Ollama é inválida.")

        return TriageResult(
            category_id=category_id,
            category=category,
            subcategory=_optional_text(result.get("subcategoria")),
            priority=_enum_value(result, "prioridadeSugerida", self.PRIORITIES),
            impact=_enum_value(result, "impacto", self.LEVELS),
            urgency=_enum_value(result, "urgencia", self.LEVELS),
            confidence=round(float(confidence), 2),
            summary=_required_text(result, "resumo"),
            rationale=_required_text(result, "justificativa"),
            emergency=bool(result.get("emergencia")),
            emergency_guidance=_optional_text(result.get("orientacaoEmergencia")),
            entities=result.get("entidades") if isinstance(result.get("entidades"), dict) else {},
        )

    def _request(self, payload: dict) -> dict:
        request = urllib.request.Request(  # noqa: S310 - URL validated in __init__
            f"{self.base_url}/api/chat",
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(  # noqa: S310 - URL validated in __init__
                request,
                timeout=self.timeout_seconds,
            ) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as error:
            body = error.read().decode("utf-8", errors="replace")
            raise AIProviderUnavailable(
                f"Ollama respondeu com HTTP {error.code}: {body[:240]}"
            ) from error
        except (urllib.error.URLError, TimeoutError) as error:
            raise AIProviderUnavailable("Ollama indisponível ou excedeu o tempo limite.") from error
        except json.JSONDecodeError as error:
            raise AIProviderInvalidResponse("Ollama retornou JSON inválido.") from error

    def _system_prompt(self, categories: tuple[TriageCategory, ...]) -> str:
        category_list = [
            {"id": category.id, "nome": category.name}
            for category in categories
        ]
        return (
            "Você realiza triagem assistida de solicitações de um gabinete parlamentar. "
            "Responda somente conforme o JSON Schema informado. Use exclusivamente uma categoria "
            "da lista; use null quando não houver evidência suficiente. Não invente fatos. "
            "Considere emergência somente quando houver possível risco imediato à vida, "
            "integridade física ou segurança. A revisão humana é obrigatória. "
            f"Versão do prompt: {self.prompt_version}. "
            f"Categorias: {json.dumps(category_list, ensure_ascii=False)}"
        )

    def _schema(self, categories: tuple[TriageCategory, ...]) -> dict:
        category_ids = [category.id for category in categories]
        return {
            "type": "object",
            "properties": {
                "categoriaId": {"type": ["string", "null"], "enum": [*category_ids, None]},
                "subcategoria": {"type": ["string", "null"]},
                "prioridadeSugerida": {"type": "string", "enum": list(self.PRIORITIES)},
                "impacto": {"type": "string", "enum": list(self.LEVELS)},
                "urgencia": {"type": "string", "enum": list(self.LEVELS)},
                "confianca": {"type": "number", "minimum": 0, "maximum": 1},
                "resumo": {"type": "string"},
                "justificativa": {"type": "string"},
                "emergencia": {"type": "boolean"},
                "orientacaoEmergencia": {"type": ["string", "null"]},
                "entidades": {"type": "object"},
            },
            "required": [
                "categoriaId",
                "subcategoria",
                "prioridadeSugerida",
                "impacto",
                "urgencia",
                "confianca",
                "resumo",
                "justificativa",
                "emergencia",
                "orientacaoEmergencia",
                "entidades",
            ],
            "additionalProperties": False,
        }


def _enum_value(result: dict, field: str, allowed: tuple[str, ...]) -> str:
    value = str(result.get(field, "")).upper()
    if value not in allowed:
        raise AIProviderInvalidResponse(f"O campo {field} retornado pelo Ollama é inválido.")
    return value


def _required_text(result: dict, field: str) -> str:
    value = str(result.get(field, "")).strip()
    if not value:
        raise AIProviderInvalidResponse(f"O campo {field} retornado pelo Ollama está vazio.")
    return value


def _optional_text(value: object) -> str | None:
    text = str(value).strip() if value is not None else ""
    return text or None


def _normalize(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", value.lower())
    return "".join(character for character in decomposed if not unicodedata.combining(character))


def _contains_many_people(text: str) -> bool:
    return any(term in text for term in ("moradores", "comunidade", "bairro", "escola", "familias"))


def _summary(value: str, maximum: int = 240) -> str:
    compact = " ".join(value.split())
    if len(compact) <= maximum:
        return compact
    return compact[: maximum - 1].rstrip() + "…"
