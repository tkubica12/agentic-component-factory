"""FastMCP server exposing create_mock_api, get_deployment_status, and delete_mock_api tools.

Uses an async pattern: create_mock_api starts a background job and returns
immediately with a deployment_id. Clients poll get_deployment_status until
the job completes or fails.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import subprocess
from typing import Any

from dotenv import load_dotenv
from fastmcp import FastMCP

load_dotenv(os.path.join(os.path.dirname(__file__), "..", "..", ".env"))
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

mcp = FastMCP(
    "mcp-api-mock-gen",
    instructions=(
        "MCP server that generates and deploys CRUD REST APIs from sample JSON data.\n"
        "Workflow:\n"
        "  1. Call create_mock_api to start a deployment (returns immediately with deployment_id)\n"
        "  2. Poll get_deployment_status with the deployment_id until status is 'succeeded' or 'failed'\n"
        "  3. Call delete_mock_api with deployment_id to tear down when done"
    ),
)

# In-memory job store (deployment_id -> status dict)
_jobs: dict[str, dict[str, Any]] = {}


@mcp.tool()
async def create_mock_api(
    name: str,
    sample_records: list[dict],
    record_count: int = 0,
    data_description: str = "",
) -> dict:
    """Start creating a CRUD REST API from sample data. Returns immediately.

    This starts a background deployment. Poll get_deployment_status with the
    returned deployment_id to check progress.

    Args:
        name: Resource name for the API (e.g. 'products', 'users').
        sample_records: One or more JSON records defining the schema and seed data.
        record_count: Number of additional synthetic records to generate (0 = none).
        data_description: Natural language description to guide data generation.
    """
    logger.info("create_mock_api called: name=%s, records=%d, record_count=%d", name, len(sample_records), record_count)

    # Generate deployment_id immediately — no imports, no I/O
    import uuid
    deployment_id = str(uuid.uuid4())[:8]

    # Store initial status
    _jobs[deployment_id] = {
        "deployment_id": deployment_id,
        "status": "running",
        "resource_name": name,
        "api_base_url": None,
        "cosmos_database": None,
        "cosmos_container": None,
        "container_app_name": None,
        "endpoints": [],
        "records_seeded": 0,
        "records_generated": 0,
        "error": None,
    }

    # Start background task (all heavy work happens here)
    async def _run():
        try:
            from .codegen import run_codegen
            from .config import Settings
            settings = Settings.from_env()
            result = await run_codegen(name, sample_records, settings, record_count, data_description, deployment_id)
            _jobs[deployment_id].update({
                "status": result["status"],
                "api_base_url": result.get("api_base_url"),
                "cosmos_database": result.get("cosmos_database"),
                "cosmos_container": result.get("cosmos_container"),
                "container_app_name": result.get("container_app_name"),
                "endpoints": result.get("endpoints", []),
                "records_seeded": result.get("records_seeded", 0),
                "records_generated": result.get("records_generated", 0),
                "error": result.get("error"),
            })
        except Exception as e:
            logger.exception("Background job %s failed", deployment_id)
            _jobs[deployment_id].update({"status": "failed", "error": str(e)})

    asyncio.create_task(_run())

    return {"deployment_id": deployment_id, "status": "running"}


@mcp.tool()
async def get_deployment_status(deployment_id: str) -> dict:
    """Check the status of a deployment started by create_mock_api.

    Poll this until status is 'succeeded' or 'failed'.

    Args:
        deployment_id: The deployment_id returned by create_mock_api.
    """
    job = _jobs.get(deployment_id)
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
    from .config import Settings
    from .skills.container_apps import ContainerAppsSkills
    from .skills.cosmos import CosmosSkills

    logger.info("delete_mock_api called: deployment_id=%s", deployment_id)

    settings = Settings.from_env()
    errors = []

    try:
        result = subprocess.run(
            ["az", "containerapp", "list", "--resource-group", settings.azure_resource_group,
             "--subscription", settings.azure_subscription_id, "--query", f"[?ends_with(name, '-{deployment_id}')].name",
             "--output", "json"],
            capture_output=True, text=True, timeout=60, shell=(os.name == "nt"),
        )
        app_names = json.loads(result.stdout) if result.stdout.strip() else []
        for app_name in app_names:
            logger.info("Deleting container app: %s", app_name)
            ContainerAppsSkills.delete_container_app(app_name, settings.azure_resource_group, settings.azure_subscription_id)
    except Exception as e:
        errors.append(f"Container app deletion: {e}")

    cosmos = CosmosSkills(
        endpoint=settings.cosmos_endpoint,
        account_name=settings.cosmos_account_name,
        resource_group=settings.azure_resource_group,
        subscription_id=settings.azure_subscription_id,
    )
    try:
        result = subprocess.run(
            ["az", "cosmosdb", "sql", "container", "list",
             "--account-name", settings.cosmos_account_name,
             "--resource-group", settings.azure_resource_group,
             "--subscription", settings.azure_subscription_id,
             "--database-name", "mockapi",
             "--query", f"[?ends_with(name, '_{deployment_id}')].name",
             "--output", "json"],
            capture_output=True, text=True, timeout=60, shell=(os.name == "nt"),
        )
        container_names = json.loads(result.stdout) if result.stdout.strip() else []
        for cname in container_names:
            logger.info("Deleting cosmos container: %s", cname)
            cosmos.delete_container("mockapi", cname)
    except Exception as e:
        errors.append(f"Cosmos container deletion: {e}")

    # Clean up job store
    _jobs.pop(deployment_id, None)

    status = "failed" if errors else "succeeded"
    error = "; ".join(errors) if errors else None
    return {"deployment_id": deployment_id, "status": status, "error": error}
