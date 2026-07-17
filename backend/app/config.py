import os
from datetime import timedelta


class Config:
    APP_ENV = os.getenv("APP_ENV", "development")
    APP_RELEASE = os.getenv("APP_RELEASE")
    SECRET_KEY = os.getenv("SECRET_KEY", "development-only-change-me")
    SQLALCHEMY_DATABASE_URI = os.getenv(
        "DATABASE_URL",
        "postgresql+psycopg://gabflow:gabflow@localhost:5432/gabflow",
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {"pool_pre_ping": True}

    JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY", SECRET_KEY)
    JWT_TOKEN_LOCATION = ["cookies"]
    JWT_COOKIE_SECURE = os.getenv("COOKIE_SECURE", "false").lower() == "true"
    JWT_COOKIE_SAMESITE = "Strict"
    JWT_COOKIE_CSRF_PROTECT = True
    JWT_ACCESS_TOKEN_EXPIRES = timedelta(minutes=int(os.getenv("JWT_ACCESS_TOKEN_MINUTES", "30")))

    RATELIMIT_STORAGE_URI = os.getenv("RATELIMIT_STORAGE_URI", "memory://")
    RATELIMIT_HEADERS_ENABLED = True

    SENTRY_DSN = os.getenv("SENTRY_DSN")
    SENTRY_TRACES_SAMPLE_RATE = float(os.getenv("SENTRY_TRACES_SAMPLE_RATE", "0.1"))
    ATTACHMENT_STORAGE_PATH = os.getenv("ATTACHMENT_STORAGE_PATH", "/data/attachments")
    MAX_ATTACHMENT_BYTES = int(os.getenv("MAX_ATTACHMENT_BYTES", str(15 * 1024 * 1024)))
    ATTACHMENT_TOKEN_MAX_AGE = int(os.getenv("ATTACHMENT_TOKEN_MAX_AGE", "300"))
    RESEND_API_KEY = os.getenv("RESEND_API_KEY")
    RESEND_FROM_EMAIL = os.getenv("RESEND_FROM_EMAIL")
    RESEND_TIMEOUT_SECONDS = int(os.getenv("RESEND_TIMEOUT_SECONDS", "10"))
    WORKER_POLL_SECONDS = float(os.getenv("WORKER_POLL_SECONDS", "2"))
    WORKER_BATCH_SIZE = int(os.getenv("WORKER_BATCH_SIZE", "20"))
    WORKER_MAX_ATTEMPTS = int(os.getenv("WORKER_MAX_ATTEMPTS", "5"))
    WORKER_RETRY_BASE_SECONDS = int(os.getenv("WORKER_RETRY_BASE_SECONDS", "30"))
    WORKER_RETRY_MAX_SECONDS = int(os.getenv("WORKER_RETRY_MAX_SECONDS", "3600"))
    WORKER_LOCK_TIMEOUT_SECONDS = int(os.getenv("WORKER_LOCK_TIMEOUT_SECONDS", "300"))
    SCHEDULER_INTERVAL_SECONDS = int(os.getenv("SCHEDULER_INTERVAL_SECONDS", "30"))
    AI_TRIAGE_PROVIDER = os.getenv("AI_TRIAGE_PROVIDER", "ollama")
    AI_TRIAGE_MODEL = os.getenv("AI_TRIAGE_MODEL", "qwen2.5:3b")
    AI_TRIAGE_FALLBACK_MODEL = os.getenv(
        "AI_TRIAGE_FALLBACK_MODEL",
        "gabflow-triage-rules-v1",
    )
    AI_TRIAGE_PROMPT_VERSION = os.getenv("AI_TRIAGE_PROMPT_VERSION", "triage-v2")
    AI_TRIAGE_TIMEOUT_SECONDS = int(os.getenv("AI_TRIAGE_TIMEOUT_SECONDS", "120"))
    AI_TRIAGE_FALLBACK_ENABLED = os.getenv(
        "AI_TRIAGE_FALLBACK_ENABLED",
        "true",
    ).lower() == "true"
    OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://ollama:11434")


class TestConfig(Config):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = "sqlite+pysqlite:///:memory:"
    JWT_COOKIE_SECURE = False
    RATELIMIT_ENABLED = False
    SENTRY_DSN = None
    RESEND_API_KEY = None
    RESEND_FROM_EMAIL = None
    AI_TRIAGE_PROVIDER = "local"
    AI_TRIAGE_MODEL = "gabflow-triage-rules-v1"
    AI_TRIAGE_FALLBACK_MODEL = "gabflow-triage-rules-v1"
    AI_TRIAGE_PROMPT_VERSION = "triage-v1"
