# mcp-api-mock-gen

Python MCP server that generates and deploys CRUD REST APIs from sample JSON data.

## What it does

Give it a resource name and a few example records — it generates a FastAPI app as a Docker container, provisions a CosmosDB container, seeds the data, builds and deploys to Azure Container Apps. You get back a live API URL with full CRUD endpoints.

## Current status

**Working end-to-end:**
- `create_mock_api` MCP tool — generates, builds, and deploys a containerised CRUD API
- `delete_mock_api` MCP tool — tears down Container App and Cosmos container
- Generates Python code (FastAPI + uvicorn), `requirements.txt`, and `Dockerfile`
- Builds via ACR remote build (`az acr build`)
- Deploys to Azure Container Apps (0.25 vCPU / 0.5 Gi, external ingress, port 8000)
- Creates CosmosDB container and seeds sample records
- Each deployment gets a unique GUID-based ID (8-char UUID4 prefix)

**Not yet implemented (deferred):**
- Synthetic data generation (`generate_synthetic_data`)
- Operation status polling (`get_operation_status`)
- Deployment listing (`list_deployments`)

## How it works

1. The FastMCP server receives `name` + `sample_records` from the caller.
2. Schema is inferred from the sample data.
3. A GitHub Copilot SDK session generates `main.py` (FastAPI + uvicorn), `requirements.txt`, and `Dockerfile`.
4. Custom skills create the CosmosDB container, seed data, build the Docker image via ACR remote build, create a Container App, and run a smoke test.
5. The deployed API URL and endpoints are returned.

All Azure configuration (subscription, resource group, Cosmos account, ACR, Container Apps Environment, managed identity) comes from environment variables — callers only provide `name` and `sample_records`.

## Prerequisites

- Python 3.11+
- [uv](https://docs.astral.sh/uv/) for package management
- Azure CLI (`az`) logged in with sufficient permissions
- Azure subscription with shared infrastructure deployed (see below)
- GitHub Copilot SDK access

## Setup

### 1. Deploy shared infrastructure

```bash
cd infra
terraform init
terraform apply -var="subscription_id=YOUR_SUB_ID"
```

This creates: Resource Group, CosmosDB serverless (Entra-only), Azure Container Registry (Basic SKU), Container Apps Environment, user-assigned managed identity with Cosmos RBAC and ACR Pull, current user Cosmos RBAC and ACR Push.

### 2. Configure environment

Copy `.env.example` to `.env` and fill in the Terraform outputs:

```bash
cp .env.example .env
```

Required variables (see `src/mcp_api_mock_gen/config.py`):
- `AZURE_SUBSCRIPTION_ID`
- `AZURE_RESOURCE_GROUP`
- `AZURE_LOCATION`
- `COSMOS_ACCOUNT_NAME`
- `COSMOS_ENDPOINT`
- `ACR_NAME`
- `ACR_LOGIN_SERVER`
- `ACA_ENVIRONMENT_NAME`
- `MANAGED_IDENTITY_ID`
- `MANAGED_IDENTITY_CLIENT_ID`

### 3. Install dependencies

```bash
uv sync
```

## Running

### MCP server (stdio transport)

```bash
uv run python -m mcp_api_mock_gen.server
```

### Test client (in-process)

```bash
uv run python tests/test_client.py
```

This connects to the MCP server in-process via FastMCP Client and calls `create_mock_api` with sample product data.

## MCP tool contracts

### `create_mock_api`

**Input:**
- `name: str` — Resource name (e.g. `"products"`)
- `sample_records: list[dict]` — One or more example JSON records

**Output:**
- `status` — `"succeeded"` or `"failed"`
- `deployment_id` — Unique 8-char ID for this deployment
- `api_base_url` — e.g. `https://mock-products-a1b2c3d4.nicemeadow-abc123.eastus.azurecontainerapps.io`
- `endpoints` — list of `{method, path}`
- `error` — error message if failed

### `delete_mock_api`

**Input:**
- `deployment_id: str` — The deployment ID returned by `create_mock_api`

**Output:**
- `status` — `"succeeded"` or `"failed"`
- `error` — error message if failed

## Tech stack

- **MCP server**: [FastMCP](https://github.com/jlowin/fastmcp) (Python)
- **Code generation**: GitHub Copilot SDK with custom skill handlers
- **Compute**: Azure Container Apps (Docker containers, 0.25 vCPU / 0.5 Gi)
- **Container registry**: Azure Container Registry (Basic SKU, ACR remote build)
- **Data**: Azure Cosmos DB serverless (Entra-only auth)
- **Identity**: User-assigned managed identity (Cosmos RBAC + ACR Pull)
- **IaC**: Terraform (shared infra only; Container Apps created at runtime via `az` CLI)

## Architecture docs

- Product requirements: [PRD.md](PRD.md)
- Technical design: [ARCHITECTURE.md](ARCHITECTURE.md)
- Agent conventions: [AGENTS.md](AGENTS.md)