# AGENTS.md

Coding conventions and tooling guidance for AI agents working in this repository.

## Python Code style

- Use `uv` for all package management. No `requirements.txt` — dependencies live in `pyproject.toml`.
- Docstrings on all public functions and classes; skip obvious inline comments.
- No premature abstractions — solve the problem at hand, refactor when a pattern repeats.
- Keep modules focused and small; flat structure beats deep nesting.
- Use FastMCP library for bith server and client

## Agent coding

- Start with planning and make sure you understand the task and data before coding.
- Where possible create tests so you can validate your progress and fix issues early.

## Terraform IaC

- Versions: Use the latest stable Terraform and pin Terraform/provider versions in `versions.tf`.
- Providers: Use `azurerm` by default; use `azapi` only for Azure features not yet in `azurerm`.
- Layout: Keep provider/backend setup in `main.tf`; use `variables.tf` and `outputs.tf`; split resources into focused files (`networking.tf`, `rbac.tf`, etc.), and split further when files get large.
- Variables & naming: Prefer strict types over `any`, add clear descriptions, provide safe defaults, use `snake_case`, and keep names descriptive/unique.
- Comments & tags: Comment only non-obvious or critical decisions; tags are optional unless required, and shared tags should come from `locals`.
- State & modules: Always use remote state with locking, isolate state per environment, never commit state files, and keep reusable logic in semver-versioned modules (local path or tagged git source).
- Security: Never hardcode secrets; use Key Vault/env vars; mark sensitive outputs with `sensitive = true`.