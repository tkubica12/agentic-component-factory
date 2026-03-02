"""CosmosDB skills for GitHub Copilot SDK.

Uses az CLI for control plane (create db/container) and sync Cosmos SDK
for data plane (upsert items) to avoid Windows async credential issues.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any

from azure.cosmos import CosmosClient
from azure.identity import AzureCliCredential

from .az_helpers import az_async

logger = logging.getLogger(__name__)


class CosmosSkills:
    """Stateful helper for CosmosDB operations within a single MCP operation."""

    def __init__(self, endpoint: str, account_name: str, resource_group: str, subscription_id: str):
        self.endpoint = endpoint
        self.account_name = account_name
        self.resource_group = resource_group
        self.subscription_id = subscription_id
        self._client: CosmosClient | None = None

    def _ensure_client(self) -> CosmosClient:
        if self._client is None:
            client_id = os.environ.get("AZURE_CLIENT_ID")
            if client_id:
                from azure.identity import ManagedIdentityCredential
                credential = ManagedIdentityCredential(client_id=client_id)
            else:
                credential = AzureCliCredential()
            self._client = CosmosClient(self.endpoint, credential=credential)
        return self._client

    async def close(self) -> None:
        """No-op for sync client, kept for interface compatibility."""
        pass

    async def create_container(self, database_name: str, container_name: str, partition_key_path: str = "/id") -> str:
        """Create a CosmosDB database and container using Azure CLI (control plane)."""
        await az_async([
            "cosmosdb", "sql", "database", "create",
            "--account-name", self.account_name,
            "--resource-group", self.resource_group,
            "--subscription", self.subscription_id,
            "--name", database_name,
        ], check=False)

        await az_async([
            "cosmosdb", "sql", "container", "create",
            "--account-name", self.account_name,
            "--resource-group", self.resource_group,
            "--subscription", self.subscription_id,
            "--database-name", database_name,
            "--name", container_name,
            "--partition-key-path", partition_key_path,
        ], check=False)

        logger.info("Ensured container %s/%s", database_name, container_name)
        return json.dumps({
            "status": "ok",
            "database": database_name,
            "container": container_name,
            "partition_key": partition_key_path,
        })

    def seed_data(self, database_name: str, container_name: str, records: list[dict[str, Any]]) -> str:
        """Upsert sample records into an existing container via data plane (sync)."""
        import uuid as _uuid

        client = self._ensure_client()
        db = client.get_database_client(database_name)
        container = db.get_container_client(container_name)
        count = 0
        for record in records:
            if "id" not in record:
                record["id"] = str(_uuid.uuid4())
            else:
                record["id"] = str(record["id"])  # CosmosDB requires id to be a string
            container.upsert_item(record)
            count += 1
        logger.info("Seeded %d records into %s/%s", count, database_name, container_name)
        return json.dumps({"status": "ok", "records_seeded": count})

    async def delete_container(self, database_name: str, container_name: str) -> str:
        """Delete a CosmosDB container using Azure CLI."""
        await az_async([
            "cosmosdb", "sql", "container", "delete",
            "--account-name", self.account_name,
            "--resource-group", self.resource_group,
            "--subscription", self.subscription_id,
            "--database-name", database_name,
            "--name", container_name,
            "--yes",
        ], check=False)
        logger.info("Deleted container %s/%s", database_name, container_name)
        return json.dumps({"status": "ok", "database": database_name, "container": container_name})
