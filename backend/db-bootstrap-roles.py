import os
from urllib.parse import unquote, urlsplit

import psycopg
from psycopg import sql


def _psycopg_url(value: str) -> str:
    return value.replace("postgresql+psycopg://", "postgresql://", 1)


def _credentials(url: str, expected_role: str) -> tuple[str, str]:
    parsed = urlsplit(_psycopg_url(url))
    role = unquote(parsed.username or "")
    password = unquote(parsed.password or "")
    if role != expected_role or not password:
        raise RuntimeError(f"URL de banco invalida para a role {expected_role}")
    return role, password


def _upsert_role(cursor, role: str, password: str) -> None:
    cursor.execute("SELECT 1 FROM pg_roles WHERE rolname = %s", (role,))
    if cursor.fetchone() is None:
        cursor.execute(
            sql.SQL("CREATE ROLE {} LOGIN PASSWORD {}").format(
                sql.Identifier(role),
                sql.Literal(password),
            )
        )
    cursor.execute(
        sql.SQL("ALTER ROLE {} LOGIN PASSWORD {}").format(
            sql.Identifier(role),
            sql.Literal(password),
        )
    )
    cursor.execute(
        "SELECT rolsuper, rolcreatedb, rolcreaterole, rolreplication, rolbypassrls "
        "FROM pg_roles WHERE rolname = %s",
        (role,),
    )
    if any(cursor.fetchone()):
        raise RuntimeError(f"Role de banco insegura detectada: {role}")


def _grant_runtime_access(cursor, role: str, database: str, migrator: str) -> None:
    cursor.execute(
        sql.SQL("GRANT CONNECT ON DATABASE {} TO {}").format(
            sql.Identifier(database), sql.Identifier(role)
        )
    )
    cursor.execute(
        sql.SQL("GRANT USAGE ON SCHEMA public TO {}").format(sql.Identifier(role))
    )
    cursor.execute(
        sql.SQL(
            "GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO {}"
        ).format(sql.Identifier(role))
    )
    cursor.execute(
        sql.SQL("GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO {}").format(
            sql.Identifier(role)
        )
    )
    cursor.execute(
        sql.SQL(
            "ALTER DEFAULT PRIVILEGES FOR ROLE {} IN SCHEMA public "
            "GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO {}"
        ).format(sql.Identifier(migrator), sql.Identifier(role))
    )
    cursor.execute(
        sql.SQL(
            "ALTER DEFAULT PRIVILEGES FOR ROLE {} IN SCHEMA public "
            "GRANT USAGE, SELECT ON SEQUENCES TO {}"
        ).format(sql.Identifier(migrator), sql.Identifier(role))
    )


def main() -> None:
    database = os.environ.get("POSTGRES_DB", "gabflow")
    app_role = os.environ.get("APP_DB_USER", "gabflow_app")
    worker_role = os.environ.get("WORKER_DB_USER", "gabflow_worker")
    backup_role = os.environ.get("BACKUP_DB_USER", "gabflow_backup")

    app_role, app_password = _credentials(os.environ["APP_DATABASE_URL"], app_role)
    worker_role, worker_password = _credentials(
        os.environ["WORKER_DATABASE_URL"], worker_role
    )
    backup_role, backup_password = _credentials(
        os.environ["BACKUP_DATABASE_URL"], backup_role
    )

    with psycopg.connect(_psycopg_url(os.environ["DATABASE_URL"]), autocommit=True) as conn:
        migrator = conn.info.user
        with conn.cursor() as cursor:
            _upsert_role(cursor, app_role, app_password)
            _upsert_role(cursor, worker_role, worker_password)
            _upsert_role(cursor, backup_role, backup_password)
            _grant_runtime_access(cursor, app_role, database, migrator)
            _grant_runtime_access(cursor, worker_role, database, migrator)
            cursor.execute(
                sql.SQL("GRANT CONNECT ON DATABASE {} TO {}").format(
                    sql.Identifier(database), sql.Identifier(backup_role)
                )
            )
            cursor.execute(
                sql.SQL("GRANT pg_read_all_data TO {}").format(
                    sql.Identifier(backup_role)
                )
            )
    print("Database roles bootstrapped successfully")


if __name__ == "__main__":
    main()
