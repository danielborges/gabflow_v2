"""Execute and record the role-based business acceptance flow for Gate D."""

from __future__ import annotations

import argparse
import http.cookiejar
import json
import urllib.error
import urllib.parse
import urllib.request
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any


def parse_env(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


class ApiSession:
    def __init__(self, base_url: str) -> None:
        self.base_url = base_url
        self.cookies = http.cookiejar.CookieJar()
        self.opener = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(self.cookies)
        )

    def request(
        self, method: str, path: str, payload: dict[str, Any] | None = None
    ) -> tuple[int, dict[str, Any]]:
        headers = {"User-Agent": "GabFlow-Gate-D-Business-Acceptance/1.0"}
        data = None
        if payload is not None:
            data = json.dumps(payload).encode()
            headers["Content-Type"] = "application/json"
        if method not in {"GET", "HEAD"}:
            csrf = next(
                (cookie.value for cookie in self.cookies if cookie.name == "csrf_access_token"),
                "",
            )
            if csrf:
                headers["X-CSRF-TOKEN"] = csrf
        request = urllib.request.Request(  # noqa: S310 - base URL validated in main
            f"{self.base_url}{path}", data=data, headers=headers, method=method
        )
        try:
            with self.opener.open(  # noqa: S310 - base URL validated in main
                request, timeout=30
            ) as response:
                body = response.read()
                return response.status, json.loads(body) if body else {}
        except urllib.error.HTTPError as error:
            body = error.read()
            return error.code, json.loads(body) if body else {}

    def login(self, email: str, password: str) -> dict[str, Any]:
        status, body = self.request(
            "POST", "/api/v1/auth/login", {"email": email, "password": password}
        )
        if status != 200:
            raise RuntimeError(f"Falha de autenticação: HTTP {status}")
        return body["user"]


