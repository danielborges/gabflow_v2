#!/bin/sh
set -eu

mkdir -p /app/data/attachments /app/data/rag /app/data/electoral
# EFS access points enforce their own POSIX identity and reject chown by design.
# Local volumes still receive the expected ownership when the operation is allowed.
chown -R gabflow:gabflow /app/data/attachments /app/data/rag /app/data/electoral 2>/dev/null || true

if [ "$(id -u)" = "0" ]; then
  exec gosu gabflow "$0" "$@"
fi

if [ "${RUN_MIGRATIONS_ON_START:-false}" = "true" ]; then
  flask --app wsgi:app db upgrade
fi

if [ "${RUN_SEEDS_ON_START:-false}" = "true" ] && [ "${SEED_ADMIN_ON_START:-false}" = "true" ]; then
  flask --app wsgi:app seed \
    --tenant "${SEED_TENANT:-gabinete-demo}" \
    --email "${SEED_ADMIN_EMAIL:-admin@gabflow.local}" \
    --password "${SEED_ADMIN_PASSWORD:?SEED_ADMIN_PASSWORD is required}"
fi

if [ "${RUN_SEEDS_ON_START:-false}" = "true" ] && [ "${SEED_PLATFORM_ADMIN_ON_START:-false}" = "true" ]; then
  flask --app wsgi:app seed-platform-admin \
    --email "${SEED_PLATFORM_ADMIN_EMAIL:-platform@gabflow.local}" \
    --password "${SEED_PLATFORM_ADMIN_PASSWORD:?SEED_PLATFORM_ADMIN_PASSWORD is required}"
fi

exec "$@"
