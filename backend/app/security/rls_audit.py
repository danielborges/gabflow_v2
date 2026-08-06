import os
import uuid
from datetime import UTC, datetime

from sqlalchemy import text

from app.extensions import db
from app.models import AuditLog, OutboxEvent, RlsAuditRun

RLS_AUDIT_EVENT = "AuditoriaAutomatizadaRls"
EXPECTED_POLICY_FRAGMENT = "current_setting('app.tenant_id'"


def create_rls_audit(actor_id: uuid.UUID) -> RlsAuditRun:
    run = RlsAuditRun(initiated_by_id=actor_id)
    db.session.add(run)
    db.session.flush()
    db.session.add(
        OutboxEvent(
            tenant_id=None,
            event_type=RLS_AUDIT_EVENT,
            aggregate_type="rls_audit_run",
            aggregate_id=str(run.id),
            payload={"runId": str(run.id)},
        )
    )
    db.session.add(
        AuditLog(
            tenant_id=None,
            user_id=actor_id,
            action="security.rls_audit_requested",
            entity_type="rls_audit_run",
            entity_id=str(run.id),
            after={"status": run.status},
        )
    )
    return run


def execute_rls_audit(run: RlsAuditRun) -> None:
    run.status = "PROCESSANDO"
    run.started_at = datetime.now(UTC)
    db.session.flush()
    if db.engine.dialect.name != "postgresql":
        run.status = "NAO_APLICAVEL"
        run.findings = [{"code": "POSTGRESQL_REQUIRED", "compliant": True}]
        run.completed_at = datetime.now(UTC)
        return

    rows = db.session.execute(
        text(
            """
            SELECT c.relname AS table_name, c.relrowsecurity, c.relforcerowsecurity,
                   COALESCE(
                       string_agg(
                           COALESCE(p.qual, '') || ' ' || COALESCE(p.with_check, ''), ' '
                       ),
                       ''
                   ) AS expressions
            FROM pg_class c
            JOIN pg_namespace n ON n.oid = c.relnamespace
            LEFT JOIN pg_policies p ON p.schemaname = n.nspname AND p.tablename = c.relname
            WHERE n.nspname = 'public' AND c.relkind = 'r'
              AND (
                  c.relname LIKE 'rag_%'
                  OR c.relname IN (
                      'attachments',
                      'mandates',
                      'electoral_module_settings',
                      'electoral_access_delegations',
                      'electoral_identity_reviews',
                      'electoral_favorites',
                      'electoral_saved_comparisons',
                      'electoral_report_jobs',
                      'electoral_generated_reports',
                      'electoral_coverage_profiles',
                      'electoral_mandate_snapshots',
                      'electoral_public_commitments',
                      'electoral_commitment_evidence',
                      'electoral_commitment_history'
                  )
              )
              AND EXISTS (
                  SELECT 1 FROM information_schema.columns col
                  WHERE col.table_schema = 'public' AND col.table_name = c.relname
                    AND col.column_name = 'tenant_id'
              )
            GROUP BY c.relname, c.relrowsecurity, c.relforcerowsecurity
            ORDER BY c.relname
            """
        )
    ).mappings()
    findings = []
    for row in rows:
        expression = str(row["expressions"] or "").lower().replace(" ", "")
        compliant = bool(
            row["relrowsecurity"]
            and row["relforcerowsecurity"]
            and "current_setting('app.tenant_id'".replace(" ", "") in expression
            and "tenant_id" in expression
        )
        findings.append(
            {
                "table": row["table_name"],
                "rlsEnabled": bool(row["relrowsecurity"]),
                "rlsForced": bool(row["relforcerowsecurity"]),
                "tenantPolicy": "tenant_id" in expression,
                "compliant": compliant,
            }
        )

    role_names = {
        os.getenv("APP_DB_USER", "gabflow_app"),
        os.getenv("WORKER_DB_USER", "gabflow_worker"),
    }
    role_rows = db.session.execute(
        text("SELECT rolname, rolsuper, rolbypassrls FROM pg_roles WHERE rolname = ANY(:roles)"),
        {"roles": list(role_names)},
    ).mappings()
    role_checks = [
        {
            "role": row["rolname"],
            "superuser": bool(row["rolsuper"]),
            "bypassRls": bool(row["rolbypassrls"]),
            "compliant": not row["rolsuper"] and not row["rolbypassrls"],
        }
        for row in role_rows
    ]
    missing_roles = role_names - {item["role"] for item in role_checks}
    role_checks.extend(
        {"role": role, "present": False, "compliant": False} for role in sorted(missing_roles)
    )

    tenants = list(db.session.execute(text("SELECT id FROM tenants ORDER BY id LIMIT 2")).scalars())
    if tenants:
        tenant_id = tenants[0]
        db.session.execute(
            text("SELECT set_config('app.tenant_id', :tenant_id, true)"),
            {"tenant_id": str(tenant_id)},
        )
        for finding in findings:
            table = finding["table"]
            visible_foreign = db.session.scalar(
                text(
                    f'SELECT count(*) FROM "{table}" WHERE tenant_id <> :tenant_id'  # noqa: S608
                ),
                {"tenant_id": tenant_id},
            )
            finding["isolationProbeForeignRows"] = int(visible_foreign or 0)
            finding["compliant"] = finding["compliant"] and not visible_foreign

    run.expected_tables = len(findings)
    run.compliant_tables = sum(item["compliant"] for item in findings)
    run.findings = findings
    run.role_checks = role_checks
    run.status = (
        "CONFORME"
        if findings
        and run.compliant_tables == run.expected_tables
        and all(item["compliant"] for item in role_checks)
        else "NAO_CONFORME"
    )
    run.completed_at = datetime.now(UTC)
    db.session.add(
        AuditLog(
            tenant_id=None,
            user_id=run.initiated_by_id,
            action="security.rls_audit_completed",
            entity_type="rls_audit_run",
            entity_id=str(run.id),
            after=rls_audit_data(run),
        )
    )


def fail_rls_audit(run: RlsAuditRun, message: str) -> None:
    run.status = "ERRO"
    run.error = str(message)[:2000]
    run.completed_at = datetime.now(UTC)


def rls_audit_data(run: RlsAuditRun) -> dict:
    return {
        "id": str(run.id),
        "status": run.status,
        "tabelasEsperadas": run.expected_tables,
        "tabelasConformes": run.compliant_tables,
        "achados": run.findings,
        "perfisRuntime": run.role_checks,
        "erro": run.error,
        "criadaEm": run.created_at.isoformat(),
        "iniciadaEm": run.started_at.isoformat() if run.started_at else None,
        "concluidaEm": run.completed_at.isoformat() if run.completed_at else None,
    }
