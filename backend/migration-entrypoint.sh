#!/bin/sh
set -eu

DATABASE_URL="$(python - <<'PY'
import os
from urllib.parse import quote

username = quote(os.environ["RDS_MASTER_USERNAME"], safe="")
password = quote(os.environ["RDS_MASTER_PASSWORD"], safe="")
host = os.environ["RDS_DATABASE_HOST"]
port = os.environ.get("RDS_DATABASE_PORT", "5432")
database = os.environ.get("RDS_DATABASE_NAME", "gabflow")
print(f"postgresql+psycopg://{username}:{password}@{host}:{port}/{database}?sslmode=require")
PY
)"
export DATABASE_URL
unset RDS_MASTER_USERNAME RDS_MASTER_PASSWORD

exec /app/docker-entrypoint.sh "$@"
