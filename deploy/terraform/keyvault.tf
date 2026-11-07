# Key Vault holds the application secrets. Terraform writes them; the pods read them through the
# Secrets Store CSI driver with workload identity (identity.tf). Names match deploy/helm values.yaml.

resource "azurerm_key_vault" "main" {
  name                          = local.kv_name
  resource_group_name           = azurerm_resource_group.main.name
  location                      = azurerm_resource_group.main.location
  tenant_id                     = local.tenant_id
  sku_name                      = "standard"
  rbac_authorization_enabled    = true
  soft_delete_retention_days    = 7
  purge_protection_enabled      = false
  public_network_access_enabled = true # Terraform and the CSI driver reach the vault over its public endpoint; access is still role-gated.
  tags                          = var.tags
}

resource "azurerm_role_assignment" "kv_deployer" {
  scope                = azurerm_key_vault.main.id
  role_definition_name = "Key Vault Secrets Officer"
  principal_id         = data.azurerm_client_config.current.object_id
}

# Role assignments take a moment to apply.
resource "time_sleep" "kv_rbac" {
  depends_on      = [azurerm_role_assignment.kv_deployer]
  create_duration = "90s"
}

resource "random_password" "secret_key" {
  length  = 64
  special = false
}

locals {
  secrets = {
    "database-url"    = "postgresql://${azurerm_postgresql_flexible_server.main.administrator_login}:${random_password.pg.result}@${azurerm_postgresql_flexible_server.main.fqdn}:5432/${azurerm_postgresql_flexible_server_database.app.name}?sslmode=require"
    "redis-url"       = "rediss://:${urlencode(azurerm_redis_cache.main.primary_access_key)}@${azurerm_redis_cache.main.hostname}:6380/0"
    "secret-key"      = random_password.secret_key.result
    "otp-dev-code"    = var.otp_code
    "admin-mobiles"   = var.admin_mobiles
    "allowed-mobiles" = var.allowed_mobiles
  }
}

resource "azurerm_key_vault_secret" "app" {
  # Names are not secret, so only they are iterated (values stay sensitive).
  for_each     = toset(nonsensitive(keys(local.secrets)))
  name         = each.value
  value        = local.secrets[each.value]
  key_vault_id = azurerm_key_vault.main.id
  depends_on   = [time_sleep.kv_rbac]
}
