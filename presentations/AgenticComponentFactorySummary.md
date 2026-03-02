# Agentic Component Factory — Summary

## Vision

Build a catalog of **agentic components**: systems that generate, build, deploy, and validate software, then return a running interface for a main coding agent.

## Problem → Solution

Templates provide consistency, but still need code edits plus manual provisioning, seeding, deployment, and verification. This project exposes MCP tools that automate execution and return integration details.

## Example: API Mock Generator

First component: an MCP tool that takes a resource name + sample JSON, seeds and optionally generates synthetic records, and deploys a live FastAPI CRUD API backed by Azure Cosmos DB.

## Architecture (How)

FastMCP server writes job state to Cosmos DB and queues work on Service Bus. A Worker uses the GitHub Copilot SDK (Azure OpenAI BYOK) to generate code, then uses tools to build in ACR, deploy to Azure Container Apps, optionally generate data, and smoke test.