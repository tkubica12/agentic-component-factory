# mcp-api-mock-gen

Python MCP server that generates and deploys CRUD REST APIs from sample JSON data.

## What it does

Give it a resource name and a few example records -- it generates a FastAPI app as a Docker container, provisions a CosmosDB container, seeds the data, builds and deploys to Azure Container Apps. You get back a live API URL with full CRUD endpoints. Optionally, request synthetic data generation using Azure OpenAI structured outputs.

```
                         mcp-api-mock-gen
                         ================

  Calling Agent                MCP Server              GitHub Copilot SDK
  (Copilot CLI)                (FastMCP)               (Code Generation)
       |                          |                          |
       |  create_mock_api(        |                          |
       |    name="products",      |                          |
       |    sample_records=[..],  |                          |
       |    record_count=50,      |                          |
       |    data_description=".." |                          |
       |  )                       |                          |
       |------------------------->|                          |
       |                          |                          |
       |                          |  1. Create Cosmos        |
       |                          |     container + seed     |
       |                          |     sample data          |
       |                          |                          |
       |                          |  2. Start SDK session    |
       |                          |     with skills/tools    |
       |                          |------------------------->|
       |                          |                          |
       |                          |     +--------------------+----------+
       |                          |     | Copilot SDK generates:       |
       |                          |     |  - main.py (FastAPI + CRUD)  |
       |                          |     |  - Dockerfile                |
       |                          |     |  - requirements.txt          |
       |                          |     |  - generate_data.py          |
       |                          |     +------------------------------+
       |                          |                          |
       |                          |     Calls skills:        |
       |                          |                          |
       |                          |     [build_image]        |
       |                          |     Code -----> ACR Remote Build ---> Docker Image
       |                          |                          |
       |                          |     [run_script]         |
       |                          |     generate_data.py --> Azure OpenAI (gpt-5.2)
       |                          |       |                    Structured Outputs
       |                          |       +---> CosmosDB       (Pydantic models)
       |                          |             (50 records)
       |                          |                          |
       |                          |     [create_container_app]
       |                          |     Docker Image ------> Azure Container Apps
       |                          |                          |
       |                          |     [smoke_test]         |
       |                          |     GET /api/products -> 200 OK
       |                          |<-------------------------|
       |                          |                          |
       |  {                       |
       |    deployment_id: "a1b2",|
       |    api_base_url: "https://mock-products-a1b2.....io",
       |    records_seeded: 3,    |
       |    records_generated: 50,|
       |    endpoints: [...]      |
       |  }                       |
       |<-------------------------|
```

## Current status

**Working end-to-end:**
- `create_mock_api` MCP tool — generates, builds, and deploys a containerised CRUD API
- `delete_mock_api` MCP tool — tears down Container App and Cosmos container
- Generates Python code (FastAPI + uvicorn), `requirements.txt`, and `Dockerfile`
- Builds via ACR remote build (`az acr build`)
- Deploys to Azure Container Apps (0.25 vCPU / 0.5 Gi, external ingress, port 8000)
- Creates CosmosDB container and seeds sample records
- Synthetic data generation via `create_mock_api` — generates a `generate_data.py` script using Azure OpenAI Responses API with structured outputs (Pydantic models) and inserts records into CosmosDB
- Each deployment gets a unique GUID-based ID (8-char UUID4 prefix)

**Not yet implemented (deferred):**
- Operation status polling (`get_operation_status`)
- Deployment listing (`list_deployments`)

## How it works

1. The FastMCP server receives `name` + `sample_records` (plus optional `record_count` and `data_description`) from the caller.
2. Schema is inferred from the sample data (including Pydantic model definitions for structured outputs).
3. A GitHub Copilot SDK session generates `main.py` (FastAPI + uvicorn), `requirements.txt`, and `Dockerfile`.
4. Custom skills create the CosmosDB container, seed data, build the Docker image via ACR remote build, create a Container App, and run a smoke test.
5. If `record_count > 0`, the Copilot SDK agent generates a `generate_data.py` script that uses Azure OpenAI Responses API (gpt-5.2, Entra auth) with structured outputs to produce realistic records and insert them into CosmosDB.
6. The `run_script` skill executes the data generation script locally.
7. The deployed API URL and endpoints are returned.

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
- `AZURE_OPENAI_ENDPOINT` — Azure OpenAI endpoint for synthetic data generation

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

### Tesst client (streamable http)

```bash
uv run python tests/test_remote.py
```

## MCP tool contracts

### `create_mock_api`

**Input:**
- `name: str` — Resource name (e.g. `"products"`)
- `sample_records: list[dict]` — One or more example JSON records (schema + seed data)
- `record_count: int` (optional, default 0) — Number of synthetic records to generate
- `data_description: str` (optional) — Natural language description to guide synthetic data generation

