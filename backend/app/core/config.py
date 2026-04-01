from functools import lru_cache
from pathlib import Path
from typing import Any

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[3]
ENV_FILE = REPO_ROOT / ".env"
DEFAULT_DATABASE_URL = "sqlite:///./pivot_backend.db"
DEFAULT_REDIS_URL = "redis://localhost:6379/0"
DEFAULT_CODEX_AUTH_JSON_PATH = REPO_ROOT / "backend" / ".codex" / "auth.json"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=ENV_FILE,
        env_ignore_empty=True,
        extra="ignore",
    )

    PROJECT_NAME: str = "Pivot Backend Build Team"
    API_V1_STR: str = "/api/v1"
    POSTGRES_SERVER: str | None = None
    POSTGRES_PORT: int | None = None
    POSTGRES_DB: str | None = None
    POSTGRES_USER: str | None = None
    POSTGRES_PASSWORD: str | None = None
    REDIS_URL: str = DEFAULT_REDIS_URL
    DATABASE_URL: str = DEFAULT_DATABASE_URL
    CELERY_BROKER_URL: str = DEFAULT_REDIS_URL
    CELERY_RESULT_BACKEND: str = DEFAULT_REDIS_URL
    SWARM_DOCKER_BIN: str = "docker"
    SWARM_DOCKER_TIMEOUT_SECONDS: float = 10.0
    SWARM_MANAGER_HOST: str = "pivotcompute.store"
    SWARM_MANAGER_PORT: int = 2377
    OPENAI_API_KEY: str | None = None
    CODEX_AUTH_JSON_PATH: str = str(DEFAULT_CODEX_AUTH_JSON_PATH)
    CODEX_AUTH_JSON_FALLBACK_HOME: bool = True
    CODEX_MODEL_PROVIDER: str = "fox"
    CODEX_MODEL: str = "gpt-5"
    CODEX_REVIEW_MODEL: str = "gpt-5"
    CODEX_MODEL_REASONING_EFFORT: str = "high"
    CODEX_DISABLE_RESPONSE_STORAGE: bool = True
    CODEX_NETWORK_ACCESS: str = "enabled"
    CODEX_WINDOWS_WSL_SETUP_ACKNOWLEDGED: bool = True
    CODEX_MODEL_CONTEXT_WINDOW: int = 1_000_000
    CODEX_MODEL_AUTO_COMPACT_TOKEN_LIMIT: int = 900_000
    CODEX_PROVIDER_NAME: str = "fox"
    CODEX_PROVIDER_BASE_URL: str = "https://code.newcli.com/codex/v1"
    CODEX_PROVIDER_WIRE_API: str = "responses"
    CODEX_PROVIDER_REQUIRES_OPENAI_AUTH: bool = True
    WIREGUARD_ENABLED: bool = True
    WIREGUARD_INTERFACE: str = "wg-seller"
    WIREGUARD_ENDPOINT_HOST: str = "pivotcompute.store"
    WIREGUARD_ENDPOINT_PORT: int = 45182
    WIREGUARD_SERVER_PUBLIC_KEY: str = "puGAoUTF0vyha+32vxQ+BBVOWXlCOUzhFoNe5tJ9hyo="
    WIREGUARD_ALLOWED_IPS: str = "10.66.66.0/24"
    WIREGUARD_NETWORK_CIDR: str = "10.66.66.0/24"
    WIREGUARD_DNS: str = ""
    WIREGUARD_PERSISTENT_KEEPALIVE: int = 25
    WIREGUARD_BUYER_INTERFACE: str = "wg-buyer"
    WIREGUARD_BUYER_NETWORK_CIDR: str = "10.66.66.128/25"
    WIREGUARD_SERVER_INTERFACE: str = "wg0"
    WIREGUARD_SERVER_CONFIG_PATH: str = "/etc/wireguard/wg0.conf"
    WIREGUARD_SERVER_SSH_ENABLED: bool = False
    WIREGUARD_SERVER_SSH_HOST: str = "pivotcompute.store"
    WIREGUARD_SERVER_SSH_PORT: int = 22
    WIREGUARD_SERVER_SSH_USER: str = "root"
    WIREGUARD_SERVER_SSH_PASSWORD: str = ""
    WIREGUARD_SERVER_SSH_KEY_PATH: str = ""
    SESSION_GATEWAY_IMAGE: str = "python:3.12-alpine"
    SESSION_GATEWAY_PROTOCOL: str = "http"
    SESSION_GATEWAY_BASE_PORT: int = 20000
    SESSION_GATEWAY_SUPPORTED_FEATURES: str = "exec,logs,shell,files"
    SESSION_GATEWAY_HANDSHAKE_MODE: str = "session_token"
    USD_CNY_RATE: float = 7.2
    PRICING_REFERENCE_AWS_REGION: str = "us-east-1"
    PRICING_REFERENCE_AZURE_REGION: str = "eastus"
    PRICING_REFRESH_INTERVAL_SECONDS: int = 3600
    OFFER_REPRICING_INTERVAL_SECONDS: int = 3600
    USAGE_BILLING_INTERVAL_SECONDS: int = 3600
    PRICING_STALE_AFTER_SECONDS: int = 7200
    PRICING_PROBE_TIMEOUT_SECONDS: int = 180
    PRICING_PROBE_IMAGE: str = "python:3.12-alpine"
    DEFAULT_TEST_BALANCE_CNY_CREDITS: float = 100.0
    SESSION_ALLOWED_DEBT_MULTIPLIER: float = 1.0

    @model_validator(mode="before")
    @classmethod
    def derive_connection_settings(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data

        values = dict(data)
        redis_url = values.get("REDIS_URL") or DEFAULT_REDIS_URL
        postgres_server = values.get("POSTGRES_SERVER")
        postgres_port = values.get("POSTGRES_PORT")
        postgres_db = values.get("POSTGRES_DB")
        postgres_user = values.get("POSTGRES_USER")
        postgres_password = values.get("POSTGRES_PASSWORD")

        if not values.get("DATABASE_URL") and all(
            [
                postgres_server,
                postgres_port,
                postgres_db,
                postgres_user,
                postgres_password,
            ]
        ):
            values["DATABASE_URL"] = (
                "postgresql+psycopg://"
                f"{postgres_user}:{postgres_password}"
                f"@{postgres_server}:{postgres_port}/{postgres_db}"
            )

        values.setdefault("REDIS_URL", redis_url)
        values.setdefault("CELERY_BROKER_URL", redis_url)
        values.setdefault("CELERY_RESULT_BACKEND", redis_url)
        return values


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
