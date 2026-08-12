#!/bin/sh
set -eu

mkdir -p /app/data/attachments /app/data/rag /app/data/electoral
# EFS access points enforce their own POSIX identity and reject chown by design.
# Local volumes still receive the expected ownership when the operation is allowed.
chown -R gabflow:gabflow /app/data/attachments /app/data/rag /app/data/electoral 2>/dev/null || true

if [ "$(id -u)" = "0" ]; then
  exec gosu gabflow "$0" "$@"
fi

exec flask --app wsgi:app worker
