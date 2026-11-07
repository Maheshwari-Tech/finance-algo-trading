data "azurerm_client_config" "current" {}

locals {
  rg_name    = "rg-${var.prefix}"
  acr_name   = "${var.prefix}${var.suffix}" # letters and digits only
  aks_name   = "aks-${var.prefix}"
  kv_name    = "kv-${var.prefix}-${var.suffix}" # 3-24 chars
  pg_name    = "pg-${var.prefix}-${var.suffix}"
  redis_name = "redis-${var.prefix}-${var.suffix}"
  agc_name   = "agc-${var.prefix}"
  tenant_id  = data.azurerm_client_config.current.tenant_id

  # The identity running Terraform (the pipeline) plus any named admins.
  cluster_admins = toset(concat([data.azurerm_client_config.current.object_id], var.admin_object_ids))
}

resource "azurerm_resource_group" "main" {
  name     = local.rg_name
  location = var.location
  tags     = var.tags
}

resource "azurerm_virtual_network" "main" {
  name                = "vnet-${var.prefix}"
  resource_group_name = azurerm_resource_group.main.name
  location            = azurerm_resource_group.main.location
  address_space       = ["10.10.0.0/16"]
  tags                = var.tags
}

resource "azurerm_subnet" "aks" {
  name                 = "snet-aks"
  resource_group_name  = azurerm_resource_group.main.name
  virtual_network_name = azurerm_virtual_network.main.name
  address_prefixes     = ["10.10.0.0/22"]
}

# Reserved for Application Gateway for Containers
resource "azurerm_subnet" "alb" {
  name                 = "snet-alb"
  resource_group_name  = azurerm_resource_group.main.name
  virtual_network_name = azurerm_virtual_network.main.name
  address_prefixes     = ["10.10.8.0/24"]

  delegation {
    name = "agfc"
    service_delegation {
      name    = "Microsoft.ServiceNetworking/trafficControllers"
      actions = ["Microsoft.Network/virtualNetworks/subnets/join/action"]
    }
  }
}

# Reserved for PostgreSQL Flexible Server (private access)
resource "azurerm_subnet" "pg" {
  name                 = "snet-pg"
  resource_group_name  = azurerm_resource_group.main.name
  virtual_network_name = azurerm_virtual_network.main.name
  address_prefixes     = ["10.10.9.0/24"]

  delegation {
    name = "postgres"
    service_delegation {
      name    = "Microsoft.DBforPostgreSQL/flexibleServers"
      actions = ["Microsoft.Network/virtualNetworks/subnets/join/action"]
    }
  }
}

# Private endpoints (Redis)
resource "azurerm_subnet" "pe" {
  name                 = "snet-pe"
  resource_group_name  = azurerm_resource_group.main.name
  virtual_network_name = azurerm_virtual_network.main.name
  address_prefixes     = ["10.10.10.0/24"]
}
