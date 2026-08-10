"""Gunicorn capacity defaults, overridable per deployment."""

import os

bind = "0.0.0.0:5000"
workers = int(os.getenv("WEB_CONCURRENCY", "4"))
threads = int(os.getenv("GUNICORN_THREADS", "8"))
timeout = int(os.getenv("GUNICORN_TIMEOUT_SECONDS", "180"))
graceful_timeout = 30
accesslog = "-"
