"""Copilot SDK orchestration - generate and deploy CRUD API as a Docker container.

Creates a Copilot SDK session with custom tools (skills) and a detailed prompt,
then lets the agent generate FastAPI code + Dockerfile and deploy to Azure Container Apps.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import tempfile
import uuid
from typing import Any

from copilot import CopilotClient
from copilot.types import Tool, PermissionRequestResult

from .config import Settings
from .schema import infer_schema, schema_summary
from .skills.acr import AcrSkills
from .skills.container_apps import ContainerAppsSkills
from .skills.cosmos import CosmosSkills

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are a code generation agent that creates CRUD REST APIs packaged as Docker containers.
You will be given a resource name, its schema, and sample records.

Your job:
1. Generate a Python FastAPI project with a Dockerfile.
2. Use the provided tools to create CosmosDB infrastructure, build the image, deploy as a Container App, and smoke test.

CRITICAL: You are running in FULLY AUTONOMOUS mode. NEVER ask the user questions.
If a tool call fails, read the error message carefully, fix the code, and retry.
Do NOT stop to ask for confirmation. Complete ALL steps.

IMPORTANT RULES - generate EXACTLY these files in the current working directory:

1. main.py - FastAPI application using SYNCHRONOUS Azure Cosmos SDK:
   - Use the SYNC azure.cosmos SDK (from azure.cosmos import CosmosClient), NOT the async one
   - Use azure.identity.ManagedIdentityCredential (NOT DefaultAzureCredential) for auth
   - Initialize Cosmos at module level (NOT in startup event) — this is safe in Docker:
     ```
     credential = ManagedIdentityCredential(client_id=os.environ.get("AZURE_CLIENT_ID"))
     cosmos_client = CosmosClient(os.environ["COSMOS_ENDPOINT"], credential)
     database = cosmos_client.get_database_client(os.environ["COSMOS_DATABASE"])
     container = database.get_container_client(os.environ["COSMOS_CONTAINER"])
     ```
   - For list/query endpoints: ALWAYS pass enable_cross_partition_query=True to query_items()
   - For create: use container.create_item(body), generate UUID id if not provided
   - For read: use container.read_item(item=id, partition_key=id)
   - For update: read item, merge patch, container.replace_item(item=id, body=updated)
   - For delete: container.delete_item(item=id, partition_key=id)
   - Use standard sync def for all endpoint handlers (not async def)
   - Implement endpoints:
     POST /api/{resource}         - Create record
     GET  /api/{resource}         - List all (support exact-match query param filtering)
     GET  /api/{resource}/{{id}}  - Get by id
     PATCH /api/{resource}/{{id}} - Partial update
     DELETE /api/{resource}/{{id}} - Delete
   - At the bottom: if __name__ == "__main__": uvicorn.run(app, host="0.0.0.0", port=8000)

2. requirements.txt - EXACTLY these lines, nothing else:
   fastapi
   uvicorn[standard]
   azure-cosmos
   azure-identity

3. Dockerfile - EXACTLY these lines:
   FROM python:3.11-slim
   WORKDIR /app
   COPY requirements.txt .
   RUN pip install --no-cache-dir -r requirements.txt
   COPY . .
   EXPOSE 8000
   CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]

AFTER generating ALL 3 files, call tools in this exact order:
1. build_image - build Docker image via ACR remote build (if it fails, fix the code and retry)
2. create_container_app - deploy the container
3. smoke_test - verify the API returns HTTP 200 on GET /api/{resource}

After all steps complete, report the final API URL and endpoints.
Do NOT ask questions. Execute all steps.
"""


def _build_prompt(resource_name: str, schema: dict, sample_records: list[dict],
                  deployment_id: str, app_name: str, image_tag: str,
                  db_name: str, container_name: str) -> str:
    return f"""Create a CRUD API for resource "{resource_name}".

Schema:
{schema_summary(schema)}

Sample records (JSON):
{json.dumps(sample_records, indent=2)}

Deployment parameters:
- deployment_id: {deployment_id}
- app_name: {app_name}
- image_tag: {image_tag}
- database_name: {db_name}
- container_name: {container_name}

Generate all 3 files (main.py, requirements.txt, Dockerfile), then use the tools to deploy. Go step by step.
"""


