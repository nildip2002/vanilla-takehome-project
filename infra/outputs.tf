output "resource_group_name" {
  value = azurerm_resource_group.main.name
}

output "backend_url" {
  value = "https://${azurerm_container_app.backend.ingress[0].fqdn}"
}

output "frontend_url" {
  value = "https://${azurerm_static_web_app.frontend.default_host_name}"
}

output "acr_login_server" {
  value = azurerm_container_registry.main.login_server
}

output "cosmos_endpoint" {
  value     = azurerm_cosmosdb_account.main.endpoint
  sensitive = true
}

output "foundry_endpoint" {
  value     = azurerm_cognitive_account.foundry.endpoint
  sensitive = true
}

output "appinsights_connection_string" {
  value     = azurerm_application_insights.main.connection_string
  sensitive = true
}

output "swa_deployment_token" {
  value     = azurerm_static_web_app.frontend.api_key
  sensitive = true
}

output "key_vault_url" {
  value = azurerm_key_vault.main.vault_uri
}
