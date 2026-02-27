"""Container Apps skill for GitHub Copilot SDK.

Creates and manages Azure Container Apps from ACR images.
"""

from __future__ import annotations

import json
import logging
import os
import subprocess

logger = logging.getLogger(__name__)


def _az(args: list[str], check: bool = True) -> subprocess.CompletedProcess:
    cmd = ["az"] + args + ["--output", "json"]
    logger.info("az %s", " ".join(args[:10]))
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=300, shell=(os.name == "nt"))
    if check and result.returncode != 0:
        raise RuntimeError(f"az command failed: {result.stderr}")
    return result


class ContainerAppsSkills:
    """Skills for Azure Container Apps lifecycle."""

    def __init__(
        self,
        subscription_id: str,
        resource_group: str,
        aca_environment_name: str,
        acr_login_server: str,
        managed_identity_id: str,
        managed_identity_client_id: str,
        cosmos_endpoint: str,
    ):
        self.subscription_id = subscription_id
        self.resource_group = resource_group
        self.aca_environment_name = aca_environment_name
        self.acr_login_server = acr_login_server
        self.managed_identity_id = managed_identity_id
        self.managed_identity_client_id = managed_identity_client_id
        self.cosmos_endpoint = cosmos_endpoint
        self.app_url: str | None = None

    def create_container_app(
        self, app_name: str, image_tag: str, database_name: str, container_name: str
    ) -> str:
        """Create a Container App from an ACR image with smallest sizing and external ingress."""
        full_image = f"{self.acr_login_server}/{image_tag}"

        _az([
            "containerapp", "create",
            "--name", app_name,
            "--resource-group", self.resource_group,
            "--subscription", self.subscription_id,
            "--environment", self.aca_environment_name,
            "--image", full_image,
            "--target-port", "8000",
            "--ingress", "external",
            "--min-replicas", "0",
            "--max-replicas", "1",
            "--cpu", "0.25",
            "--memory", "0.5Gi",
            "--user-assigned", self.managed_identity_id,
            "--registry-server", self.acr_login_server,
            "--registry-identity", self.managed_identity_id,
            "--env-vars",
            f"COSMOS_ENDPOINT={self.cosmos_endpoint}",
            f"COSMOS_DATABASE={database_name}",
            f"COSMOS_CONTAINER={container_name}",
            f"AZURE_CLIENT_ID={self.managed_identity_client_id}",
        ])

        # Get the FQDN
        result = _az([
            "containerapp", "show",
            "--name", app_name,
            "--resource-group", self.resource_group,
            "--subscription", self.subscription_id,
            "--query", "properties.configuration.ingress.fqdn",
        ])
        fqdn = json.loads(result.stdout).strip('"') if result.stdout.strip() else ""
        self.app_url = f"https://{fqdn}" if fqdn else None

        logger.info("Created container app %s at %s", app_name, self.app_url)
        return json.dumps({"status": "ok", "app_name": app_name, "url": self.app_url})

    @staticmethod
    def delete_container_app(app_name: str, resource_group: str, subscription_id: str) -> str:
        """Delete a Container App."""
        try:
            _az([
                "containerapp", "delete",
                "--name", app_name,
                "--resource-group", resource_group,
                "--subscription", subscription_id,
                "--yes",
            ])
            logger.info("Deleted container app %s", app_name)
            return json.dumps({"status": "ok"})
        except Exception as e:
            return json.dumps({"status": "error", "message": str(e)})