def _make_tools(cosmos: CosmosSkills, acr: AcrSkills, aca: ContainerAppsSkills) -> list[Tool]:
    """Create Copilot SDK Tool definitions wired to skill handlers."""

    def _create_cosmos_container(call_info) -> str:
        try:
            a = call_info.get("arguments", {})
            return cosmos.create_container(a.get("database_name", ""), a.get("container_name", ""), a.get("partition_key_path", "/id"))
        except Exception as e:
            logger.exception("create_cosmos_container failed")
            return json.dumps({"status": "error", "message": str(e)})

    def _seed_cosmos_data(call_info) -> str:
        try:
            a = call_info.get("arguments", {})
            return cosmos.seed_data(a.get("database_name", ""), a.get("container_name", ""), a.get("records", []))
        except Exception as e:
            logger.exception("seed_cosmos_data failed")
            return json.dumps({"status": "error", "message": str(e)})

    def _build_image(call_info) -> str:
        try:
            a = call_info.get("arguments", {})
            return acr.build_image(a.get("image_tag", ""), a.get("code_directory", ""))
        except Exception as e:
            logger.exception("build_image failed")
            return json.dumps({"status": "error", "message": str(e)})

    def _create_container_app(call_info) -> str:
        try:
            a = call_info.get("arguments", {})
            return aca.create_container_app(a.get("app_name", ""), a.get("image_tag", ""), a.get("database_name", ""), a.get("container_name", ""))
        except Exception as e:
            logger.exception("create_container_app failed")
            return json.dumps({"status": "error", "message": str(e)})

    def _smoke_test(call_info) -> str:
        """HTTP GET to verify the API is accessible. Retries up to 3 times with 15s delay for cold start."""
        import time
        import urllib.request
        import urllib.error
        a = call_info.get("arguments", {})
        url = a.get("url", "")
        for attempt in range(3):
            try:
                req = urllib.request.Request(url, method="GET")
                with urllib.request.urlopen(req, timeout=30) as resp:
                    body = resp.read().decode("utf-8")[:1000]
                    return json.dumps({"status": "ok", "http_status": resp.status, "body": body, "url": url})
            except urllib.error.HTTPError as e:
                body = e.read().decode("utf-8")[:1000] if e.fp else ""
                if attempt < 2:
                    time.sleep(15)
                    continue
                return json.dumps({"status": "error", "http_status": e.code, "body": body, "url": url,
                                   "message": f"HTTP {e.code}: {body}"})
            except Exception as e:
                if attempt < 2:
                    time.sleep(15)
                    continue
                return json.dumps({"status": "error", "message": f"Smoke test failed: {e}", "url": url})

    return [
        Tool(name="create_cosmos_container", description="Create a CosmosDB database and container.", handler=_create_cosmos_container,
             parameters={"type": "object", "properties": {"database_name": {"type": "string"}, "container_name": {"type": "string"}, "partition_key_path": {"type": "string", "default": "/id"}}, "required": ["database_name", "container_name"]}),
        Tool(name="seed_cosmos_data", description="Insert sample records into CosmosDB.", handler=_seed_cosmos_data,
             parameters={"type": "object", "properties": {"database_name": {"type": "string"}, "container_name": {"type": "string"}, "records": {"type": "array", "items": {"type": "object"}}}, "required": ["database_name", "container_name", "records"]}),
        Tool(name="build_image", description="Build Docker image via ACR remote build. Returns build errors if any — fix code and retry.", handler=_build_image,
             parameters={"type": "object", "properties": {"image_tag": {"type": "string", "description": "Image name:tag"}, "code_directory": {"type": "string", "description": "Path to directory with Dockerfile"}}, "required": ["image_tag", "code_directory"]}),
        Tool(name="create_container_app", description="Create Azure Container App from ACR image.", handler=_create_container_app,
             parameters={"type": "object", "properties": {"app_name": {"type": "string"}, "image_tag": {"type": "string"}, "database_name": {"type": "string"}, "container_name": {"type": "string"}}, "required": ["app_name", "image_tag", "database_name", "container_name"]}),
        Tool(name="smoke_test", description="HTTP GET to verify the API is accessible.", handler=_smoke_test,
             parameters={"type": "object", "properties": {"url": {"type": "string", "description": "Full URL to test"}}, "required": ["url"]}),
    ]


