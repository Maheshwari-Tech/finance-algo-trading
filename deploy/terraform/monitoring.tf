# Managed Prometheus: workspace + collection rule + association with the cluster.
# This is what `az aks create --enable-azure-monitor-metrics` creates behind the scenes.

resource "azurerm_monitor_workspace" "prometheus" {
  name                = "amw-${var.prefix}"
  resource_group_name = azurerm_resource_group.main.name
  location            = azurerm_resource_group.main.location
  tags                = var.tags
}

resource "azurerm_monitor_data_collection_endpoint" "prometheus" {
  name                = "MSProm-${var.location}-${local.aks_name}"
  resource_group_name = azurerm_resource_group.main.name
  location            = azurerm_resource_group.main.location
  kind                = "Linux"
  tags                = var.tags
}

resource "azurerm_monitor_data_collection_rule" "prometheus" {
  name                        = "MSProm-${var.location}-${local.aks_name}"
  resource_group_name         = azurerm_resource_group.main.name
  location                    = azurerm_resource_group.main.location
  data_collection_endpoint_id = azurerm_monitor_data_collection_endpoint.prometheus.id
  kind                        = "Linux"
  tags                        = var.tags

  destinations {
    monitor_account {
      monitor_account_id = azurerm_monitor_workspace.prometheus.id
      name               = "MonitoringAccount1"
    }
  }

  data_flow {
    streams      = ["Microsoft-PrometheusMetrics"]
    destinations = ["MonitoringAccount1"]
  }

  data_sources {
    prometheus_forwarder {
      streams = ["Microsoft-PrometheusMetrics"]
      name    = "PrometheusDataSource"
    }
  }
}

resource "azurerm_monitor_data_collection_rule_association" "prometheus" {
  name                    = "MSProm-${var.location}-${local.aks_name}"
  target_resource_id      = azurerm_kubernetes_cluster.main.id
  data_collection_rule_id = azurerm_monitor_data_collection_rule.prometheus.id
}

resource "azurerm_monitor_data_collection_rule_association" "prometheus_endpoint" {
  target_resource_id          = azurerm_kubernetes_cluster.main.id
  data_collection_endpoint_id = azurerm_monitor_data_collection_endpoint.prometheus.id
}

# Optional dashboards
resource "azurerm_dashboard_grafana" "main" {
  count                 = var.enable_grafana ? 1 : 0
  name                  = "grafana-${var.prefix}-${var.suffix}"
  resource_group_name   = azurerm_resource_group.main.name
  location              = azurerm_resource_group.main.location
  grafana_major_version = 11
  tags                  = var.tags

  identity {
    type = "SystemAssigned"
  }

  azure_monitor_workspace_integrations {
    resource_id = azurerm_monitor_workspace.prometheus.id
  }
}

resource "azurerm_role_assignment" "grafana_reads_metrics" {
  count                = var.enable_grafana ? 1 : 0
  scope                = azurerm_monitor_workspace.prometheus.id
  role_definition_name = "Monitoring Data Reader"
  principal_id         = azurerm_dashboard_grafana.main[0].identity[0].principal_id
}

resource "azurerm_role_assignment" "grafana_admins" {
  for_each             = var.enable_grafana ? local.cluster_admins : toset([])
  scope                = azurerm_dashboard_grafana.main[0].id
  role_definition_name = "Grafana Admin"
  principal_id         = each.value
}
