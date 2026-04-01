from app.core.config import DEFAULT_DATABASE_URL, DEFAULT_REDIS_URL, Settings


def test_settings_fall_back_to_default_urls_without_explicit_env(monkeypatch) -> None:
    for env_name in (
        "POSTGRES_SERVER",
        "POSTGRES_PORT",
        "POSTGRES_DB",
        "POSTGRES_USER",
        "POSTGRES_PASSWORD",
        "REDIS_URL",
        "DATABASE_URL",
        "CELERY_BROKER_URL",
        "CELERY_RESULT_BACKEND",
    ):
        monkeypatch.delenv(env_name, raising=False)

    settings = Settings(_env_file=None)

    assert settings.DATABASE_URL == DEFAULT_DATABASE_URL
    assert settings.REDIS_URL == DEFAULT_REDIS_URL
    assert settings.CELERY_BROKER_URL == DEFAULT_REDIS_URL
    assert settings.CELERY_RESULT_BACKEND == DEFAULT_REDIS_URL


def test_settings_derive_database_and_celery_urls_from_postgres_and_redis(monkeypatch) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("CELERY_BROKER_URL", raising=False)
    monkeypatch.delenv("CELERY_RESULT_BACKEND", raising=False)

    settings = Settings(
        _env_file=None,
        POSTGRES_SERVER="db",
        POSTGRES_PORT=5432,
        POSTGRES_DB="pivot_backend",
        POSTGRES_USER="postgres",
        POSTGRES_PASSWORD="secret",
        REDIS_URL="redis://redis:6379/0",
    )

    assert (
        settings.DATABASE_URL
        == "postgresql+psycopg://postgres:secret@db:5432/pivot_backend"
    )
    assert settings.CELERY_BROKER_URL == "redis://redis:6379/0"
    assert settings.CELERY_RESULT_BACKEND == "redis://redis:6379/0"


def test_explicit_connection_urls_take_precedence_over_derived_values(monkeypatch) -> None:
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("CELERY_BROKER_URL", raising=False)
    monkeypatch.delenv("CELERY_RESULT_BACKEND", raising=False)

    settings = Settings(
        _env_file=None,
        POSTGRES_SERVER="db",
        POSTGRES_PORT=5432,
        POSTGRES_DB="pivot_backend",
        POSTGRES_USER="postgres",
        POSTGRES_PASSWORD="secret",
        REDIS_URL="redis://redis:6379/0",
        DATABASE_URL="sqlite:///./override.db",
        CELERY_BROKER_URL="redis://broker:6379/1",
        CELERY_RESULT_BACKEND="redis://backend:6379/2",
    )

    assert settings.DATABASE_URL == "sqlite:///./override.db"
    assert settings.CELERY_BROKER_URL == "redis://broker:6379/1"
    assert settings.CELERY_RESULT_BACKEND == "redis://backend:6379/2"


def test_codex_and_wireguard_defaults_are_present(monkeypatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    settings = Settings(_env_file=None)

    assert settings.CODEX_MODEL_PROVIDER == "fox"
    assert settings.CODEX_MODEL == "gpt-5"
    assert settings.CODEX_REVIEW_MODEL == "gpt-5"
    assert settings.CODEX_MODEL_REASONING_EFFORT == "high"
    assert settings.CODEX_PROVIDER_NAME == "fox"
    assert settings.CODEX_PROVIDER_BASE_URL == "https://code.newcli.com/codex/v1"
    assert settings.CODEX_PROVIDER_WIRE_API == "responses"
    assert settings.WIREGUARD_INTERFACE == "wg-seller"
    assert settings.WIREGUARD_NETWORK_CIDR == "10.66.66.0/24"
    assert settings.SESSION_GATEWAY_SUPPORTED_FEATURES == "exec,logs,shell,files"
