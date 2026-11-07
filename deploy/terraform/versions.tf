terraform {
  required_version = ">= 1.6"

  required_providers {
    azurerm = {
      source  = "hashicorp/azurerm"
      version = "~> 4.0"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.6"
    }
    time = {
      source  = "hashicorp/time"
      version = "~> 0.12"
    }
  }

  # State lives in a storage account created once by deploy/scripts/bootstrap.sh.
  # The settings are passed at init time:  terraform init -backend-config=backend.hcl
  backend "azurerm" {}
}

provider "azurerm" {
  # Falls back to ARM_SUBSCRIPTION_ID, which the pipeline sets.
  subscription_id = var.subscription_id

  features {
    key_vault {
      purge_soft_delete_on_destroy = false
    }
    resource_group {
      prevent_deletion_if_contains_resources = false
    }
  }
}
