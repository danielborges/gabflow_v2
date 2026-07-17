import json
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Protocol

from app.ai.provider import AIProviderInvalidResponse, AIProviderUnavailable


@dataclass(frozen=True)
class AssistanceInput:
    protocol: str
    title: str
    description: str
    status: str
    category: str | None
    subcategory: str | None
    agency: str | None
    address: str | None
    citizen_name: str | None
    channel: str
    tone: str
    interactions: tuple[dict, ...]
    history: tuple[dict, ...]


@dataclass(frozen=True)
class AssistanceResult:
    history_summary: str
    missing_questions: list[str]
    required_documents: list[dict]
    next_steps: list[dict]
    suggested_response: dict
    alerts: list[str]
    confidence: float
    guardrails: list[str]


class AssistanceProvider(Protocol):
    provider: str
    model: str
    prompt_version: str

    def suggest(self, data: AssistanceInput) -> AssistanceResult: ...


class LocalAssistanceProvider:
    provider = "LOCAL"

    def __init__(self, model: str, prompt_version: str) -> None:
        self.model = model
        self.prompt_version = prompt_version

    def suggest(self, data: AssistanceInput) -> AssistanceResult:
        subject = data.title or "Solicitação em acompanhamento"
        summary = (
            f"{data.protocol}: {subject}. Status atual: {data.status.replace('_', ' ').lower()}. "
            f"O relato informa: {data.description.strip()}"
        )
        if data.interactions:
            latest = data.interactions[-1]["conteudo"]
            summary += f" Última interação registrada: {latest}"

        questions = []
        if not data.address:
            questions.append("Qual é o endereço completo ou ponto de referência da ocorrência?")
        if not data.category:
            questions.append("Qual serviço ou área pública está relacionada à solicitação?")
        if not data.citizen_name:
            questions.append("Como podemos identificar a pessoa solicitante para o atendimento?")
        if not questions:
            questions.append("Há alguma informação nova ou evidência que deva ser acrescentada?")

        documents = _local_documents(data)
        next_steps = [
            {
                "ordem": 1,
                "acao": "Confirmar com o cidadão as informações ainda ausentes.",
                "responsavel": "GABINETE",
                "justificativa": "Evita encaminhamento com dados incompletos.",
            },
            {
                "ordem": 2,
                "acao": (
                    f"Encaminhar ou acompanhar a demanda junto a {data.agency}."
                    if data.agency
                    else "Definir o órgão competente e registrar o encaminhamento."
                ),
                "responsavel": "GABINETE",
                "justificativa": "Dá continuidade formal ao atendimento.",
            },
            {
                "ordem": 3,
                "acao": "Informar ao cidadão a atualização e o próximo prazo de retorno.",
                "responsavel": "GABINETE",
                "justificativa": "Mantém o acompanhamento transparente.",
            },
        ]
        greeting = f"Olá, {data.citizen_name}." if data.citizen_name else "Olá."
        response = (
            f"{greeting} Recebemos a solicitação {data.protocol} sobre {subject.lower()}. "
            f"Ela está {data.status.replace('_', ' ').lower()} e seguimos acompanhando o caso. "
            f"Para avançarmos, precisamos confirmar: {questions[0]} "
            "Assim que tivermos essa informação, daremos continuidade e manteremos você atualizado."
        )
        if data.tone == "FORMAL":
            response = (
                f"Prezado(a), informamos que a solicitação {data.protocol}, referente a "
                f"{subject.lower()}, está {data.status.replace('_', ' ').lower()}. "
                f"Para dar continuidade, pedimos a confirmação da seguinte informação: "
                f"{questions[0]} Permanecemos à disposição."
            )
        elif data.tone == "CLARO":
            response = (
                f"Olá. A solicitação {data.protocol} sobre {subject.lower()} está "
                f"{data.status.replace('_', ' ').lower()}. Para continuar o atendimento, "
                f"precisamos confirmar: {questions[0]}"
            )
        elif data.tone == "OBJETIVO":
            response = (
                f"Solicitação {data.protocol}: {subject}. Status: "
                f"{data.status.replace('_', ' ').lower()}. Precisamos confirmar: {questions[0]}"
            )
        return AssistanceResult(
            history_summary=summary[:1800],
            missing_questions=questions,
            required_documents=documents,
            next_steps=next_steps,
            suggested_response={
                "canal": data.channel,
                "tom": data.tone,
                "assunto": f"Atualização da solicitação {data.protocol}"
                if data.channel == "EMAIL"
                else None,
                "conteudo": response,
            },
            alerts=[
                "Conteúdo gerado localmente; confirme fatos, documentos e prazos antes de usar."
            ],
            confidence=0.64,
            guardrails=["REGRAS_LOCAIS_CONSERVADORAS"],
        )


