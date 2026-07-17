import json
import re
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Protocol

from app.ai.provider import AIProviderInvalidResponse, AIProviderUnavailable


@dataclass(frozen=True)
class LegislativeInput:
    document_type: str
    title: str
    requests: tuple[dict, ...]
    selected_facts: tuple[str, ...]
    instructions: str | None
    template: str | None
    normative_sources: tuple[dict, ...]


@dataclass(frozen=True)
class LegislativeResult:
    title: str
    content: str
    justification: str
    legal_basis: list[dict]
    sources: list[dict]
    unsupported_passages: list[dict]
    suggested_structure: list[str]
    confidence: float
    guardrails: list[str]


class LegislativeProvider(Protocol):
    provider: str
    model: str
    prompt_version: str

    def generate(self, data: LegislativeInput) -> LegislativeResult: ...


class LocalLegislativeProvider:
    provider = "LOCAL"

    def __init__(self, model: str, prompt_version: str) -> None:
        self.model = model
        self.prompt_version = prompt_version

    def generate(self, data: LegislativeInput) -> LegislativeResult:
        facts = list(data.selected_facts) or [
            request["descricao"] for request in data.requests if request.get("descricao")
        ]
        location = next(
            (request.get("endereco") for request in data.requests if request.get("endereco")),
            None,
        )
        structure = _structure(data.document_type)
        subject = data.title.strip() or _default_title(data.document_type, data.requests)
        fact_text = "\n".join(f"- {fact}" for fact in facts[:12])
        destination = next(
            (request.get("orgao") for request in data.requests if request.get("orgao")),
            "órgão competente",
        )
        opening = _opening(data.document_type, subject, destination)
        content = f"{opening}\n\nFATOS CONSIDERADOS\n{fact_text}"
        if location:
            content += f"\n- Local informado: {location}"
        content += (
            "\n\nPROVIDÊNCIA PROPOSTA\n"
            "Solicita-se a análise dos fatos relatados e a adoção das providências cabíveis, "
            "com posterior comunicação ao gabinete sobre as medidas adotadas."
        )
        if data.template:
            content = f"ESTRUTURA DO TEMPLATE\n{data.template.strip()}\n\n{content}"
        justification = (
            "A proposta decorre das solicitações relacionadas e dos fatos selecionados pelo "
            "usuário. O texto deve ser conferido quanto à competência, atualidade e adequação "
            "jurídica antes da aprovação."
        )
        legal_basis = [_normalized_source(source) for source in data.normative_sources]
        unsupported = (
            []
            if legal_basis
            else [
                {
                    "trecho": "Fundamentação normativa",
                    "motivo": "Nenhuma fonte normativa foi informada ou validada.",
                    "severidade": "ALTA",
                }
            ]
        )
        return LegislativeResult(
            title=subject[:240],
            content=content[:30000],
            justification=justification,
            legal_basis=legal_basis,
            sources=legal_basis,
            unsupported_passages=unsupported,
            suggested_structure=structure,
            confidence=0.58 if legal_basis else 0.42,
            guardrails=[
                "SOMENTE_FATOS_SELECIONADOS",
                "FONTES_NORMATIVAS_NAO_INVENTADAS",
                "RASCUNHO_COM_REVISAO_HUMANA",
                "PROTOCOLO_AUTOMATICO_DESABILITADO",
            ],
        )


