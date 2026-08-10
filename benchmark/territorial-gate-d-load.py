"""Concurrent, authenticated load test for Territorial Operations Gate D."""

from __future__ import annotations

import argparse
import concurrent.futures
import http.cookiejar
import json
import math
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path


def parse_env(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def percentile(values: list[float], fraction: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = max(0, math.ceil(len(ordered) * fraction) - 1)
    return ordered[index]


def login(base_url: str, email: str, password: str) -> tuple[str, dict]:
    cookie_jar = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cookie_jar))
    payload = json.dumps({"email": email, "password": password}).encode()
    request = urllib.request.Request(  # noqa: S310 - URL validated in main
        f"{base_url}/api/v1/auth/login",
        data=payload,
        headers={"Content-Type": "application/json", "User-Agent": "GabFlow-Gate-D/1.0"},
        method="POST",
    )
    with opener.open(request, timeout=20) as response:  # noqa: S310 - URL validated in main
        user = json.load(response)["user"]
    cookie_header = "; ".join(f"{cookie.name}={cookie.value}" for cookie in cookie_jar)
    return cookie_header, user


def get_json(base_url: str, path: str, cookie_header: str, timeout: float = 20) -> dict:
    request = urllib.request.Request(  # noqa: S310 - URL validated in main
        f"{base_url}{path}",
        headers={"Cookie": cookie_header, "User-Agent": "GabFlow-Gate-D/1.0"},
    )
    with urllib.request.urlopen(  # noqa: S310 - URL validated in main
        request, timeout=timeout
    ) as response:
        return json.load(response)


def execute(base_url: str, path: str, cookie_header: str) -> dict:
    started = time.perf_counter()
    status = 0
    size = 0
    error = None
    try:
        request = urllib.request.Request(  # noqa: S310 - URL validated in main
            f"{base_url}{path}",
            headers={"Cookie": cookie_header, "User-Agent": "GabFlow-Gate-D/1.0"},
        )
        with urllib.request.urlopen(  # noqa: S310 - URL validated in main
            request, timeout=20
        ) as response:
            status = response.status
            size = len(response.read())
    except urllib.error.HTTPError as failure:
        status = failure.code
        error = f"HTTP {failure.code}"
    except Exception as failure:  # noqa: BLE001 - benchmark records typed failure names
        error = type(failure).__name__
    return {
        "path": path.split("?", 1)[0],
        "latency_ms": round((time.perf_counter() - started) * 1000, 3),
        "status": status,
        "bytes": size,
        "error": error,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://localhost:8081")
    parser.add_argument("--env-file", type=Path, required=True)
    parser.add_argument("--concurrency", type=int, default=50)
    parser.add_argument("--requests", type=int, default=1000)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    env = parse_env(args.env_file)
    email = env.get("SEED_ADMIN_EMAIL", "admin@gabflow.local")
    password = env.get("SEED_ADMIN_PASSWORD")
    if not password:
        raise SystemExit("SEED_ADMIN_PASSWORD ausente no arquivo informado.")
    base_url = args.base_url.rstrip("/")
    parsed_base_url = urllib.parse.urlparse(base_url)
    if parsed_base_url.scheme not in {"http", "https"} or not parsed_base_url.hostname:
        raise SystemExit("Base URL deve usar HTTP ou HTTPS e possuir hostname.")
    cookie_header, user = login(base_url, email, password)
    dashboard = get_json(base_url, "/api/v1/painel/operacional", cookie_header)
    rows = dashboard.get("territorial", {}).get("tabelaTerritorial", [])
    if not rows:
        raise SystemExit("Painel autenticado não retornou território para o ensaio.")
    territory_id = rows[0]["id"]
    query_id = urllib.parse.quote(str(territory_id))
    operational_endpoints = [
        f"/api/v1/painel/territorial/acoes?territorioId={query_id}&status=TODAS&page=1&size=25",
        f"/api/v1/painel/territorial/acoes?territorioId={query_id}&status=ABERTAS&page=1&size=10",
        f"/api/v1/painel/territorial/metricas-execucao?territorioId={query_id}",
        f"/api/v1/painel/territorial/alertas?territorioId={query_id}&status=ABERTOS",
    ]
    warmup_paths = ["/api/v1/painel/operacional", *operational_endpoints]
    for path in warmup_paths:
        execute(base_url, path, cookie_header)

    dashboard_requests = min(args.concurrency, args.requests)
    schedule = ["/api/v1/painel/operacional"] * dashboard_requests
    schedule.extend(
        operational_endpoints[index % len(operational_endpoints)]
        for index in range(args.requests - dashboard_requests)
    )

    started = time.perf_counter()
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.concurrency) as executor:
        futures = [
            executor.submit(execute, base_url, path, cookie_header)
            for path in schedule
        ]
        results = [future.result() for future in concurrent.futures.as_completed(futures)]
    duration = time.perf_counter() - started

    grouped: dict[str, list[dict]] = defaultdict(list)
    for result in results:
        grouped[result["path"]].append(result)
    successful = [item for item in results if item["status"] == 200 and item["error"] is None]
    errors = len(results) - len(successful)

    def metrics(items: list[dict]) -> dict:
        ok = [item for item in items if item["status"] == 200 and item["error"] is None]
        values = [item["latency_ms"] for item in ok]
        return {
            "requests": len(items),
            "successes": len(ok),
            "errors": len(items) - len(ok),
            "p50_ms": round(percentile(values, 0.50), 1),
            "p95_ms": round(percentile(values, 0.95), 1),
            "p99_ms": round(percentile(values, 0.99), 1),
            "max_ms": round(max(values), 1) if values else None,
        }

    summary = metrics(results)
    summary.update({
        "duration_seconds": round(duration, 3),
        "throughput_rps": round(len(results) / duration, 2),
        "error_rate_percent": round(errors * 100 / len(results), 3),
    })
    thresholds = {
        "overall_p95_ms": 2000,
        "error_rate_percent": 1.0,
        "operational_dashboard_p95_ms": 2000,
    }
    dashboard_metrics = metrics(grouped["/api/v1/painel/operacional"])
    passed = (
        summary["p95_ms"] <= thresholds["overall_p95_ms"]
        and summary["error_rate_percent"] <= thresholds["error_rate_percent"]
        and dashboard_metrics["p95_ms"] <= thresholds["operational_dashboard_p95_ms"]
    )
    report = {
        "gate": "D",
        "executed_at": datetime.now(UTC).isoformat(),
        "environment": base_url,
        "tenant": user["tenant"]["slug"],
        "dataset": {"citizens": 307, "organizations": 51, "service_requests": 765},
        "profile": {
            "concurrency": args.concurrency,
            "requests": args.requests,
            "warmup_requests": len(warmup_paths),
            "business_mix": "one dashboard load per virtual user, followed by territorial work",
            "read_only": True,
        },
        "thresholds": thresholds,
        "summary": summary,
        "by_endpoint": {path: metrics(items) for path, items in sorted(grouped.items())},
        "error_types": {
            name: sum(item["error"] == name for item in results)
            for name in sorted({item["error"] for item in results if item["error"]})
        },
        "decision": "PASSED" if passed else "FAILED",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if passed else 2


if __name__ == "__main__":
    raise SystemExit(main())
