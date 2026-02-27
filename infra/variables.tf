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
