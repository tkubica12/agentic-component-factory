variable "subscription_id" {
  description = "Azure subscription ID"
  type        = string
}

variable "resource_group_name" {
  description = "Name of the resource group"
  type        = string
  default     = "rg-mcp-api-mock-gen"
}

variable "location" {
  description = "Azure region"
  type        = string
  default     = "swedencentral"
}

variable "mcp_api_key" {
  description = "API key to protect the MCP server endpoint"
  type        = string
  sensitive   = true
}

variable "mcp_server_image" {
  description = "Docker image for the MCP server"
  type        = string
  default     = "ghcr.io/tkubica12/mcp-api-mock-gen:latest"
}

variable "worker_image" {
  description = "Docker image for the worker"
  type        = string
  default     = "ghcr.io/tkubica12/mcp-api-mock-gen-worker:latest"
}
