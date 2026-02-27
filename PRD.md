# Product Requirements Document (PRD)

## 1. Overview

`mcp-api-mock-gen` is a Python-based MCP server that enables an AI agent to create a realistic mock REST API from sample JSON data with minimal user input.

The server receives:
- JSON example records (one or more objects)
- Optional natural-language field descriptions
- Optional synthetic record count

It then orchestrates generation/deployment of an Azure Functions CRUD API and data persistence in Azure Cosmos DB serverless.

## 2. Problem Statement

Teams prototyping applications with AI often need multiple APIs quickly, but backend implementation and data preparation is still slow and repetitive.

Current pain points:
- Rebuilding basic CRUD APIs for each prototype
- Manually creating datasets
- Context switching between prompt design, backend coding, and cloud deployment

## 3. Goals

1. Generate deployable mock REST APIs in minutes.
2. Support realistic test data quickly (seed + synthetic).
3. Provide standard CRUD behavior plus basic filtering.
4. Return API details in a machine-consumable way for downstream agent workflows.

## 4. Non-Goals (MVP)

- Production-grade auth/authorization and enterprise IAM flows
- Advanced API versioning lifecycle management
- Highly custom business logic generation
- Full IaC abstraction for every Azure topology

## 5. Personas

- **AI App Builder**: Uses Copilot/agent to create UI prototypes quickly.
- **Developer**: Needs temporary APIs for integration tests and demos.
- **Solution Architect**: Wants a repeatable rapid-prototyping backbone.

## 6. User Stories

### 6.1 API generation
- As an AI app builder, I provide sample JSON and get a CRUD API with endpoints I can call immediately.

### 6.2 Data seeding
- As a developer, I provide initial records and they are available in Cosmos DB for API reads.

### 6.3 Synthetic data
- As an AI app builder, I provide field meaning descriptions and target record count to generate realistic data.

### 6.4 Multi-API workflow
- As a solution architect, I can call MCP tools repeatedly to create several APIs for one UI app.

## 7. Functional Requirements

### FR-1: MCP tooling
The MCP server must expose tools to:
1. `create_mock_api`
2. `generate_synthetic_data`
3. `get_operation_status`
4. `list_deployments`

### FR-2: Input schema inference
- Infer schema fields and primitive types from sample JSON.
- Detect id candidate (prefer `id`, fallback generated UUID).

### FR-3: REST endpoint generation
For each API resource generated:
- `POST /{resource}` create
- `GET /{resource}` list
- `GET /{resource}/{id}` get one
- `PATCH /{resource}/{id}` partial update
- `DELETE /{resource}/{id}` delete

### FR-4: Basic filtering
`GET /{resource}` supports query params for exact match filtering on scalar fields.

### FR-5: Cosmos DB persistence
- Create/ensure database and container.
- Seed sample data and synthetic data.
- Configure partition key strategy (default `/id` for MVP unless specified).

### FR-6: Synthetic data generation
- Accept example JSON + free-text field explanations + target count.
- Generate in batches with retries and validation.
- Enforce default maximum of 10,000 generated records per operation in MVP.
- Store generated records in Cosmos DB.

### FR-7: Deployment behavior
- Deploy or update a dedicated Azure Functions app per generated API resource in MVP.
- Return endpoint base URL and resource metadata.

### FR-9: OpenAPI contract output
- Generate and return a basic OpenAPI/Swagger document for each generated API.

### FR-8: Operation status and logs
Long operations return operation id and allow polling status.

## 8. MCP Tool Contracts (Draft)

### 8.1 `create_mock_api`
**Input**
- `project_name: str`
- `resource_name: str`
- `sample_records: list[object]`
- `azure_subscription_id: str`
- `resource_group: str`
- `location: str`
- `cosmos_account_name: str`
- `function_app_name: str`

**Output**
- `operation_id: str`
- `status: queued|running|succeeded|failed`
- `api_base_url: str` (when available)
- `resource_name: str`
- `endpoints: object`

### 8.2 `generate_synthetic_data`
**Input**
- `deployment_id: str`
- `sample_records: list[object]`
- `field_descriptions: str`
- `record_count: int`
- `batch_size: int` (default 100)

**Output**
- `operation_id: str`
- `status: queued|running|succeeded|failed`
- `records_generated: int`

## 9. Non-Functional Requirements

- **Language**: Python only for MCP backend and generation scripts.
- **Latency target**: API generation flow < 10 min for simple schema.
- **Scalability target**: support up to 10k synthetic records per operation in MVP via batching.
- **Reliability**: idempotent retries for deployment and data upload.
- **Observability**: structured logs and correlation/operation IDs.
- **Security**: no secrets in source; use environment variables/managed identity.

## 10. Success Metrics

- Time to first working API endpoint
- Number of successful API generation runs
- Synthetic generation throughput (records/min)
- First-call success rate of generated endpoints
- Number of APIs created per prototype project

## 11. Risks and Mitigations

1. **LLM produces invalid Python/JSON**  
   Mitigation: strict schema validation + regeneration loop.
2. **Azure deployment failures**  
   Mitigation: preflight checks + actionable failure diagnostics.
3. **Data quality inconsistency**  
   Mitigation: validate required fields/type conformance before insert.
4. **Cost drift from synthetic generation**  
   Mitigation: enforce max record limits and quotas.

## 12. MVP Scope

Included:
- Single-resource CRUD API generation per operation
- Basic exact-match filtering
- Cosmos storage + data seeding
- Synthetic generation tool
- Default synthetic limit of 10,000 records per operation
- Basic OpenAPI/Swagger generation
- Operation tracking

Deferred:
- Joins/relations across resources
- Pagination/sorting advanced query engine
- Advanced filtering operators (`gt`, `lt`, `contains`, `in`)
- Auth providers integration
- Multi-environment promotion flow

## 13. Milestones

1. **M1 - Local generation POC**
   - MCP tool skeleton
   - Generate Python Function handlers locally
2. **M2 - Azure deployment integration**
   - Deploy Function app + connect Cosmos
3. **M3 - Synthetic data pipeline**
   - Batched generation + validation + upload
4. **M4 - End-to-end demo scenario**
   - Build simple UI that consumes multiple generated APIs

## 14. Open Questions

1. Default partition key strategy: `/id` vs configurable field?
2. Should synthetic data generation support configurable limits above 10k with explicit override?
3. Should OpenAPI include example request/response payloads generated from seed data?
