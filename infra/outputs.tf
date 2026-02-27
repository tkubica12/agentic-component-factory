output "resource_group_name" {
  value = azurerm_resource_group.main.name
}

output "cosmos_account_name" {
  value = azurerm_cosmosdb_account.main.name
}

output "cosmos_endpoint" {
  value = azurerm_cosmosdb_account.main.endpoint
}

output "location" {
  value = azurerm_resource_group.main.location
}

output "subscription_id" {
  value = var.subscription_id
}

output "managed_identity_id" {
  value = azurerm_user_assigned_identity.apps.id
}

output "managed_identity_client_id" {
  value = azurerm_user_assigned_identity.apps.client_id
}

output "acr_name" {
  value = azurerm_container_registry.main.name
}

output "acr_login_server" {
  value = azurerm_container_registry.main.login_server
}

output "aca_environment_name" {
  value = azurerm_container_app_environment.main.name
}

output "aca_environment_id" {
  value = azurerm_container_app_environment.main.id
}

output "suffix" {
  value = local.suffix
}

output "foundry_endpoint" {
  value = azurerm_cognitive_account.foundry.endpoint
}

output "foundry_name" {
  value = azurerm_cognitive_account.foundry.name
}