class OllamaLegislativeProvider:
    provider = "OLLAMA"

    def __init__(
        self, base_url: str, model: str, prompt_version: str, timeout_seconds: int
    ) -> None:
        parsed = urllib.parse.urlsplit(base_url)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            raise ValueError("OLLAMA_BASE_URL deve ser uma URL HTTP ou HTTPS válida.")
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.prompt_version = prompt_version
        self.timeout_seconds = timeout_seconds

    def generate(self, data: LegislativeInput) -> LegislativeResult:
        response = self._request(
            {
                "model": self.model,
                "stream": False,
                "format": _schema(),
                "options": {"temperature": 0},
                "messages": [
                    {"role": "system", "content": self._system_prompt()},
                    {"role": "user", "content": json.dumps(data.__dict__, ensure_ascii=False)},
                ],
            }
        )
        try:
            result = json.loads(response["message"]["content"])
            title = _required_text(result, "titulo")
            content = _required_text(result, "conteudo")
            justification = _required_text(result, "justificativa")
            confidence = float(result["confianca"])
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
            raise AIProviderInvalidResponse("O Ollama retornou uma minuta inválida.") from error
        if not 0 <= confidence <= 1:
            raise AIProviderInvalidResponse("A confiança da minuta é inválida.")

        allowed_sources = [_normalized_source(source) for source in data.normative_sources]
        unsupported = _unsupported_passages(content, allowed_sources)
        if not allowed_sources:
            unsupported.insert(
                0,
                {
                    "trecho": "Fundamentação normativa",
                    "motivo": "Nenhuma fonte normativa foi fornecida ao modelo.",
                    "severidade": "ALTA",
                },
            )
        return LegislativeResult(
            title=title[:240],
            content=content[:30000],
            justification=justification[:10000],
            legal_basis=allowed_sources,
            sources=allowed_sources,
            unsupported_passages=unsupported,
            suggested_structure=[
                str(item)[:160] for item in result.get("estruturaSugerida", [])[:12]
            ],
            confidence=min(round(confidence, 2), 0.82),
            guardrails=[
                "FONTES_RESTRITAS_AO_CONTEXTO",
                "TRECHOS_SEM_FONTE_MARCADOS",
                "RASCUNHO_COM_REVISAO_HUMANA",
                "PROTOCOLO_AUTOMATICO_DESABILITADO",
            ],
        )

    def _request(self, payload: dict) -> dict:
        request = urllib.request.Request(  # noqa: S310 - URL validated above
            f"{self.base_url}/api/chat",
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(  # noqa: S310 - URL validated above
                request, timeout=self.timeout_seconds
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

    def _system_prompt(self) -> str:
        return (
            "Você auxilia na redação legislativa municipal. Produza somente um rascunho no JSON "
            "Schema informado, baseado exclusivamente nos fatos selecionados e solicitações. "
            "Nunca invente lei, artigo, competência, protocolo, autoridade, prazo ou fato. Use "
            "fundamentação normativa apenas quando ela estiver em fontesNormativas. Quando não "
            "houver fonte, redija sem citação legal e deixe a fundamentação pendente. O documento "
            "exige revisão e aprovação humanas e jamais pode ser protocolado automaticamente. "
            f"Versão do prompt: {self.prompt_version}."
        )


def _schema() -> dict:
    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["titulo", "conteudo", "justificativa", "estruturaSugerida", "confianca"],
        "properties": {
            "titulo": {"type": "string", "minLength": 4},
            "conteudo": {"type": "string", "minLength": 40},
            "justificativa": {"type": "string", "minLength": 20},
            "estruturaSugerida": {"type": "array", "items": {"type": "string"}},
            "confianca": {"type": "number", "minimum": 0, "maximum": 1},
        },
    }


def _required_text(result: dict, field: str) -> str:
    value = result.get(field)
    if not isinstance(value, str) or not value.strip():
        raise AIProviderInvalidResponse(f"Campo obrigatório ausente na minuta: {field}.")
    return value.strip()


def _normalized_source(source: dict) -> dict:
    return {
        "titulo": str(source.get("titulo", "Fonte informada")).strip()[:240],
        "referencia": str(source.get("referencia", "")).strip()[:300] or None,
        "trecho": str(source.get("trecho", "")).strip()[:3000] or None,
        "validadaPeloUsuario": bool(source.get("validadaPeloUsuario", False)),
    }


def _unsupported_passages(content: str, sources: list[dict]) -> list[dict]:
    references = " ".join(
        f"{item.get('titulo') or ''} {item.get('referencia') or ''}" for item in sources
    ).casefold()
    markers = re.compile(
        r"\b(lei|decreto|resolu[cç][aã]o|constitui[cç][aã]o|art(?:igo|\.)?)\b", re.I
    )
    unsupported = []
    for paragraph in (part.strip() for part in content.splitlines() if part.strip()):
        if markers.search(paragraph) and not any(
            token in paragraph.casefold() for token in references.split() if len(token) > 4
        ):
            unsupported.append(
                {
                    "trecho": paragraph[:500],
                    "motivo": "Referência normativa não encontrada nas fontes fornecidas.",
                    "severidade": "ALTA",
                }
            )
    return unsupported[:20]


def _structure(document_type: str) -> list[str]:
    structures = {
        "INDICACAO": ["Destinatário", "Objeto", "Fatos", "Providência indicada", "Justificativa"],
        "REQUERIMENTO": ["Destinatário", "Objeto", "Pedidos", "Justificativa"],
        "OFICIO": ["Destinatário", "Assunto", "Contexto", "Solicitação", "Fecho"],
        "MOCAO": ["Objeto", "Homenageado ou fato", "Justificativa", "Deliberação"],
        "PEDIDO_INFORMACAO": ["Destinatário", "Contexto", "Perguntas objetivas", "Justificativa"],
        "PROJETO_LEI": ["Ementa", "Dispositivos", "Cláusula de vigência", "Justificativa"],
    }
    return structures.get(document_type, ["Objeto", "Fatos", "Providência", "Justificativa"])


def _default_title(document_type: str, requests: tuple[dict, ...]) -> str:
    label = document_type.replace("_", " ").title()
    subject = requests[0].get("titulo") if requests else "demanda selecionada"
    return f"{label} - {subject or 'demanda selecionada'}"


def _opening(document_type: str, subject: str, destination: str) -> str:
    if document_type == "OFICIO":
        return f"OFÍCIO\nAssunto: {subject}\nAo(À) {destination},"
    if document_type == "PEDIDO_INFORMACAO":
        return f"PEDIDO DE INFORMAÇÃO\nObjeto: {subject}\nDestinatário: {destination}"
    return f"{document_type.replace('_', ' ')}\nObjeto: {subject}\nDestinatário: {destination}"
