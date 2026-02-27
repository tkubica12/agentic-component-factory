"""FastMCP server exposing create_mock_api and delete_mock_api tools."""

from __future__ import annotations

import logging
import os

from dotenv import load_dotenv
from fastmcp import FastMCP

load_dotenv(os.path.join(os.path.dirname(__file__), "..", "..", ".env"))
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

mcp = FastMCP(
    "mcp-api-mock-gen",
    instructions=(
        "MCP server that generates and deploys CRUD REST APIs from sample JSON data. "
        "Call create_mock_api with a resource name and sample records to get a fully deployed API. "
        "Call delete_mock_api with a deployment_id to tear down a previously created API."
    ),
)


@mcp.tool()
async def create_mock_api(
    name: str,
    sample_records: list[dict],
    record_count: int = 0,
    data_description: str = "",
) -> dict:
    """Create a CRUD REST API from sample data, optionally with synthetic data generation.

    Generates a FastAPI application in a Docker container backed by CosmosDB serverless.
    Returns a deployment_id that can be used to delete the API later.

    Args:
        name: Resource name for the API (e.g. 'products', 'users').
        sample_records: One or more JSON records defining the schema and seed data.
        record_count: Number of additional synthetic records to generate (0 = no generation).
        data_description: Natural language description of the data to guide generation.
    """
    from .codegen import run_codegen
    from .config import Settings
    from .contracts import CreateMockApiResult, EndpointInfo

    logger.info("create_mock_api called: name=%s, records=%d, record_count=%d", name, len(sample_records), record_count)

    settings = Settings.from_env()
    result = await run_codegen(name, sample_records, settings, record_count, data_description)

    api_result = CreateMockApiResult(
        deployment_id=result.get("deployment_id", ""),
        status=result["status"],
        api_base_url=result.get("api_base_url"),
        resource_name=result["resource_name"],
        cosmos_database=result.get("cosmos_database"),
        cosmos_container=result.get("cosmos_container"),
        container_app_name=result.get("container_app_name"),
        endpoints=[EndpointInfo(**ep) for ep in result.get("endpoints", [])],
        records_seeded=result.get("records_seeded", 0),
        records_generated=result.get("records_generated", 0),
        error=result.get("error"),
    )

    return api_result.model_dump()


@mcp.tool()
async def delete_mock_api(deployment_id: str) -> dict:
    """Delete a previously created mock API.

    Removes the Container App and CosmosDB container for the given deployment.

    Args:
        deployment_id: The deployment_id returned by create_mock_api.
    """
    from .config import Settings
    from .contracts import DeleteMockApiResult
    from .skills.container_apps import ContainerAppsSkills
    from .skills.cosmos import CosmosSkills

    logger.info("delete_mock_api called: deployment_id=%s", deployment_id)

    settings = Settings.from_env()

    # Discover resources by naming convention
    # Container app name pattern: mock-{resource}-{deployment_id}
    # Cosmos container pattern: {resource}_{deployment_id}
    # We need to find them by listing container apps with the deployment_id suffix
    import subprocess, json

    errors = []

    # Delete container apps matching the deployment_id
    try:
        result = subprocess.run(
            ["az", "containerapp", "list", "--resource-group", settings.azure_resource_group,
             "--subscription", settings.azure_subscription_id, "--query", f"[?ends_with(name, '-{deployment_id}')].name",
             "--output", "json"],
            capture_output=True, text=True, timeout=60, shell=True,
        )
        app_names = json.loads(result.stdout) if result.stdout.strip() else []
        for app_name in app_names:
            logger.info("Deleting container app: %s", app_name)
            ContainerAppsSkills.delete_container_app(app_name, settings.azure_resource_group, settings.azure_subscription_id)
    except Exception as e:
        errors.append(f"Container app deletion: {e}")

    # Delete cosmos containers matching the deployment_id
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
            capture_output=True, text=True, timeout=60, shell=True,
        )
        container_names = json.loads(result.stdout) if result.stdout.strip() else []
        for cname in container_names:
            logger.info("Deleting cosmos container: %s", cname)
            cosmos.delete_container("mockapi", cname)
    except Exception as e:
        errors.append(f"Cosmos container deletion: {e}")

    status = "failed" if errors else "succeeded"
    error = "; ".join(errors) if errors else None

    return DeleteMockApiResult(deployment_id=deployment_id, status=status, error=error).model_dump()
