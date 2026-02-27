"""Copilot SDK orchestration - generate and deploy CRUD API as a Docker container.

Creates a Copilot SDK session with custom tools (skills) and a detailed prompt,
then lets the agent generate FastAPI code + Dockerfile + optional data generation script
and deploy to Azure Container Apps.
"""

from __future__ import annotations

import json
import logging
import os
import tempfile
import uuid
from typing import Any

from copilot import CopilotClient
from copilot.types import Tool, PermissionRequestResult

from .config import Settings
from .schema import infer_schema, schema_summary, schema_to_pydantic_def
from .skills.acr import AcrSkills
from .skills.container_apps import ContainerAppsSkills
from .skills.cosmos import CosmosSkills
from .skills.scripts import ScriptSkills

logger = logging.getLogger(__name__)


def _get_azure_bearer_token(client_id: str | None = None) -> str:
    """Get an Azure bearer token for Cognitive Services using MI or CLI credential."""
    from azure.identity import ManagedIdentityCredential, AzureCliCredential
    scope = "https://cognitiveservices.azure.com/.default"
    try:
        if client_id:
            cred = ManagedIdentityCredential(client_id=client_id)
        else:
            cred = AzureCliCredential()
        token = cred.get_token(scope)
        return token.token
    except Exception:
        cred = AzureCliCredential()
        token = cred.get_token(scope)
        return token.token

SYSTEM_PROMPT_BASE = """You are a code generation agent that creates CRUD REST APIs packaged as Docker containers.
You will be given a resource name, its schema, and sample records.

Your job:
1. Generate a Python FastAPI project with a Dockerfile.
2. Use the provided tools to build the image, deploy as a Container App, and smoke test.

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

2. requirements.txt - EXACTLY these lines:
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
"""

SYSTEM_PROMPT_DEPLOY_ONLY = SYSTEM_PROMPT_BASE + """
AFTER generating ALL 3 files, call tools in this exact order:
1. build_image - build Docker image via ACR remote build (if it fails, fix the code and retry)
2. create_container_app - deploy the container
3. smoke_test - verify the API returns HTTP 200 on GET /api/{resource}

CosmosDB container creation and data seeding are already done.
After all steps complete, report the final API URL and endpoints.
Do NOT ask questions. Execute all steps.
"""

SYSTEM_PROMPT_WITH_DATAGEN = SYSTEM_PROMPT_BASE + """
4. generate_data.py - A data generation script that uses Azure OpenAI to generate synthetic records.
   This script MUST:
   - Use the openai library with AzureOpenAI client
   - Use azure.identity.AzureCliCredential with get_bearer_token_provider for Entra auth
   - Connect to the endpoint from AZURE_OPENAI_ENDPOINT env var using model "gpt-5.2"
   - Use the Responses API with structured outputs (text_format parameter) to enforce the schema
   - Define Pydantic models for the record schema (given below) and a list wrapper
   - Generate records in batches (batch_size items per API call)
   - For each generated record, add a UUID "id" field
   - Insert all generated records into CosmosDB using azure.cosmos SDK with AzureCliCredential
   - Read COSMOS_ENDPOINT, COSMOS_DATABASE, COSMOS_CONTAINER from environment variables
   - Print progress and final count to stdout
   - The script structure should be:
     ```python
     import os, uuid, json
     from pydantic import BaseModel
     from openai import AzureOpenAI
     from azure.identity import AzureCliCredential, get_bearer_token_provider
     from azure.cosmos import CosmosClient

     # Pydantic models for structured output
     <SCHEMA_MODELS>

     # Azure OpenAI setup
     credential = AzureCliCredential()
     token_provider = get_bearer_token_provider(credential, "https://cognitiveservices.azure.com/.default")
     ai_client = AzureOpenAI(
         azure_endpoint=os.environ["AZURE_OPENAI_ENDPOINT"],
         azure_ad_token_provider=token_provider,
         api_version="2025-03-01-preview",
     )

     # CosmosDB setup
     cosmos_client = CosmosClient(os.environ["COSMOS_ENDPOINT"], credential)
     database = cosmos_client.get_database_client(os.environ["COSMOS_DATABASE"])
     container = database.get_container_client(os.environ["COSMOS_CONTAINER"])

     # Generate in batches
     total = <RECORD_COUNT>
     batch_size = min(20, total)
     generated = 0
     for batch_num in range(0, total, batch_size):
         count = min(batch_size, total - generated)
         response = ai_client.responses.parse(
             model="gpt-5.2",
             input=[{"role": "user", "content": f"Generate {count} realistic <DESCRIPTION>"}],
             text_format=<LIST_MODEL>,
         )
         items = response.output_parsed.items
         for item in items:
             doc = item.model_dump()
             doc["id"] = str(uuid.uuid4())
             container.upsert_item(doc)
             generated += 1
         print(f"Generated {generated}/{total} records")
     print(f"Done. Total records generated: {generated}")
     ```

AFTER generating ALL 4 files, call tools in this exact order:
1. build_image - build Docker image (only main.py, requirements.txt, Dockerfile - NOT generate_data.py)
2. run_script - execute generate_data.py to populate CosmosDB with synthetic data
   If it fails, read the error, fix generate_data.py, and run it again.
3. create_container_app - deploy the container
4. smoke_test - verify the API returns HTTP 200 and data is available

CosmosDB container creation and sample data seeding are already done.
After all steps complete, report the final API URL, endpoints, and records generated count.
Do NOT ask questions. Execute all steps.
"""


