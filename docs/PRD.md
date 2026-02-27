# Product Requirements Document (PRD)

## Overview

`mcp-api-mock-gen` is a FastMCP server that lets an AI agent create a mock REST API from sample JSON records. It orchestrates code generation, Docker build, and deployment to Azure Container Apps with CosmosDB serverless as the data store.

## Problem

Teams prototyping with AI need mock APIs quickly. Building CRUD backends, creating datasets, and deploying containers manually is slow and repetitive — especially when an agent needs multiple APIs at once.

## Goals

1. Generate deployable mock REST APIs in minutes from sample JSON.
2. Seed provided records and optionally generate synthetic data.
3. Provide standard CRUD endpoints with basic filtering.
4. Return machine-consumable API details for downstream agent workflows.

## Non-Goals

- Production auth/authorization and enterprise IAM
- Custom business logic generation
- Advanced API versioning

## MCP Tools

### `create_mock_api`

Azure infrastructure config is read from server-side env vars — callers only supply data.

**Input**

| Parameter | Type | Required | Description |
|---|---|---|---|
| `name` | `str` | yes | Resource name (e.g. `"products"`) |
| `sample_records` | `list[dict]` | yes | Example records (defines schema + seed data) |
| `record_count` | `int` | no | Synthetic records to generate (default: 0) |
| `data_description` | `str` | no | Natural language guidance for data generation |

**Output** — `deployment_id`, `api_base_url`, `endpoints`, `records_seeded`, `records_generated`, `status`, `error`.

### `delete_mock_api`

**Input** — `deployment_id: str`
**Output** — `status`, `error`

Deletes the Container App and CosmosDB container matching the deployment ID.

## Generated API

Each generated API is a FastAPI service with sync Cosmos SDK + `ManagedIdentityCredential`:

- `POST /api/{resource}` — create
- `GET /api/{resource}` — list (`enable_cross_partition_query=True`)
- `GET /api/{resource}/{id}` — get one
- `PATCH /api/{resource}/{id}` — partial update
- `DELETE /api/{resource}/{id}` — delete

## Schema Inference

- Fields and types inferred from sample records.
- `id` policy: use provided `id` if present and unique, else generate UUID.
- Default partition key: `/id`.

## Synthetic Data Generation

Integrated into `create_mock_api` via `record_count` and `data_description` parameters.

- Copilot SDK generates `generate_data.py` using inferred schema.
- Script uses `openai` library with `AzureOpenAI` client.
- Auth: `ManagedIdentityCredential` or `AzureCliCredential` depending on environment.
- Responses API with `text_format` (Pydantic structured outputs).
- Model name from `DATAGEN_MODEL` env var.
- Generates in batches, inserts into CosmosDB.
- `run_script` tool executes the script locally.

## Deployment Behavior

- Docker image built via ACR remote build (`az acr build --no-logs`).
- One Container App per API: 0.25 vCPU, 0.5Gi, external ingress, user-assigned MI.
- Deployment ID: 8-char UUID4 prefix.
- Smoke test (HTTP GET with retries) verifies 200 OK before returning.

## Non-Functional Requirements

- **Language**: Python for MCP server and all generated code.
- **Latency**: API generation < 10 min for simple schemas.
- **Security**: Entra-only auth everywhere; no secrets in source code.
- **Error handling**: Copilot SDK self-corrects — reads errors, fixes code, retries.

## Risks and Mitigations

| Risk | Mitigation |
|---|---|
| LLM produces invalid code | Schema validation + SDK regeneration loop |
| Azure deployment failures | Actionable error output fed back to SDK |
| Data quality issues | Pydantic structured outputs enforce schema |
| Cost drift | Batch limits on synthetic generation |
