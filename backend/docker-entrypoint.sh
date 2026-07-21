#!/bin/sh
set -eu

mkdir -p /app/data/attachments /app/data/rag
chown -R gabflow:gabflow /app/data/attachments /app/data/rag

if [ "$(id -u)" = "0" ]; then
  exec gosu gabflow "$0" "$@"
fi

flask --app wsgi:app db upgrade

if [ "${SEED_ADMIN_ON_START:-false}" = "true" ]; then
  flask --app wsgi:app seed \
    --tenant "${SEED_TENANT:-gabinete-demo}" \
    --email "${SEED_ADMIN_EMAIL:-admin@gabflow.local}" \
    --password "${SEED_ADMIN_PASSWORD:?SEED_ADMIN_PASSWORD is required}"
fi

if [ "${SEED_PLATFORM_ADMIN_ON_START:-false}" = "true" ]; then
  flask --app wsgi:app seed-platform-admin \
    --email "${SEED_PLATFORM_ADMIN_EMAIL:-platform@gabflow.local}" \
    --password "${SEED_PLATFORM_ADMIN_PASSWORD:?SEED_PLATFORM_ADMIN_PASSWORD is required}"
fi

exec "$@"
