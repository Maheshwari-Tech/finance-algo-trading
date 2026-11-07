resource "azurerm_container_registry" "main" {
  name                = local.acr_name
  resource_group_name = azurerm_resource_group.main.name
  location            = azurerm_resource_group.main.location
  sku                 = "Standard"
  admin_enabled       = false
  tags                = var.tags
}

resource "azurerm_kubernetes_cluster" "main" {
  name                      = local.aks_name
  resource_group_name       = azurerm_resource_group.main.name
  location                  = azurerm_resource_group.main.location
  dns_prefix                = local.aks_name
  kubernetes_version        = var.kubernetes_version
  automatic_upgrade_channel = "patch"
  oidc_issuer_enabled       = true
  workload_identity_enabled = true
  tags                      = var.tags

  identity {
    type = "SystemAssigned"
  }

  default_node_pool {
    name                        = "system"
    vm_size                     = var.aks_node_vm_size
    zones                       = ["1", "2", "3"]
    auto_scaling_enabled        = true
    min_count                   = var.aks_min_nodes
    max_count                   = var.aks_max_nodes
    vnet_subnet_id              = azurerm_subnet.aks.id
    temporary_name_for_rotation = "tmpsystem"

    upgrade_settings {
      max_surge = "33%"
    }
  }

  network_profile {
    network_plugin      = "azure"
    network_plugin_mode = "overlay"
    service_cidr        = "10.200.0.0/16"
    dns_service_ip      = "10.200.0.10"
  }

  # Sign in with Entra ID; permissions come from Azure roles (assigned below).
  azure_active_directory_role_based_access_control {
    azure_rbac_enabled = true
    tenant_id          = local.tenant_id
  }

  key_vault_secrets_provider {
    secret_rotation_enabled = true
  }

  # Managed Prometheus (the workspace and rules are in monitoring.tf)
  monitor_metrics {}

  lifecycle {
    ignore_changes = [default_node_pool[0].node_count]
  }
}

# The cluster pulls images from the registry.
resource "azurerm_role_assignment" "aks_acr_pull" {
  scope                = azurerm_container_registry.main.id
  role_definition_name = "AcrPull"
  principal_id         = azurerm_kubernetes_cluster.main.kubelet_identity[0].object_id
}

# The pipeline identity (and any named admins) can use the cluster.
resource "azurerm_role_assignment" "cluster_admin" {
  for_each             = local.cluster_admins
  scope                = azurerm_kubernetes_cluster.main.id
  role_definition_name = "Azure Kubernetes Service RBAC Cluster Admin"
  principal_id         = each.value
}

resource "azurerm_role_assignment" "cluster_user" {
  for_each             = local.cluster_admins
  scope                = azurerm_kubernetes_cluster.main.id
  role_definition_name = "Azure Kubernetes Service Cluster User Role"
  principal_id         = each.value
}
