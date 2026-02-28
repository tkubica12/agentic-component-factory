terraform {
  required_version = ">= 1.5.0"

  required_providers {
    azurerm = {
      source  = "hashicorp/azurerm"
      version = "~> 4.0"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.6"
    }
  }
}

provider "azurerm" {
  features {}
  subscription_id = var.subscription_id
}

resource "random_string" "suffix" {
  length  = 6
  special = false
  upper   = false
}

locals {
  suffix = random_string.suffix.result
  tags = {
    project         = "mcp-api-mock-gen"
    SecurityControl = "ignore"
  }
}

data "azurerm_client_config" "current" {}

# ---------- Resource Group ----------
resource "azurerm_resource_group" "main" {
  name     = var.resource_group_name
  location = var.location
  tags     = local.tags
}

# ---------- CosmosDB Serverless (Entra-only) ----------
resource "azurerm_cosmosdb_account" "main" {
  name                = "cosmos-mcpmock-${local.suffix}"
  location            = azurerm_resource_group.main.location
  resource_group_name = azurerm_resource_group.main.name
  offer_type          = "Standard"
  kind                = "GlobalDocumentDB"

  capabilities {
    name = "EnableServerless"
  }

  consistency_policy {
    consistency_level = "Session"
  }

  geo_location {
    location          = azurerm_resource_group.main.location
    failover_priority = 0
  }

  local_authentication_disabled = true
  tags                          = local.tags
}

# ---------- Azure Container Registry ----------
resource "azurerm_container_registry" "main" {
  name                = "acrmcpmock${local.suffix}"
  location            = azurerm_resource_group.main.location
  resource_group_name = azurerm_resource_group.main.name
  sku                 = "Basic"
  admin_enabled       = false
  tags                = local.tags
}

# ---------- User-Assigned Managed Identity (shared across all Container Apps) ----------
resource "azurerm_user_assigned_identity" "apps" {
  name                = "id-mcpmock-apps-${local.suffix}"
  location            = azurerm_resource_group.main.location
  resource_group_name = azurerm_resource_group.main.name
  tags                = local.tags
}

# ---------- Container Apps Environment (no Log Analytics for speed) ----------
resource "azurerm_container_app_environment" "main" {
  name                = "cae-mcpmock-${local.suffix}"
  location            = azurerm_resource_group.main.location
  resource_group_name = azurerm_resource_group.main.name
  tags                = local.tags
}

# ---------- Cosmos DB RBAC: current deployer user ----------
resource "azurerm_cosmosdb_sql_role_assignment" "deployer" {
  resource_group_name = azurerm_resource_group.main.name
  account_name        = azurerm_cosmosdb_account.main.name
  role_definition_id  = "${azurerm_cosmosdb_account.main.id}/sqlRoleDefinitions/00000000-0000-0000-0000-000000000002"
  principal_id        = data.azurerm_client_config.current.object_id
  scope               = azurerm_cosmosdb_account.main.id
}

# ---------- Cosmos DB RBAC: user-assigned managed identity ----------
resource "azurerm_cosmosdb_sql_role_assignment" "apps_mi" {
  resource_group_name = azurerm_resource_group.main.name
  account_name        = azurerm_cosmosdb_account.main.name
  role_definition_id  = "${azurerm_cosmosdb_account.main.id}/sqlRoleDefinitions/00000000-0000-0000-0000-000000000002"
  principal_id        = azurerm_user_assigned_identity.apps.principal_id
  scope               = azurerm_cosmosdb_account.main.id
}

# ---------- ACR Pull: user-assigned MI can pull images ----------
resource "azurerm_role_assignment" "mi_acr_pull" {
  scope                = azurerm_container_registry.main.id
  role_definition_name = "AcrPull"
  principal_id         = azurerm_user_assigned_identity.apps.principal_id
  principal_type       = "ServicePrincipal"
}

# ---------- ACR Push: current user can push/build images ----------
resource "azurerm_role_assignment" "deployer_acr_push" {
  scope                = azurerm_container_registry.main.id
  role_definition_name = "AcrPush"
  principal_id         = data.azurerm_client_config.current.object_id
  principal_type       = "User"
}

# ---------- AI Foundry (Cognitive Services) ----------
resource "azurerm_cognitive_account" "foundry" {
  name                          = "ai-mcpmock-${local.suffix}"
  location                      = azurerm_resource_group.main.location
  resource_group_name           = azurerm_resource_group.main.name
  kind                          = "AIServices"
  sku_name                      = "S0"
  custom_subdomain_name         = "ai-mcpmock-${local.suffix}"
  local_auth_enabled            = false
  public_network_access_enabled = true
  tags                          = local.tags

  identity {
    type = "SystemAssigned"
  }
}

