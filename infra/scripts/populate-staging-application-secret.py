import argparse
import json
import os
import secrets
import subprocess
import tempfile
from pathlib import Path
from urllib.parse import quote


def _url(user: str, password: str, endpoint: str) -> str:
    return (
        f"postgresql+psycopg://{quote(user, safe='')}:{quote(password, safe='')}"
        f"@{endpoint}/gabflow?sslmode=require"
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--application-secret-id", required=True)
    parser.add_argument("--database-endpoint", required=True)
    parser.add_argument("--region", required=True)
    args = parser.parse_args()

    master_user = os.environ["RDS_MASTER_USERNAME"]
    master_password = os.environ["RDS_MASTER_PASSWORD"]
    app_password = secrets.token_urlsafe(48)
    worker_password = secrets.token_urlsafe(48)
    backup_password = secrets.token_urlsafe(48)

    payload = {
        "database_url_api": _url("gabflow_app", app_password, args.database_endpoint),
        "database_url_worker": _url(
            "gabflow_worker", worker_password, args.database_endpoint
        ),
        "database_url_backup": _url(
            "gabflow_backup", backup_password, args.database_endpoint
        ),
        "database_url_migration": _url(
            master_user, master_password, args.database_endpoint
        ),
        "secret_key": secrets.token_urlsafe(64),
        "jwt_secret_key": secrets.token_urlsafe(64),
        "storage_encryption_master_key": secrets.token_urlsafe(48),
        "metrics_bearer_token": secrets.token_urlsafe(48),
    }

    temp_path = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", suffix=".json", delete=False
        ) as temp:
            temp_path = Path(temp.name)
            json.dump(payload, temp, separators=(",", ":"))
        os.chmod(temp_path, 0o600)
        subprocess.run(
            [
                "aws",
                "secretsmanager",
                "put-secret-value",
                "--secret-id",
                args.application_secret_id,
                "--secret-string",
                f"file://{temp_path}",
                "--region",
                args.region,
                "--no-cli-pager",
                "--query",
                "{ARN:ARN,VersionId:VersionId}",
                "--output",
                "json",
            ],
            check=True,
        )
    finally:
        if temp_path is not None and temp_path.exists():
            temp_path.unlink()


if __name__ == "__main__":
    main()
