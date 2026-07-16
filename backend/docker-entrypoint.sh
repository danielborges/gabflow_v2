#!/bin/sh
set -eu

flask --app wsgi:app db upgrade

if [ "${SEED_ADMIN_ON_START:-false}" = "true" ]; then
  flask --app wsgi:app seed \
    --tenant "${SEED_TENANT:-gabinete-demo}" \
    --email "${SEED_ADMIN_EMAIL:-admin@gabflow.local}" \
    --password "${SEED_ADMIN_PASSWORD:?SEED_ADMIN_PASSWORD is required}"
fi

exec "$@"