def assert_status(
    checks: list[dict[str, Any]],
    name: str,
    actual: int,
    expected: int,
    detail: str,
) -> None:
    passed = actual == expected
    checks.append(
        {
            "cenario": name,
            "esperado": expected,
            "observado": actual,
            "resultado": "APROVADO" if passed else "REPROVADO",
            "evidencia": detail,
        }
    )
    if not passed:
        raise RuntimeError(f"{name}: esperado HTTP {expected}, recebido HTTP {actual}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://localhost:8081")
    parser.add_argument("--env-file", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    base_url = args.base_url.rstrip("/")
    parsed = urllib.parse.urlparse(base_url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise SystemExit("Base URL deve usar HTTP ou HTTPS e possuir hostname.")
    env = parse_env(args.env_file)
    admin_email = env.get("SEED_ADMIN_EMAIL", "admin@gabflow.local")
    password = env.get("SEED_ADMIN_PASSWORD")
    if not password:
        raise SystemExit("SEED_ADMIN_PASSWORD ausente no arquivo informado.")

    checks: list[dict[str, Any]] = []
    started_at = datetime.now(UTC)
    run_key = started_at.strftime("gate-d-%Y%m%dT%H%M%SZ")
    admin = ApiSession(base_url)
    admin_user = admin.login(admin_email, password)

    status, users_payload = admin.request("GET", "/api/v1/admin/usuarios?perPage=50")
    assert_status(checks, "Liderança lista trabalhadores", status, 200, "Acesso administrativo")
    users = users_payload.get("content", users_payload if isinstance(users_payload, list) else [])
    staff = next(
        (item for item in users if item.get("email") == "homolog.staff@gabflow.local"),
        None,
    )
    if staff is None:
        raise RuntimeError("Usuário dedicado homolog.staff@gabflow.local não encontrado.")
    status, _ = admin.request(
        "PATCH", f"/api/v1/admin/usuarios/{staff['id']}", {"senha": password, "status": "active"}
    )
    assert_status(
        checks,
        "Liderança prepara usuário dedicado de homologação",
        status,
        200,
        "Credencial redefinida sem exposição no relatório e alteração auditada",
    )

    status, dashboard = admin.request("GET", "/api/v1/painel/operacional")
    assert_status(checks, "Liderança acessa painel territorial", status, 200, "Painel operacional")
    territories = dashboard.get("territorial", {}).get("tabelaTerritorial", [])
    if not territories:
        raise RuntimeError("Nenhum território disponível para homologação.")
    territory = territories[0]
    due_at = (started_at + timedelta(hours=24)).replace(microsecond=0).isoformat()
    create_payload = {
        "territorioId": territory["id"],
        "tipo": "TAREFA",
        "titulo": f"[GATE D] Homologação negocial {started_at:%Y-%m-%d %H:%M UTC}",
        "descricao": "Validar atribuição, prazo, execução, evidência e resultado territorial.",
        "responsavelId": staff["id"],
        "prazo": due_at,
        "filtros": {"gateDRun": run_key},
        "origem": {"tipo": "HOMOLOGACAO_NEGOCIAL", "gate": "D"},
    }
    status, action = admin.request("POST", "/api/v1/painel/territorial/acoes", create_payload)
    assert_status(
        checks,
        "Liderança cria e distribui ação com prazo",
        status,
        201,
        f"Ação {action.get('id', 'indisponível')} atribuída ao trabalhador no território {territory.get('nome', territory.get('territorio', 'selecionado'))}",
    )
    if action.get("responsavelId") != staff["id"] or not action.get("prazo"):
        raise RuntimeError("A ação criada não preservou responsável e prazo.")

    worker = ApiSession(base_url)
    worker_user = worker.login(staff["email"], password)
    territory_id = urllib.parse.quote(str(territory["id"]))
    status, assigned = worker.request(
        "GET", f"/api/v1/painel/territorial/acoes?territorioId={territory_id}&status=TODAS&size=100"
    )
    visible_ids = {item["id"] for item in assigned.get("content", [])}
    assert_status(
        checks,
        "Trabalhador acessa somente ações próprias",
        status if action["id"] in visible_ids and assigned.get("permissoes", {}).get("escopo") == "PROPRIAS" else 500,
        200,
        "Escopo PROPRIAS e ação atribuída visível",
    )

    status, _ = worker.request("POST", "/api/v1/painel/territorial/acoes", create_payload)
    assert_status(
        checks, "Trabalhador não pode criar ação territorial", status, 403, "Restrição negocial por perfil"
    )
    status, _ = worker.request(
        "PATCH", f"/api/v1/painel/territorial/acoes/{action['id']}", {"prazo": due_at}
    )
    assert_status(
        checks, "Trabalhador não pode alterar prazo", status, 403, "Prazo reservado à liderança"
    )
    status, started = worker.request(
        "PATCH", f"/api/v1/painel/territorial/acoes/{action['id']}", {"status": "EM_ANDAMENTO"}
    )
    assert_status(
        checks, "Trabalhador inicia ação atribuída", status, 200, "Transição PENDENTE → EM_ANDAMENTO"
    )
    if started.get("status") != "EM_ANDAMENTO":
        raise RuntimeError("A máquina de estado não registrou EM_ANDAMENTO.")

    evidence_payload = {
        "tipo": "COMPROVANTE",
        "titulo": "Evidência estruturada da homologação Gate D",
        "descricao": "Comprovante técnico sintético para validação do fluxo negocial.",
        "url": "https://example.test/gabflow/gate-d/evidencia",
        "data": datetime.now(UTC).replace(microsecond=0).isoformat(),
    }
    status, evidence = worker.request(
        "POST", f"/api/v1/painel/territorial/acoes/{action['id']}/evidencias", evidence_payload
    )
    assert_status(
        checks,
        "Trabalhador registra evidência estruturada",
        status,
        201,
        f"Evidência {evidence.get('id', 'indisponível')} com tipo, data, título e URL",
    )
    result_text = "Fluxo territorial homologado com atribuição, prazo e evidência estruturada."
    status, completed = worker.request(
        "PATCH",
        f"/api/v1/painel/territorial/acoes/{action['id']}",
        {"status": "CONCLUIDA", "resultado": result_text},
    )
    assert_status(
        checks,
        "Trabalhador conclui ação com resultado",
        status,
        200,
        "Transição EM_ANDAMENTO → CONCLUIDA com resultado obrigatório",
    )
    if completed.get("status") != "CONCLUIDA" or completed.get("resultado") != result_text:
        raise RuntimeError("A conclusão não preservou status e resultado.")

    status, metrics = admin.request(
        "GET", f"/api/v1/painel/territorial/metricas-execucao?territorioId={territory_id}"
    )
    metric_ok = metrics.get("concluidas", 0) >= 1 and metrics.get("comEvidencias", 0) >= 1
    assert_status(
        checks,
        "Liderança acompanha métricas de execução",
        status if metric_ok else 500,
        200,
        "Conclusão e cobertura de evidências refletidas nos indicadores",
    )
    status, alerts = admin.request(
        "GET", f"/api/v1/painel/territorial/alertas?territorioId={territory_id}&status=TODOS"
    )
    assert_status(
        checks,
        "Liderança consulta ciclo de vida dos alertas",
        status,
        200,
        f"{alerts.get('total', 0)} alerta(s) consultado(s), inclusive históricos",
    )
    status, audit = admin.request("GET", "/api/v1/admin/auditoria?perPage=50")
    actions = {item.get("acao") or item.get("action") for item in audit.get("content", [])}
    required_audit = {
        "territorial.action.created",
        "territorial.action.updated",
        "territorial.action.evidence.created",
    }
    assert_status(
        checks,
        "Operação mantém trilha de auditoria",
        status if required_audit.issubset(actions) else 500,
        200,
        "Criação, movimentação e evidência localizadas na auditoria",
    )

    report = {
        "gate": "D",
        "ambiente": base_url,
        "iniciadoEm": started_at.isoformat(),
        "finalizadoEm": datetime.now(UTC).isoformat(),
        "execucao": run_key,
        "personas": {
            "lideranca": {"id": admin_user.get("id"), "perfil": admin_user.get("role") or admin_user.get("perfil")},
            "trabalhador": {"id": worker_user.get("id"), "perfil": worker_user.get("role") or worker_user.get("perfil")},
        },
        "artefatosCriados": {"acaoId": action["id"], "evidenciaId": evidence.get("id")},
        "metricasTerritoriais": metrics,
        "cenarios": checks,
        "resumo": {
            "total": len(checks),
            "aprovados": sum(item["resultado"] == "APROVADO" for item in checks),
            "reprovados": sum(item["resultado"] != "APROVADO" for item in checks),
        },
    }
    report["decisao"] = "APROVADO" if report["resumo"]["reprovados"] == 0 else "REPROVADO"
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report["resumo"], ensure_ascii=False))
    print(f"Decisão: {report['decisao']}")
    print(f"Relatório: {args.output}")
    return 0 if report["decisao"] == "APROVADO" else 1


if __name__ == "__main__":
    raise SystemExit(main())