**Output:**
- `status` — `"succeeded"` or `"failed"`
- `deployment_id` — Unique 8-char ID for this deployment
- `api_base_url` — e.g. `https://mock-products-a1b2c3d4.nicemeadow-abc123.eastus.azurecontainerapps.io`
- `endpoints` — list of `{method, path}`
- `records_seeded: int` — Number of sample records seeded
- `records_generated: int` — Number of synthetic records generated
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
- **Synthetic data**: Azure OpenAI Responses API (gpt-5.2) with structured outputs (Pydantic models), Entra auth via `AzureCliCredential`
- **Identity**: User-assigned managed identity (Cosmos RBAC + ACR Pull)
- **IaC**: Terraform (shared infra only; Container Apps created at runtime via `az` CLI)

## Architecture docs

- Product requirements: [PRD.md](PRD.md)
- Technical design: [ARCHITECTURE.md](ARCHITECTURE.md)
- Agent conventions: [AGENTS.md](AGENTS.md)

## Demo: building a complete app with Copilot CLI

This example shows a user in Copilot CLI asking to build a project management
application. Copilot uses this MCP server to create three backend APIs with
realistic data, then builds a React UI on top of them.

```
User:
  Build me a project management app with projects, tasks, and team members.
  Each project has a name, description, status, and due date.
  Tasks belong to projects and have a title, priority, assignee, and done flag.
  Team members have a name, email, role, and department.
  Generate 30 projects, 100 tasks, and 20 team members with realistic data.
  Then build a React dashboard UI that connects to these APIs.

Copilot CLI:
  I'll create three backend APIs with synthetic data, then build the UI.

  --- Step 1: Create Projects API ---

  Calling MCP tool: create_mock_api(
    name="projects",
    sample_records=[
      {"id": "1", "name": "Website Redesign", "description": "Modernize the company website",
       "status": "in_progress", "due_date": "2026-06-15"},
      {"id": "2", "name": "Mobile App", "description": "Build iOS and Android app",
       "status": "planning", "due_date": "2026-09-01"}
    ],
    record_count=30,
    data_description="realistic software projects with varied statuses
      (planning, in_progress, review, completed, on_hold) and due dates
      spread across 2026"
  )

  Result:
    deployment_id: "f4a1b2c3"
    api_base_url:  https://mock-projects-f4a1b2c3.....azurecontainerapps.io
    records_seeded: 2, records_generated: 30
    endpoints: POST/GET/GET{id}/PATCH/DELETE /api/projects

  --- Step 2: Create Tasks API ---

  Calling MCP tool: create_mock_api(
    name="tasks",
    sample_records=[
      {"id": "1", "title": "Design homepage mockup", "project_id": "1",
       "priority": "high", "assignee": "Alice", "done": false},
      {"id": "2", "title": "Set up CI/CD pipeline", "project_id": "2",
       "priority": "medium", "assignee": "Bob", "done": true}
    ],
    record_count=100,
    data_description="software development tasks with varied priorities
      (low, medium, high, critical), different assignee names, and a mix
      of done/not-done states across different project_ids from 1 to 30"
  )

  Result:
    deployment_id: "e5d6c7b8"
    api_base_url:  https://mock-tasks-e5d6c7b8.....azurecontainerapps.io
    records_seeded: 2, records_generated: 100

  --- Step 3: Create Team Members API ---

  Calling MCP tool: create_mock_api(
    name="members",
    sample_records=[
      {"id": "1", "name": "Alice Chen", "email": "alice@example.com",
       "role": "Frontend Developer", "department": "Engineering"},
      {"id": "2", "name": "Bob Martinez", "email": "bob@example.com",
       "role": "DevOps Engineer", "department": "Engineering"}
    ],
    record_count=20,
    data_description="diverse team members across departments (Engineering,
      Design, Product, QA, Management) with realistic names and email
      addresses"
  )

  Result:
    deployment_id: "a9b8c7d6"
    api_base_url:  https://mock-members-a9b8c7d6.....azurecontainerapps.io
    records_seeded: 2, records_generated: 20

  --- Step 4: Build React Dashboard ---

  Creating React app with:
    - Project list view with status badges and progress bars
    - Task board grouped by project with priority indicators
    - Team directory with department filters
    - Dashboard with summary stats

  API connections:
    REACT_APP_PROJECTS_API=https://mock-projects-f4a1b2c3.....azurecontainerapps.io
    REACT_APP_TASKS_API=https://mock-tasks-e5d6c7b8.....azurecontainerapps.io
    REACT_APP_MEMBERS_API=https://mock-members-a9b8c7d6.....azurecontainerapps.io

  Done! Your project management app is running at http://localhost:3000
  with 3 live APIs serving 152 records of realistic data.

  When you are done, clean up with:
    delete_mock_api("f4a1b2c3")
    delete_mock_api("e5d6c7b8")
    delete_mock_api("a9b8c7d6")
```