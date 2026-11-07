variable "subscription_id" {
  description = "Azure subscription ID. Leave null to use ARM_SUBSCRIPTION_ID."
  type        = string
  default     = null
}

variable "location" {
  description = "Azure region. India: centralindia (zones available) or southindia."
  type        = string
  default     = "centralindia"
}

variable "prefix" {
  description = "Short lowercase name used in resource names."
  type        = string
  default     = "strtrader"

  validation {
    condition     = can(regex("^[a-z][a-z0-9]{2,11}$", var.prefix))
    error_message = "prefix: 3-12 lowercase letters/digits, starting with a letter."
  }
}

variable "suffix" {
  description = "Makes globally unique names (registry, key vault, database, redis) unique. e.g. your initials + digits."
  type        = string

  validation {
    condition     = can(regex("^[a-z0-9]{3,6}$", var.suffix))
    error_message = "suffix: 3-6 lowercase letters/digits."
  }
}

variable "namespace" {
  description = "Kubernetes namespace for the API."
  type        = string
  default     = "trader"
}

variable "release_name" {
  description = "Helm release name. Also the ServiceAccount name the workload identity trusts."
  type        = string
  default     = "strategic-trader"
}

# ---- AKS ----

variable "kubernetes_version" {
  description = "AKS version. null = the current default for the region."
  type        = string
  default     = null
}

variable "aks_node_vm_size" {
  type    = string
  default = "Standard_D2as_v5"
}

variable "aks_min_nodes" {
  type    = number
  default = 2
}

variable "aks_max_nodes" {
  type    = number
  default = 6
}

variable "admin_object_ids" {
  description = "Entra object IDs (people or groups) that get cluster-admin on AKS. The identity running Terraform always gets it."
  type        = list(string)
  default     = []
}

# ---- Data services ----

variable "pg_sku_name" {
  type    = string
  default = "GP_Standard_D2ds_v5"
}

variable "pg_storage_mb" {
  type    = number
  default = 65536
}

variable "pg_high_availability" {
  description = "Zone-redundant standby. Turn off for a cheaper non-production database."
  type        = bool
  default     = true
}

variable "redis_sku_name" {
  type    = string
  default = "Standard"
}

variable "redis_capacity" {
  type    = number
  default = 1
}

# ---- Application secrets (stored in Key Vault) ----

variable "otp_code" {
  description = "The shared 6-digit access code the admin gives to invited users."
  type        = string
  sensitive   = true

  validation {
    condition     = can(regex("^[0-9]{6}$", var.otp_code))
    error_message = "otp_code must be exactly 6 digits."
  }
}

variable "admin_mobiles" {
  description = "Comma separated admin mobile numbers."
  type        = string
  sensitive   = true
}

variable "allowed_mobiles" {
  description = "Comma separated invited mobile numbers (invite-only sign-in). Admins can always sign in."
  type        = string
  sensitive   = true
}

# ---- Optional ----

variable "enable_grafana" {
  description = "Create Azure Managed Grafana linked to the Prometheus workspace (billed separately)."
  type        = bool
  default     = false
}

variable "tags" {
  type    = map(string)
  default = { app = "strategic-trader" }
}
