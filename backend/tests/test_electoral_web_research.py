import json

from app.electoral.web_research import research_electoral_context


class _Response:
    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self):
        return json.dumps(self.payload).encode("utf-8")


def test_web_research_builds_context_and_filters_unsafe_results(app, monkeypatch):
    captured = {}

    def urlopen(request, timeout):
        captured["url"] = request.full_url
        captured["timeout"] = timeout
        return _Response(
            {
                "results": [
                    {
                        "title": "Perfil público e atuação territorial",
                        "url": "https://example.org/noticia",
                        "content": "A reportagem descreve agenda pública e presença territorial da candidatura.",
                        "engine": "duckduckgo",
                    },
                    {
                        "title": "Endereço interno",
                        "url": "http://127.0.0.1/private",
                        "content": "Este resultado interno não pode ser exposto como fonte pública.",
                    },
                ]
            }
        )

    monkeypatch.setattr("app.electoral.web_research.urllib.request.urlopen", urlopen)
    with app.app_context():
        app.config.update(
            ELECTORAL_WEB_RESEARCH_ENABLED=True,
            ELECTORAL_WEB_RESEARCH_BASE_URL="http://searxng:8080",
            ELECTORAL_WEB_RESEARCH_TIMEOUT_SECONDS=25,
            ELECTORAL_WEB_RESEARCH_MAX_RESULTS=5,
        )
        sources, metadata = research_electoral_context(
            "Por que houve vantagem nesta zona?",
            {
                "candidates": [
                    {"ballot_name": "CANDIDATA A"},
                    {"ballot_name": "CANDIDATO B"},
                ],
                "items": [{"territory_name": "Zona 101"}],
            },
        )

    assert len(sources) == 1
    assert sources[0].title == "Perfil público e atuação territorial"
    assert metadata["provider"] == "SEARXNG"
    assert metadata["resultCount"] == 1
    assert "format=json" in captured["url"]
    assert captured["timeout"] == 25