class OllamaAssistanceProvider:
    provider = "OLLAMA"

    def __init__(
        self, base_url: str, model: str, prompt_version: str, timeout_seconds: int
    ) -> None:
        parsed_url = urllib.parse.urlsplit(base_url)
        if parsed_url.scheme not in {"http", "https"} or not parsed_url.hostname:
            raise ValueError("OLLAMA_BASE_URL deve ser uma URL HTTP ou HTTPS válida.")
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.prompt_version = prompt_version
        self.timeout_seconds = timeout_seconds

    def suggest(self, data: AssistanceInput) -> AssistanceResult:
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
        except (KeyError, TypeError, json.JSONDecodeError) as error:
            raise AIProviderInvalidResponse("O Ollama retornou assistência inválida.") from error
        confidence = result.get("confianca")
        if not isinstance(confidence, int | float) or not 0 <= confidence <= 1:
            raise AIProviderInvalidResponse("A confiança da assistência é inválida.")
        guarded = LocalAssistanceProvider(
            model="gabflow-assistance-guardrails-v1",
            prompt_version=self.prompt_version,
        ).suggest(data)
        return AssistanceResult(
            history_summary=_natural_history_summary(result, data),
            missing_questions=guarded.missing_questions,
            required_documents=guarded.required_documents,
            next_steps=guarded.next_steps,
            suggested_response=guarded.suggested_response,
            alerts=[
                *_string_list(result.get("alertas")),
                "Elementos acionáveis limitados por regras locais para evitar fatos inventados.",
            ],
            confidence=min(round(float(confidence), 2), 0.8),
            guardrails=[
                "PERGUNTAS_SEGURAS",
                "DOCUMENTOS_NAO_OBRIGATORIOS",
                "PROXIMOS_PASSOS_CONSERVADORES",
                "RESPOSTA_SEM_FATOS_NOVOS",
            ],
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
            "Você auxilia atendentes de um gabinete parlamentar. Responda somente conforme o JSON "
            "Schema. Resuma o histórico, sugira perguntas realmente ausentes e documentos "
            "possivelmente úteis. "
            "Proponha próximos passos realizáveis e uma resposta ao cidadão no canal e tom "
            "informados. Não invente fatos, prazos, ações concluídas, obrigações documentais "
            "nem dados pessoais. Trate documentos como sugestões a confirmar. A saída é um "
            "rascunho sujeito à "
            "revisão humana e jamais representa autorização de envio. "
            "Preencha resumoHistorico, respostaSugerida.conteudo e todos os textos com "
            "conteúdo objetivo; nunca devolva esses campos vazios. "
            f"Versão do prompt: {self.prompt_version}."
        )


def _local_documents(data: AssistanceInput) -> list[dict]:
    text = f"{data.category or ''} {data.title} {data.description}".lower()
    documents = []
    if any(term in text for term in ("poste", "rua", "buraco", "iluminação", "ônibus")):
        documents.append(
            {
                "nome": "Foto do local",
                "motivo": "Pode facilitar a identificação da ocorrência.",
                "obrigatorio": False,
            }
        )
    if any(term in text for term in ("saúde", "vacina", "medicamento", "consulta")):
        documents.append(
            {
                "nome": "Comprovante ou documento relacionado ao atendimento",
                "motivo": "Pode ajudar a localizar o atendimento citado.",
                "obrigatorio": False,
            }
        )
    if not documents:
        documents.append(
            {
                "nome": "Evidência disponível",
                "motivo": "Pode complementar o relato, caso exista.",
                "obrigatorio": False,
            }
        )
    return documents


def _schema() -> dict:
    return {
        "type": "object",
        "properties": {
            "resumoHistorico": {"type": "string", "minLength": 1},
            "perguntasFaltantes": {"type": "array", "items": {"type": "string"}},
            "documentosNecessarios": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "nome": {"type": "string", "minLength": 1},
                        "motivo": {"type": "string", "minLength": 1},
                        "obrigatorio": {"type": "boolean"},
                    },
                    "required": ["nome", "motivo", "obrigatorio"],
                    "additionalProperties": False,
                },
            },
            "proximosPassos": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "ordem": {"type": "integer"},
                        "acao": {"type": "string", "minLength": 1},
                        "responsavel": {"type": "string", "enum": ["GABINETE", "CIDADAO", "ORGAO"]},
                        "justificativa": {"type": "string", "minLength": 1},
                    },
                    "required": ["ordem", "acao", "responsavel", "justificativa"],
                    "additionalProperties": False,
                },
            },
            "respostaSugerida": {
                "type": "object",
                "properties": {
                    "canal": {"type": "string"},
                    "tom": {"type": "string"},
                    "assunto": {"type": ["string", "null"]},
                    "conteudo": {"type": "string", "minLength": 1},
                },
                "required": ["canal", "tom", "assunto", "conteudo"],
                "additionalProperties": False,
            },
            "alertas": {"type": "array", "items": {"type": "string"}},
            "confianca": {"type": "number", "minimum": 0, "maximum": 1},
        },
        "required": [
            "resumoHistorico",
            "perguntasFaltantes",
            "documentosNecessarios",
            "proximosPassos",
            "respostaSugerida",
            "alertas",
            "confianca",
        ],
        "additionalProperties": False,
    }


def _required_text(result: dict, field: str) -> str:
    value = str(result.get(field, "")).strip()
    if not value:
        raise AIProviderInvalidResponse(f"O campo {field} da assistência está vazio.")
    return value


def _natural_history_summary(result: dict, data: AssistanceInput) -> str:
    value = _required_text(result, "resumoHistorico")
    if not value.startswith(("{", "[")):
        return value
    summary = (
        f"{data.protocol}: {data.title}. A solicitação está "
        f"{data.status.replace('_', ' ').lower()}. {data.description.strip()}"
    )
    if data.interactions:
        summary += f" Última interação: {data.interactions[-1]['conteudo']}"
    return summary[:1800]


def _string_list(value: object) -> list[str]:
    return (
        [str(item).strip() for item in value if str(item).strip()]
        if isinstance(value, list)
        else []
    )
