# Agentic Component Factory

From prompt to running software component.

## Vision

Move beyond static templates toward specialized agent systems that can build,
deploy, and validate real software components end to end. The goal is a
component catalog where a coding agent designing an overall solution can select
a capability, delegate execution, and receive a ready-to-integrate running
interface.

In other words: coding agents orchestrate the product, while the Agentic
Component Factory executes component delivery using specialized agents.

## Current capability: API mock generator

This repository implements the first capability in that vision: an MCP-based
mock API generator that creates live CRUD REST APIs with realistic synthetic
data and deploys them to cloud infrastructure.

You provide a resource name and example records. The system generates code,
seeds data, deploys the API, and returns a live endpoint for immediate use by
the calling coding agent.

## Documentation

| Document | Description |
|---|---|
| [docs/README.md](docs/README.md) | How it works, quick start, demo scenario |
| [docs/DEVELOPMENT.md](docs/DEVELOPMENT.md) | Local development, building, testing |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | Technical design |
| [docs/PRD.md](docs/PRD.md) | Product requirements |
| [AGENTS.md](AGENTS.md) | AI agent coding conventions |

## License

[MIT](LICENSE)