resource "azurerm_cognitive_deployment" "codex" {
  name                 = "gpt-53-codex"
  cognitive_account_id = azurerm_cognitive_account.foundry.id

  model {
    format  = "OpenAI"
    name    = "gpt-5.3-codex"
    version = "2026-02-24"
  }

  sku {
    name     = "GlobalStandard"
    capacity = 500
  }
}

# ---------- AI Foundry RBAC: user-assigned MI (Cognitive Services OpenAI User) ----------
resource "azurerm_role_assignment" "mi_openai_user" {
  scope                = azurerm_cognitive_account.foundry.id
  role_definition_name = "Cognitive Services OpenAI User"
  principal_id         = azurerm_user_assigned_identity.apps.principal_id
  principal_type       = "ServicePrincipal"
}

# ---------- AI Foundry RBAC: current user ----------
resource "azurerm_role_assignment" "deployer_openai_user" {
  scope                = azurerm_cognitive_account.foundry.id
  role_definition_name = "Cognitive Services OpenAI User"
  principal_id         = data.azurerm_client_config.current.object_id
  principal_type       = "User"
}

# ---------- MI needs Contributor on RG for az CLI operations ----------
resource "azurerm_role_assignment" "mi_rg_contributor" {
  scope                = azurerm_resource_group.main.id
  role_definition_name = "Contributor"
  principal_id         = azurerm_user_assigned_identity.apps.principal_id
  principal_type       = "ServicePrincipal"
}

# ---------- MI needs Reader at subscription level for az account set ----------
resource "azurerm_role_assignment" "mi_sub_reader" {
  scope                = "/subscriptions/${var.subscription_id}"
  role_definition_name = "Reader"
  principal_id         = azurerm_user_assigned_identity.apps.principal_id
  principal_type       = "ServicePrincipal"
}

# ---------- MCP Server Container App ----------
resource "azurerm_container_app" "mcp_server" {
  name                         = "mcp-api-mock-gen"
  container_app_environment_id = azurerm_container_app_environment.main.id
  resource_group_name          = azurerm_resource_group.main.name
  revision_mode                = "Single"
  tags                         = local.tags

  identity {
    type         = "UserAssigned"
    identity_ids = [azurerm_user_assigned_identity.apps.id]
  }

  ingress {
    external_enabled = true
    target_port      = 8000
    transport        = "auto"

    ip_security_restriction {
      action           = "Allow"
      ip_address_range = "0.0.0.0/0"
      name             = "allow-all"
    }

    traffic_weight {
      latest_revision = true
      percentage      = 100
    }
  }

  lifecycle {
    ignore_changes = [
      template[0].container[0].image,
    ]
  }

  template {
    min_replicas = 3
    max_replicas = 10

    container {
      name   = "mcp-server"
      image  = var.mcp_server_image
      cpu    = 1
      memory = "2Gi"

      env {
        name  = "AZURE_SUBSCRIPTION_ID"
        value = var.subscription_id
      }
      env {
        name  = "AZURE_RESOURCE_GROUP"
        value = azurerm_resource_group.main.name
      }
      env {
        name  = "AZURE_LOCATION"
        value = var.location
      }
      env {
        name  = "COSMOS_ACCOUNT_NAME"
        value = azurerm_cosmosdb_account.main.name
      }
      env {
        name  = "COSMOS_ENDPOINT"
        value = azurerm_cosmosdb_account.main.endpoint
      }
      env {
        name  = "ACR_NAME"
        value = azurerm_container_registry.main.name
      }
      env {
        name  = "ACR_LOGIN_SERVER"
        value = azurerm_container_registry.main.login_server
      }
      env {
        name  = "ACA_ENVIRONMENT_NAME"
        value = azurerm_container_app_environment.main.name
      }
      env {
        name  = "MANAGED_IDENTITY_ID"
        value = azurerm_user_assigned_identity.apps.id
      }
      env {
        name  = "MANAGED_IDENTITY_CLIENT_ID"
        value = azurerm_user_assigned_identity.apps.client_id
      }
      env {
        name  = "AZURE_OPENAI_ENDPOINT"
        value = azurerm_cognitive_account.foundry.endpoint
      }
      env {
        name  = "CODEX_MODEL"
        value = azurerm_cognitive_deployment.codex.name
      }
      env {
        name  = "AZURE_CLIENT_ID"
        value = azurerm_user_assigned_identity.apps.client_id
      }
      env {
        name        = "MCP_API_KEY"
        secret_name = "mcp-api-key"
      }
    }
  }

  secret {
    name  = "mcp-api-key"
    value = var.mcp_api_key
  }

  depends_on = [
    azurerm_cosmosdb_sql_role_assignment.apps_mi,
    azurerm_role_assignment.mi_acr_pull,
    azurerm_role_assignment.mi_openai_user,
    azurerm_role_assignment.mi_rg_contributor,
  ]
}
