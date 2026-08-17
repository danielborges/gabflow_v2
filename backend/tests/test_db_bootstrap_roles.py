import importlib.util
from pathlib import Path


def _load_bootstrap_module():
    path = Path(__file__).resolve().parents[1] / "db-bootstrap-roles.py"
    spec = importlib.util.spec_from_file_location("db_bootstrap_roles", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class RecordingCursor:
    def __init__(self, schema_exists: bool):
        self.schema_exists = schema_exists
        self.statements = []

    def execute(self, statement, _parameters=None):
        rendered = statement.as_string() if hasattr(statement, "as_string") else statement
        self.statements.append(rendered)

    def fetchone(self):
        return (1,) if self.schema_exists else None


def test_runtime_bootstrap_grants_existing_rag_global_schema():
    bootstrap = _load_bootstrap_module()
    cursor = RecordingCursor(schema_exists=True)

    bootstrap._grant_runtime_access(cursor, "gabflow_app", "gabflow", "gabflow")

    statements = "\n".join(cursor.statements)
    assert 'GRANT USAGE ON SCHEMA rag_global TO "gabflow_app"' in statements
    assert "ON ALL TABLES IN SCHEMA rag_global" in statements
    assert "IN SCHEMA rag_global" in statements


def test_runtime_bootstrap_skips_rag_global_before_schema_creation():
    bootstrap = _load_bootstrap_module()
    cursor = RecordingCursor(schema_exists=False)

    bootstrap._grant_runtime_access(cursor, "gabflow_app", "gabflow", "gabflow")

    grant_statements = "\n".join(
        statement for statement in cursor.statements if statement.startswith("GRANT")
    )
    assert "SCHEMA rag_global" not in grant_statements
