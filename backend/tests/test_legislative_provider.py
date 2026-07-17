import json

from app.legislative.generator import (
    LegislativeInput,
    LocalLegislativeProvider,
    OllamaLegislativeProvider,
)


def _input(sources=()):
    return LegislativeInput(
        document_type="INDICACAO",
        title="Manutenção da praça",
        requests=(
            {
                "protocolo": "GF-2026-000001",
                "titulo": "Iluminação pública",
                "descricao": "Três postes estão apagados.",
                "endereco": "Praça Central",
                "orgao": "Secretaria de Obras",
            },
        ),
        selected_facts=("Três postes estão apagados.",),
        instructions=None,
        template=None,
        normative_sources=sources,
    )


def test_local_provider_marks_missing_legal_basis_and_disables_protocol():
    result = LocalLegislativeProvider("rules-v1", "prompt-v1").generate(_input())
    assert result.content
    assert result.unsupported_passages
    assert result.legal_basis == []
    assert "PROTOCOLO_AUTOMATICO_DESABILITADO" in result.guardrails


def test_ollama_provider_ignores_model_sources_and_marks_ungrounded_law(monkeypatch):
    provider = OllamaLegislativeProvider("http://ollama:11434", "qwen", "v1", 10)
    source = {
        "titulo": "Lei Orgânica Municipal",
        "referencia": "art. 12",
        "trecho": "Compete ao Município manter os espaços públicos.",
        "validadaPeloUsuario": True,
    }
    monkeypatch.setattr(
        provider,
        "_request",
        lambda _payload: {
            "message": {
                "content": json.dumps(
                    {
                        "titulo": "Indicação para manutenção da praça",
                        "conteudo": (
                            "Com base na Lei Federal 9999, solicita-se a manutenção da praça."
                        ),
                        "justificativa": "A iluminação adequada melhora o uso do espaço público.",
                        "estruturaSugerida": ["Objeto", "Fatos", "Justificativa"],
                        "confianca": 0.9,
                        "fontesInventadas": [{"titulo": "Lei Federal 9999"}],
                    }
                )
            }
        },
    )

    result = provider.generate(_input((source,)))
    assert result.legal_basis == [
        {
            "titulo": "Lei Orgânica Municipal",
            "referencia": "art. 12",
            "trecho": "Compete ao Município manter os espaços públicos.",
            "validadaPeloUsuario": True,
        }
    ]
    assert result.unsupported_passages[0]["trecho"].startswith("Com base na Lei Federal")
    assert result.confidence == 0.82
