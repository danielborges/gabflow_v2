#!/bin/sh
set -eu

exec flask --app wsgi:app worker
