# Development Guide

Local development, building, and testing instructions for contributors.

## Prerequisites

- Python 3.11+
- [uv](https://docs.astral.sh/uv/) for package management
- Azure CLI (`az`) logged in
- Azure subscription with infrastructure deployed (see main README)
- GitHub Copilot CLI (for local Copilot SDK testing)

## Setup

```bash
# Clone and install
git clone https://github.com/tkubica12/mcp-api-mock-gen.git
cd mcp-api-mock-gen
uv sync

# Configure environment
cp .env.example .env
# Fill in values from Terraform outputs (see README)
```

## Running locally

### MCP server (stdio transport, for in-process testing)

```bash
uv run python tests/test_client.py
```

This starts the MCP server in-process and runs the full E2E test: creates an API
with synthetic data, verifies all CRUD operations, then deletes the deployment.

### MCP server (StreamableHTTP, for remote-like testing)

```bash
uv run python run_server.py
# In another terminal:
MCP_URL=http://localhost:8000/mcp uv run python tests/test_remote.py
```

### Worker (Service Bus listener)

```bash
uv run python run_worker.py
```

The worker connects to Service Bus, listens for messages on the `mock-api-jobs` queue, and processes jobs using the Copilot SDK.

## Building the Docker image

### Build locally

```bash
# MCP server
docker build -t mcp-api-mock-gen .
# Worker
docker build -f Dockerfile.worker -t mcp-api-mock-gen-worker .
```

### Build via ACR

```bash
az acr build --registry YOUR_ACR_NAME --image mcp-api-mock-gen:latest .
az acr build --registry YOUR_ACR_NAME --image mcp-api-mock-gen-worker:latest -f Dockerfile.worker .
```

### Push to GHCR (done automatically by GitHub Actions)

The `.github/workflows/build.yml` workflow builds and pushes both images on every push to `main`:
- `ghcr.io/tkubica12/mcp-api-mock-gen:latest` (server)
- `ghcr.io/tkubica12/mcp-api-mock-gen-worker:latest` (worker)

## Project structure

```
src/mcp_api_mock_gen/
  server.py           FastMCP server with create_mock_api + delete_mock_api (lightweight)
  state.py             CosmosDB job state read/write (jobs container)
  worker.py            Worker: Service Bus listener, runs Copilot SDK per message
  codegen.py           Copilot SDK orchestration, prompts, tool wiring
  config.py            Settings from environment variables
  contracts.py         Pydantic models for MCP I/O
  schema.py            Schema inference + Pydantic model generation
  skills/
    cosmos.py          CosmosDB: create container, seed data, delete
    acr.py             ACR remote build
    container_apps.py  Container App create/delete
    scripts.py         Local Python script execution

tests/
  test_client.py       In-process E2E test (stdio)
  test_remote.py       Remote E2E test (StreamableHTTP)

infra/                 Terraform for all shared infrastructure + MCP server + Worker
run_server.py          MCP server entrypoint
run_worker.py          Worker entrypoint
Dockerfile             MCP server image
Dockerfile.worker      Worker image
entrypoint.sh          MCP server container entrypoint script
entrypoint_worker.sh   Worker container entrypoint script
```

## Environment variables

See `.env.example` for the full list. Key variables:

| Variable | Description |
|---|---|
| `AZURE_SUBSCRIPTION_ID` | Azure subscription |
| `AZURE_RESOURCE_GROUP` | Resource group for all resources |
| `COSMOS_ENDPOINT` | CosmosDB serverless endpoint |
| `ACR_NAME` / `ACR_LOGIN_SERVER` | Container registry for API images |
| `ACA_ENVIRONMENT_NAME` | Container Apps environment |
| `MANAGED_IDENTITY_ID` / `CLIENT_ID` | User-assigned MI for Entra auth |
| `AZURE_OPENAI_ENDPOINT` | AI Foundry endpoint for code gen + data gen |
| `CODEX_MODEL` | Model deployment name (default: `gpt-53-codex`) |
| `SERVICE_BUS_NAMESPACE` | Service Bus namespace (e.g. `myns.servicebus.windows.net`) |
| `MCP_API_KEY` | API key for remote MCP endpoint protection |

## Testing

```bash
# Full E2E (creates real Azure resources)
uv run python tests/test_client.py

# Remote E2E (against deployed MCP server)
MCP_URL=https://your-mcp.azurecontainerapps.io/mcp uv run python tests/test_remote.py
```

## Architecture docs

- [README.md](README.md) - Main documentation
- [PRD.md](PRD.md) - Product requirements
- [ARCHITECTURE.md](ARCHITECTURE.md) - Technical design
