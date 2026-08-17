#!/bin/sh
set -eu

mkdir -p /run/gabflow-parser

if [ "$(id -u)" = "0" ]; then
  chown gabflow:gabflow /run/gabflow-parser
  exec gosu gabflow "$0" "$@"
fi

exec python -m app.rag.parser_service
