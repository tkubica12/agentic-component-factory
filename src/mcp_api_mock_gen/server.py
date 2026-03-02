"""FastMCP server exposing create_mock_api, get_deployment_status, and delete_mock_api tools.

The server is lightweight — it enqueues work to Azure Service Bus and tracks
state in CosmosDB. A separate worker process handles the heavy codegen pipeline.
"""

from __future__ import annotations

import json
import logging
import os
import uuid
from typing import Any

from azure.identity.aio import DefaultAzureCredential
from azure.servicebus.aio import ServiceBusClient
from dotenv import load_dotenv
from fastmcp import FastMCP

from .config import Settings
from .state import create_job, delete_job, get_job

load_dotenv(os.path.join(os.path.dirname(__file__), "..", "..", ".env"))
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

mcp = FastMCP(
    "agentic-component-factory",
    instructions=(
        "MCP server that generates and deploys CRUD REST APIs from sample JSON data.\n"
        "Workflow:\n"
        "  1. Call create_mock_api to start a deployment (returns immediately with deployment_id)\n"
        "  2. Poll get_deployment_status with the deployment_id until status is 'succeeded' or 'failed'\n"
        "  3. Call delete_mock_api with deployment_id to tear down when done"
    ),
)

_QUEUE_NAME = "mock-api-jobs"


async def _send_to_service_bus(namespace: str, message: dict[str, Any]) -> None:
    """Send a JSON message to the Service Bus queue."""
    credential = DefaultAzureCredential()
    try:
        async with ServiceBusClient(fully_qualified_namespace=namespace, credential=credential) as sb_client:
            sender = sb_client.get_queue_sender(queue_name=_QUEUE_NAME)
            async with sender:
                from azure.servicebus import ServiceBusMessage
                sb_msg = ServiceBusMessage(json.dumps(message))
                await sender.send_messages(sb_msg)
    finally:
        await credential.close()


@mcp.tool()
async def create_mock_api(
    name: str,
    sample_records: list[dict],
    record_count: int = 0,
    data_description: str = "",
) -> dict:
    """Start creating a CRUD REST API from sample data. Returns immediately.

    This enqueues a background deployment job. Poll get_deployment_status with
    the returned deployment_id to check progress.

    Args:
        name: Resource name for the API (e.g. 'products', 'users').
        sample_records: One or more JSON records defining the schema and seed data.
        record_count: Number of additional synthetic records to generate (0 = none).
        data_description: Natural language description to guide data generation.
    """
    logger.info("create_mock_api called: name=%s, records=%d, record_count=%d", name, len(sample_records), record_count)

    # Validate inputs early
    if not name or not name.strip():
        return {"error": "name must be a non-empty string", "status": "failed"}
    if not sample_records:
        return {"error": "sample_records must contain at least one record", "status": "failed"}
    for i, rec in enumerate(sample_records):
        if not isinstance(rec, dict):
            return {"error": f"sample_records[{i}] must be a JSON object", "status": "failed"}

    # Coerce id fields to strings (CosmosDB requirement)
    for rec in sample_records:
        if "id" in rec:
            rec["id"] = str(rec["id"])

    settings = Settings.from_env()
    deployment_id = str(uuid.uuid4())[:8]

    # Create job record in CosmosDB
    create_job(settings.cosmos_endpoint, deployment_id, name)

    # Send message to Service Bus for worker processing
    message = {
        "deployment_id": deployment_id,
        "name": name,
        "sample_records": sample_records,
        "record_count": record_count,
        "data_description": data_description,
    }
    await _send_to_service_bus(settings.service_bus_namespace, message)
    logger.info("Job %s enqueued to Service Bus", deployment_id)

    return {"deployment_id": deployment_id, "status": "accepted"}


@mcp.tool()
async def get_deployment_status(deployment_id: str) -> dict:
    """Check the status of a deployment started by create_mock_api.

    Poll this until status is 'succeeded' or 'failed'.

    Args:
        deployment_id: The deployment_id returned by create_mock_api.
    """
    settings = Settings.from_env()
    job = get_job(settings.cosmos_endpoint, deployment_id)
    if not job:
        return {"deployment_id": deployment_id, "status": "not_found", "error": "Unknown deployment_id"}
    return job


@mcp.tool()
async def delete_mock_api(deployment_id: str) -> dict:
    """Delete a previously created mock API.

    Removes the Container App and CosmosDB container for the given deployment.

    Args:
        deployment_id: The deployment_id returned by create_mock_api.
    """
    from .skills.az_helpers import az_async
    from .skills.container_apps import ContainerAppsSkills
    from .skills.cosmos import CosmosSkills

    logger.info("delete_mock_api called: deployment_id=%s", deployment_id)

    settings = Settings.from_env()
    errors = []

    try:
        _, stdout, _ = await az_async(
            ["containerapp", "list", "--resource-group", settings.azure_resource_group,
             "--subscription", settings.azure_subscription_id, "--query", f"[?ends_with(name, '-{deployment_id}')].name"],
            check=False, timeout=60,
        )
        app_names = json.loads(stdout) if stdout.strip() else []
        for app_name in app_names:
            logger.info("Deleting container app: %s", app_name)
            await ContainerAppsSkills.delete_container_app(app_name, settings.azure_resource_group, settings.azure_subscription_id)
    except Exception as e:
        errors.append(f"Container app deletion: {e}")

    cosmos = CosmosSkills(
        endpoint=settings.cosmos_endpoint,
        account_name=settings.cosmos_account_name,
        resource_group=settings.azure_resource_group,
        subscription_id=settings.azure_subscription_id,
    )
    try:
        _, stdout, _ = await az_async(
            ["cosmosdb", "sql", "container", "list",
             "--account-name", settings.cosmos_account_name,
             "--resource-group", settings.azure_resource_group,
             "--subscription", settings.azure_subscription_id,
             "--database-name", "mockapi",
             "--query", f"[?ends_with(name, '_{deployment_id}')].name"],
            check=False, timeout=60,
        )
        container_names = json.loads(stdout) if stdout.strip() else []
        for cname in container_names:
            logger.info("Deleting cosmos container: %s", cname)
            await cosmos.delete_container("mockapi", cname)
    except Exception as e:
        errors.append(f"Cosmos container deletion: {e}")

    # Clean up job state
    delete_job(settings.cosmos_endpoint, deployment_id)

    status = "failed" if errors else "succeeded"
    error = "; ".join(errors) if errors else None
    return {"deployment_id": deployment_id, "status": status, "error": error}
