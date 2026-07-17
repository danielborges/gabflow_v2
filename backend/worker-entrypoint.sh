#!/bin/sh
set -eu

mkdir -p /app/data/attachments /app/data/rag
chown -R gabflow:gabflow /app/data/attachments /app/data/rag

if [ "$(id -u)" = "0" ]; then
  exec gosu gabflow "$0" "$@"
fi

exec flask --app wsgi:app worker
