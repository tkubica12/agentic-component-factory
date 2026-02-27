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

```
+------------------+                              +---------------------------+
|  Copilot CLI     |  create_mock_api(            |  MCP Server               |
|  or any          |    name, sample_records,     |  (Container App in Azure) |
|  MCP client      |    record_count,             |                           |
|                  |    data_description)         |                           |
+--------+---------+ ---------------------------> +------------+--------------+
         |                                                      |
         |                                         1. Create CosmosDB container
         |                                            and seed sample records
         |                                                      |
         |                                         2. Start Copilot SDK session
         |                                            with 4 custom tools
         |                                                      |
         |                                         +------------v--------------+
         |                                         |  GitHub Copilot SDK       |
         |                                         |  (Azure OpenAI BYOK)      |
         |                                         |                           |
         |                                         |  Codes files:             |
         |                                         |   - main.py (FastAPI)     |
         |                                         |   - Dockerfile            |
         |                                         |   - requirements.txt      |
         |                                         |   - generate_data.py      |
         |                                         |                           |
         |                                         |  Calls tools:             |
         |                                         |                           |
         |                                         |  [build_image]            |
         |                                         |   Code -> ACR -> Image    |
         |                                         |                           |
         |                                         |  [run_script]             |
         |                                         |   generate_data.py        |
         |                                         |   -> Azure OpenAI         |
         |                                         |      (structured outputs) |
         |                                         |   -> records into Cosmos  |
         |                                         |                           |
         |                                         |  [create_container_app]   |
         |                                         |   Image -> Container App  |
         |                                         |                           |
         |                                         |  [smoke_test]             |
         |                                         |   GET /api/{resource}     |
         |                                         |   -> 200 OK               |
         |                                         |                           |
         |                                         |  Repair if errors ^       |
         |                                         +---------------------------+
         |
         |  { deployment_id, api_base_url,
         |    endpoints, records_seeded,
<--------+    records_generated }
```

The SDK writes code using its own built-in file tools, then calls custom tools
provided by the MCP server to build, deploy, generate data, and verify. If any
step fails (Docker build error, script crash), the SDK reads the error output,
fixes the code, and retries autonomously.

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

Add the MCP server to your Copilot CLI config:

**Linux/macOS:** `~/.config/github-copilot/config.yml`
**Windows:** `%APPDATA%\github-copilot\config.yml`

```yaml
mcpServers:
  mock-api:
    url: https://mcp-api-mock-gen.xxxxxxxx.swedencentral.azurecontainerapps.io/mcp
    headers:
      Authorization: Bearer YOUR_SECRET_KEY
```

### 3. Use it

Open Copilot CLI and describe what you need:

```
Build me an e-commerce dashboard with products, orders, and customers.
Generate 50 products, 200 orders, and 30 customers with realistic data.
Then create a React UI that displays everything.
```

Copilot will call the MCP server to spin up three live APIs with synthetic
data, then build a frontend connected to them.

## Demo scenario

```
User:
  Build a project management app with projects, tasks, and team members.
  Generate 30 projects, 100 tasks, and 20 team members.
  Build a React dashboard.

Copilot CLI:
  Step 1/4 -- Creating Projects API
    create_mock_api(name="projects", sample_records=[...], record_count=30,
      data_description="software projects, statuses: planning/in_progress/completed")
    -> https://mock-projects-f4a1b2c3.....azurecontainerapps.io
       32 records (2 seeded + 30 generated)

  Step 2/4 -- Creating Tasks API
    create_mock_api(name="tasks", sample_records=[...], record_count=100,
      data_description="dev tasks, priorities: low/medium/high/critical")
    -> https://mock-tasks-e5d6c7b8.....azurecontainerapps.io
       102 records

  Step 3/4 -- Creating Team Members API
    create_mock_api(name="members", sample_records=[...], record_count=20,
      data_description="team across Engineering/Design/Product/QA")
    -> https://mock-members-a9b8c7d6.....azurecontainerapps.io
       22 records

  Step 4/4 -- Building React Dashboard
    Done! Running at http://localhost:3000 with 156 records.

  Clean up:  delete_mock_api("f4a1b2c3"), delete_mock_api("e5d6c7b8"), ...
```

Check your Azure portal to see the Container Apps, CosmosDB collections, and
ACR images that were created.

## MCP tools

### create_mock_api

| Parameter | Type | Required | Description |
|---|---|---|---|
| name | str | yes | Resource name (e.g. "products") |
| sample_records | list[dict] | yes | Example records (schema + seed data) |
| record_count | int | no | Synthetic records to generate (default: 0) |
| data_description | str | no | Guide for data generation |

Returns `deployment_id`, `api_base_url`, `endpoints`, `records_seeded`,
`records_generated`.

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
