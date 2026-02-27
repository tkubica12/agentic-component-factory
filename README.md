# mcp-api-mock-gen

Python MCP server for rapidly creating mocked REST APIs from JSON examples.

## What it does

- Accepts JSON example data (one or more records).
- Generates and deploys a CRUD-style API to Azure Functions.
- Stores seed/generated data in Azure Cosmos DB (serverless).
- Supports synthetic data generation from schema + field description + record count.

## Why

Accelerate prototyping: ask an agent for APIs, then immediately build UI on top of those APIs.

## Planned capabilities (MVP)

- Create API from sample JSON.
- Standard endpoints: create, list (exact-match filtering), get by id, patch, delete.
- Cosmos DB collection provisioning and initial data load.
- Optional synthetic data generation in batches (up to 10,000 records per operation by default).
- Generate basic OpenAPI/Swagger for each generated API.
- Return deployment + endpoint metadata back to calling agent.

## Tech stack

- Python
- FastMCP (MCP server)
- GitHub Copilot SDK (code generation/orchestration)
- Azure Functions (Python)
- Azure Cosmos DB serverless

## Repository docs

- Product requirements: [PRD.md](PRD.md)
- Technical design: [ARCHITECTURE.md](ARCHITECTURE.md)

## Current status

Documentation-first project setup. Next step is implementing MCP tools and an end-to-end demo.