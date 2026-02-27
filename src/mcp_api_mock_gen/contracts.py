"""Pydantic models for MCP tool inputs and outputs."""

from __future__ import annotations

from pydantic import BaseModel, Field


class EndpointInfo(BaseModel):
    method: str
    path: str


class CreateMockApiResult(BaseModel):
    """Result returned by create_mock_api."""

    deployment_id: str = Field(description="Unique ID for this deployment (use to delete later)")
    status: str = Field(description="succeeded | failed")
    api_base_url: str | None = Field(default=None, description="Base URL of the deployed API")
    resource_name: str = Field(description="Name of the resource")
    cosmos_database: str | None = Field(default=None)
    cosmos_container: str | None = Field(default=None)
    container_app_name: str | None = Field(default=None)
    endpoints: list[EndpointInfo] = Field(default_factory=list)
    records_seeded: int = Field(default=0, description="Number of sample records seeded")
    records_generated: int = Field(default=0, description="Number of synthetic records generated")
    error: str | None = Field(default=None)


class DeleteMockApiResult(BaseModel):
    """Result returned by delete_mock_api."""

    deployment_id: str
    status: str = Field(description="succeeded | failed")
    error: str | None = Field(default=None)