def _build_prompt(resource_name: str, schema: dict, sample_records: list[dict],
                  deployment_id: str, app_name: str, image_tag: str,
                  db_name: str, container_name: str,
                  record_count: int = 0, data_description: str = "",
                  pydantic_schema: str = "") -> str:
    base = f"""Create a CRUD API for resource "{resource_name}".

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
"""
    if record_count > 0:
        base += f"""
Data generation parameters:
- record_count: {record_count}
- data_description: {data_description or f"realistic {resource_name} data matching the schema"}
- Pydantic models to use in generate_data.py for structured outputs:
```python
{pydantic_schema}
```

Generate all 4 files (main.py, requirements.txt, Dockerfile, generate_data.py), then use tools to deploy and generate data.
"""
    else:
        base += "\nGenerate all 3 files (main.py, requirements.txt, Dockerfile), then use the tools to deploy.\n"

    base += "Go step by step."
    return base


def _make_tools(cosmos: CosmosSkills, acr: AcrSkills, aca: ContainerAppsSkills, scripts: ScriptSkills) -> list[Tool]:
    """Create Copilot SDK Tool definitions wired to skill handlers."""

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
        import time, urllib.request, urllib.error
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
                return json.dumps({"status": "error", "http_status": e.code, "body": body, "url": url, "message": f"HTTP {e.code}: {body}"})
            except Exception as e:
                if attempt < 2:
                    time.sleep(15)
                    continue
                return json.dumps({"status": "error", "message": f"Smoke test failed: {e}", "url": url})

    def _run_script(call_info) -> str:
        try:
            a = call_info.get("arguments", {})
            return scripts.run_python_script(a.get("script_path", ""), a.get("working_directory", ""))
        except Exception as e:
            logger.exception("run_script failed")
            return json.dumps({"status": "error", "message": str(e)})

    return [
        Tool(name="build_image", description="Build Docker image via ACR remote build. Returns build errors if any — fix code and retry.", handler=_build_image,
             parameters={"type": "object", "properties": {"image_tag": {"type": "string", "description": "Image name:tag"}, "code_directory": {"type": "string", "description": "Path to directory with Dockerfile"}}, "required": ["image_tag", "code_directory"]}),
        Tool(name="create_container_app", description="Create Azure Container App from ACR image.", handler=_create_container_app,
             parameters={"type": "object", "properties": {"app_name": {"type": "string"}, "image_tag": {"type": "string"}, "database_name": {"type": "string"}, "container_name": {"type": "string"}}, "required": ["app_name", "image_tag", "database_name", "container_name"]}),
        Tool(name="smoke_test", description="HTTP GET to verify the API is accessible. Returns response body.", handler=_smoke_test,
             parameters={"type": "object", "properties": {"url": {"type": "string", "description": "Full URL to test"}}, "required": ["url"]}),
        Tool(name="run_script", description="Execute a Python script locally. Use this to run generate_data.py. Returns stdout/stderr.", handler=_run_script,
             parameters={"type": "object", "properties": {"script_path": {"type": "string", "description": "Name of the script file (e.g. generate_data.py)"}, "working_directory": {"type": "string", "description": "Directory containing the script"}}, "required": ["script_path", "working_directory"]}),
    ]


