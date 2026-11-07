# ---- Pods -> Key Vault (workload identity) ----

resource "azurerm_user_assigned_identity" "api" {
  name                = "id-${var.prefix}-api"
  resource_group_name = azurerm_resource_group.main.name
  location            = azurerm_resource_group.main.location
  tags                = var.tags
}

resource "azurerm_role_assignment" "api_reads_secrets" {
  scope                = azurerm_key_vault.main.id
  role_definition_name = "Key Vault Secrets User"
  principal_id         = azurerm_user_assigned_identity.api.principal_id
}

# Trusts the Kubernetes ServiceAccount the Helm chart creates (named after the release).
resource "azurerm_federated_identity_credential" "api" {
  name                = "aks-${var.namespace}-${var.release_name}"
  resource_group_name = azurerm_resource_group.main.name
  parent_id           = azurerm_user_assigned_identity.api.id
  audience            = ["api://AzureADTokenExchange"]
  issuer              = azurerm_kubernetes_cluster.main.oidc_issuer_url
  subject             = "system:serviceaccount:${var.namespace}:${var.release_name}"
}

# ---- ALB controller -> Application Gateway for Containers ----

resource "azurerm_user_assigned_identity" "alb" {
  name                = "id-${var.prefix}-alb-controller"
  resource_group_name = azurerm_resource_group.main.name
  location            = azurerm_resource_group.main.location
  tags                = var.tags
}

resource "azurerm_federated_identity_credential" "alb" {
  name                = "alb-controller"
  resource_group_name = azurerm_resource_group.main.name
  parent_id           = azurerm_user_assigned_identity.alb.id
  audience            = ["api://AzureADTokenExchange"]
  issuer              = azurerm_kubernetes_cluster.main.oidc_issuer_url
  subject             = "system:serviceaccount:azure-alb-system:alb-controller-sa"
}

resource "azurerm_role_assignment" "alb_reader" {
  scope                = azurerm_resource_group.main.id
  role_definition_name = "Reader"
  principal_id         = azurerm_user_assigned_identity.alb.principal_id
}

resource "azurerm_role_assignment" "alb_config_manager" {
  scope                = azurerm_resource_group.main.id
  role_definition_name = "AppGw for Containers Configuration Manager"
  principal_id         = azurerm_user_assigned_identity.alb.principal_id
}

resource "azurerm_role_assignment" "alb_subnet" {
  scope                = azurerm_subnet.alb.id
  role_definition_name = "Network Contributor"
  principal_id         = azurerm_user_assigned_identity.alb.principal_id
}
