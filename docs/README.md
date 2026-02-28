# mcp-api-mock-gen

## The problem

When prototyping or developing software you constantly need mock data and APIs.
You need records in a specific structure, stored in a database, with CRUD
endpoints on top, and ideally some realistic synthetic data to showcase your
idea or test your UI. Setting this up manually is slow and repetitive --
especially when an AI agent is building your prototype and needs multiple APIs
at once.

## The solution

An MCP server that takes a resource name, a few example records, and an optional
data description, then delivers a fully deployed CRUD REST API backed by
CosmosDB with realistic generated data. The AI agent calling the MCP gets back a
live URL it can immediately wire into the UI it is building.

Under the hood the MCP server uses the GitHub Copilot SDK (running against your
own Azure OpenAI model -- no GitHub login required) to write the API code and
data generation scripts. If the generated code has issues, the SDK
self-corrects. Purpose-built tools let the SDK build Docker images, deploy
containers, run scripts, and verify the result -- all in an autonomous loop.

## How it works

```mermaid
flowchart LR
    Agent["Copilot CLI<br>or any MCP client"]
    MCP["MCP Server"]
    Cosmos[("CosmosDB")]
    ACR["Container<br>Registry"]
    AOAI["Azure OpenAI"]
    ACA["Container<br>Apps"]

    subgraph SDK ["GitHub Copilot SDK (gpt-5.3-codex)"]
        direction TB
        Writes["Writes code<br><i>main.py, Dockerfile,<br>requirements.txt,<br>generate_data.py</i>"]
        Tools["Uses tools<br><i>build_image<br>run_script<br>create_container_app<br>smoke_test</i>"]
        Writes --- Tools
        Tools -- "fix on error" --> Writes
    end

    Agent -- "create_mock_api()" --> MCP
    MCP -- "seed sample data" --> Cosmos
    MCP -- "start session" --> SDK

    Tools -- "build_image:<br>Docker build" --> ACR
    Tools -- "run_script: generate_data.py<br>generate + insert records" --> AOAI
    Tools -- "run_script: generate_data.py<br>insert records" --> Cosmos
    Tools -- "create_container_app:<br>deploy API" --> ACA
    Tools -- "smoke_test:<br>GET /api/..." --> ACA

    MCP -- "deployment_id +<br>api_base_url" --> Agent
```

The Copilot SDK does two things: it **writes code** (API server, Dockerfile,
data generation script) and it **calls tools** to execute that code against
Azure services. The `run_script` tool runs `generate_data.py` which calls
Azure OpenAI to generate records and inserts them directly into CosmosDB.
If any step fails, the SDK reads the error, fixes the code, and retries.

## Quick start

### 1. Deploy infrastructure

```bash
cd infra
terraform init
terraform apply \
  -var="subscription_id=YOUR_SUB_ID" \
  -var="mcp_api_key=YOUR_SECRET_KEY"
```

This creates everything in one step:

| Resource | Purpose |
|---|---|
| CosmosDB serverless | Data store for generated APIs (Entra-only) |
| Container Registry | Builds Docker images for each API |
| Container Apps Environment | Hosts generated APIs and the MCP server |
| AI Foundry + gpt-5.3-codex | Powers code generation and data synthesis |
| User-assigned managed identity | Entra auth across all services |
| **MCP server Container App** | The MCP endpoint itself |

Terraform outputs your MCP endpoint:

```
mcp_endpoint = "https://mcp-api-mock-gen.xxxxxxxx.swedencentral.azurecontainerapps.io/mcp"
```

### 2. Configure Copilot CLI

Create new folder, run copilot and configure the MCP server:

```bash
mkdir copilot-test
cd copilot-test
copilot
/mcp add  # Type http, paste the URL, and add the Authorization header with your MCP API key
```

### 3. Use it

Open Copilot CLI and describe what you need:

```
Build me an e-commerce dashboard with products, orders, and customers.
Generate 50 products, 200 orders, and 30 customers with realistic data, no image links.
Then create a React UI that displays everything. Run it for me, tell me how to access it.
```

Copilot will call the MCP server to spin up three live APIs with synthetic
data, then build a frontend connected to them.

Check your Azure portal to see the Container Apps, CosmosDB collections, and
ACR images that were created.

![](/images/cosmosdb.png)

![](/images/acr.png)

![](/images/resources.png)

## MCP tools

The server uses an async pattern: `create_mock_api` starts a background job
and returns immediately. Poll `get_deployment_status` until the job completes.

### create_mock_api

Starts a deployment (returns immediately).

| Parameter | Type | Required | Description |
|---|---|---|---|
| name | str | yes | Resource name (e.g. "products") |
| sample_records | list[dict] | yes | Example records (schema + seed data) |
| record_count | int | no | Synthetic records to generate (default: 0) |
| data_description | str | no | Guide for data generation |

Returns `deployment_id` and `status: "running"`.

### get_deployment_status

Poll this until `status` is `"succeeded"` or `"failed"`.

| Parameter | Type | Required | Description |
|---|---|---|---|
| deployment_id | str | yes | ID from create_mock_api |

Returns full deployment state including `api_base_url`, `endpoints`,
`records_seeded`, `records_generated` when succeeded.

### delete_mock_api

| Parameter | Type | Required | Description |
|---|---|---|---|
| deployment_id | str | yes | ID from create_mock_api |

Deletes the Container App and CosmosDB container.

## Tech stack

| Component | Technology |
|---|---|
| MCP server | FastMCP, StreamableHTTP transport |
| Code generation | GitHub Copilot SDK, Azure OpenAI BYOK (gpt-5.3-codex) |
| API hosting | Azure Container Apps |
| Image build | Azure Container Registry (ACR remote build) |
| Data store | Azure Cosmos DB serverless (Entra-only) |
| Data generation | Azure OpenAI Responses API, Pydantic structured outputs |
| Auth | User-assigned managed identity, Entra everywhere |
| Infrastructure | Terraform |
