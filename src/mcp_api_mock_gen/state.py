"""Job state management using CosmosDB.

Uses the "mockapi" database, "jobs" container (partition key /id)
to track deployment job status across the MCP server and worker.
"""

from __future__ import annotations

import logging
import os
from typing import Any

from azure.cosmos import CosmosClient, exceptions
from azure.identity import AzureCliCredential, ManagedIdentityCredential

logger = logging.getLogger(__name__)

_DB_NAME = "mockapi"
_CONTAINER_NAME = "jobs"


def _get_credential():
    """Return ManagedIdentityCredential when AZURE_CLIENT_ID is set, else AzureCliCredential."""
    client_id = os.environ.get("AZURE_CLIENT_ID")
    if client_id:
        return ManagedIdentityCredential(client_id=client_id)
    return AzureCliCredential()


def _get_container(cosmos_endpoint: str):
    """Return the jobs container client."""
    credential = _get_credential()
    client = CosmosClient(cosmos_endpoint, credential=credential)
    db = client.get_database_client(_DB_NAME)
    return db.get_container_client(_CONTAINER_NAME)


def create_job(cosmos_endpoint: str, deployment_id: str, resource_name: str) -> dict[str, Any]:
    """Create a new job document with status='running'."""
    container = _get_container(cosmos_endpoint)
    job = {
        "id": deployment_id,
        "status": "accepted",
        "resource_name": resource_name,
        "api_base_url": None,
        "cosmos_database": None,
        "cosmos_container": None,
        "container_app_name": None,
        "endpoints": [],
        "records_seeded": 0,
        "records_generated": 0,
        "error": None,
    }
    container.upsert_item(job)
    logger.info("Created job %s for resource '%s'", deployment_id, resource_name)
    return job


def update_job(cosmos_endpoint: str, deployment_id: str, updates: dict[str, Any]) -> dict[str, Any] | None:
    """Merge fields into an existing job document. Won't overwrite terminal states with progress states."""
    container = _get_container(cosmos_endpoint)
    try:
        job = container.read_item(item=deployment_id, partition_key=deployment_id)
    except exceptions.CosmosResourceNotFoundError:
        logger.warning("Job %s not found for update", deployment_id)
        return None

    # Don't overwrite terminal states (succeeded/failed) with progress states
    current_status = job.get("status")
    new_status = updates.get("status")
    if current_status in ("succeeded", "failed") and new_status not in ("succeeded", "failed", None):
        logger.info("Skipping status update %s -> %s for job %s (terminal state)", current_status, new_status, deployment_id)
        return job

    job.update(updates)
    container.replace_item(item=deployment_id, body=job)
    logger.info("Updated job %s: %s", deployment_id, list(updates.keys()))
    return job


def get_job(cosmos_endpoint: str, deployment_id: str) -> dict[str, Any] | None:
    """Return the full job document or None if not found."""
    container = _get_container(cosmos_endpoint)
    try:
        return container.read_item(item=deployment_id, partition_key=deployment_id)
    except exceptions.CosmosResourceNotFoundError:
        return None


def delete_job(cosmos_endpoint: str, deployment_id: str) -> bool:
    """Delete a job document. Returns True if deleted, False if not found."""
    container = _get_container(cosmos_endpoint)
    try:
        container.delete_item(item=deployment_id, partition_key=deployment_id)
        logger.info("Deleted job %s", deployment_id)
        return True
    except exceptions.CosmosResourceNotFoundError:
        return False