async def run_codegen(
    resource_name: str,
    sample_records: list[dict],
    settings: Settings,
) -> dict[str, Any]:
    """Run the full code generation and deployment pipeline via Copilot SDK."""
    deployment_id = str(uuid.uuid4())[:8]
    safe_name = resource_name.lower().replace(" ", "").replace("_", "")[:20]
    app_name = f"mock-{safe_name}-{deployment_id}"
    image_tag = f"mock-{safe_name}-{deployment_id}:latest"
    db_name = "mockapi"
    container_name = f"{safe_name}_{deployment_id}"

    schema = infer_schema(sample_records)
    work_dir = tempfile.mkdtemp(prefix="mcpgen_")
    logger.info("Deployment %s: work_dir=%s, app=%s", deployment_id, work_dir, app_name)

    cosmos = CosmosSkills(
        endpoint=settings.cosmos_endpoint,
        account_name=settings.cosmos_account_name,
        resource_group=settings.azure_resource_group,
        subscription_id=settings.azure_subscription_id,
    )
    acr = AcrSkills(acr_name=settings.acr_name, subscription_id=settings.azure_subscription_id)
    aca = ContainerAppsSkills(
        subscription_id=settings.azure_subscription_id,
        resource_group=settings.azure_resource_group,
        aca_environment_name=settings.aca_environment_name,
        acr_login_server=settings.acr_login_server,
        managed_identity_id=settings.managed_identity_id,
        managed_identity_client_id=settings.managed_identity_client_id,
        cosmos_endpoint=settings.cosmos_endpoint,
    )

    try:
        # Pre-provision CosmosDB and seed data (don't rely on the LLM for this)
        logger.info("Creating Cosmos container %s/%s...", db_name, container_name)
        cosmos.create_container(db_name, container_name)
        logger.info("Seeding %d records...", len(sample_records))
        cosmos.seed_data(db_name, container_name, sample_records)

        client = CopilotClient()
        await client.start()

        tools = _make_tools(cosmos, acr, aca)
        prompt = _build_prompt(resource_name, schema, sample_records, deployment_id, app_name, image_tag, db_name, container_name)

        def _auto_approve(req, meta):
            return PermissionRequestResult(kind="approved", rules=[])

        def _on_event(event):
            etype = event.type.value if hasattr(event.type, "value") else event.type
            logger.info("Copilot event: %s", etype)

        session = await client.create_session({
            "model": "gpt-4.1",
            "system_message": {"mode": "append", "content": SYSTEM_PROMPT},
            "working_directory": work_dir,
            "on_permission_request": _auto_approve,
            "tools": tools,
        })
        session.on(_on_event)

        logger.info("Sending codegen prompt to Copilot SDK...")
        response = await session.send_and_wait({"prompt": prompt}, timeout=600)

        response_text = ""
        if response and hasattr(response, "data") and hasattr(response.data, "content"):
            response_text = response.data.content or ""
        logger.info("Agent response: %s", response_text[:500] if response_text else "(empty)")

        await session.destroy()
        await client.stop()

        url = aca.app_url
        endpoints = [
            {"method": "POST", "path": f"/api/{resource_name}"},
            {"method": "GET", "path": f"/api/{resource_name}"},
            {"method": "GET", "path": f"/api/{resource_name}/{{id}}"},
            {"method": "PATCH", "path": f"/api/{resource_name}/{{id}}"},
            {"method": "DELETE", "path": f"/api/{resource_name}/{{id}}"},
        ]

        return {
            "status": "succeeded" if url else "failed",
            "deployment_id": deployment_id,
            "api_base_url": url,
            "resource_name": resource_name,
            "cosmos_database": db_name,
            "cosmos_container": container_name,
            "container_app_name": app_name,
            "endpoints": endpoints,
            "error": None if url else "Deployment did not complete",
        }

    except Exception as e:
        logger.exception("Codegen pipeline failed")
        return {
            "status": "failed",
            "deployment_id": deployment_id,
            "resource_name": resource_name,
            "error": str(e),
        }
    finally:
        await cosmos.close()
