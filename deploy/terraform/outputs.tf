# Read by the pipeline (terraform output -json) so no names are copied into GitHub by hand.

output "resource_group" { value = azurerm_resource_group.main.name }
output "aks_name" { value = azurerm_kubernetes_cluster.main.name }
output "acr_name" { value = azurerm_container_registry.main.name }
output "acr_login_server" { value = azurerm_container_registry.main.login_server }
output "key_vault_name" { value = azurerm_key_vault.main.name }
output "tenant_id" { value = local.tenant_id }
output "namespace" { value = var.namespace }
output "release_name" { value = var.release_name }

output "api_workload_identity_client_id" { value = azurerm_user_assigned_identity.api.client_id }
output "alb_controller_client_id" { value = azurerm_user_assigned_identity.alb.client_id }

output "agc_id" { value = azurerm_application_load_balancer.main.id }
output "agc_frontend_name" { value = azurerm_application_load_balancer_frontend.main.name }
# Public address of the API until a custom domain is pointed at it.
output "api_fqdn" { value = azurerm_application_load_balancer_frontend.main.fully_qualified_domain_name }

output "postgres_fqdn" { value = azurerm_postgresql_flexible_server.main.fqdn }
output "prometheus_workspace_id" { value = azurerm_monitor_workspace.prometheus.id }
