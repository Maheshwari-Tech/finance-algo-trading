# Application Gateway for Containers, "bring your own" style: Terraform owns the gateway, its
# frontend and the subnet link. The Helm chart's Gateway resource just points at them (gateway.albId / frontendName).

resource "azurerm_application_load_balancer" "main" {
  name                = local.agc_name
  resource_group_name = azurerm_resource_group.main.name
  location            = azurerm_resource_group.main.location
  tags                = var.tags
}

resource "azurerm_application_load_balancer_subnet_association" "main" {
  name                         = "alb-subnet"
  application_load_balancer_id = azurerm_application_load_balancer.main.id
  subnet_id                    = azurerm_subnet.alb.id
}

resource "azurerm_application_load_balancer_frontend" "main" {
  name                         = "frontend"
  application_load_balancer_id = azurerm_application_load_balancer.main.id
}