async def run_codegen(
    resource_name: str,
    sample_records: list[dict],
    settings: Settings,
    record_count: int = 0,
    data_description: str = "",
) -> dict[str, Any]:
    """Run the full code generation and deployment pipeline via Copilot SDK."""
    deployment_id = str(uuid.uuid4())[:8]
    safe_name = resource_name.lower().replace(" ", "").replace("_", "")[:20]
    app_name = f"mock-{safe_name}-{deployment_id}"
    image_tag = f"mock-{safe_name}-{deployment_id}:latest"
    db_name = "mockapi"
    container_name = f"{safe_name}_{deployment_id}"

    schema = infer_schema(sample_records)
    pydantic_schema = schema_to_pydantic_def(schema, class_name=resource_name.capitalize().rstrip("s"))
    work_dir = tempfile.mkdtemp(prefix="mcpgen_")
    logger.info("Deployment %s: work_dir=%s, app=%s, record_count=%d", deployment_id, work_dir, app_name, record_count)

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
    scripts = ScriptSkills(env_overrides={
        "COSMOS_ENDPOINT": settings.cosmos_endpoint,
        "COSMOS_DATABASE": db_name,
        "COSMOS_CONTAINER": container_name,
        "AZURE_OPENAI_ENDPOINT": settings.azure_openai_endpoint,
    })

    try:
        # Pre-provision CosmosDB and seed sample data
        logger.info("Creating Cosmos container %s/%s...", db_name, container_name)
        cosmos.create_container(db_name, container_name)
        logger.info("Seeding %d sample records...", len(sample_records))
        cosmos.seed_data(db_name, container_name, sample_records)

        client = CopilotClient()
        await client.start()

        tools = _make_tools(cosmos, acr, aca, scripts)
        system_prompt = SYSTEM_PROMPT_WITH_DATAGEN if record_count > 0 else SYSTEM_PROMPT_DEPLOY_ONLY
        prompt = _build_prompt(
            resource_name, schema, sample_records,
            deployment_id, app_name, image_tag, db_name, container_name,
            record_count, data_description, pydantic_schema,
        )

        def _auto_approve(req, meta):
            return PermissionRequestResult(kind="approved", rules=[])

        def _on_event(event):
            etype = event.type.value if hasattr(event.type, "value") else event.type
            logger.info("Copilot event: %s", etype)

        # Use Azure BYOK provider — works without GitHub auth
        bearer_token = _get_azure_bearer_token(
            client_id=os.environ.get("AZURE_CLIENT_ID") or settings.managed_identity_client_id
        )
        session = await client.create_session({
            "model": settings.codex_model,
            "provider": {
                "type": "azure",
                "base_url": settings.azure_openai_endpoint.rstrip("/"),
                "bearer_token": bearer_token,
                "wire_api": "responses",
                "azure": {"api_version": "2025-03-01-preview"},
            },
            "system_message": {"mode": "append", "content": system_prompt},
            "working_directory": work_dir,
            "on_permission_request": _auto_approve,
            "tools": tools,
        })
        session.on(_on_event)

        logger.info("Sending codegen prompt to Copilot SDK...")
        response = await session.send_and_wait({"prompt": prompt}, timeout=900)

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
            "records_seeded": len(sample_records),
            "records_generated": record_count,
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
