from __future__ import annotations

import logging
from functools import lru_cache
from typing import Optional

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger(__name__)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    DATABASE_URL: str = "postgresql+asyncpg://cqc:devpassword@localhost:5432/cqc_readiness"
    GRAPH_TENANT_ID: str = "placeholder"
    GRAPH_CLIENT_ID: str = "placeholder"
    GRAPH_CLIENT_SECRET: str = "placeholder"
    GRAPH_SENDER_EMAIL: str = "noreply@example.com"
    CQM_ALERT_EMAIL: str = "cqm@example.com"
    APP_BASE_URL: str = "http://localhost:8000"
    ADMIN_USERNAME: str = "admin"
    ADMIN_PASSWORD_HASH: str = "$2b$12$placeholder"
    SCHEDULER_SEND_HOUR: int = 7
    SCHEDULER_TIMEZONE: str = "Europe/London"
    TOKEN_EXPIRY_HOURS: int = 16
    KEY_VAULT_URL: Optional[str] = None

    @field_validator("SCHEDULER_SEND_HOUR")
    @classmethod
    def validate_send_hour(cls, v: int) -> int:
        if not 0 <= v <= 23:
            raise ValueError("SCHEDULER_SEND_HOUR must be between 0 and 23")
        return v

    @field_validator("TOKEN_EXPIRY_HOURS")
    @classmethod
    def validate_token_expiry(cls, v: int) -> int:
        if v < 1:
            raise ValueError("TOKEN_EXPIRY_HOURS must be at least 1")
        return v


def _load_from_key_vault(vault_url: str) -> dict:
    """Load secrets from Azure Key Vault using Managed Identity."""
    try:
        from azure.identity import DefaultAzureCredential
        from azure.keyvault.secrets import SecretClient

        credential = DefaultAzureCredential()
        client = SecretClient(vault_url=vault_url, credential=credential)

        secret_names = [
            "DATABASE-URL",
            "GRAPH-TENANT-ID",
            "GRAPH-CLIENT-ID",
            "GRAPH-CLIENT-SECRET",
            "GRAPH-SENDER-EMAIL",
            "CQM-ALERT-EMAIL",
            "APP-BASE-URL",
            "ADMIN-USERNAME",
            "ADMIN-PASSWORD-HASH",
            "SCHEDULER-SEND-HOUR",
            "SCHEDULER-TIMEZONE",
            "TOKEN-EXPIRY-HOURS",
        ]

        overrides: dict = {}
        for name in secret_names:
            try:
                secret = client.get_secret(name)
                env_key = name.replace("-", "_").upper()
                overrides[env_key] = secret.value
                logger.info("Loaded secret %s from Key Vault", name)
            except Exception as exc:
                logger.debug("Secret %s not found in Key Vault: %s", name, exc)

        return overrides

    except Exception as exc:
        logger.warning("Failed to connect to Key Vault at %s: %s", vault_url, exc)
        return {}


@lru_cache
def get_settings() -> Settings:
    """
    Return application settings.

    If KEY_VAULT_URL is set the function first loads secrets from Azure Key Vault
    (via Managed Identity / DefaultAzureCredential) and merges them on top of the
    base env-file settings.  Falls back gracefully to env vars / .env if Key Vault
    is unavailable.
    """
    # Build base settings first so we can read KEY_VAULT_URL
    base = Settings()

    if base.KEY_VAULT_URL:
        kv_overrides = _load_from_key_vault(base.KEY_VAULT_URL)
        if kv_overrides:
            # Re-initialise Settings with Key Vault values injected as env overrides
            return Settings(**kv_overrides)

    return base
