output "mcp_url" {
  description = "URL do endpoint MCP (streamable HTTP) para configurar nos clientes"
  value       = "https://${azurerm_container_app.mcp.ingress[0].fqdn}/mcp"
}

output "health_url" {
  value = "https://${azurerm_container_app.mcp.ingress[0].fqdn}/health"
}

output "identity_principal_id" {
  value = azurerm_user_assigned_identity.mcp.principal_id
}
