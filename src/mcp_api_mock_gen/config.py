"""Configuration loaded from environment variables."""

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    """Azure deployment settings sourced from environment."""

    azure_subscription_id: str
    azure_resource_group: str
    azure_location: str
    cosmos_account_name: str
    cosmos_endpoint: str
    acr_name: str
    acr_login_server: str
    aca_environment_name: str
    managed_identity_id: str
    managed_identity_client_id: str
    azure_openai_endpoint: str
    codex_model: str = "gpt-53-codex"

    @classmethod
    def from_env(cls) -> "Settings":
        def _require(key: str) -> str:
            val = os.environ.get(key)
            if not val:
                raise EnvironmentError(f"Required environment variable {key} is not set")
            return val

        return cls(
            azure_subscription_id=_require("AZURE_SUBSCRIPTION_ID"),
            azure_resource_group=_require("AZURE_RESOURCE_GROUP"),
            azure_location=_require("AZURE_LOCATION"),
            cosmos_account_name=_require("COSMOS_ACCOUNT_NAME"),
            cosmos_endpoint=_require("COSMOS_ENDPOINT"),
            acr_name=_require("ACR_NAME"),
            acr_login_server=_require("ACR_LOGIN_SERVER"),
            aca_environment_name=_require("ACA_ENVIRONMENT_NAME"),
            managed_identity_id=_require("MANAGED_IDENTITY_ID"),
            managed_identity_client_id=_require("MANAGED_IDENTITY_CLIENT_ID"),
            azure_openai_endpoint=_require("AZURE_OPENAI_ENDPOINT"),
            codex_model=os.environ.get("CODEX_MODEL", "gpt-53-codex"),
        )
