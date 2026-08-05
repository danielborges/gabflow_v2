import ast
import re
from pathlib import Path

import yaml

from app import create_app
from app.config import TestConfig

ROOT = Path(__file__).resolve().parents[2]
OPENAPI_PATH = ROOT / "docs/specs-inteligencia-eleitoral/api/openapi.yaml"
ROUTES_PATH = ROOT / "backend/app/electoral/routes.py"
HTTP_METHODS = {"get", "post", "put", "patch", "delete"}


def _spec():
    return yaml.safe_load(OPENAPI_PATH.read_text(encoding="utf-8"))


def _path_shape(path):
    return re.sub(r"<(?:[^:>]+:)?[^>]+>|\{[^}]+\}", "{}", path)


def _constant_statuses(expression):
    if isinstance(expression, ast.Constant) and isinstance(expression.value, int):
        return {expression.value}
    if isinstance(expression, ast.IfExp):
        return _constant_statuses(expression.body) | _constant_statuses(expression.orelse)
    return set()


def test_electoral_openapi_has_exactly_the_implemented_routes_and_methods():
    app = create_app(TestConfig)
    implemented = {
        (_path_shape(rule.rule.removeprefix("/api/v1")), method.lower())
        for rule in app.url_map.iter_rules()
        if rule.rule.startswith("/api/v1/electoral")
        for method in rule.methods
        if method.lower() in HTTP_METHODS
    }
    documented = {
        (_path_shape(path), method)
        for path, path_item in _spec()["paths"].items()
        for method in path_item
        if method in HTTP_METHODS
    }

    assert documented == implemented


def test_electoral_openapi_documents_explicit_route_statuses():
    tree = ast.parse(ROUTES_PATH.read_text(encoding="utf-8"))
    operations = {
        (_path_shape(path), method): operation
        for path, path_item in _spec()["paths"].items()
        for method, operation in path_item.items()
        if method in HTTP_METHODS
    }
    missing = []

    for function in tree.body:
        if not isinstance(function, ast.FunctionDef):
            continue
        for decorator in function.decorator_list:
            if (
                not isinstance(decorator, ast.Call)
                or not isinstance(decorator.func, ast.Attribute)
                or decorator.func.attr not in HTTP_METHODS
                or not decorator.args
                or not isinstance(decorator.args[0], ast.Constant)
            ):
                continue
            route = decorator.args[0].value
            method = decorator.func.attr
            explicit_statuses = set()
            for returned in (node for node in ast.walk(function) if isinstance(node, ast.Return)):
                if isinstance(returned.value, ast.Tuple) and len(returned.value.elts) >= 2:
                    explicit_statuses |= _constant_statuses(returned.value.elts[1])
            documented_statuses = {
                int(status)
                for status in operations[(_path_shape(route), method)]["responses"]
                if str(status).isdigit()
            }
            for status in sorted(explicit_statuses - documented_statuses):
                missing.append(f"{method.upper()} {route}: {status}")

    assert not missing, "Respostas ausentes no OpenAPI:\n" + "\n".join(missing)


def test_electoral_json_mutations_have_a_documented_request_body():
    tree = ast.parse(ROUTES_PATH.read_text(encoding="utf-8"))
    operations = {
        (_path_shape(path), method): operation
        for path, path_item in _spec()["paths"].items()
        for method, operation in path_item.items()
        if method in {"post", "put", "patch"}
    }
    missing = []

    for function in tree.body:
        if not isinstance(function, ast.FunctionDef):
            continue
        reads_json = any(
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "get_json"
            for node in ast.walk(function)
        )
        if not reads_json:
            continue
        for decorator in function.decorator_list:
            if (
                isinstance(decorator, ast.Call)
                and isinstance(decorator.func, ast.Attribute)
                and decorator.func.attr in {"post", "put", "patch"}
                and decorator.args
                and isinstance(decorator.args[0], ast.Constant)
            ):
                route = decorator.args[0].value
                operation = operations[(_path_shape(route), decorator.func.attr)]
                if "requestBody" not in operation:
                    missing.append(f"{decorator.func.attr.upper()} {route}")

    assert not missing, "Corpos JSON ausentes no OpenAPI:\n" + "\n".join(missing)


def test_electoral_openapi_path_parameters_and_operation_ids_are_valid():
    operation_ids = []
    for path, path_item in _spec()["paths"].items():
        path_parameters = {
            parameter.get("name")
            for parameter in path_item.get("parameters", [])
            if "$ref" not in parameter and parameter.get("in") == "path"
        }
        for method, operation in path_item.items():
            if method not in HTTP_METHODS:
                continue
            operation_ids.append(operation["operationId"])
            operation_parameters = {
                parameter.get("name")
                for parameter in operation.get("parameters", [])
                if "$ref" not in parameter and parameter.get("in") == "path"
            }
            referenced_parameters = {
                parameter["$ref"].rsplit("/", 1)[-1]
                for parameter in path_item.get("parameters", [])
                + operation.get("parameters", [])
                if "$ref" in parameter
            }
            referenced_names = {
                _spec()["components"]["parameters"][name]["name"]
                for name in referenced_parameters
                if _spec()["components"]["parameters"][name]["in"] == "path"
            }
            assert set(re.findall(r"\{([^}]+)\}", path)) == (
                path_parameters | operation_parameters | referenced_names
            )

    assert len(operation_ids) == len(set(operation_ids))


def test_electoral_openapi_local_references_resolve():
    specification = _spec()

    references = re.findall(
        r"\$ref:\s*['\"]?(#[^'\"\s}]+)", OPENAPI_PATH.read_text(encoding="utf-8")
    )
    for reference in references:
        current = specification
        for segment in reference.removeprefix("#/").split("/"):
            current = current[segment.replace("~1", "/").replace("~0", "~")]


def test_electoral_ai_is_permanently_enabled_in_the_public_contract():
    availability = _spec()["components"]["schemas"]["ElectoralAvailability"]

    assert availability["properties"]["funcionalidades"]["properties"]["ia"]["const"] is True
    assert availability["properties"]["iaEleitoral"]["properties"]["enabled"]["const"] is True
    assert (
        availability["properties"]["iaEleitoral"]["properties"]["webResearch"]
        ["properties"]["provider"]["enum"]
        == ["SEARXNG"]
    )
